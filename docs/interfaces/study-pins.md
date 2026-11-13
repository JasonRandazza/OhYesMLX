# Study pins — interface shapes

The Phase 4 studies' pinned variables: KV quantization, MTP depth, expert streaming, and multi-turn as a fixed workload.

## Phase 4 study 03-05 — the KV-quantization pin

The second cache pin, one cache down from 06-02: which **codec** a runtime's KV cache is held in,
rather than whether prefix/KV reuse happens at all. Same shape as that pin — one run drives every
cell in it into one codec, so it is a header pin a sweep varies and never an axis or a cell
property.

```
ohyesmlx run ... --kv-quant {off,affine8,affine4}
ohyesmlx sweep <off-run-dir> <affine8-run-dir> --varying kv_quant --rank ttft_p50_s
```

**The values name the codec, not the width, and that is the whole point of them.**

| value | means |
|---|---|
| `off` | no KV quantization: the runtime's own native, full-precision cache |
| `affine8` | MLX's affine codec, 8-bit, group size pinned in the command |
| `affine4` | the same, 4-bit |

**`fp8` is not one of them and must not come back as a spelling of `affine8`.** Nothing in this
set has an FP8 (E4M3/E5M2) KV codec: "8-bit" here is `mx.quantize`'s default `affine` mode — a
signed integer code plus a per-group float scale and bias — which has no exponent and does not
share FP8's error profile. The earlier study's "FP8" arms were this codec, and naming them float8
was false about what ran. A genuine float8 codec gets its own value and its own column on the day
one appears, because it would not be comparable with `affine8`. `int4`/`int8` are not used either:
they are true of this affine path and false of the TurboQuant codebook codecs two of these
runtimes carry, and a codec a runtime cannot deliver is `N/A` with a reason rather than
approximated into a neighbour. The group size is a second variable and is pinned in the command
rather than inherited.

The definitions are `runtimes.KV_QUANTS` (the values, and that rationale, written once) and the
evidence is `docs/research/2026-09-24-kv-quant-surface.md` — §2.3 for the names, §9 and §11 for
the per-runtime mapping. It is not restated here.

**The header pin.**

```python
"kv_quant": "off" | "affine8" | "affine4" | None     # None: the pin was not taken
```

`PIN_FIELDS` and `ABSENT_PINS` gained it exactly as they gained `cache_state`, and for the same
reason: `None` is not a fourth value and not a synonym for `"off"`. Every run measured before the
pin existed ran each runtime's own codec — and those were not uniform, since `off` is the absence
of two flags on OptiQ, a settings field nobody wrote on oMLX, and a host setting on Osaurus — so
reading the absence as `off` would fold different codecs into one column. Without the flag every
start command is **byte-identical to today**, checked against recorded literals for all five
runtimes rather than re-derived.

**The mechanism, per runtime.** `off` is the runtime's own full-precision cache, and a codec value
is driven only where a start flag exists for it:

