"""Checks for the guarded localhost server.

Every test talks to a real ``ThreadingHTTPServer`` over a real socket on port 0. The guard is
a property of the server -- it runs before the router, on every method -- and a handler called
directly would test a call the server never makes. The module seams (``scan``, ``detect``,
``load_catalog``) are the fakes; ``engines.install_plan`` and ``recommend`` are the real
functions, because what the endpoints are checked for is the composition those modules already
define.

The launch token is a fixed string here so an assertion can look for it; the test that it is
generated fresh per launch is the one place a real token is read.
"""

from __future__ import annotations

import dataclasses
import functools
import http.client
import json
import socket
import subprocess
import threading
import time

import pytest

from ohyesmlx import catalog, engines, fetch, hardware, recommend, server

TOKEN = "a-fixed-launch-token-for-these-tests"

UNSET = object()


# --- fixtures the endpoints are composed from ------------------------------------------------
#
# Real dataclasses, never dicts: the endpoints serialise with `dataclasses.asdict`, and a fake
# that was already the serialised shape would test the fake rather than the composition.


def this_mac(**overrides):
    """A supported M2 Max with room for the small fixture model, overridable per test."""
    fields = dict(
        supported=True,
        unsupported_reason=None,
        chip="Apple M2 Max",
        family="M2",
        tier="max",
        cpu_cores=12,
        gpu_cores=38,
        ram_bytes=64 * 1024**3,
        macos="15.4",
        disk_free_bytes=100 * 1024**3,
        volumes=[{"path": "/", "free_bytes": 100 * 1024**3}],
        model_budget_bytes=46 * 1024**3,
    )
    fields.update(overrides)
    return hardware.Hardware(**fields)


def status(name, *, installed, version=None):
    return engines.EngineStatus(
        name=name,
        title=name,
        blurb="",
        installed=installed,
        version=version,
        path=f"/bin/{name}" if installed else None,
        tested=installed,
        verified="2026-10-29",
        install=None,
    )


def a_model(repo, size_bytes, *, params=3_000_000_000, tier="starter"):
    return catalog.Model(
        repo=repo,
        title=repo,
        params=params,
        format="oq4",
        modality="text",
        license="apache-2.0",
        tier=tier,
        revision="0" * 40,
        size_bytes=size_bytes,
        files=[
            catalog.ModelFile(
                path="model.safetensors", size=size_bytes, sha256="a" * 64, git_oid=None
            )
        ],
        engines=["mlxlm"],
        measured_here=False,
        notes="",
    )


# 2 GiB is comfortable against a 46 GiB budget and fits the 100 GiB disk; 40 GiB exceeds both
# lines, so the pair gives `/recommendations` one pick and one exclusion.
MODELS = [a_model("org/small", 2 * 1024**3), a_model("org/large", 40 * 1024**3, params=70_000_000_000, tier="standard")]


class Recorder:
    """A stand-in module function that remembers whether it was called."""

    def __init__(self, answer):
        self.answer = answer
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        return self.answer


