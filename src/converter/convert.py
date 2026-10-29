import os
import tempfile
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from utils.filenames import individual_output_paths

from .images import ImageLoadError, encode_for_pdf
from .layout import PdfSettings, compute_placement
from .pdf_writer import PdfWriter

ProgressCallback = Callable[[int, int, Path], None]
CancelCheck = Callable[[], bool]


@dataclass
class ConversionReport:
    outputs: list[Path] = field(default_factory=list)
    failures: list[tuple[Path, str]] = field(default_factory=list)
    cancelled: bool = False


@contextmanager
def _atomic_pdf(destination: Path):
    """Write to a hidden temp file next to the destination and move it into place on success."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".heic2pdf-", suffix=".part", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            yield PdfWriter(stream)
        os.replace(temp_name, destination)
    finally:
        if os.path.exists(temp_name):
            os.remove(temp_name)


class _Cancelled(Exception):
    pass


def _never() -> bool:
    return False


def _noop(done: int, total: int, current: Path) -> None:
    pass


def convert_individual(sources: list[Path], output_dir: Path, settings: PdfSettings,
                       progress: ProgressCallback = _noop, cancelled: CancelCheck = _never
                       ) -> ConversionReport:
    report = ConversionReport()
    for index, (source, destination) in enumerate(zip(sources, individual_output_paths(sources, output_dir))):
        if cancelled():
            report.cancelled = True
            break
        progress(index, len(sources), source)
        try:
            image = encode_for_pdf(source)
            with _atomic_pdf(destination) as writer:
                writer.add_page(image, compute_placement(image.width, image.height, settings))
                writer.close()
            report.outputs.append(destination)
        except (ImageLoadError, OSError, ValueError) as exc:
            report.failures.append((source, str(exc)))
    progress(len(sources), len(sources), sources[-1] if sources else Path())
    return report


def convert_merged(sources: list[Path], destination: Path, settings: PdfSettings,
                   progress: ProgressCallback = _noop, cancelled: CancelCheck = _never
                   ) -> ConversionReport:
    """Write every readable source as one page, in order. Unreadable files are skipped and reported."""
    report = ConversionReport()
    try:
        with _atomic_pdf(destination) as writer:
            for index, source in enumerate(sources):
                if cancelled():
                    raise _Cancelled
                progress(index, len(sources), source)
                try:
                    image = encode_for_pdf(source)
                except ImageLoadError as exc:
                    report.failures.append((source, str(exc)))
                    continue
                writer.add_page(image, compute_placement(image.width, image.height, settings))
            if writer.page_count == 0:
                raise ValueError("None of the images could be read")
            writer.close()
        report.outputs.append(destination)
    except _Cancelled:
        report.cancelled = True
    except (OSError, ValueError) as exc:
        report.failures.append((destination, str(exc)))
    progress(len(sources), len(sources), sources[-1] if sources else Path())
    return report
