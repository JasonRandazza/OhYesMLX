---
phase: 04-server
plan: 03b
subsystem: benchmark
tags: [quickbench, measurement, osaurus, jobs]
requires:
  - phase: 04-03a
    provides: catalog base/siblings, the quick pin, osaurus_settings pin/restore/recover
provides:
  - "ohyesmlx/quickbench.py, `ohyesmlx quickbench`, the quickbench job kind, GET /quickbench/plan, measured_here"
  - "engines.install records an app-installed pip engine's bin in lab-paths.json (AC-0)"
completed: 2026-11-02
description: "Quickbench measured on this Mac end to end; Osaurus is refused by a baseline-path mismatch (known gap)"
type: Summary
about: "OhYesMLX"
---

# Phase 4 Plan 03b: quickbench — Summary

**Quickbench runs two single-axis stages on the user's own Mac with light cells, labels everything quick, never
joins the published tables and fills `measured_here`. One known gap: the Osaurus cell is refused by its own drift
guard because quickbench pins against a different baseline file than the guard reads.**

## Checkpoint run (Jason's go, 2026-11-02 17:50-17:59 EST)

`ohyesmlx quickbench --repo mlx-community/Qwen3.5-2B-4bit --osaurus --yes`, chosen model and sibling in a scratch
`HF_HUB_CACHE`, control hub unloaded and reloaded, load 2.1 -> 3.3 (not labelled busy), 527 s against a 630 s
estimate. Summary: `~/Library/Application Support/OhYesMLX/quickbench/20261102T225004Z/summary.json`.

| Stage | Cell | Result |
|---|---|---|
| A | omlx 0.7.3 | PASS 173.7 tok/s, TTFT 0.074 s (winner, no tie) |
| A | vmlx 1.6.82 (untested) | PASS 144.0, 0.091 |
| A | mlxlm 0.31.3 | PASS 132.6, 0.180 |
| A | optiq 0.5.13 | PASS 124.6, 0.208 |
| A | osaurus 0.25.29 | N/A: drift guard (see Known gap) |
| B (omlx) | 4-bit, reused from A | 173.7 |
| B (omlx) | oQ4, fetched then evicted | PASS 166.3, 0.071 |

Verified by the coordinator: Osaurus host settings byte-identical to pre-run copies (`cmp`), no backup left, no
Osaurus app left running, all engine ports free, the oQ4 sibling evicted (scratch cache holds only the chosen
model), the real HF cache listing unchanged, `grid` refuses the quick directory, `/recommendations` shows
`measured_here` for the repo.

## Acceptance Criteria

| AC | Status |
|---|---|
| AC-0 app installs reach PATH | Pass (tests; red-check) |
| AC-1 plan first, chosen repo must be downloaded | Pass (plan printed live; tests) |
| AC-2 stages, light cells, pinned snapshot, winner/tie, caveats | Pass (live) |
| AC-3 consent, port/app probes, recover/pin/restore | **Partial**: probes, recover, pin and byte-exact restore pass live; the Osaurus cell cannot run (Known gap) |
| AC-4 job kind, cancel between cells, load recorded | Pass (tests; load recorded live) |
| AC-4b summary record | Pass (live) |
| AC-5 measured_here | Pass (live) |
| Checkpoint | Run done; Jason chose to commit with the gap and fix next session |

1144 tests green.

## Known gap (fix first next session)

`quickbench` pins Osaurus with `baseline_path` under Application Support (as the plan said), but
`runtimes`' Osaurus start guard reads `osaurus_settings.BASELINE_PATH` (the repo's
`config/osaurus-settings-baseline.json`, which records the host's caches on). So the pinned host reads as drift
and the cell is N/A. A plan defect, not a code defect. Proposed fix: pin against the baseline the guard reads and
back it up and restore it with the two config files (what `scripts/osaurus-pin.sh` does with `git checkout`),
then re-run quickbench (~9 min) to show the Osaurus cell PASS and the restore byte-exact. Phase 4.5: in a
packaged app the repo `config/` does not exist, so the baseline's location needs a decision there.

## Deviations

- Coordinator fix: sibling download/evict now receive the run's `cache_dir` and a discarding emitter (they had
  used the default cache and printed to stdout, which under `ohyesmlx app` is the client's pipe); test added.
- `record_lab_path` failing after a successful pip install raises out of `install` (worker's call; no pinned code).
