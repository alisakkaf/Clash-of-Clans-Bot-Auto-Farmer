"""
ObstacleDetectorSkill — pre-touch validation. Returns False when the
candidate (x, y) lands on a non-grass pixel cluster (rock, tree, wall,
decoration). CoC silently ignores deploy taps that hit obstacles, so we
must shift the touch BEFORE issuing it.

Approach (theme-resilient — does NOT depend on grass color):
    1. Crop a small ROI around (x, y).
    2. Compute per-channel std of the ROI. Plain grass / sand / snow has
       low texture variance (< threshold). Obstacles introduce
       high-frequency texture and shadow → std spikes.
    3. (Optional) match against a small library of obstacle templates;
       a hit at >0.70 confidence vetoes the touch.

If the point fails, `find_nearest_deployable` searches a spiral of
±20 px steps for a valid alternative, up to N attempts.
"""

from __future__ import annotations

import os
from typing import List, Optional

import cv2
import numpy as np

from core.logger import BotLogger
from vision.template_manager import (
    get_template_path,
    template_exists,
)

log = BotLogger.get("v2.obstacle")


class ObstacleDetectorSkill:
    name = "obstacle_detector"

    def __init__(self) -> None:
        self._template_cache: dict[str, np.ndarray] = {}

    def is_deployable(
        self,
        screenshot: np.ndarray,
        x: int,
        y: int,
        config: dict | None = None,
    ) -> bool:
        cfg = config or {}
        radius = int(cfg.get("obstacle_search_radius_px", 15))
        std_thr = float(cfg.get("obstacle_color_std_threshold", 30))

        h, w = screenshot.shape[:2]
        if x < 0 or y < 0 or x >= w or y >= h:
            return False

        x1 = max(0, x - radius)
        y1 = max(0, y - radius)
        x2 = min(w, x + radius)
        y2 = min(h, y + radius)
        roi = screenshot[y1:y2, x1:x2]
        if roi.size == 0:
            return False

        std = roi.reshape(-1, roi.shape[-1]).std(axis=0)
        if float(std.mean()) > std_thr:
            return False

        for tmpl_key in cfg.get("obstacle_templates", []) or []:
            if self._roi_matches_template(roi, tmpl_key, threshold=0.70):
                return False

        return True

    def find_nearest_deployable(
        self,
        screenshot: np.ndarray,
        x: int,
        y: int,
        config: dict | None = None,
        max_attempts: int = 8,
        step_px: int = 20,
    ) -> Optional[tuple[int, int]]:
        if self.is_deployable(screenshot, x, y, config):
            return (x, y)
        offsets: List[tuple[int, int]] = []
        for k in range(1, max_attempts + 1):
            offsets.extend([
                (0,  k * step_px),
                (0, -k * step_px),
                ( k * step_px, 0),
                (-k * step_px, 0),
            ])
        for dx, dy in offsets:
            nx, ny = x + dx, y + dy
            if self.is_deployable(screenshot, nx, ny, config):
                return (nx, ny)
        return None

    def _roi_matches_template(
        self, roi: np.ndarray, template_key: str, threshold: float,
    ) -> bool:
        tmpl = self._load_template(template_key)
        if tmpl is None:
            return False
        if roi.shape[0] < tmpl.shape[0] or roi.shape[1] < tmpl.shape[1]:
            return False
        gray_r = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray_t = cv2.cvtColor(tmpl, cv2.COLOR_BGR2GRAY)
        try:
            res = cv2.matchTemplate(gray_r, gray_t, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            return float(max_val) >= float(threshold)
        except cv2.error:
            return False

    def _load_template(self, key: str) -> np.ndarray | None:
        if key in self._template_cache:
            return self._template_cache[key]
        if not template_exists(key):
            return None
        path = get_template_path(key)
        if not path or not os.path.isfile(path):
            return None
        img = cv2.imread(path, cv2.IMREAD_COLOR)
        if img is None:
            return None
        self._template_cache[key] = img
        return img
