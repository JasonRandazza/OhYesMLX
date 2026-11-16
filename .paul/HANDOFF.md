---
description: "OhYesMLX (OYMLX) session handoff, 2026-11-16: Fable fix plans A (05-07) and B (05-08) closed and on main; start plan C (05-09) with Claude Code subagents, not Command Code"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-11-16 (plans A and B closed; plan C next)

> Read this first, then `.paul/STATE.md`, then `AGENTS.md`. STATE wins wherever this note and STATE disagree.
> Previous handoff: `.paul/archive/2026-11-15-handoff-fable-review.md`. Jason calls the project **OYMLX**.

## Start here — plan C, 05-09: process identity, locks and the ledger

Jason chose the fix order A→B→C→D→E→F→G (plans 05-07..05-13) on 2026-11-16. A and B are done, so do not re-ask the
order. Run C as an ordinary PAUL loop: `/paul:plan` → `/paul:audit` → `/paul:apply` → two-axis review → `/paul:unify`.
The pattern that worked for A and B: when the audit finds nothing that needs Jason, go straight from audit to APPLY
and tell him what was applied.

**Findings (11, none High), from `.paul/review/fable-5.2/FINDINGS.md` §5–§7:** S1-F1, S1-F2, S3-F16, S4-F13, S5-F3,
S5-F4, S5-F5, S5-F10, S5-F11, S5-F13, S5-F14. The fix direction for each is in `S1-`, `S3-`, `S4-` and
`S5-findings.md` (grep `### F<n> `). The red tests are on branch `review/fable-verify` (commit `6fb323c`). Copy each one with
`git checkout review/fable-verify -- tests/test_fable_s<n>_f<k>.py`. S3-F16 has no test, because there is no syscall seam
to inject, so its evidence is the unguarded `kill` in `BackendLauncher.swift`.

**The design the handoff from 2026-11-15 already chose:** write one shared check that a pid is still the process
that was recorded. Compare start time plus executable. Stop now, the fetch lock, the running-engines ledger and
`Handle.stop` all call it. One definition, every caller.

**What A and B already changed, so check these before planning:**
- 05-07 split PATH per engine. `_run` (lsof, ps, stop sweeps) now gets **no** lab prefix (`runtimes._engine_command`,
  `_lab_paths`), which may already close part or all of **S5-F10**. Run its red test first.
- 05-07 moved `cold_load_s` to end at readiness. The ledger write comes after `_serving_pid`. **S5-F5** asks for the
  ledger entry before readiness. Keep AC-4 of 05-07: the ledger write must stay outside the load window. Write the
  entry right after `_spawn` but before the clock starts, or subtract it.
- 05-08 moved the single-instance lock into the backend (`ohyesmlx app --lock-dir`, `cli._lock_app`, pid written into
  `app.lock`). That lock now uses pid-only liveness too, so it belongs under the same identity check if C touches it.
- 05-08 made `server._Job.finish` the only place the job slot is released.

## How to work while Command Code is limited (Jason, 2026-11-16)

Command Code's weekly limit is at 88% (resets around 2026-11-20). Do not dispatch `cc-agent` unless Jason says so.
Plans A and B ran this way:

- **The coordinator (Opus) does it directly** when the work is a High, a small fix, or a review fix.
- **Claude Code subagents (the Agent tool)**, with the model and effort chosen per task:
  - Sonnet at medium effort for a bounded Python fix with exact files.
  - Sonnet at high effort for a Swift state machine with red tests.
  - Opus at high effort for a design-heavy change (05-08's lock).
- Antigravity (Gemini 3.8 Flash) only if it is actually worth it. It was not worth it for B.

Every subagent prompt carries the plan's ACs, the exact files it may touch, "touch nothing else", "do not spawn
subagents", "start no runtime, model or download", and a first-edit-early rule.

**Traps that cost time in A and B:**
- **Create worktrees yourself** (`git worktree add -b fix/05-09-tN ~/orca/workspaces/OhYesMLX/05-09-tN fix/05-09`) and
  point the subagent there. The Agent tool's `isolation: "worktree"` once started from a stale commit.
- **The git stash stack is shared across worktrees.** Never use a bare `git stash`/`pop`. Use a WIP commit, or stash with a
  unique message and `git stash apply <sha>`.
- **Never `git merge` in the main checkout by accident.** Merge into an integration worktree on `fix/05-09`, then
  into `main` at UNIFY.
- **macOS has no `timeout` command.** A red-check of an events test on unfixed code can hang forever, so filter tests and
  watch for a hang.
- **The shared dev venv** (`~/.local/share/ohyesmlx/app-dev-venv`) imports the *main* checkout. If `swift test` runs on a branch
  that changes the backend, it needs a branch-local venv:
  `scripts/dev_backend_venv.sh <scratch>/venv` from that worktree, then `OYMLX_DEV_PYTHON=<scratch>/venv/bin/python`.
- **A red test can be wrong.** In A and B, four kinds turned up: a filter that compared a split PATH to the joined
  string; controls that pinned the old defect; tests that need a file the plan excluded; and tests that clash with the
  chosen design. Correct one minimally and list it in the SUMMARY. Never weaken what the finding asks.
- **DeepSeek workers stall** for 15–20 minutes re-verifying "contradictions". If one stalls, rule on it and re-dispatch, or do
  it yourself.

## Closing a plan (unchanged)

The coordinator runs `…/test-venv/bin/python -m pytest -q` (main is at **1420 passed**). For app changes, also
`cd app && OYMLX_DEV_PYTHON=… swift test` (**104 tests**). For UI changes, screenshot the existing `OYMLX_STUB_SCENARIO`
states in light and dark with `screencapture`, toggling appearance through System Events and restoring **dark**.
05-08's shell loop does this; see `docs/design/phase5/shots-05-08/`. Then the SUMMARY, merge `fix/05-09` → `main`
(local, not pushed), `graphify update .` (the post-merge hook does it), `project-state set --next …`.

## Still open beyond C

- **Live Phase 5 checks** (Stop now, a real download) are now possible, because B fixed the event stream. They need Jason's "when".
  Before them, run canaries for the untested Osaurus 0.25.33 and vMLX 1.6.84, and measure the S5-F2 constant (STATE
  Deferred Issues).
- Plans D–G. G includes re-running `scripts/check_bundle.sh`, because the packaged backend now gets `--lock-dir`.
- From B: retrying an interrupted evict does not auto-open its confirm sheet, because that needs `ModelsView.swift`.
- Phase 5 close: clean-account smoke, UAT (`/paul:verify`), `PHASE-5-SUMMARY.md`.
