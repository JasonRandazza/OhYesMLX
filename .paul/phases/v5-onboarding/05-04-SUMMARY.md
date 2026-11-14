---
phase: 05-app
plan: 04
subsystem: app
tags: [swiftui, shell, engines, design]
requires: [{phase: 05-02, provides: AppModel}, {phase: 05-03, provides: DESIGN.md}]
provides: ["Format (one formatter)", "Components: Badge, StatusGlyph, Figure, InterruptedBanner, ConsentSheet", "shell + full-window states", "Your Mac, Engines", "DEBUG stub scenarios"]
affects: [05-05, 05-06]
completed: 2026-11-14
description: "T5.2 + T5.3: the designed shell, full-window states, banner, Your Mac and Engines screens"
type: Summary
about: "OhYesMLX"
---

# Phase 5 Plan 04: Shell, Your Mac, Engines — Summary

**The placeholder became the designed NavigationSplitView app: step ticks, toolbar actions, four full-window states,
the interrupted banner, Your Mac and Engines with the consent sheet, busy reasons and failure tails. 57 swift tests.**

| AC | Result | Evidence |
|---|---|---|
| AC-1 Format | PASS | FormatTests (binary memory "64 GB", decimal disk, NBSP joins; red-checked); `AppModel.formatGB` deleted |
| AC-2 shell | PASS | screenshots `docs/design/phase5/shots-05-04/` light+dark; `.regular` activation (lsappinfo Foreground) |
| AC-3 banner | PASS | `interrupted` scenario; click-only Retry |
| AC-4 Your Mac | PASS | `welcome` scenario |
| AC-5 Engines | PASS | `engines`, `-consent`, `-busy`, `-failed` scenarios |
| AC-6 stub scenarios | PASS | 9 scenarios; release binary contains no `OYMLX_STUB_SCENARIO` |

Coordinator review (screenshots, 9 scenarios × light/dark): matches DESIGN.md; no contrast failures. Carried into 05-05:
Benchmark sidebar glyph is `info.circle` (should be a gauge); busy/banner text names the repo id rather than the pick
title; a guided install's sheet says "Install" (should read "Open Download Page") and its size is unlabelled as estimated.
Worker note carried: recommendations are not refreshed after a download finishes (05-05).
Note: screenshots toggled the system appearance; it was restored to dark, as found.
