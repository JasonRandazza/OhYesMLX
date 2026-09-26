# The third 35B replicate: r2 and r3 agree within a few per cent, so the published 09-20 levels are the outlier

**Date:** 2026-09-25 (run 18:17:41 → 20:24:04 EDT)
**Milestone:** v3.1 Hardening — closes Follow-up 1 of `docs/research/2026-09-24-hardening-validation-grids.md` and the "Third 35B replicate not run" issue in `.paul/STATE.md`
**Harness:** 0.3.0 — `source_sha256 aa510642adcab88a3e3dd01c013d786201dcabb31203387bf09dfc0f052309f9`, identical in all five columns (r2's was `07387e201cc53557e5a32490bd1590886b05938f507c6eb2378407d45e8d5604`, commit `17b3791`)
**Runner:** `scripts/run_grid_35b.sh` → `results/harden-35b-r3/`
**Subject:** `Qwen3.6-35B-A3B` (35.95 B, 256 routed experts, 8 routed/token, hybrid attention) in four 4-bit artifacts — `stock4bit`, `oQ4`, `OptiQ`, `JANGTQ4` — across five serving runtimes, on the same gridspec as the published grid and r2: 3 workloads, 16 cells, 48 cell-workloads per grid
**Author:** Claude Opus coordinator

## Why this run exists

The hardening-validation paper re-ran the three published grids on the hardened harness and found
that its 35B grid replicated every **format ordering** and no **level**: at identical runtime
versions, mlx-lm, oMLX and vMLX measured 8–27% above the published 2026-09-20 grid, and rendering
the published run directories with current code reproduced the published figures exactly — so the
difference was in the measurements, not the code, and no cause was established. Its Follow-up 1
named the cheapest way to settle which night was the outlier: a third 35B replicate.
`.paul/STATE.md` carried it as "Decides whether the 2026-09-24 +8–27% 35B level shift
(mlx-lm/oMLX/vMLX, orderings held) is real".

This is that replicate. Same runner script, same gridspec, same pins, the same runtime versions as
r2, a fresh output directory. What it settles is written in §1 and the Conclusion; what it cannot
say is §5.

## What ran

| grid | runner | columns | wall clock (EDT) | exit |
|---|---|---|---|---|
| 35B MoE | `scripts/run_grid_35b.sh`, `--cache-state off` | mlxlm, omlx, optiq, vmlx, osaurus | 18:17:41 → 20:24:04 | 0 |

One run per runtime, five directories under `results/harden-35b-r3/`:

| runtime | run directory | column window (EDT) | version |
|---|---|---|---|
| `mlxlm` | `20260925T221741Z-format` | 18:17:41 → 18:39:39 | 0.31.3 |
| `omlx` | `20260925T223951Z-format` | 18:39:50 → 19:02:35 | 0.6.4 |
| `optiq` | `20260925T230247Z-format` | 19:02:46 → 19:25:06 | 0.5.13 |
| `vmlx` | `20260925T232518Z-format` | 19:25:18 → 19:57:30 | 1.6.59 |
| `osaurus` | `20260925T235742Z-format` | 19:57:42 → 20:23:55 | 0.25.12 |

- **All 48 cell-workloads are `PASS` with `n = 9` measured**, in all five columns; no `FAIL` row and
  no `N/A` row. (The `N/A` legend the current renderer prints appears in this grid's table head;
  nothing in this grid uses it.)
- **The pins line grew, and nothing in it is taken:** temperature `0.0`, seed `0`, warmup
  `{'cap': 20, 'floor': 10, 'mode': 'plateau', 'plateau_pct': 3.0, 'window': 5}`, measured `9`,
  cooldown `30.0` s, concurrency `1`, `prompt_tokens —`, `cache_state off`, plus the three Phase 4
  pins `kv_quant —`, `mtp_depth —`, `stream_experts —`. Workloads `chat` (max_tokens 128),
  `prefill` (64) and `decode` (512), identical messages in all runs.
- **Harness `0.3.0` at `aa510642…09f9` in all five columns.** r2 carried a different tree under the
  same version string; §4 says what moved and why it still counts as a replicate.
- **Every row on the four Python runtimes is `reasoning timed`; no OptiQ row is.** That is the A5 /
  Decision 119 split r2 shows and the split the published directories produce when rendered with
  current code. Decode tok/s times the same generated tokens whichever channel carries them; the
  mixed-channel caveat belongs to TTFT, and Decision 122 already refuses that ordering.
- **The runner's log holds no port sweep** — every sweep, including the one before the first
  column, found all five ports free — and it holds the Osaurus pin and its byte-exact restore
  (`cmp`). Each column then started, measured and released its port, exit 0.
- **Axis and caveat.** A column is one runtime with the format varying — the format axis the
  gridspec (`--study format`) declares; the runtime axis in §3 is the same three tables read
  across columns, which is a join of five independent runs, not an interleaved measurement. And
  the subject of this paper is a comparison **between** grids: three grids are three joins,
  compared here by the ratio of their cells' `decode_tps`. No join guard watches a cross-grid
  comparison; the pair that can be compared version-free is named in §1.

### Conditions

- **r3 ran on an evening, with the desktop in use** (session record: desktop applications open) —
  not the quiet night the Deferred Issue asked for. The harness cannot detect contention, so
  nothing in the runner log or the result files speaks to it.
- r2 ran overnight (23:18:38 → 01:35:48). The published grid's own directory stamps put its
  columns on the evening of 2026-09-19 EDT (`results/grid-35b/`, starts 2026-09-20T000155Z →
  020122Z), so an evening slot alone does not separate r3 from the published run — and the
  published run's conditions were never recorded, as r2's paper already said.
- Nothing else is recorded for r3's window; the drift field (§4) is the only condition evidence
  the run carries.

## Results

### 1. The levels: r2 and r3 agree within 2.7–6.8% on every runtime, and both read far above the published grid for mlx-lm, oMLX and OptiQ

**Metric and method.** `decode_tps`, the grid's one ordering metric (median per-request
`completion_tokens / (last content − TTFT)`). Per runtime, the median of the per-cell ratios
`decode_tps(later grid) / decode_tps(earlier grid)` over the **(format, workload) cells both grids
measured** — 9 for the four runtimes that serve three formats, 12 for vMLX, which serves four. The
median is of the cells' ratios, not of the columns' medians, so the min–max column below is the
spread that median summarizes. All fifteen figures were re-derived from the three committed
`grid.md` files and match the coordinator's to 0.1 pp — **no disagreement**.

