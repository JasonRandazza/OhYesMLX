"""Join measure's raw numbers into one row per cell and one leaderboard.

The metric formulas are the ones pinned in ``docs/interfaces.md``, not re-derived here::

    decode_tps  = completion_tokens / (last_content_s - ttft_s)
    prefill_tps = prompt_tokens / ttft_s
    itl_s       = (last_content_s - ttft_s) / max(1, completion_tokens - 1)

``decode_tps`` is a per-request rate and ``aggregate_tps`` is a cell-wide one. They stay
separate fields because continuous batching wins one and loses the other, and one number
cannot say both.

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
    ("peak_mb", 1),
    ("disk_bytes", 0),
)

# The caveat a value carries once it exists: a rate's is the delta rule's, and TTFT's is the
# channel the stream delivered it in.
_METRIC_CAVEAT = {
    "decode_tps": "delta_note",
    "prefill_tps": "delta_note",
    "itl_s": "delta_note",
    "ttft_p50_s": "ttft_note",
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


def summarize(results: list[CellResult]) -> list[dict]:
    """One row per (cell, workload): the contract's fields, joined from measure, the sampler
    and disk.

    Rows keep the order the cells came in. Observations are used exactly as measure
    recorded them — this module has no warmup marker to filter on, so keeping warmups out
    of a cell's summary is measure's job. Percentiles below ``MIN_PERCENTILE_N`` samples
    are omitted rather than guessed, and ``percentile_note`` says so; a request that
    streamed fewer than ``MIN_CONTENT_DELTAS`` content deltas carries no rate to report, and
    ``delta_note`` and ``ttft_note`` say that instead.

    Each row also carries the floor verdicts and whether they leave it rankable. Figures
    are never averaged across workloads: a prefill-bound number blended with a decode-bound
    one describes no workload that was run.
    """
    return [_row(result) for result in results]


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
        _card_row("status", _text(row.get("status")), row.get("reason")),
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
        _card_row("n measured", _text(row.get("n_measured"))),
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


def _row(result: CellResult) -> dict:
    cell = result.cell
    observations = list(result.observations)
    # Who came back is measure's question, and its answer is asked for rather than respelled:
    # ``observation.ok`` is a second definition of it, and the two drifted apart — a cell whose
    # five requests all answered in the reasoning channel was published as ``n = 0/5``.
    measured = [o for o in observations if measure.came_back(o)]

    ttft = [o.ttft_s for o in measured if o.ttft_s is not None]
    decode, prefill, itl = [], [], []
    for observation in measured:
        per_request = _per_request(observation)
        if per_request["decode_tps"] is not None:
            decode.append(per_request["decode_tps"])
        if per_request["prefill_tps"] is not None:
            prefill.append(per_request["prefill_tps"])
        if per_request["itl_s"] is not None:
            itl.append(per_request["itl_s"])

    n = len(ttft)
    deltas = [_content_deltas(observation) for observation in measured]
    single_delta = deltas.count(1)
    too_few = sum(1 for count in deltas if count < MIN_CONTENT_DELTAS)
    row = {
        "cell_id": cell.id,
        "runtime": cell.runtime,
        "label": cell.label,
        "artifact_dir": cell.artifact_dir,
        "workload_id": result.workload_id,
        "status": result.status,
        "reason": result.reason,
        "n_measured": len(measured),
        "n_requests": len(observations),
        "content_deltas": sum(deltas),
        "token_source": _token_source(measured),
        "ttft_p50_s": percentile(ttft, 50),
        "ttft_p90_s": percentile(ttft, 90) if n >= MIN_PERCENTILE_N else None,
        "ttft_p99_s": percentile(ttft, 99) if n >= MIN_PERCENTILE_N else None,
        "itl_s": median(itl),
        "decode_tps": median(decode),
        "aggregate_tps": _aggregate_tps(measured),
        "prefill_tps": median(prefill),
        "cold_load_s": result.cold_load_s,
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
        f"{MIN_CONTENT_DELTAS} content deltas in {too_few} of {len(measured)} measured "
        "requests)",
        "ttft_note": None
        if not single_delta
        else f"TTFT is time-to-completion, not time-to-first-token: {single_delta} of "
        f"{len(measured)} measured requests arrived whole in one content delta",
    }
    row.update(_floor_verdicts(row["status"], row["reason"]))
    return row


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


def _aggregate_tps(observations: list) -> float | None:
    """Cell-wide output throughput: every completion token over the time they took.

    # ponytail: Observation carries durations, not timestamps, so this sums per-request
    # wall clocks and cannot see overlap. Ceiling: exact at concurrency 1, conservative
    # once requests run concurrently. Upgrade path: record send/close stamps on
    # Observation and use the span of the measured window instead.
    """
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
        runtimes = sorted({str(r.get("runtime")) for r in rows})
        held = f"runtime `{runtimes[0]}`"
        distinct = runtimes

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
        "| ITL s | decode tok/s | aggregate tok/s | prefill tok/s | cold load s | peak MB "
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
                row.get("percentile_note"),
                row.get("ttft_note"),
                row.get("delta_note"),
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
        _number(row.get("aggregate_tps"), 1),
        _number(row.get("prefill_tps"), 1),
        _number(row.get("cold_load_s"), 2),
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
        f"p90 and p99 need at least {MIN_PERCENTILE_N} samples; below that the cell shows "
        "`—` and the row says `n=<k>` rather than inventing a percentile.",
        "",
        f"decode tok/s, ITL and prefill tok/s need at least {MIN_CONTENT_DELTAS} content deltas in the "
        "stream: a runtime that returns the whole completion in one delta has no inter-token "
        "interval, so the cell shows `—` and the row says why. A response that arrived whole "
        "in one delta also makes that cell's TTFT a time-to-completion rather than a "
        "time-to-first-token; the value is kept, and the row's notes label it.",
    ]


def _number(value, places: int) -> str:
    return "—" if value is None else f"{value:.{places}f}"


def _bytes(value) -> str:
    return "—" if value is None else f"{value:,}"


def _text(value) -> str:
    return "—" if value is None or value == "" else str(value)
