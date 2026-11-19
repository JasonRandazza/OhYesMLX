---
phase: v5-onboarding
plan: 055-01
subsystem: backend (runtimes, fetch)
tags: [lab-paths, lsof, ps, cancel, download-lock]
provides:
  - "System helpers (ps, lsof, /usr/bin/env-wrapped ps) never read the lab files"
  - "Cancellable hashing during _verify (every CANCEL_CHECK_CHUNKS = 64 chunks, about 16 MiB)"
  - "A legacy bare-pid download.lock is reclaimed once its pid belongs to a non-ohyesmlx process"
key-files:
  created: [tests/test_055_01_backend_cleanup.py]
  modified: [ohyesmlx/runtimes.py, ohyesmlx/fetch.py]
key-decisions:
  - "Helper skip is by system directory OR exact LSOF/PS (LSOF may be a Homebrew path)"
  - "A cancel during a hash raises the private _Cancelled exception, never a False return value"
completed: 2026-11-19
description: "Phase 5.5 items 4, 6, 7: a malformed lab-paths.json no longer breaks ps/lsof, a cancel interrupts a hash mid-file, a recycled-pid legacy lock no longer wedges downloads"
type: Summary
about: "OhYesMLX"
---

# Plan 055-01: Backend cleanup (Phase 5.5 items 4, 6, 7)

**Outcome.** This plan fixed three backend defects:
- A malformed `lab-paths.json` no longer takes out stop and recovery for every engine.
- A cancel takes effect within about 16 MiB of hashing, where before it waited for the whole file.
- A recycled pid in a legacy lock no longer blocks downloads.

A broken lab file still refuses an engine start.

## Acceptance Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| AC-1: helpers never read the lab files | Pass | `_listener_pids` and `_process_identity` answer under a lab file containing `{`. A non-system `LSOF` path is covered, the lab prefix still applies to lab programs, and an engine start still raises. |
| AC-2: a cancel interrupts a hash mid-file | Pass | Covered for sha256 and for git-blob hashing. A pre-existing blob is kept and not repaired. A finished `.incomplete` is kept and not renamed. With no cancel, `_verify` gives the same answers as before. |
| AC-3: a legacy lock held by a non-ohyesmlx pid is stale | Pass | The lock is reclaimed for a non-ohyesmlx argv. It stays busy when the argv names ohyesmlx, when the argv cannot be read, or when the lock names this process. JSON-identity locks and `_release_lock` are unchanged. |

## Verification

- **Red on main.** I ran the new test file against `main`'s source. The 7 behaviour tests failed. The 8 that guard unchanged behaviour passed, as they should.
- **Full suite.** `test-venv pytest -q` gave 1664 passed and 3 skipped; the baseline was 1649 passed. The coordinator ran it after the review fix.
- **Scope.** The diff touches only the three files the plan allowed. No existing test was edited.
- **Review.** The coordinator reviewed inline on both axes, Spec and Standards. There was one Standards finding: the 64-chunk interval and its rationale were restated in the `_verify` and `_file_chunks` docstrings. That was fixed in `2712314`, so the interval is now stated once, at `CANCEL_CHECK_CHUNKS`.

## Commits

| Commit | Description |
|--------|-------------|
| `e2a4bb8` | The fix, written by a worker: Command Code, DeepSeek v4.1 flash, 45 turns, $0.05 |
| `2712314` | The review fix: the cancel interval is stated once |

## Deviations

- **New helper.** The worker added a private helper, `fetch._file_chunks`, which the plan did not name. It is the single place the cancel check lives, shared by both hash functions. Without it, the 64-chunk rule would have been written twice.
- **Who wrote the SUMMARY.** The plan's `<output>` was written by the coordinator, not the worker, because the worker's order limited it to three files.

## Deferred

- **Fail-closed lock (audit deferred item 1).** A process whose argv merely contains an `.../ohyesmlx/...` path, such as pytest run from the test venv, keeps a legacy lock busy. This fails closed. Nothing writes the bare-pid format any more.
- **Cancel latency not measured.** Real wall-clock cancel latency on a 20 GB hash has not been measured, because no download was run.

## Next

Phase 5.5 continues:
- **App:** items 2, 3 and 8.
- **Scripts and docs:** items 1, 5 and 10.
- **Item 9:** the vMLX measurement waits for Jason to say when.
