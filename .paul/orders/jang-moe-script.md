GOAL: Author scripts/run_jang_moe.sh — the executable runner script for Plan 01-02 (MoE JANG Study on LFM2.5-8B-A1B across vMLX and Osaurus, plus grid join and 2-cell replication).

FILES YOU MAY EDIT:
scripts/run_jang_moe.sh only. Touch nothing else.

SPECIFICATION:
1. Shell: POSIX /bin/sh with `set -u` (deliberately no `set -e`, capture statuses and clean up Osaurus properly).
2. Working Directory: `/Users/jrazz/Dev/active/OhYesMLX`.
3. Python binary: `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python`.
4. PATH: prepend `$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin`.
5. Artifact paths (all in `$HOME/.cache/huggingface/hub`):
   - JG: `$H/models--JANGQ-AI--LFM2.5-8B-A1B-JANG_2L/snapshots/5fb82773427c2f25395de8821eff6d95e86feb53`
   - S4: `$H/models--mlx-community--LFM2.5-8B-A1B-MLX-4bit/snapshots/146590a491db88581884033023f51f6b49a27b89`
   - Q4: `$H/models--stamsam--LFM2.5-8B-A1B-oQ4/snapshots/acb4fd209565b7c05de287488416f4217820a3db`
   - QE: `$H/models--brainworkup--LFM2.5-8B-A1B-oQ4e/snapshots/88977e47cd1fe2eb5ec5bf5230d3de9868adef9e`
   - OQ: `$H/models--mlx-community--LFM2.5-8B-A1B-OptiQ-4bit/snapshots/5a5c595823cf26ab1068508eb5cf85816bb2db6b`

6. Cell definitions:
   - CELLS_vmlx: "stock4bit__vmlx=$S4,oq4__vmlx=$Q4,oq4e__vmlx=$QE,optiq__vmlx=$OQ,jang2l__vmlx=$JG"
   - CELLS_osaurus: "stock4bit__osaurus=$S4,oq4__osaurus=$Q4,oq4e__osaurus=$QE,optiq__osaurus=$OQ,jang2l__osaurus=$JG"

7. Output Directory:
   - OUT="results/grid-jang-moe"
   - Create directories: `mkdir -p "$OUT/replicate"`
   - Redirect runner stdout/stderr via `exec > "$OUT/runner.log" 2>&1` at script start.

8. CLI Invariant:
   - Every `cli run` invocation MUST pass `--cache-state off`:
     `$PY -m ohyesmlx.cli run --study format --cache-state off --cells "$CELLS" --results-dir "$DIR"`
     This records `"cache_state": "off"` in the run headers and ensures proper runtime cache flags.

9. Osaurus Cache Toggle & Restoration Protocol (per scripts/run_sweep_prompt.sh lines 45-94):
   - Config files:
     CONF="$HOME/.osaurus/config/server-runtime.json"
     SERVER="$HOME/.osaurus/config/server.json"
     CONF_ORIG="$CONF.grid-orig"
     SERVER_ORIG="$SERVER.grid-orig"
   - `osaurus_restore()`:
     Restores `$CONF_ORIG` -> `$CONF` and `$SERVER_ORIG` -> `$SERVER`.
     Runs `git checkout -- config/osaurus-settings-baseline.json`.
   - `osaurus_cache()` with argument `off`:
     If `$CONF_ORIG` doesn't exist, copies `$CONF` -> `$CONF_ORIG` and `$SERVER` -> `$SERVER_ORIG`.
     Installs trap: `trap 'echo "ABORTED -- restoring Osaurus settings"; osaurus_restore; exit 130' INT TERM HUP`.
     Restores from `.orig` first, then modifies via Python:
     * Sets `runtime['cache']['prefix']['enabled'] = False`
     * Sets `runtime['cache']['blockDisk']['enabled'] = False`
     * Sets `hardware.setdefault('modelIdleResidencyPolicy', {})['seconds'] = 900`
     Calls `$PY -c "from ohyesmlx import osaurus_settings as s; s.write_baseline()"` so the drift guard accepts the test baseline.
   - `restore_and_check()`:
     Calls `osaurus_restore()`.
     Verifies byte-exact with `cmp -s "$CONF" "$CONF_ORIG" && cmp -s "$SERVER" "$SERVER_ORIG"`.
     Fails closed (`exit 1`) if mismatch.
     Removes `.orig` files.

10. Process & Port Cleanup (`sweep` function):
   - Ports: 8081, 1337, 8100, 8080, 8000.
   - Osaurus leftovers swept by full executable path: `pgrep -f "^/Applications/osaurus.app/Contents/MacOS/osaurus"`. NEVER bare name `osaurus`.
   - `sleep 5`.

11. Execution Flow:
   - Pre-sweep.
   - Step 1: Run vMLX column:
     `column vmlx "$OUT" "$OUT/log-vmlx.log" "$CELLS_vmlx"`
     Extract `VMLX_DIR=$(newest_run_dir "$OUT")`.
   - Step 2: Sweep ports and stale runtimes.
   - Step 3: Osaurus column:
     `osaurus_cache off`
     `column osaurus "$OUT" "$OUT/log-osaurus.log" "$CELLS_osaurus"`
     Extract `OSAURUS_DIR=$(newest_run_dir "$OUT")`.
   - Step 4: Sweep, then `restore_and_check`.
   - Step 5: Join grid:
     `$PY -m ohyesmlx.cli grid "$VMLX_DIR" "$OSAURUS_DIR" --out "$OUT/grid.md"`
   - Step 6: 2-Cell Replication Pass:
     * Column order REVERSED from primary (design doc §2.5): Osaurus replicate FIRST, vMLX replicate SECOND.
     * Dynamic portable cell resolution: compute the best portable on `decode` from the primary column:
       For Osaurus: inspect `$OSAURUS_DIR` to find the non-JANG cell with highest `decode_tps` (fallback: `oq4`).
       For vMLX: inspect `$VMLX_DIR` to find the non-JANG cell with highest `decode_tps` (fallback: `stock4bit`).
       Construct REPL cells with `jang2l` and that best portable.
     * Run Osaurus replicate:
       `osaurus_cache off`
       `column osaurus-repl "$OUT/replicate" "$OUT/replicate/log-osaurus-repl.log" "$REPL_osaurus"`
       `sweep`
       `restore_and_check`
     * Run vMLX replicate:
       `column vmlx-repl "$OUT/replicate" "$OUT/replicate/log-vmlx-repl.log" "$REPL_vmlx"`
       `sweep`
   - Step 7: Print summary and exit 0 (or exit 1 if FAILED != 0).

12. Make script executable (`chmod +x scripts/run_jang_moe.sh`).

VERIFICATION:
Run `sh -n scripts/run_jang_moe.sh` to confirm shell syntax is clean.
Run `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q` to confirm suite is green.
Do NOT start any measurement or server during this task.
