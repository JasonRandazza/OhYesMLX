"""The measurement loop: cells in, raw observations out.

One cell is one (format, runtime) pair, and every cell is measured under every workload it is
given. A visit to a cell starts its runtime once, runs each workload's warmups, measured
requests and memory sampling under that single load, stops the runtime, and persists. This
module never speaks HTTP (``ohyesmlx/transport.py`` does) and never spawns a server
(``ohyesmlx/runtimes.py`` does).

What this module refuses to do:

* **Have two decode tok/s definitions.** There is exactly one, from ``docs/interfaces.md``::

      decode_tps  = completion_tokens / (last_content_s - ttft_s)
      prefill_tps = prompt_tokens / ttft_s
      itl_s       = (last_content_s - ttft_s) / max(1, completion_tokens - 1)

  The denominator is the content window, never ``total_s``. The predecessor's fallback
  divided by ``total_s`` — the final usage chunk, ``[DONE]`` and teardown included — while
  its numerator counted reasoning tokens that TTFT excluded, and the same cell reported
  243.5 tok/s one run and 57.2 the next. There is no second path here to re-enable later.

* **Fold model load into the first request.** ``Handle.cold_load_s`` is its own number on
  the ``CellResult`` and is never added to a request's timing. A warmup window opens with a
  floor of ``MIN_WARMUP`` so Metal shader compilation and lazy mmap land before the first
  measured request, and then runs until the cell's decode rate stops moving, because one
  budget applied to five runtimes ranks them by how fast they warm up and calls it how fast
  they serve.

* **Let a lazy loader's load hide in a warmup.** ``cold_load_s`` is spawn until readiness,
  which is a load time for a runtime that loads at startup and only a time-to-listening for
  one that loads on the first request. That runtime's load lands inside warmup #1, so the
  cold visit's first warmup latency is recorded too — as ``first_request_s``, its own
  number, never folded into ``cold_load_s`` — and with it the workload that made that
  request, because the latency is the visit's while the claim that reads it as a deferred
  load belongs to the one row whose own requests it was measured against. Ranking on
  ``cold_load_s`` alone named oMLX the fastest loader when it is the second slowest to a
  first useful token; a comparison across runtimes uses the sum.

* **Compare different generation lengths.** ``max_tokens`` belongs to the workload, and every
  request in a workload uses that workload's value, so decode tok/s is never a ratio between
  a model that stopped at 40 tokens and one that ran to the cap. Workloads are never averaged
  into each other either: prefill-heavy and decode-heavy work can have different winners, and
  one figure blended from both describes neither shape.

* **Walk cells in config order.** A run visits every cell twice, in opposite directions
  (see :func:`visit_plan`), with a cooldown between visits and the drift across the window
  recorded per cell. Walking the config order measures the first runtime cool and the last
  one throttled, which is a thermal curve wearing a runtime's name.

* **Lose a whole run to one bad cell.** Persistence happens after every visit, and a cell
  that cannot run is ``N/A`` with its reason, not an exception that ends the run.

* **Mix token sources inside a comparison.** The local tokenizer is built once per cell and
  passed to every request, so ``token_source`` is a property of the run rather than of
  whichever request happened to be answered. If the tokenizer cannot be built, the cell is
  ``N/A`` — visible — rather than quietly falling back to usage tokens.

* **Issue one request at a time.** A batch is ``concurrency`` requests issued together under
  one clock — ``concurrent.futures.ThreadPoolExecutor`` around the same :func:`_request` every
  sequential request goes through, because the transport is blocked on an SSE stream and a
  thread is enough to drive it. No second stream reader exists for it: one definition of TTFT,
  one decode window, one ``Observation``, at any concurrency. ``measured`` counts batches, so at
  ``concurrency=1`` a batch is one request and a sequential record is byte-identical to the one
  this module wrote before batches existed; the span is the batch's whole clock, because summing
  per-request spans would count the overlap N times and N requests share one GPU. The warmup
  window reads the batch's aggregate throughput there instead of per-request rates, which at N=8
  swing +/-11% with no trend and never satisfy a 3% trend test — see :func:`_warmup_rate`.

* **Publish a row that is not language.** Stock ``mlx_lm.server`` loaded a 256-expert oQ4
  MoE in 4 s, answered HTTP 200, decoded 64/64 tokens at full speed — and returned
  mixed-script token salad with replacement characters. Nothing raised. Before a cell's
  status is decided, the responses it already made are judged by ``ohyesmlx/coherence.py``:
  more than half of them incoherent and the cell is ``FAIL``, with the sample that failed
  still on the record. The measured responses *are* the sample, so asking costs no request.

  A response is judged on its content, or on its reasoning when it emitted no content at
  all: the same model spent one whole response in the reasoning channel and that channel
  was token salad too. ``STILL_THINKING`` is the honest verdict for a response that
  produced neither — no output is not bad output — but output in the other channel is.

A cell is ``PASS`` only when every measured request came back ok, carried what the published
metrics need (content-delta timing, content completion tokens, usage prompt tokens), and
produced language. Anything else is ``FAIL`` with the first reason — a failed cell is not a
result and no tok/s, TTFT, ITL or throughput figure is read from one — so a blank column is
never mistaken for a fast runtime. ``N/A`` means the cell could not be run at all here — an
unknown runtime, a runtime that will not load the artifact, no tokenizer.
"""

from __future__ import annotations

import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

from . import coherence, runtimes, sample, token_counter, transport
from .runtimes import CACHE_STATES

# Imported at runtime, not under TYPE_CHECKING: load_run rebuilds a record with the class
# that wrote it, from transport.py itself rather than from a re-bound module handle.
from .transport import Observation

# Warmup is measured, not pinned: a workload's window keeps issuing requests until its decode
# rate stops moving. The 2026-09-15 grid, per-column median ``change_pct`` across the MEASURED
# window on the decode workload -- every sign positive, cells still getting faster when their
# window closed:
#
#     mlx-lm +17.0% (11 of its 12 rows over 5%)   oMLX +2.6%   mlx-optiq -0.0%
#     vMLX +0.5%                                  Osaurus +1.0%
#
# Three requests leaves mlx-lm climbing and the other four settled, so one budget applied to
# five runtimes ranked them by warmup speed and called it serving speed: mlx-lm is last in 11
# of 14 decode orderings on the published median and 1st/3rd/3rd/4th on the late-window one.
# Raising the budget would pay mlx-lm's cost on four runtimes that do not need it, so the
# budget becomes a measured property of the cell and ``warmup_count`` publishes what it took.
MIN_WARMUP = 3            # the floor a caller pinning a fixed budget may not go below
WARMUP_WINDOW = 5         # rates per window; the rule compares the medians of two of them
WARMUP_CAP = 20           # the window closes here whether or not it settled
WARMUP_PLATEAU_PCT = 3.0  # the step between two window medians, in percent

