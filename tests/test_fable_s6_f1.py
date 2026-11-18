"""Fable 5.2 S6-F1: the build ships timestamp bytecode for the stdlib it imported.

``scripts/build_app.sh:33-34`` reads ``ohyesmlx.__version__`` with the *cache*
interpreter and no ``-B``.  ``ohyesmlx/__init__.py`` imports ``json``,
``tempfile`` and ``pathlib``, so that read writes default (timestamp) pycs into
the cached python tree; ``:55`` copies the tree with ``ditto``, which preserves
mtimes.  ``:76-77`` then runs ``compileall`` **without** ``-f``, and
``compileall`` skips any source whose existing pyc header is "magic + flags 0 +
source mtime" -- so those modules keep timestamp pycs in the sealed bundle.

A timestamp pyc is revalidated against its source mtime on every import
(``importlib._bootstrap_external._validate_timestamp_pyc``), so any transfer
that does not reproduce mtimes to the second makes it stale, and the first
child interpreter that is not ``-B`` -- ``{python} -I -m venv`` for every
engine (``ohyesmlx/engines.py:797``) -- rewrites it inside the signed bundle.

Measured on this Mac's ``dist/OhYesMLX.app`` (2026-11-16): 1079 pycs, 1028
hash-based, 51 timestamp-based; all 51 are exactly the pycs the cached tree
carries, and ``json``'s four are the pre-existing ones while ``tool`` and
``__main__`` (which nobody imported) are ``compileall``'s.  One child
``python3 -I -m venv`` against a copy whose source mtimes had moved rewrote all
51 and ``codesign --verify --deep --strict`` then exited 1 with "a sealed
resource is missing or invalid"; with mtimes intact, the same venv changed
nothing.

The two commands below are read out of ``build_app.sh`` itself, so a change to
the build changes what is exercised here.  Nothing is built, started or
downloaded: the tree is a scratch directory and the interpreter is the one
running pytest.
"""

from __future__ import annotations

import shlex
import shutil
import struct
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BUILD = REPO / "scripts" / "build_app.sh"
BUNDLE = REPO / "dist" / "OhYesMLX.app"


def _logical_lines(text):
    """The script's lines with backslash continuations joined."""
    joined, pending = [], ""
    for line in text.splitlines():
        if line.rstrip().endswith("\\"):
            pending += line.rstrip()[:-1] + " "
            continue
        joined.append(pending + line)
        pending = ""
    if pending:
        joined.append(pending)
    return joined


def _version_read_command():
    """The logical line that assigns VERSION, tokenised."""
    for line in _logical_lines(BUILD.read_text()):
        if line.lstrip().startswith("VERSION=$("):
            return shlex.split(line.strip()[len("VERSION=$(") :].rsplit(")", 1)[0])
    raise AssertionError("build_app.sh has no VERSION=$(...) assignment")


def _compileall_invocation():
    """(interpreter arguments, target) of the script's one compileall call.

    The tokens come from the script itself: the interpreter token is dropped so
    the caller can supply its own, and the remaining argv (``-I -B -m
    compileall`` and the flags) is returned verbatim.
    """
    for line in _logical_lines(BUILD.read_text()):
        stripped = line.strip()
        if "-m compileall" not in stripped:
            continue
        tokens = shlex.split(stripped)
        # Stop at the shell's own operators: only the command's argv matters.
        argv = []
        for token in tokens:
            if token in ("||", "&&") or token.startswith(">") or token.startswith("|"):
                break
            argv.append(token)
        return argv[1:-1], argv[-1]
    raise AssertionError("build_app.sh runs no compileall")


def _flags_word(pyc):
    with open(pyc, "rb") as handle:
        magic, flags = struct.unpack("<4sI", handle.read(8))
    assert magic, pyc
    return flags


def _write_timestamp_pyc(source, interpreter):
    """A pyc in the shape the build's own version read leaves behind."""
    import subprocess

    code = (
        "import py_compile, sys;"
        "py_compile.compile(sys.argv[1], doraise=True,"
        " invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP);"
        "import importlib.util as u; print(u.cache_from_source(sys.argv[1]))"
    )
    completed = subprocess.run(
        [interpreter, "-I", "-c", code, str(source)], check=True, capture_output=True, text=True
    )
    target = Path(completed.stdout.strip())
    assert target.exists(), f"py_compile wrote no pyc beside {source}"
    return target


