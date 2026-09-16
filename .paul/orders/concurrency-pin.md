GOAL: the harness can only issue requests one at a time, so Phase 6's concurrency sweep cannot
be run at all. Add concurrency as a run pin.

FILES YOU MAY EDIT: ohyesmlx/measure.py, tests/test_measure.py.

READ FIRST: `docs/interfaces.md`, section "Phase 6 plan 06-01b — the concurrency pin", and the
section above it, "Phase 6 — a sweep is a pin, not an axis". They pin the signature, the batch
semantics, the new field and the warmup change. Do not deviate; report BLOCKED if one is wrong.

REQUIRED:

1. `run_cells(..., concurrency: int = 1, ...)`. Refuse `concurrency < 1`. The run header gains
   `"concurrency"`, so a join can compare it.

2. `measured` counts BATCHES, not requests. At `concurrency=1` a batch is one request and the
   existing behaviour must be byte-identical -- that equivalence is what keeps every number
   measured so far comparable, and a test must assert it: same seed, same responder, a run at
   `concurrency=1` produces the same record as one that never heard of concurrency.

3. A batch is N requests issued together under ONE clock, via
   `concurrent.futures.ThreadPoolExecutor` around the existing `transport.chat`. No new
   dependency, and do NOT re-implement the stream reader -- one definition of TTFT, one decode
   window, one Observation. Every request's observation is recorded, so a cell at N=8 with
   `measured=9` has 72 observations.

4. New `CellResult` field and record field `batch_spans: list[float]` -- wall-clock seconds per
   measured batch, one entry per batch. `load_run` reads it leniently, the way `warmup_plateau`
   is read: a record written before concurrency existed has no batch spans and `[]` is exactly
   true of it. Do NOT reconstruct a sequential record's spans from per-request totals: a gap
   between two sequential requests belongs to neither.

5. Warmup at `concurrency > 1` settles on AGGREGATE throughput per batch, not per-request decode
   rates -- same `_settled`, same constants, different series. Measured in 06-01a: at N=8 the
   per-request series swings +/-11% with no trend and never settles in sixteen batches, while
   aggregate settles at batch 12. At `concurrency=1`, per-request rates are used exactly as
   today.

WHAT MUST NOT CHANGE: the floors, the coherence gate, `measured_drift`, `decode_tps`,
`prefill_tps`, `itl_s`, and every per-request figure. A concurrent cell's requests are judged
one at a time exactly as a sequential cell's are -- a fast cell emitting garbage is a failed
cell at any concurrency. Do not touch report.py, cli.py, transport.py, runtimes.py.

ACCEPTANCE: pytest -q green from a 403 baseline, no regressions. Tests must cover: a
`concurrency=1` run is byte-identical to today's (the assertion that matters most); a
`concurrency=4` run issues four requests per batch and records four observations per batch and
one span; `measured=3` at N=4 gives 12 observations and 3 spans; the header carries the pin;
`batch_spans` round-trips through `load_run` and a record lacking it loads as `[]`; a batch
whose requests overlap has a span shorter than the sum of their totals (that is the whole
reason for the shared clock); warmup at N>1 settles on aggregate and at N=1 on per-request.

Red-check the byte-identical test and the shared-clock test, and report that you did.

Do not start a server or load a model -- a real sweep is the coordinator's to run.

ANSWER IN YOUR REPORT: with `measured` counting batches, what does the visit plan's quota split
mean at N=8, and does `measured_drift` -- which reads `observations` -- still compare what its
docstring says it compares when those observations arrive 8 at a time?
