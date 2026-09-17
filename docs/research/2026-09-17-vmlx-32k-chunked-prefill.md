# 06-01c follow-up: vMLX at 32k — one env var opens the chunked prefill the flag could not reach

Date: 2026-09-17. Three server starts of one request each, 13:51:53–13:57:29 local, on the same
artifact the sweep used (`RepublicOfKorokke--Qwen3.5-4B-oQ4`, 3,160,559,814 bytes on disk), same
32,768-token target, same 64-token decode tail. One variable moved against the sweep's vMLX cells:
the environment the server was started in.

06-01c published one FAIL: `oq4__vmlx` at 32,768 held 49 request records and 28 of them produced
nothing, every dead stream a `chat stream produced no content` at the client and a
`[METAL] Command buffer execution failed: Impacting Interactivity` at the server, raised at
`mx.eval(last_logits)` after `Hybrid prefill path=one-shot … seq_len=32775`
(`docs/research/2026-09-16-prompt-length-sweep.md` § "vMLX at 32k"). A rerun reproduced it worse
(43 of 49), and a diagnostic with the documented remedy — `--prefill-step-size 512` — reproduced it
again (42 of 49) while logging one-shot on all 24 prefills of its second visit. Open question 1 was
answered *no, not through the documented flag*, and left the lever named but unreachable: whether a
chunked prefill path existed at all for this family.

It exists, one environment variable away, and it is not a tuning knob — it is a gate. With
`VMLX_ALLOW_HYBRID_CHUNKED_PREFILL=1` set in the serving process's environment, the same binary
logs `Hybrid prefill path=chunked`, prefills the 32,775-token span in 2,048-token chunks under
4.10 GB of active Metal memory, and returns a coherent answer with **zero dead streams** across
three consecutive requests.

This note is a diagnostic, not a cell. It answers the mechanism question and reports what three
requests did; it does not replace the FAIL, does not join the sweep table, and publishes no new
32k column for vMLX. Nothing in the sweep document is re-measured here, and the sweep's FAIL stands
as written.

## The lane is gated, and the gate is an environment variable

The prefill lane for hybrid text models is chosen in `_run_vision_encoding_inner`, and the choice is
made in two steps. First the variable is read (`mllm_batch_generator.py` lines 11412–11418, shipped
source of the host app, vMLX 1.6.59):

```python
        # VMLX_ALLOW_HYBRID_CHUNKED_PREFILL: unset -> one-shot default;
        # truthy -> chunk every hybrid; falsy -> one-shot every hybrid.
        # Neither value ever refuses work — this only selects a path.
        _hybrid_chunk_env = (
            os.environ.get("VMLX_ALLOW_HYBRID_CHUNKED_PREFILL")
            or os.environ.get("VMLINUX_ALLOW_HYBRID_CHUNKED_PREFILL")
        )
```

Then the default is set when it is absent, and the per-request gate is computed from it (lines
11435–11463, with the fifteen-line retraction comment elided):

```python
        if _hybrid_chunk_env is not None:
            _allow_hybrid_chunked = _hybrid_chunk_env in (
                "1", "true", "True", "yes", "on"
            )
            _hybrid_path_reason = (
                f"VMLX_ALLOW_HYBRID_CHUNKED_PREFILL={_hybrid_chunk_env!r}"
            )
        else:
            # DEFAULT STAYS ONE-SHOT — the flip was built, proven at the
            # mechanism level, and then RETRACTED on the answer-byte gate …
            _allow_hybrid_chunked = False
            _hybrid_path_reason = (
                "hybrid default one-shot (replacement MLX 0.32.2 fused-D256 "
                "answer-byte gate pending — see the comment at this decision)"
            )
        _hybrid_blocks_chunk = self._is_hybrid and not _allow_hybrid_chunked
```

`_hybrid_blocks_chunk` is what the two prefill lanes test between themselves and the forward:

- the short-prompt lane, line 11755: `if not has_media_payload and (not _hybrid_blocks_chunk or _native_mtp_hybrid_text_split):`
- the chunked lane, lines 11879–11889:

