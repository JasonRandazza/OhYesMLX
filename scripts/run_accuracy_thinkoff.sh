#!/bin/sh
# scripts/run_accuracy_thinkoff.sh
#
# Thinking-Off MMLU Arm (ROADMAP Candidate 3), revised 2026-09-29 per Jason: an Osaurus-only 2x2
# on LFM2.5-8B-A1B, plus a one-request vMLX refusal probe.
#
#   cells:  jang2l x stock4bit  ->  thinking OFF and thinking ON, all on the SAME Osaurus build
#   task:   MMLU 5-shot multiturn, --mmlu-limit 20 (1,140 items), temperature 0, cache off
#   after:  every cell is re-scored offline with scripts/rescore_moe_mmlu.py --cell-dir, because
#           Osaurus prefixes its answer with prose and lm-eval's first-line filter scores the
#           prefix (3.77% raw vs 42.19% recovered on the 09-19 cell).
#
# Why not the plan's 8 cells (docs/research/2026-09-29-thinking-off-arm-plan.md): vMLX refuses
# enable_thinking=false on LFM2 with HTTP 400 (supports_instruct_mode=False, Decision 105), so seven
# of eight would abort on item 1; and the 09-19 thinking-on comparator ran on Osaurus 0.25.6, so an
# Osaurus thinking-off cell alone would vary the build as well. Running BOTH arms now on one build
# keeps thinking the only difference. vMLX gets one probe request, recorded, not seven aborted cells.
#
# Single-variable rule: within this run, thinking on/off is the only thing that differs between the
# paired cells. Do not compare a cell here with the 09-19 Osaurus cell (0.25.6): different build.
#
# DRY=1 prints every command and touches nothing (no runtime, no model, no lm-eval, no Osaurus config).
# Nothing else may run on this machine while this runs. Run: sh scripts/run_accuracy_thinkoff.sh
# Optional target: probe | osaurus  (default: all).
set -u

cd /Users/jrazz/Dev/active/OhYesMLX
PY=/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python
export PATH="$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH"

H=$HOME/.cache/huggingface/hub
# Same artifacts as Plan 02-03 (scripts/run_accuracy_moe.sh)
S4="$H/models--mlx-community--LFM2.5-8B-A1B-MLX-4bit/snapshots/146590a491db88581884033023f51f6b49a27b89"
JG="$H/models--JANGQ-AI--LFM2.5-8B-A1B-JANG_2L/snapshots/5fb82773427c2f25395de8821eff6d95e86feb53"

OUT=results/accuracy-thinkoff

CONF="$HOME/.osaurus/config/server-runtime.json"
SERVER="$HOME/.osaurus/config/server.json"
CONF_ORIG="$CONF.thinkoff-orig"
SERVER_ORIG="$SERVER.thinkoff-orig"
OSAURUS_PLIST=/Applications/osaurus.app/Contents/Info.plist

FAILED=0
DRY_MODE="${DRY:-0}"
TARGET="${1:-all}"

if [ "$DRY_MODE" != "1" ]; then
  mkdir -p "$OUT/think-off" "$OUT/think-on"
  exec > "$OUT/runner.log" 2>&1
fi

osaurus_version() { defaults read "$OSAURUS_PLIST" CFBundleShortVersionString 2>/dev/null || echo unknown; }

sweep() {
  if [ "$DRY_MODE" = "1" ]; then
    echo "[DRY RUN] sweep: terminate pids on ports 8081 1337 8100 8080 8000 and stale osaurus app instances (by full path)"
    return 0
  fi
  for p in 8081 1337 8100 8080 8000; do
    h=$(lsof -ti:$p 2>/dev/null | head -1); [ -n "$h" ] && { echo "  sweeping port $p pid $h"; kill -9 "$h" 2>/dev/null; }
  done
  # Stale Osaurus apps by FULL executable path, NEVER by the bare name `osaurus`.
  for h in $(pgrep -f "^/Applications/osaurus.app/Contents/MacOS/osaurus" 2>/dev/null); do
    echo "  sweeping stale osaurus app pid $h"; kill -9 "$h" 2>/dev/null
  done
  sleep 5
}

