---
phase: 04-server
plan: 03b
plan_type: tdd
wave: 2
depends_on: ["04-03a"]
files_modified: [ohyesmlx/engines.py, tests/test_engines.py, ohyesmlx/quickbench.py, ohyesmlx/cli.py, ohyesmlx/server.py, ohyesmlx/recommend.py, tests/test_quickbench.py, tests/test_cli.py, tests/test_server.py, tests/test_recommend.py, docs/interfaces.md]
autonomous: false
description: "ohyesmlx quickbench: two single-axis stages on the user's own Mac, estimated first, light cells, results that never join the tables"
type: Plan
about: "OhYesMLX"
---

<objective>
## Goal
`ohyesmlx quickbench --repo R --yes` (and the `quickbench` job kind) measures, on this Mac, stage A (installed
engines, the chosen model's format fixed) and then stage B (the winning engine fixed, the chosen model's sibling
formats), with D9's light cells and the coherence gate, and writes a "best for you" summary that fills
`Pick.measured_here` (D5).

## Purpose
T4.4, seam S8, decisions D3, D4, D5, D9, D10 and Jason's 2026-11-02 calls (Osaurus asked, pinned and restored;
`quick: true` header; sibling downloads shown up front and evicted after). This is the one place v5.0 measures on
a user's machine, so it inherits every runtime hazard in AGENTS.md: one model resident, ports released, no second
selector, incoherent output is FAIL, and nothing the user owns is changed without consent and restore.
</objective>

