# 06-01c, before anything is measured: where each runtime's context ends, and what it does there

Date: 2026-09-16. Read from the shipped source of each installed runtime, plus the recorded
grid, with every claim citing the file it came from. The live probe that followed is the last
section, "Measured"; where it and the source reading disagree, the measurement wins.

The question the Phase 6 design asks first: *can each runtime's context be raised from its
start command?* It turns out to be the wrong first question for this model. Qwen3.5-4B declares
`max_position_embeddings: 262144` in every one of the five artifacts, and no runtime's
effective limit sits below 32k on it. The question that matters is the second one — **what a
runtime does with a prompt past its limit** — because two of the five would not refuse it.

## Per runtime

| runtime | limit on Qwen3.5-4B, as started today | past the limit | raise from start command |
|---|---|---|---|
| mlx-lm 0.31.3 | none | no check exists | n/a |
| mlx-optiq 0.5.6 | `--max-context 8192` is passed, and is a **no-op on this model** | would rotate the KV window, silently, on a model it applies to | `--max-context <int>` / `off` |
| oMLX 0.6.4 | 262144, discovered from the nested `text_config` | **HTTP 400** `Prompt too long` | per-model `max_context_window` in settings; no flag |
| vMLX 1.6.59 | memory-estimated at startup (60% of free Metal memory) | **HTTP 413** `prompt_too_long` | `--max-prompt-tokens <int>` |
| Osaurus 0.25.4 | `contextLength: 128000` in `~/.osaurus/config/chat.json` — whether the server path honours it is **not known** | not known (Swift, no readable source) | settings file only |

### mlx-lm

`mlx_lm/server.py` has no prompt-length check anywhere. Qwen3.5's model class defines its own
`make_cache` (`models/qwen3_5.py:304`) returning `ArraysCache` for the linear-attention layers
and a plain unbounded `KVCache` for the full-attention ones. A 32k prompt is simply prefilled.

### mlx-optiq — the cap the start command claims is not there

`optiq/cli.py:2979-3024`: an integer `--max-context` calls
`runtime/context_cap.install(cap)`, which wraps `mlx_lm.server.make_prompt_cache` to pass
`max_kv_size`. On a model that uses the default cache that installs a `RotatingKVCache`, and a
prompt longer than the cap **rotates the window instead of refusing** — the server logs
"longer prompts rotate the KV window instead of OOM-crashing". That is exactly the silent
truncation 06-01c must never measure.

