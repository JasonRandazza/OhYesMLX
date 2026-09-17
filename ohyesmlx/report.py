"""Join measure's raw numbers into one row per cell and one leaderboard.

The metric formulas are the ones pinned in ``docs/interfaces.md``, not re-derived here::

    decode_tps  = completion_tokens / (last_content_s - ttft_s)
    prefill_tps = prompt_tokens / ttft_s
    itl_s       = (last_content_s - ttft_s) / max(1, completion_tokens - 1)

``decode_tps`` is a per-request rate and ``aggregate_tps`` is a cell-wide one. They stay
separate fields because continuous batching wins one and loses the other, and one number
cannot say both.

``first_request_s`` is the cold visit's first warmup latency, and it stays a column of its
own. It is where a runtime that loads its weights lazily pays for them — ``cold_load_s`` is
only a time-to-listening for one of those — so a reader who cannot see it reads a whole load
as warm-up noise. It is never added to ``cold_load_s`` here either: the contract says a
cross-runtime load comparison uses the sum, not that the harness publishes it. The column is
the visit's and every row of the cell prints it; the deferred-load note is not, because it
reads that one number against the requests *this row* measured, and one request belongs to
one workload. Only the shape that ran first can say the gap is a load.

``drift`` is the counterweight to the ordering the tables print. ``measure.measured_drift``
compares the median decode rate of the first half of a cell's measured requests against the
second half's, and the row prints the change beside the decode rate it qualifies — a cell that
moved 28% across its own window and one that moved 0.5% are otherwise indistinguishable, and
on the format axis that difference lands on the formats rather than on the run. Both signs are
findings: a negative one is a cell that slowed as it ran, the thermal curve the interleave
exists to expose, and a positive one is a cell that had not finished warming up, so the rate
it published is an early-window rate. Neither is a floor — a still-moving cell is ranked with
the rest and annotated — because the row that says the window was too short is the row that
must not be thrown away.

A cell that landed fewer measured batches than the run pinned is the same shape of finding as
a drifting one, and gets the same treatment: the pin comes from the run header, the row carries
a note, and the grid and the sweep print the count beside the number. It is not a floor and not
a status either — a row short of its pin was still measured, and failing it would delete the one
row that says the window was short.

Percentiles need samples to be percentiles. Below five, ``ttft_p90_s`` and ``ttft_p99_s``
are ``None`` and the row carries an ``n=<k>`` note, because a p95 built from two values is
not a p95.

A rate needs an interval to be a rate. ``decode_tps`` and ``itl_s`` are ``None`` for a
request whose stream delivered fewer than two content deltas, and ``delta_note`` says so:
with one delta the first content delta *is* the whole response, so there is no inter-token
interval and the rate is undefined rather than merely large. That same single delta makes
the request's ``ttft_s`` a time-to-completion rather than a time-to-first-token, which
``ttft_note`` says. The TTFT value is kept — it is a real measurement, of a different thing,
and the row's label is what keeps a reader from comparing it against a streaming runtime's
first-token latency. ``aggregate_tps`` is unaffected either way: it divides every completion
token by the wall time the requests took and needs no per-delta timing at all.

Every table is ordered by **one named metric**, chosen by the caller and printed in the
table header, and one workload at a time: a figure from one shape is not a ranking of
another. There is no blended score. Weighting a second of latency against a megabyte has no
objective answer, and one number would encode an arbitrary trade-off as though it had been
measured — so the metric card carries every measured value behind the ordering instead, and
the ordering can always be checked against the numbers that produced it.

A row is ranked only after it clears every floor, and the floors are pass/fail, never
weighted: coherence, every published metric present, and fits. A row that fails one is
excluded from the ordering, still printed, and named against the floor that kept it out —
an excluded cell is a result, not an absence.

Every raw observation goes into ``results.jsonl``, so every number here stays recomputable
from the file.
"""

from __future__ import annotations

import os
import statistics
from typing import TYPE_CHECKING

from ohyesmlx import measure

if TYPE_CHECKING:  # measure.py owns the shapes; report reads a CellResult and two strings.
    from ohyesmlx.measure import CellResult

AXES = ("runtime", "format")

MIN_PERCENTILE_N = 5

# A rate needs an interval. A runtime that returns the entire completion in a single content
# delta has none, and dividing by the float noise between two identical timestamps is how 256
# tokens were published at 1.5 billion tok/s.
MIN_CONTENT_DELTAS = 2

# How far above the median measured request the cold visit's first request has to sit before
# the row says a load was deferred into it, in SECONDS rather than as a ratio. The ratio this
# replaced was workload-dependent and the deferral is not: oMLX 0.6.4's deferral read as 9.4x
# against a 0.42 s probe request and as 3.3x against a 1.6 s grid request, so the same load
# moved in and out of the verdict because the measured requests got longer. An absolute excess
# does not move that way.
#
# Measured populations. Deferred: oMLX 0.6.4 sat 2.66-3.51 s above its own later requests on
# scripts/probe_lazy.py (three requests, no warmups, three artifacts) and +3.63 s above the
# median on the grid's 128-token chat column. Honest: mlx-lm, mlx-optiq and vMLX stayed
# 0.04-0.10 s above their own later requests on the probe, and -0.19, -0.09 and +0.21 s on the
# grid's four columns. 1 s is 10x the probe's worst honest excess, 4.8x the grid's worst, and
# 2.7x below the smallest deferred one, which puts it in that gap with room on both sides.
#
# It also fires on a deferral a longer workload had hidden: oMLX's own prefill column measured
# +1.47 s, and any threshold above that restores the workload-dependence this replaced. It is
# a note and not a metric -- the row prints both numbers and the excess -- so a reader can
# disagree with the threshold without disagreeing with the finding.
DEFERRED_LOAD_EXCESS_S = 1.0

# How far a cell may move across its own measurement window before the row says so, in PERCENT
# of the early median decode rate and in either direction. A named threshold rather than one of
# the pass/fail FLOORS below: a drifting cell is a result, it is a result that had not finished
# moving, and excluding it would delete the only evidence that the window was too short for it.
#
# Measured, full grid re-run 2026-09-15 evening, all 60 cells, ``change_pct`` per column:
#
#     mlx-lm      median +17.0%   range  -1.3% .. +28.4%   11 of 12 rows over 5%
#     oMLX        median  +2.6%   range  -0.2% .. +14.9%    1 of 12
#     mlx-optiq   median  -0.0%   range  -1.7% .. +14.9%    2 of 12
#     vMLX        median  +0.5%   range  -3.0% ..  +4.6%    0 of 12
#     Osaurus     median  +1.0%   range  -5.7% .. +16.9%    4 of 12
#
# 5% separates the COLUMNS, not every row: mlx-lm's median is 3.4x the threshold while no other
# column's reaches it, and that is the split that has to be visible. It does not cleanly split
# the rows, and the constant is not chosen as though it did — mlx-lm's own `optiq/chat` sits at
# -1.3% and goes unannotated, and 7 rows across the four settled columns are over 5% and are
# annotated. Both are correct: the threshold reports what a row did, and a settled column is
# allowed to contain a row that moved. 4 of those 7 are the first cell measured in their column
# (oMLX and mlx-optiq at +14.9% each, Osaurus at +15.4% and +16.9%) — a column-entry effect that
# is its own finding and not this constant's to fix. The other 3 are ordinary rows.
#
# On the format axis the spread is the whole point: there the runtime is held constant and
# drift still ranges -1.3% to +28.4% *between formats*, so it lands differently on each row and
# nothing cancels it as a common-mode offset. 5% is also about as fine as this comparison can be
# read. With ``measured=5``, ``measured_drift`` puts a median of two rates against a median of
# two and discards the middle sample, so a single row's magnitude is noisy; a lower threshold
# would annotate that noise instead of the unanimous direction.
DRIFT_ANNOTATION_PCT = 5.0

# A row that was measured but has no percentage to print says why, the way every other empty
# value here does. Drift needs two rates to compare, and a cell whose measured requests carry
# fewer has no window to compare: a dash beside a decode rate with no word about it is how the
# cell that was still climbing went unremarked in the first place.
_DRIFT_ABSENCE = (
    "no drift figure: fewer than two decode rates across the measured requests, and drift "
    "compares the first half of the cell's own window against the second"
)

# Each axis holds one variable and varies the other, which is the whole point of the split.
HELD_CONSTANT = {"runtime": "format", "format": "runtime"}

VARIED = {"runtime": "serving runtime", "format": "quantization format"}

# What a table on each axis therefore cannot claim.
CAVEAT = {
    "runtime": "format held constant; this compares serving, not quantization",
    "format": "runtime held constant; this compares quantization, not serving",
}

# --- floors -------------------------------------------------------------------------------

# The gates a (cell, workload) row clears before it is ranked. Pass/fail, never weighted: a
# weighted gate is a score, and a score is what hides which one failed.
FLOORS = ("coherence", "metrics", "fits")

# A floor's verdict. "not reached" is a gate an earlier failure never got to, "not measured"
# is a cell that never ran here, and "not evaluated" is one this build has no source for.
# None of those three is a pass, and none of them excludes a row: a floor nobody asked is
# not a floor to rank against, it is a hole to print.
FLOOR_STATES = ("pass", "fail", "not reached", "not measured", "not evaluated")
FLOOR_CLEARED = frozenset({"pass", "not evaluated"})

# Floor (c) has no source in this build. Nothing under ``ohyesmlx/`` reads the host's total
# unified memory — ``sample.py`` reads ``phys_footprint`` per pid, the ``vmmap --summary``
# regions and ``iogpu.wired_limit_mb`` — so ``peak_mb`` has nothing to be tested against.
# The floor reports that as "not evaluated" rather than passing a check nobody made.
FITS_DETAIL = (
    "sample.py exposes no total unified-memory figure, so peak_mb has nothing to be "
    "tested against"
)

# --- ordering -----------------------------------------------------------------------------

# One named metric orders a table, and which end of its column is good is a property of the
# metric rather than of the reader: a lower TTFT is better, a lower peak is better, and a
# higher tok/s is better. Never a blend of the two families — those weights have no
# objective value, and one number would encode an arbitrary trade-off as though it had been
# measured.
RANK_METRICS = {
    "decode_tps": "higher",
    "aggregate_tps": "higher",
    "prefill_tps": "higher",
    "ttft_p50_s": "lower",
    "itl_s": "lower",
    "peak_mb": "lower",
    "cold_load_s": "lower",
    "disk_bytes": "lower",
}

DEFAULT_RANK = "decode_tps"

# Every value the row carries, in one place, so the card cannot drift from the table.
CARD_FIELDS = (
    ("ttft_p50_s", 3),
    ("ttft_p90_s", 3),
    ("ttft_p99_s", 3),
    ("itl_s", 4),
    ("decode_tps", 1),
    ("aggregate_tps", 1),
    ("prefill_tps", 1),
    ("cold_load_s", 2),
    ("first_request_s", 2),
    ("peak_mb", 1),
    ("disk_bytes", 0),
)

# The decimals every metric is printed with, so a grid entry is the same string the table and
# the card print for the same number: the grid rearranges published rows rather than re-deriving
# them, and two renderings of one number that disagree are two numbers.
_RANK_PLACES = dict(CARD_FIELDS)

