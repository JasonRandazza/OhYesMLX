#!/bin/bash
# Usage: run_verify_batch.sh <name> S1-F5 S1-F6 ...  — one DeepSeek run verifies several Low findings (cost cut, 2026-11-15).
set -u
M=$HOME/Dev/active/OhYesMLX; R=$M/.paul/review/fable-5.2; W=$HOME/orca/workspaces/OhYesMLX/fable-verify
name=$1; shift; o=$R/orders/verify/$name.md; log=$R/orders/verify/$name.log
{ cat $R/orders/_verify-brief.md; echo " (BATCH) $*"
  echo
  echo "BATCH RULE: verify each finding below separately, one after another, applying the method above to each and writing"
  echo "one report per finding (verify/<FINDING-ID>.md, each ending in its own VERDICT and SEVERITY-CHECK lines) and one test"
  echo "file per finding. These are Low severity: prefer reading the code path and citing it when a test would need more"
  echo "than about 40 lines. Do not spawn subagents. If tests/test_fable_<id>.py already exists (a killed earlier run), run and reuse it rather than rewriting it."
  for id in "$@"; do s=${id%-*}; k=${id#*-}; echo; echo "=== FINDING-ID: $id ==="
    awk -v h="### $k —" 'index($0,h)==1{f=1;print;next} f&&/^### F/{exit} f&&/^Coverage/{exit} f' $R/$s-findings.md; done; } > $o
(cd $W && CC_ROUTE=deepseek CC_AGENT_MAX_TURNS=200 $M/.paul/orders/dispatch.sh implement $o $log)
for id in "$@"; do v=$(grep -h "^VERDICT:" $W/.paul/review/fable-5.2/verify/$id.md 2>/dev/null | tail -1); echo "$id ${v:-NO-VERDICT}"; done