It does not fire here. `mlx_lm.models.cache.make_prompt_cache` defers to the model's
`make_cache` when one exists and ignores `max_kv_size`, and Qwen3.5 defines one (the bundled
mlx-lm in OptiQ's venv is the same code, `qwen3_5.py:304`). `context_cap.py`'s own docstring
says models that manage their own cache "ignore `max_kv_size` and are untouched". LFM2 and
LFM2-MoE define `make_cache` too (`lfm2.py:312`, `lfm2_moe.py:367`), so the MoE column is
untouched as well.

So `--max-context 8192` has never capped anything this project measured, and the grid is not
affected. But a published 32k OptiQ figure next to a start command reading `--max-context 8192`
would be a table contradicting its own provenance. The honest pin for a sweep is `off`, and on
these two models it changes no behaviour. On a future model *without* `make_cache` the 8192
pin would start silently rotating at 8192 tokens — a hazard worth one line in `AGENTS.md`.

### oMLX

`omlx/server.py:1762-1813`, `get_max_context_window`: per-model override, then the model's
discovered native length, then the 32768 fallback. `model_discovery.py:866`,
`_read_model_context_length`, reads nested `text_config` / `language_config` — Qwen3.5's key
lives there — so the discovered value is 262144 and the 32768 fallback is not reached. A prompt
over the limit is refused before prefill with HTTP 400 (`server.py:1840-1847`). Correct
behaviour; nothing to change.

### vMLX

`vmlx_engine/server.py:675`, `_estimate_max_prompt_tokens`: at startup, 60% of free Metal
memory divided by per-token KV cost. Over it, HTTP 413 with code `prompt_too_long`
(`server.py:1140-1175`). An explicit `--max-prompt-tokens` wins over the estimate
(`_resolve_max_prompt_tokens`, `server.py:1091`).

The estimate depends on free memory **at the moment the server starts**, so the limit is not a
pin. On a 4B hybrid model with few full-attention layers it lands far above 32k and will not
fire, but a refusal that depends on what else happened to be resident is not a reproducible
result. If a 32k cell is ever refused by vMLX, the recorded reason has to carry the limit from
the error message, not just "refused".

### Osaurus

No readable source. `chat.json` carries `contextLength: 128000`, which the reference
(`docs/runtimes/osaurus.md:243`) lists among "chat defaults that reach inference" — for the
chat UI. Whether the HTTP server enforces it, truncates, or ignores it has to be probed.

## The prompt cache is the larger hazard for this sweep

**`mlx_lm.server` keeps an LRU prompt cache and reuses the nearest prefix across requests**
(`server.py:753`, `fetch_nearest_cache`). OptiQ runs `mlx_lm.server` underneath, so it has the
same cache. A sweep sends one identical prompt 19+ times per cell; if the cache hit, every
request after the first would time a lookup and publish it as prefill.

The recorded grid says it does not hit on Qwen3.5. Prefill TTFT, first warmups then first
measured requests, from the five publishable dense columns:

| cell | TTFT, s |
|---|---|
| `oq4__mlxlm` | 2.45 2.43 2.39 2.37 … 2.47 2.49 2.44 |
| `oq4__optiq` | 2.38 2.51 2.58 2.59 … 2.59 2.59 2.59 |
| `oq4__omlx` | 2.46 2.64 2.75 2.71 … 2.72 2.73 2.72 |
| `oq4__vmlx` | 1.89 2.19 2.15 2.17 … 2.19 2.19 2.18 |
| `oq4__osaurus` | **0.86 0.27 0.27 0.27 … 0.29 0.30 0.29** |

Four flat series, and Osaurus at a third of a second from request two onward — the 8.3× cache
effect Phase 3 isolated, still present in the published grid. The likely reason mlx-lm and
OptiQ miss is the hybrid architecture: a GatedDeltaNet `ArraysCache` is a recurrent state and
cannot be trimmed back to a prefix, so a stored entry for the full prompt cannot serve a request
that needs the last token recomputed. **That is an inference from the numbers, not read from
the source,** and it is model-specific: on a model with plain attention the same server would
hit, and the numbers would show it.

Consequences for 06-01c:

1. **An Osaurus prompt-length sweep with its cache on measures cache lookups at every length.**
   It would be a flat line labelled prefill. Either Osaurus runs the sweep with
   `cache.prefix.enabled` and `cache.blockDisk.enabled` off — the toggle Jason authorised for
   06-02, under the restore-and-verify-NONE procedure — or its row is `N/A` with that reason.
2. **Every sweep cell needs the same flat-TTFT check the table above is.** Warmup request 1
   against the measured median, per length. A TTFT that collapses after request 1 is a cache
   hit, whatever runtime it is.

## The seed text is 1,309 tokens

`cli.PREFILL_PROMPT` is 6,485 characters, **1,309 tokens** by the oQ4 artifact's own
`tokenizer.json` (1,319–1,321 once each runtime's chat template wraps it). Cutting it at a token
boundary covers the 128 and 1k points. It cannot reach 4k, 16k or 32k: ~130,000 characters of
non-repeating prose are needed for 32k, and the design forbids both repetition and a silently
different prompt. Where that text comes from is a decision, not an implementation detail —
it has to be deterministic, committed, free of downloads, and real prose.

## Only a live request can settle

- Osaurus: what a 32k prompt does at `contextLength: 128000`, and whether a 16k one is served.
- OptiQ: that `usage.prompt_tokens` at 16k equals the templated count — the confirmation that
  the no-op reading above is right and nothing rotated.
- vMLX: the startup estimate, read from its log line `Max prompt/context tokens`.
- mlx-lm and OptiQ: that TTFT stays flat across repeated long prompts. The 1.3k evidence above
  does not prove a 32k prompt behaves the same.

---

## Measured: all five serve 32k whole, and none of them caches it

2026-09-16 11:42–11:57 local, `scripts/probe_context.py <runtime> 16384 32768`, oQ4 cell, one
runtime resident at a time, nothing else running. Each prompt sent twice. Not a published
figure: one request per point, no warmup.

| runtime | sent | `prompt_tokens` | TTFT #1 s | TTFT #2 s | output |
|---|---|---|---|---|---|
| mlx-lm | 16,384 | 16,394 | 32.12 | 32.53 | coherent |
| mlx-lm | 32,765 | 32,775 | 72.95 | 72.03 | coherent |
| oMLX | 16,384 | 16,394 | 36.99 | 33.09 | coherent |
| oMLX | 32,765 | 32,775 | 75.78 | 73.90 | coherent |
| OptiQ (`--max-context off`) | 16,384 | 16,396 | 34.92 | 31.99 | coherent |
| OptiQ | 32,765 | 32,777 | 69.22 | 69.24 | coherent |
| vMLX | 16,384 | 16,389 | 28.07 | 29.21 | coherent |
| vMLX | 32,765 | 32,770 | 67.02 | 66.98 | coherent |
| Osaurus (caches off) | 16,384 | 12,851 † | 33.76 | 33.94 | coherent |
| Osaurus (caches off) | 32,765 | 26,215 † | 75.57 | 74.56 | coherent |

- **No refusal and no truncation.** Every runtime reports the prompt it was sent plus its chat
  template (+5 to +12 tokens, constant per runtime across lengths), so nothing was cut or
  windowed. The per-runtime template overhead is why `prompt_tokens` is recorded beside the
  locally counted `achieved` and never replaces it.
- **No prefix-cache hit on a repeated 32k prompt**, in any of the four: the second TTFT is
  within 5% of the first. The flat-TTFT reading of the 1.3k grid holds at 32k. oMLX's 16k pair
  is the widest (−10.5%) and is one pair — the sweep's own warmup-vs-measured check is what
  decides it.
- Every answer is on-topic: each model summarised the document it was sent (the 16k and 32k
  cuts end in different research notes, and the answers name them differently).
- **Prefill is ~500 tok/s at 16k and ~450 at 32k** across all four, so a 32k request costs
  ~70 s. Under the plateau warmup rule a 32k cell makes at least 20 requests: ~25 minutes per
  cell before loads and cooldowns. Budget the sweep at 4–5 hours.

**Osaurus, probed 2026-09-16 afternoon** with `cache.prefix` and `cache.blockDisk` disabled
(toggled and restored as `scripts/run_sweep_prompt.sh` does; drift NONE before and after).

† **Osaurus's `usage.prompt_tokens` is not a token count.** It is the prompt's character count
divided by four: 51,404 chars → 12,851 and 104,861 chars → 26,215, exact. It served the whole
prompt all the same — TTFT at both lengths matches the other four's full prefill, and each
answer summarises the tail of its cut, which a truncated prompt would not reach. No refusal, no
cache hit (repeat TTFT within 1.3%), so `REFUSED` stays unbuilt.

**Consequence:** `prefill_tps = usage.prompt_tokens / ttft_s` understates Osaurus by the ratio
of chars/4 to real tokens — about 0.78–0.80 on this text, and different on other text. Any
published Osaurus `prefill_tps`, and any prefill ranking that includes Osaurus, is not
comparable with the other four. TTFT is unaffected. The sweep should compare runtimes on TTFT,
or on the locally counted `achieved` over TTFT, never on reported usage.
