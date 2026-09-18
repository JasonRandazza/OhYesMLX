"""Plan 02-01: the harness spike against a local endpoint.

docs/research/2026-09-17-v2-track2-accuracy-study-design.md §6.2 is the protocol; this runs its
endpoint-facing half against one pin set -- runtime `vmlx` on port 8000, artifact `Qwen3.5-4B`
`stock4bit`, `cache_state="off"` -- and prints one JSON report: the uv and `lm-eval` versions
out of the isolated env (which also warms the uv cache, §4.3), the §3.5 canary with its whole
response kept verbatim, and one `gsm8k` invocation at `--limit 2` audited against the harness's
own `--log_samples` output.

The canary is the point of the spike. lm-evaluation-harness reads only
``choices[0].message.content`` and has no reasoning-channel rule, so a runtime answering in
``reasoning_content`` scores 0% on a run that looks perfectly healthy.

The runtime is started and stopped through `runtimes.RUNTIMES[...]`, never by hand, because the
start command is a pin; `Handle.stop()` runs in a `finally` and the port is re-checked free.
`seconds_per_item` carries uv's env setup and the harness's startup, so on two items it is a
ceiling rather than a rate.

    scripts/probe_accuracy_spike.py > results/spike-eval/spike-report.json
    scripts/probe_accuracy_spike.py --self-test     # offline, no runtime, no network

Exit status is 0 only when the harness returned 0, the port is free and nothing raised.
"""

from __future__ import annotations

import glob
import json
import os
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

RUNTIME = "vmlx"
ARTIFACT = os.path.expanduser(
    "~/.cache/huggingface/hub/models--mlx-community--Qwen3.5-4B-4bit/snapshots/"
    "0e7ffd5c629ef7719d4cbc04069232580bfa9d9c"
)
UV = os.path.expanduser("~/.local/bin/uv")
HARNESS = "lm-eval[api,ifeval]==0.4.13"
TASK = "gsm8k"
OUT = os.path.join(ROOT, "results", "spike-eval")
CANARY_BODY = {
    "messages": [{"role": "user", "content": "What is 2+2? Answer with just the number."}],
    "temperature": 0.0,
    "max_tokens": 256,
}
# Generous: a first `uv run --isolated` builds the harness env, and a first request pays for
# whatever the runtime loads lazily.
UV_TIMEOUT_S = 900.0
REQUEST_TIMEOUT_S = 300.0


def run(command: tuple[str, ...], timeout: float = UV_TIMEOUT_S):
    return subprocess.run(
        command, capture_output=True, text=True, cwd=ROOT, timeout=timeout, check=False
    )


def uv(*args: str):
    return run((UV, "run", "--isolated", "--with", HARNESS, *args))


def channel_of(payload: dict) -> tuple[str, str]:
    """The channel the answer arrived in, and its verbatim text (§3.5's channel rule)."""
    message = payload["choices"][0]["message"]
    for channel in ("content", "reasoning_content"):
        text = message.get(channel)
        if isinstance(text, str) and text.strip():
            return channel, text
    return "none", ""


def ask(base_url: str, model_id: str) -> dict:
    """The canary: one known-answer request, every channel of the response kept verbatim."""
    # §3.4 pins the resolved `model` id and `stream` off; the order's body carries the rest.
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


def score_of(results_path: str, task: str = TASK) -> tuple[str | None, float | None]:
    """The task's primary metric and value, read from the harness's own results JSON."""
    entry = (json.loads(Path(results_path).read_text("utf-8")).get("results") or {}).get(task)
    named = sorted(
        (key for key in entry or {} if key.startswith("exact_match")),
        key=lambda key: "strict" not in key,
    )
    if named and isinstance(entry[named[0]], (int, float)):
        return named[0], float(entry[named[0]])
    return None, None


def count_of(samples_path: str | None, results_path: str, task: str = TASK) -> int | None:
    """Items scored, counted from `--log_samples` or, when absent, the results JSON."""
    if samples_path:
        return sum(1 for line in Path(samples_path).read_text("utf-8").splitlines() if line.strip())
    counts = json.loads(Path(results_path).read_text("utf-8")).get("n-samples") or {}
    effective = (counts.get(task) or {}).get("effective")
    return int(effective) if isinstance(effective, (int, float)) else None


