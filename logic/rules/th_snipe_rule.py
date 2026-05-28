"""
THSnipeRule — drop the army on the closest safe corridor to the
configured target building (typically town_hall_*). Designed for the
"building" mode of the V2 panel.
"""

from __future__ import annotations

from logic.rules.air_attack_rule import AirAttackRule
from logic.rules.base_rule import AttackContext
from vision.skills.safe_corridor import SafeCorridorSkill


class THSnipeRule(AirAttackRule):
    name = "th_snipe"
    priority = 20

    def matches(self, profile: dict, screenshot) -> bool:
        return True

    def execute(self, ctx: AttackContext) -> bool:
        cfg = ctx.config
        ss = ctx.screenshot
        skills = ctx.skills

        if not ctx.target_key:
            return False

        candidates = skills.target.expand_prefix(ctx.target_key) or [ctx.target_key]
        hit = skills.target.find_first_of(ss, candidates)
        if hit is None:
            return False
        _, tx, ty = hit
        target_xy = (tx, ty)

        corridors = skills.corridor.map(ss, ctx.polygon, ctx.ui_cutoff, cfg)
        if not corridors:
            return False

        side = skills.corner.pick_for_target(
            ss, corridors, target_xy, "ground", cfg,
        ) or SafeCorridorSkill.closest(corridors, target_xy)
        rect = corridors[side]
        cluster = SafeCorridorSkill.closest_point_in(rect, target_xy)
        ok = skills.obstacle.find_nearest_deployable(ss, cluster[0], cluster[1], cfg)
        if ok is not None:
            cluster = ok

        for troop in self._selected_troops(ctx):
            if self._interrupted(ctx):
                self._stamp_engine_post_deploy(ctx, [])
                return True
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
