GOAL: Resolve the Osaurus MoE MMLU extraction filter defect by writing an offline re-scoring tool and research report recovering the true MMLU score for jang2l__osaurus.

CONTEXT:
In Plan 02-03 (MoE Accuracy Study), Osaurus completed all 1,140 MMLU items across 57 subjects in `results/accuracy-moe/study-2c/jang2l__osaurus/mmlu_generative/lfm2.5-8b-a1b-jang_2l/`.
However, lm-eval's `get_response` filter scored it at 3.77% (43 / 1140 correct) because Osaurus completions include reasoning/explanations and end with phrases like `**Answer: B. Media tour**`, `Answer: C`, or `The correct answer is **B**`. lm-eval evaluated `exact_match` against the raw completion, failing thousands of correct answers.

FILES TO TOUCH:
- scripts/rescore_moe_mmlu.py
- docs/research/2026-09-19-osaurus-moe-mmlu-extraction.md

SPECIFICATION:
1. Create `scripts/rescore_moe_mmlu.py`:
   - Standalone Python 3 script (stdlib only: json, glob, re, sys, pathlib).
   - Reads all 57 JSONL files in `results/accuracy-moe/study-2c/jang2l__osaurus/mmlu_generative/lfm2.5-8b-a1b-jang_2l/samples_*.jsonl`.
   - Reconstructs both:
     a) The baseline score under strict equality (`resp.strip() == target.strip()`), verifying agreement with lm-eval's reported 0.0377 (43/1140).
     b) The recovered score using robust extraction:
        - Search for standard answer patterns in the completion, prioritizing patterns near the end:
          1) `(?:Answer|answer):\s*(?:\*\*)?([A-D])(?:\*\*)?(?:\.|\b)`
          2) `\b([A-D])\.\s+[A-Za-z]` (e.g. `B. Media tour`)
          3) `\*\*([A-D])\*\*`
          4) `(?i:the correct answer is\s+(?:\*\*)?([A-D]))`
          5) Fallback to last isolated [A-D] character.
        - Handle empty responses gracefully (score 0.0).
   - Computes:
     - Total items (1,140)
     - Baseline matches & accuracy (43 / 1,140 = 3.77%)
     - Recovered matches & accuracy (score and 95% Wilson score interval)
     - Subject-by-subject recovery table.
     - Distribution of extracted answers vs targets.
   - Saves results summary to `results/accuracy-moe/study-2c/jang2l__osaurus/mmlu_rescored.json`.
   - Includes a `--self-test` mode with synthetic samples testing each regex pattern.

2. Create `docs/research/2026-09-19-osaurus-moe-mmlu-extraction.md`:
   - Concise research note documenting:
     - The extraction filter defect (why lm-eval reported 3.77%).
     - Concrete examples of false-negative outputs from the samples files.
     - The extraction methodology.
     - The recovered MMLU score for `jang2l__osaurus`.
     - How this compares to `jang2l__vmlx` (which threw HTTP 502 at item 80) and `stock4bit__vmlx` (35.53%).
     - Attribution: This is an offline recovery from completed, verified model outputs.

3. Verification:
   - Run: `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python scripts/rescore_moe_mmlu.py --self-test`
   - Run: `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python scripts/rescore_moe_mmlu.py`
   - Run: `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q`
   - Touch nothing else.
