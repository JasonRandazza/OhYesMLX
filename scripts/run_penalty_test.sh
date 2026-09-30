#!/bin/sh
# scripts/run_penalty_test.sh
#
# The one-variable test for STATE's open concern "Osaurus applies the model bundle's
# presence_penalty": the dense Qwen3.5-4B-OptiQ-4bit cell on Osaurus, MMLU only, twice on ONE build.
#   arm shipped : the bundle as downloaded (generation_config.json has presence_penalty 1.5)
#   arm nopen   : a scratch bundle, weights and every other file symlinked to the original, its
#                 generation_config.json rewritten without presence_penalty / repetition_penalty
# Everything else is identical: same runtime build, same pin, same task, thinking off, temperature 0.
# Do not compare either arm with the 09-19 cell (0.25.6, caches on, different pin): only with each other.
# The scratch bundle is an extra HF-cache repo (Osaurus names a cache repo after its directory) and is
# removed at the end. Whether Osaurus will let an HTTP request override presence_penalty is not
# established, which is why this edits the bundle instead.
# Nothing else may run on this machine while this runs. Run: sh scripts/run_penalty_test.sh
set -u

cd /Users/jrazz/Dev/active/OhYesMLX
PY=/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python
export PATH="$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH"

H=$HOME/.cache/huggingface/hub
OQ="$H/models--mlx-community--Qwen3.5-4B-OptiQ-4bit/snapshots/6cb5bdfd0bf15f484881fb9f1ab6d7c840fddde9"
SCRATCH_REPO="$H/models--ohyesmlx--Qwen3.5-4B-OptiQ-4bit-nopenalty"
NP="$SCRATCH_REPO/snapshots/scratch"
OUT=results/accuracy-penalty
OSAURUS_PLIST=/Applications/osaurus.app/Contents/Info.plist
FAILED=0

sweep() {
  for p in 8081 1337 8100 8080 8000; do
    h=$(lsof -ti:$p 2>/dev/null | head -1); [ -n "$h" ] && { echo "  sweeping port $p pid $h"; kill -9 "$h" 2>/dev/null; }
  done
  # Stale Osaurus apps by FULL executable path, NEVER by the bare name `osaurus`.
  for h in $(pgrep -f "^/Applications/osaurus.app/Contents/MacOS/osaurus" 2>/dev/null); do
    echo "  sweeping stale osaurus app pid $h"; kill -9 "$h" 2>/dev/null
  done
  sleep 5
}
. "$(dirname "$0")/osaurus-pin.sh"

build_scratch() {
  rm -rf "$SCRATCH_REPO"; mkdir -p "$NP"
  for f in "$OQ"/* "$OQ"/.[!.]*; do
    n=$(basename "$f"); [ "$n" = generation_config.json ] && continue
    [ -e "$f" ] && ln -s "$(cd "$(dirname "$f")" && pwd -P)/$n" "$NP/$n"
  done
  $PY - "$OQ/generation_config.json" "$NP/generation_config.json" <<'PYEOF'
import json, sys
cfg = json.load(open(sys.argv[1]))
for k in ("presence_penalty", "repetition_penalty", "frequency_penalty"):
    cfg.pop(k, None)
json.dump(cfg, open(sys.argv[2], "w"), indent=2)
print("  scratch generation_config.json:", cfg)
PYEOF
}

cell() {  # <label> <artifact>
  cdir="$OUT/$1"
  v0=$(defaults read "$OSAURUS_PLIST" CFBundleShortVersionString)
  echo "=== CELL $1 starting $(date +%H:%M:%S) (osaurus $v0)"
  $PY scripts/probe_accuracy_cell.py --runtime osaurus --cell "$1" --artifact "$2" --out "$cdir" --task mmlu_generative
  rc=$?
  echo "=== CELL $1 exit=$rc $(date +%H:%M:%S)"
  [ "$rc" -eq 0 ] || FAILED=1
  v1=$(defaults read "$OSAURUS_PLIST" CFBundleShortVersionString)
  [ "$v1" = "$RUN_VERSION" ] || { echo "WARNING: osaurus is $v1, run started on $RUN_VERSION -- the arms no longer share a build"; FAILED=1; }
  sweep
}

mkdir -p "$OUT"
exec > "$OUT/runner.log" 2>&1
RUN_VERSION=$(defaults read "$OSAURUS_PLIST" CFBundleShortVersionString)
echo "Penalty test starting $(date +%H:%M:%S); Osaurus build for both arms: $RUN_VERSION"
sweep
build_scratch
osaurus_pin
cell optiq-shipped__osaurus "$OQ"
cell optiq-nopenalty__osaurus "$NP"
osaurus_restore_check
rm -rf "$SCRATCH_REPO"
echo "Penalty test finished $(date +%H:%M:%S); status: $([ $FAILED -eq 0 ] && echo SUCCESS || echo 'FAILURES RECORDED')"
exit $FAILED
