"""Render a Jupyter notebook (nbformat 4) to PDF bytes with Qt's text engine, entirely offline.

Only the saved outputs are drawn; no cell is ever run. The document loads images only from resources registered
here, inline data, and files inside the notebook's own folder. It has no network access, so a notebook that links
to the web cannot make Papyr fetch anything.
"""

import base64
import json
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.styles import get_style_by_name
from pygments.token import _TokenType
from pygments.util import ClassNotFound
from PySide6.QtCore import (QBuffer, QByteArray, QCoreApplication, QIODevice, QLocale, QMarginsF, QRectF, QSizeF, Qt,
                            QUrl)
from PySide6.QtGui import (QAbstractTextDocumentLayout, QColor, QFont, QFontDatabase, QFontInfo, QGuiApplication,
                           QImage, QPageLayout, QPageSize, QPainter, QPalette, QPdfWriter, QTextBlockFormat,
                           QTextCharFormat, QTextCursor, QTextDocument, QTextDocumentFragment,
                           QTextFragment, QTextFrame, QTextFrameFormat, QTextImageFormat, QTextLength,
                           QTextOption, QTextTable)

from .formats import ImageLoadError
from .layout import PageSize, PdfSettings
from .notebook_media import (Picture, decode_image, math_link, math_name, prepare_markdown, render_math,
                             render_svg)

ERROR = "error"
NOTE = "note"  # an output Papyr can't draw, named so the reader knows something was there
MIME_PRIORITY = ("image/png", "image/jpeg", "image/svg+xml", "text/html", "text/markdown", "text/latex",
                 "text/plain")
_IMAGE_MIMES = ("image/png", "image/jpeg")
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_SCRIPT = re.compile(r"<(script|style)\b.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<(?!img\b)[^>]*>", re.IGNORECASE)
_CSS_DPI = 96  # Jupyter shows an image pixel as one CSS pixel; the PDF writer also works in CSS pixels
_BODY_PT = 10.5
_CODE_PT = 9
_CELL_GAP = 10
_CELL_CHROME_IN = 0.1  # a table cell's padding and borders, kept free so a fitted image never overhangs
_INK = QColor("#1f2328")
_LINK = QColor("#0b5cad")
_MUTED = QColor("#8a8a8a")
_ERROR_INK = QColor("#a31515")
_CODE_STYLE = get_style_by_name("default")


@dataclass(frozen=True)
class Output:
    mime: str  # one of MIME_PRIORITY, ERROR, or NOTE
    data: str | bytes  # bytes for PNG and JPEG
    width: float | None = None  # display width in CSS pixels, from the output's metadata (retina figures)


@dataclass(frozen=True)
class Cell:
    kind: str  # "markdown", "code", or "raw"
    source: str
    execution_count: int | None = None
    outputs: tuple[Output, ...] = ()
    attachments: dict[str, bytes] = field(default_factory=dict)


@dataclass(frozen=True)
class Notebook:
    cells: tuple[Cell, ...]
    language: str  # the kernel's language, for highlighting code cells


def _text(value) -> str:
    """nbformat stores multiline strings as a str or a list of str."""
    if isinstance(value, list):
        return "".join(str(part) for part in value)
    return value if isinstance(value, str) else ""


def _display_width(raw: dict, mime: str) -> float | None:
    width = ((raw.get("metadata") or {}).get(mime) or {}).get("width")
    return float(width) if isinstance(width, (int, float)) and width > 0 else None


def _shows_something(html: str) -> bool:
    """Whether HTML has text or an image once scripts are gone. Interactive plots and widgets are an empty element
    that JavaScript fills, and Papyr runs no JavaScript."""
    return bool(_TAG.sub("", _SCRIPT.sub("", html)).strip())


def _pick_mime(bundle: dict) -> str | None:
    """The richest format Papyr draws, skipping HTML that would come out empty when a static fallback exists."""
    available = [mime for mime in MIME_PRIORITY if mime in bundle]
    for index, mime in enumerate(available):
        if mime == "text/html" and index + 1 < len(available) and not _shows_something(_text(bundle[mime])):
            continue
        return mime
    return None


