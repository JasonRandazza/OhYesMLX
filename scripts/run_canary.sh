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

# One sweep, by process (055-03): scripts/sweep.sh, which needs $PY.
. "$(dirname "$0")/sweep.sh"

sweep || exit 1
case ",$ENGINES," in *,osaurus,*) osaurus_pin ;; esac
$PY -m ohyesmlx.cli canary --yes $RECORD --engines "$ENGINES"
echo "canary exit=$?"
sweep || exit 1
# A restore that did not verify must be this script's exit status, not a line in its log: the
# standing authorisation requires the settings returned and verified, and a coordinator reads
# the code (Fable S5-F7).
osaurus_restore_check || exit 1
echo "DONE $(date +%H:%M:%S)"
