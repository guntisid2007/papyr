"""Deterministic test files for the conversion matrix, written with each format's real encoder.

Every fixture is described by a FixtureSpec: what it is, where it lives, and what its pages should look like once
converted (size, page identifier, fingerprint colour, and a lossless reference picture). The files themselves are
generated into tests/fixtures/generated, which is not committed, once per test run. The same seed and
library versions give the same pictures; manifest.json records both.

    python scripts/make_conversion_fixtures.py
"""
import base64
import io
import json
import random
import shutil
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path

import pillow_heif
from PIL import Image, ImageDraw, ImageFont, features

GENERATOR_VERSION = "2"
SEED = 20261031
ROOT = Path(__file__).parent / "fixtures" / "generated"
LIBRARIES = ("Pillow", "pillow-heif", "pypdf", "pypdfium2", "PySide6-Essentials")

MARKER_RED = (220, 20, 30)
MARKER_BLUE = (20, 60, 220)
PAGE_COLORS = [(230, 25, 75), (60, 180, 75), (255, 200, 0), (0, 130, 200), (245, 130, 48), (145, 30, 180),
               (70, 220, 220), (240, 50, 230), (128, 128, 0), (0, 0, 128), (128, 0, 0), (170, 255, 195)]
NOTEBOOK_SECTIONS = 6

pillow_heif.register_heif_opener()


@dataclass(frozen=True)
class PageSpec:
    """One page as a reader should see it after conversion. size is in pixels for pictures, points for PDFs."""

    id: str
    size: tuple[float, float]
    color: tuple[int, int, int] | None = None
    reference: str | None = None  # file name under generated/reference: the page as lossless RGBA
    has_text: bool = True
    alpha: bool = False  # has fully and half transparent areas at ALPHA_PROBES


@dataclass(frozen=True)
class FixtureSpec:
    name: str
    format: str  # the input format row: HEIC, JPEG, PDF, IPYNB, ...
    suffix: str
    kind: str  # raster | pdf | notebook
    pages: tuple[PageSpec, ...]
    lossy: bool = False
    animated_frames: int = 1
    description: str = ""
    extra: dict = field(default_factory=dict, compare=False, hash=False)

    @property
    def file_name(self) -> str:
        return f"{self.name}{self.suffix}"

    @property
    def has_alpha(self) -> bool:
        return any(page.alpha for page in self.pages)

    def path(self, root: Path = ROOT) -> Path:
        return root / self.format.lower() / self.file_name

    def reference(self, page: int, root: Path = ROOT) -> Image.Image:
        with Image.open(root / "reference" / self.pages[page].reference) as image:
            return image.convert("RGBA")


# Pictures

