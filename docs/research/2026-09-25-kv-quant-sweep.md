# KV-cache codecs at 16k and 32k: one runtime drives the pin, four refuse it

**Date:** 2026-09-25 (kv-quant runs 01:11 → 06:15 EDT; the Osaurus column re-run 11:34 → 12:30 EDT)
**Study:** v3.1 Phase 4, plan 03-05 (quantized KV caches) — the harness re-run that
`docs/research/2026-09-20-quantized-kv-caches.md`'s own 2026-09-23 caveat asked for
**Harness:** 0.3.0, `source_sha256 a8ad60e7f76e13c5f2c4b7eaa686989abc60ff2cab5809999f7873ff6ed5c9c1`,
identical in all 30 run directories
**Runner:** `scripts/run_sweep_kvquant.sh` → `results/sweep-kvquant/`, joined by
`ohyesmlx.cli sweep --varying kv_quant` into `sweep-p16384.md` and `sweep-p32768.md`
**Subject:** `Jundot/Qwen3.6-35B-A3B-oQ4`, 21,125,808,764 bytes on disk (sidecars included), one
cell per run
**Author:** Claude Opus coordinator

## Why this run exists

The 2026-09-20 KV-cache paper was produced by `scripts/probe_kv_quant.py`, not by the harness:
one request per configuration, no warmup plateau, a different decode formula, no raw records,
and no runtime versions. Its own caveat marks it as not comparable with harness figures. The
surface research of 2026-09-24 (`docs/research/2026-09-24-kv-quant-surface.md`) then established,
statically and per runtime, what a `kv_quant` pin could actually drive, and recommended the value
names this run uses — `off`, `affine8`, `affine4`; `fp8` retired because none of the five has a
float8 codec, and `int4` because the one non-affine codec in the set is a codebook rather than an
integer format. This run is that document's §11 table met by live servers, under the harness's
single-variable discipline, with the raw rows kept.

The study design (`docs/research/2026-09-20-v3-phase2-plan-03-05-study-design.md`) pre-registered
five hypotheses about a *different* subject — `brainworkup/Llama-3.1-8B-oQ4` at 16k/32k with
`--kv-bits 8`/`--kv-bits 4` on OptiQ and `--kv-cache-quantization q8`/`q4` on vMLX. The harness
pin landed on the 35B oQ4 artifact all five runtimes serve, and three of the design's lanes do
not exist as written: mlx-lm has no codec surface, oMLX's codec is TurboQuant rather than affine,
and vMLX's codec covers only the stored prefix cache. Where the design's hypotheses can still be
read against this run, they are read in §4 below.

## What ran

Every run is `oq4__<runtime>` at one prompt length and one codec, in
`results/sweep-kvquant/oq4__<runtime>/p<length>/<UTC>-format/`. Wall-clock times are the runner's
own (`results/sweep-kvquant/runner-night.log`, `runner.log`).

| runtime | version | 16k run directories (`off` / `affine8` / `affine4`) | 32k run directories |
|---|---|---|---|
| mlxlm | 0.31.3 | `T051131Z` / `T052827Z` / `T052838Z` | `T052850Z` / `T060200Z` / `T060211Z` |
| omlx | 0.6.4 | `T064205Z` / `T064154Z` / `T064142Z` | `T060246Z` / `T060235Z` / `T060223Z` |
| optiq | 0.5.13 | `T065818Z` / `T071227Z` / `T072830Z` | `T074433Z` / `T081434Z` / `T085057Z` |
| osaurus | 0.25.12 | `T153453Z` / `T155248Z` / `T155259Z` | `T155311Z` / `T163039Z` / `T163050Z` |
| vmlx | 1.6.59 | `T095957Z` / `T095945Z` / `T095934Z` | `T092731Z` / `T092719Z` / `T092708Z` |

Every entry above is a directory named `20260925` + the time part + `-format`, inside
`results/sweep-kvquant/oq4__<runtime>/p<length>/`; the two sweep files' own Provenance tables
carry the same 15 directories per length with the `kv_quant` each pinned, and every run's
`results.jsonl` and `leaderboard.md` are in them. Only OptiQ has a number in all six of its cells:
the other four runtimes' `affine8` and `affine4` runs (8 per length) are N/A rows — see §2 — and
the night's six Osaurus directories are not part of either join at all (see Conditions).

