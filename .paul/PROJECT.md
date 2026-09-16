---
description: "Mac users get honest, single-variable benchmarks of local LLM serving runtimes and quantization formats on Apple Silicon."
type: Project
about: "OhYesMLX"
---

# OhYesMLX

## What This Is

A small command-line benchmarking tool that measures local LLM serving on Apple
Silicon — speed, memory, and on-disk size — across the MLX serving runtimes
(`mlx_lm.server`, Osaurus, oMLX, `optiq serve`) and the specialized quantization
formats built for them (mlx-lm affine, oQ/oQe, OptiQ, JANG). It talks to every
runtime over its OpenAI-compatible HTTP endpoint, samples macOS memory while the
run is in flight, and joins the result into one leaderboard table.

Its defining property is that it varies **one thing at a time**. Published MLX
numbers routinely change the runtime and the quantization together, then credit
the difference to whichever one the author is promoting.

## Core Value

A Mac user can point this at their own machine and find out whether their serving
runtime or their quantization is what's actually costing them speed and memory.

## Current State

| Attribute | Value |
|-----------|-------|
| Type | Application (CLI tool) |
| Version | 0.0.1 |
| Status | Prototype |
| Last Updated | 2026-09-14 |

## Requirements

### Core Features

- Uniform lifecycle for four heterogeneous runtimes (a Swift app, a Python daemon, a CLI) — start, health-check, warm, stop, release the port.
- Streaming SSE measurement over OpenAI-compatible endpoints: TTFT, ITL/TPOT, end-to-end P50/P90/P99, per-request and aggregate throughput, cold-load time.
- macOS memory sampling via `footprint -p <pid>`, with optional `powermetrics` for power and thermal pressure.
- On-disk artifact size including sidecar files.
- One joined `results.jsonl` plus a rendered markdown leaderboard, retaining every raw observation so summaries stay recomputable.

### Validated (Shipped)

- [x] Repository, license, and the stated methodology — 0.0.1

### Active (In Progress)

- [ ] Phase 2.1 — the coherence gate, which every later number depends on.

### Planned (Next)

- [ ] Format axis on `Qwen3.5-4B` and `LFM2.5-8B-A1B` — the headline contribution.
- [ ] The 256-expert question: one cached artifact, two runtimes, coherence as the outcome.
- [ ] Runtime axis, citing `mlx-Chronos` rather than duplicating it.
- [ ] Concurrency, prompt-length, and cold/warm KV-cache sweeps.

### Out of Scope

- **Accuracy / "intelligence" scoring** — deferred to v2 entirely. It is a harder problem than speed and it is what drowned the predecessor project. When it lands it will be `lm-evaluation-harness` over the same endpoints, not a bespoke scorer. The v1 coherence gate is a floor, not an eval: it answers "is this producing language at all", never "is it smart".
- **JANG as a point on either axis** — it loads in no runtime that loads the other formats, so it is a runtime+format bundle rather than a quantization you can isolate. It gets its own labelled study after v1.
- ~~**Any new model download**~~ **Lifted 2026-09-16 for what v1 needs.** The rule existed because free disk was 36 GiB; it is now 238 GiB. 21.9 GB of LFM2.5-8B-A1B was fetched for the MoE format axis. A download still needs a stated phase purpose and a committed fetch script — see `AGENTS.md`.
- **35B model families** — deferred until models move to `/Volumes/Storage`.
- **vMLX/MLX Studio, LM Studio, llama.cpp** as runtimes — v2.
- **A governance layer** — no plan hashing, no sealed evidence bundles, no action grants, no operator policy, no workspace scaffolding. A directory name plus `results.jsonl` is the right amount of provenance for a single-user Mac tool.
- **A second cell-selection mechanism.** `--cells a,b,c` is the only one. Ever.

## Target Users

**Primary:** Mac owners running local LLMs who are choosing between serving runtimes or quantization formats.
- Have 16–128 GB of unified memory and care a lot about what fits.
- Are choosing between Osaurus / oMLX / OptiQ / LM Studio largely on vibes and forum claims.
- Want to know which lever — runtime or quantization — is the one worth pulling.

**Secondary:** The authors of these runtimes and quantization formats, who currently have no neutral third-party numbers to point at.

## Context

**Technical Context:**
This project replaces `~/Dev/archive/local-model-runtime-evaluation-harness` (LMRE) —
334 commits, 21.8k lines of source, 774 passing tests, and zero published benchmark
numbers. Roughly 4,000 of those lines did the measurement and 16,000 governed
permission to measure. Its SSE transport, its runtime start-command flag pins, its
model-ID alias registry, and its oMLX per-run catalog are ported here; nothing else is.

Three of the four runtimes are already installed locally: Osaurus 0.25.3, oMLX, and
mlx-optiq 0.5.6. `mlx_lm.server` — the control — needs a fresh venv.

**Ecosystem Context:**
The vMLX/MLX Studio README claims JANG 2-bit beats MLX 4-bit at 74% vs 26.5% MMLU.
26.5% on MMLU is chance level, which means that baseline is almost certainly broken.
Testing that claim fairly is the sharpest single reason this project should exist.

## Constraints

### Technical Constraints