def _parse_output(raw: dict) -> Output | None:
    kind = raw.get("output_type")
    if kind == "stream":
        text = _ANSI.sub("", _text(raw.get("text")))
        return Output("text/plain", text) if text.strip() else None
    if kind == ERROR:
        traceback = "\n".join(_text(line) for line in raw.get("traceback") or [])
        return Output(ERROR, _ANSI.sub("", traceback or f"{raw.get('ename', 'Error')}: {raw.get('evalue', '')}"))
    if kind in ("execute_result", "display_data"):
        bundle = raw.get("data") or {}
        mime = _pick_mime(bundle)
        if mime is None:
            return Output(NOTE, f"Output not shown ({', '.join(sorted(bundle))})") if bundle else None
        text = _text(bundle[mime])
        if mime in _IMAGE_MIMES:
            return Output(mime, base64.b64decode(text), _display_width(raw, mime))
        return Output(mime, text if mime == "image/svg+xml" else _ANSI.sub("", text), _display_width(raw, mime))
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


def _language(metadata) -> str:
    if not isinstance(metadata, dict):
        return "python"
    info = metadata.get("language_info") or {}
    kernel = metadata.get("kernelspec") or {}
    name = (info.get("name") if isinstance(info, dict) else None) or \
        (kernel.get("language") if isinstance(kernel, dict) else None)
    return name if isinstance(name, str) and name else "python"


def parse_notebook(raw: bytes) -> Notebook:
    try:
        notebook = json.loads(raw)
    except ValueError as exc:
        raise ImageLoadError(f"Not a valid notebook: {exc}") from exc
    if not isinstance(notebook, dict) or notebook.get("nbformat") != 4:
        raise ImageLoadError("Only Jupyter notebooks in format 4 are supported")
    if not isinstance(notebook.get("cells"), list):
        raise ImageLoadError("Notebook has no list of cells")
    try:
        cells = tuple(cell for cell in map(_parse_cell, notebook["cells"])
                      if cell is not None and (cell.source.strip() or cell.outputs))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ImageLoadError(f"Notebook is damaged: {exc}") from exc
    if not cells:
        raise ImageLoadError("Notebook has no cells with any content")
    return Notebook(cells, _language(notebook.get("metadata")))


def _fixed_font() -> QFont:
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    if not QFontInfo(font).fixedPitch():  # headless Qt on macOS names a "monospace" family that does not exist
        fixed = [family for family in QFontDatabase.families() if QFontDatabase.isFixedPitch(family)]
        font.setFamilies(fixed[:1] or font.families())
    font.setPointSizeF(_CODE_PT)
    return font


def _fragments(doc: QTextDocument) -> Iterator[QTextFragment]:
    """Every run of same-format text in the document, frames and tables included."""
    block = doc.begin()
    while block.isValid():
        fragments = block.begin()
        while not fragments.atEnd():
            yield fragments.fragment()
            fragments += 1
        block = block.next()


def _set_format(doc: QTextDocument, changes: list[tuple[int, int, QTextCharFormat]]) -> None:
    cursor = QTextCursor(doc)
    for position, length, char_format in changes:
        cursor.setPosition(position)
        cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(char_format)


def _scope_images(doc: QTextDocument, prefix: str, display: set[str]) -> None:
    """Attachment and formula names are scoped to their cell, so give each a document-unique name. Display formulas
    are centered on their own line; inline ones sit on the middle of the text line."""
    changes = []
    cursor = QTextCursor(doc)
    for fragment in _fragments(doc):
        image = fragment.charFormat().toImageFormat()
        name = image.name()
        if not fragment.charFormat().isImageFormat() or not name.startswith(("attachment:", "math:")):
            continue
        if name in display:
            cursor.setPosition(fragment.position())
            block_format = cursor.blockFormat()
            block_format.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            cursor.setBlockFormat(block_format)
        elif name.startswith("math:"):
            image.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignMiddle)
        image.setName(prefix + name)
        changes.append((fragment.position(), fragment.length(), image))
    _set_format(doc, changes)


def _code_span(text: str) -> str:
    ticks = "`" * (max((len(run) for run in re.findall("`+", text)), default=0) + 1)
    return f"{ticks} {text} {ticks}"


def _data_payload(url: QUrl) -> bytes:
    header, _, payload = url.toString(QUrl.ComponentFormattingOption.FullyEncoded).partition(",")
    try:
        return base64.b64decode(payload) if header.endswith(";base64") else \
            QUrl.fromPercentEncoding(payload.encode()).encode()
    except ValueError:
        return b""


