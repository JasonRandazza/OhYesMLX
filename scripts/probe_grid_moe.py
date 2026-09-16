"""Loadability probe for the MoE column: which (format, runtime) cells can run at all.

Not a measurement. One short request per cell, coherence checked, then stop. A cell that
loads and answers is a live cell; anything else records the reason verbatim so the MoE grid's
holes are evidence rather than absence.

Same shape as probe_grid.py, which did this for the dense model. Worth the twenty minutes
before a 2.5-hour grid: the dense probe is what established that every runtime advertises
models it cannot serve, so readiness is not the port and not the model list either.

STANDING CAVEAT: LFM2.5-8B-A1B has 32 experts. The checkpoint stock mlx-lm turns into token
salad has 256. A clean result here validates the machinery on MoE and exonerates nothing.
"""
import json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ohyesmlx import coherence, runtimes, transport  # noqa: E402

HUB = os.path.expanduser("~/.cache/huggingface/hub")
FORMATS = {
    "stock4bit": "models--mlx-community--LFM2.5-8B-A1B-MLX-4bit",
    "oq4":       "models--stamsam--LFM2.5-8B-A1B-oQ4",
    "oq4e":      "models--brainworkup--LFM2.5-8B-A1B-oQ4e",
    "optiq":     "models--mlx-community--LFM2.5-8B-A1B-OptiQ-4bit",
    "jang2l":    "models--JANGQ-AI--LFM2.5-8B-A1B-JANG_2L",
}
RUNTIMES = ["mlxlm", "omlx", "optiq", "vmlx", "osaurus"]
MESSAGES = [{"role": "user", "content": "Name one colour."}]

runtimes.READY_TIMEOUT_S = 180.0  # a probe, not a run: a cell that needs 15 min is a no.


def snapshot(repo_dir: str) -> str | None:
    root = os.path.join(HUB, repo_dir, "snapshots")
    if not os.path.isdir(root):
        return None
    entries = sorted(os.listdir(root))
    return os.path.join(root, entries[0]) if entries else None


out = []
for fmt, repo in FORMATS.items():
    art = snapshot(repo)
    if art is None:
        print(json.dumps({"format": fmt, "verdict": f"not in cache: {repo}"}), flush=True)
        continue
    for name in RUNTIMES:
        rt = runtimes.RUNTIMES[name]
        row = {"format": fmt, "runtime": name}
        handle = None
        started = time.monotonic()
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
        except Exception as error:  # noqa: BLE001 - a cell that cannot run is the result
            row["verdict"] = f"{type(error).__name__}: {error}"[:220]
        finally:
            if handle is not None:
                try:
                    handle.stop()
                except Exception as error:  # noqa: BLE001
                    row["stop_error"] = str(error)[:120]
        row["elapsed_s"] = round(time.monotonic() - started, 1)
        out.append(row)
        print(json.dumps(row), flush=True)
print("PROBEDONE", flush=True)
