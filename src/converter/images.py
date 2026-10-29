import io
import zlib
from pathlib import Path

import pillow_heif
from PIL import Image, ImageCms, ImageMath, ImageOps, UnidentifiedImageError

from .pdf_writer import EncodedImage

pillow_heif.register_heif_opener()

SUPPORTED_EXTENSIONS = frozenset({".heic", ".heif", ".jpg", ".jpeg", ".png"})
LOSSLESS_EXTENSIONS = frozenset({".png"})
DEEP_GRAY_MODES = frozenset({"I", "I;16", "I;16B", "I;16L"})
JPEG_QUALITY = 92


class ImageLoadError(Exception):
    pass


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def _to_srgb(image: Image.Image, icc: bytes | None) -> Image.Image:
    if not icc:
        return image
    try:
        source = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        mode = "RGBA" if "A" in image.getbands() else "RGB"
        return ImageCms.profileToProfile(image, source, ImageCms.createProfile("sRGB"), outputMode=mode)
    except (ImageCms.PyCMSError, OSError, ValueError):
        return image


def _with_alpha(image: Image.Image) -> Image.Image:
    """Scale 16-bit gray to 8 bits and turn a color-key transparency into an alpha band."""
    key = image.info.get("transparency")
    if image.mode in DEEP_GRAY_MODES:
        wide = image.convert("I")
        gray = wide.convert("F").point(lambda v: v / 256).convert("L")
        if not isinstance(key, int):
            return gray
        mask = ImageMath.lambda_eval(lambda a: a["convert"](a["notequal"](a["x"], key) * 255, "L"), x=wide)
        return Image.merge("LA", (gray, mask))
    if key is not None or image.mode == "P":
        return image.convert("RGBA")
    return image


def _normalize(image: Image.Image, icc: bytes | None) -> Image.Image:
    """Return 8-bit sRGB (RGB or L) with any transparency composited onto white."""
    image = _to_srgb(_with_alpha(image), icc)
    if "A" in image.getbands():
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba.convert("RGB"), mask=rgba.getchannel("A"))
        return background
    return image.convert("L" if image.mode in ("L", "1") else "RGB")


def load_image(path: Path) -> Image.Image:
    """Decode an image upright, in sRGB, as an RGB or L image ready for a PDF page."""
    if not is_supported(path):
        raise ImageLoadError(f"Unsupported file type: {path.suffix or 'no extension'}")
    try:
        with Image.open(path) as source:
            source.load()
            image = _normalize(ImageOps.exif_transpose(source), source.info.get("icc_profile"))
    except Image.DecompressionBombError as exc:
        raise ImageLoadError("Image is too large to convert safely") from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise ImageLoadError(f"Could not read image: {exc}") from exc
    return image


def encode_for_pdf(path: Path) -> EncodedImage:
    """Encode an image for embedding. Photo metadata such as GPS is never copied."""
    image = load_image(path)
    color_space = "DeviceGray" if image.mode == "L" else "DeviceRGB"
    if path.suffix.lower() in LOSSLESS_EXTENSIONS:
        return EncodedImage(zlib.compress(image.tobytes(), 6), "FlateDecode",
                            image.width, image.height, color_space)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=JPEG_QUALITY, subsampling=0, optimize=True)
    return EncodedImage(buffer.getvalue(), "DCTDecode", image.width, image.height, color_space)


def make_thumbnail(path: Path, max_size: int) -> Image.Image:
    """Square, upright RGBA preview with the image centred. Uses JPEG draft decoding so large photos load quickly."""
    if not is_supported(path):
        raise ImageLoadError(f"Unsupported file type: {path.suffix or 'no extension'}")
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
