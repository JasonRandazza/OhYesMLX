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
weighted: coherence, and every published metric present. A row that fails one is
excluded from the ordering, still printed, and named against the floor that kept it out —
an excluded cell is a result, not an absence.

Every raw observation goes into ``results.jsonl``, so every number here stays recomputable
from the file.
"""

from __future__ import annotations

import statistics
from typing import TYPE_CHECKING

from ohyesmlx import measure, transport

if TYPE_CHECKING:  # measure.py owns the shapes; report reads a CellResult and two strings.
    from ohyesmlx.measure import CellResult

AXES = ("runtime", "format")

MIN_PERCENTILE_N = 5

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
FLOORS = ("coherence", "metrics")

# A floor's verdict. "not reached" is a gate an earlier failure never got to and "not
# measured" is a cell that never ran here. Neither is a pass, and neither excludes a row: a
# floor nobody asked is not a floor to rank against, it is a hole to print.
FLOOR_CLEARED = frozenset({"pass"})

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
    "e2e_p50_s": "lower",
    "e2e_p90_s": "lower",
    "e2e_p99_s": "lower",
}

DEFAULT_RANK = "decode_tps"

# The rank metrics the drift marker qualifies: `decode_tps`, and anything computed from decode
# rates. `measure.measured_drift` compares per-request decode rates, so the percentage is one
# metric's movement and the marker's whole claim is "this cell's decode rate moved x% across its
# own window". Beside a metric that is not a decode rate it makes that claim about a different
# number, which is how a sweep read on `ttft_p50_s` came to print `drift +11.5%` beside a
# first-token latency: the cell's decode rate moved and its TTFT did not, and nothing in the
# marker's words let a reader tell the two apart.
#
# Nothing else in `RANK_METRICS` is a decode rate or computed from one, and each neighbour is
# excluded for a reason of its own. `itl_s` is read off the same decode window, but as that
# window's interval -- the rate's reciprocal -- so its own movement carries the opposite sign:
# `drift +17.0%` beside it would report an inter-token gap that grew where the rate rising is
# the gap shrinking. `aggregate_tps` divides a batch's completion tokens by the wall time it
# took, prefill and queueing included, and at concurrency > 1 the per-request rate it is read
# against is the one thing it deliberately is not. `prefill_tps` is prompt over TTFT, and the
# rest are latency, memory and disk. A metric added to `RANK_METRICS` later belongs here only
# when it is a decode rate or is computed from one.
DECODE_DERIVED_RANKS = frozenset({"decode_tps"})

_UNPUBLISHED_FIELDS = frozenset({
    "ttft_p50_s", "ttft_p90_s", "ttft_p99_s", "e2e_p50_s", "e2e_p90_s", "e2e_p99_s",
    "itl_s", "decode_tps",
    "drift_pct", "aggregate_tps", "prefill_tps",
})


# Every value the row carries, in one place, so the card cannot drift from the table.
CARD_FIELDS = (
    ("ttft_p50_s", 3),
    ("ttft_p90_s", 3),
    ("ttft_p99_s", 3),
    ("e2e_p50_s", 3),
    ("e2e_p90_s", 3),
    ("e2e_p99_s", 3),
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
# exists, and six did: `concurrency` (plan 06-01b), `prompt_tokens` (plan 06-01c),
# `cache_state` (plan 06-02), `kv_quant` (study 03-05), `mtp_depth` and `stream_experts`
# (studies 03-06 and 03-03). The first two were pinned in the header and left out of this
# tuple, so an N=8 run and a 32k-prompt run would each have joined a grid of their opposite
# without a word; the last four are here from the day they were written. Every one of the six
# is a property of how the run drove its cells, which is exactly why the grid may not join runs
# that disagree about it -- and the last four are two mechanisms' two questions each, so two
# runs of one cell under different codecs, depths or streaming states are a sweep's columns and
# never one grid.
PIN_FIELDS = (
    "temperature",
    "seed",
    "warmup",
    "measured",
    "cooldown_s",
    "concurrency",
    "prompt_tokens",
    "cache_state",
    "kv_quant",
    "mtp_depth",
    "stream_experts",
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

# The rank metrics whose value depends on the timing channel — which stream the request was
# timed on — and so cannot carry a runtime-axis ordering across rows that do not share one.
# Jason's decision, 2026-09-24: the refusal `CROSS_RUNTIME_UNCOMPARABLE` makes, for the same
# reason, one level down.
#
# The channel is which stream supplied an observation's `ttft_s`, `last_content_s` and
# `content_event_count`: the content deltas ordinarily, and the reasoning deltas when a runtime
# streamed its whole answer in that channel or mirrored it into content
# (`transport.timing_channel`, and "Which channel is the output stream" in
# docs/interfaces.md). So a row timed on reasoning measures the model's first token out of it,
# and one timed on content measures the first *content* token — which on a thinking model lands
# after the whole reasoning run, seconds later. Read side by side on a runtime axis those are
# two definitions of first-token latency, and the ordering would compare them rather than the
# runtimes. Within one channel the same column is one quantity and orders as it always did.
#
# `ttft_p50_s` is such a metric directly. `prefill_tps` is one because the code computes it
# from TTFT — `prompt_tokens / ttft_s`, `measure.prefill_tps` — so it divides a prompt by
# whichever span the row was timed on. Nothing else in `RANK_METRICS` is, and each neighbour is
# out for a reason of its own: `decode_tps` and `itl_s` are read off the window between
# `ttft_s` and `last_content_s`, two timestamps of one output stream, so within a row they are
# that stream's own and the 2026-09-24 decision leaves them rankable across a mixed group;
# `aggregate_tps` divides every completion token by wall-clock spans no channel moves; the rest
# are memory, disk and end-to-end latency. A metric added to `RANK_METRICS` later belongs here
# only when it is a first-token latency or is computed from one.
#
# Enforced in two places and named here once: `_ordering` withholds the runtime-axis positions
# where a group does not share one channel, `_channel_note` says so in the section, and
# `_recommendation` names no best cell from a workload whose rows mix channels. A
# partly-reasoning row is a channel of its own rather than either one — see `_mixes_channels`.
CHANNEL_DEPENDENT_RANKS = frozenset({"ttft_p50_s", "prefill_tps"})

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
    "e2e_p50_s": "percentile_note",
    "e2e_p90_s": "percentile_note",
    "e2e_p99_s": "percentile_note",
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


def summarize(results: list[CellResult], *, measured: int | None = None) -> list[dict]:
    """One row per (cell, workload): the contract's fields, joined from measure, the sampler
    and disk.

    Rows keep the order the cells came in. Observations are used exactly as measure
    recorded them — this module has no warmup marker to filter on, so keeping warmups out
    of a cell's summary is measure's job. Percentiles below ``MIN_PERCENTILE_N`` samples
    are omitted rather than guessed, and ``percentile_note`` says so; a request that
    streamed fewer than ``measure.MIN_CONTENT_DELTAS`` content deltas carries no rate to report, and
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

    A runtime-axis table ordered by a metric that is not one quantity across runtimes is the
    one case where the table prints values and no ordering, and the two refusals are the
    grid's own: ``CROSS_RUNTIME_UNCOMPARABLE``'s whatever the rows are, and
    ``CHANNEL_DEPENDENT_RANKS``' where the rows were not all timed on one channel. The rows
    are listed by ``_unpositioned`` with the rank column empty, and the refusal's note --
    ``_runtime_axis_note``, built from the same two texts the grid prints -- says why. The
    format axis holds one runtime, which is the condition the first refusal is about, so its
    table orders unchanged.

    A table ordered on a first-token latency carries ``CONCURRENCY_TTFT_SENTENCE`` when the
    rows it covers were driven more than one request at a time: at concurrency > 1 the figure
    is a queueing measurement, and the row's own ``concurrent`` says whether the run it came
    from drove batches at all.
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
    if rank in CHANNEL_DEPENDENT_RANKS and any(row.get("concurrent") for row in rows):
        lines += [f"> {CONCURRENCY_TTFT_SENTENCE}", ""]
    for workload, group in _by_workload(rows):
        lines += [
            f"## Workload `{workload}` — ordered by `{rank}` ({_direction(rank)})",
            "",
        ]
        if axis == "runtime" and _uncomparable_across_runtimes(group, rank):
            lines += [_runtime_axis_note(group, rank), ""]
            lines += [_table(_unpositioned(group, "runtime"), rank), ""]
        else:
            lines += [_table(order_rows(group, rank), rank), ""]
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

    An entry carries the drift marker only where the drift figure qualifies the number beside
    it, exactly as a sweep's entries do: ``measure.measured_drift`` compares per-request decode
    rates, so the marker rides only a rank in ``DECODE_DERIVED_RANKS`` and a table ordered on
    anything else prints its entries' numbers alone. The default rank is a decode rate's, so
    every published grid renders as it always has. Nothing is dropped from the record: the
    drift stays on the row, and each run's own leaderboard prints it beside the rate it
    qualifies.
    """
    if rank not in RANK_METRICS:
        raise ValueError(_rank_error(rank))
    runs = [(label, dict(header or {}), list(rows)) for label, header, rows in runs]
    _check_harness(runs)
    _check_known_runtime_versions(runs)
    _check_pins(runs)
    _check_cells_appear_once(
        runs,
        lambda _header, row: (row.get("label"), row.get("runtime"), row.get("workload_id")),
        key_fields="label, runtime, workload_id",
        twice="measured one cell",
    )
    _check_one_value_per_key(
        runs,
        field="artifact_dir",
        kind="format",
        key_of=lambda row: (row.get("label"), row.get("artifact_dir")),
        verb="measured",
        clause="one format name pointing at two artifacts is two formats",
    )
    _check_one_value_per_key(
        runs,
        field="runtime_version",
        kind="runtime",
        key_of=lambda row: (row.get("runtime"), row.get("runtime_version")),
        verb="ran",
        clause="the same runtime at two versions means the column's held-constant variable "
        "moved",
    )

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

    reasoning_note = (
        "A `reasoning timed` marker means TTFT and decode use the reasoning stream, not content."
    )
    marker_note = (
        "A cell whose drift moved more than "
        f"{DRIFT_ANNOTATION_PCT:g}% across its own window carries its marker beside its "
        "number, the same marker the leaderboard prints beside the rate it qualifies."
        if rank in DECODE_DERIVED_RANKS
        else "A cell whose drift moved more than "
        f"{DRIFT_ANNOTATION_PCT:g}% across its own window carries no marker in this table: "
        "the marker states a decode rate's movement and every entry here carries its "
        f"`{rank}` alone. Each run's own leaderboard prints it beside the rate it qualifies."
    )
    lines += [
        f"Each table is one workload and carries one metric: `{rank}` "
        f"({_direction(rank)}).",
        "",
        *ENTRY_LEGEND,
        "The matrix is ragged by design — no runtime loads every format — so `—` is ordinary "
        "and does not read as a failure. " + marker_note,
        reasoning_note,
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
        "listed beside the figures derived from them.",
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
    unpublished = _not_published_note(row)
    for field, places in CARD_FIELDS:
        value = row.get(field)
        if unpublished and field in _UNPUBLISHED_FIELDS:
            shown, note = "—", unpublished
        else:
            shown = _bytes(value) if field == "disk_bytes" else _number(value, places)
            note = _card_note(row, field, rank)
        lines.append(_card_row(field, shown, note))
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


def _not_published_note(row: dict) -> str | None:
    status = row.get("status")
    return None if status == "PASS" else f"not published: {status} row"


def _card_row(field: str, value: str, note: str | None = None) -> str:
    return f"| {field} | {value} | {note or ''} |"


def _card_note(row: dict, field: str, rank: str) -> str | None:
    """What a card row has to say for itself: its caveat, why it is empty, or that it is the
    metric the ordering used."""
    notes = []
    if field == "ttft_p50_s":
        notes.append(row.get("reasoning_timed_note"))
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
    # End-to-end latency: request sent -> stream closed, for requests that came back only.
    e2e = [o.total_s for o in samples]
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
    too_few = sum(1 for count in deltas if count < measure.MIN_CONTENT_DELTAS)
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
        # Whether this row's run drove more than one request at a time, read off the one record
        # that says so: a batch span is taken only around a batch of more than one request, so a
        # row with spans was driven concurrently and a sequential one has none
        # (``CellResult.batch_spans``). Not a figure and never ranked -- the queueing sentences
        # the renders print read it, because a concurrent TTFT is a different quantity from a
        # sequential one and a leaderboard is handed rows and no header to ask.
        "concurrent": bool(result.batch_spans),
        "content_deltas": sum(deltas),
        "token_source": _token_source(samples),
        "ttft_p50_s": percentile(ttft, 50),
        "ttft_p90_s": percentile(ttft, 90) if n >= MIN_PERCENTILE_N else None,
        "ttft_p99_s": percentile(ttft, 99) if n >= MIN_PERCENTILE_N else None,
        "e2e_p50_s": percentile(e2e, 50),
        "e2e_p90_s": percentile(e2e, 90) if len(e2e) >= MIN_PERCENTILE_N else None,
        "e2e_p99_s": percentile(e2e, 99) if len(e2e) >= MIN_PERCENTILE_N else None,
        "timing_channel": _timing_channel(samples),
        "reasoning_timed_note": _reasoning_timed_note(samples),
        "itl_s": median(itl),
        "decode_tps": median(decode),
        "drift": drift,
        "aggregate_tps": _aggregate_tps(samples, result.batch_spans),
        "prefill_tps": median(prefill),
        "cold_load_s": result.cold_load_s,
        "first_request_s": result.first_request_s,
        "peak_mb": (result.memory or {}).get("peak_mb"),
        "disk_bytes": result.disk_bytes,
        "runtime_version": result.runtime_version,
        "percentile_note": None
        if n >= MIN_PERCENTILE_N
        else f"n={n}: p90/p99 omitted (fewer than {MIN_PERCENTILE_N} samples)",
        "delta_note": None
        if not too_few
        else f"n={len(decode)}: decode tok/s, ITL and prefill tok/s omitted (fewer than "
        f"{measure.MIN_CONTENT_DELTAS} content deltas in {too_few} of {len(samples)} measured "
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


def _reasoning_timed_note(samples) -> str | None:
    reasoning = sum(transport.timing_channel(observation) == "reasoning" for observation in samples)
    if not reasoning:
        return None
    return (
        f"timed on reasoning channel: {reasoning} of {len(samples)} measured requests "
        "(TTFT and decode are the reasoning stream's, not content's)"
    )


def _timing_channel(samples) -> str | None:
    """Which stream this row's measured requests were timed on, in ``transport``'s words.

    One observation's channel is ``transport.timing_channel``'s answer and a row's is the one
    answer its measured requests shared. A row whose own requests did not all answer in one
    channel is ``"mixed"`` — a channel of its own rather than either of the two it mixes,
    because it is not the measurement a wholly-content row is and not the measurement a
    wholly-reasoning one is. ``None`` when nothing was measured: a row with no request was timed
    on no channel, and it carries no latency for a channel to qualify.
    """
    channels = {transport.timing_channel(observation) for observation in samples}
    if not channels:
        return None
    return channels.pop() if len(channels) == 1 else "mixed"


def _mixes_channels(rows: list[dict]) -> bool:
    """Whether these rows were not all timed on one channel.

    Read off the rows' own ``timing_channel``, so a join decides it from what each run recorded
    rather than from observations it does not hold. A row that measured nothing contributes
    none: it carries no first-token latency, so it cannot put two definitions in one ordering.
    """
    channels = {row.get("timing_channel") for row in rows if row.get("timing_channel")}
    return len(channels) > 1


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
    unpublished = _not_published_note(row)
    return _card_row(
        "drift_pct",
        "—" if unpublished else _drift_cell(row),
        unpublished or row.get("drift_note"),
    )


def _floor_verdicts(status, reason) -> dict:
    """The two gates, their verdicts, and what they leave this row.

    Both floors are measure's already: ``_set_status`` decides PASS only when every
    measured request came back carrying what the published metrics need and the responses are
    language. This re-runs neither check — it reads the verdict measure recorded and names the
    gate that wrote it, which is what the table and the card print and what a status string
    alone does not say. A row that fails a floor is kept out of the ordering and still shown.
    """
    if status == "N/A":
        # The cell never ran here, so no gate was faced. It cannot rank, and the row says the
        # cell was not measured rather than blaming a gate it never reached. The reason is on
        # the row itself; repeating it under both floors would bury it.
        floors = [_verdict(floor, "not measured", "not measured") for floor in FLOORS]
    elif _coherence_failed(status, reason):
        floors = [
            _verdict("coherence", "fail", reason),
            _verdict("metrics", "not reached"),
        ]
    elif status != "PASS":
        floors = [
            _verdict("coherence", "pass"),
            _verdict("metrics", "fail", reason),
        ]
    else:
        floors = [
            _verdict("coherence", "pass"),
            _verdict("metrics", "pass"),
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

    The three formulas are measure's, asked for rather than respelled: one definition each,
    in the module that owns the raw fields. A metric whose inputs are missing — no token
    count, a decode window of zero length, a stream with no inter-token interval — is
    ``None``. It is never faked from a leftover number.
    """
    return {
        "decode_tps": measure.decode_tps(observation),
        "prefill_tps": measure.prefill_tps(observation),
        "itl_s": measure.itl_s(observation),
    }


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
        "| E2E p50 s | E2E p90 s | E2E p99 s "
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
    unpublished = _not_published_note(row)
    notes = _unrepeated(
        [
            part
            for part in (
                row.get("rank_note"),
                row.get("exclusion"),
                unpublished,
                row.get("reason"),
                row.get("lost_visit_note"),
                row.get("short_note"),
                row.get("percentile_note"),
                row.get("ttft_note"),
                row.get("reasoning_timed_note"),
                row.get("delta_note"),
                row.get("drift_note"),
                row.get("cold_load_note"),
                row.get("first_request_note"),
            )
            if part
        ]
    )
    unpublished = _not_published_note(row)
    figures = {
        field: "—" if unpublished else _number(row.get(field), places)
        for field, places in (
            ("ttft_p50_s", 3), ("ttft_p90_s", 3), ("ttft_p99_s", 3),
            ("e2e_p50_s", 3), ("e2e_p90_s", 3), ("e2e_p99_s", 3),
            ("itl_s", 4), ("decode_tps", 1), ("aggregate_tps", 1),
            ("prefill_tps", 1),
        )
    }
    return [
        _text(row.get("cell_id")),
        _text(row.get("runtime")),
        _text(row.get("label")),
        _text(row.get("workload_id")),
        _text(row.get("rank")),
        _text(row.get("status")),
        _text(n) if total in (None, n) else f"{n}/{total}",
        figures["ttft_p50_s"],
        figures["ttft_p90_s"],
        figures["ttft_p99_s"],
        figures["e2e_p50_s"],
        figures["e2e_p90_s"],
        figures["e2e_p99_s"],
        figures["itl_s"],
        figures["decode_tps"],
        "—" if unpublished else _drift_cell(row),
        figures["aggregate_tps"],
        figures["prefill_tps"],
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
        "never weighted: coherence (the gate in `coherence.py`) and every published metric "
        "present, both of them measure's and both recorded as the row's status. A row that "
        "fails a floor is excluded from the ordering, still printed, and names the floor in "
        "its notes.",
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
        f"decode tok/s, ITL and prefill tok/s need at least {measure.MIN_CONTENT_DELTAS} content deltas in the "
        "stream: a runtime that returns the whole completion in one delta has no inter-token "
        "interval, so the cell shows `—` and the row says why. A response that arrived whole "
        "in one delta also makes that cell's TTFT a time-to-completion rather than a "
        "time-to-first-token; the value is kept, and the row's notes label it.",
    ]


