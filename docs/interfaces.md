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
    def start(self, artifact_dir: str, model_id: str, *,
              cache_state: str | None = None) -> "Handle": ...    # see "Phase 6 plan 06-02"
    def cache_state_refusal(self, cache_state: str | None) -> str | None: ...

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
#  "duration_s": float, "memory_split": {...},
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
    warmup_observations: list[Observation]
    batch_spans: list[float]       # one per measured batch; [] for a sequential cell (06-01b)
    warmup_plateau: bool | None
    lost_visit_reason: str | None  # a planned visit that never measured. See the short-window section.
    cold_load_after_lost_visit: bool
    measured_pin: int | None       # the run's batch pin; not written to the record
    cold_load_s: float | None
    first_request_s: float | None
    first_request_workload_id: str | None   # which shape made it. See below.
    memory: dict                   # the sample.py result dict
    runtime_version: str | None
    disk_bytes: int | None

def run_cells(cells: list[Cell], workloads: list[Workload], *,
              warmup: int | str = "plateau", measured: int = 9, concurrency: int = 1,
              cache_state: str | None = None,
              cooldown_s: float = 30.0, prompt_tokens: dict | None = None,
              results_dir: str) -> list[CellResult]: ...
# warmup/measured/concurrency: see "Phase 6 plan 06-01b"; prompt_tokens: 06-01c;
# cache_state: 06-02. Every one of them is a run header pin and none is a cell property.
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

A third floor, **fits** (`peak_mb` within available unified memory), was specified here and
removed 2026-09-23: nothing in the package reads total unified memory, so it only ever printed
"not evaluated". Re-add it with a real source, not as a placeholder.

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
def summarize(results: list[CellResult], *, measured: int | None = None) -> list[dict]: ...
# one row per cell: ttft_p50_s/p90/p99, e2e_p50_s/p90/p99, reasoning_timed_note,
# itl_s, decode_tps, prefill_tps, cold_load_s, peak_mb, disk_bytes, runtime_version,
# status — plus the short-window
# fields in "the lost visit and the short measured window" below. E2E percentiles use
# returned samples' total_s, share MIN_PERCENTILE_N and percentile() with TTFT, and are not
# produced for failed requests.

def render_markdown(rows: list[dict], *, axis: str, rank: str = DEFAULT_RANK) -> str: ...
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
5. **A joined row has an unknown runtime version.** A shared check refuses any
   `runtime_version` beginning with `unknown` in `render_grid` or `render_sweep`, naming the
   run directory, cell and value; a join cannot establish that the runtime stayed constant
   when its version is not stated. Single-run leaderboards render these rows unchanged.

Guard 4 compares `runtime_version` as an exact string. mlx-optiq reports
`"mlx-optiq, version 0.5.6"` rather than a bare `0.5.6` — uniform within its column today,
so the guard does not misfire, but a runtime that rephrases its `--version` output would
read as a version change. Normalise here if it ever does.

Every guard names the offending run directory or both disagreeing directories in its message.
A grid or sweep that refuses must say which
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

---

## Phase 5 plan 05-02 — warmup is measured, not pinned

The joined grid's runtime axis ordered the five runtimes by how long each takes to warm up
and called it how fast each one serves. mlx-lm is last in 11 of 14 orderings on the
published median and 1st/3rd/3rd/4th on the late-window median — see
`docs/research/2026-09-16-phase5-joined-grid.md`. One warmup budget applied to five
runtimes is the cause: three requests leaves mlx-lm still climbing and the other four
settled.

Raising the global budget is the wrong fix. It pays mlx-lm's cost on four runtimes that do
not need it and lengthens a 67-minute grid for nothing, and it replaces one guessed constant
with a larger guessed constant. **Warmup stops being a pin and becomes a measured property
of the cell.**

### The plateau rule

A workload's warmup window keeps issuing requests until its decode rate stops moving:

```python
MIN_WARMUP = 3            # the floor a caller pinning a fixed budget may not go below
WARMUP_WINDOW = 5         # rates per window; the rule compares the medians of two
WARMUP_CAP = 20           # the window closes here whether or not it settled
WARMUP_PLATEAU_PCT = 3.0  # the step between two window medians
```

The cell is warm when the median of the last `WARMUP_WINDOW` rates is within
`WARMUP_PLATEAU_PCT` of the median of the `WARMUP_WINDOW` before them. It is a **trend test
and never a variance test** — see "Noise is not unfinished warmup" below. A rate comes from `decode_tps`, the same function every published figure uses; a
warmup observation that carries none cannot settle the window, and the cap is what ends it.

