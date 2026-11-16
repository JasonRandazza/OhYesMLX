# S2 findings — measurement integrity

Reviewer: Fable 5.2 (final pass). Inputs: `dossier-S2.md`, `W1-sweep.md` (context only).
Source read only at the dossier's ranges, plus four stated leads: `transport.py:222-321`
(re-read of the SSE loop for F2), a grep of `app/Sources` for `decodeTPS` (Q1 / F1), a grep of
`report.py` for any read of `memory["error"]` (F4), and a grep of
`results/20260915T151218Z-runtime/results.jsonl` for `last_content_s` / `total_s` (F2). No code
was edited, nothing was run.

Verdict: the grid path (measure → report) holds its own rules well — FAIL never prints a number
in a joined table, drift and short windows are annotated, guards refuse rather than choose. The
defects are at the edges of that path: quickbench hands a failed cell's number to the app (F1),
the SSE reader can timestamp late or stall (F2), and three recorded facts are trusted without
being reconciled against a second fact the harness already holds (F3 version, F4 sampler error,
F5 usage split). Nothing in the dossier's "Already known" list is re-reported.

Severity order, most severe first.

### F1 — A FAILED quickbench cell carries its tok/s and TTFT to the app, which prints them
- Severity: High
- Where: `ohyesmlx/quickbench.py:346-350` (and docstring 335-337); printed at `app/Sources/OhYesMLX/Screens/ResultsView.swift:246-247` and `BenchmarkView.swift:341`
- Failure scenario: a stage-A cell returns token salad at 300 tok/s (the 2026-09-15 `mlx_lm.server` + oQ4-mtp case). `measure._set_status` marks it FAIL "incoherent output: …". `report.summarize` keeps `decode_tps` and `ttft_p50_s` on the row regardless of status (its renderers suppress them; the row does not). `_cell_record(row=rows[0])` copies both. The `result` event and `quickbench.json` carry `status: FAIL, decode_tps: 300`, and both Swift views render the figure whenever it is non-nil — beside the word "Failed". Same for "2 of 5 measured requests failed" (median of the three that came back) and F7's lost second visit.
- Evidence: `"decode_tps": (row or {}).get("decode_tps")` with no status test, under a docstring that says "a skipped or failed one carries its own status and reason with no number at all". Swift: `figure(cell.decodeTPS.map(Format.rate))`; `if let decode = cell.decodeTPS {`. Neither consults `cell.status`. `_winner` / `_best` do filter on PASS, so the recommendation and `Pick.measured_here` are not affected — only the displayed and persisted cell.
- Confidence: 85. A stubbed `run_cells` returning a FAIL result whose observations carry timings would make it 100.
- Fix direction: in `_cell_record`, take `decode_tps` / `ttft_s` from the row only when `row["status"] == "PASS"`. One place; the Swift views then need no change.
- Test idea: `measure_cell` with `run_cells` stubbed to return a FAIL `CellResult` holding five ok observations of garbage text; assert `record["decode_tps"] is None and record["ttft_s"] is None`.

