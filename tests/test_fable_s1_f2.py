"""Fable 5.2 S1-F2: owner liveness is a bare pid, so a recycled pid strands the owner's files.

Both probes -- ``fetch._pid_alive`` and ``runtimes._process_alive`` -- answer "alive" on
``PermissionError``, and neither consumer records anything that would tell its owner from a
process that inherited the pid later:

* ``fetch._acquire_lock`` finds ``download.lock`` naming that pid, sees it alive and returns
  ``False``; ``download`` (``fetch.py:707``) and ``evict`` (``:1217``) both answer ``busy``,
  so the dead owner's lock blocks every later transfer for as long as that pid belongs to
  something this user cannot signal.
* ``runtimes.stop_orphaned_engines`` skips ``running-engines/<owner>.json`` whenever the
  owner pid is alive (``runtimes.py:1890-1891``), so the engine the dead owner recorded is
  never recovered and keeps its port and its weights.

The dead owner is modelled with pid 1: a real, running process no harness could ever be, and
one this user cannot signal -- what a recycled low pid becomes after a reboot. No process is
started, signalled or killed.
"""

from __future__ import annotations

import json
import os

from ohyesmlx import fetch, runtimes

OWNER_PID = 1


def test_a_lock_whose_owner_pid_belongs_to_another_process_is_reclaimed(tmp_path):
    """The finding's test idea: a lock naming pid 1 must not block every transfer forever."""
    lock = tmp_path / fetch.LOCK_NAME
    lock.write_text(str(OWNER_PID), encoding="utf-8")

    acquired = fetch._acquire_lock(str(lock))

    assert acquired is True, (
        f"a lock naming pid {OWNER_PID} -- alive, but not the process that wrote it -- is "
        "never reclaimed, so every later download and eviction answers busy with "
        "'another download is already running'"
    )
    assert lock.read_text(encoding="utf-8").strip() == str(os.getpid())
    fetch._release_lock(str(lock))


def test_a_dead_owners_ledger_file_is_swept_when_its_pid_is_alive_again(tmp_path, monkeypatch):
    """A recycled owner pid skips its ledger at every launch, so its engine is never stopped."""
    directory = tmp_path / "results" / runtimes.RUNNING_ENGINES_DIRNAME
    directory.mkdir(parents=True)
    path = directory / f"{OWNER_PID}.json"
    path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "pid": 999_999,
                        "lstart": "Thu Nov  6 11:00:00 2025",
                        "argv": "the engine the dead owner spawned",
                        "serving_pid": 999_999,
                        "serving_lstart": "Thu Nov  6 11:00:00 2025",
                        "serving_argv": "the engine the dead owner spawned",
                        "port": 59999,
                        "stop_command": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    calls = []
    monkeypatch.setattr(runtimes, "_listener_pids", lambda port: ())
    monkeypatch.setattr(runtimes, "_shutdown", lambda *args, **kwargs: calls.append(args))

    runtimes.stop_orphaned_engines(root=tmp_path)

    assert calls == [], "the sweep signalled a process whose identity it had not confirmed"
    assert not path.exists(), (
        f"running-engines/{OWNER_PID}.json is skipped at every launch because its owner pid "
        "is alive again; the engine it records keeps its port and its weights forever"
    )
