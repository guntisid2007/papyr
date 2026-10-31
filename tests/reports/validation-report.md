# Papyr 2.3.1 conversion validation report

Branch `test/comprehensive-conversion-validation`, from `main` at `5706e71` (Papyr 2.3.1), final commit `89a034e`.
Run on 2026-10-31 on macOS 27.0, Apple Silicon (arm64), Python 3.12.14. Library versions are in `run-summary.json`.

Every number here comes from a run on this machine. Windows and Linux were not run (see Platform coverage).

## Executive summary

| | Count |
|---|---|
| Input formats Papyr reads | 11: HEIC, HEIF, JPEG, PNG, WebP, AVIF, TIFF, BMP, GIF, PDF, Jupyter notebook |
| Output targets | 11: PDF, JPEG, PNG, HEIC, WebP, AVIF, TIFF, animated GIF, separate static GIFs, BMP, and notebook (not offered) |
| Possible input/output pairs | 121 |
| Declared supported | 110 |
| Unsupported by design | 11 (every input to notebook; Papyr never writes notebooks) |
| Conditional | 0 on this machine. A pair is marked CONDITIONAL and skipped when its AVIF or HEIC codec is missing. |
| Pairs executed | 110 of 110 supported |
| Pairs passed | 110 |
| Pairs failed | 0 (after the fixes below) |
| Pairs skipped | 0 |
| Individual conversions executed | 500 (50 fixtures, 1 to 6 per input format) |
| Conversions passed independent validation | 500 |
| Whole suite | 1129 tests passed in 6 min 35 s (395 existing, 734 new) |
| Bugs found in Papyr 2.3.1 (`main`) | 10: 9 fixed, 1 left as a product decision |
| Defects my own fixes introduced, caught in review | 2, fixed |

**Verdict: READY FOR BETA on macOS Apple Silicon**, provided the fixes on this branch ship. Not yet established for
Windows, Linux, or Intel Macs. See Release readiness.

## Method

Fixtures are generated with each format's real encoder from a fixed seed (`tests/fixture_factory.py`):

- **Pictures.** Each carries a gradient, text, shapes, one-pixel lines, and an orientation marker. Where the format
  allows it, there is also a fully transparent box and a half-transparent band.
- **Shapes and extras.** Landscape, portrait, 24x16, and 3200x2000 for every format. Extras: `.jpeg` and `.tif`
  extensions, 8-bit and 16-bit grayscale PNG, JPEG and HEIC stored sideways with EXIF orientation 6, a 3-page TIFF
  of mixed sizes, and 4-frame animated GIF and WebP.
- **PDFs, drawn with Qt.** One page of text. Twelve pages with alternating orientation. Seven pages covering text,
  an embedded photo, vectors, a landscape table, translucent shapes, Unicode, and a scanned page with no text layer,
  on Letter, A4, A5, and custom sizes. Every page carries a `PAGE_00N` identifier and its own colour band.
- **Notebooks.** Saved outputs only: Markdown, code, stdout, PNG figures, an HTML table, math, and Unicode. One
  code cell would create a sentinel file if it were ever run.

Each pair runs through `gui.model.plan_job`, the same call the window makes, into a temporary folder. Nothing is
mocked. Each output is then checked without trusting the converter:

- **Container.** Magic bytes name the format; HEIC and AVIF are checked by their `ftyp` brand.
- **Two decoders.** Pillow and a second decoder agree on the size. That was Qt for 394 outputs and `sips` for the
  50 AVIF outputs, which Qt cannot read.
- **Pictures from pictures.** Compared with a lossless reference at 512 px, with the worst quarter checked
  separately so rotation or mirroring can't hide in the average. Default-quality chains measure at most 3.1 out
  of 255. A JPEG at quality 5 measures 8.4 or more.
- **Pictures from PDFs and notebooks.** Compared with PDFium's drawing of the source page. They must also keep its
  dark text ink (recall) and add none (precision), each within one pixel. Every real output scores 1.000 on both.
- **Transparency.** Kept where the format has it, white where it doesn't, and never added to an opaque source.
- **PDFs.** Read by pypdf and drawn by PDFium: page count from both, page sizes, page text in order, embedded image
  count and pixel size, and ink on every page.
- **Notebooks.** Every heading and saved output in order, and visibly dark where PDFium places it. Notebook pictures
  and GIF frames are compared with the notebook laid out the way those outputs lay it out, after that layout's own
  text has been checked.
