# MTPLX — capability and configuration reference (2.12.2)

Read this before claiming MTPLX cannot do something. It is an index with the verified facts; the
long form is in three research papers, each claim there labelled VERIFIED / CLAIMED / INFERRED.

- Architecture, MTP mechanism, scheduler, caches, sampler defaults, release health:
  `docs/research/2026-10-06-mtplx-architecture.md`
- CLI, files, env vars, HTTP API, ports, hook-by-hook mapping to `Runtime`:
  `docs/research/2026-10-06-mtplx-surface.md`
- Models, formats, published speed claims (read, not reproduced), lineage, which axis a cell varies:
  `docs/research/2026-10-06-mtplx-landscape.md`
- What a real start, request and stop showed: `docs/research/2026-10-09-mtplx-load-probes.md`
- Plan and cell sets: `docs/research/2026-10-06-mtplx-integration-plan.md`

## Version of record

`~/.mtplx/bin/mtplx --version` → `mtplx 2.12.2` (the app's own runtime-venv; the harness does not
install it). Source read at `youssofal/MTPLX@9882703`. Every row records the version; a new build
joins nothing earlier.

## Harness facts (observed 2026-10-09)

| Item | Value |
|---|---|
| Start | `mtplx serve --model <dir> --host 127.0.0.1 --port 8200 --model-id <name> --no-stats-footer --ssd-session-cache off` |
| Port | 8200 (own default is 8000, vMLX's) |
| Readiness | `/health` `ok` and one `/v1/models` entry equal to `--model-id`; a failed load exits before the port binds |
| Receipt | final SSE chunk `mtplx_stats`: `mode`, `draft_head_installed`, `drafted_tokens`, `accepted_drafts`, `mtp_depth` |
| Depth pin | off: `--no-mtp --generation-mode ar`; N: `--depth N --generation-mode mtp` (family max 3) |
| Seed | none sent; greedy-inert at temperature 0 |
| Thinking | on by default for Qwen3.5/3.6; text arrives in `reasoning_content` (Decision 119 timing label) |
| Sampler | profile resolves 0.6 / 0.95 / 20 by default; the request's `temperature: 0` is honoured; no penalty taken from the bundle |
| cache_state | `on` = SSD tier on, directory under the run scratch; `off` **refused** (RAM session bank has no flag) |
| kv_quant | affine values refused: MTPLX q8/q4 is a different codec |
| Scheduler | `serial` by default; concurrency moves nothing |

## Artifacts

| Artifact | Behaviour |
|---|---|
| `mlx-community/Qwen3.5-4B-OptiQ-4bit`, `...Qwen3.6-35B-A3B-OptiQ-4bit` | attach and draft (~90% accepted at depth 1) |
| `Youssofal--Qwen3.5-4B-MTPLX-Optimized-Speed` (`~/.mtplx/models`) | attaches and drafts (60/67); `mtplx_runtime.json` present, contract verified. Format-axis cell inside MTPLX only |
| `uingei/Qwen3.5-4B-oQ4e`, `Jundot/Qwen3.6-35B-A3B-oQ4` | declare MTP, ship none: serve AR silently; refused for a depth pin by the receipt gate |
| `RepublicOfKorokke/Qwen3.5-4B-oQ4` | predicted to refuse at load (no index); unprobed |
| `JANGQ-AI/Qwen3.5-4B-JANG_4S` | does not load (`embed_tokens` shape 320 vs 640) |
| LFM2.5-8B-A1B (all five) | no MTP head exists; AR-only, never an MTP cell |

## Open

RAM session-bank off switch; whether oMLX loads the OptiQ 4B bundle (gates a plain-decode
"vs oMLX" column); a request naming a mismatched `model`; the depth-2/3 ladder and AR control
(cells, not probes). The Youssofal pack's 4-bit affine group-64 quant against OptiQ's mixed
recipe is the format variable; the MTP head storage (bf16 vs quantized sidecar) travels with it
and is part of that variable, not separable.
