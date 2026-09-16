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

import itertools
import json
import time
from dataclasses import dataclass, fields, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from ohyesmlx import measure, report

WARMUPS = 3
MEASURED = 5


def workload(workload_id="chat", *, content="hi", max_tokens=256) -> measure.Workload:
    """One ``measure.Workload``, the pinned shape, for a test that needs a specific one."""
    return measure.Workload(
        id=workload_id,
        messages=[{"role": "user", "content": content}],
        max_tokens=max_tokens,
    )


# The default workload the harness measures under. One shape keeps a test that is about the
# loop's shape -- visits, quotas, cooldowns, persistence -- reading as the loop's shape, and
# the three-shape tests below pin the grouping on top of it.
DEFAULT_WORKLOAD = workload("short-chat", content="hi")
THREE = [
    workload("chat", content="hi", max_tokens=128),
    workload("prefill", content="long " * 400, max_tokens=64),
    workload("decode", content="hi", max_tokens=512),
]


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
        self.memory_pid = self.pid
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}/v1"
        self.model_id = model_id
        self.version = version
        self.cold_load_s = cold_load_s
        # The seventh pinned field, filled in by the loop when the cold visit's first
        # warmup comes back -- which is a request the loop makes, not the runtime.
        self.first_request_s = None
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

    def run(self, cells, *, workloads=None, results_dir=None, warmup=WARMUPS,
            measured=MEASURED, **kwargs):
        """One run under a fixed budget of three warmups and five samples.

        The loop's real defaults are the plateau rule and nine samples, and a run that does
        not name them gets them; the tests about visits, quotas, persistence and the gate are
        about neither, so they pin the budget they were written against. The tests that are
        about the rule and the nine say so by passing them.
        """
        return measure.run_cells(
            cells,
            [DEFAULT_WORKLOAD] if workloads is None else workloads,
            warmup=warmup,
            measured=measured,
            results_dir=str(results_dir if results_dir is not None else self.tmp_path / "results"),
            **kwargs,
        )

    def results_file(self, results_dir=None) -> Path:
        root = results_dir if results_dir is not None else self.tmp_path / "results"
        return Path(root) / measure.RESULTS_FILENAME

    def header(self, results_dir=None) -> dict:
        """Line 1: the pins and every workload the run's cells were measured under."""
        return json.loads(self.results_file(results_dir).read_text().splitlines()[0])

    def lines(self, results_dir=None) -> list[dict]:
        """The cell records on disk, the run header line excluded."""
        return [
            json.loads(line)
            for line in self.results_file(results_dir).read_text().splitlines()[1:]
        ]

    def calls_by_workload(self):
        """The requests, grouped by the cap of the workload that made them.

        The cap is what tells the three shapes' requests apart: `chat` and `decode` send the
        same prompt on purpose, and each workload pins its own distinct max_tokens.
        """
        grouped: dict[int, list] = {}
        for call in self.transport.calls:
            grouped.setdefault(call.max_tokens, []).append(call)
        return grouped

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
    empty = measure.Workload(id="empty", messages=[], max_tokens=64)

    with pytest.raises(ValueError, match="messages"):
        harness.run([harness.cell("oq__mlxlm", "mlxlm")], workloads=[empty])


def test_a_run_with_no_workloads_is_refused(harness):
    """No workload is no measurement, and starting a runtime to run none of them is a load
    spent on nothing."""
    harness.add_runtime("mlxlm")
    with pytest.raises(ValueError, match="workloads"):
        harness.run([harness.cell("oq__mlxlm", "mlxlm")], workloads=[])


def test_two_workloads_cannot_share_an_id(harness):
    """A result is keyed by (cell, workload): a repeated id would pool two shapes' samples
    into one row instead of producing two."""
    harness.add_runtime("mlxlm")

    with pytest.raises(ValueError, match="duplicate workload id"):
        harness.run(
            [harness.cell("oq__mlxlm", "mlxlm")],
            workloads=[workload("chat", max_tokens=128), workload("chat", max_tokens=512)],
        )


def test_a_missing_module_is_named_rather_than_measured(harness, monkeypatch):
    harness.add_runtime("mlxlm")
    monkeypatch.setattr(measure, "transport", None)

    with pytest.raises(measure.MeasureError, match="transport.py"):
        harness.run([harness.cell("oq__mlxlm", "mlxlm")])


# ---------------------------------------------------------------------- the warmup window

# The rule, from docs/interfaces.md: a window opens with the floor of three, the last three
# rates have to stop moving within 3% of their median, and the cap of sixteen ends it either
# way. The rates below are built by solving `decode_tps` for timestamps, so a test's warmup
# population is exactly the one a real stream would have produced.


def rate_observation(rate: float, **overrides) -> FakeObservation:
    """One response whose decode rate is *rate* tok/s: the published formula, inverted."""
    return FakeObservation(
        ttft_s=0.5, last_content_s=0.5 + 100.0 / rate, completion_tokens=100, **overrides
    )


def rate_responder(rates):
    """A responder handing the k-th request of a visit the k-th rate, the last one repeating.

    The loop decides how long a window runs, so the sequence has to carry the answer: rates
    that stop moving have settled, rates that keep climbing have not.
    """
    def responder(call):
        return rate_observation(rates[min(call.visit_index, len(rates) - 1)])

    return responder


def test_a_stream_that_plateaus_immediately_stops_at_the_floor(harness):
    """A cell warm from its first request does not pay for a budget it does not need -- but
    the floor is two windows, not one, because one window cannot tell a warm rate from a boost
    rate holding steady."""
    harness.transport.responder = rate_responder([8.0, 8.0, 8.0])
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")], warmup="plateau", measured=1)

    assert len(results[0].warmup_observations) == 2 * measure.WARMUP_WINDOW == 10
    assert results[0].warmup_plateau is True


def test_a_window_that_keeps_climbing_runs_to_the_cap_and_says_so(harness):
    """The cap is not a fallback that quietly substitutes for the rule. A window that ran to
    it was still climbing, and a row that renders like a settled one is the defect the field
    exists to prevent."""
    harness.transport.responder = rate_responder([float(k) for k in range(1, 64)])
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")], warmup="plateau", measured=1)

    assert len(results[0].warmup_observations) == measure.WARMUP_CAP == 20
    assert results[0].warmup_plateau is False
    record, = harness.lines()
    assert record["warmup_count"] == 20
    assert record["warmup_plateau"] is False
    assert measure._record(results[0]) == record


def test_a_climbing_window_settles_where_the_climb_stops(harness):
    """The budget a cell needed becomes a published number: six would have been too few here,
    sixteen would have been seven too many. The window closes at the request where the last
    three rates agree AND agree with the three before them -- one request after the climb
    flattens, never on the first flat window."""
    harness.transport.responder = rate_responder([1.0, 2.0, 3.0, 5.0, 7.0, 7.0, 7.0])
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")], warmup="plateau", measured=1)

    assert len(results[0].warmup_observations) == 12
    assert results[0].warmup_plateau is True
    assert harness.lines()[0]["warmup_count"] == 12


