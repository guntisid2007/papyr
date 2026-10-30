from pathlib import Path

import pillow_heif
import pytest
from PIL import Image

from gui.app import use_headless_platform

use_headless_platform()

FIXTURES = Path(__file__).parent / "fixtures"


def make_image(path: Path, size: tuple[int, int], color="red", **save_kwargs) -> Path:
    image = Image.new("RGB", size, color)
    if path.suffix.lower() in (".heic", ".heif"):
        pillow_heif.from_pillow(image).save(path, quality=90)
    else:
        image.save(path, **save_kwargs)
    return path


@pytest.fixture(scope="session")
def app(tmp_path_factory):
    """The one Qt application for the whole run. Notebook rendering and the window both need it."""
    from PySide6.QtCore import QSettings

    from gui.app import create_app
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                      str(tmp_path_factory.mktemp("settings")))  # never touch the real preferences
    return create_app(["test"])


@pytest.fixture
def sample_heic() -> Path:
    return FIXTURES / "sample.heic"


@pytest.fixture
def make(tmp_path):
    def _make(name: str, size=(400, 300), color="red", **kwargs) -> Path:
        return make_image(tmp_path / name, size, color, **kwargs)
    return _make
