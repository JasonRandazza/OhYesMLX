"""Checks for `ohyesmlx canary`'s own pieces: the verdict, the cells string, the resolver.

No runtime is started, no model is loaded and nothing is fetched: ``verdict`` is handed
literal numbers, ``artifact_dir`` a temporary Hugging Face cache, and the cells string the
canary composes is handed to ``cli.build_cells`` -- the one cell selector -- to prove the
canary composes a selection rather than adding a second one. The subcommand's own wiring is
``tests/test_cli.py``.
"""

from __future__ import annotations

import json
import os

import pytest

from ohyesmlx import canary, cli, engines, measure

# The manifest's canary spec for one engine, with a baseline recorded. The two numbers are
# AC-1's literals: 70.0 tok/s and 0.40 s.
BASELINE = {
    "format": "stock4bit",
    "repo": "mlx-community/Qwen3.5-4B-4bit",
    "workload": "decode",
    "decode_tok_s": 70.0,
    "ttft_s": 0.40,
    "measured": "2026-10-29",
    "version_measured": "0.31.3",
}

# A row as `report.summarize` writes it, cut down to what the canary reads.
PASS_ROW = {
    "runtime": "mlxlm",
    "status": "PASS",
    "reason": None,
    "decode_tps": 62.0,
    "ttft_p50_s": 0.40,
}

SNAPSHOTS = (
    "0e7ffd5c629ef7719d4cbc04069232580bfa9d9c",
    "9c4d2f8e1a7b3c5d9e0f1a2b3c4d5e6f7a8b9c0d",
)


# --- AC-1: the verdict is a pure comparison ------------------------------------------------


def test_the_noise_floor_and_the_noisy_load_are_the_two_named_constants():
    """One definition each, and the numbers the plan names: the ~5% session bar of
    Decision 131 and the 4.0 load this 12-core host is allowed."""
    assert canary.NOISE_FLOOR == 0.05
    assert canary.LOAD_NOISY == 4.0


def test_a_move_inside_the_floor_is_no_effect():
    reading = canary.verdict(BASELINE, {"decode_tok_s": 68.0, "ttft_s": 0.40})

    assert reading.text == "no effect"
    assert reading.moved_pct is None
    assert reading.metric is None


def test_a_moved_decode_rate_names_its_percentage_and_its_metric():
    reading = canary.verdict(BASELINE, {"decode_tok_s": 62.0, "ttft_s": 0.40})

    assert reading.text == "moved -11.4%"
    assert reading.moved_pct == -11.4
    assert reading.metric == "decode_tok_s"


def test_a_moved_ttft_is_read_as_its_own_signed_percentage():
    reading = canary.verdict(BASELINE, {"decode_tok_s": 70.0, "ttft_s": 0.50})

    assert reading.text == "moved +25%"
    assert reading.moved_pct == 25.0
    assert reading.metric == "ttft_s"


def test_the_worst_moved_metric_names_the_verdict():
    """-2.9% on decode and +25% on TTFT is a move, and the line reports the metric that
    moved rather than the one that did not."""
    reading = canary.verdict(BASELINE, {"decode_tok_s": 68.0, "ttft_s": 0.50})

    assert reading.text == "moved +25%"
    assert reading.metric == "ttft_s"


def test_exactly_the_floor_is_no_effect_on_either_side():
    for decode_tok_s in (73.5, 66.5):  # +5.0% and -5.0% on a 70.0 baseline
        reading = canary.verdict(BASELINE, {"decode_tok_s": decode_tok_s, "ttft_s": 0.40})

        assert reading.text == "no effect", decode_tok_s


def test_the_floor_is_a_parameter_and_a_tighter_one_moves_what_was_quiet():
    reading = canary.verdict(BASELINE, {"decode_tok_s": 68.0, "ttft_s": 0.40}, floor=0.01)

    assert reading.text == "moved -2.9%"
    assert reading.metric == "decode_tok_s"


# --- AC-3: a failed cell is a FAIL line, never a number comparison ---------------------------


def test_a_cell_that_failed_the_coherence_gate_is_a_fail_line():
    row = {
        **PASS_ROW,
        "status": "FAIL",
        "reason": "incoherent output: replacement characters in 3 of 5 samples",
        "decode_tps": 71.2,
        "ttft_p50_s": 0.41,
    }

    assert canary.verdict_line(BASELINE, row) == (
        "FAIL: incoherent output: replacement characters in 3 of 5 samples"
    )


def test_a_cell_that_could_not_run_is_a_fail_line_with_its_reason():
    row = {**PASS_ROW, "status": "N/A", "reason": "runtime 'omlx' did not start: TimeoutError"}

    assert canary.verdict_line(BASELINE, row) == (
        "FAIL: runtime 'omlx' did not start: TimeoutError"
    )


def test_a_pass_row_against_a_baseline_is_the_verdict_the_plan_names():
    assert canary.verdict_line(BASELINE, PASS_ROW) == (
        "moved -11.4%: re-run the grids containing mlxlm"
    )
    assert canary.verdict_line(BASELINE, {**PASS_ROW, "decode_tps": 70.0}) == (
        "no effect on our tables"
    )


def test_a_pass_row_with_no_baseline_says_so_instead_of_comparing():
    """The shipped manifest carries null baselines until the first recorded run, and a
    comparison against nothing is not a verdict."""
    for baseline in (None, {**BASELINE, "decode_tok_s": None}, {**BASELINE, "ttft_s": None}):
        assert canary.verdict_line(baseline, PASS_ROW) == (
            "no baseline recorded: --record writes one"
        )


