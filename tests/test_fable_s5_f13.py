"""Fable 5.2 S5-F13: the ledger's ``stop_command`` is data on disk that gets executed.

``_record_running_engine`` writes ``stop_command`` into ``running-engines/<owner>.json`` and
both stoppers hand the string list to ``_shutdown``, which runs it through ``_run``. Nothing
re-derives it from ``RUNTIMES``, so a ledger file names any argv its writer liked.

Two entry points, tested separately below: ``stop_own_engines`` (the app's "Stop now") runs
the recorded command with no identity check at all, and ``_stop_orphan`` runs it after the
identity checks -- which are satisfied by the same writer. Nothing here starts a server or
signals a process: the pids are numbers, the identity and liveness probes are the module's
own seams, and the only thing executed is the test's own ``touch``.
"""

from __future__ import annotations

import json
import os

from ohyesmlx import runtimes

PORT = 8081
LSTART = "Wed Nov 5 10:00:00 2025"
ARGV = "python -m mlx_lm.server --model /models/x --port 8081"
DEAD_PID = 64123
DEAD_OWNER = 64124


def write_ledger(root, owner, entries, owner_block=None):
    directory = root / "results" / runtimes.RUNNING_ENGINES_DIRNAME
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{owner}.json"
    payload = {"entries": entries}
    if owner_block is not None:
        payload["owner"] = owner_block
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def entry(stop_command, pid=DEAD_PID):
    return {
        "pid": pid,
        "lstart": LSTART,
        "argv": ARGV,
        "serving_pid": pid,
        "serving_lstart": LSTART,
        "serving_argv": ARGV,
        "port": PORT,
        "stop_command": stop_command,
    }


def quiet_stop(monkeypatch):
    monkeypatch.setattr(runtimes, "_engine_env", lambda: dict(os.environ))
    monkeypatch.setattr(runtimes, "_process_alive", lambda pid: False)
    monkeypatch.setattr(runtimes, "_port_is_free", lambda port: True)


def test_stop_now_does_not_execute_a_stop_command_read_from_the_ledger(tmp_path, monkeypatch):
    """``stop_own_engines`` runs ``<this pid>.json``'s command with no identity check."""
    marker = tmp_path / "stop-now-executed"
    # 05-09: Stop now reads only a file whose owner block is this process (S1-F1).
    monkeypatch.setattr(runtimes, "_OWN_IDENTITY", {os.getpid(): ("own lstart", "own argv")})
    write_ledger(
        tmp_path,
        os.getpid(),
        [entry(["/usr/bin/touch", str(marker)])],
        {"pid": os.getpid(), "lstart": "own lstart", "argv": "own argv"},
    )
    quiet_stop(monkeypatch)
    monkeypatch.setattr(runtimes, "_listener_pids", lambda port: ())

    stopped = runtimes.stop_own_engines(tmp_path)

    assert stopped == 1, "precondition: the entry was taken to be stopped"
    assert not marker.exists(), (
        "the ledger's stop_command was executed verbatim: a file nothing vouches for "
        "chose the argv this process ran"
    )


def test_an_orphan_entry_does_not_execute_its_recorded_stop_command(tmp_path, monkeypatch):
    """The identity-matched orphan path runs the recorded command too.

    The finding's own correction says the checks do precede the command here; they do --
    and the entry supplies both sides of the comparison, so they do not constrain it.
    """
    marker = tmp_path / "orphan-executed"
    write_ledger(
        tmp_path, DEAD_OWNER, [entry(["/usr/bin/touch", str(marker)])]
    )
    quiet_stop(monkeypatch)
    monkeypatch.setattr(runtimes, "_listener_pids", lambda port: (DEAD_PID,))
    monkeypatch.setattr(runtimes, "_process_identity", lambda pid: (LSTART, ARGV))

    runtimes.stop_orphaned_engines(tmp_path)

    assert not marker.exists(), (
        "the orphan entry's stop_command was executed: the entry's own fields satisfied "
        "every identity check the argv was never compared against"
    )
