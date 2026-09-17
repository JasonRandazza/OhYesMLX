GOAL: write docs/research/2026-09-17-vmlx-32k-chunked-prefill.md — explaining how vMLX's 32k Metal watchdog failure on hybrid models (Qwen3.5-4B-oQ4) is resolved via VMLX_ALLOW_HYBRID_CHUNKED_PREFILL=1, verified live with exact timings, logs, and release comparison.

FILES YOU MAY EDIT: docs/research/2026-09-17-vmlx-32k-chunked-prefill.md only. Touch nothing else.

STYLE & METHOD:
Match docs/research/ style: full technical prose, code excerpts, verbatim log lines, exact numbers recomputed from run records. Cite source files and line numbers.

INPUTS:
- docs/research/2026-09-16-prompt-length-sweep.md (the original 32k failure: 28/49 dead streams, kIOGPUCommandBufferCallbackErrorImpactingInteractivity, and open question 1)
- Shipped source of vMLX: /Applications/vMLX.app/Contents/Resources/vmlx-engine-source/vmlx_engine/mllm_batch_generator.py (lines 11412–11497, 11874–11889)
- Shipped wheel of vMLX 1.6.61: /tmp/vmlx-inspect/unpacked/vmlx_engine/mllm_batch_generator.py
- Latest verified live probe run: scripts/probe_vmlx_32k.py and results/logs/vmlx-20260917T135344-44197.log (and latest run log)

COORDINATOR'S VERIFIED FINDINGS:
1. Why --prefill-step-size 512 was previously ignored on Qwen3.5:
   - In mllm_batch_generator.py lines 11412-11463:
     `_hybrid_chunk_env = os.environ.get("VMLX_ALLOW_HYBRID_CHUNKED_PREFILL") or os.environ.get("VMLINUX_ALLOW_HYBRID_CHUNKED_PREFILL")`
     Unless this env var is set truthy, `_allow_hybrid_chunked` defaults to False.
     `_hybrid_blocks_chunk = self._is_hybrid and not _allow_hybrid_chunked`
     In line 11888, the chunked prefill path requires `(not _hybrid_blocks_chunk)`.
     Because Qwen3.5 has `self._is_hybrid = True`, it was blocked from chunking, forcing `Hybrid prefill path=one-shot seq_len=32775`.
2. Live probe execution with VMLX_ALLOW_HYBRID_CHUNKED_PREFILL=1:
   - Model: RepublicOfKorokke/Qwen3.5-4B-oQ4, prompt tokens 32765 (achieved).
   - Log confirmed:
     `Hybrid prefill path=chunked family=qwen3_5_text seq_len=32775 cached=0 — VMLX_ALLOW_HYBRID_CHUNKED_PREFILL='1'`
     `Pre-sized 8 KV slots to the full 32775-token span +4096 decode headroom`
     `hybrid-prefill-slots chunk=8 processed=16384 active=4.10GB ArraysCachex24=0.05GB KVCachex8=1.13GB`
     `hybrid-prefill-slots chunk=16 processed=32768 active=4.10GB ArraysCachex24=0.05GB KVCachex8=1.13GB`
   - Request result:
     HTTP 200 OK, request finished in 90.11s, TTFT: 88.76s, completion_tokens: 64, content_events: 64, error: None.
     Output: Coherent (passed coherence.is_coherent with full reasoning process).
     Active Metal memory capped at only 4.10 GB.
     ZERO watchdog timeouts. ZERO dropped streams.
3. Comparative standing at 32k:
   - mlx-lm: 75.54s
   - Osaurus: 79.91s
   - oMLX: 81.02s
   - vMLX (chunked): 88.76s
   - OptiQ: 88.99s
   The 32k column is now complete across all 5 runtimes.
4. Release audit (1.6.59 vs 1.6.61):
   - PyPI has 1.6.61 (host has 1.6.59).
   - In 1.6.61, `_allow_hybrid_chunked` remains False by default (line 11492).
   - Therefore, `VMLX_ALLOW_HYBRID_CHUNKED_PREFILL=1` is the essential operator mechanism in both versions.

REPORT:
Path to document, summary of the mechanism, and test verification confirmation.
