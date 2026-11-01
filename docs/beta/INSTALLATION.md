# Installing Papyr 2.3.1-beta.1

For Macs with **Apple silicon** (M1 or later) running **macOS 15 or later**.

To check your Mac, open the Apple menu → **About This Mac**. It must say "Chip: Apple M…" and "macOS Sequoia" (15),
"macOS Tahoe" (26), or later. This beta doesn't include builds for Intel Macs, Windows, or Linux. The app declares
macOS 14.4 as its minimum, but macOS 14 hasn't been tested.

## What you receive

| File | What it is |
| --- | --- |
| `Papyr-2.3.1-beta.1-macOS-AppleSilicon.zip` | The app |
| `SHA256SUMS.txt` | The checksum, to confirm the download is intact |
| `INSTALLATION.md` | This guide |
| `RELEASE-NOTES.md`, `BETA-TESTER-GUIDE.md`, `BETA-FEEDBACK-TEMPLATE.md` | What changed, what to test, and how to report |

## About the security warning

This beta is **not signed with an Apple Developer ID and is not notarized by Apple**. It has only an ad-hoc
signature, which shows the app hasn't been altered since it was built, but not who built it. So the first time you
open it, macOS says it can't verify the app. Step 4 shows how to allow **this one app** through the normal macOS
setting. You never need to turn off Gatekeeper or any other macOS protection, and you shouldn't.

## 1. Download

Save the ZIP and `SHA256SUMS.txt` in the same folder, for example **Downloads**. Don't open the ZIP yet.

## 2. Check the checksum

This confirms the file is exactly the one that was tested.

1. Open **Terminal** (Applications → Utilities → Terminal).
2. Type `cd ` with a space after it, drag the folder holding the two files into the Terminal window, and press
   Return.
3. Run:

   ```sh
   shasum -a 256 -c SHA256SUMS.txt
   ```

4. It must print:

   ```
   Papyr-2.3.1-beta.1-macOS-AppleSilicon.zip: OK
   ```

   The full checksum is `a47235c84266594eff732c1b69e089a42a1379f99da256e497c24444602046d1`.

If it says `FAILED`, or anything else, **don't open the app**. Delete the ZIP and report it (see
[Problems](#problems-installing)).

## 3. Unzip and move to Applications

1. Double-click the ZIP. Finder creates **Papyr.app** beside it.
2. Drag **Papyr.app** into your **Applications** folder.
3. If you have an older Papyr, quit it first. When asked, choose **Replace**. Both versions use the same settings.

## 4. Open it the first time

1. Open **Applications** and double-click **Papyr**.
2. macOS says "Papyr" can't be opened because Apple cannot check it for malicious software, or that it can't verify
   the developer. Click **Done**. (It may say **OK** instead, depending on your macOS version.)
3. Open the **Apple menu → System Settings → Privacy & Security**.
4. Scroll down to **Security**. Next to the message about Papyr, click **Open Anyway**. The message appears there for
   about an hour after you tried to open Papyr; if it's gone, repeat step 1.
5. Confirm with your password or Touch ID.
6. Click **Open** in the dialog that follows.

Papyr opens. From then on it opens normally, with no warning.

If macOS instead says Papyr **"is damaged and can't be opened"**, stop. Don't use any Terminal command to get around
it. Report it, because it means the download or the app is broken.

## 5. First use

The window shows where converted files are saved (**Documents** at first). Add files with **Browse Files**,
**Add Folder**, or by dragging them onto the window. Choose a format and click **Convert**. The tester guide
explains what to try.

## Problems installing

Report installation problems the way the tester guide describes, and include:

- Your Mac model and macOS version (Apple menu → About This Mac).
- The step number above where it went wrong.
- The exact wording of any message, ideally a screenshot (press Cmd-Shift-4, then drag around the message).
- The output of the checksum command in step 2.

## Uninstall

1. Quit Papyr.
2. Drag **Papyr.app** from **Applications** to the Trash.
3. To remove its settings and log as well:
   - Settings: `~/Library/Preferences/com.papyr.Papyr.plist`.
   - Log of conversion problems: the folder `~/Library/Logs/Papyr`.

   In Finder, choose **Go → Go to Folder…** and paste each path to find it.
4. Empty the Trash.

Converted files stay where Papyr saved them. Uninstalling never deletes them.

Removing the settings also resets the Save to folder for any other copy of Papyr on this Mac, since all copies share
them.
