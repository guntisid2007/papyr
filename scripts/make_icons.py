"""Regenerate assets/icon.png, icon.icns, and icon.ico: a sheet of paper with a coral folded corner on a
graphite tile. The geometry matches the mark the window draws (gui.icons.paint_mark) on its 64-unit grid."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SIZE = 1024
SUPERSAMPLE = 4
ASSETS = Path(__file__).resolve().parent.parent / "assets"
TILE_TOP, TILE_BOTTOM = (54, 54, 60), (30, 30, 34)
PAPER = (251, 250, 247)
CORAL = (208, 67, 47)
INK = (26, 26, 29, 46)


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

    fold = 13
    sheet = [at(17, 12), at(47 - fold, 12), at(47, 12 + fold), at(47, 52), at(17, 52)]
    lift = Image.new("L", (s, s), 0)
    ImageDraw.Draw(lift).polygon([(x, y + unit * 1.4) for x, y in sheet], fill=120)
    image = Image.composite(Image.new("RGBA", (s, s), (0, 0, 0, 255)), image,
                            lift.filter(ImageFilter.GaussianBlur(unit * 1.2)))
    draw = ImageDraw.Draw(image, "RGBA")
    draw.polygon(sheet, fill=PAPER)
    draw.polygon([at(47 - fold, 12), at(47 - fold, 12 + fold), at(47, 12 + fold)], fill=CORAL)
    for y, width in ((32, 20), (38, 20), (44, 12)):
        draw.rounded_rectangle(box(22, y, width, 2.6), radius=1.3 * unit, fill=INK)
    draw.rounded_rectangle(box(22, 21, 9, 5), radius=1.5 * unit, fill=CORAL)
    return image.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


icon = draw()
icon.save(ASSETS / "icon.png")
icon.save(ASSETS / "icon.icns")
icon.save(ASSETS / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("wrote", sorted(p.name for p in ASSETS.iterdir()))
