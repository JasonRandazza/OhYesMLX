Scope: Read-only metric-correctness review of the six specified modules against `docs/interfaces.md` and `AGENTS.md`; test baseline/current: 497 passed.

### F1 [high] Failed rows still publish numeric summary metrics
Where: `ohyesmlx/measure.py:976-1023`; `ohyesmlx/report.py:707-764, 1150-1192`
Evidence:
```python
# measure.py:979-982
    A cell that produced no language is FAIL however fast it was, and a FAILed cell is not
    a result: no tok/s, TTFT, ITL or throughput figure is read from it. Its observations —

# measure.py:989-998
    failures = [
        observation for observation in result.observations if not came_back(observation)
    ]
    if failures:
        result.status = "FAIL"
        result.reason = (
            f"{len(failures)} of {len(result.observations)} measured requests failed; "
            f"first: {failures[0].error}"
        )
        return

# report.py:752-764
        "ttft_p50_s": percentile(ttft, 50),
        "ttft_p90_s": percentile(ttft, 90) if n >= MIN_PERCENTILE_N else None,
        "ttft_p99_s": percentile(ttft, 99) if n >= MIN_PERCENTILE_N else None,
        "itl_s": median(itl),
        "decode_tps": median(decode),
        "drift": drift,
        "aggregate_tps": _aggregate_tps(samples, result.batch_spans),
        "prefill_tps": median(prefill),
        "cold_load_s": result.cold_load_s,
        "first_request_s": result.first_request_s,
        "peak_mb": (result.memory or {}).get("peak_mb"),
        "disk_bytes": result.disk_bytes,
```
Failure: When a cell has at least one failed measured request mixed with valid requests, `_set_status` correctly marks it `FAIL`, but `_row` still derives TTFT, per-request and aggregate rates from the valid subset. `_cells` renders those values in the leaderboard alongside `FAIL`; the report's own policy says failed cells contribute no published figures. This is especially misleading for aggregate throughput because it divides valid-request tokens by spans including failed batches.
Fix: Suppress the measured metric fields for non-`PASS` rows in the summary/rendering path; keep every raw observation and the failure reason on the record/card.

### F2 [medium] One-delta streams feed unsupported rates into drift and warmup
Where: `ohyesmlx/measure.py:268-279, 301-319, 811-840`; `ohyesmlx/report.py:730-733, 777`
Evidence:
```python
# docs/interfaces.md:295-303
# DOMAIN: all three require content_event_count >= 2.

# measure.py:274-279
    if observation.ttft_s is None or observation.last_content_s is None:
        return None
    span = observation.last_content_s - observation.ttft_s
    if span <= 0 or not observation.completion_tokens:
        return None
    return observation.completion_tokens / span

# measure.py:314-319
    rates = [rate for observation in observations if (rate := decode_tps(observation)) is not None]
    if len(rates) < 2:
        return None
    half = len(rates) // 2
    early = statistics.median(rates[:half])
    late = statistics.median(rates[-half:])

# measure.py:833-840
    if concurrency == 1:
        return decode_tps(observations[0])
    if span <= 0 or not all(came_back(observation) for observation in observations):
        return None
    tokens = sum(observation.completion_tokens or 0 for observation in observations)
    if not tokens:
        return None
    return tokens / span
```
Failure: For single-delta observations with positive token counts and nonzero timestamp noise, `decode_tps` returns an unsupported rate because it never checks `content_event_count`. `measured_drift` consumes those rates and `_row` publishes drift even though `_per_request` correctly omits decode, ITL and prefill rates for fewer than two deltas. At concurrency 1, `_warmup_rate` also accepts that unsupported rate and can certify a plateau from whole-response latencies rather than decode windows. The resulting drift and plateau are wrong numbers, not merely omitted metrics.
Fix: Apply the `content_event_count >= 2` domain guard before admitting rates into drift and warmup calculations; preserve one-delta TTFT and aggregate throughput as specified.
