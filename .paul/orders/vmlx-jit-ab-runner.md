GOAL: Implement vMLX JIT A/B experiment runner script and runtime toggle support.

CONTEXT:
Milestone v2 Candidate 2 measures the single-variable impact of `--enable-jit` vs `--no-jit` on `vMLX 1.6.59` on identical JANG weights across dense (`Qwen3.5-4B-JANG_4S`) and MoE (`LFM2.5-8B-A1B-JANG_2L`).
Currently, `Vmlx.start_command` in `ohyesmlx/runtimes.py` hardcodes `"--no-jit"`.
We need an environment-variable toggle `OHYESMLX_VMLX_ENABLE_JIT` so that setting `OHYESMLX_VMLX_ENABLE_JIT=1` emits `"--enable-jit"` instead of `"--no-jit"`, while defaulting to `"--no-jit"` when unset or `"0"` (preserving 100% byte-identity with existing pinned commands).

FILES TO TOUCH:
- ohyesmlx/runtimes.py
- tests/test_runtimes.py
- scripts/run_vmlx_jit_ab.sh

SPECIFICATION:
1. Edit `ohyesmlx/runtimes.py`:
   - In `Vmlx.start_command`:
     Check `os.environ.get("OHYESMLX_VMLX_ENABLE_JIT") == "1"`.
     If true, pass `("--enable-jit",)`.
     Otherwise, pass `("--no-jit",)`.
     Keep all other flags and order untouched. Note: import `os` is already present or import at top level if needed.

2. Edit `tests/test_runtimes.py`:
   - Add a test `test_vmlx_start_command_honors_enable_jit_env_var(monkeypatch)`:
     Verify that when `OHYESMLX_VMLX_ENABLE_JIT` is "1", `RUNTIMES["vmlx"].start_command(ARTIFACT, HF_ID)` contains `"--enable-jit"` and does not contain `"--no-jit"`.
     Verify that when unset or "0", it matches `TODAY["vmlx"]` exactly.

3. Create `scripts/run_vmlx_jit_ab.sh`:
   - Standalone executable bash script (`chmod +x`).
   - Sets:
     `PY=/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python`
     `export PATH="$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH"`
     `H=$HOME/.cache/huggingface/hub`
     `JG="$H/models--JANGQ-AI--Qwen3.5-4B-JANG_4S/snapshots/4567967a46cd9e9bf26d3bb491ddd422ad607775"`
     `JM="$H/models--JANGQ-AI--LFM2.5-8B-A1B-JANG_2L/snapshots/5fb82773427c2f25395de8821eff6d95e86feb53"`
     `CELLS="jang4s__vmlx=$JG,jang2l__vmlx=$JM"`
     `OUT=results/vmlx-jit-ab`
   - Include sweep function:
     Sweep ports 8081, 1337, 8100, 8080, 8000 (kill -9).
     Sweep stale Osaurus by exact pattern `^/Applications/osaurus.app/Contents/MacOS/osaurus` (never bare `osaurus`).
   - Logging:
     Redirect top-level runner stdout/stderr to `$OUT/runner.log`.
   - Execution sequence:
     1. Initial sweep.
     2. Column 1 (JIT OFF):
        `OHYESMLX_VMLX_ENABLE_JIT=0 $PY -m ohyesmlx.cli run --study format --cells "$CELLS" --results-dir "$OUT/jit-off"`
     3. Post-column sweep and 30-second thermal cooldown.
     4. Column 2 (JIT ON):
        `OHYESMLX_VMLX_ENABLE_JIT=1 $PY -m ohyesmlx.cli run --study format --cells "$CELLS" --results-dir "$OUT/jit-on"`
     5. Final sweep.
     6. Print completion message and locations of both result directories.

VERIFICATION:
- Run `bash -n scripts/run_vmlx_jit_ab.sh`
- Run `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q`
- Touch nothing else. Do NOT execute the benchmark script (measurement is reserved for the coordinator).
