# Order: plan 05-02 — the SwiftUI app skeleton (T5.1)

Execute `.paul/phases/v5-onboarding/05-02-PLAN.md` (read it whole — it is the order; AC-1..AC-6 including
AC-2b/AC-2c are the acceptance bar, Tasks 1-3 in order). The spec is `docs/interfaces/v5-app.md` (read whole,
it is short). JSON shapes: grep `docs/interfaces/v5-onboarding.md` and `v5-quickbench.md`. Fixtures already
exist in `app/Tests/OhYesMLXKitTests/Fixtures/` — use them, do not re-capture.

Files you may touch: exactly the plan's `files_modified` list. Touch nothing under `ohyesmlx/` or `tests/`
(another worker is changing the Python backend in this same tree) and nothing under `docs/`.
This order overrides the preamble's "do not start a server" for ONE thing only: you may start the localhost
API `ohyesmlx app` (via the dev venv) in the live test and `swift run`. It starts no engine and loads no model.
Never start an engine, never call POST /jobs against the live backend.

Build/test: `cd app && swift build && swift test`. Make the dev venv with your `scripts/dev_backend_venv.sh`.
Swift files over ~12 KB: write in stages. Write Package.swift and Models.swift within your first ~15 turns.

Report: per AC the test(s) proving it; `swift test` count; the P5-1 grep output; what you did not verify.
