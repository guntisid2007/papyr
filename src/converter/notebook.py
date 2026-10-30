"""Render a Jupyter notebook (nbformat 4) to PDF bytes with Qt's text engine, entirely offline.

QTextDocument loads images only from resources registered here and from local files next to the
notebook. It has no network access, so a notebook that links to the web cannot make Papyr fetch anything.
"""

import base64
import binascii
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QCoreApplication, QIODevice, QLocale, QMarginsF, QRectF, QSizeF, QUrl
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QFontInfo, QGuiApplication, QImage, QPageLayout, QPageSize,
                           QPainter, QPdfWriter, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument,
                           QTextDocumentFragment, QTextFrameFormat, QTextImageFormat)

from .formats import ImageLoadError
from .layout import PageSize, PdfSettings

ERROR = "error"
MIME_PRIORITY = ("image/png", "image/jpeg", "text/html", "text/markdown", "text/plain")
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_CSS_DPI = 96  # Jupyter shows an image pixel as one CSS pixel; the PDF writer also works in CSS pixels
_BODY_PT = 10.5
_CODE_PT = 9
_CELL_GAP = 10


@dataclass(frozen=True)
class Output:
    mime: str  # one of MIME_PRIORITY, or ERROR
    data: str | bytes  # bytes for images


@dataclass(frozen=True)
class Cell:
    kind: str  # "markdown", "code", or "raw"
    source: str
    execution_count: int | None = None
    outputs: tuple[Output, ...] = ()
    attachments: dict[str, bytes] = field(default_factory=dict)


def _text(value) -> str:
    """nbformat stores multiline strings as a str or a list of str."""
    if isinstance(value, list):
        return "".join(str(part) for part in value)
    return value if isinstance(value, str) else ""


def _parse_output(raw: dict) -> Output | None:
    kind = raw.get("output_type")
    if kind == "stream":
        return Output("text/plain", _ANSI.sub("", _text(raw.get("text"))))
    if kind == ERROR:
        traceback = "\n".join(_text(line) for line in raw.get("traceback") or [])
        return Output(ERROR, _ANSI.sub("", traceback or f"{raw.get('ename', 'Error')}: {raw.get('evalue', '')}"))
    if kind in ("execute_result", "display_data"):
        bundle = raw.get("data") or {}
        for mime in MIME_PRIORITY:
            if mime in bundle:
                text = _text(bundle[mime])
                return Output(mime, base64.b64decode(text) if mime.startswith("image/") else _ANSI.sub("", text))
    return None


def _parse_cell(raw: dict) -> Cell | None:
    kind = raw.get("cell_type")
    source = _text(raw.get("source"))
    if kind == "markdown":
        attachments = {name: base64.b64decode(_text(data))
                       for name, bundle in (raw.get("attachments") or {}).items()
                       for mime, data in bundle.items() if mime.startswith("image/")}
        return Cell(kind, source, attachments=attachments)
    if kind == "code":
        outputs = tuple(o for o in map(_parse_output, raw.get("outputs") or []) if o is not None)
        count = raw.get("execution_count")
        return Cell(kind, source, count if isinstance(count, int) else None, outputs)
    if kind == "raw":
        return Cell(kind, source)
    return None


def parse_notebook(raw: bytes) -> list[Cell]:
    try:
        notebook = json.loads(raw)
    except ValueError as exc:
        raise ImageLoadError(f"Not a valid notebook: {exc}") from exc
    if not isinstance(notebook, dict) or notebook.get("nbformat") != 4:
        raise ImageLoadError("Only Jupyter notebooks in format 4 are supported")
    if not isinstance(notebook.get("cells"), list):
        raise ImageLoadError("Notebook has no list of cells")
    try:
        cells = [cell for cell in map(_parse_cell, notebook["cells"]) if cell is not None]
    except (AttributeError, TypeError, binascii.Error) as exc:
        raise ImageLoadError(f"Notebook is damaged: {exc}") from exc
    if not cells:
        raise ImageLoadError("Notebook has no cells")
    return cells


