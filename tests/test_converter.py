import io
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader

from converter import (ImageLoadError, PageSize, PdfSettings, convert_individual, convert_merged,
                       load_image)
from converter.layout import MM_TO_PT

ORIGINAL = PdfSettings(PageSize.ORIGINAL, margin_mm=0)
A4_W, A4_H = PageSize.A4.dimensions
LETTER_W, LETTER_H = PageSize.LETTER.dimensions


def page_size(page) -> tuple[float, float]:
    return float(page.mediabox.width), float(page.mediabox.height)


def placed_rect(page) -> tuple[float, float, float, float]:
    """Return (width, height, x, y) from the page's 'w 0 0 h x y cm' image matrix."""
    tokens = page.get_contents().get_data().decode().split()
    i = tokens.index("cm")
    w, _, _, h, x, y = map(float, tokens[i - 6:i])
    return w, h, x, y


def page_image(page) -> Image.Image:
    return Image.open(io.BytesIO(page.images[0].data)).convert("RGB")


def assert_close_color(actual, expected, tolerance=40):
    assert all(abs(a - e) <= tolerance for a, e in zip(actual, expected)), (actual, expected)


def test_heic_decodes_to_upright_rgb(sample_heic):
    image = load_image(sample_heic)
    assert image.size == (640, 480)
    assert image.mode == "RGB"
    assert_close_color(image.getpixel((320, 10)), (255, 0, 0))
    assert_close_color(image.getpixel((320, 470)), (0, 0, 255))


def test_heic_converts_to_pdf_with_content_intact(sample_heic, tmp_path):
    report = convert_merged([sample_heic], tmp_path / "out.pdf", ORIGINAL)
    assert report.failures == []
    page = PdfReader(tmp_path / "out.pdf").pages[0]
    assert page_size(page) == (640, 480)
    image = page_image(page)
    assert_close_color(image.getpixel((320, 10)), (255, 0, 0))
    assert_close_color(image.getpixel((320, 470)), (0, 0, 255))


@pytest.mark.parametrize("name", ["photo.jpg", "photo.jpeg", "photo.png", "PHOTO.JPG", "shot.heif"])
def test_supported_formats_convert(make, tmp_path, name):
    source = make(name, (300, 200), "green")
    report = convert_individual([source], tmp_path / "out", ORIGINAL)
    assert report.failures == [] and len(report.outputs) == 1
    page = PdfReader(report.outputs[0]).pages[0]
    assert page_size(page) == (300, 200)
    assert_close_color(page_image(page).getpixel((150, 100)), (0, 128, 0))


def test_png_transparency_is_flattened_onto_white(tmp_path):
    source = tmp_path / "alpha.png"
    Image.new("RGBA", (50, 50), (0, 0, 0, 0)).save(source)
    report = convert_merged([source], tmp_path / "out.pdf", ORIGINAL)
    assert_close_color(page_image(PdfReader(report.outputs[0]).pages[0]).getpixel((25, 25)), (255, 255, 255), 2)


@pytest.mark.parametrize("mode", ["L", "LA", "P", "I;16", "1", "CMYK"])
def test_unusual_color_modes_convert(tmp_path, mode):
    source = tmp_path / f"img_{mode.replace(';', '')}.{'jpg' if mode == 'CMYK' else 'png'}"
    Image.new(mode, (40, 30)).save(source)
    report = convert_merged([source], tmp_path / "out.pdf", ORIGINAL)
    assert report.failures == []
    assert len(PdfReader(report.outputs[0]).pages) == 1


def test_individual_mode_writes_one_pdf_per_image_named_after_source(make, tmp_path):
    sources = [make("IMG_0001.heic"), make("IMG_0002.jpg"), make("holiday.png")]
    out_dir = tmp_path / "pdfs"
    report = convert_individual(sources, out_dir, PdfSettings())
    assert [p.name for p in report.outputs] == ["IMG_0001.pdf", "IMG_0002.pdf", "holiday.pdf"]
    for output in report.outputs:
        assert len(PdfReader(output).pages) == 1


def test_individual_mode_never_overwrites(make, tmp_path):
    out_dir = tmp_path / "pdfs"
    out_dir.mkdir()
    (out_dir / "photo.pdf").write_bytes(b"existing")
    sources = [make("photo.heic"), make("photo.jpg")]
    report = convert_individual(sources, out_dir, PdfSettings())
    assert [p.name for p in report.outputs] == ["photo (1).pdf", "photo (2).pdf"]
    assert (out_dir / "photo.pdf").read_bytes() == b"existing"


