# Dossier S2 — Measurement integrity

Scope: `ohyesmlx/transport.py`, `measure.py`, `coherence.py`, `sample.py`, `token_counter.py`,
the summary/grid/join paths of `report.py`, `canary.py`, `quickbench.py` (`_cell_record`,
`_best`, `_winner`, `latest`, stage loops). Prepared for the Fable 5.2 review. Line numbers
confirmed against the working tree at commit 714e8f6 (plus uncommitted review files only; no
`ohyesmlx/*.py` is modified in this tree).

## 1. Map

### ohyesmlx/transport.py (519 lines) — the SSE measurement client

- `transport.py:1-11` — module docstring: ported near-verbatim from LMRE; loopback allowlist, frozen Observation return, token_counter wired through.
- `transport.py:26-30` — `_TOKEN_SOURCES`: maps `resolve_token_accounting` status words to the recorded `token_source` values.
- `transport.py:33-45` — `TransportError(RuntimeError)`: carries `reason` and optional `http_status`.
- `transport.py:48-79` — `Observation` (frozen dataclass): one measured request — ok/error, ttft_s, last_content_s, total_s, prompt/completion/reasoning tokens, `content_event_count`, text, `token_source`, `reasoning_text`, `cached_tokens`, `mtplx_stats` (last three appended with defaults for backward-compatible loads).
- `transport.py:82-91` — `timing_channel(observation)`: `"reasoning"` when reasoning_text == text or content is empty, else `"content"`; derived, not stored.
- `transport.py:94-107` — `_parts`: enforces `http://127.0.0.1:<port>/v1` exactly; anything else is `endpoint_forbidden`.
- `transport.py:110-114` — `_connection`: HTTPConnection over `_parts`.
- `transport.py:117-145` — `_call_before_deadline`: runs a blocking call on a daemon thread, waits on a deadline, closes the connection and raises `timeout` when the deadline passes.
- `transport.py:148-152` — `_usage_count`: a usage counter must be a non-negative int (bools refused), else `invalid_token_accounting`.
- `transport.py:155-519` — `chat(...)`: the whole request. Builds the body (temperature 0, max_tokens, `stream_options.include_usage`, optional seed/api_key), deadline-bound send/receive, SSE loop over `select()` + `read1` (`transport.py:265-380`) parsing `content`/`reasoning_content`/`reasoning` deltas, `usage` counters, `cached_tokens` (nested spelling wins, `transport.py:357-370`) and the final-chunk `mtplx_stats` receipt (`transport.py:371-378`).
  - `transport.py:385-426`: post-stream channel decision — `mirrored` (reasoning == content accumulation, oMLX 0.6.4) and `reasoning_only` (reasoning streamed, no content) both move ttft/last/event-count to the reasoning deltas; otherwise the content deltas are timed. This is where TTFT can be measured on the reasoning channel, deliberately, and `timing_channel` recovers which.
  - `transport.py:442-474`: token accounting — exact split from `usage.completion_tokens_details.reasoning_tokens` when the runtime reports it (and not on a reasoning-only response), else `resolve_token_accounting`.
  - `transport.py:475-490`: the success Observation; `completion_tokens` is the *content* count.
  - `transport.py:491-519`: the failure Observation — any TransportError/TimeoutError/OSError/ValueError/KeyError/TypeError/JSONDecodeError becomes `ok=False` with the partial text and timings kept; `token_source="none"`.

### ohyesmlx/measure.py (1603 lines) — the measurement loop

- `measure.py:1-87` — module docstring: the refusals (one decode definition, no load folding, no mixed generation lengths, interleaved visits, per-visit persistence, no mixed token sources, batch = N requests one clock, coherence gate before status).
- `measure.py:115-199` — constants and their rationale: `MIN_WARMUP=3`, `WARMUP_WINDOW=5`, `WARMUP_CAP=20`, `WARMUP_PLATEAU_PCT=3.0` (128-131), `WARMUP_MODE="plateau"` (169), `VISIT_ROUNDS=2` (171), `MIN_CONTENT_DELTAS=2` (183), `INCOHERENT_PREFIX` (185), `EMPTY_CONTENT_ERROR` (192), `STILL_THINKING` (196), `_sleep` indirection (199).
- `measure.py:202-209` — `Cell`: one (format, runtime) pair; `id` is `<format>__<runtime>`.
- `measure.py:212-224` — `Workload`: id, messages, per-workload `max_tokens`.
- `measure.py:227-289` — `CellResult`: observations + batch_spans + warmup_observations + warmup_plateau + cold_load_s + first_request_s(+workload_id) + memory + runtime_version + disk_bytes + lost_visit_reason + cold_load_after_lost_visit + measured_pin (not written to record) + request_seed.
- `measure.py:292-305` — `decode_tps`: `completion_tokens / (last_content_s - ttft_s)`, `None` below `MIN_CONTENT_DELTAS` deltas or on a non-positive span; `total_s` is deliberately never a fallback.
- `measure.py:308-314` — `prefill_tps`: `prompt_tokens / ttft_s`, same delta gate.
- `measure.py:317-328` — `itl_s`: `span / max(1, completion_tokens - 1)`.
- `measure.py:331-355` — `measured_drift`: splits the per-request decode rates in half in order, compares the medians; `None` with fewer than two rates; `change_pct` `None` when the early median is 0.
- `measure.py:358-366` — `visit_plan`: alternating forward/reverse cell order per round.
- `measure.py:369-391` — `artifact_bytes`: on-disk size counted once per (device, inode) so HF-cache symlink snapshots are not double-counted.
- `measure.py:394-421` — `_warmup_pin`: header `warmup` validation; an int must be >= `MIN_WARMUP`, `"plateau"` becomes the rule dict (floor 2×window, cap 20).
- `measure.py:424-433` — `_header_seed`: asks a bare `Runtime` for the seed policy so the header states `runtimes.Runtime.request_seed`'s answer rather than a second copy.
- `measure.py:436-440` — `_source_sha256`: hash of every `ohyesmlx/*.py`, stamped in the run header.
- `measure.py:443-677` — `run_cells`: validates every pin (measured/concurrency/cache_state/kv_quant/mtp_depth/stream_experts/quick/cooldown_s), writes the run header, then visits cells per `_visits` plan; per-visit persistence via `write_jsonl`; lost-visit bookkeeping (`lost` dict, `measure.py:635-668`); cooldown only after a visit that sampled (`measure.py:671-675`).
- `measure.py:680-718` — `_results_for`: one CellResult per (cell, workload), created once, `measured_pin` stamped at creation.
- `measure.py:721-738` — `_visits`: splits `measured` batches across `VISIT_ROUNDS` rounds (5+4 for 9); zero-quota visits dropped.
- `measure.py:741-920` — `_visit`: refusals first (unknown runtime, no tokenizer, cache/kv/mtp/stream-expert refusals → N/A "skip"), then one `runtime.start()`, per-row `request_seed`/`cold_load_s`/`runtime_version` stamping (860-865), `stream_experts_missing` check post-start (870-874), per-workload `_workload_visit` (877-880), `mtp_depth_missing` check post-measurement (893-906), cold-visit `first_request_s` attribution (908-915); `finally: handle.stop()`.
- `measure.py:923-931` — `_first_warmup_result`: the workload holding the first warmup observation owns request #1.
- `measure.py:934-945` — `_first_warmup_latency`: first warmup's `total_s`, `None` unless `came_back`.
- `measure.py:948-992` — `_workload_visit`: per-workload Sampler window; warmup window then `quota` measured batches; observations and spans appended in step.
- `measure.py:995-1038` — `_warmup_window`: fixed budget returns `None` (no plateau verdict); `"plateau"` runs until `_settled` or `WARMUP_CAP`; every request kept on `warmup_observations` as it is made.
- `measure.py:1041-1070` — `_warmup_rate`: per-request `decode_tps` at concurrency 1; batch aggregate (`tokens / span`) above it; `None` for a batch that did not come back whole.
- `measure.py:1073-1112` — `_batch`: concurrency-1 is the sequential path with no span; above 1 a ThreadPoolExecutor under one monotonic clock; span is the whole batch.
- `measure.py:1115-1143` — `_settled`: two-window median trend test (3%), `None` rates cannot settle.
- `measure.py:1146-1157` — `_plateau_verdict`: `False` sticky across visits, `True` if any window settled.
- `measure.py:1160-1198` — `_request`: one transport call with the pins; any exception becomes a failed Observation (kept, not raised).
- `measure.py:1201-1207` — `_token_counter`: one TokenCounter per cell id, cached; construction failure recorded and the cell goes N/A.
- `measure.py:1210-1220` — `_highest_peak`: keeps the higher `peak_mb` of two visits' sampled memories.
- `measure.py:1223-1270` — `_set_status`: PASS only when every measured request `came_back`, not all still-thinking, majority-coherent (`_incoherent`), and every one carries its published metrics (`_missing_metric`); otherwise FAIL with the first reason.
- `measure.py:1273-1282` — `_judged_text`: content, else reasoning.
- `measure.py:1285-1298` — `came_back`: `ok or error == EMPTY_CONTENT_ERROR` — the one definition report counts samples with.
- `measure.py:1301-1308` — `_still_thinking`: neither channel produced text.
- `measure.py:1311-1342` — `_incoherent`: majority gate over judged responses (`failures * 2 > judged`), first failing reason quoted.
- `measure.py:1345-1365` — `_missing_metric`: names the first published metric the observation cannot carry (decode window, deltas, completion tokens, prompt tokens).
- `measure.py:1368-1370` — `_na`: status/reason for an unrunnable cell.
- `measure.py:1373-1400` — `_workloads`: validates non-empty messages and unique ids, copies messages out of the caller's hands.
- `measure.py:1403-1449` — `write_jsonl`: header line + one record per result, rewritten atomically (tmp + `os.replace` + fsync) after every visit.
- `measure.py:1452-1501` — `_record`: the record shape; derived fields (`measured_count`, `warmup_count`, `drift`) written for jq readers only; `batch_spans`/`lost_visit_reason` keys omitted when absent so pre-existing records stay byte-identical.
- `measure.py:1504-1533` — `load_run`: header + one CellResult per line; derived fields deliberately not read back.
- `measure.py:1536-1548` — `_line_object`: JSON decode with path/line-numbered ValueError.
- `measure.py:1551-1603` — `_cell_result`: rebuilds CellResult; lenient reads only where the absence is the historical fact (`warmup_plateau`, `batch_spans`, `lost_visit_reason`, `cold_load_after_lost_visit`, `request_seed` defaulting to `0` for pre-seed-key records).