# --- the joined grid ------------------------------------------------------------------------


# What a pin is worth on a header that predates it. `concurrency`, `prompt_tokens`,
# `cache_state`, `kv_quant`, `mtp_depth` and `stream_experts` are the six that arrived after runs
# existed: every header written before them drove its requests one at a time and sized no prompt
# at all and ran each runtime's own cache default and its own KV codec and its own MTP default
# and its own expert default, so `1` and five `None`s are what those runs did rather than
# defaults standing in for something unknown -- which is what separates them from an absent
# `temperature`, whose absence is a header this guard cannot compare. The `None`s are the ones
# that matter most here: an absent pin is not `"off"`, because the runs it stands for were not
# uniform -- the Osaurus grid columns ran with its prefix cache ON, OptiQ's default expert mode
# is `auto`, and vMLX runs MTP on any bundle that carries the heads -- so reading an absence as
# a state would fold two different states into one column and call them a sweep. Every one of
# the six is the absence being the fact: `ABSENT_PINS` is where that is written once.
ABSENT_PINS = {
    "concurrency": 1,
    "prompt_tokens": None,
    "cache_state": None,
    "kv_quant": None,
    "mtp_depth": None,
    "stream_experts": None,
}

# The five entry states as the two joined tables spell them out: the grid and the sweep print
# the same legend, and two copies of it are two places for one reading to drift.
ENTRY_LEGEND = (
    "| entry | means |",
    "|---|---|",
    "| a number | a measured cell that cleared every floor |",
    "| `no value` | a cell that cleared every floor and has no value for this metric; "
    "its run's leaderboard carries the note saying why |",
    "| `FAIL` | a measured cell that did not clear one |",
    "| `N/A` | a cell that could not be run here; its own run's row carries the reason |",
    "| `—` | a combination no run measured |",
    "",
)


