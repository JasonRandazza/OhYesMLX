#!/bin/sh
# 03-04: the ten-turn conversation, runtime axis. One run measures all five runtimes against one
# artifact -- oq4, the one format all five serve -- so every cell was driven under the run's own
# pins by construction, and the report is the runtime axis over the ten turns:
#
#   grid:  python -m ohyesmlx.cli grid "$OUT"/*/
#
# `--workloads multiturn` swaps the three pinned shapes for cli.DIALOGUE's ten turns, turn-01 to
# turn-10, each `max_tokens=128`. The history is the pinned conversation with fixed literal
# replies, not each runtime's own answers fed back, so turn N is the same prompt on every runtime.
#
# This study varies no header pin, so there is nothing here to join with `sweep --varying`: one run,
# five cells, one head-to-head table per turn.
set -u
cd /Users/jrazz/Dev/active/OhYesMLX
. "$(dirname "$0")/gridspec-35b.sh"
PY=/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python
export PATH="$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH"
OUT=${OUT:-results/multiturn}
DRY=${DRY:-0}
CELLS="oq4__mlxlm=$Q4,oq4__omlx=$Q4,oq4__optiq=$Q4,oq4__vmlx=$Q4,oq4__osaurus=$Q4"

if [ "$DRY" = 1 ]; then
  echo "DRY=1: printing the run command for $OUT -- nothing is started, no port is swept, no directory is written"
else
  mkdir -p "$OUT"
  # The runner owns its log, for the reason run_sweep_kvquant.sh states once: an exec redirect
  # cannot be unbound from the command the way `cmd & > file` can.
  exec > "$OUT/runner.log" 2>&1
fi

sweep() {
  for p in 8081 1337 8100 8080 8000; do
    h=$(lsof -ti:$p 2>/dev/null | head -1); [ -n "$h" ] && { echo "  sweeping port $p pid $h"; kill -9 "$h" 2>/dev/null; }
  done
  # By FULL EXECUTABLE PATH, never the name `osaurus`: `osaurus mcp` is Jason's.
  for h in $(pgrep -f "^/Applications/osaurus.app/Contents/MacOS/osaurus" 2>/dev/null); do
    echo "  sweeping stale osaurus app pid $h"; kill -9 "$h" 2>/dev/null
  done
  sleep 5
}

# No Osaurus settings are toggled in this study, so the trap has nothing to put back -- it sweeps
# so that a killed runner does not leave a runtime holding a port.
[ "$DRY" = 1 ] || trap 'echo "ABORTED $(date +%H:%M:%S)"; sweep; exit 130' INT TERM HUP

run_one() {  # $1 = the run's marker, which names its log; the rest is the run command line
  marker=$1; shift
  if [ "$DRY" = 1 ]; then
    echo "$PY -m ohyesmlx.cli run $*"
    return 0
  fi
  echo "=== $marker starting $(date +%H:%M:%S)"
  $PY -m ohyesmlx.cli run "$@" > "$OUT/log-$marker.log" 2>&1
  echo "=== $marker exit=$? $(date +%H:%M:%S)"
}

# Before as well as after: an Osaurus app relaunched between runs must not sit resident through
# another runtime's cell. The kill is logged.
[ "$DRY" = 1 ] || sweep
run_one multiturn --study runtime --cells "$CELLS" --workloads multiturn --results-dir "$OUT"
[ "$DRY" = 1 ] || sweep

echo "grid: $PY -m ohyesmlx.cli grid \"$OUT\"/*/"
echo "SWEEPDONE $(date +%H:%M:%S)"
