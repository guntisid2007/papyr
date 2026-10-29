import io
from pathlib import Path

import pillow_heif
import pytest
from PIL import Image
from pypdf import PdfReader

from converter import (ImageSettings, OutputFormat, PageSize, PdfSettings, convert_images, convert_individual,
                       convert_merged)
from pdf_samples import encrypted_pdf, text_pdf

RED, BLUE = (230, 20, 20), (20, 20, 230)
SIZE = (64, 48)
ORIGINAL = PdfSettings(PageSize.ORIGINAL, margin_mm=0)
INPUTS = ["heic", "heif", "jpg", "png", "webp", "avif", "tiff", "bmp", "gif", "pdf"]
IMAGE_OUTPUTS = [f for f in OutputFormat if f is not OutputFormat.PDF]


def split_image() -> Image.Image:
    image = Image.new("RGB", SIZE, BLUE)
    image.paste(RED, (0, 0, SIZE[0] // 2, SIZE[1]))
    return image


def write_input(tmp_path: Path, ext: str) -> Path:
    path = tmp_path / f"in-{ext}.{ext}"
    image = split_image()
    if ext in ("heic", "heif"):
        pillow_heif.from_pillow(image).save(path, quality=95)
    elif ext == "pdf":
        png = tmp_path / "pdf-source.png"
        image.save(png)
        convert_merged([png], path, ORIGINAL)
    else:
        image.save(path, quality=95) if ext in ("jpg", "webp", "avif") else image.save(path)
    return path


def open_output(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def assert_close(actual, expected, tolerance=60):
    assert all(abs(a - e) <= tolerance for a, e in zip(actual, expected)), (actual, expected)


@pytest.mark.parametrize("output", IMAGE_OUTPUTS, ids=lambda f: f.name)
@pytest.mark.parametrize("ext", INPUTS)
def test_every_input_converts_to_every_image_format(tmp_path, ext, output):
    source = write_input(tmp_path, ext)
    report = convert_images([source], tmp_path / "out", ImageSettings(output, 90, pdf_dpi=72))
    assert report.failures == []
    [result] = report.outputs
    assert result.suffix == output.extension and result.stem == source.stem
    image = open_output(result)
    assert image.size == SIZE
    assert_close(image.getpixel((8, 24))[:3], RED)
    assert_close(image.getpixel((56, 24))[:3], BLUE)


@pytest.mark.parametrize("ext", INPUTS)
def test_every_input_converts_to_pdf(tmp_path, ext):
    source = write_input(tmp_path, ext)
    report = convert_individual([source], tmp_path / "out", ORIGINAL)
    assert report.failures == []
    page = PdfReader(report.outputs[0]).pages[0]
    assert (float(page.mediabox.width), float(page.mediabox.height)) == SIZE


@pytest.mark.parametrize("output", IMAGE_OUTPUTS, ids=lambda f: f.name)
def test_transparency_kept_where_the_format_supports_it(tmp_path, output):
    source = tmp_path / "alpha.png"
    image = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    image.paste((200, 30, 30, 255), (0, 0, 32, 48))
    image.save(source)
    [result] = convert_images([source], tmp_path, ImageSettings(output, 95)).outputs
    out = open_output(result)
    if output.keeps_alpha:
        assert out.getpixel((56, 24))[3] == 0
    else:
        assert_close(out.getpixel((56, 24)), (255, 255, 255, 255), 3)
    assert_close(out.getpixel((8, 24))[:3], (200, 30, 30))


def test_merging_pdfs_keeps_their_text_and_adds_images_in_order(tmp_path, sample_heic):
    doc = text_pdf(tmp_path / "doc.pdf", ["Hello first", "Hello second"])
    report = convert_merged([doc, sample_heic, doc], tmp_path / "all.pdf", PdfSettings(PageSize.A4, 10))
    assert report.failures == []
    pages = PdfReader(report.outputs[0]).pages
    assert len(pages) == 5
    texts = [p.extract_text() for p in pages]
    assert "Hello first" in texts[0] and "Hello second" in texts[1]
    assert pages[2].images and texts[2].strip() == ""
    assert "Hello first" in texts[3] and "Hello second" in texts[4]
    assert (float(pages[0].mediabox.width), float(pages[0].mediabox.height)) == (300, 200)


def test_multipage_pdf_becomes_numbered_images(tmp_path):
    doc = text_pdf(tmp_path / "report.pdf", ["one", "two", "three"], size=(72, 36))
    report = convert_images([doc], tmp_path / "out", ImageSettings(OutputFormat.PNG, pdf_dpi=144))
    assert [p.name for p in report.outputs] == ["report-page-1.png", "report-page-2.png", "report-page-3.png"]
    assert Image.open(report.outputs[0]).size == (144, 72)


def test_multiframe_tiff_becomes_pdf_pages(tmp_path):
    source = tmp_path / "scan.tiff"
    frames = [Image.new("RGB", (40, 30), c) for c in ("red", "green", "blue")]
    frames[0].save(source, save_all=True, append_images=frames[1:])
    report = convert_merged([source], tmp_path / "scan.pdf", ORIGINAL)
    assert len(PdfReader(report.outputs[0]).pages) == 3


def test_encrypted_pdf_is_reported(tmp_path):
    locked = encrypted_pdf(tmp_path / "locked.pdf")
    for report in (convert_images([locked], tmp_path / "a", ImageSettings(OutputFormat.PNG)),
                   convert_individual([locked], tmp_path / "b", ORIGINAL)):
        assert report.outputs == []
        assert "password" in report.failures[0][1].lower()


def test_same_format_conversion_never_overwrites_the_source(tmp_path):
    source = tmp_path / "photo.jpg"
    split_image().save(source)
    original = source.read_bytes()
    report = convert_images([source], tmp_path, ImageSettings(OutputFormat.JPEG, 50))
    assert [p.name for p in report.outputs] == ["photo (1).jpg"]
    assert source.read_bytes() == original


def test_quality_setting_changes_size(tmp_path):
    source = tmp_path / "noise.png"
    Image.effect_noise((256, 256), 64).convert("RGB").save(source)
    sizes = []
    for quality in (30, 95):
        [out] = convert_images([source], tmp_path / str(quality), ImageSettings(OutputFormat.JPEG, quality)).outputs
        sizes.append(out.stat().st_size)
    assert sizes[0] < sizes[1]


def test_image_output_is_upright_and_has_no_metadata(tmp_path):
    exif = Image.Exif()
    exif[0x0112] = 6
    exif[0x010F] = "SecretCameraMaker"
    source = tmp_path / "turned.jpg"
    split_image().save(source, exif=exif.tobytes())
    for fmt in (OutputFormat.JPEG, OutputFormat.PNG, OutputFormat.HEIC, OutputFormat.WEBP):
        [out] = convert_images([source], tmp_path / fmt.name, ImageSettings(fmt)).outputs
        assert Image.open(out).size == (48, 64)
        assert b"SecretCameraMaker" not in out.read_bytes()


def test_cancel_image_conversion_keeps_finished_files_only(tmp_path):
    doc = text_pdf(tmp_path / "long.pdf", [f"p{i}" for i in range(6)], size=(72, 72))
    report = convert_images([doc], tmp_path / "out", ImageSettings(OutputFormat.PNG),
                            cancelled=lambda: len(list((tmp_path / "out").glob("*.png"))) >= 2)
    assert report.cancelled
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["long-page-1.png", "long-page-2.png"]


def test_broken_pdf_is_reported(tmp_path):
    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"%PDF-1.4 nonsense")
    report = convert_images([bad], tmp_path / "out", ImageSettings(OutputFormat.PNG))
    assert report.outputs == [] and report.failures[0][0] == bad
    report = convert_merged([bad], tmp_path / "m.pdf", ORIGINAL)
    assert report.outputs == [] and report.failures[0][0] == bad


def test_pdf_thumbnails_from_many_threads_do_not_crash(tmp_path):
    """PDFium is not thread-safe. Run in a subprocess so a crash fails this test instead of the whole run."""
    import subprocess
    import sys

    script = f"""
import sys
sys.path[:0] = {[str(Path(__file__).parent.parent / "src"), str(Path(__file__).parent)]!r}
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from converter.images import iter_pages, make_thumbnail
from pdf_samples import text_pdf
paths = [text_pdf(Path({str(tmp_path)!r}) / f"{{i}}.pdf", ["a", "b"]) for i in range(24)]
with ThreadPoolExecutor(8) as pool:
    for _ in range(10):
        list(pool.map(lambda p: make_thumbnail(p, 80), paths))
        list(pool.map(lambda p: [page.size for page in iter_pages(p)], paths))
print("ok")
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0 and "ok" in result.stdout, result.stderr[-2000:]


@pytest.mark.parametrize("output", [OutputFormat.PDF, OutputFormat.PNG], ids=lambda f: f.name)
def test_pdf_with_empty_user_password_converts(tmp_path, output):
    import pypdf
    source = tmp_path / "restricted.pdf"
    writer = pypdf.PdfWriter(clone_from=text_pdf(tmp_path / "plain.pdf", ["Readable"]))
    writer.encrypt("", owner_password="owner", algorithm="RC4-128")
    with open(source, "wb") as stream:
        writer.write(stream)
    if output is OutputFormat.PDF:
        report = convert_individual([source], tmp_path / "out", ORIGINAL)
        assert "Readable" in PdfReader(report.outputs[0]).pages[0].extract_text()
    else:
        report = convert_images([source], tmp_path / "out", ImageSettings(output))
    assert report.failures == [] and len(report.outputs) == 1
