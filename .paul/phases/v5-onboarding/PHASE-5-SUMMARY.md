---
phase: v5-onboarding Phase 5
completed: 2026-11-19
description: "Phase 5 complete: SwiftUI onboarding app plus a DMG release, hardened by the Fable 5.2 review (75 findings, fix plans A–G) and verified live (UAT, clean-account smoke, canaries)"
type: Summary
about: "OhYesMLX"
---

# Phase 5: SwiftUI app and packaging. Summary

## What shipped

- **`app/`**: a SwiftUI client for macOS 14 and later, with no package dependencies. Its screens are Your Mac, Engines, Models, Benchmark and Results. A launcher starts the bundled Python backend (`ohyesmlx app --lock-dir`) and owns its lifecycle.
- **`scripts/build_app.sh`**: builds `dist/OhYesMLX-0.3.0.dmg`, which is UDZO and contains the app and an Applications shortcut, alongside `.dmg.sha256` and an SBOM. The DMG carries an ad-hoc signature and bundles CPython 3.14.10, which is unpacked fresh from the hash-verified tarball and compiled with unchecked-hash pycs only.
- **Gates:**
  - `scripts/check_bundle.sh` checks P5-3, P5-4, P5-6 (read-only, then a writable copy with the signature re-verified) and P5-9.
  - `scripts/smoke_clean_account.sh` runs the bundle as `oymlxtest`.

## How it got here

| Stage | Plans |
|---|---|
| First pass, 2026-11-13/14 | 05-01 Stop now · 05-02 skeleton · 05-03 design · 05-04 shell/Your Mac/Engines · 05-05 Models/Benchmark/Results · 05-06 packaging (two review waves) |
| Fable 5.2 review, 2026-11-14/15 | 75 findings, 73 confirmed by red tests, 4 High. `.paul/review/fable-5.2/FINDINGS.md` |
| Fix plans A–G, 2026-11-16..18 | 05-07 numbers · 05-08 job lifecycle/SSE · 05-09 process identity · 05-10 downloads/disk · 05-10b port independence (inserted) · 05-11 onboarding decisions · 05-12 Osaurus pin/restore · 05-13 packaging/release |
| Close, 2026-11-18/19 | 05-14 DMG, disk meter, Pause, gatekeeper order. Live checks and UAT (`05-UAT.md`) |

## Verified at close

- pytest **1652**, swift test **123**, `build_app.sh` exit 0, `check_bundle.sh` all PASS.
- Clean-account smoke **21/21** against the bundle.
- UAT (Jason): 9/9 pass. The four issues it found were fixed in 05-14.
- **Canaries, recorded 2026-11-19:**
  - Osaurus 0.25.33: no effect on our tables.
  - vMLX 1.6.84: decode unaffected. TTFT rose across three runs (0.183 → 0.196 s against 0.181 s), which is not established either way. Cold load was 15–22 s against about 2.5 s.
- **S5-F2 constant:** the old `cold_load_s` overstated mlx-lm and OptiQ by about 1.0–1.8 s, Osaurus by about 0.3 s, and oMLX and vMLX by about 0.1 s. The audit (`docs/research/2026-11-19-cold-load-ordering-audit.md`) finds several published oMLX/mlx-lm/OptiQ orderings flip. The 35B recommendations hold.
- Jason's Osaurus settings were restored byte-exact after every pinned run. Each restore was confirmed by the script's `cmp` and by an independent `cmp`.

## Ways of working that held

- PAUL loop per plan: plan, then audit (which applies its upgrades), then apply, then a two-axis review (Standards and Spec), then unify.
- Red tests from `review/fable-verify` seed each fix. A worker's report is never evidence: the coordinator reads every diff and has caught real gaps in 05-11 T1 and 05-12.
- Workers: Command Code `cc-agent` through `.paul/orders/dispatch.sh` (DeepSeek v4.1 flash, about $0.10–0.45 per order), with Claude subagents only when unavoidable. See `.paul/HANDOFF.md`.

## Carried forward

- Phase 5.5, deferred cleanup: 10 items, listed in ROADMAP.
- Phase 5.6, UI aesthetics: waiting on Jason's list.
- The UAT flows not exercised (`05-UAT.md`).
