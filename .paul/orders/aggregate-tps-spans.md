GOAL: `report._aggregate_tps` sums per-request `total_s`, so at concurrency N it divides by
~N× the real wall clock. Rendering `results/sweep-conc/` shows oMLX `chat` aggregate
66.0 / 42.3 / 25.5 / 14.3 at N=1/2/4/8; the measured truth (docs/research/
2026-09-16-concurrency-omlx.md) is 66.0 / 66.5 / 66.8 / ... — flat. Make the row's
`aggregate_tps` use the batch spans 06-01b records.

FILES YOU MAY EDIT: ohyesmlx/report.py (`_aggregate_tps` and its call in `_row` ONLY),
tests/test_report.py. Touch nothing else.

READ FIRST: `docs/interfaces.md` "Phase 6 plan 06-01b — the concurrency pin" (batch spans,
`aggregate_tps` for a batch = its completion tokens over its span), `CellResult.batch_spans`
in measure.py, and how measure.py computes per-batch aggregate for warmup.

REQUIRED:
1. When the result has `batch_spans`: aggregate = measured completion tokens / sum(batch_spans).
   Match the observations-to-batches mapping measure.py uses; if measure.py already has a
   per-batch aggregate function, reuse it rather than re-deriving.
2. With no `batch_spans` (sequential records, and every record written before 06-01b): exactly
   today's behaviour. Every existing grid number must be byte-identical.
3. Delete the `ponytail:` ceiling comment it resolves.

ACCEPTANCE: `pytest -q` green from the 449 baseline. Tests: a result with 2 batches of 4
concurrent requests (per-request total_s 2.0 each, span 2.1 each) gives tokens/4.2, not
tokens/16; a result without spans gives today's value. Red-check the first test against the
old function and report it. Then run, and paste in your report, the output tables of:
`python -m ohyesmlx.cli sweep --varying concurrency --rank aggregate_tps results/sweep-conc/*/`
(read-only; do not write to results/). Use
`/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python`.

Do not start a server or load a model. No git.
