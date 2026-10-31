"""What conversions do beyond format pairs: page sequences and their order, one animation per document, many files
at once, and every setting the window offers, each checked on the files written."""
from pathlib import Path

import pypdf
import pytest
from PIL import Image

from conversion_matrix import A4, notebook_pages
from converter import (GifResolution, GifSettings, ImageSettings, OutputFormat, PageSize, PdfSettings,
                       convert_animated_gifs, convert_combined_gif, convert_images, convert_individual,
                       convert_merged)
from fixture_factory import PAGE_COLORS, canonical, flatten
from validators import (band_color, color_distance, gif_frames, ink, is_solid, mae, parse_gif, pdf_facts, pdf_render,
                        second_decoder, sniff)

pytestmark = pytest.mark.usefixtures("app")


def path_of(fixture_specs, name):
    return fixture_specs[name].path()


def assert_valid_picture(path, fmt: str):
    assert sniff(path) == fmt, f"{path.name} is {sniff(path)}"
    with Image.open(path) as image:
        image.load()
        assert not is_solid(image), f"{path.name} is one flat colour"
        size = image.size
    decoder, other = second_decoder(path, fmt)
    assert other in (None, size), f"{decoder} decodes {path.name} as {other}, Pillow as {size}"


# Multi-page sources

@pytest.mark.pdf
@pytest.mark.parametrize("fmt, sniffed", [(OutputFormat.PNG, "PNG"), (OutputFormat.JPEG, "JPEG"),
                                          (OutputFormat.WEBP, "WEBP"), (OutputFormat.TIFF, "TIFF")])
def test_a_pdf_becomes_one_picture_per_page_in_page_order(fixture_specs, tmp_path, fmt, sniffed):
    report = convert_images([path_of(fixture_specs, "pdf-twelve-pages")], tmp_path, ImageSettings(fmt, 90, 72))
    assert not report.failures
    names = [p.name for p in report.outputs]
    assert names == [f"pdf-twelve-pages-page-{n}{fmt.extension}" for n in range(1, 13)]
    for number, path in enumerate(report.outputs):
        assert_valid_picture(path, sniffed)
        with Image.open(path) as image:
            seen = band_color(image)
        assert color_distance(seen, PAGE_COLORS[number]) <= 40, f"{path.name} shows page colour {seen}"


@pytest.mark.pdf
def test_pdf_to_webp_writes_still_pages_not_an_animation(fixture_specs, tmp_path):
    report = convert_images([path_of(fixture_specs, "pdf-mixed-content")], tmp_path,
                            ImageSettings(OutputFormat.WEBP, 80, 72))
    assert len(report.outputs) == 7
    for path in report.outputs:
        with Image.open(path) as image:
            assert getattr(image, "n_frames", 1) == 1


