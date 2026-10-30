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


class GifResolution(Enum):
    """How large animation frames may be: (label, longest side in pixels)."""

    HIGH = ("High quality", 1600)
    BALANCED = ("Balanced", 1000)
    SMALL = ("Smaller file", 500)

    def __init__(self, label: str, long_side: int):
        self.label = label
        self.long_side = long_side


@dataclass(frozen=True)
class GifSettings:
    frame_ms: int = 1000
    plays: int = 0  # 0 plays forever
    resolution: GifResolution = GifResolution.BALANCED

    @property
    def loop(self) -> int | None:
        """The GIF loop field: 0 repeats forever, n repeats n more times, and None (no field) plays once."""
        return None if self.plays == 1 else max(self.plays - 1, 0)
