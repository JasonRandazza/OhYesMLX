#!/usr/bin/env python3
"""Plan 03-03 Probe: Expert Streaming under High Memory Pressure on 35B MoE.

Compares Resident Serving vs SSD Expert Streaming vs Cached Streaming vs Smelt:
1. OptiQ Resident Baseline: --max-context off --no-stream-experts
2. OptiQ SSD Streaming: --max-context off --stream-experts
3. OptiQ Streaming + LRU Cache: --max-context off --stream-experts --stream-experts-cache 64
4. vMLX Resident Baseline: --no-jit --disable-native-mtp
5. vMLX FlashMoE Streaming: --no-jit --disable-native-mtp --flash-moe --flash-moe-slot-bank 64
6. vMLX Smelt Partial Loading: --no-jit --disable-native-mtp --smelt --smelt-experts 50

Measures:
- Cold startup / readiness latency (s)
- Idle and peak physical footprint (footprint -p <pid>)
- vmmap memory distribution (IOAccelerator graphics vs anonymous vs mapped-file)
- TTFT, decode throughput (tok/s), prefill throughput (tok/s) across Request 1 & 2
- Text completion sample and coherence floor verification

Usage:
    python scripts/probe_expert_streaming_35b.py [cell_name ...]
"""

from __future__ import annotations

import collections
import contextlib
import glob
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ohyesmlx import coherence, runtimes, sample, token_counter, transport

# Model configuration
HUB = os.path.expanduser("~/.cache/huggingface/hub")
MODEL_DIR = os.path.join(HUB, "models--mlx-community--Qwen3.6-35B-A3B-4bit", "snapshots")
SNAP_DIRS = glob.glob(os.path.join(MODEL_DIR, "*"))
if not SNAP_DIRS:
    print(f"ERROR: No snapshot found in {MODEL_DIR}", file=sys.stderr)
    sys.exit(1)
ARTIFACT = sorted(SNAP_DIRS)[0]

PROMPT = [
    {
        "role": "user",
        "content": "Explain the architecture of Mixture of Experts (MoE) neural networks in 50 words.",
    }
]

_REGION = re.compile(
    r"^(?P<kind>.+?)\s+([0-9a-f]+)-([0-9a-f]+)\s+\[\s*(?P<vsize>\S+)\s+(?P<rsdnt>\S+)\s+"
    r"(?P<dirty>\S+)\s+(?P<swap>\S+)\s*\]",
    re.IGNORECASE,
)


def sample_regions(pid: int) -> dict:
    """Analyze memory region distribution of the target process via vmmap."""
    try:
        proc = subprocess.run(
            [sample.VMMAP, str(pid)], capture_output=True, text=True, timeout=60
        )
        if proc.returncode != 0:
            return {"error": f"vmmap exited {proc.returncode}"}
    except Exception as e:
        return {"error": str(e)}

    totals = collections.defaultdict(lambda: [0.0, 0.0])
    for line in proc.stdout.splitlines():
        m = _REGION.match(line)
        if m:
            kind = m.group("kind").strip()
            rsdnt = sample.parse_mb(m.group("rsdnt")) or 0.0
            dirty = sample.parse_mb(m.group("dirty")) or 0.0
            totals[kind][0] += rsdnt
            totals[kind][1] += dirty

    breakdown = []
    for kind, (r, d) in sorted(totals.items(), key=lambda x: -x[1][0]):
        breakdown.append({"kind": kind, "resident_mb": round(r, 1), "dirty_mb": round(d, 1)})

    ioaccel_res = totals.get("IOAccelerator", [0.0, 0.0])[0]
    mapped_res = sum(v[0] for k, v in totals.items() if "mapped file" in k.lower())
    anon_res = sum(
        v[0]
        for k, v in totals.items()
        if "mapped file" not in k.lower() and "ioaccelerator" not in k.lower()
    )

    return {
        "ioaccelerator_resident_mb": round(ioaccel_res, 1),
        "mapped_file_resident_mb": round(mapped_res, 1),
        "anonymous_resident_mb": round(anon_res, 1),
        "top_regions": breakdown[:8],
    }


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
# Specialized Runtime Classes for Plan 03-03
# ---------------------------------------------------------------------------

class OptiqResident(runtimes.Optiq):
    """OptiQ with expert streaming forced OFF (resident control)."""

    def __init__(self):
        super().__init__(name="optiq", port=8080)

    def start_command(
        self, artifact_dir: str, model_id: str, *, cache_state: str | None = None,
        kv_quant: str | None = None, mtp_depth: str | None = None,
        stream_experts: str | None = None,
    ) -> tuple[str, ...]:
        cmd = list(super().start_command(artifact_dir, model_id, cache_state=cache_state,
                                         mtp_depth=mtp_depth,
                                         stream_experts=stream_experts))
        if "--no-stream-experts" not in cmd:
            cmd.append("--no-stream-experts")
        return tuple(cmd)


