"""Fable 5.2 S5-F14: the Osaurus app is recognised only under ``/Applications``.

``OSAURUS_APP_BUNDLES`` (``runtimes.py:149``) names two absolute paths, both under
``/Applications``. ``_resident_osaurus_pids`` (:634-648) matches a ``ps`` argument vector
against the executables derived from that tuple, and ``ENGINE_BUNDLE_EXECUTABLES`` (:163-172)
derives the CLI fallback from it too -- as does ``engines._detect_osaurus`` (:499-505), which
imports the same tuple. An app installed to ``~/Applications`` (Homebrew ``--appdir``, or a
user without admin rights) is therefore invisible to all three.

Only ``_run`` is faked here: the ``ps`` output is the one under test, nothing is spawned, and
no process is signalled.
"""

from __future__ import annotations

import subprocess

from ohyesmlx import runtimes

HOME_APP = "~/Applications/osaurus.app/Contents/MacOS/osaurus"


def ps_output(argv):
    """``_run``'s answer for ``ps -axo pid=,args=`` with one process at *argv*."""
    return subprocess.CompletedProcess(
        args=["ps"], returncode=0, stdout=f"7311 {argv}\n", stderr=""
    )


def test_resident_osaurus_pids_sees_a_home_directory_install(monkeypatch):
    """An app in ``~/Applications`` is resident and must be found before a cell starts."""
    import os

    monkeypatch.setattr(runtimes, "_run", lambda command, timeout_s: ps_output(os.path.expanduser(HOME_APP)))
    monkeypatch.setattr(runtimes, "_process_alive", lambda pid: True)

    assert runtimes._resident_osaurus_pids() == (7311,), (
        "the resident Osaurus app at "
        f"{os.path.expanduser(HOME_APP)} was not recognised; it stays resident through "
        "every later cell"
    )


def test_the_osaurus_cli_fallback_covers_a_home_directory_install(monkeypatch):
    """``ENGINE_BUNDLE_EXECUTABLES`` is derived from the same tuple, so it misses it too.

    Under launchd's PATH ``osaurus`` does not resolve and ``_resolve_program`` falls back to
    the bundle's ``Contents/Helpers`` tool; an emptied table means the start dies ENOENT.
    """
    import os

    candidates = runtimes.ENGINE_BUNDLE_EXECUTABLES["osaurus"]
    assert os.path.expanduser(
        "~/Applications/osaurus.app/Contents/Helpers/osaurus"
    ) in candidates, f"the CLI fallback table holds only {candidates}"
