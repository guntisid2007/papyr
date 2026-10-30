import base64
import io
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from PIL import Image
from pypdf import PdfReader
from PySide6.QtCore import QLocale

from converter import (ImageLoadError, ImageSettings, OutputFormat, PageSize, PdfSettings, convert_images,
                       convert_individual, convert_merged, iter_pages)
from converter.images import make_thumbnail
from converter.layout import MM_TO_PT
from converter.notebook import render_notebook
from pdf_samples import text_pdf

pytestmark = pytest.mark.usefixtures("app")
A4 = PdfSettings(PageSize.A4, 10)


def write_notebook(path: Path, *cells, nbformat=4) -> Path:
    path.write_text(json.dumps({"nbformat": nbformat, "nbformat_minor": 5, "metadata": {}, "cells": list(cells)}))
    return path


def markdown(source, **extra) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": source, **extra}


def code(source, *outputs, count=1) -> dict:
    return {"cell_type": "code", "execution_count": count, "metadata": {}, "source": source, "outputs": list(outputs)}


def stream(text) -> dict:
    return {"output_type": "stream", "name": "stdout", "text": text}


def png_b64(size, color) -> str:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, "PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def display(**data) -> dict:
    return {"output_type": "display_data", "metadata": {}, "data": {k.replace("_", "/"): v for k, v in data.items()}}


def words(page) -> str:
    return " ".join(page.extract_text().split())


def pdf_text(pdf: Path | bytes) -> list[str]:
    reader = PdfReader(io.BytesIO(pdf) if isinstance(pdf, bytes) else pdf)
    return [words(page) for page in reader.pages]


def image_boxes(pdf: bytes) -> list[tuple[float, float]]:
    """Width and height in points of every image drawn on the first page."""
    page = pdfium.PdfDocument(pdf)[0]
    boxes = []
    for obj in page.get_objects():
        if obj.type == pdfium.raw.FPDF_PAGEOBJ_IMAGE:
            left, bottom, right, top = obj.get_bounds()
            boxes.append((right - left, top - bottom))
    return boxes


def test_markdown_code_and_stream_output_become_searchable_text(tmp_path):
    source = write_notebook(tmp_path / "nb.ipynb",
                            markdown(["# Quarterly Results\n", "\n", "Some **bold** prose."]),
                            code(["total = sum(range(10))\n", "print(total)"], stream(["45\n"])))
    report = convert_individual([source], tmp_path / "out", A4)
    assert not report.failures
    [text] = pdf_text(report.outputs[0])
    assert "Quarterly Results" in text
    assert "Some bold prose." in text
    code_text = text.replace(" ", "")  # highlighted tokens are separate runs, and pypdf spaces them apart
    assert "total=sum(range(10))print(total)" in code_text
    assert "45" in code_text.split("print(total)")[1]


def test_png_output_is_drawn_as_an_image(tmp_path):
    source = write_notebook(tmp_path / "plot.ipynb",
                            code("plot()", display(image_png=png_b64((320, 200), "blue"), text_plain="<Figure>")))
    page = PdfReader(io.BytesIO(render_notebook(source, A4))).pages[0]
    [image] = page.images
    assert image.image.size == (320, 200)
    red, green, blue = image.image.convert("RGB").getpixel((160, 100))
    assert blue > 200 and red < 50 and green < 50
    assert "<Figure>" not in words(page)


def test_images_keep_their_size_but_shrink_to_fit_the_text_width(tmp_path):
    source = write_notebook(tmp_path / "sizes.ipynb",
                            code("small", display(image_png=png_b64((192, 96), "red"))),
                            code("wide", display(image_png=png_b64((4000, 400), "green"))))
    text_width = 595.2756 - 2 * 10 * MM_TO_PT
    small, wide = image_boxes(render_notebook(source, A4))
    assert small == pytest.approx((144, 72), abs=1)  # one image pixel per CSS pixel, 96 per inch
    assert wide == pytest.approx((text_width, text_width / 10), abs=1.5)


def test_markdown_attachments_and_local_images_are_shown(tmp_path):
    Image.new("RGB", (60, 30), "green").save(tmp_path / "local.png")
    source = write_notebook(tmp_path / "pictures.ipynb", markdown(
        "![a](attachment:pasted.png) ![b](local.png) ![c](https://example.com/remote.png)",
        attachments={"pasted.png": {"image/png": png_b64((40, 20), "red")}}))
    boxes = {(round(w), round(h)) for w, h in image_boxes(render_notebook(source, A4))}
    assert {(30, 15), (45, 22)} <= boxes  # the remote image is never fetched; at most a broken-image icon shows


