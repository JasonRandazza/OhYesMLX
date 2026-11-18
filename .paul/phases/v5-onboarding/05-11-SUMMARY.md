---
phase: v5-onboarding
plan: 05-11
subsystem: onboarding decisions (quickbench stage B, engine install/detect, recommend, app Results/Models)
tags: [quickbench, engines, recommend, fetch, swiftui, fable-5.2]
requires:
  - phase: 05-10b
    provides: runtimes.port_plan / port_refusal seam that stage B re-asks
provides:
  - stage B re-checks the winner before and after each sibling download, hears Stop/Stop now, skips unlisted siblings
  - install rolls back on any late failure; lab engines count as installed only when startable
  - memory sentences quote the factor that decided the row
  - Pick.mismatch_on_disk (P5-11) and the app's Re-download / remove-first copy
  - Results shows the run's busy label and stage-A tie
key-decisions:
  - "P5-11 field is mismatch_on_disk: null|'ours'|'foreign', not a bool: fetch.download repairs only blobs it wrote"
  - "Exclusion sentence: 'Needs about {1.25 x size, rounded up} GB of memory'; 'at peak' dropped (1.25x is the line, not a peak)"
  - "A tied stage A heads the best card 'Fastest measured here (top engines tied)'"
completed: 2026-11-18
duration: ~2.5h (one session)
description: "Fable plan E closed: 8 findings + P5-11; stage B guards, install rollback/startability, honest memory sentences, Results tie/busy, Re-download"
type: Summary
about: "OhYesMLX"
---

# Plan 05-11 (Fable fix plan E): Onboarding decisions — Summary

**Stage B no longer drives an engine the user has since claimed, ignores Stop, or runs formats the catalog
says the engine cannot serve. An interrupted install no longer leaves an unrecorded venv. "Installed" now means
startable. The memory sentences quote the line that decided the row. Results stops calling one of two tied engines
best. A model whose files on disk don't match now gets an honest Re-download or remove-first row (P5-11).**

## Acceptance Criteria Results

