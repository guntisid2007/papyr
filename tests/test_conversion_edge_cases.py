"""Bad inputs and awkward paths. Papyr must report each failure in one plain sentence, write no partial file, and keep
converting whatever else it can. A failure counts as a pass here only where failing is the right behavior."""
import os
import struct
import sys
import time
import zlib
from pathlib import Path

import pypdf
import pytest
from PIL import Image

from conftest import FIXTURES
from conversion_matrix import targets
from converter import (INPUT_EXTENSIONS, GifSettings, ImageSettings, OutputFormat, PdfSettings, convert_animated_gifs,
                       convert_combined_gif, convert_images, convert_individual, convert_merged)
from gui.model import Options, QueueSummary, plan_job
from pdf_samples import encrypted_pdf, text_pdf
from utils.errors import GENERIC, friendly_error
from validators import pdf_facts, sniff

pytestmark = [pytest.mark.negative, pytest.mark.usefixtures("app")]
POSIX_PERMISSIONS = sys.platform != "win32" and hasattr(os, "geteuid") and os.geteuid() != 0
OFFERED = [t for t in targets() if t.offered]


def run_everywhere(source: Path, out: Path):
    """Convert one file to every output the window offers. Yields (target, report)."""
    for target in OFFERED:
        options = Options(format=target.format, gif_mode=target.gif_mode)
        queue = QueueSummary(count=1, has_document=source.suffix.lower() in (".pdf", ".ipynb"))
        destination = out / target.key
        yield target, plan_job(options, queue, [source], destination)(lambda *a: None, lambda: False)


def leftovers(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.rglob("*") if p.is_file()) if folder.exists() else []


def assert_fails_cleanly(source: Path, out: Path, reason: str):
    for target, report in run_everywhere(source, out):
        assert not report.outputs, f"{target.key}: wrote {report.outputs} from a bad file"
        assert len(report.failures) == 1, f"{target.key}: {report.failures}"
        friendly = friendly_error(report.failures[0][1])
        assert friendly == reason, f"{target.key}: said '{friendly}' ({report.failures[0][1]})"
    assert leftovers(out) == [], "partial or temporary files were left behind"


# Damaged and empty files

@pytest.mark.parametrize("suffix", sorted(INPUT_EXTENSIONS))
def test_zero_byte_files_fail_with_a_reason_for_every_output(tmp_path, suffix):
    source = tmp_path / f"empty{suffix}"
    source.write_bytes(b"")
    expected = {".pdf": "The file appears to be damaged.", ".ipynb": "This isn't a valid Jupyter notebook."}
    assert_fails_cleanly(source, tmp_path / "out", expected.get(suffix, "The file appears to be damaged."))


@pytest.mark.parametrize("name", ["png-landscape", "jpeg-landscape", "heic-landscape", "webp-landscape",
                                  "avif-landscape", "tiff-landscape", "bmp-landscape", "gif-landscape"])