def test_long_notebook_spans_several_pages(tmp_path):
    cells = [code(f"value_{n} = {n}", stream(f"line {n}\n"), count=n) for n in range(1, 121)]
    text = pdf_text(render_notebook(write_notebook(tmp_path / "long.ipynb", *cells), A4))
    assert len(text) > 2
    assert "value_1 = 1" in text[0]
    assert "value_120 = 120" in text[-1]


def test_error_traceback_is_shown_without_ansi_codes(tmp_path):
    error = {"output_type": "error", "ename": "ZeroDivisionError", "evalue": "division by zero", "traceback": [
        "\x1b[0;31m-----------\x1b[0m",
        "Cell \x1b[0;32mIn[1], line 1\x1b[0m\n\x1b[0;32m----> 1\x1b[0m \x1b[38;5;241m1\x1b[39m\x1b[38;5;241m/\x1b[39m0",
        "\x1b[0;31mZeroDivisionError\x1b[0m: division by zero"]}
    [text] = pdf_text(render_notebook(write_notebook(tmp_path / "err.ipynb", code("1/0", error)), A4))
    assert "----> 1 1/0" in text
    assert "ZeroDivisionError: division by zero" in text
    assert "[0;31m" not in text and "\x1b" not in text


def test_html_output_is_rendered_and_plain_text_fallback_skipped(tmp_path):
    table = "<table><tr><th>city</th></tr><tr><td>Tokyo</td></tr></table><script>alert('hidden')</script>"
    source = write_notebook(tmp_path / "df.ipynb", code("df", display(text_html=table, text_plain="PLAINFALLBACK")))
    [text] = pdf_text(render_notebook(source, A4))
    assert "city Tokyo" in text
    assert "PLAINFALLBACK" not in text and "alert" not in text


@pytest.mark.parametrize("content, message", [
    ("{not json", "Not a valid notebook"),
    (json.dumps({"nbformat": 3, "worksheets": []}), "format 4"),
    (json.dumps({"nbformat": 4, "metadata": {}}), "no list of cells"),
    (json.dumps({"nbformat": 4, "cells": [code("", display(image_png="é"))]}), "damaged"),
])
def test_unreadable_notebooks_are_reported_as_failures(tmp_path, content, message):
    bad = tmp_path / "bad.ipynb"
    bad.write_text(content)
    good = write_notebook(tmp_path / "good.ipynb", markdown("fine"))
    report = convert_merged([bad, good], tmp_path / "out.pdf", A4)
    assert report.outputs == [tmp_path / "out.pdf"]
    [(path, reason)] = report.failures
    assert path == bad and message in reason
    with pytest.raises(ImageLoadError, match=message):
        list(iter_pages(bad))


def test_merge_keeps_order_and_page_count_across_notebook_photo_and_pdf(make, tmp_path):
    sources = [text_pdf(tmp_path / "doc.pdf", ["PDFPAGEONE", "PDFPAGETWO"]),
               write_notebook(tmp_path / "nb.ipynb", markdown("NOTEBOOKTEXT")),
               make("photo.jpg", (300, 200))]
    report = convert_merged(sources, tmp_path / "all.pdf", PdfSettings(PageSize.LETTER, 10))
    assert not report.failures
    reader = PdfReader(tmp_path / "all.pdf")
    assert [words(page) for page in reader.pages] == ["PDFPAGEONE", "PDFPAGETWO", "NOTEBOOKTEXT", ""]
    assert len(reader.pages[3].images) == 1
    assert [float(reader.pages[2].mediabox.width), float(reader.pages[2].mediabox.height)] == \
        pytest.approx([612, 792], abs=1)


def test_converting_to_images_writes_one_numbered_image_per_page(tmp_path):
    cells = [code(f"x = {n}", stream(f"{n}\n"), count=n) for n in range(1, 121)]
    source = write_notebook(tmp_path / "report.ipynb", *cells)
    report = convert_images([source], tmp_path / "out", ImageSettings(OutputFormat.PNG, pdf_dpi=72))
    assert not report.failures
    names = [p.name for p in report.outputs]
    assert len(names) > 2
    assert names == [f"report-page-{n}.png" for n in range(1, len(names) + 1)]


@pytest.mark.parametrize("page, size", [(PageSize.A4, (595.3, 841.9)), (PageSize.LETTER, (612, 792))])
def test_page_size_and_margins_are_honored(tmp_path, page, size):
    source = write_notebook(tmp_path / "nb.ipynb", markdown("Margin check"))
    pdf = render_notebook(source, PdfSettings(page, 25))
    mediabox = PdfReader(io.BytesIO(pdf)).pages[0].mediabox
    assert (float(mediabox.width), float(mediabox.height)) == pytest.approx(size, abs=1)
    text_page = pdfium.PdfDocument(pdf)[0].get_textpage()
    left, _, _, top = text_page.get_charbox(0)
    assert left == pytest.approx(25 * MM_TO_PT, abs=2)
    assert size[1] - top == pytest.approx(25 * MM_TO_PT, abs=6)