def test_a_warmup_with_no_decode_rate_cannot_settle_the_window(harness):
    """Rates come from ``decode_tps``, the same function every published figure uses. A window
    can hold three rates that agree and still not have settled: they have to be the last
    three, and a request that came back with no decode window is not one of them."""
    def responder(call):
        # Only the warmup window: a rate-less request among the MEASURED ones is a FAILed cell,
        # which is a different test. This one is about what can close a warmup window.
        if call.visit_index < measure.WARMUP_CAP and call.visit_index % 3 == 2:
            return FakeObservation(ttft_s=None, last_content_s=None, completion_tokens=None)
        return rate_observation(5.0)

    harness.transport.responder = responder
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")], warmup="plateau", measured=1)
    warmups = results[0].warmup_observations

    assert sum(measure.decode_tps(observation) is not None for observation in warmups) >= 3
    assert len(warmups) == measure.WARMUP_CAP
    assert results[0].warmup_plateau is False
    assert results[0].status == "PASS", "the measured requests were healthy throughout"


def test_a_row_settles_only_when_every_visit_s_window_settled(harness):
    """Both visits' windows are this row's windows: a cell still climbing in its second one
    has not settled, and the first visit's settle does not cover for it."""
    def responder(call):
        if call.visit == 1:
            return rate_observation(5.0)
        return rate_observation(5.0 + call.visit_index)

    harness.transport.responder = responder
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")], warmup="plateau", measured=2)

    assert len(results[0].warmup_observations) == 2 * measure.WARMUP_WINDOW + measure.WARMUP_CAP
    assert results[0].warmup_plateau is False


def test_a_fixed_budget_is_still_exactly_that_many_requests(harness):
    """An int is a caller pinning a count, and it still refuses below the floor. The rule
    never runs, so there is no plateau for the row to report and the header stays the number
    that was asked for."""
    harness.transport.responder = rate_responder([9.0, 8.0, 7.0, 6.0])
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")], warmup=3, measured=1)

    assert len(results[0].warmup_observations) == 3
    assert harness.header()["warmup"] == 3
    assert results[0].warmup_plateau is None
    assert measure._record(results[0]) == harness.lines()[0]


def test_a_row_no_visit_reached_has_no_plateau_verdict(harness):
    """No warmup ran, so no window settled and none hit the cap — which is a different thing
    from a window that settled, and is written as its own value rather than left out."""
    harness.add_runtime("omlx", start_error=RuntimeError("model type not supported"))

    results = harness.run([harness.cell("oq__omlx", "omlx")], warmup="plateau")

    assert results[0].warmup_plateau is None
    assert harness.lines()[0]["warmup_plateau"] is None


def test_a_run_that_names_no_warmup_gets_the_rule_and_nine_samples(harness):
    """What the grid runs and what the header pins: the rule rather than a count, and nine
    samples so the drift compares medians of four."""
    harness.add_runtime("mlxlm")

    results = measure.run_cells(
        [harness.cell("oq__mlxlm", "mlxlm")],
        [DEFAULT_WORKLOAD],
        results_dir=str(harness.tmp_path / "results"),
    )

    assert harness.header()["warmup"] == {
        "mode": "plateau",
        "window": measure.WARMUP_WINDOW,
        "floor": 2 * measure.WARMUP_WINDOW,
        "cap": measure.WARMUP_CAP,
        "plateau_pct": measure.WARMUP_PLATEAU_PCT,
    }
    assert harness.header()["measured"] == 9
    assert len(results[0].observations) == 9
    assert [len(calls) - 2 * measure.WARMUP_WINDOW
            for calls in harness.transport.calls_by_visit().values()] == [5, 4]
    assert harness.lines()[0]["drift"]["n"] == 9
    assert results[0].warmup_plateau is True


def test_the_plateau_pins_round_trip_through_load_run(harness):
    """Join guard 1 compares the warmup pin across columns, so the header a reader gets back
    has to be the one the run wrote, dict and all — and the record's verdict comes back with
    it rather than being re-derived on read."""
    harness.add_runtime("mlxlm")
    harness.run([harness.cell("oq__mlxlm", "mlxlm")], warmup="plateau", measured=1)

    header, results = measure.load_run(harness.results_file())

    assert header["warmup"] == harness.header()["warmup"] == {
        "mode": "plateau",
        "window": measure.WARMUP_WINDOW,
        "floor": 2 * measure.WARMUP_WINDOW,
        "cap": measure.WARMUP_CAP,
        "plateau_pct": measure.WARMUP_PLATEAU_PCT,
    }
    assert results[0].warmup_plateau is True
    assert measure._record(results[0]) == harness.lines()[0]


def test_the_warmup_window_contributes_no_sample_to_a_published_figure(harness):
    """The assertion that matters most. Two runs of one cell, identical in every measured
    request and different only in how long they warmed up — one settled at the floor, one ran
    to the cap — publish the same row, field for field.

    The warmups are a different population on purpose: at 2 tok/s against 40 for every
    measured request, a warmup that reached a figure would move it by a factor, not by a
    rounding."""
    def settling(call):
        return rate_observation(2.0 if call.visit_index < 2 * measure.WARMUP_WINDOW else 40.0)

    def climbing(call):
        return rate_observation(2.0 + call.visit_index if call.visit_index < measure.WARMUP_CAP
                                else 40.0)

    harness.add_runtime("mlxlm")
    harness.sample.peaks = [128.0] * 8
    cell = harness.cell("oq__mlxlm", "mlxlm")

    harness.transport.responder = settling
    from_floor = harness.run([cell], warmup="plateau", measured=9,
                             results_dir=harness.tmp_path / "floor")
    harness.transport.responder = climbing
    from_cap = harness.run([cell], warmup="plateau", measured=9,
                           results_dir=harness.tmp_path / "cap")

    # A window per visit — nine samples are two visits — and both rows warmed up their own.
    assert len(from_floor[0].warmup_observations) == (
        measure.VISIT_ROUNDS * 2 * measure.WARMUP_WINDOW
    )
    assert from_floor[0].warmup_plateau is True
    assert len(from_cap[0].warmup_observations) == measure.VISIT_ROUNDS * measure.WARMUP_CAP
    assert from_cap[0].warmup_plateau is False

    assert [measure.decode_tps(observation) for observation in from_floor[0].observations] == (
        [40.0] * 9
    )
    assert report.summarize(from_floor) == report.summarize(from_cap)


# ------------------------------------------------------------------- the three workloads


def test_every_cell_runs_every_workload(harness):
    """One shape measures one corner, so a cell produces one result per (cell, workload)."""
    harness.add_runtime("mlxlm")
    harness.add_runtime("osaurus")
    cells = [harness.cell("oq__mlxlm", "mlxlm"), harness.cell("oq__osaurus", "osaurus")]

    results = harness.run(cells, workloads=THREE)

    assert [(result.cell.id, result.workload_id) for result in results] == [
        ("oq__mlxlm", "chat"), ("oq__mlxlm", "prefill"), ("oq__mlxlm", "decode"),
        ("oq__osaurus", "chat"), ("oq__osaurus", "prefill"), ("oq__osaurus", "decode"),
    ]
    assert all(len(result.observations) == MEASURED for result in results)
    assert all(result.status == "PASS" for result in results)


