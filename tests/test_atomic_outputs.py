"""A source's outputs appear whole or not at all: a file that fails part way, a cancelled run, a full disk, or a
name that appears mid-run never leaves some of a source's files behind or replaces a file already there."""
import errno
import os
import stat
import struct
import sys
from pathlib import Path

import pytest
from PIL import Image

import converter.convert as convert
from converter import (GifSettings, ImageSettings, OutputFormat, PdfSettings, convert_animated_gifs,
                       convert_combined_gif, convert_images, convert_individual, convert_merged)
from pdf_samples import text_pdf
from utils.errors import friendly_error
from validators import parse_gif, pdf_facts

COLORS = ("red", "green", "blue")


def tiff_with_broken_page(path: Path, broken: int | None, pages: int = 3) -> Path:
    """A multi-page TIFF whose page number broken (1-based) has its width tag renamed, so Pillow fails on it."""
    frames = [Image.new("RGB", (24, 16), COLORS[i % 3]) for i in range(pages)]
    frames[0].save(path, save_all=True, append_images=frames[1:])
    if broken is None:
        return path
    data = bytearray(path.read_bytes())
    ifd = struct.unpack_from("<I", data, 4)[0]
    for _ in range(broken - 1):
        ifd = struct.unpack_from("<I", data, ifd + 2 + 12 * struct.unpack_from("<H", data, ifd)[0])[0]
    for index in range(struct.unpack_from("<H", data, ifd)[0]):
        entry = ifd + 2 + 12 * index
        if struct.unpack_from("<H", data, entry)[0] == 256:
            struct.pack_into("<H", data, entry, 65000)
    path.write_bytes(bytes(data))
    return path


def good_png(path: Path, color="purple") -> Path:
    Image.new("RGB", (40, 30), color).save(path)
    return path


