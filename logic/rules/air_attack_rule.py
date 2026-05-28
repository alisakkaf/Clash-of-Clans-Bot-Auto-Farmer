"""
AirAttackRule — fan-deploy air troops along the corridor with the
fewest air defenses. Drops the tank (lava_hound) first when present,
then the DPS air troops in stagger waves, then heroes, then spells.

Trigger: any selected troop has profile.kind == "air".
"""

from __future__ import annotations

import time

from core.adb_handler import screencap
from core.logger import BotLogger
from logic.rules.base_rule import AttackContext, AttackRule
from vision.skills.safe_corridor import SafeCorridorSkill

log = BotLogger.get("v2.rule.air_attack")


class AirAttackRule(AttackRule):
    name = "air_attack"
    priority = 30

    def matches(self, profile: dict, screenshot) -> bool:
        return True

    def execute(self, ctx: AttackContext) -> bool:
        cfg = ctx.config
        troop_profiles = ctx.troop_profiles
        ss = ctx.screenshot
        skills = ctx.skills

        corridors = skills.corridor.map(ss, ctx.polygon, ctx.ui_cutoff, cfg)
        if not corridors:
            return False

        side = skills.corner.pick_for_air(ss, corridors, cfg) \
            or SafeCorridorSkill.widest(corridors)
        rect = corridors[side]
        fan_points = skills.fan.plan(rect, count=9)

        validated: list[tuple[int, int]] = []
        for (px, py) in fan_points:
            ok = skills.obstacle.find_nearest_deployable(ss, px, py, cfg)
            if ok is not None:
                validated.append(ok)
        if not validated:
            validated = fan_points

        cluster = validated[len(validated) // 2]
        target = ctx.base_centroid or SafeCorridorSkill.center(rect)

        air_troops = [
            t for t in self._selected_troops(ctx)
            if self._troop_kind(t, ctx) == "air"
        ]
        air_troops.sort(
            key=lambda t: (
                0 if troop_profiles.get(t, {}).get("drop_first") else 1,
                t,
            )
        )

        hero_memory = self._deploy_air_troops(ctx, air_troops, validated, cluster)
        if self._interrupted(ctx):
            self._stamp_engine_post_deploy(ctx, hero_memory)
            return True

        hero_memory = self._deploy_heroes(ctx, cluster, hero_memory)
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

        self._deploy_spells(ctx, cluster, target)
        self._stamp_engine_post_deploy(ctx, hero_memory)
        return True

    def _deploy_air_troops(
        self,
        ctx: AttackContext,
        air_troops: list[str],
        fan_points: list[tuple[int, int]],
        cluster: tuple[int, int],
    ) -> list:
        skills = ctx.skills
        cfg = ctx.config
        ss = ctx.screenshot
        for troop in air_troops:
            if self._interrupted(ctx):
                break
            card = skills.target.find_one(ss, troop)
            if card is None:
                continue
            skills.touch.tap(card[0], card[1], cfg)
            skills.touch.pre_select_settle(cfg)
            style = ctx.troop_profiles.get(troop, {}).get("style", "fan")
            if style == "stack":
                skills.touch.long_press(cluster[0], cluster[1], None, cfg)
            else:
                stagger_ms = int(ctx.troop_profiles.get(troop, {}).get("stagger_ms", 220))
                for (px, py) in fan_points:
                    if self._interrupted(ctx):
                        break
                    skills.touch.tap(px, py, cfg)
                    time.sleep(stagger_ms / 1000.0)
            skills.touch.post_deploy_settle(cfg)
        return []

    def _deploy_heroes(
        self,
        ctx: AttackContext,
        cluster: tuple[int, int],
        hero_memory: list,
    ) -> list:
        skills = ctx.skills
        cfg = ctx.config
        ss = ctx.screenshot
        heroes = self._selected_heroes(ctx)
        cards: list[tuple[str, int, int]] = []
        for hero in heroes:
            hit = skills.target.find_one(ss, hero)
            if hit is not None:
                cards.append((hero, hit[0], hit[1]))
        plans = skills.hero.plan_drops(cluster, cards)
        for (name, card_xy, drop_xy) in plans:
            if self._interrupted(ctx):
                break
            skills.touch.tap(card_xy[0], card_xy[1], cfg)
            skills.touch.pre_select_settle(cfg)
            skills.touch.tap(drop_xy[0], drop_xy[1], cfg)
            skills.touch.post_deploy_settle(cfg)
            hero_memory.append((name, card_xy, drop_xy))
        return hero_memory

    def _wait_for_engagement(self, ctx: AttackContext) -> None:
        delay = ctx.skills.hero.ability_delay_seconds(ctx.config)
        end = time.time() + max(0.0, delay)
        while time.time() < end:
            if self._interrupted(ctx):
                return
            time.sleep(0.25)

    def _fire_hero_abilities(self, ctx: AttackContext, hero_memory: list) -> None:
        skills = ctx.skills
        cfg = ctx.config
        gap_ms = skills.hero.ability_double_tap_gap_ms(cfg)
        for (_name, card_xy, _drop_xy) in hero_memory:
            if self._interrupted(ctx):
                return
            skills.touch.double_tap(card_xy[0], card_xy[1], gap_ms=gap_ms, config=cfg)

    def _deploy_spells(
        self,
        ctx: AttackContext,
        cluster: tuple[int, int],
        target: tuple[int, int],
    ) -> None:
        """Drop EVERY selected spell in a single tight burst, smartly
        ahead of the army's launch line.

        Robustness rules:
            • Refresh the screenshot first — the spell bar's page may
              have changed after the troop dump.
            • Use prefix expansion (`rage_spell` matches `rage_spell_5`)
              so card lookup never fails on level-suffixed templates.
            • Spells without a profile in v2_spell_profiles.json get a
              sensible "ahead of army" default (60 % along cluster→target),
              rather than being silently skipped.
            • Inter-spell delay is the default tap-settle only — no extra
              pre/post settles between spells, so the whole sequence
              feels like one batch (the user requested دفعة واحدة).
        """
        skills = ctx.skills
        cfg = ctx.config

        selected = self._selected_spells(ctx)
        if not selected:
            return

        # Fresh screenshot — the spell bar may have moved page after the
        # troop dump, so reading from the stale ctx.screenshot can miss
        # cards that are actually visible right now.
        fresh = screencap()
        ss = fresh if fresh is not None else ctx.screenshot

        for spell in selected:
            if self._interrupted(ctx):
                return

            candidates = skills.target.expand_prefix(spell) or [spell]
            hit = skills.target.find_first_of(ss, candidates)
            if hit is None:
                log.info(
                    "Spell '%s': card not visible on the bar (tried %d variants) — skipped.",
                    spell, len(candidates),
                )
                continue
            _, card_x, card_y = hit

            drops = skills.spell.plan_spell(
                ss, spell, cluster, target, cfg, ctx.spell_profiles,
            ) or [self._default_spell_drop(cluster, target)]

            log.info("Spell '%s': %d drop(s) %s", spell, len(drops), drops)
            for (sx, sy) in drops:
                if self._interrupted(ctx):
                    return
                # Card-tap → tight 100 ms gap → drop-tap. No extra
                # settles between spells: the tap()'s built-in settle
                # already supplies a humanized 150–400 ms gap.
                skills.touch.tap(card_x, card_y, cfg)
                time.sleep(0.10)
                skills.touch.tap(sx, sy, cfg)

        # One final settle so the engine post-deploy stamp is clean.
        skills.touch.post_deploy_settle(cfg)

    @staticmethod
    def _default_spell_drop(
        cluster: tuple[int, int],
        target: tuple[int, int],
    ) -> tuple[int, int]:
        """In-front-of-army fallback when the planner returns nothing."""
        cx, cy = cluster
        tx, ty = target
        return (
            int(round(cx + (tx - cx) * 0.60)),
            int(round(cy + (ty - cy) * 0.60)),
        )
