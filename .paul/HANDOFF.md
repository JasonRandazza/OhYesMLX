---
description: "OhYesMLX (OYMLX) session handoff, 2026-11-01: v5.0 Onboarding App, Phases 0-3 built"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-11-01

> Read this, then `.paul/STATE.md` (Decisions 134-137), `.paul/phases/v5-onboarding/PLAN.md`, then `AGENTS.md`. STATE wins on conflict.
> Previous handoff (MTPLX class landed, 2026-10-10): `.paul/archive/2026-10-10-handoff-mtplx-class-landed.md`. Jason calls the project **OYMLX** in conversation.

## Where things stand

OYMLX is being turned from a CLI benchmark into a guided app for non-technical Mac owners (v5.0, Decision 134; MTPLX v4.0 is parked on branch `mtplx-wip`, commit `925c4a4`, unmerged). Architecture: a stdlib Python backend (headless, test-driven) behind a localhost JSON API, with a SwiftUI shell on top. **Phases 0-3 are built and committed on `main`; 945 tests pass.** Nothing in Phases 4-5 exists yet: no server, no `quickbench`, no Swift.

| Phase | Built | Where |
|---|---|---|
| 0 contract | governance, decisions D1-D8, pinned shapes | `docs/interfaces.md` "v5.0 -- Onboarding shapes" |
| 1 hardware | `hardware.scan`: chip, RAM, disk, volumes, `model_budget` | `ohyesmlx/hardware.py` |
| 2 engines | `detect_all`, `install_plan` (data), consent-gated `install` (12 audited guards) | `ohyesmlx/engines.py` |
| 2.5 version stability | tested-versions manifest, `canary`, machine-local `lab-paths.json`, lab-copy doc | `ohyesmlx/engines-tested.json`, `canary.py`, `docs/runtimes/lab-copies.md` |
| 3 models | revision-pinned catalog (12 models), `recommend.pick`, `fetch` (HF-cache layout, resumable, ledger-limited evict) | `catalog.py/.json`, `recommend.py`, `fetch.py` |

Plans, audits and per-phase summaries live in `.paul/phases/v5-onboarding/` (`02-0x`, `025-0x`, `03-0x` PLAN/AUDIT, `PHASE-1-2-SUMMARY.md`, `PHASE-2.5-3-SUMMARY.md`).

## Do next, in this order

1. ~~Code-review gate for Phases 2.5 and 3~~ **done 2026-11-02**: Standards + Spec read-only reviews, 9 verified findings fixed in one worker pass (canary None/zero crash, non-LFS files now checked by git blob sha1, canary honours `HF_HUB_CACHE`, one download at a time per Decision 138, one path guard and one `catalog.disk_needed`). Orders and logs: `.paul/orders/v5-review-25-3-*`.
2. **Plan Phase 4** (`/paul:plan`, then `/paul:audit` on it; the localhost API is the riskiest surface: CSRF from any web page, so install/download jobs must take engine/repo NAMES only and require `confirmed`): `ohyesmlx app` server, `GET /hardware /engines /recommendations`, jobs with an SSE event stream, `quickbench` (D3 two-stage, D4 10-minute budget, D5 "measured on your Mac"). `recommend` is meant to be composed as `{picks, excluded, unsupported_reason}` (see its `Pick` pin). `quickbench` must prepend engine lab bin dirs to PATH the way `runtimes._engine_env` already does.
3. **Phase 5**: run the `prototype` skill for the screens first, then SwiftUI tickets (XCTest with a stub client), packaging with bundled standalone Python (D6) and an unsigned right-click-Open zip (D7).
4. Still owed to Jason's hands: `scripts/lab-copies-wizard.sh` (generate with the `wizard` skill from `docs/runtimes/lab-copies.md`) to archive the tested DMGs of Osaurus, oMLX, vMLX and turn their auto-update off; ~~T2.5.5~~ done 2026-11-02 (`ohyesmlx/constraints/<engine>-<version>.txt`, applied by `install_plan` with `pip -c`).

## Decisions waiting on Jason

- OptiQ's 0.5.13 to 0.7.8 self-update cut TTFT ~30% (Decision 136). Re-run the OptiQ columns of published tables, or label them 0.5.x? Harness here runs the 0.5.13 lab copy.
- Merge or keep parking `mtplx-wip`; the 0.3.1 version bump; Apple Developer account for notarization (not needed before Phase 5 packaging); README rewrite (deferred since 2026-10-09).
- Vault: a short decision note for v5.0 (Decisions 134-137) is proposed, not written (needs Jason's yes per the Vault Contract).

## Standing rules and traps learned this session

- **Pytest** lives in a permanent venv: `/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python -m pytest -q` (the old temp-job venv in older docs is gone; 20 scripts and AGENTS.md now point here; three `fetch_*.sh` scripts still reference a missing `hf` binary).
- **Osaurus**: Jason's standing authorisation (2026-10-29) lets any test or canary pin it (idle 900, caches off) if his own settings (idle 30) are restored byte-exact and the report says so. Always go through `scripts/osaurus-pin.sh`; `scripts/run_canary.sh` is the pattern. Verify with `cmp`.
- **Measuring**: confirm with Jason first; machine quiet. `ohyesmlx canary --yes` (all five ~17 min; one engine ~3-4 min); it reads load average and refuses to `--record` a noisy engine. Time Machine's post-backup thinning is light and was tolerated. First baselines are in `ohyesmlx/engines-tested.json` (OptiQ at 0.7.8 and vMLX at 1.6.82 are untested builds).
- **Lab copy**: `~/Library/Application Support/OhYesMLX/lab-paths.json` points OptiQ at the pinned 0.5.13 venv; delete it to use the global install. A pinned package is not a pinned build: OptiQ needs `mlx-lm==0.31.3` beside it or it serves HTTP 404.
- **Workers** (`cc-agent`, DeepSeek v4.1 flash): set `CC_AGENT_MAX_TURNS=300`; they cannot reach the network reliably; `review`/`explain` cannot run shell; a worker may write a `BLOCKED.md` at the repo root (read it as a finding, then delete it; the stale tracked copy was removed 2026-11-02); a worker's BLOCKED report is a finding (this session one caught a wrong literal in a coordinator order). If cc-agent says "Not authenticated", Jason runs `! cmd login`. The coordinator reviews every diff and runs the suite and a real-Mac smoke itself: that caught the OptiQ version bug and the machine-specific manifest path, which tests did not.
- Keep graphify current: a post-commit hook rebuilds it; workers are told to use `graphify query`.
- oMLX also scans the user's HF cache (AGENTS.md corrected 2026-11-01); the downloader writes the HF cache layout on purpose.
- Search tools for workers: `searxng` (Omarchy, `http://100.73.137.9:8888`) first, then Tavily, then Exa.
