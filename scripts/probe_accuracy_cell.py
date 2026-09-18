"""Plan 02-02: Accuracy scoring evaluation for a single cell.

Drives one runtime (vmlx or osaurus) over one model artifact, runs the canary,
evaluates the pinned benchmark tasks (MMLU 5-shot, GSM8K 5-shot, IFEval 0-shot)
via isolated `uv run --isolated --with lm-eval[api,ifeval]==0.4.13`, captures the
runtime logs, and writes a structured manifest and per-task results.

Zero dependencies added to OhYesMLX.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ohyesmlx import runtimes  # noqa: E402

UV = os.path.expanduser("~/.local/bin/uv")
HARNESS = "lm-eval[api,ifeval]==0.4.13"
VMLX_PATCHED_SHA256 = "9710d2b9cf07abc7380f46fef240e64febb2d06d52eb7f64236bd0e76cf686f7"
VMLX_SCHEDULER_PATH = (
    "/Applications/vMLX.app/Contents/Resources/vmlx-engine-source/vmlx_engine/mllm_scheduler.py"
)

CANARY_BODY = {
    "messages": [{"role": "user", "content": "What is 2+2? Answer with just the number."}],
    "temperature": 0.0,
    "max_tokens": 256,
}
REQUEST_TIMEOUT_S = 300.0
TASK_TIMEOUT_S = 14400.0  # 4 hours per task ceiling

# Task configurations for Plan 02-02 (Dense Accuracy Study)
DEFAULT_TASKS = (
    ("mmlu_generative", 40, 5),   # 40 items per subject * 57 subjects = 2,280 items, 5-shot
    ("gsm8k", 250, 5),            # 250 items, 5-shot CoT
    ("ifeval", 250, 0),           # 250 items, 0-shot
)

REPLICATE_TASKS = (
    ("mmlu_generative", 40, 5),   # Replicate is MMLU only
)


def run_cmd(command: tuple[str, ...], timeout: float = TASK_TIMEOUT_S) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, capture_output=True, text=True, cwd=ROOT, timeout=timeout, check=False
    )


def uv_run(*args: str, timeout: float = TASK_TIMEOUT_S) -> subprocess.CompletedProcess[str]:
    return run_cmd((UV, "run", "--isolated", "--with", HARNESS, *args), timeout=timeout)


def verify_vmlx_patch() -> tuple[bool, str]:
    if not os.path.exists(VMLX_SCHEDULER_PATH):
        return False, f"missing scheduler at {VMLX_SCHEDULER_PATH}"
    digest = hashlib.sha256(Path(VMLX_SCHEDULER_PATH).read_bytes()).hexdigest()
    if digest != VMLX_PATCHED_SHA256:
        return False, f"hash mismatch: {digest} != {VMLX_PATCHED_SHA256}"
    return True, digest


def channel_of(payload: dict) -> tuple[str, str]:
    message = payload["choices"][0]["message"]
    for channel in ("content", "reasoning_content"):
        text = message.get(channel)
        if isinstance(text, str) and text.strip():
            return channel, text
    return "none", ""


def ask_canary(base_url: str, model_id: str) -> dict:
    body = dict(CANARY_BODY, model=model_id, stream=False)
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S) as response:
        payload = json.loads(response.read())
    channel, text = channel_of(payload)
    return {
        "canary_request": body,
        "canary_response": payload,
        "canary_channel": channel,
        "canary_text": text,
    }


def score_of(results_path: str, task: str) -> tuple[str | None, float | None]:
    data = json.loads(Path(results_path).read_text("utf-8"))
    results = data.get("results") or {}
    entry = results.get(task)
    if not entry:
        # Group task fallback (e.g. mmlu_generative)
        groups = data.get("groups") or {}
        entry = groups.get(task)
    if not entry:
        return None, None

    # Priority metrics per task
    if task.startswith("mmlu"):
        for key in ("exact_match,get_response", "exact_match", "acc"):
            if key in entry and isinstance(entry[key], (int, float)):
                return key, float(entry[key])
    elif task == "gsm8k":
        for key in ("exact_match,strict-match", "exact_match,flexible-extract", "exact_match"):
            if key in entry and isinstance(entry[key], (int, float)):
                return key, float(entry[key])
    elif task == "ifeval":
        for key in ("prompt_level_strict_acc,none", "prompt_level_strict_acc", "inst_level_strict_acc"):
            if key in entry and isinstance(entry[key], (int, float)):
                return key, float(entry[key])

    # Fallback to any exact_match or acc metric
    for key, val in entry.items():
        if ("exact_match" in key or "acc" in key) and isinstance(val, (int, float)):
            return key, float(val)
    return None, None


def count_of(samples_path: str | None, results_path: str, task: str) -> int | None:
    if samples_path and os.path.exists(samples_path):
        return sum(1 for line in Path(samples_path).read_text("utf-8").splitlines() if line.strip())
    counts = json.loads(Path(results_path).read_text("utf-8")).get("n-samples") or {}
    effective = (counts.get(task) or {}).get("effective")
    if isinstance(effective, (int, float)):
        return int(effective)
    # Check group counts
    total = 0
    for subtask, subval in counts.items():
        if subtask.startswith(task + "_") or subtask.startswith(task + "::"):
            eff = subval.get("effective", 0)
            if isinstance(eff, (int, float)):
                total += int(eff)
    return total if total > 0 else None


def task_hash_of(results_path: str, task: str) -> dict[str, str]:
    data = json.loads(Path(results_path).read_text("utf-8"))
    hashes = data.get("task_hashes") or {}
    return {k: v for k, v in hashes.items() if k == task or k.startswith(task + "_") or k.startswith(task + "::")}


def newest_file(pattern: str, before: set[str]) -> str | None:
    written = sorted(set(glob.glob(pattern, recursive=True)) - before)
    return max(written, key=os.path.getmtime) if written else None


def run_cell(
    runtime_name: str,
    cell_label: str,
    artifact_path: str,
    out_dir: str,
    is_replicate: bool = False,
) -> int:
    os.makedirs(out_dir, exist_ok=True)
    manifest_path = os.path.join(out_dir, "manifest.json")
    manifest: dict = {
        "cell": cell_label,
        "runtime": runtime_name,
        "artifact": artifact_path,
        "cache_state": runtimes.CACHE_STATE_OFF,
        "is_replicate": is_replicate,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "uv_version": run_cmd((UV, "--version")).stdout.strip(),
        "lm_eval_version": None,
        "runtime_version": None,
        "vmlx_engine_sha256": None,
        "canary": None,
        "tasks": {},
        "status": "INCOMPLETE",
        "error": None,
    }

    if runtime_name == "vmlx":
        ok, detail = verify_vmlx_patch()
        manifest["vmlx_engine_sha256"] = detail
        if not ok:
            manifest["status"] = "FAIL"
            manifest["error"] = f"vMLX engine patch verification failed: {detail}"
            Path(manifest_path).write_text(json.dumps(manifest, indent=2), "utf-8")
            print(f"ERROR: {manifest['error']}", file=sys.stderr)
            return 1

    runtime = runtimes.RUNTIMES[runtime_name]
    task_plan = REPLICATE_TASKS if is_replicate else DEFAULT_TASKS
    logs_dir = Path(ROOT) / "results" / "logs"
    logs_before = set(glob.glob(str(logs_dir / f"{runtime_name}-*.log")))

    handle = None
    cell_success = True
    try:
        print(f"[{cell_label}] Starting {runtime_name}...", flush=True)
        handle = runtime.start(artifact_path, cell_label, cache_state=runtimes.CACHE_STATE_OFF)
        manifest["model_id"] = handle.model_id
        manifest["runtime_version"] = handle.version
        manifest["cold_load_s"] = round(handle.cold_load_s, 3)
        print(f"[{cell_label}] Started on port {handle.port}, model_id: {handle.model_id}", flush=True)

        probe = uv_run("python", "-c", "import importlib.metadata as m; print(m.version('lm-eval'))")
        manifest["lm_eval_version"] = probe.stdout.strip()

        print(f"[{cell_label}] Checking canary...", flush=True)
        canary = ask_canary(handle.base_url, handle.model_id)
        manifest["canary"] = canary
        print(f"[{cell_label}] Canary channel={canary['canary_channel']}: {canary['canary_text']!r}", flush=True)

        model_args = (
            f"base_url={handle.base_url}/chat/completions,"
            f"model={handle.model_id},"
            f"tokenizer={artifact_path},"
            "think_end_token=</think>,"
            "eos_string=<|im_end|>,"
            "max_gen_toks=1024,"
            "max_length=4096"
        )

        for task_name, limit, num_fewshot in task_plan:
            print(f"\n[{cell_label}] Running task {task_name} (limit={limit}, fewshot={num_fewshot})...", flush=True)
            task_out = os.path.join(out_dir, task_name)
            os.makedirs(task_out, exist_ok=True)
            before_files = set(glob.glob(os.path.join(task_out, "**", "*"), recursive=True))

            cmd = [
                "lm_eval",
                "--model", "local-chat-completions",
                "--model_args", model_args,
                "--apply_chat_template",
                "--fewshot_as_multiturn",
                "--gen_kwargs", "enable_thinking=false",
                "--tasks", task_name,
                "--limit", str(limit),
                "--output_path", task_out + os.sep,
                "--log_samples",
            ]
            if num_fewshot > 0:
                cmd.extend(["--num_fewshot", str(num_fewshot)])

            t0 = time.monotonic()
            completed = uv_run(*cmd)
            duration_s = round(time.monotonic() - t0, 3)

            output_log = os.path.join(task_out, "lm_eval_output.txt")
            Path(output_log).write_text(completed.stdout + completed.stderr, "utf-8")

            results_file = newest_file(os.path.join(task_out, "**", "results_*.json"), before_files)
            samples_file = newest_file(os.path.join(task_out, "**", "samples_*.jsonl"), before_files)

            metric_name, score = (None, None)
            items_scored = None
            task_hashes = {}
            if results_file and os.path.exists(results_file):
                metric_name, score = score_of(results_file, task_name)
                items_scored = count_of(samples_file, results_file, task_name)
                task_hashes = task_hash_of(results_file, task_name)

            task_record = {
                "task": task_name,
                "limit": limit,
                "num_fewshot": num_fewshot,
                "returncode": completed.returncode,
                "duration_s": duration_s,
                "metric": metric_name,
                "score": score,
                "items_scored": items_scored,
                "results_path": results_file,
                "samples_path": samples_file,
                "task_hashes": task_hashes,
            }
            manifest["tasks"][task_name] = task_record

            if completed.returncode != 0:
                cell_success = False
                print(f"[{cell_label}] Task {task_name} FAILED with returncode {completed.returncode}", file=sys.stderr)
            else:
                print(f"[{cell_label}] Task {task_name} DONE in {duration_s}s: {metric_name} = {score} (n={items_scored})", flush=True)

    except Exception as exc:
        cell_success = False
        manifest["error"] = traceback.format_exc()
        print(f"[{cell_label}] Exception during evaluation: {exc}", file=sys.stderr)
    finally:
        manifest["port_released"] = False
        if handle is not None:
            try:
                print(f"[{cell_label}] Stopping runtime...", flush=True)
                handle.stop()
                runtimes.await_port_free(runtime.port)
                manifest["port_released"] = True
                print(f"[{cell_label}] Port {runtime.port} verified free.", flush=True)
            except Exception as stop_exc:
                manifest["stop_error"] = str(stop_exc)
                print(f"[{cell_label}] Error stopping runtime: {stop_exc}", file=sys.stderr)

        # Locate runtime log
        logs_after = set(glob.glob(str(logs_dir / f"{runtime_name}-*.log"))) - logs_before
        if logs_after:
            newest_log = max(logs_after, key=os.path.getmtime)
            cell_runtime_log = os.path.join(out_dir, "runtime.log")
            try:
                shutil.copyfile(newest_log, cell_runtime_log)
                manifest["runtime_log"] = cell_runtime_log
            except OSError:
                pass

        manifest["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        manifest["status"] = "PASS" if cell_success and manifest["port_released"] else "FAIL"
        Path(manifest_path).write_text(json.dumps(manifest, indent=2, sort_keys=True), "utf-8")

    return 0 if manifest["status"] == "PASS" else 1


def self_test() -> int:
    """Offline check against fixtures."""
    both = {"choices": [{"message": {"content": "4", "reasoning_content": "2+2="}}]}
    assert channel_of(both) == ("content", "4")
    answered = {"choices": [{"message": {"content": "", "reasoning_content": "4"}}]}
    assert channel_of(answered) == ("reasoning_content", "4")

    with tempfile.TemporaryDirectory() as tmpdir:
        res_file = os.path.join(tmpdir, "results.json")
        entry = {
            "results": {
                "gsm8k": {"exact_match,strict-match": 0.8},
                "ifeval": {"prompt_level_strict_acc,none": 0.75},
            },
            "groups": {
                "mmlu_generative": {"exact_match,get_response": 0.65},
            },
            "n-samples": {
                "gsm8k": {"effective": 250},
                "ifeval": {"effective": 250},
                "mmlu_generative": {"effective": 2280},
            },
            "task_hashes": {
                "gsm8k": "hash_gsm",
                "ifeval": "hash_ifeval",
                "mmlu_generative": "hash_mmlu",
            },
        }
        Path(res_file).write_text(json.dumps(entry), "utf-8")
        assert score_of(res_file, "gsm8k") == ("exact_match,strict-match", 0.8)
        assert score_of(res_file, "ifeval") == ("prompt_level_strict_acc,none", 0.75)
        assert score_of(res_file, "mmlu_generative") == ("exact_match,get_response", 0.65)
        assert count_of(None, res_file, "gsm8k") == 250
        assert count_of(None, res_file, "mmlu_generative") == 2280
        assert task_hash_of(res_file, "gsm8k") == {"gsm8k": "hash_gsm"}

    print("probe_accuracy_cell self-test ok")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run accuracy scoring evaluation on a single cell.")
    parser.add_argument("--runtime", choices=["vmlx", "osaurus"], help="Serving runtime")
    parser.add_argument("--cell", help="Cell label, e.g. stock4bit__vmlx")
    parser.add_argument("--artifact", help="Absolute path to model snapshot directory")
    parser.add_argument("--out", help="Output directory for cell results")
    parser.add_argument("--replicate", action="store_true", help="Run replicate pass (MMLU only)")
    parser.add_argument("--self-test", action="store_true", help="Run offline unit self-test")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    if not args.runtime or not args.cell or not args.artifact or not args.out:
        parser.error("--runtime, --cell, --artifact, and --out are required unless --self-test is set")

    return run_cell(
        runtime_name=args.runtime,
        cell_label=args.cell,
        artifact_path=args.artifact,
        out_dir=args.out,
        is_replicate=args.replicate,
    )


if __name__ == "__main__":
    raise SystemExit(main())