| runtime | `off` | `affine8` / `affine4` |
|---|---|---|
| mlx-lm 0.31.3 | accepted, no flag — it is the only state the server can hold | **refused**: no flag in the server's argv, no environment variable, no settings file, no per-request field, and `make_prompt_cache` takes no bit width (`server.py:1751-1886`, `:971`, `models/cache.py:15-42`). The codec is real but wired into the client CLIs only (`generate.py:192-208`, `cache_prompt.py:61-76`) |
| OptiQ 0.5.13 | accepted, no flag — neither `--kv-bits` nor `--kv-config`, which is the production default (`cli.py:2332-2347`) | **driven**: `--kv-bits 8` / `--kv-bits 4`, each with `--kv-group-size 64` pinned (`cli.py:2502-2504`). Enabling it also installs OptiQ's fused streaming-KV path unless `--no-fused-kv` is passed (`cli.py:2729-2739`) — the runtime as shipped, deliberately not moved by this pin, and the reason an affine cell there is not stock-mlx-lm-with-a-quantized-cache |
| oMLX 0.6.4 | accepted, no flag, and structural: the per-run `--base-path` scratch holds no `model_settings.json`, so `turboquant_kv_enabled` is `False` (`model_settings.py:235`, `:433-435`) | **refused**: oMLX's codec is TurboQuant, a codebook codec that derives `key_bits = floor` / `value_bits = ceil` (`turboquant_kv.py:70-92`), not affine; and it is a per-model settings field with no start-command surface (`grep turboquant omlx/cli.py` is empty) |
| Osaurus 0.25.12 | accepted only when the host's `cache.liveKVCodec` is `engine_selected` — the same read-the-key-and-refuse shape as `cache.prefix.enabled` | **refused**: no flag exists in either direction, the affine route (`kvMode: .affine` / legacy `kvBits`) is inert under batched decode and falls back to float KV, and the route that works while batching is TurboQuant, needing both widths explicitly |
| vMLX 1.6.59 | accepted and **driven**: `--kv-cache-quantization none`, the flag's own explicit off (`cli.py:3864-3882`) | **refused**: the codec quantizes only the prefix cache's stored copy and generation stays full precision (`scheduler.py:2444-2458`), and it is a no-op under this harness's `--disable-prefix-cache` (`scheduler.py:1393-1404`) |

**A codec a runtime cannot be driven into is `N/A` with the reason**, through the same path the
cache pin uses: the runtime is asked (`Runtime.kv_quant_refusal`) where
`Runtime.cache_state_refusal` is asked, *before* anything is started, and `_visit` returns
`"skip"` so no later visit retries it. The reason names the evidence, because what would have to
change is the runtime or the host and not this run.

**`render_sweep` gains `varying="kv_quant"`.** `SWEEP_VALUES` orders it `off` before `affine8`
before `affine4`: the baseline column first, then the codecs in `KV_QUANTS`' order. Like the
cache pin — and unlike the prompt-length pin — it relaxes nothing: its columns are meant to answer
the same prompt under one codec and then another, so two runs whose prompts differ are refused
like any other grid. What a column does not carry is each runtime's own side effects of reaching
the codec — the same class of caveat as OptiQ's fused path above — and those are named beside the
values, in `runtimes.KV_QUANTS` and in each runtime's refusal, rather than in the table.

## Phase 4 studies 03-06, 03-03 — the MTP-depth and expert-streaming pins

Two more header pins, one decode-side and one load-side, built exactly like the three before
them (`kv_quant` above is the template): a header field, `<pin>_refusal` asked before anything
is started, `PIN_FIELDS`/`ABSENT_PINS`/`SWEEP_PINS`/`SWEEP_VALUES`, and a CLI flag with
`choices`. Absent is `None` for both and leaves every start command **byte-identical to
today**, checked against recorded literals for all five runtimes.

Each of the two carries a **second question the three above do not have**, and both are the
same defect: the runtime accepts the flag and does something else. So a state one of these pins
claims is not taken from the command line alone — a depth is decided from the artifact on disk
before the start, and `on` is decided from the server's own log after it. A depth also has a log
half, on the one runtime whose engine is built later than its start: see "`mtp_depth`'s log
half, on OptiQ" below.

### `mtp_depth` — the native-MTP draft depth

```
ohyesmlx run ... --mtp-depth {off,1,2,3}
ohyesmlx sweep <off-run-dir> <3-run-dir> --varying mtp_depth --rank decode_tps
```

| value | means |
|---|---|
| `off` | MTP not running: the runtime's own kill switch, or the state its own default is already in |
| `1` / `2` / `3` | that many draft tokens per verify cycle, under the **fixed** policy |

**The policy is part of the value, not a second pin.** vMLX's default is `adaptive`, which
"may also lower the depth on measured acceptance and tries depth 1 once against the configured
depth's measured cost, keeping the measured winner" (`cli.py:4324-4331`): depth can change
*inside one request*, and a cell measured under it is not a cell at depth N. Every depth is
therefore passed as `--native-mtp-depth N --native-mtp-depth-policy fixed`. The values are
strings — one word beside three numbers — and the ceiling is vMLX's own (1..3 by default,
`cli.py:1668-1678`). The definitions are `runtimes.MTP_DEPTHS`, written once. OptiQ needs no
equivalent pin: its cycle takes `cycle_K = depth` once and holds it for the whole call, the
HuggingFace-style dynamic-depth adapter having measured 4-17% slower and been removed
(`optiq/runtime/engine.py:897-905`, `:920`).

