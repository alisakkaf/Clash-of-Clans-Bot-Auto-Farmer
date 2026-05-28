"""
Training Mode Tab — visual template training interface.

Features:
  • "Take Screenshot" button → ADB screencap → display on a canvas
  • Mouse-drawn red bounding box (rubber-band selection)
  • Save cropped region as a named template
  • Template list sidebar with preview thumbnails and delete option
  • Category selector (Buttons, Troops, Buildings, Popups, Misc)
"""

import os

import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QLineEdit, QComboBox, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QSplitter,
    QSizePolicy,
)
from PyQt5.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QIcon
from PyQt5.QtCore import Qt, QRect, QPoint, pyqtSignal

from core.logger import BotLogger
from core.adb_handler import screencap
from vision.template_manager import (
    save_template, list_templates, delete_template, get_all_categories,
)

log = BotLogger.get("training")


class ScreenCanvas(QLabel):
    """
    Custom QLabel that displays a screenshot and lets the user draw
    a red bounding box via click-drag.

    Coordinate scaling accounts for the centered image offset within
    the QLabel:
      1. scaled pixmap may not fill the label → centering offset
      2. mouse coords are translated to image-relative by subtracting offset
      3. then scaled by (original_size / displayed_size)
    """

    region_selected = pyqtSignal(int, int, int, int)  # x, y, w, h (in image coords)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(400, 300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("border: 1px solid #0f3460; background: #0d0d1a;")

        self._pixmap: QPixmap | None = None
        self._original_image: np.ndarray | None = None
        self._scaled_pixmap: QPixmap | None = None
        self._drawing = False
        self._start_point = QPoint()
        self._end_point = QPoint()
        self._image_offset_x = 0
        self._image_offset_y = 0

    def set_image(self, image: np.ndarray) -> None:
        """Display a BGR numpy array on the canvas."""
        self._original_image = image.copy()
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        self._pixmap = QPixmap.fromImage(qimg)
        self._update_display()

    def get_crop(self, x: int, y: int, w: int, h: int) -> np.ndarray | None:
        """Return the cropped region from the original image."""
        if self._original_image is None:
            return None
        img_h, img_w = self._original_image.shape[:2]
        x = max(0, min(x, img_w - 1))
        y = max(0, min(y, img_h - 1))
        w = min(w, img_w - x)
        h = min(h, img_h - y)
        if w <= 0 or h <= 0:
            return None
        return self._original_image[y : y + h, x : x + w].copy()

    # ── Mouse Events ────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._pixmap:
            self._drawing = True
            self._start_point = event.pos()
            self._end_point = event.pos()

    def mouseMoveEvent(self, event):
        if self._drawing:
            self._end_point = event.pos()
            self._update_display()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drawing:
            self._drawing = False
            self._end_point = event.pos()
            self._update_display()
            self._emit_selection()

    # ── Drawing ─────────────────────────────────────────────────────────

    def _update_display(self) -> None:
        if self._pixmap is None:
            return

        scaled = self._pixmap.scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        self._scaled_pixmap = scaled

        # Centering offset within the label
        self._image_offset_x = (self.width() - scaled.width()) // 2
        self._image_offset_y = (self.height() - scaled.height()) // 2

        display = scaled.copy()

        if self._start_point != self._end_point:
            painter = QPainter(display)
            pen = QPen(QColor("#e94560"), 2, Qt.SolidLine)
            painter.setPen(pen)
            # Adjust mouse coords to image-relative before drawing
            adj_start = QPoint(
                self._start_point.x() - self._image_offset_x,
                self._start_point.y() - self._image_offset_y,
            )
            adj_end = QPoint(
                self._end_point.x() - self._image_offset_x,
                self._end_point.y() - self._image_offset_y,
            )
            painter.drawRect(QRect(adj_start, adj_end).normalized())
            painter.end()

        self.setPixmap(display)

    def _emit_selection(self) -> None:
        """Convert widget coordinates to original image coordinates and emit."""
        if self._pixmap is None or self._original_image is None:
            return
        if self._scaled_pixmap is None:
            return

        disp_w = self._scaled_pixmap.width()
        disp_h = self._scaled_pixmap.height()
        orig_h, orig_w = self._original_image.shape[:2]

        if disp_w == 0 or disp_h == 0:
            return

        scale_x = orig_w / disp_w
        scale_y = orig_h / disp_h

        # Convert label-relative mouse coords to image-relative
        rect = QRect(self._start_point, self._end_point).normalized()
        img_x = int((rect.x() - self._image_offset_x) * scale_x)
        img_y = int((rect.y() - self._image_offset_y) * scale_y)
        img_w = int(rect.width() * scale_x)
        img_h = int(rect.height() * scale_y)

        # Clamp to image bounds
        img_x = max(0, min(img_x, orig_w - 1))
        img_y = max(0, min(img_y, orig_h - 1))
        img_w = max(0, min(img_w, orig_w - img_x))
        img_h = max(0, min(img_h, orig_h - img_y))

        if img_w > 5 and img_h > 5:
            log.info("Region selected: x=%d y=%d w=%d h=%d", img_x, img_y, img_w, img_h)
            self.region_selected.emit(img_x, img_y, img_w, img_h)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_display()


