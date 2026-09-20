#!/usr/bin/env python3
"""Plan 03-02 Probe: Cold vs Warm Page Cache Load & Memory Residency Attribution on 35B MoE.

Measures:
1. Exact file page cache residency via libc.mincore (0.0% to 100.0%) before and after load.
2. Cold load time (from APFS NVMe disk) vs warm load time (from macOS buffer cache).
3. Request #1, #2, #3 latency decomposition to expose hidden lazy-loading penalties at 35B.
4. Process memory breakdown via footprint and vmmap (IOAccelerator wired vs anonymous vs mapped).
5. System-wide vm_stat memory state (wired, file-backed, anonymous) before, during, and after.

Usage:
    python scripts/probe_page_cache_35b.py [runtime_name ...]
"""

from __future__ import annotations

import collections
import contextlib
import ctypes
import glob
import json
import mmap
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ohyesmlx import runtimes, sample, token_counter, transport

# Resolve Qwen3.6-35B-A3B stock4bit snapshot
HUB = os.path.expanduser("~/.cache/huggingface/hub")
MODEL_DIR = os.path.join(HUB, "models--mlx-community--Qwen3.6-35B-A3B-4bit", "snapshots")
SNAP_DIRS = glob.glob(os.path.join(MODEL_DIR, "*"))
if not SNAP_DIRS:
    print(f"ERROR: No snapshot found in {MODEL_DIR}", file=sys.stderr)
    sys.exit(1)
ARTIFACT = sorted(SNAP_DIRS)[0]

PROMPT = [{"role": "user", "content": "Say the word ready."}]

_REGION = re.compile(
    r"^(?P<kind>.+?)\s+([0-9a-f]+)-([0-9a-f]+)\s+\[\s*(?P<vsize>\S+)\s+(?P<rsdnt>\S+)\s+"
    r"(?P<dirty>\S+)\s+(?P<swap>\S+)\s*\]",
    re.IGNORECASE,
)

libc = ctypes.CDLL(None)


def get_cache_residency(shard_paths: list[str]) -> dict:
    """Measure exact page-level buffer cache residency for given file shards via mincore."""
    tot_bytes = 0
    tot_pages = 0
    tot_resident = 0
    per_file = {}
    page_size = 16384  # Apple Silicon 16 KiB page

    for fpath in shard_paths:
        size = os.path.getsize(fpath)
        num_pages = (size + page_size - 1) // page_size
        with open(fpath, "rb") as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_COPY)
            buf = (ctypes.c_char * size).from_buffer(mm)
            addr = ctypes.addressof(buf)
            vec = (ctypes.c_char * num_pages)()
            libc.mincore(ctypes.c_void_p(addr), ctypes.c_size_t(size), vec)
            res = sum(1 for b in vec.raw if b != 0)
            del buf
            mm.close()

        tot_bytes += size
        tot_pages += num_pages
        tot_resident += res
        per_file[os.path.basename(fpath)] = {
            "size_mb": round(size / (1024 * 1024), 2),
            "pages": num_pages,
            "resident_pages": res,
            "pct_resident": round(100.0 * res / num_pages, 2) if num_pages else 0.0,
        }

    return {
        "total_bytes": tot_bytes,
        "total_gb": round(tot_bytes / (1024**3), 3),
        "total_pages": tot_pages,
        "total_resident_pages": tot_resident,
        "pct_resident": round(100.0 * tot_resident / tot_pages, 2) if tot_pages else 0.0,
        "shards": per_file,
    }