def _fixed_font() -> QFont:
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    if not QFontInfo(font).fixedPitch():  # headless Qt on macOS names a "monospace" family that does not exist
        fixed = [family for family in QFontDatabase.families() if QFontDatabase.isFixedPitch(family)]
        font.setFamilies(fixed[:1] or font.families())
    font.setPointSizeF(_CODE_PT)
    return font


class _Builder:
    """Appends cells to one QTextDocument laid out for the PDF writer."""

    def __init__(self, doc: QTextDocument):
        self.doc = doc
        self.cursor = QTextCursor(doc)
        self.body = QTextCharFormat()
        self.mono = QTextCharFormat()
        self.mono.setFont(_fixed_font())
        self.gap = 0.0  # space before the next block, set at each cell boundary
        self._images = 0

    def block(self, top_margin: float = 0, char_format: QTextCharFormat | None = None) -> None:
        block_format = QTextBlockFormat()
        block_format.setTopMargin(top_margin + self.gap)
        self.gap = 0.0
        if self.doc.isEmpty():
            self.cursor.setBlockFormat(block_format)
            self.cursor.setBlockCharFormat(char_format or self.body)
        else:
            self.cursor.insertBlock(block_format, char_format or self.body)

    def mono_text(self, text: str, color: str | None = None) -> None:
        char_format = QTextCharFormat(self.mono)
        if color:
            char_format.setForeground(QColor(color))
        self.block(4, char_format)
        self.cursor.insertText(text.rstrip("\n"), char_format)

    def markdown(self, text: str) -> None:
        source = QTextDocument()
        source.setMarkdown(text)
        self.block()
        self.cursor.insertFragment(QTextDocumentFragment(source))

    def add_image(self, name: str, data: bytes) -> bool:
        image = QImage.fromData(data)
        if not image.isNull():
            self.doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), image)
        return not image.isNull()

    def image(self, data: bytes) -> None:
        self._images += 1
        name = f"output:{self._images}"
        if self.add_image(name, data):
            image_format = QTextImageFormat()
            image_format.setName(name)
            self.block(4)
            self.cursor.insertImage(image_format)


def _markdown_cell(builder: _Builder, cell: Cell) -> None:
    for name, data in cell.attachments.items():
        builder.add_image(f"attachment:{name}", data)
    builder.markdown(cell.source)


def _code_cell(builder: _Builder, cell: Cell) -> None:
    prompt = QTextCharFormat()
    prompt.setForeground(QColor("#8a8a8a"))
    prompt.setFontPointSize(_CODE_PT - 1)
    builder.block(0, prompt)
    builder.cursor.insertText(f"[{cell.execution_count or ' '}]", prompt)
    frame = QTextFrameFormat()
    frame.setBackground(QColor("#f5f6f8"))
    frame.setBorder(0.75)
    frame.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
    frame.setBorderBrush(QColor("#dde1e6"))
    frame.setPadding(6)
    frame.setTopMargin(2)
    builder.cursor.insertFrame(frame)
    builder.cursor.setBlockCharFormat(builder.mono)
    builder.cursor.insertText(cell.source.rstrip("\n"), builder.mono)
    builder.cursor.movePosition(QTextCursor.MoveOperation.End)
    for output in cell.outputs:
        _OUTPUT_RENDERERS[output.mime](builder, output.data)


def _raw_cell(builder: _Builder, cell: Cell) -> None:
    builder.mono_text(cell.source)


def _html(builder: _Builder, html: str) -> None:
    builder.block(4)
    builder.cursor.insertHtml(html)


def _markdown(builder: _Builder, text: str) -> None:
    builder.markdown(text)


_CELL_RENDERERS: dict[str, Callable[[_Builder, Cell], None]] = {
    "markdown": _markdown_cell, "code": _code_cell, "raw": _raw_cell}
_OUTPUT_RENDERERS: dict[str, Callable[[_Builder, str | bytes], None]] = {
    "image/png": _Builder.image, "image/jpeg": _Builder.image, "text/html": _html, "text/markdown": _markdown,
    "text/plain": _Builder.mono_text, ERROR: lambda builder, text: builder.mono_text(text, "#a31515")}