- **GIFs.** A block parser written for this suite reads frame count, per-frame delay, and the NETSCAPE loop count.
  Pillow and Qt cross-check the frame count. Every frame is compared with its page.

`tests/test_validator_sensitivity.py` plants 24 real defects in the engine and requires the matrix check to fail on
each:

- wrong container bytes, upside-down output, mirrored output, lost alpha, blank output, JPEG quality 5
- a lost page, reordered pages or frames, wrong GIF timing
- the dark-mode white notebook text that shipped once
- page content erased, sparse text erased, text blacked out into bars, saved notebook output dropped

All 24 are caught.

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

None of the 500 well-formed fixtures produced a wrong output, before or after the fixes. Every Papyr bug below came
from malformed, protected, or unusual inputs. The 19 failures in the first matrix run were all harness defects.

### Specific regressions

- **Notebook to PDF blank pages.** Every page is checked for ink, and the title and first saved output must be
  visibly dark where PDFium places them. A planted white-ink defect fails the check. A window test converts under a
  dark palette. All pass.
- **12-page PDF to one animated GIF.** One file, 12 frames, 1000 ms each, looping forever. Each frame matches its
  page, and no per-page GIFs are written. Separate static GIFs (`-page-001.gif` to `-page-012.gif`) appear only
  when that mode is chosen. Checked by the matrix, the behavior tests, and the window.
- **Notebook code is never run.** The sentinel file was never created. The stale saved output `STALE_SAVED_RESULT`
  appears in the PDF, not the `42` the code would print.

## Failure analysis

### Papyr bugs, fixed

Each bug has a failing test committed before its fix, and each fix commit makes those tests pass. Bugs 1 to 5 came
from this suite. Bugs 6 to 10 came from the cross-family review and were reproduced here before being fixed. Rows 8
and 9 were not in `main`: my own earlier fixes introduced them, and review caught them.

| # | Pair | Fixture | Root cause | Error before | Fix status |
|---|---|---|---|---|---|
| 1 | PDF to any picture format, animated GIF, or combined GIF | `pdf-twelve-pages` with 2000 bytes zeroed | `_render_page` and `pdf_page_sizes` let `pypdfium2.PdfiumError` escape. The window caught it as unexpected and the batch ended. | "Unexpected error: Failed to load page." Nothing converted, not even the valid PNG after it. | Fixed, `c38d17c`. The PDF is reported as damaged and the rest converts. |
| 2 | AES owner-restricted PDF to PDF | `restricted-aes-128.pdf`, `restricted-aes-256.pdf` (they open with no password, as statements and forms do) | pypdf needs `cryptography` for AES, and Papyr does not ship it. Its `DependencyError` escaped. | "Unexpected error: cryptography>=3.1 is required for AES algorithm." The rest of the queue was lost. | Fixed, `c38d17c`, refined in `550dc5d`. The page copy is all-or-nothing, and a real `DependencyError` becomes "This PDF is protected, so Papyr can only turn it into images, not a new PDF." Picture and GIF outputs of the same file work through PDFium. |
| 3 | Unsupported type to GIF | `.txt`, `.docx`, `.svg`, `.mp4`, no extension | `animation.measure` opened the file before the supported-type check. | "The file appears to be damaged." | Fixed, `c38d17c`. The message is now "This file format isn't supported." |
| 4 | Notebook to any output | `[1, 2, 3]` saved as `.ipynb` | Non-object JSON was treated as an old nbformat. | "This notebook uses an old format…" | Fixed, `c38d17c`. The message is now "This isn't a valid Jupyter notebook." |
| 5 | Empty `.pdf` to PDF | 0-byte file | pypdf's "Cannot read an empty file" matched no rule in `utils/errors.py`. | "This file couldn't be converted." | Fixed, `c38d17c`. The file is now reported as damaged. |
| 6 | TIFF to every output | 3-frame TIFF with the second frame's width tag removed | Pillow's TIFF plugin raised `TypeError`, which no converter caught. | Every batch kind raised; no file after it converted. | Fixed, `c9477aa`. Any error while Pillow decodes a file is that file's failure. |
| 7 | Unusual encrypted PDF to PDF | RC4 PDF with an unexpected `/SubFilter` (PDFium reads it) | pypdf raised `NotImplementedError`. | PDF batches raised. | Fixed, `c9477aa`. Any error while pypdf reads or copies a file is that file's failure, and its partial pages are removed. |
| 8 | Copyable restricted PDF to PDF | RC4 PDFs that list unused AES filters (`/V 2`, or `/V 4` with AES only for attachments) | The first fix for bug 2 predicted AES from the dictionary and got these wrong. | Refused with the AES message although pypdf copies them. | Fixed, `550dc5d`. The prediction is deleted; the copy itself decides. |
| 9 | Any input, when memory runs out | `MemoryError` planted in a decoder | The broader catch from bug 6 reported it as damage. | "The file appears to be damaged." on a valid file. | Fixed, `550dc5d`. The message is now "There isn't enough memory to convert this file.", and the batch goes on. |
| 10a | Notebook with an SVG attached to a Markdown cell, to every output | `![chart](attachment:chart.svg)` | Attachments were all base64-decoded. nbformat stores SVG as text, so the figure decoded to nothing. | The figure silently vanished. | Fixed, `89a034e`. |
| 10b | Notebook whose figure has a huge saved width, to every output | `"width": 10**400` | `float()` raised `OverflowError` while the notebook was read, and it escaped. | Every batch kind raised. | Fixed, `89a034e`. The width is ignored and the figure fits the page. Any other error from a malformed cell reports the notebook as damaged. |