def _check_known_runtime_versions(runs: list[tuple]) -> None:
    """Refuse a joined row whose runtime would not state its version (review D3).

    ``runtimes`` records ``unknown: <why>`` when a version command fails. Guard 4 holds each
    runtime's version constant across a join, and a version nobody stated cannot be held.
    """
    for label, _header, rows in runs:
        for row in rows:
            version = row.get("runtime_version")
            if isinstance(version, str) and version.startswith("unknown"):
                raise ValueError(
                    f"{label} cell {row.get('cell_id')!r} has runtime_version {version!r}; "
                    "joined runs require a stated runtime version"
                )


def _check_harness(runs: list[tuple]) -> None:
    seen = None
    for label, header, _rows in runs:
        harness = header.get("harness")
        if harness is None:
            continue
        source_sha256 = harness.get("source_sha256")
        if seen is not None and seen[1] != source_sha256:
            raise ValueError(
                f"harness source_sha256 disagrees: {seen[0]} used {seen[1]!r} and {label} "
                f"used {source_sha256!r}; runs with different harness source are not one join"
            )
        if seen is None:
            seen = (label, source_sha256)


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


def _check_cells_appear_once(
    runs: list[tuple], key_of, *, key_fields: str, twice: str
) -> None:
    """Guard 2: no cell measured by two run directories, in either join.

    There is no "latest wins" rule: which run is newer is not which run is right, so a cell
    measured twice is ambiguous rather than superseded and the join refuses instead of
    choosing one of the two.

    *key_of* is what a cell is keyed on, and the two joins key it differently: the grid on the
    cell's own three fields, the sweep on those three plus the value of its swept pin, because
    one cell at two values is a sweep's table working as intended while one cell at one value
    twice is the same ambiguity the grid refuses. *key_fields* names that key as the refusal
    prints it and *twice* says what the two directories did to it.
    """
    seen: dict[tuple, str] = {}
    for label, header, rows in runs:
        for row in rows:
            key = key_of(header, row)
            if key in seen:
                raise ValueError(
                    f"duplicate cell: ({key_fields}) = {key!r} appears in both "
                    f"{seen[key]} and {label}; two run directories {twice}, and there is no "
                    "latest-wins rule because which run is newer is not which run is right"
                )
            seen[key] = label


