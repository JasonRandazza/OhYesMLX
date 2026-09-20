#!/usr/bin/env python3
"""Plan 03-06 Probe: Native Multi-Token Prediction (MTP) in vMLX.

Evaluates decode throughput, acceptance rates, ITL distributions, prefill invariance,
memory residency, and coherence across Native MTP configurations in vMLX 1.6.59:

1. Primary Live Acceleration Study on Qwen3.5-4B-JANG_4S (verified MTP weights):
   - jang_ar_baseline: Base AR decode (--disable-native-mtp)
   - jang_mtp_d1_fixed: Fixed Depth 1 (--native-mtp-depth 1 --native-mtp-depth-policy fixed)
   - jang_mtp_d2_fixed: Fixed Depth 2 (--native-mtp-depth 2 --native-mtp-depth-policy fixed)
   - jang_mtp_d3_fixed: Fixed Depth 3 (--native-mtp-depth 3 --native-mtp-depth-policy fixed)
   - jang_mtp_d3_adaptive: Adaptive Depth 3 (--native-mtp-depth 3 --native-mtp-depth-policy adaptive)

2. Coherence Floor Diagnostic on 35B MoE (Qwen3.6-35B-A3B-oQ4-mtp vs Control):
   - moe35b_mtp_disabled: Jundot/-mtp with --disable-native-mtp
   - moe35b_mtp_enabled: Jundot/-mtp with --native-mtp-depth 1 fixed
   - moe35b_control_clean: Jundot/-oQ4 clean control

Workloads evaluated per configuration:
- Workload A (Structured Code / Low Entropy): Fibonacci memoization function in Python
- Workload B (Philosophy / High Entropy): Ship of Theseus paradox analysis
- Workload C (Technical Architecture / Medium Entropy): Apple Silicon Unified Memory explanation

Usage:
    python scripts/probe_native_mtp_35b.py [cell_name ...]
"""

from __future__ import annotations

import glob
import http.client
import json
import os
import re
import select
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ohyesmlx import coherence, runtimes, sample, token_counter, transport

# Artifact paths
HUB = os.path.expanduser("~/.cache/huggingface/hub")
JANG_4S_DIR = os.path.join(HUB, "models--JANGQ-AI--Qwen3.5-4B-JANG_4S", "snapshots")
JANG_4S_PATH = sorted(glob.glob(os.path.join(JANG_4S_DIR, "*")))[0]

MOE_MTP_PATH = os.path.join(HUB, "Jundot", "Qwen3.6-35B-A3B-oQ4-mtp")
MOE_CLEAN_DIR = os.path.join(HUB, "models--Jundot--Qwen3.6-35B-A3B-oQ4", "snapshots")
MOE_CLEAN_PATH = sorted(glob.glob(os.path.join(MOE_CLEAN_DIR, "*")))[0]

RESULTS_DIR = Path("results/plan-03-06")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
RAW_OUTPUT = RESULTS_DIR / "mtp_results.json"


def sweep_ports():
    """Ensure all harness ports are freed and stale instances killed."""
    for p in [8000, 8080, 8081, 8100, 1337]:
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