# The run-header pins the grid's first join guard compares across columns. A header carries
# these and the workloads it measured, and nothing else -- a pin belongs here on the day one
# exists, and three did: `concurrency` (plan 06-01b), `prompt_tokens` (plan 06-01c) and
# `cache_state` (plan 06-02). The first two were pinned in the header and left out of this
# tuple, so an N=8 run and a 32k-prompt run would each have joined a grid of their opposite
# without a word; the third is here from the day it was written. Every one of the three is a
# property of how the run drove its cells, which is exactly why the grid may not join runs
# that disagree about it.
PIN_FIELDS = (
    "temperature",
    "seed",
    "warmup",
    "measured",
    "cooldown_s",
    "concurrency",
    "prompt_tokens",
    "cache_state",
)

# The caveat a value carries once it exists: a rate's is the delta rule's, TTFT's is the
# channel the stream delivered it in, and a cold visit's first request carries the load a
# runtime deferred into it.
# Metrics that are not one quantity across runtimes, and so cannot carry a runtime-axis
# ordering on their own. A format-axis ordering of them is fine: within one column the
# runtime is held constant, so whatever the number leaves out, it leaves out identically.
#
# `cold_load_s` was the first: oMLX loads lazily and hides 3.08-3.85 s of it inside request
# #1, which is why `first_request_s` exists and why a cross-runtime load comparison uses the
# sum of the two.
#
# `peak_mb` is the second, and the joined grid is what exposed it. Measured, decode workload,
# `footprint` against `vmmap`'s resident size and the weights on disk:
#
#   runtime      footprint MB   resident MB   weights MB
#   mlx-lm          2867-3789     3379-4198    3061-4044
#   oMLX            3686-4198     4403-4813    3061-4044
#   mlx-optiq       2970-3789     3379-4198    3061-4044
#   vMLX            3686          4096-4301    3061-3207
#   Osaurus         1331-2560     2867-3994    3161-4044
#
# In four columns footprint lands within a few percent of the weight bytes. In the Osaurus
# column it lands at roughly half them -- below the size of the weights the process is serving.
#
# PROBED 2026-09-16, and the first explanation was wrong. The standing guess was that Osaurus
# maps its weights file-backed, so the pages would be clean and uncounted. `vmmap`'s full region
# table says otherwise: mapped-file regions hold 34 MB in Osaurus and 2 MB in oMLX, nowhere near
# the 3014 MB of weights either is serving. What differs is the PAGE CLASS. Loading the same
# artifact, system-wide:
#
#   Osaurus   process footprint 1562 MB   wired +1064 MB   active  -66 MB
#   oMLX      process footprint 3995 MB   wired    +1 MB   active +752 MB
#
# and in the region table Osaurus's `IOAccelerator (graphics)` holds 581 MB against oMLX's
# 3334 MB for identical weights. Osaurus puts its weights in wired, GPU-pinned pages; oMLX
# holds them as ordinary anonymous memory. `phys_footprint` charges those two differently, so
# the number is not the same quantity in the two columns -- which is the point, and it is now
# measured rather than inferred. Exactly how Metal attributes a wired device allocation to a
# process is not settled here and does not need to be: what a cross-runtime ranking needs is
# one quantity, and this is not one.
CROSS_RUNTIME_UNCOMPARABLE = {
    "peak_mb": "`footprint` does not measure the same pages in every runtime: in the "
    "2026-09-16 grid four columns report a footprint within a few percent of their weight "
    "bytes and Osaurus reports roughly half of its, below the weights it is serving, while "
    "its resident size sits at them. Read this row as five numbers, not as a ranking, until "
    "the sampler is probed against a runtime that maps its weights file-backed.",
    "cold_load_s": "a lazy loader defers part of its load past readiness and into request #1, "
    "where `first_request_s` records it. A cross-runtime load comparison is the sum of the "
    "two, not this column alone.",
}

# A cold load recorded by a later start says which start it came from; a rate's, TTFT's and a
# cold visit's first request carry the caveats above.
_METRIC_CAVEAT = {
    "decode_tps": "delta_note",
    "prefill_tps": "delta_note",
    "itl_s": "delta_note",
    "ttft_p50_s": "ttft_note",
    "first_request_s": "first_request_note",
    "cold_load_s": "cold_load_note",
}

# The note that explains a missing value instead: a rate's absence is the delta rule's, and a
# percentile's absence is the sample count's.
_METRIC_ABSENCE = {
    "decode_tps": "delta_note",
    "prefill_tps": "delta_note",
    "itl_s": "delta_note",
    "ttft_p50_s": "percentile_note",
    "ttft_p90_s": "percentile_note",
    "ttft_p99_s": "percentile_note",
}


def percentile(values, q):
    """The q-th percentile, linearly interpolated between order statistics.

    Same definition as ``numpy.percentile``'s default, so a reader can recompute the number
    with the tooling they already have. ``None`` when there is nothing to take it from.
    """
    ordered = sorted(values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return float(ordered[0])
    return float(statistics.quantiles(ordered, n=100, method="inclusive")[q - 1])


def median(values):
    """The median, or ``None`` when there is nothing to take it from."""
    values = list(values)
    if not values:
        return None
    return float(statistics.median(values))


def dir_bytes(path):
    """Total size of every file under *path*, sidecars included.

    Every file, not just the weights: JANGTQ ships a ``jangtq_runtime.safetensors`` next to
    its shards, and a walk that collected shards by name would credit that format with a
    smaller footprint than it has. Symlinked directories are not followed (``os.walk``'s
    default), so the walk stays finite. ``None`` if *path* is not a directory.
    """
    root = os.path.expanduser(str(path))
    if not os.path.isdir(root):
        return None

    total = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                continue  # a file that went away mid-walk is not a reason to fail a run
    return total


def summarize(results: list[CellResult], *, measured: int | None = None) -> list[dict]:
    """One row per (cell, workload): the contract's fields, joined from measure, the sampler
    and disk.

    Rows keep the order the cells came in. Observations are used exactly as measure
    recorded them — this module has no warmup marker to filter on, so keeping warmups out
    of a cell's summary is measure's job. Percentiles below ``MIN_PERCENTILE_N`` samples
    are omitted rather than guessed, and ``percentile_note`` says so; a request that
    streamed fewer than ``MIN_CONTENT_DELTAS`` content deltas carries no rate to report, and
    ``delta_note`` and ``ttft_note`` say that instead.

    *measured* is the run's batch pin: a row that landed fewer batches than that carries
    ``short_note``, and the grid and the sweep print the count beside the number. A caller
    joining run directories reads it from each run's header and passes it in, because a result
    rebuilt by ``load_run`` does not carry it — the header owns it on disk. A caller
    summarizing a run it just made passes nothing, and each row's own pin is used instead,
    which is the same number that run's header recorded.

    No pin at all means no note: absent is no check, never a pin of zero. That is the honest
    reading of an older record and of a caller that never knew about the pin, and it is the one
    place a run short of its window can go unremarked.

    Each row also carries the floor verdicts and whether they leave it rankable. Figures
    are never averaged across workloads: a prefill-bound number blended with a decode-bound
    one describes no workload that was run.
    """
    return [
        _row(result, measured=measured if measured is not None else result.measured_pin)
        for result in results
    ]


def render_markdown(rows: list[dict], *, axis: str, rank: str = DEFAULT_RANK) -> str:
    """The leaderboard: one table per workload, each ordered by one named metric.

    *axis* is required and is ``"runtime"`` or ``"format"``. A table that does not say
    which variable it held constant is not a result, and one whose rows do not actually
    hold it constant is refused rather than rendered.

    *rank* names the single metric each table is ordered by, and every header names it. The
    workload is the other axis of the table: the shapes are ordered independently, because
    one shape's figures are not a ranking of another's. The metric card follows the tables.
    """
    if axis not in AXES:
        raise ValueError(f"axis must be one of {AXES!r}, not {axis!r}")
    if rank not in RANK_METRICS:
        raise ValueError(_rank_error(rank))

    held = _held_constant(rows, axis)
    lines = [f"# Leaderboard — {axis} axis", ""]
    if held is None:
        lines.append(f"One variable varied: the {VARIED[axis]}. No cells were measured.")
    else:
        lines.append(f"One variable varied: the {VARIED[axis]}. Held constant: {held}.")
    lines += [
        "",
        f"> **Caveat:** {CAVEAT[axis]}.",
        "",
        f"Each table is ordered by one metric, `{rank}` ({_direction(rank)}), and names it "
        "in its header. One workload per table, ordered on its own, and no figure averaged "
        "across workloads: a prefill-bound number blended with a decode-bound one describes "
        "no workload that was run. There is no combined score either — those weights have "
        "no objective value — so every number behind each ordering is in the metric card "
        "under the tables.",
        "",
    ]
    for workload, group in _by_workload(rows):
        lines += [
            f"## Workload `{workload}` — ordered by `{rank}` ({_direction(rank)})",
            "",
            _table(order_rows(group, rank), rank),
            "",
        ]
    lines += _footnotes()
    lines += ["", render_cards(rows, rank=rank).rstrip("\n"), ""]
    return "\n".join(lines) + "\n"


def render_grid(runs: list[tuple[str, dict, list[dict]]], *, rank: str = DEFAULT_RANK) -> str:
    """The joined grid: one table per workload, formats down and runtimes across.

    *runs* is one ``(run label, run header, rows)`` per run directory, where *rows* is
    ``summarize``'s output. No file is read and no figure is re-derived here: the grid
    rearranges the numbers five leaderboards already published, so a cell's entry is the
    string its row prints there.

    Phase 3 measured the grid one column at a time, which makes joining the columns the one
    place this project could vary two things without noticing. Four disagreements refuse the
    join before a table is drawn — pins that differ, a cell in two run directories, one
    format label at two artifacts, one runtime at two versions — and each names both run
    directories and the field that disagreed, because a grid that refuses has to say which
    two files disagreed and on what. It refuses rather than picks: which run is newer is not
    which run is right.

    A **column** is one runtime across many formats and is the format axis; a **row** is one
    format across many runtimes and is the runtime axis. Both readings are printed below the
    tables and neither is a blend of the other. The best cell across the whole grid is a
    recommendation and never an attribution: it won under one format and one runtime at once,
    and nothing in the number can apportion the win between them. No figure is averaged
    across workloads, and there is no combined score.
    """
    if rank not in RANK_METRICS:
        raise ValueError(_rank_error(rank))
    runs = [(label, dict(header or {}), list(rows)) for label, header, rows in runs]
    _check_pins(runs)
    _check_cells_appear_once(runs)
    _check_one_artifact_per_label(runs)
    _check_one_version_per_runtime(runs)

    columns = _columns(runs)
    labels = _format_labels(runs)
    lines = [
        f"# Grid — {len(runs)} run directories joined",
        "",
        "Two axes, one set of cells, and they are read apart from each other. **A column is "
        "one runtime across many formats — the format axis.** **A row is one format across "
        "many runtimes — the runtime axis.** Nothing here blends them: no figure is averaged "
        "across workloads and no ordering puts the two axes on one scale.",
        "",
    ]
    if not columns:
        lines += ["No run directories were named, so there was nothing to join.", ""]
        return "\n".join(lines) + "\n"

    lines += [
        f"Each table is one workload and carries one metric: `{rank}` "
        f"({_direction(rank)}).",
        "",
        "| entry | means |",
        "|---|---|",
        "| a number | a measured cell that cleared every floor |",
        "| `no value` | a cell that cleared every floor and has no value for this metric; "
        "its run's leaderboard carries the note saying why |",
        "| `FAIL` | a measured cell that did not clear one |",
        "| `—` | a combination no run measured |",
        "",
        "The matrix is ragged by design — no runtime loads every format — so `—` is ordinary "
        "and does not read as a failure. A cell whose drift moved more than "
        f"{DRIFT_ANNOTATION_PCT:g}% across its own window carries its marker beside its "
        "number, the same marker the leaderboard prints beside the rate it qualifies.",
        "",
    ]
    lines += _provenance(runs, columns)

    groups = _by_workload([row for _label, _header, rows in runs for row in rows])
    for workload, rows in groups:
        lines += [
            f"## Workload `{workload}` — entries are `{rank}` ({_direction(rank)})",
            "",
            _grid_table(rows, labels, columns, rank),
            "",
        ]
    lines += _readings(groups, columns, labels, rank)
    lines += [
        "## Notes",
        "",
        "The notes below are the leaderboard's own, unchanged, and govern every figure here. "
        "Where one refers to the metric card, that card is in each run's own "
        "`leaderboard.md`: the grid joins published rows and re-renders none of their "
        "numbers.",
        "",
    ]
    lines += _footnotes()
    return "\n".join(lines) + "\n"


def order_rows(rows: list[dict], metric: str = DEFAULT_RANK) -> list[dict]:
    """The rows in ranking order for one metric: ranked first, then the valueless, then the
    excluded.

    Higher-is-better metrics sort descending and lower-is-better ones ascending, from
    ``RANK_METRICS``. A row that cleared every floor but carries no value for *metric* ranks
    below every row that has one and says why — a stream that delivered the whole completion
    in one delta has no decode rate to rank by, and that is a fact about the stream, not a
    slow result. A row a floor excluded is not in the ranking at all, keeps the exclusion as
    its note, and is still printed.

    Rows are copied rather than annotated in place, so one set can be ranked twice by two
    metrics and the two orderings cannot contaminate each other.
    """
    if metric not in RANK_METRICS:
        raise ValueError(_rank_error(metric))

    ranked, valueless, excluded = [], [], []
    for row in rows:
        copied = dict(row)
        copied["rank"], copied["rank_note"] = None, None
        if not row.get("rankable"):
            excluded.append(copied)
        elif row.get(metric) is None:
            copied["rank_note"] = (
                f"{metric} is None, so this row ranks last: {_why_none(row, metric)}"
            )
            valueless.append(copied)
        else:
            ranked.append(copied)

    ranked.sort(key=lambda row: row[metric], reverse=RANK_METRICS[metric] == "higher")
    for position, row in enumerate(ranked, start=1):
        row["rank"] = position
    return ranked + valueless + excluded


def render_cards(rows: list[dict], *, rank: str = DEFAULT_RANK) -> str:
    """The metric card: every value behind the ordering, one card per (cell, workload).

    The tables say which cell came first. This says what every number behind that ordering
    was — the raw inputs the derived figures were built from, the figures themselves, and the
    floor verdicts — including for the cells the floors kept out of the ranking. It carries
    no combined figure, and deliberately: there is no honest way to weight a second of
    latency against a megabyte, so the reader gets the numbers and makes the trade-off
    themselves.
    """
    if rank not in RANK_METRICS:
        raise ValueError(_rank_error(rank))

    lines = [
        "## Metric card",
        "",
        f"Every value behind the ordering, per (cell, workload), ranked by `{rank}` "
        f"({_direction(rank)}) under the same floors the tables use. The raw inputs are "
        "listed beside the figures derived from them, and a floor this build cannot evaluate "
        "says so rather than counting as cleared.",
        "",
    ]
    for workload, group in _by_workload(rows):
        lines += [f"### Workload `{workload}`", ""]
        for row in order_rows(group, rank):
            lines += _card(row, rank)
            lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def _by_workload(rows: list[dict]) -> list[tuple[str, list[dict]]]:
    """The rows grouped by the shape that produced them, in the order the shapes arrived."""
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row.get("workload_id") or "—", []).append(row)
    return list(groups.items())


