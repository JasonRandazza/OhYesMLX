---
description: "OhYesMLX (OYMLX) session handoff, 2026-11-14: v5.0 Phase 5 built and reviewed; clean-account smoke, live checks and UAT remain"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-11-14

> Read this, then `.paul/STATE.md` (Current Position, Session Continuity), then
> `.paul/phases/v5-onboarding/05-06-SUMMARY.md`, then `AGENTS.md`. STATE wins on conflict.
> Previous handoff: `.paul/archive/2026-11-13-handoff-phase5-prototype.md`. Jason calls the project **OYMLX**.

## Where things stand

Phase 5 (the SwiftUI app) is built on `main`. Jason answered the prototype's 7 questions on 2026-11-13, and they are
pinned in `docs/interfaces/v5-app.md`. Six plans (05-01 to 05-06) were each audited, applied by Command Code, verified
by the coordinator and reviewed on two axes in two waves. 1370 pytest and 81 swift tests pass. The design authority
is `docs/design/phase5/DESIGN.md` (Open Design comps plus an impeccable critique), and screenshots of every state are
under `docs/design/phase5/shots-05-0{4,5}/`.

Build: `scripts/build_app.sh` writes `dist/OhYesMLX.app`, `dist/OhYesMLX-0.3.0.zip` and the SBOM. Check:
`scripts/check_bundle.sh dist/OhYesMLX.app` passes 9/9. Dev: `scripts/dev_backend_venv.sh`, then
`OYMLX_DEV_PYTHON=… swift run OhYesMLX`, or `OYMLX_STUB_SCENARIO=<name>` (DEBUG) for any screen state without a backend.

## The next steps, in order

1. **Clean-account smoke (05-06 AC-6).** Jason re-adds `/etc/sudoers.d/oymlxtest`
   (`jrazz ALL=(oymlxtest) NOPASSWD: ALL`), then removes it afterwards. The coordinator runs the built bundle's
   backend as `oymlxtest`, using the launcher's exact argv and env, with `scripts/smoke_clean_account.sh`.
2. **Live checks, with Jason's go-ahead** (measurement rule: a quiet machine). Run one "Stop now" on a quickbench of
   the smallest catalog model, and one real download and evict through the app.
3. `/paul:verify` Phase 5 UAT, then `PHASE-5-SUMMARY.md`, then close the milestone.

## Jason's calls

- The release version. The bundle reads `ohyesmlx.__version__`, which is 0.3.0.
- Whether, and when, to publish a GitHub Release. This is outward-facing; nothing has been uploaded.
- Open Design's MCP registration is stale (it points at 0.24.1; the app is 0.26.1). Refresh it in the app.

## How this session worked (keep doing it)

- Command Code does the implementation through `.paul/orders/dispatch.sh`, with a 5-minute progress Monitor on each
  dispatch. Reviewers (`review` profile) get the diff as a file under `.paul/review/<date>-…/` (gitignored `diff.patch`).
- **A worker's report is not evidence.** This session, coordinator verification found:
  - a measured number attributed to the wrong model (`best.repo`);
  - stage-B results collapsing in the client;
  - the signed bundle being written to at runtime;
  - three defects in the bundle check script itself.
- Screenshots of the stub scenarios need the system appearance toggled. Restore it to what you found (dark).