def test_merged_mode_preserves_order(make, tmp_path):
    sizes = [(100, 50), (60, 90), (300, 30), (77, 77)]
    sources = [make(f"{chr(ord('d') - i)}.png", size) for i, size in enumerate(sizes)]
    report = convert_merged(sources, tmp_path / "merged.pdf", ORIGINAL)
    pages = PdfReader(report.outputs[0]).pages
    assert [page_size(p) for p in pages] == sizes


def test_merged_mode_mixes_formats(make, sample_heic, tmp_path):
    sources = [sample_heic, make("b.jpg"), make("c.png")]
    report = convert_merged(sources, tmp_path / "merged.pdf", PdfSettings(PageSize.LETTER))
    assert len(PdfReader(report.outputs[0]).pages) == 3


@pytest.mark.parametrize("page, size, expected", [
    (PageSize.A4, (300, 400), (A4_W, A4_H)),
    (PageSize.A4, (400, 300), (A4_H, A4_W)),
    (PageSize.LETTER, (300, 400), (LETTER_W, LETTER_H)),
    (PageSize.LETTER, (400, 300), (LETTER_H, LETTER_W)),
    (PageSize.LETTER, (300, 300), (LETTER_W, LETTER_H)),
])
def test_page_sizes_and_auto_orientation(make, tmp_path, page, size, expected):
    report = convert_merged([make("a.png", size)], tmp_path / "out.pdf", PdfSettings(page, 10))
    assert page_size(PdfReader(report.outputs[0]).pages[0]) == pytest.approx(expected, abs=0.01)


def test_original_size_adds_margins(make, tmp_path):
    report = convert_merged([make("a.png", (200, 100))], tmp_path / "o.pdf", PdfSettings(PageSize.ORIGINAL, 10))
    margin = 10 * MM_TO_PT
    page = PdfReader(report.outputs[0]).pages[0]
    assert page_size(page) == pytest.approx((200 + 2 * margin, 100 + 2 * margin), abs=0.01)
    assert placed_rect(page) == pytest.approx((200, 100, margin, margin), abs=0.01)


@pytest.mark.parametrize("size", [(4032, 3024), (3024, 4032), (1000, 100), (50, 2000), (10, 10)])
@pytest.mark.parametrize("margin_mm", [0, 12.5, 40])
def test_aspect_ratio_preserved_and_image_fits_inside_margins(make, tmp_path, size, margin_mm):
    report = convert_merged([make("a.jpg", size)], tmp_path / "o.pdf", PdfSettings(PageSize.A4, margin_mm))
    page = PdfReader(report.outputs[0]).pages[0]
    page_w, page_h = page_size(page)
    w, h, x, y = placed_rect(page)
    margin = margin_mm * MM_TO_PT
    assert w / h == pytest.approx(size[0] / size[1], rel=1e-3)
    assert x >= margin - 0.01 and y >= margin - 0.01
    assert x + w <= page_w - margin + 0.01 and y + h <= page_h - margin + 0.01
    assert min(x, y) == pytest.approx(margin, abs=0.01)  # scaled to touch the margin on one axis
    assert (x - (page_w - x - w), y - (page_h - y - h)) == pytest.approx((0, 0), abs=0.01)


def test_margin_larger_than_page_is_reported(make, tmp_path):
    report = convert_merged([make("a.png")], tmp_path / "o.pdf", PdfSettings(PageSize.A4, 200))
    assert report.outputs == [] and "margin" in report.failures[0][1]
    assert list(tmp_path.glob("*.pdf")) == [] and list(tmp_path.glob(".*.part")) == []


@pytest.mark.parametrize("orientation, expected_size, top_color", [
    (1, (200, 100), (255, 0, 0)),
    (3, (200, 100), (0, 0, 255)),
    (6, (100, 200), (255, 0, 0)),
    (8, (100, 200), (0, 0, 255)),
])
def test_exif_orientation_is_applied(tmp_path, orientation, expected_size, top_color):
    """The stored pixels are 200x100: left half red, right half blue."""
    image = Image.new("RGB", (200, 100), "blue")
    image.paste((255, 0, 0), (0, 0, 100, 100))
    exif = Image.Exif()
    exif[0x0112] = orientation
    source = tmp_path / f"o{orientation}.jpg"
    image.save(source, exif=exif.tobytes())

    report = convert_merged([source], tmp_path / "o.pdf", ORIGINAL)
    page = PdfReader(report.outputs[0]).pages[0]
    assert page_size(page) == expected_size
    embedded = page_image(page)
    assert embedded.size == expected_size
    if orientation in (6, 8):
        assert_close_color(embedded.getpixel((50, 10)), top_color)
    else:
        assert_close_color(embedded.getpixel((10, 50)), top_color)


