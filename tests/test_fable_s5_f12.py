"""Fable 5.2 S5-F12: ``osaurus_set_seqs`` rewrites the live host config in place and accepts 0.

The function (``scripts/osaurus-pin.sh:46-67``) validates with ``''|*[!0-9]*`` only, so ``0``
passes a check whose own message says "expected a positive integer"; it then rewrites
``server-runtime.json`` with ``json.dump(runtime, open(conf, 'w'), indent=2)`` -- truncate,
then write, on the user's own file -- before anything validates the value, and it bypasses
``osaurus_settings._write_atomic`` (:178-200), which ``pin`` uses for the same file (:282-283).

Both halves are measured here, nothing is stubbed inside the script:

* ``$HOME`` is a scratch directory, so ``CONFIG_DIR``/``BACKUP_DIR`` and, in the subprocess,
  ``Path.home()`` all point at scratch files;
* the subprocess runs from a scratch directory holding a two-file copy of the package
  (``__init__.py`` and ``osaurus_settings.py``) and no ``.git``, which is the installed-app
  shape ``writable_root`` describes: the baseline lands under ``$HOME``, not in this repo;
* the config is hard-linked, so an in-place truncate destroys the link's bytes too while a
  temp-and-replace leaves them alone.

No server, no model, no process is started: ``osaurus_set_seqs`` only reads and writes JSON.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "osaurus-pin.sh"
PYTHON = "/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python"

ORIGINAL = {
    "cache": {"prefix": {"enabled": True}, "blockDisk": {"enabled": True}},
    "concurrency": {"maxConcurrentSequences": 4, "continuousBatching": True},
    "generation": {"streamInterval": 1},
}


@pytest.fixture
def host(tmp_path):
    """A scratch ``$HOME`` with a pinned Osaurus config, plus the installed-shape package."""
    home = tmp_path / "home"
    config = home / ".osaurus" / "config"
    config.mkdir(parents=True)
    original_bytes = (json.dumps(ORIGINAL, indent=2) + "\n").encode()
    (config / "server-runtime.json").write_bytes(original_bytes)
    # pin's own first act, which osaurus_set_seqs refuses without.
    backup = home / ".osaurus" / "config.phase4-orig"
    backup.mkdir(parents=True)
    (backup / "server-runtime.json").write_bytes(original_bytes)
    (config / "server.json").write_text("{}\n", encoding="utf-8")
    (backup / "server.json").write_text("{}\n", encoding="utf-8")

    package = tmp_path / "installed" / "ohyesmlx"
    package.mkdir(parents=True)
    shutil.copy(REPO / "ohyesmlx" / "__init__.py", package / "__init__.py")
    shutil.copy(REPO / "ohyesmlx" / "osaurus_settings.py", package / "osaurus_settings.py")

    # A second name for the same inode: an in-place rewrite edits this too.
    os.link(config / "server-runtime.json", tmp_path / "linked-copy")
    return tmp_path


def set_seqs(host, value):
    """Source the shipped script and run ``osaurus_set_seqs <value>`` as a caller does."""
    env = dict(os.environ)
    env["HOME"] = str(host / "home")
    env["PY"] = PYTHON
    return subprocess.run(
        ["bash", "-c", f'source "{SCRIPT}"; osaurus_set_seqs {value}'],
        cwd=host / "installed",
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_zero_is_refused_like_the_message_says(host):
    """``0`` is not a positive integer, and a batch cap of 0 is a host that will not serve."""
    result = set_seqs(host, 0)

    assert result.returncode != 0, (
        "osaurus_set_seqs 0 succeeded and re-recorded the baseline with a batch cap of 0: "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_a_valid_value_is_written_atomically(host):
    """Independent of the ``0`` bug: the edit itself must be temp-and-replace.

    ``osaurus_settings._write_atomic`` (:178-200) is what ``pin`` uses on the same file. A
    hard link to the config keeps the old inode: an in-place truncate empties it, a replace
    leaves its bytes as they were.
    """
    result = set_seqs(host, 8)
    assert result.returncode == 0, f"a valid value was refused: {result.stderr!r}"

    assert (host / "linked-copy").read_bytes() == (json.dumps(ORIGINAL, indent=2) + "\n").encode(), (
        "the live config was truncated and rewritten in place (the hard link followed the "
        "same inode); a kill between truncate and write leaves server-runtime.json empty"
    )


def test_a_rejected_value_never_touches_the_live_config(host):
    """The write must not happen before the value is validated.

    Today ``0`` is written to the live file first and read back afterwards, so a value the
    function's own message calls invalid has already replaced the user's concurrency cap --
    and a kill inside that truncate window leaves no config at all.
    """
    config = host / "home" / ".osaurus" / "config" / "server-runtime.json"
    before = config.read_bytes()

    set_seqs(host, 0)

    after = config.read_bytes()
    assert after == before, (
        "the live server-runtime.json was rewritten for a value that was then refused: "
        f"it now holds {json.loads(after).get('concurrency')!r}"
    )
    assert (host / "linked-copy").read_bytes() == before, (
        "the config was truncated in place (the hard link kept the old inode and lost its "
        "bytes), not replaced: a kill between truncate and write leaves it empty"
    )
