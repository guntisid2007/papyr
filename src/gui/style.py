"""The window's look, derived from the system palette so light and dark mode both read well."""
from dataclasses import dataclass

from PySide6.QtGui import QColor, QGuiApplication, QPalette

ACCENT = QColor("#e5534b")
ACCENT_HOVER = QColor("#d9443c")
ACCENT_PRESSED = QColor("#c23a33")


def _alpha(color: QColor, alpha: float) -> QColor:
    tinted = QColor(color)
    tinted.setAlphaF(alpha)
    return tinted


def is_dark(palette: QPalette) -> bool:
    return palette.color(QPalette.ColorRole.Window).lightness() < 128


@dataclass(frozen=True)
class Colors:
    dark: bool
    text: QColor
    secondary: QColor
    disabled: QColor
    border: QColor
    card: QColor
    control: QColor
    control_hover: QColor
    control_pressed: QColor
    field: QColor
    track: QColor
    row_hover: QColor
    row_selected: QColor
    danger: QColor
    success: QColor
    warning: QColor


def palette_colors(palette: QPalette) -> Colors:
    dark = is_dark(palette)
    text = palette.color(QPalette.ColorRole.WindowText)
    return Colors(
        dark=dark,
        text=text,
        secondary=_alpha(text, 0.7),
        disabled=_alpha(text, 0.42),
        border=_alpha(text, 0.13 if dark else 0.12),
        card=palette.color(QPalette.ColorRole.Base),
        control=_alpha(text, 0.09) if dark else QColor("#ffffff"),
        control_hover=_alpha(text, 0.14) if dark else QColor("#f4f4f4"),
        control_pressed=_alpha(text, 0.2) if dark else QColor("#e6e6e6"),
        field=_alpha(text, 0.05) if dark else QColor("#ffffff"),
        track=_alpha(text, 0.18),
        row_hover=_alpha(text, 0.06 if dark else 0.045),
        row_selected=_alpha(text, 0.13 if dark else 0.09),
        danger=QColor("#ff7b72" if dark else "#c62f2a"),
        success=QColor("#3fb950" if dark else "#1a7f37"),
        warning=QColor("#e3b341" if dark else "#9a6700"),
    )


def current_colors() -> Colors:
    """Colours for custom painting. Read from the application palette, because a stylesheet rewrites widget
    palettes (a transparent background would look dark in light mode)."""
    return palette_colors(QGuiApplication.palette())


def _css(color: QColor) -> str:
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"


def stylesheet(palette: QPalette) -> str:
    c = palette_colors(palette)
    v = {name: _css(value) for name, value in vars(c).items() if isinstance(value, QColor)}
    v.update(accent=_css(ACCENT), accent_hover=_css(ACCENT_HOVER), accent_pressed=_css(ACCENT_PRESSED),
             accent_wash=_css(_alpha(ACCENT, 0.08)), selection=_css(_alpha(ACCENT, 0.45)))
    return """
QWidget { font-size: 13px; }
QLabel#Title { font-size: 20px; font-weight: 600; }
QLabel#Section { font-weight: 600; }
QLabel#Heading { font-size: 15px; font-weight: 600; }
QLabel#Subtitle { color: %(secondary)s; }
QLabel#Secondary { color: %(secondary)s; font-size: 12px; }
QLabel:disabled, QLabel#Secondary:disabled { color: %(disabled)s; }
QLabel#Status { color: %(secondary)s; }
QLabel#Status[kind="success"] { color: %(success)s; font-weight: 600; }
QLabel#Status[kind="error"] { color: %(danger)s; font-weight: 600; }

QFrame#Workspace { border: 2px solid transparent; border-radius: 14px; }
QFrame#Workspace[dragging="true"] { border: 2px dashed %(accent)s; background: %(accent_wash)s; }
QFrame#Card, QFrame#EmptyCard { background: %(card)s; border: 1px solid %(border)s; border-radius: 12px; }
QFrame#ActionBar { border-top: 1px solid %(border)s; }
QFrame#Destination { background: %(field)s; border: 1px solid %(border)s; border-radius: 8px; }
QFrame#Destination[problem="true"] { border: 1px solid %(warning)s; }
QLabel#DestinationProblem { color: %(warning)s; font-size: 12px; font-weight: 600; }

QPushButton { background: %(control)s; color: %(text)s; border: 1px solid %(border)s; border-radius: 6px;
              padding: 5px 13px; }
QPushButton:hover { background: %(control_hover)s; }
QPushButton:pressed { background: %(control_pressed)s; }
QPushButton:focus { border: 2px solid %(accent)s; padding: 4px 12px; }
QPushButton:disabled { color: %(disabled)s; background: %(row_hover)s; }
QPushButton#Primary { background: %(accent)s; color: white; border: 1px solid %(accent)s; font-weight: 600;
                      padding: 6px 18px; }
QPushButton#Primary:hover { background: %(accent_hover)s; border-color: %(accent_hover)s; }
QPushButton#Primary:pressed { background: %(accent_pressed)s; border-color: %(accent_pressed)s; }
QPushButton#Primary:focus { border: 2px solid %(text)s; padding: 5px 17px; }
QPushButton#Primary:disabled { background: %(row_hover)s; border-color: %(border)s; color: %(disabled)s; }
QPushButton#Link { background: transparent; border: 2px solid transparent; color: %(text)s; padding: 0 2px;
                   text-decoration: underline; }
QPushButton#Link:focus { border-color: %(accent)s; }

QComboBox { background: %(control)s; color: %(text)s; border: 1px solid %(border)s; border-radius: 6px;
            padding: 4px 26px 4px 9px; }
QComboBox:hover { background: %(control_hover)s; }
QComboBox:focus { border: 2px solid %(accent)s; padding: 3px 25px 3px 8px; }
QComboBox:disabled { color: %(disabled)s; background: %(row_hover)s; }
QComboBox::drop-down { border: none; width: 24px; }

QLineEdit, QDoubleSpinBox { background: %(field)s; color: %(text)s; border: 1px solid %(border)s;
                            border-radius: 6px; padding: 4px 8px; selection-background-color: %(selection)s; }
QDoubleSpinBox { padding-right: 24px; }
QLineEdit:focus { border: 2px solid %(accent)s; padding: 3px 7px; }
QDoubleSpinBox:focus { border: 2px solid %(accent)s; padding: 3px 23px 3px 7px; }
QLineEdit:disabled, QDoubleSpinBox:disabled { color: %(disabled)s; }
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 22px; border: none; background: transparent; }

QSlider { min-height: 22px; }
QSlider::groove:horizontal { height: 4px; background: %(track)s; border-radius: 2px; }
QSlider::sub-page:horizontal { background: %(accent)s; border-radius: 2px; }
QSlider::sub-page:horizontal:disabled { background: %(disabled)s; }
QSlider::handle:horizontal { width: 16px; height: 16px; margin: -7px 0; border-radius: 9px; background: white;
                             border: 1px solid rgba(0, 0, 0, 70); }
QSlider::handle:horizontal:focus { border: 2px solid %(accent)s; }

QProgressBar { border: none; border-radius: 2px; background: %(track)s; max-height: 4px; min-height: 4px; }
QProgressBar::chunk { border-radius: 2px; background: %(accent)s; }

QListWidget#FileQueue { background: transparent; border: none; outline: none; }
QCheckBox { spacing: 8px; }
""" % v
