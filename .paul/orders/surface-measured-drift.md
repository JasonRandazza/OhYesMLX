GOAL: `measured_drift()` is computed into every result row and read by nothing. Surface it in
the report so a cell that moved 28% across its own measurement window cannot render identically
to one that moved 0.5%.

FILES YOU MAY EDIT: ohyesmlx/report.py, tests/test_report.py.

THE DEFECT. `measure.measured_drift()` (ohyesmlx/measure.py:218) writes a `drift` dict into
every row: `early_median_tps`, `late_median_tps`, `change_pct`, `n`. Grep `drift` in report.py
and the only hits are the word "drift" inside unrelated comments. It is recorded and unread —
the same shape as `runtime_version` before commit 7945067.

MEASURED, full grid re-run 2026-09-15 evening, per-column median `change_pct`:

  mlx-lm      +17.0%   (12 of 12 rows over 5%; range -1.3% to +28.4%)
  oMLX         +2.6%
  mlx-optiq    -0.0%
  vMLX         +0.5%

Every sign is positive: cells get FASTER across their window, which is under-warmup, not the
thermal slowdown the docstring reasons about. In the mlx-lm column the runtime is held constant
and drift still ranges -1.3% to +28.4% BETWEEN FORMATS. That is not a common-mode offset a
reader can subtract out; it lands differently on each format and so contaminates the ordering
that column is for.

REQUIRED:
1. `drift.change_pct` becomes a visible column on the leaderboard row and a line on the metric
   card, beside the decode rate it qualifies. A reader comparing two cells must be able to see
   that one of them was still climbing.
2. A drift floor, in the same style as the floors already in report.py: a cell whose
   `abs(change_pct)` exceeds a named module-level constant is annotated, NOT failed. Name the
   constant and put the measured per-column table above it as the comment justifying the
   number. Pick the threshold from the data above and say in your report why you chose it.
3. The docstring on `measured_drift` says a drifting cell is "the thermal curve the interleave
   exists to expose". That is one direction only and every row measured moved the other way.
   Correct it to describe both signs and what each means: negative = thermal throttle, positive
   = insufficient warmup.

DO NOT change the warmup budget, the visit plan, `measured_drift`'s arithmetic, or any
published figure. Whether mlx-lm needs a longer warmup is a measurement-design decision that is
not yours to make in this order — this order makes the existing number visible, nothing more.
A row's decode_tps must be byte-identical before and after your change; assert that in a test.

KNOWN LIMITATION, do not try to fix it here: with `measured=5`, `measured_drift` compares
median-of-2 against median-of-2 and discards the middle sample, so each `change_pct` is noisy.
The direction is trustworthy because it is unanimous across 48 rows; a single row's magnitude
is not. If your annotation wording implies more precision than a 2-vs-2 comparison supports,
reword it.

ACCEPTANCE: pytest -q green from a 340 baseline, no regressions. Tests must cover: a
high-drift row is annotated and still PASSes; a flat row is not annotated; a row with
`drift: null` (fewer than two rates) renders without raising; decode_tps and every other
published figure are unchanged for all three cases. Red-check it and report that you did.

Do not touch measure.py's arithmetic, transport.py, runtimes.py, coherence.py, cli.py. Do not
start a server or load a model.
