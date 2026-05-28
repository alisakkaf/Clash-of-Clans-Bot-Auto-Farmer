"""
FanPlannerSkill — produces an evenly-spaced line of drop points along
the long axis of a corridor. Used for air troops and unbuffered ground
swarms (archers, barbarians).

The fan is symmetric around the corridor center, leaves a small margin
at each end, and exposes the geometric center as the "cluster" anchor
for spells / heroes.
"""

from __future__ import annotations

from typing import List, Tuple

from core.logger import BotLogger
from vision.skills.safe_corridor import SafeCorridorSkill, Rect

log = BotLogger.get("v2.fan_planner")


class FanPlannerSkill:
    name = "fan_planner"

    def plan(
        self,
        corridor: Rect,
        count: int = 9,
        margin_pct: float = 0.10,
    ) -> List[Tuple[int, int]]:
        if corridor is None:
            return []
        x, y, w, h = corridor
        if count < 1:
            return []
        if count == 1:
            return [SafeCorridorSkill.center(corridor)]

        if SafeCorridorSkill.is_horizontal(corridor):
            mx = int(w * margin_pct)
            x_lo = x + mx
            x_hi = x + w - mx
            cy = int(y + h / 2)
            step = (x_hi - x_lo) / float(count - 1)
            return [(int(round(x_lo + step * i)), cy) for i in range(count)]
        else:
            my = int(h * margin_pct)
            y_lo = y + my
            y_hi = y + h - my
            cx = int(x + w / 2)
            step = (y_hi - y_lo) / float(count - 1)
            return [(cx, int(round(y_lo + step * i))) for i in range(count)]

    def cluster_anchor(self, corridor: Rect) -> Tuple[int, int]:
        return SafeCorridorSkill.center(corridor)
