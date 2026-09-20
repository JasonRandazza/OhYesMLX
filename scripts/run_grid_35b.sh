#!/bin/sh
# The 35B MoE grid (Plan 03-01): one column per runtime, --study format holding the runtime constant.
#
# Pinned:
#   --cache-state off
#   --results-dir results/grid-35b
#
# Around Osaurus:
#   Both ~/.osaurus/config files are copied byte-exact.
#   modelIdleResidencyPolicy.seconds is pinned to 900.
#   cache.prefix.enabled and cache.blockDisk.enabled are pinned to false.
#   Baseline is re-recorded and restored byte-exact afterwards, verified with `cmp`.
#
# Ports and stale Osaurus processes are swept before and after every column.
# Nothing else may run on this machine while this runs.
set -u
cd /Users/jrazz/Dev/active/OhYesMLX
. "$(dirname "$0")/gridspec-35b.sh"
PY=/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python
export PATH="$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH"

OUT=results/grid-35b
mkdir -p "$OUT"
exec > "$OUT/runner.log" 2>&1

CONF="$HOME/.osaurus/config/server-runtime.json"
SERVER="$HOME/.osaurus/config/server.json"
CONF_ORIG="$CONF.grid-35b-orig"
SERVER_ORIG="$SERVER.grid-35b-orig"

sweep() {
  for p in 8081 1337 8100 8080 8000; do
    h=$(lsof -ti:$p 2>/dev/null | head -1)
    [ -n "$h" ] && { echo "  sweeping port $p pid $h"; kill -9 "$h" 2>/dev/null; }
  done
  for h in $(pgrep -f "^/Applications/osaurus.app/Contents/MacOS/osaurus" 2>/dev/null); do
    echo "  sweeping stale osaurus app pid $h"; kill -9 "$h" 2>/dev/null
  done
  sleep 3
}

osaurus_restore() {
  [ -f "$CONF_ORIG" ] || return 0
  cp -p "$CONF_ORIG" "$CONF"
  cp -p "$SERVER_ORIG" "$SERVER"
  git checkout -- config/osaurus-settings-baseline.json
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
conf, server = '$CONF', '$SERVER'
runtime = json.load(open(conf))
runtime.setdefault('cache', {}).setdefault('prefix', {})['enabled'] = False
runtime.setdefault('cache', {}).setdefault('blockDisk', {})['enabled'] = False
json.dump(runtime, open(conf, 'w'), indent=2)
hardware = json.load(open(server))
hardware.setdefault('modelIdleResidencyPolicy', {})['seconds'] = 900
json.dump(hardware, open(server, 'w'), indent=2)"
  $PY -c "from ohyesmlx import osaurus_settings as s; s.write_baseline()"
  echo "  osaurus cache off & idle residency pinned to 900 s"
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

sweep
for r in mlxlm omlx optiq vmlx osaurus; do
  eval "c=\$CELLS_$r"
  if [ -z "$c" ]; then
    echo "=== COLUMN $r SKIPPED (no cells defined or probe showed no live cells)"
    continue
  fi
  [ "$r" = osaurus ] && osaurus_pin
  sweep
  echo "=== COLUMN $r starting $(date +%H:%M:%S)"
  $PY -m ohyesmlx.cli run --study format --cache-state off --cells "$c" --results-dir "$OUT" \
      > "$OUT/log-$r.log" 2>&1
  echo "=== COLUMN $r exit=$? $(date +%H:%M:%S)"
  sweep
  [ "$r" = osaurus ] && restore_and_check
  sleep 5
done

echo "=== RENDERING GRID $(date +%H:%M:%S)"
$PY -m ohyesmlx.cli grid "$OUT"/*/ --out "$OUT/grid.md" || echo "GRID RENDER WARNING: $?"
echo "35BGRIDDONE $(date +%H:%M:%S)"