**One window is not enough, measured.** oMLX serving Qwen3.5-4B-oQ4, fourteen identical chat
requests in a flat loop with no harness structure around them, decode tok/s:

```
103.5  102.8  103.3 | 70.8  73.4  75.7  73.6  75.2  75.3  74.6  72.0  73.8  72.9  73.3
```

The machine serves the first three requests from a boost state and then steps down ~29% to
the rate it holds — request 1 spends 1.24 s generating and request 4 spends 1.81 s for the
same 128 tokens, so this is the runtime slowing down and not the stream re-chunking. The
boost phase is **flat**: 0.5% spread. A single-window rule calls that warm at request three,
at a rate 40% above what the cell can sustain, and certifies exactly the three requests the
fixed budget already used while claiming to have verified something. Live, before and after:

| rule | warm declared at | first measured request |
|---|---|---|
| one window | 103.3 | 75.7 (−27%) |
| two windows | 77.0 | 76.1 (−1%) |

So the floor is `2 * WARMUP_WINDOW`, not `MIN_WARMUP`.

**Noise is not unfinished warmup, also measured.** The first cell of the aborted 03:30Z
column — mlx-lm serving stock-4bit, the prefill workload's warmup rates:

```
70.3 74.7 72.5 77.1 71.9 78.6 77.5 73.6 70.2 70.9 75.2 64.8 72.5 71.3 76.8 75.4
```

No trend at all. That cell is warm from request one and simply swings ±8% per request, and a
rule requiring neighbouring rates to agree within 3% can never be satisfied by it: it ran to
the cap, spent sixteen requests learning nothing, and reported "did not settle" about a cell
with nothing left to warm. Per-request noise is a property of the workload — a 128-token chat
varies far more than a 512-token decode — and reading it as unfinished warmup conflates two
different things, which is the conflation this rule exists to undo.

So the test compares **window medians only**, never the spread inside a window, and the window
is five rather than three because a median of three of those rates is itself noise. Live, on
the cell that had capped twice:

| workload | warmups | settled | warm rate | first measured |
|---|---|---|---|---|
| chat | 12 | yes | 77.5 | 78.0 |
| prefill | 10 | yes | 85.1 | 78.2 |
| decode | 11 | yes | 67.0 | 66.8 |

The floor of ten also caught a third thing: under the old floor of six, the decode workload
settled while it was still climbing (measured 64.7 → 66.7 across its window).

`3.0%` sits between the two populations the grid measured — four runtimes settle their whole
*measured* window inside `+2.6 / −0.0 / +0.5 / +1.0%`, and mlx-lm moves `+17.0%` across its.
A plateau tolerance below that spread would chase noise; one above it would call mlx-lm warm
while it was still climbing.

The cap is not a fallback that quietly substitutes for the rule. A window that hit it did
**not** settle, and that is a finding about the cell:

```python
warmup_plateau: bool | None   # new CellResult field, new record field
```

`True` when every warmup window on this row reached the plateau, `False` when any hit the
cap, `None` when no warmup ran. A capped cell that rendered identically to a settled one
would be this project's own recurring defect — a quantity recorded and unread — committed
one more time.

`warmup_count` already records how many requests it took, so the budget each runtime needed
becomes a published number rather than a constant in a source file.

`load_run` reads `warmup_plateau` **leniently** — the only field it does. A record written
before the rule existed was measured under a fixed budget, so the rule did not run on it and
`None` is exactly true of those rows rather than a default standing in for something unknown.
That is what separates it from `first_request_workload_id`, whose absence is refused: a
default there would claim the cold visit made no request, which is false about rows whose
visit did. A default is honest when the absence is the fact, and the five 2026-09-16 columns
the Phase 5 write-up published stay readable by the tool that published them.

### The pins change, so every column re-runs

The run header's `warmup` becomes the rule rather than a count:

```python
{"mode": "plateau", "window": 5, "floor": 10, "cap": 20, "plateau_pct": 3.0}
```

and `measured` goes `5 → 9`. At 5, `measured_drift` compares a median of two against a
median of two and throws the middle sample away, which is why the drift threshold cannot be
tightened and why a single row's magnitude is untrustworthy. At 9 it compares medians of
four.

