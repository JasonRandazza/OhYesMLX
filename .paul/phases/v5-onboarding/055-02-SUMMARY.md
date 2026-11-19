---
phase: v5-onboarding
plan: 055-02
subsystem: app (SwiftUI) + hardware scan
tags: [evict-retry, already-running, disk-volume, free-disk-label]
provides:
  - "Retry of an interrupted evict opens the remove-confirm sheet. The request waits for the picks to load and is gated by the Remove button's own predicate"
  - "A second launch activates the other instance (`BackendLauncher.otherInstance`, one selector `otherPID`)"
  - "`Hardware.disk_volume` (mount point of the cache volume, null when the probe failed), and `Hardware.freeDiskLabel` as the one label definition"
key-files:
  created: [app/Tests/OhYesMLXKitTests/Plan05502Tests.swift, tests/test_055_02_disk_volume.py]
  modified: [app/Sources/OhYesMLXKit/AppModel.swift, app/Sources/OhYesMLX/Screens/ModelsView.swift, app/Sources/OhYesMLX/OhYesMLXApp.swift, app/Sources/OhYesMLXKit/BackendLauncher.swift, app/Sources/OhYesMLXKit/Models.swift, app/Sources/OhYesMLX/Screens/YourMacView.swift, app/Sources/OhYesMLX/Screens/BenchmarkView.swift, app/Sources/OhYesMLXKit/StubBackend.swift, ohyesmlx/hardware.py, docs/interfaces/v5-onboarding.md, docs/interfaces/v5-app.md]
key-decisions:
  - "Jason approved the new `disk_volume` Hardware field and the DEBUG stub `models-external-cache`"
  - "An evict request is taken by `AppModel.takeEvictRequest`, which waits until the picks have loaded (review finding)"
completed: 2026-11-19
description: "Phase 5.5 items 2, 3, 8: an interrupted evict's Retry opens the confirm sheet, a second launch activates the other instance, and Free disk names a non-startup cache volume"
type: Summary
about: "OhYesMLX"
---

# Plan 055-02: App cleanup (Phase 5.5 items 2, 3, 8)

**Outcome.** This plan fixed three app defects:
- Retry of an interrupted evict now lands on the remove-confirm sheet for that model. It never evicts without the user's confirmation.
- A second launch activates the first instance, not itself.
- "Free disk" reads "Free disk on Storage" when the Hugging Face cache lives on another volume, and reads as before on `/`.

## Acceptance Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| AC-1: evict Retry opens the confirm sheet | Pass | Unit tests cover the request, the pick lookup, the Remove-predicate gate, "no job started", and (review) "the request waits for the picks". The view wiring was checked by reading the code. There is no screenshot, because the `interrupted` stub scenario is a download. |
| AC-2: activate the other instance | Pass | `otherPID` is tested on plain pids ([me, other] gives other; [me] gives nil). `anotherInstanceIsRunning` and the activation share `otherInstance()`. `activate()` itself cannot be exercised in a test. |
| AC-3: Free disk names its volume | Pass | Python: the mount-point walk, `/` maps to `/`, and the probe-failure path gives `None`, with one shared `_existing_ancestor`. Swift: decoding works with and without the field, and the label is checked for nil, `/` and `/Volumes/Storage`. Screenshots in light and dark: `models` is unchanged, and `models-external-cache` reads "Free disk on Storage". |

## Verification

- **Red on main.** I ran the 5 new Python tests against `main`'s code and all 5 failed. The new Swift tests cannot compile against `main`, which counts as red, and the worker recorded behavioural red runs for each task.
- **pytest.** 1669 passed and 3 skipped in the worktree.
- **swift test.** 131 tests, 0 failures, after the review fix.
- **Screenshots.** Taken by the coordinator in light and dark, of `models` and `models-external-cache`. Dark mode was restored afterwards.
- **Scope.** Files changed match `files_modified`. One existing test was edited: `AppModelTests.testEveryStubScenarioReachesItsScreen` gained the new stub case, because its switch is exhaustive and would not compile otherwise. No assertion changed.

## Commits

| Commit | Description |
|--------|-------------|
| `be4b738` | The fix, written by a worker: Command Code, DeepSeek v4.1 flash, 70 turns, $0.11 |
| `119c5dc` | Review fix: the evict request waits for the picks |

## Deviations

- **Review finding (Spec, AC-1), fixed by the coordinator.** The worker's view cleared the evict request even when the picks had not loaded yet. A Retry that arrived before `recommendations` loaded would then silently open nothing. The fix moves the logic into `AppModel.takeEvictRequest()`, which keeps the request until the picks exist. `ModelsView` also re-checks when `recommendations` change. The test was red against the old behaviour and green after the fix.
- **One new API.** `AppModel.canRemove(_:)` lifts the Remove button's predicate out of the view, as the audit asked. It is equivalent to the old `canStartJob`, because Remove is only shown on downloaded rows.
- **One screenshot not taken.** The AC-1 screenshot was best-effort and was skipped, because no stub scenario has an interrupted evict.

## Deferred

These are the audit's two deferred items:
- A long volume name in the toolbar meter. That belongs to Phase 5.6 (UI aesthetics).
- `activate()` when the other instance is hidden or on another Space.

## Next

Phase 5.5 still has:
- **Scripts and docs:** items 1, 5 and 10.
- **Item 9:** the vMLX quiet-machine measurement, which waits for Jason to say when.