def _nothing() -> QImage:
    """What a refused image resolves to. Answering None would make Qt load the name as a file path itself."""
    image = QImage(1, 1, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    return image


class _NotebookDocument(QTextDocument):
    """Loads registered images and inline data, plus image files inside the notebook's folder and nothing else, so a
    notebook can't pull an unrelated private image from elsewhere on the disk into the PDF. Every image is decoded by
    decode_image, which names the format, so Qt never sniffs one and never reads an SVG's references."""

    def __init__(self, folder: Path):
        super().__init__()
        self._folder = folder.resolve()
        self.setBaseUrl(QUrl.fromLocalFile(f"{self._folder}/"))

    def loadResource(self, kind: int, url: QUrl):
        if kind != QTextDocument.ResourceType.ImageResource:
            return QByteArray()  # style sheets and anything else a notebook's HTML links to
        image = decode_image(self._read(url))
        return _nothing() if image.isNull() else image

    def _read(self, url: QUrl) -> bytes:
        if url.scheme() == "data":
            return _data_payload(url)
        if url.scheme() not in ("", "file"):
            return b""
        target = Path(url.toLocalFile() if url.isLocalFile() else url.path())
        target = (self._folder / target).resolve()
        if not target.is_relative_to(self._folder) or not target.is_file():
            return b""
        try:
            return target.read_bytes()
        except OSError:
            return b""


class _Builder:
    """Appends cells to one QTextDocument laid out for the PDF writer."""

    def __init__(self, doc: QTextDocument, language: str):
        self.doc = doc
        self.cursor = QTextCursor(doc)
        self.body = QTextCharFormat()
        self.mono = QTextCharFormat()
        self.mono.setFont(_fixed_font())
        self.gap = 0.0  # space before the next block, set at each cell boundary
        self.widths: dict[str, float] = {}  # natural width in CSS pixels of each image registered here
        self._images = 0
        self._cells = 0
        try:
            self._lexer = get_lexer_by_name(language, stripnl=False, ensurenl=False)
        except ClassNotFound:
            self._lexer = TextLexer(stripnl=False, ensurenl=False)
        self._token_formats: dict[_TokenType, QTextCharFormat] = {}

    def block(self, top_margin: float = 0, char_format: QTextCharFormat | None = None) -> None:
        block_format = QTextBlockFormat()
        block_format.setTopMargin(top_margin + self.gap)
        self.gap = 0.0
        if self.doc.isEmpty():
            self.cursor.setBlockFormat(block_format)
            self.cursor.setBlockCharFormat(char_format or self.body)
        else:
            self.cursor.insertBlock(block_format, char_format or self.body)

    def mono_text(self, text: str, color: QColor | None = None) -> None:
        char_format = QTextCharFormat(self.mono)
        if color:
            char_format.setForeground(color)
        self.block(4, char_format)
        self.cursor.insertText(text.rstrip("\n").expandtabs(4), char_format)

    def note(self, text: str) -> None:
        char_format = QTextCharFormat(self.body)
        char_format.setForeground(_MUTED)
        char_format.setFontItalic(True)
        self.block(4, char_format)
        self.cursor.insertText(text, char_format)

    def markdown(self, text: str, attachments: dict[str, bytes] | None = None) -> None:
        self._cells += 1
        prefix = f"cell{self._cells}-"
        text, formulas = prepare_markdown(text)
        display = set()
        for index, formula in enumerate(formulas):
            name = math_name(index)
            picture = render_math(formula)
            if picture is None:
                text = text.replace(math_link(index), _code_span(formula.latex), 1)
                continue
            self.add_picture(prefix + name, picture)
            if formula.display:
                display.add(name)
        for name, data in (attachments or {}).items():
            self.add_image(f"{prefix}attachment:{name}", data)
        source = QTextDocument()
        source.setMarkdown(text)
        _scope_images(source, prefix, display)
        self.block()
        self.cursor.insertFragment(QTextDocumentFragment(source))

    def add_image(self, name: str, data: bytes, width: float | None = None) -> bool:
        image = decode_image(data)
        if image.isNull():
            return False
        self.add_picture(name, Picture(image, width or image.width(), 0))
        return True

    def add_picture(self, name: str, picture: Picture) -> None:
        self.doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), picture.image)
        self.widths[name] = picture.width

    def insert_image(self, name: str) -> None:
        image_format = QTextImageFormat()
        image_format.setName(name)
        self.block(4)
        self.cursor.insertImage(image_format)

    def output_image(self, output: Output) -> None:
        self._images += 1
        name = f"output:{self._images}"
        if self.add_image(name, output.data, output.width):
            self.insert_image(name)
        else:
            self.note(f"Image not shown ({output.mime} could not be decoded)")

    def output_svg(self, output: Output) -> None:
        self._images += 1
        name = f"output:{self._images}"
        picture = render_svg(output.data)
        if picture is None:
            self.note("Image not shown (image/svg+xml could not be drawn)")
            return
        if output.width:
            picture = Picture(picture.image, output.width, 0)
        self.add_picture(name, picture)
        self.insert_image(name)

    def code(self, source: str) -> None:
        frame = QTextFrameFormat()
        frame.setBackground(QColor("#f5f6f8"))
        frame.setBorder(0.75)
        frame.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
        frame.setBorderBrush(QColor("#dde1e6"))
        frame.setPadding(6)
        frame.setTopMargin(2)
        self.cursor.insertFrame(frame)
        self.cursor.setBlockCharFormat(self.mono)
        for token, text in self._lexer.get_tokens(source.rstrip("\n").expandtabs(4)):
            self.cursor.insertText(text, self._token_format(token))
        self.cursor.movePosition(QTextCursor.MoveOperation.End)

    def _token_format(self, token: _TokenType) -> QTextCharFormat:
        """Color and italics from the Jupyter-like default style. Bold is left out because Qt fakes it for a
        monospace face without a bold weight by drawing each glyph twice, which doubles the words in copied text."""
        char_format = self._token_formats.get(token)
        if char_format is None:
            style = _CODE_STYLE.style_for_token(token)
            char_format = QTextCharFormat(self.mono)
            if style["color"]:
                char_format.setForeground(QColor(f"#{style['color']}"))
            char_format.setFontItalic(bool(style["italic"]))
            self._token_formats[token] = char_format
        return char_format