### F2 — The SSE loop waits on `select()` of the raw socket while reading through a buffered reader, so buffered chunks are invisible until more bytes arrive
- Severity: Medium
- Where: `ohyesmlx/transport.py:264-292`
- Failure scenario: the response is `Transfer-Encoding: chunked` (Osaurus per the comment at 252-254; every uvicorn-served runtime). `HTTPResponse.read1` → `_get_chunk_left` → `fp.readline()` fills the 8 KiB `BufferedReader` with everything the kernel held, then returns **one** HTTP chunk. The loop goes back to `select()` on the socket, which reports nothing until another segment or EOF arrives, although the next event is already in user space. (a) Mid-stream: when the role chunk and first content chunk arrive together, every delta is thereafter stamped on the arrival of the *next* one — TTFT late by one ITL, the last content stamp pulled toward the finish chunk, decode window altered; the size depends on how each runtime flushes, so it is a cross-runtime bias, not a constant. (b) Tail: if the finish / usage / `[DONE]` / `0\r\n\r\n` chunks are read in one fill, `[DONE]` sits unread until the server closes the keep-alive connection (no `Connection: close` is sent) — `total_s`, the e2e percentiles, `batch_spans`, `aggregate_tps` and `first_request_s` grow by the server's keep-alive timeout — or until the 600 s deadline, which records a `timeout` for a request that completed.
- Evidence: `select.select([stream_socket], [], [], min(1.0, remaining))` → `if not readable: continue` → `chunk = stream_reader.read1(4096)` with `stream_reader = response`. One `read1` per wake-up, no drain of the reader before waiting again.
- Confidence: 90 that the hazard exists as written; 35 that it has moved a published number. Checked: the eleven oMLX observations in `results/20260915T151218Z-runtime` have `total_s − last_content_s` ≈ 0.5 ms, so the tail stall did not occur there (that run predates per-token streaming). What would raise it: the same subtraction over a current Osaurus and vMLX run — a second mode near a keep-alive timeout is the signature — and `ttft_s` compared against a packet capture for one request.
- Fix direction: drain before waiting — after each `read1`, keep reading while the response has buffered bytes (`response.fp.peek()` non-empty, or a non-blocking read until would-block) and only then `select`. Sending `Connection: close` fixes the tail only.
- Test idea: a fake server that writes the whole chunked SSE response (role, three content chunks, usage, `[DONE]`, terminator) in one `sendall` and holds the socket open; assert `chat_stream(timeout_s=3)` returns ok in well under 3 s. Today it times out.

### F3 — `runtime_version` is stamped on the first started visit only; a later visit's version is never compared
- Severity: Medium
- Where: `ohyesmlx/measure.py:860-865`; consumers `report.py:1624-1660` (guard 4), `report.py:1677-1680`
- Failure scenario: Osaurus (or any GUI runtime with an updater) updates between a cell's cold visit and its hot visit — the project has already watched Osaurus go 0.25.6 → 0.25.18, and guard 4's own docstring records 1.15× across one such step. The row's nine samples come from two builds; the row says the first. Guard 4 compares one string per row, so it cannot see it, and `_check_known_runtime_versions` passes.
- Evidence: `if result.cold_load_s is None: result.cold_load_s = handle.cold_load_s; result.runtime_version = handle.version` — the version assignment is under the same first-visit condition (dossier Q2 confirmed), and nothing reads `handle.version` on a later visit.
- Confidence: 70. Reading the three lines once more for indentation would settle whether the assignment is inside the `if`; the dossier states it is.
- Fix direction: on every started visit compare `handle.version` with `result.runtime_version`; on mismatch set the row FAIL with both versions in the reason (a row is one build or it is not a row).
- Test idea: fake runtime whose handle reports version "1" on visit 1 and "2" on visit 2; assert the result is not PASS under "1".

### F4 — `peak_mb` is published from a sampler that stopped early; `memory["error"]` is written and never read
- Severity: Medium
- Where: `ohyesmlx/sample.py:262-279, 290-302`; `ohyesmlx/report.py:865`; `ohyesmlx/measure.py:880`
- Failure scenario: `footprint` returns nothing three times running — it times out under exactly the load a decode peak creates — so `_loop` sets `error` to "the process has most likely exited" and returns for good while the engine is alive and still allocating. `stop()` returns `peak_mb` = the maximum of the samples taken before that. `report._row` publishes it as the cell's peak on a PASS row with no marker. This is distinct from the accepted thread-still-alive case: here the window is short and the number is low.
- Evidence: `"peak_mb": (result.memory or {}).get("peak_mb")`; a grep of `report.py` for any read of the memory dict's `error` finds none. `_highest_peak(result.memory, memory)` keeps one of two visit dicts, so the error can also be dropped when the other visit's peak is higher.
- Confidence: 70. Raise it by reading `_highest_peak` and confirming nothing between `sampler.stop()` and the row inspects `error`.
- Fix direction: a memory dict with `error` set publishes no `peak_mb` (render `—` with the error as the note), the same way a missing rate is `None` and never a leftover number. Consider not giving up on misses while the pid is still alive.
- Test idea: `summarize` over a PASS result whose `memory = {"peak_mb": 4096, "error": "footprint read nothing 3 times…"}`; assert the row's `peak_mb` is `None` or carries a note.

