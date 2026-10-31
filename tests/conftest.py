import tempfile
from pathlib import Path

import pillow_heif
import pytest
from PIL import Image

from gui.app import use_headless_platform, use_settings_dir

use_headless_platform()
# Set before any test can build a window, whatever fixtures it asks for: tests never touch the real preferences.
SETTINGS_DIR = Path(tempfile.mkdtemp(prefix="papyr-test-settings-"))
use_settings_dir(SETTINGS_DIR)

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
    from gui.app import create_app
    return create_app(["test"])


@pytest.fixture
def sample_heic() -> Path:
    return FIXTURES / "sample.heic"


@pytest.fixture
def make(tmp_path):
    def _make(name: str, size=(400, 300), color="red", **kwargs) -> Path:
        return make_image(tmp_path / name, size, color, **kwargs)
    return _make


def pytest_addoption(parser):
    parser.addoption("--report-dir", default=None,
                     help="write conversion-matrix.csv/.md and run-summary.json for the matrix tests here")


def pytest_configure(config):
    for marker, about in [("matrix", "every input format against every output, through the real engine"),
                          ("pdf", "PDF input or output behavior"), ("animation", "animated GIF behavior"),
                          ("notebook", "Jupyter notebook conversion"), ("negative", "bad inputs and hostile paths"),
                          ("batch", "many files at once"), ("settings", "conversion options reach the output"),
                          ("gui_smoke", "conversions driven through the real window")]:
        config.addinivalue_line("markers", f"{marker}: {about}")


def pytest_sessionfinish(session, exitstatus):
    directory = session.config.getoption("--report-dir")
    if not directory:
        return
    from conversion_matrix import RESULTS, write_reports
    if RESULTS:
        write_reports(RESULTS, Path(directory))


@pytest.fixture(scope="session")
def fixture_specs(app):
    """Every generated fixture, built once per run into tests/fixtures/generated."""
    import fixture_factory
    return {spec.name: spec for spec in fixture_factory.specs()}
