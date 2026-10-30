"""The list of files waiting to be converted: one row per file, painted by QueueDelegate."""
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum, IntEnum
from pathlib import Path

from PySide6.QtCore import QEvent, QItemSelectionModel, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QCursor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem, QStyle, QStyledItemDelegate, QToolTip

from converter import is_document
from utils.files import human_size

from .style import ACCENT, current_colors
from .widgets import paint_warning

ROW_HEIGHT = 60
THUMB = 44
REMOVE_SIZE = 22
REMOVE_TOOLTIP = "Remove from list"
_USER = int(Qt.ItemDataRole.UserRole)


class Role(IntEnum):
    """Where each fact about a row lives. Values are plain Python types so drag-and-drop can copy them."""

    PATH = _USER
    SIZE = _USER + 1
    KIND = _USER + 2
    STATE = _USER + 3
    REASON = _USER + 4


class FileState(Enum):
    PENDING = "pending"
    UNREADABLE = "unreadable"  # the preview could not decode it when it was added
    FAILED = "failed"  # the last conversion could not convert it


@dataclass(frozen=True)
class QueueSummary:
    count: int = 0
    unreadable: int = 0
    has_document: bool = False


def kind_label(path: Path) -> str:
    suffix = path.suffix.lower()
    return "Notebook" if suffix == ".ipynb" else suffix.lstrip(".").upper()


def summary_text(summary: QueueSummary) -> str:
    ready = summary.count - summary.unreadable
    text = "No files ready" if ready == 0 else f"{ready} file{'s' if ready != 1 else ''} ready"
    return f"{text} · {summary.unreadable} can't be read" if summary.unreadable else text


class FileQueue(QListWidget):
    """Drag rows to reorder. Drops from outside the app pass through to the window, which adds them."""

    changed = Signal()  # files were added or removed; reordering is not a change

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FileQueue")
        self.setAccessibleName("Files to convert")
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setMouseTracking(True)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setItemDelegate(QueueDelegate(self))
        self._thumbnails: dict[str, QPixmap] = {}
        self._quiet = 0
        self.focus_visible = False
        for signal in (self.model().rowsInserted, self.model().rowsRemoved, self.model().modelReset):
            signal.connect(self._emit_changed)

    def _emit_changed(self) -> None:
        if not self._quiet:
            self.changed.emit()

    @contextmanager
    def _silenced(self) -> Iterator[None]:
        self._quiet += 1
        try:
            yield
        finally:
            self._quiet -= 1

    # Rows

    def add_files(self, paths: list[Path]) -> None:
        with self._silenced():
            for path in paths:
                item = QListWidgetItem(path.name)
                item.setData(Role.PATH, str(path))
                item.setData(Role.SIZE, path.stat().st_size)
                item.setData(Role.KIND, kind_label(path))
                item.setToolTip(str(path))
                self._set_state(item, FileState.PENDING, "")
                self.addItem(item)
        if paths:
            self.changed.emit()

    def paths(self) -> list[Path]:
        return [Path(self.item(i).data(Role.PATH)) for i in range(self.count())]

    def state(self, row: int) -> FileState:
        return FileState(self.item(row).data(Role.STATE))

    def reason(self, row: int) -> str:
        return self.item(row).data(Role.REASON)

    def summary(self) -> QueueSummary:
        items = [self.item(i) for i in range(self.count())]
        return QueueSummary(len(items),
                            sum(item.data(Role.STATE) == FileState.UNREADABLE.value for item in items),
                            any(is_document(Path(item.data(Role.PATH))) for item in items))

    def mark(self, path: str, state: FileState, reason: str) -> None:
        for i in range(self.count()):
            item = self.item(i)
            if item.data(Role.PATH) != path:
                continue
            if state is FileState.FAILED and item.data(Role.STATE) == FileState.UNREADABLE.value:
                continue  # it already says why it can't be read
            self._set_state(item, state, reason)

    def reset_failures(self) -> None:
        for i in range(self.count()):
            if self.item(i).data(Role.STATE) == FileState.FAILED.value:
                self._set_state(self.item(i), FileState.PENDING, "")

    def _set_state(self, item: QListWidgetItem, state: FileState, reason: str) -> None:
        item.setData(Role.STATE, state.value)
        item.setData(Role.REASON, reason)
        detail = reason or f"{item.data(Role.KIND)}, {human_size(item.data(Role.SIZE))}"
        item.setData(Qt.ItemDataRole.AccessibleDescriptionRole, detail)

    def remove_selected(self) -> None:
        rows = sorted((self.row(item) for item in self.selectedItems()), reverse=True)
        with self._silenced():
            for row in rows:
                self.takeItem(row)
        if rows:
            self.changed.emit()

    def move_selected(self, step: int) -> None:
        rows = sorted((self.row(item) for item in self.selectedItems()), reverse=step > 0)
        if not rows or not 0 <= rows[0] + step < self.count():
            return
        current = self.currentItem()
        with self._silenced():
            for row in rows:
                item = self.takeItem(row)
                self.insertItem(row + step, item)
                item.setSelected(True)
        if current is not None:
            self.setCurrentItem(current, QItemSelectionModel.SelectionFlag.NoUpdate)
        self.scrollToItem(self.item(rows[-1] + step))

    def clear(self) -> None:
        self._thumbnails.clear()
        super().clear()

    # Thumbnails

    def set_thumbnail(self, path: str, image: QImage) -> None:
        scale = 2  # sharp on Retina screens, smoothly scaled down elsewhere
        pixmap = QPixmap.fromImage(image.scaled(THUMB * scale, THUMB * scale, Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation))
        pixmap.setDevicePixelRatio(scale)
        self._thumbnails[path] = pixmap
        self.viewport().update()

    def thumbnail(self, path: str) -> QPixmap | None:
        return self._thumbnails.get(path)

    # Keyboard focus ring: shown after keyboard navigation, not after a click

    def focusInEvent(self, event) -> None:
        self.focus_visible = event.reason() in (Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason,
                                                Qt.FocusReason.ShortcutFocusReason)
        super().focusInEvent(event)

    def keyPressEvent(self, event) -> None:
        self.focus_visible = True
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        self.focus_visible = False
        super().mousePressEvent(event)