Join guard 1 compares both fields, so **a column measured under the new pins cannot join one
measured under the old**. This is not a mlx-lm re-run; it is a full grid re-run, and the
five 2026-09-16 directories become history the moment it starts.

`run_cells(warmup=...)` still accepts an `int` for a fixed budget — a quick run pinning three
requests is still a legal thing to ask for, and it is what most tests want. `"plateau"` is
the default and is what the grid runs.

---

## Phase 6 — a sweep is a pin, not an axis

Full reasoning in `docs/research/2026-09-16-phase6-design.md`. What is settled and pinned:

`--study` names which of a **cell's** two variables a selection may vary, and a cell is
`(format, runtime)`. Concurrency, prompt length and cache state are none of those — they are
properties of how the run drove the cells, which is what the run header holds. So each sweep
is N runs differing in exactly one header pin, joined afterwards, the same shape the grid
already is.

```python
def render_sweep(runs, *, varying: str, rank: str = DEFAULT_RANK) -> str: ...
# varying: the one header field these runs are allowed to disagree about.
```

Every other field is compared as join guard 1 compares it. `varying` must actually vary: a
sweep whose runs all pin the same value is not a sweep, and two runs sharing a value of the
swept pin is the duplicate case guard 2 already refuses. The swept pin is named in the title
and the provenance block — a table that does not say what varied between its columns is the
thing this project exists not to publish.

**At concurrency N > 1 the ordering metric is aggregate throughput, not `decode_tps`.** N
requests share one GPU, so per-request decode rate falls as N rises by construction; a reader
who sees it drop from 75 to 30 between N=1 and N=8 and concludes the runtime got worse has
read a throughput result as a latency result. Per-request rate stays recorded, TTFT becomes a
queueing measurement whose percentiles matter more than its median, and `_aggregate_tps` —
which already exists — is what the sweep is ordered by.

**The warmup rule does not carry over to concurrency — measured, plan 06-01a.** oMLX, N=8,
workload `chat`, 16 batches:

```
per-request median   65.3 - 81.0   NEVER settles in 16 batches
aggregate tok/s      62.1 - 68.3   settles at batch 12
```

Per-request decode rate at N>1 carries queueing variance of about ±11% with no trend, which a
3% trend test can never satisfy — the same shape as the noisy prefill workload at N=1, and the
same wrong answer: it would run every concurrent cell to the cap and report "did not settle"
about a cell with nothing left to warm.

So **a concurrency sweep warms on aggregate throughput**, which is also the quantity it
publishes. `_settled` takes a second form for it: the same two-window median comparison at the
same tolerance, over `_aggregate_tps` per batch rather than per-request rates. The rule's shape
is unchanged; only the series it reads changes.

A sequential run (N=1) keeps warming on per-request decode rate. One batch of one is not the
same measurement as one request, and nothing about the existing grid changes.

Prompt lengths are **token** counts verified against the tokenizer that will serve them, with
the achieved count recorded beside the target. A prompt that exceeds a runtime's context is
`—` with the refusal recorded, never a `FAIL` and never silently truncated.

---

## Phase 6 plan 06-01b — the concurrency pin

```python
def run_cells(cells, workloads, *, warmup="plateau", measured=9, concurrency=1,
              cooldown_s=30.0, results_dir): ...
```

**`measured` counts batches, not requests.** At `concurrency=1` a batch is one request and
nothing about the existing grid changes — that equivalence is what keeps every number measured
so far comparable. At `concurrency=8`, `measured=9` means nine batches of eight, so the cell
records 72 observations and nine batch spans.

**A batch is N requests issued together under one clock.** The span is measured around the
whole batch, because summing per-request spans would count the overlap N times and aggregate
throughput is the quantity a concurrency sweep publishes. Threads, not processes:
`concurrent.futures.ThreadPoolExecutor` around the existing `transport.chat`, which is blocked
on an SSE stream. **The stream reader is not re-implemented** — one definition of TTFT, one of
the decode window, one `Observation`.

New on `CellResult` and the record:

```python
batch_spans: list[float]   # wall-clock seconds per measured batch; one entry per batch
```

`aggregate_tps` for a batch is its completion tokens over its span. Read back leniently like
`warmup_plateau`: a record written before concurrency existed has no batch spans and `[]` is
exactly true of it, since there were no batches. A sequential record's spans are *not*
reconstructed from per-request totals — a gap between two sequential requests is not part of
either one.

