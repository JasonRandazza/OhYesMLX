"""Fable 5.2 S1-F1: a stale own-pid ledger file is signalled with no identity check.

"Stop now" (``stop_own_engines``) reads ``<own pid>.json`` and hands every entry straight to
``_shutdown``. The orphan path gates on the recorded ``(lstart, argv)`` identity; this path
does not. So a ledger file a *previous* process wrote under the pid this process now holds --
possible after a reboot, since macOS restarts pid allocation and a launchd-started backend can
land on a low pid a killed predecessor used -- is treated as this process's own engine.

These checks write the file a killed predecessor would leave, patch ``_shutdown`` so nothing
is signalled, and call the stopper. No process is started, signalled or killed.
"""

from __future__ import annotations

import json
import os

from ohyesmlx import runtimes

STALE_PORT = 59999
STALE_STOP = ("osaurus", "stop")


def _write_own_ledger(root, entries):
    """``<root>/results/running-engines/<this pid>.json``, the shape ``_write_ledger`` writes."""
    directory = root / "results" / runtimes.RUNNING_ENGINES_DIRNAME
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{os.getpid()}.json"
    path.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return path


def _stale_entry(live_stranger_pid):
    """An entry a dead predecessor recorded: a live pid that is not ours, and not that process."""
    return {
        "pid": live_stranger_pid,
        "lstart": "Mon Jan  1 00:00:00 2024",
        "argv": "not the process this pid names now",
        "serving_pid": live_stranger_pid,
        "serving_lstart": "Mon Jan  1 00:00:00 2024",
        "serving_argv": "not the process this pid names now",
        "port": STALE_PORT,
        "stop_command": list(STALE_STOP),
    }


def test_stop_now_does_not_signal_a_stale_own_pid_ledger_entry(tmp_path, monkeypatch):
    """F1's reproduction: the file predates this process, so none of it is ours to stop."""
    # The parent pid is alive and unrelated -- what a recycled pid would point at.
    stale = _stale_entry(os.getppid())
    _write_own_ledger(tmp_path, [stale])
    calls = []
    monkeypatch.setattr(
        runtimes,
        "_shutdown",
        lambda pid, port, stop_command=(): calls.append((pid, port, stop_command)),
    )

    stopped = runtimes.stop_own_engines(tmp_path)

    assert calls == [], (
        "Stop now signalled an entry this process never recorded: "
        f"{calls}, with no identity check against {stale['lstart']!r}/{stale['argv']!r}"
    )
    assert stopped == 0


def test_a_stale_own_pid_entry_is_not_merged_into_the_next_engine_start(tmp_path, monkeypatch):
    """Inverted 05-09 (it pinned the defect: the stale entry was merged forward as this
    process's own). The start hands it to the orphan handling instead: its pid is alive and
    its identity unproven, so it is kept -- marked ``inherited``, never Stop now's to signal."""
    stale = _stale_entry(os.getppid())
    _write_own_ledger(tmp_path, [stale])
    monkeypatch.setattr(runtimes, "writable_root", lambda: tmp_path)
    monkeypatch.setattr(runtimes, "_OWN_IDENTITY", {})
    monkeypatch.setattr(
        runtimes, "_process_identity", lambda pid: ("Tue Jan  2 00:00:00 2024", "engine")
    )
    monkeypatch.setattr(runtimes, "_listener_pids", lambda port: ())
    monkeypatch.setattr(runtimes, "_process_alive", lambda pid: pid == os.getppid())
    calls = []
    monkeypatch.setattr(runtimes, "_shutdown", lambda *args, **kwargs: calls.append(args))

    runtimes._record_running_engine(5555, 5555, 8100)

    path = tmp_path / "results" / runtimes.RUNNING_ENGINES_DIRNAME / f"{os.getpid()}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    own = [entry["pid"] for entry in payload["entries"] if not entry.get("inherited")]
    assert stale not in payload["entries"], "the start merged the stale entry as its own"
    assert own == [5555]
    assert [entry["pid"] for entry in payload["entries"] if entry.get("inherited")] == [
        os.getppid()
    ], "the stale entry was dropped unseen"
    assert payload["owner"]["pid"] == os.getpid()
    assert calls == []
    assert runtimes.stop_own_engines(tmp_path) == 1
    assert calls == [(5555, 8100, runtimes.RUNTIMES["omlx"].stop_command())]


def test_the_orphan_path_drops_the_same_entry_the_own_path_signals(tmp_path, monkeypatch):
    """The asymmetry: ``(lstart, argv)`` is checked on one path and not the other."""
    # A dead owner's file can only exist from a predecessor; its entry is the same shape.
    directory = tmp_path / "results" / runtimes.RUNNING_ENGINES_DIRNAME
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "999999.json").write_text(
        json.dumps({"entries": [_stale_entry(os.getppid())]}), encoding="utf-8"
    )
    calls = []
    monkeypatch.setattr(
        runtimes,
        "_shutdown",
        lambda pid, port, stop_command=(): calls.append((pid, port, stop_command)),
    )
    monkeypatch.setattr(runtimes, "_listener_pids", lambda port: ())

    runtimes.stop_orphaned_engines(root=tmp_path)

    assert calls == [], "the orphan path signalled an entry whose identity no longer matches"


def test_the_startup_orphan_sweep_skips_the_backends_own_pid_file(tmp_path, monkeypatch):
    """Startup never cleans it: the owner pid it gates on is the backend doing the sweep."""
    path = _write_own_ledger(tmp_path, [_stale_entry(os.getppid())])
    calls = []
    monkeypatch.setattr(
        runtimes,
        "_shutdown",
        lambda pid, port, stop_command=(): calls.append((pid, port, stop_command)),
    )

    runtimes.stop_orphaned_engines(root=tmp_path)

    assert calls == []
    assert path.exists(), "the sweep removed a live owner's ledger file"
