# Enterprise Plan Audit Report

**Plan:** .paul/phases/v5-onboarding/05-06-PLAN.md · **Audited:** 2026-11-14 · **Verdict:** not acceptable as drafted → acceptable after upgrades

## 1. Executive Verdict
The draft would have shipped an app that strands its own engines. Engine venvs are made from `sys.executable`, a
path inside the .app; an unsigned app opened from Downloads is App-Translocated to a random read-only path that
changes every launch, so every pip engine installed in that session points at an interpreter that no longer exists
next time. The user sees "installed" then a failure with no explanation. That is release-blocking.

## 2. What Is Solid
Pinned interpreter by tag and sha256 in a committed script; the interpreter version matches the one the hashed
constraints were frozen with; inside-out ad-hoc signing with strict verify; P5 rules re-checked on the shipped
interpreter, including a read-only volume; `-B` so the bundle never gains bytecode; no notarization claimed.

## 3. Gaps
1. App Translocation / moved app strands pip-engine venvs (must-have). 2. Licence files of the bundled interpreter
could be stripped by a size-minded build (strongly recommended). 3. SBOM omits the toolchain that built the binary
(strongly recommended). 4. A venv broken by a later move is reported by `detect_all` however its version probe fails
(deferred: needs a backend detect change; the translocation guard and the doc cover the common path).

## 4. Upgrades Applied
| # | Class | Finding | Change |
|---|---|---|---|
| 1 | Must-have | Translocation strands engines | AC-7: detect before spawn, full-window "Move to Applications", no job; doc |
| 2 | Strongly rec. | Licence files | AC-7: ship PBS licences unmodified |
| 3 | Strongly rec. | SBOM toolchain | AC-3: Swift toolchain version |

Deferred: detect_all marking a venv whose interpreter vanished as "needs reinstall" (backend change; next milestone).

## 5–6. Readiness / Release Bar
Ships when check_bundle.sh is all PASS, AC-7's guard is tested, and the clean-account smoke (Jason's sudoers step)
passes. Remaining risk: a user who moves the app after installing pip engines must reinstall them; the doc says so.
**Summary:** 1 must-have + 2 strongly-recommended applied; 1 deferred.
