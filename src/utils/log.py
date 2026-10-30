"""A local log of conversion failures with their tracebacks, for diagnosing a report. It never leaves the computer."""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QStandardPaths

from .app_info import APP_NAME


def log_path() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / APP_NAME / "papyr.log"
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)) / "papyr.log"


def start_logging() -> None:
    """Write warnings and errors to the log file. Papyr keeps running without a log if the folder can't be made."""
    path = log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    except OSError:
        return
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger("papyr")
    root.addHandler(handler)
    root.setLevel(logging.WARNING)
