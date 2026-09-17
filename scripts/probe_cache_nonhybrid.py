"""Loadability probe for Candidate 3 non-hybrid model: brainworkup/Llama-3.1-8B-oQ4.

Tests whether all five runtimes (mlxlm, omlx, optiq, vmlx, osaurus) can start,
serve the non-hybrid Llama-3.1-8B-oQ4 model, answer one short request coherently,
and cleanly stop without leaking ports or processes.

Does not write to results/.
"""
import json
import os
import sys
import time

sys.path.insert(0, "/Users/jrazz/Dev/active/OhYesMLX")
from ohyesmlx import coherence, runtimes, transport

SNAP = os.path.expanduser(
    "~/.cache/huggingface/hub/models--brainworkup--Llama-3.1-8B-oQ4/snapshots/a041336af01fe59ffe17c762d4c970564dcabc53"
)
RUNTIMES = ["mlxlm", "omlx", "optiq", "vmlx", "osaurus"]
MESSAGES = [{"role": "user", "content": "Name one colour."}]

runtimes.READY_TIMEOUT_S = 180.0

out = []
for name in RUNTIMES:
    rt = runtimes.RUNTIMES[name]
    row = {"runtime": name, "model": "Llama-3.1-8B-oQ4"}
    handle = None
    t0 = time.monotonic()
    try:
        handle = rt.start(SNAP, f"{name}/oq4")
        row["load_s"] = round(handle.cold_load_s, 2)
        obs = transport.chat(
            handle.base_url,
            handle.model_id,
            MESSAGES,
            max_tokens=24,
            temperature=0.0,
            seed=0,
            api_key=handle.api_key,
        )
        text = obs.text or obs.reasoning_text
        row["ok"] = bool(obs.ok)
        row["text"] = (text or "")[:70]
        row["coherent"] = coherence.is_coherent(text)[0] if text and text.strip() else False
        row["verdict"] = "LOADS" if obs.ok and row["coherent"] else f"error: {obs.error}"
    except Exception as e:
        row["verdict"] = f"{type(e).__name__}: {e}"[:220]
    finally:
        if handle is not None:
            try:
                handle.stop()
            except Exception as e:
                row["stop_error"] = str(e)[:120]
    row["elapsed_s"] = round(time.monotonic() - t0, 1)
    out.append(row)
    print(json.dumps(row), flush=True)

print("PROBEDONE", flush=True)
