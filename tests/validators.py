"""Checks on converted files that do not trust the converter: magic bytes, a GIF block parser written here, a second
decoder (Qt, or sips on macOS) beside Pillow, and PDFs read with pypdf and drawn with PDFium, neither of which wrote
them."""
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pypdf
import pypdfium2 as pdfium
from PIL import Image, ImageChops, ImageOps, ImageStat

# The file format each Papyr output must really be, read from its first bytes.

def sniff(path: Path) -> str | None:
    head = path.read_bytes()[:64]
    if head.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "GIF"
    if head.startswith(b"BM"):
        return "BMP"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "TIFF"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "WEBP"
    if head.startswith(b"%PDF-"):
        return "PDF"
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"avif", b"avis"):
            return "AVIF"
        if brand in (b"heic", b"heix", b"heim", b"heis", b"hevc", b"hevx", b"mif1", b"msf1"):
            return "HEIC"
    return None


# GIF, parsed block by block

@dataclass
class GifInfo:
    width: int
    height: int
    frames: int = 0
    delays_ms: list[int] = field(default_factory=list)
    loop: int | None = None  # None: no NETSCAPE block, so the animation plays once
    transparent: list[bool] = field(default_factory=list)


def parse_gif(path: Path) -> GifInfo:
    data = path.read_bytes()
    if data[:6] not in (b"GIF87a", b"GIF89a"):
        raise ValueError("not a GIF")
    info = GifInfo(int.from_bytes(data[6:8], "little"), int.from_bytes(data[8:10], "little"))
    packed, pos = data[10], 13
    if packed & 0x80:
        pos += 3 * 2 ** ((packed & 7) + 1)
    delay, transparent = 0, False

    def skip_sub_blocks(p: int) -> int:
        while data[p]:
            p += data[p] + 1
        return p + 1

    while pos < len(data):
        marker = data[pos]
        if marker == 0x3B:
            return info
        if marker == 0x21:
            label = data[pos + 1]
            if label == 0xF9:
                block = data[pos + 3:pos + 7]
                transparent = bool(block[0] & 1)
                delay = int.from_bytes(block[1:3], "little") * 10
            elif label == 0xFF and data[pos + 3:pos + 14] == b"NETSCAPE2.0":
                sub = pos + 14
                if data[sub] >= 3 and data[sub + 1] == 1:
                    info.loop = int.from_bytes(data[sub + 2:sub + 4], "little")
            pos = skip_sub_blocks(pos + 2)
        elif marker == 0x2C:
            flags = data[pos + 9]
            pos += 10
            if flags & 0x80:
                pos += 3 * 2 ** ((flags & 7) + 1)
            pos = skip_sub_blocks(pos + 1)
            info.frames += 1
            info.delays_ms.append(delay)
            info.transparent.append(transparent)
            delay, transparent = 0, False
        else:
            raise ValueError(f"unexpected GIF block 0x{marker:02x} at {pos}")
    raise ValueError("GIF has no trailer")


def gif_frames(path: Path) -> list[Image.Image]:
    """Every frame as it is shown, composited by Pillow."""
    frames = []
    with Image.open(path) as gif:
        for index in range(gif.n_frames):
            gif.seek(index)
            frames.append(gif.convert("RGBA"))
    return frames


# A second decoder

def second_decoder(path: Path, fmt: str) -> tuple[str, tuple[int, int] | None]:
    """Decode with something other than Pillow: Qt's image plugins, or sips on macOS for what Qt lacks.
    Returns (decoder, size), size None when no second decoder is available here."""
    from PySide6.QtGui import QImageReader
    supported = {bytes(f).decode() for f in QImageReader.supportedImageFormats()}
    qt_name = {"JPEG": "jpeg", "PNG": "png", "GIF": "gif", "BMP": "bmp", "TIFF": "tiff", "WEBP": "webp",
               "HEIC": "heic", "AVIF": "avif"}[fmt]
    if qt_name in supported:
        reader = QImageReader(str(path))
        reader.setAutoTransform(False)
        image = reader.read()
        if image.isNull():
            raise ValueError(f"Qt could not decode it: {reader.errorString()}")
        return "Qt", (image.width(), image.height())
    if sys.platform == "darwin" and shutil.which("sips"):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "decoded.png"
            run = subprocess.run(["sips", "-s", "format", "png", str(path), "--out", str(out)],
                                 capture_output=True, text=True, timeout=60)
            if run.returncode or not out.exists():
                raise ValueError(f"sips could not decode it: {run.stderr.strip() or run.stdout.strip()}")
            with Image.open(out) as image:
                return "sips", image.size
    return "none", None


# Pictures

def _fit(size: tuple[int, int], box: int) -> tuple[int, int]:
    scale = min(1.0, box / max(size))
    return max(1, round(size[0] * scale)), max(1, round(size[1] * scale))


