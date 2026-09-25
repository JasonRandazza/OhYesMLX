#!/bin/sh
# 03-03: the expert-streaming sweep. OptiQ and vMLX are the two runtimes that accept the flag on
# this repository's 35B formats, each through its own switch, and the pin moves off/on:
#
#   OptiQ: --stream-experts for `on`, --no-stream-experts for `off`
#   vMLX:  --flash-moe for `on`
#
# Both fall back to a resident load silently, so the harness reads the runtime's own log after
# start and writes FAIL with that log quoted for an `on` cell that never streamed -- that is a
# result, not a harness bug.
#
# $OUT/stock4bit__<runtime>/ holds both of one runtime's runs, which differ in nothing but the pin:
#
#   join:  python -m ohyesmlx.cli sweep --varying stream_experts "$OUT"/stock4bit__*/*/
#
# The tail of this script runs that join, writing $OUT/sweep.md, and skips it when its glob
# matches no run directory.
#
# Streaming direction alternates per runtime -- OptiQ off then on, vMLX on then off -- so thermal
# drift does not alias onto the pin.
set -u
cd /Users/jrazz/Dev/active/OhYesMLX
. "$(dirname "$0")/gridspec-35b.sh"
PY=/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python
export PATH="$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH"
OUT=${OUT:-results/sweep-streaming}
DRY=${DRY:-0}

if [ "$DRY" = 1 ]; then
  echo "DRY=1: printing the run commands for $OUT -- nothing is started, no port is swept, no directory is written"
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

join_sweep() {  # $1 = the swept pin; $2 = the run-dir glob under $OUT; $3 = the report to write
  if [ "$DRY" = 1 ]; then
    echo "join: $PY -m ohyesmlx.cli sweep --varying $1 \"$OUT\"/$2"
    return 0
  fi
  # This study has no subset knob, so the glob is empty only when no run wrote a directory --
  # a runner stopped before its first run. An empty join is skipped, not handed to the renderer.
  matched=
  for d in "$OUT"/$2; do
    [ -d "$d" ] && { matched=1; break; }
  done
  [ -n "$matched" ] || { echo "join skipped: nothing matches \"$OUT\"/$2"; return 0; }
  echo "=== join $1 $(date +%H:%M:%S)"
  $PY -m ohyesmlx.cli sweep --varying "$1" "$OUT"/$2 --out "$3"
  echo "=== join $1 exit=$? $(date +%H:%M:%S)"
}

stream_sweep() {  # $1 = runtime; $2 $3 = the pin's two states, in the order they run
  echo "--- stock4bit__$1: stream-experts $2 $3"
  for state in "$2" "$3"; do
    [ "$DRY" = 1 ] || sweep
    run_one "stock4bit-$1-$state" --study format --cells "stock4bit__$1=$S4" \
        --stream-experts "$state" --results-dir "$OUT/stock4bit__$1"
    [ "$DRY" = 1 ] || sweep
  done
}

stream_sweep optiq off on
stream_sweep vmlx on off

join_sweep stream_experts 'stock4bit__*/*/' "$OUT/sweep.md"
echo "SWEEPDONE $(date +%H:%M:%S)"
