"""
Sequence Builder Tab — define ordered button sequences per attack mode.

V4 Compatible: Uses get_full_asset_catalogue() for the step dropdown
(dynamically picks up custom assets).
"""

import json
import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QComboBox, QPushButton,
    QListWidget, QListWidgetItem, QScrollArea,
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, pyqtSignal

from core.logger import BotLogger
from vision.template_manager import get_full_asset_catalogue, template_exists

log = BotLogger.get("seq_builder")


def _get_available_steps() -> list[tuple[str, str, str]]:
    """Return (key, label, category) for all UI/BB assets."""
    catalogue = get_full_asset_catalogue()
    return [
        (key, label, cat) for key, (cat, label, _) in sorted(catalogue.items())
        if cat in ("ui_elements", "builder_base", "custom")
    ]


class _SequenceEditor(QGroupBox):
    sequence_changed = pyqtSignal()

    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        self._list = QListWidget()
        self._list.setMinimumHeight(120)
        self._list.setDragDropMode(QListWidget.InternalMove)
        self._list.model().rowsMoved.connect(lambda: self.sequence_changed.emit())
        layout.addWidget(self._list)

        add_row = QHBoxLayout()
        self._combo = QComboBox()
        self._combo.setMinimumWidth(200)
        self._populate_combo()
        add_row.addWidget(self._combo)

        refresh_btn = QPushButton("🔄")
        refresh_btn.setFixedWidth(32)
        refresh_btn.setToolTip("Refresh list (picks up newly added assets)")
        refresh_btn.clicked.connect(self._populate_combo)
        add_row.addWidget(refresh_btn)

        add_btn = QPushButton("➕ Add Step")
        add_btn.clicked.connect(self._add_step)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)

        btn_row = QHBoxLayout()
        for text, fn in [("⬆ Up", self._move_up), ("⬇ Down", self._move_down),
                         ("🗑 Remove", self._remove), ("✖ Clear", self._clear)]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            btn_row.addWidget(b)
        layout.addLayout(btn_row)

    def _populate_combo(self):
        self._combo.clear()
        for key, label, cat in _get_available_steps():
            status = "✅" if template_exists(key) else "❌"
            self._combo.addItem(f"{status} {label} ({key})", key)

    def _add_step(self):
        key = self._combo.currentData()
        if key:
            catalogue = get_full_asset_catalogue()
            _, label, _ = catalogue.get(key, ("", key, False))
            status = "✅" if template_exists(key) else "❌"
            item = QListWidgetItem(f"{self._list.count()+1}. {status} {label} ({key})")
            item.setData(Qt.UserRole, key)
            self._list.addItem(item)
            self.sequence_changed.emit()

    def _remove(self):
        r = self._list.currentRow()
        if r >= 0:
            self._list.takeItem(r)
            self._renumber()
            self.sequence_changed.emit()

    def _move_up(self):
        r = self._list.currentRow()
        if r > 0:
            item = self._list.takeItem(r)
            self._list.insertItem(r-1, item)
            self._list.setCurrentRow(r-1)
            self._renumber()
            self.sequence_changed.emit()

    def _move_down(self):
        r = self._list.currentRow()
        if r < self._list.count()-1:
            item = self._list.takeItem(r)
            self._list.insertItem(r+1, item)
            self._list.setCurrentRow(r+1)
            self._renumber()
            self.sequence_changed.emit()

    def _clear(self):
        self._list.clear()
        self.sequence_changed.emit()

    def _renumber(self):
        catalogue = get_full_asset_catalogue()
        for i in range(self._list.count()):
            item = self._list.item(i)
            key = item.data(Qt.UserRole)
            _, label, _ = catalogue.get(key, ("", key, False))
            status = "✅" if template_exists(key) else "❌"
            item.setText(f"{i+1}. {status} {label} ({key})")

    def get_sequence(self) -> list[str]:
        return [self._list.item(i).data(Qt.UserRole) for i in range(self._list.count())]

    def set_sequence(self, keys: list[str]):
        self._list.clear()
        catalogue = get_full_asset_catalogue()
        for key in keys:
            _, label, _ = catalogue.get(key, ("", key, False))
            status = "✅" if template_exists(key) else "❌"
            item = QListWidgetItem(f"{self._list.count()+1}. {status} {label} ({key})")
            item.setData(Qt.UserRole, key)
            self._list.addItem(item)


class SequenceBuilderTab(QWidget):
    sequences_changed = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(12)

        hdr = QLabel("Attack Sequence Builder")
        hdr.setFont(QFont("Segoe UI", 14, QFont.Bold))
        layout.addWidget(hdr)

        info = QLabel(
            "Define the exact button-press sequence the bot uses to ENTER an attack.\n"
            "For each step, it scans → taps → waits → next step.\n"
            "Drag items to reorder. ❌ = unmapped asset (map it in Asset Manager)."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #9e9e9e; padding: 8px;")
        layout.addWidget(info)

        self._hv = _SequenceEditor("🏠  Home Village — Attack Entry Sequence")
        self._hv.sequence_changed.connect(self._changed)
        layout.addWidget(self._hv)

        self._bb = _SequenceEditor("🔨  Builder Base — Attack Entry Sequence")
        self._bb.sequence_changed.connect(self._changed)
        layout.addWidget(self._bb)

        layout.addStretch()
        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _changed(self):
        self.sequences_changed.emit(self.get_sequences())

    def get_sequences(self) -> dict:
        return {
            "hv_entry_sequence": self._hv.get_sequence(),
            "bb_entry_sequence": self._bb.get_sequence(),
        }

    def load_sequences(self, profile: dict):
        self._hv.set_sequence(profile.get("hv_entry_sequence", []))
        self._bb.set_sequence(profile.get("bb_entry_sequence", []))

    def refresh_assets(self) -> None:
        """Re-populate dropdowns when manifest changes; preserve current items."""
        self._hv._populate_combo()
        self._bb._populate_combo()
        # Re-render the existing sequences so status icons (\u2705/\u274c) stay current.
        self._hv.set_sequence(self._hv.get_sequence())
        self._bb.set_sequence(self._bb.get_sequence())