@pytest.mark.parametrize("locale, size", [("en_US", (612, 792)), ("de_DE", (595.3, 841.9))])
def test_original_page_size_uses_the_local_paper(tmp_path, locale, size):
    source = write_notebook(tmp_path / "nb.ipynb", markdown("paper"))
    previous = QLocale()
    QLocale.setDefault(QLocale(locale))
    try:
        pdf = render_notebook(source, PdfSettings(PageSize.ORIGINAL, 10))
    finally:
        QLocale.setDefault(previous)
    mediabox = PdfReader(io.BytesIO(pdf)).pages[0].mediabox
    assert (float(mediabox.width), float(mediabox.height)) == pytest.approx(size, abs=1)


def test_notebooks_render_on_worker_threads(tmp_path):
    paths = [write_notebook(tmp_path / f"nb{n}.ipynb", markdown(f"# Thread {n}"),
                            code("x", display(image_png=png_b64((50, 50), "red")))) for n in range(6)]
    with ThreadPoolExecutor(4) as pool:
        texts = list(pool.map(lambda p: pdf_text(render_notebook(p, A4)), paths))
    assert texts == [[f"Thread {n} [1] x"] for n in range(6)]


def test_thumbnail_shows_the_first_page(tmp_path):
    source = write_notebook(tmp_path / "nb.ipynb", markdown("# Title"),
                            code("plot()", display(image_png=png_b64((600, 300), "black"))))
    thumb = make_thumbnail(source, 64)
    assert thumb.size == (64, 64) and thumb.mode == "RGBA"
    page = [thumb.getpixel((x, y)) for x in range(64) for y in range(64) if thumb.getpixel((x, y))[3] == 255]
    assert page and max(page) == (255, 255, 255, 255)
    assert min(page)[:3] == (0, 0, 0)


def test_rendering_without_a_qt_application_is_a_clear_error(tmp_path):
    source = write_notebook(tmp_path / "nb.ipynb", markdown("hi"))
    script = ("import sys; from pathlib import Path; from converter import ImageLoadError, PdfSettings\n"
              "from converter.notebook import render_notebook\n"
              "try: render_notebook(Path(sys.argv[1]), PdfSettings())\n"
              "except ImageLoadError as exc: print('refused:', exc)\n")
    src = Path(__file__).parents[1] / "src"
    result = subprocess.run([sys.executable, "-c", script, str(source)], capture_output=True, text=True,
                            env={**os.environ, "PYTHONPATH": str(src)}, timeout=60)
    assert result.stdout.startswith("refused:"), result.stderr


def test_each_cell_shows_its_own_attachment_when_names_repeat(tmp_path):
    cells = [markdown("![plot](attachment:image.png)",
                      attachments={"image.png": {"image/png": png_b64((40, 40), color)}})
             for color in ("red", "blue")]
    pdf = render_notebook(write_notebook(tmp_path / "nb.ipynb", *cells), A4)
    page = pdfium.PdfDocument(pdf)[0]
    colors = sorted(obj.get_bitmap().to_pil().convert("RGB").getpixel((0, 0))
                    for obj in page.get_objects() if obj.type == pdfium.raw.FPDF_PAGEOBJ_IMAGE)
    assert len(colors) == 2 and colors[0][2] > 200 and colors[1][0] > 200


def darkest_ink(pdf: bytes, page: int = 0) -> int:
    """The darkest gray level drawn on a page, so text that only exists for search but is invisible fails."""
    return pdfium.PdfDocument(pdf)[page].render(scale=1).to_pil().convert("L").getextrema()[0]


def test_text_stays_dark_on_white_when_the_app_uses_a_dark_theme(app, tmp_path):
    from PySide6.QtGui import QColor, QPalette
    source = write_notebook(tmp_path / "nb.ipynb", markdown("# Heading\n\nProse with a [link](https://example.com)."),
                            code("print('hi')", stream("hi\n")))
    light = app.palette()
    dark = QPalette(light)
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.Link):
        dark.setColor(role, QColor(255, 255, 255, 216))
    app.setPalette(dark)
    try:
        pdf = render_notebook(source, A4)
    finally:
        app.setPalette(light)
    assert darkest_ink(pdf) < 80
