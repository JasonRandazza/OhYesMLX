"""055-04: `canary --repeat N` -- N interleaved visits per engine, the median as the reading.

No runtime, no model, no HTTP and no shipped manifest. ``measure`` is faked at the CLI's one
seam and answers each visit with a real ``CellResult``, because the row the canary reduces is
``report.summarize``'s -- the same fake pattern the canary tests in ``test_cli.py`` use,
repeated here because those drive one visit per engine and these drive N. ``canary.load`` is a
plan of readings, detection is a stub, and the manifest a recording run writes is a tmp copy.
"""

from __future__ import annotations

import argparse
import dataclasses
import json

import pytest

from ohyesmlx import canary, cli


@dataclasses.dataclass(frozen=True)
class FakeCell:
    """``measure.Cell``'s shape: ``build_cells`` builds these and the CLI forwards them."""

    id: str
    runtime: str
    artifact_dir: str
    label: str


@dataclasses.dataclass(frozen=True)
class FakeWorkload:
    """``measure.Workload``'s shape: the CLI builds these and forwards them."""

    id: str
    messages: list
    max_tokens: int


class FakeMeasure:
    """The ``run_cells`` calls the CLI makes, recorded. No runtime, no results, no file."""

    Cell = FakeCell
    Workload = FakeWorkload

    def __init__(self):
        self.calls = []

    def run_cells(self, cells, workloads, **kwargs):
        raise AssertionError("the fake was not armed")


def cell_result(cell, *, status="PASS", reason=None, tokens=62, ttft_s=0.40):
    """One decode row: ``tokens`` completion tokens over a 1.0 s content window."""
    from ohyesmlx import measure, transport

    observation = transport.Observation(
        ok=True,
        error=None,
        ttft_s=ttft_s,
        last_content_s=ttft_s + 1.0,
        total_s=ttft_s + 1.0,
        prompt_tokens=32,
        completion_tokens=tokens,
        reasoning_tokens=None,
        content_event_count=2,
        text="A measured answer.",
        token_source="usage",
    )
    return measure.CellResult(
        cell=cell,
        workload_id="decode",
        status=status,
        reason=reason,
        observations=[observation],
        batch_spans=[],
        warmup_observations=[],
        warmup_plateau=True,
        cold_load_s=1.0,
        first_request_s=None,
        first_request_workload_id=None,
        memory={},
        runtime_version="0.31.3",
        disk_bytes=None,
    )


def fake_measure(monkeypatch, *, tokens=(62,), ttfts=(0.40,), statuses=None, reasons=None):
    """Arm the fake with a per-visit plan: an engine's k-th visit reads ``tokens[k]``.

    The plan is cycled, so a test that cares about one visit passes one value.
    """
    fake = FakeMeasure()

    def run_cells(cells, workloads, **kwargs):
        cell = cells[0]
        rep = sum(1 for call in fake.calls if call["cells"][0].runtime == cell.runtime)
        fake.calls.append({"cells": cells, "workloads": workloads, **kwargs})
        return [
            cell_result(
                cell,
                status=(statuses or {}).get(rep, "PASS"),
                reason=(reasons or {}).get(rep),
                tokens=tokens[rep % len(tokens)],
                ttft_s=ttfts[rep % len(ttfts)],
            )
        ]

    fake.run_cells = run_cells
    monkeypatch.setattr(cli, "_load_measure", lambda: fake)
    monkeypatch.setattr(cli.canary, "artifact_dir", lambda repo, root=None: f"/models/{repo}")
    return fake


def fake_detect(monkeypatch, *, versions=None):
    from ohyesmlx import engines

    versions = versions or {}
    monkeypatch.setattr(
        engines,
        "detect_all",
        lambda env=None: [
            engines.EngineStatus(
                name=name,
                title=name,
                blurb="",
                installed=True,
                version=versions.get(name, "0.31.3"),
                path=f"/bin/{name}",
                tested=True,
                verified="2026-10-29",
                install=None,
            )
            for name in engines.ONBOARDING_ENGINES
        ],
    )


def fake_baseline(monkeypatch, name="mlxlm", decode_tok_s=70.0, ttft_s=0.40):
    from ohyesmlx import engines

    entry = engines.MANIFEST[name]
    monkeypatch.setitem(
        engines.MANIFEST,
        name,
        {
            **entry,
            "canary": {
                **entry["canary"],
                "decode_tok_s": decode_tok_s,
                "ttft_s": ttft_s,
                "measured": "2026-10-29",
                "version_measured": "0.31.3",
            },
        },
    )


