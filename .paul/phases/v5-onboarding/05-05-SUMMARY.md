---
phase: 05-app
plan: 05
subsystem: app
tags: [swiftui, models, benchmark, results, quickbench]
requires: [{phase: 05-04, provides: shell, Format, components}]
provides: ["result event on every quickbench ending", "typed QuickSummary + raw bytes for Export", "Models, Benchmark, Results screens", "best names format+repo; measured_here keyed by the measured repo"]
affects: [05-06]
completed: 2026-11-14
description: "T5.4 + T5.5: Models, Benchmark and Results; every quickbench ending carries its summary; a sibling's win is no longer attributed to the chosen model"
type: Summary
about: "OhYesMLX"
---

# Phase 5 Plan 05: Models, Benchmark, Results — Summary

**The last three screens, built to DESIGN.md; a stopped run now shows the cell the user stopped. Coordinator review found
and fixed a misattribution: when a stage-B sibling format won, the chosen model's pick was shown the sibling's speed.**

| AC | Result | Evidence |
|---|---|---|
| AC-1 summary on every ending | PASS | one `result` from the place the summary is written; pytest |
| AC-2 typed summary, raw bytes | PASS | DecodingTests on finished + cancelled fixtures; Export writes the raw payload |
| AC-3 Models | PASS | `models-downloading`, `models-low-disk` scenarios (Q4 inline) |
| AC-4 Benchmark | PASS | `benchmark-plan`, `benchmark-running` (both stops + explainer, Q3) |
| AC-5 Results | PASS | `results-finished`, `results-cancelled` (Stopped by you, no best, not_evicted line Q7) |
| AC-6 05-04 carry-overs | PASS | gauge glyph, titles in busy/banner, Open Download Page, recommendations refresh after download/evict |

**Verification:** pytest **1371** (from 1366), swift **74** (from 57). Screenshots `docs/design/phase5/shots-05-05/`, light + dark.

**Coordinator review fixes (after the worker hit its 300-turn cap without a final report):**
1. Stage B rows named the engine twice instead of the format stage B varies (fixed in ResultsView/BenchmarkView by the coordinator).
2. **Misattribution (backend, since 04-03b):** `best` carried no format or repo and `Pick.measured_here` was keyed by the
   chosen repo, so a sibling's win showed on the chosen model. Fixed by a worker: cells carry `repo`, `best` carries
   `format`/`repo`, the server keys measured_here by `best.repo` (red-checked); the coordinator added newest-wins when two
   runs' winners measured one repo (red-checked through `/recommendations`).
3. The worker found and fixed a plan-fetch race (`planBenchmark` cleared the plan while `.onAppear` re-requested it).

**Deviations:** StatusGlyph gained `.stopped` (allowed defect fix). Not run: a live download or quickbench (needs Jason's go-ahead).
