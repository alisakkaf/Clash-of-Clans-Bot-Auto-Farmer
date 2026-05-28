"""
Asset Manager Tab — DYNAMIC manifest with Add/Delete custom assets.

V4 Changes:
  • Assets are loaded from get_full_asset_catalogue() (defaults + manifest)
  • "Add Custom Asset" button: user picks category + name
  • "Delete Asset Definition" removes the asset from manifest entirely
  • Readiness is SEQUENCE-BASED: only checks if sequence assets are mapped
  • readiness_changed signal includes the current sequences from the
    SequenceBuilderTab (fetched via parent reference)
"""

import os

import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QLineEdit, QPushButton, QComboBox,
    QTreeWidget, QTreeWidgetItem, QMessageBox, QFileDialog,
    QSplitter, QDialog, QDialogButtonBox, QSizePolicy, QInputDialog,
)
from PyQt5.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QIcon, QFont
from PyQt5.QtCore import Qt, QRect, QPoint, pyqtSignal

from core.logger import BotLogger
from core.adb_handler import screencap
from vision.template_manager import (
    template_exists, save_template, import_template_from_file,
    delete_template, delete_asset, load_template, register_asset,
    get_full_asset_catalogue, get_sequence_readiness, VALID_CATEGORIES,
)

log = BotLogger.get("asset_mgr")


# ═══════════════════════════════════════════════════════════════════════
#  Capture Canvas
# ═══════════════════════════════════════════════════════════════════════

