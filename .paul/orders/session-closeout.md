# PAUL Session Closeout Protocol

GOAL: Perform a clean session boundary closeout after completing a phase, plan, or major milestone, updating state stores, committing durable artifacts, and preparing for a zero-token session reset.

PRE-REQUISITES:
1. All planned work for the active plan is completed.
2. The deliverable research document is written and verified in `docs/research/`.
3. The test suite passes green (`verify-venv/bin/python -m pytest -q`).

CLOSEOUT STEPS:
1. Verify Test Suite & Git Status:
   - Run: `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q`
   - Confirm 495 tests pass.
   - Inspect `git status` to ensure only intended files were touched.

2. Update .paul/STATE.md:
   - Increment progress and update Current Position (`Milestone`, `Phase`, `Plan`, `Status`, `Last activity`).
   - Append new durable Decisions to the Decisions table.
   - Update `Session Continuity` with stopping point and next action.

3. Update .paul/ROADMAP.md:
   - Mark completed plan as `[x] <plan_id>: <title> — **Complete <date>** (<research_doc>)`.
   - Mark next plan as `[ ] <plan_id>: <title> — *Next*`.

4. Archive and Rewrite .paul/HANDOFF.md:
   - Copy previous handoff to `.paul/archive/$(date +%Y-%m-%d)-handoff-<tag>.md`.
   - Rewrite `.paul/HANDOFF.md` fresh (<60 lines).
   - Detail: where the project is, active plan & immediate objective, active gates, standing invariants.

5. Reconcile Deep Wiki:
   - Update `10 Wiki/Projects/OhYesMLX/OhYesMLX.md` (frontmatter `updated`, `next_step`, `confidence_basis`, append finding to Published Findings, update roadmap).
   - Run validator: `python3 "00 System/Automation/validate_vault.py" "/Users/jrazz/Documents/ObsidianNotes"`.
   - Never commit or push the vault.

6. Port & Process Sweep:
   - Confirm ports 8000, 1337, 8080, 8081, 8100 are free.
   - Confirm no lingering `vmlx` or Osaurus instances (`^/Applications/osaurus.app/Contents/MacOS/osaurus`).

7. Commit & Reset Signal:
   - Stage and commit project changes.
   - Notify user that closeout is complete and recommend clearing conversation context (`/clear` or new chat thread) before starting the next plan.