<context>
@ohyesmlx/measure.py `run_cells` (warmup, measured, cooldown_s, results_dir, and `quick` from 04-03a); @ohyesmlx/cli.py `build_cells`, `workloads`, `_canary` (the pattern: one `--cells` string per cell, `canary.load()` before and after)
@ohyesmlx/canary.py `load`, `LOAD_NOISY`, `NOISE_FLOOR`; @ohyesmlx/catalog.py `siblings` (04-03a); @ohyesmlx/fetch.py `download`, `evict`, `downloaded`, the ledger (what OYMLX downloaded)
@ohyesmlx/osaurus_settings.py `pin`/`restore` (04-03a); @ohyesmlx/runtimes.py ports and `_shutdown` (kills every listener on an engine's port at stop)
@ohyesmlx/server.py job registry (04-02)
</context>

<acceptance_criteria>

## AC-0: An engine the app installed is an engine the harness can start <!-- audit-added: must-have -->
```gherkin
Given `engines.install` succeeds for a pip engine (mlxlm, optiq) into `<Application Support>/OhYesMLX/engines/<name>-<version>`
Then it records that venv's `bin` in the machine-local `lab-paths.json` (through the one writer next to
 `engines.lab_paths`, atomic), so `runtimes._engine_env` puts it on PATH for every later start
And without this every mlx-lm and OptiQ cell on a user's Mac fails to start: the start commands use bare names and
 the app's venvs are not on PATH; an existing entry for that engine is replaced only by an install of the tested version
```

## AC-1: The plan is shown before anything runs
```gherkin
Given `quickbench.plan(repo, hw, engines, models)` (pure)
Then it returns stage A's engines (installed engines that list the row; untested builds included and labelled),
 stage B's sibling repos, each extra download's bytes, whether Osaurus would be pinned, and an estimate in seconds
 (per-cell estimate x cells, plus download bytes / an assumed 20 MB/s, both constants named once)
And the chosen repo must already be downloaded (`fetch.downloaded`); otherwise the plan is refused with "download it
 first", because quickbench never fetches or evicts the user's own choice <!-- audit-added: must-have -->
And `ohyesmlx quickbench --repo R` without `--yes` prints that plan and starts nothing; the job kind takes
 {"repo", "confirmed": true, "osaurus": true|false} and the server exposes the same plan as
 `GET /quickbench/plan?repo=R` so the app can show it before the click
```

## AC-2: Stage A, then stage B, one variable each
```gherkin
Given a confirmed run
Then each cell's artifact dir is `fetch.plan(model)`'s snapshot for the catalog revision, never a newest-mtime
 lookup, so the measured bytes are the pinned bytes <!-- audit-added: must-have -->
And stage A builds one `<format>__<engine>=<snapshot dir>` cell per stage-A engine for the chosen repo and runs
 them through `run_cells` with `workloads=[decode]`, `warmup=3`, `measured=5`, `cooldown_s=10`, `quick=True`, and a
 results_dir under `~/Library/Application Support/OhYesMLX/quickbench/<stamp>/A`
And the stage-A winner is the PASS cell with the highest `decode_tps`; cells within 5% of it are reported as a tie,
 and with no PASS cell stage B does not run and the summary says why
And stage B runs the winner engine over the chosen repo plus each sibling (the chosen repo's stage-A row is reused,
 not re-measured), downloading a missing sibling first through `fetch.download` and evicting it through
 `fetch.evict` after its cell, so one extra model at most is on disk at a time; the user's chosen model is never
 evicted, and a sibling OYMLX did not download is never evicted
And each stage's summary carries its can't-claim caveat (A: "engines compared on one format only"; B: "formats
 compared on one engine only"), and every number is labelled "quick: measured on this Mac"
```

## AC-3: Nothing the user owns is changed without consent, and it is put back
```gherkin
Given an engine whose port is already in use by a process quickbench did not start (e.g. the user's own Osaurus)
Then that engine is skipped with the reason "quit <engine> first", and nothing on that port is stopped
And <!-- audit-added: must-have --> Osaurus is also skipped while the Osaurus app process is running at all
 (matched by its full executable path, never by name), because the harness's Osaurus stop path and stale-instance
 sweep would end the user's own app; quickbench never runs that sweep on a user's Mac
And <!-- audit-added: must-have --> before any pin, `osaurus_settings.recover` runs with quickbench's backup dir, and a
 recover that does not verify blocks Osaurus for the run with that reason
And Osaurus runs only when the run was confirmed with `osaurus: true`; then `osaurus_settings.pin` runs before its
 cell with the backup and baseline under Application Support, and `restore` runs in a `finally` after it, and the
 summary records whether the restore verified byte-exact; `osaurus: false` skips Osaurus with that reason
And a failed restore is an `error` event naming the backup directory, never silent
```

## AC-4: Runs as a job, cancellable between cells
```gherkin
Given `POST /jobs {"kind": "quickbench", ...}`
Then it takes the 04-02 slot, streams `progress` per cell and stage, a `result` carrying the summary, then `done`
And each cell is its own `run_cells` call (as `canary` does per engine), which is what makes a between-cells cancel
 possible <!-- audit-added -->
And cancel takes effect between cells (never mid-cell: the harness's stop path still runs), evicts any sibling it
 downloaded, restores Osaurus if pinned, and ends with `cancelled`
And contention is recorded, not refused: `canary.load()` before and after each stage, and a stage above
 `LOAD_NOISY` is labelled "this Mac was busy"
```

## AC-4b: The summary is a record <!-- audit-added: strongly recommended -->
```gherkin
Then `summary.json` beside the stage directories holds the plan as shown, the estimate and the actual seconds,
 every cell's status (PASS/FAIL with reason, skipped with reason), each engine's version and tested flag, the load
 readings, whether Osaurus was pinned and whether its restore verified, and the harness revision; it is written
 atomically, and a run that ends early still writes one saying how it ended
```

## AC-5: Results feed the recommendations
```gherkin
Given a finished quickbench summary under Application Support
Then `GET /recommendations` fills `measured_here` for that repo with {"engine", "decode_tps", "ttft_s",
 "measured_at", "quick": true} from the newest summary, and only ever from runs on this Mac (D5)
```

</acceptance_criteria>

<tasks>
<task type="auto">
  <name>Task 0: app-installed pip engines reach PATH</name>
  <files>ohyesmlx/engines.py, tests/test_engines.py</files>
  <action>AC-0: one atomic writer for `lab-paths.json` beside `lab_paths()`; `install` calls it after a successful pip install. Scratch paths only in tests; never this Mac's real lab-paths.json.</action>
  <verify>pytest green; a fake successful optiq install into a scratch engines dir leaves `{"optiq": "<scratch>/optiq-0.5.13/bin"}` and `_engine_env` with that dir first on PATH</verify>
  <done>AC-0 satisfied</done>
</task>

<task type="auto">
  <name>Task 1: quickbench.py — plan, stages, summary (fakes only)</name>
  <files>ohyesmlx/quickbench.py, tests/test_quickbench.py, ohyesmlx/cli.py, tests/test_cli.py</files>
  <action>AC-1, AC-2, AC-3 with injected seams for run_cells, download, evict, downloaded, pin, restore, port probe and load; the `quickbench` subcommand (approved surface) is a thin caller. One definition for every constant (warmup 3, measured 5, cooldown 10, tie 5% = canary.NOISE_FLOOR, 20 MB/s, per-cell estimate). `--cells` stays the only selector: quickbench composes a `--cells` string and calls `build_cells`, exactly as canary does.</action>
  <verify>pytest green; red-checks: evict the chosen repo -> its test fails; skip the port probe -> the "user's Osaurus running" test fails; drop the restore `finally` -> the failed-cell test sees no restore</verify>
  <done>AC-1, AC-2, AC-3, AC-4b satisfied</done>
</task>
<task type="auto">
  <name>Task 2: the job kind, the plan endpoint, measured_here</name>
  <files>ohyesmlx/server.py, ohyesmlx/recommend.py, tests/test_server.py, tests/test_recommend.py, docs/interfaces.md</files>
  <action>AC-4, AC-5, and AC-1's `GET /quickbench/plan`. The 04-01 guard and 04-02 validation rules apply unchanged; `quickbench` args are a closed set like the others. Pin the job args, the plan shape and the summary shape in docs/interfaces.md.</action>
  <verify>pytest green</verify>
  <done>AC-4, AC-5 satisfied</done>
</task>
<task type="checkpoint:human-verify" gate="blocking">
  <what-built>quickbench end to end</what-built>
  <how-to-verify>
    1. With Jason's go and a quiet machine (a measured run): `ohyesmlx quickbench --repo mlx-community/Qwen3.5-2B-4bit` prints the plan; Jason reads it.
    2. Then `--yes` with Osaurus allowed: stage A over the installed engines, stage B fetching and evicting the oQ4 sibling into a scratch `HF_HUB_CACHE`, total under ~12 minutes.
    3. Coordinator shows: the summary, Osaurus restored byte-exact (`cmp`), all engine ports free, the sibling evicted, `grid` refusing the quick run directory, and `/recommendations` showing `measured_here` for that repo.
  </how-to-verify>
  <resume-signal>"approved", or the issues to fix</resume-signal>
</task>
</tasks>

<boundaries>
## DO NOT CHANGE
- runtimes.py, measure.py beyond 04-03a's pin, the coherence gate, fetch's guards
- engines.py beyond Task 0's lab-paths writer
- The 04-01 guard and 04-02 job rules
## SCOPE LIMITS
- Decode workload only; one model resident; no concurrency; no new selector
- No publishing: quick results live under Application Support and never under results/
</boundaries>

<output>
After completion, create `.paul/phases/v5-onboarding/04-03b-SUMMARY.md`
</output>
