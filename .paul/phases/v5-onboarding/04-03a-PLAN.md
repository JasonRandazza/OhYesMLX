---
phase: 04-server
plan: 03a
plan_type: tdd
wave: 1
depends_on: ["04-02"]
files_modified: [ohyesmlx/catalog.py, ohyesmlx/catalog.json, scripts/build_catalog.py, ohyesmlx/measure.py, ohyesmlx/report.py, ohyesmlx/osaurus_settings.py, scripts/osaurus-pin.sh, tests/test_catalog.py, tests/test_report.py, tests/test_measure.py, tests/test_osaurus_settings.py, docs/interfaces.md]
autonomous: true
description: "Quickbench foundations: catalog base field, the `quick` header pin the join refuses, and one Python Osaurus pin/restore"
type: Plan
about: "OhYesMLX"
---

<objective>
## Goal
Three pieces 04-03b's quickbench stands on, each defined once: a catalog `base` field that names a model's other
formats, a `quick` run-header pin that `grid` and `sweep` refuse outright, and an Osaurus pin/restore in
`osaurus_settings.py` that quickbench and `scripts/osaurus-pin.sh` both use.

## Purpose
Decision 140 and Jason's 2026-11-02 calls: stage B finds sibling formats through `base` (D10); quickbench results
never join the published tables (D9), marked by a header pin Jason approved; on a user's Mac Osaurus is pinned
for the run only with the user's consent and restored byte-exact. Today the pin exists only as shell in
`scripts/osaurus-pin.sh` and re-records a baseline inside the repo (`git checkout` restores it), which a packaged
app has neither of.
</objective>

