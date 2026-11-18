# Sourced, not run. The Osaurus settings pin for the Phase 4 runners, run_grid_35b.sh now among
# its callers: `osaurus_settings.pin` copies both ~/.osaurus/config files and the drift guard's
# baseline byte-exact into a backup directory, then
#   modelIdleResidencyPolicy.seconds = 900 (the host's 30 unloads the model inside the 30 s
#     cooldown, and the drift guard refuses to start against the committed baseline's 900),
#   cache.prefix.enabled = cache.blockDisk.enabled = false (the other four runtimes prefill cold),
# and afterwards `osaurus_settings.restore` puts all three files back and returns true only when
# each is byte-identical to its backup. The baseline it writes is the committed one with only
# those keys overridden -- never the live host, which would make the drift gate compare the host
# with itself (Fable S5-F8).
# 2026-09-25: the Phase 4 night ran without this and every Osaurus cell was N/A. The edit, the
# copies and the byte-exact check live in ohyesmlx/osaurus_settings.py -- one definition, which
# quickbench calls too; this file is the shell wrapper around it.
# ponytail: copies remain in run_grid.sh / run_grid_moe.sh (they pin idle 900 only and leave the
# host's caches alone), run_sweep_cache*.sh (there the Osaurus cache IS the varied pin), and
# run_accuracy_*.sh / run_jang_*.sh / run_sweep_prompt.sh; point them here when next touched.
# Needs $PY and a sweep() from the caller. osaurus_pin installs a restoring trap; callers call
# osaurus_restore_check when their Osaurus runs are done.
CONFIG_DIR="$HOME/.osaurus/config"
# `osaurus_settings.BACKUP_DIR`, derived from CONFIG_DIR rather than respelled so a scratch HOME
# pins under its own backup directory. That module is the one definition; quickbench's default
# and the app's launch recovery read the same path, so a backup any of the three leaves behind
# is found by the other two (Fable S5-F6).
BACKUP_DIR="$CONFIG_DIR.ohyesmlx-backup"
CONF="$CONFIG_DIR/server-runtime.json"
SERVER="$CONFIG_DIR/server.json"
CONF_ORIG="$BACKUP_DIR/server-runtime.json"
SERVER_ORIG="$BACKUP_DIR/server.json"

# The one restore, and the only thing here that prints a restore's verdict: the signal trap, the
# EXIT trap and osaurus_restore_check all call it. Returns non-zero when the restore did not
# verify -- and re-installs the restoring trap, so an interrupt after a failed check still
# attempts one. Silent when there is no backup left to put back, which is the ordinary state
# after a verified restore and what a clean run's EXIT trap sees.
osaurus_restore() {
  if [ ! -f "$CONF_ORIG" ] && [ ! -f "$SERVER_ORIG" ]; then return 0; fi
  if $PY -c "
from ohyesmlx import osaurus_settings as s
raise SystemExit(0 if s.restore('$CONFIG_DIR', backup_dir='$BACKUP_DIR') else 1)"; then
    echo "  osaurus settings restored byte-exact (cmp)"
    return 0
  fi
  echo "RESTORE FAILED: ~/.osaurus/config differs from $BACKUP_DIR -- copies kept"
  osaurus_restore_trap
  return 1
}

# The traps, written once so the abort path and the exit path cannot restore differently. EXIT
# covers what a signal does not: a `set -u` abort, a failed command and a plain return, each of
# which used to leave the host pinned with no backup tried.
osaurus_restore_trap() {
  trap 'echo "ABORTED $(date +%H:%M:%S) -- restoring Osaurus settings"; sweep; osaurus_restore; exit 130' INT TERM HUP
  trap 'osaurus_restore || true' EXIT
}

osaurus_pin() {
  osaurus_restore_trap
  $PY -c "
from ohyesmlx import osaurus_settings as s
s.pin('$CONFIG_DIR', backup_dir='$BACKUP_DIR')" || return 1
  echo "  osaurus cache off & idle residency pinned to 900 s"
}

# Set concurrency.maxConcurrentSequences = N, the batch cap following the run's own N -- the rule
# Decision 129 wrote as runtimes.Omlx.start_command's --max-concurrent-requests (OptiQ's
# --max-concurrent and vMLX's --max-num-seqs are the same edit). Osaurus takes no such flag, so
# its cap is this host setting.
#
# The edit is `osaurus_settings.set_key`'s: temp-and-replace on the user's own file, a read-back,
# and the baseline updated under the pin's rule. This wrapper writes no JSON itself -- an
# in-place rewrite here truncated server-runtime.json before writing it (Fable S5-F12). Refuses
# before osaurus_pin has copied $CONF byte-exact, in this backup directory or a legacy one: with
# no copy there is nothing osaurus_restore_check's byte-exact check could put back, and the host
# would silently keep the run's N.
osaurus_set_seqs() {
  case ${1:-} in
    ''|*[!0-9]*) echo "osaurus_set_seqs: refusing -- expected a positive integer, got '${1:-}'"; return 1 ;;
  esac
  # Leading zeros are still the same number: "00" is 0, which is not positive, and the Python
  # below would not even parse it.
  digits=${1#"${1%%[1-9]*}"}
  if [ -z "$digits" ]; then
    echo "osaurus_set_seqs: refusing -- expected a positive integer, got '$1'"
    return 1
  fi
  if ! $PY -c "
from ohyesmlx import osaurus_settings as s
raise SystemExit(0 if s.backup_dirs_holding('$CONFIG_DIR', backup_dir='$BACKUP_DIR') else 1)"; then
    echo "osaurus_set_seqs: refusing -- osaurus_pin has not run, so $CONF has no byte-exact backup to restore"
    return 1
  fi
  $PY -c "
from ohyesmlx import osaurus_settings as s
key = 'server-runtime.json:concurrency.maxConcurrentSequences'
host = s.set_key(key, int('$1'), config_dir='$CONFIG_DIR')
print('  osaurus %s = %r (baseline re-recorded)' % (key, host))"
}

osaurus_restore_check() {
  if [ ! -f "$CONF_ORIG" ] && [ ! -f "$SERVER_ORIG" ]; then
    echo "  osaurus settings were never pinned; nothing to restore"
    return 0
  fi
  osaurus_restore
}
