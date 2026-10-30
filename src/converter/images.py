import io
import math
import threading
import zlib
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import BinaryIO

import pillow_heif
import pypdfium2 as pdfium
from PIL import Image, ImageCms, ImageMath, ImageOps, ImageSequence, UnidentifiedImageError

from .formats import INPUT_EXTENSIONS, LOSSLESS_INPUTS, ImageLoadError, OutputFormat
from .layout import PageSize, PdfSettings
from .notebook import render_notebook
from .pdf_writer import EncodedImage

pillow_heif.register_heif_opener()

DEEP_GRAY_MODES = frozenset({"I", "I;16", "I;16B", "I;16L"})
PDF_EMBED_JPEG_QUALITY = 92
DEFAULT_PDF_DPI = 200
NOTEBOOK_IMAGE_SETTINGS = PdfSettings(PageSize.ORIGINAL, 15)
_PDFIUM_LOCK = threading.Lock()  # PDFium is not thread-safe; thumbnails and conversion use it concurrently
_DOCUMENTS: dict[str, Callable[[Path, PdfSettings], Path | bytes]] = {
    ".pdf": lambda path, settings: path,
    ".ipynb": render_notebook,
}


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in INPUT_EXTENSIONS


def is_document(path: Path) -> bool:
    """A source made of text pages (a PDF, or a notebook rendered to one) rather than a picture."""
    return path.suffix.lower() in _DOCUMENTS


def document_pdf(path: Path, settings: PdfSettings) -> Path | bytes:
    """The PDF behind a document: the file itself, or the notebook laid out with these page settings."""
    return _DOCUMENTS[path.suffix.lower()](path, settings)


def _to_srgb(image: Image.Image, icc: bytes | None) -> Image.Image:
    if not icc:
        return image
    try:
        source = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        return ImageCms.profileToProfile(image, source, ImageCms.createProfile("sRGB"), outputMode="RGB")
    except (ImageCms.PyCMSError, OSError, ValueError):
        return image


def _split_alpha(image: Image.Image) -> tuple[Image.Image, Image.Image | None]:
    """Separate 8-bit color (RGB, L, or CMYK) from transparency, using the original pixel values."""
    key = image.info.get("transparency")
    if image.mode in DEEP_GRAY_MODES:
        wide = image.convert("I")
        gray = wide.convert("F").point(lambda v: v / 256).convert("L")
        if not isinstance(key, int):
            return gray, None
        mask = ImageMath.lambda_eval(lambda a: a["convert"](a["notequal"](a["x"], key) * 255, "L"), x=wide)
        return gray, mask
    if key is not None or image.mode in ("P", "PA") or "A" in image.getbands():
        mask = image.convert("RGBA").getchannel("A")
        color = image.convert("L" if image.mode in ("L", "LA", "1") else "RGB")
        return color, mask
    if image.mode in ("L", "RGB", "CMYK"):
        return image, None
    return image.convert("L" if image.mode == "1" else "RGB"), None


def _normalize(image: Image.Image, icc: bytes | None, keep_alpha: bool) -> Image.Image:
    """Return 8-bit sRGB as L or RGB, or LA or RGBA when keep_alpha and the image has transparency.

    Without keep_alpha, transparency is composited onto white. All metadata (EXIF, XMP, GPS) is dropped
    so no writer can copy it into the output.
    """
    page = _composite(image, icc, keep_alpha)
    page.info = {}
    return page


def _composite(image: Image.Image, icc: bytes | None, keep_alpha: bool) -> Image.Image:
    color, mask = _split_alpha(image)
    color = _to_srgb(color, icc)
    color = color.convert("L" if color.mode == "L" else "RGB")
    if mask is None:
        return color
    if keep_alpha:
        color.putalpha(mask)
        return color
    background = Image.new(color.mode, color.size, "white")
    background.paste(color, mask=mask)
    return background


