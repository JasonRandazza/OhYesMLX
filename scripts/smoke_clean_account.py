#!/usr/bin/env python3
"""The client half of the 045-03 clean-account smoke, run as the throwaway user.

It spawns ``ohyesmlx app`` the way the Swift client will -- stdin held open, stdout the only
place the launch line is read from -- and then drives every API surface a first-time user
reaches: the four GETs, two hash-pinned installs, one download, one quickbench run, an
eviction, and the stdin-EOF shutdown. Everything it observes is one ``checks`` entry, and it
never stops at a failure: a check whose prerequisite did not pass is a SKIP naming it.

Run by ``scripts/smoke_clean_account.sh``, never by hand on a real account. The pure parts
(launch-line parse, SSE parse, the ``/Users/jrazz`` scan, the pip-argv check and the result
bookkeeping) are unit-tested in ``tests/test_smoke_clean_account.py``.
"""

from __future__ import annotations

import argparse
import datetime
import http.client
import json
import os
import pathlib
import re
import select
import socket
import subprocess
import sys
import threading
import time

# AC-2: the app must write its launch line and nothing else, and a child that writes nothing
# must not hang the client, so the first read is bounded.
LAUNCH_TIMEOUT_S = 60

# The order's bounds. An install is two pip steps at most; a download is 0.35 GB; a
# quickbench is one light cell per installed engine.
INSTALL_TIMEOUT_S = 1800
DOWNLOAD_TIMEOUT_S = 900
QUICKBENCH_TIMEOUT_S = 1800

# AC-6: stdin EOF must be answered within this long.
SHUTDOWN_TIMEOUT_S = 10

APP_SUPPORT = pathlib.Path.home() / "Library" / "Application Support" / "OhYesMLX"


class LaunchLineError(ValueError):
    """The child's stdout is not exactly one launch line with exactly ``port`` and ``token``."""


# ---------------------------------------------------------------------------
# Pure helpers -- unit-tested, no network, no subprocess
# ---------------------------------------------------------------------------


def parse_launch(text: str) -> tuple[int, str]:
    """The launch line, from the child's stdout text (AC-2, P5-2).

    Exactly one non-blank line, a JSON object with exactly the two keys, an integer ``port``
    that is a legal TCP port and a non-empty string ``token``. Anything else is a refusal:
    a second stdout line would be a module printing onto the pipe the client reads, and a
    missing key would make the client invent one.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) != 1:
        raise LaunchLineError(
            f"stdout must carry exactly one line, got {len(lines)}: {lines!r}"
        )
    try:
        payload = json.loads(lines[0])
    except ValueError as error:
        raise LaunchLineError(f"the launch line is not JSON: {error}") from error
    if not isinstance(payload, dict):
        raise LaunchLineError("the launch line is not a JSON object")
    missing = sorted({"port", "token"} - set(payload))
    extra = sorted(set(payload) - {"port", "token"})
    if missing:
        raise LaunchLineError(f"the launch line is missing {', '.join(missing)}")
    if extra:
        raise LaunchLineError(f"the launch line carries unexpected {', '.join(extra)}")
    port, token = payload["port"], payload["token"]
    if isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536:
        raise LaunchLineError(f"port must be an integer 1..65535, got {port!r}")
    if not isinstance(token, str) or not token:
        raise LaunchLineError(f"token must be a non-empty string, got {token!r}")
    return port, token


def parse_ports(text: str) -> tuple[int, ...]:
    """The AC-1 port list, from the ``.sh``'s ``PORTS`` -- the one definition of it."""
    return tuple(int(token) for token in text.split())


def _sse_frame(block: str) -> dict | None:
    """One SSE block as ``{"id", "event", "data"}``, or None for a keepalive-only block."""
    data: list[str] = []
    frame_id = None
    event = None
    for line in block.splitlines():
        if not line or line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "data":
            data.append(value)
        elif field == "id":
            frame_id = int(value) if value.isdigit() else value
        elif field == "event":
            event = value
    if not data:
        return None
    return {"id": frame_id, "event": event, "data": "\n".join(data)}


