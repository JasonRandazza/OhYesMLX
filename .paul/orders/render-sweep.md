GOAL: Phase 6 sweeps are N run directories differing in exactly one header pin, and nothing
renders them. Build `report.render_sweep` and an `ohyesmlx sweep` command, mirroring how
`render_grid` / `ohyesmlx grid` join runs today.

FILES YOU MAY EDIT: ohyesmlx/report.py, ohyesmlx/cli.py (the new subcommand ONLY),
tests/test_report.py, tests/test_cli.py. Touch nothing else.

READ FIRST: `docs/interfaces.md`, section "Phase 6 — a sweep is a pin, not an axis", plus
06-01b and 06-01c; then `render_grid`, `PIN_FIELDS`, `_check_pins` and `_grid` as they are.
Signature is pinned: `render_sweep(runs, *, varying: str, rank: str = DEFAULT_RANK) -> str`,
`runs` in the same shape `render_grid` takes. Report BLOCKED if the spec contradicts the code.

REQUIRED:

1. `varying` must be one of `PIN_FIELDS` that a sweep may vary: `concurrency` or
   `prompt_tokens`. Anything else raises ValueError.
2. Guard 1: every other pin compared exactly as `_check_pins` compares it today (reuse it,
   do not copy it). `varying` must take >= 2 distinct values across the runs, else ValueError.
   A `prompt_tokens` pin is keyed on its `target`; two runs with the same target but different
   `achieved` raise.
3. The workload half of guard 1: runs must agree on the workload set as today, EXCEPT that for
   `varying="prompt_tokens"` a workload's `messages` may differ (and only that field). For
   `varying="concurrency"` nothing about workloads is relaxed.
4. Guard 2: a (cell, workload, pin value) seen twice raises, as the grid's duplicate case does.
5. Output: title names the swept pin. One table per workload: cells down, pin values across in
   ascending order, each entry the `rank` metric (same formatting and `—`/FAIL conventions
   render_grid uses). For `prompt_tokens` column heads show target and achieved. Missing
   (cell, value) is `—`. A provenance block lists each run dir with its value of the swept pin.
6. When `varying="concurrency"` or any run pins concurrency > 1, the output carries this
   sentence verbatim: "At concurrency > 1, measured drift reads per-request rates: positive
   drift means the per-request rate was still moving, not that the cell was under-warmed."
7. `ohyesmlx sweep --varying {concurrency,prompt_tokens} [--rank M] [--out PATH] RUN_DIR...`
   loading run dirs exactly as `_grid` does; guard errors print `ohyesmlx sweep: <msg>` to
   stderr and exit non-zero.

WHAT MUST NOT CHANGE: `render_grid`'s output and guards, every metric, every run header.

ACCEPTANCE: `pytest -q` green from the 428 baseline. Tests cover: each ValueError in 1–4; a
prompt_tokens sweep whose messages differ renders; the same messages difference is REFUSED by
render_grid and by a concurrency sweep; columns ascend; missing cell is `—`; title and
provenance name the pin; the drift sentence present for concurrency and absent for a
prompt_tokens sweep at N=1; the CLI exit code on a guard error. Red-check the messages
relaxation (make it apply to all pins, watch the refusal test fail) and report that you did.

Do not start a server, load a model, or read/write results/.

ANSWER IN YOUR REPORT: which `rank` default makes sense for a prompt_tokens sweep given the one
workload is `prefill` with cap 64, and whether `DEFAULT_RANK` renders anything useful there.
Note: Osaurus's `usage.prompt_tokens` is chars/4, not tokens (see the research doc
2026-09-16-prompt-length-context-limits.md, "Measured"), so `prefill_tps` is not comparable
across runtimes; TTFT is. Do not change measure.py for it — just say what `rank` a prompt
sweep should use and confirm `render_sweep` supports it.