def _check_one_value_per_key(
    runs: list[tuple], *, field: str, kind: str, key_of, verb: str, clause: str
) -> None:
    """Guards 3 and 4: one value per key, across columns as well as inside a table.

    Guard 3: one format label, one artifact. Two rows agreeing on the format's name and
    pointing at different bytes are two formats. ``_held_constant`` makes that check within one
    table; this makes it across the grid.

    Guard 4: one runtime, one version. Two *different* runtimes at different versions is the
    grid working as intended. The same runtime at 0.25.3 in one directory and 0.25.4 in another
    is the grid's held-constant variable moving — Osaurus measured 1.15x across exactly that
    step — so it is refused rather than joined. Guard 4 compares ``runtime_version`` as an exact
    string: mlx-optiq reports ``"mlx-optiq, version 0.5.6"`` rather than a bare ``0.5.6``, and a
    runtime that rephrases its ``--version`` output would read as a version change here.

    *key_of* returns the row's ``(key, value)``, *field* is the value's name in the refusal,
    *kind* names the key, and *verb* and *clause* say what the two directories did with it and
    what the disagreement means. A row missing either half is skipped: a cell that never ran
    cannot disagree about which build the others ran on.
    """
    seen: dict[str, tuple] = {}
    for label, _header, rows in runs:
        for row in rows:
            key, value = key_of(row)
            if not key or not value:
                continue
            if key in seen and seen[key][0] != value:
                previous, previous_run = seen[key]
                raise ValueError(
                    f"{field} disagrees for {kind} `{key}`: {previous_run} {verb} "
                    f"{previous} and {label} {verb} {value}; {clause}"
                )
            seen.setdefault(key, (value, label))


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
            column["runs"] = list(dict.fromkeys([*column["runs"], run_label]))
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
    return list(dict.fromkeys(
        row.get("label")
        for _run_label, _header, rows in runs
        for row in rows
        if row.get("label")
    ))


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
    lines += _harness_provenance(runs)
    lines += _shared_pins(runs, varying=None)
    return lines