@pytest.fixture
def launch():
    """Start a real server on port 0, and stop it when the test is done."""
    started = []

    def start(**kwargs):
        kwargs.setdefault("token", TOKEN)
        # No test reads this Mac's Application Support directory: the quickbench summaries
        # `/recommendations` asks for are empty unless the test hands in its own.
        kwargs.setdefault("summaries", lambda: {})
        listener = server.make_server(0, **kwargs)
        thread = threading.Thread(
            target=listener.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        thread.start()
        started.append((listener, thread))
        return listener

    yield start
    for listener, thread in started:
        listener.shutdown()
        listener.server_close()
        thread.join(timeout=5)


def request(listener, path="/hardware", *, method="GET", token=None, headers=None, host=UNSET):
    """One request on its own connection: ``(status, headers, raw body)``.

    ``token`` adds ``Authorization: Bearer <token>`` and ``host`` sets the ``Host`` header;
    both are explicit because the guard's whole job is those two values. ``host=None`` sends no
    ``Host`` at all, which ``http.client`` will not do on its own.
    """
    given = dict(headers or {})
    if token is not None:
        given["Authorization"] = f"Bearer {token}"
    if host is UNSET:
        given.setdefault("Host", f"127.0.0.1:{listener.server_address[1]}")
    elif host is not None:
        given["Host"] = host

    connection = http.client.HTTPConnection(
        "127.0.0.1", listener.server_address[1], timeout=5
    )
    try:
        connection.putrequest(method, path, skip_host=True)
        for name, value in given.items():
            connection.putheader(name, value)
        connection.endheaders()
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def error_of(raw: bytes) -> dict:
    """The pinned error object, checked for shape before its contents are read."""
    payload = json.loads(raw)
    assert set(payload) == {"error"}, payload
    assert set(payload["error"]) == {"code", "status", "message"}, payload
    return payload["error"]


# --- AC-1: loopback only, ephemeral by default, one fresh token per launch -------------------


def test_the_server_binds_loopback_only_on_an_ephemeral_port(launch):
    """127.0.0.1 and not 0.0.0.0 or ::, with the OS's port because the caller passed 0."""
    listener = launch()

    assert listener.server_address[0] == "127.0.0.1"
    assert listener.server_address[1] != 0
    assert listener.daemon_threads is True, "a handler thread may never block shutdown"


def test_each_launch_gets_its_own_token(launch):
    """AC-1: `secrets.token_urlsafe(32)`, fresh per launch, held in memory only."""
    first = launch(token=None)
    second = launch(token=None)

    assert first.token != second.token
    assert len(first.token) == 43  # token_urlsafe(32) is 32 bytes, unpadded base64url


# --- AC-2: the guard, in order, before the router -------------------------------------------


def test_a_foreign_host_is_403_bad_host(launch):
    listener = launch()
    port = listener.server_address[1]

    for host in (f"evil.example:{port}", "127.0.0.1", f"127.0.0.1:{port + 1}", f"LOCALHOST:{port}"):
        code, _, raw = request(listener, token=TOKEN, host=host)

        assert code == 403, host
        assert error_of(raw)["code"] == "bad_host", host


def test_an_absent_host_is_403_bad_host(launch):
    """A missing Host passes a loose check; the audit's must-have is that it does not."""
    listener = launch()

    code, _, raw = request(listener, token=TOKEN, host=None)

    assert code == 403
    assert error_of(raw)["code"] == "bad_host"


def test_both_exact_host_forms_are_accepted(launch):
    listener = launch()
    port = listener.server_address[1]

    assert request(listener, token=TOKEN, host=f"127.0.0.1:{port}")[0] == 200
    assert request(listener, token=TOKEN, host=f"localhost:{port}")[0] == 200


def test_any_origin_header_is_403_origin_refused(launch):
    listener = launch()

    for origin in ("https://evil.example", "null", "http://127.0.0.1:3000"):
        code, _, raw = request(listener, token=TOKEN, headers={"Origin": origin})

        assert code == 403, origin
        assert error_of(raw)["code"] == "origin_refused", origin


def test_a_missing_or_wrong_token_is_401_unauthorized(launch):
    """The token is the control: right Host, no Origin, and still 401 without it."""
    listener = launch()

    for token in (None, "wrong", TOKEN + "x", ""):
        code, _, raw = request(listener, token=token)

        assert code == 401, token
        assert error_of(raw)["code"] == "unauthorized", token


def test_the_token_is_compared_as_bytes_so_non_ascii_is_401_not_500(launch):
    """`hmac.compare_digest` raises TypeError on non-ASCII str; UTF-8 bytes cannot raise."""
    listener = launch()

    code, _, raw = request(listener, token="é")

    assert code == 401
    assert error_of(raw)["code"] == "unauthorized"


def test_the_guard_runs_before_the_router(launch):
    """An unknown path is refused by the guard first: 401 without a token, 403 with an Origin."""
    listener = launch()

    code, _, raw = request(listener, "/nope")
    assert code == 401
    assert error_of(raw)["code"] == "unauthorized"

    code, _, raw = request(listener, "/nope", token=TOKEN, headers={"Origin": "https://evil.example"})
    assert code == 403
    assert error_of(raw)["code"] == "origin_refused"


def test_a_refused_request_reaches_no_handler_and_runs_no_module(launch):
    """AC-2's property rather than each handler's: nothing is asked of a module before the token."""
    scan = Recorder(this_mac())
    detect = Recorder([status("mlxlm", installed=True, version="0.31.3")])
    load = Recorder(MODELS)
    listener = launch(scan=scan, detect=detect, load_catalog=load)

    refusals = (
        {"token": None},
        {"token": "wrong"},
        {"token": TOKEN, "headers": {"Origin": "https://evil.example"}},
        {"token": TOKEN, "headers": {"Host": "evil.example"}},
    )
    for path in (
        "/hardware",
        "/engines",
        "/recommendations",
        "/quickbench/plan?repo=org/small",
    ):
        for refusal in refusals:
            code, _, _ = request(listener, path, **refusal)
            assert code in (401, 403), (path, refusal)

    assert (scan.calls, detect.calls, load.calls) == (0, 0, 0)


def test_no_response_or_log_echoes_the_token_or_a_header_value(launch, capsys):
    """Responses are fixed strings per code, and the refusal line names no header value."""
    listener = launch()

    for kwargs in (
        {},
        {"token": TOKEN},
        {"token": TOKEN, "headers": {"Origin": TOKEN}},
        {"token": TOKEN, "headers": {"Host": TOKEN}},
        {"token": TOKEN, "headers": {"Origin": "https://evil.example", "Host": "evil.example"}},
    ):
        _, headers, raw = request(listener, **kwargs)

        assert TOKEN.encode() not in raw
        assert b"evil.example" not in raw
        assert all(TOKEN not in value for value in headers.values())
        assert all("evil.example" not in value for value in headers.values())

    lines = capsys.readouterr().err.splitlines()
    assert lines
    assert all(TOKEN not in line for line in lines), "a header value reached stderr"


# --- AC-3: GET /hardware --------------------------------------------------------------------


def test_hardware_is_the_scan_as_json_with_integer_byte_counts(launch):
    fake = this_mac()
    listener = launch(scan=Recorder(fake))

    code, _, raw = request(listener, "/hardware", token=TOKEN)

    assert code == 200
    body = json.loads(raw)
    assert body == dataclasses.asdict(fake)
    for key in ("cpu_cores", "ram_bytes", "disk_free_bytes", "model_budget_bytes"):
        assert isinstance(body[key], int) and not isinstance(body[key], bool), key
    assert isinstance(body["volumes"][0]["free_bytes"], int)


# --- AC-4: GET /engines ---------------------------------------------------------------------


def test_engines_composes_install_plans_and_leaves_installed_engines_null(launch):
    installed = status("mlxlm", installed=True, version="0.31.3")
    missing = status("optiq", installed=False)
    listener = launch(scan=Recorder(this_mac()), detect=Recorder([installed, missing]))

    code, _, raw = request(listener, "/engines", token=TOKEN)

    assert code == 200
    body = json.loads(raw)
    assert body[0] == dataclasses.asdict(installed), "an installed engine carries install: null"
    assert body[1]["installed"] is False
    plan = body[1]["install"]
    assert plan["engine"] == "optiq"
    assert plan["kind"] == "command"
    assert plan["steps"], "a command plan is nothing without its steps"
    assert plan["size_bytes_estimate"] is None


def test_the_install_plan_gets_the_macos_major_and_only_for_missing_engines(launch, monkeypatch):
    """`macos_major` is the integer before the first dot, and an installed engine is not planned."""
    seen = []

    def install_plan(name, macos_major):
        seen.append((name, macos_major))
        return engines.Plan(
            engine=name,
            kind="guided_download",
            source_url="",
            size_bytes_estimate=None,
            needs_admin=False,
            steps=[],
        )

    monkeypatch.setattr(engines, "install_plan", install_plan)
    listener = launch(
        scan=Recorder(this_mac(macos="26.1")),
        detect=Recorder(
            [status("mlxlm", installed=True, version="0.31.3"), status("osaurus", installed=False)]
        ),
    )

    code, _, raw = request(listener, "/engines", token=TOKEN)

    assert code == 200
    assert seen == [("osaurus", 26)]
    assert json.loads(raw)[1]["install"]["engine"] == "osaurus"


def test_an_install_plan_value_error_is_500_naming_the_engine(launch, monkeypatch):
    def install_plan(name, macos_major):
        raise ValueError("no pip constraints file for optiq 0.5.13")

    monkeypatch.setattr(engines, "install_plan", install_plan)
    listener = launch(
        scan=Recorder(this_mac()), detect=Recorder([status("optiq", installed=False)])
    )

    code, _, raw = request(listener, "/engines", token=TOKEN)

    assert code == 500
    error = error_of(raw)
    assert error["code"] == "install_plan_failed"
    assert "optiq" in error["message"], "the failure has to name the engine it is about"


# --- AC-1 (04-03b): GET /quickbench/plan -----------------------------------------------------


def a_quick_plan(repo="org/small"):
    """The module's own plan shape, returned by a fake so no cache or hardware is read."""
    from ohyesmlx import quickbench

    return quickbench.QuickPlan(
        repo=repo,
        format="oq4",
        stage_a=[quickbench.PlannedEngine("mlxlm", "0.31.3", True)],
        stage_b=[quickbench.PlannedSibling("org/sibling", "stock4bit", 2_000, False)],
        download_bytes=2_000,
        osaurus=False,
        estimate_s=120,
    )


def test_the_quickbench_plan_endpoint_returns_the_plan(launch, monkeypatch):
    from ohyesmlx import quickbench

    calls = []

    def fake_plan(repo, hw, statuses, models, **kwargs):
        calls.append({"repo": repo, "hw": hw, "statuses": statuses, "models": models})
        return a_quick_plan(repo)

    monkeypatch.setattr(quickbench, "plan", fake_plan)
    hw = this_mac()
    statuses = [status("mlxlm", installed=True, version="0.31.3")]
    listener = launch(
        scan=Recorder(hw), detect=Recorder(statuses), load_catalog=Recorder(MODELS)
    )

    code, headers, raw = request(listener, "/quickbench/plan?repo=org/small", token=TOKEN)

    assert code == 200
    body = json.loads(raw)
    assert set(body) == {
        "repo",
        "format",
        "stage_a",
        "stage_b",
        "download_bytes",
        "osaurus",
        "estimate_s",
    }
    assert body["repo"] == "org/small"
    assert body["stage_a"] == [{"engine": "mlxlm", "version": "0.31.3", "tested": True}]
    assert body["stage_b"][0]["repo"] == "org/sibling"
    assert calls == [{"repo": "org/small", "hw": hw, "statuses": statuses, "models": MODELS}]
    assert headers["Content-Type"] == "application/json; charset=utf-8"


def test_the_quickbench_plan_endpoint_refuses_a_missing_repo(launch):
    listener = launch()

    code, _, raw = request(listener, "/quickbench/plan", token=TOKEN)

    assert code == 400
    error = error_of(raw)
    assert error["code"] == "bad_args"
    assert "repo" in error["message"]


def test_the_quickbench_plan_endpoint_delivers_the_modules_refusal(launch, monkeypatch):
    """A repo that is not downloaded is a 400 whose message says to download it first."""
    from ohyesmlx import quickbench

    def refuse(*args, **kwargs):
        raise ValueError(
            "org/nope is not in this Mac's Hugging Face cache; download it first"
        )

    monkeypatch.setattr(quickbench, "plan", refuse)
    listener = launch()

    code, _, raw = request(listener, "/quickbench/plan?repo=org/nope", token=TOKEN)

    assert code == 400
    error = error_of(raw)
    assert error["code"] == "bad_args"
    assert "download it first" in error["message"]


# --- AC-5: GET /recommendations -------------------------------------------------------------


def test_recommendations_is_the_pinned_composition(launch):
    listener = launch(
        scan=Recorder(this_mac()),
        detect=Recorder([status("mlxlm", installed=True, version="0.31.3")]),
        load_catalog=Recorder(MODELS),
    )

    code, _, raw = request(listener, "/recommendations", token=TOKEN)

    assert code == 200
    body = json.loads(raw)
    assert set(body) == {"picks", "excluded", "unsupported_reason"}
    assert body["unsupported_reason"] is None
    assert [pick["model_id"] for pick in body["picks"]] == ["org/small"]
    assert [row["model_id"] for row in body["excluded"]] == ["org/large"]

    pick = body["picks"][0]
    assert set(pick) == {
        "model_id",
        "title",
        "params_b",
        "format",
        "size_bytes",
        "fit",
        "fit_basis",
        "engines",
        "install_needed",
        "start_here",
        "reason",
        "downloaded",
        "measured_here",
    }
    assert pick["params_b"] == 3.0
    assert isinstance(pick["size_bytes"], int)
    assert pick["fit"] == "comfortable"
    assert pick["downloaded"] is False
    assert pick["measured_here"] is None, "no quick run on this Mac has named the row"

    large = MODELS[1]
    assert body["excluded"][0] == {
        "model_id": large.repo,
        "reason": recommend.exclusion_reason(large, this_mac(), this_mac().disk_free_bytes),
    }


def test_recommendations_asks_fetch_downloaded_and_marks_the_picks(launch, monkeypatch):
    """AC-2: the set comes from `fetch.downloaded` over the catalog, and a downloaded row
    is offered even on a Mac whose free disk could not hold the download."""
    asked = []

    def downloaded(model, cache_dir=None):
        asked.append(model.repo)
        return model.repo == "org/small"

    monkeypatch.setattr(server.fetch, "downloaded", downloaded)
    listener = launch(
        scan=Recorder(this_mac(disk_free_bytes=0)),
        detect=Recorder([]),
        load_catalog=Recorder(MODELS),
    )

    body = json.loads(request(listener, "/recommendations", token=TOKEN)[2])

    assert asked == ["org/small", "org/large"]
    assert [pick["model_id"] for pick in body["picks"]] == ["org/small"]
    pick = body["picks"][0]
    assert pick["downloaded"] is True
    assert "already on this Mac" in pick["reason"]
    assert "GB download" not in pick["reason"]
    assert [row["model_id"] for row in body["excluded"]] == ["org/large"]


def test_recommendations_fills_measured_here_from_the_newest_quick_run(launch):
    """AC-5: the newest finished quickbench summary's `best` block is the pick's own run."""
    best = {
        "engine": "mlxlm",
        "decode_tps": 60.0,
        "ttft_s": 0.2,
        "measured_at": "2026-11-02T10:00:00+00:00",
        "quick": True,
    }
    listener = launch(
        scan=Recorder(this_mac()),
        detect=Recorder([status("mlxlm", installed=True, version="0.31.3")]),
        load_catalog=Recorder(MODELS),
        summaries=lambda: {
            "org/small": {"repo": "org/small", "ended": "finished", "best": best}
        },
    )

    body = json.loads(request(listener, "/recommendations", token=TOKEN)[2])

    picks = {pick["model_id"]: pick for pick in body["picks"]}
    assert picks["org/small"]["measured_here"] == best


def test_recommendations_leaves_measured_here_null_without_a_finished_quick_run(launch):
    """A cancelled run is a record, not a recommendation: its summary has no `best`."""
    listener = launch(
        scan=Recorder(this_mac()),
        detect=Recorder([status("mlxlm", installed=True, version="0.31.3")]),
        load_catalog=Recorder(MODELS),
        summaries=lambda: {
            "org/small": {"repo": "org/small", "ended": "cancelled", "best": None}
        },
    )

    body = json.loads(request(listener, "/recommendations", token=TOKEN)[2])

    assert body["picks"][0]["measured_here"] is None


def test_recommendations_uses_the_hardware_scans_free_disk(launch):
    """The free disk is `Hardware.disk_free_bytes`: shrink it and the small row is a disk refusal."""
    hw = this_mac(disk_free_bytes=1 * 1024**3)
    listener = launch(
        scan=Recorder(hw), detect=Recorder([]), load_catalog=Recorder(MODELS)
    )

    body = json.loads(request(listener, "/recommendations", token=TOKEN)[2])

    assert body["picks"] == []
    assert [row["model_id"] for row in body["excluded"]] == ["org/small", "org/large"]
    assert "free disk" in body["excluded"][0]["reason"]
    assert "memory" in body["excluded"][1]["reason"], "memory is checked before disk"


def test_an_unsupported_mac_has_empty_lists_and_carries_the_reason(launch):
    """The one sentence belongs to the Mac, so no model gets a copy of it in `excluded`."""
    hw = this_mac(
        supported=False,
        unsupported_reason="this Mac is not Apple silicon",
        model_budget_bytes=1,
        disk_free_bytes=1,
    )
    listener = launch(
        scan=Recorder(hw), detect=Recorder([]), load_catalog=Recorder(MODELS)
    )

    body = json.loads(request(listener, "/recommendations", token=TOKEN)[2])

    assert body == {
        "picks": [],
        "excluded": [],
        "unsupported_reason": "this Mac is not Apple silicon",
    }


# --- AC-6: everything else, in the pinned shape ---------------------------------------------


def test_an_unknown_path_is_404_not_found(launch):
    listener = launch()

    code, _, raw = request(listener, "/nope", token=TOKEN)

    assert code == 404
    assert error_of(raw)["code"] == "not_found"


def test_a_non_get_on_a_known_path_is_405_method_not_allowed(launch):
    listener = launch(scan=Recorder(this_mac()))

    for method in ("POST", "PUT", "DELETE", "PATCH", "OPTIONS"):
        code, _, raw = request(listener, "/hardware", token=TOKEN, method=method)

        assert code == 405, method
        assert error_of(raw)["code"] == "method_not_allowed", method


def test_head_on_a_known_path_is_405(launch):
    """HEAD is one of the methods the plan enumerates; it gets the 405, and no body to read."""
    listener = launch(scan=Recorder(this_mac()))

    code, headers, raw = request(listener, "/hardware", token=TOKEN, method="HEAD")

    assert code == 405
    assert raw == b""
    assert not [name for name in headers if name.lower().startswith("access-control-")]


def test_a_non_get_on_an_unknown_path_is_still_404(launch):
    """There is nothing at an unknown path to be method-not-allowed about."""
    listener = launch()

    code, _, raw = request(listener, "/nope", token=TOKEN, method="POST")

    assert code == 404
    assert error_of(raw)["code"] == "not_found"


def test_a_module_exception_is_500_internal_with_its_message_and_no_traceback(launch):
    def explode():
        raise RuntimeError("the scan failed")

    listener = launch(scan=explode)

    code, _, raw = request(listener, "/hardware", token=TOKEN)

    assert code == 500
    error = error_of(raw)
    assert error == {"code": "internal", "status": 500, "message": "the scan failed"}
    text = raw.decode("utf-8")
    assert "Traceback" not in text
    assert "RuntimeError" not in text


def test_every_response_is_json_uncached_and_has_no_cors_header(launch):
    """One response builder, so 200, 401, 403, 404 and 405 agree on all three properties."""
    listener = launch(scan=Recorder(this_mac()), detect=Recorder([]), load_catalog=Recorder(MODELS))

    responses = [
        request(listener, "/hardware", token=TOKEN),
        request(listener, "/hardware"),
        request(listener, "/hardware", token=TOKEN, headers={"Origin": "https://evil.example"}),
        request(listener, "/hardware", token=TOKEN, headers={"Host": "evil.example"}),
        request(listener, "/nope", token=TOKEN),
        request(listener, "/hardware", token=TOKEN, method="OPTIONS"),
    ]

    assert [code for code, _, _ in responses] == [200, 401, 403, 403, 404, 405]
    for code, headers, raw in responses:
        lowered = {name.lower(): value for name, value in headers.items()}
        assert lowered["content-type"] == "application/json; charset=utf-8", code
        assert lowered["cache-control"] == "no-store", code
        assert not [name for name in lowered if name.startswith("access-control-")], code
        json.loads(raw), code


# --- AC-8: bounded connections and a trace of refusals --------------------------------------


def test_an_idle_connection_is_closed_after_the_handler_timeout(launch):
    """A client that sends nothing is dropped when the timeout elapses, not held forever."""
    listener = launch(timeout=0.2)

    connection = socket.create_connection(listener.server_address, timeout=5)
    try:
        assert connection.recv(1) == b"", "the server never closed the idle connection"
    finally:
        connection.close()


def test_a_refusal_writes_one_stderr_line_and_a_served_request_writes_nothing(launch, capsys):
    listener = launch()

    assert request(listener, "/hardware", token=TOKEN)[0] == 200
    assert capsys.readouterr().err == "", "a served request writes nothing"

    assert request(listener, "/hardware")[0] == 401
    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == 1, lines
    record = json.loads(lines[0])
    assert record["refused"] == "unauthorized"
    assert record["method"] == "GET"
    assert record["path"] == "/hardware"
    assert isinstance(record["time"], str) and record["time"]


def test_the_refusal_line_carries_no_header_value_and_no_query(launch, capsys):
    """A token pasted into an Origin or a query string must not reach stderr either."""
    listener = launch()

    assert request(listener, "/hardware", token=TOKEN, headers={"Origin": TOKEN})[0] == 403
    assert request(listener, f"/hardware?token={TOKEN}")[0] == 401

    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == 2
    for line in lines:
        assert TOKEN not in line
    assert json.loads(lines[1])["path"] == "/hardware", "the query is dropped with the path"


def test_every_error_body_carries_the_http_status_it_was_sent_with(launch):
    listener = launch()
    cases = [
        ("/hardware", {}, 401),
        ("/hardware", {"token": TOKEN, "headers": {"Origin": "https://evil.example"}}, 403),
        ("/nowhere", {"token": TOKEN}, 404),
    ]
    for path, kwargs, expected in cases:
        code, _, raw = request(listener, path, **kwargs)
        assert code == expected
        assert error_of(raw)["status"] == code


# --- the job routes, plan 04-02 ---------------------------------------------------------------
#
# A job is a request, a thread, a stream and a slot, so every test here uses a real server over a
# real socket and a fake module seam. The fakes emit the pinned event shape and end with `done`,
# because that is the modules' contract and the server's one slot frees on it; no test installs,
# downloads or opens a network connection.


def an_event(kind, message="", *, payload=None, fraction=None):
    """One event in the pinned shape; the job assigns the seq the stream carries."""
    return {
        "seq": 0,
        "type": kind,
        "message": message,
        "fraction": fraction,
        "payload": payload,
    }


def scripted(*events, result=True):
    """A module seam that emits the given events in order and records each call."""
    calls = []

    def module(name, confirmed, **kwargs):
        calls.append({"name": name, "confirmed": confirmed, **kwargs})
        for event in events:
            kwargs["emit"](event)
        return result

    module.calls = calls
    return module


def cancelled_on_request(result=False):
    """A download/install seam that emits progress, then ends when its cancel probe says so."""

    def module(name, confirmed, **kwargs):
        kwargs["emit"](an_event("progress", "started"))
        for _ in range(500):
            if kwargs["cancel"]():
                kwargs["emit"](
                    an_event("error", "cancelled", payload={"code": "cancelled"})
                )
                kwargs["emit"](an_event("done", "cancelled"))
                return result
            time.sleep(0.01)
        return result

    return module


def blocking(release):
    """A module seam that emits one event, waits for *release*, then emits `done`."""
    started = threading.Event()
    calls = []

    def module(name, confirmed, **kwargs):
        calls.append({"name": name, "confirmed": confirmed, **kwargs})
        kwargs["emit"](an_event("progress", "started"))
        started.set()
        release.wait(5)
        kwargs["emit"](an_event("done", "finished"))
        return True

    module.started = started
    module.calls = calls
    return module


def never_called(*args, **kwargs):
    raise AssertionError("no module may run for a request the server refused")


def wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def send_to(listener, path, *, method="POST", body=b"", headers=None, token=TOKEN):
    """One request with its own raw headers; ``body`` is sent as-is after them."""
    given = {}
    if token is not None:
        given["Authorization"] = f"Bearer {token}"
    given["Host"] = f"127.0.0.1:{listener.server_address[1]}"
    given.update(headers or {})
    connection = http.client.HTTPConnection(
        "127.0.0.1", listener.server_address[1], timeout=10
    )
    try:
        connection.putrequest(method, path, skip_host=True)
        for name, value in given.items():
            connection.putheader(name, value)
        connection.endheaders()
        if body:
            connection.send(body)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def post_job(
    listener,
    payload,
    *,
    content_type="application/json",
    headers=None,
    token=TOKEN,
    body=None,
):
    """POST /jobs with a JSON body the caller may override or omit."""
    raw = json.dumps(payload).encode() if body is None else body
    given = {}
    if content_type is not None:
        given["Content-Type"] = content_type
    given["Content-Length"] = str(len(raw))
    given.update(headers or {})
    return send_to(listener, "/jobs", body=raw, headers=given, token=token)


def open_stream(listener, job_id, *, last_event_id=None, timeout=10.0, rcvbuf=None):
    """A raw socket carrying GET /jobs/{id}/events, so a test can read it at its own pace."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if rcvbuf is not None:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, rcvbuf)
        sock.settimeout(timeout)
        sock.connect(("127.0.0.1", listener.server_address[1]))
    except OSError:
        sock.close()
        raise
    lines = [
        f"GET /jobs/{job_id}/events HTTP/1.0",
        f"Host: 127.0.0.1:{listener.server_address[1]}",
        f"Authorization: Bearer {TOKEN}",
    ]
    if last_event_id is not None:
        lines.append(f"Last-Event-ID: {last_event_id}")
    sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
    return sock


class StreamReader:
    """A tiny buffered reader for a live event stream."""

    def __init__(self, sock):
        self.sock = sock
        self.buffer = b""

    def read_until(self, marker):
        while marker not in self.buffer:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise AssertionError(f"the stream closed before {marker!r}")
            self.buffer += chunk
        head, _, self.buffer = self.buffer.partition(marker)
        return head

    def read_to_close(self):
        chunks = [self.buffer]
        while True:
            chunk = self.sock.recv(65536)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)


def sse_events(body: bytes):
    """The ``(id, event)`` pairs in a stream body, keepalive comments skipped."""
    events = []
    for block in body.decode("utf-8").split("\n\n"):
        block = block.strip("\n")
        if not block or block.startswith(":"):
            continue
        lines = block.splitlines()
        event_id = int(lines[0].split(":", 1)[1].strip())
        event = json.loads(lines[1].split(":", 1)[1].strip())
        events.append((event_id, event))
    return events


def stream_to_close(listener, job_id, *, last_event_id=None):
    """``(header text, body bytes)`` for a stream the server has already finished."""
    sock = open_stream(listener, job_id, last_event_id=last_event_id)
    try:
        raw = StreamReader(sock).read_to_close()
    finally:
        sock.close()
    head, _, body = raw.partition(b"\r\n\r\n")
    return head.decode("latin-1"), body


def posted_job_id(listener, payload):
    code, _, raw = post_job(listener, payload)
    assert code == 202, raw
    return json.loads(raw)["job_id"]


DOWNLOAD = {"kind": "download", "args": {"repo": "org/small", "confirmed": True}}


# --- AC-1: names, a literal true, and a body that is refused before it is read -----------------


def test_an_install_job_takes_a_name_and_the_literal_true(launch):
    release = threading.Event()
    module = blocking(release)
    listener = launch(install=module, scan=Recorder(this_mac(macos="26.1")))

    job_id = posted_job_id(
        listener, {"kind": "install", "args": {"engine": "mlxlm", "confirmed": True}}
    )

    assert len(job_id) == 16 and all(char in "0123456789abcdef" for char in job_id)
    assert module.started.wait(5)
    call = module.calls[0]
    assert call["name"] == "mlxlm"
    assert call["confirmed"] is True
    assert call["macos_major"] == 26, "the plan gets the scan's macOS generation"
    assert callable(call["emit"]) and callable(call["cancel"])

    release.set()
    head, body = stream_to_close(listener, job_id)
    assert [event["type"] for _, event in sse_events(body)] == ["progress", "done"]


QUICKBENCH = {
    "kind": "quickbench",
    "args": {"repo": "org/small", "confirmed": True, "osaurus": True},
}


def test_a_quickbench_job_carries_its_repo_and_the_osaurus_boolean(launch):
    """AC-1/AC-4: the kind takes the repo it measures and the client's pin consent."""
    release = threading.Event()
    module = blocking(release)
    listener = launch(quickbench=module)

    job_id = posted_job_id(listener, QUICKBENCH)

    assert module.started.wait(5)
    call = module.calls[0]
    assert call["name"] == "org/small"
    assert call["confirmed"] is True
    assert call["osaurus"] is True
    assert callable(call["emit"]) and callable(call["cancel"])

    release.set()
    _, body = stream_to_close(listener, job_id)
    assert [event["type"] for _, event in sse_events(body)] == ["progress", "done"]


@pytest.mark.parametrize("kind", ["download", "evict"])
def test_download_and_evict_take_a_repo_name(launch, kind):
    module = scripted(an_event("done", "finished"))
    listener = launch(download=module, evict=module)

    job_id = posted_job_id(
        listener, {"kind": kind, "args": {"repo": "org/small", "confirmed": True}}
    )

    assert wait_until(lambda: listener.jobs.running is None)
    assert module.calls[0]["name"] == "org/small"
    assert module.calls[0]["confirmed"] is True
    _, body = stream_to_close(listener, job_id)
    assert [event["type"] for _, event in sse_events(body)] == ["done"]


@pytest.mark.parametrize(
    "args, named",
    [
        ({"repo": "org/small", "confirmed": True}, "osaurus"),
        ({"repo": "org/small", "confirmed": True, "osaurus": "true"}, "osaurus"),
        ({"repo": "org/small", "confirmed": True, "osaurus": 1}, "osaurus"),
        (
            {"repo": "org/small", "confirmed": True, "osaurus": False, "engine": "mlxlm"},
            "engine",
        ),
        ({"repo": 5, "confirmed": True, "osaurus": False}, "repo"),
    ],
)
def test_quickbench_args_are_a_closed_set(launch, args, named):
    """`osaurus` is required and must be a JSON bool; nothing else is accepted either."""
    listener = launch(quickbench=never_called)

    code, _, raw = post_job(listener, {"kind": "quickbench", "args": args})

    assert code == 400
    error = error_of(raw)
    assert error["code"] == "bad_args"
    assert named in error["message"]


@pytest.mark.parametrize(
    "payload, named",
    [
        ({"kind": "install", "args": {"engine": "mlxlm", "confirmed": "true"}}, "confirmed"),
        ({"kind": "download", "args": {"repo": "org/small", "confirmed": 1}}, "confirmed"),
        ({"kind": "install", "args": {"engine": "mlxlm"}}, "confirmed"),
        (
            {"kind": "install", "args": {"engine": "mlxlm", "confirmed": True, "path": "/tmp"}},
            "path",
        ),
        ({"kind": "download", "args": {"confirmed": True}}, "repo"),
        ({"kind": "evict", "args": {"repo": 5, "confirmed": True}}, "repo"),
        ({"kind": "install", "args": "mlxlm"}, "args"),
    ],
)
def test_bad_args_is_400_naming_the_key_and_starts_no_job(launch, payload, named):
    """`confirmed` must be JSON true -- not "true" and not 1 -- and no thread may start."""
    listener = launch(
        install=never_called,
        download=scripted(an_event("done", "finished")),
        evict=never_called,
    )

    code, _, raw = post_job(listener, payload)

    assert code == 400
    error = error_of(raw)
    assert error["code"] == "bad_args"
    assert named in error["message"], error["message"]
    assert listener.jobs.jobs == {}, "a refused request created a job"
    assert post_job(listener, DOWNLOAD)[0] == 202, "the slot was left taken"


@pytest.mark.parametrize("kind", ["bench", "command", None, 7, ["install"]])
def test_an_unknown_kind_is_400_bad_kind(launch, kind):
    listener = launch(install=never_called)

    code, _, raw = post_job(
        listener, {"kind": kind, "args": {"engine": "mlxlm", "confirmed": True}}
    )

    assert code == 400
    assert error_of(raw)["code"] == "bad_kind"


@pytest.mark.parametrize(
    "content_type", ["text/plain", "application/x-www-form-urlencoded", None]
)
def test_a_non_json_content_type_is_415(launch, content_type):
    listener = launch(install=never_called)

    code, _, raw = post_job(
        listener,
        {"kind": "install", "args": {"engine": "mlxlm", "confirmed": True}},
        content_type=content_type,
    )

    assert code == 415
    assert error_of(raw)["code"] == "unsupported_media_type"


def test_a_missing_or_non_integer_content_length_is_413_before_the_body(launch):
    listener = launch(install=never_called)

    for length in (None, "three", "-1"):
        headers = {"Content-Type": "application/json"}
        if length is not None:
            headers["Content-Length"] = length
        code, _, raw = send_to(listener, "/jobs", body=b"", headers=headers)

        assert code == 413, length
        assert error_of(raw)["code"] == "body_too_large"
    assert listener.jobs.jobs == {}


def test_an_oversize_body_is_413_and_is_never_read(launch):
    """The client sends no body at all: a server that read one would block until its timeout."""
    listener = launch(install=never_called, timeout=1.0)

    code, _, raw = send_to(
        listener,
        "/jobs",
        body=b"",
        headers={"Content-Type": "application/json", "Content-Length": "4097"},
    )

    assert code == 413
    assert error_of(raw)["code"] == "body_too_large"


def test_a_body_of_exactly_the_limit_is_accepted(launch):
    listener = launch(download=scripted(an_event("done", "finished")))
    body = json.dumps(DOWNLOAD).encode()
    padded = body + b" " * (server.MAX_BODY_BYTES - len(body))

    code, _, raw = send_to(
        listener,
        "/jobs",
        body=padded,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Content-Length": str(len(padded)),
        },
    )

    assert code == 202
    job_id = json.loads(raw)["job_id"]
    assert wait_until(lambda: listener.jobs.get(job_id).done)