```python
        if (
            not has_media_payload
            and (
                seq_len > self.prefill_step_size * 2
                or (
                    _tight_text_prefill_step_size < self.prefill_step_size
                    and seq_len > _tight_text_prefill_step_size + 1
                )
            )
            and (not _hybrid_blocks_chunk or _native_mtp_hybrid_text_split)
        ):
```

Qwen3.5 sets `self._is_hybrid = True` (the log's own `Runtime cache layout: model_type=qwen3_5
layers=32 layout=0:ArraysCache;…;31:KVCache` — 24 recurrent slots and 8 attention slots), so with the
variable unset `_hybrid_blocks_chunk` is True, both lanes are skipped, and the request falls through
to the one-shot forward. The gate is not family-specific: it applies to every hybrid model.

**This is why `--prefill-step-size` could not help.** The flag is read — at the chunked lane's entry
test (line 11882, `seq_len > self.prefill_step_size * 2`) and as the chunk size itself
(`chunk_size = min(_chunk_ceiling, seq_len - 1 - processed)`, line 12135, with `_chunk_ceiling`
defaulting to `self.prefill_step_size` at lines 11591 and 11974–11978). But all of that is *inside* a
lane that `_hybrid_blocks_chunk` had already closed. The two controls act at different levels: the
flag chooses how large a chunk is, the variable decides whether there are chunks at all. On this
model and this build, no value of the flag changes the lane.

Two other things had to be true for the flag to be irrelevant rather than merely ignored, and both
are visible in the run logs:

- **Native MTP was off**, so the other escape into the chunked lane was shut:
  `and (not _hybrid_blocks_chunk or _native_mtp_hybrid_text_split)` cannot be satisfied from the
  second disjunct because the harness starts vMLX with `--disable-native-mtp`
  (`runtimes.py` lines 1092–1125) and the log confirms it — `MLLM native MTP skipped for
  request=chatcmpl-…: disabled by VMLX_NATIVE_MTP=0/--disable-native-mtp`.
- **No `--prefill-step-size` was passed** by the harness, so the serving path's default 2,048 was in
  force (`cli.py`: flag default 2,048 at lines 3646 and 4411, passed to the scheduler at lines 2659
  and 3063; `mllm_scheduler.py` config default 2,048 at line 387, forwarded at 2641). The
  constructor's own default of 1,024 at `mllm_batch_generator.py:8318` is never the serving value.

## The OOM escape hatch that should have chunked this prompt, and did not

There is a second route to the chunked lane, and it needs no variable: while the hybrid default
blocks chunking, a one-shot forward whose estimated attention buffer exceeds the Metal single-buffer
guard is force-chunked anyway (lines 11521–11527, with the guard constant at 2956):

```python
        if (
            _hybrid_blocks_chunk
            and not has_media_payload
            and not _fused_d256_owns_allocation
            and _predicted_attn_bytes > _OOM_GUARD_BYTES
            and os.environ.get("VMLX_DISABLE_HYBRID_AUTO_CHUNK") not in ("1", "true", "True", "yes", "on")
        ):
```

The estimate is `heads × seq_len² × 2` (line 11485) against the 8 GiB default of
`_HYBRID_ONE_SHOT_GUARD_BYTES` (line 2956). For this model the config is
`num_attention_heads: 16`, `head_dim: 256`, 32 layers, so at `seq_len = 32775` the estimate is

    16 × 32775² × 2 = 34,374,420,000 bytes = 32.01 GiB — four times the 8 GiB guard.

The hatch still did not fire. **No 32k log contains its line.** The hatch's own message,
`Hybrid model (family=…) seq_len=…: one-shot attention buffer … exceeds Metal single-buffer limit
(~9.5 GB). Enabling chunked prefill`, appears zero times in all six 32k logs (`grep -c` on
`results/logs/vmlx-20260916T164132-18804.log`, `…T170838`, `…T205450`, `…T210611`, `…T221754`,
`…T222600`), and the reason every one of those logs carries on its `one-shot` line is the *default*
branch's string, not the hatch's `"one-shot attention buffer would exceed the Metal single-buffer
limit (OOM escape hatch)"`.

The only condition in that conjunction that can be false here is `not _fused_d256_owns_allocation`
(line 11524, computed at line 11486). It is true when the family is in the proven set
(`qwen3_5_text` is), `head_dim` is 256 (it is), the fused-prefill env is not disabled (defaults on)
and **MLX ≥ 0.32.2** — and the bundled interpreter ships `mlx-0.32.2.dist-info`. So the engine
concluded that on this stack the fused kernel owns the allocation and the quadratic estimate does not
describe it, and left the hybrid default alone. That is the recorded chain; one alternative is not
excluded and cannot be from these artefacts: a `VMLX_DISABLE_HYBRID_AUTO_CHUNK` exported in the
operator's shell would suppress the same block (line 11526). Nothing in this repository sets it
(`grep -rn` over `*.md`, `*.py`, `*.sh`, `*.json` finds no assignment), and `runtimes.py` passes no
environment of its own — but a shell export is not in any log.

## The probe: one request, three times, with the variable set

`scripts/probe_vmlx_32k.py` is 69 lines. It sets the variable **in its own process** before starting
the runtime (lines 20–21), sizes the prompt with the harness's own cutter
(`cli.sized_prompt(counter, 32768)` → achieved 32,765 tokens, lines 24–26), starts vMLX through the
harness's `runtimes.RUNTIMES["vmlx"]`, sends exactly one chat request — `max_tokens` 64, temperature
`0.0`, seed `0`, timeout 300 s — prints the observation, and runs `coherence.is_coherent` on the
output. It writes no run record and no `results.jsonl`.

The variable reaches the server by inheritance, not by a flag: `_spawn` calls `subprocess.Popen`
with no `env=` argument (`runtimes.py` lines 172–178), so the child `vmlx serve` sees the parent's
environment. There is no command-line spelling of this variable anywhere in the shipped CLI.

Three runs, three logs, one request each — verified per log: exactly one
`POST /v1/chat/completions`, exactly one `chatcmpl-` id, exactly one path line, one completion.

| run (log create → last write) | log | request id | path line |
|---|---|---|---|
| 13:51:53 → 13:53:21 (88 s) | `results/logs/vmlx-20260917T135153-41764.log` | `chatcmpl-fa1e82d8` | `chunked … VMLX_ALLOW_HYBRID_CHUNKED_PREFILL='1'` |
| 13:53:44 → 13:55:26 (102 s) | `results/logs/vmlx-20260917T135344-44197.log` | `chatcmpl-974725cd` | same |
| 13:55:52 → 13:57:29 (97 s) | `results/logs/vmlx-20260917T135552-46888.log` | `chatcmpl-0c975ca6` | same |

Every request line in all three logs is `path=chunked`; there is no `path=one-shot` line and no
`Prefill failed` line in any of them.

What the 13:53:44 log says, verbatim, from the request's admission to its completion:

    INFO:vmlx_engine.mllm_batch_generator:MLLM prefill cache-in for chatcmpl-974725cd: layer0=ArraysCache offset=None layers=32 cached_tokens=0
    INFO:vmlx_engine.mllm_batch_generator:Hybrid prefill path=chunked family=qwen3_5_text seq_len=32775 cached=0 — VMLX_ALLOW_HYBRID_CHUNKED_PREFILL='1'
    INFO:vmlx_engine.mllm_batch_generator:Deep-span prefill: cleared MLX allocator cache before a 32775-token span (threshold 32768)
    INFO:vmlx_engine.mllm_batch_generator:Pre-sized 8 KV slots to the full 32775-token span +4096 decode headroom (avoids a full K/V realloc per chunk AND at decode start).
    INFO:vmlx_engine.mllm_batch_generator:hybrid-prefill-slots chunk=8 processed=16384 active=4.10GB ArraysCachex24=0.05GB KVCachex8=1.13GB
    INFO:vmlx_engine.mllm_batch_generator:hybrid-prefill-slots chunk=16 processed=32768 active=4.10GB ArraysCachex24=0.05GB KVCachex8=1.13GB
    INFO:vmlx_engine.mllm_batch_generator:span-peak-fit samples=17 intercept=6.02GB slope=-0.0253GB/1k-tok largest_observed_peak=5.69GB
    INFO:vmlx_engine.mllm_batch_generator:MLLM native MTP skipped for request=chatcmpl-974725cd: disabled by VMLX_NATIVE_MTP=0/--disable-native-mtp
    INFO:vmlx_engine.mllm_scheduler:Terminal durability barrier: request=chatcmpl-974725cd wait_ms=113.110 waited=true cache_outcome=unknown detail='cleanup completed; no store outcome recorded'

Each line has a source:

- **The path line** is emitted once per hybrid text prefill, and its reason field is the one the
  decision built (line 11568–11576). `VMLX_ALLOW_HYBRID_CHUNKED_PREFILL='1'` is the env branch's
  string (line 11439–11441) — the run's own log names the variable that selected the lane.
- **The deep-span clear** is the default `VMLX_DEEP_SPAN_CACHE_CLEAR_TOKENS` of 32,768 firing
  (`_maybe_clear_deep_span_cache`, defined at line 3106, logging at 3128): 32,775 ≥ the threshold,
  so the allocator cache was drained before the prefill. A default, not a tuned value.
- **The presize** is the default `VMLX_KV_PRESIZE_SPAN` path (lines 12057–12077) with the default
  4,096-token decode headroom (line 12065): the eight attention layers' `step` is set to the whole
  span so no chunk reallocates K/V. Eight slots, because this model has eight `KVCache` layers.
- **The census lines** are printed every eighth chunk (`if … chunk_num > 0 and chunk_num % 8 == 0`,
  lines 12541–12543) and carry the chunk counter, the cumulative token count and the live cache
  census (lines 12576–12585). `chunk=8 → processed=16384` and `chunk=16 → processed=32768` is the
  chunk size itself: **2,048 tokens**, which is the harness's untouched default from
  `--prefill-step-size` (see above), not the 512 of the earlier diagnostic.
- **The KV figure agrees with the arithmetic.** Eight attention layers × 4 key/value heads × 256
  `head_dim` × 2 (K and V) × 2 bytes at the *presized* 36,871-token capacity is 1.125 GiB — the
  `KVCachex8=1.13GB` the census prints. The census is reading the presized slots, which is exactly
  what the presize line claims it did. The 24 `ArraysCache` slots, the model's GatedDeltaNet state,
  total 0.05 GB.
- **`active=4.10GB`** is `mx.get_active_memory()` sampled at the census points (line 12572) —
  MLX active memory, with the model resident at 2.9 GB before the request (the log's
  `Recorded Metal working-set model baseline: active=2.9GB max=51.8GB`). It is **not** a
  `footprint -p` figure, no sampler ran, and it is not comparable to any `peak_mb` in the sweep's
  memory column. Across the three runs the first census reads 4.10 / 4.10 / 4.85 GB and the second
  4.10 / 4.10 / 4.10 GB.
- **`span-peak-fit`** is the per-chunk transient model the admission valve maintains for the span
  (lines 12824–12831): seventeen samples, an intercept of 6.02 GB, a slope of −0.0253 GB per 1k
  tokens and a largest observed chunk peak of 5.69 GB in this span.

## The request: 200, coherent, and slow

The probe's output, as the dispatch that commissioned this note recorded it — HTTP 200, request
finished in **90.11 s**, TTFT **88.76 s**, `prompt_tokens` 32,765, `completion_tokens` 64,
`content_events` 64, `error` None, and `coherence.is_coherent` passing on an output that carried the
model's full reasoning process. Those are the probe's own printed values, in the probe's own fields
(`scripts/probe_vmlx_32k.py` prints exactly `obs.ok`, `ttft_s`, `total_s`, `prompt_tokens`,
`completion_tokens`, `content_event_count`, `error`, then the coherence verdict); the stdout itself
is not in the repository.

Reconciliation status, stated plainly because the rule is never to publish an unreconciled number:
the probe writes no run record, and the engine's mllm path logs no per-request latency (unlike the
text path, there is no `Chat completion (stream): N tokens in Xs` line), so **88.76 s and 90.11 s are
not recomputable from anything on disk**. What the three logs do corroborate independently: one
request per run, chunked, each reaching the completion barrier, zero `Prefill failed` lines, zero
occurrences of the watchdog string. The run windows above (88 s, 102 s, 97 s from log create to last
write, including cold load and shutdown) bracket a ~90 s request in two of the three runs and not the
first, so the quoted timing belongs to one of the later two — the dispatch names the 13:53:44 log,
whose window is 102 s. Which of the three printed 90.11 s was not reconstructed.

