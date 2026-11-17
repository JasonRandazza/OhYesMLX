---
phase: 05-app
plan: 10
subsystem: downloads
tags: [fetch, disk, eviction, quickbench, swiftui]
requires:
  - phase: 05-09
    provides: identity-checked fetch lock (untouched here)
provides:
  - a mid-body network error is retried and its partial ledgered; retry exhaustion keeps a valid prefix
  - one free-disk definition (`hardware.free_bytes_at`) on the cache's volume, used by both fetch guards, /hardware, recommendations and the quickbench plan
  - one bytes-still-to-fetch definition (`fetch.missing_bytes`, stat-only), so a partial row is judged on its remainder
  - quick-bench evicts only what it owns, records every leftover, keeps the user's own partials (`summary["kept"]`), and refuses a chosen row whose bytes do not verify
affects: [05-10b, plan E (P5-11 re-download), live Phase 5 download check]
key-files:
  modified: [ohyesmlx/fetch.py, ohyesmlx/hardware.py, ohyesmlx/recommend.py, ohyesmlx/server.py, ohyesmlx/quickbench.py, app/Sources/OhYesMLXKit/AppModel.swift, app/Sources/OhYesMLXKit/Models.swift, app/Sources/OhYesMLXKit/StubBackend.swift, app/Sources/OhYesMLX/Screens/BenchmarkView.swift, docs/interfaces/v5-app.md]
key-decisions:
  - "Retry budget stays cumulative (the S1-F4 red test pins it); exhaustion keeps the partial instead of deleting it"
  - "Hardware.disk_free_bytes now means free bytes on the HF cache's volume"
  - "The integrity check runs in quickbench.run before the Osaurus pin, never in plan (a GET handler)"
  - "Durability flush is F_FULLFSYNC with an os.fsync fallback"
duration: ~2.5h (plan, audit, apply, review)
completed: 2026-11-16
description: "Fable plan D closed: downloads survive dropped connections without losing bytes, free disk is measured where the bytes land and re-read after every job, partial rows are judged on what is left, and quick-bench deletes only what it downloaded and never measures a corrupt blob"
type: Summary
about: "OhYesMLX"
---

# Phase 5 Plan 10 (Fable fix plan D): Downloads, disk and eviction — Summary

**All 10 plan-D findings are closed: S1-F3, S1-F4, S1-F8, S3-F10, S4-F3, S4-F7, S4-F9, S4-F11, S4-F12 and S4-F14. Each
red test from `review/fable-verify` (`6fb323c`) is green, and the 2 control tests are still green.**

## Performance

| Metric | Value |
|--------|-------|
| Tasks | 3 of 3, each qualified by the coordinator |
| Commits | `3b3a7f7` red tests, `0d36ce7` + `a991068` Task 1, `1db5fe5` + `9471822` Task 2, `6ea4a5f` Task 3, `7f4f611` review fixes |
| Tests | pytest 1499 passed and 2 skipped (main before: 1473); swift 110 (before: 108), 0 failures |
| Files | 31 changed |

## Acceptance Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| AC-1: mid-body error retried and ledgered (S1-F3) | Pass | Only `response.read` is inside the catch; ENOSPC on write is not retried (new test); the residue is ledgered in a `finally` |
| AC-2: exhaustion keeps a valid prefix (S1-F4) | Pass | `size_mismatch` without `remove=`; budget unchanged |
| AC-3: refs/main removed only if it still holds our revision (S1-F8) | Pass | Unreadable or rewritten → kept and logged |
| AC-4: flush before rename; ledgered bad blob repaired (S4-F14 half 1) | Pass | `_flush` (F_FULLFSYNC → fsync) on the partial and the blobs dir; a bad blob is re-fetched only when the ledger lists it; a present blob is hashed once |
| AC-5: one free-disk definition on the cache volume (S4-F3) | Pass | `hardware.free_bytes_at`; `disk_usage` appears only in hardware.py |
| AC-6: partial row judged on its remainder (S4-F7) | Pass | `fetch.missing_bytes` is stat-only; `_download` passes its verified `present` map |
| AC-7: app re-reads free disk; backend computes `free_after_bytes` (S3-F10) | Pass | Hardware refresh after every download or evict ending, including errors; client arithmetic deleted |
| AC-8: evict only what the run owns; record every leftover (S4-F9, F11, F12) | Pass | `_run_owned`; `summary["kept"]`; one `evict_or_record`; the last error code in the skip reason |
| AC-9: corrupt chosen row refused before the Osaurus pin (S4-F14 half 2) | Pass | A log event; cancel checked between files; siblings already on disk are verified before their cell |
| AC-10: everything green | Pass | Counts above; `graphify update .` run |

## Decisions Made

