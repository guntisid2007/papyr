"""Render docs/screenshots/*.png from the real window with a few generated sample photos loaded."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pillow_heif
from PIL import Image, ImageDraw
from PySide6.QtCore import QThreadPool, Qt

from gui.app import create_app
from gui.main_window import MainWindow


def sample_photo(path: Path, size, sky, ground, sun) -> None:
    img = Image.new("RGB", size, sky)
    d = ImageDraw.Draw(img)
    w, h = size
    d.ellipse((w * 0.65, h * 0.15, w * 0.8, h * 0.15 + w * 0.15), fill=sun)
    d.polygon([(0, h), (w * 0.35, h * 0.45), (w * 0.7, h)], fill=ground)
    d.polygon([(w * 0.4, h), (w * 0.7, h * 0.55), (w, h)], fill=tuple(int(c * 0.8) for c in ground))
    pillow_heif.from_pillow(img).save(path, quality=80)


def main(scheme: str) -> None:
    out = ROOT / "docs" / "screenshots"
    out.mkdir(parents=True, exist_ok=True)
    app = create_app(sys.argv[:1])
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark if scheme == "dark" else Qt.ColorScheme.Light)
    with tempfile.TemporaryDirectory() as tmp:
        specs = [("IMG_4021.HEIC", (1600, 1200), (135, 190, 235), (70, 130, 80), (255, 210, 90)),
                 ("IMG_4022.HEIC", (1200, 1600), (250, 180, 140), (120, 80, 140), (255, 240, 200)),
                 ("IMG_4025.HEIC", (1600, 1200), (40, 50, 90), (30, 90, 110), (240, 240, 250)),
                 ("Receipt.jpg", (1200, 1600), (240, 240, 235), (200, 200, 190), (180, 180, 180)),
                 ("Whiteboard.png", (1600, 1000), (250, 250, 250), (90, 140, 220), (230, 90, 80))]
        paths = []
        for name, *args in specs:
            path = Path(tmp) / name
            sample_photo(path.with_suffix(".heic"), *args)
            if path.suffix != ".HEIC":
                Image.open(path.with_suffix(".heic")).save(path)
            else:
                path.with_suffix(".heic").rename(path)
            paths.append(path)

        window = MainWindow()
        window._output_label.setText(str(Path.home() / "Documents" / "PDFs"))
        window._merged.setChecked(True)
        window._name_edit.setText("Trip Photos")
        window.show()
        window.resize(1040, 660)
        window._stack.setCurrentIndex(0)
        app.processEvents()
        window._list.clear()
        window._refresh()
        app.processEvents()
        window.grab().save(str(out / f"empty-{scheme}.png"))

        window.add_paths(paths)
        QThreadPool.globalInstance().waitForDone()
        for _ in range(20):
            app.processEvents()
        window._list.item(1).setSelected(True)
        window._set_status("✓ Saved Trip Photos.pdf in PDFs.", "success")
        app.processEvents()
        window.grab().save(str(out / f"main-{scheme}.png"))
        window.close()
        del window


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "light")
