# Opening OhYesMLX for the first time

This page is for a user who has downloaded `OhYesMLX-<version>.zip` from GitHub Releases and
has never opened an unsigned app before. It needs no Terminal.

## Move OhYesMLX to Applications first

1. Double-click the zip to unpack it. You get `OhYesMLX.app`.
2. **Drag `OhYesMLX.app` into your Applications folder** before you open it. Open Applications
   from the Finder sidebar, or press Shift-Command-A.

Do this first, every time. If you open the app while it still sits in Downloads (or on the
Desktop or in a disk image), macOS runs it from a hidden, temporary copy under its
**App Translocation** path, and that path changes on every launch. Anything OhYesMLX installs
from there would point at a copy that no longer exists the next time you open it.

If you open it from the wrong place anyway, OhYesMLX does not try to work around it: it shows
one screen saying **"Move OhYesMLX to your Applications folder, then open it again"** and a
**Quit** button. Nothing is installed from that run. Move the app and open it again.

If you move the app **after** you have installed engines, open the Engines screen and install
**mlx-lm** and **OptiQ** again: each engine is a Python environment built inside the app's own
copy of Python, and moving the app leaves the old one behind. Your downloaded models and your
results are not affected — they do not live inside the app.

## The first open will be refused

OhYesMLX is **not notarized**. Notarization is Apple's automated security check on software
distributed outside the App Store, and it needs a paid Apple Developer account. This app is a
free, unsigned project release, so it ships **ad-hoc signed only**: macOS can tell the files
have not been changed since they were built, but it has no developer to vouch for them, and it
refuses the first launch.

The first time you open it you will see a dialog saying Apple could not verify OhYesMLX.

## The way past, on current macOS

1. Click **Done** (or **Cancel** — either closes the dialog).
2. Open **System Settings** (Apple menu > System Settings), then **Privacy & Security**.
3. Scroll down to the **Security** section. You will see a line about OhYesMLX being blocked
   because it is not from an identified developer.
4. Click **Open Anyway**, then confirm with your password or Touch ID.
5. Open OhYesMLX from Applications again. The dialog now offers **Open**; click it.

You only do this once per copy of the app. If you move or replace the app, macOS asks again.

## Why it is safe to check for yourself

You do not have to take the release on trust, and the release is built so you can see what it
is made of:

- **A sha256 is published next to the zip.** The release notes list the zip's sha256. Anyone
  can compute the same value from the file they received, and the two matching means the file
  you have is the file that was published. It takes one line in Terminal
  (`shasum -a 256 OhYesMLX-<version>.zip`); if you would rather not open Terminal, skip this
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

OhYesMLX keeps three places on disk:

| Where | What it holds |
|---|---|
| `~/Library/Application Support/OhYesMLX` | Engine environments (a Python environment per engine), the list of what has been downloaded, the install and download logs, benchmark summaries, and a single-instance lock file. Created so that only your account can read it. |
| `~/.cache/huggingface/hub` | The models you downloaded, in the standard Hugging Face cache layout. Shared with any other tool that uses it. |
| `~/Library/Caches/OhYesMLX` | The build cache: the copy of Python the release was assembled from. Only used when building from source, never at runtime. |

To remove everything the app has added:

1. Quit OhYesMLX.
2. In the Finder, press Shift-Command-G, paste `~/Library/Application Support/`, and move the
   **OhYesMLX** folder to the Trash.
3. Press Shift-Command-G again, paste `~/.cache/huggingface/` (the Finder shows it as
   `.cache`, which is hidden, so the Go-to-Folder box is the easy way in), and delete the
   **hub** folder if you do not want the downloaded models for anything else.
4. Delete `OhYesMLX.app` from Applications.

If you only want to free model space, the Models screen removes a downloaded model for you
without touching anything else.

## Notarization

Notarizing and Developer ID-signing this app is a separate step, and it is **not done**: it
needs a paid Apple Developer account first. When an account exists, the plan is to sign with a
Developer ID, notarize the zip, staple the ticket to the bundle, and re-check every packaging
rule on the notarized build. Until then the instructions above are the whole procedure, and the
SBOM and sha256 are how you check the download instead.