<context>
@ohyesmlx/catalog.py, ohyesmlx/catalog.json, scripts/build_catalog.py (the seed is built from Hub listings)
@ohyesmlx/report.py `PIN_FIELDS` and the grid/sweep join guards; @ohyesmlx/measure.py run header
@ohyesmlx/osaurus_settings.py (`capture_osaurus_settings`, `write_baseline`, `diff_against_baseline`, `BASELINE_PATH` under the repo's config/)
@scripts/osaurus-pin.sh (`osaurus_pin`, `osaurus_restore`, `osaurus_restore_check`: copy both config files, set idle 900 and both caches off, re-record the baseline, restore and verify with cmp)
AGENTS.md: Osaurus runs go through the pin; Jason's settings (idle 30) restored byte-exact and verified with cmp.
</context>

<acceptance_criteria>

## AC-1: Catalog `base` <!-- audit: strengthened -->
```gherkin
Given `catalog.json`
Then every row carries `base`: a string naming the base model (e.g. "Qwen3.5-0.8B"), the same for every format of
 one base and different across bases; `Model.base` exposes it; a missing or non-string `base` is a ValueError
 naming the repo
And `catalog.siblings(model, models) -> list[Model]` returns the other rows with the same `base`, in catalog order
And today's catalog gives Qwen3.5-0.8B (4bit, OptiQ) and Qwen3.5-2B (4bit, oQ4) as the only bases with two rows,
 pinned by a test listing every base with its rows, so a hand-entry mistake fails loudly <!-- audit-added -->
And `scripts/build_catalog.py` writes the field, so a rebuild does not drop it
```

## AC-2: The `quick` header pin
```gherkin
Given `measure.run_cells(..., quick=False)`
Then the run header records `quick` (bool), and `quick` joins `report.PIN_FIELDS`
And `grid` and `sweep` refuse any run directory whose header has `quick: true`, with a message naming the
 directory and saying quickbench results never join the published tables; a header without the key loads as false
And a quick-vs-quick pair is refused too: refusal is on the value, not on a mismatch
And <!-- audit-added: must-have --> false compares equal to an absent key, so every existing run still joins exactly
 as before (a test joins two pre-04-03a run fixtures)
```

## AC-3: One Osaurus pin, with a restore that proves itself
```gherkin
Given `osaurus_settings.pin(config_dir=None, backup_dir=..., baseline_path=...)`
Then it copies `server-runtime.json` and `server.json` byte-exact into backup_dir, sets
 `modelIdleResidencyPolicy.seconds = 900`, `cache.prefix.enabled = false` and `cache.blockDisk.enabled = false`,
 and writes the baseline the drift guard reads to baseline_path (never the repo's config/ unless passed)
And `osaurus_settings.restore(...)` puts both files back and returns True only when each is byte-identical to its
 backup (a `filecmp.cmp(shallow=False)` check), then removes the backup; False leaves the backup in place
And a second `pin` while a backup exists refuses (ValueError) rather than overwriting the user's original
And <!-- audit-added: must-have --> a crash between `pin` and `restore` cannot strand the user's settings:
 `osaurus_settings.recover(backup_dir=...)` restores from a leftover backup (same byte-exact check) and is a no-op
 without one, so 04-03b calls it before any new pin and the app can call it at launch
And <!-- audit-added: must-have --> every config write is atomic (write a temp file in the same directory, then
 `os.replace`), so a kill mid-write never leaves a half-written Osaurus config; the backup directory is created 0700
And <!-- audit-added: strongly recommended --> the pin and restore write one JSON line each to the caller's log or
 stderr naming the files and the outcome (never their contents)
And `scripts/osaurus-pin.sh` calls these functions instead of carrying its own copy of the edit, with its cmp check
 and trap unchanged in behaviour (Jason's host restored byte-exact)
```

</acceptance_criteria>

<tasks>
<task type="auto">
  <name>Task 1: catalog base and siblings</name>
  <files>ohyesmlx/catalog.py, ohyesmlx/catalog.json, scripts/build_catalog.py, tests/test_catalog.py, docs/interfaces.md</files>
  <action>AC-1. Add `base` to the 12 rows by hand from each repo's own base model (the title carries it); the builder writes it from its input table. Pin `base` in the Model shape in docs/interfaces.md.</action>
  <verify>pytest green; `catalog.siblings` of Qwen3.5-2B-4bit returns the oQ4 row and nothing else</verify>
  <done>AC-1 satisfied</done>
</task>
<task type="auto">
  <name>Task 2: the quick pin and the join refusal</name>
  <files>ohyesmlx/measure.py, ohyesmlx/report.py, tests/test_measure.py, tests/test_report.py, docs/interfaces.md</files>
  <action>AC-2. `quick` defaults False everywhere a header is built, so every existing run and test is unchanged; the refusal lives with the existing join guards. Red-check: remove the refusal and the quick-vs-quick test fails.</action>
  <verify>pytest green; `ohyesmlx grid` on a scratch dir whose header says quick:true refuses</verify>
  <done>AC-2 satisfied</done>
</task>
<task type="auto">
  <name>Task 3: Python pin/restore, and the shell script uses it</name>
  <files>ohyesmlx/osaurus_settings.py, scripts/osaurus-pin.sh, tests/test_osaurus_settings.py</files>
  <action>AC-3, tests on a scratch config dir only (never ~/.osaurus). Audit-added tests: recover after a simulated crash (backup present, files pinned) restores byte-exact; recover without a backup is a no-op; a write interrupted between temp and replace leaves the original intact; the backup dir mode is 0700. Keep `BASELINE_PATH` as the default for the harness; quickbench will pass an Application Support path. The shell's trap, its sweep and `osaurus_restore_check`'s cmp stay; only the inline Python and copies move into the module.</action>
  <verify>pytest green; coordinator runs `scripts/run_canary.sh` for Osaurus only if Jason says go (a measured run); otherwise a dry check that `osaurus_pin` then `osaurus_restore_check` round-trips a scratch copy</verify>
  <done>AC-3 satisfied</done>
</task>
</tasks>

<boundaries>
## DO NOT CHANGE
- runtimes.py, server.py, fetch.py, engines.py, recommend.py
- Any published result directory; the committed `config/osaurus-settings-baseline.json` content
## SCOPE LIMITS
- No quickbench itself (04-03b); no measured run without Jason's go
</boundaries>

<output>
After completion, create `.paul/phases/v5-onboarding/04-03a-SUMMARY.md`
</output>
