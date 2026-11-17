"""05-10b: an engine is found by its process, on whatever port it listens; a default port held
by something that is not an engine no longer blocks a start (AC-1..AC-7, AC-3b).

Every ``ps``/``lsof`` answer is injected through ``runtimes._run``; no engine is started. The one
real socket is AC-3b's local fake model server, bound to an ephemeral loopback port.
"""

from __future__ import annotations

import dataclasses
import http.server
import json
import os
import threading
from types import SimpleNamespace

import pytest

from ohyesmlx import measure, quickbench, runtimes

LAB = "/Users/x/Library/Application Support/OhYesMLX/labs/optiq-0.5.13"
VENV_PY = "/Users/x/.venvs/a/bin/python"


class FakeHost:
    """``ps`` and ``lsof`` as one table: pid -> (comm, args, listening ports)."""

    def __init__(self, procs=None, *, ps_fails=False, lsof_fails=False):
        self.procs = dict(procs or {})
        self.ps_fails = ps_fails
        self.lsof_fails = lsof_fails
        self.commands = []

    def __call__(self, command, timeout_s):
        self.commands.append(command)
        if command[0] == runtimes.PS:
            if self.ps_fails:
                return None
            column = command[-1].split(",")[1].rstrip("=")
            index = {"comm": 0, "args": 1}[column]
            out = "".join(f"{pid:>6} {p[index]}\n" for pid, p in self.procs.items())
            return SimpleNamespace(stdout=out, returncode=0)
        if command[0] == runtimes.LSOF:
            if self.lsof_fails:
                return None
            if "-F" in command:
                pids = {int(p) for p in command[command.index("-p") + 1].split(",")}
                out = ""
                for pid in sorted(pids):
                    ports = self.procs.get(pid, (None, None, ()))[2]
                    if ports:
                        out += f"p{pid}\n" + "".join(f"n127.0.0.1:{port}\n" for port in ports)
                return SimpleNamespace(stdout=out, returncode=0 if out else 1)
            port = int(next(a for a in command if a.startswith("-iTCP:")).split(":")[1])
            holders = [pid for pid, p in self.procs.items() if port in p[2]]
            if "-t" in command:
                out = "".join(f"{pid}\n" for pid in holders)
            else:
                out = "".join(f"x {pid} u\n" for pid in holders)
            return SimpleNamespace(stdout=out, returncode=0 if out else 1)
        return SimpleNamespace(stdout="", returncode=0)


@pytest.fixture
def host(monkeypatch):
    fake = FakeHost()
    monkeypatch.setattr(runtimes, "_run", fake)
    monkeypatch.setattr(runtimes, "_models_probe", lambda port: None)
    monkeypatch.setattr(runtimes, "_engine_roots", lambda: ())
    return fake


# --- AC-1 / AC-2: who is an engine -----------------------------------------------------------


@pytest.mark.parametrize(
    "comm, args, engine",
    [
        (VENV_PY, f"python -m mlx_lm.server --model /m --port 8091", "mlxlm"),
        (VENV_PY, f"{VENV_PY} -u -m mlx_lm.server --port 1", "mlxlm"),
        (f"{LAB}/bin/python", f"{LAB}/bin/python {LAB}/bin/optiq serve --port 8001", "optiq"),
        (
            "/Applications/oMLX.app/Contents/Resources/Python/cpython-3.11/bin/python3",
            "/Applications/oMLX.app/Contents/Resources/Python/cpython-3.11/bin/python3 "
            "-m omlx.cli serve --port 8101",
            "omlx",
        ),
        (VENV_PY, f"{VENV_PY} /opt/vmlx/bin/vmlx serve /m --port 8002", "vmlx"),
        (
            "/Users/x/Library/Application Support/MTPLX/runtime-venv/bin/python3.12",
            "/Users/x/Library/Application Support/MTPLX/runtime-venv/bin/python3.12 "
            "/Users/x/Library/Application Support/MTPLX/runtime-venv/bin/mtplx serve --port 9",
            "mtplx",
        ),
        (runtimes.OSAURUS_APP_EXECUTABLES[0], runtimes.OSAURUS_APP_EXECUTABLES[0], "osaurus"),
        # Not engines: a client sharing the name, text tools reading about an engine, a lookalike.
        ("/opt/homebrew/bin/osaurus", "osaurus mcp", None),
        ("/usr/bin/grep", "grep mlx_lm.server", None),
        ("/usr/bin/less", "less /x/bin/optiq serve", None),
        (VENV_PY, f"{VENV_PY} ./fake optiq serve", None),
        (VENV_PY, f"{VENV_PY} -c import x -m mlx_lm.server", None),
        (VENV_PY, f"{VENV_PY} -m http.server 8081", None),
    ],
)
def test_engine_of_matches_by_executable_and_anchored_args(comm, args, engine):
    assert runtimes._engine_of(comm, args) == engine


