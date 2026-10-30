"""Render the real window to PNG with generated sample files.

    python scripts/screenshots.py light|dark [--states DIR]

Without --states it writes the README screenshots to docs/screenshots/. With --states it renders every state a
reviewer should check into DIR: welcome, a workspace with 3 and with 200 files, converting mid-progress, done with
all successes, done with a partial failure, and each output format's controls, at the default, minimum, and a wide
window size. Run it on a desktop session so macOS draws real fonts; offscreen Qt also works, and switches light
and dark through the application palette instead of the system appearance.
"""
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pillow_heif
from PIL import Image, ImageDraw
from PySide6.QtCore import QSettings, Qt, QThreadPool
from PySide6.QtGui import QColor, QPalette

from converter import ConversionReport, OutputFormat
from gui.app import create_app
from gui.main_window import DEFAULT_SIZE, MINIMUM_SIZE, MainWindow, RunSpec
from gui.model import Converting
from gui.widgets import FadeOut
from gui.workers import ConversionWorker

SPECS = [("IMG_4021.HEIC", (1600, 1200), (135, 190, 235), (70, 130, 80), (255, 210, 90)),
         ("IMG_4022.HEIC", (1200, 1600), (250, 180, 140), (120, 80, 140), (255, 240, 200)),
         ("IMG_4025.HEIC", (1600, 1200), (40, 50, 90), (30, 90, 110), (240, 240, 250)),
         ("Receipt.jpg", (1200, 1600), (240, 240, 235), (200, 200, 190), (180, 180, 180)),
         ("Whiteboard.png", (1600, 1000), (250, 250, 250), (90, 140, 220), (230, 90, 80))]
SIZES = {"default": DEFAULT_SIZE, "minimum": MINIMUM_SIZE, "wide": (1280, 800)}


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
    if path.suffix.lower() == ".heic":
        pillow_heif.from_pillow(img).save(path, quality=80)
    else:
        img.save(path)


def sample_files(folder: Path) -> list[Path]:
    paths = []
    for name, *args in SPECS:
        path = folder / name
        sample_photo(path, *args)
        paths.append(path)
    return paths


def many_files(folder: Path, count: int) -> list[Path]:
    folder.mkdir(exist_ok=True)
    paths = []
    for i in range(count):
        hue = (i * 37) % 360
        sky = QColor.fromHsv(hue, 90, 235)
        ground = QColor.fromHsv((hue + 120) % 360, 140, 140)
        path = folder / f"Scan {i + 1:03d}.jpg"
        sample_photo(path, (240, 180), sky.getRgb()[:3], ground.getRgb()[:3], (255, 230, 150))
        paths.append(path)
    return paths


def sample_pdf(path: Path) -> Path:
    page = Image.new("RGB", (850, 1100), "white")
    draw = ImageDraw.Draw(page)
    for y in range(120, 900, 60):
        draw.rectangle((90, y, 760, y + 18), fill=(210, 210, 215))
    page.save(path)
    return path


def use_scheme(app, dark: bool) -> None:
    """Switch light and dark: the system appearance on a desktop session, the palette offscreen."""
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)
    if app.platformName() == "offscreen":
        palette = QPalette()
        if dark:
            for role, color in [(QPalette.ColorRole.Window, "#2b2b2b"), (QPalette.ColorRole.WindowText, "#ffffff"),
                                (QPalette.ColorRole.Base, "#1e1e1e"), (QPalette.ColorRole.Text, "#ffffff")]:
                palette.setColor(role, QColor(color))
        app.setPalette(palette)
    app.processEvents()