**Warmup at concurrency > 1 reads aggregate throughput.** Same rule, same constants, different
series: `_settled` over per-batch aggregate rather than per-request decode rates. Measured in
plan 06-01a — at N=8 the per-request series swings ±11% with no trend and never settles, while
aggregate settles at batch 12. At `concurrency=1` the per-request series is used exactly as
today.

**The header pin** gains `concurrency`, so join guard 1 compares it and a sweep declares it via
`render_sweep(varying="concurrency")`.

**What does not change:** the floors, the coherence gate, `measured_drift`, `decode_tps`,
`prefill_tps`, `itl_s`, and every per-request figure. A concurrent cell's requests are judged
one at a time exactly as a sequential cell's are — a fast cell emitting garbage is still a
failed cell, at any concurrency.

---

## Phase 6 plan 06-01c — the prompt-length pin

Findings behind it, from the runtimes' shipped source: `docs/research/2026-09-16-prompt-length-context-limits.md`.

```python
# cli.py
LONGTEXT = Path(__file__).with_name("longtext.md")   # frozen; sha256 3ed2c160…a8a3
# Phase 6 walked 128, 1024, 4096, 16384 and 32768; --prompt-tokens takes any N.

def sized_prompt(counter, target: int) -> tuple[str, int]: ...
# -> (prompt text, achieved token count). achieved <= target, and achieved is what
#    counter.count(text) returns for the exact text returned.
```

```
ohyesmlx run --study format --cells <cell> --prompt-tokens 4096
```

**The text.** `SIZED_HEAD + cut + SIZED_TAIL`, where the source is the MS-7 excerpt body out of
`PREFILL_PROMPT` (between its BEGIN and END markers) followed by `longtext.md`, and `cut` is the
longest prefix of that source ending at a **whitespace boundary** whose whole prompt counts
`<= target`. Found by bisection over whitespace positions using only `counter.count`, so a test
can drive it with a counter as simple as `len(text.split())`. The head asks the model to read
the document; the tail asks, in one sentence, what the document is about — a question any cut
can answer, which the MS-7 question is not once the cut lands before rule 3. No repetition,
ever: a target whose prompt would need more text than the source holds is a `ValueError`, as
is a target too small to fit the head and tail.

`longtext.md` is the 2026-09-14 and 2026-09-15 research documents concatenated in name order,
frozen as a package file (60,701 tokens by the Qwen3.5-4B tokenizer). It is never regenerated
from `docs/`: those documents may be edited, and a prompt that changed under a pin is a
different prompt. Chosen by Jason, 2026-09-16, over a downloaded book and authored text.

**The workload.** With `--prompt-tokens N` the run measures **one** workload, `prefill`, whose
message is `sized_prompt(counter, N)` and whose cap is 64 — the existing prefill cap. `chat` and
`decode` are not run: they would be byte-identical across every run of the sweep and cost a
plateau warmup each. Without the flag the three pinned workloads run exactly as today.

**The counter is the serving tokenizer.** `TokenCounter(cell.artifact_dir)` for each distinct
artifact the cells name. If two artifacts' counters disagree about the achieved count of the
prompt, the run is refused before a runtime starts: one run pins one prompt length.

**The header pin.**

```python
"prompt_tokens": {"target": 4096, "achieved": 4093} | None   # None: the three pinned workloads
```

`run_cells(..., prompt_tokens: dict | None = None, ...)` writes it verbatim; `measure` does not
compute it. `load_run` needs nothing: a header is a dict, and `.get` of an absent key is `None`,
which is exactly true of every run before this pin.

**Join guard 1 compares both sweep pins.** `PIN_FIELDS` gains `concurrency` and
`prompt_tokens`. `concurrency` is compared with an absent value read as `1` — every run written
before the pin existed issued requests one at a time, so `1` is the fact and not a default
standing in for something unknown. This closes a defect: 06-01b's header pin was never added to
`PIN_FIELDS`, so `ohyesmlx grid` would have joined an N=8 run into an N=1 grid without a word.

**Refusals are not built yet, on purpose.** The source says no runtime refuses 32k on
Qwen3.5-4B: mlx-lm has no check, OptiQ's cap is now `off`, oMLX's discovered limit is 262,144,
vMLX's memory estimate lands far above it. Osaurus is unreadable and gets a live probe first. A
`REFUSED` status is built only if a probe shows a refusal; until then an HTTP 400/413 at a long
prompt reports as the `FAIL` it currently is, and the sweep is not published with one in it.

---

## Phase 6 — the lost visit and the short measured window (found by 06-01c's sweep)

