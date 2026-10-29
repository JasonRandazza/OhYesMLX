# Order: Osaurus's sequence cap follows the run's concurrency in the concurrency runner (Jason, 2026-09-27)
Why: Decision 129 made oMLX/OptiQ/vMLX caps follow the run's N. Osaurus takes no flags; its cap is the host
setting `concurrency.maxConcurrentSequences` in ~/.osaurus/config/server-runtime.json (host value 1;
docs/runtimes/osaurus.md §3.2; tracked by ohyesmlx/osaurus_settings.py:43 and config/osaurus-settings-baseline.json).
Files you may touch: scripts/osaurus-pin.sh, scripts/run_sweep_concurrency.sh, scripts/run_harden_validation.sh,
docs/runtimes/osaurus.md. Touch nothing else (no ohyesmlx/*.py, no tests/, no AGENTS.md, no .paul/, no ~/.osaurus
writes -- DRY runs only).
1. osaurus-pin.sh: add `osaurus_set_seqs N` -- sets concurrency.maxConcurrentSequences = N in $CONF (after
   osaurus_pin has taken the byte-exact backup; refuse with a message if it has not), then re-records the
   baseline exactly as osaurus_pin does. Restore stays byte-exact via the existing backup/cmp.
2. run_sweep_concurrency.sh: before each Osaurus run, `osaurus_set_seqs $n`, so N=1 keeps today's value 1 and
   N>1 matches the run. One comment there naming Decision 129 and runtimes.Omlx.start_command as where the rule
   is written. Nothing changes for the other four runtimes. DRY=1 prints the set per Osaurus run.
3. run_harden_validation.sh: `T=${T:-results/harden-2026-09-23}` so a new output dir needs no edit. No other change.
4. docs/runtimes/osaurus.md §3.2 row: record that the concurrency runner sets the key to the run's N and
   restores it. Also say, from the doc/app strings you can read (the app is Swift -- do not guess), whether
   `memorySafety.mode safe_auto` / `customMaxConcurrentSequences` could also cap sequences; if unknown, say so.
Acceptance: `sh -n` on every touched script; `DRY=1 RUNTIMES=osaurus OUT=$CLAUDE_JOB_DIR/tmp/x sh scripts/run_sweep_concurrency.sh`
output shown in your report; `T=... ` default unchanged when unset. No git, no server starts. Report DONE or BLOCKED.