# Why the rule compares TWO windows and not one. Measured 2026-09-16, oMLX serving
# Qwen3.5-4B-oQ4, fourteen identical chat requests in a flat loop with no harness structure
# around them -- decode tok/s:
#
#   103.5  102.8  103.3 | 70.8  73.4  75.7  73.6  75.2  75.3  74.6  72.0  73.8  72.9  73.3
#
# The machine serves the first three requests from a boost state and then steps down ~29% to
# the rate it holds. Total request time confirms it is the runtime and not the stream
# re-chunking: request 1 spends 1.24 s generating, request 4 spends 1.81 s for the same 128
# tokens.
#
# The boost phase is FLAT -- 0.5% spread across those three -- so a rule asking whether the last
# few rates AGREE WITH EACH OTHER calls the cell warm at request three, at a rate 40% above what
# it can sustain. Warmth is a rate the cell is still holding a window later, so the rule compares
# two consecutive windows and never the spread inside one.
#
# Variance is not warmth, and this is the second thing the machine had to teach. mlx-lm serving
# stock-4bit, first cell of the 03:30Z column -- the prefill workload's warmup rates:
#
#   70.3 74.7 72.5 77.1 71.9 78.6 77.5 73.6 70.2 70.9 75.2 64.8 72.5 71.3 76.8 75.4
#
# That cell has no trend at all. It is warm from request one and simply noisy at +/-8%, and a
# rule that required three consecutive rates to agree within 3% could never be satisfied by it:
# it ran to the cap, spent sixteen requests learning nothing, and reported "did not settle" about
# a cell with nothing left to warm. Noise is a property of the workload -- a 128-token chat
# varies far more per request than a 512-token decode -- and reading it as unfinished warmup
# conflates two different things, which is the conflation this whole rule exists to undo.
#
# So the test is a TREND test on robust statistics: the median of the last WARMUP_WINDOW rates
# against the median of the WARMUP_WINDOW before them. Five, not three, because a median of
# three of those prefill rates is itself noise. Against every sequence measured so far -- the
# boost-and-step loop above, that prefill row, its chat row, and a decode row still climbing --
# this settles at requests 11, 10, 13 and past 6 respectively, and the rate it settles on matches
# the first measured request to about 1% on the two that are not intrinsically noisy.

# The header's ``warmup`` is the rule rather than a count when this is asked for.
WARMUP_MODE = "plateau"

VISIT_ROUNDS = 2
TEMPERATURE = 0.0
SEED = 0
RESULTS_FILENAME = "results.jsonl"

INCOHERENT_PREFIX = "incoherent output: "

# transport.py's empty-content failure: the stream closed without a single content delta.
# It is measure's only signal that a response emitted nothing in the content channel, and it
# is the shape a model that spent its whole budget in the reasoning channel arrives in. The
# reasoning it did emit is judged like any other output; only a response with nothing in
# either channel is still thinking.
EMPTY_CONTENT_ERROR = "chat stream produced no content"

# The still-thinking cell's own reason, never an incoherence verdict: the response produced
# neither content nor reasoning, so there is no output to judge and no figure to publish.
STILL_THINKING = "still thinking: no content within max_tokens"

# Indirection so a test can watch cooldowns without waiting for them.
_sleep = time.sleep


@dataclass(frozen=True)
class Cell:
    """One measured configuration. ``id`` is ``<format>__<runtime>``."""

    id: str
    runtime: str
    artifact_dir: str
    label: str


@dataclass(frozen=True)
class Workload:
    """One corner of the space. ``id`` is the column key in every report.

    ``max_tokens`` lives here rather than on the run because the shapes need different caps:
    a prefill probe that generated 512 tokens would be measuring decode. Every request in a
    workload uses that workload's cap, which is what keeps one workload's decode tok/s out of
    the other's.
    """

    id: str
    messages: list[dict]
    max_tokens: int


@dataclass
class CellResult:
    """Everything one (cell, workload) pair produced, raw observations included."""

    cell: Cell
    workload_id: str
    status: str
    reason: str | None
    observations: list[Observation]
    # Wall-clock seconds per measured batch, one entry per batch, in the order the batches were
    # run. Empty for a run that had no batch to span: at ``concurrency=1`` a batch is one
    # request, no clock is taken around it, and ``[]`` is exactly true of a sequential run
    # rather than a default standing in for a measurement nobody made. A sequential record's
    # spans are never reconstructed from its per-request ``total_s`` — a gap between two
    # sequential requests belongs to neither one.
    batch_spans: list[float]
    warmup_observations: list[Observation]
    # How the warmup window ended. ``True`` when every window on this row reached the plateau,
    # ``False`` when any ran to ``WARMUP_CAP`` still climbing, ``None`` when no plateau window
    # ran at all -- no visit reached the row, or the budget was fixed and the rule was never in
    # force. A row that hit the cap was still climbing, and rendering it like one that settled
    # is the defect this field exists to prevent.
    warmup_plateau: bool | None
    cold_load_s: float | None
    # The cold visit's first warmup latency: the load a runtime that loads lazily deferred
    # past readiness, charged to request #1. Never added to a request's timing and never
    # folded into cold_load_s; ``None`` when this cell was never visited, or when that first
    # request did not come back.
    first_request_s: float | None
    # Which workload made that request. One request has one owner -- the shape that ran first
    # -- and it is recorded on every row of the cell beside the latency, the way the latency
    # itself is, because the visit's number stays the visit's fact while the note that reads
    # it as a deferred load is a claim only the row that paid it can make.
    first_request_workload_id: str | None
    memory: dict
    runtime_version: str | None
    disk_bytes: int | None
    # The reason a planned visit to this cell was lost before the visit that measured it. A
    # visit that fails writes its reason on the row, and the next visit's verdict rewrites the
    # row's status and reason from the samples that survived -- which erased the failure. Seen:
    # the prompt sweep's Osaurus 128, where visit 1's ``runtime.start()`` raised, visit 2
    # measured its quota of four, and the row was published PASS/None with nothing saying a
    # visit was missing. The reason is kept here, where :func:`_set_status` cannot overwrite
    # it; ``None`` means no visit was lost.
    lost_visit_reason: str | None = None
    # Whether the start that recorded ``cold_load_s`` came after a lost visit rather than
    # first. The figure is still the start's own, but it is a later, warm-page-cache start and
    # not the cell's cold one, which the cold load column alone cannot say.
    cold_load_after_lost_visit: bool = False
    # The run's batch pin, stamped on every row by :func:`run_cells` with the ``measured`` it
    # was given. It is what tells the report a row fell short of the run's window, and it is
    # the run's own number rather than the default this module would use if left to itself.
    # **Not written to the record**: the run header owns it there, one copy per run, and a copy
    # per line would be the duplication the record's rules forbid -- so a result rebuilt by
    # `load_run` carries ``None``, and a caller joining run directories passes each run's own
    # header pin to ``report.summarize`` instead.
    measured_pin: int | None = None


