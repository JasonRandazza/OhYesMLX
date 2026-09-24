#!/usr/bin/env python3
"""Plan 03-05 Probe: Quantized KV Caches (FP8, INT4 vs FP16 at 16k and 32k Context).

Evaluates unified memory savings, TTFT/prefill overhead, decode throughput,
and output coherence across KV cache quantization formats:
1. OptiQ FP16 Baseline: --max-context off
2. OptiQ FP8 (8-bit): --max-context off --kv-bits 8
3. OptiQ INT4 (4-bit): --max-context off --kv-bits 4
4. vMLX FP16 Baseline: --kv-cache-quantization none --no-jit
5. vMLX FP8 (q8): --kv-cache-quantization q8 --no-jit
6. vMLX INT4 (q4): --kv-cache-quantization q4 --no-jit
7. mlx-lm FP16 Control: stock mlx_lm.server

Context lengths evaluated per configuration:
- 16,384 tokens
- 32,768 tokens

Subject Model:
    brainworkup/Llama-3.1-8B-oQ4 (4.60 GB safetensors, 128k context)

Usage:
    python scripts/probe_kv_quant.py [cell_name ...]
"""

from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ohyesmlx import cli, coherence, runtimes, sample, token_counter, transport

# Model configuration
HUB = os.path.expanduser("~/.cache/huggingface/hub")
MODEL_DIR = os.path.join(HUB, "models--brainworkup--Llama-3.1-8B-oQ4", "snapshots")
SNAP_DIRS = glob.glob(os.path.join(MODEL_DIR, "*"))
if not SNAP_DIRS:
    print(f"ERROR: No snapshot found in {MODEL_DIR}", file=sys.stderr)
    sys.exit(1)
ARTIFACT = sorted(SNAP_DIRS)[0]


