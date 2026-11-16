"""Fable 5.2 S5-F3: "exactly one model resident" is checked against one port and the Osaurus app.

``Runtime.start`` (``ohyesmlx/runtimes.py:2267``) asks two questions before it builds a command:
``_port_is_free(self.port)`` and ``_resident_osaurus_pids()``, whose own exclusion
(``:646``, ``pid not in _RUN_STARTED_PIDS``) hides a process this run spawned. So a start on
8100 never looks at 8081, 8080, 8000, 8200 or 1337; and ``Handle.stop`` (``:1981``) calls
``_shutdown`` first and discards the run's pids afterwards, so a stop that raises -- ``lsof``
unavailable is enough (``:1665-1669``) -- leaves the engine holding its weights and still
tracked as this run's own. The next cell then loads a second model beside it.

These tests fake only the module's outward seams (``_run``, ``_process_alive``,
``_port_is_free``, ``_spawn``, ``_listener_pids``). No server is started, no process is
signalled and no model is read: ``_spawn`` raises a marker, which is how a start that got past
its pre-flight refusal is observed from the outside.
"""

from __future__ import annotations

import subprocess

import pytest

from ohyesmlx import runtimes

MODEL_ID = "mlx-community/fake-model-4bit"


class SpawnReached(Exception):
    """``_spawn`` was called: the start passed every pre-start refusal."""


def _completed(stdout: str = ""):
    return subprocess.CompletedProcess(
        args=(), returncode=0, stdout=stdout, stderr=""
    )


@pytest.fixture(autouse=True)
def run_started_pids_restored():
    """The run's own pid set is module state; leave it as it was found."""
    saved = set(runtimes._RUN_STARTED_PIDS)
    try:
        yield
    finally:
        runtimes._RUN_STARTED_PIDS.clear()
        runtimes._RUN_STARTED_PIDS.update(saved)


@pytest.fixture
def artifact(tmp_path):
    """A real artifact directory: oMLX's catalog symlinks to it for real."""
    model = tmp_path / "hub" / "mlx-community" / "fake-model-4bit"
    model.mkdir(parents=True)
    (model / "config.json").write_text("{}")
    return str(model)


@pytest.fixture
def no_spawn(monkeypatch, tmp_path):
    """The pre-flight seams, with ``_spawn`` raising instead of starting anything."""
    monkeypatch.setattr(runtimes, "_log_path", lambda name: tmp_path / f"{name}.log")
    monkeypatch.setattr(runtimes, "_resident_osaurus_pids", lambda: ())

    spawns = []

    def spawn(command, log_path):
        spawns.append(command)
        raise SpawnReached(" ".join(command))

    monkeypatch.setattr(runtimes, "_spawn", spawn)
    return spawns


def test_start_refuses_when_another_runtimes_port_holds_a_listener(
    monkeypatch, no_spawn, artifact
):
    """The finding's own test: 8081 busy, an oMLX start on 8100, and no refusal."""
    mlxlm_port = runtimes.RUNTIMES["mlxlm"].port
    omlx_port = runtimes.RUNTIMES["omlx"].port
    monkeypatch.setattr(runtimes, "_port_is_free", lambda port: port != mlxlm_port)

    runtime = runtimes.Omlx(name="omlx", port=omlx_port)

    with pytest.raises(runtimes.RuntimeStartError, match=str(mlxlm_port)):
        runtime.start(artifact, MODEL_ID)


def test_start_refuses_when_a_failed_stop_left_another_engine_resident(
    monkeypatch, no_spawn, artifact
):
    """Scenario (a): ``_shutdown`` raises, its pids are never discarded, the next start goes on."""
    osaurus = runtimes.RUNTIMES["osaurus"]
    survivor = 9191

    # The engine a previous cell started, recorded exactly as `Runtime.start` records it.
    runtimes._RUN_STARTED_PIDS.add(survivor)
    handle = runtimes.Handle(
        pid=survivor,
        port=osaurus.port,
        base_url=osaurus.base_url,
        model_id=MODEL_ID,
        version="9.9.9",
        cold_load_s=1.0,
        stop_command=("osaurus", "stop"),
    )

    # `lsof` unavailable is the transient that makes `_shutdown` raise before signalling
    # anything, so the app is still serving and its port is still held.
    monkeypatch.setattr(runtimes, "_listener_pids", lambda port: None)
    with pytest.raises(runtimes.RuntimeStopError):
        handle.stop()
    assert survivor in runtimes._RUN_STARTED_PIDS, (
        "the stop had to skip its discards for this scenario to be the finding's"
    )

    # The survivor is real: `ps` lists it, it is alive, and its port answers.
    monkeypatch.setattr(
        runtimes,
        "_run",
        lambda command, timeout_s: _completed(
            stdout=f"{survivor} {runtimes.OSAURUS_APP_EXECUTABLES[0]}\n"
        ),
    )
    monkeypatch.setattr(runtimes, "_process_alive", lambda pid: pid == survivor)
    monkeypatch.setattr(
        runtimes, "_port_is_free", lambda port: port != osaurus.port
    )

    omlx = runtimes.Omlx(name="omlx", port=runtimes.RUNTIMES["omlx"].port)

    with pytest.raises(runtimes.RuntimeStartError, match=rf"{osaurus.port}|{survivor}"):
        omlx.start(artifact, MODEL_ID)
