---
description: "OhYesMLX — current position and accumulated context"
type: ProjectState
about: "OhYesMLX"
---

# Project State

## Project Reference

See: .paul/PROJECT.md (updated 2026-09-14)

**Core value:** A Mac user can find out whether their serving runtime or their quantization is what's actually costing them speed and memory.
**Current focus:** v1 — Phase 2.1, Coherence gate

## Current Position

Milestone: v1 — Format axis on small models (0.1.0)
Phase: 2.1 of 6 (Coherence gate)
Plan: 1 of 1 in current phase
Status: Applying
Last activity: 2026-09-15 — Phases 1 and 2 complete, 199 tests green. Coherence gate rewiring in flight.

Progress:
- Milestone: [███░░░░░░░] 33%
- Phase: [███████░░░] 70%

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

### Deferred Issues

| Issue | Origin | Effort | Revisit |
|-------|--------|--------|---------|
| LMRE not yet archived to ~/Dev/archive/ | Pre-phase | S | After Phase 4, once nothing more is needed from it |
| Disk audit incomplete — two workers hit the turn cap | Phase 2.1 | S | Low urgency: both hero models fit in 36 GiB without deleting anything |
| LMRE's rubric/ruling design (floors then one ordering metric) not ported | Pre-phase | M | v2, with the accuracy axis |
| No CI | Pre-phase | S | Before the repo gets its first outside contributor |

### Blockers/Concerns

| Blocker | Impact | Resolution Path |
|---------|--------|-----------------|
| Stock mlx-lm executes a 256-expert oQ4 MoE incorrectly — loads and generates at speed, output is token salad | Invalidates any speed number taken without a coherence check | Phase 2.1 gate; Phase 4 settles whether it is runtime-specific |
| 36 GiB free, `/System/Volumes/Data` at 96%; external drive offline | Caps model choice; no bf16 reference possible | Both hero models fit at 33.7 GB. Jason is clearing JANG/LMRE models by hand |

## Boundaries (Active)

- `.paul/STATE.md` is the only project state store. If a second appears, delete it.
- No new dependency without naming what it replaces.
- No governance layer: no plan hashing, no sealed evidence, no action grants, no workspace scaffolding.

## Session Continuity

Last session: 2026-09-15
Stopped at: Phases 1-2 complete and pushed. `coherence.py` landed with 16 tests; its call site in `measure.py` is being rewired by a worker.
Next action: verify and commit the coherence wiring, close #7, then begin Phase 3 (format axis).
Resume context: **Read `.paul/HANDOFF.md` first** — it carries the three findings that redirected the project, the traps that cost time, and machine state.

---
*STATE.md — Updated after every significant action*
*Size target: <100 lines (digest, not archive)*
