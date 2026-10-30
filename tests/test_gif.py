"""GIF output, checked by reopening every GIF Papyr writes: frame count, order, size, timing, and looping."""
from pathlib import Path

import pytest
from PIL import Image, ImageSequence

from conftest import FIXTURES
from converter import (GifResolution, GifSettings, ImageSettings, OutputFormat, convert_animated_gifs,
                       convert_combined_gif, convert_images)
from pdf_samples import TWELVE_COLORS, colored_pdf

TWELVE_PAGES = FIXTURES / "twelve-pages.pdf"


def gif_frames(path: Path) -> list[tuple[Image.Image, dict]]:
    """Each frame as RGBA, with the metadata Pillow read for it."""
    with Image.open(path) as gif:
        assert gif.format == "GIF"
        return [(frame.convert("RGBA"), dict(frame.info)) for frame in ImageSequence.Iterator(gif)]


def loop_field(path: Path) -> int | None:
    with Image.open(path) as gif:
        return gif.info.get("loop")


def center(frame: Image.Image) -> tuple[int, int, int]:
    return frame.getpixel((frame.width // 2, frame.height // 2))[:3]


def close(actual, expected, tolerance=24) -> bool:
    return all(abs(a - e) <= tolerance for a, e in zip(actual, expected))


def out_names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def test_the_fixture_is_a_real_twelve_page_pdf():
    import pypdf
    assert len(pypdf.PdfReader(TWELVE_PAGES).pages) == 12


def test_a_twelve_page_pdf_becomes_one_gif_with_twelve_frames_in_page_order(tmp_path):
    out = tmp_path / "out"
    report = convert_animated_gifs([TWELVE_PAGES], out, GifSettings())
    assert report.failures == []
    assert out_names(out) == ["twelve-pages.gif"], "one file, not one per page"
    frames = gif_frames(out / "twelve-pages.gif")
    assert len(frames) == 12
    assert all(close(center(frame), color) for (frame, _), color in zip(frames, TWELVE_COLORS))
    assert loop_field(out / "twelve-pages.gif") == 0, "loops forever by default"
    assert {info["duration"] for _, info in frames} == {1000}


def test_a_single_page_pdf_becomes_a_one_frame_gif(tmp_path):
    source = colored_pdf(tmp_path / "flyer.pdf", [(0, 130, 200)])
    report = convert_animated_gifs([source], tmp_path / "out", GifSettings())
    assert report.outputs == [tmp_path / "out" / "flyer.gif"]
    frames = gif_frames(report.outputs[0])
    assert len(frames) == 1 and close(center(frames[0][0]), (0, 130, 200))


def test_separate_mode_writes_one_still_gif_per_page_with_padded_numbers(tmp_path):
    out = tmp_path / "out"
    report = convert_images([TWELVE_PAGES], out, ImageSettings(OutputFormat.GIF, pdf_dpi=72))
    assert report.failures == []
    assert out_names(out) == [f"twelve-pages-page-{n:03d}.gif" for n in range(1, 13)]
    for number, color in enumerate(TWELVE_COLORS, start=1):
        frames = gif_frames(out / f"twelve-pages-page-{number:03d}.gif")
        assert len(frames) == 1 and close(center(frames[0][0]), color)


def test_other_formats_keep_their_page_names(tmp_path):
    report = convert_images([TWELVE_PAGES], tmp_path / "out", ImageSettings(OutputFormat.PNG, pdf_dpi=36))
    assert report.outputs[0].name == "twelve-pages-page-1.png"


def test_images_combine_into_one_animation_in_queue_order(make, tmp_path):
    images = [make("c.png", (300, 200), "red"), make("a.jpg", (300, 200), "lime"), make("b.png", (300, 200), "blue")]
    destination = tmp_path / "out" / "Combined.gif"
    report = convert_combined_gif(images, destination, GifSettings(frame_ms=500))
    assert report.failures == [] and report.outputs == [destination]
    frames = gif_frames(destination)
    assert len(frames) == 3
    assert all(close(center(frame), color) for (frame, _), color in
               zip(frames, [(255, 0, 0), (0, 255, 0), (0, 0, 255)]))


def test_animate_each_never_combines_separate_images(make, tmp_path):
    images = [make("a.png", (300, 200), "red"), make("b.png", (300, 200), "blue")]
    report = convert_animated_gifs(images, tmp_path / "out", GifSettings())
    assert out_names(tmp_path / "out") == ["a.gif", "b.gif"]
    assert all(len(gif_frames(path)) == 1 for path in report.outputs)


def test_a_single_picture_keeps_its_own_size(make, tmp_path):
    big = make("big.png", (2400, 1200), "red")
    report = convert_animated_gifs([big], tmp_path / "out", GifSettings(resolution=GifResolution.SMALL))
    with Image.open(report.outputs[0]) as gif:
        assert gif.size == (2400, 1200)


def test_combining_pdf_pages_and_images_keeps_every_frame(make, tmp_path):
    pdf = colored_pdf(tmp_path / "two.pdf", [(230, 25, 75), (60, 180, 75)])
    picture = make("pic.png", (400, 300), "blue")
    report = convert_combined_gif([pdf, picture], tmp_path / "out" / "Mix.gif", GifSettings())
    frames = gif_frames(report.outputs[0])
    assert len(frames) == 3
    assert [close(center(frame), color) for (frame, _), color in
            zip(frames, [(230, 25, 75), (60, 180, 75), (0, 0, 255)])] == [True] * 3


@pytest.mark.parametrize("frame_ms", [250, 500, 1000, 2000, 330])
def test_every_frame_carries_the_chosen_duration(tmp_path, frame_ms):
    source = colored_pdf(tmp_path / "doc.pdf", TWELVE_COLORS[:3])
    report = convert_animated_gifs([source], tmp_path / "out", GifSettings(frame_ms=frame_ms))
    assert [info["duration"] for _, info in gif_frames(report.outputs[0])] == [frame_ms] * 3


@pytest.mark.parametrize("plays, loop", [(0, 0), (1, None), (3, 2)])
def test_loop_metadata_matches_the_number_of_plays(tmp_path, plays, loop):
    source = colored_pdf(tmp_path / "doc.pdf", TWELVE_COLORS[:2])
    report = convert_animated_gifs([source], tmp_path / "out", GifSettings(plays=plays))
    assert loop_field(report.outputs[0]) == loop


def test_identical_neighbouring_pages_stay_separate_frames(tmp_path):
    white = (255, 255, 255)
    source = colored_pdf(tmp_path / "blanks.pdf", [(230, 25, 75), white, white, white, (0, 130, 200)])
    report = convert_animated_gifs([source], tmp_path / "out", GifSettings(frame_ms=250))
    frames = gif_frames(report.outputs[0])
    assert len(frames) == 5
    assert [info["duration"] for _, info in frames] == [250] * 5


def test_pages_of_different_sizes_share_one_frame_size_and_keep_their_shape(tmp_path):
    portrait, landscape, small = (612, 792), (792, 612), (300, 300)
    colors = [(230, 25, 75), (60, 180, 75), (0, 130, 200)]
    source = colored_pdf(tmp_path / "mixed.pdf", colors, [portrait, landscape, small])
    report = convert_animated_gifs([source], tmp_path / "out", GifSettings(resolution=GifResolution.BALANCED))
    frames = gif_frames(report.outputs[0])
    assert {frame.size for frame, _ in frames} == {(1000, 1000)}
    for (frame, _), (width, height), color in zip(frames, [portrait, landscape, small], colors):
        mask = Image.eval(frame.convert("RGB"), lambda v: 255 if v < 250 else 0).convert("L")
        left, top, right, bottom = mask.getbbox()
        assert abs((right - left) / (bottom - top) - width / height) < 0.02, "aspect ratio kept"
        assert max(right - left, bottom - top) >= 998, "each page fills the frame along its long side"
        assert frame.getpixel((0, 0))[:3] == (255, 255, 255) or (width, height) == (300, 300)
        assert close(center(frame), color)


@pytest.mark.parametrize("resolution", list(GifResolution))
def test_frame_size_follows_the_resolution_choice(tmp_path, resolution):
    report = convert_animated_gifs([TWELVE_PAGES], tmp_path, GifSettings(resolution=resolution))
    with Image.open(report.outputs[0]) as gif:
        assert max(gif.size) == resolution.long_side
        assert abs(gif.width / gif.height - 612 / 792) < 0.01


def test_transparent_pictures_stay_transparent_in_a_combined_animation(tmp_path):
    clear = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    clear.paste((255, 0, 0, 255), (50, 50, 150, 150))
    clear.save(tmp_path / "clear.png")
    report = convert_combined_gif([tmp_path / "clear.png", tmp_path / "clear.png"], tmp_path / "out" / "a.gif",
                                  GifSettings())
    frames = gif_frames(report.outputs[0])
    assert len(frames) == 2
    for frame, _ in frames:
        assert frame.getpixel((10, 10))[3] == 0 and frame.getpixel((100, 100)) == (255, 0, 0, 255)


def test_a_corrupted_pdf_is_reported_and_leaves_nothing_behind(tmp_path):
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.7\nthis is not really a pdf")
    out = tmp_path / "out"
    out.mkdir()
    report = convert_animated_gifs([broken], out, GifSettings())
    assert report.outputs == [] and [path for path, _ in report.failures] == [broken]
    assert out_names(out) == [], "no GIF and no leftover temp file"


def test_a_corrupted_pdf_is_skipped_when_combining(make, tmp_path):
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"garbage")
    good = make("good.png", (300, 200), "blue")
    report = convert_combined_gif([broken, good], tmp_path / "out" / "a.gif", GifSettings())
    assert [path for path, _ in report.failures] == [broken]
    assert len(gif_frames(report.outputs[0])) == 1


def test_combining_nothing_readable_writes_nothing(tmp_path):
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"garbage")
    out = tmp_path / "out"
    report = convert_combined_gif([broken], out / "a.gif", GifSettings())
    assert report.outputs == [] and not (out / "a.gif").exists()


