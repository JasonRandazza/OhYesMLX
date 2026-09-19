#!/usr/bin/env bash
# Milestone v2, candidate 2: the vMLX JIT A/B. The same two JANG cells measured twice on
# vMLX 1.6.59 -- once with `--no-jit`, once with `--enable-jit` -- across a dense
# (Qwen3.5-4B-JANG_4S) and an MoE (LFM2.5-8B-A1B-JANG_2L) artifact.
#
# JIT is the variable and the environment variable is how it moves: `Vmlx.start_command` reads
# OHYESMLX_VMLX_ENABLE_JIT and flips exactly one flag, so the two columns' commands differ by
# that flag alone and every other byte is the command every earlier vMLX row was measured
# with. The pin rides in each column's own environment, so a run's command cannot disagree
# with the JIT state its directory is named for. Unset means `--no-jit`, which is why the
# jit-off column is directly comparable to the recorded vMLX rows.
#
# The two columns are joined afterwards by explicit directory, never a glob: results/
# accumulates runs from every session, and a directory named by wildcard is how columns that
# never belonged together get joined.
#
# The sweep before each column and the 30 s cooldown between them are the two places this
# runner defends "nothing else runs while a cell measures". Osaurus releases its port on
# `stop` and leaves the app resident at ~900 MB, so a port sweep misses it by design; a
# leftover resident would contend for the unified memory the next column's numbers are
# measured against.
#
# `set -e` is deliberately absent: a column's exit code is a fact this runner reports, and
# exiting on it mid-flow would leave the machine unswept with the next column never run.
# Every step's status is captured instead and the runner exits non-zero after the flow ends.
set -u
cd /Users/jrazz/Dev/active/OhYesMLX
PY=/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python
export PATH="$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH"
H=$HOME/.cache/huggingface/hub
JG="$H/models--JANGQ-AI--Qwen3.5-4B-JANG_4S/snapshots/4567967a46cd9e9bf26d3bb491ddd422ad607775"
JM="$H/models--JANGQ-AI--LFM2.5-8B-A1B-JANG_2L/snapshots/5fb82773427c2f25395de8821eff6d95e86feb53"
CELLS="jang4s__vmlx=$JG,jang2l__vmlx=$JM"
OUT=results/vmlx-jit-ab
mkdir -p "$OUT"
# The runner owns its log. A caller-side `cmd & > file` came unbound from its command on
# 2026-09-16 and left runner.log at 0 bytes; an exec redirect cannot be separated from the
# echoes it covers. The column commands below are not redirected, so their progress lands
# here too -- `tail -f results/vmlx-jit-ab/runner.log` to watch a run.
exec > "$OUT/runner.log" 2>&1

FAILED=0

sweep() {  # ports first, then stale apps; a leaked resident would contend for the memory the next column measures
  for p in 8081 1337 8100 8080 8000; do
    h=$(lsof -ti:$p 2>/dev/null | head -1); [ -n "$h" ] && { echo "  sweeping port $p pid $h"; kill -9 "$h" 2>/dev/null; }
  done
  # Osaurus releases its port on `stop` and leaves the app running, so a port sweep misses
  # it. Swept by FULL EXECUTABLE PATH, never by the name `osaurus`: `osaurus mcp` is Jason's
  # long-running process and must not be touched.
  for h in $(pgrep -f "^/Applications/osaurus.app/Contents/MacOS/osaurus" 2>/dev/null); do
    echo "  sweeping stale osaurus app pid $h"; kill -9 "$h" 2>/dev/null
  done
  sleep 5
}

# Step 1 -- initial sweep: no earlier tenant of these five ports may be resident.
echo "--- initial sweep $(date +%H:%M:%S)"
sweep

# Step 2 -- column 1, JIT off. This is the byte-identical default and the column the JIT-on
# one is read against.
echo "=== COLUMN jit-off starting $(date +%H:%M:%S)"
OHYESMLX_VMLX_ENABLE_JIT=0 $PY -m ohyesmlx.cli run --study format --cells "$CELLS" --results-dir "$OUT/jit-off"
rc=$?
echo "=== COLUMN jit-off exit=$rc $(date +%H:%M:%S)"
[ "$rc" -eq 0 ] || FAILED=1

# Step 3 -- post-column sweep, then the cooldown: the machine is an M2 Max in a laptop chassis
# and throttles under sustained inference, so the second column starts from the temperature
# the first one did.
echo "--- sweep after jit-off $(date +%H:%M:%S)"
sweep
echo "--- 30 s thermal cooldown $(date +%H:%M:%S)"
sleep 30

# Step 4 -- column 2, JIT on. Same cells, same pins; only the JIT flag moved.
echo "=== COLUMN jit-on starting $(date +%H:%M:%S)"
OHYESMLX_VMLX_ENABLE_JIT=1 $PY -m ohyesmlx.cli run --study format --cells "$CELLS" --results-dir "$OUT/jit-on"
rc=$?
echo "=== COLUMN jit-on exit=$rc $(date +%H:%M:%S)"
[ "$rc" -eq 0 ] || FAILED=1

# Step 5 -- final sweep: nothing this runner started stays resident.
echo "--- final sweep $(date +%H:%M:%S)"
sweep

# Step 6 -- summary.
echo "SUMMARY $(date +%H:%M:%S)"
echo "  jit off (--no-jit)     : $OUT/jit-off"
echo "  jit on  (--enable-jit) : $OUT/jit-on"
echo "  runner log             : $OUT/runner.log"
[ "$FAILED" -eq 0 ] || { echo "VMLX JIT A/B FAILED -- a column above returned non-zero"; exit 1; }
echo "VMLXJITABDONE $(date +%H:%M:%S)"
exit 0