| Decision | Rationale | Impact |
|----------|-----------|--------|
| Cumulative retry budget, partial kept (audit) | The failing red test pins 4 passes, 3 sleeps and `size_mismatch`. Resetting on progress would make the pass count unbounded | A user's Retry resumes from the prefix |
| `disk_free_bytes` = the cache volume's free bytes | Every screen shows the number the guards use | Identical to before when the cache is on `/` |
| Verify in `run`, not `plan` | `plan` serves `GET /quickbench/plan`; hashing gigabytes there stalls the request | One hash pass per run |
| `free_after_bytes` required, not defaulted to 0 | A default would show a silent wrong figure | `test_cli.py` constructor gained one field |
| `download`'s `hardware=` parameter deleted (review) | Unread once the guards asked `free_bytes_at`; dead flexibility | 4 test call sites lost the keyword |
| `fetch.in_ledger` is public (review) | quickbench read the ledger's dict shape through a private loader | One reader of the ledger shape outside fetch's own internals |

## Deviations from Plan

**Red-test corrections.** Each one is minimal, none weakens its finding, and each is one of the four known kinds:
- **S4-F3:** `(event["payload"] or {})`. This was a filter bug: the first event is a `log` with no payload.
  `hardware=` was also removed from its `download` call; the parameter no longer exists, so this is a design clash.
- **S4-F9:** the partial's path is now derived rather than looked up in `cache.partials`. The fake's own `evict` pops
  that entry, so the old precondition could not hold in the evicted branch. `verify=NO_VERIFY` was added.
- **S4-F11:** `verify=NO_VERIFY` was added, because its fakes hold wrong bytes on purpose.
- **S4-F14:** the test now drives `run` instead of `plan`, as the plan context records. It is stronger than the
  original: it adds assertions on the pin, the summary and the refusal wording, plus a test that `plan` never hashes.
- **S1-F3 and S1-F4:** `hardware=` was removed from their `download` calls. This is a design clash.

**Test seam.** `quickbench.run(verify=fetch._verify)` was added, and `NO_VERIFY` is used at every existing direct `run`
call site. The fakes write no blobs, so real verification would refuse every run.

**Verification grep.** The plan expected `remove=incomplete` only on the `over` path. Six sites remain: a partial larger
than the pinned size, HTTP 416, a bad Content-Range, a mismatched range, a claimed length above the pinned size, and
`over`. All six predate this plan and all are real size contradictions, so AC-2's wording holds. The short-close
exhaustion path no longer removes the partial.

**Review fixes (`7f4f611`):**
- **Spec axis, AC-8 defect.** A run-owned sibling whose download was refused before its first byte (`low_disk`,
  `busy`) ledgers nothing. It was still evicted, which refused, so it was reported in `not_evicted` as "left on disk"
  with zero bytes on disk. It is now skipped when the ledger has no entry. The new test was red-checked against the
  old code and is green on the fix.
- **Missing tests added:** `summary["kept"]`, and the chosen-row check's log event and between-files cancel.
- **Standards axis.** The dead `hardware=` parameter was deleted. `fetch.in_ledger` was added. `downloaded` now asks
  `_stat_present` for its blob half, so the stat-presence check is defined once. Rationale restated in `run`'s
  docstring was trimmed, and a mis-wrapped docstring in `hardware.free_bytes_at` was fixed.
- **One reviewer claim was wrong.** The Standards reviewer counted the `hardware=` sites in `test_engines.py`, but those
  belong to `engines.install`, whose parameter is still read.

**Review findings judged and not changed:**
- **The `hardware` ↔ `fetch` lazy import in `scan`.** The audit chose it to keep `default_cache_dir` defined once.
- **`fetch._verify` called from quickbench.** It is private by name inside a flat package; renaming it would touch
  every fetch test.
- **The `verify=` seam.** It matches the file's existing injection style (`pin`, `restore`, `recover`).
- **The size of `quickbench.run`.** It predates this plan.

## Deferred (from the audit)

- The "Free disk" label on Your Mac and Models now means the cache volume. This is identical for every default setup,
  and the label copy lives in `ModelsView`, which was out of scope.
- `_verify` cannot be cancelled mid-file (about 10 s for 20 GB); cancel is honoured between files.
- The two hero models' re-serialised safetensors would fail `_verify`. `downloaded()` already reports them absent, so
  this adds no new refusal.
- `missing_bytes` read on a GET races an in-flight partial. The figure is an estimate, and the download's own guard
  decides under the lock.

## Next Phase Readiness

**Ready:**
- **Plan 05-10b (port independence) is next.**
- **The live Phase 5 download check** now exercises the retry, the kept prefix and the flush. It needs Jason's "when".

**Concerns:**
- **`fetch.download` lost its `hardware=` keyword.** Any external script that passed it now gets a TypeError. No
  in-repo caller remains.

**Blockers:** none.

---
*Phase: 05-app, Plan: 10*
*Completed: 2026-11-16*
