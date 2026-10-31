# Papyr 2.3.1 conversion validation report

Branch `test/comprehensive-conversion-validation`, from `main` at `5706e71` (Papyr 2.3.1). Run on 2026-10-31 on
macOS 27.0, Apple Silicon (arm64), Python 3.12.14. Library versions are in `run-summary.json`.

Every number here comes from a run on this machine. Windows and Linux were not run (see Platform coverage).

## Executive summary

| | Count |
|---|---|
| Input formats Papyr reads | 11 (HEIC, HEIF, JPEG, PNG, WebP, AVIF, TIFF, BMP, GIF, PDF, Jupyter notebook) |
| Output targets | 11 (PDF, JPEG, PNG, HEIC, WebP, AVIF, TIFF, animated GIF, separate static GIFs, BMP, and notebook, which Papyr does not offer) |
| Possible input/output pairs | 121 |
| Declared supported | 110 |
| Unsupported by design | 11 (every input to notebook; Papyr never writes notebooks) |
| Conditional | 0 on this machine (AVIF and HEIC encoders were present; the matrix marks a pair CONDITIONAL and skips it when a codec is missing) |
| Pairs executed | 110 of 110 supported |
| Pairs passed | 110 |
| Pairs failed | 0 (after fixes; see Failure analysis) |
| Pairs skipped | 0 |
| Individual conversions executed | 500 (50 fixtures, 1 to 6 per input format) |
| Conversions passed independent validation | 500 |
| Whole suite | 1105 tests passed in 4 min 49 s (395 existing and 710 new) |

**Verdict: READY FOR BETA on macOS, with three conditions.** These are listed under Release readiness.

## Method

Fixtures are generated with each format's real encoder from a fixed seed (`tests/fixture_factory.py`). Pictures
carry a gradient, text, shapes, one-pixel lines, an orientation marker, and, where the format allows it, a fully
transparent box and a half-transparent band. Shapes cover landscape, portrait, 24x16, and 3200x2000. Extras cover
`.jpeg` and `.tif` extensions, 8-bit and 16-bit grayscale PNG, JPEG and HEIC stored sideways with EXIF orientation 6,
a 3-page TIFF with mixed sizes, and 4-frame animated GIF and WebP. The PDFs are drawn with Qt. They cover 1 page of
text, 12 pages with alternating orientation, and a 7-page document with text, an embedded photo, vectors, a
landscape table, translucent shapes, Unicode, and a scanned page with no text layer. Page sizes are Letter, A4, A5,
and custom. Every page carries a `PAGE_00N` identifier and its own colour band. The two notebooks hold saved outputs
only: Markdown, code, stdout, PNG figures, an HTML table, math, and Unicode. One code cell would create a sentinel
file if it were ever run.

Each pair runs through `gui.model.plan_job`, the same call the window makes, into a temporary folder. Nothing is
mocked. The output is then checked without trusting the converter:

- Magic bytes name the format (HEIC and AVIF by their `ftyp` brand).
- Pillow and a second decoder agree on the size. On this machine that was Qt for 394 outputs and `sips` for 50 AVIF
  outputs.
- Pictures are compared to a lossless reference at 512 px, and the worst quarter is checked separately.
  Tolerances were measured on these fixtures: default-quality chains stay at or below 3.1 out of 255, and a JPEG
  at quality 5 measures 8.4 or more.
- Alpha probes check that transparency is kept, or composited onto white for JPEG, BMP, and PDF. They also check
  that opaque sources gain no transparency.
- PDFs are read by pypdf and drawn by PDFium. The checks cover page count from both, page sizes, page text and its
  order, embedded image count and pixel size, ink on every page, colour bands in order, and for notebooks, text
  that is visibly dark where PDFium places it.
- GIFs go through a block parser written for this suite, which reads frame count, per-frame delay, and the
  NETSCAPE loop count. Pillow and Qt cross-check the frame count, and frames are checked to be distinct and in
  page order.

