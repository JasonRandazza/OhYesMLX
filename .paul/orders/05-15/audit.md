
# Order: cold-load ordering audit (Fable S5-F2 follow-up)

**Work in the main checkout, `/Users/jrazz/Dev/active/OhYesMLX`.** You create exactly ONE new file: `docs/research/2026-11-19-cold-load-ordering-audit.md`. Touch nothing else. Run no runtime, model, measurement or download.

## Background
Before plan 05-07 (merged 2026-11-16), `cold_load_s` included the engine's version probe and one `lsof` call. Fable S5-F2 is that finding; see `### F2` in `.paul/review/fable-5.2/S5-findings.md`. On 2026-11-19 the overstatement was measured per engine. The figures give the warm median, and in brackets the cold first call:

| Engine | Overstatement |
|---|---|
| mlx-lm | 1.01 s (1.83 s) |
| OptiQ | 1.03 s (1.76 s) |
| Osaurus | 0.31 s |
| oMLX | 0.11 s (0.15 s) |
| vMLX | 0.07 s |

Each figure is the version probe plus one 0.068 s `lsof`. Source: `.paul/phases/v5-onboarding/05-14-SUMMARY.md`.

## Task
1. Find every **published** cold-load comparison across engines. Search `docs/research/*.md`, `README.md` and `docs/*.md` for `cold_load`, "cold load" and "load time". Publication means a written doc, not raw `results/`.
2. For each one:
   - Note the date, the engines and the cold-load figures.
   - Check whether the run predates 05-07. Use the run date, or the harness revision in the run header where `results/<dir>/results.jsonl` exists; read line 1 only.
3. For every adjacent pair in a published ordering, subtract each engine's overstatement at both bounds, warm and cold. Report whether the ordering or any stated gap/ratio changes. Recompute from `results.jsonl` when a doc's numbers trace to a run directory and the run is present; say when it is not.
4. Write the research doc:
   - A table of each claim with: source file:line, the old ordering, the corrected range, and whether it flips (Yes / No / Only at cold bound).
   - A short verdict: which sentences in which docs would need a correction note.
   - Do NOT edit those docs; list them.

## Rules
- AGENTS.md: a negative claim needs evidence.
- Never git stash.
- Commit only the new file, with a message ending in the line `Co-Authored-By: Command Code <noreply@commandcode.ai>`.
- Report in 15 lines or fewer: what flips, if anything.
