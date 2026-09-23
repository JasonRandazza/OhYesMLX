Scope: Read AGENTS.md, ohyesmlx/*.py, tests/*.py and docs/interfaces.md; baseline STATE reports 497 tests; permitted suite run: 497 passed.

| Rule | Code enforcement | Test evidence |
|---|---|---|
| TTFT is request-to-first content token; reasoning is not content. | **UNENFORCED as specified:** `transport.py:351-375, 365-375` substitutes reasoning timing for mirrored/reasoning-only streams. | `test_reasoning_only_stream_times_and_counts_its_reasoning_deltas` tests the contrary behavior; `test_ttft_ignores_reasoning_deltas_and_counts_content_only` covers ordinary content streams. |
| ITL / TPOT is mean gap between successive output tokens after first. | `measure.py:297-306`; published path also gates on at least two deltas in `report.py:1039-1045`. | `test_the_metric_formulas_are_the_documented_ones` (`test_measure.py`); `test_a_one_delta_cell_omits_the_rates_its_stream_cannot_support` (`test_report.py`). |
| End-to-end latency is P50/P90/P99, never a bare mean. | **UNENFORCED:** only TTFT percentile fields are summarized/rendered; no end-to-end percentile metric exists (`report.py:752-759`). | `test_five_samples_produce_real_percentiles_and_no_note` tests TTFT percentiles only; end-to-end latency UNTESTED. |
| Per-request and aggregate output throughput are separate. | `report.py:756-759, 1048-1094`; concurrent runs use batch spans. | `test_decode_and_aggregate_throughput_are_two_different_numbers`; `test_aggregate_throughput_divides_by_the_batch_spans_not_the_summed_requests`. |
| Cold load is separate from request timing. | `measure.py:763-770`; `report.py:824-875` and `CROSS_RUNTIME_UNCOMPARABLE` explain deferred load. | `test_cold_load_comes_from_the_handle_and_never_into_a_request`; `test_first_request_is_its_own_column_and_the_cold_load_is_not_summed_into_it`. |
| Peak memory uses `footprint -p`; never `ps` RSS; no cross-runtime ranking. | Sampling uses `/usr/bin/footprint -p` (`sample.py:108-114, 262-278`). **UNENFORCED cross-runtime prohibition:** `report.py:176-185, 1702-1711` still orders `peak_mb` on the runtime axis, with a warning. | `test_phys_footprint_mb_on_a_live_process`; `test_the_runtime_axis_refuses_to_rank_a_metric_that_is_not_one_quantity` actually asserts the ordering remains printed. |
| On-disk size includes sidecars. | `measure.py:339-357` walks all files and deduplicates inode aliases. | `test_disk_bytes_counts_sidecar_files_and_each_inode_once`. |
| Temperature 0 and fixed seed. | `measure.py:175-176, 931-933` pins 0 and 0 on each request and records both. | `test_every_request_pins_temperature_zero_and_the_fixed_seed`. |
| Fixed chat template and output length. | CLI pins workload prompt literals and caps (`cli.py:25-31, 226-248`); run header stores workload messages/caps (`measure.py:466-473`). | `test_every_request_carries_its_workload_s_max_tokens`; `test_persisted_header_names_all_three_workloads_and_every_line_names_its_own`. |
| Runtime versions recorded for every run. | `runtimes.py:639-653, 763-774`; **partial:** unavailable probes become generic `unknown` values and are not made unrankable. | `test_runtime_version_is_recorded`; `test_version_absence_says_why`; `test_guard_4_refuses_one_runtime_measured_at_two_versions`. |
| Pin `top_p` and `repetition_penalty`. | **UNENFORCED:** runtime start commands do not set these pins (`runtimes.py:807-819, 834-841, 929-954, 987-1021, 1118-1151`); Osaurus tracked settings omit them (`osaurus_settings.py:34-58`). | UNTESTED. |
| Raw observations, including failures and warmups, are retained; summaries recomputable. | `measure.py:1149-1177, 1202-1215, 1230-1269`; load recomputes derived values. | `test_every_measured_observation_is_retained_untruncated`; `test_every_failed_request_is_still_retained_as_an_observation`; `test_summaries_stay_recomputable_from_the_jsonl`. |
| `--cells` is the only selector; one axis varies. | `cli.py:371-430, 584-609`; `report.py:375-399, 1097-1133`. | `test_cells_is_the_only_cell_selector_the_cli_has`; `test_study_runtime_refuses_a_selection_that_varies_the_format`; `test_study_format_refuses_a_selection_that_varies_the_runtime`. |
| No governance layer. | Deliberately absent; no measurement implication. | UNTESTED (not a runtime invariant). |
| No new dependency without naming its replacement. | Package stays stdlib-only in the reviewed imports. Commit-message replacement claim is not checked by source. | `test_modules_stay_on_the_standard_library`; commit-message part UNTESTED. |
| Downloads have phase reason/record and never overlap measurement. | **UNENFORCED:** no download or host-activity gate in `run_cells`; see also quiet-machine rule below. | UNTESTED. |
| No accuracy scoring in v1. | No accuracy-scoring surface in the reviewed modules; no speed/memory row depends on one. | UNTESTED. |
| One definition per formula/guard/size/constant. | `measure.py:268-306, 339-357`; report delegates metric formulas/drift to measure (`report.py:1025-1045, 730-732`). | `test_report_asks_measure_what_came_back_rather_than_respelling_it`; `test_report_asks_measure_for_the_drift_rather_than_recomputing_it`; disk sidecar test above. |
| Each rationale is written once at its definition. | **UNENFORCED** as a prose-maintenance rule; no number impact established. | UNTESTED. |
| Run `graphify update .` after Python edits. | **UNENFORCED** by the package/test suite; workflow rule only. | UNTESTED. |
| Ask before adding modules, subcommands, or header pins. | **UNENFORCED** by code; approval/workflow rule, not a published-number guard. | UNTESTED. |
| OptiQ expert streaming is explicitly off. | `runtimes.py:1014-1020` passes `--no-stream-experts`. | `test_optiq_pins_expert_streaming_off_rather_than_leaving_it_auto`. |
| OptiQ max-context is `off`, not a rotating integer cap. | `runtimes.py:1002-1007` pins `--max-context off`. | `test_optiq_start_command_is_pinned`. |
| Osaurus settings are snapshotted/diffed against baseline before runs. | `runtimes.py:908-923` checks tracked settings when a baseline loads. **Partial:** absent/unreadable baseline silently disables the gate (`osaurus_settings.py:100-108`). | `test_osaurus_refuses_to_start_when_the_host_drifted_from_the_baseline`; `test_osaurus_starts_when_no_baseline_has_been_recorded` exercises the fail-open case. |
| oMLX gets a per-run catalog containing only the cell model. | `runtimes.py:447-465, 968-981` creates a fresh one-link catalog/base. | `test_omlx_injects_a_per_run_catalog_a_base_path_and_a_key`. |
| Clear oMLX SSD prefix cache between cold-cache runs. | Fresh per-run base and scratch cleanup (`runtimes.py:447-465, 468-493, 600-603`) isolate its cache. | `test_omlx_injects_a_per_run_catalog_a_base_path_and_a_key`; `test_stop_removes_the_omlx_scratch_it_created`. |
| Ports released after runs. | `Handle.stop` calls shutdown and `await_port_free` (`runtimes.py:526-562, 600-603`). | `test_stop_does_not_return_while_the_port_is_still_held`; `test_stop_verifies_the_port_even_when_the_process_already_exited`. |
| Incoherent cell fails, retains sample, publishes no metrics. | `measure.py:1030-1109, 1149-1215`; report excludes failed rows (`report.py:938-981`). | `test_an_incoherent_cell_fails_and_keeps_the_sample_that_failed`; `test_a_fast_cell_that_failed_a_floor_does_not_rank`. |
| Exactly one model resident; stop prior runtime before next. | Run visits stop each started handle (`measure.py:688-775`); shutdown kills listeners and waits for port (`runtimes.py:544-562`). **UNENFORCED for stale, unbound Osaurus apps:** only port listeners are discovered. | `test_the_handle_is_stopped_after_every_visit_even_when_requests_fail`; `test_stop_kills_the_process_the_launcher_left_holding_the_weights`; no test for a stale app that no longer holds its port. |
| Interleave order, cooldown, record drift. | `measure.py:325-337, 367-373, 514-535`; report annotates drift. | `test_cells_are_visited_in_alternating_order`; `test_a_cooldown_sits_between_visits_and_not_after_the_last_one`; `test_drift_across_the_window_is_recorded`. |
| Nothing else runs on machine while measuring. | **UNENFORCED by design:** no global activity/exclusivity gate; AGENTS.md says discipline holds without enforcement. | UNTESTED. |
| Never edit Python source during a grid; merge after. | **UNENFORCED:** run header has measurement pins but no harness revision/digest (`measure.py:466-493`); explicit CLI joins cannot detect differing harness code. | UNTESTED. |
| Discard only for stated condition defect; preserve named directory. | **UNENFORCED:** joins consume only explicitly supplied paths (`cli.py:336-366`); no discard provenance or required-run-set check. | UNTESTED. |
| Sweep stale Osaurus instances by executable path, not process name. | **UNENFORCED:** start checks port only (`runtimes.py:723-740`); shutdown discovers processes by currently held port (`runtimes.py:246-267, 544-562`). | `test_stop_kills_the_process_the_launcher_left_holding_the_weights` covers a current listener, not a stale port-free app. |
| Use mlx-lm's dedicated venv and verify `from mlx_lm import load`. | **UNENFORCED:** starts `python -m mlx_lm.server` from PATH (`runtimes.py:807-819`); no venv/import preflight. | UNTESTED. |

### F1 [high] Reasoning-only generations are published as content TTFT and throughput
Where: `AGENTS.md:36`; `ohyesmlx/transport.py:351-375, 387-424`
Evidence:
> - **TTFT** — request sent → first *content* token. Includes prefill. Reasoning tokens are not content.
>
>         reasoning_only = bool(reasoning_text) and not joined
>         if mirrored or reasoning_only:
>             stream_ttft_s, stream_last_s, stream_events = (
>                 first_reasoning,
>                 last_reasoning,
>                 reasoning_event_count,
>             )
>
>         accounting_reasoning_text = (
>             "" if (mirrored or reasoning_only) else reasoning_text
>         )
Failure: on a reasoning-only response, the reasoning stream's timestamps/count are relabeled as content; a runtime can therefore rank on reasoning-token latency/throughput while the metric definition excludes those tokens. The test `test_reasoning_only_stream_times_and_counts_its_reasoning_deltas` locks in that opposite behavior.
Fix: retain reasoning text for the coherence gate, but leave content timing/count/token metrics unavailable for reasoning-only responses (or explicitly revise the metric contract before publishing them).

### F2 [high] Runtime sampler defaults are not held constant
Where: `AGENTS.md:44-46`; `ohyesmlx/runtimes.py:807-819, 834-841, 929-954, 987-1021, 1118-1151`
Evidence:
> Every measured run pins temperature 0, a fixed seed, a fixed chat template, and a fixed
> output length, and records every runtime's version. Runtimes ship different default
> `top_p` and `repetition_penalty`; leaving them unpinned invalidates the comparison.
>
>     def start_command(
>         self, artifact_dir: str, model_id: str, *, cache_state: str | None = None
>     ) -> tuple[str, ...]:
>         return (
>             "python",
>             "-m",
>             "mlx_lm.server",
>             "--model",
>             artifact_dir,
>             "--port",
>             str(self.port),
>             *prompt_cache_flags(cache_state),
>         )
Failure: the selected runtimes can apply different top-p/repetition defaults; output lengths, token paths, and generation speed then differ for sampler reasons while the header contains no such pin for the join to compare.
Fix: explicitly pin both sampler parameters consistently wherever supported and record/compare those values as run pins.

### F3 [high] An absent or unreadable Osaurus baseline bypasses the drift gate
Where: `ohyesmlx/osaurus_settings.py:100-108`; `ohyesmlx/runtimes.py:914-923`
Evidence:
>     try:
>         payload = json.loads(target.read_text())
>     except (OSError, ValueError):
>         return None
>
>         baseline = load_baseline()
>         if baseline is None:
>             return
Fix: distinguish an intentionally unconfigured checkout from an expected-but-missing/unreadable checked-in baseline, and fail closed in the latter case.

### F4 [high] A stale port-free Osaurus process can keep another model resident
Where: `AGENTS.md:71, 76`; `ohyesmlx/runtimes.py:246-267, 544-562, 734-740`
Evidence:
> - **Stale Osaurus instances accumulate.** `osaurus stop` frees the port and leaves the app alive at ~900 MB, so a port sweep misses it by design; three aged 5–7 h were resident through both grids on 2026-09-16.
>
>     listeners = _listener_pids(port)
>     if stop_command:
>         _run(stop_command, STOP_TIMEOUT_S)
>     if _process_alive(pid):
>         _signal_tree(pid, signal.SIGTERM)
>         if not _await_exit(pid, TERM_GRACE_S):
>             _signal_tree(pid, signal.SIGKILL)
>             _await_exit(pid, KILL_GRACE_S)
>     _kill_resident(tuple(other for other in listeners if other != pid))
>     await_port_free(port)
>
>         if not _port_is_free(self.port):
>             raise RuntimeStartError(
Failure: after a prior `osaurus stop` frees the port but leaves its app resident, the next run's port check passes and this code has no PID to sweep; the leftover model consumes memory during a published cell, violating the one-resident-model condition.
Fix: before an Osaurus start, identify and reject/clean only stale processes by the documented full executable path, never by process name.

### F5 [high] External machine activity and downloads can contaminate measurements without a gate
Where: `AGENTS.md:55, 73`; `ohyesmlx/measure.py:514-535`
Evidence:
> - **Downloads need a reason and a record.** ... **Never download while a measurement is running** — it competes for the disk that `cold_load_s` is timing.
>
> - **Nothing else runs on this machine while a cell is measured.** ... the harness cannot detect contention, so this rule holds without enforcement.
>
>         write_jsonl(results, results_path, run=run)
>         # A cooldown after a visit that started no runtime and took no sample is 30
>         # seconds spent cooling nothing.
>         sampled = sum(len(result.observations) for result in cell_results)
Failure: a concurrent download or workload can contend for disk, CPU, GPU, or memory and change cold-load/throughput/footprint figures; no runner check detects or records that condition.
Fix: make the required quiet-machine/exclusive-run precondition explicit at run launch and refuse or clearly invalidate a run when the precondition is not met; keep model downloads outside measurement windows.

### F6 [medium] Runtime-axis joins still print rankings for incomparable peak and cold-load values
Where: `ohyesmlx/report.py:287-296, 1702-1712`; `tests/test_report.py:2778-2804`
Evidence:
> CROSS_RUNTIME_UNCOMPARABLE = {
>     "peak_mb": "`footprint` does not measure the same pages in every runtime: in the "
>     "2026-09-16 grid four columns report a footprint within a few percent of their weight "
>     "bytes and Osaurus reports roughly half of its, below the weights it is serving, while "
>     "its resident size sits at them. Read this row as five numbers, not as a ranking, until "
>     "the sampler is probed against a runtime that maps its weights file-backed.",
>     "cold_load_s": "a lazy loader defers part of its load past readiness and into request #1, "
>     "where `first_request_s` records it. A cross-runtime load comparison is the sum of the "
>     "two, not this column alone.",
> }
>
>         if rank in CROSS_RUNTIME_UNCOMPARABLE:
>             lines += [
>                 f"> **`{rank}` is not one quantity across runtimes.** "
>                 f"{CROSS_RUNTIME_UNCOMPARABLE[rank]}",
>                 "",
>             ]
>
>     for metric in report.CROSS_RUNTIME_UNCOMPARABLE:
>         rendered = report.render_grid(runs, rank=metric)
>         assert f"`{metric}` is not one quantity across runtimes" in rendered, metric
>         # the ordering is still printed: the reader is warned, not denied the numbers
Failure: the grid visibly orders runtimes by `peak_mb` or `cold_load_s` even though each is explicitly declared non-comparable; a reader can quote the ranking as a cross-runtime winner. The test confirms warning-only behavior.
Fix: refuse those runtime-axis ranks (or rank a correctly defined comparable composite for cold start); retain the raw figures and allow within-runtime format comparisons.

### F7 [medium] End-to-end latency percentiles required by the metric contract are not reported
Where: `AGENTS.md:38`; `ohyesmlx/report.py:208-221, 752-759`
Evidence:
> - **End-to-end latency** — P50 / P90 / P99. Never report a bare mean.
>
> CARD_FIELDS = (
>     ("ttft_p50_s", 3),
>     ("ttft_p90_s", 3),
>     ("ttft_p99_s", 3),
>     ("itl_s", 4),
>     ("decode_tps", 1),
>     ("aggregate_tps", 1),
>     ("prefill_tps", 1),
>
>         "ttft_p50_s": percentile(ttft, 50),
>         "ttft_p90_s": percentile(ttft, 90) if n >= MIN_PERCENTILE_N else None,
>         "ttft_p99_s": percentile(ttft, 99) if n >= MIN_PERCENTILE_N else None,
Failure: a published leaderboard has no request end-to-end latency distribution, so readers cannot assess total request time/tail latency as required; the only latency percentiles are TTFT. This is an omission rather than a falsely computed field.
Fix: add P50/P90/P99 over raw `total_s` (with the same sample-count policy) and expose them in the row/table/card.

### F8 [medium] Harness edits between column runs are invisible to the grid join
Where: `AGENTS.md:74`; `ohyesmlx/measure.py:466-493`; `ohyesmlx/report.py:1295-1335`
Evidence:
> - **Never edit `ohyesmlx/*.py` while a grid is running.** The runners re-enter the CLI once per column, so a mid-run edit means the columns ran different code and cannot be joined.
>
>     run = {
>         "workloads": [
>             {
>                 "id": workload.id,
>                 "messages": workload.messages,
>                 "max_tokens": workload.max_tokens,
>             }
>             for workload in workloads
>         ],
>         "temperature": TEMPERATURE,
>         "seed": SEED,
Failure: if a measurement formula or request path changes between separately invoked columns, their headers can still match and the join accepts numbers produced by different harness implementations.
Fix: record a harness revision/digest in each header and compare it in grid joins; operationally, keep the stated worktree/merge boundary.

### F9 [medium] Unavailable runtime-version probes do not prevent a version-sensitive comparison
Where: `ohyesmlx/runtimes.py:639-653`; `ohyesmlx/report.py:1415-1425`
Evidence:
>         if not command:
>             return "unknown: no version command"
>         result = _run(command, VERSION_TIMEOUT_S)
>         if result is None:
>             return "unknown: version command could not be run"
>         if result.returncode != 0:
>             return f"unknown: exited with code {result.returncode}"
>
>             key, value = key_of(row)
>             if not key or not value:
>                 continue
Failure: separate runs whose version probes fail with the same generic result can pass the exact-string join check despite using different builds; runtime version can affect speed and memory.
Fix: keep the diagnostic string in provenance but make an unknown version unrankable for comparisons that require that build to be held constant.

### F10 [medium] Run-discard decisions and retained evidence are operator-only
Where: `AGENTS.md:75`; `ohyesmlx/cli.py:336-366`
Evidence:
> - **Discard a run only for a stated defect in its conditions, never for its number.** Keep the discarded directory and name it with the reason.
>
>     for run_dir in args.run_dirs:
>         try:
>             header, results = measure.load_run(run_dir)
Failure: a caller can omit an inconvenient run directory or delete it and explicitly join only favorable runs; the join has no record of the omitted run or its condition-based discard reason.
Fix: preserve discarded run directories with a defect reason in their name and require the reviewed intended run set when publishing a joined result.
