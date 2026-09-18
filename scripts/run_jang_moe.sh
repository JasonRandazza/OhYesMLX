#!/bin/sh
# Plan 01-02, the MoE JANG study: LFM2.5-8B-A1B in five quantizations, one column per runtime,
# then a two-cell replication pass over the cells that carry the claim.
#
# --study format holds the serving runtime constant, so each column varies the format and the
# grid is the join of the two columns. The join is by explicit directory (`ohyesmlx grid`),
# never a glob: results/ accumulates runs from every session, and a directory named by
# wildcard is how columns that never belonged together get joined. This campaign keeps its own
# directory for the other half of that rule -- join guard 3 refuses one label pointing at two
# artifacts, and `stock4bit` is the dense snapshot in one campaign and the MoE snapshot in the
# other, so the two grids are never joined and never may be.
#
# Every run carries `--cache-state off`: the header records the pin, vMLX already starts that
# way, and Osaurus -- which cannot be told from any command line -- is held to it by the host
# toggle below. v1 measured these same cells with no cache pin at all, so these runs cannot be
# joined with any v1 run directory, and a prose comparison has to name the difference.
#
# Osaurus takes no tuning flags, so what its column measures lives in ~/.osaurus/config.
# Around that column only, both files are copied byte-exact, the prefix and block-disk caches
# are turned off (with them on, a repeated prefill prompt is a lookup and the prefill column
# measures a cache hit), modelIdleResidencyPolicy.seconds is pinned to 900 (the host's 30
# unloads the model inside the 30 s cooldown, and 900 is what the recorded baseline holds, so
# the pin is also what lets the drift guard pass), and both are restored byte-exact afterwards
# and on INT/TERM/HUP, checked with `cmp`. The committed baseline is restored with the files,
# because the cache toggle moves tracked keys off it. vMLX sees no settings write at all. The
# replication pass runs the same protocol a second time, so it is one function called twice
# rather than one inline block.
#
# `set -e` is deliberately absent: a column's exit code is a fact this runner reports, and
# exiting on it mid-flow would leave Jason's Osaurus with its caches off and no restore
# performed. Every step's status is captured instead and the runner exits non-zero after the
# flow finishes.
#
# Nothing else may run on this machine while this runs. Not a test suite, not a git
# operation. That rule cost a column on 2026-09-16.
set -u
cd /Users/jrazz/Dev/active/OhYesMLX
PY=/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python
export PATH="$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH"

H=$HOME/.cache/huggingface/hub
S4="$H/models--mlx-community--LFM2.5-8B-A1B-MLX-4bit/snapshots/146590a491db88581884033023f51f6b49a27b89"
Q4="$H/models--stamsam--LFM2.5-8B-A1B-oQ4/snapshots/acb4fd209565b7c05de287488416f4217820a3db"
QE="$H/models--brainworkup--LFM2.5-8B-A1B-oQ4e/snapshots/88977e47cd1fe2eb5ec5bf5230d3de9868adef9e"
OQ="$H/models--mlx-community--LFM2.5-8B-A1B-OptiQ-4bit/snapshots/5a5c595823cf26ab1068508eb5cf85816bb2db6b"
JG="$H/models--JANGQ-AI--LFM2.5-8B-A1B-JANG_2L/snapshots/5fb82773427c2f25395de8821eff6d95e86feb53"

CELLS_vmlx="stock4bit__vmlx=$S4,oq4__vmlx=$Q4,oq4e__vmlx=$QE,optiq__vmlx=$OQ,jang2l__vmlx=$JG"
CELLS_osaurus="stock4bit__osaurus=$S4,oq4__osaurus=$Q4,oq4e__osaurus=$QE,optiq__osaurus=$OQ,jang2l__osaurus=$JG"

OUT=results/grid-jang-moe
mkdir -p "$OUT/replicate"
# The runner owns its log. A caller-side `cmd & > file` came unbound from its command on
# 2026-09-16 and left runner.log at 0 bytes, so the echoes here have an exec redirect they
# cannot be separated from. The per-column redirects below still override per command.
exec > "$OUT/runner.log" 2>&1