@pytest.mark.animation
@pytest.mark.pdf
def test_twelve_page_pdf_becomes_one_animated_gif_with_twelve_frames_and_no_stray_files(fixture_specs, tmp_path):
    report = convert_animated_gifs([path_of(fixture_specs, "pdf-twelve-pages")], tmp_path, GifSettings())
    assert [p.name for p in report.outputs] == ["pdf-twelve-pages.gif"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["pdf-twelve-pages.gif"], "no separate static GIFs"
    info = parse_gif(report.outputs[0])
    assert info.frames == 12 and info.delays_ms == [1000] * 12 and info.loop == 0
    frames = gif_frames(report.outputs[0])
    for number, frame in enumerate(frames):
        rgb = frame.convert("RGB")
        hits = [sum(1 for p in rgb.resize((100, 100)).get_flattened_data() if color_distance(p, c) <= 30) for c in PAGE_COLORS]
        assert hits.index(max(hits)) == number, f"frame {number + 1} shows page {hits.index(max(hits)) + 1}"


@pytest.mark.animation
def test_separate_static_gifs_only_when_asked(fixture_specs, tmp_path):
    report = convert_images([path_of(fixture_specs, "pdf-twelve-pages")], tmp_path,
                            ImageSettings(OutputFormat.GIF, pdf_dpi=72))
    assert [p.name for p in report.outputs] == [f"pdf-twelve-pages-page-{n:03d}.gif" for n in range(1, 13)]
    for path in report.outputs:
        assert parse_gif(path).frames == 1


@pytest.mark.animation
def test_combined_gif_holds_every_page_of_every_file_in_queue_order(fixture_specs, tmp_path):
    sources = [path_of(fixture_specs, n) for n in ("tiff-multipage", "png-landscape", "pdf-single-text")]
    report = convert_combined_gif(sources, tmp_path / "All.gif", GifSettings(frame_ms=250))
    assert not report.failures
    info = parse_gif(tmp_path / "All.gif")
    assert info.frames == 3 + 1 + 1 and set(info.delays_ms) == {250}
    frames = [frame.convert("RGB").resize((200, 200)) for frame in gif_frames(tmp_path / "All.gif")]

    def share(frame, color):
        return sum(1 for p in frame.get_flattened_data() if color_distance(p, color) <= 30) / (200 * 200)
    for number in range(3):
        assert share(frames[number], PAGE_COLORS[number]) > 0.02 and ink(frames[number]) > 0.5, \
            f"frame {number + 1} is not TIFF page {number + 1}"
    assert ink(frames[3]) > 0.5 and max(share(frames[3], c) for c in PAGE_COLORS[:3]) < 0.005, "frame 4 is not the PNG"
    assert ink(frames[4]) < 0.25 and share(frames[4], PAGE_COLORS[0]) > 0.02, "frame 5 is not the text PDF"


@pytest.mark.pdf
def test_pictures_merge_into_one_pdf_in_order_with_pixels_intact(fixture_specs, tmp_path):
    names = ["png-landscape", "jpeg-portrait", "heic-landscape", "avif-portrait", "tiff-multipage", "gif-landscape",
             "bmp-portrait", "webp-landscape"]
    report = convert_merged([path_of(fixture_specs, n) for n in names], tmp_path / "Album.pdf", PdfSettings())
    assert not report.failures
    facts = pdf_facts(tmp_path / "Album.pdf")
    expected = [fixture_specs[n].pages for n in names]
    flat = [page for pages in expected for page in pages]
    assert facts.pages == len(flat) == 10
    assert [images for images in facts.images] == [[tuple(map(int, p.size))] for p in flat]
    for index, page in enumerate(flat):
        landscape = page.size[0] > page.size[1]
        assert facts.sizes[index] == pytest.approx((A4[1], A4[0]) if landscape else A4, abs=0.5)
        assert ink(pdf_render(tmp_path / "Album.pdf", index, 36)) > 0.05


@pytest.mark.pdf
def test_pdfs_and_notebooks_merge_with_their_text_searchable(fixture_specs, tmp_path):
    sources = [path_of(fixture_specs, "pdf-mixed-content"), path_of(fixture_specs, "notebook-short"),
               path_of(fixture_specs, "png-tiny")]
    report = convert_merged(sources, tmp_path / "Mixed.pdf", PdfSettings())
    assert not report.failures
    facts = pdf_facts(tmp_path / "Mixed.pdf")
    text = "\n".join(facts.texts)
    order = [text.find(m) for m in ("PAGE_001", "PAGE_006", "NB_TITLE", "SAVED_OUTPUT_01")]
    assert -1 not in order and order == sorted(order)
    assert facts.images[-1] == [(24, 16)]


def test_a_multipage_tiff_becomes_three_files_three_pages_or_three_frames(fixture_specs, tmp_path):
    tiff = path_of(fixture_specs, "tiff-multipage")
    pngs = convert_images([tiff], tmp_path / "png", ImageSettings(OutputFormat.PNG))
    assert [p.name for p in pngs.outputs] == [f"tiff-multipage-page-{n}.png" for n in (1, 2, 3)]
    sizes = [Image.open(p).size for p in pngs.outputs]
    assert sizes == [(500, 350), (300, 450), (420, 420)]
    pdf = convert_individual([tiff], tmp_path / "pdf", PdfSettings())
    assert pdf_facts(pdf.outputs[0]).pages == 3
    gif = convert_animated_gifs([tiff], tmp_path / "gif", GifSettings())
    info = parse_gif(gif.outputs[0])
    assert info.frames == 3 and (info.width, info.height) == (500, 450)


# Many files at once

def _batch(tmp_path, count: int, fmt: str = "png"):
    folder = tmp_path / f"batch-{count}"
    folder.mkdir()
    files = []
    for i in range(count):
        image = flatten(canonical((160 + i, 120), f"#{i}", False)).convert("RGB")
        path = folder / f"photo-{i:03d}.{fmt}"
        image.save(path)
        files.append(path)
    return files


@pytest.mark.batch
@pytest.mark.parametrize("count", [1, 10, 50])
def test_batches_convert_every_file(tmp_path, count):
    files = _batch(tmp_path, count)
    out = tmp_path / "out"
    report = convert_images(files, out, ImageSettings(OutputFormat.JPEG, 85))
    assert not report.failures and len(report.outputs) == count
    for source, output in zip(files, report.outputs):
        assert output.name == source.with_suffix(".jpg").name
        with Image.open(output) as image, Image.open(source) as original:
            assert image.size == original.size and mae(image, original) < 8
    pdfs = convert_individual(files, tmp_path / "pdf", PdfSettings())
    assert len(pdfs.outputs) == count and all(pdf_facts(p).pages == 1 for p in pdfs.outputs)


@pytest.mark.batch
def test_a_mixed_batch_of_every_input_format(fixture_specs, tmp_path):
    names = ["heic-landscape", "heif-portrait", "jpeg-landscape", "png-portrait", "webp-landscape", "avif-landscape",
             "tiff-multipage", "bmp-landscape", "gif-portrait", "pdf-single-text", "notebook-short"]
    report = convert_images([path_of(fixture_specs, n) for n in names], tmp_path, ImageSettings(OutputFormat.PNG))
    assert not report.failures
    notebook = notebook_pages(fixture_specs["notebook-short"], "image")
    assert len(report.outputs) == 8 + 3 + 1 + notebook
    for path in report.outputs:
        assert_valid_picture(path, "PNG")


@pytest.mark.batch
def test_same_names_from_different_folders_never_overwrite_each_other(tmp_path, make):
    (tmp_path / "x").mkdir()
    (tmp_path / "y").mkdir()
    a = make("x/a.png", color="red")
    b = make("y/a.png", color="blue")
    c = make("a.jpg", color="green")
    out = tmp_path / "out"
    pdfs = convert_individual([a, b, c], out, PdfSettings())
    assert [p.name for p in pdfs.outputs] == ["a.pdf", "a (1).pdf", "a (2).pdf"]
    pngs = convert_images([a, b, c], out, ImageSettings(OutputFormat.PNG))
    assert [p.name for p in pngs.outputs] == ["a.png", "a (1).png", "a (2).png"]
    colors = [Image.open(p).convert("RGB").getpixel((5, 5)) for p in pngs.outputs]
    assert colors[0][0] > 200 and colors[1][2] > 200 and colors[2][1] > 100


@pytest.mark.batch
def test_converting_again_keeps_the_first_results_and_existing_files(tmp_path, make):
    source = make("photo.png")
    out = tmp_path / "out"
    out.mkdir()
    precious = out / "photo.jpg"
    precious.write_bytes(b"the user's own file")
    first = convert_images([source], out, ImageSettings(OutputFormat.JPEG))
    second = convert_images([source], out, ImageSettings(OutputFormat.JPEG))
    assert [p.name for p in first.outputs + second.outputs] == ["photo (1).jpg", "photo (2).jpg"]
    assert precious.read_bytes() == b"the user's own file"
    pdf_one = convert_individual([source], out, PdfSettings())
    pdf_two = convert_individual([source], out, PdfSettings())
    assert [p.name for p in pdf_one.outputs + pdf_two.outputs] == ["photo.pdf", "photo (1).pdf"]


@pytest.mark.batch
def test_unreadable_files_in_a_batch_are_reported_and_the_rest_convert(fixture_specs, tmp_path):
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"\xff\xd8\xff not really a jpeg")
    notebook = tmp_path / "bad.ipynb"
    notebook.write_text("{ not json")
    good = [path_of(fixture_specs, "png-landscape"), path_of(fixture_specs, "pdf-single-text")]
    sources = [good[0], broken, notebook, good[1]]
    report = convert_merged(sources, tmp_path / "Merged.pdf", PdfSettings())
    assert [p.name for p, _ in report.failures] == ["broken.jpg", "bad.ipynb"]
    assert pdf_facts(tmp_path / "Merged.pdf").pages == 2
    images = convert_images(sources, tmp_path / "png", ImageSettings(OutputFormat.PNG))
    assert sorted(p.name for p in images.outputs) == ["pdf-single-text.png", "png-landscape.png"]
    assert {p.name for p, _ in images.failures} == {"broken.jpg", "bad.ipynb"}


