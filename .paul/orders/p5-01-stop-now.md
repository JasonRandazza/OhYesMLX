# Order: plan 05-01 — "Stop now" mid-cell abort + low_disk payload numbers

Execute `.paul/phases/v5-onboarding/05-01-PLAN.md` (read it whole — it is the order; its acceptance criteria
AC-1..AC-7 are the acceptance bar, Tasks 1-3 in order). The spec it implements is
`docs/interfaces/v5-app.md`, section "Backend addition: Stop now".

Files you may touch: exactly the plan's `files_modified` list. Touch nothing else — in particular not `app/`,
which another worker is building in parallel in this same tree, and not `ohyesmlx/measure.py`.

Suite: `/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python -m pytest -q` (baseline 1329 passed).
Red-check every new test. No live run: fakes only.

Report: per AC, the test(s) that prove it; the final suite count; whether `_winner` needed a change; anything
in the plan you found contradictory (BLOCKED is a good outcome if the plan is wrong).
