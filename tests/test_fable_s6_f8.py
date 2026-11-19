"""Fable 5.2 S6-F8: the release promises a download sha256 that no step produces.

``docs/release/gatekeeper.md`` tells the reader "A sha256 is published next to the disk image.
The release notes list the image's sha256", and says "the SBOM and sha256 are how you check
the download".  ``scripts/build_app.sh`` — the only release build — names ``shasum``
in its header but never runs it: its last line printed ``$APP``, ``$ZIP`` and
``$SBOM`` and computed no digest, and ``scripts/make_sbom.py:128-147`` has no field that
could tie the SBOM to the shipped file, the Swift binary or the bundled tree.

Plan 05-14 replaced the zip with ``OhYesMLX-<v>.dmg``; the digest and its ``.sha256`` file
follow it (AC-1). The first test pins that pair. The second is evidence for the finding's
other limb — the doc credits the ad-hoc signature with tamper evidence — by showing that any
third party can replace a sealed file, re-sign ad hoc, and verify again, and that the
signature names no developer. That test is green by construction: it demonstrates the property
the doc overstates. Nothing here runs ``build_app.sh``, signs the real bundle, starts a server
or loads a model.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BUILD_APP = REPO / "scripts" / "build_app.sh"

DIGEST_COMMAND = re.compile(
    r"\b(?:shasum\s+-a\s+256|openssl\s+dgst\s+-sha256|hashlib\.sha256)\b"
)

INFO_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>invalid.verifier.probe</string>
<key>CFBundleExecutable</key><string>Probe</string>
<key>CFBundleName</key><string>Probe</string>
<key>CFBundlePackageType</key><string>APPL</string>
</dict></plist>
"""


def test_the_build_produces_the_digest_the_release_doc_promises():
    """The release build computes the shipped image's digest and writes it beside the image."""
    script = BUILD_APP.read_text(encoding="utf-8")
    commands = [
        line.strip()
        for line in script.splitlines()
        if DIGEST_COMMAND.search(line) and not line.lstrip().startswith("#")
    ]
    assert commands, (
        "scripts/build_app.sh computes no digest: docs/release/gatekeeper.md tells the user a "
        "sha256 is published next to the disk image and that it is how the download is checked."
    )
    assert ".sha256" in script, (
        "no step names a .sha256 file, so nothing is written beside the image for the user to "
        "compare against the value the release notes list"
    )
    assert 'DMG="$DIST/OhYesMLX-$VERSION.dmg"' in script, (
        "the digest must be of the shipped disk image (plan 05-14, AC-1)"
    )
    assert '"$DMG.sha256"' in script, "the digest file does not follow the disk image's name"
    assert "shasum -a 256 \"$DMG\"" in script, "the digest is not taken from the disk image"


def test_the_build_writes_a_dmg_and_no_zip():
    """AC-1: the shipped file is a read-only UDZO image with an /Applications symlink."""
    script = BUILD_APP.read_text(encoding="utf-8")
    live = "\n".join(
        line for line in script.splitlines() if not line.lstrip().startswith("#")
    )
    assert ".zip" not in live, "build_app.sh still writes a zip"
    assert (
        "hdiutil create -quiet -volname OhYesMLX -srcfolder \"$STAGE\" -format UDZO" in script
    ), "the disk image is not made by hdiutil from the staging directory as UDZO"
    assert 'ln -s /Applications "$STAGE/Applications"' in script, (
        "the image carries no /Applications symlink, so there is nothing to drag onto"
    )
    assert 'ditto "$APP" "$STAGE/OhYesMLX.app"' in script, "the app is not staged into the image"
    assert ".sha256" in script, (
        "no step names a .sha256 file, so nothing is written beside the zip for the user to "
        "compare against the value gatekeeper.md:52 says the release notes list"
    )


def _codesign(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["codesign", *arguments], capture_output=True, text=True)


@pytest.mark.skipif(shutil.which("codesign") is None, reason="the probe needs macOS codesign")
def test_an_adhoc_signature_can_be_replaced_by_anyone_and_names_no_one(tmp_path):
    """Evidence for gatekeeper.md:30-31: a re-signed alteration still verifies, with no identity."""
    app = tmp_path / "Probe.app"
    macos = app / "Contents" / "MacOS"
    macos.mkdir(parents=True)
    shutil.copyfile("/bin/echo", macos / "Probe")
    (app / "Contents" / "Info.plist").write_text(INFO_PLIST, encoding="utf-8")

    signed = _codesign("--force", "--sign", "-", str(app))
    assert signed.returncode == 0, signed.stderr
    assert _codesign("--verify", "--strict", str(app)).returncode == 0

    shutil.copyfile("/usr/bin/true", macos / "Probe")
    assert _codesign("--verify", "--strict", str(app)).returncode != 0, (
        "the ad-hoc seal should notice a replaced executable until the signature is replaced"
    )

    resigned = _codesign("--force", "--sign", "-", str(app))
    assert resigned.returncode == 0, resigned.stderr
    assert _codesign("--verify", "--strict", str(app)).returncode == 0, (
        "any third party can modify a bundle, re-sign it with codesign --force --sign -, "
        "and it verifies again: the signature is not tamper evidence a downloader can use"
    )

    details = _codesign("-dvv", str(app)).stderr
    assert "Signature=adhoc" in details, details
    assert "TeamIdentifier=not set" in details, details
    assert "Authority=" not in details, details
