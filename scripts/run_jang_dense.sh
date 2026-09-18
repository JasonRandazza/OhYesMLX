#!/bin/sh
# Plan 01-01, the dense JANG study: Qwen3.5-4B in five quantizations, one column per
# runtime, then a two-cell replication pass over the cells that carry the claim.
#
# --study format holds the serving runtime constant, so each column varies the format and the
# grid is the join of the two columns. The join is by explicit directory (`ohyesmlx grid`),
# never a glob: results/ accumulates runs from every session, and a directory named by
# wildcard is how columns that never belonged together get joined.
#
# Osaurus takes no tuning flags, so what its column measures lives in ~/.osaurus/config.
# Around that column only, both files are copied byte-exact, modelIdleResidencyPolicy.seconds
# is pinned to 900 (the host's 30 unloads the model inside the 30 s cooldown, and 900 is what
# the recorded baseline holds, so the pin is also what lets the drift guard pass), and both
# are restored byte-exact afterwards and on INT/TERM/HUP, checked with `cmp`. vMLX sees no
# settings write at all. The replication pass runs the same protocol a second time, so it is
# two functions rather than one inline block.
#
# `set -e` is deliberately absent: a column's exit code is a fact this runner reports, and
# exiting on it mid-flow would leave Jason's Osaurus pinned with no restore performed. Every
# step's status is captured instead and the runner exits non-zero after the flow finishes.
#
# Nothing else may run on this machine while this runs. Not a test suite, not a git
# operation. That rule cost a column on 2026-09-16.
set -u
cd /Users/jrazz/Dev/active/OhYesMLX
PY=/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python
export PATH="$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH"

H=$HOME/.cache/huggingface/hub
S4="$H/models--mlx-community--Qwen3.5-4B-4bit/snapshots/0e7ffd5c629ef7719d4cbc04069232580bfa9d9c"
Q4="$H/models--RepublicOfKorokke--Qwen3.5-4B-oQ4/snapshots/3ae88a7d17b1c6bb71b795c1090948a82508fdb8"
QE="$H/models--uingei--Qwen3.5-4B-oQ4e/snapshots/2e232d525d5df5e7a6eece4b03b17087e6b3c3ac"
OQ="$H/models--mlx-community--Qwen3.5-4B-OptiQ-4bit/snapshots/6cb5bdfd0bf15f484881fb9f1ab6d7c840fddde9"
JG="$H/models--JANGQ-AI--Qwen3.5-4B-JANG_4S/snapshots/4567967a46cd9e9bf26d3bb491ddd422ad607775"

CELLS_vmlx="stock4bit__vmlx=$S4,oq4__vmlx=$Q4,oq4e__vmlx=$QE,jang4s__vmlx=$JG"
CELLS_osaurus="oq4__osaurus=$Q4,oq4e__osaurus=$QE,optiq__osaurus=$OQ,jang4s__osaurus=$JG"
REPL_vmlx="stock4bit__vmlx=$S4,jang4s__vmlx=$JG"
REPL_osaurus="oq4__osaurus=$Q4,jang4s__osaurus=$JG"

OUT=results/grid-jang-dense
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
  $PY -m ohyesmlx.cli run --study format --cells "$4" --results-dir "$2" > "$3" 2>&1
  rc=$?
  echo "=== COLUMN $1 exit=$rc $(date +%H:%M:%S)"
  [ "$rc" -eq 0 ] || FAILED=1
  return 0
}

osaurus_restore() {  # byte-exact, both files; the drift guard is not the check here
  [ -f "$CONF_ORIG" ] || return 0   # nothing was pinned, so nothing is Jason's to get back
  cp -p "$CONF_ORIG" "$CONF"
  cp -p "$SERVER_ORIG" "$SERVER"
}

osaurus_pin() {
  if [ ! -f "$CONF_ORIG" ]; then
    cp -p "$CONF" "$CONF_ORIG"        # byte-exact; the ohyesmlx-backup differs in whitespace
    cp -p "$SERVER" "$SERVER_ORIG"
    # A killed run must not leave Jason's Osaurus unloading its model inside a cooldown.
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

# Step 3 -- the Osaurus column, under the pinned idle residency.
osaurus_pin
column osaurus "$OUT" "$OUT/log-osaurus.log" "$CELLS_osaurus"
OSAURUS_DIR=$(newest_run_dir "$OUT")

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

# Step 6 -- the replication pass: the two cells carrying the claim, re-measured on each
# runtime into a directory of its own, so a replication cannot be mistaken for the grid it
# replicates.
column vmlx-repl "$OUT/replicate" "$OUT/replicate/log-vmlx-repl.log" "$REPL_vmlx"
echo "--- sweep after vmlx-repl $(date +%H:%M:%S)"
sweep
osaurus_pin
column osaurus-repl "$OUT/replicate" "$OUT/replicate/log-osaurus-repl.log" "$REPL_osaurus"
echo "--- sweep after osaurus-repl $(date +%H:%M:%S)"
sweep
restore_and_check

# Step 7 -- summary.
echo "SUMMARY $(date +%H:%M:%S)"
echo "  vmlx column     : ${VMLX_DIR:-<none>}  (log $OUT/log-vmlx.log)"
echo "  osaurus column  : ${OSAURUS_DIR:-<none>}  (log $OUT/log-osaurus.log)"
echo "  grid            : $OUT/grid.md"
echo "  replication     : $OUT/replicate  (log-vmlx-repl.log, log-osaurus-repl.log)"
[ "$FAILED" -eq 0 ] || { echo "JANG DENSE FAILED -- a step above returned non-zero"; exit 1; }
echo "JANGDENSEDONE $(date +%H:%M:%S)"
exit 0