### F5 — The usage reasoning split is trusted without being reconciled against the reasoning text the stream delivered
- Severity: Medium
- Where: `ohyesmlx/transport.py:445-466`
- Failure scenario: a runtime streams non-mirrored reasoning deltas and then content, and its usage block carries `completion_tokens_details: {"reasoning_tokens": 0}` (a server that emits the field as a constant, or counts reasoning under content). `visible_exact = completion_tokens − 0` is all tokens, divided by a window that covers the content only: 400 reasoning + 100 content tokens publishes 5× the real decode rate, labelled `token_source: "usage"`. The counter path would have caught it — its split must sum exactly — but the usage branch runs first and skips it.
- Evidence: `if usage_reasoning_tokens is not None and completion_tokens is not None and not reasoning_only:` → usage path; the only sanity check is `visible_exact <= 0`. `reasoning_text` is in hand and is not consulted.
- Confidence: 40. No runtime here is known to do this; `docs/runtimes/*.md` or one captured usage block per runtime would settle it either way. The cost of the check is one comparison, and a new runtime is the case it protects.
- Fix direction: when `reasoning_text` is non-empty, not mirrored, and usage reports zero reasoning tokens, do not take the usage split — fall through to `resolve_token_accounting` (which reconciles or returns incomparable).
- Test idea: stream two reasoning deltas, three content deltas and `usage: {completion_tokens: 500, completion_tokens_details: {reasoning_tokens: 0}}`; assert the observation's `completion_tokens` is not 500 with `token_source == "usage"`.

### F6 — A FAIL row whose requests failed in transport is published as "coherence: pass", and the transport reason buries garbage
- Severity: Low
- Where: `ohyesmlx/report.py:1102-1106`; `ohyesmlx/measure.py:1236-1245`
- Failure scenario: one of nine requests times out and the other eight are token salad. `_set_status` returns at the `failures` branch before `_incoherent` runs, with reason "1 of 9 measured requests failed". `_floor_verdicts` sees a non-PASS status whose reason is not the gate's vocabulary and prints `coherence: pass`, `metrics: fail`. The table states the gate passed on a cell it never judged — and on garbage. Same label for nine timeouts out of nine and for "runtime did not start".
- Evidence: `elif status != "PASS": floors = [_verdict("coherence", "pass"), _verdict("metrics", "fail", reason)]`. The code already has a "not reached" state and uses it in the other direction. `_set_status`'s own comment says the gate runs before the metric check so garbage is not buried; the transport-failure branch above it does bury it.
- Confidence: 80.
- Fix direction: run `_incoherent` over the responses that came back before reporting transport failures (it already skips the ones that did not), and have `_floor_verdicts` print coherence "not reached" when the reason is a transport or start failure.
- Test idea: result with one `timeout` observation and eight garbage ones; assert the reason starts with `INCOHERENT_PREFIX`, or that the coherence floor's state is not "pass".

### F7 — A lost second visit fails the row; a lost first visit is an annotation
- Severity: Low
- Where: `ohyesmlx/measure.py:843-852` and `654-668`; contract `docs/interfaces/sweep-pins.md:174-203`
- Failure scenario: visit 1 measures five clean samples (PASS). Visit 2's `start()` fails once (port not yet released, Osaurus relaunch race). `_visit` sets `FAIL`, "runtime … did not start"; `run_cells` stores the reason in `lost[cell.id]`, which only a later measured visit consumes, so `lost_visit_reason` is never written. The mirror case (visit 1 lost, visit 2 measured) is PASS with a short-window marker. The contract says lost visits are "annotations and none of them floors … a window that was short is a result". In quickbench (3 + 2) a transient second start turns three good samples into FAIL — and, through F1, a FAIL with a number.
- Evidence: `if result.observations: result.status, result.reason = "FAIL", reason` then `return "retry"`; `_set_status` is called only on `"measured"`.
- Confidence: 55. It may be deliberate (a hot visit that never happened is a different loss from a cold one); nothing read says so, and the contract's sentence reads the other way. Jason's word decides the direction.
- Fix direction: either record `lost_visit_reason` and let `_set_status` judge the samples held (short marker applies), or write in `sweep-pins.md` that a lost *later* visit is a floor and why.
- Test idea: fake runtime that starts on visit 1 and raises on visit 2; assert the row carries `lost_visit_reason` (or assert FAIL and pin the contract sentence that says so).

