# Enterprise Plan Audit Report

**Plan:** `.paul/phases/v5-onboarding/05-07-PLAN.md`
**Audited:** 2026-11-16
**Verdict:** Conditionally acceptable. The upgrades below are applied, and the plan is ready for APPLY.

---

## 1. Executive Verdict

Conditionally acceptable. The plan is well bounded. Every acceptance criterion is tied to a red test that already
exists, and the waves are file-disjoint. But three defects in the plan as first written would have made the fix itself
publish wrong or unattributable numbers. All three are now fixed in the plan. If I were accountable, I would approve it
with these applied.

## 2. What Is Solid

- **The red tests come from the review branch (`6fb323c`) unedited, and a worker reports BLOCKED if one cannot pass as
  written.** This stops a worker from fitting the test to the fix. The review has already caught that failure mode
  (AGENTS.md delegation contract).
- **S2-F1 is fixed once, at the place every caller goes through (`_cell_record`).** It is not fixed in the Swift views.
  This keeps one definition of the rule, and the report tables already hide FAIL figures (v3.1 A1).
- **Measurement is out of scope and `results/` is read-only.** This follows the AGENTS.md rule that raw observations are
  never discarded or rewritten, and the quiet-machine rule.
- **The plan defers the things that need Jason:** recording the mlx core version on each row, and the `disableThinking`
  plist setting. Each would add a field to every row, and adding one needs his yes.

## 3. Enterprise Gaps Identified

1. **The OptiQ version probe would silently record the wrong build.** `Runtime.version()` goes through `_run`. The plan
   said "helpers get no lab prefix", which would drop OptiQ's lab bin from its own version probe. The probe would then
   find the global optiq 0.7.8 while the server runs the lab copy, 0.5.13. That is the S5-F1 defect in reverse, on a
   different engine.
2. **The S2-F2 drain could hang the transport.** `BufferedReader.peek()` blocks on an empty buffer. The suggested fix
   could therefore turn a stalled stream into a hang past its deadline, on the TTFT path.
3. **The S5-F1 audit's evidence was weak.** `lab-paths.json` is rewritten atomically, so its creation date
   (2026-10-30 13:24) is when it was last written, not when it first existed. Rows written before that could still be
   affected. The audit also did not cover the app's quickbench runs under Application Support.
4. **AC-7 did not say what happens when a version is unknown.** A visit reporting `unknown: …` beside a known version
   was not covered, and the join already refuses unknown versions (D3).
5. **S2-F7 loosens a gate without saying so.** After the fix, a lost later visit no longer fails the row by itself, so
   the reason has to be written where the rule is defined, and stored rows must not be re-judged.
6. **Nothing said how the waves merge.** Wave 2 has to start from wave 1's merged result, or Task 3 would build on code
   that does not have Task 2's transport change.
7. **The S5-F2 checkpoint blocked the plan on a measurement it does not need.** The startup overhead depends on the
   engine build, and the host now runs builds nobody has tested: Osaurus 0.25.33 and vMLX 1.6.84.

## 4. Upgrades Applied to Plan

### Must-Have (Release-Blocking)

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | OptiQ version probe loses its lab bin | Context facts, AC-2, Task 1 | `_run` takes an optional `engine`, and `version()` passes its own engine name. A new test proves OptiQ's start and version probe still resolve its lab bin. |
| 2 | Drain can block on an empty buffer | AC-5, Task 2 | Never read when the buffer might be empty. A new test sends a partial event, stalls, and expects a timeout at the deadline rather than a hang. |
| 3 | `lab-paths.json` dates its last write, not its first | Context facts, AC-3, Task 5 | Evidence is install-log, the lab dir's creation date and git history. The file's own date is only an upper bound. App quickbench runs are covered, and quickbench/ is read-only. |

### Strongly Recommended

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | Unknown version is not covered | AC-7 | An unknown version beside a known one counts as a mismatch, so the row is FAIL. |
| 2 | S2-F7 loosens a gate | AC-10 | sweep-pins states why at the definition. A row with too few samples is still FAIL, and stored rows are not re-judged. |
| 3 | No merge order between waves | Tasks preamble | Each wave merges into `fix/05-07` and the full suite runs green before the next wave is dispatched. A worker that touches another file is reverted. |
| 4 | Checkpoint blocks the plan | Checkpoint → deferral, verification, scope | The S5-F2 measurement moves to the live Phase 5 checks session, after canaries on the new builds. UNIFY records it in STATE Deferred Issues. The plan is now `autonomous: true`. |

### Deferred (Can Safely Defer)

| # | Finding | Rationale for Deferral |
|---|---------|----------------------|
| 1 | Recording the mlx core version on each row (S5-F1's second suggestion) | It adds a field to every row, which needs Jason's yes. Raise it at UNIFY. With the PATH fix, the control's stack follows from its venv. |
| 2 | The `disableThinking` setting in the Osaurus app plist (second half of S5-F9) | It also adds a recorded field, so the same yes is needed. The smeltMode half closes the drift that is currently unattested. |
| 3 | Canaries for Osaurus 0.25.33 and vMLX 1.6.84 | No measurement runs in this plan. They are the precondition for the deferred S5-F2 measurement and the live checks. |

## 5. Audit & Compliance Readiness

- **Evidence:** each finding has a red test that is red on `main` and green on the branch, and the coordinator runs both.
  The S5-F1 audit note says which evidence it used for each row.
- **Silent failures:** the plan's purpose is to remove four of them: a figure on a FAIL row, a mislabelled control
  stack, a sampler error that was never read, and drift in a setting nobody attested. The two must-haves stop the fix from
  adding two new ones.
- **Reconstruction:** `results/` and quickbench/ stay unchanged, and the audit note records which rows are affected
  rather than deleting them.
- **Ownership:** the coordinator merges, runs the suite and reviews. Workers own only the files their task lists.

## 6. Final Release Bar

- **Before it ships:** all 14 red tests are green, plus the two added tests. The full suite is green on the
  coordinator's own run. A two-axis review reads the transport diff line by line. The audit note is committed. The S5-F2
  measurement is recorded as deferred.
- **Risk left if shipped as is:** the published cold-load orderings stay unverified until the S5-F2 constant is
  measured.
- **Sign-off:** I would sign it with the upgrades applied.

---

**Summary:** Applied 3 must-have + 4 strongly-recommended upgrades. Deferred 3 items.
**Plan status:** Updated and ready for APPLY.

---
*Audit performed by PAUL Enterprise Audit Workflow*
*Audit template version: 1.0*