def files_in(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def no_temporaries(folder: Path) -> None:
    assert not [p for p in folder.rglob(".papyr-*")], f"temporary files left in {folder}"


ENTRY_POINTS = {
    "images": lambda s, out, **kw: convert_images(s, out, ImageSettings(OutputFormat.PNG), **kw),
    "individual": lambda s, out, **kw: convert_individual(s, out, PdfSettings(), **kw),
    "merged": lambda s, out, **kw: convert_merged(s, out / "All.pdf", PdfSettings(), **kw),
    "animated": lambda s, out, **kw: convert_animated_gifs(s, out, GifSettings(), **kw),
    "combined": lambda s, out, **kw: convert_combined_gif(s, out / "All.gif", GifSettings(), **kw),
}


@pytest.mark.negative
@pytest.mark.parametrize("broken", [1, 2, 3], ids=["first-page", "middle-page", "last-page"])
@pytest.mark.parametrize("name", ENTRY_POINTS)
def test_a_page_failing_leaves_none_of_its_files(tmp_path, name, broken):
    before = good_png(tmp_path / "before.png", "orange")
    bad = tiff_with_broken_page(tmp_path / "scan.tiff", broken)
    after = good_png(tmp_path / "after.png", "purple")
    out = tmp_path / "out"
    report = ENTRY_POINTS[name]([before, bad, after], out)

    assert [(p.name, friendly_error(r)) for p, r in report.failures] == \
        [("scan.tiff", "The file appears to be damaged.")]
    assert not any("scan" in p for p in files_in(out)), files_in(out)
    assert all(p.exists() for p in report.outputs)
    no_temporaries(out)
    if name == "merged":
        assert pdf_facts(out / "All.pdf").pages == 2, "only the two good pictures"
    elif name == "combined":
        assert parse_gif(out / "All.gif").frames == 2, "none of the damaged file's frames"
    else:
        ext = {"images": ".png", "individual": ".pdf", "animated": ".gif"}[name]
        assert files_in(out) == [f"after{ext}", f"before{ext}"]


@pytest.mark.parametrize("name", ENTRY_POINTS)
def test_a_complete_multipage_source_writes_every_page(tmp_path, name):
    scan = tiff_with_broken_page(tmp_path / "scan.tiff", None)
    out = tmp_path / "out"
    report = ENTRY_POINTS[name]([scan], out)
    assert not report.failures
    expected = {"images": ["scan-page-1.png", "scan-page-2.png", "scan-page-3.png"], "individual": ["scan.pdf"],
                "merged": ["All.pdf"], "animated": ["scan.gif"], "combined": ["All.gif"]}[name]
    assert files_in(out) == expected
    assert [p.name for p in report.outputs] == expected
    if name in ("individual", "merged"):
        assert pdf_facts(out / expected[0]).pages == 3
    elif name in ("animated", "combined"):
        assert parse_gif(out / expected[0]).frames == 3


@pytest.mark.parametrize("name", ENTRY_POINTS)
def test_cancelling_mid_source_leaves_only_finished_sources(tmp_path, name):
    first = good_png(tmp_path / "first.png")
    long = tiff_with_broken_page(tmp_path / "long.tiff", None, pages=5)
    checks = []
    out = tmp_path / "out"
    report = ENTRY_POINTS[name]([first, long], out, cancelled=lambda: checks.append(1) or len(checks) > 6)
    assert report.cancelled
    assert not any("long" in p for p in files_in(out)), files_in(out)
    no_temporaries(out)
    if name in ("merged", "combined"):
        assert files_in(out) == [], "a merged file is all or nothing"
    else:
        assert [p.name for p in report.outputs] == files_in(out) and len(files_in(out)) == 1


@pytest.mark.negative
@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="POSIX permissions, not as root")
@pytest.mark.parametrize("name", ENTRY_POINTS)
def test_an_unwritable_folder_fails_each_file_and_leaves_nothing(tmp_path, name):
    out = tmp_path / "locked"
    out.mkdir()
    out.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        report = ENTRY_POINTS[name]([good_png(tmp_path / "a.png"), good_png(tmp_path / "b.png")], out)
    finally:
        out.chmod(stat.S_IRWXU)
    assert report.outputs == [] and report.failures
    assert {friendly_error(r) for _, r in report.failures} == {"The destination folder is not writable."}
    assert files_in(out) == []


def test_existing_files_are_never_replaced(tmp_path):
    scan = tiff_with_broken_page(tmp_path / "scan.tiff", None)
    out = tmp_path / "out"
    out.mkdir()
    for name in ("scan-page-1.png", "scan.pdf", "scan.gif"):
        (out / name).write_bytes(b"the user's own file")
    reports = [convert_images([scan], out, ImageSettings(OutputFormat.PNG)),
               convert_individual([scan], out, PdfSettings()),
               convert_animated_gifs([scan], out, GifSettings())]
    for name in ("scan-page-1.png", "scan.pdf", "scan.gif"):
        assert (out / name).read_bytes() == b"the user's own file"
    assert [[p.name for p in r.outputs] for r in reports] == [
        ["scan-page-1 (1).png", "scan-page-2.png", "scan-page-3.png"], ["scan (1).pdf"], ["scan (1).gif"]]


def test_a_merged_file_replaces_only_on_success(tmp_path):
    """The window asks before a merged file is replaced. A run that then fails keeps the old file."""
    out = tmp_path / "out"
    out.mkdir()
    (out / "All.pdf").write_bytes(b"old merge")
    bad = tiff_with_broken_page(tmp_path / "scan.tiff", 2)
    report = convert_merged([bad], out / "All.pdf", PdfSettings())
    assert not report.outputs and (out / "All.pdf").read_bytes() == b"old merge"
    report = convert_merged([good_png(tmp_path / "a.png")], out / "All.pdf", PdfSettings())
    assert report.outputs == [out / "All.pdf"] and pdf_facts(out / "All.pdf").pages == 1


