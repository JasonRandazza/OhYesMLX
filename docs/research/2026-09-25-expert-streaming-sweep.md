# Expert streaming at 35B: a 9× decode cost, and vMLX's streaming arm fails coherence

**Date:** 2026-09-25 (runs 07:00 → 09:14 EDT)
**Study:** v3.1 Phase 4, plan 03-03 (expert streaming under high memory pressure) — the
harness-driven re-run of the study whose probe script is `scripts/probe_expert_streaming_35b.py`
**Harness:** 0.3.0, `source_sha256 a8ad60e7f76e13c5f2c4b7eaa686989abc60ff2cab5809999f7873ff6ed5c9c1`,
identical in all four run directories
**Runner:** `scripts/run_sweep_streaming.sh` → `results/sweep-streaming/sweep.md`
**Subject:** `mlx-community/Qwen3.6-35B-A3B-4bit` (19.03 GiB safetensors; 20,429,169,720 bytes on
disk including sidecars, identical in every run), one cell per run
**Author:** Claude Opus coordinator

## Why this run exists

Plan 03-03 asked whether SSD expert streaming lets a 256-expert, 40-layer MoE serve on a machine
that cannot hold it, and what serving through the disk costs. Its evidence was a probe script; the
harness `stream_experts` pin turns the same question into a single-variable sweep with the raw
rows kept, and with one extra rule the probe did not have: **`on` is only `on` if the runtime's own
log says so** (`runtimes.STREAM_EXPERTS`, `Runtime.stream_experts_missing`). Both runtimes accept
the flag on a model they cannot stream and fall back to a resident load with a log line and no
error (OptiQ `serve.py:1641-1643`, vMLX `server.py:8996-9002`), so a cell whose log does not show
streaming is FAIL with that line quoted rather than a speed number.

Two runtimes in the set accept the flag at all — OptiQ's `--stream-experts` and vMLX's
`--flash-moe`; the other three refuse `on` (mlx-lm has no expert path, oMLX's DSL surface is burst
decode rather than expert streaming, and Osaurus's `concurrency.smeltMode` is host state the
harness does not edit). So the sweep has two cells, each with a two-value column.

## What ran

| cell | `off` run directory | `off` wall clock | `on` run directory | `on` wall clock | version |
|---|---|---|---|---|---|
| `stock4bit__optiq` | `20260925T110053Z-format` | 07:00:53 → 07:07:21 | `20260925T110732Z-format` | 07:07:32 → 07:48:51 | 0.5.13 |
| `stock4bit__vmlx` | `20260925T130741Z-format` | 09:07:41 → 09:14:19 | `20260925T114902Z-format` | 07:49:02 → 09:07:30 | 1.6.59 |

(The `on`/`off` order alternates per runtime — OptiQ `off` then `on`, vMLX `on` then `off` — so a
monotone thermal trend does not read as the pin's effect.)

**Pins every run shared**, from the sweep's own shared-pins line: temperature `0.0`, seed `0`,
warmup `{cap: 20, floor: 10, mode: plateau, plateau_pct: 3.0, window: 5}`, measured `9`,
cooldown `30.0` s, concurrency `1`, and `prompt_tokens`, `cache_state`, `kv_quant`, `mtp_depth`
all not taken. Workloads: `chat` (max_tokens 128), `prefill` (64) and `decode` (512), whose
messages are identical across the four runs; the servers' own prompt counts are 36/1321/36 on
OptiQ and 29/1314/29 on vMLX for the same text, because each tokenizer counts its own way.

**The `on` state is logged, not assumed.** OptiQ's log for the `on` cell
(`results/logs/optiq-20260925T070732-42053.log`) carries `[optiq.serve] SSD expert streaming: on`
and `[optiq.serve] SSD expert streaming: pre-loaded /Users/…/models--mlx-community--Qwen3.6-35B-A3B-4bit/…`.
vMLX's (`results/logs/vmlx-20260925T074902-74580.log`, lines 55–58) carries:

```
INFO:vmlx_engine.utils.smelt_loader:ExpertIndex built: 40 MoE layers, 256 experts/layer, expert=18.12GB backbone=2.28GB
INFO:vmlx_engine.models.flash_moe_integration:Flash MoE: patched 40 MoE layers
INFO:vmlx_engine.models.flash_moe_integration:Flash MoE: freed ~18.12 GB expert weights
INFO:vmlx_engine.server:Flash MoE enabled: 40 layers patched, 18.12 GB freed, slot bank=256, io_workers=4
```

So both `on` cells are streaming in fact, and both `off` cells are the runtimes' resident paths:
OptiQ's `--no-stream-experts` (its own default is `auto`, which would stream anything over 0.70 of
RAM) and vMLX's default, with no `--flash-moe`.