def _card(row: dict, rank: str) -> list[str]:
    """One (cell, workload) card: what happened, then the raw inputs, then the figures."""
    lines = [
        f"#### `{_text(row.get('cell_id'))}` — {_text(row.get('runtime'))} / "
        f"{_text(row.get('label'))}",
        "",
        "| field | value | note |",
        "|---|---|---|",
        _card_row("workload", _text(row.get("workload_id"))),
        # The row's own reason, and beside it the visit that was lost before this one measured:
        # the status is the surviving visit's and the lost visit is why the row is short.
        _card_row(
            "status",
            _text(row.get("status")),
            "; ".join(
                note for note in (row.get("reason"), row.get("lost_visit_note")) if note
            ),
        ),
        _card_row(
            "rank",
            _text(row.get("rank")),
            row.get("rank_note") or row.get("exclusion"),
        ),
    ]
    for floor in row.get("floors") or ():
        lines.append(
            _card_row(f"floor {floor['floor']}", floor["state"], floor.get("detail"))
        )
    lines += [
        # The count the pin was checked against, and what the check found: a card that printed
        # the count alone would render a cell that landed four of nine batches like one that
        # landed all nine.
        _card_row("n measured", _text(row.get("n_measured")), row.get("short_note")),
        _card_row("n requests", _text(row.get("n_requests"))),
        _card_row(
            "content deltas", _text(row.get("content_deltas")), "over the measured requests"
        ),
        _card_row("token_source", _text(row.get("token_source"))),
    ]
    for field, places in CARD_FIELDS:
        value = row.get(field)
        shown = _bytes(value) if field == "disk_bytes" else _number(value, places)
        lines.append(_card_row(field, shown, _card_note(row, field, rank)))
        if field == "decode_tps":
            # Beside the rate it qualifies: whether the cell had settled by the time its window
            # closed is part of reading that rate, and a card that listed the rate alone would
            # print a cell still climbing exactly as it prints one that held still.
            lines.append(_drift_card_row(row))
    lines += [
        _card_row("runtime_version", _text(row.get("runtime_version"))),
        _card_row("artifact_dir", _text(row.get("artifact_dir"))),
        "",
    ]
    return lines


def _card_row(field: str, value: str, note: str | None = None) -> str:
    return f"| {field} | {value} | {note or ''} |"


def _card_note(row: dict, field: str, rank: str) -> str | None:
    """What a card row has to say for itself: its caveat, why it is empty, or that it is the
    metric the ordering used."""
    notes = []
    if field == rank:
        notes.append("the ranking metric")
    if row.get(field) is None:
        notes.append(_why_none(row, field))
    else:
        notes.append(row.get(_METRIC_CAVEAT.get(field)))
    return "; ".join(note for note in notes if note) or None


def _why_none(row: dict, metric: str) -> str:
    """Why this row carries no value for *metric*, in the row's own words.

    A row with nothing measured says that first: a percentile note about a sample count
    explains a missing p90, and it is not the reason a cell that never ran carries no p50.
    """
    if not row.get("n_measured"):
        return "n=0: nothing was measured for this (cell, workload)"
    return row.get(_METRIC_ABSENCE.get(metric)) or (
        f"the run recorded no {metric} for this (cell, workload)"
    )


def _direction(metric: str) -> str:
    """Which end of the column is good, in words a reader can act on."""
    return "higher is better" if RANK_METRICS[metric] == "higher" else "lower is better"


def _rank_error(metric) -> str:
    return f"rank must be one of {tuple(RANK_METRICS)}, not {metric!r}"


def _row(result: CellResult, *, measured: int | None = None) -> dict:
    cell = result.cell
    observations = list(result.observations)
    # Who came back is measure's question, and its answer is asked for rather than respelled:
    # ``observation.ok`` is a second definition of it, and the two drifted apart — a cell whose
    # five requests all answered in the reasoning channel was published as ``n = 0/5``.
    samples = [o for o in observations if measure.came_back(o)]

    ttft = [o.ttft_s for o in samples if o.ttft_s is not None]
    decode, prefill, itl = [], [], []
    for observation in samples:
        per_request = _per_request(observation)
        if per_request["decode_tps"] is not None:
            decode.append(per_request["decode_tps"])
        if per_request["prefill_tps"] is not None:
            prefill.append(per_request["prefill_tps"])
        if per_request["itl_s"] is not None:
            itl.append(per_request["itl_s"])

    n = len(ttft)
    deltas = [_content_deltas(observation) for observation in samples]
    single_delta = deltas.count(1)
    too_few = sum(1 for count in deltas if count < MIN_CONTENT_DELTAS)
    # measure's own dict off the raw observations, which is what ``results.jsonl`` recorded for
    # this row: asking for it rather than recomputing it here is what keeps the two in step.
    drift = measure.measured_drift(result.observations)
    batches = _measured_batches(result)
    # A cell that landed fewer batches than its pin is a result measured short, not a failed
    # one: it is annotated and still ranked, and the pin is only compared when the caller
    # handed one over -- absent is no check, never a pin of zero.
    short = measured is not None and 0 < batches < measured
    row = {
        "cell_id": cell.id,
        "runtime": cell.runtime,
        "label": cell.label,
        "artifact_dir": cell.artifact_dir,
        "workload_id": result.workload_id,
        "status": result.status,
        "reason": result.reason,
        "n_measured": len(samples),
        "n_requests": len(observations),
        "measured_batches": batches,
        "measured_pin": measured,
        "content_deltas": sum(deltas),
        "token_source": _token_source(samples),
        "ttft_p50_s": percentile(ttft, 50),
        "ttft_p90_s": percentile(ttft, 90) if n >= MIN_PERCENTILE_N else None,
        "ttft_p99_s": percentile(ttft, 99) if n >= MIN_PERCENTILE_N else None,
        "itl_s": median(itl),
        "decode_tps": median(decode),
        "drift": drift,
        "aggregate_tps": _aggregate_tps(samples, result.batch_spans),
        "prefill_tps": median(prefill),
        "cold_load_s": result.cold_load_s,
        "first_request_s": result.first_request_s,
        "peak_mb": (result.memory or {}).get("peak_mb"),
        "disk_bytes": result.disk_bytes
        if result.disk_bytes is not None
        else dir_bytes(cell.artifact_dir),
        "runtime_version": result.runtime_version,
        "percentile_note": None
        if n >= MIN_PERCENTILE_N
        else f"n={n}: p90/p99 omitted (fewer than {MIN_PERCENTILE_N} samples)",
        "delta_note": None
        if not too_few
        else f"n={len(decode)}: decode tok/s, ITL and prefill tok/s omitted (fewer than "
        f"{MIN_CONTENT_DELTAS} content deltas in {too_few} of {len(samples)} measured "
        "requests)",
        "ttft_note": None
        if not single_delta
        else f"TTFT is time-to-completion, not time-to-first-token: {single_delta} of "
        f"{len(samples)} measured requests arrived whole in one content delta",
        "drift_note": _drift_note(drift, len(samples)),
        "short_note": None
        if not short
        else f"short measured window: {batches} of {measured} pinned batches landed; "
        f"the median is over the {batches} that did",
        "lost_visit_note": _lost_visit_note(result),
        "cold_load_note": _cold_load_note(result),
        "first_request_note": _deferred_load_note(
            result.first_request_s if _made_the_first_request(result) else None,
            [observation.total_s for observation in samples],
        ),
    }
    row.update(_floor_verdicts(row["status"], row["reason"]))
    return row


