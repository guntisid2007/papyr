from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, QSizeF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                               QStyle, QStyleOptionSpinBox, QVBoxLayout, QWidget)

from .save_animation import FOLDER_BACK, FOLDER_FRONT
from .style import ACCENT, Colors, current_colors

FORMATS_LINE = "Photos (HEIC, JPEG, PNG, WebP, AVIF, TIFF, BMP, GIF), PDFs, and Jupyter notebooks"
PRIVACY_LINE = "100% offline — your files stay on this computer."

GlyphPainter = Callable[[QPainter, QRectF, Colors], None]


def dropped_paths(event) -> list[Path]:
    return [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]


def _pen(color: QColor, width: float) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def paint_chevron(painter: QPainter, center: QPointF, half_width: float, down: bool, color: QColor) -> None:
    rise = half_width / 2 if down else -half_width / 2
    path = QPainterPath(center + QPointF(-half_width, -rise))
    path.lineTo(center + QPointF(0, rise))
    path.lineTo(center + QPointF(half_width, -rise))
    painter.setPen(_pen(color, 1.6))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)


def paint_upload(painter: QPainter, rect: QRectF, colors: Colors) -> None:
    """A tray with an arrow rising out of it, on a soft accent disc."""
    painter.setPen(Qt.PenStyle.NoPen)
    wash = QColor(ACCENT)
    wash.setAlphaF(0.14)
    painter.setBrush(wash)
    painter.drawEllipse(rect)
    s = rect.width() / 64
    origin = rect.topLeft()

    def at(x: float, y: float) -> QPointF:
        return origin + QPointF(x * s, y * s)

    painter.setPen(_pen(ACCENT, 3.2 * s))
    tray = QPainterPath(at(19, 35))
    tray.lineTo(at(19, 43))
    tray.quadTo(at(19, 46), at(22, 46))
    tray.lineTo(at(42, 46))
    tray.quadTo(at(45, 46), at(45, 43))
    tray.lineTo(at(45, 35))
    painter.drawPath(tray)
    arrow = QPainterPath(at(32, 39))
    arrow.lineTo(at(32, 18))
    arrow.moveTo(at(25, 25))
    arrow.lineTo(at(32, 18))
    arrow.lineTo(at(39, 25))
    painter.drawPath(arrow)


def paint_lock(painter: QPainter, rect: QRectF, colors: Colors) -> None:
    w, h = rect.width(), rect.height()
    body = QRectF(rect.left() + w * 0.12, rect.top() + h * 0.45, w * 0.76, h * 0.52)
    painter.setPen(_pen(colors.secondary, 1.4))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    shackle = QRectF(rect.left() + w * 0.26, rect.top() + h * 0.06, w * 0.48, h * 0.64)
    painter.drawArc(shackle, 0, 180 * 16)
    painter.drawLine(QPointF(shackle.left(), shackle.center().y()), QPointF(shackle.left(), body.top()))
    painter.drawLine(QPointF(shackle.right(), shackle.center().y()), QPointF(shackle.right(), body.top()))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(colors.secondary)
    painter.drawRoundedRect(body, 1.5, 1.5)


def paint_folder(painter: QPainter, rect: QRectF, colors: Colors) -> None:
    """The same blue folder the save animation flies into."""
    w, h = rect.width(), rect.height()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(FOLDER_BACK)
    back = QPainterPath()
    back.addRoundedRect(QRectF(rect.left(), rect.top() + h * 0.12, w, h * 0.88), 3, 3)
    back.addRoundedRect(QRectF(rect.left(), rect.top(), w * 0.42, h * 0.3), 2, 2)
    painter.drawPath(back.simplified())
    painter.setBrush(FOLDER_FRONT)
    painter.drawRoundedRect(QRectF(rect.left(), rect.top() + h * 0.3, w, h * 0.7), 3, 3)


