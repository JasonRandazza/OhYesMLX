GOAL: port the Osaurus idle-residency pin from scripts/run_sweep_cache.sh into the three
older runners, which refuse to start Osaurus on drift since 0.25.5 set
modelIdleResidencyPolicy.seconds=30 (baseline says 900; Jason keeps 30 on the host).

READ FIRST: scripts/run_sweep_cache.sh (the pattern to copy: osaurus_state, osaurus_restore,
restore_and_check). Then scripts/run_grid.sh, scripts/run_grid_moe.sh,
scripts/run_sweep_prompt.sh as they are.

FILES YOU MAY EDIT: scripts/run_grid.sh, scripts/run_grid_moe.sh,
scripts/run_sweep_prompt.sh. Touch nothing else.

REQUIRED:
1. Each runner takes byte-exact copies of ~/.osaurus/config/server-runtime.json AND
   server.json at toggle time, pins modelIdleResidencyPolicy.seconds to 900 for the run,
   and restores both files byte-exact at the end AND on INT/TERM/HUP.
2. Verify restoration with `cmp` against the copies, NOT drift NONE (the host's 30 differs
   from the committed baseline by Jason's choice). run_sweep_prompt.sh's existing
   drift-NONE restore must be converted: it cannot pass while the host keeps 30.
3. run_sweep_prompt.sh already toggles the two cache flags; compose the residency pin with
   that toggle (both states pinned, same restore path). run_grid.sh / run_grid_moe.sh have
   no toggle today: pin residency around the Osaurus column only, leaving the other four
   columns byte-identical in behavior.
4. Keep every existing safeguard: sweep before each cell as well as after, Osaurus kills by
   FULL EXECUTABLE PATH only (`osaurus mcp` is Jason's long-running process), sleep 5.

ACCEPTANCE: `sh -n` clean on all three scripts. Do NOT run any of them (no measurements on
this machine from a worker, ever). No pytest, no git, no servers, no edits outside the
three files.

REPORT: what each script now does around the Osaurus column, and anything in
run_sweep_cache.sh's pattern that did not transfer cleanly.
