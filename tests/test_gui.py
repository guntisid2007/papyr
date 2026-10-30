import sys
import threading
import time
from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import QCoreApplication, QMimeData, QPoint, QPointF, QSettings, Qt, QThreadPool, QUrl
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QFileOpenEvent, QHelpEvent, QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QToolTip
from pypdf import PdfReader

from conftest import FIXTURES
from converter import ConversionReport, GifResolution, OutputFormat, PageSize
from gui.file_queue import FileState, QueueDelegate
from gui.main_window import MainWindow, RunSpec
from gui.model import Converting, Done, GifMode, Outcome, Welcome, Workspace
from gui.workers import ConversionWorker
from pdf_samples import TWELVE_COLORS, colored_pdf, text_pdf


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
    return [p.name for p in window.queue.paths()]


def shown(window, widget) -> bool:
    return widget.isVisibleTo(window)


def choose_format(window, fmt: OutputFormat) -> None:
    """Pick a format the way a user does: its segment, or the More menu for the rarer ones."""
    bar = window.dock.formats
    if fmt in bar.buttons:
        bar.buttons[fmt].click()
    else:
        next(a for a in bar.menu.actions() if a.data() is fmt).trigger()


def convert(app, window) -> None:
    window.dock.convert_button.click()
    assert window.is_converting()
    wait_until(app, lambda: not window.is_converting())


def outputs(tmp_path) -> list[str]:
    return sorted(p.name for p in (tmp_path / "out").iterdir())


def visible_page(window):
    return window._pages.currentWidget()


# The three states and the moves between them

def test_welcome_until_files_arrive_and_again_after_clear_all(window, make, tmp_path):
    assert isinstance(window.state(), Welcome) and visible_page(window) is window.welcome
    assert not shown(window, window.dock.convert_button), "nothing to convert yet"
    assert shown(window, window.dock.formats), "the format can be chosen before adding files"

    folder = tmp_path / "album"
    folder.mkdir()
    make("album/x.heic")
    make("album/y.jpg", (200, 100))
    (folder / "readme.txt").write_text("not an image")
    window.add_paths([folder])
    assert names(window) == ["x.heic", "y.jpg"]
    assert isinstance(window.state(), Workspace) and visible_page(window) is window.workspace
    assert window.workspace.summary.text().startswith("2 files · ")
    assert window.dock.convert_button.isEnabled()

    window.workspace.clear_button.click()
    assert window.queue.count() == 0 and isinstance(window.state(), Welcome)


def test_removing_the_last_file_returns_to_welcome(app, window, make):
    window.add_paths([make("a.png")])
    app.processEvents()
    row = window.queue.visualItemRect(window.queue.item(0))
    button = QueueDelegate.remove_rect(QueueDelegate.row_rect(row)).center().toPoint()
    QTest.mouseClick(window.queue.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, button)
    assert window.queue.count() == 0 and isinstance(window.state(), Welcome)


def test_a_finished_run_shows_done_and_can_go_back_or_start_over(app, window, make, tmp_path):
    window.add_paths([make("a.png"), make("b.png")])
    choose_format(window, OutputFormat.JPEG)
    convert(app, window)
    assert isinstance(window.state(), Done) and visible_page(window) is window.done
    assert not shown(window, window.dock), "Done has its own actions"
    assert window.state().result.outcome is Outcome.SUCCESS
    assert window.done.title.text() == "2 files converted"
    assert window.done.subtitle.text() == f"2 JPEG files saved to {tmp_path / 'out'}"
    assert shown(window, window.done.reveal_button) and not shown(window, window.done.retry_button)

    window.done.back_button.click()
    assert isinstance(window.state(), Workspace) and names(window) == ["a.png", "b.png"]
    convert(app, window)
    window.done.more_button.click()
    assert isinstance(window.state(), Welcome) and window.queue.count() == 0


def test_files_added_after_a_run_start_a_new_batch(app, window, make):
    window.add_paths([make("a.png")])
    convert(app, window)
    window.add_paths([make("b.png")])
    assert names(window) == ["b.png"] and isinstance(window.state(), Workspace)


