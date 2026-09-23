"""Checks for ohyesmlx.report and ohyesmlx.cli.

``measure.py`` (issue #5) is being written concurrently against docs/interfaces.md, so the
shapes it will hand over are stood in for here: ``FakeObservation``, ``FakeCell`` and
``FakeCellResult`` are transcriptions of the contract, and no module under test is patched
to make them fit. Everything else runs for real — the JSONL is parsed back off disk, the
disk sizes are real files in a tmp directory, and the CLI is driven through ``main()``.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import sys
from pathlib import Path

import pytest

from ohyesmlx import cli, measure, report

# --- stand-ins for docs/interfaces.md (measure.py, issue #5) -------------------------------


@dataclasses.dataclass(frozen=True)
class FakeObservation:
    ok: bool
    error: str | None
    ttft_s: float | None
    last_content_s: float | None
    total_s: float
    prompt_tokens: int | None
    completion_tokens: int | None
    reasoning_tokens: int | None
    content_event_count: int
    text: str
    token_source: str
    # The channel a response that never left the reasoning channel answers in.
    reasoning_text: str = ""


@dataclasses.dataclass(frozen=True)
class FakeCell:
    id: str
    runtime: str
    artifact_dir: str
    label: str


@dataclasses.dataclass
class FakeCellResult:
    cell: FakeCell
    status: str
    reason: str | None
    observations: list
    cold_load_s: float | None
    memory: dict
    runtime_version: str | None
    disk_bytes: int | None
    # Results are per (cell, workload): one row per shape, never an average across them.
    # Defaulted here only so the many single-workload fixtures below stay readable.
    workload_id: str = "chat"
    warmup_observations: list = dataclasses.field(default_factory=list)
    # Wall-clock seconds per measured batch, one entry per batch. Empty for a sequential run:
    # at concurrency=1 a batch is one request and no clock is taken around it.
    batch_spans: list = dataclasses.field(default_factory=list)
    # The cold visit's first warmup latency: the load a lazy loader deferred past readiness.
    first_request_s: float | None = None
    # Which workload made that request, as measure records it on every row of the cell.
    first_request_workload_id: str | None = None
    # The reason a visit that failed left behind, when a later visit measured the cell anyway,
    # and whether the cold load this row carries came from that later start. Defaulted because
    # no lost visit is the ordinary case and the one every other fixture here is.
    lost_visit_reason: str | None = None
    cold_load_after_lost_visit: bool = False
    # The run's batch pin, as `run_cells` stamps it on a fresh result. `load_run` does not
    # rebuild it -- the run header owns it on disk -- so a fixture standing in for a loaded row
    # leaves it None and a test that wants the pin passed a loaded row's header, not this.
    measured_pin: int | None = None


def obs(
    *,
    ok=True,
    ttft=0.5,
    last=2.5,
    total=3.0,
    prompt=250,
    completion=101,
    error=None,
    token_source="usage",
):
    """One measured request. Defaults are a plausible decode of 101 tokens in 2.0 s."""
    return FakeObservation(
        ok=ok,
        error=error,
        ttft_s=ttft,
        last_content_s=last,
        total_s=total,
        prompt_tokens=prompt,
        completion_tokens=completion,
        reasoning_tokens=None,
        content_event_count=completion if completion is not None else 0,
        text="a measured answer that no chart will ever be drawn for",
        token_source=token_source,
    )


def cell_result(
    observations,
    *,
    cell_id="oq4__mlxlm",
    runtime="mlxlm",
    artifact_dir="/models/oq4",
    label="oq4",
    status="PASS",
    reason=None,
    cold_load_s=12.5,
    memory=None,
    runtime_version="mlx-lm 0.31.3",
    disk_bytes=None,
    workload_id="chat",
    first_request_s=None,
    first_request_workload_id=None,
    batch_spans=None,
    lost_visit_reason=None,
    cold_load_after_lost_visit=False,
    measured_pin=None,
):
    """A cell as measure.py will hand it over: one result per (cell, workload)."""
    return FakeCellResult(
        cell=FakeCell(cell_id, runtime, artifact_dir, label),
        status=status,
        reason=reason,
        observations=list(observations),
        cold_load_s=cold_load_s,
        memory={"peak_mb": 9150.0} if memory is None else memory,
        runtime_version=runtime_version,
        disk_bytes=disk_bytes,
        workload_id=workload_id,
        first_request_s=first_request_s,
        first_request_workload_id=first_request_workload_id,
        batch_spans=[] if batch_spans is None else list(batch_spans),
        lost_visit_reason=lost_visit_reason,
        cold_load_after_lost_visit=cold_load_after_lost_visit,
        measured_pin=measured_pin,
    )


@pytest.fixture
def rows():
    """Two cells of one format, so an axis' held-constant variable really is constant."""
    return report.summarize(
        [
            cell_result([obs(ttft=t) for t in (0.40, 0.42, 0.44, 0.46, 0.48)]),
            cell_result(
                [obs(ttft=t, last=t + 4.0) for t in (0.60, 0.62, 0.64, 0.66, 0.68)],
                cell_id="oq4__osaurus",
                runtime="osaurus",
                runtime_version="Osaurus 0.25.3",
            ),
        ]
    )


# --- summarize -----------------------------------------------------------------------------


def test_row_carries_every_field_the_contract_names(rows):
    assert set(rows[0]) >= {
        "ttft_p50_s",
        "ttft_p90_s",
        "ttft_p99_s",
        "itl_s",
        "decode_tps",
        "aggregate_tps",
        "prefill_tps",
        "cold_load_s",
        "peak_mb",
        "disk_bytes",
        "runtime_version",
        "status",
    }


def test_per_request_metrics_follow_the_formulas_verbatim():
    # 101 tokens over (2.5 - 0.5) s, 250 prompt tokens over a 0.5 s prefill,
    # and one inter-token gap of (2.5 - 0.5) / (101 - 1).
    row = report.summarize([cell_result([obs()])])[0]

    assert row["decode_tps"] == pytest.approx(101 / 2.0)
    assert row["prefill_tps"] == pytest.approx(250 / 0.5)
    assert row["itl_s"] == pytest.approx(2.0 / 100)


def test_decode_and_aggregate_throughput_are_two_different_numbers():
    """The lie this project exists to avoid: one throughput number for both questions."""
    observations = [obs(), obs(), obs()]
    row = report.summarize([cell_result(observations)])[0]

    assert row["decode_tps"] == pytest.approx(101 / 2.0)
    assert row["aggregate_tps"] == pytest.approx(3 * 101 / (3 * 3.0))
    assert row["decode_tps"] != row["aggregate_tps"]


def test_aggregate_throughput_counts_every_token_over_every_request():
    row = report.summarize(
        [cell_result([obs(total=3.0, completion=100), obs(total=1.0, completion=50)])]
    )[0]

    assert row["aggregate_tps"] == pytest.approx(150 / 4.0)


def test_aggregate_throughput_divides_by_the_batch_spans_not_the_summed_requests():
    """At concurrency N the per-request clocks overlap, so summing them counts the batch N
    times: two batches of four 2.0 s requests over 2.1 s each is 4.2 s of wall clock, and a
    throughput figure over 16.0 s is the per-request result published as a batch one."""
    concurrent = [obs(total=2.0) for _ in range(8)]
    row = report.summarize([cell_result(concurrent, batch_spans=[2.1, 2.1])])[0]

    assert row["aggregate_tps"] == pytest.approx(8 * 101 / 4.2)
    assert row["aggregate_tps"] != pytest.approx(8 * 101 / 16.0), (
        "the sum of the per-request clocks is what the batch spans exist to replace"
    )


def test_a_record_without_batch_spans_keeps_the_aggregate_it_always_had():
    """Every sequential run, and every record written before batches existed, carries no span
    to divide by: the same eight requests over the same per-request clocks report the number
    they always did."""
    concurrent = [obs(total=2.0) for _ in range(8)]
    without = report.summarize([cell_result(concurrent)])[0]
    spanned = report.summarize([cell_result(concurrent, batch_spans=[2.1, 2.1])])[0]

    # Today's formula, spelled out: every token over the sum of the per-request clocks.
    assert without["aggregate_tps"] == pytest.approx(
        8 * 101 / sum(o.total_s for o in concurrent)
    )
    assert without["aggregate_tps"] != spanned["aggregate_tps"]


def test_decode_tok_per_second_is_a_real_number_for_a_normal_cell(rows):
    """The acceptance criterion: decode tok/s present in 100% of cells."""
    assert all(isinstance(row["decode_tps"], float) and row["decode_tps"] > 0 for row in rows)


def test_percentiles_need_five_samples_and_say_so_below_that():
    two = report.summarize([cell_result([obs(ttft=0.4), obs(ttft=0.6)])])[0]

    assert two["ttft_p50_s"] == pytest.approx(0.5)
    assert two["ttft_p90_s"] is None
    assert two["ttft_p99_s"] is None
    assert "n=2" in two["percentile_note"]


def test_five_samples_produce_real_percentiles_and_no_note():
    row = report.summarize([cell_result([obs(ttft=float(i)) for i in (1, 2, 3, 4, 5)])])[0]

    assert row["ttft_p50_s"] == pytest.approx(3.0)
    assert row["ttft_p90_s"] == pytest.approx(4.6)
    assert row["ttft_p99_s"] == pytest.approx(4.96)
    assert row["percentile_note"] is None


@pytest.mark.parametrize("status", ["FAIL", "N/A"])
def test_non_pass_rows_keep_values_in_summary_but_publish_no_request_figures(status):
    result = cell_result(
        [obs(ttft=0.4, last=1.4) for _ in range(5)],
        status=status,
        reason="diagnostic reason",
        batch_spans=[1.0],
    )
    row, = report.summarize([result])

    assert row["ttft_p50_s"] == pytest.approx(0.4)
    assert row["decode_tps"] == pytest.approx(101.0)
    assert row["aggregate_tps"] is not None
    assert row["drift"] is not None

    printed, = leaderboard_rows(report.render_markdown([row], axis="runtime"))
    for field in (
        "TTFT p50 s", "TTFT p90 s", "TTFT p99 s", "ITL s", "decode tok/s",
        "drift %", "aggregate tok/s", "prefill tok/s",
    ):
        assert printed[field] == "—", field
    assert f"not published: {status} row" in printed["notes"]

    card = card_blocks(report.render_cards([row]))[("chat", "oq4__mlxlm")]
    for field in (
        "ttft_p50_s", "ttft_p90_s", "ttft_p99_s", "itl_s", "decode_tps",
        "aggregate_tps", "prefill_tps",
    ):
        assert f"| {field} | — | not published: {status} row |" in card
    assert f"| drift_pct | — | not published: {status} row |" in card
    assert "| cold_load_s | 12.50 |" in card
    assert "| peak_mb | 9150.0 |" in card
    assert "| runtime_version | mlx-lm 0.31.3 |" in card


def test_a_cell_with_no_observations_reports_nothing_rather_than_zero():
    row = report.summarize([cell_result([], status="FAIL", reason="port 8100 never opened")])[0]

    assert row["status"] == "FAIL"
    assert row["reason"] == "port 8100 never opened"
    assert row["decode_tps"] is None
    assert row["ttft_p50_s"] is None
    assert row["percentile_note"].startswith("n=0")


def test_failed_requests_stay_out_of_the_summary():
    observations = [obs(), obs(), obs(ok=False, ttft=None, last=None, error="HTTP 500")]
    row = report.summarize([cell_result(observations)])[0]

    assert row["n_measured"] == 2
    assert row["n_requests"] == 3
    assert row["decode_tps"] == pytest.approx(101 / 2.0)


def test_a_missing_token_count_yields_none_not_zero():
    row = report.summarize([cell_result([obs(completion=None, token_source="none")])])[0]

    assert row["decode_tps"] is None
    assert row["itl_s"] is None
    assert row["ttft_p50_s"] == pytest.approx(0.5)


def test_a_zero_length_decode_window_does_not_divide_by_zero():
    row = report.summarize([cell_result([obs(ttft=1.0, last=1.0)])])[0]

    assert row["decode_tps"] is None
    assert row["itl_s"] == pytest.approx(0.0)


def test_peak_memory_comes_from_the_sampler_dict():
    row = report.summarize([cell_result([obs()], memory={"peak_mb": 12345.6})])[0]

    assert row["peak_mb"] == pytest.approx(12345.6)


def test_summarize_keeps_the_order_the_cells_arrived_in(rows):
    assert [row["runtime"] for row in rows] == ["mlxlm", "osaurus"]


# --- what came back -------------------------------------------------------------------------

# The transport reports a stream that closed with no content delta as its empty-content
# failure, and stock mlx-lm and vMLX answer entirely in the reasoning channel on a thinking
# model. Those responses are samples. measure owns that definition and report asks for it;
# counting `observation.ok` here instead is how one cell was published as `n = 0/5` beside the
# five samples that had answered.


def reasoning_only():
    """One response with nothing in the content channel: it all arrived as reasoning."""
    return dataclasses.replace(
        obs(
            ok=False,
            error=measure.EMPTY_CONTENT_ERROR,
            ttft=None,
            last=None,
            prompt=None,
            completion=None,
            token_source="none",
        ),
        text="",
        reasoning_text="an answer, spelled in the reasoning channel",
    )


def streamed_ok():
    """One ordinary content-streaming response: a real decode window and a token count."""
    return obs(ttft=0.5, last=1.5)


def test_a_reasoning_only_response_counts_as_a_sample():
    """Every request answered; only the channel it answered in was different."""
    result = cell_result(
        [reasoning_only() for _ in range(5)],
        status="FAIL",
        reason="no content-delta timing, so decode tok/s is undefined",
    )
    row = report.summarize([result])[0]

    assert row["n_measured"] == 5
    assert row["n_requests"] == 5
    assert leaderboard_rows(report.render_markdown([row], axis="runtime"))[0]["n"] == "5"
    assert "| n measured | 5 |" in card_blocks(report.render_cards([row]))[
        ("chat", "oq4__mlxlm")
    ]
    # And the row no longer says nothing was measured while five samples sit beside it.
    assert "nothing was measured" not in report.render_markdown([row], axis="runtime")


def test_a_genuine_transport_failure_is_not_a_sample():
    """The other side of the definition: a request that never reached the model is no sample,
    and the row prints what came back beside what was attempted."""
    timed_out = obs(
        ok=False,
        error="TimeoutError: read timed out",
        ttft=None,
        last=None,
        prompt=None,
        completion=None,
        token_source="none",
    )
    row = report.summarize([cell_result([streamed_ok(), streamed_ok(), timed_out, timed_out])])[0]

    assert row["n_measured"] == 2
    assert row["n_requests"] == 4
    assert leaderboard_rows(report.render_markdown([row], axis="runtime"))[0]["n"] == "2/4"


def test_a_reasoning_only_sample_leaves_every_rate_where_it_was():
    """It carries no content window, so it contributes no rate: the rates stay the rates of
    the requests that streamed."""
    streamed = [streamed_ok() for _ in range(3)]
    mixed = report.summarize([cell_result(streamed + [reasoning_only()] * 2)])[0]
    alone = report.summarize([cell_result(streamed)])[0]

    for metric in ("decode_tps", "itl_s", "prefill_tps", "aggregate_tps", "ttft_p50_s"):
        assert mixed[metric] == pytest.approx(alone[metric])
    assert (mixed["n_measured"], mixed["n_requests"]) == (5, 5)
    assert (alone["n_measured"], alone["n_requests"]) == (3, 3)

    reasoning_only_cell = report.summarize([cell_result([reasoning_only()] * 5)])[0]
    assert reasoning_only_cell["decode_tps"] is None
    assert reasoning_only_cell["itl_s"] is None
    assert reasoning_only_cell["prefill_tps"] is None


def test_an_ordinary_content_streaming_cell_counts_and_publishes_what_it_always_did():
    """Where every response came back ok the two definitions agree, so nothing on this row
    moved: n is every request and every rate is present."""
    observations = [streamed_ok() for _ in range(5)]
    row = report.summarize([cell_result(observations)])[0]

    # The old spelling, side by side: where every request came back ok, it agrees.
    assert row["n_measured"] == sum(o.ok for o in observations) == len(observations) == 5
    assert row["n_requests"] == 5
    assert row["decode_tps"] == pytest.approx(101 / (1.5 - 0.5))
    assert row["itl_s"] == pytest.approx((1.5 - 0.5) / (101 - 1))
    assert row["prefill_tps"] == pytest.approx(250 / 0.5)
    assert row["aggregate_tps"] == pytest.approx(5 * 101 / (5 * 3.0))
    assert row["delta_note"] is None
    assert row["ttft_note"] is None
    assert leaderboard_rows(report.render_markdown([row], axis="runtime"))[0]["n"] == "5"


def test_report_asks_measure_what_came_back_rather_than_respelling_it(monkeypatch):
    """One definition, in one module. A second copy here is how the two drifted apart."""
    asked = []

    def spy(observation):
        asked.append(observation)
        return observation.ok

    monkeypatch.setattr(measure, "came_back", spy)
    observations = [streamed_ok(), reasoning_only()]
    row = report.summarize([cell_result(observations)])[0]

    assert asked == observations, "report counted samples without asking measure"
    assert row["n_measured"] == 1, "report ignored the answer it was given"


# --- a stream too coarse to carry a rate ----------------------------------------------------

# oMLX 0.6.4 accepts "stream": true, returns correct SSE framing, and then delivers the whole
# completion in ONE content delta. Transcribed from results/20260915T151218Z-runtime — the run
# that published 1,532,954,517 tok/s and called the cell PASS. Each tuple is one measured
# request: ttft_s, last_content_s, total_s. The window is last_content_s - ttft_s: not zero,
# just float noise, which is exactly why the rate looked like a rate.
OMLX_RUN = (
    (5.353212750007515, 5.353212916001212, 5.353684625006281),
    (5.182277416999568, 5.1822776250046445, 5.182759209012147),
    (5.498635957992519, 5.498636124990298, 5.499060916990857),
    (5.904398707993096, 5.904398792001302, 5.904995167002198),
    (6.583833500000765, 6.583833666998544, 6.584281499992358),
)


