import sys
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QMimeData, QPoint, QPointF, QSettings, Qt, QThreadPool, QUrl
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QHelpEvent, QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox, QToolTip
from pypdf import PdfReader

from converter import OutputFormat, PageSize
from gui.file_queue import FileState, QueueDelegate
from gui.main_window import MainWindow, Run
from pdf_samples import text_pdf


@pytest.fixture
def window(app, tmp_path):
    QSettings().clear()
    win = MainWindow()
    (tmp_path / "out").mkdir()
    win.set_output_dir(tmp_path / "out")
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


def names(window) -> list[str]:
    return [p.name for p in window._queue.paths()]


def shown(window, widget) -> bool:
    return widget.isVisibleTo(window)


def choose_format(window, fmt: OutputFormat) -> None:
    window._panel.format_combo.setCurrentIndex(window._panel.format_combo.findData(fmt))


def convert(app, window) -> None:
    window._convert_button.click()
    assert window._converting
    wait_until(app, lambda: not window._converting)


def outputs(tmp_path) -> list[str]:
    return sorted(p.name for p in (tmp_path / "out").iterdir())


# Adding and removing files

def test_empty_state_until_files_arrive_and_after_clear_all(window, make, tmp_path):
    assert window._stack.currentWidget() is window._empty
    assert not window._convert_button.isEnabled()
    assert window._convert_button.toolTip() == "Add files to convert."

    folder = tmp_path / "album"
    folder.mkdir()
    make("album/x.heic")
    make("album/y.jpg")
    (folder / "readme.txt").write_text("not an image")
    window.add_paths([folder])
    assert names(window) == ["x.heic", "y.jpg"]
    assert window._stack.currentWidget() is not window._empty
    assert window._summary_label.text() == "2 files ready"
    assert window._convert_button.isEnabled()

    window._clear_button.click()
    assert window._queue.count() == 0 and window._stack.currentWidget() is window._empty
    assert not window._convert_button.isEnabled()


def test_duplicates_are_ignored(window, make):
    a = make("a.png")
    window.add_paths([a, make("b.png")])
    window.add_paths([a])
    assert names(window) == ["a.png", "b.png"]
    assert window._status.text() == "Those files are already in the list."


def test_unsupported_files_are_reported_and_not_added(window, make, tmp_path):
    notes = [tmp_path / "notes.txt", tmp_path / "data.csv"]
    for note in notes:
        note.write_text("x")
    window.add_paths([*notes, make("a.png")])
    assert names(window) == ["a.png"]
    assert window._status.text() == "Added 1 file. 2 files skipped — this file format isn't supported."

    window.add_paths(notes[:1])
    assert names(window) == ["a.png"]
    assert window._status.text() == "1 file skipped — this file format isn't supported."
    assert window._status.property("kind") == "error"


def test_unreadable_file_is_flagged_with_a_friendly_reason(app, window, make, tmp_path):
    bad = tmp_path / "broken.heic"
    bad.write_bytes(b"not an image")
    window.add_paths([bad, make("fine.png")])
    wait_until(app, lambda: window._queue.state(0) is FileState.UNREADABLE)
    assert window._queue.reason(0) == "The file appears to be damaged."
    assert window._queue.state(1) is FileState.PENDING
    assert window._summary_label.text() == "1 file ready · 1 can't be read"


def test_row_remove_button_removes_only_that_row(app, window, make):
    window.add_paths([make("a.png"), make("b.png"), make("c.png")])
    app.processEvents()
    viewport = window._queue.viewport()
    row = window._queue.visualItemRect(window._queue.item(1))
    button = QueueDelegate.remove_rect(row.toRectF().adjusted(4, 2, -4, -2)).center().toPoint()

    QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, row.center())
    assert names(window) == ["a.png", "b.png", "c.png"]
    QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, button)
    assert names(window) == ["a.png", "c.png"]

    QCoreApplication.sendEvent(viewport, QHelpEvent(QHelpEvent.Type.ToolTip, button, viewport.mapToGlobal(button)))
    assert QToolTip.text() == "Remove from list"


