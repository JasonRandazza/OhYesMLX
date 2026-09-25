# The KV-cache quantization surface, per runtime (research, 2026-09-24)

**Status:** research complete. No code, no server, no model loaded.
**Dispatch:** evidence for a proposed `--kv-quant off|fp8|int4` header pin, built like
`--cache-state` (`runtimes.Runtime.cache_state_refusal`, `measure.py`, `report.SWEEP_PINS`).
**Question it answers:** for each of the five runtimes, how would the harness drive it into a
KV-cache quantization state — and is `fp8` the right label for what any of them actually does?

**Method.** Static inspection of the installed source and the shipped config files only. No
server was started, no model was loaded, no request was sent, no tensor analyzed. Reading the
installed source was the whole job; the things this document cannot settle — whether a
runtime's *refusal* is exercised on a given model, what a given codec costs in tok/s — need a
live cell and are listed in §10.

**Evidence roots.** Citations are relative to these, and are given in full where they are not.

| Tag | Root |
|---|---|
| `MLXL` | `~/.local/share/ohyesmlx/mlx-lm-0.31.3/lib/python3.14/site-packages/mlx_lm/` |
| `OPT` | `/Users/jrazz/Dev/tools/mlx-optiq/.venv/lib/python3.12/site-packages/optiq/` |
| `OMLX` | `/Applications/oMLX.app/Contents/Resources/omlx/` |
| `MLXVLM` | `/Applications/oMLX.app/Contents/Resources/Python/framework-mlx-base/lib/python3.11/site-packages/mlx_vlm/` |
| `VMLX` | `/Applications/vMLX.app/Contents/Resources/vmlx-engine-source/vmlx_engine/` |
| `G` / `H` | `/Applications/osaurus.app/Contents/MacOS/osaurus` (GUI, 125 MB) and `Contents/Helpers/osaurus` (CLI). Offsets are decimal byte offsets printed by `strings -a -n 4 -t d`. Osaurus ships no readable Python, so its evidence is binary strings — which prove a symbol or key exists and cannot prove control flow. That limit is flagged wherever it carries a claim. |

**Versions as installed today**, checked rather than assumed, because several of the runtime
documents are stale:

| Runtime | Doc says | Installed now | Source of truth |
|---|---|---|---|
| mlx-lm | 0.31.3 | **0.31.3** (`MLXL/_version.py:3`), MLX **0.32.2** | venv `~/.local/share/ohyesmlx/mlx-lm-0.31.3` |
| OptiQ | 0.5.6 | **0.5.13** (`optiq --version` → `mlx-optiq, version 0.5.13`) | venv bundles the same mlx-lm 0.31.3 + MLX 0.32.2 |
| oMLX | 0.6.4 | **0.6.4** (`OMLX/_version.py`) | app bundle |
| Osaurus | 0.25.3 | **0.25.12** (`Info.plist` `CFBundleShortVersionString`) | Mach-O, strings only |
| vMLX | 1.6.59 | **1.6.59** (`VMLX/__init__.py:15`) | app bundle |

Line numbers quoted from `docs/runtimes/optiq.md` are **stale** — that document was written
against 0.5.6 and the flag block has moved by ~170 lines. The live numbers are below.

---

## 1. The headline

**OptiQ is the one runtime this harness can put into a KV-quantization state with a flag and
have it quantize the live cache.** Everything else is a different shade of not-that:

1. **mlx-lm's server has no KV-quantization surface at all.** Not a flag, not an env var, not a
   per-request field. The machinery exists in the same site-packages but is only wired into the
   *client* CLIs (`mlx_lm.generate`, `mlx_lm.cache_prompt`), not the HTTP server.
2. **vMLX has the flag, but its codec covers only the stored prefix-cache copy** — generation
   stays full precision — **and it is inert under the harness's own start command**, which
   passes `--disable-prefix-cache`. A `q4`/`q8` cell there would log its own no-op warning and
   serve fp16.
3. **oMLX's switch is a per-model settings field the harness never writes.** It is `off` by
   construction because the run's base path is a fresh scratch directory — which is a good
   place to be, but it means `on` is not a flag away.
4. **Osaurus's switch is a host setting the harness refuses to move**, and under batched decode
   (this host) its affine route silently falls back to float KV.
5. **`fp8` is wrong for all five.** Nothing in this set has an FP8 (E4M3/E5M2) KV codec. The
   earlier study's "FP8" arms were `mx.quantize` **affine 8-bit**, which is a signed integer
   with a per-group scale and bias. §2 is the naming recommendation.
6. **`off` is pinnable explicitly on one runtime only** — vMLX, with
   `--kv-cache-quantization none`. On oMLX it is structural rather than pinned; on OptiQ it is
   the *absence* of two flags and cannot be made explicit; on Osaurus it is a host state the
   harness verifies and refuses to move.

---

## 2. The naming question — `fp8` has to go, and `int4` is ambiguous

This is the most important output of the dispatch, so it is stated before the per-runtime
detail that supports it.

### 2.1 What the codecs actually are

| Runtime | What `8` or `q8` constructs | What `4` or `q4` constructs |
|---|---|---|
| mlx-lm (client CLIs only) | `QuantizedKVCache(group_size=64, bits=8)` → `mx.quantize(k, group_size, bits)` | same with `bits=4` |
| OptiQ | the same class, via a patched `stream_generate` | same |
| vMLX | the same class, applied at the prefix-cache **storage** boundary | same |
| oMLX | `TurboQuantKVCache(bits=…)` from `mlx_vlm.turboquant` | same |
| Osaurus | `TurboQuantKVCache` (`G:103397984`) or MLX `QuantizedKVCache` (`G:103350992`) | same |

`mx.quantize`'s own signature fixes the first four rows:

```
mlx/core/__init__.pyi:3396   def quantize(w: array, /, group_size: int | None = None,
                                            bits: int | None = None, mode: str = 'affine', ...)
```

`mode` defaults to **`'affine'`**, and `QuantizedKVCache.update_and_fetch` passes neither
`mode` nor a dtype — `mx.quantize(keys, group_size=self.group_size, bits=self.bits)`
(`MLXL/models/cache.py:277-278`), and the same in vMLX's converter
(`VMLX/scheduler.py:2608-2612`) and OptiQ's batch cache (`OPT/runtime/kv/batch.py:43-44`).
So "8-bit" here means **8-bit affine: signed integer codes plus a per-group float scale and
bias**. It is not E4M3, it has no exponent, and it does not share FP8's error profile.

