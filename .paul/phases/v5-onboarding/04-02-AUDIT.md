# Enterprise Plan Audit Report

**Plan:** .paul/phases/v5-onboarding/04-02-PLAN.md
**Audited:** 2026-11-02
**Verdict:** conditionally acceptable (acceptable for APPLY with the upgrades below applied)

---

## 1. Executive Verdict

Conditionally acceptable. The plan keeps the one property that matters for the first machine-changing endpoints:
the server passes a validated NAME and a literal `true` to module functions that already own consent, locks,
rollback and verification, and adds no rule of its own. Two defects in the plan as written would have shipped
real harm. First, the stream design told the implementer to clear the socket timeout, which lets any client that
connects and stops reading hold a server thread forever. Second, install was declared not cancellable while a
guided install polls for up to 600 s and a pip step can run 900 s; one abandoned "Install Osaurus" click would hold
the single job slot for ten minutes, and app shutdown would orphan a running pip with no rollback and no record
of it. With the must-have upgrades applied I would approve it.

## 2. What Is Solid

- **Names, not commands.** `args` is a closed set of keys and types, and `confirmed` must be JSON `true`; a
  request cannot name a path, URL, command or version, so the module allowlists are the only allowlists.
- **Refuse before reading.** Content-Type and Content-Length are checked before the body is read; nothing starts
  a thread before validation completes.
- **One job slot.** It matches Decision 138's single download lock and keeps disk accounting honest.
- **Streams always end.** A raising module still produces `error` + `done` with continuing `seq`.
- **The 04-01 guard is untouched** and runs first on every job route.
- **The manual check uses a scratch cache and installs nothing.**

## 3. Enterprise Gaps Identified

1. Clearing the socket timeout for SSE makes a non-reading client a permanent thread leak.
2. Install not cancellable: a guided install holds the slot for its 600 s poll window; shutdown mid-install
   orphans pip.
3. `confirmed: true` is not evidence of a human decision; the plan did not say who owns that guarantee.
4. Job end left no trace; only starts were logged, so an outcome could not be reconstructed from stderr.
5. `Last-Event-ID` edge values (negative, non-numeric, beyond the last seq) unspecified.
6. The residual risk of a pip step outliving the server was not written down anywhere.
7. Unbounded concurrent stream readers per job (each a thread).
8. Jobs are never removed from the registry.

## 4. Upgrades Applied to Plan

### Must-Have (Release-Blocking)

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | SSE thread leak from a cleared socket timeout | AC-4, Task 2 action, Task 2 tests | Socket timeout stays set and bounds each write; waits are on the condition; a never-reading client is dropped (test) |
| 2 | Install holds the slot, orphans on shutdown | AC-5, AC-6, Task 1 action, boundaries, files_modified | `engines.install(cancel=...)` checked between steps and guided polls, through the existing rollback; cancel and shutdown use it; tests in test_engines.py |

### Strongly Recommended

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | `confirmed` is a client statement | AC-1 | Stated in the AC and in docs/interfaces.md; Phase 5 must send it only from a user gesture |
| 2 | No job-end trace | AC-6 | One stderr line per job end: id, ok, code, time |
| 3 | Last-Event-ID edges | AC-4 | Non-integer or negative is 400 `bad_event_id`; beyond-last waits |
| 4 | Residual pip-orphan risk unrecorded | AC-6 | Written into docs/interfaces.md; owned by Phase 4.5 |

### Deferred (Can Safely Defer)

| # | Finding | Rationale for Deferral |
|---|---------|----------------------|
| 1 | Cap concurrent stream readers per job | Token-gated, loopback only; each thread is now bounded by the write timeout. Phase 4.5 |
| 2 | Registry never prunes finished jobs | A job is a few KB and one app session runs a handful; restart clears it |
| 3 | Killing a running pip step on cancel | Interrupting pip mid-install risks a worse half-state than waiting for its step boundary; the 900 s step timeout already bounds it |

## 5. Audit & Compliance Readiness

- **Evidence:** red-checks named per guard; a scratch-cache download and evict streamed to `done` with the real
  cache listed before and after.
- **Silent failures:** module exceptions, event overflow, cancel and shutdown all end the stream with `error` and
  `done`; the module logs (install log, fetch log, ledger) remain the durable record.
- **Reconstruction:** stderr start and end lines per job, plus the modules' own logs.
- **Ownership:** coordinator verifies; Jason approves at the checkpoint; Phase 4.5 owns the residual risks above.

## 6. Final Release Bar

Before this ships: AC-1..AC-7 green with red-checks, the scratch-cache run pasted, the real cache unchanged.
Remaining risk if shipped: a pip step that is mid-run when the 120 s shutdown wait expires can outlive the server
without rollback (documented), and any holder of the token can submit consented jobs (by design; the token is the
boundary). I would sign this.

---

**Summary:** Applied 2 must-have + 4 strongly-recommended upgrades. Deferred 3 items.
**Plan status:** Updated and ready for APPLY (after 04-02b lands)

---
*Audit performed by PAUL Enterprise Audit Workflow*
*Audit template version: 1.0*
