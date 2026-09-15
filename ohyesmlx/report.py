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

Every raw observation goes into ``results.jsonl``, so every number here stays recomputable
from the file.
"""

from __future__ import annotations

import os
import statistics
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # measure.py is written against the same contract; report only reads it.
    from ohyesmlx.measure import CellResult

AXES = ("runtime", "format")

MIN_PERCENTILE_N = 5

# Each axis holds one variable and varies the other, which is the whole point of the split.
HELD_CONSTANT = {"runtime": "format", "format": "runtime"}

VARIED = {"runtime": "serving runtime", "format": "quantization format"}

# What a table on each axis therefore cannot claim.
CAVEAT = {
    "runtime": "format held constant; this compares serving, not quantization",
    "format": "runtime held constant; this compares quantization, not serving",
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
    """One row per cell: the contract's fields, joined from measure, the sampler and disk.

    Rows keep the order the cells came in. Observations are used exactly as measure
    recorded them — this module has no warmup marker to filter on, so keeping warmups out
    of a cell's summary is measure's job. Percentiles below ``MIN_PERCENTILE_N`` samples
    are omitted rather than guessed, and ``percentile_note`` says so.
    """
    return [_row(result) for result in results]


def render_markdown(rows: list[dict], *, axis: str) -> str:
    """The leaderboard, stating the variable it held constant and what that cannot claim.

    *axis* is required and is ``"runtime"`` or ``"format"``. A table that does not say
    which variable it held constant is not a result, and one whose rows do not actually
    hold it constant is refused rather than rendered.
    """
    if axis not in AXES:
        raise ValueError(f"axis must be one of {AXES!r}, not {axis!r}")

    held = _held_constant(rows, axis)
    lines = [f"# Leaderboard — {axis} axis", ""]
    if held is None:
        lines.append(f"One variable varied: the {VARIED[axis]}. No cells were measured.")
    else:
        lines.append(f"One variable varied: the {VARIED[axis]}. Held constant: {held}.")
    lines += ["", f"> **Caveat:** {CAVEAT[axis]}.", "", _table(rows), "", *_footnotes()]
    return "\n".join(lines) + "\n"


def _row(result: CellResult) -> dict:
    cell = result.cell
    observations = list(result.observations)
    measured = [o for o in observations if o.ok]

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
    return {
        "cell_id": cell.id,
        "runtime": cell.runtime,
        "label": cell.label,
        "artifact_dir": cell.artifact_dir,
        "status": result.status,
        "reason": result.reason,
        "n_measured": len(measured),
        "n_requests": len(observations),
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
    }


def _per_request(observation) -> dict:
    """One observation's three per-request metrics, exactly as the contract defines them.

    A metric whose inputs are missing — no token count, a decode window of zero length —
    is ``None``. It is never faked from a leftover number.
    """
    ttft = observation.ttft_s
    last = observation.last_content_s
    tokens = observation.completion_tokens
    prompt = observation.prompt_tokens
    span = last - ttft if last is not None and ttft is not None else None
    counted = tokens is not None

    decode_tps = tokens / span if counted and span is not None and span > 0 else None
    prefill_tps = (
        prompt / ttft if prompt is not None and ttft is not None and ttft > 0 else None
    )
    itl_s = span / max(1, tokens - 1) if counted and span is not None and span >= 0 else None
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


def _table(rows: list[dict]) -> str:
    header = (
        "| cell | runtime | format | status | n | TTFT p50 s | TTFT p90 s | TTFT p99 s "
        "| ITL s | decode tok/s | aggregate tok/s | prefill tok/s | cold load s | peak MB "
        "| disk bytes | runtime version | notes |"
    )
    divider = "|" + "---|" * (header.count("|") - 1)
    lines = [header, divider]
    lines += ["| " + " | ".join(_cells(row)) + " |" for row in rows]
    return "\n".join(lines)


def _cells(row: dict) -> list[str]:
    n, total = row.get("n_measured"), row.get("n_requests")
    notes = [part for part in (row.get("reason"), row.get("percentile_note")) if part]
    return [
        _text(row.get("cell_id")),
        _text(row.get("runtime")),
        _text(row.get("label")),
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


def _footnotes() -> list[str]:
    return [
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
    ]


def _number(value, places: int) -> str:
    return "—" if value is None else f"{value:.{places}f}"


def _bytes(value) -> str:
    return "—" if value is None else f"{value:,}"


def _text(value) -> str:
    return "—" if value is None or value == "" else str(value)
