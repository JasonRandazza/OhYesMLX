"""S6-F10: "remove everything the app has added" leaves two things behind.

The finding: the engine install argv carries no `--no-cache-dir`, so each install fills
`~/Library/Caches/pip` with the wheels of a closure hundreds of MB deep, and the app's
`UserDefaults` writes `~/Library/Preferences/io.github.jasonrandazza.ohyesmlx.plist` while
gatekeeper.md's table and removal steps name neither.

The tests below assert the repair instead of the defect they used to pin: the one pip argv
carries the flag, and the doc's table and steps carry both places.
"""

import re
from pathlib import Path

from ohyesmlx.engines import install_plan

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs/release/gatekeeper.md"


def _pip_argv(name):
    plan = install_plan(name, 15)
    pip_steps = [step for step in plan.steps if "pip" in step.command]
    assert len(pip_steps) == 1, plan.steps
    return pip_steps[0].command


def _section():
    doc = DOC.read_text()
    return doc[doc.index("## What the app writes"):doc.index("## Notarization")]


def test_every_pip_argv_carries_no_cache_dir():
    for name in ("mlxlm", "optiq"):
        assert "--no-cache-dir" in _pip_argv(name), name


def test_the_doc_lists_the_pip_cache_and_the_preferences_plist_and_how_to_remove_them():
    section = _section()

    assert "Library/Caches/pip" in section, "pip's default cache is not in the table or steps"
    assert "Preferences" in section, "the app's UserDefaults plist is not in the table"
    assert "io.github.jasonrandazza.ohyesmlx.plist" in section
    # Both are named twice: once in the table, once in the numbered steps that remove them.
    assert section.count("Library/Caches/pip") >= 2
    assert section.count("Preferences") >= 2


def test_the_doc_no_longer_claims_three_places():
    """The sentence the finding quotes is false once pip's cache and the plist are listed."""
    assert "keeps three places on disk" not in _section()


def test_the_pip_cache_flag_is_in_the_one_argv_that_installs_an_engine():
    """``--isolated`` and ``--no-cache-dir`` are different flags with different jobs; both stay."""
    for name in ("mlxlm", "optiq"):
        argv = _pip_argv(name)
        assert "--isolated" in argv
        assert "--no-cache-dir" in argv
        assert not any(token.startswith("--cache-dir") for token in argv), (
            "an explicit cache directory would still leave the wheels on disk"
        )
        assert re.fullmatch(r"--no-cache-dir", argv[argv.index("--no-cache-dir")])
