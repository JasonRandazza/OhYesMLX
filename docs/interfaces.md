# Module interfaces

Pinned so modules can be built concurrently without inventing mismatched shapes.
**These signatures are the contract.** If one is wrong, say so in the ticket and stop —
do not quietly change it, because three other modules are being written against it.

All types are plain dataclasses or dicts. Stdlib only.

## `ohyesmlx/transport.py` — issue #2

```python
@dataclass(frozen=True)
class Observation:
    """One measured request."""
    ok: bool
    error: str | None
    ttft_s: float | None            # send -> first delta of the OUTPUT stream (see below)
    last_content_s: float | None    # send -> final content delta
    total_s: float                  # send -> stream closed
    prompt_tokens: int | None       # from usage
    completion_tokens: int | None   # from usage, content only
    reasoning_tokens: int | None    # from usage.completion_tokens_details, if present
    content_event_count: int        # deltas of the OUTPUT stream, not always the content channel
    text: str                       # CONTENT deltas only
    reasoning_text: str             # reasoning deltas joined; "" when the model emitted none
    token_source: str               # "usage" | "local_tokenizer" | "none"

def chat(base_url: str, model: str, messages: list[dict], *,
         max_tokens: int, temperature: float = 0.0, seed: int | None = None,
         timeout_s: float = 600.0, api_key: str | None = None,
         token_counter: "TokenCounter | None" = None) -> Observation: ...
```

`base_url` is `http://127.0.0.1:<port>/v1`. Streaming is always on internally with
`stream_options.include_usage`; `Observation` is what the caller sees.

**`api_key` must be wired at every call site.** oMLX refuses an unauthenticated
`/v1/chat/completions` with HTTP 401 and `Runtime.api_key()` already supplies the key the
runtime was started with. A measured run that never sends it measures nothing.

**Which channel is the output stream.** There are two exceptions, not one: a **mirrored**
runtime (reasoning identical to content) and a **reasoning-only** runtime (content empty,
reasoning present). In both, the reasoning deltas are the output stream and supply `ttft_s`,
`last_content_s` and `content_event_count`. mlx-lm 0.31.3 and vMLX 1.6.59 are reasoning-only on
a thinking model: before this was handled, all 24 of their grid rows failed with "no
content-delta timing". A response with neither channel still raises `empty_content`.

Normally it is the content channel: `ttft_s` is the
first content delta, `last_content_s` the last, `content_event_count` how many. The exception
is a runtime that **mirrors** — one whose accumulated reasoning text is identical to its
accumulated content, meaning it streamed incrementally in the reasoning channel and then
repeated the whole text once as a single content delta. There the reasoning deltas *are* the
output stream, and all three fields are taken from them.

Measured — oMLX 0.6.4, one request: 15 reasoning deltas spanning 0.685 s to 2.352 s, against
one content delta at 2.352 s. Timing the content channel reported a TTFT of 5.499 s for a
runtime whose real TTFT is 0.685 s, and left the decode window as 1.66e-07 s of float noise.
The same mirror test drives the token-accounting dedupe; there is one detector, not two.

The count moves with the timing deliberately. `report.py` omits every rate below two deltas,
so a corrected timestamp with a stale count of 1 would be computed and then discarded.

**Reasoning deltas are captured, never dropped.** A reasoning model can spend an entire
response in the reasoning channel and emit no content at all — and that reasoning text can
itself be token salad. `reasoning_text` is what lets the coherence gate see it. mlx-lm
0.31.3 spells the field `delta.reasoning`; other servers spell it `delta.reasoning_content`.
Both are read.

**`token_counter` must be wired at every call site.** In the predecessor project the exact
token path existed, was never passed by any production caller, and
`median_decode_tokens_per_second` was therefore `None` in 100% of runs on disk.

```python
class TokenCounter:            # ohyesmlx/token_counter.py
    def __init__(self, model_dir: str): ...
    def count(self, text: str) -> int: ...
```