### 2.2 Why `int4` is also a trap

`int4` reads correctly for the affine path and incorrectly for TurboQuant, and the difference
is not cosmetic:

- TurboQuant's own validator refuses a width it cannot express: `_validate_bits` raises
  `TurboQuant requires kv_bits >= 1.` and `TurboQuant currently supports integer and .5
  bit-widths, got {bits}.` (`MLXVLM/turboquant.py:3498-3508`), and oMLX documents the accepted
  set as `2/2.5/3/3.5/4/6/8` (`OMLX/model_settings.py:236`).
- oMLX derives **two** widths from the one value — `key_bits = floor(bits)`,
  `value_bits = ceil(bits)` (`OMLX/turboquant_kv.py:76-92`) — so a single "4" can mean K=4/V=4
  or K=3/V=4 depending on how the runtime rounds, and vMLX's own JANG path carries a
  calibrated key/value pair plus a per-layer critical-layer list
  (`VMLX/utils/jang_loader.py:2055-2080`: `default_key_bits: 3, default_value_bits: 3,
  critical_key_bits: 4, critical_value_bits: 4`, `critical_layers: [0, 1, 2, -3, -2, -1]`).

A grid column named `int4` would therefore put **an affine int4 live cache** and **a
TurboQuant 4-bit codebook cache** in the same column and call them one variable. That is the
"vary one thing at a time" failure committed inside a single value name.

### 2.3 Recommended value names

**Pin the codec, not the width.** Proposed `--kv-quant` values:

| Proposed value | Means | Why not the order's name |
|---|---|---|
| `off` | no KV quantization; the runtime's own native, full-precision cache | keep |
| `affine8` | MLX affine, 8-bit, group size pinned explicitly | `fp8` is false — there is no float8 codec here |
| `affine4` | MLX affine, 4-bit, group size pinned explicitly | `int4` is true for this path, but see the next row |
| `tq4` (not needed for v1) | TurboQuant, 4-bit, **key and value widths both 4** | `int4` would be false: codebook quantization, and two widths, not one |

Rules that follow from the evidence and should travel with the pin:

- **`fp8` is retired.** If a genuine float8/mxfp8 KV codec ever appears, it gets its own value
  and its own column, because it will not be comparable with affine8.
- **`int4`/`int8` are not used as pin values** — `affine4`/`affine8` name the codec and leave
  the name free for a codec that is not affine.
- **The group size is a second variable and is pinned in the command**, not inherited: OptiQ
  defaults it to 64 (`OPT/cli.py:2504`) and vMLX to 64 (`VMLX/cli.py:3883-3889`). vMLX may
  silently *change* it for head-dim compatibility (§7.4).
- **A value a runtime cannot deliver is `N/A` with a reason**, exactly as `cache_state` does —
  never approximated into a neighbouring codec.

---

## 3. mlx-lm 0.31.3 — no surface, and the absence is evidenced

Citations are `MLXL/…` = `~/.local/share/ohyesmlx/mlx-lm-0.31.3/lib/python3.14/site-packages/mlx_lm/`.

### 3.1 How is it turned on?

**It is not, through any surface the server exposes.** Every path was checked:

- **The server's argv.** `main()`'s parser (`server.py:1751-1886`) declares 23 arguments:
  `--model`, `--adapter-path`, `--host`, `--port`, `--allowed-origins`, `--draft-model`,
  `--num-draft-tokens`, `--trust-remote-code`, `--log-level`, `--chat-template`,
  `--use-default-chat-template`, `--temp`, `--top-p`, `--top-k`, `--min-p`, `--max-tokens`,
  `--chat-template-args`, `--decode-concurrency`, `--prompt-concurrency`,
  `--prefill-step-size` (`:1865-1870`), `--prompt-cache-size` (`:1871-1876`),
  `--prompt-cache-bytes` (`:1877-1881`), `--pipeline` (`:1882-1886`).
  **No KV-quantization flag exists.**
- **Any mention of KV quantization anywhere in the server.** `grep -n "kv.bits\|quantized_kv\|
  to_quantized\|QuantizedKVCache"` across `mlx_lm/*.py` and `mlx_lm/models/*.py` lands on
  `generate.py`, `cache_prompt.py` and `models/cache.py` (which defines the class). `server.py`
  is not among them.
- **The cache it builds.** The server constructs prompt caches with
  `cache = make_prompt_cache(self.model_provider.model)` (`server.py:971`), and
  `make_prompt_cache(model, max_kv_size=None)` (`models/cache.py:15-42`) has **no bit-width or
  group-size parameter at all** — it either delegates to the model's own `make_cache()` or
  returns plain `KVCache()`s.
- **The environment.** `grep -n "os.environ\|getenv"` over `server.py` returns **zero** hits.