| Criterion | Status | Evidence |
|---|---|---|
| AC-1 stage B re-checks before/after download (S4-F1) | Pass | `test_fable_s4_f1.py` (4 tests incl. review's post-download evict-and-continue) |
| AC-2 sibling download hears Stop/Stop now; progress forwarded at ≤1/percent (S4-F4) | Pass | `test_fable_s4_f4.py` (5 tests incl. coordinator's stopped-download-ends-cancelled) |
| AC-3 unlisted sibling skipped before any byte (S4-F8) | Pass | `test_fable_s4_f8.py`, `plan()` unchanged test |
| AC-4 late install failures roll back first, then error+done (S1-F7, S4-F10) | Pass | `test_fable_s1_f7.py`, `test_fable_s4_f10.py`, bad lab-paths, raising runner, 0755-under-umask tests |
| AC-5 installed = startable; unfinished root cleared unless a live process names it (S4-F2) | Pass | `test_fable_s4_f2.py`; CLI-PATH/app-PATH, in-progress, recorded-root, refused-start tests in `test_engines.py` |
| AC-6 memory sentences use the deciding factor (S4-F6) | Pass | `test_fable_s4_f6.py` (all 8 cases); need==budget collision test |
| AC-7 Results shows busy label and tie (S3-F9) | Pass | `FableS3F9Tests` (4), `Plan0511T4Tests`; screenshots |
| AC-8 P5-11 Re-download (as `mismatch_on_disk`) | Pass | 5 `test_fetch.py` mismatch tests, server pass-through test, Swift decode/copy tests; screenshots |
| AC-9 gates | Pass | pytest **1580 passed** (2 worktree-only skips: no local `results/grid`), swift test **122/122** with a branch-local backend venv; screenshots in `docs/design/phase5/shots-05-11/` |

## Commits (branch `fix/05-11`)

| Task | Commit | Done by |
|---|---|---|
| Plan + audit | `34edc5f` | coordinator |
| T1 stage B guards | `a2c7d6f` + coordinator fix `9485250` | Sonnet (medium) |
| T2 install + detection | `a05f48d` | Opus (high) |
| T3 memory sentences + `mismatch_on_disk` backend | `2b2b417` | coordinator |
| T4 Results + Models (Swift) | `166ad98` | Sonnet (high) |
| Screenshots | `702524e` | coordinator |
| Two-axis review fixes | `5af0bc2` | coordinator |

## Deviations

1. **P5-11 field shape (T3).** The plan's `differs_on_disk` bool became `mismatch_on_disk: null|"ours"|"foreign"`.
   Reading `fetch.download` (AC-8's last clause) showed it repairs a mismatched blob only when its ledger says this
   app wrote it, and refuses to overwrite any other one with `integrity_failed`. A bool would have shown a
   Re-download button that always fails on foreign files, such as the two hero models'. "foreign" also covers a
   symlinked blob and a snapshot link `download` would refuse (`_link_conflicts`); the review added these.
2. **Exclusion wording (T3).** "…GB of memory at peak" became "…GB of memory". The figure is now 1.25 × size, rounded
   up. If it would print equal to the budget, it is bumped a tenth. The budget stays rounded to nearest so it agrees
   with every other screen. A round-down was tried and rejected: it showed an 8 GiB Mac's budget as 3.5 GB.
3. **Coordinator fix to T1 (`9485250`).** A Stop now heard by the sibling download was recorded as "could not be
   downloaded" and the loop moved on. It now ends the run `cancelled`. Red-checked: the new test fails without the fix.
4. **Red-test corrections (all minimal; no assertion weakened):**
   - **S4-F1/S4-F4:** these used the `port_in_use=` seam, which 05-10b replaced with `port_refusal=`. They also gained `verify=NO_VERIFY`, because 05-10's integrity check now runs in `quickbench.run`.
   - **S4-F2:** the precondition `status.installed is True` became `is False`, because the fix makes it so. The final "startable or installable" assertion is unchanged.
   - **S4-F6:** the regex dropped " at peak" (deviation 2).
   - **Fakes:** three fake `download` signatures (`test_quickbench.py`, `test_fable_s4_f9.py`, `test_fable_s4_f11.py`) accept `cancel=`.
5. **Tests that pinned the defect, updated:**
   - Five sentences in `test_recommend.py` asserted the old 2× / 1× figures.
   - `test_engines.py::test_a_venv_that_existed_before_the_call_is_never_removed` now records the venv in lab-paths. An unrecorded root is an unfinished install under AC-5.
   - `AppModelTests` gained the two new stub scenarios in its exhaustive switch.
6. **Behaviour changes worth knowing:**
   - A recorded lab path with nothing at it, or one that `_engine_env` refuses, now reads as not installed. It used to fall back to a global install, which the start would have refused anyway.
   - If `ps` cannot be read, an install refuses `install_in_progress` rather than removing an unfinished root.
   - An unfinished root that is a symlink out of `engines_dir` refuses `stale_install`.
   - Rollback log lines now precede `error`.

## Review (two axes, Sonnet reviewers; all findings confirmed and fixed in `5af0bc2`)

- **Standards:**
  - Medium: `_startable` contradicted its docstring on a refused lab.
  - Low: docstring overclaimed what is injectable.
  - Low: dead `Pick.offersDownload` made a second copy of the button rule.
  - Low: `_FIT_FACTORS` was a tuple rebuilt into a dict on every call.
  - Low: import spacing.
- **Spec:**
  - Medium: the tie card still headed one engine "Best on your Mac".
  - Medium: `mismatch_on_disk` missed link/symlink conflicts.
  - Low-Medium: same as Standards' Medium.
  - Low: need/budget printed equal.
  - Low: untested clauses (post-download refusal, server pass-through, chmod).
  - Nit: unguarded rollback send.

## Next

Plan F (05-12, Osaurus pin and restore: S2-F10, S5-F6, S5-F7, S5-F8, S5-F12), then G (packaging; re-run
`scripts/check_bundle.sh`). Still open from STATE: live Phase 5 checks (app-UI download, Stop now), the S5-F2
constant, clean-account smoke, UAT.