Bugs 1, 2, 6, 7, and 10b share one root cause. Converters caught a fixed list of exception types, and third-party
decoders raise whatever a malformed file trips. Three point fixes failed against the same premise, so the fix moved
to the decode boundary. Wherever Papyr hands an untrusted file to Pillow, pypdf, PDFium, or the notebook parser,
any error becomes that file's failure, with a plain reason, and the batch continues.

Reproduce the first five before and after:

```sh
K="unloadable or aes or unsupported or bad_notebooks or zero_byte or damaged_pdf"
git worktree add --detach /tmp/before ba058ed && (cd /tmp/before && python -m pytest tests/test_conversion_edge_cases.py tests/test_gui_smoke.py -q -k "$K")
git worktree add --detach /tmp/after c38d17c && (cd /tmp/after && python -m pytest tests/test_conversion_edge_cases.py tests/test_gui_smoke.py -q -k "$K")
```

Measured: `11 failed, 16 passed` at `ba058ed`, and `27 passed` after the fix. The later bugs follow the same pattern:
the tests in `8ddffb7`, `f807804`, and `e6b43f9` fail, and they pass from the next commit on.

### Papyr bug, not fixed: a product decision

**11. A multi-page file that fails partway leaves its earlier pages.** A 3-page TIFF whose third page can't be
decoded gives `-page-1.png` and `-page-2.png`, or a 2-frame animated GIF, plus a "damaged" failure for the file.
PDF output is already all-or-nothing. The window reports the file as failed while some of its pages sit in the
folder. Making this all-or-nothing is easy for picture outputs: delete that file's pages on failure. Animated GIFs
are written frame by frame, so they would need to buffer each file's frames. Recommendation: make every output
all-or-nothing per file, which matches how merged PDFs already behave and keeps the window's counts honest.

### Harness defects found and fixed

These were mine, not Papyr's. They are listed because each one first looked like a Papyr failure, or let one pass.

| Symptom | Evidence | Fix |
|---|---|---|
| 9 cases: `tiff-multipage` pages 2 and 3 "lost transparency" | Only page 1 had alpha, but the spec marked the whole file. | Alpha became a per-page property. |
| 10 cases: `pdf-mixed-content` page 7 washed out | The fixture applied `/ca 0.431` to its scanned image, a brush state carried over from page 5 by `QPainter`. Papyr drew the fixture faithfully. | The fixture painter resets state per page. |
| A JPEG at quality 5 passed | Comparison at 128 px averaged its blocks away. | Compare at 512 px with calibrated bands. |
| PDF pages with the body erased passed | Only the colour band and page size were checked. | Compare with PDFium's drawing of the source page. Found in review. |
| Sparse pages with all text erased passed | One line of text is about 1% of a page. | Ink recall. Found in review. |
| Text blacked out into bars passed | Recall can't see added ink. | Ink precision. Found in review. |
| Notebook pictures with saved output missing passed | No text check on picture outputs. | Check the layout's text, then each page against it. Found in review. |
| Combined-GIF order test passed a reversed queue | It only checked that neighbouring frames differed. | It identifies each frame. Found in review. |
| A PDF cut short could pass with garbage output | The test accepted any output. | It requires a clean failure, which is what happens. Found in review. |

