# Measurement core — interface shapes

The shapes and metric formulas every measured request composes on: the SSE client, runtime lifecycle, sampling, the measurement loop, the report join, and the one definition of each metric.

## `ohyesmlx/transport.py` — issue #2

```python
@dataclass(frozen=True)
class Observation:
    """One measured request."""
    ok: bool
    error: str | None
    ttft_s: float | None            # send -> first delta of the OUTPUT stream (see below)
    last_content_s: float | None    # send -> last delta of the OUTPUT stream
    total_s: float                  # send -> stream closed
    prompt_tokens: int | None       # from usage
    completion_tokens: int | None   # from usage, content only
    reasoning_tokens: int | None    # from usage.completion_tokens_details, if present
    content_event_count: int        # deltas of the OUTPUT stream, not always the content channel
    text: str                       # CONTENT deltas only
    token_source: str               # "usage" | "local_tokenizer" | "none"
    reasoning_text: str = ""        # reasoning deltas joined; "" when the model emitted none
    cached_tokens: int | None = None  # prompt tokens the server says its prompt cache served; None if unsaid
    mtplx_stats: dict | None = None   # MTPLX's final-chunk receipt, verbatim; None on every other runtime

def chat(base_url: str, model: str, messages: list[dict], *,
         max_tokens: int, temperature: float = 0.0, seed: int | None = None,
         timeout_s: float = 600.0, api_key: str | None = None,
         token_counter: "TokenCounter | None" = None) -> Observation: ...
```

`base_url` is `http://127.0.0.1:<port>/v1`. Streaming is always on internally with
`stream_options.include_usage`; `Observation` is what the caller sees.

**The three timing and count fields describe the OUTPUT stream, whichever channel it was.**
`ttft_s`, `last_content_s` and `content_event_count` are the output stream's, and the output
stream is the content deltas in the ordinary case and the reasoning deltas when the runtime
streamed only in that channel or mirrored it into content (see below). `text` is only ever the
content channel and `reasoning_text` only ever the reasoning one, so read those three as
statements about the output stream and never as statements about `text` — they keep their
content-channel names because that is the ordinary case. `reasoning_text` is declared **last**
in the dataclass, after `token_source`, with a default: a field with a default cannot precede
one without, and that default is what lets the failure path build an `Observation` with no
reasoning to report.

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
first content delta, `last_content_s` the last, `content_event_count` how many. A runtime that
**mirrors** — one whose accumulated reasoning text is identical to its accumulated content,
meaning it streamed incrementally in the reasoning channel and then repeated the whole text
once as a single content delta — is the case where that reading is wrong: there the reasoning
deltas *are* the output stream, and all three fields are taken from them.

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
    name: str                      # "mlxlm" | "osaurus" | "omlx" | "optiq" | "vmlx" | "mtplx"
    port: int
    def start(self, artifact_dir: str, model_id: str, *,
              cache_state: str | None = None,
              kv_quant: str | None = None,
              mtp_depth: str | None = None,
              stream_experts: str | None = None,
              concurrency: int = 1) -> "Handle": ...  # see "Phase 6 plan 06-02",
                                                      # "Phase 4 study 03-05",
                                                      # "Phase 4 studies 03-06, 03-03"
                                                      # and "the concurrency cap" below
    def start_command(self, artifact_dir: str, model_id: str, *, ...,
                      concurrency: int = 1) -> tuple[str, ...]: ...
    def build_command(self, artifact_dir: str, model_id: str, *, ...,
                      concurrency: int = 1) -> tuple[tuple[str, ...], str | None]: ...
    # `concurrency` reaches all three: start -> build_command -> start_command.
    def request_seed(self, mtp_depth: str | None) -> int | None: ...       # see "the seed" below
    def cache_state_refusal(self, cache_state: str | None) -> str | None: ...
    def kv_quant_refusal(self, kv_quant: str | None) -> str | None: ...    # 03-05, below
    def mtp_depth_refusal(self, mtp_depth: str | None, artifact_dir: str) -> str | None: ...
    def stream_experts_refusal(self, stream_experts: str | None) -> str | None: ...
    def stream_experts_missing(self, stream_experts: str | None,
                               log_path: str | None) -> str | None: ...
    def mtp_depth_missing(self, mtp_depth: str | None, log_path: str | None, *,
                          observations: list | None = None,
                          artifact_dir: str | None = None) -> str | None: ...
                          # OptiQ, vMLX and MTPLX, 03-06 / v4.0. `observations` is the VISIT's
                          # measured samples and `artifact_dir` the cell's directory; the two
                          # log-reading overrides ignore both, and MTPLX's receipt gate is the
                          # one that needs them.