def test_photo_metadata_is_not_embedded(tmp_path):
    exif = Image.Exif()
    exif[0x010F] = "SecretCameraMaker"
    source = tmp_path / "gps.jpg"
    Image.new("RGB", (40, 40)).save(source, exif=exif.tobytes())
    report = convert_merged([source], tmp_path / "o.pdf", ORIGINAL)
    assert b"SecretCameraMaker" not in report.outputs[0].read_bytes()


@pytest.mark.parametrize("name, content", [
    ("broken.heic", b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64),
    ("notreally.jpg", b"this is a text file"),
    ("empty.png", b""),
])
def test_corrupted_files_raise_clear_error(tmp_path, name, content):
    path = tmp_path / name
    path.write_bytes(content)
    with pytest.raises(ImageLoadError):
        load_image(path)


def test_unsupported_extension_rejected(tmp_path):
    path = tmp_path / "doc.gif"
    Image.new("RGB", (10, 10)).save(path)
    with pytest.raises(ImageLoadError, match="Unsupported"):
        load_image(path)


def test_merge_skips_bad_files_and_reports_them(make, tmp_path):
    bad = tmp_path / "bad.heic"
    bad.write_bytes(b"garbage")
    sources = [make("a.png", (10, 20)), bad, make("c.png", (30, 40))]
    report = convert_merged(sources, tmp_path / "m.pdf", ORIGINAL)
    assert [p for p, _ in report.failures] == [bad]
    assert [page_size(p) for p in PdfReader(report.outputs[0]).pages] == [(10, 20), (30, 40)]


def test_merge_with_no_readable_files_leaves_nothing_behind(tmp_path):
    bad = tmp_path / "bad.heic"
    bad.write_bytes(b"garbage")
    report = convert_merged([bad], tmp_path / "out" / "m.pdf", ORIGINAL)
    assert report.outputs == [] and len(report.failures) == 2
    assert [p.name for p in (tmp_path / "out").iterdir()] == []


def test_individual_continues_after_bad_file(make, tmp_path):
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"garbage")
    report = convert_individual([bad, make("good.png")], tmp_path / "out", ORIGINAL)
    assert [p.name for p in report.outputs] == ["good.pdf"]
    assert report.failures[0][0] == bad


def test_cancel_during_merge_removes_partial_file(make, tmp_path):
    sources = [make(f"{i}.png") for i in range(5)]
    calls = []
    report = convert_merged(sources, tmp_path / "out" / "m.pdf", ORIGINAL,
                            progress=lambda done, total, path: calls.append(done),
                            cancelled=lambda: len(calls) >= 2)
    assert report.cancelled and report.outputs == []
    assert list((tmp_path / "out").iterdir()) == []


def test_cancel_during_individual_keeps_finished_files(make, tmp_path):
    sources = [make(f"{i}.png") for i in range(5)]
    calls = []
    report = convert_individual(sources, tmp_path / "out", ORIGINAL,
                                progress=lambda done, total, path: calls.append(done),
                                cancelled=lambda: len(calls) >= 2)
    assert report.cancelled
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["0.pdf"]


def test_progress_reports_every_step(make, tmp_path):
    sources = [make(f"{i}.png") for i in range(3)]
    calls = []
    convert_merged(sources, tmp_path / "m.pdf", ORIGINAL, progress=lambda d, t, p: calls.append((d, t)))
    assert calls == [(0, 3), (1, 3), (2, 3), (3, 3)]


def test_heic_orientation_is_applied_once(tmp_path):
    image = Image.new("RGB", (200, 100), "blue")
    image.paste((255, 0, 0), (0, 0, 100, 100))
    exif = Image.Exif()
    exif[0x0112] = 6
    source = tmp_path / "portrait.heic"
    image.save(source, exif=exif.tobytes(), quality=90)

    upright = load_image(source)
    assert upright.size == (100, 200)
    assert_close_color(upright.getpixel((50, 10)), (255, 0, 0))
    assert_close_color(upright.getpixel((50, 190)), (0, 0, 255))


