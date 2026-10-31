"""The conversion matrix: every input format Papyr reads against every output it offers.

Rows come from converter.INPUT_EXTENSIONS and columns from OutputFormat (plus the GIF modes the window offers), so a
format added to the engine shows up here, and fails loudly until it is classified. What Papyr declares (Declared) is
kept apart from what a run observed (Result). A pair is PASSED only when it ran and every output passed validation.
"""
import csv
import functools
import io
import json
import platform
import time
import warnings
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

import pypdf
from PIL import Image, features

from converter import INPUT_EXTENSIONS, OutputFormat
from converter.images import NOTEBOOK_IMAGE_SETTINGS
from converter.notebook import render_notebook
from fixture_factory import ALPHA_PROBES, EXECUTION_SENTINEL, PAGE_COLORS, FixtureSpec
from gui.model import GifMode, Options, QueueSummary, plan_job
from validators import (alpha_at, band_color, color_distance, fit_on_page, gif_frames, ink, is_solid, mae,
                        parse_gif, pdf_facts, pdf_page_count_pdfium, pdf_render, quadrant_mae, second_decoder, sniff,
                        text_darkness)

EXTENSION_ROWS = {".heic": "HEIC", ".heif": "HEIF", ".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP",
                  ".avif": "AVIF", ".tif": "TIFF", ".tiff": "TIFF", ".bmp": "BMP", ".gif": "GIF", ".pdf": "PDF",
                  ".ipynb": "IPYNB"}
ROW_ORDER = ["HEIC", "HEIF", "JPEG", "PNG", "WEBP", "AVIF", "TIFF", "BMP", "GIF", "PDF", "IPYNB"]
DOCUMENT_ROWS = {"PDF", "IPYNB"}
SNIFFED = {OutputFormat.JPEG: "JPEG", OutputFormat.PNG: "PNG", OutputFormat.HEIC: "HEIC", OutputFormat.WEBP: "WEBP",
           OutputFormat.AVIF: "AVIF", OutputFormat.TIFF: "TIFF", OutputFormat.GIF: "GIF", OutputFormat.BMP: "BMP",
           OutputFormat.PDF: "PDF"}
LOSSY_OUTPUTS = {OutputFormat.JPEG, OutputFormat.WEBP, OutputFormat.HEIC, OutputFormat.AVIF}
SLOW_SECONDS = 120
DPI = 200  # the window's default page resolution for PDFs and notebooks turned into pictures
A4 = (595.2756, 841.8898)
# Lossless, then lossy or palette. Measured on these fixtures: at most 0.0 lossless, and 1.2 (worst quarter 1.4) for
# WebP, GIF palettes, and animation frames. Erasing a page body below its band measures far above either.
RENDER_TOLERANCE = {False: (1.0, 2.0), True: (2.5, 5.0)}
MARGIN_PT = 10 * 72 / 25.4


def input_rows() -> list[str]:
    unclassified = INPUT_EXTENSIONS - EXTENSION_ROWS.keys()
    assert not unclassified, f"Papyr reads {sorted(unclassified)}; classify them in EXTENSION_ROWS"
    found = {EXTENSION_ROWS[ext] for ext in INPUT_EXTENSIONS}
    return [row for row in ROW_ORDER if row in found]


@dataclass(frozen=True)
class Target:
    key: str
    label: str
    format: OutputFormat | None
    gif_mode: GifMode = GifMode.ANIMATE_EACH

    @property
    def offered(self) -> bool:
        return self.format is not None


def targets() -> list[Target]:
    found = []
    for fmt in OutputFormat:
        if fmt is OutputFormat.GIF:
            found.append(Target("GIF", "GIF (animated, the default)", fmt, GifMode.ANIMATE_EACH))
            found.append(Target("GIF_SEPARATE", "GIF (separate static)", fmt, GifMode.SEPARATE))
        else:
            found.append(Target(fmt.name, fmt.label, fmt))
    found.append(Target("IPYNB", "Jupyter notebook", None))
    return found


class Declared(Enum):
    SUPPORTED = "SUPPORTED"
    CONDITIONAL = "CONDITIONAL"
    UNSUPPORTED_BY_DESIGN = "UNSUPPORTED_BY_DESIGN"


