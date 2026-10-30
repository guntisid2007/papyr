import os
import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QEvent
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from utils.app_info import APP_NAME
from utils.log import start_logging
from utils.resources import asset_path

from .main_window import MainWindow
from .theme import app_font, stylesheet, system_is_dark, current

PathHandler = Callable[[list[Path]], None]


def use_headless_platform() -> None:
    """Offscreen Qt shares the system fonts on macOS and Linux, but on Windows it ships none and draws every glyph
    as a box. The native Windows platform needs no display server, so headless runs keep it there."""
    if sys.platform != "win32":
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def paths_from_argv(argv: list[str]) -> list[Path]:
    """Files passed on the command line, as Windows and Linux do for "Open with". Flags are ignored."""
    return [Path(arg) for arg in argv[1:] if arg and not arg.startswith("-")]


class Application(QApplication):
    """Restyles itself when the system switches between light and dark, and passes files opened from Finder or the
    Dock to the window. Files that arrive before the window exists wait for it."""

    def __init__(self, argv: list[str]):
        super().__init__(argv)
        self._dark: bool | None = None
        self._open_paths: PathHandler | None = None
        self._pending: list[Path] = []
        self.styleHints().colorSchemeChanged.connect(self._apply_style)
        self._apply_style()

    def _apply_style(self) -> None:
        dark = system_is_dark()
        if dark != self._dark:
            self._dark = dark
            self.setStyleSheet(stylesheet(current()))

    def set_path_handler(self, handler: PathHandler | None) -> None:
        self._open_paths = handler
        pending, self._pending = self._pending, []
        if handler is not None and pending:
            handler(pending)

    def open_paths(self, paths: list[Path]) -> None:
        if not paths:
            return
        if self._open_paths is None:
            self._pending.extend(paths)
        else:
            self._open_paths(paths)

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.FileOpen and event.file():
            self.open_paths([Path(event.file())])
            return True
        if event.type() == QEvent.Type.ApplicationPaletteChange:
            self._apply_style()
        return super().event(event)


def create_app(argv: list[str]) -> Application:
    app = Application(argv)
    app.setFont(app_font())
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setWindowIcon(QIcon(str(asset_path("icon.png"))))
    return app


def launch(app: Application, argv: list[str]) -> MainWindow:
    window = MainWindow()
    app.set_path_handler(window.add_paths)
    app.open_paths(paths_from_argv(argv))
    window.show()
    return window


def run() -> int:
    app = create_app(sys.argv)
    start_logging()
    window = launch(app, sys.argv)
    code = app.exec()
    app.set_path_handler(None)
    del window
    return code