def on_white(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    return Image.alpha_composite(background, rgba).convert("RGB")


def mae(a: Image.Image, b: Image.Image, box: int = 128) -> float:
    """Mean absolute difference per channel (0-255) once both are on white and scaled to the smaller of them."""
    size = _fit(min(a.size, b.size, key=lambda s: s[0] * s[1]), box)
    a = on_white(a).resize(size, Image.Resampling.BOX)
    b = on_white(b).resize(size, Image.Resampling.BOX)
    return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3


def quadrant_mae(a: Image.Image, b: Image.Image) -> float:
    """The worst of the four quarters, so a flipped or rotated picture can't hide in the average."""
    worst = 0.0
    for qx in (0, 1):
        for qy in (0, 1):
            def crop(img):
                w, h = img.size
                return img.crop((qx * w // 2, qy * h // 2, (qx + 1) * w // 2 or 1, (qy + 1) * h // 2 or 1))
            worst = max(worst, mae(crop(a), crop(b), 256))
    return worst


def ink(image: Image.Image) -> float:
    """Fraction of pixels visibly darker than paper."""
    gray = on_white(image).convert("L").resize(_fit(image.size, 400), Image.Resampling.BOX)
    histogram = gray.histogram()
    return sum(histogram[:225]) / max(1, gray.width * gray.height)


def is_solid(image: Image.Image) -> bool:
    gray = on_white(image).convert("L")
    return ImageStat.Stat(gray).stddev[0] < 2.0


def region_color(image: Image.Image, rel: tuple[float, float, float, float]) -> tuple[int, int, int]:
    rgb = on_white(image)
    w, h = rgb.size
    box = (int(rel[0] * w), int(rel[1] * h), max(int(rel[2] * w), int(rel[0] * w) + 1),
           max(int(rel[3] * h), int(rel[1] * h) + 1))
    return tuple(round(v) for v in ImageStat.Stat(rgb.crop(box)).median)


def color_distance(a, b) -> int:
    return max(abs(x - y) for x, y in zip(a, b))


def alpha_at(image: Image.Image, rel: tuple[float, float]) -> int:
    if "A" not in image.getbands() and "transparency" not in image.info:
        return 255
    rgba = image.convert("RGBA")
    x, y = int(rel[0] * rgba.width), int(rel[1] * rgba.height)
    return rgba.getpixel((min(x, rgba.width - 1), min(y, rgba.height - 1)))[3]


def band_color(image: Image.Image) -> tuple[int, int, int]:
    """The fingerprint band across the top 12% of a test page."""
    return region_color(image, (0.25, 0.02, 0.75, 0.08))


def open_upright(path: Path) -> Image.Image:
    with Image.open(path) as image:
        image.load()
        return ImageOps.exif_transpose(image)


# PDFs

@dataclass
class PdfFacts:
    pages: int
    sizes: list[tuple[float, float]]
    texts: list[str]
    images: list[list[tuple[int, int]]]  # each page's image XObjects as (width, height)
    encrypted: bool


def _page_images(page) -> list[tuple[int, int]]:
    found = []

    def walk(resources, depth=0):
        if not resources or depth > 4:
            return
        xobjects = resources.get("/XObject")
        if not xobjects:
            return
        for ref in xobjects.get_object().values():
            obj = ref.get_object()
            if obj.get("/Subtype") == "/Image":
                found.append((int(obj["/Width"]), int(obj["/Height"])))
            elif obj.get("/Subtype") == "/Form":
                walk(obj.get("/Resources"), depth + 1)

    walk(page.get("/Resources"))
    return found


def pdf_facts(path: Path) -> PdfFacts:
    reader = pypdf.PdfReader(path)
    sizes = [(float(p.mediabox.width), float(p.mediabox.height)) for p in reader.pages]
    texts = [p.extract_text() or "" for p in reader.pages]
    return PdfFacts(len(reader.pages), sizes, texts, [_page_images(p) for p in reader.pages], reader.is_encrypted)


def pdf_render(path: Path, index: int, dpi: float = 72) -> Image.Image:
    doc = pdfium.PdfDocument(str(path))
    try:
        page = doc[index]
        bitmap = page.render(scale=dpi / 72)
        image = bitmap.to_pil().convert("RGB")
        bitmap.close()
        page.close()
        return image
    finally:
        doc.close()


def pdf_page_count_pdfium(path: Path) -> int:
    doc = pdfium.PdfDocument(str(path))
    try:
        return len(doc)
    finally:
        doc.close()


def fit_on_page(image_size: tuple[int, int], page_size: tuple[float, float], margin_pt: float
                ) -> tuple[float, float, float, float]:
    """Where a picture lands on a fixed-size page: as large as fits inside the margins, centred, unstretched.
    Returns (left, top, width, height) in points from the top-left corner."""
    avail_w, avail_h = page_size[0] - 2 * margin_pt, page_size[1] - 2 * margin_pt
    scale = min(avail_w / image_size[0], avail_h / image_size[1])
    w, h = image_size[0] * scale, image_size[1] * scale
    return (page_size[0] - w) / 2, (page_size[1] - h) / 2, w, h


def text_darkness(path: Path, needle: str) -> int | None:
    """The darkest gray (0 black, 255 white) drawn inside the box where PDFium places needle's characters, or None
    when the text is not on any page. Searchable but invisible text, such as white ink on white paper, scores high."""
    doc = pdfium.PdfDocument(str(path))
    try:
        for index in range(len(doc)):
            page = doc[index]
            text_page = page.get_textpage()
            found = text_page.get_text_range().find(needle)
            if found < 0:
                continue
            boxes = [text_page.get_charbox(found + i) for i in range(len(needle))]
            left, bottom = min(b[0] for b in boxes), min(b[1] for b in boxes)
            right, top = max(b[2] for b in boxes), max(b[3] for b in boxes)
            scale = 3
            image = page.render(scale=scale).to_pil().convert("L")
            height = page.get_height()
            crop = image.crop((int(left * scale), int((height - top) * scale), int(right * scale) + 1,
                               int((height - bottom) * scale) + 1))
            return crop.getextrema()[0]
        return None
    finally:
        doc.close()
