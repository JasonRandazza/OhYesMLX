---
phase: 04-server
plan: 03c
plan_type: execute
autonomous: true
description: "Quickbench pins Osaurus against the baseline the drift guard reads, and the pin backs that baseline up and restores it byte-exact with the two config files"
type: Plan
about: "OhYesMLX"
---

<objective>
## Goal
A quickbench run with `--osaurus` measures the Osaurus cell instead of reporting it N/A, and afterwards the
user's two Osaurus configs **and** the drift guard's baseline file are byte-identical to what they were before the
pin.

## Why
`04-03b-SUMMARY.md`, "Known gap". `quickbench.run` passes `baseline_path=DEFAULT_BASELINE_PATH` (under Application
Support) to `osaurus_settings.pin`, but `runtimes.Osaurus.check_host_state` calls `load_baseline()` with no path,
so it reads `osaurus_settings.BASELINE_PATH` (the repo's `config/osaurus-settings-baseline.json`, caches on). The
pinned host (caches off) reads as drift and the cell is refused. A plan defect, not a code defect.
`scripts/osaurus-pin.sh` avoids it by pinning against the default path and undoing the baseline write with
`git checkout`, a second, git-dependent definition of "put the baseline back".
</objective>

<context>
@ohyesmlx/osaurus_settings.py (`pin`, `restore`, `recover`, `_backups`, `_put_back`, `PIN_FILES`, `BASELINE_PATH`)
@ohyesmlx/quickbench.py (`DEFAULT_BASELINE_PATH` line 93, `run`'s `baseline_path` parameter, `measure_cell`)
@ohyesmlx/runtimes.py (`Osaurus.check_host_state` line 2342, read only: not to be changed)
@scripts/osaurus-pin.sh (the two `git checkout -- config/osaurus-settings-baseline.json` lines)
@tests/test_osaurus_settings.py, @tests/test_quickbench.py
Where the baseline lives in a packaged app (no repo `config/`) is a Phase 4.5 decision, not this plan's.
</context>

<acceptance_criteria>
## AC-1: The pin backs up the baseline it overwrites, and restore puts it back byte-exact
Given a baseline file at `baseline_path` (default `BASELINE_PATH`)
When `pin(config_dir, backup_dir=…, baseline_path=…)` runs
Then a byte-exact copy of that baseline is in `backup_dir` before `write_baseline` replaces it
And `restore(config_dir, backup_dir=…, baseline_path=…)` and `recover(…)` put it back through `_write_atomic`,
 verify it with the same `filecmp.cmp(shallow=False)` as the configs, and return `True` only when all three files
 match; on any mismatch every backup is kept
And when no baseline existed at pin time, the backup records that (a marker file in `backup_dir`) and a successful
 restore deletes the baseline the pin wrote, so the guard is left exactly as ungated as it was
And `pin` still refuses over an existing backup, now including a leftover baseline backup or marker

## AC-2: Quickbench pins against the guard's baseline
Given `quickbench.run(…, osaurus=True)`
When it pins, restores and recovers Osaurus
Then all three calls use the same baseline path, and that path is the one `check_host_state` reads (default
 `osaurus_settings.BASELINE_PATH`); `quickbench.DEFAULT_BASELINE_PATH` is deleted, and a test asserts the pinned
 host passes `diff_against_baseline` against `load_baseline()` (no drift) between pin and restore

## AC-3: One definition of "put the baseline back"
Given `scripts/osaurus-pin.sh`
Then both `git checkout -- config/osaurus-settings-baseline.json` lines are gone and `restore` alone puts the
 baseline back; `osaurus_set_seqs`'s mid-run `write_baseline()` still works, because restore returns the pre-pin
 bytes regardless of later writes
And the module docstring's pin paragraph and the script's header comment say the baseline is backed up and
 restored with the configs (each rationale once, where it is defined)

## AC-4: Live
Given Jason's go and a quiet machine (HANDOFF recipe), `ohyesmlx quickbench --repo mlx-community/Qwen3.5-2B-4bit
 --osaurus --yes`
Then the Osaurus stage-A cell is PASS with a tok/s figure, `summary.json` has `osaurus.restored: true`, and the
 coordinator's own `cmp` shows `~/.osaurus/config/server{,-runtime}.json` and `config/osaurus-settings-baseline.json`
 identical to pre-run copies, no backup directory left, `git status` clean
</acceptance_criteria>

<tasks>
<task type="auto">
  <name>Baseline joins the pin's backup set</name>
  <files>ohyesmlx/osaurus_settings.py, tests/test_osaurus_settings.py</files>
  <action>
    - `pin` copies `baseline_path` into `backup_dir` (fixed name, e.g. `baseline.json`) before `write_baseline`; absent → write an empty marker `baseline.absent` instead.
    - `restore` and `recover` gain `baseline_path: Path | None = None` (default `BASELINE_PATH`); `_backups`/`_put_back` map each backup to its target (configs → `config_dir`, baseline → `baseline_path`), restore the marker case by deleting the baseline, and remove the marker only on full success.
    - Keep every write atomic and the backup dir `0700`; `_log` lists the baseline among `files`.
    - Tests (tmp paths only, never the real `BASELINE_PATH` or `~/.osaurus`): baseline restored byte-exact after pin + a later `write_baseline`; absent-baseline case leaves no baseline; a tampered baseline after restore attempt returns `False` and keeps the backups; `pin` refuses over a leftover `baseline.json` or `baseline.absent`; `recover` restores all three.
  </action>
  <verify>pytest green; red-check: drop the baseline copy from `pin` and the byte-exact test fails</verify>
  <done>AC-1</done>
</task>
<task type="auto">
  <name>Quickbench and the shell runner use it</name>
  <files>ohyesmlx/quickbench.py, tests/test_quickbench.py, scripts/osaurus-pin.sh</files>
  <action>
    - Delete `DEFAULT_BASELINE_PATH`; `run`'s `baseline_path` defaults to `osaurus_settings.BASELINE_PATH` and is passed to `recover`, `pin` and `restore` alike. Keep the existing comment's reason for fixed backup paths.
    - Test: with real `pin`/`restore` on tmp config + tmp baseline, the host captured between pin and restore shows no drift against `load_baseline(baseline_path)`; the injected fakes receive the same `baseline_path` in all three calls.
    - Script: remove both `git checkout` lines; update the header comment in one sentence.
  </action>
  <verify>pytest green; `bash -n scripts/osaurus-pin.sh`; `graphify update .`</verify>
  <done>AC-2, AC-3</done>
</task>
<task type="checkpoint:human-verify">
  <name>Live quickbench with Osaurus (Jason's go)</name>
  <action>Coordinator runs the HANDOFF recipe after copying the two configs and the repo baseline; nothing else runs.</action>
  <done>AC-4</done>
</task>
</tasks>

<boundaries>
No change to `runtimes.py`, `TRACKED_KEYS`, the pinned values, or the committed baseline's contents. No new module,
subcommand or dependency. Touch only the five files named in the tasks.
</boundaries>

<output>
After completion, the coordinator writes `.paul/phases/v5-onboarding/04-03c-SUMMARY.md` and flips 04-03b's AC-3 to
Pass in `04-03b-SUMMARY.md`.
</output>