def _measured_batches(result: CellResult) -> int:
    """How many measured batches the row landed, the unit the run's pin is counted in.

    ``measured`` pins batches, and at ``concurrency=1`` a batch is one request with no clock
    around it: the observation count is the batch count exactly, which is what every column on
    disk ran. Above 1 the batch spans are the only record of how many batches ran — nine batches
    of eight are 72 observations and nine spans, and the pin counts the nine — so the count is
    read off them rather than off the requests they held, which would compare requests to
    batches and never report a concurrent run short of its pin.
    """
    if result.batch_spans:
        return len(result.batch_spans)
    return len(result.observations)


def _lost_visit_note(result: CellResult) -> str | None:
    """The note a cell whose visit was lost keeps, or ``None`` when none was.

    A visit that fails writes its reason on the row, and the visit that measures after it
    rewrites that row's status and reason from its own samples — so without this the failure is
    erased and the row is a PASS one visit short with nothing saying so or why. The reason is
    what the row keeps, because which visit was lost is the whole account of the gap.
    """
    if result.lost_visit_reason is None:
        return None
    return (
        "a visit to this cell was lost before the one that measured: "
        f"{result.lost_visit_reason}; the samples on this row are the surviving visit's"
    )


def _cold_load_note(result: CellResult) -> str | None:
    """The note a cold load recorded by a later start earns, or ``None``.

    ``cold_load_s`` and ``first_request_s`` are the cold visit's numbers, and the visit that
    recorded them is a later one whenever an earlier visit was lost: its start is a
    warm-page-cache start, not the cell's first, and a column read as "cold load s" would say
    otherwise. The figures stay exactly as measured; the row says which start they came from.
    """
    if not result.cold_load_after_lost_visit:
        return None
    return (
        "cold load s and first request s are from a later start than the first planned visit: "
        "the load this start paid is a warm-page-cache one, not the cell's cold start"
    )


def _made_the_first_request(result: CellResult) -> bool:
    """Whether this row's workload is the one that made the cold visit's first request.

    A visit runs its workloads in order, so that request belongs to the shape that ran first,
    and measure records which one on every row of the cell. The latency is still the visit's
    fact and every row prints it; the note is a different claim — that the gap between it and
    the requests measured here is a load the runtime deferred — and only the row that paid it
    has the population to make that claim from. On any other row the two sides are different
    workloads: an eager loader's honest 3.6-5.0 s chat request read against prefill's ~1.0 s
    median is +2.6-4.0 s of deferral that never happened. A row that did not make that request
    claims nothing, and a visit that made none leaves every row of the cell silent.
    """
    return result.first_request_workload_id == result.workload_id


def _deferred_load_note(first_request_s, request_seconds) -> str | None:
    """The note a first request far above the measured ones earns, or ``None``.

    The cold visit's first request is the one that carries whatever the runtime did not do
    before it was ready, so for a lazy loader it is a whole model load wearing a request's
    name. Above ``DEFERRED_LOAD_EXCESS_S`` seconds more than the median measured request the
    row says so, and prints both numbers and their difference: the load is the reason the
    user's first prompt is slow, and a reader left to guess would file it as warm-up.
    """
    median_s = median(request_seconds)
    if first_request_s is None or not median_s or median_s <= 0:
        return None
    excess = first_request_s - median_s
    if excess < DEFERRED_LOAD_EXCESS_S:
        return None
    return (
        f"the cold visit's first request took {first_request_s:.2f} s against a median "
        f"measured request of {median_s:.2f} s ({excess:+.2f} s over it): a load this "
        "runtime deferred past readiness, not warm-up noise"
    )


def _drift_note(drift, n_measured: int) -> str | None:
    """What the row has to say about its own drift, or ``None`` when there is nothing to say.

    Three cases and no fourth. Above ``DRIFT_ANNOTATION_PCT`` in either direction the row says
    which way it moved and prints the medians it compared, so the call can be checked rather
    than taken. Below it there is nothing to report: a cell that held still is not a finding,
    and a note on every row would separate none of them. And a cell that was measured but whose
    requests carry fewer than two rates has no window to compare, which the row says instead of
    printing a dash for; a cell that was never measured says nothing here at all, because drift
    is not the reason its row is empty and the row already carries the reason that is.

    Direction is the finding and the only part a two-against-two comparison of medians
    supports, so the note names the direction and says outright that the magnitude is not what
    it is claiming: a slower late half is the thermal curve the interleave exists to expose, and
    a faster one is a cell still warming up, whose published rate is an early-window rate.
    """
    if drift is None:
        return _DRIFT_ABSENCE if n_measured else None
    change = drift["change_pct"]
    if change is None:
        # An early median of zero: the ratio is undefined rather than infinite, and measure
        # reports it as no percentage rather than as one.
        return _DRIFT_ABSENCE
    if abs(change) <= DRIFT_ANNOTATION_PCT:
        return None
    direction = (
        "it was still warming up as it was measured, so its decode rate is an early-window "
        "figure rather than a settled one — insufficient warmup, not a thermal effect"
        if change > 0
        else "it was slowing down as it was measured — the thermal curve the interleave "
        "exists to expose"
    )
    half = drift["n"] // 2
    return (
        f"drift {change:+.1f}% across the cell's own measurement window (early median "
        f"{drift['early_median_tps']:.1f} tok/s against a late median of "
        f"{drift['late_median_tps']:.1f} tok/s, n={drift['n']}): {direction}. A median of "
        f"{half} rates against a median of {half} fixes the direction, not the magnitude"
    )


def _drift_cell(row: dict) -> str:
    """The drift column: the signed percentage, or ``—`` when there is nothing to compare.

    The sign is carried rather than left to the reader, because it is the whole difference
    between a cell that slowed under its own window and one that had not finished warming up.
    """
    drift = row.get("drift") or {}
    change = drift.get("change_pct")
    return "—" if change is None else f"{change:+.1f}"


def _drift_card_row(row: dict) -> str:
    """The card's drift line, beside the decode rate it qualifies.

    A reader comparing two cells needs to see that one of them was still climbing while the
    other had settled, and a card that printed the rate alone would render the two identically.
    """
    return _card_row("drift_pct", _drift_cell(row), row.get("drift_note"))


def _floor_verdicts(status, reason) -> dict:
    """The three gates, their verdicts, and what they leave this row.

    The first two floors are measure's already: ``_set_status`` decides PASS only when every
    measured request came back carrying what the published metrics need and the responses are
    language. This re-runs neither check — it reads the verdict measure recorded and names the
    gate that wrote it, which is what the table and the card print and what a status string
    alone does not say. A row that fails a floor is kept out of the ordering and still shown.
    """
    if status == "N/A":
        # The cell never ran here, so no gate was faced. It cannot rank, and the row says the
        # cell was not measured rather than blaming a gate it never reached. The reason is on
        # the row itself; repeating it under all three floors would bury it.
        floors = [_verdict(floor, "not measured", "not measured") for floor in FLOORS]
    elif _coherence_failed(status, reason):
        floors = [
            _verdict("coherence", "fail", reason),
            _verdict("metrics", "not reached"),
            _verdict("fits", "not evaluated", FITS_DETAIL),
        ]
    elif status != "PASS":
        floors = [
            _verdict("coherence", "pass"),
            _verdict("metrics", "fail", reason),
            _verdict("fits", "not evaluated", FITS_DETAIL),
        ]
    else:
        floors = [
            _verdict("coherence", "pass"),
            _verdict("metrics", "pass"),
            _verdict("fits", "not evaluated", FITS_DETAIL),
        ]

    excluded_by = next((floor["floor"] for floor in floors if floor["state"] == "fail"), None)
    rankable = all(floor["state"] in FLOOR_CLEARED for floor in floors)
    if rankable:
        exclusion = None
    elif excluded_by is not None:
        exclusion = f"excluded by {excluded_by}"
    else:
        exclusion = "not ranked: not measured"
    return {
        "floors": floors,
        "rankable": rankable,
        "excluded_by": excluded_by,
        "exclusion": exclusion,
    }


def _verdict(floor: str, state: str, detail: str | None = None) -> dict:
    return {"floor": floor, "state": state, "detail": detail}


def _coherence_failed(status, reason) -> bool:
    """Whether measure's verdict on this row came from the coherence gate.

    measure records one reason string per cell and does not name the gate that produced it,
    so the gate's own vocabulary is what identifies it — read from measure rather than
    respelled here, because a second copy of ``"incoherent output: "`` is a second source of
    truth for one verdict, and the two would drift.
    """
    if status == "PASS" or not reason:
        return False
    return reason.startswith(measure.INCOHERENT_PREFIX) or reason == measure.STILL_THINKING


def _token_source(observations) -> str | None:
    """Where the completion-token counts came from, as the run reported them.

    measure builds one counter per cell and passes it to every request, so one value is the
    normal case. More than one is printed rather than collapsed: the contract forbids mixing
    sources inside one comparison, and a row that did is a row to look at.
    """
    sources = sorted({observation.token_source for observation in observations})
    if not sources:
        return None
    if len(sources) == 1:
        return sources[0]
    return "mixed: " + ", ".join(sources)


def _content_deltas(observation) -> int:
    """How many content deltas this request's stream delivered.

    One delta means the first content delta was the whole response, so the two timestamps a
    rate is built from are the same instant.
    """
    return observation.content_event_count or 0


def _per_request(observation) -> dict:
    """One observation's three per-request metrics, exactly as the contract defines them.

    A metric whose inputs are missing — no token count, a decode window of zero length, a
    stream with no inter-token interval — is ``None``. It is never faked from a leftover
    number.
    """
    ttft = observation.ttft_s
    last = observation.last_content_s
    tokens = observation.completion_tokens
    prompt = observation.prompt_tokens
    span = last - ttft if last is not None and ttft is not None else None
    counted = tokens is not None
    streamed = _content_deltas(observation) >= MIN_CONTENT_DELTAS

    decode_tps = (
        tokens / span if counted and streamed and span is not None and span > 0 else None
    )
    # prefill_tps divides the prompt by TTFT, which is only prefill time when TTFT is a
    # first-token latency. In a one-delta stream TTFT spans the whole generation, so the
    # same arithmetic reports a prefill rate several times slower than the runtime's real
    # one — wrong in the believable direction, which is worse than wrong absurdly.
    prefill_tps = (
        prompt / ttft
        if prompt is not None and streamed and ttft is not None and ttft > 0
        else None
    )
    itl_s = (
        span / max(1, tokens - 1)
        if counted and streamed and span is not None and span >= 0
        else None
    )
    return {"decode_tps": decode_tps, "prefill_tps": prefill_tps, "itl_s": itl_s}