def newest(pattern: str, before: set[str]) -> str | None:
    """The newest file this invocation wrote. Nothing is deleted to find it."""
    written = sorted(set(glob.glob(pattern, recursive=True)) - before)
    return max(written, key=os.path.getmtime) if written else None


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    runtime = runtimes.RUNTIMES[RUNTIME]
    report: dict = {
        "artifact": ARTIFACT, "runtime": RUNTIME, "cache_state": runtimes.CACHE_STATE_OFF,
        "uv_version": run((UV, "--version")).stdout.strip(), "lm_eval_version": None,
        "runtime_version": None, "canary_channel": None, "canary_text": None,
        "lm_eval_returncode": None, "gsm8k_sample_score": None, "seconds_per_item": None,
    }
    handle = None
    try:
        handle = runtime.start(ARTIFACT, ARTIFACT, cache_state=runtimes.CACHE_STATE_OFF)
        report["model_id"] = handle.model_id
        report["runtime_version"] = handle.version
        probe = uv("python", "-c", "import importlib.metadata as m; print(m.version('lm-eval'))")
        report["lm_eval_version"] = probe.stdout.strip() or f"unknown: exited {probe.returncode}"
        report.update(ask(handle.base_url, handle.model_id))

        model_args = (
            f"base_url={handle.base_url}/chat/completions,"
            f"model={handle.model_id},"
            f"tokenizer={ARTIFACT},"
            "think_end_token=</think>,"
            f"eos_string=<|im_end|>,"
            "max_gen_toks=1024,"
            "max_length=4096"
        )
        report["model_args"] = model_args
        before = set(glob.glob(os.path.join(OUT, "**", "*"), recursive=True))
        started = time.monotonic()
        completed = uv(
            "lm_eval", "--model", "local-chat-completions", "--model_args", model_args,
            "--apply_chat_template",
            "--gen_kwargs", "enable_thinking=false",
            "--tasks", TASK, "--limit", "2", "--output_path", OUT + os.sep, "--log_samples",
        )
        elapsed = time.monotonic() - started
        report["invocation_s"] = round(elapsed, 3)
        report["lm_eval_returncode"] = completed.returncode
        output_path = os.path.join(OUT, "lm_eval_output.txt")
        Path(output_path).write_text(completed.stdout + completed.stderr, "utf-8")
        report["lm_eval_output_path"] = output_path

        results_path = newest(os.path.join(OUT, "**", "results_*.json"), before)
        samples_path = newest(os.path.join(OUT, "**", "samples_*.jsonl"), before)
        report["lm_eval_results_path"] = results_path
        if results_path is not None:
            metric, score = score_of(results_path)
            report["gsm8k_metric"] = metric
            report["gsm8k_sample_score"] = score
            items = count_of(samples_path, results_path)
            report["items_scored"] = items
            if items:
                report["seconds_per_item"] = round(elapsed / items, 3)
    except Exception:  # the report is the record; the exit status carries the failure
        report["error"] = traceback.format_exc()
    finally:
        # One runtime holds weights at a time, and a run that does not release its port has
        # failed whatever else it reported.
        report["port_released"] = False
        if handle is not None:
            try:
                handle.stop()
                runtimes.await_port_free(runtime.port)
                report["port_released"] = True
            except runtimes.RuntimeLifecycleError as error:
                report["stop_error"] = f"{type(error).__name__}: {error}"

    print(json.dumps(report, indent=2, sort_keys=True))
    clean = report["lm_eval_returncode"] == 0 and report["port_released"] and "error" not in report
    return 0 if clean else 1


def self_test() -> int:
    """The runnable check: the channel rule and the two parsers, offline, against fixtures."""
    both = {"choices": [{"message": {"content": "4", "reasoning_content": "2+2="}}]}
    assert channel_of(both) == ("content", "4")
    answered = {"choices": [{"message": {"content": "", "reasoning_content": "4"}}]}
    assert channel_of(answered) == ("reasoning_content", "4")
    assert channel_of({"choices": [{"message": {}}]}) == ("none", "")
    with tempfile.TemporaryDirectory() as scratch:
        results = os.path.join(scratch, "results_2026-09-18T00-00-00.json")
        entry = {
            "results": {TASK: {"exact_match,flexible-extract": 1.0, "exact_match,strict-match": 0.5}},
            "n-samples": {TASK: {"effective": 2, "original": 1319}},
        }
        Path(results).write_text(json.dumps(entry), "utf-8")
        assert score_of(results) == ("exact_match,strict-match", 0.5)
        assert score_of(results, "gsm8k-cot") == (None, None)
        samples = os.path.join(scratch, "samples_2026-09-18T00-00-00.jsonl")
        Path(samples).write_text('{"doc_id": 0}\n\n{"doc_id": 1}\n', "utf-8")
        assert count_of(samples, results) == 2
        assert count_of(None, results) == 2
    print("self-test ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test() if "--self-test" in sys.argv[1:] else main())
