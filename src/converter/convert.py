import io
import itertools
import logging
import os
import shutil
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import BinaryIO

import pypdf

from utils.filenames import individual_output_paths, safe_stem, unique_path
from utils.noreplace import rename_no_replace

from .animation import FrameSource, GifWriter, canvas_size, frames, measure
from .formats import GifSettings, ImageLoadError, ImageSettings, OutputFormat, unreadable
from .images import PDF_ENCRYPTED, animation_timing, document_pdf, encode_for_pdf, is_document, is_lossless_source, \
    iter_pages, pdf_is_encrypted, save_animation, save_image
from .layout import PdfSettings, compute_placement
from .pdf_writer import PdfWriter

ProgressCallback = Callable[[int, int, Path], None]
CancelCheck = Callable[[], bool]
# Decoders and encoders raise whatever type a malformed file or a full disk trips, so any exception while converting
# one source is that source's failure. Cancelling and finding nothing readable are control flow, not errors, so they
# derive from BaseException and pass through.
_ERRORS = (Exception,)
log = logging.getLogger("papyr.convert")
# mkstemp makes files only their owner can read. A finished file gets the mode any app's new file gets instead.
# The umask can only be read by setting it, so this happens once, at import, before any conversion thread starts.
_UMASK = os.umask(0o022)
os.umask(_UMASK)
_FILE_MODE = 0o666 & ~_UMASK


@dataclass
class ConversionReport:
    outputs: list[Path] = field(default_factory=list)
    failures: list[tuple[Path, str]] = field(default_factory=list)
    cancelled: bool = False


class _Cancelled(BaseException):
    pass


class _NothingReadable(BaseException):
    pass


class _Staged:
    """The new files from one source. Each is written to a hidden temporary file in its destination folder, so
    nothing appears under a real name until every file is complete, and moving one into place is a rename on
    the same disk. Leaving the block without commit removes them all."""

    def __init__(self):
        self._files: list[tuple[str, Path]] = []  # (temporary file, the name it should get)

    def __enter__(self) -> "_Staged":
        return self

    def __exit__(self, *exc) -> None:
        for temp, _ in self._files:
            _remove(Path(temp))
        self._files.clear()

    @contextmanager
    def file(self, destination: Path) -> Iterator[BinaryIO]:
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix=".papyr-", suffix=".part", dir=destination.parent)
        self._files.append((temp, destination))
        with os.fdopen(fd, "wb") as stream:
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, _FILE_MODE)
        if os.path.getsize(temp) == 0:
            raise OSError(f"Writing {destination.name} produced an empty file")

    def commit(self, taken: set[Path], replace: bool = False) -> list[Path]:
        """Move every file into place and return where each went. A name already used on disk or in this batch
        gets a ' (n)' suffix, unless replace says the user agreed to overwrite it. If one move fails, the files
        this commit already placed are removed again, so a source never leaves only some of its files. A file
        is removed only while it is still the one Papyr placed, never one another program put there since."""
        placed: list[tuple[Path, _Identity]] = []
        try:
            for temp, destination in self._files:
                placed.append(_place(temp, destination, taken, replace))
        except BaseException:
            for path, identity in placed:
                _remove_if_ours(path, identity)
                taken.discard(path)
            raise
        self._files.clear()
        return [path for path, _ in placed]


# Device, inode, and size of a file Papyr placed. Not the modification time: some network disks set it on close.
_Identity = tuple[int, int, int]


def _identity(info: os.stat_result) -> _Identity:
    return info.st_dev, info.st_ino, info.st_size


