"""Regenerate assets/icon.png, icon.icns, and icon.ico."""
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
ASSETS = Path(__file__).resolve().parent.parent / "assets"


def draw() -> Image.Image:
    scale = 4
    s = SIZE * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    gradient = Image.new("RGBA", (1, 256))
    for y in range(256):
        t = y / 255
        gradient.putpixel((0, y), (int(255 - 40 * t), int(122 - 70 * t), int(89 - 20 * t), 255))
    gradient = gradient.resize((s, s))
    mask = Image.new("L", (s, s), 0)
    inset = int(s * 0.09)
    ImageDraw.Draw(mask).rounded_rectangle((inset, inset, s - inset, s - inset), radius=int(s * 0.2), fill=255)
    img.paste(gradient, (0, 0), mask)

    d = ImageDraw.Draw(img)
    left, top, right, bottom = int(s * 0.29), int(s * 0.22), int(s * 0.71), int(s * 0.78)
    fold = int(s * 0.12)
    d.polygon([(left, top), (right - fold, top), (right, top + fold), (right, bottom), (left, bottom)],
              fill=(255, 255, 255, 255))
    d.polygon([(right - fold, top), (right - fold, top + fold), (right, top + fold)], fill=(255, 205, 190, 255))

    pl, pt, pr, pb = left + int(s * 0.05), top + int(s * 0.17), right - int(s * 0.05), bottom - int(s * 0.12)
    d.rounded_rectangle((pl, pt, pr, pb), radius=int(s * 0.025), fill=(255, 236, 228, 255))
    d.ellipse((pr - int(s * 0.11), pt + int(s * 0.04), pr - int(s * 0.05), pt + int(s * 0.10)),
              fill=(255, 170, 60, 255))
    d.polygon([(pl, pb), (pl + int(s * 0.11), pt + int(s * 0.12)), (pl + int(s * 0.2), pb)], fill=(232, 80, 70, 255))
    d.polygon([(pl + int(s * 0.12), pb), (pl + int(s * 0.25), pt + int(s * 0.17)), (pr, pb)],
              fill=(200, 55, 60, 255))
    bar_top = bottom - int(s * 0.085)
    d.rounded_rectangle((pl, bar_top, pl + int(s * 0.22), bar_top + int(s * 0.03)),
                        radius=int(s * 0.015), fill=(220, 90, 70, 255))
    return img.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


icon = draw()
icon.save(ASSETS / "icon.png")
icon.save(ASSETS / "icon.icns")
icon.save(ASSETS / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("wrote", sorted(p.name for p in ASSETS.iterdir()))
