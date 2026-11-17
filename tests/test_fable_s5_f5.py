"""Fable 5.2 S5-F5: no running-engines ledger entry exists until after readiness.

``Runtime.start`` spawns (``_spawn``, ``start_new_session=True``) and then polls
``await_ready`` for up to ``READY_TIMEOUT_S`` (900 s). ``_record_running_engine`` is called only
after ``cold_load_s`` is taken, i.e. after readiness. In that window the engine is in its own
session, holding its weights, and nothing on disk names it: ``stop_own_engines`` ("Stop now")
reads only the ledger, and ``stop_orphaned_engines`` at the next launch reads only ledger files.
A harness killed mid-load therefore leaves an engine no launch recovers and no "Stop now" reaches,
and a second run on the same port is refused by ``_port_is_free`` (runtimes.py:2295-2299).

No server is started here. Every seam ``Runtime.start`` reaches outside the module with is
faked: spawn, clock, ps/lsof-backed helpers via ``_run``, the listener probe, and the ledger
root. The pid below is a number, not a process.
"""

from __future__ import annotations

import json
import os
import subprocess

import pytest

from ohyesmlx import runtimes
from ohyesmlx.runtimes import RUNTIMES

ARTIFACT = "/nonexistent/models/gemma-4-12B-it-qat-4bit"
HF_ID = "mlx-community/gemma-4-12B-it-qat-4bit"
SPAWNED_PID = 4243


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += float(seconds)


class Aborted(Exception):
    """The start was interrupted mid-load: a quit, a crash, a killed backend."""


def _completed(stdout=""):
    return subprocess.CompletedProcess(
        args=(), returncode=0, stdout=stdout, stderr=""
    )


@pytest.fixture
def start_rig(tmp_path, monkeypatch):
    """``Runtime.start`` reachable with no process, no port and no runtimes on this host."""
    state = {
        "clock": FakeClock(),
        "spawned": [],
        "shutdowns": [],
        "alive": {},
        "listeners": (),
        "on_ready": None,
    }

    monkeypatch.setattr(runtimes, "_now", state["clock"])
    monkeypatch.setattr(runtimes, "_sleep", state["clock"].advance)
    monkeypatch.setattr(runtimes, "writable_root", lambda: tmp_path)
    # The ledger's owner block (05-09) needs this process's identity; the faked `ps` has none.
    monkeypatch.setattr(runtimes, "_OWN_IDENTITY", {os.getpid(): ("Wed Nov 5 09:59:00 2025", "pytest")})
    monkeypatch.setattr(runtimes, "_port_is_free", lambda port: True)
    monkeypatch.setattr(runtimes, "_listener_pids", lambda port: state["listeners"])
    monkeypatch.setattr(runtimes, "_process_alive", lambda pid: state["alive"].get(pid, False))
    # ps (resident-Osaurus probe, ledger identities) and lsof all come through _run.
    monkeypatch.setattr(runtimes, "_run", lambda command, timeout_s: _completed())
    monkeypatch.setattr(
        runtimes,
        "_shutdown",
        lambda pid, port, stop_command=(): state["shutdowns"].append((pid, port)),
    )

    def spawn(command, log_path):
        state["spawned"].append(command)
        state["alive"][SPAWNED_PID] = True
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("", encoding="utf-8")
        return SPAWNED_PID

    monkeypatch.setattr(runtimes, "_spawn", spawn)
    monkeypatch.setattr(runtimes, "_log_path", lambda name: tmp_path / "runtime.log")

    def await_ready(self, **kwargs):
        if state["on_ready"] is not None:
            return state["on_ready"](**kwargs)
        return HF_ID

    monkeypatch.setattr(runtimes.Runtime, "await_ready", await_ready)
    return state


def test_the_ledger_names_the_engine_before_readiness_is_awaited(start_rig):
    """The finding's test: at the moment of the abort the ledger already names the spawn."""
    ledger = runtimes._ledger_path()
    seen = {}

    def on_ready(*, pid, log_path, artifact_dir, model_id, timeout_s=runtimes.READY_TIMEOUT_S):
        seen["pid"] = pid
        seen["exists"] = ledger.exists()
        seen["entries"] = runtimes._read_ledger(ledger)[1]
        raise Aborted("the harness was killed while the model was loading")

    start_rig["on_ready"] = on_ready

    with pytest.raises(Aborted):
        RUNTIMES["mlxlm"].start(ARTIFACT, HF_ID)

    assert seen["pid"] == SPAWNED_PID, "the start never reached readiness with the spawned pid"
    assert seen["exists"], (
        "no running-engines ledger entry existed while the engine was loading: "
        f"nothing on disk named pid {SPAWNED_PID} on port 8081"
    )
    assert [entry.get("pid") for entry in seen["entries"]] == [SPAWNED_PID]