def _place(temp: str, wanted: Path, taken: set[Path], replace: bool) -> tuple[Path, _Identity]:
    """Give temp its name. Without replace this never replaces a file, even one that appears at the chosen name
    while Papyr moves into it: the move is an atomic no-replace rename, else a hard link, else a copy into a file
    created exclusively. Only the copy is not atomic. A crash during it can leave a partial file under the name."""
    if replace:
        os.replace(temp, wanted)
        taken.add(wanted)
        return wanted, _identity(os.stat(wanted))
    while True:
        destination = unique_path(wanted, taken)
        taken.add(destination)
        try:  # a real failure to move propagates; only an unsupported move falls back
            if rename_no_replace(temp, destination):
                return destination, _identity(os.stat(destination))
        except FileExistsError:
            continue  # the name appeared since unique_path looked
        try:
            os.link(temp, destination)
        except FileExistsError:
            continue
        except OSError:  # no hard links on this disk (FAT, exFAT, some network shares)
            try:
                return destination, _copy_exclusive(temp, destination)
            except FileExistsError:
                continue
        _remove(Path(temp))
        return destination, _identity(os.stat(destination))


def _copy_exclusive(temp: str, destination: Path) -> _Identity:
    """Create destination only if it doesn't exist, and write temp's bytes through that handle. Another program
    that replaces the name meanwhile keeps its file: Papyr's handle still points at the file Papyr created."""
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0), 0o666)
    try:
        with os.fdopen(fd, "wb", closefd=False) as out, open(temp, "rb") as source:
            shutil.copyfileobj(source, out, 1024 * 1024)
            out.flush()
            os.fsync(fd)
        identity = _identity(os.fstat(fd))
        if _identity(os.stat(destination)) != identity:  # renamed over while copying: that file is not Papyr's
            raise FileExistsError(f"{destination} was replaced while Papyr wrote it")
    except BaseException:
        info = os.fstat(fd)
        os.close(fd)
        _remove_if_ours(destination, _identity(info))
        raise
    os.close(fd)
    _remove(Path(temp))
    return identity


def _remove_if_ours(path: Path, identity: _Identity) -> None:
    """Remove a file Papyr placed, unless something else now has its name."""
    try:
        if _identity(os.stat(path)) != identity:
            log.warning("Left %s in place: another program replaced it after Papyr wrote it", path)
            return
    except FileNotFoundError:
        return
    except OSError:
        log.warning("Could not check %s", path, exc_info=True)
        return
    _remove(path)


def _remove(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        log.warning("Could not remove %s", path, exc_info=True)


def _fail(report: ConversionReport, path: Path, exc: Exception) -> None:
    """Record a file that couldn't be converted, and keep the traceback in the local log."""
    log.warning("Could not convert %s", path, exc_info=exc)
    report.failures.append((path, str(exc)))


def _never() -> bool:
    return False


def _noop(done: int, total: int, current: Path) -> None:
    pass


def _check(cancelled: CancelCheck) -> None:
    if cancelled():
        raise _Cancelled


def _encoded_pages(source: Path, settings: PdfSettings, cancelled: CancelCheck) -> Iterator[tuple]:
    lossless = is_lossless_source(source)
    for page in iter_pages(source, every_frame=settings.every_frame):
        _check(cancelled)
        encoded = encode_for_pdf(page, lossless)
        yield encoded, compute_placement(encoded.width, encoded.height, settings)


def _read_document(source: Path, settings: PdfSettings) -> pypdf.PdfReader:
    """Open a document for copying into a PDF. An encrypted PDF is refused even when it opens without a password:
    its encryption carries the owner's restrictions, and a copy would drop them."""
    pdf = document_pdf(source, settings)
    if pdf_is_encrypted(pdf):
        raise ImageLoadError(PDF_ENCRYPTED)
    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf) if isinstance(pdf, bytes) else pdf)
        if reader.is_encrypted:  # PDFium saw no encryption, but pypdf would decrypt something: refuse all the same
            raise ImageLoadError(PDF_ENCRYPTED)
        if not reader.pages:
            raise ImageLoadError("PDF has no pages")
    except ImageLoadError:
        raise
    except pypdf.errors.DependencyError as exc:  # pypdf met AES, so the file is encrypted
        raise ImageLoadError(PDF_ENCRYPTED) from exc
    except Exception as exc:
        raise unreadable(exc, "PDF") from exc
    return reader


