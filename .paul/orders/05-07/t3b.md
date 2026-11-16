# Order: plan 05-07 Task 3 — row status, sampler error, join guard (S2-F3, S2-F4, S2-F6, S2-F7, S2-F8, S2-F9)

Read `.paul/phases/v5-onboarding/05-07-PLAN.md`: AC-7..AC-12 (including the audit-added notes), Task 3, <boundaries>.
Finding details: `.paul/review/fable-5.2/S2-findings.md` (grep "### F3 ", F4, F6, F7, F8, F9). Contract:
`docs/interfaces/sweep-pins.md` lines 174-203 (lost-visit rule).

Working tree: this worktree (branch fix/05-07-t3, already holds Tasks 2/4/5). Commit there; do not push or merge.

Step 1: `git checkout review/fable-verify -- tests/test_fable_s2_f3.py tests/test_fable_s2_f4.py tests/test_fable_s2_f6.py tests/test_fable_s2_f7.py tests/test_fable_s2_f8.py tests/test_fable_s2_f9.py`
Run them; confirm red. Rules for those files: never weaken a test that asserts the fix. If a test in them pins the
OLD defect as a control and must flip, or a test is self-contradictory (e.g. compares a split PATH entry to a joined
string), you may make the minimal correction — list each one with its reason in the report. Do not reason about a
suspected contradiction for more than 3 turns: fix it minimally and report, or report BLOCKED with the failure text.

Step 2, the fixes (one definition each; any new constant lives in one place):
- S2-F3 (measure.py ~:860-865): compare every started visit's `handle.version` with `result.runtime_version`; a
  mismatch, or an unknown version ("unknown: …") beside a known one, sets the row FAIL with both versions in the reason.
- S2-F4 (sample.py ~:262-302, report.py ~:865, measure.py ~:880): a memory dict with "error" publishes peak_mb None,
  rendered "—" with the error as the note.
- S2-F6 (report.py ~:1102-1106, measure.py ~:1236-1245): judge coherence over the responses that came back before
  reporting transport failures; `_floor_verdicts` shows coherence "not reached" for a transport/start-failure reason.
- S2-F7 (measure.py ~:654-668, :843-852): a lost later visit records `lost_visit_reason` like a lost first visit, and
  `_set_status` judges the samples held (still FAIL when they are short). Update sweep-pins.md :174-203 to state the
  rule and why, at the definition. Stored rows are not re-judged.
- S2-F8 (measure.py ~:1000-1112): end the visit after two consecutive request timeouts; row FAIL with that reason.
- S2-F9 (report.py ~:1499-1502 `_check_harness`): handle a mixed set (some headers stamped, some not) as the red test
  asserts; all-absent behaves as before.

Files: ohyesmlx/measure.py, ohyesmlx/sample.py, ohyesmlx/report.py, docs/interfaces/sweep-pins.md, the six red tests,
and tests/test_measure.py / test_report.py / test_sample.py only where an existing assertion states the old defect
(list each). Touch nothing else. Do not spawn subagents. No server, measurement or download.
Pace: first source edit within 10 turns.

Suite: `/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python -m pytest -q` green (this branch's baseline: 1380 passed).

Report: per AC the command and output; every test edited and why; diff stat; what you did not verify.

## Restart note
A previous worker copied the six red tests (already staged here) and confirmed them red (8 failed, 5 passed), then spent 15 minutes reading without editing. Do not re-confirm red. Make your first source edit within 5 turns, one finding at a time, running that finding's red test after each.
