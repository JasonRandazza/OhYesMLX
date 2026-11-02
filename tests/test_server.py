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
import http.client
import json
import socket
import threading

import pytest

from ohyesmlx import catalog, engines, hardware, recommend, server

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
        listener = server.make_server(0, **kwargs)
        thread = threading.Thread(target=listener.serve_forever, daemon=True)
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
    for path in ("/hardware", "/engines", "/recommendations"):
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
        "measured_here",
    }
    assert pick["params_b"] == 3.0
    assert isinstance(pick["size_bytes"], int)
    assert pick["fit"] == "comfortable"

    large = MODELS[1]
    assert body["excluded"][0] == {
        "model_id": large.repo,
        "reason": recommend.exclusion_reason(large, this_mac(), this_mac().disk_free_bytes),
    }


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