**A depth is only MTP if the artifact says so, on both runtimes that drive one — and the two
fail differently.** vMLX does not fail at all: `--native-mtp-depth` is accepted on a bundle with
no MTP heads, the load succeeds, every request is answered, and the decode is plain
autoregressive — with the startup banner suppressed altogether for a `not_configured` bundle
(`cli.py:2441`) and the INFO line that would explain an inactive draft head conditional on the
bundle having declared one (`native_mtp.py:1307-1316`). vMLX's own source records that exact
failure as measured (`native_mtp.py:1296-1303`): "A bundle that DECLARES MTP but is not
runtime-supported used to deactivate in total silence, so the model ran plain autoregressive
with nothing in the log to say why. MEASURED: Nemotron 3.5 Lightning (JANG_2L/4M/6M, 34
mtp.layers.0.* tensors, num_nextn_predict_layers=1) and Inkling both hit this." OptiQ fails
loudly but late: with `--mtp` and no attachable head it builds an engine without a draft head,
warns once, and then answers each request as HTTP 404 (`optiq/serve.py:459-464`,
`engine.py:297-304`, `mlx_lm/server.py:1424-1427`) — a per-request failure that costs a full
model load first.

So `Runtime.mtp_depth_refusal` is handed the **cell's artifact directory** (the one place this
pin's refusal departs from the three above) and decides from the files, through
`runtimes.vmlx_mtp_refusal` and `runtimes.optiq_mtp_refusal`. For vMLX: the family must be one
vMLX wires (`native_mtp.py:64-79`), the bundle must not declare MTP dropped (`:883-925`), the
config must declare at least one MTP layer (`:538-546`), and the safetensors index must carry
`mtp.*` tensors (`:606-611`). **Both halves of the declaration are required**, because each has
its own failure in vMLX's source: a config that expects MTP over an index with no tensors reads
`metadata_inconsistent` (`:983-986`), and tensors under a config that disables MTP read the same
(`:987-988`). For OptiQ: the config must declare at least one MTP layer
(`optiq/runtime/mtp/mtp_patch.py:69-76`, whose zero sends the injector home at `:382-385`),
the head file must be where its resolver looks (`mtp/artifacts.py:104-115` — the path the
config names under `mlx_lm_extra_tensors.mtp_file` first, then the four published
spellings), and the head's tensors must fit the block that artifact's own config says OptiQ
will build (`runtimes._optiq_head_packing_refusal`): a head the config declares
prequantized is refused when a weight has no `.scales`/`.biases` pair, when the pair's two
axes disagree about the input dimension, or when its routed experts are in the fused HF
layout `_split_fused_experts` rewrites into weights without their scales. The accepted cases
are on this host — `models--JANGQ-AI--Qwen3.5-4B-JANG_4S` declares one layer in
`text_config.mtp_num_hidden_layers`, indexes 31 `mtp.layers.0.*` tensors, stamps family
`qwen3_5`, and its recorded start log carries `Qwen3.5/3.6 MTP model adapter applied`
(`results/logs/vmlx-20260924T032906-11424.log:38`); both OptiQ quants name
`optiq/mtp.safetensors` in `mlx_lm_extra_tensors.mtp_file` and declare
`mtp_num_hidden_layers: 1` — two of the three conditions, not all three. The 4B passes the
third and the 35B does not: its head is prequantized and its routed experts are fused, so
`Qwen3.6-35B-A3B-OptiQ-4bit` is `N/A` before a runtime starts
(`docs/research/2026-09-25-mtp-depth-sweep.md` §4, open question 6).

