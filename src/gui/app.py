import os
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from utils.app_info import APP_NAME
from utils.resources import asset_path

from .main_window import MainWindow

STYLE = """
QLabel#Title { font-size: 22px; font-weight: 600; }
QLabel#Strong { font-weight: 600; }
QLabel#Muted, QLabel#Path { color: palette(placeholder-text); }
QLabel#Status[kind="success"] { color: #2e9d50; font-weight: 600; }
QLabel#Status[kind="error"] { color: #d64541; font-weight: 600; }
QFrame#Card { border: 1px solid palette(mid); border-radius: 12px; background: palette(base); }
QFrame#DropZone { border: 2px dashed palette(mid); border-radius: 16px; background: palette(base); }
QFrame#DropZone[hover="true"] { border-color: #e5534b; background: palette(alternate-base); }
QLabel#DropGlyph { font-size: 44px; color: #e5534b; }
QLabel#DropTitle { font-size: 18px; font-weight: 600; }
QListWidget#ImageList { border: none; background: transparent; outline: none; }
QListWidget#ImageList::item { padding: 6px; border-radius: 8px; }
QListWidget#ImageList::item:selected { background: palette(highlight); color: palette(highlighted-text); }
QPushButton#Primary { background: #e5534b; color: white; border: none; border-radius: 7px;
                      padding: 7px 18px; font-weight: 600; }
QPushButton#Primary:hover { background: #d9443c; }
QPushButton#Primary:pressed { background: #c23a33; }
QPushButton#Primary:disabled { background: palette(mid); color: palette(placeholder-text); }
QProgressBar { border: none; border-radius: 3px; background: palette(mid); }
QProgressBar::chunk { border-radius: 3px; background: #e5534b; }
"""


def use_headless_platform() -> None:
    """Offscreen Qt shares the system fonts on macOS and Linux, but on Windows it ships none and draws every glyph
    as a box. The native Windows platform needs no display server, so headless runs keep it there."""
    if sys.platform != "win32":
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def create_app(argv: list[str]) -> QApplication:
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setWindowIcon(QIcon(str(asset_path("icon.png"))))
    app.setStyleSheet(STYLE)
    return app


def run() -> int:
    app = create_app(sys.argv)
    window = MainWindow()
    window.show()
    code = app.exec()
    del window
    return code
