#!/bin/sh
# 03-06: the native-MTP draft-depth sweep. One cell per run, the pin moving off/1/2/3, joined
# afterwards by `ohyesmlx sweep --varying mtp_depth` -- a sweep is a pin, never a --study axis.
#
# Three (runtime, artifact) pairings, because MTP is not a property of the model alone: the runtime
# has to wire the bundle's heads, and a bundle without them is N/A with the reason rather than a
# plain autoregressive decode published as a depth (runtimes.vmlx_mtp_refusal).
#
#   vMLX  x JANGQ-AI/Qwen3.5-4B-JANG_4S                 jang4s__vmlx   ($JANG4S, resolved here)
#   OptiQ x mlx-community/Qwen3.5-4B-OptiQ-4bit        optiq4b__optiq ($OPT4B, resolved here)
#   OptiQ x mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit   optiq__optiq   ($OQ, from gridspec-35b.sh)
#
# The two OptiQ artifacts take different labels -- `optiq4b` for the 4B snapshot and `optiq` for
# the 35B one -- because the label is what a table shows and these are two different models.
#
# $OUT/<cell>/ holds one pairing's four runs, which differ in nothing but the pin:
#
#   join:  python -m ohyesmlx.cli sweep --varying mtp_depth "$OUT"/jang4s__vmlx/*/
#          (and the same per pairing: optiq4b__optiq, optiq__optiq)
#
# Depth order alternates direction per pairing, so thermal drift does not alias onto the pin.
set -u
cd /Users/jrazz/Dev/active/OhYesMLX
. "$(dirname "$0")/gridspec-35b.sh"
PY=/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python
export PATH="$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH"
# The two 4B snapshots, resolved the way gridspec-35b.sh resolves the 35B ones.
H=$HOME/.cache/huggingface/hub
JANG4S="$H/models--JANGQ-AI--Qwen3.5-4B-JANG_4S/snapshots"
OPT4B="$H/models--mlx-community--Qwen3.5-4B-OptiQ-4bit/snapshots"
for v in JANG4S OPT4B; do
  eval "d=\$$v"
  eval "$v=\$(ls -d \"\$d\"/*/ 2>/dev/null | head -1 | sed 's:/$::')"
done
OUT=${OUT:-results/sweep-mtp}
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

DEPTHS="off 1 2 3"
DEPTHS_REV="3 2 1 off"

mtp_sweep() {  # $1 = cell id (`<format>__<runtime>`), $2 = artifact dir, $3 = ascending|descending
  cell=$1
  case $3 in
    ascending) order=$DEPTHS ;;
    descending) order=$DEPTHS_REV ;;
  esac
  echo "--- $cell: mtp-depth $order"
  for d in $order; do
    [ "$DRY" = 1 ] || sweep
    run_one "$cell-$d" --study format --cells "$cell=$2" --mtp-depth "$d" --results-dir "$OUT/$cell"
    [ "$DRY" = 1 ] || sweep
  done
}

mtp_sweep jang4s__vmlx "$JANG4S" ascending
mtp_sweep optiq4b__optiq "$OPT4B" descending
mtp_sweep optiq__optiq "$OQ" ascending

echo "join: $PY -m ohyesmlx.cli sweep --varying mtp_depth \"$OUT\"/jang4s__vmlx/*/"
echo "join: $PY -m ohyesmlx.cli sweep --varying mtp_depth \"$OUT\"/optiq4b__optiq/*/"
echo "join: $PY -m ohyesmlx.cli sweep --varying mtp_depth \"$OUT\"/optiq__optiq/*/"
echo "SWEEPDONE $(date +%H:%M:%S)"