`tests/test_validator_sensitivity.py` plants eleven real defects in the engine and requires the matrix check to
fail each one: wrong container bytes, upside-down output, mirrored output, lost alpha, blank output, JPEG
quality 5, a lost PDF page, reordered pages, reordered or missing animation frames, wrong GIF timing, and the
dark-mode white notebook text that shipped once. All eleven are caught. That suite first exposed a gap. The original
tolerance, measured at 128 px, let the quality-5 JPEG pass, so the measurement moved to 512 px with calibrated
bands.

## Conversion matrix

`PASS n/m` means n of m fixtures passed. Per-fixture rows, timings, sizes, and decoders are in
`conversion-matrix.md` and `conversion-matrix.csv`.

| input \ output | PDF | JPEG | PNG | HEIC | WEBP | AVIF | TIFF | GIF | GIF_SEPARATE | BMP | IPYNB |
|---|---|---|---|---|---|---|---|---|---|---|---|
| HEIC | PASS 5/5 | PASS 5/5 | PASS 5/5 | PASS 5/5 | PASS 5/5 | PASS 5/5 | PASS 5/5 | PASS 5/5 | PASS 5/5 | PASS 5/5 | n/a |
| HEIF | PASS 4/4 | PASS 4/4 | PASS 4/4 | PASS 4/4 | PASS 4/4 | PASS 4/4 | PASS 4/4 | PASS 4/4 | PASS 4/4 | PASS 4/4 | n/a |
| JPEG | PASS 6/6 | PASS 6/6 | PASS 6/6 | PASS 6/6 | PASS 6/6 | PASS 6/6 | PASS 6/6 | PASS 6/6 | PASS 6/6 | PASS 6/6 | n/a |
| PNG | PASS 6/6 | PASS 6/6 | PASS 6/6 | PASS 6/6 | PASS 6/6 | PASS 6/6 | PASS 6/6 | PASS 6/6 | PASS 6/6 | PASS 6/6 | n/a |
| WEBP | PASS 5/5 | PASS 5/5 | PASS 5/5 | PASS 5/5 | PASS 5/5 | PASS 5/5 | PASS 5/5 | PASS 5/5 | PASS 5/5 | PASS 5/5 | n/a |
| AVIF | PASS 4/4 | PASS 4/4 | PASS 4/4 | PASS 4/4 | PASS 4/4 | PASS 4/4 | PASS 4/4 | PASS 4/4 | PASS 4/4 | PASS 4/4 | n/a |
| TIFF | PASS 6/6 | PASS 6/6 | PASS 6/6 | PASS 6/6 | PASS 6/6 | PASS 6/6 | PASS 6/6 | PASS 6/6 | PASS 6/6 | PASS 6/6 | n/a |
| BMP | PASS 4/4 | PASS 4/4 | PASS 4/4 | PASS 4/4 | PASS 4/4 | PASS 4/4 | PASS 4/4 | PASS 4/4 | PASS 4/4 | PASS 4/4 | n/a |
| GIF | PASS 5/5 | PASS 5/5 | PASS 5/5 | PASS 5/5 | PASS 5/5 | PASS 5/5 | PASS 5/5 | PASS 5/5 | PASS 5/5 | PASS 5/5 | n/a |
| PDF | PASS 3/3 | PASS 3/3 | PASS 3/3 | PASS 3/3 | PASS 3/3 | PASS 3/3 | PASS 3/3 | PASS 3/3 | PASS 3/3 | PASS 3/3 | n/a |
| IPYNB | PASS 2/2 | PASS 2/2 | PASS 2/2 | PASS 2/2 | PASS 2/2 | PASS 2/2 | PASS 2/2 | PASS 2/2 | PASS 2/2 | PASS 2/2 | n/a |

The matrix holds only after the harness fixes and engine fixes below. The first run had 19 failing cases. All 19
came from the harness, as the Failure analysis shows.

### Specific regressions

