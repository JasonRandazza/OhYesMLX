"""Checks for ohyesmlx.measure.

``ohyesmlx/transport.py`` and ``ohyesmlx/runtimes.py`` are written against the same
``docs/interfaces.md`` by other workers, so nothing here opens a socket or spawns a
server: the fakes below are the module contract written down twice, and they record the
order of every start, request, stop and cooldown so the loop's shape can be checked
without a Mac and without a model.

The measurement loop's own rules are checked here too: one decode definition, warmups that
never reach the samples, a fixed output length, pinned sampling, cold load kept out of the
requests, and results that survive the process that wrote them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields
from pathlib import Path
from types import SimpleNamespace

import pytest

from ohyesmlx import measure, report

WARMUPS = 3
MEASURED = 5


@dataclass(frozen=True)
class FakeObservation:
    """``ohyesmlx.transport.Observation``, field for field."""

    ok: bool = True
    error: str | None = None
    ttft_s: float | None = 0.5
    last_content_s: float | None = 2.5
    total_s: float = 2.6
    prompt_tokens: int | None = 64
    completion_tokens: int | None = 100
    reasoning_tokens: int | None = None
    content_event_count: int = 100
    text: str = "measured"
    reasoning_text: str = ""
    token_source: str = "usage"


class Recorder:
    """Every side effect the loop makes, in the order it made it."""

    def __init__(self):
        self.events: list[tuple] = []

    def log(self, kind, *payload):
        self.events.append((kind, *payload))

    def kinds(self):
        return [event[0] for event in self.events]

    def of(self, kind):
        return [event[1:] for event in self.events if event[0] == kind]


class FakeHandle:
    def __init__(self, runtime, model_id, port, version, cold_load_s, recorder, api_key=None):
        self.pid = 40000 + port
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}/v1"
        self.model_id = model_id
        self.version = version
        self.cold_load_s = cold_load_s
        self.runtime = runtime
        self.recorder = recorder
        self.api_key = api_key
        self.stops = 0

    def stop(self):
        self.stops += 1
        self.recorder.log("stop", self.runtime)


class FakeRuntime:
    """``ohyesmlx.runtimes.Runtime``: one port, one start, one Handle."""

    def __init__(self, name, recorder, *, port=8081, version="0.31.3", cold_load_s=7.5,
                 start_error=None, fail_from_attempt=None):
        self.name = name
        self.port = port
        self.version = version
        self.cold_load_s = cold_load_s
        self.start_error = start_error
        self.fail_from_attempt = fail_from_attempt
        self.recorder = recorder
        self.attempts = 0
        self.handles: list[FakeHandle] = []

    def start(self, artifact_dir, model_id):
        self.attempts += 1
        self.recorder.log("start", self.name, artifact_dir, model_id)
        if self.start_error is not None and (
            self.fail_from_attempt is None or self.attempts >= self.fail_from_attempt
        ):
            raise self.start_error
        handle = FakeHandle(
            self.name,
            f"{self.name}/{Path(artifact_dir).name}",
            self.port,
            self.version,
            self.cold_load_s,
            self.recorder,
        )
        self.handles.append(handle)
        return handle


class FakeTransport:
    """``ohyesmlx.transport``: streaming is a detail, the Observation is the interface."""

    Observation = FakeObservation

    def __init__(self, recorder, responder=None):
        self.recorder = recorder
        self.responder = responder or (lambda call: FakeObservation())
        self.calls: list[SimpleNamespace] = []
        self.responses: list[FakeObservation] = []

    def chat(self, base_url, model, messages, *, max_tokens, temperature=0.0, seed=None,
             timeout_s=600.0, api_key=None, token_counter=None):
        kinds = self.recorder.kinds()
        visit = kinds.count("start")
        since_start = kinds[len(kinds) - 1 - kinds[::-1].index("start"):]
        call = SimpleNamespace(
            base_url=base_url,
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            seed=seed,
            timeout_s=timeout_s,
            token_counter=token_counter,
            visit=visit,
            visit_index=sum(1 for kind in since_start if kind == "chat"),
            index=len(self.calls),
        )
        self.calls.append(call)
        self.recorder.log("chat", call)
        response = self.responder(call)
        self.responses.append(response)
        return response

    def calls_by_visit(self):
        visits: dict[int, list[SimpleNamespace]] = {}
        for call in self.calls:
            visits.setdefault(call.visit, []).append(call)
        return visits


class FakeTokenCounter:
    def __init__(self, model_dir, recorder):
        self.model_dir = model_dir
        self.recorder = recorder
        self.counted: list[str] = []
        recorder.log("counter", model_dir)

    def count(self, text):
        self.counted.append(text)
        return len(text)


class FakeSampler:
    def __init__(self, pid, peaks, recorder, interval_s=1.0):
        self.pid = pid
        self.peaks = peaks
        self.recorder = recorder
        self.interval_s = interval_s
        self.stops = 0

    def start(self):
        self.recorder.log("sample", self.pid)
        return self

    def stop(self):
        self.stops += 1
        peak = self.peaks.pop(0) if self.peaks else 100.0
        self.recorder.log("sampled", self.pid, peak)
        return {
            "pid": self.pid,
            "interval_s": self.interval_s,
            "duration_s": 1.0,
            "n_samples": 1,
            "peak_mb": peak,
            "samples": [{"t": 0.0, "mb": peak}],
            "memory_split": {},
            "power": {"available": False},
            "gpu_wired_limit": {"mb": 0, "raised": False},
            "error": None,
        }


class FakeSampleModule:
    """Stands in for ``ohyesmlx.sample`` so no ``footprint`` call is made against a fake pid."""

    def __init__(self, recorder, peaks):
        self.recorder = recorder
        self.peaks = list(peaks)
        self.samplers: list[FakeSampler] = []

    def Sampler(self, pid, interval_s=1.0):
        sampler = FakeSampler(pid, self.peaks, self.recorder, interval_s=interval_s)
        self.samplers.append(sampler)
        return sampler


class Harness:
    def __init__(self, monkeypatch, tmp_path):
        self.recorder = Recorder()
        self.runtimes = SimpleNamespace(RUNTIMES={})
        self.transport = FakeTransport(self.recorder)
        self.sample = FakeSampleModule(self.recorder, [250.0, 100.0])
        self.token_counter = SimpleNamespace(
            TokenCounter=lambda model_dir: FakeTokenCounter(model_dir, self.recorder)
        )
        self.tmp_path = tmp_path

        monkeypatch.setattr(measure, "transport", self.transport)
        monkeypatch.setattr(measure, "runtimes", self.runtimes)
        monkeypatch.setattr(measure, "token_counter", self.token_counter)
        monkeypatch.setattr(measure, "sample", self.sample)
        monkeypatch.setattr(measure, "_sleep", lambda seconds: self.recorder.log("sleep", seconds))

    def add_runtime(self, name, **kwargs) -> FakeRuntime:
        runtime = FakeRuntime(name, self.recorder, **kwargs)
        self.runtimes.RUNTIMES[name] = runtime
        return runtime

    def cell(self, cell_id, runtime, label="affine-4bit") -> measure.Cell:
        return measure.Cell(
            id=cell_id,
            runtime=runtime,
            artifact_dir=str(self.tmp_path / "artifacts" / cell_id),
            label=label,
        )

    def run(self, cells, *, workload=None, results_dir=None, **kwargs):
        return measure.run_cells(
            cells,
            workload if workload is not None else {"id": "short-chat", "messages": [{"role": "user", "content": "hi"}]},
            results_dir=str(results_dir if results_dir is not None else self.tmp_path / "results"),
            **kwargs,
        )

    def results_file(self, results_dir=None) -> Path:
        root = results_dir if results_dir is not None else self.tmp_path / "results"
        return Path(root) / measure.RESULTS_FILENAME

    def header(self, results_dir=None) -> dict:
        """Line 1: the pins and the workload every cell in the file was measured under."""
        return json.loads(self.results_file(results_dir).read_text().splitlines()[0])

    def lines(self, results_dir=None) -> list[dict]:
        """The cell records on disk, the run header line excluded."""
        return [
            json.loads(line)
            for line in self.results_file(results_dir).read_text().splitlines()[1:]
        ]

    def sleeps(self):
        return [event[0] for event in self.recorder.of("sleep")]


@pytest.fixture
def harness(monkeypatch, tmp_path):
    return Harness(monkeypatch, tmp_path)


def starts(harness):
    return [runtime for runtime, _artifact_dir, _model_id in harness.recorder.of("start")]


# ---------------------------------------------------------------- one decode definition


def test_the_metric_formulas_are_the_documented_ones():
    observation = FakeObservation(ttft_s=0.5, last_content_s=2.5, prompt_tokens=64, completion_tokens=100)

    assert measure.decode_tps(observation) == pytest.approx(100 / 2.0)
    assert measure.prefill_tps(observation) == pytest.approx(64 / 0.5)
    assert measure.itl_s(observation) == pytest.approx(2.0 / 99)


def test_decode_never_falls_back_to_total_s():
    """The removed fork. total_s covers the usage chunk, [DONE] and teardown."""
    no_content_window = FakeObservation(ttft_s=None, last_content_s=None, total_s=9.9, completion_tokens=100)
    assert measure.decode_tps(no_content_window) is None

    slow_teardown = FakeObservation(ttft_s=0.5, last_content_s=2.5, total_s=99.0, completion_tokens=100)
    assert measure.decode_tps(slow_teardown) == pytest.approx(50.0)
    assert measure.decode_tps(slow_teardown) != pytest.approx(100 / 98.5)


def test_a_single_content_delta_has_no_decode_window():
    buffered = FakeObservation(ttft_s=2.5, last_content_s=2.5, total_s=2.6, content_event_count=1)
    assert measure.decode_tps(buffered) is None


def test_itl_never_divides_by_zero_on_a_single_token():
    one_token = FakeObservation(ttft_s=0.5, last_content_s=0.6, completion_tokens=1)
    assert measure.itl_s(one_token) == pytest.approx(0.1)


def test_prefill_needs_usage_prompt_tokens():
    assert measure.prefill_tps(FakeObservation(prompt_tokens=None)) is None
    assert measure.prefill_tps(FakeObservation(prompt_tokens=0)) is None


# ------------------------------------------------------------------------- loop shape


def test_cells_are_visited_in_alternating_order(harness):
    """Config order measures the first runtime cool and the last one throttled."""
    for name in ("mlxlm", "osaurus", "omlx"):
        harness.add_runtime(name)
    cells = [harness.cell(f"oq__{name}", name) for name in ("mlxlm", "osaurus", "omlx")]

    harness.run(cells)

    assert starts(harness) == ["mlxlm", "osaurus", "omlx", "omlx", "osaurus", "mlxlm"]


def test_visit_plan_reverses_direction_each_round():
    cells = [measure.Cell(id=f"c{index}", runtime="mlxlm", artifact_dir=f"/m/{index}", label="f")
             for index in range(3)]

    forwards, backwards = measure.visit_plan(cells)

    assert [cell.id for cell in forwards] == ["c0", "c1", "c2"]
    assert [cell.id for cell in backwards] == ["c2", "c1", "c0"]


def test_a_cooldown_sits_between_visits_and_not_after_the_last_one(harness):
    harness.add_runtime("mlxlm")
    harness.add_runtime("osaurus")

    harness.run([harness.cell("oq__mlxlm", "mlxlm"), harness.cell("oq__osaurus", "osaurus")],
                cooldown_s=12.5)

    assert harness.sleeps() == [12.5] * 3


def test_the_measured_requests_are_split_across_the_visits(harness):
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    assert len(results[0].observations) == MEASURED
    per_visit = [len(calls) - WARMUPS for calls in harness.transport.calls_by_visit().values()]
    assert per_visit == [3, 2]


def test_warmup_is_enforced_at_three(harness):
    harness.add_runtime("mlxlm")
    cells = [harness.cell("oq__mlxlm", "mlxlm")]

    with pytest.raises(ValueError, match="warmup"):
        harness.run(cells, warmup=2)


def test_measured_must_be_positive(harness):
    harness.add_runtime("mlxlm")
    with pytest.raises(ValueError, match="measured"):
        harness.run([harness.cell("oq__mlxlm", "mlxlm")], measured=0)


def test_a_run_too_short_to_split_still_measures_something(harness):
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")], measured=1)

    assert len(results[0].observations) == 1
    assert starts(harness) == ["mlxlm"]
    assert harness.sleeps() == []


def test_a_workload_without_messages_is_refused(harness):
    harness.add_runtime("mlxlm")
    with pytest.raises(ValueError, match="messages"):
        harness.run([harness.cell("oq__mlxlm", "mlxlm")], workload={"id": "empty"})


def test_a_missing_module_is_named_rather_than_measured(harness, monkeypatch):
    harness.add_runtime("mlxlm")
    monkeypatch.setattr(measure, "transport", None)

    with pytest.raises(measure.MeasureError, match="transport.py"):
        harness.run([harness.cell("oq__mlxlm", "mlxlm")])


# ------------------------------------------------------------------------- every request


def test_every_request_pins_temperature_zero_and_the_fixed_seed(harness):
    harness.add_runtime("mlxlm")

    harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    assert harness.transport.calls
    assert {call.temperature for call in harness.transport.calls} == {0.0}
    assert {call.seed for call in harness.transport.calls} == {0}
    assert measure.TEMPERATURE == 0.0


def test_every_request_carries_the_fixed_max_tokens(harness):
    harness.add_runtime("mlxlm")

    harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    assert {call.max_tokens for call in harness.transport.calls} == {256}


def test_the_token_counter_is_wired_into_every_request(harness):
    """The predecessor's exact token path existed and no production caller ever passed it."""
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    counters = {id(call.token_counter) for call in harness.transport.calls}
    assert None not in {call.token_counter for call in harness.transport.calls}
    assert len(counters) == 1
    assert harness.recorder.of("counter") == [(results[0].cell.artifact_dir,)]


