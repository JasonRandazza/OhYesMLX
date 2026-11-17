---
phase: 05-app
plan: 09
subsystem: runtime lifecycle, fetch lock, app launcher
tags: [process-identity, ledger, pid-reuse, flock, osaurus, swift]
requires:
  - phase: 05-07
    provides: per-engine lab PATH (closes S5-F10), cold_load_s spawn-to-ready
  - phase: 05-08
    provides: backend-owned app.lock (flock, untouched here), `_Job.finish` as the one slot release
provides:
  - "`runtimes.same_process(pid, identity)`: the one liveness+identity check (start time compared, C locale, UTC)"
  - "ledger files carry an owner block; stale own-pid files are orphans; kept orphans are reported"
  - "the ledger names an engine from its spawn; stop commands derived from the port, never read from disk"
  - "starts refuse while any engine port or any Osaurus app is resident; `~/Applications` Osaurus recognised"
  - "download lock records owner identity; a young empty lock is held"
  - "the app never SIGKILLs a reaped backend pid"
key-files:
  modified: [ohyesmlx/runtimes.py, ohyesmlx/fetch.py, ohyesmlx/quickbench.py, app/Sources/OhYesMLXKit/BackendLauncher.swift, docs/interfaces/v5-app.md, docs/runtimes/osaurus.md, tests/conftest.py]
  created: [tests/test_fable_s1_f1.py, tests/test_fable_s1_f2.py, tests/test_fable_s4_f13.py, tests/test_fable_s5_f3.py, tests/test_fable_s5_f4.py, tests/test_fable_s5_f5.py, tests/test_fable_s5_f10.py, tests/test_fable_s5_f11.py, tests/test_fable_s5_f13.py, tests/test_fable_s5_f14.py, app/Tests/OhYesMLXKitTests/FableS3F16Tests.swift]
key-decisions:
  - "Identity is the process start time (argv recorded, not compared): launch scripts `exec` and change argv"
  - "The early ledger write is not subtracted from cold_load_s; settling a predecessor's file runs before the clock"
  - "`_RUN_STARTED_PIDS` deleted: unread once every Osaurus app counts as resident"
duration: ~2h (plan, audit, apply, review, unify)
completed: 2026-11-16
description: "Fable fix plan C: one identity check for every signal and every owner, ledger from spawn with no executable data, one-model-resident enforced across every engine port; 11 findings closed"
type: Summary
about: "OhYesMLX"
---

# Phase 5 Plan 09 (Fable fix plan C): process identity, ledger, locks — Summary

**Every path that signals a pid, or decides that a lock or ledger owner is dead, now goes through one check,
`runtimes.same_process`. An engine is in the ledger from the moment it is spawned. A start refuses while any engine
port is held or any Osaurus app is resident. All 11 findings are closed. Merged to `main` as `251090d`, locally,
not pushed.**

