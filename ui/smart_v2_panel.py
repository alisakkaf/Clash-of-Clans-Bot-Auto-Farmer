"""
Smart Vision AI V2 — reusable QGroupBox embedded in HV and BB tabs.

UI surface for the CSR (Config + Skills + Rules) attack system:
  • Enable / disable per village.
  • Strategy mode (smart / building / storage) — legacy compat.
  • NEW: Rule selector (auto / smart_default / air / ground / raid / snipe).
  • NEW: Reload Config button (hot-reload JSON files in config/).
  • NEW: Active rule indicator (shows what the orchestrator picked).
  • Zoom-out steps + decoration wait + briefing toggle.
  • Target picker synced with the Asset Manager.
"""

import os
import subprocess
import sys
from pathlib import Path

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QComboBox, QSpinBox, QDoubleSpinBox, QFormLayout, QPushButton,
    QFrame, QSizePolicy,
)

from core.logger import BotLogger
from core.settings import Settings
from vision.template_manager import list_assets_by_category

log = BotLogger.get("v2_panel")

_BUILDING_CATEGORIES = ("buildings", "builder_base", "custom")

_RULE_OPTIONS = [
    ("Auto  — orchestrator picks the best rule", "auto"),
    ("Smart Default  — widest corridor + long-press dump",   "smart_default"),
    ("Air Attack  — fan along safest air corridor",          "air_attack"),
    ("Ground Funnel  — 2-prong funnel + main wave",          "ground_funnel"),
    ("Resource Raid  — scout each storage, then dump",       "resource_raid"),
    ("TH Snipe  — closest safe corridor to target building", "th_snipe"),
]


