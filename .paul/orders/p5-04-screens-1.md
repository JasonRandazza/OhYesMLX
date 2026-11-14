# Order: plan 05-04 — app shell + Your Mac + Engines screens (T5.2, T5.3)

Execute `.paul/phases/v5-onboarding/05-04-PLAN.md` (read it whole — it is the order; AC-1..AC-6 are the bar,
Tasks 1-2 in order). Visual authority: `docs/design/phase5/DESIGN.md` (read whole; its §4 overrides the comps).
Behaviour: `docs/interfaces/v5-app.md`. Comps: `docs/design/phase5/comps.html` — grep for the frame you build
(it is ~50 KB; never read it whole).

Files you may touch: exactly the plan's `files_modified`. Nothing under `ohyesmlx/`, `tests/`, `docs/`.
You may run `swift run` / the built binary with `OYMLX_STUB_SCENARIO=...` to check it starts; you cannot judge
visuals — the coordinator screenshots and reviews. Never start an engine or POST /jobs against a live backend.

Build/test: `cd app && OYMLX_DEV_PYTHON=$HOME/.local/share/ohyesmlx/app-dev-venv/bin/python swift test`
(baseline 52). Write each new Swift file within your first ~15 turns as a skeleton, then fill it; files over
~12 KB in stages.

Report: per AC the test or the scenario name that shows it; swift test count; the two greps from <verification>;
the exact list of stub scenarios and how to launch each.