def test_invalid_json_is_400_bad_json(launch):
    listener = launch(install=never_called)

    code, _, raw = post_job(listener, None, body=b'{"kind": ')

    assert code == 400
    assert error_of(raw)["code"] == "bad_json"


# --- AC-2: the module owns the name and its refusal is an event --------------------------------


def test_the_modules_own_refusal_arrives_as_its_error_and_done_events(launch):
    module = scripted(
        an_event("error", "org/nope is not a catalog model", payload={"code": "unknown_repo"}),
        an_event("done", "download failed"),
        result=False,
    )
    listener = launch(download=module)

    job_id = posted_job_id(
        listener, {"kind": "download", "args": {"repo": "org/nope", "confirmed": True}}
    )

    _, body = stream_to_close(listener, job_id)
    events = [event for _, event in sse_events(body)]
    assert [event["type"] for event in events] == ["error", "done"]
    assert events[0]["payload"] == {"code": "unknown_repo"}


def test_a_real_evict_refusal_ends_its_stream_and_frees_the_slot(launch, tmp_path):
    """The real `fetch.evict`, not a fake: its refusal is `error` + its own `done`, and the
    slot is free for the next job instead of 409 until restart."""
    ledger = tmp_path / "fetched.json"
    ledger.write_text(json.dumps({"repos": {}}), encoding="utf-8")
    real_evict = functools.partial(
        fetch.evict,
        cache_dir=str(tmp_path / "cache"),
        ledger_path=str(ledger),
        log_path=str(tmp_path / "fetch-log.jsonl"),
    )
    listener = launch(evict=real_evict)
    payload = {"kind": "evict", "args": {"repo": "org/nope", "confirmed": True}}

    job_id = posted_job_id(listener, payload)

    _, body = stream_to_close(listener, job_id)
    events = [event for _, event in sse_events(body)]
    assert [event["type"] for event in events] == ["error", "done"]
    assert events[0]["payload"]["code"] == "unknown_repo"
    assert events[-1]["message"] == "fetch ended", "the module's done, not the server's guard"

    assert post_job(listener, payload)[0] == 202, "the slot did not free at the module's done"