### F8 — A hung engine is retried at 600 s per request with no consecutive-failure bailout
- Severity: Low
- Where: `ohyesmlx/measure.py` `_warmup_window` / `_request` (1000-1112 range); default `timeout_s=600.0` in `transport.py`
- Failure scenario: an engine accepts the connection and never answers (model load deadlock, wired-memory stall). Every request runs to the 600 s deadline. Under the plateau rule a `None` rate cannot settle, so warmup runs to `WARMUP_CAP = 20`, then the measured quota: ~25 × 600 s ≈ 4 h per workload per visit, during which the grid's other cells wait and the thermal interleave is void. In quickbench (3 warmup + 5 measured over two visits) one hung cell is ~80 min against a ~90 s estimate; "Stop now" is the only exit.
- Evidence: `_request` passes no timeout; no branch in `_workload_visit` or `_warmup_window` stops on repeated `timeout` failures.
- Confidence: 60. Raise it by confirming no caller passes a shorter `timeout_s` for `quick=True`.
- Fix direction: end the visit after two consecutive `timeout` failures (the row is already FAIL), or scale the timeout from the workload's `max_tokens`.
- Test idea: fake transport that always returns `error_kind="timeout"`; assert `_workload_visit` makes at most a small fixed number of requests.

### F9 — `_check_harness` skips a header with no `harness` key, so a pre-stamp run joins a stamped one
- Severity: Low
- Where: `ohyesmlx/report.py:1499-1502`
- Failure scenario: a 2026-09-16 column (written before `harness.source_sha256` existed) is joined with a column measured this week. The guard that exists to refuse "runs with different harness source" continues past the old header and compares nothing, though the two are different source by construction. An all-legacy join is fine and must stay readable; the mixed join is the hole.
- Evidence: `harness = header.get("harness"); if harness is None: continue`.
- Confidence: 60. If a mixed join is how old published grids are extended on purpose, this is a labelling matter rather than a refusal.
- Fix direction: refuse, or print a caveat line, when some headers carry `harness` and some do not; leave the all-absent case as it is.
- Test idea: `_check_harness` over one header with `harness` and one without; assert it raises or returns a caveat.

### F10 — A restore that raises after a pin that did not take effect is swallowed without a trace
- Severity: Low
- Where: `ohyesmlx/quickbench.py:707-717`
- Failure scenario: `recover` succeeds, `pin` raises part-way (backup written, one settings file already changed), so `pinned` stays False and the cell is SKIPPED with the pin's error. In `finally`, `restore` also raises. `restored = False if pinned else None` → `None`, `raised` is discarded, `summary["osaurus"]` records nothing and no event is sent. The user's Osaurus may be left on harness settings (idle 900, caches off) with the originals in `backup_dir` and no message naming it, until the next run's `recover`.
- Evidence: the `restored is True` / `restored is False` branches are the only ones that write anything; `None` falls through.
- Confidence: 45. Depends on whether `osaurus-pin` can change a file and then raise; S-section on the pin itself would know.
- Fix direction: treat any raised restore after `attempted` as not restored: record `restored: False`, the reason and `backup_dir`, and emit the same `restore_failed` error.
- Test idea: `pin` stub that raises, `restore` stub that raises; assert `summary["osaurus"]["restored"] is False` and the reason names `backup_dir`.

