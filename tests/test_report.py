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
    # The cold visit's first warmup latency: the load a lazy loader deferred past readiness.
    first_request_s: float | None = None


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


def first_request_cell(first_request_s, *, request_seconds=ORDINARY_S, **kwargs):
    """One cell whose cold visit's first request took *first_request_s*."""
    return cell_result(
        [obs(total=request_seconds) for _ in range(5)],
        first_request_s=first_request_s,
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


# --- disk size -----------------------------------------------------------------------------


def test_dir_bytes_counts_sidecars_and_subdirectories(tmp_path):
    artifact = tmp_path / "jangtq"
    (artifact / "weights").mkdir(parents=True)
    (artifact / "model.safetensors").write_bytes(b"x" * 1000)
    (artifact / "jangtq_runtime.safetensors").write_bytes(b"y" * 500)
    (artifact / "config.json").write_bytes(b"{}")
    (artifact / "weights").mkdir(exist_ok=True)
    (artifact / "weights" / "extra.safetensors").write_bytes(b"z" * 250)

    total = report.dir_bytes(artifact)

    assert total == 1000 + 500 + 2 + 250
    assert total > 1000 + 2 + 250, "the JANGTQ sidecar must count against the format"


def test_dir_bytes_on_a_missing_directory_is_none(tmp_path):
    assert report.dir_bytes(tmp_path / "not-here") is None


def test_disk_bytes_prefers_what_measure_recorded(tmp_path):
    measured = cell_result([obs()], artifact_dir=str(tmp_path), status="PASS")
    measured.disk_bytes = 7_000_000_000

    assert report.summarize([measured])[0]["disk_bytes"] == 7_000_000_000


def test_disk_bytes_falls_back_to_walking_the_artifact_dir(tmp_path):
    (tmp_path / "model.safetensors").write_bytes(b"x" * 4096)
    (tmp_path / "jangtq_runtime.safetensors").write_bytes(b"y" * 2048)
    walked = cell_result([obs()], artifact_dir=str(tmp_path))

    assert report.summarize([walked])[0]["disk_bytes"] == 6144


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

    assert "| decode tok/s | aggregate tok/s |" in header
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

    assert flags == {"-h", "--help", "--study", "--cells", "--results-dir", "--rank"}
    assert set(subcommands.choices) == {"run"}


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
        "not evaluated",
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
        "not evaluated",
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


def test_the_fits_floor_is_reported_as_not_evaluated_and_excludes_nothing():
    """No source for a total-memory figure here, so the floor says so instead of passing."""
    row = report.summarize([cell_result([obs()])])[0]
    fits, = [floor for floor in row["floors"] if floor["floor"] == "fits"]

    assert fits["state"] == "not evaluated"
    assert "sample.py" in fits["detail"]
    assert row["rankable"] is True, "a floor nobody can ask does not exclude a row"
    assert "fits" in report.FLOORS
    assert report.FLOOR_STATES == (
        "pass",
        "fail",
        "not reached",
        "not measured",
        "not evaluated",
    )


def test_the_floors_are_pass_fail_and_never_weighted(rows):
    for row in rows:
        assert [floor["floor"] for floor in row["floors"]] == list(report.FLOORS)
        assert all(floor["state"] in report.FLOOR_STATES for floor in row["floors"])
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
    assert "| floor fits | not evaluated |" in healthy

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
