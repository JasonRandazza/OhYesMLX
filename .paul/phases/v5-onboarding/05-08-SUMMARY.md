---
phase: 05-app
plan: 08
subsystem: app
tags: [swiftui, sse, urlsession, job-lifecycle, flock, server]
requires:
  - phase: 05-app
    provides: 05-07 (measurement integrity) merged; Fable red tests on review/fable-verify
provides:
  - The app receives real events over a real URLSession (S3-F1 closed)
  - One job slot, freed when the work ends; `done` means the slot is free
  - Backend-owned single-instance lock with a "still finishing" state
affects: [live Phase 5 checks, 05-09 (process identity), clean-account smoke]
key-files:
  modified: [app/Sources/OhYesMLXKit/HTTPBackend.swift, app/Sources/OhYesMLXKit/AppModel.swift, app/Sources/OhYesMLXKit/BackendLauncher.swift, app/Sources/OhYesMLX/RootView.swift, app/Sources/OhYesMLX/Screens/BenchmarkView.swift, app/Sources/OhYesMLX/Screens/EnginesView.swift, ohyesmlx/server.py, ohyesmlx/fetch.py, ohyesmlx/cli.py, docs/interfaces/v5-app.md]
key-decisions:
  - "SSE lines split on bytes; reconnect stops on connection-refused / non-429 4xx and after 5 consecutive failures"
  - "A job is active from a successful POST until `done`; `error` records, `done` decides"
  - "`ohyesmlx app --lock-dir DIR` takes app.lock before its launch line; a held lock prints {\"error\":{\"code\":\"already_running\",\"holder_pid\":N}} and exits 2"
completed: 2026-11-16
description: "Fable fix plan B: the app's live event stream dispatches (S3-F1 High), a job is active until `done`, the slot and the single-instance lock belong to the side doing the work, and eleven smaller lifecycle defects are fixed"
type: Summary
about: "OhYesMLX"
---

# Phase 5 Plan 08: Fable fix plan B — app job lifecycle and event stream

**All 16 plan-B findings are closed. The app now receives `progress`/`result`/`error`/`done` over the real
transport. That used to never happen: `bytes.lines` dropped the blank line every SSE event ends on. The job
slot, the job state and the single-instance lock are each owned by the side doing the work.**

## Performance

| Metric | Value |
|--------|-------|
| Tasks | 4 (1 coordinator, 3 Claude subagents: Sonnet medium, Sonnet high, Opus high) |
| Tests | pytest 1414 → 1418 passed, 2 skipped; swift 81 → 104, 0 failures |
| Files | 37 changed, +2246 / −167 |
| Command Code | none (weekly limit at 88%) |

## Acceptance Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| AC-1 real stream dispatches (S3-F1) | Pass | `FableS3F1Tests` red on the old code (blank line dropped, no event in 3 s) and green now. A split "…" and an unterminated final event are tested |
| AC-2 bounded reconnect (S3-F11) | Pass | 203 reconnects in 0.5 s on the old code; now it stops on connection refused. `backendExited` cancels the event task |
| AC-3 active until `done` (S3-F5) | Pass | `endedState` is recorded at `error`, and the state flips at `done` |
| AC-4 atomic start, routed refusal (S3-F6) | Pass | The `starting` claim happens before the first await. Reset and inflight write happen after the POST. Refusals go to `benchmarkRefusal`/`modelRefusals` |
| AC-5 only quickbench replaces the summary (S3-F2) | Pass | |
| AC-6 cancel does not resurrect (S3-F4) | Pass | |
| AC-7 Stop Now escalates (S3-F13) | Pass | Model test plus `.disabled` only in `.stoppingNow` |
| AC-8 retry through the gates (S3-F15) | Pass | An install opens the consent sheet. A benchmark shows its plan. An evict opens Models, without auto-opening the confirm (see Deferred) |
| AC-9 failed plan fetch clears the plan (S3-F17) | Pass | |
| AC-10 quit completes on backend exit (S3-F12) | Pass | The banner reads "Stopping \<name\>…" only for an active job |
| AC-11 retry reloads over a live runner (S3-F7) | Pass | |
| AC-12 backend owns the lock (S3-F8) | Pass | `--lock-dir`, non-inheritable fd (tested), pid written; `.stillFinishing` with Check Again when no other app is running |
| AC-13 only EWOULDBLOCK is held (S3-F14) | Pass | |
| AC-14 slot freed when the thread returns; `done` after (S1-F5, S1-F6) | Pass | One release site, `_Job.finish`. A test starts a second job from `done` and gets 202 |
| AC-15 copy states what the code does (S3-F3 residual) | Pass | Three BenchmarkView sentences softened; the stale `AppModel` comment rewritten |
| AC-16 suites green and screenshots | Pass | Coordinator ran both suites on `fix/05-08`. Screenshots in `docs/design/phase5/shots-05-08/`, light and dark; appearance restored to dark |

## Task Commits

| Task | Commit | Who |
|------|--------|-----|
| 1 SSE splitter + bounded reconnect | `6b056bb` | coordinator |
| 2 slot freed at thread return | `9089dac` | Sonnet subagent (medium) |
| 2b fetch holds `done` until ledger+lock | `8e5affa` | coordinator |
| 3 AppModel lifecycle + screens | `3fb4980` | Sonnet subagent (high) |
| 4 backend-owned lock | `1d141f7` | Opus subagent (high) |
| screenshots | `ea99b44` | coordinator |

## Deviations from Plan

| Type | Count | Impact |
|------|-------|--------|
| Boundary amended | 1 | `fetch.py` was excluded, but S1-F5's red test calls `fetch.download` directly. Its `done` is now held until the ledger is written and the lock released, as the finding's fix direction says |
| Red-test corrections | 4 files | s1_f5 (the slot is held after the module's `done`); s3_f6 (two assertions encoded the missing claim); s3_f8 (the fake backend now takes the lock, the app holds none, `.stillFinishing` accepted); s3_f14 (new enum case). None is weaker |
| New CLI flag | 1 | `ohyesmlx app --lock-dir`. It is a flag, not a subcommand, and is pinned in `docs/interfaces/v5-app.md` P5-7 |
| New system import | 1 | `BackendLauncher` imports AppKit for `NSRunningApplication`. It is a system framework, not a package dependency |
| Worker isolation | 1 | The first subagent's automatic worktree started at a stale commit, and it reset to `main`. Later tasks used coordinator-made worktrees |

## Deferred Items

- **Retrying an interrupted evict** opens Models but not the confirm sheet, because auto-opening it needs `ModelsView.swift`. The user presses Remove, which confirms as usual.
- **Activating the running app.** `OhYesMLXApp`'s `alreadyRunning` handler activates `.first` of the processes with this bundle id, which can be the app itself. This is harmless now that `.alreadyRunning` requires another instance.
- **The packaged-app check was not re-run.** `check_bundle.sh` launches the GUI and writes Application Support. The packaged backend now receives `--lock-dir`, so re-run the check before release (plan G).
- **The shared dev venv** (`~/.local/share/ohyesmlx/app-dev-venv`) imports the main checkout, so a branch with a backend change needs a branch-local venv for `LiveBackendTests`. This is how it works already, not a defect.

## Next Phase Readiness

**Ready:** the live Phase 5 checks (Stop now, a real download) can now see real events, whenever Jason chooses to run them. Plan C (05-09, process identity) is next.

**Blockers:** none.

---
*Phase: 05-app, Plan: 08 · Completed: 2026-11-16*