class QueueDelegate(QStyledItemDelegate):
    """Paints a row: thumbnail, name, a detail line or the reason it failed, and a remove button on hover."""

    def __init__(self, queue: FileQueue):
        super().__init__(queue)
        self._queue = queue

    def sizeHint(self, option, index) -> QSize:
        return QSize(max(option.rect.width(), 200), ROW_HEIGHT)

    @staticmethod
    def remove_rect(row: QRectF) -> QRectF:
        return QRectF(row.right() - 12 - REMOVE_SIZE, row.center().y() - REMOVE_SIZE / 2, REMOVE_SIZE, REMOVE_SIZE)

    @staticmethod
    def _row_rect(option) -> QRectF:
        return QRectF(option.rect).adjusted(4, 2, -4, -2)

    def paint(self, painter: QPainter, option, index) -> None:
        colors = current_colors()
        state = option.state
        enabled = bool(state & QStyle.StateFlag.State_Enabled)
        selected = bool(state & QStyle.StateFlag.State_Selected)
        hovered = bool(state & QStyle.StateFlag.State_MouseOver) and enabled
        row = self._row_rect(option)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        if selected or hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(colors.row_selected if selected else colors.row_hover)
            painter.drawRoundedRect(row, 8, 8)
        if state & QStyle.StateFlag.State_HasFocus and self._queue.focus_visible and self._queue.hasFocus():
            painter.setPen(QPen(ACCENT, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(row.adjusted(1, 1, -1, -1), 7, 7)

        path = index.data(Role.PATH)
        file_state = FileState(index.data(Role.STATE))
        thumb = QRectF(row.left() + 10, row.center().y() - THUMB / 2, THUMB, THUMB)
        extension = Path(path).suffix.lstrip(".").upper()
        self._paint_thumbnail(painter, thumb, self._queue.thumbnail(path), extension, colors)

        show_remove = (hovered or selected) and enabled
        text_left = thumb.right() + 12
        text_right = (self.remove_rect(row).left() if show_remove else row.right()) - 10
        width = max(text_right - text_left, 0)
        name_font = QFont(option.font)
        name_font.setPixelSize(13)
        painter.setFont(name_font)
        painter.setPen(colors.text if enabled else colors.disabled)
        name = painter.fontMetrics().elidedText(Path(path).name, Qt.TextElideMode.ElideMiddle, int(width))
        painter.drawText(QRectF(text_left, row.top() + 10, width, 20),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        detail_font = QFont(option.font)
        detail_font.setPixelSize(12)
        painter.setFont(detail_font)
        detail_rect = QRectF(text_left, row.top() + 30, width, 18)
        if file_state is FileState.PENDING:
            painter.setPen(colors.secondary if enabled else colors.disabled)
            detail = f"{index.data(Role.KIND)} · {human_size(index.data(Role.SIZE))}"
        else:
            paint_warning(painter, QRectF(detail_rect.left(), detail_rect.center().y() - 6.5, 13, 13), colors.danger)
            detail_rect.setLeft(detail_rect.left() + 19)
            painter.setFont(detail_font)
            painter.setPen(colors.danger)
            detail = index.data(Role.REASON)
        detail = painter.fontMetrics().elidedText(detail, Qt.TextElideMode.ElideRight, int(detail_rect.width()))
        painter.drawText(detail_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, detail)

        if show_remove:
            self._paint_remove(painter, self.remove_rect(row), colors)
        painter.restore()

    def _paint_thumbnail(self, painter, rect: QRectF, pixmap: QPixmap | None, extension: str, colors) -> None:
        clip = QPainterPath()
        clip.addRoundedRect(rect, 6, 6)
        painter.save()
        painter.setClipPath(clip)
        painter.fillRect(rect, colors.row_hover)
        if pixmap is not None:
            painter.drawPixmap(rect.toRect(), pixmap)
        else:
            font = QFont(painter.font())
            font.setPixelSize(11)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(colors.secondary)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, extension)
        painter.restore()

    def _paint_remove(self, painter: QPainter, rect: QRectF, colors) -> None:
        cursor = QPointF(self._queue.viewport().mapFromGlobal(QCursor.pos()))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colors.control_pressed if rect.contains(cursor) else colors.control_hover)
        painter.drawEllipse(rect)
        pen = QPen(colors.text, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        inset = rect.adjusted(7.5, 7.5, -7.5, -7.5)
        painter.drawLine(inset.topLeft(), inset.bottomRight())
        painter.drawLine(inset.topRight(), inset.bottomLeft())

    def editorEvent(self, event, model, option, index) -> bool:
        clicks = (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick)
        if (event.type() in clicks and event.button() == Qt.MouseButton.LeftButton
                and self.remove_rect(self._row_rect(option)).contains(event.position())):
            if event.type() == QEvent.Type.MouseButtonRelease:
                model.removeRow(index.row())
            return True
        return super().editorEvent(event, model, option, index)

    def helpEvent(self, event, view, option, index) -> bool:
        if event.type() == QEvent.Type.ToolTip and self.remove_rect(self._row_rect(option)).contains(
                QPointF(event.pos())):
            QToolTip.showText(event.globalPos(), REMOVE_TOOLTIP, view)
            return True
        return super().helpEvent(event, view, option, index)