# Settings reach the file

@pytest.mark.settings
def test_jpeg_quality_trades_size_for_fidelity(fixture_specs, tmp_path):
    source = path_of(fixture_specs, "png-hires")
    sizes, errors = {}, {}
    for quality in (20, 60, 95):
        out = convert_images([source], tmp_path / str(quality), ImageSettings(OutputFormat.JPEG, quality)).outputs[0]
        sizes[quality] = out.stat().st_size
        with Image.open(out) as image, Image.open(source) as original:
            errors[quality] = mae(image, original, 1024)
    assert sizes[20] < sizes[60] < sizes[95]
    assert errors[20] > errors[60] > errors[95]


@pytest.mark.settings
@pytest.mark.parametrize("fmt", [OutputFormat.WEBP, OutputFormat.AVIF, OutputFormat.HEIC])
def test_quality_changes_lossy_output_size(fixture_specs, tmp_path, fmt):
    source = path_of(fixture_specs, "png-landscape")
    low = convert_images([source], tmp_path / "low", ImageSettings(fmt, 30)).outputs[0].stat().st_size
    high = convert_images([source], tmp_path / "high", ImageSettings(fmt, 95)).outputs[0].stat().st_size
    assert low < high


@pytest.mark.settings
def test_webp_at_quality_100_is_lossless(fixture_specs, tmp_path):
    source = path_of(fixture_specs, "png-landscape")
    out = convert_images([source], tmp_path, ImageSettings(OutputFormat.WEBP, 100)).outputs[0]
    with Image.open(out) as image, Image.open(source) as original:
        assert list(image.convert("RGBA").get_flattened_data()) == list(original.convert("RGBA").get_flattened_data())


