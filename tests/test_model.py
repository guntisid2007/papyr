from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

from converter import ConversionReport, OutputFormat, PageSize
from gui.model import (FORMAT_CONTROLS, Control, Converting, Options, Outcome, QueueSummary, RunResult,
                       controls_for, plan_job)

ONE = QueueSummary(count=1)
TWO = QueueSummary(count=2)
WITH_PDF = QueueSummary(count=2, has_document=True)


def test_every_format_has_a_row_in_the_controls_table():
    assert set(FORMAT_CONTROLS) == set(OutputFormat)


def test_pdf_shows_page_settings_and_merge_only_for_two_or_more_files():
    pdf = Options(OutputFormat.PDF)
    assert controls_for(pdf, ONE) == (Control.PAGE_SIZE, Control.MARGINS)
    assert controls_for(pdf, TWO) == (Control.MERGE, Control.PAGE_SIZE, Control.MARGINS)
    assert controls_for(pdf.with_(merge=True), TWO) == (Control.MERGE, Control.MERGED_NAME, Control.PAGE_SIZE,
                                                       Control.MARGINS)
    assert controls_for(pdf.with_(merge=True), ONE) == (Control.PAGE_SIZE, Control.MARGINS)


@pytest.mark.parametrize("fmt", [f for f in OutputFormat if f is not OutputFormat.PDF])
def test_image_formats_show_quality_only_where_the_encoder_has_one(fmt):
    expected_quality = fmt.label in {"JPEG", "HEIC", "WebP", "AVIF"}
    assert (Control.QUALITY in controls_for(Options(fmt), TWO)) == expected_quality
    assert Control.PDF_DPI not in controls_for(Options(fmt), TWO)
    assert Control.PDF_DPI in controls_for(Options(fmt), WITH_PDF)
    assert not {Control.MERGE, Control.PAGE_SIZE, Control.MARGINS} & set(controls_for(Options(fmt), WITH_PDF))


def test_merging_needs_two_files(tmp_path):
    options = Options(OutputFormat.PDF, merge=True, merged_name="Album")
    assert options.merges(TWO) and not options.merges(ONE)
    assert not options.with_(format=OutputFormat.JPEG).merges(TWO)
    sources = [tmp_path / "a.png", tmp_path / "b.png"]
    merged = plan_job(options, TWO, sources, tmp_path)
    assert merged.func.__name__ == "convert_merged" and merged.args[1] == tmp_path / "Album.pdf"
    single = plan_job(options, ONE, sources[:1], tmp_path)
    assert single.func.__name__ == "convert_individual"


def test_merged_name_is_made_safe_and_defaults_to_combined():
    assert Options(merged_name="").merged_file_name() == "Combined.pdf"
    assert Options(merged_name="Trip: day 1/2").merged_file_name() == "Trip_ day 1_2.pdf"
    assert Options(merged_name="report.pdf").merged_file_name() == "report.pdf"


def test_options_round_trip_and_ignore_bad_saved_values(app, tmp_path):
    settings = QSettings(str(tmp_path / "prefs.ini"), QSettings.Format.IniFormat)
    chosen = Options(OutputFormat.WEBP, True, "Album", PageSize.LETTER, 25, 40, 300)
    chosen.save(settings)
    assert Options.load(settings) == chosen

    settings.setValue("output_format", "DOCX")
    settings.setValue("pdf_dpi", 123)
    settings.setValue("margin_mm", 400)
    settings.setValue("page_size", "Tabloid")
    loaded = Options.load(settings)
    assert (loaded.format, loaded.pdf_dpi, loaded.margin_mm, loaded.page_size) == (OutputFormat.PDF, 200, 50,
                                                                                    PageSize.A4)


def result(report: ConversionReport, sources, merged=False) -> RunResult:
    return RunResult.from_report(report, sources, OutputFormat.PDF, merged, Path("/out"))


def test_failed_sources_are_the_queued_files_that_failed_in_queue_order():
    a, b, c = Path("a.png"), Path("b.png"), Path("c.png")
    partial = result(ConversionReport(outputs=[Path("/out/a.pdf")],
                                      failures=[(c, "No such file"), (b, "cannot identify image file")]), [a, b, c])
    assert partial.outcome is Outcome.PARTIAL
    assert partial.failed_sources == (b, c)
    assert partial.converted_count == 1
    assert [f.reason for f in partial.failures] == ["The file was moved or deleted.", "The file appears to be damaged."]
    assert result(ConversionReport(outputs=[Path("/out/a.pdf")]), [a]).outcome is Outcome.SUCCESS


def test_a_run_level_failure_leaves_every_file_unconverted():
    a, b = Path("a.png"), Path("b.png")
    broken = result(ConversionReport(failures=[(Path("/out/All.pdf"), "[Errno 28] No space left on device")]),
                    [a, b], merged=True)
    assert broken.outcome is Outcome.FAILED
    assert broken.failed_sources == (a, b)
    assert broken.failures[0].reason == "There isn't enough free space on the disk."


def test_converting_counts_what_is_left():
    assert Converting(total=10, done=3).remaining == 7