CONF="$HOME/.osaurus/config/server-runtime.json"
SERVER="$HOME/.osaurus/config/server.json"
CONF_ORIG="$CONF.grid-orig"
SERVER_ORIG="$SERVER.grid-orig"

FAILED=0

sweep() {  # ports first, then stale apps; a leaked resident would contend for the memory the next column measures
  for p in 8081 1337 8100 8080 8000; do
    h=$(lsof -ti:$p 2>/dev/null | head -1); [ -n "$h" ] && { echo "  sweeping port $p pid $h"; kill -9 "$h" 2>/dev/null; }
  done
  # Osaurus releases its port on `stop` and leaves the app running, so a port sweep misses
  # it and the leftovers accumulate at ~900 MB each -- three of them, aged 5-7 h, were
  # resident through both grids on 2026-09-16. Swept by FULL EXECUTABLE PATH, never by the
  # name `osaurus`: `osaurus mcp` is a long-running user process and must not be touched.
  for h in $(pgrep -f "^/Applications/osaurus.app/Contents/MacOS/osaurus" 2>/dev/null); do
    echo "  sweeping stale osaurus app pid $h"; kill -9 "$h" 2>/dev/null
  done
  sleep 5
}

newest_run_dir() {  # <results-dir>: run dirs are stamped UTC and sort chronologically
  ls -1d "$1"/*-format 2>/dev/null | sort | tail -1
}

column() {  # <label> <results-dir> <log> <cells>: one --study format column, status reported
  echo "=== COLUMN $1 starting $(date +%H:%M:%S)"
  $PY -m ohyesmlx.cli run --study format --cache-state off --cells "$4" --results-dir "$2" \
      > "$3" 2>&1
  rc=$?
  echo "=== COLUMN $1 exit=$rc $(date +%H:%M:%S)"
  [ "$rc" -eq 0 ] || FAILED=1
  return 0
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
    # A killed run must not leave Jason's Osaurus with its caches off or its model unloading
    # inside a cooldown.
    trap 'echo "ABORTED -- restoring Osaurus settings"; osaurus_restore; exit 130' INT TERM HUP
  fi
  # Both states are built from the host's own files, so the state is the host's state with the
  # study's changes applied -- not whatever the previous state left behind.
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

artifact_of() {  # <label>: the snapshot that label named in this campaign's columns
  case "$1" in
    stock4bit) echo "$S4" ;;
    oq4) echo "$Q4" ;;
    oq4e) echo "$QE" ;;
    optiq) echo "$OQ" ;;
    *) echo "" ;;
  esac
}

best_portable() {  # <run-dir> <fallback-label>: the portable that led on decode in that column
  # Design doc §2.5: the replicate names the JANG cell and the portable cell it beat (or lost
  # to) by the widest margin. Reading that off the primary's own decode rows -- through the
  # same load_run + summarize the grid uses -- means the replicate follows the data instead of
  # a label hard-coded before it existed; the fallback fires only when the primary wrote no
  # readable decode row at all. A label outside the campaign's four portables also falls back:
  # the artifact table above is what the cell string is built from.
  if [ -z "$1" ]; then
    echo "$2"
    return 0
  fi
  $PY -c "
from ohyesmlx import measure, report
header, results = measure.load_run('$1')
rows = report.summarize(results, measured=header.get('measured'))
ports = [r for r in rows
         if r['workload_id'] == 'decode' and 'jang' not in r['label'].lower()
         and r['decode_tps'] is not None]
best = max(ports, key=lambda r: r['decode_tps'])['label'] if ports else ''
print(best if best in ('stock4bit', 'oq4', 'oq4e', 'optiq') else '$2')
" 2>/dev/null || echo "$2"
}

# Pre-sweep: ensure all ports are free and no stale runtimes are resident.
echo "--- pre-sweep $(date +%H:%M:%S)"
sweep

# Step 1 -- the vMLX column.
column vmlx "$OUT" "$OUT/log-vmlx.log" "$CELLS_vmlx"
VMLX_DIR=$(newest_run_dir "$OUT")
[ -n "$VMLX_DIR" ] || { echo "VMLX COLUMN WROTE NO RUN DIR"; FAILED=1; }

# Step 2 -- sweep between columns.
echo "--- sweep after vmlx $(date +%H:%M:%S)"
sweep

# Step 3 -- the Osaurus column, with the host's caches off and the idle residency pinned.
osaurus_cache off
column osaurus "$OUT" "$OUT/log-osaurus.log" "$CELLS_osaurus"
OSAURUS_DIR=$(newest_run_dir "$OUT")
[ -n "$OSAURUS_DIR" ] || { echo "OSAURUS COLUMN WROTE NO RUN DIR"; FAILED=1; }

# Step 4 -- sweep, then restore: a still-running Osaurus app must be dead before the host's
# own files go back.
echo "--- sweep after osaurus $(date +%H:%M:%S)"
sweep
restore_and_check

# Step 5 -- join the two columns. The run directories are named one by one; `grid` refuses to
# render rather than join runs whose pins or versions disagree.
if [ -n "$VMLX_DIR" ] && [ -n "$OSAURUS_DIR" ] && [ "$VMLX_DIR" != "$OSAURUS_DIR" ]; then
  echo "=== GRID vmlx=$VMLX_DIR osaurus=$OSAURUS_DIR starting $(date +%H:%M:%S)"
  $PY -m ohyesmlx.cli grid "$VMLX_DIR" "$OSAURUS_DIR" --out "$OUT/grid.md"
  rc=$?
  echo "=== GRID exit=$rc $(date +%H:%M:%S)"
  [ "$rc" -eq 0 ] || FAILED=1
else
  echo "GRID SKIPPED: vmlx='${VMLX_DIR:-}' osaurus='${OSAURUS_DIR:-}' -- one column wrote no run dir"
  FAILED=1
fi

# Step 6 -- the replication pass, in the reverse column order of the primary: Osaurus's
# replicate first, vMLX's second (design doc §2.5). Walking the same order twice would alias a
# session-long thermal or load trend onto runtime identity, and the reversal is the cheap
# defence. Each replicate names only the two decisive cells of its column -- the JANG cell and
# the portable it beat (or lost to) by the widest margin -- resolved from the primary's own
# decode rows because that margin is a measurement, not an input.
BEST_osaurus=$(best_portable "$OSAURUS_DIR" oq4)
BEST_vmlx=$(best_portable "$VMLX_DIR" stock4bit)
REPL_osaurus="jang2l__osaurus=$JG,${BEST_osaurus}__osaurus=$(artifact_of "$BEST_osaurus")"
REPL_vmlx="jang2l__vmlx=$JG,${BEST_vmlx}__vmlx=$(artifact_of "$BEST_vmlx")"
echo "  replicate cells: osaurus '$REPL_osaurus'"
echo "  replicate cells: vmlx    '$REPL_vmlx'"

osaurus_cache off
column osaurus-repl "$OUT/replicate" "$OUT/replicate/log-osaurus-repl.log" "$REPL_osaurus"
echo "--- sweep after osaurus-repl $(date +%H:%M:%S)"
sweep
restore_and_check

column vmlx-repl "$OUT/replicate" "$OUT/replicate/log-vmlx-repl.log" "$REPL_vmlx"
echo "--- sweep after vmlx-repl $(date +%H:%M:%S)"
sweep

# Step 7 -- summary.
echo "SUMMARY $(date +%H:%M:%S)"
echo "  vmlx column     : ${VMLX_DIR:-<none>}  (log $OUT/log-vmlx.log)"
echo "  osaurus column  : ${OSAURUS_DIR:-<none>}  (log $OUT/log-osaurus.log)"
echo "  grid            : $OUT/grid.md"
echo "  replication     : $OUT/replicate  (log-osaurus-repl.log, log-vmlx-repl.log)"
[ "$FAILED" -eq 0 ] || { echo "JANG MOE FAILED -- a step above returned non-zero"; exit 1; }
echo "JANGMOEDONE $(date +%H:%M:%S)"
exit 0
