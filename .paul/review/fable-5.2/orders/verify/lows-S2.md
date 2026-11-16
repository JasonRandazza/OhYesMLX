# Order: verify one Fable 5.2 finding (V step)

You verify one finding from a senior reviewer. Its report is a claim, not evidence. Your job is to prove it or refute it.

You run inside the `fable-verify` Orca worktree (branch `review/fable-verify`). Write exactly one report file:
`.paul/review/fable-5.2/verify/<FINDING-ID>.md`. If you can write a test, put it in a NEW file named after the finding
(`tests/test_fable_<finding-id>.py`, or `app/Tests/OhYesMLXKitTests/Fable<FindingId>Tests.swift`), so parallel
verifiers never edit the same file. Never fix the code.

Method:
1. Read the cited code (the ranges named) and its dossier entry. The dossiers live in the main checkout (read-only, absolute path):
   `/Users/jrazz/Dev/active/OhYesMLX/.paul/review/fable-5.2/dossier-S<n>.md`. Restate the claim in one line.
2. Try to reproduce it with the smallest failing test (pytest, or a swift test in app/Tests). Run only that test:
   `/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python -m pytest -q <file>::<name>` or
   `cd app && swift test --filter <name>`. A test that passes on the current code means the claim is not reproduced.
3. If no test is possible (a race needing real timing, a GUI-only path, packaging), give the concrete evidence instead:
   the exact code path with line numbers, or a command and its output.
4. End the file with exactly one verdict line:
   `VERDICT: CONFIRMED (test: <path::name>)` or `VERDICT: CONFIRMED (no test: <why>)` or `VERDICT: REFUTED (<evidence>)`
   and a line `SEVERITY-CHECK: agree | lower to <x> | raise to <x> — <why>`.
Never start a server, engine, model download or the app. Never edit code outside the one test you add.

---
FINDING:
 (BATCH) S2-F6 S2-F7 S2-F8 S2-F9 S2-F10 S2-F11

BATCH RULE: verify each finding below separately, one after another, applying the method above to each and writing
one report per finding (verify/<FINDING-ID>.md, each ending in its own VERDICT and SEVERITY-CHECK lines) and one test
file per finding. These are Low severity: prefer reading the code path and citing it when a test would need more
than about 40 lines. Do not spawn subagents.

=== FINDING-ID: S2-F6 ===
### F6 — A FAIL row whose requests failed in transport is published as "coherence: pass", and the transport reason buries garbage
- Severity: Low
- Where: `ohyesmlx/report.py:1102-1106`; `ohyesmlx/measure.py:1236-1245`
- Failure scenario: one of nine requests times out and the other eight are token salad. `_set_status` returns at the `failures` branch before `_incoherent` runs, with reason "1 of 9 measured requests failed". `_floor_verdicts` sees a non-PASS status whose reason is not the gate's vocabulary and prints `coherence: pass`, `metrics: fail`. The table states the gate passed on a cell it never judged — and on garbage. Same label for nine timeouts out of nine and for "runtime did not start".
- Evidence: `elif status != "PASS": floors = [_verdict("coherence", "pass"), _verdict("metrics", "fail", reason)]`. The code already has a "not reached" state and uses it in the other direction. `_set_status`'s own comment says the gate runs before the metric check so garbage is not buried; the transport-failure branch above it does bury it.
- Confidence: 80.
- Fix direction: run `_incoherent` over the responses that came back before reporting transport failures (it already skips the ones that did not), and have `_floor_verdicts` print coherence "not reached" when the reason is a transport or start failure.
- Test idea: result with one `timeout` observation and eight garbage ones; assert the reason starts with `INCOHERENT_PREFIX`, or that the coherence floor's state is not "pass".


