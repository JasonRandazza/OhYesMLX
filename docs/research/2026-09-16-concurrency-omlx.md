# Phase 6 plan 06-01b — the first concurrency sweep: oMLX does not batch

Date: 2026-09-16, measured 09:09–10:42Z. Run directories (gitignored):
`results/sweep-conc/20260916T090909Z-format` (N=1), `…T091619Z` (N=2), `…T092911Z` (N=4),
`…T095351Z` (N=8). One cell: `oq4__omlx`, Qwen3.5-4B-oQ4 on oMLX 0.6.4. All 12 rows PASS.

Four runs differing in exactly one header pin — `concurrency` — which is what Phase 6's design
means by "a sweep is a pin, not an axis".

## The result

| N | per-request decode tok/s | **aggregate tok/s** | requests | median batch span | TTFT p50 |
|---|---|---|---|---|---|
| 1 | 74.2 | **70.4** | 9 | — | 0.418 s |
| 2 | 73.8 | **71.4** | 18 | 14.30 s | 3.935 s |
| 4 | 73.3 | **72.2** | 36 | 28.38 s | 10.929 s |
| 8 | 73.0 | **72.5** | 72 | 56.45 s | 25.077 s |

(decode workload; chat and prefill show the same shape — chat aggregate 66.0 / 66.5 / 66.8 /
66.4, prefill 18.8 / 19.1 / 19.2 / 19.3.)

**Aggregate throughput is flat and the batch span scales linearly with N.** 14.30 → 28.38 →
56.45 is 2× per doubling, to within a percent. TTFT p50 does the same: 3.9 → 10.9 → 25.1.

That is serialization, not batching. A runtime that batched would show the opposite pair:
per-request decode rate falling as N rises, because N requests share one GPU, and aggregate
throughput climbing, because the GPU is doing more total work per unit time. Here per-request
rate barely moves (74.2 → 73.0, under 2%) and aggregate barely moves (70.4 → 72.5). Each
request is being served essentially alone; the others wait.

**For a reader choosing a server: on oMLX, concurrency buys nothing and costs latency in
proportion to it.** Eight simultaneous users get the same total tokens per second as one, and
each waits eight times as long for a first token. The right move on oMLX is to queue work
yourself rather than send it in parallel and think you are getting throughput.

## Why the warmup rule had to change first

This sweep is also why plan 06-01a existed. Warmup at N>1 settles on aggregate throughput
rather than per-request decode rate, because the per-request series at N=8 swings ±11% with no
trend — which of eight simultaneous requests is served first is not a property of how warm the
model is. Under the old series every concurrent cell would have run to the warmup cap and
reported "did not settle" about a cell with nothing left to warm.

The numbers above are the vindication: per-request rate is flat to within 2% across a 3-doubling
of N, so a rule reading it would have been reading noise, while aggregate — the quantity that
actually answers the question — is stable enough to settle on.

## A caveat this phase inherits, and must not publish without

`measured_drift` reads **per-request decode rates**. At N=1 a positive drift means the cell was
still warming when its window closed, which is what its docstring says and what plan 05-02 was
built on. At N>1 that reading is no longer safe: the warmup window closed on *aggregate*
throughput, so the per-request series can still be trending when measurement starts, and
queueing variance rides on top of it.

The function is unchanged and correct about what it computes. What changes is the diagnosis a
reader may draw from it. **At N>1, positive drift means "per-request rate was still moving",
not "this cell was under-warmed."** Any sweep table that prints a drift column needs that
sentence next to it.

## What this does not say

- **It is one runtime.** oMLX serializes; mlx-lm, mlx-optiq, vMLX and Osaurus are untested at
  concurrency and may well batch. "Which of these actually batches" is the most useful question
  Phase 6 can answer for someone choosing a server, and this answers one fifth of it.
- **It is one cell and one model.** Qwen3.5-4B-oQ4. Whether a larger model or a different
  format changes oMLX's behaviour is unmeasured.