## `ohyesmlx/runtimes.py` — issue #3

```python
@dataclass(frozen=True)
class Runtime:
    name: str                      # "mlxlm" | "osaurus" | "omlx" | "optiq"
    port: int
    def start(self, artifact_dir: str, model_id: str) -> "Handle": ...

@dataclass
class Handle:
    pid: int
    port: int
    base_url: str                  # "http://127.0.0.1:<port>/v1"
    model_id: str                  # what THIS runtime calls the model
    version: str                   # runtime version, recorded as provenance
    cold_load_s: float             # spawn -> ready. Its own metric, never folded in.
    first_request_s: float | None  # the cold visit's FIRST warmup latency. See below.
    def stop(self) -> None: ...    # must not return until the port is free

RUNTIMES: dict[str, Runtime]       # keyed by name
```

**Readiness is decided by the runtime's log, not by the port.** Observed on mlx-lm 0.31.3:
on a model-load failure the server still binds its port and logs `Starting httpd` after the
load thread has died, so a client POST connects and then hangs forever. Poll `/v1/models`
for the model id *and* watch the log for a load error.

Each runtime names identical weights differently (`mlx-community/X`, `mlx-community__X`,
`omlx/X`, `<artifact_dir>`, `<artifact_dir>:no-think`). `model_id` on the `Handle` is the
resolved one.

## `ohyesmlx/sample.py` — issue #4, **merged, do not change**

```python
sampler = Sampler(pid, interval_s=1.0).start()
result = sampler.stop()
# {"peak_mb": float, "samples": [{"t": float, "mb": float}], "n_samples": int,
#  "duration_s": float, "memory_split": {...}, "power": {...},
#  "gpu_wired_limit": {...}, "error": str | None}
```

## `ohyesmlx/measure.py` — issue #5

```python
@dataclass(frozen=True)
class Cell:
    id: str                        # "<format>__<runtime>"
    runtime: str                   # key into RUNTIMES
    artifact_dir: str
    label: str                     # human name for the format

@dataclass
class CellResult:
    cell: Cell
    status: str                    # "PASS" | "FAIL" | "N/A"
    reason: str | None
    observations: list[Observation]   # EVERY raw sample. Never truncated.
    cold_load_s: float | None
    first_request_s: float | None
    first_request_workload_id: str | None   # which shape made it. See below.
    memory: dict                   # the sample.py result dict
    runtime_version: str | None
    disk_bytes: int | None

def run_cells(cells: list[Cell], workloads: list[Workload], *,
              warmup: int = 3, measured: int = 5,
              max_tokens: int = 256, cooldown_s: float = 30.0,
              results_dir: str) -> list[CellResult]: ...
```

### `cold_load_s` alone cannot be compared across runtimes

`cold_load_s` is spawn until `await_ready` returns. For a runtime that loads weights at
startup that is a load time. For one that loads them **lazily on the first request** it is a
time-to-listening, and the load is charged to request #1 instead.

`first_request_s` is the latency of the **first warmup request of the cold visit** — the same
visit that sets `cold_load_s`, and `None` on every later visit. It is already made and already
timed; only the record discarded it.

Measured — oMLX 0.6.4 reports ~2.2-3.1 s ready, then spends 3.08-3.85 s inside request #1
against ~0.42 s for requests 2 and 3, on three different artifacts. mlx-lm, mlx-optiq and vMLX
differ by 0.04-0.10 s between first and later requests. Ranking on `cold_load_s` alone named
oMLX the fastest loader when it is the second slowest to a first useful token.

**Any cross-runtime load comparison uses `cold_load_s + first_request_s`.** A large gap between
`first_request_s` and the measured requests is a load the runtime deferred, and the report says
so rather than leaving a reader to assume warm-up noise.

