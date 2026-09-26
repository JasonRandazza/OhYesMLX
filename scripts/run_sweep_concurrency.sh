#!/bin/sh
# 06-01: the concurrency sweep, on the seedless harness. One runtime per run, one oq4 cell per run
# (the one format all five serve), the request concurrency moving 1/2/4/8, joined afterwards by
# `ohyesmlx sweep --varying concurrency` -- a sweep is a pin, never a --study axis.
#
# Why this is run again rather than extended (Decision 128, .paul/STATE.md, 2026-09-26): a request
# seed at temperature 0 forced mlx-lm and OptiQ onto their sequential path
# (mlx_lm/server.py:685-686), so every earlier concurrency column measured a batching-free path
# everyday clients never take. results/sweep-conc and results/sweep-conc8 were seeded and are
# therefore superseded, not re-joined: a seed-bearing header cannot join a seedless one. oMLX and
# vMLX do not route on the seed (source-read); Osaurus is not readable.
#
# $OUT/oq4__<runtime>/ holds one runtime's four runs, which differ in nothing but the pin:
#
#   join:  python -m ohyesmlx.cli sweep --varying concurrency "$OUT"/oq4__<runtime>/*/
#
# The tail of this script runs one join per runtime, writing $OUT/sweep-oq4__<runtime>.md, and skips
# one whose glob matches nothing (a RUNTIMES rerun leaves the other runtimes' directories unwritten).
#
# Concurrency order alternates direction per runtime, so thermal drift does not alias onto the pin.
#
# Osaurus is pinned around its runs exactly as run_sweep_kvquant.sh does: osaurus-pin.sh turns the
# prefix and blockDisk caches off and pins modelIdleResidencyPolicy.seconds to 900, re-records the
# drift baseline, and restores both settings byte-exact afterwards.
set -u
cd /Users/jrazz/Dev/active/OhYesMLX
. "$(dirname "$0")/gridspec.sh"
PY=/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python
export PATH="$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH"
OUT=${OUT:-results/sweep-conc-seedless}
DRY=${DRY:-0}
# RUNTIMES narrows a rerun. Order and the alternation below follow this list, so a one-runtime
# rerun reads the pin forward.
RUNTIMES=${RUNTIMES:-mlxlm omlx optiq vmlx osaurus}
. "$(dirname "$0")/osaurus-pin.sh"

if [ "$DRY" = 1 ]; then
  echo "DRY=1: printing the run commands for $OUT -- nothing is started, no port is swept, no directory is written"
else
  mkdir -p "$OUT"
  # The runner owns its log. runner.log came out 0 bytes on 2026-09-16 because the caller's
  # redirect was unbound from the command (`cmd & > file` shape), so the echoes here went to a
  # terminal instead. An exec redirect cannot be missed that way. The per-run redirects below
  # still override per-command. Tradeoff: live progress now reaches only this file -- `tail -f`
  # $OUT/runner.log to watch a run.
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

# A killed runner must not leave a runtime holding a port, so the trap sweeps exactly as a
# finished run does before it exits; around Osaurus, osaurus-pin.sh's trap also restores settings.
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
  # RUNTIMES narrows a rerun, so a glob can be left matching no run directory at all; an empty
  # join is skipped rather than handed to the renderer.
  matched=
  for d in "$OUT"/$2; do
    [ -d "$d" ] && { matched=1; break; }
  done
  [ -n "$matched" ] || { echo "join skipped: nothing matches \"$OUT\"/$2"; return 0; }
  echo "=== join $1 $(date +%H:%M:%S)"
  $PY -m ohyesmlx.cli sweep --varying "$1" "$OUT"/$2 --out "$3"
  echo "=== join $1 exit=$? $(date +%H:%M:%S)"
}

LEVELS="1 2 4 8"
LEVELS_REV="8 4 2 1"
levels=$LEVELS
for r in $RUNTIMES; do
  echo "--- $r: concurrency $levels"
  [ "$DRY" = 1 ] || { [ "$r" = osaurus ] && osaurus_pin; }
  for n in $levels; do
    # Before as well as after: an Osaurus app relaunched between runs must not sit resident
    # through another runtime's cell. The kill is logged.
    [ "$DRY" = 1 ] || sweep
    run_one "oq4__$r-n$n" --study format --cells "oq4__$r=$Q4" --concurrency "$n" \
        --results-dir "$OUT/oq4__$r"
    [ "$DRY" = 1 ] || sweep
  done
  [ "$DRY" = 1 ] || { [ "$r" = osaurus ] && osaurus_restore_check; }
  # The next runtime reads the pin the other way round. The first runtime reads it forward.
  [ "$levels" = "$LEVELS" ] && levels=$LEVELS_REV || levels=$LEVELS
done

for r in $RUNTIMES; do
  join_sweep concurrency "oq4__$r/*/" "$OUT/sweep-oq4__$r.md"
done
echo "SWEEPDONE $(date +%H:%M:%S)"