def _aggregate_tps(observations: list, batch_spans: list[float]) -> float | None:
    """Cell-wide output throughput: every completion token over the wall time it took.

    Two clocks, and which one is the cell's depends on how the run drove the cell. A record
    carrying ``batch_spans`` was driven in batches of N requests issued together under one clock
    each, so the window is the sum of those spans. Summing the per-request ``total_s`` instead
    counts the overlap N times and divides by ~N x the wall clock: measured, oMLX ``chat`` in
    ``results/sweep-conc/`` read 66.0 / 42.3 / 25.5 / 14.3 tok/s at N=1/2/4/8 over the
    per-request clocks while the runtime held a flat 66.0-66.8. A per-request result rendered as
    a throughput one is the reading the concurrency sweep exists to avoid.

    A record without spans is every sequential run and every record written before plan 06-01b:
    at ``concurrency=1`` a batch is one request, no clock is taken around it, and measure refuses
    to reconstruct one from ``total_s`` -- a gap between two sequential requests belongs to
    neither one. Those rows keep the sum of the per-request clocks exactly as they always had
    it, so no number measured so far moves.

    The mapping between the two series is measure's: ``_workload_visit`` extends
    ``observations`` with a batch's observations and appends that batch's span in the same step,
    so N observations arrive per span and the ratio over the totals is what the per-batch
    aggregates are over the window, without attributing any observation to a batch. That
    attribution is deliberately not made -- the row is handed the requests that came back, and
    one request that did not come back would shift every later chunk of them. A batch that lost
    a request still took its span, and the tokens that came back over the time the window took
    is the honest figure.
    """
    if batch_spans:
        tokens = sum(
            observation.completion_tokens
            for observation in observations
            if observation.completion_tokens is not None
        )
        seconds = sum(batch_spans)
        if not tokens or seconds <= 0:
            return None
        return tokens / seconds

    tokens = 0
    seconds = 0.0
    for observation in observations:
        if observation.completion_tokens is None or not observation.total_s:
            continue
        tokens += observation.completion_tokens
        seconds += observation.total_s
    if not tokens or seconds <= 0:
        return None
    return tokens / seconds


def _held_constant(rows: list[dict], axis: str) -> str | None:
    """What every row shares on this axis' held-constant variable, in words.

    Two rows that agree on the format's name but point at different artifacts are two
    formats, so the runtime axis is checked against the pair, and both are named.
    """
    if not rows:
        return None

    if axis == "runtime":
        pairs = sorted({(str(r.get("label")), str(r.get("artifact_dir"))) for r in rows})
        held = f"format `{pairs[0][0]}` at `{pairs[0][1]}`"
        distinct = [f"{label} at {artifact}" for label, artifact in pairs]
    else:
        # The runtime's *version* is part of the runtime. Osaurus updated 0.25.3 -> 0.25.4
        # mid-session and measured a 1.15x difference across it, so a format-axis table
        # spanning two builds varies its held-constant variable as surely as one spanning
        # two runtimes would. Rows carrying no version never started a runtime, and a cell
        # that never ran cannot disagree about which build the others ran on.
        names = sorted({str(r.get("runtime")) for r in rows})
        versions = sorted(
            {str(r.get("runtime_version")) for r in rows if r.get("runtime_version")}
        )
        held = f"runtime `{names[0]}`"
        if versions:
            held += f" at version `{versions[0]}`"
        distinct = [f"{name} {version}".strip()
                    for name in names
                    for version in (versions or [""])]

    if len(distinct) > 1:
        raise ValueError(
            f"these rows vary the {HELD_CONSTANT[axis]} as well as the {VARIED[axis]} "
            f"({len(distinct)} distinct: {', '.join(distinct)}); a table that varies both "
            "variables is not a result"
        )
    return held


def _table(rows: list[dict], rank: str) -> str:
    header = (
        f"| cell | runtime | format | workload | rank by {rank} | status | n "
        "| TTFT p50 s | TTFT p90 s | TTFT p99 s "
        "| ITL s | decode tok/s | drift % | aggregate tok/s | prefill tok/s | cold load s "
        "| first request s | peak MB "
        "| disk bytes | runtime version | notes |"
    )
    divider = "|" + "---|" * (header.count("|") - 1)
    lines = [header, divider]
    lines += ["| " + " | ".join(_cells(row)) + " |" for row in rows]
    return "\n".join(lines)


def _cells(row: dict) -> list[str]:
    n, total = row.get("n_measured"), row.get("n_requests")
    notes = _unrepeated(
        [
            part
            for part in (
                row.get("rank_note"),
                row.get("exclusion"),
                row.get("reason"),
                row.get("lost_visit_note"),
                row.get("short_note"),
                row.get("percentile_note"),
                row.get("ttft_note"),
                row.get("delta_note"),
                row.get("drift_note"),
                row.get("cold_load_note"),
                row.get("first_request_note"),
            )
            if part
        ]
    )
    return [
        _text(row.get("cell_id")),
        _text(row.get("runtime")),
        _text(row.get("label")),
        _text(row.get("workload_id")),
        _text(row.get("rank")),
        _text(row.get("status")),
        _text(n) if total in (None, n) else f"{n}/{total}",
        _number(row.get("ttft_p50_s"), 3),
        _number(row.get("ttft_p90_s"), 3),
        _number(row.get("ttft_p99_s"), 3),
        _number(row.get("itl_s"), 4),
        _number(row.get("decode_tps"), 1),
        _drift_cell(row),
        _number(row.get("aggregate_tps"), 1),
        _number(row.get("prefill_tps"), 1),
        _number(row.get("cold_load_s"), 2),
        _number(row.get("first_request_s"), 2),
        _number(row.get("peak_mb"), 1),
        _bytes(row.get("disk_bytes")),
        _text(row.get("runtime_version")),
        "; ".join(notes) if notes else "—",
    ]


def _unrepeated(notes: list[str]) -> list[str]:
    """The notes, minus any that an earlier note already spells out.

    A row whose ranking metric is missing says why twice — once inside the rank note and
    once as the delta note it quotes — and the same sentence printed twice reads as two
    separate findings about one stream.
    """
    kept = []
    for note in notes:
        if not any(note in earlier for earlier in kept):
            kept.append(note)
    return kept


def _footnotes() -> list[str]:
    return [
        "Every table is ordered by one metric, named in its header, and every workload is "
        "ordered on its own: a figure from one shape is never a ranking of another. The "
        "ordering is never a blend of speed and memory — those weights have no objective "
        "value — so the metric card below carries every number behind it.",
        "",
        "A row is ranked only after it clears every floor, and the floors are pass/fail, "
        "never weighted: coherence (the gate in `coherence.py`), every published metric "
        "present, and fits. The first two are measure's, recorded as the row's status. Fits "
        "is not evaluated in this build: nothing under `ohyesmlx/` reads the host's total "
        "unified memory, so peak MB has nothing to be tested against, and the floor prints "
        "itself as not evaluated rather than as cleared. A row that fails a floor is "
        "excluded from the ordering, still printed, and names the floor in its notes.",
        "",
        "decode tok/s is the median per-request rate, "
        "`completion_tokens / (last content − TTFT)`. aggregate tok/s is every completion "
        "token over the time the measured requests took, so it includes prefill and "
        "queueing. They are reported as two numbers because continuous batching wins one "
        "and loses the other.",
        "",
        "peak MB is Apple's `phys_footprint` from `footprint -p <pid>`. disk bytes counts "
        "every file under the artifact directory, sidecars included.",
        "",
        "first request s is the cold visit's first warmup, and every row of a cell carries it "
        "because the visit is the cell's. For a runtime that loads its weights at startup it "
        "is an ordinary warm request; for one that loads them lazily it is where the load "
        "landed. cold load s and first request s are the two halves of what a cold start "
        "costs — a cross-runtime load comparison uses their sum — and a first request more "
        f"than {DEFERRED_LOAD_EXCESS_S:g} s above the median of the requests the workload that "
        "made it went on to measure says so in that row's notes rather than being read as "
        "warm-up noise. A row that did not make that request says nothing about it: the two "
        "numbers would come from different workloads, and the gap between them would be this "
        "harness comparing two shapes.",
        "",
        "drift % is how far the cell moved across its own measurement window: the median decode "
        "rate of the first half of its measured requests against the second half's. Both signs "
        "are readings. A negative one is a cell that ran slower late than early — the thermal "
        "curve the interleave exists to expose. A positive one is a cell that had not finished "
        "warming up, so its decode rate is an early-window rate; that is the direction every "
        "column of the 2026-09-15 grid leaned, and in the mlx-lm column it ranged -1.3% to "
        "+28.4% between formats, which is not a common-mode offset a reader can subtract out. "
        f"Above {DRIFT_ANNOTATION_PCT:g}% either way the row says which of the two it was. It is "
        "not a floor: a cell that was still moving is ranked with the rest and annotated, "
        "because dropping it would delete the only row that says the window was too short. With "
        "the window split two rates against two, the direction is the finding and the magnitude "
        "is noisy.",
        "",
        f"p90 and p99 need at least {MIN_PERCENTILE_N} samples; below that the cell shows "
        "`—` and the row says `n=<k>` rather than inventing a percentile.",
        "",
        f"decode tok/s, ITL and prefill tok/s need at least {MIN_CONTENT_DELTAS} content deltas in the "
        "stream: a runtime that returns the whole completion in one delta has no inter-token "
        "interval, so the cell shows `—` and the row says why. A response that arrived whole "
        "in one delta also makes that cell's TTFT a time-to-completion rather than a "
        "time-to-first-token; the value is kept, and the row's notes label it.",
    ]


# --- the joined grid ------------------------------------------------------------------------


# What a pin is worth on a header that predates it. `concurrency`, `prompt_tokens` and
# `cache_state` are the three that arrived after runs existed: every header written before them
# drove its requests one at a time and sized no prompt at all and ran each runtime's own cache
# default, so `1`, `None` and `None` are what those runs did rather than defaults standing in
# for something unknown -- which is what separates them from an absent `temperature`, whose
# absence is a header this guard cannot compare. `cache_state`'s `None` is the one that matters
# most here: an absent pin is not `"off"`, because the runs it stands for were not uniform --
# the Osaurus grid columns ran with its prefix cache ON -- so reading the absence as a state
# would fold two different cache states into one column and call them a sweep.
ABSENT_PINS = {"concurrency": 1, "prompt_tokens": None, "cache_state": None}


