---
description: "OhYesMLX (OYMLX) session handoff, 2026-11-13: v5.0 Phase 4.5 complete; Phase 5 prototype gate built, waiting on Jason's answers before PLAN"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-11-13

> Read this, then `.paul/STATE.md` (Current Position, Session Continuity), then
> `.paul/phases/v5-onboarding/PHASE-4.5-SUMMARY.md` (Carried forward), then the Phase 5 section of
> `.paul/phases/v5-onboarding/PLAN.md`, then `AGENTS.md`. STATE wins on conflict.
> Previous handoff: `.paul/archive/2026-11-03-handoff-phase-4-complete.md`. Jason calls the project **OYMLX**.

## Where things stand

v5.0 Phases 0–4.5 are complete on `main` and the tree is clean. 1,329 tests pass
(`/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python -m pytest -q`). Phase 4.5 ended with a
clean-account smoke run as standard user `oymlxtest`: 21/21 after two fixes, optiq installing without
pygame and the app engines starting from their own bundles. Jason removed `/etc/sudoers.d/oymlxtest`
on 2026-11-13, so a new clean-account run needs that rule re-added. The rule is in
`045-03-SUMMARY.md` Deviations 5, and `scripts/smoke_clean_account.sh` is the harness.

## The one thing to do next: Phase 5

1. **Prototype gate (built).** https://claude.ai/code/artifact/0f1614ae-9053-4c90-b31e-621393d56128.
   Its source is on branch `prototype/phase5-flows`, which never merges. Jason answers the seven open
   questions at the bottom of the page:
   - while a job holds the one slot, are other actions greyed out or left live with a 409;
   - what the next launch says about an interrupted job;
   - what to show on a cancel in the middle of a cell;
   - which screen owns `low_disk`;
   - whether a guided install is verified again later;
   - whether the unsupported-Mac gate is absolute;
   - whether Results mentions `not_evicted`.
2. With those answers, run `/paul:plan` for Phase 5 (T5.1–T5.6, PLAN.md). The constraints:
   - threat-model §10 (P5-1..P5-12) binds the packaging;
   - D6 bundles python-build-standalone, so the bundled interpreter must re-verify P5-3 and P5-4
     (both were checked against Homebrew Python only);
   - **there is no Apple Developer account**, so T5.6 is the unsigned `.app` zip (D7) and
     notarization stays a gated step;
   - the backend's PATH is launchd's (P5-9).
3. Each ticket follows PAUL: `/paul:audit` on the plan, then APPLY through Command Code workers,
   then a Standards + Spec code review, then `/paul:unify`.

## How this session worked (keep doing it)

- **Workers.** Command Code does all implementation through `.paul/orders/dispatch.sh`. Every
  dispatch gets a five-minute progress Monitor, and a backgrounded dispatch needs a Bash timeout of
  7200000.
- **Worker instructions.** The preamble (`.paul/orders/PREAMBLE.md`) now says to use graphify first,
  to write a file within ~15 turns, and to write any file over ~12 KB in stages.
- **Read-only reviewers.** The `review` and `explain` profiles cannot run a shell, so give them the
  diff as a file.
- **Docs layout.** `docs/interfaces/` holds the shapes, one file per subject; `docs/interfaces.md`
  is now an index. `.paul/DECISIONS.md` is the full decision log, and STATE keeps only recent rows.

## Open, not urgent

- `/engines` reports vMLX installed for an account that cannot run its bundle. This affects
  multi-user Macs only; it is deferred, and the full list is in PHASE-4.5-SUMMARY.
- Paused milestones: v3.1's 0.3.1 bump, and v4.0 MTPLX (`mtplx-wip`).
- README rewrite (STATE Deferred Issues).
