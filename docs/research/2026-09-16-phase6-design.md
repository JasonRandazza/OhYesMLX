# Phase 6 — sweeps: the design, before any of it is built

Date: 2026-09-16. Written while the 05-02 grid re-run was in flight, so nothing here is
measured yet. It is the design and the reasoning behind it; the numbers come later.

Phase 6 is the roadmap's last v1 phase: concurrency 1/2/4/8/16/32, prompt lengths
128/1k/4k/16k/32k, and cold versus warm KV cache with the caches cleared between. Its goal
is to find where continuous batching and prefix caching actually pay off.

## The framing: a sweep is a pin, not an axis

The instinct is to add `--study concurrency` beside `--study runtime` and `--study format`.
That is wrong, and the reason matters.

`--study` names which of a **cell's** two variables a selection is allowed to vary. A cell is
`(format, runtime)` — `Cell.id` is literally `<format>__<runtime>` — and `_check_axis`
refuses a selection that varies both. Concurrency is not a property of a cell. Neither is
prompt length, and neither is whether the KV cache was cleared. They are properties of **how
the run drove the cells**, which is exactly what the run header already holds: `temperature`,
`seed`, `warmup`, `measured`, `cooldown_s`.

So a sweep is N runs, each pinning a different value of one header field, joined afterwards —
the same shape the grid already has. The grid is five runs that differ in nothing but which
cells they name; a concurrency sweep is six runs that differ in nothing but one pin. Phase 5
already built the machinery for joining runs and for refusing to join runs that disagree
about something they should not.

This also keeps the single-variable rule enforceable at the only place it can be enforced.
If concurrency were a cell property, one `--cells` selection could name
`oq4__omlx` at concurrency 1 and `stock4bit__mlxlm` at concurrency 8, and no check in the
CLI would catch a selection that varied three things at once.

## What the join guard has to learn

Phase 5's guard 1 refuses a join when any header field differs. A sweep deliberately differs
in exactly one, so the join has to be told which:

```python
def render_sweep(runs, *, varying: str, rank: str = DEFAULT_RANK) -> str: ...
# varying: the one header field these runs are allowed to disagree about.
```

Every other field is compared exactly as guard 1 compares it today, and `varying` must
actually vary — a "sweep" whose runs all pin the same value is not a sweep, and rendering it
as one would put a label on a comparison that was never made. Two runs sharing a value of the
swept pin is the duplicate-cell case guard 2 already refuses.

The rendered output states the swept pin in its title and its provenance block, because a
table of numbers that does not say what varied between its columns is the thing this project
exists not to publish.

## Concurrency: what the metrics mean when N > 1

This is the part that cannot be bolted on, and the reason 06-01 is a design task before it is
a coding task.

Today every metric is per-request and the requests are sequential. At concurrency N they are
not, and three of the published figures change meaning:

- **`decode_tps` per request falls as N rises, by construction.** N requests share one GPU,
  so each one decodes more slowly. A reader who sees the decode rate drop from 75 to 30
  between N=1 and N=8 and concludes the runtime got worse has read a throughput result as a
  latency result. Per-request decode rate stays recorded — it is what each user experiences —
  but it is **not** the ordering metric for a concurrency sweep.
- **Aggregate throughput is the ordering metric.** It already exists: `_aggregate_tps` sums
  completion tokens over the wall-clock span of the measured window. At N=1 it is close to
  the per-request rate; at N=8 it is the number that says whether batching paid.
- **TTFT becomes a queueing measurement.** At N=1 it is time-to-first-token. At N=32 it
  includes however long the request waited for a slot, which is a real user-facing cost and a
  completely different quantity. The percentiles matter far more here than the median.

**The warmup rule needs re-examination at concurrency, and must not be assumed to carry
over.** `_settled` compares medians of per-request decode rates. At N>1 those rates carry
queueing variance on top of the runtime's own, and the noise floor that made a 3-rate window
useless at N=1 (see `docs/interfaces.md`, "Noise is not unfinished warmup") will be worse.
The likely answer is that a concurrency sweep warms on **aggregate** throughput rather than
per-request rate, since that is the quantity it publishes — but that is a hypothesis, and the
first thing 06-01 should do is measure the warmup behaviour at N=8 before pinning a rule.

**What has to be built:** `transport.chat` issues one request and returns one `Observation`.
A concurrency driver issues N and returns N, with one shared clock so the aggregate span is
the real one. The laziest correct shape is a `concurrent.futures.ThreadPoolExecutor` around
the existing `chat` — the transport is I/O-bound on an SSE stream, threads are enough, and it
adds no dependency. What it must not do is re-implement the stream reader: one definition of
TTFT, one of the decode window.

## Prompt length: the prompts have to be generated, and counted in tokens

128/1k/4k/16k/32k are **token** counts, not character counts. The tokenizer is already
available — `token_counter.TokenCounter` reads the artifact's `tokenizer.json` — so each
prompt is generated and then verified against the tokenizer that will serve it, and the run
header records the achieved token count beside the target. A prompt that lands at 3,847
tokens when 4,096 was asked for is fine; a prompt whose length nobody checked is not.

The text itself must be deterministic and must not be repetitive filler: a prompt of one
sentence repeated 400 times compresses in the KV cache differently than real text, and at
that point the sweep measures the filler. The existing `PREFILL_PROMPT` in `cli.py` is real
prose of a known shape and is the right seed to extend from, cut at a token boundary.

