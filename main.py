"""
CoC Bot — Clash of Clans Automation
====================================

Entry point for the PyQt5 application.
Initializes the logging system, applies the dark theme, and launches
the MainWindow.
"""

import sys
import os

# Ensure project root is on the path so relative imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtGui import QFont

from core.logger import BotLogger
from ui.styles import DARK_THEME_QSS
from ui.main_window import MainWindow


def main() -> None:
    # 1. Initialize the global logger FIRST (before any other module logs)
    BotLogger.setup()
    log = BotLogger.get("main")
    log.info("=" * 60)
    log.info("  CoC Bot — Clash of Clans Automation")
    log.info("  Starting application…")
    log.info("=" * 60)

    # 2. Create the Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("CoC Bot")
    app.setOrganizationName("CoC Bot")

    # 3. Apply global dark theme
    app.setStyleSheet(DARK_THEME_QSS)
    log.info("Dark theme applied.")

    # 4. Set a clean default font
    font = QFont("Segoe UI", 11)
    app.setFont(font)

    # 5. Ensure required directories exist
    for d in ("assets/templates", "assets/logs", "profiles", "strategies", "recordings"):
        os.makedirs(d, exist_ok=True)
    log.info("Asset directories verified.")

    # 5b. Verify ADB binary presence
    if not os.path.isfile("2adb.exe"):
        log.critical("2adb.exe not found in project root.")
        QMessageBox.critical(
            None, "Missing ADB",
            "2adb.exe was not found in the project root.\n"
            "Place 2adb.exe next to main.py before running the bot.\n\n"
            "The UI will still open so you can configure settings,\n"
            "but device commands will fail until ADB is present.",
        )

    # 6. Launch the main window
    window = MainWindow()
    window.show()
    log.info("Main window displayed. Ready for user interaction.")

    # 7. Enter the Qt event loop
    exit_code = app.exec_()
    log.info("Application exiting with code %d.", exit_code)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()