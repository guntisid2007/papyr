from dataclasses import dataclass
from enum import Enum

MM_TO_PT = 72 / 25.4


class PageSize(Enum):
    ORIGINAL = ("Original image size", None)
    A4 = ("A4", (595.2756, 841.8898))
    LETTER = ("US Letter", (612.0, 792.0))

    def __init__(self, label: str, dimensions: tuple[float, float] | None):
        self.label = label
        self.dimensions = dimensions


@dataclass(frozen=True)
class PdfSettings:
    page_size: PageSize = PageSize.A4
    margin_mm: float = 10.0

    @property
    def margin_pt(self) -> float:
        return self.margin_mm * MM_TO_PT


@dataclass(frozen=True)
class Placement:
    page_width: float
    page_height: float
    x: float
    y: float
    width: float
    height: float


def compute_placement(image_width: int, image_height: int, settings: PdfSettings) -> Placement:
    """Fit the image inside the page margins without distortion.

    Fixed page sizes rotate to landscape for landscape images. Original size maps
    one pixel to one point and adds the margin around the image.
    """
    margin = settings.margin_pt
    if settings.page_size.dimensions is None:
        return Placement(image_width + 2 * margin, image_height + 2 * margin,
                         margin, margin, float(image_width), float(image_height))

    short, long = sorted(settings.page_size.dimensions)
    page_w, page_h = (long, short) if image_width > image_height else (short, long)
    avail_w, avail_h = page_w - 2 * margin, page_h - 2 * margin
    if avail_w <= 0 or avail_h <= 0:
        raise ValueError(f"A {settings.margin_mm:g} mm margin leaves no room on the page")

    scale = min(avail_w / image_width, avail_h / image_height)
    width, height = image_width * scale, image_height * scale
    return Placement(page_w, page_h, (page_w - width) / 2, (page_h - height) / 2, width, height)
