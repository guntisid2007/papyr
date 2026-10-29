import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QSettings, QThreadPool  # noqa: E402
from pypdf import PdfReader  # noqa: E402

from converter import PageSize  # noqa: E402
from gui.app import create_app  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    QCoreApplication.setOrganizationName("HEIC to PDF Tests")
    return create_app(["test"])


@pytest.fixture
def window(app, tmp_path):
    QSettings("HEIC to PDF Tests", "HEIC to PDF").clear()
    win = MainWindow()
    win._output_label.setText(str(tmp_path / "out"))
    (tmp_path / "out").mkdir()
    win.show()
    yield win
    win.close()
    win.deleteLater()


def wait_until(app, condition, timeout=20):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        app.processEvents()
        time.sleep(0.01)


def test_merge_follows_list_order_after_reordering(app, window, make, sample_heic, tmp_path):
    sources = [make("a.png", (100, 50)), make("b.jpg", (50, 100)), sample_heic]
    window.add_paths(sources)
    window.add_paths([sources[0]])  # duplicates are ignored
    assert window._list.count() == 3
    QThreadPool.globalInstance().waitForDone()

    window._list.item(2).setSelected(True)
    window._list.move_selected(-1)
    window._list.move_selected(-1)
    assert [p.name for p in window._list.paths()] == ["sample.heic", "a.png", "b.jpg"]

    window._merged.setChecked(True)
    window._name_edit.setText("My Album")
    window._page_combo.setCurrentIndex(window._page_combo.findData(PageSize.ORIGINAL))
    window._margin.setValue(0)
    window._convert_button.click()
    assert window._converting
    wait_until(app, lambda: not window._converting)

    pages = PdfReader(tmp_path / "out" / "My Album.pdf").pages
    assert [(float(p.mediabox.width), float(p.mediabox.height)) for p in pages] == [(640, 480), (100, 50), (50, 100)]
    assert window._status.text().startswith("✓")
    assert window._open_button.isVisibleTo(window)


def test_individual_mode_and_settings_are_remembered(app, window, make, tmp_path):
    window.add_paths([make("one.heic"), make("two.png")])
    window._individual.setChecked(True)
    window._page_combo.setCurrentIndex(window._page_combo.findData(PageSize.LETTER))
    window._convert_button.click()
    wait_until(app, lambda: not window._converting)
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["one.pdf", "two.pdf"]

    again = MainWindow()
    assert again._output_dir() == tmp_path / "out"
    assert again._page_combo.currentData() is PageSize.LETTER
    again.deleteLater()


def test_folder_drop_adds_images_and_clear_all_empties(window, make, tmp_path):
    folder = tmp_path / "album"
    folder.mkdir()
    make("album/x.heic")
    make("album/y.jpg")
    (folder / "readme.txt").write_text("not an image")
    window.add_paths([folder])
    assert [p.name for p in window._list.paths()] == ["x.heic", "y.jpg"]
    assert window._stack.currentIndex() == 1
    window._list_buttons[-1].click()
    assert window._list.count() == 0 and window._stack.currentIndex() == 0
    assert not window._convert_button.isEnabled()


def test_unreadable_file_is_flagged_in_list(app, window, tmp_path):
    bad = tmp_path / "broken.heic"
    bad.write_bytes(b"not an image")
    window.add_paths([bad])
    wait_until(app, lambda: "⚠" in window._list.item(0).text())


def test_cancel_stops_merge_and_leaves_no_file(app, window, make, tmp_path):
    window.add_paths([make(f"{i}.png", (2500, 2500)) for i in range(30)])
    window._merged.setChecked(True)
    window._name_edit.setText("big")
    window._convert_button.click()
    window._cancel()
    wait_until(app, lambda: not window._converting)
    assert "cancelled" in window._status.text()
    assert list((tmp_path / "out").iterdir()) == []


def test_closing_mid_conversion_waits_for_worker(app, make, tmp_path, monkeypatch):
    import converter.convert as convert_module

    real_encode = convert_module.encode_for_pdf

    def slow_encode(path):
        time.sleep(12)  # longer than the old 10 s shutdown timeout
        return real_encode(path)

    monkeypatch.setattr(convert_module, "encode_for_pdf", slow_encode)
    win = MainWindow()
    win._output_label.setText(str(tmp_path))
    win.add_paths([make("slow.png")])
    win._individual.setChecked(True)
    win._convert_button.click()
    thread = win._thread
    wait_until(app, lambda: "Converting" in win._status.text())
    win.close()
    assert not thread.isRunning()
    assert list(tmp_path.glob("*.pdf")) == []  # cancelled before the PDF was written
    win.deleteLater()
