import os
import re
from collections.abc import Iterable
from enum import Enum
from pathlib import Path

from converter.images import is_supported


def _natural_key(path: Path) -> list:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name)]


def collect_images(paths: Iterable[Path]) -> list[Path]:
    """Expand folders recursively, keep supported files, and drop duplicates, in input order.

    Hidden files and anything inside hidden folders (such as Jupyter's .ipynb_checkpoints) are skipped."""
    seen: set[Path] = set()
    result = []
    for path in paths:
        if path.is_dir():
            found = sorted((p for p in path.rglob("*")
                            if p.is_file() and is_supported(p)
                            and not any(part.startswith(".") for part in p.relative_to(path).parts)),
                           key=lambda p: (_natural_key(p.parent), _natural_key(p)))
        else:
            found = [path] if path.is_file() and is_supported(path) else []
        for item in found:
            key = item.resolve()
            if key not in seen:
                seen.add(key)
                result.append(item)
    return result


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    raise AssertionError("unreachable")


class FolderProblem(Enum):
    """Why converted files can't be saved in a folder: (short line for the folder row, explanation)."""

    MISSING = ("Folder not found", "The Save to folder no longer exists. Choose another folder.")
    NOT_WRITABLE = ("Folder isn't writable", "Papyr can't save files in this folder. Choose another folder.")

    def __init__(self, short: str, explanation: str):
        self.short = short
        self.explanation = explanation


def folder_problem(folder: Path) -> FolderProblem | None:
    if not folder.is_dir():
        return FolderProblem.MISSING
    if not os.access(folder, os.W_OK | os.X_OK):
        return FolderProblem.NOT_WRITABLE
    return None