The prompt itself is the same construction as the sweep's 32k cells: achieved 32,765 tokens, engine
`seq_len=32775` — the ten-token difference is the chat template — and the same figure appears on
every one-shot line in the sweep's own 32k visits.

## The failure record, with the lane open and with it shut

Six logs under `results/logs/` carry the watchdog error name, and all six are vMLX at 32,768 (the
sweep document counted four; the step-512 pair had not been run when it was written). Per log,
`Hybrid prefill path=` lines count the requests that reached a prefill and `Prefill failed` lines
count the dead streams, one per failure — so requests minus dead is the survivor count, and that
arithmetic gives 21, 6 and 7 survivors for the sweep, rerun and step-512 datasets, matching the
numbers the sweep document published:

| dataset | build | requests | dead | log |
|---|---|---|---|---|
| sweep, visit 1 (09-16 16:41) | 1.6.59 | 25 | 16 | `vmlx-20260916T164132-18804.log` |
| sweep, visit 2 (09-16 17:08) | 1.6.59 | 24 | 12 | `vmlx-20260916T170838-18804.log` |
| rerun, visit 1 (09-16 20:54) | 1.6.59 | 25 | 23 | `vmlx-20260916T205450-40527.log` |
| rerun, visit 2 (09-16 21:06) | 1.6.59 | 24 | 20 | `vmlx-20260916T210611-40527.log` |
| step-512 diagnostic, visit 1 (09-16 22:17) | 1.6.59 + `--prefill-step-size 512` | 25 | 24 | `vmlx-20260916T221754-22825.log` |
| step-512 diagnostic, visit 2 (09-16 22:26) | 1.6.59 + `--prefill-step-size 512` | 24 | 18 | `vmlx-20260916T222600-22825.log` |
| **probe, three runs (09-17 13:51 / 13:53 / 13:55)** | **1.6.59 + the variable** | **3** | **0** | the three logs above |