def test_warmups_run_before_the_measurements_and_never_reach_the_samples(harness):
    harness.transport.responder = lambda call: FakeObservation(
        text="warmup" if call.visit_index < WARMUPS else "measured"
    )
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    assert [response.text for response in harness.transport.responses[:WARMUPS]] == ["warmup"] * WARMUPS
    assert [observation.text for observation in results[0].observations] == ["measured"] * MEASURED
    assert len(harness.transport.calls) == MEASURED + 2 * WARMUPS


def test_every_measured_observation_is_retained_untruncated(harness):
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    for observation in results[0].observations:
        assert observation.text == "measured"
        assert observation.prompt_tokens == 64
        assert observation.completion_tokens == 100
        assert observation.token_source == "usage"


def test_every_failed_request_is_still_retained_as_an_observation(harness):
    harness.transport.responder = lambda call: FakeObservation(ok=False, error="TimeoutError: read timed out")
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    assert len(results[0].observations) == MEASURED
    assert results[0].status == "FAIL"
    assert results[0].runtime_version == "0.31.3"


# ----------------------------------------------------------------------------- handle


def test_cold_load_comes_from_the_handle_and_never_into_a_request(harness):
    harness.add_runtime("mlxlm", cold_load_s=23.25)

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    assert results[0].cold_load_s == pytest.approx(23.25)
    # The runtime's own name for the weights, not the artifact path, is what is requested.
    assert {call.model for call in harness.transport.calls} == {"mlxlm/oq__mlxlm"}
    assert results[0].observations[0].ttft_s == pytest.approx(0.5)
    assert results[0].observations[0].total_s == pytest.approx(2.6)


