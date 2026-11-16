"""Fable 5.2 S5-F2: ``cold_load_s`` includes the version probe and an ``lsof`` call.

``Runtime.start`` takes its clock before ``_spawn`` and subtracts it only after
``await_ready``, ``self.version()`` and ``_serving_pid`` have all returned. ``version()`` runs
a fresh subprocess on every start (``python -m mlx_lm --version``, ``osaurus doctor --json``,
``optiq --version``, ``omlx --version``, a ``sed`` over vMLX's shipped source, ``mtplx
--version``), and ``_serving_pid`` runs ``lsof``. Both sit inside the timed window, so the
published cold-load metric carries a per-runtime constant that is not load time.

The only thing faked here is the clock and the module's outward seams. The version command is
the real ``Runtime.version`` path with a ``_run`` that takes 5 s, which is what a cold Python
import of mlx-lm costs.

No server is started, no model is read and nothing is signalled.
"""

from __future__ import annotations

import subprocess

import pytest

from ohyesmlx import runtimes

MODEL_ID = "mlx-community/fake-model-4bit"
SPAWN_S = 2.0
VERSION_PROBE_S = 5.0
LSOF_PROBE_S = 0.5
PORT = 59998


def _completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        args=(), returncode=returncode, stdout=stdout, stderr=stderr
    )


class Clock:
    """Monotonic time that only moves when something spawns or runs a helper."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += float(seconds)


class SlowProbeRuntime(runtimes.Runtime):
    """A runtime whose load is instant and whose helper subprocesses are not."""

    def start_command(self, artifact_dir, model_id, **kwargs):
        return ("fake-engine", "--model", artifact_dir)

    def version_command(self):
        return ("fake-engine", "--version")

    def model_id_candidates(self, artifact_dir, model_id):
        return (model_id,)


@pytest.fixture
def seams(monkeypatch, tmp_path):
    clock = Clock()
    log_file = tmp_path / "runtime.log"
    state = {"pid": 4242, "alive": True}

    monkeypatch.setattr(runtimes, "_now", clock)
    monkeypatch.setattr(runtimes, "_sleep", clock.advance)
    monkeypatch.setattr(runtimes, "_log_path", lambda name: log_file)
    monkeypatch.setattr(runtimes, "writable_root", lambda: tmp_path)
    monkeypatch.setattr(runtimes, "_resident_osaurus_pids", lambda: ())
    monkeypatch.setattr(runtimes, "_port_is_free", lambda port: True)
    monkeypatch.setattr(runtimes, "_process_alive", lambda pid: state["alive"])
    monkeypatch.setattr(runtimes, "_inventory", lambda base_url, api_key=None: (MODEL_ID,))
    monkeypatch.setattr(
        runtimes,
        "_record_running_engine",
        lambda pid, serving_pid, port, stop_command=(): None,
    )

    def spawn(command, log_path):
        clock.advance(SPAWN_S)
        log_path.write_text("Starting httpd at 127.0.0.1 on port 8081...\n")
        state["pid"] += 1
        return state["pid"]

    def run(command, timeout_s):
        if command in (("fake-engine", "--version"),):
            clock.advance(VERSION_PROBE_S)
            return _completed(stdout="9.9.9\n")
        if command and command[0] == runtimes.LSOF:
            clock.advance(LSOF_PROBE_S)
            return _completed(stdout="")
        return _completed()

    monkeypatch.setattr(runtimes, "_spawn", spawn)
    monkeypatch.setattr(runtimes, "_run", run)
    yield clock


def test_cold_load_s_does_not_include_the_version_probe_or_lsof(seams):
    """The finding: the load metric carries the helper probes' time, per-runtime constants."""
    runtime = SlowProbeRuntime(name="slowprobe", port=PORT)

    handle = runtime.start("/nonexistent/artifact", MODEL_ID)

    # The whole window this metric names is spawn -> ready: SPAWN_S and nothing else. The
    # inventory answers on the first poll, so no readiness poll sleeps.
    assert handle.cold_load_s == pytest.approx(SPAWN_S), (
        "cold_load_s carries the helper probes: the version subprocess costs "
        f"{VERSION_PROBE_S}s and the lsof listener probe {LSOF_PROBE_S}s, and the metric "
        f"reported {handle.cold_load_s}s for a {SPAWN_S}s load"
    )
    # A fix that stops probing the version rather than moving the probe would be wrong too.
    assert handle.version == "9.9.9"
