"""055-03 AC-1: one sweep, by process scan rather than by port.

The kill loop is ``runtimes.sweep_resident_engines`` and the shell wrapper is
``scripts/sweep.sh``. Nothing here signals a real process: every pid is a number the function
is handed by a monkeypatched ``resident_engines``, and no test runs a runner script.
"""

from __future__ import annotations

import re
import signal
import subprocess
from pathlib import Path

import pytest

from ohyesmlx import runtimes

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
SWEEP = SCRIPTS / "sweep.sh"

# 045-03's clean-account smoke keeps a sweep of its own, and must: it signals only the
# throwaway account's leftovers (TERM then KILL, every listing limited to that user), and the
# phase boundaries forbid changing its behaviour. Measured runners get the shared one below.
OWN_SWEEP_ALLOWED = {"smoke_clean_account.sh"}

# A `sweep` in command position: start of line, after a pipe/and-list/semicolon/subshell
# opener. `join_sweep`, `mtp_sweep`, `sweep_hit`, `pre-sweep` and `sweep.sh` are words, not
# this command, and quoted text is stripped before this runs.
_SWEEP_COMMAND = re.compile(r"(?:^|[|;&(]|\|\||&&)\s*sweep(?=[\s|;&]|$)")


def _commands(text: str) -> list[str]:
    """Each line of *text* with its quoted strings removed and its comment lines dropped."""
    lines = []
    for raw in text.splitlines():
        stripped = re.sub(r"'[^']*'|\"[^\"]*\"", "", raw)
        if stripped.lstrip().startswith("#"):
            continue
        lines.append(stripped)
    return lines


def _script_texts() -> list[tuple[str, str]]:
    return [(path.name, path.read_text()) for path in sorted(SCRIPTS.glob("*.sh"))]


def test_the_sweep_signals_every_resident_engine_and_nothing_else(monkeypatch):
    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(
        runtimes,
        "resident_engines",
        lambda: (("optiq", 4242, (8080,)), ("osaurus", 7311, None)),
    )
    monkeypatch.setattr(runtimes, "_process_alive", lambda pid: True)
    monkeypatch.setattr(
        runtimes, "_signal_process", lambda pid, sig: killed.append((pid, sig))
    )
    monkeypatch.setattr(runtimes, "_await_exit", lambda pid, timeout_s: True)

    lines = runtimes.sweep_resident_engines()

    assert [pid for pid, _sig in killed] == [4242, 7311], (
        f"the sweep signalled {killed}, not exactly the resident engines"
    )
    assert {sig for _pid, sig in killed} == {signal.SIGKILL}, (
        "these instances ignore SIGTERM; the old sweeps used SIGKILL and so must this one"
    )
    assert len(lines) == 2, lines
    assert "4242" in lines[0] and "7311" in lines[1], lines


def test_a_user_dev_server_and_osaurus_mcp_survive_the_sweep(monkeypatch):
    """AC-1: the pids come from the engine scan, so neither is ever signalled.

    A non-engine listener on a default port is a dev server, and `osaurus mcp` is Jason's
    long-running client: both survive, because `_engine_of` is the one definition of an engine.
    """
    from types import SimpleNamespace

    venv_python = "/Users/x/.venvs/a/bin/python"
    procs = {
        500: ("/usr/local/bin/node", "node dev-server.js", (8000,)),
        600: ("/opt/homebrew/bin/osaurus", "osaurus mcp", ()),
        700: (venv_python, f"{venv_python} -m mlx_lm.server --port 8081", (8081,)),
    }

    def fake_run(command, timeout_s):
        if command[0] == runtimes.PS:
            index = {"comm": 0, "args": 1}[command[-1].split(",")[1].rstrip("=")]
            return SimpleNamespace(
                stdout="".join(f"{pid:>6} {p[index]}\n" for pid, p in procs.items()),
                returncode=0,
            )
        pids = {int(p) for p in command[command.index("-p") + 1].split(",")}
        out = "".join(
            f"p{pid}\n" + "".join(f"n127.0.0.1:{port}\n" for port in procs[pid][2])
            for pid in sorted(pids)
            if procs[pid][2]
        )
        return SimpleNamespace(stdout=out, returncode=0 if out else 1)

    killed: list[int] = []
    monkeypatch.setattr(runtimes, "_run", fake_run)
    monkeypatch.setattr(runtimes, "_process_alive", lambda pid: True)
    monkeypatch.setattr(runtimes, "_signal_process", lambda pid, sig: killed.append(pid))
    monkeypatch.setattr(runtimes, "_await_exit", lambda pid, timeout_s: True)

    runtimes.sweep_resident_engines()

    assert killed == [700], f"the sweep signalled {killed}, not just the one engine"


def test_a_ps_that_cannot_be_read_stops_the_sweep(monkeypatch):
    def unreadable():
        raise runtimes.RuntimeStartError("could not inspect running processes")

    monkeypatch.setattr(runtimes, "resident_engines", unreadable)

    with pytest.raises(runtimes.RuntimeStartError, match="could not inspect"):
        runtimes.sweep_resident_engines()


def test_a_pid_gone_before_the_sweep_is_a_line_not_an_error(monkeypatch):
    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(runtimes, "resident_engines", lambda: (("optiq", 4242, ()),))
    monkeypatch.setattr(runtimes, "_process_alive", lambda pid: False)
    monkeypatch.setattr(
        runtimes, "_signal_process", lambda pid, sig: killed.append((pid, sig))
    )

    lines = runtimes.sweep_resident_engines()

    assert killed == [], "a pid that has gone must not be signalled"
    assert len(lines) == 1 and "4242" in lines[0] and "gone" in lines[0], lines


