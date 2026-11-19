# Opening OhYesMLX for the first time

This page is for a user who has downloaded `OhYesMLX-<version>.dmg` from GitHub Releases and
has never opened an unsigned app before. It needs no Terminal.

## Install it by dragging it out of the disk image

1. Double-click `OhYesMLX-<version>.dmg`. A Finder window opens showing **OhYesMLX** and an
   **Applications** folder beside it. The disk image is read-only, so you cannot run the app
   from inside it and nothing is installed until you copy it out.
2. **Drag `OhYesMLX` onto the Applications folder in that window.** That is the whole install:
   the copy in Applications is the one you keep.
3. Eject the disk image (the eject button beside its name in the Finder sidebar).

Do this first, every time. If you open the app while it still sits in Downloads, on the Desktop
or on the mounted disk image, macOS runs it from a hidden, temporary copy under its
**App Translocation** path, and that path changes on every launch. Anything OhYesMLX installs
from there would point at a copy that no longer exists the next time you open it.

If you open it from the wrong place anyway, OhYesMLX does not try to work around it: it shows
one screen saying **"Move OhYesMLX to your Applications folder, then open it again"** and a
**Quit** button. Nothing is installed from that run. Move the app and open it again. That
screen is reached only after macOS has let the app run at all, so on a first launch it comes
after the approval step below, not before it.

If you move the app **after** you have installed engines, open the Engines screen and install
**mlx-lm** and **OptiQ** again: each engine is a Python environment built inside the app's own
copy of Python, and moving the app leaves the old one behind. The Engines screen will show those
engines as not installed, so installing them again replaces the old environment instead of
refusing. Your downloaded models and your results are not affected — they do not live inside the
app.

## The first open is blocked before any of the app runs

OhYesMLX is **not notarized**. Notarization is Apple's automated security check on software
distributed outside the App Store, and it needs a paid Apple Developer account. This app is a
free, unsigned project release, so it ships **ad-hoc signed only**. The signature's one job is to
let macOS run the code once it is approved: it carries no developer identity, so anyone who
altered the app could sign it again and it would still run. The **published sha256 — not the
signature — is what shows your download is unaltered**.

macOS checks the download before it executes a single instruction of it. There is no partially
started app, no backend process and no window: the app is stopped at the gate. The first time you
open it you get a dialog saying Apple could not verify OhYesMLX, with **Move to Trash** and
**Done**. Click **Done** — *not* Move to Trash. The app has not run, and nothing has told macOS
yet that you want it; that is what the next step is for.

## Approve it once, then open it

**Open Anyway must come first.** Clicking Open on the first dialog does not exist, because the
app was never allowed to start:

1. Click **Done** on the dialog (or **Cancel**, on older macOS — either dismisses it). Do not
   click **Move to Trash**: that deletes the app.
2. Open **System Settings** (Apple menu > System Settings), then **Privacy & Security**.
3. Scroll down to the **Security** section. You will see a line about OhYesMLX being blocked
   because it is not from an identified developer, with an **Open Anyway** button.
4. Click **Open Anyway**, then confirm with your password or Touch ID.
5. Open OhYesMLX from Applications again. It is now allowed to run, and macOS asks once more
   with an **Open** button; click **Open**.

You only do this once per copy of the app. If you move or replace the app, macOS asks again.
Until step 4 has happened, nothing about the app executes — so the **"Move OhYesMLX to your
Applications folder"** screen (the App Translocation guard) can only appear on the first launch
that was actually approved, and only if that approved launch was from Downloads, the Desktop or
the disk image rather than from Applications.

## Why it is safe to check for yourself

You do not have to take the release on trust, and the release is built so you can see what it
is made of:

- **A sha256 file is published next to the disk image.** The release build writes
  `OhYesMLX-<version>.dmg.sha256` beside the image, and the release notes list the same value.
  Anyone can compute it from the file they received, and the two matching means the file you have
  is the file that was published. It takes one line in Terminal
  (`shasum -a 256 OhYesMLX-<version>.dmg`); if you would rather not open Terminal, skip this
  one and read the SBOM instead.
- **An SBOM ships with every release.** `OhYesMLX-<version>-sbom.json` is a plain text file you
  can open in TextEdit. It lists the exact CPython build bundled inside the app (with the URL
  it came from and its sha256), the OhYesMLX version, the git commit it was built from, a
  sha256 of the app's Python source, the Swift toolchain that built the app, and every Python
  package pinned for each engine (`mlx-lm` and `OptiQ`) with the hash of every file that may be
  installed. An engine install refuses any file whose hash is not in that list.

The app itself makes network requests only to Hugging Face (when you download a model) and to
PyPI (when you install an engine). When an engine has no installer it can run for you, it opens
that vendor's own download page in your browser and leaves the installing to you. Nothing is
uploaded, and nothing is ever sent anywhere else.

