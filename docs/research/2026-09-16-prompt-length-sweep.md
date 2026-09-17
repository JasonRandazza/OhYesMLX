# 06-01c: the prompt-length sweep, measured — 128 to 32k on five runtimes, oQ4

Date: 2026-09-16. Ran 13:00:11–19:14:48 local as 25 runs, one per (runtime, length), joined
afterwards. One variable moved: the run header pin `prompt_tokens`. Everything else is held
constant by the join guard, field by field.

The question 06-01c exists to answer is the one the context probe raised and could not settle:
**what does a prompt's length cost each runtime's first token, and does any of them serve a
repeated long prompt out of a cache instead of prefilling it.** The probe sent 16k and 32k
twice each, on a quiet machine, and said what a single request costs. This is the sweep: 17–49
requests per cell, a plateau warmup ahead of every measured window, and the whole matrix at
five lengths.

## What ran, and what the sweep can claim

`scripts/run_sweep_prompt.sh` walks five runtimes — mlx-lm 0.31.3, oMLX 0.6.4, mlx-optiq
0.5.6, vMLX 1.6.59, Osaurus 0.25.4 — at 128 / 1024 / 4096 / 16384 / 32768 target tokens, one
cell each: `oq4__<runtime>`, all five serving the same artifact
(`RepublicOfKorokke--Qwen3.5-4B-oQ4`, 3,160,559,814 bytes on disk), one workload, `prefill`,
`max_tokens` 64. The order alternates between runtimes so a length does not always land at the
same point in a runtime's session.

Pins every run shares: temperature `0.0`, seed `0`, warmup the plateau rule (two windows of 5
rates, a 3% step between their medians, floor 10, cap 20), `measured` 9 batches, `concurrency`
1, `cooldown_s` 30.0. The prompt is the longest cut of one committed source — the MS-7 excerpt
body followed by `ohyesmlx/longtext.md` (60,701 tokens, sha256 `3ed2c160…a8a3`) — that fits the
target with its head and tail, cut at a whitespace boundary and never repeated to reach a
length. `achieved` is the serving tokenizer's count of the text actually sent and is recorded
beside the target: 128, 1024, 4096, 16384 and 32765. Because every cut starts at the same
place, the prompt at one length is a prefix of the prompt at the next — the 32k prompt opens
with the 128-token one.

Two claim limits are structural rather than incidental. The sweep varies **length alone**: it
says nothing about the other four formats or about another model. And the workload is
prefill-bound, so the published figure is the time to the first token with a 64-token decode
tail behind it; it is not a decode or a chat result.

The joined render is `results/sweep-prompt/sweep-ttft.md`, produced with
`ohyesmlx sweep --varying prompt_tokens --rank ttft_p50_s`. The 25 `results.jsonl` files under
`results/sweep-prompt/*-format/` are the raw record, warmups and failures included; every
number below outside the Reruns section is recomputed from them, and the p50s reproduce the
rendered table to the digit.

## TTFT by prompt length: p50, and p90 beside it

`ttft_p50_s`, seconds, lower is better. The drift annotations are the leaderboard's own and
are read in the caveats below.

| cell | 128 | 1024 | 4096 | 16384 | 32768 |
|---|---|---|---|---|---|
| `oq4__mlxlm` | 0.476 (drift −5.0%) | 2.021 | 7.835 (drift +6.7%) | 30.202 (drift −8.9%) | 76.981 |
| `oq4__omlx` | 0.728 (drift +10.9%) | 2.586 (drift −7.1%) | 8.141 | 36.848 | 85.573 |
| `oq4__optiq` | 0.549 | 2.422 | 9.026 | 42.418 | 91.101 |
| `oq4__vmlx` | 0.404 | 2.171 | 9.020 | 41.203 | FAIL |
| `oq4__osaurus` | 0.592 | 2.246 | 8.266 | 37.729 | 80.335 |

`ttft_p90_s`, seconds. A p90 needs five samples: the two absences below are the rules already
documented in `report.py`, not new exceptions.

| cell | 128 | 1024 | 4096 | 16384 | 32768 |
|---|---|---|---|---|---|
| `oq4__mlxlm` | 0.497 | 2.051 | 8.271 | 33.082 | 77.866 |
| `oq4__omlx` | 0.736 | 2.622 | 8.198 | 37.099 | 87.433 |
| `oq4__optiq` | 0.573 | 2.477 | 9.577 | 43.146 | 94.575 |
| `oq4__vmlx` | 0.415 | 2.183 | 9.139 | 45.014 | FAIL |
| `oq4__osaurus` | — (n=4) | 2.291 | 8.419 | 38.989 | 80.721 |