## Acceptance Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| AC-1: One definition of "the same process" | Pass | `same_process` calls `_process_alive`, then checks the pid is this user's (EPERM means not ours), then compares start time. `ps` runs as `env LC_ALL=C TZ=UTC`. `_process_identity(` is called only by `same_process`, `_own_identity` and the recorder. `fetch._pid_alive` is deleted. |
| AC-2: A ledger file belongs to the process that wrote it | Pass | Each file has an owner block. A file under this process's own pid that has no owner block, or a foreign one, is an orphan. A predecessor's entries are settled before this process writes its own (`_adopt_ledger`), and any kept are marked `inherited`. Stop now reads only a file this process wrote, and only entries whose identity still matches. |
| AC-3: An orphan that cannot be proved is kept and reported | Pass | The file is kept and one `running_engine_ledger` line names the reason: "port unreadable" or "identity unproven". A stranger on the port is dropped, and since the review that drop is now reported too. |
| AC-4: The ledger stores no command | Pass | `_stop_command_for_port` derives the command from `RUNTIMES`. New entries have no `stop_command`, and the old field is ignored. A back-compat test reads a pre-05-09 file. |
| AC-5: The engine is in the ledger from its spawn | Pass (amended at review) | The entry is written right after `_spawn` and written again with `serving_pid` after readiness. A failed start forgets the entry only once its cleanup has succeeded. **Amended:** the plan said to subtract the write time from `cold_load_s`; that is removed (see Deviations). |
| AC-6: The download lock | Pass | The lock holds `{pid, lstart, argv}` as JSON. A bare-pid lock is read as legacy. An empty lock younger than `LOCK_WRITE_WINDOW_S = 10.0` is held. The existing fetch tests pass unmodified. |
| AC-7: A reaped pid is never signalled | Pass | `_REAPED_PIDS` is filled by `_process_alive`'s `waitpid` and cleared when `_spawn` reuses a pid. Since the review, a reaped pid is recorded with no identity. |
| AC-8: One model resident | Pass | A start refuses while any `RUNTIMES` port is not free, naming the port, the runtime and the `lsof` command. Every live Osaurus app counts, including one this run started. Osaurus is found under `/Applications` and `~/Applications`, both spellings. In quickbench a `RuntimeStopError` ends the run (`ended: error`), and the Osaurus restore still runs, which a test covers. |
| AC-9: The Swift kill guard | Pass | `FoundationLauncherProcess.kill` checks `isRunning`, and `LaunchSession.forceKill` checks `exited`. `FableS3F16Tests` has 4 tests (forceKill and abandon on an exited fake; a live fake is still killed). |
| AC-10: Suites green | Pass | 14 Fable tests failed on `main` before this plan; S5-F10's 6 already passed, as recorded at planning. On `main` after the merge: **pytest 1473 passed**, **swift test 108 passed**. |

## Task Commits

| Task | Commit | Worker | Description |
|------|--------|--------|-------------|
| 1: identity + ledger | `2739735`, `eeb8272` | Opus subagent (high); conftest added by the coordinator | `same_process`, owner block, orphan settle and keep, stop command derived from the port |
| 2: start/stop | `ae04650` | Sonnet subagent (high) | early ledger write, `_REAPED_PIDS`, every-port refusal, `~/Applications`, quickbench abort |
| 3: download lock | `f9050e8` | Sonnet subagent (medium) | lock records identity, young empty lock held |
| 4: Swift kill | `e6756e0` | coordinator | `kill`/`forceKill` guards and a test |
| Integration | `c30614b` | coordinator | deleted `_RUN_STARTED_PIDS`; reaped-pid state reset per test |
| Review fixes | `b014ffd` | coordinator | see Deviations |
| Merge | `251090d` | — | `fix/05-09-int` merged into `main` |

## Deviations from Plan

**Review fixes.** The two-axis review was done by an Opus subagent, and every finding was verified against the code before it was fixed.

1. **High (spec, S5-F5).** oMLX, vMLX and MTPLX start as `/bin/sh <script>` and `exec` Python. The identity recorded right after the spawn therefore carried the shell's argv. Both Stop now during a load and a later launch's sweep would then refuse the engine as a stranger. The reviewer reproduced this with a scratch shim. **Fix:** `same_process` compares the start time only and keeps argv for the reader. `exec` keeps the pid and the start time, and a reused pid has a later start time. New test: `test_same_process_holds_across_an_exec_that_changes_argv`.
2. **Medium (metric).** AC-5's subtraction made `cold_load_s` read too low, because the engine keeps loading while the ledger is written. Settling a predecessor's file inside the window could make a 4 s load read about 0 s. **Fix:** no subtraction. The early write is one `ps` plus a file. `_adopt_ledger()` settles a predecessor's file before the clock starts. The old test pinned the wrong model and was replaced by `test_settling_an_earlier_processs_ledger_is_outside_cold_load_s`. The plan's AC-5 carries a `review-amended` note.
3. **Medium.** An Osaurus load killed mid-way left an entry naming only the launcher, and the app on the port was dropped as a stranger with no message. **Fix:** dropping an entry because of a stranger on its port now emits one `running_engine_ledger` line naming the pid. The app itself is still never signalled, since it could be the user's own. The resident-app check then refuses every start and names it.
4. **Low.** `_REAPED_PIDS` was also filtering pids that `ps` had listed. `_resident_osaurus_pids` now trusts the `ps` listing.
5. **Low.** A reaped launcher's pid could be given an identity on the second write. **Fix:** a pid in `_REAPED_PIDS` is recorded with no identity.
6. **Low (doc).** `v5-app.md` still said Stop now does nothing before the entry exists. That sentence is replaced.

