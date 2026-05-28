"""
ResourceRaidRule — goblin / sneak-archer style storage raids.

Sequence:
    1. Locate every visible storage matching the configured prefix
       (gold_storage_*, elixir_storage_*, dark_elixir_storage_*).
    2. Drop a small scout pair of the cheap fodder troop (goblin /
       barbarian) on the closest safe corridor next to EACH storage.
    3. After all storages have been scouted, dump the remaining army on
       the closest safe spot to the densest storage cluster.
    4. Heroes follow + spells along path as usual.
"""

from __future__ import annotations

import time

from core.logger import BotLogger
from logic.rules.air_attack_rule import AirAttackRule
from logic.rules.base_rule import AttackContext
from logic.rules.smart_default_rule import SmartDefaultRule
from vision.skills.safe_corridor import SafeCorridorSkill

log = BotLogger.get("v2.rule.resource_raid")


DEFAULT_STORAGE_PREFIXES = [
    "gold_storage", "elixir_storage", "dark_elixir_storage",
]


class ResourceRaidRule(AirAttackRule):
    name = "resource_raid"
    priority = 10

    def matches(self, profile: dict, screenshot) -> bool:
        return True

    def execute(self, ctx: AttackContext) -> bool:
        cfg = ctx.config
        ss = ctx.screenshot
        skills = ctx.skills

        prefixes = self._target_prefixes(ctx)
        targets = skills.target.find_all_by_prefix(ss, prefixes)
        if not targets:
            log.info("ResourceRaid: no storage targets found (prefixes=%s) — chaining to SmartDefault.", prefixes)
            return SmartDefaultRule().execute(ctx)

        corridors = skills.corridor.map(ss, ctx.polygon, ctx.ui_cutoff, cfg)
        if not corridors:
            log.info("ResourceRaid: no safe corridors — chaining to SmartDefault.")
            return SmartDefaultRule().execute(ctx)

        scout_troop = self._first_scout_troop(ctx)
        if not scout_troop:
            log.info("ResourceRaid: no scout-style troop available — chaining to SmartDefault.")
            return SmartDefaultRule().execute(ctx)

        self._scout_storages(ctx, targets, corridors, scout_troop)
        if self._interrupted(ctx):
            self._stamp_engine_post_deploy(ctx, [])
            return True

        primary = targets[0]
        primary_xy = (primary[1], primary[2])
        side = skills.corner.pick_for_target(
            ss, corridors, primary_xy, "ground", cfg,
        ) or SafeCorridorSkill.closest(corridors, primary_xy)
        rect = corridors[side]
        cluster = SafeCorridorSkill.closest_point_in(rect, primary_xy)
        ok = skills.obstacle.find_nearest_deployable(ss, cluster[0], cluster[1], cfg)
        if ok is not None:
            cluster = ok

        target_xy = ctx.base_centroid or primary_xy
        main_troops = [t for t in self._selected_troops(ctx) if t != scout_troop]

        for troop in main_troops:
            if self._interrupted(ctx):
                self._stamp_engine_post_deploy(ctx, [])
                return
            card = skills.target.find_one(ss, troop)
            if card is None:
                continue
            skills.touch.tap(card[0], card[1], cfg)
            skills.touch.pre_select_settle(cfg)
            skills.touch.long_press(cluster[0], cluster[1], None, cfg)
            skills.touch.post_deploy_settle(cfg)

        hero_memory = self._deploy_heroes(ctx, cluster, [])
        if self._interrupted(ctx):
            self._stamp_engine_post_deploy(ctx, hero_memory)
            return True
        self._wait_for_engagement(ctx)
        self._fire_hero_abilities(ctx, hero_memory)
        self._deploy_spells(ctx, cluster, target_xy)
        self._stamp_engine_post_deploy(ctx, hero_memory)
        return True

    def _scout_storages(
        self,
        ctx: AttackContext,
        targets: list,
        corridors: dict,
        scout_troop: str,
    ) -> None:
        skills = ctx.skills
        cfg = ctx.config
        ss = ctx.screenshot
        for (key, tx, ty) in targets:
            if self._interrupted(ctx):
                return
            side = SafeCorridorSkill.closest(corridors, (tx, ty))
            if side is None:
                continue
            rect = corridors[side]
            spot = SafeCorridorSkill.closest_point_in(rect, (tx, ty))
            ok = skills.obstacle.find_nearest_deployable(ss, spot[0], spot[1], cfg)
            if ok is not None:
                spot = ok
            card = skills.target.find_one(ss, scout_troop)
            if card is None:
                return
            pair_size = int(ctx.troop_profiles.get(scout_troop, {}).get("pair_size", 2))
            for _ in range(max(1, pair_size)):
                if self._interrupted(ctx):
                    return
                skills.touch.tap(card[0], card[1], cfg)
                skills.touch.pre_select_settle(cfg)
                skills.touch.tap(spot[0], spot[1], cfg)
                time.sleep(0.15)
            skills.touch.post_deploy_settle(cfg)

    def _target_prefixes(self, ctx: AttackContext) -> list[str]:
        if ctx.target_key:
            return [ctx.target_key]
        for troop in self._selected_troops(ctx):
            tp = ctx.troop_profiles.get(troop, {})
            if tp.get("style") == "scout_pairs":
                return list(tp.get("scout_targets", DEFAULT_STORAGE_PREFIXES))
        return list(DEFAULT_STORAGE_PREFIXES)

    def _first_scout_troop(self, ctx: AttackContext) -> str | None:
        for troop in self._selected_troops(ctx):
            tp = ctx.troop_profiles.get(troop, {})
            if tp.get("style") == "scout_pairs":
                return troop
        return None