def paint_warning(painter: QPainter, rect: QRectF, color: QColor) -> None:
    """A filled warning triangle with a knocked-out exclamation mark."""
    side = min(rect.width(), rect.height())
    box = QRectF(0, 0, side, side)
    box.moveCenter(rect.center())
    triangle = QPainterPath(QPointF(box.center().x(), box.top() + side * 0.06))
    triangle.lineTo(box.right(), box.bottom() - side * 0.06)
    triangle.lineTo(box.left(), box.bottom() - side * 0.06)
    triangle.closeSubpath()
    painter.setPen(_pen(color, side * 0.12))
    painter.setBrush(color)
    painter.drawPath(triangle)
    knockout = QColor(Qt.GlobalColor.white)
    painter.setPen(_pen(knockout, side * 0.12))
    x = box.center().x()
    painter.drawLine(QPointF(x, box.top() + side * 0.4), QPointF(x, box.top() + side * 0.62))
    painter.drawPoint(QPointF(x, box.top() + side * 0.78))


class Glyph(QWidget):
    """A small painted icon. Decorative unless given an accessible name."""

    def __init__(self, paint: GlyphPainter, size: QSize, accessible_name: str = "", parent=None):
        super().__init__(parent)
        self._paint = paint
        self.setFixedSize(size)
        self.setAccessibleName(accessible_name)

    def set_painter(self, paint: GlyphPainter) -> None:
        self._paint = paint
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint(painter, QRectF(self.rect()), current_colors())


