"""
FunnelPlannerSkill — plans 2-prong (or 1-prong) ground funnel drops.

A funnel is two outer drop points placed at roughly 20% and 80% of the
corridor's long axis, used to draw the perimeter defenses' aggro before
the main wave. Without a funnel, ground troops "edge" around the base
and miss the core.

Returns:
    {
        "funnel_left":  (x, y),   # outer #1
        "funnel_right": (x, y),   # outer #2
        "main":         (x, y),   # main wave cluster
    }
The keys "funnel_left/right" are also used for top/bottom corridors —
they refer to the two extremes of the corridor's long axis, not a
literal compass direction.
"""

from __future__ import annotations

from typing import Dict, Tuple

from core.logger import BotLogger
from vision.skills.safe_corridor import SafeCorridorSkill, Rect

log = BotLogger.get("v2.funnel_planner")


class FunnelPlannerSkill:
    name = "funnel_planner"

    def plan(
        self,
        corridor: Rect,
        target_xy: tuple[int, int] | None = None,
        config: dict | None = None,
    ) -> Dict[str, Tuple[int, int]]:
        if corridor is None:
            return {}
        cfg = (config or {}).get("funnel", {}) if config else {}
        outer_pcts = cfg.get("outer_drop_pct", [0.20, 0.80])
        main_pct = float(cfg.get("main_drop_pct", 0.50))

        x, y, w, h = corridor
        horiz = SafeCorridorSkill.is_horizontal(corridor)

        if horiz:
            cy = int(y + h / 2)
            o1 = (int(x + w * float(outer_pcts[0])), cy)
            o2 = (int(x + w * float(outer_pcts[1])), cy)
            main = (int(x + w * main_pct), cy)
        else:
            cx = int(x + w / 2)
            o1 = (cx, int(y + h * float(outer_pcts[0])))
            o2 = (cx, int(y + h * float(outer_pcts[1])))
            main = (cx, int(y + h * main_pct))

        if target_xy is not None:
            main = SafeCorridorSkill.closest_point_in(corridor, target_xy)

        return {"funnel_left": o1, "funnel_right": o2, "main": main}

    @staticmethod
    def main_cluster(plan: Dict[str, Tuple[int, int]]) -> Tuple[int, int] | None:
        return plan.get("main")

    @staticmethod
    def outer_pair(plan: Dict[str, Tuple[int, int]]) -> Tuple[Tuple[int, int], Tuple[int, int]] | None:
        a, b = plan.get("funnel_left"), plan.get("funnel_right")
        if a is None or b is None:
            return None
        return a, b
