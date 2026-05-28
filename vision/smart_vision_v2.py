"""
Smart Vision V2 — Red-Zone-Aware deployment planner.

Capabilities:
  • Detect the enemy base's red deploy boundary (the orange/red dashed
    rectangle that marks the no-deploy zone).
  • Wait for enemy decorations to fade (CoC clears trees / props after
    a few seconds inside a battle), then re-screencap.
  • Build a SAFE deploy line that always sits OUTSIDE the red zone,
    against the screen-edge with the most free space.
  • Locate target buildings (town_hall_xx, gold_storage_xx, ...) and
    return the closest safe deploy point to the target.
  • Plan SPELL drops as a left/right pair anchored on the army's path,
    so spells reinforce the actual deployment instead of landing in
    distant corners.
  • Distribute deployment across multiple safe edges to avoid putting
    every troop on the same wall.
"""

from __future__ import annotations

import time
from typing import Iterable

import cv2
import numpy as np

from core.adb_handler import screencap
from core.logger import BotLogger
from vision.screen_reader import ScreenReader
from vision.template_manager import _load_manifest

log = BotLogger.get("vision_v2")


class SmartVisionV2:
    def __init__(self, screen_reader: ScreenReader):
        self._sr = screen_reader

    # ── Decoration fade ─────────────────────────────────────────────
    def wait_for_decorations(self, seconds: float) -> np.ndarray | None:
        if seconds > 0:
            log.info("V2: waiting %.1fs for enemy decorations to fade…", seconds)
            time.sleep(seconds)
        return screencap()

    # ── Red Zone Detection ──────────────────────────────────────────
    def red_zone_mask(self, screenshot: np.ndarray) -> np.ndarray:
        """Binary mask of the deploy boundary.

        CoC renders the deploy boundary as a DASHED line that varies
        between bright red, orange, and pink/magenta depending on the
        in-game theme. We union all three ranges, then aggressively
        close the dash gaps so contour detection can find a clean
        rectangle around the playfield.
        """
        hsv = cv2.cvtColor(screenshot, cv2.COLOR_BGR2HSV)
        m_red_low  = cv2.inRange(hsv, np.array([0,   100, 100]), np.array([12,  255, 255]))
        m_red_high = cv2.inRange(hsv, np.array([168, 100, 100]), np.array([180, 255, 255]))
        m_orange   = cv2.inRange(hsv, np.array([10,  120, 120]), np.array([24,  255, 255]))
        m_pink     = cv2.inRange(hsv, np.array([140,  60, 160]), np.array([170, 220, 255]))
        m_magenta  = cv2.inRange(hsv, np.array([150,  80, 140]), np.array([175, 255, 255]))
        mask = m_red_low | m_red_high | m_orange | m_pink | m_magenta

        # Two-pass close: first big horizontal/vertical kernels to bridge
        # dash gaps along each axis, then a square kernel to consolidate.
        kh = cv2.getStructuringElement(cv2.MORPH_RECT, (35, 3))
        kv = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 35))
        ks = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kh, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kv, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, ks, iterations=1)
        return mask

    def red_zone_bbox(self, screenshot: np.ndarray) -> tuple[int, int, int, int] | None:
        """Bounding rectangle of the deploy boundary.

        Stricter than before: the boundary MUST span the majority of the
        playfield (≥55% width AND ≥55% ui-cutoff height). Anything
        smaller is treated as a spurious red blob (red roof tile, lava
        pool, etc.) and rejected so the planner falls back to the proven
        base-bounding-box deploy line.
        """
        h, w = screenshot.shape[:2]
        ui_cutoff = self._sr.get_ui_cutoff(h)
        roi = screenshot[:ui_cutoff, :]
        mask = self.red_zone_mask(roi)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None
        contours = sorted(contours, key=cv2.contourArea, reverse=True)
        min_w = int(w * 0.55)
        min_h = int(ui_cutoff * 0.55)
        for c in contours:
            x, y, bw, bh = cv2.boundingRect(c)
            if bw < min_w or bh < min_h:
                continue
            if bw > w * 0.97 and bh > ui_cutoff * 0.97:
                continue  # full-screen match → noise
            return x, y, bw, bh
        return None

    def is_inside_red_zone(self, screenshot: np.ndarray, x: int, y: int, margin: int = 25) -> bool:
        bbox = self.red_zone_bbox(screenshot)
        if bbox is None:
            return False
        rx, ry, rw, rh = bbox
        return (rx - margin) <= x <= (rx + rw + margin) and (ry - margin) <= y <= (ry + rh + margin)

    # ── Safe Deploy Line ────────────────────────────────────────────
    def safe_deploy_line(
        self,
        screenshot: np.ndarray,
        count: int = 9,
        margin: int = 30,
        prefer_side: str | None = None,
    ) -> tuple[list[tuple[int, int]], str, tuple[int, int]]:
        """Return (points, side, anchor_xy) where points lie OUTSIDE the
        red zone along the screen edge with the most free space.

        side ∈ {"left","right","top","bottom"} — the edge the points run
        along. anchor_xy is the geometric center of the points (used as
        the spell anchor).
        """
        h, w = screenshot.shape[:2]
        ui_cutoff = self._sr.get_ui_cutoff(h)
        bbox = self.red_zone_bbox(screenshot)

        if bbox is None:
            line, base_xy = self._sr.get_focused_deployment_line(screenshot, ui_cutoff, count)
            mid = line[len(line) // 2] if line else (w // 2, ui_cutoff // 2)
            return line, "auto", mid

        rx, ry, rw, rh = bbox
        margins = {
            "left":   max(0, rx - margin),
            "right":  max(0, w - (rx + rw) - margin),
            "top":    max(0, ry - margin),
            "bottom": max(0, ui_cutoff - (ry + rh) - margin),
        }

        if prefer_side and margins.get(prefer_side, 0) > 0:
            side = prefer_side
        else:
            side = max(margins, key=margins.get)

        if margins[side] <= 0:
            line, base_xy = self._sr.get_focused_deployment_line(screenshot, ui_cutoff, count)
            mid = line[len(line) // 2] if line else (w // 2, ui_cutoff // 2)
            return line, "auto", mid

        # HUD-safe clamps — keep deploy points away from the top battle
        # banner (timer / surrender) and the bottom troop tray. Without
        # these floors the line top can land at y≈30 which CoC treats as
        # an HUD tap rather than a deploy.
        y_top_min = max(margin, 110)
        y_bot_max = max(margin, ui_cutoff - 80)
        x_lo = max(margin, 60)
        x_hi = min(w - margin, w - 60)

        # Stand-off: the deploy line MUST sit far enough outside the red
        # zone that tap jitter (±15 px) + dashed-line detector slop
        # (~±20 px) cannot push points back inside the no-deploy area.
        stand_off = 80

        if side == "left":
            x = max(margin, rx - max(stand_off, margins["left"] // 2))
            ys = np.linspace(max(y_top_min, ry + 30),
                             min(y_bot_max, ry + rh - 30), count, dtype=int)
            line = [(int(x), int(yy)) for yy in ys]
        elif side == "right":
            x = min(w - margin, rx + rw + max(stand_off, margins["right"] // 2))
            ys = np.linspace(max(y_top_min, ry + 30),
                             min(y_bot_max, ry + rh - 30), count, dtype=int)
            line = [(int(x), int(yy)) for yy in ys]
        elif side == "top":
            y = max(y_top_min, ry - max(stand_off, margins["top"] // 2))
            xs = np.linspace(max(x_lo, rx + 30),
                             min(x_hi, rx + rw - 30), count, dtype=int)
            line = [(int(xx), int(y)) for xx in xs]
        else:  # bottom
            y = min(y_bot_max, ry + rh + max(stand_off, margins["bottom"] // 2))
            xs = np.linspace(max(x_lo, rx + 30),
                             min(x_hi, rx + rw - 30), count, dtype=int)
            line = [(int(xx), int(y)) for xx in xs]

        line = [(int(np.clip(px, x_lo, x_hi)),
                 int(np.clip(py, y_top_min, y_bot_max))) for (px, py) in line]
        anchor = line[len(line) // 2]
        return line, side, anchor

    # ── Target Building ─────────────────────────────────────────────
    def find_target(self, screenshot: np.ndarray, asset_key: str) -> tuple[int, int] | None:
        return self._sr.find_template_by_name(screenshot, asset_key)

    @staticmethod
    def expand_storage_keys(prefix: str) -> list[str]:
        """Return every manifest key starting with `prefix` (e.g.
        "gold_storage" → ["gold_storage", "gold_storage_17", ...]).
        Lets the user pick a single concept and have the bot match every
        in-game level variant they have a template for.
        """
        if not prefix:
            return []
        manifest = _load_manifest()
        keys = [k for k in manifest.keys() if k == prefix or k.startswith(prefix + "_")]
        return sorted(keys)

    def find_all_targets(
        self, screenshot: np.ndarray, prefixes: Iterable[str],
    ) -> list[tuple[str, int, int]]:
        """Return one match (key, cx, cy) per prefix that hits."""
        out: list[tuple[str, int, int]] = []
        for prefix in prefixes:
            for key in self.expand_storage_keys(prefix) or [prefix]:
                hit = self._sr.find_template_by_name(screenshot, key)
                if hit:
                    out.append((key, hit[0], hit[1]))
                    break
        return out

    # ── Closest Safe Point ──────────────────────────────────────────
    def closest_safe_to(
        self, screenshot: np.ndarray, target_xy: tuple[int, int],
    ) -> tuple[int, int] | None:
        h, w = screenshot.shape[:2]
        ui_cutoff = self._sr.get_ui_cutoff(h)
        bbox = self.red_zone_bbox(screenshot)
        tx, ty = target_xy

        if bbox is None:
            return self._fallback_safe(target_xy, ui_cutoff, w)

        rx, ry, rw, rh = bbox
        # Stand-off: the cluster MUST sit far enough outside the red zone
        # that the tap-jitter (±15 px) plus any red-zone-detector slop
        # (±20 px is realistic for dashed lines) cannot push it inside.
        # 80 px clears both with safe room.
        stand_off = 80
        margin = 60
        # HUD safe band — keep cluster clear of top/bottom HUD strips.
        y_top_min = max(margin, 110)
        y_bot_max = max(margin, ui_cutoff - 80)
        candidates = [
            # left edge of base
            (max(margin, rx - stand_off),
             int(np.clip(ty, ry + 30, ry + rh - 30))),
            # right edge of base
            (min(w - margin, rx + rw + stand_off),
             int(np.clip(ty, ry + 30, ry + rh - 30))),
            # top edge of base
            (int(np.clip(tx, rx + 30, rx + rw - 30)),
             max(y_top_min, ry - stand_off)),
            # bottom edge of base
            (int(np.clip(tx, rx + 30, rx + rw - 30)),
             min(y_bot_max, ry + rh + stand_off)),
        ]
        candidates = [(int(x), int(y)) for x, y in candidates]
        candidates = [c for c in candidates
                      if margin <= c[0] <= w - margin
                      and y_top_min <= c[1] <= y_bot_max]
        if not candidates:
            return self._fallback_safe(target_xy, ui_cutoff, w)
        candidates.sort(key=lambda p: (p[0] - tx) ** 2 + (p[1] - ty) ** 2)
        return candidates[0]

    @staticmethod
    def _fallback_safe(target_xy: tuple[int, int], ui_cutoff: int, w: int) -> tuple[int, int]:
        tx, ty = target_xy
        return int(np.clip(tx, 60, w - 60)), int(np.clip(ty, 110, ui_cutoff - 80))

    # ── Spell Plan (left + right of army path) ──────────────────────
    def plan_spell_drops(
        self,
        screenshot: np.ndarray,
        anchor_xy: tuple[int, int],
        side: str,
        spell_count: int,
        depth_pct: float = 0.55,
    ) -> list[tuple[int, int]]:
        """Build `spell_count` drop points along the line that runs from
        the deployment anchor INTO the base, alternating left/right of
        that line so spells flank the army instead of clustering.
        """
        h, w = screenshot.shape[:2]
        ui_cutoff = self._sr.get_ui_cutoff(h)
        ax, ay = anchor_xy
        cx, cy = w // 2, ui_cutoff // 2

        dx, dy = (cx - ax), (cy - ay)
        norm = max(1.0, (dx * dx + dy * dy) ** 0.5)
        ux, uy = dx / norm, dy / norm
        # Perpendicular unit vector (for left/right offsets).
        px, py = -uy, ux

        out: list[tuple[int, int]] = []
        for i in range(spell_count):
            depth = depth_pct + 0.10 * (i // 2)
            depth = max(0.30, min(depth, 0.95))
            base_x = ax + ux * norm * depth
            base_y = ay + uy * norm * depth
            offset = 90 + 35 * (i // 2)
            sign = 1 if (i % 2 == 0) else -1
            sx = int(base_x + px * offset * sign)
            sy = int(base_y + py * offset * sign)
            sx = int(np.clip(sx, 60, w - 60))
            sy = int(np.clip(sy, 60, ui_cutoff - 60))
            out.append((sx, sy))
        return out