def test_backspace_removes_rows_only_while_the_list_has_focus(app, window, make):
    window.add_paths([make("a.png"), make("b.png")])
    window.activateWindow()
    window._queue.item(0).setSelected(True)

    window._panel.margin_spin.setFocus()
    app.processEvents()
    assert not window._remove_action.isEnabled()
    QTest.keyClick(window._panel.margin_spin, Qt.Key.Key_Backspace)
    assert names(window) == ["a.png", "b.png"]

    window._queue.setFocus()
    app.processEvents()
    assert window._remove_action.isEnabled()
    QTest.keyClick(window._queue, Qt.Key.Key_Backspace)
    assert names(window) == ["b.png"]


# Settings that depend on the format and the queue

def test_combine_appears_with_two_files_and_shows_its_name_field(window, make):
    choose_format(window, OutputFormat.PDF)
    panel = window._panel
    window.add_paths([make("a.png")])
    assert not shown(window, panel.combine_check) and not shown(window, panel.name_row)
    panel.combine_check.setChecked(True)
    assert not panel.combine() and not shown(window, window._order_hint)

    window.add_paths([make("b.png")])
    assert shown(window, panel.combine_check) and shown(window, panel.name_row)
    assert shown(window, window._order_hint)
    assert window._order_hint.text() == "Drag to reorder. Pages follow this order."
    panel.combine_check.setChecked(False)
    assert not shown(window, panel.name_row) and not shown(window, window._order_hint)


@pytest.mark.parametrize("fmt", [f for f in OutputFormat if f is not OutputFormat.PDF])
def test_image_settings_follow_the_format(window, make, fmt):
    window.add_paths([make("a.png")])
    choose_format(window, fmt)
    panel = window._panel
    assert shown(window, panel.image_options) and not shown(window, panel.pdf_options)
    assert shown(window, panel.quality_row) == (fmt.label in {"JPEG", "HEIC", "WebP", "AVIF"})
    expected = "Transparent areas become white." if fmt.label in {"JPEG", "BMP"} else "Transparency is preserved."
    assert panel.alpha_note.text() == expected
    assert window._convert_button.text() == f"Convert to {fmt.label}"


@pytest.mark.parametrize("document", ["report.pdf", "analysis.ipynb"])
def test_pdf_page_resolution_only_with_a_document_queued(window, make, tmp_path, document):
    choose_format(window, OutputFormat.JPEG)
    window.add_paths([make("photo.heic")])
    assert not shown(window, window._panel.dpi_row)
    path = tmp_path / document
    path.write_text("{}") if document.endswith(".ipynb") else text_pdf(path, ["a"])
    window.add_paths([path])
    assert shown(window, window._panel.dpi_row)
    window._queue.item(1).setSelected(True)
    window._queue.remove_selected()
    assert not shown(window, window._panel.dpi_row)


def test_quality_slider_shows_its_value_and_is_remembered(window):
    choose_format(window, OutputFormat.WEBP)
    window._panel.quality_slider.setValue(40)
    assert window._panel.quality_value.text() == "40%"
    window.close()
    again = MainWindow()
    assert again._panel.quality_slider.value() == 40 and again._panel.output_format() is OutputFormat.WEBP
    again.deleteLater()


# Where files are saved

def test_missing_folder_blocks_convert_and_says_why(window, make, tmp_path):
    window.add_paths([make("a.png")])
    window.set_output_dir(tmp_path / "gone")
    assert not window._convert_button.isEnabled()
    assert window._convert_button.toolTip() == "The Save to folder no longer exists. Choose another folder."
    assert window._panel.destination.problem_label.text() == "Folder not found — choose another"
    assert shown(window, window._panel.destination.problem_label)
    assert window._panel.destination.property("problem") is True


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_unwritable_folder_blocks_convert(window, make, tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o555)
    try:
        window.add_paths([make("a.png")])
        window.set_output_dir(locked)
        assert not window._convert_button.isEnabled()
        assert window._panel.destination.problem_label.text() == "This folder isn't writable"
        assert "can't save" in window._convert_button.toolTip()
    finally:
        locked.chmod(0o755)


def test_folder_removed_after_choosing_it_is_caught_at_convert_time(app, window, make, tmp_path):
    target = tmp_path / "soon-gone"
    target.mkdir()
    window.add_paths([make("a.png")])
    window.set_output_dir(target)
    target.rmdir()
    window._convert_action.trigger()
    assert not window._converting
    assert window._status.text() == "The Save to folder no longer exists. Choose another folder."
    assert not window._convert_button.isEnabled()