| runtime | `off` | `1` / `2` / `3` |
|---|---|---|
| vMLX 1.6.59 | accepted, and it is the command of today: `--disable-native-mtp` sets `VMLINUX_NATIVE_MTP=0` and clears any depth the environment left behind (`cli.py:1662-1667`) | **driven**, then decided from the artifact: `--native-mtp-depth N --native-mtp-depth-policy fixed` on a bundle whose MTP heads vMLX will wire, and `N/A` with the check that failed on one whose heads it will not |
| OptiQ 0.5.13 | accepted, no flag change: `--mtp` is `is_flag=True, default=False` (`optiq/cli.py:2554-2558`), so a command without the pair is a command that never drafts | **driven**, then decided twice: `--mtp --mtp-depth N` on an artifact whose head passes `optiq_mtp_refusal`'s three checks — declared layer, resolvable file, tensors that fit the block its config builds — and `FAIL` quoting the log if the engine's own ready line at the pinned depth does not appear (below) |
| mlx-lm 0.31.3 | accepted, no flag — the only state the server has: its 23 options include none for MTP, the string `mtp` does not occur in `server.py`, and its model code drops the head's weights at load (`models/qwen3_5.py:313`) | **refused**: no MTP exists in the server for a depth to apply to |
| oMLX 0.6.4 | accepted, no flag, and structural: the per-run `--base-path` scratch holds no `model_settings.json`, so `mtp_enabled` is `False` (`model_settings.py:303`) | **refused**: `mtp_num_draft_tokens` is a per-model settings field with no flag, and it is adaptive even when set (`model_settings.py:304-308`) |
| Osaurus 0.25.12 | accepted only when the host's `mtp.mode` is `force_off` — read through the tracked key the drift gate already records | **refused**: the depth is the host setting `mtp.explicitDepth`, which "must be 1, 2, or 3" (docs/runtimes/osaurus.md:344), with no start-command surface |

### `mtp_depth`'s second half, on OptiQ, vMLX and MTPLX

The streaming pin is not the only one whose state is settled after the start, and on the two
runtimes below it is settled by the server's own log. OptiQ
echoes `--mtp --mtp-depth N` at startup, but the engine that echo names is created on the
**first request** (`optiq/serve.py:443-471`, reached from the patched `stream_generate`), so the
line that says a draft head is really driving the decode —
`[optiq.serve] MTP engine ready (depth=N).`, `serve.py:465` — cannot exist before one has been
made. `Runtime.mtp_depth_missing` is therefore asked **after the visit's measured requests have
answered**, and it is the same verdict the streaming check gives: `FAIL` with the log quoted,
kept on the row's own start facts, and not retried on a later visit.

The required line carries the pinned depth — `serve.py:465` interpolates it — so a cell that
asked for 3 and got an engine built at 2 is a `FAIL` rather than a number published under a
depth the decode did not hold. The fallback lines are the engine's own warning that it attached
without a head (`engine.py:297-304`); the `HTTP 404` that follows is answered to the client and
never logged, so the warning is what the log holds. A window holding neither the required line
nor a fallback marker is read once more for a traceback, and the message then quotes that
traceback's exception line and its innermost frame rather than claiming the log says nothing —
the 4B's depth cells carried no ready line and no attach warning and held a `TypeError` at
`engine.py:760`, which is the case `docs/research/2026-09-25-mtp-depth-sweep.md` §4 /
open question 5 asked for; a window with no traceback either says the log "prints no line this
check reads" (`runtimes._banner_evidence`, `_traceback_cause`). The evidence window is the log
head (`LOG_HEAD_BYTES`), the same one the streaming banner is read from.

vMLX answers it too (2026-09-25). A vMLX depth cell carries `env VMLX_NATIVE_MTP_AR_SAFETY=0
VMLX_NATIVE_MTP_AR_REENTRY=0` in front of `vmlx serve` (`runtimes.VMLX_MTP_FIXED_ENV`), because
`--native-mtp-depth-policy fixed` alone leaves the AR-safety valve and the sticky start rung
moving depth. Its evidence is per request, so its window is the **whole log**
(`runtimes._read_log_all`): depth N>1 is `FAIL` on any `finish=fallback_to_ar` or
`start rung D<k>` with k<N, and every depth is `FAIL` without one `accept_by_depth` row whose
`d<N>` denominator is non-zero. `Vmlx.mtp_depth_missing` holds the source citations.

