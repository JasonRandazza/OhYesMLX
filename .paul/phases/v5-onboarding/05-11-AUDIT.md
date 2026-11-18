# Enterprise Plan Audit Report

**Plan:** `.paul/phases/v5-onboarding/05-11-PLAN.md`
**Audited:** 2026-11-18
**Verdict:** conditionally acceptable. Upgrades applied, ready for APPLY.

## 1. Executive Verdict

Conditionally acceptable. The plan maps one-to-one onto the eight findings and P5-11, and each finding has a red test.
Each task has one owner surface, and the tasks' files are disjoint. Three gaps would have shipped a new defect:

1. S4-F2's "remove an unrecorded venv and reinstall" could delete a directory that pip was still writing to. Pip runs in its own session and survives a backend that is hard-killed, so it outlives the backend that launched it.
2. P5-11's `files_on_disk` would have labelled a paused, resumable download "Re-download". A `.incomplete` partial is on disk, so the field could not tell the two apart.
3. The detection PATH for S4-F2 was not stated to be injectable. Tests would then read the real `os.environ`, or a worker would copy the PATH logic, which breaks the "one definition" rule.

## 2. What Is Solid

- **Stage B reuses `_skip_reason` and its `port_refusal`.** Both are the 05-10b single definition, so there is no second guard to drift.
- **Rollback stays with the existing `_rollback` helper.** The plan only reorders the calls and makes them exception-safe.
- **S4-F6 derives the sentences from the factors `_fit` already uses.** The wording follows the rule, and the red test asserts against the factors rather than against copy.
- **The global installs are left untouched.** Under S4-F2 the app installs its own copy beside a Homebrew or `~/.local` install instead of modifying it.
- **The boundaries exclude measure, transport, report and `port_plan`.** No measured number can change.

## 3. Enterprise Gaps Identified

- **Removal race.** `install` could remove an unrecorded root while a pip process that survived the backend is still writing into it.
- **Partial versus mismatch.** P5-11 did not distinguish a resumable partial from files of the wrong size.
- **Real environment in tests.** Detection's PATH was not injectable, so tests depended on the real environment.
- **Event-buffer pressure.** Forwarded sibling-download progress arrives every 0.5 s. A one-hour fetch is about 7,200 events against the job buffer's `MAX_EVENTS = 10,000`.
- **Bytes before a refusal.** The S4-F1 re-check ran only after the download, so the run spent gigabytes on an engine it was about to refuse.
- **Untested clauses.** The red tests did not cover the CLI-unchanged clause of AC-5, the partial/mismatch split, or the unchanged `plan()` output.

## 4. Upgrades Applied to Plan

### Must-Have (Release-Blocking)

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | A reinstall could remove a root that a live pip is writing to | AC-5, T2 | A `ps -ww` argv check through an injectable seam refuses `install_in_progress` and removes nothing. Removal is limited to the plan's own root, never a recorded lab path, never outside `engines_dir`. |
| 2 | P5-11 field conflated a partial with a mismatch | AC-8, T3, T4 | Renamed to `differs_on_disk`, true only for a complete-named blob or link of the wrong size. A `.incomplete` file alone is false. Tests cover all three states. |
| 3 | Detection PATH not injectable | AC-5, T2 | The PATH comes from the `env` object, with `_engine_env` as the single join rule. A test pins that the CLI-path behaviour is unchanged. |

### Strongly Recommended

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | Forwarded progress could approach `MAX_EVENTS` | AC-2, T1 | Forwarded progress is throttled to one event per whole percent of the sibling's bytes. |
| 2 | Bytes were spent before a refusal | AC-1, T1 | `_skip_reason` is also checked before the download. A test asserts that no `download` call happens. |
| 3 | Import-cycle direction unstated | T2 | States that `engines` imports `runtimes` and never the reverse. |
| 4 | New behaviour not covered by red tests | T1, T2, T3 | Named tests added for each uncovered clause. |

### Deferred (Can Safely Defer)

| # | Finding | Rationale for Deferral |
|---|---------|----------------------|
| 1 | `plan()` and the consent estimate still count siblings the winner may not serve | The estimate errs high, which is the safe side, and the winner is unknown when the plan is shown. Changing the plan's shape is an API change. |
| 2 | Which engine stage B uses when stage A ties | This is noise-band policy, owned by S4-F5 (plan A). This plan only stops the UI from calling the tie a win. |
| 3 | The app's copy of OptiQ/mlx-lm duplicates a global install on disk | The user consents to the install. Its size is shown in the install plan. |

## 5. Audit & Compliance Readiness

- **Evidence.** Each red test is re-run green by the coordinator. Every red-test correction is listed in the SUMMARY.
- **Silent failures.** Skips carry a reason in the cell. A refused install carries a code (`install_in_progress`, plus the lab-path refusal).
- **Reconstruction.** Every skipped stage-B cell keeps its reason in `summary.json`, and every install keeps its `install-log.jsonl`. Logging is best-effort, so a log failure cannot block cleanup.
- **Ownership.** The coordinator integrates, reviews, and observes the gates.

## 6. Final Release Bar

The plan ships when:
- all seven Python red tests, `FableS3F9Tests` and the new tests are green;
- the full pytest suite and `swift test` are green, with `swift test` run on a venv built from the branch;
- the light and dark screenshots exist;
- the two-axis review findings are fixed or ruled on.

Remaining risk if shipped as-is: the Re-download copy depends on what `fetch.download` actually does with a wrong-size blob. T3 reads that first, and the AC makes the copy follow the code.

**Summary:** Applied 3 must-have and 4 strongly-recommended upgrades. Deferred 3 items.
**Plan status:** Updated and ready for APPLY.

---
*Audit performed by PAUL Enterprise Audit Workflow*
*Audit template version: 1.0*