def test_a_raising_module_ends_the_stream_with_internal_and_done_after_its_own_seq(launch):
    def broken(name, confirmed, *, emit, cancel):
        emit(an_event("log", "about to fail"))
        raise RuntimeError("the module broke")

    listener = launch(download=broken)

    job_id = posted_job_id(listener, DOWNLOAD)

    _, body = stream_to_close(listener, job_id)
    events = sse_events(body)
    assert [event_id for event_id, _ in events] == [1, 2, 3]
    assert [event["type"] for _, event in events] == ["log", "error", "done"]
    assert events[1][1]["payload"] == {"code": "internal"}
    assert "the module broke" in events[1][1]["message"]


# --- AC-3: one job at a time -------------------------------------------------------------------


def test_a_second_job_while_one_is_running_is_409_busy_naming_the_job(launch):
    release = threading.Event()
    module = blocking(release)
    listener = launch(download=module, evict=module)

    job_id = posted_job_id(listener, DOWNLOAD)
    assert module.started.wait(5)

    for payload in (DOWNLOAD, {"kind": "evict", "args": {"repo": "org/x", "confirmed": True}}):
        code, _, raw = post_job(listener, payload)

        assert code == 409, payload
        error = error_of(raw)
        assert error["code"] == "busy"
        assert job_id in error["message"], "the refusal has to name the job holding the slot"
    assert len(module.calls) == 1, "a refused request started a second job"

    release.set()
    assert wait_until(lambda: listener.jobs.running is None)
    assert post_job(listener, DOWNLOAD)[0] == 202, "the slot did not free at done"


