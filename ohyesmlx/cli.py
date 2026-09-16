"""``ohyesmlx run --study runtime --cells <cell>,<cell> [--rank <metric>]``.

One selector, one axis, one table per workload, one named ordering metric. ``--cells`` is the
only way to say which cells run: there is no config-file selector, no profile, no lineup, and
there will not be a second one. Each entry is ``<format>__<runtime>=<artifact dir>`` — the
``Cell.id`` convention — and ``--study`` says which of those two variables the run is allowed
to vary. A selection that varies both is refused before a runtime is started, because a number
that changed two things is not a result.

``--rank`` picks the single metric the tables are ordered by, and there is no blend of them:
weighting a second of latency against a megabyte has no objective answer, so the ordering
names its metric and the metric card carries every number behind it.
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

# Pinned for v1: three workload shapes, and no more. One shape measures one corner of the
# space, and a column keyed by shape is the only honest way to publish them: prefill-heavy and
# decode-heavy work can have different winners, so a figure averaged across shapes describes
# no shape that was ever run. measure.py pins temperature 0 and a fixed seed; the prompts and
# the output caps live here so two runs are the same two runs.
#
# `chat` is the short prompt with a 128-token cap: latency and per-request overhead.
PROMPT = (
    "Explain why a benchmark that changes two variables at once cannot attribute a "
    "difference to either one. Give one concrete example."
)

# `prefill` is the long prompt with a 64-token cap: prompt-processing throughput. The excerpt
# below is 6,485 characters, roughly 1,600 tokens at four characters per token and ~12x the
# `chat` prompt. That is what makes it dominate the request: at a 400 tok/s prefill engine the
# prompt path is about 4 s, so fixed per-request overhead is a couple of percent of TTFT
# instead of a third of it, and `prompt_tokens / ttft_s` measures prompt processing rather
# than the cost of asking. A longer prompt would buy a fraction of a percent that a 5-sample
# median cannot resolve, at ~1.5 s more prefill on each of the 16 prefill requests a cell
# makes in a run. A read-and-answer task rather than a generative one, so the 64-token cap is
# enough to answer it coherently.
PREFILL_PROMPT = (
    "Read the engineering standard below in full, then answer the question at the end in "
    "one sentence.\n\n"
    "--- BEGIN EXCERPT: Measurement Standard MS-7 ---\n\n"
    "1. Scope. This standard governs every performance figure this organisation publishes "
    "about software it runs on hardware it owns, whether that figure appears in a changelog, "
    "a design review, a sales deck, or a comment in a source file. It applies to latency, "
    "throughput, memory, disk, cost, and every derived ratio built from them. A figure that "
    "cannot be traced to a run recorded under this standard is not evidence, and quoting one "
    "as though it were is a breach of the standard rather than an oversight in it.\n\n"
    "2. The single-variable rule. A comparison varies exactly one thing. Every other input "
    "that can move the measurement is pinned and written down: the software version, the "
    "hardware, the operating system, the model or data set, the request shape, the number of "
    "repetitions, the seeding, the cache state, and the ambient conditions where they matter. "
    "If two things differ between the runs being compared, the comparison answers no question "
    "at all, because any difference observed could belong to either variable and nothing in "
    "the numbers can apportion it between them.\n\n"
    "3. Why the rule is not negotiable. The rule is not a matter of taste or of neatness. It "
    "is what makes a difference attributable. A benchmark that moves two things at once "
    "produces a number that is real, reproducible, and useless: real because the machine did "
    "the work it did, reproducible because a rerun moves the same two things again, and "
    "useless because the reader cannot act on it. The reader's question is always which of two "
    "choices to make, and a figure that cannot separate the choices cannot answer it.\n\n"
    "4. Pinning. Everything held constant is recorded with the run rather than remembered by "
    "the person who ran it. A pin that lives only in someone's head is not a pin; it is a "
    "detail that will differ next month without anyone noticing. Recorded pins include the "
    "exact build, the exact weights including the file digest where one exists, the hardware "
    "model and its memory configuration, the power source as well as the charge state, and the "
    "version of every tool in the measurement path, because a runtime that ships a different "
    "default changes the result without changing a single flag in the command.\n\n"
    "5. Ordering and drift. The order in which configurations are measured is itself an input, "
    "so it is chosen deliberately and never left as the order they happen to be listed in. A "
    "machine that heats up under sustained load will report its first configuration cool and "
    "its last one throttled, which turns a thermal curve into a property of the software with "
    "no warning anywhere in the output. Configuration order is therefore interleaved or "
    "reversed between repetitions, cool-down periods are inserted between them and recorded, "
    "and the drift across the measurement window is kept as a number so a reader can see "
    "whether the window moved underneath the result.\n\n"
    "6. Repetition and distribution. A single request is an anecdote. Reported latency figures "
    "are percentiles with the count they were taken over, never a bare mean, because a mean "
    "hides exactly the queueing behaviour a reader is trying to understand. Where there are "
    "too few samples for a percentile to mean anything, the percentile is omitted and the "
    "count is printed instead of being estimated from three values. Throughput is reported per "
    "request and in aggregate as two separate numbers, since batching improves one and can "
    "worsen the other, and one figure cannot say both.\n\n"
    "7. Cold start. Model load time is its own measurement and is never folded into the first "
    "request. Loading weights from disk, mapping them, and compiling kernels are work that "
    "happens once, and a first-request figure that includes them describes a startup path "
    "rather than a serving path. Cold load is reported separately, alongside a warm-start "
    "figure where one was measured, and a run that reports only the cold case says so in the "
    "same sentence.\n\n"
    "8. Self-reported numbers. A number a server reports about itself is not a measurement. "
    "Servers report durations that were never instrumented, throughput computed from counters "
    "that restart, and token counts rounded to whatever their tokenizer happened to produce. "
    "Such numbers are kept as provenance, labelled as the server's own claim, and never used "
    "as the value in a table. Where a client-side and a server-side figure disagree, the "
    "disagreement is itself evidence and is published rather than smoothed away.\n\n"
    "9. Missing values. A metric that cannot be computed is reported as missing, with the "
    "reason, and never as zero. A zero is a measurement and will be read as one. If a stream "
    "delivered too few deltas for an interval to exist, the interval is undefined rather than "
    "tiny; if a token count is unavailable, the rate is unavailable with it. Printing a "
    "placeholder where a number belongs is how a table of blanks comes to look like a table of "
    "results.\n\n"
    "10. Raw records. Every run keeps its raw observations, including the ones that failed, "
    "the warmups, and the sample that produced the anomaly being investigated later. A summary "
    "is recomputable from the raw record or it is not a summary. Derived values are never "
    "stored beside the fields they were derived from, because two copies of one metric will "
    "eventually disagree and there will be no way to tell which one is right. Retention is not "
    "negotiable on the grounds of size: the record is small next to the cost of re-running a "
    "measurement window that has already passed.\n\n"
    "11. Grouping. A figure belongs to one configuration and one workload. Two configurations "
    "share a table only when the run varied one thing between them; two workloads share a "
    "table only when a reader can tell the workloads apart. Averaging across either grouping "
    "produces a number describing something that was never run, and that number will be quoted "
    "for years because it looks tidy. When in doubt, print more tables rather than fewer, and "
    "let each one say what it varied.\n\n"
    "12. Publication. Every published figure carries the caveat naming what it held constant, "
    "so a reader knows what it cannot claim. A table without that line is not a result, "
    "whatever the numbers in it say. Corrections are published with the same prominence as the "
    "original figure, since a wrong number that has been read once has already done its "
    "damage.\n\n"
    "--- END EXCERPT ---\n\n"
    "Question: which single rule does the standard treat as non-negotiable, and why?"
)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns the process exit code."""
    args = _parser().parse_args(argv)
    if args.command == "grid":
        return _grid(args)
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


