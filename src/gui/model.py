"""What the window is doing and what the user chose, kept apart from the widgets that show it.

The window is always in exactly one AppState. Options holds every conversion setting the user can change, and
FORMAT_CONTROLS says which of those settings each output format uses.
"""
import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum, auto
from functools import partial
from pathlib import Path

from PySide6.QtCore import QSettings

from converter import (ConversionReport, GifResolution, GifSettings, ImageSettings, OutputFormat, PageSize,
                       PdfSettings, convert_animated_gifs, convert_combined_gif, convert_images, convert_individual,
                       convert_merged)
from utils.errors import friendly_error
from utils.filenames import sanitize_name

PDF_DPI_CHOICES = (100, 150, 200, 300)
FRAME_MS_CHOICES = (250, 500, 1000, 2000)
FRAME_MS_RANGE = (20, 60_000)  # GIF stores hundredths of a second, and most viewers slow anything under 20 ms
PLAYS_RANGE = (2, 999)
PAGE_SIZES = (PageSize.A4, PageSize.LETTER, PageSize.ORIGINAL)
MARGIN_RANGE = (0, 50)
DEFAULT_MERGED_NAME = "Combined"


def round_frame_ms(ms: float) -> int:
    """GIF stores hundredths of a second, so show and save the duration the file will really have."""
    return int(round(ms, -1))


def plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'s' if count != 1 else ''}"


# The queue

@dataclass(frozen=True)
class QueueSummary:
    count: int = 0
    unreadable: int = 0
    has_document: bool = False
    total_bytes: int = 0
    has_tiff: bool = False

    @property
    def may_have_pages(self) -> bool:
        return self.has_document or self.has_tiff


# Conversion settings

class Control(Enum):
    """A setting the user can change. Each one maps to exactly one field of Options."""

    MERGE = auto()
    MERGED_NAME = auto()
    PAGE_SIZE = auto()
    MARGINS = auto()
    QUALITY = auto()
    PDF_DPI = auto()
    GIF_MODE = auto()
    FRAME_MS = auto()
    PLAYS = auto()
    GIF_RESOLUTION = auto()


class GifMode(Enum):
    """What GIF output does with pages and files: (label, short label for the dock, detail)."""

    ANIMATE_EACH = ("Animated GIF", "Animated", "A file's pages become one animation")
    COMBINE = ("Combine into one GIF", "Combined", "Every file, in list order")
    SEPARATE = ("Separate static GIFs", "Separate", "One GIF per page")

    def __init__(self, label: str, short: str, detail: str):
        self.label = label
        self.short = short
        self.detail = detail


def _image_controls(fmt: OutputFormat) -> tuple[Control, ...]:
    return (Control.QUALITY,) * fmt.has_quality + (Control.PDF_DPI,)


FORMAT_CONTROLS: dict[OutputFormat, tuple[Control, ...]] = {
    fmt: (Control.MERGE, Control.MERGED_NAME, Control.PAGE_SIZE, Control.MARGINS) if fmt is OutputFormat.PDF
    else (Control.GIF_MODE, Control.MERGED_NAME, Control.FRAME_MS, Control.PLAYS, Control.GIF_RESOLUTION,
          Control.PDF_DPI) if fmt is OutputFormat.GIF
    else _image_controls(fmt)
    for fmt in OutputFormat
}