## What the app writes, and how to remove it all

OhYesMLX keeps five places on disk:

| Where | What it holds |
|---|---|
| `~/Library/Application Support/OhYesMLX` | Engine environments (a Python environment per engine), the list of what has been downloaded, the install and download logs, benchmark summaries, and a single-instance lock file. Created so that only your account can read it. |
| `~/.cache/huggingface/hub` | The models you downloaded, in the standard Hugging Face cache layout. Shared with any other tool that uses it. |
| `~/Library/Caches/OhYesMLX` | The build cache: the copy of Python the release was assembled from. Only used when building from source, never at runtime. |
| `~/Library/Caches/pip` | Not made by OhYesMLX, but shared with anything else on your Mac that runs pip: every tool that installs Python packages fills it. OhYesMLX's own engine installs pass `--no-cache-dir`, so they do not add to it — anything already there belongs to you or another tool, and deleting the folder only costs a re-download. |
| `~/Library/Preferences/io.github.jasonrandazza.ohyesmlx.plist` | The app's small preferences record: window state and the last in-flight job, so a job interrupted by Quit is reported rather than silently lost. |

To remove everything the app has added:

1. Quit OhYesMLX.
2. In the Finder, press Shift-Command-G, paste `~/Library/Application Support/`, and move the
   **OhYesMLX** folder to the Trash.
3. Press Shift-Command-G again, paste `~/.cache/huggingface/` (the Finder shows it as
   `.cache`, which is hidden, so the Go-to-Folder box is the easy way in), and delete the
   **hub** folder if you do not want the downloaded models for anything else.
4. Press Shift-Command-G once more, paste `~/Library/Preferences/`, and delete
   **io.github.jasonrandazza.ohyesmlx.plist**.
5. If you want the shared **pip** cache back too, open `~/Library/Caches/pip` the same way and
   move the **pip** folder to the Trash. OhYesMLX's engine installs do not write there, so this
   only reclaims what other tools cached.
6. Delete `OhYesMLX.app` from Applications, then move `OhYesMLX-<version>.dmg` to the Trash.

If you only want to free model space, the Models screen removes a downloaded model for you
without touching anything else.

## Notarization

Notarizing and Developer ID-signing this app is a separate step, and it is **not done**: it
needs a paid Apple Developer account first. When an account exists, the plan is to sign with a
Developer ID, notarize the app, staple the ticket to the bundle, build the disk image from the
stapled app, and re-check every packaging rule on the notarized build. Until then the
instructions above are the whole procedure, and the SBOM and sha256 are how you check the
download instead.

## Release check: quarantined download

This section is the release maintainer's check, not a step for a user. It runs the path every
downloader takes, once per release, on a Mac that did not build the app. It is the one check no
script performs: `check_bundle.sh` opens a locally built bundle that has never been quarantined.

1. Put the browser's quarantine flag on the disk image that will be published:

   ```
   xattr -w com.apple.quarantine "0083;$(printf %x "$(date +%s)");Safari;" OhYesMLX-<version>.dmg
   ```

2. Double-click the image and let macOS mount it. The Finder window shows `OhYesMLX` and the
   `Applications` symlink. Confirm the volume is read-only (`mount` says `read-only`), and that
   nothing can be written to it.
3. Drag `OhYesMLX.app` into Applications, as a user does. Dragging is the normal install, and the
   copy keeps the quarantine flag.
4. Open the copy in **Applications**. macOS blocks it **before any of its code runs**: expect the
   "Apple could not verify" dialog with **Move to Trash** and **Done**, and no backend process.
   A crash, a window, or a "Couldn't start" here means the block is not happening at the gate.
5. Approve it the way the steps above say — **Done**, then System Settings > Privacy & Security >
   **Open Anyway**, then **Open**. Confirm the app runs its own backend: the Hardware screen shows
   this Mac's chip and memory, which is a served `/hardware`. A "Couldn't start" here means the
   quarantined bundled interpreter, or one of its extension modules, would not load: the first
   public release would fail that way on every Mac but the builder's.
6. Now check the translocation guard, which only the wrong install path reaches. In Finder, copy
   the `.dmg`'s `OhYesMLX.app` to Downloads (or reopen it from the mounted image), and launch that
   copy. Because it is quarantined, expect the same block as step 4, then approve it; the first
   launch that macOS actually approves from Downloads or the image shows the move screen —
   "Move OhYesMLX to your Applications folder, then open it again" — and starts no backend. A
   crash or a "Couldn't start" here is the translocation guard failing under a real quarantine
   flag.

Record in the release summary that this ran, and the macOS version it ran on.