def decode_tps(observation) -> float | None:
    """Content tokens per second of the decode window, or ``None`` if undefined.

    ``total_s`` is deliberately not a fallback: it includes the final usage chunk,
    ``[DONE]`` and stream teardown, and dividing by it is the fork this project deleted.
    """
    if observation.ttft_s is None or observation.last_content_s is None:
        return None
    span = observation.last_content_s - observation.ttft_s
    if span <= 0 or not observation.completion_tokens:
        return None
    return observation.completion_tokens / span


def prefill_tps(observation) -> float | None:
    """Prompt tokens per second of prefill, from ``usage.prompt_tokens``."""
    if observation.ttft_s is None or observation.ttft_s <= 0 or not observation.prompt_tokens:
        return None
    return observation.prompt_tokens / observation.ttft_s


def itl_s(observation) -> float | None:
    """Mean gap between successive output tokens after the first."""
    if observation.ttft_s is None or observation.last_content_s is None:
        return None
    if not observation.completion_tokens:
        return None
    span = observation.last_content_s - observation.ttft_s
    if span < 0:
        return None  # a last delta before the first is a broken clock, not an interval
    return span / max(1, observation.completion_tokens - 1)


def measured_drift(observations) -> dict | None:
    """How far the cell moved across its own measurement window, and in which direction.

    The measured samples are split in half in the order they were taken — the first half
    is the cell's cool visit, the second half its hot one — and the medians are compared.
    Both signs are readings, and they mean different things. A **negative** change is the
    thermal curve the interleave exists to expose: the cell ran slower late than early. A
    **positive** one is not the cell speeding up for free — it had not finished warming up
    when its window closed, so the rate it published is an early-window rate and the warmup
    budget was too short for it. That is the direction every column of the 2026-09-15 grid
    leaned, which makes it the ordinary reading here rather than the surprising one.
    ``None`` when there are not two rates to compare.
    """
    rates = [rate for observation in observations if (rate := decode_tps(observation)) is not None]
    if len(rates) < 2:
        return None
    half = len(rates) // 2
    early = statistics.median(rates[:half])
    late = statistics.median(rates[-half:])
    return {
        "early_median_tps": early,
        "late_median_tps": late,
        "change_pct": ((late - early) / early * 100.0) if early else None,
        "n": len(rates),
    }


def visit_plan(cells: list[Cell], *, rounds: int = VISIT_ROUNDS) -> list[list[Cell]]:
    """The cells to visit each round, with the direction alternating.

    Round 1 walks the config order, round 2 walks it backwards, round 3 forwards again.
    This is the alternate-order pairing the predecessor used between two routes, applied
    where it was needed instead: over cells. No cell is measured only while the machine is
    cool, and none only once it is throttled.
    """
    return [list(cells) if index % 2 == 0 else list(reversed(cells)) for index in range(rounds)]


def artifact_bytes(path: str) -> int | None:
    """On-disk size of an artifact, sidecar files included, or ``None`` if absent.

    Files are counted once by ``(device, inode)``. That is what makes a HuggingFace cache
    snapshot correct: its files are symlinks to blobs that several snapshots share.
    """
    root = Path(path)
    if not root.exists():
        return None
    seen = set()
    total = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            try:
                stat = os.stat(os.path.join(dirpath, name))
            except OSError:
                continue
            key = (stat.st_dev, stat.st_ino)
            if key in seen:
                continue
            seen.add(key)
            total += stat.st_size
    return total


def _warmup_pin(warmup: int | str) -> int | dict:
    """The run header's ``warmup``, and the validation that goes with it.

    The rule in force is the pin, not a count: one header naming one budget for five runtimes
    is the reading this phase exists to stop publishing. A fixed budget is the caller's to
    name and stays an integer, because the rule did not run and the header must not claim it
    did.
    """
    if isinstance(warmup, int):
        if warmup < MIN_WARMUP:
            raise ValueError(
                f"warmup must be >= {MIN_WARMUP}: model load, Metal shader compilation and "
                "lazy mmap all have to land outside the measurement"
            )
        return warmup
    if warmup != WARMUP_MODE:
        raise ValueError(
            f"warmup must be {WARMUP_MODE!r} or an int >= {MIN_WARMUP}, not {warmup!r}"
        )
    return {
        "mode": WARMUP_MODE,
        "window": WARMUP_WINDOW,
        # Two windows, so the floor is twice one: a rule that can call a cell warm inside a
        # single window cannot tell a warm rate from a boost rate holding steady.
        "floor": 2 * WARMUP_WINDOW,
        "cap": WARMUP_CAP,
        "plateau_pct": WARMUP_PLATEAU_PCT,
    }


