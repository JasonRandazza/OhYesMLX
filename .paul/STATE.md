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
Phase: 3 of 6 (the sparse grid) — COMPLETE. Full grid re-run 60/60 PASS.
Plan: 1 of 1 in current phase
Status: Applying (Phase 3 closed; Phase 5 report is the next build)
Last activity: 2026-09-15 evening — the grid re-ran clean. 60/60 cells PASS across 5 columns, 353 tests. The format ordering replicated in every runtime that can read it. A seventh measurement-validity defect found and fixed: measured_drift was recorded and unread.

Progress:
- Milestone: [████████░░] 80%
- Phase: [██████████] 100%

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

### Deferred Issues

| Issue | Origin | Effort | Revisit |
|-------|--------|--------|---------|
| LMRE not yet archived to ~/Dev/archive/ | Pre-phase | S | After Phase 4, once nothing more is needed from it |
| Disk audit incomplete — two workers hit the turn cap | Phase 2.1 | S | Low urgency: both hero models fit in 36 GiB without deleting anything |
| ~~LMRE's rubric/ruling design not ported~~ **PULLED FORWARD 2026-09-15** | Pre-phase | — | Floors + one ordering metric now pinned in docs/interfaces.md. The accuracy axis stays in v2; only the honest half moved. |
| No CI | Pre-phase | S | Before the repo gets its first outside contributor |
| Tokenizer-unavailable should make a cell N/A, not 5 transport failures | Phase 4 | S | measure.py's docstring promises visible N/A; behaviour gives FAIL with a server-shaped reason |
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

Last session: 2026-09-15 (evening)
Stopped at: Phase 3 closed. Tasks #3, #4 and #6 all done and verified live; the deferred-load threshold was re-attributed. Four commits unpushed.
Next action: push the four commits, then Phase 5 — the report that joins the five run directories under results/grid/. Two open questions carried forward, both recorded in HANDOFF.md: the per-runtime warmup budget, and the column-entry drift effect.
Resume context: **Read `.paul/HANDOFF.md` first** — it carries the grid result, the drift finding, and machine state.

---
*STATE.md — Updated after every significant action*
*Size target: <100 lines (digest, not archive)*
