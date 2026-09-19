# Plan 02-04 — the accuracy Pareto synthesis: speed, memory and quality joined across two models, two runtimes and ten artifacts

Date: 2026-09-19. **No new measurement.** Nothing in this document was measured for it: no runtime
was started, no model was loaded, no benchmark item was run, no tensor was read. Every accuracy
figure is a quotation from the two Track 2 studies with its interval and its discordant count beside
it; every speed, footprint and disk figure is a quotation from Track 1 with its section named and
its drift marker intact. Where a source's own label and the design's rule disagree, this paper
prints both and says which one it applied.

Sources, and the short names this paper cites them by:

| short name | document | what is quoted from it |
|---|---|---|
| **`design`** | [`2026-09-17-v2-track2-accuracy-study-design.md`](2026-09-17-v2-track2-accuracy-study-design.md) | the coordinates (`§5.5`), the parity band (`§5.1`), the paired instrument (`§5.2`), the reading vocabulary (`§5.3`), the join rules (`§5.6`), the publication limits (`§5.7`), and the one sentence shape this paper may publish (`§6.5`) |
| **`acc-dense`** | [`2026-09-18-accuracy-dense.md`](2026-09-18-accuracy-dense.md) | Plan 02-02: `Qwen3.5-4B`, 11 cell runs, 30,580 scored item evaluations, 100% PASS |
| **`acc-moe`** | [`2026-09-19-accuracy-moe.md`](2026-09-19-accuracy-moe.md) | Plan 02-03: `LFM2.5-8B-A1B`, 8 cell runs, 9,340 scored item evaluations, 5 PASS + 3 FAIL |
| **`dense`** | [`2026-09-17-dense-jang-study.md`](2026-09-17-dense-jang-study.md) | Track 1 Plan 01-01: dense `decode_tps`, drift, `peak_mb`, `cold_load_s`, disk bytes |
| **`moe`** | [`2026-09-17-moe-jang-study.md`](2026-09-17-moe-jang-study.md) | Track 1 Plan 01-02: MoE `decode_tps`, drift, `peak_mb`, disk bytes |
| **`xrt`** | [`2026-09-17-jang-cross-runtime.md`](2026-09-17-jang-cross-runtime.md) | Track 1 Plan 01-03: the JANG duality, the runtime-axis rows, R4 |

---

## 1. Executive summary

### 1.1 The synthesis sentence, instantiated three times

The design pre-registers one sentence shape for this paper (`design §6.5`). It is printed here
verbatim before it is instantiated, because everything in §3–§6 is the filling-in of its blanks:

> *On `Qwen3.5-4B` and `LFM2.5-8B-A1B`, in vMLX 1.6.59 and Osaurus 0.25.x, at these pins and on
> this item set, format A's measured speed and density advantage was / was not bought with a
> measurable accuracy cost of Δ points (interval, K discordant items), and the frontier of
> non-dominated formats is…*

**Instantiation 1 — dense `Qwen3.5-4B`, vMLX 1.6.59, A = `JANG_4S`, B = `stock4bit` (the
near-equal-precision control):**

> …`JANG_4S`'s measured **+22.6%** sustained-decode advantage over the uniform-4-bit control **was
> not** bought with a measurable accuracy cost: Δ = **+0.53 pp** MMLU (95% CI [−0.38, +1.43] pp,
> **K = 110** discordant items) — a tie inside the pre-registered ±1.5 pp band — and against the
> column's best portable (`oq4`) the same bundle is **+13.9%** faster at Δ = +0.22 pp
> ([−0.66, +1.10] pp, K = 105, also a tie); the frontier of non-dominated formats on the MMLU axis
> is **{`JANG_4S`, `oq4`, `stock4bit`}**, with `oq4e` outside it and leading the column on IFEval
> instead.

**Instantiation 2 — dense `Qwen3.5-4B`, Osaurus 0.25.6, A = `JANG_4S`, B = `optiq` (the column's
only pair with a published interval):**

> …`JANG_4S`'s **+9.8%** decode advantage over `optiq`, and its 836.2 MB smaller bundle, were
> bought with a measurable accuracy **gain** rather than a cost: Δ = **+3.82 pp** MMLU
> ([+2.45, +5.18] pp, **K = 175**). Against the column's best portable (`oq4`) the decode lead is
> +9.5% and the accuracy pair has **no interval in the record**, so no Δ is quoted for it; the
> frontier of non-dominated formats on the MMLU axis is **{`JANG_4S`, `oq4e`, `oq4`}**, and
> **`optiq` is eliminated**.

**Instantiation 3 — MoE `LFM2.5-8B-A1B`, vMLX 1.6.59, A = `JANG_2L`, B = `stock4bit` (the pair the
vendor claim names):**

> …`JANG_2L`'s density advantage — **36.0%** fewer bytes on disk and **30.5%** lower peak footprint
> than the control, at a **0.87%** decode tie — **was not priced**, in either direction: the pair's
> MMLU leg **does not exist** (the runtime refused item 80/1,140 with HTTP 502 in both visits,
> 9 h 23 m apart), and on the one task the cell completed, IFEval, the difference is **+4.80 pp**
> ([−1.17, +10.77] pp, **K = 58**) — indeterminate at n = 250, with no collapse. The frontier of
> non-dominated formats is **{`stock4bit`, `oq4e`}** with **`JANG_2L`'s position undetermined**,
> and **`optiq` and `oq4` eliminated**.

### 1.2 The thesis: accuracy preserves the JANG Duality

Track 1 closed on the JANG duality — on the dense model the JANG bundle is a *throughput* winner,
on the MoE it is a *density* winner, and the decode-rate outcome splits by model (R4) — with the
standing rule that every vMLX number is a floor for the shipped JANG path, not a measurement of it,
because JIT and native MTP were pinned off (`xrt §1.2`, `§8.2`; `dense §8.4`; `moe §8.5`). The third
coordinate does not disturb either half. It sharpens both:

- **Dense: the speed is free.** `JANG_4S` declares 4.15 average bits against the control's uniform
  4.00 and carries 4.8% more bytes on disk (+146.3 MB), and it decoded ahead of the best portable
  by a replicated **+13.9% / +16.8%** in vMLX and **+9.5% / +9.0%** in Osaurus (`dense §1.2`;
  `xrt §1.1`). On MMLU it is at parity with the control (+0.53 pp, K = 110, the whole interval
  inside the band), and this is the program's only **replicate-gated P1** reading: the dense
  replicate re-ran both cells and reproduced their MMLU scores **exactly** — 0 of 6,840 answered
  items differed (`acc-dense §1.2`, `§5`). The 4.8% disk premium buys a replicated decode lead of
  **+9.0% to +22.6%** at **zero measured quality cost**.
- **MoE: the density is free on the floor that was measurable.** `JANG_2L` returns **36.0%** of the
  disk (3.062 GB against the control's 4.782 GB) and **30.5%** of the peak footprint (3,624 MB
  against 5,214 MB) for a decode rate that ties in vMLX (+0.87% / −0.50%, R3) — and the two tasks
  that could have failed it did not: instruction following at 2.37 average bits is **above** the
  control's level (IFEval 56.8% against 52.0%, +4.80 pp, indeterminate at n = 250), and the two
  scores that do sit below a task floor carry measured instrument causes rather than collapses.
  The design's live hypothesis — P3, quality collapse — **does not fire** on anything `JANG_2L`
  completed (`acc-moe §1.2`, findings 2 and 5).

The one thing the accuracy coordinate takes away from the MoE half is certainty in the other
direction: the density is not *shown* to cost MMLU points, and it is not *shown* not to, because
that comparison does not exist. The vendor parity claim is **unanswered** — neither reproduced nor
falsified (`acc-moe §5.3`).

### 1.3 OptiQ: eliminated on both frontiers

`optiq` is the one format that loses on every axis in both models, and it is eliminated by measured
pairs rather than by a glance at point scores:

| model / runtime | what `optiq` measured there | the verdict |
|---|---|---|
| dense `Qwen3.5-4B`, Osaurus | MMLU **61.05%** — 3.11 to 4.39 pp below every column-mate, p ≤ 2.4 × 10⁻⁸ (`acc-dense §3.2`); decode 38.7, a 0.26% / 0.52% **tie** with `oq4` / `oq4e` (`dense §4.1`); peak 2,472 MB, a 0.24% tie with `oq4` and 256 MB above `oq4e`; disk **4.044 GB** against 3.161 / 3.168 GB for the two portables, ≈28% larger | dominated by `JANG_4S` on (x, decode) and (x, disk); by `oq4e` on (x, peak) and (x, disk); by `oq4` on (x, disk) — **off the frontier** |
| MoE `LFM2.5-8B-A1B`, vMLX | MMLU **28.25%** — 7.28 pp below the control (K = 291, p = 1.3 × 10⁻⁶) and 7.98 pp below `oq4e` (K = 277, p = 4.9 × 10⁻⁸); decode 100.6 against the control's 115.3 (−12.8%); peak 5,869 MB against 5,214 MB; disk 5.473 GB against 4.782 GB | **`stock4bit` dominates it on all three pairs** — off the frontier |

