# Papyr 2.3.1-beta.1: manual acceptance results

Fill this in while running `MANUAL-ACCEPTANCE-TEST.md`. Each test starts as **NOT RUN**. Change it only after a
person has done the test: **PASS**, **FAIL**, or **BLOCKED**. No test here has been run yet.

## Test run

| | |
| --- | --- |
| Tester | |
| Date and time | |
| Mac model and chip | |
| macOS version and build | |
| macOS user account used (must be a separate test account) | |
| ZIP file name | `Papyr-2.3.1-beta.1-macOS-AppleSilicon.zip` |
| Expected SHA-256 | `a47235c84266594eff732c1b69e089a42a1379f99da256e497c24444602046d1` |
| SHA-256 printed by `shasum -a 256 -c SHA256SUMS.txt` (copy the line) | |
| How the ZIP reached the test account (download, AirDrop, …) | |
| `acceptance-kit` checksum check all `OK`? | |

## Summary

Fill in when finished. Total 39 tests; 14 are blockers.

| Status | Count | Test IDs |
| --- | --- | --- |
| PASS | | |
| FAIL | | |
| BLOCKED | | |
| NOT RUN | 39 | all |

**Blocker tests:** A1, A2, A3, A4, D3, D4, E1, E3, F1, F4, G1, G3, G4, G6.
Any FAIL among them is NO-GO for the beta. BLOCKED blocker tests must be named and justified at sign-off.

## At a glance

| ID | Test | Blocker | Status |
| --- | --- | --- | --- |
| A1 | Download and checksum | **yes** | NOT RUN |
| A2 | Unzip and install | **yes** | NOT RUN |
| A3 | First open is blocked, with no way around it but the documented one | **yes** | NOT RUN |
| A4 | Approve this app only | **yes** | NOT RUN |
| A5 | First-launch state (checklist 1) |  | NOT RUN |
| A6 | Second launch |  | NOT RUN |
| B1 | Open With |  | NOT RUN |
| B2 | Papyr does not become the default app |  | NOT RUN |
| B3 | Drop on the Dock icon (checklist 5) |  | NOT RUN |
| C1 | Browse Files (checklist 2) |  | NOT RUN |
| C2 | Add Folder (checklist 3) |  | NOT RUN |
| C3 | Finder drag and drop (checklist 4) |  | NOT RUN |
| C4 | Duplicate drop (known issue) |  | NOT RUN |
| C5 | Reorder (checklist 6) |  | NOT RUN |
| C6 | Remove (known issue) |  | NOT RUN |
| D1 | Choose where to save (checklist 8, first half) |  | NOT RUN |
| D2 | Every format offers the right options (checklist 7) |  | NOT RUN |
| D3 | Single file, each format | **yes** | NOT RUN |
| D4 | One PDF page per image (checklist 12) | **yes** | NOT RUN |
| D5 | Show in Finder (checklist 11) |  | NOT RUN |
| E1 | Mixed batch with a damaged file (checklist 9) | **yes** | NOT RUN |
| E2 | Retry Failed (checklist 10) |  | NOT RUN |
| E3 | Protected PDFs (checklist 20) | **yes** | NOT RUN |
| F1 | Animated GIF to WebP | **yes** | NOT RUN |
| F2 | Animated WebP to animated GIF |  | NOT RUN |
| F3 | Every frame off |  | NOT RUN |
| F4 | Every frame on | **yes** | NOT RUN |
| F5 | Every frame for PDF |  | NOT RUN |
| G1 | Existing files are never replaced (checklist 17) | **yes** | NOT RUN |
| G2 | Replacing a merged file asks first |  | NOT RUN |
| G3 | exFAT or FAT32 disk (checklist 18) | **yes** | NOT RUN |
| G4 | Cancel (checklist 14) | **yes** | NOT RUN |
| G5 | Close the window during a conversion (checklist 15) |  | NOT RUN |
| G6 | Quit during a conversion (checklist 16) | **yes** | NOT RUN |
| H1 | The chosen folder persists (checklist 8, second half) |  | NOT RUN |
| H2 | A deleted folder (checklist 19) |  | NOT RUN |
| H3 | Relaunch after the folder is gone |  | NOT RUN |
| H4 | An unwritable folder |  | NOT RUN |
| H5 | Clean up |  | NOT RUN |

