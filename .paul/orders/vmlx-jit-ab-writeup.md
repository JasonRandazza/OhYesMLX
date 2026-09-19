GOAL: Write the research report for the vMLX JIT A/B experiment (Milestone v2, Candidate 2).

CONTEXT:
We have just executed `scripts/run_vmlx_jit_ab.sh` on Apple Silicon (M2 Max 64GB).
Results are recorded in:
- JIT OFF: `results/vmlx-jit-ab/jit-off/20260919T195147Z-format/results.jsonl`
- JIT ON: `results/vmlx-jit-ab/jit-on/20260919T200559Z-format/results.jsonl`
- Runner log: `results/vmlx-jit-ab/runner.log`

FILES TO TOUCH:
- docs/research/2026-09-19-vmlx-jit-ab.md

SPECIFICATION:
Create `docs/research/2026-09-19-vmlx-jit-ab.md` documenting the findings with rigor and exact numbers.

Structure:
1. Executive Summary & Metadata:
   - Date: 2026-09-19
   - Hardware: Apple Silicon M2 Max (64 GB unified memory)
   - Runtime: vMLX 1.6.59
   - Single variable: `--no-jit` vs `--enable-jit` via `OHYESMLX_VMLX_ENABLE_JIT`
   - Artifacts: `Qwen3.5-4B-JANG_4S` (dense) and `LFM2.5-8B-A1B-JANG_2L` (MoE)
   - Headline Finding: JIT does NOT improve decode speed on 4B/8B models on Apple Silicon. Across all 6 cell-workloads, `--enable-jit` carries a -2.7% to -11.3% decode throughput penalty (-1.5 to -8.7 tok/s).

2. Measured Comparison Tables:
   - Decode throughput (tok/s) across chat, prefill, decode:
     - `jang4s__vmlx` (Qwen3.5-4B-JANG_4S):
       - chat: 58.7 tok/s (OFF) -> 57.0 tok/s (ON), delta -1.7 tok/s (-2.8%)
       - prefill: 54.8 tok/s (OFF) -> 53.3 tok/s (ON), delta -1.5 tok/s (-2.7%)
       - decode: 65.0 tok/s (OFF) -> 57.7 tok/s (ON), delta -7.3 tok/s (-11.3%)
     - `jang2l__vmlx` (LFM2.5-8B-A1B-JANG_2L):
       - chat: 110.7 tok/s (OFF) -> 103.9 tok/s (ON), delta -6.9 tok/s (-6.2%)
       - prefill: 108.9 tok/s (OFF) -> 100.2 tok/s (ON), delta -8.7 tok/s (-8.0%)
       - decode: 113.4 tok/s (OFF) -> 105.6 tok/s (ON), delta -7.8 tok/s (-6.8%)
   - TTFT P50 (s):
     - `jang4s__vmlx`: chat 0.142s -> 0.144s (+1.5%); prefill 2.282s -> 2.231s (-2.3%); decode 0.139s -> 0.139s (0.0%)
     - `jang2l__vmlx`: chat 0.102s -> 0.104s (+1.9%); prefill 1.019s -> 1.033s (+1.4%); decode 0.102s -> 0.105s (+2.5%)
   - Prefill Throughput (tok/s):
     - `jang4s__vmlx`: prefill workload 575.8 -> 589.1 tok/s (+2.3%)
     - `jang2l__vmlx`: prefill workload 1310.0 -> 1292.4 tok/s (-1.3%)
   - Peak Memory (MB phys_footprint):
     - `jang4s__vmlx`: 3791 MB -> 3717 MB (-74 MB, -2.0%)
     - `jang2l__vmlx`: 3596 MB -> 3596 MB (0 MB, 0.0%)
   - Cold Load Time (s):
     - `jang4s__vmlx`: 9.11s -> 6.08s
     - `jang2l__vmlx`: 7.07s -> 6.07s

3. Architectural Analysis:
   - Why did the Eric directive default JIT on for JANG affine bundles?
     - `docs/runtimes/vmlx.md` quotes the rationale: on a massive 397B model (`JANG_1L`), inference ran at 10 tok/s without JIT vs 20+ expected.
   - Why does JIT regress on 4B–8B models on Apple Silicon?
     - On smaller models at batch size N=1, inference is strictly memory-bandwidth bound. Graph compilation via `mx.compile` does not reduce memory traffic for 4-bit affine dequantization; instead, kernel dispatch overhead or suboptimal fusion hurts decode throughput.
   - Vindication of harness methodology:
     - The harness pinned `--no-jit` in Track 1 to hold runtime features constant; this study proves `--no-jit` was also faster.

4. Actionable Guidance for Users:
   - For 4B–8B models on Apple Silicon, pass `--no-jit` or set `VMLX_DISABLE_JANG_AFFINE_JIT_DEFAULT=1`.

VERIFICATION:
- Verify exact figures against the results directories.
- Run `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q`
- Touch nothing else.
