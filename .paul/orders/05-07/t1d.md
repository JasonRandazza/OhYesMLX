# Order: plan 05-07 Task 1, finishing step (continuation)

This worktree (fix/05-07-t1) holds your earlier, uncommitted Task 1 source change. Keep it. Context: t1c.md in
/Users/jrazz/Dev/active/OhYesMLX/.paul/orders/05-07/ (rulings R1-R5 still apply). Do not change ohyesmlx/*.py further
unless a failing test below shows a real defect in it — then say so in the report.

Coordinator already fixed the red test's ambient-PATH filter in tests/test_fable_s5_f1.py; your BLOCKED is resolved.

Your one job: make these existing tests pass by updating them to the new engine-scoped semantics (R3) — pass
`engine=` where a test expects a lab prefix, keep each test's intent (refusals, ordering, pass-through), and keep
each test name. Failing now:
```
FAILED tests/test_engines.py::test_a_successful_pip_install_records_its_venv_bin_and_engine_env_prefixes_it
FAILED tests/test_runtimes.py::test_start_returns_a_handle_only_after_the_model_id_appears
FAILED tests/test_runtimes.py::test_vmlx_starts_without_a_key_and_records_the_version_it_read
FAILED tests/test_runtimes.py::test_capture_reads_every_tracked_measurement_key
FAILED tests/test_runtimes.py::test_osaurus_starts_when_the_settings_match_the_baseline
FAILED tests/test_runtimes.py::test_version_absence_says_why - AssertionError...
FAILED tests/test_runtimes.py::test_vmlx_version_does_not_come_from_a_flag_that_errors
FAILED tests/test_runtimes.py::test_vmlx_version_absence_says_which_way_it_was_absent
FAILED tests/test_runtimes.py::test_a_lab_path_is_prefixed_to_path_and_the_rest_of_the_environment_passes_through
FAILED tests/test_runtimes.py::test_a_lab_path_that_does_not_exist_is_refused_naming_the_engine
FAILED tests/test_runtimes.py::test_the_machine_local_file_overrides_the_manifests_lab_path_for_one_engine
FAILED tests/test_runtimes.py::test_a_lab_path_only_in_the_machine_local_file_is_prefixed
FAILED tests/test_runtimes.py::test_the_manifest_lab_path_still_applies_to_an_engine_the_local_file_omits
FAILED tests/test_runtimes.py::test_a_missing_machine_local_file_leaves_the_manifest_alone
FAILED tests/test_runtimes.py::test_a_machine_local_lab_path_that_does_not_exist_is_refused_naming_the_engine
FAILED tests/test_runtimes.py::test_a_lab_path_that_must_not_join_path_is_refused_at_start[relative]
FAILED tests/test_runtimes.py::test_a_lab_path_that_must_not_join_path_is_refused_at_start[file]
FAILED tests/test_runtimes.py::test_a_lab_path_that_must_not_join_path_is_refused_at_start[group-writable]
FAILED tests/test_runtimes.py::test_a_lab_path_that_must_not_join_path_is_refused_at_start[other-writable]
FAILED tests/test_runtimes.py::test_a_lab_path_nobody_else_can_write_is_still_prefixed
FAILED tests/test_runtimes.py::test_a_lab_path_owned_by_another_user_is_refused_at_start
```
Investigate test_vmlx_version_absence_says_which_way_it_was_absent and any non-_engine_env failure on its own:
it may be a real regression from the source change (fix the source if so).

Then run the full suite (test-venv pytest -q) to green, and commit everything in this worktree as one commit.
Files allowed: tests/test_runtimes.py, tests/test_engines.py, tests/test_paths.py, and ohyesmlx/runtimes.py only for a
real regression. Do not spawn subagents. Report: each edited test and why; full-suite output; diff stat.