def test_one_model_load_serves_every_workload_in_a_visit(harness):
    """The cost that matters: a load per workload per visit would triple the wall time."""
    runtime = harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")], workloads=THREE)

    assert starts(harness) == ["mlxlm"] * 2  # two visits, one load each
    assert [handle.stops for handle in runtime.handles] == [1, 1]
    assert len(results) == 3  # three results out of two loads


def test_the_workloads_run_under_the_load_their_visit_started(harness):
    """Every request of a visit belongs to a runtime that was started once for that visit."""
    harness.add_runtime("mlxlm")
    harness.add_runtime("osaurus")

    harness.run([harness.cell("oq__mlxlm", "mlxlm"), harness.cell("oq__osaurus", "osaurus")],
                workloads=THREE)

    per_visit = harness.transport.calls_by_visit()
    # The plan flattens by round, so all cells take the larger quota first and the smaller
    # one on the reversed second round. Each visit carries three workloads' warmups and
    # measured requests under the single load it started.
    assert [len(calls) for calls in per_visit.values()] == [18, 18, 15, 15]
    assert starts(harness) == ["mlxlm", "osaurus", "osaurus", "mlxlm"]


def test_each_workload_carries_its_own_cap_and_messages(harness):
    harness.add_runtime("mlxlm")

    harness.run([harness.cell("oq__mlxlm", "mlxlm")], workloads=THREE)

    by_cap = harness.calls_by_workload()
    assert set(by_cap) == {128, 64, 512}
    assert {call.messages[0]["content"] for call in by_cap[128]} == {"hi"}
    assert {call.messages[0]["content"] for call in by_cap[512]} == {"hi"}
    assert {call.messages[0]["content"] for call in by_cap[64]} == {"long " * 400}


def test_each_workload_is_measured_and_sampled_on_its_own(harness):
    """A figure averaged across shapes describes no shape, so samples and peaks never mix."""
    harness.sample.peaks = [100.0, 20.0, 30.0, 10.0, 200.0, 3.0]
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")], workloads=THREE)

    assert [len(result.observations) for result in results] == [MEASURED] * 3
    assert [len(result.warmup_observations) for result in results] == [2 * WARMUPS] * 3
    # One sampler per workload per visit: a sampler around the whole visit would publish
    # decode's footprint as chat's.
    assert len(harness.sample.samplers) == 6
    assert [result.memory["peak_mb"] for result in results] == [100.0, 200.0, 30.0]


def test_the_cooldown_is_per_visit_and_not_per_workload(harness):
    harness.add_runtime("mlxlm")
    harness.add_runtime("osaurus")

    harness.run([harness.cell("oq__mlxlm", "mlxlm"), harness.cell("oq__osaurus", "osaurus")],
                workloads=THREE, cooldown_s=12.5)

    assert harness.sleeps() == [12.5] * 3


def test_each_workload_keeps_its_own_cold_load_provenance(harness):
    """One load is shared by the three shapes, so every row carries it rather than whichever
    shape happened to run first."""
    harness.add_runtime("mlxlm", cold_load_s=23.25, version="0.31.3")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")], workloads=THREE)

    assert [result.cold_load_s for result in results] == [pytest.approx(23.25)] * 3
    assert {result.runtime_version for result in results} == {"0.31.3"}


def test_the_persisted_header_names_all_three_workloads_and_every_line_names_its_own(harness):
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")], workloads=THREE)

    assert harness.header()["workloads"] == [
        {"id": "chat", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 128},
        {"id": "prefill", "messages": [{"role": "user", "content": "long " * 400}],
         "max_tokens": 64},
        {"id": "decode", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 512},
    ]
    records = harness.lines()
    assert len(records) == len(results) == 3
    assert [record["workload_id"] for record in records] == ["chat", "prefill", "decode"]


def test_a_visit_persists_one_line_per_workload_pair(harness):
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
                          workloads=THREE, results_dir=results_dir)

    # Nothing on disk during the first visit; after it, the header and the first cell's three
    # pairs; after the last one, the header and six pairs. A line is a (cell, workload) pair.
    assert seen[0] is None
    assert sorted(set(seen) - {None}) == [4, 7]
    assert len(harness.lines(results_dir)) == len(results) == 6


# ------------------------------------------------------------------------- every request


def test_every_request_pins_temperature_zero_and_the_fixed_seed(harness):
    harness.add_runtime("mlxlm")

    harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    assert harness.transport.calls
    assert {call.temperature for call in harness.transport.calls} == {0.0}
    assert {call.seed for call in harness.transport.calls} == {0}
    assert measure.TEMPERATURE == 0.0


def test_every_request_carries_its_workload_s_max_tokens(harness):
    """The cap belongs to the workload: it moved there so one shape's decode tok/s is never
    a ratio between a model that stopped at 40 tokens and one that ran to the cap."""
    harness.add_runtime("mlxlm")
    pinned = workload("chat", max_tokens=99)

    harness.run([harness.cell("oq__mlxlm", "mlxlm")], workloads=[pinned])

    assert {call.max_tokens for call in harness.transport.calls} == {99}
    assert {call.messages[0]["content"] for call in harness.transport.calls} == {"hi"}


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


# ------------------------------------------------------- the cold visit's first request

# The lazy loader's cost, from the live probe the contract was written against: oMLX reports
# ~3.1 s ready, then spends 3.08-3.93 s inside request #1 against ~0.42 s for the requests
# after it. The request is made either way; the record used to throw its latency away.
FIRST_REQUEST_S = 3.93
ORDINARY_REQUEST_S = 0.42
# The second visit's first request. Nothing was deferred into it -- the load was paid in the
# cold visit -- so a slow one must not overwrite the cold visit's figure or earn a note.
WARM_VISIT_FIRST_S = 9.5


def first_request_responder(first_request_s=FIRST_REQUEST_S, ordinary_s=ORDINARY_REQUEST_S):
    """Every request at *ordinary_s*, except the first one the loop ever makes."""

    def responder(call):
        return FakeObservation(total_s=first_request_s if call.index == 0 else ordinary_s)

    return responder


def test_first_request_s_is_the_cold_visits_first_warmup(harness):
    harness.transport.responder = first_request_responder()
    runtime = harness.add_runtime("mlxlm", cold_load_s=3.12)

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    # The first warmup of the visit that set the cold load, not the first measured request,
    # and not a number built from either: the request's own latency, as it was measured.
    assert results[0].cold_load_s == pytest.approx(3.12)
    assert results[0].first_request_s == pytest.approx(FIRST_REQUEST_S)
    assert results[0].first_request_s != pytest.approx(results[0].observations[0].total_s)
    assert harness.transport.calls[0].visit_index == 0, "call 0 is a warmup of the cold visit"

    # The second visit's first request is an ordinary one and does not overwrite the cold
    # visit's figure -- the visit that recorded the load is the visit that carries it.
    assert [handle.first_request_s for handle in runtime.handles] == [
        pytest.approx(FIRST_REQUEST_S),
        None,
    ]


