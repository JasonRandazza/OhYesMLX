#!/usr/bin/env python3
"""Plan 03-04 Probe: Multi-Turn Conversation Sweep (1 to 10 Turns) on 35B MoE.

Quantifies turn-by-turn conversational dynamics on Apple Silicon:
- Time to First Content Token (TTFT) across accumulating dialogue history (1 to 10 turns)
- Prefix-cache retention and reuse speedup (flat TTFT vs linear prefill scaling)
- Inter-Token Latency (ITL / TPOT) and Decode Throughput (tok/s) stability
- Process physical memory footprint (phys_footprint_mb) trajectory
- Conversational consistency and output coherence across all turns

Subject Model:
    mlx-community/Qwen3.6-35B-A3B-4bit (19.03 GiB safetensors)

Candidate Runtimes:
    - mlxlm (mlx_lm.server 0.31.3)
    - omlx (oMLX 0.6.4)
    - osaurus (Osaurus 0.25.5)
    - vmlx (vMLX 1.6.59)
    - optiq (mlx-optiq 0.5.6)

Usage:
    python scripts/probe_multiturn_sweep.py [runtime_name ...]
"""

from __future__ import annotations

import contextlib
import glob
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ohyesmlx import coherence, osaurus_settings, runtimes, sample, token_counter, transport

# Model configuration
HUB = os.path.expanduser("~/.cache/huggingface/hub")
MODEL_DIR = os.path.join(HUB, "models--mlx-community--Qwen3.6-35B-A3B-4bit", "snapshots")
SNAP_DIRS = glob.glob(os.path.join(MODEL_DIR, "*"))
if not SNAP_DIRS:
    print(f"ERROR: No snapshot found in {MODEL_DIR}", file=sys.stderr)
    sys.exit(1)
ARTIFACT = sorted(SNAP_DIRS)[0]

# Pinned 10-turn dialogue questions
DIALOGUE_TURNS = [
    "What are the core differences between monolithic and microservice software architectures?",
    "Considering those differences, how does service discovery work in a microservice setup?",
    "How does client-side service discovery compare to server-side service discovery in terms of load balancing?",
    "What consensus algorithms (like Raft or Paxos) are typically used by service registries like Consul or etcd?",
    "Explain the leader election phase in Raft in detail.",
    "What happens if a network partition splits the Raft cluster into two equal halves?",
    "How do vector clocks help detect concurrent updates during network partitions in distributed key-value stores?",
    "Can you provide a simple concrete example of two conflicting vector clock states?",
    "How does Dynamo-style eventual consistency resolve such vector clock conflicts using Last-Write-Wins or CRDTs?",
    "Summarize the key architectural lessons learned from these ten discussion points into three golden rules.",
]

CANDIDATE_RUNTIMES = ["mlxlm", "omlx", "optiq", "vmlx", "osaurus"]


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


@contextlib.contextmanager
def osaurus_pin_context():
    """Temporarily pin Osaurus modelIdleResidencyPolicy.seconds to 900 and ensure prefix cache is enabled."""
    conf = Path(os.path.expanduser("~/.osaurus/config/server-runtime.json"))
    server = Path(os.path.expanduser("~/.osaurus/config/server.json"))
    baseline = Path(__file__).resolve().parents[1] / "ohyesmlx" / "osaurus_settings_baseline.json"

    conf_orig = conf.with_suffix(".orig")
    server_orig = server.with_suffix(".orig")

    if conf.exists():
        conf_orig.write_bytes(conf.read_bytes())
    if server.exists():
        server_orig.write_bytes(server.read_bytes())

    try:
        if conf.exists():
            runtime_cfg = json.loads(conf.read_text())
            runtime_cfg.setdefault("cache", {}).setdefault("prefix", {})["enabled"] = True
            conf.write_text(json.dumps(runtime_cfg, indent=2))

        if server.exists():
            server_cfg = json.loads(server.read_text())
            server_cfg.setdefault("modelIdleResidencyPolicy", {})["seconds"] = 900
            server.write_text(json.dumps(server_cfg, indent=2))

        osaurus_settings.write_baseline()
        yield
    finally:
        if conf_orig.exists():
            conf.write_bytes(conf_orig.read_bytes())
            conf_orig.unlink()
        if server_orig.exists():
            server.write_bytes(server_orig.read_bytes())
            server_orig.unlink()
        subprocess.run(["git", "checkout", "--", str(baseline)], capture_output=True)


