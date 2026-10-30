"""Turn the parts of a notebook Qt's text engine can't draw (LaTeX math and SVG) into images, offline.

Math is typeset by ziamath with its bundled STIX font. SVG is drawn by Qt SVG, which runs no scripts. Every image
a notebook carries is decoded here, so Qt never guesses a format: an SVG hidden behind a PNG label could otherwise
reach Qt's SVG reader without the clean-up below, which keeps it from reading any file.
"""

import base64
import binascii
import math
import re
import threading
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass

import ziamath
from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ziamath.config.svg2 = False  # SVG 2 symbols are invisible to Qt SVG, which draws only SVG 1.2 Tiny

_SCALE = 4  # raster pixels per CSS pixel, so math and SVG stay crisp at 384 dpi
_MATH_PT = 10.5
_MAX_PIXELS = 40_000_000  # caps memory for a huge SVG at the cost of resolution

_MATH_LOCK = threading.Lock()  # ziamath shares one font reader, so two threads typesetting at once corrupt it

# Fenced, indented, and inline code are copied untouched so a "$" in code is never read as math.
_MARKDOWN_MATH = re.compile(
    r"(?P<fence>^[ ]{0,3}(?P<mark>(?P<fch>[`~])(?P=fch){2,})[^\n]*\n.*?(?:^[ ]{0,3}(?P=mark)(?P=fch)*[ \t]*$|\Z))"
    r"|(?P<indented>(?:\A|(?<=\n\n))(?:(?: {4}|\t)[^\n]*(?:\n|\Z))+)"
    r"|(?P<code>(?P<ticks>`+).+?(?P=ticks))"
    r"|(?P<escaped>\\\$)"
    r"|(?P<bare>!\[\]\()"
    r"|\$\$(?P<dollars>.+?)\$\$"
    r"|\\\[(?P<brackets>.+?)\\\]"
    r"|(?P<env>\\begin\{(?P<name>equation|align|gather|multline|eqnarray)\*?\}.*?\\end\{(?P=name)\*?\})"
    r"|\\\((?P<parens>.+?)\\\)"
    r"|(?<![\\$\w])\$(?P<inline>[^\s$](?:[^$\n]|\n(?!\s*\n))*?(?<![\s\\]))\$(?![\w$])",
    re.DOTALL | re.MULTILINE)
_DOCTYPE = re.compile(r"<!DOCTYPE[^\[>]*(?:\[.*?\])?\s*>", re.IGNORECASE | re.DOTALL)
_DATA_URL = re.compile(r"data:image/(?:png|jpeg|gif);base64,(.*)", re.IGNORECASE | re.DOTALL)
_OUTSIDE_URL = re.compile(r"url\(\s*['\"]?\s*(?!#)|@import", re.IGNORECASE)
_DROPPED_ELEMENTS = {"script", "foreignObject"}
_RASTER_MAGIC = ((b"\x89PNG\r\n\x1a\n", "PNG"), (b"\xff\xd8\xff", "JPEG"), (b"GIF87a", "GIF"), (b"GIF89a", "GIF"),
                 (b"BM", "BMP"))
ElementTree.register_namespace("", "http://www.w3.org/2000/svg")
ElementTree.register_namespace("xlink", "http://www.w3.org/1999/xlink")


@dataclass(frozen=True)
class Picture:
    image: QImage
    width: float  # natural size in CSS pixels
    height: float


@dataclass(frozen=True)
class Formula:
    latex: str
    display: bool


