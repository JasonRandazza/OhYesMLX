GOAL: Author docs/research/2026-09-19-accuracy-pareto.md — the final Pareto Tradeoff Synthesis paper for v2 Phase 2 Track 2 (Plan 02-04), uniting Speed, Memory, and Accuracy across all tested models and runtimes.

FILES YOU MAY EDIT:
docs/research/2026-09-19-accuracy-pareto.md only. Touch nothing else.

STYLE & METHOD:
- Rigorous research paper style, exact Markdown tables, citations to all underlying studies.
- No new measurements. Synthesizes findings across Track 1 (Dense & MoE JANG studies) and Track 2 (Dense & MoE Accuracy studies).
- Ground all numbers in the source research documents and evaluate against docs/research/2026-09-17-v2-track2-accuracy-study-design.md.

INPUTS:
- docs/research/2026-09-17-v2-track2-accuracy-study-design.md (especially §1.3, §5.3, §5.5, §5.6, §5.7, §6.5)
- docs/research/2026-09-18-accuracy-dense.md (Plan 02-02 Dense Accuracy Study: scores, paired intervals, Study 2C loader offset)
- docs/research/2026-09-19-accuracy-moe.md (Plan 02-03 MoE Accuracy Study: scores, paired intervals, vMLX truncation trap, Study 2C extraction confound)
- docs/research/2026-09-17-dense-jang-study.md (Track 1 Dense speed and memory quotations)
- docs/research/2026-09-17-moe-jang-study.md (Track 1 MoE speed and memory quotations)
- docs/research/2026-09-17-jang-cross-runtime.md (Track 1 Cross-Runtime Synthesis)

KEY COORDINATES TO QUOTE (from Track 1 & Track 2 records):
1. Dense Qwen3.5-4B in vMLX:
   - stock4bit: decode=44.2 tok/s (+16.6% drift), peak=3,843 MB, disk=3,061,131,520 B (3.06 GB), MMLU=67.89% (1548/2280), GSM8K=89.6%, IFEval=78.8%
   - jang4s: decode=54.2 tok/s (+5.9% drift), peak=3,820 MB, disk=3,207,385,506 B (3.21 GB), MMLU=68.42% (1560/2280), GSM8K=87.2%, IFEval=79.2%
   - oq4: decode=47.6 tok/s (+14.2% drift), peak=3,819 MB, disk=3,160,559,814 B (3.16 GB), MMLU=68.20% (1555/2280), GSM8K=90.0%, IFEval=80.8%
   - oq4e: decode=46.0 tok/s (+5.4% drift), peak=3,946 MB, disk=3,167,949,891 B (3.17 GB), MMLU=66.89% (1525/2280), GSM8K=88.0%, IFEval=84.0%

2. Dense Qwen3.5-4B in Osaurus:
   - jang4s: decode=42.5 tok/s (+5.1% drift), peak=3,400 MB, disk=3,207,385,506 B (3.21 GB), MMLU=64.87%, GSM8K=89.6%, IFEval=78.0%
   - oq4: decode=38.8 tok/s (+18.7% drift), peak=2,466 MB, disk=3,160,559,814 B (3.16 GB), MMLU=64.17%, GSM8K=89.2%, IFEval=83.6%
   - oq4e: decode=38.6 tok/s (+6.2% drift), peak=2,216 MB, disk=3,167,949,891 B (3.17 GB), MMLU=65.44%, GSM8K=85.6%, IFEval=78.4%
   - optiq: decode=38.7 tok/s (-1.0% drift), peak=2,472 MB, disk=4,043,620,369 B (4.04 GB), MMLU=61.05%, GSM8K=88.8%, IFEval=76.8%

3. MoE LFM2.5-8B-A1B in vMLX:
   - stock4bit: decode=115.3 tok/s (+3.9% drift), peak=5,214 MB, disk=4,782,228,753 B (4.78 GB), MMLU=35.53% (405/1140), GSM8K=FAIL (halted item 176), IFEval=52.0%
   - jang2l: decode=116.3 tok/s (+0.5% drift), peak=3,624 MB, disk=3,062,430,853 B (3.06 GB), MMLU=FAIL (halted item 80), GSM8K=FAIL (halted item 53), IFEval=56.8%
   - oq4: decode=65.6 tok/s (+76.0% drift ⚠), peak=5,415 MB, disk=4,994,822,580 B (4.99 GB), MMLU=21.93% (250/1140), GSM8K=38.8%, IFEval=57.6%
   - oq4e: decode=97.0 tok/s (+10.9% drift), peak=5,416 MB, disk=4,994,831,815 B (4.99 GB), MMLU=36.23% (413/1140), GSM8K=41.6%, IFEval=60.8%
   - optiq: decode=100.6 tok/s (+6.1% drift), peak=5,869 MB, disk=5,473,296,789 B (5.47 GB), MMLU=28.25% (322/1140), GSM8K=37.6%, IFEval=62.4%