def test_cancel_returns_to_the_files_and_says_what_was_kept(app, window, make, tmp_path, monkeypatch):
    revealed = []
    monkeypatch.setattr("gui.main_window.reveal", revealed.append)
    window.add_paths([make(f"{i}.png", (2500, 2500)) for i in range(30)])
    choose_format(window, OutputFormat.PNG)
    window.dock.convert_button.click()
    wait_until(app, lambda: window.state().done >= 1)
    window.dock.cancel_button.click()
    assert window.state().cancelling and not window.dock.cancel_button.isEnabled()
    wait_until(app, lambda: not window.is_converting())

    state = window.state()
    assert isinstance(state, Workspace) and names(window) == [f"{i}.png" for i in range(30)]
    kept = len(state.kept)
    assert 1 <= kept < 30 and kept == len(outputs(tmp_path))
    assert state.notice == f"Conversion cancelled. {kept} finished file{'s' if kept != 1 else ''} kept."
    assert shown(window, window.workspace.banner.reveal_button)
    window.workspace.banner.reveal_button.click()
    assert revealed == [state.kept[0]]


# Real progress

def test_progress_counts_files_done_and_left_and_blocks_a_second_start(app, window, make):
    window.add_paths([make(f"{i}.png") for i in range(5)])
    sources = window.queue.paths()
    release = threading.Event()

    def job(progress, cancelled):
        progress(2, 5, sources[2])
        release.wait(10)
        progress(5, 5, sources[4])
        return ConversionReport(outputs=[sources[0]])

    window._run = RunSpec(sources, OutputFormat.PDF, False, window.output_dir())
    window._start(ConversionWorker(job), len(sources))
    wait_until(app, lambda: window.state().done == 2)
    assert window.state() == Converting(total=5, done=2, current="2.png")
    assert window.dock.progress_title.text() == "Converting 3 of 5"
    assert window.dock.progress_remaining.text() == "2 done · 3 left"
    assert window.dock.progress.fraction() == pytest.approx(0.4)
    assert window.queue.active_row == 2

    thread = window._thread
    assert not window._convert_action.isEnabled()
    window._convert()
    window._convert_action.trigger()
    window.add_paths([Path(__file__)])
    assert window._thread is thread and window.queue.count() == 5, "no second job and no edits while converting"
    release.set()
    wait_until(app, lambda: not window.is_converting())


def test_escape_and_command_period_cancel(window):
    assert window._cancel_action.shortcuts() == [QKeySequence(Qt.Key.Key_Escape), QKeySequence("Ctrl+.")]
    assert not window._cancel_action.isEnabled()


# Done: success, partial failure, retry

def test_partial_failure_lists_reasons_and_retry_requeues_only_the_failed_files(app, window, make, tmp_path):
    files = [make("a.png"), make("b.png"), make("c.png"), make("d.png")]
    window.add_paths(files)
    QThreadPool.globalInstance().waitForDone()
    files[1].write_bytes(b"not a png")
    files[3].unlink()
    choose_format(window, OutputFormat.JPEG)
    convert(app, window)

    result = window.state().result
    assert result.outcome is Outcome.PARTIAL
    assert outputs(tmp_path) == ["a.jpg", "c.jpg"]
    assert window.done.title.text() == "2 of 4 files converted"
    assert "2 files couldn't be converted" in window.done.subtitle.text()
    failures = window.done.failures
    rows = [failures.item(i).data(Qt.ItemDataRole.AccessibleTextRole) for i in range(failures.count())]
    assert rows == ["b.png: The file appears to be damaged.", "d.png: The file was moved or deleted."]
    assert shown(window, window.done.retry_button) and shown(window, window.done.reveal_button)

    files[1].write_bytes(files[0].read_bytes())
    window.done.retry_button.click()
    state = window.state()
    assert isinstance(state, Workspace) and names(window) == ["b.png"]
    assert state.notice == "1 file that failed could not be found and was left out."
    convert(app, window)
    assert window.state().result.outcome is Outcome.SUCCESS
    assert outputs(tmp_path) == ["a.jpg", "b.jpg", "c.jpg"]


