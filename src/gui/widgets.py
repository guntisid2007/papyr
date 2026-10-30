"""Papyr's controls, painted from the theme so they look the same in light, dark, and on every platform."""
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QEvent, QPoint, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QFontMetrics, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QAbstractButton, QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from . import motion
from .icons import Icon, paint_icon
from .theme import RADIUS_CONTROL, Theme, Type, current, font

KEYBOARD_REASONS = (Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason,
                    Qt.FocusReason.ShortcutFocusReason, Qt.FocusReason.OtherFocusReason)


def shortcut_text(sequence: QKeySequence | str) -> str:
    """How the platform writes a shortcut, such as ⌘O on a Mac and Ctrl+O elsewhere. Needs the application."""
    return QKeySequence(sequence).toString(QKeySequence.SequenceFormat.NativeText)


def dropped_paths(event) -> list[Path]:
    return [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]


def paint_focus_ring(painter: QPainter, rect: QRectF, radius: float, theme: Theme) -> None:
    painter.setPen(QPen(theme.accent, 2))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), radius, radius)


class Kind(Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    GHOST = "ghost"  # no fill until hovered: toolbar icons and quiet actions


class Button(QAbstractButton):
    """A push button with an optional icon and keyboard hint, such as Convert ⌘↩."""

    def __init__(self, text: str = "", icon: Icon | None = None, kind: Kind = Kind.SECONDARY, hint: str = "",
                 height: int = 30, parent=None):
        super().__init__(parent)
        self._icon, self._kind, self._hint, self._height = icon, kind, hint, height
        self._keyboard_focus = False
        self.setText(text)
        self.setAccessibleName(text)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_text(self, text: str) -> None:
        self.setText(text)
        self.setAccessibleName(text)
        self.updateGeometry()

    def _font(self):
        return font(Type.BODY_STRONG if self._kind is Kind.PRIMARY else Type.BODY)

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(self._font())
        text = self.text()
        width = (metrics.horizontalAdvance(text) if text else 0) + (24 if text else 0)
        if self._icon is not None:
            width += 16 + (6 if text else 0)
        if not text:
            width = max(width + 14, self._height)
        if self._hint:
            width += QFontMetrics(font(Type.CAPTION)).horizontalAdvance(self._hint) + 18
        return QSize(width + 2, self._height)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def focusInEvent(self, event) -> None:
        self._keyboard_focus = event.reason() in KEYBOARD_REASONS
        super().focusInEvent(event)

    def mousePressEvent(self, event) -> None:
        self._keyboard_focus = False
        super().mousePressEvent(event)

    def _colors(self, theme: Theme) -> tuple[QColor, QColor]:
        """(fill, text) for the current state."""
        enabled, down, hover = self.isEnabled(), self.isDown(), self.underMouse() and self.isEnabled()
        if not enabled:
            fill = theme.control if self._kind is not Kind.GHOST else QColor(Qt.GlobalColor.transparent)
            return fill, theme.text_tertiary
        if self._kind is Kind.PRIMARY:
            return theme.accent_pressed if down else theme.accent_hover if hover else theme.accent, theme.on_accent
        if self._kind is Kind.GHOST:
            fill = theme.control_pressed if down else theme.control if hover else QColor(Qt.GlobalColor.transparent)
            return fill, theme.text if hover or down else theme.text_secondary
        return theme.control_pressed if down else theme.control_hover if hover else theme.control, theme.text

    def paintEvent(self, event) -> None:
        theme = current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        fill, text_color = self._colors(theme)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, RADIUS_CONTROL, RADIUS_CONTROL)

        content = rect.adjusted(12 if self.text() else 0, 0, -12 if self.text() else 0, 0)
        if self._hint:
            hint_font = font(Type.CAPTION)
            hint_width = QFontMetrics(hint_font).horizontalAdvance(self._hint) + 10
            hint_rect = QRectF(content.right() - hint_width, rect.center().y() - 9, hint_width, 18)
            wash = QColor(text_color)
            wash.setAlphaF(0.18 if self._kind is Kind.PRIMARY else 0.08)
            painter.setBrush(wash)
            painter.drawRoundedRect(hint_rect, 5, 5)
            painter.setFont(hint_font)
            hint_text = QColor(text_color)
            hint_text.setAlphaF(0.92)
            painter.setPen(hint_text)
            painter.drawText(hint_rect, Qt.AlignmentFlag.AlignCenter, self._hint)
            content.setRight(hint_rect.left() - 8)

        painter.setFont(self._font())
        metrics = painter.fontMetrics()
        label = metrics.elidedText(self.text(), Qt.TextElideMode.ElideRight,
                                   int(content.width() - (22 if self._icon is not None else 0)))
        text_width = metrics.horizontalAdvance(label) if label else 0
        icon_width = 16 + (6 if label else 0) if self._icon is not None else 0
        x = content.center().x() - (text_width + icon_width) / 2
        if self._icon is not None:
            paint_icon(painter, self._icon, QRectF(x, rect.center().y() - 8, 16, 16), text_color)
            x += icon_width
        if label:
            painter.setPen(text_color)
            painter.drawText(QRectF(x, rect.top(), text_width + 2, rect.height()),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)
        if self.hasFocus() and self._keyboard_focus:
            paint_focus_ring(painter, rect, RADIUS_CONTROL, theme)


