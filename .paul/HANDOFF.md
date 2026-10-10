---
description: "OhYesMLX — session handoff, 2026-10-10 (v4.0: MTPLX runtime class landed)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-10-10

> Read this, then `.paul/STATE.md` (Decision 132), then `AGENTS.md`. STATE wins on conflict.
> Previous handoff: `.paul/archive/2026-09-25-handoff-evening-phase4-closed.md`.

## Where things stand

MTPLX is the **sixth runtime** (v4.0, Decision 132). The class, port 8200, the depth-pin receipt
gate and the `mtplx_stats` raw field are committed and pushed (`bcb94e8`; 673 tests). **No MTPLX
cell has been measured.** Also unfinished from before: the v3.1 → 0.3.1 bump, and Osaurus 0.25.18
has no measured cell beyond the thinking-on cap-8192 run (`results/accuracy-thinkon-cap8192/`).

## What MTPLX is here

A runtime-axis column on artifacts we already own. Never put a `Youssofal/*` pack in a cross-runtime
column; the pack at `~/.mtplx/models/Youssofal--Qwen3.5-4B-MTPLX-Optimized-Speed` is a **format
axis cell inside MTPLX** (OptiQ-4bit vs that pack, runtime fixed). No special lane (Jason, 2026-10-10).
Facts and artifact table: `docs/runtimes/mtplx.md`. Probes: `docs/research/2026-10-09-mtplx-load-probes.md`.
Plan: `docs/research/2026-10-06-mtplx-integration-plan.md`.

## Proposed cells (each needs Jason's yes before launch; nothing else on the machine)

1. **A — runtime axis:** `mlx-community/Qwen3.5-4B-OptiQ-4bit`, runtimes `optiq` and `mtplx`,
   `--mtp-depth off,1,2,3`, cache off (mtplx refuses `off`; use the absent pin, which passes the SSD tier off — decide
   whether that is honest for a cross-runtime row before launching), temp 0, seed recorded per row.
2. **B — depth ladder inside MTPLX** on the same bundle.
3. **F — format axis inside MTPLX:** OptiQ-4bit vs the MTPLX pack, depth 1 and AR.
4. **D — AR "vs oMLX":** only if a probe shows oMLX loads the OptiQ 4B bundle. Unprobed.
5. Closed: vMLX-vs-MTPLX on JANG_4S (does not load).

## Before the first cell

- Run the sampler survey into AGENTS.md (Decision 131 pattern): temperature honoured, penalties 0.0,
  no `generation_config` penalty path; per artifact record the thinking default and resolved profile.
- First live cell is the real test of flags and readiness; read the receipt, not the exit code.
- Decide what `cache_state` row to publish given `off` is refused (RAM session bank). Probing whether a zero
  `MTPLX_SESSION_BANK_MAX_BYTES` really disables warm restore would unblock it.

## Hazards learned this session

- cc-agent workers touched `BLOCKED.md` and STATE.md outside their list; check `git status` after each.
- Two research agents died on a transient API error; a dispatch that logs "Unable to connect" is a
  retry, not a result.
- Coordinator-run probes use `scripts/probe_mtplx_load.py`; not a harness surface.