def run_cells(
    cells: list[Cell],
    workloads: list[Workload],
    *,
    warmup: int | str = WARMUP_MODE,
    measured: int = 9,
    concurrency: int = 1,
    cache_state: str | None = None,
    cooldown_s: float = 30.0,
    prompt_tokens: dict | None = None,
    results_dir: str,
) -> list[CellResult]:
    """Measure every cell under every workload; one :class:`CellResult` per pair.

    A visit starts the cell's runtime **once** and runs every workload under that one load,
    so the model is loaded twice per cell however many workloads there are. ``measured``
    **batches** are made per (cell, workload) in total, split across the visits the plan calls
    for (nine becomes five then four), and every workload gets its own warmup window because a
    long prompt compiles a different set of kernels than a short one does. Findings are
    published per workload: a prefill-bound number blended with a decode-bound one describes no
    workload that was run.

    ``concurrency`` is how many requests a batch holds, issued together under one clock. At 1
    — the default — a batch is one request and this is the run every column so far was measured
    by, record for record. At 8, nine batches are 72 requests and nine spans. Concurrency is a
    property of how the run drove the cells rather than of a cell, so it is a header pin: a
    sweep is N runs differing in that one field, joined afterwards.

    ``prompt_tokens`` is the prompt-length pin, and it is written to the header verbatim:
    ``{"target": N, "achieved": M}`` for a run whose prompt was sized to N tokens, or ``None``
    for the three pinned workloads, which send their own literals. Nothing here computes or
    checks it -- the prompt is sized against the serving tokenizer by the caller, before this
    function is called -- and like ``concurrency`` it describes how the run drove the cells
    rather than a cell, so a sweep of it is N runs differing in this one field.

    ``cache_state`` is the same kind of pin: ``"off"`` or ``"on"`` for a run whose cells were
    measured with their prefix/KV reuse disabled or enabled, and ``None`` when the pin was not
    taken. ``None`` is not a third state and is never read as ``"off"`` -- every run measured
    before the pin existed ran each runtime's own default and those defaults were not uniform
    -- so it rides into the header as the absence it is and into each start command as no flag
    at all. The state is asked of the runtime before it is started
    (:meth:`runtimes.Runtime.cache_state_refusal`), and a runtime that cannot be driven into
    the requested state is ``N/A`` with that reason rather than measured in the other state.

    ``warmup`` is the plateau rule by default and an ``int`` for a fixed budget of that many
    batches; either way the budget each cell needed is published as ``warmup_count``. Results
    are written to ``<results_dir>/results.jsonl`` after every visit, so a run that dies still
    has everything it had measured up to that point.

    The returned results are in first-visit order, each cell's workloads kept together in the
    order they were given.
    """
    warmup_pin = _warmup_pin(warmup)
    if measured < 1:
        raise ValueError("measured must be >= 1")
    if concurrency < 1:
        raise ValueError(
            f"concurrency must be >= 1, not {concurrency!r}: a batch is at least one request"
        )
    if cache_state not in (None, *CACHE_STATES):
        raise ValueError(
            f"cache_state must be one of {CACHE_STATES} or None, not {cache_state!r}: None is "
            "the pin not taken and not a third state, which is why it is also not 'off' -- "
            "the runs measured before the pin existed ran each runtime's own default, and "
            "those defaults were not uniform"
        )
    if cooldown_s < 0:
        raise ValueError("cooldown_s must be >= 0")
    workloads = _workloads(workloads)

    results_path = Path(results_dir) / RESULTS_FILENAME
    results_path.parent.mkdir(parents=True, exist_ok=True)
    run = {
        "workloads": [
            {
                "id": workload.id,
                "messages": workload.messages,
                "max_tokens": workload.max_tokens,
            }
            for workload in workloads
        ],
        "temperature": TEMPERATURE,
        "seed": SEED,
        "warmup": warmup_pin,
        "measured": measured,
        # How the run drove the cells, pinned beside the sampling pins so a sweep declares it
        # with one header field and a join compares it like every other hold-constant.
        "concurrency": concurrency,
        # The prompt-length pin, verbatim, and `None` for the three pinned workloads. This
        # module does not compute it: the caller sized the prompt against the serving
        # tokenizer, and a pin this module re-derived would be its own opinion about what the
        # columns sent.
        "prompt_tokens": prompt_tokens,
        # How the run drove the cells, one more time: `"off"`/`"on"` for a run whose cells
        # were measured with prefix/KV reuse disabled/enabled, and `None` for the pin not
        # taken. `None` is not `"off"` in the header either -- an absent pin means each
        # runtime ran its own default, which is a different fact from a disabled cache.
        "cache_state": cache_state,
        "cooldown_s": cooldown_s,
    }

    results: list[CellResult] = []
    by_key: dict[tuple[str, str], CellResult] = {}
    counters: dict[str, tuple] = {}
    unmeasurable: set[str] = set()

    visits = _visits(cells, measured=measured)
    # Each cell's lost reason, held for the visit that may still measure. A failed visit writes
    # it on the row, and the next visit's verdict overwrites it there -- so it is kept here
    # until that verdict lands, and then recorded beside it.
    lost: dict[str, str] = {}
    for index, (cell, quota) in enumerate(visits):
        if cell.id in unmeasurable:
            # A cell that cannot run here is not visited again, and nothing waits for it.
            continue

        cell_results = _results_for(cell, workloads, by_key, results, measured=measured)
        measured_before = sum(len(result.observations) for result in cell_results)
        outcome = _visit(cell_results, cell, workloads, warmup=warmup, quota=quota,
                         concurrency=concurrency, cache_state=cache_state, counters=counters)
        if outcome == "measured":
            reason = lost.pop(cell.id, None)
            for result in cell_results:
                if reason is not None:
                    # The visit that measured is a later one, and both facts that makes are
                    # kept: the reason a visit is missing, and that the cold load this row now
                    # carries is that later start's rather than the cell's first.
                    result.lost_visit_reason = reason
                    result.cold_load_after_lost_visit = result.cold_load_s is not None
                _set_status(result)
        elif outcome == "skip":
            unmeasurable.add(cell.id)
        elif outcome == "retry":
            # "retry" keeps the reason the failed visit wrote, and the next visit tries again.
            lost[cell.id] = cell_results[0].reason

        write_jsonl(results, results_path, run=run)
        # A cooldown after a visit that started no runtime and took no sample is 30
        # seconds spent cooling nothing.
        sampled = sum(len(result.observations) for result in cell_results)
        if sampled > measured_before and index < len(visits) - 1:
            _sleep(cooldown_s)

    return results


def _results_for(
    cell: Cell,
    workloads: list[Workload],
    by_key: dict[tuple[str, str], CellResult],
    results: list[CellResult],
    *,
    measured: int | None = None,
) -> list[CellResult]:
    """This cell's result per workload, created on the first visit and reused after.

    The pair is the key, so a cell's three shapes are three results rather than three
    measurements collapsed into one. The run's batch pin is stamped on each one as it is
    created: the row it belongs to is the row that can fall short of it.
    """
    cell_results = []
    for workload in workloads:
        result = by_key.get((cell.id, workload.id))
        if result is None:
            result = CellResult(
                cell=cell,
                workload_id=workload.id,
                status="N/A",
                reason=None,
                observations=[],
                batch_spans=[],
                warmup_observations=[],
                warmup_plateau=None,
                cold_load_s=None,
                first_request_s=None,
                first_request_workload_id=None,
                memory={},
                runtime_version=None,
                disk_bytes=artifact_bytes(cell.artifact_dir),
                measured_pin=measured,
            )
            by_key[(cell.id, workload.id)] = result
            results.append(result)
        cell_results.append(result)
    return cell_results


def _visits(cells: list[Cell], *, measured: int) -> list[tuple[Cell, int]]:
    """Flatten the plan into (cell, measured-batches-this-visit) pairs.

    Visits with a zero quota are dropped: starting a runtime to measure nothing costs a
    full model load for no sample. The quota splits batches, so a cell measured at
    ``concurrency=8`` with ``measured=9`` takes five batches of eight on the cold visit and
    four on the hot one — the same 5/4 imbalance in the same direction, N times the requests.
    """
    quotas = [
        measured // VISIT_ROUNDS + (1 if index < measured % VISIT_ROUNDS else 0)
        for index in range(VISIT_ROUNDS)
    ]
    visits: list[tuple[Cell, int]] = []
    for index, ordering in enumerate(visit_plan(cells)):
        if quotas[index] == 0:
            continue
        visits.extend((cell, quotas[index]) for cell in ordering)
    return visits


