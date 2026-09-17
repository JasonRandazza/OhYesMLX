GOAL: runners own their log so a caller-side redirect can never leave an empty runner.log again (Jason 2026-09-17: apply hardening).

READ FIRST: scripts/run_sweep_prompt.sh lines 17-23 and scripts/run_sweep_cache.sh lines 22-23 (mkdir -p $OUT sites); the diagnosis in .paul/orders/empty-runner-log.md tail.

FILES YOU MAY EDIT: scripts/run_sweep_prompt.sh, scripts/run_sweep_cache.sh. Nothing else.

REQUIRED:
1. After mkdir -p "$OUT" add exec > "$OUT/runner.log" 2>&1 so progress echoes land regardless of caller redirect. Per-cell > "$OUT/log-*.log" 2>&1 redirects override per-command and keep working.
2. Keep trap/restore/cmp behavior byte-identical otherwise. Note tradeoff in comment: live progress reaches only the file, tail it.
3. Do NOT touch run_grid.sh/run_grid_moe.sh (no OUT var, different launch shape; separate order if wanted).

ACCEPTANCE: sh -n clean on both scripts. No pytest (scripts only), no git, no servers, never run them.
REPORT: the two added lines with file:line and sh -n result.
