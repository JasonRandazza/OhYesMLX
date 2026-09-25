# Sourced, not run. The Osaurus settings pin for the Phase 4 runners, run_grid_35b.sh now among
# its callers: both ~/.osaurus/config files are copied byte-exact, then
#   modelIdleResidencyPolicy.seconds = 900 (the host's 30 unloads the model inside the 30 s
#     cooldown, and the drift guard refuses to start against the committed baseline's 900),
#   cache.prefix.enabled = cache.blockDisk.enabled = false (the other four runtimes prefill cold),
# the baseline is re-recorded so the guard passes, and afterwards both files are restored and
# verified with `cmp`. 2026-09-25: the Phase 4 night ran without this and every Osaurus cell was N/A.
# ponytail: copies remain in run_grid.sh / run_grid_moe.sh (they pin idle 900 only and leave the
# host's caches alone), run_sweep_cache*.sh (there the Osaurus cache IS the varied pin), and
# run_accuracy_*.sh / run_jang_*.sh / run_sweep_prompt.sh; point them here when next touched.
# Needs $PY and a sweep() from the caller; both traps sweep, as the callers' own does. osaurus_pin installs a restoring trap; callers call
# osaurus_restore_check when their Osaurus runs are done.
CONF="$HOME/.osaurus/config/server-runtime.json"
SERVER="$HOME/.osaurus/config/server.json"
CONF_ORIG="$CONF.phase4-orig"
SERVER_ORIG="$SERVER.phase4-orig"

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
  fi
  trap 'echo "ABORTED $(date +%H:%M:%S) -- restoring Osaurus settings"; sweep; osaurus_restore; exit 130' INT TERM HUP
  $PY -c "
import json
conf, server = '$CONF', '$SERVER'
runtime = json.load(open(conf))
runtime.setdefault('cache', {}).setdefault('prefix', {})['enabled'] = False
runtime['cache'].setdefault('blockDisk', {})['enabled'] = False
json.dump(runtime, open(conf, 'w'), indent=2)
hardware = json.load(open(server))
hardware.setdefault('modelIdleResidencyPolicy', {})['seconds'] = 900
json.dump(hardware, open(server, 'w'), indent=2)"
  $PY -c "from ohyesmlx import osaurus_settings as s; s.write_baseline()"
  echo "  osaurus cache off & idle residency pinned to 900 s"
}

osaurus_restore_check() {
  [ -f "$CONF_ORIG" ] || { echo "  osaurus settings were never pinned; nothing to restore"; return 0; }
  osaurus_restore
  if cmp -s "$CONF" "$CONF_ORIG" && cmp -s "$SERVER" "$SERVER_ORIG"; then
    echo "  osaurus settings restored byte-exact (cmp)"
    rm -f "$CONF_ORIG" "$SERVER_ORIG"
  else
    echo "RESTORE FAILED: ~/.osaurus/config differs from $CONF_ORIG / $SERVER_ORIG -- copies kept"
  fi
  trap 'echo "ABORTED $(date +%H:%M:%S)"; sweep; exit 130' INT TERM HUP
}