def _check_pins(runs: list[tuple], *, varying: str | None = None) -> None:
    """Guard 1: every column was measured under the same pins, down to the prompts.

    Every header pin is compared one by one and so is every workload's ``messages`` and
    ``max_tokens``, because columns that answered different prompts are not one grid. No
    prompt is printed in the refusal: the prefill prompt is 6.5 kB of prose, and naming the
    field is what a reader needs to find the difference themselves.

    A pin the header does not carry is read through ``ABSENT_PINS`` when that absence is
    itself the fact -- see its comment -- so a column measured before a pin existed joins a
    column that pinned the value that absence means, and is refused against any other.

    *varying* is the one pin a caller's join permits its runs to disagree about -- a Phase 6
    sweep's swept pin -- and it is the only field skipped; the grid passes nothing and so
    compares every one of them. `prompt_tokens` carries one further relaxation: a prompt length
    IS the prompt, so a workload's ``messages`` go uncompared when that is what the runs are
    sweeping, and every other field of every shape still is.
    """
    if len(runs) < 2:
        return
    reference_label, reference = runs[0][0], runs[0][1]
    for label, header, _rows in runs[1:]:
        for field in PIN_FIELDS:
            if field == varying:
                continue
            pinned = reference.get(field, ABSENT_PINS.get(field))
            held = header.get(field, ABSENT_PINS.get(field))
            if pinned != held:
                raise ValueError(
                    f"the pins disagree: {reference_label} pinned {field}={pinned!r} and "
                    f"{label} pinned {field}={held!r}; columns measured under different pins "
                    "are not one grid"
                )
        _check_workload_pins(
            reference_label,
            reference,
            label,
            header,
            ignore_messages=varying == "prompt_tokens",
        )


def _check_workload_pins(
    label_a: str,
    header_a: dict,
    label_b: str,
    header_b: dict,
    *,
    ignore_messages: bool = False,
) -> None:
    """The workload half of guard 1: the same shapes, with the same prompts and caps.

    *ignore_messages* is the prompt-length pin's relaxation and no other caller's: a sweep of
    prompt lengths is the one join whose columns are meant to answer prompts of different
    lengths, so their ``messages`` go uncompared while the set of shapes and every
    ``max_tokens`` are still held to each other. The relaxation belongs to the pin rather than
    to the caller's convenience -- a concurrency sweep whose columns answered different prompts
    is refused like any other grid.
    """
    shapes_a, shapes_b = _shapes(header_a), _shapes(header_b)
    if set(shapes_a) != set(shapes_b):
        raise ValueError(
            f"the pins disagree: the workloads differ between {label_a} "
            f"({sorted(shapes_a)}) and {label_b} ({sorted(shapes_b)}); columns that measured "
            "a different set of shapes are not one grid"
        )
    for workload_id, shape in shapes_a.items():
        for field in ("messages", "max_tokens"):
            if ignore_messages and field == "messages":
                continue
            if shape.get(field) != shapes_b[workload_id].get(field):
                raise ValueError(
                    f"the pins disagree: workload `{workload_id}` pinned a different "
                    f"{field} in {label_a} and {label_b}; columns that answered different "
                    "prompts are not one grid"
                )


def _shapes(header: dict) -> dict:
    """A header's workloads by id, which is how one run's shapes are matched to another's."""
    return {shape.get("id"): shape for shape in header.get("workloads") or ()}


def _check_cells_appear_once(runs: list[tuple]) -> None:
    """Guard 2: no ``(label, runtime, workload_id)`` measured by two run directories.

    There is no "latest wins" rule: which run is newer is not which run is right, so a cell
    measured twice is ambiguous rather than superseded and the join refuses instead of
    choosing one of the two.
    """
    seen: dict[tuple, str] = {}
    for label, _header, rows in runs:
        for row in rows:
            key = (row.get("label"), row.get("runtime"), row.get("workload_id"))
            if key in seen:
                raise ValueError(
                    f"duplicate cell: (label, runtime, workload_id) = {key!r} appears in both "
                    f"{seen[key]} and {label}; two run directories measured one cell, and "
                    "there is no latest-wins rule because which run is newer is not which run "
                    "is right"
                )
            seen[key] = label


def _check_one_artifact_per_label(runs: list[tuple]) -> None:
    """Guard 3: one format label, one artifact — across columns as well as inside a table.

    Two rows agreeing on the format's name and pointing at different bytes are two formats.
    ``_held_constant`` makes that check within one table; this makes it across the grid.
    """
    seen: dict[str, tuple] = {}
    for label, _header, rows in runs:
        for row in rows:
            name, artifact = row.get("label"), row.get("artifact_dir")
            if not name or not artifact:
                continue
            if name in seen and seen[name][0] != artifact:
                previous, previous_run = seen[name]
                raise ValueError(
                    f"artifact_dir disagrees for format `{name}`: {previous_run} measured "
                    f"{previous} and {label} measured {artifact}; one format name pointing at "
                    "two artifacts is two formats"
                )
            seen.setdefault(name, (artifact, label))


def _check_one_version_per_runtime(runs: list[tuple]) -> None:
    """Guard 4: one runtime, one version, across columns.

    Two *different* runtimes at different versions is the grid working as intended. The same
    runtime at 0.25.3 in one directory and 0.25.4 in another is the grid's held-constant
    variable moving — Osaurus measured 1.15x across exactly that step — so it is refused
    rather than joined. A row carrying no version never started a runtime, and a cell that
    never ran cannot disagree about which build the others ran on.
    """
    seen: dict[str, tuple] = {}
    for label, _header, rows in runs:
        for row in rows:
            runtime, version = row.get("runtime"), row.get("runtime_version")
            if not runtime or not version:
                continue
            if runtime in seen and seen[runtime][0] != version:
                previous, previous_run = seen[runtime]
                raise ValueError(
                    f"runtime_version disagrees for runtime `{runtime}`: {previous_run} ran "
                    f"{previous} and {label} ran {version}; the same runtime at two versions "
                    "means the column's held-constant variable moved"
                )
            seen.setdefault(runtime, (version, label))


def _columns(runs: list[tuple]) -> list[dict]:
    """The grid's columns: one per runtime name, in the order the runs arrived.

    A column is a runtime, and it records the run directory (or directories) that measured it
    so the provenance block can name them. A run that measured two runtimes contributes to two
    columns; two runs that measured the same one share it, which guard 2 has already refused
    where they measured the same cell.
    """
    columns: dict[str, dict] = {}
    for run_label, _header, rows in runs:
        for row in rows:
            runtime = row.get("runtime")
            if not runtime:
                continue
            column = columns.setdefault(runtime, {"runtime": runtime, "runs": [], "version": None})
            if run_label not in column["runs"]:
                column["runs"].append(run_label)
            if column["version"] is None and row.get("runtime_version"):
                column["version"] = row["runtime_version"]
    return list(columns.values())


def _format_labels(runs: list[tuple]) -> list[str]:
    """The grid's rows: the format labels any run measured, in the order they arrived.

    The whole grid shares one set of rows and one set of columns, so a reader who has found a
    format in one table finds it in the same place in the next. A label nothing measured never
    becomes a row: a row of `—` says a combination does not exist, and a format no runtime
    loaded is not a combination.
    """
    labels: list[str] = []
    for _run_label, _header, rows in runs:
        for row in rows:
            label = row.get("label")
            if label and label not in labels:
                labels.append(label)
    return labels


def _provenance(runs: list[tuple], columns: list[dict]) -> list[str]:
    """Per column its run directory, runtime and version, then the pins they all share.

    This is the block that makes the join legal rather than assumed: it names the directory
    behind every column and the fields guard 1 compared them on, so a reader holding the same
    ``results.jsonl`` files can rebuild the grid and check the refusals were not needed.
    """
    lines = [
        "## Provenance",
        "",
        "A column in the tables below is one runtime, and each is one run directory named here "
        "with the version it measured. The lines under the table are the pins every column "
        "shared; the join guard compared them field by field, and the workload line names the "
        "shapes whose prompts were compared with them.",
        "",
        "| runtime | run directory | version |",
        "|---|---|---|",
    ]
    for column in columns:
        lines.append(
            f"| {_text(column['runtime'])} | {', '.join(column['runs'])} | "
            f"{_text(column['version'])} |"
        )
    lines.append("")
    if runs:
        header = runs[0][1]
        pins = ", ".join(f"{field} `{_text(header.get(field, ABSENT_PINS.get(field)))}`" for field in PIN_FIELDS)
        lines.append(f"Pins all columns share: {pins}.")
        lines.append("")
        shapes = ", ".join(
            f"`{_text(shape.get('id'))}` (max_tokens {_text(shape.get('max_tokens'))})"
            for shape in header.get("workloads") or ()
        )
        lines.append(f"Workloads all columns ran, with identical messages: {shapes}.")
        lines.append("")
    return lines


def _grid_table(rows: list[dict], labels: list[str], columns: list[dict], rank: str) -> str:
    """One workload's grid: format labels down, runtime names across, one entry per cell."""
    index = {}
    for row in rows:
        index.setdefault((row.get("label"), row.get("runtime")), row)

    header = "| format | " + " | ".join(_text(c["runtime"]) for c in columns) + " |"
    divider = "|" + "---|" * (header.count("|") - 1)
    lines = [header, divider]
    for label in labels:
        cells = [_text(label)]
        cells += [_entry(index.get((label, column["runtime"])), rank) for column in columns]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _entry(row: dict | None, rank: str) -> str:
    """One grid entry, in one of the four states a cell can be in.

    A combination no run measured is ``—`` and a cell that ran without clearing a floor is
    ``FAIL``: they are different facts about a cell, and rendering them alike is how a rag
    comes to read as a failure. ``N/A`` is measure's word for a cell that never ran here, the
    same state the floors print as "not measured"; anything else that is not PASS ran and did
    not clear one. A PASS entry carries its number, and a drifting one carries its marker
    beside it.

    A cell that cleared every floor and still has no value for *this* metric is the fourth
    state and gets its own word. ``_number`` renders ``None`` as ``—``, which would file it
    with the combinations nobody ran — but it did run, it produced language, and it cleared
    the floors; what is missing is one metric's domain, not the cell. `order_rows` already
    holds that distinction and ranks such a row last with a note rather than excluding it,
    and the grid would be the one place it collapsed.

    A row measured short of its pin carries the count beside the number, the way an annotated
    cell carries its drift percentage: the number is the row's own and the count says how much
    of the window it stands on, which the joined tables have no notes column to say in words.
    """
    if row is None or row.get("status") == "N/A":
        return "—"
    if row.get("status") != "PASS":
        return "FAIL"
    if row.get(rank) is None:
        return "no value"
    number = _rank_number(row, rank)
    markers = []
    drift = _drift_marker(row)
    if drift is not None:
        markers.append(f"drift {drift}%")
    short = _short_marker(row)
    if short is not None:
        markers.append(short)
    return number if not markers else f"{number} ({') ('.join(markers)})"


def _short_marker(row: dict) -> str | None:
    """The count a short entry carries, or ``None`` when the window was full.

    The threshold is `_row`'s to apply, not this function's: the entry annotates exactly the
    rows that earned the note, so the grid cannot print a count the leaderboard leaves alone.
    It is a marker and never a state: the cell cleared every floor, produced language, and is
    ranked with the rest -- dropping it would delete the only row that says the window was
    short.
    """
    if not row.get("short_note"):
        return None
    return f"n={row['measured_batches']} of {row['measured_pin']}"