def prepare_markdown(markdown: str) -> tuple[str, list[Formula]]:
    """Replace each formula with a numbered placeholder image link, and return the formulas in order. Images get
    alt text, because Qt's Markdown reader drops an image whose alt text is empty."""
    found: list[Formula] = []

    def replace(match: re.Match) -> str:
        if match["fence"] or match["indented"] or match["code"]:
            return match[0]
        if match["escaped"]:
            return "\\$"
        if match["bare"]:
            return "![image]("
        display = match["inline"] is None and match["parens"] is None
        latex = next(group for group in (match["dollars"], match["brackets"], match["env"], match["parens"],
                                         match["inline"]) if group is not None)
        found.append(Formula(latex.strip(), display))
        link = math_link(len(found) - 1)
        return f"\n\n{link}\n\n" if display else link

    return _MARKDOWN_MATH.sub(replace, markdown), found


def math_name(index: int) -> str:
    return f"math:{index}"


def math_link(index: int) -> str:
    return f"![formula]({math_name(index)})"


def render_math(formula: Formula) -> Picture | None:
    """Typeset LaTeX, or None when ziamath can't parse it so the caller can show the source instead."""
    try:
        with _MATH_LOCK:
            svg = ziamath.Latex(formula.latex, size=_MATH_PT * 96 / 72, inline=not formula.display).svg()
    except Exception:  # noqa: BLE001 - any LaTeX ziamath can't handle falls back to showing the source
        return None
    return render_svg(svg)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _is_raster_data(url: str) -> bool:
    """An inline image whose bytes really are PNG, JPEG, or GIF, whatever its label says."""
    match = _DATA_URL.match(url.strip())
    if not match:
        return False
    try:
        data = base64.b64decode("".join(match[1].split()), validate=True)
    except (binascii.Error, ValueError):
        return False
    return any(data.startswith(magic) for magic, image_format in _RASTER_MAGIC if image_format != "BMP")


def safe_svg(svg: str) -> str | None:
    """The SVG with scripts, embedded HTML, style sheets that load anything, and every reference to a file, URL, or
    nested SVG removed. Only links to ids inside the drawing and inline PNG, JPEG, or GIF data remain. None when it
    isn't valid XML."""
    try:
        root = ElementTree.fromstring(_DOCTYPE.sub("", svg, count=1))  # drops processing instructions too
    except ElementTree.ParseError:
        return None
    for parent in list(root.iter()):
        for child in list(parent):
            name = _local_name(child.tag) if isinstance(child.tag, str) else ""
            if name in _DROPPED_ELEMENTS or (name == "style" and _OUTSIDE_URL.search(child.text or "")):
                parent.remove(child)
    for element in root.iter():
        for attribute, value in list(element.attrib.items()):
            is_link = _local_name(attribute).lower() == "href"
            if (is_link and not (value.startswith("#") or _is_raster_data(value))) or \
                    (not is_link and _OUTSIDE_URL.search(value)):
                del element.attrib[attribute]
    return ElementTree.tostring(root, encoding="unicode")


def decode_image(data: bytes) -> QImage:
    """A PNG, JPEG, GIF, WebP, or BMP read with its format named, or a sanitized SVG; a null image otherwise."""
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return QImage.fromData(data, "WEBP")
    for magic, image_format in _RASTER_MAGIC:
        if data.startswith(magic):
            return QImage.fromData(data, image_format)
    head = data[:2048].lstrip().lower()
    if head.startswith((b"<svg", b"<?xml", b"<!doctype svg", b"<!--")) and b"<svg" in data[:65536].lower():
        picture = render_svg(data.decode("utf-8", "replace"))
        return picture.image if picture else QImage()
    return QImage()


def render_svg(svg: str) -> Picture | None:
    cleaned = safe_svg(svg)
    if cleaned is None:
        return None
    renderer = QSvgRenderer(QByteArray(cleaned.encode()))
    size = renderer.defaultSize()
    if not renderer.isValid() or size.isEmpty():
        return None
    scale = min(_SCALE, math.sqrt(_MAX_PIXELS / (size.width() * size.height())))
    image = QImage(max(1, round(size.width() * scale)), max(1, round(size.height() * scale)),
                   QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter, QRectF(image.rect()))
    painter.end()
    return Picture(image, float(size.width()), float(size.height()))
