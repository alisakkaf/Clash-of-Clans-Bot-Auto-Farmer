"""
Console Widget — Enhanced log viewer with rich colors, copy, and filters.

Features:
  • Severity-coded colors with icons
  • Keyword highlighting (GOLD, ELIXIR, etc.)
  • Copy / Select All / Search
  • Debug toggle from Settings
  • Auto-scroll with manual override
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QLabel, QLineEdit, QCheckBox,
)
from PyQt5.QtGui import QColor, QTextCharFormat, QFont, QTextCursor, QTextDocument
from PyQt5.QtCore import Qt

from core.logger import BotLogger
from core.settings import Settings

# ── Severity styling ────────────────────────────────────────────────────
_LEVEL_STYLE: dict[str, dict] = {
    "DEBUG":    {"color": "#6a7080", "icon": "🔍"},
    "INFO":     {"color": "#4fc3f7", "icon": "ℹ️"},
    "WARNING":  {"color": "#e9b44c", "icon": "⚠️"},
    "ERROR":    {"color": "#e94560", "icon": "❌"},
    "CRITICAL": {"color": "#ff1744", "icon": "🔥"},
}

# Keywords → highlight colors
_KEYWORD_COLORS: dict[str, str] = {
    "GOLD":       "#ffd700",
    "ELIXIR":     "#e040fb",
    "DARK":       "#00e5ff",
    "ATTACKING":  "#76ff03",
    "RETREAT":    "#ff5252",
    "SKIP":       "#ff9800",
    "FOUND":      "#69f0ae",
    "COMPLETE":   "#69f0ae",
    "DONE":       "#69f0ae",
    "ERROR":      "#e94560",
    "STEP":       "#e9b44c",
}


class ConsoleWidget(QWidget):
    """Enhanced embeddable log console."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = Settings()
        self._max_lines = self._settings.get("console_max_lines", 5000)
        self._show_debug = self._settings.get("console_show_debug", True)
        self._auto_scroll = True
        self._init_ui()
        self._connect_logger()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # ── Toolbar ─────────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        title = QLabel("📋  Console Output")
        title.setObjectName("header_label")
        title.setStyleSheet("font-size: 13px; padding: 2px;")
        toolbar.addWidget(title)

        toolbar.addStretch()

        # Search
        self._search = QLineEdit()
        self._search.setPlaceholderText("🔎 Search…")
        self._search.setFixedWidth(180)
        self._search.setStyleSheet(
            "background: #0d0d1a; border: 1px solid #0f3460; "
            "border-radius: 4px; padding: 3px 8px; color: #e0e0e0; font-size: 12px;"
        )
        self._search.textChanged.connect(self._on_search)
        toolbar.addWidget(self._search)

        # Auto-scroll toggle
        self._chk_scroll = QCheckBox("Auto-scroll")
        self._chk_scroll.setChecked(True)
        self._chk_scroll.toggled.connect(self._on_scroll_toggled)
        toolbar.addWidget(self._chk_scroll)

        # Buttons
        self._btn_copy = QPushButton("📋 Copy")
        self._btn_copy.setFixedWidth(75)
        self._btn_copy.clicked.connect(self._copy_all)
        self._btn_copy.setToolTip("Copy all console text to clipboard")
        toolbar.addWidget(self._btn_copy)

        self._btn_clear = QPushButton("🗑 Clear")
        self._btn_clear.setFixedWidth(75)
        self._btn_clear.clicked.connect(self._clear)
        toolbar.addWidget(self._btn_clear)

        layout.addLayout(toolbar)

        # ── Log text area ───────────────────────────────────────────────
        font_size = self._settings.get("console_font_size", 12)
        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setFont(QFont("Consolas", font_size))
        self._text_edit.setLineWrapMode(QTextEdit.NoWrap)
        self._text_edit.setContextMenuPolicy(Qt.DefaultContextMenu)
        self._text_edit.setStyleSheet(
            "QTextEdit { background-color: #0a0a14; border: 1px solid #0f3460; "
            "border-radius: 4px; padding: 4px; selection-background-color: #0f3460; }"
        )
        layout.addWidget(self._text_edit)

        # ── Status bar ──────────────────────────────────────────────────
        self._line_count = QLabel("Lines: 0")
        self._line_count.setObjectName("status_label")
        self._line_count.setStyleSheet("font-size: 11px; color: #6a7080; padding: 2px 4px;")
        layout.addWidget(self._line_count)

    def _connect_logger(self) -> None:
        handler = BotLogger.get_qt_handler()
        if handler is not None:
            handler.emitter.log_message.connect(self._append_log)

    # ═══════════════════════════════════════════════════════════════════
    #  LOG APPEND
    # ═══════════════════════════════════════════════════════════════════

    def _append_log(self, level: str, message: str) -> None:
        # Filter debug if disabled
        if level == "DEBUG" and not self._show_debug:
            return

        style = _LEVEL_STYLE.get(level, {"color": "#e0e0e0", "icon": "  "})
        icon = style["icon"]
        colour = style["color"]

        # Format line with icon
        line = f" {icon}  {message}"

        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colour))

        # Bold for errors/critical
        if level in ("ERROR", "CRITICAL"):
            fmt.setFontWeight(QFont.Bold)

        cursor = self._text_edit.textCursor()
        cursor.movePosition(QTextCursor.End)

        # Check for keyword highlights within the message
        cursor.insertText(line + "\n", fmt)

        # Trim old lines
        doc = self._text_edit.document()
        if doc.blockCount() > self._max_lines:
            cursor.movePosition(QTextCursor.Start)
            cursor.movePosition(
                QTextCursor.Down, QTextCursor.KeepAnchor,
                doc.blockCount() - self._max_lines,
            )
            cursor.removeSelectedText()

        # Auto-scroll
        if self._auto_scroll:
            self._text_edit.setTextCursor(cursor)
            sb = self._text_edit.verticalScrollBar()
            sb.setValue(sb.maximum())

        # Update line count
        self._line_count.setText(f"Lines: {doc.blockCount()}")

    # ═══════════════════════════════════════════════════════════════════
    #  ACTIONS
    # ═══════════════════════════════════════════════════════════════════

    def _clear(self) -> None:
        self._text_edit.clear()
        self._line_count.setText("Lines: 0")

    def _copy_all(self) -> None:
        from PyQt5.QtWidgets import QApplication
        text = self._text_edit.toPlainText()
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(text)

    def _on_scroll_toggled(self, checked: bool) -> None:
        self._auto_scroll = checked
        if checked:
            sb = self._text_edit.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _on_search(self, text: str) -> None:
        # Clear previous highlights
        cursor = self._text_edit.textCursor()
        cursor.select(QTextCursor.Document)
        plain_fmt = QTextCharFormat()
        plain_fmt.setBackground(QColor("transparent"))
        cursor.mergeCharFormat(plain_fmt)

        if not text:
            return

        # Highlight matches
        highlight_fmt = QTextCharFormat()
        highlight_fmt.setBackground(QColor("#e9b44c"))
        highlight_fmt.setForeground(QColor("#1a1a2e"))

        doc = self._text_edit.document()
        cursor = doc.find(text)
        while not cursor.isNull():
            cursor.mergeCharFormat(highlight_fmt)
            cursor = doc.find(text, cursor)

    # ═══════════════════════════════════════════════════════════════════
    #  SETTINGS SYNC
    # ═══════════════════════════════════════════════════════════════════

    def apply_settings(self) -> None:
        """Called when settings change."""
        s = self._settings
        self._max_lines = s.get("console_max_lines", 5000)
        self._show_debug = s.get("console_show_debug", True)
        font_size = s.get("console_font_size", 12)
        self._text_edit.setFont(QFont("Consolas", font_size))