# --- AC-4: the event stream --------------------------------------------------------------------


def test_the_stream_frames_events_and_closes_after_done(launch):
    module = scripted(
        an_event("progress", "one", fraction=0.5, payload={"step": "x"}),
        an_event("result", "two", payload={"installed": True}),
        an_event("done", "finished"),
    )
    listener = launch(download=module)
    job_id = posted_job_id(listener, DOWNLOAD)
    assert wait_until(lambda: listener.jobs.get(job_id).done)

    head, body = stream_to_close(listener, job_id)

    lines = head.splitlines()
    assert lines[0].endswith("200 OK"), lines[0]
    lowered = head.lower()
    assert "content-type: text/event-stream" in lowered
    assert "cache-control: no-store" in lowered
    assert "access-control-" not in lowered, "a stream must not carry a CORS header"
    assert body.startswith(b"id: 1\ndata: ")
    events = sse_events(body)
    assert [event_id for event_id, _ in events] == [1, 2, 3]
    assert [event["type"] for _, event in events] == ["progress", "result", "done"]
    assert events[0][1]["payload"] == {"step": "x"}
    assert events[0][1]["fraction"] == 0.5


def test_the_stream_replays_after_last_event_id(launch):
    module = scripted(
        an_event("log", "one"),
        an_event("progress", "two"),
        an_event("result", "three"),
        an_event("done", "four"),
    )
    listener = launch(download=module)
    job_id = posted_job_id(listener, DOWNLOAD)
    assert wait_until(lambda: listener.jobs.get(job_id).done)

    _, body = stream_to_close(listener, job_id, last_event_id=2)

    assert [event_id for event_id, _ in sse_events(body)] == [3, 4]


