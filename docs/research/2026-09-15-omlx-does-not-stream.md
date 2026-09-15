# oMLX 0.6.4 does not stream, and the harness nearly published 1.5 billion tok/s

Date: 2026-09-15. Machine: MacBook Pro, M2 Max, 64 GiB, macOS 26.6.2.
Run: `results/20260915T151218Z-runtime/` (gitignored). oMLX 0.6.4, `omlx serve`,
`Jundot/Qwen3.6-35B-A3B-oQ4-mtp`, five measured requests, `max_tokens=256`.

This is the run that produced the project's first `PASS`. The `PASS` was wrong, and the way
it was wrong is worth recording in full, because it is the same shape as the failure the
whole project was built around.

## What the leaderboard said

| cell | status | n | TTFT p50 s | ITL s | decode tok/s | aggregate tok/s | cold load s | peak MB |
|---|---|---|---|---|---|---|---|---|
| `oq4__omlx` | **PASS** | 5 | 5.499 | 0.0000 | **1,532,954,517.6** | 44.9 | 2.23 | 21,504 |

One and a half billion tokens per second, an inter-token latency of exactly zero, and a
green `PASS` beside them. Every other column in that row is correct.

## Why

`decode tok/s` is `completion_tokens / (last_content_s - ttft_s)` — the tokens divided by the
window between the first content delta and the last. Every measured observation:

```
events=1  ctok=256  ttft=5.3532  last_content=5.3532  window=1.66e-07
events=1  ctok=256  ttft=5.1823  last_content=5.1823  window=2.08e-07
events=1  ctok=256  ttft=5.4986  last_content=5.4986  window=1.67e-07
events=1  ctok=256  ttft=5.9044  last_content=5.9044  window=8.40e-08
events=1  ctok=256  ttft=6.5838  last_content=6.5838  window=1.67e-07
```

`content_event_count` is **1**. oMLX accepts `"stream": true`, returns correct SSE framing,
opens the stream, holds it — and then delivers the entire 256-token completion in a single
content delta. The first content delta and the last are the same delta, so the window is not
small. It is zero, and what survives is float noise: 1.7e-07 seconds. Dividing 256 by that
noise produced the number above.

No flag changes this. `omlx serve --help` exposes `--sse-keepalive-mode`,
`--max-concurrent-requests`, `--embedding-batch-size`, cache and memory controls, and nothing
that sets streaming granularity. The keepalive comments visible in a raw capture
(`: keepalive 14/16`) are the connection being held open while the whole response is
generated — not partial output.

## The serious part is not the absurd number

An impossible number is self-announcing. A reader sees 1.5 billion tok/s and distrusts the
row. The dangerous column is the one that looks entirely reasonable:

**oMLX's TTFT of 5.5 s is not time-to-first-token. It is time-to-entire-completion.**

The first content delta *is* the whole response, so "time until the first content arrived"
and "time until all 256 tokens were generated" are the same measurement. Placed in a
leaderboard beside a token-streaming runtime's genuine TTFT — stock mlx-lm emits a delta per
token and its TTFT is a true first-token latency — the column silently compares two different
quantities. Every reader would conclude oMLX has catastrophic latency. Nothing in the table
would contradict them.

This is the founding failure in a new costume. Stock mlx-lm returned HTTP 200, full
throughput, and token salad: a result-shaped thing that was not a result. oMLX returns a
well-formed SSE stream, a plausible latency figure, and correct text: a measurement-shaped
thing that measures something else. In both cases nothing raised, nothing timed out, and a
harness that only checked for errors would publish it.

## What is actually true about this cell

Not everything here is unmeasurable. Separating what the stream supports from what it does
not:

| metric | status | why |
|---|---|---|
| coherence | **valid** | The text is correct, relevant English. The gate returns `(True, "ok")`. |
| cold load 2.23 s | **valid** | Measured before any token. Independent of streaming. |
| peak 21,504 MB | **valid** | `phys_footprint` sampled at 1 Hz. Independent of streaming. |
| disk 21,636,566,952 B | **valid** | A property of the artifact. |
| aggregate tok/s 44.9 | **valid** | Every completion token over the wall time the measured requests took. Needs no per-delta timing. The only honest rate this stream supports. |
| TTFT 5.499 s | **valid but NOT comparable** | Real, and real for time-to-completion. Not the same quantity as a streaming runtime's TTFT. |
| decode tok/s | **undefined** | Needs a window between two content deltas. There is one delta. |
| ITL | **undefined** | Same reason. |

The cell served the model correctly and should keep its `PASS`. This is not a coherence
failure and not a transport failure — it is a metric that the stream cannot define, which is
a different thing from a metric that came out badly.

## What this costs the runtime axis

The roadmap treats TTFT and decode tok/s as headline runtime-axis metrics. They are only
available for runtimes that stream incrementally. Stock mlx-lm does; oMLX 0.6.4 does not; the
other runtimes are unverified on this point and must each be checked rather than assumed.

Consequences to carry forward:

1. **Every runtime must be probed for streaming granularity before its numbers are
   compared.** `content_event_count` already records it per observation — it was in the data
   all along, and nothing read it.
2. **The runtime axis is thinner than planned.** A cross-runtime decode tok/s table cannot
   include a non-streaming runtime at all, and a cross-runtime TTFT table has to mark which
   rows are time-to-completion.
3. **`aggregate tok/s`, cold load, and peak memory are the metrics every runtime supports.**
   Any comparison that must span streaming and non-streaming runtimes should lead with those.
4. This strengthens the case for the native-diagonal study: it ranks on exactly those
   universally-available metrics and does not depend on per-delta timing.

## The fix

`report.py` omits `decode tok/s` and `ITL` when `content_event_count < 2`, following the
pattern already used for p90/p99 below five samples — the row says what is missing and why,
rather than showing a number that cannot mean anything. `aggregate tok/s` stays. The TTFT
value stays and is **labelled** as time-to-completion rather than suppressed: the measurement
is real, and hiding it would lose a true fact about the runtime. `PASS` is unchanged.

No epsilon, no floor, no guard against a zero window. A rate the stream cannot support is not
computed at all.

## Reproducing

```
PATH=~/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH python -m ohyesmlx.cli run \
  --study runtime --cells oq4__mlxlm=<artifact>,oq4__omlx=<artifact>
```

Then read `content_event_count` in `results.jsonl` — one delta per response is the signature.
