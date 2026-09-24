"""Loadability and coherence probe for the 35B MoE matrix: Qwen3.6-35B-A3B.

Not a measurement. One short request per cell, coherence checked, then stop.
A cell that loads and answers is a live cell; anything else records the reason verbatim
so the 35B grid's holes are evidence rather than absence.

Three requirements from Phase 1 Study Design §7.3:
1. Do not lower READY_TIMEOUT_S to 180s. Keep the 900s default (35B cold loads are minutes).
2. Probe all twenty cells (5 runtimes x 4 formats), including every cell §3.2 predicts will refuse.
3. Read the verdict, not the exit code. A cell that fails the gate is recorded FAIL with its sample;
   a cell that fails to load is recorded with the runtime's own error text, verbatim.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Ensure mlx_lm venv binary is on PATH
MLX_LM_BIN = os.path.expanduser("~/.local/share/ohyesmlx/mlx-lm-0.31.3/bin")
if os.path.isdir(MLX_LM_BIN) and MLX_LM_BIN not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"{MLX_LM_BIN}:{os.environ.get('PATH', '')}"

from ohyesmlx import coherence, runtimes, transport  # noqa: E402

HUB = os.path.expanduser("~/.cache/huggingface/hub")
FORMATS = {
    "stock4bit": "models--mlx-community--Qwen3.6-35B-A3B-4bit",
    "optiq":     "models--mlx-community--Qwen3.6-35B-A3B-OptiQ-4bit",
    "oq4":       "models--Jundot--Qwen3.6-35B-A3B-oQ4",
    "jangtq4":   "models--JANGQ-AI--Qwen3.6-35B-A3B-JANGTQ4",
}
RUNTIMES = ["mlxlm", "omlx", "optiq", "vmlx", "osaurus"]
MESSAGES = [{"role": "user", "content": "Name one colour."}]

# Pinned: keep the 900s default for 35B models (do not lower to 180s)
assert runtimes.READY_TIMEOUT_S == 900.0, f"Expected READY_TIMEOUT_S=900.0, got {runtimes.READY_TIMEOUT_S}"

CONF = os.path.expanduser("~/.osaurus/config/server-runtime.json")
SERVER = os.path.expanduser("~/.osaurus/config/server.json")
CONF_ORIG = f"{CONF}.probe-35b-orig"
SERVER_ORIG = f"{SERVER}.probe-35b-orig"


def sweep_ports_and_processes() -> None:
    lsof = shutil.which("lsof") or "/usr/sbin/lsof"
    for p in (8081, 1337, 8100, 8080, 8000):
        try:
            out = subprocess.check_output([lsof, "-ti", f":{p}"], text=True)
            for line in out.strip().splitlines():
                pid = int(line)
                os.kill(pid, signal.SIGKILL)
        except Exception:
            pass
    try:
        out = subprocess.check_output(
            ["pgrep", "-f", "^/Applications/osaurus.app/Contents/MacOS/osaurus"], text=True
        )
        for line in out.strip().splitlines():
            pid = int(line)
            os.kill(pid, signal.SIGKILL)
    except Exception:
        pass
    time.sleep(1)


def osaurus_pin() -> None:
    """Pin Osaurus host settings (residency 900s, cache off) and update baseline."""
    if os.path.exists(CONF) and not os.path.exists(CONF_ORIG):
        shutil.copy2(CONF, CONF_ORIG)
    if os.path.exists(SERVER) and not os.path.exists(SERVER_ORIG):
        shutil.copy2(SERVER, SERVER_ORIG)

    if os.path.exists(CONF):
        with open(CONF) as f:
            runtime_conf = json.load(f)
        runtime_conf.setdefault("cache", {}).setdefault("prefix", {})["enabled"] = False
        runtime_conf.setdefault("cache", {}).setdefault("blockDisk", {})["enabled"] = False
        with open(CONF, "w") as f:
            json.dump(runtime_conf, f, indent=2)

    if os.path.exists(SERVER):
        with open(SERVER) as f:
            hardware = json.load(f)
        hardware.setdefault("modelIdleResidencyPolicy", {})["seconds"] = 900
        with open(SERVER, "w") as f:
            json.dump(hardware, f, indent=2)

    from ohyesmlx import osaurus_settings
    osaurus_settings.write_baseline()


def osaurus_restore() -> None:
    """Restore Osaurus host settings byte-exact and revert baseline."""
    if os.path.exists(CONF_ORIG):
        shutil.copy2(CONF_ORIG, CONF)
        os.remove(CONF_ORIG)
    if os.path.exists(SERVER_ORIG):
        shutil.copy2(SERVER_ORIG, SERVER)
        os.remove(SERVER_ORIG)
    subprocess.run(["git", "checkout", "--", "config/osaurus-settings-baseline.json"], check=False)


def resolve_artifact(fmt: str, repo_or_dir: str) -> str | None:
    # 1. Standard hub snapshots layout
    root = os.path.join(HUB, repo_or_dir, "snapshots")
    if os.path.isdir(root):
        entries = sorted(os.listdir(root))
        if entries:
            snap = os.path.join(root, entries[0])
            if os.path.isfile(os.path.join(snap, "config.json")):
                return snap
    # 2. Check if OptiQ exists in flat layout
    if fmt == "optiq":
        flat_optiq = os.path.join(HUB, "mlx-community", "Qwen3.6-35B-A3B-OptiQ-4bit")
        if os.path.isdir(flat_optiq) and os.path.isfile(os.path.join(flat_optiq, "config.json")):
            return flat_optiq
    # 3. Direct directory check under HUB
    flat = os.path.join(HUB, repo_or_dir)
    if os.path.isdir(flat) and os.path.isfile(os.path.join(flat, "config.json")):
        return flat
    return None


def main() -> None:
    sweep_ports_and_processes()
    out = []
    try:
        for fmt, repo in FORMATS.items():
            art = resolve_artifact(fmt, repo)
            if art is None:
                row = {"format": fmt, "verdict": f"not in cache: {repo}"}
                print(json.dumps(row), flush=True)
                out.append(row)
                continue

            for name in RUNTIMES:
                sweep_ports_and_processes()
                row = {"format": fmt, "runtime": name}
                handle = None
                started = time.monotonic()
                try:
                    if name == "osaurus":
                        osaurus_pin()
                    rt = runtimes.RUNTIMES[name]
                    handle = rt.start(art, f"{fmt}__{name}")
                    row["load_s"] = round(handle.cold_load_s, 2)
                    obs = transport.chat(
                        handle.base_url,
                        handle.model_id,
                        MESSAGES,
                        max_tokens=24,
                        temperature=0.0,
                        seed=0,
                        api_key=handle.api_key,
                        timeout_s=120.0,
                    )
                    text = obs.text or obs.reasoning_text or ""
                    row["ok"] = bool(obs.ok)
                    row["deltas"] = obs.content_event_count
                    row["text"] = text  # whole: the sample is what audits the verdict
                    if text.strip():
                        coh_ok, coh_reason = coherence.is_coherent(text)
                        row["coherent"] = coh_ok
                        if not coh_ok:
                            row["coherence_reason"] = coh_reason
                    else:
                        row["coherent"] = False
                        row["coherence_reason"] = "no content or reasoning"

                    if not obs.ok:
                        row["verdict"] = f"answered: {obs.error}"
                    elif not row.get("coherent", True):
                        row["verdict"] = f"FAIL (incoherent: {row.get('coherence_reason')})"
                    else:
                        row["verdict"] = "LOADS"
                except Exception as error:  # noqa: BLE001
                    row["verdict"] = f"{type(error).__name__}: {error}"[:220]
                finally:
                    if handle is not None:
                        try:
                            handle.stop()
                        except Exception as error:  # noqa: BLE001
                            row["stop_error"] = str(error)[:120]
                    if name == "osaurus":
                        sweep_ports_and_processes()
                        osaurus_restore()
                    sweep_ports_and_processes()

                row["elapsed_s"] = round(time.monotonic() - started, 1)
                out.append(row)
                print(json.dumps(row), flush=True)
    finally:
        sweep_ports_and_processes()
        osaurus_restore()

    print("PROBEDONE", flush=True)


if __name__ == "__main__":
    main()
