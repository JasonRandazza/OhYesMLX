"""S5-F10: `lsof`, `ps` and stop commands run under the lab environment, so one engine's
lab-path defect disables stopping and recovery for every engine.

The claim has three parts, each tested below against a scratch files, no server and no
signal:

1. ``lab-paths.json`` that is not JSON makes ``lab_paths`` raise ``ValueError``, which
   ``_run`` does not catch (``:584`` catches ``OSError``, ``subprocess.SubprocessError``
   and ``RuntimeStartError`` only). Every caller of the probe then dies with a traceback --
   ``Handle.stop``, the "Stop now" thread through ``stop_own_engines`` (which catches only
   ``RuntimeStopError``), and launch recovery -- before anything is signalled.
2. A lab path that names a directory which is not there raises ``RuntimeStartError`` inside
   ``_engine_env``, which ``_run`` *does* catch and turns into ``None``. ``_shutdown`` then
   reads ``None`` as "cannot identify listeners" and refuses with a ``RuntimeStopError`` for
   every engine that has a stop command, so a stop path is refusable by configuration.
3. ``_engine_env`` walks every engine on every spawn, with no engine identity, so a missing
   OptiQ lab copy refuses an Osaurus or mlx-lm start with a message about OptiQ.

Nothing here starts a server, loads a model, or signals a process: the pid used is a reaped
child and the port is one this test bound and released.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from ohyesmlx import runtimes


def write_manifest(tmp_path):
    """The shipped manifest's shape: every engine present, no lab_path committed."""
    payload = {
        name: {
            "version": "0.0.0",
            "verified": "2026-10-29",
            "lab_path": None,
            "canary": None,
        }
        for name in ("mlxlm", "osaurus", "omlx", "optiq", "vmlx")
    }
    path = tmp_path / "engines-tested.json"
    path.write_text(json.dumps(payload))
    return path


def bind_env(manifest, lab_paths_file):
    """``_engine_env`` as ``_run``/``_spawn`` call it, driven by scratch files.

    ``_engine_env`` takes the two loaders' paths so a test can drive it, and ``_run`` calls
    it with neither. Binding them here is how that parameter reaches the real call chain
    without this Mac's Application Support file.
    """

    original = runtimes._engine_env

    def env():
        return original(manifest, lab_paths_file)

    return env


