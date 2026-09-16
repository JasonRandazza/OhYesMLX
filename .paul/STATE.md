---
description: "OhYesMLX — current position and accumulated context"
type: ProjectState
about: "OhYesMLX"
---

# Project State

## Project Reference

See: .paul/PROJECT.md (updated 2026-09-14)

**Core value:** A Mac user can find out whether their serving runtime or their quantization is what's actually costing them speed and memory.
**Current focus:** v1 — Phase 3, the sparse grid on Qwen3.5-4B

## Current Position

Milestone: v1 — The sparse format x runtime grid on small models (0.1.0)
Phase: 5 of 7 (the joined grid) — built and reviewed. Phases 1, 2, 2.1, 3, 4 complete.
Plan: 1 of 1 in current phase
Status: Applying (Phase 5 code and write-up landed; the warmup decision is the gate on publishing the runtime axis)
Last activity: 2026-09-16 — the five columns joined. `measure.load_run` reads a run back, `report.render_grid` draws the grid, `ohyesmlx grid <dir>...` renders it, 389 tests. Reading the rows for the first time found the runtime-axis ordering to be the warmup budget rather than the runtimes, and an eighth measurement-validity defect: `footprint` is not one quantity across runtimes.

Progress:
- Milestone: [█████████░] 90%
- Phase: [█████████░] 90%

## Loop Position

Current loop state:
```
PLAN ──▶ APPLY ──▶ UNIFY
  ◉        ○        ○     [Planning]
```

## Performance Metrics

**Velocity:**
- Total plans completed: 0
- Average duration: —
- Total execution time: —

## Accumulated Context

### Decisions

| Decision | Phase | Impact |
|----------|-------|--------|
| Two single-variable studies replace LMRE's native diagonal | Pre-phase | Every run declares which axis it varies; nothing varies both. |
| PAUL is the only process spine | Pre-phase | No CONTEXT.md, no ADRs, no handoff docs, no wayfinder. This file is the only state store. |
| Speed + memory only in v1 | Pre-phase | Accuracy work is refused until v1 ships, however tempting. |
| Hero model is `gemma-4-12B-it-qat` | Pre-phase | Zero downloads; 36 GiB free disk forbids more. |
| `--cells a,b,c` is the only cell selector | Pre-phase | Any second mechanism gets deleted on sight. |
| Implementation delegated to `cc-agent` (deepseek-v4.1-flash, max effort) | Pre-phase | Opus reviews every diff and every test run personally; worker prose is not evidence. |
| Hero models are `Qwen3.5-4B` + `LFM2.5-8B-A1B` | Phase 1 | `gemma4_unified` is not shipped by mlx-lm, so that family can carry no stock-mlx control. 33.7 GB for both, all four formats each. |
| Format axis ships before runtime axis | Phase 1 | `mlx-Chronos` already published a runtime-axis protocol; nobody has done the format axis properly. |
| A cell emitting garbage FAILS, however fast | Phase 1 | Stock mlx-lm loaded a 256-expert oQ4 MoE, hit full throughput, and returned token salad with nothing raised. |
| JANG is a runtime+format bundle, not an axis point | Phase 1 | No runtime loads JANG and the other formats both. Own study, after v1. |
| A grid contains both axes as its slices | Phase 3 | Rows (one format, many runtimes) are the runtime axis; columns (one runtime, many formats) are the format axis; the best cell is a recommendation. Attribute within a row or column, recommend across the whole. The two axes were never alternatives to the diagonal — they are readings of one measurement. |
| Three workloads, never averaged | Phase 3 | chat/prefill/decode. One shape measures one corner and prefill-heavy and decode-heavy work can have different winners. A richer suite is v2's. |
| Floors then one ordering metric, never a blended score | Phase 3 | Weighting speed against memory has no objective answer, so a single number would encode an arbitrary trade-off as though it were measured. Full metric card behind every ranking. |
| Osaurus prefill was a cache hit: 8.3x cache, 1.15x version | Phase 3 | Three runs isolated it. Its KV cache cannot be disabled from any command line, only from ~/.osaurus/config, and the settings drift guard already watches both keys. |
| cold_load_s is not one quantity across runtimes | Phase 3 | oMLX loads lazily and hides 3.08-3.85 s in request #1. first_request_s now records it. A cross-runtime load comparison uses the sum. |
| The reasoning channel is the output stream when there is no content | Phase 3 | mlx-lm and vMLX answer entirely in it; all 24 of their grid rows failed before this. |
| Every runtime advertises models it cannot serve | Phase 3 | mlx-lm, oMLX and Osaurus all list a model in /v1/models and then refuse it. oMLX published a 2.15 s cold load for weights it had already failed to load. Readiness is not the port, and not the model list either. |
| Osaurus and vMLX are two independent JANG runtimes, both kept | Phase 3 | JANG cannot be a format-axis row, but JANG-on-Osaurus vs JANG-on-vMLX is the runtime axis with format held constant. Two implementations are what make a single-variable JANG study possible at all. |
| The 256-expert failure is runtime-specific, not format-specific | Phase 4 | oMLX 0.6.4 answers coherently from the same bytes stock mlx-lm turns into salad. The format axis is not built on a corrupting quantizer. |
| Drift annotates, never fails | Phase 3 | A cell still moving is a result, and the row saying the window was too short is the row that must not be dropped. DRIFT_ANNOTATION_PCT=5.0 separates the columns, not every row. |
| Warmup is a per-runtime property, not a universal constant | Phase 3 | mlx-lm drifts +17.0% median across a whole column; oMLX, mlx-optiq, vMLX and Osaurus settle at +2.6/-0.0/+0.5/+1.0%. One warmup budget cannot be right for all five. |
| A server's self-reported tok/s is not a measurement | Phase 4 | oMLX reports 15,286 tok/s from a generation_duration of 0.0. The harness measures; it does not relay. |
| Phase 5 is a join, not a measurement campaign | Phase 5 | The runtime axis was measured in full by Phase 3's five columns and read by nobody. Re-measuring it would have re-run 67 minutes of data already on disk. |
| A grid is assembled from named directories, never a glob | Phase 5 | `results/grid/` holds thirteen run dirs from three sessions; a wildcard would silently join columns that never belonged together. |
| The runtime axis is not publishable until warmup is per-runtime | Phase 5 | mlx-lm is last in 11 of 14 orderings on the published median and 1st/3rd/3rd/4th on the late-window median. The cross-runtime ordering is measuring warmup and calling it speed. The format axis is unaffected — within a column the shortfall lands on every format equally. |
| `peak_mb` and `cold_load_s` carry no runtime-axis ranking | Phase 5 | `footprint` counts different pages per runtime: four columns report within a few percent of their weight bytes, Osaurus roughly half of its. `CROSS_RUNTIME_UNCOMPARABLE` prints the reason above any runtime-axis ordering by them. Format-axis orderings are untouched. |