def test_the_runtime_version_is_recorded(harness):
    harness.add_runtime("osaurus", version="0.25.3")

    results = harness.run([harness.cell("oq__osaurus", "osaurus")])

    assert results[0].runtime_version == "0.25.3"


def test_the_handle_is_stopped_after_every_visit_even_when_requests_fail(harness):
    def explode(call):
        raise RuntimeError("server died")

    harness.transport.responder = explode
    runtime = harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    assert results[0].status == "FAIL"
    assert [handle.stops for handle in runtime.handles] == [1, 1]
    assert harness.recorder.kinds().count("stop") == 2


def test_memory_is_the_visits_higher_peak(harness):
    harness.sample.peaks = [100.0, 250.0]
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    assert results[0].memory["peak_mb"] == 250.0
    assert len(harness.sample.samplers) == 2


# ----------------------------------------------------------------------------- statuses


def test_a_fully_measurable_cell_passes(harness):
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    assert results[0].status == "PASS"
    assert results[0].reason is None


def test_one_failed_request_fails_the_cell(harness):
    harness.transport.responder = lambda call: (
        FakeObservation() if call.index == 2 else FakeObservation(ok=False, error="HTTPError: 500")
    )
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    assert results[0].status == "FAIL"
    assert "HTTPError: 500" in results[0].reason