- **Notebook to PDF blank pages.** Covered in four places. The matrix checks every page for ink and checks that
  `NB_TITLE` and `SAVED_OUTPUT_01` are visibly dark where PDFium places them. A sensitivity test plants white ink
  and confirms the check fails. A window test converts under a dark palette, and `test_notebook_fixtures.py`
  already existed. All pass.
- **12-page PDF to one animated GIF.** One file with 12 frames, 1000 ms each, looping forever, frames in page order,
  and no stray per-page GIFs. Checked by the matrix (`pdf-twelve-pages`), by
  `test_twelve_page_pdf_becomes_one_animated_gif_with_twelve_frames_and_no_stray_files`, and in the window. Separate
  static GIFs (`-page-001.gif` to `-page-012.gif`) appear only when that mode is chosen. Both paths pass.
- **Notebook code is never run.** The sentinel file was never created. The stale saved output
  `STALE_SAVED_RESULT` appears in the PDF, not the value `42` the code would print.

## Failure analysis

### Papyr bugs found and fixed (commit `c38d17c`)

Each has a failing test in `ba058ed` that passes after `c38d17c`.

| # | Pair | Fixture | Root cause | Error before | Fix |
|---|---|---|---|---|---|
| 1 | PDF to any picture format, animated GIF, or combined GIF | `pdf-twelve-pages` with 2000 bytes zeroed (`damaged.pdf`) | `_render_page` and `pdf_page_sizes` let `pypdfium2.PdfiumError` escape. It is not one of the converter's per-file errors, so the window's worker caught it as unexpected and the batch ended. | Window: "Unexpected error: Failed to load page." Nothing converted, not even the valid PNG queued after it. | PDFium page errors become `ImageLoadError` where pages are read. The damaged file is reported as damaged, and the rest of the queue converts. |
| 2 | AES owner-restricted PDF to PDF | `tests/fixtures/restricted-aes-128.pdf`, `restricted-aes-256.pdf` (open with no password, as bank statements and forms usually do) | pypdf needs the `cryptography` package for AES, and Papyr does not ship it. AES-256 failed as the reader opened, and AES-128 failed later, mid-copy inside `add_page`. Its `DependencyError` escaped the same way. | "Unexpected error: cryptography>=3.1 is required for AES algorithm." The rest of the queue was lost. | The PDF's `/Encrypt` dictionary is read before any page is copied, and an AES document is refused as one file with "This PDF is protected, so Papyr can only turn it into images, not a new PDF." Picture and GIF outputs of the same files already worked through PDFium and still do. |
| 3 | Unsupported type to GIF | `notes.txt`, `.docx`, `.svg`, `.mp4`, no extension | `animation.measure` opened the file before the supported-type check that every other path runs. | "The file appears to be damaged." | `measure` checks the type first, so the message is "This file format isn't supported." |
| 4 | Notebook to any output | `[1, 2, 3]` saved as `.ipynb` | `parse_notebook` treated any non-object JSON as an old nbformat. | "This notebook uses an old format that Papyr can't read." | Non-object JSON is reported as "This isn't a valid Jupyter notebook." |
| 5 | Empty `.pdf` to PDF | 0-byte file | pypdf's "Cannot read an empty file" matched no rule in `utils/errors.py`. | "This file couldn't be converted." | Added a rule, so the message is "The file appears to be damaged." |

Reproduce before and after, each in a scratch worktree:

```sh
K="unloadable or aes or unsupported or bad_notebooks or zero_byte or damaged_pdf"
git worktree add --detach /tmp/before ba058ed && (cd /tmp/before && python -m pytest tests/test_conversion_edge_cases.py tests/test_gui_smoke.py -q -k "$K")
git worktree add --detach /tmp/after c38d17c && (cd /tmp/after && python -m pytest tests/test_conversion_edge_cases.py tests/test_gui_smoke.py -q -k "$K")
```

Measured: `11 failed, 16 passed` at `ba058ed`, and `27 passed` after the fix.

### Harness defects found and fixed during the audit

These were mine, not Papyr's. They are listed because each one first looked like a Papyr failure.