def test_every_workload_row_carries_the_visits_first_request(harness):
    """One load is shared by the cell's workloads, so the request that paid for it is too."""
    harness.transport.responder = first_request_responder()
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")], workloads=THREE)

    assert len(results) == 3
    assert [result.first_request_s for result in results] == [pytest.approx(FIRST_REQUEST_S)] * 3


def test_the_cold_visit_records_which_workload_made_that_request(harness):
    """One request has one owner. WHICH shape paid for the load is recorded on every row of the
    cell, beside the latency that is the visit's fact, so a row can be asked whether the visit's
    first request was its own."""
    harness.transport.responder = first_request_responder()
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")], workloads=THREE)

    assert [result.first_request_workload_id for result in results] == ["chat"] * 3
    # The other two shapes were in the same visit and made ordinary requests in it: the load
    # landed in chat's request #1, and neither of theirs.
    assert [result.warmup_observations[0].total_s for result in results] == [
        pytest.approx(FIRST_REQUEST_S),
        pytest.approx(ORDINARY_REQUEST_S),
        pytest.approx(ORDINARY_REQUEST_S),
    ]


def deferred_rows(harness):
    """One cell's three workload rows, its cold visit's request #1 charged to `chat`."""
    harness.transport.responder = first_request_responder()
    harness.add_runtime("mlxlm")
    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")], workloads=THREE)
    return {row["workload_id"]: row for row in report.summarize(results)}


def test_the_workload_that_made_the_first_request_earns_the_note(harness):
    """The claim is still made where it is true: chat made request #1, and its own requests
    after it came back in 0.42 s."""
    rows = deferred_rows(harness)

    assert rows["chat"]["first_request_s"] == pytest.approx(FIRST_REQUEST_S)
    assert rows["chat"]["first_request_note"] is not None
    assert f"{FIRST_REQUEST_S:.2f} s" in rows["chat"]["first_request_note"]
    assert f"{ORDINARY_REQUEST_S:.2f} s" in rows["chat"]["first_request_note"]


def test_a_sibling_workload_claims_nothing_from_the_visits_first_request(harness):
    """The defect. prefill and decode measured 0.42 s requests in that same visit, so read
    against their own medians the visit's 3.93 s is +3.51 s of deferral that never happened --
    and they did not make that request, so the claim is not theirs to make."""
    rows = deferred_rows(harness)

    for workload_id in ("prefill", "decode"):
        assert rows[workload_id]["first_request_s"] == pytest.approx(FIRST_REQUEST_S), (
            "the column is the visit's fact and every row of the cell keeps it"
        )
        assert rows[workload_id]["first_request_note"] is None


def test_a_cold_visit_that_made_no_request_credits_no_workload(harness):
    """No warmup observation means no request #1, so nothing is recorded and every row of the
    cell stays silent."""
    harness.add_runtime("omlx", start_error=RuntimeError("model type not supported"))

    results = harness.run([harness.cell("oq__omlx", "omlx")], workloads=THREE)

    assert [result.status for result in results] == ["N/A"] * 3
    assert [result.first_request_workload_id for result in results] == [None] * 3
    assert [row["first_request_note"] for row in report.summarize(results)] == [None] * 3


def test_a_warm_visit_records_no_first_request_of_its_own(harness):
    """The load was paid in the cold visit. The second visit's first request is an ordinary one
    however long it took, and it overwrites nothing, credits no workload and earns no note: a
    visit that did not record the cold load is not where a load can have landed."""
    def responder(call):
        if call.visit == 2 and call.visit_index == 0:
            return FakeObservation(total_s=WARM_VISIT_FIRST_S)
        return FakeObservation(total_s=FIRST_REQUEST_S if call.index == 0 else ORDINARY_REQUEST_S)

    harness.transport.responder = responder
    runtime = harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")], workloads=THREE)

    # The slow second visit really happened: it is a raw observation, on the record like every
    # other warmup, and it is not the visit's first request.
    assert results[0].warmup_observations[WARMUPS].total_s == pytest.approx(WARM_VISIT_FIRST_S)
    assert [handle.first_request_s for handle in runtime.handles] == [
        pytest.approx(FIRST_REQUEST_S),
        None,
    ]
    assert [result.first_request_s for result in results] == [pytest.approx(FIRST_REQUEST_S)] * 3
    assert [result.first_request_workload_id for result in results] == ["chat"] * 3

    notes = {row["workload_id"]: row["first_request_note"] for row in report.summarize(results)}
    assert notes["chat"] is not None
    assert f"{WARM_VISIT_FIRST_S:.2f} s" not in notes["chat"], "the warm visit carries no note"


def test_a_cell_with_no_warmups_records_none_first_request_s(harness):
    """No visit ever reached this cell, so no request was made and none can be charged."""
    harness.add_runtime("omlx", start_error=RuntimeError("model type not supported"))

    results = harness.run([harness.cell("oq__omlx", "omlx")])

    assert results[0].status == "N/A"
    assert results[0].warmup_observations == []
    assert results[0].first_request_s is None
    assert results[0].first_request_workload_id is None


def test_a_first_request_that_never_came_back_records_none(harness):
    """Its duration is how long it waited for the failure, not what the runtime charged for
    the load -- and the load is the only thing this number is for."""
    def responder(call):
        if call.index == 0:
            return FakeObservation(ok=False, error="TimeoutError: read timed out",
                                   ttft_s=None, last_content_s=None, total_s=600.0)
        return FakeObservation()

    harness.transport.responder = responder
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    assert results[0].first_request_s is None
    # The failed first request is still a raw observation, on the record with its duration.
    assert results[0].warmup_observations[0].total_s == pytest.approx(600.0)
    assert results[0].status == "PASS", "a failed warmup is not a failed cell"


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
    pinned = workload("short-chat", content="hello")

    harness.run(cells, workloads=[pinned])

    header = harness.header()
    assert header["temperature"] == 0.0
    assert header["seed"] == 0
    assert header["warmup"] == WARMUPS
    assert header["measured"] == MEASURED
    # The run-level max_tokens is gone on purpose: three workloads carry three caps, and one
    # run-level number would be a half-truth about two of them. The cap is in the workload.
    assert "max_tokens" not in header
    assert header["workloads"] == [
        {"id": "short-chat", "messages": [{"role": "user", "content": "hello"}], "max_tokens": 256}
    ]

    record, = harness.lines()
    assert record["workload_id"] == "short-chat"
    assert record["cell"] == {"id": "oq__mlxlm", "runtime": "mlxlm",
                              "artifact_dir": cells[0].artifact_dir, "label": "affine-4bit"}
    assert record["status"] == "PASS"
    assert record["cold_load_s"] == pytest.approx(7.5)
    assert record["first_request_s"] == pytest.approx(2.6)
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
                runtime_version="mlx-lm 0.31.3", disk_bytes=123, workload_id="chat",
                first_request_s=None, first_request_workload_id=None, warmup_plateau=None,
                batch_spans=()):
    """A CellResult to hand straight to write_jsonl, with no run behind it."""
    return measure.CellResult(
        cell=measure.Cell(id=cell_id, runtime=runtime, artifact_dir="/models/oq4", label="oq4"),
        workload_id=workload_id,
        status="PASS",
        reason=None,
        observations=list(observations),
        batch_spans=list(batch_spans),
        warmup_observations=[],
        warmup_plateau=warmup_plateau,
        cold_load_s=12.5,
        first_request_s=first_request_s,
        first_request_workload_id=first_request_workload_id,
        memory={"peak_mb": 9150.0},
        runtime_version=runtime_version,
        disk_bytes=disk_bytes,
    )


