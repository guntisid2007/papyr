"""Regenerate tests/fixtures/sample.heic: a 640x480 HEIC with a red top half and a blue bottom half."""
from pathlib import Path

import pillow_heif
from PIL import Image, ImageDraw

image = Image.new("RGB", (640, 480), "blue")
ImageDraw.Draw(image).rectangle((0, 0, 639, 239), fill="red")
target = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "sample.heic"
pillow_heif.from_pillow(image).save(target, quality=85)
print(target, target.stat().st_size)
