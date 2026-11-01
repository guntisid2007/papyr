# Papyr 2.3.1 beta readiness report

> Superseded for the release decision by [`beta-release-readiness.md`](beta-release-readiness.md) (2026-11-01). Kept as the MacBook record.

Branch `test/comprehensive-conversion-validation`. The fixes are in three commits on top of `fa30405`:
`2ae1e81`, `99751f2`, and `c8e71f7`. Every number below comes from runs on 2026-10-31 on macOS 27.0, Apple Silicon
(arm64), Python 3.12.14, Pillow 13.0.0, pypdf 6.21.4, pypdfium2 5.14.0, pillow-heif 1.8.1 (libheif 1.23.6), and
PySide6 6.12.0. Nothing ran on Windows, Linux, or an Intel Mac.

## Recommendation

**READY FOR LIMITED BETA, on macOS Apple Silicon only.**

- **Data integrity.** The partial-output defect is fixed and tested at every page position for all five
  conversion paths. A damaged file can no longer leave some of its pages behind or replace an existing file. It
  also can no longer stop the rest of the batch.
- **Matrix.** All 110 declared pairs pass independent validation, 500 of 500 conversions, with nothing skipped.
- **Packaged app.** It builds from this branch and passes its self-test. It converts through its own bundled
  libraries: a damaged multi-page TIFF leaves nothing behind while the good file beside it converts, and an
  animated GIF becomes a WebP with its timing kept.

Three things keep this from a public beta.

1. **Three of the four desktop platforms are untested.** The validation workflow is ready for macOS Intel,
   Windows, and Linux, but it has not run, because pushing it needs your authorization. The README's "Supported
   systems" table says each platform is "Built and tested in CI on every release". That is true of `build.yml` on
   `main`. It is not yet true of this branch.
2. **The macOS app has only an ad-hoc signature and is not notarized.** Gatekeeper blocks it until each user
   approves it by hand. The README already says so.
3. **No person has driven the window by hand on this branch.** Window behavior is covered by 105 offscreen
   automated tests (`test_gui.py` and `test_gui_smoke.py`), and the packaged app was launched and displayed its welcome screen (screenshot, 14:04). No
   one has used real system file dialogs, real drag and drop from Finder, or window resizing.

## Functional reliability

| | Result |
| --- | --- |
| Whole suite, `pytest tests/` | 1217 collected, 1217 passed, 0 failed, 0 skipped (6 min 26 s) |
| Before this work | 1129 passed at `fa30405` |
| New tests | 88: 48 for atomic outputs, 23 for animation, and the rest in GUI, model, errors, and filenames |
| Matrix pairs | 121 possible, 110 supported, 11 unsupported by design (writing notebooks) |
| Supported pairs passed | 110 of 110 |
| Conversions validated independently | 500 of 500 passed, 0 failed, 0 skipped |
| Validator sensitivity, `test_validator_sensitivity.py` | Passes. The matrix still catches every planted defect. |

The matrix checks each output without trusting the converter. It checks the format's magic bytes, and Pillow and a
second decoder (Qt or `sips`) must agree on the dimensions. It also checks page and frame counts, a pixel
comparison against lossless references, transparency, and text and ink on PDF pages. For animations it checks
delays and loop counts read by a separate GIF block parser. Four animated pairs changed their expected result in
this work: GIF to GIF, GIF to WebP, WebP to GIF, and WebP to WebP. Each now checks all four frames against
per-frame references, along with 200 ms durations and the loop-forever setting. Before, the expectation was
"first frame only". The reports are `conversion-matrix.md`, `conversion-matrix.csv`, and `run-summary.json`.

### Remaining limitations

- **Encrypted PDFs.** AES-encrypted PDFs that open without a password can become images and GIFs but not a new
  PDF. pypdf needs the `cryptography` package to decrypt AES, which Papyr does not ship. Copying the pages would
  also drop the owner's restrictions. Papyr reports "This PDF is protected, so Papyr can only turn it into images,
  not a new PDF." `test_aes_restricted_pdfs_never_end_the_batch` covers this. The README documents it.
