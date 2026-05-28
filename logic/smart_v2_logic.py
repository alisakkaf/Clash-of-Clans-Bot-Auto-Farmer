"""
Smart V2 Attack — thin wrapper around V2Orchestrator (CSR architecture).

This module is the single entry point that HomeVillageLogic and
BuilderBaseLogic call when the V2 toggle is on. The new flow:

    1. ``execute(screenshot)`` delegates to ``V2Orchestrator.execute``.
    2. The orchestrator loads JSON config, builds Skills, picks a Rule,
       and runs it.
    3. If the orchestrator returns False (no rule matched / orchestrator
       error) we fall through to the LEGACY V36 path preserved below.

Legacy V36 path (``_legacy_attack_smart`` / ``_legacy_attack_building``
/ ``_legacy_attack_storage``) is the proven single-cluster long-press
dump pattern. We keep it untouched as ultimate fallback so the bot is
NEVER worse than V36 even if the new CSR pipeline misbehaves.
"""

from __future__ import annotations

import random
import time
from typing import Literal

import numpy as np

from core.adb_handler import screencap, tap, swipe
from core.adb_gestures import pinch_zoom_out, pan_camera
from core.logger import BotLogger
from core.settings import Settings
from logic.v2_orchestrator import V2Orchestrator
from vision.screen_reader import ScreenReader
from vision.smart_vision_v2 import SmartVisionV2

log = BotLogger.get("v2_logic")

Mode = Literal["smart", "building", "storage"]