The failure, verbatim, from the sweep's first 32k visit — the `one-shot` line, then the error:

    INFO:vmlx_engine.mllm_batch_generator:Hybrid prefill path=one-shot family=qwen3_5_text seq_len=32775 cached=0 — hybrid default one-shot (replacement MLX 0.32.2 fused-D256 answer-byte gate pending — see the comment at this decision)
    ERROR:vmlx_engine.mllm_batch_generator:Prefill failed for chatcmpl-e58c43ec: RuntimeError: [METAL] Command buffer execution failed: Impacting Interactivity (0000000e:kIOGPUCommandBufferCallbackErrorImpactingInteractivity).
    Traceback (most recent call last):
      File "/Applications/vMLX.app/Contents/Resources/bundled-python/python/lib/python3.12/site-packages/vmlx_engine/mllm_batch_generator.py", line 15768, in _process_prompts
        mx.eval(last_logits)
    RuntimeError: [METAL] Command buffer execution failed: Impacting Interactivity (0000000e:kIOGPUCommandBufferCallbackErrorImpactingInteractivity).
    — other requests in batch will continue

(The bundled site-packages copy of `mllm_batch_generator.py` is byte-identical to the app's
`vmlx-engine-source` copy — `diff -q` reports no difference — so the traceback's file path and the
line numbers cited in this document are the same file.)

