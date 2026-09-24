#!/bin/sh
# The Phase 4 night: the four studies of v3.1 Phase 4 in the order of the handoff table, one after
# the other, each with its own OUT and each logging its own start and end time.
#
#   kvquant    scripts/run_sweep_kvquant.sh    OUT_KVQUANT   results/sweep-kvquant
#   mtp        scripts/run_sweep_mtp.sh        OUT_MTP       results/sweep-mtp
#   streaming  scripts/run_sweep_streaming.sh  OUT_STREAMING results/sweep-streaming
#   multiturn  scripts/run_multiturn.sh        OUT_MULTITURN results/multiturn
#
# The third 35B replicate is NOT here: it is its own quiet night (AGENTS.md -- one model resident,
# nothing else on the machine), and the handoff keeps it separate.
#
# Each study's runner owns its own runner.log inside its OUT; this wrapper's log carries only the
# four start/end pairs, so a study that died shows up as an exit code beside the times. Every OUT
# is overridable, and so is the wrapper's: OUT_KVQUANT=... sh scripts/run_phase4_night.sh.
#
# DRY=1 passes straight through: the four scripts print their `ohyesmlx.cli run` commands and
# nothing is started, no port is swept, no directory is written.
set -u
cd /Users/jrazz/Dev/active/OhYesMLX
DRY=${DRY:-0}
OUT_KVQUANT=${OUT_KVQUANT:-results/sweep-kvquant}
OUT_MTP=${OUT_MTP:-results/sweep-mtp}
OUT_STREAMING=${OUT_STREAMING:-results/sweep-streaming}
OUT_MULTITURN=${OUT_MULTITURN:-results/multiturn}

if [ "$DRY" = 1 ]; then
  echo "DRY=1: the four studies print their run commands; nothing is started"
else
  mkdir -p results
  # The wrapper owns its log, for the reason run_sweep_kvquant.sh states once: an exec redirect
  # cannot be unbound from the command the way `cmd & > file` can.
  exec > results/phase4-night.log 2>&1
fi

night() {  # $1 = study, $2 = its OUT, $3 = its script
  echo "=== phase4 $1 starting $(date +%H:%M:%S) OUT=$2"
  OUT="$2" DRY="$DRY" sh "$3"
  echo "=== phase4 $1 exit=$? $(date +%H:%M:%S)"
}

night kvquant "$OUT_KVQUANT" scripts/run_sweep_kvquant.sh
night mtp "$OUT_MTP" scripts/run_sweep_mtp.sh
night streaming "$OUT_STREAMING" scripts/run_sweep_streaming.sh
night multiturn "$OUT_MULTITURN" scripts/run_multiturn.sh

echo "PHASE4NIGHTDONE $(date +%H:%M:%S)"
