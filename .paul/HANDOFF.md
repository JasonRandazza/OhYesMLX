---
description: "OhYesMLX (OYMLX) session handoff, 2026-11-18: Fable fix plans A–F (05-07..05-12, plus 05-10b) closed on main; start plan G (05-13) with Command Code workers"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-11-18 (plan F closed; plan G next)

> **Update (plan F closed):** F ran on one Command Code worker (`.paul/orders/05-12/t1.md` is the order pattern; ~65 min, $0.43). **Workers are cc-agent again** (Jason, 2026-11-18: Claude's session budget is the scarce one); a Claude subagent only if unavoidable. Next is **plan G (05-13)**: S6-F1..F11 in `.paul/review/fable-5.2/S6-findings.md`, then re-run `scripts/check_bundle.sh dist/OhYesMLX.app`. The plan-F sections below are history.

> Read this first, then `.paul/STATE.md`, then `AGENTS.md`. STATE wins wherever this note and STATE disagree.
> Previous handoff: `.paul/archive/2026-11-16-handoff-plan-c.md`. Jason calls the project **OYMLX**.

## Start here: plan F (05-12), Osaurus pin and restore

The Fable fix order is A→B→C→D→E→F→G, plans 05-07..05-13. 05-10b was inserted after D. A through E are closed and
merged to `main` locally, not pushed. Run F as an ordinary PAUL loop:

1. `/paul:plan`
2. `/paul:audit`, applying its upgrades to the plan
3. `/paul:apply`
4. A two-axis review: two Sonnet reviewers, Standards and Spec, both read-only
5. Fix every finding
6. `/paul:unify`

Jason has authorised going straight from audit to apply.

**F's findings:** S2-F10, S5-F6, S5-F7, S5-F8, S5-F12.
- The fix direction for each is in `.paul/review/fable-5.2/S2-findings.md` and `S5-findings.md`; grep `### F<n> `.
- The red tests are on branch `review/fable-verify`. Copy one with `git checkout review/fable-verify -- tests/test_fable_s<n>_f<k>.py`.
- Run each red test on `main` first. Earlier plans changed seams, for example `port_in_use` became `port_refusal` in 05-10b, and `verify=` is now required by quickbench. Stale tests need a minimal re-seam, listed in the SUMMARY.

Osaurus runs go through `scripts/osaurus-pin.sh` under Jason's standing authorisation (AGENTS.md). F is about that pin and
restore path, so read `docs/runtimes/osaurus.md` before planning.

## How to work (Jason, 2026-11-16, reaffirmed 2026-11-18)

Do not dispatch `cc-agent`. Use Claude Code subagents through the Agent tool, choosing model and effort per task:
- **Sonnet, medium effort:** a bounded Python fix with exact files.
- **Sonnet, high effort:** Swift work or reviews.
- **Opus, high effort:** a design-heavy change, such as the install/detection rework in 05-11 T2.
- **The coordinator itself:** small or wording-sensitive work and all review fixes.

Jason has 4 banked Anthropic resets. Stay efficient anyway.

Every worker prompt carries:
- the plan's ACs;
- the exact files it may touch, and "touch nothing else";
- "do not spawn subagents";
- "start no runtime, model or download";
- "never `git stash`";
- "make the first edit early".

## Traps that cost time

- **Worktrees.** Create them yourself: `git worktree add -b fix/05-12-tN ~/orca/workspaces/OhYesMLX/05-12-tN fix/05-12`.
  - Integrate in the `fix/05-12` worktree, never in the main checkout.
  - Remove all of them at UNIFY.
- **Checking diffs.** Worker diffs need the coordinator's own read.
  - 05-11 T1 passed its tests yet recorded a "Stop now" heard mid-download as a skip.
  - Write a red-checked test for any gap you find: confirm it fails without the fix, then passes with it.
- **`swift test`.** Run it against a branch-local backend venv:
  - Build it with `scripts/dev_backend_venv.sh <scratch>/venv` from the integration worktree, then pass `OYMLX_DEV_PYTHON=<scratch>/venv/bin/python`.
  - `LauncherTests.testEOFBeforeTheLaunchLineIsCouldntStartWithTheStderrTail` flakes more under full-suite load. Re-run it alone and confirm it passes.
- **Screenshots.**
  - Build with `swift build`, then run `.build/debug/OhYesMLX` with `OYMLX_STUB_SCENARIO=<name>`.
  - Get the window id with a small CoreGraphics `swift` script (05-11's was in the session scratchpad and is easy to recreate).
  - Capture with `screencapture -x -o -l <id>`.
  - Toggle appearance through System Events, and restore **dark** at the end.
- **Python one-off edit scripts.** Run them with `python3 -I`. `re.sub` misbehaved once in a worktree cwd without it.
- **pytest skips.** It skips 2 tests in a worktree, because `results/grid` is gitignored. That is expected.

## Still open beyond F

- **Plan G (packaging).** It includes re-running `scripts/check_bundle.sh`, because the packaged backend now gets `--lock-dir`.
- **Live Phase 5 checks, which need Jason's "when":**
  - app-UI download and Stop now;
  - canaries for Osaurus 0.25.33 and vMLX 1.6.84;
  - the S5-F2 constant.
- **Phase 5 close:**
  - clean-account smoke;
  - UAT (`/paul:verify`);
  - `PHASE-5-SUMMARY.md`.
- **From B:** retrying an interrupted evict does not auto-open its confirm sheet. The fix needs `ModelsView.swift`.