def test_nothing_converted_says_why_and_offers_retry_not_reveal(app, window, make):
    gone = make("gone.png")
    window.add_paths([gone])
    QThreadPool.globalInstance().waitForDone()
    gone.unlink()
    convert(app, window)
    assert window.state().result.outcome is Outcome.FAILED
    assert window.done.title.text() == "Nothing was converted"
    assert window.done.subtitle.text() == "The file was moved or deleted."
    assert not shown(window, window.done.reveal_button)
    assert shown(window, window.done.retry_button) and not window.done.retry_button.isEnabled()


def test_unexpected_error_in_the_job_ends_in_a_friendly_failure(app, window, make, monkeypatch):
    import converter.convert as convert_module

    def explode(*args):
        raise RuntimeError("boom")

    monkeypatch.setattr(convert_module, "encode_for_pdf", explode)
    window.add_paths([make("a.png")])
    choose_format(window, OutputFormat.PDF)
    convert(app, window)
    assert window.state().result.outcome is Outcome.FAILED
    assert "boom" not in window.done.subtitle.text() and "Traceback" not in window.done.subtitle.text()
    window.done.retry_button.click()
    assert names(window) == ["a.png"] and window.dock.convert_button.isEnabled()


def test_show_in_finder_reveals_the_first_output(app, window, make, tmp_path, monkeypatch):
    revealed = []
    monkeypatch.setattr("gui.main_window.reveal", revealed.append)
    window.add_paths([make("a.png")])
    choose_format(window, OutputFormat.JPEG)
    convert(app, window)
    window.done.reveal_button.click()
    window._reveal_action.trigger()
    assert revealed == [tmp_path / "out" / "a.jpg"] * 2


# Converting through the window, end to end with the real engine

def test_end_to_end_merged_pdf_follows_the_list_order(app, window, make, sample_heic, tmp_path):
    window.add_paths([make("a.png", (100, 50)), make("b.jpg", (50, 100)), sample_heic])
    QThreadPool.globalInstance().waitForDone()
    window.queue.item(2).setSelected(True)
    window._move_up_action.trigger()
    window._move_up_action.trigger()
    assert names(window) == ["sample.heic", "a.png", "b.jpg"]

    choose_format(window, OutputFormat.PDF)
    window.dock.merge.click()
    window.dock.name_chip.click()
    window.dock.name_popover.edit.setText("")
    QTest.keyClicks(window.dock.name_popover.edit, "My Album")
    window.dock.page_chip.click()
    window.dock.page_popover.choices[PageSize.ORIGINAL].click()
    window.dock.page_popover.margin.setValue(0)
    window.dock.page_popover.close()
    assert window.queue.numbered and shown(window, window.workspace.hint)
    convert(app, window)

    reader = PdfReader(tmp_path / "out" / "My Album.pdf")
    assert [(float(p.mediabox.width), float(p.mediabox.height)) for p in reader.pages] == \
        [(640, 480), (100, 50), (50, 100)]
    assert window.done.title.text() == "Saved “My Album.pdf”"


def test_end_to_end_jpeg_images_open(app, window, make, sample_heic, tmp_path):
    doc = text_pdf(tmp_path / "notes.pdf", ["a", "b"], size=(72, 72))
    window.add_paths([sample_heic, make("clear.png", (40, 30)), doc])
    choose_format(window, OutputFormat.JPEG)
    convert(app, window)
    assert outputs(tmp_path) == ["clear.jpg", "notes-page-1.jpg", "notes-page-2.jpg", "sample.jpg"]
    for name in outputs(tmp_path):
        with Image.open(tmp_path / "out" / name) as image:
            image.load()
            assert image.format == "JPEG"


# Every control changes the setting it claims to change