- **A decision for you.** RC4-encrypted PDFs with only an owner password do become a new PDF today, and the copy
  drops their restrictions. An earlier commit chose this, and
  `test_a_pdf_with_only_an_owner_password_opens_like_any_other` pins it. That conflicts with "do not discard
  security protections". I left it unchanged because it is a product call. Refusing PDF output for every
  encrypted PDF would make the two cases consistent.
- **Animated WebP output uses memory.** Pillow holds every frame while it encodes, so animations over 128 Mi
  pixels in total are refused by name. Measured: 120 frames of 1000 × 800 (96 M pixels) used 478 MB peak.
- **libwebp merges identical frames.** It folds a frame identical to the one before it into that frame's duration.
  Playback looks the same and total time is kept (tested), but the frame count drops.
- **Animated PNG and multi-image HEIC** still convert their first image only. The README says so.
- **Three lower-impact GUI items** from the audit are not fixed. Edit > Remove Selected greys out while the Edit
  menu is open, though Delete, Backspace, and the row's × still work. Thumbnails of removed rows stay cached for
  the session. A duplicate dropped together with a new file is skipped without a notice.
- **Leftover temporary files.** If Papyr crashes or loses power mid-write, a hidden `.papyr-*.part` file can remain
  in the destination folder. Normal failures and cancellation remove them (tested). Papyr ignores hidden files when
  adding a folder, so a leftover is never converted.

## Bug fixes

Each fix has a test that fails on `fa30405` and passes now, unless noted.

