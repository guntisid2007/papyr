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


COPY_DENIED = "This PDF's security settings don't allow its content to be copied, so Papyr won't convert it."
PROTECTED = "This PDF is protected. Papyr won't copy it into a new PDF, because the copy would lose that protection."


def _rc4(path: Path, algorithm: str = "RC4-128", permissions: int | None = None) -> Path:
    """Text pages encrypted with an empty user password: anyone can open them, and /P holds the owner's limits."""
    source = text_pdf(path.with_name(f"plain-{path.name}"), ["PAGE_001", "PAGE_002"])
    writer = pypdf.PdfWriter(clone_from=source)
    options = {} if permissions is None else {"permissions_flag": permissions}
    writer.encrypt("", "owner", algorithm=algorithm, **options)
    writer.write(path)
    return path


def _copyable(tmp_path: Path, kind: str) -> Path:
    return FIXTURES / f"copyable-{kind}.pdf" if kind.startswith("aes") else _rc4(tmp_path / f"{kind}.pdf", kind.upper())


def _copy_denied(tmp_path: Path, kind: str) -> Path:
    return FIXTURES / f"restricted-{kind}.pdf" if kind.startswith("aes") else _rc4(tmp_path / f"{kind}.pdf",
                                                                                 permissions=0)


@pytest.mark.pdf
@pytest.mark.parametrize("kind", ["rc4-40", "rc4-128", "aes-128", "aes-256"])
def test_an_encrypted_pdf_that_allows_copying_becomes_images_but_never_a_new_pdf(tmp_path, kind):
    """A copy into a new PDF would drop the owner's restrictions, so PDF output refuses every encrypted PDF.
    Pictures of its pages are a copy the owner allowed."""
    source = _copyable(tmp_path, kind)
    for target, report in run_everywhere(source, tmp_path / "out"):
        if target.format is OutputFormat.PDF:
            assert not report.outputs, f"{target.key}: copied an encrypted PDF into {report.outputs}"
            assert [friendly_error(r) for _, r in report.failures] == [PROTECTED], f"{target.key}: {report}"
        else:
            assert not report.failures, f"{target.key}: {report.failures}"
            animated = target.format is OutputFormat.GIF and target.key != "GIF_SEPARATE"
            assert len(report.outputs) == (1 if animated else 2), f"{target.key}: {report.outputs}"
    assert not (tmp_path / "out" / "PDF").exists() or leftovers(tmp_path / "out" / "PDF") == []


@pytest.mark.pdf
@pytest.mark.parametrize("kind", ["rc4-128", "aes-128", "aes-256"])
def test_an_encrypted_pdf_that_forbids_copying_is_refused_for_every_output(tmp_path, kind):
    """The owner set /P without the copy bit. Rendering its pages to pictures would export what it protects."""
    source = _copy_denied(tmp_path, kind)
    for target, report in run_everywhere(source, tmp_path / "out"):
        assert not report.outputs, f"{target.key}: wrote {report.outputs}"
        expected = PROTECTED if target.format is OutputFormat.PDF else COPY_DENIED
        assert [friendly_error(r) for _, r in report.failures] == [expected], f"{target.key}: {report.failures}"
    assert leftovers(tmp_path / "out") == []


@pytest.mark.pdf
@pytest.mark.parametrize("name", ["restricted-aes-128.pdf", "restricted-aes-256.pdf", "copyable-aes-256.pdf"])
def test_a_protected_pdf_never_ends_the_batch(tmp_path, name):
    sources = [FIXTURES / name, FIXTURES / "outside.png"]
    for target in OFFERED:
        options = Options(format=target.format, gif_mode=target.gif_mode)
        job = plan_job(options, QueueSummary(count=2, has_document=True), sources, tmp_path / target.key)
        report = job(lambda *a: None, lambda: False)
        assert any(p.stem == "outside" for p in report.outputs) or report.outputs and target.format is \
            OutputFormat.GIF, f"{target.key}: {report}"
        for path, reason in report.failures:
            assert path.name == name and friendly_error(reason) in (PROTECTED, COPY_DENIED), f"{target.key}: {reason}"


