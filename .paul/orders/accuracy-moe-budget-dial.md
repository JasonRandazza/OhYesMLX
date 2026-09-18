GOAL: Update scripts/probe_accuracy_cell.py and scripts/run_accuracy_moe.sh to implement the pre-registered budget dial (MMLU limit=20 items/subject = 1,140 items; GSM8K limit=250; IFEval limit=250) for Plan 02-03 (MoE Accuracy Study: LFM2.5-8B-A1B).

FILES TO TOUCH:
- scripts/probe_accuracy_cell.py
- scripts/run_accuracy_moe.sh
- scripts/analyze_accuracy_moe.py (only if needed for sample count flexibility)

SPECIFICATION:
1. In `scripts/probe_accuracy_cell.py`:
   - Add `--mmlu-limit` argument (type=int, default=40).
   - In `run_cell`, if `mmlu_limit` is provided (or differs from 40), set `limit` for `mmlu_generative` to `mmlu_limit`, keeping GSM8K at 250 and IFEval at 250.
   - Keep existing CLI arguments (`--task`, `--limit`, `--no-disable-thinking`, `--replicate`, `--self-test`).
   - Preserve `--no-disable-thinking` and its handling: `lfm2` has `supports_instruct_mode=False` in vMLX and rejects `enable_thinking=false` with HTTP 400, so `--no-disable-thinking` is mandatory.
2. In `scripts/run_accuracy_moe.sh`:
   - In `run_cell`, pass `--mmlu-limit 20` and `--no-disable-thinking` to `scripts/probe_accuracy_cell.py`.
   - Ensure all 8 cells are configured:
     - Column A (vMLX): stock4bit__vmlx, jang2l__vmlx, oq4__vmlx, oq4e__vmlx, optiq__vmlx
     - Replicate (vMLX, MMLU only, reversed order): jang2l__vmlx_repl, stock4bit__vmlx_repl
     - Study 2C (Osaurus): jang2l__osaurus (host residency pinned to 900s, restored byte-exact)
3. Ensure offline self-tests pass:
   - `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python scripts/probe_accuracy_cell.py --self-test`
   - `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python scripts/analyze_accuracy_moe.py --self-test`
   - `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q`
4. Touch nothing else.
