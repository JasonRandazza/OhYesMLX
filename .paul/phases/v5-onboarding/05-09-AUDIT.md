# Enterprise Plan Audit Report

**Plan:** .paul/phases/v5-onboarding/05-09-PLAN.md
**Audited:** 2026-11-16
**Verdict:** conditionally acceptable (upgrades applied; ready for APPLY)

---

## 1. Executive Verdict

Conditionally acceptable. The plan's core design is right: one identity check, called by every place that signals or
reclaims. As first written, it had four latent holes. Each would have reproduced the class of bug the plan exists to
close: a claim on a live engine being lost, or a second definition appearing. It also had one execution trap: a task's
own verify step could never pass. With the upgrades below applied, I would approve it.

## 2. What Is Solid

- The single shared `same_process` check. It follows AGENTS.md's "one definition" rule, and the plan asks for a grep
  that proves no second comparison remains.
- The derived stop command (S5-F13) is a deletion that removes an exec primitive from disk data. It does not add a
  validator.
- AC-7 puts the reaped-pid fix inside `_process_alive`, the function every caller already goes through. That fixes the
  root cause, not just one caller.
- The red-check was done before planning. S5-F10 is recorded as already closed, and the tests that pin the defect are
  named in advance. The plan says they are inverted, never deleted.
- `cold_load_s` keeps the 05-07 AC-4 contract: the ledger write is timed and subtracted, with a test.
- `app.lock` is explicitly left alone. It is an flock, so the pid-liveness question does not apply to it.

## 3. Enterprise Gaps Identified

1. **Two liveness definitions.** AC-1 introduced an "EPERM means not ours" rule beside `_process_alive`'s
   "EPERM means alive". The plan did not say how they relate, and that is the kind of drift AGENTS.md forbids.
2. **A stale own-pid file in a CLI run would be dropped silently.** AC-2 said `_record_running_engine` "starts fresh".
   A CLI grid never runs the startup sweep, so starting fresh would delete the only claim on a live orphan engine.
   That is the same harm S5-F4 describes.
3. **A failed start would leave its early ledger entry behind.** AC-5 writes the entry before readiness, but the plan
   did not say what happens to it when the start fails. The entry must be dropped when cleanup succeeds and kept when
   it fails.
4. **Quickbench ending the run on a `RuntimeStopError` must still restore Osaurus.** That is a standing rule (the
   byte-exact restore). The `finally` paths exist (`quickbench.py:732`, `:968`), but nothing in the plan tested them on
   the new abort path.
5. **Task 1's verify could never pass.** It copies `test_fable_s1_f2.py` whole, and that file's lock test belongs to
   Task 3, so "full suite green" was impossible.
6. **The AC-8 refusal message.** `_port_is_free` reads an unreadable port as busy, so a message saying "held by a
   listener" could be false. The message should also name the `lsof` command, as `await_port_free` already does.
7. **No back-compat test for pre-05-09 ledger files.** Files with `stop_command` and no `owner` exist on disk today,
   and nothing covered loading them.
8. **The AC-3 report line.** It should say which reason applied (port unreadable, or identity unproven), so a kept file
   can be explained from the log alone.
9. **Tasks 2 and 3 run in parallel.** They need serial merges into the integration branch, with a full suite run after
   each.

## 4. Upgrades Applied to Plan

### Must-Have (Release-Blocking)

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | Two liveness definitions | AC-1 | `same_process` calls `_process_alive`, then the this-user check, then identity. `fetch._pid_alive` is deleted. The docstring explains the EPERM difference. Own identity is cached. |
| 2 | A stale own-pid file is dropped silently in a CLI run | AC-2 | Its entries go through the orphan handling (stop if proven, keep and report if not) before this process writes its own file. |
| 3 | A failed start leaves its early ledger entry | AC-5 | Forget the entry when cleanup succeeds, keep it when cleanup fails. Tested both ways. |
| 4 | The abort path must still restore Osaurus | AC-8 | The run ends through the existing `finally` restore. A test asserts the restore ran. |
| 5 | Task 1's verify was impossible | Task 1 verify | It deselects exactly the Task 3 lock test, by node id, and says so. |

### Strongly Recommended

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | Refusal message accuracy | AC-8 | Name the `lsof` command. An unreadable port must not be described as a listener. |
| 2 | Back-compat of old ledger files | Task 1 action | A test loads a pre-05-09 file through both the sweep and Stop now. |
| 3 | Reason on the kept-orphan line | AC-3 | The stderr line names which reason applied. |
| 4 | Parallel merge discipline, and never touching the real ledger or lock | Verification | Serial merges with a full run after each, and an explicit check that no test reaches the real Application Support. |

### Deferred (Can Safely Defer)

| # | Finding | Rationale for Deferral |
|---|---------|----------------------|
| 1 | A kept, unprovable orphan file is retried and reported at every launch, with no expiry | The cost is bounded and visible (one stderr line per launch). An expiry would reintroduce a "drop the claim" path, which is what S5-F4 forbids. Revisit if it is seen in the wild. |
| 2 | A legacy bare-pid `download.lock` whose same-user pid was recycled still wedges | Only lock files written before 05-09 have no identity, and the EPERM rule already covers the reboot case. Deleting the file by hand recovers. |
| 3 | S3-F16: a time-of-check/time-of-use gap remains between `isRunning` and `kill` | Foundation's `Process` exposes no pidfd. The guard closes everything except a window of microseconds, which matches the finding's stated fix direction. |

## 5. Audit & Compliance Readiness

- **Evidence:** every finding has a red test that is copied and must fail on `main` (or is recorded as already green),
  and the coordinator runs both suites. That evidence is defensible.
- **Silent failures:** the plan converts three silent drops into reported keeps (S5-F4, the CLI stale file, a failed
  cleanup). After the upgrades, no remaining path deletes a claim without a line in the log.
- **Reconstruction:** each ledger file now names its owner's identity, and each kept entry says why it was kept. An
  incident can be traced from the files on disk and stderr.
- **Ownership:** each task names its worker, its model and effort, its files, and the merge order.

## 6. Final Release Bar

- **Must be true:** AC-1..AC-10, including the audit-added clauses; both suites green and observed by the coordinator;
  a single identity comparison, proven by grep; the Osaurus restore exercised on the abort path.
- **Remaining risks if shipped:** the three deferred items above, all bounded and visible.
- **Sign-off:** yes, with the upgrades applied.

---

**Summary:** Applied 5 must-have + 4 strongly-recommended upgrades. Deferred 3 items.
**Plan status:** Updated and ready for APPLY

---
*Audit performed by PAUL Enterprise Audit Workflow*
*Audit template version: 1.0*
