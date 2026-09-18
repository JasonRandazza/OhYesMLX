GOAL: Author docs/research/2026-09-17-jang-cross-runtime.md — the cross-runtime JANG synthesis paper that closes v2 Phase 1 (Track 1: The JANG Study).

FILES YOU MAY EDIT:
docs/research/2026-09-17-jang-cross-runtime.md only. Touch nothing else.

STYLE & METHOD:
- Rigorous research paper style, exact Markdown tables, citations to the two underlying studies.
- No new measurements. Synthesizes findings across Plan 01-01 (Dense) and Plan 01-02 (MoE).
- Ground all numbers in docs/research/2026-09-17-dense-jang-study.md and docs/research/2026-09-17-moe-jang-study.md, evaluated against docs/research/2026-09-17-v2-track1-jang-study-design.md.

INPUTS:
- docs/research/2026-09-17-v2-track1-jang-study-design.md (especially §2.3, §3.1, §3.7, §6.4)
- docs/research/2026-09-17-dense-jang-study.md (Plan 01-01 findings, numbers, and tables)
- docs/research/2026-09-17-moe-jang-study.md (Plan 01-02 findings, numbers, and tables)

FOUR CORE QUESTIONS TO ANSWER DIRECTLY (per design doc §6.4):
1. Did JANG lead in vMLX, in Osaurus, in both, or in neither — per model, per workload?
   - Dense Qwen3.5-4B: JANG_4S led in BOTH runtimes on sustained decode (512 tokens), scoring R1 (Replicated Lead): +13.9%/+16.8% vMLX (54.2/59.1 vs best portable 47.6/50.6), +9.5%/+9.0% Osaurus (42.5/46.0 vs best portable 38.8/42.2).
   - MoE LFM2.5-8B-A1B: JANG_2L led in NEITHER runtime on sustained decode (512 tokens):
     * vMLX: +0.87% primary, −0.50% replicate — strictly inside the 2.5% band, an unresolvable TIE (R3) with stock4bit (116.3 vs 115.3, 120.4 vs 121.0).
     * Osaurus: −5.12% primary, −9.80% replicate — stock4bit cleanly beats JANG in both visits (123.0 vs 116.7, 127.5 vs 115.0).
   - Synthesis: The serving outcome forms a sharp 2x2 matrix. Decode throughput advantage is NOT a universal property of JANG; it holds on dense uniform packing and disappears on MoE.

2. Did the two runtimes agree on the direction, and how far apart are their JANG rates on identical bytes?
   - On Dense JANG_4S (identical 3,207,385,506 B):
     * vMLX decisively leads Osaurus across ALL workloads:
       decode: 54.2 vs 42.5 (+27.5% vMLX) in grid; 59.1 vs 46.0 (+28.5% vMLX) in replicate.
       chat: 55.2 vs 48.1 (+14.8% vMLX) in grid; 60.0 vs 49.6 (+21.0% vMLX) in replicate.
       prefill: 60.2 vs 55.8 (+7.9% vMLX) in grid; 62.7 vs 59.0 (+6.3% vMLX) in replicate.
   - On MoE JANG_2L (identical 3,062,430,853 B):
     * Runtimes diverge by workload:
       decode: dead heat in primary (116.3 vs 116.7, −0.3% gap, tie); slight vMLX lead in replicate (120.4 vs 115.0, +4.7%).
       chat: Osaurus leads vMLX by +12.4% (126.1 vs 112.2) in primary, +12.7% (132.3 vs 117.4) in replicate.
       prefill decode rate: Osaurus leads vMLX by +27.1% (123.4 vs 97.1) in primary, +25.0% (124.4 vs 99.5) in replicate.
       prefill prompt throughput: vMLX leads Osaurus by ~2x (1,643 vs 831 tok/s).
   - Insight: vMLX's Python/Metal stack dominates dense decode and long prompt ingestion; Osaurus's C++ binary excels at low per-request dispatch latency on short MoE generation.

3. Does the dense reading transfer to the MoE model (R4), or does the effect prove model-specific?
   - Pre-registered reading R4 (Split by Model) is triggered. The dense reading fails to transfer.
   - Confound & Attribution analysis: Why did JANG win dense and lose/tie MoE?
     * Bit width & packing difference: JANG_4S was near-equal precision (4.15 bits vs 4.0 bits, 4.8% larger on disk) where custom Metal tensor unpacking and half-width embeddings paid off on all weights. JANG_2L is highly compressed (2.37 bits average, 2/6/8 bit widths, 36% smaller on disk).
     * MoE routing dynamics: MoE decode activates only 1B out of 8B parameters per step (top-4 of 32 experts). Contiguous uniform 4-bit memory streaming in stock MLX is extremely fast. The overhead of dequantizing non-uniform 2/6/8-bit tensors per token neutralizes the memory bandwidth reduction.
     * Prefill vs Decode split: During prefill, all tokens process in parallel across projection weights; here JANG_2L's 2.37 bits delivered +53.6% higher prompt throughput in vMLX (1,643 vs 1,070 prompt tok/s).

4. What remains unattributed, and what is the exact next experiment?
   - The Ledger of Confounds: Packing vs Kernel vs JIT.
   - In both studies, `--no-jit` and `--disable-native-mtp` were pinned off to isolate the format.
   - The shipped vMLX experience uses auto-JIT (`mx.compile`) and native MTP heads.
   - The deferred single-variable follow-up: A legal single-variable A/B inside vMLX (`--no-jit` vs JIT on identical JANG weights) to isolate the compiler speedup.
   - The Density Trade: JANG on MoE is not a throughput accelerator; it is a compression and memory footprint optimizer (36% disk savings, 16–31% memory reduction, identical decode throughput in vMLX).

REQUIRED SECTIONS:
1. Executive Summary & Synthesis Thesis (The JANG duality: throughput winner on dense, memory/density winner on MoE; R4 triggered).
2. The Test Matrix & Methodological Basis (Summary of the two campaigns, 5-format matrices, zero downloads, pins, byte-exact Osaurus cache restoration guarantee).
3. Synthesis Finding 1: Format-Axis Comparison Across Dense and MoE (Side-by-side tables for Qwen3.5-4B vs LFM2.5-8B-A1B, R1 vs R4, tie bands).
4. Synthesis Finding 2: The Runtime Axis on Identical Bytes (Cross-runtime JANG row comparison: vMLX dominance on dense vs Osaurus/vMLX split on MoE).
5. Architectural Attribution: Dense Uniformity vs MoE Routing Dynamics (Why unpacking speedups hold when all weights decode, but fail under expert routing; prefill throughput divergence).
6. The Unified Resource Economy: Throughput vs Memory Footprint vs Disk (Quantifying the trade: JANG_4S carries more disk for +15% speed; JANG_2L gives equal/slower speed for 36% disk and 30% memory savings).
7. The Confound Ledger & The Next Experiment (What remains: JIT, MTP; framing the vMLX JIT A/B test).
8. Phase 1 Closeout & Transition to Track 2 (Closing Track 1; setting up Accuracy Scoring).

REPORT:
Path to the new document, summary of synthesis findings, and confirmation of 495 green tests.
