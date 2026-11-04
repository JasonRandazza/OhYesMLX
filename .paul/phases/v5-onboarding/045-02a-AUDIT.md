# Enterprise Plan Audit Report

**Plan:** .paul/phases/v5-onboarding/045-02a-PLAN.md
**Audited:** 2026-11-03
**Verdict:** conditionally acceptable. Ready for APPLY with the upgrades below applied.

---

## 1. Executive Verdict

Conditionally acceptable. The plan fixes the right findings, test-first, and the AC-1 guarantee that paths stay
byte-identical in the checkout is the correct protection for published work. Three defects would have shipped new
harm while fixing old harm:

- the orphan-engine ledger write would have landed inside the `cold_load_s` measurement;
- startup recovery would have restored Osaurus files while the Osaurus app could overwrite them;
- the "same argv" test for a leftover process would have signalled a user's own identically-launched server
  after a pid reuse.

With these fixed, I would approve it.

## 2. What Is Solid

- **The writable root keeps every checkout path byte-identical (AC-1).** No published run, canary or drift-guard
  baseline moves. The packaged case is tested by simulating a missing `.git` on a read-only tree.
- **An orphan stop never touches a process whose owner is alive.** A grid running from the CLI is safe from the
  app.
- **`.incomplete` files are no longer swept.** That correctly protects fetch's resume state, against a fix
  045-01 had proposed.
- **Disclosure moves in the fix commit (AC-8),** and T-01 and T-06 stay withheld until 045-02b.
- **Two sequential orders,** because the files overlap, and the coordinator red-checks each guard.

## 3. Enterprise Gaps Identified

1. **The ledger write was inside a measured interval.** `runtimes.Runtime.start` computes
   `cold_load_s = _now() - started` at `runtimes.py:2012`, *after* `_RUN_STARTED_PIDS.add(pid)` (`2003-2005`), so
   writing the ledger there adds file I/O to every published cold-load number. This is the project's core
   measurement; no security fix may touch it.
2. **Startup recovery raced the Osaurus app.** quickbench refuses to pin while the app runs, for exactly this
   reason (`quickbench.py:175-202`). Recovering at app launch while Osaurus is open repeats the hazard 04-03a
   deferred.
3. **A pid can be reused.** Owner-dead plus identical argv is not identity: a user who starts the same
   `mlx_lm.server …` command after a crash would be killed. The start time is what makes the match safe, and
   `ps -o args=` truncates without `-ww`.
4. **One shared ledger file for many processes** races its read-modify-write. A lost entry fails safe, but a
   resurrected one is a stale kill candidate.
5. **The thread-cap slot release was unspecified.** A semaphore that leaks on the exception or timeout paths
   becomes a self-inflicted outage.
6. **Order files carry fix detail.** Their commit timing was not tied to the fix commit.
7. **The thread cap leaves a residual availability risk.** A local account filling 32 slots delays the app's own
   requests. This is acceptable now that T-04 cannot make it permanent, but it must be recorded.

## 4. Upgrades Applied to Plan

### Must-Have (Release-Blocking)

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | Ledger write inside `cold_load_s` | AC-6, verification | The write must follow the timestamp. A call-order test, plus a read of the diff |
| 2 | Startup recover vs a running Osaurus app | AC-6, verification | Recover only when the app is not running; otherwise a `recovery_pending` line, and the backup is kept. A recover failure never blocks startup |
| 3 | Pid reuse | AC-6, live check (b) | The process start time is recorded with argv (`ps -ww -o lstart=,args=`). Both must match before any signal. The live check covers the wrong-start-time case |

### Strongly Recommended

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | Shared ledger race | AC-6 | One file per owner pid under `results/running-engines/` |
| 2 | Semaphore release | AC-3 | Released on every handler exit. A test with N+1 timed-out connections then gets a 200 |
| 3 | Order commit timing | Task 1 | Each order and its log are committed with their fix, after a token scan |
| 4 | Residual availability risk | Output | §9 row |

### Deferred (Can Safely Defer)

| # | Finding | Rationale for Deferral |
|---|---------|----------------------|
| 1 | Reserving a handler slot for the token holder | It needs authentication before the thread starts, which a stdlib handler cannot do cheaply. The 10 s timeouts bound the delay, and T-04 is closed |
| 2 | Log rotation for `install-log.jsonl` and `fetch-log.jsonl` | Each line is small and a session writes a handful. Revisit with Phase 5 diagnostics |

## 5. Audit & Compliance Readiness

- **Evidence.** Every AC has a red-checked test. The live checks (a) and (b) run on a scratch HOME with their
  output pasted. The probe re-run shows the thread cap holding.
- **Silent failures.** The recovery outcomes (recovered, pending, failed) each produce a stderr line, and a
  dropped ledger entry is logged rather than signalled.
- **Reconstruction.** Per-owner ledger files show what was running and who started it.
- **Ownership.** The coordinator verifies each worker diff. Jason reviews at code-review and `/paul:verify`.

## 6. Final Release Bar

What must be true before shipping:

- AC-1 to AC-8 green, with red-checks.
- Checkout paths unchanged.
- No ledger I/O inside `cold_load_s`.
- Live checks done on scratch only.
- Private detail for T-02 to T-05 published in the commits that fix them.

What remains: availability under local-account connection flooding, bounded by timeouts and recorded. I would
sign off on the plan as amended.

---

**Summary:** Applied 3 must-have + 4 strongly-recommended upgrades. Deferred 2 items.
**Plan status:** Updated and ready for APPLY

---
*Audit performed by PAUL Enterprise Audit Workflow*
*Audit template version: 1.0*
