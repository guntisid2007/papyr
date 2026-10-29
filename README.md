<p align="center"><img src="assets/icon.png" width="96" alt="Papyr icon"></p>

<h1 align="center">Papyr</h1>

<p align="center">A free, offline desktop converter for photos and PDFs.<br>
HEIC, JPEG, PNG, WebP, AVIF, TIFF, BMP, GIF, and PDF, from any of them to any of them.</p>

<p align="center"><a href="https://github.com/guntisid2007/heic-to-pdf/releases/latest"><b>Download the latest version</b></a></p>

![Papyr with five photos ready to combine into one PDF](docs/screenshots/main-light.png)

Papyr turns iPhone photos (HEIC) into PDFs or JPEGs, PDFs into images, PNGs into WebP, and any other combination of common image formats and PDF. It runs on your computer and never sends your files anywhere. You do not need Python or any other software to use it.

## Features

- **Any to any.** Reads HEIC, HEIF, JPEG, PNG, WebP, AVIF, TIFF, BMP, GIF, and PDF. Writes PDF, JPEG, PNG, HEIC, WebP, AVIF, TIFF, GIF, and BMP.
- Drag and drop files or whole folders, or pick them with the Browse button.
- Thumbnails, names, and sizes for every file. Remove files, reorder them by dragging or with the arrow buttons, or clear the list. Unreadable files are flagged as soon as you add them.
- **To PDF:**
  - One PDF per file, or everything combined into one PDF in list order.
  - Page size: original image size, A4, or US Letter. Pages turn landscape automatically for wide photos.
  - Adjustable margins. Images are scaled to fit without stretching.
  - PDFs you add keep their own pages, and their text stays sharp and searchable, so Papyr also merges PDFs.
- **To an image format:**
  - Adjustable quality for JPEG, HEIC, WebP, and AVIF.
  - Each page of a PDF becomes its own image (`report-page-1.png`, `report-page-2.png`, …), rendered at 100, 150, 200, or 300 DPI.
  - Transparency is kept in PNG, HEIC, WebP, AVIF, TIFF, and GIF, and filled with white in JPEG and BMP.
- Photos taken sideways or upside down come out the right way up.
- Colours are converted to standard sRGB so they look right everywhere.
- Never overwrites anything. If a file with the same name exists, Papyr adds a number, such as `photo (1).jpg`.
- A progress bar and a Cancel button. The window stays responsive while it works.
- When conversion finishes, the new file flies into a folder, and "Show in Folder" opens the results.
- Remembers your output folder and settings, and follows your system's light or dark mode.

![The finished file flying into the output folder](docs/screenshots/save-animation.gif)

| Light mode | Dark mode, converting to JPEG |
| --- | --- |
| ![Empty window in light mode](docs/screenshots/empty-light.png) | ![Window set to convert to JPEG in dark mode](docs/screenshots/main-dark.png) |

## Download and install