def _logical_dpi() -> int:
    """Qt sizes text-document images in its default DPI, which depends on the platform (72 on macOS, 96 elsewhere).
    A 72 pt font is exactly that many pixels at that DPI."""
    font = QFont()
    font.setPointSizeF(72)
    return QFontInfo(font).pixelSize()


def _resource_image(doc: QTextDocument, name: str) -> QImage:
    resource = doc.resource(QTextDocument.ResourceType.ImageResource, QUrl(name))
    if isinstance(resource, QImage):
        return resource
    if isinstance(resource, (QByteArray, bytes)):
        return QImage.fromData(resource)
    return QImage()


def _fit_images(doc: QTextDocument, max_width_in: float) -> None:
    """Show each image at its natural size, scaled down (never up) to fit the text width."""
    dpi = _logical_dpi()
    images = []
    block = doc.begin()
    while block.isValid():
        fragments = block.begin()
        while not fragments.atEnd():
            fragment = fragments.fragment()
            if fragment.charFormat().isImageFormat():
                images.append((fragment.position(), fragment.length(), fragment.charFormat().toImageFormat()))
            fragments += 1
        block = block.next()
    cursor = QTextCursor(doc)
    for position, length, image_format in images:
        image = _resource_image(doc, image_format.name())
        if image.isNull():
            continue
        natural_in = image_format.width() / dpi if image_format.width() > 0 else image.width() / _CSS_DPI
        width_in = min(natural_in, max_width_in)
        image_format.setWidth(width_in * dpi)
        image_format.setHeight(width_in * dpi * image.height() / image.width())
        cursor.setPosition(position)
        cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(image_format)


def _page_layout(settings: PdfSettings) -> QPageLayout:
    page = settings.page_size
    if page.dimensions is None:  # a notebook has no natural page size, so use the reader's paper
        imperial = QLocale().measurementSystem() == QLocale.MeasurementSystem.ImperialUSSystem
        page = PageSize.LETTER if imperial else PageSize.A4
    margin = settings.margin_pt
    width, height = page.dimensions
    if width <= 2 * margin or height <= 2 * margin:
        raise ValueError(f"A {settings.margin_mm:g} mm margin leaves no room on the page")
    return QPageLayout(QPageSize(QSizeF(width, height), QPageSize.Unit.Point, page.label),
                       QPageLayout.Orientation.Portrait, QMarginsF(margin, margin, margin, margin),
                       QPageLayout.Unit.Point, QMarginsF())


def render_notebook(path: Path, settings: PdfSettings) -> bytes:
    """Lay out every cell and its saved outputs as searchable text pages. Needs a running QGuiApplication."""
    if not isinstance(QCoreApplication.instance(), QGuiApplication):
        raise ImageLoadError("Notebooks can only be rendered while Papyr is running")
    cells = parse_notebook(path.read_bytes())

    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    writer = QPdfWriter(buffer)
    writer.setResolution(_CSS_DPI)
    writer.setPageLayout(_page_layout(settings))
    body = writer.pageLayout().paintRectPixels(_CSS_DPI)

    doc = QTextDocument()
    doc.documentLayout().setPaintDevice(writer)
    doc.setUseDesignMetrics(True)
    doc.setDocumentMargin(0)
    doc.setPageSize(QSizeF(body.width(), body.height()))
    doc.setBaseUrl(QUrl.fromLocalFile(f"{path.parent.resolve()}/"))
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    font.setPointSizeF(_BODY_PT)
    doc.setDefaultFont(font)

    builder = _Builder(doc)
    for index, cell in enumerate(cells):
        builder.gap = _CELL_GAP if index else 0
        _CELL_RENDERERS[cell.kind](builder, cell)
    _fit_images(doc, body.width() / _CSS_DPI)

    painter = QPainter(writer)
    for page in range(doc.pageCount()):
        if page:
            writer.newPage()
        painter.save()
        painter.translate(0, -page * body.height())
        doc.drawContents(painter, QRectF(0, page * body.height(), body.width(), body.height()))
        painter.restore()
    painter.end()
    buffer.close()
    return bytes(data)
