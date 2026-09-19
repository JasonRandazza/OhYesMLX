# Plan 02-03 — the MoE accuracy study: `LFM2.5-8B-A1B` in vMLX and Osaurus

Date: 2026-09-19. **Measured.** Evaluated 2026-09-18 17:27:12 to 2026-09-19 09:46:47 local
(16h 19m 35s wall clock; the eight cell windows sum to 16h 18m 43s) across 8 cell runs
(5 primary format-cells on vMLX, 2 replicate cells, 1 Study 2C cell on Osaurus), **9,340 scored
item evaluations**. Design, test matrix, budget dial and pre-registered interpretation rules:
[`docs/research/2026-09-17-v2-track2-accuracy-study-design.md`](file:///Users/jrazz/Dev/active/OhYesMLX/docs/research/2026-09-17-v2-track2-accuracy-study-design.md)
(§2.2, §3.3, §5, §6.4). Track 1's speed and memory coordinates are **quotations, never
re-measured**: [`docs/research/2026-09-17-moe-jang-study.md`](file:///Users/jrazz/Dev/active/OhYesMLX/docs/research/2026-09-17-moe-jang-study.md)
(§3.1, §4.1) via [`docs/research/2026-09-17-jang-cross-runtime.md`](file:///Users/jrazz/Dev/active/OhYesMLX/docs/research/2026-09-17-jang-cross-runtime.md) (§3.2, §6.1).

Every number in this document is computed from the 8 cell manifests, their task-level result
files, and the sample rows under `results/accuracy-moe/`, and each one was re-derived
independently from those sample rows and checked against
`results/accuracy-moe/analysis_summary.json` before publication (§6). Where the record's own
shorthand for a failure is narrower than what the logs show, §1.2 finding 5 corrects it and says
so.

Three facts frame the whole study and are stated once here:

1. **This campaign ran one format axis in one runtime** (design §2.2): five `LFM2.5-8B-A1B`
   formats in vMLX 1.6.59, plus a two-cell MMLU replicate of the claim-bearing pair, plus the
   Study 2C cross-runtime leg (`jang2l__osaurus`, Osaurus 0.25.6).
2. **The budget dial was applied** — the design's one permitted downward revision (§3.3): MMLU
   at 20 items/subject = **1,140 items**, GSM8K 250, IFEval 250. Every cell saw the same items.
   ARC-Challenge was not run: it was dropped upstream under **Decision 103** for an extraction
   filter defect, the same decision the dense study took.
3. **The reasoning channel stayed live for every cell**, because LFM2 exposes no instruct mode
   in vMLX and `enable_thinking=false` is refused with HTTP 400 (Decision 105). That condition
   produced this campaign's four task halts and is finding 5 below.

---

## 1. Executive summary and headline findings

### 1.1 What ran

| # | cell | runtime | started → ended (local) | duration | items scored | MMLU (n=1,140) | GSM8K (n=250) | IFEval (n=250) | status |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `stock4bit__vmlx` | vMLX 1.6.59 | 09-18 17:27:17 → 20:10:46 | 2h 43m 29s | 1,390 | 35.53% | **FAIL** (halted, item 176) | 52.0% | **FAIL** |
| 2 | `jang2l__vmlx` | vMLX 1.6.59 | 09-18 20:10:51 → 20:58:47 | 47m 56s | 250 | **FAIL** (halted, item 80) | **FAIL** (halted, item 53) | 56.8% | **FAIL** |
| 3 | `oq4__vmlx` | vMLX 1.6.59 | 09-18 20:58:52 → 23:56:00 | 2h 57m 08s | 1,640 | 21.93% | 38.8% | 57.6% | PASS |
| 4 | `oq4e__vmlx` | vMLX 1.6.59 | 09-18 23:56:06 → 09-19 02:44:21 | 2h 48m 15s | 1,640 | 36.23% | 41.6% | 60.8% | PASS |
| 5 | `optiq__vmlx` | vMLX 1.6.59 | 09-19 02:44:26 → 05:34:17 | 2h 49m 51s | 1,640 | 28.25% | 37.6% | 62.4% | PASS |
| 6 | `jang2l__vmlx_repl` | vMLX 1.6.59 | 09-19 05:34:23 → 05:41:29 | 7m 06s | 0 | **FAIL** (halted, item 80) | — | — | **FAIL** |
| 7 | `stock4bit__vmlx_repl` | vMLX 1.6.59 | 09-19 05:41:34 → 07:21:39 | 1h 40m 05s | 1,140 | 35.53% | — | — | PASS |
| 8 | `jang2l__osaurus` | Osaurus 0.25.6 | 09-19 07:21:44 → 09:46:37 | 2h 24m 53s | 1,640 | 3.77% (see §2.2) | 33.2% | 60.4% | PASS |
| | **Total** | | **09-18 17:27:12 → 09-19 09:46:47** | **16h 19m 35s** | **9,340** | | | | **5 PASS + 3 FAIL** |

- **5 of 8 cells PASS; 3 FAIL, all four halted tasks stop on one runtime-side trap** (§1.2
  finding 5). The runner's final line is `Overall Status: FAILURES RECORDED`
  (`results/accuracy-moe/runner.log:151`). "Items scored" counts items with a recorded score:
  MMLU 1,140 (57 subjects × 20), GSM8K 250 strict-match items, IFEval 250. A GSM8K task writes
  500 sample rows because the harness emits two filter passes per item; the scored metric is
  `exact_match,strict-match` over the 250 items.
- **Port safety:** `Port 8000 verified free` after every one of the five vMLX cells and both
  replicate cells (`runner.log:25, 42, 59, 76, 93, 111, 122`); `Port 1337 verified free` after
  the Osaurus cell (`runner.log:144`). One stale Osaurus instance still holding 1337 at the end
  of Column A was swept by pid (`runner.log:95`, `sweeping port 1337 pid 98423`) before the
  Study 2C block started.
- **Osaurus host settings restored byte-exact** (`cmp`), not merely re-written:
  `osaurus settings restored byte-exact (cmp)` (`runner.log:146`), after the host's idle
  residency had been pinned to 900 s for the campaign (`runner.log:128`).
- **vMLX engine integrity:** the scheduler patch was hashed before Column A and again before the
  replication pass, both times
  `sha256 9710d2b9cf07abc7380f46fef240e64febb2d06d52eb7f64236bd0e76cf686f7`
  (`runner.log:7`, `:101`; re-verified by the evaluator before every cell,
  `scripts/probe_accuracy_cell.py:34`).
- **Canary gate on all 8 cells:** each cell answered a known-answer canary in the `content`
  channel before any benchmark item ran, and each manifest keeps the verbatim request and
  response (`4`, or `\boxed{4}` for `oq4e__vmlx`; Osaurus answered `\n4`). No cell failed the
  gate, so the floor everything else rests on — the cell produces language — held everywhere,
  including the cells whose tasks later halted.
- **Harness pin:** `lm-eval[api,ifeval]==0.4.13` under `uv run --isolated`, `max_gen_toks=1024`,
  `max_length=4096`, `--apply_chat_template` with `--fewshot_as_multiturn`; MMLU and GSM8K 5-shot,
  IFEval 0-shot; `--gen_kwargs until=<|im_end|>` and **no** `enable_thinking=false` (finding 5).

### 1.2 Headline findings

#### 1. 100.000% within-runtime replicate determinism (`stock4bit__vmlx`)

The claim-bearing control was re-run in a separate pass — primary MMLU leg 17:27–19:14 on 09-18,
replicate 05:41–07:21 on 09-19, 10h 27m later — on the identical 1,140 items:

- `stock4bit__vmlx` primary **35.53%** (405/1,140) vs replicate **35.53%** (405/1,140):
  **Δ = 0.0000 pp**, **0 discordant items**, 1,140 of 1,140 response strings identical.
- The second visit moved the wall-clock cost while leaving every answer untouched: the replicate
  MMLU leg took 5,996.4 s against the primary's 6,414.4 s (**6.5% faster**), and every scored
  answer still matched.
- At `temperature: 0.0`, within-runtime evaluation is exactly deterministic. Observed differences
  between formats are properties of the quantized bytes and their loader, not session noise.

The second replicate (`jang2l__vmlx_repl`) produced no score at all — it halted at item 80/1,140
(finding 5), and its 7m 06s cell window is the price of the halt, not a measurement. Its entry in
`analysis_summary.json` reads `agreement_pct: 0.0`; that is the analysis engine's degenerate
**no-common-items** value, not a disagreement rate, and §4.2 states it as such.

#### 2. Outcome P3 did not fire on the tasks `JANG_2L` completed: instruction following holds at 2.37 bits

- **IFEval:** `jang2l__vmlx` **56.8%** (142/250) against `stock4bit__vmlx`'s **52.0%** (130/250) —
  paired Δ = **+4.80 pp**, 95% CI [−1.17 pp, +10.77 pp], 58 discordant items, exact McNemar
  p = 0.148.
- `jang2l__osaurus` posts the campaign's highest IFEval at **60.4%** (151/250); the two runtimes
  are a live confound for this artifact (§2.2), so the two numbers are printed and no ordering is
  drawn between them.
- **The reading is indeterminate, and that is the pre-registered expectation**: the design
  states that a 250-item task cannot resolve a 1.5 pp effect even paired (design §3.3), and this
  comparison's interval straddles zero. What the data does support is the negative half of Q1's
  live hypothesis: **no collapse**. No completed score in this campaign sits at or below its
  task's floor except the two MMLU levels named in §2.1 and §2.2 (each with a measured
  instrument cause), and no JANG cell's IFEval is near its floor.
- **What is not answerable is stated as unanswerable:** `JANG_2L` produced no MMLU score and no
  GSM8K score in the vMLX column (both halted, in the primary and again in the replicate), and a
  halt is published as a halt, never as a collapse.

#### 3. Q3 answered: OptiQ is strictly Pareto-dominated on this model, by the control

- **MMLU:** `optiq` **28.25%** (322/1,140) trails `stock4bit` **35.53%** by **−7.28 pp**
  [−10.21, −4.35] (K = 291, p = 1.3 × 10⁻⁶) and trails `oq4e` **36.23%** by **−7.98 pp**
  [−10.84, −5.12] (K = 277, p = 4.9 × 10⁻⁸).
- **GSM8K:** `optiq` **37.6%** (94/250) trails `oq4e` **41.6%** (104/250) by **−4.00 pp**
  [−10.92, +2.92] (K = 78, p = 0.31 — indeterminate at n = 250).
- **Resources (Track 1 quotations, never re-measured):** OptiQ's 5,473,296,789-byte bundle is
  **78.7% larger** than `jang2l`'s 3,062,430,853 B (equivalently: the JANG bundle is **44%**
  smaller, the design §5.7 figure) and **14.4% larger** than the control's 4,782,228,753 B; it
  decodes at 100.6 tok/s against `stock4bit`'s 115.3 (**14.6% slower**) and peaks at 5,869 MB
  against 5,214 MB (**12.6% more**).
- **Verdict:** `stock4bit` beats `optiq` on accuracy, decode rate, peak footprint *and* disk
  bytes, each by more than its own band. The dominance is per-pair (design §5.5) and it holds on
  every pair, so OptiQ is **eliminated from the MoE frontier**: its resource penalty bought
  negative accuracy against the control.

#### 4. Q4 answered: outlier protection is not one thing — the two protected artifacts land on opposite sides of the control

- `oq4e` vs `stock4bit` on MMLU: **+0.70 pp** [−2.27, +3.67] (K = 298, p = 0.685) — an
  **indeterminate** comparison, not a tie: the interval escapes the ±1.5 pp band.
- `oq4` vs `stock4bit` on MMLU: **−13.60 pp** [−16.60, −10.59] (K = 305, p = 1.8 × 10⁻¹⁹).
- `oq4e` vs `oq4` on MMLU: **+14.30 pp** [+11.29, +17.31] (K = 307, **p = 2.5 × 10⁻²¹**) — the
  largest MMLU gap in the column.
- The same split appears on IFEval: `oq4e` beats `stock4bit` by **+8.80 pp** [+3.15, +14.45]
  (K = 52, p = 0.0032) while `oq4`'s +5.60 pp [−0.05, +11.25] is indeterminate.
- **The caveat travels with the number:** `oq4` (`stamsam/LFM2.5-8B-A1B-oQ4`) and `oq4e`
  (`brainworkup/LFM2.5-8B-A1B-oQ4e`) are two publishers' ≈4-bit artifacts. The 14.30 pp gap is
  a measured difference between two recipes, **not** a one-variable measurement of outlier
  protection, and no attribution beyond "these two artifacts differ" is published.

#### 5. The vMLX reasoning-channel trap halted four tasks, and it is not a token-cap effect

LFM2 exposes no instruct mode in vMLX (`supports_instruct_mode=False`; Decision 105), so
`enable_thinking=false` is refused with HTTP 400 and was not passed for any cell in this campaign
(`--no-disable-thinking`, `scripts/run_accuracy_moe.sh:113`). The reasoning channel therefore
stayed live, and the trap Decision 102 had closed for the dense model stayed open here:

- **The mechanism, as recorded:** when a completion ends carrying `reasoning_content` and no
  visible answer and no tool call, vMLX answers **HTTP 502** with
  `{"type":"invalid_response_error","code":"reasoning_only_no_content","message":"The model
  produced reasoning_content but no visible answer and no tool call. This turn is incomplete;
  retry with a larger output budget or adjust the prompt/reasoning settings."}` instead of a 200
  with empty content. `lm-evaluation-harness` retries three times — three 502s land in the
  runtime log, three `reasoning_only_no_content` warnings in the harness log — and then raises
  an uncaught `requests.exceptions.HTTPError: 502 Server Error`. The task subprocess exits with
  `returncode 139` and the task is recorded FAIL with no score. The canary and every
  non-halting item are unaffected; this is an item-level refusal, not a cell crash.
- **The four halts:** `stock4bit__vmlx` GSM8K at item **176/250**; `jang2l__vmlx` MMLU at item
  **80/1,140** and GSM8K at item **53/250**; `jang2l__vmlx_repl` MMLU at item **80/1,140**
  again. The two MMLU halts are the *same item failing the same way 9h 23m apart* — 196 tokens
  generated, refused, retried, refused again — which is determinism showing up as a defect.
- **Correction to the record's shorthand:** these refusals are **not** 1,024-token cap
  truncations. The campaign's generation cap was `max_gen_toks=1024`, and every refused
  completion ended well under it — the runtime log's own token counts are **196** (both
  `jang2l` MMLU halts), **432** (`stock4bit` GSM8K) and **507** (`jang2l` GSM8K). What the
  runtime rejects is a completion with no visible answer channel, whatever its length; a longer
  budget is the error message's advice, not this failure's cause.
