import sys
from pathlib import Path


def asset_path(name: str) -> Path:
    """Locate a bundled asset both from source and inside a PyInstaller build."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / "assets" / name