def sample_vmstat() -> dict:
    """Read system-wide virtual memory statistics via vm_stat."""
    proc = subprocess.run(["vm_stat"], capture_output=True, text=True, check=True)
    stats = {}
    page_size = 16384
    for line in proc.stdout.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            k = k.strip().strip('"')
            v = v.strip().rstrip(".")
            try:
                stats[k] = int(v) * page_size / (1024 * 1024)  # convert to MB
            except ValueError:
                pass
    return {
        "free_mb": round(stats.get("Pages free", 0.0), 1),
        "active_mb": round(stats.get("Pages active", 0.0), 1),
        "inactive_mb": round(stats.get("Pages inactive", 0.0), 1),
        "wired_mb": round(stats.get("Pages wired down", 0.0), 1),
        "purgeable_mb": round(stats.get("Pages purgeable", 0.0), 1),
        "file_backed_mb": round(stats.get("File-backed pages", 0.0), 1),
        "anonymous_mb": round(stats.get("Anonymous pages", 0.0), 1),
        "compressed_mb": round(stats.get("Pages occupied by compressor", 0.0), 1),
    }


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
        v[0] for k, v in totals.items() if "mapped file" not in k.lower() and "ioaccelerator" not in k.lower()
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
    # Sweep stale Osaurus app processes by full path
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
    conf = Path.home() / ".osaurus" / "config" / "server-runtime.json"
    server = Path.home() / ".osaurus" / "config" / "server.json"
    baseline = Path(__file__).resolve().parents[1] / "config" / "osaurus-settings-baseline.json"

    conf_orig = conf.with_suffix(".probe-orig")
    server_orig = server.with_suffix(".probe-orig")

    if conf.exists():
        conf_orig.write_bytes(conf.read_bytes())
    if server.exists():
        server_orig.write_bytes(server.read_bytes())

    try:
        if conf.exists():
            runtime_cfg = json.loads(conf.read_text())
            runtime_cfg.setdefault("cache", {}).setdefault("prefix", {})["enabled"] = False
            runtime_cfg.setdefault("cache", {}).setdefault("blockDisk", {})["enabled"] = False
            conf.write_text(json.dumps(runtime_cfg, indent=2))

        if server.exists():
            server_cfg = json.loads(server.read_text())
            server_cfg.setdefault("modelIdleResidencyPolicy", {})["seconds"] = 900
            server.write_text(json.dumps(server_cfg, indent=2))

        from ohyesmlx import osaurus_settings
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


