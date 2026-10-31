"""Animated GIF and WebP inputs: animation formats keep every frame, its timing, and its plays; still formats take
the first frame, or every frame when asked, under predictable names."""
from pathlib import Path

import pytest
from PIL import Image

import converter.images as images
from converter import (GifSettings, ImageSettings, OutputFormat, PdfSettings, convert_animated_gifs,
                       convert_combined_gif, convert_images, convert_individual)
from converter.images import animation_timing, is_animated
from pdf_samples import text_pdf
from utils.errors import friendly_error
from validators import mae, parse_gif, pdf_facts

pytestmark = pytest.mark.animation

COLORS = [(220, 40, 40), (40, 160, 60), (40, 80, 220), (230, 200, 30)]
DURATIONS = [100, 300, 50, 1000]


def frames_of(colors=COLORS, size=(80, 60)) -> list[Image.Image]:
    frames = []
    for index, color in enumerate(colors):
        frame = Image.new("RGB", size, color)
        frame.paste((255, 255, 255), (5 + 10 * index, 5, 15 + 10 * index, 15))
        frames.append(frame)
    return frames


def animation(path: Path, durations=DURATIONS, loop: int | None = 0, **options) -> Path:
    frames = frames_of(COLORS[:len(durations)])
    if loop is not None:
        options["loop"] = loop
    if path.suffix == ".webp":
        options.setdefault("lossless", True)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=list(durations), **options)
    return path


def read(path: Path) -> tuple[list[Image.Image], list[int], int | None]:
    """(frames as shown, durations, the file's loop value). Durations are read after decoding: WebP needs that."""
    with Image.open(path) as image:
        frames, durations = [], []
        for index in range(getattr(image, "n_frames", 1)):
            image.seek(index)
            frames.append(image.convert("RGBA"))
            durations.append(image.info.get("duration"))
        loop = image.info.get("loop")
    if path.suffix == ".gif":
        info = parse_gif(path)
        return frames, info.delays_ms, info.loop
    return frames, durations, loop


def assert_same_frames(got: list[Image.Image], source: Path, tolerance: float = 3.0) -> None:
    want, _, _ = read(source)
    assert len(got) == len(want)
    for number, (a, b) in enumerate(zip(got, want), start=1):
        assert a.size == b.size, f"frame {number}"
        assert mae(a, b) < tolerance, f"frame {number} differs by {mae(a, b):.1f}"


@pytest.mark.parametrize("source_ext", [".gif", ".webp"])
def test_animation_becomes_animated_webp_with_its_timing(tmp_path, source_ext):
    source = animation(tmp_path / f"clip{source_ext}")
    report = convert_images([source], tmp_path / "out", ImageSettings(OutputFormat.WEBP, quality=100))
    assert [p.name for p in report.outputs] == ["clip.webp"] and not report.failures
    frames, durations, loop = read(report.outputs[0])
    assert durations == DURATIONS and loop == 0
    assert_same_frames(frames, source)


@pytest.mark.parametrize("source_ext", [".gif", ".webp"])
def test_animation_becomes_animated_gif_with_its_timing(tmp_path, source_ext):
    source = animation(tmp_path / f"clip{source_ext}")
    report = convert_animated_gifs([source], tmp_path / "out", GifSettings(frame_ms=2000))
    assert [p.name for p in report.outputs] == ["clip.gif"] and not report.failures
    frames, durations, loop = read(report.outputs[0])
    assert durations == DURATIONS, "the source's own timing, not the page duration setting"
    assert loop == 0
    assert_same_frames(frames, source, tolerance=6.0)


