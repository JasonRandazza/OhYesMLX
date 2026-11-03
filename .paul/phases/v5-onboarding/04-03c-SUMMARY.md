---
phase: 04-server
plan: 03c
subsystem: benchmark
tags: [quickbench, osaurus, baseline]
requires:
  - phase: 04-03b
    provides: quickbench, osaurus_settings pin/restore/recover
completed: 2026-11-03
description: "The Osaurus pin backs up and restores the drift guard's baseline; quickbench pins against it and its Osaurus cell now measures"
type: Summary
about: "OhYesMLX"
---

# Phase 4 Plan 03c: Osaurus baseline fix — Summary

**`osaurus_settings.pin` copies the drift guard's baseline (or a `baseline.absent` marker) into the backup with the
two configs; `restore`/`recover` put all three back byte-exact. Quickbench pins against
`osaurus_settings.BASELINE_PATH`, the file `runtimes.Osaurus.check_host_state` reads, and `scripts/osaurus-pin.sh`
no longer runs `git checkout` on the baseline. Commit `ad73b76`; 1152 tests (1144 before).**

## Live run (Jason's go, 2026-11-03 11:40 EST start)

`ohyesmlx quickbench --repo mlx-community/Qwen3.5-2B-4bit --osaurus --yes`, chosen model in a scratch
`HF_HUB_CACHE`, control hub unloaded and reloaded, load 1.7 -> 2.6 (not labelled busy). 1956 s against a 630 s
estimate: the oQ4 sibling downloaded at ~7 MB/s against the estimate's 20 MB/s. Summary:
`~/Library/Application Support/OhYesMLX/quickbench/20261103T164018Z/summary.json`.

| Stage | Cell | decode tok/s | TTFT s |
|---|---|---|---|
| A | omlx 0.7.3 (winner, no tie) | 175.3 | 0.074 |
| A | vmlx 1.6.82 (untested) | 153.9 | 0.087 |
| A | mlxlm 0.31.3 | 137.1 | 0.173 |
| A | **osaurus 0.25.29** | **131.3** | 0.128 |
| A | optiq 0.5.13 | 126.6 | 0.176 |
| B (omlx) | 4-bit, reused from A | 175.3 | 0.074 |
| B (omlx) | oQ4, fetched then evicted | 178.6 | 0.068 |

Quick numbers only (3 warmup, 5 measured): never joined to the published tables.

Verified by the coordinator: `summary.json` `osaurus: {pinned: true, restored: true}`; `cmp` of
`~/.osaurus/config/server.json`, `server-runtime.json` and `config/osaurus-settings-baseline.json` against pre-run
copies, all identical; no backup directory left (neither `config.phase4-orig` nor the quickbench one); no Osaurus
app running; all engine ports free; scratch cache holds only the chosen model (oQ4 evicted); real HF cache listing
unchanged; control hub agent and dashboard reloaded; `git status` clean.

## Acceptance Criteria

| AC | Status |
|---|---|
| AC-1 baseline in the backup set, byte-exact restore, marker case, refusal | Pass (tests; worker red-check) |
| AC-2 quickbench pins against the guard's baseline | Pass (tests; live) |
| AC-3 one definition: no `git checkout` in the script | Pass (diff; `bash -n`) |
| AC-4 live Osaurus PASS, restore byte-exact | Pass (live) |

04-03b's AC-3 is now Pass.

## Deviations

- Coordinator refreshed `docs/interfaces.md` (new `restore`/`recover` signatures, quickbench default), outside the
  worker's file list.
- Unhandled by choice: a backup directory holding both `baseline.json` and `baseline.absent` makes `_put_back`
  raise instead of returning `False`; only hand-made, since `pin` never writes both and refuses over either.