def test_write_jsonl_writes_a_header_and_one_object_per_result(tmp_path):
    observations = [
        FakeObservation(),
        FakeObservation(total_s=2.75),
        FakeObservation(ok=False, ttft_s=None, last_content_s=None, error="boom"),
    ]
    results = [
        cell_result(observations, disk_bytes=123),
        cell_result([FakeObservation()], cell_id="oq__omlx", runtime="omlx",
                    runtime_version="oMLX 0.3", workload_id="decode"),
    ]
    run = {
        "temperature": 0.0,
        "seed": 0,
        "warmup": WARMUPS,
        "measured": MEASURED,
        "cooldown_s": 30.0,
        "workloads": [
            {"id": "chat", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 128},
            {"id": "decode", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 512},
        ],
    }
    path = tmp_path / "run" / "results.jsonl"

    measure.write_jsonl(results, str(path), run=run)

    header, *lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert header == run
    assert len(lines) == 2
    # One line per (cell, workload) pair, each naming the shape that produced it.
    assert [line["workload_id"] for line in lines] == ["chat", "decode"]
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


def test_the_deferred_load_note_stays_recomputable_from_the_jsonl(tmp_path):
    """The note is decided from which workload made the visit's first request, so the file has
    to say which one that was: a reader re-deriving the row from disk gets the same claim."""
    results = [
        cell_result([FakeObservation(total_s=ORDINARY_REQUEST_S)] * MEASURED,
                    first_request_s=FIRST_REQUEST_S, first_request_workload_id="chat")
    ]
    path = tmp_path / "results.jsonl"

    measure.write_jsonl(results, str(path), run={"temperature": 0.0})

    record, = [json.loads(line) for line in path.read_text().splitlines()[1:]]
    assert record["first_request_s"] == pytest.approx(FIRST_REQUEST_S)
    assert record["first_request_workload_id"] == "chat"

    rebuilt = cell_result(
        [FakeObservation(**raw) for raw in record["observations"]],
        first_request_s=record["first_request_s"],
        first_request_workload_id=record["first_request_workload_id"],
    )
    assert report.summarize([rebuilt])[0]["first_request_note"] == (
        report.summarize(results)[0]["first_request_note"]
    )


def test_summaries_stay_recomputable_from_the_jsonl(tmp_path):
    results = [cell_result([FakeObservation(ttft_s=t) for t in (0.4, 0.5, 0.6, 0.7, 0.8)])]
    path = tmp_path / "results.jsonl"

    measure.write_jsonl(results, str(path), run={"temperature": 0.0})

    # Line 1 of the file is the run header; every line after it is a cell.
    records = [json.loads(line) for line in path.read_text().splitlines()[1:]]
    rebuilt = [
        measure.CellResult(
            cell=measure.Cell(**record["cell"]),
            workload_id=record["workload_id"],
            status=record["status"],
            reason=record["reason"],
            observations=[FakeObservation(**raw) for raw in record["observations"]],
            batch_spans=record.get("batch_spans", []),
            warmup_observations=[FakeObservation(**raw) for raw in record["warmup_observations"]],
            warmup_plateau=record["warmup_plateau"],
            cold_load_s=record["cold_load_s"],
            first_request_s=record["first_request_s"],
            first_request_workload_id=record["first_request_workload_id"],
            memory=record["memory"],
            runtime_version=record["runtime_version"],
            disk_bytes=record["disk_bytes"],
        )
        for record in records
    ]

    assert report.summarize(rebuilt) == report.summarize(results)


# ------------------------------------------------------------------------ reading a run

# A real Phase 3 column: one runtime, twelve (cell, workload) pairs. results/ is gitignored,
# so this is read where it lies and skipped in a checkout that does not have it -- copying it
# in as a fixture would make the test check a copy instead of the artifact.
REAL_GRID_RUN = (
    Path(__file__).resolve().parents[1]
    / "results" / "grid" / "20260916T014210Z-format" / measure.RESULTS_FILENAME
)


def parsed_lines(path: Path) -> list[dict]:
    """Every line of a results.jsonl as parsed JSON: line 1 the header, the rest records."""
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_load_run_round_trips_every_record_of_a_real_run():
    """The loader is the exact inverse of the writer, checked against a real column rather
    than a fixture: every record on disk rebuilds into an object that ``_record`` turns back
    into that same record, dict for dict. One assertion over a real file covers every field a
    loader could have dropped -- the derived ones, the raw ones, the cell, both observation
    lists -- which is the only way to know a reader agrees with the writer about the shape."""
    if not REAL_GRID_RUN.exists():
        pytest.skip(f"no grid run in this checkout: {REAL_GRID_RUN}")
    header, results = measure.load_run(REAL_GRID_RUN)
    lines = parsed_lines(REAL_GRID_RUN)

    assert results, "the run has records to read"
    assert header == lines[0]
    assert len(results) == len(lines) - 1
    assert [result.workload_id for result in results[:3]] == ["chat", "prefill", "decode"]
    for index, result in enumerate(results):
        line = lines[index + 1]
        # A column written before the plateau rule carries no `warmup_plateau`, and the loader
        # reads that absence as the `None` it honestly is. The round trip is otherwise exact:
        # every other field has to come back byte for byte.
        assert measure._record(result) == {**line, "warmup_plateau": line.get("warmup_plateau")}


def test_the_run_directory_and_its_file_read_the_same(tmp_path):
    """Both name the same run, and the header comes back as it was written -- a reader that
    re-derived the pins would be reporting its own guess about what was held constant."""
    path = tmp_path / "20260916T014210Z-format" / measure.RESULTS_FILENAME
    run = {
        "temperature": 0.0,
        "seed": 0,
        "warmup": WARMUPS,
        "measured": MEASURED,
        "cooldown_s": 30.0,
        "workloads": [
            {"id": "chat", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 128}
        ],
    }
    measure.write_jsonl([cell_result([FakeObservation()])], str(path), run=run)

    header, results = measure.load_run(path.parent)

    assert header == run
    assert measure.load_run(path) == (header, results)


