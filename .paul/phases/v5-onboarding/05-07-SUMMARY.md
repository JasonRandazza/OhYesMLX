---
phase: 05-app
plan: 07
subsystem: measurement
tags: [quickbench, transport, sse, runtimes, lab-path, osaurus, mlx]
requires:
  - phase: 05-app
    provides: Phase 5 first pass (05-01..05-06) and the Fable 5.2 review (FINDINGS.md, red tests on review/fable-verify)
provides:
  - Fable fix plan A closed (14 findings, 3 High)
  - Engine-scoped lab PATH; cold_load_s = spawn-to-ready
  - Per-row mlx core version and Osaurus per-model options (Jason 2026-11-16)
  - S5-F1 audit note: 2 of 216 mlx-lm rows affected
affects: [05-08, 05-09, live Phase 5 checks, any future grid]
key-files:
  created: [docs/research/2026-11-16-mlx-lm-lab-path-audit.md, tests/test_fable_s2_f*.py, tests/test_fable_s4_f5.py, tests/test_fable_s5_f{1,2,9}.py]
  modified: [ohyesmlx/runtimes.py, ohyesmlx/transport.py, ohyesmlx/measure.py, ohyesmlx/report.py, ohyesmlx/quickbench.py, ohyesmlx/osaurus_settings.py, config/osaurus-settings-baseline.json, docs/interfaces/sweep-pins.md]
key-decisions:
  - "Lab bins are per engine; a program is pinned to an absolute path only for an engine with a lab copy"
  - "mlx core version is read from what the serving process mapped (lsof), not from PATH"
  - "Osaurus per-model plist options are attested for the served model only"
  - "S5-F2's probe constant is measured later, after canaries for the new engine builds"
duration: ~5h (one session)
started: 2026-11-16T19:10:00Z
completed: 2026-11-16T21:40:00Z
description: "Fable fix plan A: FAILED cells publish no figure, the mlx-lm control no longer starts OptiQ's lab venv, cold_load_s is spawn-to-ready, the SSE reader drains its buffer, six row/report integrity fixes, and every row now records its mlx core and Osaurus thinking switch"
type: Summary
about: "OhYesMLX"
---

# Phase 5 Plan 07: Fable fix plan A — published numbers and measurement integrity

**All 14 plan-A findings are fixed on `fix/05-07`. A FAILED cell publishes no figure. Each
engine starts with only its own lab bin. `cold_load_s` ends at readiness. The SSE reader
consumes buffered events without ever blocking. Rows now record the mlx core the server loaded
and, for Osaurus, the served model's thinking switch.**

## Performance

| Metric | Value |
|--------|-------|
| Tasks | 5 planned + 2 added (Jason) + review fixes |
| Tests | 1370 → 1412 passed, 2 skipped (test-venv); all 14 red-test files red on `main`, 40 green on the branch |
| Files | 30 changed, +2879 / −179 |
| Command Code | ~$4.4 over 9 runs (DeepSeek $0.10, kimi-pro ~$4.3); 5-hour window exhausted mid-Task 3 |

## Acceptance Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| AC-1 FAILED cell publishes no figure (S2-F1) | Pass | `_cell_record` takes figures only on PASS |
| AC-2 per-engine lab PATH (S5-F1) | Pass | Plus the audit test: OptiQ start and version probe keep its lab bin, and mlx-lm gets none. The test was red-checked by removing the probe's resolution |
| AC-3 affected mlx-lm rows named (S5-F1 audit) | Pass | 47 runs / 216 rows: 2 affected (app quickbench 2026-11-02, -03), 0 undetermined; coordinator checked the logs |
| AC-4 cold_load_s spawn-to-ready (S5-F2) | Pass | Clock starts after command resolution and ends at readiness; probes follow |
| AC-5 SSE drain never blocks (S2-F2) | Pass | Peek runs non-blocking, then a framing predicate; stalled-stream test times out at its deadline. Green on 3.13 and 3.14 |
| AC-6 zero usage reasoning not taken (S2-F5) | Pass | |
| AC-7 one build per row (S2-F3) | Pass | An unknown version beside a known one is a mismatch. After review, the mlx core must also hold across visits |
| AC-8 disowned peak not published (S2-F4) | Pass | `peak_mb` None, `memory_note` carries the error |
| AC-9 transport/start failure is "not reached" (S2-F6) | Pass | Coherence is judged first; phrases are defined once in `measure.NOT_JUDGED` |
| AC-10 lost visits judged alike (S2-F7) | Pass | `sweep-pins.md` states the rule and why; stored rows are not re-judged |
| AC-11 hung engine ends its visit (S2-F8) | Pass | `HUNG_AFTER_TIMEOUTS = 2` |
| AC-12 mixed harness stamps (S2-F9) | Pass | Refused |
| AC-13 `latest` not superseded (S2-F11) | Pass | Ordered by `best.measured_at`; a newer non-winning measurement drops the older win |
| AC-14 one TIE rule (S4-F5) | Pass | `_tied_with` is shared by `_winner` and `_best` |
| AC-15 smeltMode attested (S5-F9) | Pass | Plus the plist half, now in scope (below) |
| AC-16 suite green, coordinator-observed | Pass | 1412 passed on `fix/05-07` |