4. MoE LFM2.5-8B-A1B in Osaurus (Notes for non-drawability):
   - Track 1: stock4bit 123.0 tok/s, jang2l 116.7 tok/s, oq4 115.8 tok/s, but oq4e and optiq FAILed decode.
   - Track 2: jang2l MMLU is 3.77% due to extraction filter regex failure on prose prefix.
   - Per Study Design §5.5, this frontier is UN-DRAWABLE and explicitly omitted.

CORE REQUIREMENTS:
1. Executive Summary:
   - Must contain the mandatory synthesis framing sentence (Study Design §6.5):
     "On Qwen3.5-4B and LFM2.5-8B-A1B, in vMLX 1.6.59 and Osaurus 0.25.x, at these pins and on this item set, format A's measured speed and density advantage was / was not bought with a measurable accuracy cost of Δ points (interval, K discordant items), and the frontier of non-dominated formats is..."
   - State the high-level synthesis thesis: Accuracy preserves the JANG Duality (Dense JANG_4S gives free +14–22% decode speedup with zero accuracy loss; MoE JANG_2L preserves instruction following at 2.37 bits with 36% disk savings and 30% memory reduction).
   - Summarize the fate of OptiQ: strictly dominated across both dense and MoE.
   - Summarize the fate of outlier protection: mandatory on MoE to prevent quality collapse.

2. Methodological Foundation (§5.5):
   - Detail the 2D Pareto formulation with coordinates (x=accuracy, y1=decode_tps, y2=peak_mb, y3=disk_bytes).
   - Strict dominance definition: requires clearing the 1.5 pp accuracy band (with 95% CI excluding 0), 2.5% throughput band, 1% memory band, and exact disk equality.
   - Explain why no task-pooling or composite index is computed (preserving single-workload clarity).
   - Re-state that all speed and memory figures are direct quotations from Track 1 with drift markers intact.

3. The Three Frontier Tables (§5.5):
   - Table 1: Qwen3.5-4B on vMLX (MMLU primary; secondary notes for GSM8K/IFEval).
   - Table 2: Qwen3.5-4B on Osaurus (MMLU primary; secondary notes for GSM8K/IFEval).
   - Table 3: LFM2.5-8B-A1B on vMLX (MMLU primary; secondary notes for IFEval).
   - For each table: list every format, its coordinates, drift annotation, dominance verdict, and frontier bin.
   - Clearly articulate why MoE Osaurus is omitted.

4. Trade Rates (Slopes) (§5.5):
   - Calculate R_quality/speed (pp per tok/s), R_quality/memory (pp per 100 MB), R_quality/disk (pp per GB) for pairs that clear the bands.
   - For pairs within the parity band (e.g., JANG_4S vs stock4bit on dense vMLX: +0.53 pp MMLU [CI: -0.38, +1.43 pp]), explicitly mark with a slash (—) indicating free speedup / zero quality penalty.
   - Price the real trade-offs (e.g., oQ4e vs stock4bit on dense: -1.00 pp MMLU for +1.8 tok/s and +5.2 pp IFEval; oQ4e vs stock4bit on MoE).

5. The Four Questions Answered in Order (§1.3 / §5.3):
   - Q1: Vendor Claim (JANG_2L at 2.37 bits matching 4-bit MMLU): Indeterminate on MMLU due to vMLX reasoning truncation halt (HTTP 502); Outcome P3 rejected on IFEval (56.8% vs 52.0%, no collapse).
   - Q2: JANG_4S Quality Trade (Dense decode lead vs uniform 4-bit): Zero penalty. Outcome P1 (Quality Parity) confirmed (+0.53 pp MMLU [95% CI: -0.38, +1.43 pp]).
   - Q3: Pareto Status of OptiQ: Strictly dominated on both Dense and MoE. Resource penalties bought negative accuracy.
   - Q4: Outlier Protection (oQ4 vs oQ4e): Mandatory on MoE (+14.30 pp MMLU advantage for oQ4e over oQ4); subtle trade-off on Dense.

6. The Unified Recommendation Table:
   - Construct the final 3-coordinate recommendation table for Apple Silicon users:
     * Dense recommendations (Best throughput: JANG_4S; Smallest disk: stock4bit; Best instruction following: oQ4e).
     * MoE recommendations (Smallest footprint & disk with preserved IFEval: JANG_2L; Best MMLU accuracy: oQ4e / stock4bit; strictly avoid: OptiQ, un-protected oQ4).
   - Clearly state what cannot be claimed (no leaderboard claims, no general quantization claims, no cross-runtime accuracy rankings).

7. v2 Track 2 & Milestone v2 Closeout:
   - Document the completion of Track 2 and Milestone v2.