### ohyesmlx/coherence.py (94 lines) — the language floor

- `coherence.py:1-15` — module docstring: a floor, not an eval; the token-salad incident; `NO_CONTENT` is not the incoherent verdict.
- `coherence.py:19-35` — constants: `_BLOCKS` (Unicode script ranges), `SCRIPT_MAJORITY=0.75`, `MIN_SCRIPTED=16`, `WORD_FLOOR=0.5`, `WORD_MIN=2`, `WORD_MAX=20`.
- `coherence.py:38-43` — `_script`: character → script name or None.
- `coherence.py:46-53` — `_core`: token stripped to alphabetic edges.
- `coherence.py:56-59` — `_is_word`: shape check per script (CJK unspaced).
- `coherence.py:62-72` — `_word_ratio`: fraction of whitespace tokens that look like words; `# ponytail` notes a Latin pseudo-word salad can pass.
- `coherence.py:75-94` — `is_coherent`: four checks in order — empty → `no content`; replacement chars; no 75% majority script (16+ scripted chars); word ratio < 0.5; then the optional `expect` substring.

### ohyesmlx/sample.py (303 lines) — peak-memory sampling

- `sample.py:1-16` — module docstring: `phys_footprint` from `footprint -p <pid>`; `ps` RSS is never used.
- `sample.py:25-59` — paths, timeouts (`FOOTPRINT_TIMEOUT_S=10`, `VMMAP_TIMEOUT_S=30`, `SYSCTL_TIMEOUT_S=5`, `CONSECUTIVE_MISSES_BEFORE_STOP=3`) and the parsing regexes.
- `sample.py:62-73` — `_run`: subprocess with timeout and DEVNULL stdin; failure → `None`.
- `sample.py:76-78` — `_reason`: first stderr/stdout line as the failure reason.
- `sample.py:81-86` — `parse_mb`: size string → MB.
- `sample.py:89-105` — `parse_footprint_text`: `phys_footprint` and `phys_footprint_peak` from `footprint` output.
- `sample.py:108-113` — `phys_footprint_mb`: one footprint read, `None` on failure.
- `sample.py:116-143` — `parse_vmmap_summary`: TOTAL row read by header names, not position.
- `sample.py:146-189` — `vmmap_split`: dirty/swapped/compressed split + vmmap's own footprint reading as a cross-check.
- `sample.py:192-214` — `gpu_wired_limit`: `sysctl iogpu.wired_limit_mb`, `raised` when > 0.
- `sample.py:217-303` — `Sampler`: background thread polling `phys_footprint_mb` every `interval_s`; `stop()` returns `{peak_mb, samples, memory_split, gpu_wired_limit, error}`; `peak_mb` is `max` of samples (`sample.py:291`); 3 consecutive misses stop the loop with an error (`sample.py:262-278`).

### ohyesmlx/token_counter.py (116 lines) — token accounting reconciliation

- `token_counter.py:1-17` — module docstring: usage is preferred when it splits reasoning; the counter exists to split one combined stream; re-tokenization is not the inverse of generation.
- `token_counter.py:24-76` — `TokenCounter`: `tokenizer.json` via `tokenizers`, else `transformers.AutoTokenizer` (`trust_remote_code=True`, `token_counter.py:62-65`); `count(text)` re-tokenizes.
- `token_counter.py:79-116` — `resolve_token_accounting`: (a) no reasoning text + usage total → `(0, completion_tokens, EXACT_VISIBLE)` (96-97); (b) no counter → `INCOMPARABLE`; (c) counter split must sum exactly to `completion_tokens` with visible > 0 → `DERIVED_REASONING_CONTENT`; (d) no usage total but both parts > 0 → derived; else `INCOMPARABLE`.

### ohyesmlx/report.py — summary/grid/join paths (file is 2609 lines; in-scope ranges)

