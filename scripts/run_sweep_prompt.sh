#!/bin/sh
# 06-01c: the prompt-length sweep. One cell per runtime (oq4, the one format all five serve),
# one run per (runtime, length), joined afterwards -- a sweep is a pin, never a --study axis.
#
# Length order alternates between runtimes so the longest, hottest prefills do not always land
# at the same point in a runtime's session.
#
# Osaurus runs with its prefix and block-disk caches OFF: with them on every repeated prompt
# after the first is a 0.27 s lookup, and a prefill sweep would be a flat line of cache hits.
# Authorised by Jason 2026-09-16. Restored from the ohyesmlx-backup afterwards, and the runner
# refuses to exit clean unless the drift guard reads NONE again.
set -u
cd /Users/jrazz/Dev/active/OhYesMLX
. "$(dirname "$0")/gridspec.sh"
PY=/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python
export PATH="$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH"
OUT=results/sweep-prompt
mkdir -p "$OUT"
CONF="$HOME/.osaurus/config/server-runtime.json"

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

drift_none() {  # the host against the COMMITTED baseline, not whatever was last written
  $PY -c "
import json, subprocess, sys
from ohyesmlx import osaurus_settings as s
base = json.loads(subprocess.check_output(['git', 'show', 'HEAD:config/osaurus-settings-baseline.json']))['settings']
d = s.diff_against_baseline(s.capture_osaurus_settings(), base)
print(s.describe_drift(d) if d else '  drift NONE'); sys.exit(1 if d else 0)"
}

osaurus_cache() {  # off | on
  if [ "$1" = off ]; then
    drift_none || { echo "ABORT: Osaurus had drifted before the toggle"; exit 1; }
    cp -p "$CONF" "$CONF.sweep-prompt-orig"   # byte-exact; the ohyesmlx-backup differs in whitespace
    # A killed sweep must not leave Jason's Osaurus with its caches off.
    trap 'cp -p "$CONF.sweep-prompt-orig" "$CONF"; git checkout -- config/osaurus-settings-baseline.json; exit 130' INT TERM HUP
    $PY -c "
import json; p='$CONF'; d=json.load(open(p))
d['cache']['prefix']['enabled']=False; d['cache']['blockDisk']['enabled']=False
open(p,'w').write(json.dumps(d, indent=2))"
    $PY -c "from ohyesmlx import osaurus_settings as s; s.write_baseline()"
  else
    cp -p "$CONF.sweep-prompt-orig" "$CONF"
    git checkout -- config/osaurus-settings-baseline.json
    drift_none || { echo "RESTORE FAILED: Osaurus settings still drift"; exit 1; }
  fi
  echo "  osaurus cache $1"
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

drift_none || { echo "SWEEP ENDED WITH OSAURUS DRIFT"; exit 1; }
echo "SWEEPDONE $(date +%H:%M:%S)"
