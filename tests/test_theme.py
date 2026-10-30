import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette

from gui.theme import DARK, LIGHT, current

TEXT = ("text", "text_secondary", "accent_text", "success", "warning", "danger")
BACKGROUNDS = ("canvas", "surface", "raised", "control")


def luminance(color: QColor) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * channel(color.redF()) + 0.7152 * channel(color.greenF()) + 0.0722 * channel(color.blueF())


def contrast(a: QColor, b: QColor) -> float:
    lighter, darker = sorted((luminance(a), luminance(b)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


@pytest.mark.parametrize("theme", [LIGHT, DARK], ids=["light", "dark"])
def test_body_text_reads_at_4_5_to_1_on_every_surface(theme):
    for text in TEXT:
        for background in BACKGROUNDS:
            ratio = contrast(getattr(theme, text), getattr(theme, background))
            assert ratio >= 4.5, f"{text} on {background}: {ratio:.2f}"
    assert contrast(theme.on_accent, theme.accent) >= 4.5, "white on the Convert button"


def test_the_theme_follows_the_system_appearance(app):
    """Offscreen Qt reports no colour scheme, so switch the application palette the way the system does."""
    if app.styleHints().colorScheme() != Qt.ColorScheme.Unknown:
        pytest.skip("this platform reports its own appearance, which a test can't switch")
    light = app.palette()
    dark = QPalette(light)
    for role, color in [(QPalette.ColorRole.Window, "#2b2b2b"), (QPalette.ColorRole.WindowText, "#ffffff")]:
        dark.setColor(role, QColor(color))
    try:
        app.setPalette(dark)
        assert current() is DARK
        assert "rgba(22, 22, 24, 255)" in app.styleSheet(), "the window canvas is the dark graphite"
        app.setPalette(light)
        assert current() is LIGHT
        assert "rgba(243, 243, 244, 255)" in app.styleSheet()
    finally:
        app.setPalette(light)
