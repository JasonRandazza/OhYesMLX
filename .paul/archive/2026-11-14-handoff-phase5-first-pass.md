---
description: "OhYesMLX (OYMLX) session handoff, 2026-11-14: Phase 5 first pass done; Jason's to-do list first, then the Fable 5.2 review (promotion ends 2026-11-16 23:59 PT)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-11-14 (end of the Phase 5 first pass)

> Read this, then `.paul/STATE.md`, then `.paul/review/fable-5.2/PLAN.md`, then `AGENTS.md`. STATE wins on conflict.
> Previous handoff: `.paul/archive/2026-11-13-handoff-phase5-prototype.md`. Jason calls the project **OYMLX**.

## Start here: open the session by walking Jason through his list

Jason asked for this explicitly. **Before any other work**, explain each item below in plain language: what it
is, why it matters, and exactly what to type or click. Then wait for him. Items 1–4 unblock the Fable review and
are time-critical. Items 5–8 can be done any time this week.

**Time-critical. The Fable 5.2 Pro promotion and Jason's Fable reset both expire Tue 2026-11-17 2:59 AM EST.**

Already settled with Jason on 2026-11-14, so do not re-ask: the budget is the current Fable allowance plus **1 Fable
reset**, with **4 full resets** (expiring Dec 10) kept mostly for after the promotion. **Kimi K3.1 Pro is approved** as
the main worker; its bench already passed (18/18, 0 collateral deletions, 2026-11-14), so P0-1 only adds the route. **MiMo v2.6 Pro** builds the dossiers.

1. **Choose the order.** Recommended: Fable review first (it is the only time-limited item). The live Phase 5 checks
   (item 5) go before P0 or after V, never overlapping workers.
2. **Know the four checkpoints** the plan will ask him for during the review: the usage panel's 5-hour % and weekly %
   at the start (ASK 1) and after S1 (ASK 2); triggering the Fable reset when told (ASK 3); and whether to spend one
   full reset if S1–S3 are not done when both allowances are gone (ASK 4).
3. **Stay reachable** Sun 11/15 to Mon 11/16. No Fable section starts after Mon 11:30 PM EST.
4. **Re-add the test-account sudo rule** for the clean-account smoke (05-06 AC-6) whenever convenient:
   `echo 'jrazz ALL=(oymlxtest) NOPASSWD: ALL' | sudo tee /etc/sudoers.d/oymlxtest`, then remove it after the
   run: `sudo rm /etc/sudoers.d/oymlxtest`.

**This week (not time-critical):**

5. **Go-ahead for two live checks on a quiet Mac** (about 15 min; nothing else running): one "Stop now" during a
   quickbench of the smallest catalog model, and one real download and evict through the app. AGENTS.md: a
   measurement starts only when Jason says when.
6. **Release decisions.** The version: the app ships as 0.3.0 because it reads `ohyesmlx.__version__`; bump it for
   v5.0? And whether and when to publish a GitHub Release (outward-facing; nothing has been uploaded).
7. **Open Design housekeeping.** Open the Open Design app and refresh its MCP registration: the Codex config points at
   the 0.24.1 payload, and the app is 0.26.1. Optionally register it for Claude Code too, so the next design pass
   needs no shim.
8. **Small yes/no items.** Two vault decision notes proposed (the `best.repo` misattribution fix; the bundled-tree
   precompile). The README full rewrite is still deferred, and still his call. Impeccable v4.9.0 is available
   (`npx impeccable update`).

## Then: the Fable 5.2 review

Execute `.paul/review/fable-5.2/PLAN.md` (executable as written; the order files are in `orders/`). Opus orchestrates, Fable 5.2 reviews six sections (S1 security, S2
measurement integrity, S3 SwiftUI app, S4 onboarding backend, S5 runtime lifecycle, S6 packaging) as background
subagents. Command Code workers build each section's dossier first and verify every finding afterwards. The plan
explains why there is no single massive pass and why Fable does not orchestrate.

## Where things stand

v5.0 Phase 5 first pass is built, reviewed in two waves, and committed on `main` (05-01 `93d374c` … 05-06
`101df7c`). 1370 pytest and 81 swift tests pass. `scripts/build_app.sh` → `dist/OhYesMLX.app`, a zip and an SBOM;
`scripts/check_bundle.sh` passes 9/9. Threat-model §10 now carries a status table: everything is met except
**P5-11** (the client cannot offer "Re-download", because `Pick.downloaded` is a bool). Still open for Phase 5:
the clean-account smoke, the live checks, UAT (`/paul:verify`), P5-11, and `PHASE-5-SUMMARY.md`.

## How this project's sessions work (keep doing it)

- Command Code does the implementation via `.paul/orders/dispatch.sh` (cached PREAMBLE), with a 5-minute progress
  Monitor on each dispatch. Reviewers get the diff as a file (`.paul/review/<date>-…/diff.patch`, gitignored).
- **A worker's or reviewer's report is not evidence.** Phase 5's coordinator checks caught a measured number
  attributed to the wrong model, stage-B rows collapsing, the signed bundle being written to at runtime, and three
  defects in the bundle check script itself.
- UI changes: screenshot the `OYMLX_STUB_SCENARIO` states in light and dark. Toggling the system appearance changes
  Jason's Mac, so restore it (dark).