@dataclass
class Handle:
    pid: int
    port: int
    base_url: str                  # "http://127.0.0.1:<port>/v1"
    model_id: str                  # what THIS runtime calls the model
    version: str                   # runtime version, recorded as provenance
    cold_load_s: float             # spawn -> ready. Its own metric, never folded in.
    first_request_s: float | None  # the cold visit's FIRST warmup latency. See below.
    serving_pid: int | None        # pid to sample; None means the spawned pid is the server
    stop_command: tuple[str, ...]  # ("osaurus", "stop"), or () when SIGTERM is the stop
    scratch: str | None            # per-run tree a stop removes (oMLX's catalog and base)
    api_key: str | None            # the credential the runtime was started with
    log_path: str | None           # where this start's stdout/stderr went. See below.
    def stop(self) -> None: ...    # must not return until the port is free

RUNTIMES: dict[str, Runtime]       # keyed by name
```

**The lifecycle fields are not measurements, and vice versa.** `serving_pid` exists because a
launcher can hand the port to another process — Osaurus's does — so the pid to sample
(`Handle.memory_pid`) is not always the pid that was spawned. `stop_command` and `scratch` are
what `stop()` needs to release the port and remove the per-run tree; `api_key` is the credential
a measured request must send (`measure._request` passes it through). `first_request_s` is the
odd one: it is a field with a default of `None`, and it is
**written by the measurement loop** — `measure._visit` fills it in via
`measure._first_warmup_latency` when the cold visit's first warmup request lands, and copies it,
with `first_request_workload_id`, onto every `CellResult` of that cell. It is never passed at
construction, and a `CellResult` is where a report reads it.

`log_path` is the one field added for a *pin* rather than for the lifecycle: it is the file the
spawn's stdout and stderr were redirected into, and it is the only place a state the runtime can
silently decline is visible (see "Phase 4 studies 03-06, 03-03"). `Runtime.start` sets it from
the path it spawned into; a handle built without a spawn carries `None`, and an `on` cell that
cannot be checked is a `FAIL` rather than a pass.

`request_seed` is the one method here that decides a **request body** rather than a lifecycle: it
answers the seed a measured request carries, `None` while `runtimes.TEMPERATURE == 0`, and
`Optiq` overrides it to keep `SEED` at an MTP depth. The policy and its entire rationale are
written once at that method; `measure` asks it rather than holding a second copy (see
"`seed` is a policy, and `request_seed` is what a row sent").

### The concurrency cap follows the run

`concurrency` is the run's batch width rather than a pin: `measure.run_cells(concurrency=N)`
drives N requests at once, and `measure._visit` hands the same N to `Runtime.start`. The three
runtimes whose start command carries a batch cap put it in that cap — oMLX's
`--max-concurrent-requests`, OptiQ's `--max-concurrent` and vMLX's `--max-num-seqs` — while the
two without one ignore it (mlx-lm passes no cap; Osaurus takes no flags at all). Hard-coded to
1, the cap makes an N>1 sweep measure the harness rather than the runtime, which is what the
2026-09-27 sweep did (`results/sweep-conc-seedless` measured the cap, not their batching, at
N>1). The rule and its rationale are written once at `runtimes.Omlx.start_command`, and at
`concurrency=1` — every run measured before it — each command is **byte-identical** to the ones
recorded before the cap moved, which is what `tests/test_runtimes.py`'s `TODAY` table checks.

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
    workload_id: str               # which shape this row is: a result is one (cell, workload) pair
    status: str                    # "PASS" | "FAIL" | "N/A"
    reason: str | None
    observations: list[Observation]   # EVERY raw sample. Never truncated.
    batch_spans: list[float]       # one per measured batch; [] for a sequential cell (06-01b)
    warmup_observations: list[Observation]
    warmup_plateau: bool | None
    cold_load_s: float | None
    first_request_s: float | None
    first_request_workload_id: str | None   # which shape made it. See below.
    memory: dict                   # the sample.py result dict
    runtime_version: str | None
    disk_bytes: int | None
    lost_visit_reason: str | None = None    # a planned visit that never measured. See the short-window section.
    cold_load_after_lost_visit: bool = False
    measured_pin: int | None = None         # the run's batch pin; not written to the record
    request_seed: int | None = None         # what this cell's requests sent. See "the seed" below.
    port: int | None = None                 # 05-10b: the port the first started visit served on.

def run_cells(cells: list[Cell], workloads: list[Workload], *,
              warmup: int | str = "plateau", measured: int = 9, concurrency: int = 1,
              cache_state: str | None = None, kv_quant: str | None = None,
              mtp_depth: str | None = None, stream_experts: str | None = None,
              quick: bool = False, cooldown_s: float = 30.0,
              prompt_tokens: dict | None = None,
              results_dir: str) -> list[CellResult]: ...
# warmup/measured/concurrency: see "Phase 6 plan 06-01b"; prompt_tokens: 06-01c;
# cache_state: 06-02; kv_quant: 03-05; mtp_depth and stream_experts: 03-06 and 03-03;
# quick: 04-03a. Every one of them is a run header pin and none is a cell property.
```

