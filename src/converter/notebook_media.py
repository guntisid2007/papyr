"""Turn the parts of a notebook Qt's text engine can't draw (LaTeX math and SVG) into images, offline.

Math is typeset by ziamath with its bundled STIX font. SVG is drawn by Qt SVG, which runs no scripts and, once
external references are stripped here, reads nothing but the markup itself.
"""

import math
import re
from dataclasses import dataclass

import ziamath
from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ziamath.config.svg2 = False  # SVG 2 symbols are invisible to Qt SVG, which draws only SVG 1.2 Tiny

_SCALE = 4  # raster pixels per CSS pixel, so math and SVG stay crisp at 384 dpi
_MATH_PT = 10.5
_MAX_PIXELS = 40_000_000  # caps memory for a huge SVG at the cost of resolution

# Fenced code and inline code are copied untouched so a "$" in code is never read as math.
_MARKDOWN_MATH = re.compile(
    r"(?P<fence>^[ ]{0,3}(?P<mark>`{3,}|~{3,})[^\n]*\n.*?(?:^[ ]{0,3}(?P=mark)[ \t]*$|\Z))"
    r"|(?P<code>(?P<ticks>`+).+?(?P=ticks))"
    r"|(?P<escaped>\\\$)"
    r"|(?P<bare>!\[\]\()"
    r"|\$\$(?P<dollars>.+?)\$\$"
    r"|\\\[(?P<brackets>.+?)\\\]"
    r"|(?P<env>\\begin\{(?P<name>equation|align|gather|multline|eqnarray)\*?\}.*?\\end\{(?P=name)\*?\})"
    r"|\\\((?P<parens>.+?)\\\)"
    r"|(?<![\\$\w])\$(?P<inline>[^\s$](?:[^$\n]|\n(?!\s*\n))*?(?<![\s\\]))\$(?![\w$])",
    re.DOTALL | re.MULTILINE)
_EXTERNAL_REF = re.compile(r"""\s(?:xlink:)?href\s*=\s*(["'])(?!data:|#).*?\1""", re.IGNORECASE | re.DOTALL)
_ACTIVE_SVG = re.compile(r"<(script|foreignObject)\b.*?(</\1\s*>|/>)", re.IGNORECASE | re.DOTALL)


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
        if match["fence"] or match["code"]:
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
        svg = ziamath.Latex(formula.latex, size=_MATH_PT * 96 / 72, inline=not formula.display).svg()
    except Exception:  # noqa: BLE001 - any LaTeX ziamath can't handle falls back to showing the source
        return None
    return render_svg(svg)


def safe_svg(svg: str) -> str:
    """Drop scripts, embedded HTML, and every reference to a file or URL, keeping inline data and local ids."""
    return _EXTERNAL_REF.sub("", _ACTIVE_SVG.sub("", svg))


def render_svg(svg: str) -> Picture | None:
    renderer = QSvgRenderer(QByteArray(safe_svg(svg).encode()))
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