osaurus_restore() {
  [ -f "$CONF_ORIG" ] || return 0
  cp -p "$CONF_ORIG" "$CONF"
  cp -p "$SERVER_ORIG" "$SERVER"
}

osaurus_pin() {
  if [ "$DRY_MODE" = "1" ]; then
    echo "[DRY RUN] osaurus_pin: backup $CONF and $SERVER; pin modelIdleResidencyPolicy.seconds=900"
    return 0
  fi
  if [ ! -f "$CONF_ORIG" ]; then
    cp -p "$CONF" "$CONF_ORIG"
    cp -p "$SERVER" "$SERVER_ORIG"
    trap 'echo "ABORTED -- restoring Osaurus settings"; osaurus_restore; exit 130' INT TERM HUP
  fi
  cp -p "$CONF_ORIG" "$CONF"
  cp -p "$SERVER_ORIG" "$SERVER"
  $PY -c "
import json
server = '$SERVER'
hardware = json.load(open(server))
hardware.setdefault('modelIdleResidencyPolicy', {})['seconds'] = 900
json.dump(hardware, open(server, 'w'), indent=2)"
  echo "  osaurus idle residency pinned to 900 s"
}

restore_and_check() {
  if [ "$DRY_MODE" = "1" ]; then
    echo "[DRY RUN] restore_and_check: restore Osaurus config and verify byte-exact with cmp"
    return 0
  fi
  if [ ! -f "$CONF_ORIG" ]; then
    echo "  osaurus settings were never pinned; nothing to restore"
    return 0
  fi
  osaurus_restore
  if cmp -s "$CONF" "$CONF_ORIG" && cmp -s "$SERVER" "$SERVER_ORIG"; then
    echo "  osaurus settings restored byte-exact (cmp)"
  else
    echo "RESTORE FAILED: ~/.osaurus/config is not byte-identical to the copies"
    exit 1
  fi
  rm -f "$CONF_ORIG" "$SERVER_ORIG"
}

