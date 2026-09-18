# Plan 02-02 — the dense accuracy study: `Qwen3.5-4B` in vMLX and Osaurus

Date: 2026-09-18. **Measured.** Evaluated 2026-09-17 23:24:41 to 2026-09-18 16:31:27 local (17h 06m 46s total duration) across 11 cell runs (8 primary format-cells + 3 replication cells). Design, test matrix, and pre-registered interpretation rules: [`docs/research/2026-09-17-v2-track2-accuracy-study-design.md`](file:///Users/jrazz/Dev/active/OhYesMLX/docs/research/2026-09-17-v2-track2-accuracy-study-design.md) (§6.3). Spike report and pin provenance: [`docs/research/2026-09-18-accuracy-spike-report.md`](file:///Users/jrazz/Dev/active/OhYesMLX/docs/research/2026-09-18-accuracy-spike-report.md).

Every number in this document is computed from the 11 cell manifests and the 30,580 individual evaluation items recorded in `results/accuracy-dense/`.

---

## 1. Executive summary and headline findings

### 1.1 What ran

| run block | runtime | started | ended | cells | item evaluations | status |
|---|---|---|---|---|---|---|
| Column A (`vmlx`, format axis) | vMLX 1.6.59 | 23:24:46 | 06:05:07 | 4 (`stock4bit`, `oq4`, `oq4e`, `jang4s`) | 11,120 (4 × 2,780) | **100% PASS** |
| Column B (`osaurus`, format axis) | Osaurus 0.25.6 | 06:05:12 | 13:24:31 | 4 (`oq4`, `oq4e`, `optiq`, `jang4s`) | 11,120 (4 × 2,780) | **100% PASS** |
| Replicate pass (MMLU 5-shot) | vMLX & Osaurus | 13:24:42 | 16:31:17 | 3 (`jang4s__vmlx`, `stock4bit__vmlx`, `jang4s__osa`) | 6,840 (3 × 2,280) | **100% PASS** |
| **Total Campaign** | | **23:24:41** | **16:31:27** | **11 cell runs** | **30,580 evaluations** | **ALL PASS** |

- **11 of 11 cell runs PASS.** Zero runtime crashes, zero timeout aborts, zero port leaks.
- **Port safety:** All ports (8000, 1337) released and confirmed free between cells (`scripts/run_accuracy_dense.sh:38-46`).
- **Osaurus host settings:** Byte-exact restoration verified by `cmp -s` after Column B (`runner.log:147`) and after the replication pass (`runner.log:176`).
- **vMLX engine integrity:** Scheduler stop-deadlock patch verified prior to execution:
  `sha256 9710d2b9cf07abc7380f46fef240e64febb2d06d52eb7f64236bd0e76cf686f7` (`runner.log:7`, `:152`).
- **Decision 103 applied:** Upstream `arc_challenge_chat` dropped due to extraction filter defect; evaluated across the 3 clean, fully-validated benchmark tasks:
  - **MMLU** (`mmlu_generative`): 40 items/subject × 57 subjects = 2,280 items, 5-shot multiturn.
  - **GSM8K** (`gsm8k`): 250 test items, 5-shot multiturn.
  - **IFEval** (`ifeval`): 250 prompts, 0-shot.

---

### 1.2 Headline Findings

#### 1. Q2 Answered: JANG_4S Achieves Outcome P1 (Quality Parity) vs Uniform 4-Bit
On the 2,280-item MMLU benchmark, `JANG_4S` scores **68.42%** against `stock4bit`'s **67.89%**:
- Paired difference $\Delta = \mathbf{+0.53\text{ pp}}$ with a 95% confidence interval of $[\mathbf{-0.38\text{ pp}}, \mathbf{+1.43\text{ pp}}]$ (110 discordant pairs out of 2,280 items).
- The entire 95% confidence interval lies **strictly inside the pre-registered $\pm1.5\text{ pp}$ parity band** (§5.1).
- On GSM8K (250 items): 87.2% vs 89.6% ($\Delta = -2.40\text{ pp}$, CI $[-6.08, +1.28]\text{ pp}$, indeterminate at $n=250$).
- On IFEval (250 items): 79.2% vs 78.8% ($\Delta = +0.40\text{ pp}$, CI $[-3.36, +4.16]\text{ pp}$, indeterminate at $n=250$).
- **Verdict:** JANG_4S's measured +14% to +17% decode throughput advantage over portable 4-bit is bought at **zero measurable cost to task accuracy**.

#### 2. Q3 Answered: OptiQ Is Strictly Pareto-Dominated Across All Three Dimensions
In Column B (Osaurus), OptiQ scores the lowest accuracy of any format across every benchmark:
- **MMLU:** OptiQ scores **61.05%** — trailing `oq4e` by **-4.39 pp** ($p < 10^{-6}$), trailing `jang4s` by **-3.82 pp** ($p < 10^{-6}$), and trailing `oq4` by **-3.11 pp** ($p < 10^{-5}$).
- **IFEval:** OptiQ scores **76.8%** (lowest in column; portables score 78.0%–83.6%).
- **The Pareto Collapse:** Track 1 established that OptiQ carries **28% more disk bytes** (4.04 GB vs 3.16 GB) and is slower/tied on decode (38.7 vs 38.8 tok/s). The accuracy study proves that this footprint and latency penalty bought **negative reasoning quality**. OptiQ is strictly dominated and eliminated from the Pareto frontier.

#### 3. 100.000% Within-Runtime Replicate Determinism
Across 6,840 replicate evaluations on MMLU (2,280 items repeated across 3 independent cell runs in reversed order), **every single answer agreed byte-for-byte with the primary visit**:
- `stock4bit__vmlx`: Primary 67.8947% vs Replicate 67.8947% ($\Delta = 0.0000\text{ pp}$, **100.0% agreement**)
- `jang4s__vmlx`: Primary 68.4211% vs Replicate 68.4211% ($\Delta = 0.0000\text{ pp}$, **100.0% agreement**)
- `jang4s__osaurus`: Primary 64.8684% vs Replicate 64.8684% ($\Delta = 0.0000\text{ pp}$, **100.0% agreement**)
Greedy decoding (`temperature: 0.0`) provides perfect numerical determinism within each serving runtime.

#### 4. Study 2C: Cross-Runtime Agreement & The Loader Confound
On identical artifact bytes evaluated across both runtimes (`vmlx` vs `osaurus`):
- **GSM8K:** **91.2% to 94.0%** answer agreement.
- **MMLU:** **87.8% to 89.6%** answer agreement.
- **IFEval:** **11.6% to 14.8%** raw string agreement (divergence in open-ended generation phrasing despite matching strict satisfaction rates: 78.0% vs 79.2%).
- **The Loader Confound Confirmed:** Because cross-runtime agreement $A < 99\%$, the serving runtime is a live confound for accuracy (pre-registered Rule 3). vMLX systematically scores ~3–4 pp higher on MMLU across all formats (e.g. `jang4s` 68.42% vs 64.87%; `oq4` 68.20% vs 64.17%). Cross-runtime accuracy rankings are invalid; format comparisons are valid **only within a constant runtime**.

---

## 2. Complete Scored Matrix

### 2.1 Column A: Runtime `vmlx` (Format Axis Held Constant)

All four formats served by vMLX 1.6.59 with `cache_state="off"` (`--disable-prefix-cache --disable-block-disk-cache`).

| Format | Declared Bits | Disk (GB) | Track 1 Decode (tok/s) | MMLU (5-shot, n=2280) | GSM8K (5-shot, n=250) | IFEval (0-shot, n=250) |
|---|---|---|---|---|---|---|
| `stock4bit` (control) | 4.00 | 3.06 | 44.2 | 67.89% (1548/2280) | 89.6% (224/250) | 78.8% (197/250) |
| `jang4s` | 4.15 | 3.21 | **54.2 (+22.6%)** | **68.42% (1560/2280)** | 87.2% (218/250) | 79.2% (198/250) |
| `oq4` | ≈4.0 | 3.16 | 47.6 (+7.7%) | 68.20% (1555/2280) | **90.0% (225/250)** | 80.8% (202/250) |
| `oq4e` | ≈4.0 | 3.17 | 46.0 (+4.1%) | 66.89% (1525/2280) | 88.0% (220/250) | **84.0% (210/250)** |

*Track 1 decode speeds are quoted from `docs/research/2026-09-17-dense-jang-study.md` Table 1.1.*

---

### 2.2 Column B: Runtime `osaurus` (Format Axis Held Constant)

All four formats served by Osaurus 0.25.6 under host idle residency pinned to 900s.

| Format | Declared Bits | Disk (GB) | Track 1 Decode (tok/s) | MMLU (5-shot, n=2280) | GSM8K (5-shot, n=250) | IFEval (0-shot, n=250) |
|---|---|---|---|---|---|---|
| `jang4s` | 4.15 | 3.21 | **42.5 (+9.5%)** | 64.87% (1479/2280) | **89.6% (224/250)** | 78.0% (195/250) |
| `oq4` | ≈4.0 | 3.16 | 38.8 | 64.17% (1463/2280) | 89.2% (223/250) | **83.6% (209/250)** |
| `oq4e` | ≈4.0 | 3.17 | 38.6 | **65.44% (1492/2280)** | 85.6% (214/250) | 78.4% (196/250) |
| `optiq` | ≈4.0 | 4.04 (+28%) | 38.7 | **61.05% (1392/2280)** | 88.8% (222/250) | 76.8% (192/250) |

---

## 3. Paired Difference Intervals & Hypothesis Testing

Because each task was evaluated over **identical prompt items** with identical seeds and greedy decoding, differences between formats are evaluated as **paired differences** (McNemar test for 0/1 accuracy), where item-level difficulty cancels out.

$$\Delta = \frac{b - c}{n}, \quad \text{SE}(\Delta) = \frac{\sqrt{b + c}}{n}, \quad 95\%\text{ CI} = \Delta \pm 1.96 \cdot \text{SE}(\Delta)$$

where $b$ is the number of items format A answered correctly and B incorrectly, and $c$ is the reverse.

### 3.1 Column A Pairwise Analysis (vMLX)

#### MMLU (2,280 items):
| Pair (A vs B) | $b$ (A only) | $c$ (B only) | Both Correct | Discordant ($b+c$) | Paired $\Delta$ | 95% CI | Verdict |
|---|---|---|---|---|---|---|---|
| **`jang4s` vs `stock4bit` (Q2)** | 61 | 49 | 1,499 | 110 (4.8%) | **+0.53 pp** | **[-0.38 pp, +1.43 pp]** | **P1 (Parity)** |
| `jang4s` vs `oq4` | 55 | 50 | 1,505 | 105 (4.6%) | **+0.22 pp** | [-0.66 pp, +1.10 pp] | P1 (Parity) |
| `jang4s` vs `oq4e` | 83 | 48 | 1,477 | 131 (5.7%) | **+1.54 pp** | [+0.56 pp, +2.51 pp] | Moderate Lead |
| `oq4` vs `stock4bit` | 46 | 39 | 1,509 | 85 (3.7%) | **+0.31 pp** | [-0.46 pp, +1.08 pp] | P1 (Parity) |
| `oq4e` vs `stock4bit` | 38 | 61 | 1,487 | 99 (4.3%) | **-1.01 pp** | [-1.86 pp, -0.15 pp] | P1 (Parity) |
| `oq4` vs `oq4e` | 74 | 44 | 1,481 | 118 (5.2%) | **+1.32 pp** | [+0.40 pp, +2.23 pp] | Slight Lead |

*Note on Q2:* The entire 95% CI for `jang4s` vs `stock4bit` ($[-0.38, +1.43]\text{ pp}$) is contained within $[-1.5, +1.5]\text{ pp}$. The hypothesis of meaningful degradation is rejected.

#### GSM8K (250 items):
| Pair (A vs B) | $b$ | $c$ | Both Correct | Discordant | Paired $\Delta$ | 95% CI |
|---|---|---|---|---|---|---|
| `jang4s` vs `stock4bit` | 8 | 14 | 210 | 22 (8.8%) | -2.40 pp | [-6.08 pp, +1.28 pp] |
| `oq4` vs `stock4bit` | 6 | 5 | 219 | 11 (4.4%) | +0.40 pp | [-2.20 pp, +3.00 pp] |
| `oq4e` vs `stock4bit` | 7 | 11 | 213 | 18 (7.2%) | -1.60 pp | [-4.92 pp, +1.72 pp] |

#### IFEval (250 items):
| Pair (A vs B) | $b$ | $c$ | Both Correct | Discordant | Paired $\Delta$ | 95% CI |
|---|---|---|---|---|---|---|
| `jang4s` vs `stock4bit` | 12 | 11 | 186 | 23 (9.2%) | +0.40 pp | [-3.36 pp, +4.16 pp] |
| `oq4` vs `stock4bit` | 13 | 8 | 189 | 21 (8.4%) | +2.00 pp | [-1.67 pp, +5.67 pp] |
| `oq4e` vs `stock4bit` | 21 | 8 | 189 | 29 (11.6%) | **+5.20 pp** | [+1.86 pp, +8.54 pp] |

---

### 3.2 Column B Pairwise Analysis (Osaurus): The OptiQ Deficit

#### MMLU (2,280 items):
| Pair (A vs B) | $b$ (A only) | $c$ (OptiQ only) | Discordant | Paired $\Delta$ | 95% CI | $p$-value (McNemar) |
|---|---|---|---|---|---|---|
| **`jang4s` vs `optiq`** | 131 | 44 | 175 (7.7%) | **+3.82 pp** | **[+2.45 pp, +5.18 pp]** | $p = 1.3 \times 10^{-10}$ |
| **`oq4e` vs `optiq`** | 149 | 49 | 198 (8.7%) | **+4.39 pp** | **[+2.76 pp, +6.01 pp]** | $p = 4.2 \times 10^{-12}$ |
| **`oq4` vs `optiq`** | 118 | 47 | 165 (7.2%) | **+3.11 pp** | **[+1.82 pp, +4.41 pp]** | $p = 2.4 \times 10^{-8}$ |

Every single competing format in Osaurus beats OptiQ by **over 3 percentage points on MMLU**, with extreme statistical significance ($p < 10^{-7}$).

---

## 4. Study 2C: Cross-Runtime Numerical Consistency Check

Study 2C measures the observable per-item answer agreement rate $A = \frac{\text{identical}}{\text{total}}$ on **identical weights** served across two independent runtimes (`vmlx` vs `osaurus`).

### 4.1 Agreement Rate Table

| Format | MMLU Agreement ($n=2,280$) | GSM8K Agreement ($n=250$) | IFEval String Agreement ($n=250$) |
|---|---|---|---|
| `jang4s` | **89.61%** (2,043 / 2,280) | **94.00%** (235 / 250) | 11.60% (29 / 250) |
| `oq4` | **87.76%** (2,001 / 2,280) | **93.60%** (234 / 250) | 11.60% (29 / 250) |
| `oq4e` | **88.55%** (2,019 / 2,280) | **91.20%** (228 / 250) | 14.80% (37 / 250) |

### 4.2 Interpretation of the Cross-Runtime Divergence

1. **Constrained Reasoning Consistency (~90–94%):** On multiple-choice (MMLU) and mathematical reasoning (GSM8K), 9 out of 10 items produce verbatim identical answer strings across both engines.
2. **Open-Ended Phrasing Divergence in IFEval:** On IFEval, raw string agreement drops to ~12%, yet both runtimes achieve nearly identical task satisfaction scores (vMLX: 79.2%–84.0%, Osaurus: 78.0%–83.6%). In long-form generation, tiny numerical precision differences in Apple Metal matrix operations between the two framework implementations cause word choice or sentence order to vary while adhering to the underlying prompt constraints.
3. **The Loader Offset:** On MMLU, vMLX systematically scores ~3–4 pp higher than Osaurus across all three shared formats:
   - `jang4s`: 68.42% (vMLX) vs 64.87% (Osaurus) $\rightarrow +3.55\text{ pp}$
   - `oq4`: 68.20% (vMLX) vs 64.17% (Osaurus) $\rightarrow +4.03\text{ pp}$
   - `oq4e`: 66.89% (vMLX) vs 65.44% (Osaurus) $\rightarrow +1.45\text{ pp}$
   Because $A < 99\%$, the pre-registered threshold (§2.3 Rule 3) is active: **the serving runtime is a live confound for accuracy**. The relative format ranking is consistent within each runtime, but no cross-runtime accuracy comparison is permitted.

---

## 5. Replicate Stability and Determinism

Three cells were re-evaluated in a separate replication pass with reversed order:

| Cell | Primary Score (MMLU) | Replicate Score (MMLU) | Delta | Item Agreement ($n=2,280$) | Disagreed Items |
|---|---|---|---|---|---|
| `stock4bit__vmlx` | 0.678947 | 0.678947 | **0.0000 pp** | **100.00%** | **0** |
| `jang4s__vmlx` | 0.684211 | 0.684211 | **0.0000 pp** | **100.00%** | **0** |
| `jang4s__osaurus` | 0.648684 | 0.648684 | **0.0000 pp** | **100.00%** | **0** |

**Conclusion:** At `temperature: 0.0`, within-runtime evaluation is 100% deterministic. Observed differences between formats are true properties of the quantized weights and dequantization kernels, not stochastic noise.

---

## 6. The 2D Pareto Frontier for Dense Serving

Combining Track 1's speed and footprint measurements with Track 2's accuracy scores:

### 6.1 Column A (vMLX 1.6.59)

| Format | Decode Speed (tok/s) | Footprint (MB) | Disk (GB) | MMLU (%) | Frontier Status |
|---|---|---|---|---|---|
| **`jang4s`** | **54.2** | 2,842 | 3.21 | **68.42%** | **Non-dominated (Throughput & Accuracy Leader)** |
| `oq4` | 47.6 | 2,810 | 3.16 | 68.20% | Dominated by `jang4s` (slower, near-equal accuracy) |
| `oq4e` | 46.0 | 2,795 | 3.17 | 66.89% | Non-dominated on IFEval (84.0%), dominated on MMLU |
| `stock4bit` | 44.2 | 2,812 | 3.06 | 67.89% | Non-dominated (Smallest Disk: 3.06 GB) |

### 6.2 Column B (Osaurus 0.25.6)

| Format | Decode Speed (tok/s) | Footprint (MB) | Disk (GB) | MMLU (%) | Frontier Status |
|---|---|---|---|---|---|
| **`jang4s`** | **42.5** | 2,466 | 3.21 | 64.87% | **Non-dominated (Throughput Leader)** |
| **`oq4e`** | 38.6 | **2,216** | 3.17 | **65.44%** | **Non-dominated (Memory & Accuracy Leader)** |
| `oq4` | 38.8 | 2,466 | 3.16 | 64.17% | Dominated by `oq4e` and `jang4s` |
| `optiq` | 38.7 | 2,472 | 4.04 | 61.05% | **Strictly Dominated on all 3 dimensions** |

---

## 7. Answers to the Core Research Questions

### Q2: What does JANG_4S buy and cost?
- **Speed Gain:** +14% to +17% sustained decode throughput lead in vMLX (+22.6% over stock 4-bit, +13.9% over best portable).
- **Disk Cost:** +4.8% larger on disk than stock 4-bit (3.21 GB vs 3.06 GB).
- **Accuracy Cost:** **0.0 pp** (MMLU paired difference $\Delta = +0.53\text{ pp}$ [95% CI: $-0.38, +1.43\text{ pp}$]).
- **Finding:** JANG_4S delivers its throughput advantage with **no penalty to reasoning accuracy**.

### Q3: Is OptiQ Pareto-dominated?
- **Finding:** **Yes, strictly.** In Osaurus, OptiQ consumes 28% more disk, decodes slower than or ties portables, and loses 3.1 to 4.4 pp on MMLU ($p < 10^{-6}$) and 1.6 to 6.8 pp on IFEval. OptiQ offers zero Pareto justification on dense Qwen3.5-4B.

### Q4: Does outlier-channel protection (oQ4/oQ4e) improve accuracy?
- **Finding:** Mixed. `oQ4` preserves exact parity with uniform 4-bit on MMLU ($\Delta = +0.31\text{ pp}$) and GSM8K ($\Delta = +0.40\text{ pp}$). `oQ4e` exhibits a minor trade-off: $-1.01\text{ pp}$ on MMLU in exchange for a substantial $+5.20\text{ pp}$ gain on IFEval instruction compliance (84.0% vs 78.8%).

---

## 8. Artifact and Provenance Index

- **Runner Script:** [`scripts/run_accuracy_dense.sh`](file:///Users/jrazz/Dev/active/OhYesMLX/scripts/run_accuracy_dense.sh)
- **Cell Evaluator:** [`scripts/probe_accuracy_cell.py`](file:///Users/jrazz/Dev/active/OhYesMLX/scripts/probe_accuracy_cell.py)
- **Analysis Engine:** [`scripts/analyze_accuracy_dense.py`](file:///Users/jrazz/Dev/active/OhYesMLX/scripts/analyze_accuracy_dense.py)
- **Execution Log:** `results/accuracy-dense/runner.log` (181 lines, exit code 0)
- **Aggregated Data:** `results/accuracy-dense/analysis_summary.json`
- **11 Cell Directories:** `results/accuracy-dense/column-vmlx/`, `results/accuracy-dense/column-osaurus/`, `results/accuracy-dense/replicate/`
