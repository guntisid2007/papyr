"""Regenerate assets/icon.png, icon.icns, and icon.ico: the Papyr prism on a graphite tile.
The prism is painted by gui.icons.paint_prism, the same code the window uses, so the two cannot drift."""
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from PySide6.QtCore import QRectF  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402

from gui.icons import MARK_SCALE, paint_prism  # noqa: E402

SIZE = 1024
SUPERSAMPLE = 4
ASSETS = ROOT / "assets"
TILE_TOP, TILE_BOTTOM = (54, 54, 60), (30, 30, 34)


def prism(s: int, rect: QRectF) -> Image.Image:
    canvas = QImage(s, s, QImage.Format.Format_RGBA8888)
    canvas.fill(0)
    painter = QPainter(canvas)
    paint_prism(painter, rect)
    painter.end()
    return Image.frombytes("RGBA", (s, s), bytes(canvas.constBits()))


def draw() -> Image.Image:
    s = SIZE * SUPERSAMPLE
    inset = round(s * 100 / 1024)  # Apple's icon grid: an 824 px body inside the 1024 px canvas
    unit = (s - 2 * inset) / 64

    def at(x: float, y: float) -> tuple[float, float]:
        return inset + x * unit, inset + y * unit

    def box(x: float, y: float, w: float, h: float) -> tuple[float, float, float, float]:
        return (*at(x, y), *at(x + w, y + h))

    image = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    shadow = Image.new("L", (s, s), 0)
    ImageDraw.Draw(shadow).rounded_rectangle(box(0, 1.2, 64, 64), radius=15 * unit, fill=90)
    image = Image.composite(Image.new("RGBA", (s, s), (0, 0, 0, 255)), image,
                            shadow.filter(ImageFilter.GaussianBlur(unit * 1.6)))

    tone = Image.new("RGBA", (1, 256))
    for y in range(256):
        t = y / 255
        tone.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(TILE_TOP, TILE_BOTTOM)) + (255,))
    tone = tone.resize((s, s))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle(box(0, 0, 64, 64), radius=15 * unit, fill=255)
    image.paste(tone, (0, 0), mask)

    inner = 64 * unit * MARK_SCALE
    image.alpha_composite(prism(s, QRectF(s / 2 - inner / 2, s / 2 - inner / 2, inner, inner)))
    return image.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


app = QGuiApplication(sys.argv)
icon = draw()
icon.save(ASSETS / "icon.png")
icon.save(ASSETS / "icon.icns")
icon.save(ASSETS / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("wrote", sorted(p.name for p in ASSETS.iterdir()))
