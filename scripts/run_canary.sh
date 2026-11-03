#!/bin/sh
# The canary (plan 025-02) around the Osaurus pin. `ohyesmlx canary` itself pins nothing: Osaurus's
# drift guard refuses to start while the host runs modelIdleResidencyPolicy.seconds = 30 against the
# committed baseline's 900 (first canary, 2026-10-29). scripts/osaurus-pin.sh is the one definition of
# the pin and the byte-exact restore; this runner only calls it, and always restores, success or not.
# Jason's standing authorisation (2026-10-29): Osaurus may be pinned for any run provided his own
# settings are returned and verified with `cmp`.
#
#   ENGINES=osaurus scripts/run_canary.sh           # a subset (default: all five)
#   RECORD=--record scripts/run_canary.sh           # write baselines (default: verdicts only)
# Nothing else may run on this machine while this runs.
set -u
cd /Users/jrazz/Dev/active/OhYesMLX
PY=/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python
export PATH="$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH"
. "$(dirname "$0")/osaurus-pin.sh"

ENGINES=${ENGINES:-mlxlm,osaurus,omlx,optiq,vmlx}
RECORD=${RECORD:-}
OUT=results/canary
mkdir -p "$OUT"
LOG="$OUT/runner-$(date +%Y%m%dT%H%M%S).log"
exec > "$LOG" 2>&1

sweep() {
  for p in 8081 1337 8100 8080 8000; do
    h=$(lsof -ti:$p 2>/dev/null | head -1)
    [ -n "$h" ] && { echo "  sweeping port $p pid $h"; kill -9 "$h" 2>/dev/null; }
  done
  for h in $(pgrep -f "^/Applications/[oO]saurus.app/Contents/MacOS/osaurus" 2>/dev/null); do
    echo "  sweeping stale osaurus app pid $h"; kill -9 "$h" 2>/dev/null
  done
  sleep 3
}

sweep
case ",$ENGINES," in *,osaurus,*) osaurus_pin ;; esac
$PY -m ohyesmlx.cli canary --yes $RECORD --engines "$ENGINES"
echo "canary exit=$?"
sweep
osaurus_restore_check
echo "DONE $(date +%H:%M:%S)"