### Deferred Issues

| Issue | Origin | Effort | Revisit |
|-------|--------|--------|---------|
| LMRE not yet archived to ~/Dev/archive/ | Pre-phase | S | After Phase 4, once nothing more is needed from it |
| Disk audit incomplete — two workers hit the turn cap | Phase 2.1 | S | Low urgency: both hero models fit in 36 GiB without deleting anything |
| ~~LMRE's rubric/ruling design not ported~~ **PULLED FORWARD 2026-09-15** | Pre-phase | — | Floors + one ordering metric now pinned in docs/interfaces.md. The accuracy axis stays in v2; only the honest half moved. |
| No CI | Pre-phase | S | Before the repo gets its first outside contributor |
| Tokenizer-unavailable should make a cell N/A, not 5 transport failures | Phase 4 | S | measure.py's docstring promises visible N/A; behaviour gives FAIL with a server-shaped reason |
| Eight pre-`first_request_workload_id` run dirs cannot be loaded | Phase 5 | S | `load_run` refuses them by line number rather than defaulting the field. A schema migration, only if those columns are ever wanted |
| mlx-optiq reports `"mlx-optiq, version 0.5.6"`, not a bare version | Phase 3 | S | Join guard 4 compares the exact string. Normalise when that guard is next touched |
| `footprint` vs resident on Osaurus is inferred, not probed | Phase 5 | S | The file-backed-pages explanation needs a probe before any memory ranking is published |
| ~~`mlx-lm` 0.31.3 lives only in `/tmp/mlxspike`~~ **RESOLVED 2026-09-15** | Phase 4 | — | Reinstalled at `~/.local/share/ohyesmlx/mlx-lm-0.31.3` with the spike's exact pins (mlx 0.32.2, transformers 5.17.0, tokenizers 0.23.2, numpy 2.5.3). |

### Blockers/Concerns

| Blocker | Impact | Resolution Path |
|---------|--------|-----------------|
| ~~Stock mlx-lm executes a 256-expert oQ4 MoE incorrectly~~ **RESOLVED Phase 4** | Was: invalidates any speed number taken without a coherence check | Runtime-specific, not format-specific. oMLX serves the same bytes coherently. Gate catches it. `docs/research/2026-09-15-phase4-256-expert.md` |
| ~~36 GiB free~~ **RESOLVED 2026-09-15** | Was: caps model choice | 312 GiB free after Jason cleared JANG models and deleted the Time Machine local snapshots that were pinning the blocks. Phase 3 is unconstrained. |

## Boundaries (Active)

- `.paul/STATE.md` is the only project state store. If a second appears, delete it.
- No new dependency without naming what it replaces.
- No governance layer: no plan hashing, no sealed evidence, no action grants, no workspace scaffolding.

## Session Continuity

Last session: 2026-09-16
Stopped at: Phase 5's code, guards and write-up landed in `a92fe11` and `fe371e9`, 389 tests, reviewed and re-verified personally. `docs/research/2026-09-16-phase5-joined-grid.md` is the phase's document.
Next action: the per-runtime warmup budget. It stopped being a nice-to-have when the join showed the runtime-axis ordering flips under it. Then re-run the mlx-lm column (and raise `measured` above 5 while doing so) and re-join.
Resume context: **Read `.paul/HANDOFF.md` first**, then `docs/research/2026-09-16-phase5-joined-grid.md`.

---
*STATE.md — Updated after every significant action*
*Size target: <100 lines (digest, not archive)*
