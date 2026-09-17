GOAL: the drift marker beside a sweep entry is decode-rate drift, so on
`ohyesmlx sweep --rank ttft_p50_s` it reads as TTFT drift. Fix it in report.py.

READ FIRST: ohyesmlx/report.py render_sweep, _sweep_table, DRIFT_ANNOTATION_PCT,
RANK_METRICS, CONCURRENCY_DRIFT_SENTENCE; tests/test_report.py sweep tests. Decide from the
code whether the marker is printed per-entry in _sweep_table or reused from grid helpers.

FILES YOU MAY EDIT: ohyesmlx/report.py, tests/test_report.py. Touch nothing else.

REQUIRED:
1. When the rank metric is decode-derived (decode_tps and anything computed from decode
   rates), the marker prints exactly as today. When the rank metric is NOT decode-derived
   (ttft_p50_s and kin), entries print with NO drift marker — or with a correctly labeled
   one, your choice, but one rule for all non-decode ranks, documented in the docstring.
2. Every published grid (`ohyesmlx grid` over the five dense run dirs) renders
   byte-identical before and after. Verify with the real results/ dirs and paste the diff
   result (must be empty).
3. `results/sweep-prompt` and `results/sweep-cache` rendered with --rank ttft_p50_s lose the
   misleading marker; decode-ranked renders keep it.

ACCEPTANCE: pytest -q green from the 487 baseline. Tests: TTFT-ranked sweep entry carries no
decode-drift marker; decode-ranked sweep keeps it; the byte-identical grid check above.
Red-check the fix (revert, watch the new test fail with the misleading marker, restore) and
report it. Use /Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python. No git, no
servers, do not read or write results/ beyond rendering it.

REPORT: which rule you chose (drop vs label) and why, the before/after render check, and
anything else in render_sweep that mislabels a metric.
