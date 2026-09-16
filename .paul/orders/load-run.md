GOAL: nothing in this project can read a `results.jsonl` back. Five run directories hold the
Phase 3 grid and the only way to see it is to open five files by hand. Give `measure.py` the
exact inverse of what it writes.

FILES YOU MAY EDIT: ohyesmlx/measure.py, tests/test_measure.py.

READ FIRST: `docs/interfaces.md`, section "Phase 5 — the joined grid", subsection
"`ohyesmlx/measure.py` — reading a run back". It pins the signature and the one design rule.
Do not deviate from it; if you believe it is wrong, report BLOCKED and say why.

REQUIRED:

1. `load_run(path) -> tuple[dict, list[CellResult]]`. `path` is either a run directory or a
   `results.jsonl` inside one; accept both. Line 1 of the file is the run header and is
   returned as-is. Every line after it is one CellResult.

2. It is the inverse of `write_results` / `_record` (measure.py:~800). `Cell(**record["cell"])`
   and `Observation(**obs)` reconstruct by construction — that is why `_record` used `asdict`.
   Import Observation from transport.py; it is already imported there.

3. **The three derived fields are not read back.** `measured_count`, `warmup_count` and
   `drift` are recomputed from the observations, never taken from the file. A loader that
   trusted them would let a hand-edited file publish a drift its own samples do not support.
   Leave them in the written record — a `jq` reader wants them — and ignore them on read.

4. A file that is empty, or whose first line is not an object, or whose later lines are not
   records, raises ValueError naming the path and the line number. A truncated last line is
   the ordinary failure here (`write_results` is atomic, but a file copied mid-write is not),
   so say which line, not just "bad file".

ACCEPTANCE: pytest -q green from a 353 baseline, no regressions.

The test that matters is the **round-trip against real data**:
`results/grid/20260916T014210Z-format/results.jsonl` is a real 13-line Osaurus column in this
repo (results/ is gitignored, so read it, do not copy it into the test as a fixture — skip the
test with pytest.skip if the path is absent). For every record in it,
`_record(load_run(path)[1][i])` must equal the i-th parsed line exactly, dict for dict. That
one assertion covers every field you could have dropped. Also cover: a directory path and a
file path give the same result; the header comes back unchanged; a truncated final line raises
ValueError naming that line number; `drift`/`measured_count`/`warmup_count` in the file are
ignored — hand-edit them in an in-test copy to absurd values and assert the loaded object
recomputes the true ones.

Red-check the round-trip test and report that you did.

DO NOT change `_record`, `write_results`, `measured_drift`, or any measurement code. Do not
touch report.py, cli.py, transport.py, runtimes.py. Do not start a server or load a model.
This order adds a reader; it changes nothing that writes.
