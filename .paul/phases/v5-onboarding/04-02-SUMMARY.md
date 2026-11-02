---
phase: 04-server
plan: 02
subsystem: api
tags: [jobs, sse, http.server, consent]
requires:
  - phase: 04-01
    provides: the guard, `_ERRORS`, `make_server` seams
provides:
  - "POST /jobs (install, download, evict), GET /jobs/{id}/events (SSE), POST /jobs/{id}/cancel"
  - "engines.install(cancel=...) checked between steps and guided polls"
affects: [04-03 quickbench, 4.5 security hardening, 5 SwiftUI client]
key-files:
  modified: [ohyesmlx/server.py, ohyesmlx/cli.py, ohyesmlx/engines.py, docs/interfaces.md, tests/test_server.py, tests/test_cli.py, tests/test_engines.py]
key-decisions:
  - "evict is a job kind (D4 needs evict-before-fetch); pinned in docs/interfaces.md"
  - "install is cancellable between steps only (audit must-have)"
completed: 2026-11-02
description: "Consent-gated install/download/evict jobs, one at a time, streamed over SSE with resume, keepalive and cancel"
type: Summary
about: "OhYesMLX"
---

# Phase 4 Plan 02: Jobs and the event stream — Summary

**The server runs one consented job at a time through the modules' own functions and streams its events; a real
351 MB download and its eviction streamed to `done` on this Mac through the live server.**

## Acceptance Criteria Results

| Criterion | Status | Evidence |
|-----------|--------|----------|
| AC-1 Names, never commands | Pass | Live: `confirmed: "true"` 400, form body 415, 5 KB body 413; tests for every args shape; red-checks (truthy confirmed; body read before length) |
| AC-2 Modules own every rule | Pass | Code read: server passes name + `True` + emit/cancel only; raise -> `internal` + `done` test |
| AC-3 One job at a time | Pass | Live 409 naming the running job; red-check (busy removed) |
| AC-4 Event stream | Pass | Live: 166 events, 163 progress, monotonic 0.0 -> 1.0, ends at `done`; resume past end closes; never-reading client dropped (red-check: cleared timeout) |
| AC-5 Cancel | Pass | Tests (download + install between steps, guided poll); live: evict 409 `not_cancellable` |
| AC-6 Shutdown, job lines | Pass | Live start/end stderr lines, no token; shutdown cancel tested; residual pip risk in docs/interfaces.md |
| AC-7 04-01 guard unchanged | Pass | Code read; guard tests still green |
| Human-verify checkpoint | Approved | Jason, 2026-11-02 |

1065 tests green. Real `~/.cache/huggingface/hub` listing unchanged (`cmp`).

## Deviations

| What | Why |
|------|-----|
| Shared 405 message reworded ("the method is not served on this path") | POST-only routes now exist; code and status unchanged |
| `_macos_major` helper shared by `/engines` and install jobs | One definition |

## Not exercised live

Cancelling a running download (tests cover it; a live run means another partial download).

## Next Phase Readiness

**Ready:** 04-03 quickbench can be a fourth job kind on the same registry and stream.
**Concerns:** the job thread runs on the request handler object after the response; it only touches
`self.server`, which outlives it, but 4.5 should look at it alongside the per-job reader cap (deferred in the audit).
