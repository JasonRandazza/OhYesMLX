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
# Resident engines and stale Osaurus processes are swept, by process rather than by port,
# before and after every column.
# Nothing else may run on this machine while this runs.
set -u
cd /Users/jrazz/Dev/active/OhYesMLX
. "$(dirname "$0")/gridspec-35b.sh"
PY=/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python
export PATH="$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH"
. "$(dirname "$0")/osaurus-pin.sh"

OUT=${OUT:-results/grid-35b}
mkdir -p "$OUT"
exec > "$OUT/runner.log" 2>&1

# One sweep, by process (055-03): scripts/sweep.sh, which needs $PY.
. "$(dirname "$0")/sweep.sh"

sweep || exit 1
for r in mlxlm omlx optiq vmlx osaurus; do
  eval "c=\$CELLS_$r"
  if [ -z "$c" ]; then
    echo "=== COLUMN $r SKIPPED (no cells defined or probe showed no live cells)"
    continue
  fi
  [ "$r" = osaurus ] && osaurus_pin
  sweep || exit 1
  echo "=== COLUMN $r starting $(date +%H:%M:%S)"
  $PY -m ohyesmlx.cli run --study format --cache-state off --cells "$c" --results-dir "$OUT" \
      > "$OUT/log-$r.log" 2>&1
  echo "=== COLUMN $r exit=$? $(date +%H:%M:%S)"
  sweep || exit 1
  [ "$r" = osaurus ] && osaurus_restore_check
  sleep 5
done

echo "=== RENDERING GRID $(date +%H:%M:%S)"
$PY -m ohyesmlx.cli grid "$OUT"/*/ --out "$OUT/grid.md" || echo "GRID RENDER WARNING: $?"
echo "35BGRIDDONE $(date +%H:%M:%S)"
