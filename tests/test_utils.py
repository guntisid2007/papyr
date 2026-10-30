import os
from pathlib import Path

import pytest

from utils.filenames import individual_output_paths, sanitize_pdf_name, unique_path
from utils.files import FolderProblem, collect_images, folder_problem, human_size


@pytest.mark.parametrize("raw, expected", [
    ("Vacation", "Vacation.pdf"),
    ("Vacation.pdf", "Vacation.pdf"),
    ("Report.PDF", "Report.pdf"),
    ("  spaced  ", "spaced.pdf"),
    ("a/b\\c:d*e?f\"g<h>i|j", "a_b_c_d_e_f_g_h_i_j.pdf"),
    ("", "Converted.pdf"),
    ("...", "Converted.pdf"),
    ("CON", "Converted.pdf"),
    ("photo.heic", "photo.heic.pdf"),
])
def test_sanitize_pdf_name(raw, expected):
    assert sanitize_pdf_name(raw) == expected


def test_sanitize_truncates_long_names():
    assert len(sanitize_pdf_name("x" * 500)) == 204


def test_unique_path_skips_existing(tmp_path):
    (tmp_path / "a.pdf").touch()
    (tmp_path / "a (1).pdf").touch()
    assert unique_path(tmp_path / "a.pdf") == tmp_path / "a (2).pdf"
    assert unique_path(tmp_path / "b.pdf") == tmp_path / "b.pdf"


def test_individual_output_paths_keep_original_names(tmp_path):
    sources = [Path("/x/IMG_1.HEIC"), Path("/y/IMG_1.jpg"), Path("/x/beach.png")]
    assert [p.name for p in individual_output_paths(sources, tmp_path)] == \
        ["IMG_1.pdf", "IMG_1 (1).pdf", "beach.pdf"]


def test_collect_images_expands_folders_naturally_and_dedupes(tmp_path):
    folder = tmp_path / "album"
    (folder / "sub").mkdir(parents=True)
    for name in ["IMG_10.heic", "IMG_2.HEIC", "IMG_1.jpg", "notes.txt", ".hidden.png", "sub/z.png"]:
        (folder / name).write_bytes(b"x")
    loose = tmp_path / "loose.png"
    loose.write_bytes(b"x")
    found = collect_images([loose, folder, folder / "IMG_2.HEIC", tmp_path / "missing.png"])
    assert [p.relative_to(tmp_path).as_posix() for p in found] == [
        "loose.png", "album/IMG_1.jpg", "album/IMG_2.HEIC", "album/IMG_10.heic", "album/sub/z.png"]


@pytest.mark.parametrize("size, text", [(500, "500 B"), (2048, "2.0 KB"), (5 * 1024 ** 2, "5.0 MB")])
def test_human_size(size, text):
    assert human_size(size) == text


def test_collect_images_skips_hidden_folders_such_as_notebook_checkpoints(tmp_path):
    for name in ["analysis.ipynb", ".ipynb_checkpoints/analysis-checkpoint.ipynb", ".git/x.png"]:
        (tmp_path / name).parent.mkdir(exist_ok=True)
        (tmp_path / name).write_bytes(b"x")
    found = collect_images([tmp_path])
    assert [p.relative_to(tmp_path).as_posix() for p in found] == ["analysis.ipynb"]


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0, reason="root can write anywhere")
def test_folder_problem_reads_the_real_filesystem(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o555)
    try:
        assert folder_problem(locked) is FolderProblem.NOT_WRITABLE
        assert folder_problem(tmp_path) is None
        assert folder_problem(tmp_path / "missing") is FolderProblem.MISSING
    finally:
        locked.chmod(0o755)