**Pins every run shared**, from the sweeps' own shared-pins line: temperature `0.0`, seed `0`,
warmup `{cap: 20, floor: 10, mode: plateau, plateau_pct: 3.0, window: 5}`, measured `9`,
cooldown `30.0` s, concurrency `1`, `cache_state`/`mtp_depth`/`stream_experts` all not taken, one
workload `prefill` with `max_tokens` 64, and one prompt length per join — target 16,384
(harness-counted 16,384) or 32,768 (harness-counted 32,765). The servers' own `usage` counts land
close but not identical — 16,389–16,396 at 16k and 32,770–32,777 at 32k — because each runtime
tokenizes the same text with its own tokenizer; the pin is the text, and the text is identical.

## Conditions

- **Order.** The runner alternates codec order and length order per runtime so thermal drift does
  not alias onto either pin (`scripts/run_sweep_kvquant.sh`). For OptiQ — the one column where the
  codec actually moved — both orders ran forward: `off → affine8 → affine4` at 16k, then
  16,384 → 32,768. Within-cell drift is the harness's check on a moving window and every one of the
  six OptiQ cells is inside ±1.1% (quoted per cell in §1); a slow monotone trend across the ~2.5 h
  OptiQ block (02:58:17 → 05:26:56) is not something those figures can exclude, and within that
  block the codec's order is the clock's.
- **Two visits per cell.** Every cell is visited twice, forwards then backwards
  (`measure.visit_plan`), with the nine measured requests split across the two visits; the drift
  figure compares the two halves of the window, and a row's memory reading is the visit whose
  sampled peak was higher (`measure._highest_peak`). Both visits' requests are in that run's
  observations.
- **One runtime at a time.** The runner sweeps all five ports and any stray Osaurus app (`by full
  executable path`, never the name) before and after every run, and each run starts one server.
  The harness cannot detect contention, so exclusivity here is the runner's design and not a
  measurement.
- **The Osaurus column is from a second sitting.** During the night (06:14:04–06:15:02) all six
  Osaurus runs refused at startup — `Osaurus settings drifted from the recorded baseline …
  server.json:modelIdleResidencyPolicy.seconds: baseline 900, host 30` — and measured nothing.
  Those six directories are kept, renamed for their defect, under
  `results/sweep-kvquant/void-oq4__osaurus-residency-unpinned/` (a run discarded for a stated
  defect in its conditions keeps its record). Commit `732eaef` pinned the host settings the way
  `scripts/run_grid_35b.sh` does, and the column was re-run 11:34:53 → 12:30:27. The four other
  runtimes ran 01:11 → 06:14, so the Osaurus `off` rows sit ~5.3 to 11.3 hours after theirs — a
  confound no amount of pinning removes, named rather than corrected. The re-run's settings were
  restored byte-exact afterwards (`cmp`, `runner.log`).

## Results

### 1. OptiQ: the one column the codec axis can read

**Axis — `kv_quant`, format and runtime held constant.** One cell's codec was varied against that
same cell's `off`; the runtime, the artifact and every other pin are identical across the rows.
**Caveat — what this cannot read:** the pin installs more than a codec (§4), and each row is one
cell of one workload, so these are not cross-runtime figures.