class Shooter:
    def __init__(self, app, out: Path, scheme: str):
        self.app, self.out, self.scheme = app, out, scheme
        self.window: MainWindow | None = None

    def open(self, fmt: OutputFormat = OutputFormat.PDF, size: str = "default") -> MainWindow:
        QSettings().clear()
        window = MainWindow()
        window.menuBar().hide()  # macOS shows the menu bar at the top of the screen, not in the window
        window.set_output_dir(Path.home() / "Documents" / "PDFs")
        window.show()
        window.resize(*SIZES[size])
        window.dock._edit(format=fmt)
        self.window = window
        return window

    def settle(self) -> None:
        QThreadPool.globalInstance().waitForDone()
        deadline = time.monotonic() + 2
        while self.window.findChildren(FadeOut) and time.monotonic() < deadline:
            self.app.processEvents()
        for _ in range(40):
            self.app.processEvents()

    def shoot(self, name: str, size: str = "default") -> Path:
        self.window.resize(*SIZES[size])
        self.settle()
        path = self.out / f"{name}-{self.scheme}-{size}.png"
        self.window.grab().save(str(path))
        print(path)
        return path

    def shoot_sizes(self, name: str) -> None:
        for size in SIZES:
            self.shoot(name, size)

    def convert(self) -> None:
        self.window.dock.convert_button.click()
        while self.window.is_converting():
            self.app.processEvents()
        self.settle()

    def close(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()


def docs(app, scheme: str, tmp: Path, out: Path) -> None:
    """The README screenshots."""
    shooter = Shooter(app, out, scheme)
    shooter.open()
    shooter.shoot("welcome")
    shooter.window.add_paths(sample_files(tmp))
    shooter.window.dock._edit(merge=True, merged_name="Trip Photos")
    shooter.shoot("workspace")
    shooter.convert()
    shooter.shoot("done")
    shooter.close()


def states(app, scheme: str, tmp: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    photos = sample_files(tmp)
    shooter = Shooter(app, out, scheme)

    shooter.open()
    shooter.shoot_sizes("welcome")
    shooter.window.add_paths(photos[:3])
    shooter.shoot_sizes("workspace-3")
    shooter.close()

    shooter.open(OutputFormat.JPEG)
    shooter.window.add_paths(many_files(tmp / "many", 200))
    shooter.shoot_sizes("workspace-200")

    window = shooter.window
    sources = window.queue.paths()
    release = threading.Event()

    def job(progress, cancelled):
        progress(37, len(sources), sources[37])
        release.wait(30)
        return ConversionReport(cancelled=True)

    window._run = RunSpec(sources, OutputFormat.JPEG, False, window.output_dir())
    window._start(ConversionWorker(job), len(sources))
    while not (isinstance(window.state(), Converting) and window.state().done == 37):
        app.processEvents()
    shooter.shoot_sizes("converting")
    release.set()
    while window.is_converting():
        app.processEvents()
    shooter.close()

    shooter.open(OutputFormat.JPEG)
    shooter.window.add_paths(photos)
    shooter.convert()
    shooter.shoot_sizes("done-success")
    shooter.close()

    shooter.open(OutputFormat.PNG)
    doomed = [tmp / "Scan (damaged).jpg", tmp / "Lost photo.heic"]
    shooter.window.add_paths(photos[:3])
    for path in doomed:
        sample_photo(path, (300, 200), (200, 200, 200), (90, 90, 90), (255, 255, 255))
    shooter.window.add_paths(doomed)
    shooter.settle()
    doomed[0].write_bytes(b"not really a jpeg")
    doomed[1].unlink()
    shooter.convert()
    shooter.shoot_sizes("done-partial")
    shooter.close()

    document = sample_pdf(tmp / "Lease agreement.pdf")
    for fmt in OutputFormat:
        shooter.open(fmt)
        shooter.window.add_paths([photos[0], photos[1], document])
        if fmt is OutputFormat.PDF:
            shooter.window.dock._edit(merge=True, merged_name="Trip Photos")
        shooter.shoot(f"format-{fmt.name.lower()}")
        shooter.close()

    shooter.open(OutputFormat.PDF)
    shooter.window.add_paths(photos[:3])
    shooter.window.set_output_dir(tmp / "Exports (deleted)")
    shooter.shoot("destination-missing")
    shooter.close()


def main(scheme: str, states_dir: Path | None) -> None:
    isolate_settings()
    app = create_app(sys.argv[:1])
    use_scheme(app, scheme == "dark")
    with tempfile.TemporaryDirectory() as home:
        # Converted files really are written, to a stand-in home folder, so paths read ~/Documents/PDFs.
        os.environ["HOME"] = home
        tmp = Path(home) / "Pictures"
        tmp.mkdir()
        (Path(home) / "Documents" / "PDFs").mkdir(parents=True)
        if states_dir is None:
            docs(app, scheme, tmp, ROOT / "docs" / "screenshots")
        else:
            states(app, scheme, tmp, states_dir)


if __name__ == "__main__":
    args = sys.argv[1:]
    states_dir = Path(args[args.index("--states") + 1]) if "--states" in args else None
    main(args[0] if args and not args[0].startswith("--") else "light", states_dir)
