"""Diagnostic probe for Candidate 4: vMLX hybrid chunked prefill at 32k.

Tests whether setting VMLX_ALLOW_HYBRID_CHUNKED_PREFILL=1 allows vMLX 1.6.59 to
chunk the 32k prompt on Qwen3.5-4B-oQ4, avoiding the Metal watchdog interactivity
failure (kIOGPUCommandBufferCallbackErrorImpactingInteractivity).

Runs exactly 1 request to verify mechanism and logs before any full sweep.
"""
import os
import sys
import time

sys.path.insert(0, "/Users/jrazz/Dev/active/OhYesMLX")
from ohyesmlx import cli, coherence, runtimes, token_counter, transport

Q4_SNAP = os.path.expanduser(
    "~/.cache/huggingface/hub/models--RepublicOfKorokke--Qwen3.5-4B-oQ4/snapshots/3ae88a7d17b1c6bb71b795c1090948a82508fdb8"
)

# Enable hybrid chunked prefill in the environment for vMLX
os.environ["VMLX_ALLOW_HYBRID_CHUNKED_PREFILL"] = "1"

print("Sizing 32k prompt for Qwen3.5-4B-oQ4...", flush=True)
counter = token_counter.TokenCounter(Q4_SNAP)
text, achieved = cli.sized_prompt(counter, 32768)
print(f"Target 32768 -> Achieved {achieved} tokens", flush=True)

messages = [{"role": "user", "content": text}]
rt = runtimes.RUNTIMES["vmlx"]

print("Starting vMLX with VMLX_ALLOW_HYBRID_CHUNKED_PREFILL=1...", flush=True)
handle = None
t0 = time.monotonic()
try:
    handle = rt.start(Q4_SNAP, "vmlx/oq4")
    print(f"vMLX started in {round(handle.cold_load_s, 2)}s (PID {handle.pid})", flush=True)
    
    print("Sending 32k prompt request (timeout 300s)...", flush=True)
    req_t0 = time.monotonic()
    obs = transport.chat(
        handle.base_url,
        handle.model_id,
        messages,
        max_tokens=64,
        temperature=0.0,
        seed=0,
        api_key=handle.api_key,
        timeout_s=300.0,
    )
    req_elapsed = time.monotonic() - req_t0
    print(f"Request finished in {round(req_elapsed, 2)}s", flush=True)
    print(
        f"obs.ok: {obs.ok}, TTFT: {obs.ttft_s}, total_s: {obs.total_s}, "
        f"prompt_tokens: {obs.prompt_tokens}, completion_tokens: {obs.completion_tokens}, "
        f"content_events: {obs.content_event_count}, error: {obs.error}"
    )
    out_text = obs.text or obs.reasoning_text or ""
    print(f"Output preview ({len(out_text)} chars): {out_text[:300]}")
    if out_text:
        is_coh, coh_reason = coherence.is_coherent(out_text)
        print(f"Coherent: {is_coh} ({coh_reason})")

finally:
    if handle is not None:
        print("Stopping vMLX...", flush=True)
        handle.stop()
        print("vMLX stopped.", flush=True)

print("PROBEDONE", flush=True)