| # | Defect | Root cause | Fix | Tests |
| --- | --- | --- | --- | --- |
| 1 | A 3-page TIFF failing on page 3 left pages 1 and 2 as PNGs | `convert_images` moved each page into place as it was written | `_Staged` in `convert.py` writes every file of a source to hidden temp files beside the destination, then moves them all into place. If a move fails, the files already placed are removed. | `test_a_page_failing_leaves_none_of_its_files` (15 cases), `test_a_move_failing_part_way_takes_back_the_files_already_moved` |
| 2 | An animated GIF or combined GIF kept the frames of a source that failed part way | `_write_animation` caught the error and wrote the frames it already had | `GifWriter.checkpoint` and `rollback` truncate the stream back to before that source | `test_an_animation_failing_after_its_first_frame_keeps_none_of_its_frames` |
| 3 | Cancelling mid-file kept that file's finished pages | Same as 1 | Same as 1 | `test_cancelling_mid_source_leaves_only_finished_sources` (5 cases) |
| 4 | A file created at the output name mid-run was overwritten | `os.replace` after an earlier existence check | Names are claimed with `os.link`, which never overwrites. Disks without hard links claim the name with an exclusive create. | `test_a_name_taken_while_converting_is_not_overwritten`, `test_without_hard_links_a_name_taken_mid_run_is_still_not_overwritten` |
| 5 | Animated GIF and WebP lost their animation (first frame only) | `iter_pages` read only frame 0 of non-TIFF files | WebP output and animated GIF output keep every frame, its duration, and its play count. Still formats and PDF get an **Every frame** toggle, which is shown only when an animated file is queued and the format can't animate. | `test_animation_formats.py` (23), 4 matrix pairs, `test_every_frame_*` |
| 6 | Animated WebP durations read as 0 | WebP reports `duration` only after the frame is decoded | Decode before reading the duration | Matrix WebP rows, `test_animation_becomes_animated_gif_with_its_timing` |
| 7 | Transparent animations became black in WebP | libwebp crops frames to what changed and then leaves out the file's alpha flag, and Pillow trusts the flag | Write whole keyframes (`kmin=0, kmax=1`) when any frame has transparency | `test_transparency_and_disposal_come_through_as_shown` |
| 8 | An unexpected exception (for example `RuntimeError`) ended the job, and the window said nothing was converted although files existed | `_ERRORS` listed four exception types | Any `Exception` while converting a source is that source's failure. Cancel and nothing-readable are `BaseException`. | `test_an_unexpected_error_is_that_files_failure_and_keeps_the_rest` (5) |
| 9 | Quit during a conversion aborted the process (exit 134) | The Quit action called `QApplication.quit` and skipped `closeEvent`, which joins the worker | Quit closes the window first | `test_quit_during_a_conversion_stops_and_joins_the_worker` |
| 10 | A preview finishing after the window closed raised `Signal source has been deleted` | The thumbnail task emitted on a deleted loader | The emit catches the deleted-object error | `test_a_preview_finishing_after_the_window_closed_is_dropped` |
| 11 | An empty folder dropped on Done brought the finished batch back | `add_paths` replaced the queue only when it found files | A drop on Done always starts a new list | `test_an_empty_folder_dropped_on_done_starts_an_empty_batch` |
| 12 | Web links dragged onto the window were accepted and then ignored | The drag accepted any URL | Accept only local files | `test_a_drag_without_local_files_is_refused` |
| 13 | GIF mode said "Combined" with one file | The label showed the stored mode | Show the mode that will run | `test_combine_with_one_file_says_animated` |
| 14 | Clicking the chosen frame duration or loop setting unchecked it | The choices had no exclusive group | `QButtonGroup` | `test_clicking_the_chosen_frame_duration_keeps_it_chosen` |
| 15 | Popovers stayed open over the progress and Done screens | Popovers are top-level windows | The dock closes them when it hides or shows progress | `test_an_open_popover_closes_when_converting_starts` |
| 16 | A Save to folder deleted mid-run was reported as "The file was moved or deleted." | The error text names the temp file, and the rule matched any missing file | Separate rule for `.papyr-` paths | `test_a_save_folder_removed_mid_write_is_not_blamed_on_the_input` |
| 17 | A long file name failed with "This file couldn't be converted." | `convert_images` used the stem unsanitized, and the name passed 255 bytes | `safe_stem` cleans names and cuts them to 180 UTF-8 bytes. The error is now named. | `test_a_very_long_or_unusual_name_still_converts_every_page`, `test_long_names_fit_in_255_bytes_with_every_suffix` |
| 18 | Review round 1: a portrait animated WebP (EXIF 6) became a landscape GIF at half resolution | Animation size was measured before rotation | Measure upright | `test_a_turned_animation_keeps_its_full_upright_size` |
| 19 | Review round 1: cancel was ignored during animated WebP output | No cancel check on that path | Check before encoding and before moving into place | `test_cancelling_while_an_animation_is_read_writes_nothing` |
| 20 | Review round 1: one animated file hid the GIF mode chip | `_NEEDS` ignored animations | Count animations | `test_one_animated_file_can_still_choose_how_gif_output_animates` |
| 21 | Review round 2: an I/O error closing the name claim left an empty file | `os.close` sat outside the cleanup | Close inside the cleanup | `test_a_failed_name_claim_leaves_no_empty_file` |

Bugs 18 to 21 were in this branch's own new code, not in `fa30405`.

Files modified: `src/converter/{convert,images,animation,formats,layout}.py`, `src/gui/{main_window,model,file_queue,workers}.py`,
`src/gui/views/controls.py`, `src/utils/{errors,filenames}.py`, `src/main.py` (self-test),
`.github/workflows/conversion-validation.yml`, `README.md`. The tests changed are the matrix oracle
(`conversion_matrix.py`, `fixture_factory.py`), two new files (`test_atomic_outputs.py`, `test_animation_formats.py`),
and additions to six existing files.

Two existing tests changed because they pinned the old behavior.

- `test_cancel_image_conversion_keeps_finished_files_only` asserted that a cancelled PDF kept pages 1 and 2. It now
  asserts that a finished file is kept and the cancelled one leaves nothing.
