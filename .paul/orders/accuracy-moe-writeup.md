GOAL: Author the official Plan 02-03 MoE Accuracy Study research report at docs/research/2026-09-19-accuracy-moe.md.

FILES TO CREATE:
- docs/research/2026-09-19-accuracy-moe.md

DATA SOURCES:
- results/accuracy-moe/runner.log
- results/accuracy-moe/analysis_summary.json
- Individual cell manifests in results/accuracy-moe/column-vmlx/, results/accuracy-moe/study-2c/, results/accuracy-moe/replicate/
- Reference style and structure: docs/research/2026-09-18-accuracy-dense.md
- Study design: docs/research/2026-09-17-v2-track2-accuracy-study-design.md (§2.2, §3.3, §6.4)
- Track 1 synthesis: docs/research/2026-09-17-jang-cross-runtime.md

SPECIFICATION & STRUCTURE:
Follow the exact style, headings, and statistical rigor of docs/research/2026-09-18-accuracy-dense.md:

1. Title & Metadata:
   - "Plan 02-03 — the MoE accuracy study: LFM2.5-8B-A1B in vMLX and Osaurus"
   - Date: 2026-09-19. Measured. Duration: 2026-09-18 17:27:12 to 2026-09-19 09:46:47 local (16h 19m 35s) across 8 cells.
   - Pinned budget dial applied per §3.3 (MMLU limit=20 items/subject = 1,140 items; GSM8K 250; IFEval 250).

2. Section 1: Executive Summary & Headline Findings
   - 1.1 What ran: Summary table of the 8 cell runs, durations, item evaluations, status.
     - Port safety: all ports confirmed released (8000, 1337).
     - Osaurus byte-exact config restore confirmed by cmp -s.
     - vMLX scheduler patch sha256 confirmed (9710d2b9...).
   - 1.2 Headline Findings:
     - Finding 1: 100.000% Within-Runtime Replicate Determinism (stock4bit__vmlx primary 35.53% vs replicate 35.53%, delta=0.00pp, 0 discordant items across 1,140 items).
     - Finding 2: Instruction Following Preserved on 2.37-bit JANG_2L (IFEval: jang2l__vmlx 56.8% vs stock4bit__vmlx 52.0%, paired delta=+4.80pp; jang2l__osaurus 60.4%; confirms Outcome P3 quality collapse did not occur).
     - Finding 3: Q3 Answered — OptiQ Strictly Pareto-Dominated on MoE (MMLU: optiq 28.25% trails stock 35.53% by -7.28pp [p < 10^-5] and trails oq4e 36.23% by -7.98pp [p < 10^-6]; GSM8K: optiq 37.6% trails oq4e 41.6% by -4.0pp; carries 44% more disk bytes for negative reasoning quality).
     - Finding 4: Outlier Protection Vital on MoE (Q4 Answered: oq4e 36.23% beats oq4 21.93% on MMLU by +14.30pp [p < 10^-10]).
     - Finding 5: The vMLX Reasoning-Truncation Trap (HTTP 502 reasoning_only_no_content): LFM2 does not expose instruct mode (supports_instruct_mode=False), so enable_thinking cannot be turned off. When thinking traces hit the 1024 token limit before </think>, vMLX returns HTTP 502, causing task halts on stock4bit (GSM8K item 176) and jang2l (MMLU item 80).
     - Finding 6: Study 2C: Osaurus JANG_2L Evaluation & Prompt Extraction Confound (jang2l__osaurus completed 100% PASS: GSM8K 33.2%, IFEval 60.4%; MMLU 3.77% caused by prose preamble "The correct answer is C..." confounding get_response filter).

3. Section 2: Complete Scored Matrix
   - 2.1 Column A: Runtime vmlx (Format Axis Held Constant). Formats: stock4bit, jang2l, oq4, oq4e, optiq.
   - 2.2 Study 2C: Runtime osaurus (jang2l__osaurus).

4. Section 3: Paired Difference Intervals & Hypothesis Testing
   - Table of paired comparisons with delta_pp, 95% CI, discordant counts, and p-values.

5. Section 4: Replicate Determinism & Stability
   - Analysis of replicate stability.

6. Section 5: The Pareto Frontier on MoE & Answers to Q1, Q3, Q4
   - Direct answers to design questions.

VERIFICATION:
- Verify report against results/accuracy-moe/analysis_summary.json.
- Run `pytest -q` (495 passed).
- Touch nothing else.