def fake_load(monkeypatch, plan):
    """The 1-minute load average, read in order from *plan* -- two reads per visit."""
    readings = iter(plan)
    monkeypatch.setattr(cli.canary, "load", lambda: next(readings))


def tmp_manifest(monkeypatch, tmp_path):
    """Point the manifest a recording run writes at a copy, never the shipped one."""
    from ohyesmlx import engines

    path = tmp_path / "engines-tested.json"
    path.write_text(json.dumps(engines.MANIFEST, indent=2), encoding="utf-8")
    monkeypatch.setattr(engines, "MANIFEST_PATH", path)
    return path


def row(decode_tps=62.0, ttft_p50_s=0.40, *, status="PASS", reason=None):
    """``report.summarize``'s row, narrowed to the keys ``median_reading`` reads."""
    return {
        "status": status,
        "reason": reason,
        "decode_tps": decode_tps,
        "ttft_p50_s": ttft_p50_s,
    }


# --- AC-1: repeat, interleaved, median -------------------------------------------------------


def test_the_reps_go_on_the_outer_loop_and_every_visit_gets_its_own_run_dir(monkeypatch):
    fake = fake_measure(monkeypatch)
    fake_detect(monkeypatch)
    fake_load(monkeypatch, [1.0] * 12)

    assert cli.main(["canary", "--yes", "--engines", "mlxlm,optiq", "--repeat", "3"]) == 0

    # a1 b1 a2 b2 a3 b3: the whole engine list is visited before any engine is revisited.
    assert [call["cells"][0].runtime for call in fake.calls] == ["mlxlm", "optiq"] * 3
    dirs = [call["results_dir"] for call in fake.calls]
    assert len(set(dirs)) == 6, "two visits shared a run directory"
    expected = [f"-{name}-r{rep}" for rep in (1, 2, 3) for name in ("mlxlm", "optiq")]
    assert all(path.endswith(suffix) for path, suffix in zip(dirs, expected))


