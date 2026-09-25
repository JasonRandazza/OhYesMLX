#!/bin/sh
# The 35B MoE grid (Plan 03-01): one column per runtime, --study format holding the runtime constant.
#
# Pinned:
#   --cache-state off
#   --results-dir results/grid-35b
#
# Around Osaurus:
#   scripts/osaurus-pin.sh is the one definition of this pin -- both ~/.osaurus/config files are
#   copied byte-exact, modelIdleResidencyPolicy.seconds is pinned to 900, cache.prefix.enabled and
#   cache.blockDisk.enabled are pinned to false, the baseline is re-recorded and both files are
#   restored byte-exact afterwards, verified with `cmp`.
#
# Ports and stale Osaurus processes are swept before and after every column.
# Nothing else may run on this machine while this runs.
set -u
cd /Users/jrazz/Dev/active/OhYesMLX
. "$(dirname "$0")/gridspec-35b.sh"
PY=/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python
export PATH="$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH"
. "$(dirname "$0")/osaurus-pin.sh"

OUT=${OUT:-results/grid-35b}
mkdir -p "$OUT"
exec > "$OUT/runner.log" 2>&1

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
for r in mlxlm omlx optiq vmlx osaurus; do
  eval "c=\$CELLS_$r"
  if [ -z "$c" ]; then
    echo "=== COLUMN $r SKIPPED (no cells defined or probe showed no live cells)"
    continue
  fi
  [ "$r" = osaurus ] && osaurus_pin
  sweep
  echo "=== COLUMN $r starting $(date +%H:%M:%S)"
  $PY -m ohyesmlx.cli run --study format --cache-state off --cells "$c" --results-dir "$OUT" \
      > "$OUT/log-$r.log" 2>&1
  echo "=== COLUMN $r exit=$? $(date +%H:%M:%S)"
  sweep
  [ "$r" = osaurus ] && osaurus_restore_check
  sleep 5
done

echo "=== RENDERING GRID $(date +%H:%M:%S)"
$PY -m ohyesmlx.cli grid "$OUT"/*/ --out "$OUT/grid.md" || echo "GRID RENDER WARNING: $?"
echo "35BGRIDDONE $(date +%H:%M:%S)"