- ~~**36 GiB free disk.**~~ **Resolved 2026-09-15**: 312 GiB after Time Machine local snapshots were cleared; 238 GiB free as of 2026-09-16 after the MoE artifacts. A bf16 reference (~70 GB at 35B) is now physically possible, and has not been attempted.
- **M2 Max in a laptop chassis throttles** under sustained inference. Cell order must be interleaved, cooldowns inserted, and thermal drift recorded — otherwise drift aliases perfectly onto runtime identity.
- **`ps` RSS is wrong for MLX.** Metal buffers, mmap'd weights, and wired GPU memory account inconsistently. `footprint` is the primary number.
- **The matrix is ragged.** JANG cannot be loaded by stock mlx-lm; GGUF cannot be loaded by any MLX runtime. A full cross-product does not exist.
- **Runtimes ship different sampler defaults** (`top_p`, `repetition_penalty`). Everything must be pinned explicitly or the comparison is meaningless.

### Business Constraints

- Anthropic plan tokens are scarce. Implementation is delegated to Command Code on `deepseek/deepseek-v4.1-flash`; Opus 5 orchestrates and reviews.
- Public repository from commit one. Anything published has to survive being wrong in front of the people who wrote these runtimes.

## Key Decisions

| Decision | Rationale | Date | Status |
|----------|-----------|------|--------|
| Two single-variable studies, not a diagonal | LMRE's native diagonal correctly spotted that quant and runtime co-vary, then drew the wrong conclusion — a diagonal can never attribute a difference to either axis. | 2026-09-14 | Active |
| PAUL is the only process spine | LMRE carried three dev methodologies at once. `.paul/STATE.md` is the single state store; Matt Pocock skills are tools called inside the loop. | 2026-09-14 | Active |
| Speed + memory only in v1 | Accuracy is a separate, harder problem and is what drowned the predecessor. | 2026-09-14 | Active |
| Hero model is `gemma-4-12B-it-qat`, not a 35B | All three format variants are already on disk, iteration takes minutes not hours, and 36 GiB free forbids anything larger. | 2026-09-14 | **Superseded 2026-09-15** |
| Hero models are `Qwen3.5-4B` (dense) and `LFM2.5-8B-A1B` (MoE) | `gemma4_unified` is not shipped by mlx-lm 0.31.3, so that family can carry no stock-mlx control. These two are the smallest pair with all four formats published, 33.7 GB combined. | 2026-09-15 | Active |
| Format axis ships before runtime axis | Prior-art research: `mlx-Chronos` already publishes a runtime-axis protocol, while no published format comparison holds the runtime constant. The unoccupied ground is the format axis. | 2026-09-15 | Active |
| A cell emitting incoherent output FAILS, however fast | Stock mlx-lm loaded a 256-expert oQ4 MoE in 4s, returned HTTP 200 at full throughput, and produced mixed-script token salad with nothing raised. Speed without a coherence floor is worse than no number. | 2026-09-15 | Active |
| The 256-expert question is its own single-format two-runtime study | All four formats of a 256-expert model would need ~52 GiB, which this machine does not have. Two runtimes over one cached artifact answers it with zero downloads. | 2026-09-15 | Active |
| `--cells a,b,c` is the only cell selector | LMRE built six overlapping mechanisms across ~3,700 lines for this exact job. | 2026-09-14 | Active |
| Build on GuideLLM / lm-eval rather than reimplement | Only three jobs are genuinely ours: runtime lifecycle, macOS memory sampling, and the result join. | 2026-09-14 | Active |

## Success Metrics

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| Decode tok/s reported as a real number | 100% of passing cells | — | Not started |
| Cells passing the coherence gate before any number is reported | 100% | — | Phase 2.1 |
| Same-cell rerun variance | within 5% | — | Not started |
| Ports released after a run (1337/8080/8081/8100) | 100% | — | Not started |
| Total source size | under ~1,000 lines | 0 | On track |
| Published leaderboard rows | 4 (Study A) | 0 | Not started |

## Tech Stack / Tools

| Layer | Technology | Notes |
|-------|------------|-------|
| Language | Python 3.11+ | Matches every runtime's own ecosystem. |
| HTTP/SSE | `http.client` (stdlib) | Ported from LMRE. Zero dependencies, and it already handles chunked encoding and OptiQ's slow keepalives. |
| Memory sampling | `footprint`, `vmmap`, `powermetrics` | All at `/usr/bin/`. `powermetrics` needs sudo and degrades gracefully without it. |
| Load generation (later) | GuideLLM | For the concurrency sweeps. Purpose-built; percentile machinery is tedious to get right. |
| Accuracy (v2) | lm-evaluation-harness | `local-chat-completions` against the same endpoints. |
| Process | PAUL 1.4.0 | `PLAN → APPLY → UNIFY`. |
| Delegation | Command Code (`cc-agent`) on `deepseek/deepseek-v4.1-flash` | Orchestrated and reviewed by Claude Opus 5. |

## Links

| Resource | URL |
|----------|-----|
| Repository | https://github.com/JasonRandazza/OhYesMLX |
| Predecessor (archived) | https://github.com/JasonRandazza/local-model-runtime-evaluation-harness |

---
*PROJECT.md — Updated when requirements or context change*
*Last updated: 2026-09-15*