@pytest.mark.pdf
def test_a_merged_pdf_leaves_out_an_encrypted_file_and_keeps_the_rest(tmp_path):
    locked = _rc4(tmp_path / "locked.pdf")
    report = convert_merged([locked, text_pdf(tmp_path / "next.pdf", ["NEXT_PAGE"])], tmp_path / "All.pdf",
                            PdfSettings())
    assert [(p.name, friendly_error(r)) for p, r in report.failures] == [("locked.pdf", PROTECTED)]
    facts = pdf_facts(tmp_path / "All.pdf")
    assert facts.pages == 1 and "NEXT_PAGE" in facts.texts[0]
    assert pypdf.PdfReader(tmp_path / "All.pdf").is_encrypted is False


@pytest.mark.pdf
def test_a_pdf_that_needs_a_password_to_open_is_refused_for_aes_too(tmp_path):
    assert_fails_cleanly(FIXTURES / "password-aes-256.pdf", tmp_path / "out", "This PDF is password-protected.")


@pytest.mark.pdf
def test_a_copy_denied_pdf_still_shows_a_preview(tmp_path):
    """A thumbnail in the window is viewing, which every PDF allows once it opens. Nothing is written."""
    from converter.images import make_thumbnail
    assert make_thumbnail(FIXTURES / "restricted-aes-128.pdf", 64).size == (64, 64)


def _malformed_encryption(path: Path, key: str, value) -> Path:
    from pypdf.generic import NameObject, NumberObject, TextStringObject
    values = {"bogus-name": NameObject("/Bogus"), "99": NumberObject(99), "text": TextStringObject("abc"),
              "pkcs7": NameObject("/adbe.pkcs7.s4")}
    source = text_pdf(path.with_name(f"plain-{path.name}"), ["MALFORMED"])
    writer = pypdf.PdfWriter(clone_from=source)
    writer.encrypt("", "owner", algorithm="RC4-128")
    if value is None:
        del writer._encrypt_entry[NameObject(key)]
    else:
        writer._encrypt_entry[NameObject(key)] = values[value]
    writer.write(path)
    return path


MALFORMED = {"unknown-filter": ("/Filter", "bogus-name"), "unknown-version": ("/V", "99"),
             "unknown-revision": ("/R", "99"), "no-owner-key": ("/O", None), "no-permissions": ("/P", None),
             "permissions-not-a-number": ("/P", "text"), "short-user-key": ("/U", "text")}


@pytest.mark.pdf
@pytest.mark.parametrize("case", sorted(MALFORMED))
def test_malformed_encryption_fails_that_file_with_a_reason_and_the_batch_goes_on(tmp_path, case):
    bad = _malformed_encryption(tmp_path / f"{case}.pdf", *MALFORMED[case])
    good = tmp_path / "good.png"
    Image.new("RGB", (40, 30), "blue").save(good)
    for name, run in ENTRY_POINTS:
        report = run([bad, good], tmp_path / name)
        assert report.outputs, f"{name}: the good file was not converted: {report}"
        assert [p.name for p, _ in report.failures] == [bad.name], f"{name}: {report.failures}"
        reason = friendly_error(report.failures[0][1])
        assert reason not in (GENERIC,), f"{name}: {report.failures[0][1]}"
        assert not any("MALFORMED" in "".join(pdf_facts(o).texts) for o in report.outputs if o.suffix == ".pdf")


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


@pytest.mark.pdf
def test_an_unusual_encryption_handler_is_one_failure_and_the_batch_goes_on(tmp_path):
    bad = _malformed_encryption(tmp_path / "unusual.pdf", "/SubFilter", "pkcs7")
    good = text_pdf(tmp_path / "good.pdf", ["VALID_AFTER_BAD"])
    for name, run in ENTRY_POINTS:
        report = run([bad, good], tmp_path / name)
        assert report.outputs, f"{name}: {report}"
        for path, reason in report.failures:
            assert path.name == "unusual.pdf" and friendly_error(reason) != GENERIC, f"{name}: {reason}"
    merged = convert_merged([bad, good], tmp_path / "m" / "All.pdf", PdfSettings())
    assert "VALID_AFTER_BAD" in "".join(pdf_facts(merged.outputs[0]).texts)


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
