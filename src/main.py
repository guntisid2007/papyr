import sys


def self_test(sample: str) -> int:
    """Headless check used by CI on the packaged app.

    Exercises HEIC decoding, PDF writing, PDF rendering, notebook layout, every image encoder, and the window itself.
    """
    import base64
    import io
    import json
    import tempfile
    from pathlib import Path

    import pypdfium2 as pdfium
    from PIL import Image
    from PySide6.QtGui import QColor, QPalette

    from converter import (GifSettings, ImageSettings, OutputFormat, PageSize, PdfSettings, convert_combined_gif,
                           convert_images, convert_merged)
    from gui.app import create_app, use_headless_platform
    from gui.main_window import MainWindow

    use_headless_platform()
    app = create_app([sys.argv[0]])  # notebooks are laid out with Qt, so the app must exist before converting
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "self-test.pdf"
        report = convert_merged([Path(sample)], pdf, PdfSettings(PageSize.A4, 10))
        if report.outputs != [pdf] or report.failures or b"/Count 1" not in pdf.read_bytes():
            problems.append(f"HEIC to PDF: {report.failures}")
        report = convert_images([pdf], Path(tmp) / "png", ImageSettings(OutputFormat.PNG, pdf_dpi=72))
        if len(report.outputs) != 1 or report.failures:
            problems.append(f"PDF to PNG: {report.failures}")
        for fmt in OutputFormat:
            if fmt is OutputFormat.PDF or not report.outputs:
                continue
            converted = convert_images(report.outputs, Path(tmp) / fmt.name, ImageSettings(fmt))
            if len(converted.outputs) != 1 or converted.failures:
                problems.append(f"PNG to {fmt.label}: {converted.failures}")
                continue
            with Image.open(converted.outputs[0]) as image:
                image.load()
        animation = Path(tmp) / "animation.gif"
        report = convert_combined_gif([pdf, pdf], animation, GifSettings(frame_ms=500))
        if report.outputs != [animation] or report.failures:
            problems.append(f"PDF to animated GIF: {report.failures}")
        else:
            with Image.open(animation) as image:
                if image.n_frames != 2 or image.info.get("loop") != 0 or image.info.get("duration") != 500:
                    problems.append(f"PDF to animated GIF: {image.n_frames} frames, {image.info}")
        wide_figure = io.BytesIO()
        Image.new("RGB", (4000, 400), "green").save(wide_figure, "PNG")
        square = '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"><rect width="40" height="40"/></svg>'
        notebook = Path(tmp) / "self-test.ipynb"
        notebook.write_text(json.dumps({"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": "Energy $E = mc^2$"},
            {"cell_type": "code", "execution_count": 1, "metadata": {}, "source": "print('papyr')  # 1",
             "outputs": [{"output_type": "stream", "name": "stdout", "text": "papyr\n"},
                         {"output_type": "display_data", "metadata": {},
                          "data": {"image/png": base64.b64encode(wide_figure.getvalue()).decode()}},
                         {"output_type": "display_data", "metadata": {}, "data": {"image/svg+xml": square}}]}]}))
        notebook_pdf = Path(tmp) / "notebook.pdf"
        light = app.palette()
        dark = QPalette(light)
        dark.setColor(QPalette.ColorRole.Text, QColor("white"))  # macOS dark mode once made notebook text invisible
        app.setPalette(dark)
        report = convert_merged([notebook], notebook_pdf, PdfSettings(PageSize.A4, 10))
        app.setPalette(light)
        if report.outputs != [notebook_pdf] or report.failures:
            problems.append(f"Notebook to PDF: {report.failures}")
        else:
            page = pdfium.PdfDocument(notebook_pdf.read_bytes())[0]
            text_page = page.get_textpage()
            found = text_page.get_text_range().find("papyr")
            if found < 0:
                problems.append("Notebook to PDF: text is not searchable")
            else:
                left, bottom, right, top = text_page.get_charbox(found)
                word = page.render(scale=2).to_pil().convert("L").crop(
                    (int(left * 2), int((page.get_height() - top) * 2), int(right * 2) + 1,
                     int((page.get_height() - bottom) * 2) + 1))
                if word.getextrema()[0] > 100:
                    problems.append("Notebook to PDF: text is invisible")
            figures = [obj.get_bounds() for obj in page.get_objects() if obj.type == pdfium.raw.FPDF_PAGEOBJ_IMAGE]
            if len(figures) != 3 or max(right - left for left, _, right, _ in figures) > page.get_width():
                problems.append(f"Notebook to PDF: math, PNG, and SVG drawn as {figures}")
            colors = set()
            for obj in page.get_objects():
                if obj.type == pdfium.raw.FPDF_PAGEOBJ_TEXT:
                    rgba = [pdfium.raw.c_uint() for _ in range(4)]
                    pdfium.raw.FPDFPageObj_GetFillColor(obj.raw, *rgba)
                    colors.add(tuple(c.value for c in rgba))
            if len(colors) < 4:
                problems.append(f"Notebook to PDF: code is not highlighted ({len(colors)} text colors)")
    window = MainWindow()
    window.show()
    app.processEvents()
    window.close()
    del window
    print("self-test", "passed" if not problems else "failed: " + "; ".join(problems))
    return 0 if not problems else 1


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        sys.exit(self_test(sys.argv[2]))
    from gui.app import run
    sys.exit(run())