def test_same_names_from_different_folders_get_their_own_files(tmp_path):
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    sources = [good_png(tmp_path / "one" / "photo.png", "red"), good_png(tmp_path / "two" / "photo.png", "blue")]
    report = convert_images(sources, tmp_path / "out", ImageSettings(OutputFormat.PNG))
    assert [p.name for p in report.outputs] == ["photo.png", "photo (1).png"]
    assert Image.open(report.outputs[1]).getpixel((0, 0)) == (0, 0, 255)


def test_a_name_taken_while_converting_is_not_overwritten(tmp_path, monkeypatch):
    """Another program creates the output's name after Papyr chose it. The move into place must not replace it."""
    out = tmp_path / "out"
    real_save = convert.save_image

    def save_and_race(image, stream, fmt, quality):
        (out / "photo.png").write_bytes(b"someone else's file")
        real_save(image, stream, fmt, quality)
    monkeypatch.setattr(convert, "save_image", save_and_race)
    report = convert_images([good_png(tmp_path / "photo.png")], out, ImageSettings(OutputFormat.PNG))
    assert (out / "photo.png").read_bytes() == b"someone else's file"
    assert [p.name for p in report.outputs] == ["photo (1).png"]


def test_a_full_disk_while_writing_leaves_nothing(tmp_path, monkeypatch):
    real_save = convert.save_image
    calls = []

    def fill_disk(image, stream, fmt, quality):
        calls.append(1)
        if len(calls) == 2:
            raise OSError(errno.ENOSPC, "No space left on device")
        real_save(image, stream, fmt, quality)
    monkeypatch.setattr(convert, "save_image", fill_disk)
    out = tmp_path / "out"
    scan = tiff_with_broken_page(tmp_path / "scan.tiff", None)
    report = convert_images([scan, good_png(tmp_path / "after.png")], out, ImageSettings(OutputFormat.PNG))
    assert [(p.name, friendly_error(r)) for p, r in report.failures] == \
        [("scan.tiff", "There isn't enough free space on the disk.")]
    assert files_in(out) == ["after.png"]


def test_a_move_failing_part_way_takes_back_the_files_already_moved(tmp_path, monkeypatch):
    real_rename = convert.rename_no_replace
    moved = []

    def rename(src, dst):
        if moved:
            raise OSError(errno.ENOSPC, "No space left on device")
        moved.append(dst)
        return real_rename(src, dst)
    monkeypatch.setattr(convert, "rename_no_replace", rename)
    out = tmp_path / "out"
    report = convert_images([tiff_with_broken_page(tmp_path / "scan.tiff", None)], out,
                            ImageSettings(OutputFormat.PNG))
    assert moved, "the first page was moved into place before the failure"
    assert report.outputs == [] and len(report.failures) == 1
    assert files_in(out) == []


def test_taking_back_a_moved_file_spares_one_another_program_put_in_its_place(tmp_path, monkeypatch):
    """Page 1 is in place, another program replaces it with its own file, then page 2 fails to move. Taking
    back page 1 must not delete the other program's file."""
    real_rename = convert.rename_no_replace
    moved = []

    def rename(src, dst):
        if moved:
            (moved[0].parent / "elsewhere").write_bytes(b"someone else's file")
            os.replace(moved[0].parent / "elsewhere", moved[0])
            raise OSError(errno.ENOSPC, "No space left on device")
        moved.append(Path(dst))
        return real_rename(src, dst)
    monkeypatch.setattr(convert, "rename_no_replace", rename)
    out = tmp_path / "out"
    report = convert_images([tiff_with_broken_page(tmp_path / "scan.tiff", None)], out,
                            ImageSettings(OutputFormat.PNG))
    assert report.outputs == [] and len(report.failures) == 1
    assert files_in(out) == ["scan-page-1.png"]
    assert (out / "scan-page-1.png").read_bytes() == b"someone else's file"


