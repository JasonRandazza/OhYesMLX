GOAL: Write docs/research/2026-09-17-v2-track1-jang-study-design.md — the comprehensive study design, single-variable test matrix, loader attribution framework, and measurement protocol for v2 Track 1: The JANG Study.

FILES YOU MAY EDIT:
docs/research/2026-09-17-v2-track1-jang-study-design.md only. Touch nothing else.

STYLE & METHOD:
- Technical rigor matching docs/research/ style.
- Full markdown prose with structured tables, section headings, and explicit equations/definitions where needed.
- Grounded in existing repo code and observed data (ohyesmlx/runtimes.py, ohyesmlx/measure.py, scripts/gridspec.sh, scripts/gridspec-moe.sh).
- Strictly adhere to the defining rule: "Vary one thing at a time."

CONTEXT & EVIDENCE:
1. The Core Dilemma:
   - JANG formats (JANG_4S, JANG_2L, JANGTQ) showed remarkable decode throughput in initial spikes, but are proprietary bundles supported only by vMLX and Osaurus.
   - In v1, comparing JANG to mlx-lm or oMLX would change both runtime and format simultaneously, violating the single-variable rule.
   - Now in v2, because vMLX loads portable formats (stock-4bit, oQ4, oQ4e) AND JANG, and Osaurus loads portable formats (oQ4, oQ4e, OptiQ) AND JANG, we can formulate clean single-variable studies holding runtime constant, as well as holding JANG format constant across both runtimes.

2. On-Disk Artifact Verification:
   - All 10 artifacts are 100% verified on disk in ~/.cache/huggingface/hub/ (zero downloads needed):
     * Qwen3.5-4B (dense):
       - JANG_4S: models--JANGQ-AI--Qwen3.5-4B-JANG_4S/snapshots/4567967a46cd9e9bf26d3bb491ddd422ad607775 (2.99 GB)
       - stock-4bit: models--mlx-community--Qwen3.5-4B-4bit/snapshots/0e7ffd5c629ef7719d4cbc04069232580bfa9d9c (2.85 GB)
       - oQ4: models--RepublicOfKorokke--Qwen3.5-4B-oQ4/snapshots/3ae88a7d17b1c6bb71b795c1090948a82508fdb8 (2.94 GB)
       - oQ4e: models--uingei--Qwen3.5-4B-oQ4e/snapshots/2e232d525d5df5e7a6eece4b03b17087e6b3c3ac (2.95 GB)
       - OptiQ-4bit: models--mlx-community--Qwen3.5-4B-OptiQ-4bit/snapshots/6cb5bdfd0bf15f484881fb9f1ab6d7c840fddde9 (3.06 GB)
     * LFM2.5-8B-A1B (MoE):
       - JANG_2L: models--JANGQ-AI--LFM2.5-8B-A1B-JANG_2L/snapshots/5fb82773427c2f25395de8821eff6d95e86feb53 (2.85 GB)
       - stock-4bit: models--mlx-community--LFM2.5-8B-A1B-MLX-4bit/snapshots/146590a491db88581884033023f51f6b49a27b89 (4.45 GB)
       - oQ4: models--stamsam--LFM2.5-8B-A1B-oQ4/snapshots/acb4fd209565b7c05de287488416f4217820a3db (4.65 GB)
       - oQ4e: models--brainworkup--LFM2.5-8B-A1B-oQ4e/snapshots/88977e47cd1fe2eb5ec5bf5230d3de9868adef9e (4.65 GB)
       - OptiQ-4bit: models--mlx-community--LFM2.5-8B-A1B-OptiQ-4bit/snapshots/5a5c595823cf26ab1068508eb5cf85816bb2db6b (5.10 GB)

3. Attributions to Disentangle:
   - Is JANG's performance a result of:
     a) Tensor geometry and quantization (packed embed_tokens at half width (248320, 320), mixed bitwidths across modules)?
     b) Custom Metal kernels (vMLX utils/jang_loader)?
     c) Runtime optimizations that must be pinned (vMLX pins --no-jit and --disable-native-mtp; Osaurus tiedHeadCodec: q6)?

REQUIRED SECTIONS IN DOC:
1. Executive Summary & The Problem Statement (The single-variable imperative, why JANG was kept separate in v1, why v2 can measure it).
2. The Test Matrix Formulation:
   - Study 1A: JANG vs Portable in vMLX (Format Axis, runtime=vMLX held constant). Detail Dense (Qwen3.5-4B) and MoE (LFM2.5-8B-A1B). Note vMLX OptiQ behavior on dense (missing vision parameters in config.json).
   - Study 1B: JANG vs Portable in Osaurus (Format Axis, runtime=Osaurus held constant). Detail Dense and MoE. Note Osaurus stock4bit provider registration behavior.
   - Study 1C: Cross-Runtime JANG (Runtime Axis, format=JANG held constant: vMLX vs Osaurus on JANG_4S and JANG_2L).
3. The Attribution Analysis Framework:
   - Distinguishing weight-format advantages from loader-level optimizations.
   - Pinning discipline: pinning --no-jit and --disable-native-mtp in vMLX; Osaurus config capture.
4. On-Disk Artifact Inventory & Storage Verification:
   - Table of all 10 verified artifacts with snapshot paths, file counts, and sizes.
   - Zero-download compliance statement.
5. Experimental Protocol & Invariants:
   - Pinning parameters (temp 0, seed 0, cooldown 30s, plateau warmup: window 5, floor 10, cap 20, 3%).
   - Workload definitions (chat 128 tokens, prefill 64 tokens, decode 512 tokens).
   - Coherence gate requirement.
   - Memory sampling via footprint.
   - Host isolation & Osaurus settings guarantee: backup ~/.osaurus/config/, pin modelIdleResidencyPolicy to 900s, restore byte-exact verified with cmp.
   - Machine quietness requirement during measurement.
6. Execution Plan & Next Steps:
   - Phase 1 execution milestones (Plan 01-01: Dense JANG Study, Plan 01-02: MoE JANG Study, Plan 01-03: Cross-Runtime JANG Synthesis).

REPORT:
Return the path to the new document, an outline of its contents, and verification that tests still pass.