def measure_peak_memory(pid: int) -> float | None:
    """Measure peak resident footprint in MB via footprint -p <pid>."""
    try:
        out = subprocess.check_output(["footprint", "-p", str(pid)], text=True, stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            line_s = line.strip()
            if "Footprint:" in line_s or "Total footprint:" in line_s or "phys_footprint" in line_s:
                parts = line_s.split()
                for i, part in enumerate(parts):
                    if part in ("MB", "M", "MiB"):
                        return float(parts[i - 1].replace(",", ""))
                    if part in ("GB", "G", "GiB"):
                        return float(parts[i - 1].replace(",", "")) * 1024.0
    except Exception:
        pass
    try:
        out = subprocess.check_output(["ps", "-o", "rss=", "-p", str(pid)], text=True).strip()
        if out:
            return float(out) / 1024.0
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Streaming Client with ITL distribution calculation
# ---------------------------------------------------------------------------

@dataclass
class StreamingStats:
    ttft_s: float
    decode_tps: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    total_duration_s: float
    itl_p50_ms: float
    itl_p90_ms: float
    itl_p99_ms: float
    text: str
    reasoning_text: str
    coherence_status: str


def stream_completion(
    port: int,
    model_name: str,
    prompt: str,
    max_tokens: int = 128,
    temperature: float = 0.0,
    timeout_s: float = 60.0,
) -> StreamingStats:
    """Send SSE request to vMLX and record precise per-token timestamps."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout_s)
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    
    t_start = time.perf_counter()
    conn.request("POST", "/v1/chat/completions", body=body, headers=headers)
    resp = conn.getresponse()
    if resp.status != 200:
        err_msg = resp.read().decode("utf-8", errors="replace")
        conn.close()
        raise RuntimeError(f"HTTP {resp.status}: {err_msg}")
    
    content_chunks: list[str] = []
    reasoning_chunks: list[str] = []
    token_timestamps: list[float] = []
    t_first_token: float | None = None
    prompt_tokens = 0
    completion_tokens = 0
    
    buffer = ""
    while True:
        chunk = resp.read(1024)
        if not chunk:
            break
        t_now = time.perf_counter()
        buffer += chunk.decode("utf-8", errors="replace")
        lines = buffer.split("\n")
        buffer = lines.pop()  # Keep incomplete tail
        
        for line in lines:
            line = line.strip()
            if not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                continue
            try:
                data = json.loads(data_str)
            except Exception:
                continue
            
            # Check usage block
            if "usage" in data and data["usage"]:
                u = data["usage"]
                prompt_tokens = u.get("prompt_tokens", prompt_tokens)
                completion_tokens = u.get("completion_tokens", completion_tokens)
            
            choices = data.get("choices")
            if choices and len(choices) > 0:
                delta = choices[0].get("delta", {})
                c = delta.get("content")
                r = delta.get("reasoning_content")
                if c or r:
                    if t_first_token is None:
                        t_first_token = t_now
                    token_timestamps.append(t_now)
                    if c:
                        content_chunks.append(c)
                    if r:
                        reasoning_chunks.append(r)

    conn.close()
    t_end = time.perf_counter()
    total_duration_s = t_end - t_start
    ttft_s = (t_first_token - t_start) if t_first_token else total_duration_s
    
    text = "".join(content_chunks)
    reasoning_text = "".join(reasoning_chunks)
    
    # Calculate ITL distribution
    itls_ms: list[float] = []
    for i in range(1, len(token_timestamps)):
        gap_ms = (token_timestamps[i] - token_timestamps[i - 1]) * 1000.0
        itls_ms.append(gap_ms)
        
    itls_ms.sort()
    if itls_ms:
        n = len(itls_ms)
        itl_p50_ms = itls_ms[int(n * 0.50)]
        itl_p90_ms = itls_ms[min(int(n * 0.90), n - 1)]
        itl_p99_ms = itls_ms[min(int(n * 0.99), n - 1)]
    else:
        itl_p50_ms = itl_p90_ms = itl_p99_ms = 0.0
        
    # Tokens count
    gen_tokens = completion_tokens or len(token_timestamps)
    gen_time_s = max(0.001, total_duration_s - ttft_s)
    decode_tps = gen_tokens / gen_time_s if gen_tokens > 0 else 0.0
    
    # Coherence check
    full_output = text.strip() or reasoning_text.strip()
    coherent, reason = coherence.is_coherent(full_output)
    status = "PASS" if coherent else f"FAIL: {reason}"
    
    return StreamingStats(
        ttft_s=ttft_s,
        decode_tps=decode_tps,
        prompt_tokens=prompt_tokens,
        completion_tokens=gen_tokens,
        total_tokens=prompt_tokens + gen_tokens,
        total_duration_s=total_duration_s,
        itl_p50_ms=itl_p50_ms,
        itl_p90_ms=itl_p90_ms,
        itl_p99_ms=itl_p99_ms,
        text=text,
        reasoning_text=reasoning_text,
        coherence_status=status,
    )


# ---------------------------------------------------------------------------
# Server Process Manager with MTP Telemetry Parser
# ---------------------------------------------------------------------------

class VmlxServerManager:
    """Manages vMLX background instance and parses MTP stdout telemetry."""
    
    def __init__(self, artifact_path: str, extra_args: list[str], port: int = 8000):
        self.artifact_path = artifact_path
        self.extra_args = extra_args
        self.port = port
        self.proc: subprocess.Popen | None = None
        self.stdout_lines: list[str] = []
        self._reader_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        sweep_ports()
        time.sleep(1)
        cmd = [
            os.path.expanduser("~/.local/bin/vmlx"),
            "serve",
            self.artifact_path,
            "--host", "127.0.0.1",
            "--port", str(self.port),
            "--stream-interval", "1",
            "--continuous-batching",
            "--max-num-seqs", "1",
            "--no-jit",
            "--disable-prefix-cache",
            "--disable-block-disk-cache",
        ] + self.extra_args
        
        self.proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        
        self._reader_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader_thread.start()
        
        # Wait for server readiness
        start_t = time.time()
        ready = False
        while time.time() - start_t < 90:
            if self._check_health():
                ready = True
                break
            if self.proc.poll() is not None:
                raise RuntimeError(f"vMLX exited prematurely with code {self.proc.returncode}")
            time.sleep(1)
            
        if not ready:
            self.stop()
            raise RuntimeError("Timed out waiting for vMLX server ready")

    def _read_stdout(self):
        while not self._stop_event.is_set():
            line = self.proc.stdout.readline()
            if not line:
                break
            self.stdout_lines.append(line.rstrip())

    def _check_health(self) -> bool:
        try:
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=1)
            conn.request("GET", "/health")
            resp = conn.getresponse()
            conn.close()
            return resp.status == 200
        except Exception:
            return False

    def get_mtp_telemetry(self) -> dict:
        """Parse MLLM MTP log telemetry lines from vMLX stdout."""
        telemetry = {}
        for line in reversed(self.stdout_lines):
            # Example: INFO:vmlx_engine.mllm_batch_generator:MLLM MTP[chatcmpl-e1ecd701] finish=length cycles=34 accepted=28/34 (82.4%) ...
            if "MLLM MTP[" in line and "cycles=" in line:
                m_cyc = re.search(r"cycles=(\d+)", line)
                m_acc = re.search(r"accepted=(\d+)/(\d+)\s*\(([\d\.]+)%\)", line)
                m_emits = re.search(r"emits\[(.*?)\]", line)
                m_pol = re.search(r"policy=(\w+)", line)
                m_depth = re.search(r"configured=D(\d+)", line)
                m_spd = re.search(r"confirmed_tok_s=([\d\.]+)", line)
                
                if m_cyc:
                    telemetry["cycles"] = int(m_cyc.group(1))
                if m_acc:
                    telemetry["accepted_tokens"] = int(m_acc.group(1))
                    telemetry["drafted_tokens"] = int(m_acc.group(2))
                    telemetry["acceptance_rate_pct"] = float(m_acc.group(3))
                if m_pol:
                    telemetry["policy"] = m_pol.group(1)
                if m_depth:
                    telemetry["configured_depth"] = int(m_depth.group(1))
                if m_spd:
                    telemetry["confirmed_tok_s"] = float(m_spd.group(1))
                break
                
        for line in reversed(self.stdout_lines):
            if "MLLM MTP[" in line and "timings_ms[" in line:
                m_timings = re.search(r"timings_ms\[(.*?)\]", line)
                if m_timings:
                    t_str = m_timings.group(1)
                    t_dict = {}
                    for item in t_str.split():
                        if "=" in item:
                            k, v = item.split("=", 1)
                            try:
                                t_dict[k] = float(v)
                            except ValueError:
                                pass
                    telemetry["timings_ms"] = t_dict
                break
        return telemetry

    def stop(self) -> None:
        self._stop_event.set()
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        sweep_ports()


# ---------------------------------------------------------------------------
# Test Configurations Matrix
# ---------------------------------------------------------------------------

CONFIGS = [
    # 1. Primary Live Quantitative Study on Qwen3.5-4B-JANG_4S
    {
        "id": "jang_ar_baseline",
        "name": "Qwen3.5-4B-JANG_4S (Base AR Decode, No MTP)",
        "artifact": JANG_4S_PATH,
        "model_name": "qwen3.5-4b-jang_4s",
        "flags": ["--disable-native-mtp"],
    },
    {
        "id": "jang_mtp_d1_fixed",
        "name": "Qwen3.5-4B-JANG_4S (Native MTP D=1 Fixed)",
        "artifact": JANG_4S_PATH,
        "model_name": "qwen3.5-4b-jang_4s",
        "flags": [
            "--native-mtp-depth", "1",
            "--native-mtp-depth-policy", "fixed",
            "--native-mtp-sampling-policy", "greedy-only",
        ],
    },
    {
        "id": "jang_mtp_d2_fixed",
        "name": "Qwen3.5-4B-JANG_4S (Native MTP D=2 Fixed)",
        "artifact": JANG_4S_PATH,
        "model_name": "qwen3.5-4b-jang_4s",
        "flags": [
            "--native-mtp-depth", "2",
            "--native-mtp-depth-policy", "fixed",
            "--native-mtp-sampling-policy", "greedy-only",
        ],
    },
    {
        "id": "jang_mtp_d3_fixed",
        "name": "Qwen3.5-4B-JANG_4S (Native MTP D=3 Fixed)",
        "artifact": JANG_4S_PATH,
        "model_name": "qwen3.5-4b-jang_4s",
        "flags": [
            "--native-mtp-depth", "3",
            "--native-mtp-depth-policy", "fixed",
            "--native-mtp-sampling-policy", "greedy-only",
        ],
    },
    {
        "id": "jang_mtp_d3_adaptive",
        "name": "Qwen3.5-4B-JANG_4S (Native MTP D=3 Adaptive)",
        "artifact": JANG_4S_PATH,
        "model_name": "qwen3.5-4b-jang_4s",
        "flags": [
            "--native-mtp-depth", "3",
            "--native-mtp-depth-policy", "adaptive",
            "--native-mtp-sampling-policy", "greedy-only",
        ],
    },
    # 2. Coherence Floor Diagnostic on 35B MoE
    {
        "id": "moe35b_control_clean",
        "name": "Qwen3.6-35B-A3B-oQ4 (Clean Control, No MTP)",
        "artifact": MOE_CLEAN_PATH,
        "model_name": "qwen3.6-35b-a3b-oq4",
        "flags": ["--disable-native-mtp"],
    },
    {
        "id": "moe35b_mtp_disabled",
        "name": "Qwen3.6-35B-A3B-oQ4-mtp (MTP Disabled Diagnostic)",
        "artifact": MOE_MTP_PATH,
        "model_name": "qwen3.6-35b-a3b-oq4-mtp",
        "flags": ["--disable-native-mtp"],
    },
    {
        "id": "moe35b_mtp_enabled",
        "name": "Qwen3.6-35B-A3B-oQ4-mtp (MTP D=1 Enabled Diagnostic)",
        "artifact": MOE_MTP_PATH,
        "model_name": "qwen3.6-35b-a3b-oq4-mtp",
        "flags": [
            "--native-mtp-depth", "1",
            "--native-mtp-depth-policy", "fixed",
            "--native-mtp-sampling-policy", "greedy-only",
        ],
    },
]

WORKLOADS = [
    {
        "id": "workload_a_code",
        "name": "Workload A: Structured Code (Low Entropy)",
        "prompt": "Write a Python function fibonacci_memo(n: int) -> int that computes the nth Fibonacci number using recursion and an explicit dictionary memoization cache. Include docstring and type hints.",
        "max_tokens": 128,
    },
    {
        "id": "workload_b_philosophy",
        "name": "Workload B: Philosophy & Reasoning (High Entropy)",
        "prompt": "Analyze the Ship of Theseus paradox from the perspective of mereological essentialism versus four-dimensionalism (worm theory). Summarize the key metaphysical distinction.",
        "max_tokens": 128,
    },
    {
        "id": "workload_c_architecture",
        "name": "Workload C: Technical Architecture (Medium Entropy)",
        "prompt": "Explain how Apple Silicon unified memory architecture eliminates redundant PCIe transfers between the CPU and GPU during LLM decode steps.",
        "max_tokens": 128,
    },
]


def run_benchmark():
    print("=" * 80)
    print("OHYESMLX PLAN 03-06: NATIVE MULTI-TOKEN PREDICTION (MTP) IN VMLX")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Configurations: {len(CONFIGS)} | Workloads: {len(WORKLOADS)}")
    print("=" * 80)

    all_results = {}

    for cfg in CONFIGS:
        cfg_id = cfg["id"]
        cfg_name = cfg["name"]
        print(f"\n[{time.strftime('%H:%M:%S')}] >>> Starting Arm: {cfg_name} ({cfg_id})")
        
        server = VmlxServerManager(cfg["artifact"], cfg["flags"], port=8000)
        t_cold_start = time.perf_counter()
        try:
            server.start()
        except Exception as exc:
            print(f"  [ERROR] Server start failed for {cfg_id}: {exc}")
            all_results[cfg_id] = {"error": str(exc), "status": "START_FAILED"}
            continue
            
        t_cold_ready = time.perf_counter()
        cold_load_s = t_cold_ready - t_cold_start
        print(f"  [SERVER READY] Cold load time: {cold_load_s:.2f} s (PID: {server.proc.pid})")
        
        # Settle memory
        time.sleep(2)
        baseline_mem_mb = measure_peak_memory(server.proc.pid)
        print(f"  [MEMORY] Baseline resident footprint: {baseline_mem_mb} MB")

        cfg_runs = []
        for wl in WORKLOADS:
            wl_id = wl["id"]
            wl_name = wl["name"]
            print(f"    -> Running {wl_name}...")
            
            try:
                stats = stream_completion(
                    port=8000,
                    model_name=cfg["model_name"],
                    prompt=wl["prompt"],
                    max_tokens=wl["max_tokens"],
                    temperature=0.0,
                    timeout_s=90.0,
                )
                peak_mem_mb = measure_peak_memory(server.proc.pid)
                time.sleep(0.5)
                mtp_telem = server.get_mtp_telemetry()
                
                print(
                    f"       TTFT: {stats.ttft_s:.3f} s | "
                    f"Decode: {stats.decode_tps:.1f} tok/s | "
                    f"ITL P50: {stats.itl_p50_ms:.1f} ms | "
                    f"P90: {stats.itl_p90_ms:.1f} ms | "
                    f"Tokens: {stats.completion_tokens} | "
                    f"Coherence: {stats.coherence_status}"
                )
                if mtp_telem:
                    print(
                        f"       MTP Telemetry: Cycles: {mtp_telem.get('cycles')} | "
                        f"Accepted: {mtp_telem.get('accepted_tokens')}/{mtp_telem.get('drafted_tokens')} "
                        f"({mtp_telem.get('acceptance_rate_pct')}%) | "
                        f"MTP Confirmed: {mtp_telem.get('confirmed_tok_s')} tok/s"
                    )
                
                cfg_runs.append({
                    "workload_id": wl_id,
                    "workload_name": wl_name,
                    "ttft_s": stats.ttft_s,
                    "decode_tps": stats.decode_tps,
                    "prompt_tokens": stats.prompt_tokens,
                    "completion_tokens": stats.completion_tokens,
                    "total_tokens": stats.total_tokens,
                    "total_duration_s": stats.total_duration_s,
                    "itl_p50_ms": stats.itl_p50_ms,
                    "itl_p90_ms": stats.itl_p90_ms,
                    "itl_p99_ms": stats.itl_p99_ms,
                    "peak_mb": peak_mem_mb,
                    "coherence_status": stats.coherence_status,
                    "sample_text": stats.text[:200] if stats.text else stats.reasoning_text[:200],
                    "mtp_telemetry": mtp_telem,
                })
            except Exception as exc:
                print(f"       [ERROR] Workload {wl_id} failed: {exc}")
                cfg_runs.append({
                    "workload_id": wl_id,
                    "workload_name": wl_name,
                    "error": str(exc),
                    "status": "RUN_FAILED",
                })
                
        all_results[cfg_id] = {
            "name": cfg_name,
            "artifact": cfg["artifact"],
            "flags": cfg["flags"],
            "cold_load_s": cold_load_s,
            "baseline_mem_mb": baseline_mem_mb,
            "runs": cfg_runs,
        }
        
        print(f"  [STOPPING SERVER] Tearing down {cfg_id}...")
        server.stop()
        time.sleep(2)

    # Save raw results
    with open(RAW_OUTPUT, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\n[DONE] Saved complete raw results to {RAW_OUTPUT}")


if __name__ == "__main__":
    run_benchmark()
