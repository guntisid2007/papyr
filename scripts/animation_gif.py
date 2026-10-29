"""Render docs/screenshots/save-animation.gif from the real window's save animation."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, QThreadPool

from gui.app import create_app
from gui.main_window import MainWindow
from screenshots import isolate_settings, sample_photo

FRAMES = 42


def to_pil(pixmap) -> Image.Image:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    import io
    return Image.open(io.BytesIO(bytes(buffer.data()))).convert("RGB")


def main() -> None:
    isolate_settings()
    app = create_app(sys.argv[:1])
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for i, colors in enumerate([((135, 190, 235), (70, 130, 80), (255, 210, 90)),
                                    ((250, 180, 140), (120, 80, 140), (255, 240, 200)),
                                    ((40, 50, 90), (30, 90, 110), (240, 240, 250))]):
            path = Path(tmp) / f"IMG_40{21 + i}.HEIC"
            sample_photo(path, (1600, 1200), *colors)
            paths.append(path)
        window = MainWindow()
        window.resize(1040, 660)
        window.show()
        window.add_paths(paths)
        QThreadPool.globalInstance().waitForDone()
        for _ in range(20):
            app.processEvents()
        window._set_status("✓ Created 3 PDFs in PDFs.", "success")
        window._open_button.show()
        app.processEvents()

        animation = window._play_save_animation(3)
        animation._animation.stop()
        frames = []
        for i in range(FRAMES + 1):
            animation.set_progress(i / FRAMES)
            app.processEvents()
            frame = to_pil(window.grab())
            frames.append(frame.resize((frame.width // 2, frame.height // 2), Image.Resampling.LANCZOS))
        out = ROOT / "docs" / "screenshots" / "save-animation.gif"
        frames[0].save(out, save_all=True, append_images=frames[1:] + [frames[-1]] * 15,
                       duration=33, loop=0, optimize=True)
        for t in (0.25, 0.5, 0.78):
            frames[round(t * FRAMES)].save(f"/tmp/anim-{t}.png")
        print(out, out.stat().st_size)
        window.close()
        del window


if __name__ == "__main__":
    main()
