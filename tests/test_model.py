from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

from converter import ConversionReport, GifResolution, OutputFormat, PageSize
from gui.model import (FORMAT_CONTROLS, Control, Converting, GifMode, Options, Outcome, QueueSummary, RunResult,
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


@pytest.mark.parametrize("fmt", [f for f in OutputFormat if f not in (OutputFormat.PDF, OutputFormat.GIF)])
def test_image_formats_show_quality_only_where_the_encoder_has_one(fmt):
    expected_quality = fmt.label in {"JPEG", "HEIC", "WebP", "AVIF"}
    assert (Control.QUALITY in controls_for(Options(fmt), TWO)) == expected_quality
    assert Control.PDF_DPI not in controls_for(Options(fmt), TWO)
    assert Control.PDF_DPI in controls_for(Options(fmt), WITH_PDF)
    assert not {Control.MERGE, Control.PAGE_SIZE, Control.MARGINS} & set(controls_for(Options(fmt), WITH_PDF))


ONE_PDF = QueueSummary(count=1, has_document=True)
TIMING = (Control.FRAME_MS, Control.PLAYS, Control.GIF_RESOLUTION)


def test_gif_shows_animation_settings_only_when_there_is_something_to_animate():
    gif = Options(OutputFormat.GIF)
    assert controls_for(gif, ONE) == ()
    assert controls_for(gif, TWO) == (Control.GIF_MODE,), "two pictures are not combined unless asked"
    assert controls_for(gif, ONE_PDF) == (Control.GIF_MODE, *TIMING)
    assert controls_for(gif, WITH_PDF) == (Control.GIF_MODE, *TIMING)
    assert controls_for(gif.with_(gif_mode=GifMode.COMBINE), TWO) == (Control.GIF_MODE, Control.MERGED_NAME, *TIMING)
    assert controls_for(gif.with_(gif_mode=GifMode.COMBINE), ONE_PDF) == (Control.GIF_MODE, *TIMING)
    assert controls_for(gif.with_(gif_mode=GifMode.SEPARATE), WITH_PDF) == (Control.GIF_MODE, Control.PDF_DPI)


def test_gif_mode_picks_the_engine_call(tmp_path):
    sources = [tmp_path / "a.pdf", tmp_path / "b.png"]
    gif = Options(OutputFormat.GIF, merged_name="Story", frame_ms=250, plays=3,
                  gif_resolution=GifResolution.SMALL)
    each = plan_job(gif, WITH_PDF, sources, tmp_path)
    assert each.func.__name__ == "convert_animated_gifs" and each.args[1] == tmp_path
    assert (each.args[2].frame_ms, each.args[2].plays, each.args[2].resolution) == (250, 3, GifResolution.SMALL)
    combined = plan_job(gif.with_(gif_mode=GifMode.COMBINE), WITH_PDF, sources, tmp_path)
    assert combined.func.__name__ == "convert_combined_gif" and combined.args[1] == tmp_path / "Story.gif"
    assert plan_job(gif.with_(gif_mode=GifMode.COMBINE), ONE_PDF, sources[:1], tmp_path).func.__name__ == \
        "convert_animated_gifs"
    separate = plan_job(gif.with_(gif_mode=GifMode.SEPARATE), WITH_PDF, sources, tmp_path)
    assert separate.func.__name__ == "convert_images" and separate.args[2].format is OutputFormat.GIF


def test_combining_gifs_is_its_own_choice_not_the_pdf_merge():
    assert not Options(OutputFormat.GIF, merge=True).merges(TWO)
    assert Options(OutputFormat.GIF, gif_mode=GifMode.COMBINE).merges(TWO)
    assert not Options(OutputFormat.PDF, gif_mode=GifMode.COMBINE).merges(TWO)


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
    assert Options(OutputFormat.GIF).merged_file_name() == "Combined.gif"
    assert Options(OutputFormat.GIF, merged_name="story.gif").merged_file_name() == "story.gif"


def test_options_round_trip_and_ignore_bad_saved_values(app, tmp_path):
    settings = QSettings(str(tmp_path / "prefs.ini"), QSettings.Format.IniFormat)
    chosen = Options(OutputFormat.WEBP, True, "Album", PageSize.LETTER, 25, 40, 300, GifMode.COMBINE, 330, 4,
                     GifResolution.HIGH)
    chosen.save(settings)
    assert Options.load(settings) == chosen

    settings.setValue("output_format", "DOCX")
    settings.setValue("pdf_dpi", 123)
    settings.setValue("margin_mm", 400)
    settings.setValue("page_size", "Tabloid")
    settings.setValue("quality", "high")
    settings.setValue("gif_mode", "SIDEWAYS")
    settings.setValue("gif_frame_ms", 3)
    settings.setValue("gif_plays", "lots")
    settings.setValue("gif_resolution", "HUGE")
    loaded = Options.load(settings)
    assert (loaded.format, loaded.pdf_dpi, loaded.margin_mm, loaded.page_size, loaded.quality) == \
        (OutputFormat.PDF, 200, 50, PageSize.A4, 90)
    assert (loaded.gif_mode, loaded.frame_ms, loaded.plays, loaded.gif_resolution) == \
        (GifMode.ANIMATE_EACH, 20, 0, GifResolution.BALANCED)
    settings.setValue("gif_frame_ms", "333")
    assert Options.load(settings).frame_ms == 330 and isinstance(Options.load(settings).frame_ms, int)


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


def test_a_merged_pdf_that_overwrites_a_queued_file_and_fails_leaves_every_file_unconverted():
    combined, photo = Path("/out/Combined.pdf"), Path("/out/photo.png")
    failed = result(ConversionReport(failures=[(combined, "[Errno 1] Operation not permitted")]),
                    [combined, photo], merged=True)
    assert failed.failed_sources == (combined, photo)
    assert failed.converted_count == 0


def test_converting_counts_what_is_left():
    assert Converting(total=10, done=3).remaining == 7
