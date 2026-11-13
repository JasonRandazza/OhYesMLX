"""Checks for ``scripts/smoke_clean_account.py``, with no network, no subprocess, no sudo.

The script is the client half of the 045-03 clean-account smoke, so it is loaded from its path
the way ``tests/test_hash_freeze.py`` loads its script. Every live call in it needs the
throwaway account; only the pure parts are exercised here.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import types

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "smoke_clean_account.py"

_spec = importlib.util.spec_from_file_location("smoke_clean_account", SCRIPT)
smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke)


# ---------------------------------------------------------------------------
# AC-2: the launch line is the only thing on stdout
# ---------------------------------------------------------------------------


def test_launch_line_reads_port_and_token():
    assert smoke.parse_launch('{"port": 51234, "token": "abc"}\n') == (51234, "abc")


def test_launch_line_tolerates_blank_lines_but_not_two_lines():
    assert smoke.parse_launch('\n{"port": 1, "token": "t"}\n\n') == (1, "t")
    with pytest.raises(smoke.LaunchLineError) as caught:
        smoke.parse_launch('{"port": 1, "token": "t"}\n{"port": 2, "token": "u"}\n')
    assert "exactly one line" in str(caught.value)


@pytest.mark.parametrize(
    "text, expected",
    [
        ('{"port": 2}', "missing token"),
        ('{"token": "t"}', "missing port"),
        ('{"port": 2, "token": "t", "x": 1}', "unexpected x"),
        ('{"port": "2", "token": "t"}', "port must be an integer"),
        ('{"port": true, "token": "t"}', "port must be an integer"),
        ('{"port": 70000, "token": "t"}', "port must be an integer"),
        ('{"port": 2, "token": ""}', "token must be a non-empty string"),
        ('["port", "token"]', "not a JSON object"),
        ("not json", "not JSON"),
    ],
)
def test_launch_line_refuses_every_shape_it_does_not_pin(text, expected):
    with pytest.raises(smoke.LaunchLineError) as caught:
        smoke.parse_launch(text)
    assert expected in str(caught.value)


def test_the_launch_read_is_bounded_and_returns_the_first_line():
    read_fd, write_fd = os.pipe()
    try:
        with os.fdopen(read_fd, "rb") as stream:
            assert smoke.read_launch_line(stream, 0.05) is None, "no line within the deadline"
            os.write(write_fd, b'{"port": 1, "token": "t"}\n')
            assert smoke.read_launch_line(stream, 5) == b'{"port": 1, "token": "t"}\n'
    finally:
        os.close(write_fd)


def test_the_launch_read_stops_at_the_first_line_and_leaves_the_rest():
    read_fd, write_fd = os.pipe()
    try:
        with os.fdopen(read_fd, "rb") as stream:
            os.write(write_fd, b"one\ntwo\n")
            assert smoke.read_launch_line(stream, 5) == b"one\n"
            assert stream.readline() == b"two\n", "the extra line is still there to be seen"
    finally:
        os.close(write_fd)


def test_the_launch_read_returns_a_partial_line_at_eof():
    read_fd, write_fd = os.pipe()
    try:
        with os.fdopen(read_fd, "rb") as stream:
            os.write(write_fd, b'{"port": 1')
            os.close(write_fd)
            write_fd = -1
            assert smoke.read_launch_line(stream, 5) == b'{"port": 1'
    finally:
        if write_fd != -1:
            os.close(write_fd)


# ---------------------------------------------------------------------------
# SSE: id/data framing, multi-line data, keepalive comments
# ---------------------------------------------------------------------------


EVENT = 'data: {"seq": %d, "type": "%s", "message": "m", "fraction": null, "payload": null}\n\n'


def test_sse_parses_frames_in_order_with_their_ids():
    text = ("id: 1\n" + EVENT % (1, "progress")) + ("id: 2\n" + EVENT % (2, "done"))
    frames, rest = smoke.parse_sse(text)
    assert rest == ""
    assert [frame["id"] for frame in frames] == [1, 2]
    assert [json.loads(frame["data"])["type"] for frame in frames] == ["progress", "done"]


def test_sse_joins_multi_line_data_and_drops_keepalive_comments():
    text = (
        ": keepalive\n\n"
        "id: 3\ndata: {\"seq\": 3,\ndata:  \"type\": \"log\"}\n\n"
        ": keepalive\n\n"
    )
    frames, rest = smoke.parse_sse(text)
    assert rest == ""
    assert len(frames) == 1
    assert json.loads(frames[0]["data"]) == {"seq": 3, "type": "log"}


def test_sse_keeps_an_incomplete_frame_for_the_next_read():
    frames, rest = smoke.parse_sse('id: 9\ndata: {"seq": 9}')
    assert frames == []
    assert rest == 'id: 9\ndata: {"seq": 9}'
    frames, rest = smoke.parse_sse(rest + "\n\n")
    assert rest == ""
    assert json.loads(frames[0]["data"]) == {"seq": 9}
    assert frames[0]["id"] == 9


def test_sse_returns_nothing_for_a_keepalive_only_read():
    frames, rest = smoke.parse_sse(": keepalive\n\n: keepalive\n\n")
    assert frames == []
    assert rest == ""


# ---------------------------------------------------------------------------
# AC-3: the leak scan
# ---------------------------------------------------------------------------


def test_forbid_scan_names_the_offending_lines():
    text = '{"path": "/Users/Shared/oymlx-smoke"}\n{"path": "/Users/jrazz/x"}\n'
    assert smoke.forbid_hits(text, "/Users/jrazz") == ['{"path": "/Users/jrazz/x"}']


def test_forbid_scan_is_quiet_on_a_clean_body_and_on_an_empty_needle():
    assert smoke.forbid_hits('{"chip": "Apple M2 Max"}', "/Users/jrazz") == []
    assert smoke.forbid_hits("/Users/jrazz", "") == []


# ---------------------------------------------------------------------------
# AC-3 / AC-4: the pip step really is hash-pinned
# ---------------------------------------------------------------------------


def test_real_install_plans_carry_the_hash_pins():
    from ohyesmlx import engines

    package_dir = str(pathlib.Path(engines.__file__).resolve().parent)
    for name in ("mlxlm", "optiq"):
        plan = _as_plan(engines.install_plan(name, 15))
        assert smoke.pip_argv_problems(plan, name, package_dir) == []


def _as_plan(plan):
    import dataclasses

    return dataclasses.asdict(plan)


def test_both_pip_engines_install_with_no_deps_and_wheels_only():
    """The ``--no-deps``/pygame rationale is at ``ohyesmlx.engines`` (``_command_plan``)."""
    from ohyesmlx import engines

    package_dir = str(pathlib.Path(engines.__file__).resolve().parent)
    for name in ("mlxlm", "optiq"):
        argv = smoke._pip_argv(_as_plan(engines.install_plan(name, 15)))
        assert "--no-deps" in argv
        assert "--no-binary" not in argv
        assert smoke.pip_argv_problems(_as_plan(engines.install_plan(name, 15)), name, package_dir) == []


def test_pip_argv_problems_names_a_missing_no_deps():
    from ohyesmlx import engines

    package_dir = str(pathlib.Path(engines.__file__).resolve().parent)
    for name in ("mlxlm", "optiq"):
        plan = _as_plan(engines.install_plan(name, 15))
        assert smoke.pip_argv_problems(_strip(plan, "--no-deps"), name, package_dir) == [
            f"{name}: the pip step has no --no-deps"
        ]


def test_a_plan_missing_a_pin_is_refused_one_reason_each():
    from ohyesmlx import engines

    package_dir = str(pathlib.Path(engines.__file__).resolve().parent)
    plan = _as_plan(engines.install_plan("mlxlm", 15))
    for flag in ("--require-hashes", "--isolated"):
        assert smoke.pip_argv_problems(_strip(plan, flag), "mlxlm", package_dir) == [
            f"mlxlm: the pip step has no {flag}"
        ]
    assert smoke.pip_argv_problems(_strip(plan, "--only-binary", ":all:"), "mlxlm", package_dir) == [
        "mlxlm: the pip step has no --only-binary :all:"
    ]
    assert smoke.pip_argv_problems(_strip(plan, "-r", None), "mlxlm", package_dir) == [
        "mlxlm: the pip step has no -r constraints file"
    ]


def test_a_constraints_file_outside_the_package_is_refused():
    from ohyesmlx import engines

    package_dir = str(pathlib.Path(engines.__file__).resolve().parent)
    plan = _as_plan(engines.install_plan("mlxlm", 15))
    moved = json.loads(json.dumps(plan))
    command = _pip_step(moved)["command"]
    command[command.index("-r") + 1] = "/tmp/elsewhere/constraints.txt"
    assert smoke.pip_argv_problems(moved, "mlxlm", package_dir) == [
        "mlxlm: /tmp/elsewhere/constraints.txt is not under " + package_dir
    ]


def test_a_plan_without_a_pip_step_is_refused():
    assert smoke.pip_argv_problems({"kind": "guided_download", "steps": []}, "osaurus", "/pkg") == [
        "osaurus: the install plan is not a command plan"
    ]
    assert smoke.pip_argv_problems({"kind": "command", "steps": []}, "mlxlm", "/pkg") == [
        "mlxlm: the plan has no pip install step"
    ]


def _pip_step(plan):
    for step in plan["steps"]:
        if isinstance(step.get("command"), list) and "pip" in step["command"]:
            return step
    raise AssertionError("no pip step")


def _strip(plan, flag, value=None):
    """A copy of *plan* with ``flag``, and *value* after it when given, removed from its pip step."""
    copied = json.loads(json.dumps(plan))
    command = _pip_step(copied)["command"]
    index = command.index(flag)
    if value is None:
        del command[index]
    else:
        assert command[index + 1] == value
        del command[index : index + 2]
    return copied


# ---------------------------------------------------------------------------
# Result recording and the per-AC summary
# ---------------------------------------------------------------------------


def test_add_check_appends_only_the_pinned_three_keys():
    checks = []
    entry = smoke.add_check(checks, "AC-3.hardware", "PASS", {"status": 200})
    assert entry == {"id": "AC-3.hardware", "status": "PASS", "evidence": {"status": 200}}
    assert checks == [entry]


def test_add_check_refuses_a_status_outside_the_pinned_three():
    with pytest.raises(ValueError) as caught:
        smoke.add_check([], "AC-1", "OK", None)
    assert "PASS, FAIL or SKIP" in str(caught.value)


def test_update_check_rewrites_the_entry_rather_than_appending():
    checks = []
    entry = smoke.add_check(checks, "AC-3.no_host_paths", "PASS", "clean")
    smoke.update_check(entry, "FAIL", ["/Users/jrazz/x"])
    assert len(checks) == 1
    assert checks[0] == {
        "id": "AC-3.no_host_paths",
        "status": "FAIL",
        "evidence": ["/Users/jrazz/x"],
    }


def test_gate_names_the_prerequisite_that_did_not_pass():
    checks = []
    smoke.add_check(checks, "AC-5.download", "FAIL", "http_error")
    assert smoke.gate(checks, "AC-5.download") == "skipped: AC-5.download did not pass"
    assert smoke.gate(checks, "AC-5.download", "AC-5.missing") == (
        "skipped: AC-5.download did not pass"
    )
    smoke.update_check(checks[0], "PASS", "ok")
    assert smoke.gate(checks, "AC-5.download") is None
    assert smoke.gate(checks, "AC-2.launch_line") == "skipped: AC-2.launch_line did not pass"


def test_counts_and_the_summary_are_per_ac_and_in_order():
    checks = []
    smoke.add_check(checks, "AC-3.hardware", "PASS", None)
    smoke.add_check(checks, "AC-3.token_required", "FAIL", None)
    smoke.add_check(checks, "AC-2.app_support_mode", "PASS", None)
    smoke.add_check(checks, "AC-2.stdout_single_line", "SKIP", None)
    tally = smoke.counts(checks)
    assert tally == {
        "AC-2": {"PASS": 1, "FAIL": 0, "SKIP": 1},
        "AC-3": {"PASS": 1, "FAIL": 1, "SKIP": 0},
    }
    assert smoke.summary_lines(tally) == [
        "AC-2: 1 PASS 0 FAIL 1 SKIP",
        "AC-3: 1 PASS 1 FAIL 0 SKIP",
    ]


def test_job_failed_reports_the_last_error_code():
    events = [
        {"type": "progress", "payload": {"step": "create-venv"}},
        {"type": "error", "message": "step failed", "payload": {"code": "step_failed"}},
        {"type": "error", "message": "another", "payload": {"code": "cancelled"}},
        {"type": "done", "payload": None},
    ]
    assert smoke.job_failed(events) == "cancelled"
    assert smoke.job_failed(events[:1] + events[3:]) is None
    assert smoke.job_failed([{"type": "error", "message": "no code", "payload": None}]) == "no code"


def test_hub_repo_dir_is_the_models_dash_dash_name():
    assert smoke.hub_repo_dir("mlx-community/Qwen3-0.6B-4bit").name == (
        "models--mlx-community--Qwen3-0.6B-4bit"
    )


def test_hub_repo_dir_asks_fetch_instead_of_rebuilding_the_name(monkeypatch):
    """045-03: one definition of the hub directory, and it is ``fetch``'s."""
    from ohyesmlx import fetch

    asked = []
    monkeypatch.setattr(fetch, "default_cache_dir", lambda: "/cache/hub")
    monkeypatch.setattr(
        fetch, "_repo_dir", lambda root, repo: asked.append((root, repo)) or f"{root}/asked"
    )
    assert smoke.hub_repo_dir("org/name") == pathlib.Path("/cache/hub/asked")
    assert asked == [("/cache/hub", "org/name")]