That gap is only a gap when both sides come from the same workload. A visit runs its shapes in
order, so request #1 belongs to exactly one of them, and `first_request_workload_id` records
which. `first_request_s` is the visit's fact and every row of the cell prints it; the
deferred-load **note** is made only on the row that owns it. Read against another shape's
requests the comparison is between two workloads: on the recorded corpus the note fired on 27
rows, and 13 of those were rows that did not make the request -- a 3.6-5.0 s chat request read
against prefill's shorter median. Attributed, 14 remain, every one the shape that paid.

Excluding a JIT warm-up from the measured figures is correct — it is an artifact of
benchmarking. Excluding the weight load is not: the user pays it on every cold start.

### Workloads — the three shapes, pinned

```python
@dataclass(frozen=True)
class Workload:
    id: str                  # "chat" | "prefill" | "decode" — the column key in every report
    messages: list[dict]
    max_tokens: int
```

One workload measures one corner. Prefill-heavy and decode-heavy work can have **different
winners**, so a figure from a single shape is not a ranking. v1 pins exactly three and no
more; a richer suite is v2's.

| id | prompt | max_tokens | what it exposes |
|---|---|---|---|
| `chat` | short | 128 | latency and per-request overhead |
| `prefill` | long | 64 | prompt-processing throughput |
| `decode` | short | 512 | sustained generation and memory growth |

**Every cell runs every workload**, and a cell's result is per `(cell, workload)`. Figures are
never averaged across workloads — averaging a prefill-bound number with a decode-bound one
produces a figure describing no workload that was run. `max_tokens` moves to the workload; it
is no longer a `run_cells` argument.

### Floors and ordering — no blended score

A cell is ranked only after it clears every floor, and floors are pass/fail, never weighted:

1. **Coherence** — the gate in `coherence.py`. Already enforced.
2. **Every published metric present** — already enforced by `_set_status`.
3. **Fits** — `peak_mb` did not exceed available unified memory.

`report.render_markdown(rows, *, axis, rank="decode_tps")` — `rank` is keyword-only with a
default, so a call that predates it still works. One table per workload, each ranked
independently and numbered from 1.

Ranking then uses **one named metric**, chosen by the caller and printed in the table header.
It is never a weighted blend of speed and memory: those weights have no objective value, and a
single number would encode an arbitrary trade-off as though it were measured, hiding exactly
what this project exists to show. The metric card carries every measured value behind the
ranking, so the ordering can always be checked against the numbers that produced it.

**Exactly one runtime may hold weights at any moment.** `run_cells` stops the current
runtime and confirms its port is free before starting the next. Two resident 20 GB models
on a 64 GB machine saturate unified memory and quietly poison every number in the run
while the run still completes and still looks plausible.

Cell order is **interleaved**, never config order — otherwise thermal drift aliases
perfectly onto runtime identity. Persist after every cell. `max_tokens` is fixed so tok/s
is never compared across different generation lengths.

## `ohyesmlx/report.py` — issue #6

```python
def summarize(results: list[CellResult]) -> list[dict]: ...
# one row per cell: ttft_p50_s/p90/p99, itl_s, decode_tps, prefill_tps,
# cold_load_s, peak_mb, disk_bytes, runtime_version, status

def render_markdown(rows: list[dict], *, axis: str) -> str: ...      # axis: "runtime" | "format"
```

**`measure.py` owns `results.jsonl`, and is the only thing that writes it.** The
serializer (`write_jsonl`, and the per-cell record it builds) lives in `measure.py`
alongside `CellResult`, which owns the shape. `run_cells` calls it after every cell so a
run that dies still has its completed cells on disk; `report.py` imports it if it needs
it, and never defines a second one.

Two writers for one artifact is the exact pattern this project exists to avoid.

### The raw record stays raw

```python
def write_jsonl(results: list[CellResult], path: str, *, run: dict) -> None: ...
```

Line 1 of the file is the **run header**: the pins (`temperature`, `seed`, `max_tokens`,
`warmup`, `measured`, `cooldown_s`, `workload`). Every line after it is one cell.

