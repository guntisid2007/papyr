# Native macOS checklist for Papyr 2.3.1-beta.1

Automated tests drive the window offscreen. They don't open real system dialogs, Finder drag and drop, or the Dock.
A person runs this checklist on the packaged app before each beta goes out. It takes about 15 minutes.

For 2.3.1-beta.1, run the detailed version instead: [`docs/beta/MANUAL-ACCEPTANCE-TEST.md`](../../docs/beta/MANUAL-ACCEPTANCE-TEST.md)
(39 tests covering all 20 steps below, with results in `MANUAL-ACCEPTANCE-RESULTS.md`). Test only the approved ZIP,
SHA-256 `a47235c84266594eff732c1b69e089a42a1379f99da256e497c24444602046d1`.

## Before you start

1. Quit any running copy of Papyr. The older app in `dist/` and this one share preferences.
2. Start the beta with its own preferences, so the checklist can't change where your own files are saved:

   ```sh
   mkdir -p /tmp/papyr-checklist
   open -n --env PAPYR_SETTINGS_DIR=/tmp/papyr-checklist -a /path/to/Papyr.app
   ```

3. Have ready: two photos (one HEIC), a multi-page PDF, an animated GIF, a Jupyter notebook, a damaged file (any
   picture cut in half with `head -c 2000 photo.jpg > broken.jpg`), and a folder that holds some of them.

Write down a pass or fail for each step, and the macOS version and Mac model.

## Checklist

| # | Step | Expected |
| --- | --- | --- |
| 1 | First launch | The window opens. Save to shows Documents. |
| 2 | Browse Files: pick two photos in the system file dialog | Both appear in the list with thumbnails. |
| 3 | Add Folder: pick the prepared folder | Every supported file in it is added. Hidden files are not. |
| 4 | Drag files from Finder onto the window | They are added. Dragging a web link from Safari is refused. |
| 5 | Drag a file onto Papyr's Dock icon | It is added. |
| 6 | Reorder by dragging a row | The order changes, and a combined PDF follows the new order. |
| 7 | Pick each output format in turn | The options shown match the format. |
| 8 | Save to: choose a different folder in the system dialog | The new folder is shown. After quitting and reopening, it is still chosen. |
| 9 | Convert to PDF with the damaged file included | The others convert. The damaged file is listed with one plain sentence. |
| 10 | Retry Failed | Only the damaged file is tried again, and it fails again with the same sentence. |
| 11 | Reveal in Finder | Finder opens with the new files selected. |
| 12 | Convert the 12-page PDF to JPEG | Twelve JPEGs, `-page-1` to `-page-12`, in page order. |
| 13 | Convert the animated GIF to WebP | One WebP that plays like the GIF. |
| 14 | Start a large conversion, then Cancel | It stops. Finished files stay. No half-written file is left, and no `.papyr-` file is visible with hidden files shown (Cmd-Shift-.). |
| 15 | Start a large conversion, then close the window | Papyr stops the conversion and closes without a crash report. |
| 16 | Start a large conversion, then Cmd-Q | Papyr quits without a crash report. |
| 17 | Convert into a folder that already has a file of the same name | The old file is untouched. The new one is named `name (1)`. |
| 18 | Convert onto a USB stick or SD card formatted exFAT or FAT32 | Files are written, and existing files are untouched. |
| 19 | Delete the Save to folder in Finder, then return to Papyr | Papyr says the folder is missing and won't convert until you choose another. |
| 20 | Convert a PDF whose owner forbids copying (for example one exported with "Restrict copying" in Preview) | Papyr refuses it with a plain sentence. Its preview thumbnail still shows. |

## Afterwards

Delete `/tmp/papyr-checklist`. Report failures as described in the release notes, with the step number.
