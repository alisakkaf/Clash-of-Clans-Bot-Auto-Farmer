"""
Interactive Assist Dialog — "Help Me" popup when the bot gets stuck.

Shown when the bot detects UNKNOWN state for > 20 seconds.
The dialog presents the current screenshot and offers three options:
  1. "Save as New Asset" — draw a bounding box, give it a name
  2. "Manual Tap" — click on the screenshot to send a tap
  3. "Abort to Home" — press Android Back/Home to recover
"""

import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QGroupBox, QMessageBox,
    QDialogButtonBox, QSizePolicy,
)
from PyQt5.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QFont
from PyQt5.QtCore import Qt, QPoint, QRect, pyqtSignal

from core.logger import BotLogger
from vision.template_manager import (
    save_template, register_asset, VALID_CATEGORIES,
)

log = BotLogger.get("assist")


class _AssistCanvas(QLabel):
    """
    Canvas for the assist dialog.  Supports two modes:
      • "tap" mode: single click sends coordinates back
      • "draw" mode: rubber-band box for asset capture
    """

    tap_requested = pyqtSignal(int, int)         # image coords
    region_selected = pyqtSignal(int, int, int, int)  # x, y, w, h in image coords

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(640, 360)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("border: 1px solid #0f3460; background: #0d0d1a;")
        self._original: np.ndarray | None = None
        self._pixmap: QPixmap | None = None
        self._scaled_pixmap: QPixmap | None = None
        self._mode = "tap"  # "tap" or "draw"
        self._drawing = False
        self._start = QPoint()
        self._end = QPoint()
        self._offset_x = 0
        self._offset_y = 0

    def set_image(self, image: np.ndarray) -> None:
        self._original = image.copy()
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        self._pixmap = QPixmap.fromImage(qimg)
        self._refresh()

    def set_mode(self, mode: str) -> None:
        self._mode = mode

    def get_crop(self, x, y, w, h) -> np.ndarray | None:
        if self._original is None:
            return None
        ih, iw = self._original.shape[:2]
        x, y = max(0, min(x, iw-1)), max(0, min(y, ih-1))
        w, h = min(w, iw-x), min(h, ih-y)
        if w <= 0 or h <= 0:
            return None
        return self._original[y:y+h, x:x+w].copy()

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton or self._pixmap is None:
            return
        if self._mode == "draw":
            self._drawing = True
            self._start = e.pos()
            self._end = e.pos()
        elif self._mode == "tap":
            ix, iy = self._widget_to_img(e.pos())
            if ix is not None:
                self.tap_requested.emit(ix, iy)

    def mouseMoveEvent(self, e):
        if self._drawing:
            self._end = e.pos()
            self._refresh()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self._drawing:
            self._drawing = False
            self._end = e.pos()
            self._refresh()
            self._emit_region()

    def _widget_to_img(self, pos: QPoint) -> tuple[int | None, int | None]:
        if self._scaled_pixmap is None or self._original is None:
            return None, None
        dw, dh = self._scaled_pixmap.width(), self._scaled_pixmap.height()
        oh, ow = self._original.shape[:2]
        if dw == 0 or dh == 0:
            return None, None
        ix = int((pos.x() - self._offset_x) * ow / dw)
        iy = int((pos.y() - self._offset_y) * oh / dh)
        ix = max(0, min(ix, ow - 1))
        iy = max(0, min(iy, oh - 1))
        return ix, iy

    def _refresh(self):
        if self._pixmap is None:
            return
        scaled = self._pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._scaled_pixmap = scaled
        self._offset_x = (self.width() - scaled.width()) // 2
        self._offset_y = (self.height() - scaled.height()) // 2
        disp = scaled.copy()
        if self._drawing and self._start != self._end:
            p = QPainter(disp)
            p.setPen(QPen(QColor("#e94560"), 2))
            adj_s = QPoint(self._start.x() - self._offset_x, self._start.y() - self._offset_y)
            adj_e = QPoint(self._end.x() - self._offset_x, self._end.y() - self._offset_y)
            p.drawRect(QRect(adj_s, adj_e).normalized())
            p.end()
        self.setPixmap(disp)

    def _emit_region(self):
        if self._scaled_pixmap is None or self._original is None:
            return
        dw, dh = self._scaled_pixmap.width(), self._scaled_pixmap.height()
        oh, ow = self._original.shape[:2]
        if dw == 0 or dh == 0:
            return
        sx, sy = ow / dw, oh / dh
        r = QRect(self._start, self._end).normalized()
        ix = int((r.x() - self._offset_x) * sx)
        iy = int((r.y() - self._offset_y) * sy)
        iw = int(r.width() * sx)
        ih = int(r.height() * sy)
        ix, iy = max(0, ix), max(0, iy)
        iw = min(iw, ow - ix)
        ih = min(ih, oh - iy)
        if iw > 3 and ih > 3:
            self.region_selected.emit(ix, iy, iw, ih)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._refresh()


# ═══════════════════════════════════════════════════════════════════════
#  Result Enum
# ═══════════════════════════════════════════════════════════════════════

class AssistAction:
    NONE = "none"
    SAVED_ASSET = "saved_asset"
    MANUAL_TAP = "manual_tap"
    ABORT_HOME = "abort_home"


