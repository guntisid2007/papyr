from pathlib import Path

import pillow_heif
import pytest
from PIL import Image

FIXTURES = Path(__file__).parent / "fixtures"


def make_image(path: Path, size: tuple[int, int], color="red", **save_kwargs) -> Path:
    image = Image.new("RGB", size, color)
    if path.suffix.lower() in (".heic", ".heif"):
        pillow_heif.from_pillow(image).save(path, quality=90)
    else:
        image.save(path, **save_kwargs)
    return path


@pytest.fixture
def sample_heic() -> Path:
    return FIXTURES / "sample.heic"


@pytest.fixture
def make(tmp_path):
    def _make(name: str, size=(400, 300), color="red", **kwargs) -> Path:
        return make_image(tmp_path / name, size, color, **kwargs)
    return _make
