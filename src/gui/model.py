"""What the window is doing and what the user chose, kept apart from the widgets that show it.

The window is always in exactly one AppState. Options holds every conversion setting the user can change, and
FORMAT_CONTROLS says which of those settings each output format uses.
"""
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum, auto
from functools import partial
from pathlib import Path

from PySide6.QtCore import QSettings

from converter import (ConversionReport, ImageSettings, OutputFormat, PageSize, PdfSettings, convert_images,
                       convert_individual, convert_merged)
from utils.errors import friendly_error
from utils.filenames import sanitize_pdf_name

PDF_DPI_CHOICES = (100, 150, 200, 300)
PAGE_SIZES = (PageSize.A4, PageSize.LETTER, PageSize.ORIGINAL)
MARGIN_RANGE = (0, 50)
DEFAULT_MERGED_NAME = "Combined"


def plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'s' if count != 1 else ''}"


# The queue

@dataclass(frozen=True)
class QueueSummary:
    count: int = 0
    unreadable: int = 0
    has_document: bool = False
    total_bytes: int = 0


# Conversion settings

class Control(Enum):
    """A setting the user can change. Each one maps to exactly one field of Options."""

    MERGE = auto()
    MERGED_NAME = auto()
    PAGE_SIZE = auto()
    MARGINS = auto()
    QUALITY = auto()
    PDF_DPI = auto()


def _image_controls(fmt: OutputFormat) -> tuple[Control, ...]:
    return (Control.QUALITY,) * fmt.has_quality + (Control.PDF_DPI,)


FORMAT_CONTROLS: dict[OutputFormat, tuple[Control, ...]] = {
    fmt: (Control.MERGE, Control.MERGED_NAME, Control.PAGE_SIZE, Control.MARGINS) if fmt is OutputFormat.PDF
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

    def with_(self, **changes) -> "Options":
        return replace(self, **changes)

    def merges(self, queue: QueueSummary) -> bool:
        """Merging into one PDF is on and means something for these files."""
        return self.merge and Control.MERGE in controls_for(self, queue)

    def pdf_settings(self) -> PdfSettings:
        return PdfSettings(self.page_size, self.margin_mm)

    def image_settings(self) -> ImageSettings:
        return ImageSettings(self.format, self.quality, self.pdf_dpi)

    def merged_file_name(self) -> str:
        return sanitize_pdf_name(self.merged_name or DEFAULT_MERGED_NAME, DEFAULT_MERGED_NAME)

    # Remembered between launches, under the keys Papyr 1 used

    @classmethod
    def load(cls, settings: QSettings) -> "Options":
        """Read saved settings. A value that is missing, malformed, or out of range falls back to the default."""
        default = cls()

        def number(key: str, fallback: float, low: float, high: float) -> float:
            try:
                return min(max(float(settings.value(key, fallback)), low), high)
            except (TypeError, ValueError):
                return fallback

        fmt = OutputFormat.__members__.get(str(settings.value("output_format", "PDF")), default.format)
        page = next((size for size in PAGE_SIZES if size.label == settings.value("page_size")), default.page_size)
        dpi = int(number("pdf_dpi", default.pdf_dpi, 0, 10_000))
        return cls(format=fmt,
                   merge=settings.value("mode") == "merged",
                   merged_name=str(settings.value("merged_name", "")),
                   page_size=page,
                   margin_mm=number("margin_mm", default.margin_mm, *MARGIN_RANGE),
                   quality=int(number("quality", default.quality, 1, 100)),
                   pdf_dpi=dpi if dpi in PDF_DPI_CHOICES else default.pdf_dpi)

    def save(self, settings: QSettings) -> None:
        settings.setValue("output_format", self.format.name)
        settings.setValue("mode", "merged" if self.merge else "individual")
        settings.setValue("merged_name", self.merged_name)
        settings.setValue("page_size", self.page_size.label)
        settings.setValue("margin_mm", self.margin_mm)
        settings.setValue("quality", self.quality)
        settings.setValue("pdf_dpi", self.pdf_dpi)


# Some settings only mean something for certain files or choices: merging needs two files, the merged file's
# name needs merging on, and the page resolution only applies to PDFs and notebooks being turned into images.
_NEEDS: dict[Control, Callable[[Options, QueueSummary], bool]] = {
    Control.MERGE: lambda options, queue: queue.count >= 2,
    Control.MERGED_NAME: lambda options, queue: options.merge and queue.count >= 2,
    Control.PDF_DPI: lambda options, queue: queue.has_document,
}


def controls_for(options: Options, queue: QueueSummary) -> tuple[Control, ...]:
    """The settings to show for this format and these files, in display order."""
    return tuple(c for c in FORMAT_CONTROLS[options.format] if _NEEDS.get(c, lambda *_: True)(options, queue))


Job = Callable[..., ConversionReport]


def plan_job(options: Options, queue: QueueSummary, sources: list[Path], destination: Path) -> Job:
    """The engine call for these files and settings. It takes (progress, cancelled) and returns a report."""
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
        """The queued files that were not converted, in queue order. A failure that names no queued file (the
        merged PDF could not be written, or the job itself broke) leaves every file unconverted."""
        named = {failure.path for failure in self.failures}
        if not self.outputs and named - set(self.sources):
            return self.sources
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