@pytest.fixture
def engine(monkeypatch):
    """Record what the window asks the engine to do, instead of converting."""
    calls = []

    def fake(name):
        def run(sources, target, settings, progress, cancelled):
            calls.append((name, list(sources), target, settings))
            return ConversionReport(outputs=[target])
        return run

    for name in ("convert_images", "convert_merged", "convert_individual", "convert_animated_gifs",
                 "convert_combined_gif"):
        monkeypatch.setattr(f"gui.model.{name}", fake(name))
    return calls


def run_once(app, window, engine):
    engine.clear()
    convert(app, window)
    window.done.back_button.click()
    return engine[-1]


def test_each_pdf_control_reaches_the_engine(app, window, make, engine, tmp_path):
    files = [make("a.png"), make("b.png")]
    window.add_paths(files)
    choose_format(window, OutputFormat.PDF)
    name, sources, target, settings = run_once(app, window, engine)
    assert (name, sources, target) == ("convert_individual", files, tmp_path / "out")

    window.dock.page_chip.click()
    window.dock.page_popover.choices[PageSize.LETTER].click()
    window.dock.page_popover.plus.click()
    window.dock.page_popover.close()
    assert window.dock.page_chip.value() == "US Letter · 11 mm"
    assert run_once(app, window, engine)[3].page_size is PageSize.LETTER
    assert engine[-1][3].margin_mm == 11

    window.dock.merge.click()
    name, _, target, _ = run_once(app, window, engine)
    assert (name, target) == ("convert_merged", tmp_path / "out" / "Combined.pdf")


def test_each_image_control_reaches_the_engine(app, window, make, engine, tmp_path):
    window.add_paths([make("a.png"), text_pdf(tmp_path / "doc.pdf", ["x"])])
    choose_format(window, OutputFormat.TIFF)
    assert not shown(window, window.dock.quality_chip) and shown(window, window.dock.dpi_chip)
    assert run_once(app, window, engine)[3].format is OutputFormat.TIFF

    choose_format(window, OutputFormat.WEBP)
    window.dock.quality_chip.click()
    window.dock.quality_popover.slider.setValue(42)
    window.dock.dpi_chip.click()
    window.dock.dpi_popover.choices[300].click()
    window.dock.dpi_popover.close()
    assert window.dock.quality_chip.value() == "42%" and window.dock.dpi_chip.value() == "300 DPI"
    settings = run_once(app, window, engine)[3]
    assert (settings.format, settings.quality, settings.pdf_dpi) == (OutputFormat.WEBP, 42, 300)


@pytest.mark.parametrize("fmt", list(OutputFormat))
def test_the_dock_shows_exactly_the_controls_for_the_format(window, make, tmp_path, fmt):
    window.add_paths([make("a.png"), make("b.png"), text_pdf(tmp_path / "doc.pdf", ["x"])])
    choose_format(window, fmt)
    dock = window.dock
    to_pdf = fmt is OutputFormat.PDF
    assert shown(window, dock.merge) == to_pdf and shown(window, dock.page_chip) == to_pdf
    assert shown(window, dock.quality_chip) == fmt.has_quality
    to_gif = fmt is OutputFormat.GIF
    assert shown(window, dock.dpi_chip) == (not to_pdf and not to_gif), "an animated GIF sizes frames instead"
    assert shown(window, dock.gif_mode_chip) == to_gif and shown(window, dock.animation_chip) == to_gif
    assert dock.convert_button.text() == f"Convert to {fmt.label}"
    if not to_pdf:
        expected = "Transparency is preserved." if fmt.keeps_alpha else "Transparent areas become white."
        assert dock.note.text() == expected
    featured = fmt in dock.formats.buttons
    assert (dock.formats.buttons[fmt] if featured else dock.formats.more).isChecked()
    assert dock.formats.more.text() == ("More" if featured else fmt.label)


def test_settings_are_remembered_between_launches(app, window, make, tmp_path):
    window.add_paths([make("a.png")])
    choose_format(window, OutputFormat.AVIF)
    window.dock.quality_chip.click()
    window.dock.quality_popover.slider.setValue(40)
    window.dock.quality_popover.close()
    window.close()
    again = MainWindow()
    assert again.options().format is OutputFormat.AVIF and again.options().quality == 40
    assert again.output_dir() == tmp_path / "out"
    again.deleteLater()


