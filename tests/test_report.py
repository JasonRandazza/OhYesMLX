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

from ohyesmlx import cli, report

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
):
    """A cell as measure.py will hand it over."""
    return FakeCellResult(
        cell=FakeCell(cell_id, runtime, artifact_dir, label),
        status=status,
        reason=reason,
        observations=list(observations),
        cold_load_s=cold_load_s,
        memory={"peak_mb": 9150.0} if memory is None else memory,
        runtime_version=runtime_version,
        disk_bytes=disk_bytes,
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

    assert flags == {"-h", "--help", "--study", "--cells", "--results-dir"}
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
