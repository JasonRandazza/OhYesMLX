GOAL: Specify Plan 03-03 (Expert Streaming under High Memory Pressure) study design and probe script.

CONTEXT:
Milestone v3 Phase 1 addresses Large-Model Scaling on Apple Silicon using Qwen3.6-35B-A3B (~19–20 GB 4-bit weights).
Plan 03-01 established the 16-cell serving grid across 5 runtimes, confirming:
- Resident 35B MoE decodes at 58–70 tok/s across all runtimes, within 2x of 8B MoE.
- Memory footprint is ~19.5–27.6 GB across mlxlm, oMLX, OptiQ, and vMLX.
- OptiQ and vMLX ship built-in SSD expert streaming architectures designed to allow large MoEs to serve on memory-constrained hardware:
  1. OptiQ: `--stream-experts` / `--stream-experts-cache` (using `StreamingQuantizedSwitchLinear` and `os.pread` queue depth 24).
  2. vMLX: `--flash-moe` / `--flash-moe-slot-bank` (dynamic streaming) and `--smelt` / `--smelt-experts` (static partial expert retention).

Plan 03-03 evaluates the exact trade-offs of SSD-based expert streaming vs resident serving on 35B MoE, pricing the memory savings against decode and prefill penalties, evaluating LRU cache effectiveness, and testing the 70% RAM auto-trigger heuristic.

DELIVERABLES:
1. docs/research/2026-09-20-v3-phase1-plan-03-03-study-design.md
   - Single-variable study design for Plan 03-03.
   - Pre-registers Hypotheses H1–H5 (Backbone resident floor, Decode throughput penalty, Slot bank/LRU caching efficiency, Smelt vs FlashMoE trade-offs, 70% RAM auto threshold analysis).
   - Test matrix across OptiQ and vMLX comparing Resident Baseline vs Streamed vs Cached vs Smelt configurations on stock 4-bit (mlx-community/Qwen3.6-35B-A3B-4bit).
2. scripts/probe_expert_streaming_35b.py
   - Multi-configuration probe executing:
     a) OptiQ Resident Baseline (`--no-stream-experts`)
     b) OptiQ Full Streaming (`--stream-experts`)
     c) OptiQ Streaming + LRU Cache (`--stream-experts --stream-experts-cache 64`)
     d) vMLX Resident Baseline (standard `--no-jit --disable-native-mtp`)
     e) vMLX FlashMoE Streaming (`--flash-moe --flash-moe-slot-bank 64`)
     f) vMLX Smelt Partial Loading (`--smelt --smelt-experts 50`)
   - Measures:
     - Startup time & TTFT
     - Prefill throughput & Decode throughput
     - Physical memory footprint (`phys_footprint_mb`, `IOAccelerator` resident)
     - Output coherence & text integrity