def test_a_response_without_content_timing_fails_the_cell(harness):
    harness.transport.responder = lambda call: FakeObservation(ttft_s=2.5, last_content_s=2.5)
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    assert results[0].status == "FAIL"
    assert "empty decode window" in results[0].reason


def test_a_response_without_usage_prompt_tokens_fails_the_cell(harness):
    harness.transport.responder = lambda call: FakeObservation(prompt_tokens=None)
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    assert results[0].status == "FAIL"
    assert "prefill throughput is undefined" in results[0].reason


def test_an_unknown_runtime_is_na_and_the_run_continues(harness):
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm"), harness.cell("jang__jang", "jang")])

    assert [result.status for result in results] == ["PASS", "N/A"]
    assert "unknown runtime 'jang'" in results[1].reason
    assert starts(harness) == ["mlxlm"] * 2
    assert results[1].observations == []


def test_a_runtime_that_will_not_start_is_na_and_does_not_end_the_run(harness):
    harness.add_runtime("mlxlm")
    broken = harness.add_runtime("omlx", start_error=RuntimeError("model type not supported"))

    results = harness.run([harness.cell("jang__omlx", "omlx"), harness.cell("j4__mlxlm", "mlxlm")])

    assert [result.status for result in results] == ["N/A", "PASS"]
    assert "did not start" in results[0].reason
    assert "model type not supported" in results[0].reason
    assert results[0].cold_load_s is None
    assert results[0].runtime_version is None
    assert broken.attempts == 2


def test_a_second_visit_that_will_not_start_fails_rather_than_passes(harness):
    """The samples that were taken stand, and the visit that did not happen is not hidden."""
    harness.add_runtime("mlxlm", start_error=RuntimeError("port still held by a stale server"),
                        fail_from_attempt=2)

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    assert results[0].status == "FAIL"
    assert "did not start" in results[0].reason
    assert "port still held" in results[0].reason
    assert len(results[0].observations) == 3
    assert results[0].cold_load_s == pytest.approx(7.5)


