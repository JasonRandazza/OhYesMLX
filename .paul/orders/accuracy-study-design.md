GOAL: Write docs/research/2026-09-17-v2-track2-accuracy-study-design.md — the comprehensive study design, single-variable test matrix, evaluation harness protocol, benchmark selection, and Pareto analysis framework for v2 Track 2: Accuracy Scoring.

FILES YOU MAY EDIT:
docs/research/2026-09-17-v2-track2-accuracy-study-design.md only. Touch nothing else.

STYLE & METHOD:
- Technical rigor matching docs/research/ style (reference docs/research/2026-09-17-v2-track1-jang-study-design.md and docs/research/2026-09-17-jang-cross-runtime.md).
- Full markdown prose with structured tables, section headings, and explicit equations/definitions where needed.
- Grounded in existing repo code and observed data (ohyesmlx/runtimes.py, ohyesmlx/measure.py, scripts/gridspec.sh, scripts/gridspec-moe.sh).
- Strictly adhere to the defining rule: "Vary one thing at a time."

CONTEXT & EVIDENCE:
1. The Core Research Questions:
   - In v1 and v2 Track 1, we established the speed and memory hierarchy of quantization formats:
     * Dense Qwen3.5-4B: JANG_4S (+14–17% vMLX, +9–10% Osaurus) > stock4bit > oq4 > oq4e > optiq.
     * MoE LFM2.5-8B-A1B: stock4bit ties JANG_2L in vMLX and beats it in Osaurus; but JANG_2L provides 36% smaller on-disk size (3.06 GB vs 4.78 GB), 16–31% lower peak memory, and +54% prompt prefill throughput in vMLX.
     * OptiQ in v1 was the slowest and largest format across all columns that carried it (4.04 GB vs 3.06 GB on dense).
   - The Crucial Unanswered Question: What does this speed and density actually cost in accuracy?
     * Vendor Claim Check: JANG claims its importance-quantization preserves reasoning fidelity and specifically claims JANG_2L (2.37 bits average) achieves parity with or beats 4-bit MMLU. Is this true, or does 2-bit MoE suffer catastrophic quality collapse?
     * Quality Trade for JANG_4S: Does JANG_4S's 14–17% decode speedup come with subtle task degradation vs uniform 4-bit?
     * Pareto Value of OptiQ: Did OptiQ's substantial latency and footprint penalty buy superior accuracy, or is it strictly Pareto-dominated?
     * Mixed Precision (oQ4 vs oQ4e): Does outlier-channel protection in oQ4/oQ4e improve task accuracy over stock 4-bit?

2. Evaluation Tooling & Zero-Dependency Invariant:
   - Tool: lm-evaluation-harness (EleutherAI).
   - Execution isolation: Ran via `uv run --isolated --with lm-eval lm_eval` to maintain zero new dependencies in the OhYesMLX core package.
   - Endpoint model: `--model local-chat-completions` targeting local OpenAI-compatible endpoints (`http://localhost:<port>/v1`).
   - Reasoning token handling: Utilizing `think_end_token="</think>"` to strip reasoning traces for models that emit `<think>` blocks.

3. Benchmark Selection & Execution Budget:
   - Selected tasks:
     * MMLU (knowledge, multi-subject multi-choice reasoning — direct test of vendor claim).
     * GSM8K (multi-step chain-of-thought mathematical reasoning).
     * ARC-Challenge (reasoning under adversarial distraction).
     * IFEval (instruction-following strict adherence).
   - Execution Budget:
     * Full MMLU is 14,042 questions; running 14k queries across 10 formats on local Mac runtimes would require days of compute and induce severe thermal throttling.
     * Pinned sample budget: `--limit 250` or `--limit 500` per task, with fixed seeds and identical sample sets across all models.
     * Pinned generation parameters: Temperature 0, fixed seed, fixed max generation tokens.

4. Single-Variable Test Matrix:
   - All 10 artifacts are 100% verified on disk in ~/.cache/huggingface/hub/ (zero downloads needed).
   - Study 2A: Dense Format Axis Accuracy (Qwen3.5-4B across stock4bit, oq4, oq4e, optiq, jang4s) served on a consistent runtime (vMLX / Osaurus).
   - Study 2B: MoE Format Axis Accuracy (LFM2.5-8B-A1B across stock4bit, oq4, oq4e, optiq, jang2l) served on a consistent runtime.
   - Study 2C: Cross-Runtime / Loader Accuracy Sanity Check (evaluating identical JANG weights on vMLX vs Osaurus to verify that custom loader unpacking kernels produce bit-for-bit identical or numerically consistent accuracy).

REQUIRED SECTIONS IN DOC:
1. Executive Summary & Problem Statement:
   - Why accuracy scoring is needed to complete the evaluation trilogy (Speed, Memory, Accuracy).
   - The vendor claim to be tested (JANG 2-bit vs 4-bit MMLU).
   - The single-variable invariant for evaluation.
2. The Test Matrix Formulation:
   - Study 2A: Dense Format Axis (Qwen3.5-4B, 5 formats).
   - Study 2B: MoE Format Axis (LFM2.5-8B-A1B, 5 formats).
   - Study 2C: Cross-Runtime Numerical Consistency Check (vMLX vs Osaurus).
   - The 10 on-disk verified artifacts (table with snapshot hashes, sizes, and declared bits).
3. Benchmark Suite & Protocol:
   - Task selection rationale (MMLU, GSM8K, ARC-Challenge, IFEval).
   - Pinned sample budget and thermal protection (subsampling with fixed seeds, cooldowns between tasks).
   - Prompt templates and chat completion interfacing.
   - Handling reasoning models and `<think>` token filtering.
4. Confound Ledger & Experimental Controls:
   - Pinned parameters (temperature 0, fixed seed, fixed max tokens).
   - Preventing runtime drift, host cache interference (Osaurus settings baseline).
   - Tool isolation via `uv run --isolated --with lm-eval`.
5. Pre-registered Decision Rules & Pareto Frontier Framework:
   - Definition of Accuracy Parity Band (e.g. ±1.5% accuracy points).
   - Pre-registered outcomes:
     * P1: Quality Parity (Speed/memory gain at zero accuracy cost).
     * P2: Measured Degradation (Quantifying the exact loss per unit of speedup or memory reduction).
     * P3: Quality Collapse (Format fails reasoning floor).
   - 2D Pareto formulation: Throughput (tok/s) vs Accuracy (%), and Memory (GB) vs Accuracy (%).
6. Execution Roadmap for Phase 2:
   - Plan 02-01: Harness Spike & Local Endpoint Validation.
   - Plan 02-02: Dense Accuracy Study (Qwen3.5-4B).
   - Plan 02-03: MoE Accuracy Study (LFM2.5-8B-A1B).
   - Plan 02-04: Accuracy vs Throughput Pareto Tradeoff Synthesis.

REPORT:
Return the path to the new document, an outline of its contents, and verification that tests still pass.