class OptiqStreaming(runtimes.Optiq):
    """OptiQ with SSD expert streaming forced ON."""

    def __init__(self):
        super().__init__(name="optiq", port=8080)

    def start_command(
        self, artifact_dir: str, model_id: str, *, cache_state: str | None = None,
        kv_quant: str | None = None, mtp_depth: str | None = None,
        stream_experts: str | None = None,
    ) -> tuple[str, ...]:
        cmd = list(super().start_command(artifact_dir, model_id, cache_state=cache_state,
                                         mtp_depth=mtp_depth,
                                         stream_experts=stream_experts))
        if "--no-stream-experts" in cmd:
            cmd.remove("--no-stream-experts")
        cmd.append("--stream-experts")
        return tuple(cmd)


class OptiqStreamingCached(runtimes.Optiq):
    """OptiQ with SSD expert streaming forced ON + 64-slot in-RAM LRU cache."""

    def __init__(self):
        super().__init__(name="optiq", port=8080)

    def start_command(
        self, artifact_dir: str, model_id: str, *, cache_state: str | None = None,
        kv_quant: str | None = None, mtp_depth: str | None = None,
        stream_experts: str | None = None,
    ) -> tuple[str, ...]:
        cmd = list(super().start_command(artifact_dir, model_id, cache_state=cache_state,
                                         mtp_depth=mtp_depth,
                                         stream_experts=stream_experts))
        if "--no-stream-experts" in cmd:
            cmd.remove("--no-stream-experts")
        cmd.extend(["--stream-experts", "--stream-experts-cache", "64"])
        return tuple(cmd)


class VmlxResident(runtimes.Vmlx):
    """vMLX resident control (--no-jit --disable-native-mtp)."""

    def __init__(self):
        super().__init__(name="vmlx", port=8000)


class VmlxFlashMoE(runtimes.Vmlx):
    """vMLX dynamic SSD streaming via FlashMoE."""

    def __init__(self):
        super().__init__(name="vmlx", port=8000)

    def start_command(
        self, artifact_dir: str, model_id: str, *, cache_state: str | None = None,
        kv_quant: str | None = None, mtp_depth: str | None = None,
        stream_experts: str | None = None,
    ) -> tuple[str, ...]:
        cmd = list(super().start_command(artifact_dir, model_id, cache_state=cache_state,
                                         mtp_depth=mtp_depth,
                                         stream_experts=stream_experts))
        cmd.extend(["--flash-moe", "--flash-moe-slot-bank", "64"])
        return tuple(cmd)


class VmlxSmelt(runtimes.Vmlx):
    """vMLX static partial expert loading (Smelt 50%)."""

    def __init__(self):
        super().__init__(name="vmlx", port=8000)

    def start_command(
        self, artifact_dir: str, model_id: str, *, cache_state: str | None = None,
        kv_quant: str | None = None, mtp_depth: str | None = None,
        stream_experts: str | None = None,
    ) -> tuple[str, ...]:
        cmd = list(super().start_command(artifact_dir, model_id, cache_state=cache_state,
                                         mtp_depth=mtp_depth,
                                         stream_experts=stream_experts))
        cmd.extend(["--smelt", "--smelt-experts", "50"])
        return tuple(cmd)


CELL_CONFIGS = [
    ("optiq_resident", OptiqResident, "OptiQ Resident Baseline (--no-stream-experts)"),
    ("optiq_stream", OptiqStreaming, "OptiQ SSD Streaming (--stream-experts)"),
    ("optiq_stream_cached", OptiqStreamingCached, "OptiQ Streaming + LRU Cache 64 (--stream-experts-cache 64)"),
    ("vmlx_resident", VmlxResident, "vMLX Resident Baseline (--no-jit --disable-native-mtp)"),
    ("vmlx_flash_moe", VmlxFlashMoE, "vMLX FlashMoE Streaming (--flash-moe --flash-moe-slot-bank 64)"),
    ("vmlx_smelt", VmlxSmelt, "vMLX Smelt Partial Load (--smelt --smelt-experts 50)"),
]