def test_change_picks_a_folder_and_remembers_it(window, make, tmp_path, monkeypatch):
    picked = tmp_path / "Picked"
    picked.mkdir()
    window.set_output_dir(tmp_path / "gone")
    monkeypatch.setattr("gui.main_window.QFileDialog.getExistingDirectory", lambda *a: str(picked))
    window._panel.destination.change_button.click()
    assert window.output_dir() == picked
    assert window._panel.destination.name_label.text() == "Picked"
    assert window._panel.destination.property("problem") is False
    assert not shown(window, window._panel.destination.problem_label)
    window.add_paths([make("a.png")])
    assert window._convert_button.isEnabled()
    assert MainWindow().output_dir() == picked


def test_launch_falls_back_to_documents_when_the_saved_folder_is_gone(app, tmp_path):
    from PySide6.QtCore import QStandardPaths

    QSettings().clear()
    QSettings().setValue("output_dir", str(tmp_path / "deleted"))
    documents = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation))
    win = MainWindow()
    assert win.output_dir() == (documents if documents.is_dir() else Path.home())
    win.deleteLater()


# Converting

def test_merge_follows_queue_order_after_moving_rows(app, window, make, sample_heic, tmp_path):
    window.add_paths([make("a.png", (100, 50)), make("b.jpg", (50, 100)), sample_heic])
    QThreadPool.globalInstance().waitForDone()
    window._queue.item(2).setSelected(True)
    window._move_up_action.trigger()
    window._move_up_action.trigger()
    assert names(window) == ["sample.heic", "a.png", "b.jpg"]

    choose_format(window, OutputFormat.PDF)
    window._panel.combine_check.setChecked(True)
    window._panel.name_edit.setText("My Album")
    window._panel.page_combo.setCurrentIndex(window._panel.page_combo.findData(PageSize.ORIGINAL))
    window._panel.margin_spin.setValue(0)
    convert(app, window)

    pages = PdfReader(tmp_path / "out" / "My Album.pdf").pages
    assert [(float(p.mediabox.width), float(p.mediabox.height)) for p in pages] == [(640, 480), (100, 50), (50, 100)]
    assert window._status.text() == "✓ Saved My Album.pdf"
    assert shown(window, window._reveal_button) and window._reveal_action.isEnabled()

    window._move_down_action.trigger()
    assert names(window) == ["a.png", "sample.heic", "b.jpg"]
    assert shown(window, window._reveal_button), "reordering keeps the result"


def test_individual_pdfs_and_settings_are_remembered(app, window, make, tmp_path):
    window.add_paths([make("one.heic"), make("two.png")])
    choose_format(window, OutputFormat.PDF)
    window._panel.page_combo.setCurrentIndex(window._panel.page_combo.findData(PageSize.LETTER))
    convert(app, window)
    assert outputs(tmp_path) == ["one.pdf", "two.pdf"]
    assert window._status.text() == "✓ 2 files converted successfully"

    again = MainWindow()
    assert again.output_dir() == tmp_path / "out"
    assert again._panel.page_combo.currentData() is PageSize.LETTER
    again.deleteLater()


def test_converting_to_an_image_format_from_the_window(app, window, make, tmp_path):
    doc = text_pdf(tmp_path / "notes.pdf", ["a", "b"], size=(72, 72))
    window.add_paths([make("photo.heic"), doc])
    choose_format(window, OutputFormat.WEBP)
    assert shown(window, window._panel.dpi_row)
    convert(app, window)
    assert outputs(tmp_path) == ["notes-page-1.webp", "notes-page-2.webp", "photo.webp"]


def test_partial_failure_marks_the_failed_row_and_keeps_the_rest(app, window, make, tmp_path, monkeypatch):
    files = [make("a.png"), make("b.png"), make("c.png")]
    window.add_paths(files)
    QThreadPool.globalInstance().waitForDone()
    files[1].unlink()
    choose_format(window, OutputFormat.PNG)
    monkeypatch.setattr("gui.main_window.QMessageBox.warning", lambda *a: pytest.fail("no modal on failure"))
    convert(app, window)

    assert outputs(tmp_path) == ["a.png", "c.png"]
    assert window._status.text() == "Conversion failed for 1 file. The remaining files were saved."
    assert [window._queue.state(i) for i in range(3)] == [FileState.PENDING, FileState.FAILED, FileState.PENDING]
    assert window._queue.reason(1) == "The file was moved or deleted."
    assert shown(window, window._reveal_button) and shown(window, window._details_button)

    window._details_button.click()
    box = window.findChild(QMessageBox)
    assert "b.png: The file was moved or deleted." in box.informativeText()
    assert "No such file" in box.detailedText()
    box.close()

    convert(app, window)
    assert window._queue.state(1) is FileState.FAILED, "a second run reports it again"
    assert outputs(tmp_path) == ["a (1).png", "a.png", "c (1).png", "c.png"], "convert again with one click"

    window.add_paths([make("d.png")])
    assert not shown(window, window._details_button) and not shown(window, window._reveal_button)
    assert window._status.text() == "Added 1 file."


