"""
SmartDefaultRule — fallback when no other rule explicitly matches.

Strategy:
    • Pick the widest safe corridor.
    • Compute its center as the cluster.
    • Long-press dump every selected troop at that cluster (V36 pattern).
    • Deploy heroes, wait for engagement, fire abilities, drop spells
      along the path to the base centroid.
"""

from __future__ import annotations

from core.logger import BotLogger
from logic.rules.air_attack_rule import AirAttackRule
from logic.rules.base_rule import AttackContext
from vision.skills.safe_corridor import SafeCorridorSkill

log = BotLogger.get("v2.rule.smart_default")


class SmartDefaultRule(AirAttackRule):
    name = "smart_default"
    priority = 90

    def matches(self, profile: dict, screenshot) -> bool:
        return True

    def execute(self, ctx: AttackContext) -> bool:
        cfg = ctx.config
        ss = ctx.screenshot
        skills = ctx.skills

        corridors = skills.corridor.map(ss, ctx.polygon, ctx.ui_cutoff, cfg)
        if not corridors:
            log.info("SmartDefault: no corridors — caller should fall back to V36.")
            return False

        side = SafeCorridorSkill.widest(corridors)
        if side is None:
            log.info("SmartDefault: widest() returned None — caller should fall back to V36.")
            return False
        rect = corridors[side]

        # Corridor sanity — must be wide enough to fit a long-press dump
        # without spilling into the no-deploy zone or off-screen.
        min_w = int(cfg.get("min_corridor_width_px", 60))
        if rect[2] < min_w or rect[3] < min_w:
            log.info(
                "SmartDefault: corridor '%s' too small (%dx%d, min=%d) — V36 fallback.",
                side, rect[2], rect[3], min_w,
            )
            return False

        cluster = SafeCorridorSkill.center(rect)
        ok = skills.obstacle.find_nearest_deployable(ss, cluster[0], cluster[1], cfg)
        if ok is not None:
            cluster = ok

        # Cluster sanity — must be inside the playfield, away from screen
        # edges and below the top UI strip. If the cluster lands on the
        # HUD or hovers off-screen the long-press will hit a UI element
        # (loot/timer banner) and not deploy anything.
        h, w = ss.shape[:2]
        ui_cutoff = max(1, min(ctx.ui_cutoff, h))
        edge_margin = max(40, int(cfg.get("stand_off_px", 80)) // 2)
        top_excl = int((cfg.get("polygon") or {}).get("top_ui_exclude_px", 150))
        cx, cy = int(cluster[0]), int(cluster[1])
        if (
            cx < edge_margin
            or cx > w - edge_margin
            or cy < max(top_excl, edge_margin)
            or cy > ui_cutoff - edge_margin
        ):
            log.info(
                "SmartDefault: cluster (%d,%d) too close to edge / UI strip (margin=%d top_excl=%d) — V36 fallback.",
                cx, cy, edge_margin, top_excl,
            )
            return False

        target_xy = ctx.base_centroid or (ss.shape[1] // 2, ctx.ui_cutoff // 2)

        deployed_any = False
        for troop in self._selected_troops(ctx):
            if self._interrupted(ctx):
                self._stamp_engine_post_deploy(ctx, [])
                return deployed_any
            card = skills.target.find_one(ss, troop)
            if card is None:
                continue
            skills.touch.tap(card[0], card[1], cfg)
            skills.touch.pre_select_settle(cfg)
            skills.touch.long_press(cluster[0], cluster[1], None, cfg)
            skills.touch.post_deploy_settle(cfg)
            deployed_any = True

        # If we couldn't even find a single troop card, don't claim
        # success — V36 fallback is more useful than a silent no-op.
        if not deployed_any:
            log.info("SmartDefault: no troop cards matched — V36 fallback.")
            return False

        hero_memory = self._deploy_heroes(ctx, cluster, [])
        if self._interrupted(ctx):
            self._stamp_engine_post_deploy(ctx, hero_memory)
            return True
        self._wait_for_engagement(ctx)
        self._fire_hero_abilities(ctx, hero_memory)
        self._deploy_spells(ctx, cluster, target_xy)
        self._stamp_engine_post_deploy(ctx, hero_memory)
        return True