A **record** carries every `CellResult` field except `measured_pin`, adds three derived ones
(`measured_count`, `warmup_count`, `drift`), and omits three keys when they are not true of the
cell: `batch_spans` (a sequential cell ran no batch and took no clock), `lost_visit_reason` (no
visit was lost) and `cold_load_after_lost_visit`. `load_run` reads those three back leniently;
`measured_pin` is never in the file at all, because the run header owns it — one copy per run,
and a result rebuilt by `load_run` carries `None`. `request_seed` is carried like any other
field, and unlike those three it is written on **every** record — the header states the run's
policy and the row states what its own cell sent, so an OptiQ-at-depth row reads `0` under a
header whose ordinary answer is `null`. `port` (05-10b) is written whenever a visit started, which
is every record since, and is absent on older ones; `load_run` reads its absence as `None`. It is
the runtime's default unless `runtimes.port_plan` moved the engine off a default held by a
non-engine. A later visit on another port is a `port_moved` stderr note, never a failure.

### `seed` is a policy, and `request_seed` is what a row sent

Every measured request pins `temperature` 0 and, **at temperature 0, no seed at all**. That is not
a reproducibility choice: greedy decoding makes a seed inert (a temperature-0 completion is
deterministic without one), and a request that carries a seed takes mlx-lm's **sequential**
serving path — `_is_batchable` is false on `args.seed is not None` (`mlx_lm/server.py:685-686`)
— and OptiQ is that same server. A seeded harness therefore never measures the `BatchGenerator`
path everyday clients use, which is the path both axes are about.
`runtimes.Runtime.request_seed` is the one definition of the rule and holds its rationale;
`measure._visit` asks it once per visit and hands the answer to every request of the visit, so
the warmup and the measured batches take the same path.

The header's `seed` is therefore the **policy for an ordinary cell** — `None` while
`runtimes.TEMPERATURE == 0` — and each record's `request_seed` is the per-row fact: what that
cell's requests actually carried. The two differ in exactly one place, an **OptiQ cell at an MTP
depth**, which keeps the seed because OptiQ installs MTP on the same sequential path
(`runtimes.Optiq.request_seed`, and docs/runtimes/optiq.md); such a row reads `0`.

Join guard 1 compares the header field (`PIN_FIELDS`), so a run measured now (`seed: None`)
refuses to join one measured before this change (`seed: 0`): the old columns were measured on
the sequential path and the new ones are not. `request_seed` is not a pin — it is a record of
what happened — and a record written before the key existed has none and **sent `0`** (its own
header says `seed: 0`), which is what `load_run` reads that absence as.

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
winners**, so a figure from a single shape is not a ranking. The default set is exactly these
three and no more; `--workloads multiturn` selects a second pinned set of ten turns (see
"Phase 4 study 03-04"), and there is no config file and no flag that invents a third.

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

**A runtime-axis table ordered by a metric that is not one quantity across runtimes prints its
values and no ordering.** The two refusals are the grid's own, applied through the same
`_uncomparable_across_runtimes`: `CROSS_RUNTIME_UNCOMPARABLE` (`peak_mb`, `cold_load_s`)
whatever the rows are, and `CHANNEL_DEPENDENT_RANKS` (`ttft_p50_s`, `prefill_tps`) where the
rows were not all timed on one channel. The rank column is empty on every row, the rows list
alphabetically by runtime (`_unpositioned` — a metric order with the numbers removed is the
same claim in another typeface), and the note above the table is the text the grid's
runtime-axis section prints, not a second wording of it. The format axis holds one runtime,
where those figures are one quantity, and orders unchanged. Added 2026-09-25; before it, a
single run's runtime-axis table numbered `peak_mb` 1 and 2 and published the sampler's page
accounting as a ranking.