class ElidedLabel(QLabel):
    """One line of text shortened with an ellipsis to fit its width. text() returns the full text."""

    def __init__(self, text: str = "", mode: Qt.TextElideMode = Qt.TextElideMode.ElideRight, parent=None):
        super().__init__(parent)
        self._full = ""
        self._mode = mode
        self.setText(text)

    def setText(self, text: str) -> None:
        self._full = text
        self.setAccessibleName(text)
        self._elide()
        self.updateGeometry()

    def text(self) -> str:
        return self._full

    def sizeHint(self) -> QSize:
        margins = self.contentsMargins()
        width = self.fontMetrics().horizontalAdvance(self._full) + margins.left() + margins.right() + 2
        return QSize(width, super().sizeHint().height())

    def minimumSizeHint(self) -> QSize:
        return QSize(min(self.sizeHint().width(), 40), super().minimumSizeHint().height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._elide()

    def _elide(self) -> None:
        super().setText(self.fontMetrics().elidedText(self._full, self._mode, self.width()))


def _arrow_color(widget: QWidget) -> QColor:
    colors = current_colors()
    return colors.secondary if widget.isEnabled() else colors.disabled


class ComboBox(QComboBox):
    """A combo box that draws its own chevron, since the stylesheet replaces the platform arrow."""

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_chevron(painter, QPointF(self.width() - 15, self.height() / 2 + 0.5), 4, True, _arrow_color(self))


class SpinBox(QDoubleSpinBox):
    """A spin box that draws its own stepper chevrons, since the stylesheet replaces the platform arrows."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lineEdit().setTextMargins(7, 0, 0, 0)  # the macOS style ignores the stylesheet's left padding here

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        option = QStyleOptionSpinBox()
        self.initStyleOption(option)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = _arrow_color(self)
        for control, down in ((QStyle.SubControl.SC_SpinBoxUp, False), (QStyle.SubControl.SC_SpinBoxDown, True)):
            rect = self.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, option, control, self)
            nudge = -1.5 if down else 1.5
            paint_chevron(painter, QPointF(rect.center()) + QPointF(-1, nudge), 3.5, down, color)


def section_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Section")
    return label


def secondary_label(text: str = "", wrap: bool = True) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Secondary")
    label.setWordWrap(wrap)
    return label


class EmptyState(QWidget):
    """What the workspace shows before any file is added: a compact card that explains the first step."""

    browseFiles = Signal()
    browseFolder = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.addStretch(1)
        row = QHBoxLayout()
        outer.addLayout(row)
        outer.addStretch(1)
        row.addStretch(1)
        card = QFrame()
        card.setObjectName("EmptyCard")
        card.setMaximumWidth(440)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        row.addWidget(card, 100)
        row.addStretch(1)

        column = QVBoxLayout(card)
        column.setContentsMargins(32, 28, 32, 22)
        column.setSpacing(0)
        icon = Glyph(paint_upload, QSize(64, 64), "Drop files here")
        column.addWidget(icon, 0, Qt.AlignmentFlag.AlignHCenter)
        column.addSpacing(14)
        heading = QLabel("Drop files here to get started")
        heading.setObjectName("Heading")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(heading)
        column.addSpacing(6)
        formats = secondary_label(FORMATS_LINE)
        formats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(formats)
        column.addSpacing(18)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        column.addLayout(buttons)
        buttons.addStretch()
        self.browse_button = QPushButton("Browse Files…")
        self.browse_button.setObjectName("Primary")
        self.browse_button.setToolTip("Choose photos, PDFs, or notebooks to convert")
        self.browse_button.clicked.connect(self.browseFiles)
        self.folder_button = QPushButton("Add Folder…")
        self.folder_button.setToolTip("Add every supported file in a folder")
        self.folder_button.clicked.connect(self.browseFolder)
        buttons.addWidget(self.browse_button)
        buttons.addWidget(self.folder_button)
        buttons.addStretch()
        column.addSpacing(18)

        privacy = QHBoxLayout()
        privacy.setSpacing(6)
        column.addLayout(privacy)
        privacy.addStretch()
        privacy.addWidget(Glyph(paint_lock, QSize(11, 13)), 0, Qt.AlignmentFlag.AlignVCenter)
        privacy.addWidget(secondary_label(PRIVACY_LINE, wrap=False))
        privacy.addStretch()


class DestinationPicker(QFrame):
    """The Save to row: which folder, where it is, and whether Papyr can write there."""

    changeRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Destination")
        column = QVBoxLayout(self)
        column.setContentsMargins(10, 8, 8, 8)
        column.setSpacing(6)
        row = QHBoxLayout()
        row.setSpacing(10)
        column.addLayout(row)
        self._icon = Glyph(paint_folder, QSize(24, 20))
        row.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignVCenter)
        text = QVBoxLayout()
        text.setSpacing(1)
        row.addLayout(text, 1)
        self.name_label = ElidedLabel()
        self.detail_label = ElidedLabel(mode=Qt.TextElideMode.ElideMiddle)
        self.detail_label.setObjectName("Secondary")
        text.addWidget(self.name_label)
        text.addWidget(self.detail_label)
        self.change_button = QPushButton("Change…")
        self.change_button.setToolTip("Choose the folder where converted files are saved")
        self.change_button.clicked.connect(self.changeRequested)
        row.addWidget(self.change_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.problem_label = QLabel()
        self.problem_label.setObjectName("DestinationProblem")
        self.problem_label.setWordWrap(True)
        self.problem_label.hide()
        column.addWidget(self.problem_label)

    def show_folder(self, path: Path, problem: str | None) -> None:
        self.name_label.setText(path.name or str(path))
        home = Path.home()
        self.detail_label.setText(f"~/{path.relative_to(home).as_posix()}"
                                  if path.is_relative_to(home) and path != home else str(path))
        self.problem_label.setText(problem or "")
        self.problem_label.setVisible(bool(problem))
        self._icon.set_painter(_paint_folder_warning if problem else paint_folder)
        self.setToolTip(f"{path}\n{problem}" if problem else str(path))
        self.setAccessibleName(f"Save to {path}" + (f". {problem}" if problem else ""))
        self.setProperty("problem", bool(problem))
        self.style().unpolish(self)
        self.style().polish(self)


def _paint_folder_warning(painter: QPainter, rect: QRectF, colors: Colors) -> None:
    paint_warning(painter, QRectF(rect.topLeft(), QSizeF(rect.height(), rect.height())), colors.warning)