A stored observation carries **only the `Observation` fields** — never `decode_tps`,
`prefill_tps`, or `itl_s`. Those are derived, and `report.summarize` computes them from the
raw fields on read. Storing a derived value beside the raw values it comes from creates two
sources of truth for one metric, and when they disagree there is no way to say which is
right. That disagreement is not hypothetical: it is how the predecessor reported 243.5 and
57.2 tok/s for the same cell on consecutive runs.

`CellResult` carries `warmup_observations: list[Observation]` alongside `observations`.
Warmups are discarded from the summary, never from the record — they are how a cold-start
anomaly is spotted after the fact.

`axis` is required, and `render_markdown` emits the caveat naming what that axis cannot
claim. A table that does not say which variable it held constant is not a result.

## Metric formulas — one definition each, no forks

```
decode_tps  = completion_tokens / (last_content_s - ttft_s)
prefill_tps = prompt_tokens / ttft_s
itl_s       = (last_content_s - ttft_s) / max(1, completion_tokens - 1)

# DOMAIN: all three require content_event_count >= 2.
```

All three formulas are only defined for a stream that delivered **at least two content
deltas**. With one delta the first content delta *is* the whole response, so `ttft_s` and
`last_content_s` are the same instant: `decode_tps` divides by float noise, `itl_s` collapses
to zero, and `prefill_tps` divides the prompt by a span that covers the entire generation.
Outside that domain all three are `None` and the row says why — they are never computed and
clamped, and no epsilon is added to the window.

`ttft_s` itself stays a real number in that case, but it measures **time-to-completion, not
time-to-first-token**, and the row must label it. It is not comparable against a streaming
runtime's first-token latency.

Measured — oMLX 0.6.4 accepts `"stream": true` and returns the whole completion in one
content delta. Before this domain was pinned the harness published 1,532,954,517 tok/s, an
ITL of 0.0000, and a `PASS`:

```
events=1  ctok=256  ttft=5.3532  last_content=5.3532  window=1.66e-07
```

`completion_tokens` comes from `token_source` in priority order. Two ways to be exact,
one way to derive:

1. **`usage`** — the runtime reports the reasoning count itself, so content is the
   remainder.
2. **`usage`** — the runtime emitted no reasoning channel at all, so there is no split to
   derive and `completion_tokens` *is* the content count. The local tokenizer is not
   consulted.
3. **`local_tokenizer`** — the stream mixes both and the runtime reports one total, so the
   counter splits it, and the two parts must sum to that total **exactly**.

Never mix sources within one comparison, and never soften case 3 with a tolerance.

Case 2 is not a shortcut. Re-tokenizing decoded text is not the inverse of generation: a
response truncated at `max_tokens` re-tokenizes across different boundaries and lands a
token or two away. Measured — oMLX 0.6.4 generated 256, the local counter re-read the same
text as 257, and five coherent responses published no tok/s at all. The reconciliation in
case 3 validates a *derived split*; where nothing is derived there is nothing to validate,
and demanding the round-trip makes the metric unreachable rather than more honest.

---

## Phase 5 — the joined grid

Phase 3 measured the grid one column at a time: five invocations of `ohyesmlx run --study
format`, five run directories, each holding one runtime's twelve rows. The grid exists only
as five files that nobody joins. Phase 5 joins them.

The reading is the one Phase 3 pinned: a **column** (one runtime, many formats) is the
format axis, a **row** (one format, many runtimes) is the runtime axis, and the best cell
across the whole grid is a *recommendation*, never an attribution. Nothing in this phase
re-measures anything.

### `ohyesmlx/measure.py` — reading a run back

```python
def load_run(path) -> tuple[dict, list[CellResult]]: ...
# path: a run directory or its results.jsonl.
# Returns (run_header, results) — line 1 of the file, then one CellResult per line after it.
```