- **Cost to the study:** two of the five formats lost their MMLU leg and one lost GSM8K; the
  `JANG_2L` MMLU cell does not exist in either visit, which is what makes Q1 unanswerable as
  measured (§5.3).

#### 6. Study 2C: Osaurus `JANG_2L` completed all three tasks — and its MMLU number is an extraction artifact

- `jang2l__osaurus` finished 100% of its plan (cell PASS, exit 0): GSM8K **33.2%** (83/250),
  IFEval **60.4%** (151/250), MMLU **3.77%** (43/1,140).
- **The MMLU number measures the extraction path, and the record shows why:** 845 of 1,140
  responses are prose rather than a bare letter, 171 are empty, 124 reduce to a bare letter.
  The task's `get_response` filter returns the whole content channel and `exact_match` compares
  it to a single-character key, so **prose scores zero however right it is** —
  e.g. an item keyed `D` answered "…Answer: D. Idols" scores 0. Under a stated, reproducible
  diagnostic (§2.2) 207 responses state an explicit answer letter and 113 state the key's
  letter, a lower bound of 9.9% against the recorded 3.77%.
- Because the score is instrument-limited, it is published with that label and **no cross-cell or
  cross-runtime reading is drawn from it** — and it is also below the design's 25% four-option
  floor with a measured cause, which §2.2 states rather than hides.