| Symptom in run 1 | Evidence | Fix |
|---|---|---|
| 9 cases: `tiff-multipage` pages 2 and 3 "lost transparency" | Only page 1 of that fixture was generated with alpha, but the spec marked the whole file. | Alpha became a per-page property. |
| 10 cases: `pdf-mixed-content` page 7 band washed out | The fixture's own content stream applied `/GState34` with `/ca 0.431` to the scanned image. That was the translucent brush from page 5, carried over by `QPainter`. The embedded image was correct. Papyr rendered the fixture faithfully. | The fixture painter saves and restores state per page. |
| A JPEG at quality 5 passed | Picture comparison at 128 px averaged block artifacts away. | Compare at 512 px with tolerances calibrated per chain. |

## Behavior beyond format pairs

All of these pass:

- **Multipage.** PDF to PNG, JPEG, WebP, and TIFF sequences come out in page order. PDF to WebP gives still pages,
  not an animation. A 3-page TIFF gives 3 files, 3 PDF pages, or 3 frames. Mixed pictures merge into one PDF in queue
  order with each picture's pixel size intact. PDFs and notebooks merge with their text still searchable. A combined
  GIF holds every page of every file in queue order.
- **Batches.** 1, 10, and 50 files to JPEG and to PDF. A mixed batch of every input format. Same names from
  different folders become `a`, `a (1)`, and `a (2)`. Converting again never overwrites earlier results or a file
  already in the folder. Damaged files in a batch are reported and the rest convert.
- **Settings.** JPEG quality orders both size and error. WebP, AVIF, and HEIC quality change size. WebP at quality
  100 is pixel-exact. TIFF output is Deflate-compressed. A4 and Letter rotate to match the picture's orientation.
  Original page size is the picture plus margins. A 25 mm margin leaves 25 mm blank, and an impossible margin fails
  with a reason. PDF resolution (100, 150, 300 dpi) sets the pixel size. GIF timing, loop count (forever, once,
  three times), and frame size (500, 1000, or 1600 px long side) all reach the file. Camera and GPS metadata never
  reach any output.
- **Negative.** Zero-byte files of all 13 extensions fail with a reason, as do truncated pictures in 8 formats, PDFs
  cut short or zeroed in the middle, 5 kinds of bad notebook, 5 unsupported types, and contents that don't match
  their extension. Password-protected PDFs say so. An RC4 owner-only PDF converts. A PNG declaring 60000x60000
  is refused in under a second without decoding it. A real 8000x6000 picture converts. Unicode, emoji, spaces,
  and dots in names carry through. Deep folders work, and a missing output folder is created. A read-only
  destination and an unreadable source fail with a reason. A file deleted after queueing is reported as gone.
  Cancelling any of the 5 job kinds keeps finished files, leaves no `.part` file, and writes nothing for merged
  outputs.
- **Window (offscreen Qt).** Each of 4 fixtures (sideways HEIC, 7-page PDF, long notebook, 3-page TIFF) was dropped
  onto the window and converted to each of the 10 offered outputs. Every output passed the matrix validator. Dock
  options reach the file. A notebook under a dark palette has visible text. A damaged PDF and an AES PDF in the queue
  no longer cost the other files. Retry converts a fixed file. Progress counts up to the total.

## Performance

These figures are the engine call only, excluding validation, from the matrix run in `conversion-matrix.csv`.

| Measure | Value |
|---|---|
| Engine time, all 500 conversions | 34.5 s |
| Whole matrix run, including fixture build and validation | 112 s (first run) |
| Peak RSS of the whole test process (1105 tests) | 1.40 GB (`/usr/bin/time -l`) |

Slowest pathways:

| Input | Output | Fixture | Seconds | Output |
|---|---|---|---|---|
| IPYNB | HEIC | notebook-matrix | 1.56 | 6 pages, 1700x2200, 1.16 MB |
| PDF | HEIC | pdf-twelve-pages | 1.40 | 12 pages, 0.19 MB |
| PDF | HEIC | pdf-mixed-content | 1.21 | 7 pages, 0.96 MB |
| IPYNB | AVIF | notebook-matrix | 1.03 | 6 pages, 0.29 MB |
| PDF | WEBP | pdf-twelve-pages | 0.93 | 12 pages, 0.13 MB |

