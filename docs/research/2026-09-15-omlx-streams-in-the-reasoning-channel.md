# CORRECTED — oMLX streams; the harness was reading the wrong channel

Date: 2026-09-15. Machine: MacBook Pro, M2 Max, 64 GiB, macOS 26.6.2.

> **This document's original title and conclusion were wrong.** It was first written as
> "oMLX 0.6.4 does not stream, and the harness nearly published 1.5 billion tok/s", and it
> claimed on the evidence of `omlx serve --help` that no flag could make oMLX stream
> incrementally. That claim is false. oMLX streams fine. The original text is preserved
> below under "What the first version claimed", because how the wrong conclusion was reached
> is the more useful half of this document.

## The correction

oMLX 0.6.4 streams incrementally — in the **`reasoning_content`** channel. It then emits the
entire completed text once more as a single `content` delta at the end. Timed directly, one
request, `max_tokens=128`:

| channel | deltas | first | last | window |
|---|---|---|---|---|
| `reasoning_content` | **15** | 0.685 s | 2.352 s | **1.668 s** |
| `content` | 1 | 2.352 s | 2.352 s | 0.000 s |

`docs/interfaces.md` pins `ttft_s` as *"send → first CONTENT delta. Reasoning deltas
excluded."* For this runtime that is the one channel carrying no timing information at all.
The harness was not measuring a runtime that fails to stream; it was reading the only channel
where the streaming does not appear.

### What the harness published, and what is true

| | published | actual |
|---|---|---|
| TTFT | 5.499 s | **0.685 s** in the probe above — roughly 8x lower |
| decode window | 1.66e-07 s (float noise) | **1.668 s** across 15 deltas |
| decode tok/s | 1,532,954,517.6 | a real, ordinary rate |
| aggregate tok/s | 44.9 | 44.9 — unaffected, it never used per-delta timing |

The reported TTFT was wrong by an order of magnitude **in oMLX's disfavour**. Had the runtime
axis shipped on that number, it would have published a false and damaging claim about a
runtime that was performing well.

### Consequences

- **No hunt for a different runtime is needed.** oMLX loads all four formats and can carry
  the full metric set, decode tok/s and ITL included. The format axis is unaffected.
- **The `>= 2 content deltas` guard in `report.py` stays.** A one-delta stream genuinely has
  no rate, and omitting it is correct. oMLX simply is not a one-delta stream once the right
  channel is read.
- **`transport.py` must take timing from the reasoning deltas when a runtime mirrors.** That
  is the actual fix, and it is separate from the report guard.
- **The mirroring dedupe already shipped is still correct** — it addressed token *counting*.
  Timing is a second, independent consequence of the same mirroring.

## What the first version claimed

Verbatim, the reasoning that produced the wrong answer:

> No flag changes this. `omlx serve --help` exposes `--sse-keepalive-mode`,
> `--max-concurrent-requests`, `--embedding-batch-size`, cache and memory controls, and
> nothing that sets streaming granularity.

Every fact in that paragraph is true. `omlx serve --help` really does expose no
streaming-granularity flag. The conclusion drawn from it — that oMLX therefore cannot stream
incrementally — does not follow, and was not checked before being written down.

## How the error was actually found, and what would have found it sooner

Three cheap checks, none of which had been run:

**1. The settings file, not the flags.** `~/.omlx/settings.json` holds 17 top-level keys
covering scheduler, cache, memory, and sampling — a configuration surface much larger than
the command line. (It contains no streaming key either, but it establishes that `--help` is
not the whole story.)

**2. The shipped source.** oMLX bundles readable Python at
`/Applications/oMLX.app/Contents/Resources/omlx/`. One grep finds it:

```
omlx/output_collector.py:188:    This is used to implement stream_interval batching,
omlx/output_collector.py:192:    stream_interval: int = 1
omlx/engine_core.py:157:    stream_interval: int = 1  # Tokens to batch before streaming (1=every token)
```

A per-token streaming mechanism, defaulting to every token, in a runtime just declared
incapable of streaming. That single grep contradicts the published conclusion outright.

**3. A longer probe.** The original probe used `max_tokens=8` — small enough that the whole
response plausibly fit one chunk, so one content delta looked like proof of non-streaming
rather than a sample size of one. At 96 and 128 tokens the structure is unmistakable: 11 and
15 reasoning deltas against 1 content delta.

**The general lesson.** `--help` documents the command line. It does not document the
runtime. These are GUI applications shipping a CLI as one entry point among several, and
their real configuration surface spans flags, a settings file, per-request API fields, and
behaviour visible only in the shipped source. A negative capability claim — "this tool
*cannot* do X" — needs evidence from the source or the settings, not the absence of a flag.

A claim that a tool cannot do something should be held to a higher standard than a claim
that it can, because the first one closes off investigation and the second invites it.

## The part of the original finding that survives

The `PASS` really did publish 1,532,954,517 tok/s and an ITL of exactly 0.0000, and the guard
added in response is correct and stays. `content_event_count` really was recorded in every
observation from the first live run onward, and nothing read it — that remains the strongest
argument for a startup capability probe rather than a field nobody consults.

And the underlying shape holds, just with a different culprit: **the harness published a
measurement-shaped number that measured something other than what its column name claimed.**
The runtime was fine. The instrument was pointed at the wrong channel.

## Reproducing

```
omlx serve --model-dir <catalog> --host 127.0.0.1 --port 8106 \
  --max-concurrent-requests 1 --memory-guard off --no-cache --api-key probe-key
```

Then time both channels separately — counting deltas per channel is the whole test, and
`max_tokens` must be large enough that a streaming runtime would produce many:

```
curl -sN http://127.0.0.1:8106/v1/chat/completions \
  -H 'Content-Type: application/json' -H 'Authorization: Bearer probe-key' \
  -d '{"model":"probe-model","messages":[{"role":"user","content":"Explain confounded variables in three sentences."}],
       "max_tokens":128,"stream":true,"temperature":0,"stream_options":{"include_usage":true}}'
```