def sweep_ports():
    """Ensure all harness ports are freed and stale instances killed."""
    for p in [8081, 1337, 8100, 8080, 8000]:
        try:
            out = subprocess.check_output(["lsof", f"-ti:{p}"], text=True).strip()
            for pid in out.split():
                if pid:
                    subprocess.run(["kill", "-9", pid], capture_output=True)
        except Exception:
            pass
    try:
        out = subprocess.check_output(
            ["pgrep", "-f", "^/Applications/osaurus.app/Contents/MacOS/osaurus"], text=True
        ).strip()
        for pid in out.split():
            if pid:
                subprocess.run(["kill", "-9", pid], capture_output=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Specialized Runtime Classes for Plan 03-05
# ---------------------------------------------------------------------------

class OptiqFP16(runtimes.Optiq):
    """OptiQ with standard FP16 KV cache (unquantized baseline)."""
    def __init__(self):
        super().__init__(name="optiq", port=8080)


class OptiqFP8(runtimes.Optiq):
    """OptiQ with 8-bit quantized KV cache."""
    def __init__(self):
        super().__init__(name="optiq", port=8080)

    def start_command(
        self, artifact_dir: str, model_id: str, *, cache_state: str | None = None,
        kv_quant: str | None = None,
    ) -> tuple[str, ...]:
        cmd = list(super().start_command(artifact_dir, model_id, cache_state=cache_state))
        cmd.extend(["--kv-bits", "8"])
        return tuple(cmd)


class OptiqINT4(runtimes.Optiq):
    """OptiQ with 4-bit quantized KV cache."""
    def __init__(self):
        super().__init__(name="optiq", port=8080)

    def start_command(
        self, artifact_dir: str, model_id: str, *, cache_state: str | None = None,
        kv_quant: str | None = None,
    ) -> tuple[str, ...]:
        cmd = list(super().start_command(artifact_dir, model_id, cache_state=cache_state))
        cmd.extend(["--kv-bits", "4"])
        return tuple(cmd)


class VmlxFP16(runtimes.Vmlx):
    """vMLX with unquantized FP16 KV cache."""
    def __init__(self):
        super().__init__(name="vmlx", port=8000)

    def start_command(
        self, artifact_dir: str, model_id: str, *, cache_state: str | None = None,
        kv_quant: str | None = None,
    ) -> tuple[str, ...]:
        cmd = list(super().start_command(artifact_dir, model_id, cache_state=cache_state))
        cmd.extend(["--kv-cache-quantization", "none"])
        return tuple(cmd)


class VmlxFP8(runtimes.Vmlx):
    """vMLX with 8-bit quantized KV cache (q8)."""
    def __init__(self):
        super().__init__(name="vmlx", port=8000)

    def start_command(
        self, artifact_dir: str, model_id: str, *, cache_state: str | None = None,
        kv_quant: str | None = None,
    ) -> tuple[str, ...]:
        cmd = list(super().start_command(artifact_dir, model_id, cache_state=cache_state))
        cmd.extend(["--kv-cache-quantization", "q8"])
        return tuple(cmd)


class VmlxINT4(runtimes.Vmlx):
    """vMLX with 4-bit quantized KV cache (q4)."""
    def __init__(self):
        super().__init__(name="vmlx", port=8000)

    def start_command(
        self, artifact_dir: str, model_id: str, *, cache_state: str | None = None,
        kv_quant: str | None = None,
    ) -> tuple[str, ...]:
        cmd = list(super().start_command(artifact_dir, model_id, cache_state=cache_state))
        cmd.extend(["--kv-cache-quantization", "q4"])
        return tuple(cmd)


class MlxlmFP16(runtimes.MlxLm):
    """mlx_lm.server canonical FP16 control reference."""
    def __init__(self):
        super().__init__(name="mlxlm", port=8081)


CELL_CONFIGS = [
    ("optiq_fp16", OptiqFP16, "OptiQ FP16 Baseline", "FP16"),
    ("optiq_fp8", OptiqFP8, "OptiQ FP8 (--kv-bits 8)", "FP8"),
    ("optiq_int4", OptiqINT4, "OptiQ INT4 (--kv-bits 4)", "INT4"),
    ("vmlx_fp16", VmlxFP16, "vMLX FP16 Baseline", "FP16"),
    ("vmlx_fp8", VmlxFP8, "vMLX FP8 (--kv-cache-quantization q8)", "FP8"),
    ("vmlx_int4", VmlxINT4, "vMLX INT4 (--kv-cache-quantization q4)", "INT4"),
    ("mlxlm_fp16", MlxlmFP16, "mlx-lm FP16 Control Reference", "FP16"),
]


def run_cell_benchmarks(
    cell_name: str,
    cls: type,
    desc: str,
    kv_prec: str,
    prompts: dict[str, tuple[str, int]],
    counter: token_counter.TokenCounter,
) -> dict:
    print(f"\n{'='*75}")
    print(f"BENCHMARKING CELL: {cell_name} [{kv_prec}]")
    print(f"Description: {desc}")
    print(f"Model: {ARTIFACT}")
    print(f"{'='*75}")

    sweep_ports()
    rt = cls()

    result = {
        "cell": cell_name,
        "runtime": rt.name,
        "kv_precision": kv_prec,
        "description": desc,
        "model": "Llama-3.1-8B-oQ4",
        "artifact_dir": ARTIFACT,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "runs": {},
    }

    handle = None
    try:
        print(f"--> Starting server for {cell_name}...")
        handle = rt.start(ARTIFACT, f"{cell_name}/Llama-3.1-8B-oQ4")
        cold_load_s = round(handle.cold_load_s, 2)
        pid = handle.memory_pid
        result["cold_load_s"] = cold_load_s
        result["pid"] = pid
        print(f"    Startup / readiness time: {cold_load_s}s (PID: {pid})")

        idle_footprint = sample.phys_footprint_mb(pid)
        result["idle_phys_footprint_mb"] = idle_footprint
        print(f"    Initial idle phys_footprint: {idle_footprint} MB")

        for ctx_label in ["16k", "32k"]:
            prompt_text, achieved_tokens = prompts[ctx_label]
            print(f"\n--> Running context length {ctx_label} ({achieved_tokens} tokens)...")

            messages = [{"role": "user", "content": prompt_text}]

            obs = transport.chat(
                handle.base_url,
                handle.model_id,
                messages,
                max_tokens=64,
                temperature=0.0,
                seed=0,
                token_counter=counter,
                api_key=handle.api_key,
            )

            ttft_s = round(obs.ttft_s or 0.0, 3)
            tokens = obs.completion_tokens or 0
            prompt_toks = obs.prompt_tokens or achieved_tokens
            total_s = round(obs.total_s, 3)

            decode_time = (
                round(obs.last_content_s - obs.ttft_s, 3)
                if (obs.last_content_s and obs.ttft_s)
                else 0.0
            )
            decode_tps = (
                round((tokens - 1) / decode_time, 2)
                if (decode_time > 0 and tokens > 1)
                else 0.0
            )
            itl_ms = (
                round((decode_time / (tokens - 1)) * 1000.0, 2)
                if (decode_time > 0 and tokens > 1)
                else 0.0
            )

            peak_footprint = sample.phys_footprint_mb(pid)
            output_text = obs.text.strip() if obs.text.strip() else obs.reasoning_text.strip()
            coherent, reason = coherence.is_coherent(output_text)

            run_data = {
                "context_label": ctx_label,
                "achieved_prompt_tokens": prompt_toks,
                "completion_tokens": tokens,
                "ttft_s": ttft_s,
                "prefill_tps": round(prompt_toks / ttft_s, 1) if ttft_s > 0 else 0.0,
                "decode_time_s": decode_time,
                "decode_tps": decode_tps,
                "itl_ms": itl_ms,
                "total_s": total_s,
                "peak_phys_footprint_mb": peak_footprint,
                "coherent": coherent,
                "coherence_reason": reason,
                "response_sample": output_text[:140],
            }
            result["runs"][ctx_label] = run_data

            print(f"    Prompt Tokens   : {prompt_toks}")
            print(f"    Completion Toks : {tokens} in {total_s}s")
            print(f"    TTFT            : {ttft_s}s (Prefill: {run_data['prefill_tps']} tok/s)")
            print(f"    Decode Rate     : {decode_tps} tok/s (ITL: {itl_ms} ms/tok)")
            print(f"    Peak Footprint  : {peak_footprint} MB")
            print(f"    Coherence       : {'PASS' if coherent else 'FAIL'} ({reason})")
            print(f"    Sample Output   : {output_text[:80]}...")

    except Exception as e:
        print(f"ERROR executing cell {cell_name}: {type(e).__name__}: {e}", file=sys.stderr)
        result["error"] = f"{type(e).__name__}: {e}"

    finally:
        if handle is not None:
            try:
                handle.stop()
            except Exception:
                pass
        sweep_ports()

    return result


def main():
    out_dir = Path("results/plan-03-05")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "kv_quant_results.json"

    selected_cells = sys.argv[1:] if len(sys.argv) > 1 else [c[0] for c in CELL_CONFIGS]
    cells_to_run = [c for c in CELL_CONFIGS if c[0] in selected_cells]

    print("===========================================================================")
    print("PLAN 03-05: QUANTIZED KV CACHES BENCHMARK (FP8, INT4 VS FP16)")
    print(f"Model: {ARTIFACT}")
    print(f"Cells to evaluate: {[c[0] for c in cells_to_run]}")
    print("===========================================================================")

    print("--> Preparing sized prompts from longtext.md...")
    counter = token_counter.TokenCounter(ARTIFACT)
    p16, a16 = cli.sized_prompt(counter, 16384)
    p32, a32 = cli.sized_prompt(counter, 32768)
    prompts = {
        "16k": (p16, a16),
        "32k": (p32, a32),
    }
    print(f"    16k Prompt: {a16} tokens")
    print(f"    32k Prompt: {a32} tokens")

    all_results = []
    if out_file.exists():
        try:
            all_results = json.loads(out_file.read_text("utf-8"))
        except Exception:
            all_results = []

    completed_cell_names = {r.get("cell") for r in all_results if "runs" in r and "32k" in r["runs"]}

    for cell_name, cls, desc, prec in cells_to_run:
        if cell_name in completed_cell_names:
            print(f"Cell {cell_name} already completed. Skipping (remove results file to rerun).")
            continue

        res = run_cell_benchmarks(cell_name, cls, desc, prec, prompts, counter)
        all_results = [r for r in all_results if r.get("cell") != cell_name] + [res]
        out_file.write_text(json.dumps(all_results, indent=2), "utf-8")

        print("--> Cooling down 10s between cells...")
        time.sleep(10.0)

    print(f"\nKV cache quantization benchmark complete. Evidence saved to {out_file}")


if __name__ == "__main__":
    main()