def test_one_line_per_engine_and_it_is_the_median_of_its_visits(monkeypatch, capsys):
    fake_measure(monkeypatch, tokens=(60, 62, 70), ttfts=(0.40, 0.44, 0.42))
    fake_detect(monkeypatch)
    fake_baseline(monkeypatch)
    fake_load(monkeypatch, [1.0] * 8)

    assert cli.main(["canary", "--yes", "--engines", "mlxlm", "--repeat", "3"]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    # The medians are 62 tok/s and 0.42 s against 70 and 0.40: -11.4% is the worst move. The
    # first visit alone would read -14.3% and the last one no effect at all.
    assert lines[0].startswith(
        "mlxlm: moved -11.4%: re-run the grids containing mlxlm"
    )


def test_repeat_one_is_todays_output_and_todays_run_dir(monkeypatch, capsys):
    fake = fake_measure(monkeypatch)
    fake_detect(monkeypatch)
    fake_baseline(monkeypatch)
    fake_load(monkeypatch, [1.0] * 8)

    assert cli.main(["canary", "--yes", "--engines", "mlxlm"]) == 0
    today = capsys.readouterr().out

    assert cli.main(["canary", "--yes", "--engines", "mlxlm", "--repeat", "1"]) == 0
    once = capsys.readouterr().out

    assert once == today
    assert all(call["results_dir"].endswith("-mlxlm") for call in fake.calls)


@pytest.mark.parametrize("value", ["0", "-2"])
def test_repeat_below_one_is_refused_before_anything_is_measured(
    monkeypatch, capsys, value
):
    fake = fake_measure(monkeypatch)
    fake_detect(monkeypatch)

    assert cli.main(["canary", "--yes", "--engines", "mlxlm", "--repeat", value]) == 2

    assert fake.calls == []
    err = capsys.readouterr().err
    assert "--repeat" in err and "at least 1" in err


# --- AC-2: what counts -----------------------------------------------------------------------


def test_a_rep_that_did_not_pass_fails_the_engine_and_names_it(
    monkeypatch, capsys, tmp_path
):
    fake_measure(
        monkeypatch,
        statuses={1: "FAIL"},
        reasons={1: "incoherent output: replacement characters"},
    )
    fake_detect(monkeypatch)
    fake_baseline(monkeypatch)
    fake_load(monkeypatch, [1.0] * 8)
    path = tmp_manifest(monkeypatch, tmp_path)
    before = path.read_text(encoding="utf-8")

    assert cli.main(
        ["canary", "--yes", "--engines", "mlxlm", "--repeat", "3", "--record"]
    ) == 0

    out = capsys.readouterr().out
    assert "mlxlm: FAIL: rep 2: incoherent output: replacement characters" in out
    assert out.count("mlxlm:") == 1
    assert "not recorded: the cell did not PASS" in out
    assert path.read_text(encoding="utf-8") == before


def test_a_visit_the_runtime_cannot_start_aborts_that_engine_and_names_the_rep(
    monkeypatch, capsys, tmp_path
):
    fake = fake_measure(monkeypatch)
    tried = {}

    def run_cells(cells, workloads, **kwargs):
        name = cells[0].runtime
        tried[name] = tried.get(name, 0) + 1
        fake.calls.append({"cells": cells, "workloads": workloads, **kwargs})
        if name == "mlxlm" and tried[name] == 2:
            raise ValueError("no Hugging Face snapshot of the model can be served")
        return [cell_result(cells[0])]

    fake.run_cells = run_cells
    fake_detect(monkeypatch)
    fake_baseline(monkeypatch)
    fake_load(monkeypatch, [1.0] * 12)
    path = tmp_manifest(monkeypatch, tmp_path)
    before = path.read_text(encoding="utf-8")

    assert cli.main(
        ["canary", "--yes", "--engines", "mlxlm,optiq", "--repeat", "3", "--record"]
    ) == 2

    captured = capsys.readouterr()
    assert "rep 2" in captured.err
    assert "no Hugging Face snapshot" in captured.err
    # The engine that lost a visit gets no verdict from the visits that ran; the other one
    # is unaffected and still gets its three.
    assert "mlxlm:" not in captured.out
    assert "optiq:" in captured.out
    assert [call["cells"][0].runtime for call in fake.calls] == [
        "mlxlm",
        "optiq",
        "mlxlm",
        "optiq",
        "optiq",
    ]
    recorded = json.loads(path.read_text(encoding="utf-8"))
    assert "runs" not in recorded["mlxlm"]["canary"]
    assert len(recorded["optiq"]["canary"]["runs"]) == 3
    assert path.read_text(encoding="utf-8") != before


def test_a_load_above_the_constant_around_any_rep_makes_the_engine_noisy(
    monkeypatch, capsys, tmp_path
):
    fake_measure(monkeypatch)
    fake_detect(monkeypatch)
    fake_baseline(monkeypatch)
    # Rep 2 ran on a busy machine; reps 1 and 3 were quiet.
    fake_load(monkeypatch, [1.0, 1.0, 5.0, 5.0, 1.0, 1.0])
    path = tmp_manifest(monkeypatch, tmp_path)
    before = path.read_text(encoding="utf-8")

    assert cli.main(
        ["canary", "--yes", "--engines", "mlxlm", "--repeat", "3", "--record"]
    ) == 0
    out = capsys.readouterr().out
    assert "noisy: above 4.0" in out
    assert "not recorded" in out
    assert path.read_text(encoding="utf-8") == before

    fake_load(monkeypatch, [1.0, 1.0, 5.0, 5.0, 1.0, 1.0])
    assert cli.main(
        [
            "canary",
            "--yes",
            "--engines",
            "mlxlm",
            "--repeat",
            "3",
            "--record",
            "--allow-noisy",
        ]
    ) == 0
    recorded = json.loads(path.read_text(encoding="utf-8"))["mlxlm"]["canary"]
    assert recorded["decode_tok_s"] == pytest.approx(62.0)


# --- AC-3: record keeps the readings ---------------------------------------------------------


def test_record_writes_the_medians_and_the_n_readings_in_rep_order(
    monkeypatch, tmp_path
):
    fake_measure(monkeypatch, tokens=(60, 62, 70), ttfts=(0.40, 0.44, 0.42))
    fake_detect(monkeypatch, versions={"mlxlm": "0.32.2"})
    fake_baseline(monkeypatch)
    fake_load(monkeypatch, [1.0] * 8)
    path = tmp_manifest(monkeypatch, tmp_path)

    assert cli.main(
        ["canary", "--yes", "--engines", "mlxlm", "--repeat", "3", "--record"]
    ) == 0

    written = json.loads(path.read_text(encoding="utf-8"))["mlxlm"]["canary"]
    assert written["decode_tok_s"] == pytest.approx(62.0)
    assert written["ttft_s"] == pytest.approx(0.42)
    assert written["version_measured"] == "0.32.2"
    runs = written["runs"]
    assert all(set(entry) == {"decode_tok_s", "ttft_s"} for entry in runs)
    assert [entry["decode_tok_s"] for entry in runs] == pytest.approx([60.0, 62.0, 70.0])
    assert [entry["ttft_s"] for entry in runs] == pytest.approx([0.40, 0.44, 0.42])


def test_record_with_one_rep_writes_one_run(monkeypatch, tmp_path):
    fake_measure(monkeypatch)
    fake_detect(monkeypatch)
    fake_baseline(monkeypatch)
    fake_load(monkeypatch, [1.0] * 4)
    path = tmp_manifest(monkeypatch, tmp_path)

    assert cli.main(["canary", "--yes", "--engines", "mlxlm", "--record"]) == 0

    written = json.loads(path.read_text(encoding="utf-8"))["mlxlm"]["canary"]
    runs = written["runs"]
    assert len(runs) == 1
    assert set(runs[0]) == {"decode_tok_s", "ttft_s"}
    assert runs[0]["decode_tok_s"] == pytest.approx(62.0)
    assert runs[0]["ttft_s"] == pytest.approx(0.40)


def test_median_reading_takes_the_median_of_each_metric():
    reading = canary.median_reading([row(60.0, 0.40), row(62.0, 0.44), row(70.0, 0.42)])

    assert reading.failure is None
    assert reading.decode_tok_s == 62.0
    assert reading.ttft_s == 0.42


def test_median_reading_of_an_even_count_is_the_midpoint_of_the_middle_two():
    reading = canary.median_reading([row(60.0, 0.40), row(70.0, 0.42)])

    assert reading.decode_tok_s == 65.0
    assert reading.ttft_s == pytest.approx(0.41)


def test_median_reading_is_a_fail_naming_the_first_rep_that_did_not_pass():
    reading = canary.median_reading(
        [
            row(status="FAIL", reason="incoherent output: replacement characters"),
            row(62.0, 0.40),
            row(status="FAIL", reason="the engine returned no content"),
        ]
    )

    assert reading.failure == "FAIL: rep 1: incoherent output: replacement characters"
    assert reading.decode_tok_s is None
    assert reading.ttft_s is None


def test_median_reading_of_one_visit_is_a_fail_without_a_rep_number():
    # A one-visit line is the line today's canary prints: there is no second rep that "rep 1"
    # could distinguish it from, and the existing canary tests pin that text.
    reading = canary.median_reading(
        [row(status="FAIL", reason="incoherent output: replacement characters")]
    )

    assert reading.failure == "FAIL: incoherent output: replacement characters"


def test_median_reading_leaves_a_metric_a_rep_left_undefined_undefined():
    reading = canary.median_reading([row(None, 0.40), row(62.0, 0.44), row(70.0, 0.42)])

    assert reading.failure is None
    assert reading.decode_tok_s is None
    assert reading.ttft_s == 0.42


def test_record_without_runs_writes_no_runs_key(tmp_path):
    from ohyesmlx import engines

    path = tmp_path / "engines-tested.json"
    path.write_text(json.dumps(engines.MANIFEST, indent=2), encoding="utf-8")

    canary.record(
        path,
        "optiq",
        decode_tok_s=75.3,
        ttft_s=0.42,
        version_measured="0.7.8",
        measured="2026-10-30",
    )

    entry = json.loads(path.read_text(encoding="utf-8"))["optiq"]["canary"]
    assert "runs" not in entry
    assert entry["decode_tok_s"] == 75.3


def test_the_repeat_help_text_recommends_three_for_record():
    parser = cli._parser()
    subparsers = next(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    repeat = next(
        action
        for action in subparsers.choices["canary"]._actions
        if action.dest == "repeat"
    )

    assert "--repeat 3" in repeat.help
    assert "--record" in repeat.help


def test_the_docs_say_what_repeat_does_one_sentence_each():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent

    assert "--repeat 3" in (root / "README.md").read_text(encoding="utf-8")
    assert "--repeat 3" in (root / "docs/interfaces/v5-onboarding.md").read_text(
        encoding="utf-8"
    )
