GOAL: write docs/research/2026-09-17-cache-state-split-nonhybrid.md — the non-hybrid (Llama-3.1-8B-oQ4) cold/warm KV split result — comparing off vs on across all five serving runtimes and contrasting directly with the hybrid Qwen3.5-4B result in docs/research/2026-09-17-cache-state-split.md.

FILES YOU MAY EDIT: docs/research/2026-09-17-cache-state-split-nonhybrid.md only. Touch nothing else.

STYLE & METHOD:
Match docs/research/ style: full prose, Markdown tables, clear section headings, exact numbers recomputed from run records. No hand-waving. Cite evidence files.

INPUTS:
- results/sweep-cache-nonhybrid/ (10 run directories, oq4__<runtime>, Llama-3.1-8B-oQ4, prompt-tokens achieved 4089 / target 4096, off then on per runtime, run 2026-09-17 12:26–13:33 local):
  * mlxlm: off 20260917T162610Z-format / on 20260917T163922Z-format
  * omlx: off 20260917T164142Z-format / on 20260917T165226Z-format
  * optiq: off 20260917T165500Z-format / on 20260917T170554Z-format
  * vmlx: off 20260917T170825Z-format / on 20260917T171756Z-format
  * osaurus: off 20260917T172032Z-format / on 20260917T173114Z-format
- results/sweep-cache-nonhybrid/sweep-ttft.md and sweep-decode.md
- results/sweep-cache-nonhybrid/runner.log (exit 0, osaurus settings restored byte-exact)
- docs/research/2026-09-17-cache-state-split.md (the hybrid baseline to contrast against)
- Server logs in results/logs/ for those runs

COORDINATOR'S VERIFIED READINGS (verify every number from leaderboard.md and results.jsonl):
- TTFT p50 off -> on:
  * mlxlm: 19.112 s -> 0.136 s (140.5x speedup; prefill tok/s 215.7 -> 30,210.0)
  * omlx: 19.495 s -> 0.529 s (36.9x speedup; prefill tok/s 211.5 -> 7,792.3)
  * optiq: 19.637 s -> 0.138 s (142.3x speedup; prefill tok/s 210.0 -> 29,773.4)
  * vmlx: 16.440 s -> 0.419 s (39.2x speedup; prefill tok/s 250.8 -> 9,850.0)
  * osaurus: 17.641 s -> 0.697 s (25.3x speedup; prefill tok/s 233.7 -> 5,917.1)
- TTFT p90 off -> on:
  * mlxlm: 19.364 s -> 0.141 s
  * omlx: 19.626 s -> 0.533 s
  * optiq: 19.908 s -> 0.144 s
  * vmlx: 16.695 s -> 0.429 s
  * osaurus: 17.852 s -> 0.725 s
- All 10 cells PASS, 9 measured requests, 0 failed requests.
- Warmup series in "on" state:
  * Warmup #1 is full prefill (~16–21 s): mlxlm 16.569 s, omlx 21.351 s, optiq 20.489 s, vmlx 16.046 s, osaurus 18.533 s.
  * Warmup #2 immediately collapses to lookup speed: mlxlm 0.115 s, optiq 0.111 s, vmlx 0.497 s, osaurus 0.606 s, omlx 0.800 s.
- Peak memory:
  * vmlx on allocates cache structures: 6385 MB (off) -> 7520 MB (on).
  * optiq ~8940 MB baseline in both states.
  * mlxlm and omlx ~6270–6350 MB.
  * osaurus ~3730–3780 MB (wired GPU accounting difference as documented in research).

REQUIRED SECTIONS:
1. What ran and provenance table (runtimes, versions, run dirs, pins, artifact brainworkup/Llama-3.1-8B-oQ4).
2. The headline table: off vs on TTFT (p50, p90, on/off ratio, speedup).
3. First request against the rest: warmup #1 vs warmup #2 vs measured p50.
4. Direct comparison with the hybrid Qwen3.5-4B sweep:
   - Contrast the two sweeps side by side (table comparing hybrid speedup vs non-hybrid speedup).
   - Prove the hypothesis from 2026-09-17-cache-state-split.md: mlx-lm, optiq, and vmlx showed 1.00x on Qwen3.5-4B because of `ArraysCache` (non-trimmable linear attention layers), NOT because of defective cache implementation.
   - When given standard trimmable `KVCache`, mlx-lm and optiq are the fastest prefix lookups of all five runtimes (~136–138 ms, >140x speedup).
5. Decode throughput and ITL impact: show decode_tps in off vs on, discuss prefill_tps jump (30k tok/s on hits), ITL stability.
6. Memory and resource footprint: footprint comparison off vs on, vMLX's explicit cache memory growth (+1.1 GB).
7. Host isolation & integrity: Osaurus settings toggled and restored byte-exact, verified by cmp; oMLX scratch isolation; port isolation.

REPORT:
Path to the new document, summary of the headline findings, and confirmation of byte-exact test verification.