- **2C's agreement instrument has one leg of three.** On identical bytes, vMLX and Osaurus can be
  compared only on IFEval: **13.6%** identical response strings (34/250), far under the
  pre-registered 99% threshold, so the loader remains a live confound for this artifact
  (design §2.3 rule 3). MMLU and GSM8K agreements are not computable — the vMLX side of both
  comparisons is the halted `JANG_2L` cell, so there are zero common items.

---

## 2. Complete scored matrix

### 2.1 Column A — runtime `vmlx` (format axis held constant)

All five formats served by vMLX 1.6.59 with `cache_state="off"` in every manifest, the patched
scheduler hash verified per cell, and 20 MMLU items per subject on the design's dialed budget.

| Format | Declared bits | Disk (GB) | Track 1 decode (tok/s) | MMLU (5-shot, n=1,140) | GSM8K (5-shot, n=250) | IFEval (0-shot, n=250) |
|---|---|---|---|---|---|---|
| `stock4bit` (control) | 4.00 uniform | 4.782 | 115.3 | 35.53% (405/1,140) | **FAIL** — halted, item 176 | 52.0% (130/250) |
| `jang2l` | **2.37** average | **3.062** | **116.3** | **FAIL** — halted, item 80 (both visits) | **FAIL** — halted, item 53 | 56.8% (142/250) |
| `oq4` | ≈4, mixed | 4.995 | 65.6 ⚠ | 21.93% (250/1,140) ⚠ | 38.8% (97/250) | 57.6% (144/250) |
| `oq4e` | ≈4, mixed | 4.995 | 97.0 | 36.23% (413/1,140) | 41.6% (104/250) | 60.8% (152/250) |
| `optiq` | ≈4, mixed | 5.473 | 100.6 | 28.25% (322/1,140) | 37.6% (94/250) | 62.4% (156/250) |

