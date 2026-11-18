"""Fable 5.2 S6-F2: the unpacked interpreter tree is reused without verification.

``scripts/fetch_python_standalone.sh:48-68`` re-verifies the cached *tarball*
against the pinned sha256 on every run -- and then ``:70`` hands back
``${UNPACKED}/python`` whenever ``bin/python3`` there is executable, with no
check that the tree is still that tarball's.  The tree lives under
``~/Library/Caches/OhYesMLX/build/``, is user-writable, and *is* mutated by
ordinary use.

``scripts/build_app.sh:55`` then ``ditto``s exactly that tree into
``Contents/Resources/python``, ad-hoc signs it and zips it, and
``scripts/make_sbom.py:137-144`` records its identity as the *tarball's* url
and sha256 (``build_app.sh:113-116`` passes the ``--identity`` pin straight
through).  So the SBOM's ``interpreter.sha256`` describes a tree the bundle may
no longer contain.

The first test is the finding's own test idea, made runnable without a build:
the script is the only thing that decides what ``$PYTHON_ROOT`` is, so plant a
marker in its cached tree and assert the root it prints does not carry it.  The
assertion is on the marker, not on the path, so either fix direction -- a fresh
unpack per run, or a cached tree re-derived from the tarball -- makes it pass.

Nothing is downloaded, built, started or signed here: ``--identity`` runs
before any cache path is touched, the fake cache is a scratch directory seeded
from a tarball this Mac already has (its digest is asserted against the pin
first, so the script can never reach for the network), and every check that
needs the tarball skips when it is absent.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "fetch_python_standalone.sh"
BUILD = REPO / "scripts" / "build_app.sh"

MARKER = "PLANTED-BY-FABLE-S6-F2.pth"


def _identity():
    """The script's own pinned facts, as a dict (its ``--identity`` mode)."""
    completed = subprocess.run(
        ["/bin/sh", str(SCRIPT), "--identity"], capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr
    facts = {}
    for line in completed.stdout.splitlines():
        key, _, value = line.partition("=")
        facts[key] = value
    assert {"tarball", "sha256", "url"} <= set(facts), completed.stdout
    return facts


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verified_tarball(facts):
    """The real tarball the pin names, from this Mac's build cache.

    Skipped where it has never been fetched, or where the copy here is not the
    pinned bytes: either way the script would go to the network, which a test
    must not do.
    """
    path = Path.home() / "Library" / "Caches" / "OhYesMLX" / "build" / facts["tarball"]
    if not path.is_file():
        pytest.skip(f"no cached {facts['tarball']} to seed the fake cache; nothing is fetched here")
    if _digest(path) != facts["sha256"]:
        pytest.skip(f"the cached {facts['tarball']} is not the pinned bytes; nothing is fetched here")
    return path


def _stub_tree(cache, facts):
    """A cached "unpacked" tree that satisfies ``:70`` but is not the tarball's."""
    unpacked = cache / facts["tarball"].removesuffix("-install_only.tar.gz")
    python = unpacked / "python"
    (python / "bin").mkdir(parents=True)
    stub = python / "bin" / "python3"
    stub.write_text("#!/bin/sh\nexit 1\n")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # The shape a `pip install` leaves behind, one of the three mutations the
    # finding names (the other two are an edited stdlib file, a planted .pth).
    site_packages = python / "lib" / "python3.14" / "site-packages"
    site_packages.mkdir(parents=True)
    planted = site_packages / MARKER
    planted.write_text("import anything_you_like\n")
    return python, planted


def test_the_tree_the_build_copies_is_the_tarball_and_nothing_else(tmp_path):
    """Whatever the script prints is what ``build_app.sh:55`` dittos into the bundle.

    ``bin/python3`` being executable is the script's only evidence that the
    cached tree is the verified tarball's; a file planted beside it therefore
    reaches the ad-hoc-signed bundle while the SBOM still names the tarball's
    sha256.
    """
    if os.uname().machine != "arm64":
        pytest.skip("fetch_python_standalone.sh exits 1 off arm64")

    facts = _identity()
    tarball = _verified_tarball(facts)

    fake_home = tmp_path / "home"
    cache = fake_home / "Library" / "Caches" / "OhYesMLX" / "build"
    cache.mkdir(parents=True)
    shutil.copyfile(tarball, cache / facts["tarball"])
    _, planted = _stub_tree(cache, facts)

    completed = subprocess.run(
        ["/bin/sh", str(SCRIPT)],
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(fake_home)},
    )
    assert completed.returncode == 0, completed.stderr
    root = Path(completed.stdout.strip())
    assert (root / "bin" / "python3").exists(), f"the script printed no python root: {root}"

    carried = root / "lib" / "python3.14" / "site-packages" / MARKER
    assert not carried.exists(), (
        f"{carried} was handed to the build. The script re-verifies the cached tarball on "
        "every run (:48-68) but reuses \"${UNPACKED}/python\" on the strength of `-x "
        "bin/python3` alone (:70), so a pip install, an edited stdlib file or a planted "
        ".pth is copied by build_app.sh:55, signed and zipped while the SBOM still records "
        "the tarball's sha256 (make_sbom.py:137-144)."
    )


def test_the_sbom_names_the_tarball_not_the_tree_that_ships():
    """``interpreter.sha256`` is the archive pin passed through untouched.

    ``build_app.sh`` takes the value from ``--identity`` and hands it to
    ``make_sbom.py --interpreter-sha256``, and no digest of the copied tree is
    taken anywhere -- so the SBOM cannot distinguish the tarball's tree from a
    mutated one.
    """
    build = BUILD.read_text()
    assert (
        'INTERPRETER_SHA256=$(printf \'%s\\n\' "$IDENTITY" | sed -n \'s/^sha256=//p\')'
        in build
    ), "INTERPRETER_SHA256 no longer comes from --identity; re-read build_app.sh:24-29"
    assert '--interpreter-sha256 "$INTERPRETER_SHA256"' in build
    assert 'ditto "$PYTHON_ROOT" "$CONTENTS/Resources/python"' in build, (
        "build_app.sh:55 no longer copies $PYTHON_ROOT; the finding's copy step moved"
    )
    for line in build.splitlines():
        if "PYTHON_ROOT=" in line:
            assert "fetch_python_standalone.sh" in line, line
            break
    else:
        raise AssertionError("build_app.sh no longer sets PYTHON_ROOT; re-read :24-25")