def _harness_provenance(runs: list[tuple]) -> list[str]:
    provenance = [
        f"Harness `{_text(header['harness'].get('version'))}` source_sha256 "
        f"`{_text(header['harness'].get('source_sha256'))}` for `{label}`."
        for label, header, _rows in runs
        if header.get("harness") is not None
    ]
    return provenance + [""] if provenance else []


def _shared_pins(runs: list[tuple], *, varying: str | None) -> list[str]:
    """The two lines every provenance block ends with: the pins the runs shared, and the shapes.

    Each block's prose above them is the join's own — the grid names what every column shares,
    a sweep names the one pin its columns differ on — but these two lines are the same reading
    in both, because they are what guard 1 actually compared. *varying* is the pin the runs were
    allowed to differ on, named as the exception rather than listed among the shared ones;
    ``None`` is the grid, which permits none.
    """
    if not runs:
        return []
    header = runs[0][1]
    pins = ", ".join(
        f"{field} `{_text(header.get(field, ABSENT_PINS.get(field)))}`"
        for field in PIN_FIELDS
        if field != varying
    )
    shapes = ", ".join(
        f"`{_text(shape.get('id'))}` (max_tokens {_text(shape.get('max_tokens'))})"
        for shape in header.get("workloads") or ()
    )
    if varying is None:
        return [
            f"Pins all columns share: {pins}.",
            "",
            f"Workloads all columns ran, with identical messages: {shapes}.",
            "",
        ]
    shapes_line = (
        f"Workloads all runs ran: {shapes}."
        if varying == "prompt_tokens"
        else f"Workloads all runs ran, with identical messages: {shapes}."
    )
    return [
        f"Pins all runs shared, with `{varying}` the one pin they differ on: {pins}.",
        "",
        shapes_line,
        "",
    ]


def _entry_table(head: str, columns: list[tuple], rows: list[tuple], entry_for) -> str:
    """One joined table: a head column, one column per key and one row per key.

    The two joins key their cells differently — the grid on ``(label, runtime)``, the sweep on
    ``(cell, workload, pin value)`` — so *columns* and *rows* arrive as ``(text, key)`` pairs and
    *entry_for* is handed the row's key and the column's. Everything between the keys is one
    rendering: the heads, the divider and the cells, so an entry is the same string in either
    table.
    """
    header = "| " + " | ".join([head, *(text for text, _key in columns)]) + " |"
    divider = "|" + "---|" * (header.count("|") - 1)
    lines = [header, divider]
    for text, row_key in rows:
        cells = [text, *(entry_for(row_key, key) for _head, key in columns)]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _grid_table(rows: list[dict], labels: list[str], columns: list[dict], rank: str) -> str:
    """One workload's grid: format labels down, runtime names across, one entry per cell.

    The drift marker rides only a rank in ``DECODE_DERIVED_RANKS``, by ``_sweep_table``'s rule
    and for its reason: the figure is the cell's decode rate moving, so it qualifies an entry
    carrying a decode rate and misstates one carrying anything else. Every published grid was
    rendered on the default ``decode_tps``, where the marker is unchanged.
    """
    index = {}
    for row in rows:
        index.setdefault((row.get("label"), row.get("runtime")), row)

    marker = rank in DECODE_DERIVED_RANKS
    return _entry_table(
        "format",
        [(_text(column["runtime"]), column["runtime"]) for column in columns],
        [(_text(label), label) for label in labels],
        lambda label, runtime: _entry(
            index.get((label, runtime)), rank, drift_marker=marker
        ),
    )


def _reasoning_timed_marker(row: dict) -> str | None:
    note = row.get("reasoning_timed_note")
    return "reasoning timed" if note else None


