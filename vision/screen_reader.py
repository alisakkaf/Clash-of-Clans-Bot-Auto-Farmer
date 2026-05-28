"""
Screen Reader — V59 Simple Grayscale with bb_troop_slot.

V59 FIXES:
  • Removed all complex X-coordinate cropping and color-matching logic.
  • Uses ONLY the user's defined `bb_troop_slot` to dynamically find the UI bar.
  • Performs a simple grayscale match inside that horizontal strip to reliably find 
    both ALIVE (Stage 1) and DEAD (Stage 2) troops.
"""

import os
import random

import cv2
import numpy as np

from core.logger import BotLogger
from core.state_machine import GameState
from core.settings import Settings
from vision.template_manager import get_template_path, DEFAULT_ASSETS, _load_manifest

log = BotLogger.get("vision")

# All thresholds + scales are TUNABLES → read from Settings() at call time.
# DO NOT reintroduce module-level constants for these values.

def _ui_thr() -> float:
    return float(Settings().get("vision_ui_threshold", 0.80))

def _troop_thr() -> float:
    return float(Settings().get("vision_troop_threshold", 0.42))

def _building_thr() -> float:
    return float(Settings().get("vision_building_threshold", 0.40))

def _bb_card_thr() -> float:
    return float(Settings().get("vision_bb_card_threshold", 0.45))

def _scales() -> list[float]:
    s = Settings().get("template_scales", [0.8, 0.9, 1.0, 1.1, 1.2])
    return list(s) if s else [1.0]

TROOP_CATEGORIES = {"troops", "spells", "heroes"}
BUILDING_CATEGORIES = {"buildings", "builder_base"}

FALLBACK_BATTLEFIELD_RATIO = 0.60

# Deployment line params
BASE_OFFSET = 80       
LINE_SPACING = 35      
LINE_POINTS = 15       
X_CLAMP_MIN = 30
Y_CLAMP_MIN = 120
CLAMP_PAD = 40


def _get_troops_bar_height() -> int | None:
    manifest = _load_manifest()
    entry = manifest.get("troops_bar")
    if entry and entry.get("height"):
        return int(entry["height"])
    return None


