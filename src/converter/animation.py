"""Animated GIFs: each page of each source becomes one frame, in order, all on one canvas size."""
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from PIL import GifImagePlugin, Image, ImageSequence, UnidentifiedImageError

from .formats import GifSettings, ImageLoadError
from .images import NOTEBOOK_IMAGE_SETTINGS, document_pdf, is_document, iter_pages, pdf_page_sizes, pdf_pages, \
    to_gif_palette

Size = tuple[int, int]
_ORIENTATION = 274
_QUARTER_TURNS = frozenset({5, 6, 7, 8})


@dataclass(frozen=True)
class FrameSource:
    """One file's pages, measured but not decoded. A document keeps the PDF it resolved to, so a notebook is
    laid out once."""

    path: Path
    sizes: tuple[tuple[float, float], ...]
    pdf: Path | bytes | None = None

    @property
    def is_still(self) -> bool:
        return self.pdf is None and len(self.sizes) == 1


def measure(path: Path) -> FrameSource:
    if is_document(path):
        pdf = document_pdf(path, NOTEBOOK_IMAGE_SETTINGS)
        return FrameSource(path, tuple(pdf_page_sizes(pdf)), pdf)
    try:
        with Image.open(path) as image:
            frames = ImageSequence.Iterator(image) if image.format == "TIFF" else [image]
            sizes = tuple(_upright(frame) for frame in frames)
    except Image.DecompressionBombError as exc:
        raise ImageLoadError("Image is too large to convert safely") from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, EOFError) as exc:
        raise ImageLoadError(f"Could not read image: {exc}") from exc
    return FrameSource(path, sizes)


def _upright(frame: Image.Image) -> Size:
    """The frame's size once its EXIF orientation is applied. Pillow opens a TIFF with that already done."""
    turned = frame.format != "TIFF" and frame.getexif().get(_ORIENTATION) in _QUARTER_TURNS
    return (frame.height, frame.width) if turned else frame.size


def _fit(size: tuple[float, float], box: Size, upscale: bool) -> Size:
    """The largest size with this aspect ratio inside box. Pictures are never enlarged; PDF pages are vector,
    so they render at whatever size fits."""
    scale = min(box[0] / size[0], box[1] / size[1])
    if not upscale:
        scale = min(scale, 1.0)
    return max(1, round(size[0] * scale)), max(1, round(size[1] * scale))


def canvas_size(sources: list[FrameSource], long_side: int) -> Size:
    """Every frame shares this size: wide enough for the widest fitted page and tall enough for the tallest."""
    fitted = [_fit(size, (long_side, long_side), source.pdf is not None)
              for source in sources for size in source.sizes]
    return max(width for width, _ in fitted), max(height for _, height in fitted)


def frames(source: FrameSource, canvas: Size) -> Iterator[Image.Image]:
    """Each page scaled to fit the canvas and centred on it, on white, or on transparency for a picture
    that has some."""
    vector = source.pdf is not None
    pages = pdf_pages(source.pdf, fit=canvas) if vector else iter_pages(source.path, keep_alpha=True)
    try:
        for page in pages:
            yield _on_canvas(page, canvas, vector)
    finally:
        pages.close()


def _on_canvas(page: Image.Image, canvas: Size, upscale: bool) -> Image.Image:
    mode = "RGBA" if "A" in page.getbands() else "RGB"
    page = page.convert(mode)
    size = _fit(page.size, canvas, upscale)
    if page.size != size:
        page = page.resize(size, Image.Resampling.LANCZOS)
    if size == canvas:
        return page
    framed = Image.new(mode, canvas, (0, 0, 0, 0) if mode == "RGBA" else "white")
    framed.paste(page, ((canvas[0] - size[0]) // 2, (canvas[1] - size[1]) // 2))
    return framed


class GifWriter:
    """Writes each frame as it arrives, so only one page is ever held in memory.

    Pillow's save_all keeps every frame until the end and folds a frame identical to the one before it into
    that frame's duration, so two blank pages in a row would become one. Here every page is its own frame
    with its own palette.
    """

    def __init__(self, stream: BinaryIO, settings: GifSettings):
        self._stream = stream
        self._settings = settings
        self.frame_count = 0

    def add(self, frame: Image.Image) -> None:
        # Every frame reserves a transparent index, even an opaque one. Disposal 2 then clears to transparency, so
        # an opaque page never shows through the clear areas of a transparent picture after it.
        paletted = to_gif_palette(frame, reserve_transparent=True)
        params = {"duration": self._settings.frame_ms, "disposal": 2, "transparency": paletted.info["transparency"]}
        if self.frame_count == 0:
            header, _ = GifImagePlugin.getheader(paletted, info={"loop": self._settings.loop,
                                                                 "duration": self._settings.frame_ms})
            self._stream.writelines(header)
        else:
            params["include_color_table"] = True
        self._stream.writelines(GifImagePlugin.getdata(paletted, **params))
        self.frame_count += 1

    def close(self) -> None:
        if not self.frame_count:
            raise ImageLoadError("There were no pages to animate")
        self._stream.write(b";")
