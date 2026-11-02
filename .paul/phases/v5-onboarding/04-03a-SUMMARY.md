---
phase: 04-server
plan: 03a
completed: 2026-11-02
description: "Catalog base + siblings, the `quick` header pin the joins refuse, and one Python Osaurus pin/restore/recover"
type: Summary
about: "OhYesMLX"
---

# Phase 4 Plan 03a Summary

**Quickbench's foundations, each defined once: `Model.base` and `catalog.siblings`; a `quick` header pin that
`grid` and `sweep` refuse (absent equals false); `osaurus_settings.pin/restore/recover` with atomic writes, a 0700
backup dir and a byte-exact verify, now also used by `scripts/osaurus-pin.sh`.**

## AC Results

| Criterion | Status | Evidence |
|-----------|--------|----------|
| AC-1 catalog `base`, `siblings` | Pass | Test pins every base and its rows; Qwen3.5-0.8B and Qwen3.5-2B are the only two-row bases |
| AC-2 `quick` pin | Pass | Grid and sweep refuse quick runs incl. quick-vs-quick; pre-04-03a fixtures still join; red-check (refusal removed -> 3 tests fail) |
| AC-3 pin/restore/recover | Pass | Scratch-dir tests (crash recovery, interrupted write, 0700, mismatch keeps backup); red-checks (no byte compare; no-op recover); live round trip on Jason's host below |

1092 tests green.

## Live check (Jason's standing Osaurus authorisation, 2026-10-29)

`scripts/osaurus-pin.sh` on the real host: pinned (idle 900, caches off), then `osaurus_restore_check` reported
byte-exact; an independent `cmp` against copies taken before the test matched both files; the repo baseline is
unchanged and no backup directory was left behind. No runtime was started.

## Deviations

- The shell pin's backup moved from `*.phase4-orig` files beside each config to one `~/.osaurus/config.phase4-orig/`
  directory (the module's backup_dir).
- Behaviour change: the old shell pin silently reused a leftover backup; `pin` now refuses while one exists
  (audit rule). A runner that crashed mid-run must `recover` first; 04-03b calls it before any pin.