- `test_missing_settings_are_documented_not_faked` lists every setting. It gains `EVERY_FRAME`, as its docstring
  asks.

## Security

| Check | Evidence | Result |
| --- | --- | --- |
| No network use | `grep` of `src/` for network modules and Qt network classes, plus a notebook with remote `<img>`, Markdown images, `<link>`, and SVG `<image>` converted with `socket` patched to fail | 0 connection attempts. Notebook resources load only from `file:` or relative paths. |
| No code execution from files | `grep` for `eval`, `exec`, `subprocess`, and `shell=True`. Notebook HTML is drawn by `QTextDocument`. QtWebEngine is not used. | Notebooks are never executed. `subprocess` is used only with fixed argument lists (`reveal.py`, `motion.py`). |
| SVG in notebooks | `safe_svg` with `xlink:href` to `file:///etc/passwd` and remote URLs | Scripts, `foreignObject`, external `href`s, and DOCTYPE/XXE are stripped |
| Output paths | Names with `..`, `/`, `:`, device names, null bytes, and 250-byte names | Fixed in bug 17. Output never leaves the chosen folder (`test_a_very_long_or_unusual_name_still_converts_every_page` checks `parent == out`). |
| Logs and messages | `utils/log.py`, `utils/errors.py` | Logs hold paths and exception text, never file contents. The window shows one plain sentence per failure. |
| Dependencies | `pip-audit -r requirements.txt` in a scratch venv | "No known vulnerabilities found" for the pinned versions |
| Decoder limits | Pillow's 89 M pixel bomb limit, PDFium page scaling, Qt's 256 MB image limit, and the new 128 Mi pixel animation cap | Oversized inputs are refused by name |

Remaining concerns:

- **No page-count limit.** A 10,000-page PDF converts to 10,000 files. It runs one page at a time, so memory stays
  bounded, but there is no timeout either. Cancel works between pages.
- **Rename race without hard links (narrow, not fixed).** On a disk without hard links (FAT, some network shares),
  another program that atomically replaces Papyr's just-claimed empty file in the microseconds before Papyr moves
  into it can lose its file. That program is itself overwriting an existing file. The full fix needs
  `renamex_np(RENAME_EXCL)` on macOS and `renameat2(RENAME_NOREPLACE)` on Linux through ctypes. The second review
  round reproduced it with a scripted competitor.
- The security audit was one model's read-only pass with scripted probes. It is not a penetration test.

## Performance

`scripts/perf_probe.py` ran each path in a fresh process, on `fa30405` and on this branch, against the same
fixtures:

| Path | Before | After |
| --- | --- | --- |
| 12-page PDF to animated GIF | 0.26 s, 141 MB | 0.25 s, 141 MB |
| Mixed PDF to AVIF / HEIC / PNG | 0.57 / 1.13 / 0.21 s; 369 / 355 / 238 MB | 0.53 / 1.15 / 0.21 s; 371 / 360 / 238 MB |
| Notebook to PDF / GIF | 0.68 / 0.69 s; 187 / 206 MB | 0.55 / 0.67 s; 187 / 207 MB |
| 3200 × 2000 PNG to AVIF / HEIC | 0.16 / 0.46 s; 372 / 463 MB | 0.16 / 0.48 s; 373 / 460 MB |
| BMP to PDF, TIFF to WebP, JPEG to JPEG | 0.06 / 0.22 / 0.04 s | 0.06 / 0.21 / 0.04 s |

There is no significant regression. Every difference is within run-to-run noise, from one run each. The staging
step adds an `fsync` per file, which these numbers do not show.

New paths, measured on a 120-frame 1000 × 800 animated GIF (96 M pixels):

| Output | Time | Peak RSS |
| --- | --- | --- |
| Animated WebP | 1.9 s | 478 MB |
| Animated GIF | 1.8 s | 110 MB |
| PNG, every frame (120 files) | 0.9 s | 111 MB |

GIF and image-sequence outputs stream one frame at a time. WebP holds all frames, which is why the cap exists.