**Each cell is visited twice, forwards then backwards** (`measure.visit_plan`), with the nine
measured requests split across the two visits; the drift figure compares the two halves of the
window and a row's memory reading is the visit whose sampled peak was higher
(`measure._highest_peak`). Both visits' requests are in that run's observations.

## Results

### 1. OptiQ: streaming costs about 9× decode and about 15 GB of resident memory

**Axis — `stream_experts`, runtime, artifact and every other pin held constant.** Both columns are
one cell of one runtime, timed on the same channel (`content`, 9 of 9 measured requests in all six
of its cells). **Caveat — what this cannot read:** it is the cost of the on-state on a host that
does not need it; nothing here says what the same weights would do on a machine that cannot hold
them, and the `off` column is OptiQ's own resident path rather than a control for another runtime.

| workload | decode tok/s `off` → `on` | ITL ms `off` → `on` | TTFT p50 s `off` → `on` | E2E p50 s `off` → `on` | peak MB `off` → `on` | vmmap footprint MB `off` → `on` |
|---|---|---|---|---|---|---|
| `chat` (128) | 84.38 → **9.32** | 11.94 → 108.13 | 0.281 → 1.447 | 1.797 → 15.169 | 25600 → 4565 | 19046.4 → 3788.8 |
| `prefill` (64) | 90.27 → **9.59** | 11.35 → 106.41 | 2.057 → 6.712 | 2.544 → 12.036 | 20480 → 6136 | 19148.8 → 4198.4 |
| `decode` (512) | 77.71 → **9.25** | 12.89 → 108.31 | 0.292 → 1.461 | 6.883 → 56.782 | 19456 → 5115 | 19251.2 → 4300.8 |

Every cell is `PASS` and every measured request in both columns produced coherent English.

- **The decode cost is −89% on `chat`, −89% on `prefill` and −88% on `decode`** — one number,
  ~9.3 tok/s, regardless of the workload's cap (128, 64 or 512 tokens) and regardless of the prompt
  length (36 tokens or 1321). That is the signature of a per-generated-token cost, not a
  per-prompt one: 320 expert slices per token across 40 layers, read from SSD on every step. The
  0.11 s per token (ITL 106–108 ms) is the disk's latency, not the model's arithmetic.
- **TTFT rises 3.3×–5.2×** (0.281 → 1.447 s, 2.057 → 6.712 s, 0.292 → 1.461 s): the `on` path
  streams the prompt's expert reads too, and the `prefill` workload's 1321-token prompt pays the
  most in absolute terms while the two short-prompt workloads pay the largest multiple.
- **The resident memory drops by about 15 GB.** The finer end-of-window `vmmap` reading falls
  19046.4 → 3788.8, 19148.8 → 4198.4 and 19251.2 → 4300.8 MB — 14.6–14.9 GB, or **−78% to −80%**.
  The harness's sampled peak falls 25600 → 4565 MB (`chat`), 20480 → 6136 MB (`prefill`) and
  19456 → 5115 MB (`decode`) — −70% to −82%, a wider band because that instrument is a maximum
  over the workload's own windows and the cell's first visit began with the process load. The
  design's H1 predicted 3.5–5.0 GB, and all three `vmmap` readings land inside it
  (3.79, 4.20, 4.30 GB); the sampled peak runs to 6.14 GB on `prefill`.
- **Cold load and the first request both grow** (cold 3.26 → 5.16 s; the cold visit's first
  request 10.12 → 15.25 s). The `off` cell's first request is +8.32 s over the median of the
  requests its workload went on to measure and its row carries the deferred-load note; the `on`
  cell's is 0.08 s above its own workload's median of 15.17 s, and carries no note — because in
  the streaming state every request is slow, so the first one is not the outlier (the note fires
  at +1 s).