**A table ordered on a first-token latency says so when its rows were driven concurrently.**
At N=1 TTFT is time-to-first-token; at N it includes the request's wait for a batch slot, which
is a real user-facing cost and a different quantity (`docs/research/2026-09-16-phase6-design.md`).
`CONCURRENCY_TTFT_SENTENCE` is printed by `render_markdown` when the rank is in
`CHANNEL_DEPENDENT_RANKS` and any row's `concurrent` is true, and by `render_sweep` on the same
rank when its runs' `concurrency` pin is above 1 — and only then: no other rank's value moves
with the queue, and a sequential run has no slot to wait for. The leaderboard reads the row
because it is handed rows and no header; `concurrent` is `bool(CellResult.batch_spans)`, the one
record of a batch of more than one request.

**Exactly one runtime may hold weights at any moment.** `run_cells` stops the current
runtime and confirms its port is free before starting the next. Two resident 20 GB models
on a 64 GB machine saturate unified memory and quietly poison every number in the run
while the run still completes and still looks plausible.

Cell order is **interleaved**, never config order — otherwise thermal drift aliases
perfectly onto runtime identity. Persist after every visit. `max_tokens` is fixed so tok/s
is never compared across different generation lengths.

**Two visits are the plan, not a guarantee.** `visit_plan` names `VISIT_ROUNDS` orderings of
the cells and `_visits` splits the run's `measured` across them — five batches then four at the
default. A visit whose quota is zero is **dropped** rather than run: starting a runtime to
measure nothing costs a full model load for no sample. At `measured=1` the second visit is the
one dropped, so no cell is visited twice, and the samples on disk are one visit's. A run that
lands fewer batches than its own pin says so in the row (`short_note`) instead of reading as a
full window; see "the lost visit and the short measured window".

## `ohyesmlx/report.py` — issue #6

```python
def summarize(results: list[CellResult], *, measured: int | None = None) -> list[dict]: ...
# one row per (cell, workload): ttft_p50_s/p90/p99, e2e_p50_s/p90/p99, reasoning_timed_note,
# itl_s, decode_tps, prefill_tps, cold_load_s, peak_mb, disk_bytes, runtime_version,
# status — plus the short-window
# fields in "the lost visit and the short measured window" below. E2E percentiles use
# returned samples' total_s, share MIN_PERCENTILE_N and percentile() with TTFT, and are not
# produced for failed requests. `concurrent` is `bool(batch_spans)`: whether the run drove
# more than one request at a time, which the queueing sentences read.

def render_markdown(rows: list[dict], *, axis: str, rank: str = DEFAULT_RANK) -> str: ...
```

**`measure.py` owns `results.jsonl`, and is the only thing that writes it.** The serializer
(`write_jsonl`, and the per-cell record it builds) and the shape it serializes (`CellResult`)
both live there; `run_cells` calls it after every **visit**, so a run that dies still has
everything it had measured up to that point on disk, and a reader never sees half a file. Why a
second writer for one artifact is unacceptable is `AGENTS.md`'s rule, "One definition of
everything" — this document names the owner and points at the rule rather than restating it.

### The raw record stays raw

```python
def write_jsonl(results: list[CellResult], path: str, *, run: dict) -> None: ...
```

Line 1 of the file is the **run header**: the pins — `temperature`, `seed`, `warmup`,
`measured`, `concurrency`, `prompt_tokens`, `cache_state`, `kv_quant`, `mtp_depth`,
`stream_experts`, `cooldown_s` — the
`workloads` the run measured, each with its own `messages` and `max_tokens` (`max_tokens` is a
workload field, never a run-level pin), and the `harness` block (`version`, `source_sha256`).
Every line after it is one (cell, workload) pair, and each carries `request_seed`, the seed that
pair's requests actually sent. A header written before a pin existed simply
lacks that key — `load_run` returns a header as the dict it is and callers `.get` what they
need, so an absent key reads as the absence it was. `seed` is the header's own reading of that:
it is the **policy** an ordinary cell sends (see "`seed` is a policy" above), not a seed this
run sent.

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

