GOAL: Specify Plan 03-05 (Quantized KV Caches: FP8, INT4 vs FP16 KV Caches at 16k and 32k) study design and probe script.

CONTEXT:
Milestone v3 Phase 2 addresses Context Scaling & Conversational Dynamics on Apple Silicon.
At long context windows (16k and 32k tokens), standard FP16 KV caches consume massive unified memory:
- For an 8B GQA model (e.g. LLaMA 3.1 8B, 32 layers, 8 KV heads, dim 128), FP16 KV cache consumes 2.15 GB at 16k and 4.29 GB at 32k.
- On Apple Silicon unified memory architectures where memory bandwidth is shared between CPU and GPU, reading a 4.29 GB KV cache on every decode step competes directly with model weight reading.
Runtimes support KV cache quantization:
1. OptiQ (`optiq serve`):
   - Supports uniform QuantizedKVCache via `--kv-bits 4` (INT4) and `--kv-bits 8` (FP8), with streaming per-layer conversion and fused quantized SDPA (FlashAttention-2 N-tiling).
2. vMLX (`vmlx serve`):
   - Supports generic KV cache quantization via `--kv-cache-quantization {none, q8, q4}`.
3. mlx-lm (`mlx_lm.server`):
   - Serves as the unquantized FP16 control reference.

Plan 03-05 evaluates unified memory savings vs TTFT/decode latency and output coherence at 16k and 32k context lengths across candidate configurations:
1. OptiQ: FP16 baseline, FP8 (`--kv-bits 8`), INT4 (`--kv-bits 4`).
2. vMLX: FP16 baseline (`--kv-cache-quantization none`), FP8 (`--kv-cache-quantization q8`), INT4 (`--kv-cache-quantization q4`).
3. mlxlm: FP16 reference control.

DELIVERABLES:
1. docs/research/2026-09-20-v3-phase2-plan-03-05-study-design.md
   - Pre-registered single-variable study design with hypotheses H1–H5.
   - Pinned 16k and 32k prompts cut from frozen fixture `ohyesmlx/longtext.md`.
2. scripts/probe_kv_quant.py
   - Dedicated probe script measuring cold load time, TTFT, decode throughput (tok/s), ITL (ms), peak physical footprint (`phys_footprint_mb`), and coherence.
3. results/plan-03-05/kv_quant_results.json
   - Full raw empirical observations across all cells and context lengths.
4. docs/research/2026-09-20-quantized-kv-caches.md
   - Comprehensive research report analyzing H1–H5 against empirical data and closing Milestone v3 Phase 2.
