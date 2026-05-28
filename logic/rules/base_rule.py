"""
Base contracts for V2 attack rules.

A Rule is a strategy. The orchestrator picks ONE rule per attack and
runs its `execute` method. Rules access Skills through the
`AttackContext.skills` bundle and Config through `AttackContext.config`.

A rule MUST implement two methods:
    matches(profile, screenshot)  → bool
    execute(ctx)                  → bool

`execute` returns True if the rule actually carried out a deploy (or at
least started one), False if pre-conditions failed and the orchestrator
should chain to the next fallback (typically SmartDefault, then legacy
V36). Rules that early-return without deploying MUST return False so the
orchestrator can recover.

A rule SHOULD be deterministic: given the same screenshot and profile
it should produce the same drops (modulo human-touch jitter).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import numpy as np

from logic.skills.fan_planner import FanPlannerSkill
from logic.skills.funnel_planner import FunnelPlannerSkill
from logic.skills.hero_planner import HeroPlannerSkill
from logic.skills.human_touch import HumanTouchSkill
from logic.skills.spell_planner import SpellPlannerSkill
from vision.skills.corner_selector import CornerSelectorSkill
from vision.skills.isometric_grid import IsometricGridSkill
from vision.skills.obstacle_detector import ObstacleDetectorSkill
from vision.skills.red_zone_polygon import RedZonePolygonSkill
from vision.skills.safe_corridor import SafeCorridorSkill
from vision.skills.target_locator import TargetLocatorSkill


@dataclass
class SkillBundle:
    red_zone:   RedZonePolygonSkill
    iso_grid:   IsometricGridSkill
    corridor:   SafeCorridorSkill
    obstacle:   ObstacleDetectorSkill
    target:     TargetLocatorSkill
    corner:     CornerSelectorSkill
    touch:      HumanTouchSkill
    fan:        FanPlannerSkill
    funnel:     FunnelPlannerSkill
    spell:      SpellPlannerSkill
    hero:       HeroPlannerSkill


@dataclass
class AttackContext:
    screenshot:     np.ndarray
    profile:        dict
    config:         dict
    troop_profiles: dict
    spell_profiles: dict
    skills:         SkillBundle
    mode_key:       str
    target_key:     str
    ui_cutoff:      int
    engine:         Any | None = None
    polygon:        np.ndarray | None = None
    base_centroid:  tuple[int, int] | None = None


class AttackRule(ABC):
    """Abstract attack strategy."""

    name: str = "base_rule"
    priority: int = 100

    @abstractmethod
    def matches(self, profile: dict, screenshot: np.ndarray) -> bool: ...

    @abstractmethod
    def execute(self, ctx: AttackContext) -> bool: ...

    def _interrupted(self, ctx: AttackContext) -> bool:
        eng = ctx.engine
        if eng is None:
            return False
        return (not getattr(eng, "_running", False)) or getattr(eng, "_paused", False)

    @staticmethod
    def _selected_troops(ctx: AttackContext) -> list[str]:
        key = "bb_selected_troops" if ctx.mode_key == "bb" else "selected_troops"
        return list(ctx.profile.get(key, []) or [])

    @staticmethod
    def _selected_heroes(ctx: AttackContext) -> list[str]:
        key = "bb_selected_heroes" if ctx.mode_key == "bb" else "selected_heroes"
        return list(ctx.profile.get(key, []) or [])

    @staticmethod
    def _selected_spells(ctx: AttackContext) -> list[str]:
        key = "bb_selected_spells" if ctx.mode_key == "bb" else "selected_spells"
        return list(ctx.profile.get(key, []) or [])

    @staticmethod
    def _troop_kind(troop_name: str, ctx: AttackContext) -> str:
        prof = ctx.troop_profiles.get(troop_name, {}) if ctx.troop_profiles else {}
        return str(prof.get("kind", "ground"))

    @staticmethod
    def _has_kind(troop_names: list[str], kind: str, ctx: AttackContext) -> bool:
        return any(AttackRule._troop_kind(t, ctx) == kind for t in troop_names)

    @staticmethod
    def _stamp_engine_post_deploy(ctx: AttackContext, hero_memory: list) -> None:
        eng = ctx.engine
        if eng is None:
            return
        try:
            import time as _t
            eng._home_logic._post_deploy_time = _t.time()
            eng._home_logic._battle_phase_done = True
            eng._home_logic._hero_memory = [
                (name, card_xy[0], card_xy[1])
                for (name, card_xy, _drop_xy) in hero_memory
            ]
        except Exception:
            pass