@pytest.mark.parametrize("loop, plays", [(None, 1), (0, 0), (2, 3)], ids=["once", "forever", "three-times"])
def test_plays_survive_gif_to_webp_to_gif(tmp_path, loop, plays):
    gif = animation(tmp_path / "clip.gif", loop=loop)
    assert animation_timing(gif).plays == plays
    [webp] = convert_images([gif], tmp_path / "webp", ImageSettings(OutputFormat.WEBP)).outputs
    assert animation_timing(webp).plays == plays
    [back] = convert_animated_gifs([webp], tmp_path / "gif", GifSettings(plays=0)).outputs
    assert parse_gif(back).loop == loop


@pytest.mark.parametrize("source_ext", [".gif", ".webp"])
def test_a_single_frame_file_stays_a_still_picture(tmp_path, source_ext):
    source = tmp_path / f"still{source_ext}"
    Image.new("RGB", (40, 30), "teal").save(source)
    assert animation_timing(source) is None and not is_animated(source)
    [webp] = convert_images([source], tmp_path / "webp", ImageSettings(OutputFormat.WEBP)).outputs
    [gif] = convert_animated_gifs([source], tmp_path / "gif", GifSettings()).outputs
    assert [p.name for p in (tmp_path / "webp").iterdir()] == ["still.webp"]
    for out in (webp, gif):
        with Image.open(out) as image:
            assert getattr(image, "n_frames", 1) == 1 and image.size == (40, 30)


@pytest.mark.parametrize("fmt", [OutputFormat.PNG, OutputFormat.JPEG, OutputFormat.BMP, OutputFormat.GIF])
def test_still_formats_take_the_first_frame_unless_every_frame_is_asked(tmp_path, fmt):
    source = animation(tmp_path / "clip.gif")
    first = convert_images([source], tmp_path / "first", ImageSettings(fmt))
    assert [p.name for p in first.outputs] == [f"clip{fmt.extension}"]
    every = convert_images([source], tmp_path / "every", ImageSettings(fmt, every_frame=True))
    assert [p.name for p in every.outputs] == [f"clip-frame-{n:03d}{fmt.extension}" for n in range(1, 5)]
    want, _, _ = read(source)
    for out, frame in zip(every.outputs, want):
        with Image.open(out) as image:
            assert getattr(image, "n_frames", 1) == 1
            assert mae(image.convert("RGBA"), frame) < 6.0, out.name


def test_every_frame_names_sort_in_play_order_past_999_frames(tmp_path, monkeypatch):
    source = animation(tmp_path / "clip.gif")
    real = images.animation_timing
    monkeypatch.setattr("converter.convert.animation_timing",
                        lambda path: images.Timing(real(path).durations * 300, 0, (80, 60)))
    report = convert_images([source], tmp_path / "out", ImageSettings(OutputFormat.PNG, every_frame=True))
    assert report.outputs[0].name == "clip-frame-0001.png"


def test_pdf_gets_a_page_per_frame_only_when_asked(tmp_path):
    source = animation(tmp_path / "clip.webp")
    [one] = convert_individual([source], tmp_path / "one", PdfSettings()).outputs
    [every] = convert_individual([source], tmp_path / "every", PdfSettings(every_frame=True)).outputs
    assert pdf_facts(one).pages == 1 and pdf_facts(every).pages == 4


