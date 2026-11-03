---
phase: 045-security
plan: 01
completed: 2026-11-03
duration: one session (~3 h including audit)
description: "045-01: threat model of the v5.0 backend; 6 medium + 10 low findings verified, none high; carried items dispositioned; Phase 5 checklist"
type: Summary
about: "OhYesMLX"
status: UNIFIED 2026-11-03
---

# 045-01 Summary

`docs/threat-model.md` holds the full review. The detail of each unfixed medium finding is in
`045-01-findings-private.md`, which is gitignored (AC-5b).

## Delivered

- Inventory of every entry point, with a grep reconciliation (102 hits over 11 modules, none unaccounted for).
- Assets, actors, trust boundaries and a severity rubric.
- Live probes against a scratch-HOME `ohyesmlx app`. Every guard held. The digest of the real Application
  Support, HF cache and Osaurus config was identical before and after (`7962e8c2…`).
- Two read-only review passes (server, installers). Every finding was verified against the code; two worker
  severities were changed (S1 high → medium, F5 medium → low).
- Every carried item and audit deferral has one disposition. Phase 5 checklist P5-1 to P5-12.

## Approved for 045-02

| Id | Severity | One line |
|---|---|---|
| T-01 | medium | installer (pip). Detail in the private file |
| T-02 | medium | app lifecycle: interrupted jobs. Detail in the private file |
| T-03 | medium | writable paths. Detail in the private file |
| T-04 | medium | server job registry. Detail in the private file |
| T-05 | medium | quickbench Osaurus pin. Detail in the private file |
| T-06 | medium | fetch ledger. Detail in the private file |
| T-07 | low | `-I` for the venv step, `--isolated` for pip |
| T-08 | low | Cap concurrent handler threads and per-job streams |
| T-09 | low | Absolute paths for `ps`/`sysctl`/`sw_vers`/`ioreg`/`open`; timeout on `hardware._run` |
| T-10 | low | Application Support created `0700` |
| T-11 | low | The refusal log names the route, never the raw path |
| T-12 | low | Validate `lab-paths.json` values; `mkstemp` for its temp file |
| T-13 | low | `evict` containment per repo directory |
| T-16 | low | Snapshot-conflict check before the transfer |

Not for 045-02: T-14 (accepted), T-15 (checklist P5-7).

## Proposed checklist lines

P5-1 to P5-12, in `docs/threat-model.md` section 10.

## Triage

Jason approved the table above, the dispositions in `docs/threat-model.md` §7.3 and §8, and checklist P5-1..P5-12 unchanged (2026-11-03). T-01 stays medium (worker rated high).

## Acceptance criteria

| AC | Result | Evidence |
|---|---|---|
| AC-1 Entry points and grep | PASS | threat-model §5.1-5.7: 102 hits across 11 modules, all reconciled |
| AC-2 Assets, actors, boundaries | PASS | threat-model §2-4, with out-of-scope actors and their reasons |
| AC-3 Findings verified, rubric | PASS | §7.1 rubric. Every worker claim checked in the code: two severities changed, one claim corrected (T-07 user site-packages) |
| AC-4 Carried items and deferrals | PASS | §8: one row each. UAT-001 accepted. Clean-account smoke → 045-03 |
| AC-5 Phase 5 checklist | PASS | §10 P5-1 to P5-12, each traced to a finding |
| AC-5b No early disclosure, no token | PASS | Unfixed medium detail only in the gitignored private file (`git status --ignored` shows `!!`). No token-shaped string in the repo or the logs. The probe script asserted the token was absent from its output |
| AC-6 Jason approves triage | PASS | Approved unchanged, 2026-11-03 |

## Verification

- `pytest -q`: 1164 passed (no code changed).
- Real-state digest `7962e8c2…207a` before and after the probes. The scratch HOME was deleted.
- No listener was left on the probe port (`lsof`).
- `git diff --stat` touches only planning and doc files, plus `.gitignore`.
- Deviation at commit: the worker logs were in the first local commit and were removed by amend before any push. They are gitignored until 045-02 (AC-5b).

## Files

| File | Change |
|---|---|
| `docs/threat-model.md` | Created: the full review (458 lines) |
| `.gitignore` | Added an entry ignoring the private findings file |
| `.paul/orders/v5-sec-45-{server,installers}.md` | Created: review orders. The `.log` worker reports are gitignored until 045-02, because they carry unfixed detail |
| `.paul/phases/v5-onboarding/045-01-{PLAN,AUDIT,SUMMARY}.md` | Created |
| `.paul/phases/v5-onboarding/045-01-findings-private.md` | Created, local only, gitignored |
| `.paul/STATE.md`, `.paul/ROADMAP.md`, `.paul/phases/v5-onboarding/PLAN.md` | Updated position |

## Deviations

- **The probe script needed two fixes after TCP resets.** Python's `socketserver` listen backlog is 5, so rapid
  connects get reset. The resets are now counted rather than fatal, and this is recorded under T-08. No AC changed.
- **A held SSE stream on a running job was not probed live.** Every long-running job kind reaches real binaries or
  the network, so this was reviewed from the code (T-08). This was planned as a probe and reported in §6.
- **The snapshot-conflict carried item had no written definition in the records.** It was read from the code as
  "the conflict is found only after the transfer" (T-16).

## Decisions

- No finding is high. S1 (pip without hashes) is medium, because exploiting it needs a compromised maintainer
  account on a pinned dependency, and PyPI files cannot be replaced once uploaded. Jason approved.
- A same-user-only finding that gives that process nothing beyond editing the user's files is rated low (§3, §7.1).

## Next

045-02 TDD fixes: T-01 to T-13 and T-16 (14 items, so likely split into server/lifecycle and installer/fetch
plans), each moving its private detail into §7 in the commit that fixes it. Then 045-03 (clean-account smoke).