def test_the_observation_point_sees_a_ledger_written_right_after_the_spawn(
    start_rig, monkeypatch
):
    """Sensitivity: the missing write is the whole difference, not the rig.

    The fix direction -- write the entry immediately after ``_spawn`` -- is applied to the
    fixture here, against unmodified source. The same assertion that fails above passes,
    so the test above is red for the absent entry and for nothing else.
    """
    ledger = runtimes._ledger_path()
    spawn = runtimes._spawn

    def spawn_and_record(command, log_path):
        pid = spawn(command, log_path)
        runtimes._record_running_engine(pid, pid, RUNTIMES["mlxlm"].port)
        return pid

    monkeypatch.setattr(runtimes, "_spawn", spawn_and_record)
    seen = {}

    def on_ready(*, pid, log_path, artifact_dir, model_id, timeout_s=runtimes.READY_TIMEOUT_S):
        seen["exists"] = ledger.exists()
        seen["entries"] = runtimes._read_ledger(ledger)[1]
        raise Aborted("the harness was killed while the model was loading")

    start_rig["on_ready"] = on_ready

    with pytest.raises(Aborted):
        RUNTIMES["mlxlm"].start(ARTIFACT, HF_ID)

    assert seen["exists"], "a ledger written right after _spawn was not visible to the start"
    assert [entry.get("pid") for entry in seen["entries"]] == [SPAWNED_PID]


def test_a_load_interrupted_before_readiness_leaves_an_engine_the_next_launch_recovers(
    start_rig, tmp_path, monkeypatch
):
    """The gap closed: the engine is in the ledger from its spawn, so the next launch stops it.

    Inverted from the finding's control, which pinned the defect (no ledger, nothing recovered).
    The start's own cleanup is what a SIGKILL of the harness skips: it is made to fail here, which
    is the case where the entry must stay (a cleanup that succeeds forgets it).
    """
    start_rig["on_ready"] = lambda **kwargs: (_ for _ in ()).throw(
        Aborted("the backend died while the model was loading")
    )
    monkeypatch.setattr(
        runtimes,
        "_process_identity",
        lambda pid: ("Wed Nov 5 10:00:00 2025", "python -m mlx_lm.server"),
    )

    def cleanup_fails(pid, port, stop_command=()):
        raise runtimes.RuntimeStopError("port still held")

    monkeypatch.setattr(runtimes, "_shutdown", cleanup_fails)

    with pytest.raises(runtimes.RuntimeStopError, match="cleanup failed"):
        RUNTIMES["mlxlm"].start(ARTIFACT, HF_ID)

    ledger = runtimes._ledger_path()
    entries = runtimes._read_ledger(ledger)[1]
    assert [entry["pid"] for entry in entries] == [SPAWNED_PID]
    assert entries[0]["port"] == RUNTIMES["mlxlm"].port

    # The next launch: this harness is gone (its file now belongs to a dead owner), the engine
    # it spawned is not.
    dead_owner = 999_999
    payload = json.loads(ledger.read_text(encoding="utf-8"))
    payload["owner"]["pid"] = dead_owner
    ledger.unlink()
    dead_file = runtimes._ledger_path(dead_owner)
    dead_file.write_text(json.dumps(payload), encoding="utf-8")

    stopped = []
    monkeypatch.setattr(runtimes, "_shutdown", lambda pid, port, stop_command=(): stopped.append((pid, port)))
    monkeypatch.setattr(os, "kill", lambda pid, sig: None)
    start_rig["alive"][SPAWNED_PID] = True
    start_rig["alive"][dead_owner] = False

    runtimes.stop_orphaned_engines()

    assert stopped == [(SPAWNED_PID, RUNTIMES["mlxlm"].port)], (
        "the sweep did not recover the engine the ledger named from its spawn"
    )


def test_a_load_that_fails_and_cleans_up_leaves_no_ledger_entry(start_rig):
    start_rig["on_ready"] = lambda **kwargs: (_ for _ in ()).throw(Aborted("the load failed"))

    with pytest.raises(Aborted):
        RUNTIMES["mlxlm"].start(ARTIFACT, HF_ID)

    assert start_rig["shutdowns"] == [(SPAWNED_PID, RUNTIMES["mlxlm"].port)]
    assert runtimes._read_ledger(runtimes._ledger_path())[1] == []
