# Papyr 2.3.1-beta.1: guide for beta testers

Thank you for testing Papyr. This first beta goes to five people before anything is released publicly. Your reports
decide what gets fixed before then.

## What Papyr does

Papyr is a free desktop converter for photos, PDFs, and Jupyter notebooks. It works entirely on your Mac: it makes
no network connections, needs no account, and sends nothing anywhere.

- **Reads:** HEIC, HEIF, JPEG, PNG, WebP, AVIF, TIFF, BMP, GIF, PDF, and Jupyter notebooks (`.ipynb`).
- **Writes:** PDF, JPEG, PNG, HEIC, WebP, AVIF, TIFF, GIF, and BMP.
- **Batches:** convert many files at once, combine them into one PDF, or merge PDFs.
- **Animations:** animated GIF and WebP stay animated when converted to WebP or an animated GIF. **Every frame**
  saves each frame as its own file.
- **Safety:**
  - Existing files are never replaced. New ones get a number, like `photo (1).jpg`.
  - A file that fails part way leaves nothing behind, and the rest of the batch still converts.
  - Photo location data (GPS) is never copied into the converted files.
  - Protected PDFs keep their protection. Papyr won't copy an encrypted PDF into a new PDF, and won't convert one
    whose owner forbids copying.

## Who this beta is for

| You can join if | Not in this beta |
| --- | --- |
| A Mac with **Apple silicon** (M1, M2, M3, M4, or later) | Intel Macs |
| **macOS 15 (Sequoia) or later** | macOS 14 or earlier (untested) |
| You're comfortable approving an app in System Settings once | Windows and Linux |

Check under Apple menu → About This Mac: "Chip: Apple M…" and macOS 15 or later.

## Before you install: about security

This beta is **ad-hoc signed and not notarized**. It isn't signed with an Apple Developer ID, and Apple hasn't
scanned it. That costs money this project doesn't spend yet. macOS will block the first launch until you approve
Papyr in **System Settings → Privacy & Security → Open Anyway**.

- That approval covers this one app.
- **Never turn off Gatekeeper or run Terminal commands to get around macOS security.** No step needs it.
- Check the checksum before opening, as `INSTALLATION.md` explains. If it doesn't match, don't open the app.

## Install

Follow `INSTALLATION.md`, which you received with the app: checksum, unzip, move to Applications, first launch,
and how to uninstall. It takes about five minutes.

## What to test

Please spend 30–60 minutes over the first week, mostly with **your own files**. Keep copies of anything important
until you have checked the converted results.

1. **Everyday photos.** Convert iPhone HEIC photos to JPEG, and some to PDF. Are portrait photos the right way up?
   Do colours look the same?
2. **PDFs.**
   - Convert a multi-page PDF to PNG or JPEG. You should get one image per page, in order.
   - Combine several photos and PDFs into one PDF with **Merge into one PDF**. Check the page order and that PDF text
     can still be searched (Cmd-F in Preview).
3. **Protected PDFs.** If you have bank statements or forms, try converting one. Papyr should either convert it to
   images or explain in one sentence why it won't. It must never make an unprotected copy.
4. **Animations.**
   - Convert an animated GIF to WebP. It should still move at the same speed.
   - Convert it to PNG with **Every frame** on. You should get one numbered file per frame.
5. **Batches.**
   - Add a whole folder (**Add Folder…**) or drag 50+ files onto the window.
   - Try **Cancel** part way through.
   - Include a broken file (a photo copied while still downloading, for example) and check that the rest still
     convert, then try **Retry Failed**.
6. **Everyday use.**
   - Drag files from Finder and onto Papyr's Dock icon, and use right-click → Open With → Papyr.
   - Change the Save to folder, quit, and reopen. It should remember the folder.
7. **Notebooks** (if you use Jupyter): convert a notebook to PDF and check the text, code, and plots.

Note anything slow, confusing, or surprising, not only crashes.

## Known limitations

- Ad-hoc signed and not notarized, so first launch needs approval (see above).
- Tested on macOS 15.8 and 26.6 only.
- A PDF to JPEG or PNG gives one file per page. That's intended: choose GIF for one animated file, or PDF for one
  document.
- Animated PNG files and HEIC bursts convert their first image only.
- A PDF that needs a password to open is refused. Encrypted PDFs never become a new PDF, and become images only if
  their owner allows copying.
- Very large animated WebP output (over about 134 million pixels in total) is refused to protect memory.
- On exFAT drives, a power cut during the last step of writing can leave a partly written file. After a crash, a
  hidden `.papyr-….part` file can remain in the folder. It is safe to delete.
- Small window issues:
  - **Edit → Remove Selected** is greyed out while the Edit menu is open. Delete still works.
  - Thumbnails of removed files stay in memory until you quit.
  - A duplicate dropped together with new files is skipped without a notice.
- The About box says 2.3.1. Please call this build **2.3.1-beta.1** in reports.

## Reporting bugs

Report through **GitHub issues** at <https://github.com/guntisid2007/papyr/issues> (free account needed). If
you'd rather not post publicly, send the same details back the way you received the beta.

Issues on GitHub are public: anyone can read them.

Put **[beta.1]** at the start of the title, and include:

1. **System:** Mac model, chip, and macOS version (Apple menu → About This Mac).
2. **Version:** 2.3.1-beta.1.
3. **What you did:** the steps, the files (format, size, pages), and the output format with its options.
4. **What you expected, and what happened.** Copy the exact sentence Papyr showed, if any.
5. **Screenshot** of the window or message (Cmd-Shift-4, then drag around it).
6. **Log:** `~/Library/Logs/Papyr/papyr.log` (Finder → Go → Go to Folder…). It holds file paths and error messages,
   never file contents. Remove any path you'd rather not share.
7. **Crash report**, if Papyr quit unexpectedly: the file starting with `Papyr` in
   `~/Library/Logs/DiagnosticReports`.
8. **A sample file**, only if you're comfortable sharing it publicly. Otherwise describe it.

When you're done, please fill in `BETA-FEEDBACK-TEMPLATE.md`, even if everything worked.

## Stopping

To stop testing, follow **Uninstall** in `INSTALLATION.md`. Your converted files are never deleted.
