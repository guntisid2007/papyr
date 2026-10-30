import json
import os
import sys

import pytest

from converter import ImageSettings, OutputFormat, PageSize, PdfSettings, convert_images, convert_individual
from pdf_samples import encrypted_pdf
from utils.errors import DAMAGED, GENERIC, NOT_WRITABLE, friendly_error


def only_failure(report) -> str:
    assert len(report.failures) == 1, report.failures
    return report.failures[0][1]


def test_unsupported_file(tmp_path):
    note = tmp_path / "note.txt"
    note.write_text("hello")
    raw = only_failure(convert_images([note], tmp_path / "out", ImageSettings(OutputFormat.PNG)))
    assert friendly_error(raw) == "This file format isn't supported."


@pytest.mark.parametrize("name", ["broken.heic", "broken.jpg", "broken.png"])
def test_damaged_image(tmp_path, name):
    bad = tmp_path / name
    bad.write_bytes(b"not an image at all")
    raw = only_failure(convert_images([bad], tmp_path / "out", ImageSettings(OutputFormat.PNG)))
    assert friendly_error(raw) == DAMAGED


def test_damaged_pdf(tmp_path):
    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"%PDF-1.4 truncated")
    raw = only_failure(convert_images([bad], tmp_path / "out", ImageSettings(OutputFormat.PNG)))
    assert friendly_error(raw) == DAMAGED


def test_password_protected_pdf(tmp_path):
    locked = encrypted_pdf(tmp_path / "locked.pdf")
    raw = only_failure(convert_images([locked], tmp_path / "out", ImageSettings(OutputFormat.PNG)))
    assert friendly_error(raw) == "This PDF is password-protected."


@pytest.mark.parametrize("content, friendly", [
    ("{not json", "This isn't a valid Jupyter notebook."),
    (json.dumps({"nbformat": 3, "worksheets": []}), "This notebook uses an old format that Papyr can't read."),
    (json.dumps({"nbformat": 4, "cells": []}), "This notebook is empty."),
    (json.dumps({"nbformat": 4, "cells": "nope"}), "This notebook file is damaged."),
])
def test_notebook_problems(app, tmp_path, content, friendly):
    notebook = tmp_path / "analysis.ipynb"
    notebook.write_text(content)
    raw = only_failure(convert_individual([notebook], tmp_path, PdfSettings(PageSize.A4, 10)))
    assert friendly_error(raw) == friendly


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_unwritable_destination(tmp_path, make):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o555)
    try:
        raw = only_failure(convert_individual([make("a.png")], locked, PdfSettings()))
    finally:
        locked.chmod(0o755)
    assert friendly_error(raw) == NOT_WRITABLE


@pytest.mark.parametrize("raw, friendly", [
    ("Image is too large to convert safely", "This image is too large to convert safely."),
    (str(OSError(30, os.strerror(30), "/Volumes/CD/.papyr-1.part")), NOT_WRITABLE),
    (str(OSError(28, "No space left on device")), "There isn't enough free space on the disk."),
    (f"Could not read image: {FileNotFoundError(2, 'No such file or directory', '/gone.jpg')}",
     "The file was moved or deleted."),
    (f"Could not read image: {PermissionError(13, 'Permission denied', '/a.jpg')}",
     "Papyr isn't allowed to read this file."),
    ("A 60 mm margin leaves no room on the page", "The margins are too large for the page."),
    ("None of the files could be read", "None of the files could be read."),
    ("Unexpected error: boom", GENERIC),
    ("", GENERIC),
])
def test_error_text_mapping(raw, friendly):
    assert friendly_error(raw) == friendly


def test_tracebacks_and_paths_never_reach_the_window():
    raw = 'Traceback (most recent call last):\n  File "/x.py", line 1\nKeyError: /Users/me/secret.jpg'
    assert friendly_error(raw) == GENERIC
