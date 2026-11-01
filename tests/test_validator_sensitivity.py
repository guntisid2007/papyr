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


def blacked_out_lines(original):
    """Each line of body text becomes one solid black bar: the ink is all still there, the words are not."""
    def save(image, stream, fmt, quality):
        from validators import _dark
        wrong = image.convert("RGB")
        mask = _dark(wrong, 100).load()
        top = round(wrong.height * 0.17)
        for y in range(top, wrong.height):
            xs = [x for x in range(wrong.width) if mask[x, y]]
            if xs:
                wrong.paste("black", (min(xs), y, max(xs) + 1, y + 1))
        original(wrong, stream, fmt, quality)
    return save


@pytest.mark.parametrize("target", ["JPEG", "PNG", "GIF_SEPARATE"])
def test_the_matrix_check_catches_text_blacked_out(target, fixture_specs, monkeypatch, tmp_path):
    _planted(monkeypatch, convert, "save_image", blacked_out_lines)
    result = run_pair(fixture_specs["pdf-twelve-pages"], TARGET[target], tmp_path / "out")
    RESULTS.remove(result)
    assert result.validation == "FAILED", result.actual


@pytest.mark.parametrize("target", ["PNG", "GIF", "PDF"])
def test_the_matrix_check_catches_lost_notebook_output_text(target, fixture_specs, monkeypatch, tmp_path):
    """Saved stdout dropped from the layout: the figures and their order survive, the printed results do not."""
    original = notebook._Builder.mono_text

    def mono_text(self, text, color=None):
        original(self, "" if "SAVED_OUTPUT" in text else text, color)
    monkeypatch.setattr(notebook._Builder, "mono_text", mono_text)
    result = run_pair(fixture_specs["notebook-short"], TARGET[target], tmp_path / "out")
    RESULTS.remove(result)
    assert result.validation == "FAILED", result.actual


def _one_line_page_pdf(path, gray: float):
    """Two pages: a full page of text, then a page with one short line drawn in the given gray (0 black, 1 white)."""
    from pdf_samples import _pdf
    full = " ".join(f"BT /F1 12 Tf 20 {760 - 14 * i} Td (LINE_{i:03d} with several words of text) Tj ET"
                    for i in range(50))
    last = f"{gray} g BT /F1 12 Tf 20 760 Td (LONELY_LAST_LINE) Tj ET"
    return _pdf(path, [(full, (612, 792)), (last, (612, 792))])


@pytest.mark.parametrize("gray, flagged", [(0, False), (1, True)])
def test_a_one_line_last_page_passes_only_when_its_text_is_visible(tmp_path, gray, flagged):
    """Windows lays the matrix notebook out with its last line alone on a page, which has little ink. That page is
    fine when the line is visibly dark, and still caught when the text is invisible."""
    from conversion_matrix import _check_notebook_pdf
    from validators import pdf_facts
    file = _one_line_page_pdf(tmp_path / "doc.pdf", gray)
    problems = []

    class Spec:
        extra = {"sections": 0}
        pages = ()

        @staticmethod
        def path():
            return file
    import conversion_matrix
    original = conversion_matrix._check_notebook_text, conversion_matrix._check_section_order
    conversion_matrix._check_notebook_text = lambda *a, **k: None
    conversion_matrix._check_section_order = lambda *a, **k: None
    try:
        _check_notebook_pdf(Spec, file, pdf_facts(file), problems)
    finally:
        conversion_matrix._check_notebook_text, conversion_matrix._check_section_order = original
    blank = [p for p in problems if "is blank" in p]
    assert bool(blank) is flagged, problems


def test_a_frame_with_its_text_gone_is_still_caught_when_it_has_no_ink_at_all():
    """With no dark ink in the output, precision has nothing to judge, so recall must catch the lost text."""
    from PIL import ImageDraw

    from validators import ink_match
    reference = Image.new("RGB", (400, 200), "white")
    ImageDraw.Draw(reference).text((20, 80), "SOME TEXT THAT MUST SURVIVE", fill="black")
    recall, precision = ink_match(Image.new("RGB", (400, 200), "white"), reference)
    assert recall == 0.0 and precision == 1.0