def _copy_pages(combined: pypdf.PdfWriter, reader: pypdf.PdfReader) -> None:
    """Copy every page, or none. pypdf reads objects as it copies them, so a damaged object fails part way
    through."""
    before = len(combined.pages)
    try:
        for page in reader.pages:
            combined.add_page(page)
    except Exception as exc:
        while len(combined.pages) > before:
            combined.remove_page(len(combined.pages) - 1)
        raise unreadable(exc, "PDF") from exc


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
                _fail(report, source, exc)
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
            _copy_pages(combined, reader)
        except _ERRORS as exc:
            _fail(report, source, exc)
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
    taken: set[Path] = set()
    destinations = individual_output_paths(sources, output_dir, ".pdf")
    try:
        for index, (source, destination) in enumerate(zip(sources, destinations)):
            try:
                with _Staged() as staged:
                    with staged.file(destination) as stream:
                        _write_pdf(stream, [source], settings, report,
                                   lambda _, path: progress(index, len(sources), path), cancelled)
                    report.outputs += staged.commit(taken)
            except _NothingReadable:
                pass  # _write_pdf already recorded why this source failed
            except _ERRORS as exc:
                _fail(report, source, exc)
    except _Cancelled:
        report.cancelled = True
    progress(len(sources), len(sources), sources[-1] if sources else Path())
    return report


def convert_merged(sources: list[Path], destination: Path, settings: PdfSettings,
                   progress: ProgressCallback = _noop, cancelled: CancelCheck = _never
                   ) -> ConversionReport:
    """Write every readable source into one PDF, in order. Unreadable files are skipped and reported. The window
    asks before destination is replaced."""
    report = ConversionReport()
    try:
        with _Staged() as staged:
            with staged.file(destination) as stream:
                _write_pdf(stream, sources, settings, report,
                           lambda index, path: progress(index, len(sources), path), cancelled)
            report.outputs += staged.commit(set(), replace=True)
    except _Cancelled:
        report.cancelled = True
    except _NothingReadable:
        report.failures.append((destination, "None of the files could be read"))
    except _ERRORS as exc:
        _fail(report, destination, exc)
    progress(len(sources), len(sources), sources[-1] if sources else Path())
    return report


def convert_images(sources: list[Path], output_dir: Path, settings: ImageSettings,
                   progress: ProgressCallback = _noop, cancelled: CancelCheck = _never
                   ) -> ConversionReport:
    """Write every page of every source as an image file. Multi-page sources get '-page-N' names, and the frames
    of an animation '-frame-NNN'. A source's files appear only once all of them are written."""
    report = ConversionReport()
    taken: set[Path] = set()
    try:
        for index, source in enumerate(sources):
            _check(cancelled)
            progress(index, len(sources), source)
            try:
                with _Staged() as staged:
                    _stage_images(staged, source, output_dir, settings, cancelled)
                    report.outputs += staged.commit(taken)
            except _ERRORS as exc:
                _fail(report, source, exc)
    except _Cancelled:
        report.cancelled = True
    progress(len(sources), len(sources), sources[-1] if sources else Path())
    return report


def _stage_images(staged: _Staged, source: Path, output_dir: Path, settings: ImageSettings,
                  cancelled: CancelCheck) -> None:
    fmt = settings.format
    stem = safe_stem(source.stem)
    timing = animation_timing(source) if settings.keeps_animation or settings.every_frame else None
    if timing is not None and settings.keeps_animation:
        _check(cancelled)
        with staged.file(output_dir / f"{stem}{fmt.extension}") as stream:
            save_animation(source, timing, stream, settings.quality)
        _check(cancelled)
        return
    every_frame = settings.every_frame and timing is not None
    pages = iter_pages(source, keep_alpha=fmt.keeps_alpha, pdf_dpi=settings.pdf_dpi, every_frame=every_frame)
    try:
        first = next(pages)
        second = next(pages, None)
        all_pages = itertools.chain([first] if second is None else [first, second], pages)
        for number, page in enumerate(all_pages, start=1):
            _check(cancelled)
            if second is None:
                name = stem
            elif every_frame:
                name = f"{stem}-frame-{number:0{max(3, len(str(len(timing.durations))))}d}"
            else:
                name = f"{stem}-page-{_page_label(number, fmt)}"
            with staged.file(output_dir / f"{name}{fmt.extension}") as stream:
                save_image(page, stream, fmt, settings.quality)
    finally:
        pages.close()