# Adding, reordering, and removing files

def test_duplicates_and_unsupported_files_are_explained(window, make, tmp_path):
    notes = [tmp_path / "notes.txt", tmp_path / "data.csv"]
    for note in notes:
        note.write_text("x")
    window.add_paths(notes[:1])
    assert window.state() == Welcome("1 file skipped because this format isn't supported.", True)
    assert shown(window, window.welcome.notice)

    a = make("a.png")
    window.add_paths([*notes, a])
    assert names(window) == ["a.png"]
    assert window.state().notice == "2 files skipped because this format isn't supported."
    window.add_paths([a])
    assert window.state() == Workspace("Those files are already in the list.", False)
    assert shown(window, window.workspace.banner)
    window.workspace.banner.close_button.click()
    assert not shown(window, window.workspace.banner)


def test_unreadable_file_is_flagged_with_a_friendly_reason(app, window, make, tmp_path):
    bad = tmp_path / "broken.heic"
    bad.write_bytes(b"not an image")
    window.add_paths([bad, make("fine.png")])
    wait_until(app, lambda: window.queue.state(0) is FileState.UNREADABLE)
    assert window.queue.reason(0) == "The file appears to be damaged."
    assert window.queue.state(1) is FileState.PENDING
    assert window.workspace.summary.text().endswith("· 1 can't be read")


def test_row_remove_button_removes_only_that_row(app, window, make):
    window.add_paths([make("a.png"), make("b.png"), make("c.png")])
    app.processEvents()
    viewport = window.queue.viewport()
    row = window.queue.visualItemRect(window.queue.item(1))
    button = QueueDelegate.remove_rect(QueueDelegate.row_rect(row)).center().toPoint()

    QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, row.center())
    assert names(window) == ["a.png", "b.png", "c.png"]
    QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, button)
    assert names(window) == ["a.png", "c.png"]

    QCoreApplication.sendEvent(viewport, QHelpEvent(QHelpEvent.Type.ToolTip, button, viewport.mapToGlobal(button)))
    assert QToolTip.text() == "Remove from list"


def test_backspace_removes_rows_only_while_the_list_has_focus(app, window, make):
    window.add_paths([make("a.png"), make("b.png")])
    window.activateWindow()
    window.queue.item(0).setSelected(True)
    window.dock.convert_button.setFocus()
    app.processEvents()
    assert not window._remove_action.isEnabled()

    window.queue.setFocus()
    app.processEvents()
    assert window._remove_action.isEnabled()
    QTest.keyClick(window.queue, Qt.Key.Key_Backspace)
    assert names(window) == ["b.png"]


def test_move_up_and_down_reorder_the_selection(window, make):
    window.add_paths([make("a.png"), make("b.png"), make("c.png")])
    window.queue.item(0).setSelected(True)
    window._move_down_action.trigger()
    assert names(window) == ["b.png", "a.png", "c.png"]
    window._move_up_action.trigger()
    assert names(window) == ["a.png", "b.png", "c.png"]


def test_rows_fit_the_list_after_the_window_shrinks(app, window, make):
    from gui.main_window import DEFAULT_SIZE, MINIMUM_SIZE

    window.add_paths([make("a.png")])
    for size in (DEFAULT_SIZE, (1280, 800), MINIMUM_SIZE):
        window.resize(*size)
        app.processEvents()
        assert window.queue.visualItemRect(window.queue.item(0)).width() == window.queue.viewport().width()


def test_two_hundred_files_load_thumbnails_off_the_gui_thread(app, window, make):
    window.add_paths([make(f"{i:03d}.png", (60, 40)) for i in range(200)])
    assert window.queue.count() == 200
    assert window.workspace.summary.text().startswith("200 files · ")
    wait_until(app, lambda: all(window.queue.thumbnail(str(p)) for p in window.queue.paths()))


# Where files are saved

