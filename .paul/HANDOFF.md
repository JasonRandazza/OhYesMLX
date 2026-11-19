---
description: "OhYesMLX (OYMLX) session handoff, 2026-11-19: Phase 5 closed; start Phase 5.5 (deferred cleanup) with Command Code workers"
type: Handoff
about: "OhYesMLX"
---

# Handoff, 2026-11-19 (Phase 5 closed; Phase 5.5 next)

> Read this first, then `.paul/STATE.md`, then `AGENTS.md`. Where this note and STATE disagree, STATE wins.
> Previous handoff: `.paul/archive/2026-11-18-handoff-fable-fixes.md`. Jason calls the project **OYMLX**.

## Where things stand

- **v5.0 Phases 0–5 are complete.** Phase 5 is summarised in `.paul/phases/v5-onboarding/PHASE-5-SUMMARY.md`, and its UAT in `05-UAT.md`.
- **Repository:** everything is merged to `main` locally and not pushed. There are no worktrees and no running workers. The untracked `settings.json` in the repo root is Jason's; leave it alone.
- **Release artifact:** `dist/OhYesMLX-0.3.0.dmg` plus `.dmg.sha256` and the SBOM. It is ad-hoc signed and not notarized, because there is no Apple Developer account. `dist/` is gitignored, so rebuild it with `scripts/build_app.sh` and check it with `scripts/check_bundle.sh dist/OhYesMLX.app`.
- **Gates at close:** pytest 1652 (`/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python -m pytest -q`), swift test 123, `check_bundle` all PASS.
- **Engine baselines** (`ohyesmlx/engines-tested.json`) were recorded on 2026-11-19 for Osaurus 0.25.33 and vMLX 1.6.84.

## Start here: Phase 5.5, deferred cleanup

ROADMAP "Phase 5.5" lists 10 items, each with its origin. Run it as an ordinary PAUL loop:
1. `/paul:plan`
2. `/paul:audit`, applying its upgrades
3. Apply
4. Review on two axes, Standards and Spec
5. Unify

Group the items into two or three plans by surface:
- **App:** items 2, 3 and 8.
- **Backend:** items 4, 6 and 7.
- **Scripts and docs:** items 1, 5 and 10.
- Item 9, vMLX TTFT and cold load, needs a quiet-machine measurement and Jason's "when". See the measurement rules below.

Phase 5.6 (UI aesthetics) waits on Jason's list. Do not start it without that list.

## How to work (Jason, 2026-11-18)

- **Workers are Command Code**, dispatched with `.paul/orders/dispatch.sh implement <order.md> <log>` and `CC_AGENT_MAX_TURNS=300`. Use a Claude subagent only when unavoidable, because the Claude session budget is the scarce resource.
  - Order pattern: `.paul/orders/05-13/w1.md`.
  - Two parallel workers at most.
  - Use one background `until`-loop to wait for each worker, plus one 15-minute stall check.
- **The coordinator owns verification:**
  - Read every diff.
  - Run both test suites.
  - Fix review findings itself.
  - Write a red-checked test for any gap the review finds.
- **Worktrees:** create them yourself under `~/orca/workspaces/OhYesMLX/<plan>-<task>` and integrate them in a `fix/<plan>` worktree. Never `git stash`.
- **Swift tests:** run `swift test` against a branch-local venv built with `scripts/dev_backend_venv.sh <scratch>/venv`. `LauncherTests.testEOFBefore…StderrTail` is flaky under load; re-run it alone.
- **Screenshots:**
  - Build with `swift build`, then run `.build/debug/OhYesMLX` with `OYMLX_STUB_SCENARIO=<name>`.
  - Get the window id with a small CoreGraphics script.
  - Capture with `screencapture -x -o -l <id>`.
  - Toggle light/dark through System Events, and restore **dark** at the end.
  - Captures come out black while the display sleeps.
- **Python edit one-offs:** run them with `python3 -I`.

## Measurement rules learned at the Phase 5 close

- **Ask Jason before any measured run**, and make sure the Mac is quiet first. These cost real time on 2026-11-18/19:
  - Spotlight (`spotlightknowledged`, about 300% CPU after builds)
  - Wallspace (a live wallpaper that decodes video)
  - Sidecar to the iPad (`avconferenced` plus the video encoder)
  - Chrome and Obsidian
- **Gate a run on load** with `until [ "$(sysctl -n vm.loadavg | awk '{print ($2<3)}')" = 1 ]`. The harness itself flags load above 4.0 as noisy.
- **Canaries:** run `ENGINES=a,b scripts/run_canary.sh`. Its verdicts are written to `results/canary/runner-<stamp>.log`; redirecting stdout loses nothing. Snapshot `~/.osaurus/config` first and run an independent `cmp` after every pinned run.
- **Discarding a run** must name a defect in its conditions, never the number it produced. A run discarded on a guess was restored on 2026-11-18.

## Closing a plan (unchanged)

1. The coordinator runs pytest, plus swift test for app changes, plus screenshots for UI changes, plus `build_app.sh` and `check_bundle.sh` for packaging changes.
2. Write the SUMMARY.
3. Merge `fix/<plan>` into `main` locally.
4. Run `graphify update .`.
5. Run `project-state set --next … --by "Claude Code"`.
