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

**Time-critical (the Fable 5.2 Pro promotion ends Sunday 2026-11-16 at 11:59 PM PT):**

1. **Confirm Fable 5.2 capacity.** Open Claude Settings → Usage. Note the weekly usage remaining, how many Fable
   resets are available (Jason believes 5; the published Pro offer is 1, and Max/Ultra get 1–3), and that
   Fable 5.2 appears in Claude Code's `/model`. *Why:* the plan calibrates how many review sections fit per window.
2. **Approve or decline a Kimi K3.1 Pro trial route for Command Code.** Kimi K3.1 Pro is the strongest worker
   model available (Vals 62.5%; Qwen 3.8 Max is weaker and pricier). It is not an approved fleet route, and adding
   one is a policy change that is Jason's call. *If yes:* the agent benchmarks it with `model-bench.py` (about $1)
   and uses it to verify Fable's findings. *If no:* the plan uses MiMo v2.6 Pro, which is already approved.
3. **Choose the order.** Recommended: the Fable review **first** (it is the only time-limited item), and the Phase 5
   closing checks (items 4–6) in the same sitting while workers build dossiers. The live checks must not run while
   workers run, so they go before P0 or after it.
4. **Re-add the test-account sudo rule** for the clean-account smoke (05-06 AC-6):
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

Execute `.paul/review/fable-5.2/PLAN.md`. Opus orchestrates, Fable 5.2 reviews six sections (S1 security, S2
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
