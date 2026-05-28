"""
Builder Base Tab — V10: Perfect Drag & Drop Filtering & Profile Saving.

V10 CHANGES:
  • Fixed the bug where UI elements (like bb_attack_confirm) appeared in the Troops list.
  • Fixed Hero saving/loading logic in the Profile.
  • Strict filtering for _bb suffixes.
"""

import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QSpinBox, QPushButton, QCheckBox,
    QComboBox, QScrollArea, QFileDialog, QListWidget, 
    QListWidgetItem, QAbstractItemView, QMessageBox, QInputDialog
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, pyqtSignal

from core.logger import BotLogger
from core.adb_handler import start_recording, stop_recording, save_recording
from vision.template_manager import list_assets_by_category
from ui.smart_v2_panel import SmartV2Panel

log = BotLogger.get("bb_tab")


class _OrderableList(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("orderable_list")
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setMinimumHeight(160)

    def populate(self, assets: list[tuple[str, str, bool]], saved_selection: list[str]):
        self.clear()
        added_keys = set()
        
        # 1. Add saved items first (in order)
        for key in saved_selection:
            for k, label, has_img in assets:
                if k == key:
                    self._add_item(k, label, has_img, True)
                    added_keys.add(k)
                    break
                    
        # 2. Add remaining assets unchecked
        for k, label, has_img in assets:
            if k not in added_keys:
                self._add_item(k, label, has_img, False)

    def _add_item(self, key, label, has_img, checked):
        status = "✅" if has_img else "❌"
        item = QListWidgetItem(f"{status} {label}")
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled)
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        item.setData(Qt.UserRole, key)
        self.addItem(item)

    def get_selected_ordered(self) -> list[str]:
        selected = []
        for i in range(self.count()):
            item = self.item(i)
            if item.checkState() == Qt.Checked:
                selected.append(item.data(Qt.UserRole))
        return selected