# One request each way at vMLX on the LFM2 stock bundle, recorded: enable_thinking=false is expected to
# be refused with HTTP 400, and the same request without the field to succeed (so the refusal is about
# the field and not a server that never came up). The start command is the harness's own, asked of
# ohyesmlx.runtimes rather than copied here.
vmlx_refusal_probe() {
  rec="$OUT/vmlx-refusal-probe.txt"
  if [ "$DRY_MODE" = "1" ]; then
    echo "[DRY RUN] vmlx_refusal_probe: start the harness's vMLX command on $S4, POST once with enable_thinking=false and once without, record both HTTP codes and bodies to $rec, stop vMLX"
    return 0
  fi
  echo "=== vMLX refusal probe starting $(date +%H:%M:%S)"
  sweep
  cmd=$($PY -c "
import shlex
from ohyesmlx import runtimes
a = '$S4'
print(shlex.join(runtimes.RUNTIMES['vmlx'].start_command(a, runtimes.vmlx_served_name(a))))")
  served=$($PY -c "
from ohyesmlx import runtimes
print(runtimes.vmlx_served_name('$S4'))")
  sh -c "$cmd" > "$OUT/vmlx-refusal-probe.server.log" 2>&1 &
  pid=$!
  n=0; until curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; do
    n=$((n+1)); [ $n -gt 90 ] && { echo "  vMLX did not come up"; kill "$pid" 2>/dev/null; FAILED=1; return 0; }
    sleep 2
  done
  {
    echo "vMLX probe $(date +%Y-%m-%dT%H:%M:%S) model=$served"
    for body in \
      "{\"model\":\"$served\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with the letter A.\"}],\"max_tokens\":8,\"temperature\":0,\"enable_thinking\":false}" \
      "{\"model\":\"$served\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with the letter A.\"}],\"max_tokens\":8,\"temperature\":0}"; do
      echo "--- request: $body"
      code=$(curl -s -o "$OUT/.probe-body" -w '%{http_code}' -H 'Content-Type: application/json' -d "$body" http://127.0.0.1:8000/v1/chat/completions)
      echo "HTTP $code"; head -c 600 "$OUT/.probe-body"; echo
    done
  } > "$rec" 2>&1
  rm -f "$OUT/.probe-body"
  kill "$pid" 2>/dev/null; sleep 3; kill -9 "$pid" 2>/dev/null
  sweep
  echo "=== vMLX refusal probe done $(date +%H:%M:%S); see $rec"
}

# args: <cell_label> <artifact> <arm: off|on>
osaurus_cell() {
  cell="$1"; art="$2"; arm="$3"
  cdir="$OUT/think-$arm/$cell"
  flag=""; [ "$arm" = "on" ] && flag="--no-disable-thinking"
  # thinking OFF is probe_accuracy_cell.py's default (gen_kwargs enable_thinking=false); ON is
  # --no-disable-thinking, exactly as run_accuracy_moe.sh ran the 09-19 cells.
  cmd="$PY scripts/probe_accuracy_cell.py --runtime osaurus --cell $cell --artifact $art --out $cdir --task mmlu_generative --mmlu-limit 20 $flag"
  if [ "$DRY_MODE" = "1" ]; then
    echo "$cmd"
    echo "$PY scripts/rescore_moe_mmlu.py --cell-dir $cdir"
    return 0
  fi
  v0=$(osaurus_version)
  echo "=== CELL think-$arm/$cell starting $(date +%H:%M:%S) (osaurus $v0)"
  eval "$cmd"
  rc=$?
  echo "=== CELL think-$arm/$cell exit=$rc $(date +%H:%M:%S)"
  [ "$rc" -eq 0 ] || FAILED=1
  # A self-update mid-run would put the two arms on different builds; say so loudly, keep going.
  v1=$(osaurus_version)
  [ "$v1" = "$RUN_VERSION" ] || { echo "WARNING: osaurus is $v1, run started on $RUN_VERSION -- the arms no longer share a build"; FAILED=1; }
  echo "--- offline re-score $cell think-$arm"
  $PY scripts/rescore_moe_mmlu.py --cell-dir "$cdir" || FAILED=1
  sweep
}

echo "=========================================================="
echo "Thinking-Off MMLU Arm (Osaurus 2x2 + vMLX probe) starting $(date +%H:%M:%S)"
echo "Target: $TARGET (DRY=$DRY_MODE)"
RUN_VERSION=$(osaurus_version)
echo "Osaurus build for every cell: $RUN_VERSION"
echo "=========================================================="

echo "--- pre-sweep $(date +%H:%M:%S)"
sweep

if [ "$TARGET" = "all" ] || [ "$TARGET" = "probe" ]; then
  vmlx_refusal_probe
fi

if [ "$TARGET" = "all" ] || [ "$TARGET" = "osaurus" ]; then
  echo ">>> STARTING Osaurus 2x2 $(date +%H:%M:%S)"
  osaurus_pin
  # One model resident at a time and one load per model: both arms of a format back to back.
  osaurus_cell "jang2l__osaurus" "$JG" off
  osaurus_cell "jang2l__osaurus" "$JG" on
  osaurus_cell "stock4bit__osaurus" "$S4" off
  osaurus_cell "stock4bit__osaurus" "$S4" on
  sweep
  restore_and_check
  echo ">>> FINISHED Osaurus 2x2 $(date +%H:%M:%S)"
fi

echo "=========================================================="
echo "Thinking-Off MMLU Arm finished $(date +%H:%M:%S)"
if [ "$DRY_MODE" = "1" ]; then
  echo "Overall Status: DRY RUN COMPLETE"
else
  echo "Overall Status: $([ $FAILED -eq 0 ] && echo 'SUCCESS' || echo 'FAILURES RECORDED')"
fi
echo "=========================================================="

exit $FAILED
