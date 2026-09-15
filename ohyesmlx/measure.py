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
  the ``CellResult`` and is never added to a request's timing. ``warmup`` is enforced at a
  floor of 3 so Metal shader compilation and lazy mmap land before the first measured
  request.

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
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from . import coherence, sample

if TYPE_CHECKING:  # pragma: no cover - the shapes the loop is written against
    from .transport import Observation

# transport.py (issue #2), runtimes.py (issue #3) and token_counter.py are written
# concurrently against docs/interfaces.md, so this module has to stay importable while
# they are absent. A real run refuses to start without them; see _require_modules.
try:
    from . import token_counter
except ImportError:  # pragma: no cover - cleared as issues #2/#3 merge
    token_counter = None

try:
    from . import runtimes
except ImportError:  # pragma: no cover - cleared as issues #2/#3 merge
    runtimes = None

try:
    from . import transport
except ImportError:  # pragma: no cover - cleared as issues #2/#3 merge
    transport = None

MIN_WARMUP = 3
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


class MeasureError(RuntimeError):
    """The run cannot start: a module it measures through is missing."""


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
    warmup_observations: list[Observation]
    cold_load_s: float | None
    memory: dict
    runtime_version: str | None
    disk_bytes: int | None


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
    return span / max(1, observation.completion_tokens - 1)


def measured_drift(observations) -> dict | None:
    """How far the cell moved across its own measurement window.

    The measured samples are split in half in the order they were taken — the first half
    is the cell's cool visit, the second half its hot one — and the medians are compared.
    A cell whose late samples are slower than its early ones is the thermal curve the
    interleave exists to expose. ``None`` when there are not two rates to compare.
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


def run_cells(
    cells: list[Cell],
    workloads: list[Workload],
    *,
    warmup: int = 3,
    measured: int = 5,
    cooldown_s: float = 30.0,
    results_dir: str,
) -> list[CellResult]:
    """Measure every cell under every workload; one :class:`CellResult` per pair.

    A visit starts the cell's runtime **once** and runs every workload under that one load,
    so the model is loaded twice per cell however many workloads there are. ``measured``
    requests are made per (cell, workload) in total, split across the visits the plan calls
    for (five becomes three then two), and every workload gets its own warmups because a long
    prompt compiles a different set of kernels than a short one does. Results are written to
    ``<results_dir>/results.jsonl`` after every visit, so a run that dies still has
    everything it had measured up to that point.

    The returned results are in first-visit order, each cell's workloads kept together in the
    order they were given. Figures are never averaged across workloads: a prefill-bound number
    blended with a decode-bound one describes no workload that was run.
    """
    if warmup < MIN_WARMUP:
        raise ValueError(
            f"warmup must be >= {MIN_WARMUP}: model load, Metal shader compilation and "
            "lazy mmap all have to land outside the measurement"
        )
    if measured < 1:
        raise ValueError("measured must be >= 1")
    if cooldown_s < 0:
        raise ValueError("cooldown_s must be >= 0")
    workloads = _workloads(workloads)
    _require_modules()

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
        "warmup": warmup,
        "measured": measured,
        "cooldown_s": cooldown_s,
    }

    results: list[CellResult] = []
    by_key: dict[tuple[str, str], CellResult] = {}
    counters: dict[str, tuple] = {}
    unmeasurable: set[str] = set()

    visits = _visits(cells, measured=measured)
    for index, (cell, quota) in enumerate(visits):
        if cell.id in unmeasurable:
            # A cell that cannot run here is not visited again, and nothing waits for it.
            continue

        cell_results = _results_for(cell, workloads, by_key, results)
        measured_before = sum(len(result.observations) for result in cell_results)
        outcome = _visit(cell_results, cell, workloads, warmup=warmup, quota=quota,
                         counters=counters)
        if outcome == "measured":
            for result in cell_results:
                _set_status(result)
        elif outcome == "skip":
            unmeasurable.add(cell.id)
        # "retry" keeps the reason the failed visit wrote, and the next visit tries again.

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
) -> list[CellResult]:
    """This cell's result per workload, created on the first visit and reused after.

    The pair is the key, so a cell's three shapes are three results rather than three
    measurements collapsed into one.
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
                warmup_observations=[],
                cold_load_s=None,
                memory={},
                runtime_version=None,
                disk_bytes=artifact_bytes(cell.artifact_dir),
            )
            by_key[(cell.id, workload.id)] = result
            results.append(result)
        cell_results.append(result)
    return cell_results


