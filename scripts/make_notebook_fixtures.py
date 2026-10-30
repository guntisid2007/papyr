"""Regenerate tests/fixtures/notebooks: one small notebook per kind of content Papyr must lay out.

    python scripts/make_notebook_fixtures.py

Each notebook holds saved outputs only, as Jupyter writes them. The figures are drawn here with Pillow, so the
fixtures need neither Jupyter nor matplotlib to rebuild.
"""
import base64
import io
import json
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "notebooks"
METADATA = {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"}}


def markdown(source: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": source.splitlines(keepends=True)}


def code(source: str, *outputs: dict, count: int | None = 1) -> dict:
    return {"cell_type": "code", "execution_count": count, "metadata": {},
            "source": source.splitlines(keepends=True), "outputs": list(outputs)}


def stream(text: str, name: str = "stdout") -> dict:
    return {"output_type": "stream", "name": name, "text": text.splitlines(keepends=True)}


def result(count: int = 1, **data: str) -> dict:
    return {"output_type": "execute_result", "execution_count": count, "metadata": {},
            "data": {mime.replace("_", "/", 1).replace("_", "+"): value for mime, value in data.items()}}


def display(**data: str) -> dict:
    return {"output_type": "display_data", "metadata": {},
            "data": {mime.replace("_", "/", 1).replace("_", "+"): value for mime, value in data.items()}}


def plot(fmt: str, size=(480, 320)) -> str:
    """A line chart with axes, the shape of a saved matplotlib figure."""
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    width, height = size
    draw.line([(40, 20), (40, height - 30), (width - 20, height - 30)], fill="black", width=2)
    draw.line([(40 + x, height - 30 - int((x / (width - 60)) ** 2 * (height - 60))) for x in range(0, width - 60, 4)],
              fill=(31, 119, 180), width=3)
    buffer = io.BytesIO()
    image.save(buffer, fmt)
    return base64.b64encode(buffer.getvalue()).decode()


def notebook(*cells: dict) -> dict:
    return {"nbformat": 4, "nbformat_minor": 5, "metadata": METADATA, "cells": list(cells)}


DATAFRAME = ("<div><table border=\"1\" class=\"dataframe\"><thead><tr><th></th><th>planet</th><th>moons</th></tr>"
             "</thead><tbody><tr><th>0</th><td>Earth</td><td>1</td></tr><tr><th>1</th><td>Mars</td><td>2</td></tr>"
             "</tbody></table></div>")
SVG = ("<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"200\" height=\"100\" viewBox=\"0 0 200 100\">"
       "<rect x=\"10\" y=\"10\" width=\"180\" height=\"80\" fill=\"#2ca02c\"/></svg>")

FIXTURES = {
    "markdown-only": notebook(
        markdown("# Field Notes\n\nA paragraph with **bold**, *italic*, and a [link](https://jupyter.org).\n"),
        markdown("## Shopping list\n\n- apples\n- bread\n  - rye\n\n1. first step\n2. second step\n"),
        markdown("| Instrument | Range |\n|---|---|\n| Thermometer | -40 to 120 |\n| Barometer | 870 to 1085 |\n"),
        markdown("> Quoted remark.\n\n```python\nprint('shown, not run')\n```\n")),
    "code-only": notebook(
        code("def fibonacci(n):\n    a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a\n",
             count=1),
        code("squares = [n * n for n in range(10)]  # a comment\n", count=2),
        code("class Greeter:\n\tdef hello(self):\n\t\treturn 'tabbed indentation'\n", count=3),
        code("very_long_line = '" + "wrap " * 60 + "'\n", count=4)),
    "mixed": notebook(
        markdown("# Mixed Report\n\nSome context before the code."),
        code("total = sum(range(10))\nprint(total)", stream("45\n")),
        markdown("Text between cells."),
        code("total * 2", result(2, text_plain="90"), count=2)),
    "printed-output": notebook(
        code("for n in range(3):\n    print('line', n)", stream("line 0\nline 1\nline 2\n")),
        code("import sys\nprint('warning!', file=sys.stderr)", stream("warning!\n", "stderr"), count=2),
        code("1 / 0", {"output_type": "error", "ename": "ZeroDivisionError", "evalue": "division by zero",
                       "traceback": ["\u001b[0;31mZeroDivisionError\u001b[0m: division by zero"]}, count=3),
        code("{'answer': 42}", result(4, text_plain="{'answer': 42}"), count=4)),
    "plots-and-images": notebook(
        markdown("# Figures"),
        code("plt.plot(x, y)", display(image_png=plot("PNG"), text_plain="<Figure size 480x320>")),
        code("Image('photo.jpg')", display(image_jpeg=plot("JPEG", (300, 200)), text_plain="<Image>"), count=2),
        code("SVG(drawing)", display(image_svg_xml=SVG, text_plain="<SVG>"), count=3),
        code("fig.show()  # interactive, needs JavaScript",
             display(text_html="<div id='plot'></div><script>Plotly.newPlot('plot')</script>",
                     image_png=plot("PNG", (240, 160)), text_plain="<Plotly figure>"), count=4),
        code("widget", display(**{"application/vnd.jupyter.widget-view+json": {"model_id": "a1"}}), count=5)),
    "tables": notebook(
        markdown("| Name | Score |\n|:--|--:|\n| Ada | 98 |\n| Grace | 95 |\n"),
        code("df", result(1, text_html=DATAFRAME, text_plain="  planet  moons\n0  Earth  1\n1  Mars  2"))),
    "math": notebook(
        markdown("Inline math $E = mc^2$ sits in a sentence, and costs \\$5 without being math."),
        markdown("$$\\int_0^\\infty e^{-x^2}\\,dx = \\frac{\\sqrt{\\pi}}{2}$$"),
        markdown("\\begin{equation}\na^2 + b^2 = c^2\n\\end{equation}"),
        markdown("Code keeps its dollars: `price = $3`."),
        code("Math(r'\\alpha + \\beta')", display(text_latex="$\\displaystyle \\alpha + \\beta$",
                                                   text_plain="<IPython.core.display.Math object>"))),
    "long": notebook(*[cell for n in range(1, 81) for cell in (
        markdown(f"## Section {n}\n\nParagraph {n} explains the step below in a sentence or two of prose."),
        code(f"value_{n} = {n} ** 2\nprint(value_{n})", stream(f"{n * n}\n"), count=n))]),
    "empty": notebook(markdown(""), code("", count=None), markdown("   \n")),
    "never-run": notebook(
        markdown("This notebook would leave a file behind if any cell ran."),
        code("import pathlib\npathlib.Path('PAPYR_RAN_THIS_CELL').write_text('ran')", count=None),
        code("import os\nos.system('touch PAPYR_RAN_THIS_CELL')", count=None)),
    "external-references": notebook(
        markdown("![inside](inside.png) ![outside](../outside.png) ![web](https://example.com/x.png)"),
        code("HTML(...)", display(text_html="<p>html images</p><img src=\"../outside.png\"><img src=\"inside.png\">")),
        code("SVG(...)", display(image_svg_xml=(
            "<svg xmlns=\"http://www.w3.org/2000/svg\" xmlns:xlink=\"http://www.w3.org/1999/xlink\" width=\"60\" "
            "height=\"60\"><image xlink:href=\"../outside.png\" width=\"60\" height=\"60\"/></svg>"))))
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, content in FIXTURES.items():
        (OUT / f"{name}.ipynb").write_text(json.dumps(content, indent=1) + "\n")
    (OUT / "corrupted.ipynb").write_text(json.dumps(FIXTURES["mixed"], indent=1)[:300])
    Image.new("RGB", (40, 40), (220, 20, 60)).save(OUT / "inside.png")
    Image.new("RGB", (40, 40), (255, 0, 255)).save(OUT.parent / "outside.png")
    print(f"wrote {len(FIXTURES) + 1} notebooks to {OUT}")


if __name__ == "__main__":
    main()