def test_missing_folder_blocks_convert_and_says_why(window, make, tmp_path):
    window.add_paths([make("a.png")])
    window.set_output_dir(tmp_path / "gone")
    assert not window.dock.convert_button.isEnabled()
    assert window.dock.convert_button.toolTip() == "The Save to folder no longer exists. Choose another folder."
    assert window.dock.destination.value() == "Folder not found"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_unwritable_folder_blocks_convert(window, make, tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o555)
    try:
        window.add_paths([make("a.png")])
        window.set_output_dir(locked)
        assert not window.dock.convert_button.isEnabled()
        assert window.dock.destination.value() == "Folder isn't writable"
    finally:
        locked.chmod(0o755)


def test_folder_removed_after_choosing_it_is_caught_at_convert_time(window, make, tmp_path):
    target = tmp_path / "soon-gone"
    target.mkdir()
    window.add_paths([make("a.png")])
    window.set_output_dir(target)
    target.rmdir()
    window._convert_action.trigger()
    assert window.state() == Workspace("The Save to folder no longer exists. Choose another folder.", True)
    assert not window.dock.convert_button.isEnabled()


def test_destination_chip_picks_a_folder_and_remembers_it(window, make, tmp_path, monkeypatch):
    picked = tmp_path / "Picked"
    picked.mkdir()
    window.set_output_dir(tmp_path / "gone")
    monkeypatch.setattr("gui.main_window.QFileDialog.getExistingDirectory", lambda *a: str(picked))
    window.dock.destination.click()
    assert window.output_dir() == picked
    assert window.dock.destination.problem is None
    window.add_paths([make("a.png")])
    assert window.dock.convert_button.isEnabled()
    assert MainWindow().output_dir() == picked


def test_launch_falls_back_to_documents_when_the_saved_folder_is_gone(app, tmp_path):
    from PySide6.QtCore import QStandardPaths

    QSettings().clear()
    QSettings().setValue("output_dir", str(tmp_path / "deleted"))
    documents = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation))
    win = MainWindow()
    assert win.output_dir() == (documents if documents.is_dir() else Path.home())
    win.deleteLater()


def test_each_gif_control_reaches_the_engine(app, window, make, engine, tmp_path):
    files = [make("a.png"), make("b.png")]
    window.add_paths(files)
    choose_format(window, OutputFormat.GIF)
    dock = window.dock
    assert not shown(window, dock.animation_chip), "nothing animates until files are combined"
    assert run_once(app, window, engine)[0] == "convert_animated_gifs"

    dock.gif_mode_chip.click()
    dock.gif_mode_popover.choices[GifMode.COMBINE].click()
    dock.gif_mode_popover.close()
    assert shown(window, dock.animation_chip) and shown(window, dock.name_chip)
    assert dock.name_chip.value() == "Combined.gif"
    dock.animation_chip.click()
    popover = dock.animation_popover
    popover.durations[250].click()
    popover.play_once.click()
    popover.sizes[GifResolution.SMALL].click()
    popover.close()
    assert dock.animation_chip.value() == "250 ms · Plays once"
    name, sources, target, settings = run_once(app, window, engine)
    assert (name, sources, target) == ("convert_combined_gif", files, tmp_path / "out" / "Combined.gif")
    assert (settings.frame_ms, settings.plays, settings.resolution) == (250, 1, GifResolution.SMALL)

    dock.animation_chip.click()
    popover.custom_ms.setValue(333)
    popover.custom_plays.setValue(4)
    popover.close()
    assert dock.animation_chip.value() == "330 ms · Plays 4×", "GIF keeps hundredths of a second"
    settings = run_once(app, window, engine)[3]
    assert (settings.frame_ms, settings.plays) == (330, 4)

    dock.gif_mode_chip.click()
    dock.gif_mode_popover.choices[GifMode.SEPARATE].click()
    dock.gif_mode_popover.close()
    assert not shown(window, dock.animation_chip)
    name, _, _, settings = run_once(app, window, engine)
    assert name == "convert_images" and settings.format is OutputFormat.GIF


