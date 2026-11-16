#!/bin/bash
# Usage: run_verify.sh <parallel> S1-F1 S1-F2 ...  — DeepSeek verifiers in the fable-verify worktree (PLAN.md amendment).
set -u
M=$HOME/Dev/active/OhYesMLX; R=$M/.paul/review/fable-5.2; W=$HOME/orca/workspaces/OhYesMLX/fable-verify
par=$1; shift; mkdir -p $R/orders/verify $W/.paul/review/fable-5.2/verify
one() {
  id=$1; s=${id%-*}; k=${id#*-}
  o=$R/orders/verify/$id.md; log=$R/orders/verify/$id.log
  { cat $R/orders/_verify-brief.md; echo " $id"; echo
    awk -v h="### $k —" 'index($0,h)==1{f=1;print;next} f&&/^### F/{exit} f&&/^Coverage/{exit} f' $R/$s-findings.md; } > $o
  (cd $W && CC_ROUTE=deepseek CC_AGENT_MAX_TURNS=120 $M/.paul/orders/dispatch.sh implement $o $log)
  v=$(grep -h "^VERDICT:" $W/.paul/review/fable-5.2/verify/$id.md 2>/dev/null | tail -1)
  echo "$id ${v:-NO-VERDICT}"
}
export -f one; export M R W
printf '%s\n' "$@" | xargs -P "$par" -I{} bash -c 'one {}'
echo QUEUE-DONE