def _flatten(image: Image.Image) -> Image.Image:
    if "A" not in image.getbands():
        return image
    background = Image.new(image.mode[:-1], image.size, "white")
    background.paste(image.convert(image.mode[:-1]), mask=image.getchannel("A"))
    return background


def _render_page(document: pdfium.PdfDocument, index: int, dpi: float, fit: tuple[int, int] | None) -> Image.Image:
    with _PDFIUM_LOCK:
        page = document[index]
        try:
            width, height = page.get_size()
            scale = min(fit[0] / width, fit[1] / height) if fit else dpi / 72
            pixels = width * height * scale * scale
            if pixels > Image.MAX_IMAGE_PIXELS:
                scale *= math.sqrt(Image.MAX_IMAGE_PIXELS / pixels)
            bitmap = page.render(scale=scale)
            try:
                return bitmap.to_pil().convert("RGB")
            finally:
                bitmap.close()
        finally:
            page.close()


def _open_pdf(source: Path | bytes) -> pdfium.PdfDocument:
    """Open a PDF. Call with the PDFium lock held."""
    try:
        return pdfium.PdfDocument(source)
    except pdfium.PdfiumError as exc:
        message = "PDF is password-protected" if "password" in str(exc).lower() else f"Could not read PDF: {exc}"
        raise ImageLoadError(message) from exc


def pdf_page_sizes(source: Path | bytes) -> list[tuple[float, float]]:
    """Each page's width and height in points, without rendering anything."""
    with _PDFIUM_LOCK:
        document = _open_pdf(source)
        try:
            sizes = [document.get_page_size(index) for index in range(len(document))]
        finally:
            document.close()
    if not sizes:
        raise ImageLoadError("PDF has no pages")
    return sizes


def pdf_pages(source: Path | bytes, dpi: float = DEFAULT_PDF_DPI,
              fit: tuple[int, int] | None = None) -> Iterator[Image.Image]:
    """Render each page at dpi, or as large as fits inside fit. The PDFium lock is held per call, not across
    yields, so a long conversion never blocks thumbnails."""
    with _PDFIUM_LOCK:
        document = _open_pdf(source)
        count = len(document)
    try:
        if count == 0:
            raise ImageLoadError("PDF has no pages")
        for index in range(count):
            yield _render_page(document, index, dpi, fit)
    finally:
        with _PDFIUM_LOCK:
            document.close()


def _image_pages(path: Path, keep_alpha: bool) -> Iterator[Image.Image]:
    try:
        with Image.open(path) as source:
            frames = ImageSequence.Iterator(source) if source.format == "TIFF" else [source]
            for frame in frames:
                frame.load()
                icc = frame.info.get("icc_profile") or source.info.get("icc_profile")
                yield _normalize(ImageOps.exif_transpose(frame), icc, keep_alpha)
    except Image.DecompressionBombError as exc:
        raise ImageLoadError("Image is too large to convert safely") from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, EOFError) as exc:
        raise ImageLoadError(f"Could not read image: {exc}") from exc


def iter_pages(path: Path, *, keep_alpha: bool = False, pdf_dpi: int = DEFAULT_PDF_DPI) -> Iterator[Image.Image]:
    """Yield every page of a file upright in sRGB: each PDF or notebook page, each TIFF frame, or the single image.

    Animated GIF, WebP, and multi-image HEIC files yield their first image only.
    """
    if not is_supported(path):
        raise ImageLoadError(f"Unsupported file type: {path.suffix or 'no extension'}")
    if is_document(path):
        yield from pdf_pages(document_pdf(path, NOTEBOOK_IMAGE_SETTINGS), pdf_dpi)
    else:
        yield from _image_pages(path, keep_alpha)


def load_image(path: Path) -> Image.Image:
    """First page of a file, upright, in sRGB, as RGB or L with transparency on white."""
    pages = iter_pages(path)
    try:
        return next(pages)
    finally:
        pages.close()


