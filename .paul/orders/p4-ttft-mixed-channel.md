## Order: refuse cross-runtime TTFT orderings when rows mix timing channels

Jason's decision (2026-09-24): on the runtime axis, a TTFT ordering across rows timed on
different channels (content vs reasoning, see `transport.timing_channel` and
`report._reasoning_timed_note`) compares two definitions and is refused, the same way
Decision 120 / `CROSS_RUNTIME_UNCOMPARABLE` refuses `peak_mb` and `cold_load_s`.

Files you may touch: `ohyesmlx/report.py`, `tests/test_report.py`. Touch nothing else.

Acceptance criteria:
1. One constant in `report.py` names the rank metrics whose value depends on the timing
   channel. `ttft_p50_s` is in it. Decide from the code whether `prefill_tps` (and anything
   else in `RANK_METRICS`) is computed from TTFT; include it only if it is, and say which in
   your report. The rationale is written once, at that constant.
2. A row is "mixed" when its measured requests were not all timed on one channel; a group is
   mixed when its rows do not all share one channel. Decide the test from the recorded
   `reasoning_timed_note` / observations; a partly-reasoning row counts as its own channel.
3. `_ordering(..., key="runtime")` for such a rank over a mixed group: list values
   alphabetically by runtime with no positions (as the uncomparable branch does), and the
   runtime-axis section prints one `>` note naming why. An unmixed group still orders.
4. `_recommendation` returns the "none" style refusal (a sentence naming the reason) when the
   rank is channel-dependent and the workload's rows mix channels. Unmixed: unchanged.
5. Format-axis orderings (one runtime) are unchanged.
6. Tests: mixed group → no ordering + note + no recommendation; unmixed → ordering intact;
   a non-channel rank (`decode_tps`) over a mixed group → ordering intact. Red-check them.
7. Suite green; baseline is 543.
