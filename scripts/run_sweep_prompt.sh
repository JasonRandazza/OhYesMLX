#!/bin/sh
# 06-01c: the prompt-length sweep. One cell per runtime (oq4, the one format all five serve),
# one run per (runtime, length), joined afterwards -- a sweep is a pin, never a --study axis.
#
# Length order alternates between runtimes so the longest, hottest prefills do not always land
# at the same point in a runtime's session.
#
# Osaurus runs with its prefix and block-disk caches OFF: with them on every repeated prompt
# after the first is a 0.27 s lookup, and a prefill sweep would be a flat line of cache hits.
# Authorised by Jason 2026-09-16. Both ~/.osaurus/config files are copied byte-exact before the
# toggle, modelIdleResidencyPolicy.seconds is pinned to 900 in BOTH cache states (the host's 30
# unloads the model inside the 30 s cooldown), and both are restored byte-exact at the end and
# on INT/TERM/HUP. Restoration is checked with `cmp` against the copies and never with the
# drift guard: the host's 30 differs from the committed baseline's 900 by Jason's choice, so
# the guard would report his own machine as drift forever.
set -u
cd /Users/jrazz/Dev/active/OhYesMLX
. "$(dirname "$0")/gridspec.sh"
PY=/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python
export PATH="$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH"
OUT=results/sweep-prompt
mkdir -p "$OUT"
CONF="$HOME/.osaurus/config/server-runtime.json"
SERVER="$HOME/.osaurus/config/server.json"
CONF_ORIG="$CONF.sweep-prompt-orig"
SERVER_ORIG="$SERVER.sweep-prompt-orig"

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

osaurus_cache() {  # off | on
  if [ ! -f "$CONF_ORIG" ]; then
    cp -p "$CONF" "$CONF_ORIG"        # byte-exact; the ohyesmlx-backup differs in whitespace
    cp -p "$SERVER" "$SERVER_ORIG"
    # A killed sweep must not leave Jason's Osaurus with its caches off or its model unloading
    # inside a cooldown.
    trap 'echo "ABORTED -- restoring Osaurus settings"; osaurus_restore; exit 130' INT TERM HUP
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
  # The cache flags move tracked keys off the committed baseline, so it is re-recorded for the
  # run and put back by the restore.
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

ASC="128 1024 4096 16384 32768"
DESC="32768 16384 4096 1024 128"
order=$ASC
for r in mlxlm omlx optiq vmlx osaurus; do
  [ "$r" = osaurus ] && osaurus_cache off
  for t in $order; do
    # Before as well as after: an Osaurus app relaunched between runs (seen 2026-09-16, origin
    # unknown) must not sit resident through another runtime's cell. The kill is logged.
    [ "$r" = osaurus ] || sweep
    echo "=== $r $t starting $(date +%H:%M:%S)"
    $PY -m ohyesmlx.cli run --study format --cells "oq4__$r=$Q4" --prompt-tokens "$t" \
        --results-dir "$OUT" > "$OUT/log-$r-$t.log" 2>&1
    echo "=== $r $t exit=$? $(date +%H:%M:%S)"
    sweep
  done
  [ "$r" = osaurus ] && osaurus_cache on
  [ "$order" = "$ASC" ] && order=$DESC || order=$ASC
done

restore_and_check
echo "SWEEPDONE $(date +%H:%M:%S)"
