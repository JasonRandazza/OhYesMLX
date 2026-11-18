# Enterprise Plan Audit — 05-12 (Fable plan F)

**Audited:** 2026-11-18 by the coordinator, kept short to save session budget.
**Verdict:** conditionally acceptable. Upgrades applied.

## Must-have (applied)

1. **Conflicting backups.** A backup could exist in both the new directory and a legacy one, and recovery would have to pick. `recover()` now refuses and names every directory holding a backup. It never picks or merges. (AC-1)
2. **Caller exit status.** `scripts/run_canary.sh` is the pattern caller, and it must exit non-zero after a failed restore. It was added to `files_modified`. (AC-2)
3. **Live-host check.** No backup exists today in `~/.osaurus/config.phase4-orig`, `<app support>/quickbench/osaurus-backup` or `results/osaurus-backup` (checked 2026-11-18). The move to one location strands nothing.

## Strongly recommended (applied)

1. `BACKUP_DIR` keeps mode 0700 (`BACKUP_DIR_MODE`). (AC-1)
2. The baseline rule is split by caller: the harness keeps the committed baseline, and the app takes the live host at pin time. The committed baseline is Jason's host, so using it in the app would refuse every run on any other Mac. (AC-3)

## Deferred

1. **Snapshot in the run header.** A header pin needs Jason's yes. The committed baseline, versioned by the harness revision already in the header, identifies the conditions of a harness run.
2. **The other runner scripts' Osaurus pin copies.** Already in STATE Deferred Issues.
