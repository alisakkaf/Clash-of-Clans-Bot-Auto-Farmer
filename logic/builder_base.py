"""
Builder Base Logic — V39.1 Fresh Capture Strategy.

V39.1 CHANGES:
  • POST-HERO RE-SCAN: After deploying the Hero, the bot now takes a FRESH screenshot.
    This is critical because the UI changes (Health bars appear) once combat begins.
  • Better Troop Detection: By re-scanning, the bot sees the troops in their final 
    "combat-ready" state, fixing the issue where it couldn't find them before.
  • Maintains the stable Long-Swipe deployment logic.
"""

import random
import time
import cv2
import numpy as np

from core.logger import BotLogger
from core.adb_handler import tap, swipe, screencap as adb_screencap
from core.state_machine import StateMachine, GameState
from core.settings import Settings
from vision.screen_reader import ScreenReader
from vision.ocr_reader import OCRReader
from logic.smart_v2_logic import SmartV2Logic

log = BotLogger.get("builder_base")

C_GREEN = "\033[92m"
C_RED = "\033[91m"
C_RESET = "\033[0m"

BB_TEXT_CONFIDENCE = 0.75


class BuilderBaseLogic:
    def __init__(self, profile, sm, sr, ocr):
        self._profile = profile
        self._sm: StateMachine = sm
        self._sr: ScreenReader = sr
        self._ocr: OCRReader = ocr
        
        self._current_stage = 1
        self._stage_deployed = False
        self._active_combat_started = False
        self._hero_memory: list[tuple[str, int, int]] = []
        self._last_ability_tap_time: float = 0.0
        self._post_deploy_time: float = 0.0
        self._engine = None

        # Smart Vision V2 (BB) — opt-in.
        self._v2 = SmartV2Logic(self._profile, self._sr, self._ocr, mode_key="bb")

    def set_engine(self, engine):
        self._engine = engine
        self._v2.set_engine(engine)

    def update_profile(self, profile: dict):
        self._profile = profile
        self._v2.update_profile(profile)

    def _is_interrupted(self) -> bool:
        if self._engine is None: return False
        return not self._engine._running or self._engine._paused

    def handle(self, screenshot: np.ndarray, state: GameState):
        if state == GameState.BUILDER_BASE_HOME:
            self._handle_home(screenshot)
        elif state == GameState.BB_BATTLE or state == GameState.BB_BATTLE_STAGE2:
            self._handle_battle(screenshot)
        elif state == GameState.BATTLE_ENDED:
            self._handle_battle_ended(screenshot)

    def _handle_home(self, screenshot: np.ndarray):
        m_confirm = self._sr.find_template_by_name(screenshot, "bb_attack_confirm", 0.70)
        if m_confirm:
            log.info("Clicking BB Attack Confirmation...")
            tap(m_confirm[0], m_confirm[1])
            time.sleep(1.0)
            return

        m_find = self._sr.find_template_by_name(screenshot, "bb_find_match", 0.75)
        if m_find:
            tap(m_find[0], m_find[1])

    def _handle_battle(self, screenshot: np.ndarray):
        h, w = screenshot.shape[:2]
        top_roi = screenshot[0:int(h * 0.25), int(w * 0.25):int(w * 0.75)]
        
        is_prep = self._sr.find_template_by_name(top_roi, "bb_prep_text", BB_TEXT_CONFIDENCE) is not None
        is_active = self._sr.find_template_by_name(top_roi, "bb_active_text", BB_TEXT_CONFIDENCE) is not None

        if self._current_stage == 1 and self._active_combat_started and is_prep:
            log.info("%sDetected Stage Transition! Resetting for Stage 2...%s", C_GREEN, C_RESET)
            self._current_stage = 2
            self._stage_deployed = False
            self._active_combat_started = False
            self._hero_memory.clear()
            self._post_deploy_time = 0.0

        # 1. DEPLOYMENT
        if not self._stage_deployed:
            log.info("BB Stage %d: Starting Intelligent Deployment...", self._current_stage)
            self._deploy_army(screenshot)
            self._stage_deployed = True
            self._post_deploy_time = time.time()
            return

        # 2. COMBAT STATE TRACKING
        if self._stage_deployed and not self._active_combat_started:
            if is_active:
                log.info("%sCombat formally started. Monitoring abilities...%s", C_GREEN, C_RESET)
                self._active_combat_started = True
                self._last_ability_tap_time = time.time()
            return

        # 3. ACTIVE ABILITIES + DEPLOY TIMER WATCHDOG
        if self._active_combat_started:
            if self._check_deploy_timer(screenshot):
                return
            self._trigger_hero_abilities()
            if self._current_stage == 1:
                self._check_stage2_transition(screenshot)

    def _check_deploy_timer(self, screenshot: np.ndarray) -> bool:
        """
        Silent post-deployment countdown for Builder Base.
        Counts ``bb_deploy_timer_seconds`` from the moment the current
        stage finished deploying, then ends the battle if the user enabled
        ``bb_deploy_timer_enabled``.
        """
        if not self._profile.get("bb_deploy_timer_enabled", False):
            return False
        if self._post_deploy_time <= 0:
            return False
        seconds = int(self._profile.get("bb_deploy_timer_seconds", 90))
        if seconds <= 0:
            return False
        elapsed = time.time() - self._post_deploy_time
        if elapsed >= seconds:
            log.info("%sBB DEPLOY TIMER: %.0fs elapsed → attempting battle exit.%s",
                     C_RED, elapsed, C_RESET)
            self._post_deploy_time = 0.0
            # BB doesn't have an explicit "end battle" button mid-stage; we
            # simply stop deploying further and let the natural BB flow end.
            self._active_combat_started = False
            self._stage_deployed = True
            return True
        return False

    def _check_stage2_transition(self, screenshot: np.ndarray):
        m = self._sr.find_template_by_name(screenshot, "bb_stage2_indicator", 0.65)
        if m:
            log.info("%s>>> MOVING TO STAGE 2! <<<%s", C_GREEN, C_RESET)
            tap(m[0], m[1])
            self._current_stage = 2
            self._stage_deployed = False 
            self._active_combat_started = False
            self._hero_memory.clear()
            self._sm.transition(GameState.BB_BATTLE_STAGE2)
            time.sleep(3.0)  

    def _handle_battle_ended(self, screenshot: np.ndarray):
        self._current_stage = 1
        self._stage_deployed = False
        self._active_combat_started = False
        self._hero_memory.clear()
        self._post_deploy_time = 0.0
        m = self._sr.find_template_by_name(screenshot, "bb_return_home") or \
            self._sr.find_template_by_name(screenshot, "bb_battle_result")
        if m: tap(m[0], m[1])

    # ═══════════════════════════════════════════════════════════════════
    #  V39.1 FRESH CAPTURE DEPLOYMENT
    # ═══════════════════════════════════════════════════════════════════

    def _deploy_army(self, screenshot: np.ndarray):
        if self._is_interrupted(): return

        # Smart Vision V2 fast path (BB).
        if self._v2.is_enabled():
            log.info("═══ SMART VISION V2 — BB ═══")
            self._v2.execute(screenshot)
            self._stage_deployed = True
            self._post_deploy_time = time.time()
            return

        h, w = screenshot.shape[:2]
        ui_cutoff = self._sr.get_ui_cutoff(h)

        # ── Step 1: Initial Hero Drop ──
        selected_heroes = self._profile.get("bb_selected_heroes", [])
        if self._current_stage == 1: 
            self._hero_memory.clear()
            time.sleep(1.5) # Wait for UI to settle

        # Find drop point once
        deploy_line, _ = self._sr.get_focused_deployment_line(screenshot, ui_cutoff, 15)
        raw_cx, raw_cy = deploy_line[len(deploy_line)//2] if deploy_line else (w//2, ui_cutoff//2)
        cx, cy = max(100, min(raw_cx, w-100)), max(100, min(raw_cy, ui_cutoff-50))

        # Drop Hero First
        for hero_name in selected_heroes:
            hero_loc = self._sr.find_template_by_name(screenshot, hero_name)
            if hero_loc:
                if not any(name == hero_name for name, _, _ in self._hero_memory):
                    self._hero_memory.append((hero_name, hero_loc[0], hero_loc[1]))
                tap(hero_loc[0], hero_loc[1])
                time.sleep(0.4)
                tap(cx, cy)
                time.sleep(0.5)

        # ── Step 2: FRESH SCREENSHOT FOR TROOPS ──
        # Now that the hero is down, health bars are visible. Take a new shot!
        log.info("Hero deployed. Capturing FRESH screenshot for troop detection...")
        fresh_ss = adb_screencap()
        if fresh_ss is None: fresh_ss = screenshot

        # ── Step 3: Deploy Troops with the new view ──
        selected_troops = self._profile.get("bb_selected_troops", [])
        trigger_troop_abs = self._profile.get("bb_troop_abilities", True)

        for troop_name in selected_troops:
            if self._is_interrupted(): return
            
            # Find the card using the FRESH capture
            troop_loc = self._sr.find_template_by_name(fresh_ss, troop_name)
            if troop_loc is None:
                log.warning("Could not find troop card: %s (Even with re-scan)", troop_name)
                continue

            tap(troop_loc[0], troop_loc[1])
            time.sleep(0.5) # Time for health bar/selection highlight
            
            log.info("Executing Long-Swipe for %s...", troop_name)
            # BB needs longer holds than HV → 1.6× the configured swipe_duration
            base_swipe = int(Settings().get("swipe_duration", 2500))
            swipe(cx, cy, cx + 20, cy + 20, duration_ms=int(base_swipe * 1.6))
            time.sleep(0.2)
            
            if trigger_troop_abs:
                time.sleep(0.3)
                tap(troop_loc[0], troop_loc[1])
            
            time.sleep(0.3)

    def _trigger_hero_abilities(self):
        if self._is_interrupted() or not self._hero_memory: return
        hero_interval = self._profile.get("bb_hero_timer", 15)
        if time.time() - self._last_ability_tap_time >= hero_interval:
            log.info("BB: Triggering Hero Ability...")
            for name, hx, hy in self._hero_memory:
                tap(hx, hy)
                time.sleep(0.1)
                tap(hx, hy)
            self._last_ability_tap_time = time.time()