def test_thumbnail_is_square_and_upright(tmp_path):
    from converter.images import make_thumbnail
    image = Image.new("RGB", (200, 100), "blue")
    image.paste((255, 0, 0), (0, 0, 100, 100))
    exif = Image.Exif()
    exif[0x0112] = 6
    source = tmp_path / "t.jpg"
    image.save(source, exif=exif.tobytes())
    thumb = make_thumbnail(source, 64)
    assert thumb.size == (64, 64)
    assert thumb.getpixel((0, 32))[3] == 0  # transparent padding beside a portrait image
    assert_close_color(thumb.getpixel((32, 4))[:3], (255, 0, 0))


def test_oversized_heic_is_refused(sample_heic, monkeypatch):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)
    with pytest.raises(ImageLoadError, match="too large"):
        load_image(sample_heic)


def test_16_bit_grayscale_keeps_its_tones(tmp_path):
    source = tmp_path / "deep.png"
    image = Image.new("I;16", (4, 1))
    for x, value in enumerate([0, 16384, 32768, 65535]):
        image.putpixel((x, 0), value)
    image.save(source)
    upright = load_image(source)
    assert upright.mode == "L"
    assert [upright.getpixel((x, 0)) for x in range(4)] == pytest.approx([0, 64, 128, 255], abs=1)


@pytest.mark.parametrize("mode, key", [("RGB", (0, 0, 0)), ("L", 0)])
def test_png_color_key_transparency_becomes_white(tmp_path, mode, key):
    source = tmp_path / f"key_{mode}.png"
    Image.new(mode, (10, 10), key).save(source, transparency=key)
    pixel = load_image(source).convert("RGB").getpixel((5, 5))
    assert_close_color(pixel, (255, 255, 255), 2)


@pytest.mark.parametrize("merged", [True, False])
def test_cancel_during_last_image_is_honoured(make, tmp_path, merged):
    source = make("only.png")
    out = tmp_path / "out"
    out.mkdir()
    existing = out / "only.pdf"
    existing.write_bytes(b"keep me")
    flag = []
    progress = lambda done, total, path: flag.append(True)
    cancelled = lambda: len(flag) > 0
    if merged:
        report = convert_merged([source], existing, ORIGINAL, progress, cancelled)
    else:
        report = convert_individual([source], out, ORIGINAL, progress, cancelled)
    assert report.cancelled and report.outputs == []
    assert existing.read_bytes() == b"keep me"
    assert sorted(p.name for p in out.iterdir()) == ["only.pdf"]


def _gray16(tmp_path, values, **save_kwargs):
    source = tmp_path / "g16.png"
    image = Image.new("I;16", (len(values), 1))
    for x, value in enumerate(values):
        image.putpixel((x, 0), value)
    image.save(source, **save_kwargs)
    return source


def test_16_bit_scaling_comes_from_bit_depth_not_pixel_values(tmp_path):
    upright = load_image(_gray16(tmp_path, [0, 64, 128, 255]))
    assert [upright.getpixel((x, 0)) for x in range(4)] == [0, 0, 0, 0]


def test_16_bit_color_key_transparency(tmp_path):
    upright = load_image(_gray16(tmp_path, [0, 32768, 65535], transparency=32768)).convert("L")
    assert [upright.getpixel((x, 0)) for x in range(3)] == pytest.approx([0, 255, 255], abs=1)


def test_color_key_survives_embedded_icc_profile(tmp_path):
    from PIL import ImageCms
    srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    source = tmp_path / "icc_key.png"
    image = Image.new("RGB", (10, 10), (0, 0, 0))
    image.putpixel((0, 0), (200, 10, 10))
    image.save(source, transparency=(0, 0, 0), icc_profile=srgb)
    upright = load_image(source)
    assert_close_color(upright.getpixel((5, 5)), (255, 255, 255), 2)
    assert_close_color(upright.getpixel((0, 0)), (200, 10, 10), 6)


def test_cmyk_jpeg_with_icc_profile_converts(tmp_path):
    from PIL import ImageCms
    srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    source = tmp_path / "cmyk.jpg"
    Image.new("CMYK", (10, 10), (0, 255, 255, 0)).save(source, icc_profile=srgb)
    assert load_image(source).mode == "RGB"