## Platform readiness

| Platform | Status | Evidence |
| --- | --- | --- |
| macOS Apple Silicon | **VERIFIED** | Full suite and matrix as above. Packaged app rebuilt in `/tmp` (the existing `build/` and `dist/` were not touched), self-test passed at `c8e71f7`. A probe build converted HEIC, a damaged TIFF batch, animations, and a read-only folder through the bundle's own libraries. libheif, libwebpmux, and pdfium are bundled. The icon matches `assets/icon.icns`, and the version is 2.3.1. The app launched and drew its welcome screen. No real file dialogs or Finder drag and drop were tested. |
| macOS Intel | **NOT TESTED** | No Intel hardware, and this Mac has no Rosetta. The workflow now has a `macos-15-intel` job, which has not run. |
| Windows | **NOT TESTED** | No Windows machine or VM. The `windows-latest` job has not run on this branch. |
| Linux | **NOT TESTED** | No Linux machine or container runtime here. The `ubuntu-22.04` job has not run on this branch. |

### Validation workflow changes (not pushed)

`.github/workflows/conversion-validation.yml`:

- **Jobs.** Adds a macOS Intel job (`macos-15-intel`, the label `build.yml` already uses). Each platform writes its
  reports and uploads its artifact under its own slug, so the two macOS jobs no longer collide.
- **Codecs.** Fails by name when AVIF, WebP, or libheif is missing. Before, missing codecs turned matrix pairs into
  silent skips.
- **Matrix completeness.** A new step reads `run-summary.json` and fails unless every supported pair passed with no
  skipped or failed conversions. It also runs after a matrix failure, so the counts are always printed.
- **Reporting.** Runs pytest with `-rs`, so each skip is listed with its reason. Skips that are platform-specific
  and legitimate stay skips, such as POSIX permission tests on Windows. A missing report now fails the upload
  (`if-no-files-found: error`).

The YAML parses (`yaml.safe_load`). The summary check passes against this branch's report. `actionlint` is not
installed, so the workflow has not been linted.

## Code review

Independent review used families other than the author's (Claude Opus 5.5):

| Round | Reviewer | Scope | Verified findings |
| --- | --- | --- | --- |
| Audit | Gemini 3.8 Flash | Security and privacy, read-only | 1 (bug 17) |
| Audit | GPT-6 Luna | GUI reliability, read-only | 10 confirmed. 7 fixed (bugs 9 to 16), 3 left (see limitations). |
| Audit | Gemini 3.8 Flash | CI workflow | 6 of 7 accepted. Its claim that `macos-15-intel` does not exist was wrong, and `macos-13` is retired. |
| 1 | GPT-6.1 Sol | `2ae1e81` | 4: the rename race, the rotated WebP, WebP cancel, and the GIF mode chip. All fixed in `99751f2`. |
| 1 | Gemini 3.8 Flash | `2ae1e81`, animation focus | 0. It also judged the rename fallback safe, which round 1's other reviewer disproved. |
| 2 | GPT-6.1 Sol | `2ae1e81..99751f2` | 2: the claim-close leak, fixed in `c8e71f7`, and the narrow rename race, recorded above |

`c8e71f7` is a two-line move of `os.close` into the cleanup. Its review is the round-2 reviewer's own reproduction,
which now passes. No reviewer read that commit as a whole.

## Process notes

- An audit agent ran the app outside pytest and set the real Papyr preference `output_dir` to a `/tmp` folder. The
  key has been removed, so Papyr falls back to Documents. Your Papyr, which was running throughout, writes its own
  folder back when you quit it.
- An agent created an untracked `uv.lock` in the repository. It was removed. `assets/branding/` was not touched.
- The first baseline run had one matrix failure that passed alone. The fixture builder deletes and rebuilds
  `tests/fixtures/generated/` on each run, and an audit agent was running tests in the same checkout at the time.
  Later full runs had no agents running tests in the checkout, and neither failed.
