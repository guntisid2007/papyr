import re
from pathlib import Path

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = frozenset({"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                       *(f"LPT{i}" for i in range(1, 10))})


def sanitize_name(name: str, extension: str, fallback: str = "Converted") -> str:
    """Turn user input into a safe file name that ends in extension."""
    stem = name.strip()
    if stem.lower().endswith(extension):
        stem = stem[:-len(extension)]
    stem = _ILLEGAL.sub("_", stem).strip(" .")
    if not stem or stem.upper() in _RESERVED:
        stem = fallback
    return f"{stem[:200]}{extension}"


def unique_path(path: Path, taken: set[Path] = frozenset()) -> Path:
    """Return path, or 'name (n).pdf' if it exists on disk or is already taken in this batch."""
    candidate, n = path, 1
    while candidate.exists() or candidate in taken:
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        n += 1
    return candidate


def individual_output_paths(sources: list[Path], output_dir: Path, extension: str = ".pdf") -> list[Path]:
    """Map each source to '<original name><extension>' in output_dir without overwriting anything."""
    taken: set[Path] = set()
    outputs = []
    for source in sources:
        path = unique_path(output_dir / sanitize_name(source.stem, extension), taken)
        taken.add(path)
        outputs.append(path)
    return outputs