def test_an_unavailable_tokenizer_is_na_rather_than_a_silent_fallback(harness):
    def refuse(model_dir):
        raise FileNotFoundError(f"no tokenizer.json in {model_dir}")

    harness.token_counter.TokenCounter = refuse
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    assert results[0].status == "N/A"
    assert "token counter unavailable" in results[0].reason
    assert harness.transport.calls == []


def test_a_cell_that_cannot_be_measured_costs_no_cooldown(harness):
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("jang__jang", "jang"), harness.cell("oq__mlxlm", "mlxlm")],
                          cooldown_s=5.0)

    # The unknown runtime came first in the plan and started nothing, so nothing cooled
    # down for it: no tokenizer, no request, no cooldown. Only the runtime that can be
    # measured pays cooldowns, two of them for its two visits (three samples then two).
    assert [result.status for result in results] == ["N/A", "PASS"]
    assert len(harness.recorder.of("counter")) == 1
    kinds = harness.recorder.kinds()
    assert kinds.index("sleep") > kinds.index("chat")
    assert harness.sleeps() == [5.0, 5.0]


# ------------------------------------------------------------------------- persistence


def test_results_are_persisted_after_every_visit(harness):
    results_dir = harness.tmp_path / "results"
    seen: list[int | None] = []

    def responder(call):
        path = Path(results_dir) / measure.RESULTS_FILENAME
        seen.append(None if not path.exists() else len(path.read_text().splitlines()))
        return FakeObservation()

    harness.transport.responder = responder
    harness.add_runtime("mlxlm")
    harness.add_runtime("osaurus")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm"), harness.cell("oq__osaurus", "osaurus")],
                          results_dir=results_dir)

    # First visit: nothing written yet. Second visit: the header and the first cell are
    # on disk — the header is a line too, so one cell is two lines and two cells three.
    assert seen[0] is None
    assert seen[WARMUPS + 3] == 2
    assert sorted(seen[-1:]) == [3]
    assert len(harness.lines(results_dir)) == len(results)


def test_the_persisted_record_carries_raw_observations_and_the_pins(harness):
    harness.add_runtime("mlxlm")
    cells = [harness.cell("oq__mlxlm", "mlxlm")]
    workload = {"id": "short-chat", "messages": [{"role": "user", "content": "hello"}]}

    harness.run(cells, workload=workload)

    header = harness.header()
    assert header["temperature"] == 0.0
    assert header["seed"] == 0
    assert header["max_tokens"] == 256
    assert header["warmup"] == WARMUPS
    assert header["measured"] == MEASURED
    assert header["workload"] == workload

    record, = harness.lines()
    assert record["cell"] == {"id": "oq__mlxlm", "runtime": "mlxlm",
                              "artifact_dir": cells[0].artifact_dir, "label": "affine-4bit"}
    assert record["status"] == "PASS"
    assert record["cold_load_s"] == pytest.approx(7.5)
    assert record["runtime_version"] == "0.31.3"

    assert len(record["observations"]) == MEASURED
    assert len(record["warmup_observations"]) == 2 * WARMUPS
    assert record["measured_count"] == MEASURED
    observation = record["observations"][0]
    assert set(observation) >= {
        "ok", "error", "ttft_s", "last_content_s", "total_s", "prompt_tokens",
        "completion_tokens", "reasoning_tokens", "content_event_count", "text",
        "token_source",
    }
    # Derived metrics are computed on read, so a stored copy can never disagree with the
    # raw fields it comes from.
    assert not set(observation) & {"decode_tps", "prefill_tps", "itl_s"}


def test_drift_across_the_window_is_recorded(harness):
    """Late samples slower than early ones is the thermal curve, and it is a number."""
    def responder(call):
        return FakeObservation(ttft_s=0.5, last_content_s=2.5 + 0.1 * call.index)

    harness.transport.responder = responder
    harness.add_runtime("mlxlm")

    harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    record, = harness.lines()
    assert record["drift"]["n"] == MEASURED
    assert record["drift"]["late_median_tps"] < record["drift"]["early_median_tps"]
    assert record["drift"]["change_pct"] < 0


def test_drift_needs_two_rates():
    assert measure.measured_drift([]) is None
    assert measure.measured_drift([FakeObservation()]) is None


def test_a_second_run_overwrites_rather_than_appends(harness):
    harness.add_runtime("mlxlm")
    cells = [harness.cell("oq__mlxlm", "mlxlm")]

    harness.run(cells)
    harness.run(cells)

    assert len(harness.lines()) == 1


# ------------------------------------------------------------------------- results.jsonl