def test_combine_is_unavailable_for_one_file(app, window, tmp_path):
    window.add_paths([colored_pdf(tmp_path / "doc.pdf", TWELVE_COLORS[:2])])
    choose_format(window, OutputFormat.GIF)
    window.dock.gif_mode_chip.click()
    assert not window.dock.gif_mode_popover.choices[GifMode.COMBINE].isEnabled()
    window.dock.gif_mode_popover.close()


def test_a_twelve_page_pdf_converts_to_one_animated_gif_in_the_window(app, window, tmp_path):
    window.add_paths([FIXTURES / "twelve-pages.pdf"])
    choose_format(window, OutputFormat.GIF)
    convert(app, window)
    assert outputs(tmp_path) == ["twelve-pages.gif"]
    with Image.open(tmp_path / "out" / "twelve-pages.gif") as gif:
        assert gif.n_frames == 12 and gif.info["loop"] == 0
    assert window.done.subtitle.text() == f"1 GIF file saved to {tmp_path / 'out'}"


def test_combined_gif_says_so_when_done(app, window, make, tmp_path):
    window.add_paths([make("a.png", color="red"), make("b.png", color="blue")])
    choose_format(window, OutputFormat.GIF)
    window.dock.gif_mode_chip.click()
    window.dock.gif_mode_popover.choices[GifMode.COMBINE].click()
    window.dock.gif_mode_popover.close()
    assert window.queue.numbered and shown(window, window.workspace.hint), "rows show the frame order"
    convert(app, window)
    assert outputs(tmp_path) == ["Combined.gif"]
    with Image.open(tmp_path / "out" / "Combined.gif") as gif:
        assert gif.n_frames == 2
    assert window.done.title.text() == "Saved “Combined.gif”"
    assert window.done.subtitle.text() == f"2 files combined into one animated GIF in {tmp_path / 'out'}"


