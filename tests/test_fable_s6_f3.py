"""S6-F3: check_bundle's P5-6 signature check could not fail for the defect it was written for.

The regression P5-6 guards is "a child interpreter writes bytecode into the signed bundle". The
check ran the app from a `UDRO` image -- where a write cannot land, and Python ignores a failed
pyc write -- and then verified the signature of that immutable copy: a comparison of the image
with itself. It never made a child interpreter run either. P5-6 therefore passed for a build with
timestamp bytecode in it, and would pass for one with no precompile at all.

The missing half is a writable copy, with its mtimes moved, in which the bundled interpreter makes
a venv and imports the stdlib the app's children import -- without `-B`, as the app's children
run -- after which nothing may have been rewritten and the signature must still verify.

This is a static test of the script: the writable half needs a built bundle, which the coordinator
runs. It reads the block out of `check_bundle.sh` rather than restating it, so a change to the
script changes what is exercised here.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_bundle.sh"
TEXT = SCRIPT.read_text()

START = "==> P5-6: a writable copy"
END = "==> P5-6 and P5-9: the app on a read-only disk image"


def _writable_block() -> str:
    assert START in TEXT, "check_bundle.sh no longer has a writable-copy P5-6 half"
    return TEXT[TEXT.index(START) : TEXT.index(END)]


def _lines(block: str) -> list[str]:
    return [
        line.strip()
        for line in block.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_the_writable_copy_runs_before_the_no_gui_branch():
    """`--no-gui` may skip the launch; it must not skip the half that can fail."""
    assert TEXT.index(START) < TEXT.index('if [ "$MODE" = "--no-gui" ]')


def test_the_copy_is_writable_and_its_mtimes_are_moved():
    lines = _lines(_writable_block())
    assert 'cp -R "$APP" "$WRITABLE/OhYesMLX.app"' in lines, (
        "the bundle is not copied to a writable place; a UDRO image cannot receive the write "
        "this check exists to catch"
    )
    assert not any(line.startswith("ditto ") for line in lines), (
        "ditto preserves mtimes, which is the opposite of what makes a timestamp pyc stale"
    )
    assert any('find "$COPY" -type f -exec touch' in line for line in lines), (
        "the copy's mtimes are not moved, so a timestamp pyc can still match its source and the "
        "check proves nothing"
    )


def test_a_child_interpreter_runs_from_the_copy_without_dash_b():
    lines = _lines(_writable_block())
    venv = [line for line in lines if "-m venv" in line]
    assert venv, "the copy's interpreter never makes a venv, so no child writes at all"
    for line in venv:
        assert "-I" in line, f"the venv run is not isolated: {line}"
        assert "-B" not in line, (
            f"the venv run passes -B, so it cannot show whether a child rewrites bytecode: {line}"
        )

    imports = [line for line in lines if "-c 'import email, json, tempfile, ssl'" in line]
    assert imports, "the copy's interpreter never imports the stdlib the app's children import"
    for line in imports:
        assert "-I" in line
        assert "-B" not in line, f"the import run passes -B: {line}"


def test_a_rewrite_and_a_broken_signature_both_fail_the_check():
    block = _writable_block()
    assert 'find "$COPY" -newer "$REFERENCE"' in block, (
        "nothing compares the tree with the time the child ran, so a rewritten file goes unseen"
    )
    assert 'fail P5-6 "a child interpreter rewrote files inside the bundle' in block
    assert 'codesign --verify --deep --strict "$COPY"' in block, (
        "the signature of the writable copy is never verified, so the seal is untested"
    )


def test_the_read_only_half_is_still_there():
    assert "hdiutil create" in TEXT and '-format UDRO' in TEXT
    assert "mount | grep -F \" on $MOUNT \" | grep -q 'read-only'" in TEXT
