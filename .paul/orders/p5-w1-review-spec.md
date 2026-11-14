# Order: Spec review of Phase 5 wave 1 (read-only)

Diff: `.paul/review/2026-11-14-phase5-w1/diff.patch` (git diff 99d2a55...HEAD; commits 93d374c 05-01, 004171c 05-02). Read it in ranges; ~5,500 lines.
Specs: `.paul/phases/v5-onboarding/05-01-PLAN.md` (AC-1..AC-7), `.paul/phases/v5-onboarding/05-02-PLAN.md` (AC-1..AC-6 incl. 2b/2c), `docs/interfaces/v5-app.md` (the launcher, client, app model, Jason's Q1-Q7).

Report: (a) requirements missing or partial; (b) behaviour not asked for (scope creep); (c) requirements that look implemented but where the implementation looks wrong (races, wrong state transitions, a test that cannot fail). Quote the spec line for each and give file:line. Under 500 words. You cannot run a shell; do not try.