def workloads(measure) -> list:
    """The three pinned shapes, built against the measure module the run will use.

    Pinned as literals and pinned to three: there is no config file and no flag that adds a
    fourth. `chat` and `decode` send the same prompt and differ only in the output cap, which
    is the point — one measures per-request latency, the other sustained generation.
    """
    return [
        measure.Workload(
            id="chat", messages=[{"role": "user", "content": PROMPT}], max_tokens=128
        ),
        measure.Workload(
            id="prefill", messages=[{"role": "user", "content": PREFILL_PROMPT}], max_tokens=64
        ),
        measure.Workload(
            id="decode", messages=[{"role": "user", "content": PROMPT}], max_tokens=512
        ),
    ]


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
        "--rank",
        default=report.DEFAULT_RANK,
        choices=tuple(report.RANK_METRICS),
        metavar="METRIC",
        help="the one metric each table is ordered by; lower-is-better metrics sort "
        f"ascending (default: {report.DEFAULT_RANK}). There is no blended score.",
    )
    run.add_argument(
        "--concurrency",
        type=int,
        default=1,
        metavar="N",
        help="requests issued together per batch (default: 1). `--measured` counts BATCHES, so "
        "at N=8 a run of 9 makes 72 requests. A sweep is several runs differing only in this "
        "pin, joined afterwards; it is not a second cell selector and not a third --study axis.",
    )
    run.add_argument(
        "--results-dir",
        default="results",
        help="parent of the run directory (default: results, so results/<run-id>/results.jsonl)",
    )

    grid = commands.add_parser(
        "grid",
        help="join run directories into one grid",
        description="Join finished run directories into one grid: formats down, runtimes "
        "across. Measures nothing and starts no runtime -- it reads results.jsonl files "
        "that already exist.",
    )
    grid.add_argument(
        "run_dirs",
        nargs="+",
        metavar="RUN-DIR",
        help="the run directories to join, named one by one. There is no glob and no "
        "--all: results/ accumulates runs from every session, and a grid assembled by "
        "wildcard would silently join columns that never belonged together.",
    )
    grid.add_argument(
        "--rank",
        default=report.DEFAULT_RANK,
        choices=tuple(report.RANK_METRICS),
        metavar="METRIC",
        help=f"the one metric each grid entry carries (default: {report.DEFAULT_RANK})",
    )
    grid.add_argument(
        "--out",
        default=None,
        help="also write the grid here (default: stdout only)",
    )
    return parser


def _grid(args) -> int:
    """Join the named run directories and render the grid.

    The join guards live in report.render_grid, not here: refusing to join two runs that
    disagree is a statement about the data, and the CLI is not where that is decided.
    """
    measure = _load_measure()
    runs = []
    for run_dir in args.run_dirs:
        try:
            header, results = measure.load_run(run_dir)
        except (OSError, ValueError) as exc:
            print(f"ohyesmlx grid: {run_dir}: {exc}", file=sys.stderr)
            return 2
        runs.append((Path(run_dir).name, header, report.summarize(results)))

    try:
        grid = report.render_grid(runs, rank=args.rank)
    except ValueError as exc:
        print(f"ohyesmlx grid: {exc}", file=sys.stderr)
        return 2

    print(grid)
    if args.out:
        Path(args.out).write_text(grid, encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


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
        cells, workloads(measure), concurrency=args.concurrency, results_dir=str(run_dir)
    )
    rows = report.summarize(results)

    leaderboard = report.render_markdown(rows, axis=args.study, rank=args.rank)
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