def _rank_number(row: dict, rank: str) -> str:
    """The row's ``rank`` metric, formatted exactly as the table and the card format it."""
    if rank == "disk_bytes":
        return _bytes(row.get(rank))
    return _number(row.get(rank), _RANK_PLACES[rank])


def _drift_marker(row: dict) -> str | None:
    """The marker an annotated entry carries, or ``None`` when the cell is not annotated.

    The threshold is ``_drift_note``'s to apply, not this function's: it makes the
    ``DRIFT_ANNOTATION_PCT`` call from the same drift measure recorded, so the grid cannot
    annotate a cell the leaderboard leaves alone. The absence a measured cell with no window
    to compare gets is not a finding, and neither is a cell that held still.
    """
    note = _drift_note(row.get("drift"), row.get("n_measured") or 0)
    if note is None or note == _DRIFT_ABSENCE:
        return None
    return _drift_cell(row)


def _readings(groups: list[tuple], columns: list[dict], labels: list[str], rank: str) -> list[str]:
    """The two axis readings, one block per workload, and the recommendation that closes it.

    Each entry is one column's formats or one row's runtimes, ordered by ``rank`` and by
    ``order_rows`` — the same function the leaderboard orders its tables with, so a reading
    and a table cannot disagree about which cell came first. A column compares quantization
    under one runtime, a row compares serving under one format, and neither says anything
    about the other; that is what keeps the two axes from being read as one comparison. The
    recommendation is the single line that spans both, and it is labelled as what that makes
    it.
    """
    lines = [
        "## Axis readings",
        "",
        "Both axes are in the tables above and are read apart from each other. A column is one "
        "runtime across many formats — the format axis. A row is one format across many "
        "runtimes — the runtime axis. Every line below is one workload's ordering by "
        f"`{rank}` ({_direction(rank)}), and no line mixes the two.",
        "",
    ]
    for workload, rows in groups:
        lines += [f"### Workload `{workload}`", ""]
        lines += [f"**Format axis — one runtime, its formats ordered.** {CAVEAT['format']}.", ""]
        for column in columns:
            group = [row for row in rows if row.get("runtime") == column["runtime"]]
            lines.append(f"- `{_text(column['runtime'])}`: {_ordering(group, rank, 'label')}")
        lines.append("")
        lines += [f"**Runtime axis — one format, its runtimes ordered.** {CAVEAT['runtime']}.", ""]
        if rank in CROSS_RUNTIME_UNCOMPARABLE:
            lines += [
                f"> **`{rank}` is not one quantity across runtimes.** "
                f"{CROSS_RUNTIME_UNCOMPARABLE[rank]}",
                "",
            ]
        for label in labels:
            group = [row for row in rows if row.get("label") == label]
            lines.append(f"- `{_text(label)}`: {_ordering(group, rank, 'runtime')}")
        lines += ["", _recommendation(rows, rank), ""]
    return lines


def _ordering(rows: list[dict], rank: str, key: str) -> str:
    """One axis reading's ordering, with what kept each unranked cell out of it.

    The position is the row's own ``rank``, so the reading is checkable against the table.
    A cell that failed a floor or carries no value for the metric is named rather than
    dropped: it is a result, and it is the one the ordering could not include.
    """
    if not rows:
        return "—"
    parts = []
    for row in order_rows(rows, rank):
        name = f"`{_text(row.get(key))}`"
        if row.get("rank") is not None:
            parts.append(f"{name} ({row['rank']})")
        elif row.get("rankable"):
            parts.append(f"{name} (no {rank})")
        else:
            parts.append(f"{name} ({_text(row.get('exclusion'))})")
    return " > ".join(parts)


def _recommendation(rows: list[dict], rank: str) -> str:
    """The best cell in one workload's grid, labelled as a recommendation.

    It is the one line in the document that spans both axes, and that is exactly why it cannot
    be read as an attribution: the cell that won won under one format and one runtime at once,
    and the number carries no way to split the win between them. Which of the two earned it is
    what the column and the row above this line are for.
    """
    ranked = [row for row in order_rows(rows, rank) if row.get("rank") is not None]
    if not ranked:
        return (
            f"**Recommendation — none.** No cell in this grid cleared every floor at `{rank}`, "
            "so there is no best cell to name."
        )
    best = ranked[0]
    return (
        "**Recommendation — the best cell across this grid, and a recommendation rather than "
        f"an attribution.** `{_text(best.get('cell_id'))}` ({_text(best.get('runtime'))} / "
        f"{_text(best.get('label'))}) leads all {len(ranked)} ranked cells at `{rank}` = "
        f"{_rank_number(best, rank)}. The cell won under one format and one runtime together, "
        "so this says which pair came first and not which of the two earned it — the format "
        "axis is its column above and the runtime axis is its row."
    )


# --- the Phase 6 sweep ----------------------------------------------------------------------

# The header pins a sweep may vary, and the whole of the list. A cell is `(format, runtime)`,
# and all three of these are properties of how a run *drove* its cells rather than of a cell:
# that is why they are header pins, why `--study` can name none of them, and why a sweep is N
# runs differing in exactly one of them. Anything else a header carries is held by guard 1 like
# any other pin, so a "sweep" of `temperature` would be a grid with a pin quietly uncompared.
SWEEP_PINS = ("concurrency", "prompt_tokens", "cache_state")

# What each swept pin holds, in words a reader of the rendered sweep can act on.
SWEPT_PIN = {
    "concurrency": "requests issued together in one batch",
    "prompt_tokens": "the length the prompt was sized to, as a target and the count the "
    "serving tokenizer achieved",
    "cache_state": "whether the runtime's prefix/KV reuse was off or on, as the start command "
    "pinned it",
}

# What each sweep holds constant while the pin moves, and -- for the one pin that moves
# something else with it -- exactly how far that goes.
SWEEP_HELD = {
    "concurrency": (
        "Every other pin is identical across these runs, and so is every workload down to its "
        "prompt and its cap: the join guard compared them field by field, so a column differs "
        "from its neighbour in concurrency and nothing else."
    ),
    "prompt_tokens": (
        "Every other pin is identical across these runs and every workload keeps its "
        "`max_tokens`; the prompts themselves differ, and that is what this pin holds. A "
        "prompt-length sweep is the one join whose columns are meant to answer prompts of "
        "different lengths, so a workload's `messages` is the single field the guard relaxes, "
        "and only for this pin."
    ),
    "cache_state": (
        "Every other pin is identical across these runs, and so is every workload down to its "
        "prompt and its cap -- the runs sent byte-identical prompts and differ only in whether "
        "the runtime's prefix/KV reuse was off or on, which is the single field the guard "
        "skips. No prompt is relaxed for this pin: a cache sweep's whole subject is the same "
        "prompt answered twice."
    ),
}

# A swept pin's values in the order they are read, for the one pin whose order is not its
# numeric one. A cache sweep's reading is the difference between the same prompt answered cold
# and answered warm, so `off` is the baseline column and `on` is the reading against it; the
# order is pinned here rather than left to the words' spelling, which happens to sort the same
# way today and would stop the moment a third value arrived.
SWEEP_VALUES = {"cache_state": ("off", "on")}


# The sentence a sweep of concurrency carries, verbatim. Measured, plan 06-01a: oMLX at N=8
# swung 65.3-81.0 tok/s of per-request decode rate across 16 batches with no trend and never
# settled, while its per-batch aggregate settled at batch 12. So the drift a concurrent cell
# prints is queueing variance in a per-request rate, and the annotation's own reading of a
# positive change -- insufficient warmup -- is not the reading there.
CONCURRENCY_DRIFT_SENTENCE = (
    "At concurrency > 1, measured drift reads per-request rates: positive drift means the "
    "per-request rate was still moving, not that the cell was under-warmed."
)


def render_sweep(
    runs: list[tuple[str, dict, list[dict]]], *, varying: str, rank: str = DEFAULT_RANK
) -> str:
    """The Phase 6 sweep: one table per workload, cells down and the swept pin's values across.

    *runs* is one ``(run label, run header, rows)`` per run directory, exactly the shape and the
    meaning :func:`render_grid` takes: *rows* is ``summarize``'s output, no file is read here,
    and no figure is re-derived. What differs is which one field the runs are allowed to
    disagree about.

    A **cell** is `(format, runtime)`, and *varying* is neither of those: `concurrency`,
    `prompt_tokens` and `cache_state` are properties of how a run drove its cells, so they live
    in the header. A sweep is N run directories differing in exactly that pin, joined
    afterwards. Guard 1 is the grid's, with the swept pin skipped, and beside it sit the two
    refusals a sweep needs and a grid has no use for: a pin holding one value across every run
    -- a table with one column is not a sweep -- and the same cell measured at one value by two
    run directories.

    `varying="prompt_tokens"` is the one relaxation, and the refusal it does not lift is worth
    reading beside it. Its pin is ``{"target": N, "achieved": M}`` and its runs measure the
    single `prefill` shape, so their prompts are *supposed* to differ: a workload's `messages`
    are dropped from the comparison for this pin, and every other field of every shape is still
    compared. Two runs that pinned one target are one column whatever their tokenizers achieved
    — which is why the pin's key is its target — and two runs whose *other* shapes disagree are
    still refused. `cache_state` relaxes nothing: its columns are meant to answer the same
    prompt twice, once cold and once warm, so a pair of runs whose prompts differ is refused
    like any other grid.

    The columns ascend, because that is the reading: a prompt that got longer or batches that
    got wider says nothing while the table is in command-line order. A pin with an order of its
    own reads in that order — `cache_state`'s `off` before its `on`, the cold column first
    because it is the baseline the warm one is read against. Entries are the ``rank`` metric,
    formatted by the same functions the grid formats its own with, so `—`, `FAIL` and
    `no value` mean here exactly what they mean there.

    A run that issued more than one request at a time, or a sweep of concurrency, carries
    ``CONCURRENCY_DRIFT_SENTENCE``: the drift beside a concurrent cell's per-request rate is not
    the unfinished warm-up that annotation was written for.
    """
    if varying not in SWEEP_PINS:
        raise ValueError(
            f"varying must be one of {SWEEP_PINS}, not {varying!r}: a sweep varies one run "
            "header pin, and a cell's two variables are what `--study` names"
        )
    if rank not in RANK_METRICS:
        raise ValueError(_rank_error(rank))

    runs = [(label, dict(header or {}), list(rows)) for label, header, rows in runs]
    _check_pins(runs, varying=varying)
    _check_sweep_varies(runs, varying)
    _check_sweep_cells_appear_once(runs, varying)

    columns = _sweep_columns(runs, varying)
    cells = _sweep_cells(runs)
    index = _sweep_index(runs, varying)

    lines = [
        f"# Sweep — `{varying}` across {len(columns)} values in {len(runs)} run directories",
        "",
        f"One variable varied: the run header pin `{varying}` — {SWEPT_PIN[varying]}. "
        f"{SWEEP_HELD[varying]}",
        "",
        f"Each table is one workload and carries one metric: `{rank}` ({_direction(rank)}).",
        "",
        "| entry | means |",
        "|---|---|",
        "| a number | a measured cell that cleared every floor |",
        "| `no value` | a cell that cleared every floor and has no value for this metric; "
        "its run's leaderboard carries the note saying why |",
        "| `FAIL` | a measured cell that did not clear one |",
        "| `—` | a combination no run measured |",
        "",
    ]
    if varying == "concurrency" or any(
        _drove_more_than_one_request(header) for _label, header, _rows in runs
    ):
        lines += [f"> {CONCURRENCY_DRIFT_SENTENCE}", ""]
    lines += _sweep_provenance(runs, varying)

    for workload, _rows in _by_workload(
        [row for _label, _header, rows in runs for row in rows]
    ):
        lines += [
            f"## Workload `{workload}` — entries are `{rank}` ({_direction(rank)})",
            "",
            _sweep_table(workload, cells, columns, index, rank, varying),
            "",
        ]
    lines += [
        "## Notes",
        "",
        "The notes below are the leaderboard's own, unchanged, and govern every figure here. "
        "Where one refers to the metric card, that card is in each run's own `leaderboard.md`: "
        "the sweep joins published rows and re-renders none of their numbers.",
        "",
    ]
    lines += _footnotes()
    return "\n".join(lines) + "\n"