def test_the_builds_version_read_cannot_write_bytecode():
    """``build_app.sh:33-34`` runs the cache interpreter, so it must pass ``-B``.

    Without it the tree that ``:55`` copies into the sealed bundle is already
    carrying the interpreter's pycs, before ``compileall`` gets a chance to
    replace them.
    """
    argv = _version_read_command()
    assert "-B" in argv or "--dont-write-bytecode" in argv, (
        "the VERSION read imports ohyesmlx (json, tempfile, pathlib) with no -B, so it "
        f"writes timestamp pycs into the cache tree that :55 copies: {argv}"
    )


def test_the_builds_compileall_replaces_the_bytecode_it_copies(tmp_path):
    """``compileall`` without ``-f`` keeps a pyc that matches its source's mtime.

    The tree here is the state ``build_app.sh:55`` hands to ``:76``: a source
    plus the timestamp pyc an interpreter already wrote for it.  The flags and
    target are the script's own, with the scratch directory substituted for
    ``$CONTENTS/Resources/python/lib``.
    """
    flags, target = _compileall_invocation()
    lib = tmp_path / "lib"
    package = lib / "pkg"
    package.mkdir(parents=True)
    source = package / "__init__.py"
    source.write_text('"""Stand-in for a stdlib module the build itself imported."""\nVALUE = 1\n')

    seeded = _write_timestamp_pyc(source, __import__("sys").executable)
    assert _flags_word(seeded) == 0, "the seed pyc is not timestamp-based"

    import subprocess

    completed = subprocess.run(
        [__import__("sys").executable, *flags, str(lib)],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert target.endswith("lib"), f"unexpected compileall target in build_app.sh: {target}"

    timestamp = [p for p in lib.rglob("*.pyc") if _flags_word(p) == 0]
    assert not timestamp, (
        "compileall left timestamp bytecode in the tree the build seals: "
        f"{[p.name for p in timestamp]}. It moves its validity check into the source mtime, "
        "so a transfer that does not reproduce mtimes makes every one of them stale and the "
        "first non--B child interpreter (engines.py:797's `-I -m venv`) rewrites it inside "
        "the signed bundle."
    )


def test_the_shipped_bundle_carries_no_timestamp_bytecode():
    """The artifact check the finding asks for: every pyc's flag word is non-zero.

    Skipped where nothing has been built (``dist/`` is gitignored).
    """
    python = BUNDLE / "Contents" / "Resources" / "python"
    if not python.is_dir():
        pytest.skip(f"no built bundle at {BUNDLE}")

    pycs = list(python.rglob("*.pyc"))
    assert pycs, f"{python} has no bytecode at all"
    timestamp = sorted(p.relative_to(python) for p in pycs if _flags_word(p) == 0)
    assert not timestamp, (
        f"{len(timestamp)} of {len(pycs)} bundled pycs are timestamp-based, e.g. "
        f"{[str(p) for p in timestamp[:5]]}"
    )


def _sealed_walk():
    """The build's own bytecode walk, read out of the script."""
    import re

    match = re.search(r"<<'PY' \|\| fail .*?\n(.*?)\nPY\n", BUILD.read_text(), re.S)
    assert match is not None, "build_app.sh has no sealed-tree walk after compileall"
    return match.group(1)


def _run_walk(root):
    import subprocess

    code = _sealed_walk()
    return subprocess.run(
        [__import__("sys").executable, "-I", "-B", "-", str(root)],
        input=code,
        capture_output=True,
        text=True,
    )


def _compile(source, interpreter):
    import subprocess

    subprocess.run(
        [
            interpreter,
            "-I",
            "-B",
            "-c",
            "import py_compile, sys; py_compile.compile(sys.argv[1], doraise=True, "
            "invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)",
            str(source),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def test_the_builds_walk_fails_on_timestamp_bytecode_and_on_a_missing_pyc(tmp_path):
    """The replacement for `[ -n "$(find ... -name '*.pyc')" ]`, exercised on fixtures."""
    import sys

    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "module.py").write_text("VALUE = 1\n")
    _compile(clean / "module.py", sys.executable)
    completed = _run_walk(clean)
    assert completed.returncode == 0, completed.stderr

    timestamp = tmp_path / "timestamp"
    timestamp.mkdir()
    (timestamp / "module.py").write_text("VALUE = 1\n")
    seeded = _write_timestamp_pyc(timestamp / "module.py", sys.executable)
    assert _flags_word(seeded) == 0
    completed = _run_walk(timestamp)
    assert completed.returncode != 0, "a timestamp pyc passed the build's walk"
    assert "not unchecked-hash" in completed.stderr

    missing = tmp_path / "missing"
    missing.mkdir()
    (missing / "module.py").write_text("VALUE = 1\n")
    completed = _run_walk(missing)
    assert completed.returncode != 0, "a source with no pyc passed the build's walk"
    assert "no pyc" in completed.stderr
