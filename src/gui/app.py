import os
import sys

from PySide6.QtCore import QEvent
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from utils.app_info import APP_NAME
from utils.resources import asset_path

from .main_window import MainWindow
from .style import is_dark, stylesheet


def use_headless_platform() -> None:
    """Offscreen Qt shares the system fonts on macOS and Linux, but on Windows it ships none and draws every glyph
    as a box. The native Windows platform needs no display server, so headless runs keep it there."""
    if sys.platform != "win32":
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class Application(QApplication):
    """Restyles itself when the system switches between light and dark."""

    def __init__(self, argv: list[str]):
        super().__init__(argv)
        self._dark: bool | None = None
        self.styleHints().colorSchemeChanged.connect(self._apply_style)
        self._apply_style()

    def _apply_style(self) -> None:
        dark = is_dark(self.palette())
        if dark != self._dark:
            self._dark = dark
            self.setStyleSheet(stylesheet(self.palette()))

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.ApplicationPaletteChange:
            self._apply_style()
        return super().event(event)


def create_app(argv: list[str]) -> Application:
    app = Application(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setWindowIcon(QIcon(str(asset_path("icon.png"))))
    return app


def run() -> int:
    app = create_app(sys.argv)
    window = MainWindow()
    window.show()
    code = app.exec()
    del window
    return code