def cell_result(observations=(), *, cell_id="oq__mlxlm", runtime="mlxlm",
                runtime_version="mlx-lm 0.31.3", disk_bytes=123):
    """A CellResult to hand straight to write_jsonl, with no run behind it."""
    return measure.CellResult(
        cell=measure.Cell(id=cell_id, runtime=runtime, artifact_dir="/models/oq4", label="oq4"),
        status="PASS",
        reason=None,
        observations=list(observations),
        warmup_observations=[],
        cold_load_s=12.5,
        memory={"peak_mb": 9150.0},
        runtime_version=runtime_version,
        disk_bytes=disk_bytes,
    )


def test_write_jsonl_writes_a_header_and_one_object_per_cell(tmp_path):
    observations = [
        FakeObservation(),
        FakeObservation(total_s=2.75),
        FakeObservation(ok=False, ttft_s=None, last_content_s=None, error="boom"),
    ]
    results = [
        cell_result(observations, disk_bytes=123),
        cell_result([FakeObservation()], cell_id="oq__omlx", runtime="omlx",
                    runtime_version="oMLX 0.3"),
    ]
    run = {
        "temperature": 0.0,
        "seed": 0,
        "max_tokens": 256,
        "warmup": WARMUPS,
        "measured": MEASURED,
        "cooldown_s": 30.0,
        "workload": {"id": "short-chat", "messages": [{"role": "user", "content": "hi"}]},
    }
    path = tmp_path / "run" / "results.jsonl"

    measure.write_jsonl(results, str(path), run=run)

    header, *lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert header == run
    assert len(lines) == 2
    assert lines[0]["cell"] == {
        "id": "oq__mlxlm",
        "runtime": "mlxlm",
        "artifact_dir": "/models/oq4",
        "label": "oq4",
    }
    assert lines[0]["runtime_version"] == "mlx-lm 0.31.3"
    assert lines[1]["runtime_version"] == "oMLX 0.3"
    assert lines[0]["disk_bytes"] == 123
    assert lines[0]["cold_load_s"] == pytest.approx(12.5)
    assert lines[0]["memory"] == {"peak_mb": 9150.0}

    assert len(lines[0]["observations"]) == 3
    raw = lines[0]["observations"][0]
    assert set(raw) == {field.name for field in fields(FakeObservation)}
    assert raw["total_s"] == pytest.approx(2.6)
    assert raw["completion_tokens"] == 100
    assert raw["token_source"] == "usage"
    assert raw["text"] == observations[0].text
    assert lines[0]["observations"][2]["ok"] is False
    assert lines[0]["observations"][2]["error"] == "boom"


def test_summaries_stay_recomputable_from_the_jsonl(tmp_path):
    results = [cell_result([FakeObservation(ttft_s=t) for t in (0.4, 0.5, 0.6, 0.7, 0.8)])]
    path = tmp_path / "results.jsonl"

    measure.write_jsonl(results, str(path), run={"temperature": 0.0})

    # Line 1 of the file is the run header; every line after it is a cell.
    records = [json.loads(line) for line in path.read_text().splitlines()[1:]]
    rebuilt = [
        measure.CellResult(
            cell=measure.Cell(**record["cell"]),
            status=record["status"],
            reason=record["reason"],
            observations=[FakeObservation(**raw) for raw in record["observations"]],
            warmup_observations=[FakeObservation(**raw) for raw in record["warmup_observations"]],
            cold_load_s=record["cold_load_s"],
            memory=record["memory"],
            runtime_version=record["runtime_version"],
            disk_bytes=record["disk_bytes"],
        )
        for record in records
    ]

    assert report.summarize(rebuilt) == report.summarize(results)


# ------------------------------------------------------------------------- disk bytes


def test_disk_bytes_counts_sidecar_files_and_each_inode_once(harness, tmp_path):
    artifact = tmp_path / "artifact"
    (artifact / "nested").mkdir(parents=True)
    (artifact / "model.safetensors").write_text("x" * 10)
    (artifact / "nested" / "sidecar.json").write_text("y" * 5)
    (artifact / "duplicate.safetensors").symlink_to(artifact / "model.safetensors")

    assert measure.artifact_bytes(str(artifact)) == 15


def test_disk_bytes_of_a_missing_artifact_is_none():
    assert measure.artifact_bytes("/nonexistent/artifact") is None


def test_the_cell_result_carries_the_artifact_size(harness):
    harness.add_runtime("mlxlm")
    cell = harness.cell("oq__mlxlm", "mlxlm")
    Path(cell.artifact_dir).mkdir(parents=True)
    (Path(cell.artifact_dir) / "weights.safetensors").write_text("z" * 32)

    results = harness.run([cell])

    assert results[0].disk_bytes == 32


# ------------------------------------------------------------------------- results dir


def test_the_results_directory_is_created(harness, tmp_path):
    harness.add_runtime("mlxlm")
    results_dir = tmp_path / "deep" / "run-2026-09-15"

    harness.run([harness.cell("oq__mlxlm", "mlxlm")], results_dir=results_dir)

    assert (results_dir / measure.RESULTS_FILENAME).exists()