The prompt sweep's Osaurus 128 cell recorded **4 measured requests against a run pinning 9**, on
a row that was marked `PASS` with no note. Two visits are planned per cell and its quota splits
5/4; visit 1's `runtime.start()` raised, visit 2 measured its quota of four, and `_set_status`
rewrote the row from the samples that survived — erasing both the failure and the fact that half
the window was missing. A reader of that table saw a full `PASS` row with the count column
reading `4/4`.

Three additions, all of them annotations and none of them floors — the same rule drift follows:
a window that was short is a result, and dropping it would delete the only row that says so.

```python
CellResult.lost_visit_reason: str | None   # the failed visit's reason, kept where _set_status
                                           # cannot overwrite it. None = no visit was lost.
CellResult.cold_load_after_lost_visit: bool  # the start that recorded cold_load_s came after a
                                             # lost visit, so it is a warm-page-cache start and
                                           # not the cell's cold one.
CellResult.measured_pin: int | None        # the run's batch pin, stamped on every row by
                                           # run_cells. NOT written to the record: the header
                                           # owns it there, one copy per run, and a result
                                           # rebuilt by load_run carries None.
```

`lost_visit_reason` and `cold_load_after_lost_visit` are written to the record **only when they
are true**, so a cell whose every visit measured keeps the record it always had, byte for byte;
both are read back leniently on the same reasoning — every record on disk was written before the
fields existed and no visit of theirs was lost, so the absence *is* the fact.

```python
def summarize(results: list[CellResult], *, measured: int | None = None) -> list[dict]: ...
```

*measured* is the run's batch pin, passed in by a caller joining run directories because a
result rebuilt by `load_run` does not carry it. A row that landed fewer batches than the pin —
counted off `batch_spans` above concurrency 1 and off the observations at 1, because the pin
counts batches — carries `short_note` and the row reads `(n=K of N)` beside its number in the
grid and the sweep. No pin at all is **no check**, never a pin of zero: that is the honest
reading of an older record and of a caller that never knew about the pin, and it is the one
place a run short of its window can go unremarked.

