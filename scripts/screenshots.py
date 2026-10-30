"""Render docs/screenshots/{empty,main}-{light,dark}.png from the real window with generated sample photos.

    python scripts/screenshots.py light|dark [--states DIR]

--states also renders the window in the states a reviewer should check (a failed row, the PDF page resolution
setting, a combined PDF, a missing Save to folder, and a conversion in progress) into DIR.
The light and dark switch needs the native platform, so run this on a desktop session, not offscreen.
"""
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pillow_heif
from PIL import Image, ImageDraw
from PySide6.QtCore import QSettings, QThreadPool, Qt

from converter import ConversionReport, OutputFormat
from gui.app import create_app
from gui.main_window import MainWindow, Run
from gui.save_animation import SaveAnimation
from gui.workers import ConversionWorker

SPECS = [("IMG_4021.HEIC", (1600, 1200), (135, 190, 235), (70, 130, 80), (255, 210, 90)),
         ("IMG_4022.HEIC", (1200, 1600), (250, 180, 140), (120, 80, 140), (255, 240, 200)),
         ("IMG_4025.HEIC", (1600, 1200), (40, 50, 90), (30, 90, 110), (240, 240, 250)),
         ("Receipt.jpg", (1200, 1600), (240, 240, 235), (200, 200, 190), (180, 180, 180)),
         ("Whiteboard.png", (1600, 1000), (250, 250, 250), (90, 140, 220), (230, 90, 80))]
TYPICAL_FOLDER = Path.home() / "Documents" / "PDFs"


def isolate_settings() -> None:
    """Keep the scripted window from reading or overwriting the real app preferences."""
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tempfile.mkdtemp())


def sample_photo(path: Path, size, sky, ground, sun) -> None:
    img = Image.new("RGB", size, sky)
    d = ImageDraw.Draw(img)
    w, h = size
    d.ellipse((w * 0.65, h * 0.15, w * 0.8, h * 0.15 + w * 0.15), fill=sun)
    d.polygon([(0, h), (w * 0.35, h * 0.45), (w * 0.7, h)], fill=ground)
    d.polygon([(w * 0.4, h), (w * 0.7, h * 0.55), (w, h)], fill=tuple(int(c * 0.8) for c in ground))
    pillow_heif.from_pillow(img).save(path, quality=80)


def sample_files(folder: Path) -> list[Path]:
    paths = []
    for name, *args in SPECS:
        path = folder / name
        sample_photo(path.with_suffix(".heic"), *args)
        if path.suffix != ".HEIC":
            Image.open(path.with_suffix(".heic")).save(path)
        else:
            path.with_suffix(".heic").rename(path)
        paths.append(path)
    return paths


def sample_pdf(path: Path) -> Path:
    page = Image.new("RGB", (850, 1100), "white")
    draw = ImageDraw.Draw(page)
    for y in range(120, 900, 60):
        draw.rectangle((90, y, 760, y + 18), fill=(210, 210, 215))
    page.save(path)
    return path


class Shooter:
    def __init__(self, app, window: MainWindow):
        self.app, self.window = app, window

    def settle(self) -> None:
        QThreadPool.globalInstance().waitForDone()
        while self.window.findChildren(SaveAnimation):
            self.app.processEvents()
        for _ in range(20):
            self.app.processEvents()

    def shoot(self, path: Path, folder: Path | None = None) -> None:
        self.settle()
        if folder is not None:
            self.window._panel.show_destination(folder, None)  # a folder a reader would pick, not the temp dir
        self.app.processEvents()
        self.window.grab().save(str(path))
        print(path)

    def convert(self) -> None:
        self.window._convert_button.click()
        while self.window._converting:
            self.app.processEvents()
        self.settle()


def new_window(output: Path) -> MainWindow:
    QSettings().clear()
    window = MainWindow()
    window.menuBar().hide()  # macOS shows the menu bar at the top of the screen, not in the window
    window.set_output_dir(output)
    window.show()
    window.resize(1000, 660)
    return window


def choose_format(window: MainWindow, fmt: OutputFormat) -> None:
    window._panel.format_combo.setCurrentIndex(window._panel.format_combo.findData(fmt))


def docs(app, scheme: str, tmp: Path, out: Path) -> None:
    window = new_window(tmp / "out")
    shooter = Shooter(app, window)
    if scheme == "dark":
        choose_format(window, OutputFormat.JPEG)
    else:
        choose_format(window, OutputFormat.PDF)
        window._panel.combine_check.setChecked(True)
        window._panel.name_edit.setText("Trip Photos")
    shooter.shoot(out / f"empty-{scheme}.png", TYPICAL_FOLDER)

    window.add_paths(sample_files(tmp))
    shooter.settle()
    shooter.convert()
    window._queue.item(1).setSelected(True)
    shooter.shoot(out / f"main-{scheme}.png", TYPICAL_FOLDER)
    window.close()


def states(app, scheme: str, tmp: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    photos = sample_files(tmp)

    window = new_window(tmp / "out")
    shooter = Shooter(app, window)
    choose_format(window, OutputFormat.JPEG)
    window.add_paths(photos[:3])
    shooter.settle()
    photos[1].unlink()
    shooter.convert()
    shooter.shoot(out / f"partial-failure-{scheme}.png")
    window.close()

    window = new_window(tmp / "out")
    shooter = Shooter(app, window)
    choose_format(window, OutputFormat.JPEG)
    window.add_paths([photos[0], sample_pdf(tmp / "Lease agreement.pdf")])
    shooter.shoot(out / f"pdf-to-jpeg-{scheme}.png")
    window.close()

    window = new_window(tmp / "out")
    shooter = Shooter(app, window)
    choose_format(window, OutputFormat.PDF)
    window._panel.combine_check.setChecked(True)
    window._panel.name_edit.setText("Trip Photos")
    window.add_paths([photos[0], *photos[2:]])
    shooter.settle()
    shooter.convert()
    shooter.shoot(out / f"combined-pdf-{scheme}.png")
    window.close()

    window = new_window(tmp / "out")
    shooter = Shooter(app, window)
    window.add_paths(photos[2:])
    window.set_output_dir(tmp / "Exports (deleted)")
    shooter.shoot(out / f"destination-warning-{scheme}.png")
    window.close()

    window = new_window(tmp / "out")
    shooter = Shooter(app, window)
    window.add_paths(photos[2:] + [photos[0]])
    shooter.settle()
    release = threading.Event()

    sources = window._queue.paths()

    def job(progress, cancelled):
        progress(2, len(sources), sources[2])
        release.wait(10)
        return ConversionReport(cancelled=True)

    window._start(ConversionWorker(job), Run(sources, False))
    while not window._status.text().startswith("Converting"):
        app.processEvents()
    shooter.shoot(out / f"converting-{scheme}.png")
    release.set()
    while window._converting:
        app.processEvents()
    window.close()


def main(scheme: str, states_dir: Path | None) -> None:
    isolate_settings()
    app = create_app(sys.argv[:1])
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark if scheme == "dark" else Qt.ColorScheme.Light)
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "out").mkdir()
        docs(app, scheme, Path(tmp), ROOT / "docs" / "screenshots")
    if states_dir is not None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "out").mkdir()
            states(app, scheme, Path(tmp), states_dir)


if __name__ == "__main__":
    args = sys.argv[1:]
    states_dir = Path(args[args.index("--states") + 1]) if "--states" in args else None
    main(args[0] if args and not args[0].startswith("--") else "light", states_dir)
