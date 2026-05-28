"""
HeroPlannerSkill — decides where heroes drop and when their abilities
fire.

Drop policy:
    • Heroes drop AFTER the first wave (tanks) has engaged.
    • Drop point is just behind the main army cluster (toward the deploy
      corridor center, not the base center) so they tank for the wave.
    • Each hero drops with ±15 px jitter to avoid stack-of-one.

Ability policy:
    • A hero's ability button is the SAME card slot the hero was selected
      from. After the configured engagement delay we DOUBLE-TAP that slot
      to trigger the ability.
"""

from __future__ import annotations

import random
from typing import List, Tuple

from core.logger import BotLogger

log = BotLogger.get("v2.hero_planner")

HeroEntry = Tuple[str, Tuple[int, int], Tuple[int, int]]


class HeroPlannerSkill:
    name = "hero_planner"

    def plan_drops(
        self,
        cluster_xy: tuple[int, int],
        hero_card_locations: List[Tuple[str, int, int]],
    ) -> List[HeroEntry]:
        cx, cy = cluster_xy
        out: List[HeroEntry] = []
        for name, hx, hy in hero_card_locations:
            drop_x = cx + random.randint(-18, 18)
            drop_y = cy + random.randint(-18, 18)
            out.append((name, (hx, hy), (drop_x, drop_y)))
        return out

    @staticmethod
    def ability_delay_seconds(config: dict | None) -> float:
        if not config:
            return 4.0
        return float(((config.get("hero_ability") or {}).get("trigger_after_engagement_sec", 4.0)))

    @staticmethod
    def ability_double_tap_gap_ms(config: dict | None) -> int:
        if not config:
            return 120
        return int(((config.get("hero_ability") or {}).get("double_tap_gap_ms", 120)))