def _markdown_cell(builder: _Builder, cell: Cell) -> None:
    builder.markdown(cell.source, cell.attachments)


def _code_cell(builder: _Builder, cell: Cell) -> None:
    prompt = QTextCharFormat()
    prompt.setForeground(_MUTED)
    prompt.setFontPointSize(_CODE_PT - 1)
    builder.block(0, prompt)
    builder.cursor.insertText(f"[{cell.execution_count or ' '}]", prompt)
    builder.code(cell.source)
    for output in cell.outputs:
        _OUTPUT_RENDERERS[output.mime](builder, output)


def _raw_cell(builder: _Builder, cell: Cell) -> None:
    builder.mono_text(cell.source)


def _html(builder: _Builder, output: Output) -> None:
    builder.block(4)
    builder.cursor.insertHtml(output.data)


_CELL_RENDERERS: dict[str, Callable[[_Builder, Cell], None]] = {
    "markdown": _markdown_cell, "code": _code_cell, "raw": _raw_cell}
_OUTPUT_RENDERERS: dict[str, Callable[[_Builder, Output], None]] = {
    "image/png": _Builder.output_image, "image/jpeg": _Builder.output_image, "image/svg+xml": _Builder.output_svg,
    "text/html": _html, "text/markdown": lambda builder, output: builder.markdown(output.data),
    "text/latex": lambda builder, output: builder.markdown(output.data),
    "text/plain": lambda builder, output: builder.mono_text(output.data),
    ERROR: lambda builder, output: builder.mono_text(output.data, _ERROR_INK),
    NOTE: lambda builder, output: builder.note(output.data)}


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
        return decode_image(bytes(resource))
    return QImage()


def _finish(doc: QTextDocument, widths: dict[str, float], max_width_in: float, max_height_in: float) -> None:
    """Show each image at its natural size, scaled down (never up) to fit the text area, so no figure is cut at a
    page edge. Links get a print color, since Qt colors them from the app's theme, which may be dark."""
    dpi = _logical_dpi()
    _fit_tables(doc.rootFrame(), max_width_in * _CSS_DPI)
    cursor = QTextCursor(doc)
    changes = []
    for fragment in _fragments(doc):
        char_format = fragment.charFormat()
        if char_format.isAnchor() and not char_format.isImageFormat():
            char_format.setForeground(_LINK)
            changes.append((fragment.position(), fragment.length(), char_format))
            continue
        if not char_format.isImageFormat():
            continue
        image_format = char_format.toImageFormat()
        image = _resource_image(doc, image_format.name())
        if image.isNull():
            continue
        if image_format.name() in widths:
            natural_in = widths[image_format.name()] / _CSS_DPI
        elif image_format.width() > 0:
            natural_in = image_format.width() / dpi
        else:
            natural_in = image.width() / _CSS_DPI
        cursor.setPosition(fragment.position())
        table = cursor.currentTable()
        room_in = max_width_in / table.columns() - _CELL_CHROME_IN if table else max_width_in
        aspect = image.height() / image.width()
        width_in = min(natural_in, room_in, max_height_in / aspect)
        image_format.setWidth(width_in * dpi)
        image_format.setHeight(width_in * dpi * aspect)
        changes.append((fragment.position(), fragment.length(), image_format))
    _set_format(doc, changes)


