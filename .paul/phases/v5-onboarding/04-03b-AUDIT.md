# Enterprise Plan Audit Report

**Plan:** .paul/phases/v5-onboarding/04-03b-PLAN.md
**Audited:** 2026-11-02
**Verdict:** conditionally acceptable (ready for APPLY with the upgrades applied)

## 1. Executive Verdict
Conditionally acceptable. This is the one plan that measures on, and changes, a user's machine, and as written it
would have failed on exactly that machine: engines the app installs live under Application Support, which no start
command can see, so every mlx-lm and OptiQ cell would have failed to start on a user's Mac while passing on this
one (where `lab-paths.json` already points OptiQ there by hand). It also left three ways to harm the user: the
harness's Osaurus stop path and stale-instance sweep can end the user's own Osaurus app even when its port is free;
a pin after an earlier crash had no recovery step; and a cell could have measured a newer snapshot than the
pinned revision. With the must-haves applied I would approve it.

## 2. What Is Solid
- Two single-axis stages with their can't-claim captions (D3); stage B reuses stage A's row.
- Light cells are explicit constants, the coherence gate stays, `--cells` stays the only selector.
- Consent for Osaurus is per run, with restore in a `finally` and its result recorded.
- Evicts only what quickbench fetched; never the user's choice.
- Results under Application Support with the `quick` pin (04-03a), so they cannot join published tables.

## 3. Enterprise Gaps Identified
1. App-installed pip engines are not on PATH for the runtimes.
2. Osaurus app process running with its server port free: the stop path / sweep ends the user's app.
3. No `recover` before pin.
4. Cell artifact dir underspecified (newest-mtime lookup could pick another revision).
5. Chosen repo not downloaded: undefined (fetch it? evict it?).
6. One `run_cells` call for all cells makes "cancel between cells" impossible.
7. The summary's content as a record was unspecified.

## 4. Upgrades Applied to Plan

### Must-Have
| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | App installs invisible to the runtimes | new AC-0, Task 0, files, boundaries | `install` records the venv bin in `lab-paths.json` through one atomic writer; `_engine_env` already prefixes it |
| 2 | User's Osaurus app could be ended | AC-3 | Osaurus skipped while its app runs (full-path match); no stale sweep on a user's Mac |
| 3 | No recover before pin | AC-3 | `recover` first; an unverified recover blocks Osaurus for the run |
| 4 | Wrong snapshot measured | AC-2 | Cells use `fetch.plan`'s pinned-revision snapshot |
| 5 | Chosen repo not downloaded | AC-1 | Refused: "download it first" |

### Strongly Recommended
| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | Cancel needs a cell boundary | AC-4 | One `run_cells` call per cell |
| 2 | Summary as a record | new AC-4b | Plan, estimate vs actual, every cell's status and reason, versions, load, Osaurus restore, harness revision; atomic; written on early end |

### Deferred
| # | Finding | Rationale |
|---|---------|-----------|
| 1 | Thermal drift across a 10-minute run on a laptop | Quick results are labelled as such and never published; the load reading is recorded |
| 2 | Running quickbench while the user's other MLX apps hold GPU memory | Contention is recorded, not refused (D9); Phase 4.5 / Phase 5 copy |
| 3 | A per-run time cap | Each cell already has the harness's timeouts; the summary records estimate vs actual |

## 5. Audit & Compliance Readiness
The summary is now a full record of what ran, what was skipped and why, and whether the user's settings were put
back. Silent failure paths (unstartable engines, an unverified restore) are now explicit skips or errors.

## 6. Final Release Bar
AC-0..AC-5 green with red-checks; the checkpoint run on this Mac with Jason's go and a quiet machine; Osaurus
restored byte-exact; all ports free; the sibling evicted; `grid` refusing the quick directory. Remaining risk:
thermal and contention noise in quick numbers, labelled. I would sign this.

**Summary:** Applied 5 must-have + 2 strongly-recommended upgrades. Deferred 3 items.
**Plan status:** Updated and ready for APPLY
