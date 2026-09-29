# Seedless validation: the three published grids, re-run on the Decision 128 harness

**Date:** run 2026-09-27 21:56 → 2026-09-28 04:51 EDT (`tonight.log`)
**Milestone:** v3.1 Hardening, after Decision 128 (no request seed at temperature 0) and Decision 129 (batch caps follow the run's concurrency)
**Harness:** 0.3.0, `source_sha256 6968456b…27a2`, identical in all fifteen run directories — the package the tree hashes to at write time
**Runner:** `scripts/run_harden_validation.sh` → `results/harden-2026-09-27-seedless/grid-{35b,dense,moe}/`
**Author:** Command Code implementer (the write-up); the runs are the coordinator's.

## Why this run exists

Decision 128 removed the request seed at temperature 0 (`b820bda`, 2026-09-26). The reason was
that the seed is not inert in the *server*: a seeded request routes mlx-lm onto its sequential
path — `model_provider.is_batchable and args.seed is None` (`mlx_lm/server.py:685-686`) — and
OptiQ routes with it, so every grid this project had published measured a path an ordinary
client never takes. The three validation grids were re-run on the seedless harness, same pins,
same runner scripts, same artifacts, so the published grids get an arm on the path everyday
clients use. This is the counterpart of `docs/research/2026-09-24-hardening-validation-grids.md`:
that paper re-ran the three grids on the hardened harness (seed 0); this one re-runs them with
the seed gone.

What this is **not**: a re-measurement of the hardening changes (those landed in the 09-23 arm),
a new study, or a concurrency run (every cell here is N=1).

**The two arms cannot be joined.** The 09-23 rows were written by a harness that had no
per-row `request_seed` field at all — the header's `seed: 0` is the only record that they sent
one — while all 168 data rows of this run carry `request_seed: null` and the header's `seed` is
`null` too. The join's pin guard refuses that pair, correctly, so every figure below is a
reading of two grids side by side (per cell and per workload), never a join. No number here
comes from a joined file.

## What ran

| grid | runner | model × formats | columns | wall clock (EDT) | exit |
|---|---|---|---|---|---|
| 35B MoE | `run_grid_35b.sh --cache-state off` | Qwen3.6-35B-A3B × 4 | mlxlm, omlx, optiq, vmlx, osaurus | 22:01 → 00:29 | 0 |
| dense | `run_grid.sh` | Qwen3.5-4B × 5 | same five | 00:34 → 03:13 | 0 |
| MoE | `run_grid_moe.sh` | LFM2.5-8B-A1B × 5 | same five | 03:18 → 04:51 | 0 |

Wall clocks are the runner's own (`tonight.log`, `runner-dense.log`, `runner-moe.log`,
`grid-35b/runner.log`; the session opened with a 300 s cooldown at 21:56). The 09-23 arm ran
23:18 → 05:37 four nights earlier, in the same evening→early-morning order: 35B first, then
dense, then MoE.

Runtime versions, identical in both arms except one:

| runtime | 09-23 arm | this arm |
|---|---|---|
| mlx-lm | 0.31.3 | 0.31.3 |
| oMLX | 0.6.4 | 0.6.4 |
| mlx-optiq | 0.5.13 | 0.5.13 |
| vMLX | 1.6.59 | 1.6.59 |
| Osaurus | 0.25.12 | **0.25.13** |