def _visit(
    results: list[CellResult],
    cell: Cell,
    workloads: list[Workload],
    *,
    warmup: int | str,
    quota: int,
    concurrency: int,
    cache_state: str | None,
    counters: dict,
) -> str:
    """One visit to one cell, returning ``"measured"``, ``"retry"`` or ``"skip"``.

    The runtime is started once and every workload runs under that load, then it is stopped:
    reloading the weights per workload would triple the cost of the only expensive step here.
    ``"skip"`` means the cell cannot run here at all and no later visit will change that.
    ``"retry"`` means this visit failed for a reason that may not hold next time — a runtime
    that will not load is usually deterministic, but a port still held by a stale server is
    not — and the samples already taken, if any, stand.

    The requested cache state is asked of the runtime before anything is started, and a state
    the runtime cannot be driven into is ``"skip"`` with the reason on every row: a cell whose
    cache state the host disagrees with is not a cell that is briefly unavailable, and
    measuring it anyway would publish a number under a header pin it does not hold. The check
    is the runtime's to answer because only it knows its mechanism -- a start flag, or for
    Osaurus a settings file the harness does not edit.
    """
    runtime = runtimes.RUNTIMES.get(cell.runtime)
    if runtime is None:
        reason = f"unknown runtime {cell.runtime!r}; known runtimes: {sorted(runtimes.RUNTIMES)}"
        for result in results:
            _na(result, reason)
        return "skip"

    counter, counter_error = _token_counter(cell, counters)
    if counter is None:
        reason = f"token counter unavailable for {cell.artifact_dir}: {counter_error}"
        for result in results:
            _na(result, reason)
        return "skip"

    refusal = runtime.cache_state_refusal(cache_state)
    if refusal is not None:
        for result in results:
            _na(result, refusal)
        return "skip"

    try:
        # The artifact directory doubles as the model-id hint; the runtime resolves it to
        # whatever it calls those weights, and that resolved name is what gets recorded.
        handle = runtime.start(
            cell.artifact_dir, cell.artifact_dir, cache_state=cache_state
        )
    except Exception as error:  # noqa: BLE001 - a runtime that will not load is a result
        reason = f"runtime {cell.runtime!r} did not start: {type(error).__name__}: {error}"
        for result in results:
            if result.observations:
                result.status, result.reason = "FAIL", reason
            else:
                _na(result, reason)
        return "retry"

    # The same rule decides the cold visit for the first request: it is the one whose load has
    # not been recorded yet. Read before the rows take their cold load, because by then every
    # one of them carries it.
    cold_visit = all(result.cold_load_s is None for result in results)

    for result in results:
        if result.cold_load_s is None:
            # The first visit's load is the cold one; a later visit starts from a warm page
            # cache. One load is shared by the cell's workloads, so it is recorded on every
            # one of their rows rather than on whichever shape happened to run first.
            result.cold_load_s = handle.cold_load_s
            result.runtime_version = handle.version

    try:
        for result, workload in zip(results, workloads):
            memory = _workload_visit(handle, result, workload, warmup=warmup, quota=quota,
                                     concurrency=concurrency, counter=counter)
            result.memory = _highest_peak(result.memory, memory)
    finally:
        handle.stop()

    if cold_visit:
        # Warmup #1 is where a lazy loader pays for its weights. One load is shared by the
        # cell's workloads, so the cost is recorded on the handle and on every one of their
        # rows rather than on whichever shape happened to run first -- and beside it the one
        # shape that made that request, because a row that did not make it has no latency of
        # its own to read against its own measured requests.
        carrier = _first_warmup_result(results)
        handle.first_request_s = _first_warmup_latency(results)
        for result in results:
            result.first_request_s = handle.first_request_s
            result.first_request_workload_id = None if carrier is None else carrier.workload_id

    return "measured"


def _first_warmup_result(results: list[CellResult]) -> CellResult | None:
    """The workload that made the cold visit's first request, or ``None`` when none did.

    A visit's requests are made workload by workload and recorded in that order, so the first
    workload holding a warmup observation is request #1's owner. One request has one owner: the
    shape that ran first answers for it, not all three of them. A visit that made no request
    has no such row, and nothing is recorded for it.
    """
    return next((result for result in results if result.warmup_observations), None)


def _first_warmup_latency(results: list[CellResult]) -> float | None:
    """The cold visit's first warmup latency: what request #1 cost, load included.

    The request is the first warmup of the workload :func:`_first_warmup_result` names.
    ``None`` when it did not come back: a failed request's duration is how long it waited for
    the failure, not what the runtime charged for the load, and the load is what this is for.
    """
    result = _first_warmup_result(results)
    if result is None:
        return None
    first = result.warmup_observations[0]
    return first.total_s if came_back(first) else None


def _workload_visit(
    handle,
    result: CellResult,
    workload: Workload,
    *,
    warmup: int | str,
    quota: int,
    concurrency: int,
    counter,
) -> dict:
    """One workload's requests inside a visit, sampled over that workload's own window.

    The sampler covers this workload alone. A visit that ran a 512-token decode and a
    128-token chat has two different memory peaks, and publishing the visit's peak under both
    names would report decode's footprint as chat's.

    ``quota`` counts batches, and every request in one is kept: a batch at ``concurrency=4``
    leaves four observations and one span on the row, because the observations are what the
    per-request figures and the gate are read from and the span is what aggregate throughput is.
    """
    # The handle's pid, not the one this run spawned: a runtime whose launcher handed the
    # port to an app process is measured on the process that holds the weights.
    sampler = sample.Sampler(handle.memory_pid).start()
    memory = None
    try:
        result.warmup_plateau = _plateau_verdict(
            result.warmup_plateau,
            _warmup_window(handle, result, workload, warmup=warmup, concurrency=concurrency,
                           counter=counter),
        )
        for _ in range(quota):
            observations, span = _batch(handle, workload.messages,
                                        max_tokens=workload.max_tokens, concurrency=concurrency,
                                        counter=counter)
            result.observations.extend(observations)
            if span is not None:
                result.batch_spans.append(span)
    finally:
        memory = sampler.stop()
    return memory


def _warmup_window(
    handle,
    result: CellResult,
    workload: Workload,
    *,
    warmup: int | str,
    concurrency: int,
    counter,
) -> bool | None:
    """One workload's warmup window, ending when the cell is warm or its budget is spent.

    A fixed ``int`` issues exactly that many batches and returns ``None``: the rule never
    ran, so there is no plateau for the window to report. ``"plateau"`` issues two windows of
    ``WARMUP_WINDOW`` rates and then keeps going until the rate stops moving -- the median
    of the last window must be within ``WARMUP_PLATEAU_PCT`` of the median of the one before
    it. It is a trend test and not a variance test: one flat window is a boost state holding
    steady as often as it is a warm cell, and a noisy workload is not an unwarmed one. One
    step is one batch, so at ``concurrency=1`` that is one request and above it a batch of
    ``concurrency`` of them; either way one rate is appended per step. The rates come from
    :func:`_warmup_rate` -- :func:`decode_tps` at ``concurrency=1``, the batch's aggregate
    throughput above it -- so a step carrying no rate, a failed request or a batch that did not
    come back whole, is not evidence that the cell stopped moving and cannot settle the window;
    only ``WARMUP_CAP`` ends it.

    ``True`` for a window the rule closed, ``False`` for one that ran to the cap still
    climbing. Every request made is kept on ``result.warmup_observations`` as it is made,
    whether it settled anything or not.
    """
    fixed = isinstance(warmup, int)
    rates: list[float | None] = []
    while True:
        observations, span = _batch(handle, workload.messages, max_tokens=workload.max_tokens,
                                    concurrency=concurrency, counter=counter)
        result.warmup_observations.extend(observations)
        rates.append(_warmup_rate(observations, span, concurrency=concurrency))
        if fixed:
            if len(rates) >= warmup:
                return None
            continue
        if _settled(rates):
            return True
        if len(rates) >= WARMUP_CAP:
            return False