def _font(size: int) -> ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def canonical(size: tuple[int, int], label: str, alpha: bool, band: tuple[int, int, int] | None = None,
              seed: int = SEED) -> Image.Image:
    """A picture with a gradient, text, shapes, one-pixel detail, an orientation marker in the top-left corner,
    and, when alpha, a fully transparent box and a half-transparent band in the top-right quarter."""
    width, height = size
    rng = random.Random(f"{seed}-{label}-{size}")
    gradient = Image.new("RGB", size)
    gradient.putdata([(40 + 175 * x // max(width - 1, 1), 60 + 150 * y // max(height - 1, 1), 140)
                      for y in range(height) for x in range(width)])
    image = gradient.convert("RGBA")
    draw = ImageDraw.Draw(image)
    short = min(size)
    if band:
        draw.rectangle([0, 0, width, max(1, height * 12 // 100)], fill=band)
    m = max(1, short * 3 // 100)
    s = max(2, short * 12 // 100)
    draw.rectangle([m, m, m + s, m + s], fill=MARKER_RED)
    draw.ellipse([width - m - s, height - m - s, width - m, height - m], fill=MARKER_BLUE)
    if short >= 40:
        stripe_w = max(4, width // 6)
        top = height - m - max(4, height // 6)
        for x in range(m, m + stripe_w, 2):
            draw.line([(x, top), (x, height - m)], fill=(0, 0, 0))
        for _ in range(12):
            x, y = rng.randrange(width // 4, width * 3 // 4), rng.randrange(height // 4, height * 3 // 4)
            r = rng.randrange(2, max(3, short // 20))
            draw.ellipse([x - r, y - r, x + r, y + r], outline=(rng.randrange(256), rng.randrange(256), 0), width=1)
        font = _font(max(10, short // 9))
        draw.text((width // 2, height // 2), label, fill=(10, 10, 10), font=font, anchor="mm")
    if alpha:
        clear = Image.new("L", size, 255)
        cdraw = ImageDraw.Draw(clear)
        cdraw.rectangle([width * 62 // 100, height * 18 // 100, width * 92 // 100, height * 34 // 100], fill=0)
        cdraw.rectangle([width * 62 // 100, height * 36 // 100, width * 92 // 100, height * 46 // 100], fill=128)
        image.putalpha(clear)
    return image


ALPHA_PROBES = {"clear": (0.77, 0.26), "half": (0.77, 0.41), "opaque": (0.30, 0.55)}


def flatten(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    return Image.alpha_composite(background, rgba)


def _binary_alpha(image: Image.Image) -> Image.Image:
    """What a GIF can store: each pixel fully clear or fully opaque, colour flattened where it stays."""
    alpha = image.getchannel("A").point(lambda a: 0 if a < 128 else 255)
    result = flatten(image)
    result.putalpha(alpha)
    return result


def _encode(image: Image.Image, path: Path, fmt: str, **options) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "HEIF":
        pillow_heif.from_pillow(image).save(path, quality=options.get("quality", 92))
    else:
        image.save(path, fmt, **options)


RASTER_FORMATS = {
    # format: (suffix, Pillow format, keeps alpha, lossy, save options)
    "HEIC": (".heic", "HEIF", True, True, {"quality": 92}),
    "HEIF": (".heif", "HEIF", True, True, {"quality": 92}),
    "JPEG": (".jpg", "JPEG", False, True, {"quality": 92}),
    "PNG": (".png", "PNG", True, False, {}),
    "WEBP": (".webp", "WEBP", True, True, {"quality": 92}),
    "AVIF": (".avif", "AVIF", True, True, {"quality": 90}),
    "TIFF": (".tiff", "TIFF", True, False, {"compression": "tiff_lzw"}),
    "BMP": (".bmp", "BMP", False, False, {}),
    "GIF": (".gif", "GIF", True, False, {}),
}
SHAPES = {"landscape": (640, 400), "portrait": (360, 540), "tiny": (24, 16), "hires": (3200, 2000)}


def _for_format(image: Image.Image, fmt: str) -> tuple[Image.Image, Image.Image]:
    """(what to hand the encoder, what the file then depicts)."""
    keeps_alpha = RASTER_FORMATS[fmt][2]
    if fmt == "GIF":
        depicted = _binary_alpha(image)
        return depicted, depicted
    if not keeps_alpha:
        flat = flatten(image)
        return flat.convert("RGB"), flat
    return image, image


def _write_gif(image: Image.Image, path: Path) -> None:
    alpha = image.getchannel("A")
    paletted = flatten(image).convert("RGB").quantize(255, dither=Image.Dither.NONE)
    paletted.paste(255, mask=alpha.point(lambda a: 255 if a < 128 else 0))
    palette = paletted.getpalette()
    paletted.putpalette(palette + [0] * (768 - len(palette)))
    paletted.save(path, "GIF", transparency=255)


class _Builder:
    def __init__(self, root: Path):
        self.root = root
        self.specs: list[FixtureSpec] = []
        (root / "reference").mkdir(parents=True, exist_ok=True)

    def reference(self, name: str, image: Image.Image) -> str:
        file = f"{name}.png"
        image.convert("RGBA").save(self.root / "reference" / file, "PNG")
        return file

    def add(self, spec: FixtureSpec) -> FixtureSpec:
        self.specs.append(spec)
        return spec

    def raster(self, fmt: str, shape: str, size: tuple[int, int], suffix: str | None = None, alpha: bool | None = None,
               name: str | None = None) -> FixtureSpec:
        ext, pillow_fmt, keeps_alpha, lossy, options = RASTER_FORMATS[fmt]
        alpha = keeps_alpha and (alpha if alpha is not None else shape == "landscape")
        name = name or f"{fmt.lower()}-{shape}"
        image = canonical(size, f"{fmt} {shape}", alpha)
        to_encode, depicted = _for_format(image, fmt)
        spec = FixtureSpec(name, fmt, suffix or ext, "raster",
                           (PageSpec("PAGE_001", size, None, self.reference(name, depicted), alpha=alpha),),
                           lossy=lossy, description=f"{size[0]}x{size[1]} {shape}"
                           + (", transparent box and half-transparent band" if alpha else ""))
        path = spec.path(self.root)
        if fmt == "GIF":
            path.parent.mkdir(parents=True, exist_ok=True)
            _write_gif(to_encode, path)
        else:
            _encode(to_encode, path, pillow_fmt, **options)
        return self.add(spec)


def _build_rasters(b: _Builder) -> None:
    for fmt in RASTER_FORMATS:
        for shape, size in SHAPES.items():
            b.raster(fmt, shape, size)
    b.raster("JPEG", "alias", (300, 200), suffix=".jpeg", name="jpeg-alias-extension")
    b.raster("TIFF", "alias", (300, 200), suffix=".tif", name="tiff-alias-extension")
    _build_png_variants(b)
    _build_exif_rotated(b)
    _build_multipage_tiff(b)
    _build_animated(b, "GIF")
    _build_animated(b, "WEBP")


def _build_png_variants(b: _Builder) -> None:
    gray = canonical((300, 200), "PNG grayscale", False).convert("L")
    spec = b.add(FixtureSpec("png-grayscale", "PNG", ".png", "raster",
                             (PageSpec("PAGE_001", (300, 200), None, b.reference("png-grayscale", gray)),),
                             description="300x200 8-bit grayscale"))
    gray.save(spec.path(b.root), "PNG")
    deep = canonical((300, 200), "PNG 16 bit", False).convert("L")
    wide = Image.new("I;16", deep.size)
    wide.putdata([v * 257 for v in deep.get_flattened_data()])
    path = b.root / "png" / "png-16bit-grayscale.png"
    wide.save(path, "PNG")
    b.add(FixtureSpec("png-16bit-grayscale", "PNG", ".png", "raster",
                      (PageSpec("PAGE_001", (300, 200), None, b.reference("png-16bit-grayscale", deep)),),
                      description="300x200 16-bit grayscale"))


def _build_exif_rotated(b: _Builder) -> None:
    """Pixels stored sideways with EXIF orientation 6, as phones write them. Upright it is 640x400."""
    for fmt in ("JPEG", "HEIC"):
        upright = flatten(canonical((640, 400), f"{fmt} rotated", False))
        stored = upright.convert("RGB").transpose(Image.Transpose.ROTATE_90)
        name = f"{fmt.lower()}-exif-rotated"
        spec = FixtureSpec(name, fmt, RASTER_FORMATS[fmt][0], "raster",
                           (PageSpec("PAGE_001", (640, 400), None, b.reference(name, upright)),), lossy=True,
                           description="stored 400x640 with EXIF orientation 6; upright 640x400")
        exif = Image.Exif()
        exif[0x0112] = 6
        path = spec.path(b.root)
        if fmt == "JPEG":
            stored.save(path, "JPEG", quality=92, exif=exif.tobytes())
        else:
            heif = pillow_heif.from_pillow(stored)
            heif.info["exif"] = exif.tobytes()
            heif.save(path, quality=92)
        b.add(spec)


def _build_multipage_tiff(b: _Builder) -> None:
    pages = [canonical(size, f"TIFF PAGE_00{i + 1}", i == 0, PAGE_COLORS[i])
             for i, size in enumerate([(500, 350), (300, 450), (420, 420)])]
    specs = tuple(PageSpec(f"PAGE_00{i + 1}", page.size, PAGE_COLORS[i], b.reference(f"tiff-multipage-{i + 1}", page),
                           alpha=i == 0) for i, page in enumerate(pages))
    spec = FixtureSpec("tiff-multipage", "TIFF", ".tiff", "raster", specs,
                       description="3 pages, different sizes, first page transparent")
    pages[0].save(spec.path(b.root), "TIFF", save_all=True, append_images=pages[1:], compression="tiff_deflate")
    b.add(spec)


def _build_animated(b: _Builder, fmt: str) -> None:
    frames = [flatten(canonical((320, 240), f"{fmt} FRAME {i + 1}", False, PAGE_COLORS[i])).convert("RGB")
              for i in range(4)]
    name = f"{fmt.lower()}-animated"
    spec = FixtureSpec(name, fmt, RASTER_FORMATS[fmt][0], "raster",
                       (PageSpec("PAGE_001", (320, 240), PAGE_COLORS[0], b.reference(name, frames[0])),),
                       lossy=fmt == "WEBP", animated_frames=4,
                       description="4-frame animation, 200 ms per frame, distinct frames")
    path = spec.path(b.root)
    options = {"quality": 92} if fmt == "WEBP" else {}
    frames[0].save(path, fmt, save_all=True, append_images=frames[1:], duration=200, loop=0, **options)
    b.add(spec)


# PDFs, drawn with Qt so text is real, searchable, and Unicode

def _qimage(image: Image.Image):
    from PySide6.QtGui import QImage
    rgba = image.convert("RGBA")
    return QImage(rgba.tobytes(), rgba.width, rgba.height, rgba.width * 4, QImage.Format.Format_RGBA8888).copy()


class _PdfPages:
    """Draws one PDF page by page. Units are points, origin top-left."""

    def __init__(self, path: Path):
        from PySide6.QtGui import QPdfWriter
        path.parent.mkdir(parents=True, exist_ok=True)
        self.writer = QPdfWriter(str(path))
        self.writer.setResolution(72)
        self.writer.setCreator("Papyr test fixtures")
        self.painter = None

    def page(self, size: tuple[float, float]):
        from PySide6.QtCore import QMarginsF, QSizeF
        from PySide6.QtGui import QPageLayout, QPageSize, QPainter
        layout = QPageLayout(QPageSize(QSizeF(*size), QPageSize.Unit.Point, "", QPageSize.SizeMatchPolicy.ExactMatch),
                             QPageLayout.Orientation.Portrait, QMarginsF(0, 0, 0, 0))
        self.writer.setPageLayout(layout)
        if self.painter is None:
            self.painter = QPainter(self.writer)
            self.painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        else:
            self.painter.restore()  # QPainter keeps a translucent brush across pages, and Qt applies its opacity
            self.writer.newPage()  # to later images too
        self.painter.save()
        return self.painter

    def close(self) -> None:
        self.painter.restore()
        self.painter.end()


def _band(painter, size, color, page_id: str) -> None:
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QFont
    painter.fillRect(QRectF(0, 0, size[0], size[1] * 0.12), QColor(*color))
    painter.setPen(QColor("black"))
    painter.setFont(QFont("Helvetica", 16))
    painter.drawText(QRectF(24, size[1] * 0.12 + 8, size[0] - 48, 24), 0, page_id)


def _text_page(painter, size, color, page_id, lines):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QFont
    _band(painter, size, color, page_id)
    painter.setFont(QFont("Helvetica", 12))
    y = size[1] * 0.12 + 48
    for line in lines:
        painter.drawText(QRectF(24, y, size[0] - 48, 18), 0, line)
        y += 18


LOREM = ["Papyr converts files offline.", "This paragraph is real text that a PDF reader can select and copy.",
         "The quick brown fox jumps over the lazy dog 0123456789."]
UNICODE_LINES = ["Grüße aus Zürich: àéîõü ÆØÅ ß", "Ελληνικά: καλημέρα κόσμε", "Кириллица: привет мир",
                 "Symbols: € £ ¥ © ® ™ ± ≤ ≥ → ∑ √ ∞"]


def _mixed_pdf(b: _Builder) -> None:
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QBrush, QColor, QFont, QPainterPath, QPen
    pages = [((612, 792), "text"), ((595.28, 841.89), "image"), ((595.28, 841.89), "vector"),
             ((841.89, 595.28), "table"), ((400, 300), "transparency"), ((419.53, 595.28), "unicode"),
             ((612, 792), "scanned")]
    spec_pages = []
    name = "pdf-mixed-content"
    path = b.root / "pdf" / f"{name}.pdf"
    doc = _PdfPages(path)
    photo = flatten(canonical((640, 400), "EMBEDDED", False))
    for index, (size, kind) in enumerate(pages):
        page_id, color = f"PAGE_{index + 1:03d}", PAGE_COLORS[index]
        painter = doc.page(size)
        w, h = size
        top = h * 0.12 + 48
        if kind == "text":
            _text_page(painter, size, color, page_id, LOREM * 6)
        elif kind == "image":
            _text_page(painter, size, color, page_id, ["An embedded photograph:"])
            painter.drawImage(QRectF(48, top + 30, w - 96, (w - 96) * 400 / 640), _qimage(photo))
        elif kind == "vector":
            _text_page(painter, size, color, page_id, ["Vector shapes:"])
            painter.setPen(QPen(QColor(20, 20, 20), 3))
            painter.setBrush(QBrush(QColor(0, 160, 120)))
            painter.drawRect(QRectF(60, top + 40, 200, 120))
            painter.setBrush(QBrush(QColor(200, 40, 160)))
            painter.drawEllipse(QRectF(300, top + 40, 200, 200))
            curve = QPainterPath(QPointF(60, top + 400))
            curve.cubicTo(QPointF(200, top + 200), QPointF(380, top + 600), QPointF(540, top + 380))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(curve)
        elif kind == "table":
            _text_page(painter, size, color, page_id, ["A table:"])
            painter.setFont(QFont("Helvetica", 11))
            for row in range(6):
                for col in range(5):
                    cell = QRectF(48 + col * 140, top + 30 + row * 36, 140, 36)
                    painter.drawRect(cell)
                    text = ["Format", "Lossy", "Alpha", "Pages", "Animated"][col] if row == 0 else f"R{row}C{col + 1}"
                    painter.drawText(cell.adjusted(6, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, text)
        elif kind == "transparency":
            _text_page(painter, size, color, page_id, ["Overlapping translucent circles"])
            painter.setPen(Qt.PenStyle.NoPen)
            for i, rgb in enumerate([(255, 0, 0), (0, 160, 0), (0, 0, 255)]):
                painter.setBrush(QBrush(QColor(*rgb, 110)))
                painter.drawEllipse(QRectF(80 + i * 70, 120, 140, 140))
        elif kind == "unicode":
            _text_page(painter, size, color, page_id, UNICODE_LINES)
        elif kind == "scanned":
            scan = Image.new("L", (int(w * 2), int(h * 2)), 245)
            sdraw = ImageDraw.Draw(scan)
            rng = random.Random(SEED)
            for _ in range(4000):
                x, y = rng.randrange(scan.width), rng.randrange(scan.height)
                sdraw.point((x, y), fill=rng.randrange(180, 235))
            sdraw.rectangle([0, 0, scan.width, int(scan.height * 0.12)], fill=sum(color) // 3)
            for i, line in enumerate(["SCANNED PAGE", page_id] + LOREM):
                sdraw.text((60, scan.height * 0.16 + i * 50), line, fill=20, font=_font(36))
            scan_rgb = scan.convert("RGB")
            ImageDraw.Draw(scan_rgb).rectangle([0, 0, scan.width, int(scan.height * 0.12)], fill=color)
            painter.drawImage(QRectF(0, 0, w, h), _qimage(scan_rgb))
        spec_pages.append(PageSpec(page_id, size, color, has_text=kind != "scanned"))
    doc.close()
    b.add(FixtureSpec(name, "PDF", ".pdf", "pdf", tuple(spec_pages),
                      description="7 pages: text, embedded image, vectors, table (landscape), transparency, "
                                  "Unicode, scanned image; Letter, A4, A5, and custom sizes"))


def _simple_pdfs(b: _Builder) -> None:
    name = "pdf-single-text"
    doc = _PdfPages(b.root / "pdf" / f"{name}.pdf")
    _text_page(doc.page((595.28, 841.89)), (595.28, 841.89), PAGE_COLORS[0], "PAGE_001", LOREM)
    doc.close()
    b.add(FixtureSpec(name, "PDF", ".pdf", "pdf", (PageSpec("PAGE_001", (595.28, 841.89), PAGE_COLORS[0]),),
                      description="1 A4 page of text"))

    name = "pdf-twelve-pages"
    doc = _PdfPages(b.root / "pdf" / f"{name}.pdf")
    pages = []
    for i in range(12):
        size = (612, 792) if i % 3 else (792, 612)
        _text_page(doc.page(size), size, PAGE_COLORS[i], f"PAGE_{i + 1:03d}", [f"Page {i + 1} of 12"])
        pages.append(PageSpec(f"PAGE_{i + 1:03d}", size, PAGE_COLORS[i]))
    doc.close()
    b.add(FixtureSpec(name, "PDF", ".pdf", "pdf", tuple(pages),
                      description="12 pages, every third landscape, a distinct colour band per page"))


# Notebooks: saved outputs only, never run

def _png_b64(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def _cell_md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def _cell_code(source: str, *outputs: dict, count: int = 1) -> dict:
    return {"cell_type": "code", "execution_count": count, "metadata": {},
            "source": source.splitlines(keepends=True), "outputs": list(outputs)}


EXECUTION_SENTINEL = "PAPYR_NOTEBOOK_WAS_EXECUTED.flag"


def _notebook(b: _Builder) -> None:
    cells = [_cell_md("# Papyr matrix notebook NB_TITLE\n\nUnicode: Grüße, Ελληνικά, привет.")]
    for section in range(1, NOTEBOOK_SECTIONS + 1):
        color = PAGE_COLORS[section - 1]
        swatch = Image.new("RGB", (480, 140), color)
        ImageDraw.Draw(swatch).text((240, 70), f"FIGURE {section}", fill="white", font=_font(40), anchor="mm")
        listing = "\n".join(f"value_{section}_{i} = {i} * {section}  # line {i}" for i in range(28))
        cells += [
            _cell_md(f"## Section NB_SECTION_{section:02d}\n\nMath: $e^{{i\\pi}} + {section} = {section - 1}$\n\n"
                     f"$$\\int_0^{section} x^2\\,dx = \\frac{{{section ** 3}}}{{3}}$$"),
            _cell_code(listing + f"\nprint('computed', {section})",
                       {"output_type": "stream", "name": "stdout", "text": [f"SAVED_OUTPUT_{section:02d}\n"]},
                       count=section),
            _cell_code(f"plot_{section}()", {"output_type": "display_data", "metadata": {},
                                             "data": {"image/png": _png_b64(swatch), "text/plain": "<Figure>"}},
                       count=section),
        ]
        if section == 3:
            table = ("<table><thead><tr><th>format</th><th>pages</th></tr></thead><tbody>"
                     + "".join(f"<tr><td>TABLE_ROW_{r}</td><td>{r}</td></tr>" for r in range(1, 6))
                     + "</tbody></table>")
            cells.append(_cell_code("df", {"output_type": "execute_result", "execution_count": 3, "metadata": {},
                                           "data": {"text/html": table, "text/plain": "df"}}, count=3))
    cells.append(_cell_code(f"open({EXECUTION_SENTINEL!r}, 'w').write('ran')\nprint(6 * 7)",
                            {"output_type": "stream", "name": "stdout", "text": ["STALE_SAVED_RESULT\n"]}, count=99))
    nb = {"nbformat": 4, "nbformat_minor": 5, "cells": cells,
          "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                       "language_info": {"name": "python"}}}
    name = "notebook-matrix"
    path = b.root / "ipynb" / f"{name}.ipynb"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
    b.add(FixtureSpec(name, "IPYNB", ".ipynb", "notebook", (), extra={"sections": NOTEBOOK_SECTIONS},
                      description=f"{len(cells)} cells: Markdown, code, saved stdout, PNG figures, HTML table, "
                                  "math, Unicode; long enough for several pages"))
    short = {**nb, "cells": nb["cells"][:4]}
    path = b.root / "ipynb" / "notebook-short.ipynb"
    path.write_text(json.dumps(short, indent=1, ensure_ascii=False), encoding="utf-8")
    b.add(FixtureSpec("notebook-short", "IPYNB", ".ipynb", "notebook", (), extra={"sections": 1},
                      description="4 cells: title, one section with code output and a figure"))


# Building and caching

ROSTER: list[tuple[str, str]] = (
    [(f"{fmt.lower()}-{shape}", fmt) for fmt in RASTER_FORMATS for shape in SHAPES]
    + [("jpeg-alias-extension", "JPEG"), ("tiff-alias-extension", "TIFF"), ("png-grayscale", "PNG"),
       ("png-16bit-grayscale", "PNG"), ("jpeg-exif-rotated", "JPEG"), ("heic-exif-rotated", "HEIC"),
       ("tiff-multipage", "TIFF"), ("gif-animated", "GIF"), ("webp-animated", "WEBP"),
       ("pdf-mixed-content", "PDF"), ("pdf-single-text", "PDF"), ("pdf-twelve-pages", "PDF"),
       ("notebook-matrix", "IPYNB"), ("notebook-short", "IPYNB")])

def _versions() -> dict[str, str]:
    found = {}
    for name in LIBRARIES:
        try:
            found[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            found[name] = "missing"
    found["libavif"] = str(features.version("avif"))
    found["libheif"] = pillow_heif.libheif_version()
    return found


def build(root: Path = ROOT) -> list[FixtureSpec]:
    """Write every fixture into root, replacing what was there, and return their specs."""
    if root.exists():
        shutil.rmtree(root)
    b = _Builder(root)
    _build_rasters(b)
    _mixed_pdf(b)
    _simple_pdfs(b)
    _notebook(b)
    assert sorted((spec.name, spec.format) for spec in b.specs) == sorted(ROSTER), "update ROSTER"
    (root / "manifest.json").write_text(json.dumps(
        {"generator": GENERATOR_VERSION, "seed": SEED, "versions": _versions(),
         "fixtures": [{"name": s.name, "format": s.format, "file": str(s.path(root).relative_to(root)),
                       "pages": len(s.pages), "description": s.description} for s in b.specs]}, indent=1))
    return b.specs


_SPECS: list[FixtureSpec] | None = None


def specs(root: Path = ROOT) -> list[FixtureSpec]:
    """Every fixture, built once per test run. Qt must already have a QGuiApplication: the PDFs are drawn with it."""
    global _SPECS
    if _SPECS is None:
        _SPECS = build(root)
    return _SPECS
