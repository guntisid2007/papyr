from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QLabel, QListWidget,
                               QPushButton, QVBoxLayout)


def dropped_paths(event) -> list[Path]:
    return [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]


class DropZone(QFrame):
    """Empty-state drop target with Browse buttons."""

    filesDropped = Signal(list)
    browseFiles = Signal()
    browseFolder = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.addStretch()
        glyph = QLabel("⇣")
        glyph.setObjectName("DropGlyph")
        title = QLabel("Drop photos, PDFs, or folders here")
        title.setObjectName("DropTitle")
        hint = QLabel("HEIC, JPEG, PNG, WebP, AVIF, TIFF, BMP, GIF, and PDF")
        hint.setObjectName("Muted")
        for label in (glyph, title, hint):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
        layout.addSpacing(12)
        buttons = QHBoxLayout()
        layout.addLayout(buttons)
        buttons.addStretch()
        browse = QPushButton("Browse Files…")
        browse.setObjectName("Primary")
        browse.clicked.connect(self.browseFiles)
        folder = QPushButton("Add Folder…")
        folder.clicked.connect(self.browseFolder)
        buttons.addWidget(browse)
        buttons.addWidget(folder)
        buttons.addStretch()
        layout.addStretch()

    def _set_hover(self, hover: bool) -> None:
        self.setProperty("hover", hover)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_hover(True)

    def dragLeaveEvent(self, event) -> None:
        self._set_hover(False)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_hover(False)
        self.filesDropped.emit(dropped_paths(event))
        event.acceptProposedAction()


class ImageList(QListWidget):
    """Thumbnail list. Drag rows to reorder, or drop files from the desktop to add them."""

    filesDropped = Signal(list)
    PATH_ROLE = Qt.ItemDataRole.UserRole

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ImageList")
        self.setIconSize(QSize(56, 56))
        self.setSpacing(2)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setAcceptDrops(True)
        QShortcut(QKeySequence.StandardKey.Delete, self, self.remove_selected)
        QShortcut(QKeySequence(Qt.Key.Key_Backspace), self, self.remove_selected)

    def paths(self) -> list[Path]:
        return [Path(self.item(i).data(self.PATH_ROLE)) for i in range(self.count())]

    def remove_selected(self) -> None:
        for item in self.selectedItems():
            self.takeItem(self.row(item))

    def move_selected(self, step: int) -> None:
        rows = sorted((self.row(item) for item in self.selectedItems()), reverse=step > 0)
        if not rows or not 0 <= rows[0] + step < self.count():
            return
        for row in rows:
            item = self.takeItem(row)
            self.insertItem(row + step, item)
            item.setSelected(True)
        self.scrollToItem(self.item(rows[-1] + step))

    def _external(self, event) -> bool:
        return event.mimeData().hasUrls() and event.source() is not self

    def dragEnterEvent(self, event) -> None:
        if self._external(event):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if self._external(event):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        if self._external(event):
            self.filesDropped.emit(dropped_paths(event))
            event.acceptProposedAction()
        else:
            super().dropEvent(event)