@pytest.mark.parametrize("value", ["abc", "-1", "1.5", ""])
def test_a_bad_last_event_id_is_400_bad_event_id(launch, value):
    listener = launch(download=scripted(an_event("done", "finished")))
    job_id = posted_job_id(listener, DOWNLOAD)
    assert wait_until(lambda: listener.jobs.get(job_id).done)

    code, _, raw = send_to(
        listener,
        f"/jobs/{job_id}/events",
        method="GET",
        headers={"Last-Event-ID": value},
    )

    assert code == 400
    assert error_of(raw)["code"] == "bad_event_id"


def test_a_last_event_id_beyond_the_last_stored_seq_waits_for_new_events(launch):
    release = threading.Event()

    def module(name, confirmed, *, emit, cancel):
        emit(an_event("progress", "one"))
        release.wait(5)
        emit(an_event("progress", "two"))
        emit(an_event("done", "three"))
        return True

    listener = launch(download=module)
    job_id = posted_job_id(listener, DOWNLOAD)
    assert wait_until(lambda: len(listener.jobs.get(job_id).events) == 1)

    sock = open_stream(listener, job_id, last_event_id=2)
    try:
        reader = StreamReader(sock)
        head = reader.read_until(b"\r\n\r\n").decode("latin-1")
        assert " 200 " in head.splitlines()[0]
        release.set()
        block = reader.read_until(b"\n\n").decode("utf-8")
    finally:
        sock.close()

    assert block.startswith("id: 3"), "the client's claimed seq was not re-sent"


def test_a_job_quiet_for_longer_than_the_socket_timeout_still_streams(launch):
    """The wait is on the job's condition: a 0.2 s socket timeout does not cut a 0.5 s gap."""
    def module(name, confirmed, *, emit, cancel):
        emit(an_event("progress", "one"))
        time.sleep(0.5)
        emit(an_event("done", "two"))
        return True

    listener = launch(download=module, timeout=0.2, keepalive_s=5.0)

    job_id = posted_job_id(listener, DOWNLOAD)

    _, body = stream_to_close(listener, job_id)
    assert [event["type"] for _, event in sse_events(body)] == ["progress", "done"]


def test_a_client_that_never_reads_is_dropped_at_the_write_timeout_while_the_job_runs(launch):
    """Clearing the socket timeout would leave this handler blocked in send forever."""
    release = threading.Event()

    def module(name, confirmed, *, emit, cancel):
        for number in range(300):
            emit(an_event("progress", "x" * 8192, payload={"n": number}))
        release.wait(10)
        emit(an_event("done", "finished"))
        return True

    listener = launch(download=module, timeout=0.2, keepalive_s=5.0)
    job_id = posted_job_id(listener, DOWNLOAD)

    sock = open_stream(listener, job_id, rcvbuf=4096)
    try:
        # Read the headers byte by byte, so the handler is provably in its stream and this
        # client has provably stopped reading before the timeout is expected to fire.
        head = b""
        while not head.endswith(b"\r\n\r\n"):
            chunk = sock.recv(1)
            assert chunk, "the stream closed before its headers"
            head += chunk
        assert b" 200 " in head.split(b"\r\n")[0]

        handlers = lambda: [
            thread
            for thread in threading.enumerate()
            if "process_request_thread" in thread.name
        ]
        assert wait_until(lambda: handlers() == [], timeout=5.0), (
            "a client that stopped reading held its handler thread"
        )
        assert not listener.jobs.get(job_id).done, "a dropped stream must never end the job"
    finally:
        sock.close()
        release.set()

    assert wait_until(lambda: listener.jobs.running is None)
    _, body = stream_to_close(listener, job_id)
    assert sse_events(body)[-1][1]["type"] == "done"


