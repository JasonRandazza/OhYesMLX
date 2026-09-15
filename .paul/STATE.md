---
description: "OhYesMLX — current position and accumulated context"
type: ProjectState
about: "OhYesMLX"
---

# Project State

## Project Reference

See: .paul/PROJECT.md (updated 2026-09-14)

**Core value:** A Mac user can find out whether their serving runtime or their quantization is what's actually costing them speed and memory.
**Current focus:** v1 — Phase 1, Portability spike

## Current Position

Milestone: v1 — Speed and memory, one model (0.1.0)
Phase: 1 of 5 (Portability spike)
Plan: 0 of 1 in current phase
Status: Ready to plan
Last activity: 2026-09-14 — Repo created and pushed; PAUL initialized from the approved restart plan.

Progress:
- Milestone: [░░░░░░░░░░] 0%
- Phase: [░░░░░░░░░░] 0%

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
| Implementation delegated to `cc-agent` (deepseek-v4.1-flash) | Pre-phase | Opus reviews every diff and every test run personally; worker prose is not evidence. |

### Deferred Issues

| Issue | Origin | Effort | Revisit |
|-------|--------|--------|---------|
| LMRE not yet archived to ~/Dev/archive/ | Pre-phase | S | After Phase 2 ports the salvage files out of it |
| LMRE's rubric/ruling design (floors then one ordering metric) not ported | Pre-phase | M | v2, with the accuracy axis |
| No CI | Pre-phase | S | Before the repo gets its first outside contributor |

### Blockers/Concerns

| Blocker | Impact | Resolution Path |
|---------|--------|-----------------|
| oQ portability to stock mlx-lm is an unverified research claim | Study A's whole design rests on it | Phase 1 is exactly this spike; fallback is an `mlx-community/*-4bit` artifact |
| 36 GiB free disk, `/System/Volumes/Data` at 96% | Caps model choice; no bf16 reference possible | v1 downloads nothing. Move models to `/Volumes/Storage` (931 GiB free) before v2 |

## Boundaries (Active)

- `.paul/STATE.md` is the only project state store. If a second appears, delete it.
- No new dependency without naming what it replaces.
- No governance layer: no plan hashing, no sealed evidence, no action grants, no workspace scaffolding.

## Session Continuity

Last session: 2026-09-14
Stopped at: Repo initialized, pushed to github.com/JasonRandazza/OhYesMLX; PAUL installed and populated.
Next action: `/paul:plan` for Phase 1 (Portability spike).
Resume context: The approved restart plan lives at `~/.claude/plans/twinkling-hopping-crab.md`. Salvage sources are in `~/Dev/active/local-model-runtime-evaluation-harness` (not yet archived).

---
*STATE.md — Updated after every significant action*
*Size target: <100 lines (digest, not archive)*