def run_cell(name: str, runtime_cls: type, desc: str) -> dict:
    print(f"\n{'='*70}")
    print(f"RUNNING CELL: {name}")
    print(f"Description: {desc}")
    print(f"{'='*70}")

    sweep_ports()
    rt = runtime_cls()
    counter = token_counter.TokenCounter(ARTIFACT)

    result = {
        "cell": name,
        "description": desc,
        "runtime": rt.name,
        "model": "Qwen3.6-35B-A3B-4bit",
        "artifact_dir": ARTIFACT,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    handle = None
    try:
        t_start = time.monotonic()
        print(f"--> Starting server for {name}...")
        handle = rt.start(ARTIFACT, f"{name}/Qwen3.6-35B-A3B-4bit")
        cold_load_s = round(handle.cold_load_s, 2)
        result["cold_load_s"] = cold_load_s
        pid = handle.memory_pid
        result["memory_pid"] = pid
        print(f"    Startup / readiness time: {cold_load_s}s (PID: {pid})")

        # Initial memory sampling (idle state)
        idle_footprint = sample.phys_footprint_mb(pid)
        idle_regions = sample_regions(pid)
        result["idle_phys_footprint_mb"] = idle_footprint
        result["idle_ioaccelerator_mb"] = idle_regions.get("ioaccelerator_resident_mb")
        result["idle_regions"] = idle_regions
        print(f"    Idle phys_footprint    : {idle_footprint} MB")
        print(f"    Idle IOAccelerator     : {idle_regions.get('ioaccelerator_resident_mb')} MB")

        # Request #1: Cold generation (testing expert fetch on prompt + decode)
        print(f"--> Sending Request #1 (max_tokens=64, greedy)...")
        obs1 = transport.chat(
            handle.base_url,
            handle.model_id,
            PROMPT,
            max_tokens=64,
            temperature=0.0,
            seed=0,
            token_counter=counter,
            api_key=handle.api_key,
        )

        r1_ttft = round(obs1.ttft_s or 0.0, 3)
        r1_tokens = obs1.completion_tokens or 0
        r1_total = round(obs1.total_s, 3)
        r1_decode_time = (
            round(obs1.last_content_s - obs1.ttft_s, 3)
            if (obs1.last_content_s and obs1.ttft_s)
            else 0.0
        )
        r1_decode_tps = (
            round((r1_tokens - 1) / r1_decode_time, 2)
            if (r1_decode_time > 0 and r1_tokens > 1)
            else 0.0
        )
        r1_coherent, r1_reason = coherence.is_coherent(obs1.text)

        result["request_1"] = {
            "ok": obs1.ok,
            "error": obs1.error,
            "ttft_s": r1_ttft,
            "decode_time_s": r1_decode_time,
            "decode_tps": r1_decode_tps,
            "completion_tokens": r1_tokens,
            "total_s": r1_total,
            "coherent": r1_coherent,
            "coherence_reason": r1_reason,
            "text_sample": obs1.text.strip()[:200],
        }

        print(f"    Request #1 TTFT        : {r1_ttft}s")
        print(f"    Request #1 Decode TPS  : {r1_decode_tps} tok/s ({r1_tokens} tokens in {r1_decode_time}s)")
        print(f"    Request #1 Coherence   : {'PASS' if r1_coherent else 'FAIL'} ({r1_reason})")
        print(f"    Sample Output          : {obs1.text.strip()[:100]}...")

        # Peak memory sampling
        peak_footprint = sample.phys_footprint_mb(pid)
        peak_regions = sample_regions(pid)
        result["peak_phys_footprint_mb"] = peak_footprint
        result["peak_ioaccelerator_mb"] = peak_regions.get("ioaccelerator_resident_mb")
        result["peak_regions"] = peak_regions
        print(f"    Peak phys_footprint    : {peak_footprint} MB")
        print(f"    Peak IOAccelerator     : {peak_regions.get('ioaccelerator_resident_mb')} MB")

        # Request #2: Warm generation (testing cache hit rate / steady-state)
        print(f"--> Sending Request #2 (warm steady-state check)...")
        obs2 = transport.chat(
            handle.base_url,
            handle.model_id,
            PROMPT,
            max_tokens=64,
            temperature=0.0,
            seed=0,
            token_counter=counter,
            api_key=handle.api_key,
        )

        r2_ttft = round(obs2.ttft_s or 0.0, 3)
        r2_tokens = obs2.completion_tokens or 0
        r2_total = round(obs2.total_s, 3)
        r2_decode_time = (
            round(obs2.last_content_s - obs2.ttft_s, 3)
            if (obs2.last_content_s and obs2.ttft_s)
            else 0.0
        )
        r2_decode_tps = (
            round((r2_tokens - 1) / r2_decode_time, 2)
            if (r2_decode_time > 0 and r2_tokens > 1)
            else 0.0
        )

        result["request_2"] = {
            "ok": obs2.ok,
            "error": obs2.error,
            "ttft_s": r2_ttft,
            "decode_time_s": r2_decode_time,
            "decode_tps": r2_decode_tps,
            "completion_tokens": r2_tokens,
            "total_s": r2_total,
        }

        print(f"    Request #2 TTFT        : {r2_ttft}s")
        print(f"    Request #2 Decode TPS  : {r2_decode_tps} tok/s")

    except Exception as e:
        print(f"ERROR executing cell {name}: {type(e).__name__}: {e}")
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
    out_dir = Path("results/plan-03-03")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "streaming_results.json"

    filter_cells = sys.argv[1:]
    cells_to_run = (
        [c for c in CELL_CONFIGS if c[0] in filter_cells]
        if filter_cells
        else CELL_CONFIGS
    )

    print("========================================================================")
    print("PLAN 03-03: EXPERT STREAMING UNDER HIGH MEMORY PRESSURE (35B MoE)")
    print(f"Model: {ARTIFACT}")
    print(f"Cells to evaluate: {[c[0] for c in cells_to_run]}")
    print("========================================================================")

    all_results = []
    for name, cls, desc in cells_to_run:
        res = run_cell(name, cls, desc)
        all_results.append(res)
        out_file.write_text(json.dumps(all_results, indent=2), "utf-8")
        print("--> Cooling down 10s...")
        time.sleep(10.0)

    print(f"\nBenchmark complete. Results saved to {out_file}")


if __name__ == "__main__":
    main()