All six cells are `PASS` (coherence), `n = 9` measured each, and their sample text is ordinary
English prose (`oq4__optiq/p16384/20260925T065818Z-format`, observation 1: *"This document
establishes a rigorous standard for publishing software performance figures…"*).

| length | codec | decode tok/s | TTFT p50 s | prefill tok/s | ITL ms | E2E p50 s | peak MB | vmmap peak MB | cold load s | first req s | drift % |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 16k | `off` | **69.79** | 26.238 | 624.9 | 14.64 | 26.936 | 28672 | 28467.2 | 4.26 | 32.83 | −0.55 |
| 16k | `affine8` | 35.03 | 29.301 | 559.6 | 29.03 | 31.050 | 26624 | 27340.8 | 3.25 | 36.52 | −0.67 |
| 16k | `affine4` | 33.51 | 29.305 | 559.5 | 30.41 | 30.936 | 26624 | 27340.8 | 3.27 | 36.89 | +0.09 |
| 32k | `off` | **61.64** | 59.115 | 554.5 | 16.62 | 59.824 | 28672 | 28467.2 | 3.26 | 65.75 | +0.35 |
| 32k | `affine8` | 22.92 | 69.987 | 468.3 | 44.32 | 72.776 | 26624 | 27340.8 | 3.26 | 79.71 | +1.10 |
| 32k | `affine4` | 21.80 | 70.122 | 467.4 | 46.79 | 72.526 | 26624 | 27340.8 | 3.27 | 79.43 | −0.55 |

Reading it, one length at a time:

- **Decode falls hard, and further at the longer prompt.** 16k: 69.79 → 35.03 (−49.8%, `affine8`)
  and → 33.51 (−52.0%, `affine4`). 32k: 61.64 → 22.92 (−62.8%) and → 21.80 (−64.6%). ITL moves the
  same way, 14.6 → 29.0/30.4 ms and 16.6 → 44.3/46.8 ms.
- **TTFT rises.** 26.238 → 29.301/29.305 s at 16k, +11.7% both widths; 59.115 → 69.987/70.122 s at
  32k, +18.4% and +18.6%. Prefill throughput moves the same way (624.9 → 559.6/559.5; 554.5 →
  468.3/467.4).
- **The two widths are indistinguishable.** 35.03 against 33.51, and 22.92 against 21.80 — a 4–5%
  gap in the same direction, against a step of 50–65% from `off`. Whatever the pin costs, it is
  not proportional to the bits the codec holds.
- **The peak moves by 2048 MB in the harness's reading and 1126.4 MB in the finer one.**
  `peak_mb` (the sampled `phys_footprint` maximum) is 28672 → 26624 at both lengths; the same
  row's end-of-visit `vmmap` cross-check reads 28467.2 → 27340.8. Both say the quantized state
  peaks lower; they disagree on the size of the step, and neither step moves between 16k and 32k
  (see §4).
- **The `off` column is OptiQ's own default rather than a flag**, because the runtime has no
  `--kv-bits none`: `off` is the absence of `--kv-bits` and `--kv-config`
  (`docs/research/2026-09-24-kv-quant-surface.md` §4.1).

### 2. The other four runtimes refused the codec, and the sweep tables print that as `—`

The two sweep tables carry 15 entries each — five cells across three codec values — and 8 of each
table's entries are `—` (16 of the 30 across both). Their legend says `—` is "a combination no run
measured". In these two tables it is not: **all 16 of those combinations ran and were refused**,
and the `—` is the same glyph the renderer uses for a cell nobody ran (`report._entry` maps
`row is None` and `status == "N/A"` to the same character). The distinction lives in each run's own
`leaderboard.md`, which prints `N/A` with the reason, and in the raw rows, which are the record.
Per runtime:

- **mlxlm (4 combos).** *"kv_quant='affine8' asks for a KV-cache codec, and mlx_lm.server 0.31.3
  has no surface that selects one: no option in its argv … no environment variable anywhere in it,
  no settings file and no per-request field, and the cache it builds is make_prompt_cache's …
  which takes no bit width. The codec exists one layer away on the client CLIs … which is not the
  server this cell would be measured through."* `off` is therefore not a pin on this runtime — it
  is the only state its server can hold.
- **omlx (4).** *"kv_quant='affine8' asks for the affine codec, and oMLX's KV codec is not affine:
  it is TurboQuant, a codebook codec that splits one value into key_bits=floor/value_bits=ceil …
  It is also not drivable from a start command: turboquant_kv_enabled is a per-model settings field
  read from `<base-path>/model_settings.json` … `off` needs no flag: the per-run base path holds no
  `model_settings.json`, which leaves turboquant_kv_enabled False."*
- **osaurus (4).** *"kv_quant='affine4' cannot be driven on Osaurus: it exposes no start-command
  flag for the KV codec in either direction, its affine route (kvMode: .affine, and the legacy
  kvBits) is not supported under batched decode and falls back to float KV on this host, and the
  codec it can deliver while batching is TurboQuant — a codebook codec that requires both bit
  widths explicitly."*
- **vmlx (4).** *"kv_quant='affine8' cannot be measured on vMLX: its codec quantizes only the
  prefix cache's stored copy and generation stays full precision … and it is a no-op under this
  command, which passes `--disable-prefix-cache` unless the run pinned `cache_state='on'` … So this
  cell is N/A in this codec; `off` is passed as `--kv-cache-quantization none`, which is this
  runtime's real explicit off."*

So the `off` columns are not one thing either: on OptiQ it is an unset default, on vMLX an explicit
flag, on oMLX a structural consequence of a fresh scratch directory, and on Osaurus a host state
the harness verifies rather than sets. That is the surface document's prediction reproduced on
live runs, and it is the reason this study's codec axis has one readable column.

### 3. The five `off` columns, as context for the OptiQ rows

**Axis — runtime, `kv_quant` held constant at `off`.** One format, five runtimes, one workload.
**Caveat — what this cannot read:** the columns were timed on different channels, so their TTFT
is not one quantity, and `peak_mb` carries no cross-runtime ranking (see below). This table is
context for §1, not a runtime comparison of its own.

| length | mlxlm | omlx | optiq | osaurus | vmlx |
|---|---|---|---|---|---|
| 16k `off`, decode tok/s | 58.27 | 76.51 | 69.79 | 58.98 | 57.01 |
| 16k `off`, TTFT p50 s | 29.235 | 30.714 | 26.238 | 33.944 | 26.140 |
| 32k `off`, decode tok/s | 49.65 | 65.13 | 61.64 | 55.16 | 48.37 |
| 32k `off`, TTFT p50 s | 66.296 | 74.301 | 59.115 | 74.382 | 62.748 |
| 32k `off`, peak MB | 25600 | 27648 | 28672 | 15360 | 29696 |

Two things to read from it, and one not to:

1. **Every runtime is slower at double the prompt.** Decode 58.3 → 49.7, 76.5 → 65.1, 69.8 → 61.6,
   59.0 → 55.2, 57.0 → 48.4 (−6% to −15%); TTFT roughly doubles. The 35B MoE at a 32k prompt is
   the same serving problem on all five.
2. **The `off` rows are timed on two different streams.** OptiQ's column is `content`-timed (9 of 9
   measured requests in every cell); mlxlm, omlx, osaurus and vmlx are `reasoning`-timed (9 of 9
   each) — their Qwen3.6 answer arrives on the reasoning stream or as a mirror of it. Decode tok/s
   and ITL are read off one stream's own two timestamps, so they stay readable across that
   boundary; **TTFT does not**: on a reasoning-timed row it is the model's first token out of the
   trace, on OptiQ it is the first content token. No runtime-axis TTFT ordering is available from
   this table (Decision 122), and none is made.
