# Enterprise Plan Audit Report

**Plan:** `.paul/phases/v5-onboarding/05-08-PLAN.md`
**Audited:** 2026-11-16
**Verdict:** Conditionally acceptable. The upgrades below are applied, and the plan is ready for APPLY.

## 1. Executive Verdict
The plan is conditionally acceptable. Its fixes target the right owners: the slot is freed when the job thread
returns, and the lock is held by the process that does the work. But three of its designs, as first written, would have
traded each defect for a new one. Two of those would strand a user with no recovery short of a terminal. All three are
fixed in the plan.

## 2. What Is Solid
- Every finding with a red test reuses it. The corrections rule matches 05-07's, where it worked.
- S1-F5 and S1-F6 are fixed at one site in `server.py`, not twice in `fetch.py` and `server.py`.
- The one High stays with the coordinator, and Swift tasks run one at a time.
- No live engines, downloads or Command Code. The live checks are kept as a separate step that needs Jason's go-ahead.

## 3. Gaps Identified
1. **A crashed app would lock the user out (AC-12).** Once the backend owns the lock, an orphaned backend that is still
   unwinding makes the next launch refuse. The launcher would map that refusal to "already running" and exit, even though
   no app is running. The user sees nothing and cannot start the app.
2. **An orphaned engine could hold the lock forever.** A lock descriptor inherited by a spawned engine server would keep
   `app.lock` locked after the backend dies.
3. **The lock path could split in two.** If the backend derived the path independently of the launcher, a test or scratch
   launch could lock the real `app.lock`, or two copies of the path rule could drift apart.
4. **`done` before the slot frees would leave a busy window (AC-14).** After S3-F5 the app starts its next job as soon as it
   sees `done`. If the slot is freed after `done` is published, that start is refused `busy`. The plan would have
   turned a hidden race into a user-visible one.
5. **The SSE splitter could break characters.** Splitting decoded text per chunk mangles a multi-byte character that
   arrives across two chunks.
6. **A screenshot was unreachable.** The plan asked for a quit-banner screenshot, but no stub scenario reaches it.
   Adding one is a new surface.
7. **No Swift baseline was recorded,** so "nothing else went red" could not be shown.

## 4. Upgrades Applied to Plan

### Must-Have
| # | Finding | Section | Change |
|---|---|---|---|
| 1 | Crashed app locks the user out | AC-12, Task 4 | The refusal carries the holder pid. A new `.stillFinishing` outcome with **Check again** is shown when no other app instance is running |
| 2 | Inherited lock descriptor | AC-12, Task 4 | The lock fd is non-inheritable, asserted by a test |
| 3 | `done` before the slot frees | AC-14, Task 2 | `done` is held and published only after the slot is freed. A test starts a second job from `done` and gets 202 |

### Strongly Recommended
| # | Finding | Section | Change |
|---|---|---|---|
| 1 | One lock path | AC-12, Task 4 | The path comes from `app_support_dir()` plus the launcher's directory. Scratch launches never touch the real one |
| 2 | UTF-8 split across chunks | AC-1 | Split on bytes and decode whole lines. A test covers a 3-byte character split across chunks |
| 3 | Unreachable screenshot | Verification, Task 3 | Screenshots use existing scenarios only; AC-10 is proven by the model test |
| 4 | Swift baseline | Verification | Measured on `main` before Task 1 |

### Deferred
| # | Finding | Rationale |
|---|---|---|
| 1 | Measuring how long a real backend takes to unwind, to size the **Check again** copy | Needs a live job, which belongs to the live Phase 5 checks session |

## 5. Audit & Compliance Readiness
- **Evidence:** each fix has its red test, red on `main` and green on the branch, and the coordinator runs both
  suites and takes the screenshots.
- **Silent failures:** the plan removes the biggest one, a stream that never dispatches, and with the must-haves applied
  it adds no new ones.
- **Ownership:** Task 4 writes the lock owner into `docs/interfaces/v5-app.md` P5-7, its one definition.

## 6. Final Release Bar
Before this ships: all copied Fable tests green, both suites green on the coordinator's run, the lock handoff and the
splitter read line by line, and screenshots taken. The risk left is that the live behaviour of the new lock and the real
stream is proven only by tests until the live checks run. I would sign it with the upgrades applied.

---
**Summary:** Applied 3 must-have + 4 strongly-recommended upgrades. Deferred 1.
**Plan status:** Updated and ready for APPLY.
