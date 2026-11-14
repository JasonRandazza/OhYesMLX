# Order: 05-05 review fix — `best` names its format and repo; measured_here goes to the repo that was measured

Defect (coordinator, verified in code): `quickbench._best` returns {engine, decode_tps, ttft_s, measured_at, quick}
with no format or repo. `quickbench.latest` keys finished summaries by the summary's `repo`, and GET /recommendations
fills `Pick.measured_here` from that. When a stage-B sibling format wins, the user's chosen repo is shown the
sibling's speed — a number attributed to an artifact that did not produce it. The app's best card likewise prints
`summary.format`, not the winning cell's.

Fix:
1. `_cell_record` gains `"repo"` (the artifact's catalog repo: the chosen repo for stage A, the sibling's repo for
   stage B). `_best` adds `"format"` and `"repo"` from the winning cell.
2. measured_here is keyed by `best["repo"]`: find where the server/recommend builds the `{repo: best}` map from
   `quickbench.latest` and key it on best's repo (newest finished summary wins per best-repo). A losing chosen repo
   gets no measured_here. Keep `latest`'s contract (or adjust its docstring) — one definition.
3. docs/interfaces/v5-quickbench.md: cell gains `repo`, best gains `format` and `repo`, and one sentence on keying.
4. Swift: `QuickCell` gains `repo`, `QuickBest` gains `format` and `repo` (optional when decoding, so an older summary
   still decodes); ResultsView's best card prints best's format (falling back to summary.format only when absent);
   update both summary fixtures and StubBackend payloads so best's format is the stage-B winner's (oQ4 in the finished
   fixture). Test: the finished fixture's best card text names oQ4.

Files: ohyesmlx/quickbench.py, ohyesmlx/server.py (only if the map is built there), ohyesmlx/recommend.py (only if
built there), tests/test_quickbench.py, tests/test_server.py, tests/test_recommend.py, docs/interfaces/v5-quickbench.md,
app/Sources/OhYesMLXKit/Models.swift, app/Sources/OhYesMLXKit/StubBackend.swift, app/Sources/OhYesMLX/Screens/ResultsView.swift,
app/Tests/OhYesMLXKitTests/*.swift, app/Tests/OhYesMLXKitTests/Fixtures/quickbench_summary_*.json. Touch nothing else.
Red-check the misattribution test (a stage-B sibling wins -> chosen repo's pick has no measured_here; the sibling's does).
Suites: test-venv pytest (baseline 1368); `cd app && OYMLX_DEV_PYTHON=$HOME/.local/share/ohyesmlx/app-dev-venv/bin/python swift test` (baseline 73).
