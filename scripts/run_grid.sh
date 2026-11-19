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
PY=/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python
export PATH="$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH"
# One sweep, by process (055-03): scripts/sweep.sh, which needs $PY.
. "$(dirname "$0")/sweep.sh"
CONF="$HOME/.osaurus/config/server-runtime.json"
SERVER="$HOME/.osaurus/config/server.json"
CONF_ORIG="$CONF.grid-orig"
SERVER_ORIG="$SERVER.grid-orig"

osaurus_restore() {  # byte-exact, both files; the drift guard is not the check here
  [ -f "$CONF_ORIG" ] || return 0   # nothing was pinned, so nothing is Jason's to get back
  cp -p "$CONF_ORIG" "$CONF"
  cp -p "$SERVER_ORIG" "$SERVER"
}

# ponytail: kept rather than pointed at osaurus-pin.sh -- this pin sets
# modelIdleResidencyPolicy.seconds only and leaves the host's caches alone.
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
  sweep || exit 1
  # Restore after the sweep: a still-running Osaurus app must be dead before the host's own
  # files go back.
  [ "$r" = osaurus ] && restore_and_check
  sleep 5
done
echo "GRIDDONE $(date +%H:%M:%S)"
