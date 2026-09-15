"""Does cold_load_s mean the same thing in every runtime?

A runtime that loads weights at startup pays for it before readiness. One that loads lazily
on first request pays inside request #1, where it lands in that request's TTFT and vanishes
from every later one. Same column name, two different quantities.

Three requests per runtime, no warmups, timing each. A first-request penalty that disappears
is the signature of a lazy loader.
"""
import json, os, sys, time
sys.path.insert(0, "/Users/jrazz/Dev/active/OhYesMLX")
from ohyesmlx import runtimes, transport
ART = os.path.expanduser("~/.cache/huggingface/hub/models--RepublicOfKorokke--Qwen3.5-4B-oQ4/"
                         "snapshots/3ae88a7d17b1c6bb71b795c1090948a82508fdb8")
runtimes.READY_TIMEOUT_S = 180.0
M = [{"role": "user", "content": "Name one colour."}]
for name in ["mlxlm", "omlx", "optiq", "vmlx"]:
    rt = runtimes.RUNTIMES[name]; handle = None
    row = {"runtime": name}
    try:
        handle = rt.start(ART, f"{name}/oq4")
        row["cold_load_s"] = round(handle.cold_load_s, 2)
        lat = []
        for i in range(3):
            t = time.monotonic()
            o = transport.chat(handle.base_url, handle.model_id, M, max_tokens=16,
                               temperature=0.0, seed=0, api_key=handle.api_key)
            lat.append(round(time.monotonic() - t, 2))
        row["request_s"] = lat
        row["first_minus_rest"] = round(lat[0] - min(lat[1:]), 2)
    except Exception as e:
        row["error"] = f"{type(e).__name__}: {e}"[:150]
    finally:
        if handle is not None:
            try: handle.stop()
            except Exception: pass
    print(json.dumps(row), flush=True)
print("LAZYDONE", flush=True)
