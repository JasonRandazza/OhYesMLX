#!/bin/sh
# The MoE grid: one column per runtime, --study format holding the runtime constant.
#
# Same structure as run_grid.sh, against gridspec-moe.sh's cells. The PATH export is not
# optional: mlx_lm.server lives in its own venv, and a probe launched without it reported
# mlx-lm failing on all five formats -- see docs/research/2026-09-16-moe-loadability-probe.md.
#
# Nothing else may run on this machine while this runs. Not a test suite, not a git
# operation. That rule cost a column on 2026-09-16.
set -u
cd /Users/jrazz/Dev/active/OhYesMLX
. "$(dirname "$0")/gridspec-moe.sh"
PY=/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python
export PATH="$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH"
for r in mlxlm omlx optiq vmlx osaurus; do
  eval "c=\$CELLS_$r"
  echo "=== COLUMN $r starting $(date +%H:%M:%S)"
  $PY -m ohyesmlx.cli run --study format --cells "$c" --results-dir results/grid-moe \
      > "results/grid-moe/log-$r.log" 2>&1
  echo "=== COLUMN $r exit=$? $(date +%H:%M:%S)"
  for p in 8081 1337 8100 8080 8000; do
    h=$(lsof -ti:$p 2>/dev/null | head -1); [ -n "$h" ] && { echo "  sweeping port $p pid $h"; kill -9 "$h" 2>/dev/null; }
  done
  sleep 5
done
echo "MOEGRIDDONE $(date +%H:%M:%S)"
