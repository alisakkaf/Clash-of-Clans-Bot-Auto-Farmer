"""
Bot Engine — QThread main loop with continuous vision tick,
stuck detection, macro support, and V6 ROI calibration fallback.

V6 CHANGE:
  • On start_bot(), checks OCRReader.get_missing_calibrations().
  • If ROIs are missing, emits calibration_needed signal BEFORE
    entering the main loop. MainWindow shows InteractiveAssistDialog
    for each missing ROI and saves results to the profile.
  • OCRReader now receives the profile dict at construction.
"""

import time
import traceback

from PyQt5.QtCore import QThread, pyqtSignal

from core.logger import BotLogger
from core.adb_handler import screencap, tap, check_connection, press_back, press_home
from core.adb_handler import play_recording, load_recording
from core.adb_handler import (
    is_app_installed,
    is_game_running,
    launch_app,
    get_focused_package,
)
from core.state_machine import StateMachine, GameState
from vision.screen_reader import ScreenReader
from vision.ocr_reader import OCRReader
from vision.template_manager import get_sequence_readiness
from logic.home_village import HomeVillageLogic
from logic.builder_base import BuilderBaseLogic
from core.settings import Settings

log = BotLogger.get("engine")

SEQUENCE_SCAN_TIMEOUT = 12
SEQUENCE_SCAN_SLEEP = 0.8
ACTION_CHAIN_MAX_LOOPS = 15
ACTION_CHAIN_SLEEP = 1.0
STUCK_TIMEOUT = 20

# After tapping `attack_button2` (Find a Match) the game *sometimes*
# shows an extra Confirm popup — usually in Ranked mode, occasionally
# in Normal. We poll for `confirm_button` for this many seconds before
# giving up so we never miss it, and never freeze if it doesn't appear.
POST_ATTACK_CONFIRM_WAIT = 4.0
POST_ATTACK_CONFIRM_POLL = 0.5


