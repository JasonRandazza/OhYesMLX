#!/bin/sh
# Usage: run_fable.sh S<n>  — one Fable 5.2 section, headless, read+write-findings only (PLAN.md amendment).
set -u
cd "$HOME/Dev/active/OhYesMLX" || exit 1
R=.paul/review/fable-5.2; s=$1
P="$(cat $R/orders/_fable-brief.txt)

SECTION: $s. Dossier: $R/dossier-$s.md. Findings file: $R/$s-findings.md. W1 sweep (for context only): $R/W1-sweep.md"
claude -p --model claude-fable-5-2 --allowedTools Read Grep Glob Write --output-format json "$P" > $R/orders/fable-$s.json 2> $R/orders/fable-$s.err
echo "exit=$?"
python3 -c "
import json
t=open('$R/orders/fable-$s.json').read(); d=json.loads(t[t.index('{'):])
print('result:',d.get('result'))
for k,v in (d.get('modelUsage') or {}).items(): print(k, 'out',v.get('outputTokens'),'cacheRd',v.get('cacheReadInputTokens'),'usd',round(v.get('costUSD',0),2))
print('turns',d.get('num_turns'),'secs',d.get('duration_ms',0)//1000)"
ls -la $R/$s-findings.md
