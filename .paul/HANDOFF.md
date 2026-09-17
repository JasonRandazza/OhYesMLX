---
description: "OhYesMLX — session handoff, 2026-09-17 (afternoon, Candidates 3 & 4 closed)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-17, afternoon

> **This file is short by design and is rewritten each session, never appended to.** It holds
> *state*: where things stand now and what is next. Durable rules live in `AGENTS.md`;
> decisions live in `.paul/STATE.md`; findings live in `docs/research/`. Previous handoffs are
> in `.paul/archive/` and are not required reading. If this file starts growing per-session
> headings, it has become a log — rewrite it.

Read this, then `.paul/STATE.md`, then `AGENTS.md`.

## Where the project is

**v1 is closed, and both v2 candidate closeouts (Candidates 3 and 4) are complete and published.**
All commits are pushed to `origin/main` (latest HEAD `5773b14`).
CI (`tests.yml`) remains green — verify with `gh run list --workflow=tests.yml`.
STATE reads 100% / UNIFY.

- **495 tests pass** (observed by coordinator via `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q`).
- **Nothing is in flight.** Check before starting:
  `lsof -i :1337 -i :8080 -i :8081 -i :8100 -i :8000`,
  `pgrep -fl "^/Applications/osaurus.app"`, `pgrep -fl "cc-agent|ohyesmlx.cli run|run_grid|probe_"`.
- `osaurus mcp` is Jason's and must stay up. **Never sweep by the name `osaurus`.**
- Osaurus settings on host are byte-exact to Jason's baseline (`cache.prefix.enabled: true`, `cache.blockDisk.enabled: true`, `modelIdleResidencyPolicy.seconds: 30`), verified with `cmp`.

## What this session did

1. **Grid TTFT Drift Fix:** Render sweep and grid marker fix committed and pushed (`38cb8bb`).
2. **README Status:** Updated with research links (`4c69c7f`, `7ec6ff0`, `5773b14`).
3. **Deep Wiki Page:** Authoritative project page created at `/Users/jrazz/Documents/ObsidianNotes/10 Wiki/Projects/OhYesMLX/OhYesMLX.md` conforming to Agent Onboarding Contract and Metadata Schema. Vault validated clean.
4. **Stale Osaurus Backups Removed:** `~/.osaurus/config/server-runtime.json.probe-orig` and `.sweep-prompt-orig` deleted.
5. **Candidate 3 (Non-hybrid KV Cache Sweep):**
   - Fetched `brainworkup/Llama-3.1-8B-oQ4` via `scripts/fetch_cache_nonhybrid.sh` and attached instruct chat template.
   - Executed full 10-cell sweep across all 5 runtimes via `scripts/run_sweep_cache_nonhybrid.sh`.
   - Result: All 5 runtimes hit on trimmable `KVCache` (25x–142x speedup; mlx-lm 0.136s, optiq 0.138s, vmlx 0.419s, omlx 0.529s, osaurus 0.697s).
   - Documented in `docs/research/2026-09-17-cache-state-split-nonhybrid.md`.
6. **Candidate 4 (vMLX 32k Prefill Resolution):**
   - Audited vMLX source (`mllm_batch_generator.py`) and PyPI release `1.6.61`.
   - Identified that `VMLX_ALLOW_HYBRID_CHUNKED_PREFILL=1` unlocks chunked hybrid prefill, overriding the one-shot default that bypassed `--prefill-step-size`.
   - Verified live at 32k on Qwen3.5-4B-oQ4: prefilled in 16 chunks of 2,048 tokens, 4.10 GB active memory, TTFT 88.76s, 0 Metal errors.
   - Documented in `docs/research/2026-09-17-vmlx-32k-chunked-prefill.md` and updated `docs/runtimes/vmlx.md`.

## Research Documents Index

| Topic | Document |
|---|---|
| Dense format axis | `docs/research/2026-09-16-phase5-joined-grid.md` |
| MoE format axis | `docs/research/2026-09-16-moe-format-axis.md` |
| Memory footprint accounting across runtimes | `docs/research/2026-09-16-footprint-is-not-one-quantity.md` |
| Concurrency & batching (N=8) | `docs/research/2026-09-16-concurrency-omlx.md` |
| Prompt-length sweep (128 to 32k) | `docs/research/2026-09-16-prompt-length-sweep.md` |
| Cold vs warm KV cache state (hybrid baseline) | `docs/research/2026-09-17-cache-state-split.md` |
| Cold vs warm KV cache state (non-hybrid control) | `docs/research/2026-09-17-cache-state-split-nonhybrid.md` |
| vMLX 32k watchdog diagnosis and resolution | `docs/research/2026-09-17-vmlx-32k-chunked-prefill.md` |
| v2 options roadmap | `.paul/v2-options-note.md` |

## Next Steps

Await Jason's review and direction on subsequent v2 phases:
1. JANG study (Osaurus vs vMLX, runtime axis with format held constant).
2. Accuracy benchmarking (designing methodology without unpinned sampling noise).
