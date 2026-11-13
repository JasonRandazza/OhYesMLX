# Enterprise Plan Audit Report

**Plan:** .paul/phases/v5-onboarding/05-01-PLAN.md
**Audited:** 2026-11-13
**Verdict:** conditionally acceptable → acceptable after the applied upgrades

## 1. Executive Verdict
Approvable once the race between the external engine stop and the cell's own stop path is specified. As written
the plan stopped the engine from the HTTP request thread and assumed the cell's `finally: handle.stop()` would
succeed afterwards; a second stop that raises would have turned a user's "Stop now" into an `error` ending, which
is the one ending that skips nothing but reads as a defect.

## 2. What Is Solid
- The abort works by stopping the engine from outside, so `measure.py` is untouched: no published-table code path changes.
- `stop_own_engines` reads only this process's ledger file: it cannot reach a CLI grid's engines or another account's.
- The ABORTED record carries no figures, and raw rows stay on disk: no number from a half-measured cell can be shown.
- The bodyless cancel and every existing refusal keep their order: the shipped contract is not reopened.

## 3. Enterprise Gaps Identified
1. A second stop (`handle.stop` after the abort's `_shutdown`) can raise `RuntimeStopError`; unhandled, the run ends `error`.
2. `_shutdown` can take TERM_GRACE + KILL_GRACE + the port wait; doing it in the request thread holds the 202 for tens of seconds and invites a client timeout and a retry.
3. A repeated "Stop now" (double click, client retry) would run two concurrent `_shutdown`s on one port.
4. The live verification line launched a measurement without asking Jason first (standing rule: confirm before measuring).
5. No stderr audit line for the abort itself (the job's end line records `cancelled`; the summary records ABORTED).
6. The abort window before the ledger entry exists degrades to "after this cell, number discarded" — documented, acceptable.

## 4. Upgrades Applied to Plan

### Must-Have (Release-Blocking)
| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | Second stop / any raise during an abort must still end `cancelled` with restore + eviction | AC-7 (new), Task 1 done | AC-7 with a fake measure_cell raising RuntimeStopError after abort |

### Strongly Recommended
| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | Stop runs on a daemon thread; 202 answers at once | AC-7, Task 2 action, v5-app.md | Blocking fake stop test; spec text updated |
| 2 | One stop per job | AC-7, v5-app.md | Second `now` answers 202, starts nothing |
| 3 | Ask Jason before the live check | verification | Wording added |

### Deferred (Can Safely Defer)
| # | Finding | Rationale for Deferral |
|---|---------|----------------------|
| 1 | Separate stderr line for an abort | The end line (`code: cancelled`) and the summary's ABORTED cell already reconstruct it; a new line changes a pinned log shape for no new information |
| 2 | Closing the pre-ledger window | Worst case is documented and safe (number discarded); closing it needs a start-time hook in `runtimes`, out of proportion |

## 5. Audit & Compliance Readiness
Evidence: the summary JSON (ABORTED cell, `ended: cancelled`), raw rows, the job end line. No silent failure path
remains once AC-7 holds: a failed stop is a stderr line, never a swallowed one.

## 6. Final Release Bar
Ships when AC-1..AC-7 pass red-checked and one live "Stop now" (with Jason's go-ahead) shows the port freed and
the Osaurus pin restored byte-exact. Remaining risk: the pre-ledger window. I would sign it with AC-7 in place.

---
**Summary:** Applied 1 must-have + 3 strongly-recommended upgrades. Deferred 2 items.
**Plan status:** Updated and ready for APPLY