def parse_sse(text: str) -> tuple[list[dict], str]:
    """The complete SSE frames in *text*, and the unterminated remainder to feed next time.

    A frame ends at a blank line; ``: keepalive`` comments carry no data and are dropped; a
    ``data:`` field continued over several lines is joined with newlines, as the framing
    pins.
    """
    frames: list[dict] = []
    rest = text
    while True:
        match = re.search(r"\r?\n\r?\n", rest)
        if match is None:
            return frames, rest
        block = rest[: match.start()]
        rest = rest[match.end() :]
        frame = _sse_frame(block)
        if frame is not None:
            frames.append(frame)


def forbid_hits(text: str, needle: str) -> list[str]:
    """Every line of *text* carrying *needle*: the one definition of the leak scan."""
    if not needle:
        return []
    return [line for line in text.splitlines() if needle in line]


def _pip_argv(plan) -> list[str] | None:
    """The plan's pip install command as a list of strings, or None when it has none."""
    if not isinstance(plan, dict):
        return None
    steps = plan.get("steps")
    if not isinstance(steps, list):
        return None
    for step in steps:
        command = step.get("command") if isinstance(step, dict) else None
        if isinstance(command, list) and "pip" in command and "install" in command:
            return [str(token) for token in command]
    return None


def _flag_value(argv: list[str], flag: str) -> str | None:
    if flag not in argv:
        return None
    index = argv.index(flag)
    return argv[index + 1] if index + 1 < len(argv) else None


def pip_argv_problems(plan, engine: str, package_dir: str) -> list[str]:
    """Why *plan*'s pip step is not the hash-pinned one this app promises; empty means it is.

    AC-3/AC-4: ``--require-hashes`` is only a pin when the file names every requirement with
    a hash, ``--only-binary :all:`` keeps pip off sdists (which hash-checking does not
    cover), ``--isolated`` keeps a user's pip config out of the index choice, ``--no-deps``
    makes the file the whole closure so pip resolves nothing of its own, and the
    constraints file must be the one the installed package ships rather than any file the
    user can edit. The ``--no-deps``/pygame reasoning is at ``ohyesmlx.engines``
    (``_command_plan``).
    """
    problems: list[str] = []
    if not isinstance(plan, dict) or plan.get("kind") != "command":
        return [f"{engine}: the install plan is not a command plan"]
    argv = _pip_argv(plan)
    if argv is None:
        return [f"{engine}: the plan has no pip install step"]
    for flag in ("--require-hashes", "--isolated", "--no-deps"):
        if flag not in argv:
            problems.append(f"{engine}: the pip step has no {flag}")
    if _flag_value(argv, "--only-binary") != ":all:":
        problems.append(f"{engine}: the pip step has no --only-binary :all:")
    if "--no-binary" in argv:
        problems.append(f"{engine}: the pip step has --no-binary; every engine is wheels-only")
    constraints = _flag_value(argv, "-r")
    if constraints is None:
        problems.append(f"{engine}: the pip step has no -r constraints file")
    elif not constraints.endswith(".txt"):
        problems.append(f"{engine}: the constraints file is not a .txt: {constraints}")
    else:
        root = os.path.abspath(package_dir)
        named = os.path.abspath(constraints)
        if os.path.commonpath([root, named]) != root:
            problems.append(f"{engine}: {constraints} is not under {package_dir}")
    return problems


def add_check(checks: list[dict], check_id: str, status: str, evidence) -> dict:
    """Append one result entry; the only place ``checks`` grows."""
    if status not in ("PASS", "FAIL", "SKIP"):
        raise ValueError(f"status must be PASS, FAIL or SKIP, got {status!r}")
    entry = {"id": check_id, "status": status, "evidence": evidence}
    checks.append(entry)
    return entry


def update_check(entry: dict, status: str, evidence) -> dict:
    """Rewrite one entry in place: the leak scan keeps gathering after AC-3 has been recorded."""
    if status not in ("PASS", "FAIL", "SKIP"):
        raise ValueError(f"status must be PASS, FAIL or SKIP, got {status!r}")
    entry["status"] = status
    entry["evidence"] = evidence
    return entry