def _pin_value(header: dict, varying: str):
    """The swept pin's value on this header, an absent pin read as what that absence means.

    `concurrency`'s absence is ``1``: every run written before the pin existed issued its
    requests one at a time, so that is the fact rather than a default standing in for something
    unknown. `prompt_tokens`'s is ``None``: those runs sized no prompt.
    """
    return header.get(varying, ABSENT_PINS.get(varying))


def _pin_key(header: dict, varying: str):
    """What a sweep's columns are keyed on: the pin's value, or its target where it has one.

    A `prompt_tokens` pin is ``{"target": 4096, "achieved": 4093}`` and the target is the length
    the run asked for. Keying the column on the whole dict would make two runs of one intended
    length two columns the moment their tokenizers landed a token apart -- and the achieved count
    is already printed beside the target, so the disagreement stays visible either way.
    """
    value = _pin_value(header, varying)
    if varying == "prompt_tokens" and isinstance(value, dict):
        return value.get("target")
    return value


def _pin_note(header: dict, varying: str) -> str:
    """One run's value of the swept pin, as a reader should see it beside its directory.

    A prompt pin is two numbers and both are printed: the target is what the run asked for and
    the achieved count is what its own tokenizer produced for the text it sent.
    """
    value = _pin_value(header, varying)
    if not isinstance(value, dict):
        return _text(value)
    target, achieved = value.get("target"), value.get("achieved")
    return _text(target) if achieved is None else f"{_text(target)} (achieved {achieved})"


def _drove_more_than_one_request(header: dict) -> bool:
    """Whether this run issued more than one request at a time.

    An absent pin is a run that issued them one at a time, so it is the ``1`` it means.
    """
    return (_pin_value(header, "concurrency") or 1) > 1


def _check_sweep_varies(runs: list[tuple], varying: str) -> None:
    """A sweep's pin has to actually vary, and a prompt pin is keyed on its target.

    One value across every run makes every one of them the same column, so there is no sweep to
    render and the join refuses rather than drawing a table with one column and calling it one.
    `prompt_tokens` is keyed on its **target**: the achieved count is a fact about a run's own
    tokenizer at that length, so two runs that pinned one target are one column whether or not
    their tokenizers landed on the same number -- and this is the only place that says so.
    """
    values: dict = {}
    for label, header, _rows in runs:
        values.setdefault(_pin_key(header, varying), []).append((label, _pin_note(header, varying)))
    if len(values) >= 2:
        return
    named = "; ".join(
        f"{label} pinned {value}" for pinned in values.values() for label, value in pinned
    )
    raise ValueError(
        f"the swept pin does not vary: {varying} is the same value in every one of these runs "
        f"({named or 'no run directories were named'}); a sweep is N run directories that "
        "differ in exactly this pin, and one value across all of them is not a sweep"
    )


def _check_sweep_cells_appear_once(runs: list[tuple], varying: str) -> None:
    """Guard 2: no ``(cell, workload, pin value)`` measured by two run directories.

    The pin value joins the grid's key because a sweep's columns are the pin: one cell at two
    values is the table working as intended, and one cell at one value twice is ambiguous rather
    than superseded. There is no latest-wins rule here either -- which run is newer is not which
    run is right -- so the join refuses and names both directories.
    """
    seen: dict[tuple, str] = {}
    for label, header, rows in runs:
        value = _pin_key(header, varying)
        for row in rows:
            key = (row.get("label"), row.get("runtime"), row.get("workload_id"), value)
            if key in seen:
                raise ValueError(
                    f"duplicate cell: (label, runtime, workload_id, {varying}) = {key!r} "
                    f"appears in both {seen[key]} and {label}; two run directories measured one "
                    "cell at one value of the swept pin, and there is no latest-wins rule "
                    "because which run is newer is not which run is right"
                )
            seen[key] = label


def _sweep_columns(runs: list[tuple], varying: str) -> list[dict]:
    """The sweep's columns: one per value of the swept pin, smallest first.

    Ascending order is the reading rather than a tidiness: a prompt that got longer or batches
    that got wider says nothing across columns left in the order the directories happened to be
    named, and every other table in this project names its ordering for the same reason. A pin
    with a named order of its own -- `cache_state`'s off-before-on -- reads in that order, which
    is why the ordering is a property of the pin rather than of the Python type its values
    happen to be. A column carries the achieved counts its runs landed on, and a column two runs
    share prints both of them rather than the first.
    """
    columns: dict = {}
    for _label, header, _rows in runs:
        key = _pin_key(header, varying)
        column = columns.setdefault(key, {"key": key, "achieved": []})
        achieved = _achieved(header, varying)
        if achieved is not None and achieved not in column["achieved"]:
            column["achieved"].append(achieved)
    return sorted(columns.values(), key=lambda column: _ascending(column["key"], varying))


def _achieved(header: dict, varying: str):
    """The count a prompt pin achieved, or ``None`` for a pin that has no such field."""
    value = _pin_value(header, varying)
    return value.get("achieved") if isinstance(value, dict) else None


def _ascending(value, varying: str):
    """A sort key for one swept pin's values: its own order, an absent value last.

    A pin with a named order (`SWEEP_VALUES`) sorts by that order; every other pin's values are
    numbers and sort numerically. The only other thing a value can be is the absence of a pin
    the run predates, which sorts after every real value rather than raising.
    """
    order = SWEEP_VALUES.get(varying)
    if order is not None:
        return (value is None, order.index(value) if value in order else len(order))
    return (value is None, "" if value is None else value)



def _sweep_cells(runs: list[tuple]) -> list[str]:
    """The sweep's rows: every cell any run measured, in the order they arrived.

    A row is the cell's own id, `<format>__<runtime>`, because the columns are the pin and the
    row therefore has to carry the two things a cell is. A cell no run measured never becomes a
    row for the same reason a label never does in the grid: a row of `—` says a combination does
    not exist, and a cell nobody ran is not a combination.
    """
    cells: list[str] = []
    for _label, _header, rows in runs:
        for row in rows:
            cell_id = row.get("cell_id")
            if cell_id and cell_id not in cells:
                cells.append(cell_id)
    return cells


def _sweep_index(runs: list[tuple], varying: str) -> dict:
    """``(cell, workload, pin value)`` -> the row measured there, across every run.

    Guard 2 has already refused a key two run directories both wrote, so nothing here is
    overwritten: a ``setdefault`` that silently dropped a row would be the exact ambiguity that
    guard exists to refuse.
    """
    index: dict[tuple, dict] = {}
    for _label, header, rows in runs:
        key = _pin_key(header, varying)
        for row in rows:
            index.setdefault((row.get("cell_id"), row.get("workload_id"), key), row)
    return index


def _sweep_provenance(runs: list[tuple], varying: str) -> list[str]:
    """Per run directory its value of the swept pin, then the pins the runs held in common.

    This is the block that makes the join legal rather than assumed: it names the directory
    behind every column of every table and the one field they were allowed to differ on, and it
    prints the pins guard 1 compared them on, so a reader holding the same ``results.jsonl``
    files can rebuild the sweep and check that the refusals were not needed.
    """
    lines = [
        "## Provenance",
        "",
        f"A column in the tables below is one value of `{varying}`, and every run directory "
        "behind the sweep is named here with the value it pinned. The lines under the table are "
        "the pins every run shared -- the join guard compared them field by field -- and the "
        "workload line names the shapes it compared with them.",
        "",
        f"| run directory | `{varying}` |",
        "|---|---|",
    ]
    for label, header, _rows in runs:
        lines.append(f"| {_text(label)} | {_pin_note(header, varying)} |")
    lines.append("")
    if runs:
        header = runs[0][1]
        pins = ", ".join(
            f"{field} `{_text(header.get(field, ABSENT_PINS.get(field)))}`"
            for field in PIN_FIELDS
            if field != varying
        )
        lines.append(
            f"Pins all runs shared, with `{varying}` the one pin they differ on: {pins}."
        )
        lines.append("")
        shapes = ", ".join(
            f"`{_text(shape.get('id'))}` (max_tokens {_text(shape.get('max_tokens'))})"
            for shape in header.get("workloads") or ()
        )
        lines.append(
            f"Workloads all runs ran: {shapes}."
            if varying == "prompt_tokens"
            else f"Workloads all runs ran, with identical messages: {shapes}."
        )
        lines.append("")
    return lines


def _sweep_table(
    workload: str, cells: list[str], columns: list[dict], index: dict, rank: str, varying: str
) -> str:
    """One workload's sweep: cells down, the swept pin's values across, one entry per cell.

    An entry is the row's ``rank`` metric in the same four states the grid renders it in, by the
    same function, so a combination no run measured (`—`), a cell that ran and did not clear a
    floor (`FAIL`) and one that cleared every floor without a value for this metric (`no value`)
    stay three facts here as they are there.
    """
    header = "| cell | " + " | ".join(_sweep_head(column, varying) for column in columns) + " |"
    divider = "|" + "---|" * (header.count("|") - 1)
    lines = [header, divider]
    for cell in cells:
        entry = [_text(cell)]
        entry += [
            _entry(index.get((cell, workload, column["key"])), rank) for column in columns
        ]
        lines.append("| " + " | ".join(entry) + " |")
    return "\n".join(lines)


def _sweep_head(column: dict, varying: str) -> str:
    """A column head: the pin's value, and for a prompt pin the count achieved beside it.

    The target is what the run asked for and the achieved count is what its tokenizer produced,
    and both are printed because the pin is only checkable against the text that was sent. A
    column whose runs landed on different counts prints all of them: the runs disagreed, and a
    head that picked one of them would be the join choosing a number on their behalf.
    """
    if varying != "prompt_tokens":
        return _text(column["key"])
    achieved = ", ".join(str(count) for count in column["achieved"])
    if not achieved:
        return _text(column["key"])
    return f"{_text(column['key'])} (achieved {achieved})"


def _number(value, places: int) -> str:
    return "—" if value is None else f"{value:.{places}f}"


def _bytes(value) -> str:
    return "—" if value is None else f"{value:,}"


def _text(value) -> str:
    return "—" if value is None or value == "" else str(value)