### 2. vMLX: the `on` cell streams, and does not produce language

**Axis — `stream_experts`, runtime held constant.** Same cell, same channel (`reasoning`, 9 of 9
in all six cells). **Caveat:** the coherence gate is a floor — this says the cell produced no
language, and nothing about whether an answer would have been right.

| workload | decode tok/s `off` → `on` | status `on` | coherence verdict, `on` (per request) | peak MB `off` → `on` | TTFT p50 s `off` → `on` |
|---|---|---|---|---|---|
| `chat` | 77.00 → 4.96 | **FAIL** | `replacement characters`, 9 of 9 | 20480 → 3525 | 0.199 → 3.895 |
| `prefill` | 74.98 → 4.97 | **FAIL** | `implausible words`, 9 of 9 | 21504 → 4536 | 2.059 → 10.581 |
| `decode` | 73.93 → 4.94 | **FAIL** | `replacement characters`, 9 of 9 | 20480 → 3352 | 0.205 → 3.892 |

The `off` column produced coherent language on all 27 measured requests; the `on` column failed on
all 27. The first measured request of the `chat` cell (`results/sweep-streaming/stock4bit__vmlx/20260925T114902Z-format`,
observation 1, 128 completion tokens, all of them in the reasoning channel) begins:

> `onsel遥 desiredazgo终身itechakanyonspurIss年头归母 clos夏令erti folidor GenttroOLA Querнк狈eteriaicarbonyechraリック起手五味lixkund foreseeable majorityOwnershipcé具有较高的 mixedτερabinadle.Lang_attacheddessliderekhuerta<|box_end|>ZFOLONocratindsight…`

and later contains `öre��` — the replacement character the gate reports. The `decode` cell's first
request is the same salad; the `prefill` cell's is judged on its word shapes rather than on a
replacement character.

So the `on` state in vMLX is a measured FAIL, not a missing measurement: the banner above says the
layers were patched and 18.12 GB of expert weights were freed, the port answered, 128/64/512 tokens
came back at 4.9 tok/s, and the text is token salad. **The speed is not a result.** Under the
project's first rule, a fast cell that emits garbage is a failed cell, and this cell is not even
fast: 4.94–4.97 tok/s is below OptiQ's 9.3 with the same weights on the same disk, and below the
7–11 tok/s the design predicted for it.

Two things about the memory reading in this cell, because they look contradictory and are not:

- The harness's sampled peak (3525/4536/3352 MB) and the end-of-window `vmmap` footprint
  (3481.6/3276.8/3174.4 MB) both show ~3.2–4.5 GB.
- The same rows' `vmmap` **lifetime** peak is 20582.4 MB on all three workloads — the resident
  load of the full 19.03 GiB artifact, which vMLX performs before the readiness barrier patches the
  MoE blocks and frees the experts. The sampler's window opens with the workload, after the port
  is open, so it never sees that transient; `vmmap`'s lifetime peak does. The `off` cells read
  20275.2 MB on the `vmmap` footprint and 20480–21504 MB on the sampled peak, with a lifetime peak
  of 20684.8–21196.8 MB.

### 3. Where the results answer the design (plan 03-03, H1–H5, cells C1–C6)

The design's cells map onto this sweep as: C1 = OptiQ resident (`off`), C2 = OptiQ streaming
(`on`), C4 = vMLX resident (`off`), C5 = vMLX FlashMoE (`on`). **C3 (OptiQ
`--stream-experts-cache 64`) and C6 (vMLX `--smelt --smelt-experts 50`) were not run**: the
`stream_experts` pin has two values and neither is a cache arm, and Smelt is a different mechanism
from the pin. Two flag differences from the design's own table are worth naming: this run's vMLX
command passes `--no-jit` and `--disable-native-mtp` (the first is the harness default with
`OHYESMLX_VMLX_ENABLE_JIT` unset, the second follows from the depth pin not being taken), and it
passes no `--flash-moe-slot-bank`, so the banner's `slot bank=256` is vMLX's own default rather
than the design's 64.