def _warmup_rate(observations: list[Observation], span: float | None, *, concurrency: int
                 ) -> float | None:
    """The rate one warmup batch contributes to the window's series.

    At ``concurrency=1`` it is the request's own decode rate from :func:`decode_tps` -- the
    series every warmup window has always read, unchanged. Above 1 it is the batch's aggregate
    throughput: every completion token the batch produced over the span of its shared clock,
    which is also the quantity a concurrency sweep publishes, so the cell warms on the number
    it reports.

    Plan 06-01a measured why the series has to change: oMLX at N=8, sixteen batches of the
    ``chat`` workload, the per-request median swinging between 65.3 and 81.0 tok/s with no
    trend, which a 3% two-window rule can never satisfy, while aggregate throughput held a
    62.1-68.3 band and settled at batch 12. Read as unfinished warmup, that is the noise the
    prefill workload already taught this rule not to mistake for a cold cell -- except the
    window could never close at all, so every concurrent cell would pay the cap and report
    "did not settle" about a cell with nothing left to warm.

    A batch that did not come back whole produced no rate, for the reason a failed request
    produces none at ``concurrency=1``: the aggregate of a batch with a dead request in it is
    not the quantity the window is watching. ``None`` cannot settle a window.
    """
    if concurrency == 1:
        return decode_tps(observations[0])
    if span <= 0 or not all(came_back(observation) for observation in observations):
        return None
    tokens = sum(observation.completion_tokens or 0 for observation in observations)
    if not tokens:
        return None
    return tokens / span


def _batch(
    handle, messages: list[dict], *, max_tokens: int, concurrency: int, counter
) -> tuple[list[Observation], float | None]:
    """One batch: ``concurrency`` requests issued together, and the span of their clock.

    Returns every request's observation in submission order, whatever it came back with, and
    the wall-clock seconds the whole batch took. ``concurrency=1`` is the sequential case and
    returns no span: a batch of one is issued exactly as every request was issued before
    batches existed, and a span around a single request is not a batch span -- reconstructing
    one from its ``total_s`` is how a record would come to claim a clock nobody took.

    The clock is around the whole batch because summing per-request spans would count the
    overlap N times, and at N requests sharing one GPU it is aggregate throughput -- their
    tokens over the batch's span -- that says whether batching paid. Threads and not processes:
    ``transport.chat`` is blocked on an SSE stream, so the pool drives requests rather than
    re-implementing one -- the same :func:`_request` runs in it that runs sequentially, so
    there is one definition of TTFT, one decode window and one failure shape at every N.

    # ponytail: one pool per batch, so thread creation lands inside the span it helps measure.
    # Ceiling: that span reads a fraction of a millisecond long and the aggregate a fraction
    # low -- the conservative direction. Upgrade path: one pool per visit, reused per workload.
    """
    if concurrency == 1:
        return [_request(handle, messages, max_tokens=max_tokens, counter=counter)], None
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [
            pool.submit(_request, handle, messages, max_tokens=max_tokens, counter=counter)
            for _ in range(concurrency)
        ]
        observations = [future.result() for future in futures]
    return observations, time.monotonic() - started


def _settled(rates: list[float | None]) -> bool:
    """Whether the cell is warm: the rate it is holding now is the rate it held a window ago.

    The medians of the last two windows of ``WARMUP_WINDOW`` rates, compared against
    ``WARMUP_PLATEAU_PCT``. It is a trend test and deliberately not a variance test -- a
    workload whose per-request rate swings +/-8% with no trend is a noisy workload, not an
    unwarmed one, and a rule that demanded agreement between neighbouring requests would run
    every such cell to the cap and report "did not settle" about a cell with nothing left to
    warm. Medians of five rather than three because a median of three noisy rates is itself
    noise.

    A rate the cell did not produce -- a failed request, or a stream with no decode window --
    is not a measurement a median can be taken over, so a window holding one cannot settle and
    only ``WARMUP_CAP`` ends it.

    The series is whatever :func:`_warmup_rate` appends, one rate per batch: per-request decode
    rates at ``concurrency=1`` and per-batch aggregate throughput above it. The rule is the same
    rule at both, and this function has no opinion about which series it was handed.
    """
    if len(rates) < 2 * WARMUP_WINDOW:
        return False  # fewer rates than the rule reads is not a settled cell, it is no answer
    last = rates[-WARMUP_WINDOW:]
    previous = rates[-2 * WARMUP_WINDOW:-WARMUP_WINDOW]
    if any(rate is None for rate in last + previous):
        return False
    before = statistics.median(previous)
    if before <= 0:
        return False
    return abs(statistics.median(last) - before) / before * 100.0 <= WARMUP_PLATEAU_PCT


def _plateau_verdict(current: bool | None, window: bool | None) -> bool | None:
    """What one more warmup window makes of the row's verdict.

    ``False`` is sticky: a row that ran to the cap on any visit did not settle, whatever the
    other visit's window did. ``None`` is what both sides being ``None`` leaves -- a row no
    visit reached, or one measured under a fixed budget.
    """
    if current is False or window is False:
        return False
    if current is True or window is True:
        return True
    return None


def _request(handle, messages: list[dict], *, max_tokens: int, counter) -> Observation:
    """One request, with the pins applied and a transport failure kept as an observation."""
    started = time.monotonic()
    try:
        return transport.chat(
            handle.base_url,
            handle.model_id,
            messages,
            max_tokens=max_tokens,
            temperature=TEMPERATURE,
            seed=SEED,
            token_counter=counter,
            # oMLX answers an unauthenticated request with HTTP 401, and a run that never
            # sends this key measures a server that loaded no weights at all.
            api_key=handle.api_key,
        )
    except Exception as error:  # noqa: BLE001 - a dead server is a FAILed cell, not a crash
        return transport.Observation(
            ok=False,
            error=f"{type(error).__name__}: {error}",
            ttft_s=None,
            last_content_s=None,
            total_s=time.monotonic() - started,
            prompt_tokens=None,
            completion_tokens=None,
            reasoning_tokens=None,
            content_event_count=0,
            text="",
            token_source="none",
        )


def _token_counter(cell: Cell, counters: dict) -> tuple[object | None, str | None]:
    if cell.id not in counters:
        try:
            counters[cell.id] = (token_counter.TokenCounter(cell.artifact_dir), None)
        except Exception as error:  # noqa: BLE001 - reported as N/A, never swallowed
            counters[cell.id] = (None, f"{type(error).__name__}: {error}")
    return counters[cell.id]