def whole_response(ttft, last, total, *, prompt=34, completion=256):
    """One request whose entire completion arrived in a single content delta."""
    return dataclasses.replace(
        obs(ttft=ttft, last=last, total=total, prompt=prompt, completion=completion),
        content_event_count=1,
    )


def one_delta_cell():
    return cell_result(
        [whole_response(*observation) for observation in OMLX_RUN],
        cell_id="oq4__omlx",
        runtime="omlx",
        runtime_version="oMLX 0.6.4",
    )


def test_a_one_delta_cell_omits_the_rates_its_stream_cannot_support():
    row = report.summarize([one_delta_cell()])[0]
    window = OMLX_RUN[0][1] - OMLX_RUN[0][0]

    assert 0 < window < 1e-6, "the window is float noise, not a decode window"
    assert 256 / window > 1e9, "256 tokens over that noise is the number that got published"
    assert row["decode_tps"] is None
    assert row["itl_s"] is None


def test_a_one_delta_cell_keeps_aggregate_throughput_and_its_ttft_value():
    row = report.summarize([one_delta_cell()])[0]

    # Every completion token over the wall time the measured requests took: 44.9 tok/s, the
    # only rate this stream supports, and it needs no per-delta timing to exist.
    assert row["aggregate_tps"] == pytest.approx(5 * 256 / sum(o[2] for o in OMLX_RUN))
    assert row["aggregate_tps"] == pytest.approx(44.9, abs=0.1)
    # TTFT is labelled, never suppressed: 5.5 s is a real measurement of a real thing.
    assert row["ttft_p50_s"] == pytest.approx(5.498635957992519)
    assert row["status"] == "PASS"


def test_a_one_delta_row_says_why_the_rates_are_gone_and_labels_its_ttft():
    row = report.summarize([one_delta_cell()])[0]

    assert row["delta_note"].startswith("n=0: decode tok/s, ITL and prefill tok/s omitted")
    assert "fewer than 2 content deltas" in row["delta_note"]
    assert "5 of 5 measured requests" in row["delta_note"]
    assert "time-to-completion" in row["ttft_note"]
    assert "not time-to-first-token" in row["ttft_note"]


def test_the_leaderboard_prints_no_rate_for_a_one_delta_cell():
    table = report.render_markdown(report.summarize([one_delta_cell()]), axis="runtime")
    header = next(line for line in table.splitlines() if line.startswith("| cell |"))
    body = next(line for line in table.splitlines() if line.startswith("| oq4__omlx |"))
    columns = [cell.strip() for cell in header.strip("|").split("|")]
    cells = [cell.strip() for cell in body.strip("|").split("|")]

    assert cells[columns.index("decode tok/s")] == "—"
    assert cells[columns.index("ITL s")] == "—"
    assert cells[columns.index("aggregate tok/s")] == "44.9"
    assert cells[columns.index("TTFT p50 s")] == "5.499"
    assert "decode tok/s, ITL and prefill tok/s omitted" in cells[columns.index("notes")]
    assert "time-to-completion" in cells[columns.index("notes")]


def test_a_multi_delta_cell_is_unchanged_by_the_delta_rule():
    """A stream that streamed keeps every number it had, and grows no note."""
    row = report.summarize([cell_result([obs(), obs(), obs()])])[0]

    assert row["decode_tps"] == pytest.approx(101 / 2.0)
    assert row["itl_s"] == pytest.approx(2.0 / 100)
    assert row["aggregate_tps"] == pytest.approx(3 * 101 / (3 * 3.0))
    assert row["prefill_tps"] == pytest.approx(250 / 0.5)
    assert row["ttft_p50_s"] == pytest.approx(0.5)
    assert row["delta_note"] is None
    assert row["ttft_note"] is None


def test_two_content_deltas_are_enough_for_a_rate():
    """The boundary: two deltas is the least a stream can carry an interval in."""
    two = dataclasses.replace(obs(ttft=1.0, last=3.0), content_event_count=2)
    row = report.summarize([cell_result([two])])[0]

    assert row["decode_tps"] == pytest.approx(101 / 2.0)
    assert row["itl_s"] == pytest.approx(2.0 / 100)
    assert row["delta_note"] is None
    assert row["ttft_note"] is None


def test_one_whole_response_among_streamed_ones_is_omitted_and_noted():
    """The rule is per request: the requests that streamed still carry their rate."""
    row = report.summarize([cell_result([obs(), obs(), whole_response(*OMLX_RUN[0])])])[0]

    assert row["decode_tps"] == pytest.approx(101 / 2.0)
    assert row["delta_note"].startswith("n=2: decode tok/s, ITL and prefill tok/s omitted")
    assert "in 1 of 3 measured requests" in row["delta_note"]
    assert "1 of 3 measured requests" in row["ttft_note"]
    assert row["aggregate_tps"] == pytest.approx(
        (2 * 101 + 256) / (3.0 + 3.0 + 5.353684625006281)
    )


# --- the cold visit's first request ---------------------------------------------------------

# The probe the contract was written against (scripts/probe_lazy.py, three requests, no
# warmups): oMLX 0.6.4 reports ~3.1 s ready, then spends 3.08-3.93 s inside request #1 against
# ~0.42 s for the two after it, on three artifacts. mlx-lm, mlx-optiq and vMLX stayed within
# 0.04-0.10 s of their own later requests.
DEFERRED_FIRST_S = 3.93
ORDINARY_S = 0.42


def first_request_cell(first_request_s, *, request_seconds=ORDINARY_S, workload_id="chat",
                       **kwargs):
    """One cell whose cold visit's first request took *first_request_s*.

    The row *is* the workload that made it: request #1 belongs to whichever shape ran first,
    and a cell with a single workload has no other row for it to belong to.
    """
    return cell_result(
        [obs(total=request_seconds) for _ in range(5)],
        workload_id=workload_id,
        first_request_s=first_request_s,
        first_request_workload_id=workload_id,
        **kwargs,
    )


def test_first_request_is_its_own_column_and_the_cold_load_is_not_summed_into_it():
    """The contract compares on the sum; the harness publishes the two halves, not a third."""
    row = report.summarize(
        [cell_result([obs()], cold_load_s=3.12, first_request_s=DEFERRED_FIRST_S)]
    )[0]
    table = report.render_markdown([row], axis="runtime")
    printed = leaderboard_rows(table)[0]

    assert printed["cold load s"] == "3.12"
    assert printed["first request s"] == "3.93"
    assert "7.05" not in table, "the sum is a comparison rule, not a published column"
    # The cold load keeps its own value: nothing was folded into it.
    assert row["cold_load_s"] == pytest.approx(3.12)
    assert row["first_request_s"] == pytest.approx(DEFERRED_FIRST_S)


def test_the_deferred_load_note_fires_above_the_threshold_and_not_below():
    """1 s of excess is the named threshold, and both sides of it are checked."""
    above = report.summarize([first_request_cell(1.5, request_seconds=0.5)])[0]
    below = report.summarize([first_request_cell(1.49, request_seconds=0.5)])[0]

    assert report.DEFERRED_LOAD_EXCESS_S == 1.0
    assert above["first_request_note"] is not None, "exactly at the threshold still fires"
    assert below["first_request_note"] is None


def test_a_deferred_load_is_named_as_one_in_the_row_notes():
    """oMLX's first request is 3.51 s above the requests that followed: a load, not warm-up
    noise."""
    row = report.summarize([first_request_cell(DEFERRED_FIRST_S)])[0]

    assert "deferred past readiness" in row["first_request_note"]
    assert "not warm-up noise" in row["first_request_note"]
    # Both numbers and the excess between them, so the threshold can be checked rather than
    # trusted.
    assert "3.93 s" in row["first_request_note"]
    assert "0.42 s" in row["first_request_note"]
    assert "+3.51 s over it" in row["first_request_note"]

    printed = leaderboard_rows(report.render_markdown([row], axis="runtime"))[0]
    assert "deferred past readiness" in printed["notes"]
    card = card_blocks(report.render_cards([row]))[("chat", "oq4__mlxlm")]
    assert "deferred past readiness" in card


# The defect: a visit runs chat, then prefill, then decode, and request #1 belongs to whichever
# ran first. Every row of the cell carries the visit's first request -- that column is the
# visit's fact -- but only the shape that made it measured that latency.
VISIT_SECONDS = {"chat": 1.00, "prefill": 0.95, "decode": 1.15}


def visit_rows(first_request_s, *, made_by="chat", seconds=None):
    """One cell's three workload rows, its cold visit's first request owned by *made_by*.

    `chat` runs first, so the visit's number sits 2.93 s above chat's own median measured
    request and 2.98 s above prefill's: the same latency reads as a deferral against either
    one, and only one of them paid it.
    """
    seconds = VISIT_SECONDS if seconds is None else seconds
    return report.summarize(
        [
            cell_result(
                [obs(total=seconds[workload_id]) for _ in range(5)],
                workload_id=workload_id,
                first_request_s=first_request_s,
                first_request_workload_id=made_by,
            )
            for workload_id in ("chat", "prefill", "decode")
        ]
    )


def test_the_workload_that_made_the_first_request_earns_the_note():
    rows = visit_rows(DEFERRED_FIRST_S)
    chat = next(row for row in rows if row["workload_id"] == "chat")

    assert chat["first_request_note"] is not None
    assert "3.93 s" in chat["first_request_note"]
    assert "1.00 s" in chat["first_request_note"]
    assert "+2.93 s over it" in chat["first_request_note"]

    printed = {row["workload"]: row for row in leaderboard_rows(report.render_markdown(rows, axis="runtime"))}
    assert "deferred past readiness" in printed["chat"]["notes"]


def test_a_sibling_workload_claims_nothing_from_the_visits_first_request():
    """prefill measured 0.95 s requests and did not make the visit's first request, so the
    visit's 3.93 s is not a deferral in prefill's column: it is another workload's population,
    and the harness has no reading that crosses the two."""
    rows = visit_rows(DEFERRED_FIRST_S)
    by_workload = {row["workload_id"]: row for row in rows}

    for workload_id in ("prefill", "decode"):
        assert by_workload[workload_id]["first_request_s"] == pytest.approx(DEFERRED_FIRST_S), (
            "the column is the visit's fact and every row of the cell keeps it"
        )
        assert by_workload[workload_id]["first_request_note"] is None

    printed = leaderboard_rows(report.render_markdown(rows, axis="runtime"))
    assert {row["first request s"] for row in printed} == {"3.93"}
    for row in printed:
        if row["workload"] == "chat":
            continue
        assert "deferred" not in row["notes"], "a row that did not pay the load claimed it"


def test_a_visit_that_recorded_no_first_request_leaves_every_row_silent():
    """A cold visit that made no warmup and a visit that was not the cold one record nothing,
    and their rows claim nothing however short their own requests are."""
    rows = visit_rows(None, made_by=None, seconds={"chat": 0.05, "prefill": 0.05, "decode": 0.05})

    assert [row["first_request_s"] for row in rows] == [None] * 3
    assert [row["first_request_note"] for row in rows] == [None] * 3

    printed = leaderboard_rows(report.render_markdown(rows, axis="runtime"))
    assert {row["first request s"] for row in printed} == {"—"}
    assert all("deferred" not in row["notes"] for row in printed)


# The four columns of the runtime-axis grid: cold_load_s, first_request_s and the median
# measured request. oMLX charges a whole load to request #1; the other three are warm-up.
GRID_COLUMNS = (
    ("mlxlm", "mlx-lm 0.31.3", 3.84, 1.61, 1.8),
    ("omlx", "oMLX 0.6.4", 2.16, 5.23, 1.6),
    ("optiq", "mlx-optiq 0.5.6", 4.11, 2.06, 1.85),
    ("vmlx", "vMLX 1.6.59", 7.10, 1.81, 1.9),
)


def grid_column(runtime, runtime_version, cold_load_s, first_request_s, median_s):
    """One grid column as a row: its cold visit, and the requests measured after it."""
    return report.summarize(
        [
            first_request_cell(
                first_request_s,
                request_seconds=median_s,
                cell_id=f"oq4__{runtime}",
                runtime=runtime,
                runtime_version=runtime_version,
                cold_load_s=cold_load_s,
            )
        ]
    )[0]


def test_the_deferred_load_note_fires_on_the_omlx_column_and_not_the_other_three():
    """The case the ratio missed: 5.23 s against 1.6 s is only 3.3x — under the 5x the deleted
    factor required — and 3.63 s of excess, which is a load however long the requests got."""
    rows = {column[0]: grid_column(*column) for column in GRID_COLUMNS}

    assert rows["omlx"]["first_request_note"] is not None, "the deferred load went unremarked"
    assert "+3.63 s over it" in rows["omlx"]["first_request_note"]
    for runtime in ("mlxlm", "optiq", "vmlx"):
        assert rows[runtime]["first_request_note"] is None, (
            f"{runtime}'s first request is warm-up-shaped, not a deferred load"
        )


def test_a_first_request_in_line_with_the_measured_ones_gets_no_note():
    """vMLX: 0.51 s first against 0.43 s after. An ordinary request, and a row that said
    otherwise on every runtime would be crying wolf."""
    row = report.summarize([first_request_cell(0.51, request_seconds=0.43)])[0]

    assert row["first_request_s"] == pytest.approx(0.51)
    assert row["first_request_note"] is None


def test_a_cell_with_no_first_request_on_the_record_carries_none_and_claims_nothing():
    row = report.summarize([cell_result([obs()], first_request_s=None)])[0]

    assert row["first_request_s"] is None
    assert row["first_request_note"] is None
    printed = leaderboard_rows(report.render_markdown([row], axis="runtime"))[0]
    assert printed["first request s"] == "—"


# --- drift across the measurement window ----------------------------------------------------

# ``measure.measured_drift`` splits the measured samples in half in the order they were taken
# and compares the medians, so five requests put two rates in each half and discard the middle
# one. On the 2026-09-15 grid the per-column median change was +17.0% (mlx-lm), +2.6% (oMLX),
# -0.0% (mlx-optiq) and +0.5% (vMLX): the mlx-lm column was still climbing while the other three
# had settled, and a row that cannot show that difference renders the two identically. In the
# mlx-lm column the runtime is held constant and drift still ranges -1.3% to +28.4% between
# formats, so it lands on the rows instead of cancelling as a common-mode offset.


def drift_cell(windows, **kwargs):
    """One cell whose measured requests decode over *windows*, in the order they were taken.

    101 completion tokens over a 1.0 s window is 101 tok/s, so a 0.5 s window is 202.
    """
    return cell_result([obs(ttft=0.5, last=0.5 + window) for window in windows], **kwargs)


# An early half at 101.0 tok/s and a late half at 202.0: +100%, the mlx-lm column's shape.
CLIMBING = (1.0, 1.0, 1.0, 0.5, 0.5)
# The same rate in both halves: nothing to say about it.
FLAT = (1.0,) * 5


def test_a_cell_still_climbing_across_its_window_is_annotated_and_still_ranks():
    """The mlx-lm column: 12 of 12 rows over 5%, up to +28.4%. The row says so — and it is
    still a result, because the annotation is a note and never a floor."""
    row = report.summarize([drift_cell(CLIMBING)])[0]

    assert row["status"] == "PASS"
    assert row["rankable"] is True
    assert row["excluded_by"] is None
    assert row["decode_tps"] == 101.0
    assert row["drift"]["change_pct"] == pytest.approx(100.0)
    # The medians it compared and the count it compared them over, so the call can be checked
    # rather than taken.
    assert "drift +100.0%" in row["drift_note"]
    assert "early median 101.0 tok/s" in row["drift_note"]
    assert "202.0 tok/s" in row["drift_note"]
    assert "n=5" in row["drift_note"]
    # Direction, and no more than direction: a median of two rates against a median of two.
    assert "still warming up" in row["drift_note"]
    assert "insufficient warmup" in row["drift_note"]
    assert "fixes the direction, not the magnitude" in row["drift_note"]

    printed = leaderboard_rows(report.render_markdown([row], axis="runtime"))[0]
    assert printed["drift %"] == "+100.0"
    assert "still warming up" in printed["notes"]


def test_a_cell_that_held_still_across_its_window_is_not_annotated():
    """A note printed on every row separates none of them: 0.0% is not a finding."""
    row = report.summarize([drift_cell(FLAT)])[0]

    assert row["drift"]["change_pct"] == pytest.approx(0.0)
    assert row["drift_note"] is None

    printed = leaderboard_rows(report.render_markdown([row], axis="runtime"))[0]
    assert printed["drift %"] == "+0.0"
    assert "drift" not in printed["notes"]


def test_a_cell_that_slowed_across_its_window_is_annotated_as_a_thermal_one():
    """The other sign, which no row of the grid produced: slower late than early is the thermal
    curve the interleave exists to expose, and the row says that rather than 'warming up'."""
    row = report.summarize([drift_cell((0.5, 0.5, 0.5, 1.0, 1.0))])[0]

    assert row["drift"]["change_pct"] == pytest.approx(-50.0)
    assert "drift -50.0%" in row["drift_note"]
    assert "slowing down" in row["drift_note"]
    assert "thermal curve" in row["drift_note"]
    assert "warming up" not in row["drift_note"]


# The 2026-09-15 grid's per-column medians, as rows: the threshold has exactly that split to
# make, between the column that was still climbing and the three that had settled.
GRID_DRIFT_PCT = (
    ("mlxlm", "mlx-lm 0.31.3", 17.0),
    ("omlx", "oMLX 0.6.4", 2.6),
    ("optiq", "mlx-optiq 0.5.6", -0.0),
    ("vmlx", "vMLX 1.6.59", 0.5),
)


