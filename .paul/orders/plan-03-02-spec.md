GOAL: Specify Plan 03-02 (Cold vs Warm Page Cache Load & Memory Residency Attribution) study design and probe script.

CONTEXT:
Milestone v3 Phase 1 addresses Large-Model Scaling on Apple Silicon using Qwen3.6-35B-A3B (~19 GB 4-bit weights).
Plan 03-01 established the 16-cell serving grid across 5 runtimes and confirmed that:
1. Osaurus reports 12.3–15.4 GB peak footprint (0.74x weights) due to wired GPU page allocation, while mlx-lm, oMLX, OptiQ, and vMLX report 19.5–27.6 GB.
2. Cold load times across runtimes ranged from 1.4s to 12.1s without attributing how much was true APFS NVMe read vs warm page cache hit.
3. In v1, oMLX hid +3.5s in request #1 on 4B models (probe_lazy.py); at 35B, the lazy loading penalty needs rigorous attribution.

We have discovered that libc.mincore via ctypes can objectively measure the exact percentage (0.0% to 100.0%) of weight pages resident in the macOS unified buffer cache without requiring root/sudo purge.

DELIVERABLES:
1. docs/research/2026-09-20-v3-phase1-plan-03-02-study-design.md
   - Single-variable study design for Plan 03-02.
   - Pre-registers Hypotheses H1–H4 (I/O vs Remap, Lazy-load scaling, Metal wired GPU attribution, unified memory headroom).
   - Test matrix across all 5 runtimes holding format constant on stock4bit (mlx-community/Qwen3.6-35B-A3B-4bit).
2. scripts/probe_page_cache_35b.py
   - Uses mincore to verify page cache residency before and after load.
   - Measures cold load time (at verified cold state) vs warm load time (at verified warm state).
   - Times requests #1, #2, #3 to quantify the hidden lazy-load penalty at 35B.
   - Measures footprint and vmmap region breakdown (IOAccelerator vs anonymous vs mapped-file).
   - Verifies clean shutdown and port release.