def _highest_peak(current: dict, candidate: dict | None) -> dict:
    """The visit whose sampled peak is higher. Both are real; the bigger one is the cell's."""
    if not candidate:
        return current
    if not current:
        return candidate
    if current.get("peak_mb") is None:
        return candidate
    if candidate.get("peak_mb") is None:
        return current
    return candidate if candidate["peak_mb"] > current["peak_mb"] else current


def _set_status(result: CellResult) -> None:
    """PASS only when every measured request carried what the published metrics need.

    A cell that produced no language is FAIL however fast it was, and a FAILed cell is not
    a result: no tok/s, TTFT, ITL or throughput figure is read from it. Its observations —
    the offending sample included, in whichever channel it was spelled — stay on the
    record, so the reason can be read against the text that earned it.
    """
    if not result.observations:
        # Nothing measured, so there is no verdict to give: the N/A or FAIL reason the
        # failed visit wrote stands. Only the next visit can move this.
        return

    failures = [
        observation for observation in result.observations if not came_back(observation)
    ]
    if failures:
        result.status = "FAIL"
        result.reason = (
            f"{len(failures)} of {len(result.observations)} measured requests failed; "
            f"first: {failures[0].error}"
        )
        return

    if all(_still_thinking(observation) for observation in result.observations):
        # Every measured response produced neither content nor reasoning. No output is not
        # bad output, so this cell gets its own reason and never an incoherence verdict.
        result.status, result.reason = "FAIL", STILL_THINKING
        return

    # The gate runs before the metric check. A response that answered only in the reasoning
    # channel carries no content window, so asking for its metrics first would report the
    # missing window and bury the garbage that is the reason there is nothing to publish.
    incoherent = _incoherent(result.observations)
    if incoherent is not None:
        result.status, result.reason = "FAIL", incoherent
        return

    missing = next(
        (reason for observation in result.observations
         if (reason := _missing_metric(observation)) is not None),
        None,
    )
    if missing is not None:
        result.status, result.reason = "FAIL", missing
        return

    result.status, result.reason = "PASS", None


def _judged_text(observation) -> str:
    """The text one response is judged on: its content, or its reasoning when content is empty.

    Content wins when a response carries both, because content is the channel the published
    metrics describe. A response that never left the reasoning channel has still produced
    output — it is simply spelled in the other channel, and the gate reads it there.
    """
    if observation.text.strip():
        return observation.text
    return observation.reasoning_text


def came_back(observation) -> bool:
    """The request reached the model, and the model answered in whichever channel.

    The transport reports a stream with no content delta as its empty-content failure. That
    is not a request that failed: it is a model that spent its budget in the reasoning
    channel, and what it wrote there is judged like any other output. Every other failure is
    the transport's, and :func:`_set_status` reports it as one.

    This is the definition ``report.py`` counts a cell's samples with. It is public for that
    reason and for that reason only: report respelling the condition as ``observation.ok`` is
    how a cell whose five requests all answered in the reasoning channel was published as
    ``n = 0/5`` beside the five samples that answered.
    """
    return observation.ok or observation.error == EMPTY_CONTENT_ERROR


def _still_thinking(observation) -> bool:
    """A response that produced neither content nor reasoning.

    Reasoning is not content and never becomes a published figure, but a response that
    answered in the reasoning channel is not an empty one: token salad there is token salad.
    Only a response with nothing in either channel is still thinking.
    """
    return came_back(observation) and not _judged_text(observation).strip()


def _incoherent(observations) -> str | None:
    """``"incoherent output: <first failing reason>"``, or ``None`` when the cell is language.

    The measured responses *are* the sample: this asks the question the gate exists for
    without making a request of its own, and it pins no expected answer, because an
    arbitrary workload declares none.

    A response is judged on its content, or on its reasoning when it emitted no content: a
    model that spends the whole budget in the reasoning channel has produced output, and
    garbage is garbage in either channel. A response that failed is a transport failure that
    :func:`_set_status` already reports, and a response with no text at all is not a wrong
    answer — no output is not bad output. Majority rule, taken over the responses that could
    be judged rather than over the requests that were made: a cell does not survive the gate
    by having most of its requests die.
    """
    judged = 0
    failures = 0
    first: str | None = None
    for observation in observations:
        if not came_back(observation):
            continue
        text = _judged_text(observation)
        if not text.strip():
            continue
        judged += 1
        passed, reason = coherence.is_coherent(text)
        if not passed:
            failures += 1
            first = first or reason
    if failures * 2 > judged:
        return f"{INCOHERENT_PREFIX}{first}"
    return None


def _missing_metric(observation) -> str | None:
    """Which published metric this observation cannot carry, or ``None`` when it can."""
    if decode_tps(observation) is None:
        if observation.ttft_s is None or observation.last_content_s is None:
            return "no content-delta timing, so decode tok/s is undefined"
        if not observation.completion_tokens:
            return (
                "no content completion tokens from "
                f"token_source={observation.token_source!r}, so decode tok/s is undefined"
            )
        return "empty decode window (ttft_s == last_content_s)"
    if prefill_tps(observation) is None:
        return "no usage.prompt_tokens, so prefill throughput is undefined"
    return None


def _na(result: CellResult, reason: str) -> None:
    result.status = "N/A"
    result.reason = reason


def _workloads(workloads: list[Workload]) -> list[Workload]:
    """The workloads, validated, their messages copied out of the caller's hands.

    A duplicate id is refused rather than measured: a result is keyed by (cell, workload),
    so two workloads sharing an id would share one row and quietly pool their observations
    instead of producing two.
    """
    if not workloads:
        raise ValueError("workloads must name at least one Workload")
    checked = []
    seen = set()
    for workload in workloads:
        if not workload.messages:
            raise ValueError(f"workload {workload.id!r} has no messages")
        if workload.id in seen:
            raise ValueError(
                f"duplicate workload id {workload.id!r}: results are keyed by "
                "(cell, workload), so two workloads of the same id are one result"
            )
        seen.add(workload.id)
        checked.append(
            Workload(
                id=workload.id,
                messages=[dict(message) for message in workload.messages],
                max_tokens=workload.max_tokens,
            )
        )
    return checked