def grid_drift_row(change_pct, *, runtime, runtime_version):
    """One grid column as a row whose window moved by *change_pct*, the median it measured."""
    late = 1.0 / (1.0 + change_pct / 100.0)
    return report.summarize(
        [
            drift_cell(
                (1.0, 1.0, 1.0, late, late),
                cell_id=f"oq4__{runtime}",
                runtime=runtime,
                runtime_version=runtime_version,
            )
        ]
    )[0]


def test_the_drift_annotation_fires_on_the_mlx_lm_column_and_not_the_settled_three():
    rows = {
        runtime: grid_drift_row(pct, runtime=runtime, runtime_version=version)
        for runtime, version, pct in GRID_DRIFT_PCT
    }

    assert rows["mlxlm"]["drift_note"] is not None, "the column that was still climbing went unremarked"
    assert "drift +17.0%" in rows["mlxlm"]["drift_note"]
    for runtime in ("omlx", "optiq", "vmlx"):
        assert rows[runtime]["drift_note"] is None, (
            f"{runtime}'s column settled inside the threshold and has nothing to report"
        )


def test_the_drift_annotation_fires_above_the_threshold_and_not_below():
    """5% is the named threshold, and both sides of it are checked: +5.3% is annotated."""
    above = report.summarize([drift_cell((1.0, 1.0, 1.0, 0.95, 0.95))])[0]
    below = report.summarize([drift_cell((1.0, 1.0, 1.0, 0.96, 0.96))])[0]

    assert report.DRIFT_ANNOTATION_PCT == 5.0
    assert above["drift"]["change_pct"] == pytest.approx(5.26, abs=0.01)
    assert above["drift_note"] is not None
    assert below["drift"]["change_pct"] == pytest.approx(4.17, abs=0.01)
    assert below["drift_note"] is None


def test_a_row_with_no_drift_to_report_renders_without_raising():
    """Fewer than two rates to compare: one sample, or samples whose requests carry no rate."""
    thin = report.summarize([cell_result([obs()])])[0]
    rateless = report.summarize(
        [cell_result([obs(completion=None, token_source="none")] * 5)]
    )[0]

    for row in (thin, rateless):
        assert row["drift"] is None
        assert "no drift figure" in row["drift_note"]

        printed = leaderboard_rows(report.render_markdown([row], axis="runtime"))[0]
        assert printed["drift %"] == "—"
        assert "no drift figure" in printed["notes"]

        card = card_blocks(report.render_cards([row]))[("chat", "oq4__mlxlm")]
        assert "| drift_pct | — | no drift figure" in card


def test_a_drift_dict_without_a_percentage_renders_without_raising(monkeypatch):
    """measure reports ``change_pct`` as None rather than dividing by an early median of zero,
    and the row prints a dash and says why, the way it does for every other empty value."""
    monkeypatch.setattr(
        measure,
        "measured_drift",
        lambda observations: {
            "early_median_tps": 0.0,
            "late_median_tps": 101.0,
            "change_pct": None,
            "n": 5,
        },
    )
    row = report.summarize([cell_result([obs() for _ in range(5)])])[0]

    assert row["drift"]["change_pct"] is None
    assert "no drift figure" in row["drift_note"]

    printed = leaderboard_rows(report.render_markdown([row], axis="runtime"))[0]
    assert printed["drift %"] == "—"
    assert "no drift figure" in printed["notes"]


def test_a_cell_that_never_ran_is_not_told_drift_is_why_its_row_is_empty():
    """n=0 already says nothing was measured, and that is the reason. Drift is not."""
    row = report.summarize(
        [cell_result([], status="N/A", reason="port 8100 never opened")]
    )[0]

    assert row["drift"] is None
    assert row["drift_note"] is None

    printed = leaderboard_rows(report.render_markdown([row], axis="runtime"))[0]
    assert printed["drift %"] == "—"
    assert "drift" not in printed["notes"]


def test_two_cells_at_the_same_rate_render_differently_when_one_is_still_climbing():
    """The defect itself: same decode rate, same everything but the note, and a reader
    comparing them has to be able to see that one of the two was still moving."""
    rows = report.summarize(
        [
            drift_cell(CLIMBING, cell_id="oq4__mlxlm", runtime="mlxlm"),
            drift_cell(
                FLAT,
                cell_id="oq4__osaurus",
                runtime="osaurus",
                runtime_version="Osaurus 0.25.3",
            ),
        ]
    )
    printed = {
        row["cell"]: row for row in leaderboard_rows(report.render_markdown(rows, axis="runtime"))
    }

    assert printed["oq4__mlxlm"]["decode tok/s"] == "101.0"
    assert printed["oq4__osaurus"]["decode tok/s"] == "101.0"
    assert printed["oq4__mlxlm"]["drift %"] == "+100.0"
    assert printed["oq4__osaurus"]["drift %"] == "+0.0"
    assert "still warming up" in printed["oq4__mlxlm"]["notes"]
    assert "drift" not in printed["oq4__osaurus"]["notes"]


def test_the_card_prints_the_drift_line_beside_the_decode_rate_it_qualifies():
    card = card_blocks(report.render_cards(report.summarize([drift_cell(CLIMBING)])))[
        ("chat", "oq4__mlxlm")
    ]
    lines = card.splitlines()
    decode = next(index for index, line in enumerate(lines) if line.startswith("| decode_tps |"))
    drift = next(index for index, line in enumerate(lines) if line.startswith("| drift_pct |"))

    assert drift == decode + 1, "the drift line belongs beside the decode rate it qualifies"
    assert "| drift_pct | +100.0 |" in lines[drift]
    assert "still warming up" in lines[drift]


def test_report_asks_measure_for_the_drift_rather_than_recomputing_it(monkeypatch):
    """One definition, in one module — the rule ``came_back`` is held to, and what makes this
    row's percentage the one ``results.jsonl`` recorded for it."""
    asked = []

    def spy(observations):
        asked.append(observations)
        return {"early_median_tps": 101.0, "late_median_tps": 202.0, "change_pct": 100.0, "n": 5}

    monkeypatch.setattr(measure, "measured_drift", spy)
    observations = [obs() for _ in range(5)]
    row = report.summarize([cell_result(observations)])[0]

    assert asked == [observations], "report computed the drift instead of asking measure"
    assert row["drift"]["late_median_tps"] == 202.0


def test_surfacing_drift_moves_no_published_figure():
    """The order's own acceptance: a column was added and no other number changed. Read back
    off the printed row, so the assertion is on the bytes a reader sees."""
    # All three decode 101 tokens over the same 1.0 s window, so the figures they publish are
    # the same figures: a single sample has no p90, which is the percentile rule and not drift.
    cases = (
        ("climbing", drift_cell(CLIMBING), "0.500"),
        ("flat", drift_cell(FLAT), "0.500"),
        ("no drift to report", drift_cell((1.0,)), "—"),
    )

    for name, result, p90 in cases:
        row = report.summarize([result])[0]
        printed = leaderboard_rows(report.render_markdown([row], axis="runtime"))[0]

        assert row["decode_tps"] == 101.0, name
        assert row["itl_s"] == pytest.approx(0.01), name
        for column, expected in (
            ("decode tok/s", "101.0"),
            ("ITL s", "0.0100"),
            ("aggregate tok/s", "33.7"),
            ("prefill tok/s", "500.0"),
            ("TTFT p50 s", "0.500"),
            ("TTFT p90 s", p90),
            ("peak MB", "9150.0"),
        ):
            assert printed[column] == expected, f"{name}: {column} moved"


def test_the_drift_column_is_the_only_column_added():
    """Every other column is exactly where it was, and the new one sits beside the decode rate."""
    row = report.summarize([drift_cell(CLIMBING)])[0]
    header = next(
        line
        for line in report.render_markdown([row], axis="runtime").splitlines()
        if line.startswith("| cell |")
    )

    assert header == (
        "| cell | runtime | format | workload | rank by decode_tps | status | n "
        "| TTFT p50 s | TTFT p90 s | TTFT p99 s | ITL s | decode tok/s | drift % "
        "| aggregate tok/s | prefill tok/s | cold load s | first request s | peak MB "
        "| disk bytes | runtime version | notes |"
    )


# --- a lost visit, and a short measured window -----------------------------------------------

# `measured` counts batches, and a run pins nine. The prompt sweep's Osaurus 128 landed four of
# them -- visit 1's `runtime.start()` raised and visit 2 measured its quota -- and the row was
# published PASS with nothing saying either thing. Both are notes, not floors and not statuses:
# the row was measured, it cleared every floor with what it landed, and it is ranked with the
# rest, because dropping it would delete the one row that says the window was short.

LOST_REASON = (
    "runtime 'osaurus' did not start: RuntimeStartError: port still held by a stale server"
)


def short_window_row(*, pin=9, batches=4):
    """One row measured short of its pin: *batches* healthy requests against a pinned nine."""
    return report.summarize([cell_result([obs() for _ in range(batches)])], measured=pin)[0]


def test_a_short_measured_window_is_a_note_and_never_a_floor():
    row = short_window_row()

    assert row["status"] == "PASS"
    assert row["rankable"] is True
    assert row["excluded_by"] is None
    assert row["measured_batches"] == 4
    assert row["measured_pin"] == 9
    assert row["short_note"] == (
        "short measured window: 4 of 9 pinned batches landed; the median is over the 4 that did"
    )
    # The median it names is the row's own: four requests of 101 tokens over a 2.0 s window.
    assert row["decode_tps"] == pytest.approx(101 / 2.0)

    printed = leaderboard_rows(report.render_markdown([row], axis="runtime"))[0]
    assert printed["decode tok/s"] == "50.5"
    assert printed["rank by decode_tps"] == "1", "annotated, and still in the ordering"
    assert "short measured window: 4 of 9 pinned batches landed" in printed["notes"]

    card = card_blocks(report.render_cards([row]))[("chat", "oq4__mlxlm")]
    assert "short measured window: 4 of 9 pinned batches landed" in card


def test_a_full_measured_window_carries_no_short_note():
    """A note on every row would separate none of them: nine of nine is not a finding."""
    row = report.summarize([cell_result([obs() for _ in range(5)])], measured=5)[0]

    assert row["measured_batches"] == 5
    assert row["short_note"] is None

    printed = leaderboard_rows(report.render_markdown([row], axis="runtime"))[0]
    assert "short measured window" not in printed["notes"]


def test_a_pin_nobody_passed_is_no_check_rather_than_a_pin_of_zero():
    """An older caller, or a run whose header predates the field: absent is absent, and a row is
    never reported short against a pin nobody stated."""
    row = report.summarize([cell_result([obs() for _ in range(4)])])[0]

    assert row["measured_pin"] is None
    assert row["short_note"] is None


def test_a_cell_that_never_measured_is_not_told_its_window_was_short():
    """n=0 already says nothing was measured and the row carries the reason it was not: a note
    about a window that never opened would bury the reason that is."""
    row = report.summarize(
        [cell_result([], status="N/A", reason="port 8100 never opened")], measured=9
    )[0]

    assert row["status"] == "N/A"
    assert row["measured_batches"] == 0
    assert row["short_note"] is None


def test_the_count_is_batches_so_a_concurrent_row_is_read_against_the_pin_it_was_given():
    """`measured` counts batches, and above concurrency 1 the requests outnumber them: four
    batches of eight are 32 samples against a pinned nine, and the window is still short. The
    count is read off the spans, which are the batches that ran."""
    observations = [obs() for _ in range(8 * 4)]
    row = report.summarize(
        [cell_result(observations, batch_spans=[2.1, 2.1, 2.1, 2.1])], measured=9
    )[0]

    assert row["n_measured"] == 32
    assert row["measured_batches"] == 4
    assert row["short_note"] == (
        "short measured window: 4 of 9 pinned batches landed; the median is over the 4 that did"
    )


def test_a_lost_visit_and_the_later_start_it_left_behind_are_both_visible():
    """The row the sweep published: PASS over four of nine batches, with the failure that
    explains both gone from the record. The reason is the row's note again, and the cold load
    the later start recorded says which start it was."""
    row = report.summarize(
        [
            cell_result(
                [obs() for _ in range(4)],
                lost_visit_reason=LOST_REASON,
                cold_load_after_lost_visit=True,
            )
        ],
        measured=9,
    )[0]

    assert row["status"] == "PASS"
    assert "a visit to this cell was lost before the one that measured" in row["lost_visit_note"]
    assert LOST_REASON in row["lost_visit_note"]
    assert "later start" in row["cold_load_note"]
    assert "not the cell's cold start" in row["cold_load_note"]

    printed = leaderboard_rows(report.render_markdown([row], axis="runtime"))[0]
    assert "a visit to this cell was lost" in printed["notes"]
    assert "port still held by a stale server" in printed["notes"]
    assert "cold load s and first request s are from a later start" in printed["notes"]
    assert "short measured window: 4 of 9" in printed["notes"]

    card = card_blocks(report.render_cards([row]))[("chat", "oq4__mlxlm")]
    assert "| status | PASS | a visit to this cell was lost before the one that measured" in card
    assert "| n measured | 4 | short measured window: 4 of 9 pinned batches landed" in card
    assert "| cold_load_s | 12.50 | cold load s and first request s are from a later start" in card


def test_a_row_with_no_lost_visit_carries_neither_note():
    row = report.summarize([cell_result([obs() for _ in range(5)])], measured=5)[0]

    assert row["lost_visit_note"] is None
    assert row["cold_load_note"] is None

    printed = leaderboard_rows(report.render_markdown([row], axis="runtime"))[0]
    assert "lost" not in printed["notes"]
    assert "cold load s and first request s" not in printed["notes"]

    card = card_blocks(report.render_cards([row]))[("chat", "oq4__mlxlm")]
    assert "was lost" not in card
    assert "later start" not in card


# --- disk size -----------------------------------------------------------------------------


def test_disk_bytes_prefers_what_measure_recorded(tmp_path):
    measured = cell_result([obs()], artifact_dir=str(tmp_path), status="PASS")
    measured.disk_bytes = 7_000_000_000

    assert report.summarize([measured])[0]["disk_bytes"] == 7_000_000_000


# --- leaderboard ---------------------------------------------------------------------------


def test_render_markdown_requires_its_axis(rows):
    with pytest.raises(TypeError):
        report.render_markdown(rows)


def test_render_markdown_refuses_an_axis_it_does_not_know(rows):
    with pytest.raises(ValueError):
        report.render_markdown(rows, axis="whatever")


def test_runtime_axis_table_states_the_held_constant_and_its_caveat(rows):
    table = report.render_markdown(rows, axis="runtime")

    assert "format held constant; this compares serving, not quantization" in table
    assert "runtime held constant" not in table
    assert "Held constant: format `oq4`" in table
    assert "| oq4__mlxlm | mlxlm |" in table
    assert "| oq4__osaurus | osaurus |" in table


def test_format_axis_table_states_the_other_held_constant_and_caveat(rows):
    shared = [
        cell_result([obs()], cell_id="oq4__omlx", runtime="omlx", label="oq4"),
        cell_result([obs()], cell_id="jang4__omlx", runtime="omlx", label="jang4"),
    ]
    table = report.render_markdown(report.summarize(shared), axis="format")

    assert "runtime held constant; this compares quantization, not serving" in table
    assert "Held constant: runtime `omlx`" in table


def test_format_axis_names_the_build_the_runtime_was_held_constant_at():
    shared = [
        cell_result([obs()], cell_id="oq4__osaurus", runtime="osaurus", label="oq4",
                    runtime_version="0.25.4"),
        cell_result([obs()], cell_id="jang4__osaurus", runtime="osaurus", label="jang4",
                    runtime_version="0.25.4"),
    ]
    table = report.render_markdown(report.summarize(shared), axis="format")

    assert "Held constant: runtime `osaurus` at version `0.25.4`" in table


def test_format_axis_refuses_a_runtime_that_changed_version_mid_join():
    """Osaurus updated 0.25.3 -> 0.25.4 mid-session; the harness never said so. Now it does."""
    spanning = report.summarize(
        [
            cell_result([obs()], cell_id="oq4__osaurus", runtime="osaurus", label="oq4",
                        runtime_version="0.25.3"),
            cell_result([obs()], cell_id="jang4__osaurus", runtime="osaurus", label="jang4",
                        runtime_version="0.25.4"),
        ]
    )

    with pytest.raises(ValueError) as raised:
        report.render_markdown(spanning, axis="format")

    assert "osaurus 0.25.3" in str(raised.value) and "osaurus 0.25.4" in str(raised.value)


def test_a_cell_that_never_started_a_runtime_does_not_count_as_a_second_build():
    """No version means no runtime ran, and a cell that never ran cannot disagree."""
    with_a_dead_cell = report.summarize(
        [
            cell_result([obs()], cell_id="oq4__osaurus", runtime="osaurus", label="oq4",
                        runtime_version="0.25.4"),
            cell_result([], cell_id="jang4__osaurus", runtime="osaurus", label="jang4",
                        runtime_version=None, status="FAIL", reason="did not start"),
        ]
    )

    table = report.render_markdown(with_a_dead_cell, axis="format")

    assert "Held constant: runtime `osaurus` at version `0.25.4`" in table


def test_render_markdown_refuses_rows_that_vary_both_variables():
    """Two things changed, so the table would be a press release. Do not render it."""
    mixed = report.summarize(
        [
            cell_result([obs()], label="oq4", runtime="mlxlm"),
            cell_result([obs()], label="jang4", runtime="osaurus"),
        ]
    )

    with pytest.raises(ValueError):
        report.render_markdown(mixed, axis="runtime")


def test_render_markdown_reports_omitted_percentiles_in_the_row():
    table = report.render_markdown(
        report.summarize([cell_result([obs(), obs()])]), axis="runtime"
    )

    assert "n=2: p90/p99 omitted" in table