*Declared bits and disk bytes are quoted from the design's artifact table (§2.4). Track 1 decode
speeds are quotations from the MoE JANG study (§3.1), carried in the design's §5.6 table; this
study did not re-measure a single tok/s or byte. **⚠ `oq4`'s decode figure carries its Track 1
drift annotation (+76.0%)**: its window never closed, so 65.6 narrates the window more than the
artifact (MoE §3.1). Its accuracy numbers are unaffected — a score does not depend on the speed
coordinate.*

**The MMLU column is exact-string-match over the `content` channel, and that is a measured limit
on every number in it.** The task's `get_response` filter returns each response whole and
`exact_match` compares it to a one-character key, so only responses that reduce to a bare letter
can score. The response forms differ widely across cells:

| cell | bare letter | empty | prose/other | of the bare letters, matched key |
|---|---|---|---|---|
| `stock4bit__vmlx` | 592 | 209 | 339 | 405 (68.4%) |
| `jang2l__vmlx` | — no MMLU samples — | | | |
| `oq4__vmlx` | 347 | 193 | 600 | 250 (72.0%) |
| `oq4e__vmlx` | 568 | 202 | 370 | 413 (72.7%) |
| `optiq__vmlx` | 444 | 208 | 488 | 322 (72.5%) |
| `jang2l__osaurus` | 124 | 171 | 845 | 43 (34.7%) |

*Counts are of the 1,140 `get_response` outputs per cell: "bare letter" = the output equals one
of `A`–`D` (a `\boxed{X}` wrapper counted with it); "empty" = blank output; "prose/other" =
everything else. Recomputable from each cell's `mmlu_generative/**/samples_*.jsonl`.*

Two consequences ride on that table, and both are limits rather than findings:

1. **The metric is not form-invariant across cells.** Where the response was a bare letter the
   criterion is clean (68–73% of those matched the key in the four vMLX cells), but the *share*
   of responses that take that form varies from 30% (`oq4`) to 52% (`stock4bit`) — so cell-to-cell
   MMLU differences carry a response-form component that this study did **not** quantify and
   does not correct for. The pairwise intervals below remove item difficulty, not form
   propensity.
2. **Two cells' point scores sit below the design's 25% four-option floor** (§5.3(a)):
   `oq4__vmlx` at 21.93% and `jang2l__osaurus` at 3.77%. Both are published with the floor named
   and their form counts beside them, and neither is promoted to a capability collapse, because
   the measured cause in both cases is the response form. The campaign's own record does not
   classify them either way: the runner marks `oq4__vmlx` PASS, and no floor check exists in the
   analysis engine. This report states the rule it is not satisfying rather than quietly
   dropping it.

### 2.2 Study 2C — runtime `osaurus` (`jang2l__osaurus`)

Same bytes as `jang2l__vmlx` (snapshot `5fb82773…`, 3,062,430,853 B), served by Osaurus 0.25.6
with idle residency pinned to 900 s and the host's settings restored `cmp`-verified after the
block.

| Format | Declared bits | Disk (GB) | Track 1 decode (tok/s) | MMLU (5-shot, n=1,140) | GSM8K (5-shot, n=250) | IFEval (0-shot, n=250) |
|---|---|---|---|---|---|---|
| `jang2l` (Osaurus) | 2.37 average | 3.062 | 116.7 | 3.77% (43/1,140) † | 33.2% (83/250) | **60.4% (151/250)** |

*† The MMLU number is instrument-limited; see below. Track 1's Osaurus decode quotation is
116.7 tok/s (MoE §4.1), against `stock4bit__osaurus`'s 123.0 — Track 1 measured a replicated
5.12% / 9.80% `stock4bit` lead on this model in this runtime, which is why no Osaurus Pareto
column is drawn (design §2.2, §5.5).*

#### The MMLU extraction confound, measured

The cell's 3.77% is 43 exact matches out of 1,140 items. The distribution of `get_response`
outputs explains what the number is measuring:

| form of the response | items | score under `exact_match` |
|---|---|---|
| prose of more than a bare letter | **845** | 0, however correct |
| empty output | 171 | 0 |
| reduced to a bare letter | 124 | 43 matched the key (34.7%) |

- **Two verbatim samples** (both keyed correctly, both scored 0): `…Among the options provided,
  "Idols" (D) is the most plausible translation… Answer: D. Idols` on an item keyed `D`; and
  `The correct answer is **B. Consumer relations**…` on an item keyed `B`.
- **A stated-rule diagnostic**, not a score: matching
  `(?i)(final answer|correct answer|answer)\s*(is|:)?\s*[*\s]*([ABCD])\b` against each response
  finds **207** responses stating an explicit answer letter, of which **113** state the key's
  letter — a lower bound of **9.9%** of items whose text names the right answer, against the
  3.77% recorded. (The same rule applied to the vMLX cells finds fewer stated letters than their
  `exact_match` counts, because their main path is the bare letter, not prose.)
- **What may and may not be read from it.** The published number is 3.77%, with the confound
  named. It is **not** a capability measurement, it is **not** comparable with any other cell's
  MMLU score, and it is below the design's 25% four-option floor — so no Δ, no Pareto position
  and no cross-runtime claim is drawn from it. The honest one-line reading is: *the cell's MMLU
  score measures a filter that this artifact's answer style defeats, and the study publishes it
  as a floor-shaped artifact rather than as a result.*

#### Cross-runtime answer agreement (the designed 2C reading)

