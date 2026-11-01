# Papyr 2.3.1-beta.1: native macOS acceptance test

This replaces the 20-row table in `tests/reports/native-macos-checklist.md` with exact steps. Every one of those 20
steps is covered; the map is at the end. Allow about 45 minutes.

A person runs this on a Mac with Apple silicon and macOS 15 or later, using **only** the approved ZIP:

| | |
| --- | --- |
| File | `Papyr-2.3.1-beta.1-macOS-AppleSilicon.zip` |
| SHA-256 | `a47235c84266594eff732c1b69e089a42a1379f99da256e497c24444602046d1` |
| Source | GitHub Actions run 41290479138, commit `48fef48` |

Never test the withdrawn Mac mini ZIP, whose SHA-256 starts with `789e9564`. No step needs Accessibility, Screen
Recording, or any change to macOS security settings, and no step bypasses a security prompt.

Record every result in `MANUAL-ACCEPTANCE-RESULTS.md`. Tests marked **BLOCKER** stop the beta if they fail.

## Before you start

### Where to run it

Use **a separate macOS user account** made for testing (System Settings → Users & Groups → Add User). This gives:

- The real first-launch Gatekeeper prompt.
- Real Finder, Dock, and Open With behaviour.
- Preferences that are disposable, so your own Papyr settings and Save to folder are never touched.

Launching from Finder or the Dock can't take `PAPYR_SETTINGS_DIR`, so a separate account is the only way to test
those paths without touching real preferences. If you must use your own account, quit any other Papyr first. Then
note your current Save to folder, and set it back afterwards.

Record the Mac model, the macOS version (Apple menu → About This Mac), and the SHA-256 of the ZIP under test.

### Test files

Copy `acceptance-kit/` from the distribution folder (`~/Downloads/Papyr-Beta-Distribution/` on the Mac mini) to the
test account's Desktop. Then, in Terminal inside the copied `acceptance-kit` folder, run
`shasum -a 256 -c ../acceptance-kit.sha256` (copy that file too). Every line must say `OK`.

| File | Used for |
| --- | --- |
| `batch/sample.heic`, `batch/jpeg-portrait.jpg`, `batch/png-landscape.png` | Dialogs, drag and drop, batches |
| `pdf-twelve-pages.pdf` | 12 pages, each a different colour, labelled "Page N" |
| `gif-animated.gif`, `webp-animated.webp` | 4-frame animations, 200 ms per frame, looping forever |
| `tiff-multipage.tiff`, `notebook-short.ipynb` | Multi-page and notebook inputs |
| `broken.jpg` | A JPEG cut short: must fail with a reason |
| `copy-forbidden.pdf` | Encrypted; the owner forbids copying |
| `copy-allowed-encrypted.pdf` | Encrypted; the owner allows copying (2 pages) |
| `needs-password.pdf` | Needs a password to open |
| `folder-to-add/` | `a.png`, `b.jpg`, `notes.txt`, a hidden `.hidden.png`, and a hidden folder |
| `large-1.tiff` … `large-8.tiff` | 3200 × 2000 pictures, for a conversion long enough to interrupt |

Also have a USB stick or SD card you can erase, or make a disk image in Disk Utility (File → New Image → Blank
Image, 100 MB, Format ExFAT).

### Recording results

Use `MANUAL-ACCEPTANCE-RESULTS.md`. Every test starts as **NOT RUN**. Change it only after you have done the test
yourself:

- **PASS:** everything under Expected happened.
- **FAIL:** anything under Failure happened. Describe exactly what, and keep the output folder.
- **BLOCKED:** the test could not be run. Say why.

After any FAIL, copy `~/Library/Logs/Papyr/papyr.log` and note the time. Check
`~/Library/Logs/DiagnosticReports` for a file starting with `Papyr` after every test in sections F and G.

"Hidden files visible" means: in Finder press **Cmd-Shift-.**, which you need for every leftover check.

## A. First launch and Gatekeeper

**A1. Download and checksum.** BLOCKER

- **Steps:**
  1. Get the ZIP and `SHA256SUMS.txt` the way testers will, for example a browser download or AirDrop, so macOS marks
     it as downloaded.
  2. In Terminal, in that folder, run `shasum -a 256 -c SHA256SUMS.txt`.