The lost visit rides in the metric card as `lost_visit_note` ("a visit to this cell was lost
before the one that measured: …; the samples on this row are the surviving visit's"), beside the
status whose reason it is not, and the cold load carries `cold_load_note` naming which start the
figure came from. Neither is a floor and neither moves a published number.

## Phase 6 plan 06-02 — the cache-state pin

The cold/warm split, per the Phase 6 design ("Cold versus warm KV"): the same prompt answered
with a runtime's prefix/KV reuse off and on, the difference between the two being what the cache
is worth. It is a **pin**, not an axis and not a cell property — one run drives every cell in it
into one state — so it is joined exactly as the other two sweeps are.

```
ohyesmlx run ... --cache-state {off,on}
ohyesmlx sweep <off-run-dir> <on-run-dir> --varying cache_state --rank ttft_p50_s
```

**The header pin.**

```python
"cache_state": "off" | "on" | None     # None: the pin was not taken
```

`PIN_FIELDS` gains `cache_state` and `ABSENT_PINS` reads an absent one as `None` — which is the
one part of this pin that must not be got wrong. `None` is not a third state and it is not a
synonym for `"off"`: every run measured before the pin existed ran each runtime's own default,
and those defaults were not uniform — the Osaurus grid columns ran with its prefix cache ON, and
the same 2026-09-15 columns ran with oMLX's `--no-cache` and vMLX's two disable flags pinned off.
Reading the absence as `off` would fold two different cache states into one column and call them
a comparison. Without the flag every start command is **byte-identical to today**; that is
checked against recorded literals for all five runtimes, not re-derived.

**The mechanism, per runtime.** `off` disables prefix/KV reuse and `on` enables it, through each
runtime's own start command:

| runtime | `off` | `on` | where it comes from |
|---|---|---|---|
| mlx-lm 0.31.3 | `--prompt-cache-size 0` | `--prompt-cache-size 10` | `mlx_lm/server.py:1872` — "Maximum number of distinct KV caches to hold in the prompt cache", default 10. At 0 the cache holds nothing: every insert evicts the entry it just added (`models/cache.py:1696-1737`), so the `fetch_nearest_cache` at `server.py:753` always answers `None` and every request prefills its prompt whole. |
| mlx-optiq 0.5.6 | the same two flags | the same two flags | `optiq serve` is a fork of the same server: unknown options are collected (`optiq/cli.py:2332` `ignore_unknown_options`, `:2571` `ctx.args`) and handed to the bundled `mlx_lm.server`'s own argparse (`:3030`), and the bundle is the same mlx-lm 0.31.3. |
| oMLX 0.6.4 | `--no-cache` (already in the command) | omit `--no-cache` | `omlx/cli.py:1139-1143` — "Disable oMLX paged SSD cache". Absent it, `CacheSettings.enabled` is True (`omlx/settings.py:331`) and the SSD directory resolves to `<base-path>/cache` (`settings.py:387-399`) — for a run, the per-run scratch the runtime is handed and that `stop()` removes. |
| vMLX 1.6.59 | `--disable-prefix-cache` | `--enable-prefix-cache` | `vmlx_engine/cli.py:3658-3670` — `--enable-prefix-cache` defaults True, `--disable-prefix-cache` is the explicit off. `--disable-block-disk-cache` is in **both** states: left unset, the engine turns the SSD L2 on by itself whenever continuous batching and prefix caching are active (`cli.py:661-701`) and persists it under `~/.cache/vmlx-engine/block-cache/<model_hash>`, so the two states would differ in two things and an `on` cell could serve another run's prefix. |
| Osaurus 0.25.x | refused unless the host is already off | refused unless the host is already on | No flag exists in either direction. The state is `cache.prefix.enabled` in `~/.osaurus/config/server-runtime.json`, which the harness does **not** edit — the sweep script does, with a byte-exact backup and restore. |

**A state a runtime cannot be driven into is `N/A` with the reason**, through the same path an
unknown runtime and an unavailable tokenizer take: the runtime is asked
(`Runtime.cache_state_refusal`) *before* it is started, and `_visit` returns `"skip"` so no later
visit retries it. Osaurus is the whole of the mechanism: `_visit` asks it whether the live
`cache.prefix.enabled` matches the requested state (`True` for `on`, `False` for `off`), and a
disagreement — or a settings file that cannot be read, `MISSING`/`UNREADABLE` included — records
the refusal instead of measuring. **A restart is not a way to turn a cache on**: a process that
just started has an empty cache whatever the settings say, so restarting to reach `on` would
label an off cell as an on one, and a cell measured in a state it did not hold is not a result.
The reason names the setting and the value that disagreed, because the fix is a script's and not
this runtime's.

**`render_sweep` gains `varying="cache_state"`.** `concurrency`, `prompt_tokens` and
`cache_state` are the whole of `SWEEP_PINS`. The one relaxation stays the prompt-length pin's
alone: a cache sweep's columns are meant to answer the **same** prompt twice, once cold and once
warm, so every workload's `messages` are compared like any other field and two runs that sent
different prompts are refused. The columns render **`off` before `on`** — the cold column is the
baseline the warm one is read against — from `SWEEP_VALUES`, an explicit order rather than the
accident of how two words sort. `off` vs `on` in a *grid* is refused by guard 1 like any other
pin difference, and so is an absent pin against a pinned `off`.

**What the sweep is read on.** TTFT, not a rate: a prefix cache that hits collapses prefill, so
the reading is `ttft_p50_s`. A cell whose runtime never hits the cache measures the same number
in both columns, and that is a finding — "the cache was worth nothing here" — not a failure.
The 2026-09-16 probe found exactly that for an oQ4 prefill on four of the five runtimes, and the
flat-TTFT check (warmup #1 against the measured median) is what tells a hit from a miss rather
than assuming one.

**The runner** is `scripts/run_sweep_cache.sh`, modelled on `scripts/run_sweep_prompt.sh`: the
`oq4` cell, five runtimes, `--prompt-tokens 4096`, each runtime `off` then `on`, into
`results/sweep-cache/`. For Osaurus it snapshots `server-runtime.json` **and** `server.json`
byte-exact, flips `cache.prefix.enabled` and `cache.blockDisk.enabled` false for `off`, sets
`modelIdleResidencyPolicy.seconds` to 900 in **both** states (the host's 30 unloads the model
inside the 30 s cooldown), re-records the baseline so the harness's drift guard passes, and
restores both files with `git checkout -- config/osaurus-settings-baseline.json` at the end and
on INT/TERM/HUP. Restoration is verified with `cmp` against the copies rather than with the drift
guard, because the host's 30 legitimately differs from the committed baseline's 900 and the
guard would report Jason's own machine as drift forever.