| task | agreement | n | status |
|---|---|---|---|
| MMLU | — | 0 common items | **not computable** — the vMLX side halted at item 80 |
| GSM8K | — | 0 common items | **not computable** — the vMLX side halted at item 53 |
| IFEval | **13.6%** (34/250) | 250 | computed; far under the pre-registered 99% threshold |

The first IFEval disagreement is item 1: vMLX opens "Morning arrival in Tokyo. First explore the
neon lights of Shibuya…" and Osaurus opens "A Shakespearean Journey Across Japan\n\nDay one:
Arrive in Tokyo with a sonnet of neon lights…" — the same instruction-following task answered in
visibly different prose, which is the same open-ended-phrasing divergence the dense study
measured (11.6%–14.8% on its three formats), not a change in task satisfaction: both runtimes
land within 3.6 pp of each other on IFEval (60.4% vs 56.8%) and neither number may be read as an
ordering across runtimes (design §2.3 rules 2–3).

---

## 3. Paired difference intervals and hypothesis testing

Every benchmark ran on **identical prompt items** with identical seeds and greedy decoding, so
differences between cells are evaluated as **paired differences** (McNemar), where item
difficulty cancels:

$$\Delta = \frac{b - c}{n}, \qquad \text{SE}(\Delta) = \frac{\sqrt{b + c}}{n}, \qquad
95\%\ \text{CI} = \Delta \pm 1.96\,\text{SE}(\Delta)$$

where $b$ is the number of items format A answered correctly and B incorrectly, and $c$ the
reverse. $K = b + c$ is the discordant count and is printed with every row — it is the quantity
that says how distinguishable the two cells were on this item set at all (design §5.2).

Three rules govern the tables below, and they are stated before the numbers:

1. **The exact-binomial fallback never fired.** The design mandates the exact interval when
   $K < 25$ (design §3.3); the smallest $K$ in this campaign is 32 (`optiq` vs `oq4e`, IFEval),
   so every interval below is the normal-approximation form, and the exact **two-sided binomial
   McNemar p-value** is reported beside it.
2. **The replicate gate is not satisfied for any row.** The design publishes its P1/P2 readings
   only where primary and replicate agree on the bin (design §5.2–§5.3), and only one comparison
   in this campaign was replicated — the Q1 pair — whose MMLU leg has no samples on either side.
   Accordingly **no row in this section carries a P1/P2 label**; each row is published as the
   measured paired difference with its interval and p-value, exactly as the dense study published
   its non-replicated pairs. The tie/difference/indeterminate *statistical* conditions are named
   where they apply, with the gate noted.
3. **Pairing was verified by item key, not by the design's hash field.** Every comparison below
   intersects the raw sample sets on `(subject, doc_id)` and reports the common count
   (1,140/1,140 for every MMLU pair, 250/250 elsewhere). The manifests' `task_hashes` field is
   populated for GSM8K and IFEval but **empty for `mmlu_generative`** in all eight cells — a
   record gap inherited from the evaluator, named here so that no reader assumes an identity
   hash that is not in the record.

### 3.1 MMLU (5-shot, n = 1,140)

| Pair (A vs B) | $b$ (A only) | $c$ (B only) | Both correct | Both wrong | $K$ | Paired Δ | 95% CI | $p$ (exact) | condition |
|---|---|---|---|---|---|---|---|---|---|
| **`optiq` vs `stock4bit`** | 104 | 187 | 218 | 631 | 291 | **−7.28 pp** | **[−10.21, −4.35] pp** | $1.3\times10^{-6}$ | interval excludes zero |
| `optiq` vs `oq4` | 168 | 96 | 154 | 722 | 264 | **+6.32 pp** | [+3.52, +9.11] pp | $1.1\times10^{-5}$ | interval excludes zero |
| **`optiq` vs `oq4e`** | 93 | 184 | 229 | 634 | 277 | **−7.98 pp** | **[−10.84, −5.12] pp** | $4.9\times10^{-8}$ | interval excludes zero |
| `oq4` vs `stock4bit` | 75 | 230 | 175 | 660 | 305 | **−13.60 pp** | [−16.60, −10.59] pp | $1.8\times10^{-19}$ | interval excludes zero |
| `oq4e` vs `stock4bit` | 153 | 145 | 260 | 582 | 298 | **+0.70 pp** | [−2.27, +3.67] pp | 0.685 | **indeterminate** |
| **`oq4` vs `oq4e`** | 72 | 235 | 178 | 655 | 307 | **−14.30 pp** | **[−17.31, −11.29] pp** | $\mathbf{2.5\times10^{-21}}$ | interval excludes zero |

*The `jang2l__vmlx` × every-cell MMLU rows are absent by arithmetic, not by omission: the JANG
cell has no MMLU samples from either visit, so every pair with it has zero common items. The
analysis engine's entries for those pairs read `n: 0, delta_pp: 0.0` — the degenerate
no-comparison return, never a measured zero.*

### 3.2 GSM8K (5-shot, n = 250)

| Pair (A vs B) | $b$ | $c$ | Both correct | Both wrong | $K$ | Paired Δ | 95% CI | $p$ (exact) | condition |
|---|---|---|---|---|---|---|---|---|---|
| `oq4` vs `oq4e` | 30 | 37 | 67 | 116 | 67 | −2.80 pp | [−9.22, +3.62] pp | 0.464 | indeterminate |
| `optiq` vs `oq4` | 29 | 32 | 65 | 124 | 61 | −1.20 pp | [−7.32, +4.92] pp | 0.798 | indeterminate |
| `optiq` vs `oq4e` | 34 | 44 | 60 | 112 | 78 | −4.00 pp | [−10.92, +2.92] pp | 0.308 | indeterminate |

*`stock4bit__vmlx` has no GSM8K samples (halted at item 176), so all of its GSM8K pairs —
including Q1's — have zero common items and are not computed; `jang2l__vmlx`'s halted GSM8K
removes its pairs the same way.*

### 3.3 IFEval (0-shot, n = 250)

