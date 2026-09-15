GOAL: floors, one named ordering metric, and a per-cell metric card showing every value behind
the ranking. No blended score.

FILES YOU MAY EDIT: ohyesmlx/report.py, ohyesmlx/cli.py, tests/test_report.py ONLY.

THE CONTRACT IS PINNED in docs/interfaces.md — read "Floors and ordering — no blended score"
and the "Workloads" section above it, and implement exactly that.

CONTEXT YOU NEED: results are now per (cell, workload). CellResult carries workload_id, and the
three shapes are chat / prefill / decode. Figures are NEVER averaged across workloads — a
prefill-bound number averaged with a decode-bound one describes no workload that was run.

BUILD THREE THINGS.

1. FLOORS — pass/fail gates, never weighted, evaluated per (cell, workload):
   a. Coherence: the cell's status is already PASS/FAIL from the gate. Reuse it; add nothing.
   b. Every published metric present: also already decided by measure. Reuse it.
   c. Fits: peak_mb did not exceed available unified memory. `ohyesmlx/sample.py` already reads
      host memory — find what it exposes and reuse it; do NOT add a dependency or shell out. If
      it exposes no total-memory figure, say so in your report and leave floor (c) unimplemented
      rather than inventing a source.
   A cell failing any floor is excluded from the ranking and the table says WHICH floor and why.
   It is still shown — an excluded cell is a result, not an absence.

2. ORDERING — a `--rank <metric>` CLI option, default `decode_tps`. Valid choices are the
   metric keys a row already carries (decode_tps, aggregate_tps, ttft_p50_s, prefill_tps,
   itl_s, peak_mb, cold_load_s, disk_bytes). Ranking is per workload, so each workload's table
   is ordered independently. Lower-is-better metrics (ttft_p50_s, itl_s, peak_mb, cold_load_s,
   disk_bytes) must sort ascending and higher-is-better descending — get this right and test
   both directions. The chosen metric MUST be named in the table header. A row whose ranking
   metric is None ranks last and says why, never silently.

3. THE METRIC CARD — per (cell, workload), every measured value behind the ranking, rendered
   under the tables. This is the deliverable the user asked for by name: they want to see all
   the metrics that produced the ordering. Include the raw inputs (n measured, n requests,
   content deltas, token_source) as well as the derived figures, and the floor verdicts. Markdown,
   readable, no new dependency.

DO NOT build a composite or weighted score, a normalised 0-100 figure, or any single number
blending speed and memory. Weighting them has no objective answer, and a blended number would
encode an arbitrary trade-off as though it were measured. If you think one is needed, say so in
your report and build nothing.

ACCEPTANCE: pytest -q green from a 267 baseline. Tests must cover: a cell failing a floor is
excluded from the ranking, still shown, and names its floor; ranking direction correct for one
higher-is-better and one lower-is-better metric; the header names the metric; a None ranking
metric sorts last with a reason; each workload ranks independently; the card shows every metric
for every (cell, workload). Red-check it and report that you did.

Do not touch measure.py, runtimes.py, transport.py, coherence.py, token_counter.py, sample.py.
Do not start a server or load a model.