class SmartV2Panel(QGroupBox):
    """One V2 configuration block. ``mode_key`` ∈ {"hv","bb"} so the
    same widget feeds two independent settings groups."""

    settings_changed = pyqtSignal()

    def __init__(self, mode_key: str, parent=None):
        super().__init__("Smart Vision AI V2 (CSR)", parent)
        assert mode_key in ("hv", "bb")
        self._mode_key = mode_key
        self._s = Settings()
        self._engine = None
        self._init_ui()
        self.refresh_targets()
        self._load()

    def set_engine(self, engine) -> None:
        """Bound by MainWindow so 'Reload Config' can hot-reload the
        running orchestrator inside the engine threads."""
        self._engine = engine

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)

        self._chk_enable = QCheckBox("Enable V2 (Red-Zone-Aware Smart Deploy)")
        self._chk_enable.setToolTip(
            "When ON, this village uses the V2 CSR planner. The legacy\n"
            "V36 flow remains as ULTIMATE FALLBACK if the orchestrator\n"
            "fails. Independent per village.",
        )
        self._chk_enable.stateChanged.connect(self._emit)
        root.addWidget(self._chk_enable)

        form = QFormLayout()

        self._combo_mode = QComboBox()
        self._combo_mode.addItem("Smart  (no specific target)",         "smart")
        self._combo_mode.addItem("Building  (closest safe spot)",       "building")
        self._combo_mode.addItem("Storage  (scout + dump nearest)",     "storage")
        self._combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        form.addRow("Strategy:", self._combo_mode)

        self._combo_target = QComboBox()
        self._combo_target.setMinimumWidth(260)
        self._combo_target.setToolTip(
            "Synced with the Asset Manager. Pick a building (or its\n"
            "level variant) — the bot will aim at the closest one on\n"
            "screen and deploy on the nearest safe tile next to it.",
        )
        self._combo_target.currentIndexChanged.connect(self._emit)
        form.addRow("Target:", self._combo_target)

        self._combo_rule = QComboBox()
        for label, value in _RULE_OPTIONS:
            self._combo_rule.addItem(label, value)
        self._combo_rule.setToolTip(
            "Manual rule override. 'Auto' lets the orchestrator pick the\n"
            "best rule based on your selected troops + target.\n"
            "Override only if you want to force a specific strategy.",
        )
        self._combo_rule.currentIndexChanged.connect(self._emit)
        form.addRow("V2 Rule:", self._combo_rule)

        zoom_row = QHBoxLayout()
        zoom_row.addWidget(QLabel("Pinch zoom-out steps:"))
        self._spin_zoom = QSpinBox()
        self._spin_zoom.setRange(0, 5)
        self._spin_zoom.setToolTip(
            "Each step = one two-finger pinch to enlarge the view.\n"
            "Set to 0 if multi-touch is unsupported on your emulator.",
        )
        self._spin_zoom.valueChanged.connect(self._emit)
        zoom_row.addWidget(self._spin_zoom)

        zoom_row.addSpacing(16)
        zoom_row.addWidget(QLabel("Decoration fade wait (s):"))
        self._spin_wait = QDoubleSpinBox()
        self._spin_wait.setRange(0.0, 15.0)
        self._spin_wait.setSingleStep(0.5)
        self._spin_wait.setDecimals(1)
        self._spin_wait.setToolTip(
            "Time to wait AFTER loot scan before re-screencapping for\n"
            "deployment planning. Enemy decorations fade after a few\n"
            "seconds so the safe-line detection becomes accurate.",
        )
        self._spin_wait.valueChanged.connect(self._emit)
        zoom_row.addWidget(self._spin_wait)
        zoom_row.addStretch()

        self._chk_brief = QCheckBox("Show pre-attack briefing dialog")
        self._chk_brief.setToolTip(
            "Pop a one-page English briefing the first time a Building\n"
            "or Storage attack is launched, so you know what army to\n"
            "bring before the bot starts dropping.",
        )
        self._chk_brief.stateChanged.connect(self._emit)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)

        cfg_row = QHBoxLayout()
        self._lbl_cfg_status = QLabel("Config: ready (config/v2_*.json)")
        self._lbl_cfg_status.setStyleSheet("color: #c0c0c0;")
        self._lbl_cfg_status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        cfg_row.addWidget(self._lbl_cfg_status)

        self._btn_reload = QPushButton("Reload Config")
        self._btn_reload.setToolTip(
            "Hot-reload the V2 JSON config files (config/v2_*.json) in the\n"
            "running orchestrator without restarting the bot.",
        )
        self._btn_reload.clicked.connect(self._on_reload_config)
        cfg_row.addWidget(self._btn_reload)

        self._btn_open = QPushButton("Open Config Folder")
        self._btn_open.setToolTip(
            "Open the config/ folder in your OS file explorer to edit\n"
            "v2_attack_rules.json / v2_troop_profiles.json / v2_spell_profiles.json.",
        )
        self._btn_open.clicked.connect(self._on_open_config_folder)
        cfg_row.addWidget(self._btn_open)

        root.addLayout(form)
        root.addLayout(zoom_row)
        root.addWidget(self._chk_brief)
        root.addWidget(sep)
        root.addLayout(cfg_row)

    # ── Sync from Asset Manager ─────────────────────────────────────
    def refresh_targets(self) -> None:
        prev = self._combo_target.currentData()
        self._combo_target.blockSignals(True)
        self._combo_target.clear()
        self._combo_target.addItem("(none)", "")
        seen: set[str] = set()
        for category in _BUILDING_CATEGORIES:
            for key, label, has_image in list_assets_by_category(category):
                if key in seen:
                    continue
                seen.add(key)
                tag = "✓" if has_image else "○"
                self._combo_target.addItem(f"{tag}  {label}  [{category}]", key)
        if prev:
            idx = self._combo_target.findData(prev)
            if idx >= 0:
                self._combo_target.setCurrentIndex(idx)
        self._combo_target.blockSignals(False)

    # ── Settings I/O ────────────────────────────────────────────────
    def _key(self, base: str) -> str:
        return f"{base}_{self._mode_key}"

    def _load(self) -> None:
        for w in (self._chk_enable, self._combo_mode, self._combo_target,
                  self._combo_rule, self._spin_zoom, self._spin_wait,
                  self._chk_brief):
            w.blockSignals(True)

        self._chk_enable.setChecked(bool(self._s.get(self._key("v2_enabled"), False)))
        mode = str(self._s.get(self._key("v2_mode"), "smart"))
        idx = self._combo_mode.findData(mode)
        self._combo_mode.setCurrentIndex(max(0, idx))

        target = str(self._s.get(self._key("v2_target"), ""))
        tidx = self._combo_target.findData(target)
        self._combo_target.setCurrentIndex(max(0, tidx))

        rule = str(self._s.get(self._key("v2_rule"), "auto"))
        ridx = self._combo_rule.findData(rule)
        self._combo_rule.setCurrentIndex(max(0, ridx))

        self._spin_zoom.setValue(int(self._s.get("v2_zoom_out_steps", 2)))
        self._spin_wait.setValue(float(self._s.get("v2_decoration_wait", 5.0)))
        self._chk_brief.setChecked(bool(self._s.get("v2_show_briefing", True)))

        for w in (self._chk_enable, self._combo_mode, self._combo_target,
                  self._combo_rule, self._spin_zoom, self._spin_wait,
                  self._chk_brief):
            w.blockSignals(False)

        self._on_mode_changed()

    def _save(self) -> None:
        self._s.set(self._key("v2_enabled"),  self._chk_enable.isChecked())
        self._s.set(self._key("v2_mode"),     self._combo_mode.currentData() or "smart")
        self._s.set(self._key("v2_target"),   self._combo_target.currentData() or "")
        self._s.set(self._key("v2_rule"),     self._combo_rule.currentData() or "auto")
        self._s.set("v2_zoom_out_steps",      self._spin_zoom.value())
        self._s.set("v2_decoration_wait",     self._spin_wait.value())
        self._s.set("v2_show_briefing",       self._chk_brief.isChecked())
        self._s.save()

    def _on_mode_changed(self) -> None:
        mode = self._combo_mode.currentData()
        self._combo_target.setEnabled(mode in ("building", "storage"))
        self._emit()

    # ── Config controls ─────────────────────────────────────
    def _on_reload_config(self) -> None:
        """Hot-reload the V2 JSON configs in the running engine."""
        ok_engine = False
        if self._engine is not None:
            for attr in ("_home_logic", "_bb_logic"):
                logic = getattr(self._engine, attr, None)
                if logic is None:
                    continue
                v2 = getattr(logic, "_v2", None)
                if v2 is None or not hasattr(v2, "reload_config"):
                    continue
                try:
                    v2.reload_config()
                    ok_engine = True
                except Exception as exc:
                    log.warning("reload_config failed on %s: %s", attr, exc)
        msg = (
            "Config reloaded into running orchestrator."
            if ok_engine
            else "Config will be reloaded on next attack (engine not running)."
        )
        self._lbl_cfg_status.setText(f"Config: {msg}")
        log.info("V2 panel reload_config: %s", msg)

    def _on_open_config_folder(self) -> None:
        root = Path(__file__).resolve().parent.parent / "config"
        root.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(root))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(root)])
            else:
                subprocess.Popen(["xdg-open", str(root)])
        except Exception as exc:
            log.warning("open config folder failed: %s", exc)
            self._lbl_cfg_status.setText(f"Config: open failed — {root}")

    def _emit(self, *_) -> None:
        self._save()
        self.settings_changed.emit()