def no_atomic_moves(monkeypatch, link_error=errno.ENOTSUP):
    """A disk like exFAT on macOS: no atomic no-replace rename and no hard links."""
    def no_links(src, dst, **kw):
        raise OSError(link_error, os.strerror(link_error))
    monkeypatch.setattr(convert, "rename_no_replace", lambda src, dst: False)
    monkeypatch.setattr(os, "link", no_links)


@pytest.mark.parametrize("link_error", [errno.ENOTSUP, errno.EPERM, errno.EACCES])
def test_a_disk_without_atomic_moves_still_gets_its_files(tmp_path, monkeypatch, link_error):
    no_atomic_moves(monkeypatch, link_error)
    out = tmp_path / "out"
    out.mkdir()
    (out / "scan-page-1.png").write_bytes(b"keep me")
    report = convert_images([tiff_with_broken_page(tmp_path / "scan.tiff", None)], out,
                            ImageSettings(OutputFormat.PNG))
    assert [p.name for p in report.outputs] == ["scan-page-1 (1).png", "scan-page-2.png", "scan-page-3.png"]
    assert (out / "scan-page-1.png").read_bytes() == b"keep me"
    assert [Image.open(p).size for p in report.outputs] == [(24, 16)] * 3
    no_temporaries(out)


@pytest.mark.batch
def test_one_damaged_file_in_a_mixed_batch_stops_nothing_else(tmp_path):
    sources = [good_png(tmp_path / "a.png"), tiff_with_broken_page(tmp_path / "bad.tiff", 3),
               text_pdf(tmp_path / "doc.pdf", ["one", "two"]), (tmp_path / "empty.jpg"),
               good_png(tmp_path / "z.png")]
    sources[3].write_bytes(b"")
    out = tmp_path / "out"
    report = convert_images(sources, out, ImageSettings(OutputFormat.JPEG))
    assert sorted(p.name for p, _ in report.failures) == ["bad.tiff", "empty.jpg"]
    assert files_in(out) == ["a.jpg", "doc-page-1.jpg", "doc-page-2.jpg", "z.jpg"]
    no_temporaries(out)


@pytest.mark.animation
@pytest.mark.parametrize("name", ["animated", "combined"])
def test_an_animation_failing_after_its_first_frame_keeps_none_of_its_frames(tmp_path, monkeypatch, name):
    """A PDF page can be damaged in a way only drawing it reveals, after earlier pages became frames."""
    real_frames = convert.frames

    def failing_frames(source, canvas):
        for number, frame in enumerate(real_frames(source, canvas), start=1):
            if source.path.name == "doc.pdf" and number == 2:
                raise convert.ImageLoadError("Could not read page 2 of the PDF: damaged")
            yield frame
    monkeypatch.setattr(convert, "frames", failing_frames)
    doc = text_pdf(tmp_path / "doc.pdf", ["one", "two", "three"])
    good = text_pdf(tmp_path / "good.pdf", ["fine", "also fine"])
    out = tmp_path / "out"
    report = ENTRY_POINTS[name]([doc, good], out)
    assert [p.name for p, _ in report.failures] == ["doc.pdf"]
    if name == "animated":
        assert files_in(out) == ["good.gif"]
    else:
        assert files_in(out) == ["All.gif"] and parse_gif(out / "All.gif").frames == 2
    no_temporaries(out)


@pytest.mark.negative
def test_a_very_long_or_unusual_name_still_converts_every_page(tmp_path):
    long = tiff_with_broken_page(tmp_path / f"{'名' * 80}.tiff", None)
    out = tmp_path / "out"
    report = convert_images([long], out, ImageSettings(OutputFormat.PNG))
    assert not report.failures and len(report.outputs) == 3
    assert all(len(p.name.encode()) <= 255 and p.parent == out for p in report.outputs)


DECODE_STEP = {"images": "iter_pages", "individual": "_encoded_pages", "merged": "_encoded_pages",
               "animated": "measure", "combined": "measure"}