The reading this note offers for the mechanism is narrow and is consistent with that pair of logs:
the one-shot lane asks Metal for a single forward over 32,775 tokens, whose command buffer runs for
the better part of a minute and is killed by the OS's interactivity guard; the chunked lane breaks
the same span into 2,048-token forwards — the loop's bound `seq_len - 1 - processed` (line 12135)
makes that sixteen full chunks, a six-token chunk and the single-token final forward at line 12838 —
and the guard never fires. Nothing read for this note establishes *why*
one long command buffer trips the watchdog on this machine while sixteen short ones do not, and the
engine's own guard language is about single-buffer *size* (the 8 GiB estimate, the "~9.5 GB"
single-buffer limit in the hatch's message), not about the watchdog at all. That the one-shot failure
is intermittent rather than deterministic is visible in the table above — 16 dead in one visit and
23 in another on the same build, same prompt, same artifact.

## Where this leaves the 32k column, and a correction

The dispatch commissioning this note listed "comparative standing at 32k" as mlx-lm 75.54, Osaurus
79.91, oMLX 81.02, vMLX (chunked) 88.76, OptiQ 88.99, and concluded the 32k column is complete
across all five runtimes. **Those four runtime figures are not p50s and the fifth is not from the
same dataset, so the list is not a column.** Recomputed from the five 32k `results.jsonl` files
under `results/sweep-prompt/*-format/`, the four are exactly the sweep's *minimum* measured TTFT per
cell — and the probe's 88.76 s is a single request from a different lane:

| runtime | 32k p50 (published, sweep) | min measured | max measured | n | status |
|---|---|---|---|---|---|
| `oq4__mlxlm` | 76.981 | 75.543 | 78.466 | 9 | PASS |
| `oq4__osaurus` | 80.335 | 79.905 | 81.021 | 9 | PASS |
| `oq4__omlx` | 85.573 | 81.020 | 87.533 | 9 | PASS |
| `oq4__vmlx` | — | 85.561 | 87.508 | 6 of 9 | **FAIL** |
| `oq4__optiq` | 91.101 | 88.990 | 95.043 | 9 | PASS |

A minimum and a p50 are different estimators, and a single request from a new lane is a third; a
table that sets four minima beside one probe number would be the two-changes-at-once error this
project exists to avoid. The published column therefore stays as the sweep rendered it, with vMLX's
row FAIL and unranked.

What can be said honestly about the probe's single request is same-runtime only: 88.76 s sits inside
the 85.56–92.41 s range that vMLX's *survivors* covered across the three one-shot 32k datasets
(sweep 85.561–87.508 s over six requests, rerun's single survivor 92.413 s) — and those survivors
are a selected subset, because every dead stream closed before the ~80 s a full prefill-and-decode
took. So the chunked lane cost nothing visible in TTFT against vMLX's own successful one-shot
requests, and it converted a 28-of-49 / 43-of-49 failure into three consecutive completions. It has
not been shown to be faster, and one request cannot show a rate.

## What this does not establish

- **Coherence is not answer parity, and the vendor's own gate has not passed.** The reason the
  default is one-shot is in the source at the decision (lines 11443–11457): the chunked default was
  flipped and *retracted* the same day on an answer-byte gate — a measured 2026-08-23 A/B on
  Qwen3.8-27B at temperature 0 where a 9,190-token prompt produced 1,388 output tokens chunked
  against 1,915 one-shot. The diverging mechanism was a materialized softmax for `head_dim=256`,
  which MLX 0.32.2's fused path removes; the vendor's words are that the *replacement live
  answer-byte gate has not passed yet*, and 1.6.61 still defaults to one-shot. The probe ran on the
  bundled MLX 0.32.2, and its check is this project's coherence floor, not a byte comparison. No
  paired one-shot/chunked outputs were diffed for this note.
- **No failure rate.** Three requests, none dead, against 28/49, 43/49 and 42/49 on the one-shot
  lane. Three is not a rate, and the one-shot lane is intermittent by its own record.
- **No timing comparison and no decode result.** The probe's TTFT is one request's; the sweep's
  vMLX 32k cell is FAIL and a rerun cannot join it (`report._check_sweep_cells_appear_once`), so the
  number is not a column entry and decode throughput on this lane was not measured at all.
- **No memory claim.** 4.10 GB is MLX active memory at two census points, not `footprint -p`, and
  the chunked lane's peak memory is unmeasured. It carries no cross-runtime or cross-lane ranking.
- **The watchdog's trigger is uncharacterised** (see above), and with it whether a different chunk
  size, a different prompt length or a different hybrid family is safe.
- **The machine's quietness is not verified.** What is checkable: no other runtime's log under
  `results/logs/` was written inside the probe window, and the engine's own pre-load reading is
  `System memory before load: 33.5GB available / 64.0GB total (47.6% used)`. Whether anything
  non-runtime ran is not in the record, and this is one reason the probe is a diagnostic rather than
  a cell.

## Release comparison: 1.6.59 on the host, 1.6.61 in the wheel

The host app is **vMLX 1.6.59** (its engine constant, `__init__.py`; `runtimes.py` reads that file
for provenance at lines 1132–1137 because `vmlx --version` exits 2). A wheel of **1.6.61** is
unpacked at `/tmp/vmlx-inspect/unpacked/` (`vmlx-1.6.61-py3-none-any.whl`; its `METADATA` says
`Version: 1.6.61`). The dispatch states 1.6.61 is what PyPI serves; that was not re-verified here —
a fetch of the PyPI JSON API timed out — so the local wheel is the evidence this note rests on, and
the "latest on PyPI" claim is the coordinator's, not this document's.

Diffing the whole decision region — from the `VMLX_ALLOW_HYBRID_CHUNKED_PREFILL: unset ->` comment
through the `Hybrid prefill path=` log statement, app lines 11412–11577 against wheel lines
11446–11617 — the two builds differ by **one added block**, GLM-specific:

```python
        _hybrid_blocks_chunk = self._is_hybrid and not _allow_hybrid_chunked
        if getattr(self, "native_glm_cache", None) is not None and not has_media_payload:
            # This experimental route owns an exact materialized N-1 state, …
            _hybrid_blocks_chunk = False
            _hybrid_path_reason = "experimental GLM native SSD exact N-1 boundary"
```

(wheel lines 11497–11503). Everything else in the region is line-for-line the same, including the
variable's name and its second spelling, the truthy set `("1", "true", "True", "yes", "on")`, the
one-shot default and the OOM escape hatch:

| | 1.6.59 (host, engine source) | 1.6.61 (wheel) |
|---|---|---|
| env var read | 11415–11418 | 11449–11452 |
| truthy parse → `_allow_hybrid_chunked` | 11436 | 11470 |
| **default `_allow_hybrid_chunked = False`** | **11458** | **11492** |
| `_hybrid_blocks_chunk` | 11463 | 11497 |
| OOM hatch condition | 11521–11527 | 11561–11567 |
| path log line | 11570 | 11610 |
| chunked lane gate | 11888 | 11929 |

So the release comparison resolves the sweep's open question the same way in both directions:
**1.6.61 does not flip the default**, and upgrading without the variable would still run this cell
one-shot. `VMLX_ALLOW_HYBRID_CHUNKED_PREFILL=1` is the operator mechanism in both versions.

## Open questions

1. **What does a full cell under the variable look like?** Forty-nine requests, the sweep's pins,
   the variable in the start environment, and a vMLX 32k row that is a number rather than a FAIL.
   That is the measurement this note deliberately did not run, and the only thing that can replace
   the published FAIL.
2. **Answer-byte parity against the one-shot lane, on this build and model.** The vendor's own gate
   is the reason the default is one-shot; a temperature-0 paired comparison of the two lanes'
   outputs is what would make the chunked lane publishable rather than merely available.
3. **Chunk size, now that the flag has a lane to act in.** 2,048 was in force here because it is the
   harness default; 512 and 256 are the values vMLX's own help recommends for single-buffer trouble.
   Whether TTFT or failure behaviour moves between them is untested.
4. **Does the harness pin it?** Nothing in `runtimes.py`'s vMLX start command sets the variable, so
   no cell can currently carry this lane and every published vMLX number describes the one-shot
   path. Pinning it in a flagless runtime means an env entry in the start path, and that is a
   harness decision, not this document's.
5. **Which other hybrids benefit?** The gate is family-wide: every hybrid model runs one-shot by
   default and takes the same variable. Nothing here says which of them would survive a chunked
   prefill at long context, and the mechanism section applies to all of them unchanged.
6. **Should `docs/runtimes/vmlx.md` explain it?** `VMLX_ALLOW_HYBRID_CHUNKED_PREFILL` appears there
   once, as one bare name in the "Prefill and batching" list at line 1940, with no mechanism and no
   mention of the one-shot default it overrides.