MTPLX answers it from the responses themselves (v4.0), which is why `Runtime.mtp_depth_missing`
is handed the visit's measured `observations` and the cell's `artifact_dir`: its depth flags are
accepted on an artifact whose heads it cannot wire and it answers HTTP 200 with coherent text in
plain autoregressive decode, so the files decide nothing and the receipt decides everything —
every measured request of the visit must carry the final chunk's `mtplx_stats` with `mode` not
`"ar"`, `draft_head_installed` true and a positive `drafted_tokens`, and one that does not is
`FAIL` with the artifact named (`runtimes.mtplx_mtp_refusal`). A receipt that is absent is that
same `FAIL` rather than a pass: an absent receipt is not evidence that a head drafted. Measured
2026-10-09: both OptiQ packs draft 67 tokens at depth 1, `uingei/Qwen3.5-4B-oQ4e` loads and
answers with `mode` `"ar"` and `drafted_tokens` 0, and `JANGQ-AI/Qwen3.5-4B-JANG_4S` exits 1 at
the model-load step before any port binds (`docs/research/2026-10-09-mtplx-load-probes.md`).

### `stream_experts` — experts from SSD, or resident

```
ohyesmlx run ... --stream-experts {off,on}
ohyesmlx sweep <off-run-dir> <on-run-dir> --varying stream_experts --rank decode_tps
```

`on` means the runtime is streaming MoE expert weights from SSD on demand instead of holding
the fused expert tensors resident. `off` is not the absence of a flag on two of the five — it
is a flag that must be passed: OptiQ's own default is `auto`, which streams a MoE the moment
its weights exceed 0.70 of total RAM (`optiq/runtime/moe_stream.py:621-634`), and that is why
this harness has passed `--no-stream-experts` since long before the pin existed. `auto` is not
a value of this pin, because taking that decision away from the runtime is what the pin is for.

**A flag is not evidence that anything streamed, so the log is.** Both runtimes that accept the
flag fall back to a resident load without failing anything: OptiQ when the model is not one it
recognises as streamable (`optiq/serve.py:1641-1643`, the fall-through its own source documents
against itself at `moe_stream.py:344-352`) and when a streaming attempt raises
(`serve.py:1688-1692`); vMLX when the model has no MoE layers (`server.py:8981-8982`), when the
bundle is JANGTQ (`:8964-8973`), and when the patch applies to nothing or raises (`:9003-9008`).
So `Runtime.stream_experts_missing` is asked **after the start and before the first request**,
over `Handle.log_path`, and an `on` cell whose log does not show it is `FAIL` with that log
quoted — never a number published under a pin it does not hold. It is not retried on the next
visit: the answer is a property of the model and the flag, so a second start would buy the same
log and one more model load.

The evidence, per runtime: OptiQ needs **both** `[optiq.serve] SSD expert streaming: on`, which
is printed only when the mode is not `off` (`optiq/cli.py:3095-3101`), **and**
`[optiq.serve] SSD expert streaming: pre-loaded <path>`, which is printed only when the model
was really built through `load_streaming` (`serve.py:1654-1662`) — the banner alone is printed
before the model is inspected. vMLX needs `Flash MoE enabled: <n> layers patched`, which is
printed only when layers were patched (`server.py:8996-9002`), and it is in the log before the
runtime answers: the patching is applied at the readiness barrier, ahead of the yield that opens
the port (`server.py:6176-6177`, `:6199`).

