#!/bin/sh
# Plan 03-01 Replicate Run: Decisive cell pair for H3 (JANGTQ4 vs Stock 4-bit in vMLX)
# Design §2.5: reverse cell order (JANG first, stock second) to eliminate thermal aliasing.
set -u
cd /Users/jrazz/Dev/active/OhYesMLX
. "$(dirname "$0")/gridspec-35b.sh"
PY=/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python
export PATH="$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH"

OUT=results/grid-35b/replicate
mkdir -p "$OUT"

# One sweep, by process (055-03): scripts/sweep.sh, which needs $PY.
. "$(dirname "$0")/sweep.sh"

sweep || exit 1
echo "=== REPLICATE vMLX starting (reversed order: JANG first, stock second) $(date +%H:%M:%S)"
REPL_VMLX="jangtq4__vmlx=$JG,stock4bit__vmlx=$S4"
$PY -m ohyesmlx.cli run --study format --cache-state off --cells "$REPL_VMLX" --results-dir "$OUT" \
    > "$OUT/log-vmlx-repl.log" 2>&1
rc=$?
echo "=== REPLICATE vMLX exit=$rc $(date +%H:%M:%S)"
sweep || exit 1
echo "35BREPLDONE $(date +%H:%M:%S)"
