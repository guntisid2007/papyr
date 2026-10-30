import io
import itertools
import os
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

import pypdf

from utils.filenames import individual_output_paths, unique_path

from .animation import FrameSource, GifWriter, canvas_size, frames, measure
from .formats import GifSettings, ImageLoadError, ImageSettings, OutputFormat
from .images import document_pdf, encode_for_pdf, is_document, is_lossless_source, iter_pages, save_image
from .layout import PdfSettings, compute_placement
from .pdf_writer import PdfWriter

ProgressCallback = Callable[[int, int, Path], None]
CancelCheck = Callable[[], bool]
_ERRORS = (ImageLoadError, OSError, ValueError, pypdf.errors.PyPdfError)


@dataclass
class ConversionReport:
    outputs: list[Path] = field(default_factory=list)
    failures: list[tuple[Path, str]] = field(default_factory=list)
    cancelled: bool = False


class _Cancelled(Exception):
    pass


class _NothingReadable(Exception):
    pass


@contextmanager
def _atomic_file(destination: Path):
    """Write to a hidden temp file next to the destination and move it into place on success."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".papyr-", suffix=".part", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            yield stream
        os.replace(temp_name, destination)
    finally:
        if os.path.exists(temp_name):
            os.remove(temp_name)


def _never() -> bool:
    return False


def _noop(done: int, total: int, current: Path) -> None:
    pass


def _check(cancelled: CancelCheck) -> None:
    if cancelled():
        raise _Cancelled


def _encoded_pages(source: Path, settings: PdfSettings, cancelled: CancelCheck) -> Iterator[tuple]:
    lossless = is_lossless_source(source)
    for page in iter_pages(source):
        _check(cancelled)
        encoded = encode_for_pdf(page, lossless)
        yield encoded, compute_placement(encoded.width, encoded.height, settings)


def _read_document(source: Path, settings: PdfSettings) -> pypdf.PdfReader:
    pdf = document_pdf(source, settings)
    reader = pypdf.PdfReader(io.BytesIO(pdf) if isinstance(pdf, bytes) else pdf)
    if reader.is_encrypted and reader.decrypt("") == pypdf.PasswordType.NOT_DECRYPTED:
        raise ImageLoadError("PDF is password-protected")
    if not reader.pages:
        raise ImageLoadError("PDF has no pages")
    return reader


def _write_pdf(stream: BinaryIO, sources: list[Path], settings: PdfSettings, report: ConversionReport,
               progress: Callable[[int, Path], None], cancelled: CancelCheck) -> None:
    """Write every readable source as pages, in order. Documents (PDFs, and notebooks laid out on the chosen
    page size) are copied page for page, without re-rendering, so their text stays sharp and searchable.
    Unreadable sources are skipped and reported."""
    if not any(is_document(s) for s in sources):
        writer = PdfWriter(stream)
        for index, source in enumerate(sources):
            _check(cancelled)
            progress(index, source)
            try:
                pages = list(_encoded_pages(source, settings, cancelled))
            except _ERRORS as exc:
                report.failures.append((source, str(exc)))
                continue
            for encoded, placement in pages:
                writer.add_page(encoded, placement)
        if writer.page_count == 0:
            raise _NothingReadable
        _check(cancelled)
        writer.close()
        return

    combined = pypdf.PdfWriter()
    for index, source in enumerate(sources):
        _check(cancelled)
        progress(index, source)
        try:
            if is_document(source):
                reader = _read_document(source, settings)
            else:
                buffer = io.BytesIO()
                image_writer = PdfWriter(buffer)
                for encoded, placement in _encoded_pages(source, settings, cancelled):
                    image_writer.add_page(encoded, placement)
                image_writer.close()
                reader = pypdf.PdfReader(buffer)
            for page in reader.pages:
                combined.add_page(page)
        except _ERRORS as exc:
            report.failures.append((source, str(exc)))
    if not combined.pages:
        raise _NothingReadable
    _check(cancelled)
    combined.add_metadata({"/Producer": "Papyr"})
    combined.write(stream)


def convert_individual(sources: list[Path], output_dir: Path, settings: PdfSettings,
                       progress: ProgressCallback = _noop, cancelled: CancelCheck = _never
                       ) -> ConversionReport:
    """Write one PDF per source, named after it."""
    report = ConversionReport()
    destinations = individual_output_paths(sources, output_dir, ".pdf")
    try:
        for index, (source, destination) in enumerate(zip(sources, destinations)):
            try:
                with _atomic_file(destination) as stream:
                    _write_pdf(stream, [source], settings, report,
                               lambda _, path: progress(index, len(sources), path), cancelled)
                report.outputs.append(destination)
            except _NothingReadable:
                pass  # _write_pdf already recorded why this source failed
            except _ERRORS as exc:
                report.failures.append((source, str(exc)))
    except _Cancelled:
        report.cancelled = True
    progress(len(sources), len(sources), sources[-1] if sources else Path())
    return report


def convert_merged(sources: list[Path], destination: Path, settings: PdfSettings,
                   progress: ProgressCallback = _noop, cancelled: CancelCheck = _never
                   ) -> ConversionReport:
    """Write every readable source into one PDF, in order. Unreadable files are skipped and reported."""
    report = ConversionReport()
    try:
        with _atomic_file(destination) as stream:
            _write_pdf(stream, sources, settings, report,
                       lambda index, path: progress(index, len(sources), path), cancelled)
        report.outputs.append(destination)
    except _Cancelled:
        report.cancelled = True
    except _NothingReadable:
        report.failures.append((destination, "None of the files could be read"))
    except _ERRORS as exc:
        report.failures.append((destination, str(exc)))
    progress(len(sources), len(sources), sources[-1] if sources else Path())
    return report


def convert_images(sources: list[Path], output_dir: Path, settings: ImageSettings,
                   progress: ProgressCallback = _noop, cancelled: CancelCheck = _never
                   ) -> ConversionReport:
    """Write every page of every source as an image file. Multi-page sources get '-page-N' names."""
    report = ConversionReport()
    taken: set[Path] = set()
    ext = settings.format.extension
    try:
        for index, source in enumerate(sources):
            _check(cancelled)
            progress(index, len(sources), source)
            pages = iter_pages(source, keep_alpha=settings.format.keeps_alpha, pdf_dpi=settings.pdf_dpi)
            try:
                first = next(pages)
                second = next(pages, None)
                numbered = second is not None
                all_pages = itertools.chain([first] if second is None else [first, second], pages)
                for number, page in enumerate(all_pages, start=1):
                    _check(cancelled)
                    name = f"{source.stem}-page-{_page_label(number, settings.format)}{ext}" if numbered \
                        else f"{source.stem}{ext}"
                    destination = unique_path(output_dir / name, taken)
                    taken.add(destination)
                    with _atomic_file(destination) as stream:
                        save_image(page, stream, settings.format, settings.quality)
                    report.outputs.append(destination)
            except _ERRORS as exc:
                report.failures.append((source, str(exc)))
            finally:
                pages.close()
    except _Cancelled:
        report.cancelled = True
    progress(len(sources), len(sources), sources[-1] if sources else Path())
    return report


def _page_label(number: int, fmt: OutputFormat) -> str:
    """Separate GIF pages are zero-padded so they sort in page order; other formats keep their Papyr 2 names."""
    return f"{number:03d}" if fmt is OutputFormat.GIF else str(number)


def _write_animation(stream: BinaryIO, sources: list[FrameSource], settings: GifSettings, report: ConversionReport,
                     progress: Callable[[int, Path], None], cancelled: CancelCheck) -> None:
    """Write every page of every source as one frame, in order. A source that fails while decoding is reported
    and the animation goes on without its remaining pages."""
    canvas = canvas_size(sources, settings.resolution.long_side)
    writer = GifWriter(stream, settings)
    for index, source in enumerate(sources):
        _check(cancelled)
        progress(index, source.path)
        try:
            for frame in frames(source, canvas):
                _check(cancelled)
                writer.add(frame)
        except _ERRORS as exc:
            report.failures.append((source.path, str(exc)))
    if not writer.frame_count:
        raise _NothingReadable
    writer.close()


def convert_animated_gifs(sources: list[Path], output_dir: Path, settings: GifSettings,
                          progress: ProgressCallback = _noop, cancelled: CancelCheck = _never
                          ) -> ConversionReport:
    """Write one GIF per source, named after it. Every page of a PDF, notebook, or multi-page TIFF becomes a
    frame of one animation; a single picture becomes a still GIF at its own size."""
    report = ConversionReport()
    destinations = individual_output_paths(sources, output_dir, OutputFormat.GIF.extension)
    try:
        for index, (source, destination) in enumerate(zip(sources, destinations)):
            _check(cancelled)
            progress(index, len(sources), source)
            try:
                measured = measure(source)
                with _atomic_file(destination) as stream:
                    if measured.is_still:
                        pages = iter_pages(source, keep_alpha=True)
                        try:
                            save_image(next(pages), stream, OutputFormat.GIF, 0)
                        finally:
                            pages.close()
                    else:
                        _write_animation(stream, [measured], settings, report, lambda *_: None, cancelled)
                report.outputs.append(destination)
            except _NothingReadable:
                pass  # _write_animation already recorded why this source failed
            except _ERRORS as exc:
                report.failures.append((source, str(exc)))
    except _Cancelled:
        report.cancelled = True
    progress(len(sources), len(sources), sources[-1] if sources else Path())
    return report


def convert_combined_gif(sources: list[Path], destination: Path, settings: GifSettings,
                         progress: ProgressCallback = _noop, cancelled: CancelCheck = _never) -> ConversionReport:
    """Write every page of every readable source into one animated GIF, in queue order. Unreadable files are
    skipped and reported."""
    report = ConversionReport()
    measured = []
    try:
        for source in sources:
            _check(cancelled)
            try:
                measured.append(measure(source))
            except _ERRORS as exc:
                report.failures.append((source, str(exc)))
        if not measured:
            raise _NothingReadable
        with _atomic_file(destination) as stream:
            _write_animation(stream, measured, settings, report,
                             lambda index, path: progress(sources.index(path), len(sources), path), cancelled)
        report.outputs.append(destination)
    except _Cancelled:
        report.cancelled = True
    except _NothingReadable:
        report.failures.append((destination, "None of the files could be read"))
    except _ERRORS as exc:
        report.failures.append((destination, str(exc)))
    progress(len(sources), len(sources), sources[-1] if sources else Path())
    return report