| runtime | cells | r2 / published | r3 / published | r3 / r2 |
|---|---|---|---|---|
| `mlxlm` | 9 | **+19.7%** (+10.8 … +29.8) | **+22.2%** (+14.2 … +34.1) | **+2.7%** (+0.5 … +4.4) |
| `omlx` | 9 | **+16.8%** (+8.0 … +24.7) | **+25.6%** (+16.9 … +35.5) | **+6.6%** (+4.3 … +10.9) |
| `optiq` | 9 | **+10.7%** (+8.6 … +16.3) | **+16.9%** (+13.0 … +19.4) | **+5.6%** (+2.6 … +8.1) |
| `vmlx` | 12 | **+1.5%** (−1.9 … +10.2) | **+5.4%** (+1.4 … +18.3) | **+3.7%** (+2.2 … +7.8) |
| `osaurus` | 9 | **−8.1%** (−14.3 … −2.8) | **+2.7%** (−2.9 … +5.1) | **+6.8%** (+4.7 … +20.0) |

Reading it as two statements:

- **The two harness nights agree.** r2 and r3, three nights apart, put every runtime within
  **2.7–6.8%** of the other — about the size of an ordinary night-to-night difference at this
  precision, against r3's own within-grid drift spread of ±5.1%.
- **Both disagree with the published grid the same way, for three runtimes.** mlx-lm (+19.7,
  +22.2), oMLX (+16.8, +25.6) and OptiQ (+10.7, +16.9) sit 10–26% above their published cells in
  *both* replicates — each gap larger than the night-to-night spread between the two later grids
  (2.7–6.8% by median; the per-cell ranges overlap for oMLX alone). **The published levels for
  those three runtimes are the outlier, and the r2/r3 pair is the measurement to use.** That is
  where the hardening paper's "the 35B paper's cross-runtime statements are the ones this puts in
  doubt" lands, and it supersedes finding 17's cross-runtime levels — finding 17 being the project
  wiki's numbering for the 09-20 35B study.

