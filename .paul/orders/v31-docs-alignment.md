# Order: documentation alignment audit against the code (v3.1)
Goal: every current-state claim in the docs matches the code at HEAD. Evidence is the code and the
installed runtimes' source, not other docs.
Files you may touch: README.md, docs/interfaces.md, docs/runtimes/*.md, docs/research/*.md (see rule 3),
and docstrings/comments ONLY in ohyesmlx/*.py (no code changes -- a code defect goes in your report).
Do NOT touch AGENTS.md, CLAUDE.md, .paul/**, scripts/, tests/.
1. README.md and docs/interfaces.md: walk every CLI flag, subcommand, pin, header field, row key, render
   state and refusal against ohyesmlx/cli.py, report.py, measure.py, runtimes.py. Known stale: interfaces.md
   describes optiq_mtp_refusal without the new sidecar shape condition (commit 773b739); check what
   f998dcd (N/A entries, leaderboard refusals, concurrent TTFT sentence) and ac90077 (vMLX env pin) changed.
2. docs/runtimes/*.md: citations of OhYesMLX code (ohyesmlx/*.py:line) must resolve at HEAD; the
   runtime-source citations were re-walked today for optiq.md and vmlx.md -- spot-check, do not redo.
   Known stale: runtimes.py ~1836-1838 docstring cites optiq cli.py:2571/:3030/:2332 (now 2768/3310/2500).
3. docs/research/ papers are dated records: never rewrite a finding. Where later work answered an open
   question or changed a mechanism the paper describes as current (e.g. 2026-09-25-mtp-depth-sweep.md
   Open questions 5-6 are now addressed by 773b739; KV/streaming papers describe N/A cells as `—`),
   append a short dated "Update 2026-09-25" note pointing at the commit. Only for the 2026-09-2x papers.
4. Report every AGENTS.md or .paul/ claim you find contradicted by the code -- report only, no edit.
Acceptance: a list of every change (file, old -> new, evidence). Suite green
(/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q). No git, no servers.
Report DONE or BLOCKED.
