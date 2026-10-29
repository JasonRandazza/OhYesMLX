# Enterprise Plan Audit Report

**Plan:** .paul/phases/v5-onboarding/02-03-PLAN.md
**Audited:** 2026-10-29
**Verdict:** conditionally acceptable (acceptable after the upgrades below, which are applied)

---

## 1. Executive Verdict

As written, not approvable: the installer accepted a caller-supplied `plan`, which makes the Phase 4 localhost API an arbitrary-command endpoint reachable from any web page the user visits. With the upgrades applied it is conditionally acceptable.

## 2. What Is Solid

- Consent gate as AC-1 with a test that must fail when the gate is removed.
- Every side effect injected (run, open_url, emit, detect, sleep): the executor is testable with no real subprocess.
- Guided download for the three app engines: the app never downloads or runs a vendor DMG itself.
- No sudo anywhere; manual smoke confined to a scratch dir.

## 3. Enterprise Gaps Identified

1. Caller-supplied Plan = remote command execution via localhost API (CSRF-style).
2. No guard against reinstalling over an existing engine; all five are installed on the author's machine.
3. Rollback "removes the venv" with no statement of what it may delete.
4. No timeouts or output bounds; a hung pip hangs the job and the UI.
5. `open_url` unconstrained.
6. No record of what was installed, when, with consent.
7. Concurrent installs of one engine race on the same venv dir.
8. Disk is scarce on target machines and was not checked first.
9. pip inherits ambient env (PYTHONPATH, PIP_*), so results differ per machine.

## 4. Upgrades Applied to Plan

### Must-Have (Release-Blocking)

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | Caller-supplied Plan | objective, Task 1, AC-6 | `install(engine_name, confirmed, ...)`; Plan derived internally; non-engine names raise |
| 2 | Overwrites existing installs | AC-7, boundaries | refuse `already_installed` |
| 3 | Unbounded rollback | AC-7, boundaries | delete only paths created by this call, inside engines dir, no symlink escape |
| 4 | Hang / unbounded output | AC-8 | step timeout, output tail cap, polling timeout ends in `result` |
| 5 | Unconstrained URL/argv | AC-9 | https host allowlist, argv lists, no sudo |

### Strongly Recommended

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | No evidence trail | AC-10 | append-only local jsonl install log |
| 2 | Races | AC-11 | per-engine lock, `busy` |
| 3 | Disk | AC-11 | `low_disk` refusal from hardware.scan |
| 4 | Ambient pip env | AC-12 | hermetic env and flags |

### Deferred (Can Safely Defer)

| # | Finding | Rationale for Deferral |
|---|---------|----------------------|
| 1 | Checksum/signature verification of DMGs | The app never fetches DMGs; the user installs from the vendor page and macOS verifies signatures. Revisit if the app ever downloads binaries. |
| 2 | Uninstall / upgrade flows | Not in v5.0 scope; the install log gives the record needed to add them. |
| 3 | vMLX's failing Gatekeeper assessment (research §5.6) | A Phase 5 UI-copy matter; do not describe it as clean. |

## 5. Audit & Compliance Readiness

With AC-10 each attempt leaves a reconstructable record; refusals are logged, not silent. Ownership: the coordinator verifies every red test; Jason approves the manual smoke. Without AC-10 the plan would fail a post-incident review.

## 6. Final Release Bar

Before shipping: AC-1..AC-12 green with each guard red-checked; smoke approved. Remaining risk: real vendor installers change over time (version table drift, research §6.3). I would sign off on the plan as amended.

---

**Summary:** Applied 5 must-have + 4 strongly-recommended upgrades. Deferred 3 items.
**Plan status:** Updated and ready for APPLY (after 02-01 and 02-02 land)

---
*Audit performed by PAUL Enterprise Audit Workflow*
*Audit template version: 1.0*