**Two cells will refuse, and that is a result.** Qwen3.5-4B's context window and each
runtime's default context flag both cap what can be sent. A 32k prompt against a runtime
started with a 8k context is not a slow cell, it is a cell that cannot exist, and it belongs
in the grid as `—` with the refusal recorded — never as a `FAIL` and never as a truncated
prompt silently measured at a different length than the one in the header. Whether each
runtime's context can be raised from its start command is a per-runtime question 06-01 has to
answer before it measures anything.

## Cold versus warm KV: per-runtime, and honestly N/A where it cannot be done

The measurement is: the same prompt twice, with the prefix cache cleared between, against the
same prompt twice with it warm. The difference is what the cache is worth. Phase 3 already
measured one instance of this by accident — Osaurus's prefill was **8.3× faster** because it
was a cache lookup, which is the finding that makes this phase worth running.

Clearing it is a different operation in every runtime:

- **Osaurus** cannot do it from any command line. Only
  `~/.osaurus/config/server-runtime.json`, keys `cache.prefix.enabled` and
  `cache.blockDisk.enabled`. Changing them trips the settings-drift guard, which refuses to
  run and names them — correct behaviour, and the procedure is: back up, change, re-record
  with `osaurus_settings.write_baseline()`, run, restore from
  `~/.osaurus/config/server-runtime.json.ohyesmlx-backup`, re-record, and **verify the drift
  reads NONE again before anything else runs**.
- **The other four** are start-command flags or a restart. A restart is always a valid
  cache-clear and is the fallback that needs no per-runtime knowledge: a process that just
  started has no prefix cache. It costs a model load per measurement, which is why it is the
  fallback and not the method.
- **Where a runtime offers neither**, the cell is `N/A` with the reason recorded. A cache
  measurement faked by changing the prompt slightly is measuring prompt sensitivity, not
  caching.

The cold/warm split is therefore **not** a sweep over a pin in the same way as the other two.
It is a pair of runs — cache on, cache off — and the pin that varies is a new header field
naming the cache state. Same join machinery, same `varying` argument.

## The order this gets built in

1. **06-01a, measurement first**: at N=8 on one cell, does warmup settle on per-request rate
   or does it need aggregate throughput? Answer before pinning a rule. Nothing is published
   from this run; it is a probe.
2. **06-01b**: the concurrency driver, the `concurrency` pin, `render_sweep(varying=...)`,
   and the aggregate-throughput ordering. Then the 1/2/4/8/16/32 sweep on one cell.
3. **06-01c**: prompt-length generation with token verification, the context-limit refusals,
   then the 128/1k/4k/16k/32k sweep.
4. **06-02**: the cache-state pin, the per-runtime clear procedure, and the cold/warm split.

Each step is a run that can be joined against its siblings and against nothing else, which is
the property the whole project is built to keep.

## What this design refuses

- **No blended "efficiency score"** across concurrency and latency. Weighting throughput
  against tail latency has no objective answer and a single number would encode an arbitrary
  trade-off as if it were measured. Same rule as the floors.
- **No averaging across prompt lengths or concurrency levels.** A 32k prefill blended with a
  128-token chat describes no workload anybody runs, exactly as the three workloads are never
  averaged today.
- **No self-reported throughput.** oMLX reports 15,286 tok/s from a `generation_duration` of
  0.0; at concurrency the temptation to trust a server's own batch counters will be stronger
  and the answer is the same one.

---

## Plan 06-01a, answered: a concurrency sweep warms on aggregate throughput

Measured 2026-09-16 08:47Z, `scripts/probe_concurrency_warmup.py omlx 8 16`. oMLX serving
Qwen3.5-4B-oQ4, workload `chat`, sixteen batches of eight concurrent requests, all 8/8 coming
back every batch.

| batch | per-request median | aggregate tok/s | span s |
|---|---|---|---|
| 1 | 80.2 | 62.3 | 16.45 |
| 2–6 | 71.2 → 65.3 | 68.3 → 65.1 | ~15.5 |
| 7–13 | 72.3, 80.7, 74.4, 75.1, 71.0, 81.0, 78.8 | 63.9 → 62.6 | ~16.2 |
| 14–16 | 65.7, 66.3, 68.3 | 65.2, 66.2, 65.9 | ~15.6 |

Under the existing two-window 3% rule: **per-request median never settles in sixteen batches;
aggregate throughput settles at batch 12.**

The per-request series swings 65.3–81.0 with no trend — queueing variance, since which of
eight simultaneous requests gets served first is not a property of how warm the model is. That
is the prefill-noise problem again, in a new place: a variance-sensitive test reads a noisy
quantity as an unwarmed one. The aggregate series sits in a 62–68 band and settles.

**So the rule keeps its shape and changes its series.** Two windows of five, medians compared
at 3%, floor 10, cap 20 — over `_aggregate_tps` per batch instead of per-request decode rates.
Sequential runs are untouched: one batch of one is not the same measurement as one request, and
nothing in the existing grid changes.

### A signal to test, not a finding

Eight concurrent requests take ~16 s, and each one's decode rate (65–81) is close to what the
same runtime delivers at N=1 (~88 on this workload). If oMLX were batching, per-request rate
should fall sharply while aggregate rose; instead aggregate (≈64) sits near per-request and the
span scales with N. That is what serialization looks like.

It is **one runtime at one concurrency on one workload**, measured by a probe that publishes
nothing, so it is recorded as the first thing plan 06-01b should look for and not as a result.
If it holds across runtimes, "which of these actually batches" is the most useful question
Phase 6 can answer for a reader choosing a server.
