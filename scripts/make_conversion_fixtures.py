"""Write every conversion-matrix fixture into tests/fixtures/generated (or the folder given) and list them.

    python scripts/make_conversion_fixtures.py [folder]

The test run builds the same files itself; this is for looking at them, or for feeding them to the packaged app.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

from gui.app import create_app, use_headless_platform  # noqa: E402

import fixture_factory  # noqa: E402


def main() -> None:
    use_headless_platform()
    app = create_app([sys.argv[0]])  # noqa: F841  the PDF fixtures are drawn with Qt
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else fixture_factory.ROOT
    for spec in fixture_factory.build(root):
        path = spec.path(root)
        print(f"{spec.format:6} {path.relative_to(root)}  {path.stat().st_size:>9} bytes  {spec.description}")


if __name__ == "__main__":
    main()
