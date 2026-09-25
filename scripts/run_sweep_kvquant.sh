#!/bin/sh
# 03-05: the KV-cache codec sweep. One runtime per run, one oq4 cell per run (the one format all
# five serve), joined afterwards by `ohyesmlx sweep --varying kv_quant` -- a sweep is a pin, never
# a --study axis.
#
# Two pins move in this study, so the layout has to keep them apart. A sweep varies exactly ONE
# header pin, and report.py refuses a join whose runs disagree about any other one, so the two
# prompt lengths cannot sit in one join: $OUT/oq4__<runtime>/p<target>/ holds the three runs of one
# (runtime, artifact) pairing at one prompt length, which differ in nothing but the codec.
#
#   join:  python -m ohyesmlx.cli sweep --varying kv_quant "$OUT"/oq4__*/p16384/*/
#          python -m ohyesmlx.cli sweep --varying kv_quant "$OUT"/oq4__*/p32768/*/
#
# Codec order alternates direction per runtime, and so does the prompt-length order, so thermal
# drift does not alias onto either pin.
set -u
cd /Users/jrazz/Dev/active/OhYesMLX
. "$(dirname "$0")/gridspec-35b.sh"
PY=/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python
export PATH="$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH"
OUT=${OUT:-results/sweep-kvquant}
DRY=${DRY:-0}
# RUNTIMES narrows a rerun (2026-09-25: RUNTIMES=osaurus after the unpinned night). Order and the
# alternation below follow this list, so a one-runtime rerun reads both pins forward.
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
  # results/sweep-kvquant/runner.log to watch a run.
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

CODECS="off affine8 affine4"
CODECS_REV="affine4 affine8 off"
LENGTHS="16384 32768"
LENGTHS_REV="32768 16384"
codecs=$CODECS
lengths=$LENGTHS
for r in $RUNTIMES; do
  echo "--- $r: kv-quant $codecs at prompt-tokens $lengths"
  [ "$DRY" = 1 ] || { [ "$r" = osaurus ] && osaurus_pin; }
  for t in $lengths; do
    for kv in $codecs; do
      # Before as well as after: an Osaurus app relaunched between runs must not sit resident
      # through another runtime's cell. The kill is logged.
      [ "$DRY" = 1 ] || sweep
      run_one "$r-t$t-$kv" --study format --cells "oq4__$r=$Q4" --kv-quant "$kv" \
          --prompt-tokens "$t" --results-dir "$OUT/oq4__$r/p$t"
      [ "$DRY" = 1 ] || sweep
    done
  done
  [ "$DRY" = 1 ] || { [ "$r" = osaurus ] && osaurus_restore_check; }
  # The next runtime reads both pins the other way round.
  [ "$codecs" = "$CODECS" ] && codecs=$CODECS_REV || codecs=$CODECS
  [ "$lengths" = "$LENGTHS" ] && lengths=$LENGTHS_REV || lengths=$LENGTHS
done

echo "join: $PY -m ohyesmlx.cli sweep --varying kv_quant \"$OUT\"/oq4__*/p16384/*/"
echo "join: $PY -m ohyesmlx.cli sweep --varying kv_quant \"$OUT\"/oq4__*/p32768/*/"
echo "SWEEPDONE $(date +%H:%M:%S)"