def test_transparency_and_disposal_come_through_as_shown(tmp_path):
    """Frame 2 is cleared to the background before it is drawn (disposal 2), frame 3 draws over frame 2 (disposal
    1), and frame 3 itself only covers part of the picture."""
    size = (60, 40)
    first = Image.new("RGBA", size, (0, 0, 0, 0))
    first.paste((255, 0, 0, 255), (0, 0, 30, 40))
    second = Image.new("RGBA", size, (0, 0, 0, 0))
    second.paste((0, 0, 255, 255), (30, 0, 60, 40))
    third = second.copy()
    third.paste((0, 200, 0, 255), (0, 10, 20, 30))
    source = tmp_path / "layers.gif"
    first.save(source, save_all=True, append_images=[second, third], duration=[200, 200, 200], loop=0,
               disposal=[2, 1, 1])
    want, _, _ = read(source)
    assert want[0].getpixel((45, 20))[3] == 0, "the fixture starts with a clear right half"

    [webp] = convert_images([source], tmp_path / "webp", ImageSettings(OutputFormat.WEBP, quality=100)).outputs
    [gif] = convert_animated_gifs([source], tmp_path / "gif", GifSettings()).outputs
    for out in (webp, gif):
        got, _, _ = read(out)
        assert len(got) == 3
        for number, (a, b) in enumerate(zip(got, want), start=1):
            for point in ((10, 5), (45, 20), (10, 20), (50, 35)):
                pa, pb = a.getpixel(point), b.getpixel(point)
                assert (pa[3] > 127) == (pb[3] > 127), f"{out.name} frame {number} alpha at {point}: {pa} vs {pb}"
                if pb[3] > 127:
                    assert max(abs(x - y) for x, y in zip(pa[:3], pb[:3])) < 30, f"{out.name} frame {number}"


def test_frames_stored_as_smaller_rectangles_come_out_full_size(tmp_path):
    """Pillow stores a GIF frame that changes a small area as just that rectangle."""
    base = Image.new("RGB", (100, 80), (200, 200, 200))
    frames = []
    for index in range(4):
        frame = base.copy()
        frame.paste(COLORS[index], (10 + 20 * index, 30, 25 + 20 * index, 45))
        frames.append(frame)
    source = tmp_path / "sprites.gif"
    frames[0].save(source, save_all=True, append_images=frames[1:], duration=100, loop=0)
    [webp] = convert_images([source], tmp_path / "out", ImageSettings(OutputFormat.WEBP, quality=100)).outputs
    got, durations, _ = read(webp)
    assert [f.size for f in got] == [(100, 80)] * 4 and durations == [100] * 4
    assert_same_frames(got, source)


def test_a_combined_gif_keeps_each_animations_timing(tmp_path):
    clip = animation(tmp_path / "clip.webp")
    doc = text_pdf(tmp_path / "doc.pdf", ["one", "two"])
    [out] = convert_combined_gif([doc, clip], tmp_path / "All.gif", GifSettings(frame_ms=700)).outputs
    assert parse_gif(out).delays_ms == [700, 700] + DURATIONS


def test_a_damaged_animation_writes_nothing(tmp_path):
    source = animation(tmp_path / "clip.gif")
    data = source.read_bytes()
    source.write_bytes(data[:len(data) * 2 // 3])
    for report, folder in ((convert_images([source], tmp_path / "webp", ImageSettings(OutputFormat.WEBP)), "webp"),
                           (convert_animated_gifs([source], tmp_path / "gif", GifSettings()), "gif")):
        assert report.outputs == [] and len(report.failures) == 1, report
        assert not list((tmp_path / folder).glob("*")) if (tmp_path / folder).exists() else True


def test_an_animation_too_large_for_memory_is_refused_by_name(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "MAX_ANIMATION_PIXELS", 1000)
    report = convert_images([animation(tmp_path / "clip.gif")], tmp_path / "out", ImageSettings(OutputFormat.WEBP))
    assert [friendly_error(r) for _, r in report.failures] == ["This image is too large to convert safely."]


def test_identical_frames_in_a_webp_keep_the_total_time(tmp_path):
    """libwebp folds a frame identical to the one before it into that frame's duration. What plays is the same."""
    red, blue = Image.new("RGB", (40, 30), "red"), Image.new("RGB", (40, 30), "blue")
    source = tmp_path / "hold.gif"
    red.save(source, save_all=True, append_images=[red, blue], duration=[200, 300, 400], loop=0)
    [webp] = convert_images([source], tmp_path / "out", ImageSettings(OutputFormat.WEBP)).outputs
    frames, durations, _ = read(webp)
    assert durations == [500, 400]
    assert mae(frames[0], red.convert("RGBA")) < 3 and mae(frames[1], blue.convert("RGBA")) < 3