@pytest.mark.parametrize("name", ENTRY_POINTS)
def test_an_unexpected_error_is_that_files_failure_and_keeps_the_rest(tmp_path, monkeypatch, name):
    """A bug or an odd decoder error used to end the job, and the window then lost the files already written."""
    real = getattr(convert, DECODE_STEP[name])

    def step(source, *args, **kwargs):
        if source.name == "bad.png":
            raise RuntimeError("something nobody expected")
        return real(source, *args, **kwargs)
    monkeypatch.setattr(convert, DECODE_STEP[name], step)
    sources = [good_png(tmp_path / "first.png"), good_png(tmp_path / "bad.png"), good_png(tmp_path / "last.png")]
    report = ENTRY_POINTS[name](sources, tmp_path / "out")
    assert [p.name for p, _ in report.failures] == ["bad.png"]
    assert report.outputs and all(p.exists() for p in report.outputs)
    assert not any("bad" in p for p in files_in(tmp_path / "out"))


def test_without_atomic_moves_a_name_taken_mid_run_is_still_not_overwritten(tmp_path, monkeypatch):
    """The name is created exclusively, so a file another program writes just before the copy keeps its bytes and
    the conversion takes the next name."""
    out = tmp_path / "out"
    no_atomic_moves(monkeypatch)

    def competitor_first(src, dst, **kw):
        if not (out / "photo.png").exists():
            (out / "photo.png").write_bytes(b"someone else's file")
        raise OSError(errno.ENOTSUP, "Operation not supported")
    monkeypatch.setattr(os, "link", competitor_first)
    report = convert_images([good_png(tmp_path / "photo.png")], out, ImageSettings(OutputFormat.PNG))
    assert (out / "photo.png").read_bytes() == b"someone else's file"
    assert [p.name for p in report.outputs] == ["photo (1).png"]
    assert Image.open(report.outputs[0]).size == (40, 30)


def test_without_atomic_moves_a_name_replaced_during_the_copy_keeps_the_other_file(tmp_path, monkeypatch):
    """The narrow race the audit found: another program renames its file over Papyr's freshly created name while
    Papyr copies into it. Its file survives, and Papyr writes its own under the next name instead of claiming
    the replaced one as its output."""
    out = tmp_path / "out"
    no_atomic_moves(monkeypatch)
    real_copy = convert.shutil.copyfileobj
    raced = []

    def copy_then_race(source, target, *args):
        real_copy(source, target, *args)
        if not raced:
            raced.append(1)
            (out / "theirs").write_bytes(b"someone else's file")
            os.replace(out / "theirs", out / "photo.png")
    monkeypatch.setattr(convert.shutil, "copyfileobj", copy_then_race)
    report = convert_images([good_png(tmp_path / "photo.png")], out, ImageSettings(OutputFormat.PNG))
    assert not report.failures
    assert (out / "photo.png").read_bytes() == b"someone else's file"
    assert [p.name for p in report.outputs] == ["photo (1).png"]
    assert Image.open(report.outputs[0]).size == (40, 30)
    no_temporaries(out)


def test_without_atomic_moves_a_failed_copy_leaves_no_file(tmp_path, monkeypatch):
    no_atomic_moves(monkeypatch)
    real_fsync = os.fsync

    def fail_on_the_copy(fd):
        if any(p.name == "photo.png" for p in (tmp_path / "out").iterdir()):
            raise OSError(errno.EIO, "I/O error")
        real_fsync(fd)
    monkeypatch.setattr(os, "fsync", fail_on_the_copy)
    out = tmp_path / "out"
    report = convert_images([good_png(tmp_path / "photo.png")], out, ImageSettings(OutputFormat.PNG))
    monkeypatch.undo()
    assert report.outputs == [] and len(report.failures) == 1
    assert files_in(out) == []


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no POSIX file modes")
@pytest.mark.parametrize("name", list(ENTRY_POINTS))
def test_converted_files_get_the_usual_permissions_not_owner_only(tmp_path, name):
    """Staged files start as mkstemp's owner-only 0600. Papyr 2.3.1 left its outputs that way, so other accounts
    and some shared folders couldn't read them."""
    umask = os.umask(0o022)
    os.umask(umask)
    report = ENTRY_POINTS[name]([good_png(tmp_path / "photo.png")], tmp_path / "out")
    assert report.outputs and not report.failures
    for path in report.outputs:
        assert stat.S_IMODE(path.stat().st_mode) == 0o666 & ~umask, f"{path.name}: {oct(path.stat().st_mode)}"


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no POSIX file modes")
def test_without_atomic_moves_files_get_the_usual_permissions_too(tmp_path, monkeypatch):
    no_atomic_moves(monkeypatch)
    umask = os.umask(0o022)
    os.umask(umask)
    report = convert_images([good_png(tmp_path / "photo.png")], tmp_path / "out", ImageSettings(OutputFormat.PNG))
    assert stat.S_IMODE(report.outputs[0].stat().st_mode) == 0o666 & ~umask


