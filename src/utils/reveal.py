"""Show a converted file in the system file manager. Runs a local command only; nothing touches the network."""
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

REVEAL_LABEL = {"darwin": "Show in Finder", "win32": "Show in Explorer"}.get(sys.platform, "Show in Folder")


def reveal_command(path: Path, platform: str = sys.platform) -> list[str] | None:
    """The command that opens the file manager with path selected, or None where there is no such command."""
    if platform == "darwin":
        return ["open", "-R", str(path)]
    if platform == "win32":
        return ["explorer", f"/select,{path}"]
    return None


def reveal(path: Path) -> None:
    command = reveal_command(path) if path.exists() else None
    if command is None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
    else:
        subprocess.Popen(command)