The dense half of Q3 is the design's pre-registered shape arriving exactly as written (`design
§2.1`: "if their accuracies also tie, `optiq` is strictly dominated on two axes"), except that the
accuracies did **not** tie — they separated, against `optiq`, by more than 3 pp with extreme
significance, which is the stronger version of the same verdict. The MoE half arrives one step
weaker than the design's `§5.7` example sentence anticipated: that sentence named `JANG_2L` as the
dominator (15.6% faster, 44% smaller), and `JANG_2L` has no MMLU coordinate, so the domination
that is published is the control's (`acc-moe §5.4`).

**The counter-current rides with the finding and is not hidden.** On the MoE column `optiq` is also
the **best** cell on IFEval (62.4%, +10.40 pp over the control, K = 50, p = 0.0003) and it beats
`oq4` on both accuracy and speed (`acc-moe §3.3`, `§5.4`). OptiQ is eliminated from the MMLU
frontier; it is not condemned across every task, and this paper does not condemn it across every
task.

### 1.4 Outlier protection: two artifacts, opposite sides of the control

The design's Q4 is "does outlier-channel protection (`oQ4` / `oQ4e`) buy task accuracy over stock
4-bit?" The measured answer is the same shape in both models — **the two protected artifacts land
on opposite sides of the control** — with an order-of-magnitude difference in how far apart they
land:

| | dense `Qwen3.5-4B` (vMLX) | MoE `LFM2.5-8B-A1B` (vMLX) |
|---|---|---|
| `oq4e` vs the control, MMLU | **−1.01 pp** ([−1.86, −0.15], K = 99) — direction resolved, magnitude inside the band | **+0.70 pp** ([−2.27, +3.67], K = 298) — **indeterminate**, effective parity |
| `oq4` vs the control, MMLU | **+0.31 pp** ([−0.46, +1.08], K = 85) — a tie | **−13.60 pp** ([−16.60, −10.59], K = 305, p = 1.8 × 10⁻¹⁹) — floor-shaped 21.93% |
| the two protected artifacts against each other, MMLU | **+1.32 pp** ([+0.40, +2.23], K = 118) | **+14.30 pp** ([+11.29, +17.31], K = 307, p = 2.5 × 10⁻²¹) — the column's largest gap |
| IFEval, the sharper half | `oq4e` **+5.20 pp** over the control ([+1.86, +8.54], K = 29) | `oq4e` **+8.80 pp** over the control ([+3.15, +14.45], K = 52, p = 0.0032); `oq4`'s +5.60 pp is indeterminate |

Two readings follow, and both are in the sources' own vocabulary:

1. **Protection is not one variable.** On the dense model the two protected builds bracket the
   control by ~1 pp; on the MoE they bracket it by 14.30 pp while their bundles differ by
   **9,235 bytes** on disk. A single mechanism that "buys accuracy" cannot produce both columns.
2. **The MoE decision the evidence does support: run the `oq4e` build or the control, not the
   `oq4` build.** `oq4` sits below the four-option floor at 21.93% with its response-form counts
   named, is dominated on every pair, and its +14.30 pp deficit against `oq4e` is the campaign's
   most significant single difference. **The attribution limit is not optional and rides with the
   recommendation:** `stamsam/LFM2.5-8B-A1B-oQ4` and `brainworkup/LFM2.5-8B-A1B-oQ4e` are two
   publishers' ≈4-bit artifacts, so the gap is a measured difference between two recipes and
   **not** a one-variable measurement of protection; this synthesis recommends artifacts, not a
   mechanism (`acc-moe §1.2` finding 4, `§5.5`).

On the dense model the same discipline gives a softer recommendation: `oq4` buys nothing over the
control (tie on MMLU, +0.40 pp on GSM8K indeterminate) and `oq4e` is the column's IFEval leader at
a ~1 pp MMLU cost — a real but small trade-off, priced in §4.

### 1.5 What travels with all of it

Not faster in general, not why, not equal precision anywhere on the MoE, not a cross-runtime memory
or load ranking, not an accuracy claim beyond this harness and these items, and not a number read
from inside the band. The full list is `design §7` and `§5.7`, restated for this paper in §6.3.

---

## 2. Method: the framework this paper applies

### 2.1 Coordinates

For a cell `c` = (format, runtime), the design's `§5.5` coordinates are:

```
x(c)   = score(c, t)     accuracy on task t — MMLU on the primary axis, each other task on its own
y₁(c)  = decode_tps(c)   quoted from Track 1's record for this cell (never re-measured)
y₂(c)  = peak_mb(c)      within one runtime only
y₃(f)  = disk_bytes(f)   the format's own bytes, runtime-independent
```

Two things about that table of coordinates are load-bearing and are restated here because every
number in §3–§6 inherits them:

- **`peak_mb` does not cross a runtime boundary.** vMLX reports a footprint within a few percent of
  the weight bytes; Osaurus reports roughly half of them because it holds weights in wired,
  GPU-pinned pages that `phys_footprint` charges differently (`dense §7.1`; `moe §7.1`; the
  measured basis is `2026-09-16-footprint-is-not-one-quantity.md`). Every frontier in this paper
  names its runtime in the header, and no memory ranking is drawn across one.
- **Disk is runtime-independent and byte-exact.** It is the one resource coordinate that can be
  compared across the whole matrix, and it is quoted to the byte from the design's artifact table
  (`design §2.4`), which agrees with every Track 1 row.

### 2.2 Dominance with bands

A cell `c` **dominates** a cell `c′` on the pair `(x, y)` when **all** of the following hold
(`design §5.5`):

1. `x(c) − x(c′) > 1.5 pp` with the paired interval excluding zero — **a difference, not a tie, and
   not indeterminate**;
2. `y(c)` is at least as good as `y(c′)` by more than `y`'s own band — **2.5%** for throughput
   (Track 1's tie band, the largest gap v1 observed to change places when the measurement window
   moved), **1%** for memory (the scale at which Track 1's own replicate agreed with itself: 1 MB
   and 21 MB on the MoE cells, `moe §7.1`), and **exact equality** for disk;
3. at least one of the two inequalities is strict.

A pair inside the bands on both axes is a **tie**, printed as two points, not as a domination.

### 2.3 Frontier membership, and the one place two readings are possible

The design defines per-pair dominance and then says: *"A point that no other point dominates is on
the frontier"* (`design §5.5`), and the MoE study applied it as *"the dominance is per-pair … and it
holds on every pair, so OptiQ is eliminated"* (`acc-moe §5.2`). This paper reads that as: **a cell is
off the frontier when some other cell dominates it on the accuracy axis and on at least one resource
axis; it is on the frontier otherwise**, with per-pair verdicts printed for every cell either way.

Where a stricter reading would change an answer, the paper says so in the table's own note rather
than hiding the choice. It changes exactly one bin in §3: under a reading that requires a single
comparator to dominate on *every* resource pair, `oq4e` would stay on Table 1's frontier instead of
leaving it, because its bundle is 39.4 MB smaller than `JANG_4S`'s (`design §2.4`). The same
strict reading would also leave dense `optiq` on Table 2's frontier — which contradicts the
pre-registered Q3 shape (`design §2.1`) and the dense study's own verdict (`acc-dense §6.2`) — and
this paper takes that as the reading being wrong, not the verdict.

### 2.4 No task pooling, and no composite index

Three rules from the project's own decisions govern the tables, unchanged:

> **Floors then one ordering metric, never a blended score** … a single number would encode an
> arbitrary trade-off as though it were measured. (`.paul/STATE.md`, Decisions; `docs/interfaces.md`)

> Figures are never averaged across workloads. (`docs/interfaces.md`, Workloads)

> **No quality-adjusted single number.** No "accuracy per token", no weighted score, no composite
> index. The Pareto frontier of `§5.5` is the honest replacement: it keeps every coordinate
> measured and lets the reader see the trade instead of the study choosing one. (`design §5.4`)

Applied here: MMLU, GSM8K and IFEval are three readings, never one; a format that gains on MMLU and
loses on IFEval is a finding and is printed as one (`oq4e` on the dense vMLX column is exactly that
case); where a summary is genuinely needed the permitted form is a **count**, not a mean. The
`R_quality/...` slopes of §4 are pair properties with both cells named — they are rates, not scores,
and no reader is offered a ranking derived from them.

### 2.5 The join: quotations, never re-measurements

Every `decode_tps`, drift annotation, `peak_mb` and byte count in this paper is a quotation from
Track 1 with the section it came from printed beside the table (the coordinates the design
pre-collected live in `design §5.6`; their homes are `dense §3.1`, `dense §4.1`, `moe §3.1`,
`moe §4.1`). **Track 2 never produced a rate and Track 1 never produced a score**, and the two are
joined here editorially, by `(format, runtime)`, exactly as `design §1.4` and `§5.6` require —
not by `report.py`, whose join guards refuse directories whose pins differ, as Track 1's and Track
2's do (`cache_state`, workload literals, record shape).

Three rules for reading those quotations, each learned the hard way:

1. **A speed coordinate carries its drift marker into the table.** Four cells in this paper carry
   drift of ±10% or more, and one is in a class of its own: `oq4__vmlx`'s **+76.0%** means its
   65.6 tok/s narrates its measurement window more than its artifact (`moe §3.1`). Its accuracy
   scores are unaffected — a score does not depend on the speed coordinate — but no frontier
   position or slope that uses that cell's decode rate may be read as a property of `oq4` alone.
2. **Absolute levels are not visit-stable.** Every comparison in this paper is *within* a visit —
   two cells measured in the same campaign window — and R-reproduce fired on 9 of 12 dense cell
   pairs and 1 of 12 MoE pairs (`dense §8.3`; `moe §8.1`). Reading any single figure as "the
   bundle's rate on this machine" is what that rule forbids.
3. **The speed coordinate of a Track 2 cell is that cell's own Track 1 figure from its own column**
   — never a figure carried across pin sets (`design §2.4`, `§5.6`).

### 2.6 Replicates, gates and bins

The design publishes its P1/P2 readings only where the primary and the replicate agree on the bin
(`design §5.1`–`§5.3`). What actually got replicated, across both accuracy campaigns:

| campaign | replicated cells (MMLU only) | outcome |
|---|---|---|
| dense (`acc-dense §5`) | `stock4bit__vmlx`, `jang4s__vmlx`, `jang4s__osaurus` — 6,840 item evaluations in a separate pass with reversed order | **100.000% item agreement, 0 disagreements, Δ = 0.0000 pp on every cell** |
| MoE (`acc-moe §4`) | `stock4bit__vmlx`, `jang2l__vmlx` | `stock4bit` 405/1,140 in both visits, 1,140/1,140 strings identical; `jang2l` **halted at item 80 in both visits** — no score to compare |

So exactly one comparison in the program is replicate-gated end to end: **Q2's dense pair**
(`JANG_4S` vs `stock4bit` on vMLX, MMLU). Every other comparison in this paper is a single-visit
reading, and each one says so. This is the same discipline the MoE study applied when it published
no P1/P2 label on any row (`acc-moe §3`, rule 2) — and it is why the dominance verdicts in §3 rest
on the *statistical* condition (`design §5.5` condition 1: > 1.5 pp with the interval excluding
zero) while the P1/P2 vocabulary appears only where the gate is satisfied.

The three pre-registered bins (`design §5.2`), and the states this paper prints:

| bin | condition | printed as |
|---|---|---|
| **tie (parity)** | \|Δ\| ≤ 1.5 pp **and** the paired 95% interval entirely inside ±1.5 pp | "a tie" |
| **difference** | \|Δ\| > 1.5 pp **and** the interval excludes zero **and** the replicate agrees | "Δ points (interval, K)" — the source studies' "interval excludes zero" condition, with the gate noted |
| **indeterminate** | everything else | "indeterminate at this item count: Δ, interval, K — not evidence of parity and not evidence of a difference" |

### 2.7 Where the record's own labels differ from the rule

Three places in the sources carry a label this paper could not reproduce under the design's rule.
Each is printed with both readings rather than smoothed:

1. **`acc-dense §3.1` labels `oq4e` vs `stock4bit` "P1 (Parity)"** at Δ = −1.01 pp with interval
   [−1.86, −0.15]. The design's tie needs *both* conditions, and that interval escapes the ±1.5 pp
   band; the MoE study called the identical shape (`oq4e` vs `stock4bit`, +0.70 pp) **indeterminate**
   for exactly that reason (`acc-moe §3.4`). This paper calls it indeterminate, uses its resolved
   direction for the slope in §4, and prints the source's label beside it.
2. **`acc-dense §6.1`/`§6.2` annotate `oq4` as "dominated by `JANG_4S`"** and use a footprint
   column (2,795–2,842 MB) that matches no Track 1 decode-workload quotation (3,819–3,946 MB).
   Under the design's rule a dominance needs an accuracy *difference* to fire, and `JANG_4S` vs
   `oq4` is a tie (+0.22 pp, K = 105) — so this paper's Table 1 gives `oq4` no domination and uses
   Track 1's own `peak_mb` figures, which the design's `§5.6` table also carries. The discrepancy is
   recorded in Appendix B so a reader can audit it.
3. **The dispatch record's shorthand "reasoning truncation halt"** for the vMLX 502s is corrected
   by the study that measured them: the refusals are **not** cap truncations (the cap was 1,024
   tokens and the refused completions ended at 196, 432 and 507 tokens) — they are item-level
   refusals of a completion with no visible answer channel (`acc-moe §1.2` finding 5). §5.1 uses the
   measured mechanism and names the shorthand.

---

## 3. The three frontiers

Three of the design's four possible frontier tables are drawable (`design §5.5`); the fourth is not,
and §3.4 says why. Every resource figure in every table is a Track 1 quotation with its drift
marked; every score is a Track 2 quotation with its `n` printed.

### 3.1 Table 1 — `Qwen3.5-4B` in vMLX 1.6.59 (four of five dense formats)

*Column cast: `jang4s`, `stock4bit`, `oq4`, `oq4e`. `optiq` is not in this column and cannot be:
vMLX's multimodal path requires 297 vision parameters that the dense OptiQ artifact's per-layer map
omits (0 of 249 entries), so the cell was never attempted and renders `—`, never a synthetic FAIL
(`design §2.1`; `2026-09-15-grid-loadability-probe.md`). Scores: `acc-dense §2.1`. Resources:
`dense §3.1` (decode, drift, peak) and `design §2.4` (disk).*

| # | format | MMLU (n = 2,280) | decode tok/s (drift) | peak MB | disk GB | dominance verdict | frontier bin |
|---|---|---|---|---|---|---|---|
| 1 | `jang4s` | **68.42%** | **54.2** (+5.9%) | 3,820 | 3.207 | dominates `oq4e` on (x, decode) [+17.8%] and (x, peak) [126 MB, 3.2%]; every other pair is a tie | **on** — throughput and MMLU leader |
| 2 | `oq4` | 68.20% | 47.6 (+14.2%) | 3,819 | 3.161 | not dominated on any pair (every accuracy gap above it is a tie); dominates no one on this axis | **on** — second-fastest, second-smallest disk, inside the accuracy tie cluster |
| 3 | `stock4bit` | 67.89% | 44.2 (+16.6%) | 3,843 | **3.061** | not dominated on any pair; the only in-column control | **on** — smallest disk; every accuracy difference against it is a tie |
| 4 | `oq4e` | 66.89% | 46.0 (+5.4%) | 3,946 | 3.168 | **dominated by `jang4s` on (x, decode) and (x, peak)**; escapes on (x, disk) only (39.4 MB smaller) | **off** — and the column's **IFEval** leader (84.0%) instead |

The paired evidence behind those verdicts, every row on identical items (`acc-dense §3.1`):

| pair (A vs B) | Δ MMLU | 95% CI | K | this paper's bin |
|---|---|---|---|---|
| `jang4s` vs `stock4bit` (**Q2**) | **+0.53 pp** | [−0.38, +1.43] pp | 110 | **tie** — P1 (Parity), replicate-gated and confirmed |
| `jang4s` vs `oq4` | +0.22 pp | [−0.66, +1.10] pp | 105 | tie |
| `oq4` vs `stock4bit` | +0.31 pp | [−0.46, +1.08] pp | 85 | tie |
| `oq4e` vs `stock4bit` | −1.01 pp | [−1.86, −0.15] pp | 99 | indeterminate by `§5.2` (direction resolved, magnitude inside the band; source label "P1 (Parity)" — see §2.7) |
| `oq4` vs `oq4e` | +1.32 pp | [+0.40, +2.23] pp | 118 | indeterminate by `§5.2` (same shape; source label "Slight Lead") |
| `jang4s` vs `oq4e` | +1.54 pp | [+0.56, +2.51] pp | 131 | difference condition met (> 1.5 pp, interval excludes zero); this pair has no replicate |

**What the column's frontier says in one sentence:** the dense vMLX column is an accuracy tie
cluster — three of the four formats are mutually indistinguishable on 2,280 MMLU items — so the
frontier is decided by resources: `jang4s` owns the decode rate, `stock4bit` the disk, and `oq4`
survives because nothing is separated from it on any axis. `oq4e` is the one cell a single
comparator separates from on accuracy and beats on two resources, and it stays in the
recommendation (§6) on a different axis, not on this one.

### 3.2 Table 2 — `Qwen3.5-4B` in Osaurus 0.25.6 (four of five dense formats)

*Column cast: `jang4s`, `oq4`, `oq4e`, `optiq`. `stock4bit` is not in this column: Osaurus lists the
artifact in `GET /v1/models` and refuses it at request time as `not installed or registered with any
provider` — offering is not serving (`design §2.2`). Scores: `acc-dense §2.2`. Resources:
`dense §4.1` (decode, drift, peak), `design §2.4` (disk).*

| # | format | MMLU (n = 2,280) | decode tok/s (drift) | peak MB | disk GB | dominance verdict | frontier bin |
|---|---|---|---|---|---|---|---|
| 1 | `jang4s` | 64.87% | **42.5** (+5.1%) | 3,400 | 3.207 | dominates `optiq` on (x, decode) [+9.8%] and (x, disk) [836.2 MB smaller]; loses (x, peak) to `optiq` (928 MB) | **on** — throughput leader |
| 2 | `oq4e` | **65.44%** | 38.6 (+6.2%) | **2,216** | 3.168 | dominates `optiq` on (x, peak) [256 MB, 10.4%] and (x, disk) [875.7 MB]; the (x, decode) pair with `optiq` is a 0.52% tie | **on** — MMLU and footprint leader |
| 3 | `oq4` | 64.17% | 38.8 (+18.7%) | 2,466 | 3.161 | dominates `optiq` on (x, disk) [883.1 MB]; its pairs with `jang4s` and `oq4e` have **no published interval** (point gaps +0.70 pp and +1.27 pp, inside the band as point estimates) | **on** — no resolvable deficit; decode ties the portables |
| 4 | `optiq` | **61.05%** | 38.7 (−1.0%) | 2,472 | **4.044** | **dominated by `jang4s` on (x, decode) and (x, disk)**; by `oq4e` on (x, peak) and (x, disk); by `oq4` on (x, disk) | **off — the column's only elimination; Q3's dense half** |

The paired evidence this table uses is the column's only published set, all three against `optiq`
(`acc-dense §3.2`):

| pair (A vs B) | Δ MMLU | 95% CI | K | p (McNemar) | reading |
|---|---|---|---|---|---|
| `jang4s` vs `optiq` | **+3.82 pp** | [+2.45, +5.18] pp | 175 | 1.3 × 10⁻¹⁰ | interval excludes zero |
| `oq4e` vs `optiq` | **+4.39 pp** | [+2.76, +6.01] pp | 198 | 4.2 × 10⁻¹² | interval excludes zero |
| `oq4` vs `optiq` | **+3.11 pp** | [+1.82, +4.41] pp | 165 | 2.4 × 10⁻⁸ | interval excludes zero |
| `jang4s` vs `oq4`, `oq4e` vs `oq4`, `jang4s` vs `oq4e` | +0.70, +1.27, −0.57 pp (point scores) | **not published** | — | — | **no verdict possible** — the design refuses an unpaired or un-quantified reading (`design §5.2`) |

**The three portables are a decode tie, and the rank numbers are not the claim.** 38.8 / 38.7 /
38.6 span 0.52% end to end, well inside the 2.5% band, so `optiq` is *not* slower than its
neighbours by the project's own rule — which is precisely why its elimination is an accuracy-and-
resource verdict and not a speed one (`dense §4.1`).

### 3.3 Table 3 — `LFM2.5-8B-A1B` in vMLX 1.6.59 (all five MoE formats)

*The one column in the project with no structural hole: all five labels load in this runtime
(`moe §1.1`). Scores: `acc-moe §2.1`. Resources: `moe §3.1` (decode, drift, peak), `design §2.4`
(disk); MMLU `n = 1,140` — the design's `§3.3` budget dial was applied (20 items/subject).*

| # | format | MMLU (n = 1,140) | decode tok/s (drift) | peak MB | disk GB | dominance verdict | frontier bin |
|---|---|---|---|---|---|---|---|
| 1 | `jang2l` | **FAIL** — halted at item 80/1,140, both visits | **116.3** (+0.5%) | **3,624** | **3.062** | **no verdict possible** — every pair turns on the coordinate it does not have | **undetermined** — fastest, smallest and lightest cell in the column |
| 2 | `stock4bit` | 35.53% | 115.3 (+3.9%) | 5,214 | 4.782 | dominates `optiq` on **all three** pairs; dominates `oq4` on **all three** pairs; its pair with `oq4e` fails the accuracy condition first (inside the band) | **on** — the control, and the only cell that dominates anyone on every axis |
| 3 | `oq4e` | **36.23%** | 97.0 (+10.9%) | 5,416 | 4.995 | dominates `optiq` on (x, peak) and (x, disk); dominates `oq4` on (x, decode) [+47.9%]; the (x, decode) pair with `optiq` is OptiQ's on the resource half (3.6% faster) and nobody's overall | **on** — the column's highest measured MMLU level |
| 4 | `optiq` | 28.25% | 100.6 (+6.1%) | 5,869 | 5.473 | **dominated by `stock4bit` on all three pairs**; itself dominates `oq4` on (x, decode) [+53.4%] | **off — Q3's MoE half** |
| 5 | `oq4` | **21.93%** ⚠ | 65.6 ⚠ (**+76.0%**) | 5,415 | 4.995 | **dominated by `stock4bit` on all three pairs**; dominated by `optiq` on (x, decode) | **off** — and its decode coordinate narrates its window, not the artifact |

⚠ **Two annotations on `oq4`'s row, both required before its numbers are read.** Its MMLU level sits
below the four-option floor at 21.93% with the measured cause named: the task's filter returns the
response whole and `exact_match` compares it to a one-character key, and its responses took the
bare-letter form less often than any other cell's (347 of 1,140) — a form-variance effect the study
quantifies but does not correct for (`acc-moe §2.1`). Its decode coordinate carries the campaign's
largest drift, **+76.0%** (early median 60.6 tok/s against a late 106.7), so 65.6 is an early-window
figure and no frontier position or slope built on it may be read as a property of `oq4` alone
(`moe §3.1`).

The paired evidence (`acc-moe §3.1`, all pairs on 1,140 common items):

| pair (A vs B) | Δ MMLU | 95% CI | K | p (exact) | this paper's bin |
|---|---|---|---|---|---|
| `stock4bit` vs `optiq` | **+7.28 pp** | [+4.35, +10.21] pp | 291 | 1.3 × 10⁻⁶ | interval excludes zero |
| `oq4e` vs `optiq` | **+7.98 pp** | [+5.12, +10.84] pp | 277 | 4.9 × 10⁻⁸ | interval excludes zero |
| `oq4` vs `stock4bit` | −13.60 pp | [−16.60, −10.59] pp | 305 | 1.8 × 10⁻¹⁹ | interval excludes zero |
| `oq4e` vs `oq4` | **+14.30 pp** | [+11.29, +17.31] pp | 307 | 2.5 × 10⁻²¹ | interval excludes zero — the column's largest gap |
| `optiq` vs `oq4` | +6.32 pp | [+3.52, +9.11] pp | 264 | 1.1 × 10⁻⁵ | interval excludes zero |
| `oq4e` vs `stock4bit` | +0.70 pp | [−2.27, +3.67] pp | 298 | 0.685 | **indeterminate** — the control is not dominated |
| `jang2l` × any cell | **no samples on either side** | — | 0 | — | **not computable** — a halt is published as a halt |

**The one sentence this table licenses:** on this model, in this runtime, the MMLU axis separates
the cast into a top pair that cannot be ordered by the rule (the control and `oq4e`, +0.70 pp with
an interval that escapes the band) and a bottom pair that can (`optiq` and `oq4`, each dominated on
every axis by the control) — plus a JANG bundle that is the best of the five on both resources it
has coordinates for and has no accuracy coordinate at all.

### 3.4 Why the MoE Osaurus frontier is not drawn

The design pre-registered this table as un-drawable (`design §5.5`: *"`LFM2.5-8B-A1B` | `osaurus` |
— not drawn —"*), and nothing in Track 2 changed that. Three independent reasons, each sufficient:

1. **Two of the five cells have no speed coordinate.** `oq4e__osaurus` and `optiq__osaurus` both
   FAIL their decode row with `no content completion tokens from token_source='none', so decode
   tok/s is undefined` — the runtime answered in two channels and reported no usage block, so no
   rate is attributable. Both cells **produced language** and passed the coherence floor; they fail
   the *metrics* floor, which is the failure mode that associates with **Osaurus on the 512-token
   shape**, not with one quantization (`moe §4.1`, `§8.4`). A frontier would be three points and two
   holes.
2. **Track 2 ran one cell in that runtime, not a column.** `jang2l__osaurus` is Study 2C's MoE leg
   (`acc-moe §2.2`), and the four portables have no Osaurus accuracy measurement at all. A frontier
   needs at least two comparable coordinates; this row has one.
3. **That one cell's MMLU number is an extraction artifact, not a capability reading.** Of its
   1,140 responses, 845 are prose, 171 are empty and 124 reduce to a bare letter; `exact_match`
   scored the 43 bare letters that matched, and prose scores zero however right it is — two verbatim
   samples are printed in the source, both correct, both scored 0. A stated-rule diagnostic finds a
   lower bound of 9.9% of items whose text names the right answer, against the recorded 3.77%
   (`acc-moe §2.2`). The number is published with that label, is below the 25% floor with a measured
   cause, and draws no reading.

What the omission costs is stated rather than hidden: Track 1's MoE Osaurus column is where
`stock4bit` posts the campaign's **fastest** decode number (123.0 tok/s, a replicated 5.12% / 9.80%
lead over `jang2l` — `moe §1.2`, `§4.1`), so the runtimes disagree about the MoE's decode ordering
and the accuracy coordinate that might arbitrate is missing on one side.

### 3.5 The secondary-task axes

The design runs one frontier per task in principle (`design §5.5`: "per model, per runtime, per
task"), the dispatch fixes MMLU as the primary axis, and the other two tasks are read as notes
because their 250-item arms cannot resolve 1.5 pp even paired (±3.9 pp at 10% discordance —
`design §3.3`). Two of them still carry resolvable differences, and those are real findings:

| column | task | resolvable differences | everything else |
|---|---|---|---|
| Table 1 (dense vMLX) | **IFEval** | `oq4e` **+5.20 pp** over `stock4bit` ([+1.86, +8.54], K = 29) — the column's only resolved IFEval difference | `jang4s` +0.40 pp (K = 23) and `oq4` +2.00 pp (K = 21) vs the control: **indeterminate** at n = 250 (`acc-dense §3.1`) |
| Table 1 (dense vMLX) | **GSM8K** | **none** — every pair indeterminate (K = 22, 11, 18); the four levels span 87.2–90.0%, and a 250-item arm cannot resolve that span (`acc-dense §3.1`, `design §3.3`) | — |
| Table 2 (dense Osaurus) | **IFEval / GSM8K** | **no paired interval exists in the record for either task** in this column; only levels are published (IFEval 76.8–83.6%, GSM8K 85.6–89.6% — `acc-dense §2.2`), so no verdict is drawn | — |
| Table 3 (MoE vMLX) | **IFEval** | `optiq` **+10.40 pp** ([+4.86, +15.94], K = 50, p = 0.0003) and `oq4e` **+8.80 pp** ([+3.15, +14.45], K = 52, p = 0.0032) over the control | the other eight rows indeterminate; `jang2l`'s +4.80 pp vs the control is one of them (`acc-moe §3.3`) |
| Table 3 (MoE vMLX) | **GSM8K** | **none** — all three computable pairs indeterminate (K = 67, 61, 78); the control and the JANG cell have **no GSM8K samples** (both halted) | — |

Two things follow that the primary axis alone would hide. **On the MoE, instruction following is
the axis where the portables beat the control — and it is bought with every resource**: `oq4e` is
18.3 tok/s slower, 202 MB heavier and 212.6 MB larger than `stock4bit` for its +8.80 pp. **On the
dense vMLX column the same trade is nearly free**: `oq4e` is 1.8 tok/s *faster* for its +5.20 pp.
A pooled score would have averaged those two facts into nothing (`design §5.4`).

---

## 4. Trade rates (slopes)

### 4.1 The formula, the slash rule, and the direction convention

Straight from `design §5.5`, with `A` and `B` both named on every row:

```
R_quality/speed  = (x(A) − x(B)) / (y₁(A) − y₁(B))     pp per tok/s
R_quality/memory = (x(A) − x(B)) / (y₂(A) − y₂(B))     pp per 100 MB
R_quality/disk   = (x(A) − x(B)) / (y₃(A) − y₃(B))     pp per GB
```

Four rules govern the tables, and three of them are the design's:

1. **A rate is published with both cells named, both coordinates, and the interval propagated from
   the accuracy interval** (`design §5.5`).
2. **A slash replaces the rate when the accuracy difference is in the tie or indeterminate bin** —
   "a rate computed from an unresolvable difference is not an exchange rate at all" (`design §5.5`).
3. **This paper extends that rule to the resource axis, and says so:** a slope is also slashed when
   its denominator's difference sits inside the resource's own band (2.5% throughput, 1% memory,
   exact equality for disk), because a rate whose denominator is a tie is not an exchange rate
   either — the arithmetic would divide by a rounding difference.
4. **The sign is `Δq/Δr` in the direction printed, and every row carries a one-line reading that
   names which way each coordinate moved.** Several priced pairs below move *both* coordinates in
   the same direction (better accuracy *and* less memory, or its reverse); their rates are printed
   with the direction spelled out rather than left to the sign, because a sign is the wrong
   instrument for a pair that is not a trade at all.

**One transparency note on the slash rule.** Two priced pairs below have intervals that exclude zero
(so the direction is resolved) while their magnitudes sit inside the ±1.5 pp band: `oq4e` vs
`stock4bit` and `oq4` vs `oq4e`, both in Table 1. The design's slash rule names the *tie* and
*indeterminate* bins, and under the strictest reading of `§5.2` those two sub-band pairs are
indeterminate — so a reader who prefers the strict rule reads those two rows' rates as `—`. The
paper prices them because the direction is measured, the interval is printed beside every number,
and the alternative is to discard a measured direction the campaign paid 17 hours for. Both
readings are visible in the tables and neither is hidden.

### 4.2 Priced pairs

**Table 1 — dense `Qwen3.5-4B`, vMLX.** Accuracy axis MMLU unless the row says otherwise.

| pair (A vs B) | Δ MMLU (CI, K) | Δ decode | Δ peak | Δ disk | R/speed | R/memory | R/disk | reading |
|---|---|---|---|---|---|---|---|---|
| `oq4e` vs `stock4bit` | **−1.01 pp** ([−1.86, −0.15], K = 99) | **+1.8 tok/s** (+4.1%) | **+103 MB** (+2.7%) | **+106.8 MB** (+3.5%) | **−0.56 pp per tok/s** | **−0.98 pp per 100 MB** | **−9.46 pp per GB** | 1.01 pp of MMLU and 103 MB of peak bought 1.8 tok/s; the same bundle gains **+5.20 pp IFEval** for the same price (below) |
| `oq4` vs `oq4e` | **+1.32 pp** ([+0.40, +2.23], K = 118) | +1.6 tok/s (+3.5%) | **−127 MB** (−3.2%) | −7.4 MB (−0.23%) | **+0.83 pp per tok/s** | **−1.04 pp per 100 MB** | `—` (inside the exact-equality band) | **not a trade**: `oq4` is better on accuracy, speed and peak at once; the disk difference is 0.23% |
| `jang4s` vs `oq4e` | **+1.54 pp** ([+0.56, +2.51], K = 131) | **+8.2 tok/s** (+17.8%) | **−126 MB** (−3.2%) | **+39.4 MB** (+1.2%) | **+0.19 pp per tok/s** | **−1.22 pp per 100 MB** | **+39.05 pp per GB** | the column's one clean exchange: **39.4 MB of extra disk** buys 1.54 pp, 8.2 tok/s and 126 MB of peak |
| `oq4e` vs `stock4bit`, **IFEval axis** | **+5.20 pp** ([+1.86, +8.54], K = 29) | +1.8 tok/s | +103 MB | +106.8 MB | **+2.89 pp per tok/s** | **+5.05 pp per 100 MB** | **+48.68 pp per GB** | the same 103 MB that costs 0.98 pp of MMLU buys **5.05 pp of instruction following** — the two tasks price the same footprint in opposite directions |

**Table 2 — dense `Qwen3.5-4B`, Osaurus.** Every priced row is against `optiq`; the other pairs
have no interval (§3.2).

| pair (A vs B) | Δ MMLU (CI, K) | Δ decode | Δ peak | Δ disk | R/speed | R/memory | R/disk | reading |
|---|---|---|---|---|---|---|---|---|
| `jang4s` vs `optiq` | **+3.82 pp** ([+2.45, +5.18], K = 175) | **+3.8 tok/s** (+9.8%) | **+928 MB** (+37.5%) | **−836.2 MB** (−20.7%) | **+1.01 pp per tok/s** | **+0.41 pp per 100 MB** | **−4.57 pp per GB** | the one axis where `jang4s` pays: 928 MB of extra peak comes with 3.82 pp and 9.8% of decode, while its bundle is 836 MB smaller |
| `oq4e` vs `optiq` | **+4.39 pp** ([+2.76, +6.01], K = 198) | −0.1 tok/s (0.26%, **tie**) | **−256 MB** (−10.4%) | **−875.7 MB** (−21.7%) | `—` (resource tie) | **−1.71 pp per 100 MB** | **−5.01 pp per GB** | not a trade: `oq4e` is better on accuracy, ties on speed, and is lighter and smaller |
| `oq4` vs `optiq` | **+3.11 pp** ([+1.82, +4.41], K = 165) | +0.1 tok/s (0.26%, **tie**) | −6 MB (0.24%, **tie**) | **−883.1 MB** (−21.8%) | `—` (resource tie) | `—` (inside the 1% band) | **−3.52 pp per GB** | the whole of `optiq`'s loss to `oq4` is accuracy and disk; the other two coordinates are the same number twice |

**Table 3 — MoE `LFM2.5-8B-A1B`, vMLX.** Rows using `oq4`'s decode coordinate carry ⚠ and are not
attributable to `oq4` alone (§3.3).

| pair (A vs B) | Δ MMLU (CI, K) | Δ decode | Δ peak | Δ disk | R/speed | R/memory | R/disk | reading |
|---|---|---|---|---|---|---|---|---|
| `optiq` vs `stock4bit` | **−7.28 pp** ([−10.21, −4.35], K = 291) | **−14.7 tok/s** (−12.8%) | **+655 MB** (+12.6%) | **+691.1 MB** (+14.4%) | **+0.50 pp per tok/s** | **−1.11 pp per 100 MB** | **−10.53 pp per GB** | every coordinate is worse: the resource penalty bought **negative** accuracy (`acc-moe §5.4`) |
| `optiq` vs `oq4e` | **−7.98 pp** ([−10.84, −5.12], K = 277) | **+3.6 tok/s** (+3.7%) | **+453 MB** (+8.4%) | **+478.5 MB** (+9.6%) | **−2.22 pp per tok/s** | **−1.76 pp per 100 MB** | **−16.68 pp per GB** | the column's clearest genuine exchange on this axis: `optiq` buys 3.7% of decode and pays 7.98 pp, 453 MB and 478 MB for it |
| `oq4e` vs `oq4` | **+14.30 pp** ([+11.29, +17.31], K = 307) | **+31.4 tok/s** ⚠ (+47.9%) | +1 MB (0.02%, **tie**) | +9,235 B (**tie** by the exact-equality rule) | **+0.46 pp per tok/s** ⚠ | `—` (inside the 1% band) | `—` (the bundles differ by 0.0002%) | the largest accuracy gap in either model, bought for a 1 MB and 9 KB difference in bundled bytes — which is the finding, not a rate (`acc-moe §5.5`) |
| `oq4` vs `stock4bit` | **−13.60 pp** ([−16.60, −10.59], K = 305) | **−49.7 tok/s** ⚠ (−43.1%) | **+201 MB** (+3.9%) | **+212.6 MB** (+4.4%) | **+0.27 pp per tok/s** ⚠ | **−6.77 pp per 100 MB** | **−63.97 pp per GB** | 212.6 MB of extra disk and 201 MB of peak for 13.60 pp *below* the control |
| `optiq` vs `oq4` | **+6.32 pp** ([+3.52, +9.11], K = 264) | **+35.0 tok/s** ⚠ (+53.4%) | **+454 MB** (+8.4%) | **+478.5 MB** (+9.6%) | **+0.18 pp per tok/s** ⚠ | **+1.39 pp per 100 MB** | **+13.21 pp per GB** | genuine both ways — `optiq` is faster *and* more accurate, and pays 454 MB and 478 MB — but the decode coordinate is the +76.0% figure |
| `oq4e` vs `stock4bit`, **IFEval axis** | **+8.80 pp** ([+3.15, +14.45], K = 52) | **−18.3 tok/s** (−15.9%) | **+202 MB** (+3.9%) | **+212.6 MB** (+4.4%) | **−0.48 pp per tok/s** | **+4.36 pp per 100 MB** | **+41.39 pp per GB** | the dispatch's MoE example priced: on the MMLU axis this pair is **indeterminate** (+0.70 pp, K = 298), so its real price is instruction following — 15.9% of decode and 212.6 MB of disk per 8.80 pp |
| `optiq` vs `stock4bit`, **IFEval axis** | **+10.40 pp** ([+4.86, +15.94], K = 50) | −14.7 tok/s (−12.8%) | +655 MB (+12.6%) | +691.1 MB (+14.4%) | **−0.71 pp per tok/s** | **+1.59 pp per 100 MB** | **+15.05 pp per GB** | `optiq`'s one genuine advantage in the column, and it costs every resource at once |

### 4.3 The free exchanges (slashed)

These are the pairs the slash was written for: the accuracy difference is a tie, so the speed and
density on the table are bought at **no measurable quality cost**, and every rate is `—`.

| column | pair (A vs B) | what A takes | Δ MMLU (CI, K) | bin |
|---|---|---|---|---|
| Table 1 | `jang4s` vs `stock4bit` (**Q2**) | **+10.0 tok/s (+22.6%)** and 23 MB less peak | **+0.53 pp** ([−0.38, +1.43], K = 110) | **tie**, replicate-gated, P1 |
| Table 1 | `jang4s` vs `oq4` | **+6.6 tok/s (+13.9%)** | +0.22 pp ([−0.66, +1.10], K = 105) | tie |
| Table 1 | `oq4` vs `stock4bit` | **+3.4 tok/s (+7.7%)** and 24 MB less peak | +0.31 pp ([−0.46, +1.08], K = 85) | tie |
| Table 3 | `oq4e` vs `stock4bit` (MMLU) | — (the resources are the wrong way) | +0.70 pp ([−2.27, +3.67], K = 298) | indeterminate — **the pair the control cannot be dominated through** |
| Table 3 | `jang2l` vs `stock4bit` | **0.87% decode (a tie), −36.0% disk, −30.5% peak** | **no interval — the MMLU leg does not exist** | **not computable**; the density is free on the floor that was measurable (no collapse on IFEval) |

The Q2 line is the whole dense half of this synthesis in one row: **+22.6% sustained decode for
+146.3 MB of disk, and the MMLU interval [−0.38, +1.43] does not resolve a difference in either
direction** — a free exchange, replicated, at near-equal precision.

### 4.4 What the rates are not

- **Not a recommendation.** The design publishes rates and does not choose for the reader
  (`design §5.3`): a reader with 8 GB of unified memory and one with 64 GB read different answers
  off the same frontier (`design §8.4`). §6 names per-axis leaders; it does not rank the rates.
- **Not a pooled quality number.** A rate is per task. `oq4e` vs `stock4bit` on the dense column is
  −0.98 pp of MMLU per 100 MB *and* +5.05 pp of IFEval per 100 MB, and no arithmetic combines them.
- **Not attributable where the source says it is not.** The `oq4`-bearing rows carry ⚠; the MoE
  protection gap carries its two-publisher caveat; every rate involving a Track 1 level carries the
  single-visit limit of §2.5.
- **Not a cross-runtime rate.** No slope in this paper divides a score by a coordinate from another
  runtime's table.

---

## 5. The four questions, in order (`design §1.3`, `§5.3`)

### 5.1 Q1 — does `JANG_2L` at 2.37 bits reach or beat 4-bit on MMLU?

**Not answerable from these campaigns, and not refuted by them** (`acc-moe §5.3`). The
pre-registered comparison — `jang2l` vs `stock4bit`, MMLU, vMLX — **does not exist**: the runtime
refused one item's completion with **HTTP 502**, type `invalid_response_error`, code
`reasoning_only_no_content`, at **item 80/1,140 in the primary and again at item 80/1,140 in the
replicate** (9 h 23 m apart, the same 196-token refused completion recorded server-side). The
harness retried three times, raised an uncaught `HTTPError`, and recorded the task FAIL with no
score; the same mechanism halted `stock4bit`'s GSM8K at item 176 and `jang2l`'s at item 53
(`acc-moe §1.2` finding 5). Determinism strong enough to reproduce a *defect* item-for-item is the
campaign's own evidence that this is a property of the item-and-runtime pair, not of the session
(`acc-moe §4.1`).

Two corrections to the shorthand that travelled with this finding are made in the record and
carried here:

- **It is not a token-cap truncation.** The cap was `max_gen_toks=1024` and every refused completion
  ended well under it — the runtime's own token counts are 196, 432 and 507. The runtime rejects a
  completion with **no visible answer channel**, whatever its length (`acc-moe §1.2` finding 5).
  §2.7 records where this paper's dispatch said "truncation halt" and why the measured mechanism
  replaces it.
- **A halt is published as a halt, never as a collapse.** No score, no Δ, no frontier position.

**What the record does support is the negative half of the design's live hypothesis.** P3 — quality
collapse — was the one outcome that would have mattered most, and it **did not fire** on anything
`JANG_2L` completed: IFEval **56.8%** against the control's **52.0%**, Δ = **+4.80 pp**
([−1.17, +10.77], K = 58, p = 0.148, indeterminate at n = 250) and nowhere near the 0 floor.
Instruction following holds at 2.37 average bits on the one task that measured it.

**The Osaurus copy of the artifact did complete MMLU, and its number is an instrument reading, not
a score:** 3.77% (43/1,140) with 845 prose responses, 171 empty and 124 bare letters, and a
stated-rule diagnostic finding a lower bound of 9.9% of items whose text names the right answer
(`acc-moe §2.2`). It is published with that label; no cross-cell or cross-runtime reading is drawn
from it.

**The publishable sentence:** *under this harness, at these pins, on these items, the parity claim
was neither reproduced nor falsified — the pair's MMLU cell does not exist, and the only task the
cell completed is indeterminate at n = 250. The vendor's own measurement at the vendor's own pins
is untouched by any of this.*

### 5.2 Q2 — does `JANG_4S`'s decode lead cost task accuracy against uniform 4-bit?

**Zero measurable penalty. Outcome P1 (Quality Parity) is confirmed, and it is the program's only
replicate-gated reading** (`acc-dense §1.2`, `§7`; `design §5.3`):

| coordinate | what `JANG_4S` measured | against `stock4bit` |
|---|---|---|
| MMLU (n = 2,280) | **68.42%** (1,560/2,280) | **+0.53 pp** ([−0.38, +1.43], K = 110) — tie; the whole interval inside the band |
| GSM8K (n = 250) | 87.2% (218/250) | −2.40 pp ([−6.08, +1.28], K = 22) — indeterminate |
| IFEval (n = 250) | 79.2% (198/250) | +0.40 pp ([−3.36, +4.16], K = 23) — indeterminate |
| decode | 54.2 tok/s (vMLX, +5.9% drift) | **+22.6%** over the control in the primary, **+16.8%** in the replicate, **+13.9%** over the best portable |
| disk | 3.207 GB | **+146.3 MB (+4.8%)** — the price |
| peak | 3,820 MB | −23 MB (−0.6%) — no memory penalty |

The replicate is what makes this a **gated P1** rather than a single visit's point estimate: both
cells were re-run in a separate block with the order reversed, and **every one of 2,280 items
answered identically in both visits, Δ = 0.0000 pp on both cells** (`acc-dense §5`) — so the primary
and the replicate agree on the bin, which is the design's condition for publishing P1 at all.
The Osaurus half of Q2 cannot be gated the same way: the `jang4s__osaurus` MMLU level is replicate-
confirmed (64.87% in both visits), but the pair that would test it — `jang4s` vs `oq4` — has no
published interval (§3.2), so Q2's reading lives in Column A, exactly as `design §2.1` planned.

**What it may not say:** that `JANG_4S` is as accurate as uniform 4-bit *in general*. Parity is on
this task, this item set, this harness, this machine, and — with JIT and native MTP pinned off —
at a floor for the shipped JANG path, not on it (`dense §8.4`).

### 5.3 Q3 — did OptiQ's latency and footprint penalty buy accuracy, or is it dominated?

**Dominated, on both models, and the penalty bought negative accuracy against the control**
(`acc-dense §7`; `acc-moe §5.4`). §1.3 has the two tables; the parts that belong here are the
precision of the claim and its counter-current.

- **Dense (Osaurus):** the accuracy half is a measured paired difference over 2,280 items against
  every column-mate — `optiq` is **3.11 to 4.39 pp** below all three, p ≤ 2.4 × 10⁻⁸ — and the
  resource half is a **0.26%/0.52% decode tie** with two of them plus ≈28% more disk than either.
  It is *not* a speed story: on the project's own rule `optiq` decodes at the same rate as its
  neighbours, and its elimination turns on accuracy, peak and disk.
- **MoE (vMLX):** `stock4bit` beats it on accuracy (**+7.28 pp**, K = 291, p = 1.3 × 10⁻⁶), decode
  (115.3 against 100.6 tok/s), peak (5,214 against 5,869 MB) and disk (4.782 against 5.473 GB),
  every gap outside its own band — the strongest form of the verdict available in this program.
- **The counter-current, unfiltered:** on the MoE, `optiq` posts the column's **best IFEval**
  (62.4%, +10.40 pp over the control, K = 50, p = 0.0003) and beats `oq4` on accuracy *and* speed.
  It is eliminated from the MMLU frontier, not globally condemned — on this model, in this runtime,
  on these items.
- **The design's `§5.7` example sentence does not survive contact and is replaced.** It named
  `JANG_2L` as the dominator (15.6% faster, 44% smaller); `JANG_2L` has no MMLU coordinate, and the
  published domination is the control's (`acc-moe §5.4`).

### 5.4 Q4 — does outlier-channel protection buy task accuracy over stock 4-bit?

**It is not one variable in either model, and its spread is an order of magnitude larger on the
MoE.** §1.4 carries the table; in the design's own vocabulary:

| model | `oq4e` vs control | `oq4` vs control | the two protected artifacts against each other |
|---|---|---|---|
| dense (vMLX) | −1.01 pp ([−1.86, −0.15], K = 99) — a resolved sub-band difference | +0.31 pp ([−0.46, +1.08], K = 85) — parity | **+1.32 pp** ([+0.40, +2.23], K = 118) |
| MoE (vMLX) | +0.70 pp ([−2.27, +3.67], K = 298) — indeterminate, effective parity | **−13.60 pp** ([−16.60, −10.59], K = 305, p = 1.8 × 10⁻¹⁹) at a floor-shaped 21.93% | **+14.30 pp** ([+11.29, +17.31], K = 307, p = 2.5 × 10⁻²¹) |

Three things this question may and may not be answered with:

1. **May:** on the MoE the pair of protected artifacts brackets the control, and the build that
   carries the higher measured accuracy is the one to run — `oq4e` is at effective parity with the
   control on MMLU and **above** it on IFEval (+8.80 pp, K = 52, p = 0.0032), while `oq4` sits
   below the four-option floor, is dominated on every pair, and is the configuration §6 lists as
   avoided.
2. **May:** on the dense model the same question is a *subtle* trade-off, not a collapse — `oq4`
   buys nothing over the control, and `oq4e` gives up ~1 pp of MMLU ([−1.86, −0.15]) for **+5.20 pp
   of IFEval** ([+1.86, +8.54]) and 1.8 tok/s. That is the clearest "different task, different
   verdict" pair in the program, and it is a rate, not a ranking (§4.2).
3. **May not:** attribute the MoE gap to the protection mechanism. `stamsam/LFM2.5-8B-A1B-oQ4` and
   `brainworkup/LFM2.5-8B-A1B-oQ4e` are two publishers' builds, so the 14.30 pp is a measured
   difference between two artifacts — "these two differ" — and this synthesis recommends artifacts,
   not a mechanism (`acc-moe §1.2` finding 4, `§5.5`).

---

## 6. The unified recommendation

Three coordinates, one row per axis leader, every figure a quotation from §3 and every caveat from
§2. This table is a recommendation **per axis**; it is not a ranking, and no row is derived from a
composite score (§2.4).

### 6.1 Dense `Qwen3.5-4B`

| axis | format | runtime(s) | the three coordinates | what it costs | the reading |
|---|---|---|---|---|---|
| **Best throughput** | `JANG_4S` | vMLX **54.2** tok/s (+5.9%); Osaurus **42.5** (+5.1%) | 3,820 / 3,400 MB peak; 3.207 GB disk | **+146.3 MB (+4.8%) disk**; MMLU parity (vMLX), no interval (Osaurus) | replicated **+13.9–22.6%** decode at **zero measurable accuracy cost** — the program's only replicate-gated parity (Q2) |
| **Smallest disk** | `stock4bit` | vMLX only (Osaurus refuses it at request time) | 44.2 tok/s (+16.6%); 3,843 MB; **3.061 GB** | slowest of the four; the control every accuracy claim is measured against | the storage-constrained pick, at parity with everything on MMLU |
| **Best instruction following** | `oQ4e` | vMLX **84.0% IFEval**; (Osaurus's IFEval leader is `oq4` at 83.6%) | 46.0 tok/s (+5.4%); 3,946 MB; 3.168 GB | **−1.01 pp MMLU** ([−1.86, −0.15], K = 99) and +103 MB peak / +106.8 MB disk | the column's only resolved IFEval gain: **+5.20 pp for 103 MB and 1.01 pp of MMLU** — and 1.8 tok/s *faster* |
| *(middle of the column)* | `oq4` | both | 47.6 / 38.8 tok/s; 3,819 / 2,466 MB; 3.161 GB | no axis on which it leads the column beyond the bands | second on speed and disk in vMLX and never separated from the top on accuracy; a defensible default with no headline |

*Role of the runtime in these rows: the vMLX numbers are a floor for the shipped JANG path
(JIT/MTP off) and Osaurus's decode column is a 0.52% tie among its three portables. No memory or
load figure is comparable across the two runtimes (`design §5.6`; `§3.4` of this paper).*

### 6.2 MoE `LFM2.5-8B-A1B` (vMLX — the only column with accuracy coordinates for all five formats)

| axis | format | the three coordinates | what it costs | the reading |
|---|---|---|---|---|
| **Smallest footprint and disk, IFEval preserved** | `JANG_2L` | **116.3** tok/s (+0.5%, a tie); **3,624 MB**; **3.062 GB** | the MMLU leg **does not exist** (halted ×2); the vendor parity claim is unanswered | **36.0% less disk and 30.5% less peak than the control** for a decode tie, with IFEval **above** the control's (56.8% vs 52.0%, indeterminate at n = 250) and no collapse — the density pick, with its accuracy question open |
| **Best measured MMLU** | `oQ4e` **36.23%** / `stock4bit` **35.53%** | 97.0 tok/s (+10.9%); 5,416 / 5,214 MB; 4.995 / 4.782 GB | `oq4e` is 15.9% slower, 202 MB heavier and 212.6 MB larger than the control for its +0.70 pp (K = 298) — a difference the rule calls **indeterminate** | the accuracy pick is the pair that cannot be ordered by the rule; `oq4e` also leads the control on IFEval (+8.80 pp) |
| **Strictly avoid** | `optiq` and `oq4` | `optiq`: 28.25%, 100.6 tok/s, 5,869 MB, 5.473 GB. `oq4`: 21.93% ⚠, 65.6 ⚠ tok/s, 5,415 MB, 4.995 GB | every axis worse than the control, or a floor-shaped score | both **eliminated**: `stock4bit` dominates `optiq` on all three pairs and `oq4` on all three pairs; `optiq`'s IFEval lead does not rescue it on this axis, and `oq4`'s decode coordinate is the +76.0% figure |

*The MoE Osaurus frontier is not drawn and carries no recommendation (§3.4). The MoE MMLU column is
exact-string-match over the `content` channel and is not form-invariant across cells — 30% to 52% of
each cell's responses took the scorable bare-letter form — so every MoE MMLU figure in this table is
a level with a measured instrument limit beside it (`acc-moe §2.1`).*

### 6.3 What cannot be claimed

Each of these is a rule doing its job, and each is stated in the source it comes from:

- **No leaderboard or absolute-capability claim.** These benchmarks are public and predate every
  artifact, the MMLU sets are subsamples (57 × 40 on dense, 57 × 20 on MoE), the other tasks are
  250 items, and ARC-Challenge was dropped upstream (Decision 103). Nothing here is comparable to a
  published number for these models (`design §7`).
- **No general quantization claim.** Two models, two runtimes, one machine, ten artifacts at ten
  snapshots. The reading is about *these* bytes (`design §7`; `xrt §1.3`).
- **No cross-runtime accuracy ranking, ever.** Study 2C measured the observable and closed the
  door: on identical bytes the two loaders agree on **87.8–89.6%** of MMLU items and **91.2–94.0%**
  of GSM8K items (dense), with vMLX scoring **~3–4 pp higher on MMLU across every shared format** —
  and on the MoE only IFEval's **13.6%** string agreement is computable at all (MMLU and GSM8K have
  no common items, the vMLX side having halted). Both rates are far below the pre-registered 99%
  threshold, so the serving runtime is a **live confound** and format comparisons are legal only
  within a constant runtime (`acc-dense §4`; `acc-moe §2.2`; `design §2.3` rule 3).
- **No cross-runtime memory or load ranking.** `phys_footprint` charges wired GPU pages differently
  in the two runtimes; a cross-runtime load comparison uses the sum of `cold_load_s` and
  `first_request_s` or nothing (`dense §7`; `moe §7`; `report.CROSS_RUNTIME_UNCOMPARABLE`).
- **No claim from inside the band and none from an indeterminate comparison.** A tie is a tie; an
  indeterminate comparison is printed as indeterminate and is evidence in neither direction
  (`design §5.2`, `§7`).
- **No accuracy claim from the MoE Osaurus MMLU number.** It measures a filter this artifact's
  answer style defeats (`acc-moe §2.2`).
- **No speed or memory number that is not a Track 1 quotation**, no rate from an unresolvable
  difference, and no attribution of any measured gap to a mechanism: the bundle and the loader
  travel together in every cell that produced one (`design §5.7`; `xrt §8.2`).

---

## 7. Track 2 and Milestone v2 closeout

### 7.1 Track 2's plans

| plan | deliverable | status |
|---|---|---|
| 02-01 | Harness spike and local-endpoint validation — `docs/research/2026-09-18-accuracy-spike-report.md` | **complete 2026-09-18** (Decision 102: vMLX scheduler stop-deadlock patched, canary channel verified, `fewshot_as_multiturn: true` priced and frozen) |
| 02-02 | Dense accuracy study (`Qwen3.5-4B`) — `docs/research/2026-09-18-accuracy-dense.md` | **complete 2026-09-18** (Decision 104; 11 cell runs, 30,580 item evaluations, 100% PASS) |
| 02-03 | MoE accuracy study (`LFM2.5-8B-A1B`) — `docs/research/2026-09-19-accuracy-moe.md` | **complete 2026-09-19** (Decisions 105–106; 8 cell runs, 9,340 item evaluations, 5 PASS + 3 FAIL) |
| 02-04 | Pareto tradeoff synthesis — **this document** | **complete 2026-09-19** |

**39,920 scored item evaluations** across the two studies, every one of them on disk with its raw
sample rows, its manifest and its task log (`acc-dense §8`; `acc-moe §6`).

### 7.2 Track 2's exit criteria, as met

The design's exit criteria for the two measurement plans (`design §6.3`, `§6.4`), evaluated:

| criterion | dense | MoE |
|---|---|---|
| every cell scored, or N/A/FAIL with its reason | 11/11 PASS | 5 PASS; 3 FAIL, each with the item number, the mechanism and the runtime log line (`acc-moe §1.2` finding 5) |
| item-identity hashes agree within each task across all cells | the dense study states its comparisons were run over identical prompt items with identical seeds and greedy decoding (`acc-dense §3`) | pairing verified by `(subject, doc_id)` intersection (1,140/1,140 per MMLU pair) — the manifests' `task_hashes` field is **empty for `mmlu_generative`** in all eight cells, a record gap named in `acc-moe §3` rule 3 |
| every confound pinned or declared | `cache_state: "off"` on every cell; residency pinned; restore `cmp`-verified; the per-cell `shasum` gap declared | same; plus the channel check that produced finding 5 |
| the replicate run | 3 cells on MMLU, reversed order, 100.000% agreement | 2 cells on MMLU; one halted, so the Q1 replicate produced no comparison |
| the write-up, answered against the design's questions | Q2 and Q4 answered; Q3's dense half answered | Q1 indeterminate, Q3 and Q4 answered |

### 7.3 What the milestone established, in the only sentences it permits

1. **The trilogy is complete and joined.** Speed, memory and accuracy now exist for the same ten
   artifacts under pins that are recorded per cell, and this paper is the join. Nothing in Track 1
   was re-measured to make it.
2. **On `Qwen3.5-4B`, `JANG_4S`'s replicated 9–22% decode lead is free**: at MMLU parity
   (+0.53 pp, K = 110, replicate-confirmed at 0.0000 pp drift) for a 4.8% disk premium, with the
   column's IFEval leader a different format (`oq4e`) that pays ~1 pp of MMLU and 103 MB of peak
   for it.
3. **On `LFM2.5-8B-A1B`, `JANG_2L`'s 36% disk and 30.5% footprint advantage is bought at no
   measured cost on the floor that exists** — instruction following holds at 2.37 average bits and
   P3 does not fire — **and the MMLU question is open**, because the item set does not exist.
4. **OptiQ is eliminated on both models** by measured pairs, and the elimination is stronger than
   the design anticipated on dense (accuracies separated rather than tied) and weaker on MoE (the
   dominator is the control, not `JANG_2L`).
5. **Outlier protection is not a single variable**: two protected builds bracket the control by
   ~1 pp on dense and by 14.30 pp on the MoE, and the MoE recommendation is therefore about
   artifacts, not mechanisms.
6. **The loader is a live confound for accuracy** (2C: 87.8–94.0% agreement on the constrained
   tasks, 11.6–14.8% on open-ended ones), so the milestone's accuracy claims are within-runtime
   claims by construction.

### 7.4 What the record still owes

Stated plainly, because a milestone that closes over its own gaps is the pattern this project
exists to avoid:

| gap | origin | consequence |
|---|---|---|
| **Truncation and parse-failure rates are not carried in the manifests** — the design `§3.5` asks for both per (cell, task) | both accuracy campaigns; the MoE study names their absence explicitly, and the dense write-up publishes neither | the 5%-truncation FAIL rule could not be applied mechanically; the halt mechanism that did fire was diagnosed from the runtime log instead (`acc-moe §6`) |
| **Per-cell `shasum` of the Osaurus settings files was never taken** | Track 1 (both campaigns) and Track 2 | a byte that moved outside the drift guard's 23 tracked keys is not in either record; the `cmp`-verified pre/post restoration is what the record carries (`moe §8.6`) |
| **`task_hashes` is empty for `mmlu_generative`** in all eight MoE manifests | evaluator | pairing was proved independently — named so no reader assumes an identity hash that is not in the record (`acc-moe §3`) |
| **The MoE MMLU metric is not form-invariant across cells** | the task's `get_response` filter | every MoE MMLU number is a level with an uncorrected response-form component; the direction of the effect is not estimable (`acc-moe §3.4`) |
| **ARC-Challenge was dropped** | Decision 103 (upstream extraction defect) | the study prices three failure modes, not four |
| **The dense Osaurus IFEval/GSM8K pairs have no intervals** | Plan 02-02's analysis scope | Table 2's secondary axes carry levels and no verdicts |
| **`acc-dense §6.1`/`§6.2`'s footprint column matches no Track 1 quotation** | Plan 02-02's write-up | this paper uses Track 1's and the design's figures (§2.7, Appendix B); the source's column is left as published |
| **The "reasoning truncation" shorthand** | dispatch-level record | the measured mechanism is a 502 `reasoning_only_no_content` refusal, not a cap truncation (§2.7) |

### 7.5 Milestone v2

**Milestone v2 — "JANG Study and Accuracy Scoring" (0.2.0) is complete with this document.** Both
of its phases close here:

| phase | plans | status |
|---|---|---|
| 1 — Track 1: The JANG Study | 3 of 3 | **complete 2026-09-17** (R1 on dense, R4 on MoE, the JANG duality, the cross-runtime rows) |
| 2 — Track 2: Accuracy Scoring | 4 of 4 | **complete 2026-09-19** (spike, dense study, MoE study, this synthesis) |

The milestone's question was the third coordinate, deferred since v1's founding decision ("Speed +
memory only in v1. Accuracy work is refused until v1 ships"). It is discharged: for ten artifacts, on
two models, in two runtimes, the project can now say what each format's speed and density buy and
cost in measured task accuracy, with the pins, the intervals, the discordant counts and the limits
printed beside every number.

**What carries forward, named and unrun** (each is a single-variable experiment the milestone
deliberately left open):

- **The vMLX JIT A/B** — `--enable-jit` against `--no-jit` on identical JANG weights. Every vMLX
  number in Track 1 and every vMLX accuracy cell is a floor for the shipped path; this prices the
  accelerator both campaigns pinned off (`xrt §7.3`).
- **The thinking-off arm** — thinking pinned off, MMLU only, the decisive pair. It would price the
  reasoning channel's contribution to both score and cost, and it is the arm that would have made
  Q1 answerable had it run (`design §8.2`).
- **The dense Osaurus `prefill` re-run under `cache_state: "off"`** — Track 1's one void workload,
  now that the MoE campaign demonstrated the protocol works (`xrt §7.4`).
- **Model ∧ profile separation** — a dense model at ~2.4 bits or a MoE at ~4.15 bits, to separate
  R4's two variables (`moe §8.3`).
- **A per-module bit map or a kernel trace** — would move expert routing and kernel cost from
  candidate to measured (`xrt §7.4`).
- **A third model** — two models is what makes a reading model-specific; a third is a new campaign
  (`design §8.1`).

`.paul/STATE.md` and `.paul/ROADMAP.md` carry the phase bookkeeping this section documents; this
dispatch's file scope is this document alone.

---

## Appendix A — evidence index

| what | where |
|---|---|
| the coordinates, the parity band, the paired instrument, the reading vocabulary, the join rules, the publication limits, the synthesis sentence | `docs/research/2026-09-17-v2-track2-accuracy-study-design.md` (`§1.3`, `§1.4`, `§5.1`–`§5.7`, `§6.5`, `§7`) |
| dense accuracy scores, paired intervals, replicate determinism, Study 2C | `docs/research/2026-09-18-accuracy-dense.md` (`§1.2`, `§2`–`§5`, `§7`) |
| MoE accuracy scores, paired intervals, the 502 halts, the extraction confound, the MoE frontier verdicts | `docs/research/2026-09-19-accuracy-moe.md` (`§1.2`, `§2`–`§5`) |
| every dense `decode_tps`, drift, `peak_mb`, disk byte count | `docs/research/2026-09-17-dense-jang-study.md` (`§3.1`, `§4.1`, `§6.1`, `§7.1`) |
| every MoE `decode_tps`, drift, `peak_mb`, disk byte count, the two Osaurus decode FAILs | `docs/research/2026-09-17-moe-jang-study.md` (`§3.1`, `§4.1`, `§6.1`, `§7.1`, `§8.4`) |
| the JANG duality, R4, the cross-runtime rows, the deferred JIT A/B | `docs/research/2026-09-17-jang-cross-runtime.md` (`§1.2`, `§3.3`, `§4`, `§6`, `§7.3`) |
| the ten artifacts' bytes, declared bits and snapshot revisions | `docs/research/2026-09-17-v2-track2-accuracy-study-design.md` `§2.4` (re-verified there; identical on every Track 1 row) |
| the dense OptiQ vision-map refusal, the Osaurus stock-4bit refusal | `docs/research/2026-09-15-grid-loadability-probe.md`; `design §2.1`, `§2.2` |
| why a footprint is not one quantity across runtimes | `docs/research/2026-09-16-footprint-is-not-one-quantity.md` |
| `decode_tps`, `prefill_tps`, `CROSS_RUNTIME_UNCOMPARABLE`, drift annotation | `ohyesmlx/report.py` |
| the cache pin, readiness rule, reasoning-channel rule | `ohyesmlx/runtimes.py`; `ohyesmlx/measure.py`; `docs/interfaces.md` |
| Phase and milestone bookkeeping (not edited by this dispatch) | `.paul/STATE.md`, `.paul/ROADMAP.md` |

## Appendix B — number provenance

Every figure in this paper is a quotation or an arithmetic derivation of quotations; no number was
measured for it. This table maps each table to its source:

| this paper | value(s) | source |
|---|---|---|
| §1.1 instantiation 1; §1.2 dense bullet; §3.1; §4.2 Table 1; §4.3; §5.2 | dense MMLU/GSM8K/IFEval scores, `Δ`, CIs, `K`; `JANG_4S` decode lead and disk premium | `acc-dense §1.2`, `§2.1`, `§3.1`, `§5`, `§7`; `dense §1.2`, `§3.1`, `§6.1` |
| §1.1 instantiation 2; §1.3; §3.2; §4.2 Table 2 | Osaurus dense scores and the three `optiq` pairs; decode/peak/disk | `acc-dense §1.2`, `§2.2`, `§3.2`, `§6.2`; `dense §4.1` |
| §1.1 instantiation 3; §3.3; §3.4; §4.2 Table 3; §5.1; §5.4 | MoE scores, the seven MMLU pairs, the ten IFEval pairs, the halts, the extraction confound, the response-form counts | `acc-moe §1.2`, `§2`, `§3`, `§4`, `§5`; `moe §3.1`, `§4.1`, `§7.1` |
| §2.1–§2.4 | coordinate definitions, dominance conditions, bands, no-pooling rules | `design §5.1`, `§5.4`, `§5.5`; `.paul/STATE.md` (Decisions); `docs/interfaces.md` |
| §2.5 | drift markers, R-reproduce counts, the join rules | `dense §3.1`–`§4.1`, `§8.3`; `moe §3.1`, `§8.1`; `design §5.6` |
| §2.6 | replicate outcomes and gates | `acc-dense §5`; `acc-moe §4`; `design §5.2` |
| §2.7, §7.4 | the three label discrepancies and the open gaps | `acc-dense §3.1`, `§6.1`; `acc-moe §1.2` finding 5, `§3.4`, `§8.6`; this paper's Appendix C |
| §3.4 | the two Osaurus decode FAILs and their reason | `moe §4.1`, `§8.4` |
| §3.5 | secondary-axis intervals and the 250-item resolution limit | `acc-dense §3.1`; `acc-moe §3.3`; `design §3.3` |
| §4 | every slope | arithmetic on the rows above; the formula and slash rule are `design §5.5` |
| §6 | the per-axis leaders | assembled from §3 and §4; no new number |
| §7 | plan statuses, exit criteria, the carried-forward experiments | `design §6.3`–`§6.5`, `§8`; `acc-dense §1.1`, `§8`; `acc-moe §1.1`, `§6`; `xrt §7.3`, `§7.4` |

**Conventions, inherited from the sources and not re-derived here:** percentages of memory and disk
are stated relative to the comparator being named ("X% lower than `stock4bit`'s 5,214 MB" =
(5,214 − 3,624) / 5,214); throughput percentages are the quotient of the one-decimal figures the
leaderboards render, as both Track 1 studies verified (rendered and full-precision bases agree to
within 0.24 pp dense / 0.06 pp MoE and no reading moves between them, `dense §1.2`, `moe Appendix B`);
every `decode_tps` is `report.summarize`'s median of `completion_tokens / (last_content_s − ttft_s)`
across the measured requests; disk bytes are the design's `§2.4` table, byte-identical on every
Track 1 row.

**Two source discrepancies this paper resolves in favour of Track 1 and the design, both auditable:**

1. `acc-dense §6.1–§6.2`'s footprint column (2,795–2,842 MB for the vMLX cells, and 2,466 MB for
   `jang4s__osaurus`, which is `oq4__osaurus`'s value) matches no Track 1 decode-workload quotation
   in this paper's sources. The design's `§5.6` coordinate table and Track 1's own columns
   (`dense §3.1`, `§4.1`) carry 3,819–3,946 MB (vMLX) and 2,216–3,400 MB (Osaurus), and those are
   what this paper uses.
2. Where a point-score difference and a paired estimate differ by a rounding step — `oq4e` vs
   `stock4bit` on dense MMLU: −1.00 pp from the scores, **−1.01 pp** paired — this paper uses the
   paired estimate everywhere, because it is the quantity with an interval.

## Appendix C — recomputation

Every slope in §4 was recomputed for this document from the quoted coordinates, by the design's own
formula. Two spot checks reproduce the method on the first and last priced pairs, and the free
exchange (Q2) is named as the counter-example, because it is slashed rather than priced:

```sh
python3 - <<'EOF'
# The dispatch's two worked examples, from the quoted coordinates only.
def rate(dx, dspd, dpeak_mb, ddisk_bytes):
    return dx/dspd, dx/(dpeak_mb/100), dx/(ddisk_bytes/1e9)

