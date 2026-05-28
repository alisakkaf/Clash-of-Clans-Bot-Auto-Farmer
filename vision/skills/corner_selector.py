"""
CornerSelectorSkill — scores the four screen-edge corridors and picks
the best one for the current attack situation.

Scoring inputs:
    • Corridor area (more space ⇒ better funnel / fan).
    • Distance to target (closer ⇒ shorter army travel).
    • Defense density along the army path (fewer ⇒ better).
    • Wall segments crossed (fewer ⇒ better).
    • Diagonal bonus (corner attacks sweep more area).

Two convenience methods:
    pick_for_target(target_xy, troop_kind) — generic
    pick_for_air()                         — air-defense-aware
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

from core.logger import BotLogger
from vision.skills.safe_corridor import SafeCorridorSkill, Rect
from vision.skills.target_locator import TargetLocatorSkill

log = BotLogger.get("v2.corner_selector")

AIR_DEFENSE_ASSETS = ["air_defense", "air_sweeper", "archer_tower"]
GROUND_DEFENSE_ASSETS = [
    "cannon", "mortar", "wizard_tower", "x_bow",
    "inferno_tower", "scattershot", "eagle_artillery",
]


class CornerSelectorSkill:
    name = "corner_selector"

    def __init__(self, target_locator: TargetLocatorSkill) -> None:
        self._tl = target_locator

    def pick_for_target(
        self,
        screenshot: np.ndarray,
        corridors: Dict[str, Rect],
        target_xy: tuple[int, int],
        troop_kind: str,
        config: dict | None = None,
    ) -> str | None:
        if not corridors:
            return None
        defense_locs = self._defense_locations(screenshot, troop_kind)
        scores = {
            side: self._score(rect, target_xy, defense_locs, troop_kind)
            for side, rect in corridors.items()
        }
        best = max(scores, key=scores.get)
        log.info(
            "Corner scores: %s → pick=%s",
            {k: round(v, 2) for k, v in scores.items()}, best,
        )
        return best

    def pick_for_air(
        self,
        screenshot: np.ndarray,
        corridors: Dict[str, Rect],
        config: dict | None = None,
    ) -> str | None:
        if not corridors:
            return None
        air_defs = self._tl.find_all_by_prefix(screenshot, AIR_DEFENSE_ASSETS)
        scores: dict[str, float] = {}
        for side, rect in corridors.items():
            cx, cy = SafeCorridorSkill.center(rect)
            count = sum(
                1 for (_, dx, dy) in air_defs
                if self._point_in_path(rect, (cx, cy), (dx, dy))
            )
            area_score = (rect[2] * rect[3]) / 100000.0
            scores[side] = area_score * (1.0 / (1.0 + count))
        if not scores:
            return SafeCorridorSkill.widest(corridors)
        best = max(scores, key=scores.get)
        log.info(
            "Air corner scores (lower defenses=better): %s → pick=%s",
            {k: round(v, 2) for k, v in scores.items()}, best,
        )
        return best

    def _defense_locations(
        self, screenshot: np.ndarray, troop_kind: str,
    ) -> List[Tuple[int, int]]:
        if troop_kind == "air":
            assets = AIR_DEFENSE_ASSETS
        else:
            assets = GROUND_DEFENSE_ASSETS
        return [(x, y) for (_, x, y) in self._tl.find_all_by_prefix(screenshot, assets)]

    def _score(
        self,
        rect: Rect,
        target_xy: tuple[int, int],
        defenses: List[Tuple[int, int]],
        troop_kind: str,
    ) -> float:
        cx, cy = SafeCorridorSkill.center(rect)
        tx, ty = target_xy
        dist = max(50.0, ((cx - tx) ** 2 + (cy - ty) ** 2) ** 0.5)
        area = rect[2] * rect[3]
        defenses_in_path = sum(
            1 for (dx, dy) in defenses
            if self._point_in_path(rect, (cx, cy), (dx, dy))
        )
        diagonal_bonus = 1.10 if (cx < tx and cy < ty) or (cx > tx and cy > ty) else 1.0
        return (area / dist) * (1.0 / (1.0 + defenses_in_path)) * diagonal_bonus

    @staticmethod
    def _point_in_path(
        rect: Rect, start: tuple[int, int], target: tuple[int, int],
    ) -> bool:
        sx, sy = start
        tx, ty = target
        x_lo, x_hi = min(sx, tx), max(sx, tx)
        y_lo, y_hi = min(sy, ty), max(sy, ty)
        rx, ry, rw, rh = rect
        return not (
            x_hi < rx or x_lo > rx + rw or y_hi < ry or y_lo > ry + rh
        )