def test_the_derived_fields_in_the_file_are_ignored_on_read(tmp_path):
    """measured_count, warmup_count and drift are the file's own summary of its own samples.
    A loader that read them back would let a hand-edited file publish a drift its
    observations do not support, so all three are recomputed here and the file's copy of
    them changes nothing -- including what the rebuilt object writes back."""
    result = replace(
        cell_result(
            [FakeObservation(ttft_s=0.5, last_content_s=2.5 + 0.1 * index)
             for index in range(MEASURED)]
        ),
        warmup_observations=[FakeObservation(text="warmup")] * (2 * WARMUPS),
    )
    honest_path = tmp_path / "honest" / measure.RESULTS_FILENAME
    measure.write_jsonl([result], str(honest_path), run={"temperature": 0.0})
    honest, = parsed_lines(honest_path)[1:]
    assert honest["drift"]["n"] == MEASURED, "the run has a drift to lie about"

    tampered = honest | {
        "measured_count": 99,
        "warmup_count": 99,
        "drift": {"early_median_tps": 1.0, "late_median_tps": 9999.0,
                  "change_pct": 9999.0, "n": 99},
    }
    edited_path = tmp_path / "hand-edited" / measure.RESULTS_FILENAME
    edited_path.parent.mkdir(parents=True)
    edited_path.write_text(
        json.dumps({"temperature": 0.0}) + "\n" + json.dumps(tampered) + "\n"
    )

    loaded, = measure.load_run(edited_path)[1]

    assert len(loaded.observations) == honest["measured_count"] == MEASURED
    assert len(loaded.warmup_observations) == honest["warmup_count"] == 2 * WARMUPS
    assert measure.measured_drift(loaded.observations) == honest["drift"]
    assert measure._record(loaded) == honest


def test_a_reasoning_channel_survives_the_round_trip(tmp_path):
    """``reasoning_text`` is the field a loader can drop in silence: it has a default, so
    rebuilding an observation without it raises nothing. The real grid column this loader is
    round-tripped against emitted no reasoning at all in any of its observations, so it
    cannot catch that -- this one carries the channel in both lists."""
    result = replace(
        cell_result([FakeObservation(reasoning_text="thinking about it", reasoning_tokens=12)]
                    * MEASURED),
        warmup_observations=[FakeObservation(reasoning_text="thinking")] * WARMUPS,
    )
    path = tmp_path / measure.RESULTS_FILENAME
    measure.write_jsonl([result], str(path), run={"temperature": 0.0})
    honest, = parsed_lines(path)[1:]

    loaded, = measure.load_run(path)[1]

    assert loaded.observations[0].reasoning_text == "thinking about it"
    assert loaded.warmup_observations[0].reasoning_text == "thinking"
    assert measure._record(loaded) == honest


def test_a_record_missing_a_field_is_refused_rather_than_defaulted(tmp_path):
    """Eight of the columns under results/grid/ were written before
    ``first_request_workload_id`` existed, and this is what reading one of them does: the
    field is refused, by name and by line. Filling it with None would render those columns
    as cells whose cold visit made no request -- a false claim standing where a missing
    field is, and the defect that field was added to fix. A schema the file predates is the
    coordinator's call to migrate, not the loader's to guess at."""
    path = tmp_path / measure.RESULTS_FILENAME
    measure.write_jsonl([cell_result([FakeObservation()])], str(path),
                        run={"temperature": 0.0})
    lines = path.read_text().splitlines()
    record = json.loads(lines[1])
    del record["first_request_workload_id"]
    path.write_text(lines[0] + "\n" + json.dumps(record) + "\n")

    with pytest.raises(ValueError) as error:
        measure.load_run(path)

    assert str(path) in str(error.value)
    assert "line 2" in str(error.value)
    assert "first_request_workload_id" in str(error.value)