def test_total_failure_says_why(app, window, make, tmp_path):
    gone = make("gone.png")
    window.add_paths([gone])
    QThreadPool.globalInstance().waitForDone()
    gone.unlink()
    convert(app, window)
    assert window._status.text() == "Conversion failed. The file was moved or deleted."
    assert window._status.property("kind") == "error"
    assert not shown(window, window._reveal_button) and shown(window, window._details_button)


def test_show_in_finder_reveals_the_first_output(app, window, make, tmp_path, monkeypatch):
    revealed = []
    monkeypatch.setattr("gui.main_window.reveal", revealed.append)
    window.add_paths([make("a.png")])
    choose_format(window, OutputFormat.JPEG)
    convert(app, window)
    window._reveal_button.click()
    window._reveal_action.trigger()
    assert revealed == [tmp_path / "out" / "a.jpg"] * 2


def test_progress_cancel_and_no_second_job_while_converting(app, window, make, tmp_path):
    window.add_paths([make(f"{i}.png", (2500, 2500)) for i in range(30)])
    choose_format(window, OutputFormat.PDF)
    window._convert_button.click()
    thread = window._thread
    wait_until(app, lambda: window._status.text().startswith("Converting "))
    assert " of 30 — " in window._status.text()
    assert shown(window, window._progress) and shown(window, window._cancel_button)
    assert not window._convert_button.isEnabled() and not window._convert_action.isEnabled()
    window._convert()
    window._convert_action.trigger()
    assert window._thread is thread

    window._cancel_button.click()
    wait_until(app, lambda: not window._converting)
    assert window._status.text().startswith("Conversion cancelled.")
    assert not shown(window, window._progress) and not shown(window, window._cancel_button)
    assert all(" (1)" not in name for name in outputs(tmp_path))


def test_cancel_stops_merge_and_leaves_no_file(app, window, make, tmp_path):
    window.add_paths([make(f"{i}.png", (2500, 2500)) for i in range(30)])
    choose_format(window, OutputFormat.PDF)
    window._panel.combine_check.setChecked(True)
    window._panel.name_edit.setText("big")
    window._convert_button.click()
    window._cancel()
    wait_until(app, lambda: not window._converting)
    assert window._status.text() == "Conversion cancelled."
    assert outputs(tmp_path) == []


def test_closing_mid_conversion_waits_for_worker(app, make, tmp_path, monkeypatch):
    import converter.convert as convert_module

    real_encode = convert_module.encode_for_pdf

    def slow_encode(*args):
        time.sleep(12)  # longer than the old 10 s shutdown timeout
        return real_encode(*args)

    monkeypatch.setattr(convert_module, "encode_for_pdf", slow_encode)
    QSettings().clear()
    win = MainWindow()
    win.set_output_dir(tmp_path)
    win.add_paths([make("slow.png")])
    choose_format(win, OutputFormat.PDF)
    win._convert_button.click()
    thread = win._thread
    wait_until(app, lambda: "Converting" in win._status.text())
    win.close()
    assert not thread.isRunning()
    assert list(tmp_path.glob("*.pdf")) == []  # cancelled before the PDF was written
    win.deleteLater()


def test_unexpected_error_in_job_returns_window_to_idle(app, window, make, monkeypatch):
    import converter.convert as convert_module

    def explode(*args):
        raise RuntimeError("boom")

    monkeypatch.setattr(convert_module, "encode_for_pdf", explode)
    window.add_paths([make("a.png")])
    choose_format(window, OutputFormat.PDF)
    convert(app, window)
    assert window._status.text().startswith("Conversion failed.")
    assert "boom" not in window._status.text() and "Traceback" not in window._status.text()
    assert window._convert_button.isEnabled()


