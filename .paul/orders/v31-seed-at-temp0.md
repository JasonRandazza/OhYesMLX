# Order: omit the request seed at temperature 0 (approved by Jason 2026-09-26)
Why: a seeded request takes mlx-lm's and OptiQ's sequential path (mlx_lm server.py:685-686, optiq
serve.py; docs/runtimes/mlx-lm.md, docs/runtimes/optiq.md ~1310-1319), so the harness never measures their
batching path. At temperature 0 decoding is greedy and the seed changes no token. Exception: OptiQ's MTP
engine is reached only on the sequential path, so an OptiQ cell with mtp_depth 1-3 must keep sending it.
Files you may touch: ohyesmlx/measure.py, ohyesmlx/runtimes.py, ohyesmlx/report.py (only if a new row key
needs rendering/contract), README.md, docs/interfaces.md, docs/runtimes/{mlx-lm,optiq}.md, tests/test_measure.py,
tests/test_runtimes.py, tests/test_report.py. Touch nothing else (not AGENTS.md, not .paul/).
1. One definition: `Runtime.request_seed(mtp_depth) -> int | None` returning None when TEMPERATURE == 0
   and SEED otherwise; `Optiq` overrides to return SEED for mtp_depth in MTP_DEPTHS[1:]. The rationale is
   written once, at that method. `measure._request` asks it instead of passing SEED.
2. Header: `seed` records the policy for ordinary cells -- None at temperature 0 -- so every new run
   refuses to join an old seed-0 run (the existing pin guard does this; prove it with a test). Each result
   row records the seed actually sent (a row key, e.g. `request_seed`), so an OptiQ MTP depth row says 0.
   Document the key in docs/interfaces.md.
3. Read oMLX's and vMLX's shipped Python for how a request `seed` is used (bundle paths are in
   docs/runtimes/{omlx,vmlx}.md). Report, with file:line, whether omitting it changes their request path.
   Osaurus is Swift -- say "not readable" rather than guess. Report only; no code for this item.
4. README "Every run pins temperature 0 and a fixed seed" and the two runtime docs: say what is sent now.
Acceptance: tests fail if reverted (red-check each item 1-2); absent-pin start commands unchanged; suite green
(/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q). No git, no server starts.
Report DONE or BLOCKED.