def test_existing_gifs_are_never_overwritten(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "twelve-pages.gif").write_bytes(b"keep me")
    report = convert_animated_gifs([TWELVE_PAGES], out, GifSettings())
    assert report.outputs == [out / "twelve-pages (1).gif"]
    assert (out / "twelve-pages.gif").read_bytes() == b"keep me"


def test_cancelling_mid_animation_removes_the_partial_gif(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    checks = iter(range(1000))
    report = convert_animated_gifs([TWELVE_PAGES], out, GifSettings(), cancelled=lambda: next(checks) > 5)
    assert report.cancelled and report.outputs == []
    assert out_names(out) == []


def test_progress_reports_each_file_when_combining(make, tmp_path):
    files = [make("a.png"), colored_pdf(tmp_path / "b.pdf", TWELVE_COLORS[:2]), make("c.png")]
    seen = []
    convert_combined_gif(files, tmp_path / "out" / "a.gif", GifSettings(),
                         progress=lambda done, total, path: seen.append((done, total, path.name)))
    assert seen == [(0, 3, "a.png"), (1, 3, "b.pdf"), (2, 3, "c.png"), (3, 3, "c.png")]


def test_cancelling_while_combining_writes_nothing(make, tmp_path):
    out = tmp_path / "out"
    report = convert_combined_gif([make("a.png"), make("b.png")], out / "a.gif", GifSettings(), cancelled=lambda: True)
    assert report.cancelled and report.outputs == [] and not out.exists()