| Pair (A vs B) | $b$ | $c$ | Both correct | Both wrong | $K$ | Paired Δ | 95% CI | $p$ (exact) | condition |
|---|---|---|---|---|---|---|---|---|---|
| **`jang2l` vs `stock4bit`** | 35 | 23 | 107 | 85 | 58 | **+4.80 pp** | [−1.17, +10.77] pp | 0.148 | **indeterminate** |
| `jang2l` vs `oq4` | 29 | 31 | 113 | 77 | 60 | −0.80 pp | [−6.87, +5.27] pp | 0.897 | indeterminate |
| `jang2l` vs `oq4e` | 19 | 29 | 123 | 79 | 48 | −4.00 pp | [−9.43, +1.43] pp | 0.193 | indeterminate |
| `jang2l` vs `optiq` | 20 | 34 | 122 | 74 | 54 | −5.60 pp | [−11.36, +0.16] pp | 0.076 | indeterminate |
| `optiq` vs `stock4bit` | 38 | 12 | 118 | 82 | 50 | **+10.40 pp** | [+4.86, +15.94] pp | 0.0003 | interval excludes zero |
| `optiq` vs `oq4` | 25 | 13 | 131 | 81 | 38 | +4.80 pp | [−0.03, +9.63] pp | 0.073 | indeterminate |
| `optiq` vs `oq4e` | 18 | 14 | 138 | 80 | 32 | +1.60 pp | [−2.83, +6.03] pp | 0.597 | indeterminate |
| `oq4` vs `stock4bit` | 33 | 19 | 111 | 87 | 52 | +5.60 pp | [−0.05, +11.25] pp | 0.070 | indeterminate |
| `oq4e` vs `stock4bit` | 37 | 15 | 115 | 83 | 52 | **+8.80 pp** | [+3.15, +14.45] pp | 0.0032 | interval excludes zero |
| `oq4` vs `oq4e` | 18 | 26 | 126 | 80 | 44 | −3.20 pp | [−8.40, +2.00] pp | 0.291 | indeterminate |

IFEval is the **only** task on which `JANG_2L` has samples in the vMLX column, and its four rows
are the whole of what the campaign measured about that artifact's task quality. Two patterns
worth stating without ranking them: the open-ended task compresses differences (eight of ten
rows indeterminate at n = 250), and `optiq` — the worst cell on MMLU — posts the campaign's
highest IFEval, a within-column trade-off that a pooled score would have erased (design §5.4).

### 3.4 What these tables cannot say

- **`JANG_2L`'s MMLU and GSM8K comparisons do not exist.** Its `n: 0` rows are the absence of a
  measurement, and no interval, p-value or direction may be quoted from them.
- **The replicate pass covered the Q1 pair only** — two cells, one of which halted — and no other
  cell in this campaign has a second visit. A single-visit score is not called unstable by this
  study; it is called **replicated** nowhere.
- **No row carries the design's P1/P2 vocabulary** (§3, rule 2 above), and no row inside ±1.5 pp
  is called a tie unless the whole interval sits inside the band — which is why `oq4e` vs
  `stock4bit` on MMLU (Δ = +0.70 pp, interval escaping the band) is called indeterminate rather
  than parity.
- **The 250-item rows cannot resolve 1.5 pp**, by pre-registration (design §3.3): a narrow
  interval there is arithmetic, not resolution.
- **The MMLU column's form-variance limit (§2.1) rides on every MMLU row above**, including the
  two extreme ones: part of `optiq`'s −7.28 pp and part of `oq4`'s −13.60 pp is a response-form
  difference between the paired cells, not a knowledge difference. The direction of the effect is
  not estimable from this record.

---

## 4. Replicate determinism and stability

Two cells were scheduled for the replication pass — the pair that carries Q1 — on MMLU only, in
a separate block after Column A closed.

| Cell | Primary (MMLU) | Replicate (MMLU) | Δ | Identical items | Disagreed |
|---|---|---|---|---|---|
| `stock4bit__vmlx` | 0.355263 (405/1,140) | 0.355263 (405/1,140) | **0.0000 pp** | **1,140 / 1,140** | **0** |
| `jang2l__vmlx` | — (halted, item 80) | — (halted, item 80) | **void** | 0 | 0 |

### 4.1 What the completed replicate established

- **100.000% answer determinism within a runtime.** Both visits produced the same 405 correct
  items and the same 735 wrong items; the agreement check compares **response strings**, not
  scores, and found zero differences across 1,140 items.
- **The visit moved the timing, not the answers.** The replicate's MMLU leg took 5,996.4 s
  against the primary's 6,414.4 s — 6.5% faster over identical work — and every answer still
  matched. Within-cell timing on this laptop moves; the score does not.
- **Determinism is strong enough to reproduce a defect.** The `jang2l` replicate halted on
  **item 80/1,140**, the same item its primary visit failed on 9h 23m earlier, with the same
  196-token refused completion recorded server-side. A trap that reproduces item-for-item is a
  property of the item-and-runtime pair, not of the session.

### 4.2 What the record must not be read as claiming

- `jang2l__vmlx_repl` produced **no samples**, so its summary entry carries
  `score_primary: null, delta_pp: null, agreement_pct: 0.0, disagreed: 0`. The `0.0` is the
  analysis engine's degenerate no-common-items value (the same value its self-test asserts for
  the empty case), and it is **not** a claim that the replicate agreed zero percent of the time.
  There was nothing to compare, because the task halted before its first sampled item landed.
- `oq4__vmlx`, `oq4e__vmlx` and `optiq__vmlx` were never replicated: their scores are
  single-visit readings, published as measured and **not** as stable.
- The replicate covers MMLU only. No IFEval or GSM8K score in this campaign has a second visit.

---

## 5. The Pareto frontier on MoE, and answers to Q1, Q3 and Q4