| runtime | `off` | `on` |
|---|---|---|
| OptiQ 0.5.13 | accepted, no flag change: `--no-stream-experts` is a complete opt-out — `mode == "off"` returns before anything is installed (`optiq/serve.py:1629-1630`) | **driven**, then read from the log: `--stream-experts` plus both banner lines, and `FAIL` quoting the log otherwise |
| vMLX 1.6.59 | accepted, no flag — `--flash-moe` is `default=False` (`vmlx_engine/cli.py:3966`; `FlashMoEConfig.enabled: bool = False`, `flash_moe_config.py:29`) | **driven**, then read from the log: `--flash-moe` plus `Flash MoE enabled:` |
| mlx-lm 0.31.3 | accepted, no flag — there is no expert-loading path in the server at all (`expert` does not occur in `server.py`) | **refused**: the streaming loader is OptiQ's, patched onto this server from the outside |
| oMLX 0.6.4 | accepted, no flag — no option in `omlx/cli.py` names experts and no module in the package mentions expert streaming | **refused**: the mechanism that resembles it, burst decode (`server.burst_decode_mode` → `OMLX_DECODE_BURST_*`, `settings.py:148-162`), sets how many decode steps are coalesced before a delta is emitted — docs/runtimes/omlx.md:510-572 — not where expert weights live |
| Osaurus 0.25.12 | accepted only when the host's `concurrency.smeltMode` is `disabled` — not a tracked key, so read by `runtimes.osaurus_smelt_mode` | **refused**: `flashMoE` and `ssdStreaming` are values of that host setting (docs/runtimes/osaurus.md:298), with no start-command flag in either direction |

**`render_sweep` gains both.** `SWEEP_VALUES` orders `mtp_depth` `off` before `1` before `2`
before `3`, and `stream_experts` `off` before `on`: the baseline column first, as the cache and
codec sweeps read. Neither relaxes anything — the same prompt answered at one depth and then
another, or resident and then streamed — so two runs whose prompts differ are refused like any
other grid.

## Phase 4 study 03-04 — multi-turn as fixed workloads

The multi-turn study's probe (`scripts/probe_multiturn_sweep.py`) measured the same ten
questions in one run per runtime, feeding **each runtime's own replies** back into the next
turn. Every runtime therefore saw a different history, and a difference between two runtimes at
turn N could belong to the reply text as easily as to the runtime: two things varying at once.
Re-running it through the harness means the conversation has to be something the harness pins.

```
ohyesmlx run ... --workloads {pinned,multiturn}
```

```python
# cli.py
def multiturn_workloads(measure) -> list: ...
# ten Workloads, `turn-01`…`turn-10`, each at `chat`'s 128-token cap
```

**The workload set is a selector, not a pin** — the same shape as `--prompt-tokens`, one level
up. `pinned` is the default and is the three shapes above, byte-identical. `multiturn` is ten
workloads: turn N's `messages` are the first N questions and the N−1 replies between them,
ending on question N, so turn N's prompt is turn N−1's with one exchange appended. The
accumulating history is the thing under study and the output cap is not allowed to move with it,
which is why all ten carry `chat`'s 128 rather than the probe's 64.

**Nothing new is in the header, because the header already carries it.** A run records every
workload it measured with its own `messages` and `max_tokens` (`write_jsonl`), so the set that
ran is provenance as it stands and a name for it would be a second copy of the same fact. It
also means the join guards already cover it: guard 1 compares two headers' workload sets by id
and by prompt, so a `pinned` run and a `multiturn` run are refused a shared table rather than
merged, and so are two `multiturn` runs measured from different literals.

**The replies are literals, and that is the fix.** `cli.DIALOGUE` holds the ten questions of the
probe's `DIALOGUE_TURNS` and nine short neutral replies between them. A probe that fed the model
its own text gave turn N a different prompt on every runtime; a fixed reply makes turn N the
same prompt everywhere, which is what makes one runtime's turns comparable with another's — and
it is the only way a `turn-07` figure across two columns is about one request.

**`--workloads` and `--prompt-tokens` are mutually exclusive** in argparse. The prompt-length
pin measures its own single sized `prefill` shape and says so in its own header field, so a run
that named both would be a run that measured one of them with no record of which.