class InteractiveAssistDialog(QDialog):
    """
    "Help Me" dialog shown when the bot is stuck.

    Returns (action, data) via get_result():
      • ("saved_asset", asset_key)
      • ("manual_tap", (x, y))
      • ("abort_home", None)
      • ("none", None) if cancelled
    """

    def __init__(self, screenshot: np.ndarray, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚠ Bot Needs Help — Interactive Assist")
        self.setMinimumSize(900, 600)
        self.setModal(True)
        self._screenshot = screenshot
        self._result_action = AssistAction.NONE
        self._result_data = None
        self._crop: np.ndarray | None = None
        self._tap_coords: tuple[int, int] | None = None
        self._last_region: tuple[int, int, int, int] | None = None  # V6: for calibration

        self._init_ui()
        self._canvas.set_image(screenshot)

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Warning header
        hdr = QLabel("⚠  The bot is stuck or on an unknown screen.")
        hdr.setFont(QFont("Segoe UI", 14, QFont.Bold))
        hdr.setStyleSheet("color: #e94560; padding: 8px;")
        hdr.setAlignment(Qt.AlignCenter)
        layout.addWidget(hdr)

        info = QLabel("Choose an action below. The bot is PAUSED until you respond.")
        info.setAlignment(Qt.AlignCenter)
        info.setStyleSheet("color: #9e9e9e;")
        layout.addWidget(info)

        # Canvas
        self._canvas = _AssistCanvas()
        self._canvas.tap_requested.connect(self._on_tap)
        self._canvas.region_selected.connect(self._on_region)
        layout.addWidget(self._canvas)

        self._status = QLabel("Select an option below.")
        self._status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._status)

        # ── Option 1: Save as New Asset ──────────────────────────────────
        asset_group = QGroupBox("Option 1: This is a New Asset (Draw Box + Save)")
        asset_layout = QHBoxLayout()

        self._draw_btn = QPushButton("✏  Enable Drawing Mode")
        self._draw_btn.setMinimumHeight(34)
        self._draw_btn.clicked.connect(self._enable_draw)
        asset_layout.addWidget(self._draw_btn)

        asset_layout.addWidget(QLabel("Name:"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. new_confirm_btn")
        self._name_edit.setMinimumWidth(150)
        asset_layout.addWidget(self._name_edit)

        asset_layout.addWidget(QLabel("Category:"))
        self._cat_combo = QComboBox()
        self._cat_combo.addItems([c.replace("_", " ").title() for c in VALID_CATEGORIES])
        asset_layout.addWidget(self._cat_combo)

        self._save_asset_btn = QPushButton("💾  Save Asset")
        self._save_asset_btn.setMinimumHeight(34)
        self._save_asset_btn.setEnabled(False)
        self._save_asset_btn.clicked.connect(self._save_asset)
        asset_layout.addWidget(self._save_asset_btn)

        asset_group.setLayout(asset_layout)
        layout.addWidget(asset_group)

        # ── Option 2 & 3 ───────────────────────────────────────────────
        btn_row = QHBoxLayout()

        self._tap_btn = QPushButton("👆  Option 2: Manual Tap (click on screenshot)")
        self._tap_btn.setMinimumHeight(36)
        self._tap_btn.clicked.connect(self._enable_tap)
        btn_row.addWidget(self._tap_btn)

        self._abort_btn = QPushButton("🏠  Option 3: Abort to Home")
        self._abort_btn.setMinimumHeight(36)
        self._abort_btn.clicked.connect(self._abort_home)
        btn_row.addWidget(self._abort_btn)

        layout.addLayout(btn_row)

        # Cancel
        cancel_btn = QPushButton("Cancel (keep bot paused)")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

    def _enable_draw(self):
        self._canvas.set_mode("draw")
        self._status.setText("Draw a bounding box around the element, then fill in Name + Category and Save.")

    def _enable_tap(self):
        self._canvas.set_mode("tap")
        self._status.setText("Click on the screenshot where you want the bot to tap.")

    def _on_tap(self, x: int, y: int):
        self._tap_coords = (x, y)
        self._result_action = AssistAction.MANUAL_TAP
        self._result_data = (x, y)
        self._status.setText(f"Manual tap at ({x}, {y}). Closing…")
        log.info("Interactive Assist: manual tap at (%d, %d).", x, y)
        self.accept()

    def _on_region(self, x, y, w, h):
        self._crop = self._canvas.get_crop(x, y, w, h)
        self._last_region = (x, y, w, h)  # V6: store for calibration
        if self._crop is not None:
            self._save_asset_btn.setEnabled(True)
            self._status.setText(f"Region selected: x={x} y={y} w={w} h={h}. Enter a name and save.")

    def _save_asset(self):
        name = self._name_edit.text().strip().lower().replace(" ", "_")
        if not name:
            QMessageBox.warning(self, "No Name", "Enter an asset name.")
            return
        if self._crop is None:
            QMessageBox.warning(self, "No Region", "Draw a box first.")
            return
        cat_index = self._cat_combo.currentIndex()
        category = VALID_CATEGORIES[cat_index] if cat_index < len(VALID_CATEGORIES) else "custom"
        path = save_template(name, self._crop, category)
        log.info("Interactive Assist: saved asset '%s' -> %s", name, path)
        self._result_action = AssistAction.SAVED_ASSET
        self._result_data = name
        QMessageBox.information(self, "Saved", f"Asset '{name}' saved!")
        self.accept()

    def _abort_home(self):
        self._result_action = AssistAction.ABORT_HOME
        self._result_data = None
        log.info("Interactive Assist: user chose Abort to Home.")
        self.accept()

    def get_result(self) -> tuple[str, object]:
        return self._result_action, self._result_data