class BuilderBaseTab(QWidget):
    start_requested = pyqtSignal()
    stop_requested  = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._recording = False
        self._init_ui()

    def _init_ui(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(10)

        hdr = QLabel("Builder Base — Advanced Attack Configuration")
        hdr.setFont(QFont("Segoe UI", 14, QFont.Bold))
        layout.addWidget(hdr)

        # ── Match Mode ──────────────────────────────────────────────────
        match_group = QGroupBox("Match Settings")
        match_layout = QHBoxLayout()
        match_layout.addWidget(QLabel("Mode:"))
        self._match_mode = QComboBox()
        self._match_mode.addItems(["Ranked", "Practice"])
        match_layout.addWidget(self._match_mode)
        match_layout.addStretch()
        match_group.setLayout(match_layout)
        layout.addWidget(match_group)

        # ── Abilities Configuration ─────────────────────────────────
        abilities_group = QGroupBox("Abilities & Automation")
        ab_layout = QGridLayout()

        self._troop_abilities = QCheckBox("Auto-Trigger Troop Abilities (e.g., Bomber)")
        self._troop_abilities.setChecked(True)
        ab_layout.addWidget(self._troop_abilities, 0, 0, 1, 2)

        ab_layout.addWidget(QLabel("Trigger Hero Ability Every (Seconds):"), 1, 0)
        self._hero_timer = QSpinBox()
        self._hero_timer.setRange(5, 60)
        self._hero_timer.setValue(15)
        ab_layout.addWidget(self._hero_timer, 1, 1)

        # ── NEW: Post-Deployment Timer (silent end-of-stage countdown) ──
        self._deploy_timer_enabled = QCheckBox("End BB battle after troops/heroes are deployed")
        self._deploy_timer_enabled.setToolTip(
            "Once the bot finishes the deployment for the current BB stage,\n"
            "it counts the seconds silently. When the countdown ends the bot\n"
            "stops nudging abilities and lets the natural BB flow finish.",
        )
        ab_layout.addWidget(self._deploy_timer_enabled, 2, 0, 1, 2)

        ab_layout.addWidget(QLabel("End after deployment (s):"), 3, 0)
        self._deploy_timer_seconds = QSpinBox()
        self._deploy_timer_seconds.setRange(5, 300)
        self._deploy_timer_seconds.setSingleStep(5)
        self._deploy_timer_seconds.setValue(90)
        ab_layout.addWidget(self._deploy_timer_seconds, 3, 1)

        abilities_group.setLayout(ab_layout)
        layout.addWidget(abilities_group)

        # ── Hybrid Attack Mode ──────────────────────────────────────────
        mode_group = QGroupBox("Execution Strategy")
        mode_layout = QHBoxLayout()

        mode_layout.addWidget(QLabel("Strategy:"))
        self._attack_mode = QComboBox()
        self._attack_mode.addItems(["Smart Vision AI", "Playback Recorded Macro"])
        self._attack_mode.currentIndexChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self._attack_mode)

        self._macro_label = QLabel("Macro:")
        self._macro_label.hide()
        mode_layout.addWidget(self._macro_label)

        self._macro_path_label = QLabel("(none)")
        self._macro_path_label.setStyleSheet("color: #9e9e9e;")
        self._macro_path_label.hide()
        mode_layout.addWidget(self._macro_path_label)

        self._macro_pick_btn = QPushButton("📂 Browse…")
        self._macro_pick_btn.hide()
        self._macro_pick_btn.clicked.connect(self._pick_macro)
        mode_layout.addWidget(self._macro_pick_btn)

        self._record_btn = QPushButton("🔴 Record Macro")
        self._record_btn.setMinimumHeight(32)
        self._record_btn.clicked.connect(self._toggle_recording)
        mode_layout.addWidget(self._record_btn)

        mode_layout.addStretch()
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)
        self._macro_file = ""

        # ── Lists (Drag & Drop) ───────────────────────────────────────
        lists_layout = QHBoxLayout()

        troop_box = QGroupBox("BB Troops (Drag to Reorder)")
        tv = QVBoxLayout()
        troop_refresh = QPushButton("🔄 Refresh BB Assets")
        troop_refresh.clicked.connect(lambda: self._rebuild_lists())
        tv.addWidget(troop_refresh)
        self._troop_list = _OrderableList()
        tv.addWidget(self._troop_list)
        troop_box.setLayout(tv)
        lists_layout.addWidget(troop_box)

        hero_box = QGroupBox("BB Heroes (Drag to Reorder)")
        hv = QVBoxLayout()
        self._hero_list = _OrderableList()
        hv.addWidget(self._hero_list)
        hero_box.setLayout(hv)
        lists_layout.addWidget(hero_box)

        layout.addLayout(lists_layout)
        self._rebuild_lists()

        # ── Smart Vision V2 ─────────────────────────────────────────────
        self._v2 = SmartV2Panel("bb")
        layout.addWidget(self._v2)

        # ── Action Buttons ──────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._start_btn = QPushButton("▶  Start Builder Base")
        self._start_btn.setObjectName("start_button")
        self._start_btn.setMinimumHeight(40)
        self._start_btn.clicked.connect(self.start_requested.emit)
        btn_row.addWidget(self._start_btn)

        self._stop_btn = QPushButton("■  Stop")
        self._stop_btn.setObjectName("stop_button")
        self._stop_btn.setMinimumHeight(40)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self.stop_requested.emit)
        btn_row.addWidget(self._stop_btn)
        layout.addLayout(btn_row)

        layout.addStretch()
        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _rebuild_lists(self, saved_troops=None, saved_heroes=None) -> None:
        t_sel = saved_troops if saved_troops is not None else self._troop_list.get_selected_ordered()
        h_sel = saved_heroes if saved_heroes is not None else self._hero_list.get_selected_ordered()

        bb_troops = []
        bb_heroes = []
        
        all_assets = list_assets_by_category("troops") + list_assets_by_category("heroes") + list_assets_by_category("builder_base")
        seen = set()
        
        # STRICT UI FILTER: These keys will NEVER show up in troops/heroes list
        skip_ui = {
            "bb_find_match", "bb_attack_confirm", "bb_stage2_indicator", 
            "bb_return_home", "bb_battle_result", "bb_battle_hud", "bb_troop_slot"
        }

        for k, label, has_img in all_assets:
            if k in seen or k in skip_ui: 
                continue
            
            # Allow items ending in _bb or categorised manually
            if k.endswith("_bb") or k.startswith("bb_") or "builder_base" in k:
                seen.add(k)
                if "machine" in k.lower() or "copter" in k.lower() or "hero" in k.lower():
                    bb_heroes.append((k, label, has_img))
                else:
                    bb_troops.append((k, label, has_img))

        self._troop_list.populate(bb_troops, t_sel)
        self._hero_list.populate(bb_heroes, h_sel)

    def _on_mode_changed(self, index: int) -> None:
        is_macro = index == 1
        self._macro_label.setVisible(is_macro)
        self._macro_path_label.setVisible(is_macro)
        self._macro_pick_btn.setVisible(is_macro)

    def _pick_macro(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Macro Recording", "recordings", "JSON (*.json);;All Files (*)")
        if path:
            self._macro_file = path
            self._macro_path_label.setText(os.path.basename(path))

    def _toggle_recording(self) -> None:
        if not self._recording:
            self._recording = True
            self._record_btn.setText("⏹ Stop Recording")
            self._record_btn.setObjectName("stop_button")
            self._record_btn.setStyle(self._record_btn.style())
            start_recording()
        else:
            self._recording = False
            self._record_btn.setText("🔴 Record Macro")
            self._record_btn.setObjectName("")
            self._record_btn.setStyle(self._record_btn.style())
            events = stop_recording()
            if not events: return
            name, ok = QInputDialog.getText(self, "Save Macro", "Macro name:", text="bb_attack_macro")
            if ok and name.strip():
                os.makedirs("recordings", exist_ok=True)
                filepath = os.path.join("recordings", f"{name.strip()}.json")
                save_recording(events, filepath)
                self._macro_file = filepath
                self._macro_path_label.setText(os.path.basename(filepath))
                self._attack_mode.setCurrentIndex(1)

    def get_settings(self) -> dict:
        mode = "smart_target" if self._attack_mode.currentIndex() == 0 else "macro_playback"
        return {
            "bb_attack_mode": self._match_mode.currentText().lower(),
            "bb_attack_strategy": mode,
            "bb_macro_file": self._macro_file,
            "bb_troop_abilities": self._troop_abilities.isChecked(),
            "bb_hero_timer": self._hero_timer.value(),
            "bb_deploy_timer_enabled": self._deploy_timer_enabled.isChecked(),
            "bb_deploy_timer_seconds": self._deploy_timer_seconds.value(),
            "bb_selected_troops": self._troop_list.get_selected_ordered(),
            "bb_selected_heroes": self._hero_list.get_selected_ordered(),
        }

    def load_settings(self, profile: dict) -> None:
        mode = profile.get("bb_attack_mode", "ranked")
        self._match_mode.setCurrentIndex(0 if mode == "ranked" else 1)

        strategy = profile.get("bb_attack_strategy", "smart_target")
        self._attack_mode.setCurrentIndex(1 if strategy == "macro_playback" else 0)
        self._macro_file = profile.get("bb_macro_file", "")
        if self._macro_file:
            self._macro_path_label.setText(os.path.basename(self._macro_file))

        self._troop_abilities.setChecked(profile.get("bb_troop_abilities", True))
        self._hero_timer.setValue(profile.get("bb_hero_timer", 15))
        self._deploy_timer_enabled.setChecked(profile.get("bb_deploy_timer_enabled", False))
        self._deploy_timer_seconds.setValue(profile.get("bb_deploy_timer_seconds", 90))

        # V10: Pass saved profiles directly to rebuild to restore checking and order
        t_sel = profile.get("bb_selected_troops", [])
        h_sel = profile.get("bb_selected_heroes", [])
        self._rebuild_lists(saved_troops=t_sel, saved_heroes=h_sel)

    def set_running_state(self, running: bool) -> None:
        self._running = running
        self._start_btn.setEnabled(not running)
        self._stop_btn.setEnabled(running)

    def refresh_assets(self) -> None:
        """Re-populate BB lists from the manifest while preserving selection/order."""
        self._rebuild_lists()
        if hasattr(self, "_v2"):
            self._v2.refresh_targets()