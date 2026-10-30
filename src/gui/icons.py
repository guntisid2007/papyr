"""Papyr's icons: one line style (round caps, 1.5 px strokes on a 16 unit grid), drawn with QPainter."""
from collections.abc import Callable
from enum import Enum, auto

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from .theme import Theme

GRID = 16.0


class Icon(Enum):
    PLUS = auto()
    FOLDER = auto()
    TRASH = auto()
    CLOSE = auto()
    CHECK = auto()
    WARNING = auto()
    LOCK = auto()
    CHEVRON_DOWN = auto()
    ARROW_RIGHT = auto()
    ARROW_LEFT = auto()
    RETRY = auto()
    REVEAL = auto()
    GRIP = auto()
    SLIDERS = auto()
    DOCUMENT = auto()
    STACK = auto()


def _path(*points: tuple[float, float]) -> QPainterPath:
    path = QPainterPath(QPointF(*points[0]))
    for point in points[1:]:
        path.lineTo(QPointF(*point))
    return path


def _plus(p: QPainter) -> None:
    p.drawLine(QPointF(8, 3), QPointF(8, 13))
    p.drawLine(QPointF(3, 8), QPointF(13, 8))


def _folder(p: QPainter) -> None:
    path = QPainterPath(QPointF(2, 4.5))
    path.quadTo(QPointF(2, 3), QPointF(3.5, 3))
    path.lineTo(QPointF(6.2, 3))
    path.lineTo(QPointF(7.7, 4.6))
    path.lineTo(QPointF(12.5, 4.6))
    path.quadTo(QPointF(14, 4.6), QPointF(14, 6.1))
    path.lineTo(QPointF(14, 11.5))
    path.quadTo(QPointF(14, 13), QPointF(12.5, 13))
    path.lineTo(QPointF(3.5, 13))
    path.quadTo(QPointF(2, 13), QPointF(2, 11.5))
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(2, 7), QPointF(14, 7))


def _trash(p: QPainter) -> None:
    p.drawLine(QPointF(2.5, 4.2), QPointF(13.5, 4.2))
    p.drawPath(_path((6, 4.2), (6, 2.6), (10, 2.6), (10, 4.2)))
    p.drawPath(_path((3.8, 4.2), (4.6, 13.4), (11.4, 13.4), (12.2, 4.2)))
    p.drawLine(QPointF(6.7, 6.8), QPointF(6.9, 10.8))
    p.drawLine(QPointF(9.3, 6.8), QPointF(9.1, 10.8))


def _close(p: QPainter) -> None:
    p.drawLine(QPointF(4, 4), QPointF(12, 12))
    p.drawLine(QPointF(12, 4), QPointF(4, 12))


def _check(p: QPainter) -> None:
    p.drawPath(_path((3, 8.5), (6.5, 12), (13, 4.5)))


def _warning(p: QPainter) -> None:
    triangle = _path((8, 2.2), (14.4, 13.4), (1.6, 13.4))
    triangle.closeSubpath()
    p.drawPath(triangle)
    p.drawLine(QPointF(8, 6.4), QPointF(8, 9.2))
    p.drawPoint(QPointF(8, 11.4))


def _lock(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(3, 7, 10, 7), 1.6, 1.6)
    shackle = QPainterPath(QPointF(5.2, 7))
    shackle.lineTo(QPointF(5.2, 5))
    shackle.arcTo(QRectF(5.2, 2.2, 5.6, 5.6), 180, -180)
    shackle.lineTo(QPointF(10.8, 7))
    p.drawPath(shackle)


def _chevron_down(p: QPainter) -> None:
    p.drawPath(_path((4.5, 6.5), (8, 10), (11.5, 6.5)))


def _arrow_right(p: QPainter) -> None:
    p.drawLine(QPointF(3, 8), QPointF(13, 8))
    p.drawPath(_path((9, 4), (13, 8), (9, 12)))


def _arrow_left(p: QPainter) -> None:
    p.drawLine(QPointF(13, 8), QPointF(3, 8))
    p.drawPath(_path((7, 4), (3, 8), (7, 12)))


def _retry(p: QPainter) -> None:
    arc = QPainterPath()
    arc.arcMoveTo(QRectF(2.8, 2.8, 10.4, 10.4), 60)
    arc.arcTo(QRectF(2.8, 2.8, 10.4, 10.4), 60, 280)
    p.drawPath(arc)
    p.drawPath(_path((10.6, 1.8), (10.6, 4.4), (13.2, 4.4)))


def _reveal(p: QPainter) -> None:
    p.drawEllipse(QRectF(2.5, 2.5, 8, 8))
    p.drawLine(QPointF(9.6, 9.6), QPointF(13.5, 13.5))