def run_runtime_multiturn(runtime_name: str) -> dict:
    rt = runtimes.RUNTIMES.get(runtime_name)
    if rt is None:
        return {"runtime": runtime_name, "error": f"Unknown runtime {runtime_name}"}

    print(f"\n{'='*75}")
    print(f"BENCHMARKING MULTI-TURN CONVERSATION: {runtime_name}")
    print(f"Model: Qwen3.6-35B-A3B-4bit ({ARTIFACT})")
    print(f"Turns: {len(DIALOGUE_TURNS)}")
    print(f"{'='*75}")

    sweep_ports()
    counter = token_counter.TokenCounter(ARTIFACT)

    pin_cm = osaurus_pin_context() if runtime_name == "osaurus" else contextlib.nullcontext()
    result = {
        "runtime": runtime_name,
        "model": "Qwen3.6-35B-A3B-4bit",
        "artifact_dir": ARTIFACT,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "turns": [],
    }

    handle = None
    with pin_cm:
        try:
            print(f"--> Starting runtime {runtime_name}...")
            t_start = time.monotonic()
            handle = rt.start(ARTIFACT, f"{runtime_name}/Qwen3.6-35B-A3B-4bit")
            cold_load_s = round(handle.cold_load_s, 2)
            pid = handle.memory_pid
            result["cold_load_s"] = cold_load_s
            result["pid"] = pid
            print(f"    Startup / readiness time: {cold_load_s}s (PID: {pid})")

            idle_footprint = sample.phys_footprint_mb(pid)
            result["idle_phys_footprint_mb"] = idle_footprint
            print(f"    Initial idle phys_footprint: {idle_footprint} MB")

            conversation_history: list[dict[str, str]] = []

            for turn_idx, question in enumerate(DIALOGUE_TURNS, start=1):
                messages = list(conversation_history)
                messages.append({"role": "user", "content": question})

                # Measure local prompt token count
                full_prompt_text = " ".join(m["content"] for m in messages)
                local_prompt_tokens = counter.count(full_prompt_text)

                print(f"\n--> Turn {turn_idx}/{len(DIALOGUE_TURNS)}: '{question[:55]}...'")
                print(f"    Cumulative messages in context: {len(messages)}")

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
                prompt_tokens = obs.prompt_tokens or local_prompt_tokens
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

                output_text = obs.text.strip() if obs.text.strip() else obs.reasoning_text.strip()
                coherent, reason = coherence.is_coherent(output_text)
                turn_footprint = sample.phys_footprint_mb(pid)

                turn_record = {
                    "turn": turn_idx,
                    "user_question": question,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": tokens,
                    "ttft_s": ttft_s,
                    "decode_time_s": decode_time,
                    "decode_tps": decode_tps,
                    "itl_ms": itl_ms,
                    "total_s": total_s,
                    "phys_footprint_mb": turn_footprint,
                    "coherent": coherent,
                    "coherence_reason": reason,
                    "response_sample": output_text[:140],
                }
                result["turns"].append(turn_record)

                print(f"    Prompt Tokens   : {prompt_tokens}")
                print(f"    Completion Toks : {tokens} in {total_s}s")
                print(f"    TTFT            : {ttft_s}s")
                print(f"    Decode Rate     : {decode_tps} tok/s (ITL: {itl_ms} ms/tok)")
                print(f"    Footprint       : {turn_footprint} MB")
                print(f"    Coherence       : {'PASS' if coherent else 'FAIL'} ({reason})")
                print(f"    Completion      : {output_text[:90]}...")

                # Append assistant reply for subsequent turns
                conversation_history.append({"role": "user", "content": question})
                conversation_history.append({"role": "assistant", "content": output_text})

            # Calculate summary stats across turns
            ttfts = [t["ttft_s"] for t in result["turns"]]
            decode_rates = [t["decode_tps"] for t in result["turns"]]
            itls = [t["itl_ms"] for t in result["turns"]]
            footprints = [t["phys_footprint_mb"] for t in result["turns"] if t["phys_footprint_mb"]]

            result["summary"] = {
                "turn1_ttft_s": ttfts[0] if ttfts else None,
                "turn10_ttft_s": ttfts[-1] if ttfts else None,
                "ttft_growth_ratio": round(ttfts[-1] / ttfts[0], 2) if (ttfts and ttfts[0] > 0) else None,
                "mean_decode_tps": round(sum(decode_rates) / len(decode_rates), 2) if decode_rates else None,
                "decode_tps_std": round((sum((x - (sum(decode_rates)/len(decode_rates)))**2 for x in decode_rates) / len(decode_rates))**0.5, 2) if decode_rates else None,
                "mean_itl_ms": round(sum(itls) / len(itls), 2) if itls else None,
                "initial_footprint_mb": footprints[0] if footprints else None,
                "final_footprint_mb": footprints[-1] if footprints else None,
                "footprint_delta_mb": round(footprints[-1] - footprints[0], 1) if len(footprints) > 1 else 0.0,
                "all_coherent": all(t["coherent"] for t in result["turns"]),
            }

            print(f"\n--> {runtime_name} Summary:")
            print(f"    TTFT Turn 1 -> Turn 10 : {result['summary']['turn1_ttft_s']}s -> {result['summary']['turn10_ttft_s']}s (Ratio: {result['summary']['ttft_growth_ratio']}x)")
            print(f"    Mean Decode TPS        : {result['summary']['mean_decode_tps']} tok/s (std: {result['summary']['decode_tps_std']})")
            print(f"    Mean ITL               : {result['summary']['mean_itl_ms']} ms/tok")
            print(f"    Memory Delta           : +{result['summary']['footprint_delta_mb']} MB")
            print(f"    All Turns Coherent     : {result['summary']['all_coherent']}")

        except Exception as e:
            print(f"ERROR executing {runtime_name}: {type(e).__name__}: {e}", file=sys.stderr)
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
    out_dir = Path("results/plan-03-04")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "multiturn_results.json"

    selected_runtimes = sys.argv[1:] if len(sys.argv) > 1 else CANDIDATE_RUNTIMES

    print("===========================================================================")
    print("PLAN 03-04: MULTI-TURN CONVERSATION SWEEP (1 TO 10 TURNS)")
    print(f"Model: {ARTIFACT}")
    print(f"Target runtimes: {selected_runtimes}")
    print("===========================================================================")

    all_results = []
    # If partial results file exists, load it
    if out_file.exists():
        try:
            all_results = json.loads(out_file.read_text("utf-8"))
        except Exception:
            all_results = []

    completed_runtimes = {r.get("runtime") for r in all_results if "turns" in r and len(r["turns"]) == 10}

    for rt_name in selected_runtimes:
        if rt_name in completed_runtimes:
            print(f"Runtime {rt_name} already completed with 10 turns. Skipping (use clean run to force).")
            continue

        res = run_runtime_multiturn(rt_name)
        # Update or append
        all_results = [r for r in all_results if r.get("runtime") != rt_name] + [res]
        out_file.write_text(json.dumps(all_results, indent=2), "utf-8")

        print("--> Cooldown 10s between runtimes...")
        time.sleep(10.0)

    print(f"\nMulti-turn benchmark sweep complete. All evidence saved to {out_file}")


if __name__ == "__main__":
    main()