## Behavior beyond format pairs

All of these pass:

- **Multipage.** PDF to PNG, JPEG, WebP, and TIFF sequences come out in page order. PDF to WebP gives still pages,
  not an animation. A 3-page TIFF gives 3 files, 3 PDF pages, or 3 frames. Mixed pictures merge into one PDF in queue
  order with each picture's pixel size intact. PDFs and notebooks merge with their text searchable. A combined GIF
  holds every page of every file in queue order, with each frame identified.
- **Batches.** 1, 10, and 50 files to JPEG and to PDF. A mixed batch of every input format. Same names from
  different folders become `a`, `a (1)`, and `a (2)`. Converting again never overwrites earlier results or a file
  already in the folder. Damaged files in a batch are reported and the rest convert.
- **Settings.**
  - JPEG quality orders both size and error. WebP, AVIF, and HEIC quality change size. WebP at quality 100 is
    pixel-exact. TIFF output is Deflate-compressed.
  - A4 and Letter rotate to match the picture's orientation. Original page size is the picture plus margins. A
    25 mm margin leaves 25 mm blank, and an impossible margin fails with a reason.
  - PDF resolution (100, 150, 300 dpi) sets the pixel size.
  - GIF timing, loop count (forever, once, three times), and frame size (500, 1000, or 1600 px) all reach the file.
  - Camera and GPS metadata never reach any output.
- **Negative.**
  - Every case fails with a reason: zero-byte files of all 13 extensions, truncated pictures in 8 formats, PDFs cut
    short or zeroed, 5 kinds of bad notebook, 5 unsupported types, mismatched extensions, a TIFF frame Pillow
    can't read, a PDF pypdf can't read, and out-of-memory on one file. In each case the rest of the batch converts.
  - Password-protected PDFs say so. RC4 owner-only PDFs convert.
  - A PNG declaring 60000x60000 is refused in under a second without decoding it. A real 8000x6000 picture converts.
  - Unicode, emoji, spaces, and dots in names carry through. Deep folders work, and a missing output folder is
    created.
  - A read-only destination and an unreadable source fail with a reason. A file deleted after queueing is reported
    as gone.
  - Cancelling any of the 5 job kinds keeps finished files, leaves no `.part` file, and writes nothing for merged
    outputs.
- **Window (offscreen Qt).**
  - Each of 4 fixtures (sideways HEIC, 7-page PDF, long notebook, 3-page TIFF) was dropped onto the window and
    converted to each of the 10 offered outputs. Every output passed the matrix validator.
  - Dock options reach the file. A notebook under a dark palette has visible text.
  - A damaged PDF and an AES PDF in the queue no longer cost the other files.
  - Retry converts a fixed file. Progress counts up to the total.

## Performance

These figures are the engine call only, excluding validation, from the final run's `conversion-matrix.csv`.

| Measure | Value |
|---|---|
| Engine time, all 500 conversions | 34.2 s |
| Whole suite, 1129 tests | 6 min 35 s |
| Peak RSS of the whole test process | 1.34 GB (`/usr/bin/time -l`) |

Slowest pathways:

| Input | Output | Fixture | Seconds | Output size |
|---|---|---|---|---|
| IPYNB | HEIC | notebook-matrix (6 pages) | 1.52 | 1.16 MB |
| PDF | HEIC | pdf-twelve-pages | 1.35 | 0.19 MB |
| PDF | HEIC | pdf-mixed-content | 1.24 | 0.96 MB |
| IPYNB | AVIF | notebook-matrix | 1.05 | 0.29 MB |
| PDF | WEBP | pdf-twelve-pages | 0.94 | 0.13 MB |

Median seconds per output: PDF 0.005, JPEG 0.003, PNG 0.008, HEIC 0.079, WebP 0.011, AVIF 0.027, TIFF 0.005, GIF
0.028, BMP 0.002. Documents dominate: the median per input is 0.12 s for PDF and 0.20 s for notebooks, against
0.003 to 0.017 s for pictures.

The largest outputs are BMP pages rendered at 200 dpi: 134.6 MB for the 12-page PDF, about 11 MB per page. That is
inherent to uncompressed BMP.

**Peak memory per pathway** comes from `scripts/perf_probe.py`, with each path in a fresh process. Raw numbers are
in `perf-probe.json`. A process that only loads Python, Qt, and the codecs peaks at 111 MB, so conversion adds:

| Path | Seconds | Peak RSS | Added by the conversion |
|---|---|---|---|
| PNG 3200x2000 to HEIC | 0.49 | 459 MB | 348 MB |
| PNG 3200x2000 to AVIF | 0.17 | 373 MB | 262 MB |
| 7-page PDF to AVIF | 0.59 | 369 MB | 258 MB |
| 7-page PDF to HEIC | 1.19 | 364 MB | 253 MB |
| TIFF 3200x2000 to WebP | 0.23 | 246 MB | 135 MB |
| 7-page PDF to PNG | 0.22 | 237 MB | 126 MB |
| BMP 3200x2000 to PDF | 0.07 | 224 MB | 113 MB |
| notebook to GIF | 0.71 | 206 MB | 95 MB |
| JPEG 3200x2000 to JPEG | 0.05 | 198 MB | 87 MB |
| notebook to PDF | 0.73 | 187 MB | 76 MB |
| 12-page PDF to GIF | 0.28 | 141 MB | 30 MB |

The 12-page GIF's small footprint confirms the writer streams one frame at a time.

## Known limitations

- **Animated GIF and animated WebP inputs are read as their first frame.** This is documented in
  `converter.images.iter_pages` and verified by the matrix. An animated GIF converted to GIF comes out still. This is
  the most likely beta surprise.
- **A multi-page file that fails partway leaves its earlier pages** (bug 11).
- **AES-protected PDFs can become images, not a new PDF.** They fail cleanly and say so. Adding `cryptography` to
  `requirements.txt` would let pypdf copy them, but the copy would drop the owner's restrictions. That is a product
  call.
- No animated WebP output, and no multipage TIFF output; each page becomes its own file.
- No resize option for still pictures, and no PNG compression setting. `test_missing_settings_are_documented_not_faked`
  fails if a control is added.
- Multi-image HEIC yields its primary image only.
- The PDF fixtures carry Qt's creation date, so their bytes differ between builds. Their drawn content does not.
  Pictures and notebooks are byte-identical between builds.

## Platform coverage

| Platform | Engine matrix | Window (offscreen) | Packaged app |
|---|---|---|---|
| macOS 27 arm64 | Run: 500/500 | Run: all pass | Built from `89a034e` (2.3.1, arm64). `--self-test` passed, and the window launched and stayed up. Native drag and drop and the packaged window's controls were not automated. |
| macOS Intel | Not run | Not run | Not run |
| Windows | Not run | Not run | Not run |
| Linux | Not run | Not run | Not run |

`.github/workflows/conversion-validation.yml` runs the matrix and the rest of the suite on `macos-15`,
`windows-latest`, and `ubuntu-22.04`, and uploads each platform's report on its own. It has not been pushed.
Expected differences:

- Qt's HEIC plugin and `sips` exist only on macOS, so on Windows and Linux HEIC and AVIF outputs are checked by
  Pillow alone. The `decoders` column says so.
- Permission tests skip on Windows.
- Fixture fonts fall back per system; Linux CI installs DejaVu.

The existing `build.yml` also runs `pytest` on its four targets.

## Independent review

The fixes and the harness were reviewed by models from a different family than the author, which was Claude. The
reviewers ran GPT-6.1-Sol on two accounts, in three rounds on the fix diffs plus one slice review of notebooks,
multipage behavior, and test honesty. That gives 13 findings, all reproduced before acting: 12 fixed, and 1 left as
the product decision above. The last fix commit (`89a034e`) came after the third review round and has not had an
independent review. It is covered by its failing-then-passing tests and the full suite. Two Gemini review seats
ended without a report, and one GPT seat was blocked by its provider's content filter and rerun.

## Release readiness

**READY FOR BETA on macOS Apple Silicon, with this branch's fixes.**

- Every one of the 110 declared pairs ran through the real engine and passed independent validation across 500
  conversions.
- No well-formed input produced a blank, corrupt, misnamed, or wrongly ordered output.
- The two previously reported regressions are covered and pass.
- Before these fixes, one damaged TIFF or PDF, one AES-protected PDF, or one notebook with an unusual figure width
  in a queue silently cost the user every other file. Shipping `main` as it stands would ship that.

Before calling it ready everywhere:

1. Run `conversion-validation.yml` on Windows and Linux and read each platform's report.
2. Decide bug 11, partial pages on a late failure. Recommendation: all-or-nothing per file.
3. Decide whether an animated GIF converted to GIF should stay animated, or tell users only the first frame is used.