def _page_label(number: int, fmt: OutputFormat) -> str:
    """Separate GIF pages are zero-padded so they sort in page order; other formats keep their Papyr 2 names."""
    return f"{number:03d}" if fmt is OutputFormat.GIF else str(number)


def _write_animation(stream: BinaryIO, sources: list[FrameSource], settings: GifSettings, report: ConversionReport,
                     progress: Callable[[int, Path], None], cancelled: CancelCheck) -> None:
    """Write every page of every source as one frame, in order. An animated source keeps its own frame durations.
    A source that fails while decoding is reported, and none of its frames are kept."""
    canvas = canvas_size(sources, settings.resolution.long_side)
    writer = GifWriter(stream, settings)
    for index, source in enumerate(sources):
        _check(cancelled)
        progress(index, source.path)
        durations = source.timing.durations if source.timing else (None,) * len(source.sizes)
        checkpoint = writer.checkpoint()
        try:
            for frame, duration in zip(frames(source, canvas), durations, strict=True):
                _check(cancelled)
                writer.add(frame, duration)
        except _ERRORS as exc:
            writer.rollback(checkpoint)
            _fail(report, source.path, exc)
    if not writer.frame_count:
        raise _NothingReadable
    _check(cancelled)
    writer.close()


def convert_animated_gifs(sources: list[Path], output_dir: Path, settings: GifSettings,
                          progress: ProgressCallback = _noop, cancelled: CancelCheck = _never
                          ) -> ConversionReport:
    """Write one GIF per source, named after it. Every page of a PDF, notebook, or multi-page TIFF becomes a
    frame of one animation; an animated GIF or WebP keeps its own frames, timing, and plays; a single picture
    becomes a still GIF at its own size."""
    report = ConversionReport()
    taken: set[Path] = set()
    destinations = individual_output_paths(sources, output_dir, OutputFormat.GIF.extension)
    try:
        for index, (source, destination) in enumerate(zip(sources, destinations)):
            _check(cancelled)
            progress(index, len(sources), source)
            try:
                measured = measure(source)
                own = replace(settings, plays=measured.timing.plays) if measured.timing else settings
                with _Staged() as staged:
                    with staged.file(destination) as stream:
                        if measured.is_still:
                            pages = iter_pages(source, keep_alpha=True)
                            try:
                                save_image(next(pages), stream, OutputFormat.GIF, 0)
                            finally:
                                pages.close()
                        else:
                            _write_animation(stream, [measured], own, report, lambda *_: None, cancelled)
                    report.outputs += staged.commit(taken)
            except _NothingReadable:
                pass  # _write_animation already recorded why this source failed
            except _ERRORS as exc:
                _fail(report, source, exc)
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
                _fail(report, source, exc)
        if not measured:
            raise _NothingReadable
        with _Staged() as staged:
            with staged.file(destination) as stream:
                _write_animation(stream, measured, settings, report,
                                 lambda index, path: progress(sources.index(path), len(sources), path), cancelled)
            report.outputs += staged.commit(set(), replace=True)
    except _Cancelled:
        report.cancelled = True
    except _NothingReadable:
        report.failures.append((destination, "None of the files could be read"))
    except _ERRORS as exc:
        _fail(report, destination, exc)
    progress(len(sources), len(sources), sources[-1] if sources else Path())
    return report