def run_probe_cell(runtime_name: str, shards: list[str]) -> dict:
    rt = runtimes.RUNTIMES.get(runtime_name)
    if rt is None:
        return {"error": f"unknown runtime {runtime_name}"}

    print(f"\n{'='*72}\nPROBING: {runtime_name} on Qwen3.6-35B-A3B-4bit\n{'='*72}")
    sweep_ports()

    res_pre = get_cache_residency(shards)
    vmstat_pre = sample_vmstat()
    print(f"Pre-load Buffer Cache Residency : {res_pre['pct_resident']:.2f}% ({res_pre['total_resident_pages']}/{res_pre['total_pages']} pages)")
    print(f"Pre-load System Wired Memory    : {vmstat_pre['wired_mb']:.1f} MB, Free: {vmstat_pre['free_mb']:.1f} MB")

    counter = token_counter.TokenCounter(ARTIFACT)
    handle = None
    result = {
        "runtime": runtime_name,
        "artifact": ARTIFACT,
        "pre_cache_residency_pct": res_pre["pct_resident"],
        "vmstat_pre": vmstat_pre,
    }

    pin_cm = osaurus_pin_context() if runtime_name == "osaurus" else contextlib.nullcontext()
    with pin_cm:
        try:
            # Phase 1: Cold Load
            print(f"--> Starting {runtime_name} (Cold Load)...")
            handle = rt.start(ARTIFACT, f"{runtime_name}/stock4bit")
            cold_load_s = round(handle.cold_load_s, 2)
            result["cold_load_s"] = cold_load_s
            print(f"    Startup / readiness time: {cold_load_s}s")

            # Phase 2: Sequential Requests (testing lazy loading)
            req_times = []
            for i in range(1, 4):
                t0 = time.monotonic()
                transport.chat(
                    handle.base_url,
                    handle.model_id,
                    PROMPT,
                    max_tokens=8,
                    temperature=0.0,
                    seed=0,
                    token_counter=counter,
                    api_key=handle.api_key,
                )
                elapsed = round(time.monotonic() - t0, 3)
                req_times.append(elapsed)
                print(f"    Request #{i} latency: {elapsed}s")

            result["request_latencies_s"] = req_times
            hidden_penalty = round(req_times[0] - min(req_times[1:]), 3)
            result["lazy_hidden_penalty_s"] = hidden_penalty
            print(f"    Hidden first-request delta: {hidden_penalty}s")

            # Phase 3: Residency Sampling
            pid = handle.memory_pid
            result["memory_pid"] = pid
            result["phys_footprint_mb"] = sample.phys_footprint_mb(pid)
            result["vmmap_summary"] = sample.vmmap_split(pid)
            result["region_breakdown"] = sample_regions(pid)
            result["vmstat_resident"] = sample_vmstat()

            print(f"    Process phys_footprint    : {result['phys_footprint_mb']} MB")
            print(f"    IOAccelerator (graphics)  : {result['region_breakdown'].get('ioaccelerator_resident_mb')} MB")
            print(f"    Anonymous memory          : {result['region_breakdown'].get('anonymous_resident_mb')} MB")
            print(f"    Mapped file memory        : {result['region_breakdown'].get('mapped_file_resident_mb')} MB")
            print(f"    System wired increase     : {round(result['vmstat_resident']['wired_mb'] - vmstat_pre['wired_mb'], 1)} MB")

        finally:
            if handle is not None:
                try:
                    handle.stop()
                except Exception:
                    pass
            sweep_ports()

        res_post_cold = get_cache_residency(shards)
        result["post_cold_cache_residency_pct"] = res_post_cold["pct_resident"]
        print(f"Post-cold Buffer Cache Residency: {res_post_cold['pct_resident']:.2f}%")

        # Phase 4: Warm Reload
        print(f"--> Re-starting {runtime_name} (Warm Reload, cache={res_post_cold['pct_resident']:.1f}%)...")
        handle_warm = None
        try:
            handle_warm = rt.start(ARTIFACT, f"{runtime_name}/stock4bit")
            warm_load_s = round(handle_warm.cold_load_s, 2)
            result["warm_load_s"] = warm_load_s
            print(f"    Warm startup time         : {warm_load_s}s")

            t0 = time.monotonic()
            transport.chat(
                handle_warm.base_url,
                handle_warm.model_id,
                PROMPT,
                max_tokens=8,
                temperature=0.0,
                seed=0,
                token_counter=counter,
                api_key=handle_warm.api_key,
            )
            warm_req1 = round(time.monotonic() - t0, 3)
            result["warm_request_1_s"] = warm_req1
            print(f"    Warm Request #1 latency   : {warm_req1}s")
        finally:
            if handle_warm is not None:
                try:
                    handle_warm.stop()
                except Exception:
                    pass
            sweep_ports()

        res_post_warm = get_cache_residency(shards)
        result["post_warm_cache_residency_pct"] = res_post_warm["pct_resident"]
        return result


def main():
    shards = sorted(glob.glob(os.path.join(ARTIFACT, "model-*.safetensors")))
    if not shards:
        print(f"ERROR: No safetensors found in {ARTIFACT}", file=sys.stderr)
        sys.exit(1)

    runtimes_to_probe = sys.argv[1:] or ["mlxlm", "omlx", "optiq", "vmlx", "osaurus"]
    out_dir = Path("results/plan-03-02")
    out_dir.mkdir(parents=True, exist_ok=True)

    print("========================================================================")
    print("Plan 03-02 Page Cache Load & Memory Residency Probe on Qwen3.6-35B-A3B")
    print(f"Artifact : {ARTIFACT}")
    print(f"Shards   : {len(shards)} files ({round(sum(os.path.getsize(f) for f in shards)/(1024**3), 2)} GiB)")
    print(f"Runtimes : {', '.join(runtimes_to_probe)}")
    print("========================================================================")

    all_results = []
    out_file = out_dir / "probe_results.json"
    for rt_name in runtimes_to_probe:
        try:
            res = run_probe_cell(rt_name, shards)
            all_results.append(res)
        except Exception as e:
            print(f"ERROR probing {rt_name}: {type(e).__name__}: {e}")
            all_results.append({"runtime": rt_name, "error": f"{type(e).__name__}: {e}"})
        out_file.write_text(json.dumps(all_results, indent=2), "utf-8")
        # 10s quiet cooldown between runtimes
        time.sleep(10.0)

    print(f"\nProbe complete. Results saved to {out_file}")


if __name__ == "__main__":
    main()