def test_keepalive_is_written_while_the_job_is_quiet(launch):
    release = threading.Event()
    module = blocking(release)
    listener = launch(download=module, keepalive_s=0.05)

    job_id = posted_job_id(listener, DOWNLOAD)
    assert module.started.wait(5)

    sock = open_stream(listener, job_id, timeout=5.0)
    try:
        reader = StreamReader(sock)
        reader.read_until(b"\r\n\r\n")
        first = reader.read_until(b"\n\n")
        assert first.startswith(b"id: 1"), first
        keepalive = reader.read_until(b"\n\n")
        assert keepalive == b": keepalive", keepalive
        release.set()
        rest = reader.read_to_close().decode("utf-8")
    finally:
        sock.close()

    assert 'id: 2' in rest and '"type": "done"' in rest


def test_a_client_disconnect_leaves_the_job_running_and_holds_the_slot_until_done(launch):
    release = threading.Event()

    def module(name, confirmed, *, emit, cancel):
        emit(an_event("progress", "one"))
        release.wait(5)
        emit(an_event("progress", "two"))
        emit(an_event("done", "three"))
        return True

    listener = launch(download=module, evict=scripted(an_event("done", "finished")))
    job_id = posted_job_id(listener, DOWNLOAD)
    assert wait_until(lambda: len(listener.jobs.get(job_id).events) == 1)

    sock = open_stream(listener, job_id)
    reader = StreamReader(sock)
    reader.read_until(b"\r\n\r\n")
    reader.read_until(b"\n\n")
    sock.close()

    assert not listener.jobs.get(job_id).done
    code, _, raw = post_job(
        listener, {"kind": "evict", "args": {"repo": "org/x", "confirmed": True}}
    )
    assert code == 409 and error_of(raw)["code"] == "busy"

    release.set()
    assert wait_until(lambda: listener.jobs.running is None)
    _, body = stream_to_close(listener, job_id)
    assert [event["type"] for _, event in sse_events(body)] == [
        "progress",
        "progress",
        "done",
    ]


def test_past_the_event_cap_the_job_ends_with_too_many_events_and_done(launch):
    def module(name, confirmed, *, emit, cancel):
        for number in range(server.MAX_EVENTS + 50):
            emit(an_event("log", "x", payload={"n": number}))
        emit(an_event("done", "the module's own done"))
        return True

    listener = launch(download=module)
    job_id = posted_job_id(listener, DOWNLOAD)
    assert wait_until(lambda: listener.jobs.get(job_id).done)

    events = listener.jobs.get(job_id).events
    assert len(events) == server.MAX_EVENTS
    assert events[-2]["type"] == "error"
    assert events[-2]["payload"] == {"code": "too_many_events"}
    assert events[-1]["type"] == "done"
    assert wait_until(lambda: listener.jobs.running is None)
    assert post_job(listener, DOWNLOAD)[0] == 202


def test_an_unknown_job_id_is_404_unknown_job_on_both_routes(launch):
    listener = launch()
    unknown = "0" * 16

    for method, path in (("GET", f"/jobs/{unknown}/events"), ("POST", f"/jobs/{unknown}/cancel")):
        code, _, raw = send_to(listener, path, method=method)

        assert code == 404, path
        assert error_of(raw)["code"] == "unknown_job"


def test_a_job_path_without_an_action_or_with_a_bad_id_is_404(launch):
    listener = launch()

    for path in ("/jobs/" + "0" * 16, "/jobs/xyz/events", "/jobs/" + "0" * 15 + "/events"):
        code, _, raw = send_to(listener, path, method="GET")

        assert code == 404, path
        assert error_of(raw)["code"] == "not_found"


# --- AC-5: cancel ------------------------------------------------------------------------------


@pytest.mark.parametrize("kind, args", [
    ("download", {"repo": "org/small", "confirmed": True}),
    ("install", {"engine": "mlxlm", "confirmed": True}),
])
def test_cancel_makes_the_modules_probe_answer_true_and_the_stream_ends_cancelled(
    launch, kind, args
):
    module = cancelled_on_request()
    listener = launch(
        download=module, install=module, scan=Recorder(this_mac()),
    )
    job_id = posted_job_id(listener, {"kind": kind, "args": args})
    assert wait_until(lambda: len(listener.jobs.get(job_id).events) == 1)

    code, _, raw = send_to(listener, f"/jobs/{job_id}/cancel")

    assert code == 202
    assert json.loads(raw) == {"job_id": job_id}
    _, body = stream_to_close(listener, job_id)
    events = [event for _, event in sse_events(body)]
    assert [event["type"] for event in events] == ["progress", "error", "done"]
    assert events[1]["payload"] == {"code": "cancelled"}


def test_cancel_of_an_evict_job_is_409_not_cancellable(launch):
    release = threading.Event()
    module = blocking(release)
    listener = launch(evict=module)
    job_id = posted_job_id(
        listener, {"kind": "evict", "args": {"repo": "org/small", "confirmed": True}}
    )
    assert module.started.wait(5)

    code, _, raw = send_to(listener, f"/jobs/{job_id}/cancel")

    assert code == 409
    assert error_of(raw)["code"] == "not_cancellable"
    release.set()
    assert wait_until(lambda: listener.jobs.running is None)


def test_cancel_of_a_finished_job_is_409_job_finished(launch):
    listener = launch(download=scripted(an_event("done", "finished")))
    job_id = posted_job_id(listener, DOWNLOAD)
    assert wait_until(lambda: listener.jobs.get(job_id).done)

    code, _, raw = send_to(listener, f"/jobs/{job_id}/cancel")

    assert code == 409
    assert error_of(raw)["code"] == "job_finished"


# --- AC-6: the stderr record and shutdown ------------------------------------------------------


def test_each_job_writes_one_start_and_one_end_line_and_nothing_else(launch, capsys):
    module = scripted(
        an_event("error", "org/nope is not a catalog model", payload={"code": "unknown_repo"}),
        an_event("done", "download failed"),
        result=False,
    )
    listener = launch(download=module)

    job_id = posted_job_id(
        listener, {"kind": "download", "args": {"repo": "org/nope", "confirmed": True}}
    )
    assert wait_until(lambda: listener.jobs.running is None)

    lines = []
    deadline = time.monotonic() + 5
    while len(lines) < 2 and time.monotonic() < deadline:
        lines.extend(capsys.readouterr().err.splitlines())
        if len(lines) < 2:
            time.sleep(0.01)

    assert len(lines) == 2, lines
    start, end = (json.loads(line) for line in lines)
    assert set(start) == {"job", "kind", "name", "time"}
    assert start["job"] == job_id
    assert start["kind"] == "download"
    assert start["name"] == "org/nope"
    assert set(end) == {"job", "ok", "code", "time"}
    assert end["job"] == job_id
    assert end["ok"] is False
    assert end["code"] == "unknown_repo"
    assert TOKEN not in "".join(lines)


def test_shutdown_cancel_waits_for_a_running_job_to_its_done(launch):
    release = threading.Event()
    module = blocking(release)
    listener = launch(download=module)
    job_id = posted_job_id(listener, DOWNLOAD)
    assert module.started.wait(5)

    threading.Timer(0.2, release.set).start()
    began = time.monotonic()
    listener.jobs.cancel_and_wait(5)
    elapsed = time.monotonic() - began

    assert elapsed >= 0.1, "cancel_and_wait returned before the job finished"
    assert listener.jobs.get(job_id).done
    assert module.calls[0]["cancel"](), "a running download's cancel flag was not set"


def test_shutdown_does_not_cancel_an_evict_and_waits_for_it(launch):
    release = threading.Event()
    module = blocking(release)
    listener = launch(evict=module)
    job_id = posted_job_id(
        listener, {"kind": "evict", "args": {"repo": "org/small", "confirmed": True}}
    )
    assert module.started.wait(5)

    threading.Timer(0.2, release.set).start()
    began = time.monotonic()
    listener.jobs.cancel_and_wait(5)
    elapsed = time.monotonic() - began

    assert elapsed >= 0.1
    assert listener.jobs.get(job_id).done, "an evict was abandoned by the shutdown wait"


# --- AC-7: the job routes are behind the 04-01 guard -------------------------------------------