def test_ports_are_the_shs_list_space_separated():
    """045-03: ``PORTS`` in the .sh is the definition; the client parses what it is given."""
    assert smoke.parse_ports("1337 8000 8080") == (1337, 8000, 8080)
    assert smoke.parse_ports(" 1337\n8000 ") == (1337, 8000)
    with pytest.raises(ValueError):
        smoke.parse_ports("1337 8o00")


def test_outcome_records_the_client_interval_and_the_last_event():
    events = [
        {"seq": 1, "type": "progress", "message": "stage A", "payload": None},
        {"seq": 2, "type": "done", "message": "quickbench finished", "payload": None},
    ]
    assert smoke._outcome(events, 12.5, None) == {
        "events": 2,
        "seconds": 12.5,
        "problem": None,
        "error": None,
        "last": events[-1],
    }
    assert smoke._outcome([], None, "no done event within 1800 s")["last"] is None


def test_cell_outcomes_take_the_progress_events_and_the_summary_wins():
    events = [
        {
            "type": "progress",
            "payload": {"engine": "mlxlm", "status": "PASS"},
        },
        {
            "type": "progress",
            "payload": {"engine": "omlx", "skipped": "port 8100 answers"},
        },
        {
            "type": "result",
            "payload": {
                "stage_a": {
                    "cells": [
                        {"engine": "mlxlm", "status": "FAIL", "reason": "token salad"},
                        {"engine": "optiq", "status": "PASS", "reason": None},
                    ]
                },
                "stage_b": {"cells": [{"engine": "optiq", "status": "PASS"}]},
            },
        },
        {"type": "done", "payload": None},
    ]
    assert smoke.cell_outcomes(events) == [
        {"engine": "mlxlm", "status": "FAIL", "reason": "token salad"},
        {"engine": "omlx", "status": "SKIPPED", "reason": "port 8100 answers"},
        {"engine": "optiq", "status": "PASS", "reason": None},
        {"engine": "stage_b:optiq", "status": "PASS", "reason": None},
    ]