**Outside the plan's file list:**
- `tests/conftest.py`: an autouse reset of `runtimes._OWN_IDENTITY` and `_REAPED_PIDS`, so module state cannot leak between tests. This was the worker's flagged concern.
- `_RUN_STARTED_PIDS` deleted: after AC-8 nothing read it. This touched `tests/test_fable_s5_f2.py` (one fixture), `test_fable_s5_f3.py` (fixture and one precondition assertion about the deleted set), `test_fable_s5_f14.py` and `test_runtimes.py` (one `setattr` each).
- `app/Tests/OhYesMLXKitTests/LauncherTests.swift`: `FakeLauncherProcess.markExitedWithoutTermination()` helper.

**Red-test corrections.** Each falls under one of the four allowed kinds, and none weakens its finding.

| Test | Kind | Correction |
|------|------|------------|
| S1-F1 `test_a_stale_own_pid_entry_survives_the_next_engine_start` | control pinning the defect | Inverted to `..._is_not_merged_into_the_next_engine_start`. |
| S5-F5 `test_a_load_interrupted_before_readiness_leaves_an_engine_no_launch_recovers` | control pinning the defect | Inverted to `..._the_next_launch_recovers`. |
| S5-F5 rig | clash with design | Uses `_read_ledger` and seeds `_OWN_IDENTITY`. |
| S5-F13 and S5-F10 Stop now tests | clash with design | The ledger file carries an owner block, because Stop now reads only its own file. |
| S1-F2 lock test | clash with design | Reads the lock as JSON through `fetch._read_lock`. |
| S5-F3 test 2 | clash with design | Its precondition on `_RUN_STARTED_PIDS` was removed together with the set. |

The `tests/test_runtimes.py` assertions that stated the old ledger shape, the old drop behaviour or the old refusal text were updated to the new contract. Task 1 renamed three tests from `*_dropped` to `*_kept`.

## Deferred

| Item | Why it is safe to defer |
|------|-------------------------|
| A kept, unprovable orphan file is retried and reported at every launch, and is never pruned | Bounded and visible. An expiry would bring back silent dropping, which S5-F4 forbids (audit deferral 1; review finding 6). |
| A legacy bare-pid `download.lock` held by a same-user recycled pid still wedges the lock | Only files from before 05-09; deleting the file by hand recovers (audit deferral 2). |
| S3-F16: a microsecond window remains between checking `isRunning` and sending `kill` | `Process` has no pidfd (audit deferral 3). |
| `FoundationLauncherProcess.kill`'s own guard is not tested in isolation | The test goes through the fake; the session-level guard is tested. |

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| A flaky Swift test, `LauncherTests.testEOFBeforeTheLaunchLineIsCouldntStartWithTheStderrTail`: it fails about 1 run in 6, on the base branch as well, from a race between the stderr reader and stdout EOF | Not caused by this plan. Recorded here and in STATE for a later plan. |

## Next Phase Readiness

**Ready:** plan D (05-10). The live Phase 5 checks (Stop now, a real download) can now also exercise a Stop now during a load.

**Concerns:**
- AC-8 now refuses a start while anything listens on 8000, 8080, 8081, 8100, 8200 or 1337, including an unrelated dev server. That is intended, and Jason should know it.
- The S5-F2 constant is still unmeasured (STATE Deferred Issues).

**Blockers:** none.

---
*Phase: 05-app, Plan: 09 · Completed: 2026-11-16*
