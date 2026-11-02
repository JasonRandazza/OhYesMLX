---
description: "v5.0 Phases 2.5 and 3 reconciled: plan vs actual, findings, what carries forward"
type: Summary
about: "OhYesMLX"
---

# Phases 2.5-3 Summary (UNIFY, 2026-11-01)

## Delivered

| Plan | Delivered | Commit |
|---|---|---|
| 025-01 | `ohyesmlx/engines-tested.json` (only version table) and `runtimes._engine_env` (only PATH-prefix definition) | `e7a98ae` |
| 025-02 | `ohyesmlx canary`, `canary.py`, contention gate; first baselines for all five engines | `7a5e843`, `bbbaf57`, `9a6699a` |
| 025-03 | machine-local `lab-paths.json`, detection honours it, `docs/runtimes/lab-copies.md` | `a9b5c46` |
| 03-01 | `catalog.py/.json`, 12 revision-pinned models, `DISK_MARGIN` | `96703ed` |
| 03-02, 03-03 | `recommend.pick` + `exclusion_reason`; `fetch.download/evict` | `8df8a19` |

Tests 733 -> 945. Real checks by the coordinator: canary live on all five engines; OptiQ 0.5.13 lab copy canaried against 0.7.8; Osaurus pin restored byte-exact; real 351 MB download of Qwen3-0.6B-4bit into a scratch HF cache (6 s, sha256 equals blob name, mlx-lm generated a coherent reply, evict removed 28 paths, decoy entry untouched).

## Findings (details: `docs/research/2026-10-30-optiq-0513-vs-078-canary.md`, `2026-10-30-phase3-models.md`)

- OptiQ TTFT 0.24 s (0.5.13) vs 0.17 s (0.7.8), reproduced twice; decode within noise (Decision 136).
- A pinned package is not a pinned build: unpinned `mlx-lm` under OptiQ 0.5.13 gave HTTP 404. T2.5.5 closed 2026-11-02: both lab venvs frozen into committed constraints files that every pip install applies.
- The shipped manifest must be portable: lab paths are machine-local (`lab-paths.json`).
- No MLX MoE at or under 3B exists; "3B" models are 3.08-3.2B; catalog cap is disk size (~2 GB), Decision 137.
- oMLX appends the user's HF cache to its model dirs; AGENTS.md corrected, command unchanged.
- Worker BLOCKED report on 03-02 corrected a wrong coordinator literal (8B-A1B is `tight` on a 16 GiB Mac).

## Deviations

- `canary --record` writes baselines only; adopting a tested version is a separate manifest edit (decided at review).
- 025-03's wizard script (Jason's manual DMG archiving) is not generated yet.
- Phase-end code review for 2.5 and 3: done 2026-11-02, 9 findings fixed (orders `.paul/orders/v5-review-25-3-*`). Kept as-is: `refs/main` is written only when absent (HF itself does not move it for a commit-pinned download).
