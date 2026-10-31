"""Time and peak memory of the heaviest conversion paths, each in a fresh process so one path's memory is not
another's. Needs the fixtures (python scripts/make_conversion_fixtures.py) and a POSIX resource module.

    python scripts/perf_probe.py
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "generated"
PATHS = [
    ("pdf/pdf-twelve-pages.pdf", "GIF"), ("pdf/pdf-mixed-content.pdf", "AVIF"), ("pdf/pdf-mixed-content.pdf", "HEIC"),
    ("pdf/pdf-mixed-content.pdf", "PNG"), ("ipynb/notebook-matrix.ipynb", "PDF"), ("ipynb/notebook-matrix.ipynb", "GIF"),
    ("png/png-hires.png", "AVIF"), ("png/png-hires.png", "HEIC"), ("bmp/bmp-hires.bmp", "PDF"),
    ("tiff/tiff-hires.tiff", "WEBP"), ("jpeg/jpeg-hires.jpg", "JPEG"),
]
CHILD = """
import sys, time, tempfile, resource
from pathlib import Path
sys.path[:0] = [{src!r}]
from gui.app import create_app, use_headless_platform
use_headless_platform(); app = create_app(["probe"])
from converter import OutputFormat
from gui.model import Options, QueueSummary, plan_job
source, fmt = Path({source!r}), OutputFormat[{fmt!r}]
job = plan_job(Options(format=fmt), QueueSummary(count=1, has_document=source.suffix in ('.pdf', '.ipynb')),
               [source], Path(tempfile.mkdtemp()))
started = time.perf_counter()
report = job(lambda *a: None, lambda: False)
seconds = time.perf_counter() - started
peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(seconds, peak if sys.platform == "darwin" else peak * 1024, len(report.outputs), len(report.failures))
"""


def main() -> None:
    rows = []
    for name, fmt in PATHS:
        source = FIXTURES / name
        code = CHILD.format(src=str(ROOT / "src"), source=str(source), fmt=fmt)
        run = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=600)
        if run.returncode:
            rows.append({"source": name, "output": fmt, "error": run.stderr.strip().splitlines()[-1]})
            continue
        seconds, peak, outputs, failures = run.stdout.split()
        rows.append({"source": name, "output": fmt, "seconds": round(float(seconds), 2),
                     "peak_rss_mb": round(int(peak) / 2 ** 20), "outputs": int(outputs), "failures": int(failures)})
        print(rows[-1], flush=True)
    print(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