- `report.py:1-67` — module docstring: metric formulas pinned not re-derived; drift and short-window treatment; percentiles need samples; floors are pass/fail.
- `report.py:81` — `MIN_PERCENTILE_N=5`.
- `report.py:101` — `DEFERRED_LOAD_EXCESS_S=1.0` (seconds, absolute; rationale with measured populations 83-100).
- `report.py:131` — `DRIFT_ANNOTATION_PCT=5.0` (rationale with the 2026-09-15 grid's per-column drift, 103-130).
- `report.py:137-140` — `_DRIFT_ABSENCE` note text.
- `report.py:157-162` — `FLOORS=("coherence","metrics")`, `FLOOR_CLEARED`.
- `report.py:171-185` — `RANK_METRICS` and `DEFAULT_RANK="decode_tps"`.
- `report.py:204` — `DECODE_DERIVED_RANKS={"decode_tps"}`: the only ranks the drift marker may ride.
- `report.py:249-262` — `PIN_FIELDS`: the 11 header pins a join compares.
- `report.py:304-313` — `CROSS_RUNTIME_UNCOMPARABLE` (`peak_mb`, `cold_load_s`) with the measured evidence (275-303).
- `report.py:344` — `CHANNEL_DEPENDENT_RANKS={"ttft_p50_s","prefill_tps"}` (rationale 315-343).
- `report.py:372-383` — `percentile`: linear interpolation (`statistics.quantiles`, inclusive) ≈ numpy default.
- `report.py:386-391` — `median`.
- `report.py:394-423` — `summarize`: one row per (cell, workload); `measured` pin falls back to `result.measured_pin`; absent pin = no check.
- `report.py:426-488` — `render_markdown`: per-workload leaderboard; runtime-axis refusal for uncomparable/channel-mixed ranks.
- `report.py:491-612` — `render_grid`: joins run directories; five guards run first (525-551), then provenance, per-workload grid tables, axis readings, footnotes. No figure re-derived — entries are the rows' own printed strings.
- `report.py:615-649` — `order_rows`: ranked / valueless / excluded; copies rows so two orderings cannot contaminate.
- `report.py:652-678` — `render_cards`, `report.py:689-747` — `_card`: every value behind the ordering, floors and notes per row.
- `report.py:796-893` — `_row`: builds the published row — samples filtered by `measure.came_back` (802), TTFT percentiles over `n = len(ttft)` (817, 850-855), per-request metrics via `measure.*` (808-815), drift asked of `measure.measured_drift` (823), `short` = batches < measured pin (828), all notes attached (868-891), floors attached (892).
- `report.py:896-930` — `_reasoning_timed_note`, `_timing_channel`, `_mixes_channels`: the timing-channel bookkeeping.
- `report.py:933-945` — `_measured_batches`: `len(batch_spans)` when spans exist, else `len(observations)`.
- `report.py:948-977` — `_lost_visit_note`, `_cold_load_note`: the two "a visit/start was not the first" notes.
- `report.py:980-1014` — `_made_the_first_request`, `_deferred_load_note`: deferred-load claim only on the row that owns request #1; threshold `DEFERRED_LOAD_EXCESS_S` over the median measured request.
- `report.py:1017-1055` — `_drift_note`: three cases (above threshold signed, below = silence, no window = `_DRIFT_ABSENCE`).
- `report.py:1058-1080` — `_drift_cell`, `_drift_card_row`.
- `report.py:1083-1126` — `_floor_verdicts`: reads measure's verdict; coherence-fail vs metrics-fail vs N/A vs PASS; `rankable` only when both floors pass.
- `report.py:1133-1143` — `_coherence_failed`: identifies the gate by `measure.INCOHERENT_PREFIX` / `STILL_THINKING` — one vocabulary.
- `report.py:1146-1182` — `_token_source`, `_content_deltas`, `_per_request`: per-request metrics asked of measure, never re-spelled.
- `report.py:1185-1231` — `_aggregate_tps`: batch spans when present (tokens over summed spans), else sum of per-request clocks (the pre-batches reading); never reconstructs spans.
- `report.py:1234-1270` — `_held_constant`: refuses a table that varies both variables (format checked as label+artifact pair; runtime as name+version).
- `report.py:1273-1418` — `_table`, `_cells`, `_unrepeated`, `_footnotes`: the leaderboard rendering and its notes.
- `report.py:1438-1446` — `ABSENT_PINS`: what a header's missing pin means (the absence is the fact).
- `report.py:1450-1460` — `ENTRY_LEGEND`: the five entry states, one copy for both joined tables.
- `report.py:1463-1478` — `_check_not_quick`: refuses `quick: true` by value, before any comparison.
- `report.py:1481-1494` — `_check_known_runtime_versions`: refuses `runtime_version` starting `"unknown"` (review D3).
- `report.py:1497-1510` — `_check_harness`: refuses two runs with different `harness.source_sha256`.
- `report.py:1513-1552` — `_check_pins` (guard 1): every `PIN_FIELDS` field compared (sweep skips `varying`); `prompt_tokens` sweep drops only `messages`.
- `report.py:1555-1588` — `_check_workload_pins`: same shape set, same `messages` and `max_tokens` per shape (messages exempt only for the prompt-length sweep).
- `report.py:1591-1593` — `_shapes`: header workloads by id.
- `report.py:1596-1621` — `_check_cells_appear_once` (guard 2): no cell in two run directories; no latest-wins.
- `report.py:1624-1660` — `_check_one_value_per_key` (guards 3/4): one artifact per format label; one version per runtime; rows missing either half skipped.
- `report.py:1663-1697` — `_columns`, `_format_labels`: grid axes.
- `report.py:1700-1777` — `_provenance`, `_harness_provenance`, `_shared_pins`: the block that names every column's run directory, version, harness hash and shared pins.
- `report.py:1780-1795` — `_entry_table`: one rendering for both joined tables.
- `report.py:1798-1818` — `_grid_table`: index keyed `(label, runtime)`; drift marker only when `rank in DECODE_DERIVED_RANKS`.
- `report.py:1826-1876` — `_entry`: the five states (`—`, `N/A`, `FAIL`, `no value`, number) plus drift/short/reasoning-timed markers.
- `report.py:1879-1897` — `_short_marker` (`n=<batches> of <pin>`), `_rank_number`.
- `report.py:1900-1916` — `_drift_marker`: delegates the threshold to `_drift_note`.
- `report.py:1919-1963` — `_readings`: both axis readings per workload + recommendation.
- `report.py:1966-2028` — `_uncomparable_across_runtimes`, `_channel_note`, `_cross_runtime_note`, `_runtime_axis_note`: the two runtime-axis refusals and their notes.
- `report.py:2031-2069` — `_unpositioned`, `_ordering`: values-without-positions for a refused ordering; positions come from `order_rows`.
- `report.py:2072-2114` — `_recommendation`: best cell labelled as a recommendation; refuses on uncomparable ranks and channel-mixed workloads.
- `report.py:2123-2221` — `SWEEP_PINS`, `SWEPT_PIN`, `SWEEP_HELD`, `SWEEP_VALUES`: the six swept header pins and their prose.
- `report.py:2222-2244` — `CONCURRENCY_DRIFT_SENTENCE`, `CONCURRENCY_TTFT_SENTENCE`.
- `report.py:2245-2385` — `render_sweep`: the sweep join — same guards with `varying` skipped, plus `_check_sweep_varies`; entries formatted by the grid's own functions.
- `report.py:2388-2430` — `_pin_value` (absent pin via `ABSENT_PINS`), `_pin_key` (prompt pin keyed on `target`), `_pin_note`, `_drove_more_than_one_request`.
- `report.py:2433-2454` — `_check_sweep_varies`: one value across all runs is not a sweep.
- `report.py:2457-2609` — `_sweep_columns`, `_achieved`, `_ascending`, `_sweep_cells`, `_sweep_index`, `_sweep_provenance`, `_sweep_table`, `_sweep_head`, `_number`, `_bytes`, `_text`: sweep rendering helpers (columns ascending per pin order; entries reuse `_entry`).

### ohyesmlx/canary.py (228 lines) — version-bump canary

- `canary.py:1-32` — module docstring: Decision 135's loop; pure comparison, failed cell is never a verdict, busy machine is not a baseline.
- `canary.py:47` — `NOISE_FLOOR=0.05` (Decision 131's session bar); `canary.py:53` — `LOAD_NOISY=4.0`.
- `canary.py:66-73` — `Verdict`; `canary.py:75-100` — `Reading` (with `noisy` = max(load_before, load_after) > LOAD_NOISY).
- `canary.py:103-105` — `_pct`: signed percent at published precision.
- `canary.py:108-135` — `verdict`: metric with larger |change| wins; change computed then rounded to 1 dp *before* the floor comparison ("5.0% reads no effect"); baseline 0/None skipped as "never recorded".
- `canary.py:138-165` — `verdict_line`: non-PASS rows never reach the comparison; PASS with a `None` rate says "no verdict"; null/zero baseline says "no baseline recorded".
- `canary.py:168-190` — `artifact_dir`: newest HF snapshot with a `config.json` (mtime).
- `canary.py:193-199` — `cells`: the manifest canary block as a `--cells` string.
- `canary.py:202-204` — `load`: 1-minute load average.
- `canary.py:207-228` — `record`: writes the four baseline fields into the manifest; tested version deliberately not adopted.

### ohyesmlx/quickbench.py (1059 lines) — the v5 quick bench

- `quickbench.py:1-31` — module docstring: two single-axis stages; every number labelled quick; every side effect injected.
- `quickbench.py:58-102` — constants: `WARMUP=3`, `MEASURED=5`, `COOLDOWN_S=10.0` (61-63), `TIE = canary.NOISE_FLOOR` (67), `LABEL`/`CAVEAT_A`/`CAVEAT_B`/`BUSY`/`CANCELLED`/`ABORTED`/`ABORTED_REASON` (77-85), `DEFAULT_RESULTS_DIR` (89), `DEFAULT_BACKUP_DIR` (95), `SUMMARY_NAME` (98), `WORKLOAD_ID="decode"` (102).
- `quickbench.py:105-139` — `PlannedEngine`, `PlannedSibling`, `QuickPlan`.
- `quickbench.py:142-156` — `_print_event`, `_discard`, `_never_cancelled`.
- `quickbench.py:159-165` — `estimate_seconds`: the one estimate definition.
- `quickbench.py:168-175` — `_port_busy`: probe, never a stop; unknown = busy.
- `quickbench.py:178-205` — `_osaurus_app_running`: full-executable-path match (never name), unrunnable probe = app present.
- `quickbench.py:208-225` — `_osaurus_drift`: post-cell host-vs-baseline comparison.
- `quickbench.py:228-244` — `_keep_during_run`: byte-exact copy of the two pinned host files (0700 dir).
- `quickbench.py:247-252` — `_catalog_row`.
- `quickbench.py:255-314` — `plan`: pure plan (AC-1); refuses a repo not in the cache; stage A = installed engines listing the row, stage B = catalog siblings.
- `quickbench.py:317-319` — `cell_spec`: one cell as a `--cells` string.
- `quickbench.py:322-353` — `_cell_record`: one cell's summary line; numbers come only from `report.summarize`'s row; skipped/failed cells carry no number.
- `quickbench.py:356-357` — `_skipped`; `quickbench.py:360-371` — `_aborted`: "Stop now" lands on a status with no number (raw rows stay on disk).
- `quickbench.py:374-395` — `_winner`: highest decode among PASS cells; `TIE` band reported as a tie; exact tie keeps stage order.
- `quickbench.py:398-428` — `_best`: stage-B cells if stage B ran, else stage A's; only PASS + non-None decode; `format`/`repo` from the winning cell itself.
- `quickbench.py:431-447` — `_skip_reason`: osaurus consent/app/port checks; nothing on a skipped port is stopped.
- `quickbench.py:450-466` — `_stamp`, `_write_summary` (atomic, fsync).
- `quickbench.py:469-485` — `_emitter` (engines' `_job_event` shape), `_refuse`.
- `quickbench.py:488-1020` — `run`: the stage loop. Consent → catalog row → plan; summary skeleton with harness hash and load slots (572-605); nested helpers `step`/`note_not_evicted`/`record_load` (612-644); `measure_cell` (646-751) wraps `run_cells` with Osaurus recover→pin→drift→restore (restore in `finally`, restore-failure ends the run); `measured` (753-761) swaps in `_aborted` on a stop. Stage-A loop 763-811 (skip reasons, per-cell records, restore_failure/abort breaks), winner/tie 813-842, stage-B loop 843-937 (download one sibling, measure, evict in `finally`, `not_evicted` recorded), `record_load` per stage. `finally` 943-1002: evict leftovers, `actual_s`, cancelled-run plan coverage, stage-B notes, `best` only when `ended == "finished"`, `_write_summary`, one `result` event. Terminal events 1004-1020.
- `quickbench.py:1023-1059` — `latest`: newest finished summary per `best.repo` for `GET /recommendations`; unreadable summaries skipped; non-finished never read.

## 2. Contracts

### docs/interfaces/measurement-core.md

- `measurement-core.md:9-22` — the `Observation` shape this code produces: "`content_event_count: int` — deltas of the OUTPUT stream, not always the content channel"; "`text: str` — CONTENT deltas only".
- `measurement-core.md:36-40` — "`ttft_s`, `last_content_s` and `content_event_count` are the output stream's, and the output stream is the content deltas in the ordinary case and the reasoning deltas when the runtime [mirrored or reasoning-only]".
- `measurement-core.md:50-66` — "Which channel is the output stream": two exceptions (mirrored, reasoning-only); the oMLX 0.6.4 incident (TTFT 5.499 s reported vs 0.685 s real) is the rationale for `transport.py:385-426`.
- `measurement-core.md:446-459` — "Metric formulas — one definition each, no forks": `decode_tps = completion_tokens / (last_content_s - ttft_s)` etc., "DOMAIN: all three require `content_event_count >= 2`".
- `measurement-core.md:414, 432-439` — "The raw record stays raw": "A stored observation carries **only the `Observation` fields** — never `decode_tps`, `prefill_tps`, or `itl_s`"; warmups kept alongside observations.
- `measurement-core.md:189-196` — `sample.py`'s result shape (**merged, do not change**): `{peak_mb, samples, n_samples, duration_s, memory_split, gpu_wired_limit, error}`.
- `measurement-core.md:215` — `observations: list[Observation]   # EVERY raw sample. Never truncated.`
- `measurement-core.md:252-275` — "`seed` is a policy, and `request_seed` is what a row sent".
- `measurement-core.md:392-402` — `report.summarize`'s row fields, incl. "`concurrent` is `bool(batch_spans)`".

### docs/interfaces/grid-and-warmup.md

- `grid-and-warmup.md:75-88` — the join guards: "Joining five separately-invoked runs is the one place this project can vary two things without noticing, so the join refuses rather than renders when: 1. **The pins disagree**… 2. **A cell appears twice**… There is no 'latest wins' rule, because which run is newer is not which run is right."
- `grid-and-warmup.md:96-100` — guard 5 (unknown runtime version refused) and guard 6 (`_check_harness`): "a header predating the block carries none and is skipped. Two revisions of the loop are not one grid."
- `grid-and-warmup.md:154-167` — the plateau rule: "The cell is warm when the median of the last `WARMUP_WINDOW` rates is within `WARMUP_PLATEAU_PCT` of the median of the `WARMUP_WINDOW` before them. It is a **trend test and never a variance test**"; "A rate comes from `decode_tps`, the same function every published figure uses".
- `grid-and-warmup.md:16-33` — `load_run`'s shape: `(run_header, results)`; line 1 is the header.

### docs/interfaces/sweep-pins.md

- `sweep-pins.md:5-17` — "each sweep is N runs differing in exactly one header pin, joined afterwards… `varying` must actually vary: a sweep whose runs all pin the same value is not a sweep".
- `sweep-pins.md:27-40` — "At concurrency N > 1 the ordering metric is aggregate throughput, not `decode_tps`… Per-request rate stays recorded, TTFT becomes a queueing measurement"; "a concurrency sweep warms on aggregate throughput" (`_settled` over per-batch aggregates, `_warmup_rate`).
- `sweep-pins.md:176-200` — the lost-visit contract: `lost_visit_reason`, `cold_load_after_lost_visit`, `measured_pin` — "all of them annotations and none of them floors… a window that was short is a result"; "`measured_pin`… NOT written to the record: the header owns it there".

### docs/interfaces/study-pins.md

- `study-pins.md:15-27` — kv_quant: "**The values name the codec, not the width**"; "`fp8` is not one of them and must not come back as a spelling of `affine8`… a codec a runtime cannot deliver is `N/A` with a reason rather than approximated into a neighbour."
- `study-pins.md:94-110` — mtp_depth: "**The policy is part of the value, not a second pin**" (every depth passed `--native-mtp-depth-policy fixed`; vMLX's adaptive default can change depth inside one request).
- `study-pins.md:212-235` — stream_experts: "**A flag is not evidence that anything streamed, so the log is**… an `on` cell whose log does not show it is `FAIL` with that log quoted — never a number published under a pin it does not hold."

### docs/interfaces/v5-quickbench.md

- `v5-quickbench.md:19-22` — "`_check_not_quick` refuses any grid or sweep naming a run directory whose header pins `quick: true`, by value".
- `v5-quickbench.md:126, 139-141` — "One variable per stage. Stage A varies the engine on the chosen row's format; its winner is [held] … Stage B holds that engine and varies the format"; `run` returns True only when the run finished.
- `v5-quickbench.md:169-198` — the summary shape and the cell record pin: `{"engine", "format", "repo", "artifact_dir", "status": "PASS|FAIL|SKIPPED|ABORTED", "reason", "decode_tps", "ttft_s", "runtime_version", "label", "reused"}`; "ABORTED (\"Stop now\"): a mid-cell stop, no figure, never the winner".
- `v5-quickbench.md:201-206` — "`best` is non-null only on a finished run… `quickbench.latest(root)` returns the newest **finished** summary".

### AGENTS.md

- `AGENTS.md:37` §"Metric definitions — do not redefine these": "**TTFT** — request sent → first *content* token. Includes prefill. Reasoning tokens are not content. Exception (Decision 119)… every such row is labelled 'timed on reasoning channel'." and "**Peak memory** — `footprint -p <pid>`. **Never `ps` RSS**… `peak_mb` is sound **within a runtime** and carries **no cross-runtime ranking**".
- `AGENTS.md:37-60` — "Every measured run pins temperature 0… **At temperature 0 no seed is sent**… `Runtime.request_seed` is the one definition"; "Raw observations are never discarded. Summaries must stay recomputable from them."
- `AGENTS.md:88` §"Runtime hazards, already paid for": "**A cell that produces incoherent output has FAILED, however fast it was**… Every measured cell therefore passes a **coherence gate** before its numbers count"; "**Exactly one model is resident at a time**… a run that violates it is void"; "MTPLX answers HTTP 200 with coherent text when it has no MTP head to wire… A depth cell is therefore gated on the final chunk's `mtplx_stats` receipt".
- `AGENTS.md:88+` — "**Never infer a capability from the absence of a flag**… A claim that a tool CANNOT do something needs evidence from the source or the settings" (the oMLX "does not stream" 8× TTFT error).

### docs/threat-model.md (rows naming this code)

- `threat-model.md:27-29` — scope includes `quickbench.py` and "`runtimes.py` and `measure.py`, as far as quickbench reaches them".
- `threat-model.md:50` — asset row: Osaurus host config + drift-guard baseline — "quickbench pins these and restores them. If a restore is missed, the user's own Osaurus keeps running under settings they did not choose."
- `threat-model.md:144-145, 155` — write/read rows: `…/quickbench/<run>/summary.json` (temp+replace), `results.jsonl` per `measure.run_cells`, and `quickbench.latest` reads only `best` of finished summaries.
- `threat-model.md:274, 365-371` — T-05 (CONFIRMED, fixed 045-02a part B): an Osaurus pin clobbered mid-cell was measured and reported as pinned; the fix is quickbench's post-cell `osaurus_drift` before restore.

### docs/design/phase5/DESIGN.md (app sections)

- `DESIGN.md:32, 110` — the app's Setup flow includes Benchmark/Results; Escape cancels. No measurement semantics live here; the quickbench contract is v5-quickbench.md's.

## 3. Already known — do not re-report

Format: `- <claim> — <source> — fixed <sha> | accepted | deferred | open`.

### From the 2026-09-23 deep review (`.paul/review/2026-09-23/SUMMARY.md`) and the hardening waves

- A1: leaderboard/card printed figures on FAIL rows — `.paul/review/2026-09-23/SUMMARY.md` A1 — fixed 5313062 (row dict keeps them; renderings suppress), plus f998dcd (N/A cells say N/A on the single-run leaderboard).
- A2: one-delta stream produced a float-noise decode window that fed drift and warmup ("1.5-billion-tok/s bug") — A2 — fixed 5313062 (`MIN_CONTENT_DELTAS` moved into measure, decode/prefill/ITL refuse below it) and ef01396 (one-chunk timing exact-zero).
- A3: v3 research probe scripts reimplement the metrics (`(tokens-1)/span`, `ps` RSS fallback etc.) — A3 — fixed 4279663 (paper caveats); probe scripts themselves unchanged — deferred (scripts out of S2 scope).
- A4: `probe_grid*.py` labelled an incoherent cell `LOADS` — A4 — fixed 4279663 (`LOADS` requires coherence).
- A5: reasoning-channel timing conflicted with "Reasoning tokens are not content" — A5 (conflict) — fixed by Decision 119: b805545 (reasoning channel captured and labelled), 17b3791 (reasoning-channel label + e2e percentiles + unknown-version refusal), e57775d (refuse runtime-axis TTFT orderings across mixed channels).
- A6: sampling only partly pinned (`repetition_penalty` from bundles) — A6 — fixed 9f3bd4b + 71987a4 (Decision 131, vMLX pinned); the Osaurus bundle-penalty half is the STATE blocker below.
- A7: runtime-axis ordering printed for `peak_mb`/`cold_load_s` with a warning — A7 (conflict) — fixed 17b3791 (ordering refused, values kept; Decision 122) and f998dcd (single-run leaderboard applies it).
- B1–B4: stale Osaurus apps not swept, swallowed cleanup, ignored second `_await_exit`, `lsof`-failure capture hole (runtimes.py, one-model-resident rule) — B1–B4 — fixed ef01396 (residency, cleanup) — verified in scope only as far as `measure._visit`'s `finally: handle.stop()`.
- C1/C2: an exception or Ctrl-C inside a visit lost observations / skipped `handle.stop()` — C1, C2 — fixed 5313062 (whole visit after start inside try/finally; `run_cells` persists before re-raising, `measure.py:651-653`).
- C3: an existing-but-unreadable Osaurus baseline disabled the drift gate — C3 — fixed in the `osaurus_settings` rebuild: `load_baseline` now raises `ValueError` on an unreadable/invalid baseline (`osaurus_settings.py:130-142`) rather than returning `None`.
- C4: `write_jsonl` left `.tmp` behind on failure — C4 (tmp half) — fixed 5313062 (`measure.py:1447-1449`); the `Sampler.stop()` thread-alive half is reported as `error` on the result (`sample.py:285-286`, test_sampler_retains_a_thread_that_does_not_join) — accepted as reported-not-prevented.
- D1: no end-to-end latency percentiles — D1 — fixed 17b3791 (`e2e_p50/p90/p99_s` in `_row`).
- D2: no harness revision in the run header, columns run on different code joined silently — D2 — fixed 5313062 (`harness.source_sha256`, `_check_harness`; headers without the block still join, per grid-and-warmup.md:96-100).
- D3: a generic `unknown: …` version passed the one-version guard — D3 — fixed 17b3791 (`_check_known_runtime_versions`, its docstring cites "review D3").
- E1: measure fakes carried no API key — E1 — fixed 5313062 ("E1 API-key wiring test").
- E2: HTTP-status and non-SSE rejection paths untested — E2 — fixed ef01396 (`test_http_status_and_content_type_errors_are_reported`).
- E3: no request-deadline test — E3 — fixed ef01396 (`test_headers_then_stall_respects_request_deadline`).
- docs F10 (README "0.0.1/Prototype" quote) — fabricated finding, rejected (eb4590d).

### From `.paul/review/2026-11-14-phase5-w1` (spec + standards logs; fix ac0de1b)

- Stage-B progress payloads keyed rows by the winner's engine, collapsing the app's cell rows and dropping stage-B reasons — w1 spec #2 / standards HARD 1 — fixed ac0de1b ("structured cell events"; `test_every_measured_cell_event_carries_stage_engine_format_status_and_reason`).
- Quickbench abort rationale restated in three docstrings ("each rationale written once") — w1 standards HARD 2 — fixed in tree (verified at 714e8f6: the rationale is written once at `_aborted`, `quickbench.py:360-371`, callers point at it); exact commit ac0de1b/bb762c6 not pinned.
- `test_quickbench.py` "abort after last cell" probe never triggered (a test that cannot fail) — w1 spec #4 — open (not named in ac0de1b's fix list).
- AC-7's `RuntimeStopError`-from-`measure_cell` path untested (the `measured` except branch) — w1 spec #5 — open.
- Swift-side findings (poison SSE event loop, `deliverLine` losing the launch line, cancel-body detection) — w1 — fixed ac0de1b — out of S2 scope.

### From `.paul/review/2026-11-14-phase5-w2` (fixes landed in 101df7c's app tree per fee692b)

- All six w2 findings (stale-summary marking later jobs failed, ephemeral benchmark tick, "exactly as received" raw bytes re-encoded, `not_evicted` line defined twice in Swift, benchmark plan-fetch race, AC-1 grep gate) — w2 logs — fixed in 101df7c app tree (fee692b) — Swift-side; the raw-bytes one reads quickbench summaries but lives outside S2 code.

### From STATE.md (Deferred Issues, Blockers)

- Eight pre-`first_request_workload_id` run directories cannot be loaded (`load_run` refuses by line number rather than defaulting) — STATE.md Deferred Issues — deferred.
- `usage.cached_tokens` recorded per observation "not yet surfaced in a report or gate" — STATE.md Deferred Issues — fixed 7c22c83 for the recording half; the surfacing half — deferred.
- mlx-lm/OptiQ served prompt-cache hits as prefill TTFT when `cache_state` unpinned — STATE.md Blockers — fixed 933f6a4 (Decision 130; absent pin is cache off for those two).
- AGENTS.md sampler-pinning claim vs reality — STATE.md Blockers — fixed 2026-09-29 (Decision 131, 9f3bd4b; AGENTS.md rewritten 71987a4).
- Osaurus applies a bundle's `presence_penalty`/`repetition_penalty` the harness does not pin; HTTP-override unknown; the speed-side effect unmeasured — STATE.md Blockers (2026-09-29/30) — open (tested for MMLU accuracy only).
- `fetch.downloaded` size-check reads re-serialised hero safetensors as "not downloaded" (proved same tensors, 2026-11-02) — STATE.md Blockers — closed, no action; affects canary/quickbench artifact resolution only via fetch.

### From `.paul/phases/v5-onboarding/*SUMMARY.md` (Deviations / Carried forward)

- "The four remaining atomic-write copies (`osaurus_settings`, `runtimes`, `measure`, `quickbench`)" — PHASE-4.5-SUMMARY.md Carried forward — open (known duplication: `measure.write_jsonl:1435-1449`, `quickbench._write_summary:454-466` and two others).
- `canary --record` writes baselines only; adopting a tested version is a separate manifest edit — PHASE-2.5-3-SUMMARY.md Deviations — accepted (by design; `canary.record` docstring).
- The Osaurus `pin` refuses while a leftover backup exists (was: silently reused) — 04-03a-SUMMARY.md Deviations — accepted (behaviour change, deliberate).
- A hand-made backup holding both `baseline.json` and `baseline.absent` makes `_put_back` raise — 04-03c-SUMMARY.md Deviations, PHASE-4-SUMMARY.md — accepted ("not handled, by choice").
- 05-05-SUMMARY: "Not run: a live download or quickbench (needs Jason's go-ahead)" — 05-05-SUMMARY.md Deviations — open (quickbench's app integration unproven live).
- AC-7 drift check / copy are injectable and one existing test was edited to bind them to a tmp dir (Jason, 2026-11-09) — 045-02a-SUMMARY.md Deviations 1 — accepted (decision recorded in STATE Decisions).

### From threat-model §8/§9/§10

- T-05: an Osaurus pin clobbered mid-cell was measured and reported as pinned — threat-model §7 T-05 — fixed 9bc9388 (045-02a part B: `osaurus_drift` after the cell, before restore; `quickbench.py:678-702`).
- "Thermal drift; other MLX apps holding GPU memory during quickbench" — threat-model §8 (04-03b audit #1/#2) — accepted ("quick results are labelled and never join the published tables").
- T-06: `_acquire_lock` stale-lock reclaim check-then-remove race — threat-model §9 — accepted (quickbench's evictions run under it; `fetch`, not S2 code).
- P5-11 status "Partly met": `Pick.downloaded` cannot distinguish absent from size-mismatched — threat-model §10 status — open (also STATE deferred; recommend.py, not S2 code).

## 4. Hotspots

Ordered by how much of the project's core claim a defect there would break. "Guard" names a test that would fail; "none" means no test asserts the property.

*Corrigendum to §1, left here rather than editing §1:* `report.py:249-262` `PIN_FIELDS` holds **12** entries, not the 11 §1 states. The tuple is `temperature, seed, warmup, measured, cooldown_s, concurrency, prompt_tokens, cache_state, kv_quant, mtp_depth, stream_experts, quick`; the comment above it (`report.py:240-248`) counts "seven" because it is counting the seven *driving* pins from `concurrency` onward.

- **`transport.py:385-426`** — the channel decision: `mirrored` / `reasoning_only` move `ttft_s`, `last_content_s` and `content_event_count` from the content deltas to the reasoning deltas in one assignment. A wrong branch publishes another stream's latency — this is the oMLX 0.6.4 8× TTFT error (5.499 s reported vs 0.685 s real), and the only detector is `reasoning_text == joined`. Guard: `test_transport.py::test_a_mirrored_stream_is_timed_from_the_reasoning_deltas`, `::test_a_reasoning_only_stream_times_and_counts_its_reasoning_deltas`, `::test_a_content_streaming_response_keeps_its_own_timing`, `::test_a_reasoning_channel_that_differs_from_content_keeps_content_timing`, `::test_observation_labels_the_channel_that_supplied_timings`.
- **`transport.py:491-519`** — every exit that is not a success becomes `ok=False` while keeping partial `text`/`reasoning_text`/timings and setting `completion_tokens=None`. The risk is misclassification, not loss: the one failure that *counts as a sample* downstream is `empty_content` (`measure.came_back`), and the branch at `transport.py:428-431` is what decides it. Guard: `test_transport.py::test_a_stream_with_neither_channel_still_raises_empty_content`, `::test_incomplete_stream_is_reported_rather_than_raised`, `::test_http_status_and_content_type_errors_are_reported`.
- **`transport.py:117-145`** — a blocking connect/send/read is raced against a deadline on a daemon thread; on expiry the connection is closed and `TransportError(timeout)` is raised. A defect here turns a hung server into a slow "measurement" rather than a refusal. Guard: `test_transport.py::test_headers_then_stall_respects_request_deadline`, `::test_first_chunk_more_than_a_second_after_headers_is_survived`.
- **`measure.py:292-328`** — the three formulas and their domains (`content_event_count >= MIN_CONTENT_DELTAS`, non-positive span refused, `total_s` deliberately never a fallback, ITL never divides by zero). The predecessor's "1.5-billion-tok/s" bug lived exactly here. Guard: `test_measure.py::test_the_metric_formulas_are_the_documented_ones`, `::test_decode_never_falls_back_to_total_s`, `::test_a_single_content_delta_has_no_decode_window`, `::test_itl_never_divides_by_zero_on_a_single_token`, `::test_itl_is_none_when_the_last_delta_precedes_the_first`.
- **`measure.py:1223-1270`** — the PASS gate, in order: no observations → leave the visit's verdict; any `not came_back` → FAIL; all still-thinking → FAIL; majority incoherent → FAIL; missing published metric → FAIL; else PASS. The gate runs before the metric check deliberately (a removed content window would otherwise bury the garbage). A defect here publishes a garbage cell's number. Guard: `test_measure.py::test_a_fully_measurable_cell_passes`, `::test_one_failed_request_fails_the_cell`, `::test_an_incoherent_cell_fails_and_keeps_the_sample_that_failed`, `::test_a_cell_that_is_still_thinking_gets_its_own_reason`, `::test_a_response_without_content_timing_fails_the_cell`.
- **`measure.py:1311-1342`** — the incoherence majority: `failures * 2 > judged`, over responses that came back **and** produced text, judging content first and reasoning only when content is empty. Guarding denominator this loosely could let a cell survive by having most requests die. Guard: `test_measure.py::test_more_than_half_the_judged_responses_have_to_be_incoherent`, `::test_a_response_that_did_not_come_back_is_never_called_incoherent`, `::test_incoherent_reasoning_counts_in_the_same_majority_as_content`.
- **`measure.py:854-874`** — per-row attribution of the start's own facts: `cold_load_s`/`runtime_version` are stamped only when `cold_load_s is None` (the first visit that started), `request_seed` on every visit, and `stream_experts_missing` turns the row FAIL **after** the start but keeps the start's facts. This is where a number could be labelled with a version or pin that did not produce it. Guard: `test_measure.py::test_the_runtime_version_is_recorded`, `::test_an_on_cell_whose_log_does_not_show_streaming_fails_with_the_log_quoted` — partial (no test varies the version between visits).
- **`measure.py:948-992`** — one workload's window: the sampler covers warmups *and* measured requests, warmups go to `warmup_observations` only, and `observations`/`batch_spans` are appended in the same step (the mapping `_aggregate_tps` relies on and deliberately does not re-derive). A desynchronised append mis-attributes aggregate throughput. Guard: `test_measure.py::test_warmups_run_before_the_measurements_and_never_reach_the_samples`, `::test_a_run_at_four_issues_four_requests_per_batch_and_records_one_span`, `test_report.py::test_aggregate_throughput_divides_by_the_batch_spans_not_the_summed_requests`.
- **`measure.py:1073-1112`** — the batch clock: one `time.monotonic()` span around `concurrency` requests, `None` at N=1 (a reconstructed span is "a clock nobody took"). Summing per-request clocks is the concurrency-sweep error this exists to prevent. Guard: `test_measure.py::test_a_batchs_span_is_shorter_than_the_sum_of_its_requests`, `::test_measured_counts_batches_not_requests`.
- **`measure.py:1403-1449`** — `write_jsonl` rewrites header + one line per result atomically (tmp, `flush`, `fsync`, `os.replace`) and `unlink`s the tmp on any failure. Raw observations must survive a crash mid-visit. Guard: `test_measure.py::test_write_jsonl_failure_removes_tmp_and_preserves_previous_file`, `::test_results_are_persisted_after_every_visit`, `::test_exception_during_visit_persists_partial_observations_and_stops`.
- **`measure.py:1504-1533`, `measure.py:1551-1603`** — `load_run`/`_cell_result`: lenient defaults only where the absence *is* the historical fact (`warmup_plateau`, `batch_spans`, `lost_visit_reason`, `request_seed`→0); everything else refuses by path and line number. A guess here silently invents a measurement on read. Guard: `test_measure.py::test_a_record_missing_a_field_is_refused_rather_than_defaulted`, `::test_a_truncated_last_line_names_the_line_it_stopped_at`, `::test_the_derived_fields_in_the_file_are_ignored_on_read`.
- **`report.py:796-893`** — `_row`: samples filtered by `measure.came_back` (not `observation.ok`), TTFT percentiles over `n = len(ttft)`, per-request metrics asked of `measure`, drift asked of `measure.measured_drift`, `short` from batches vs pin, all notes attached, floors attached last. Every published figure is assembled here. Guard: `test_report.py::test_report_asks_measure_what_came_back_rather_than_respelling_it`, `::test_failed_requests_stay_out_of_the_summary`, `::test_percentiles_need_five_samples_and_say_so_below_that`, `::test_row_carries_every_field_the_contract_names`.
- **`report.py:1185-1231`** — `_aggregate_tps`: batch spans when present, else the sum of per-request `total_s`; never reconstructs a span and never attributes an observation to a batch. Guard: `test_report.py::test_aggregate_throughput_counts_every_token_over_every_request`, `::test_a_record_without_batch_spans_keeps_the_aggregate_it_always_had`, `::test_decode_and_aggregate_throughput_are_two_different_numbers`.
- **`report.py:1513-1552`, `report.py:1596-1660`, `report.py:1497-1510`** — the join guards. Joining separately-invoked runs is "the one place this project can vary two things without noticing"; there is no latest-wins rule. `_check_harness` skips a header with no `harness` block by design. Guard: `test_report.py::test_guard_1_refuses_two_runs_that_pinned_a_header_field_differently`, `::test_guard_1_refuses_a_concurrent_column_in_a_sequential_grid`, `::test_guard_2_refuses_a_cell_two_run_directories_both_measured`, `::test_guard_3_…`, `::test_guard_4_…`, `::test_harness_source_mismatch_refuses_grid_and_sweep_joins`.
- **`report.py:1826-1876`** — `_entry`, the five states. `status != "PASS"` returns `"FAIL"` before any number is read, and the drift marker rides only `DECODE_DERIVED_RANKS`. This is the single place a FAIL row's retained number is suppressed. Guard: `test_report.py::test_a_ragged_cell_and_a_failed_cell_and_a_missing_cell_are_three_entries`, `::test_non_pass_rows_keep_values_in_summary_but_publish_no_request_figures`, `::test_a_cell_that_never_ran_says_na_and_is_not_a_rag`.
- **`report.py:1017-1055`, `report.py:1083-1126`** — drift note (three cases, threshold in one place) and `_floor_verdicts`, which *reads* measure's verdict rather than re-running a check. Guard: `test_report.py::test_the_drift_annotation_fires_above_the_threshold_and_not_below`, `::test_a_drift_dict_without_a_percentage_renders_without_raising`, `::test_a_cell_that_failed_the_coherence_gate_is_excluded_and_names_its_floor`, `::test_the_floors_are_pass_fail_and_never_weighted`.
- **`quickbench.py:322-353`** — `_cell_record`: status and numbers are taken from `report.summarize`'s row, so a number and the status beside it come from one source. Its docstring claims a failed cell carries "no number at all", but `(row or {}).get("decode_tps")` has no status test — see §7 Q1. Guard: none asserting the FAIL case.
- **`quickbench.py:646-761`** — `measure_cell`: recover→pin→measure→drift→restore, restore in `finally`, a restore that raises treated exactly as one that returned False, and drift after the cell fails it. A miss here means the user's Mac keeps measuring under settings the pin did not reach (T-05). Guard: `test_quickbench.py::test_drift_between_pin_and_restore_fails_the_cell_and_keeps_both_copies`, `::test_a_cell_that_raises_still_restores_osaurus`, `::test_a_restore_that_does_not_verify_ends_the_run_and_names_the_backup`.
- **`quickbench.py:1023-1059`** — `latest`: what `GET /recommendations` fills `measured_here` from. Keyed on `best.repo`, finished summaries only, unreadable files skipped, newest by mtime. A defect attributes one artifact's number to another repo. Guard: `test_quickbench.py::test_latest_returns_the_newest_finished_summary_per_repo`, `::test_a_stage_b_sibling_win_is_keyed_by_the_sibling_not_the_chosen_repo`, `::test_latest_of_a_missing_root_is_no_summaries`.
- **`canary.py:108-165`** — `verdict`/`verdict_line`: change is rounded to 1 dp **before** the floor comparison, zero/None baseline is "never recorded" rather than infinite, and a non-PASS row never reaches the comparison. Guard: `test_canary.py::test_exactly_the_floor_is_no_effect_on_either_side`, `::test_a_zero_baseline_is_read_as_missing_and_is_never_divided_by`, `::test_a_cell_that_failed_the_coherence_gate_is_a_fail_line`, `::test_a_pass_row_with_no_decode_rate_is_undefined_not_an_error`.
- **`sample.py:262-303`** — `peak_mb` is `max()` over samples of `phys_footprint` only; three consecutive misses stop the loop with an error; a thread that will not join is reported as an `error` on the result rather than prevented. `peak_mb` carries no cross-runtime ranking (AGENTS.md). Guard: `test_sample.py::test_sampler_peaks_on_a_real_process`, `::test_peak_is_within_10_percent_of_an_independent_reading`, `::test_sampler_stops_itself_when_the_process_goes_away`, `::test_module_never_reaches_for_ps_rss`.
- **`coherence.py:75-94`** — the language floor, four checks in order (empty, replacement chars, 75% majority script over 16+ scripted chars, word ratio < 0.5), then an optional `expect`. A `# ponytail` records that a Latin pseudo-word salad can pass. A false PASS here is a garbage number published. Guard: `test_coherence.py::test_the_captured_salad_fails`, `::test_the_salad_fails_on_its_mixed_scripts_when_nothing_was_replaced`, `::test_a_response_of_pure_debris_fails_the_word_check`.

## 5. Mechanical scan

Python patterns named by the order, over `transport.py`, `measure.py`, `coherence.py`, `sample.py`, `token_counter.py`, `report.py`, `canary.py`, `quickbench.py`. One line per hit, no judgement.

- `shell=True` — none.
- `os.system` — none.
- `eval(` — none.
- `exec(` — none.
- `pickle` — none.
- bare `except:` — none.
- `except Exception: pass` — none.
- `chmod` — `quickbench.py:237` — chmod (the 0700 backup dir).
- `tempfile.mktemp` — none.
- `open(` for write on a path built from input — `measure.py:1440` — open-w-from-input (`results_dir`); `quickbench.py:459` — open-w-from-input (`results_dir`); `canary.py:227` — write_text (fixed manifest path, not input-derived).
- `subprocess` without a timeout — none (`sample.py:64` and `quickbench.py:188` both pass `timeout` and `stdin=DEVNULL`); `quickbench.py:178` is the injectable callable itself, not a bare spawn.
- `json.loads` on unbounded input — `transport.py:308` — json.loads-per-SSE-event; `measure.py:1539` — json.loads-per-record-line; `canary.py:217` — json.loads-manifest; `quickbench.py:1042` — json.loads-summary.

Section-specific patterns:

- `mean(` — none.
- `median` — `measure.py:348-349` — median (drift halves); `measure.py:1140-1143` — median (warmup plateau); `report.py:386-391` — median (row); `report.py:1004` — median (deferred-load baseline).
- `percentile` — `report.py:372-383` — percentile definition; `report.py:850-855` — percentile calls at `n`/`MIN_PERCENTILE_N`.
- `p50`/`p90`/`p99` — `report.py:175-220` — rank names, order and printed places; `report.py:344` — `CHANNEL_DEPENDENT_RANKS`; `report.py:352-368` — absence notes; `report.py:868-870` — `percentile_note`; `report.py:1276-1277,1316-1317,1330-1335` — table columns; `report.py:1317` — sweep columns.
- `/ 0` — none (no literal division by zero).
- `or 0` — `report.py:1167` — `or 0` (`content_event_count`); `report.py:1913` — `or 0` (`n_measured` into the drift note); `measure.py:1067` — `or 0` (batch token sum).
- `max(` — `sample.py:291` — max (peak_mb); `coherence.py:85` — max (largest script share); `canary.py:89` — max (noise: worst load); `canary.py:190` — max (newest snapshot mtime); `measure.py:328` — max (ITL denominator floor 1); `quickbench.py:389` — max (stage-A winner); `quickbench.py:419` — max (best cell); `quickbench.py:632` — max (stage load label).
- `min(` — `transport.py:136` — min (deadline poll interval); `transport.py:274` — min (select timeout).
- `round(` — `canary.py:127` — round (change to 1 dp before the floor test); `quickbench.py:165` — round (estimate_seconds); `quickbench.py:954` — round (`actual_s`).
- `time.time()` used for durations — `quickbench.py:508` — `clock=time.time` default; `quickbench.py:954` — `actual_s = round(clock() - started, 3)`. (`quickbench.py:451,566` use it for a directory stamp / ISO timestamp, not a duration.) Everything else measures with `time.monotonic`: `transport.py:136,138,141,168,205,219,266,323,329,385,511`; `measure.py:1103,1112,1171,1191`; `sample.py:254,265,295`.
- `except` around a number computation — `transport.py:491-502` — failure Observation retains `ttft_s`/`last_content_s`/`total_s`, nulls the token counts; `measure.py:1185-1198` — `_request` turns any exception into a failed Observation with `total_s` only; `measure.py:1205-1207` — token-counter construction failure → N/A reason; `quickbench.py:690-706` — drift read raising → FAIL cell; `quickbench.py:703-706` — cell raise → FAIL cell; `quickbench.py:867-869` — download raise → SKIPPED cell with reason.

Swift patterns (`try!`, force-unwrap from I/O, `fatalError`, `DispatchQueue.main.sync`, `@unchecked Sendable`, `Task {` without cancellation, `print(`): **no Swift file is in this section's scope**, so none are listed here. The app's two render sites that read a quickbench cell's number are named in §4 and §7 Q1 because they consume this section's output.

## 6. Test inventory

One line per §4 hotspot: the tests that would fail if it broke.

- `transport.py:385-426` — `tests/test_transport.py::test_a_mirrored_stream_is_timed_from_the_reasoning_deltas`, `::test_a_reasoning_only_stream_times_and_counts_its_reasoning_deltas`, `::test_a_content_streaming_response_keeps_its_own_timing`, `::test_a_mirrored_stream_of_one_reasoning_delta_still_reports_a_count_of_one`, `::test_a_reasoning_channel_that_differs_from_content_keeps_content_timing`.
- `transport.py:491-519` — `tests/test_transport.py::test_a_stream_with_neither_channel_still_raises_empty_content`, `::test_incomplete_stream_is_reported_rather_than_raised`, `::test_reasoning_text_survives_an_incomplete_stream`, `::test_truncated_sse_line_is_a_framing_error`, `::test_http_status_and_content_type_errors_are_reported`.
- `transport.py:117-145` — `tests/test_transport.py::test_headers_then_stall_respects_request_deadline`, `::test_first_chunk_more_than_a_second_after_headers_is_survived`.
- `measure.py:292-328` — `tests/test_measure.py::test_the_metric_formulas_are_the_documented_ones`, `::test_decode_never_falls_back_to_total_s`, `::test_a_single_content_delta_has_no_decode_window`, `::test_itl_never_divides_by_zero_on_a_single_token`, `::test_itl_is_none_when_the_last_delta_precedes_the_first`, `::test_prefill_needs_usage_prompt_tokens`; `tests/test_report.py::test_per_request_metrics_follow_the_formulas_verbatim`, `::test_a_zero_length_decode_window_does_not_divide_by_zero`.
- `measure.py:1223-1270` — `tests/test_measure.py::test_a_fully_measurable_cell_passes`, `::test_one_failed_request_fails_the_cell`, `::test_an_incoherent_cell_fails_and_keeps_the_sample_that_failed`, `::test_a_cell_that_is_still_thinking_gets_its_own_reason`, `::test_a_response_without_content_timing_fails_the_cell`, `::test_a_response_without_usage_prompt_tokens_fails_the_cell`.
- `measure.py:1311-1342` — `tests/test_measure.py::test_more_than_half_the_judged_responses_have_to_be_incoherent`, `::test_a_response_that_did_not_come_back_is_never_called_incoherent`, `::test_incoherent_reasoning_counts_in_the_same_majority_as_content`, `::test_a_response_with_content_is_judged_on_its_content`, `::test_the_gate_makes_no_transport_call_of_its_own`.
- `measure.py:854-874` — `tests/test_measure.py::test_the_runtime_version_is_recorded`, `::test_every_start_is_asked_for_the_runs_cache_state`, `::test_an_on_cell_whose_log_does_not_show_streaming_fails_with_the_log_quoted`, `::test_each_workload_keeps_its_own_cold_load_provenance`. **Not guarded:** a version changing between visits of one cell.
- `measure.py:948-992` — `tests/test_measure.py::test_warmups_run_before_the_measurements_and_never_reach_the_samples`, `::test_every_measured_observation_is_retained_untruncated`, `::test_a_run_at_four_issues_four_requests_per_batch_and_records_one_span`, `::test_each_workload_is_measured_and_sampled_on_its_own`; `tests/test_report.py::test_aggregate_throughput_divides_by_the_batch_spans_not_the_summed_requests`.
- `measure.py:1073-1112` — `tests/test_measure.py::test_a_batchs_span_is_shorter_than_the_sum_of_its_requests`, `::test_measured_counts_batches_not_requests`, `::test_a_concurrency_one_run_is_byte_identical_to_one_that_never_heard_of_concurrency`, `::test_a_concurrent_warmup_settles_on_the_batchs_aggregate_throughput`.
- `measure.py:1403-1449` — `tests/test_measure.py::test_write_jsonl_failure_removes_tmp_and_preserves_previous_file`, `::test_results_are_persisted_after_every_visit`, `::test_exception_during_visit_persists_partial_observations_and_stops`, `::test_keyboard_interrupt_during_visit_persists_before_reraising`, `::test_a_second_run_overwrites_rather_than_appends`.
- `measure.py:1504-1533`, `measure.py:1551-1603` — `tests/test_measure.py::test_a_record_missing_a_field_is_refused_rather_than_defaulted`, `::test_a_truncated_last_line_names_the_line_it_stopped_at`, `::test_an_empty_file_names_the_header_it_is_missing`, `::test_the_derived_fields_in_the_file_are_ignored_on_read`, `::test_load_run_round_trips_every_record_of_a_real_run`, `::test_a_record_without_the_lost_visit_fields_loads_as_no_lost_visit`.
- `report.py:796-893` — `tests/test_report.py::test_report_asks_measure_what_came_back_rather_than_respelling_it`, `::test_failed_requests_stay_out_of_the_summary`, `::test_percentiles_need_five_samples_and_say_so_below_that`, `::test_a_missing_token_count_yields_none_not_zero`, `::test_row_carries_every_field_the_contract_names`, `::test_non_pass_rows_keep_values_in_summary_but_publish_no_request_figures`.
- `report.py:1185-1231` — `tests/test_report.py::test_aggregate_throughput_counts_every_token_over_every_request`, `::test_aggregate_throughput_divides_by_the_batch_spans_not_the_summed_requests`, `::test_a_record_without_batch_spans_keeps_the_aggregate_it_always_had`, `::test_decode_and_aggregate_throughput_are_two_different_numbers`.
- `report.py:1513-1552`, `report.py:1596-1660`, `report.py:1497-1510` — `tests/test_report.py::test_guard_1_refuses_two_runs_that_pinned_a_header_field_differently`, `::test_guard_1_refuses_two_runs_that_pinned_a_different_prompt_length`, `::test_guard_1_refuses_two_runs_that_pinned_different_prompts`, `::test_guard_1_refuses_two_runs_that_pinned_a_different_max_tokens`, `::test_guard_2_refuses_a_cell_two_run_directories_both_measured`, `::test_guard_3_refuses_one_format_label_pointing_at_two_artifacts`, `::test_guard_4_refuses_one_runtime_measured_at_two_versions`, `::test_harness_source_mismatch_refuses_grid_and_sweep_joins`, `::test_legacy_runs_without_harness_provenance_still_join`.
- `report.py:1826-1876` — `tests/test_report.py::test_a_ragged_cell_and_a_failed_cell_and_a_missing_cell_are_three_entries`, `::test_a_cell_that_never_ran_says_na_and_is_not_a_rag`, `::test_a_fast_cell_that_failed_a_floor_does_not_rank`, `::test_a_grid_entry_is_the_same_string_the_leaderboard_prints`.
- `report.py:1017-1055`, `report.py:1083-1126` — `tests/test_report.py::test_the_drift_annotation_fires_above_the_threshold_and_not_below`, `::test_a_row_with_no_drift_to_report_renders_without_raising`, `::test_a_drift_dict_without_a_percentage_renders_without_raising`, `::test_a_cell_that_failed_the_coherence_gate_is_excluded_and_names_its_floor`, `::test_the_floors_are_pass_fail_and_never_weighted`.
- `quickbench.py:322-353` — **none** for the FAIL-carries-no-number claim. Adjacent: `tests/test_quickbench.py::test_no_pass_cell_means_stage_b_does_not_run_and_the_summary_says_why`, `::test_an_aborted_cell_is_never_the_winner_even_with_a_number`.
- `quickbench.py:646-761` — `tests/test_quickbench.py::test_osaurus_is_recovered_pinned_and_restored_around_its_cell`, `::test_drift_between_pin_and_restore_fails_the_cell_and_keeps_both_copies`, `::test_a_cell_that_raises_still_restores_osaurus`, `::test_a_restore_that_does_not_verify_ends_the_run_and_names_the_backup`, `::test_a_restore_that_raises_ends_the_run_exactly_as_a_false_one`, `::test_an_aborted_osaurus_cell_still_restores_the_host_settings`.
- `quickbench.py:1023-1059` — `tests/test_quickbench.py::test_latest_returns_the_newest_finished_summary_per_repo`, `::test_a_stage_b_sibling_win_is_keyed_by_the_sibling_not_the_chosen_repo`, `::test_latest_of_a_missing_root_is_no_summaries`, `::test_the_summary_the_run_wrote_is_what_latest_reads`.
- `canary.py:108-165` — `tests/test_canary.py::test_exactly_the_floor_is_no_effect_on_either_side`, `::test_a_move_inside_the_floor_is_no_effect`, `::test_the_worst_moved_metric_names_the_verdict`, `::test_a_zero_baseline_is_read_as_missing_and_is_never_divided_by`, `::test_a_cell_that_failed_the_coherence_gate_is_a_fail_line`, `::test_a_pass_row_with_no_decode_rate_is_undefined_not_an_error`.
- `sample.py:262-303` — `tests/test_sample.py::test_sampler_peaks_on_a_real_process`, `::test_peak_is_within_10_percent_of_an_independent_reading`, `::test_sampler_stops_itself_when_the_process_goes_away`, `::test_sampler_retains_a_thread_that_does_not_join`, `::test_module_never_reaches_for_ps_rss`.
- `coherence.py:75-94` — `tests/test_coherence.py::test_the_captured_salad_fails`, `::test_the_salad_fails_on_its_mixed_scripts_when_nothing_was_replaced`, `::test_a_response_of_pure_debris_fails_the_word_check`, `::test_legitimate_non_english_output_passes`, `::test_a_numbered_list_is_not_a_word_salad`, `::test_still_thinking_is_not_reported_as_incoherent`.

## 7. Open questions for the reviewer

Ten, each falsifiable, each with the location that would settle it.

1. **Can a FAIL cell's number reach a user?** `quickbench._cell_record` copies `(row or {}).get("decode_tps")` with no status test (`quickbench.py:341-353`) although its docstring says a skipped or failed cell carries "no number at all" (`quickbench.py:334-336`); `report.summarize` keeps values on non-PASS rows by design (`report.py:859`, test at `tests/test_report.py:271-301`), and the app prints the cell's number beside its status with no status guard (`app/Sources/OhYesMLX/Screens/ResultsView.swift:246`, `BenchmarkView.swift:341`). Is a FAIL row's retained rate supposed to be nulled at the quickbench boundary, or is the docstring the stale half?
2. **Can a number be attributed to a runtime version that did not produce it?** `measure.py:861-865` stamps `runtime_version` only on the first visit that started (`cold_load_s is None`); a later visit that starts a different build leaves later samples under the earlier version, and `report._columns` then records whichever version a row first carries (`report.py:1677-1680`). Is a mid-run version change detected anywhere, or is it invisible by construction?
3. **Is TTFT ever measured on the wrong channel for a *partial* mirror?** The only detector is full-string equality (`transport.py:396-401`). A runtime that mirrors reasoning into content but truncates or re-chunks it keeps content timing, and `test_a_reasoning_channel_that_differs_from_content_keeps_content_timing` (`tests/test_transport.py:776`) asserts that as correct. Is a partial mirror a shape worth distinguishing?
4. **Does a response with no text contribute an end-to-end latency?** `measure.came_back` counts `empty_content` as a sample (`measure.py:1285-1298`), and `report._row` takes `e2e = [o.total_s for o in samples]` (`report.py:802,806`) while the TTFT list excludes the same observation (`ttft_s` is `None`). `n` for the e2e percentiles and for the TTFT percentiles can therefore differ. Is a time-to-nothing an end-to-end latency?
5. **Can two runs with different pins be joined?** Guard 1 compares all 12 `PIN_FIELDS` plus every workload's `messages`/`max_tokens` (`report.py:1513-1552`), but `request_seed` — the per-row fact that differs for OptiQ at an MTP depth — is not a header pin and not compared, and legacy headers predating `harness` join unconditionally (`report.py:1497-1510`). Is a join of a seeded OptiQ depth column with an unseeded one reachable through the sweep path (`report.py:2245-2385`)?
6. **Is drift computed over the same population as the row's rate?** `report.py:823` passes `result.observations` (every request) to `measure.measured_drift`, while the published rate takes the median over `samples` (`came_back` only, `report.py:802-811`). Failed observations always carry `completion_tokens=None` (`transport.py:513`) so they cannot produce a rate today — but is that an invariant or a coincidence of the current failure shape?
7. **Is a batch with one token-less-but-returned request a valid warmup rate?** `measure._warmup_rate` sums `observation.completion_tokens or 0` after checking only `came_back` (`measure.py:1063-1070`); a request that returned with `completion_tokens=None` contributes 0 tokens instead of refusing the batch, deflating that step's aggregate and moving the plateau comparison.
8. **Is `p99` on five samples a percentile?** `MIN_PERCENTILE_N = 5` lets `ttft_p99_s`/`e2e_p99_s` print from `statistics.quantiles(..., n=100, method="inclusive")[98]` (`report.py:81,372-383,851-852`), which on 5 points is an interpolation between the top two order statistics. Is the printed figure intended to be read as a tail latency at that sample count?
9. **Can `actual_s` be wrong without anything saying so?** `quickbench.run` defaults `clock=time.time` (`quickbench.py:508`) and records `actual_s = round(clock() - started, 3)` (`quickbench.py:954`), so a wall-clock step (NTP, sleep/wake) misreports the run's duration against `estimate_s`. Duration is display-only — is `time.monotonic` deliberately not used here?
10. **Can a prompt-length sweep join runs whose prompts differ?** Guard 1 drops `messages` only for `varying == "prompt_tokens"` (`report.py:1527-1529,1551`), and `_check_sweep_varies` keys the pin on its *target*, not the achieved count (`report.py:2438-2444`). Two runs at one target but different achieved prompt tokens therefore join as one column. Is that the intended reading of `sweep-pins.md:5-17`?