def test_replacing_an_existing_combined_gif_asks_first(app, window, make, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    (tmp_path / "out" / "Combined.gif").write_bytes(b"keep me")
    window.add_paths([make("a.png"), make("b.png")])
    choose_format(window, OutputFormat.GIF)
    window.dock.gif_mode_chip.click()
    window.dock.gif_mode_popover.choices[GifMode.COMBINE].click()
    window.dock.gif_mode_popover.close()
    monkeypatch.setattr("gui.main_window.QMessageBox.question", lambda *a: QMessageBox.StandardButton.No)
    window.dock.convert_button.click()
    assert not window.is_converting()
    assert (tmp_path / "out" / "Combined.gif").read_bytes() == b"keep me"


def test_replacing_an_existing_merged_pdf_asks_first(app, window, make, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    (tmp_path / "out" / "Combined.pdf").write_bytes(b"keep me")
    window.add_paths([make("a.png"), make("b.png")])
    window.dock.merge.click()
    monkeypatch.setattr("gui.main_window.QMessageBox.question", lambda *a: QMessageBox.StandardButton.No)
    window.dock.convert_button.click()
    assert not window.is_converting()
    assert (tmp_path / "out" / "Combined.pdf").read_bytes() == b"keep me"


# Shutdown

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
    win.dock.convert_button.click()
    thread = win._thread
    wait_until(app, lambda: win.state().current == "slow.png")  # the worker is inside the slow encode
    win.close()
    assert not thread.isRunning()
    assert list(tmp_path.glob("*.pdf")) == []  # cancelled before the PDF was written
    win.deleteLater()


# Menus, shortcuts, and files from the system

def menu_actions(window) -> dict[str, list[str]]:
    return {menu.title().replace("&", ""): [a.text() for a in menu.actions() if not a.isSeparator()]
            for menu in (a.menu() for a in window.menuBar().actions())}


def test_menus_and_shortcuts(window):
    from utils.reveal import REVEAL_LABEL

    assert menu_actions(window) == {
        "File": ["Add Files…", "Add Folder…", "Convert", "Cancel Conversion", REVEAL_LABEL, "Close Window", "Quit"],
        "Edit": ["Select All", "Remove Selected", "Move Up", "Move Down", "Clear All"],
        "Help": ["About Papyr"],
    }
    shortcuts = {
        window._add_files_action: QKeySequence(QKeySequence.StandardKey.Open),
        window._add_folder_action: QKeySequence("Ctrl+Shift+O"),
        window._convert_action: QKeySequence("Ctrl+Return"),
        window._cancel_action: QKeySequence(Qt.Key.Key_Escape),
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
    assert len(window.queue.selectedItems()) == 3
    window._clear_action.trigger()
    assert window.queue.count() == 0

    about = []
    monkeypatch.setattr("gui.main_window.QMessageBox.about", lambda parent, title, text: about.append(text))
    window._about_action.trigger()
    assert "Papyr 2.3.1" in about[0]

    window._close_action.trigger()
    assert not window.isVisible()


def test_select_all_in_the_name_field_selects_its_text_not_the_files(app, window, make):
    window.add_paths([make("a.png"), make("b.png")])
    window.dock.merge.click()
    window.dock.name_chip.click()
    edit = window.dock.name_popover.edit
    edit.setText("Trip Photos")
    QTest.keyClick(edit, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert edit.selectedText() == "Trip Photos"
    assert window.queue.selectedItems() == []
    window.dock.name_popover.close()


def test_finder_open_events_and_command_line_files_are_added(app, make):
    from gui.app import launch

    QSettings().clear()
    early = make("early.png")
    QCoreApplication.sendEvent(app, QFileOpenEvent(str(early)))  # before the window exists
    win = launch(app, ["papyr", "-psn_0_42", str(make("argv.png"))])
    try:
        assert names(win) == ["early.png", "argv.png"]
        QCoreApplication.sendEvent(app, QFileOpenEvent(str(make("later.png"))))
        assert names(win) == ["early.png", "argv.png", "later.png"]
    finally:
        app.set_path_handler(None)
        win.close()
        win.deleteLater()


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
def test_files_dropped_anywhere_on_the_window_are_added_with_drop_feedback(app, window, make, tmp_path):
    mime, point = drag_files(window.welcome, [make("a.png")])
    assert window.welcome.tile.active, "the drop target lights up"
    drop(window.welcome, mime, point)
    assert not window.welcome.tile.active
    assert names(window) == ["a.png"]

    mime, point = drag_files(window.dock, [make("b.png")])
    assert window._drop_overlay.isVisible()
    drop(window.dock, mime, point)
    assert not window._drop_overlay.isVisible()

    folder = tmp_path / "album"
    folder.mkdir()
    make("album/c.jpg")
    viewport = window.queue.viewport()
    mime, point = drag_files(viewport, [folder])
    drop(viewport, mime, point)
    assert names(window) == ["a.png", "b.png", "c.jpg"]


def test_tab_order_runs_list_settings_destination_format_convert(window, make):
    window.add_paths([make("a.png"), make("b.png")])
    dock = window.dock
    wanted = [window.workspace.add_files_button, window.queue, dock.merge, dock.page_chip, dock.destination,
              dock.formats.buttons[OutputFormat.PDF], dock.formats.more, dock.convert_button]
    order, widget = [], window.workspace.add_files_button
    for _ in range(300):
        if widget in wanted and widget not in order:
            order.append(widget)
        widget = widget.nextInFocusChain()
    assert order == wanted


# Motion

def test_reduced_motion_is_read_once_and_defaults_to_animating(monkeypatch):
    import subprocess

    from gui import motion

    def answer(stdout):
        return lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=stdout)

    for stdout, expected in (("1\n", False), ("0\n", True), ("", True)):
        motion.animations_enabled.cache_clear()
        monkeypatch.setattr(motion.sys, "platform", "darwin")
        monkeypatch.setattr(motion.subprocess, "run", answer(stdout))
        assert motion.animations_enabled() is expected

    def missing(*a, **k):
        raise FileNotFoundError("defaults")

    motion.animations_enabled.cache_clear()
    monkeypatch.setattr(motion.subprocess, "run", missing)
    assert motion.animations_enabled() is True
    motion.animations_enabled.cache_clear()
