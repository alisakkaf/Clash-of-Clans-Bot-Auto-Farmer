"""
GroundFunnelRule — funnel + main wave for ground armies.

Sequence:
    1. Drop 2 outer "funnel" troops (giant / golem) at corridor 20% / 80%.
    2. Wait `delay_between_funnels_sec` for them to engage perimeter.
    3. Drop the rest of the army (tanks, DPS, wall breakers) at the main
       cluster.
    4. Drop heroes behind the wave.
    5. Wait for engagement, fire abilities, drop spells along the path.
"""

from __future__ import annotations

import time

from logic.rules.air_attack_rule import AirAttackRule
from logic.rules.base_rule import AttackContext
from vision.skills.safe_corridor import SafeCorridorSkill


class GroundFunnelRule(AirAttackRule):
    name = "ground_funnel"
    priority = 40

    def matches(self, profile: dict, screenshot) -> bool:
        return True

    def execute(self, ctx: AttackContext) -> bool:
        cfg = ctx.config
        ss = ctx.screenshot
        skills = ctx.skills

        corridors = skills.corridor.map(ss, ctx.polygon, ctx.ui_cutoff, cfg)
        if not corridors:
            return False

        ground_troops = [
            t for t in self._selected_troops(ctx)
            if self._troop_kind(t, ctx) == "ground"
        ]

        target_xy = ctx.base_centroid
        if target_xy is None:
            target_xy = (ss.shape[1] // 2, ctx.ui_cutoff // 2)

        side = skills.corner.pick_for_target(
            ss, corridors, target_xy, "ground", cfg,
        ) or SafeCorridorSkill.widest(corridors)
        rect = corridors[side]
        funnel = skills.funnel.plan(rect, target_xy, cfg)
        cluster = funnel.get("main") or SafeCorridorSkill.center(rect)
        ok = skills.obstacle.find_nearest_deployable(ss, cluster[0], cluster[1], cfg)
        if ok is not None:
            cluster = ok

        funnel_pair = (funnel.get("funnel_left"), funnel.get("funnel_right"))
        funnel_pair_validated = []
        for pt in funnel_pair:
            if pt is None:
                continue
            v = skills.obstacle.find_nearest_deployable(ss, pt[0], pt[1], cfg)
            funnel_pair_validated.append(v if v is not None else pt)

        funnel_troops = [
            t for t in ground_troops
            if ctx.troop_profiles.get(t, {}).get("style") == "funnel"
        ][:2]
        main_troops = [
            t for t in ground_troops
            if t not in funnel_troops
        ]

        self._deploy_funnels(ctx, funnel_troops, funnel_pair_validated)
        if self._interrupted(ctx):
            self._stamp_engine_post_deploy(ctx, [])
            return True

        delay = float((cfg.get("funnel") or {}).get("delay_before_main_wave_sec", 2.0))
        end = time.time() + max(0.0, delay)
        while time.time() < end:
            if self._interrupted(ctx):
                self._stamp_engine_post_deploy(ctx, [])
                return True
            time.sleep(0.20)

        self._deploy_main_wave(ctx, main_troops, cluster)
        if self._interrupted(ctx):
            self._stamp_engine_post_deploy(ctx, [])
            return True

        hero_memory = self._deploy_heroes(ctx, cluster, [])
        if self._interrupted(ctx):
            self._stamp_engine_post_deploy(ctx, hero_memory)
            return True
        self._wait_for_engagement(ctx)
        if self._interrupted(ctx):
            self._stamp_engine_post_deploy(ctx, hero_memory)
            return True
        self._fire_hero_abilities(ctx, hero_memory)
        if self._interrupted(ctx):
            self._stamp_engine_post_deploy(ctx, hero_memory)
            return True
        self._deploy_spells(ctx, cluster, target_xy)
        self._stamp_engine_post_deploy(ctx, hero_memory)
        return True

    def _deploy_funnels(
        self,
        ctx: AttackContext,
        funnel_troops: list[str],
        funnel_points: list[tuple[int, int]],
    ) -> None:
        skills = ctx.skills
        cfg = ctx.config
        ss = ctx.screenshot
        if not funnel_troops or not funnel_points:
            return
        delay_between = float((cfg.get("funnel") or {}).get("delay_between_funnels_sec", 1.5))
        for i, troop in enumerate(funnel_troops):
            if self._interrupted(ctx):
                return
            card = skills.target.find_one(ss, troop)
            if card is None:
                continue
            point = funnel_points[i % len(funnel_points)]
            skills.touch.tap(card[0], card[1], cfg)
            skills.touch.pre_select_settle(cfg)
            skills.touch.tap(point[0], point[1], cfg)
            skills.touch.post_deploy_settle(cfg)
            time.sleep(delay_between)

    def _deploy_main_wave(
        self,
        ctx: AttackContext,
        main_troops: list[str],
        cluster: tuple[int, int],
    ) -> None:
        skills = ctx.skills
        cfg = ctx.config
        ss = ctx.screenshot
        for troop in main_troops:
            if self._interrupted(ctx):
                return
            card = skills.target.find_one(ss, troop)
            if card is None:
                continue
            skills.touch.tap(card[0], card[1], cfg)
            skills.touch.pre_select_settle(cfg)
            style = ctx.troop_profiles.get(troop, {}).get("style", "fan")
            if style in ("behind_tank", "stack"):
                skills.touch.long_press(cluster[0], cluster[1], None, cfg)
            else:
                stagger_ms = int(ctx.troop_profiles.get(troop, {}).get("stagger_ms", 90))
                for _ in range(8):
                    if self._interrupted(ctx):
                        return
                    skills.touch.tap(cluster[0], cluster[1], cfg)
                    time.sleep(stagger_ms / 1000.0)
            skills.touch.post_deploy_settle(cfg)
