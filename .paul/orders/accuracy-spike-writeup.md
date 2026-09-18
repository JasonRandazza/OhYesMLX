GOAL: Author docs/research/2026-09-18-accuracy-spike-report.md — the comprehensive research report for Plan 02-01 (Track 2 Accuracy Scoring Harness Spike & Local Endpoint Validation against vMLX on Qwen3.5-4B stock4bit).

FILES YOU MAY EDIT:
docs/research/2026-09-18-accuracy-spike-report.md only. Touch nothing else.

STYLE & METHOD:
- Follow docs/research/ style: rigorous prose, exact Markdown tables, citations to real records and artifacts.
- Reference docs/research/2026-09-17-v2-track2-accuracy-study-design.md (§6.2 10-step criteria).
- Cite results/spike-eval/spike-report.json, results/spike-eval/lm_eval_output.txt, results/spike-eval/mlx-community__Qwen3.5-4B-4bit/results_2026-09-17T22-25-38.103494.json, and the scratch probe logs.

KEY FINDINGS & MEASUREMENTS TO RECORD:
1. Environment & Tooling Pinned:
   - Isolated uv environment: uv 0.11.20 (9252ba6b5 2026-06-10 aarch64-apple-darwin).
   - lm-eval 0.4.13 (lm-eval[api,ifeval]==0.4.13).
   - Zero repository dependencies added; clean offline execution verified.
   - Serving runtime: vMLX 1.6.59 on port 8000, model mlx-community/Qwen3.5-4B-4bit.

2. Canary & The Reasoning Channel Trap (Study Design §3.5):
   - Canary ("What is 2+2? Answer with just the number.") succeeded: returned "4" in choices[0].message.content with 112 completion tokens of reasoning trace in reasoning_content in 1.49s.
   - The Reasoning Channel Trap discovered on benchmarks: On thinking models (Qwen3.5), when the generation budget (max_gen_toks) is exhausted before emitting </think>, vmlx produces reasoning_only_no_content HTTP 502 error or returns null content, scoring 0%.
   - The Switch: Discovered --gen_kwargs enable_thinking=false (or vmlx serve --default-enable-thinking false).
   - When enable_thinking=false is passed, the model generates standard step-by-step reasoning directly in content:
     * GSM8K: scores 1.0 (100% exact match on sample), latency 3.27s/item (vs 15.30s with thinking on — 4.7x faster).
     * IFEval: scores 1.0 (100% strict and loose accuracy), latency 3.87s/item.
     * ARC-Challenge chat: runs cleanly at 1.7 it/s (0.6s/item).
     * MMLU (5-shot): scores 0.60 (60% exact match on virology sample), latency ~1.9s/item.

3. Upstream Bug Isolated and Fixed in vMLX Engine:
   - In vmlx_engine/mllm_scheduler.py:3527, variable shadowing: idx = full_text.find(stop_str, search_start) overwrote the outer response loop counter idx = 0 with -1 when a stop sequence was not matched, resulting in idx += 1 resetting idx to 0 and creating an infinite loop deadlocking the step executor thread at 100% CPU on requests carrying string stop sequences.
   - Fixed by renaming variable to match_idx in both bundled-python and engine source; verified byte-identical with cmp.
   - All stop sequences (Question:, </s>, <|im_end|>) now terminate promptly.

4. Pricing fewshot_as_multiturn (Study Design §3.6):
   - Comparative evaluation on MMLU 5-shot virology (identical 5 items):
     * fewshot_as_multiturn=True: exact_match = 0.60 (3/5). Model outputs single letter ("C", "D") matching the get_response filter.
     * fewshot_as_multiturn=False: exact_match = 0.00 (0/5). Model repeats full choice string ("D. All of the above") failing exact match.
   - Setting frozen: fewshot_as_multiturn: true.

5. Task Registry & Defaults Audit:
   - mmlu_generative: version 3.0. Note: default template specifies num_fewshot: 0; must explicitly pass --num_fewshot 5 to enable few-shot demonstrations for chat letter extraction.
   - gsm8k: version 3.0, hash 1b3f08b929018851ea417880bab9c364c59f3a7d13a2c1276f1b821318759a08, default num_fewshot: 5.
   - arc_challenge_chat: version 1.0, default num_fewshot: 0.
   - ifeval: version 4.0, default num_fewshot: 0.

6. Budget & Timing Validation (Study Design §6.1):
   - Seconds per item: MMLU ~1.0-1.9s, GSM8K ~3.1-3.3s, ARC-C ~0.6s, IFEval ~3.8s.
   - Full 3,030-item cell estimate: ~1.5 to 2.0 hours per cell with enable_thinking=false (well within the §6.1 5-7h window).

7. Chat Template Digest Audit:
   - Qwen3.5-4B: 5 artifacts have byte-identical tokenizer_config.json chat templates (7,756 bytes, sha256 a4aee8afcf2e0711942cf848899be66016f8d14a889ff9ede07bca099c28f715).
   - MoE LFM2.5: Differences noted and recorded per study design.

REQUIRED SECTIONS:
1. Executive Summary & Headline Status
2. Tooling and Runtime Provenance (pins, offline verification, lifecycle)
3. Upstream Fix: The vMLX String-Stop Deadlock Bug
4. The Reasoning Channel Trap & Thinking Mode Resolution
5. Presentation Pricing: fewshot_as_multiturn Analysis
6. Task Registry & Effective Configuration Audit
7. Generation Length Distribution & Task Caps
8. Cost Model & Execution Budget Validation
9. Chat Template Consistency Audit
10. Exit Criteria & Readiness for Plan 02-02