class Chip(Button):
    """A compact control in the dock: an optional label, a value, and a chevron when it opens a popover."""

    def __init__(self, label: str = "", icon: Icon | None = None, menu: bool = True, parent=None):
        super().__init__("", icon, Kind.SECONDARY, height=28, parent=parent)
        self._label, self._value, self._menu = label, "", menu
        self.setAccessibleName(label)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)  # long values elide to fit

    def set_value(self, value: str) -> None:
        self._value = value
        self.setAccessibleDescription(value)
        self.updateGeometry()
        self.update()

    def value(self) -> str:
        return self._value

    def sizeHint(self) -> QSize:
        label = QFontMetrics(font(Type.BODY)).horizontalAdvance(self._label) + 6 if self._label else 0
        value = QFontMetrics(font(Type.BODY_STRONG)).horizontalAdvance(self._value)
        icon = 22 if self._icon is not None else 0
        return QSize(20 + icon + label + value + (18 if self._menu else 0), self._height)

    def minimumSizeHint(self) -> QSize:
        return QSize(min(self.sizeHint().width(), 100), self._height)

    def paintEvent(self, event) -> None:
        theme = current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        fill, text_color = self._colors(theme)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, RADIUS_CONTROL, RADIUS_CONTROL)
        x = rect.left() + 10
        right = rect.right() - (24 if self._menu else 10)
        if self._icon is not None:
            paint_icon(painter, self._icon, QRectF(x, rect.center().y() - 7, 14, 14), theme.text_secondary)
            x += 22
        if self._label:
            painter.setFont(font(Type.BODY))
            painter.setPen(theme.text_secondary if self.isEnabled() else theme.text_tertiary)
            label = painter.fontMetrics().elidedText(self._label, Qt.TextElideMode.ElideRight, int(right - x))
            painter.drawText(QRectF(x, rect.top(), right - x, rect.height()), Qt.AlignmentFlag.AlignVCenter, label)
            x += painter.fontMetrics().horizontalAdvance(label) + 6
        painter.setFont(font(Type.BODY_STRONG))
        painter.setPen(text_color)
        value = painter.fontMetrics().elidedText(self._value, Qt.TextElideMode.ElideMiddle, int(max(right - x, 0)))
        painter.drawText(QRectF(x, rect.top(), max(right - x, 0), rect.height()), Qt.AlignmentFlag.AlignVCenter, value)
        if self._menu:
            paint_icon(painter, Icon.CHEVRON_DOWN, QRectF(rect.right() - 22, rect.center().y() - 6, 12, 12),
                       theme.text_secondary)
        if self.hasFocus() and self._keyboard_focus:
            paint_focus_ring(painter, rect, RADIUS_CONTROL, theme)


