---
phase: 05-app
plan: 01
subsystem: api
tags: [quickbench, cancel, abort, low_disk]
requires:
  - phase: 04-03b
    provides: quickbench.run, the job registry, POST /jobs/{id}/cancel
  - phase: 045-02a
    provides: the running-engines ledger and _shutdown
provides:
  - "POST /jobs/{id}/cancel {\"now\": true}: a quickbench stops mid-cell (engine stopped outside measure.py)"
  - "runtimes.stop_own_engines; quickbench ABORTED cell status"
  - "low_disk payloads carry free_bytes / needed_bytes"
  - "structured cell progress payload {stage, engine, format, status, reason} (review fix)"
affects: [05-02 client, 05-05 Benchmark/Results]
key-files:
  modified: [ohyesmlx/server.py, ohyesmlx/runtimes.py, ohyesmlx/quickbench.py, ohyesmlx/fetch.py, ohyesmlx/engines.py, docs/interfaces/v5-onboarding.md, docs/interfaces/v5-quickbench.md]
completed: 2026-11-14
description: "Stop now: a quickbench can be stopped mid-cell, the cell is ABORTED with no number, and every restore still runs"
type: Summary
about: "OhYesMLX"
---

# Phase 5 Plan 01: Stop now — Summary

**`{"now": true}` on a quickbench cancel stops the in-flight engine from a daemon thread and records the cell
ABORTED with no figure; the run ends `cancelled` through the existing restore/evict tail. `measure.py` is untouched.**

## Acceptance Criteria Results

| AC | Result | Evidence |
|---|---|---|
| AC-1 body validated, bodyless unchanged | PASS (after review fix) | test_server: bodyless/`{}`/now/bad_args/not_abortable/415/413/400; review fix: bodyless = no Content-Length and no Content-Type, `Content-Length: 00` is zero |
| AC-2 stop_own_engines | PASS | test_runtimes: own file only, returns 2, never writes, failure line then next entry |
| AC-3 ABORTED cell, cancelled ending | PASS | test_quickbench stage A and stage B aborts; restore + eviction asserted; `_winner` already gates on PASS (no change) |
| AC-4 server wiring | PASS | fake blocking quickbench + fake stop_engines |
| AC-5 docs point at one definition | PASS | v5-quickbench.md ABORTED line; v5-onboarding.md one sentence |
| AC-6 low_disk numbers | PASS | fetch ×2, engines ×1, payload asserted |
| AC-7 race safety | PASS (after review fix) | 202 before a blocked stop; one stop per job; a raise from measure_cell while aborted -> ABORTED (test added in review) |

## Verification
- `pytest -q`: 1360 at apply, **1366** after review fixes (baseline 1329). Coordinator ran both.
- Code review (Standards + Spec, `.paul/review/2026-11-14-phase5-w1/`): stage-B cells collapsed client-side because
  the stage-B payload named only the winner engine (fixed: structured payload); a test that could not fail and an
  untested except branch (fixed); abort rationale restated three times (fixed: once, in `_aborted`).
- Not run: a live "Stop now". Per the standing rule it needs Jason's go-ahead and a quiet machine; carried to 05-06's live checks.

## Deviations
1. Absent `Content-Length` with a body cannot be detected under HTTP/1.0; the review fix keys "bodyless" on both headers being absent, so a JSON Content-Type with no length is 413 as on `POST /jobs`.
2. `_entry_stop_command` extracted so the ledger's stop-command parse has one definition (behaviour identical).
3. `scripts/smoke_clean_account.py` still reads the retired `payload["skipped"]` key (dead branch, still functional); fix when 05-06 reruns the smoke.
