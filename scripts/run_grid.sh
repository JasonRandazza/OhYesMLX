#!/bin/sh
# The dense grid: one column per runtime, --study format holding the runtime constant.
#
# Osaurus takes no tuning flags, so what its column measures lives in ~/.osaurus/config.
# Around that column only, both files are copied byte-exact, modelIdleResidencyPolicy.seconds
# is pinned to 900 (the host's 30 unloads the model inside the 30 s cooldown, and the harness
# refuses to start Osaurus while the host differs from the recorded baseline), and both are
# restored byte-exact afterwards and on INT/TERM/HUP, checked with `cmp`. The other four
# columns see no settings write at all.
set -u
cd /Users/jrazz/Dev/active/OhYesMLX
. "$(dirname "$0")/gridspec.sh"
OUT=${OUT:-results/grid}
mkdir -p "$OUT"
PY=/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python
export PATH="$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH"
CONF="$HOME/.osaurus/config/server-runtime.json"
SERVER="$HOME/.osaurus/config/server.json"
CONF_ORIG="$CONF.grid-orig"
SERVER_ORIG="$SERVER.grid-orig"

osaurus_restore() {  # byte-exact, both files; the drift guard is not the check here
  [ -f "$CONF_ORIG" ] || return 0   # nothing was pinned, so nothing is Jason's to get back
  cp -p "$CONF_ORIG" "$CONF"
  cp -p "$SERVER_ORIG" "$SERVER"
}

osaurus_pin() {
  if [ ! -f "$CONF_ORIG" ]; then
    cp -p "$CONF" "$CONF_ORIG"        # byte-exact; the ohyesmlx-backup differs in whitespace
    cp -p "$SERVER" "$SERVER_ORIG"
    # A killed grid must not leave Jason's Osaurus unloading its model inside a cooldown.
    trap 'echo "ABORTED -- restoring Osaurus settings"; osaurus_restore; exit 130' INT TERM HUP
  fi
  # Built from the host's own files, so a copy left by an interrupted run restores the host's
  # state and not whatever that run left behind.
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

for r in mlxlm omlx optiq vmlx osaurus; do
  eval "c=\$CELLS_$r"
  [ "$r" = osaurus ] && osaurus_pin
  echo "=== COLUMN $r starting $(date +%H:%M:%S)"
  $PY -m ohyesmlx.cli run --study format --cells "$c" --results-dir "$OUT" \
      > "$OUT/log-$r.log" 2>&1
  echo "=== COLUMN $r exit=$? $(date +%H:%M:%S)"
  # Sweep between columns: a leaked resident would contend for the memory the next column measures.
  for p in 8081 1337 8100 8080 8000; do
    h=$(lsof -ti:$p 2>/dev/null | head -1); [ -n "$h" ] && { echo "  sweeping port $p pid $h"; kill -9 "$h" 2>/dev/null; }
  done
  # Osaurus releases its port on `stop` and leaves the app running, so a port sweep misses it
  # and the leftovers accumulate at ~900 MB each -- three of them, aged 5-7 h, were resident
  # through both grids on 2026-09-16. Swept by FULL EXECUTABLE PATH, never by the name
  # `osaurus`: `osaurus mcp` is a long-running user process and must not be touched.
  for h in $(pgrep -f "^/Applications/osaurus.app/Contents/MacOS/osaurus" 2>/dev/null); do
    echo "  sweeping stale osaurus app pid $h"; kill -9 "$h" 2>/dev/null
  done
  # Restore after the sweep: a still-running Osaurus app must be dead before the host's own
  # files go back.
  [ "$r" = osaurus ] && restore_and_check
  sleep 5
done
echo "GRIDDONE $(date +%H:%M:%S)"
