"""
IsometricGridSkill — converts pixel coordinates to/from isometric tile
coordinates at the current zoom level.

CoC's playfield is a 45° isometric projection with a 2:1 aspect ratio:
    1 tile width  ≈ 32 px @ default zoom
    1 tile height ≈ 16 px @ default zoom

When the player pinches in/out, both scale linearly by the same factor.
We auto-calibrate the factor by measuring the red-zone polygon's width
against the canonical 40-tile playfield width (1 wall span ≈ 40 tiles
at default zoom = 1280 px).

Calling code uses this skill to:
    • Snap arbitrary pixel coords to the nearest tile center.
    • Compute distances in TILES not pixels (zoom-invariant logic).
    • Decide if two drop points are "next to each other" (1 tile apart).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from core.logger import BotLogger

log = BotLogger.get("v2.iso_grid")

CANONICAL_BASE_TILE_SPAN = 40
CANONICAL_TILE_W_PX = 32
CANONICAL_TILE_H_PX = 16


@dataclass(frozen=True)
class IsoCalibration:
    tile_w_px: float
    tile_h_px: float
    origin_x: float
    origin_y: float

    @property
    def zoom_factor(self) -> float:
        return self.tile_w_px / float(CANONICAL_TILE_W_PX)


class IsometricGridSkill:
    name = "isometric_grid"

    def calibrate(
        self,
        screenshot: np.ndarray,
        polygon: np.ndarray | None,
        config: dict | None = None,
    ) -> IsoCalibration:
        """Estimate tile_w / tile_h / origin from the red-zone polygon."""
        cfg = (config or {}).get("isometric", {}) if config else {}
        tile_w_default = float(cfg.get("tile_w_px_default", CANONICAL_TILE_W_PX))
        tile_h_default = float(cfg.get("tile_h_px_default", CANONICAL_TILE_H_PX))
        auto = bool(cfg.get("auto_calibrate", True))

        if not auto or polygon is None or len(polygon) < 3:
            h, w = screenshot.shape[:2]
            return IsoCalibration(
                tile_w_px=tile_w_default,
                tile_h_px=tile_h_default,
                origin_x=w / 2.0,
                origin_y=h / 2.0,
            )

        x_min, y_min = polygon.min(axis=0)
        x_max, y_max = polygon.max(axis=0)
        bw = max(1.0, float(x_max - x_min))
        bh = max(1.0, float(y_max - y_min))

        tile_w = bw / float(CANONICAL_BASE_TILE_SPAN)
        tile_h = bh / float(CANONICAL_BASE_TILE_SPAN / 2.0)
        tile_w = float(np.clip(tile_w, 14.0, 80.0))
        tile_h = float(np.clip(tile_h, 7.0, 40.0))
        origin_x = (x_min + x_max) / 2.0
        origin_y = (y_min + y_max) / 2.0
        return IsoCalibration(
            tile_w_px=tile_w,
            tile_h_px=tile_h,
            origin_x=origin_x,
            origin_y=origin_y,
        )

    @staticmethod
    def px_to_tile(
        px: int, py: int, calib: IsoCalibration,
    ) -> tuple[float, float]:
        """Pixel → tile-space (continuous, not rounded). Origin = base center."""
        dx = (px - calib.origin_x) / calib.tile_w_px
        dy = (py - calib.origin_y) / calib.tile_h_px
        tx = (dx + dy) / 2.0
        ty = (dy - dx) / 2.0
        return tx, ty

    @staticmethod
    def tile_to_px(
        tx: float, ty: float, calib: IsoCalibration,
    ) -> tuple[int, int]:
        """Tile-space → pixel. Inverse of px_to_tile."""
        dx = (tx - ty) * calib.tile_w_px
        dy = (tx + ty) * calib.tile_h_px
        return int(round(calib.origin_x + dx)), int(round(calib.origin_y + dy))

    @staticmethod
    def snap_to_tile_center(
        px: int, py: int, calib: IsoCalibration,
    ) -> tuple[int, int]:
        tx, ty = IsometricGridSkill.px_to_tile(px, py, calib)
        return IsometricGridSkill.tile_to_px(round(tx), round(ty), calib)

    @staticmethod
    def tile_distance(
        a_xy: tuple[int, int], b_xy: tuple[int, int], calib: IsoCalibration,
    ) -> float:
        ax, ay = IsometricGridSkill.px_to_tile(a_xy[0], a_xy[1], calib)
        bx, by = IsometricGridSkill.px_to_tile(b_xy[0], b_xy[1], calib)
        return math.hypot(ax - bx, ay - by)