class BotEngine(QThread):
    """Central automation thread."""

    state_changed      = pyqtSignal(str)
    loot_read          = pyqtSignal(int, int, int)
    battle_status      = pyqtSignal(str)
    error_occurred     = pyqtSignal(str)
    bot_stopped        = pyqtSignal()
    help_needed        = pyqtSignal(object)          # np.ndarray screenshot
    game_not_installed = pyqtSignal(str)             # package name
    briefing_needed    = pyqtSignal(str)             # multi-line message

    def __init__(self, profile: dict, mode: str = "home_village") -> None:
        super().__init__()
        self._running = False
        self._paused = False
        self._profile = profile
        self._mode = mode
        self._executing_sequence = False

        self._sm = StateMachine()
        self._screen_reader = ScreenReader()
        self._ocr = OCRReader()
        self._home_logic = HomeVillageLogic(self._profile, self._sm, self._screen_reader, self._ocr)
        self._bb_logic = BuilderBaseLogic(self._profile, self._sm, self._screen_reader, self._ocr)

        self._home_logic.set_engine(self)
        self._bb_logic.set_engine(self)

        # Stuck detection
        self._state_enter_time = time.time()
        self._help_already_requested = False

        # Game-presence periodic check (timestamps of the last verification).
        self._last_game_check: float = 0.0

    # ── Control ─────────────────────────────────────────────────────────

    def _ensure_game_running(self, allow_launch: bool = True) -> bool:
        """Make sure the configured game package is the foreground app.

        Returns True only if (a) the package is installed and
        (b) it is now focused (already focused, or was successfully
        launched when ``allow_launch`` is True). Returns False if the
        app is not installed — caller should refuse to start the bot.
        """
        s = Settings()
        package = str(s.get("game_package", "com.supercell.clashofclans"))

        if not is_app_installed(package):
            log.error("Game package not installed on device: %s", package)
            self.game_not_installed.emit(package)
            return False

        if is_game_running(package):
            return True

        focused = get_focused_package() or "<unknown>"
        log.warning(
            "Game is not in the foreground (focused: %s). %s",
            focused,
            "Auto-launching…" if allow_launch and s.get("auto_launch_game", True)
            else "Skipping auto-launch.",
        )
        if allow_launch and s.get("auto_launch_game", True):
            if launch_app(package):
                # Give Android a moment to bring the app forward.
                time.sleep(2.0)
                return is_game_running(package)
        return False

    def start_bot(self) -> bool:
        """Start the bot thread.

        Returns False (and does NOT start the QThread) when the game is
        not installed on the device. The caller is responsible for
        listening to ``game_not_installed`` and showing a UI message.
        """
        # Soft readiness notice — missing assets are SKIPPED at runtime, not blocked.
        hv_seq = self._profile.get("hv_entry_sequence", [])
        bb_seq = self._profile.get("bb_entry_sequence", [])
        ready, seq_missing = get_sequence_readiness(hv_seq, bb_seq)
        if not ready and seq_missing:
            log.warning(
                "Starting with %d unmapped sequence asset(s) (will be skipped): %s",
                len(seq_missing), ", ".join(seq_missing),
            )

        # Hard guard: refuse to start if the configured game package is
        # not installed on the connected device. Other failure modes
        # (game not focused) are auto-recovered via launch_app().
        if not self._ensure_game_running(allow_launch=True):
            if not is_app_installed(str(Settings().get("game_package",
                                                        "com.supercell.clashofclans"))):
                log.error("Refusing to start bot — game package missing.")
                return False
            log.warning("Game could not be brought to foreground; "
                        "starting anyway and will keep retrying in the loop.")

        self._last_game_check = time.time()
        log.info("Starting bot (mode=%s).", self._mode)
        self._running = True
        self.start()
        return True

    def stop_bot(self) -> None:
        log.info("Bot engine STOP.")
        self._running = False
        self._paused = False

    def pause(self) -> None:
        log.info("Bot engine PAUSED.")
        self._paused = True

    def resume(self) -> None:
        log.info("Bot engine RESUMED.")
        self._paused = False
        self._help_already_requested = False
        self._state_enter_time = time.time()

    def set_mode(self, mode: str) -> None:
        self._mode = mode

    def update_profile(self, profile: dict) -> None:
        self._profile = profile
        self._home_logic.update_profile(profile)
        self._bb_logic.update_profile(profile)

    def handle_assist_result(self, action: str, data) -> None:
        """Called by MainWindow after InteractiveAssistDialog closes."""
        if action == "manual_tap" and data is not None:
            x, y = data
            tap(x, y)
            log.info("Assist: manual tap at (%d, %d).", x, y)
        elif action == "abort_home":
            press_back()
            time.sleep(0.5)
            press_home()
            log.info("Assist: aborting to home screen.")
        elif action == "saved_asset":
            self._screen_reader.clear_cache()
            log.info("Assist: new asset saved, cache cleared.")
        self.resume()

    def notify_assets_changed(self) -> None:
        """Called by MainWindow when the asset manifest changes."""
        self._screen_reader.clear_cache()
        log.info("Assets changed → template cache cleared.")

    # ── Main Loop ───────────────────────────────────────────────────────

    def run(self) -> None:
        log.info("Bot thread started.")
        consecutive_errors = 0

        while self._running:
            if self._paused:
                time.sleep(0.5)
                continue

            try:
                self._tick()
                consecutive_errors = 0
            except Exception as exc:
                consecutive_errors += 1
                log.error("Tick error (#%d): %s\n%s", consecutive_errors, exc, traceback.format_exc())
                self.error_occurred.emit(str(exc))
                if consecutive_errors >= 10:
                    self._running = False
                    break

            time.sleep(Settings().get("tick_interval", 1.0))

        log.info("Bot thread exiting.")
        self.bot_stopped.emit()

    def _tick(self) -> None:
        if self._executing_sequence:
            return

        # ── Periodic game-presence check ──────────────────────────────
        # Runs at most once every Settings.game_check_interval seconds
        # so we don't spam dumpsys on every tick. If the user switched
        # to another app, try to bring CoC back to the foreground.
        interval = float(Settings().get("game_check_interval", 60))
        if interval > 0 and (time.time() - self._last_game_check) >= interval:
            self._last_game_check = time.time()
            self._ensure_game_running(allow_launch=True)

        if not check_connection():
            self._sm.transition(GameState.DISCONNECTED)
            self.state_changed.emit(GameState.DISCONNECTED.name)
            time.sleep(5)
            return

        screenshot = screencap()
        if screenshot is None:
            return

        detected = self._screen_reader.detect_state(screenshot)
        prev_state = self._sm.state
        if detected != prev_state:
            self._sm.transition(detected)
            self.state_changed.emit(detected.name)
            self._state_enter_time = time.time()
            self._help_already_requested = False
        else:
            # ── Stuck Detection ───────────────────────────────────
            elapsed = time.time() - self._state_enter_time
            if (
                elapsed > STUCK_TIMEOUT
                and not self._help_already_requested
                and detected in (GameState.UNKNOWN, GameState.LOADING)
            ):
                log.warning(
                    "STUCK in %s for %.0f s — requesting user help.",
                    detected.name, elapsed,
                )
                self._help_already_requested = True
                self.pause()
                self.help_needed.emit(screenshot)
                return

        # ── Handle state ────────────────────────────────────────────────
        if detected == GameState.DISCONNECTED:
            self._handle_disconnect(screenshot)
            return

        if detected in (GameState.CONFIRMING, GameState.BB_CONFIRMING):
            self._handle_action_chain()
            return

        if self._mode == "builder_base":
            self._bb_logic.handle(screenshot, detected)
        else:
            self._home_logic.handle(screenshot, detected)

    # ═══════════════════════════════════════════════════════════════════
    #  SEQUENCE EXECUTOR
    # ═══════════════════════════════════════════════════════════════════

    def execute_attack_sequence(self, sequence: list[str]) -> bool:
        if not sequence:
            return False

        self._executing_sequence = True
        log.info("SEQUENCE: %d steps…", len(sequence))

        for step_idx, template_key in enumerate(sequence):
            if not self._running or self._paused:
                self._executing_sequence = False
                return False

            log.info("SEQ [%d/%d]: scanning '%s'…", step_idx+1, len(sequence), template_key)
            found = False
            start_time = time.time()

            while time.time() - start_time < SEQUENCE_SCAN_TIMEOUT:
                if not self._running or self._paused:
                    self._executing_sequence = False
                    return False

                ss = screencap()
                if ss is None:
                    time.sleep(SEQUENCE_SCAN_SLEEP)
                    continue

                match = self._screen_reader.find_template_by_name(ss, template_key, 0.70)
                if match is not None:
                    tap(match[0], match[1])
                    log.info("SEQ [%d/%d]: tapped '%s' at (%d,%d).",
                             step_idx+1, len(sequence), template_key, match[0], match[1])
                    found = True
                    time.sleep(1.0 + step_idx * 0.2)
                    break
                time.sleep(SEQUENCE_SCAN_SLEEP)

            if not found:
                log.warning("SEQ [%d/%d]: '%s' not found — skipping.",
                            step_idx+1, len(sequence), template_key)

        self._executing_sequence = False
        return True

    # ── Macro Playback ──────────────────────────────────────────────────

    def execute_macro(self, filepath: str) -> None:
        events = load_recording(filepath)
        if events:
            self._executing_sequence = True
            play_recording(events)
            self._executing_sequence = False
        else:
            log.warning("Macro file empty or missing: %s", filepath)

    # ── Fallback Action Chain ───────────────────────────────────────────

    def _handle_action_chain(self) -> None:
        # Respect the user's HV match-mode choice (Normal vs Ranked).
        preferred_mode = (
            "ranked_mode_btn"
            if str(self._profile.get("hv_match_mode", "normal")).lower() == "ranked"
            else "normal_mode_btn"
        )
        rejected_mode = (
            "normal_mode_btn" if preferred_mode == "ranked_mode_btn" else "ranked_mode_btn"
        )

        # Tiered priority — lower tier = tapped first.
        #   Tier 0: pick the Mode tab the user chose (Normal / Ranked).
        #   Tier 1: press the FINAL confirm — attack_button2 or confirm_button
        #           (whichever appears, they are alternates with different text
        #           but the same role: start matchmaking).
        #   Tier 2: fallback popups (end-battle confirm, disconnect reload).
        priority = {
            preferred_mode:       0,
            "attack_button2":     1,
            "confirm_button":     1,
            "end_battle_confirm": 2,
            "reload_button":      2,
        }

        for attempt in range(ACTION_CHAIN_MAX_LOOPS):
            if not self._running or self._paused:
                return
            screenshot = screencap()
            if screenshot is None:
                time.sleep(ACTION_CHAIN_SLEEP)
                continue
            new_state = self._screen_reader.detect_state(screenshot)
            if new_state not in (GameState.CONFIRMING, GameState.BB_CONFIRMING, GameState.UNKNOWN):
                self._sm.transition(new_state)
                self.state_changed.emit(new_state.name)
                return
            confirmations = self._screen_reader.scan_for_confirmations(screenshot)
            if confirmations:
                # Never tap the rejected match-mode tab.
                confirmations = [c for c in confirmations if c[0] != rejected_mode]
                confirmations.sort(
                    key=lambda c: (priority.get(c[0], 99), -c[3]),
                )
                if confirmations:
                    name, cx, cy, _ = confirmations[0]
                    log.debug("ACTION-CHAIN tap '%s' at (%d,%d)", name, cx, cy)
                    tap(cx, cy)
                    # ── Post-attack Confirm grace window ──────────────
                    # The "Find a Match" button (attack_button2) is
                    # sometimes followed by an extra Confirm popup
                    # (always in Ranked, occasionally in Normal). We
                    # poll briefly for it so it's never missed even
                    # when the state has already transitioned.
                    if name == "attack_button2":
                        self._await_post_attack_confirm()
            time.sleep(ACTION_CHAIN_SLEEP)

    def _await_post_attack_confirm(self) -> None:
        """Poll for an optional ``confirm_button`` for a few seconds.
        Taps it as soon as it appears; returns silently if it doesn't.
        """
        deadline = time.time() + POST_ATTACK_CONFIRM_WAIT
        while time.time() < deadline:
            if not self._running or self._paused:
                return
            time.sleep(POST_ATTACK_CONFIRM_POLL)
            ss = screencap()
            if ss is None:
                continue
            cm = self._screen_reader.find_template_by_name(ss, "confirm_button")
            if cm:
                log.info("Post-attack confirm_button detected at (%d,%d) — tapping.",
                         cm[0], cm[1])
                tap(cm[0], cm[1])
                return
        log.debug("No post-attack confirm popup within %.1fs — continuing.",
                  POST_ATTACK_CONFIRM_WAIT)

    def _handle_disconnect(self, screenshot) -> None:
        match = self._screen_reader.find_template_by_name(screenshot, "reload_button")
        if match:
            tap(match[0], match[1])
        else:
            log.warning("reload_button not found during disconnect handling.")