class Toggle(Button):
    """A checkable chip with a small switch, such as Merge into one PDF."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, None, Kind.SECONDARY, height=28, parent=parent)
        self.setCheckable(True)

    def sizeHint(self) -> QSize:
        return QSize(QFontMetrics(font(Type.BODY)).horizontalAdvance(self.text()) + 56, self._height)

    def paintEvent(self, event) -> None:
        theme = current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        fill, text_color = self._colors(theme)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, RADIUS_CONTROL, RADIUS_CONTROL)
        track = QRectF(rect.left() + 9, rect.center().y() - 7, 24, 14)
        on = self.isChecked()
        painter.setBrush(theme.accent if on and self.isEnabled() else theme.control_pressed if not on else
                         theme.text_tertiary)
        painter.drawRoundedRect(track, 7, 7)
        painter.setBrush(QColor("#ffffff"))
        knob = 10
        painter.drawEllipse(QRectF(track.right() - knob - 2 if on else track.left() + 2,
                                   track.center().y() - knob / 2, knob, knob))
        painter.setFont(font(Type.BODY))
        painter.setPen(text_color)
        text_rect = QRectF(track.right() + 8, rect.top(), rect.right() - track.right() - 16, rect.height())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter,
                         painter.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideRight,
                                                          int(text_rect.width())))
        if self.hasFocus() and self._keyboard_focus:
            paint_focus_ring(painter, rect, RADIUS_CONTROL, theme)


class Segment(Button):
    """One choice in a SegmentedBar."""

    def __init__(self, text: str, menu: bool = False, parent=None):
        super().__init__(text, None, Kind.GHOST, height=26, parent=parent)
        self.setCheckable(True)
        self._menu = menu

    def sizeHint(self) -> QSize:
        width = QFontMetrics(font(Type.BODY_STRONG)).horizontalAdvance(self.text()) + 22
        return QSize(width + (14 if self._menu else 0), self._height)

    def paintEvent(self, event) -> None:
        theme = current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        checked, hover = self.isChecked(), self.underMouse() and self.isEnabled()
        if checked:
            painter.setPen(QPen(theme.border_strong, 1) if not theme.dark else Qt.PenStyle.NoPen)
            painter.setBrush(theme.segment)
            painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        elif hover:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme.hover)
            painter.drawRoundedRect(rect, 6, 6)
        color = theme.text if checked or hover else theme.text_secondary
        if not self.isEnabled():
            color = theme.text_tertiary
        painter.setFont(font(Type.BODY_STRONG))
        painter.setPen(color)
        text_rect = rect.adjusted(0, 0, -12 if self._menu else 0, 0)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self.text())
        if self._menu:
            paint_icon(painter, Icon.CHEVRON_DOWN, QRectF(rect.right() - 19, rect.center().y() - 5, 10, 10), color)
        if self.hasFocus() and self._keyboard_focus:
            paint_focus_ring(painter, rect, 6, theme)


class Track(QFrame):
    """A recessed rounded strip that holds segments."""

    def paintEvent(self, event) -> None:
        theme = current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(theme.control)
        painter.drawRoundedRect(QRectF(self.rect()), 8, 8)


class Surface(QFrame):
    """A raised rounded panel: the dock, cards, and popovers."""

    def __init__(self, radius: float = 14, fill: str = "raised", border: bool = True, parent=None):
        super().__init__(parent)
        self._radius, self._fill, self._border = radius, fill, border

    def paintEvent(self, event) -> None:
        theme = current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(theme.border_strong if theme.dark else theme.border, 1) if self._border
                       else Qt.PenStyle.NoPen)
        painter.setBrush(getattr(theme, self._fill))
        painter.drawRoundedRect(rect, self._radius, self._radius)


class Popover(QFrame):
    """A small floating panel that opens above or below a control and closes on a click outside or Esc."""

    def __init__(self, parent: QWidget):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(14, 12, 14, 14)
        self.body.setSpacing(8)

    def paintEvent(self, event) -> None:
        theme = current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(theme.border_strong, 1))
        painter.setBrush(theme.raised)
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)

    def open_at(self, anchor: QWidget) -> None:
        """Show above anchor when there is room on screen, otherwise below it."""
        self.adjustSize()
        top_left = anchor.mapToGlobal(QPoint(0, 0))
        above = top_left.y() - self.height() - 6
        y = above if above >= anchor.screen().availableGeometry().top() else top_left.y() + anchor.height() + 6
        self.move(top_left.x(), y)
        self.show()


class ElidedLabel(QLabel):
    """One line of text shortened with an ellipsis to fit its width. text() returns the full text."""

    def __init__(self, text: str = "", style: Type = Type.BODY, mode: Qt.TextElideMode = Qt.TextElideMode.ElideRight,
                 parent=None):
        super().__init__(parent)
        self._full = ""
        self._mode = mode
        self.setFont(font(style))
        self.setText(text)

    def setText(self, text: str) -> None:
        self._full = text
        self.setAccessibleName(text)
        self._elide()
        self.updateGeometry()

    def text(self) -> str:
        return self._full

    def sizeHint(self) -> QSize:
        width = self.fontMetrics().horizontalAdvance(self._full) + 2
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


def label(text: str = "", style: Type = Type.BODY, tone: str = "", wrap: bool = False) -> QLabel:
    """A label in one step of the type scale. tone picks a colour token from the stylesheet: secondary,
    tertiary, accent, success, warning, or danger."""
    result = QLabel(text)
    result.setFont(font(style))
    result.setWordWrap(wrap)
    if tone:
        result.setProperty("tone", tone)
    return result


def set_tone(widget: QLabel, tone: str) -> None:
    widget.setProperty("tone", tone)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class Glyph(QWidget):
    """A painted icon at a fixed size, coloured by a theme token."""

    def __init__(self, icon: Icon, size: int = 16, role: str = "text_secondary", stroke: float = 1.5, parent=None):
        super().__init__(parent)
        self._icon, self._role, self._stroke = icon, role, stroke
        self.setFixedSize(size, size)

    def set_icon(self, icon: Icon, role: str | None = None) -> None:
        self._icon = icon
        self._role = role or self._role
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        paint_icon(painter, self._icon, QRectF(self.rect()), getattr(current(), self._role), self._stroke)


CROSSFADE_MS = 180


def crossfade(widget: QWidget) -> None:
    """Fade what widget shows now into whatever it shows next. Call it just before changing the widget.
    Skipped when the user has asked macOS to reduce motion."""
    if widget.isVisible() and motion.animations_enabled():
        FadeOut(widget, widget.grab(), CROSSFADE_MS).start()


class FadeOut(QWidget):
    def __init__(self, host: QWidget, snapshot: QPixmap, duration: int):
        super().__init__(host)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._snapshot, self._opacity = snapshot, 1.0
        self.setGeometry(host.rect())
        self._animation = QVariantAnimation(self)
        self._animation.setStartValue(1.0)
        self._animation.setEndValue(0.0)
        self._animation.setDuration(duration)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._step)
        self._animation.finished.connect(self.deleteLater)
        host.installEventFilter(self)

    def start(self) -> None:
        self.raise_()
        self.show()
        self._animation.start()

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.Resize:
            self._animation.stop()  # the snapshot no longer lines up with the window
            self.deleteLater()
        return False

    def _step(self, value: float) -> None:
        self._opacity = value
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setOpacity(self._opacity)
        painter.drawPixmap(QPoint(0, 0), self._snapshot)


class DropOverlay(QWidget):
    """Shown over the window while files are dragged onto it: a coral outline and what dropping will do."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._message = ""
        self.hide()

    def show_message(self, message: str) -> None:
        self._message = message
        self.setGeometry(self.parentWidget().rect())
        self.raise_()
        self.show()
        self.update()

    def paintEvent(self, event) -> None:
        theme = current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        wash = QColor(theme.canvas)
        wash.setAlphaF(0.92)
        painter.fillRect(self.rect(), wash)
        frame = QRectF(self.rect()).adjusted(12, 12, -12, -12)
        painter.setBrush(theme.accent_wash)
        pen = QPen(theme.accent, 2, Qt.PenStyle.DashLine)
        pen.setDashPattern([4, 3])
        painter.setPen(pen)
        painter.drawRoundedRect(frame, 16, 16)
        center = frame.center()
        disc = QRectF(center.x() - 28, center.y() - 52, 56, 56)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(theme.accent)
        painter.drawEllipse(disc)
        paint_icon(painter, Icon.PLUS, disc.adjusted(14, 14, -14, -14), theme.on_accent, 2)
        painter.setFont(font(Type.HEADLINE))
        painter.setPen(theme.text)
        painter.drawText(QRectF(frame.left(), disc.bottom() + 12, frame.width(), 24), Qt.AlignmentFlag.AlignCenter,
                         self._message)
