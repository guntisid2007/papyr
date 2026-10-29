import math
from collections.abc import Callable

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

ACCENT = QColor("#e5534b")
FOLDER_BACK = QColor("#3d8ee0")
FOLDER_FRONT = QColor("#5aa9f0")
SUCCESS = QColor("#2e9d50")

FLIGHT_END = 0.7
BOUNCE_END = 0.85
FOLDER_SCALE = 0.7
_EASE = QEasingCurve(QEasingCurve.Type.InOutCubic)


def _phase(t: float, start: float, end: float) -> float:
    return min(1.0, max(0.0, (t - start) / (end - start)))


class SaveAnimation(QWidget):
    """Overlay that flies a PDF page from the image list into a folder, then removes itself."""

    def __init__(self, parent: QWidget, endpoints: Callable[[], tuple[QPointF, QPointF]], count: int,
                 duration_ms: int = 1400):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._endpoints, self._count = endpoints, count
        self._start, self._end = endpoints()
        self.setGeometry(parent.rect())
        self._t = 0.0
        self._animation = QVariantAnimation(self)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setDuration(duration_ms)
        self._animation.valueChanged.connect(self.set_progress)
        self._animation.finished.connect(self.deleteLater)

    def start(self) -> None:
        self.raise_()
        self.show()
        self._animation.start()

    def set_progress(self, t: float) -> None:
        """Advance the animation, tracking the window's current layout so a resize never strands it."""
        self._t = t
        self.setGeometry(self.parentWidget().rect())
        self._start, self._end = self._endpoints()
        self.update()

    def paintEvent(self, event) -> None:
        t = self._t
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        folder_opacity = _phase(t, 0.0, 0.15) * (1 - _phase(t, 0.9, 1.0))
        bounce = math.sin(math.pi * _phase(t, FLIGHT_END, BOUNCE_END)) * 0.18
        painter.setOpacity(folder_opacity)
        self._draw_folder(painter, self._end, FOLDER_SCALE * (1 + bounce), lid_open=t < FLIGHT_END + 0.02)

        flight = _EASE.valueForProgress(_phase(t, 0.0, FLIGHT_END))
        if flight < 1:
            control = QPointF((self._start.x() + self._end.x()) / 2,
                              min(self._start.y(), self._end.y()) - 140)
            u = 1 - flight
            position = self._start * (u * u) + control * (2 * u * flight) + self._end * (flight * flight)
            painter.setOpacity(1 - _phase(flight, 0.85, 1.0))
            self._draw_pages(painter, position, 1.0 - 0.7 * flight, -10 * math.sin(math.pi * flight))

        if t >= FLIGHT_END:
            painter.setOpacity(_phase(t, FLIGHT_END, FLIGHT_END + 0.08) * (1 - _phase(t, 0.9, 1.0)))
            self._draw_check(painter, self._end + QPointF(20, -16))
        painter.end()

    def _draw_pages(self, painter: QPainter, center: QPointF, scale: float, angle: float) -> None:
        painter.save()
        painter.translate(center)
        painter.rotate(angle)
        painter.scale(scale, scale)
        for offset in range(min(self._count, 3) - 1, 0, -1):
            self._draw_page(painter, QPointF(6 * offset, -6 * offset), shade=0.94)
        self._draw_page(painter, QPointF(0, 0), shade=1.0)
        if self._count > 1:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(ACCENT)
            painter.drawEllipse(QPointF(30, -38), 15, 15)
            painter.setPen(Qt.GlobalColor.white)
            font = QFont()
            font.setPixelSize(13)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(QRectF(15, -53, 30, 30), Qt.AlignmentFlag.AlignCenter, str(self._count))
        painter.restore()

    def _draw_page(self, painter: QPainter, origin: QPointF, shade: float) -> None:
        w, h, fold = 56.0, 72.0, 14.0
        x, y = origin.x() - w / 2, origin.y() - h / 2
        page = QPainterPath()
        page.moveTo(x, y)
        page.lineTo(x + w - fold, y)
        page.lineTo(x + w, y + fold)
        page.lineTo(x + w, y + h)
        page.lineTo(x, y + h)
        page.closeSubpath()
        painter.setPen(QPen(QColor(0, 0, 0, 50), 1))
        painter.setBrush(QColor.fromRgbF(shade, shade, shade))
        painter.drawPath(page)

        corner = QPainterPath()
        corner.moveTo(x + w - fold, y)
        corner.lineTo(x + w - fold, y + fold)
        corner.lineTo(x + w, y + fold)
        corner.closeSubpath()
        painter.setBrush(QColor("#ffd0c4"))
        painter.drawPath(corner)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffe9e2"))
        painter.drawRoundedRect(QRectF(x + 8, y + 18, w - 16, 26), 3, 3)
        painter.setBrush(ACCENT)
        mountain = QPainterPath()
        mountain.moveTo(x + 8, y + 44)
        mountain.lineTo(x + 22, y + 28)
        mountain.lineTo(x + 34, y + 44)
        painter.drawPath(mountain)
        painter.drawRoundedRect(QRectF(x + 8, y + h - 18, 26, 8), 3, 3)

    def _draw_folder(self, painter: QPainter, center: QPointF, scale: float, lid_open: bool) -> None:
        painter.save()
        painter.translate(center)
        painter.scale(scale, scale)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(FOLDER_BACK)
        back = QPainterPath()
        back.addRoundedRect(QRectF(-34, -22, 68, 46), 6, 6)
        back.addRoundedRect(QRectF(-34, -28, 28, 12), 4, 4)
        painter.drawPath(back.simplified())
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(QRectF(-28, -18, 56, 30), 3, 3)
        painter.setBrush(FOLDER_FRONT)
        if lid_open:
            front = QPainterPath()
            front.moveTo(-34, -8)
            front.lineTo(34, -8)
            front.lineTo(30, 24)
            front.lineTo(-30, 24)
            front.closeSubpath()
            painter.drawPath(front)
        else:
            painter.drawRoundedRect(QRectF(-34, -12, 68, 36), 6, 6)
        painter.restore()

    def _draw_check(self, painter: QPainter, center: QPointF) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(SUCCESS)
        painter.drawEllipse(center, 10, 10)
        pen = QPen(Qt.GlobalColor.white, 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        check = QPainterPath()
        check.moveTo(center + QPointF(-5, 0))
        check.lineTo(center + QPointF(-1, 4))
        check.lineTo(center + QPointF(6, -4))
        painter.drawPath(check)