The exact inverse of `write_results`/`_record`. `Cell(**record["cell"])` and
`Observation(**obs)` round-trip by construction, which is why the record was written with
`asdict` and no derived fields inside those two objects.

The three **derived** fields in a record — `measured_count`, `warmup_count`, `drift` — are
*not* read back onto the object. They are recomputed from the observations that carry them.
A loader that read them would let a hand-edited file publish a drift that its own samples do
not support. Their presence in the file is for a reader with `jq`, not for this function.

The round-trip is testable and must be tested: `_record(load_run(p)[1][i])` equals the i-th
record on disk, byte for byte, for a real grid run dir.

### `ohyesmlx/report.py` — the grid

```python
def render_grid(runs, *, rank: str = DEFAULT_RANK) -> str: ...
# runs: list[tuple[str, dict, list[dict]]] — (run label, run header, summarize()'d rows)
```

One grid per workload, never averaged across them — the same rule that governs the
leaderboard. Rows are format labels, columns are runtime names, and each entry is the
`rank` metric for that cell.

**Four entry states, and they must not render alike:**

| state | renders | means |
|---|---|---|
| measured, PASS | the number | a result |
| PASS, no value for *this* metric | `no value` | the cell cleared every floor; the metric has no domain on this stream |
| measured, not PASS | `FAIL` | the cell ran and did not clear a floor |
| never measured | `—` | that combination does not exist |

The second state exists because `_number` renders `None` as the same em dash as the
fourth. A cell that produced language, cleared the floors, and streamed its whole
completion in one content delta has no decode rate — `order_rows` already ranks such a row
last with a note rather than excluding it, and the grid must not be the one place that
distinction collapses back into "does not exist".

The matrix is ragged by nature — no runtime loads JANG and the other formats both — so
`—` is the ordinary case, and a reader who cannot tell it from `FAIL` is reading a
different grid. A drift-annotated cell (`DRIFT_ANNOTATION_PCT`) carries its marker into the
entry beside the number, because a grid that hides what the leaderboard shows is a
downgrade of the same data.

### The join guards

Joining five separately-invoked runs is the one place this project can vary two things
without noticing, so the join refuses rather than renders when:

1. **The pins disagree.** Every run header field — `temperature`, `seed`, `warmup`,
   `measured`, `cooldown_s` — and every workload's `messages` and `max_tokens` must be
   identical across all runs. Columns that answered different prompts are not one grid.
2. **A cell appears twice.** The same `(label, runtime, workload_id)` from two run
   directories is ambiguous; name both directories and refuse. There is no "latest wins"
   rule, because which run is newer is not which run is right.
3. **One format label points at two artifacts.** Same name, different bytes, across
   columns — the runtime-axis row guard `_held_constant` already makes within a table.
4. **One runtime appears at two versions.** Across columns two *different* runtimes at
   different versions is the grid working as intended; the *same* runtime at 0.25.3 in one
   directory and 0.25.4 in another is the held-constant variable moving, and Osaurus
   measured 1.15x across exactly that step.

Guard 4 compares `runtime_version` as an exact string. mlx-optiq reports
`"mlx-optiq, version 0.5.6"` rather than a bare `0.5.6` — uniform within its column today,
so the guard does not misfire, but a runtime that rephrases its `--version` output would
read as a version change. Normalise here if it ever does.

Every guard names both run directories in its message. A grid that refuses must say which
two files disagreed and on what.

### Provenance

The rendered grid states, above the tables: each column's run directory, runtime and
version, and the pins all columns share. That block is the evidence the join was legal, and
it is what makes the grid recomputable by someone holding only the five `results.jsonl`
files.

### `ohyesmlx/cli.py`

```
ohyesmlx grid <run-dir> [<run-dir> ...] [--rank decode_tps] [--out FILE]
```

Explicit directories, never a glob over `results/grid/` — that directory holds thirteen
run dirs from three sessions, and a grid assembled by wildcard would silently join columns
that never belonged together. `--out` defaults to stdout only.