def test_a_pid_this_user_cannot_signal_is_a_line_not_an_error(monkeypatch):
    def denied(pid, sig):
        raise runtimes.RuntimeStopError(f"permission denied signalling process {pid}")

    monkeypatch.setattr(runtimes, "resident_engines", lambda: (("vmlx", 8000, (8000,)),))
    monkeypatch.setattr(runtimes, "_process_alive", lambda pid: True)
    monkeypatch.setattr(runtimes, "_signal_process", denied)

    lines = runtimes.sweep_resident_engines()

    assert len(lines) == 1, lines
    assert "8000" in lines[0] and "permission denied" in lines[0], lines


def test_an_engine_that_survives_sigkill_fails_the_sweep(monkeypatch):
    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(
        runtimes,
        "resident_engines",
        lambda: (("optiq", 4242, (8080,)), ("omlx", 8100, (8100,))),
    )
    monkeypatch.setattr(runtimes, "_process_alive", lambda pid: True)
    monkeypatch.setattr(
        runtimes, "_signal_process", lambda pid, sig: killed.append((pid, sig))
    )
    monkeypatch.setattr(runtimes, "_await_exit", lambda pid, timeout_s: False)

    with pytest.raises(runtimes.RuntimeStopError, match="alive"):
        runtimes.sweep_resident_engines()

    assert [pid for pid, _sig in killed] == [4242, 8100], (
        "a survivor is reported after the sweep has tried every reported engine"
    )


def test_no_script_defines_its_own_sweep():
    offenders = [
        name
        for name, text in _script_texts()
        if name not in OWN_SWEEP_ALLOWED | {"sweep.sh"}
        and re.search(r"^\s*sweep\(\)", text, re.M)
    ]
    assert not offenders, (
        f"{offenders} carry their own sweep(); one definition lives in scripts/sweep.sh"
    )


def test_every_caller_sources_sweep_sh():
    pin = dict(_script_texts())["osaurus-pin.sh"]
    missing = []
    for name, text in _script_texts():
        if name == "sweep.sh" or name in OWN_SWEEP_ALLOWED:
            continue
        if not any(_SWEEP_COMMAND.search(line) for line in _commands(text)):
            continue
        direct = ". \"$(dirname \"$0\")/sweep.sh\"" in text
        through_pin = (
            ". \"$(dirname \"$0\")/osaurus-pin.sh\"" in text
            and ". \"$(dirname \"$0\")/sweep.sh\"" in pin
        )
        if not (direct or through_pin):
            missing.append(name)
    assert not missing, f"{missing} call sweep without sourcing scripts/sweep.sh"


def test_the_osaurus_pin_traps_sweep_is_the_shared_one():
    pin = (SCRIPTS / "osaurus-pin.sh").read_text()
    trap_lines = [line for line in pin.splitlines() if line.lstrip().startswith("trap ")]
    assert any("sweep;" in line for line in trap_lines), (
        "osaurus-pin.sh's signal trap no longer sweeps"
    )
    assert ". \"$(dirname \"$0\")/sweep.sh\"" in pin, (
        "the trap's sweep would be undefined unless the caller happened to source sweep.sh"
    )


def test_no_bare_sweep_outside_a_trap():
    """Every non-trap call is `sweep || exit 1`.

    A sweep that could not confirm the machine clear must stop the run: one model resident is
    a hard rule, and a rejected sweep that only printed would start the next column on a
    machine still holding the last one's weights. Inside a trap the call stays bare, because an
    `exit` there would skip osaurus-pin.sh's restore.
    """
    offenders = []
    for name, text in _script_texts():
        if name in OWN_SWEEP_ALLOWED:
            continue
        for line in _commands(text):
            if not _SWEEP_COMMAND.search(line):
                continue
            if "sweep || exit 1" not in line:
                offenders.append(f"{name}: {line.strip()}")
    assert not offenders, offenders


def test_sweep_sh_never_exits():
    """An `exit` here runs inside osaurus-pin.sh's trap and skips the Osaurus restore."""
    body = "\n".join(_commands(SWEEP.read_text()))
    assert not re.search(r"(?:^|[|;&({]\s*)exit\b", body, re.M), body


def test_sweep_sh_requires_py_and_calls_the_tested_function():
    text = SWEEP.read_text()
    assert ': "${PY:?sweep.sh needs PY}"' in text
    assert "runtimes.sweep_resident_engines" in text, (
        "sweep.sh must call the one Python kill loop rather than one of its own"
    )
    assert "lsof -ti" not in text and "kill -9" not in text, (
        "sweep.sh must not kill by port"
    )


def test_no_script_kills_a_listener_by_port():
    offenders = [name for name, text in _script_texts() if "lsof -ti:" in text]
    assert not offenders, (
        f"{offenders} still kill whatever holds a default port, a user's dev server included"
    )


def test_every_script_parses():
    for path in sorted(SCRIPTS.glob("*.sh")):
        result = subprocess.run(
            ["sh", "-n", str(path)], capture_output=True, text=True
        )
        assert result.returncode == 0, f"{path.name}: {result.stderr}"
