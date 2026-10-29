import threading
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QImage

from converter import PdfSettings, convert_individual, convert_merged
from converter.images import ImageLoadError, make_thumbnail


def pil_to_qimage(image: Image.Image) -> QImage:
    data = image.tobytes("raw", "RGBA")
    return QImage(data, image.width, image.height, image.width * 4, QImage.Format.Format_RGBA8888).copy()


class ThumbnailLoader(QObject):
    """Decodes previews on the global thread pool. Results arrive on the GUI thread."""

    loaded = Signal(str, QImage)
    failed = Signal(str, str)

    def __init__(self, size: int, parent=None):
        super().__init__(parent)
        self._size = size
        self._pool = QThreadPool.globalInstance()

    def request(self, path: Path) -> None:
        self._pool.start(_ThumbnailTask(self, path, self._size))

    def shutdown(self) -> None:
        self._pool.clear()
        self._pool.waitForDone(3000)


class _ThumbnailTask(QRunnable):
    def __init__(self, loader: ThumbnailLoader, path: Path, size: int):
        super().__init__()
        self._loader, self._path, self._size = loader, path, size

    def run(self) -> None:
        try:
            image = pil_to_qimage(make_thumbnail(self._path, self._size))
        except ImageLoadError as exc:
            self._loader.failed.emit(str(self._path), str(exc))
        except Exception as exc:  # a preview failure must never take down the pool thread
            self._loader.failed.emit(str(self._path), f"Could not read image: {exc}")
        else:
            self._loader.loaded.emit(str(self._path), image)


class ConversionWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(object)

    def __init__(self, sources: list[Path], settings: PdfSettings, *,
                 output_dir: Path | None = None, merged_path: Path | None = None):
        super().__init__()
        self._sources, self._settings = sources, settings
        self._output_dir, self._merged_path = output_dir, merged_path
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        report_progress = lambda done, total, path: self.progress.emit(done, total, path.name)
        if self._merged_path is not None:
            report = convert_merged(self._sources, self._merged_path, self._settings,
                                    report_progress, self._cancel.is_set)
        else:
            report = convert_individual(self._sources, self._output_dir, self._settings,
                                        report_progress, self._cancel.is_set)
        self.finished.emit(report)
