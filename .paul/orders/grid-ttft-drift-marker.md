GOAL: (1) In `render_grid`, grid entries ordered by a non-decode rank (such as `ttft_p50_s`)
must NOT print the decode-drift marker beside non-decode numbers. (2) In `render_sweep`,
`CONCURRENCY_DRIFT_SENTENCE` must only be emitted when the table's rank is in
`DECODE_DERIVED_RANKS`. Fix both in report.py.

READ FIRST: ohyesmlx/report.py `_grid_table`, `render_grid`, `_entry`, `DECODE_DERIVED_RANKS`,
`CONCURRENCY_DRIFT_SENTENCE`, `render_sweep`; tests/test_report.py
`test_the_grids_entry_is_not_rank_sensitive`, `test_a_ttft_ranked_sweep_entry_carries_no_decode_drift_marker`.

FILES YOU MAY EDIT: ohyesmlx/report.py, tests/test_report.py. Touch nothing else.

REQUIRED:
1. In `_grid_table`, pass `drift_marker=rank in DECODE_DERIVED_RANKS` to `_entry(...)` so that
   non-decode ranks (such as `ttft_p50_s`) do NOT print the decode-drift marker beside non-decode
   numbers.
2. In `render_grid`, the paragraph mentioning "A cell whose drift moved more than 5% across its
   own window carries its marker beside its number..." must only be included when
   `rank in DECODE_DERIVED_RANKS`. When `rank not in DECODE_DERIVED_RANKS`, that sentence is
   omitted (or replaced with note that entries carry numbers alone without drift markers).
   CRITICAL: For the default rank (`decode_tps`), `render_grid` output MUST remain 100%
   byte-identical to today.
3. In `render_sweep`, `CONCURRENCY_DRIFT_SENTENCE` explains decode-drift markers on concurrent
   runs. Emit `CONCURRENCY_DRIFT_SENTENCE` ONLY when `rank in DECODE_DERIVED_RANKS` AND the
   concurrency condition is met (`varying == "concurrency"` or any run drove >1 request). When
   `rank not in DECODE_DERIVED_RANKS`, omit `CONCURRENCY_DRIFT_SENTENCE`.
4. Update/replace `test_the_grids_entry_is_not_rank_sensitive` in `tests/test_report.py` (which
   previously asserted that grid entries did keep drift on TTFT because sweep had been fixed in
   isolation) with tests asserting:
   - A grid entry with a decode rank (`decode_tps`) keeps the drift marker.
   - A grid entry with a non-decode rank (`ttft_p50_s`, etc.) omits the drift marker.
   - A sweep with a non-decode rank omits `CONCURRENCY_DRIFT_SENTENCE`, while decode-ranked keeps it.
5. Every published grid (`ohyesmlx grid` over the five dense run dirs:
   `results/grid/20260916T034308Z-format results/grid/20260916T061309Z-format results/grid/20260916T044750Z-format results/grid/20260916T051603Z-format results/grid/20260916T054434Z-format`)
   rendered with the default rank (`decode_tps`) MUST render byte-identical before and after.
   Verify with the real results/ dirs and report the diff.

ACCEPTANCE: pytest -q green from the 491 baseline.
Red-check the fix: verify new tests fail if the changes are reverted, then restore and pass.
Use `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q`.
No git operations, no starting servers.

REPORT: summary of edits in report.py and tests, the byte-identical check output, and pytest count.