- **Nothing about a batching runtime's quality.** A server that batches trades per-request
  latency for total throughput, and which of those a reader wants is theirs to decide. This
  measures which trade each server is actually making, not which is better.

---

# All five, at N=8: none of them batch

Measured 2026-09-16 10:44–13:44Z. Run directories (gitignored):
`results/sweep-conc8/` holds Osaurus, mlx-optiq, vMLX and mlx-lm at N=8;
`results/sweep-conc/20260916T095351Z-format` is oMLX's. One cell each,
`oq4` = Qwen3.5-4B-oQ4, the one format all five runtimes serve. All 60 rows PASS.

The N=1 reference is each runtime's `oq4` row from the dense grid measured earlier the same
night — identical pins, identical workloads, `measured 9` sequential requests. The runs are
compared rather than joined: the grid's headers predate the `concurrency` pin, so join guard 1
would refuse them, correctly. This is a research comparison and says so.

| runtime | N=1 per-req | N=1 agg | N=8 per-req | **N=8 agg** | **gain** |
|---|---|---|---|---|---|
| mlx-lm | 67.0 | 64.2 | 77.1 | 73.9 | **1.15×** |
| oMLX | 75.5 | 71.2 | 73.0 | 72.5 | **1.02×** |
| mlx-optiq | 76.2 | 72.1 | 77.1 | 73.0 | **1.01×** |
| vMLX | 73.3 | 71.1 | 73.9 | 72.1 | **1.01×** |
| Osaurus | 68.7 | 66.4 | 69.3 | 67.0 | **1.01×** |

(decode workload, 512 tokens. The chat workload gives the same picture: 1.09, 0.99, 0.99,
1.00, 0.99.)

**Not one of the five gains throughput from eight simultaneous requests.** Four are flat to
within 2%. Every batch span is ~8× a single request's, and TTFT grows in proportion.

## mlx-lm's 1.15× is not batching, and the per-request column is how you can tell

mlx-lm is the only one showing a gain worth a second look, and the second look kills it.
**Its per-request decode rate went *up*, 67.0 → 77.1.**

That is impossible under real batching. Eight requests sharing one GPU must each decode more
slowly; batching trades exactly that per-request slowdown for total throughput. A runtime whose
per-request rate *rises* while its aggregate rises is not batching — it is a runtime that
happened to run faster in this measurement than in the one it is being compared against.

mlx-lm is also the column that needed the longest warmup and whose drift was the whole subject
of plan 05-02, so run-to-run variation is exactly where it would show up. Reading 1.15× as
"mlx-lm batches a little" would be the same error this project has caught four other times: a
number that moved for a reason nobody checked.

## What this means for someone choosing a server

On any of these five, **concurrency is pure latency cost.** Eight simultaneous users get the
total throughput of one and each waits roughly eight times as long for a first token. The
useful move is to queue work yourself and send it sequentially; sending it in parallel buys
nothing and makes every user's experience worse.

That is a genuinely useful thing to know and it is not what the MLX ecosystem's framing
suggests — "server" implies concurrent serving, and all five of these expose an
OpenAI-compatible endpoint that accepts parallel requests without complaint. They accept them
and then serve them one at a time.

## What this does not say

- **One cell, one model, one concurrency level.** Qwen3.5-4B-oQ4 at N=8. Whether any of them
  batches at N=2 with a smaller model, or under a build flag not used here, is unmeasured. The
  oMLX ladder (N=1/2/4/8) is the only place the *shape* was checked, and there it was linear.
- **Nothing about correctness under load.** Every row PASSed the coherence gate at N=8, which
  says the outputs were language, not that they were identical to the sequential ones.
- **Nothing about a batching server being better.** Batching trades per-request latency for
  throughput. This measures which trade each server actually makes — and the answer is that
  none of them makes it.
- **The drift caveat above applies to every row here.** At N>1 a positive `measured_drift`
  means per-request rate was still moving, not that the cell was under-warmed.
