# Papyr 2.3.1-beta.1 release readiness

Prepared 2026-11-01 on Siddharth's Mac mini (macOS 26.6.2, Apple silicon, Python 3.12.16) and GitHub Actions. It
follows `beta-readiness-report.md` from the MacBook, and its numbers come from runs here, not from that report.

## Verdict

**READY FOR LIMITED BETA**, for macOS on Apple silicon only.

- **Why a beta at all.** The full suite passes everywhere: 1,261 tests, none failing. That includes all 110
  supported conversion pairs (500 of 500 conversions, each checked independently of the converter), on four CI
  platforms and on a real Mac. The packaged app passes its self-test on all four.
  The three release concerns are fixed and tested: encrypted PDFs, the overwrite race, and output preferences. An
  independent review found four more defects, and all are fixed.
- **Why limited.** The app is not signed with a Developer ID or notarized, so Gatekeeper blocks it until each tester
  approves it. No person has yet used native file dialogs, Finder drag and drop, the Dock, Cancel, or Quit during a
  conversion on this build. This session could not automate them (see [Native macOS](#native-macos-interaction)).
- **Why only Apple silicon.** Intel macOS, Windows, and Linux pass every automated test and package self-test in CI,
  but no person has run the app on them.

Public beta needs at least two things: a person to complete `native-macos-checklist.md` on this build, and Developer
ID signing and notarization, or a decision to ship unsigned with the documented Gatekeeper steps.

## Git state

| | |
| --- | --- |
| Branch | `test/comprehensive-conversion-validation` |
| Base | `74e75c9` (MacBook beta work, imported by Git bundle) |
| Commits added here | `a6ede95` `77aa438` `67a8fd0` `d500c08` `3fcb41e` `12b2fda`, plus this documentation commit |
| Remote branch | Pushed to `origin/test/comprehensive-conversion-validation`, fast-forward only, never forced |
| `main` | Unchanged at `5706e71` (local and `origin/main`). Nothing merged, no tags, no releases. |
| Untracked and untouched | `assets/branding/`: all 119 files hash the same as before this work. `MACBOOK-HANDOFF.md` is unchanged. |

## Fixes

### Encrypted PDFs (`a6ede95`, `d500c08`)

Before, an RC4-encrypted PDF that opens without a password was copied into a new PDF without its owner restrictions.

- Papyr never copies an encrypted PDF into a new PDF, whatever the cipher (RC4-40, RC4-128, AES-128, AES-256), and
  says: "This PDF is protected. Papyr won't copy it into a new PDF, because the copy would lose that protection."
- An encrypted PDF becomes images or a GIF only if its permissions (`/P` bit 5, copy and extract) allow it. PDFium
  reads the permissions. Otherwise every format refuses it with: "This PDF's security settings don't allow its
  content to be copied, so Papyr won't convert it."
- The preview thumbnail still renders. Viewing is not export, and nothing is written.
- A PDF that needs a password is refused, as before.
- PDFium reports damaged encryption settings as a wrong password, so pypdf now tells the two apart. Damaged
  dictionaries say the file is damaged. An unknown security handler says Papyr can't open that kind of protection.
- Nothing was decrypted beyond what PDFium already did, and no dependency was added. Three AES fixtures were written
  once with pypdf and `cryptography` in a scratch environment and committed: two that allow copying, and one that
  needs a password.

Tests (all new or rewritten): copyable and copy-denied files for each cipher across every output; a password AES-256
file; a merged batch that keeps only the plain file; the preview; seven kinds of damaged encryption dictionary, each
with its exact sentence; and a batch that carries on after each. The GUI smoke test and an older format test pinned
the old behavior, so they were rewritten to assert the new one exactly.

### Output overwrite race (`a6ede95`, `d500c08`, `3fcb41e`)

Files move into place in this order:

1. The system's atomic no-replace rename: `renamex_np(RENAME_EXCL)` on macOS, `renameat2(RENAME_NOREPLACE)` on Linux,
   and `MoveFileExW` without replace on Windows (`src/utils/noreplace.py`).
2. A hard link.
3. A copy into a name created exclusively (`O_CREAT|O_EXCL`), followed by a check that the name still points at
   Papyr's file. If another program renamed over it, that program's file is kept and Papyr takes the next name.

Rollback removes a placed file only while its device, inode, and size still match what Papyr placed. That identity is
read before the move. On disks that report no inode numbers, rollback leaves the file and logs it rather than guess.

Measured on real volumes mounted from disk images on this Mac:

| Disk | No-replace rename | Hard link | Path Papyr uses |
| --- | --- | --- | --- |
| APFS | yes | yes | atomic rename |
| FAT32 (macOS) | yes | no | atomic rename |
| exFAT (macOS) | no (`ENOTSUP`); still refuses a taken name with `EEXIST` | no | exclusive copy |

**Remaining limitation (documented in README and release notes).** The exclusive copy never replaces a file, but it
is not atomic. If power is lost during it, a partly written file can remain under the new name.

Tests include:

- Real FAT32 and exFAT volumes on macOS: every file is written, existing files are untouched, and a taken name is
  refused.
- Four processes converting the same names into one folder, and three processes doing the same on each removable
  volume. Every output survives with its own colour.
- A competitor renaming over the name during the copy.
- A file saved over Papyr's just after the move, which rollback must not delete.
- Failures part way through placement, and disks that refuse `chmod`.
- Windows can't replace a file another program holds open, so the copy-race test is skipped there and the skip says
  so.

### Output permissions (`a6ede95`, `d500c08`, new defect)

Since 2.3.1, every output kept `mkstemp`'s owner-only mode `0600`, so other accounts and some shared folders couldn't
read converted files. Outputs now get `0666 & ~umask`, which is `0644` normally. Disks that refuse mode changes (FAT on
Linux) still get their files.

### Output folder preferences (`77aa438`)

- This Mac mini has never stored a Papyr preference, so no temporary folder is configured here
  (`~/Library/Preferences` has no Papyr file). The MacBook's preferences were not reachable from this machine and
  were not checked.
- Existing tests cover the rest: a first launch uses Documents and shows it; a chosen folder persists; a deleted
  folder falls back to Documents at launch; a folder deleted or made unwritable mid-session blocks Convert with a
  reason. New tests check that the first launch saves nothing until a folder is chosen, and that tests keep
  preferences in their own folder.
- `conftest.py` now applies isolation at import, before any test can open a window.
- `PAPYR_SETTINGS_DIR` points the real or packaged app at its own preferences. It is used by the self-test, by CI
  packaging, and by the native launch below.
- The packaged self-test opens the main window, so before this change it read the user's real preferences.

### CI workflow (`67a8fd0`, `3fcb41e`, `12b2fda`)

- **Triggers.** `conversion-validation.yml` ran only on pull requests or manual dispatch, and manual dispatch needs
  the file on `main`, so pushing the branch would have run nothing. It now runs on pushes to `test/**`.
- **Architecture.** Each job asserts `platform.machine()` (arm64, x86_64, AMD64, x86_64), so the Intel job can't
  silently run on Apple silicon.
- **Totals.** JUnit totals are printed, with every skip named.
- **Packaging.** A packaging job builds each platform with PyInstaller into `ci-dist/` and runs the packaged
  self-test. On macOS it also unzips the ZIP and runs the self-test again. It uploads 14-day artifacts with SHA-256
  files and never publishes.
- **Timeout.** The Intel runner needs about 20 minutes for the matrix, so the timeout went from 40 to 90 minutes.
- `actionlint` 1.7.12 reports nothing for this workflow. `build.yml` is unchanged; it has one informational
  shellcheck note on `main`.

### Test-oracle fixes found on Windows (`12b2fda`)

Windows lays the matrix notebook out with its final output line alone on page 6, and two checks misjudged that:

- The "blank page" check measured ink only. A low-ink page now passes only if it has text and that text is visibly
  dark where PDFium places it.
- `ink_match` gave precision 0 when a frame had no dark ink at all. It now gives 1; lost text is still caught by
  recall.

Two new sensitivity tests prove both checks still fail an invisible last line and a frame whose text is gone. No
assertion was loosened.

## Independent review

One review ran, from a reviewer with no context from this session. It was the same model family (Claude Opus 5.5),
because no other provider was available on this machine (Codex not installed; others disabled). It read the source
diff of `a6ede95`–`67a8fd0` and ran its own reproductions.

| Finding | Status |
| --- | --- |
| Rollback could delete a file another program saved over Papyr's just after the move (reproduced) | Fixed in `d500c08`, with a test |
| A stat failing after a move escaped rollback and left a page (reproduced) | Fixed in `d500c08`, with a test |
| Damaged encryption said "password-protected" (reproduced) | Fixed in `d500c08`, with exact-message tests |
| `chmod` failing on Linux FAT would fail every file (reasoned) | Fixed in `d500c08`, with a test |
| Identity on shares without inode numbers (reasoned) | Rollback now leaves such files, with a test |
| Reading the umask briefly sets it process-wide (reasoned) | Left. It happens once at import, before conversion threads exist. |
| No bypass of the encrypted-PDF policy found across PDF, image, GIF, notebook, and every-frame paths | — |

CI then found a fifth defect: the copy fallback removed its file while still holding it open, which Windows refuses.
It is fixed in `3fcb41e`. In practice Windows never reaches that fallback, because its rename never replaces a file.

## Test results

| Run | Tests | Passed | Failed | Skipped | Matrix |
| --- | --- | --- | --- | --- | --- |
| Mac mini, before changes (`74e75c9`) | 1,217 | 1,217 | 0 | 0 | — |
| Mac mini, final (`12b2fda`) | 1,261 | 1,261 | 0 | 0 | 110/110 pairs, 500/500 |
| CI macOS Apple silicon (macOS 15.8.2, arm64) | 1,261 | 1,261 | 0 | 0 | 110/110, 500/500 |
| CI macOS Intel (macOS 15.7.9, x86_64) | 1,261 | 1,261 | 0 | 0 | 110/110, 500/500 |
| CI Windows (Server 2025, AMD64) | 1,261 | 1,232 | 0 | 29 | 110/110, 500/500 |
| CI Linux (Ubuntu 22.04, x86_64) | 1,261 | 1,250 | 0 | 11 | 110/110, 500/500 |

CI is run [41287141119](https://github.com/guntisid2007/papyr/actions/runs/41287141119), at `12b2fda`.

Every skip is platform-specific and states its reason:

- POSIX permissions and modes on Windows.
- The macOS app bundle and the macOS gray profile, on other systems.
- `hdiutil` volumes, which only macOS can mount.
- A font with an fi ligature.
- The system appearance switch.
- The copy race that Windows can't have.

One local full run, which isn't counted above, had 9 notebook matrix failures with "No such file". The review agent
was running tests in the same checkout, and the fixture builder rebuilds `tests/fixtures/generated/` on each run. The
matrix alone then passed 575 of 575. Don't run two test sessions in one checkout.

Earlier CI runs (41217531898, 41218417801, 41285773420) failed on Windows and timed out on Intel. They are the
failures diagnosed above and are kept for the record.

`pip-audit` reports no known vulnerabilities for `requirements.txt` or `requirements-dev.txt`.

## Platform status

| Platform | Tests executed / passed | Package build | Executable smoke test | Known issues |
| --- | --- | --- | --- | --- |
| macOS Apple silicon | 1,261 / 1,261 on the Mac mini and in CI | `.app` and ZIP, arm64 (local and CI) | Self-test passed, before and after unzip. Launched through LaunchServices with a PNG and a 12-page PDF; ran 11 s and exited cleanly; no crash report. | Native interactions not driven by a person; unsigned |
| macOS Intel | 1,261 / 1,261 in CI | `.app` and ZIP, x86_64 (`lipo` checked), CI | Self-test passed, before and after unzip, in CI | No person has run it; unsigned; slow runner |
| Windows | 1,261 run, 1,232 passed, 29 skipped, in CI | `Papyr.exe` folder ZIP, CI | Self-test exit code 0 in CI | No person has run it; unsigned (SmartScreen) |
| Linux | 1,261 run, 1,250 passed, 11 skipped, in CI | `tar.gz`, CI | Self-test passed in CI (offscreen) | No person has run it; needs glibc 2.35+ |

CI package SHA-256 values (14-day test artifacts, not releases):

| Asset | SHA-256 |
| --- | --- |
| Papyr-macOS-AppleSilicon.zip | `1766689bb60f8e74b880f5e1d316c0fa75c50591cb192131bb7a981773a4a849` |
| Papyr-macOS-Intel.zip | `55da8e02d2627ea1acf6fa013d84d1cbfc5b36c064fd3ddd97e65e2e8b7fd132` |
| Papyr-Windows.zip | `88081a1c97dca854fa9efa57a4f8a2dba972db6925a76bb0ccf79200f2ae9f19` |
| Papyr-Linux-x86_64.tar.gz | `58079f517c78a5362ff2839dfa648a220e4c08354b4d5e28b577446a38b0b9ed` |

Packaging review:

- Each bundle carries libheif, libavif, libwebp (with mux and demux), and pdfium, plus Qt's `cocoa`, `offscreen`, and
  `minimal` platform plugins on macOS.
- The self-test exercises HEIC and AVIF codecs, PDF writing and rendering, notebook layout, the window, the
  encrypted-PDF refusal, and the no-replace move, all through each bundle's own libraries.
- The icon comes from `assets/icon.icns` or `icon.ico`.
- File dialogs are Qt's native ones. No person has opened them on any packaged build.

## Native macOS interaction

Driving the native UI requires macOS Accessibility or Automation permission, and capturing the screen requires Screen
Recording permission, for the process running the agent. Neither was granted. The first `osascript` and
`screencapture` probes hung, waiting on a permission prompt nobody could answer, and were stopped. Granting those
permissions changes system security settings, so they were left for you to decide.

**Done:** the packaged app launched through LaunchServices with documents (`open -n --env PAPYR_SETTINGS_DIR=… -a
Papyr.app photo.png twelve-pages.pdf`). That is the same open-document path as Finder's Open With and Dock drops. It
stayed running, exited on SIGTERM, wrote no crash report, and created no real preferences. The window's contents
couldn't be observed.

**Not done:** Browse Files, Add Folder, Finder drag and drop, reordering, choosing the format and the destination,
Convert, Cancel, Retry Failed, Reveal in Finder, closing the window or quitting during a conversion. The offscreen GUI
suite (`test_gui.py` and `test_gui_smoke.py`) covers their logic, but that is not native coverage.
`native-macos-checklist.md` lists all 20 steps for a person.

## Beta package

| | |
| --- | --- |
| Path | `/Users/siddharthgunti/papyr-release-assets/v2.3.1-beta.1/` (outside the repository; `build/` and `dist/` untouched) |
| File | `Papyr-2.3.1-beta.1-macOS-AppleSilicon.zip` (45,283,315 bytes), with `.sha256`, `RELEASE-NOTES.md`, and `BUILT-FROM.txt` |
| Package type | macOS `.app` in a ZIP made with `ditto --sequesterRsrc --keepParent` |
| Version | `v2.3.1-beta.1`. The bundle reports `CFBundleShortVersionString` 2.3.1; the version was not bumped. |
| Built from | `12b2fda`, exported with `git archive`, PyInstaller 6.22.3, arm64 |
| SHA-256 | `789e9564e777aabe130bd98f4f3a1534a9f858de3213b2d652c31b8510a5f9e4` |
| Signing | Ad-hoc only (`codesign --verify --deep --strict` passes). No Developer ID, not notarized; `spctl` rejects it. |
| Checked after unzip | Executable bit kept; all 356 files, modes, and symlinks identical to the built bundle; self-test passed |

Not uploaded, not tagged, not released.

## Remaining limitations and decisions

1. **Signing and notarization.** These need an Apple Developer ID. The release notes give the per-app "Open Anyway"
   steps and don't suggest turning off Gatekeeper.
2. **Native interactions.** A person should run `native-macos-checklist.md` on this build, or grant the automation
   permissions so it can be scripted.
3. **The exclusive copy is not atomic.** On disks without an atomic no-replace move (exFAT on macOS, some network
   shares), a power loss during the final copy can leave a partly written file under the new name.
4. **Version.** The bundle says 2.3.1. Bumping to a beta version string is a release decision; it was not made here.
5. **Unchanged from the MacBook report:**
   - Three small GUI issues: Remove Selected greyed out while the Edit menu is open, cached thumbnails of removed
     files, and a duplicate dropped with a new file skipped silently.
   - Animated WebP memory cap and frame merging.
   - Animated PNG and multi-image HEIC convert their first image only.
   - No PDF page-count limit.
   - A hidden `.papyr-*.part` file can remain after a crash.