@pytest.mark.settings
def test_tiff_output_is_deflate_compressed(fixture_specs, tmp_path):
    out = convert_images([path_of(fixture_specs, "png-landscape")], tmp_path,
                         ImageSettings(OutputFormat.TIFF)).outputs[0]
    with Image.open(out) as image:
        assert image.info["compression"] == "tiff_adobe_deflate"


@pytest.mark.settings
@pytest.mark.pdf
@pytest.mark.parametrize("page, portrait", [(PageSize.A4, A4), (PageSize.LETTER, (612.0, 792.0))])
def test_page_size_and_orientation(fixture_specs, tmp_path, page, portrait):
    sources = [path_of(fixture_specs, "png-landscape"), path_of(fixture_specs, "png-portrait")]
    report = convert_merged(sources, tmp_path / "out.pdf", PdfSettings(page, 10))
    sizes = pdf_facts(tmp_path / "out.pdf").sizes
    assert sizes[0] == pytest.approx((portrait[1], portrait[0]), abs=0.5)
    assert sizes[1] == pytest.approx(portrait, abs=0.5)
    assert not report.failures


@pytest.mark.settings
@pytest.mark.pdf
def test_original_page_size_is_the_picture_plus_margins(fixture_specs, tmp_path):
    convert_merged([path_of(fixture_specs, "png-landscape")], tmp_path / "o.pdf", PdfSettings(PageSize.ORIGINAL, 5))
    margin = 5 * 72 / 25.4
    assert pdf_facts(tmp_path / "o.pdf").sizes[0] == pytest.approx((640 + 2 * margin, 400 + 2 * margin), abs=0.5)