class _CaptureCanvas(QLabel):
    region_selected = pyqtSignal(int, int, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(600, 400)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("border: 1px solid #0f3460; background: #0d0d1a;")
        self._pixmap: QPixmap | None = None
        self._original: np.ndarray | None = None
        self._drawing = False
        self._start = QPoint()
        self._end = QPoint()
        self._scaled_pixmap: QPixmap | None = None
        self._offset_x = 0
        self._offset_y = 0

    def set_image(self, image: np.ndarray):
        self._original = image.copy()
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        self._pixmap = QPixmap.fromImage(qimg)
        self._refresh()

    def get_crop(self, x, y, w, h):
        if self._original is None:
            return None
        ih, iw = self._original.shape[:2]
        x, y = max(0, min(x, iw-1)), max(0, min(y, ih-1))
        w, h = min(w, iw-x), min(h, ih-y)
        return self._original[y:y+h, x:x+w].copy() if w > 0 and h > 0 else None

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self._pixmap:
            self._drawing = True
            self._start = e.pos()
            self._end = e.pos()

    def mouseMoveEvent(self, e):
        if self._drawing:
            self._end = e.pos()
            self._refresh()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self._drawing:
            self._drawing = False
            self._end = e.pos()
            self._refresh()
            self._emit()

    def _refresh(self):
        if self._pixmap is None:
            return
        scaled = self._pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._scaled_pixmap = scaled
        self._offset_x = (self.width() - scaled.width()) // 2
        self._offset_y = (self.height() - scaled.height()) // 2
        disp = scaled.copy()
        if self._start != self._end:
            p = QPainter(disp)
            p.setPen(QPen(QColor("#e94560"), 2))
            s = QPoint(self._start.x()-self._offset_x, self._start.y()-self._offset_y)
            e = QPoint(self._end.x()-self._offset_x, self._end.y()-self._offset_y)
            p.drawRect(QRect(s, e).normalized())
            p.end()
        self.setPixmap(disp)

    def _emit(self):
        if not self._pixmap or self._original is None or self._scaled_pixmap is None:
            return
        dw, dh = self._scaled_pixmap.width(), self._scaled_pixmap.height()
        oh, ow = self._original.shape[:2]
        if dw == 0 or dh == 0:
            return
        sx, sy = ow/dw, oh/dh
        r = QRect(self._start, self._end).normalized()
        ix = max(0, int((r.x()-self._offset_x)*sx))
        iy = max(0, int((r.y()-self._offset_y)*sy))
        iw = min(int(r.width()*sx), ow-ix)
        ih = min(int(r.height()*sy), oh-iy)
        if iw > 3 and ih > 3:
            self.region_selected.emit(ix, iy, iw, ih)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._refresh()


class CaptureDialog(QDialog):
    def __init__(self, asset_key: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Capture: {asset_key}")
        self.setMinimumSize(800, 550)
        self._asset_key = asset_key
        self._crop: np.ndarray | None = None
        layout = QVBoxLayout(self)
        self._canvas = _CaptureCanvas()
        self._canvas.region_selected.connect(self._on_region)
        layout.addWidget(self._canvas)
        self._info = QLabel("Click 'Take Screenshot' then draw a bounding box.")
        layout.addWidget(self._info)
        btn_row = QHBoxLayout()
        snap = QPushButton("📷  Take Screenshot")
        snap.clicked.connect(self._snap)
        btn_row.addWidget(snap)
        btn_row.addStretch()
        self._btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self._btn_box.button(QDialogButtonBox.Ok).setEnabled(False)
        self._btn_box.accepted.connect(self.accept)
        self._btn_box.rejected.connect(self.reject)
        btn_row.addWidget(self._btn_box)
        layout.addLayout(btn_row)

    def _snap(self):
        img = screencap()
        if img is None:
            QMessageBox.warning(self, "Error", "Screenshot failed.")
            return
        self._canvas.set_image(img)
        self._info.setText("Draw a red bounding box around the target.")

    def _on_region(self, x, y, w, h):
        self._crop = self._canvas.get_crop(x, y, w, h)
        if self._crop is not None:
            self._btn_box.button(QDialogButtonBox.Ok).setEnabled(True)
            self._info.setText(f"Selected: x={x} y={y} w={w} h={h}. Press OK.")

    def get_crop(self):
        return self._crop


# ═══════════════════════════════════════════════════════════════════════
#  Asset Manager Tab
# ═══════════════════════════════════════════════════════════════════════

class AssetManagerTab(QWidget):
    """Dynamic asset management with sequence-based readiness."""

    readiness_changed = pyqtSignal(bool)
    assets_changed    = pyqtSignal()   # emitted whenever the manifest is mutated

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_key: str | None = None
        self._hv_sequence: list[str] = []
        self._bb_sequence: list[str] = []
        self._init_ui()
        self._refresh_tree()

    def set_sequences(self, hv_seq: list[str], bb_seq: list[str]) -> None:
        """Called by MainWindow to update the sequences for readiness check."""
        self._hv_sequence = hv_seq
        self._bb_sequence = bb_seq
        self._refresh_tree()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        hdr = QLabel("Asset Manager — Map game elements (fully dynamic)")
        hdr.setObjectName("header_label")
        layout.addWidget(hdr)

        self._readiness_label = QLabel()
        self._readiness_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self._readiness_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._readiness_label)

        # ── Add / Delete Custom Asset buttons ───────────────────────────
        custom_row = QHBoxLayout()
        add_btn = QPushButton("➕  Add Custom Asset")
        add_btn.setMinimumHeight(32)
        add_btn.clicked.connect(self._add_custom_asset)
        custom_row.addWidget(add_btn)

        del_btn = QPushButton("🗑  Delete Asset Definition")
        del_btn.setMinimumHeight(32)
        del_btn.clicked.connect(self._delete_asset_definition)
        custom_row.addWidget(del_btn)

        custom_row.addStretch()
        layout.addLayout(custom_row)

        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)

        # ── LEFT: Tree ──────────────────────────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Status", "Asset Name", "Category", "In Sequence"])
        self._tree.setColumnWidth(0, 60)
        self._tree.setColumnWidth(1, 220)
        self._tree.setColumnWidth(2, 120)
        self._tree.setColumnWidth(3, 90)
        self._tree.setAlternatingRowColors(True)
        self._tree.setStyleSheet(
            "QTreeWidget { alternate-background-color: #16213e; }"
            "QTreeWidget::item { padding: 4px; }"
        )
        self._tree.currentItemChanged.connect(self._on_item_selected)
        left_layout.addWidget(self._tree)
        splitter.addWidget(left)

        # ── RIGHT: Actions ──────────────────────────────────────────────
        right = QWidget()
        right.setMaximumWidth(380)
        right_layout = QVBoxLayout(right)

        self._preview = QLabel("No preview")
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setMinimumHeight(150)
        self._preview.setStyleSheet("border: 1px solid #0f3460; background: #0d0d1a;")
        right_layout.addWidget(self._preview)

        self._selected_label = QLabel("Select an asset from the tree.")
        self._selected_label.setWordWrap(True)
        right_layout.addWidget(self._selected_label)

        actions = QGroupBox("Actions")
        al = QVBoxLayout()
        self._capture_btn = QPushButton("📷  Capture from Screen")
        self._capture_btn.setMinimumHeight(36)
        self._capture_btn.setEnabled(False)
        self._capture_btn.clicked.connect(self._on_capture)
        al.addWidget(self._capture_btn)

        self._upload_btn = QPushButton("📂  Upload Image File")
        self._upload_btn.setMinimumHeight(36)
        self._upload_btn.setEnabled(False)
        self._upload_btn.clicked.connect(self._on_upload)
        al.addWidget(self._upload_btn)

        self._delete_btn = QPushButton("🗑  Remove Template Image")
        self._delete_btn.setMinimumHeight(34)
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._on_delete)
        al.addWidget(self._delete_btn)

        actions.setLayout(al)
        right_layout.addWidget(actions)

        refresh_btn = QPushButton("🔄  Refresh Checklist")
        refresh_btn.clicked.connect(self._refresh_tree)
        right_layout.addWidget(refresh_btn)

        right_layout.addStretch()
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

    # ═══════════════════════════════════════════════════════════════════
    #  Tree
    # ═══════════════════════════════════════════════════════════════════

    def _refresh_tree(self) -> None:
        prev_key = self._selected_key
        self._tree.blockSignals(True)
        self._tree.clear()

        catalogue = get_full_asset_catalogue()
        seq_keys = set(self._hv_sequence) | set(self._bb_sequence)

        cat_items: dict[str, QTreeWidgetItem] = {}
        mapped = 0
        item_to_reselect = None

        for key, (category, label, has_img) in sorted(catalogue.items(), key=lambda x: (x[1][0], x[1][1])):
            if category not in cat_items:
                ci = QTreeWidgetItem(self._tree)
                ci.setText(1, category.replace("_", " ").title())
                ci.setFont(1, QFont("Segoe UI", 11, QFont.Bold))
                ci.setExpanded(True)
                ci.setFlags(ci.flags() & ~Qt.ItemIsSelectable)
                cat_items[category] = ci

            parent = cat_items[category]
            item = QTreeWidgetItem(parent)
            item.setText(0, "✅" if has_img else "❌")
            item.setText(1, label)
            item.setText(2, category.replace("_", " ").title())
            in_seq = "YES" if key in seq_keys else ""
            item.setText(3, in_seq)
            item.setData(0, Qt.UserRole, key)

            if has_img:
                mapped += 1
            elif key in seq_keys:
                for col in range(4):
                    item.setForeground(col, QColor("#e94560"))

            if key == prev_key:
                item_to_reselect = item

        # Category counters
        for cat, ci in cat_items.items():
            cc = ci.childCount()
            mc = sum(1 for i in range(cc) if ci.child(i).text(0) == "✅")
            ci.setText(0, f"{mc}/{cc}")

        # Readiness banner — SEQUENCE-BASED
        ready, missing = get_sequence_readiness(self._hv_sequence, self._bb_sequence)
        total = len(catalogue)
        if not seq_keys:
            # No sequences configured → NOT ready (cannot start the bot).
            ready = False
            self._readiness_label.setText(
                f"⚠  Define an attack sequence in the Sequences tab — {mapped}/{total} assets mapped"
            )
            self._readiness_label.setStyleSheet(
                "color: #e9b44c; background: #2e2a1a; padding: 8px; border-radius: 6px;"
            )
        elif ready:
            self._readiness_label.setText(
                f"✅  READY — All {len(seq_keys)} sequence assets mapped ({mapped}/{total} total)"
            )
            self._readiness_label.setStyleSheet(
                "color: #4caf50; background: #1a2e1a; padding: 8px; border-radius: 6px;"
            )
        else:
            preview = ", ".join(missing[:5])
            suffix = "…" if len(missing) > 5 else ""
            self._readiness_label.setText(
                f"❌  NOT READY — {len(missing)} sequence asset(s) missing: {preview}{suffix}"
            )
            self._readiness_label.setStyleSheet(
                "color: #e94560; background: #2e1a1a; padding: 8px; border-radius: 6px;"
            )

        self._tree.blockSignals(False)
        self.readiness_changed.emit(ready)

        if item_to_reselect:
            self._tree.setCurrentItem(item_to_reselect)
        else:
            self._update_right_panel(None)

    # ═══════════════════════════════════════════════════════════════════
    #  Item Selection
    # ═══════════════════════════════════════════════════════════════════

    def _on_item_selected(self, current, previous):
        if current is None:
            self._update_right_panel(None)
            return
        self._update_right_panel(current.data(0, Qt.UserRole))

    def _update_right_panel(self, key: str | None):
        self._selected_key = key
        if not key:
            self._capture_btn.setEnabled(False)
            self._upload_btn.setEnabled(False)
            self._delete_btn.setEnabled(False)
            self._selected_label.setText("Select an asset.")
            self._preview.setText("No preview")
            self._preview.setPixmap(QPixmap())
            return

        catalogue = get_full_asset_catalogue()
        if key not in catalogue:
            return

        category, label, has_img = catalogue[key]
        self._capture_btn.setEnabled(True)
        self._upload_btn.setEnabled(True)
        self._delete_btn.setEnabled(has_img)

        seq_keys = set(self._hv_sequence) | set(self._bb_sequence)
        in_seq = "YES" if key in seq_keys else "No"
        status = "Mapped ✅" if has_img else "Missing ❌"
        self._selected_label.setText(
            f"<b>{label}</b><br>"
            f"Key: <code>{key}</code><br>"
            f"Category: {category}<br>"
            f"Status: {status}<br>"
            f"In Sequence: {in_seq}"
        )

        if has_img:
            img = load_template(key)
            if img is not None:
                self._show_preview(img)
            else:
                self._preview.setText("(file missing)")
        else:
            self._preview.setText("Not yet mapped")
            self._preview.setPixmap(QPixmap())

    # ═══════════════════════════════════════════════════════════════════
    #  Add / Delete Custom Asset
    # ═══════════════════════════════════════════════════════════════════

    def _add_custom_asset(self):
        name, ok = QInputDialog.getText(
            self, "Add Custom Asset",
            "Enter asset key (lowercase, underscores, e.g. 'super_archer'):",
        )
        if not ok or not name.strip():
            return
        name = name.strip().lower().replace(" ", "_")

        cats = [c.replace("_", " ").title() for c in VALID_CATEGORIES]
        cat, ok2 = QInputDialog.getItem(
            self, "Category", "Select category:", cats, 0, False,
        )
        if not ok2:
            return
        cat_key = VALID_CATEGORIES[cats.index(cat)]

        label, ok3 = QInputDialog.getText(
            self, "Display Label",
            "Human-readable label (e.g. 'Super Archer'):",
            text=name.replace("_", " ").title(),
        )
        if not ok3 or not label.strip():
            label = name.replace("_", " ").title()

        register_asset(name, cat_key, label.strip())
        log.info("Custom asset added: '%s' in '%s'.", name, cat_key)
        QMessageBox.information(self, "Added", f"Asset '{name}' registered in '{cat}'.")
        self._refresh_tree()
        self.assets_changed.emit()

    def _delete_asset_definition(self):
        key = self._selected_key
        if not key:
            QMessageBox.information(self, "No Selection", "Select an asset first.")
            return
        reply = QMessageBox.question(
            self, "Delete Asset",
            f"Permanently delete '{key}' from the manifest?\n"
            "This also removes the template image if present.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            delete_asset(key)
            self._selected_key = None
            self._refresh_tree()
            self.assets_changed.emit()

    # ═══════════════════════════════════════════════════════════════════
    #  Capture / Upload / Delete Image
    # ═══════════════════════════════════════════════════════════════════

    def _on_capture(self):
        key = self._selected_key
        if not key:
            return
        catalogue = get_full_asset_catalogue()
        if key not in catalogue:
            return
        category, label, _ = catalogue[key]
        dlg = CaptureDialog(f"{label} ({key})", self)
        if dlg.exec_() == QDialog.Accepted:
            crop = dlg.get_crop()
            if crop is not None:
                save_template(key, crop, category)
                QMessageBox.information(self, "Saved", f"'{label}' captured!")
                self._refresh_tree()
                self.assets_changed.emit()

    def _on_upload(self):
        key = self._selected_key
        if not key:
            return
        catalogue = get_full_asset_catalogue()
        if key not in catalogue:
            return
        category, label, _ = catalogue[key]
        path, _ = QFileDialog.getOpenFileName(
            self, f"Upload for '{label}'", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All (*)",
        )
        if path:
            dest = import_template_from_file(key, path, category)
            if dest:
                QMessageBox.information(self, "Imported", f"'{label}' imported!")
                self._refresh_tree()
                self.assets_changed.emit()
            else:
                QMessageBox.warning(self, "Error", "Import failed.")

    def _on_delete(self):
        key = self._selected_key
        if not key:
            return
        catalogue = get_full_asset_catalogue()
        if key not in catalogue:
            return
        _, label, _ = catalogue[key]
        if QMessageBox.question(self, "Remove Image", f"Remove image for '{label}'?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            delete_template(key)
            self._refresh_tree()
            self.assets_changed.emit()

    def _show_preview(self, image: np.ndarray):
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch*w, QImage.Format_RGB888)
        px = QPixmap.fromImage(qimg)
        self._preview.setPixmap(
            px.scaled(self._preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def is_ready(self) -> bool:
        r, _ = get_sequence_readiness(self._hv_sequence, self._bb_sequence)
        return r
