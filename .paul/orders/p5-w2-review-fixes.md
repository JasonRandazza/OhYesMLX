# Order: Phase 5 wave-2 code-review fixes (05-04 + 05-05 Swift)

Reviews: `.paul/review/2026-11-14-phase5-w2/{standards,spec}.log` (read both). The coordinator verified the items below.
Files you may touch: app/Sources/OhYesMLXKit/{AppModel,Models,Format}.swift, app/Sources/OhYesMLX/Screens/{BenchmarkView,ResultsView,ModelsView,EnginesView}.swift, app/Sources/OhYesMLX/Components/StatusGlyph.swift, app/Tests/OhYesMLXKitTests/*.swift. Touch nothing else (05-06's uncommitted changes to AppModel/RootView/FullWindowStates/BackendLauncher are in this tree — keep them).

1. A finished job's state is judged by the quickbench summary only when the job IS a quickbench (spec #1 / standards #4). Test: quickbench restore_failed, then a download done -> download `.finished`.
2. The Benchmark step tick derives from data that survives later jobs (the last finished quickbench summary, or any pick with measured_here), not from the current `job` (spec #2). Test.
3. Export (spec #3): JSONValue keeps every key, so drop the "exactly as the backend wrote it" claim — the panel and the docstring say it writes every field the backend sent, re-serialised; keep `payloadData` but name it honestly. Number fidelity: integers must round-trip as integers (test a byte count > 2^31).
4. One not_evicted line: ResultsView renders `AppModel.notEvictedLines` (delete its own builder) (spec #4 / standards #6).
5. Plan fetch race (spec #5): `planBenchmark` drops a response whose repo is not the currently selected one. Test with a slow first response.
6. `Format.percent` replaces `String(format: "%.0f%%")` in ModelsView (spec #6 / standards #1).
7. Status: one function maps a cell status to (glyph, word) — used by BenchmarkCellRow (which gains the glyph, DESIGN §4.3) and ResultsView; one spelling (PASS/FAIL/SKIPPED/Stopped by you) (standards #2, #8). StatusGlyph is 8 pt (standards #7).
8. EnginesView: the disabled Try Again shows the busy reason beside it as Install… does; one install-start path for Install and Try Again (standards #3, #9).
9. Delete the duplicate `waitUntilAsync` test helper (standards #10).

Suite: `cd app && OYMLX_DEV_PYTHON=$HOME/.local/share/ohyesmlx/app-dev-venv/bin/python swift test` (baseline 75). Red-check items 1, 2, 5. Report per item.
