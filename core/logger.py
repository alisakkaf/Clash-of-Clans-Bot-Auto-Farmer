"""
Comprehensive logging system with dual output:
  1. Real-time CMD console output (stdout)
  2. Qt signal emission for the GUI console widget

Every action, state change, detection, and error is logged with timestamps.
"""

import logging
import sys
from datetime import datetime

from PyQt5.QtCore import QObject, pyqtSignal


class _QtLogSignalEmitter(QObject):
    """Emits a Qt signal for every log record so the GUI console can receive it."""
    log_message = pyqtSignal(str, str)  # (level_name, formatted_message)


class QtSignalHandler(logging.Handler):
    """Custom logging handler that emits log records as Qt signals."""

    def __init__(self):
        super().__init__()
        self.emitter = _QtLogSignalEmitter()

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            self.emitter.log_message.emit(record.levelname, msg)
        except Exception:
            self.handleError(record)


class BotLogger:
    """
    Singleton-style logger for the entire application.
    Call ``BotLogger.setup()`` once at startup, then use
    ``BotLogger.get(name)`` anywhere to get a child logger.
    """

    _qt_handler: QtSignalHandler | None = None
    _initialized: bool = False

    @classmethod
    def setup(cls, level: int = logging.DEBUG) -> None:
        """Initialize the root 'coc_bot' logger with console + Qt handlers."""
        if cls._initialized:
            return

        root = logging.getLogger("coc_bot")
        root.setLevel(level)

        # ── Console handler (CMD / stdout) ──────────────────────────────
        console_fmt = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s",
            datefmt="%H:%M:%S",
        )
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(console_fmt)
        root.addHandler(console_handler)

        # ── Qt signal handler (for GUI console widget) ──────────────────
        cls._qt_handler = QtSignalHandler()
        qt_fmt = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)-8s] %(message)s",
            datefmt="%H:%M:%S",
        )
        cls._qt_handler.setFormatter(qt_fmt)
        root.addHandler(cls._qt_handler)

        cls._initialized = True
        root.info("Logger initialized — console + GUI signal output active.")

    @classmethod
    def get(cls, name: str = "coc_bot") -> logging.Logger:
        """Return a child logger under the 'coc_bot' namespace."""
        return logging.getLogger(f"coc_bot.{name}")

    @classmethod
    def get_qt_handler(cls) -> QtSignalHandler | None:
        """Return the Qt signal handler so the GUI can connect to its signal."""
        return cls._qt_handler
