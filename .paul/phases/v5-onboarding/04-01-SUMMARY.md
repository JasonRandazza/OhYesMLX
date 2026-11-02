---
phase: 04-server
plan: 01
subsystem: api
tags: [http.server, localhost, bearer-token, stdlib]
requires:
  - phase: 01-03 (hardware, engines, catalog, recommend)
    provides: the shapes the server composes
provides:
  - "`ohyesmlx app`: a 127.0.0.1 JSON server with GET /hardware, /engines, /recommendations"
  - "the request guard (Host, then Origin, then per-launch token) every later endpoint sits behind"
affects: [04-02 jobs and SSE, 04-03 quickbench, 4.5 security hardening, 5 SwiftUI client]
key-files:
  created: [ohyesmlx/server.py, tests/test_server.py]
  modified: [ohyesmlx/cli.py, tests/test_cli.py, tests/test_report.py, docs/interfaces.md]
key-decisions:
  - "Error bodies carry the HTTP status (`status`), Jason 2026-11-02"
  - "`app` joins the pinned subcommand set in tests/test_report.py (worker BLOCKED report)"
completed: 2026-11-02
description: "Guarded loopback API: per-launch token, Host/Origin refusal, three composed GET endpoints, parent-death shutdown"
type: Summary
about: "OhYesMLX"
---

# Phase 4 Plan 01: Guarded localhost server — Summary

**`ohyesmlx app` serves `/hardware`, `/engines` and `/recommendations` on 127.0.0.1 only, behind a per-launch
bearer token checked after Host and Origin, with no CORS and no logic the modules do not already own.**

## Acceptance Criteria Results

| Criterion | Status | Evidence |
|-----------|--------|----------|
| AC-1 Loopback bind, one announce line, bind failure exit 2 | Pass | `lsof`: `127.0.0.1:62962` only; token 43 chars; occupied-port test (exit 2, empty stdout) |
| AC-2 Guard before routing, fixed order | Pass | Live curl: no/wrong token 401, Origin 403, foreign Host 403; refused requests run no scan (recording fake); worker red-checked each guard |
| AC-3 GET /hardware | Pass | Live: M2 Max, 64 GiB, 83.4 GB free, budget 49.4 GB |
| AC-4 GET /engines composes install plans | Pass | Live with all engines installed (plans null); live with every engine forced "not installed": real plans for all five, pip ones with `-c` constraints |
| AC-5 GET /recommendations composition | Pass | Live: 12 picks, 0 excluded, 3 `start_here` |
| AC-6 404/405/500, JSON, no-store | Pass | OPTIONS 405 with no `Access-Control-*`; `Cache-Control: no-store`; content type checked live |
| AC-7 Dies with its parent | Pass | stdin EOF -> exit 0, port released (live and subprocess test) |
| AC-8 Bounded connections, refusal trace | Pass | Idle-socket test; four live refusals wrote four stderr JSON lines, no token in any body or log |
| Human-verify checkpoint | Approved | Jason, 2026-11-02, including a browser 401 |

## Verification

- `pytest -q`: 992 passed (959 before).
- Live server checks run by the coordinator (curl matrix, `lsof`, token grep across bodies and stderr, clean shutdown).

## Deviations

| Type | What | Why |
|------|------|-----|
| Scope (file) | `tests/test_report.py` subcommand pin gained `app` | Outside the order's allowlist; the worker stopped with BLOCKED, and `app` is an approved surface |
| Scope (shape) | Error object gained `status: int` | Jason asked at the checkpoint; one table feeds both the status line and the body |
| Cosmetic | A mislabelled section comment in server.py | Coordinator fix |

## Found at the checkpoint, carried forward (v5 PLAN.md, Phase 4)

- 04-01b: `Hardware.gpu_cores` is hardcoded `None`; read `gpu-core-count` from `ioreg` (30 here).
- 04-02: `Pick.downloaded`, so a model already in the cache is not offered as a download.
- 04-02 or 4.5: Osaurus and vMLX guided plans open `releases/latest`, not the tested release.
- 4.5 (deferred, Jason): clean-account smoke via a throwaway user driven with `sudo -u`.

## Next Phase Readiness

**Ready:** the guard and the composition pattern 04-02's jobs and SSE stream will sit behind.
**Concerns:** SSE needs a long-lived response; the 10 s idle timeout and HTTP/1.0 close must be reconciled with
streaming in 04-02 (a timeout applies to reads, so a server-side writer is fine, but test it).
**Blockers:** none.

---
*Phase: 04-server, Plan: 01 · Completed: 2026-11-02*