The same levels on `stock4bit`, the one format every runtime serves (`decode_tps`, published → r2 → r3):

| workload | mlxlm | omlx | optiq | vmlx | osaurus |
|---|---|---|---|---|---|
| `chat` | 65.0 → **82.4** → **84.6** | 70.3 → **87.4** → **93.2** | 70.1 → **77.4** → **83.7** | 65.7 → **71.7** → **77.3** | 63.8 → 61.9 → **64.8** |
| `prefill` | 64.5 → **83.7** → **86.5** | 84.1 → **95.3** → **101.1** | 76.7 → **83.3** → **89.7** | 63.8 → **70.3** → **75.5** | 72.8 → 66.9 → 70.7 |
| `decode` | 64.1 → **75.2** → **78.3** | 67.9 → **74.1** → **82.2** | 66.6 → **73.7** → **79.4** | 66.4 → **71.7** → **75.2** | 58.1 → 55.8 → **59.6** |

**Why the claim is those three runtimes and not the other two.**

- **vMLX moved +1.5% then +5.4%** — at or under what one night can move a column here, so its
  published level is not established as wrong, in either direction.
- **Osaurus's two replicates straddle the published value** (−8.1% then +2.7%): the published
  reading sits between two later nights that disagree about its sign, so no level claim is
  available for that column from this data. (The two largest r3/r2 Osaurus cells, +17.9% and
  +20.0%, are both `optiq`-format cells; r2's own record annotates the +20.0% one's r2 value as
  `drift +12.6%`, i.e. still warming when measured — a per-cell explanation, not a column one,
  and not extended to the rest of the column.)
- The published grid, r2 and r3 all keep their own tables. Nothing is re-measured, re-rendered or
  replaced: this paper is the update, and the three grids stand as measured.