### F11 — `latest` picks by file mtime and keys only on winners, so a repo can show a superseded number
- Severity: Low
- Where: `ohyesmlx/quickbench.py:1040-1058`
- Failure scenario: run 1 chooses repo X and X wins at 60 tok/s. Run 2 (after an engine update) chooses X again, measures X at 48, and sibling Y wins. `latest` returns Y → run 2 and X → run 1: `Pick.measured_here` for X shows 60, though the newest measurement of X on this Mac is 48. Separately, ordering is `st_mtime`: a results directory copied, restored from backup or touched outranks a newer run, though each summary carries its own start time.
- Evidence: `repo = best.get("repo")` is the only key; `if repo not in found or modified > found[repo][0]`.
- Confidence: 65.
- Fix direction: order by the summary's own timestamp (`best.measured_at`), and drop a repo's older entry when a newer finished run measured that repo as a non-winning cell.
- Test idea: two summaries as above; assert `latest()` has no entry for X, or one that is not run 1's.

## Coverage

Hotspots (dossier §4; 22 entries as listed):
- `transport.py:385-426` (channel decision) — covered; Q3, no finding
- `transport.py:491-519` (failure observation) — covered; no finding
- `transport.py:117-145` — covered; no finding
- `measure.py:292-328` — covered; no finding
- `measure.py:1223-1270` (`_set_status`) — covered; F6
- `measure.py:1311-1342` (`_incoherent`) — covered; majority rule is deliberate and tested, not reported
- `measure.py:854-874` (visit stamping) — covered; F3
- `measure.py:948-992` (workload visit, sampler) — covered; F4
- `measure.py:1073-1112` (warmup) — covered; F8
- `measure.py:1403-1449` (`write_jsonl`) — covered; no finding
- `measure.py:1504-1533, 1551-1603` (`load_run`) — covered; no finding beyond the known unloadable dirs
- `report.py:796-893` (`_row`) — covered; F1, F4
- `report.py:1185-1231` (`_aggregate_tps`) — covered; no finding of its own (inherits F2's `total_s`)
- `report.py:1513-1552, 1596-1660, 1497-1510` (guards) — covered; F3, F9
- `report.py:1826-1876` (`_entry`) — covered; no finding (FAIL prints no number here)
- `report.py:1017-1055, 1083-1126` (drift note, floors) — covered; F6
- `quickbench.py:322-353` (`_cell_record`) — covered; F1
- `quickbench.py:646-761` (`measure_cell`) — covered; F10
- `quickbench.py:1023-1059` (`latest`) — covered; F11
- `canary.py:108-165` — covered; no finding (non-PASS rows never reach the comparison)
- `sample.py:262-303` — covered; F4
- `coherence.py:75-94` — covered; no finding

Open questions (dossier §7):
- Q1 FAIL cell's number reaching the user — covered; confirmed, F1
- Q2 `runtime_version` first visit only — covered; F3
- Q3 partial mirror — covered; no finding: with no usage split the counter's exact-sum rule returns incomparable, which fails safe; with one, see F5
- Q4 `empty_content` in e2e — covered; no finding: any such observation fails `_missing_metric`, so it never reaches a PASS row
- Q5 `request_seed` not a compared pin / legacy headers — covered; `seed` is a compared pin and the per-row exception is a function of pinned fields, no finding; legacy headers, F9
- Q6 drift over all observations — covered; no finding: on a PASS row every observation is a sample
- Q7 `_warmup_rate` counting `None` as 0 — covered; no finding: it moves only where warmup ends, and the same condition fails the measured window
- Q8 P99 over five samples — covered; no finding: numpy's definition, `n` is on the row; at n ≤ 9 it is the maximum in effect, which the row's `n` lets a reader see
- Q9 `actual_s` on `time.time` — covered; not filed: a wall-clock step skews an informational duration only
- Q10 prompt-length sweep keyed on target — covered; no finding: the achieved count rides the pin note and guard 2 still refuses a duplicate cell at one target

Coverage: 32 / 32.