def gate(checks: list[dict], *prereq_ids: str) -> str | None:
    """None when every prerequisite passed, else the SKIP reason naming the first that did not."""
    by_id = {entry["id"]: entry for entry in checks}
    for check_id in prereq_ids:
        entry = by_id.get(check_id)
        if entry is None or entry["status"] != "PASS":
            return f"skipped: {check_id} did not pass"
    return None


def counts(checks: list[dict]) -> dict[str, dict[str, int]]:
    """PASS/FAIL/SKIP tallies keyed by the AC prefix of each check id."""
    tally: dict[str, dict[str, int]] = {}
    for entry in checks:
        group = entry["id"].split(".", 1)[0]
        bucket = tally.setdefault(group, {"PASS": 0, "FAIL": 0, "SKIP": 0})
        bucket[entry["status"]] += 1
    return tally


def summary_lines(tally: dict[str, dict[str, int]]) -> list[str]:
    """One line per AC: the PASS/FAIL/SKIP count the coordinator reads first."""
    return [
        f"{group}: {bucket['PASS']} PASS {bucket['FAIL']} FAIL {bucket['SKIP']} SKIP"
        for group, bucket in sorted(tally.items())
    ]


def job_failed(events: list[dict]) -> str | None:
    """The last error code a job's stream carried, or None when it ended clean (AC-4/AC-5)."""
    code = None
    for event in events:
        if event.get("type") == "error":
            payload = event.get("payload") or {}
            code = payload.get("code") or event.get("message") or "error"
    return code


def hub_repo_dir(model: str) -> pathlib.Path:
    """Where a repo id lands in the HF cache (AC-1/AC-5): ``fetch``'s one definition of it."""
    from ohyesmlx import fetch

    return pathlib.Path(fetch._repo_dir(fetch.default_cache_dir(), model))


def cell_outcomes(events: list[dict]) -> list[dict]:
    """Per-engine cell outcomes from a quickbench stream, one entry per engine, sorted by name.

    Both sources are read because the stream carries them at different moments: each cell's
    final ``progress`` names the engine and its status as the run reaches it, and the closing
    ``result`` event's summary is the authoritative copy. The summary wins where the two
    disagree, so a cell that was still ``running`` in a progress event reports what it ended as.
    """
    reached: dict[str, dict] = {}
    for event in events:
        payload = event.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        kind = event.get("type")
        if kind == "progress" and isinstance(payload.get("engine"), str):
            if payload.get("status"):
                reached[payload["engine"]] = {
                    "engine": payload["engine"],
                    "status": payload["status"],
                }
            elif payload.get("skipped"):
                reached[payload["engine"]] = {
                    "engine": payload["engine"],
                    "status": "SKIPPED",
                    "reason": payload["skipped"],
                }
        elif kind == "result":
            for stage in ("stage_a", "stage_b"):
                block = payload.get(stage)
                if not isinstance(block, dict):
                    continue
                for cell in block.get("cells") or []:
                    if not isinstance(cell, dict) or not cell.get("engine"):
                        continue
                    name = cell["engine"] if stage == "stage_a" else f"stage_b:{cell['engine']}"
                    reached[name] = {
                        "engine": name,
                        "status": cell.get("status"),
                        "reason": cell.get("reason"),
                    }
    return [reached[name] for name in sorted(reached)]


# ---------------------------------------------------------------------------
# The live client -- run as oymlxtest, against 127.0.0.1 only
# ---------------------------------------------------------------------------