# --- AC-7: contention rides on the reading --------------------------------------------------


def test_a_load_above_the_constant_marks_the_reading_noisy_and_says_so():
    reading = canary.Reading("mlxlm", "no effect on our tables", "0.31.3", "0.31.3", 1.2, 4.5)

    assert reading.noisy is True
    assert reading.line() == (
        "mlxlm: no effect on our tables  "
        "[version 0.31.3 -> 0.31.3; load 1.2 -> 4.5, noisy: above 4.0]"
    )


def test_a_load_at_the_constant_is_not_noisy():
    """The rule is "exceeds": exactly 4.0 is the machine this host is allowed to be."""
    reading = canary.Reading("mlxlm", "no effect on our tables", None, "0.32.2", 2.0, 4.0)

    assert reading.noisy is False
    assert "noisy" not in reading.line()
    assert "version unrecorded -> 0.32.2" in reading.line()


def test_the_load_reads_the_one_minute_average(monkeypatch):
    monkeypatch.setattr(canary.os, "getloadavg", lambda: (3.25, 2.0, 1.0))

    assert canary.load() == 3.25


# --- the artifact resolver ------------------------------------------------------------------


def snapshot(root, index, *, config=True):
    """One HF-cache snapshot directory for the stock4bit repo, config.json and all."""
    path = root / "models--mlx-community--Qwen3.5-4B-4bit" / "snapshots" / SNAPSHOTS[index]
    path.mkdir(parents=True)
    if config:
        (path / "config.json").write_text("{}", encoding="utf-8")
    return path


def test_the_artifact_is_the_newest_snapshot_that_carries_a_config(tmp_path):
    older = snapshot(tmp_path, 0)
    newer = snapshot(tmp_path, 1)
    os.utime(older / "config.json", (1_000, 1_000))

    assert canary.artifact_dir("mlx-community/Qwen3.5-4B-4bit", tmp_path) == str(newer)


def test_a_snapshot_without_a_config_json_is_not_an_artifact(tmp_path):
    real = snapshot(tmp_path, 0)
    configless = snapshot(tmp_path, 1, config=False)
    os.utime(configless, (4_000_000_000, 4_000_000_000))  # newest, and still not a model

    assert canary.artifact_dir("mlx-community/Qwen3.5-4B-4bit", tmp_path) == str(real)


def test_a_repo_with_no_snapshot_is_refused_naming_the_repo_and_the_cache(tmp_path):
    with pytest.raises(ValueError) as raised:
        canary.artifact_dir("RepublicOfKorokke/Qwen3.5-4B-oQ4", tmp_path)

    assert "RepublicOfKorokke/Qwen3.5-4B-oQ4" in str(raised.value)
    assert "models--RepublicOfKorokke--Qwen3.5-4B-oQ4" in str(raised.value)


# --- AC-2: the cells string is the one selector ---------------------------------------------


def test_the_cells_string_the_canary_composes_is_accepted_by_build_cells(tmp_path):
    path = snapshot(tmp_path, 0)

    spec = canary.cells("mlxlm", BASELINE, tmp_path)

    assert spec == f"stock4bit__mlxlm={path}"
    cells = cli.build_cells(measure.Cell, spec)
    assert [(cell.id, cell.runtime, cell.label, cell.artifact_dir) for cell in cells] == [
        ("stock4bit__mlxlm", "mlxlm", "stock4bit", str(path))
    ]


# --- AC-4: recording writes the baseline and adopts nothing else -----------------------------


def write_manifest(tmp_path, payload=None):
    path = tmp_path / "engines-tested.json"
    path.write_text(json.dumps(payload or engines.MANIFEST, indent=2), encoding="utf-8")
    return path


def test_recording_writes_the_baseline_and_leaves_the_tested_version_alone(tmp_path):
    path = write_manifest(tmp_path)

    canary.record(
        path,
        "optiq",
        decode_tok_s=75.3,
        ttft_s=0.42,
        version_measured="0.7.8",
        measured="2026-10-30",
    )
    written = json.loads(path.read_text(encoding="utf-8"))

    assert written["optiq"]["canary"] == {
        "format": "stock4bit",
        "repo": "mlx-community/Qwen3.5-4B-4bit",
        "workload": "decode",
        "decode_tok_s": 75.3,
        "ttft_s": 0.42,
        "measured": "2026-10-30",
        "version_measured": "0.7.8",
    }
    # A baseline measured on 0.7.8 does not make 0.7.8 the tested version: that is a
    # decision someone takes after reading this line.
    assert written["optiq"]["version"] == "0.5.13"
    assert written["optiq"]["verified"] == "2026-10-29"
    assert engines.load_manifest(path) == written


def test_recording_one_engine_leaves_every_other_entry_byte_identical(tmp_path):
    path = write_manifest(tmp_path)
    before = json.loads(path.read_text(encoding="utf-8"))

    canary.record(
        path,
        "mlxlm",
        decode_tok_s=70.0,
        ttft_s=0.40,
        version_measured="0.31.3",
        measured="2026-10-30",
    )
    after = json.loads(path.read_text(encoding="utf-8"))

    assert {name: entry for name, entry in after.items() if name != "mlxlm"} == {
        name: entry for name, entry in before.items() if name != "mlxlm"
    }
