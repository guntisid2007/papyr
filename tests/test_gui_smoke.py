"""Conversions driven through the real window the way a person does it: files dropped on the window, a format picked
from the dock, Convert clicked, the Done page read. Every output is then checked by the same independent validation
the matrix uses. The window runs on Qt's offscreen platform, so this proves the window's wiring, not native drag
and drop from Finder or Explorer."""
import pytest
from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtGui import QColor, QPalette

from conftest import FIXTURES
from conversion_matrix import Result, targets, validate
from converter import ConversionReport, OutputFormat, PageSize
from gui.model import Converting, GifMode, Outcome
from test_gui import choose_format, convert, drag_files, drop, wait_until, window  # noqa: F401  (window is a fixture)

pytestmark = [pytest.mark.gui_smoke, pytest.mark.filterwarnings("ignore:Function.*QDragEnterEvent:DeprecationWarning")]
OFFERED = [t for t in targets() if t.offered]


def drop_onto(window, paths):  # noqa: F811
    mime, point = drag_files(window.welcome if window.queue.count() == 0 else window.dock, paths)
    drop(window.welcome if window.queue.count() == 0 else window.dock, mime, point)
    QThreadPool.globalInstance().waitForDone()


def pick(window, target):  # noqa: F811
    choose_format(window, target.format)
    if target.format is OutputFormat.GIF:
        window.dock.gif_mode_popover.choices[target.gif_mode].click()
        window.dock.gif_mode_popover.close()


def check_outputs(spec, target, window, out_dir):
    result = window.state().result
    report = ConversionReport(list(result.outputs), [(f.path, f.detail) for f in result.failures])
    on_disk = sorted(p for p in out_dir.rglob("*") if p.is_file())
    problems, facts = validate(spec, target, report, out_dir, on_disk, [(1, 1)])
    assert not problems, problems
    return facts


@pytest.mark.parametrize("target", OFFERED, ids=[t.key for t in OFFERED])
@pytest.mark.parametrize("fixture", ["heic-exif-rotated", "pdf-mixed-content", "notebook-matrix", "tiff-multipage"])
def test_a_dropped_file_converts_through_the_window(app, window, fixture_specs, tmp_path, fixture, target):  # noqa: F811
    spec = fixture_specs[fixture]
    drop_onto(window, [spec.path()])
    assert [p.name for p in window.queue.paths()] == [spec.file_name]
    pick(window, target)
    convert(app, window)
    assert window.state().result.outcome is Outcome.SUCCESS, window.state().result.failures
    check_outputs(spec, target, window, tmp_path / "out")
    assert "saved to" in window.done.subtitle.text()


def test_options_chosen_in_the_dock_reach_the_file(app, window, fixture_specs, tmp_path):  # noqa: F811
    drop_onto(window, [fixture_specs["png-landscape"].path(), fixture_specs["png-portrait"].path()])
    choose_format(window, OutputFormat.PDF)
    window.dock.merge.click()
    window.dock.page_chip.click()
    window.dock.page_popover.choices[PageSize.LETTER].click()
    window.dock.page_popover.margin.setValue(0)
    window.dock.page_popover.close()
    convert(app, window)
    from validators import pdf_facts
    facts = pdf_facts(tmp_path / "out" / "Combined.pdf")
    assert facts.sizes == [(792.0, 612.0), (612.0, 792.0)] and facts.images == [[(640, 400)], [(360, 540)]]


def test_a_notebook_in_dark_mode_converts_with_visible_text(app, window, fixture_specs, tmp_path):  # noqa: F811
    light = app.palette()
    dark = QPalette(light)
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText):
        dark.setColor(role, QColor(255, 255, 255, 216))
    app.setPalette(dark)
    try:
        spec = fixture_specs["notebook-matrix"]
        drop_onto(window, [spec.path()])
        choose_format(window, OutputFormat.PDF)
        convert(app, window)
        check_outputs(spec, next(t for t in OFFERED if t.key == "PDF"), window, tmp_path / "out")
    finally:
        app.setPalette(light)


def test_a_damaged_pdf_in_the_queue_does_not_cost_the_other_files(app, window, fixture_specs, tmp_path):  # noqa: F811
    data = bytearray(fixture_specs["pdf-twelve-pages"].path().read_bytes())
    data[len(data) // 3:len(data) // 3 + 2000] = b"\x00" * 2000
    damaged = tmp_path / "damaged.pdf"
    damaged.write_bytes(bytes(data))
    drop_onto(window, [damaged, fixture_specs["png-landscape"].path(), FIXTURES / "restricted-aes-128.pdf"])
    choose_format(window, OutputFormat.PNG)
    convert(app, window)
    result = window.state().result
    assert "png-landscape.png" in [p.name for p in result.outputs], result
    assert [f.reason for f in result.failures] == ["The file appears to be damaged."]
    assert window.done.retry_button.isVisible()

    window.done.back_button.click()
    choose_format(window, OutputFormat.PDF)
    convert(app, window)
    result = window.state().result
    assert "png-landscape.pdf" in [p.name for p in result.outputs], result
    assert all(f.reason != "This file couldn't be converted." for f in result.failures), result.failures
    rows = [window.done.failures.item(i).data(Qt.ItemDataRole.AccessibleTextRole)
            for i in range(window.done.failures.count())]
    assert rows and all(":" in row for row in rows)


def test_retry_after_fixing_the_file_converts_it(app, window, fixture_specs, tmp_path):  # noqa: F811
    broken = tmp_path / "later.heic"
    broken.write_bytes(fixture_specs["heic-landscape"].path().read_bytes()[:500])
    drop_onto(window, [broken, fixture_specs["jpeg-portrait"].path()])
    choose_format(window, OutputFormat.AVIF)
    convert(app, window)
    assert window.state().result.outcome is Outcome.PARTIAL
    broken.write_bytes(fixture_specs["heic-landscape"].path().read_bytes())
    window.done.retry_button.click()
    assert [p.name for p in window.queue.paths()] == ["later.heic"]
    convert(app, window)
    assert window.state().result.outcome is Outcome.SUCCESS
    names = sorted(p.name for p in (tmp_path / "out").iterdir())
    assert names == ["jpeg-portrait.avif", "later.avif"]


def test_progress_reports_every_file_and_ends_at_the_total(app, window, fixture_specs, tmp_path):  # noqa: F811
    paths = [fixture_specs[n].path() for n in ("png-landscape", "pdf-single-text", "gif-portrait", "bmp-tiny")]
    drop_onto(window, paths)
    choose_format(window, OutputFormat.JPEG)
    window.dock.convert_button.click()
    states = []
    wait_until(app, lambda: states.append(window.state()) or not window.is_converting())
    converting = [state for state in states if isinstance(state, Converting)]
    assert converting and {state.total for state in converting} == {4}
    assert [state.done for state in converting] == sorted(state.done for state in converting)
    assert window.state().result.converted_count == 4


def test_separate_static_gifs_only_when_chosen_in_the_window(app, window, tmp_path):  # noqa: F811
    drop_onto(window, [FIXTURES / "twelve-pages.pdf"])
    choose_format(window, OutputFormat.GIF)
    convert(app, window)
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["twelve-pages.gif"]
    window.done.back_button.click()
    window.dock.gif_mode_popover.choices[GifMode.SEPARATE].click()
    window.dock.gif_mode_popover.close()
    convert(app, window)
    assert len(list((tmp_path / "out").glob("twelve-pages-page-*.gif"))) == 12