class ScreenReader:
    _template_cache: dict[str, tuple[np.ndarray, np.ndarray | None, str]] = {}

    @staticmethod
    def get_ui_cutoff(screen_height: int) -> int:
        bar_h = _get_troops_bar_height()
        if bar_h is not None and bar_h > 0:
            cutoff = screen_height - bar_h
        else:
            cutoff = int(screen_height * FALLBACK_BATTLEFIELD_RATIO)
        return max(int(screen_height * 0.40), min(cutoff, int(screen_height * 0.85)))

    @staticmethod
    def _detect_red_mask(screenshot: np.ndarray, ui_cutoff: int) -> np.ndarray:
        hsv = cv2.cvtColor(screenshot, cv2.COLOR_BGR2HSV)
        m1 = cv2.inRange(hsv, np.array([0, 70, 50]), np.array([10, 255, 255]))
        m2 = cv2.inRange(hsv, np.array([170, 70, 50]), np.array([180, 255, 255]))
        mask = cv2.bitwise_or(m1, m2)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
        mask[ui_cutoff:, :] = 0
        return mask

    @staticmethod
    def get_base_bounding_box(screenshot: np.ndarray, ui_cutoff: int) -> tuple[int, int, int, int]:
        h, w = screenshot.shape[:2]
        mask = ScreenReader._detect_red_mask(screenshot, ui_cutoff)
        
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        valid_contours = [c for c in contours if cv2.contourArea(c) > 400]
        
        if valid_contours:
            x_min = min(cv2.boundingRect(c)[0] for c in valid_contours)
            y_min = min(cv2.boundingRect(c)[1] for c in valid_contours)
            x_max = max(cv2.boundingRect(c)[0] + cv2.boundingRect(c)[2] for c in valid_contours)
            y_max = max(cv2.boundingRect(c)[1] + cv2.boundingRect(c)[3] for c in valid_contours)
            
            bx, by, bw, bh = x_min, y_min, x_max - x_min, y_max - y_min
            
            if bw > w * 0.90:
                pts = cv2.findNonZero(mask)
                if pts is not None:
                    med_x = int(np.median(pts[:, 0, 0]))
                    med_y = int(np.median(pts[:, 0, 1]))
                    bx, by = max(0, med_x - w//4), max(0, med_y - ui_cutoff//4)
                    bw, bh = w//2, ui_cutoff//2
            
            return bx, by, bw, bh

        bx = int(w * 0.20)
        by = int(ui_cutoff * 0.20)
        bw = int(w * 0.60)
        bh = int(ui_cutoff * 0.60)
        return bx, by, bw, bh

    @staticmethod
    def get_focused_deployment_line(
        screenshot: np.ndarray, ui_cutoff: int | None = None,
        count: int = LINE_POINTS, edge: str | None = None,
    ) -> tuple[list[tuple[int, int]], tuple[int, int]]:
        h, w = screenshot.shape[:2]
        if ui_cutoff is None:
            ui_cutoff = ScreenReader.get_ui_cutoff(h)

        bx, by, bw, bh = ScreenReader.get_base_bounding_box(screenshot, ui_cutoff)
        base_cx = bx + bw // 2
        base_cy = by + bh // 2

        x_max_clamp = w - X_CLAMP_MIN
        y_max_clamp = ui_cutoff - CLAMP_PAD

        if edge is None:
            candidates = []
            left_space = bx
            right_space = w - (bx + bw)
            top_space = by - Y_CLAMP_MIN

            if left_space > 40: candidates.append(("LEFT", left_space))
            if right_space > 40: candidates.append(("RIGHT", right_space))
            if top_space > 40: candidates.append(("TOP", top_space))

            if candidates:
                edge = max(candidates, key=lambda c: c[1])[0]
            else:
                edge = random.choice(["LEFT", "TOP", "RIGHT"])

        half_span = (count // 2) * LINE_SPACING
        points: list[tuple[int, int]] = []

        if edge == "LEFT":
            anchor_x = max(X_CLAMP_MIN, bx - BASE_OFFSET)
            anchor_y = base_cy
            for i in range(count):
                py = anchor_y - half_span + i * LINE_SPACING
                points.append((max(X_CLAMP_MIN, min(anchor_x, x_max_clamp)), max(Y_CLAMP_MIN, min(py, y_max_clamp))))

        elif edge == "RIGHT":
            anchor_x = min(x_max_clamp, bx + bw + BASE_OFFSET)
            anchor_y = base_cy
            for i in range(count):
                py = anchor_y - half_span + i * LINE_SPACING
                points.append((max(X_CLAMP_MIN, min(anchor_x, x_max_clamp)), max(Y_CLAMP_MIN, min(py, y_max_clamp))))

        elif edge == "TOP":
            anchor_x = base_cx
            anchor_y = max(Y_CLAMP_MIN, by - BASE_OFFSET)
            for i in range(count):
                px = anchor_x - half_span + i * LINE_SPACING
                points.append((max(X_CLAMP_MIN, min(px, x_max_clamp)), max(Y_CLAMP_MIN, min(anchor_y, y_max_clamp))))

        return points, (base_cx, base_cy)

    def _get_cached_template(self, name: str) -> tuple[np.ndarray, np.ndarray | None, str] | None:
        if name in self._template_cache:
            return self._template_cache[name]

        path = get_template_path(name)
        if path is None or not os.path.isfile(path): return None

        if name in DEFAULT_ASSETS:
            category = DEFAULT_ASSETS[name][0]
        else:
            manifest = _load_manifest()
            entry = manifest.get(name, {})
            category = entry.get("category", "custom")

        raw = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if raw is None: return None

        if len(raw.shape) == 2:
            bgr = cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)
            mask = None
        elif raw.shape[2] == 4:
            bgr = raw[:, :, :3]
            alpha = raw[:, :, 3]
            _, mask = cv2.threshold(alpha, 128, 255, cv2.THRESH_BINARY)
        elif raw.shape[2] == 3:
            bgr = raw
            mask = None
        else:
            bgr = raw[:, :, :3]
            mask = None

        self._template_cache[name] = (bgr, mask, category)
        return bgr, mask, category

    @staticmethod
    def _raw_match(
        region: np.ndarray, tmpl: np.ndarray,
        mask: np.ndarray | None, use_mask: bool,
    ) -> tuple[float, tuple[int, int], tuple[int, int]]:
        th, tw = tmpl.shape[:2]
        rh, rw = region.shape[:2]
        if th > rh or tw > rw:
            return -1.0, (0, 0), (th, tw)
        if use_mask and mask is not None:
            result = cv2.matchTemplate(region, tmpl, cv2.TM_CCORR_NORMED, mask=mask)
        else:
            result = cv2.matchTemplate(region, tmpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        return max_val, max_loc, (th, tw)

    def _match_ui(self, screenshot: np.ndarray, tmpl_bgr: np.ndarray, threshold: float) -> tuple[int, int, float] | None:
        gray_ss = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
        gray_t = cv2.cvtColor(tmpl_bgr, cv2.COLOR_BGR2GRAY)
        val, loc, dims = self._raw_match(gray_ss, gray_t, None, False)
        if val >= threshold:
            return loc[0] + dims[1]//2, loc[1] + dims[0]//2, val
        return None

    @staticmethod
    def _troop_scales() -> list[float]:
        """Live-read template scales used for troop/spell/hero matching."""
        return _scales()

    def _match_troop(
        self, screenshot: np.ndarray, tmpl_bgr: np.ndarray,
        tmpl_mask: np.ndarray | None, threshold: float,
    ) -> tuple[int, int, float] | None:
        h, w = screenshot.shape[:2]
        ui_cutoff = self.get_ui_cutoff(h)
        
        safe_width = int(w * 0.80)
        bar_region = screenshot[ui_cutoff:, :safe_width]
        
        gray_bar = cv2.cvtColor(bar_region, cv2.COLOR_BGR2GRAY)
        gray_t = cv2.cvtColor(tmpl_bgr, cv2.COLOR_BGR2GRAY)

        best_val = -1.0
        best_loc = (0, 0)
        best_dims = gray_t.shape[:2]

        for scale in self._troop_scales():
            nw = max(8, int(gray_t.shape[1] * scale))
            nh = max(8, int(gray_t.shape[0] * scale))
            s_tmpl = cv2.resize(gray_t, (nw, nh), interpolation=cv2.INTER_AREA)
            s_mask = cv2.resize(tmpl_mask, (nw, nh), interpolation=cv2.INTER_NEAREST) if tmpl_mask is not None else None

            cy1, cy2 = int(nh * 0.30), int(nh * 0.75)
            cx1, cx2 = int(nw * 0.30), int(nw * 0.80)
            
            if cy2 <= cy1 or cx2 <= cx1: continue
            
            c_tmpl = s_tmpl[cy1:cy2, cx1:cx2]
            c_mask = s_mask[cy1:cy2, cx1:cx2] if s_mask is not None else None

            val, loc, dims = self._raw_match(gray_bar, c_tmpl, c_mask, True)
            
            if val > best_val:
                best_val = val
                best_loc = (loc[0] - cx1, loc[1] - cy1)
                best_dims = (nh, nw)

        if best_val >= threshold:
            cx = best_loc[0] + best_dims[1] // 2
            cy = best_loc[1] + best_dims[0] // 2 + ui_cutoff
            return cx, cy, best_val
            
        return None

    def _match_bb_card(self, screenshot: np.ndarray, tmpl_bgr: np.ndarray, tmpl_mask: np.ndarray | None, threshold: float) -> tuple[int, int, float] | None:
        """V59: Clean Grayscale crop based purely on the `bb_troop_slot`."""
        h, w = screenshot.shape[:2]
        
        # Default start if slot not found
        y_start = int(h * 0.70)
        
        slot_tmpl = self._get_cached_template("bb_troop_slot")
        if slot_tmpl is not None:
            # Find the slot in the lower 40% of the screen
            search_area = screenshot[int(h * 0.60):, :]
            gray_ss = cv2.cvtColor(search_area, cv2.COLOR_BGR2GRAY)
            gray_slot = cv2.cvtColor(slot_tmpl[0], cv2.COLOR_BGR2GRAY)
            res = cv2.matchTemplate(gray_ss, gray_slot, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            
            if max_val > 0.40:
                exact_y = max_loc[1] + int(h * 0.60)
                # Set crop start dynamically based on the found slot
                y_start = max(int(h * 0.50), exact_y - 20)

        # Crop from y_start to the bottom, covering 85% of screen width (avoids right side)
        bar_region = screenshot[y_start:h, :int(w * 0.85)]
        
        # Simple Grayscale match
        gray_bar = cv2.cvtColor(bar_region, cv2.COLOR_BGR2GRAY)
        gray_t = cv2.cvtColor(tmpl_bgr, cv2.COLOR_BGR2GRAY)

        best_val = -1.0
        best_loc = (0, 0)
        best_dims = gray_t.shape[:2]

        for scale in self._troop_scales():
            nw = max(8, int(gray_t.shape[1] * scale))
            nh = max(8, int(gray_t.shape[0] * scale))
            
            s_tmpl = cv2.resize(gray_t, (nw, nh), interpolation=cv2.INTER_AREA)
            
            if tmpl_mask is not None:
                s_mask = cv2.resize(tmpl_mask, (nw, nh), interpolation=cv2.INTER_NEAREST)
            else:
                s_mask = None

            cy1, cy2 = int(nh * 0.30), int(nh * 0.75)
            cx1, cx2 = int(nw * 0.30), int(nw * 0.80)
            
            if cy2 <= cy1 or cx2 <= cx1: continue
            
            c_tmpl = s_tmpl[cy1:cy2, cx1:cx2]
            c_mask = s_mask[cy1:cy2, cx1:cx2] if s_mask is not None else None

            val, loc, dims = self._raw_match(gray_bar, c_tmpl, c_mask, True)
            
            if val > best_val:
                best_val = val
                best_loc = (loc[0] - cx1, loc[1] - cy1)
                best_dims = (nh, nw)

        if best_val >= threshold:
            cx = best_loc[0] + best_dims[1] // 2
            cy = best_loc[1] + best_dims[0] // 2 + y_start
            log.debug("BB Card GRAY match: conf=%.3f at (%d,%d)", best_val, cx, cy)
            return cx, cy, best_val
            
        return None

    def _match_building(self, screenshot: np.ndarray, tmpl_bgr: np.ndarray, tmpl_mask: np.ndarray | None, threshold: float) -> tuple[int, int, float] | None:
        gray_ss = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
        gray_t = cv2.cvtColor(tmpl_bgr, cv2.COLOR_BGR2GRAY)
        val, loc, dims = self._raw_match(gray_ss, gray_t, tmpl_mask, True)
        if val >= threshold:
            return loc[0] + dims[1]//2, loc[1] + dims[0]//2, val
        return None

    def find_template_by_name(self, screenshot: np.ndarray, template_name: str, threshold: float | None = None) -> tuple[int, int] | None:
        cached = self._get_cached_template(template_name)
        if cached is None: return None
        tmpl_bgr, tmpl_mask, category = cached

        if template_name.endswith("_bb"):
            thr = threshold if threshold is not None else _bb_card_thr()
            result = self._match_bb_card(screenshot, tmpl_bgr, tmpl_mask, thr)
        elif category in TROOP_CATEGORIES:
            thr = threshold if threshold is not None else _troop_thr()
            result = self._match_troop(screenshot, tmpl_bgr, tmpl_mask, thr)
        elif category in BUILDING_CATEGORIES:
            thr = threshold if threshold is not None else _building_thr()
            result = self._match_building(screenshot, tmpl_bgr, tmpl_mask, thr)
        else:
            thr = threshold if threshold is not None else _ui_thr()
            result = self._match_ui(screenshot, tmpl_bgr, thr)

        return (result[0], result[1]) if result else None

    def scan_for_confirmations(self, screenshot: np.ndarray) -> list[tuple[str, int, int, float]]:
        names = [
            "ranked_mode_btn", "normal_mode_btn",
            "attack_button2",
            "confirm_button",
            "end_battle_confirm", "reload_button",
        ]
        found = []
        for name in names:
            loc = self.find_template_by_name(screenshot, name)
            if loc:
                found.append((name, loc[0], loc[1], 1.0))
        return found

    def detect_state(self, screenshot: np.ndarray) -> GameState:
        f = self.find_template_by_name
        
        if f(screenshot, "connection_error"):  return GameState.DISCONNECTED
        if f(screenshot, "reload_button"):     return GameState.DISCONNECTED
        if f(screenshot, "loading_screen"):    return GameState.LOADING
        
        # 1. SCOUTING (Home Village)
        if f(screenshot, "next_button"):       return GameState.OPPONENT_FOUND
        
        # ── BUILDER BASE SPECIFIC CHECKS ──
        if f(screenshot, "bb_find_match", 0.88):     return GameState.BUILDER_BASE_HOME
        if f(screenshot, "bb_attack_confirm", 0.88): return GameState.BUILDER_BASE_HOME
        if f(screenshot, "bb_return_home", 0.80):    return GameState.BATTLE_ENDED
        if f(screenshot, "bb_battle_result", 0.80):  return GameState.BATTLE_ENDED

        # The "LOT ASSESET SHIELD" is a last-resort home-village hint;
        # we only honour it AFTER the CONFIRMING dialog has been ruled out
        # and at a sane confidence so it never misfires on the dialog.
        if f(screenshot, "lot_asseset", 0.35):       return GameState.IN_BATTLE
        if f(screenshot, "end_battle_button", 0.80): return GameState.IN_BATTLE
        if f(screenshot, "timer_top_start", 0.75):   return GameState.IN_BATTLE
        
        if f(screenshot, "bb_battle_hud", 0.70):     return GameState.BB_BATTLE
        
        h, w = screenshot.shape[:2]
        top_roi = screenshot[0:int(h * 0.25), int(w * 0.25):int(w * 0.75)]
        cached_prep = self._get_cached_template("bb_prep_text")
        cached_act = self._get_cached_template("bb_active_text")
        
        if cached_prep and self._match_ui(top_roi, cached_prep[0], 0.70):
            return GameState.BB_BATTLE
        if cached_act and self._match_ui(top_roi, cached_act[0], 0.70):
            return GameState.BB_BATTLE
        
        # ── HOME VILLAGE STATE PRIORITY ────────────────────────────────
        # CONFIRMING is checked FIRST so the matchmaking dialog
        # (mode tabs + attack_button2 / confirm_button) wins over the
        # lower-confidence IN_BATTLE heuristics — those buttons share
        # the bottom-left red-button look with end_battle_button.
        confirmations = self.scan_for_confirmations(screenshot)
        if confirmations: return GameState.CONFIRMING

        if f(screenshot, "return_home"):             return GameState.BATTLE_ENDED
        if f(screenshot, "searching_indicator"): return GameState.SEARCHING
        if f(screenshot, "attack_button"):      return GameState.HOME

        return GameState.UNKNOWN

    def clear_cache(self) -> None:
        self._template_cache.clear()