class Client:
    """One HTTP/1.0 request per connection, with the token and the leak scan in one place."""

    def __init__(self, port: int, token: str, forbid: str):
        self.port = port
        self.token = token
        self.forbid = forbid
        self.leaks: list[str] = []

    def _scan(self, text: str) -> None:
        self.leaks.extend(forbid_hits(text, self.forbid))

    def request(self, method: str, path: str, body=None, *, authorized=True):
        """(status, body text) for one request; every body is leak-scanned and never aborted."""
        headers = {"Accept": "application/json"}
        if authorized:
            headers["Authorization"] = f"Bearer {self.token}"
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        try:
            connection.request(method, path, body=data, headers=headers)
            response = connection.getresponse()
            text = response.read().decode("utf-8", "replace")
            status = response.status
        finally:
            connection.close()
        self._scan(text)
        return status, text

    def post_job(self, kind: str, name_key: str, name: str, **flags):
        """``POST /jobs`` with the pinned body, or the refusal as (None, status, body)."""
        args = {name_key: name, "confirmed": True, **flags}
        status, text = self.request("POST", "/jobs", {"kind": kind, "args": args})
        if status != 202:
            return None, status, text
        try:
            return json.loads(text)["job_id"], status, text
        except (ValueError, KeyError, TypeError):
            return None, status, text

    def follow(self, job_id: str, timeout_s: float):
        """(events, seconds, problem): the whole SSE stream of one job, to its ``done``.

        ``seconds`` is the client-observed interval from the first frame to the last, which is
        the only duration this smoke can honestly record (the backend records none).
        """
        events: list[dict] = []
        buffer = ""
        first = last = None
        problem = None
        deadline = time.monotonic() + timeout_s
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            connection.request(
                "GET",
                f"/jobs/{job_id}/events",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "text/event-stream",
                },
            )
            response = connection.getresponse()
            if response.status != 200:
                body = response.read().decode("utf-8", "replace")
                self._scan(body)
                return events, None, f"events answered {response.status}: {body}"
            finished = False
            while not finished:
                if time.monotonic() > deadline:
                    problem = f"no done event within {timeout_s:.0f} s"
                    break
                try:
                    chunk = response.read1(65536)
                except (TimeoutError, socket.timeout):
                    continue
                if not chunk:
                    problem = "the events stream closed before done"
                    break
                arrived = time.monotonic()
                buffer += chunk.decode("utf-8", "replace")
                frames, buffer = parse_sse(buffer)
                for frame in frames:
                    # AC-3's leak scan runs on the frame's own text, which is complete only
                    # once its blank line has arrived -- a chunk boundary splits nothing here.
                    self._scan(frame["data"])
                    try:
                        event = json.loads(frame["data"])
                    except ValueError:
                        problem = f"an event frame was not JSON: {frame['data']}"
                        finished = True
                        break
                    events.append(event)
                    if first is None:
                        first = arrived
                    last = arrived
                    if event.get("type") == "done":
                        finished = True
        except OSError as error:
            problem = f"the events stream failed: {error}"
        finally:
            connection.close()
        seconds = None if first is None else round(last - first, 3)
        return events, seconds, problem


def _outcome(events, seconds, problem) -> dict:
    return {
        "events": len(events),
        "seconds": seconds,
        "problem": problem,
        "error": job_failed(events),
        "last": (events[-1] if events else None),
    }


def _drain(stream, sink: list[str]) -> None:
    """Hold the child's stdout open for the whole run and record any line after the launch one."""
    try:
        for line in iter(stream.readline, b""):
            text = line.decode("utf-8", "replace").rstrip("\n")
            if text.strip():
                sink.append(text)
    except (OSError, ValueError):
        pass


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) != 0


def read_launch_line(stream, timeout_s: float) -> bytes | None:
    """The child's first stdout line; None when it wrote none before *timeout_s* (AC-2).

    Read from the raw fd, a byte at a time, so nothing is buffered ahead of the drain thread
    and any line after the launch one is still there for it; bounded by ``select`` so a child
    that stays alive without writing cannot hang the client.
    """
    fd = stream.fileno()
    deadline = time.monotonic() + timeout_s
    buffer = b""
    while not buffer.endswith(b"\n"):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        ready, _, _ = select.select([fd], [], [], remaining)
        if not ready:
            return None
        chunk = os.read(fd, 1)
        if not chunk:
            return buffer
        buffer += chunk
    return buffer


def _mode(path: pathlib.Path) -> int | None:
    try:
        return os.stat(path).st_mode & 0o777
    except OSError:
        return None


