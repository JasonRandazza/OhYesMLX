GOAL: Author scripts/run_jang_dense.sh — the executable runner script for Plan 01-01 (Dense JANG Study: Qwen3.5-4B across vMLX and Osaurus, plus 2-cell replication and grid join).

FILES YOU MAY EDIT:
scripts/run_jang_dense.sh only. Touch nothing else.

SPECIFICATION:
1. Shell: POSIX /bin/sh with `set -u` (and `set -e` where appropriate).
2. Working Directory: `/Users/jrazz/Dev/active/OhYesMLX`.
3. Python binary: `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python`.
4. PATH: prepend `$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin`.
5. Artifact paths (all in `$HOME/.cache/huggingface/hub`):
   - S4: `models--mlx-community--Qwen3.5-4B-4bit/snapshots/0e7ffd5c629ef7719d4cbc04069232580bfa9d9c`
   - Q4: `models--RepublicOfKorokke--Qwen3.5-4B-oQ4/snapshots/3ae88a7d17b1c6bb71b795c1090948a82508fdb8`
   - QE: `models--uingei--Qwen3.5-4B-oQ4e/snapshots/2e232d525d5df5e7a6eece4b03b17087e6b3c3ac`
   - OQ: `models--mlx-community--Qwen3.5-4B-OptiQ-4bit/snapshots/6cb5bdfd0bf15f484881fb9f1ab6d7c840fddde9`
   - JG: `models--JANGQ-AI--Qwen3.5-4B-JANG_4S/snapshots/4567967a46cd9e9bf26d3bb491ddd422ad607775`

6. Cell definitions:
   - CELLS_vmlx="stock4bit__vmlx=$S4,oq4__vmlx=$Q4,oq4e__vmlx=$QE,jang4s__vmlx=$JG"
   - CELLS_osaurus="oq4__osaurus=$Q4,oq4e__osaurus=$QE,optiq__osaurus=$OQ,jang4s__osaurus=$JG"
   - REPL_vmlx="stock4bit__vmlx=$S4,jang4s__vmlx=$JG"
   - REPL_osaurus="oq4__osaurus=$Q4,jang4s__osaurus=$JG"

7. Output Directory:
   - `results/grid-jang-dense/`
   - Create directory `mkdir -p results/grid-jang-dense/replicate`
   - Runner log redirection: ensure caller-side or script-side logging writes to `results/grid-jang-dense/runner.log`.

8. Osaurus Pinning & Restoration Protocol (must match scripts/run_grid.sh):
   - Config files: `~/.osaurus/config/server-runtime.json` and `~/.osaurus/config/server.json`.
   - Backup byte-exact before touch: `server-runtime.json.grid-orig` and `server.json.grid-orig`.
   - Pin `modelIdleResidencyPolicy.seconds` to 900 (so model does not unload during 30s cooldown).
   - Traps for INT TERM HUP to restore immediately if interrupted.
   - Restore after Osaurus column and verify byte-exact with `cmp -s`. Fail closed if mismatch.
   - Sweep stale Osaurus instances by full executable path: `pgrep -f "^/Applications/osaurus.app/Contents/MacOS/osaurus"`. NEVER sweep by bare name `osaurus` (must preserve `osaurus mcp`).
   - Sweep ports: 8081, 1337, 8100, 8080, 8000 between columns.

9. Execution Flow:
   - Step 1: Run vMLX column:
     `$PY -m ohyesmlx.cli run --study format --cells "$CELLS_vmlx" --results-dir results/grid-jang-dense > results/grid-jang-dense/log-vmlx.log 2>&1`
   - Step 2: Sweep ports and stale runtimes.
   - Step 3: Pin Osaurus, run Osaurus column:
     `$PY -m ohyesmlx.cli run --study format --cells "$CELLS_osaurus" --results-dir results/grid-jang-dense > results/grid-jang-dense/log-osaurus.log 2>&1`
   - Step 4: Sweep ports, sweep Osaurus app, restore Osaurus settings and verify byte-exact with `cmp`.
   - Step 5: Join the two columns into `results/grid-jang-dense/grid.md`:
     Locate latest vmlx and osaurus run dirs in `results/grid-jang-dense/` and run:
     `$PY -m ohyesmlx.cli grid "$VMLX_DIR" "$OSAURUS_DIR" --out results/grid-jang-dense/grid.md`
   - Step 6: Run 2-cell replication pass into `results/grid-jang-dense/replicate`:
     * vMLX replicate: `$PY -m ohyesmlx.cli run --study format --cells "$REPL_vmlx" --results-dir results/grid-jang-dense/replicate > results/grid-jang-dense/replicate/log-vmlx-repl.log 2>&1`
     * Sweep ports
     * Osaurus replicate: pin, run `$PY -m ohyesmlx.cli run --study format --cells "$REPL_osaurus" --results-dir results/grid-jang-dense/replicate > results/grid-jang-dense/replicate/log-osaurus-repl.log 2>&1`, sweep, restore & verify cmp.
   - Step 7: Print summary and exit 0.

10. Make script executable (`chmod +x scripts/run_jang_dense.sh`).

VERIFICATION:
Run `sh -n scripts/run_jang_dense.sh` to confirm shell syntax is clean.
Run `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q` to confirm suite is green.
Do NOT start any measurement or server during this task.
