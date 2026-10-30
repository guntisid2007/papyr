from dataclasses import dataclass
from enum import Enum

INPUT_EXTENSIONS = frozenset({".heic", ".heif", ".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff",
                              ".bmp", ".gif", ".avif", ".pdf", ".ipynb"})
LOSSLESS_INPUTS = frozenset({".png", ".tif", ".tiff", ".bmp", ".gif"})


class ImageLoadError(Exception):
    pass


class OutputFormat(Enum):
    """Every format the app can write: (label, extension, Pillow format, keeps transparency, has quality)."""

    PDF = ("PDF", ".pdf", None, False, False)
    JPEG = ("JPEG", ".jpg", "JPEG", False, True)
    PNG = ("PNG", ".png", "PNG", True, False)
    HEIC = ("HEIC", ".heic", "HEIF", True, True)
    WEBP = ("WebP", ".webp", "WEBP", True, True)
    AVIF = ("AVIF", ".avif", "AVIF", True, True)
    TIFF = ("TIFF", ".tiff", "TIFF", True, False)
    GIF = ("GIF", ".gif", "GIF", True, False)
    BMP = ("BMP", ".bmp", "BMP", False, False)

    def __init__(self, label: str, extension: str, pillow_format: str | None, alpha: bool, quality: bool):
        self.label = label
        self.extension = extension
        self.pillow_format = pillow_format
        self.keeps_alpha = alpha
        self.has_quality = quality


@dataclass(frozen=True)
class ImageSettings:
    format: OutputFormat = OutputFormat.JPEG
    quality: int = 90
    pdf_dpi: int = 200