## Task Commits

| Task | Commit | Description |
|------|--------|-------------|
| 2 transport | `6cd7b88` | S2-F2 drain, S2-F5 reconcile (DeepSeek) |
| 5 audit note | `2034657` | `docs/research/2026-11-16-mlx-lm-lab-path-audit.md` (kimi-pro) |
| 4 quickbench | `a6605d2` | S2-F1, S4-F5, S2-F11 (DeepSeek) |
| 1 runtimes | `8824447`, `d34226a` | S5-F1/F2/F9 (kimi-pro, round 3), then coordinator fixes |
| 3 measure/report | `4e10b49` | S2-F3/F4/F6/F7/F9 by kimi-pro; F8, F7 contract and test updates by coordinator |
| 6–7 added | `2674bcd` | mlx core per row; Osaurus per-model options attested |
| review | `a970e9e` | One lab-path lookup; mlx core held across visits |

## Decisions Made

| Decision | Rationale | Impact |
|----------|-----------|--------|
| `_spawn`/`_run` keep two parameters; `_engine_command` resolves before them | The red tests stub both with exactly two arguments | One resolver. A spawned absolute lab program still gets its own bin dir first |
| Only an engine with a lab copy has its program made absolute | Every other command is handed on as the runtime wrote it | Recorded start commands are unchanged on lab-free machines |
| S5-F2 constant measured later | It starts servers, depends on the engine build, and the fix does not need it | Deferred (below) |
| Record the mlx core per row (Jason) | Two venvs report the same mlx-lm over different cores (0.32.4 vs 0.32.2) | `mlx_version` from `lsof` of the serving pid; verified live, 0.32.2 vs 0.32.4 |
| Attest Osaurus `disableThinking` (Jason) | It decides whether the model reasons at all | Baseline records all `model_options_*`; only the served model's entry is compared |
| Lost later visit judged on its samples (S2-F7) | The order of two identical facts decided the verdict | Relaxes no floor; documented at the definition |

## Deviations from Plan

| Type | Count | Impact |
|------|-------|--------|
| Red-test corrections | 5 files | s5_f1 filter compared split PATH entries to the joined string; s5_f9, s2_f3, s2_f4 and s2_f6 controls pinned the old defect and were inverted. Each edit is stricter, not weaker |
| Existing tests updated | ~20 | They stated the old behaviour (every-engine PATH, lost-second-visit FAIL, all hung requests retained, note wording). Intent kept, names kept unless the meaning flipped |
| Scope additions | 2 | mlx core per row and Osaurus plist attestation, both on Jason's yes |
| Committed host data | 1 | `config/osaurus-settings-baseline.json` gained `smeltMode` and this host's 17 `model_options` entries (read-only capture) |
| Wave order | 1 | Task 4 ran beside Task 1 rather than in wave 2. The two are file-disjoint |
| Coordinator implementation | 3 | Coordinator finished F8, the F7 contract and the review fixes after the Command Code window ran out. Jason later reported the weekly limit at 88% |

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| Two DeepSeek workers on Task 1, one on Task 3, read for 15–20 min and wrote nothing | Stopped and re-dispatched with rulings on kimi-pro, which finished in 16–31 turns |
| Coordinator ran `git merge` in the main checkout | `main` reset to `7e555db` before anything else happened; nothing was pushed |
| Command Code 5-hour window exhausted (kimi-pro ~$1/run) | Remaining work done directly; memory `command-code-fanout-budget` updated |
| Adding `smeltMode`/`model_options` to the attestation drifts any older baseline | Pins re-record the baseline; the committed baseline was updated. A baseline without `model_options` refuses only a model the app now has options for |

## Deferred Items

- **S5-F2 constant:** measure the version probe + lsof time once per runtime, in the live Phase 5 checks session after plan B. The precondition is canaries for Osaurus 0.25.33 and vMLX 1.6.84, both untested on this host. It decides whether any published cold-load ordering could have flipped.
- **`_engine_command` reads the lab files** for any absolute command, including `lsof` and `ps`. A malformed `lab-paths.json` raises there, as it did before 05-07. Make those reads skip system binaries if it ever matters.
- **The plist is read from disk, not from cfprefsd.** A just-toggled switch can lag (`ponytail:` comment in `osaurus_settings`).

## Next Phase Readiness

**Ready:** plan B (05-08, app SSE stream, S3-F1 High) can start from this branch once it is merged.

**Concerns:** the Command Code weekly limit is at 88%. Keep the next plans mostly coordinator-direct or on Antigravity.

**Blockers:** none.

---
*Phase: 05-app, Plan: 07 · Completed: 2026-11-16*
