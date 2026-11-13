# Enterprise Plan Audit Report

**Plan:** .paul/phases/v5-onboarding/05-02-PLAN.md
**Audited:** 2026-11-13
**Verdict:** conditionally acceptable → acceptable after the applied upgrades

## 1. Executive Verdict
The model/launcher split is right, but the plan under-specified the child process's pipes and its death. A
launcher that reads the launch line and then stops reading stderr wedges the backend the first time it logs
64 KB; a launcher that never notices the child exiting leaves the UI pointing at a dead port. Both are now ACs.

## 2. What Is Solid
- Every packaging rule the client owns (P5-1/2/3/5/7/8/9/10) is an AC with a test, not a note.
- A real-backend round trip (AC-3) is required, skipped — never faked — when the dev interpreter is absent.
- Fixtures are real captures from this Mac's backend, so Codable drift from the pinned shapes fails a test.
- The `.pth` dev venv was checked by the coordinator: `python -I -c "import ohyesmlx"` resolves through it (2026-11-13), so dev and production use the same `-I` argv.

## 3. Enterprise Gaps Identified
1. Stderr (and stdout after the launch line) not drained continuously: pipe-buffer deadlock.
2. Stdin's nature unspecified: `/dev/null` would make the backend exit at once by design.
3. Child exit while running (crash) not modelled: no "backend stopped" state, no relaunch, job not marked interrupted.
4. Quit with a running job waits forever on a wedged backend; the user's only exit is Force Quit.
5. Fixtures carried the host's home path into a public repo.
6. Retry after an interrupted download relies on the backend to resume or no-op (it does: `fetch` resumes from bytes on disk); no client logic needed.

## 4. Upgrades Applied to Plan

### Must-Have (Release-Blocking)
| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | Continuous pipe draining | AC-2b (new), v5-app.md | 1 MB stderr-before-launch-line test |
| 2 | Stdin is a held pipe | AC-2b, v5-app.md | Stated |
| 3 | Child death -> "backend stopped" + Relaunch, job interrupted | AC-2b, Task 2/3 done, v5-app.md | Stated, tested in both halves |

### Strongly Recommended
| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | "Quit anyway" after 150 s, SIGKILL only on that click | AC-2c (new), v5-app.md | Stated |
| 2 | Scrub home paths from fixtures | Fixtures (done by coordinator), boundaries | `/Users/user/` |

### Deferred (Can Safely Defer)
| # | Finding | Rationale for Deferral |
|---|---------|----------------------|
| 1 | UI test (XCUITest) | SPM has no app-bundle UI-test host; the coordinator's run + screenshot covers S7's "one UI smoke" until 05-06 builds the .app |

## 5. Audit & Compliance Readiness
Post-incident reconstruction: the stderr ring holds the backend's own JSON lines (refusals, job start/end,
recovery) and may be shown; the token is never in it (P5-10, backend-side guarantee). The `inflightJob` entry
survives a crash, so an interrupted action is never silently forgotten.

## 6. Final Release Bar
Ships when AC-1..AC-6 (with 2b/2c) pass, the P5-1 grep is clean, and the coordinator has run the app against the
dev backend and seen no orphaned `ohyesmlx app` after quit. I would sign it with the pipe ACs in place.

---
**Summary:** Applied 3 must-have + 2 strongly-recommended upgrades. Deferred 1 item.
**Plan status:** Updated and ready for APPLY
