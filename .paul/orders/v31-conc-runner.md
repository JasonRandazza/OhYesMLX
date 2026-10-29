# Order: concurrency sweep runner on the seedless harness
Create scripts/run_sweep_concurrency.sh. Touch nothing else. Never run it without DRY=1.
Model it on scripts/run_sweep_mtp.sh (DRY=1, exec-owned runner.log, sweep() of ports + stale Osaurus by FULL
executable path, trap, run_one, join helper that runs `sweep --varying concurrency` at the end) and source
scripts/osaurus-pin.sh around the Osaurus runs exactly as scripts/run_sweep_kvquant.sh does.
Subject: Qwen3.5-4B-oQ4, `$Q4` from scripts/gridspec.sh; cells oq4__<runtime> for mlxlm omlx optiq vmlx osaurus
(RUNTIMES= override, default all five). Values: `--concurrency 1 2 4 8` (read `ohyesmlx/cli.py run --help`
for the flag's exact spelling), direction alternating per runtime (ascending, descending, ...) so thermal drift
does not alias onto the pin. One run per (runtime, level): `run --study format --cells oq4__<r>=$Q4
--concurrency N --results-dir $OUT/oq4__<r>`; OUT default results/sweep-conc-seedless. Join each runtime's
four runs to $OUT/sweep-oq4__<r>.md, skipping a join whose glob matches nothing.
Header comment: why this exists (Decision 128 in .paul/STATE.md: no seed at temperature 0, so mlx-lm/OptiQ
now take their batching path; supersedes results/sweep-conc and results/sweep-conc8 which were seeded).
Acceptance: `sh -n`; show the full DRY=1 output (20 run lines, 5 join lines). No git, no pytest, no runtimes.
Report DONE or BLOCKED.