def test_a_truncated_last_line_names_the_line_it_stopped_at(tmp_path):
    """The ordinary corruption. write_jsonl is atomic, so a half-written file is a copy
    interrupted in flight -- and which line it was cut at is the whole diagnosis."""
    path = tmp_path / measure.RESULTS_FILENAME
    measure.write_jsonl(
        [cell_result([FakeObservation()]),
         cell_result([FakeObservation()], workload_id="decode")],
        str(path), run={"temperature": 0.0},
    )
    lines = path.read_text().splitlines()
    cut = lines[2][: len(lines[2]) // 2]
    path.write_text("\n".join(lines[:2]) + "\n" + cut + "\n")

    with pytest.raises(ValueError) as error:
        measure.load_run(path)

    assert str(path) in str(error.value)
    assert "line 3" in str(error.value)


def test_an_empty_file_names_the_header_it_is_missing(tmp_path):
    path = tmp_path / measure.RESULTS_FILENAME
    path.write_text("")

    with pytest.raises(ValueError) as error:
        measure.load_run(path)

    assert str(path) in str(error.value)
    assert "line 1" in str(error.value)


def test_a_first_line_that_is_not_an_object_is_refused(tmp_path):
    path = tmp_path / measure.RESULTS_FILENAME
    path.write_text("[1, 2, 3]\n")

    with pytest.raises(ValueError) as error:
        measure.load_run(path)

    assert str(path) in str(error.value)
    assert "line 1" in str(error.value)


def test_a_line_that_is_not_a_record_names_itself(tmp_path):
    """A line that parses as an object but is not a cell record -- one missing its cell, say
    -- is refused with the line it was found on, never skipped as if it were not there."""
    path = tmp_path / measure.RESULTS_FILENAME
    measure.write_jsonl([cell_result([FakeObservation()])], str(path),
                        run={"temperature": 0.0})
    path.write_text(path.read_text() + json.dumps({"workload_id": "chat"}) + "\n")

    with pytest.raises(ValueError) as error:
        measure.load_run(path)

    assert str(path) in str(error.value)
    assert "line 3" in str(error.value)


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


def test_a_reasoning_only_cell_publishes_the_sample_count_measure_recorded(harness):
    """The divergence, on the record: measure wrote ``measured_count: 5`` while the leaderboard
    printed ``n = 0/5`` for the same cell, because report counted samples with ``ok`` and
    measure counted them with ``came_back``. There is one definition now, and it is measure's."""
    harness.transport.responder = measured_responses(*[reasoning_only(COHERENT)] * MEASURED)
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")])

    record, = harness.lines()
    assert record["measured_count"] == MEASURED

    row = report.summarize(results)[0]
    assert row["n_measured"] == MEASURED
    assert row["n_requests"] == MEASURED


def test_the_shared_predicate_is_ok_or_the_empty_content_stream_and_nothing_else():
    """It is public because report counts a cell's samples with it, and its one exception is a
    response that answered in the reasoning channel — every other failure is the transport's."""
    assert measure.came_back(FakeObservation()) is True
    assert measure.came_back(reasoning_only(COHERENT)) is True
    assert measure.came_back(reasoning_only(COHERENT, ok=True, error=None)) is True
    assert measure.came_back(
        FakeObservation(ok=False, error="TimeoutError: read timed out")
    ) is False
    assert measure.came_back(FakeObservation(ok=False, error="HTTPError: 500")) is False
    assert measure.came_back(
        FakeObservation(ok=False, error="chat stream content timing is unavailable")
    ) is False


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


def test_a_column_written_before_the_plateau_rule_still_loads_and_claims_no_verdict():
    """The five 2026-09-16 columns are what the Phase 5 write-up published, and the tool that
    published them has to keep being able to read them.

    `warmup_plateau` is the one field read leniently, because for those rows the absence IS
    the fact: they ran a fixed budget of three, the plateau rule never ran, and `None` -- no
    verdict -- is true of them. It must not come back as `False`, which would claim their
    warmup window hit a cap that did not exist yet.
    """
    if not REAL_GRID_RUN.exists():
        pytest.skip(f"no grid run in this checkout: {REAL_GRID_RUN}")
    lines = parsed_lines(REAL_GRID_RUN)
    if "warmup_plateau" in lines[1]:
        pytest.skip(f"{REAL_GRID_RUN.parent.name} was written under the plateau rule")

    header, results = measure.load_run(REAL_GRID_RUN)

    assert results, "a pre-plateau column still loads"
    assert all(result.warmup_plateau is None for result in results)
    assert header["warmup"] == 3, "and its header still names the fixed budget it ran"


def test_a_flat_boost_phase_does_not_count_as_warm(harness):
    """The measured sequence that made the rule compare two windows instead of one.

    oMLX serving Qwen3.5-4B-oQ4, fourteen identical chat requests in a flat loop on
    2026-09-16: 103.5, 102.8, 103.3, then a step down to ~73 that holds for eleven more. The
    machine serves its first three requests from a boost state, and that state is FLAT -- 0.5%
    spread. A rule reading one window would have called the cell warm at request three, at a
    rate 40% above what it can sustain, and published the boost rate as the result.
    """
    measured = [103.5, 102.8, 103.3, 70.8, 73.4, 75.7, 73.6, 75.2, 75.3, 74.6, 72.0, 73.8]
    harness.transport.responder = rate_responder(measured)
    harness.add_runtime("omlx")

    results = harness.run([harness.cell("oq__omlx", "omlx")], warmup="plateau", measured=1)
    warmups = [measure.decode_tps(o) for o in results[0].warmup_observations]

    assert not measure._settled(measured[:3]), "the boost phase alone is not warmth"
    assert len(warmups) == 11, "the window closes on the sustained rate, not the boost rate"
    assert results[0].warmup_plateau is True
    assert warmups[-1] < 80.0, f"warmed to the sustained rate, not the boost rate: {warmups}"


def test_a_noisy_workload_with_no_trend_is_warm_not_unsettled(harness):
    """Variance is not warmth, measured.

    mlx-lm serving stock-4bit, the prefill workload's warmup rates in the aborted 03:30Z
    column: 70.3 74.7 72.5 77.1 71.9 78.6 77.5 73.6 70.2 70.9 75.2 64.8 72.5 71.3 76.8 75.4.
    No trend at all -- the cell is warm from request one and simply swings +/-8% per request.
    A rule that asked neighbouring rates to agree ran it to the cap, spent sixteen requests
    learning nothing, and reported "did not settle" about a cell with nothing left to warm.
    Noise is a property of the workload; reading it as unfinished warmup is the conflation the
    rule exists to undo.
    """
    noisy = [70.3, 74.7, 72.5, 77.1, 71.9, 78.6, 77.5, 73.6, 70.2, 70.9,
             75.2, 64.8, 72.5, 71.3, 76.8, 75.4]
    harness.transport.responder = rate_responder(noisy)
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")], warmup="plateau", measured=1)

    assert results[0].warmup_plateau is True, "a noisy cell with no trend is warm"
    assert len(results[0].warmup_observations) < measure.WARMUP_CAP, (
        "and it must not pay the cap to be told so"
    )


# ------------------------------------------------------------------- the concurrency pin

# A batch is `concurrency` requests issued together under one clock, and `measured` counts
# batches: at 1 a batch is one request, at 8 nine batches are 72 requests and nine spans. The
# span is what aggregate throughput divides by, so four overlapping requests take one span
# between them -- summing theirs would count the overlap four times.


def test_a_concurrency_one_run_is_byte_identical_to_one_that_never_heard_of_concurrency(harness):
    """The assertion that matters most.

    At concurrency 1 a batch is one request, and every column measured so far was measured that
    way. A run pinning it has to produce the record the writer produced before batches existed --
    the same bytes, not merely the same figures -- or the N=1 column of a sweep is not the grid
    it is joined to.
    """
    harness.add_runtime("mlxlm")
    harness.sample.peaks = [128.0] * 8  # one peak per visit per run, the same for both
    cell = harness.cell("oq__mlxlm", "mlxlm")

    pinned = harness.run([cell], results_dir=harness.tmp_path / "pinned", concurrency=1)
    untouched = harness.run([cell], results_dir=harness.tmp_path / "untouched")

    assert harness.results_file(harness.tmp_path / "pinned").read_text() == (
        harness.results_file(harness.tmp_path / "untouched").read_text()
    ), "the pin at 1 and the run that never named it are one run"

    record, = harness.lines(harness.tmp_path / "pinned")
    # And byte-identical is checked against the fields the writer emitted before there was a
    # batch to span: nothing ran a batch, so nothing claims a span. A reader of an older column
    # gets `[]` from the same absence.
    assert set(record) == {
        "cell", "workload_id", "status", "reason", "cold_load_s", "first_request_s",
        "first_request_workload_id", "memory", "runtime_version", "disk_bytes",
        "measured_count", "warmup_count", "warmup_plateau", "drift", "observations",
        "warmup_observations",
    }
    assert pinned[0].batch_spans == []
    assert len(pinned[0].observations) == MEASURED


def test_a_concurrency_below_one_is_refused(harness):
    """A batch is at least one request. Zero is not a slower run, it is no measurement, and it
    is refused before a runtime is started for it."""
    harness.add_runtime("mlxlm")
    cell = harness.cell("oq__mlxlm", "mlxlm")

    for bad in (0, -2):
        with pytest.raises(ValueError, match="concurrency"):
            harness.run([cell], concurrency=bad)

    assert harness.transport.calls == []


def test_the_run_header_pins_the_concurrency(harness):
    """How the run drove the cells is not a property of a cell, so it rides in the header with
    the sampling pins -- which is what lets a sweep vary it and a join compare it."""
    harness.add_runtime("mlxlm")
    cell = harness.cell("oq__mlxlm", "mlxlm")

    harness.run([cell], measured=1, concurrency=4)
    assert harness.header()["concurrency"] == 4
    assert measure.load_run(harness.results_file())[0]["concurrency"] == 4

    harness.run([cell], measured=1, results_dir=harness.tmp_path / "sequential")
    assert harness.header(harness.tmp_path / "sequential")["concurrency"] == 1


def test_the_run_header_pins_the_prompt_length_verbatim_or_none(harness):
    """The prompt-length pin rides in the header with the sampling pins, and this module writes
    what it is handed: `None` for the three workloads that send their own literals, and the
    target beside the count the caller's tokenizer achieved for a sized prompt."""
    harness.add_runtime("mlxlm")
    cell = harness.cell("oq__mlxlm", "mlxlm")
    pin = {"target": 4096, "achieved": 4093}

    harness.run([cell], measured=1, prompt_tokens=pin)

    assert harness.header()["prompt_tokens"] == pin
    assert measure.load_run(harness.results_file())[0]["prompt_tokens"] == pin

    harness.run([cell], measured=1, results_dir=harness.tmp_path / "literals")
    assert harness.header(harness.tmp_path / "literals")["prompt_tokens"] is None


def test_a_run_at_four_issues_four_requests_per_batch_and_records_one_span(harness):
    """One batch, one clock, four requests: the observations are every request's and the span is
    the batch's, so a row at N=4 has four observations per span."""
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")], measured=MEASURED, concurrency=4)

    result = results[0]
    assert len(result.observations) == MEASURED * 4
    assert len(result.batch_spans) == MEASURED
    assert all(span > 0 for span in result.batch_spans)
    assert result.status == "PASS", "every request of every batch came back"
    # A warmup step is a batch too, so a visit makes warmup-batches plus its quota, four
    # requests each -- and the measured quota is still split 3 then 2 as it always was.
    assert [len(calls) for calls in harness.transport.calls_by_visit().values()] == [
        (WARMUPS + 3) * 4, (WARMUPS + 2) * 4
    ]
    assert len(result.warmup_observations) == measure.VISIT_ROUNDS * WARMUPS * 4


def test_measured_counts_batches_not_requests(harness):
    """The pin's arithmetic. Three batches of four are twelve requests and three spans; the
    order's own example, nine batches of eight, is 72 observations and nine spans."""
    harness.add_runtime("mlxlm")
    cell = harness.cell("oq__mlxlm", "mlxlm")

    three = harness.run([cell], measured=3, concurrency=4, results_dir=harness.tmp_path / "four")
    nine = harness.run([cell], measured=9, concurrency=8, results_dir=harness.tmp_path / "eight")

    assert (len(three[0].observations), len(three[0].batch_spans)) == (12, 3)
    assert (len(nine[0].observations), len(nine[0].batch_spans)) == (72, 9)
    assert harness.header(harness.tmp_path / "eight")["measured"] == 9
    assert harness.lines(harness.tmp_path / "eight")[0]["measured_count"] == 72


def test_a_batchs_span_is_shorter_than_the_sum_of_its_requests(harness):
    """The whole reason the clock is around the batch.

    Four requests of 250 ms each finish in about one 250 ms batch. An aggregate built from
    their per-request wall clocks would divide the same tokens by four times the window the
    batch actually occupied -- which is why the span is measured and not summed.

    250 ms, not 20: this test was 20 ms and flaked on CI's shared macOS runners, where
    thread-pool startup took ~30 ms and landed inside the span -- `sum(totals) > 2 * span`
    read 0.08 > 0.104. That overhead is the known ceiling `_batch`'s ponytail comment names,
    and a fixed cost must be small against the request or the test prices the pool instead of
    the overlap. At 250 ms even 150 ms of overhead leaves the assertion true.
    """
    per_request_s = 0.25

    def responder(call):
        time.sleep(per_request_s)
        return FakeObservation(total_s=per_request_s)

    harness.transport.responder = responder
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")], measured=1, concurrency=4)

    span, = results[0].batch_spans
    totals = [observation.total_s for observation in results[0].observations]
    assert len(totals) == 4
    assert span >= per_request_s, "the batch waited for the requests it issued"
    assert span < sum(totals), "the four clocks overlap: the span is not their sum"
    assert sum(totals) > 2 * span, "and it prices the overlap rather than one request"


def test_batch_spans_round_trip_and_a_record_without_them_loads_as_no_batches(harness):
    """The spans are raw measurements, so they come back as they went in -- and a record written
    before concurrency existed ran no batch, which `[]` says exactly. It is not reconstructed
    from the per-request totals either: a gap between two sequential requests belongs to
    neither one."""
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")], measured=3, concurrency=4)

    record, = harness.lines()
    assert len(record["batch_spans"]) == 3

    _header, loaded = measure.load_run(harness.results_file())
    assert loaded[0].batch_spans == record["batch_spans"] == results[0].batch_spans
    assert measure._record(loaded[0]) == record

    without = {key: value for key, value in record.items() if key != "batch_spans"}
    older_path = harness.tmp_path / "older" / measure.RESULTS_FILENAME
    older_path.parent.mkdir(parents=True)
    older_path.write_text(json.dumps({"temperature": 0.0}) + "\n" + json.dumps(without) + "\n")

    older, = measure.load_run(older_path)[1]

    assert older.batch_spans == []
    assert "batch_spans" not in measure._record(older), (
        "a cell that ran no batch writes the record this file wrote before the field existed"
    )


def test_a_concurrent_cells_requests_are_judged_one_at_a_time(harness):
    """The gate is not a batch judgement and did not move: a cell at N=4 emitting token salad is
    the failed cell it is at N=1, however fast its batches were."""
    harness.transport.responder = lambda call: FakeObservation(text=SALAD)
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")], measured=MEASURED, concurrency=4)

    assert results[0].status == "FAIL"
    assert results[0].reason == "incoherent output: replacement characters"
    record, = harness.lines()
    assert len(record["observations"]) == MEASURED * 4
    assert record["observations"][0]["text"] == SALAD
    assert len(results[0].batch_spans) == MEASURED


# The two series a warmup window can read. This cell's per-request decode rates climb forever --
# what a 3% trend test can never call settled -- while every request takes the same wall time and
# reports the same 100 tokens, so a batch's aggregate throughput is flat. Whichever series the
# window reads decides whether the cell settles or pays the cap, at the same constants.
CLIMBING_SLEEP_S = 0.02


def climbing_per_request_responder(seconds=CLIMBING_SLEEP_S):
    def responder(call):
        time.sleep(seconds)
        return rate_observation(20.0 + next(calls))

    calls = itertools.count()
    return responder


def test_a_concurrent_warmup_settles_on_the_batchs_aggregate_throughput(harness):
    """Plan 06-01a, applied: at N>1 the per-request series swings without trend and never
    settles, while the quantity the sweep publishes does. Same rule, same constants, other
    series -- so the window closes instead of running every concurrent cell to the cap."""
    harness.transport.responder = climbing_per_request_responder()
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")], warmup="plateau", measured=1,
                          concurrency=4)

    warmups = results[0].warmup_observations
    assert results[0].warmup_plateau is True, "the window closed"
    assert len(warmups) < measure.WARMUP_CAP * 4, "and it closed before the cap"
    assert not measure._settled([measure.decode_tps(observation) for observation in warmups]), (
        "the per-request series it did not read was still climbing"
    )


def test_a_sequential_warmup_still_settles_on_the_request_s_own_rate(harness):
    """The other half of the pin, and why nothing about the existing grid changes: at N=1 the
    series is the request's own decode rate exactly as it always was, so this cell runs to the
    cap and says so."""
    harness.transport.responder = climbing_per_request_responder()
    harness.add_runtime("mlxlm")

    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")], warmup="plateau", measured=1)

    assert results[0].warmup_plateau is False
    assert len(results[0].warmup_observations) == measure.WARMUP_CAP
    assert results[0].batch_spans == []
