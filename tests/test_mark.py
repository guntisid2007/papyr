"""The Papyr prism: a white beam in, coral out, on a graphite tile, in the window and in the shipped icon."""
from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter

from gui.icons import MARK_CORAL, MARK_PAPER, paint_mark
from gui.theme import DARK, LIGHT

ICON = Path(__file__).resolve().parent.parent / "assets" / "icon.png"


def close(rgb: tuple[int, ...], color: QColor, tolerance: int = 12) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(rgb, (color.red(), color.green(), color.blue())))


def mark_image(theme, size: int = 128) -> QImage:
    image = QImage(size, size, QImage.Format.Format_RGBA8888)
    image.fill(theme.canvas)
    painter = QPainter(image)
    paint_mark(painter, QRectF(0, 0, size, size), theme)
    painter.end()
    return image


def at(image: QImage, x: float, y: float) -> tuple[int, int, int]:
    color = image.pixelColor(round(x), round(y))
    return color.red(), color.green(), color.blue()


@pytest.mark.parametrize("theme", [LIGHT, DARK], ids=["light", "dark"])
def test_the_window_mark_shows_a_white_beam_entering_and_coral_leaving_a_hollow_prism(app, theme):
    image = mark_image(theme)
    unit, origin = 128 * 0.7 / 64, 128 * 0.15
    point = lambda x, y: (origin + x * unit, origin + y * unit)  # noqa: E731
    assert close(at(image, *point(12, 32)), MARK_PAPER), "the beam is paper white"
    assert close(at(image, *point(46, 36)), MARK_CORAL), "the light leaves coral"
    assert close(at(image, *point(56, 34)), MARK_CORAL), "the coral breaks into pixels"
    tile = at(image, *point(30, 40))
    assert not close(tile, MARK_PAPER) and not close(tile, MARK_CORAL), "the prism is an outline, not a solid"


def test_the_shipped_icon_is_the_prism_the_window_draws():
    icon = Image.open(ICON).convert("RGB")
    assert icon.size == (1024, 1024)
    unit, origin = 64 * (824 / 64) * 0.7 / 64, 512 - 64 * (824 / 64) * 0.7 / 2
    point = lambda x, y: (round(origin + x * unit), round(origin + y * unit))  # noqa: E731
    assert close(icon.getpixel(point(12, 32)), MARK_PAPER)
    assert close(icon.getpixel(point(46, 36)), MARK_CORAL)
    assert close(icon.getpixel(point(56, 34)), MARK_CORAL)
    assert icon.getpixel(point(30, 40))[0] < 80, "graphite shows through the hollow prism"
