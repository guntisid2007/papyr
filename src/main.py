import sys


def self_test(sample: str) -> int:
    """Headless check used by CI on the packaged app.

    Exercises HEIC decoding, PDF writing, PDF rendering, every image encoder, and the window itself.
    """
    import os
    import tempfile
    from pathlib import Path

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PIL import Image

    from converter import ImageSettings, OutputFormat, PageSize, PdfSettings, convert_images, convert_merged
    from gui.app import create_app
    from gui.main_window import MainWindow

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
    app = create_app([sys.argv[0]])
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