@functools.cache
def _encodes(fmt: OutputFormat) -> bool:
    try:
        Image.new("RGB", (8, 8)).save(io.BytesIO(), fmt.pillow_format)
        return True
    except (KeyError, OSError, ValueError):
        return False


def codec_missing(row: str, target: Target) -> str | None:
    """Pillow builds can leave out AVIF, and libheif builds can leave out the HEVC encoder."""
    if "AVIF" in (row, target.key) and not features.check("avif"):
        return "this Pillow build has no AVIF codec"
    if target.format in (OutputFormat.HEIC, OutputFormat.AVIF) and not _encodes(target.format):
        return f"no {target.format.label} encoder in this build"
    return None


def declared(row: str, target: Target) -> tuple[Declared, str]:
    if not target.offered:
        return Declared.UNSUPPORTED_BY_DESIGN, "Papyr never writes notebooks; there is no notebook output format"
    if missing := codec_missing(row, target):
        return Declared.CONDITIONAL, missing
    return Declared.SUPPORTED, ""


# What a run should produce

def expected_pages(spec: FixtureSpec, target: Target) -> int:
    if spec.kind != "notebook":
        return len(spec.pages)
    return notebook_pages(spec, "pdf" if target.format is OutputFormat.PDF else "image")


_NOTEBOOK_PAGES: dict[tuple[str, str], int] = {}


def notebook_pages(spec: FixtureSpec, use: str) -> int:
    """How many pages Papyr's own layout gives this notebook. The image outputs lay it out on 'Original' pages,
    the PDF output on A4, so the two counts can differ. This is a consistency expectation, not an independent one."""
    from converter import PageSize, PdfSettings
    key = (spec.name, use)
    if key not in _NOTEBOOK_PAGES:
        settings = PdfSettings(PageSize.A4, 10) if use == "pdf" else NOTEBOOK_IMAGE_SETTINGS
        _NOTEBOOK_PAGES[key] = len(pypdf.PdfReader(io.BytesIO(render_notebook(spec.path(), settings))).pages)
    return _NOTEBOOK_PAGES[key]


def animates(spec: FixtureSpec, target: Target) -> bool:
    return target.key == "GIF" and (spec.kind != "raster" or len(spec.pages) > 1)


def expected_names(spec: FixtureSpec, target: Target, pages: int) -> list[str]:
    stem = Path(spec.file_name).stem
    ext = target.format.extension
    if target.format is OutputFormat.PDF or target.key == "GIF" or pages == 1:
        return [f"{stem}{ext}"]
    width = 3 if target.key == "GIF_SEPARATE" else 0
    return [f"{stem}-page-{n:0{width}d}{ext}" for n in range(1, pages + 1)]


def expected_behavior(spec: FixtureSpec, target: Target) -> str:
    if not target.offered:
        return "not offered"
    pages = "each page" if spec.kind != "raster" or len(spec.pages) > 1 else "the picture"
    if spec.animated_frames > 1:
        pages = "the first frame only (animated inputs are read as their first frame)"
    if target.format is OutputFormat.PDF:
        return f"one PDF with {pages} as a page" + (", text kept" if spec.kind != "raster" else ", on A4")
    if target.key == "GIF" and animates(spec, target):
        return f"one animated GIF, {pages} as a frame, 1000 ms, loops forever"
    alpha = "" if not spec.has_alpha else (", transparency kept" if target.format.keeps_alpha
                                            else ", transparency on white")
    return f"one {target.format.label} file per page for {pages}{alpha}"


# Running and recording