def _fit_tables(frame: QTextFrame, max_width_px: float) -> None:
    """HTML tables may ask for a fixed width wider than the paper; those become full width so no column is cut."""
    for child in frame.childFrames():
        if isinstance(child, QTextTable):
            table_format = child.format()
            width = table_format.width()
            if width.type() == QTextLength.Type.FixedLength and width.rawValue() > max_width_px:
                table_format.setWidth(QTextLength(QTextLength.Type.PercentageLength, 100))
                child.setFormat(table_format)
        _fit_tables(child, max_width_px)


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
                       QPageLayout.Orientation.Portrait, QMarginsF(), QPageLayout.Unit.Point, QMarginsF())


def _print_palette() -> QPalette:
    """Dark text on white paper. Qt otherwise draws a document's text in the app's theme color, which in dark mode
    is white, and that made every notebook page come out blank."""
    palette = QPalette()
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText):
        palette.setColor(role, _INK)
    palette.setColor(QPalette.ColorRole.Link, _LINK)
    return palette


def _build(doc: QTextDocument, notebook: Notebook) -> dict[str, float]:
    builder = _Builder(doc, notebook.language)
    for index, cell in enumerate(notebook.cells):
        builder.gap = _CELL_GAP if index else 0
        _CELL_RENDERERS[cell.kind](builder, cell)
    return builder.widths


def render_notebook(path: Path, settings: PdfSettings) -> bytes:
    """Lay out every cell and its saved outputs as searchable text pages. Needs a running QGuiApplication."""
    if not isinstance(QCoreApplication.instance(), QGuiApplication):
        raise ImageLoadError("Notebooks can only be rendered while Papyr is running")
    notebook = parse_notebook(path.read_bytes())
    page_layout = _page_layout(settings)

    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    writer = QPdfWriter(buffer)
    writer.setResolution(_CSS_DPI)
    writer.setPageLayout(page_layout)
    writer.setCreator("Papyr")
    # Lay out on the whole sheet with the margin inside the document, as QTextDocument.print does, so the first
    # line of the next page sits a full margin away from this page's edge instead of touching it.
    paper = writer.pageLayout().fullRectPixels(_CSS_DPI)
    margin = settings.margin_pt * _CSS_DPI / 72

    doc = _NotebookDocument(path.parent)
    doc.documentLayout().setPaintDevice(writer)
    doc.setUseDesignMetrics(True)
    doc.setDocumentMargin(margin)
    doc.setPageSize(QSizeF(paper.width(), paper.height()))
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    doc.setDefaultTextOption(option)
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    font.setPointSizeF(_BODY_PT)
    # An "fi" ligature is one glyph, so in fonts such as Helvetica and DejaVu Sans "first" could not be searched for
    for tag in ("liga", "clig"):
        font.setFeature(QFont.Tag(tag), 0)
    doc.setDefaultFont(font)
    try:
        widths = _build(doc, notebook)
        _finish(doc, widths, (paper.width() - 2 * margin) / _CSS_DPI, (paper.height() - 2 * margin) / _CSS_DPI * 0.9)
    except Exception as exc:  # noqa: BLE001 - notebook content is untrusted, so any layout failure is this file's
        raise ImageLoadError(f"Notebook could not be laid out: {exc}") from exc
    if not doc.toPlainText().strip():  # cells whose source draws nothing, such as only an HTML comment
        raise ImageLoadError("Notebook has no cells with any content")

    context = QAbstractTextDocumentLayout.PaintContext()
    context.palette = _print_palette()
    painter = QPainter(writer)
    for page in range(doc.pageCount()):
        if page:
            writer.newPage()
        painter.save()
        painter.translate(0, -page * paper.height())
        context.clip = QRectF(0, page * paper.height(), paper.width(), paper.height())
        painter.setClipRect(context.clip)
        doc.documentLayout().draw(painter, context)
        painter.restore()
    painter.end()
    buffer.close()
    return bytes(data)
