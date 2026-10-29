import sys


def self_test(sample: str) -> int:
    """Headless check used by CI on the packaged app: decode a HEIC, write a PDF, build the window."""
    import os
    import tempfile
    from pathlib import Path

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from converter import PageSize, PdfSettings, convert_merged
    from gui.app import create_app
    from gui.main_window import MainWindow

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "self-test.pdf"
        report = convert_merged([Path(sample)], out, PdfSettings(PageSize.A4, 10))
        data = out.read_bytes() if out.exists() else b""
        ok = report.outputs == [out] and not report.failures and data.startswith(b"%PDF") and b"/Count 1" in data
    app = create_app([sys.argv[0]])
    window = MainWindow()
    window.show()
    app.processEvents()
    window.close()
    del window
    print("self-test", "passed" if ok else f"failed: {report.failures}")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        sys.exit(self_test(sys.argv[2]))
    from gui.app import run
    sys.exit(run())
