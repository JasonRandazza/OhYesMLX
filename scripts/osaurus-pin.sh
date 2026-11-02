# Sourced, not run. The Osaurus settings pin for the Phase 4 runners, run_grid_35b.sh now among
# its callers: `osaurus_settings.pin` copies both ~/.osaurus/config files byte-exact into a backup
# directory, then
#   modelIdleResidencyPolicy.seconds = 900 (the host's 30 unloads the model inside the 30 s
#     cooldown, and the drift guard refuses to start against the committed baseline's 900),
#   cache.prefix.enabled = cache.blockDisk.enabled = false (the other four runtimes prefill cold),
# the baseline is re-recorded so the guard passes, and afterwards `osaurus_settings.restore` puts
# both files back and returns true only when each is byte-identical to its backup. 2026-09-25: the
# Phase 4 night ran without this and every Osaurus cell was N/A. The edit, the copies and the
# byte-exact check live in ohyesmlx/osaurus_settings.py -- one definition, which quickbench calls
# too; this file is the shell wrapper around it.
# ponytail: copies remain in run_grid.sh / run_grid_moe.sh (they pin idle 900 only and leave the
# host's caches alone), run_sweep_cache*.sh (there the Osaurus cache IS the varied pin), and
# run_accuracy_*.sh / run_jang_*.sh / run_sweep_prompt.sh; point them here when next touched.
# Needs $PY and a sweep() from the caller; both traps sweep, as the callers' own does. osaurus_pin installs a restoring trap; callers call
# osaurus_restore_check when their Osaurus runs are done.
CONFIG_DIR="$HOME/.osaurus/config"
BACKUP_DIR="$CONFIG_DIR.phase4-orig"
CONF="$CONFIG_DIR/server-runtime.json"
SERVER="$CONFIG_DIR/server.json"
CONF_ORIG="$BACKUP_DIR/server-runtime.json"
SERVER_ORIG="$BACKUP_DIR/server.json"

osaurus_restore() {
  if [ ! -f "$CONF_ORIG" ] && [ ! -f "$SERVER_ORIG" ]; then return 0; fi
  $PY -c "
from ohyesmlx import osaurus_settings as s
s.restore('$CONFIG_DIR', backup_dir='$BACKUP_DIR')" || return 1
  git checkout -- config/osaurus-settings-baseline.json
}

osaurus_pin() {
  trap 'echo "ABORTED $(date +%H:%M:%S) -- restoring Osaurus settings"; sweep; osaurus_restore; exit 130' INT TERM HUP
  $PY -c "
from ohyesmlx import osaurus_settings as s
s.pin('$CONFIG_DIR', backup_dir='$BACKUP_DIR')" || return 1
  echo "  osaurus cache off & idle residency pinned to 900 s"
}

# Set concurrency.maxConcurrentSequences = N, the batch cap following the run's own N -- the rule
# Decision 129 wrote as runtimes.Omlx.start_command's --max-concurrent-requests (OptiQ's
# --max-concurrent and vMLX's --max-num-seqs are the same edit). Osaurus takes no such flag, so
# its cap is this host setting. The baseline is re-recorded exactly as osaurus_pin does it, or
# osaurus_settings' drift gate refuses every start. Refuses before osaurus_pin has copied $CONF
# byte-exact: with no copy there is nothing osaurus_restore_check's byte-exact check could put
# back, and the host would silently keep the run's N.
osaurus_set_seqs() {
  case ${1:-} in
    ''|*[!0-9]*) echo "osaurus_set_seqs: refusing -- expected a positive integer, got '${1:-}'"; return 1 ;;
  esac
  if [ ! -f "$CONF_ORIG" ]; then
    echo "osaurus_set_seqs: refusing -- osaurus_pin has not run, so $CONF has no byte-exact backup to restore"
    return 1
  fi
  $PY -c "
import json
from ohyesmlx import osaurus_settings as s
conf = '$CONF'
key = 'server-runtime.json:concurrency.maxConcurrentSequences'
runtime = json.load(open(conf))
runtime.setdefault('concurrency', {})['maxConcurrentSequences'] = $1
json.dump(runtime, open(conf, 'w'), indent=2)
host = s.capture_osaurus_settings()[key]
if host != $1:
    raise SystemExit('osaurus_set_seqs: %s reads back %r, not $1' % (key, host))
s.write_baseline()
print('  osaurus %s = %r (baseline re-recorded)' % (key, host))"
}

osaurus_restore_check() {
  if [ ! -f "$CONF_ORIG" ] && [ ! -f "$SERVER_ORIG" ]; then
    echo "  osaurus settings were never pinned; nothing to restore"
    return 0
  fi
  # The byte-exact check is `osaurus_settings.restore`'s `filecmp.cmp(shallow=False)` -- the one
  # definition of it -- and its verdict is printed here exactly as the `cmp` it replaced was.
  if $PY -c "
from ohyesmlx import osaurus_settings as s
raise SystemExit(0 if s.restore('$CONFIG_DIR', backup_dir='$BACKUP_DIR') else 1)"; then
    echo "  osaurus settings restored byte-exact (cmp)"
  else
    echo "RESTORE FAILED: ~/.osaurus/config differs from $BACKUP_DIR -- copies kept"
  fi
  git checkout -- config/osaurus-settings-baseline.json
  trap 'echo "ABORTED $(date +%H:%M:%S)"; sweep; exit 130' INT TERM HUP
}