Median seconds per output: PDF 0.004, JPEG 0.003, PNG 0.009, HEIC 0.079, WebP 0.010, AVIF 0.025, TIFF 0.005,
GIF 0.027, BMP 0.003. Documents dominate. The median per input is 0.12 s for PDF and 0.20 s for notebooks, against
0.003 to 0.018 s for pictures.

The largest outputs are BMP pages rendered at 200 dpi: 134.6 MB for the 12-page PDF, about 11 MB per page. That is
inherent to uncompressed BMP. Users choosing BMP for documents will get large files.

Per-pathway peak memory: see `perf-probe.json` (produced by `python scripts/perf_probe.py`).

## Known limitations

- **Animated GIF and animated WebP inputs are read as their first frame.** This is documented in
  `converter.images.iter_pages` and verified by the matrix (`gif-animated` and `webp-animated` match frame 1). An
  animated GIF converted to GIF comes out as a still picture. This is the most likely beta surprise.
- **AES-protected PDFs cannot become a new PDF.** After fix 2 they fail cleanly and say images still work. Adding
  `cryptography` to `requirements.txt` would let pypdf copy them. That is a product call, because the copy would
  drop the owner's restrictions.
- No animated WebP output. PDF to WebP gives one still per page.
- No multipage TIFF output. Each page becomes its own `.tiff`.
- No resize option for still pictures, and no PNG compression setting. GIF frame size is the only scaling control.
  `test_missing_settings_are_documented_not_faked` fails if a control is added, so the matrix learns about it.
- A PDF with an unreadable page in the middle gives the readable pages before it plus a "damaged" failure for the
  file. This matches how multipage TIFFs already behave.
- Multi-image HEIC (bursts, depth maps) yields its primary image only, per the same docstring.
- Fixture PDFs carry Qt's creation date, so they are not byte-identical between builds. Their drawn content is.

## Platform coverage

| Platform | Engine matrix | Window (offscreen) | Packaged app |
|---|---|---|---|
| macOS 27 arm64 | Run: 500/500 | Run: all pass | Built from this branch (2.3.1, arm64, 111 MB). `--self-test` passed. The window launched and stayed up. Native drag and drop was not automated. |
| macOS Intel | Not run | Not run | Not run |
| Windows | Not run | Not run | Not run |
| Linux | Not run | Not run | Not run |

`.github/workflows/conversion-validation.yml` runs the matrix and the rest of the suite on `macos-15`,
`windows-latest`, and `ubuntu-22.04`, and uploads each platform's report on its own. It has not been pushed. Known
differences to expect:

- Qt's HEIC plugin exists only on macOS, and `sips` only on macOS. On Windows and Linux, HEIC and AVIF outputs will
  be checked by Pillow alone, and the report's `decoders` column says so.
- Permission tests skip on Windows.
- Fixture fonts fall back per system. Linux CI installs DejaVu for the Greek and Cyrillic text.

The existing `build.yml` also runs `pytest` on all four of its targets, so these tests will run there too.

## Release readiness

**READY FOR BETA on macOS Apple Silicon.** Every one of the 110 declared pairs ran through the real engine and
passed independent validation across 500 conversions. The two previously reported regressions are covered and
pass. Invalid inputs fail one file at a time with a plain reason. No supported conversion produced a blank,
corrupt, misnamed, or wrongly ordered output.

Before calling it ready on every platform:

1. Run `conversion-validation.yml` on Windows and Linux, and read each platform's report. A macOS pass proves
   nothing there.
2. Ship the batch-isolation fix in `c38d17c`. Without it, one damaged or AES-protected PDF in a queue silently
   costs the user every other file.
3. Decide whether an animated GIF converted to GIF should stay animated, or say in the app that only the first frame
   is used.