# Save animation

def test_save_animation_plays_after_conversion_and_cleans_up(app, window, make, tmp_path):
    from gui.save_animation import SaveAnimation

    window.add_paths([make("one.png"), make("two.png")])
    choose_format(window, OutputFormat.PDF)
    window._convert_button.click()
    wait_until(app, lambda: window.findChildren(SaveAnimation))
    overlay = window.findChildren(SaveAnimation)[0]
    assert overlay.isVisible() and overlay._count == 2
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    wait_until(app, lambda: not window.findChildren(SaveAnimation), timeout=5)


def test_no_save_animation_when_cancelled(app, window, make):
    from gui.save_animation import SaveAnimation

    window.add_paths([make(f"{i}.png", (2500, 2500)) for i in range(20)])
    choose_format(window, OutputFormat.PDF)
    window._panel.combine_check.setChecked(True)
    window._convert_button.click()
    window._cancel()
    wait_until(app, lambda: not window._converting)
    for _ in range(5):
        app.processEvents()
    assert not window.findChildren(SaveAnimation)


def test_save_animation_follows_window_resize(app, window):
    window._reveal_button.show()
    window.resize(1000, 660)
    app.processEvents()
    animation = window._play_save_animation(1)
    animation._animation.stop()
    window.resize(760, 520)
    app.processEvents()
    animation.set_progress(0.8)
    canvas = window.centralWidget()
    assert animation.geometry() == canvas.rect()
    assert canvas.rect().contains(animation._end.toPoint())
    assert animation._end == window._save_animation_endpoints()[1]


def test_queued_save_animation_is_dropped_with_deleted_window(app, tmp_path, capfd):
    from PySide6.QtCore import QEvent

    from converter import ConversionReport

    win = MainWindow()
    win._run = Run(sources=[], combined=False)
    win._on_finished(ConversionReport(outputs=[tmp_path / "x.pdf"]))
    win.close()
    win.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    assert "already deleted" not in capfd.readouterr().err  # Qt prints slot exceptions instead of raising


# Menus, shortcuts, and files from the system

def menu_actions(window) -> dict[str, list[str]]:
    return {menu.title().replace("&", ""): [a.text() for a in menu.actions() if not a.isSeparator()]
            for menu in (a.menu() for a in window.menuBar().actions())}


def test_menus_and_shortcuts(window):
    from utils.reveal import REVEAL_LABEL

    assert menu_actions(window) == {
        "File": ["Add Files…", "Add Folder…", "Convert", REVEAL_LABEL, "Close Window", "Quit"],
        "Edit": ["Select All", "Remove Selected", "Move Up", "Move Down", "Clear All"],
        "Help": ["About Papyr"],
    }
    shortcuts = {
        window._add_files_action: QKeySequence(QKeySequence.StandardKey.Open),
        window._add_folder_action: QKeySequence("Ctrl+Shift+O"),
        window._convert_action: QKeySequence("Ctrl+Return"),
        window._close_action: QKeySequence(QKeySequence.StandardKey.Close),
        window._select_all_action: QKeySequence(QKeySequence.StandardKey.SelectAll),
        window._move_up_action: QKeySequence("Ctrl+Alt+Up"),
        window._move_down_action: QKeySequence("Ctrl+Alt+Down"),
    }
    for action, sequence in shortcuts.items():
        assert action.shortcut() == sequence, action.text()
    assert window._remove_action.shortcuts() == [QKeySequence(Qt.Key.Key_Backspace), QKeySequence(Qt.Key.Key_Delete)]
    assert window._remove_action.shortcutContext() == Qt.ShortcutContext.WidgetWithChildrenShortcut
    assert window._about_action.menuRole() == QAction.MenuRole.AboutRole


def test_menu_actions_do_what_they_say(app, window, make, monkeypatch):
    picked = [make("a.png"), make("b.png"), make("c.png")]
    monkeypatch.setattr("gui.main_window.QFileDialog.getOpenFileNames", lambda *a: ([str(p) for p in picked], ""))
    window._add_files_action.trigger()
    assert names(window) == ["a.png", "b.png", "c.png"]

    window._select_all_action.trigger()
    assert len(window._queue.selectedItems()) == 3
    window._clear_action.trigger()
    assert window._queue.count() == 0

    about = []
    monkeypatch.setattr("gui.main_window.QMessageBox.about", lambda parent, title, text: about.append(text))
    window._about_action.trigger()
    assert "Papyr 2.1.0" in about[0]

    window._close_action.trigger()
    assert not window.isVisible()


