---
description: "OhYesMLX — session handoff, 2026-09-24 morning (v3.1 Hardening: Phases 1–3 complete, validation grids run)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-24 morning (v3.1 Hardening, Phases 1–3 complete)

> Read this, then `.paul/STATE.md` (Current Position, Deferred Issues), then `AGENTS.md`.
> STATE wins on conflict. The previous handoff is `.paul/archive/HANDOFF-2026-09-23-evening.md`.

## What happened overnight

All commits are **local only, not pushed.** Review with `git log origin/main..main`.

| commit | what |
|---|---|
| `4279663` | Phase 3a: caveats at the top of the five v3 script papers (Decision 121, review A3); `probe_grid*.py` no longer calls an incoherent HTTP-200 cell `LOADS` (A4/F7); AGENTS.md TTFT definition names the reasoning-channel exception (Decision 119). |
| `7601e62` | Grid runners accept `OUT=`; `scripts/run_harden_validation.sh` re-runs the three published grids unchanged. |
| `17b3791` | **Phase 2:** A5 `reasoning_timed_note` + grid/sweep marker; A7 no cross-runtime ordering or recommendation on `peak_mb`/`cold_load_s`; D1 `e2e_p50/p90/p99_s`; D3 join refuses `unknown…` versions. Luna worker hit its 200-turn cap; the coordinator removed a duplicated D3 check and a duplicated A7 branch, gated E2E percentiles on their own sample count, and red-checked all four items. |
| `4afd162` | Validation writeup; Osaurus relaunch cause in `docs/runtimes/osaurus.md` §1.2; AGENTS.md hazard points to it. |
| `deb6189` | **Phase 3b:** documentation drift (review F): README, `docs/interfaces.md`, `docs/runtimes/{optiq,vmlx}.md`. Worker ran on the DeepSeek route. |
| `9210931` | Two CLI help tests failed under `FORCE_COLOR` (Python 3.14 argparse colours help); they now pin `NO_COLOR`. |

Tests: **543 pass**, with and without `FORCE_COLOR`.

## Validation grids: the headline

Full writeup: `docs/research/2026-09-24-hardening-validation-grids.md`. Data:
`results/harden-2026-09-23/grid-{35b,dense,moe}/` (gitignored). The three grids ran 23:18 → 05:37,
every column exited 0, and one harness sha covers all 15 columns.

- **MoE replicates**, within about 1.5% in every cell, with the same single FAIL (`optiq × osaurus`).
- **Dense replicates**: format orderings are identical in every runtime, and most cells are within 4%.
- **35B format orderings replicate, but levels do not.** mlx-lm, oMLX and vMLX are 8–27% faster than
  the published grid at *identical* versions, and the current code reproduces the published
  figures exactly from the old data, so the shift is in the measurements. OptiQ and Osaurus changed
  version, so those columns cannot be joined with the published ones. The cause is unknown.
  A third 35B replicate is the cheap way to settle it (about 2.3 h on a quiet machine).
- **New:** with A5 labelling on, OptiQ is the only runtime timed on *content* on the Qwen grids.
  The other four are timed on reasoning for 9 of 9 requests, and the old data shows the same
  split. Decode rate stays readable across the row, but a TTFT ordering across the row mixes two
  definitions. **Decision needed:** should the runtime axis refuse TTFT orderings across mixed
  channels, as A7 does for `peak_mb`?
- The 35B mlx-lm column overlapped about 12 minutes of snapshot deletion and process reaping. It
  was kept: it came out faster, with no drift marker. The writeup names it.

## Host changes Jason made (2026-09-23 night)

- Osaurus was removed from `~/.commandcode/mcp.json` and from Login Items. Both relaunched the app with
  `--launched-by-cli`, and the harness refuses every runtime start while that app is alive.
- Google Drive was quit for the run (it held ~100% CPU). **Relaunch it.**
- Time Machine local snapshots were deleted, leaving about 100 GiB free. AGENTS.md now dates the disk figure.

## Phase 4 proposal (needs Jason's yes: each item is a new header pin)

Phase 4 re-runs the v3 script studies through the harness. Four of the five need a run setting
that the harness does not have. AGENTS.md requires approval for each new header pin. The
proposal follows the `--cache-state` pattern exactly:

- a `run` flag, recorded in the header;
- a member of `SWEEP_PINS`, so `sweep --varying <pin>` joins runs that differ only in it;
- **N/A with the reason** on any runtime that cannot be driven into the state. It is never
  measured in a different state.

| study (paper) | proposed pin | values | runtimes that can honour it | notes |
|---|---|---|---|---|
| 03-05 KV-cache quant | `--kv-quant` | `off`, `fp8`, `int4` | per `docs/runtimes/*.md`; paper used OptiQ, vMLX, mlx-lm | Combine with the existing `--prompt-tokens 16384/32768`. Highest value: the paper's decode formula is the most off. |
| 03-06 native MTP | `--mtp-depth` | `off`, `1`, `2`, `3` | vMLX (`--enable-native-mtp`) | One runtime, so it is a sweep and not a grid. Acceptance rate is a runtime self-report and would be recorded, not treated as a measurement. |
| 03-03 expert streaming | `--stream-experts` | `off`, `on` | OptiQ, vMLX FlashMoE | OptiQ is already pinned `off` internally; this would make that pin explicit and sweepable. |
| 03-04 multi-turn | `--turns` | `1`…`10` | all five | The only one that changes the *workload*, not a runtime flag. It could instead be N fixed workloads in `cli.py`, with no pin. **Recommend the workload route** (no new pin). |
| 03-07 speculative draft | — | — | — | **Do not re-run.** Two resident models by design breaks the one-model rule, so it can never be a harness cell. It stays a caveated script study. |

Suggested order: KV-quant → MTP → streaming → multi-turn. Each is one worker order plus one
overnight sweep. Nothing needs a download: every artifact the papers used is on disk.

## Next moves

1. Review and push the six local commits.
2. Decide the Phase 4 pins (table above) and the mixed-channel TTFT question.
3. Queue a third 35B replicate for the next quiet night: `OUT=results/harden-35b-r3 sh scripts/run_grid_35b.sh`.
4. The Luna route trial is still owed. Tonight's Phase 2 worker (Luna) ran out of turns, and its
   partial diff contained two duplicated definitions. That is one data point for the trial.
