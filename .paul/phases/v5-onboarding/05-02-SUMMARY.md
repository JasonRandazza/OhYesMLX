---
phase: 05-app
plan: 02
subsystem: app
tags: [swiftui, launcher, sse, appmodel]
requires:
  - phase: 04-01
    provides: ohyesmlx app launch line, guard, routes
  - phase: 05-01
    provides: cancel now, low_disk numbers
provides:
  - "app/ Swift package: OhYesMLXKit (Models, Backend/HTTPBackend/SSE/StubBackend, BackendLauncher, AppModel), OhYesMLX (App, placeholder RootView)"
  - "scripts/dev_backend_venv.sh (.pth dev venv; OYMLX_DEV_PYTHON)"
affects: [05-04, 05-05, 05-06]
completed: 2026-11-14
description: "T5.1: Swift package, backend launcher, client with SSE, and the AppModel carrying the prototype flow and Q1-Q7"
type: Summary
about: "OhYesMLX"
---

# Phase 5 Plan 02: App skeleton — Summary

**The app spawns `python -I -m ohyesmlx.cli app` with launchd's PATH, reads the launch line from its pipe, talks to
the API with the redacted token, streams job events with resume, and drives a tested AppModel; menu Quit leaves no
backend process.**

## Acceptance Criteria Results

| AC | Result | Evidence |
|---|---|---|
| AC-1 build/test from CLI | PASS | `swift build`, `swift test` clean, no warnings, no dependencies |
| AC-2 launcher rules | PASS | LauncherTests: exact argv/env/cwd/0700, 30 s launch timeout, EOF tail, token redaction, quit escalation, flock |
| AC-2b pipes + child death | PASS | 1.1 MB stderr before the launch line; stdout drained; exit -> backend stopped + Relaunch + inflight kept |
| AC-2c Quit anyway | PASS | job-running quit sends no signal; one SIGKILL only on the click |
| AC-3 live round trip | PASS | coordinator ran it with the dev venv: decode, exit 0, port free |
| AC-4 decoding + SSE | PASS | fixtures; resume with Last-Event-ID; no Origin; poison frame skipped (review fix) |
| AC-5 AppModel a-i + Q1-Q7 | PASS | 16+ AppModelTests; Q6 gate now also blocks quickbench and Retry (review fix) |
| AC-6 app runs | PASS | coordinator: live Welcome with real hardware; menu Quit -> app and backend gone |

## Verification
- `swift test`: 48 at apply, **52** after review fixes, incl. the live test. P5-1 grep: the token's raw value only in the Authorization builder.
- Code review: stage-B rows keyed by engine and reasons parsed from message text (fixed: structured payload, no parsing);
  poison SSE frame looped forever (fixed); a second stdout line could overwrite the launch line (fixed); Q6 gate escape (fixed).

## Deviations
1. The unbundled `swift run` binary runs background-only (no Dock icon; Cmd-Q not delivered; the menu's Quit works). 05-04 sets `.regular` activation.
2. Memory renders as decimal "68.7 GB"; 05-04's `Format` shows binary "64 GB" as About This Mac does.
3. Bundle-id activation of an already-running instance is untestable until 05-06 builds the .app.
