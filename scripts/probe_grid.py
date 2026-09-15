"""Loadability probe: which (format, runtime) cells can run at all.

Not a measurement. One short request per cell, coherence checked, then stop. A cell that
loads and answers is a live cell; anything else records the reason verbatim so the grid's
holes are evidence rather than absence.
"""
import json, sys, time, os
sys.path.insert(0, "/Users/jrazz/Dev/active/OhYesMLX")
from ohyesmlx import runtimes, transport, coherence

HUB = os.path.expanduser("~/.cache/huggingface/hub")
FORMATS = {
    "stock4bit": "models--mlx-community--Qwen3.5-4B-4bit/snapshots/0e7ffd5c629ef7719d4cbc04069232580bfa9d9c",
    "oq4":       "models--RepublicOfKorokke--Qwen3.5-4B-oQ4/snapshots/3ae88a7d17b1c6bb71b795c1090948a82508fdb8",
    "oq4e":      "models--uingei--Qwen3.5-4B-oQ4e/snapshots/2e232d525d5df5e7a6eece4b03b17087e6b3c3ac",
    "optiq":     "models--mlx-community--Qwen3.5-4B-OptiQ-4bit/snapshots/6cb5bdfd0bf15f484881fb9f1ab6d7c840fddde9",
}
RUNTIMES = ["mlxlm", "omlx", "optiq", "vmlx", "osaurus"]
MESSAGES = [{"role": "user", "content": "Name one colour."}]

runtimes.READY_TIMEOUT_S = 180.0  # a probe, not a run: a cell that needs 15 min is a no.

out = []
for fmt, rel in FORMATS.items():
    art = os.path.join(HUB, rel)
    for name in RUNTIMES:
        rt = runtimes.RUNTIMES[name]
        row = {"format": fmt, "runtime": name}
        handle = None
        t0 = time.monotonic()
        try:
            handle = rt.start(art, f"{name}/{fmt}")
            row["load_s"] = round(handle.cold_load_s, 2)
            obs = transport.chat(handle.base_url, handle.model_id, MESSAGES,
                                 max_tokens=24, temperature=0.0, seed=0,
                                 api_key=handle.api_key)
            text = obs.text or obs.reasoning_text
            row["ok"] = bool(obs.ok)
            row["deltas"] = obs.content_event_count
            row["text"] = (text or "")[:70]
            row["coherent"] = coherence.is_coherent(text)[0] if text.strip() else None
            row["verdict"] = "LOADS" if obs.ok else f"answered: {obs.error}"
        except Exception as e:
            row["verdict"] = f"{type(e).__name__}: {e}"[:220]
        finally:
            if handle is not None:
                try: handle.stop()
                except Exception as e: row["stop_error"] = str(e)[:120]
        row["elapsed_s"] = round(time.monotonic() - t0, 1)
        out.append(row)
        print(json.dumps(row), flush=True)
json.dump(out, open(os.environ["CLAUDE_JOB_DIR"] + "/tmp/grid-probe.json", "w"), indent=1)
print("PROBEDONE", flush=True)