3. **Not a memory ranking.** Osaurus peaks at 14336/15360 MB against 23552–29696 MB for the other
   four on the same 21 GB artifact. That is the documented sampler split
   (`report.CROSS_RUNTIME_UNCOMPARABLE`, A7) — `footprint` does not charge the same pages in every
   runtime — and it is stated here so the number is not read as a memory finding.

### 4. Where the results answer the design (plan 03-05, H1–H5)

- **H1, memory compression: the direction is confirmed, the arithmetic is not.** The study
  predicted a footprint that tracks the KV tensors: ~50% of the KV saved at 8-bit, ~75% at 4-bit,
  both growing with context. Measured, the pin's step is 2048 MB at *both* widths and *both*
  context lengths (1126.4 MB by the vmmap cross-check) — a constant, which no codec can produce,
  since the bytes it holds and the bytes it saves both scale with context length and with bits.
  The pin carries a documented second variable: whenever KV quant is on, OptiQ installs the fused
  streaming-KV conversion and the fused quantized SDPA (unless `--no-fused-kv`, which no arm here
  passes), and that path exists precisely to change peak footprint
  (`docs/research/2026-09-24-kv-quant-surface.md` §4.4). So this reading is a
  *codec-plus-fused-path* delta, and the run has no control arm to separate them.
