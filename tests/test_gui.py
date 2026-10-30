import time

import pytest
from PySide6.QtCore import QSettings, Qt, QThreadPool
from pypdf import PdfReader

from converter import OutputFormat, PageSize
from gui.main_window import MainWindow


@pytest.fixture
def window(app, tmp_path):
    QSettings().clear()
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

    def slow_encode(*args):
        time.sleep(12)  # longer than the old 10 s shutdown timeout
        return real_encode(*args)

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


def test_save_animation_plays_after_conversion_and_cleans_up(app, window, make, tmp_path):
    from gui.save_animation import SaveAnimation

    window.add_paths([make("one.png"), make("two.png")])
    window._convert_button.click()
    wait_until(app, lambda: window.findChildren(SaveAnimation))
    overlay = window.findChildren(SaveAnimation)[0]
    assert overlay.isVisible() and overlay._count == 2
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    wait_until(app, lambda: not window.findChildren(SaveAnimation), timeout=5)


def test_no_save_animation_when_cancelled(app, window, make):
    from gui.save_animation import SaveAnimation

    window.add_paths([make(f"{i}.png", (2500, 2500)) for i in range(20)])
    window._merged.setChecked(True)
    window._convert_button.click()
    window._cancel()
    wait_until(app, lambda: not window._converting)
    for _ in range(5):
        app.processEvents()
    assert not window.findChildren(SaveAnimation)


def test_save_animation_follows_window_resize(app, window):
    window._open_button.show()
    window.resize(1040, 680)
    app.processEvents()
    animation = window._play_save_animation(1)
    animation._animation.stop()
    window.resize(880, 580)
    app.processEvents()
    animation.set_progress(0.8)
    canvas = window.centralWidget()
    assert animation.geometry() == canvas.rect()
    assert canvas.rect().contains(animation._end.toPoint())
    assert animation._end == window._save_animation_endpoints()[1]


def test_queued_save_animation_is_dropped_with_deleted_window(app, tmp_path, capfd):
    from PySide6.QtCore import QCoreApplication, QEvent

    from converter import ConversionReport

    win = MainWindow()
    win._on_finished(ConversionReport(outputs=[tmp_path / "x.pdf"]))
    win.close()
    win.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    assert "already deleted" not in capfd.readouterr().err  # Qt prints slot exceptions instead of raising


def test_unexpected_error_in_job_returns_window_to_idle(app, window, make, monkeypatch):
    import converter.convert as convert_module

    def explode(*args):
        raise RuntimeError("boom")

    monkeypatch.setattr(convert_module, "encode_for_pdf", explode)
    monkeypatch.setattr("gui.main_window.QMessageBox.warning", lambda *a: None)
    window.add_paths([make("a.png")])
    window._format_combo.setCurrentIndex(window._format_combo.findData(OutputFormat.PDF))
    window._convert_button.click()
    wait_until(app, lambda: not window._converting, timeout=5)
    assert "failed" in window._status.text().lower()
    assert window._convert_button.isEnabled()


def test_converting_to_an_image_format_from_the_window(app, window, make, tmp_path):
    from pdf_samples import text_pdf

    doc = text_pdf(tmp_path / "notes.pdf", ["a", "b"], size=(72, 72))
    window.add_paths([make("photo.heic"), doc])
    window._format_combo.setCurrentIndex(window._format_combo.findData(OutputFormat.WEBP))
    assert window._image_options.isVisibleTo(window) and not window._pdf_options.isVisibleTo(window)
    assert window._quality.isVisibleTo(window)
    assert window._convert_button.text() == "Convert to WebP"
    window._convert_button.click()
    wait_until(app, lambda: not window._converting)
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == [
        "notes-page-1.webp", "notes-page-2.webp", "photo.webp"]

    window._format_combo.setCurrentIndex(window._format_combo.findData(OutputFormat.PNG))
    assert not window._quality.isVisibleTo(window)