Go to the [Releases page](https://github.com/guntisid2007/heic-to-pdf/releases/latest) and download the file for your computer.

| Your computer | File to download |
| --- | --- |
| Mac with Apple silicon (M1, M2, M3, M4, and later) | `Papyr-macOS-AppleSilicon.zip` |
| Mac with an Intel processor | `Papyr-macOS-Intel.zip` |
| Windows 10 or 11 (64-bit) | `Papyr-Windows.zip` |
| Linux (x86-64) | `Papyr-Linux-x86_64.tar.gz` |

Not sure which Mac you have? Open the Apple menu and choose **About This Mac**. It says "Chip: Apple M…" for Apple silicon, or "Processor: … Intel" for Intel.

### macOS

1. Double-click the downloaded `.zip` to unzip it. You get **Papyr.app**.
2. Drag **Papyr.app** into your **Applications** folder.
3. Open it. The first time, macOS shows a warning that it cannot verify the app, because the app is not signed with a paid Apple Developer certificate (see [Known limitations](#known-limitations)). To open it anyway:
   - Click **Done** (or **OK**) on the warning.
   - Open **System Settings → Privacy & Security**, scroll down, and click **Open Anyway** next to the message about Papyr.
   - Confirm with your password or Touch ID, then click **Open**.

   You only need to do this once.

### Windows

1. Right-click the downloaded `.zip` and choose **Extract All…**.
2. Open the extracted **Papyr** folder and double-click **Papyr.exe**.
3. If Windows SmartScreen says "Windows protected your PC", click **More info**, then **Run anyway**. This appears because the app is not code-signed.

Keep `Papyr.exe` inside its folder; it needs the files next to it. To make it easy to find, right-click the `.exe` and choose **Send to → Desktop (create shortcut)** or **Pin to Start**.

### Linux

```sh
tar -xzf Papyr-Linux-x86_64.tar.gz
./Papyr/Papyr
```

The build was made on Ubuntu 22.04 and needs glibc 2.35 or newer plus the usual desktop libraries. If it fails to start on Debian or Ubuntu, install `libxcb-cursor0`.

## How to use

1. Drag photos, PDFs, or folders onto the window, or click **Browse Files…** or **Add Folder…**.
2. Arrange the list. Drag rows, or select a row and use **↑** and **↓**. Press **Delete** or click **Remove** to drop a file.
3. Under **Convert to**, pick the format you want.
   - For **PDF**, choose **One PDF per file** or **Combine into one PDF** (type a name), then a page size and margins.
   - For an image format, set the quality, and the resolution for PDF pages if you added PDFs.
4. Click **Choose Folder…** to pick where the results go.
5. Click **Convert**. When it finishes, click **Show in Folder**.

If a file cannot be read (for example, it is damaged or password-protected), it is marked in the list. Conversion skips it, carries on with the rest, and tells you which files were skipped.

## Privacy

- Everything happens on your computer. The app makes no network connections.
- No accounts, no telemetry, no analytics, no API keys.
- Photo metadata such as GPS location, camera model, and date is **not** copied into the converted files.
- The app writes nothing except the files you ask for. Each file is written to a temporary file in the destination folder and renamed when complete, so a cancelled or failed conversion leaves no partial files behind.

## Supported systems

| System | Status |
| --- | --- |
| macOS 14.4 (Sonoma) or later, Apple silicon | Built and tested in CI on every release |
| macOS 14.4 (Sonoma) or later, Intel | Built and tested in CI on every release |
| Windows 10 and 11, 64-bit | Built and tested in CI on every release |
| Linux x86-64 (glibc 2.35+) | Built and tested in CI on every release |

"Tested in CI" means the automated test suite runs on that system, and the packaged app converts HEIC to PDF, PDF to PNG, and PNG to every image format there before the download is published.

## Known limitations

- **Not code-signed or notarized.** The macOS app has only an ad-hoc signature. It is not signed with an Apple Developer ID or notarized by Apple, so Gatekeeper asks you to approve it once (steps above). The Windows app is not signed either, so SmartScreen may warn. Signing needs paid certificates, which this project does not have.
- Images become image pages in a PDF, so text in photos is not searchable (no OCR). PDFs you add keep their text.
- Turning a PDF into an image renders it at the DPI you choose; the image has no selectable text.
- Animated GIF and WebP files, and multi-image HEIC files such as bursts, convert their first image only. Multi-page TIFF files convert every page.
- In a combined PDF, page size and margins apply to image pages; pages from PDFs keep their original size.
- Password-protected PDFs are not supported.
- HDR and wide-gamut detail is converted to standard 8-bit sRGB.
- Images larger than about 178 megapixels are refused to protect your computer's memory.
- "Original image size" uses one image pixel per PDF point (1/72 inch), so a 12-megapixel photo makes a page about 142 × 107 cm. Choose A4 or Letter for printable pages.

## Run from source

You need Python 3.10 or newer.

```sh
git clone https://github.com/guntisid2007/heic-to-pdf.git
cd heic-to-pdf
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python src/main.py
```

Run the tests:

```sh
python -m pytest
```

## Build the app yourself

```sh
pyinstaller --noconfirm --clean papyr.spec
```

This produces `dist/Papyr.app` on macOS and `dist/Papyr/` on Windows and Linux. PyInstaller builds only for the system it runs on, so build on each platform. To check a build, run the packaged binary with `--self-test tests/fixtures/sample.heic`. It exits with code 0 when every conversion path works.

Releases are built by [GitHub Actions](.github/workflows/build.yml). Pushing a tag such as `v2.0.1` runs the tests, builds every platform, smoke-tests each packaged app, and attaches the builds that passed to a new release with a `SHA256SUMS.txt` file.

## Project layout

```
src/main.py            entry point and the packaged-app self-test
src/converter/         decoding, page layout, PDF and image writing (no GUI code)
src/gui/               Qt window, widgets, save animation, and background workers
src/utils/             file collection, output names, app name, bundled asset paths
assets/                app icons
tests/                 pytest suite, a sample HEIC file, and PDF builders
scripts/               regenerate icons, screenshots, the animation GIF, and the sample HEIC
```

## Contributing

Bug reports and pull requests are welcome.

1. Open an issue that describes the bug or the change.
2. Fork the repository and create a branch.
3. Keep conversion logic in `src/converter/`, with no Qt imports, and add a test for any behaviour change.
4. Run `python -m pytest` and make sure it passes.
5. Open a pull request. CI builds and tests every platform.

Please never add network access, telemetry, or anything that sends files off the user's computer.

## License

[MIT](LICENSE)

Built with [PySide6](https://doc.qt.io/qtforpython-6/) (Qt, LGPLv3), [Pillow](https://python-pillow.org/), [pillow-heif](https://github.com/bigcat88/pillow_heif) (libheif, LGPLv3), [pypdf](https://github.com/py-pdf/pypdf) (BSD), and [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) (PDFium, Apache 2.0 and BSD). The packaged apps ship these libraries as separate, replaceable files.