@pytest.mark.settings
@pytest.mark.pdf
def test_margins_leave_a_blank_border_of_that_width(fixture_specs, tmp_path):
    source = path_of(fixture_specs, "png-portrait")
    convert_merged([source], tmp_path / "0.pdf", PdfSettings(PageSize.A4, 0))
    page = pdf_render(tmp_path / "0.pdf", 0, 72).convert("L")
    assert page.crop((page.width // 2 - 5, 0, page.width // 2 + 5, 3)).getextrema()[0] < 250, \
        "with no margin a picture narrower than A4 reaches the top edge"
    convert_merged([source], tmp_path / "25.pdf", PdfSettings(PageSize.A4, 25))
    page = pdf_render(tmp_path / "25.pdf", 0, 72).convert("L")
    border = round(25 * 72 / 25.4) - 2
    for strip in (page.crop((0, 0, border, page.height)), page.crop((page.width - border, 0, page.width, page.height)),
                  page.crop((0, 0, page.width, border)), page.crop((0, page.height - border, page.width, page.height))):
        assert strip.getextrema()[0] >= 250, "ink inside the 25 mm margin"


@pytest.mark.settings
def test_impossible_margins_fail_with_a_reason(fixture_specs, tmp_path):
    report = convert_merged([path_of(fixture_specs, "png-tiny")], tmp_path / "x.pdf", PdfSettings(PageSize.A4, 200))
    assert report.failures and "leaves no room" in report.failures[0][1]
    assert not (tmp_path / "x.pdf").exists()


@pytest.mark.settings
@pytest.mark.pdf
@pytest.mark.parametrize("dpi", [100, 150, 300])
def test_pdf_resolution_sets_picture_size(fixture_specs, tmp_path, dpi):
    out = convert_images([path_of(fixture_specs, "pdf-single-text")], tmp_path,
                         ImageSettings(OutputFormat.PNG, pdf_dpi=dpi)).outputs[0]
    with Image.open(out) as image:
        assert image.size == pytest.approx((595.28 * dpi / 72, 841.89 * dpi / 72), abs=2)


@pytest.mark.settings
@pytest.mark.animation
@pytest.mark.parametrize("plays, loop", [(0, 0), (1, None), (3, 2)])
def test_gif_timing_and_loop_count(fixture_specs, tmp_path, plays, loop):
    report = convert_animated_gifs([path_of(fixture_specs, "pdf-mixed-content")], tmp_path,
                                   GifSettings(frame_ms=250, plays=plays))
    info = parse_gif(report.outputs[0])
    assert info.frames == 7 and set(info.delays_ms) == {250} and info.loop == loop


@pytest.mark.settings
@pytest.mark.animation
@pytest.mark.parametrize("resolution", list(GifResolution))
def test_gif_frame_size_follows_the_resolution_choice(fixture_specs, tmp_path, resolution):
    report = convert_animated_gifs([path_of(fixture_specs, "pdf-twelve-pages")], tmp_path,
                                   GifSettings(resolution=resolution))
    info = parse_gif(report.outputs[0])
    assert max(info.width, info.height) == resolution.long_side


@pytest.mark.settings
def test_photo_location_and_camera_metadata_are_never_copied(tmp_path):
    exif = Image.Exif()
    exif[0x010F] = "PapyrCam"
    exif[0x8825] = {1: "N", 2: (40.0, 26.0, 46.0)}
    source = tmp_path / "gps.jpg"
    flatten(canonical((200, 150), "gps", False)).convert("RGB").save(source, exif=exif.tobytes())
    for fmt in (OutputFormat.JPEG, OutputFormat.PNG, OutputFormat.WEBP, OutputFormat.HEIC, OutputFormat.TIFF):
        out = convert_images([source], tmp_path / fmt.name, ImageSettings(fmt)).outputs[0]
        assert b"PapyrCam" not in out.read_bytes(), f"{fmt.label} kept camera metadata"
    pdf = convert_individual([source], tmp_path / "pdf", PdfSettings()).outputs[0]
    assert b"PapyrCam" not in pdf.read_bytes()


def test_transparency_survives_in_formats_that_have_it_and_turns_white_elsewhere(fixture_specs, tmp_path):
    source = path_of(fixture_specs, "png-landscape")
    for fmt in OutputFormat:
        if fmt is OutputFormat.PDF:
            continue
        out = convert_images([source], tmp_path / fmt.name, ImageSettings(fmt, 90)).outputs[0]
        with Image.open(out) as image:
            pixel = image.convert("RGBA").getpixel((int(0.77 * 640), int(0.26 * 400)))
        if fmt.keeps_alpha:
            assert pixel[3] <= 10, f"{fmt.label} lost transparency: {pixel}"
        else:
            assert min(pixel[:3]) >= 230 and pixel[3] == 255, f"{fmt.label} transparency became {pixel}"


def test_missing_settings_are_documented_not_faked():
    """Papyr has no resize option for still pictures and no PNG compression level; the GIF frame size is the only
    scaling control. If one is added, this test fails so the matrix and report learn about it. EVERY_FRAME is
    covered by tests/test_animation_formats.py and the beta-readiness report."""
    from gui.model import Control
    assert {c.name for c in Control} == {"MERGE", "MERGED_NAME", "PAGE_SIZE", "MARGINS", "QUALITY", "PDF_DPI",
                                         "GIF_MODE", "FRAME_MS", "PLAYS", "GIF_RESOLUTION", "EVERY_FRAME"}


def _notebook_with(tmp_path, cells) -> Path:
    import json
    path = tmp_path / "figure.ipynb"
    path.write_text(json.dumps({"nbformat": 4, "nbformat_minor": 4, "metadata": {}, "cells": cells}))
    return path


RED_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="120"><rect width="300" height="120" fill="#e00000"/></svg>'


@pytest.mark.notebook
def test_an_svg_attached_to_a_markdown_cell_is_drawn(tmp_path):
    notebook = _notebook_with(tmp_path, [{"cell_type": "markdown", "metadata": {},
                                          "source": "Figure: ![chart](attachment:chart.svg)",
                                          "attachments": {"chart.svg": {"image/svg+xml": RED_SVG}}}])
    pdf = convert_individual([notebook], tmp_path / "out", PdfSettings()).outputs[0]
    page = pdf_render(pdf, 0, 72).convert("RGB")
    red = sum(1 for p in page.get_flattened_data() if color_distance(p, (224, 0, 0)) <= 40)
    assert red > 2000, f"the attached SVG is missing ({red} red pixels)"


@pytest.mark.notebook
def test_a_figure_with_an_absurd_saved_width_still_fits_the_page(tmp_path):
    import base64
    import io
    figure = io.BytesIO()
    Image.new("RGB", (120, 60), (224, 0, 0)).save(figure, "PNG")
    notebook = _notebook_with(tmp_path, [{"cell_type": "code", "execution_count": 1, "metadata": {}, "source": "plot()",
                                          "outputs": [{"output_type": "display_data",
                                                       "metadata": {"image/png": {"width": 10 ** 400}},
                                                       "data": {"image/png": base64.b64encode(figure.getvalue()).decode()}}]}])
    good = tmp_path / "next.png"
    Image.new("RGB", (40, 30), "blue").save(good)
    report = convert_individual([notebook, good], tmp_path / "out", PdfSettings())
    assert [p.name for p in report.outputs] == ["figure.pdf", "next.pdf"] and not report.failures, report
    assert pdf_facts(report.outputs[0]).images[0] == [(120, 60)]