**What does exist, one layer away.** The codec and its flags are real, but they are wired into
the *client* entry points: `mlx_lm/generate.py:192-208` declares `--kv-bits` ("Number of bits
for KV cache quantization. Defaults to no quantization."), `--kv-group-size` (default 64) and
`--quantized-kv-start`, and `generate.py:299-304` `maybe_quantize_kv_cache()` converts the
populated cache layer by layer via `KVCache.to_quantized(group_size=64, bits=4)`
(`models/cache.py:383-390`). `mlx_lm/cache_prompt.py:61-76` repeats the same flag block.
**Neither is reachable from `mlx_lm.server`.**

Per this project's own rule, the honest form of that is: **there is no flag, no settings key, no
environment variable and no per-request field that turns KV quantization on in this server, and
I looked in all four places plus the cache constructor.** That is not the same as "mlx-lm
cannot do it" — the class is present and the two client CLIs use it, so the capability exists
in the installed package.

### 3.2 Mapping `off` / `fp8` / `int4`

`off` is the only state the server can hold; `fp8` and `int4` are **N/A in this runtime as
installed**. The codec the client path would use is affine 8-bit / 4-bit (§2), so even the
client path is not FP8.

### 3.3 Can the harness pin `off`?

There is nothing to pin — and the structural risk is worth recording rather than the pin:
**the drift vector is the venv.** The harness runs `python -m mlx_lm.server`
(`ohyesmlx/runtimes.py:850-862`) and the venv is named for the version
(`~/.local/share/ohyesmlx/mlx-lm-0.31.3`). If that venv were ever rebuilt onto an upstream
mlx-lm whose server *adds* `--kv-bits` with a non-`None` default, the `mlxlm` column would
change its cache codec with no flag in any recorded command. `runtime_version` is already
recorded on every cell, so the drift would be visible after the fact; a pin adds nothing,
because there is no state to hold constant that could otherwise move.

### 3.4 Side effects

None available, since no surface exists. (For the record, `--prompt-cache-size` and
`--prompt-cache-bytes` do exist and are already the harness's `cache_state` mechanism —
`ohyesmlx/runtimes.py:820-844`.)

---

## 4. OptiQ 0.5.13 — live KV quantization, affine, with two automatic side effects

Citations `OPT/…` = `/Users/jrazz/Dev/tools/mlx-optiq/.venv/lib/python3.12/site-packages/optiq/`.

### 4.1 How is it turned on?

**By `optiq serve`'s own flags** — these are OptiQ's, not mlx-lm's, and because OptiQ consumes
them they are *not* forwarded to the underlying `mlx_lm.server`:

| Flag | Default | Source |
|---|---|---|
| `--kv-bits INTEGER` | `None` = fp16. Help: "Uniform bits for KV cache quantization (4 or 8). Omit for fp16." | `cli.py:2502-2503` |
| `--kv-group-size INTEGER` | `64` | `cli.py:2504` |
| `--quantized-kv-start INTEGER` | `0` | `cli.py:2505-2506` |
| `--kv-config FILE` | `None`; **overrides `--kv-bits`** | `cli.py:2507-2509` |
| `--no-fused-kv` | off | `cli.py:2593` |

The help says "4 or 8" but the option is declared `type=int` with **no `choices`**
(`cli.py:2502`), so nothing enforces that set at the CLI. Whatever is passed reaches
`mx.quantize`.

**Enable path** (`cli.py:2729-2758`):

```python
kv_quant_enabled = (kv_bits is not None) or (kv_config is not None)
if kv_quant_enabled and not no_fused_kv:
    install_streaming_kv()
    installed_fused = install_fused_sdpa()
...
elif kv_bits is not None:
    install_quantized_kv(kv_bits=kv_bits, kv_group_size=kv_group_size,
                         quantized_kv_start=quantized_kv_start)
```

`install_quantized_kv` (`OPT/serve.py:262-…`) patches `mlx_lm.server.stream_generate` to inject
`kv_bits` / `kv_group_size` / `quantized_kv_start`, and first installs
`patch_rotating_to_quantized()` so a sliding-window model does not raise
`NotImplementedError` from `RotatingKVCache.to_quantized`. **This is a live codec**: the
conversion happens once the cache has `quantized_kv_start` tokens and every subsequent decode
read goes through `QuantizedKVCache.update_and_fetch` (which quantizes each new token as it is
written).

**Codec and widths.** mlx-lm's `QuantizedKVCache`, i.e. `mx.quantize(..., mode='affine')` —
affine 8-bit or 4-bit with group size 64 by default. TurboQuant is not present on this path.

**Default when nothing is set: off.** `_effective_kv_bits` returns `None` for "neither flag"
and its docstring says why (`cli.py:2332-2347`): telling a memory estimator the cache is
quantized when it is not "shrinks every window it computes by ~3x". I found no heuristic that
turns KV quantization on by itself (contrast `--stream-experts`, which does auto-enable at
`moe_stream.py:621` on a 0.70×RAM ratio).

### 4.2 Mapping

| Value | OptiQ |
|---|---|
| `off` | the default: omit **both** `--kv-bits` and `--kv-config` |
| `fp8` | **not exact.** `--kv-bits 8` is affine 8-bit, not float8. Honest name `affine8` |
| `int4` | `--kv-bits 4` is affine 4-bit. Honest name `affine4` |

`--kv-config` is a **third** state the pin does not cover: a per-layer mixed-precision recipe
generated by `optiq kv-cache <model>` (`cli.py:2507-2509`), where two artifacts "both 4-bit"
can have different bit widths on different layers. Record the config's own summary if a cell
ever uses it; do not fold it into a uniform value.

### 4.3 Can the harness pin `off` explicitly?

**Not explicitly — `off` is the absence of the flag.** There is no `--kv-bits none` and no
`--no-kv-quant`. The pin would be "pass neither flag", which is what the harness does today and
which is what produces fp16. The default could only drift if OptiQ itself changed the default
of a flag whose current default is `None`; that would be visible in the runtime version.

Note the asymmetry with vMLX: OptiQ's `off` *is* the production default and the flag is not
consumed by anything else, so nothing about `off` changes other state.

### 4.4 Side effects — the first two are automatic

1. **The fused path installs itself whenever KV quant is on** (`cli.py:2730-2739`), on by
   default, and it is not visible in the start command beyond the absence of `--no-fused-kv`:
   - `runtime/streaming_kv_quant.py` converts **one layer at a time** instead of letting
     mlx-lm enqueue every layer's `to_quantized` as one lazy batch — its header states the
     stock path holds "fp16_all_layers + quantized_all_layers co-resident" and OOMs on tight
     RAM (`OPT/runtime/streaming_kv_quant.py:1-25`).
   - `runtime/fused_quant_sdpa.py` replaces the SDPA with a FlashAttention-2 tiling that never
     materializes the scores matrix, and its header gives the size of the effect: on a 24 GB
     Mac at 32k, "stock u4 peaks at 16.35 GB vs fp16's 11.51 GB" while the fused path "drops to
     7.60 GB peak" (`OPT/runtime/fused_quant_sdpa.py:1-30`).
   **So an OptiQ KV-quant cell is not stock-mlx-lm-with-a-quantized-cache**: it is a different
   attention kernel and a different conversion strategy. `--no-fused-kv` is the opt-out and
   produces stock behaviour, which is the right control arm if the codec is the variable.
2. **KV quant can silently cost cross-request batching.** `install_quantized_kv` tries
   `install_batch_kv_quant(default=(kv_bits, kv_group_size))` first — a mergeable quantizing
   cache class for `BatchGenerator` — and falls back to
   `force_sequential_for_kv_quant("--kv-bits")` when the hook point is missing
   (`OPT/serve.py:95-117`, `262-…`). That function's docstring is explicit that mlx-lm's batch
   path never quantizes and that it is forced onto the sequential path instead, "strictly
   better than honoring the flag in name only". At the harness's `--max-concurrent 1` this
   costs nothing, but a future concurrency sweep on this runtime could measure a batching
   loss that the flag caused.

3. `--quantized-kv-start` defaults to `0` (`cli.py:2505-2506`), so quantization begins at token
   0 and the whole prompt is converted. It is a real second axis (a non-zero value leaves the
   prompt in fp16 and quantizes only the generated tail) and is pinned in the command if
   changed.

---

## 5. oMLX 0.6.4 — TurboQuant, per-model, and structurally off

Citations `OMLX/…` = `/Applications/oMLX.app/Contents/Resources/omlx/`.

### 5.1 How is it turned on?

**Not from the command line.** `grep -n "turboquant" OMLX/cli.py` returns **zero** hits, and the
`serve` flag table in `docs/runtimes/omlx.md` §2.2 has no KV-codec entry. The surface is an
**HTTP-settable per-model setting**:

| Field | Default | Source |
|---|---|---|
| `turboquant_kv_enabled` | `False` | `model_settings.py:235` |
| `turboquant_kv_bits` | `4` — documented `2/2.5/3/3.5/4/6/8` | `model_settings.py:236` |
| `turboquant_skip_last` | `True` — "Skip last KVCache layer (prevents corruption on sensitive models)" | `model_settings.py:237-238` |

**Where it lives, and why that matters here.** `ModelSettingsManager` persists to
`<base_path>/model_settings.json` (`model_settings.py:433-435`) and is constructed with
`global_settings.base_path` (`server.py:1928-1929`). The harness starts oMLX with
`--base-path <per-run scratch>` (`ohyesmlx/runtimes.py:1014-1027`), and that scratch's base
directory is created **empty** (`runtimes.py:464-483` `create_omlx_scratch`). There is
therefore no `model_settings.json` in a run's base path, and every field is at its declared
default. It can also be written while the server runs, over
`PUT /api/models/{model_id}/settings` (`admin/routes.py:2219-2226`).

**How it is applied.** `engine/batched.py:329-337` installs the attention patch and logs
"TurboQuant KV cache enabled: {bits} bits"; `engine/batched.py:590-597` sets
`scheduler._turboquant_kv_bits` / `_turboquant_skip_last`.

**Codec.** `TurboQuantKVCache` from `mlx_vlm.turboquant` (`OMLX/turboquant_kv.py:1-30`,
`MLXVLM/turboquant.py`). It is a codebook (MSE / polar-product family) codec, **not** MLX
affine: the module's own `_rebuild_codecs` splits a single `bits` into
`key_bits = floor` / `val_bits = ceil` and rebuilds "rotation matrices, codebooks" determined by
`(head_dim, bits, seed)` (`OMLX/turboquant_kv.py:70-92`). `turboquant_enabled(bits, scheme)`
returns `False` when `bits is None` (`MLXVLM/turboquant.py:3510-3515`) — it is a predicate, not
an auto-enabler.

**Default when nothing is set: off.** `turboquant_kv_enabled = False`, and no code path I found
sets it automatically. The conversion happens only when the scheduler's
`_turboquant_kv_bits is not None` (`scheduler.py:3437`, `3812`).

### 5.2 Mapping

| Value | oMLX |
|---|---|
| `off` | the default — no `model_settings.json` in the per-run base path |
| `fp8` | **N/A.** No float8 KV codec found in the bundle's model-settings surface or in the TurboQuant module |
| `int4` | **not exact.** `turboquant_kv_bits = 4` is a 4-bit codebook codec with K=4/V=4 derived by floor/ceil. Honest name `tq4`; `int4` implies the affine codec this is not |

### 5.3 Can the harness pin `off`?

**Yes, and it is stronger than a pin: it is a property of the scratch the harness already
creates.** The runtime's own defaults are read from a file the harness never writes, so a cell
is in `off` by construction. What is *not* pinned is the *negative* — if a future harness (or a
future worker) wrote `model_settings.json` into the scratch, or called the admin route, the
state would move with nothing in the start command recording it. If the `--kv-quant` pin is
built, `off` should be accepted for oMLX on that structural basis, and any other value should
require the scratch to be written deliberately — a change to `runtimes.Omlx`, and a decision
this document does not make.

### 5.4 Side effects

1. **`turboquant_skip_last` leaves the last KV layer in full precision**
   (`scheduler.py:3325-3345`): the conversion walks the cache and skips the final KVCache layer
   when the layout has more than one, logging "skipped last KVCache layer". So a "4-bit" cell
   holds one layer at fp16 — the memory saving is not uniform across layers, and a per-layer
   mixed state is the intended behaviour, not a defect.
2. **Conversion happens after prefill, not during it.** `_apply_turboquant_kv_convert`
   (`scheduler.py:3355-3390`) exists specifically so "prefill hidden states stay exact and
   quantization error only enters at decode-time reads"; its docstring records that quantizing
   on the fly during prefill "corrupted hidden states" (issues #717/#771). So a TQ cell's TTFT
   is an fp16 prefill plus a conversion, and its decode is quantized. Two different codecs in
   one request.
3. **Not every cache is convertible.** `_turboquant_eligible` (`scheduler.py:3257-3300`) excludes
   MLA models (DeepSeek/GLM-4.7-Flash) and attention-sink models outright, and passes
   rotating/sliding-window and state-array caches through unconverted. An oMLX TQ cell on such
   a model would be `N/A`, not a small number — and the runtime would say so only in a log line.
4. The SSD/paged caches carry an expected-bits fingerprint
   (`cache/paged_ssd_cache.py:1690-1703`, `4305-4319`) so a bits change invalidates stored
   blocks; irrelevant under the harness's `--no-cache`, relevant to anyone who turns the
   cache on in the same run.

---

## 6. Osaurus 0.25.12 — two codecs, host settings, and a route that silently does nothing

Osaurus ships **no readable Python** (see `docs/runtimes/osaurus.md` §0). Every citation below
is a literal in the shipped Mach-O, reproducible with:

```sh
strings -a -n 4 -t d /Applications/osaurus.app/Contents/MacOS/osaurus | grep -F '<literal>'
```

A string proves a key or a message exists. It cannot prove control flow, and where the claim is
about behaviour it is labelled as such.

### 6.1 How is it turned on?

**No command-line flag exists in either direction** (`docs/runtimes/osaurus.md` §2.1 and §2.4:
`serve` takes `--port`, `--expose`, `--yes`, `--supervise`, `--interval` and nothing else).
The surface is `~/.osaurus/config/server-runtime.json`:

| Key | Value on this host | Evidence |
|---|---|---|
| `cache.liveKVCodec` | `engine_selected` | key at `G:100592538` and as a full path `cache.liveKVCodec` at `G:110210656`; live value read from the file. Help text: *"Compress KV cache entries in memory. TurboQuant trades quality for footprint and needs explicit bit widths."* (`G:108367232`) |
| `cache.turboQuantKeyBits` | **absent** | key at `G:100592560`; help *"TurboQuant Key Bits (2…"* `G:108367344`, *"Quantization bit width for the key cache."* `G:108367376` |
| `cache.turboQuantValueBits` | **absent** | key at `G:100592592`; `G:108367424`, `G:108367456` |
| `cache.storedKVCodec` | `auto` | key at `G:100592677`; help *"Codec used when serializing KV blocks to disk."* (`G:108367184`) |

The two bit keys are validated `2..8`: *"TurboQuant key bits must be between 2 and 8."*
(`G:110210480`) and *"TurboQuant value bits must be between 2 and 8."* (`G:110210400`); the
codec requires them explicitly — *"TurboQuant KV requires explicit key and value bit widths."*
(`G:110210688`). `docs/runtimes/osaurus.md` §3.2 prints the enum for `liveKVCodec` as
`engine_selected (| turboquant)` and records these two keys as schema-validated but absent from
this host's file — consistent with the above, and it is the doc's reading of the same binary.

Two codec families exist in the binary, so "TurboQuant" is not the only possibility:

- MLX's generic `QuantizedKVCache` — `QuantizedKVCache` (`G:103350992`),
  `QuantizedKVCacheProtocol` (`G:103351504`), the update message *"`update` was called on
  `QuantizedKVCache`. Use `updateQuantized` instead."* (`G:110182736`), the state-shape
  messages (`G:110182816`, `G:110182912`), and `MLXLMCommon.QuantizedKVCache`
  (`G:111255728`) — i.e. it is mlx-swift-lm's affine cache, the same codec family as OptiQ's.
- TurboQuant — `TurboQuantKVCache` (`G:103397984`) and
  `CompilableTurboQuantKVCache` (`G:103323920`), with `turboQuantKVLayerCount`,
  `compilableTurboQuantKVLayerCount` and `convertedTurboQuantKVLayerCount` counters
  (`G:100588592`, `:100588656`, `:100589024`).

There is also a **request-side** option cluster carrying `kvBits`, `kvGroupSize`,
`quantizedKVStart` and `kvMode` (`G:100578363`, `:100578370`, `:100578384`, `:100578401`),
sitting in the same Codable key run as `temperature`, `topP`, `topK`, `minP`, `randomSeed`,
`repetitionPenalty`, `maxTokens`, `maxKVSize` — i.e. the per-request/generation-options DTO,
which is the twin of the `modelOptions` field described in `docs/runtimes/osaurus.md` §4.2.
**Whether that bag is honoured on the OpenAI chat path is not established by a string table**
(§10).

**The one behaviour that is stated outright, and it matters.** Two messages in `G` describe the
batched-decode case:

```
G:111612192  Slot %{public}s: legacy kvBits is not supported under batched decode.
             Request will run with float KV. Use kvMode: .turboQuant(...) for
             memory-efficient batched decode.
G:111612368  Slot %{public}s: affine KV quantization (kvMode: .affine) is not supported
             under batched decode. Request will run with float KV. Use .turboQuant for
             memory-efficient batched decode.
G:111612128  Slot %{public}s: applied coordinator defaultKVMode
```

So Osaurus's affine/`kvBits` route **falls back to float KV under batched decode**, with a log
line and nothing else — and this host runs `concurrency.continuousBatching: true`
(`docs/runtimes/osaurus.md` §3.2). TurboQuant is the only memory-efficient route while
batching is on, which is the same shape as vMLX §7.4's "no effect without prefix cache".

**Default when nothing is set.** `cache.liveKVCodec = engine_selected` — the engine chooses, and
with no TurboQuant bits in the file the delivered state is the model's native (float) cache.
`cache.storedKVCodec = auto`.

### 6.2 Mapping

| Value | Osaurus |
|---|---|
| `off` | the state the host is already in. Not a flag; verified, not pinned (§6.3) |
| `fp8` | **N/A.** No float8 KV codec found in the string table; the two codec families are mlx affine `QuantizedKVCache` and TurboQuant |
| `int4` | **not exact, and not reachable by a start command.** The affine route is `kvMode: .affine` / legacy `kvBits`, which is *inert under batched decode*; the live route is TurboQuant, which is a codebook codec, not int4. Honest name for the TurboQuant state: `tqK{key}/V{value}` — the runtime needs both widths |

### 6.3 Can the harness pin `off`?

**No — and that is already the design.** This is the `cache_state` precedent exactly
(`ohyesmlx/runtimes.py:886-915`): Osaurus exposes no flag, the harness does not edit the host's
settings, so the requested state is honoured only when the host is already in it, and anything
else is `N/A` with a reason.

The useful difference is that **the gate for the KV codec already exists**:

- `ohyesmlx/osaurus_settings.py:40-41` tracks `cache.storedKVCodec` and `cache.liveKVCodec` in
  `TRACKED_KEYS` (alongside five other `cache.*` keys), and
- `Osaurus.check_host_state` (`runtimes.py:951-969`) refuses to start the runtime when the live
  values differ from `config/osaurus-settings-baseline.json`.

The baseline currently records `cache.liveKVCodec = engine_selected` and
`cache.storedKVCodec = auto`, and the live host agrees (checked 2026-09-24). So a machine where
someone had switched the codec to `turboquant` would be refused rather than measured — which is
what a KV-quant pin wants for `off`, at the cost of being a refusal rather than a flag.

**One gap worth closing if the pin is built:** `cache.turboQuantKeyBits` and
`cache.turboQuantValueBits` are **not** in `TRACKED_KEYS`. A host that had gone to
`liveKVCodec = turboquant` would be caught by the codec key, but a change of *widths* under an
unchanged `turboquant` setting would not be. Two lines in `osaurus_settings.py` and the
baseline file close it.

### 6.4 Side effects

1. **The affine route silently degrades to float under batching** (§6.1) — a cell pinned to a
   `kvBits` value would record a pin it did not hold.
2. **TurboQuant needs both widths explicitly**, so a single-value pin cannot express it; and
   `convertedTurboQuantKVLayerCount` versus `turboQuantKVLayerCount` implies a partial
   conversion (some layers converted, some not), which is the same per-layer structure oMLX has
   with `turboquant_skip_last`.
3. `defaultKVMode` exists as a **coordinator-level default** (`G:111612128`), so a request that
   specifies nothing can inherit a mode from another layer of configuration — a fourth place
   the state can come from, and one this document does not enumerate.
4. None of this is reachable through the harness's own settings gate today, because
   `runtimes.Osaurus.start_command` passes no tuning flags at all (`runtimes.py:877-884`).

---

## 7. vMLX 1.6.59 — explicit, affine, and *storage-only*

Citations `VMLX/…` = `/Applications/vMLX.app/Contents/Resources/vmlx-engine-source/vmlx_engine/`.

### 7.1 How is it turned on?

**A flag, plus an environment override, and the flag is deliberately tri-state:**

```python
VMLX/cli.py:3864   serve_parser.add_argument(
VMLX/cli.py:3865       "--kv-cache-quantization",
                       type=str, default=None, choices=["none", "q4", "q8"],
                       help="Optionally encode generic stored KV for diagnostics. "
                            "q8 = 8-bit (minimal quality loss, ~2x savings). "
                            "q4 = 4-bit (slight quality loss, ~4x savings). "
                            "Cache is stored compressed but decompressed for generation "
                            "(no inference slowdown). Requires --continuous-batching. "
                            "Omitting this flag uses production auto mode: … with no generic "
                            "TurboQuant replacement or added stored codec. Passing the flag "
                            "explicitly disables loader-level TurboQuant so the requested "
                            "diagnostic stored codec is the only added codec. (default: native)",
VMLX/cli.py:3883   serve_parser.add_argument("--kv-cache-group-size", type=int, default=64, …)
```

`default=None` is deliberate: "default=None lets us distinguish 'user didn't pass it' (None)
from 'user explicitly chose none' ('none')" (`cli.py:3857-3863`). `q4`/`q8` become bits 4/8 at
the two places the codec is built (`VMLX/scheduler.py:1395`, `VMLX/mllm_scheduler.py:1167`).
Environment override:
`VMLX_DEFAULT_KV_CACHE_QUANTIZATION` (`cli.py:1448-1464`), validated against
`none|q4|q8`; `VMLX_DISABLE_TQ_KV` / `VMLX_FORCE_TQ_AUTO` / `VMLX_FULL_PRECISION_LIVE_KV`
(`cli.py:60-91`). No `VMLX_*` variable is set in this host's environment (checked).

**What the codec is.** MLX affine `QuantizedKVCache`, built with raw `mx.quantize`
(`VMLX/scheduler.py:2606-2631`, and `_wrap_make_cache_quantized` at `scheduler.py:2443-…` /
`mllm_scheduler.py:1783-…`). Not FP8, and — the part that matters most — **not live**:

> "Quantization is applied at the storage/retrieval boundary of the prefix cache, **NOT at
> model.make_cache() level**. … During generation: full-precision KVCache (no quality loss). In
> prefix cache: quantized QuantizedKVCache (memory savings)."
> — `VMLX/scheduler.py:2444-2458`

**And it only fires when the prefix cache is on.** Both schedulers gate on it and log the
no-op when it is off:

```python
VMLX/scheduler.py:1393       elif self.config.kv_cache_quantization != "none":
VMLX/scheduler.py:1394           if self.config.enable_prefix_cache:
VMLX/scheduler.py:1395               bits = 4 if self.config.kv_cache_quantization == "q4" else 8
VMLX/scheduler.py:1396               self._wrap_make_cache_quantized(bits, self.config.kv_cache_group_size)
                                     logger.info("KV cache quantization enabled: …")
                                 else:
                                     logger.warning(f"KV cache quantization '{…}' requested but prefix "
                                                    "cache is disabled — quantization has no effect "
                                                    "without prefix cache")
```
(the same shape at `VMLX/mllm_scheduler.py:1165-1177`), and the flag really does reach that
field on the serve path: inside `serve_command`'s `elif args.continuous_batching:` branch,
`--disable-prefix-cache` makes `enable_prefix_cache = args.enable_prefix_cache and not
args.disable_prefix_cache` false (`cli.py:2639`) and that value is handed to the scheduler
config at `cli.py:2667`. (`bench` repeats the pair at `:3024` → `:3071`.) The harness passes
`--continuous-batching` (`runtimes.py:1191`), so the branch is taken.

**This collides with the harness's own command.** `runtimes.Vmlx.start_command` pins
`--disable-prefix-cache` unless the run was pinned `cache_state="on"`
(`ohyesmlx/runtimes.py:1161-1163`). **Under the harness's default start command,
`--kv-cache-quantization q4|q8` on vMLX is therefore inert** — it logs its own warning and
returns. A future `--kv-quant` cell on vMLX must either also enable the prefix cache (making
the run vary two things) or accept that the value is `N/A`.

**Default when nothing is set: native, with both generic and loader-level TurboQuant off.**
With the flag omitted, `cli.py:1437-1464` sets `kv_cache_quantization` from
`VMLX_DEFAULT_KV_CACHE_QUANTIZATION` or `"none"`, and then calls
`_configure_generic_tq_diagnostic_policy` (`cli.py:60-91`), which — with no `VMLX_FORCE_TQ_AUTO`
in the environment — sets `VMLX_DISABLE_TQ_KV=1` and logs "Native live-cache policy active:
preserving the model's make_cache() objects; generic TurboQuant KV replacement is disabled."

**This corrects `docs/runtimes/vmlx.md` §7.2.** That section reads the JANG loader's condition
("only activates when `jang_config.json` has `turboquant.enabled=true`") as the deciding one.
The loader's early return comes first and the CLI sets the variable it checks:
`_patch_turboquant_make_cache` returns immediately when `VMLX_DISABLE_TQ_KV` is truthy
(`VMLX/utils/jang_loader.py:1969-1975`), and in 1.6.59 that variable is set **by default in
every configuration except the diagnostic one** (`cli.py:86`, and `cli.py:1510-1512` sets it
again whenever the flag is passed explicitly). Loader-level TurboQuant is therefore reachable
only with the flag omitted **and** `VMLX_FORCE_TQ_AUTO=1` **and** no
`VMLX_DISABLE_TQ_KV`/`VMLX_FULL_PRECISION_LIVE_KV` in the ambient environment. The doc's
"the KV cache's precision can be decided by a key inside the model artifact" is not what this
build does by default.

### 7.2 Mapping

| Value | vMLX |
|---|---|
| `off` | **`--kv-cache-quantization none` — explicit, and the only explicitly-pinnable `off` in the set.** It is not only the same state the omitted flag produces; it also sets `kv_cache_quantization_explicit = True`, which suppresses the family-specific auto-resets (`cli.py:1509-1517`) |
| `fp8` | **not exact.** `q8` is affine 8-bit at a storage boundary. Honest name `affine8` |
| `int4` | `q4` is affine 4-bit at a storage boundary. Honest name `affine4`, and the state is only reachable with the prefix cache on |

### 7.3 Can the harness pin `off` explicitly?

**Yes.** `--kv-cache-quantization none` is a real, accepted value that is the production
default, and it is *not* neutral in the way the current `Vmlx` docstring says. That docstring
(`ohyesmlx/runtimes.py:1134-1138`) records the omission as the deliberate choice because
"passing it explicitly *disables* loader-level TurboQuant". That reasoning was written against
the loader-only reading; in 1.6.59 **omitting the flag also disables loader-level TurboQuant**
(`cli.py:86`), so the two differ only in `kv_cache_quantization_explicit`, and for the value
`none` both end in the same cache state. Pinning `none` removes the last way the state could
move underneath a run; the docstring should be updated when the pin is built.

### 7.4 Side effects

1. **Passing the flag at all disables loader-level TurboQuant.** `cli.py:1509-1517` sets
   `VMLX_DISABLE_TQ_KV=1` and pops `VMLX_FORCE_TQ_AUTO`, logging that "JANG-calibrated
   TurboQuant KV is skipped at load time". So `affine4` is not "the default plus a codec"; it
   is a substitution.
2. **Family-specific auto-resets**, all of which force the value back to `none` **unless** it
   was passed explicitly: MiniMax-M3's MSA cache (`scheduler.py:999-1011`), ZAYA/CCA typed
   caches (`scheduler.py:1012-1024`, `mllm_scheduler.py:1138-1146`), MLA models
   (`mllm_scheduler.py:1147-1150`), and MiMo-V2 asymmetric mixed-SWA (`cli.py:1852-1861`). An
   explicit `q4` on such a model is honoured-but-not-release-cleared per the runtime's own log
   text, which is a reason to expect a coherence failure rather than a speed number.
3. **The group size can be silently changed.** `_wrap_make_cache_quantized` runs
   `choose_supported_kv_group_size(cache_head_dims, group_size)` and quantizes at the adjusted
   value (`scheduler.py:2501-2510`, `mllm_scheduler.py:1821-1830`, helper at
   `utils/head_dim_detection.py:131`), and disables the codec entirely with an error when no
   group size fits. So the group size recorded in the command is not necessarily the group size
   used.
4. **It changes the cache namespace.** The prefix/paged/block-disk scope key includes the
   quantization tag (`VMLX/scheduler.py:1796-1806`: `f"{model_path}:quant={quant_tag}:…"`), so
   changing this flag orphans the previous on-disk namespace rather than reusing it — relevant
   given the 22 GB of block cache on this machine.
5. **`--continuous-batching` is required** (help text) — the harness already passes it
   (`runtimes.py:1191`).

---

## 8. Corrections to the existing notes

| Note | What it says | What is true now |
|---|---|---|
| `docs/runtimes/optiq.md` §2.2 / §7.7 | flags at `cli.py:2334-2339`, `:2404`; version 0.5.6 | flags are at `cli.py:2502-2509` and `:2593`; installed version is **0.5.13**. §7.7's substance holds — the fused path auto-installs whenever KV quant is enabled — and it now also covers the batch-vs-sequential fallback (`serve.py:95-117`) |
| `docs/runtimes/vmlx.md` §7.2 | loader-level TurboQuant is auto-enabled by the bundle's `jang_config.json` | in 1.6.59 the CLI pre-sets `VMLX_DISABLE_TQ_KV=1` on every path except the `VMLX_FORCE_TQ_AUTO=1` diagnostic (`cli.py:60-91`, `1510-1512`), so the loader's auto path is unreachable by default |
| `docs/runtimes/osaurus.md` | 0.25.3 | installed is **0.25.12**. The `cache.liveKVCodec` / `cache.storedKVCodec` reading is unchanged and the 0.25.12 string table agrees; the new material here is the request-side `kvBits`/`kvMode` cluster and the batched-decode fallback messages |
| `ohyesmlx/runtimes.py:1134-1138` | "passing `--kv-cache-quantization` explicitly disables loader-level TurboQuant … neither choice is neutral" | true for both values, but the omission is no longer the loader-TurboQuant-preserving choice in 1.6.59 |

---

## 9. Where the pin would land in the harness today

Not a design, just the mapping of the evidence onto the existing `cache_state` shape, so the
follow-up order starts from facts:

| Runtime | Pin mechanism the evidence supports | `Runtime` method |
|---|---|---|
| mlx-lm | nothing to drive; `affine8`/`affine4` → `N/A`, `off` → the only state | refusal for the two codec values |
| OptiQ | `--kv-bits 8` / `--kv-bits 4` + explicit `--kv-group-size 64`; `off` = omit both | `start_command` can drive all three; no refusal needed |
| oMLX | `off` is structural (empty per-run base path); any codec value needs a written `model_settings.json` | refusal for codec values unless the scratch is written |
| Osaurus | nothing drivable from a flag; `off` is a host state to verify, not to set | refusal for every codec value, `off` only when `cache.liveKVCodec` agrees |
| vMLX | `--kv-cache-quantization none` for `off`; `q4`/`q8` only meaningful with the prefix cache on | `start_command` for all three, with a note (or refusal) about the prefix-cache prerequisite |

`report.SWEEP_PINS` (`ohyesmlx/report.py:1890`) and `SWEEP_VALUES` (`:1930`) take the pin name
and its ordered values; `PIN_FIELDS` (`:244`) and `ABSENT_PINS` (`:1338`) make an absent pin
read as "not taken" rather than as `off` — which is exactly right here, since five existing
grid columns ran with every runtime's own default and those defaults were not uniform.

---

## 10. What I did not verify

1. **Whether the harness's `mlxlm` column and the OptiQ column actually load the same mlx-lm.**
   Both venvs carry mlx-lm **0.31.3** (`~/.local/share/ohyesmlx/mlx-lm-0.31.3` and
   `/Users/jrazz/Dev/tools/mlx-optiq/.venv`), so the codec is identical either way — but
   `MlxLm.start_command` invokes a bare `python -m mlx_lm.server` (`runtimes.py:853-862`) and I
   did not resolve which interpreter that is on a run's `PATH`.
2. **Whether Osaurus's request-side `kvBits`/`kvGroupSize`/`quantizedKVStart`/`kvMode` bag is
   honoured on the OpenAI chat path.** The keys and the fallback messages exist
   (`G:100578363-100578410`); a string table cannot show whether the chat handler reads them.
   A live probe could: send `modelOptions: {"kvMode": "turboQuant(...)"}` and watch
   `convertedTurboQuantKVLayerCount`.
3. **Which Osaurus setting actually governs the live codec in 0.25.12.** `cache.liveKVCodec`
   is on disk and in the tracked-key list; `defaultKVMode` exists as a coordinator-level
   default (`G:111612128`) whose relationship to it I did not establish.
4. **Whether oMLX's TurboQuant ever engages automatically for a model.** Nothing in the
   settings or engine code sets `turboquant_kv_enabled`; I did not read `model_profiles.py`,
   which is where a per-model profile could plausibly seed it.
5. **What any of these codecs costs or saves in a cell.** Every number in
   `docs/research/2026-09-20-quantized-kv-caches.md` came from a probe script that is not the
   harness (see that paper's own caveat), and its vMLX column in particular is now explained by
   something other than what the paper concludes: its `vmlx_fp8`/`vmlx_int4` arms passed
   `--kv-cache-quantization q8`/`q4` on top of a start command that disables the prefix cache,
   which by §7.1 makes the codec inert and leaves `--kv-cache-quantization` serving only to
   disable loader-level TurboQuant. **The vMLX rows of that table should not be read as a KV
   codec comparison.**
6. **Osaurus's compiled defaults.** A string table cannot map a value to a key, so the
   effective values of absent keys (the two bit widths included) are unread from the binary.
   `osaurus config export` or `GET /admin/config/schema` would give them, given a server.

---

## 11. The table: runtime × value → how to drive it

Proposed values are used (`off` / `affine8` / `affine4`); the order's `fp8` survives only as a
retirement note. `int4` maps onto `affine4` for two runtimes, onto a *different* codec for a
third, and onto nothing for the last two.

| Runtime | `off` | `fp8` (retired) → `affine8` | `int4` → `affine4` |
|---|---|---|---|
| **mlx-lm 0.31.3** | **N/A in the sense that nothing can change it**: the server has no KV-quant surface (`server.py:1751-1886`; `make_prompt_cache` has no bit parameter, `models/cache.py:15-42`) | **N/A** — no flag, no settings key, no env var (`server.py` reads none), no per-request field. The class and the flags exist only on the client CLIs (`generate.py:192-208`, `cache_prompt.py:61-76`) | **N/A** — same evidence |
| **OptiQ 0.5.13** | omit `--kv-bits` and `--kv-config` (`cli.py:2502-2509`); no explicit off exists | `optiq serve --kv-bits 8 --kv-group-size 64` (`cli.py:2502-2504`) — affine, not fp8; installs the fused KV path unless `--no-fused-kv` (`cli.py:2730-2739`) | `optiq serve --kv-bits 4 --kv-group-size 64`; same side effects |
| **oMLX 0.6.4** | **yes, structurally**: the per-run `--base-path` scratch holds no `model_settings.json`, so `turboquant_kv_enabled` is `False` (`model_settings.py:235`, `runtimes.py:464-483`, `1014-1027`) | **N/A** — no float8 KV codec found in the model-settings surface or `turboquant_kv.py` | **not exact**: `turboquant_kv_enabled=true` + `turboquant_kv_bits=4` in the scratch's `model_settings.json`, or `PUT /api/models/{id}/settings` (`admin/routes.py:2219`) — TurboQuant, K=4/V=4, last layer skipped (`scheduler.py:3325-3345`) |
| **Osaurus 0.25.12** | **only if the host already is**: `cache.liveKVCodec = engine_selected` (`G:100592538`), verified by `check_host_state` against the committed baseline (`runtimes.py:951-969`, `osaurus_settings.py:40-41`). No flag exists in either direction | **N/A** — the affine route (`kvMode: .affine` / legacy `kvBits`) is *inert under batched decode* and falls back to float KV (`G:111612368`, `:111612192`), and no float8 codec appears in the string table | **N/A as stated** — same fallback; the drivable TurboQuant state needs `cache.liveKVCodec=turboquant` plus both bit keys, i.e. host settings, and is a codebook codec rather than int4 |
| **vMLX 1.6.59** | **yes, explicitly**: `--kv-cache-quantization none` (`cli.py:3864-3882`), the production default | `vmlx serve … --kv-cache-quantization q8 --kv-cache-group-size 64` — **but only with the prefix cache enabled** (`scheduler.py:1393-1404`, `mllm_scheduler.py:1165-1177`); the harness's default command passes `--disable-prefix-cache` (`runtimes.py:1161-1163`, `cli.py:2639`), which makes it a logged no-op | `--kv-cache-quantization q4` — same gate, same condition |

---

## Update 2026-09-25: the pin this document mapped has landed

§9 was written as a mapping "so the follow-up order starts from facts", and it is now the code
rather than a plan: `runtimes.KV_QUANTS` holds the three codec names (with the `fp8` rationale at
its definition), each runtime's `kv_quant_refusal` carries the reason §3–§7 gave it, and
`measure._visit` asks that refusal before anything is started, so a cell a runtime cannot be
driven into is `N/A` with its reason instead of a number published under a pin it does not hold.
`report.SWEEP_PINS` and `report.SWEEP_VALUES` carry `kv_quant` with `off` before the codecs, and
`f998dcd` (2026-09-25) made the joined tables print that `N/A` state as `N/A` rather than as the
`—` a combination nobody ran gets (`report.ENTRY_LEGEND`). The live result of the mapping — one
runtime with a readable codec column, and the other four refusing it with the reasons recorded
here — is `docs/research/2026-09-25-kv-quant-sweep.md`.