- **H1, 75–80% footprint reduction to ~3.5–5.0 GB: confirmed for OptiQ.** −80%/−78%/−78% on the
  `vmmap` footprint, and the absolute levels (3.79, 4.20, 4.30 GB) sit in the predicted band. The
  same reduction in vMLX's `on` cell is real on the sampled peak but arrives with text that is not
  language, so the memory half of its H1 cannot be read as a serving option.
- **H2, decode collapse to 6–10 tok/s: confirmed for OptiQ at 9.25–9.59.** The design's band was
  right for this runtime to within a few percent. vMLX's `on` cell is below the band at 4.94–4.97
  and is a FAIL, so its number is not a decode rate in any publishable sense.
- **H3, in-RAM expert caches are near-useless (<15% hit, <5% gain): not tested.** No arm in this
  sweep carries a cache; the pin has no cache value, and adding one would be a second mechanism.
- **H4, FlashMoE preserves coherence at the cost of throughput: refuted on both halves.** The
  design expected `--flash-moe` to be "bit-exact PASS" and 7–11 tok/s; it produced token salad on
  27 of 27 measured requests at 4.94–4.97 tok/s. The runtime's log shows the patched state, so this
  is not a silent fallback to a resident load — the streamed state itself produced the salad.
- **H5, the `auto` threshold on `model_disk_bytes > 0.70 × total_RAM`: not tested, by design.**
  This run pins the flag explicitly in both states, which is the mitigation AGENTS.md records for
  that hazard; on this 64 GB host the threshold is 44.8 GB against a 19.03 GiB model, so `auto`
  would never engage. The interesting version of H5 — a constrained host where it does — is not
  this machine.
- **The design's *levels* for the resident controls were low.** C1 was expected at 56–58 tok/s and
  C4 at 61–63; measured, OptiQ resident reads 77.7–90.3 and vMLX resident 73.9–77.0. The 2026-09-24
  hardening paper already found 35B levels moving 8–27% between nights without a formula change; the
  same caution applies to any comparison against the 2026-09-20 probe numbers.

## Open questions

1. **Is the vMLX FlashMoE failure a property of this artifact, this runtime version, the slot-bank
   default, or the harness's command?** The record shows `slot bank=256` (vMLX's default) and
   `io_workers=4`; the design called for a 64-slot bank. A slot-bank arm and a second model would
   separate "vMLX cannot stream this MoE" from "vMLX cannot stream".
2. **Should the harness try Smelt (C6)?** It is the design's other memory-reduction route in vMLX,
   and this sweep's result gives a reason to test it: the streaming route did not produce language.
3. **What does the 9.3 tok/s buy on a machine that needs it?** On this host the answer is "nothing"
   — the model fits — so the useful version of the experiment is a constrained host. The memory
   numbers here (a ~15 GB reduction in resident footprint) say what would be bought.
4. **Why is the streaming decode rate flat across prompt lengths?** 9.32 tok/s at a 36-token prompt
   and 9.59 at 1321 tokens says the cost is per generated token; the design's model of the cost
   (320 expert slices per token) predicts exactly that, and it is worth one confirmation with a
   longer decode window than 512 tokens.
5. **Does the first request's 15.25 s on the `on` path hide a warm-up that a longer warmup plateau
   would absorb?** The pin's plateau is the same in both columns; a longer one would say whether
   the streaming path's first visits are being read as steady state by the harness's floors.

## What this cannot claim

- **No cross-runtime comparison of TTFT or E2E.** OptiQ's column is `content`-timed and vMLX's is
  `reasoning`-timed, so a first-token figure from one is not the same quantity as the other's
  (Decision 122). Decode tok/s is read off one stream's own two timestamps and is comparable.
- **No cross-runtime memory ranking.** `peak_mb` does not charge the same pages in every runtime
  (A7); this paper's memory statements are all within one runtime's two columns, which is the
  reading that rule leaves intact.
- **Nothing about accuracy.** Coherence is a floor. That OptiQ's streamed text is coherent says it
  is language, not that it is correct.
- **Nothing about a memory-constrained machine.** The host holds the model resident at 19.03 GiB;
  the whole run is the *cost* side of the trade, with the capacity benefit assumed rather than
  demonstrated.
- **Not a comparison with the 2026-09-20 probe numbers.** Different measurement path (probe script
  vs harness), different formula, and a level shift between the two nights that the 2026-09-24
  paper documents for this model.