The two absences are different facts. At 128 Osaurus has four samples, so no p90 exists to
print. At 32k vMLX's row is FAIL and publishes nothing: six of its nine measured requests did
come back, at TTFTs of 85.56–87.51 s, and three produced no output at all — the section on
that cell is below, and publishing that row as FAIL, rather than treating the rerun as a
replacement for it, is Jason's decision, recorded in Reruns.

The two rows agree on shape: within a cell the spread is small — p90 is 0.5–10% above p50 — and
p90 reorders no pair that p50 ranked. Osaurus's 128 p50 is a median of **four** requests rather
than nine, which is why no p90 stands beside it; see the caveats.

### The ordering at each length, with the ties named

Adjacent cells within 3% are called a tie, not a rank: at these sample counts the difference is
the session, not the runtime.

- **128.** vMLX 0.404 < mlx-lm 0.476 < OptiQ 0.549 < Osaurus 0.592 < oMLX 0.728. No ties —
  the smallest step is OptiQ→Osaurus at 7.7%, and the largest vMLX→mlx-lm at 17.9%. The whole
  column lives between 0.40 s and 0.73 s.
- **1024.** mlx-lm 2.021 < vMLX 2.171 < Osaurus 2.246 < OptiQ 2.422 < oMLX 2.586. Still no
  pair inside 3%: the closest is vMLX→Osaurus at 3.5%.
- **4096.** mlx-lm 7.835 < oMLX 8.141 ≈ Osaurus 8.266 < vMLX 9.020 ≈ OptiQ 9.026. **Two ties:**
  oMLX and Osaurus 1.5% apart, vMLX and OptiQ 0.07% apart (6 ms). mlx-lm leads oMLX by 3.9%,
  just outside the tie band.
- **16384.** mlx-lm 30.202 < oMLX 36.848 ≈ Osaurus 37.729 < vMLX 41.203 ≈ OptiQ 42.418.
  **Two ties again:** oMLX/Osaurus 2.4%, vMLX/OptiQ 2.9%. mlx-lm is 22.0% ahead of the pair
  behind it — the one unambiguous lead in the table.
- **32768.** mlx-lm 76.981 < Osaurus 80.335 < oMLX 85.573 < vMLX 86.245 (FAIL, unranked) <
  OptiQ 91.101. oMLX and vMLX's surviving requests sit 0.8% apart, and would be a tie if
  vMLX's row were rankable; it is not, so the published order at 32k is a four-way one.

The shape across lengths is that mlx-lm is first at four of the five lengths (all but 128) by
between 3.9% (4k) and 22.0% (16k); Osaurus is third at 1k, 4k and 16k, second at 32k and
fourth at 128; OptiQ is last at 4k, 16k and 32k. The 4k and 16k orderings are identical
(mlx-lm < oMLX ≈ Osaurus < vMLX ≈ OptiQ). vMLX leads at 128, oMLX drops from second at 4k
to fifth at 1k, and Osaurus and oMLX trade places at 32k.

## Where each runtime's prefill rate peaks, and where it falls off

Two rates, because one of them is contaminated by a constant and the other is not.

**Prefill tok/s, computed as `achieved / TTFT`** — the locally counted prompt over the measured
TTFT, median over the measured requests. This is the rate a user experiences for a prompt of
that length; it includes every fixed cost a request pays.

| runtime | 128 | 1024 | 4096 | 16384 | 32768 |
|---|---|---|---|---|---|
| mlx-lm | 269 | 507 | 523 | **542** | 426 |
| oMLX | 176 | 396 | **503** | 445 | 383 |
| OptiQ | 233 | 423 | **454** | 386 | 360 |
| vMLX | 317 | **472** | 454 | 398 | 380 † |
| Osaurus | 216 | 456 | **495** | 434 | 408 |

† vMLX's 32k figure is a median over the six measured requests that produced output. Its row
is FAIL and publishes no value; the number is here for completeness only.

**The marginal rate** — extra tokens divided by extra TTFT between consecutive lengths
(`(L₂−L₁)/(TTFT₂−TTFT₁)`) — strips the per-request constant, and is the honest answer to "how
fast does this runtime prefill".

| runtime | 128→1k | 1k→4k | 4k→16k | 16k→32k |
|---|---|---|---|---|
| mlx-lm | **580** | 528 | 549 | 350 |
| oMLX | 482 | **553** | 428 | 336 |
| OptiQ | **479** | 465 | 368 | 336 |
| vMLX | **507** | 448 | 382 | 364 |
| Osaurus | **542** | 510 | 417 | 384 |

