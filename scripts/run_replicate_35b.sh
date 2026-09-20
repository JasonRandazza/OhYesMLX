#!/bin/sh
# Plan 03-01 Replicate Run: Decisive cell pair for H3 (JANGTQ4 vs Stock 4-bit in vMLX)
# Design §2.5: reverse cell order (JANG first, stock second) to eliminate thermal aliasing.
set -u
cd /Users/jrazz/Dev/active/OhYesMLX
. "$(dirname "$0")/gridspec-35b.sh"
PY=/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python
export PATH="$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH"

OUT=results/grid-35b/replicate
mkdir -p "$OUT"

sweep() {
  for p in 8081 1337 8100 8080 8000; do
    h=$(lsof -ti:$p 2>/dev/null | head -1)
    [ -n "$h" ] && { echo "  sweeping port $p pid $h"; kill -9 "$h" 2>/dev/null; }
  done
  for h in $(pgrep -f "^/Applications/osaurus.app/Contents/MacOS/osaurus" 2>/dev/null); do
    echo "  sweeping stale osaurus app pid $h"; kill -9 "$h" 2>/dev/null
  done
  sleep 3
}

sweep
echo "=== REPLICATE vMLX starting (reversed order: JANG first, stock second) $(date +%H:%M:%S)"
REPL_VMLX="jangtq4__vmlx=$JG,stock4bit__vmlx=$S4"
$PY -m ohyesmlx.cli run --study format --cache-state off --cells "$REPL_VMLX" --results-dir "$OUT" \
    > "$OUT/log-vmlx-repl.log" 2>&1
rc=$?
echo "=== REPLICATE vMLX exit=$rc $(date +%H:%M:%S)"
sweep
echo "35BREPLDONE $(date +%H:%M:%S)"