=== FINDING-ID: S2-F7 ===
### F7 — A lost second visit fails the row; a lost first visit is an annotation
- Severity: Low
- Where: `ohyesmlx/measure.py:843-852` and `654-668`; contract `docs/interfaces/sweep-pins.md:174-203`
- Failure scenario: visit 1 measures five clean samples (PASS). Visit 2's `start()` fails once (port not yet released, Osaurus relaunch race). `_visit` sets `FAIL`, "runtime … did not start"; `run_cells` stores the reason in `lost[cell.id]`, which only a later measured visit consumes, so `lost_visit_reason` is never written. The mirror case (visit 1 lost, visit 2 measured) is PASS with a short-window marker. The contract says lost visits are "annotations and none of them floors … a window that was short is a result". In quickbench (3 + 2) a transient second start turns three good samples into FAIL — and, through F1, a FAIL with a number.
- Evidence: `if result.observations: result.status, result.reason = "FAIL", reason` then `return "retry"`; `_set_status` is called only on `"measured"`.
- Confidence: 55. It may be deliberate (a hot visit that never happened is a different loss from a cold one); nothing read says so, and the contract's sentence reads the other way. Jason's word decides the direction.
- Fix direction: either record `lost_visit_reason` and let `_set_status` judge the samples held (short marker applies), or write in `sweep-pins.md` that a lost *later* visit is a floor and why.
- Test idea: fake runtime that starts on visit 1 and raises on visit 2; assert the row carries `lost_visit_reason` (or assert FAIL and pin the contract sentence that says so).


=== FINDING-ID: S2-F8 ===
### F8 — A hung engine is retried at 600 s per request with no consecutive-failure bailout
- Severity: Low
- Where: `ohyesmlx/measure.py` `_warmup_window` / `_request` (1000-1112 range); default `timeout_s=600.0` in `transport.py`
- Failure scenario: an engine accepts the connection and never answers (model load deadlock, wired-memory stall). Every request runs to the 600 s deadline. Under the plateau rule a `None` rate cannot settle, so warmup runs to `WARMUP_CAP = 20`, then the measured quota: ~25 × 600 s ≈ 4 h per workload per visit, during which the grid's other cells wait and the thermal interleave is void. In quickbench (3 warmup + 5 measured over two visits) one hung cell is ~80 min against a ~90 s estimate; "Stop now" is the only exit.
- Evidence: `_request` passes no timeout; no branch in `_workload_visit` or `_warmup_window` stops on repeated `timeout` failures.
- Confidence: 60. Raise it by confirming no caller passes a shorter `timeout_s` for `quick=True`.
- Fix direction: end the visit after two consecutive `timeout` failures (the row is already FAIL), or scale the timeout from the workload's `max_tokens`.
- Test idea: fake transport that always returns `error_kind="timeout"`; assert `_workload_visit` makes at most a small fixed number of requests.


=== FINDING-ID: S2-F9 ===
### F9 — `_check_harness` skips a header with no `harness` key, so a pre-stamp run joins a stamped one
- Severity: Low
- Where: `ohyesmlx/report.py:1499-1502`
- Failure scenario: a 2026-09-16 column (written before `harness.source_sha256` existed) is joined with a column measured this week. The guard that exists to refuse "runs with different harness source" continues past the old header and compares nothing, though the two are different source by construction. An all-legacy join is fine and must stay readable; the mixed join is the hole.
- Evidence: `harness = header.get("harness"); if harness is None: continue`.
- Confidence: 60. If a mixed join is how old published grids are extended on purpose, this is a labelling matter rather than a refusal.
- Fix direction: refuse, or print a caveat line, when some headers carry `harness` and some do not; leave the all-absent case as it is.
- Test idea: `_check_harness` over one header with `harness` and one without; assert it raises or returns a caveat.


=== FINDING-ID: S2-F10 ===
### F10 — A restore that raises after a pin that did not take effect is swallowed without a trace
- Severity: Low
- Where: `ohyesmlx/quickbench.py:707-717`
- Failure scenario: `recover` succeeds, `pin` raises part-way (backup written, one settings file already changed), so `pinned` stays False and the cell is SKIPPED with the pin's error. In `finally`, `restore` also raises. `restored = False if pinned else None` → `None`, `raised` is discarded, `summary["osaurus"]` records nothing and no event is sent. The user's Osaurus may be left on harness settings (idle 900, caches off) with the originals in `backup_dir` and no message naming it, until the next run's `recover`.
- Evidence: the `restored is True` / `restored is False` branches are the only ones that write anything; `None` falls through.
- Confidence: 45. Depends on whether `osaurus-pin` can change a file and then raise; S-section on the pin itself would know.
- Fix direction: treat any raised restore after `attempted` as not restored: record `restored: False`, the reason and `backup_dir`, and emit the same `restore_failed` error.
- Test idea: `pin` stub that raises, `restore` stub that raises; assert `summary["osaurus"]["restored"] is False` and the reason names `backup_dir`.


=== FINDING-ID: S2-F11 ===
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

