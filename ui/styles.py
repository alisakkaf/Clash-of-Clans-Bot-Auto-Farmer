"""
Dark-theme QSS stylesheet — Clash of Clans inspired palette.

Colours:
  • Background:  #1a1a2e  (deep navy)
  • Surface:     #16213e  (dark blue-grey)
  • Card/Panel:  #0f3460  (indigo)
  • Accent:      #e9b44c  (gold/amber — CoC theme)
  • Accent 2:    #e94560  (red, for warnings)
  • Text:        #e0e0e0  (light grey)
  • Text muted:  #9e9e9e
"""

DARK_THEME_QSS = """
/* ── Global ─────────────────────────────────────────────────────────── */
QWidget {
    background-color: #1a1a2e;
    color: #e0e0e0;
    font-family: "Segoe UI", "Consolas", sans-serif;
    font-size: 13px;
}

/* ── Main Window ────────────────────────────────────────────────────── */
QMainWindow {
    background-color: #1a1a2e;
}

/* ── Tab Widget ─────────────────────────────────────────────────────── */
QTabWidget::pane {
    border: 1px solid #0f3460;
    border-radius: 4px;
    background-color: #16213e;
}

QTabBar::tab {
    background-color: #16213e;
    color: #9e9e9e;
    padding: 10px 24px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    min-width: 120px;
    font-weight: bold;
}

QTabBar::tab:selected {
    background-color: #0f3460;
    color: #e9b44c;
    border-bottom: 3px solid #e9b44c;
}

QTabBar::tab:hover:!selected {
    background-color: #0f3460;
    color: #e0e0e0;
}

/* ── Buttons ────────────────────────────────────────────────────────── */
QPushButton {
    background-color: #0f3460;
    color: #e9b44c;
    border: 1px solid #e9b44c;
    border-radius: 6px;
    padding: 6px 18px;
    font-weight: bold;
    min-height: 30px;
}

QPushButton:hover {
    background-color: #e9b44c;
    color: #1a1a2e;
}

QPushButton:pressed {
    background-color: #d4a23a;
    color: #1a1a2e;
}

QPushButton:disabled {
    background-color: #2a2a3e;
    color: #555;
    border-color: #444;
}

QPushButton#start_button {
    background-color: #2e7d32;
    border-color: #4caf50;
    color: #ffffff;
    font-size: 15px;
    min-height: 36px;
}

QPushButton#start_button:hover {
    background-color: #4caf50;
}

QPushButton#stop_button {
    background-color: #c62828;
    border-color: #e94560;
    color: #ffffff;
    font-size: 15px;
    min-height: 36px;
}

QPushButton#stop_button:hover {
    background-color: #e94560;
}

/* ── SpinBox / ComboBox ─────────────────────────────────────────────── */
QSpinBox, QDoubleSpinBox {
    background-color: #16213e;
    color: #e9b44c;
    border: 1px solid #0f3460;
    border-radius: 4px;
    padding: 4px 8px;
    min-width: 110px;
    min-height: 28px;
    font-size: 13px;
}

QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    background-color: #0f3460;
    border: none;
    width: 20px;
}

QComboBox {
    background-color: #16213e;
    color: #e0e0e0;
    border: 1px solid #0f3460;
    border-radius: 4px;
    padding: 4px 10px;
    min-width: 140px;
    min-height: 28px;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
    background-color: #0f3460;
}

QComboBox QAbstractItemView {
    background-color: #16213e;
    color: #e0e0e0;
    selection-background-color: #0f3460;
    selection-color: #e9b44c;
}

/* ── CheckBox ───────────────────────────────────────────────────────── */
QCheckBox {
    spacing: 8px;
    color: #e0e0e0;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 3px;
    border: 1px solid #0f3460;
    background-color: #16213e;
}

QCheckBox::indicator:checked {
    background-color: #e9b44c;
    border-color: #e9b44c;
}

/* ── Labels ─────────────────────────────────────────────────────────── */
QLabel {
    color: #e0e0e0;
}

QLabel#header_label {
    font-size: 18px;
    font-weight: bold;
    color: #e9b44c;
    padding: 6px;
}

QLabel#status_label {
    color: #9e9e9e;
    font-size: 12px;
}

/* ── GroupBox ────────────────────────────────────────────────────────── */
QGroupBox {
    border: 1px solid #0f3460;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 18px;
    font-weight: bold;
    color: #e9b44c;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}

/* ── ScrollBar ──────────────────────────────────────────────────────── */
QScrollBar:vertical {
    background-color: #1a1a2e;
    width: 10px;
    border-radius: 5px;
}

QScrollBar::handle:vertical {
    background-color: #0f3460;
    border-radius: 5px;
    min-height: 30px;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background-color: #1a1a2e;
    height: 10px;
    border-radius: 5px;
}

QScrollBar::handle:horizontal {
    background-color: #0f3460;
    border-radius: 5px;
    min-width: 30px;
}

/* ── TextEdit (Console) ─────────────────────────────────────────────── */
QTextEdit {
    background-color: #0d0d1a;
    color: #b0b0b0;
    border: 1px solid #0f3460;
    border-radius: 4px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
    padding: 4px;
}

/* ── List Widget ────────────────────────────────────────────────────── */
QListWidget {
    background-color: #16213e;
    color: #e0e0e0;
    border: 1px solid #0f3460;
    border-radius: 4px;
}

QListWidget::item:selected {
    background-color: #0f3460;
    color: #e9b44c;
}

QListWidget::item:hover {
    background-color: #1c2b4d;
}

/* ── Splitter ───────────────────────────────────────────────────────── */
QSplitter::handle {
    background-color: #0f3460;
    height: 3px;
}

/* ── StatusBar ──────────────────────────────────────────────────────── */
QStatusBar {
    background-color: #16213e;
    color: #9e9e9e;
    border-top: 1px solid #0f3460;
    font-size: 12px;
}

/* ── ToolTip ────────────────────────────────────────────────────────── */
QToolTip {
    background-color: #0f3460;
    color: #e9b44c;
    border: 1px solid #e9b44c;
    padding: 4px;
    border-radius: 4px;
}

/* ── ProgressBar ────────────────────────────────────────────────────── */
QProgressBar {
    background-color: #16213e;
    border: 1px solid #0f3460;
    border-radius: 4px;
    text-align: center;
    color: #e0e0e0;
    min-height: 18px;
}

QProgressBar::chunk {
    background-color: #e9b44c;
    border-radius: 3px;
}

/* ── Orderable List (HV/BB drag-drop pickers) ───────────────────────── */
QListWidget#orderable_list {
    background-color: #16213e;
    border: 1px solid #0f3460;
    border-radius: 4px;
}

QListWidget#orderable_list::item {
    padding: 8px;
    border-bottom: 1px solid #0d0d1a;
}

QListWidget#orderable_list::item:hover {
    background-color: #1c2b4d;
}

QListWidget#orderable_list::item:selected {
    background-color: #0f3460;
    color: #e9b44c;
}

/* ── Status pills ───────────────────────────────────────────────────── */
QLabel#preset_pill {
    color: #e9b44c;
    background: #0f3460;
    border: 1px solid #e9b44c;
    border-radius: 10px;
    padding: 2px 10px;
    font-weight: bold;
}

QLabel#ready_pill_ok {
    color: #4caf50;
    background: #1a2e1a;
    border-radius: 10px;
    padding: 2px 10px;
    font-weight: bold;
}

QLabel#ready_pill_bad {
    color: #e94560;
    background: #2e1a1a;
    border-radius: 10px;
    padding: 2px 10px;
    font-weight: bold;
}
"""
