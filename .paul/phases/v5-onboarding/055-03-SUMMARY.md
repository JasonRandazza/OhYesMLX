---
phase: v5-onboarding
plan: 055-03
subsystem: scripts + docs
tags: [sweep, osaurus-pin, s5-f2, readme, lineage]
provides:
  - "scripts/sweep.sh: one sweep() over runtimes.sweep_resident_engines (process scan), replacing 20 kill-by-port copies"
  - "Non-trap sweep calls are `sweep || exit 1`; sweep never exits (osaurus-pin trap still restores)"
  - "S5-F2 correction notes beside every flipped cold-load ordering (16 notes, 10 papers)"
  - "README rewritten as a whole: the app, the CLI, metrics, research index, LMRE lineage"
key-files:
  created: [scripts/sweep.sh, tests/test_055_03_sweep.py]
  modified: [ohyesmlx/runtimes.py, scripts/osaurus-pin.sh, "scripts/run_*.sh (20)", AGENTS.md, README.md, "docs/research/ (10 papers)"]
key-decisions:
  - "Jason approved the new sourced scripts/sweep.sh"
  - "Only run_jang_moe.sh's Osaurus edit matched osaurus-pin.sh; 8 copies stay, each with a ponytail line naming the difference"
  - "smoke_clean_account.sh keeps its own sweep (it clears only the test account's leftovers; the plan forbade changing that script)"
completed: 2026-11-19
description: "Phase 5.5 items 1, 5, 10: runner sweeps stop engines by process instead of killing whatever holds a port, flipped cold-load orderings carry correction notes, README rewritten with the LMRE lineage"
type: Summary
about: "OhYesMLX"
---

# Plan 055-03: Scripts and docs (Phase 5.5 items 1, 5, 10)

**Outcome.** The runner scripts no longer kill a user's dev server or miss an engine on a non-default port. Every published cold-load ordering that the S5-F2 constant flips now carries a dated correction note. The README describes the project as it is now: the app, the CLI and its lineage.

## Acceptance Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| AC-1: one sweep, by process | Pass | `runtimes.sweep_resident_engines` covers four cases. It kills exactly what `resident_engines` reports. A gone or EPERM pid becomes a line. A survivor after SIGKILL raises. An unreadable `ps` raises. On the shell side, `sweep.sh` guards `$PY`, never exits, and every non-trap call is `sweep \|\| exit 1`. `osaurus-pin.sh` sources it so its trap has a sweep to call. Static tests check that no `lsof -ti:` remains, that each script sources the sweep, and that `sh -n` passes. The one deviation is that `smoke_clean_account.sh` keeps its own sweep; see Deviations. |
| AC-2: pin copies | Pass | `run_jang_moe.sh` matched and now calls `osaurus_pin` / `osaurus_restore_check`. The other 8 copies are kept. `run_grid*`, `run_accuracy_*` and `run_jang_dense` pin idle only. `run_sweep_cache*` and `run_sweep_prompt` vary the cache. Each has a `# ponytail:` line, and the `osaurus-pin.sh` header is updated. |
| AC-3: correction notes | Pass | 16 notes cover all 11 rows of audit §5.1. The coordinator checked by script that every number in every note appears in the audit. No figure was deleted. The `grid-loadability-probe.md` banner sentence is struck through, with an amendment beside it. The 5.40–7.04 GB/s flag sits at both of its sites. |
| AC-4: README | Pass | The README has nine sections in the order AC-4 sets. The worker reported that all 33 relative links resolve and that all 6 CLI subcommands and 3 scripts exist. The coordinator read the whole README and checked it against the charter record and the code. |

## Verification

- **Red on main.** I ran the new sweep test file against `main`: 13 failed and 1 passed.
- **After the merge.** On `main` with both branches merged, `test-venv pytest -q` gives 1686 passed, and `sh -n` is clean on every `scripts/*.sh`.
- **Review.** The coordinator reviewed inline on both axes. The diffs for `runtimes.py`, `sweep.sh`, `osaurus-pin.sh`, `AGENTS.md`, `run_grid_35b.sh` and `run_jang_moe.sh` were read line by line. The correction-note numbers were checked by script. The whole README was read.

## Commits

| Commit | Description |
|--------|-------------|
| `0f3dfc7` | W1: one sweep by process scan. Command Code, DeepSeek v4.1 flash, 81 turns, $0.12 |
| `33233c6` | W2: correction notes and the README rewrite. 51 turns, $0.06 |
| `a59f96d` | Review fix: an engine install checks its pinned lock (`pip --require-hashes`), not the SBOM |
| `1931a14`, `0c4443a` | Merges |

## Deviations

- **The smoke script keeps its own sweep.** `smoke_clean_account.sh` keeps its sweep (TERM, then KILL, of the smoke account's leftovers only), because the plan's boundaries protect that script. The static test names it as the one allowed exception, with the reason.
- **Two more scripts converted.** `run_grid.sh` and `run_grid_moe.sh` had the kill-by-port loop inline rather than as a `sweep()`. They were converted too, so nothing under `scripts/` kills by port any more.
- **`run_jang_moe.sh` now follows the shared pin's semantics.** Its baseline is now the committed one with the pinned keys overridden (Fable S5-F8), where before it was written from the live host. Its backup dir is now `~/.osaurus/config.ohyesmlx-backup`, where before it was `$CONF.grid-orig`.
- **A dry-mode guard moved.** In `run_accuracy_thinkoff.sh` it now sits at its five call sites: `[ "$DRY_MODE" = 1 ] || sweep || exit 1`.
- **README review fix.** The README originally said an engine install refuses files whose hash is not in the SBOM. The install actually checks its own pinned lock, so the sentence was corrected.
- **A contradiction in the audit.** The audit's §3.6 says "fourth to second", while §5.1 says "third → second". The note states only the corrected order. The audit doc itself is left unedited, by boundary.

## Deferred

- **No runner script or real sweep was executed.** Running one is a measurement. The first live runner run after this merge is the end-to-end check of the new sweep.
- **The README's app section** may want refreshing after Phase 5.6 (UI aesthetics).
- **Pre-existing inconsistency.** The README says "OptiQ loads in all five" and also notes OptiQ weights missing the vision blocks vMLX requires. Both statements predate this plan.

## Next

Phase 5.5 has one item left: item 9, the vMLX 1.6.84 TTFT and cold-load question. It needs a quiet-machine measurement and Jason's go-ahead on timing.
