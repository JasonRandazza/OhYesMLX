---
phase: v5-onboarding
plan: 05-14
completed: 2026-11-19
description: "Phase 5 close polish: the DMG replaces the zip, the disk meter shows the disk, the download control says Pause, and the gatekeeper steps go approval-first; plus the live Phase 5 checks"
type: Summary
about: "OhYesMLX"
---

# Plan 05-14: Phase 5 close polish, plus the live Phase 5 checks

## Acceptance Criteria

| AC | Status | Evidence |
|---|---|---|
| AC-1 DMG replaces the zip | Pass | `dist/OhYesMLX-0.3.0.dmg` (UDZO) holds `OhYesMLX.app` and an `Applications` symlink, verified by mounting it read-only. `.dmg.sha256` is written and no zip is built. |
| AC-2 The disk meter shows the disk | Pass | `Hardware.disk_total_bytes` comes from the same volume probe as free space. The bar shows used space against the total, with what the download still needs as a separate segment, and is hidden when the total is unknown. Screenshots: `docs/design/phase5/shots-05-14/`. |
| AC-3 The download button reads Pause | Pass | Screenshot. The Cancel button in the Remove sheet is unchanged. |
| AC-4 The gatekeeper doc goes approval-first | Pass | `docs/release/gatekeeper.md` rewritten. |
| AC-5 Gates | Pass | pytest 1649, swift 123, the build, and `check_bundle.sh` all PASS. |

The worker was one Command Code `implement` run: 87 turns, $0.10. `check_bundle` still builds its own temporary image instead of mounting the release DMG, because P5-6 needs a freshly formatted read-only mount plus a writable copy.

## Live Phase 5 checks (2026-11-18 and 2026-11-19)

| Check | Result |
|---|---|
| Quarantined download (gatekeeper release check) | PASS for the zip build on macOS 27.2.1. macOS blocks the app first, offering only "Move to Trash" or "Done". After Open Anyway, the in-app move screen appeared and the app served `/hardware`. That first run is what found this plan's four items. |
| App-UI download | PASS. Pause and immediate resume work; Jason ran it by hand. |
| Clean-account smoke against the bundle (S6-F5) | **21/21 PASS** as `oymlxtest`. The artifact was the copied `OhYesMLX.app` from the 05-14 build at HEAD `99b6d06`. `verify-host` reported Jason's account unchanged. Teardown is done and the results are in `/Users/Shared/oymlx-smoke/results/20261119T003641Z.json`. |
| Canary, Osaurus 0.25.29 → 0.25.33 | **No effect on our tables.** Decode 61.2 tok/s against a 63.1 baseline (−3.0%), TTFT 0.306 s, load 2.7 → 3.5. Run `results/canary/20261119T183321Z-osaurus`. The first attempt is kept as `…-osaurus.DISCARDED-load-4.6-noisy-and-unsettled-warmup`: Spotlight was at about 300% CPU and Wallspace was decoding video on the GPU. |
| Canary, vMLX 1.6.82 → 1.6.84 | **No effect on our tables.** Decode 77.0 tok/s against 74.5 (+3.4%), TTFT 0.189 s. Run `…183838Z-vmlx`, with the earlier +8.2% reading kept as `…003041Z-vmlx`. Cold load was **15.1 s, and 22.2 s the run before, against about 2.5 s on 1.6.82**. That is an observation: the canary does not judge cold load. |
| Osaurus pin and restore | Both canary runs restored byte-exact. The script's `cmp` and the coordinator's independent `cmp` of `server.json` and `server-runtime.json` agree. The only other change was `sandbox.json`, Osaurus's own startup timings. |
| S5-F2 constant | Measured on a quiet machine with Sidecar, Chrome and Obsidian closed. The version probe's warm median, with the cold first call in brackets: mlx-lm 0.94 s (1.76), OptiQ 0.96 s (1.69), Osaurus 0.24 s, oMLX 0.04 s (0.08), vMLX 0.004 s. One `lsof` costs 0.068 s. So the old `cold_load_s` was overstated by about 1.0–1.8 s for mlx-lm and OptiQ, about 0.3 s for Osaurus, and about 0.1 s for oMLX and vMLX. |

## Still open

- Re-check any published cold-load ordering where mlx-lm or OptiQ sat within about 1.8 s of another engine. This is a paper audit, not a measurement.
- Adopting the new versions in `engines-tested.json` means a `RECORD=--record` canary run. That needs Jason's yes and another quiet window.
- Jason runs the new DMG install, Stop now, and `sudo rm /etc/sudoers.d/oymlxtest`.
- UAT (`/paul:verify`), then `PHASE-5-SUMMARY.md`.