def test_cell_outcomes_ignores_events_with_no_cell_in_them():
    events = [
        {"type": "progress", "payload": {"stage": "A"}},
        {"type": "log", "payload": {"repo": "x/y"}},
        {"type": "result", "payload": None},
        {"type": "error", "payload": {"code": "unknown_repo"}},
    ]
    assert smoke.cell_outcomes(events) == []


def test_a_failed_check_never_stops_the_recording():
    checks = []
    smoke.add_check(checks, "AC-3.hardware", "FAIL", "boom")
    smoke.add_check(checks, "AC-3.engines_plans", "PASS", "ok")
    assert [entry["status"] for entry in checks] == ["FAIL", "PASS"]
    assert smoke.counts(checks) == {"AC-3": {"PASS": 1, "FAIL": 1, "SKIP": 0}}


# ---------------------------------------------------------------------------
# The results file the coordinator reads
# ---------------------------------------------------------------------------


def test_finish_writes_one_readable_json_file_at_0644(tmp_path, capsys):
    checks = []
    smoke.add_check(checks, "AC-2.launch_line", "PASS", "one line")
    smoke.add_check(checks, "AC-3.hardware", "FAIL", {"status": 500})
    args = types.SimpleNamespace(head="a" * 40)

    code = smoke._finish(tmp_path, "20261113T000000Z", args, "2026-11-13T00:00:00+00:00", checks)

    path = tmp_path / "20261113T000000Z.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {
        "head": "a" * 40,
        "started": "2026-11-13T00:00:00+00:00",
        "ended": payload["ended"],
        "checks": checks,
    }
    assert path.stat().st_mode & 0o777 == 0o644
    assert code == 1, "one FAIL is a non-zero exit"
    out = capsys.readouterr().out.splitlines()
    assert out[:2] == ["AC-2: 1 PASS 0 FAIL 0 SKIP", "AC-3: 0 PASS 1 FAIL 0 SKIP"]
    assert out[2] == f"results: {path}"