# ---------------------------------------------------------------------- the coherence gate

# The gate keeps a cell that emitted garbage out of the results, however fast it was. These
# are shapes, not a scoring rubric: tests/test_coherence.py owns the captured salad verbatim
# and the four checks themselves.
SALAD = "，,跟ashaa.atore quell\ufffd不会ulatSR2ancel Hard1"
COHERENT = "Change one thing at a time, or the number cannot say which change moved it."


def measured_text(bad, *, warmup_text="warmup", bad_text=SALAD, good_text=COHERENT):
    """A responder whose first *bad* measured responses are *bad_text*, the rest coherent.

    Every response keeps the timing and token accounting of a healthy request: the gate
    judges text, and a cell is not let off because its garbage decoded quickly.
    """
    seen = 0

    def responder(call):
        nonlocal seen
        if call.visit_index < WARMUPS:
            return FakeObservation(text=warmup_text)
        seen += 1
        return FakeObservation(text=bad_text if seen <= bad else good_text)

    return responder


def test_an_incoherent_cell_fails_and_keeps_the_sample_that_failed(harness):
    """The failure the gate exists for: HTTP 200, full speed, 64/64 tokens of token salad."""
    harness.transport.responder = measured_text(MEASURED)
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    assert results[0].status == "FAIL"
    assert results[0].reason == "incoherent output: replacement characters"

    record, = harness.lines()
    assert record["status"] == "FAIL"
    assert record["reason"] == "incoherent output: replacement characters"
    # The offending sample is on the record in full, and the record holds raw fields only:
    # nothing derived sits beside it for a reader to mistake for an accepted figure.
    assert record["observations"][0]["text"] == SALAD
    assert not set(record["observations"][0]) & {"decode_tps", "prefill_tps", "itl_s"}

    # The leaderboard row carries the verdict, not a good number in a fast-looking row.
    row = report.summarize(results)[0]
    assert row["status"] == "FAIL"
    assert row["reason"] == results[0].reason


def test_the_gate_makes_no_transport_call_of_its_own(harness):
    """The measured responses are the sample, so the gate asks no question of its own."""
    harness.transport.responder = measured_text(MEASURED)
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    assert results[0].status == "FAIL"
    assert len(harness.transport.calls) == MEASURED + 2 * WARMUPS
    per_visit = [len(calls) - WARMUPS for calls in harness.transport.calls_by_visit().values()]
    assert per_visit == [3, 2]


def test_the_gate_judges_the_measured_responses_and_not_the_warmups(harness):
    harness.transport.responder = measured_text(0, warmup_text=SALAD)
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    assert [response.text for response in harness.transport.responses[:WARMUPS]] == [SALAD] * WARMUPS
    assert results[0].status == "PASS"
    assert results[0].reason is None


def test_more_than_half_the_judged_responses_have_to_be_incoherent(harness):
    harness.add_runtime("mlxlm")

    harness.transport.responder = measured_text(2)
    two_of_five = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    harness.transport.responder = measured_text(3)
    three_of_five = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    assert [observation.text for observation in two_of_five[0].observations] == (
        [SALAD, SALAD, COHERENT, COHERENT, COHERENT]
    )
    assert two_of_five[0].status == "PASS"
    assert three_of_five[0].status == "FAIL"
    assert three_of_five[0].reason == "incoherent output: replacement characters"


def test_a_response_that_did_not_come_back_is_never_called_incoherent(harness):
    """An empty or failed response is a transport failure, already reported as one."""
    harness.transport.responder = lambda call: FakeObservation(
        ok=False, error="TimeoutError: read timed out", ttft_s=None, last_content_s=None, text=""
    )
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    assert results[0].status == "FAIL"
    assert "TimeoutError: read timed out" in results[0].reason
    assert "incoherent" not in results[0].reason
    # Nothing came back with text, so there was nothing to judge and no majority to take.
    assert measure._incoherent(results[0].observations) is None


def reasoning_only(text, *, ok=False, error=measure.EMPTY_CONTENT_ERROR):
    """One response that emitted no content at all: everything it wrote is in the reasoning
    channel, which is the shape the transport reports as its empty-content failure."""
    return FakeObservation(
        ok=ok,
        error=error,
        ttft_s=None,
        last_content_s=None,
        completion_tokens=None,
        content_event_count=0,
        text="",
        reasoning_text=text,
        token_source="none",
    )


def measured_responses(*shapes):
    """A responder handing each measured request one shape, in order, the last one repeating.

    Warmups are never judged, so they are not part of the sequence.
    """
    measured = list(shapes)
    seen = 0

    def responder(call):
        nonlocal seen
        if call.visit_index < WARMUPS:
            return FakeObservation()
        shape = measured[min(seen, len(measured) - 1)]
        seen += 1
        return shape

    return responder