@dataclass(frozen=True)
class Options:
    format: OutputFormat = OutputFormat.PDF
    merge: bool = False
    merged_name: str = ""
    page_size: PageSize = PageSize.A4
    margin_mm: float = 10.0
    quality: int = 90
    pdf_dpi: int = 200
    gif_mode: GifMode = GifMode.ANIMATE_EACH
    frame_ms: int = 1000
    plays: int = 0  # 0 plays forever
    gif_resolution: GifResolution = GifResolution.BALANCED

    def with_(self, **changes) -> "Options":
        return replace(self, **changes)

    def merges(self, queue: QueueSummary) -> bool:
        """Every file goes into one output: a merged PDF, or a combined animated GIF."""
        if self.format is OutputFormat.GIF:
            return self.gif_mode is GifMode.COMBINE and queue.count >= 2
        return self.format is OutputFormat.PDF and self.merge and queue.count >= 2

    def animates(self, queue: QueueSummary) -> bool:
        """The output can have more than one frame, so timing and frame size mean something."""
        return self.format is OutputFormat.GIF and (
            self.merges(queue) or (self.gif_mode is not GifMode.SEPARATE and queue.may_have_pages))

    def pdf_settings(self) -> PdfSettings:
        return PdfSettings(self.page_size, self.margin_mm)

    def image_settings(self) -> ImageSettings:
        return ImageSettings(self.format, self.quality, self.pdf_dpi)

    def gif_settings(self) -> GifSettings:
        return GifSettings(self.frame_ms, self.plays, self.gif_resolution)

    def merged_file_name(self) -> str:
        extension = OutputFormat.GIF.extension if self.format is OutputFormat.GIF else OutputFormat.PDF.extension
        return sanitize_name(self.merged_name or DEFAULT_MERGED_NAME, extension, DEFAULT_MERGED_NAME)

    # Remembered between launches, under the keys Papyr 1 used

    @classmethod
    def load(cls, settings: QSettings) -> "Options":
        """Read saved settings. A value that is missing, malformed, or out of range falls back to the default."""
        default = cls()

        def number(key: str, fallback: float, low: float, high: float) -> float:
            try:
                value = float(settings.value(key, fallback))
            except (TypeError, ValueError):
                return fallback
            return min(max(value, low), high) if math.isfinite(value) else fallback

        fmt = OutputFormat.__members__.get(str(settings.value("output_format", "PDF")), default.format)
        page = next((size for size in PAGE_SIZES if size.label == settings.value("page_size")), default.page_size)
        dpi = int(number("pdf_dpi", default.pdf_dpi, 0, 10_000))
        plays = int(number("gif_plays", default.plays, 0, PLAYS_RANGE[1]))
        return cls(format=fmt,
                   merge=settings.value("mode") == "merged",
                   merged_name=str(settings.value("merged_name", "")),
                   page_size=page,
                   margin_mm=number("margin_mm", default.margin_mm, *MARGIN_RANGE),
                   quality=int(number("quality", default.quality, 1, 100)),
                   pdf_dpi=dpi if dpi in PDF_DPI_CHOICES else default.pdf_dpi,
                   gif_mode=GifMode.__members__.get(str(settings.value("gif_mode")), default.gif_mode),
                   frame_ms=round_frame_ms(number("gif_frame_ms", default.frame_ms, *FRAME_MS_RANGE)),
                   plays=plays,
                   gif_resolution=GifResolution.__members__.get(str(settings.value("gif_resolution")),
                                                                default.gif_resolution))

    def save(self, settings: QSettings) -> None:
        settings.setValue("output_format", self.format.name)
        settings.setValue("mode", "merged" if self.merge else "individual")
        settings.setValue("merged_name", self.merged_name)
        settings.setValue("page_size", self.page_size.label)
        settings.setValue("margin_mm", self.margin_mm)
        settings.setValue("quality", self.quality)
        settings.setValue("pdf_dpi", self.pdf_dpi)
        settings.setValue("gif_mode", self.gif_mode.name)
        settings.setValue("gif_frame_ms", self.frame_ms)
        settings.setValue("gif_plays", self.plays)
        settings.setValue("gif_resolution", self.gif_resolution.name)


