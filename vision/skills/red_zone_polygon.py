"""
RedZonePolygonSkill — detect the deploy-boundary as a CLOSED POLYGON
(not a bounding box).

Why a polygon: real bases have non-rectangular outlines (crosses,
T-shapes, etc). A bbox treats those bases as solid rectangles and
produces "safe" cluster points that are actually inside the no-deploy
zone in 30%+ of cases.

Pipeline (HSV pass):
    1. UI-band masking — zero out the top loot/timer strip and the
       bottom troop bar BEFORE colour matching, so the loot icons,
       timer banner, and deck don't pollute the red mask.
    2. HSV mask of red/orange/pink dashes with STRICT saturation so the
       semi-transparent UI overlays (timer banner, ranking emblems)
       don't qualify.
    3. Two-axis morphological close to bridge dash gaps.
    4. Largest external contour, convex hull, Douglas-Peucker.
    5. Sanity validation — reject polygons that touch the top edge
       (UI contamination), cover almost the entire playfield, or have
       degenerate aspect ratio.
    6. Multi-contour fusion fallback — when the LARGEST single contour
       fails sanity (typically because the morph close didn't bridge
       top↔bottom dashes and we caught only a horizontal slice), the
       skill stacks the top-K contours and tries again on the combined
       convex hull. This recovers fragmented detections without
       loosening the per-contour gates.

Fallback (inversion pass): if the HSV pass returns nothing valid, the
detector inverts the image and re-runs the same pipeline against
CYAN (which is what the perimeter dashes turn into after a bitwise NOT).
This is the user-suggested "color inversion" trick: it isolates the
perimeter line clearly when the base theme is dark/blue/snow and the
standard HSV pass struggles.

The inverted screenshot is ONLY used to compute the polygon. After
that the orchestrator goes back to the original full-colour screenshot
for every other vision step (troop card lookup, building location,
obstacle detection, etc.).

Debug dumps: set ``polygon.debug_dump`` to a directory path in
``v2_attack_rules.json`` and the skill will write
``redzone_<mode>_<ts>.png`` overlays whenever a pass fails sanity, so
you can SEE exactly what the detector caught.

Returns Nx2 int32 vertex array, or None when no valid polygon detected.
"""

from __future__ import annotations

import os
import time
from typing import List, Optional

import cv2
import numpy as np

from core.logger import BotLogger

log = BotLogger.get("v2.red_zone_polygon")


