GOAL: the Phase 3 grid exists as five separate leaderboards and was never joined. Render it as
one grid, with the guards that make joining five separately-invoked runs legal.

FILES YOU MAY EDIT: ohyesmlx/report.py, tests/test_report.py.

READ FIRST: `docs/interfaces.md`, section "Phase 5 — the joined grid", subsections
"`ohyesmlx/report.py` — the grid", "The join guards" and "Provenance". They pin the signature,
the three entry states and all four guards. Do not deviate; report BLOCKED if one is wrong.

CONTEXT. Phase 3 ran `ohyesmlx run --study format` five times, once per runtime, producing five
run directories of twelve cells each (four formats x three workloads). 60 of 60 PASS. The
reading was pinned in Phase 3: a COLUMN (one runtime, many formats) is the format axis, a ROW
(one format, many runtimes) is the runtime axis, and the best cell across the whole grid is a
RECOMMENDATION, never an attribution. Your rendering must make which is which unmissable.

REQUIRED:

1. `render_grid(runs, *, rank: str = DEFAULT_RANK) -> str` where `runs` is
   `list[tuple[str, dict, list[dict]]]` — (run label, run header, rows from `summarize()`).
   You receive rows; you do not read files. One grid table per workload id, never averaged
   across workloads — the same rule `render_markdown` already obeys.

2. Rows are format labels, columns are runtime names, entries are the `rank` metric. The three
   entry states in the interface table must render differently: the number for a PASS, `FAIL`
   for a measured cell that did not clear a floor, `—` for a combination never measured. The
   matrix is ragged by design (no runtime loads JANG and the other formats both), so `—` is
   ordinary and must not read as a failure. A drift-annotated cell carries its marker into the
   entry beside the number — reuse the existing `DRIFT_ANNOTATION_PCT` logic, do not re-derive it.

3. All four join guards from the interface doc. Each raises ValueError naming BOTH run
   directories and the exact field that disagreed. Guard 1 (pins) compares every run-header
   field and every workload's `messages` and `max_tokens`. Guard 2 (duplicate cell) has no
   "latest wins" rule — which run is newer is not which run is right.

4. The provenance block above the tables: per column, its run label, runtime and version; then
   the pins all columns share. That block is the evidence the join was legal.

5. The axis readings, below the tables and labelled as what they are: per column, the format
   ordering (format axis); per row, the runtime ordering (runtime axis); and one best-cell line
   per workload labelled explicitly as a recommendation across a grid, not an attribution to
   either variable. Reuse `order_rows`. Reuse `_footnotes`.

WHAT YOU MUST NOT DO: no new metric, no blended score, no averaging across workloads, no
ranking that mixes the two axes into one number. Weighting speed against memory has no
objective answer and a single number would encode an arbitrary trade-off as though it were
measured. Do not change `summarize`, `render_markdown`, `order_rows`, `_held_constant`, or any
published figure — a row's numbers must be byte-identical whether it is rendered by
`render_markdown` or by `render_grid`, and a test must assert that.

ACCEPTANCE: pytest -q green from a 353 baseline, no regressions. Tests must cover: a legal
5-column join renders; each of the four guards fires with both directory names in the message;
a ragged cell renders `—` and a failed cell renders `FAIL` and the two are distinguishable in
the output text; a drift-annotated cell carries its marker; the same row rendered both ways
carries the same numbers. Red-check at least the four guards and report that you did.

Do not touch measure.py, cli.py, transport.py, runtimes.py, coherence.py. Do not start a server
or load a model. Another order is adding `measure.load_run` concurrently — you do not need it,
do not wait for it, and do not import it.
