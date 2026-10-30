"""Papyr's design tokens: a graphite palette with one coral accent, in light and dark, plus the type scale.

Widgets that paint themselves read current(). Standard Qt widgets get the same tokens through stylesheet().
"""
from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette

RADIUS_CONTROL = 7
RADIUS_ROW = 9
RADIUS_SURFACE = 14


def _rgba(hex_color: str, alpha: float = 1.0) -> QColor:
    color = QColor(hex_color)
    color.setAlphaF(alpha)
    return color


@dataclass(frozen=True)
class Theme:
    dark: bool
    canvas: QColor  # the window
    surface: QColor  # cards and the list
    raised: QColor  # the command dock and popovers
    control: QColor
    control_hover: QColor
    control_pressed: QColor
    selected: QColor
    segment: QColor  # the chosen segment in a segmented bar
    hover: QColor
    border: QColor
    border_strong: QColor
    text: QColor
    text_secondary: QColor
    text_tertiary: QColor  # decoration and disabled text only, never body copy
    accent: QColor  # fills: the primary button, the selected format, focus rings
    accent_hover: QColor
    accent_pressed: QColor
    accent_text: QColor  # coral text and line icons on the canvas
    accent_wash: QColor
    on_accent: QColor
    success: QColor
    success_wash: QColor
    warning: QColor
    warning_wash: QColor
    danger: QColor
    danger_wash: QColor


LIGHT = Theme(
    dark=False,
    canvas=QColor("#f3f3f4"),
    surface=QColor("#ffffff"),
    raised=QColor("#ffffff"),
    control=QColor("#ececee"),
    control_hover=QColor("#e3e3e6"),
    control_pressed=QColor("#d8d8dc"),
    selected=_rgba("#d0432f", 0.10),
    segment=QColor("#ffffff"),
    hover=_rgba("#16161a", 0.045),
    border=_rgba("#16161a", 0.09),
    border_strong=_rgba("#16161a", 0.16),
    text=QColor("#1a1a1d"),
    text_secondary=QColor("#606068"),
    text_tertiary=QColor("#9a9aa2"),
    accent=QColor("#d0432f"),
    accent_hover=QColor("#bf3b28"),
    accent_pressed=QColor("#ab3322"),
    accent_text=QColor("#b5362a"),
    accent_wash=_rgba("#d0432f", 0.08),
    on_accent=QColor("#ffffff"),
    success=QColor("#166f3c"),
    success_wash=_rgba("#166f3c", 0.10),
    warning=QColor("#8a4f00"),
    warning_wash=_rgba("#c27a00", 0.12),
    danger=QColor("#b02c25"),
    danger_wash=_rgba("#b02c25", 0.09),
)

DARK = Theme(
    dark=True,
    canvas=QColor("#161618"),
    surface=QColor("#1d1d20"),
    raised=QColor("#232327"),
    control=QColor("#2c2c31"),
    control_hover=QColor("#35353b"),
    control_pressed=QColor("#3e3e45"),
    selected=_rgba("#ff7a66", 0.14),
    segment=QColor("#3d3d44"),
    hover=_rgba("#ffffff", 0.05),
    border=_rgba("#ffffff", 0.08),
    border_strong=_rgba("#ffffff", 0.14),
    text=QColor("#ededef"),
    text_secondary=QColor("#a3a3ab"),
    text_tertiary=QColor("#6c6c74"),
    accent=QColor("#d0432f"),
    accent_hover=QColor("#dc4f3a"),
    accent_pressed=QColor("#b93a28"),
    accent_text=QColor("#ff8a78"),
    accent_wash=_rgba("#ff7a66", 0.10),
    on_accent=QColor("#ffffff"),
    success=QColor("#4cc38a"),
    success_wash=_rgba("#4cc38a", 0.12),
    warning=QColor("#f0b45a"),
    warning_wash=_rgba("#f0b45a", 0.12),
    danger=QColor("#ff7b72"),
    danger_wash=_rgba("#ff7b72", 0.12),
)