# Some settings only mean something for certain files or choices: merging needs two files, the merged file's
# name needs merging on, and the page resolution only applies to PDFs and notebooks being turned into still images.
# A GIF's animation choice needs pages or files to animate, and its timing and frame size need an animation.
_NEEDS: dict[Control, Callable[[Options, QueueSummary], bool]] = {
    Control.MERGE: lambda options, queue: queue.count >= 2,
    Control.MERGED_NAME: lambda options, queue: options.merges(queue),
    Control.PDF_DPI: lambda options, queue: queue.has_document and not options.animates(queue),
    Control.GIF_MODE: lambda options, queue: queue.count >= 2 or queue.may_have_pages,
    Control.FRAME_MS: Options.animates,
    Control.PLAYS: Options.animates,
    Control.GIF_RESOLUTION: Options.animates,
}


def controls_for(options: Options, queue: QueueSummary) -> tuple[Control, ...]:
    """The settings to show for this format and these files, in display order."""
    return tuple(c for c in FORMAT_CONTROLS[options.format] if _NEEDS.get(c, lambda *_: True)(options, queue))


Job = Callable[..., ConversionReport]


def plan_job(options: Options, queue: QueueSummary, sources: list[Path], destination: Path) -> Job:
    """The engine call for these files and settings. It takes (progress, cancelled) and returns a report."""
    if options.format is OutputFormat.GIF and options.gif_mode is not GifMode.SEPARATE:
        if options.merges(queue):
            return partial(convert_combined_gif, sources, destination / options.merged_file_name(),
                           options.gif_settings())
        return partial(convert_animated_gifs, sources, destination, options.gif_settings())
    if options.format is not OutputFormat.PDF:
        return partial(convert_images, sources, destination, options.image_settings())
    if options.merges(queue):
        return partial(convert_merged, sources, destination / options.merged_file_name(), options.pdf_settings())
    return partial(convert_individual, sources, destination, options.pdf_settings())


# The result of one finished run

class Outcome(Enum):
    SUCCESS = auto()
    PARTIAL = auto()
    FAILED = auto()


@dataclass(frozen=True)
class Failure:
    path: Path
    reason: str  # one plain sentence
    detail: str  # what the engine or the OS said


@dataclass(frozen=True)
class RunResult:
    sources: tuple[Path, ...]
    format: OutputFormat
    merged: bool
    destination: Path
    outputs: tuple[Path, ...] = ()
    failures: tuple[Failure, ...] = ()

    @classmethod
    def from_report(cls, report: ConversionReport, sources: list[Path], fmt: OutputFormat, merged: bool,
                    destination: Path) -> "RunResult":
        failures = tuple(Failure(path, friendly_error(raw), raw) for path, raw in report.failures)
        return cls(tuple(sources), fmt, merged, destination, tuple(report.outputs), failures)

    @property
    def outcome(self) -> Outcome:
        if not self.failures:
            return Outcome.SUCCESS
        return Outcome.PARTIAL if self.outputs else Outcome.FAILED

    @property
    def failed_sources(self) -> tuple[Path, ...]:
        """The queued files that were not converted, in queue order. A run that saved nothing converted none of
        them, even when its failure names only the merged PDF or the job itself."""
        if self.failures and not self.outputs:
            return self.sources
        named = {failure.path for failure in self.failures}
        return tuple(source for source in self.sources if source in named)

    @property
    def converted_count(self) -> int:
        return len(self.sources) - len(self.failed_sources)


# The window's states

@dataclass(frozen=True)
class Welcome:
    """No files yet. notice says why something dropped here wasn't added."""

    notice: str = ""
    error: bool = False


@dataclass(frozen=True)
class Workspace:
    """Files queued and waiting. notice is a one-line message about the last thing that happened."""

    notice: str = ""
    error: bool = False
    kept: tuple[Path, ...] = ()  # files a cancelled run already saved, so the notice can offer to show them


@dataclass(frozen=True)
class Converting:
    total: int
    done: int = 0
    current: str = ""
    cancelling: bool = False

    @property
    def remaining(self) -> int:
        return self.total - self.done


@dataclass(frozen=True)
class Done:
    result: RunResult


AppState = Welcome | Workspace | Converting | Done