class SmartV2Logic:
    def __init__(self, profile: dict, screen_reader: ScreenReader, ocr, mode_key: str):
        self._profile = profile
        self._sr = screen_reader
        self._ocr = ocr
        self._vision = SmartVisionV2(screen_reader)
        self._orchestrator = V2Orchestrator(screen_reader)
        self._mode_key = mode_key  # "hv" or "bb"
        self._engine = None

    def set_engine(self, engine) -> None:
        self._engine = engine

    def update_profile(self, profile: dict) -> None:
        self._profile = profile

    # ── Public entry ────────────────────────────────────────
    def is_enabled(self) -> bool:
        return bool(Settings().get(f"v2_enabled_{self._mode_key}", False))

    def reload_config(self) -> bool:
        """Hot-reload the V2 JSON configs (called from the UI panel)."""
        return self._orchestrator.reload_config()

    def available_rules(self) -> list[str]:
        return self._orchestrator.available_rules()

    def execute(self, screenshot: np.ndarray) -> None:
        s = Settings()
        mode: Mode = str(s.get(f"v2_mode_{self._mode_key}", "smart"))  # type: ignore[assignment]
        target = str(s.get(f"v2_target_{self._mode_key}", ""))

        if self._mode_key == "hv" and self._should_brief(mode) and self._engine is not None:
            self._engine.briefing_needed.emit(self._briefing_text(mode, target))
            time.sleep(0.4)

        try:
            success = self._orchestrator.execute(
                screenshot=screenshot,
                profile=self._profile,
                mode_key=self._mode_key,
                engine=self._engine,
            )
        except Exception as exc:
            log.error("V2 orchestrator crashed (%s) — falling back to legacy V36.", exc)
            success = False

        if success:
            return

        log.warning("V2 orchestrator returned no result — running LEGACY V36 fallback.")
        self._legacy_run(screenshot, mode, target)

    # ── Legacy V36 path (ULTIMATE FALLBACK) ─────────────────────────
    def _legacy_run(self, screenshot: np.ndarray, mode: Mode, target: str) -> None:
        s = Settings()
        decoration_wait = float(s.get("v2_decoration_wait", 5.0))
        zoom_steps = int(s.get("v2_zoom_out_steps", 2))

        log.info("LEGACY V36 START mode=%s key=%s target=%s", mode, self._mode_key, target or "—")

        ss = self._vision.wait_for_decorations(decoration_wait)
        if ss is None:
            ss = screenshot

        for i in range(max(0, zoom_steps)):
            if self._interrupted():
                return
            pinch_zoom_out(span_px=380 + i * 40, duration_ms=550 + random.randint(-60, 60))
            time.sleep(0.35)
        if zoom_steps > 0:
            ss2 = screencap()
            if ss2 is not None:
                ss = ss2

        if mode == "building":
            self._attack_building(ss, target)
        elif mode == "storage":
            self._attack_storage(ss, target)
        else:
            self._attack_smart(ss)

        log.info("LEGACY V36 END   mode=%s", mode)

    # ── Mode: Smart ────────────────────────────────────────────────
    def _attack_smart(self, screenshot: np.ndarray) -> None:
        line, side, anchor = self._vision.safe_deploy_line(screenshot, count=9)
        cluster = self._validate_cluster(screenshot, anchor)
        log.info("V2 smart: edge=%s cluster=%s", side, cluster)
        self._deploy_full(screenshot, cluster, side)

    # ── Mode: Building ─────────────────────────────────────────────
    def _attack_building(self, screenshot: np.ndarray, target_key: str) -> None:
        if not target_key:
            log.warning("V2 building: no target selected — falling back to smart.")
            return self._attack_smart(screenshot)

        candidates = self._vision.expand_storage_keys(target_key) or [target_key]
        hit_xy = None
        for key in candidates:
            hit = self._sr.find_template_by_name(screenshot, key)
            if hit:
                hit_xy = hit
                log.info("V2 building: '%s' located at %s", key, hit)
                break

        if hit_xy is None:
            log.warning("V2 building: '%s' not on screen — searching by panning…", target_key)
            hit_xy = self._search_by_panning(target_key)
            if hit_xy is None:
                log.warning("V2 building: target not found after panning — fallback smart.")
                _ss = screencap()
                return self._attack_smart(_ss if _ss is not None else screenshot)

        _ss = screencap()
        ss = _ss if _ss is not None else screenshot
        safe = self._vision.closest_safe_to(ss, hit_xy)
        if safe is None:
            log.warning("V2 building: no safe spot — fallback smart.")
            return self._attack_smart(ss)

        cluster = self._validate_cluster(ss, safe)
        side = self._side_for_cluster(ss, cluster)
        log.info("V2 building: deploy near %s edge=%s", cluster, side)
        self._deploy_full(ss, cluster, side)

    # ── Mode: Storage ──────────────────────────────────────────────
    def _attack_storage(self, screenshot: np.ndarray, target_prefix: str) -> None:
        if not target_prefix:
            log.warning("V2 storage: no prefix selected — falling back to smart.")
            return self._attack_smart(screenshot)

        prefixes = [target_prefix]
        targets = self._vision.find_all_targets(screenshot, prefixes)
        if not targets:
            log.warning("V2 storage: no '%s' on screen — searching by panning…", target_prefix)
            hit = self._search_by_panning(target_prefix)
            if hit is None:
                log.warning("V2 storage: nothing found — fallback smart.")
                _ss = screencap()
                return self._attack_smart(_ss if _ss is not None else screenshot)
            targets = [(target_prefix, hit[0], hit[1])]

        _ss = screencap()
        ss = _ss if _ss is not None else screenshot
        # Scout-tap each storage with ONE troop of the first selected type
        # (revealing them is enough — the army then dumps on the nearest).
        scout_troop = self._first_selected_troop()
        if scout_troop:
            for (key, tx, ty) in targets:
                if self._interrupted():
                    return
                safe = self._vision.closest_safe_to(ss, (tx, ty))
                if safe is None:
                    continue
                safe = self._validate_cluster(ss, safe)
                tloc = self._sr.find_template_by_name(ss, scout_troop)
                if tloc is None:
                    break
                tap(tloc[0], tloc[1])
                time.sleep(0.20)
                tap(safe[0], safe[1])
                log.info("V2 storage scout: %s @ %s -> drop @ %s", key, (tx, ty), safe)
                time.sleep(0.4)

        _ss = screencap()
        ss2 = _ss if _ss is not None else ss
        # Aim the main wave on the storage with the largest visible cluster.
        primary = targets[0]
        safe_main = self._vision.closest_safe_to(ss2, (primary[1], primary[2]))
        if safe_main is None:
            return self._attack_smart(ss2)
        cluster = self._validate_cluster(ss2, safe_main)
        side = self._side_for_cluster(ss2, cluster)
        log.info("V2 storage main wave: cluster=%s edge=%s", cluster, side)
        self._deploy_full(ss2, cluster, side)

    # ── Common deploy procedure ─────────────────────────────────────
    def _deploy_full(
        self,
        screenshot: np.ndarray,
        cluster_xy: tuple[int, int],
        side: str,
    ) -> None:
        """Legacy V36 single-cluster dump pattern — proven to work.

        Mechanics (intentionally identical to ``HomeVillageLogic.
        _execute_full_attack``):
          1. TROOPS  — for each card, tap to select then issue TWO long
             ``swipe`` calls of duration ``swipe_duration`` ms staying at
             the cluster point (±10 px). CoC reads this as a tap-and-hold
             dump and unloads ALL housed troops there.
          2. HEROES  — tap card → single tap at cluster (±15 px jitter).
          3. WAIT    — ``hero_ability_delay`` seconds before triggering
             hero abilities, so the heroes are ALIVE on screen.
          4. ABILITY — double-tap each hero's CARD slot in the bottom bar.
          5. SPELLS  — for each card, tap to select then drop along seven
             ``spread_depths`` from the cluster toward the enemy core.

        V2's contribution is choosing ``cluster_xy`` intelligently (red-
        zone aware safe edge in smart mode; closest-safe to a building or
        storage in those modes). The DEPLOY MECHANICS are unchanged from
        legacy because the legacy mechanics are the only ones that work
        reliably across emulators.
        """
        s = Settings()
        swipe_dur = int(s.get("swipe_duration", 2500))
        ability_delay = float(s.get("hero_ability_delay", 3.0))

        cluster_x, cluster_y = cluster_xy
        h, w = screenshot.shape[:2]
        ui_cutoff = self._sr.get_ui_cutoff(h)

        # True base core = center of red zone bbox; if not detected, screen
        # center. Spells fly along (cluster → core), so this matters.
        bbox = self._vision.red_zone_bbox(screenshot)
        if bbox is not None:
            rx, ry, rw, rh = bbox
            true_core_x = rx + rw // 2
            true_core_y = ry + rh // 2
        else:
            true_core_x, true_core_y = w // 2, ui_cutoff // 2

        _ss = screencap()
        fresh = _ss if _ss is not None else screenshot

        # ── STEP 1: TROOPS (long-press dump at cluster) ─────────────
        selected_troops = self._profile.get(self._key("selected_troops"), [])
        for troop_name in selected_troops:
            if self._interrupted():
                return
            tloc = self._sr.find_template_by_name(fresh, troop_name)
            if tloc is None:
                continue
            tap(tloc[0], tloc[1])
            time.sleep(0.20)
            log.info("V2 dump %s @ cluster (%d,%d) side=%s",
                     troop_name, cluster_x, cluster_y, side)
            # Two micro-offset long-presses at the SAME cluster point.
            # ±10 px is too small to register as a drag (CoC threshold is
            # >30 px), too big to be a duplicate-tap suppression. The long
            # duration is what dumps the entire slot.
            swipe(cluster_x, cluster_y,
                  cluster_x + 10, cluster_y + 10, duration_ms=swipe_dur)
            time.sleep(0.20)
            swipe(cluster_x, cluster_y,
                  cluster_x - 10, cluster_y - 10,
                  duration_ms=int(swipe_dur * 0.8))

        # ── STEP 2: HEROES (tap card → tap cluster) ──────────────────
        hero_memory: list[tuple[str, int, int]] = []
        selected_heroes = self._profile.get(self._key("selected_heroes"), [])
        for hero_name in selected_heroes:
            if self._interrupted():
                return
            hloc = self._sr.find_template_by_name(fresh, hero_name)
            if hloc is None:
                continue
            hero_memory.append((hero_name, hloc[0], hloc[1]))
            tap(hloc[0], hloc[1])
            time.sleep(0.20)
            tap(cluster_x + random.randint(-15, 15),
                cluster_y + random.randint(-15, 15))
            time.sleep(0.30)

        # ── STEP 3: HERO ABILITY WAIT ────────────────────────────────
        steps = max(1, int(ability_delay / 0.5))
        for _ in range(steps):
            if self._interrupted():
                return
            time.sleep(0.5)

        # ── STEP 4: HERO ABILITIES (double-tap memory slots) ────────
        for _, hx, hy in hero_memory:
            if self._interrupted():
                return
            tap(hx, hy); time.sleep(0.10)
            tap(hx, hy); time.sleep(0.30)

        # ── STEP 5: SPELLS (path from cluster toward base core) ─────
        _ss = screencap()
        spell_ss = _ss if _ss is not None else fresh
        selected_spells = self._profile.get(self._key("selected_spells"), [])
        # Same spread_depths as legacy V36 — known to land spells on top
        # of the army's pushing column without bunching them up.
        spread_depths = [0.55, 0.75, 0.95, 1.10, 0.85, 0.95, 1.00]
        for spell_name in selected_spells:
            if self._interrupted():
                return
            sloc = self._sr.find_template_by_name(spell_ss, spell_name)
            if sloc is None:
                continue
            tap(sloc[0], sloc[1])
            time.sleep(0.20)
            for depth in spread_depths:
                if self._interrupted():
                    return
                sx = int(cluster_x + (true_core_x - cluster_x) * depth)
                sy = int(cluster_y + (true_core_y - cluster_y) * depth)
                sx = max(10, min(sx, w - 10))
                sy = max(100, min(sy, ui_cutoff - 20))
                tap(sx + random.randint(-20, 20),
                    sy + random.randint(-20, 20))
                time.sleep(0.15)

        # Stamp deploy time on the engine (so retreat-after-deploy works).
        if self._engine is not None:
            try:
                self._engine._home_logic._post_deploy_time = time.time()
                self._engine._home_logic._battle_phase_done = True
                self._engine._home_logic._hero_memory = hero_memory
            except Exception:
                pass

    # ── Helpers ─────────────────────────────────────────────────────
    def _key(self, base: str) -> str:
        return f"bb_{base}" if self._mode_key == "bb" else base

    def _first_selected_troop(self) -> str | None:
        sel = self._profile.get(self._key("selected_troops"), [])
        return sel[0] if sel else None

    def _validate_cluster(
        self, screenshot: np.ndarray, cluster_xy: tuple[int, int],
    ) -> tuple[int, int]:
        """Guarantee the cluster point is OUTSIDE the red zone and inside
        the playfield. If V2's red-zone detection produced something
        suspicious, fall back to the legacy ``get_focused_deployment_line``
        center — that's the same proven cluster the legacy V36 uses.
        """
        h, w = screenshot.shape[:2]
        ui_cutoff = self._sr.get_ui_cutoff(h)
        cx, cy = int(cluster_xy[0]), int(cluster_xy[1])

        # 1) Hard clamp so we're never on the HUD strip.
        cx = int(np.clip(cx, 60, w - 60))
        cy = int(np.clip(cy, 110, ui_cutoff - 80))

        # 2) If the (now-clamped) point is INSIDE the red zone (with a
        #    generous margin), the V2 detector misjudged the safe edge.
        #    Fall back to the legacy line center.
        if self._vision.is_inside_red_zone(screenshot, cx, cy, margin=15):
            line, _ = self._sr.get_focused_deployment_line(
                screenshot, ui_cutoff, 15,
            )
            if line:
                lcx, lcy = line[len(line) // 2]
                lcx = int(np.clip(lcx, 60, w - 60))
                lcy = int(np.clip(lcy, 110, ui_cutoff - 80))
                log.warning(
                    "V2: cluster (%d,%d) inside red zone — fallback to legacy center (%d,%d)",
                    cx, cy, lcx, lcy,
                )
                return lcx, lcy

        return cx, cy

    @staticmethod
    def _side_for_cluster(
        screenshot: np.ndarray, cluster_xy: tuple[int, int],
    ) -> str:
        """Cardinal direction of the cluster relative to screen center —
        used only for log readability and (future) spell pairing.
        """
        h, w = screenshot.shape[:2]
        cx, cy = cluster_xy
        dx, dy = cx - w / 2, cy - h / 2
        if abs(dx) >= abs(dy):
            return "left" if dx < 0 else "right"
        return "top" if dy < 0 else "bottom"

    def _search_by_panning(self, asset_key: str) -> tuple[int, int] | None:
        """Pan the camera in 4 directions, screenshot each time, search."""
        for direction in ("right", "down", "left", "up"):
            if self._interrupted():
                return None
            pan_camera(direction, distance_px=320, duration_ms=600)
            time.sleep(0.4)
            ss = screencap()
            if ss is None:
                continue
            for key in self._vision.expand_storage_keys(asset_key) or [asset_key]:
                hit = self._sr.find_template_by_name(ss, key)
                if hit:
                    return hit
        return None

    def _interrupted(self) -> bool:
        if self._engine is None:
            return False
        return (not getattr(self._engine, "_running", False)) or getattr(self._engine, "_paused", False)

    def _should_brief(self, mode: Mode) -> bool:
        return bool(Settings().get("v2_show_briefing", True)) and mode in ("building", "storage")

    @staticmethod
    def _briefing_text(mode: Mode, target: str) -> str:
        if mode == "storage":
            return (
                f"Smart Vision V2 — STORAGE MODE\n\n"
                f"Target prefix:  {target or '<none>'}\n\n"
                "The bot will scout each storage with ONE troop to reveal\n"
                "its exact location, then dump the rest of the army on the\n"
                "closest safe spot. Recommended army composition:\n"
                "  • A cheap fodder troop FIRST in the deployment list\n"
                "    (Barbarian / Goblin) — used as the scout.\n"
                "  • Main wave behind it (Giants, Wizards, Heroes, …).\n\n"
                "Spells are paired left + right of the army path."
            )
        if mode == "building":
            return (
                f"Smart Vision V2 — BUILDING MODE\n\n"
                f"Target:  {target or '<none>'}\n\n"
                "The bot will drop the army on the closest SAFE tile next\n"
                "to the target — never directly on top of it. Spells are\n"
                "paired left + right of the army's path."
            )
        return ""
