#!/bin/sh
# Hardening validation, 2026-09-23 overnight: the three harness grids (35B, dense, MoE) re-run
# unchanged into fresh directories on the post-Phase-2 harness, so the Phase 1+2 fixes meet real
# runtimes and every row carries the harness sha and end-to-end latency percentiles.
#
# Each grid script is the one that produced the published grid; only its OUT moves. The grids run
# back to back with a cooldown between them. Nothing else may run on this machine meanwhile.
#
#   sh scripts/run_harden_validation.sh > results/harden-2026-09-23/runner.log 2>&1 &
set -u
cd /Users/jrazz/Dev/active/OhYesMLX
PY=/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python
T=results/harden-2026-09-23
mkdir -p "$T"

for g in 35b dense moe; do
  case $g in
    35b)   script=scripts/run_grid_35b.sh ;;
    dense) script=scripts/run_grid.sh ;;
    moe)   script=scripts/run_grid_moe.sh ;;
  esac
  echo "##### GRID $g starting $(date +%H:%M:%S)"
  OUT="$T/grid-$g" sh "$script" > "$T/runner-$g.log" 2>&1
  echo "##### GRID $g exit=$? $(date +%H:%M:%S)"
  $PY -m ohyesmlx.cli grid "$T/grid-$g"/*/ --out "$T/grid-$g/grid.md" > /dev/null \
    || echo "GRID RENDER WARNING $g: $?"
  [ "$g" = moe ] || { echo "  cooldown 300 s"; sleep 300; }
done
echo "HARDENVALIDATIONDONE $(date +%H:%M:%S)"
