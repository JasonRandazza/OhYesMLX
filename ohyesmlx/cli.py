"""``ohyesmlx run --study runtime --cells <cell>,<cell>``.

One selector, one axis, one table. ``--cells`` is the only way to say which cells run:
there is no config-file selector, no profile, no lineup, and there will not be a second
one. Each entry is ``<format>__<runtime>=<artifact dir>`` — the ``Cell.id`` convention —
and ``--study`` says which of those two variables the run is allowed to vary. A selection
that varies both is refused before a runtime is started, because a number that changed two
things is not a result.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from ohyesmlx import report

STUDIES = report.AXES

CELLS_HELP = (
    "comma-separated cells, each `<format>__<runtime>=<artifact dir>`, "
    "e.g. oq4__mlxlm=~/.cache/huggingface/hub/models--avneetsb--gemma-4-12B-it-qat-oQ4-fp16"
)

# Pinned for v1: one prompt, one length. measure.py pins temperature 0, a fixed seed and
# the fixed 256-token output; the prompt lives here so two runs are the same two runs.
PROMPT = (
    "Explain why a benchmark that changes two variables at once cannot attribute a "
    "difference to either one. Give one concrete example."
)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns the process exit code."""
    args = _parser().parse_args(argv)
    return _run(args)


def build_cells(cell_type, spec: str) -> list:
    """``"<format>__<runtime>=<artifact dir>,..."`` -> ``[Cell(...), ...]``.

    The artifact directory is carried in the selection itself rather than looked up in a
    registry: this is the only place a cell's identity is written down, and there is
    nothing to keep in sync with the machine's disk.
    """
    cells = []
    for entry in spec.split(","):
        entry = entry.strip()
        if "=" not in entry:
            raise ValueError(
                f"cell {entry!r} has no '='; expected <format>__<runtime>=<artifact dir>"
            )

        cell_id, artifact_dir = (part.strip() for part in entry.split("=", 1))
        if "__" not in cell_id:
            raise ValueError(
                f"cell {entry!r} has no '<format>__<runtime>' id; expected "
                "<format>__<runtime>=<artifact dir>"
            )

        label, runtime = cell_id.rsplit("__", 1)
        if not label or not runtime:
            raise ValueError(f"cell id {cell_id!r} is missing its format or its runtime")
        if not artifact_dir:
            raise ValueError(f"cell {cell_id!r} has no artifact directory")

        cells.append(
            cell_type(
                id=cell_id,
                runtime=runtime,
                artifact_dir=os.path.expanduser(artifact_dir),
                label=label,
            )
        )
    return cells


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ohyesmlx",
        description="Honest benchmarks for local LLM serving on Apple Silicon. "
        "One variable at a time.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser(
        "run",
        help="measure cells and render the leaderboard",
        description="Measure cells one at a time and write results/<run-id>/results.jsonl "
        "plus a markdown leaderboard.",
    )
    run.add_argument(
        "--study",
        required=True,
        choices=STUDIES,
        help="the axis this run varies; the other variable is held constant",
    )
    run.add_argument("--cells", required=True, help=CELLS_HELP)
    run.add_argument(
        "--results-dir",
        default="results",
        help="parent of the run directory (default: results, so results/<run-id>/results.jsonl)",
    )
    return parser


def _run(args) -> int:
    measure = _load_measure()
    try:
        cells = build_cells(measure.Cell, args.cells)
        _check_axis(cells, args.study)
    except ValueError as exc:
        print(f"ohyesmlx run: {exc}", file=sys.stderr)
        return 2

    run_dir = Path(args.results_dir) / f"{_stamp()}-{args.study}"
    run_dir.mkdir(parents=True, exist_ok=True)

    results = measure.run_cells(
        cells, {"messages": [{"role": "user", "content": PROMPT}]}, results_dir=str(run_dir)
    )
    rows = report.summarize(results)

    leaderboard = report.render_markdown(rows, axis=args.study)
    (run_dir / "leaderboard.md").write_text(leaderboard, encoding="utf-8")

    print(leaderboard)
    print(f"wrote {run_dir}/results.jsonl and {run_dir}/leaderboard.md")
    return 0


def _check_axis(cells: list, study: str) -> None:
    """Refuse a selection that varies the axis' held-constant variable too."""
    if study == "runtime":
        held = {(cell.label, cell.artifact_dir) for cell in cells}
        if len(held) > 1:
            raise ValueError(
                "--study runtime holds the quantization format constant, but these cells "
                f"use {len(held)} different artifacts: "
                + ", ".join(sorted(f"{label}={path}" for label, path in held))
            )
        return

    runtimes = {cell.runtime for cell in cells}
    if len(runtimes) > 1:
        raise ValueError(
            "--study format holds the serving runtime constant, but these cells use "
            f"{len(runtimes)} different runtimes: {', '.join(sorted(runtimes))}"
        )


def _load_measure():
    """measure.py owns the loop; the CLI only asks it to run cells."""
    from ohyesmlx import measure

    return measure


def _stamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


if __name__ == "__main__":
    raise SystemExit(main())
