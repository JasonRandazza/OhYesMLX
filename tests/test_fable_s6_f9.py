"""S6-F9: no gate runs the path every downloader takes — a quarantined zip.

The claim is an absence, so the check is an inventory of the three gates in
scope: nothing in `scripts/` sets or reads `com.apple.quarantine`; check_bundle
builds its disk image from the locally built `$APP` (never a zip it unpacked);
the clean-account smoke builds and installs a wheel; and the translocation
guard's only test injects a path string rather than launching a translocated
copy.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def _scripts_text():
    return {p.name: p.read_text() for p in sorted(SCRIPTS.iterdir()) if p.is_file()}


def test_no_gate_loads_a_quarantined_zip_the_way_a_downloader_does():
    texts = _scripts_text()

    touched = sorted(
        name for name, text in texts.items() if "xattr" in text or "quarantine" in text
    )
    assert touched == [], f"a gate now touches quarantine: {touched}"

    check = texts["check_bundle.sh"]
    assert "hdiutil create" in check and '-srcfolder "$APP"' in check
    assert 'open "$MOUNT/OhYesMLX.app"' in check
    assert ".zip" not in check, "check_bundle now unpacks something"

    smoke = texts["smoke_clean_account.sh"]
    assert "uv build --wheel" in smoke
    assert "*.whl" in smoke
    assert ".zip" not in smoke, "the clean-account smoke now uses the release zip"
    assert "unzip" not in smoke

    swift = (ROOT / "app/Tests/OhYesMLXKitTests/AppModelTests.swift").read_text()
    assert "/AppTranslocation/8F2C-9A1B/d/OhYesMLX.app" in swift
    assert "xattr" not in swift
