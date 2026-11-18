---
phase: v5-onboarding
plan: 05-12
completed: 2026-11-18
duration: ~1.5h (worker ~65 min, Command Code DeepSeek v4.1 flash, 150 turns, $0.43)
description: "Fable plan F closed: one Osaurus backup location, restore verdicts that cannot read as success, a pin that cannot overwrite its own baseline, atomic key edits"
type: Summary
about: "OhYesMLX"
---

# Plan 05-12 (Fable fix plan F): Osaurus pin and restore — Summary

All five findings are closed: S2-F10, S5-F6, S5-F7, S5-F8 and S5-F12. The work was done by one Command Code
`implement` worker (order `.paul/orders/05-12/t1.md`), then reviewed and fixed by the coordinator. No Claude subagent
was used.

## Acceptance Criteria

| AC | Status | Evidence |
|---|---|---|
| AC-1 One backup location (S5-F6) | Pass | `test_fable_s5_f6.py`, recover/pin legacy and ambiguity tests in `test_osaurus_settings.py` (see below) |
| AC-2 A failed restore is never success (S5-F7) | Pass | `test_fable_s5_f7.py`, shell run in a scratch HOME |
| AC-3 The pin cannot overwrite its baseline (S5-F8) | Pass | `test_fable_s5_f8.py`, quickbench snapshot test |
| AC-4 Atomic key edits (S5-F12) | Pass | `test_fable_s5_f12.py` (atomicity, 0 and `00` rejected) |
| AC-5 A raised restore is recorded (S2-F10) | Pass | `test_fable_s2_f10.py` |
| AC-6 Gates | Pass | Full pytest suite **1606 passed** (2 skips are worktree-only). No test touches the real `~/.osaurus`. |

AC-1 in detail:
- `osaurus_settings.BACKUP_DIR` is `~/.osaurus/config.ohyesmlx-backup`, with mode 0700. quickbench's default backup
  directory, the app's launch recovery and the shell wrapper all use it.
- `legacy_backup_dirs()` and `backup_dirs_holding()` are the one definition of where a backup can be.
- `recover()` searches the legacy directories as well, and refuses if more than one directory holds a backup.
- `pin()` refuses while any of those directories holds a backup.
- The shell trap now also fires on EXIT.

## What changed in behaviour

- **Harness runs** (`osaurus-pin.sh` and the CLI) keep the committed baseline and override only `PINNED_KEYS`. A
  host that differs from it on any other tracked key is refused by the drift gate.
- **The app** (quickbench) passes `rebaseline=True`, which records the live host as the baseline. It also stores
  that snapshot in `summary.osaurus.snapshot`.
- **The shell wrapper:**
  - `osaurus_restore` is the only restore. It prints the verdict and returns non-zero after a restore that did not
    verify, and it re-arms its trap at that point.
  - `run_canary.sh` exits 1 after a failed restore.
  - `osaurus_set_seqs` calls `osaurus_settings.set_key`.

## Deviations

1. **The worker edited two files outside its allowed list.** Both edits were unavoidable, and both are kept:
   - `tests/test_paths.py` asserted that the backup directory lives under Application Support. AC-1 moves it.
   - `tests/test_quickbench.py` asserted exactly four keys in `summary.osaurus`. AC-3 adds `snapshot`. The test now
     also asserts that `rebaseline=True` is passed.
2. **Red-test correction.** In `test_fable_s5_f8`, the count of untouched keys went from 20 to 21. The intent is
   unchanged: three keys are the pin's, and the rest keep the host's values.
3. **Coordinator review fix (`75b057a`).** `pin()` hard-coded its three values next to the new `PINNED_KEYS`
   table, which made two definitions. It now applies `PINNED_KEYS`.
4. **Run-header snapshot not added.** Jason confirmed on 2026-11-18 that no header field is needed. The committed
   baseline, versioned by the harness revision already in the header, identifies what a harness run ran under.

## Notes

- After a verified restore, the restoring trap stays armed. A late Ctrl-C finds no backup and returns silently.
- This plan ran no live Osaurus pin or restore. Live checks need Jason's "when", as before.

## Next

Plan G (05-13): packaging and release, S6-F1..F11. It includes re-running `scripts/check_bundle.sh`.