def system_is_dark() -> bool:
    """Follow the system appearance. Platforms that don't report one (offscreen Qt) are read from the palette."""
    app = QGuiApplication.instance()
    scheme = app.styleHints().colorScheme()
    if scheme != Qt.ColorScheme.Unknown:
        return scheme == Qt.ColorScheme.Dark
    return app.palette().color(QPalette.ColorRole.Window).lightness() < 128


def current() -> Theme:
    return DARK if system_is_dark() else LIGHT


class Type(Enum):
    """The type scale: (pixel size, weight, letter spacing in percent)."""

    DISPLAY = (28, QFont.Weight.Bold, -1.5)
    TITLE = (19, QFont.Weight.DemiBold, -0.5)
    HEADLINE = (15, QFont.Weight.DemiBold, 0)
    BODY = (13, QFont.Weight.Normal, 0)
    BODY_MEDIUM = (13, QFont.Weight.Medium, 0)
    BODY_STRONG = (13, QFont.Weight.DemiBold, 0)
    CAPTION = (12, QFont.Weight.Normal, 0)
    LABEL = (11, QFont.Weight.DemiBold, 4)  # small uppercase section labels
    BADGE = (10, QFont.Weight.Bold, 3)

    def __init__(self, size: int, weight: QFont.Weight, spacing: float):
        self.size = size
        self.weight = weight
        self.spacing = spacing


def font(style: Type) -> QFont:
    result = QFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont))
    result.setPixelSize(style.size)
    result.setWeight(style.weight)
    if style.spacing:
        result.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 100 + style.spacing)
    return result


def app_font() -> QFont:
    return font(Type.BODY)


def css(color: QColor) -> str:
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"


def stylesheet(theme: Theme) -> str:
    """Styles for the standard widgets Papyr uses. Custom widgets paint themselves from the same tokens."""
    v = {name: css(value) for name, value in vars(theme).items() if isinstance(value, QColor)}
    return """
QWidget { color: %(text)s; }
QMainWindow, QWidget#Canvas { background: %(canvas)s; }
QLabel { background: transparent; }
QLabel[tone="secondary"] { color: %(text_secondary)s; }
QLabel[tone="tertiary"] { color: %(text_tertiary)s; }
QLabel[tone="accent"] { color: %(accent_text)s; }
QLabel[tone="success"] { color: %(success)s; }
QLabel[tone="warning"] { color: %(warning)s; }
QLabel[tone="danger"] { color: %(danger)s; }
QLabel:disabled { color: %(text_tertiary)s; }

QLineEdit, QDoubleSpinBox { background: %(control)s; color: %(text)s; border: 1px solid transparent;
                            border-radius: 7px; padding: 4px 8px; selection-background-color: %(accent)s;
                            selection-color: %(on_accent)s; }
QLineEdit:hover, QDoubleSpinBox:hover { background: %(control_hover)s; }
QLineEdit:focus, QDoubleSpinBox:focus { border: 2px solid %(accent)s; padding: 3px 7px; }
QLineEdit:disabled, QDoubleSpinBox:disabled { color: %(text_tertiary)s; }
/* Zero-width steppers rather than NoButtons, which collapses the macOS edit field to one pixel. */
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 0; border: none; }

QSlider { min-height: 22px; background: transparent; }
QSlider::groove:horizontal { height: 4px; background: %(control_pressed)s; border-radius: 2px; }
QSlider::sub-page:horizontal { background: %(accent)s; border-radius: 2px; }
QSlider::handle:horizontal { width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
                             background: #ffffff; border: 1px solid rgba(0, 0, 0, 60); }
QSlider::handle:horizontal:focus { border: 2px solid %(accent)s; }

QListView { background: transparent; border: none; outline: none; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: %(border_strong)s; border-radius: 3px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: %(text_tertiary)s; }
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page { height: 0;
                                                                                        background: none; }
QToolTip { background: %(raised)s; color: %(text)s; border: 1px solid %(border_strong)s; padding: 4px 6px;
           border-radius: 6px; }
QMenu { background: %(raised)s; color: %(text)s; border: 1px solid %(border_strong)s; padding: 4px;
        border-radius: 8px; }
QMenu::item { padding: 5px 22px 5px 12px; border-radius: 5px; }
QMenu::item:selected { background: %(accent)s; color: %(on_accent)s; }
QMenu::item:checked { font-weight: 600; }
""" % v