def _grip(p: QPainter) -> None:
    for x in (6, 10):
        for y in (4, 8, 12):
            p.drawPoint(QPointF(x, y))


def _sliders(p: QPainter) -> None:
    p.drawLine(QPointF(2.5, 5), QPointF(13.5, 5))
    p.drawLine(QPointF(2.5, 11), QPointF(13.5, 11))
    for x, y in ((10, 5), (6, 11)):
        p.save()
        p.setBrush(p.pen().color())
        p.drawEllipse(QPointF(x, y), 1.6, 1.6)
        p.restore()


def _document(p: QPainter) -> None:
    sheet = _path((3.5, 1.8), (9.5, 1.8), (12.5, 4.8), (12.5, 14.2), (3.5, 14.2))
    sheet.closeSubpath()
    p.drawPath(sheet)
    p.drawPath(_path((9.5, 1.8), (9.5, 4.8), (12.5, 4.8)))


def _stack(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(4.5, 2.5, 9, 9), 1.5, 1.5)
    p.drawPath(_path((2.5, 5), (2.5, 13.5), (11, 13.5)))


_PAINTERS: dict[Icon, Callable[[QPainter], None]] = {
    Icon.PLUS: _plus, Icon.FOLDER: _folder, Icon.TRASH: _trash, Icon.CLOSE: _close, Icon.CHECK: _check,
    Icon.WARNING: _warning, Icon.LOCK: _lock, Icon.CHEVRON_DOWN: _chevron_down, Icon.ARROW_RIGHT: _arrow_right,
    Icon.ARROW_LEFT: _arrow_left, Icon.RETRY: _retry, Icon.REVEAL: _reveal, Icon.GRIP: _grip,
    Icon.SLIDERS: _sliders, Icon.DOCUMENT: _document, Icon.STACK: _stack,
}


def paint_icon(painter: QPainter, icon: Icon, rect: QRectF, color: QColor, stroke: float = 1.5) -> None:
    """Draw icon centred in rect, at the largest square size that fits."""
    side = min(rect.width(), rect.height())
    scale = side / GRID
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.translate(rect.center().x() - side / 2, rect.center().y() - side / 2)
    painter.scale(scale, scale)
    pen = QPen(color, (stroke if icon is not Icon.GRIP else 2.2) / scale)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    _PAINTERS[icon](painter)
    painter.restore()


MARK_PAPER, MARK_CORAL, MARK_CORAL_SOFT = QColor("#f5f2ec"), QColor("#e2553d"), QColor("#eba393")
MARK_SCALE = 0.7  # the prism spans 70% of the tile, the same proportion as the app icon


def paint_prism(painter: QPainter, rect: QRectF) -> None:
    """The Papyr prism on a 64-unit grid: a white beam enters and leaves as coral that breaks into pixels.
    scripts/make_icons.py paints the app icon with this too."""
    side = min(rect.width(), rect.height())
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.translate(rect.center().x() - side / 2, rect.center().y() - side / 2)
    painter.scale(side / 64, side / 64)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(MARK_PAPER)
    painter.drawRect(QRectF(4, 30, 16, 4))
    ray = QColor(MARK_PAPER)
    ray.setAlphaF(0.5)
    painter.setPen(QPen(ray, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
    painter.drawLine(QPointF(20, 32), QPointF(39.5, 30))
    painter.setPen(Qt.PenStyle.NoPen)
    for color, fan, pixels in (
        (MARK_CORAL_SOFT, ((37.4, 26), (39.5, 30), (52, 30.5), (52, 20)), ((54, 19, 4), (54, 25, 4), (59.5, 22.5, 3))),
        (MARK_CORAL, ((39.5, 30), (41.5, 34), (52, 42), (52, 30.5)),
         ((54, 32, 4), (54, 38, 4), (59.5, 35.5, 3), (59.5, 42, 2))),
    ):
        painter.setBrush(color)
        painter.drawPath(_path(*fan))
        for x, y, size in pixels:
            painter.drawRect(QRectF(x, y, size, size))
    pen = QPen(MARK_PAPER, 4)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    prism = _path((30, 12), (48, 46), (12, 46))
    prism.closeSubpath()
    painter.drawPath(prism)
    painter.restore()


def paint_mark(painter: QPainter, rect: QRectF, theme: Theme) -> None:
    """The Papyr mark as the window shows it: the prism on a graphite tile."""
    side = min(rect.width(), rect.height())
    tile = QRectF(rect.center().x() - side / 2, rect.center().y() - side / 2, side, side)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#34343a") if theme.dark else QColor("#2a2a2f"))
    painter.drawRoundedRect(tile, side * 15 / 64, side * 15 / 64)
    painter.restore()
    inner = side * MARK_SCALE
    paint_prism(painter, QRectF(tile.center().x() - inner / 2, tile.center().y() - inner / 2, inner, inner))
