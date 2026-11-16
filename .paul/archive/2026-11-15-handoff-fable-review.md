---
description: "OhYesMLX (OYMLX) session handoff, 2026-11-15: Fable 5.2 review complete (75 findings, 4 High); next, choose and run the fix plans, then close Phase 5"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-11-15 (Fable 5.2 review complete)

> Read this, then `.paul/STATE.md`, then `.paul/review/fable-5.2/FINDINGS.md`, then `AGENTS.md`. STATE wins on conflict.
> Previous handoff: `.paul/archive/2026-11-14-handoff-phase5-first-pass.md`. Jason calls the project **OYMLX**.

## Start here — implement the review fixes (Jason decided 2026-11-16)

Jason chose the fix order **A → B → C → D → E → F → G** (FINDINGS §5) and wants the next session to go straight into
implementation. Do not re-ask the order. Run each plan as an ordinary PAUL plan in `.paul/phases/v5-onboarding/`,
continuing the Phase 5 numbering: **A = 05-07, B = 05-08, C = 05-09, D = 05-10, E = 05-11, F = 05-12, G = 05-13**.

**Step 0 (once, minutes):**
1. If `git status` still shows the review artifacts uncommitted (FINDINGS.md, `S<n>-findings.md`, dossiers, `verify/`,
   PLAN.md, STATE, this HANDOFF, the archived handoff), ask Jason for a one-line yes and commit them on `main`, and the
   red tests on `review/fable-verify` (worktree `~/orca/workspaces/OhYesMLX/fable-verify`, branch unmerged).
2. Check for hung nightly librarian processes: `pgrep -x command-code`, then each one's cwd via
   `lsof -a -p <pid> -d cwd`. The Deep Wiki librarian automation (`~/orca/workspaces/deep-wiki-librarian/auto-orca-nightly-…`)
   hung for 18–20 h on two nights running (runs 69 and 70) holding Command Code. Run 69 was stopped with Jason's yes; run 70
   (pid 40132) was still alive at handoff time and Jason had not answered. Ask before killing it, and note it as an
   Agent-Environment bug to fix.

**Per plan (the loop):**
1. `/paul:plan` → write `05-0N-PLAN.md`. Its acceptance criteria are the plan's findings. **Each finding's red test from
   `review/fable-verify` is that fix's first test.** Copy it into the plan's branch with
   `git checkout review/fable-verify -- tests/test_fable_s<n>_f<k>.py` (or the `app/Tests/OhYesMLXKitTests/FableS<n>F<k>Tests.swift`
   file) once the review branch is committed. It must go green, and nothing else may go red.
2. `/paul:audit`, then APPLY through `.paul/orders/dispatch.sh` with `CC_ROUTE=deepseek` (default) and `CC_AGENT_MAX_TURNS=200`.
   Use `kimi-pro` only where named below. **At most 2 workers at once; write "do not spawn subagents" into every order.**
   Swift work goes one worker at a time (SwiftPM `.build` lock).
3. Close only on the coordinator's own green run: `…/test-venv/bin/python -m pytest -q`, plus `swift test` for app
   changes, plus screenshots for UI changes (AGENTS.md delegation contract). Then a two-axis review, then `/paul:unify`.
4. **Never edit `ohyesmlx/*.py` while a measurement is running**, and run no measurement during this work unless Jason says when.

**Plan A, 05-07: published numbers and measurement integrity** (S2-F1..F9, S2-F11, S5-F1, S5-F2, S5-F9, S4-F5)
- S2-F1 (High): a FAIL cell must carry no `decode_tps`/`ttft_s`. Fix it at the one definition (`report._row`, or the
  quickbench cell builder `quickbench.py:335-350`, whichever every caller routes through), not in the view.
