import threading
from collections.abc import Callable
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QImage

from converter import ConversionReport
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
    """Runs one conversion job on a QThread. The job takes (progress, cancelled) and returns a report."""

    progress = Signal(int, int, str)
    finished = Signal(object)

    def __init__(self, job: Callable[..., ConversionReport]):
        super().__init__()
        self._job = job
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        try:
            report = self._job(lambda done, total, path: self.progress.emit(done, total, path.name),
                               self._cancel.is_set)
        except Exception as exc:  # the window waits on finished, so it must always be emitted
            report = ConversionReport(failures=[(Path("Conversion"), f"Unexpected error: {exc}")])
        self.finished.emit(report)