class Execution(Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    UNSUPPORTED_BY_DESIGN = "UNSUPPORTED_BY_DESIGN"


@dataclass
class Result:
    input_format: str
    output_format: str
    declared: str
    fixture: str
    expected: str
    actual: str = ""
    execution: str = ""
    validation: str = ""
    failure: str = ""
    seconds: float = 0.0
    output_bytes: int = 0
    output_files: int = 0
    decoders: str = ""
    warnings: str = ""

    @property
    def status(self) -> Execution:
        if self.declared == Declared.UNSUPPORTED_BY_DESIGN.value:
            return Execution.UNSUPPORTED_BY_DESIGN
        if self.execution == "SKIPPED":
            return Execution.SKIPPED
        return Execution.PASSED if self.execution == "OK" and self.validation == "PASSED" else Execution.FAILED


RESULTS: list[Result] = []


def run_pair(spec: FixtureSpec, target: Target, out_dir: Path) -> Result:
    status, why = declared(spec.format, target)
    result = Result(spec.format, target.key, status.value, spec.name, expected_behavior(spec, target))
    RESULTS.append(result)
    if status is Declared.UNSUPPORTED_BY_DESIGN:
        result.execution, result.validation, result.actual = "SKIPPED", "n/a", why
        return result
    if status is Declared.CONDITIONAL:
        result.execution, result.validation, result.actual = "SKIPPED", "n/a", f"condition not met: {why}"
        return result

    options = Options(format=target.format, gif_mode=target.gif_mode)
    queue = QueueSummary(count=1, has_document=spec.kind != "raster", has_tiff=spec.format == "TIFF")
    job = plan_job(options, queue, [spec.path()], out_dir)
    progress = []
    started = time.perf_counter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            report = job(lambda done, total, path: progress.append((done, total)), lambda: False)
        except Exception as exc:  # the engine promises a report, never an exception
            result.seconds = time.perf_counter() - started
            result.execution, result.validation = "CRASHED", "FAILED"
            result.failure = f"{type(exc).__name__}: {exc}"
            return result
    result.seconds = round(time.perf_counter() - started, 3)
    result.warnings = "; ".join(sorted({str(w.message)[:120] for w in caught}))
    on_disk = sorted(p for p in out_dir.rglob("*") if p.is_file())
    result.output_files = len(on_disk)
    result.output_bytes = sum(p.stat().st_size for p in on_disk)
    result.execution = "OK" if not report.failures else "REPORTED_FAILURE"

    problems, facts = validate(spec, target, report, out_dir, on_disk, progress)
    if result.seconds > SLOW_SECONDS:
        problems.append(f"took {result.seconds:.0f}s, over the {SLOW_SECONDS}s budget")
    result.actual = facts.pop("actual", "")
    result.decoders = ", ".join(sorted(set(facts.get("decoders", []))))
    result.validation = "FAILED" if problems else "PASSED"
    result.failure = " | ".join(problems)
    if report.failures:
        result.execution = "REPORTED_FAILURE"
    return result


def validate(spec, target, report, out_dir, on_disk, progress) -> tuple[list[str], dict]:
    problems: list[str] = []
    facts: dict = {"decoders": []}
    for path, reason in report.failures:
        problems.append(f"engine reported {path.name}: {reason}")
    pages = expected_pages(spec, target)
    names = expected_names(spec, target, pages)
    got = [p.name for p in on_disk]
    if got != sorted(names):
        problems.append(f"files {got}, expected {sorted(names)}")
    if [p.name for p in report.outputs] != names:
        problems.append(f"report lists {[p.name for p in report.outputs]}, expected {names}")
    if not progress or progress[-1][0] != progress[-1][1]:
        problems.append(f"progress never reached the end: {progress[-3:]}")
    files = [out_dir / name for name in names if (out_dir / name).exists()]
    if not files:
        facts["actual"] = "no output"
        return problems, facts
    try:
        if target.format is OutputFormat.PDF:
            _check_pdf(spec, files[0], pages, problems, facts)
        elif target.key == "GIF" and animates(spec, target):
            _check_animation(spec, files[0], pages, problems, facts)
        else:
            _check_pictures(spec, target, files, problems, facts)
    except Exception as exc:  # a validator that can't read the output is a failed output
        problems.append(f"could not inspect output: {type(exc).__name__}: {exc}")
    return problems, facts


# Pictures

def _tolerance(spec: FixtureSpec, fmt: OutputFormat) -> tuple[float, float]:
    """(whole-picture, worst-quarter) mean difference allowed, out of 255, measured at 512 px. Calibrated on these
    fixtures: every default-quality chain stays under 3.1, a JPEG saved at quality 5 measures 8.4 or more. A 24x16
    picture loses about 6.5 to its source codec alone, so it has its own band."""
    tiny = max(spec.pages[0].size) < 64
    if spec.lossy or fmt in LOSSY_OUTPUTS:
        return (9.0, 14.0) if tiny else (4.0, 7.0)
    if fmt is OutputFormat.GIF or spec.format == "GIF":
        return (8.0, 12.0) if tiny else (3.5, 6.0)
    return 1.0, 2.0


def _check_alpha(spec: FixtureSpec, index: int, fmt: OutputFormat, image: Image.Image, problems: list[str],
                 where: str) -> None:
    alpha = spec.pages[index].alpha
    if alpha and fmt.keeps_alpha:
        clear = alpha_at(image, ALPHA_PROBES["clear"])
        opaque = alpha_at(image, ALPHA_PROBES["opaque"])
        half = alpha_at(image, ALPHA_PROBES["half"])
        if clear > 10 or opaque < 245:
            problems.append(f"{where}: transparency lost (clear area alpha {clear}, opaque area alpha {opaque})")
        if fmt is not OutputFormat.GIF and spec.format != "GIF" and not 100 <= half <= 156:
            problems.append(f"{where}: half-transparent band has alpha {half}, expected about 128")
    elif alpha:
        rgb = image.convert("RGBA").getpixel((int(ALPHA_PROBES["clear"][0] * image.width),
                                              int(ALPHA_PROBES["clear"][1] * image.height)))
        if min(rgb[:3]) < 230:
            problems.append(f"{where}: transparent area became {rgb[:3]}, expected white")
    elif "A" in image.getbands() and image.getchannel("A").getextrema()[0] < 250:
        problems.append(f"{where}: an opaque source came out with transparent pixels")


def _check_pictures(spec, target, files, problems, facts) -> None:
    fmt = target.format
    sizes = []
    for index, file in enumerate(files):
        where = file.name
        if (kind := sniff(file)) != SNIFFED[fmt]:
            problems.append(f"{where}: bytes say {kind}, expected {SNIFFED[fmt]}")
        with Image.open(file) as image:
            image.load()
            if image.format != fmt.pillow_format:
                problems.append(f"{where}: Pillow reads it as {image.format}")
            decoded = image.copy()
            frames = getattr(image, "n_frames", 1)
        if frames != 1:
            problems.append(f"{where}: {frames} frames, expected a still picture")
        decoder, size = second_decoder(file, SNIFFED[fmt])
        facts["decoders"] += ["Pillow", decoder]
        if size is not None and size != decoded.size:
            problems.append(f"{where}: {decoder} decodes {size}, Pillow {decoded.size}")
        sizes.append(decoded.size)
        if is_solid(decoded):
            problems.append(f"{where}: a single flat colour")
        if spec.kind == "raster":
            _compare_picture(spec, index, fmt, decoded, problems, where)
        elif spec.kind == "pdf":
            page = spec.pages[index]
            want = (round(page.size[0] * DPI / 72), round(page.size[1] * DPI / 72))
            if max(abs(a - b) for a, b in zip(decoded.size, want)) > 2:
                problems.append(f"{where}: {decoded.size}, expected about {want} at {DPI} dpi")
            if (seen := band_color(decoded)) and color_distance(seen, page.color) > 45:
                problems.append(f"{where}: shows the band {seen}, which is not {page.id}'s {page.color}")
            _compare_render(spec, index, fmt, decoded, pdf_render(spec.path(), index, DPI), problems, where)
            if page.has_text and ink(decoded) < 0.003:
                problems.append(f"{where}: blank page")
        else:
            if ink(decoded) < 0.003:
                problems.append(f"{where}: blank notebook page")
    if spec.kind == "notebook":
        _check_section_order(spec, [_open_rgb(f) for f in files], problems)
    facts["actual"] = f"{len(files)} {fmt.label} file(s), " + ", ".join(f"{w}x{h}" for w, h in sizes[:4]) + \
        ("..." if len(sizes) > 4 else "")


def _open_rgb(path: Path) -> Image.Image:
    with Image.open(path) as image:
        return image.convert("RGBA")


def _compare_picture(spec, index, fmt, decoded, problems, where) -> None:
    reference = spec.reference(index)
    if decoded.size != reference.size:
        problems.append(f"{where}: {decoded.size}, expected {reference.size} (upright)")
        return
    whole, quarter = _tolerance(spec, fmt)
    diff, worst = mae(decoded, reference, 512), quadrant_mae(decoded, reference)
    if diff > whole or worst > quarter:
        problems.append(f"{where}: differs from the source by {diff:.1f} (worst quarter {worst:.1f}); "
                        f"allowed {whole}/{quarter}")
    _check_alpha(spec, index, fmt, decoded, problems, where)


def _compare_render(spec, index, fmt, decoded, reference, problems, where) -> None:
    """A PDF page against PDFium's own drawing of the source page. PDFium is the renderer Papyr uses, so this
    catches what happens after rendering (scaling, colour, encoding, lost content), not a PDFium fault."""
    if decoded.size != reference.size:
        reference = reference.resize(decoded.size, Image.Resampling.LANCZOS)
    lossy = fmt in LOSSY_OUTPUTS or fmt is OutputFormat.GIF
    whole, quarter = RENDER_TOLERANCE[lossy]
    diff, worst = mae(decoded, reference, 512), quadrant_mae(decoded, reference)
    if diff > whole or worst > quarter:
        problems.append(f"{where}: differs from the source page by {diff:.1f} (worst quarter {worst:.1f}); "
                        f"allowed {whole}/{quarter}")


def _expected_frame(spec, index, canvas: tuple[int, int]) -> Image.Image:
    """The page as the animation should show it: as large as fits the canvas (PDF pages may grow, pictures may
    not), centred on white."""
    if spec.kind == "pdf":
        width, height = spec.pages[index].size
        scale = min(canvas[0] / width, canvas[1] / height)
        page = pdf_render(spec.path(), index, 72 * scale)
    else:
        page = spec.reference(index)
        scale = min(1.0, canvas[0] / page.width, canvas[1] / page.height)
    size = (max(1, round(spec.pages[index].size[0] * scale)), max(1, round(spec.pages[index].size[1] * scale)))
    page = page.convert("RGBA").resize(size, Image.Resampling.LANCZOS)
    frame = Image.new("RGBA", canvas, (255, 255, 255, 255))
    frame.alpha_composite(page, ((canvas[0] - size[0]) // 2, (canvas[1] - size[1]) // 2))
    return frame


def _presence(image: Image.Image, color, tolerance: int = 30) -> float:
    rgb = image.convert("RGB").resize((max(1, image.width // 4), max(1, image.height // 4)), Image.Resampling.NEAREST)
    pixels = list(rgb.get_flattened_data())
    return sum(1 for p in pixels if color_distance(p, color) <= tolerance) / max(1, len(pixels))


def _check_section_order(spec, pages: list[Image.Image], problems: list[str]) -> None:
    """Each notebook section has a figure in its own colour. Read top to bottom, page by page, they must come in
    order and all be there."""
    sections = spec.extra["sections"]
    seen = []
    for number, page in enumerate(pages, start=1):
        rgb = page.convert("RGB")
        rows = []
        for s in range(sections):
            mask_rows = _rows_with_color(rgb, PAGE_COLORS[s])
            if mask_rows:
                rows.append((min(mask_rows), s + 1))
        seen += [s for _, s in sorted(rows) if s not in seen]
    if seen != list(range(1, sections + 1)):
        problems.append(f"notebook figures appear in order {seen}, expected 1..{sections}")


def _rows_with_color(image: Image.Image, color) -> list[int]:
    small = image.resize((max(1, image.width // 4), max(1, image.height // 4)), Image.Resampling.NEAREST)
    w, h = small.size
    data = small.load()
    hits = []
    for y in range(h):
        count = sum(1 for x in range(w) if color_distance(data[x, y], color) <= 30)
        if count > w * 0.15:
            hits.append(y)
    return hits if len(hits) >= 3 else []


# Animations

def _check_animation(spec, file, pages, problems, facts) -> None:
    if sniff(file) != "GIF":
        problems.append(f"{file.name}: bytes say {sniff(file)}, expected GIF")
    info = parse_gif(file)
    facts["decoders"] += ["GIF parser", "Pillow"]
    if info.frames != pages:
        problems.append(f"{info.frames} frames, expected {pages}")
    if set(info.delays_ms) != {1000}:
        problems.append(f"frame delays {sorted(set(info.delays_ms))} ms, expected 1000")
    if info.loop != 0:
        problems.append(f"loop field {info.loop}, expected 0 (forever)")
    from PySide6.QtGui import QImageReader
    reader = QImageReader(str(file))
    if (qt_count := reader.imageCount()) not in (info.frames, 0):
        problems.append(f"Qt counts {qt_count} frames, the GIF holds {info.frames}")
    facts["decoders"].append("Qt")
    frames = gif_frames(file)
    if len(frames) != info.frames:
        problems.append(f"Pillow decodes {len(frames)} frames, the GIF holds {info.frames}")
    if spec.kind != "raster" and max(info.width, info.height) != 1000:
        problems.append(f"canvas {info.width}x{info.height}, expected a 1000 px long side (Balanced)")
    for number, (frame, following) in enumerate(zip(frames, frames[1:]), start=1):
        if mae(frame, following) < 1.0:
            problems.append(f"frames {number} and {number + 1} are the same picture")
    for number, frame in enumerate(frames, start=1):
        if ink(frame) < 0.003 or is_solid(frame):
            problems.append(f"frame {number} is blank")
    if spec.kind == "notebook":
        _check_section_order(spec, frames, problems)
    else:
        for index, frame in enumerate(frames[:len(spec.pages)]):
            expected = _expected_frame(spec, index, (info.width, info.height))
            diff, worst = mae(frame, expected, 512), quadrant_mae(frame, expected)
            whole, quarter = RENDER_TOLERANCE[True]
            if diff > whole or worst > quarter:
                problems.append(f"frame {index + 1} differs from its page by {diff:.1f} (worst quarter {worst:.1f})")
        colors = [page.color for page in spec.pages]
        for number, frame in enumerate(frames[:len(colors)], start=1):
            scores = [_presence(frame, color) for color in colors]
            if scores.index(max(scores)) != number - 1 or max(scores) < 0.01:
                problems.append(f"frame {number} looks like page {scores.index(max(scores)) + 1}")
    facts["actual"] = f"1 GIF, {info.frames} frames at {info.width}x{info.height}, delays " \
                      f"{sorted(set(info.delays_ms))} ms, loop {info.loop}"


# PDFs

def _check_pdf(spec, file, pages, problems, facts) -> None:
    if sniff(file) != "PDF":
        problems.append(f"{file.name}: bytes say {sniff(file)}, expected PDF")
    out = pdf_facts(file)
    facts["decoders"] += ["pypdf", "PDFium"]
    if (pdfium_pages := pdf_page_count_pdfium(file)) != out.pages:
        problems.append(f"PDFium counts {pdfium_pages} pages, pypdf {out.pages}")
    if out.pages != pages:
        problems.append(f"{out.pages} pages, expected {pages}")
    if spec.kind == "raster":
        for index, page in enumerate(spec.pages[:out.pages]):
            width, height = page.size
            want = (A4[1], A4[0]) if width > height else A4
            if max(abs(a - b) for a, b in zip(out.sizes[index], want)) > 0.5:
                problems.append(f"page {index + 1} is {out.sizes[index]}, expected A4 {want}")
            if out.images[index] != [(int(width), int(height))]:
                problems.append(f"page {index + 1} embeds {out.images[index]}, expected one {width}x{height} image")
            scale = max(1.0, min(4.0, 600 / max(width, height) * max(want) / 600))
            rendered = pdf_render(file, index, dpi=72 * scale)
            left, top, w, h = fit_on_page((width, height), want, MARGIN_PT)
            crop = rendered.crop((round(left * scale), round(top * scale), round((left + w) * scale),
                                  round((top + h) * scale)))
            # Drawing the picture onto the page and rendering it back resamples it: measured up to 3.5 (worst
            # quarter 6.5) on these fixtures, 6.4 (12.1) for the 24x16 ones.
            whole, quarter = (8.0, 14.0) if max(width, height) < 64 else (4.5, 8.0)
            reference = spec.reference(index)
            diff, worst = mae(crop, reference, 512), quadrant_mae(crop.resize(reference.size), reference)
            if diff > whole or worst > quarter:
                problems.append(f"page {index + 1} picture differs from the source by {diff:.1f} "
                                f"(worst quarter {worst:.1f})")
            if page.alpha:
                x, y = ALPHA_PROBES["clear"]
                pixel = crop.getpixel((int(x * crop.width), int(y * crop.height)))
                if min(pixel) < 230:
                    problems.append(f"page {index + 1}: transparent area drew as {pixel}, expected white")
    elif spec.kind == "pdf":
        source = pdf_facts(spec.path())
        for index, page in enumerate(spec.pages[:out.pages]):
            if max(abs(a - b) for a, b in zip(out.sizes[index], source.sizes[index])) > 0.5:
                problems.append(f"page {index + 1} is {out.sizes[index]}, the source page is {source.sizes[index]}")
            if page.has_text and page.id not in out.texts[index]:
                problems.append(f"page {index + 1} text lacks {page.id}")
            if len(out.images[index]) != len(source.images[index]):
                problems.append(f"page {index + 1} has {len(out.images[index])} images, "
                                f"the source has {len(source.images[index])}")
            rendered = pdf_render(file, index, dpi=36)
            if ink(rendered) < 0.003:
                problems.append(f"page {index + 1} is blank")
            if color_distance(band_color(rendered), page.color) > 30:
                problems.append(f"page {index + 1} band is {band_color(rendered)}, expected {page.color}")
        if spec.name == "pdf-mixed-content" and not all(word in "".join(out.texts) for word in ("Grüße", "Ελληνικά")):
            problems.append("Unicode text did not survive")
    else:
        _check_notebook_pdf(spec, file, out, problems)
    facts["actual"] = f"1 PDF, {out.pages} page(s), first page {out.sizes[0][0]:.0f}x{out.sizes[0][1]:.0f} pt" \
        if out.pages else "empty PDF"


def notebook_text_markers(spec: FixtureSpec) -> list[str]:
    sections = spec.extra["sections"]
    markers = ["NB_TITLE"]
    for s in range(1, sections + 1):
        markers += [f"NB_SECTION_{s:02d}", f"SAVED_OUTPUT_{s:02d}"]
        if s == 3 and sections >= 3:
            markers.append("TABLE_ROW_1")
    if sections > 1:
        markers.append("STALE_SAVED_RESULT")
    return markers


def _check_notebook_pdf(spec, file, out, problems) -> None:
    text = "\n".join(out.texts)
    position = -1
    for marker in notebook_text_markers(spec):
        found = text.find(marker, position + 1)
        if found < 0:
            problems.append(f"text {marker} missing or out of order")
        else:
            position = found
    if spec.extra["sections"] > 1 and out.pages < 2:
        problems.append(f"{out.pages} page for a long notebook")
    figures = sum(1 for page in out.images for w, h in page if (w, h) == (480, 140))
    if figures != spec.extra["sections"]:
        problems.append(f"{figures} of {spec.extra['sections']} saved figures embedded")
    pages = []
    for index in range(out.pages):
        rendered = pdf_render(file, index, dpi=50)
        pages.append(rendered)
        if ink(rendered) < 0.003:
            problems.append(f"page {index + 1} is blank")
    _check_section_order(spec, pages, problems)
    for marker in ("NB_TITLE", "SAVED_OUTPUT_01"):
        darkest = text_darkness(file, marker)
        if darkest is None or darkest > 100:
            problems.append(f"text {marker} is not visible on the page (darkest pixel {darkest})")
    for folder in (spec.path().parent, Path.cwd()):
        if (folder / EXECUTION_SENTINEL).exists():
            problems.append(f"notebook code ran: {folder / EXECUTION_SENTINEL} exists")


# Reports

def environment() -> dict:
    from importlib import metadata
    versions = {}
    for name in ("Pillow", "pillow-heif", "pypdf", "pypdfium2", "PySide6-Essentials", "ziamath", "Pygments", "pytest"):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = "missing"
    import pillow_heif
    versions["libavif"] = str(features.version("avif"))
    versions["libheif"] = pillow_heif.libheif_version()
    return {"python": platform.python_version(), "platform": platform.platform(), "machine": platform.machine(),
            "libraries": versions}


@dataclass
class PairSummary:
    input_format: str
    output_format: str
    declared: str
    status: str
    fixtures: int = 0
    passed: int = 0
    failures: list[str] = field(default_factory=list)


def summarize(results: list[Result]) -> list[PairSummary]:
    pairs: dict[tuple[str, str], PairSummary] = {}
    for row in input_rows():
        for target in targets():
            status, _ = declared(row, target)
            pairs[(row, target.key)] = PairSummary(row, target.key, status.value, "NOT_RUN")
    for result in results:
        pair = pairs[(result.input_format, result.output_format)]
        pair.fixtures += 1
        status = result.status
        if status is Execution.PASSED:
            pair.passed += 1
        elif status is Execution.FAILED:
            pair.failures.append(f"{result.fixture}: {result.failure}")
        rank = {"NOT_RUN": 0, "UNSUPPORTED_BY_DESIGN": 1, "SKIPPED": 2, "PASSED": 3, "FAILED": 4}
        if rank[status.value] > rank[pair.status]:
            pair.status = status.value
    return list(pairs.values())


def write_reports(results: list[Result], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    columns = list(Result.__dataclass_fields__)
    with open(directory / "conversion-matrix.csv", "w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(columns + ["status"])
        for result in sorted(results, key=_order):
            writer.writerow([getattr(result, c) for c in columns] + [result.status.value])
    pairs = summarize(results)
    (directory / "conversion-matrix.md").write_text(_markdown(results, pairs), encoding="utf-8")
    (directory / "run-summary.json").write_text(json.dumps({
        "environment": environment(), "pairs": [asdict(p) for p in pairs],
        "counts": _counts(results, pairs)}, indent=1, ensure_ascii=False), encoding="utf-8")


def _order(result: Result):
    keys = [t.key for t in targets()]
    return ROW_ORDER.index(result.input_format), keys.index(result.output_format), result.fixture


def _counts(results, pairs) -> dict:
    by = lambda attr, items: {s: sum(1 for i in items if getattr(i, attr) == s) for s in {getattr(i, attr) for i in items}}
    return {"input_formats": len(input_rows()), "output_targets": len(targets()), "possible_pairs": len(pairs),
            "declared": by("declared", pairs), "pair_status": by("status", pairs),
            "conversions_run": sum(1 for r in results if r.execution not in ("SKIPPED", "")),
            "conversion_status": {s.value: sum(1 for r in results if r.status is s) for s in Execution}}


SYMBOL = {"PASSED": "PASS", "FAILED": "**FAIL**", "SKIPPED": "skip", "UNSUPPORTED_BY_DESIGN": "n/a",
          "NOT_RUN": "not run"}


def _markdown(results: list[Result], pairs: list[PairSummary]) -> str:
    env = environment()
    keys = [t.key for t in targets()]
    grid = {(p.input_format, p.output_format): p for p in pairs}
    lines = ["# Conversion matrix", "",
             f"Generated by `pytest tests/test_conversion_matrix.py --report-dir tests/reports` on "
             f"{env['platform']} with Python {env['python']}.", "",
             "Rows are input formats Papyr reads, columns the outputs it offers. A cell is PASS only when every "
             "fixture of that input ran through the real engine and every output passed independent validation. "
             "`n/a` is unsupported by design. Cells show passed/run fixtures.", "",
             "| input \\ output | " + " | ".join(keys) + " |", "|" + "---|" * (len(keys) + 1)]
    for row in input_rows():
        cells = []
        for key in keys:
            p = grid[(row, key)]
            count = f" {p.passed}/{p.fixtures}" if p.status in ("PASSED", "FAILED") else ""
            cells.append(SYMBOL[p.status] + count)
        lines.append(f"| {row} | " + " | ".join(cells) + " |")
    counts = _counts(results, pairs)
    lines += ["", "## Counts", "", "```", json.dumps(counts, indent=1), "```", "", "## Every conversion", "",
              "| input | output | declared | fixture | expected | actual | status | seconds | bytes | decoders | "
              "failure |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(results, key=_order):
        failure = r.failure.replace("|", "/")[:400]
        lines.append(f"| {r.input_format} | {r.output_format} | {r.declared} | {r.fixture} | {r.expected} | "
                     f"{r.actual} | {r.status.value} | {r.seconds:.2f} | {r.output_bytes} | {r.decoders} | {failure} |")
    lines += ["", "## Environment", "", "```", json.dumps(env, indent=1), "```", ""]
    return "\n".join(lines)
