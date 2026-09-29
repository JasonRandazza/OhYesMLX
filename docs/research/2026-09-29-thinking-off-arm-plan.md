# Thinking-Off MMLU Arm Study Plan & Pre-Flight Design

**Date:** 2026-09-29  
**Status:** REVISED 2026-09-29 (see below); ready for execution on Jason's go  

> **Revision, same day, after review and Jason's decisions.** This draft (written by an Antigravity
> worker, reviewed by the coordinator) proposed 8 cells. It is superseded as the run definition by
> `scripts/run_accuracy_thinkoff.sh`, whose header is now the executable specification: an
> **Osaurus-only 2×2** on `LFM2.5-8B-A1B` (`jang2l` and `stock4bit`, each thinking off and on, all on
> one Osaurus build, MMLU 1,140 items) with every cell re-scored offline by
> `scripts/rescore_moe_mmlu.py --cell-dir`, plus a **one-request vMLX refusal probe** in place of seven
> aborted vMLX cells. Corrections to the draft below: (1) it required "identical runtime versions" but
> cited Osaurus 0.25.6 from the 09-19 thinking-on cells while 0.25.14 is installed, so a thinking-off
> cell alone would vary the build too; the 2×2 runs both arms on one build and does not compare with the
> 09-19 cell. (2) §2.5 Option C says thinking-on dense has "zero HTTP 400/502 errors", but Decision 102
> records that `enable_thinking=false` is what eliminated the 502 trap on dense, so thinking-on dense
> is where it is expected; Option C is held as a follow-on with a 502 plan. (3) Only a JANG_2L cell
> ran on Osaurus in the draft, which cannot make the `jang2l` vs `stock4bit` pair; the 2×2 adds
> `stock4bit`. Sections 3 to 5 and 7 are kept as the record of the draft.  
**Execution Script:** [`scripts/run_accuracy_thinkoff.sh`](file:///Users/jrazz/Dev/active/OhYesMLX/scripts/run_accuracy_thinkoff.sh)  
**Output Target:** `results/accuracy-thinkoff/`  
**Governing Documents & Foundations:**
- `.paul/ROADMAP.md:240-246` (Candidate 3: Thinking-Off MMLU Arm)
- `docs/research/2026-09-19-accuracy-pareto.md:838-840` (The Thinking-Off Arm Bullet)
- `docs/research/2026-09-17-v2-track2-accuracy-study-design.md:1264-1267` (§8.2 Open Question 2)
- `.paul/STATE.md:101-105` (Decisions 102–105)
- `docs/research/2026-09-18-accuracy-spike-report.md:410-445` (Switch Mechanics & Pinned Defaults)
- `docs/research/2026-09-19-accuracy-moe.md:149-170` (Finding 5: The Reasoning Truncation Trap)

---

## 1. Executive Summary & Problem Formulation

### 1.1 Context and Scientific Objective

Track 2 established the accuracy coordinates of the Pareto frontier across `Qwen3.5-4B` (dense) and `LFM2.5-8B-A1B` (MoE) on Apple Silicon (`docs/research/2026-09-19-accuracy-pareto.md:10-20`). However, an asymmetry exists across the published campaigns:

1. **Plan 02-02 (Dense Accuracy Study):** `Qwen3.5-4B` was evaluated with reasoning **suppressed** via `--gen_kwargs enable_thinking=false` across all 11 cell runs (`scripts/run_accuracy_dense.sh:112`; `scripts/probe_accuracy_cell.py:197,279-280`; `results/accuracy-dense/column-vmlx/stock4bit__vmlx/mmlu_generative/lm_eval_output.txt:1`). Dense MMLU has a thinking-off coordinate (e.g. `stock4bit__vmlx` 67.89%, `jang4s__vmlx` 68.42%; `docs/research/2026-09-18-accuracy-dense.md:70-76`), but **no thinking-on MMLU baseline** (`docs/research/2026-09-18-accuracy-spike-report.md:433`).
2. **Plan 02-03 (MoE Accuracy Study):** `LFM2.5-8B-A1B` was evaluated with reasoning **live** (`--no-disable-thinking`, gen_kwargs `until=<|im_end|>`; `scripts/run_accuracy_moe.sh:113`; `results/accuracy-moe/column-vmlx/stock4bit__vmlx/mmlu_generative/lm_eval_output.txt:1`) because vMLX rejected `enable_thinking=false` with HTTP 400 (`supports_instruct_mode=False`; Decision 105 in `.paul/STATE.md:104`; `docs/research/2026-09-19-accuracy-moe.md:30-32`). Under thinking-on conditions:
   - `stock4bit__vmlx` scored **35.53%** (405/1,140) with 100.000% replicate determinism (`docs/research/2026-09-19-accuracy-moe.md:42,48,82-94`).
   - `jang2l__vmlx` **halted at item 80/1,140** in both primary and replicate visits due to vMLX HTTP 502 `reasoning_only_no_content` (`docs/research/2026-09-19-accuracy-moe.md:43,47,156-170`).
   - Consequently, **Q1 (Vendor Parity Claim for JANG_2L vs 4-bit MMLU) could not be answered on MMLU** (`docs/research/2026-09-19-accuracy-moe.md:114-117`; `docs/research/2026-09-19-accuracy-pareto.md:838-840`).

The **Thinking-Off MMLU Arm** (Candidate 3 in `.paul/ROADMAP.md:240-246`) was defined to address two goals:
- **Goal 1:** Isolate the exact accuracy contribution of the `<think>` reasoning trace vs raw parametric knowledge retrieval on MMLU (`.paul/ROADMAP.md:243`).
- **Goal 2:** Resolve the vMLX reasoning truncation trap (HTTP 502 `reasoning_only_no_content`) to complete the decisive pair (`jang2l__vmlx` vs `stock4bit__vmlx`) and make Q1 answerable (`docs/research/2026-09-19-accuracy-pareto.md:838-840`).

---

## 2. The Single-Variable Rule & The Runtime Hazard

### 2.1 The Single-Variable Invariant

The project's foundational rule mandates: **Vary one thing at a time** (`AGENTS.md:17-25`; `docs/research/2026-09-17-v2-track2-accuracy-study-design.md:121-136`). For this ablation arm, the single variable must be **the reasoning state (thinking on vs thinking off)**.
All other conditions must remain strictly pinned to match the comparator campaign:
- Identical quantization artifact bytes (`scripts/run_accuracy_moe.sh:16-22`)
- Identical runtime versions (`vMLX 1.6.59`, `Osaurus 0.25.6`; `docs/research/2026-09-19-accuracy-moe.md:40-50`)
- Identical prompt structure and 5-shot multiturn framing (`--fewshot_as_multiturn`, `--apply_chat_template`; `scripts/probe_accuracy_cell.py:272-273`)
- Identical 1,140 MMLU evaluation items (`--mmlu-limit 20`, 57 subjects × 20 items; `scripts/probe_accuracy_cell.py:50,183-185`)
- Identical temperature 0.0 and cache state off (`cache_state="off"`; `scripts/probe_accuracy_cell.py:206,238`)

### 2.2 Upstream Evidence of HTTP 400 (`supports_instruct_mode=False`)

In vMLX 1.6.59, `LFM2.5-8B-A1B` is registered as a pure reasoning architecture:
1. `/Applications/vMLX.app/Contents/Resources/vmlx-engine-source/vmlx_engine/model_configs.py:1027` explicitly declares:
   ```python
   supports_instruct_mode=False,
   ```
2. When a client request passes `"enable_thinking": false` in the JSON request body (which `lm-eval` passes via `--gen_kwargs enable_thinking=false`; `scripts/probe_accuracy_cell.py:280`), `/Applications/vMLX.app/Contents/Resources/vmlx-engine-source/vmlx_engine/server.py:4850-4852` triggers:
   ```python
   if request_value is not None:
       if request_value is False:
           _reject_unsupported_instruct_mode("the request")
       return request_value
   ```
3. `/Applications/vMLX.app/Contents/Resources/vmlx-engine-source/vmlx_engine/server.py:4832-4842` executes:
   ```python
   def _reject_unsupported_instruct_mode(source: str) -> None:
       if _mc is None or getattr(_mc, "supports_instruct_mode", None) is not False:
           return
       raise HTTPException(
           status_code=400,
           detail=(
               f"{_family} does not expose a native thinking-off/instruct mode; "
               f"{source} requested enable_thinking=false. Use Auto/On with one "
               "of the advertised reasoning_efforts instead."
           ),
       )
   ```
4. As confirmed during Plan 02-03 (Decision 105 in `.paul/STATE.md:104`; `docs/research/2026-09-19-accuracy-moe.md:30-32`), vMLX immediately aborts with HTTP 400 Client Error on item 1.

### 2.3 Prohibition of System-Prompt Substitution Tricks

Candidate 3 in `.paul/ROADMAP.md:242` noted: `(dense via API enable_thinking=false, MoE via prompt template / system prompt)`.
However, the standing delegation rule and study constraints dictate:
> *"if a runtime cannot turn thinking off the same way, say so and exclude it rather than substitute a system-prompt trick."*

**Methodological rationale:**
1. Injecting a system prompt instruction (such as `"Do not reason. Output only the answer letter directly."` or using `/no_think` template overrides) alters the token sequence, increases prompt length, and alters attention weights across all 5 few-shot demonstration turns (`docs/research/2026-09-17-v2-track2-accuracy-study-design.md:129-132`).
2. A system prompt modification introduces a second uncontrolled variable: prompt sensitivity and prompt compliance under 2.37-bit quantization (`JANG_2L`), directly violating the single-variable rule (`AGENTS.md:17-25`).
3. Therefore, **system-prompt substitution tricks are rejected**. If vMLX rejects standard API thinking suppression on LFM2, that refusal must be reported as a runtime capability boundary, not circumvented with ad-hoc prompt hacking.

### 2.4 Structural Resolution of HTTP 502 (`reasoning_only_no_content`)

In Plan 02-03, `jang2l__vmlx` halted on item 80/1,140 because vMLX returned HTTP 502 (`docs/research/2026-09-19-accuracy-moe.md:156-170`).
Upstream source analysis proves why this occurs:
- `/Applications/vMLX.app/Contents/Resources/vmlx-engine-source/vmlx_engine/server.py:22769` checks:
  ```python
  reasoning_only_no_content=bool(reasoning_text and not content_text),
  ```
- If the completion contains `reasoning_text` but `content_text` is empty (e.g. model stops or exhausts tokens before closing `</think>`), `/Applications/vMLX.app/Contents/Resources/vmlx-engine-source/vmlx_engine/server.py:21304` emits:
  ```json
  {"type":"invalid_response_error","code":"reasoning_only_no_content","message":"The model produced reasoning_content but no visible answer and no tool call. This turn is incomplete; retry with a larger output budget or adjust the prompt/reasoning settings."}
  ```
- **When thinking is disabled:** `reasoning_text` is null/empty. Therefore, `bool(reasoning_text and not content_text)` evaluates to `False`. The HTTP 502 trap is **structurally eliminated** when thinking is turned off (`docs/research/2026-09-18-accuracy-spike-report.md:44,410-417`).

### 2.5 Strategic Handling Architecture for Tonight's Arm

To honor all constraints, the study plan defines three formal evaluation postures for Jason's selection:

| Option | Posture | How vMLX HTTP 400 is Handled | Methodological Merit |
|---|---|---|---|
| **Option A (Pre-Registered Refusal Probe)** *(Recommended)* | Execute [`scripts/run_accuracy_thinkoff.sh`](file:///Users/jrazz/Dev/active/OhYesMLX/scripts/run_accuracy_thinkoff.sh) with standard `--gen_kwargs enable_thinking=false` | Let vMLX fail item 1 with HTTP 400 on LFM2; capture and record `REFUSED_UNSUPPORTED_INSTRUCT` in manifest. Complete Osaurus cell (`jang2l__osaurus`). | 100% compliant with single-variable rule. Enters runtime capability refusal into formal record (`AGENTS.md:275-290`). |
| **Option B (Exclusion of vMLX MoE)** | Exclude vMLX from MoE thinking-off; run Osaurus MoE alone (`jang2l__osaurus`) | vMLX declared out-of-scope for MoE thinking-off due to upstream `supports_instruct_mode=False` (`model_configs.py:1027`). | Avoids spending machine cycles on known 400 aborts. Directly isolates Osaurus behavior. |
| **Option C (Dense Thinking-ON Counterpart)** | Run `Qwen3.5-4B` with thinking **ON** (`--no-disable-thinking`) on MMLU | Qwen3.5 natively supports both instruct and thinking modes (`model_configs.py:199`). | Delivers Goal 1 (isolating accuracy delta of reasoning trace) with zero HTTP 400/502 errors, pairing against Plan 02-02's thinking-off data. |

---

## 3. Test Matrix & Cell Specifications

### 3.1 Primary Arm: MoE Thinking-Off MMLU (`LFM2.5-8B-A1B`)

Evaluates the 8 cells of Plan 02-03 with thinking suppressed (`enable_thinking=false`) on MMLU 5-shot multiturn (1,140 items).

| # | Cell Label | Model | Format | Serving Runtime | Artifact Snapshot Path | gen_kwargs | Exact Command |
|---|---|---|---|---|---|---|---|
| 1 | `stock4bit__vmlx` | LFM2.5-8B-A1B | `stock4bit` | vMLX 1.6.59 | `models--mlx-community--LFM2.5-8B-A1B-MLX-4bit/.../146590a4...` | `{"enable_thinking": False}` | `$PY scripts/probe_accuracy_cell.py --runtime vmlx --cell stock4bit__vmlx --artifact "$S4" --out results/accuracy-thinkoff/column-vmlx/stock4bit__vmlx --task mmlu_generative --mmlu-limit 20` |
| 2 | `jang2l__vmlx` | LFM2.5-8B-A1B | `jang2l` | vMLX 1.6.59 | `models--JANGQ-AI--LFM2.5-8B-A1B-JANG_2L/.../5fb82773...` | `{"enable_thinking": False}` | `$PY scripts/probe_accuracy_cell.py --runtime vmlx --cell jang2l__vmlx --artifact "$JG" --out results/accuracy-thinkoff/column-vmlx/jang2l__vmlx --task mmlu_generative --mmlu-limit 20` |
| 3 | `oq4__vmlx` | LFM2.5-8B-A1B | `oq4` | vMLX 1.6.59 | `models--stamsam--LFM2.5-8B-A1B-oQ4/.../acb4fd20...` | `{"enable_thinking": False}` | `$PY scripts/probe_accuracy_cell.py --runtime vmlx --cell oq4__vmlx --artifact "$Q4" --out results/accuracy-thinkoff/column-vmlx/oq4__vmlx --task mmlu_generative --mmlu-limit 20` |
| 4 | `oq4e__vmlx` | LFM2.5-8B-A1B | `oq4e` | vMLX 1.6.59 | `models--brainworkup--LFM2.5-8B-A1B-oQ4e/.../88977e47...` | `{"enable_thinking": False}` | `$PY scripts/probe_accuracy_cell.py --runtime vmlx --cell oq4e__vmlx --artifact "$QE" --out results/accuracy-thinkoff/column-vmlx/oq4e__vmlx --task mmlu_generative --mmlu-limit 20` |
| 5 | `optiq__vmlx` | LFM2.5-8B-A1B | `optiq` | vMLX 1.6.59 | `models--mlx-community--LFM2.5-8B-A1B-OptiQ-4bit/.../5a5c5958...` | `{"enable_thinking": False}` | `$PY scripts/probe_accuracy_cell.py --runtime vmlx --cell optiq__vmlx --artifact "$OQ" --out results/accuracy-thinkoff/column-vmlx/optiq__vmlx --task mmlu_generative --mmlu-limit 20` |
| 6 | `jang2l__vmlx_repl` | LFM2.5-8B-A1B | `jang2l` | vMLX 1.6.59 | `models--JANGQ-AI--LFM2.5-8B-A1B-JANG_2L/.../5fb82773...` | `{"enable_thinking": False}` | `$PY scripts/probe_accuracy_cell.py --runtime vmlx --cell jang2l__vmlx_repl --artifact "$JG" --out results/accuracy-thinkoff/replicate/jang2l__vmlx --task mmlu_generative --mmlu-limit 20 --replicate` |
| 7 | `stock4bit__vmlx_repl` | LFM2.5-8B-A1B | `stock4bit` | vMLX 1.6.59 | `models--mlx-community--LFM2.5-8B-A1B-MLX-4bit/.../146590a4...` | `{"enable_thinking": False}` | `$PY scripts/probe_accuracy_cell.py --runtime vmlx --cell stock4bit__vmlx_repl --artifact "$S4" --out results/accuracy-thinkoff/replicate/stock4bit__vmlx --task mmlu_generative --mmlu-limit 20 --replicate` |
| 8 | `jang2l__osaurus` | LFM2.5-8B-A1B | `jang2l` | Osaurus 0.25.6 | `models--JANGQ-AI--LFM2.5-8B-A1B-JANG_2L/.../5fb82773...` | `{"enable_thinking": False}` | `$PY scripts/probe_accuracy_cell.py --runtime osaurus --cell jang2l__osaurus --artifact "$JG" --out results/accuracy-thinkoff/study-2c/jang2l__osaurus --task mmlu_generative --mmlu-limit 20` |

*Notes on Matrix Parameters:*
- `cache_state`: `off` (`--disable-prefix-cache --disable-block-disk-cache`; `scripts/probe_accuracy_cell.py:206,238`).
- `lm-eval` parameters: `--apply_chat_template`, `--fewshot_as_multiturn`, `max_gen_toks=1024`, `max_length=4096`, `temperature=0.0` (`scripts/probe_accuracy_cell.py:258-275`).
- Osaurus host idle residency: pinned to 900 s before cell 8 and verified restored byte-exact (`cmp -s`; `scripts/run_accuracy_thinkoff.sh:80-117`).

### 3.2 gen_kwargs Specification per Runtime

In `lm-evaluation-harness`, `LocalChatCompletion._create_payload` splats `gen_kwargs` directly into the top-level JSON request body sent to `/v1/chat/completions` (`docs/research/2026-09-18-accuracy-spike-report.md:398-408`):
- **vMLX 1.6.59:**
  - `gen_kwargs`: `{"enable_thinking": False}`
  - Request DTO: maps to `ChatCompletionRequest.enable_thinking: bool | None = None` (`vmlx_engine/api/models.py:300`; `docs/runtimes/vmlx.md:573`).
  - Expected behavior: Rejection with HTTP 400 on LFM2 (`server.py:4832-4842`); clean acceptance on Qwen3.5 (`server.py:4852`).
- **Osaurus 0.25.6:**
  - `gen_kwargs`: `{"enable_thinking": False}`
  - Request DTO: maps to Codable key `enable_thinking` (`docs/runtimes/osaurus.md:496`).
  - Expected behavior: Accepts request; disables internal reasoning generator.

---

## 4. Pre-Registered Readings in Design Doc Vocabulary

All evaluations use the exact statistical decision vocabulary established in `docs/research/2026-09-17-v2-track2-accuracy-study-design.md:415-445, 960-1015`.

### 4.1 Statistical Intervals & Comparison Rules

Because each cell evaluates the **identical 1,140 MMLU items** with greedy decoding (`temperature: 0.0`), all comparisons are **paired differences** (McNemar test for 0/1 accuracy) (`design §3.3:1085-1100`; `docs/research/2026-09-18-accuracy-dense.md:94-100`):

$$\Delta = \frac{b - c}{n}, \quad \text{SE}(\Delta) = \frac{\sqrt{b + c}}{n}, \quad 95\%\text{ CI} = \Delta \pm 1.96 \cdot \text{SE}(\Delta)$$

where $b$ is the count of items correct in format A and incorrect in format B, and $c$ is the reverse.

- **Parity Band:** $\pm 1.5\text{ pp}$ (`design §2.6:420`; `design §5.1:965`).
- **Replicate Threshold:** $5.0\%$ maximum drift between primary and replicate visits (`design §2.6:422`).
- **Chance Floor:** $25.0\%$ for 4-option generative MMLU (`design §5.3:990`).

### 4.2 Pre-Registered Outcome Readings

1. **Outcome P1 (Quality Parity under Thinking-Off):**
   - Applies to Q1 decisive pair: `jang2l__vmlx` vs `stock4bit__vmlx`.
   - Condition: The 95% confidence interval of $\Delta$ lies **strictly inside $[-1.5\text{ pp}, +1.5\text{ pp}]$**.
   - Meaning: 2.37-bit quantization achieves exact task accuracy parity with uniform 4-bit when reasoning traces are suppressed.
2. **Outcome P2 (Definite Difference):**
   - Condition: The 95% confidence interval of $\Delta$ excludes $0.0\text{ pp}$ and $|\Delta| > 1.5\text{ pp}$.
   - Meaning: A statistically significant accuracy separation exists between the formats under non-reasoning extraction.
3. **Outcome P3 (Reasoning Collapse):**
   - Condition: Absolute MMLU score lands $\le 25.0\%$ (below chance floor).
   - Meaning: Severe quantization damage prevents basic factual retrieval (`design §5.3:995`).
4. **Outcome R-Refusal (Runtime Capability Boundary):**
   - Condition: Cell terminates with HTTP 400 `supports_instruct_mode=False`.
   - Meaning: vMLX rejects thinking suppression by design contract. Recorded as an architectural refusal (`REFUSED_UNSUPPORTED_INSTRUCT`), not an accuracy score.
5. **Reasoning Value Delta ($\Delta_{\text{think}}$):**
   - For cells with valid thinking-on baselines from Plan 02-03 (e.g. `stock4bit__vmlx` = 35.53%):
     $$\Delta_{\text{think}} = \text{Score}_{\text{think-on}} - \text{Score}_{\text{think-off}}$$
   - Directly measures the accuracy premium purchased by the reasoning trace.

---

## 5. Time Budget Derived from Empirical Observations

### 5.1 Empirical Rate Analysis

Existing run records provide exact empirical rates:
1. **Thinking-ON MoE MMLU (Plan 02-03, 1,140 items):**
   - `stock4bit__vmlx` primary: `duration_s: 6414.44` (**1h 46m 54s**, **5.63 s/item**; `results/accuracy-moe/column-vmlx/stock4bit__vmlx/manifest.json`).
   - `stock4bit__vmlx` replicate: `duration_s: 5996.38` (**1h 39m 56s**, **5.26 s/item**; `results/accuracy-moe/replicate/stock4bit__vmlx/manifest.json`).
   - `jang2l__osaurus`: `duration_s: 5432.77` (**1h 30m 33s**, **4.77 s/item**; `results/accuracy-moe/study-2c/jang2l__osaurus/manifest.json`).
   - *Cause of high duration:* LFM2 generated 150–400 tokens of `<think>` reasoning per item before emitting the final answer.
2. **Thinking-OFF Dense MMLU (Plan 02-02, 2,280 items):**
   - `stock4bit__vmlx`: `duration_s: 3420.57` for 2,280 items (**1.50 s/item**; `results/accuracy-dense/column-vmlx/stock4bit__vmlx/manifest.json`).
   - `jang4s__osaurus`: `duration_s: 3751.53` for 2,280 items (**1.64 s/item**; `results/accuracy-dense/column-osaurus/jang4s__osaurus/manifest.json`).
   - *Cause of low duration:* Model emits 1–5 tokens (bare letter "A", "B", etc.), reducing decode time to <0.05 s per request.
3. **MoE Thinking-OFF Cost Derivation:**
   - MoE prefill is **1,643 tok/s** in vMLX and **831 tok/s** in Osaurus (`docs/research/2026-09-17-v2-track2-accuracy-study-design.md:1125`).
   - MMLU 5-shot prompt is ~1,200 tokens: prefill takes ~0.73 s (vMLX) and ~1.44 s (Osaurus).
   - Generative decode for bare letter (1–3 tokens) at 115 tok/s takes ~0.02 s.
   - HTTP transport overhead: ~0.15 s.
   - **Derived rate:** **0.90 to 1.10 s/item** in vMLX; **1.60 to 1.80 s/item** in Osaurus.
   - For 1,140 items: $1,140 \times 1.0\text{ s} \approx 1,140\text{ s} \approx \mathbf{19\text{ minutes per cell}}$.

### 5.2 Campaign Duration Matrix

| Block | Cells | Items / Cell | Expected Duration (if executing) | Duration if Refused (HTTP 400) |
|---|---|---|---|---|
| **Column A (vMLX MoE)** | 5 (`stock4bit`, `jang2l`, `oq4`, `oq4e`, `optiq`) | 1,140 | ~1h 35m (5 × 19m) | <2 minutes (immediate 400 on item 1) |
| **Replication Pass (vMLX)** | 2 (`jang2l_repl`, `stock4bit_repl`) | 1,140 | ~38m (2 × 19m) | <1 minute (immediate 400 on item 1) |
| **Study 2C (Osaurus MoE)** | 1 (`jang2l__osaurus`) | 1,140 | ~32m (1,140 × 1.7s) | ~32m (Osaurus accepts DTO field) |
| **Total Campaign Time** | **8 cells** | **9,120 items max** | **~2h 45m** | **~35m** |

*Budget comparison:* Well within Candidate 3's pre-registered ~3.5 to 8 hour machine-time allocation (`.paul/ROADMAP.md:246`).

---

## 6. Execution Script Specification

The runner script [`scripts/run_accuracy_thinkoff.sh`](file:///Users/jrazz/Dev/active/OhYesMLX/scripts/run_accuracy_thinkoff.sh) is modeled directly on `scripts/run_accuracy_dense.sh:1-173` and enforces:

1. **Pre-flight vMLX Scheduler Patch Hash Check:**
   - Evaluates `/Applications/vMLX.app/Contents/Resources/vmlx-engine-source/vmlx_engine/mllm_scheduler.py`.
   - Requires exact match to `9710d2b9cf07abc7380f46fef240e64febb2d06d52eb7f64236bd0e76cf686f7` (`scripts/run_accuracy_dense.sh:32,48-60`; `scripts/run_accuracy_thinkoff.sh:31,49-61`).
2. **Port Sweeping & Process Hygiene:**
   - Sweeps ports `8081`, `1337`, `8100`, `8080`, `8000` via `lsof -ti:<port>` (`scripts/run_accuracy_dense.sh:37-46`).
   - Sweeps stale Osaurus instances by full path `^/Applications/osaurus.app/Contents/MacOS/osaurus`, NEVER by bare name `osaurus` (`scripts/run_accuracy_dense.sh:41-44`; `AGENTS.md:57-61`).
3. **Osaurus Settings Pinning & Byte-Exact Restoration:**
   - Copies `~/.osaurus/config/server.json` to `.thinkoff-orig`.
   - Pins `modelIdleResidencyPolicy.seconds = 900` (`scripts/run_accuracy_dense.sh:76-83`).
   - Restores and verifies byte-exact equivalence with `cmp -s` (`scripts/run_accuracy_dense.sh:91-96`).
4. **Logging Discipline:**
   - When running live (`DRY=0`), redirects all runner execution stdout and stderr to `results/accuracy-thinkoff/runner.log` (`scripts/run_accuracy_thinkoff.sh:37-40`).
5. **DRY=1 Operational Mode:**
   - Controlled via environment variable `DRY=1 ./scripts/run_accuracy_thinkoff.sh`.
   - Does not modify Osaurus configuration, kill background pids, or start runtimes.
   - Prints every command verbatim to stdout for verification (`scripts/run_accuracy_thinkoff.sh:36,43,68,89,114`).

---

## 7. Open Questions for Jason

Before launching this arm tonight, the following strategic questions require Jason's determination:

1. **vMLX Refusal Handling Posture:**
   - If `scripts/run_accuracy_thinkoff.sh` is executed as prepared (Option A), vMLX will terminate item 1 with HTTP 400 `supports_instruct_mode=False` on all 5 column cells and both replicate cells.
   - *Question for Jason:* Do you prefer:
     - **(A)** Run Option A as-is to record the clean HTTP 400 runtime capability refusal in `results/accuracy-thinkoff/` manifests (protocol purity)?
     - **(B)** Skip Column A and the replication pass, running Osaurus Study 2C (`jang2l__osaurus`) alone tonight?
     - **(C)** Authorize an upstream vMLX patch to `model_configs.py:1027` (`supports_instruct_mode=True`), which would require rehashing and modifying the vMLX app bundle?
2. **Dense Thinking-ON Counterpart (Goal 1 Option C):**
   - Because `Qwen3.5-4B` already ran thinking-OFF in Plan 02-02, running `Qwen3.5-4B` with thinking **ON** (`--no-disable-thinking`) on MMLU (2,280 items or 1,140 items) would provide the missing ablation pair with zero HTTP 400 issues.
   - *Question for Jason:* Should a secondary target (`TARGET=dense-thinkon`) be scheduled alongside or in place of the MoE arm to isolate the reasoning-trace contribution?
3. **MMLU Item Budget Dial:**
   - The script pins `--mmlu-limit 20` (1,140 items, ~19 min/cell) matching Plan 02-03's MoE budget dial.
   - *Question for Jason:* Should this remain at 20, or be expanded to 40 (2,280 items, ~38 min/cell) given that thinking-off decode is 5× faster?
4. **Osaurus MoE MMLU Extraction Filter:**
   - Candidate 1 (`docs/research/2026-09-19-osaurus-moe-mmlu-extraction.md:17-49`) demonstrated that Osaurus on LFM2 emitted `"The correct answer is C..."`, causing `lm-eval`'s first-line regex (`^(.*?)(?=\n|$)`) to score 3.77% (offline recovered 42.19%).
   - *Question for Jason:* When running `jang2l__osaurus` under thinking-off tonight, should we run `scripts/rescore_moe_mmlu.py` automatically as an immediate post-processing step?
