# Enterprise Plan Audit Report

**Plan:** .paul/phases/v5-onboarding/04-03a-PLAN.md
**Audited:** 2026-11-02
**Verdict:** conditionally acceptable (ready for APPLY with the upgrades applied)

## 1. Executive Verdict
Conditionally acceptable. The plan moves the Osaurus pin from shell into one Python definition, which is the right
direction for a packaged app, but as written a crash between pin and restore would strand a user's Osaurus
settings permanently: the "second pin refuses while a backup exists" rule, correct on its own, would then block
every later run with no recovery path. Config writes were not atomic, so a kill mid-write could corrupt the user's
Osaurus config. Adding `quick` to `PIN_FIELDS` could also break every existing join if an absent key and `false`
compared unequal. With the must-haves applied I would approve it.

## 2. What Is Solid
- One definition of the pin, called by both quickbench and the shell runner; the shell keeps its trap and cmp.
- Refusal on the value of `quick`, not on a mismatch, so two quick runs cannot join each other either.
- Tests confined to scratch config dirs; no measured run without Jason's go.
- `siblings` derived from data, not from title parsing at request time.

## 3. Enterprise Gaps Identified
1. No crash recovery between pin and restore; the refuse-on-existing-backup rule makes it permanent.
2. Non-atomic config writes.
3. `quick` absent vs false could break all existing joins.
4. Hand-entered `base` values had no test that would catch a wrong one.
5. Pin and restore left no record.

## 4. Upgrades Applied to Plan

### Must-Have
| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | Stranded settings after a crash | AC-3, Task 3 | `recover()` restores from a leftover backup, byte-exact; 04-03b calls it before any pin; tests |
| 2 | Non-atomic writes | AC-3, Task 3 | temp file + `os.replace`; backup dir 0700; interrupted-write test |
| 3 | Absent vs false `quick` | AC-2 | false equals absent; a test joins two pre-04-03a fixtures |

### Strongly Recommended
| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | Wrong hand-entered `base` | AC-1 | a test pins every base and its rows |
| 2 | No record of pin/restore | AC-3 | one JSON line each, names and outcome only |

### Deferred
| # | Finding | Rationale |
|---|---------|-----------|
| 1 | The Osaurus app may rewrite its own config while running, racing the pin | Same exposure the harness has run under since 2026-09-25 with byte-exact restores; 04-03b's checkpoint verifies with cmp; Phase 4.5 |
| 2 | A user's own Osaurus edit made during the run is overwritten by restore | Documented in docs/interfaces.md by 04-03b; the run is minutes long and consented |

## 5. Audit & Compliance Readiness
Byte-exact verification is the evidence; recovery and atomic writes prevent the silent, persistent failure the
plan would otherwise have allowed; one log line per pin/restore supports reconstruction.

## 6. Final Release Bar
AC-1..AC-3 green with the audit tests; the shell runner round-trips a scratch copy. Remaining risk: the
Osaurus-app config race, deferred and verified per run.

**Summary:** Applied 3 must-have + 2 strongly-recommended upgrades. Deferred 2 items.
**Plan status:** Updated and ready for APPLY