def test_an_engine_on_a_non_default_port_is_resident_with_its_port(host):
    host.procs[700] = (VENV_PY, "python -m mlx_lm.server --port 8091", (8091,))
    host.procs[701] = ("/usr/bin/grep", "grep mlx_lm.server", ())

    assert runtimes.resident_engines() == (("mlxlm", 700, (8091,)),)


def test_a_resident_engine_refuses_every_start_naming_engine_pid_and_port(host):
    host.procs[700] = (
        "/Applications/oMLX.app/Contents/Resources/Python/cpython-3.11/bin/python3",
        "/Applications/oMLX.app/Contents/Resources/Python/cpython-3.11/bin/python3 -m omlx.cli serve",
        (8001,),
    )
    plan = runtimes.port_plan(runtimes.RUNTIMES["vmlx"])

    assert plan.port is None
    assert "omlx" in plan.refusal and "700" in plan.refusal and "8001" in plan.refusal


def test_an_engine_whose_ports_lsof_cannot_read_still_refuses_port_unknown(host):
    host.procs[700] = (VENV_PY, "python -m mlx_lm.server", (8091,))
    host.lsof_fails = True

    plan = runtimes.port_plan(runtimes.RUNTIMES["optiq"])

    assert plan.port is None and "700" in plan.refusal and "unknown" in plan.refusal


def test_ps_unreadable_fails_closed(host):
    host.ps_fails = True
    with pytest.raises(runtimes.RuntimeStartError):
        runtimes.resident_engines()


def test_the_osaurus_app_is_resident_by_full_path_and_its_mcp_client_is_not(host):
    host.procs[9191] = (runtimes.OSAURUS_APP_EXECUTABLES[0], runtimes.OSAURUS_APP_EXECUTABLES[0], ())
    host.procs[9192] = ("/opt/homebrew/bin/osaurus", "osaurus mcp", ())

    assert runtimes.resident_engines() == (("osaurus", 9191, ()),)
    assert quickbench._osaurus_app_running() is True


# --- AC-3 / AC-3b / AC-4: the default port's holder --------------------------------------------


def test_a_free_default_port_is_used_unchanged(host):
    plan = runtimes.port_plan(runtimes.RUNTIMES["vmlx"])
    assert (plan.port, plan.refusal, plan.note) == (8000, None, None)


def test_a_non_engine_on_the_default_port_moves_the_engine(host, monkeypatch):
    host.procs[555] = ("/usr/local/bin/node", "node dev-server.js", (8000,))
    monkeypatch.setattr(runtimes, "_free_port", lambda: 54321)

    plan = runtimes.port_plan(runtimes.RUNTIMES["vmlx"])

    assert plan.port == 54321 and plan.refusal is None
    for part in ("8000", "555", "/usr/local/bin/node", "54321"):
        assert part in plan.note


def test_osaurus_never_moves(host):
    host.procs[555] = ("/usr/local/bin/node", "node dev-server.js", (1337,))

    plan = runtimes.port_plan(runtimes.RUNTIMES["osaurus"])

    assert plan.port is None and "555" in plan.refusal and "1337" in plan.refusal


