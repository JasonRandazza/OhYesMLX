"""Probe 06-01a: at concurrency N, what does a cell warming up look like?

`measure._settled` closes a warmup window when the median of the last five per-request decode
rates is within 3% of the median of the five before them. That rule was derived entirely from
sequential requests, and Phase 6's design says plainly that it must not be assumed to carry
over:

    _settled compares medians of per-request decode rates, and at N>1 those carry queueing
    variance on top of the runtime's own. Whether a concurrency sweep must warm on aggregate
    throughput instead is a question to be measured before any rule is pinned.

This is that measurement. It issues batches of N concurrent requests against one warm-started
runtime and prints, per batch, both candidate quantities:

  * the median per-request decode rate -- what `_settled` reads today
  * aggregate throughput -- completion tokens over the batch's wall-clock span, which is what
    a concurrency sweep actually publishes

Then it reports, for each, how many batches it would have taken to settle under the existing
3% two-window rule. If per-request rate settles as readily as aggregate does, the rule carries
over unchanged and 06-01b is simpler than feared. If it does not -- if queueing noise keeps
the per-request series from ever agreeing with itself, the way the prefill workload's noise
did at N=1 -- then a concurrency sweep warms on aggregate throughput and the rule needs a
second form.

    scripts/probe_concurrency_warmup.py [runtime] [N] [batches]
    scripts/probe_concurrency_warmup.py omlx 8 14

Nothing here is a published figure, and nothing here is written to results/. It answers one
question so that a rule can be pinned with a reason instead of a guess.
"""

from __future__ import annotations

import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ohyesmlx import cli, measure, runtimes, token_counter, transport  # noqa: E402

ARTIFACT = os.path.expanduser(
    "~/.cache/huggingface/hub/models--RepublicOfKorokke--Qwen3.5-4B-oQ4/snapshots/"
    "3ae88a7d17b1c6bb71b795c1090948a82508fdb8"
)


def batch(handle, workload, counter, n: int) -> tuple[list, float]:
    """*n* requests issued together. Returns their observations and the batch's wall span.

    One shared clock around the whole batch, because the aggregate is what the sweep
    publishes and summing per-request spans would count the overlap N times. Threads rather
    than processes: the transport is blocked on an SSE stream, not on the GIL.
    """
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=n) as pool:
        futures = [
            pool.submit(
                transport.chat,
                handle.base_url,
                handle.model_id,
                workload.messages,
                max_tokens=workload.max_tokens,
                temperature=0.0,
                seed=0,
                token_counter=counter,
                api_key=handle.api_key,
            )
            for _ in range(n)
        ]
        observations = [future.result() for future in futures]
    return observations, time.monotonic() - started


def settles_at(series: list[float]) -> int | None:
    """The batch index where `measure._settled` would have closed the window, or None."""
    for end in range(2 * measure.WARMUP_WINDOW, len(series) + 1):
        if measure._settled(series[:end]):
            return end
    return None


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "omlx"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    batches = int(sys.argv[3]) if len(sys.argv) > 3 else 14

    runtime = runtimes.RUNTIMES[name]
    workload = next(w for w in cli.workloads(measure) if w.id == "chat")
    counter = token_counter.TokenCounter(ARTIFACT)

    print(f"{name}, concurrency {n}, {batches} batches, workload `chat`\n")
    print(f"{'batch':>5}  {'per-request median':>18}  {'aggregate tok/s':>15}  {'span s':>7}  ok")

    per_request: list[float] = []
    aggregate: list[float] = []
    handle = runtime.start(ARTIFACT, ARTIFACT)
    try:
        for index in range(1, batches + 1):
            observations, span = batch(handle, workload, counter, n)
            rates = [
                rate for observation in observations
                if (rate := measure.decode_tps(observation)) is not None
            ]
            tokens = sum(o.completion_tokens or 0 for o in observations if measure.came_back(o))
            ok = sum(1 for o in observations if measure.came_back(o))

            median_rate = statistics.median(rates) if rates else None
            throughput = tokens / span if span > 0 else None
            per_request.append(median_rate)
            aggregate.append(throughput)
            print(
                f"{index:>5}  {median_rate if median_rate is None else f'{median_rate:18.1f}'}"
                f"  {throughput if throughput is None else f'{throughput:15.1f}'}"
                f"  {span:7.2f}  {ok}/{n}"
            )
    finally:
        handle.stop()

    print("\nUnder the existing two-window 3% rule:")
    for label, series in (("per-request median", per_request), ("aggregate tok/s", aggregate)):
        where = settles_at(series) if all(v is not None for v in series) else None
        verdict = f"settles at batch {where}" if where else f"NEVER settles in {batches} batches"
        print(f"  {label:20} {verdict}")

    print(
        "\nIf per-request never settles and aggregate does, a concurrency sweep warms on\n"
        "aggregate throughput and `_settled` needs a second form. If both settle, the rule\n"
        "carries over unchanged."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
