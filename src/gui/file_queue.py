"""The list of files waiting to be converted: one row per file, painted by QueueDelegate."""
from collections.abc import Iterator
from contextlib import contextmanager
from enum import Enum, IntEnum
from pathlib import Path

from PySide6.QtCore import QEvent, QItemSelectionModel, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QCursor, QFontMetrics, QImage, QKeySequence, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem, QStyle, QStyledItemDelegate, QToolTip

from converter import is_document
from utils.files import human_size

from .icons import Icon, paint_icon
from .model import QueueSummary
from .theme import RADIUS_ROW, Type, current, font
from .widgets import shortcut_text

ROW_HEIGHT = 50
MINIMUM_ROW_WIDTH = 200
THUMB = 34
REMOVE_SIZE = 24
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


def kind_label(path: Path) -> str:
    suffix = path.suffix.lower()
    return {".ipynb": "IPYNB", ".jpeg": "JPG", ".tif": "TIFF"}.get(suffix, suffix.lstrip(".").upper())


class FileQueue(QListWidget):
    """Drag rows to reorder. Drops from outside the app pass through to the window, which adds them."""

    changed = Signal()  # files were added or removed; reordering is not a change
    focusMoved = Signal()  # the list gained or lost keyboard focus

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FileQueue")
        self.setAccessibleName("Files to convert")
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMouseTracking(True)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setItemDelegate(QueueDelegate(self))
        self._thumbnails: dict[str, QPixmap] = {}
        self._quiet = 0
        self.focus_visible = False
        self.numbered = False  # show each row's position, because merged pages follow it
        self.active_row = -1  # the row being converted
        self.locked = False  # while converting, the list can be read and scrolled but not changed
        for signal in (self.model().rowsInserted, self.model().rowsRemoved, self.model().modelReset):
            signal.connect(self._emit_changed)
        self.model().rowsMoved.connect(self.viewport().update)

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

    def replace_files(self, paths: list[Path]) -> None:
        with self._silenced():
            self.clear()
        self.add_files(paths)
        if not paths:
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
                            any(is_document(Path(item.data(Role.PATH))) for item in items),
                            sum(item.data(Role.SIZE) for item in items))

    def mark_unreadable(self, path: str, reason: str) -> None:
        for i in range(self.count()):
            if self.item(i).data(Role.PATH) == path:
                self._set_state(self.item(i), FileState.UNREADABLE, reason)

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
        current_item = self.currentItem()
        with self._silenced():
            for row in rows:
                item = self.takeItem(row)
                self.insertItem(row + step, item)
                item.setSelected(True)
        if current_item is not None:
            self.setCurrentItem(current_item, QItemSelectionModel.SelectionFlag.NoUpdate)
        self.scrollToItem(self.item(rows[-1] + step))

    def clear(self) -> None:
        self._thumbnails.clear()
        super().clear()

    def set_locked(self, locked: bool) -> None:
        self.locked = locked
        self.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop if locked
                             else QAbstractItemView.DragDropMode.InternalMove)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection if locked
                              else QAbstractItemView.SelectionMode.ExtendedSelection)
        if locked:
            self.clearSelection()
        else:
            self.show_active(-1)

    def show_active(self, row: int) -> None:
        self.active_row = row
        if 0 <= row < self.count():
            self.scrollToItem(self.item(row), QAbstractItemView.ScrollHint.PositionAtCenter)
        self.viewport().update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if 0 <= self.active_row < self.count():
            self.scrollToItem(self.item(self.active_row), QAbstractItemView.ScrollHint.PositionAtCenter)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.count() and not self.locked:
            self._paint_drop_hint()

    def _paint_drop_hint(self) -> None:
        """Below the last row, say that more files can be dropped there."""
        last = QueueDelegate.row_rect(self.visualItemRect(self.item(self.count() - 1)))
        free = QRectF(last.left(), last.bottom() + 10, last.width(), self.viewport().height() - last.bottom() - 22)
        if free.height() < 64:
            return
        free.setHeight(min(free.height(), 96))
        theme = current()
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(theme.border_strong, 1, Qt.PenStyle.DashLine)
        pen.setDashPattern([4, 4])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(free, RADIUS_ROW + 3, RADIUS_ROW + 3)
        painter.setFont(font(Type.CAPTION))
        text = f"Drop more files here, or press {shortcut_text(QKeySequence.StandardKey.Open)}"
        width = painter.fontMetrics().horizontalAdvance(text)
        icon = QRectF(free.center().x() - (width + 20) / 2, free.center().y() - 7, 14, 14)
        paint_icon(painter, Icon.PLUS, icon, theme.text_secondary)
        painter.setPen(theme.text_secondary)
        painter.drawText(QRectF(icon.right() + 6, free.top(), width + 4, free.height()),
                         Qt.AlignmentFlag.AlignVCenter, text)

    # Thumbnails

    def set_thumbnail(self, path: str, image: QImage) -> None:
        scale = 2  # sharp on Retina screens, smoothly scaled down elsewhere
        side = THUMB * scale
        scaled = image.scaled(side, side, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                              Qt.TransformationMode.SmoothTransformation)
        cropped = scaled.copy((scaled.width() - side) // 2, (scaled.height() - side) // 2, side, side)
        pixmap = QPixmap.fromImage(cropped)
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
        self.focusMoved.emit()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.focusMoved.emit()

    def keyPressEvent(self, event) -> None:
        self.focus_visible = True
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        self.focus_visible = False
        super().mousePressEvent(event)


class QueueDelegate(QStyledItemDelegate):
    """Paints a row: position, thumbnail, name, size or the reason it can't be read, format, and remove."""

    def __init__(self, queue: FileQueue):
        super().__init__(queue)
        self._queue = queue

    def sizeHint(self, option, index) -> QSize:
        return QSize(MINIMUM_ROW_WIDTH, ROW_HEIGHT)  # the list stretches rows to its own width

    @staticmethod
    def row_rect(option_rect) -> QRectF:
        return QRectF(option_rect).adjusted(8, 2, -8, -2)

    @staticmethod
    def remove_rect(row: QRectF) -> QRectF:
        return QRectF(row.right() - 8 - REMOVE_SIZE, row.center().y() - REMOVE_SIZE / 2, REMOVE_SIZE, REMOVE_SIZE)

    def paint(self, painter: QPainter, option, index) -> None:
        theme = current()
        state = option.state
        enabled = bool(state & QStyle.StateFlag.State_Enabled)
        selected = bool(state & QStyle.StateFlag.State_Selected)
        hovered = bool(state & QStyle.StateFlag.State_MouseOver) and enabled and not self._queue.locked
        active = index.row() == self._queue.active_row
        row = self.row_rect(option.rect)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        if selected or hovered or active:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme.selected if selected or active else theme.hover)
            painter.drawRoundedRect(row, RADIUS_ROW, RADIUS_ROW)
        if active:
            painter.setBrush(theme.accent)
            painter.drawRoundedRect(QRectF(row.left(), row.top() + 12, 3, row.height() - 24), 1.5, 1.5)
        if state & QStyle.StateFlag.State_HasFocus and self._queue.focus_visible and self._queue.hasFocus():
            painter.setPen(QPen(theme.accent, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(row.adjusted(1, 1, -1, -1), RADIUS_ROW - 1, RADIUS_ROW - 1)

        path = index.data(Role.PATH)
        unreadable = index.data(Role.STATE) == FileState.UNREADABLE.value
        x = row.left() + 10
        if self._queue.numbered:
            painter.setFont(font(Type.CAPTION))
            painter.setPen(theme.text_secondary)
            painter.drawText(QRectF(x - 4, row.top(), 24, row.height()), Qt.AlignmentFlag.AlignCenter,
                             str(index.row() + 1))
            x += 26
        thumb = QRectF(x, row.center().y() - THUMB / 2, THUMB, THUMB)
        self._paint_thumbnail(painter, thumb, self._queue.thumbnail(path), index.data(Role.KIND), theme)

        show_remove = (hovered or selected) and enabled and not self._queue.locked
        right = self.remove_rect(row).left() - 6 if show_remove else row.right() - 10
        badge_font = font(Type.BADGE)
        badge_width = QFontMetrics(badge_font).horizontalAdvance(index.data(Role.KIND)) + 12
        badge = QRectF(right - badge_width, row.center().y() - 9, badge_width, 18)
        if row.width() > 320:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme.control)
            painter.drawRoundedRect(badge, 5, 5)
            painter.setFont(badge_font)
            painter.setPen(theme.text_secondary)
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, index.data(Role.KIND))
            right = badge.left() - 12

        text_left = thumb.right() + 12
        width = max(right - text_left, 0)
        painter.setFont(font(Type.BODY_MEDIUM))
        painter.setPen(theme.text if enabled else theme.text_tertiary)
        name = painter.fontMetrics().elidedText(Path(path).name, Qt.TextElideMode.ElideMiddle, int(width))
        painter.drawText(QRectF(text_left, row.top() + 7, width, 19),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        detail_rect = QRectF(text_left, row.top() + 26, width, 17)
        painter.setFont(font(Type.CAPTION))
        if unreadable:
            paint_icon(painter, Icon.WARNING, QRectF(detail_rect.left(), detail_rect.center().y() - 6, 12, 12),
                       theme.danger)
            detail_rect.setLeft(detail_rect.left() + 17)
            painter.setPen(theme.danger)
            detail = index.data(Role.REASON)
        elif active:
            painter.setPen(theme.accent_text)
            detail = "Converting…"
        else:
            painter.setPen(theme.text_secondary if enabled else theme.text_tertiary)
            detail = human_size(index.data(Role.SIZE))
        detail = painter.fontMetrics().elidedText(detail, Qt.TextElideMode.ElideRight, int(detail_rect.width()))
        painter.drawText(detail_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, detail)

        if show_remove:
            self._paint_remove(painter, self.remove_rect(row), theme)
        painter.restore()

    @staticmethod
    def _paint_thumbnail(painter, rect: QRectF, pixmap: QPixmap | None, kind: str, theme) -> None:
        clip = QPainterPath()
        clip.addRoundedRect(rect, 7, 7)
        painter.save()
        painter.setClipPath(clip)
        painter.fillRect(rect, theme.control)
        if pixmap is not None:
            painter.drawPixmap(rect.toRect(), pixmap)
        else:
            paint_icon(painter, Icon.DOCUMENT, rect.adjusted(9, 9, -9, -9), theme.text_tertiary)
        painter.restore()
        painter.setPen(QPen(theme.border, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 7, 7)

    def _paint_remove(self, painter: QPainter, rect: QRectF, theme) -> None:
        cursor = QPointF(self._queue.viewport().mapFromGlobal(QCursor.pos()))
        if rect.contains(cursor):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme.control_hover)
            painter.drawEllipse(rect)
        paint_icon(painter, Icon.CLOSE, rect.adjusted(6, 6, -6, -6), theme.text_secondary, 1.6)

    def editorEvent(self, event, model, option, index) -> bool:
        clicks = (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick)
        if (event.type() in clicks and event.button() == Qt.MouseButton.LeftButton and not self._queue.locked
                and self.remove_rect(self.row_rect(option.rect)).contains(event.position())):
            if event.type() == QEvent.Type.MouseButtonRelease:
                model.removeRow(index.row())
            return True
        return super().editorEvent(event, model, option, index)

    def helpEvent(self, event, view, option, index) -> bool:
        if event.type() == QEvent.Type.ToolTip and self.remove_rect(self.row_rect(option.rect)).contains(
                QPointF(event.pos())):
            QToolTip.showText(event.globalPos(), REMOVE_TOOLTIP, view)
            return True
        return super().helpEvent(event, view, option, index)
