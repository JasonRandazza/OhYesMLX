#!/bin/sh
# Plan 02-02, the dense accuracy study: Qwen3.5-4B in five quantizations across
# vMLX and Osaurus, plus a 3-cell MMLU replication pass.
#
# Follows the test matrix of docs/research/2026-09-17-v2-track2-accuracy-study-design.md §6.3:
# - Column A: vMLX across jang4s, stock4bit, oq4, oq4e (cache_state="off")
# - Column B: Osaurus across jang4s, oq4, oq4e, optiq (host idle residency pinned to 900s, restored byte-exact)
# - Replicate: stock4bit__vmlx, jang4s__vmlx, jang4s__osaurus on MMLU 5-shot
#
# Zero repository dependencies added; evaluates via isolated uv run lm-eval.
set -u
cd /Users/jrazz/Dev/active/OhYesMLX
PY=/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python
export PATH="$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH"

H=$HOME/.cache/huggingface/hub
S4="$H/models--mlx-community--Qwen3.5-4B-4bit/snapshots/0e7ffd5c629ef7719d4cbc04069232580bfa9d9c"
Q4="$H/models--RepublicOfKorokke--Qwen3.5-4B-oQ4/snapshots/3ae88a7d17b1c6bb71b795c1090948a82508fdb8"
QE="$H/models--uingei--Qwen3.5-4B-oQ4e/snapshots/2e232d525d5df5e7a6eece4b03b17087e6b3c3ac"
OQ="$H/models--mlx-community--Qwen3.5-4B-OptiQ-4bit/snapshots/6cb5bdfd0bf15f484881fb9f1ab6d7c840fddde9"
JG="$H/models--JANGQ-AI--Qwen3.5-4B-JANG_4S/snapshots/4567967a46cd9e9bf26d3bb491ddd422ad607775"

OUT=results/accuracy-dense
mkdir -p "$OUT/column-vmlx" "$OUT/column-osaurus" "$OUT/replicate"
exec > "$OUT/runner.log" 2>&1

CONF="$HOME/.osaurus/config/server-runtime.json"
SERVER="$HOME/.osaurus/config/server.json"
CONF_ORIG="$CONF.grid-orig"
SERVER_ORIG="$SERVER.grid-orig"

VMLX_PATCHED_SHA256="9710d2b9cf07abc7380f46fef240e64febb2d06d52eb7f64236bd0e76cf686f7"
VMLX_SCHEDULER="/Applications/vMLX.app/Contents/Resources/vmlx-engine-source/vmlx_engine/mllm_scheduler.py"

FAILED=0

sweep() {
  for p in 8081 1337 8100 8080 8000; do
    h=$(lsof -ti:$p 2>/dev/null | head -1); [ -n "$h" ] && { echo "  sweeping port $p pid $h"; kill -9 "$h" 2>/dev/null; }
  done
  # Sweep stale Osaurus app instances by full executable path, NEVER by bare name `osaurus`.
  for h in $(pgrep -f "^/Applications/osaurus.app/Contents/MacOS/osaurus" 2>/dev/null); do
    echo "  sweeping stale osaurus app pid $h"; kill -9 "$h" 2>/dev/null
  done
  sleep 5
}

verify_vmlx() {
  echo "--- verifying vMLX engine patch ---"
  if [ ! -f "$VMLX_SCHEDULER" ]; then
    echo "ERROR: vMLX scheduler missing at $VMLX_SCHEDULER"
    exit 1
  fi
  actual_hash=$(shasum -a 256 "$VMLX_SCHEDULER" | awk '{print $1}')
  if [ "$actual_hash" != "$VMLX_PATCHED_SHA256" ]; then
    echo "ERROR: vMLX scheduler hash mismatch: $actual_hash != $VMLX_PATCHED_SHA256"
    exit 1
  fi
  echo "  vMLX scheduler patch verified: $actual_hash"
}

osaurus_restore() {
  [ -f "$CONF_ORIG" ] || return 0
  cp -p "$CONF_ORIG" "$CONF"
  cp -p "$SERVER_ORIG" "$SERVER"
}