**One provenance note that supports the numbers above.** The three grids were re-rendered from
their run directories with the current tree's `ohyesmlx.cli grid`: r2's and r3's table sections
are byte-identical to their committed `grid.md` files, and the published grid's reproduces its
figures while adding the `reasoning timed` labels (retroactive, as r2's paper found). So the
tables compared here are what the code says today, and the published figures do not move under it.

### 2. The format axis: unchanged — `stock4bit > oq4 > optiq` in every column of all three grids except Osaurus's

Across 45 runtime-workload columns (5 runtimes × 3 workloads × 3 grids) the three-format ordering
holds in 38; the seven exceptions are all the Osaurus column (three workloads in the published
grid, one in r2, three in r3), and every one is a swap between the two formats below `stock4bit`
(printed tok/s, `stock4bit`'s lead over the pair in parentheses):

| grid | `chat` | `prefill` | `decode` |
|---|---|---|---|
| published | **optiq 60.9 > oq4 59.7** (+4.1) | **optiq 68.7 > oq4 67.8** (+5.0) | **optiq 55.9 > oq4 54.1** (+4.0) |
| r2 | oq4 58.0 > optiq 54.3 (+3.7) | oq4 63.5 > optiq 58.9 (+4.6) | **optiq 49.8 > oq4 48.7** (+7.1) |
| r3 | **optiq 64.0 > oq4 61.6** (+3.2) | **optiq 70.7361 > stock4bit 70.7089 > oq4 67.0** | **optiq 57.4 > oq4 56.1** (+3.5) |

Bold is a swap. Three refinements to the brief this paper was written from ("the pair swaps in pub
and r3 by 1–4 tok/s"):

- **r2 swaps the pair too, on `decode` alone**, by 1.1 tok/s (49.8 vs 48.7); its `chat` and
  `prefill` columns keep the published order, with the pair 3.7–4.6 tok/s apart the other way.
- **r3's `prefill` goes beyond a pair swap:** `optiq` 70.7361 edges `stock4bit` 70.7089 by
  0.03 tok/s — a tie at every printed precision, resolved upward by the ranking — so this is the
  one column of the 45 where `stock4bit` does not print first. `oq4` sits 3.7 below either.
- Every swap in all three grids is in a 0.9–3.7 tok/s band, inside this column's cell-to-cell
  movement: Osaurus is the runtime where the two formats below `stock4bit` are unresolvable at
  9 measured requests.

The fourth format's placing holds too: `jangtq4 > optiq` on vMLX in all three grids and all three
workloads, the narrowest margin 0.1 tok/s (r2 `chat`, 57.5 vs 57.4).

**This is finding 17's format half, intact.** The ordering the 09-20 grid published is the
ordering both later nights publish, on the same artifacts, with the levels moved by 10–26%: the
level shift did not move the format axis.

### 3. The runtime axis: the orderings moved, and the two replicates agree on the shape but not on the ties

The grid reads the same three tables across columns as the runtime axis. The nine rows that carry
all five runtimes (the three formats all five serve), each grid's own ordering:

| workload | format | published | r2 | r3 |
|---|---|---|---|---|
| `chat` | `stock4bit` | omlx > optiq > vmlx > mlxlm > osaurus | omlx > mlxlm > optiq > vmlx > osaurus | = r2 |
| `chat` | `oq4` | omlx > vmlx > optiq > mlxlm > osaurus | omlx > mlxlm > optiq > vmlx > osaurus | omlx > optiq > mlxlm > vmlx > osaurus |
| `chat` | `optiq` | omlx > osaurus > optiq > mlxlm > vmlx | omlx > optiq > mlxlm > vmlx > osaurus | omlx > mlxlm > optiq > osaurus > vmlx |
| `prefill` | `stock4bit` | omlx > optiq > osaurus > mlxlm > vmlx | omlx > mlxlm > optiq > vmlx > osaurus | omlx > optiq > mlxlm > vmlx > osaurus |
| `prefill` | `oq4` | omlx > optiq > osaurus > vmlx > mlxlm | omlx > optiq > mlxlm > osaurus > vmlx | = r2 |
| `prefill` | `optiq` | osaurus > optiq > omlx > mlxlm > vmlx | omlx > optiq > mlxlm > osaurus > vmlx | = r2 |
| `decode` | `stock4bit` | omlx > optiq > vmlx > mlxlm > osaurus | mlxlm > omlx > optiq > vmlx > osaurus | omlx > optiq > mlxlm > vmlx > osaurus |
| `decode` | `oq4` | vmlx > omlx > mlxlm > optiq > osaurus | omlx > mlxlm > optiq > vmlx > osaurus | omlx > optiq > mlxlm > vmlx > osaurus |
| `decode` | `optiq` | omlx > mlxlm > vmlx > optiq > osaurus | mlxlm > optiq > omlx > vmlx > osaurus | omlx > mlxlm > optiq > vmlx > osaurus |

What changed, read off the table:

- **oMLX keeps the top.** First in seven of nine published rows, seven of nine r2 rows and **all
  nine r3 rows** — by 3.5% (`decode` `stock4bit`) to 16.2% (`prefill` `oq4`). No row in any grid
  puts oMLX below third.
- **mlx-lm leaves the bottom.** It is 4th or 5th in seven of the nine published rows and never
  better than 2nd; in both r2 and r3 it is 2nd or 3rd in every row. This is the runtime-axis face
  of the level shift §1 measures.
- **vMLX settles at 4th–5th.** The published grid has it 1st–5th (its `decode` `oq4` first place
  is the widest single move); r2 and r3 both put it 4th or 5th in all nine rows.
- **Osaurus loses both podium places the published grid gave it** — 2nd on `chat` `optiq`, 1st on
  `prefill` `optiq` — and is never above 4th in r2 or r3. The `prefill` `optiq` row's winner is
  oMLX in both later grids.
- **r2 and r3 differ in six of the nine rows, and five of the six are ties being redrawn.** In five
  rows mlx-lm and OptiQ trade places on gaps of 0.6–3.7% in r3 (`chat` `oq4` 1.1%, `chat` `optiq`
  0.6%, `prefill` `stock4bit` 3.7%, `decode` `stock4bit` 1.4%, `decode` `oq4` 1.3%); the sixth,
  `decode` `optiq`, is oMLX passing both of them from 3rd to 1st (by 4.3% over mlx-lm and 4.8%
  over OptiQ) with their relative order unchanged. Two rows are more than a pair swap: `decode`
  `stock4bit` also puts oMLX first (5.0% over mlx-lm), and `chat` `optiq` also moves Osaurus back
  above vMLX at 4th/5th — that one is not a tie but Osaurus's largest cell move (54.3 → 64.0,
  +17.9%). Except for that cell, every position that changed between r2 and r3 did so between
  runtimes within 0.6–5.0% of each other.

**Caveat.** The runtime axis is not what this run varies — the gridspec holds the runtime constant
within a column — so §3 is a reading of the join. The published-grid movements (mlx-lm out of the
bottom, vMLX down, Osaurus off the podium) are the level shift's doing, not a re-ranking; the
r2↔r3 movements are cells the data cannot separate at this resolution.

### 4. What differs between the grids

| | published (09-20) | r2 (09-23/24) | r3 (09-25) |
|---|---|---|---|
| harness revision | not recorded (the field landed 09-23) | `07387e20…d5604` (commit `17b3791`) | `aa510642…09f9` |
| timing-channel labels | none printed | every row except OptiQ's | same as r2 |
| pins line | ends at `cache_state off` | same | + `kv_quant` / `mtp_depth` / `stream_experts`, none taken |
| drift annotations > ±5% | 11 (9 positive, 2 negative) | 10 (3 positive, 7 negative) | 1 (negative) |
| all 48 cell drifts | 31 positive / 17 negative, max 12.7% | 22 positive / 26 negative, max 16.7% | 31 positive / 17 negative, max 5.1%; 46 of 48 inside ±2% |
| runtime versions | optiq 0.5.6, osaurus 0.25.9; the other three as r3 | mlx-lm 0.31.3, oMLX 0.6.4, optiq 0.5.13, vMLX 1.6.59, osaurus 0.25.12 | same as r2 |
| window (EDT) | 2026-09-19 evening (dir stamps) | 23:18 → 01:36, overnight | 18:17 → 20:24, desktop in use |

- **The harness tree moved between r2 and r3** (Phase 4: the three new pins and their delivery
  checks, the report guards, the `N/A` entry). None of it changes how decode is measured when its
  pins are not taken — they are not taken here — and r3's tables re-render byte-identically under
  the current tree. But the sha differs, so "r3 vs r2" varies the night and, formally, the harness
  revision; what it holds constant is the runtime set, the pins and the gridspec.
- **The timing-channel labels are r2's addition** (Decision 119). The published `grid.md` prints
  none; r2 and r3 print the same split, OptiQ the only content-timed column — and rendering the
  published directories with current code restores the labels without moving a figure, so the
  channel assignment is not a difference between the nights: it was always there.
- **The drift field is the substantive difference in conditions.** The published grid's annotations
  lean **positive** — 9 of 11, the "still warming up" direction, so those cells' published rates
  are early-window figures — where r2's lean negative (7 of 10, the thermal direction) and r3 has
  one, negative. But the annotation fires only above ±5%: 28 of the published grid's 48 cells sit
  inside ±2%, and the shortfall §1 measures is uniform across four runtimes and their formats, not
  concentrated on the 11 annotated cells (six of which are in mlx-lm's or oMLX's columns). So the
  drift field is *consistent* with the published grid reading low and does not explain a uniform
  10–26% gap by itself. r3 is the flattest grid on record here: 46 of 48 drifts inside ±2%, none
  above +3.4%, one at −5.1%.
- **Versions.** r3 vs r2 is the version-free pair (all five runtimes identical); the published
  grid differs from both on OptiQ and Osaurus, as r2's paper recorded, which is one more reason §1
  does not lean on those two columns for the level claim.

### 5. What r3 cannot say

- **It cannot say why the published grid was low.** Neither the published run's record (its
  conditions were never recorded) nor r2's nor r3's identifies a cause. r2's candidates — host
  load on the 09-20 night, a different thermal state — remain candidates; the drift field gives
  the warm-up direction a role on 11 cells, not a cause.
- **It cannot price a quiet-night level.** r3 is uniformly 2.7–6.8% above r2, and nothing in the
  record says whether that is r3 reading high, r2 reading low, or ordinary day-to-day movement;
  the residual is not uniform at the cell level (Osaurus `prefill` `optiq` +20.0%, `chat` `optiq`
  +17.9%). r3 ran in an evening with desktop applications open — a third uncontrolled condition,
  not the quiet reference the Deferred Issue asked for — and the published grid's own stamps put
  it in an evening too, so "evening" alone is not the discriminator.
- **It does not re-open the format axis** (never in doubt after r2) **and does not establish a new
  runtime-axis ordering**: six of nine rows differ between r2 and r3, and all but one of those
  differences are cells within 0.6–5.0% of each other.
- **Nothing about accuracy.** 48/48 `PASS` in all three grids is the coherence floor — language,
  not correctness — and nothing here scores an output.
- **Nothing about memory, load or TTFT across runtimes:** this paper reads `decode_tps` only;
  `peak_mb` and `cold_load_s` orderings stay refused (Decision 120) and mixed-channel TTFT stays
  refused (Decision 122).
- **One replicate each.** "Agree within 2.7–6.8%" is two medians, not a pinned level.

## Conclusion

r2 (2026-09-23/24) and r3 (2026-09-25) agree with each other within 2.7–6.8% per runtime, and both
read 10–26% above the published 2026-09-20 grid for mlx-lm, oMLX and OptiQ. **Those three
published levels are the outlier, so finding 17's cross-runtime levels are superseded by the r2/r3
pair; its format orderings stand** — `stock4bit > oq4 > optiq` in every column of all three grids
except Osaurus's pair swap (and one print-tie its ranking resolves), and `jangtq4 > optiq` on vMLX
everywhere. vMLX's and Osaurus's published levels are not superseded by anything better: vMLX moved
too little to convict, and Osaurus's two replicates straddle it. Why the 09-20 night was low
remains unexplained, and r3 — an evening run with the desktop in use — does not supply the
explanation.

## What this does not claim

- It does not explain the published grid's level shortfall.
- It does not re-measure the published grid: its numbers are re-read and re-rendered, not re-run.
- It is not a fresh study of any runtime or artifact; it sets two existing grids' tables beside
  the published one.
- It is not an accuracy result, and coherence passing is not correctness.
- It reads no cross-runtime ordering of `peak_mb`, `cold_load_s` or TTFT; the only cross-grid
  metric in this paper is `decode_tps`.
- The runtime-axis readings in §3 are readings of a join, and the ties they resolve are not
  positions the data supports beyond a few per cent.

## Follow-ups

1. **Downstream readings of finding 17's cross-runtime levels should use the r2/r3 pair.** The wiki
   entry and STATE's finding numbering are the coordinator's to update; this paper is the evidence.
2. **The residual r3-above-r2 question needs a fourth night or an interleaved pair.** The cheapest
   probe is the two Osaurus `optiq` cells (+17.9%, +20.0%) against one mlx-lm cell, with the host
   state recorded this time.
3. **The runtime-axis tie problem is now measured, not hypothetical:** six of nine r2↔r3 rows
   differ, five of them on 0.6–3.7% gaps. STATE already carries "mark unresolvable ties" as the
   next renderer improvement; this grid is the case that justifies it.
