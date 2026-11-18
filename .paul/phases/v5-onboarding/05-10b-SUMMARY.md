---
phase: 05-app
plan: 10b
subsystem: runtimes
tags: [ports, resident-engine, ps, lsof, quickbench, measure]
requires:
  - phase: 05-09
    provides: start refusal while any engine is resident; ledger identity; `_stop_command_for_port`
provides:
  - resident engines found by process on any port (`runtimes.resident_engines`, `_engine_of`)
  - one port decision for start and quickbench (`runtimes.port_plan`), failing closed on an unrecognised model server
  - free-port fallback when a default port is held by a non-engine (Osaurus never moves)
  - `port` on every row; ledger entries name their runtime
affects: [plan E (05-11), live Phase 5 checks, runner scripts' port sweeps]
key-files:
  created: [tests/test_port_independence.py]
  modified: [ohyesmlx/runtimes.py, ohyesmlx/quickbench.py, ohyesmlx/measure.py, AGENTS.md, docs/interfaces/measurement-core.md, docs/runtimes/{omlx,vmlx,mtplx,osaurus}.md]
key-decisions:
  - "An engine is a process, matched on ps comm + anchored args, never argv split on whitespace"
  - "A default-port holder is a model server (refuse) if it lives in an engine root or answers /v1/models with a list or 401/403"
  - "Osaurus never moves off 1337 (its port also lives in ~/.osaurus/config/server.json)"
  - "05-09's port-only refusal reversed: a non-engine on another runtime's default port no longer blocks"
duration: ~1 session (2026-11-17..18)
completed: 2026-11-18
description: "A resident engine is found by its process on any port and named with pid and port; a default port held by something that is not an engine moves the engine to a free port, recorded on every row; Osaurus never moves"
type: Summary
about: "OhYesMLX"
---

# Plan 05-10b: Port independence — Summary

**Engines are recognised by what they run, not where they listen.** `Runtime.start` and quickbench ask one
function, `runtimes.port_plan`. It refuses while any engine is resident on any port and names the engine,
pid and port. When a default port is held by something that is not an engine, it moves the engine to a free
loopback port. A holder that looks like a model server still refuses. Osaurus never moves.

## Acceptance Criteria Results

| Criterion | Status | Evidence |
|-----------|--------|----------|
| AC-1 engine on a non-default port blocks, named | PASS | `test_a_resident_engine_refuses_every_start_naming_engine_pid_and_port`; live: hand-started `mlx_lm.server` on 8091 → canary refused "quit mlxlm (pid 21749, port 8091) first" (message wording before review fix: "an engine is resident: mlxlm (pid 21749, port 8091)") |
| AC-2 one definition of an engine process | PASS | `_engine_of` is the only matcher; `resident_engines` its only scan; `_resident_osaurus_pids` deleted; `quickbench._osaurus_app_running` asks `resident_engines` (review fix) |
| AC-3 non-engine on a default port: engine moves | PASS | `test_a_start_whose_default_port_a_non_engine_holds_moves_to_a_free_port` (argv, handle, base_url, ledger, one `port_moved` line); live: http.server on 8081 → mlx-lm on 65197, cell PASS, http.server untouched |
| AC-3b unrecognised model server never moved around | PASS | engine-root and `/v1/models` tests (real local HTTP server for 200+data / 401 / 403 / 200 non-list / 404 / no answer) |
| AC-4 Osaurus does not move | PASS | `test_osaurus_never_moves`, `test_an_osaurus_start_whose_port_a_non_engine_holds_is_refused` |
| AC-5 port on every row | PASS | `test_the_port_is_on_every_row_and_a_record_without_one_loads_as_none`; live row `port=65197`; all 250 loadable run dirs in `results/` load with `port=None` (the same 13 unloadable as on main) |
| AC-6 orphan on a fallback port can be stopped | PASS | `_stop_command_for(entry)` by `runtime` name, port fallback for pre-plan entries (3 tests) |
| AC-7 quickbench skips only for an engine | PASS | `_port_refusal` = `port_plan(...).refusal`; "quit <engine> (pid, port) first" (review fix); `ps` unreadable skips instead of crashing (review fix) |

## Verification

- `test-venv/bin/python -m pytest -q`: **1540 passed**, 2 skipped (worktree has no `results/`; both run green against the main checkout's results).
- New tests observed red before the fix (36/36 initial; the 2 review tests red against `9637ce6`).
- Real-process check (no engine): a plain `http.server` on 8081 → `port_plan(mlxlm)` moves; a fake `mlx_lm.server` module on 8091 → every start refused.
- Live checkpoint 2026-11-18 (Jason's go): steps 1–3 as planned, all PASS; ports 8081/8091 and the fallback ports released, no leftovers.
- `graphify update .` run.
- After merge to main (`f7fe00f`): **1542 passed**, 0 skipped.

## Commits

| Commit | What |
|--------|------|
| `9637ce6` | Tasks 1–3: scan, `port_plan`, fallback, ledger by name, `port` on rows, docs |
| `fa0023b` | Review fixes (below) |

## Deviations

1. **05-09 behaviour reversed by design.** Two existing tests asserted that any listener on another runtime's default
   port refused a start. They now assert the new rule: `test_a_non_engine_on_another_runtimes_port_no_longer_blocks_a_start`
   and the S5-F3 red test, which now uses an engine process in its fake process list (a stronger version of the finding).
2. **Deleted with no remaining caller:** `_resident_osaurus_pids`, `_stop_command_for_port`, `quickbench._port_busy`;
   the quickbench hook `port_in_use(port)` became `port_refusal(name)`. Test fakes were updated to match.
3. **`docs/interfaces.md` in the plan is stale:** the row schema lives in `docs/interfaces/measurement-core.md`, and that is
   the file updated. `v5-app.md` and `v5-quickbench.md` got the two renamed names.
4. **First live attempt was void:** mlx-lm exited at once because `python` resolved to a mise shim. The mlx-lm venv
   was not on PATH (the AGENTS.md hazard; `run_canary.sh` exports it). The re-run with that PATH is the result above.
5. **Canary verdict "moved -23%" not attributed.** Load average was 4.5–5.3 (above the 4.0 noisy line). Nothing was
   recorded (`--record` not passed). Which port the engine listens on does not enter decode. Untrusted as a speed reading.

## Two-axis review (Sonnet subagents, Standards + Spec), fixed in `fa0023b`

- Std: `ps` unreadable raised out of quickbench's stage loop. Now a skip reason. Red-checked.
- Std: `Runtime.start` re-entered itself, forwarding 7 kwargs and scanning twice. Now it rebinds `self` to the moved runtime.
- Std: the between-visits note shared `PORT_MOVED_CODE`. It now has `measure.PORT_CHANGED_CODE`.
- Std: matching documented as best-effort in both directions where it is defined.
- Spec AC-7: the refusal reads "quit <engine> (pid, port) first". Red-checked.
- Spec AC-2: `_osaurus_app_running` asks `resident_engines` instead of a second matcher.
- Not changed: `_listener_pids` vs `_listening_ports` (by-port vs by-pid questions). Lab venv roots catch any process
  from that venv on a default port (fails closed). A holder pid missing from `ps comm` leaves only the probe (a race window).

## Deferred

- Runner scripts' `sweep()` kills by default port with kill -9 (about 20 scripts, pre-existing; documented in AGENTS.md).
- How the oMLX, vMLX and MTPLX apps launch their own servers is not established from the bundles
  (`docs/runtimes/*.md`). On another port such a server is visible only if its argv matches.
- A user port override (ROADMAP step 3): not needed so far.

## Next

Plan E (05-11). Live Phase 5 checks still open: the app UI download and Stop now. The backend API download was checked 2026-11-17 (STATE).