def test_a_file_saved_over_papyrs_just_after_the_move_is_not_taken_back(tmp_path, monkeypatch):
    """Found in review: the placed file's identity was read from its name after the move, so a file another program
    saved there in that instant was recorded as Papyr's and deleted when a later page failed to move."""
    real_rename = convert.rename_no_replace
    moved = []

    def rename(src, dst):
        if moved:
            raise OSError(errno.ENOSPC, "No space left on device")
        result = real_rename(src, dst)
        moved.append(Path(dst))
        (Path(dst).parent / "theirs").write_bytes(b"someone else's file")
        os.replace(Path(dst).parent / "theirs", dst)  # lands before Papyr looks at the name
        return result
    monkeypatch.setattr(convert, "rename_no_replace", rename)
    out = tmp_path / "out"
    report = convert_images([tiff_with_broken_page(tmp_path / "scan.tiff", None)], out,
                            ImageSettings(OutputFormat.PNG))
    assert report.outputs == [] and len(report.failures) == 1
    assert (out / "scan-page-1.png").read_bytes() == b"someone else's file"


def test_a_failure_while_placing_a_later_page_takes_back_the_earlier_ones(tmp_path, monkeypatch):
    """Found in review: a stat failing right after a move escaped before the file was recorded, so rollback missed
    it. Placement now reads everything it needs before moving, so any failure leaves the source with no files."""
    real_stat = os.stat
    out = tmp_path / "out"
    seen = []

    def stat(path, *args, **kwargs):
        if Path(path).parent == out and Path(path).name.startswith(".papyr-"):
            seen.append(path)
            if len(seen) == 2:
                raise OSError(errno.EIO, "I/O error")
        return real_stat(path, *args, **kwargs)
    monkeypatch.setattr(convert.os, "stat", stat)
    report = convert_images([tiff_with_broken_page(tmp_path / "scan.tiff", None)], out,
                            ImageSettings(OutputFormat.PNG))
    monkeypatch.undo()
    assert report.outputs == [] and len(report.failures) == 1
    assert files_in(out) == []


def test_a_disk_that_refuses_mode_changes_still_gets_its_files(tmp_path, monkeypatch):
    """FAT drives on Linux give every file a fixed mode and refuse chmod. That must not fail the conversion."""
    def no_chmod(*args, **kwargs):
        raise PermissionError(errno.EPERM, "Operation not permitted")
    monkeypatch.setattr(convert.os, "chmod", no_chmod)
    report = convert_images([good_png(tmp_path / "photo.png")], tmp_path / "out", ImageSettings(OutputFormat.PNG))
    assert not report.failures and [p.name for p in report.outputs] == ["photo.png"]


def test_without_inode_numbers_rollback_leaves_files_rather_than_guess(tmp_path, monkeypatch):
    """Some network shares report inode 0 for every file, so Papyr can't prove a file is still its own."""
    path = good_png(tmp_path / "placed.png")
    convert._remove_if_ours(path, (path.stat().st_dev, 0, path.stat().st_size))
    assert path.exists()