- **H2, decode acceleration (+10–25% at 32k): refuted, in the opposite direction, at both
  lengths.** 32k measured −62.8%/−64.6%; 16k −49.8%/−52.0%. The 2026-09-20 probe paper found the
  same sign on a different model with a different formula; the harness now records it with raw
  rows, nine measured requests per cell, a warmup plateau and within-cell drift under ±1.1%.
  The fused-kernel caveat of H1 applies here too: the quantized cells run a different attention
  kernel as well as a different codec.
- **H3, prefill tax (+3–10% TTFT): the direction is confirmed, the magnitude is larger.**
  +11.7% at 16k (both widths) and +18.4%/+18.6% at 32k. Prefill throughput falls in step, so this
  is the same wall-clock cost the decode rows pay, seen from the other end.
- **H4, coherence 100% PASS: confirmed where it is testable.** Six of six OptiQ cells pass, and
  every measured request in them produced language. The other 24 combinations have no cell to test
  it on — 16 were refused and the eight `off` cells were measured without a codec.
- **H5, a fused-SDPA advantage for INT4 over a non-fused path: not testable here.** The run has no
  `--no-fused-kv` arm, and `affine4` and `affine8` (which both install the fused path) are within
  4–5% of each other. Nothing in this record separates the fused kernel's effect from the codec's.
- **The design's matrix does not survive the runtimes, and that is the finding.** Three of the five
  lanes the design assumed — mlx-lm `--kv-bits`, vMLX `--kv-cache-quantization`, oMLX/Osaurus codec
  arms — do not exist as drivable states. `kv_quant` is a pin with one readable column, and the
  surface document's §11 predicted exactly that; this run is its live confirmation.

## Open questions

1. **A `--no-fused-kv` control arm.** Until one exists, the memory *and* decode figures from a
   quantized OptiQ cell mix two changes: the cache codec and the fused conversion-plus-SDPA path.
   One extra cell per length is the cheapest way to attribute them.
2. **Why the step is 2048 MB and flat.** Both widths and both context lengths move the sampled peak
   by the same two units. The fused path is the only named mechanism in the pin that could do that;
   the KV arithmetic at 16k/32k cannot. A control arm answers this too.
3. **The whole-GiB sampling unit.** Every `peak_mb` in these 30 runs is a whole number of GiB
   (23552, 25600, 26624, 27648, 28672, 29696, 14336, 15360), while the same rows' `vmmap`
   cross-check moves in 0.1 GiB steps. A codec whose raw saving at these lengths is on the order of
   a few hundred MB is at the edge of what the sampled peak can express; the cross-check is why
   the 1126.4 MB step is visible at all.
4. **Should the sweep print `—` for a refused combination?** Today "no run measured it" and "the
   run measured it and the runtime refused the pin" render identically in a sweep table, and the
   difference here is 16 of 30 combinations. The information is in the leaderboards; it is not in
   the sweep.
5. **Whether any of the other four runtimes should get a codec column of its own.** oMLX and
   Osaurus both have a codebook codec (`tq4`-shaped, key/value widths separate) reachable only by
   writing settings; the surface document left that as a decision, since reaching it changes more
   than one thing. This run does not change that.

## What this cannot claim

- **No cross-runtime TTFT ordering.** Four columns are timed on the reasoning stream and one on
  content; the grid's own rule withholds that ordering, and so does this paper (Decision 122).
- **No cross-runtime memory ranking.** `peak_mb` does not charge the same pages in every runtime
  (A7). The Osaurus column's 14–15 GB is the clearest instance in this data set.
- **No statement about KV quantization in general.** One runtime in this set has a live codec, one
  workload shape was run, one model was measured, and the codec's own column carries a second
  variable from its own runtime.
- **Nothing about accuracy.** Coherence here is a floor — "is this language" — and it is not a
  quality judgement. H4 asks only whether the cells produced language, and they did.
- **Nothing about the Osaurus column's level relative to the night's other columns.** It was
  measured ~5.3–11.3 hours later, on re-pinned host settings, after the night's six Osaurus runs
  measured nothing at all.
- **Not a 16k-vs-32k comparison in one table.** The prompt length is a separate pin and the two
  joins are separate documents; each table above is one length, and the two are read side by side,
  never averaged.
