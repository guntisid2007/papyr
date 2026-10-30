"""The queue: a header with the file count and list actions, a notice banner, and the rows themselves."""
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from utils.files import human_size
from utils.reveal import REVEAL_LABEL

from ..file_queue import FileQueue
from ..icons import Icon
from ..model import QueueSummary, Workspace, plural
from ..widgets import Button, ElidedLabel, Glyph, Kind, Surface, label, set_tone
from ..theme import Type

ORDER_HINT = "Pages follow this order. Drag to rearrange."


def summary_text(queue: QueueSummary) -> str:
    text = f"{plural(queue.count, 'file')} · {human_size(queue.total_bytes)}"
    return f"{text} · {queue.unreadable} can't be read" if queue.unreadable else text


class Banner(Surface):
    """One line about the last thing that happened, such as files that were skipped or a cancelled run."""

    revealRequested = Signal()
    dismissed = Signal()

    def __init__(self, parent=None):
        super().__init__(10, "surface", parent=parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 6, 6, 6)
        row.setSpacing(8)
        self.icon = Glyph(Icon.CHECK, 14, "text_secondary")
        row.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignVCenter)
        self.text = ElidedLabel()
        row.addWidget(self.text, 1)
        self.reveal_button = Button(REVEAL_LABEL, height=24)
        self.reveal_button.clicked.connect(self.revealRequested)
        row.addWidget(self.reveal_button)
        self.close_button = Button("", Icon.CLOSE, Kind.GHOST, height=24)
        self.close_button.setToolTip("Dismiss")
        self.close_button.setAccessibleName("Dismiss")
        self.close_button.clicked.connect(self.dismissed)
        row.addWidget(self.close_button)

    def show_notice(self, state: Workspace) -> None:
        self.setVisible(bool(state.notice))
        self.text.setText(state.notice)
        set_tone(self.text, "danger" if state.error else "")
        self.icon.set_icon(Icon.WARNING if state.error else Icon.CHECK, "danger" if state.error else "text_secondary")
        self.reveal_button.setVisible(bool(state.kept))


class WorkspaceView(QWidget):
    addFiles = Signal()
    addFolder = Signal()
    clearAll = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        column = QVBoxLayout(self)
        column.setContentsMargins(12, 10, 12, 0)
        column.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(8, 0, 0, 0)
        header.setSpacing(4)
        self.summary = label("", Type.BODY_STRONG)
        header.addWidget(self.summary)
        header.addSpacing(8)
        self.hint = ElidedLabel(ORDER_HINT, Type.CAPTION)
        self.hint.setProperty("tone", "secondary")
        header.addWidget(self.hint)
        header.addStretch(1)
        self.add_files_button = self._tool(Icon.PLUS, "Add Files…", "Add photos, PDFs, or notebooks (⌘O)",
                                           self.addFiles)
        self.add_folder_button = self._tool(Icon.FOLDER, "Add Folder…", "Add every supported file in a folder (⇧⌘O)",
                                            self.addFolder)
        self.clear_button = self._tool(Icon.TRASH, "Clear All", "Remove every file from the list", self.clearAll)
        for button in (self.add_files_button, self.add_folder_button, self.clear_button):
            header.addWidget(button)
        column.addLayout(header)

        self.banner = Banner()
        self.banner.hide()
        column.addWidget(self.banner)
        self.queue = FileQueue()
        column.addWidget(self.queue, 1)

    @staticmethod
    def _tool(icon: Icon, name: str, tip: str, signal) -> Button:
        button = Button("", icon, Kind.GHOST, height=28)
        button.setAccessibleName(name)
        button.setToolTip(tip)
        button.clicked.connect(signal)
        return button

    def show_queue(self, queue: QueueSummary, numbered: bool, busy: bool) -> None:
        self.summary.setText(summary_text(queue))
        self.hint.setVisible(numbered and not busy)
        self.queue.numbered = numbered
        self.queue.viewport().update()
        for button in (self.add_files_button, self.add_folder_button, self.clear_button):
            button.setEnabled(not busy)
        self.queue.set_locked(busy)

    def files(self) -> list[Path]:
        return self.queue.paths()
