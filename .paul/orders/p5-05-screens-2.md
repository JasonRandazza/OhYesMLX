# Order: plan 05-05 — Models, Benchmark, Results (+ summary on every quickbench ending)

Execute `.paul/phases/v5-onboarding/05-05-PLAN.md` (read it whole — it is the order; AC-1..AC-6 are the bar,
Tasks 1-2 in order; AC-6's carry-overs go in Task 2). Visual authority `docs/design/phase5/DESIGN.md` (§4
overrides comps); behaviour `docs/interfaces/v5-app.md`; summary shape: grep `docs/interfaces/v5-quickbench.md`.
Reuse 05-04's `Format` and `Components/*`; follow how `Screens/EnginesView.swift` and the stub scenarios are built.

Files: exactly the plan's `files_modified`. In `ohyesmlx/` only quickbench.py (never measure.py).
No live download or quickbench; the coordinator screenshots and reviews visuals.
Suites: test-venv pytest (baseline 1366); `cd app && OYMLX_DEV_PYTHON=$HOME/.local/share/ohyesmlx/app-dev-venv/bin/python swift test` (baseline 57).
Red-check the Python test and the Export raw-bytes test. Write each new Swift file as a skeleton within ~15 turns; files over ~12 KB in stages.

Report: per AC the test or stub scenario; both suite counts; the list of new scenarios and how to launch them.