Osaurus is the one column where the version and the arm are confounded; its rows are read as a
new release, not as a seed-path before/after. The other four runtimes are the same release in
both arms. Pins are otherwise the same as the 09-23 arm's (`temperature 0.0`, `warmup
{cap 20, floor 10, mode plateau, plateau_pct 3.0, window 5}`, `measured 9`, `cooldown_s 30.0`,
`concurrency 1`, and the same three workload shapes with identical messages); `cache_state` is
`off` on the 35B grid in both arms and unpinned on dense and MoE in both arms. All five columns
of each grid share one harness sha (`6968456b`), one set of pins and one workload message set —
the grid files' own shared-pins lines say so.

### Conditions

- The runner pinned Osaurus around its column in all three grids — `cache off & idle residency
  pinned to 900 s`, restored byte-exact with `cmp` afterwards — the same lines the 09-23 arm's
  logs carry. No stray-Osaurus sweep fired in this run; the 09-23 arm's 35B log opens with
  `sweeping port 1337 pid 12222`.
- Nothing else about the host is recorded in either arm. The harness cannot detect contention,
  and no run in either arm attests the machine's state while it measured. The one in-run weather
  signal that survived into the files is the drift flags (§2.3 and the last bullet of "What this
  does not claim").
- **Timing channels did not move.** Every mlx-lm/oMLX/vMLX/Osaurus row in both arms carries
  `timed on reasoning channel`; no OptiQ row does on the 35B and dense grids, and every OptiQ
  row does on the MoE grid. So each TTFT comparison below is within one channel, cell by cell.
- Everything is `PASS` except the one row §1 names; no cell in this run is `N/A` and no `PASS`
  row lacks a published metric.

## Results

### 1. Status: the same three grids, and the same single FAIL

**48/48 PASS** on 35B, **60/60 PASS** on dense, **59/60 PASS** on MoE. The one exception is the
same exception the 09-23 arm carries: `optiq__osaurus` on the MoE grid's `decode` workload —
status `FAIL`, 9 of 9 requests measured, no published metrics — with the identical reason
string in both arms:

> no content completion tokens from `token_source='none'`, so decode tok/s is undefined

(the 09-23 row: `grid-moe/20260924T092148Z-format/leaderboard.md` line 34; this run's:
`grid-moe/20260928T083238Z-format/leaderboard.md` line 34). The cell was measured in both arms
(n = 9 both times, `floor coherence pass`, content deltas 711) and refused by the metrics floor
in both. It is the MoE grid's known `token_source='none'` failure, and the seedless harness
reproduces it exactly. Nothing else in any grid changed status.

### 2. Levels: dense and MoE moved down almost everywhere; 35B did not

Per runtime and grid, the change from the 09-23 arm to this one over every cell-workload pair
the two arms share. The one row that carries no metrics in either arm (MoE `optiq__osaurus`
`decode`) is in neither set, which is why MoE Osaurus has `n=11`. Decode is `decode_tps`; TTFT is
`ttft_p50_s`; "median [min, max]" is over the shared pairs.

| grid | runtime | decode tok/s change | TTFT p50 change |
|---|---|---|---|
| 35B | mlx-lm | −13.5% [−18.9, −10.4] (n=9) | +0.0% [−5.0, +13.2] |
| 35B | oMLX | **+3.7%** [−1.0, +10.5] | −2.2% [−6.0, +0.7] |
| 35B | OptiQ | −17.2% [−27.1, −15.4] | +7.7% [0.0, +18.8] |
| 35B | vMLX | −3.6% [−6.3, +0.3] | +5.7% [+0.9, +7.1] |
| 35B | Osaurus | −7.9% [−11.7, +1.2] | +9.6% [−1.4, +18.0] |
| dense | mlx-lm | −17.6% [−26.5, −12.5] | **−32.4%** [−92.6, −15.7] |
| dense | oMLX | −16.3% [−23.5, −12.3] | +10.7% [+6.8, +14.5] |
| dense | OptiQ | −18.9% [−31.2, −13.7] | **−30.9%** [−91.4, −12.7] |
| dense | vMLX | −15.4% [−19.9, −9.5] | +0.3% [−5.5, +16.4] |
| dense | Osaurus | −14.8% [−19.0, −13.6] | +18.1% [+4.9, +20.9] |
| MoE | mlx-lm | −25.1% [−26.6, −17.7] | **−42.9%** [−91.4, −34.6] |
| MoE | oMLX | −7.3% [−14.9, −4.5] | +20.6% [+7.6, +28.3] |
| MoE | OptiQ | −25.3% [−27.2, −19.5] | **−41.5%** [−91.0, −33.1] |
| MoE | vMLX | −6.1% [−9.8, +0.4] | +10.9% [−6.4, +29.1] |
| MoE | Osaurus | −15.3% [−18.3, −12.5] (n=11) | +11.4% [+2.8, +15.0] (n=11) |

Decode figures are read from each grid's `grid.md` tables and TTFT p50 from each column's
`leaderboard.md`; each runtime × grid cell of the table above is the median over that runtime's
shared rows, and the two arms were read side by side, never joined (the join would refuse them).

**Checked against the coordinator's reading, from the rows:**

- "Every runtime's decode fell" is a dense-and-MoE statement. On dense and MoE it is true:
  −14.8 to −18.9% on dense, −6.1 to −25.3% on MoE. On 35B it is false — **oMLX's 35B column rose**
  (median +3.7%, up to +10.5% on `decode`), vMLX was flat within ±6%, and only mlx-lm, OptiQ and
  Osaurus fell.
- "oMLX/vMLX/Osaurus about −4 to −16%" fits MoE (−4.5 to −18.3%) and is close on dense (−12.3 to
  −19.9%); on 35B those three read +3.7, −3.6 and −7.9%.
- "mlx-lm and OptiQ fell further (−13 to −25%)": per grid their medians are 35B −13.5/−17.2,
  dense −17.6/−18.9, MoE −25.1/−25.3. The claim holds as a per-grid median: they are the bottom
  two on all three grids. On dense the margin over the others is only 1.3–4.1 points; on MoE it
  is 10–19 points.
- "their TTFT fell 31–43% on dense/MoE": the medians are dense −32.4/−30.9 and MoE
  −42.9/−41.5. True over the twelve rows each, **but the median hides two regimes**, and the
  regimes are the finding — §2.2.

#### 2.1 What moved is per-format as well as per-runtime

Format-level rows, `decode_tps`, old → new (the 09-23 grid.md tables → this run's):

| row | mlx-lm | oMLX | OptiQ | vMLX | Osaurus |
|---|---|---|---|---|---|
| dense `stock4bit` decode | 70.3 → 58.1 | 73.6 → 63.5 | 74.7 → 60.7 | 75.0 → 61.1 | — |
| dense `oq4` decode | 69.3 → 57.0 | 73.0 → 61.5 | 70.4 → 58.9 | 68.2 → 59.3 | 68.5 → 58.5 |
| MoE `stock4bit` decode | 156.0 → 123.2 | 160.7 → 150.2 | 155.7 → 123.3 | 131.9 → 120.7 | — |
| MoE `jang2l` decode | — | — | — | 122.6 → 120.0 | 148.0 → 125.4 |
| 35B `stock4bit` decode | 75.2 → 67.2 | 74.1 → 81.9 | 73.7 → 62.0 | 71.7 → 69.1 | 55.8 → 50.9 |
| 35B `stock4bit` chat | 82.4 → 69.5 | 87.4 → 92.3 | 77.4 → 64.1 | 71.7 → 70.0 | 61.9 → 54.7 |

Two per-format readings are worth naming because they cut against a single "the night was slower"
story: on dense, vMLX's `jang4s` rows fell least of that column (−9.5 to −14.0%) while its
`stock4bit` rows fell most (−18.5 to −19.9%); and on MoE, vMLX's `jang2l` rows were essentially
flat (−2.8 to +0.4%) while on the same workloads every other format of that column fell more
(chat −7.6 to −8.6%, decode −8.5 to −9.8%). No row here isolates a cause for either; they are
named because any future reading of these columns has to carry them.

#### 2.2 The routing runtimes' TTFT is a different measurement in the two arms

On dense and MoE, mlx-lm's and OptiQ's TTFT movement is concentrated on the `prefill` workload,
whose prompt is 1,319 tokens (dense) / 1,332 (MoE) — read from the rows' own
`prompt_tokens` — and is ~−91% there, while `chat` and `decode` (32–34-token prompts) move
−13 to −45%:

| grid | runtime | chat | prefill | decode |
|---|---|---|---|---|
| dense | mlx-lm | −30.8% | **−91.9%** | −29.4% |
| dense | OptiQ | −30.9% | **−91.1%** | −16.4% |
| dense | oMLX / vMLX / Osaurus | +11.1 / +0.3 / +19.7% | +9.8 / +15.6 / +17.3% | +11.4 / −2.5 / +16.7% |
| MoE | mlx-lm | −41.4% | **−91.2%** | −38.9% |
| MoE | OptiQ | −41.0% | **−90.9%** | −38.9% |
| MoE | oMLX / vMLX / Osaurus | +24.2 / +10.4 / +12.4% | +21.3 / +25.1 / +10.3% | +13.1 / +5.6 / +11.6% |
| 35B | mlx-lm | +0.0% | −2.9% | +12.1% |
| 35B | OptiQ | +5.1% | +0.7% | +18.1% |
| 35B | oMLX / vMLX / Osaurus | −2.7 / +5.7 / +11.9% | −0.6 / +4.6 / +8.3% | −1.7 / +5.7 / +9.6% |

Per-workload medians over the shared cell-workloads; the same rows as §2.

The −91% rows are not a speed-up of the same quantity. A full prefill of that prompt costs
~1.0–2.4 s in these very rows (MoE 09-23 mlx-lm 1.000 s, dense 09-23 mlx-lm 2.407 s, 35B both
arms ~2.1 s), and this run's rows read 0.178–0.223 s (dense) and 0.086–0.100 s (MoE) — 1,319
tokens in a fifth of a second, or 1,332 in a tenth, is not a prefill. What it is, is the prompt
cache serving the repeated prompt:

- Only the two runtimes Decision 128 says route on the seed move this way. oMLX and vMLX do not
  route on it (source-read), Osaurus is not readable, and none of the three collapses.
- On the 35B grid — where `cache_state off` pins `--prompt-cache-size 0` in **both** arms — the
  same two runtimes show **no** collapse at all (+0.0% and +7.7% medians). That is the control:
  with the cache pinned off, the seedless arm's prefill costs what the seeded arm's did.
- On dense and MoE the cache is unpinned in both arms, and mlx-lm's default is on
  (`--prompt-cache-size` default 10, `ohyesmlx/runtimes.py`'s `prompt_cache_flags`). The seeded
  path cannot hit it: under `_serve_single` the only insert is keyed by prompt + completion
  (`server.py:1019-1021`), and the one fetch branch that could serve a request from a longer
  stored key needs a trimmable cache (`models/cache.py:1681-1688`), which the hybrid models'
  `ArraysCache` is not — the full chain is written up in `docs/runtimes/mlx-lm.md` against the
  multi-turn run. The batched path inserts prefix-keyed segment caches (`server.py:864-880`), so
  the seedless arm pays only the suffix. OptiQ runs the same server (its `serve` passes unknown
  flags through to `mlx_lm.server`'s argparse), which is why it moves with mlx-lm.

So on the rows with a long, repeated prompt, the two arms' TTFT p50 for these two runtimes are
**not the same quantity**: the 09-23 figure is a full-prefill time and this run's is a
cache-hit time. The dense/MoE `prefill` TTFT columns cannot be compared across the seed change
for mlx-lm and OptiQ, and neither can any `prefill_tps` derived from them (`prompt_tokens /
ttft_s`, `report.py:6`), which on those rows is now a cache-serving rate and not a prefill rate.
Within an arm the format axis is unaffected — every format of those two runtimes was measured
under the same cache state in that arm.

**Resolved 2026-09-29 (Decision 130).** The cache explanation was tested by re-running the dense
and MoE grids with the cache off: `runtimes.prompt_cache_flags` now passes `--prompt-cache-size 0`
on mlx-lm and OptiQ unless the pin is `on`, and the two grids were re-run into
`results/harden-2026-09-28-cacheoff` (2026-09-29 03:18 → 07:27 EDT, harness `6f36eb98`, every
column exit 0, `cache_state` and `seed` both `null`). The `prefill` TTFT p50 for the routing pair
returns to a full-prefill time — three arms, seconds, median over the 36 measured requests each
runtime-workload has per grid (nine per cell, four formats):

| grid | runtime | 09-23 seeded | 09-27 seedless, cache unpinned | 09-29 seedless, cache off |
|---|---|---|---|---|
| dense | mlx-lm | 2.417 | 0.199 | **2.306** |
| dense | OptiQ | 2.378 | 0.215 | **2.289** |
| MoE | mlx-lm | 1.040 | 0.091 | **1.033** |
| MoE | OptiQ | 1.030 | 0.096 | **1.029** |
| dense / MoE | oMLX, vMLX, Osaurus | 2.916 / 2.184 / 0.247 · 1.449 / 0.941 / 0.182 | 3.182 / 2.517 / 0.295 · 1.762 / 1.170 / 0.201 | 2.758 / 2.180 / 0.255 · 1.466 / 0.959 / 0.172 |

The cache-off column sits within 5% of the seeded one for both runtimes on both grids (dense −4.6% and
−3.7%, MoE −0.7% and −0.1%), the same as the 35B control predicted; the three runtimes that were
always cache-off did not move. So the −91% was the cache and only the cache, and mlx-lm's and
OptiQ's `prefill` TTFT — and the `prefill_tps` derived from it — are comparable across the seed
change **when both arms are cache-off**: the 09-23 and 09-29 columns. The 09-27 column stays a
cache-hit column and stays out of any comparison. `chat` and `decode` TTFT moved less (32–34-token
prompts; dense mlx-lm `chat` 0.284 → 0.202 → 0.228, MoE 0.147 → 0.088 → 0.146), and the cache-off
column is back within ~20% of the seeded one, a gap §2.3's session term is large enough to hold. Not re-derived
here: the decode-rate medians of §2 for these two runtimes under cache-off — the TTFT rows above
are the whole of what was checked.

#### 2.3 What the two arms can and cannot separate

The arm moved two things at once — the seed (and therefore the serving path on two runtimes) and
the session — and the rows can only bound their sum. The three runtimes that do not route on the
seed give a session estimate per grid: dense −12.3 to −19.9%, MoE −4.5 to −18.3%, 35B +3.7 to
−7.9%. That estimate is not one number: it differs by runtime on the same grid on the same
night, so it cannot be subtracted out as a common-mode offset. What the rows do license is
saying that **the routing pair's excess over the non-routing three — roughly 1–4 points on
dense, 6–21 points on 35B and 10–19 points on MoE — is an upper bound on any seed-path effect,
not a measurement of one.**

The size of the session term is documented, twice, independently of this run:

- **Decision 127 (STATE.md).** The 35B grid's r2 (09-24) and r3 (09-25) arms agree within
  2.7–6.8% per runtime and read 10–26% above the published 09-20 levels for mlx-lm, oMLX and
  OptiQ — all of them seeded, so no seed was involved in that shift. A session-level shift of
  that size on this host is the established norm.
- **The 2026-09-27 concurrency study** (`docs/research/2026-09-27-concurrency-batching.md`)
  measured its N=1 state twice on one day, seedless both times, on this host: the two readings
  differ by up to 8.9% with a byte-identical command. And its seedless mlx-lm N=1 `decode` cell
  on `RepublicOfKorokke/Qwen3.5-4B-oQ4` — the same artifact as this grid's dense `oq4` rows,
  3,160,559,814 bytes, read from this run's row — reads 65.9 tok/s, against **57.0** in this
  run's mlxlm `oq4` `decode` row 21 hours later. Two seedless sessions, one artifact, one
  runtime, one policy: 13.5% apart. (65.9 is that paper's figure, not this run's; everything
  else in this paragraph is read from the two grid arms.) That is the size of the changes §2
  reports, and it is why no delta in that table is attributed to the seed.

What cannot be separated, plainly: whether the routing pair's extra 6–21 points of decode loss
on 35B and 10–19 on MoE is the batching path costing per-token throughput at batch 1, the same
night being worse for those two runtimes, or an interaction. One arm per condition, one session
per arm, no replicate, no interleaving across the two arms.

### 3. The format orderings: 28 of 45 columns unchanged, four changes above the project's tie band

Every runtime's within-column format ordering was re-derived from both arms' `decode_tps` over
all 45 (grid, runtime, workload) columns; 28 are identical to the 09-23 arm's and 17 changed.
The project's own tie band is 2.5% (pre-registered in the JANG study design); by that band
**13 of the 17 changes are ties, and four are not**:

| grid | runtime | workload | swap | gap now | was | reading |
|---|---|---|---|---|---|---|
| dense | vMLX | chat | `jang4s` ↔ `stock4bit` | **12.4%** | 0.5% | new: JANG_4S first |
| dense | vMLX | prefill | `jang4s` ↔ `stock4bit` | **7.2%** | 2.0% | new: JANG_4S first |
| dense | OptiQ | prefill | `oq4e` ↔ `optiq` | 3.5% | 1.3% | restores the published order |
| MoE | mlx-lm | decode | `oq4e` ↔ `optiq` | 3.4% | 0.3% | tie stretches |

The 13 tie-band changes, per runtime, as asked:

- **mlx-lm.** 35B: none. Dense `prefill`: `stock4bit`/`oq4` swap by 2.6%, back to the published
  order. MoE: the three specialised formats reshuffle underneath `stock4bit` on **all three**
  workloads (their top-to-bottom spread is 1.8–3.4%; on `chat` the order becomes
  `stock4bit > oq4e > optiq > oq4`, with `oq4` carrying a +3.0% still-warming drift).
- **oMLX.** 35B: none. Dense `chat`: `stock4bit` over `oq4` by 0.7% (the `stock4bit` row carries
  +4.8% still-warming drift) and `optiq` over `oq4e` by 0.2% (`oq4e` carries +4.7%) — the one
  inversion of the dense grid's four-way order anywhere in this run. MoE `chat`/`decode`:
  `oq4e`/`oq4` by 0.5% and 0.1%.
- **OptiQ.** 35B `chat`: `optiq` over `oq4` by **0.3%**, with the `oq4` row carrying +6.1%
  still-warming drift — a tie whose mover had not settled. Dense `prefill`: the 3.5% row above.
  MoE: none.
- **vMLX.** The two 7.2%/12.4% rows above; MoE `chat` `jang2l` over `stock4bit` by 2.2% and MoE
  `prefill` `oq4` over `oq4e` by 1.1%. Notably vMLX's `decode` orderings are unchanged on all
  three grids.
- **Osaurus.** 35B `chat`/`prefill`: `optiq` over `oq4` by 2.1% and 1.8% — this **restores** the
  published 09-20 order, which the 09-23 arm had inverted; the version also moved this arm
  (0.25.12 → 0.25.13), so this column cannot be attributed to the seed. Dense `prefill`: `oq4`
  over `jang4s` by 1.8%, against 4.7% the other way in both earlier arms (the `jang4s` row
  carries −6.0% slowing drift, so its published figure is an early-window one). MoE `decode`:
  `oq4` over `jang2l` by 1.7%, against the published column's `jang2l > oq4` by 1.2% — the
  "JANG_2L leads Osaurus's decode column outright" claim is a 1.2–1.7% tie in all three arms.

Three of the 17 changed columns carry a >5% drift flag on the cell that moved: 35B OptiQ `chat`'s
`oq4` (+6.1%, still warming — its published figure is a floor, and the swap it makes is the 0.3%
one), dense Osaurus `prefill`'s `jang4s` (−6.0%, slowing) and MoE oMLX `chat`'s `oq4` (−5.6%,
slowing). Three more moved cells carry sub-5% still-warming drift in the same direction — dense
oMLX `chat`'s `stock4bit` (+4.8%) and `oq4e` (+4.7%), and MoE vMLX `chat`'s `stock4bit` (+4.2%) —
which is the same reading one notch weaker.

### 4. What this means for the published figures

**Findings that stand on orderings — all of them stand, with the two named exceptions.**

- **35B, "stock4bit leads decode in all five runtimes":** holds in all five columns on all three
  workloads in this run (`stock4bit` first in every one of the 15 columns×workloads), and it
  leads its own column's OptiQ row on all three workloads in all five columns. The JANG MoE half
  of the duality holds too: `stock4bit__vmlx` beats `jangtq4__vmlx` by +21.3% chat, +17.7%
  prefill, +20.0% decode (published: +13.1% decode primary, +17.9% replicate).
- **dense, the `stock4bit > oq4 > oq4e > OptiQ` tail:** the order holds on `decode` in all four
  columns that carry all four formats; on `chat` in three of the four (oMLX flips `optiq` over
  `oq4e` by 0.2%, with `oq4e` still warming); and on `prefill` in three of the four (Osaurus has
  `optiq` above `oq4e`, as it did published). But the tail's *separation* is thinner than it was
  published as: the `oq4e`→`optiq` gap on `decode` was +7.6/+3.0/+4.4% (published, mlx-lm/oMLX/
  OptiQ), +6.1/+4.5/+4.3% (09-23) and is **+0.8/+1.3/+1.9%** now. Adjacent cells within 2.5% are
  ties by this project's own rule, so three of those four pairs should be read as ties today,
  where the published grid read them as a separation.
- **dense JANG, R1's vMLX half:** strengthened, not weakened. `jang4s` now leads vMLX's column on
  all three workloads. The published column had `stock4bit` 0.2% ahead on `chat`, `oq4` 0.1%
  ahead of `stock4bit` on `prefill` with `jang4s` third, and `jang4s` 2.2% ahead on `decode`;
  this run reads +12.4%, +7.2% and +9.8% in `jang4s`'s favour. The Osaurus half was a tie in
  this grid's own rows in all three arms (published `jang4s` over `oq4` by 1.2% on `decode`,
  this run by 0.2%).
- **MoE, "stock4bit wins by a wide margin and the three specialised formats are tied":** holds.
  `stock4bit`'s margin over the best non-stock format: mlx-lm +12.8/+10.3/+10.0%,
  oMLX +13.8/+14.6/+12.6%, OptiQ +9.8/+9.6/+10.0% (published: +11.0 to +16.9%). The non-stock
  spread is 0.8–3.8% per column-workload. vMLX is the one column where the margin collapses:
  +2.1% prefill, +0.6% decode, −2.2% chat against `jang2l` — consistent with the v2 JANG study's
  own finding that JANG_2L ties stock4bit on vMLX in this model class.
- **MoE, "OptiQ last or tied-last":** a statement about 0.1–1.2% gaps in every arm. In this arm
  `optiq` is last in the oMLX and OptiQ columns on all three workloads, last in the mlx-lm column
  on `decode` (108.3 against `oq4e` 112.0) but third there on `chat`/`prefill` (`oq4` last by
  0.2% and 1.2%), and last in Osaurus's `chat` and `prefill` columns — its one Osaurus `decode`
  cell is the grid's FAIL row. "JANG_2L leads Osaurus's decode column outright (147.1)" is the
  **one published ordering this run does not reproduce** — `oq4` 127.6 now leads `jang2l` 125.4.
  It is a 1.7% inversion inside the tie band, but it is an inversion of a claim that was written
  as outright.

**Findings that quote levels.** Every rate in every published paper is a session figure, and this
run is the third session for the dense and MoE grids and the fourth for 35B (published, 09-23,
r2/r3, this one). Concretely:

- The 35B cross-runtime level findings are already superseded by Decision 127 (r2/r3); this run
  is a further arm in the same story — same orderings, a fourth set of levels, and the first on
  the seedless path.
- The dense and MoE rates quoted in the papers are seeded-path, published-session figures (the
  09-16 published dense grid read 70.1/75.9/77.8 on `stock4bit` `decode` for mlx-lm/oMLX/OptiQ;
  the 09-23 arm read 70.3/73.6/74.7 on the same rows). This arm reads 14.8–18.9% below the 09-23
  arm on dense and 6.1–25.3% below on MoE (per-runtime medians, §2), so a figure quoted today
  should name its arm and its session.
- The `disk_bytes` figures are untouched (the artifacts did not change) and `peak_mb` is
  unaffected by the seed; the Pareto half of the 35B paper that rests on disk and memory is not
  re-litigated here.
- The one place where the arms are not even the same quantity is dense/MoE **TTFT p50 and
  therefore prefill tok/s for mlx-lm and OptiQ** on repeated long prompts (§2.2): those columns
  must not be compared across the seed change at all — **for the 09-27 arm.** The 09-29 cache-off
  re-run (§2.2, Decision 130) restores the comparison: it is the same quantity as the 09-23 arm's.

## What this does not claim

- **No attribution to the seed of any decode delta.** Two sessions, no replicate, no
  interleaving; the session term is documented at 10–26% (Decision 127) and measured seedless at
  8.9–13.5% on this host (concurrency study; §2.3), which is the size of the effects here. The
  one mechanism the rows do establish is the TTFT path change of §2.2, and it is source plus
  rows, not a paired experiment.
- **No cross-runtime ranking.** Nothing above orders runtimes; every table is within-grid,
  within-runtime, old-vs-new, and the TTFT columns that mix timing channels stay unranked
  (Decision 122).
- **Not an accuracy result.** Coherence is the floor, every row that carries a metric here
  cleared it, and nothing scores an output.
- **Nothing about concurrency** (N=1 everywhere) or about any setting this run did not pin.
- **The Osaurus column is confounded by its version bump** (0.25.12 → 0.25.13) and cannot be
  read as a seed-path before/after.
- It does not re-litigate the 09-23 arm's conditions; that is the 09-24 paper's job. Its
  contention window (23:18–23:30, during the 35B mlx-lm column) is not this run's.
- The 35B grid's own weather: this arm's 35B column carries 13 rows with |drift| > 5%, seven of
  them oMLX — including the worst in the run, `stock4bit prefill` at −63.4% (early median 99.5,
  late 36.4), `oq4 prefill` at −50.3% (90.8 → 45.1) and `oq4 chat` at −49.2% (81.0 → 41.1) — so
  oMLX's 35B levels here are early-window figures and its "+3.7% median" rise is the least
  stable number in §2. (Its seventh flagged row runs the other way, `optiq chat` at +17.7%.) The
  09-23 arm's 35B column had 10 flagged rows and none worse than −16.7%.

## Follow-ups

1. ~~Pin `cache_state` on the dense and MoE grids.~~ **Done 2026-09-29 (Decision 130):** an absent
   pin now means cache off on mlx-lm and OptiQ, so the dense and MoE grids run cache-off without one,
   and the cache-off re-run is in §2.2. A grid that wants the cache on must pin `on`. The header
   still records `None` either way, so cache-on and cache-off runs of the same grid must live in
   separate directories — the join guard cannot separate them.
2. **A replicate of the seedless grids** — or at least of the routing pair's MoE/35B columns —
   to bound the session term inside the seedless policy itself. The 21-hour 65.9 → 57.0 mlx-lm gap
   on one artifact says a single arm cannot carry a level.
3. **A third arm for dense vMLX `chat`/`prefill`** (`jang4s` ahead of `stock4bit` by 7.2–12.4%):
   the published arm called it a 0.2% tie and this one does not. One more column decides.
4. **Jason's call: which grid set the docs quote for dense and MoE** — the seeded 09-23/09-24
   figures, or these. They are not joinable, and the README and the format-axis papers currently
   quote the published ones.