osaurus_pin() {
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

run_cell() {
  # args: <runtime> <cell_label> <artifact_path> <out_dir> [replicate_flag]
  rt="$1"
  cell="$2"
  art="$3"
  cdir="$4"
  repl="${5:-}"

  echo "=== CELL $cell starting $(date +%H:%M:%S) ==="
  repl_arg=""
  [ "$repl" = "--replicate" ] && repl_arg="--replicate"

  $PY scripts/probe_accuracy_cell.py --runtime "$rt" --cell "$cell" --artifact "$art" --out "$cdir" $repl_arg
  rc=$?
  echo "=== CELL $cell exit=$rc $(date +%H:%M:%S) ==="
  [ "$rc" -eq 0 ] || FAILED=1
  sweep
  return 0
}

TARGET="${1:-all}"

echo "=========================================================="
echo "Plan 02-02 Dense Accuracy Study starting $(date +%H:%M:%S)"
echo "Target mode: $TARGET"
echo "=========================================================="

echo "--- pre-sweep $(date +%H:%M:%S)"
sweep

if [ "$TARGET" = "all" ] || [ "$TARGET" = "vmlx" ]; then
  verify_vmlx

  echo "\n>>> STARTING COLUMN A: vMLX (4 cells) $(date +%H:%M:%S)"
  run_cell vmlx "stock4bit__vmlx" "$S4" "$OUT/column-vmlx/stock4bit__vmlx"
  run_cell vmlx "oq4__vmlx" "$Q4" "$OUT/column-vmlx/oq4__vmlx"
  run_cell vmlx "oq4e__vmlx" "$QE" "$OUT/column-vmlx/oq4e__vmlx"
  run_cell vmlx "jang4s__vmlx" "$JG" "$OUT/column-vmlx/jang4s__vmlx"
  echo ">>> FINISHED COLUMN A: vMLX $(date +%H:%M:%S)\n"
fi

if [ "$TARGET" = "all" ] || [ "$TARGET" = "osaurus" ]; then
  echo "\n>>> STARTING COLUMN B: Osaurus (4 cells) $(date +%H:%M:%S)"
  osaurus_pin
  run_cell osaurus "oq4__osaurus" "$Q4" "$OUT/column-osaurus/oq4__osaurus"
  run_cell osaurus "oq4e__osaurus" "$QE" "$OUT/column-osaurus/oq4e__osaurus"
  run_cell osaurus "optiq__osaurus" "$OQ" "$OUT/column-osaurus/optiq__osaurus"
  run_cell osaurus "jang4s__osaurus" "$JG" "$OUT/column-osaurus/jang4s__osaurus"
  sweep
  restore_and_check
  echo ">>> FINISHED COLUMN B: Osaurus $(date +%H:%M:%S)\n"
fi

if [ "$TARGET" = "all" ] || [ "$TARGET" = "replicate" ]; then
  echo "\n>>> STARTING REPLICATION PASS (3 cells, MMLU 5-shot) $(date +%H:%M:%S)"
  # Reversed order from primary for vMLX pair
  verify_vmlx
  run_cell vmlx "jang4s__vmlx_repl" "$JG" "$OUT/replicate/jang4s__vmlx" --replicate
  run_cell vmlx "stock4bit__vmlx_repl" "$S4" "$OUT/replicate/stock4bit__vmlx" --replicate

  osaurus_pin
  run_cell osaurus "jang4s__osaurus_repl" "$JG" "$OUT/replicate/jang4s__osaurus" --replicate
  sweep
  restore_and_check
  echo ">>> FINISHED REPLICATION PASS $(date +%H:%M:%S)\n"
fi

echo "=========================================================="
echo "Plan 02-02 Dense Accuracy Study finished $(date +%H:%M:%S)"
echo "Overall Status: $([ $FAILED -eq 0 ] && echo 'SUCCESS' || echo 'FAILURES RECORDED')"
echo "=========================================================="

exit $FAILED