def _visits(cells: list[Cell], *, measured: int) -> list[tuple[Cell, int]]:
    """Flatten the plan into (cell, measured-requests-this-visit) pairs.

    Visits with a zero quota are dropped: starting a runtime to measure nothing costs a
    full model load for no sample.
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
    warmup: int,
    quota: int,
    counters: dict,
) -> str:
    """One visit to one cell, returning ``"measured"``, ``"retry"`` or ``"skip"``.

    The runtime is started once and every workload runs under that load, then it is stopped:
    reloading the weights per workload would triple the cost of the only expensive step here.
    ``"skip"`` means the cell cannot run here at all and no later visit will change that.
    ``"retry"`` means this visit failed for a reason that may not hold next time — a runtime
    that will not load is usually deterministic, but a port still held by a stale server is
    not — and the samples already taken, if any, stand.
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

    try:
        # The artifact directory doubles as the model-id hint; the runtime resolves it to
        # whatever it calls those weights, and that resolved name is what gets recorded.
        handle = runtime.start(cell.artifact_dir, cell.artifact_dir)
    except Exception as error:  # noqa: BLE001 - a runtime that will not load is a result
        reason = f"runtime {cell.runtime!r} did not start: {type(error).__name__}: {error}"
        for result in results:
            if result.observations:
                result.status, result.reason = "FAIL", reason
            else:
                _na(result, reason)
        return "retry"

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
                                     counter=counter)
            result.memory = _highest_peak(result.memory, memory)
    finally:
        handle.stop()

    return "measured"


def _workload_visit(
    handle, result: CellResult, workload: Workload, *, warmup: int, quota: int, counter
) -> dict:
    """One workload's requests inside a visit, sampled over that workload's own window.

    The sampler covers this workload alone. A visit that ran a 512-token decode and a
    128-token chat has two different memory peaks, and publishing the visit's peak under both
    names would report decode's footprint as chat's.
    """
    sampler = sample.Sampler(handle.pid).start()
    memory = None
    try:
        for _ in range(warmup):
            result.warmup_observations.append(
                _request(handle, workload.messages, max_tokens=workload.max_tokens,
                         counter=counter)
            )
        for _ in range(quota):
            result.observations.append(
                _request(handle, workload.messages, max_tokens=workload.max_tokens,
                         counter=counter)
            )
    finally:
        memory = sampler.stop()
    return memory


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


def _require_modules() -> None:
    missing = [
        name
        for name, module in (
            ("transport", transport),
            ("runtimes", runtimes),
            ("token_counter", token_counter),
        )
        if module is None
    ]
    if missing:
        raise MeasureError(
            "cannot measure without ohyesmlx/"
            + ", ohyesmlx/".join(f"{name}.py" for name in missing)
            + " — issues #2 and #3 provide them"
        )


def write_jsonl(results: list[CellResult], path: str | Path, *, run: dict) -> None:
    """The run's ``results.jsonl``: a header line of the pins, then one line per result.

    Line 1 is the run header — temperature, seed, warmup, measured, cooldown_s and every
    workload that was measured, each with the messages it sent and its own max_tokens (a
    single run-level cap would be a half-truth once three workloads carry three of them).
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
    return {
        "cell": asdict(result.cell),
        "workload_id": result.workload_id,
        "status": result.status,
        "reason": result.reason,
        "cold_load_s": result.cold_load_s,
        "memory": result.memory,
        "runtime_version": result.runtime_version,
        "disk_bytes": result.disk_bytes,
        "measured_count": len(result.observations),
        "warmup_count": len(result.warmup_observations),
        "drift": measured_drift(result.observations),
        "observations": [_observation_record(observation) for observation in result.observations],
        # Warmups are not samples of the measured quantity — averaging a cold-start TTFT
        # into a percentile would be a lie — but they are still raw observations, so they
        # are kept here rather than thrown away.
        "warmup_observations": [
            _observation_record(observation) for observation in result.warmup_observations
        ],
    }


def _observation_record(observation) -> dict:
    """The observation's own fields, and nothing derived from them."""
    return asdict(observation)
