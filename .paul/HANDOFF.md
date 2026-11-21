---
description: "OhYesMLX (OYMLX) session handoff, 2026-11-21: Phase 5.5 closed; Phase 5.6 (UI aesthetics) waits on Jason's list"
type: Handoff
about: "OhYesMLX"
---

# Handoff, 2026-11-21 (Phase 5.5 closed; Phase 5.6 next)

> Read this first, then `.paul/STATE.md`, then `AGENTS.md`. Where this note and STATE disagree, STATE wins.
> Previous handoff: `.paul/archive/2026-11-19-handoff-phase-5.5-start.md`. Jason calls the project **OYMLX**.

## Where things stand

- **v5.0 Phases 0–5.5 are complete.** Phase 5.5 is summarised in `.paul/phases/v5-onboarding/PHASE-5.5-SUMMARY.md`. Its plans are 055-01 to 055-04, each with a SUMMARY. The research from the measurement days is:
  - `docs/research/2026-11-20-vmlx-1.6.84-quiet-canaries.md`
  - `docs/research/2026-11-20-canaries-and-35b-r4.md`
- **Repository:** everything is merged to `main` locally and not pushed. There are no worktrees and no running workers. The untracked `settings.json` in the repo root is Jason's; leave it alone.
- **Canary baselines:** all five engines carry median-of-3 baselines, recorded 2026-11-21 with `RECORD="--record --repeat 3" scripts/run_canary.sh`. Each manifest entry keeps its three readings as `runs`.
- **Release:** `dist/OhYesMLX-0.3.0.dmg` predates 055-02's app changes. Rebuild with `scripts/build_app.sh`, then `scripts/check_bundle.sh dist/OhYesMLX.app`, before shipping them.

## Next: Phase 5.6, UI aesthetics

It waits on Jason's list. Do not start it without that list. When the list arrives:
1. Plan the phase.
2. Take light and dark screenshots of every screen it changes. `OYMLX_STUB_SCENARIO` lists the states; `models-external-cache` was added in 055-02.

## Before any measurement

- **Fix, or route around, the orphaned `mcp-server-cloudflare` processes.**
  - **The cause:** the claude-mem worker (`bun …/claude-mem/…/worker-service.cjs --daemon`) starts a Claude Haiku session about every 15 minutes. That session launches the Cloudflare MCP server, which is orphaned at 100% CPU when the session ends.
  - **The cost:** four of them voided the first baseline attempt on 2026-11-21.
  - **The workaround used:** kill the orphans, stop the worker for the duration of the run, and restart it afterwards with its own command line.
  - **The real fix** is in Jason's Claude configuration.
- **The rest of the quiet-machine checklist** (Spotlight, Wallspace, Sidecar, Chrome, Obsidian) and the load gate are unchanged. They are in `.paul/archive/2026-11-19-handoff-phase-5.5-start.md`, under "Measurement rules".
- **Background tool waits** time out at 1–2 hours. Run long measurements detached (`nohup`), wait on them with a re-armable `until grep` loop, and never put a measurement inside the tool's background slot.
- **`scripts/sweep.sh`** (055-03) has now run live three times, all clean.

## How to work (unchanged)

- **Workers are Command Code:** `.paul/orders/dispatch.sh implement <order.md> <log>` with `CC_AGENT_MAX_TURNS=300`. Use Claude subagents only when unavoidable. Run two parallel workers at most. Create worktrees under `~/orca/workspaces/OhYesMLX/<plan>[-wN]`.
- **The coordinator owns verification:**
  - read every diff;
  - run a red-check of the new tests against `main`;
  - run the full suite;
  - fix review findings itself, each with a test that fails first.
- **Swift tests** need a venv built against the checkout under test, with `scripts/dev_backend_venv.sh <scratch>/venv`. A venv built against a removed worktree fails `LiveBackendTests`.

## Closing a plan (unchanged)

1. Run the tests: pytest; swift test for app changes; screenshots for UI changes; `build_app.sh` + `check_bundle.sh` for packaging changes.
2. Write the SUMMARY.
3. Merge to `main` locally.
4. Run `graphify update .`.
5. Run `project-state set --next … --by "Claude Code"`.
