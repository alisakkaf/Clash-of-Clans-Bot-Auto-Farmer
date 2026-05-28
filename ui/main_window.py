"""
Main Window — 6-tab layout with Settings & InteractiveAssist wiring.

V7 Changes:
  • OCR now finds ROIs via template matching (no calibration dialogs needed)
  • Profile save/load includes auto-retreat settings
  • Settings tab for performance profiles, vision toggles, console config
"""

import json
import os

from PyQt5.QtWidgets import (
    QMainWindow, QTabWidget, QDockWidget, QToolBar,
    QAction, QLabel, QWidget, QVBoxLayout, QFileDialog,
    QMessageBox, QSizePolicy,
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

from core.logger import BotLogger
from core.bot_engine import BotEngine
from core.settings import Settings, PRESETS
from ui.styles import DARK_THEME_QSS
from ui.console_widget import ConsoleWidget
from ui.home_village_tab import HomeVillageTab
from ui.builder_base_tab import BuilderBaseTab
from ui.asset_manager_tab import AssetManagerTab
from ui.sequence_builder_tab import SequenceBuilderTab
from ui.training_mode_tab import TrainingModeTab
from ui.settings_tab import SettingsTab
from ui.interactive_assist import InteractiveAssistDialog

log = BotLogger.get("main_window")

PROFILES_DIR = "profiles"
DEFAULT_PROFILE = os.path.join(PROFILES_DIR, "default_profile.json")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CoC Bot V6 — Clash of Clans Automation")
        self.setMinimumSize(1200, 800)
        self.resize(1440, 920)

        self._profile = self._load_profile()
        self._engine: BotEngine | None = None
        self._assets_ready = False

        self._init_ui()
        self._apply_profile()
        self._sync_sequences()
        log.info("Main window initialized (V6).")

    def _init_ui(self) -> None:
        # ── Toolbar ─────────────────────────────────────────────────────
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setStyleSheet("QToolBar { spacing: 10px; padding: 4px; }")
        self.addToolBar(toolbar)

        self._adb_label = QLabel("● ADB: Unknown")
        self._adb_label.setStyleSheet("color: #9e9e9e; font-weight: bold; padding: 0 12px;")
        toolbar.addWidget(self._adb_label)
        toolbar.addSeparator()

        self._preset_pill = QLabel()
        self._preset_pill.setObjectName("preset_pill")
        toolbar.addWidget(self._preset_pill)
        toolbar.addSeparator()

        load_act = QAction("📂 Load Profile", self)
        load_act.triggered.connect(self._load_profile_dialog)
        toolbar.addAction(load_act)

        save_act = QAction("💾 Save Profile", self)
        save_act.triggered.connect(self._save_profile_dialog)
        toolbar.addAction(save_act)
        toolbar.addSeparator()

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        self._ready_label = QLabel("❌ Assets Not Ready")
        self._ready_label.setObjectName("ready_pill_bad")
        toolbar.addWidget(self._ready_label)
        toolbar.addSeparator()

        self._start_act = QAction("▶  Start Bot", self)
        self._start_act.triggered.connect(self._start_bot)
        toolbar.addAction(self._start_act)

        self._stop_act = QAction("■  Stop Bot", self)
        self._stop_act.setEnabled(False)
        self._stop_act.triggered.connect(self._stop_bot)
        toolbar.addAction(self._stop_act)

        # ── Tabs ────────────────────────────────────────────────────────
        self._tabs = QTabWidget()

        self._home_tab = HomeVillageTab()
        self._home_tab.start_requested.connect(self._start_home_farming)
        self._home_tab.stop_requested.connect(self._stop_bot)

        self._bb_tab = BuilderBaseTab()
        self._bb_tab.start_requested.connect(self._start_bb)
        self._bb_tab.stop_requested.connect(self._stop_bot)

        self._asset_tab = AssetManagerTab()
        self._asset_tab.readiness_changed.connect(self._on_readiness_changed)
        self._asset_tab.assets_changed.connect(self._on_assets_changed)

        self._seq_tab = SequenceBuilderTab()
        self._seq_tab.sequences_changed.connect(self._on_sequences_changed)

        self._training_tab = TrainingModeTab()

        self._settings_tab = SettingsTab()

        self._tabs.addTab(self._home_tab,     "🏠  Home Village")
        self._tabs.addTab(self._bb_tab,       "🔨  Builder Base")
        self._tabs.addTab(self._asset_tab,    "📋  Asset Manager")
        self._tabs.addTab(self._seq_tab,      "🔗  Sequences")
        self._tabs.addTab(self._training_tab, "🎯  Training Mode")
        self._tabs.addTab(self._settings_tab, "⚙  Settings")

        self.setCentralWidget(self._tabs)

        # ── Console ─────────────────────────────────────────────────────
        self._console = ConsoleWidget()
        dock = QDockWidget("Console", self)
        dock.setWidget(self._console)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)

        # Wire settings → console + status bar + engine notice
        self._settings_tab.settings_changed.connect(self._console.apply_settings)
        self._settings_tab.settings_changed.connect(self._on_settings_changed)
        self._update_preset_pill()

        self.statusBar().showMessage("Ready. Configure settings, sequences, then start.")

    # ═══════════════════════════════════════════════════════════════════
    #  Sequence ↔ Asset Manager Sync
    # ═══════════════════════════════════════════════════════════════════

    def _on_sequences_changed(self, seqs: dict) -> None:
        self._sync_sequences()

    def _sync_sequences(self) -> None:
        seqs = self._seq_tab.get_sequences()
        self._asset_tab.set_sequences(
            seqs.get("hv_entry_sequence", []),
            seqs.get("bb_entry_sequence", []),
        )

    # ═══════════════════════════════════════════════════════════════════
    #  Readiness
    # ═══════════════════════════════════════════════════════════════════

    def _on_readiness_changed(self, ready: bool) -> None:
        self._assets_ready = ready
        if ready:
            self._ready_label.setText("✅ Assets Ready")
            self._ready_label.setObjectName("ready_pill_ok")
        else:
            self._ready_label.setText("❌ Assets Not Ready")
            self._ready_label.setObjectName("ready_pill_bad")
        # Re-apply stylesheet so the new objectName selector takes effect.
        self._ready_label.setStyle(self._ready_label.style())

    # ═════════════════════════════════════════════════════════════════════
    #  Settings broadcast
    # ═════════════════════════════════════════════════════════════════════

    def _on_settings_changed(self) -> None:
        """Settings tab edited → refresh status bar + invalidate caches."""
        self._update_preset_pill()
        if self._engine and self._engine.isRunning():
            self._engine.notify_assets_changed()  # also clears template cache

    def _update_preset_pill(self) -> None:
        s = Settings()
        preset = s.get("preset", "medium")
        tick = s.get("tick_interval", 1.0)
        label = PRESETS.get(preset, {}).get("label", preset.upper())
        self._preset_pill.setText(f"  {label}  •  tick={tick:.1f}s  ")

    # ═════════════════════════════════════════════════════════════════════
    #  Asset bus — single signal that refreshes ALL tabs
    # ═════════════════════════════════════════════════════════════════════

    def _on_assets_changed(self) -> None:
        """Manifest mutated → cascade refresh through HV / BB / Sequences / Engine."""
        log.info("Assets changed — fanning out refresh to all tabs.")
        self._home_tab.refresh_assets()
        self._bb_tab.refresh_assets()
        self._seq_tab.refresh_assets()
        # Recompute readiness against the new manifest.
        self._sync_sequences()
        if self._engine and self._engine.isRunning():
            self._engine.notify_assets_changed()

    def _check_readiness(self) -> bool:
        # Soft check: never blocks the user. Just refreshes the readiness label
        # so they can see in the toolbar which assets are still unmapped.
        self._sync_sequences()
        if not self._assets_ready:
            self.statusBar().showMessage(
                "⚠ Some sequence assets are unmapped — bot will skip them at runtime.",
            )
        return True

    # ═══════════════════════════════════════════════════════════════════
    #  Bot Control
    # ═══════════════════════════════════════════════════════════════════

    def _start_bot(self) -> None:
        idx = self._tabs.currentIndex()
        if idx == 0:
            self._start_home_farming()
        elif idx == 1:
            self._start_bb()
        else:
            QMessageBox.information(self, "Info", "Switch to HV or BB tab to start.")

    def _start_home_farming(self) -> None:
        if not self._check_readiness():
            return
        profile = {
            **self._profile,
            **self._home_tab.get_settings(),
            **self._seq_tab.get_sequences(),
        }
        self._launch_engine(profile, "home_village")
        self._home_tab.set_running_state(True)

    def _start_bb(self) -> None:
        if not self._check_readiness():
            return
        profile = {
            **self._profile,
            **self._bb_tab.get_settings(),
            **self._seq_tab.get_sequences(),
        }
        self._launch_engine(profile, "builder_base")
        self._bb_tab.set_running_state(True)

    def _launch_engine(self, profile: dict, mode: str) -> None:
        if self._engine is not None and self._engine.isRunning():
            self._engine.stop_bot()
            self._engine.wait(3000)

        self._engine = BotEngine(profile, mode)
        self._engine.state_changed.connect(self._on_state_changed)
        self._engine.loot_read.connect(self._on_loot_read)
        self._engine.error_occurred.connect(self._on_error)
        self._engine.bot_stopped.connect(self._on_bot_stopped)
        self._engine.help_needed.connect(self._on_help_needed)
        self._engine.game_not_installed.connect(self._on_game_not_installed)
        self._engine.briefing_needed.connect(self._on_briefing_needed)

        # start_bot() returns False if the game package is missing on the
        # connected device — keep the UI in stopped state in that case.
        if not self._engine.start_bot():
            self._home_tab.set_running_state(False)
            self._bb_tab.set_running_state(False)
            self.statusBar().showMessage("Bot did NOT start — game not installed.")
            return

        self._start_act.setEnabled(False)
        self._stop_act.setEnabled(True)
        self._adb_label.setText("● ADB: Running")
        self._adb_label.setStyleSheet("color: #4caf50; font-weight: bold; padding: 0 12px;")
        self.statusBar().showMessage(f"Bot running — {mode}")

        # Bind the running engine into the V2 panels so the Reload Config
        # button can hot-reload the live orchestrator.
        for tab in (self._home_tab, self._bb_tab):
            v2 = getattr(tab, "_v2", None)
            if v2 is not None and hasattr(v2, "set_engine"):
                v2.set_engine(self._engine)

    def _stop_bot(self) -> None:
        if self._engine:
            self._engine.stop_bot()
        self._start_act.setEnabled(True)
        self._stop_act.setEnabled(False)
        self._home_tab.set_running_state(False)
        self._bb_tab.set_running_state(False)
        self._adb_label.setText("● ADB: Idle")
        self._adb_label.setStyleSheet("color: #e9b44c; font-weight: bold; padding: 0 12px;")
        self.statusBar().showMessage("Bot stopped.")

        for tab in (self._home_tab, self._bb_tab):
            v2 = getattr(tab, "_v2", None)
            if v2 is not None and hasattr(v2, "set_engine"):
                v2.set_engine(None)

    # ═══════════════════════════════════════════════════════════════════
    #  Interactive Assist — "Help Me" Dialog
    # ═══════════════════════════════════════════════════════════════════

    def _on_help_needed(self, screenshot) -> None:
        """Called on the main thread via signal. Shows the assist dialog."""
        self.statusBar().showMessage("⚠  Bot PAUSED — needs your help!")
        self._adb_label.setText("● PAUSED")
        self._adb_label.setStyleSheet("color: #e94560; font-weight: bold; padding: 0 12px;")

        dlg = InteractiveAssistDialog(screenshot, self)
        dlg.exec_()
        action, data = dlg.get_result()

        if self._engine:
            self._engine.handle_assist_result(action, data)

        self._adb_label.setText("● ADB: Running")
        self._adb_label.setStyleSheet("color: #4caf50; font-weight: bold; padding: 0 12px;")
        self.statusBar().showMessage("Bot resumed after assist.")

        # Refresh asset tree in case new asset was saved
        if action == "saved_asset":
            self._asset_tab._refresh_tree()


    def _save_current_profile(self) -> None:
        """Auto-save the current profile to default location."""
        try:
            os.makedirs(PROFILES_DIR, exist_ok=True)
            with open(DEFAULT_PROFILE, "w", encoding="utf-8") as f:
                json.dump(self._profile, f, indent=2)
            log.info("Profile auto-saved to %s", DEFAULT_PROFILE)
        except Exception as exc:
            log.error("Auto-save failed: %s", exc)

    # ═══════════════════════════════════════════════════════════════════
    #  Signals
    # ═══════════════════════════════════════════════════════════════════

    def _on_state_changed(self, name: str) -> None:
        self.statusBar().showMessage(f"State: {name}")

    def _on_loot_read(self, g, e, d) -> None:
        self.statusBar().showMessage(f"Loot → G: {g:,} | E: {e:,} | DE: {d:,}")

    def _on_error(self, msg: str) -> None:
        self.statusBar().showMessage(f"Error: {msg}")

    def _on_briefing_needed(self, message: str) -> None:
        """Pre-attack V2 briefing — informs the user about army requirements."""
        QMessageBox.information(self, "Smart Vision V2 — Briefing", message)

    def _on_game_not_installed(self, package: str) -> None:
        """Critical: the configured game package is not installed on the device."""
        self.statusBar().showMessage(f"⚠  Game not installed: {package}")
        QMessageBox.critical(
            self,
            "Game Not Installed",
            (
                f"The configured game package is not installed on the connected device:\n\n"
                f"    {package}\n\n"
                "The bot cannot start until Clash of Clans is installed.\n"
                "If your device uses a different package name, change\n"
                "‘game_package’ in the Settings tab."
            ),
        )

    def _on_bot_stopped(self) -> None:
        self._stop_bot()

    # ═══════════════════════════════════════════════════════════════════
    #  Profile
    # ═══════════════════════════════════════════════════════════════════

    @staticmethod
    def _profile_defaults() -> dict:
        return {
            # HV thresholds
            "min_gold": 200000, "min_elixir": 200000, "min_dark_elixir": 1000,
            # HV retreat
            "auto_retreat_enabled": False, "retreat_heroes_dead": False,
            "retreat_gold": 50000, "retreat_elixir": 50000,
            "retreat_dark_elixir": 500, "retreat_time": 0,
            # HV deploy timer
            "deploy_timer_enabled": False, "deploy_timer_seconds": 90,
            # HV attack
            "hv_match_mode": "normal",
            "attack_strategy": "smart_target", "macro_file": "",
            "selected_troops": ["barbarian", "archer", "giant"],
            "selected_heroes": ["barbarian_king", "archer_queen", "grand_warden", "royal_champion"],
            "selected_spells": [],
            # BB
            "bb_attack_mode": "ranked", "bb_attack_strategy": "smart_target",
            "bb_macro_file": "", "bb_troop_abilities": True, "bb_hero_timer": 15,
            "bb_deploy_timer_enabled": False, "bb_deploy_timer_seconds": 90,
            "bb_selected_troops": [], "bb_selected_heroes": [],
            # Sequences
            "hv_entry_sequence": [], "bb_entry_sequence": [],
        }

    def _load_profile(self) -> dict:
        defaults = self._profile_defaults()
        if os.path.isfile(DEFAULT_PROFILE):
            try:
                with open(DEFAULT_PROFILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                # Defaults underneath, saved on top → future-proof against new keys.
                return {**defaults, **saved}
            except Exception as exc:
                log.error("Profile load error: %s", exc)
        return defaults

    def _apply_profile(self) -> None:
        self._home_tab.load_settings(self._profile)
        self._bb_tab.load_settings(self._profile)
        self._seq_tab.load_sequences(self._profile)

    def _collect_profile(self) -> dict:
        """Superset save: existing profile keys + all tab values, latest wins."""
        return {
            **self._profile_defaults(),
            **self._profile,
            **self._home_tab.get_settings(),
            **self._bb_tab.get_settings(),
            **self._seq_tab.get_sequences(),
        }

    def _save_profile_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save Profile", PROFILES_DIR, "JSON (*.json)")
        if not path:
            return
        profile = self._collect_profile()
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(profile, f, indent=2)
            self._profile = profile
            QMessageBox.information(self, "Saved", f"Profile saved to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Save failed:\n{exc}")

    def _load_profile_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load Profile", PROFILES_DIR, "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            # Merge over defaults so missing keys fall back gracefully.
            self._profile = {**self._profile_defaults(), **loaded}
            self._apply_profile()
            self._sync_sequences()
            QMessageBox.information(self, "Loaded", f"Profile loaded from:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Load failed:\n{exc}")

    def closeEvent(self, event) -> None:
        if self._engine and self._engine.isRunning():
            self._engine.stop_bot()
            self._engine.wait(3000)
        # Auto-save the latest tab values into default_profile.json.
        try:
            self._profile = self._collect_profile()
            self._save_current_profile()
        except Exception as exc:
            log.error("closeEvent autosave failed: %s", exc)
        event.accept()
