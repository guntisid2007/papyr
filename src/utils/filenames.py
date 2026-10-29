import re
from pathlib import Path

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = frozenset({"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                       *(f"LPT{i}" for i in range(1, 10))})


def sanitize_pdf_name(name: str, fallback: str = "Converted") -> str:
    """Turn user input into a safe file name that ends in .pdf."""
    stem = name.strip()
    if stem.lower().endswith(".pdf"):
        stem = stem[:-4]
    stem = _ILLEGAL.sub("_", stem).strip(" .")
    if not stem or stem.upper() in _RESERVED:
        stem = fallback
    return f"{stem[:200]}.pdf"


def unique_path(path: Path, taken: set[Path] = frozenset()) -> Path:
    """Return path, or 'name (n).pdf' if it exists on disk or is already taken in this batch."""
    candidate, n = path, 1
    while candidate.exists() or candidate in taken:
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        n += 1
    return candidate


def individual_output_paths(sources: list[Path], output_dir: Path) -> list[Path]:
    """Map each source to '<original name>.pdf' in output_dir without overwriting anything."""
    taken: set[Path] = set()
    outputs = []
    for source in sources:
        path = unique_path(output_dir / sanitize_pdf_name(source.stem), taken)
        taken.add(path)
        outputs.append(path)
    return outputs
