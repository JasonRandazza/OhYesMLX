GOAL: Author scripts/probe_accuracy_cell.py, scripts/run_accuracy_dense.sh, and scripts/analyze_accuracy_dense.py for Plan 02-02 (Dense Accuracy Study: Qwen3.5-4B across vMLX and Osaurus, plus 3-cell MMLU replication pass).

FILES CREATED:
- scripts/probe_accuracy_cell.py
- scripts/run_accuracy_dense.sh
- scripts/analyze_accuracy_dense.py

SPECIFICATION:
1. Shell: POSIX /bin/sh with `set -u`.
2. Working Directory: `/Users/jrazz/Dev/active/OhYesMLX`.
3. Python binary: `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python`.
4. PATH: prepend `$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin`.
5. Benchmark tasks (per user decision resolving Spike §6.5):
   - MMLU generative: 40 items per subject * 57 subjects = 2,280 items, 5-shot multiturn.
   - GSM8K: 250 items, 5-shot multiturn.
   - IFEval: 250 items, 0-shot.
   - ARC-Challenge dropped due to upstream prompt/filter extraction defect.
6. Execution matrix:
   - Column A: vMLX across jang4s, stock4bit, oq4, oq4e (cache_state="off").
   - Column B: Osaurus across jang4s, oq4, oq4e, optiq (idle residency pinned to 900s, restored byte-exact).
   - Replicate pass: stock4bit__vmlx, jang4s__vmlx, jang4s__osaurus on MMLU 5-shot.
7. Verification & Gates:
   - vMLX scheduler patch sha256 verified (9710d2b9…).
   - Runtime logs captured to cell directories.
   - Sweep functions enforce port safety and stale process clearing by full executable path.

VERIFICATION:
- `sh -n scripts/run_accuracy_dense.sh` passed.
- `python scripts/probe_accuracy_cell.py --self-test` passed.
- `python scripts/analyze_accuracy_dense.py --self-test` passed.
- 495 repo tests passed.