The framework is the design's (§5.5): accuracy is the primary axis (MMLU), the resource axes are
Track 1's quoted `decode_tps`, `peak_mb` (within-runtime only) and `disk_bytes`
(runtime-independent), and a cell dominates another **on a pair** $(x, y)$ only when the accuracy
gap exceeds 1.5 pp with a paired interval excluding zero, **and** the resource gap exceeds its
own band (2.5% for throughput, 1% for memory, exact equality for disk). Frontier membership is
what survives every pair.

### 5.1 Coordinates (accuracy measured here; every resource figure a Track 1 quotation)

| cell | MMLU (n=1,140) | `decode_tps` | drift | `peak_mb` | `disk_bytes` | disk (GB) |
|---|---|---|---|---|---|---|
| `jang2l__vmlx` | **no score** (halted ×2) | **116.3** | +0.5 | **3,624** | **3,062,430,853** | **3.062** |
| `stock4bit__vmlx` | 35.53% | 115.3 | +3.9 | 5,214 | 4,782,228,753 | 4.782 |
| `oq4e__vmlx` | **36.23%** | 97.0 | +10.9 | 5,416 | 4,994,831,815 | 4.995 |
| `optiq__vmlx` | 28.25% | 100.6 | +6.1 | 5,869 | 5,473,296,789 | 5.473 |
| `oq4__vmlx` | 21.93% ⚠ | 65.6 ⚠ (+76.0%) | +76.0 | 5,415 | 4,994,822,580 | 4.995 |

