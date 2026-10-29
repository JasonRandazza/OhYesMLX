# Order: runner scripts run their joins; one Osaurus pin (v3.1)
Files you may touch: scripts/*.sh only. Touch nothing else. Never run a runner without DRY=1.
1. run_sweep_kvquant.sh, run_sweep_mtp.sh, run_sweep_streaming.sh, run_multiturn.sh print their
   `join:` commands and never run them. After the runs (non-DRY), run each join and write it to
   `$OUT/<name>.md` (the names already used: results/sweep-kvquant/sweep-p16384.md / -p32768.md,
   results/sweep-mtp*/sweep-<cell>.md, results/sweep-streaming/sweep.md, results/multiturn/grid.md);
   skip a join whose glob matches no directory (PAIRS/RUNTIMES/CELLS subsets). DRY=1 keeps printing.
2. scripts/osaurus-pin.sh carries the Osaurus settings pin once. run_grid*.sh and run_sweep_cache*.sh
   carry inline copies. Diff each inline copy against osaurus-pin.sh; where the semantics are identical,
   replace it with a source + osaurus_pin/osaurus_restore_check call. Where they differ (e.g. a cache
   sweep whose variable IS the Osaurus cache), leave it and explain in your report. Remove the
   `# ponytail:` note in osaurus-pin.sh only if no copy remains.
Acceptance: `sh -n` on every touched script; `DRY=1` output of each touched runner identical before and
after except for added join lines (show the diff). No git, no pytest needed. Report DONE or BLOCKED.
