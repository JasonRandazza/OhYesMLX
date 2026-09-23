Scope: Read `tests/*.py` and `ohyesmlx/*.py`; project test command passed (497 tests).

### F1 [high] Measurement fakes omit the runtime API key
Where: `tests/test_measure.py:87-100,137-145`; `ohyesmlx/runtimes.py:959-960`; `ohyesmlx/measure.py:928-937`
Evidence:
> `def __init__(self, runtime, model_id, port, version, cold_load_s, recorder, api_key=None):`
> `self.api_key = api_key`
> `handle = FakeHandle(`
> `    self.name,`
> `    f"{self.name}/{Path(artifact_dir).name}",`
> `    self.port,`
> `    self.version,`
> `    self.cold_load_s,`
> `    self.recorder,`
> `)`
> `    def api_key(self) -> str | None:`
> `        return OMLX_API_KEY`
> `            api_key=handle.api_key,`
Failure: `FakeRuntime` always creates a handle with `api_key=None`; the fake transport accepts that call without checking authentication. Removing key propagation from `_request` would leave these measurement tests green, even though real oMLX requires the bearer key and measured requests would fail with 401. The transport's separate bearer-header test does not cover this wiring.
Fix: Give the measurement fake an API-key path and assert the key reaches `transport.chat` for an oMLX-shaped handle.

### F2 [high] Transport tests never exercise HTTP or content-type rejection
Where: `tests/test_transport.py:45-58`; `ohyesmlx/transport.py:201-212`
Evidence:
> `self.send_response(200)`
> `self.send_header("Content-Type", "text/event-stream")`
> `if response.status != 200:`
> `    _call_before_deadline(response.read, connection, deadline)`
> `    raise TransportError(`
> `        f"chat request returned HTTP {response.status}",`
> `        reason="http_status",`
> `        http_status=response.status,`
> `    )`
> `if "text/event-stream" not in response.getheader(`
> `    "Content-Type", ""`
> `):`
Failure: The local SSE server always returns HTTP 200 with an event-stream content type, so regressions in the 401/500 and non-SSE rejection paths cannot fail this suite. A server returning JSON or an auth error could then be handled incorrectly without a transport test noticing.
Fix: Let the test server configure status and content type; assert the resulting failed `Observation` and its error for each rejection branch.

### F3 [medium] Request-deadline behavior has no timeout test
Where: `tests/test_transport.py:331-345`; `ohyesmlx/transport.py:92-117,239-255`
Evidence:
> `def test_first_chunk_more_than_a_second_after_headers_is_survived(server):`
> `        pre_body_delay_s=1.2,`
> `    )`
> `    observation = chat(server.base_url, "model", MESSAGES, max_tokens=16)`
> `    assert observation.ok, observation.error`
> `    while not completed.wait(`
> `        min(0.1, max(0.0, deadline - time.monotonic()))`
> `    ):`
> `        if time.monotonic() >= deadline:`
> `            connection.close()`
> `            raise TransportError("request timed out", reason="timeout")`
Failure: The delayed-stream test proves a 1.2-second delay is survived under the default 600-second deadline, but no test sets a short deadline and verifies the request returns a timeout observation. A broken or removed deadline guard could therefore hang on an endpoint that never answers.
Fix: Add a delayed-response case with a short `timeout_s` and assert the failed observation reports `request timed out`.

Unverified suspicions:
- I did not run coverage; untested-branch findings come from comparing the source paths with the test cases, not a coverage report.
