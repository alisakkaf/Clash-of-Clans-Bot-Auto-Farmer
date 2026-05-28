"""
SafeCorridorSkill — produces axis-aligned rectangles that lie OUTSIDE
the red-zone polygon, clear of HUD strips, suitable for placing deploy
points without ever touching no-deploy tiles.

Returns four named corridors: left / right / top / bottom. Corridors
narrower than `min_corridor_width_px` are dropped (they cannot fit a
fan or a funnel pair).

Each corridor is (x, y, w, h) in screen pixels.
"""

from __future__ import annotations

from typing import Dict, Tuple

import numpy as np

from core.logger import BotLogger
from vision.skills.red_zone_polygon import RedZonePolygonSkill

log = BotLogger.get("v2.safe_corridor")

Rect = Tuple[int, int, int, int]


class SafeCorridorSkill:
    name = "safe_corridor"

    def map(
        self,
        screenshot: np.ndarray,
        polygon: np.ndarray | None,
        ui_cutoff: int,
        config: dict | None = None,
    ) -> Dict[str, Rect]:
        cfg = config or {}
        stand_off = int(cfg.get("stand_off_px", 80))
        min_w = int(cfg.get("min_corridor_width_px", 60))
        h, w = screenshot.shape[:2]
        ui_cutoff = max(1, min(ui_cutoff, h))

        y_top_min = max(60, 110)
        y_bot_max = max(120, ui_cutoff - 80)
        x_lo = 60
        x_hi = w - 60

        if polygon is None or len(polygon) < 3:
            cx = (x_hi + x_lo) // 2
            cy = (y_bot_max + y_top_min) // 2
            half_w = (x_hi - x_lo) // 4
            half_h = (y_bot_max - y_top_min) // 4
            return {
                "left":   (x_lo, y_top_min, half_w, y_bot_max - y_top_min),
                "right":  (x_hi - half_w, y_top_min, half_w, y_bot_max - y_top_min),
                "top":    (x_lo, y_top_min, x_hi - x_lo, half_h),
                "bottom": (x_lo, y_bot_max - half_h, x_hi - x_lo, half_h),
            }

        x_min, y_min = polygon.min(axis=0)
        x_max, y_max = polygon.max(axis=0)
        rx, ry, rw, rh = int(x_min), int(y_min), int(x_max - x_min), int(y_max - y_min)

        corridors: Dict[str, Rect] = {}

        left_w = rx - stand_off - x_lo
        if left_w >= min_w:
            corridors["left"] = (x_lo, y_top_min, left_w, y_bot_max - y_top_min)

        right_x = rx + rw + stand_off
        right_w = x_hi - right_x
        if right_w >= min_w:
            corridors["right"] = (right_x, y_top_min, right_w, y_bot_max - y_top_min)

        top_h = ry - stand_off - y_top_min
        if top_h >= min_w:
            corridors["top"] = (x_lo, y_top_min, x_hi - x_lo, top_h)

        bot_y = ry + rh + stand_off
        bot_h = y_bot_max - bot_y
        if bot_h >= min_w:
            corridors["bottom"] = (x_lo, bot_y, x_hi - x_lo, bot_h)

        log.debug("Corridors: %s", {k: v for k, v in corridors.items()})
        return corridors

    @staticmethod
    def widest(corridors: Dict[str, Rect]) -> str | None:
        if not corridors:
            return None

        def area(r: Rect) -> int:
            return r[2] * r[3]

        return max(corridors.keys(), key=lambda k: area(corridors[k]))

    @staticmethod
    def closest(
        corridors: Dict[str, Rect], target_xy: tuple[int, int],
    ) -> str | None:
        if not corridors:
            return None
        tx, ty = target_xy

        def dist_sq(r: Rect) -> float:
            x, y, w, h = r
            cx = max(x, min(tx, x + w))
            cy = max(y, min(ty, y + h))
            return (cx - tx) ** 2 + (cy - ty) ** 2

        return min(corridors.keys(), key=lambda k: dist_sq(corridors[k]))

    @staticmethod
    def closest_point_in(rect: Rect, target_xy: tuple[int, int]) -> tuple[int, int]:
        x, y, w, h = rect
        tx, ty = target_xy
        return int(max(x, min(tx, x + w))), int(max(y, min(ty, y + h)))

    @staticmethod
    def center(rect: Rect) -> tuple[int, int]:
        x, y, w, h = rect
        return int(x + w / 2), int(y + h / 2)

    @staticmethod
    def is_horizontal(rect: Rect) -> bool:
        return rect[2] >= rect[3]