# Example 1 — dense vMLX, oq4e vs stock4bit (acc-dense §2.1, §3.1; dense §3.1; design §2.4)
print("oq4e v stock4bit:", rate(-1.01, 46.0-44.2, 3946-3843, 3167949891-3061131520))
#   -> (-0.5611 pp/tok/s, -0.9806 pp/100MB, -9.4553 pp/GB)

# Example 2 — MoE vMLX, oq4e vs stock4bit on the IFEval axis (acc-moe §2.1, §3.3)
print("oq4e v stock4bit (IFEval):", rate(8.80, 97.0-115.3, 5416-5214, 4994831815-4782228753))
#   -> (-0.4809 pp/tok/s, +4.3564 pp/100MB, +41.3917 pp/GB)

# Example 3 — the free exchange (Q2): slashed, not priced, because the bin is a tie
#   jang4s v stock4bit: dMMLU +0.53 [-0.38, +1.43] K=110 -> every rate is "—"
EOF
```

The bins beside each row are applied from `design §5.2`'s three-way table and `§5.5`'s dominance
conditions; the replicate gate of `design §5.3` is applied per §2.6; and the frontier bins of §3
follow the reading stated in §2.3, with the alternative reading's one changed bin named there.

**Not verified and not claimed by this paper:** nothing was recomputed from the raw sample rows of
`results/accuracy-dense/` or `results/accuracy-moe/` — every score, interval and discordant count
is quoted from the two published studies, which state their own recomputation passes in
`acc-dense §8` and `acc-moe §6`; the only arithmetic performed for this document is the slope
table of §4 and the percentages printed beside the resource quotations, and the two spot checks
above reproduce the method those tables were filled in with.
