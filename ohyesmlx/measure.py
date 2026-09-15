"""The measurement loop: cells in, raw observations out.

One cell is one (format, runtime) pair. A visit to a cell starts its runtime, warms it up,
measures a fixed number of requests, samples memory for the life of the visit, stops the
runtime, and persists. This module never speaks HTTP (``ohyesmlx/transport.py`` does) and
never spawns a server (``ohyesmlx/runtimes.py`` does).

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

* **Compare different generation lengths.** ``max_tokens`` is one value for every request
  in the run, so decode tok/s is never a ratio between a model that stopped at 40 tokens
  and one that ran to the cap.

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
# It is the only signal measure has that a response produced no output at all, and it is
# what separates a model that spent its budget thinking from a stream that broke.
EMPTY_CONTENT_ERROR = "chat stream produced no content"

# The still-thinking cell's own reason, never an incoherence verdict: reasoning is not
# content, so there is no output to judge and no figure to publish.
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


@dataclass
class CellResult:
    """Everything one cell produced, raw observations included."""

    cell: Cell
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
    workload: dict,
    *,
    warmup: int = 3,
    measured: int = 5,
    max_tokens: int = 256,
    cooldown_s: float = 30.0,
    results_dir: str,
) -> list[CellResult]:
    """Measure every cell and return one :class:`CellResult` per cell, in first-visit order.

    ``measured`` requests are made per cell in total, split across the visits the plan
    calls for (five becomes three then two). Warmups are re-run on every visit because
    every visit is a fresh process. Results are written to
    ``<results_dir>/results.jsonl`` after every visit, so a run that dies still has
    everything it had measured up to that point.
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
    messages = _workload_messages(workload)
    _require_modules()

    results_path = Path(results_dir) / RESULTS_FILENAME
    results_path.parent.mkdir(parents=True, exist_ok=True)
    run = {
        "workload": {"id": workload.get("id"), "messages": messages},
        "temperature": TEMPERATURE,
        "seed": SEED,
        "max_tokens": max_tokens,
        "warmup": warmup,
        "measured": measured,
        "cooldown_s": cooldown_s,
    }

    results: list[CellResult] = []
    by_id: dict[str, CellResult] = {}
    counters: dict[str, tuple] = {}
    unmeasurable: set[str] = set()

    visits = _visits(cells, measured=measured)
    for index, (cell, quota) in enumerate(visits):
        if cell.id in unmeasurable:
            # A cell that cannot run here is not visited again, and nothing waits for it.
            continue

        result = by_id.get(cell.id)
        if result is None:
            result = CellResult(
                cell=cell,
                status="N/A",
                reason=None,
                observations=[],
                warmup_observations=[],
                cold_load_s=None,
                memory={},
                runtime_version=None,
                disk_bytes=artifact_bytes(cell.artifact_dir),
            )
            by_id[cell.id] = result
            results.append(result)

        measured_before = len(result.observations)
        outcome = _visit(result, cell, messages, warmup=warmup, quota=quota,
                         max_tokens=max_tokens, counters=counters)
        if outcome == "measured":
            _set_status(result)
        elif outcome == "skip":
            unmeasurable.add(cell.id)
        # "retry" keeps the reason the failed visit wrote, and the next visit tries again.

        write_jsonl(results, results_path, run=run)
        # A cooldown after a visit that started no runtime and took no sample is 30
        # seconds spent cooling nothing.
        if len(result.observations) > measured_before and index < len(visits) - 1:
            _sleep(cooldown_s)

    return results


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
    result: CellResult,
    cell: Cell,
    messages: list[dict],
    *,
    warmup: int,
    quota: int,
    max_tokens: int,
    counters: dict,
) -> str:
    """One visit to one cell, returning ``"measured"``, ``"retry"`` or ``"skip"``.

    ``"skip"`` means the cell cannot run here at all and no later visit will change that.
    ``"retry"`` means this visit failed for a reason that may not hold next time — a
    runtime that will not load is usually deterministic, but a port still held by a stale
    server is not — and the samples already taken, if any, stand.
    """
    runtime = runtimes.RUNTIMES.get(cell.runtime)
    if runtime is None:
        _na(result, f"unknown runtime {cell.runtime!r}; known runtimes: {sorted(runtimes.RUNTIMES)}")
        return "skip"

    counter, counter_error = _token_counter(cell, counters)
    if counter is None:
        _na(result, f"token counter unavailable for {cell.artifact_dir}: {counter_error}")
        return "skip"

    try:
        # The artifact directory doubles as the model-id hint; the runtime resolves it to
        # whatever it calls those weights, and that resolved name is what gets recorded.
        handle = runtime.start(cell.artifact_dir, cell.artifact_dir)
    except Exception as error:  # noqa: BLE001 - a runtime that will not load is a result
        reason = f"runtime {cell.runtime!r} did not start: {type(error).__name__}: {error}"
        if result.observations:
            result.status, result.reason = "FAIL", reason
        else:
            _na(result, reason)
        return "retry"

    if result.cold_load_s is None:
        # The first visit's load is the cold one; a later visit starts from a warm page
        # cache. Its provenance is recorded for the same reason.
        result.cold_load_s = handle.cold_load_s
        result.runtime_version = handle.version

    sampler = sample.Sampler(handle.pid).start()
    memory = None
    try:
        for _ in range(warmup):
            result.warmup_observations.append(
                _request(handle, messages, max_tokens=max_tokens, counter=counter)
            )
        for _ in range(quota):
            result.observations.append(
                _request(handle, messages, max_tokens=max_tokens, counter=counter)
            )
    finally:
        try:
            memory = sampler.stop()
        finally:
            handle.stop()

    result.memory = _highest_peak(result.memory, memory)
    return "measured"


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
    the offending sample included — stay on the record, so the reason can be read against
    the text that earned it.
    """
    if not result.observations:
        # Nothing measured, so there is no verdict to give: the N/A or FAIL reason the
        # failed visit wrote stands. Only the next visit can move this.
        return

    failures = [
        observation
        for observation in result.observations
        if not observation.ok and not _still_thinking(observation)
    ]
    if failures:
        result.status = "FAIL"
        result.reason = (
            f"{len(failures)} of {len(result.observations)} measured requests failed; "
            f"first: {failures[0].error}"
        )
        return

    if all(_still_thinking(observation) for observation in result.observations):
        # Every measured response went to reasoning and none of it to content. No output is
        # not bad output, so this cell gets its own reason and never an incoherence verdict.
        result.status, result.reason = "FAIL", STILL_THINKING
        return

    missing = next(
        (reason for observation in result.observations
         if (reason := _missing_metric(observation)) is not None),
        None,
    )
    if missing is not None:
        result.status, result.reason = "FAIL", missing
        return

    result.reason = _incoherent(result.observations)
    result.status = "FAIL" if result.reason else "PASS"


def _still_thinking(observation) -> bool:
    """A response that produced no content at all: the budget went to reasoning.

    Reasoning is not content, so there is nothing here to judge and nothing to publish. The
    transport reports this as its empty-content failure — the stream closed without a single
    content delta — and a response that came back blank says the same thing.
    """
    if observation.text.strip():
        return False
    return observation.ok or observation.error == EMPTY_CONTENT_ERROR


def _incoherent(observations) -> str | None:
    """``"incoherent output: <first failing reason>"``, or ``None`` when the cell is language.

    The measured responses *are* the sample: this asks the question the gate exists for
    without making a request of its own, and it pins no expected answer, because an
    arbitrary workload declares none.

    Only responses that came back with text are judged. A response that failed is a
    transport failure that :func:`_set_status` already reports, and a response with no
    content is not a wrong answer — no output is not bad output. Majority rule, taken over
    the responses that could be judged rather than over the requests that were made: a cell
    does not survive the gate by having most of its requests die.
    """
    judged = 0
    failures = 0
    first: str | None = None
    for observation in observations:
        if not observation.ok or not observation.text.strip():
            continue
        judged += 1
        passed, reason = coherence.is_coherent(observation.text)
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


def _workload_messages(workload: dict) -> list[dict]:
    messages = workload.get("messages") if isinstance(workload, dict) else None
    if not isinstance(messages, list) or not messages:
        raise ValueError("workload must be a dict with a non-empty 'messages' list")
    return [dict(message) for message in messages]


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
    """The run's ``results.jsonl``: a header line of the pins, then one line per cell.

    Line 1 is the run header — temperature, seed, max_tokens, warmup, measured,
    cooldown_s and the workload every cell in the file was measured under. Every line
    after it is one cell. Rewritten whole and atomically after every visit, so a run
    that dies still has everything it measured and no reader sees half a file.
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