def test_truncated_pictures_fail_instead_of_writing_a_half_picture(fixture_specs, tmp_path, name):
    data = fixture_specs[name].path().read_bytes()
    source = tmp_path / fixture_specs[name].file_name
    source.write_bytes(data[:len(data) // 2])
    assert_fails_cleanly(source, tmp_path / "out", "The file appears to be damaged.")


def _damaged_pdf(fixture_specs, tmp_path) -> Path:
    """Twelve pages whose middle objects are zeroed: PDFium opens it but cannot load some pages."""
    data = bytearray(fixture_specs["pdf-twelve-pages"].path().read_bytes())
    data[len(data) // 3:len(data) // 3 + 2000] = b"\x00" * 2000
    source = tmp_path / "damaged.pdf"
    source.write_bytes(bytes(data))
    return source


def test_a_pdf_with_unloadable_pages_is_reported_and_the_batch_goes_on(fixture_specs, tmp_path):
    """PDFium raised its own error type out of the converter, so one damaged PDF ended the whole batch."""
    good = fixture_specs["png-landscape"].path()
    sources = [_damaged_pdf(fixture_specs, tmp_path), good]
    for target in OFFERED:
        options = Options(format=target.format, gif_mode=target.gif_mode)
        job = plan_job(options, QueueSummary(count=2, has_document=True), sources, tmp_path / target.key)
        report = job(lambda *a: None, lambda: False)
        converted = {p.stem.split("-page-")[0] for p in report.outputs}
        assert "png-landscape" in converted or (target.key == "GIF" and report.outputs), \
            f"{target.key}: the good file was not converted: {report}"
        for path, reason in report.failures:
            assert path.name == "damaged.pdf" and friendly_error(reason) == "The file appears to be damaged.", \
                f"{target.key}: {reason}"
        for output in report.outputs:
            assert sniff(output) is not None


def test_a_pdf_cut_short_fails_with_a_reason(fixture_specs, tmp_path):
    data = fixture_specs["pdf-mixed-content"].path().read_bytes()
    source = tmp_path / "cut.pdf"
    source.write_bytes(data[:len(data) // 4])
    assert_fails_cleanly(source, tmp_path / "out", "The file appears to be damaged.")


@pytest.mark.notebook
@pytest.mark.parametrize("content, reason", [
    ("{ this is not json", "This isn't a valid Jupyter notebook."),
    ('{"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": "nope"}', "This notebook file is damaged."),
    ('{"nbformat": 3, "worksheets": []}', "This notebook uses an old format that Papyr can't read."),
    ('{"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": []}', "This notebook is empty."),
    ("[1, 2, 3]", "This isn't a valid Jupyter notebook."),
])
def test_bad_notebooks_fail_with_a_reason(tmp_path, content, reason):
    source = tmp_path / "bad.ipynb"
    source.write_text(content)
    assert_fails_cleanly(source, tmp_path / "out", reason)


# Files that are not what their name says

@pytest.mark.parametrize("suffix", [".txt", ".docx", ".svg", ".mp4", ""])
def test_unsupported_types_are_named_as_such(tmp_path, suffix):
    source = tmp_path / f"notes{suffix}"
    source.write_text("hello")
    assert_fails_cleanly(source, tmp_path / "out", "This file format isn't supported.")


def test_a_png_named_jpg_still_converts_by_its_contents(fixture_specs, tmp_path):
    source = tmp_path / "actually-png.jpg"
    source.write_bytes(fixture_specs["png-landscape"].path().read_bytes())
    report = convert_images([source], tmp_path / "out", ImageSettings(OutputFormat.WEBP))
    assert not report.failures and sniff(report.outputs[0]) == "WEBP"


@pytest.mark.parametrize("donor, suffix", [("jpeg-landscape", ".pdf"), ("pdf-single-text", ".png"),
                                           ("png-landscape", ".ipynb"), ("notebook-short", ".heic")])
def test_contents_that_do_not_match_the_extension_fail_with_a_reason(fixture_specs, tmp_path, donor, suffix):
    source = tmp_path / f"mislabeled{suffix}"
    source.write_bytes(fixture_specs[donor].path().read_bytes())
    for target, report in run_everywhere(source, tmp_path / "out"):
        assert not report.outputs and report.failures, target.key
        assert friendly_error(report.failures[0][1]) != GENERIC, f"{target.key}: {report.failures[0][1]}"


# Protected and oversized

@pytest.mark.pdf
def test_password_protected_pdfs_say_so(tmp_path):
    assert_fails_cleanly(encrypted_pdf(tmp_path / "locked.pdf"), tmp_path / "out", "This PDF is password-protected.")


@pytest.mark.pdf
def test_a_pdf_with_only_an_owner_password_opens_like_any_other(tmp_path):
    source = text_pdf(tmp_path / "plain.pdf", ["PAGE_001", "PAGE_002"])
    writer = pypdf.PdfWriter(clone_from=source)
    writer.encrypt(user_password="", owner_password="owner", algorithm="RC4-128")
    locked = tmp_path / "restricted.pdf"
    with open(locked, "wb") as stream:
        writer.write(stream)
    for target, report in run_everywhere(locked, tmp_path / "out"):
        assert not report.failures, f"{target.key}: {report.failures}"
    assert pdf_facts(tmp_path / "out" / "PDF" / "restricted.pdf").pages == 2


@pytest.mark.pdf
@pytest.mark.parametrize("name", ["restricted-aes-128.pdf", "restricted-aes-256.pdf"])
def test_aes_restricted_pdfs_never_end_the_batch(tmp_path, name):
    """Owner-restricted PDFs (no password to open) usually use AES. pypdf needs the cryptography package to copy
    their pages, and its error escaped the converter, so every file after one in the queue was lost."""
    sources = [FIXTURES / name, FIXTURES / "outside.png"]
    for target in OFFERED:
        options = Options(format=target.format, gif_mode=target.gif_mode)
        job = plan_job(options, QueueSummary(count=2, has_document=True), sources, tmp_path / target.key)
        report = job(lambda *a: None, lambda: False)
        assert any(p.stem == "outside" for p in report.outputs) or target.key == "GIF", f"{target.key}: {report}"
        for path, reason in report.failures:
            assert path.name == name and friendly_error(reason) != GENERIC, f"{target.key}: {reason}"
        if target.format is not OutputFormat.PDF:
            assert not report.failures, f"{target.key} reads AES through PDFium: {report.failures}"


def _png_header_only(path: Path, width: int, height: int) -> Path:
    """A real PNG that declares a huge canvas and holds one row of data. Nothing large is ever decoded."""
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"\x00" * 64))
                     + chunk(b"IEND", b""))
    return path


def test_a_picture_too_large_to_decode_safely_is_refused_quickly(tmp_path):
    source = _png_header_only(tmp_path / "huge.png", 60_000, 60_000)
    started = time.monotonic()
    assert_fails_cleanly(source, tmp_path / "out", "This image is too large to convert safely.")
    assert time.monotonic() - started < 30


def test_a_large_but_safe_picture_converts(tmp_path):
    source = tmp_path / "large.jpg"
    Image.new("RGB", (8000, 6000), (90, 140, 200)).save(source, quality=80)
    report = convert_images([source], tmp_path / "png", ImageSettings(OutputFormat.PNG))
    assert not report.failures
    with Image.open(report.outputs[0]) as image:
        assert image.size == (8000, 6000)
    assert pdf_facts(convert_individual([source], tmp_path / "pdf", PdfSettings()).outputs[0]).images == \
        [[(8000, 6000)]]


# Names and places

@pytest.mark.parametrize("name", ["Grüße aus Zürich", "日本語のファイル", "emoji 📄 file", "spaces   in  name",
                                  "dots.in.the.name", "-leading-dash"])
def test_unusual_names_carry_through_to_the_outputs(fixture_specs, tmp_path, name):
    source = tmp_path / f"{name}.png"
    source.write_bytes(fixture_specs["png-portrait"].path().read_bytes())
    assert convert_individual([source], tmp_path / "out", PdfSettings()).outputs == [tmp_path / "out" / f"{name}.pdf"]
    report = convert_images([source], tmp_path / "out", ImageSettings(OutputFormat.JPEG))
    assert report.outputs == [tmp_path / "out" / f"{name}.jpg"] and sniff(report.outputs[0]) == "JPEG"


def test_deep_folders_for_input_and_output(fixture_specs, tmp_path):
    deep_in = tmp_path.joinpath(*[f"in{i}" for i in range(12)])
    deep_in.mkdir(parents=True)
    source = deep_in / "photo.heic"
    source.write_bytes(fixture_specs["heic-portrait"].path().read_bytes())
    deep_out = tmp_path.joinpath(*[f"out{i}" for i in range(12)])
    report = convert_individual([source], deep_out, PdfSettings())
    assert report.outputs == [deep_out / "photo.pdf"] and pdf_facts(report.outputs[0]).pages == 1


def test_a_missing_output_folder_is_created(fixture_specs, tmp_path):
    out = tmp_path / "does" / "not" / "exist"
    report = convert_images([fixture_specs["png-tiny"].path()], out, ImageSettings(OutputFormat.PNG))
    assert report.outputs == [out / "png-tiny.png"]


@pytest.mark.skipif(not POSIX_PERMISSIONS, reason="needs POSIX permissions and a non-root user")
def test_a_read_only_destination_fails_with_a_reason_and_writes_nothing(fixture_specs, tmp_path):
    out = tmp_path / "locked"
    out.mkdir()
    out.chmod(0o555)
    try:
        for target, report in run_everywhere(fixture_specs["png-landscape"].path(), out):
            pass
        sources = [fixture_specs["png-landscape"].path()]
        for report in (convert_images(sources, out, ImageSettings(OutputFormat.JPEG)),
                       convert_individual(sources, out, PdfSettings()),
                       convert_merged(sources, out / "All.pdf", PdfSettings()),
                       convert_animated_gifs(sources, out, GifSettings()),
                       convert_combined_gif(sources, out / "All.gif", GifSettings())):
            assert not report.outputs and report.failures
            assert friendly_error(report.failures[0][1]) == "The destination folder is not writable."
        assert leftovers(out) == []
    finally:
        out.chmod(0o755)


@pytest.mark.skipif(not POSIX_PERMISSIONS, reason="needs POSIX permissions and a non-root user")
def test_an_unreadable_source_says_papyr_may_not_read_it(fixture_specs, tmp_path):
    source = tmp_path / "secret.png"
    source.write_bytes(fixture_specs["png-tiny"].path().read_bytes())
    source.chmod(0o000)
    try:
        assert_fails_cleanly(source, tmp_path / "out", "Papyr isn't allowed to read this file.")
    finally:
        source.chmod(0o644)


def test_a_file_deleted_before_conversion_is_reported_as_gone(tmp_path):
    assert_fails_cleanly(tmp_path / "vanished.png", tmp_path / "out", "The file was moved or deleted.")


# Stopping part way

def _cancel_after(calls: int):
    count = {"n": 0}

    def cancelled():
        count["n"] += 1
        return count["n"] > calls
    return cancelled


@pytest.mark.parametrize("job", ["images", "individual", "merged", "animated", "combined"])
def test_cancelling_keeps_finished_files_and_leaves_no_partial_one(fixture_specs, tmp_path, job):
    sources = [fixture_specs[n].path() for n in ("pdf-twelve-pages", "png-landscape", "pdf-mixed-content")]
    out = tmp_path / "out"
    run = {"images": lambda c: convert_images(sources, out, ImageSettings(OutputFormat.PNG, pdf_dpi=72),
                                              cancelled=c),
           "individual": lambda c: convert_individual(sources, out, PdfSettings(), cancelled=c),
           "merged": lambda c: convert_merged(sources, out / "All.pdf", PdfSettings(), cancelled=c),
           "animated": lambda c: convert_animated_gifs(sources, out, GifSettings(), cancelled=c),
           "combined": lambda c: convert_combined_gif(sources, out / "All.gif", GifSettings(), cancelled=c)}[job]
    report = run(_cancel_after(2))
    assert report.cancelled
    on_disk = leftovers(out)
    assert not [n for n in on_disk if n.startswith(".papyr-") or n.endswith(".part")], on_disk
    assert sorted(p.name for p in report.outputs) == on_disk
    for path in report.outputs:
        assert sniff(path) is not None
        if path.suffix == ".pdf":
            assert pdf_facts(path).pages >= 1
    if job in ("merged", "combined"):
        assert on_disk == [], "a merged file is all or nothing"


ENTRY_POINTS = [
    ("images", lambda s, out: convert_images(s, out, ImageSettings(OutputFormat.PNG))),
    ("individual", lambda s, out: convert_individual(s, out, PdfSettings())),
    ("merged", lambda s, out: convert_merged(s, out / "All.pdf", PdfSettings())),
    ("animated", lambda s, out: convert_animated_gifs(s, out, GifSettings())),
    ("combined", lambda s, out: convert_combined_gif(s, out / "All.gif", GifSettings())),
]


def _tiff_with_broken_second_page(path: Path) -> Path:
    """Three frames; the second frame's width tag is renamed, so Pillow raises TypeError while reading it."""
    frames = [Image.new("RGB", (24, 16), color) for color in ("red", "green", "blue")]
    frames[0].save(path, save_all=True, append_images=frames[1:])
    data = bytearray(path.read_bytes())
    first = struct.unpack_from("<I", data, 4)[0]
    second = struct.unpack_from("<I", data, first + 2 + 12 * struct.unpack_from("<H", data, first)[0])[0]
    for index in range(struct.unpack_from("<H", data, second)[0]):
        entry = second + 2 + 12 * index
        if struct.unpack_from("<H", data, entry)[0] == 256:
            struct.pack_into("<H", data, entry, 65000)
    path.write_bytes(bytes(data))
    return path


@pytest.mark.parametrize("name, run", ENTRY_POINTS, ids=[e[0] for e in ENTRY_POINTS])
def test_any_decoder_error_in_one_picture_is_that_files_failure(tmp_path, name, run):
    """Pillow raises whatever type its plugin hits on a malformed file (here TypeError). A list of expected types
    missed it, and the whole batch ended."""
    bad = _tiff_with_broken_second_page(tmp_path / "broken.tiff")
    good = tmp_path / "good.png"
    Image.new("RGB", (40, 30), "blue").save(good)
    report = run([bad, good], tmp_path / "out")
    assert report.outputs, f"{name}: the good file was not converted: {report}"
    assert [(p.name, friendly_error(r)) for p, r in report.failures] == \
        [("broken.tiff", "The file appears to be damaged.")], name


def _encrypted_with(path: Path, edit) -> Path:
    source = text_pdf(path.with_name(f"plain-{path.name}"), ["RESTRICTED_BUT_COPYABLE"])
    writer = pypdf.PdfWriter(clone_from=source)
    writer.encrypt("", "owner", algorithm="RC4-128")
    edit(writer)
    writer.write(path)
    return path


@pytest.mark.pdf
def test_a_pdf_pypdf_cannot_open_is_one_failure_on_pdf_output(tmp_path):
    from pypdf.generic import NameObject

    def unusual_handler(writer):
        writer._encrypt_entry[NameObject("/SubFilter")] = NameObject("/adbe.pkcs7.s4")
    bad = _encrypted_with(tmp_path / "unusual.pdf", unusual_handler)
    good = text_pdf(tmp_path / "good.pdf", ["VALID_AFTER_BAD"])
    for name, run in ENTRY_POINTS:
        report = run([bad, good], tmp_path / name)
        assert report.outputs, f"{name}: {report}"
        for path, reason in report.failures:
            assert path.name == "unusual.pdf" and friendly_error(reason) != GENERIC, f"{name}: {reason}"
    merged = convert_merged([bad, good], tmp_path / "m" / "All.pdf", PdfSettings())
    assert "VALID_AFTER_BAD" in "".join(pdf_facts(merged.outputs[0]).texts)


@pytest.mark.pdf
def test_an_rc4_pdf_that_also_lists_an_unused_aes_filter_still_copies(tmp_path):
    from pypdf.generic import DictionaryObject, NameObject

    def rc4_v4_with_spare_aes(writer):
        writer.encrypt("", "owner", algorithm="AES-128")
        writer._encryption.StmF = writer._encryption.StrF = writer._encryption.EFF = "/V2"
        entry = writer._encrypt_entry
        entry["/CF"]["/StdCF"][NameObject("/CFM")] = NameObject("/V2")
        entry["/CF"][NameObject("/UnusedAES")] = DictionaryObject({NameObject("/CFM"): NameObject("/AESV2")})
    try:
        restricted = _encrypted_with(tmp_path / "rc4-v4.pdf", rc4_v4_with_spare_aes)
    except pypdf.errors.DependencyError:
        pytest.skip("this pypdf needs cryptography even to write the AES-128 dictionary")
    report = convert_individual([restricted], tmp_path / "out", PdfSettings())
    assert not report.failures, report.failures
    assert "RESTRICTED_BUT_COPYABLE" in pdf_facts(report.outputs[0]).texts[0]


def _rc4_with_spare_aes_declarations(writer, variant):
    from pypdf.generic import DictionaryObject, NameObject
    aes = DictionaryObject({NameObject("/CFM"): NameObject("/AESV2")})
    entry = writer._encrypt_entry
    if variant == "v2":  # /V 2 ignores crypt filters entirely
        entry[NameObject("/CF")] = DictionaryObject({NameObject("/SpareAES"): aes})
        for key in ("/StmF", "/StrF", "/EFF"):
            entry[NameObject(key)] = NameObject("/SpareAES")
    else:  # /V 4, AES only for attachments, and there are none
        writer.encrypt("", "owner", algorithm="AES-128")
        entry = writer._encrypt_entry
        writer._encryption.StmF = writer._encryption.StrF = "/V2"
        writer._encryption.EFF = "/AESV2"
        entry["/CF"]["/StdCF"][NameObject("/CFM")] = NameObject("/V2")
        entry["/CF"][NameObject("/AttachmentAES")] = aes
        entry[NameObject("/EFF")] = NameObject("/AttachmentAES")


@pytest.mark.pdf
@pytest.mark.parametrize("variant", ["v2", "v4-attachments-only"])
def test_restricted_pdfs_copy_whenever_their_pages_need_no_aes(tmp_path, variant):
    try:
        restricted = _encrypted_with(tmp_path / f"{variant}.pdf", lambda w: _rc4_with_spare_aes_declarations(w, variant))
    except pypdf.errors.DependencyError:
        pytest.skip("this pypdf needs cryptography even to write the AES-128 dictionary")
    report = convert_merged([restricted, text_pdf(tmp_path / "next.pdf", ["NEXT"])], tmp_path / "All.pdf",
                            PdfSettings())
    assert not report.failures, report.failures
    assert pdf_facts(tmp_path / "All.pdf").pages == 2


def test_running_out_of_memory_on_one_file_says_so_and_the_batch_goes_on(fixture_specs, tmp_path, monkeypatch):
    import converter.animation as animation
    import converter.images as images
    huge, good = fixture_specs["png-hires"].path(), fixture_specs["png-tiny"].path()
    real_open = images.Image.open

    def open_image(path, *args, **kwargs):
        if Path(path) == huge:
            raise MemoryError
        return real_open(path, *args, **kwargs)
    monkeypatch.setattr(images.Image, "open", open_image)
    monkeypatch.setattr(animation.Image, "open", open_image)
    for name, run in ENTRY_POINTS:
        report = run([huge, good], tmp_path / name)
        assert report.outputs, name
        assert [(p.name, friendly_error(r)) for p, r in report.failures] == \
            [(huge.name, "There isn't enough memory to convert this file.")], f"{name}: {report.failures}"