## Details

For every FAIL or BLOCKED, fill in the details block below. For a PASS, add notes only if something was odd.
Keep screenshots (Cmd-Shift-4) and copied logs in one folder, and name them by test ID, for example
`G6-crash-dialog.png`.

Where to find evidence:

- Papyr's log: `~/Library/Logs/Papyr/papyr.log` (note the time of the test).
- Crash reports: files starting with `Papyr` in `~/Library/Logs/DiagnosticReports`.
- Leftover temporary files: press Cmd-Shift-. in Finder and look for `.papyr-` names.

### A. First launch and Gatekeeper

#### A1. Download and checksum (BLOCKER)

- **Expected:** `Papyr-2.3.1-beta.1-macOS-AppleSilicon.zip: OK`.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### A2. Unzip and install (BLOCKER)

- **Expected:** one `Papyr.app`, with no `__MACOSX` folder or `._` files beside it.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### A3. First open is blocked, with no way around it but the documented one (BLOCKER)

- **Expected:** macOS says it can't verify Papyr. The app does not open.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### A4. Approve this app only (BLOCKER)

- **Expected:** Papyr's window opens within about 10 seconds. You were never asked to change a global security setting.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### A5. First-launch state (checklist 1)

- **Expected:** the welcome screen. Save to shows **Documents**, and its tooltip shows `/Users/<you>/Documents`.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### A6. Second launch

- **Expected:** it opens straight away, with no Gatekeeper prompt.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

### B. Opening files through Finder and the Dock

#### B1. Open With

- **Expected:** Papyr opens with the file in its list, with a thumbnail.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### B2. Papyr does not become the default app

- **Expected:** it opens in Preview (or your usual viewer), not Papyr.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### B3. Drop on the Dock icon (checklist 5)

- **Expected:** each file is added. When Papyr wasn't running, it launches with the file.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

### C. File dialogs and drag and drop

#### C1. Browse Files (checklist 2)

- **Expected:** a standard macOS open dialog. Both files appear with thumbnails. The HEIC thumbnail is upright.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### C2. Add Folder (checklist 3)

- **Expected:** `a.png` and `b.jpg` are added. `notes.txt`, `.hidden.png`, and the files in `.hidden-dir` are not.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### C3. Finder drag and drop (checklist 4)

- **Expected:** the two files are added. The web link is refused (no-entry cursor), and nothing is added.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### C4. Duplicate drop (known issue)

- **Expected:** the TIFF is added and the duplicate is skipped. A known issue: no notice is shown.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### C5. Reorder (checklist 6)

- **Expected:** the rows reorder, and the PDF's pages follow the new order.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### C6. Remove (known issue)

- **Expected:** each removes the row. A known issue: Remove Selected may be greyed out while the Edit menu is open. If so, record it as a note, not a fail.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

### D. Formats, destination, and single conversions

#### D1. Choose where to save (checklist 8, first half)

- **Expected:** a native folder picker. Save to now shows `Papyr Out`.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### D2. Every format offers the right options (checklist 7)

- **Expected:** JPEG, WebP, HEIC, and AVIF show a Quality option. The PDF pages resolution option appears because a PDF is listed. PDF shows the **Page** chip (size and margins) and **Merge into one PDF**. GIF shows frame timing and looping options.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### D3. Single file, each format (BLOCKER)

- **Expected:** Nine files in `Papyr Out`, each named `sample.<ext>`, and each opens in Preview showing the upright photo. The summary says 1 converted each time.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### D4. One PDF page per image (checklist 12) (BLOCKER)

- **Expected:** 12 JPEGs, `pdf-twelve-pages-page-1.jpg` to `-page-12.jpg`. Each shows "Page N" in its own colour, in order. This is intended behaviour, not a bug.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### D5. Show in Finder (checklist 11)

- **Expected:** Finder opens `Papyr Out` with the new files selected.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

### E. Batches, failures, and protected PDFs

