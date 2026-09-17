GOAL: Phase 6 plan 06-02 — the cold/warm KV split. Add a `cache_state` run pin so one cell can
be measured with its prefix cache off and on, joined by `ohyesmlx sweep --varying cache_state`.
Also bring docs/interfaces.md up to date with the short-window fix.

READ FIRST: docs/research/2026-09-16-phase6-design.md "Cold versus warm KV"; docs/interfaces.md
06-01b/06-01c sections (the shape to copy); ohyesmlx/runtimes.py start commands (vMLX passes
--disable-prefix-cache/--disable-block-disk-cache today; find what mlx-lm 0.31.3 server, oMLX
0.6.4 and mlx-optiq 0.5.6 do by default and which flags control it, from their --help and
installed source); docs/research/2026-09-16-prompt-length-context-limits.md "prompt cache";
scripts/run_sweep_prompt.sh (Osaurus toggle).

FILES YOU MAY EDIT: ohyesmlx/cli.py, measure.py, report.py, runtimes.py, tests/*, docs/interfaces.md,
NEW scripts/run_sweep_cache.sh. Nothing else.

REQUIRED:
1. `ohyesmlx run ... --cache-state {off,on}`. Header pin `"cache_state": "off"|"on"`, or None when
   the flag is not given (today's runs; their cache state was per-runtime and not uniform —
   Osaurus grids ran with its cache ON — so absent must NOT read as "off"). Add to PIN_FIELDS,
   absent = None. Without the flag every start command is byte-identical to today.
2. Per runtime, `off` = prefix/KV reuse disabled, `on` = enabled, via start flags. Where a runtime
   has no flag for one state, a restart is not a way to turn a cache ON: the cell is N/A with the
   reason recorded (use the existing N/A path). Osaurus has no flag: its state comes from
   ~/.osaurus/config/server-runtime.json; the harness must not edit it, but must REFUSE (N/A with
   reason) when the live cache.prefix.enabled disagrees with the requested state. Document each
   runtime's mechanism, with the source line or help text, in interfaces.md.
3. `render_sweep` accepts varying="cache_state" (values ordered off, on). Workload messages are
   NOT relaxed for it.
4. scripts/run_sweep_cache.sh, modelled on run_sweep_prompt.sh: oq4 cell, five runtimes,
   --prompt-tokens 4096, each runtime `off` then `on`, results/sweep-cache/. For Osaurus: byte-exact
   copies of server-runtime.json AND server.json; for `off` flip cache.prefix.enabled and
   cache.blockDisk.enabled false; for BOTH states set server.json
   modelIdleResidencyPolicy.seconds to 900 (Osaurus 0.25.5 set 30, which unloads the model inside
   the 30 s cooldown); write_baseline() after each change; restore both files byte-exact and
   `git checkout -- config/osaurus-settings-baseline.json` at the end and on INT/TERM/HUP; verify with
   `cmp` against the copies (NOT drift NONE — the host's 30 differs from the committed baseline by
   Jason's choice). Sweep stale runtimes before and after each run, kill Osaurus by full path
   only. Print SWEEPDONE at the end. Do not run it.
5. interfaces.md: also document the short-window fix — `summarize(results, *, measured=None)`,
   `CellResult.lost_visit_reason`, `cold_load_after_lost_visit`, `measured_pin`, and `(n=K of N)`.

ACCEPTANCE: pytest -q green from 468. Tests: no flag → commands byte-identical for all five and
header cache_state None; each state's flags per runtime; N/A with reason where a state is
unsupported; Osaurus disagreeing live setting → N/A; guard 1 refuses joining on vs off in a grid;
render_sweep varying cache_state renders off before on and refuses differing messages;
`sh -n scripts/run_sweep_cache.sh`. Red-check the "absent is None, not off" test and report it.
Use /Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python.

A measurement is running on the machine: do NOT start servers, load models, or touch results/.
Run the full pytest at most twice. No git.

REPORT: per-runtime mechanism table (off / on / source), and anything in the design that turned
out wrong.