def a_free_port():
    """A port nothing is listening on: bound to take it, then released."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def a_dead_pid():
    """A pid that has exited and been reaped, so ``_process_alive`` is false."""
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


def test_a_listener_probe_survives_a_lab_paths_file_that_is_not_json(tmp_path, monkeypatch):
    """`_listener_pids` must answer, not raise, when the lab file is malformed.

    `lsof` is a system tool and never needed a lab PATH prefix, so a configuration defect in
    the lab file is not a reason for it to fail. Today `_engine_env` raises `ValueError`
    out of `_run`'s `try`, which catches only OSError/SubprocessError/RuntimeStartError --
    and `Handle.stop` and `stop_own_engines` catch only `RuntimeStopError`, so the defect
    escapes both and the process is never signalled.
    """
    lab_paths = tmp_path / "lab-paths.json"
    lab_paths.write_text("{", encoding="utf-8")
    monkeypatch.setattr(runtimes, "_engine_env", bind_env(write_manifest(tmp_path), lab_paths))

    listeners = runtimes._listener_pids(a_free_port())

    assert listeners == ()


def test_a_stop_is_not_refused_by_a_lab_path_that_is_not_there(tmp_path, monkeypatch):
    """`_shutdown` with a stop command must not refuse itself over a lab-path defect.

    A lab copy that is not there raises `RuntimeStartError` in `_engine_env`, `_run` answers
    `None`, and `_shutdown` reads that as "cannot identify listeners" and raises the
    refusal *before* signalling anything -- for every engine that has a stop command. The
    stop command here is `true`: with a dead pid and a free port there is nothing to stop,
    so the only acceptable outcome is returning.
    """
    lab_paths = tmp_path / "lab-paths.json"
    lab_paths.write_text(json.dumps({"optiq": str(tmp_path / "gone" / "bin")}))
    monkeypatch.setattr(runtimes, "_engine_env", bind_env(write_manifest(tmp_path), lab_paths))

    runtimes._shutdown(a_dead_pid(), a_free_port(), ("true",))


def test_a_port_probe_does_not_read_a_lab_path_defect_as_busy(tmp_path, monkeypatch):
    """The other five engines have no stop command, so they take `_shutdown`'s other branch.

    `_run` answering `None` makes `_port_is_free` answer "busy" (its docstring: "'unknown'
    has to mean 'not free yet'"), so `await_port_free` polls a port nothing is listening on
    for the whole `STOP_TIMEOUT_S` and then raises "port ... is still held 30s after
    stopping". Measured on the current code: `RuntimeStopError` after 30.0 s. The probe is
    called directly here so the test costs no 30 s.
    """
    lab_paths = tmp_path / "lab-paths.json"
    lab_paths.write_text(json.dumps({"optiq": str(tmp_path / "gone" / "bin")}))
    monkeypatch.setattr(runtimes, "_engine_env", bind_env(write_manifest(tmp_path), lab_paths))

    assert runtimes._port_is_free(a_free_port()) is True, (
        "a lab-path defect made a free port read as busy, so every stop of a runtime "
        "without a stop command spends STOP_TIMEOUT_S and then fails"
    )


def test_a_start_is_not_refused_by_a_port_the_lab_defect_cannot_see(
    tmp_path, monkeypatch
):
    """The same `None` also refuses a START, and names a port that is free.

    `Runtime.start`'s first check is `if not _port_is_free(self.port)` (`:2288-2292`), and
    `_port_is_free` reads an unverifiable port as busy. So a lab-path defect refuses every
    start with "port NNNN is already held by a listener this run did not start" -- a claim
    about a port nothing is listening on. Measured on the current code with mlx-lm's 8081
    (free when probed without the defect). Popen is faked, so reaching it means the port
    check passed and no server was started either way.
    """
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", runtimes.RUNTIMES["mlxlm"].port))
        except OSError:
            pytest.skip(f"port {runtimes.RUNTIMES['mlxlm'].port} is in use on this Mac")

    class FakePopen:
        def __init__(self, *args, **kwargs):
            raise AssertionError("port check passed")

    lab_paths = tmp_path / "lab-paths.json"
    lab_paths.write_text(json.dumps({"optiq": str(tmp_path / "gone" / "bin")}))
    monkeypatch.setattr(runtimes, "_engine_env", bind_env(write_manifest(tmp_path), lab_paths))
    monkeypatch.setattr(runtimes.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(runtimes, "_sleep", lambda seconds: None)

    reached_popen = False
    try:
        runtimes.RUNTIMES["mlxlm"].start(str(tmp_path), "org/model")
    except runtimes.RuntimeStartError as error:
        assert "already held by a listener" not in str(error), (
            "a lab-path defect made a free port read as held, so the start refusal names a "
            f"listener that is not there: {error}"
        )
    except AssertionError as error:
        reached_popen = "port check passed" in str(error)
        assert reached_popen, error
    assert reached_popen, "the start neither refused the port nor reached the spawn"


def test_one_engines_missing_lab_copy_does_not_refuse_another_engines_start(
    tmp_path, monkeypatch
):
    """An Osaurus start must not be refused with a message about OptiQ.

    `_engine_env` has no engine identity, so the loop's refusal for OptiQ is the refusal the
    Osaurus spawn gets. Popen is faked so this test can never start a server, whatever the
    code grows into.
    """

    class FakePopen:
        def __init__(self, *args, **kwargs):
            raise OSError(2, "No such file or directory")

    lab_paths = tmp_path / "lab-paths.json"
    lab_paths.write_text(json.dumps({"optiq": str(tmp_path / "gone" / "bin")}))
    monkeypatch.setattr(runtimes, "_engine_env", bind_env(write_manifest(tmp_path), lab_paths))
    monkeypatch.setattr(runtimes.subprocess, "Popen", FakePopen)

    with pytest.raises(runtimes.RuntimeStartError) as raised:
        runtimes._spawn(("osaurus", "serve", "--port", "1337"), tmp_path / "runtime.log")

    assert "optiq" not in str(raised.value), (
        "an Osaurus start was refused with a message about OptiQ, an engine this spawn "
        f"never touches: {raised.value}"
    )


def test_stop_own_engines_catches_more_than_the_stop_error(tmp_path, monkeypatch):
    """"Stop now" must survive a lab-path defect: `stop_own_engines` catches `RuntimeStopError`.

    The listener probe's `ValueError` is not one, so it escapes the per-entry `except` and
    the daemon thread that runs this dies before signalling the first engine. The ledger
    entry names a dead pid and a free port, so with a working probe the stop is a no-op
    that counts one engine.
    """
    lab_paths = tmp_path / "lab-paths.json"
    lab_paths.write_text("{", encoding="utf-8")
    monkeypatch.setattr(runtimes, "_engine_env", bind_env(write_manifest(tmp_path), lab_paths))

    ledger = tmp_path / "results" / "running-engines" / f"{os.getpid()}.json"
    ledger.parent.mkdir(parents=True)
    # 05-09: Stop now reads only a file whose owner block is this process (S1-F1).
    monkeypatch.setattr(runtimes, "_OWN_IDENTITY", {os.getpid(): ("own lstart", "own argv")})
    ledger.write_text(
        json.dumps(
            {
                "owner": {"pid": os.getpid(), "lstart": "own lstart", "argv": "own argv"},
                "entries": [
                    {
                        "pid": a_dead_pid(),
                        "lstart": None,
                        "argv": None,
                        "serving_pid": None,
                        "serving_lstart": None,
                        "serving_argv": None,
                        "port": a_free_port(),
                        "stop_command": ["true"],
                    }
                ]
            }
        )
    )

    assert runtimes.stop_own_engines(root=tmp_path) == 1