class TrainingModeTab(QWidget):
    """Visual interface for training OpenCV templates from screenshots."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_region: tuple[int, int, int, int] | None = None
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QHBoxLayout(self)

        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # ── Left Panel: Canvas ──────────────────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)

        # Toolbar
        toolbar = QHBoxLayout()
        self._screenshot_btn = QPushButton("📷  Take Screenshot")
        self._screenshot_btn.setMinimumHeight(36)
        self._screenshot_btn.clicked.connect(self._take_screenshot)
        toolbar.addWidget(self._screenshot_btn)
        toolbar.addStretch()
        left_layout.addLayout(toolbar)

        # Canvas
        self._canvas = ScreenCanvas()
        self._canvas.region_selected.connect(self._on_region_selected)
        left_layout.addWidget(self._canvas)

        # Selection info
        self._selection_label = QLabel("Draw a bounding box on the screenshot above.")
        self._selection_label.setObjectName("status_label")
        left_layout.addWidget(self._selection_label)

        splitter.addWidget(left)

        # ── Right Panel: Save & Template List ───────────────────────────
        right = QWidget()
        right.setMaximumWidth(350)
        right_layout = QVBoxLayout(right)

        # Save controls
        save_group = QGroupBox("Save Template")
        save_grid = QGridLayout()

        save_grid.addWidget(QLabel("Name:"), 0, 0)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. next_button")
        save_grid.addWidget(self._name_edit, 0, 1)

        save_grid.addWidget(QLabel("Category:"), 1, 0)
        self._category_combo = QComboBox()
        self._category_combo.addItems([c.replace('_', ' ').title() for c in get_all_categories()])
        save_grid.addWidget(self._category_combo, 1, 1)

        self._save_btn = QPushButton("💾  Save Template")
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._save_template)
        save_grid.addWidget(self._save_btn, 2, 0, 1, 2)

        save_group.setLayout(save_grid)
        right_layout.addWidget(save_group)

        # Preview
        self._preview_label = QLabel()
        self._preview_label.setAlignment(Qt.AlignCenter)
        self._preview_label.setMinimumHeight(100)
        self._preview_label.setStyleSheet("border: 1px solid #0f3460; background: #0d0d1a;")
        right_layout.addWidget(self._preview_label)

        # Template list
        list_group = QGroupBox("Saved Templates")
        list_layout = QVBoxLayout()

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter:"))
        self._filter_combo = QComboBox()
        self._filter_combo.addItems(["All"] + [c.replace('_', ' ').title() for c in get_all_categories()])
        self._filter_combo.currentTextChanged.connect(self._refresh_list)
        filter_layout.addWidget(self._filter_combo)
        list_layout.addLayout(filter_layout)

        self._template_list = QListWidget()
        self._template_list.currentItemChanged.connect(self._on_template_selected)
        list_layout.addWidget(self._template_list)

        self._delete_btn = QPushButton("🗑  Delete Selected")
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._delete_template)
        list_layout.addWidget(self._delete_btn)

        list_group.setLayout(list_layout)
        right_layout.addWidget(list_group)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        # Initial load
        self._refresh_list()

    # ── Screenshot ──────────────────────────────────────────────────────

    def _take_screenshot(self) -> None:
        log.info("Taking screenshot via ADB…")
        img = screencap()
        if img is None:
            QMessageBox.warning(
                self, "Screenshot Failed",
                "Could not capture screen. Make sure a device is connected via 2adb.exe.",
            )
            return
        self._canvas.set_image(img)
        self._selection_label.setText("Screenshot captured. Draw a bounding box to select a region.")
        log.info("Screenshot displayed on canvas.")

    # ── Region Selection ────────────────────────────────────────────────

    def _on_region_selected(self, x: int, y: int, w: int, h: int) -> None:
        self._selected_region = (x, y, w, h)
        self._save_btn.setEnabled(True)
        self._selection_label.setText(
            f"Selected region: x={x}, y={y}, w={w}, h={h}"
        )

        # Show preview
        crop = self._canvas.get_crop(x, y, w, h)
        if crop is not None:
            self._show_preview(crop)

    # ── Save Template ───────────────────────────────────────────────────

    def _save_template(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "No Name", "Please enter a template name.")
            return

        if self._selected_region is None:
            QMessageBox.warning(self, "No Region", "Please draw a bounding box first.")
            return

        x, y, w, h = self._selected_region
        crop = self._canvas.get_crop(x, y, w, h)
        if crop is None:
            QMessageBox.warning(self, "Crop Failed", "Could not extract the selected region.")
            return

        category = self._category_combo.currentText().lower()
        path = save_template(name, crop, category)
        log.info("Template '%s' saved to %s", name, path)

        QMessageBox.information(
            self, "Template Saved",
            f"Template '{name}' saved successfully!\n{path}",
        )

        self._name_edit.clear()
        self._selected_region = None
        self._save_btn.setEnabled(False)
        self._refresh_list()

    # ── Template List ───────────────────────────────────────────────────

    def _refresh_list(self) -> None:
        self._template_list.clear()
        filter_cat = self._filter_combo.currentText().lower()
        cat = None if filter_cat == "all" else filter_cat

        templates = list_templates(cat)
        for tmpl in templates:
            name = tmpl["name"]
            cat_text = tmpl.get("category", "misc")
            item_text = f"{name}  [{cat_text}]  ({tmpl.get('width', '?')}×{tmpl.get('height', '?')})"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, name)

            # Try to load a small icon
            filepath = tmpl.get("file", "")
            if os.path.isfile(filepath):
                icon = QIcon(filepath)
                item.setIcon(icon)

            self._template_list.addItem(item)

        self._delete_btn.setEnabled(False)

    def _on_template_selected(self, current: QListWidgetItem, previous) -> None:
        if current is None:
            self._delete_btn.setEnabled(False)
            return
        self._delete_btn.setEnabled(True)

        # Show preview
        name = current.data(Qt.UserRole)
        from vision.template_manager import load_template as _load
        img = _load(name)
        if img is not None:
            self._show_preview(img)

    def _delete_template(self) -> None:
        item = self._template_list.currentItem()
        if item is None:
            return
        name = item.data(Qt.UserRole)
        reply = QMessageBox.question(
            self, "Delete Template",
            f"Delete template '{name}'? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            delete_template(name)
            log.info("Template '%s' deleted.", name)
            self._refresh_list()

    # ── Preview ─────────────────────────────────────────────────────────

    def _show_preview(self, image: np.ndarray) -> None:
        """Display a small preview of an image in the preview label."""
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)
        scaled = pixmap.scaled(
            self._preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        self._preview_label.setPixmap(scaled)