def test_a_cell_that_is_still_thinking_gets_its_own_reason(harness):
    """Neither channel produced anything, so there is no output here to call incoherent."""
    harness.transport.responder = lambda call: FakeObservation(
        ok=False, error=measure.EMPTY_CONTENT_ERROR, ttft_s=None, last_content_s=None,
        text="", reasoning_text="",
    )
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    assert results[0].status == "FAIL"
    assert results[0].reason == measure.STILL_THINKING
    assert "incoherent" not in results[0].reason
    assert len(results[0].observations) == MEASURED
    # Empty in both channels is what earns this verdict, and nothing else —
    # "no output is not bad output" stops where the model starts writing.
    assert all(
        observation.text == "" and observation.reasoning_text == ""
        for observation in results[0].observations
    )
    assert measure._incoherent(results[0].observations) is None


def test_a_reasoning_only_salad_cell_fails_as_incoherent(harness):
    """The captured failure: zero content deltas, the whole budget in the reasoning channel,
    and that channel full of token salad. Garbage is garbage in either channel, so this cell
    fails on the garbage rather than reading as a token-budget problem."""
    harness.transport.responder = measured_responses(*[reasoning_only(SALAD)] * MEASURED)
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    assert results[0].status == "FAIL"
    assert results[0].reason == "incoherent output: replacement characters"
    assert results[0].reason != measure.STILL_THINKING
    # The content-less stream is not the failure being reported here.
    assert "measured requests failed" not in results[0].reason

    record, = harness.lines()
    assert record["status"] == "FAIL"
    assert record["reason"] == "incoherent output: replacement characters"
    # The offending sample is on the record in full, in the channel it was spelled in.
    assert record["observations"][0]["text"] == ""
    assert record["observations"][0]["reasoning_text"] == SALAD

    row = report.summarize(results)[0]
    assert row["status"] == "FAIL"
    assert row["reason"] == results[0].reason


def test_a_reasoning_only_response_is_judged_even_when_the_stream_is_not_a_failure(harness):
    """A stream that reported the same reasoning-only answer as a success must not slip past
    the gate either: the channel is what makes it judgeable, not the transport's error."""
    harness.transport.responder = measured_responses(
        *[reasoning_only(SALAD, ok=True, error=None)] * MEASURED
    )
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    assert results[0].status == "FAIL"
    assert results[0].reason == "incoherent output: replacement characters"


def test_reasoning_that_is_language_is_no_longer_still_thinking(harness):
    """A response that answered in the reasoning channel is not an empty one, so it gets no
    still-thinking verdict — and it still carries no content window for the metrics."""
    harness.transport.responder = measured_responses(*[reasoning_only(COHERENT)] * MEASURED)
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    assert results[0].status == "FAIL"
    assert results[0].reason == "no content-delta timing, so decode tok/s is undefined"
    assert measure.STILL_THINKING not in results[0].reason


def test_incoherent_reasoning_counts_in_the_same_majority_as_content(harness):
    """The denominator stays the responses that were judged, not the requests that were
    made: a reasoning-only salad is one judged response among five, content or not."""
    harness.add_runtime("mlxlm")
    content = [FakeObservation(text=COHERENT)] * 3

    harness.transport.responder = measured_responses(
        reasoning_only(SALAD), reasoning_only(SALAD), *content
    )
    two_of_five = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    harness.transport.responder = measured_responses(
        reasoning_only(SALAD), reasoning_only(SALAD), reasoning_only(SALAD),
        FakeObservation(text=COHERENT), FakeObservation(text=COHERENT),
    )
    three_of_five = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    assert measure._incoherent(two_of_five[0].observations) is None
    assert measure._incoherent(three_of_five[0].observations) == (
        "incoherent output: replacement characters"
    )
    assert three_of_five[0].status == "FAIL"
    assert three_of_five[0].reason == "incoherent output: replacement characters"


def test_a_response_with_content_is_judged_on_its_content(harness):
    """Content is the channel the published metrics describe, so a coherent answer is judged
    on the answer — the reasoning trace behind it is not the answer."""
    harness.transport.responder = lambda call: FakeObservation(
        text=COHERENT, reasoning_text=SALAD
    )
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    assert results[0].status == "PASS"
    assert results[0].reason is None


def test_the_gate_pins_no_expected_answer(harness, monkeypatch):
    """A pinned substring cannot work against an arbitrary workload, so none is passed."""
    expectations = []
    is_coherent = measure.coherence.is_coherent

    def spy(text, *, expect=None):
        expectations.append(expect)
        return is_coherent(text, expect=expect)

    monkeypatch.setattr(measure.coherence, "is_coherent", spy)
    harness.transport.responder = measured_text(0)
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    assert results[0].status == "PASS"
    assert expectations, "the gate never ran"
    assert set(expectations) == {None}
    assert "4" not in COHERENT