*Resource columns are quotations from MoE JANG study §3.1 (via the design's §5.6 table); they
were not re-measured. ⚠ marks `oq4`'s unclosed warmup window, which its 65.6 tok/s narrates
rather than its artifact, and `oq4`'s floor-shaped MMLU level (§2.1).*

### 5.2 Dominance verdicts

| pair (x = MMLU, y = …) | accuracy gap | resource gap | dominance |
|---|---|---|---|
| `stock4bit` vs `optiq` | +7.28 pp, CI excludes zero | decode +14.6%, peak −11.2%, disk −12.6% — all outside bands | **`stock4bit` dominates `optiq` on all three pairs** |
| `oq4e` vs `optiq` | +7.98 pp, CI excludes zero | peak −7.7%, disk −8.7% outside bands; **decode −3.6% in OptiQ's favour** | `oq4e` dominates `optiq` on (x, peak) and (x, disk); **(x, decode) is OptiQ's** |
| `stock4bit` vs `oq4` | +13.60 pp, CI excludes zero | decode +75.8%, peak −3.7% (outside the 1% band), disk −4.3% | **`stock4bit` dominates `oq4` on all three pairs** |
| `oq4e` vs `oq4` | +14.30 pp, CI excludes zero | decode +47.9% | `oq4e` dominates `oq4` on (x, decode); peak differs by 1 MB (inside the 1% band) and disk by 9,235 bytes (short of the exact equality the rule requires), so neither resource pair dominates |
| `optiq` vs `oq4` | +6.32 pp, CI excludes zero | decode +53.4% in OptiQ's favour | **`optiq` dominates `oq4` on (x, decode)** |
| `stock4bit` vs `oq4e` | **+0.70 pp — inside the 1.5 pp band** | stock4bit faster/lighter/smaller on every axis | **no dominance**: the accuracy condition fails first |
| any pair involving `jang2l` | **no accuracy coordinate** | — | **no verdict possible** |

**The frontier that survives (MoE, vMLX, MMLU axis): `stock4bit` and `oq4e`, with `jang2l`'s
position undetermined.** `stock4bit` does not dominate `oq4e` because their accuracy difference
is inside the band, and `oq4e` does not dominate `stock4bit` because it is slower, heavier and
larger. `optiq` and `oq4` are off the frontier. `jang2l` — the fastest, smallest and lightest
artifact in the column — **cannot be placed on this frontier at all**: the coordinate that
decides every pair is the one it does not have, because its MMLU task halted in both visits.

### 5.3 Q1 — does `JANG_2L` at 2.37 bits reach or beat 4-bit on MMLU?

**Not answerable from this campaign, and not refuted by it.** The pre-registered comparison
(JANG_2L vs `stock4bit`, MMLU, vMLX) does not exist: the JANG cell halted at item 80/1,140 in
the primary and again at item 80/1,140 in the replicate, so neither side of the pair has samples.
The one completed task in that column — IFEval — shows the JANG cell **ahead** of the control by
a point estimate of +4.80 pp with an interval that straddles zero, an indeterminate reading by
pre-registration. The Osaurus copy of the artifact did complete MMLU, but its score is the
extraction artifact of §2.2.

The publishable sentence is exactly this: *under this harness, at these pins, on these items,
the parity claim was neither reproduced nor falsified — the pair's MMLU cell does not exist,
because the runtime refused two items' completions with HTTP 502 in both visits (finding 5), and
the only task the cell completed is indeterminate at n = 250. The vendor's own measurement at
the vendor's own pins is untouched by any of this.*

### 5.4 Q3 — did OptiQ's latency and footprint penalty buy accuracy, or is it dominated?

**Dominated — the penalty bought negative accuracy against the control.** `stock4bit` beats
`optiq` by **7.28 pp of MMLU** (p = 1.3 × 10⁻⁶), decodes **14.6% faster**, holds an **11.2% lower
peak footprint** (5,214 MB against 5,869 MB), and carries a **12.6%-smaller bundle** (4.782 GB
against 5.473 GB). Every gap is outside its own band, and the accuracy half is a measured paired
difference over 1,140 items.
The design's §5.7 example sentence named `jang2l` as the dominator — 15.6% faster, 44% smaller —
but that sentence assumed the JANG cell would have an accuracy coordinate, and it does not;
the published domination is the control's.

The counter-current rides with the finding: `optiq` is also the campaign's **best** cell on
IFEval (62.4%, +10.40 pp over the control, p = 0.0003) and **beats `oq4` on both accuracy and
speed**. OptiQ is eliminated from the MoE frontier, not globally condemned — on this model, in
this runtime, on these items, its resource penalty bought nothing against the format it would
have to justify itself against.

### 5.5 Q4 — does outlier-channel protection buy task accuracy over stock 4-bit?

**Not as a single variable — and the spread between the two protected artifacts is the finding.**
`oq4e` lands at effective parity with `stock4bit` on MMLU (+0.70 pp, indeterminate) and above it
on IFEval (+8.80 pp, p = 0.0032); `oq4` lands 13.60 pp **below** the control on MMLU
(p = 1.8 × 10⁻¹⁹) at a floor-shaped 21.93% with its response-form count named, and its IFEval
gain over the control is indeterminate. The two protected artifacts differ from each other by
**+14.30 pp** on MMLU — the column's largest gap, p = 2.5 × 10⁻²¹ — while carrying bundles that
differ by 9,235 bytes on disk.

Two things follow, in the design's own discipline: protection is not one thing on this model,
since its two instances bracket the control; and because the two artifacts are different
publishers' builds (a second variable beyond protection itself), the study publishes the gap as
a measured **difference between two artifacts** and declines to attribute it to the protection
mechanism.

### 5.6 What this section may not say

- **No cross-runtime ordering.** The Osaurus JANG cell stands alone; no `peak_mb` or accuracy
  ordering crosses a runtime boundary (design §2.3 rule 2; §5.5).
- **No capability claim from the two floor-shaped MMLU levels** (§2.1, §2.2) and none from the
  `jang2l` column at all beyond IFEval.
- **No rate computed from an unresolvable difference.** No quality-per-speed, quality-per-memory
  or quality-per-disk slope is published here: the pairs with a resolvable accuracy difference
  are the dominated ones, and the design's Plan 02-04 is where the exchange rates are read.
- **No monotonic frontier statement for `oq4`.** Its speed coordinate is a quotation with a
  +76.0% drift marker; its frontier position before domination cannot be read as a property of
  `oq4` alone.

---

## 6. Artifact and provenance index

**Campaign artifacts**

- **Runner:** [`scripts/run_accuracy_moe.sh`](file:///Users/jrazz/Dev/active/OhYesMLX/scripts/run_accuracy_moe.sh)
  (5 vMLX cells, the 2-cell MMLU replicate at `--mmlu-limit 20`, the Study 2C Osaurus cell with
  residency pinned to 900 s and the `cmp`-verified restore).
- **Cell evaluator:** [`scripts/probe_accuracy_cell.py`](file:///Users/jrazz/Dev/active/OhYesMLX/scripts/probe_accuracy_cell.py)
  (canary gate, patched-scheduler hash check, `lm-eval[api,ifeval]==0.4.13` under `uv --isolated`,
  `max_gen_toks=1024`, per-task limits and few-shot counts, per-cell `manifest.json`).
- **Analysis engine:** [`scripts/analyze_accuracy_moe.py`](file:///Users/jrazz/Dev/active/OhYesMLX/scripts/analyze_accuracy_moe.py)
  (paired McNemar intervals, cross-runtime agreement, replicate stability; writes
  `results/accuracy-moe/analysis_summary.json`).
- **Execution log:** `results/accuracy-moe/runner.log` (152 lines, final status
  `FAILURES RECORDED`).
- **8 cell manifests:** `results/accuracy-moe/column-vmlx/{stock4bit,jang2l,oq4,oq4e,optiq}__vmlx/manifest.json`,
  `results/accuracy-moe/replicate/{jang2l,stock4bit}__vmlx/manifest.json`,
  `results/accuracy-moe/study-2c/jang2l__osaurus/manifest.json`.
- **Raw evaluation record:** 20 `lm_eval_output.txt` task logs and the `samples_*.jsonl` files
  under each cell directory — 9,340 scored items plus the failed attempts' retry logs, kept.

**Evidence locations for the specific claims**

| claim | where it is evidenced |
|---|---|
| run windows, port releases, patch hashes, restore line | `results/accuracy-moe/runner.log` (`:7`, `:25`, `:42`, `:59`, `:76`, `:93`, `:95`, `:101`, `:111`, `:122`, `:144`, `:146`, `:151`) |
| per-cell scores, statuses, returncodes, cold loads, canaries | each cell's `manifest.json` |
| the four 502 halts, item numbers, refused token counts | `column-vmlx/stock4bit__vmlx/runtime.log:5362,5366,5370`; `column-vmlx/jang2l__vmlx/runtime.log:407,411,415,634,640,646`; `replicate/jang2l__vmlx/runtime.log:407,411,415`; the matching `lm_eval_output.txt` per task |
| `reasoning_only_no_content` message text, retry counts, final HTTPError | `*/lm_eval_output.txt` (three warnings and the traceback per halted task) |
| response-form counts and the stated-answer diagnostic (§2.1, §2.2) | each cell's `mmlu_generative/**/samples_*.jsonl`, rule quoted in §2.2 |
| 2C first disagreement | `study-2c/jang2l__osaurus/ifeval/**/samples_*.jsonl` doc 1, and the vMLX counterpart |
| every Δ, CI, K and agreement rate | `results/accuracy-moe/analysis_summary.json`, re-derived from the sample rows for this write-up |

**Recomputation performed for this document.** Before publication, each score was recomputed as
$k/n$ from the sample rows and compared with both the manifest and `analysis_summary.json`
(exact agreement on all 16 completed cell-task scores); every pairwise $b$, $c$, $K$, Δ and CI
was recomputed and matched the summary exactly; both replicate/agreement rates were recomputed
from response strings; and the exact two-sided binomial McNemar p-values reported in §3 were
computed for this document (they are not fields of the summary). The response-form counts and
the stated-answer diagnostic were computed for this document under the rules stated where they
appear. **Not verified and not claimed:** per-(cell, task) item-identity hashes for MMLU (the
field is empty in every manifest — §3 rule 3), truncation rates and parse-failure rates (§3.5 of
the design asks for them per cell; the manifests do not carry them), and any number this
document did not quote from Track 1's published tables.