def write_jsonl(results: list[CellResult], path: str | Path, *, run: dict) -> None:
    """The run's ``results.jsonl``: a header line of the pins, then one line per result.

    Line 1 is the run header — temperature, seed, warmup, measured, concurrency, prompt_tokens,
    cache_state, cooldown_s and every workload that was measured, each with the messages it sent
    and its own max_tokens (a single run-level cap would be a half-truth once three workloads
    carry three of them). ``warmup`` is the rule that was in force, as a dict, or the integer
    budget a caller pinned instead; which one it is is what tells a reader how to read
    ``warmup_count``. ``measured`` counts batches and ``concurrency`` says how many requests are
    in one, so the two together are how many requests a row holds — and ``concurrency`` is what
    a sweep varies and a join guard compares, because it is a property of how the run drove the
    cells, not of a cell. ``prompt_tokens`` rides beside it for the same reason: one prompt
    length, recorded with the count it achieved. ``cache_state`` does too: it is the state the
    cells were started in, and its absence is the pin not taken rather than a state.

    Every line after it is one (cell, workload) pair, naming the workload that produced it.
    Rewritten whole and atomically after every visit, so a run that dies still has everything
    it measured and no reader sees half a file.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(run, sort_keys=True) + "\n")
        for result in results:
            handle.write(json.dumps(_record(result), sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)


def _record(result: CellResult) -> dict:
    record = {
        "cell": asdict(result.cell),
        "workload_id": result.workload_id,
        "status": result.status,
        "reason": result.reason,
        "cold_load_s": result.cold_load_s,
        "first_request_s": result.first_request_s,
        # Which workload that request belonged to, so the report's deferred-load note stays
        # recomputable from the file rather than from the order the shapes happened to run in.
        "first_request_workload_id": result.first_request_workload_id,
        "memory": result.memory,
        "runtime_version": result.runtime_version,
        "disk_bytes": result.disk_bytes,
        "measured_count": len(result.observations),
        "warmup_count": len(result.warmup_observations),
        # How the warmup window ended, beside how long it ran. A row that hit the cap was
        # still climbing, and a reader who cannot tell it from one that settled is reading a
        # budget as if it were a warm cell.
        "warmup_plateau": result.warmup_plateau,
        "drift": measured_drift(result.observations),
        "observations": [asdict(observation) for observation in result.observations],
        # Warmups are not samples of the measured quantity — averaging a cold-start TTFT
        # into a percentile would be a lie — but they are still raw observations, so they
        # are kept here rather than thrown away.
        "warmup_observations": [
            asdict(observation) for observation in result.warmup_observations
        ],
    }
    # One span per measured batch, and the key is absent on a cell that ran none -- which is
    # every sequential run: at ``concurrency=1`` a batch is one request, and a record of one is
    # byte-identical to the record this module wrote before batches existed. That equivalence is
    # what keeps the columns already measured comparable, and it is why no span is filled in for
    # them from per-request ``total_s``: a gap between two sequential requests belongs to
    # neither one. `load_run` reads the absence as the ``[]`` it exactly is.
    if result.batch_spans:
        record["batch_spans"] = result.batch_spans
    # A lost visit is written only when there was one, for the same reason: a cell whose every
    # visit measured keeps the record it always wrote, byte for byte, and an absent key is read
    # back as no lost visit -- which is exactly true of every record written before the field
    # existed.
    if result.lost_visit_reason is not None:
        record["lost_visit_reason"] = result.lost_visit_reason
    if result.cold_load_after_lost_visit:
        record["cold_load_after_lost_visit"] = result.cold_load_after_lost_visit
    return record


def load_run(path: str | Path) -> tuple[dict, list[CellResult]]:
    """Read a run's ``results.jsonl`` back: its header, then one :class:`CellResult` per line.

    ``path`` is the run directory or the ``results.jsonl`` inside it; both name the same run.
    Line 1 is the run header, returned as it was written, and every line after it is one
    (cell, workload) pair, rebuilt with the shapes that wrote it: ``Cell(**record["cell"])``
    and ``Observation(**obs)`` are ``asdict``'s inverse by construction.

    The three **derived** fields a record also carries — ``measured_count``,
    ``warmup_count``, ``drift`` — are deliberately not read back. They are recomputed here
    from the observations that carry them, so a hand-edited file cannot publish a drift its
    own samples do not support. They stay in the file for a reader with ``jq``; this
    function ignores them.

    A file that cannot be read back raises :class:`ValueError` naming the path and the line
    number: an empty file, a first line that is not an object, a later line that is not a
    record. A truncated final line is the ordinary case — :func:`write_jsonl` is atomic, but
    a file copied mid-write is not — which is why the line number is the whole diagnosis.
    """
    target = Path(path)
    if target.is_dir():
        target = target / RESULTS_FILENAME
    lines = target.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ValueError(f"{target}: line 1: empty file, so there is no run header to read")
    header = _line_object(lines[0], target, 1)
    return header, [
        _cell_result(_line_object(line, target, number), target, number)
        for number, line in enumerate(lines[1:], start=2)
    ]


def _line_object(line: str, path: Path, number: int) -> dict:
    """One line decoded as a JSON object, or ``ValueError`` naming the line that is not one."""
    try:
        value = json.loads(line)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"{path}: line {number}: not JSON ({error.msg} at column {error.colno})"
        ) from error
    if not isinstance(value, dict):
        raise ValueError(
            f"{path}: line {number}: not a JSON object but a {type(value).__name__}"
        )
    return value


def _cell_result(record: dict, path: Path, number: int) -> CellResult:
    """One record rebuilt into the ``CellResult`` that wrote it, or its line number if not.

    Nothing here reads ``measured_count``, ``warmup_count`` or ``drift``: a record's derived
    fields are its writer's summary of its own observations, and a summary is not read back
    over the samples it summarizes.
    """
    try:
        return CellResult(
            cell=Cell(**record["cell"]),
            workload_id=record["workload_id"],
            status=record["status"],
            reason=record["reason"],
            observations=[Observation(**raw) for raw in record["observations"]],
            warmup_observations=[
                Observation(**raw) for raw in record["warmup_observations"]
            ],
            # Read leniently, and only this field. A record written before the plateau rule
            # existed was measured under a fixed budget, so the rule did not run on it and
            # `None` -- "no plateau verdict" -- is exactly true of those rows rather than a
            # default standing in for something unknown. That is what separates it from
            # `first_request_workload_id`, which is refused on a missing key: defaulting that
            # one would claim the cold visit made no request, which is false about rows whose
            # visit did. A default is honest when the absence is the fact; the 2026-09-16
            # columns stay readable by the tool that published them.
            warmup_plateau=record.get("warmup_plateau"),
            # Read leniently for the same shape of reason. A record written before concurrency
            # existed has no batch spans because it ran no batch, and `[]` is exactly true of it
            # -- a sequential run's requests are issued one at a time, so there was no clock to
            # take. It is not `[]` filled in from the per-request `total_s` either: a gap
            # between two sequential requests belongs to neither one, and a span no clock
            # measured is not a reader's to reconstruct.
            batch_spans=list(record.get("batch_spans", [])),
            cold_load_s=record["cold_load_s"],
            first_request_s=record["first_request_s"],
            first_request_workload_id=record["first_request_workload_id"],
            # Read leniently for the same shape of reason. Every record on disk was written
            # before a lost visit could be recorded, and no visit of theirs was lost, so the
            # absence IS the fact here rather than a default standing in for something unknown.
            lost_visit_reason=record.get("lost_visit_reason"),
            cold_load_after_lost_visit=record.get("cold_load_after_lost_visit", False),
            memory=record["memory"],
            runtime_version=record["runtime_version"],
            disk_bytes=record["disk_bytes"],
        )
    except (KeyError, TypeError) as error:
        raise ValueError(f"{path}: line {number}: not a cell record: {error}") from error
