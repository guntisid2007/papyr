# Papyr tests

Everything runs from the repository root with the project's virtual environment:

```sh
python -m pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

The first test that needs fixtures builds them into `tests/fixtures/generated/` (not committed). A run takes about
four minutes on an Apple Silicon laptop. Qt runs offscreen, so no window appears.

## Focused runs

| What | Command |
|---|---|
| Full conversion matrix, with reports | `python -m pytest tests/test_conversion_matrix.py --report-dir tests/reports` |
| One input row or output column | `python -m pytest tests/test_conversion_matrix.py -k "PDF-to"` or `-k "to-AVIF"` |
| Proof the matrix checks catch defects | `python -m pytest tests/test_validator_sensitivity.py` |
| PDF behavior | `python -m pytest tests -m pdf` |
| Animated GIF behavior | `python -m pytest tests -m animation` |
| Notebook conversion | `python -m pytest tests -m notebook tests/test_notebook.py tests/test_notebook_fixtures.py` |
| Bad inputs and hostile paths | `python -m pytest tests -m negative` |
| Batches | `python -m pytest tests -m batch` |
| Settings reach the file | `python -m pytest tests -m settings` |
| Window smoke tests | `python -m pytest tests -m gui_smoke` |
| Packaged app self-test | `dist/Papyr.app/Contents/MacOS/Papyr --self-test tests/fixtures/sample.heic` |
| Time and memory of the heaviest paths | `python scripts/perf_probe.py` (macOS and Linux) |
| Look at the fixtures | `python scripts/make_conversion_fixtures.py /tmp/papyr-fixtures` |

## How the matrix decides

`tests/conversion_matrix.py` takes its rows from `converter.INPUT_EXTENSIONS` and its columns from
`converter.OutputFormat`, plus the separate-GIF mode and a notebook column Papyr does not offer. A new extension or
format fails `test_every_input_extension_has_a_row_and_fixtures` until it is classified and given fixtures.

Each case runs one fixture through `gui.model.plan_job`, the call the window makes, into a temporary folder. The
output is then checked without trusting the converter:

- the first bytes name the right format (HEIC and AVIF by their `ftyp` brand)
- Pillow and a second decoder (Qt's image plugins, or `sips` on macOS for AVIF) agree on the size
- pictures match a lossless reference, measured at 512 px, with tolerances calibrated on these fixtures; the worst
  quarter is checked too, so a rotated or mirrored picture can't hide in the average
- transparency is kept where the format has it and becomes white where it doesn't
- PDFs are read with pypdf and drawn with PDFium: page count, page sizes, page text in order, embedded images, and
  ink on every page; notebook text must also be visibly dark where PDFium places it
- GIFs are parsed block by block here: frame count, delays, loop count, and frames in page order

`--report-dir` writes `conversion-matrix.csv`, `conversion-matrix.md`, and `run-summary.json` (library versions and
counts).

## Reproducibility

Fixtures come from a fixed seed. Pictures and notebooks are byte-identical between builds with the same library
versions; `manifest.json` in the fixture folder records them. The PDF fixtures differ only in the creation date Qt
writes. `restricted-aes-128.pdf` and `restricted-aes-256.pdf` are committed because writing AES needs the
`cryptography` package, which Papyr does not use.

Tests never touch real preferences (`conftest.py` points QSettings at a temporary folder) and write only into
pytest's temporary folders and the fixture folder.