- S5-F1 (High): `runtimes.lab_env` (`runtimes.py:505-531`) prefixes every engine's lab bin to every start's PATH, so the
  mlx-lm control starts OptiQ's `mlx_lm.server` (mlx 0.32.4 vs the control's 0.32.2). Scope a lab bin to its own engine.
  **Plus an audit deliverable:** list the measured mlx-lm rows (`results/**/results.jsonl`) whose run started while
  `~/Library/Application Support/OhYesMLX/lab-paths.json` named OptiQ (STATE records it from at least 2026-11-02), and
  annotate them in a research note. Discard nothing. The audit is a `kimi-pro` candidate; the code fix is DeepSeek.
- S5-F2 (High): take the version probe and `lsof` out of the `cold_load_s` window. Measuring the constant they added, once
  per runtime, is a measurement and needs Jason's "when".
- S2-F2 (SSE `select()` over a buffered reader) touches TTFT timing in `transport.py:264-292`. Review it hardest.

**Plan B, 05-08: app job lifecycle and event stream** (S3-F1, F2, F3-residual, F4–F8, F11–F15, F17, S1-F5, S1-F6)
- **S3-F1 (High) first:** replace `bytes.lines` (`HTTPBackend.swift:38`) with a line splitter that keeps empty lines. Test:
  `FableS3F1Tests`, which uses a real `URLSession`. This unblocks the live Phase 5 checks.
- S3-F3 was refuted; only the stale comment at `AppModel.swift:677` and the Results/Benchmark copy remain.

**Plan C, 05-09: process identity, locks and the ledger** (S1-F1, S1-F2, S3-F16, S4-F13, S5-F3, F4, F5, F10, F11, F13, F14)
- One shared "is this pid still the process I recorded" check (start time plus executable) used by Stop now, the fetch
  lock, the ledger and `Handle.stop`. One definition, every caller.

**Plans D–G** follow FINDINGS §5 as listed. P5-11 joins E. G (packaging) comes before any release; S6-F7 was refuted (the
residual is only the substring PATH match).

When A–C are done, run the live Phase 5 checks (with Jason's "when"), the clean-account smoke, UAT, then D–G or Phase 5
close as Jason prefers.

## Where things stand

v5.0 Phase 5 first pass is built and committed (05-01 `93d374c` … 05-06 `101df7c`; 1370 pytest, 81 swift tests;
check_bundle 9/9). The review found that the build passes its own tests while four Highs stand, so Phase 5 is not
closeable until at least plans A–C land. P5-11 joins plan E. Open for Phase 5: the fixes, the clean-account smoke, the live
checks, UAT (`/paul:verify`), `PHASE-5-SUMMARY.md`.

## Lessons from the review run (keep them)

- **Command Code's 5-hour window is the constraint, not dollars.** Seven parallel MiMo Pro workers took it from 6% to 70%
  for about $1. Cap fan-out at 2–3, write "do not spawn subagents" into every order, and batch Low-severity
  verifications (one run per section). Whole review: about $3.70 of Command Code, 60 runs.
- **Fable headless:** `claude -p --model claude-fable-5-2 --allowedTools Read Grep Glob Write` (see
  `orders/run_fable.sh`). `Agent(model: "fable")` resolves to `claude-fable-5-1`. One section per Anthropic 5-hour
  window was safe, and Fable used neither its reset nor a full reset.
- **Background jobs stop at 2 hours;** split long waits, and wait on wall-clock time plus network
  (`until [ now >= t ] && curl …`), not a bare `sleep`, so a sleeping laptop does not launch late or offline.
- `kimi-pro` exists as an explicit-only route in Agent-Environment (bench 18/18), but at $0.20/M cache reads it is for
  hard judgment only.
- A nightly Deep Wiki librarian automation had hung for 18 hours holding a `command-code` process. It was stopped. Worth
  checking in Agent-Environment.

## How this project's sessions work (keep doing it)

- Command Code does the implementation via `.paul/orders/dispatch.sh` (cached PREAMBLE), with a progress Monitor on each
  dispatch. Reviewers get the diff as a file.
- **A worker's or reviewer's report is not evidence.** In this review the coordinator re-ran every red test, read every
  High against the code, overruled one downgrade (S5-F1) and accepted five.
- UI changes: screenshot the `OYMLX_STUB_SCENARIO` states in light and dark, and restore Jason's appearance (dark).