- **Expected:** `Papyr-2.3.1-beta.1-macOS-AppleSilicon.zip: OK`.
- **Failure:** anything else. Stop the whole test.

**A2. Unzip and install.** BLOCKER

- **Steps:**
  1. Double-click the ZIP.
  2. Drag **Papyr.app** to **Applications**.
- **Expected:** one `Papyr.app`, with no `__MACOSX` folder or `._` files beside it.
- **Failure:** missing app, an extra folder, or an error.

**A3. First open is blocked, with no way around it but the documented one.** BLOCKER

- **Steps:** double-click Papyr in Applications.
- **Expected:** macOS says it can't verify Papyr. The app does not open.
- **Failure:** the app opens with no warning (then the build is not quarantined, so the test isn't realistic), or
  macOS says the app is **damaged** and offers Move to Trash. "Damaged" is a release blocker: it means the
  signature or bundle is broken.

**A4. Approve this app only.** BLOCKER

- **Steps:**
  1. Click **Done**.
  2. Open System Settings → Privacy & Security.
  3. Click **Open Anyway** next to Papyr, and authenticate.
  4. Click **Open**.
- **Expected:** Papyr's window opens within about 10 seconds. You were never asked to change a global security
  setting.
- **Failure:** no Open Anyway button, the app quits or crashes, or a second warning appears on the next launch.

**A5. First-launch state** (checklist 1).

- **Steps:**
  1. Look at the window.
  2. Hover over the Save to control.
- **Expected:** the welcome screen. Save to shows **Documents**, and its tooltip shows `/Users/<you>/Documents`.
- **Failure:** another folder, especially anything in `/tmp` or `/private/var`, or a blank or garbled window.

**A6. Second launch.**

- **Steps:**
  1. Quit with **Cmd-Q**.
  2. Open Papyr from Applications again.
- **Expected:** it opens straight away, with no Gatekeeper prompt.
- **Failure:** any prompt, or a crash.

## B. Opening files through Finder and the Dock

**B1. Open With.**

- **Steps:**
  1. Quit Papyr.
  2. In Finder, right-click `batch/png-landscape.png` → Open With → Papyr. If Papyr isn't listed, choose Other… →
     Papyr.
- **Expected:** Papyr opens with the file in its list, with a thumbnail.
- **Failure:** the file is missing, there is no thumbnail, or a crash.

**B2. Papyr does not become the default app.**

- **Steps:** double-click `batch/png-landscape.png` in Finder.
- **Expected:** it opens in Preview (or your usual viewer), not Papyr.
- **Failure:** it opens in Papyr.

**B3. Drop on the Dock icon** (checklist 5).

- **Steps:**
  1. With Papyr running, drag `batch/jpeg-portrait.jpg` onto Papyr's Dock icon.
  2. Quit Papyr, then drag `batch/sample.heic` onto the Dock icon. To keep the icon there, right-click it → Options
     → Keep in Dock first.
- **Expected:** each file is added. When Papyr wasn't running, it launches with the file.
- **Failure:** nothing is added, or a crash.

## C. File dialogs and drag and drop

**C1. Browse Files** (checklist 2).

- **Steps:**
  1. Start with an empty list.
  2. Click **Browse Files…**.
  3. In the system dialog, select `batch/sample.heic` and `batch/jpeg-portrait.jpg` with Cmd-click, then choose
     Open.
- **Expected:** a standard macOS open dialog. Both files appear with thumbnails. The HEIC thumbnail is upright.
- **Failure:** a non-native dialog, missing files, or a wrong or rotated thumbnail.

**C2. Add Folder** (checklist 3).

- **Steps:** **Add Folder…** → pick `folder-to-add`.
- **Expected:** `a.png` and `b.jpg` are added. `notes.txt`, `.hidden.png`, and the files in `.hidden-dir` are not.
- **Failure:** a hidden or unsupported file appears, or a supported one is missing.

**C3. Finder drag and drop** (checklist 4).

- **Steps:**
  1. Drag `pdf-twelve-pages.pdf` and `gif-animated.gif` from Finder onto the window.
  2. Then drag a link from Safari's address bar onto the window.
- **Expected:** the two files are added. The web link is refused (no-entry cursor), and nothing is added.
- **Failure:** the link is accepted, or the files aren't.

**C4. Duplicate drop** (known issue).

- **Steps:** drag `batch/png-landscape.png` and `tiff-multipage.tiff` together onto a list that already holds
  `png-landscape.png`.
- **Expected:** the TIFF is added and the duplicate is skipped. A known issue: no notice is shown.
- **Failure:** the duplicate appears twice, or the TIFF is skipped.

**C5. Reorder** (checklist 6).

- **Steps:**
  1. With at least three files listed, drag the last row to the top.
  2. Choose PDF and turn on **Merge into one PDF**. Convert.
- **Expected:** the rows reorder, and the PDF's pages follow the new order.
- **Failure:** the order doesn't change, or the PDF uses the old order.

**C6. Remove** (known issue).

- **Steps:**
  1. Select a row and press Delete.
  2. Select another row and use Edit → Remove Selected.
  3. Click a row's × button.
- **Expected:** each removes the row. A known issue: Remove Selected may be greyed out while the Edit menu is open.
  If so, record it as a note, not a fail.
- **Failure:** a row can't be removed by any of the three ways.

## D. Formats, destination, and single conversions

**D1. Choose where to save** (checklist 8, first half).

- **Steps:**
  1. Click the folder chip in the dock (Save to).
  2. In the system folder dialog, make a new folder `Papyr Out` on the Desktop and choose it.
- **Expected:** a native folder picker. Save to now shows `Papyr Out`.
- **Failure:** the dialog doesn't open, or the label is wrong.

**D2. Every format offers the right options** (checklist 7).

- **Steps:** with `sample.heic` and `pdf-twelve-pages.pdf` listed, pick each format in turn. AVIF, TIFF, GIF, and
  BMP are under **More**.
- **Expected:**
  - JPEG, WebP, HEIC, and AVIF show a Quality option.
  - The PDF pages resolution option appears because a PDF is listed.
  - PDF shows the **Page** chip (size and margins) and **Merge into one PDF**.
  - GIF shows frame timing and looping options.
- **Failure:** an option that does nothing, or one that's missing.

**D3. Single file, each format.** BLOCKER

- **Steps:**
  1. List only `batch/sample.heic`.
  2. Convert to JPEG, then PNG, WebP, HEIC, AVIF, TIFF, BMP, GIF, and PDF. Use **Back to Files** between runs.
- **Expected:**
  - Nine files in `Papyr Out`, each named `sample.<ext>`, and each opens in Preview showing the upright photo.
  - The summary says 1 converted each time.
- **Failure:** a missing, blank, sideways, or unopenable file, or a summary that doesn't match the folder.

**D4. One PDF page per image** (checklist 12). BLOCKER

- **Steps:** list only `pdf-twelve-pages.pdf`. Convert to JPEG.
- **Expected:** 12 JPEGs, `pdf-twelve-pages-page-1.jpg` to `-page-12.jpg`. Each shows "Page N" in its own colour,
  in order. This is intended behaviour, not a bug.
- **Failure:** fewer or more files, wrong order, or blank pages.

**D5. Show in Finder** (checklist 11).

- **Steps:** on the summary after D4, click **Show in Finder**.
- **Expected:** Finder opens `Papyr Out` with the new files selected.
- **Failure:** nothing happens, or the wrong folder opens.

## E. Batches, failures, and protected PDFs

**E1. Mixed batch with a damaged file** (checklist 9). BLOCKER

- **Steps:**
  1. List `batch/sample.heic`, `broken.jpg`, `batch/png-landscape.png`, and `notebook-short.ipynb`.
  2. Convert to PDF, one file per input.
- **Expected:**
  - Three PDFs are made; the notebook PDF has searchable text (Cmd-F in Preview).
  - The summary lists `broken.jpg` with one plain sentence ("The file appears to be damaged.").
  - No `broken.pdf` and no `.papyr-` file exist (hidden files visible).
- **Failure:** the batch stops at the damaged file, a partial `broken` output exists, or the message is a raw
  error or traceback.

**E2. Retry Failed** (checklist 10).

- **Steps:** on that summary, click **Retry Failed**. Convert again.
- **Expected:** only `broken.jpg` is listed. It fails again with the same sentence, and nothing else is reconverted.
- **Failure:** other files are retried or duplicated.

**E3. Protected PDFs** (checklist 20). BLOCKER

- **Steps:**
  1. List `copy-forbidden.pdf`, `copy-allowed-encrypted.pdf`, `needs-password.pdf`, and
     `batch/png-landscape.png`.
  2. Look at the thumbnails.
  3. Convert to PNG.
  4. Then convert the same list to PDF.
- **Expected:**
  - **Thumbnails:** `copy-forbidden` and `copy-allowed-encrypted` show previews.
  - **PNG run:**
    - The PNG and both pages of `copy-allowed-encrypted` are written.
    - `copy-forbidden` says its security settings don't allow its content to be copied.
    - `needs-password` says it is password-protected.
  - **PDF run:**
    - Only the PNG becomes a PDF.
    - Both encrypted PDFs say Papyr won't copy them into a new PDF, because the copy would lose that protection.
    - `needs-password` says it is password-protected.
- **Failure:** any encrypted PDF becomes a new PDF, `copy-forbidden` becomes images, or the batch stops.

## F. Animation and Every frame

**F1. Animated GIF to WebP.** BLOCKER

- **Steps:** list `gif-animated.gif`. Convert to WebP. Open the result in Safari: drag it onto a Safari window.
- **Expected:** one `.webp` that animates through 4 frames, at the same speed as the GIF, looping.
- **Failure:** a still picture, a different speed, black where the GIF is transparent, or more than one file.

**F2. Animated WebP to animated GIF.**

- **Steps:**
  1. List `webp-animated.webp`.
  2. Convert to GIF, with each file becoming its own animation.
  3. Open the result in Safari.
- **Expected:** one GIF that animates and loops like the source.
- **Failure:** a still picture or wrong timing.

**F3. Every frame off.**

- **Steps:** list `gif-animated.gif`. Choose PNG and make sure **Every frame** is off. Convert.
- **Expected:** one `gif-animated.png`, showing the first frame.
- **Failure:** several files, or a frame other than the first.

**F4. Every frame on.** BLOCKER

- **Steps:** same file, PNG, turn **Every frame** on. Convert into an empty folder.
- **Expected:**
  - The switch is visible only because an animated file is listed.
  - Four files, `gif-animated-frame-001.png` to `-004.png`, in animation order.
- **Failure:** the switch is missing, the count or order is wrong, or the switch shows with no animated file
  listed.

**F5. Every frame for PDF.**

- **Steps:** same file, PDF, **Every frame** on. Convert.
- **Expected:** one PDF with 4 pages, one per frame.
- **Failure:** 1 page, or the pages are out of order.

## G. Existing files, removable disks, cancel, and quitting

**G1. Existing files are never replaced** (checklist 17). BLOCKER

- **Steps:**
  1. In `Papyr Out`, make a text file and rename it `sample.png`.
  2. List `batch/sample.heic`. Convert to PNG.
- **Expected:** the text file is unchanged, and the new file is `sample (1).png`.
- **Failure:** the text file is replaced or changed.

**G2. Replacing a merged file asks first.**

- **Steps:**
  1. List two files, choose PDF, turn on **Merge into one PDF**, and click the file name chip to name it `All`.
     Convert into `Papyr Out`.
  2. Click **Back to Files** and convert again with the same name.
- **Expected:** Papyr asks before replacing `All.pdf`. Choosing not to replace leaves the old file.
- **Failure:** it replaces without asking.

**G3. exFAT or FAT32 disk** (checklist 18). BLOCKER

- **Steps:**
  1. Set Save to on the USB stick or disk image, then put a file named `pdf-twelve-pages-page-1.png` there.
  2. List `pdf-twelve-pages.pdf`. Convert to PNG.
- **Expected:**
  - 12 PNGs, with page 1 as `pdf-twelve-pages-page-1 (1).png`.
  - The existing file is unchanged.
  - No `.papyr-` files remain. macOS's own `._` files are normal on these disks.
- **Failure:** the existing file is replaced, files are missing, or a `.papyr-….part` file remains.

**G4. Cancel** (checklist 14). BLOCKER

- **Steps:**
  1. Set Save to an empty folder.
  2. List `large-1.tiff` to `large-8.tiff`. Choose HEIC at the highest quality.
  3. Convert, and click **Cancel** (or press Esc) while the progress shows file 2 to 4.
- **Expected:**
  - It stops within a few seconds, and the summary says it was cancelled.
  - The folder holds only whole files for the inputs that finished, each opening in Preview.
  - No `.papyr-` file remains (hidden files visible).
- **Failure:**
  - It keeps going, or the app hangs.
  - A half-written or unopenable file exists, or a `.papyr-` file remains.
- **If the run finishes before you can cancel:** list the eight files several times over (drag them in again) and
  repeat.

**G5. Close the window during a conversion** (checklist 15).

- **Steps:** start the same long run, then close the window with the red button or Cmd-W.
- **Expected:**
  - Papyr stops the conversion and the window closes.
  - There is no crash report, and no `.papyr-` file remains.
  - Reopening Papyr works.
- **Failure:** a hang, a crash report, or a partial file.

**G6. Quit during a conversion** (checklist 16). BLOCKER

- **Steps:** start the same long run, then press Cmd-Q. Repeat once using Papyr → Quit Papyr from the menu.
- **Expected:**
  - Papyr quits within a few seconds, with no "quit unexpectedly" dialog.
  - There is no new `Papyr` file in `~/Library/Logs/DiagnosticReports`, and no `.papyr-` file remains.
- **Failure:** a crash dialog, a crash report, a hang, or a leftover file.

## H. Save to folder persistence and relaunch

**H1. The chosen folder persists** (checklist 8, second half).

- **Steps:** with Save to set to `Papyr Out`, quit (Cmd-Q) and reopen Papyr.
- **Expected:** Save to still shows `Papyr Out`.
- **Failure:** it shows Documents or another folder.

**H2. A deleted folder** (checklist 19).

- **Steps:**
  1. With Papyr open on `Papyr Out`, move `Papyr Out` to the Trash in Finder.
  2. Return to Papyr and add a file.
- **Expected:** Papyr says the folder is missing. Convert is unavailable until you choose another folder.
- **Failure:** it converts somewhere unexpected, or crashes.

**H3. Relaunch after the folder is gone.**

- **Steps:** with `Papyr Out` still in the Trash, quit and reopen Papyr.
- **Expected:** Save to shows Documents. Choosing a new folder works and persists after another relaunch.
- **Failure:** a crash, or a temporary or invisible folder is shown.

**H4. An unwritable folder.**

- **Steps:**
  1. Make a folder, then in Finder use Get Info → Sharing & Permissions to set your access to Read only.
  2. Choose it as Save to.
- **Expected:** Papyr says the folder isn't writable and won't convert there.
- **Failure:** it tries and fails per file, or crashes.

**H5. Clean up.**

- **Steps:** quit Papyr. Delete the test account, or the test folders, when done.
- **Expected:** no Papyr process remains (Activity Monitor).
- **Failure:** Papyr is still running.

## Map to `native-macos-checklist.md`

| Checklist step | Covered by |
| --- | --- |
| 1 First launch | A3–A6 |
| 2 Browse Files | C1 |
| 3 Add Folder | C2 |
| 4 Finder drag and drop | C3 |
| 5 Dock drop | B3 |
| 6 Reorder | C5 |
| 7 Formats | D2, D3 |
| 8 Save to and persistence | D1, H1 |
| 9 Damaged file in a batch | E1 |
| 10 Retry Failed | E2 |
| 11 Show in Finder | D5 |
| 12 12-page PDF to JPEG | D4 |
| 13 GIF to WebP | F1 |
| 14 Cancel | G4 |
| 15 Close during conversion | G5 |
| 16 Quit during conversion | G6 |
| 17 Existing file | G1 |
| 18 exFAT or FAT32 | G3 |
| 19 Deleted folder | H2, H3 |
| 20 Copy-forbidden PDF | E3 |

Added beyond the checklist:

- Checksum and install: A1, A2.
- Open With and default-app checks: B1, B2.
- The known GUI issues: C4, C6.
- Merged-file replacement: G2.
- Every frame: F3–F5.
- WebP to GIF: F2.
- An unwritable folder: H4.

## Pass criteria for beta approval

- **Release blockers:** any FAIL in A1–A4, D3, D4, E1, E3, F1, F4, G1, G3, G4, or G6.
- Other FAILs need a decision: fix first, or list them as known issues in the release notes.
- BLOCKED tests must be named in the approval.
