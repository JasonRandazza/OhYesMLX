# Order: plan 05-07 Task 1 — engine-scoped lab PATH, load window, smeltMode attestation (S5-F1, S5-F2, S5-F9)

Read `.paul/phases/v5-onboarding/05-07-PLAN.md`: the "Facts" in <context>, AC-2, AC-4, AC-15, Task 1, <boundaries>.
Finding details: `.paul/review/fable-5.2/S5-findings.md` (grep "### F1 ", "### F2 ", "### F9 ").

Working tree: this worktree (branch fix/05-07-t1). Commit there when green; do not push, do not merge.

Step 1: `git checkout review/fable-verify -- tests/test_fable_s5_f1.py tests/test_fable_s5_f2.py tests/test_fable_s5_f9.py`,
run them, confirm they FAIL. Do not edit these three files, ever. If one cannot pass as written, report BLOCKED with why.

Step 2, the fix (one definition each):
- `_engine_env(engine, ...)` prefixes only *engine*'s lab bin; refusal for a missing/invalid lab copy applies to that
  engine only. `_spawn` receives the engine name from `Runtime.start`.
- `_run(command, timeout_s, engine=None)`: no lab prefix without an engine. `Runtime.version()` passes `self.name`.
- Add ONE test to tests/test_runtimes.py: with a fake lab-paths file naming optiq, OptiQ's start env AND its version
  probe env put OptiQ's lab bin first, and mlx-lm's env does not contain it.
- `Runtime.start`: `cold_load_s` taken on the line right after `await_ready` returns; `self.version()` after it, still
  inside the try whose except cleans up a failed start; `_serving_pid` and ledger write after. Fix the AC-6 comment.
- Add `concurrency.smeltMode` to `osaurus_settings.TRACKED_KEYS`; delete the ad hoc reader/sentinel copy in runtimes.py
  (~:392, :951-969, :2638-2664) so callers use the tracked capture.
- Update the three ohyesmlx/engines.py docstrings (~:390, :417, :597) that say "every engine start". Docstrings only.
- Do NOT change stop-path behaviour beyond what the signature change requires (S5-F10 and S5-F5 are a later plan).

Files: ohyesmlx/runtimes.py, ohyesmlx/osaurus_settings.py, ohyesmlx/engines.py (docstrings), tests/test_runtimes.py
(one added test), the three red tests. Touch nothing else. Do not spawn subagents. Start no server, run no measurement.

Suite: `/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python -m pytest -q` must be green (baseline 1370 on main).

Report: per AC the command and output; the diff stat; any existing test you would have had to change (do not change it,
report BLOCKED); what you did not verify.

## Coordinator rulings (a first worker found these contradictions; they are settled — do not re-probe them)

R1. Signatures. The red tests call `_engine_env(manifest, lab_paths)` positionally and expect NO lab bin when no engine
is named, and they stub `_spawn(command, log_path)` and `_run(command, timeout_s)` with exactly two parameters. So:
- `_engine_env(manifest_path=None, lab_paths_path=None, *, engine=None)`: engine None → no lab prefix at all;
  engine given → that engine's lab bin only, with the existing refusal for a missing/invalid lab copy.
- Do NOT change the signatures of `_spawn` or `_run`. Instead add one helper, e.g.
  `_engine_command(engine, command) -> (command, env)` or similar, that resolves the program token against
  `_engine_env(engine=engine)`'s PATH to an absolute path ONLY when that PATH finds it (otherwise the command is
  returned unchanged — the f2 stub matches `("fake-engine", "--version")` exactly). `Runtime.start` and
  `Runtime.version` call it before `_spawn` / `_run`.
- Inside `_spawn` (and `_run`), the child env is `_engine_env()` (no prefix) plus, when `command[0]` is absolute and its
  directory is one of the configured lab bins, that one directory first — so an OptiQ child still finds its own venv's
  tools on PATH, and nothing else gets it. Reuse `lab_paths()`; one definition.
- Replace the order's "_run gains engine=" and "_spawn gets the engine name" lines with the above.

R2. test_fable_s5_f9.py MAY be edited, and only in these three places (record each in the report):
- `test_the_gate_is_green_across_disabled_to_ssd_streaming` and
  `test_only_continuous_batching_and_max_sequences_are_tracked_under_concurrency` pin the defect; invert them to assert
  the fixed behaviour (drift reported across disabled→ssdStreaming; smeltMode IS tracked), renaming them to match.
- `test_RED_the_gate_refuses_a_host_whose_per_model_thinking_switch_differs` (the plist half, out of scope) gets
  `@pytest.mark.xfail(strict=True, reason="S5-F9 plist disableThinking: deferred to Jason at 05-07 UNIFY")`.
- Keep the name `runtimes.osaurus_smelt_mode` (a test monkeypatches it), but make it read the key through the
  osaurus_settings capture / TRACKED_KEYS path instead of its own copy of the key path. One definition of the key.
test_fable_s5_f1.py and test_fable_s5_f2.py stay unedited.

Write code now: first edit within your next ~10 turns.