def _entry(row: dict | None, rank: str, *, drift_marker: bool = True) -> str:
    """One grid entry, in one of the five states a cell can be in.

    A combination no run measured is ``—``, a cell the runtime could not be driven into is
    ``N/A``, and a cell that ran without clearing a floor is ``FAIL``: they are different facts
    about a cell, and rendering them alike is how a rag comes to read as a failure and how a
    refused cell comes to read as one nobody planned. ``N/A`` is measure's word for a cell that
    never ran here, the same state the floors print as "not measured"; anything else that is not
    PASS ran and did not clear one. A PASS entry carries its number, and a drifting one carries
    its marker beside it. The reason a cell is ``N/A`` is on its row in its own run's
    leaderboard, which has the notes column the two joined tables do not.

    *drift_marker* is the caller's to set, because whether the marker belongs beside this entry
    depends on what the entry's number is. The figure is a decode rate's movement, so it
    qualifies an entry carrying a decode rate and misstates any other one (see
    ``DECODE_DERIVED_RANKS``). ``_grid_table`` and ``_sweep_table`` both turn it off for a rank
    the figure does not qualify, so an entry ordered on a non-decode metric prints its number
    alone; the default rank is a decode rate's, where the marker rides the entry exactly as
    every published grid has printed it.

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
    if row is None:
        return "—"
    if row.get("status") == "N/A":
        return "N/A"
    if row.get("status") != "PASS":
        return "FAIL"
    if row.get(rank) is None:
        return "no value"
    number = _rank_number(row, rank)
    markers = []
    drift = _drift_marker(row) if drift_marker else None
    if drift is not None:
        markers.append(f"drift {drift}%")
    short = _short_marker(row)
    if short is not None:
        markers.append(short)
    reasoning_timed = _reasoning_timed_marker(row)
    if reasoning_timed is not None:
        markers.append(reasoning_timed)
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

    What it returns is the decode rate's movement, so it says nothing about a cell's other
    metrics. Whether that belongs beside the number the caller is printing is the caller's to
    decide -- see ``_entry``'s *drift_marker* -- because it is a property of the metric the
    entry carries and not of the cell.
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
            lines += [_cross_runtime_note(rank), ""]
        # One group per format, built once and read by both the note and the lines below it, so
        # the note cannot name a format the readings were not grouped by.
        by_label = [
            (label, [row for row in rows if row.get("label") == label]) for label in labels
        ]
        if rank in CHANNEL_DEPENDENT_RANKS:
            mixed = [label for label, group in by_label if _mixes_channels(group)]
            if mixed:
                lines += [_channel_note(rank, mixed), ""]
        for label, group in by_label:
            lines.append(f"- `{_text(label)}`: {_ordering(group, rank, 'runtime')}")
        recommendation = _recommendation(rows, rank)
        if recommendation is not None:
            lines += ["", recommendation, ""]
    return lines


def _uncomparable_across_runtimes(rows: list[dict], rank: str) -> bool:
    """Whether a runtime-axis ordering of *rank* over these rows would compare two quantities.

    Two ways it can, and both are read off the metric against the rows rather than assumed of
    the rendering. ``CROSS_RUNTIME_UNCOMPARABLE``'s metrics are not one quantity across runtimes
    whatever the rows are; ``CHANNEL_DEPENDENT_RANKS``' are one quantity within a group timed on
    one channel and two definitions across a group that does not share one. Each refusal's
    rationale is written once, at its own constant. Either way the ordering keeps the values and
    withholds the positions, and the reading says which of the two it was.
    """
    if rank in CROSS_RUNTIME_UNCOMPARABLE:
        return True
    return rank in CHANNEL_DEPENDENT_RANKS and _mixes_channels(rows)


def _channel_note(rank: str, mixed: list[str]) -> str:
    """The one note a runtime-axis section whose rows mix channels prints.

    One note for the section rather than one above each line: the refusal is one fact about the
    section, and the labels it applies to are named inside it. The values stay printed —
    alphabetically, with no position — because they are still measurements a reader is owed;
    what is withheld is the ordering, which would read two definitions as one number.
    """
    named = ", ".join(f"`{_text(label)}`" for label in mixed)
    return (
        f"> **`{rank}` is not one quantity across rows timed on different channels.** In "
        f"{named} the rows are not all timed on one channel (`transport.timing_channel`): a "
        "first-token latency timed on the content channel is the time to the first *content* "
        "token, which on a thinking model lands after its whole reasoning run, and one timed "
        "on the reasoning channel is the model's first token out of it. Two definitions are "
        "two quantities, so the values are listed with no positions."
    )


def _cross_runtime_note(rank: str) -> str:
    """The one note a runtime-axis ordering of *rank* prints where the metric is not one
    quantity across runtimes at all: the refusal, then the reason written at its constant.

    Read by the grid's runtime-axis section and by the single-run leaderboard's
    `axis="runtime"` table, because they are the same reading of the same rows -- one format,
    its runtimes the variable -- and two renderings of one refusal that disagreed would be two
    refusals. The channel refusal's sibling is ``_channel_note``.
    """
    return (
        f"> **`{rank}` is not one quantity across runtimes.** {CROSS_RUNTIME_UNCOMPARABLE[rank]}"
    )


def _runtime_axis_note(rows: list[dict], rank: str) -> str:
    """The note a refused runtime-axis ordering prints, and which of the two refusals it was.

    ``_uncomparable_across_runtimes`` decides *whether* a group's ordering is refused; this
    decides *which* refusal it was and returns that refusal's own note -- ``_cross_runtime_note``
    where the metric is not one quantity across runtimes at all, ``_channel_note`` where it is
    one per channel and the group does not share one -- so the text a reader gets is the text
    the grid's runtime-axis section carries, not a second wording of it. A channel note names
    the formats whose rows mix them; here that is the group's own labels, because a
    leaderboard's table is one workload's rows and the group is the whole of what it orders.
    """
    if rank in CROSS_RUNTIME_UNCOMPARABLE:
        return _cross_runtime_note(rank)
    mixed = sorted({str(row.get("label")) for row in rows if row.get("label") is not None})
    return _channel_note(rank, mixed)


def _unpositioned(rows: list[dict], key: str) -> list[dict]:
    """The rows of a listing that makes no ordering claim: alphabetically by the axis key.

    A refused ordering keeps every value and gives up the positions, and what it must not do is
    hand back a ranking under another name — the metric order *is* the claim, so listing in it
    and dropping the numbers would leave the reading saying what it refuses to say. Alphabetical
    by the variable is an order no reader mistakes for a result, and it is the one both the
    grid's runtime-axis reading and the single-run leaderboard's refused table list in.
    """
    return sorted(rows, key=lambda row: str(row.get(key) or ""))


def _ordering(rows: list[dict], rank: str, key: str) -> str:
    """One axis reading's ordering, with what kept each unranked cell out of it.

    The position is the row's own ``rank``, so the reading is checkable against the table.
    A cell that failed a floor or carries no value for the metric is named rather than
    dropped: it is a result, and it is the one the ordering could not include.
    """
    if not rows:
        return "—"
    # Decision 120 and the 2026-09-24 channel decision: across runtimes these metrics are not one
    # quantity, so the values are listed alphabetically by runtime with no position. Within one
    # runtime — the format axis — they still order.
    if key == "runtime" and _uncomparable_across_runtimes(rows, rank):
        return "; ".join(
            f"`{_text(row.get(key))}` = {_rank_number(row, rank)}"
            for row in _unpositioned(rows, key)
        )
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


def _recommendation(rows: list[dict], rank: str) -> str | None:
    """The best cell in one workload's grid, labelled as a recommendation.

    It is the one line in the document that spans both axes, and that is exactly why it cannot
    be read as an attribution: the cell that won won under one format and one runtime at once,
    and the number carries no way to split the win between them. Which of the two earned it is
    what the column and the row above this line are for.

    Two ranks name no best cell rather than a wrong one, and they refuse differently because the
    facts differ. A metric that is not one quantity across runtimes at all
    (``CROSS_RUNTIME_UNCOMPARABLE``) gets no line: the runtime-axis note above it already says
    why, and every reading in the section is values-without-positions. A channel-dependent rank
    (``CHANNEL_DEPENDENT_RANKS``) over a workload whose rows mix channels gets the "none"
    sentence, because the rest of the section still orders and only this line spans the two
    definitions.
    """
    if rank in CROSS_RUNTIME_UNCOMPARABLE:
        return None
    if rank in CHANNEL_DEPENDENT_RANKS and _mixes_channels(rows):
        return (
            "**Recommendation — none.** The rows of this workload were not all timed on one "
            f"channel, so no cell can lead an ordering at `{rank}`: this figure is read off the "
            "request's first-token latency, and a latency timed on the content channel is a "
            "different measurement from one timed on the reasoning channel. Which cells "
            "answered in which channel is each row's `reasoning timed` note in its own run's "
            "leaderboard, and the marker the grid prints beside the entries that carry one."
        )
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
# and all six of these are properties of how a run *drove* its cells rather than of a cell:
# that is why they are header pins, why `--study` can name none of them, and why a sweep is N
# runs differing in exactly one of them. Anything else a header carries is held by guard 1 like
# any other pin, so a "sweep" of `temperature` would be a grid with a pin quietly uncompared.
SWEEP_PINS = (
    "concurrency",
    "prompt_tokens",
    "cache_state",
    "kv_quant",
    "mtp_depth",
    "stream_experts",
)

# What each swept pin holds, in words a reader of the rendered sweep can act on.
SWEPT_PIN = {
    "concurrency": "requests issued together in one batch",
    "prompt_tokens": "the length the prompt was sized to, as a target and the count the "
    "serving tokenizer achieved",
    "cache_state": "whether the runtime's prefix/KV reuse was off or on, as the start command "
    "pinned it",
    "kv_quant": "which codec the runtime's KV cache was held in, as the start command pinned "
    "it -- `off` for the runtime's own full-precision cache, `affine8`/`affine4` for MLX's "
    "affine codec at that width",
    "mtp_depth": "the native-MTP draft depth the runtime's heads were pinned at, as the start "
    "command pinned it -- `off` for MTP not running, `1`/`2`/`3` for that many draft tokens per "
    "verify cycle under the fixed policy",
    "stream_experts": "whether MoE expert weights were streamed from SSD on demand or held "
    "resident, as the start command pinned it and the runtime's own log confirmed it",
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
    "kv_quant": (
        "Every other pin is identical across these runs, and so is every workload down to its "
        "prompt and its cap -- the runs sent byte-identical prompts and differ only in the "
        "codec their KV caches were held in, which is the single field the guard skips. No "
        "prompt is relaxed for this pin, for the reason the cache-state sweep relaxes none: "
        "the subject is the same prompt answered under one codec and then another. What these "
        "columns cannot carry is each runtime's own side effects of reaching the codec it was "
        "pinned to -- OptiQ's fused streaming-KV path, vMLX's storage-only codec, Osaurus "
        "verifying a host setting -- which are named beside the values, in "
        "`runtimes.KV_QUANTS` and each runtime's refusal."
    ),
    "mtp_depth": (
        "Every other pin is identical across these runs, and so is every workload down to its "
        "prompt and its cap, so the columns differ only in the draft depth the runtime's MTP "
        "heads were pinned at. No prompt is relaxed, and every depth column is only rendered on "
        "an artifact whose MTP heads the runtime will wire -- a bundle without them is `N/A` "
        "with the reason, never a depth measured as plain autoregressive "
        "(`runtimes.vmlx_mtp_refusal`)."
    ),
    "stream_experts": (
        "Every other pin is identical across these runs, and so is every workload down to its "
        "prompt and its cap, so the columns differ only in whether expert weights were streamed "
        "from SSD or held resident. No prompt is relaxed. The `on` column is the one place a "
        "header pin is confirmed by the server rather than by its own command line, so an `on` "
        "cell whose log does not show streaming is `FAIL` with that log quoted "
        "(`runtimes.STREAM_EXPERTS`)."
    ),
}

# A swept pin's values in the order they are read, for the pins whose order is not their
# numeric one. A cache sweep's reading is the difference between the same prompt answered cold
# and answered warm, so `off` is the baseline column and `on` is the reading against it; the
# order is pinned here rather than left to the words' spelling, which happens to sort the same
# way today and would stop the moment a third value arrived. A codec sweep reads the same way
# one cache down: `off` is the baseline -- the runtime's own full-precision cache -- and the
# codec columns follow in `runtimes.KV_QUANTS`' order, which a test holds this tuple to. The
# two after it are the same reading again: `off` first, then the depths in `runtimes.MTP_DEPTHS`
# order and `on` after `off` in `runtimes.STREAM_EXPERTS`'.
SWEEP_VALUES = {
    "cache_state": ("off", "on"),
    "kv_quant": ("off", "affine8", "affine4"),
    "mtp_depth": ("off", "1", "2", "3"),
    "stream_experts": ("off", "on"),
}


# The sentence a sweep of concurrency carries, verbatim. Measured, plan 06-01a: oMLX at N=8
# swung 65.3-81.0 tok/s of per-request decode rate across 16 batches with no trend and never
# settled, while its per-batch aggregate settled at batch 12. So the drift a concurrent cell
# prints is queueing variance in a per-request rate, and the annotation's own reading of a
# positive change -- insufficient warmup -- is not the reading there.
CONCURRENCY_DRIFT_SENTENCE = (
    "At concurrency > 1, measured drift reads per-request rates: positive drift means the "
    "per-request rate was still moving, not that the cell was under-warmed."
)


# The sentence a table ordered on a first-token latency carries when its runs drove more than
# one request at a time, verbatim. The phase-6 design says it plainly
# (`docs/research/2026-09-16-phase6-design.md`): at N=1 TTFT is time-to-first-token, and at N it
# includes however long the request waited for a slot, which is a real user-facing cost and a
# different quantity. The ranks it rides are the first-token-latency family,
# `CHANNEL_DEPENDENT_RANKS` -- the same set Decision 122 refuses a mixed-channel runtime-axis
# ordering on, because the value is that latency or is computed from it, so the wait is in the
# number either way. A rank outside the family reads a figure no queue can move and gets no
# sentence. Printed by `render_sweep` for a concurrent sweeping run and by `render_markdown` for
# a concurrent run's rows.
CONCURRENCY_TTFT_SENTENCE = (
    "At concurrency > 1, TTFT includes a request's wait for its batch slot: it is a queueing "
    "measurement, not the time-to-first-token a sequential run measures, and a prefill rate "
    "computed from it carries that wait."
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
    `prompt_tokens`, `cache_state`, `kv_quant`, `mtp_depth` and `stream_experts` are properties
    of how a run drove its cells, so
    they live in the header. A sweep is N run directories differing in exactly that pin, joined
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
    like any other grid. `kv_quant` relaxes nothing either, and for the same reason one cache
    down: its columns are meant to answer the same prompt under one codec and then another, so
    what they cannot carry is each runtime's own side effects of reaching the codec it was
    pinned to, which are named beside the values in `runtimes.KV_QUANTS` and each runtime's
    refusal. `mtp_depth` and `stream_experts` relax nothing and add nothing beside the values:
    the `on` column's evidence is a floor on the cell, not a caveat on the table
    (`runtimes.STREAM_EXPERTS`).

    The columns ascend, because that is the reading: a prompt that got longer or batches that
    got wider says nothing while the table is in command-line order. A pin with an order of its
    own reads in that order — `cache_state`'s `off` before its `on`, and `kv_quant`'s `off`
    before its codecs, `mtp_depth`'s `off` before its depths and `stream_experts`' `off` before
    its `on`, the baseline column first because it is what the others are read against.
    Entries are the ``rank`` metric,
    formatted by the same functions the grid formats its own with, so `—`, `FAIL` and
    `no value` mean here exactly what they mean there.

    A run that issued more than one request at a time, or a sweep of concurrency, carries
    ``CONCURRENCY_DRIFT_SENTENCE``: the drift beside a concurrent cell's per-request rate is not
    the unfinished warm-up that annotation was written for. The sentence explains markers, and
    a non-decode rank prints none, so it rides only a rank in ``DECODE_DERIVED_RANKS`` too — a
    sweep ordered on `ttft_p50_s` would otherwise explain a figure none of its entries carries.

    The same runs carry ``CONCURRENCY_TTFT_SENTENCE`` when the rank is a first-token latency:
    the table is then ordered on a figure the queue is inside, which is the design's "TTFT
    becomes a queueing measurement" read as a caveat on the table that publishes it. Its rank
    test is ``CHANNEL_DEPENDENT_RANKS`` — the ranks read off that latency or computed from it —
    for the reverse reason: a sweep ordered on `decode_tps` would attach a queueing caveat to a
    figure the queue does not move.

    An entry carries the drift marker only where the drift figure qualifies the number it sits
    beside. ``measure.measured_drift`` compares per-request decode rates, so the percentage is one
    metric's movement: beside a decode rate it is that cell's own, and beside any other metric it
    states a different one's. A sweep read on `ttft_p50_s` — the prompt-length sweep and the
    cache-state sweep are both ordered on it — printed `drift +11.5%` beside a first-token latency
    whose cell's TTFT had not moved, and nothing in the marker's words said which metric had. So
    the marker rides only a rank in ``DECODE_DERIVED_RANKS``, and every entry ordered on anything
    else carries its number alone: one rule for every non-decode rank, enforced for all of them by
    ``_sweep_table``. Nothing is dropped from the record — the drift stays on the row, and each
    run's own leaderboard prints it beside the decode rate it qualifies.
    """
    if varying not in SWEEP_PINS:
        raise ValueError(
            f"varying must be one of {SWEEP_PINS}, not {varying!r}: a sweep varies one run "
            "header pin, and a cell's two variables are what `--study` names"
        )
    if rank not in RANK_METRICS:
        raise ValueError(_rank_error(rank))

    runs = [(label, dict(header or {}), list(rows)) for label, header, rows in runs]
    _check_harness(runs)
    _check_known_runtime_versions(runs)
    _check_pins(runs, varying=varying)
    _check_sweep_varies(runs, varying)
    _check_cells_appear_once(
        runs,
        lambda header, row: (
            row.get("label"),
            row.get("runtime"),
            row.get("workload_id"),
            _pin_key(header, varying),
        ),
        key_fields=f"label, runtime, workload_id, {varying}",
        twice="measured one cell at one value of the swept pin",
    )

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
        *ENTRY_LEGEND,
    ]
    lines += [
        "A `reasoning timed` marker means TTFT and decode use the reasoning stream, not content.",
        "",
    ]
    concurrent = varying == "concurrency" or any(
        _drove_more_than_one_request(header) for _label, header, _rows in runs
    )
    if rank in DECODE_DERIVED_RANKS and concurrent:
        lines += [f"> {CONCURRENCY_DRIFT_SENTENCE}", ""]
    if rank in CHANNEL_DEPENDENT_RANKS and concurrent:
        lines += [f"> {CONCURRENCY_TTFT_SENTENCE}", ""]
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
    return list(dict.fromkeys(
        row.get("cell_id")
        for _label, _header, rows in runs
        for row in rows
        if row.get("cell_id")
    ))


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
    lines += _harness_provenance(runs)
    lines += _shared_pins(runs, varying=varying)
    return lines


def _sweep_table(
    workload: str, cells: list[str], columns: list[dict], index: dict, rank: str, varying: str
) -> str:
    """One workload's sweep: cells down, the swept pin's values across, one entry per cell.

    An entry is the row's ``rank`` metric in the same four states the grid renders it in, by the
    same function, so a combination no run measured (`—`), a cell that ran and did not clear a
    floor (`FAIL`) and one that cleared every floor without a value for this metric (`no value`)
    stay three facts here as they are there.

    One thing is decided here and not by ``_entry``: whether a drifting cell's marker belongs
    beside the number. The drift figure is the cell's decode rate moving, so it qualifies an
    entry that carries a decode rate and misstates an entry carrying anything else — a table
    ordered on `ttft_p50_s` would print a decode rate's movement as an apparent TTFT movement.
    The marker therefore rides only a rank in ``DECODE_DERIVED_RANKS``, and every other rank's
    entries print their numbers alone.
    """
    marker = rank in DECODE_DERIVED_RANKS
    return _entry_table(
        "cell",
        [(_sweep_head(column, varying), column["key"]) for column in columns],
        [(_text(cell), cell) for cell in cells],
        lambda cell, key: _entry(
            index.get((cell, workload, key)), rank, drift_marker=marker
        ),
    )


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