def test_every_job_route_is_behind_the_04_01_guard(launch):
    install = never_called
    download = never_called
    evict = never_called
    listener = launch(install=install, download=download, evict=evict)
    paths = [("POST", "/jobs"), ("GET", f"/jobs/{'0' * 16}/events"),
             ("POST", f"/jobs/{'0' * 16}/cancel")]

    for method, path in paths:
        code, _, raw = send_to(listener, path, method=method, token=None)
        assert code == 401 and error_of(raw)["code"] == "unauthorized", (method, path)

        code, _, raw = send_to(
            listener, path, method=method, headers={"Origin": "https://evil.example"}
        )
        assert code == 403 and error_of(raw)["code"] == "origin_refused", (method, path)

        code, _, raw = send_to(listener, path, method=method, headers={"Host": "evil.example"})
        assert code == 403 and error_of(raw)["code"] == "bad_host", (method, path)

    assert listener.jobs.jobs == {}, "a refused request created a job"


def test_a_job_response_carries_no_cors_header(launch):
    listener = launch(
        install=never_called,
        download=scripted(an_event("done", "finished")),
        evict=never_called,
    )

    responses = [
        post_job(listener, DOWNLOAD),
        post_job(listener, {"kind": "install", "args": {"engine": "x", "confirmed": "yes"}}),
        send_to(listener, "/jobs/" + "0" * 16 + "/events", method="GET"),
    ]

    assert [code for code, _, _ in responses] == [202, 400, 404]
    for code, headers, _ in responses:
        assert not [
            name for name in headers if name.lower().startswith("access-control-")
        ], code


# --- plan 045-02a: the server's own hardening (AC-2 to AC-5) -----------------------------------
#
# Each guard is reverted in the plan's red-check; the test named beside it is the one that
# fails. Nothing here starts a runtime, downloads or touches this Mac's real directories.


def test_a_start_log_that_raises_answers_500_and_frees_the_slot(launch, monkeypatch):
    """AC-2: the slot is claimed before the start line, so a raise there must end the job."""
    listener = launch(download=scripted(an_event("done", "finished")))

    def broken(record):
        raise RuntimeError("stderr is gone")

    with monkeypatch.context() as patch:
        patch.setattr(server, "_log_job", broken)
        code, _, raw = post_job(listener, DOWNLOAD)

    assert code == 500
    assert error_of(raw)["code"] == "internal"
    failed = list(listener.jobs.jobs.values())[0]
    assert [event["type"] for event in failed.events] == ["error", "done"]
    assert failed.events[0]["payload"] == {"code": "internal"}
    assert post_job(listener, DOWNLOAD)[0] == 202, "the failed request kept the slot"


def test_a_thread_that_will_not_start_answers_500_and_frees_the_slot(launch, monkeypatch):
    """AC-2: ``Thread.start`` itself is the other raise before a job thread exists."""
    listener = launch(download=scripted(an_event("done", "finished")))

    class NoThreads:
        def __getattr__(self, name):
            if name == "Thread":
                def refuse(*args, **kwargs):
                    raise RuntimeError("the thread would not start")
                return refuse
            return getattr(threading, name)

    with monkeypatch.context() as patch:
        patch.setattr(server, "threading", NoThreads())
        code, _, raw = post_job(listener, DOWNLOAD)

    assert code == 500
    assert error_of(raw)["code"] == "internal"
    failed = list(listener.jobs.jobs.values())[0]
    assert [event["type"] for event in failed.events] == ["error", "done"]
    assert failed.events[0]["payload"] == {"code": "internal"}
    assert post_job(listener, DOWNLOAD)[0] == 202, "the failed request kept the slot"


def test_the_handler_thread_cap_closes_the_extra_connection_and_releases_at_timeout(launch):
    """AC-3: a full server closes the next connection at once, and a timeout frees the slot."""
    listener = launch(timeout=0.5)
    baseline = threading.active_count()
    quiet = []
    try:
        for _ in range(server.MAX_HANDLER_THREADS):
            quiet.append(socket.create_connection(listener.server_address, timeout=5))
        assert wait_until(lambda: listener.handler_slots._value == 0), (
            "the server did not take one slot per held connection"
        )

        extra = socket.create_connection(listener.server_address, timeout=5)
        extra.settimeout(5)
        assert extra.recv(1) == b"", "the connection beyond the cap was never closed"
        extra.close()
        assert threading.active_count() <= baseline + server.MAX_HANDLER_THREADS

        for connection in quiet:
            assert connection.recv(1) == b"", "a held connection did not time out"
        assert wait_until(
            lambda: listener.handler_slots._value == server.MAX_HANDLER_THREADS
        ), "the handler slots were not released at the socket timeout"
        assert request(listener, "/hardware", token=TOKEN)[0] == 200
    finally:
        for connection in quiet:
            connection.close()


def test_a_fifth_stream_on_one_job_is_429_and_a_freed_slot_admits_another(launch):
    """AC-3: four streams per job, and the slot returns when one ends by any path."""
    release = threading.Event()
    module = blocking(release)
    listener = launch(download=module, keepalive_s=0.05)
    job_id = posted_job_id(listener, DOWNLOAD)
    assert module.started.wait(5)
    job = listener.jobs.get(job_id)

    streams = []
    try:
        for _ in range(server.MAX_STREAMS_PER_JOB):
            sock = open_stream(listener, job_id)
            reader = StreamReader(sock)
            head = reader.read_until(b"\r\n\r\n").decode("latin-1")
            assert " 200 " in head.splitlines()[0], head
            streams.append((sock, reader))
        assert job.streams == server.MAX_STREAMS_PER_JOB

        code, _, raw = send_to(listener, f"/jobs/{job_id}/events", method="GET")
        assert code == 429
        assert error_of(raw)["code"] == "too_many_streams"

        for _, reader in streams:
            block = reader.read_until(b"\n\n").decode("utf-8")
            assert '"type": "progress"' in block, "a held stream stopped streaming"

        streams[0][0].close()
        assert wait_until(lambda: job.streams == server.MAX_STREAMS_PER_JOB - 1), (
            "a disconnected stream did not give its slot back"
        )
        replacement = open_stream(listener, job_id)
        reader = StreamReader(replacement)
        assert b" 200 " in reader.read_until(b"\r\n\r\n")
        assert job.streams == server.MAX_STREAMS_PER_JOB

        release.set()
        assert wait_until(lambda: job.done)
        assert wait_until(lambda: job.streams == 0), "a finished stream did not give its slot back"
    finally:
        for sock, _ in streams:
            sock.close()
        release.set()


def test_a_refused_unknown_path_is_logged_as_unknown_not_echoed(launch, capsys):
    """AC-4: a refusal may not write a path the router does not serve -- it is client text."""
    listener = launch()
    secret = "a-client-supplied-path-segment"

    code, _, _ = request(listener, f"/{secret}", token=None)

    assert code == 401
    stderr = capsys.readouterr().err
    assert secret not in stderr
    assert json.loads(stderr.splitlines()[0])["path"] == "<unknown>"


def test_a_refused_served_job_path_keeps_its_path_in_the_log(launch, capsys):
    """AC-4: the served routes still name themselves, so a probe leaves a usable trace."""
    listener = launch()

    code, _, _ = send_to(
        listener, f"/jobs/{'0' * 16}/events", method="GET", token=None
    )

    assert code == 401
    assert json.loads(capsys.readouterr().err.splitlines()[0])["path"] == (
        f"/jobs/{'0' * 16}/events"
    )


def test_a_hung_hardware_tool_is_500_internal_and_not_a_hang(launch):
    """AC-5: ``hardware._run`` is bounded, and the timeout surfaces as a 500."""
    def hung(argv):
        raise subprocess.TimeoutExpired(argv, hardware.TOOL_TIMEOUT_S)

    listener = launch(scan=functools.partial(hardware.scan, run=hung, volume_paths=lambda: []))

    code, _, raw = request(listener, "/hardware", token=TOKEN)

    assert code == 500
    error = error_of(raw)
    assert error["code"] == "internal"
    assert "timed out" in error["message"].lower() or "timeout" in error["message"].lower()