def encode_for_pdf(image: Image.Image, lossless: bool) -> EncodedImage:
    """Encode a normalized page for embedding. Photo metadata such as GPS is never copied."""
    color_space = "DeviceGray" if image.mode == "L" else "DeviceRGB"
    if lossless:
        return EncodedImage(zlib.compress(image.tobytes(), 6), "FlateDecode",
                            image.width, image.height, color_space)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=PDF_EMBED_JPEG_QUALITY, subsampling=0, optimize=True)
    return EncodedImage(buffer.getvalue(), "DCTDecode", image.width, image.height, color_space)


def is_lossless_source(path: Path) -> bool:
    return path.suffix.lower() in LOSSLESS_INPUTS


def save_image(image: Image.Image, stream: BinaryIO, fmt: OutputFormat, quality: int) -> None:
    """Write a normalized page in an image format. Metadata such as GPS is never copied."""
    if not fmt.keeps_alpha:
        image = _flatten(image)
    if fmt in (OutputFormat.HEIC, OutputFormat.AVIF) and image.mode in ("L", "LA"):
        image = image.convert("RGBA" if image.mode == "LA" else "RGB")
    options: dict = {}
    if fmt is OutputFormat.JPEG:
        options = {"quality": quality, "subsampling": 0 if quality >= 90 else 2, "optimize": True}
    elif fmt is OutputFormat.WEBP:
        options = {"quality": quality, "method": 4, "lossless": quality >= 100}
    elif fmt in (OutputFormat.HEIC, OutputFormat.AVIF):
        options = {"quality": quality}
    elif fmt is OutputFormat.TIFF:
        options = {"compression": "tiff_adobe_deflate"}
    elif fmt is OutputFormat.GIF and image.mode in ("RGB", "RGBA", "LA"):
        image = to_gif_palette(image)
    image.save(stream, fmt.pillow_format, **options)


def to_gif_palette(image: Image.Image, reserve_transparent: bool = False) -> Image.Image:
    """Quantize to 256 colours, or to 255 with index 255 for fully transparent pixels when there are any (or
    reserve_transparent asks for the index anyway). The palette is padded so index 255 is always in range."""
    clear = image.getchannel("A").point(lambda a: 255 if a < 128 else 0) if "A" in image.getbands() else None
    if not reserve_transparent and (clear is None or clear.getbbox() is None):
        return _flatten(image).convert("RGB").quantize(256, dither=Image.Dither.FLOYDSTEINBERG)
    paletted = _flatten(image).convert("RGB").quantize(255, dither=Image.Dither.FLOYDSTEINBERG)
    if clear is not None:
        paletted.paste(255, mask=clear)
    palette = paletted.getpalette() or []
    paletted.putpalette(palette + [0] * (768 - len(palette)))
    paletted.info["transparency"] = 255
    return paletted


def make_thumbnail(path: Path, max_size: int) -> Image.Image:
    """Square, upright RGBA preview with the image centred."""
    if not is_supported(path):
        raise ImageLoadError(f"Unsupported file type: {path.suffix or 'no extension'}")
    if is_document(path):
        pages = pdf_pages(document_pdf(path, NOTEBOOK_IMAGE_SETTINGS), dpi=36)
        try:
            image = next(pages).convert("RGBA")
        finally:
            pages.close()
    else:
        try:
            with Image.open(path) as source:
                source.draft("RGB", (max_size * 2, max_size * 2))
                image = ImageOps.exif_transpose(source).convert("RGBA")
        except Image.DecompressionBombError as exc:
            raise ImageLoadError("Image is too large to convert safely") from exc
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
            raise ImageLoadError(f"Could not read image: {exc}") from exc
    image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    square = Image.new("RGBA", (max_size, max_size), (0, 0, 0, 0))
    square.paste(image, ((max_size - image.width) // 2, (max_size - image.height) // 2))
    return square