#### E1. Mixed batch with a damaged file (checklist 9) (BLOCKER)

- **Expected:** Three PDFs are made; the notebook PDF has searchable text (Cmd-F in Preview). The summary lists `broken.jpg` with one plain sentence ("The file appears to be damaged."). No `broken.pdf` and no `.papyr-` file exist (hidden files visible).
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### E2. Retry Failed (checklist 10)

- **Expected:** only `broken.jpg` is listed. It fails again with the same sentence, and nothing else is reconverted.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### E3. Protected PDFs (checklist 20) (BLOCKER)

- **Expected:** **Thumbnails:** `copy-forbidden` and `copy-allowed-encrypted` show previews. **PNG run:** The PNG and both pages of `copy-allowed-encrypted` are written. `copy-forbidden` says its security settings don't allow its content to be copied. `needs-password` says it is password-protected. **PDF run:** Only the PNG becomes a PDF. Both encrypted PDFs say Papyr won't copy them into a new PDF, because the copy would lose that protection. `needs-password` says it is password-protected.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

### F. Animation and Every frame

#### F1. Animated GIF to WebP (BLOCKER)

- **Expected:** one `.webp` that animates through 4 frames, at the same speed as the GIF, looping.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### F2. Animated WebP to animated GIF

- **Expected:** one GIF that animates and loops like the source.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### F3. Every frame off

- **Expected:** one `gif-animated.png`, showing the first frame.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### F4. Every frame on (BLOCKER)

- **Expected:** The switch is visible only because an animated file is listed. Four files, `gif-animated-frame-001.png` to `-004.png`, in animation order.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### F5. Every frame for PDF

- **Expected:** one PDF with 4 pages, one per frame.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

### G. Existing files, removable disks, cancel, and quitting

#### G1. Existing files are never replaced (checklist 17) (BLOCKER)

- **Expected:** the text file is unchanged, and the new file is `sample (1).png`.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### G2. Replacing a merged file asks first

- **Expected:** Papyr asks before replacing `All.pdf`. Choosing not to replace leaves the old file.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### G3. exFAT or FAT32 disk (checklist 18) (BLOCKER)

- **Expected:** 12 PNGs, with page 1 as `pdf-twelve-pages-page-1 (1).png`. The existing file is unchanged. No `.papyr-` files remain. macOS's own `._` files are normal on these disks.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### G4. Cancel (checklist 14) (BLOCKER)

- **Expected:** It stops within a few seconds, and the summary says it was cancelled. The folder holds only whole files for the inputs that finished, each opening in Preview. No `.papyr-` file remains (hidden files visible).
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### G5. Close the window during a conversion (checklist 15)

- **Expected:** Papyr stops the conversion and the window closes. There is no crash report, and no `.papyr-` file remains. Reopening Papyr works.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### G6. Quit during a conversion (checklist 16) (BLOCKER)

- **Expected:** Papyr quits within a few seconds, with no "quit unexpectedly" dialog. There is no new `Papyr` file in `~/Library/Logs/DiagnosticReports`, and no `.papyr-` file remains.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

### H. Save to folder persistence and relaunch

#### H1. The chosen folder persists (checklist 8, second half)

- **Expected:** Save to still shows `Papyr Out`.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### H2. A deleted folder (checklist 19)

- **Expected:** Papyr says the folder is missing. Convert is unavailable until you choose another folder.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### H3. Relaunch after the folder is gone

- **Expected:** Save to shows Documents. Choosing a new folder works and persists after another relaunch.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### H4. An unwritable folder

- **Expected:** Papyr says the folder isn't writable and won't convert there.
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

#### H5. Clean up

- **Expected:** no Papyr process remains (Activity Monitor).
- **Status:** NOT RUN
- **What happened:**
- **Reproduction steps** (if FAIL):
- **Screenshots:**
- **Log or crash report:**
- **Notes:**

## Sign-off

| | |
| --- | --- |
| All blocker tests PASS | yes / no |
| Other FAILs, each fixed or listed as a known issue | |
| BLOCKED tests and why accepted | |
| Decision | GO / NO-GO for sending to the five testers |
| Approved by, and date | |