def test_an_unreadable_default_port_refuses(host):
    host.lsof_fails = True
    plan = runtimes.port_plan(runtimes.RUNTIMES["vmlx"])
    assert plan.port is None and "8000" in plan.refusal


def test_a_holder_inside_an_engine_root_refuses(host, monkeypatch):
    exe = "/Applications/vMLX.app/Contents/MacOS/thermalforge"
    host.procs[556] = (exe, exe, (8000,))
    monkeypatch.setattr(runtimes, "_engine_roots", lambda: ("/Applications/vMLX.app",))

    plan = runtimes.port_plan(runtimes.RUNTIMES["vmlx"])

    assert plan.port is None and "556" in plan.refusal and exe in plan.refusal


class _ModelsHandler(http.server.BaseHTTPRequestHandler):
    status = 200
    body = {"object": "list", "data": [{"id": "m"}]}

    def do_GET(self):  # noqa: N802
        payload = json.dumps(self.body).encode()
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


@pytest.fixture
def model_server():
    def serve(status, body):
        handler = type("H", (_ModelsHandler,), {"status": status, "body": body})
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return server.server_address[1]

    servers = []
    yield serve
    for server in servers:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize(
    "status, body, is_model_server",
    [
        (200, {"object": "list", "data": [{"id": "m"}]}, True),
        (401, {"error": "no key"}, True),
        (403, {"error": "no"}, True),
        (200, {"hello": "world"}, False),
        (404, {"error": "nope"}, False),
    ],
)
def test_the_models_probe_recognises_a_model_server(model_server, status, body, is_model_server):
    port = model_server(status, body)
    assert (runtimes._models_probe(port) is not None) is is_model_server


def test_a_holder_answering_v1_models_refuses(host, monkeypatch):
    host.procs[557] = ("/Applications/LM Studio.app/Contents/MacOS/lms", "lms server", (8080,))
    monkeypatch.setattr(runtimes, "_models_probe", lambda port: "answers /v1/models")

    plan = runtimes.port_plan(runtimes.RUNTIMES["optiq"])

    assert plan.port is None and "557" in plan.refusal and "/v1/models" in plan.refusal


def test_a_probe_that_gets_no_answer_is_not_a_model_server():
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    assert runtimes._models_probe(port) is None


# --- AC-6: the ledger's stop command follows the engine's name --------------------------------


def test_a_fallback_port_entry_resolves_its_stop_by_name():
    assert runtimes._stop_command_for({"runtime": "osaurus", "port": 54321}) == ("osaurus", "stop")
    assert runtimes._stop_command_for({"runtime": "vmlx", "port": 54321}) == ()


def test_a_pre_plan_entry_still_resolves_by_port():
    assert runtimes._stop_command_for({"port": 1337}) == ("osaurus", "stop")
    assert runtimes._stop_command_for({"port": 59999}) == ()


def test_an_unknown_runtime_name_falls_back_to_the_port():
    assert runtimes._stop_command_for({"runtime": "nope", "port": 1337}) == ("osaurus", "stop")


# --- AC-5: the port on every row --------------------------------------------------------------


def test_cell_result_has_a_port_field_defaulting_to_none():
    fields = {f.name: f for f in dataclasses.fields(measure.CellResult)}
    assert fields["port"].default is None


# --- AC-7: quickbench asks the same decision ---------------------------------------------------


def test_quickbench_port_refusal_is_port_plans(host, monkeypatch):
    host.procs[700] = (VENV_PY, "python -m mlx_lm.server", (8091,))
    reason = quickbench._port_refusal("optiq")
    assert reason is not None and "700" in reason and "8091" in reason


def test_quickbench_does_not_skip_an_engine_whose_default_port_a_non_engine_holds(host, monkeypatch):
    host.procs[555] = ("/usr/local/bin/node", "node dev.js", (8000,))
    monkeypatch.setattr(runtimes, "_free_port", lambda: 54321)
    assert quickbench._port_refusal("vmlx") is None
