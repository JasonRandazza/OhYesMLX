#!/bin/sh
# 06-02: the cold/warm KV split. One cell per runtime (oq4, the one format all five serve),
# one run per (runtime, cache state), joined afterwards by
# `ohyesmlx sweep --varying cache_state` -- a sweep is a pin, never a --study axis.
#
# Each runtime runs `off` first and `on` second, so a pair's warm column is always the later
# measurement and any thermal drift inside a pair leans the same way for all five.
#
# Osaurus is the one runtime with no cache flag: its state lives in
# ~/.osaurus/config/server-runtime.json, so this runner toggles it, re-records the baseline so
# the harness's drift guard passes, and restores both config files byte-exact afterwards (and
# on INT/TERM/HUP). The host's server.json has modelIdleResidencyPolicy.seconds = 30, which
# unloads the model inside the 30 s cooldown; BOTH states pin it to 900 for the run, and it is
# restored with everything else. Restoration is verified with `cmp` against the byte-exact
# copies rather than by the drift guard: the host's 30 differs from the committed baseline's
# 900 by Jason's choice, so `git checkout` puts the baseline back while the host keeps his 30.
set -u
cd /Users/jrazz/Dev/active/OhYesMLX
. "$(dirname "$0")/gridspec.sh"
PY=/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python
export PATH="$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH"
OUT=results/sweep-cache
mkdir -p "$OUT"
CONF="$HOME/.osaurus/config/server-runtime.json"
SERVER="$HOME/.osaurus/config/server.json"
CONF_ORIG="$CONF.sweep-cache-orig"
SERVER_ORIG="$SERVER.sweep-cache-orig"

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

osaurus_restore() {  # byte-exact, both files; the drift guard is not the check here
  [ -f "$CONF_ORIG" ] || return 0   # nothing was toggled, so nothing is Jason's to get back
  cp -p "$CONF_ORIG" "$CONF"
  cp -p "$SERVER_ORIG" "$SERVER"
  git checkout -- config/osaurus-settings-baseline.json
}

# A killed sweep must not leave Jason's Osaurus with its caches off or its model unloading
# inside a cooldown.
trap 'echo "ABORTED -- restoring Osaurus settings"; osaurus_restore; exit 130' INT TERM HUP

osaurus_state() {  # off | on
  if [ ! -f "$CONF_ORIG" ]; then
    cp -p "$CONF" "$CONF_ORIG"        # byte-exact; the ohyesmlx-backup differs in whitespace
    cp -p "$SERVER" "$SERVER_ORIG"
  fi
  # Both states are built from the host's own files, so `on` is the host's state with the idle
  # policy pinned -- not whatever the previous state left behind.
  cp -p "$CONF_ORIG" "$CONF"
  cp -p "$SERVER_ORIG" "$SERVER"
  $PY -c "
import json
conf, server, state = '$CONF', '$SERVER', '$1'
runtime = json.load(open(conf))
if state == 'off':
    runtime['cache']['prefix']['enabled'] = False
    runtime['cache']['blockDisk']['enabled'] = False
json.dump(runtime, open(conf, 'w'), indent=2)
hardware = json.load(open(server))
hardware.setdefault('modelIdleResidencyPolicy', {})['seconds'] = 900
json.dump(hardware, open(server, 'w'), indent=2)"
  $PY -c "from ohyesmlx import osaurus_settings as s; s.write_baseline()"
  echo "  osaurus cache $1 (idle residency pinned to 900 s)"
}

restore_and_check() {
  if [ ! -f "$CONF_ORIG" ]; then
    echo "  osaurus settings were never toggled; nothing to restore"
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
  for state in off on; do
    [ "$r" = osaurus ] && osaurus_state "$state"
    # Before as well as after: an Osaurus app relaunched between runs (seen 2026-09-16, origin
    # unknown) must not sit resident through another runtime's cell. The kill is logged.
    sweep
    echo "=== $r cache=$state starting $(date +%H:%M:%S)"
    $PY -m ohyesmlx.cli run --study format --cells "oq4__$r=$Q4" --prompt-tokens 4096 \
        --cache-state "$state" --results-dir "$OUT" > "$OUT/log-$r-$state.log" 2>&1
    echo "=== $r cache=$state exit=$? $(date +%H:%M:%S)"
    sweep
  done
done

restore_and_check
echo "SWEEPDONE $(date +%H:%M:%S)"