def check_ac2(checks, port, token, app_support, launch_error):
    """AC-2: the launch line is the only stdout, and ``~/Library/.../OhYesMLX`` is 0700."""
    if launch_error is not None:
        entry = add_check(checks, "AC-2.launch_line", "FAIL", launch_error)
    else:
        entry = add_check(
            checks,
            "AC-2.launch_line",
            "PASS",
            {"port": port, "token_read": bool(token), "line": "one line, port and token only"},
        )
    mode = _mode(app_support)
    add_check(
        checks,
        "AC-2.app_support_mode",
        "PASS" if mode == 0o700 else "FAIL",
        {"path": str(app_support), "mode": None if mode is None else oct(mode)},
    )
    return entry


def check_ac3(client, model, checks):
    """AC-3: the four read endpoints describe a fresh Mac, and no body names Jason's home."""
    import ohyesmlx

    package_dir = str(pathlib.Path(ohyesmlx.__file__).resolve().parent)

    status, body = client.request("GET", "/hardware")
    try:
        hardware = json.loads(body)
    except ValueError:
        hardware = {}
    if not isinstance(hardware, dict):
        hardware = {}
    keys = (
        "supported",
        "unsupported_reason",
        "chip",
        "family",
        "tier",
        "cpu_cores",
        "gpu_cores",
        "ram_bytes",
        "macos",
        "disk_free_bytes",
        "volumes",
        "model_budget_bytes",
    )
    missing = [key for key in keys if key not in hardware]
    add_check(
        checks,
        "AC-3.hardware",
        "PASS" if status == 200 and not missing else "FAIL",
        {"status": status, "missing": missing, "chip": hardware.get("chip"), "ram_bytes": hardware.get("ram_bytes")},
    )

    status, body = client.request("GET", "/engines")
    try:
        engines_list = json.loads(body)
    except ValueError:
        engines_list = []
    by_name = {entry.get("name"): entry for entry in engines_list if isinstance(entry, dict)}
    problems: dict[str, list[str]] = {}
    recorded: dict[str, dict] = {}
    for name in ("mlxlm", "optiq"):
        entry = by_name.get(name)
        recorded[name] = {
            "present": entry is not None,
            "installed": (entry or {}).get("installed"),
            "version": (entry or {}).get("version"),
            "install_plan_keys": sorted((entry or {}).get("install") or {}),
        }
        plan = (entry or {}).get("install")
        if (entry or {}).get("installed") is not False:
            problems[name] = [f"{name}: /engines does not report it not installed"]
        elif plan is None:
            problems[name] = [f"{name}: no install plan"]
        else:
            problems[name] = pip_argv_problems(plan, name, package_dir)
    for name in ("osaurus", "omlx", "vmlx"):
        entry = by_name.get(name) or {}
        recorded[name] = {"present": bool(entry), "installed": entry.get("installed")}
    add_check(
        checks,
        "AC-3.engines_plans",
        "PASS" if status == 200 and not any(problems.values()) else "FAIL",
        {"status": status, "problems": problems, "engines": recorded},
    )

    status, body = client.request("GET", "/recommendations")
    try:
        recommendations = json.loads(body)
    except ValueError:
        recommendations = {}
    add_check(
        checks,
        "AC-3.recommendations",
        "PASS" if status == 200 and {"picks", "excluded", "unsupported_reason"} <= set(recommendations) else "FAIL",
        {
            "status": status,
            "picks": len(recommendations.get("picks") or []),
            "excluded": len(recommendations.get("excluded") or []),
            "unsupported_reason": recommendations.get("unsupported_reason"),
        },
    )

    status, body = client.request("GET", "/quickbench/plan?repo=" + model)
    try:
        refusal = (json.loads(body) or {}).get("error") or {}
    except (ValueError, AttributeError):
        refusal = {}
    add_check(
        checks,
        "AC-3.quickbench_plan_before_download",
        "PASS"
        if status == 400 and refusal.get("code") == "bad_args" and "download it first" in body
        else "FAIL",
        {"status": status, "body": body},
    )

    status, body = client.request("GET", "/hardware", authorized=False)
    add_check(
        checks,
        "AC-3.token_required",
        "PASS" if status == 401 else "FAIL",
        {"status": status, "body": body},
    )

    return add_check(
        checks,
        "AC-3.no_host_paths",
        "PASS" if not client.leaks else "FAIL",
        client.leaks or f"no occurrence of {client.forbid}",
    )


