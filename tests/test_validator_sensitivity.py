"""The matrix checks must fail on broken output. Each case plants one real-world defect in the engine and runs the
same check the matrix runs; a check that still passes would let that defect ship."""
import pytest
from PIL import Image
from PySide6.QtGui import QColor

import converter.animation as animation
import converter.convert as convert
import converter.notebook as notebook
from conversion_matrix import RESULTS, run_pair, targets

pytestmark = pytest.mark.usefixtures("app")
TARGET = {t.key: t for t in targets()}


def _planted(monkeypatch, module, name, wrap):
    original = getattr(module, name)
    monkeypatch.setattr(module, name, wrap(original))


def wrong_container(original):
    def save(image, stream, fmt, quality):
        image.convert("RGB").save(stream, "PNG")
    return save


def upside_down(original):
    def save(image, stream, fmt, quality):
        original(image.transpose(Image.Transpose.ROTATE_180), stream, fmt, quality)
    return save


def mirrored(original):
    def save(image, stream, fmt, quality):
        original(image.transpose(Image.Transpose.FLIP_LEFT_RIGHT), stream, fmt, quality)
    return save


def drops_alpha(original):
    def save(image, stream, fmt, quality):
        original(image.convert("RGB"), stream, fmt, quality)
    return save


def blank(original):
    def save(image, stream, fmt, quality):
        original(Image.new(image.mode, image.size, "white"), stream, fmt, quality)
    return save


def loses_last_page(original):
    def pages(*args, **kwargs):
        rendered = list(original(*args, **kwargs))
        yield from rendered[:-1] or rendered
    return pages


def reversed_pages(original):
    def pages(*args, **kwargs):
        yield from reversed(list(original(*args, **kwargs)))
    return pages


def heavy_jpeg(original):
    def save(image, stream, fmt, quality):
        original(image, stream, fmt, 5)
    return save


PLANTED = [
    ("PNG-landscape saved as PNG bytes in a .jpg", convert, "save_image", wrong_container, "png-landscape", "JPEG"),
    ("picture turned upside down", convert, "save_image", upside_down, "png-portrait", "PNG"),
    ("picture mirrored", convert, "save_image", mirrored, "heic-landscape", "WEBP"),
    ("transparency dropped", convert, "save_image", drops_alpha, "png-landscape", "PNG"),
    ("blank picture", convert, "save_image", blank, "jpeg-landscape", "AVIF"),
    ("quality ignored, JPEG at 5", convert, "save_image", heavy_jpeg, "png-hires", "JPEG"),
    ("last PDF page lost from images", convert, "iter_pages", loses_last_page, "pdf-mixed-content", "PNG"),
    ("PDF pages out of order in images", convert, "iter_pages", reversed_pages, "pdf-twelve-pages", "JPEG"),
    ("animation frames out of order", animation, "pdf_pages", reversed_pages, "pdf-twelve-pages", "GIF"),
    ("animation loses a frame", animation, "pdf_pages", loses_last_page, "pdf-twelve-pages", "GIF"),
]


@pytest.mark.parametrize("about, module, name, wrap, fixture, target", PLANTED, ids=[p[0] for p in PLANTED])
def test_the_matrix_check_catches(about, module, name, wrap, fixture, target, fixture_specs, monkeypatch, tmp_path):
    _planted(monkeypatch, module, name, wrap)
    result = run_pair(fixture_specs[fixture], TARGET[target], tmp_path / "out")
    RESULTS.remove(result)
    assert result.validation == "FAILED", f"{about} went unnoticed: {result.actual}"


def test_the_matrix_check_catches_dark_mode_blank_notebook_text(fixture_specs, monkeypatch, tmp_path):
    """The regression Papyr shipped once: notebook text drawn in the theme's white, so PDF pages looked blank."""
    monkeypatch.setattr(notebook, "_INK", QColor("white"))
    result = run_pair(fixture_specs["notebook-matrix"], TARGET["PDF"], tmp_path / "out")
    RESULTS.remove(result)
    assert result.validation == "FAILED" and "not visible" in result.failure, result.failure


def test_the_matrix_check_catches_wrong_frame_timing(fixture_specs, monkeypatch, tmp_path):
    original = animation.GifWriter.__init__

    def slow(self, stream, settings):
        original(self, stream, type(settings)(frame_ms=500, plays=1, resolution=settings.resolution))
    monkeypatch.setattr(animation.GifWriter, "__init__", slow)
    monkeypatch.setattr(convert.GifWriter, "__init__", slow)
    result = run_pair(fixture_specs["pdf-twelve-pages"], TARGET["GIF"], tmp_path / "out")
    RESULTS.remove(result)
    assert "delays" in result.failure and "loop" in result.failure, result.failure


def erased_body(original):
    def save(image, stream, fmt, quality):
        wrong = image.copy()
        wrong.paste("white", (0, round(wrong.height * 0.12), wrong.width, wrong.height))
        original(wrong, stream, fmt, quality)
    return save


def test_the_matrix_check_catches_pdf_pages_with_their_content_erased(fixture_specs, monkeypatch, tmp_path):
    _planted(monkeypatch, convert, "save_image", erased_body)
    result = run_pair(fixture_specs["pdf-mixed-content"], TARGET["PNG"], tmp_path / "out")
    RESULTS.remove(result)
    assert result.validation == "FAILED", result.actual


def test_the_matrix_check_catches_animation_frames_with_their_content_erased(fixture_specs, monkeypatch, tmp_path):
    original = animation.GifWriter.add

    def add(self, frame):
        wrong = frame.copy()
        wrong.paste("white", (0, round(wrong.height * 0.25), wrong.width, wrong.height))
        original(self, wrong)
    monkeypatch.setattr(animation.GifWriter, "add", add)
    result = run_pair(fixture_specs["pdf-mixed-content"], TARGET["GIF"], tmp_path / "out")
    RESULTS.remove(result)
    assert result.validation == "FAILED", result.actual


@pytest.mark.parametrize("fixture, target", [("pdf-single-text", "JPEG"), ("pdf-single-text", "GIF"),
                                             ("pdf-twelve-pages", "PNG"), ("pdf-twelve-pages", "GIF_SEPARATE")])
def test_the_matrix_check_catches_lost_text_on_sparse_pages(fixture, target, fixture_specs, monkeypatch, tmp_path):
    """One line of text is about 1% of a page, too little to move an average, and the check must still catch its loss."""
    _planted(monkeypatch, convert, "save_image", erased_body)
    original = animation.GifWriter.add

    def add(self, frame):
        wrong = frame.copy()
        wrong.paste("white", (0, round(wrong.height * 0.12), wrong.width, wrong.height))
        original(self, wrong)
    monkeypatch.setattr(animation.GifWriter, "add", add)
    result = run_pair(fixture_specs[fixture], TARGET[target], tmp_path / "out")
    RESULTS.remove(result)
    assert result.validation == "FAILED", result.actual