def test_render_markdown_keeps_the_two_throughputs_in_separate_columns(rows):
    table = report.render_markdown(rows, axis="runtime")
    header = next(line for line in table.splitlines() if line.startswith("| cell |"))
    body = next(line for line in table.splitlines() if line.startswith("| oq4__mlxlm |"))

    # Separate columns, and the drift percentage sits between them because it qualifies the
    # decode rate; the ordering is not a blend of the two.
    assert "| decode tok/s | drift % | aggregate tok/s |" in header
    assert rows[0]["decode_tps"] != rows[0]["aggregate_tps"]
    assert f"{rows[0]['decode_tps']:.1f}" in body
    assert f"{rows[0]['aggregate_tps']:.1f}" in body


def test_render_markdown_draws_no_charts(rows):
    table = report.render_markdown(rows, axis="runtime").lower()

    assert "```" not in table
    assert "mermaid" not in table
    assert "<svg" not in table
    assert "chart" not in table


# --- the CLI -------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class FakeWorkload:
    """``measure.Workload``'s shape, no behaviour: the CLI only constructs and forwards it."""

    id: str
    messages: list
    max_tokens: int


class FakeMeasure:
    """Stands in for ohyesmlx.measure, and persists the way its ``run_cells`` does.

    A header line, then one line per cell. The CLI relies on run_cells for
    ``results.jsonl`` rather than writing it itself, so a fake that wrote nothing would
    let the CLI's test pass over a run directory with no results in it.
    """

    Cell = FakeCell
    # cli.workloads() builds its three shapes against whichever measure module the run uses,
    # so a stand-in has to offer the same constructor or the CLI cannot build a run at all.
    Workload = FakeWorkload

    def __init__(self, results):
        self.results = results
        self.calls = []

    def run_cells(self, cells, workloads, **kwargs):
        self.calls.append({"cells": cells, "workloads": workloads, **kwargs})
        # The header names every workload the run pinned, the way the real one does: a cell
        # line says which shape produced it, and the header is where that id is defined.
        records = [
            {
                "temperature": 0.0,
                "seed": 0,
                "workloads": [dataclasses.asdict(workload) for workload in workloads],
            }
        ]
        records += [dataclasses.asdict(result) for result in self.results]
        path = Path(kwargs["results_dir"]) / "results.jsonl"
        path.write_text(
            "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
        )
        return self.results


@pytest.fixture
def fake_measure(monkeypatch):
    measure = FakeMeasure(
        [
            cell_result([obs(ttft=t) for t in (0.4, 0.5, 0.6, 0.7, 0.8)], disk_bytes=1_000_000),
            cell_result(
                [obs(ttft=t) for t in (0.9, 1.0, 1.1, 1.2, 1.3)],
                cell_id="oq4__osaurus",
                runtime="osaurus",
                runtime_version="Osaurus 0.25.3",
                disk_bytes=1_000_000,
            ),
        ]
    )
    monkeypatch.setattr(cli, "_load_measure", lambda: measure)
    return measure


def test_run_writes_one_jsonl_and_one_leaderboard_into_the_run_directory(
    fake_measure, tmp_path, capsys
):
    code = cli.main(
        [
            "run",
            "--study",
            "runtime",
            "--cells",
            "oq4__mlxlm=/models/oq4,oq4__osaurus=/models/oq4",
            "--results-dir",
            str(tmp_path / "results"),
        ]
    )

    assert code == 0
    run_dirs = list((tmp_path / "results").iterdir())
    assert len(run_dirs) == 1
    assert run_dirs[0].name.endswith("-runtime")

    jsonl = run_dirs[0] / "results.jsonl"
    leaderboard = run_dirs[0] / "leaderboard.md"
    # The run header, then one line per cell.
    assert len(jsonl.read_text().splitlines()) == 3
    assert "not quantization" in leaderboard.read_text()
    assert "format held constant; this compares serving" in leaderboard.read_text()

    assert len(fake_measure.calls) == 1
    call = fake_measure.calls[0]
    assert [c.id for c in call["cells"]] == ["oq4__mlxlm", "oq4__osaurus"]
    assert call["results_dir"] == str(run_dirs[0])
    # All three shapes reach run_cells in one call, each carrying its own cap: the CLI hands
    # over the whole set so one runtime load can serve them, not one run per shape.
    assert [w.id for w in call["workloads"]] == ["chat", "prefill", "decode"]
    assert [w.max_tokens for w in call["workloads"]] == [128, 64, 512]
    assert all(w.messages for w in call["workloads"])
    assert "leaderboard.md" in capsys.readouterr().out


def test_cells_entries_become_cells():
    cells = cli.build_cells(FakeCell, "oq4__mlxlm=/models/oq4, jang4__omlx=~/models/jang4")

    assert [c.id for c in cells] == ["oq4__mlxlm", "jang4__omlx"]
    assert [c.runtime for c in cells] == ["mlxlm", "omlx"]
    assert [c.label for c in cells] == ["oq4", "jang4"]
    assert cells[0].artifact_dir == "/models/oq4"
    assert not cells[1].artifact_dir.startswith("~")


@pytest.mark.parametrize(
    "spec", ["", "oq4__mlxlm", "oq4=/models/oq4", "__mlxlm=/m", "oq4__=/m", "oq4__mlxlm="]
)
def test_malformed_cells_entries_are_refused(spec):
    with pytest.raises(ValueError):
        cli.build_cells(FakeCell, spec)


def test_study_runtime_refuses_a_selection_that_varies_the_format(tmp_path, capsys):
    code = cli.main(
        [
            "run",
            "--study",
            "runtime",
            "--cells",
            "oq4__mlxlm=/models/oq4,jang4__mlxlm=/models/jang4",
            "--results-dir",
            str(tmp_path),
        ]
    )

    assert code == 2
    assert "holds the quantization format constant" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_study_format_refuses_a_selection_that_varies_the_runtime(tmp_path, capsys):
    code = cli.main(
        [
            "run",
            "--study",
            "format",
            "--cells",
            "oq4__mlxlm=/models/oq4,oq4__osaurus=/models/oq4",
            "--results-dir",
            str(tmp_path),
        ]
    )

    assert code == 2
    assert "holds the serving runtime constant" in capsys.readouterr().err


def test_study_and_cells_are_required_and_study_has_two_values():
    with pytest.raises(SystemExit):
        cli.main(["run", "--cells", "oq4__mlxlm=/m"])
    with pytest.raises(SystemExit):
        cli.main(["run", "--study", "runtime"])
    with pytest.raises(SystemExit):
        cli.main(["run", "--study", "vibes", "--cells", "oq4__mlxlm=/m"])


def test_cells_is_the_only_cell_selector_the_cli_has():
    """LMRE built six overlapping mechanisms for this. This one gets one."""
    subcommands = cli._parser()._subparsers._group_actions[0]
    flags = {
        option
        for action in subcommands.choices["run"]._actions
        for option in action.option_strings
    }

    assert flags == {
        "-h", "--help", "--study", "--cells", "--results-dir", "--rank", "--concurrency",
        "--prompt-tokens", "--cache-state",
    }
    # --concurrency is a PIN, not a selector: it says how the named cells are driven, never
    # which cells run. That distinction is the whole reason concurrency is not a third
    # --study axis -- if it selected cells, one --cells could vary three things at once.
    selectors = {flag for flag in flags if flag in {"--cells"}}
    assert selectors == {"--cells"}
    # `run` says which cells to measure with --cells and nothing else. `grid` and `sweep` are
    # not a second way to say that: both join run directories that already exist, start no
    # runtime and measure nothing -- and `sweep`'s `--varying` names a header pin, never a cell
    # -- so the selector count for a *run* is still one.
    assert set(subcommands.choices) == {"run", "grid", "sweep"}