Read together:

- **The peak is at the short end.** Every runtime's marginal rate is highest on one of the
  first two steps (479–580 tok/s) and declines from there. On the achieved/TTFT figure four of
  five peak at 4096 (454–503 tok/s) and mlx-lm at 16384 (542); the 128 point is low everywhere,
  176–317 tok/s, because a fixed per-request cost that is a minority of a 2-second TTFT is most
  of a 0.4-second one. Backing that constant out of the 128→1k step gives an implied fixed cost
  per request of 0.15 s (vMLX), 0.26 s (mlx-lm), 0.28 s (OptiQ), 0.36 s (Osaurus) and 0.46 s
  (oMLX).
- **The fall-off is at the long end, and mlx-lm's is the steepest.** Across 16k→32k the
  marginal rate is 336–384 tok/s for all five, but mlx-lm falls from the highest rate in the
  table (549 on the previous step) to 350, while Osaurus gives up the least in proportional
  terms (417 → 384). mlx-lm is still the fastest at 32k by absolute TTFT, and the 32k column is
  the one where the five are closest together in rate (336–384).
- **The per-token cost is still rising through the last step for every runtime.** TTFT from 4k
  to 16k grows 3.86–4.70× for a prompt that grew 4.00×, and from 16k to 32k it grows 2.09–2.55×
  for a prompt that grew 2.00×. mlx-lm has both ends of that: the only sub-linear step into 16k
  (3.86×, its rate still improving there) and the steepest step out of it (2.55×, from the
  table's highest marginal rate to 350). Nothing here separates "KV memory pressure" from "a
  longer decode tail behind a longer prefill" — the workload's 64-token tail sits behind every
  TTFT, not inside it.

The 32k column is where the sweep's budget went: those five cells are 3 h 50 min of the 6 h
15 min total and are also the five longest cells in the sweep — mlx-lm 38.1 min, oMLX 48.9,
OptiQ 47.7, vMLX 50.3, Osaurus 45.2, in the order the runner walked the runtimes.

## The cache check: no cell served a repeated prompt from a cache

Every cell sends one identical prompt 17–49 times, and mlx-lm (which OptiQ runs underneath)
keeps an LRU prompt cache that reuses the nearest prefix — so a cache hit would turn the whole
cell into a lookup and publish it as prefill. 06-01c's pre-registered check is: for every cell,
the first warmup request's TTFT (the cold one, load included), the minimum TTFT over the whole
cell, against the measured median. A hit collapses that minimum to a fraction of the median.
The 2026-09-15 grid recorded what a hit looks like on this model — Osaurus at 0.27–0.30 s
against a 2.4 s prefill, 0.11 of the median.

| cell | first warmup TTFT s | min warmup TTFT s | min measured TTFT s | measured p50 s | min warmup / p50 | min measured / p50 |
|---|---|---|---|---|---|---|
| `oq4__mlxlm` 128 | 0.477 | 0.386 | 0.445 | 0.476 | 0.81 | 0.94 |
| `oq4__mlxlm` 1k | 1.719 | 1.597 | 2.003 | 2.021 | 0.79 | 0.99 |
| `oq4__mlxlm` 4k | 6.278 | 6.278 | 7.538 | 7.835 | 0.80 | 0.96 |
| `oq4__mlxlm` 16k | 30.605 | 29.634 | 29.876 | 30.202 | 0.98 | 0.99 |
| `oq4__mlxlm` 32k | 70.905 | 70.905 | 75.543 | 76.981 | 0.92 | 0.98 |
| `oq4__omlx` 128 | 4.038 | 0.588 | 0.713 | 0.728 | 0.81 | 0.98 |
| `oq4__omlx` 1k | 5.568 | 2.443 | 2.549 | 2.586 | 0.94 | 0.99 |
| `oq4__omlx` 4k | 11.372 | 7.827 | 7.898 | 8.141 | 0.96 | 0.97 |
| `oq4__omlx` 16k | 39.903 | 34.452 | 35.255 | 36.848 | 0.93 | 0.96 |
| `oq4__omlx` 32k | 88.489 | 79.914 | 81.020 | 85.573 | 0.93 | 0.95 |
| `oq4__optiq` 128 | 0.517 | 0.426 | 0.531 | 0.549 | 0.77 | 0.97 |
| `oq4__optiq` 1k | 2.025 | 1.977 | 2.395 | 2.422 | 0.82 | 0.99 |
| `oq4__optiq` 4k | 8.233 | 8.076 | 8.991 | 9.026 | 0.89 | 1.00 |
| `oq4__optiq` 16k | 36.806 | 36.806 | 41.362 | 42.418 | 0.87 | 0.98 |
| `oq4__optiq` 32k | 92.179 | 86.663 | 88.990 | 91.101 | 0.95 | 0.98 |
| `oq4__vmlx` 128 | 0.402 | 0.330 | 0.394 | 0.404 | 0.82 | 0.98 |
| `oq4__vmlx` 1k | 1.796 | 1.784 | 2.069 | 2.171 | 0.82 | 0.95 |
| `oq4__vmlx` 4k | 9.044 | 8.587 | 8.548 | 9.020 | 0.95 | 0.95 |
| `oq4__vmlx` 16k | 37.541 | 36.801 | 39.504 | 41.203 | 0.89 | 0.96 |
| `oq4__vmlx` 32k | 81.246 | 79.438 | 85.561 | 86.245 | 0.92 | 0.99 |
| `oq4__osaurus` 128 | 1.491 | 0.403 | 0.583 | 0.592 | **0.68** | 0.99 |
| `oq4__osaurus` 1k | 2.864 | 2.100 | 2.220 | 2.246 | 0.94 | 0.99 |
| `oq4__osaurus` 4k | 8.479 | 8.052 | 8.211 | 8.266 | 0.97 | 0.99 |
| `oq4__osaurus` 16k | 35.259 | 34.704 | 35.238 | 37.729 | 0.92 | 0.93 |
| `oq4__osaurus` 32k | 78.146 | 76.235 | 79.905 | 80.335 | 0.95 | 0.99 |

**Confirmed, every cell.** The lowest ratio anywhere is 0.68 — Osaurus at 128, whose median is
0.592 s and whose fastest request was 0.403 s — and it is the only cell below 0.77. On the
measured requests alone the tightest ratio is 0.93 (Osaurus 16k). A cache hit is a different
kind of number: 0.11 of the median in the recorded grid, not 0.68. The minima sit where a warm
window's spread puts them, and where the *first* warmup sits far above its own cell's median it
is the load landing, not a slow start — oMLX's 4.038 s at 128 (5.5× its median) and 5.568 s at
1k (2.2×), Osaurus's 1.491 s at 128 (2.5×): each is the first request after that runtime was
started, which is the cost the leaderboard's `first request s` column exists to record.

The bar this check was set against is what a hit does to it — Phase 3's recorded hit put the
minimum at 0.11 of the median — and **no runtime in this sweep served a repeated prompt out of
a prefix cache: mlx-lm's LRU cache did not fire on Qwen3.5 across 17–49 identical prompts at
any length up to 32k.** That is the flat-TTFT behaviour the context probe saw at 1.3k, now
confirmed at every length in the sweep and for every runtime in it.

## Osaurus at 128 is one visit's worth of requests, not two

One cell does not carry the sweep's full plan, and it is the only one. `oq4__osaurus` at 128
holds **13 warmup requests and 4 measured** where every other cell holds 20–40 warmups and 9
measured. The evidence that these are one visit's requests and not two visits' worth:

- the 13 + 4 requests' durations sum to 20.245 s and the sampler's window for that cell is
  20.248 s — the window covers those requests exactly;
- in the other 24 cells the kept window covers roughly half the recorded requests (mlx-lm 128:
  24.7 s against 48.2 s of requests; Osaurus 1k: 63.7 against 118.0; vMLX 128: 22.1 against
  40.8), because the sampler runs per visit and only the higher-peak visit's dict survives. A
  record whose window covers *all* its requests has no second visit in it;
- the cell's own log (`log-osaurus-128.log`, written at run time) already reads `n=4`, so this
  is how the run ended, not an edit to the file afterwards.

The record is internally clean — status PASS, reason `None`, the surviving visit's first request
at 1.49 s TTFT against a 0.592 s median, the drift verdict −1.8% — and at the time it was
written nothing in it said why the pinned nine measured batches did not all land. **The cause is
now known, and it is a lost visit: the row holds the second visit's quota and nothing else.** A
cell is planned for two visits (`VISIT_ROUNDS`), the pinned nine batches splitting 5 and 4
between them; here the first visit died in `runtime.start()`, the failure was recorded and the
visit returned `"retry"`, `run_cells` did nothing further with the retry, the second visit
measured its four, and `_set_status` rewrote the row to `PASS, None`, erasing the failed visit's
reason (measure.py:598-606, 486-493, 550-553, 968). Nothing compares a row's measured count
against its pin, so the row rendered clean. Three consequences a reader has to carry: the
0.592 s p50 in the table above is a median of four requests — and 4 is exactly the second
visit's split, which is what makes this a lost visit rather than an early stop — its p90/p99 are
omitted by the n≥5 rule rather than being unavailable, and `cold_load_s` (1.2667 s) and
`first_request_s` (1.9935 s) are the *second* start's numbers, so what the row prints as a cold
load sits behind a warm page cache. The cell has since been rerun — nine measured requests, none
lost (Reruns, below) — and a code fix now keeps a lost visit's reason on the row and prints a short window as `(n=K of N)` beside the entry (it renders here as `0.592 (n=4 of 9)`); it is forward-looking, so this record, written before it, still carries no lost-visit reason.

## vMLX at 32k: 28 of 49 streams produced nothing

`oq4__vmlx` at 32768 is the sweep's one FAIL. `FAIL` here is a status a measured cell carries,
not the `—` an unmeasured combination gets: the runtime ran, the cell holds 49 request records
(40 warmups + 9 measured), and 21 of them produced output.

| requests | came back | produced nothing | error on every failure |
|---|---|---|---|
| 40 warmup | 15 | 25 | `chat stream produced no content` |
| 9 measured | 6 | 3 | `chat stream produced no content` |
| **49** | **21** | **28** | |

That is 28 dead streams, and the error string is identical on all of them. What the string
means is exactly what the transport's empty-content path means: the SSE stream ended with **no
content delta and no reasoning delta**. It is not a status the server sent — a non-200 would
have been recorded as `chat request returned HTTP <status>`, and none of the 49 records carries
one — and it is not the transport's 600 s timeout, which would have been recorded as
`request timed out`.

**Timing.** The failing requests closed anywhere from 1.89 s to 78.62 s after the request went
out (n=28, quartiles 15.68 / 69.62 s, median 37.34 s). The three measured failures — the ones
that cost the cell its numbers — closed after 13.61 s, 6.64 s and 24.70 s. The 21 requests that
did come back took 80.72–90.04 s (median 86.88 s), and **no failure ran as long as the shortest
success**: every dead stream ended before the ~80 s a full 32k prefill-plus-decode took. In
sequence the failures and successes interleave — warmups run
`X.XXX.XX.XXXX.XXX.XXX.X..X.X.XXXXX..X...` — with clusters of 3–4 dead streams between live
ones early and five of the last six warmups coming back.

**The six that came back answered in the reasoning channel only.** Their `text` is empty,
their `reasoning_text` carries a "Thinking Process:" answer, and the transport — which times
whichever channel streamed — reports 64 reasoning deltas, TTFT 85.56–87.51 s and
`completion_tokens` 64 from usage. The card therefore carries decode 49.2 tok/s, ITL 0.0206 s
and prefill 380.0 tok/s over those six. The three that produced nothing carry no timing at all,
which is what trips the metrics floor: the row's reason is **"no content-delta timing, so
decode tok/s is undefined"**, a missing-metric verdict, not a coherence one. Its coherence
floor passed on the reasoning text the model did emit.

**What this is not.** It is not a context refusal. There is no 400, no 413, no
`prompt_too_long`, no truncation: the same 32,765-token prompt was served twice in the earlier
probe on this machine (TTFT 67.02 s and 66.98 s, both coherent, 16k twice too at 28.07 / 29.21
s), and inside this very cell 15 warmups and 6 measured requests did complete, at TTFTs
consistent with full prefill. vMLX's startup-estimated prompt limit is 60% of free Metal memory
divided by per-token KV cost, far above 32k on this model; nothing here was refused — a refusal
has a status code and this cell recorded none.

**What it is, from the server logs.** The record alone cannot say more than that; the cell's own
visit logs can, and they name the failure. `results/logs/vmlx-20260916T164132-18804.log` and
`results/logs/vmlx-20260916T170838-18804.log` hold **28 `Prefill failed` errors, one per dead
stream** — 16 in the first visit and 12 in the second, against 25 and 24 prefill attempts — and
every one of them is the same line:

    RuntimeError: [METAL] Command buffer execution failed: Impacting Interactivity
    (0000000e:kIOGPUCommandBufferCallbackErrorImpactingInteractivity)

raised at `mx.eval(last_logits)` inside `vmlx_engine.mllm_batch_generator._process_prompts`,
after the engine logged `Hybrid prefill path=one-shot … seq_len=32775`. The error is Metal's,
under MLX's `mx.eval`, not a vMLX limit check — the name on it, `Impacting Interactivity`, is the
OS's GPU watchdog — and the transport's `chat stream produced no content` is the same failure
arriving at the client: the server answered HTTP 200 and then aborted the stream before any
delta in either channel. The record's timing agrees with that reading — every dead stream closed
before the ~80 s a full 32k prefill-plus-decode took. A rerun later the same evening
reproduced all of it and worse (Reruns, below); why one attempt survives the guard and the next
dies is in neither log.

Worth stating beside it: the 32k cell's own warmup window is the only
one in the sweep that never settled (`warmup_plateau` false, both visits running the 20-request
cap) — a request that produces no rate cannot close a warmup window, so the cap is what ended
it. The cell is also the sweep's longest at 50.3 minutes.

## Osaurus ran with its prefix and block-disk caches off

Osaurus is the one runtime whose caches cannot be turned off from a start command: they live in
`~/.osaurus/config/server-runtime.json` as `cache.prefix.enabled` and
`cache.blockDisk.enabled`, and with them on every repeated prompt after the first is a lookup —
the sweep would have been a flat line labelled prefill. `scripts/run_sweep_prompt.sh` therefore
toggles both to `false` before the Osaurus cells and restores them afterwards, refusing to exit
clean unless the settings-drift guard reads NONE against the committed baseline; it also
restores on INT/TERM/HUP so a killed sweep cannot leave Jason's Osaurus with its caches off.
The restore is visible in the repository: `config/osaurus-settings-baseline.json` is back to
`cache.prefix.enabled: true` / `cache.blockDisk.enabled: true`, mtime 19:14:53 — five seconds
after the last cell's log closed at 19:14:48, which is where the runner's restore runs.

The measurement agrees with the toggle. Osaurus's TTFTs in this sweep are full-prefill times at
every length — 0.592 s, 2.246 s, 8.266 s, 37.729 s, 80.335 s — and rise with length; a cache
hit is the flat 0.27–0.30 s the 2026-09-15 grid recorded at 1.3k, which would have shown up as
a cell whose median barely moves between 128 and 32k. None does. The 128 rerun ran with the
same toggle off and reads the same way: 0.640 s over nine measured requests, a prefill, not a
lookup.

The consequence for reading Osaurus numbers is the one the context probe already recorded, and
the sweep's own records show it: Osaurus's `usage.prompt_tokens` is character count divided by
four — 151 reported for 128 achieved, 1,277 for 1,024, 3,546 for 4,096, 12,851 for 16,384,
26,215 for 32,765, a ratio of 1.18 / 1.25 / 0.87 / 0.78 / 0.80. Every prefill rate in this
document is `achieved / TTFT` for that reason; the renderer's own `prefill tok/s` column is
usage-based and would understate Osaurus by about 20% at 32k (326 against 408 tok/s).

## Caveats

- **The drift annotations are decode-rate drift, not TTFT drift.** `drift` is the median decode
  rate of the first half of a cell's measured requests against the second half's
  (`measure.measured_drift`), and it is computed over the 64-token decode tail, not over the
  TTFT this document orders by. Five cells are annotated: mlx-lm 128 −5.0%, mlx-lm 4k **+6.7%**,
  mlx-lm 16k −8.9%, oMLX 128 +10.9%, oMLX 1k −7.1%. The positive ones say the decode rate was
  still climbing when the measured window started; they say nothing about the first token, and
  none of them is a floor — all five cells are ranked. A reader who wants to know whether
  *TTFT* moved inside a cell should read the min/p50 ratios above, which are 0.93–1.00 on the
  measured requests.
- **One cell is a five-way comparison and one is a four-way one.** vMLX at 32k is FAIL and
  unranked, so the 32768 column compares four runtimes; Osaurus at 128 measured four requests,
  not nine. Both cells were later rerun, and neither rerun joins the table (Reruns, below).
- **Warmup counts differ per cell, and that is published rather than hidden.** The plateau rule
  asks for at least two windows of five rates and stops when the medians agree within 3%, at a
  cap of 20 per visit over two visits: mlx-lm 30/24/23/21/20, oMLX 27/26/20/20/25, OptiQ
  28/20/20/22/21, vMLX 21/20/20/20/40, Osaurus 13/30/20/20/24, in the order 128/1k/4k/16k/32k.
  A cell that needed more warmup is a cell that was still moving; vMLX's 40 is the cap on both
  visits, and the only unsettled window in the sweep.
- **Wall time ran over the design's budget.** The first cell's log was created at 13:00:16
  local and the last cell's log was written at 19:14:48 — **6 h 15 min** for 25 cells against
  the 4–5 h the design budgeted, of which the 32k cells are 3 h 50 min. By length: 128 takes
  1.5–1.6 min, 1k 2.4–2.8, 4k 5.1–5.8, 16k 16.6–22.7, 32k 38.1–50.3. (The ~8 h quoted for the
  sweep day measures the day: the context probe that precedes the runner is stamped
  11:42–11:57, and the runner itself is the 6 h 15 min above.)
- **The 128 column is the least comparable of the five.** Its TTFTs are 0.40–0.73 s, of which
  0.15–0.46 s is fixed per-request cost that has nothing to do with prefill; a 5% difference
  between two runtimes there is 20–36 ms of it. The 4k-and-up columns are where the ordering
  actually means prefill throughput.
- Everything in this document outside the Reruns section is recomputed from the 25 recorded
  `results.jsonl` files and the rendered sweep, which reproduces from them byte for byte; the
  two reruns in that section were measured after the sweep closed and live in their own run
  directories, with their server logs under `results/logs/`. Nothing else was run for this
  document, and no figure above it was re-measured for it.

## Reruns

Two cells were rerun after the sweep closed, and both are recorded beside it rather than in it.
**The decisions are Jason's:** vMLX at 32k is **published as FAIL** — the sweep's row stands as
written and the rerun is a separate test, not a replacement — and Osaurus at 128 was rerun
because its sweep cell measured 4 of the pinned 9, whose cause the section above now names. Each
run directory keeps an empty per-cell stdout log (`log-vmlx-32768.log`, `log-osaurus-128.log`, 0
bytes each); the records are the `results.jsonl` files beside them, and the runtimes' own output
is under `results/logs/`.

Neither rerun can join the sweep table above. What the join refuses first is a cell measured
twice at one value of the swept pin (`report._check_sweep_cells_appear_once`, guard 2 — *"there
is no latest-wins rule"*); under the Osaurus rerun the runtime version also moved, 0.25.4 in the
sweep against 0.25.5 here, which is the one-runtime-one-version disagreement the grid's guard 4
(`report._check_one_version_per_runtime`) exists to refuse. So the numbers below are read beside
the table, never as new columns of it.

### vMLX at 32k, rerun: the same failure, 43 of 49 streams dead

`results/rerun-vmlx-32k/20260917T005449Z-format`, 2026-09-16 20:54:49–21:21:24 local (26.6 min),
vMLX **1.6.59** — the build the sweep ran — same artifact (`RepublicOfKorokke--Qwen3.5-4B-oQ4`)
and same pins (one `prefill` workload, `max_tokens` 64, temperature `0.0`, seed `0`, `measured`
9, `cooldown_s` 30.0, the plateau warmup; prompt target 32768, achieved 32765).

| requests | came back | produced nothing | error on every failure |
|---|---|---|---|
| 40 warmup | 5 | 35 | `chat stream produced no content` |
| 9 measured | 1 | 8 | `chat stream produced no content` |
| **49** | **6** | **43** | |

The 43 dead streams carry the sweep's error string exactly, and closed 1.50–67.64 s after the
request went out; **no dead stream ran as long as the shortest survivor** (the first warmup,
83.95 s total), the same gap the sweep's 32k cell showed. Five warmups came back — the first
two, then warmups #25, #28 and #36 — at TTFTs of 82.47, 85.02, 89.63, 90.06 and 92.83 s. Of
the nine measured requests one came back, the sixth, at TTFT **92.413 s**, and like the sweep's
six survivors it answered in the reasoning channel only (the transport moves its event count
with the timings it used, so the record's `content_event_count` of 64 is 64 reasoning deltas;
`completion_tokens` 64 from usage; `text` empty). The cell is **FAIL** again, with the sweep's
reason verbatim: *no content-delta timing, so decode tok/s is undefined*.

**The server logs name it.** The cell's two visit logs —
`results/logs/vmlx-20260916T205450-40527.log` and `…T210611-40527.log` — hold 23 and 20
`Prefill failed` errors, **43 in all, one per dead stream**, against 25 + 24 = 49 prefill
attempts for the 49 requests. Every one is the same line:

    RuntimeError: [METAL] Command buffer execution failed: Impacting Interactivity
    (0000000e:kIOGPUCommandBufferCallbackErrorImpactingInteractivity)

raised at `mx.eval(last_logits)` in `vmlx_engine.mllm_batch_generator._process_prompts`, after
`Hybrid prefill path=one-shot … seq_len=32775`. The error is Metal's, under MLX's `mx.eval`,
not a vMLX limit check — the name on it, `Impacting Interactivity`, is the OS's GPU watchdog.
The client-visible string follows from it: the server answered HTTP 200 and then aborted the
stream mid-flight, so the transport saw a stream ending with no delta in either channel. That
the sweep's own 32k visits carry the same 28 errors is in the section above; this rerun is the
same failure mode a few hours later, at a worse rate (43 of 49 against 28 of 49). Why an
identical request survives the guard on one attempt and dies on the next is in neither log.

**Not claimed.** `kIOGPUCommandBufferCallbackErrorImpactingInteractivity` appears in four files
under `results/logs/`, and all four are vMLX at 32k — the sweep's two visit logs and this
rerun's two. No other runtime's server log carries it, and vMLX's own shorter cells do not
either. **Why the other four runtimes — and vMLX at 16k and below — do not trip it is not
established by anything read for this document**: their logs show no such error, and no
runtime's source was read to explain the absence. It is unverified.

### Osaurus at 128, rerun: nine measured requests, none lost

`results/rerun-osaurus-128/20260917T012209Z-format`, 2026-09-16 21:22:09–21:23:34 local,
Osaurus **0.25.5** (the sweep ran 0.25.4), same artifact and pins, caches off as in the sweep.
One setting was pinned for the run: `~/.osaurus/config/server.json`'s
`modelIdleResidencyPolicy.seconds` was **900**, because 0.25.5's update left it at 30 — a value
that unloads the model inside the `cooldown_s` 30.0 between batches, so every request would pay
the load — and the config file was restored byte-exact after the run. The repository's baseline
(`config/osaurus-settings-baseline.json`) records both caches back at `true` and the residency
policy at 900.

**23 warmups, 9 measured, 0 lost** — 32 requests, every one came back, plateau settled. The nine
measured TTFTs are 0.665 / 0.663 / 0.649 / 0.637 / 0.640 / 0.642 / 0.626 / 0.618 / 0.623 s:
**p50 0.6397 s, p90 0.664, p99 0.665**, spread 0.618–0.665 s — a warm window's own spread, not
a lookup (a prefix-cache hit on this model is the 0.27–0.30 s shape the 2026-09-15 grid
recorded). Drift +4.4%, `cold_load_s` 1.30 s, `first_request_s` 2.20 s.

Against the sweep's cell — 0.5919 s over four requests — the rerun's median is **8.1% higher
over nine**. That difference is not a claim about anything: the two runs differ in the runtime's
version as well as in the count, and this document reads no number that moved two things. What
the rerun settles is the count: the pinned nine can land, the runtime does not lose requests
under this workload, and the sweep's four were one lost visit — the second visit's quota, per
the cause above — not a cell that ran out of work.

## Open questions

1. **vMLX at 32k: does a prefill chunk-size setting avoid the watchdog?** The FAIL is published
   (Reruns, above), and the rerun reproduced it: 43 of 49 streams dead, one `[METAL] …
   Impacting Interactivity` per dead stream, on the same build and the same 32,765-token prompt.
   The lever the logs make visible is that vMLX prefills this prompt in one shot (`Hybrid prefill
   path=one-shot`, `seq_len=32775`); whether a chunked or otherwise smaller prefill path exists,
   and whether it would stay under the OS's interactivity guard, is Jason's call.
2. **Osaurus at 128: what publishes now that the rerun exists?** The rerun measured the pinned
   nine with none lost — p50 0.640 s, p90 0.664, p99 0.665 — but it cannot join the sweep table
   (the join refuses a cell measured twice at one pin value, and the version moved 0.25.4 →
   0.25.5), so the table still prints 0.592 s over four, and it is the cell the cache check's
   0.68 minimum lives in. Whether that number stays alone, or the cell is annotated once the
   lost-visit note lands, is a decision above this document.
3. **Does the p90 column get published with one FAIL and one n=4 in it,** or does the sweep
   ship p50 alone and keep p90 as the engine's own figure? Nothing in the reruns changes the
   column's shape: the FAIL is now a decision rather than a pending one, and the n=4 cell's
   nine-sample rerun cannot join it.
4. **Which prefill rate is the published one?** The renderer's `prefill tok/s` divides
   `usage.prompt_tokens` by TTFT, which is not comparable across these five runtimes — Osaurus's
   usage is chars/4, and the other four report the templated count. This document uses
   `achieved / TTFT` for exactly that reason; whether the sweep publishes the achieved-based
   rate beside the renderer's is a decision above this document.
5. **Is a reasoning-only answer an answer for a prefill workload?** vMLX's six surviving 32k
   responses produced no content at all; the transport times the reasoning stream by design, so
   their TTFTs are real, but if the same shape shows up in a *PASSing* cell the question of
   whether to publish its first-token latency will come back. The rerun's one surviving measured
   request took that same shape (TTFT 92.413 s, no content delta), so it is not one cell's
   accident.