def test_select_all_in_a_text_field_selects_its_text(app, window, make):
    window.add_paths([make("a.png"), make("b.png")])
    choose_format(window, OutputFormat.PDF)
    window._panel.combine_check.setChecked(True)
    window._panel.name_edit.setText("Trip Photos")
    window.activateWindow()
    window._panel.name_edit.setFocus()
    app.processEvents()
    window._select_all_action.trigger()
    assert window._panel.name_edit.selectedText() == "Trip Photos"
    assert window._queue.selectedItems() == []


def drag_files(target, paths: list[Path]) -> tuple[QMimeData, QPoint]:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    point = target.rect().center()
    enter = QDragEnterEvent(point, Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton,
                            Qt.KeyboardModifier.NoModifier)
    QCoreApplication.sendEvent(target, enter)
    assert enter.isAccepted()
    return mime, point


def drop(target, mime: QMimeData, point: QPoint) -> None:
    QCoreApplication.sendEvent(target, QDropEvent(QPointF(point), Qt.DropAction.CopyAction, mime,
                                                  Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))


@pytest.mark.filterwarnings("ignore:Function.*QDragEnterEvent:DeprecationWarning")  # the QPointF overload crashes
def test_files_dropped_anywhere_on_the_window_are_added(app, window, make, tmp_path):
    for target in (window._panel, window._empty):
        mime, point = drag_files(target, [make("a.png")])
        assert window._workspace.property("dragging") is True
        drop(target, mime, point)
        assert window._workspace.property("dragging") is False
    assert names(window) == ["a.png"]

    folder = tmp_path / "album"
    folder.mkdir()
    make("album/b.jpg")
    viewport = window._queue.viewport()
    mime, point = drag_files(viewport, [folder])
    drop(viewport, mime, point)
    assert names(window) == ["a.png", "b.jpg"]


def test_tab_order_runs_format_settings_destination_convert(window):
    panel = window._panel
    wanted = [panel.format_combo, panel.combine_check, panel.name_edit, panel.page_combo, panel.margin_spin,
              panel.quality_slider, panel.dpi_combo, panel.destination.change_button, window._convert_button]
    order, widget = [], panel.format_combo
    for _ in range(200):
        if widget in wanted and widget not in order:
            order.append(widget)
        widget = widget.nextInFocusChain()
    assert order == wanted


def test_secondary_text_is_readable_and_follows_a_scheme_change(app):
    """Offscreen Qt ignores setColorScheme, so switch the application palette the way the system does."""
    from PySide6.QtGui import QColor, QPalette
    from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

    def luminance(color: QColor) -> float:
        def channel(c: float) -> float:
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * channel(color.redF()) + 0.7152 * channel(color.greenF()) + 0.0722 * channel(color.blueF())

    light = app.palette()
    dark = QPalette(light)
    for role, color in [(QPalette.ColorRole.Window, "#2b2b2b"), (QPalette.ColorRole.WindowText, "#ffffff"),
                        (QPalette.ColorRole.Base, "#1e1e1e"), (QPalette.ColorRole.Text, "#ffffff")]:
        dark.setColor(role, QColor(color))
    try:
        for palette, is_dark in ((dark, True), (light, False)):
            app.setPalette(palette)
            app.processEvents()
            host = QWidget()
            label = QLabel("Sets the resolution of images made from PDF pages.")
            label.setObjectName("Secondary")
            QVBoxLayout(host).addWidget(label)
            image = host.grab().toImage()
            background = luminance(image.pixelColor(1, 1))
            text = max((luminance(image.pixelColor(x, y)) for x in range(0, image.width(), 2)
                        for y in range(image.height())), key=lambda value: abs(value - background))
            assert (background < 0.2) == is_dark
            assert (text > background) == is_dark, "text flips to light on dark backgrounds"
            lighter, darker = max(background, text), min(background, text)
            assert (lighter + 0.05) / (darker + 0.05) >= 4.5
            host.deleteLater()
    finally:
        app.setPalette(light)
        app.processEvents()