def test_modules_stay_on_the_standard_library():
    allowed = set(sys.stdlib_module_names) | {"ohyesmlx"}
    for module in (report, cli):
        tree = ast.parse(Path(module.__file__).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported = [node.module.split(".")[0]]
            else:
                continue
            assert set(imported) <= allowed, f"{module.__name__} imports {imported}"


# --- reading a rendered leaderboard back ---------------------------------------------------


def leaderboard_rows(markdown):
    """The leaderboard tables' body rows, in printed order, as ``{column: value}`` dicts.

    The metric card is built from tables too, and its first column is `field`, so it is
    skipped: this reads the ordering, and the card is read by ``card_blocks`` below.
    """
    lines = markdown.splitlines()
    records = []
    for index, line in enumerate(lines):
        if not line.startswith("|") or index + 1 >= len(lines):
            continue
        if not lines[index + 1].startswith("|---"):
            continue
        header = [cell.strip() for cell in line.strip("|").split("|")]
        if not header or header[0] != "cell":
            continue
        for body in lines[index + 2:]:
            if not body.startswith("|"):
                break
            cells = [cell.strip() for cell in body.strip("|").split("|")]
            records.append(dict(zip(header, cells)))
    return records


def printed_order(markdown, workload=None):
    """The cells in the order the tables print them, optionally for one workload alone."""
    return [
        row["cell"]
        for row in leaderboard_rows(markdown)
        if workload is None or row["workload"] == workload
    ]


def card_blocks(markdown):
    """The metric card's text, keyed by ``(workload, cell)``."""
    blocks, workload, cell = {}, None, None
    for line in markdown.splitlines():
        if line.startswith("### Workload "):
            workload, cell = line[len("### Workload "):].strip("`"), None
        elif line.startswith("#### `"):
            cell = line.split("`")[1]
            blocks[(workload, cell)] = []
        elif cell is not None:
            blocks[(workload, cell)].append(line)
    return {key: "\n".join(block) for key, block in blocks.items()}


def two_shapes():
    """Two cells under two shapes, and the shapes do not agree on a winner.

    `chat` decodes in a short window, `decode` in a long one, and the two runtimes are
    strong in opposite ones — which is the whole reason a figure is never averaged across
    workloads, and the reason each table is ordered on its own.
    """
    def shape(cell_id, runtime, *, window, workload_id):
        return cell_result(
            [obs(ttft=0.4, last=0.4 + window) for _ in range(5)],
            cell_id=cell_id,
            runtime=runtime,
            runtime_version=f"{runtime} 1.0",
            workload_id=workload_id,
        )

    return report.summarize(
        [
            shape("oq4__mlxlm", "mlxlm", window=1.0, workload_id="chat"),
            shape("oq4__mlxlm", "mlxlm", window=4.0, workload_id="decode"),
            shape("oq4__osaurus", "osaurus", window=2.0, workload_id="chat"),
            shape("oq4__osaurus", "osaurus", window=1.0, workload_id="decode"),
        ]
    )


# --- floors --------------------------------------------------------------------------------


def test_a_cell_that_failed_the_coherence_gate_is_excluded_and_names_its_floor():
    """A FAILed cell is a result: still printed, still shown, never ranked."""
    rows = report.summarize(
        [
            cell_result([obs()]),
            cell_result(
                [obs()],
                cell_id="oq4__omlx",
                runtime="omlx",
                status="FAIL",
                reason="incoherent output: replacement characters",
            ),
        ]
    )
    gagged = rows[1]

    assert gagged["rankable"] is False
    assert gagged["excluded_by"] == "coherence"
    assert gagged["exclusion"] == "excluded by coherence"
    assert [floor["state"] for floor in gagged["floors"]] == [
        "fail",
        "not reached",
    ]

    printed = leaderboard_rows(report.render_markdown(rows, axis="runtime"))

    assert [row["cell"] for row in printed] == ["oq4__mlxlm", "oq4__omlx"]
    assert printed[1]["rank by decode_tps"] == "—"
    assert "excluded by coherence" in printed[1]["notes"]
    assert "incoherent output: replacement characters" in printed[1]["notes"]


def test_a_fast_cell_that_failed_a_floor_does_not_rank():
    """Speed buys no rank: the floors are pass/fail, never a weight added to a metric."""
    rows = report.summarize(
        [
            cell_result([obs(ttft=0.4, last=4.4) for _ in range(5)]),
            cell_result(
                [obs(ttft=0.4, last=0.6) for _ in range(5)],
                cell_id="oq4__omlx",
                runtime="omlx",
                status="FAIL",
                reason="incoherent output: replacement characters",
            ),
        ]
    )
    printed = leaderboard_rows(report.render_markdown(rows, axis="runtime"))

    # The excluded cell decodes at 505 tok/s against the healthy cell's 25, and ranks
    # nowhere: it is not in the ordering at all, rather than losing a tie-break in it.
    assert rows[1]["decode_tps"] == pytest.approx(505.0)
    assert rows[0]["decode_tps"] == pytest.approx(25.25)
    assert [row["cell"] for row in printed] == ["oq4__mlxlm", "oq4__omlx"]
    assert printed[1]["rank by decode_tps"] == "—"


def test_a_cell_that_lost_a_published_metric_is_excluded_by_the_metrics_floor():
    rows = report.summarize(
        [
            cell_result([obs()]),
            cell_result(
                [obs(completion=None, token_source="none")],
                cell_id="oq4__omlx",
                runtime="omlx",
                status="FAIL",
                reason="no content completion tokens from token_source='none', so decode "
                "tok/s is undefined",
            ),
        ]
    )
    gagged = rows[1]

    assert gagged["excluded_by"] == "metrics"
    assert [floor["state"] for floor in gagged["floors"]] == [
        "pass",
        "fail",
    ]
    notes = leaderboard_rows(report.render_markdown(rows, axis="runtime"))[1]["notes"]
    assert "excluded by metrics" in notes
    assert "no content completion tokens" in notes


def test_a_cell_that_never_ran_is_shown_and_says_it_was_not_measured():
    """N/A is not a gate failure, so it names no floor — and it still cannot rank."""
    rows = report.summarize(
        [
            cell_result([obs()]),
            cell_result(
                [],
                cell_id="oq4__omlx",
                runtime="omlx",
                status="N/A",
                reason="runtime 'omlx' did not start: TimeoutError: port 8100 never opened",
            ),
        ]
    )
    never_ran = rows[1]

    assert never_ran["rankable"] is False
    assert never_ran["excluded_by"] is None
    assert never_ran["exclusion"] == "not ranked: not measured"
    assert {floor["state"] for floor in never_ran["floors"]} == {"not measured"}
    assert all("not measured" in floor["detail"] for floor in never_ran["floors"])

    printed = leaderboard_rows(report.render_markdown(rows, axis="runtime"))
    assert [row["cell"] for row in printed] == ["oq4__mlxlm", "oq4__omlx"]
    assert "not ranked: not measured" in printed[1]["notes"]
    assert "port 8100 never opened" in printed[1]["notes"]


def test_the_floors_are_pass_fail_and_never_weighted(rows):
    for row in rows:
        assert [floor["floor"] for floor in row["floors"]] == list(report.FLOORS)
        assert row["rankable"] is all(
            floor["state"] in report.FLOOR_CLEARED for floor in row["floors"]
        )


# --- ordering ------------------------------------------------------------------------------

# 101 completion tokens over windows of 1.0 s and 5.0 s: 101.0 tok/s against 20.2 tok/s.
HEALTHY = [obs(ttft=0.5, last=1.5) for _ in range(5)]
SLOW = [obs(ttft=0.5, last=5.5) for _ in range(5)]


def test_a_higher_is_better_metric_sorts_descending():
    rows = report.summarize(
        [
            cell_result(SLOW, cell_id="oq4__mlxlm", runtime="mlxlm"),
            cell_result(HEALTHY, cell_id="oq4__osaurus", runtime="osaurus"),
        ]
    )
    table = report.render_markdown(rows, axis="runtime", rank="decode_tps")
    printed = leaderboard_rows(table)

    assert [row["cell"] for row in printed] == ["oq4__osaurus", "oq4__mlxlm"]
    assert [row["rank by decode_tps"] for row in printed] == ["1", "2"]
    assert [row["decode tok/s"] for row in printed] == ["101.0", "20.2"]


def test_a_lower_is_better_metric_sorts_ascending():
    rows = report.summarize(
        [
            cell_result(SLOW, cell_id="oq4__mlxlm", runtime="mlxlm", memory={"peak_mb": 9150.0}),
            cell_result(
                HEALTHY, cell_id="oq4__osaurus", runtime="osaurus", memory={"peak_mb": 4200.0}
            ),
        ]
    )
    printed = leaderboard_rows(report.render_markdown(rows, axis="runtime", rank="peak_mb"))

    assert [row["cell"] for row in printed] == ["oq4__osaurus", "oq4__mlxlm"]
    assert [row["peak MB"] for row in printed] == ["4200.0", "9150.0"]
    assert report.RANK_METRICS["peak_mb"] == "lower"


def test_every_rank_metric_is_named_and_carries_its_direction():
    """The metric keys are the ones a row already carries, and each says which end is good."""
    assert set(report.RANK_METRICS) == {
        "decode_tps",
        "aggregate_tps",
        "ttft_p50_s",
        "prefill_tps",
        "itl_s",
        "peak_mb",
        "cold_load_s",
        "disk_bytes",
    }
    assert report.RANK_METRICS["decode_tps"] == "higher"
    for metric in ("ttft_p50_s", "itl_s", "peak_mb", "cold_load_s", "disk_bytes"):
        assert report.RANK_METRICS[metric] == "lower"

    row = report.summarize([cell_result(HEALTHY)])[0]
    assert set(report.RANK_METRICS) <= set(row)


def test_the_table_header_names_the_metric_it_is_ordered_by(rows):
    default = report.render_markdown(rows, axis="runtime")
    chosen = report.render_markdown(rows, axis="runtime", rank="cold_load_s")

    assert "rank by decode_tps" in default
    assert "ordered by `decode_tps` (higher is better)" in default
    assert "rank by cold_load_s" in chosen
    assert "ordered by `cold_load_s` (lower is better)" in chosen
    assert "rank by decode_tps" not in chosen


def test_a_row_whose_ranking_metric_is_none_ranks_last_and_says_why():
    """A stream with no decode window has no rate to rank by. It is not silently dropped."""
    rows = report.summarize(
        [
            one_delta_cell(),
            cell_result(HEALTHY, cell_id="oq4__mlxlm", runtime="mlxlm"),
        ]
    )
    printed = leaderboard_rows(report.render_markdown(rows, axis="runtime"))

    assert [row["cell"] for row in printed] == ["oq4__mlxlm", "oq4__omlx"]
    assert printed[1]["rank by decode_tps"] == "—"
    assert printed[1]["decode tok/s"] == "—"
    assert "decode_tps is None, so this row ranks last" in printed[1]["notes"]
    assert "fewer than 2 content deltas" in printed[1]["notes"]
    # The rank note quotes the reason once; the notes cell does not print it again.
    assert printed[1]["notes"].count("decode tok/s, ITL and prefill tok/s omitted") == 1

    # The row that has a value still gets a rank; the valueless one is not one of the ranks.
    assert printed[0]["rank by decode_tps"] == "1"
    valueless = report.order_rows(rows, "decode_tps")[1]
    assert valueless["rank"] is None
    assert valueless["rankable"] is True


def test_each_workload_is_ranked_on_its_own():
    """The shapes disagree, so one figure for both would describe neither."""
    table = report.render_markdown(two_shapes(), axis="runtime")
    printed = leaderboard_rows(table)

    assert printed_order(table, "chat") == ["oq4__mlxlm", "oq4__osaurus"]
    assert printed_order(table, "decode") == ["oq4__osaurus", "oq4__mlxlm"]
    # And each table is numbered from one: a rank is a position in one shape's ordering,
    # never a position in some ordering of all the shapes taken together.
    for workload in ("chat", "decode"):
        assert [
            row["rank by decode_tps"] for row in printed if row["workload"] == workload
        ] == ["1", "2"]


def test_the_workload_is_a_column_so_a_row_quoted_alone_still_says_which_shape_it_is():
    printed = leaderboard_rows(report.render_markdown(two_shapes(), axis="runtime"))

    assert [row["workload"] for row in printed] == ["chat", "chat", "decode", "decode"]


def test_ranking_one_metric_leaves_the_rows_it_was_given_alone():
    rows = report.summarize(
        [
            cell_result(SLOW, cell_id="oq4__mlxlm", runtime="mlxlm"),
            cell_result(HEALTHY, cell_id="oq4__osaurus", runtime="osaurus"),
        ]
    )
    before = [dict(row) for row in rows]

    assert [row["cell_id"] for row in report.order_rows(rows, "decode_tps")] == [
        "oq4__osaurus",
        "oq4__mlxlm",
    ]
    assert [row["cell_id"] for row in report.order_rows(rows, "peak_mb")] == [
        "oq4__mlxlm",
        "oq4__osaurus",
    ]
    assert rows == before


def test_an_unknown_metric_is_refused_rather_than_guessed(rows):
    with pytest.raises(ValueError):
        report.order_rows(rows, "vibes")
    with pytest.raises(ValueError):
        report.render_markdown(rows, axis="runtime", rank="vibes")
    with pytest.raises(ValueError):
        report.render_cards(rows, rank="vibes")


def test_the_row_carries_no_blended_or_normalised_figure(rows):
    """One number blending speed and memory would need weights nobody can justify."""
    numbers = {
        key
        for key, value in rows[0].items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }

    assert numbers <= {
        "n_measured",
        "n_requests",
        "content_deltas",
        # Counts, like the three above: how many batches the row landed and the pin it was
        # checked against. Neither is a figure and neither orders anything.
        "measured_batches",
        "measured_pin",
        "ttft_p50_s",
        "ttft_p90_s",
        "ttft_p99_s",
        "itl_s",
        "decode_tps",
        "aggregate_tps",
        "prefill_tps",
        "cold_load_s",
        "first_request_s",
        "peak_mb",
        "disk_bytes",
    }
    assert not any(
        word in key
        for key in rows[0]
        for word in ("score", "blend", "composite", "index", "normal", "weighted")
    )


# --- the metric card -----------------------------------------------------------------------


def test_the_card_carries_every_metric_for_every_cell_and_workload():
    rows = two_shapes()
    card = card_blocks(report.render_cards(rows, rank="decode_tps"))

    assert set(card) == {
        ("chat", "oq4__mlxlm"),
        ("chat", "oq4__osaurus"),
        ("decode", "oq4__mlxlm"),
        ("decode", "oq4__osaurus"),
    }
    # Every figure the row carries, named here rather than read from the card's own list of
    # fields: a card that dropped one should fail this, not quietly shrink the expectation.
    for block in card.values():
        for field in (
            "ttft_p50_s",
            "ttft_p90_s",
            "ttft_p99_s",
            "itl_s",
            "decode_tps",
            "aggregate_tps",
            "prefill_tps",
            "cold_load_s",
            "first_request_s",
            "peak_mb",
            "disk_bytes",
        ):
            assert f"| {field} |" in block, field


def test_the_card_prints_the_values_the_ranking_was_computed_from():
    rows = two_shapes()
    card = card_blocks(report.render_cards(rows, rank="decode_tps"))
    by_key = {(row["workload_id"], row["cell_id"]): row for row in rows}

    for key, block in card.items():
        row = by_key[key]
        assert f"{row['decode_tps']:.1f}" in block
        assert f"{row['ttft_p50_s']:.3f}" in block
        assert f"{row['peak_mb']:.1f}" in block


def test_the_card_carries_the_raw_inputs_the_figures_were_derived_from():
    rows = report.summarize([cell_result(HEALTHY)])
    block = card_blocks(report.render_cards(rows, rank="decode_tps"))[("chat", "oq4__mlxlm")]

    assert "| n measured | 5 |" in block
    assert "| n requests | 5 |" in block
    assert "| content deltas | 505 |" in block
    assert "| token_source | usage |" in block


def test_the_card_prints_every_floor_verdict_including_the_one_it_cannot_evaluate():
    rows = report.summarize(
        [
            cell_result(HEALTHY),
            cell_result(
                HEALTHY,
                cell_id="oq4__omlx",
                runtime="omlx",
                status="FAIL",
                reason="incoherent output: replacement characters",
            ),
        ]
    )
    card = card_blocks(report.render_cards(rows, rank="decode_tps"))

    healthy = card[("chat", "oq4__mlxlm")]
    assert "| floor coherence | pass |" in healthy
    assert "| floor metrics | pass |" in healthy

    gagged = card[("chat", "oq4__omlx")]
    assert "| floor coherence | fail |" in gagged
    assert "incoherent output: replacement characters" in gagged
    assert "| floor metrics | not reached |" in gagged
    assert "| rank | — | excluded by coherence |" in gagged


def test_the_card_marks_the_metric_the_ordering_used():
    rows = report.summarize([cell_result(HEALTHY)])
    block = card_blocks(report.render_cards(rows, rank="peak_mb"))[("chat", "oq4__mlxlm")]

    assert "| peak_mb | 9150.0 | the ranking metric |" in block
    assert "| decode_tps | 101.0 |" in block
    assert "| decode_tps | 101.0 | the ranking metric" not in block


def test_the_card_rides_under_the_tables_in_the_rendered_leaderboard():
    markdown = report.render_markdown(two_shapes(), axis="runtime")

    assert "## Metric card" in markdown
    assert markdown.index("## Workload `chat`") < markdown.index("## Metric card")
    assert len(card_blocks(markdown)) == 4


def test_the_card_states_an_empty_value_and_why_rather_than_leaving_a_blank():
    """A one-delta stream has no rate, and the card says so where the number would be."""
    block = card_blocks(report.render_cards(report.summarize([one_delta_cell()])))[
        ("chat", "oq4__omlx")
    ]

    assert "| decode_tps | — | the ranking metric; n=0: decode tok/s, ITL and prefill tok/s" in (
        block
    )
    assert "| ttft_p50_s | 5.499 |" in block
    assert "time-to-completion" in block


# --- --rank on the CLI ----------------------------------------------------------------------


def rank_action():
    actions = cli._parser()._subparsers._group_actions[0].choices["run"]._actions
    return next(action for action in actions if "--rank" in action.option_strings)


def test_the_cli_defaults_to_one_named_metric_and_offers_the_rows_own_keys():
    action = rank_action()

    assert action.default == "decode_tps"
    assert set(action.choices) == set(report.RANK_METRICS)


def test_run_writes_a_leaderboard_ordered_by_the_default_metric(fake_measure, tmp_path):
    code = cli.main(
        [
            "run",
            "--study",
            "runtime",
            "--cells",
            "oq4__mlxlm=/models/oq4,oq4__osaurus=/models/oq4",
            "--results-dir",
            str(tmp_path / "results"),
        ]
    )
    leaderboard = (list((tmp_path / "results").iterdir())[0] / "leaderboard.md").read_text()

    assert code == 0
    assert "rank by decode_tps" in leaderboard
    # The osaurus fixture decodes faster (72.1 tok/s against 53.2), so it prints first
    # although it was handed over second.
    assert printed_order(leaderboard) == ["oq4__osaurus", "oq4__mlxlm"]


def test_run_orders_the_leaderboard_by_the_metric_the_caller_named(fake_measure, tmp_path):
    code = cli.main(
        [
            "run",
            "--study",
            "runtime",
            "--cells",
            "oq4__mlxlm=/models/oq4,oq4__osaurus=/models/oq4",
            "--rank",
            "ttft_p50_s",
            "--results-dir",
            str(tmp_path / "results"),
        ]
    )
    leaderboard = (list((tmp_path / "results").iterdir())[0] / "leaderboard.md").read_text()

    assert code == 0
    assert "rank by ttft_p50_s" in leaderboard
    assert "lower is better" in leaderboard
    # The same two cells, the other ordering: 0.6 s against 1.1 s.
    assert printed_order(leaderboard) == ["oq4__mlxlm", "oq4__osaurus"]


def test_run_refuses_a_metric_that_is_not_one_a_row_carries(tmp_path, capsys):
    with pytest.raises(SystemExit):
        cli.main(
            [
                "run",
                "--study",
                "runtime",
                "--cells",
                "oq4__mlxlm=/models/oq4",
                "--rank",
                "vibes",
                "--results-dir",
                str(tmp_path),
            ]
        )

    assert list(tmp_path.iterdir()) == []


# --- the joined grid (Phase 5) --------------------------------------------------------------
#
# Phase 3 measured the grid one column at a time: five run directories, one runtime each. The
# join is the only place this project could vary two things without noticing, so the tests below
# are in three groups — a legal five-column join renders, each of the four guards refuses, and
# the three entry states stay distinguishable in the text.

# The formats, and where each one's bytes live. A label that points at two artifacts is two
# formats, which is guard 3's whole subject.
ARTIFACTS = {
    "oq4": "/models/oq4",
    "jang": "/models/jang",
    "jangtq": "/models/jangtq",
    "mxfp4": "/models/mxfp4",
    "mlx4": "/models/mlx4",
}

TOKENS = {"chat": 128, "prefill": 64, "decode": 512}

# Five run directories, one per runtime, each holding its own formats. The formats are ragged on
# purpose — mlx-lm and Osaurus both load `jang` and nothing loads everything — so the joined grid
# contains `—` as its ordinary case, exactly as the five Phase 3 runs did. Each entry is
# ``(run label, runtime, version, the formats that runtime loaded)``.
GRID_PLAN = (
    ("20260915T200320Z-format", "mlxlm", "mlx-lm 0.31.3", ("oq4", "jang")),
    ("20260915T201803Z-format", "omlx", "oMLX 0.6.4", ("oq4", "jangtq")),
    ("20260915T203336Z-format", "optiq", "mlx-optiq 0.5.6", ("oq4", "mxfp4")),
    ("20260915T204833Z-format", "vmlx", "vMLX 1.6.59", ("oq4", "mlx4")),
    ("20260915T210312Z-format", "osaurus", "Osaurus 0.25.4", ("oq4", "jang")),
)

RUN_A = "20260915T200320Z-format"
RUN_B = "20260915T201803Z-format"


def run_header(workload_ids=("chat", "prefill", "decode"), **pins):
    """A run header shaped the way ``measure.write_jsonl`` writes one."""
    header = {"temperature": 0.0, "seed": 0, "warmup": 3, "measured": 5, "cooldown_s": 30.0}
    header.update(pins)
    header["workloads"] = [
        {
            "id": workload_id,
            "messages": [{"role": "user", "content": f"the {workload_id} prompt"}],
            "max_tokens": TOKENS[workload_id],
        }
        for workload_id in workload_ids
    ]
    return header


def grid_run(
    run_label,
    runtime,
    version,
    labels,
    *,
    workload_ids=("chat", "prefill", "decode"),
    rate_of=None,
    status="PASS",
    reason=None,
    header=None,
    artifacts=None,
):
    """One run directory as the ``(run label, header, rows)`` tuple ``render_grid`` takes.

    The rows are ``summarize``'s, because that is what the caller has: the grid joins five
    published run directories, not five sets of observations. Each cell decodes at the same rate
    on every request, so no cell is drift-annotated unless a test asks for it by name.
    """
    artifacts = ARTIFACTS if artifacts is None else artifacts

    def rate(label, workload_id):
        return 100.0 if rate_of is None else rate_of(label, workload_id)

    rows = [
        cell_result(
            [obs(ttft=0.5, last=0.5 + 101 / rate(label, workload_id)) for _ in range(5)],
            cell_id=f"{label}__{runtime}",
            runtime=runtime,
            artifact_dir=artifacts[label],
            label=label,
            runtime_version=version,
            workload_id=workload_id,
            status=status,
            reason=reason,
            disk_bytes=1_000_000,
        )
        for label in labels
        for workload_id in workload_ids
    ]
    return (
        run_label,
        run_header(workload_ids) if header is None else header,
        report.summarize(rows),
    )


def grid_runs(plan=GRID_PLAN, **kwargs):
    """The run directories of *plan*, as the ``(label, header, rows)`` tuples ``render_grid``
    takes: what ``ohyesmlx grid <run-dir> ...`` hands over after reading each one back."""
    return [
        grid_run(run_label, runtime, version, labels, **kwargs)
        for run_label, runtime, version, labels in plan
    ]


def grid_tables(markdown):
    """The grid's tables as ``{workload: {format: {runtime: entry}}}``, in printed order.

    Read off the rendered text rather than from the rows behind it: what a reader can tell
    apart is the question here, and a helper that went back to the dicts would not answer it.
    """
    tables, workload = {}, None
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("## Workload ") and line.count("`") >= 2:
            workload = line.split("`")[1]
        if workload is None or not line.startswith("| format |"):
            continue
        header = [cell.strip() for cell in line.strip("|").split("|")][1:]
        table = {}
        for body in lines[index + 2:]:
            if not body.startswith("|"):
                break
            cells = [cell.strip() for cell in body.strip("|").split("|")]
            table[cells[0]] = dict(zip(header, cells[1:]))
        tables[workload] = table
    return tables


def assert_refused(runs, *fragments):
    """The join refused, and its message carried every fragment the interface requires."""
    with pytest.raises(ValueError) as raised:
        report.render_grid(runs)
    message = str(raised.value)
    for fragment in fragments:
        assert fragment in message, f"{fragment!r} is missing from the refusal: {message}"
    return message


def test_harness_source_mismatch_refuses_grid_and_sweep_joins():
    grid = [
        grid_run(RUN_A, "mlxlm", "mlx-lm 0.31.3", ("oq4",), workload_ids=("chat",),
                 header=run_header(("chat",), harness={"version": "0.3.0", "source_sha256": "aaa"})),
        grid_run(RUN_B, "omlx", "oMLX 0.6.4", ("oq4",), workload_ids=("chat",),
                 header=run_header(("chat",), harness={"version": "0.3.0", "source_sha256": "bbb"})),
    ]
    with pytest.raises(ValueError) as raised:
        report.render_grid(grid)
    assert RUN_A in str(raised.value) and RUN_B in str(raised.value)
    assert "source_sha256" in str(raised.value)

    sweep = [
        concurrency_run(SWEEP_RUNS[0], 1, header=run_header(
            ("chat",), concurrency=1,
            harness={"version": "0.3.0", "source_sha256": "aaa"},
        )),
        concurrency_run(SWEEP_RUNS[1], 8, header=run_header(
            ("chat",), concurrency=8,
            harness={"version": "0.3.0", "source_sha256": "bbb"},
        )),
    ]
    with pytest.raises(ValueError) as raised:
        report.render_sweep(sweep, varying="concurrency")
    assert SWEEP_RUNS[0] in str(raised.value) and SWEEP_RUNS[1] in str(raised.value)
    assert "source_sha256" in str(raised.value)


def test_legacy_runs_without_harness_provenance_still_join():
    rendered = report.render_grid([
        grid_run(RUN_A, "mlxlm", "mlx-lm 0.31.3", ("oq4",), workload_ids=("chat",)),
    ])
    assert "Grid" in rendered
    assert "Harness" not in rendered

    pinned = grid_run(
        RUN_A,
        "mlxlm",
        "mlx-lm 0.31.3",
        ("oq4",),
        workload_ids=("chat",),
        header=run_header(
            ("chat",), harness={"version": "0.3.0", "source_sha256": "abc123"}
        ),
    )
    rendered = report.render_grid([pinned])
    assert "Harness `0.3.0` source_sha256 `abc123`" in rendered


def test_a_legal_five_column_join_renders_one_table_per_workload():
    grid = report.render_grid(grid_runs())
    tables = grid_tables(grid)

    # One table per workload, ordered on its own. Never one table over a figure averaged across
    # the three shapes: a prefill-bound number blended with a decode-bound one describes neither.
    assert set(tables) == {"chat", "prefill", "decode"}
    assert "no figure is averaged across workloads" in grid

    # Every table carries every column, in run order, so a format sits in the same place in each.
    for table in tables.values():
        assert list(table["oq4"]) == ["mlxlm", "omlx", "optiq", "vmlx", "osaurus"]
        assert set(table) == {"oq4", "jang", "jangtq", "mxfp4", "mlx4"}

    # The one row every run measured: five numbers, no rag and no failure.
    assert all(entry == "100.0" for entry in tables["chat"]["oq4"].values())


def test_the_join_states_the_pins_and_every_run_directory_it_joined():
    grid = report.render_grid(grid_runs())

    for run_label, runtime, version, _labels in GRID_PLAN:
        assert run_label in grid, f"{run_label} is not in the provenance block"
        assert version in grid, f"{version} is not in the provenance block"
        assert runtime in grid

    assert (
        "Pins all columns share: temperature `0.0`, seed `0`, warmup `3`, measured `5`, "
        "cooldown_s `30.0`, concurrency `1`, prompt_tokens `—`, cache_state `—`." in grid
    )
    assert "Workloads all columns ran, with identical messages: `chat` (max_tokens 128)" in grid


def test_a_ragged_cell_and_a_failed_cell_and_a_missing_cell_are_three_entries():
    """`—` is the ordinary case in a ragged grid; FAIL is a result. A reader who cannot tell
    them apart is reading a different grid."""
    runs = [
        grid_run(RUN_A, "mlxlm", "mlx-lm 0.31.3", ("oq4", "jang"), workload_ids=("chat",)),
        grid_run(RUN_B, "omlx", "oMLX 0.6.4", ("oq4",), workload_ids=("chat",)),
        grid_run(
            "20260915T203336Z-format",
            "optiq",
            "mlx-optiq 0.5.6",
            ("jangtq",),
            workload_ids=("chat",),
            status="FAIL",
            reason="incoherent output: replacement characters",
        ),
    ]
    grid = report.render_grid(runs)
    table = grid_tables(grid)["chat"]

    assert table["oq4"]["mlxlm"] == "100.0"  # measured and cleared every floor
    assert table["oq4"]["omlx"] == "100.0"
    assert table["jang"]["mlxlm"] == "100.0"
    assert table["jang"]["omlx"] == "—"  # omlx never loaded jang: a rag, not a failure
    assert table["jangtq"]["optiq"] == "FAIL"  # optiq loaded it and the output was not language
    assert table["jang"]["optiq"] == "—"

    assert table["jang"]["omlx"] != table["jangtq"]["optiq"]
    assert "| `—` | a combination no run measured |" in grid
    assert "| `FAIL` | a measured cell that did not clear one |" in grid


def test_a_cell_that_never_ran_is_a_rag_and_not_a_failure():
    """`N/A` is measure's word for a cell that never ran here — the state the floors print as
    "not measured" — so its entry is the same `—` a combination that was never on the plan gets.
    """
    rows = report.summarize(
        [cell_result([], status="N/A", reason="unknown runtime 'nope'", label="oq4")]
    )
    run = (RUN_A, run_header(("chat",)), rows)

    table = grid_tables(report.render_grid([run]))["chat"]

    assert table["oq4"]["mlxlm"] == "—"
    assert table["oq4"]["mlxlm"] != "FAIL"


def test_a_drift_annotated_cell_carries_its_marker_into_its_entry():
    """A grid that hid what the leaderboard shows is a downgrade of the same data: the marker
    the row already earned travels with the number."""
    climbing = report.summarize(
        [
            drift_cell(
                CLIMBING,
                cell_id="oq4__mlxlm",
                runtime="mlxlm",
                label="oq4",
                artifact_dir=ARTIFACTS["oq4"],
                runtime_version="mlx-lm 0.31.3",
                disk_bytes=1_000_000,
            )
        ]
    )[0]
    settled = report.summarize(
        [
            drift_cell(
                FLAT,
                cell_id="oq4__osaurus",
                runtime="osaurus",
                label="oq4",
                artifact_dir=ARTIFACTS["oq4"],
                runtime_version="Osaurus 0.25.4",
                disk_bytes=1_000_000,
            )
        ]
    )[0]

    assert climbing["drift_note"] is not None, "the fixture has to be an annotated cell"
    assert settled["drift_note"] is None

    grid = report.render_grid(
        [(RUN_A, run_header(("chat",)), [climbing]), (RUN_B, run_header(("chat",)), [settled])]
    )
    table = grid_tables(grid)["chat"]

    assert table["oq4"]["mlxlm"] == "101.0 (drift +100.0%)"
    assert table["oq4"]["osaurus"] == "101.0"
    assert "51.0" not in grid, "the marker is the percentage, not a second number"


def test_a_short_measured_window_carries_its_count_into_its_entry():
    """The grid has no notes column, so a cell read from four batches would otherwise render
    exactly like one read from nine: the entry prints the count beside the number, the way the
    drift marker prints the percentage."""
    rows = report.summarize(
        [
            cell_result(
                [obs() for _ in range(4)],
                cell_id="oq4__mlxlm",
                label="oq4",
                artifact_dir=ARTIFACTS["oq4"],
                runtime_version="mlx-lm 0.31.3",
                disk_bytes=1_000_000,
            ),
            cell_result(
                [obs() for _ in range(9)],
                cell_id="jang__mlxlm",
                label="jang",
                artifact_dir=ARTIFACTS["jang"],
                runtime_version="mlx-lm 0.31.3",
                disk_bytes=1_000_000,
            ),
        ],
        measured=9,
    )

    grid = report.render_grid([(RUN_A, run_header(("chat",), measured=9), rows)])
    table = grid_tables(grid)["chat"]

    assert table["oq4"]["mlxlm"] == "50.5 (n=4 of 9)"
    assert table["jang"]["mlxlm"] == "50.5", "a full window carries its number alone"
    # Not a state of its own: the cell is a ranked entry with a count beside it, exactly as the
    # drift marker leaves an annotated cell ranked.
    assert "no value" not in table["oq4"]["mlxlm"]
    assert "FAIL" not in table["oq4"]["mlxlm"]


def test_a_short_and_drifting_cell_carries_both_markers_beside_its_number():
    """Two annotations are two facts about one number, and neither replaces the other: 101 tok/s
    in the early half against 202 in the late one, over four batches of a pinned nine."""
    row = report.summarize(
        [
            cell_result(
                [obs(ttft=0.5, last=0.5 + window) for window in (1.0, 1.0, 0.5, 0.5)],
                disk_bytes=1_000_000,
            )
        ],
        measured=9,
    )[0]

    assert row["decode_tps"] == pytest.approx(151.5)
    assert row["drift"]["change_pct"] == pytest.approx(100.0)

    grid = report.render_grid([(RUN_A, run_header(("chat",), measured=9), [row])])

    assert grid_tables(grid)["chat"]["oq4"]["mlxlm"] == "151.5 (drift +100.0%) (n=4 of 9)"


RANK_COLUMNS = {
    "decode_tps": "decode tok/s",
    "aggregate_tps": "aggregate tok/s",
    "prefill_tps": "prefill tok/s",
    "ttft_p50_s": "TTFT p50 s",
    "itl_s": "ITL s",
    "peak_mb": "peak MB",
    "cold_load_s": "cold load s",
    "disk_bytes": "disk bytes",
}


@pytest.mark.parametrize("rank", sorted(RANK_COLUMNS))
def test_a_grid_entry_is_the_same_string_the_leaderboard_prints(rank):
    """The grid rearranges published rows. Two renderings of one number that disagree are two
    numbers, so every metric the grid can be ordered by is checked against the table's own."""
    rows = report.summarize(
        [
            cell_result(
                [obs(ttft=0.5, last=2.5) for _ in range(5)],
                disk_bytes=1_234_567,
            )
        ]
    )
    run = (RUN_A, run_header(("chat",)), rows)

    printed = leaderboard_rows(report.render_markdown(rows, axis="format", rank=rank))[0]
    entry = grid_tables(report.render_grid([run], rank=rank))["chat"]["oq4"]["mlxlm"]

    assert printed["cell"] == "oq4__mlxlm"
    assert entry not in ("—", "FAIL"), f"the {rank} entry has no number to compare"
    assert entry == printed[RANK_COLUMNS[rank]]


def test_the_format_axis_reading_orders_one_runtimes_formats():
    """A column is the format axis: one runtime held constant, its formats ordered."""
    runs = [
        grid_run(
            RUN_A,
            "mlxlm",
            "mlx-lm 0.31.3",
            ("oq4", "jang"),
            workload_ids=("chat",),
            rate_of=lambda label, _workload: {"oq4": 100.0, "jang": 200.0}[label],
        )
    ]

    grid = report.render_grid(runs)

    assert "**Format axis — one runtime, its formats ordered.**" in grid
    assert "- `mlxlm`: `jang` (1) > `oq4` (2)" in grid


def test_the_runtime_axis_reading_orders_one_formats_runtimes():
    """A row is the runtime axis: one format held constant, its runtimes ordered."""
    runs = [
        grid_run(RUN_A, "mlxlm", "mlx-lm 0.31.3", ("oq4",), workload_ids=("chat",)),
        grid_run(
            RUN_B,
            "osaurus",
            "Osaurus 0.25.4",
            ("oq4",),
            workload_ids=("chat",),
            rate_of=lambda _label, _workload: 200.0,
        ),
    ]

    grid = report.render_grid(runs)

    assert "**Runtime axis — one format, its runtimes ordered.**" in grid
    assert "- `oq4`: `osaurus` (1) > `mlxlm` (2)" in grid
    # And the column on the same cells reads the other way round: the same cell is first in one
    # axis and last in the other, which is why neither reading answers the other's question.
    assert "- `osaurus`: `oq4` (1)" in grid
    assert "- `mlxlm`: `oq4` (1)" in grid


def test_the_best_cell_is_labelled_a_recommendation_across_the_grid():
    """One line per workload, and the one reading that spans both axes says so: the winning
    cell won under one format and one runtime at once, and the number cannot split them."""
    runs = [
        grid_run(
            RUN_A,
            "mlxlm",
            "mlx-lm 0.31.3",
            ("oq4", "jang"),
            workload_ids=("chat",),
            rate_of=lambda *_: 300.0,
        ),
        grid_run(
            RUN_B,
            "omlx",
            "oMLX 0.6.4",
            ("oq4",),
            workload_ids=("chat",),
            rate_of=lambda *_: 100.0,
        ),
    ]

    grid = report.render_grid(runs)

    assert grid.count("**Recommendation —") == 1  # one per workload, never one for the grid
    assert "a recommendation rather than an attribution" in grid
    assert "not which of the two earned it" in grid
    assert "`oq4__mlxlm` (mlxlm / oq4) leads all 3 ranked cells at `decode_tps` = 300.0" in grid


def test_a_grid_workload_with_no_ranked_cell_recommends_nothing():
    runs = [
        grid_run(
            RUN_A,
            "mlxlm",
            "mlx-lm 0.31.3",
            ("oq4",),
            workload_ids=("chat",),
            status="FAIL",
            reason="incoherent output: replacement characters",
        )
    ]

    grid = report.render_grid(runs)

    assert "**Recommendation — none.**" in grid
    assert "no best cell to name" in grid
    assert "`oq4`" in grid  # the excluded cell is still named in the readings, not dropped


def test_the_grid_refuses_a_rank_metric_no_row_carries():
    with pytest.raises(ValueError) as raised:
        report.render_grid(grid_runs(), rank="vibes")

    assert "rank must be one of" in str(raised.value)


# --- the four join guards --------------------------------------------------------------------


def test_guard_1_refuses_two_runs_that_pinned_a_header_field_differently():
    runs = [
        grid_run(RUN_A, "mlxlm", "mlx-lm 0.31.3", ("oq4",), workload_ids=("chat",)),
        grid_run(
            RUN_B,
            "omlx",
            "oMLX 0.6.4",
            ("oq4",),
            workload_ids=("chat",),
            header=run_header(("chat",), temperature=0.2),
        ),
    ]

    assert_refused(runs, RUN_A, RUN_B, "temperature")


def test_guard_1_refuses_a_concurrent_column_in_a_sequential_grid():
    """The defect plan 06-01c closes: 06-01b pinned the concurrency in the header and never
    added it here, so an N=8 run would have joined an N=1 grid without a word. It is refused
    against a column that pinned 1 and against one that predates the pin, which is the same
    fact written as an absence."""
    for sequential in (run_header(("chat",)), run_header(("chat",), concurrency=1)):
        runs = [
            grid_run(
                RUN_A, "mlxlm", "mlx-lm 0.31.3", ("oq4",), workload_ids=("chat",),
                header=sequential,
            ),
            grid_run(
                RUN_B,
                "osaurus",
                "Osaurus 0.25.4",
                ("jang",),
                workload_ids=("chat",),
                header=run_header(("chat",), concurrency=8),
            ),
        ]

        message = assert_refused(
            runs, RUN_A, RUN_B, "concurrency", "concurrency=1", "concurrency=8"
        )

        # A header that never carried the pin ran its requests one at a time, and that is what
        # the refusal says it pinned rather than leaving the value unstated.
        assert "concurrency=None" not in message


def test_guard_1_refuses_two_runs_that_pinned_a_different_prompt_length():
    """A prompt-length sweep is N runs differing in this pin, and two of its runs are one
    column each of a sweep. Joined as a grid instead they would be one table over two prompts."""
    runs = [
        grid_run(
            RUN_A,
            "mlxlm",
            "mlx-lm 0.31.3",
            ("oq4",),
            workload_ids=("prefill",),
            header=run_header(("prefill",), prompt_tokens={"target": 4096, "achieved": 4093}),
        ),
        grid_run(
            RUN_B,
            "osaurus",
            "Osaurus 0.25.4",
            ("jang",),
            workload_ids=("prefill",),
            header=run_header(
                ("prefill",), prompt_tokens={"target": 16384, "achieved": 16380}
            ),
        ),
    ]

    message = assert_refused(runs, RUN_A, RUN_B, "prompt_tokens")

    assert "4096" in message and "16384" in message


def test_guard_1_accepts_a_header_that_predates_the_concurrency_pin():
    """Every run written before the pin existed issued requests one at a time, so an absent
    concurrency is 1 rather than something unknown -- and a pre-pin column joins an N=1 column
    instead of being refused for a field it could not have written."""
    pre_pin = grid_run(RUN_A, "mlxlm", "mlx-lm 0.31.3", ("oq4",), workload_ids=("chat",))
    pinned_one = grid_run(
        RUN_B,
        "osaurus",
        "Osaurus 0.25.4",
        ("jang",),
        workload_ids=("chat",),
        header=run_header(("chat",), concurrency=1),
    )

    for runs in ([pre_pin, pinned_one], [pinned_one, pre_pin]):
        grid = report.render_grid(runs)

        assert "Provenance" in grid, "the join was refused where the absence is the fact"
        assert RUN_A in grid and RUN_B in grid


def test_guard_1_refuses_a_grid_over_two_cache_states():
    """`cache_state` is a header pin and a grid joins runs that agree on every one of them. Two
    states of one cell are a cache sweep's two columns; joined as a grid they would be one table
    whose difference the reader would attribute to the format or the runtime instead of to the
    cache."""
    for state_a, state_b in (("off", "on"), ("on", None)):
        runs = [
            grid_run(
                RUN_A, "mlxlm", "mlx-lm 0.31.3", ("oq4",), workload_ids=("chat",),
                header=run_header(("chat",), cache_state=state_a),
            ),
            grid_run(
                RUN_B, "osaurus", "Osaurus 0.25.4", ("jang",), workload_ids=("chat",),
                header=run_header(("chat",), cache_state=state_b),
            ),
        ]

        assert_refused(runs, RUN_A, RUN_B, "cache_state")


def test_guard_1_refuses_an_absent_cache_pin_against_a_pinned_off_one():
    """The defect the pin's absence invites: reading `None` as `off` would say a run whose cache
    state was never pinned was measured with the cache disabled. Every run on disk before the
    pin ran each runtime's own default and the Osaurus columns ran with it ON, so the absence is
    refused against `off` rather than folded into it."""
    pre_pin = grid_run(RUN_A, "mlxlm", "mlx-lm 0.31.3", ("oq4",), workload_ids=("chat",))
    pinned_off = grid_run(
        RUN_B,
        "osaurus",
        "Osaurus 0.25.4",
        ("jang",),
        workload_ids=("chat",),
        header=run_header(("chat",), cache_state="off"),
    )

    for runs in ([pre_pin, pinned_off], [pinned_off, pre_pin]):
        message = assert_refused(runs, RUN_A, RUN_B, "cache_state")

        assert "cache_state=None" in message, "the absence is printed as the absence"
        assert "cache_state='off'" in message


def test_guard_1_refuses_two_runs_that_pinned_a_different_max_tokens():
    header = run_header(("chat",))
    header["workloads"][0]["max_tokens"] = 256
    runs = [
        grid_run(RUN_A, "mlxlm", "mlx-lm 0.31.3", ("oq4",), workload_ids=("chat",)),
        grid_run(
            RUN_B,
            "omlx",
            "oMLX 0.6.4",
            ("oq4",),
            workload_ids=("chat",),
            header=header,
        ),
    ]

    assert_refused(runs, RUN_A, RUN_B, "max_tokens")


def test_guard_1_refuses_two_runs_that_pinned_different_prompts():
    header = run_header(("chat",))
    header["workloads"][0]["messages"] = [{"role": "user", "content": "a different prompt"}]
    runs = [
        grid_run(RUN_A, "mlxlm", "mlx-lm 0.31.3", ("oq4",), workload_ids=("chat",)),
        grid_run(
            RUN_B,
            "omlx",
            "oMLX 0.6.4",
            ("oq4",),
            workload_ids=("chat",),
            header=header,
        ),
    ]

    message = assert_refused(runs, RUN_A, RUN_B, "messages")

    # The prompts are 6.5 kB of prose in the real prefill column: the refusal names the field
    # rather than reprinting it.
    assert "a different prompt" not in message


def test_guard_2_refuses_a_cell_two_run_directories_both_measured():
    """There is no latest-wins rule: which run is newer is not which run is right."""
    runs = [
        grid_run(RUN_A, "mlxlm", "mlx-lm 0.31.3", ("oq4",), workload_ids=("chat",)),
        grid_run(RUN_B, "mlxlm", "mlx-lm 0.31.3", ("oq4",), workload_ids=("chat",)),
    ]

    assert_refused(runs, RUN_A, RUN_B, "(label, runtime, workload_id)", "latest-wins")


def test_guard_3_refuses_one_format_label_pointing_at_two_artifacts():
    runs = [
        grid_run(RUN_A, "mlxlm", "mlx-lm 0.31.3", ("oq4",), workload_ids=("chat",)),
        grid_run(
            RUN_B,
            "omlx",
            "oMLX 0.6.4",
            ("oq4",),
            workload_ids=("chat",),
            artifacts={"oq4": "/models/oq4-other"},
        ),
    ]

    assert_refused(runs, RUN_A, RUN_B, "artifact_dir", "/models/oq4", "/models/oq4-other")


def test_guard_4_refuses_one_runtime_measured_at_two_versions():
    """Osaurus measured 1.15x across exactly this step, so the held-constant variable moved.

    Two directories, two formats — so this is not guard 2's duplicate — and one runtime at the
    two builds.
    """
    runs = [
        grid_run(RUN_A, "osaurus", "Osaurus 0.25.3", ("oq4",), workload_ids=("chat",)),
        grid_run(RUN_B, "osaurus", "Osaurus 0.25.4", ("jang",), workload_ids=("chat",)),
    ]

    assert_refused(runs, RUN_A, RUN_B, "runtime_version", "Osaurus 0.25.3", "Osaurus 0.25.4")


def test_two_different_runtimes_at_two_versions_are_the_grid_working_as_intended():
    """Guard 4 is about one runtime at two versions, not about versions differing at all."""
    versions = [entry[2] for entry in GRID_PLAN]

    assert len(set(versions)) == len(versions)
    assert "mlx-lm 0.31.3" in report.render_grid(grid_runs())


def test_a_rankable_row_with_no_value_for_the_metric_is_not_a_ragged_cell():
    """A PASS cell with no value for this metric is its own state, not a hole in the matrix.

    `_number` renders None as the same em dash the grid uses for a combination nobody ran, so
    without a fourth state a cell that produced language and cleared every floor would file
    beside the ones that do not exist. oMLX returned a whole completion in one content delta
    and published no decode rate at all; that is a fact about the stream, not an absent cell.
    """
    ran = {"status": "PASS", "decode_tps": None, "drift": None, "rankable": True}
    never_ran = None
    failed = {"status": "FAIL", "decode_tps": None, "drift": None, "rankable": False}

    entries = {
        report._entry(ran, "decode_tps"),
        report._entry(never_ran, "decode_tps"),
        report._entry(failed, "decode_tps"),
    }
    assert len(entries) == 3, f"three states collapsed into {entries}"
    assert report._entry(ran, "decode_tps") == "no value"
    assert report._entry(never_ran, "decode_tps") == "—"
    assert report._entry(failed, "decode_tps") == "FAIL"


def test_the_runtime_axis_refuses_to_rank_a_metric_that_is_not_one_quantity():
    """A row ordered by peak_mb or cold_load_s says so before it prints the order.

    The grid is where this bites: within a column the runtime is held constant, so whatever
    `footprint` leaves out it leaves out identically and the format-axis ordering is sound.
    Across a row the runtime is the variable, and Osaurus's footprint lands below the weight
    bytes it is serving while its resident size sits at them. An ordering printed without
    that line reads as "Osaurus uses half the memory", which is a claim about the sampler.
    """
    rows = [
        {"cell_id": "oq4__osaurus", "runtime": "osaurus", "label": "oq4", "workload": "decode",
         "status": "PASS", "rankable": True, "peak_mb": 1792.0, "cold_load_s": 1.27,
         "decode_tps": 66.9, "drift": None},
        {"cell_id": "oq4__omlx", "runtime": "omlx", "label": "oq4", "workload": "decode",
         "status": "PASS", "rankable": True, "peak_mb": 4200.0, "cold_load_s": 1.69,
         "decode_tps": 75.5, "drift": None},
    ]
    runs = [("run-a", {}, [rows[0]]), ("run-b", {}, [rows[1]])]

    for metric in report.CROSS_RUNTIME_UNCOMPARABLE:
        rendered = report.render_grid(runs, rank=metric)
        assert f"`{metric}` is not one quantity across runtimes" in rendered, metric
        # the ordering is still printed: the reader is warned, not denied the numbers
        assert "Runtime axis" in rendered and "osaurus" in rendered

    speed = report.render_grid(runs, rank="decode_tps")
    assert "is not one quantity across runtimes" not in speed


# --- the Phase 6 sweep (a pin, not an axis) ---------------------------------------------------
#
# A sweep is N run directories differing in exactly one header pin, joined afterwards. The pin
# names how the run *drove* its cells -- how many requests went out together, how long the prompt
# was -- which is why neither can be a `--study` axis and why the join has to say both what
# varied and where every column came from.

SWEEP_RUNS = (
    "20260916T100000Z-format",
    "20260916T101000Z-format",
    "20260916T102000Z-format",
)

# The sentence a concurrency sweep carries, written out rather than read from the constant, so a
# reworded constant fails this file instead of agreeing with it.
DRIFT_SENTENCE = (
    "At concurrency > 1, measured drift reads per-request rates: positive drift means the "
    "per-request rate was still moving, not that the cell was under-warmed."
)


def concurrency_run(
    run_label,
    value,
    *,
    rate=100.0,
    labels=("oq4",),
    workload_ids=("chat",),
    runtime="mlxlm",
    version="mlx-lm 0.31.3",
    header=None,
    **kwargs,
):
    """One run of a concurrency sweep: the sweep's cells, driven at one N."""
    return grid_run(
        run_label,
        runtime,
        version,
        labels,
        workload_ids=workload_ids,
        rate_of=lambda *_: rate,
        header=run_header(workload_ids, concurrency=value) if header is None else header,
        **kwargs,
    )


def prompt_run(
    run_label,
    target,
    achieved,
    *,
    rate=100.0,
    labels=("oq4",),
    workload_ids=("prefill",),
    header=None,
    **pins,
):
    """One run of a prompt-length sweep: the same shapes, answered by prompts of different
    lengths. The text stands in for the pinned cut, and only has to differ across the runs the
    way the cut does."""
    if header is None:
        header = run_header(
            workload_ids, prompt_tokens={"target": target, "achieved": achieved}, **pins
        )
        header["workloads"][0]["messages"] = [
            {"role": "user", "content": f"a prompt sized to {target} tokens"}
        ]
    return grid_run(
        run_label,
        "mlxlm",
        "mlx-lm 0.31.3",
        labels,
        workload_ids=workload_ids,
        rate_of=lambda *_: rate,
        header=header,
    )


def other_prompt_header(workload_ids=("chat",), **pins):
    """A header whose one shape answered a prompt no other run of the sweep sent."""
    header = run_header(workload_ids, **pins)
    header["workloads"][0]["messages"] = [{"role": "user", "content": "a different prompt"}]
    return header


def cache_run(
    run_label,
    state,
    *,
    rate=100.0,
    labels=("oq4",),
    workload_ids=("prefill",),
    header=None,
    **kwargs,
):
    """One run of a cache-state sweep: the same prompt with prefix/KV reuse off or on."""
    return grid_run(
        run_label,
        "mlxlm",
        "mlx-lm 0.31.3",
        labels,
        workload_ids=workload_ids,
        rate_of=lambda *_: rate,
        header=run_header(workload_ids, cache_state=state) if header is None else header,
        **kwargs,
    )


def other_cache_header(workload_ids=("prefill",), state="on"):
    """A cache-sweep header whose one shape answered a prompt no other run sent."""
    return other_prompt_header(workload_ids, cache_state=state)


def sweep_tables(markdown):
    """The sweep's tables as ``{workload: {cell: {column head: entry}}}``, in printed order.

    Read off the rendered text for the same reason ``grid_tables`` is: what a reader can tell
    apart is the question, and the provenance table above the tables is not one of them.
    """
    tables, workload = {}, None
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("## Workload ") and line.count("`") >= 2:
            workload = line.split("`")[1]
        if workload is None or not line.startswith("| cell |"):
            continue
        header = [cell.strip() for cell in line.strip("|").split("|")][1:]
        table = {}
        for body in lines[index + 2:]:
            if not body.startswith("|"):
                break
            cells = [cell.strip() for cell in body.strip("|").split("|")]
            table[cells[0]] = dict(zip(header, cells[1:]))
        tables[workload] = table
    return tables


def assert_sweep_refused(runs, varying, *fragments):
    """The sweep refused, and its message carried every fragment the interface requires."""
    with pytest.raises(ValueError) as raised:
        report.render_sweep(runs, varying=varying)
    message = str(raised.value)
    for fragment in fragments:
        assert fragment in message, f"{fragment!r} is missing from the refusal: {message}"
    return message


def test_a_sweep_may_vary_only_one_of_the_header_pins():
    """A cell is (format, runtime) and none of these is one: they are properties of how a run
    drove its cells, which is why `--study` cannot name them and why anything else is refused
    rather than left uncompared."""
    runs = [concurrency_run(SWEEP_RUNS[0], 1), concurrency_run(SWEEP_RUNS[1], 8)]

    assert report.SWEEP_PINS == ("concurrency", "prompt_tokens", "cache_state")
    assert set(report.SWEEP_PINS) <= set(report.PIN_FIELDS)
    for varying in ("temperature", "seed", "warmup", "measured", "cooldown_s", "decode_tps", None):
        with pytest.raises(ValueError) as raised:
            report.render_sweep(runs, varying=varying)
        assert "varying must be one of" in str(raised.value), varying


def test_a_sweep_refuses_two_runs_that_pinned_something_else_differently():
    """Guard 1, unchanged: the one pin the caller named is skipped and every other field is
    compared exactly as the grid compares it, both directories named in the refusal."""
    runs = [
        concurrency_run(SWEEP_RUNS[0], 1),
        concurrency_run(
            SWEEP_RUNS[1], 8, header=run_header(("chat",), concurrency=8, temperature=0.2)
        ),
    ]

    assert_sweep_refused(
        runs, "concurrency", SWEEP_RUNS[0], SWEEP_RUNS[1], "temperature", "not one grid"
    )


def test_a_sweep_refuses_runs_that_all_pinned_the_same_value():
    """A pin that held still makes every run the same column, so there is no sweep to render."""
    runs = [
        concurrency_run(SWEEP_RUNS[0], 1, rate=100.0),
        concurrency_run(SWEEP_RUNS[1], 1, rate=50.0),
    ]

    message = assert_sweep_refused(
        runs, "concurrency", "does not vary", SWEEP_RUNS[0], SWEEP_RUNS[1]
    )

    assert "not a sweep" in message


def test_a_prompt_length_pin_is_keyed_on_its_target_not_on_what_was_achieved():
    """Two runs of one intended length are one column whatever their tokenizers landed on: the
    achieved count is a fact about one artifact's tokenizer, and it is printed beside the target
    rather than folded into the pin's identity."""
    at_one_target = [
        prompt_run(SWEEP_RUNS[0], 4096, 4093),
        prompt_run(SWEEP_RUNS[1], 4096, 4090),
    ]

    message = assert_sweep_refused(
        at_one_target, "prompt_tokens", "does not vary", "4093", "4090"
    )
    assert SWEEP_RUNS[0] in message and SWEEP_RUNS[1] in message

    # And the key really is the target: with a third run at another length the pin does vary, so
    # what refuses the pair above is the two of them sharing one column rather than the pin
    # having held still.
    with_another_length = at_one_target + [prompt_run(SWEEP_RUNS[2], 8192, 8180)]

    assert_sweep_refused(
        with_another_length,
        "prompt_tokens",
        "duplicate cell",
        "(label, runtime, workload_id, prompt_tokens)",
        SWEEP_RUNS[0],
        SWEEP_RUNS[1],
        "latest-wins",
    )


def test_a_sweep_refuses_a_cell_two_run_directories_measured_at_one_value():
    """Guard 2 with the pin in the key: one cell at two values is the table working, and one
    cell at one value twice is ambiguous rather than superseded."""
    runs = [
        concurrency_run(SWEEP_RUNS[0], 1),
        concurrency_run(SWEEP_RUNS[1], 1, rate=50.0),
        concurrency_run(SWEEP_RUNS[2], 8, rate=25.0),
    ]

    assert_sweep_refused(
        runs,
        "concurrency",
        "duplicate cell",
        "(label, runtime, workload_id, concurrency)",
        SWEEP_RUNS[0],
        SWEEP_RUNS[1],
        "latest-wins",
    )


def test_a_sweep_renders_a_prompt_length_sweep_whose_runs_answered_different_prompts():
    """The one relaxation, and the whole reason it exists: a prompt-length sweep's columns are
    meant to send different text, so `messages` goes uncompared for this pin."""
    runs = [prompt_run(SWEEP_RUNS[0], 128, 126), prompt_run(SWEEP_RUNS[1], 4096, 4093)]

    sweep = report.render_sweep(runs, varying="prompt_tokens", rank="ttft_p50_s")
    table = sweep_tables(sweep)["prefill"]

    assert list(table["oq4__mlxlm"]) == ["128 (achieved 126)", "4096 (achieved 4093)"]


def test_the_grid_still_refuses_the_prompt_difference_a_prompt_sweep_is_allowed():
    """The relaxation belongs to the sweep's prompt pin and nowhere else: as a grid, these two
    directories pinned the same length and answered different prompts, and are refused for it."""
    same_pin = run_header(("prefill",), prompt_tokens={"target": 128, "achieved": 126})
    same_pin["workloads"][0]["messages"] = [{"role": "user", "content": "the other prompt"}]
    runs = [
        prompt_run(SWEEP_RUNS[0], 128, 126),
        prompt_run(SWEEP_RUNS[1], 128, 126, header=same_pin),
    ]

    with pytest.raises(ValueError) as raised:
        report.render_grid(runs)

    message = str(raised.value)
    assert "messages" in message
    assert SWEEP_RUNS[0] in message and SWEEP_RUNS[1] in message


def test_a_concurrency_sweep_still_refuses_two_runs_that_answered_different_prompts():
    """Nothing about workloads is relaxed for a concurrency sweep: its columns answered one
    prompt, and a directory that answered another is not a column of it."""
    runs = [
        concurrency_run(SWEEP_RUNS[0], 1),
        concurrency_run(
            SWEEP_RUNS[1], 8, header=other_prompt_header(("chat",), concurrency=8)
        ),
    ]

    assert_sweep_refused(
        runs, "concurrency", "messages", SWEEP_RUNS[0], SWEEP_RUNS[1], "not one grid"
    )


def test_the_sweep_columns_ascend_in_the_order_of_the_pin():
    """The reading is the ordering: a prompt that got longer or batches that got wider says
    nothing across columns left in the order the directories were named."""
    runs = [
        concurrency_run(SWEEP_RUNS[0], 8, rate=25.0),
        concurrency_run(SWEEP_RUNS[1], 1, rate=100.0),
        concurrency_run(SWEEP_RUNS[2], 4, rate=50.0),
    ]

    heads = list(
        sweep_tables(report.render_sweep(runs, varying="concurrency"))["chat"]["oq4__mlxlm"]
    )
    assert heads == ["1", "4", "8"]

    # And the same for the lengths, in the order the runs happen to be named on the command line.
    prompts = [prompt_run(SWEEP_RUNS[0], 16384, 16380), prompt_run(SWEEP_RUNS[1], 128, 126)]
    heads = list(
        sweep_tables(report.render_sweep(prompts, varying="prompt_tokens"))["prefill"][
            "oq4__mlxlm"
        ]
    )
    assert heads == ["128 (achieved 126)", "16384 (achieved 16380)"]


def test_a_cache_state_sweep_renders_the_cold_column_before_the_warm_one():
    """The order is the pin's own and it is the reading: `off` is the baseline the `on` column
    is compared against. The runs are handed over the other way round, because a `cache_state`
    sweep whose columns came out in directory order would be an accident of spelling two words
    happen to sort the way the history is read."""
    runs = [
        cache_run(SWEEP_RUNS[1], "on", rate=200.0),
        cache_run(SWEEP_RUNS[0], "off", rate=100.0),
    ]

    sweep = report.render_sweep(runs, varying="cache_state")
    table = sweep_tables(sweep)["prefill"]["oq4__mlxlm"]

    assert list(table) == ["off", "on"]
    # Each column carries its own run's number: the two states are not one row printed twice.
    assert table == {"off": "100.0", "on": "200.0"}
    # The pin is named where a reader needs it, in the title and in the provenance block.
    assert "`cache_state`" in sweep.splitlines()[0]
    assert SWEEP_RUNS[0] in sweep and SWEEP_RUNS[1] in sweep
    assert "prefix/KV reuse" in sweep


def test_a_cache_state_sweep_refuses_two_runs_that_answered_different_prompts():
    """This pin relaxes nothing. A prompt-length sweep's columns are *meant* to answer different
    text; a cache sweep's are meant to answer the same text twice, once cold and once warm, so a
    pair of runs whose prompts differ is refused like any other grid -- the difference between
    their numbers would be a prompt's and would publish as a cache's."""
    runs = [
        cache_run(SWEEP_RUNS[0], "off"),
        cache_run(SWEEP_RUNS[1], "on", header=other_cache_header()),
    ]

    assert_sweep_refused(
        runs,
        "cache_state",
        "workload `prefill`",
        "pinned a different messages",
        SWEEP_RUNS[0],
        SWEEP_RUNS[1],
        "not one grid",
    )


def test_a_combination_no_run_measured_is_an_em_dash_and_a_failure_is_a_fail():
    """The grid's four entry states, rendered by the grid's own function: `—` is a combination
    nobody ran, `FAIL` is a cell that ran and did not clear a floor, and they are not alike."""
    runs = [
        concurrency_run(SWEEP_RUNS[0], 1, labels=("oq4",)),
        concurrency_run(
            SWEEP_RUNS[1],
            8,
            labels=("jang",),
            status="FAIL",
            reason="incoherent output: replacement characters",
        ),
    ]

    sweep = report.render_sweep(runs, varying="concurrency")
    table = sweep_tables(sweep)["chat"]

    assert table["oq4__mlxlm"]["1"] == "100.0"
    assert table["oq4__mlxlm"]["8"] == "—"
    assert table["jang__mlxlm"]["1"] == "—"
    assert table["jang__mlxlm"]["8"] == "FAIL"
    assert "| `—` | a combination no run measured |" in sweep
    assert "| `FAIL` | a measured cell that did not clear one |" in sweep


def test_a_short_measured_window_carries_its_count_into_its_sweep_entry():
    """The same marker in the sweep's tables, by the grid's own function: a column measured
    short of the pin says so where its number is rather than only in its own leaderboard."""
    def loaded_rows(count):
        """One run directory's rows as `load_run` hands them over: no pin on the rows."""
        return report.summarize(
            [
                cell_result(
                    [obs() for _ in range(count)],
                    disk_bytes=1_000_000,
                    runtime_version="mlx-lm 0.31.3",
                )
            ],
            measured=9,
        )

    runs = [
        (SWEEP_RUNS[0], run_header(("chat",), concurrency=1, measured=9), loaded_rows(4)),
        (SWEEP_RUNS[1], run_header(("chat",), concurrency=8, measured=9), loaded_rows(9)),
    ]

    table = sweep_tables(report.render_sweep(runs, varying="concurrency"))["chat"]

    assert table["oq4__mlxlm"]["1"] == "50.5 (n=4 of 9)"
    assert table["oq4__mlxlm"]["8"] == "50.5"


# The drift marker is a decode rate's movement, and a sweep's entries are the one metric the
# table is ordered by: the cache sweep published `0.487 (drift +11.5%)` beside a first-token
# latency whose cell's TTFT had not moved. So the marker rides only a rank in
# `DECODE_DERIVED_RANKS`, and every other rank prints its entries bare.


def drifting_sweep_runs():
    """Two columns of one sweep, the first carrying a cell that climbed 101 -> 202 tok/s."""
    return [
        (
            SWEEP_RUNS[0],
            run_header(("chat",), concurrency=1),
            report.summarize([drift_cell(CLIMBING, disk_bytes=1_000_000)]),
        ),
        concurrency_run(SWEEP_RUNS[1], 8),
    ]


def test_a_ttft_ranked_sweep_entry_carries_no_decode_drift_marker():
    """The reading the prompt sweep and the cache sweep are both published on. The cell is
    annotated -- its decode rate moved a hundred percent -- and the TTFT it is ordered by did
    not move at all: a marker beside that entry claims the wrong metric's movement."""
    runs = drifting_sweep_runs()

    assert "drift +100.0%" in runs[0][2][0]["drift_note"], "the fixture has to be an annotated cell"

    sweep = report.render_sweep(runs, varying="concurrency", rank="ttft_p50_s")
    table = sweep_tables(sweep)["chat"]

    assert table["oq4__mlxlm"]["1"] == "0.500"
    assert not any("drift" in entry for cells in table.values() for entry in cells.values())
    # Annotated and still ranked: the marker is gone from the entry, not the cell from the table.
    assert "FAIL" not in table["oq4__mlxlm"]["1"]
    assert "drift +100.0%" in runs[0][2][0]["drift_note"]


def test_a_decode_ranked_sweep_entry_keeps_the_drift_marker():
    """Unchanged where the figure qualifies the number: a decode-ranked sweep prints exactly what
    it printed before, marker and all."""
    runs = drifting_sweep_runs()

    sweep = report.render_sweep(runs, varying="concurrency")

    assert sweep_tables(sweep)["chat"]["oq4__mlxlm"]["1"] == "101.0 (drift +100.0%)"


def test_every_rank_the_drift_figure_does_not_qualify_prints_its_entries_bare():
    """One rule for all of them rather than one for TTFT: the marker states a decode rate's
    movement, so no rank outside `DECODE_DERIVED_RANKS` carries it."""
    runs = drifting_sweep_runs()

    assert report.DECODE_DERIVED_RANKS <= set(report.RANK_METRICS)
    for rank in report.RANK_METRICS:
        entry = sweep_tables(
            report.render_sweep(runs, varying="concurrency", rank=rank)
        )["chat"]["oq4__mlxlm"]["1"]
        if rank in report.DECODE_DERIVED_RANKS:
            assert entry.endswith("(drift +100.0%)"), rank
        else:
            assert "drift" not in entry, rank


# The grid's rule is the sweep's too: the marker is a decode rate's movement, so it rides only a
# rank in `DECODE_DERIVED_RANKS` and a table ordered on anything else prints its entries' numbers
# alone. Every published grid was rendered on the default `decode_tps`, whose entries are
# unchanged -- and the grid still joins published rows rather than re-reading them on one metric.


def drifting_grid_runs():
    """One run directory holding a cell whose decode rate climbed 101 -> 202 tok/s."""
    return [
        (
            RUN_A,
            run_header(("chat",)),
            report.summarize([drift_cell(CLIMBING, disk_bytes=1_000_000)]),
        )
    ]


def test_a_decode_ranked_grid_entry_keeps_the_drift_marker():
    """The default rank, and every published grid with it: the marker rides the decode rate it
    qualifies, which is the number this entry carries."""
    runs = drifting_grid_runs()

    assert "drift +100.0%" in runs[0][2][0]["drift_note"], "the fixture has to be an annotated cell"

    by_default = grid_tables(report.render_grid(runs))["chat"]["oq4"]["mlxlm"]
    by_name = grid_tables(report.render_grid(runs, rank="decode_tps"))["chat"]["oq4"]["mlxlm"]

    assert by_default == "101.0 (drift +100.0%)"
    assert by_name == by_default


def test_a_ttft_ranked_grid_entry_carries_no_decode_drift_marker():
    """A marker beside a first-token latency claims the wrong metric moved: the cell's decode
    rate moved a hundred percent and the TTFT it is ordered by did not move at all."""
    runs = drifting_grid_runs()

    entry = grid_tables(report.render_grid(runs, rank="ttft_p50_s"))["chat"]["oq4"]["mlxlm"]

    assert entry == "0.500"
    # Annotated and still ranked: the marker is gone from the entry, not the cell from the table.
    assert "FAIL" not in entry


def test_every_rank_the_drift_figure_does_not_qualify_prints_its_grid_entries_bare():
    """One rule for all of them rather than one for TTFT, read off the same set the sweep reads:
    no rank outside `DECODE_DERIVED_RANKS` carries the marker into a grid entry."""
    runs = drifting_grid_runs()

    assert report.DECODE_DERIVED_RANKS <= set(report.RANK_METRICS)
    for rank in report.RANK_METRICS:
        entry = grid_tables(report.render_grid(runs, rank=rank))["chat"]["oq4"]["mlxlm"]
        if rank in report.DECODE_DERIVED_RANKS:
            assert entry.endswith("(drift +100.0%)"), rank
        else:
            assert "drift" not in entry, rank


def test_the_grid_says_which_ranks_carry_the_marker():
    """The paragraph that explains the marker describes what the tables below it print: ordered
    on a non-decode metric it says the entries carry their numbers alone rather than promising a
    marker none of them carries."""
    runs = drifting_grid_runs()

    marked = report.render_grid(runs)
    bare = report.render_grid(runs, rank="ttft_p50_s")

    assert "carries its marker beside its number" in marked
    assert "carries no marker in this table" in bare
    assert "carries its marker beside its number" not in bare


def test_the_sweep_names_the_pin_in_its_title_and_every_run_directory_in_its_provenance():
    """A table that does not say what varied between its columns is the thing this project exists
    not to publish, and the block that names every column is what makes the join checkable."""
    runs = [concurrency_run(SWEEP_RUNS[0], 1), concurrency_run(SWEEP_RUNS[1], 8)]

    sweep = report.render_sweep(runs, varying="concurrency")

    title = sweep.splitlines()[0]
    assert title.startswith("# Sweep")
    assert "`concurrency`" in title

    assert "| run directory | `concurrency` |" in sweep
    assert f"| {SWEEP_RUNS[0]} | 1 |" in sweep
    assert f"| {SWEEP_RUNS[1]} | 8 |" in sweep

    # The pins the runs held in common, with the swept one named as the exception rather than
    # listed among them.
    shared = next(line for line in sweep.splitlines() if line.startswith("Pins all runs shared"))
    assert "`concurrency` the one pin they differ on" in shared
    assert "temperature `0.0`" in shared and "measured `5`" in shared
    assert "concurrency `1`" not in shared


def test_a_prompt_sweep_names_its_pin_and_where_each_column_landed():
    """A prompt pin is two numbers -- what the run asked for and what its tokenizer produced --
    and both are in the head and in the provenance, because the pin is only checkable against
    the text that was actually sent."""
    runs = [prompt_run(SWEEP_RUNS[0], 128, 126), prompt_run(SWEEP_RUNS[1], 4096, 4093)]

    sweep = report.render_sweep(runs, varying="prompt_tokens")

    assert "`prompt_tokens`" in sweep.splitlines()[0]
    assert f"| {SWEEP_RUNS[0]} | 128 (achieved 126) |" in sweep
    assert f"| {SWEEP_RUNS[1]} | 4096 (achieved 4093) |" in sweep

    shared = next(line for line in sweep.splitlines() if line.startswith("Pins all runs shared"))
    assert "`prompt_tokens` the one pin they differ on" in shared
    assert "prompt_tokens `" not in shared  # the swept pin is not one of the shared pins
    assert "Workloads all runs ran: `prefill` (max_tokens 64)." in sweep


def test_a_sweep_of_concurrency_carries_the_per_request_drift_sentence():
    runs = [concurrency_run(SWEEP_RUNS[0], 1), concurrency_run(SWEEP_RUNS[1], 8)]

    sweep = report.render_sweep(runs, varying="concurrency")

    assert DRIFT_SENTENCE in sweep
    assert report.CONCURRENCY_DRIFT_SENTENCE == DRIFT_SENTENCE


def test_a_sequential_prompt_sweep_carries_no_such_sentence():
    """At N=1 the drift beside a per-request rate is the leaderboard's ordinary one, and a
    sentence about concurrency in a sweep that ran none would be a claim about the wrong run."""
    runs = [prompt_run(SWEEP_RUNS[0], 128, 126), prompt_run(SWEEP_RUNS[1], 4096, 4093)]

    sweep = report.render_sweep(runs, varying="prompt_tokens")

    assert "At concurrency > 1" not in sweep


def test_a_prompt_sweep_driven_concurrently_carries_it_too():
    """The sentence is about the runs' concurrency rather than about which pin was swept."""
    runs = [
        prompt_run(SWEEP_RUNS[0], 128, 126, concurrency=8),
        prompt_run(SWEEP_RUNS[1], 4096, 4093, concurrency=8),
    ]

    sweep = report.render_sweep(runs, varying="prompt_tokens")

    assert DRIFT_SENTENCE in sweep


def test_the_concurrency_drift_sentence_rides_only_the_decode_ranks():
    """The sentence explains drift markers, and a rank outside `DECODE_DERIVED_RANKS` prints
    none: emitted anyway, it would explain a figure no entry in the table carries."""
    runs = [concurrency_run(SWEEP_RUNS[0], 1), concurrency_run(SWEEP_RUNS[1], 8)]

    for rank in report.RANK_METRICS:
        sweep = report.render_sweep(runs, varying="concurrency", rank=rank)
        if rank in report.DECODE_DERIVED_RANKS:
            assert DRIFT_SENTENCE in sweep, rank
        else:
            assert DRIFT_SENTENCE not in sweep, rank


def test_the_sweep_refuses_a_rank_metric_no_row_carries():
    runs = [concurrency_run(SWEEP_RUNS[0], 1), concurrency_run(SWEEP_RUNS[1], 8)]

    with pytest.raises(ValueError) as raised:
        report.render_sweep(runs, varying="concurrency", rank="vibes")

    assert "rank must be one of" in str(raised.value)


# --- the sweep on the CLI ----------------------------------------------------------------------


class SweepRuns:
    """Stands in for ``ohyesmlx.measure`` at the one call the sweep makes of it: ``load_run``.

    ``_sweep`` reads each directory exactly as ``_grid`` does -- ``load_run``, then
    ``report.summarize`` -- so what is stood in for here is the file read. The join and the
    rendering both run for real, and the run directory's own name is the label.
    """

    def __init__(self, runs):
        self.runs = runs

    def load_run(self, run_dir):
        return self.runs[Path(run_dir).name]


def measured_results(
    *, rate=100.0, runtime="mlxlm", labels=("oq4",), workload_ids=("chat",), count=5
):
    """One run directory's raw results, as ``load_run`` hands them over before ``summarize``."""
    return [
        cell_result(
            [obs(ttft=0.5, last=0.5 + 101 / rate) for _ in range(count)],
            cell_id=f"{label}__{runtime}",
            runtime=runtime,
            artifact_dir=ARTIFACTS[label],
            label=label,
            runtime_version="mlx-lm 0.31.3",
            workload_id=workload_id,
            disk_bytes=1_000_000,
        )
        for label in labels
        for workload_id in workload_ids
    ]


def sweep_days(monkeypatch, a, b):
    """Two run directories on disk as far as the CLI is concerned: one pin, two values."""
    runs = {"run-a": (a, measured_results(rate=100.0)), "run-b": (b, measured_results(rate=50.0))}
    monkeypatch.setattr(cli, "_load_measure", lambda: SweepRuns(runs))
    return runs


def test_the_sweep_command_joins_the_named_directories_and_writes_where_it_is_told(
    monkeypatch, tmp_path, capsys
):
    sweep_days(
        monkeypatch,
        run_header(("chat",), concurrency=1),
        run_header(("chat",), concurrency=8),
    )
    out = tmp_path / "sweep.md"

    code = cli.main(
        [
            "sweep",
            "--varying",
            "concurrency",
            "--rank",
            "aggregate_tps",
            "--out",
            str(out),
            "results/run-a",
            "results/run-b",
        ]
    )
    printed = capsys.readouterr().out
    written = out.read_text(encoding="utf-8")

    assert code == 0
    assert written.startswith("# Sweep — `concurrency` across 2 values in 2 run directories")
    assert written == printed[: len(written)], "the file is the document that was printed"
    assert "aggregate_tps" in written
    assert "| run-a | 1 |" in written and "| run-b | 8 |" in written
    assert str(out) in printed


def test_the_sweep_command_reads_each_runs_short_window_from_its_own_header(monkeypatch, capsys):
    """The pin is the run's, and the header is where a join reads it: a row rebuilt by
    ``load_run`` carries no pin of its own, so a sweep that renders the count at all is reading
    it from the header that run recorded."""
    runs = {
        "run-a": (
            run_header(("chat",), concurrency=1, measured=9),
            measured_results(count=4),
        ),
        "run-b": (
            run_header(("chat",), concurrency=8, measured=9),
            measured_results(count=9),
        ),
    }
    monkeypatch.setattr(cli, "_load_measure", lambda: SweepRuns(runs))

    code = cli.main(["sweep", "--varying", "concurrency", "results/run-a", "results/run-b"])
    table = sweep_tables(capsys.readouterr().out)["chat"]

    assert code == 0
    assert table["oq4__mlxlm"]["1"] == "100.0 (n=4 of 9)"
    assert table["oq4__mlxlm"]["8"] == "100.0"


def test_the_sweep_command_prints_a_guard_error_and_exits_non_zero(monkeypatch, tmp_path, capsys):
    sweep_days(
        monkeypatch,
        run_header(("chat",), concurrency=1),
        run_header(("chat",), concurrency=1),
    )
    out = tmp_path / "sweep.md"

    code = cli.main(
        [
            "sweep",
            "--varying",
            "concurrency",
            "--out",
            str(out),
            "results/run-a",
            "results/run-b",
        ]
    )
    captured = capsys.readouterr()

    assert code != 0
    assert captured.err.startswith("ohyesmlx sweep: ")
    assert "does not vary" in captured.err
    assert captured.out == ""
    assert not out.exists(), "a refused sweep wrote its file anyway"


def test_the_sweep_command_refuses_a_pin_it_does_not_know(monkeypatch, tmp_path, capsys):
    sweep_days(
        monkeypatch,
        run_header(("chat",), concurrency=1),
        run_header(("chat",), concurrency=8),
    )

    with pytest.raises(SystemExit):
        cli.main(["sweep", "--varying", "temperature", "results/run-a", "results/run-b"])

    assert capsys.readouterr().out == ""


def test_the_sweep_command_reports_a_directory_it_cannot_read(tmp_path, capsys):
    """The loader is ``_grid``'s own, so a directory that will not read is the loader's refusal
    rather than the join's -- reported the same way, through the same exit code."""
    code = cli.main(
        [
            "sweep",
            "--varying",
            "concurrency",
            str(tmp_path / "not-here"),
            str(tmp_path / "also-not-here"),
        ]
    )
    captured = capsys.readouterr()

    assert code == 2
    assert captured.err.startswith("ohyesmlx sweep: ")
    assert "not-here" in captured.err
    assert captured.out == ""


def test_the_sweep_command_takes_the_two_pins_a_sweep_may_vary():
    actions = cli._parser()._subparsers._group_actions[0].choices["sweep"]._actions
    varying = next(action for action in actions if "--varying" in action.option_strings)

    assert varying.required is True
    assert tuple(varying.choices) == report.SWEEP_PINS