def check_ac4(client, checks):
    """AC-4: both hash-pinned installs succeed and land in the lab path file."""
    import ohyesmlx.engines as engines_module

    for engine in ("mlxlm", "optiq"):
        job_id, status, body = client.post_job("install", "engine", engine)
        if job_id is None:
            add_check(
                checks,
                f"AC-4.install.{engine}",
                "FAIL",
                {"status": status, "body": body},
            )
            continue
        events, seconds, problem = client.follow(job_id, INSTALL_TIMEOUT_S)
        outcome = _outcome(events, seconds, problem)
        ok = problem is None and outcome["error"] is None
        add_check(checks, f"AC-4.install.{engine}", "PASS" if ok else "FAIL", outcome)

    paths = {}
    lab_file = APP_SUPPORT / "lab-paths.json"
    try:
        paths = json.loads(lab_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        paths = {}
        named_problem = str(error)
    else:
        named_problem = None
    named = {name: paths.get(name) if isinstance(paths, dict) else None for name in ("mlxlm", "optiq")}
    add_check(
        checks,
        "AC-4.lab_paths_named",
        "PASS" if all(named.values()) and named_problem is None else "FAIL",
        {"path": str(lab_file), "engines": named, "problem": named_problem},
    )

    checked: dict[str, str] = {}
    for name, path in named.items():
        if not path:
            checked[name] = "no path recorded"
            continue
        try:
            engines_module.check_lab_dir(path)
        except ValueError as error:
            checked[name] = f"refused: {error}"
        else:
            checked[name] = "ok"
    add_check(
        checks,
        "AC-4.check_lab_dir",
        "PASS" if all(value == "ok" for value in checked.values()) else "FAIL",
        checked,
    )

    status, body = client.request("GET", "/engines")
    try:
        engines_list = json.loads(body)
    except ValueError:
        engines_list = []
    installed = {
        entry.get("name"): entry.get("installed") for entry in engines_list if isinstance(entry, dict)
    }
    add_check(
        checks,
        "AC-4.engines_installed",
        "PASS" if status == 200 and installed.get("mlxlm") is True and installed.get("optiq") is True else "FAIL",
        {"status": status, "installed": installed},
    )


def check_ac5(client, model, checks):
    """AC-5: download, a real quickbench plan, a confirmed run, then the eviction."""
    job_id, status, body = client.post_job("download", "repo", model)
    if job_id is None:
        add_check(checks, "AC-5.download", "FAIL", {"status": status, "body": body})
    else:
        events, seconds, problem = client.follow(job_id, DOWNLOAD_TIMEOUT_S)
        outcome = _outcome(events, seconds, problem)
        outcome["repo_dir"] = str(hub_repo_dir(model))
        add_check(
            checks,
            "AC-5.download",
            "PASS" if problem is None and outcome["error"] is None else "FAIL",
            outcome,
        )

    download_gate = gate(checks, "AC-5.download")
    if download_gate is not None:
        add_check(checks, "AC-5.quickbench_plan", "SKIP", download_gate)
    else:
        status, body = client.request("GET", "/quickbench/plan?repo=" + model)
        try:
            shown = json.loads(body)
        except ValueError:
            shown = {}
        if not isinstance(shown, dict):
            shown = {}
        keys = ("repo", "format", "stage_a", "stage_b", "download_bytes", "osaurus", "estimate_s")
        missing = [key for key in keys if key not in shown]
        engines_planned = [
            entry.get("engine")
            for entry in shown.get("stage_a") or []
            if isinstance(entry, dict)
        ]
        add_check(
            checks,
            "AC-5.quickbench_plan",
            "PASS" if status == 200 and not missing else "FAIL",
            {
                "status": status,
                "missing": missing,
                "stage_a": engines_planned,
                "estimate_s": shown.get("estimate_s"),
                "body": None if status == 200 else body[:2000],
            },
        )

    plan_gate = gate(checks, "AC-5.quickbench_plan")
    if plan_gate is not None:
        add_check(checks, "AC-5.quickbench", "SKIP", plan_gate)
        add_check(checks, "AC-5.quickbench_cells", "SKIP", plan_gate)
    else:
        job_id, status, body = client.post_job("quickbench", "repo", model, osaurus=False)
        if job_id is None:
            add_check(checks, "AC-5.quickbench", "FAIL", {"status": status, "body": body})
            add_check(
                checks, "AC-5.quickbench_cells", "SKIP", "skipped: AC-5.quickbench did not pass"
            )
        else:
            events, seconds, problem = client.follow(job_id, QUICKBENCH_TIMEOUT_S)
            outcome = _outcome(events, seconds, problem)
            outcome["stream"] = events  # evidence: the cell parse below reads only these
            add_check(
                checks,
                "AC-5.quickbench",
                "PASS" if problem is None and outcome["error"] is None else "FAIL",
                outcome,
            )
            cells = cell_outcomes(events)
            passed = {
                cell["engine"] for cell in cells if cell["status"] == "PASS"
            }
            add_check(
                checks,
                "AC-5.quickbench_cells",
                "PASS" if {"mlxlm", "optiq"} <= passed else "FAIL",
                cells or "no per-engine cell outcome on the stream",
            )

    job_id, status, body = client.post_job("evict", "repo", model)
    if job_id is None:
        add_check(checks, "AC-5.evict", "FAIL", {"status": status, "body": body})
    else:
        events, seconds, problem = client.follow(job_id, DOWNLOAD_TIMEOUT_S)
        outcome = _outcome(events, seconds, problem)
        add_check(
            checks,
            "AC-5.evict",
            "PASS" if problem is None and outcome["error"] is None else "FAIL",
            outcome,
        )

    directory = hub_repo_dir(model)
    try:
        ledger = json.loads((APP_SUPPORT / "fetched.json").read_text(encoding="utf-8"))
        entries = sorted(ledger.get("repos") or {}) if isinstance(ledger, dict) else []
    except (OSError, ValueError) as error:
        entries = []
        ledger_problem = str(error)
    else:
        ledger_problem = None
    gone = (not directory.exists()) and model not in entries and ledger_problem is None
    add_check(
        checks,
        "AC-5.evicted",
        "PASS" if gone else "FAIL",
        {
            "repo_dir": str(directory),
            "present": directory.exists(),
            "ledger_entries": entries,
            "ledger_problem": ledger_problem,
        },
    )


def check_ac6(checks, process, stdin_closed_error, ports):
    """AC-6: closing stdin ends the child 0 within 10 s and frees every port."""
    code = None
    duration = None
    problem = stdin_closed_error
    if stdin_closed_error is None:
        started = time.monotonic()
        try:
            code = process.wait(timeout=SHUTDOWN_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            problem = f"still running {SHUTDOWN_TIMEOUT_S} s after stdin closed"
            process.kill()
            process.wait()
        duration = round(time.monotonic() - started, 3)
    add_check(
        checks,
        "AC-6.exit",
        "PASS" if problem is None and code == 0 else "FAIL",
        {"exit": code, "seconds": duration, "problem": problem},
    )
    held = [port for port in ports if not _port_free(port)]
    add_check(
        checks,
        "AC-6.ports_free",
        "PASS" if not held else "FAIL",
        {"held": held} if held else {"ports": list(ports)},
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="045-03 clean-account smoke client")
    parser.add_argument("--out", required=True, help="results and stderr log directory")
    parser.add_argument("--head", required=True, help="the git revision the wheel was built from")
    parser.add_argument("--forbid", required=True, help="a string no response may contain")
    parser.add_argument("--model", required=True, help="the catalog repo id to download")
    parser.add_argument(
        "--ports", required=True, help="AC-1's ports, space-separated, from the .sh's PORTS"
    )
    args = parser.parse_args(argv)
    ports = parse_ports(args.ports)

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    checks: list[dict] = []

    binary = os.path.join(sys.prefix, "bin", "ohyesmlx")
    log_path = out / f"app-stderr-{stamp}.log"
    extras: list[str] = []
    launch_error = None
    process = None
    with open(log_path, "wb") as log:
        try:
            process = subprocess.Popen(
                [binary, "app"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=log,
            )
        except OSError as error:
            launch_error = f"could not start {binary}: {error}"
    if process is None:
        check_ac2(checks, None, None, APP_SUPPORT, launch_error)
        reason = gate(checks, "AC-2.launch_line")
        for group in ("AC-3", "AC-4", "AC-5", "AC-6"):
            add_check(checks, group, "SKIP", reason)
        add_check(checks, "AC-3.no_host_paths", "SKIP", reason)
        return _finish(out, stamp, args, started, checks)

    launch_line = read_launch_line(process.stdout, LAUNCH_TIMEOUT_S)
    if launch_line is None:
        launch_error = f"no launch line within {LAUNCH_TIMEOUT_S} s"
        port, token = None, None
    else:
        try:
            port, token = parse_launch(launch_line.decode("utf-8", "replace"))
        except LaunchLineError as error:
            launch_error = str(error)
            port, token = None, None
    drain = threading.Thread(target=_drain, args=(process.stdout, extras), daemon=True)
    drain.start()
    launch_entry = check_ac2(checks, port, token, APP_SUPPORT, launch_error)

    if launch_error is not None:
        reason = gate(checks, "AC-2.launch_line")
        for group in ("AC-3", "AC-4", "AC-5"):
            add_check(checks, group, "SKIP", reason)
        add_check(checks, "AC-3.no_host_paths", "SKIP", reason)
        _shut_down(checks, process, None, ports)
        return _finish(out, stamp, args, started, checks)

    # AC-6's own promise holds whatever happens in between: an exception in the checks must not
    # leave the child holding a port with a model resident, so stdin is closed from a finally
    # and the client's death (the .sh trap's first sweep) is never the only shutdown path.
    client = Client(port, token, args.forbid)
    try:
        leak_entry = check_ac3(client, args.model, checks)
        check_ac4(client, checks)
        check_ac5(client, args.model, checks)
    except Exception as error:  # noqa: BLE001 -- recorded, then shutdown still runs
        crash = f"{type(error).__name__}: {error}"
        add_check(checks, "AC-3.client_exception", "FAIL", crash)
        leak_entry = next(
            (entry for entry in checks if entry["id"] == "AC-3.no_host_paths"), None
        )
        if leak_entry is None:
            leak_entry = add_check(checks, "AC-3.no_host_paths", "SKIP", crash)
    finally:
        _shut_down(checks, process, None, ports)
        drain.join(timeout=2)

    # AC-2: every line the child wrote after the launch line is a module printing onto the
    # pipe the client reads, so the launch check is only PASS when there were none.
    if extras:
        update_check(launch_entry, "FAIL", {"extra_stdout_lines": extras})
    update_check(
        leak_entry,
        "PASS" if not client.leaks else "FAIL",
        client.leaks or f"no occurrence of {client.forbid}",
    )
    return _finish(out, stamp, args, started, checks)


def _shut_down(checks, process, error, ports) -> None:
    """Close the child's stdin, wait for its own exit, and record AC-6 (AC-6)."""
    if error is None:
        try:
            process.stdin.close()
        except OSError as close_error:
            error = f"could not close the child's stdin: {close_error}"
    check_ac6(checks, process, error, ports)


def _finish(out: pathlib.Path, stamp: str, args, started: str, checks: list[dict]) -> int:
    payload = {
        "head": args.head,
        "started": started,
        "ended": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "checks": checks,
    }
    path = out / f"{stamp}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o644)
    tally = counts(checks)
    for line in summary_lines(tally):
        print(line, flush=True)
    print(f"results: {path}", flush=True)
    failed = sum(bucket["FAIL"] for bucket in tally.values())
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
