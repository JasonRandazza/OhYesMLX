"""Fable 5.2 S5-F4: an orphan whose identity cannot be verified is dropped and its ledger
deleted, so the engine is unrecoverable.

``_stop_orphan`` returns early in three cases (unreadable port, alive-but-unmatched launcher,
unmatched listener/pid identity). No exception is raised, so ``stop_orphaned_engines`` treats
the entry as handled and unlinks ``<owner>.json``. After that no later launch looks at the
engine again: it keeps the port and its weights until the machine reboots.

Nothing is signalled and no process is touched here: ``_process_alive`` and
``_process_identity`` are the module's own seams and both are faked, as in the existing ledger
tests. The pids named below are numbers, not processes.
"""

from __future__ import annotations

import json
import os

import pytest

from ohyesmlx import runtimes

DEAD_OWNER = 999_999
ENGINE_PID = 4242
PORT = 8081
LSTART = "Wed Nov 5 10:00:00 2025"
ARGV = "python -m mlx_lm.server --model /models/x --port 8081"


def _write_ledger(root, owner, entries):
    """One owner's ledger file, in the shape ``_write_ledger`` produces."""
    directory = root / "results" / runtimes.RUNNING_ENGINES_DIRNAME
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{owner}.json"
    path.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return path


def _entry(**overrides):
    entry = {
        "pid": ENGINE_PID,
        "lstart": LSTART,
        "argv": ARGV,
        "serving_pid": ENGINE_PID,
        "serving_lstart": LSTART,
        "serving_argv": ARGV,
        "port": PORT,
        "stop_command": [],
    }
    entry.update(overrides)
    return entry


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """A dead owner's ledger for one alive engine, with the stop seams recorded."""
    state = {"shutdowns": []}
    monkeypatch.setattr(
        runtimes, "_process_alive", lambda pid: pid not in (DEAD_OWNER, os.getpid())
    )
    monkeypatch.setattr(runtimes, "_process_identity", lambda pid: (LSTART, ARGV))

    def shutdown(pid, port, stop_command=()):
        state["shutdowns"].append((pid, port, stop_command))

    monkeypatch.setattr(runtimes, "_shutdown", shutdown)
    return state


def test_an_orphan_whose_port_cannot_be_read_keeps_its_ledger_file(
    ledger, tmp_path, monkeypatch
):
    """`lsof` failed once (timeout, or a refused environment): the engine is alive and its
    identity matches, so the entry still proves something -- but the file is deleted.

    Nothing is asserted about stderr: the finding's own fix direction emits a line here, so a
    test that required silence would fail the fix. The drop is silent today (measured
    separately, 0 bytes), and that is recorded in the report, not pinned here.
    """
    path = _write_ledger(tmp_path, DEAD_OWNER, [_entry()])
    monkeypatch.setattr(runtimes, "_listener_pids", lambda port: None)

    runtimes.stop_orphaned_engines(tmp_path)

    assert ledger["shutdowns"] == [], "an entry whose port could not be read was signalled"
    assert path.exists(), (
        "the ledger of an orphan whose port could not be read was deleted; the engine "
        f"({ENGINE_PID}) is alive on {PORT} and nothing records it any more"
    )


def test_an_orphan_whose_recorded_identity_no_longer_matches_keeps_its_ledger_file(
    ledger, tmp_path, monkeypatch
):
    """The recorded `lstart` is rendered by `ps` in the caller's locale and local time, so the
    same process can render differently after a DST change or under a different TZ. The
    engine is still alive; the only claim on it is deleted."""
    path = _write_ledger(
        tmp_path, DEAD_OWNER, [_entry(lstart="Wed Nov 5 09:00:00 2025",
                                      serving_lstart="Wed Nov 5 09:00:00 2025")]
    )
    monkeypatch.setattr(runtimes, "_listener_pids", lambda port: ())
    monkeypatch.setattr(runtimes, "_process_identity", lambda pid: (LSTART, ARGV))

    runtimes.stop_orphaned_engines(tmp_path)

    assert ledger["shutdowns"] == [], "an identity mismatch was signalled"
    assert path.exists(), (
        "the ledger of a live engine whose identity could not be proved was deleted; "
        "nothing records the engine any more"
    )


def test_a_stranger_on_the_port_is_dropped_and_that_is_the_recorded_behaviour(
    ledger, tmp_path, monkeypatch
):
    """Control: the drop-and-delete is intended when the entry proves nothing about the
    process in front of it. This one passes today and is here so the two above cannot be
    read as "no entry should ever be dropped"."""
    path = _write_ledger(tmp_path, DEAD_OWNER, [_entry()])
    monkeypatch.setattr(runtimes, "_listener_pids", lambda port: (5252,))
    monkeypatch.setattr(runtimes, "_process_identity", lambda pid: (LSTART, ARGV))

    runtimes.stop_orphaned_engines(tmp_path)

    assert ledger["shutdowns"] == []
    assert not path.exists()
