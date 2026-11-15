# Order: W1 sweep for the Fable 5.2 review (P0)

Write one file, `.paul/review/fable-5.2/W1-sweep.md`; touch nothing else.
Part A, interface drift: for each shape and rule in `docs/interfaces/v5-onboarding.md`, `v5-quickbench.md`,
`v5-hardening.md`, `v5-app.md` and `measurement-core.md`, check the code that produces or consumes it (via
graphify) and list every mismatch as `doc path:line vs code path:line — what differs`. Say "matches" per shape.
Part B, tests that cannot fail: in `tests/` and `app/Tests/`, list tests whose assertion only echoes a fake's own
return, re-implements the logic under test, or would pass if the code under test were deleted. Each: `path::name —
why it cannot fail`. Sample at least the 200 most recently changed tests (`git log --since=2026-10-29 --name-only`).
Read-only otherwise; do not run the suites; quote minimally.
