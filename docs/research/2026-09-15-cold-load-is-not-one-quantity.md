# `cold_load_s` is not one quantity, and the ranking it produced was inverted

Date: 2026-09-15. Machine: MacBook Pro, M2 Max, 64 GiB, macOS 26.6.2.
Probe: `$CLAUDE_JOB_DIR/tmp/probe_lazy.py` and `confirm_lazy.py`. Qwen3.5-4B.

## The claim this corrects

`docs/research/2026-09-15-grid-loadability-probe.md` published a cold-load ranking and called
it *"the first genuinely comparable figure this project has produced"*:

| runtime | median cold load | as published |
|---|---|---|
| oMLX 0.6.4 | 2.18 s | **fastest** |
| mlx-optiq 0.5.6 | 3.23 s | |
| mlx-lm 0.31.3 | 3.85 s | |
| vMLX 1.6.59 | 16.13 s | slowest |

It was not comparable. Two different quantities sat in one column, and the runtime it named
fastest is second slowest.

## The measurement

`cold_load_s` is the time from spawn until `await_ready` returns. That is a real load time for
a runtime that loads weights at startup. For a runtime that loads them **lazily, on the first
request**, it is the time until the process was *listening* — and the load itself then happens
inside request #1, where it is charged to that request's latency.

Three requests per runtime, **no warmups**, same artifact, timing each:

| runtime | reported `cold_load_s` | req 1 | req 2 | req 3 | hidden in req 1 |
|---|---|---|---|---|---|
| mlx-lm | 3.32 | 0.47 | 0.40 | 0.41 | 0.07 |
| **oMLX** | **3.12** | **3.93** | 0.42 | 0.42 | **+3.51** |
| mlx-optiq | 4.14 | 0.31 | 0.27 | 0.27 | 0.04 |
| vMLX | 9.09 | 0.51 | 0.43 | 0.41 | 0.10 |

Confirmed on two further artifacts:

| artifact | runtime | reported | req 1 | req 2–3 | hidden |
|---|---|---|---|---|---|
| stock-4bit | oMLX | 2.20 | 4.26 | 0.41 / 0.42 | **+3.85** |
| stock-4bit | mlx-lm | 3.29 | 0.46 | 0.39 / 0.36 | 0.10 |
| OptiQ | oMLX | 2.20 | 3.56 | 0.52 / 0.48 | **+3.08** |
| OptiQ | mlx-lm | 2.12 | 0.49 | 0.42 / 0.42 | 0.07 |

**oMLX hides 3.08–3.85 s in its first request, on every artifact tested. The other three hide
0.04–0.10 s, which is noise.** oMLX is the only lazy loader of the four.

## The corrected ranking

Time to first useful token — what a user actually waits — is `cold_load_s` plus the first
request's penalty:

| runtime | reported | hidden | **true cost** | published rank | true rank |
|---|---|---|---|---|---|
| mlx-lm | 3.32 | 0.07 | **3.39 s** | 3rd | **1st** |
| mlx-optiq | 4.14 | 0.04 | **4.18 s** | 2nd | 2nd |
| oMLX | 3.12 | 3.51 | **6.63 s** | **1st** | **3rd** |
| vMLX | 9.09 | 0.10 | **9.19 s** | 4th | 4th |

The runtime published as fastest to load is in fact slower than two of the three it beat.

## Why the harness could not have caught this

`measure.py` runs **three warmup requests before measuring**. A lazy loader's entire cost lands
in warmup #1, which is discarded by design — warmups exist precisely to exclude first-request
effects like JIT and cache population from the measured figures.

That is the right instinct and the wrong outcome here. A JIT warm-up is an artifact of
benchmarking. **Loading the weights is not** — it is work the user pays for every time they
start the server, and discarding it makes a runtime look faster than it is at exactly the
moment the user is waiting.

So the cost is real, is paid on every cold start, and appears **nowhere** in the record:
excluded from `cold_load_s` because readiness already returned, and excluded from every
measured figure because it happened during a warmup.

## The shape, again

This is the fourth instance today of the same failure, and the pattern is now unmistakable:

| | column said | column measured |
|---|---|---|
| stock mlx-lm on a 256-expert MoE | fastest healthy row | token salad |
| oMLX decode rate | 1,532,954,517 tok/s | a zero-length window |
| oMLX TTFT | 5.499 s first-token latency | time-to-completion, wrong channel |
| **oMLX cold load** | **fastest loader** | **time until listening** |

Every one of them is a plausible number attached to a column name that describes something
else. None raised. None timed out. All four would have shipped.

## What should change

`cold_load_s` should keep its definition — time to readiness is a real and useful figure — but
it must not be the only one, and it must not be presented as time-to-first-token.

The cheapest honest fix: **record the first warmup request's latency** alongside it. Warmups
are already made and already timed; only the record discards them. A `first_request_s` column
makes a lazy loader visible without changing what anything already means, and the report can
say plainly that a large gap between it and later requests is a load the runtime deferred.

Any cross-runtime load comparison must use `cold_load_s + first_request_s`, and the leaderboard
should say which runtimes deferred work into the request.

## What this does not say

- Nothing about throughput. A slow loader may still generate fastest, and oMLX's steady-state
  request latency (0.42 s) is comparable to the others'. The correction is to the *load*
  column only.
- Nothing about why oMLX defers. The `--no-cache` pin this harness applies may be involved;
  that was not tested, and the deferral is a fact about how the harness runs it regardless.
- Nothing about Osaurus, which was not in this probe.

## Reproducing

```
python probe_lazy.py    # 4 runtimes, one artifact, 3 requests each, no warmups
python confirm_lazy.py  # oMLX vs mlx-lm across two more artifacts
```

The whole test is: run requests with no warmups and look at whether request 1 costs more than
requests 2 and 3. If it does, the runtime deferred its load into the request.
