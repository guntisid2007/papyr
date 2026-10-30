"""Render docs/screenshots/papyr-flow.gif: the real window going from welcome to files, converting, and done.

    python scripts/animation_gif.py light|dark

Each frame is a grab of the real window. Between states the GIF blends the two frames, as the app's own
cross-fade does. The conversion is real; its progress frames are grabbed as each file finishes.
"""
import io
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice

from converter import OutputFormat
from gui.app import create_app
from screenshots import SPECS, Shooter, isolate_settings, sample_files, use_scheme

HOLD, BLEND, STEP_MS = 24, 6, 40


def to_pil(pixmap) -> Image.Image:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    image = Image.open(io.BytesIO(bytes(buffer.data()))).convert("RGB")
    return image.resize((image.width // 2, image.height // 2), Image.Resampling.LANCZOS) \
        if image.width > 1000 else image


def main(scheme: str) -> None:
    isolate_settings()
    app = create_app(sys.argv[:1])
    use_scheme(app, scheme == "dark")
    with tempfile.TemporaryDirectory() as home:
        os.environ["HOME"] = home
        pictures = Path(home) / "Pictures"
        pictures.mkdir()
        (Path(home) / "Documents" / "PDFs").mkdir(parents=True)
        shooter = Shooter(app, pictures, scheme)
        window = shooter.open(OutputFormat.PDF)
        keyframes: list[list[Image.Image]] = []

        def grab() -> Image.Image:
            shooter.settle()
            return to_pil(window.grab())

        keyframes.append([grab()])
        window.add_paths(sample_files(pictures))
        window.dock._edit(merge=True, merged_name="Trip Photos")
        keyframes.append([grab()])

        progress = []
        window.dock.convert_button.click()
        while window.is_converting():
            app.processEvents()
            state = window.state()
            if getattr(state, "done", None) is not None and len(progress) <= state.done:
                progress.append(to_pil(window.grab()))
        keyframes.append(progress)
        keyframes.append([grab()])
        window.close()

    frames, durations = [], []
    for index, group in enumerate(keyframes):
        if frames:
            for step in range(1, BLEND + 1):
                frames.append(Image.blend(frames[-1], group[0], step / BLEND))
                durations.append(STEP_MS)
        for frame in group:
            frames.append(frame)
            durations.append(STEP_MS * (HOLD if len(group) == 1 else 6))
    out = ROOT / "docs" / "screenshots" / f"papyr-flow-{scheme}.gif"
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True)
    print(out, out.stat().st_size, "bytes,", len(frames), "frames,", len(SPECS), "files")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "light")
