---
description: "v5.0 Phases 1 and 2 reconciled: plan vs actual, review findings, what carries forward"
type: Summary
about: "OhYesMLX"
---

# Phases 1-2 Summary (UNIFY, 2026-10-29)

## Delivered (plan vs actual)

| Plan | Delivered | Commit |
|---|---|---|
| T1.1-T1.3 hardware scan | `hardware.scan`: chip/family/tier, cores, RAM, macOS, supported flag, disk, volumes (hidden and Recovery skipped), `model_budget` | `8285497`..`b265e6f` |
| 02-01 detection | `engines.detect_all` for five engines, file-based versions, `tested` flag; OptiQ version from pyproject (checkout) or dist-info | `d371d62` |
| 02-02 install plans | `install_plan` as data; pip engines pinned to tested versions; oMLX skips release candidates | `8c473e5` |
| 02-03 installer | `install` with 12 audited guards; real timeout and real end-to-end install checked by hand | `ba28056` |

Tests 673 -> 733. Research: `docs/research/2026-10-29-engine-install-paths.md` (incl. §8 smoke: mlx-lm venv 472 MB / 177 s, OptiQ 612 MB / 104 s).

## Deviations

- Worker assumed OptiQ writes a `__version__` literal; the real-Mac smoke showed it does not. Fixed by coordinator (pyproject / dist-info).
- Worker-committed-red slip: one test failed in `d371d62`, fixed in `acc93ad`.
- T1.2's "low-disk flag" on `Hardware` was dropped: the decision lives in the installer (AC-11). PLAN.md corrected.
- `EngineStatus.install` is `Plan|null` in the pin (server composes it in Phase 4).

## Review (Standards and Spec, cc-agent review, read-only)

Fixed 2026-10-29: output cap now one definition and counted in bytes; engines dir derived once; OptiQ pyproject read only beside a `.venv`; unknown engine names leave an install-log line; the `install` pin; T1.2 wording.
Deferred (judgement smells, no behavior risk): oMLX-specific text inside generic `_guided_plan`; test files retype `VMLX_ENGINE_INIT` and a venv path instead of asking `runtimes.py`; one budget literal asserted twice in `test_hardware.py`.

## Carries forward

- vMLX self-updated to 1.6.82 and OptiQ to 0.7.8 on this host (both `tested: false`): the reason Phase 2.5 exists.
- Real vendor installers for the three app engines remain guided/manual (no scripted install was run).
- Phase 2.5 next (manifest, lab copies, canary), then Phase 3.