class RedZonePolygonSkill:
    name = "red_zone_polygon"

    def detect(
        self,
        screenshot: np.ndarray,
        ui_cutoff: int,
        config: dict | None = None,
    ) -> Optional[np.ndarray]:
        """Return Nx2 int32 polygon vertices, or None if not detected."""
        if screenshot is None:
            return None
        cfg = (config or {}).get("polygon", {}) if config else {}
        h, w = screenshot.shape[:2]
        ui_cutoff = max(1, min(ui_cutoff, h))

        verts = self._run_pass(screenshot, ui_cutoff, cfg, mode="hsv")
        if verts is not None:
            return verts

        if bool(cfg.get("use_inversion_fallback", True)):
            log.info("RedZone HSV pass failed sanity — retrying with colour-inversion fallback.")
            verts = self._run_pass(screenshot, ui_cutoff, cfg, mode="inversion")
            if verts is not None:
                return verts

        log.warning("RedZone polygon: detection FAILED on both HSV and inversion passes.")
        return None

    # ── Internals ─────────────────────────────────────────────────
    def _run_pass(
        self,
        screenshot: np.ndarray,
        ui_cutoff: int,
        cfg: dict,
        mode: str,
    ) -> Optional[np.ndarray]:
        h, w = screenshot.shape[:2]
        roi = screenshot[:ui_cutoff, :]
        if mode == "inversion":
            roi = cv2.bitwise_not(roi)
            mask = self._build_mask_inverted(roi, cfg)
        else:
            mask = self._build_mask(roi, cfg)

        # Zero out the top loot/timer strip and the side loot panels so
        # they cannot produce a polygon vertex on the screen border.
        top_excl = int(cfg.get("top_ui_exclude_px", 150))
        if top_excl > 0:
            mask[:min(top_excl, mask.shape[0]), :] = 0
        # Side strips: 'Available Loot' panel on the left and the ranked
        # gold/elixir bars on the right. Width comes from config so each
        # device can tune it without re-shipping code.
        side_excl_l = int(cfg.get("left_ui_exclude_px", 0))
        if side_excl_l > 0:
            mask[:int(top_excl * 2.5), :min(side_excl_l, mask.shape[1])] = 0
        side_excl_r = int(cfg.get("right_ui_exclude_px", 0))
        if side_excl_r > 0:
            cut = max(0, mask.shape[1] - side_excl_r)
            mask[:int(top_excl * 2.5), cut:] = 0
        # Bottom UI strip — the chat/clan-castle/Surrender buttons can
        # bleed warm-coloured pixels into the bottom of the playfield
        # ROI. Mask the last `bottom_ui_exclude_px` rows above ui_cutoff.
        bottom_excl = int(cfg.get("bottom_ui_exclude_px", 0))
        if bottom_excl > 0:
            cut = max(0, mask.shape[0] - bottom_excl)
            mask[cut:, :] = 0

        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
        )
        if not contours:
            log.debug("RedZone (%s): no contours.", mode)
            return None

        playfield_area = float(w * ui_cutoff)
        min_area_ratio = float(cfg.get("min_polygon_area_ratio", 0.10))
        max_area_ratio = float(cfg.get("max_polygon_area_ratio", 0.90))
        min_area = max(2000.0, playfield_area * min_area_ratio)
        max_area = playfield_area * max_area_ratio
        eps = float(cfg.get("approx_eps_px", 2.0))

        # ── Attempt 1: largest single contour ────────────────────
        best = max(contours, key=cv2.contourArea)
        verts = self._verts_from_contour(best, eps)
        if verts is not None:
            best_area = float(cv2.contourArea(best))
            if min_area <= best_area <= max_area and \
                    self._sanity_ok(verts, w, ui_cutoff, cfg, mode):
                self._log_polygon(mode, verts, best_area, "single")
                return verts
            elif best_area < min_area:
                log.debug("RedZone (%s) single: area %.0f < min %.0f.",
                          mode, best_area, min_area)
            elif best_area > max_area:
                log.debug("RedZone (%s) single: area %.0f > max %.0f (UI?).",
                          mode, best_area, max_area)

        # ── Attempt 2: fuse the top-K contours into one hull ─────
        # Real perimeters are often broken into 2-4 pieces when the
        # morph close can't bridge the gap. Stacking them and taking the
        # combined convex hull recovers the true outline.
        fuse_k = int(cfg.get("fuse_top_k", 5))
        fuse_min_each = max(200.0, min_area * 0.05)
        ranked = sorted(
            (c for c in contours if cv2.contourArea(c) >= fuse_min_each),
            key=cv2.contourArea, reverse=True,
        )[:max(2, fuse_k)]
        if len(ranked) >= 2:
            stacked = np.vstack(ranked)
            verts2 = self._verts_from_contour(stacked, eps)
            if verts2 is not None:
                fused_area = float(cv2.contourArea(cv2.convexHull(stacked)))
                if min_area <= fused_area <= max_area and \
                        self._sanity_ok(verts2, w, ui_cutoff, cfg, mode):
                    self._log_polygon(mode, verts2, fused_area,
                                      f"fused-{len(ranked)}")
                    return verts2
                else:
                    log.debug(
                        "RedZone (%s) fused-%d: area=%.0f sanity FAIL.",
                        mode, len(ranked), fused_area,
                    )

        # Both attempts failed — optionally dump a debug overlay so the
        # user can see what we caught.
        self._maybe_dump(screenshot, mask, contours, mode, cfg)
        return None

    @staticmethod
    def _verts_from_contour(
        contour: np.ndarray, eps: float,
    ) -> Optional[np.ndarray]:
        if contour is None or len(contour) < 3:
            return None
        hull = cv2.convexHull(contour)
        approx = cv2.approxPolyDP(hull, eps, True)
        if approx is None or len(approx) < 4:
            return None
        return approx.reshape(-1, 2).astype(np.int32)

    @staticmethod
    def _log_polygon(
        mode: str, verts: np.ndarray, area: float, source: str,
    ) -> None:
        x_min, y_min = verts.min(axis=0)
        x_max, y_max = verts.max(axis=0)
        bw, bh = int(x_max - x_min), int(y_max - y_min)
        log.info(
            "RedZone polygon (%s/%s): %d verts, bbox=(%d,%d,%d,%d), area=%.0f",
            mode, source, len(verts), int(x_min), int(y_min), bw, bh, area,
        )

    @staticmethod
    def _sanity_ok(
        verts: np.ndarray, w: int, ui_cutoff: int, cfg: dict, mode: str,
    ) -> bool:
        x_min, y_min = verts.min(axis=0)
        x_max, y_max = verts.max(axis=0)
        bw, bh = int(x_max - x_min), int(y_max - y_min)

        if bw > w * 0.97 and bh > ui_cutoff * 0.97:
            log.debug("RedZone (%s) sanity FAIL: covers entire playfield.", mode)
            return False

        # Polygon must NOT touch the top of the screen — if it does, the
        # mask was contaminated by the timer banner / loot HUD.
        min_top_y = int(cfg.get("min_polygon_y_px", 60))
        if y_min < min_top_y:
            log.debug("RedZone (%s) sanity FAIL: top y_min=%d < %d (UI contamination).",
                      mode, y_min, min_top_y)
            return False

        # Aspect ratio sanity — a real CoC base is roughly square-ish at
        # zoom-out (0.45 ≤ ratio ≤ 2.2). Strips that look like 5:1 or
        # 1:5 are almost always UI strips, not bases.
        if bw <= 0 or bh <= 0:
            return False
        ratio = bw / max(1, bh)
        if ratio < 0.40 or ratio > 2.5:
            log.debug("RedZone (%s) sanity FAIL: aspect ratio %.2f out of range.",
                      mode, ratio)
            return False

        # Minimum tile width — a TH13+ base at fair zoom is at least
        # ~600 px wide. Anything smaller is a fragment of dashes that
        # leaked through the morph close.
        min_w = int(cfg.get("min_polygon_width_px", 500))
        if bw < min_w:
            log.debug("RedZone (%s) sanity FAIL: width %d < %d.", mode, bw, min_w)
            return False

        return True

    @staticmethod
    def _build_mask(roi: np.ndarray, cfg: dict) -> np.ndarray:
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        # Stricter saturation (was 100) keeps semi-transparent HUD
        # overlays out of the mask. The actual perimeter dashes hit
        # S ≥ 180 reliably across themes.
        s_min = int(cfg.get("hsv_s_min", 150))
        v_min = int(cfg.get("hsv_v_min", 110))
        m_red_low  = cv2.inRange(hsv, np.array([0,   s_min, v_min]), np.array([12,  255, 255]))
        m_red_high = cv2.inRange(hsv, np.array([168, s_min, v_min]), np.array([180, 255, 255]))
        m_orange   = cv2.inRange(hsv, np.array([10,  s_min, v_min]), np.array([24,  255, 255]))
        # Pink/magenta dashes appear on lava themes. Saturation eased
        # because pink reads as desaturated red on emulator screencaps.
        m_pink     = cv2.inRange(hsv, np.array([140, 110, v_min]), np.array([170, 220, 255]))
        m_magenta  = cv2.inRange(hsv, np.array([150, 130, v_min]), np.array([175, 255, 255]))
        mask = m_red_low | m_red_high | m_orange | m_pink | m_magenta

        kh = tuple(cfg.get("morph_close_h_kernel", [35, 3]))
        kv = tuple(cfg.get("morph_close_v_kernel", [3, 35]))
        ks = tuple(cfg.get("morph_close_square", [9, 9]))
        kh_el = cv2.getStructuringElement(cv2.MORPH_RECT, kh)
        kv_el = cv2.getStructuringElement(cv2.MORPH_RECT, kv)
        ks_el = cv2.getStructuringElement(cv2.MORPH_RECT, ks)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kh_el, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kv_el, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, ks_el, iterations=1)
        return mask

    @staticmethod
    def _build_mask_inverted(roi_inv: np.ndarray, cfg: dict) -> np.ndarray:
        """After ``cv2.bitwise_not``, the perimeter dashes (originally
        red H≈0/180) move to cyan (H≈90). Detect THAT range instead.
        Same morph closing, same kernel sizes — only the colour band
        changes."""
        hsv = cv2.cvtColor(roi_inv, cv2.COLOR_BGR2HSV)
        s_min = int(cfg.get("hsv_s_min", 150))
        v_min = int(cfg.get("hsv_v_min", 110))
        m_cyan = cv2.inRange(hsv, np.array([78,  s_min, v_min]), np.array([102, 255, 255]))
        m_blue = cv2.inRange(hsv, np.array([95,  s_min, v_min]), np.array([115, 255, 255]))
        # Inverted orange becomes light teal/blue.
        m_teal = cv2.inRange(hsv, np.array([85,  120, v_min]), np.array([100, 255, 255]))
        mask = m_cyan | m_blue | m_teal

        kh = tuple(cfg.get("morph_close_h_kernel", [35, 3]))
        kv = tuple(cfg.get("morph_close_v_kernel", [3, 35]))
        ks = tuple(cfg.get("morph_close_square", [9, 9]))
        kh_el = cv2.getStructuringElement(cv2.MORPH_RECT, kh)
        kv_el = cv2.getStructuringElement(cv2.MORPH_RECT, kv)
        ks_el = cv2.getStructuringElement(cv2.MORPH_RECT, ks)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kh_el, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kv_el, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, ks_el, iterations=1)
        return mask

    @staticmethod
    def _maybe_dump(
        screenshot: np.ndarray,
        mask: np.ndarray,
        contours: List[np.ndarray],
        mode: str,
        cfg: dict,
    ) -> None:
        """When sanity fails, optionally drop a side-by-side debug
        image so the user can SEE what the detector caught vs. the raw
        screenshot. Enabled via ``polygon.debug_dump = "<dir>"`` in
        ``v2_attack_rules.json``."""
        out_dir = cfg.get("debug_dump") or ""
        if not out_dir:
            return
        try:
            os.makedirs(out_dir, exist_ok=True)
            overlay = screenshot.copy()
            roi_h = mask.shape[0]
            # Tint mask onto the playfield region in red.
            tint = np.zeros_like(overlay)
            tint[:roi_h, :, 2] = mask  # R channel
            overlay = cv2.addWeighted(overlay, 0.7, tint, 0.5, 0)
            # Draw every found contour in cyan so fragmented detections
            # are visible.
            for c in contours[:8]:
                cv2.drawContours(overlay, [c], -1, (255, 255, 0), 2)
            # Draw the largest hull in green for emphasis.
            if contours:
                top = max(contours, key=cv2.contourArea)
                cv2.drawContours(overlay, [cv2.convexHull(top)], -1,
                                 (0, 255, 0), 3)
            ts = int(time.time() * 1000)
            path = os.path.join(out_dir, f"redzone_{mode}_{ts}.png")
            cv2.imwrite(path, overlay)
            log.info("RedZone debug dump → %s", path)
        except Exception as exc:
            log.debug("RedZone debug dump failed: %s", exc)

    @staticmethod
    def is_inside(polygon: np.ndarray, x: int, y: int, margin: int = 0) -> bool:
        """Point-in-polygon with optional inflation margin (px)."""
        if polygon is None or len(polygon) < 3:
            return False
        if margin == 0:
            return cv2.pointPolygonTest(polygon, (float(x), float(y)), False) >= 0
        dist = cv2.pointPolygonTest(polygon, (float(x), float(y)), True)
        return dist >= -float(margin)

    @staticmethod
    def bbox(polygon: np.ndarray) -> tuple[int, int, int, int] | None:
        if polygon is None or len(polygon) == 0:
            return None
        x, y, w, h = cv2.boundingRect(polygon)
        return int(x), int(y), int(w), int(h)

    @staticmethod
    def centroid(polygon: np.ndarray) -> tuple[int, int] | None:
        if polygon is None or len(polygon) == 0:
            return None
        m = cv2.moments(polygon)
        if abs(m["m00"]) < 1e-3:
            x, y, w, h = cv2.boundingRect(polygon)
            return int(x + w / 2), int(y + h / 2)
        return int(m["m10"] / m["m00"]), int(m["m01"] / m["m00"])
