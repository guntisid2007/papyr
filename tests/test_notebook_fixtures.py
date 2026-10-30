"""Every fixture notebook is converted the way the window converts it, while the app wears a dark theme, and the
PDF is judged by what a reader sees and can copy: ink on every page, the text in order, and the figures."""
import base64
import io
import os
import socket
import sys
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from PIL import Image
from pypdf import PdfReader
from PySide6.QtGui import QColor, QPalette

from converter import ImageLoadError, PageSize, PdfSettings, convert_individual
from converter.notebook import render_notebook
from utils.errors import friendly_error

pytestmark = pytest.mark.usefixtures("app")
NOTEBOOKS = Path(__file__).parent / "fixtures" / "notebooks"
A4 = PdfSettings(PageSize.A4, 10)


@pytest.fixture(autouse=True)
def dark_theme(app):
    """The palette macOS gives Papyr in dark mode: near-white text. It once turned every notebook page blank."""
    light = app.palette()
    dark = QPalette(light)
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.Link):
        dark.setColor(role, QColor(255, 255, 255, 216))
    dark.setColor(QPalette.ColorRole.Window, QColor("#1e1e1e"))
    app.setPalette(dark)
    yield
    app.setPalette(light)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Any attempt to reach the network fails the test that made it."""
    def refuse(*args, **kwargs):
        raise AssertionError(f"notebook conversion tried to use the network: {args}")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def render(name: str) -> bytes:
    return render_notebook(NOTEBOOKS / f"{name}.ipynb", A4)


def page_texts(pdf: bytes) -> list[str]:
    return [" ".join(page.extract_text().split()) for page in PdfReader(io.BytesIO(pdf)).pages]


def darkest_ink(page) -> int:
    return page.render(scale=1).to_pil().convert("L").getextrema()[0]


def images_per_page(pdf: bytes) -> list[int]:
    return [sum(obj.type == pdfium.raw.FPDF_PAGEOBJ_IMAGE for obj in page.get_objects())
            for page in pdfium.PdfDocument(pdf)]


@pytest.mark.parametrize("name", ["markdown-only", "code-only", "mixed", "printed-output", "plots-and-images",
                                  "tables", "math", "long", "never-run", "external-references"])
def test_every_page_has_visible_ink(name):
    for number, page in enumerate(pdfium.PdfDocument(render(name)), start=1):
        assert darkest_ink(page) < 100, f"{name} page {number} is blank"


def test_markdown_headings_lists_links_and_tables_are_readable_in_order():
    [text] = page_texts(render("markdown-only"))
    order = ["Field Notes", "bold", "italic", "link", "Shopping list", "apples", "rye", "first step",
             "Instrument", "Thermometer", "-40 to 120", "Barometer", "Quoted remark.", "print('shown, not run')"]
    positions = [text.find(part) for part in order]
    assert -1 not in positions, dict(zip(order, positions))
    assert positions == sorted(positions)


def text_lines(page) -> dict[str, float]:
    """Each line of drawn text, spaces removed, mapped to the x where it starts."""
    text_page = page.get_textpage()
    rows: dict[int, list[tuple[float, str]]] = {}
    for index in range(text_page.count_chars()):
        char = text_page.get_text_range(index, 1)
        if char.strip():
            left, bottom, _, _ = text_page.get_charbox(index, loose=True)
            rows.setdefault(round(bottom), []).append((left, char))
    return {"".join(c for _, c in sorted(row)): min(x for x, _ in row) for row in rows.values()}


def test_code_keeps_its_indentation_and_wraps_long_lines_inside_the_page():
    page = pdfium.PdfDocument(render("code-only"))[0]
    lines = text_lines(page)
    starts = {key: next(x for line, x in lines.items() if line.startswith(key))
              for key in ("deffibonacci", "a,b=0,1", "a,b=b,a+b", "classGreeter", "defhello", "return'tabbed")}
    indent = starts["a,b=0,1"] - starts["deffibonacci"]
    assert indent > 10
    assert starts["a,b=b,a+b"] - starts["deffibonacci"] == pytest.approx(2 * indent, abs=1)
    assert starts["defhello"] - starts["classGreeter"] == pytest.approx(indent, abs=1)  # a tab is four spaces
    assert starts["return'tabbed"] - starts["classGreeter"] == pytest.approx(2 * indent, abs=1)
    text_page = page.get_textpage()
    rightmost = max(text_page.get_charbox(i)[2] for i in range(text_page.count_chars()))
    assert rightmost <= page.get_width() - 10 * 72 / 25.4 + 1
    assert sum(line.startswith("wrap") for line in lines) >= 2  # the long string wrapped onto more lines


def test_code_is_syntax_highlighted():
    page = pdfium.PdfDocument(render("code-only"))[0]
    colors = set()
    for obj in page.get_objects():
        if obj.type == pdfium.raw.FPDF_PAGEOBJ_TEXT:
            r, g, b, _ = (pdfium.raw.c_uint() for _ in range(4))
            pdfium.raw.FPDFPageObj_GetFillColor(obj.raw, r, g, b, _)
            colors.add((r.value, g.value, b.value))
    assert len(colors) >= 4  # keywords, names, strings, comments, and numbers are told apart


def test_printed_text_errors_and_results_appear_after_their_code():
    [text] = page_texts(render("printed-output"))
    assert "line 0 line 1 line 2" in text
    assert "warning!" in text
    compact = text.replace(" ", "")
    assert "ZeroDivisionError:divisionbyzero" in compact and "[0;31m" not in text
    assert compact.index("{'answer':42}") > compact.index("ZeroDivisionError")


def test_png_jpeg_and_svg_figures_are_drawn_and_unrenderable_outputs_are_named():
    pdf = render("plots-and-images")
    assert sum(images_per_page(pdf)) == 4  # PNG, JPEG, SVG, and the static PNG behind the JavaScript plot
    text = " ".join(page_texts(pdf))
    assert "Output not shown (application/vnd.jupyter.widget-view+json)" in text
    assert "<Figure size" not in text and "Plotly.newPlot" not in text


def test_figures_fit_the_text_area():
    page = pdfium.PdfDocument(render("plots-and-images"))[0]
    margin = 10 * 72 / 25.4
    for obj in page.get_objects():
        if obj.type == pdfium.raw.FPDF_PAGEOBJ_IMAGE:
            left, bottom, right, top = obj.get_bounds()
            assert left >= margin - 1 and right <= page.get_width() - margin + 1
            assert bottom >= margin - 1 and top <= page.get_height() - margin + 1


def test_dataframe_and_markdown_tables_keep_their_cells():
    [text] = page_texts(render("tables"))
    assert "Name Score Ada 98 Grace 95" in text
    assert "planet moons 0 Earth 1 1 Mars 2" in text
    assert "0 Earth 1\n1 Mars 2" not in text  # the HTML table wins over its plain-text twin


def test_math_is_typeset_and_dollars_outside_math_stay_text():
    pdf = render("math")
    [text] = page_texts(pdf)
    assert "costs $5 without being math" in text
    assert "price = $3" in text
    assert "mc^2" not in text and "\\int" not in text and "\\begin" not in text
    assert sum(images_per_page(pdf)) == 4  # inline, display, the equation environment, and the LaTeX output


def test_latex_that_cannot_be_typeset_is_shown_as_source(tmp_path):
    from test_notebook import markdown, write_notebook
    source = write_notebook(tmp_path / "bad.ipynb", markdown("Before $\\frac{1}{$ after"))
    [text] = page_texts(render_notebook(source, A4))
    assert "Before" in text and "after" in text


def test_long_notebook_flows_over_several_full_pages_in_order():
    pdf = render("long")
    texts = page_texts(pdf)
    assert len(texts) >= 5
    assert "Section 1 " in texts[0] and "Section 80" in texts[-1]
    sections = [int(word) for page in texts for word in page.split("Section ")[1:] for word in [word.split()[0]]]
    assert sections == list(range(1, 81))
    assert all(len(page) > 500 for page in texts[:-1])  # no near-empty pages before the last


def test_no_cell_is_ever_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    report = convert_individual([NOTEBOOKS / "never-run.ipynb"], tmp_path, A4)
    assert not report.failures
    assert not (tmp_path / "PAPYR_RAN_THIS_CELL").exists()
    assert not (NOTEBOOKS / "PAPYR_RAN_THIS_CELL").exists()
    assert not any(name.startswith(("ipykernel", "jupyter_client", "nbclient")) for name in sys.modules)


def test_only_images_inside_the_notebook_folder_are_read():
    pdf = render("external-references")
    bitmaps = [obj.get_bitmap().to_pil().convert("RGBA") for page in pdfium.PdfDocument(pdf)
               for obj in page.get_objects() if obj.type == pdfium.raw.FPDF_PAGEOBJ_IMAGE]
    colors = [bitmap.getpixel((bitmap.width // 2, bitmap.height // 2))[:3] for bitmap in bitmaps
              if bitmap.getpixel((bitmap.width // 2, bitmap.height // 2))[3]]
    def near(color, target):
        return all(abs(a - b) <= 3 for a, b in zip(color, target))
    assert not any(near(color, (255, 0, 255)) for color in colors)  # ../outside.png, from markdown, HTML, or SVG
    assert sum(near(color, (220, 20, 60)) for color in colors) == 2  # inside.png, from markdown and from HTML


@pytest.mark.parametrize("name, message, friendly", [
    ("empty", "no cells", "This notebook is empty."),
    ("corrupted", "Not a valid notebook", "This isn't a valid Jupyter notebook."),
])
def test_empty_and_corrupted_notebooks_fail_clearly_and_leave_no_file(tmp_path, name, message, friendly):
    with pytest.raises(ImageLoadError, match=message):
        render(name)
    report = convert_individual([NOTEBOOKS / f"{name}.ipynb"], tmp_path, A4)
    [(path, reason)] = report.failures
    assert path.name == f"{name}.ipynb" and friendly_error(reason) == friendly
    assert report.outputs == [] and os.listdir(tmp_path) == []


def red_pixels(pdf: bytes) -> int:
    image = pdfium.PdfDocument(pdf)[0].render(scale=1).to_pil().convert("RGB")
    red, green, _ = (band.tobytes() for band in image.split())
    return sum(1 for r, g in zip(red, green) if r > 200 and g < 60)


SVG_NS = 'xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"'


def svg_with(reference: str) -> str:
    return f'<svg {SVG_NS} width="80" height="80"><image {reference} width="80" height="80"/></svg>'


def data_url(mime: str, text: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(text.encode()).decode()}"


@pytest.mark.parametrize("attack", [
    "absolute path", "file url", "svg in data url", "svg labeled png", "doctype default href",
    "svg nested in svg", "css processing instruction"])
def test_no_trick_reads_an_image_outside_the_notebook_folder(tmp_path, attack):
    from test_notebook import code, display, markdown, write_notebook
    secret = tmp_path / "secret.png"
    Image.new("RGB", (80, 80), (255, 0, 0)).save(secret)
    (tmp_path / "evil.css").write_text("rect { fill: #ff0000 }")
    folder = tmp_path / "notebook"
    folder.mkdir()
    href = f'xlink:href="{secret}"'
    cell = {
        "absolute path": markdown(f"![x]({secret})"),
        "file url": markdown(f"![x](file://{secret})"),
        "svg in data url": markdown(f"![x]({data_url('image/svg+xml', svg_with(href))})"),
        "svg labeled png": code("x", display(image_png=base64.b64encode(svg_with(href).encode()).decode())),
        "doctype default href": code("x", display(**{"image/svg+xml": (
            f'<!DOCTYPE svg [<!ATTLIST image xlink:href CDATA "{secret}">]>'
            f'<svg {SVG_NS} width="40" height="40"><image width="40" height="40"/></svg>')})),
        "svg nested in svg": code("x", display(**{"image/svg+xml": (
            f'<svg {SVG_NS} width="40" height="40"><image width="40" height="40" '
            f'xlink:href="{data_url("image/svg+xml", svg_with(href))}"/></svg>')})),
        "css processing instruction": code("x", display(**{"image/svg+xml": (
            f'<?xml-stylesheet type="text/css"href="{tmp_path / "evil.css"}"?>'
            f'<svg {SVG_NS} width="40" height="40"><rect width="40" height="40" fill="blue"/></svg>')})),
    }[attack]
    source = write_notebook(folder / "nb.ipynb", markdown("Visible text"), cell)
    assert red_pixels(render_notebook(source, A4)) == 0


@pytest.mark.parametrize("markdown_text, kept", [
    ("    $x$ is code\n\nText $y$", "$x$ is code"),
    ("```\n$x$ in a fence\n````\n\nText $y$", "$x$ in a fence"),
    ("Use $HOME and $PATH.", "Use $HOME and $PATH."),
])
def test_dollars_in_code_and_shell_variables_stay_literal(tmp_path, markdown_text, kept):
    from test_notebook import markdown, write_notebook
    [text] = page_texts(render_notebook(write_notebook(tmp_path / "nb.ipynb", markdown(markdown_text)), A4))
    assert kept in text and "math:" not in text and "$y$" not in text


def test_images_in_a_table_fit_their_cells_and_wide_tables_fit_the_page(tmp_path):
    from test_notebook import code, display, png_b64, write_notebook
    picture = f'<img src="data:image/png;base64,{png_b64((2000, 1000), "blue")}">'
    html = f'<table><tr><td>{picture}</td><td>{picture}</td></tr></table>' \
           '<table width="2000"><tr><td>LEFT</td><td>RIGHT</td></tr></table>'
    pdf = render_notebook(write_notebook(tmp_path / "nb.ipynb", code("df", display(text_html=html))), A4)
    page = pdfium.PdfDocument(pdf)[0]
    margin = 10 * 72 / 25.4
    boxes = [obj.get_bounds() for obj in page.get_objects() if obj.type == pdfium.raw.FPDF_PAGEOBJ_IMAGE]
    assert len(boxes) == 2 and all(right <= page.get_width() - margin + 1 for _, _, right, _ in boxes)
    assert "LEFT RIGHT" in page_texts(pdf)[0]


def test_a_notebook_that_draws_nothing_is_reported_empty(tmp_path):
    from test_notebook import markdown, write_notebook
    source = write_notebook(tmp_path / "nb.ipynb", markdown("<!-- nothing visible -->"))
    report = convert_individual([source], tmp_path / "out", A4)
    assert report.outputs == [] and friendly_error(report.failures[0][1]) == "This notebook is empty."


def test_math_typesets_correctly_from_many_threads_at_once(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from test_notebook import markdown, write_notebook
    formulas = ["\\sum_{n=1}^{100} \\frac{n^2}{n+1}", "\\int_0^1 x^2 dx", "\\alpha\\beta\\gamma",
                "\\begin{bmatrix}1&2\\\\3&4\\end{bmatrix}"] * 3
    paths = [write_notebook(tmp_path / f"nb{n}.ipynb", markdown(f"$${latex}$$")) for n, latex in enumerate(formulas)]
    switch = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        with ThreadPoolExecutor(6) as pool:
            counts = list(pool.map(lambda path: sum(images_per_page(render_notebook(path, A4))), paths))
    finally:
        sys.setswitchinterval(switch)
    assert counts == [1] * len(formulas)
