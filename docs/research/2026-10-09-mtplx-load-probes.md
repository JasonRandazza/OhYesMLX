# MTPLX load probes (2026-10-09)

Phase 1 of `2026-10-06-mtplx-integration-plan.md`. Observation only; no harness code changed, no
measured cell. MTPLX 2.12.2 from `~/.mtplx/bin/mtplx` (the app's own runtime-venv; no separate
install was needed). Nothing else running, one model resident at a time, port 8200, every server
stopped and the port confirmed free. Script: `scripts/probe_mtplx_load.py` (one start, one
128-token streamed request at temperature 0, stop).

Command shape: `mtplx serve --model <hf-id> --host 127.0.0.1 --port 8200 --model-id probe
--no-stats-footer --ssd-session-cache off --depth 1 --generation-mode mtp`.

| Artifact | Result | Evidence in the response |
|---|---|---|
| `mlx-community/Qwen3.5-4B-OptiQ-4bit` | **attaches and drafts** | `mtplx_stats`: mode `mtpk`, `draft_head_installed` true, drafted 67, accepted 60, rejected 7 (89.6%), `mtp_depth` 1, decode 89.5 tok/s, load 6 s |
| `mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit` | **attaches and drafts** | mode `mtpk`, drafted 67, accepted 61, rejected 6 (91.0%), depth 1, decode 78.7 tok/s, load 16 s |
| `uingei/Qwen3.5-4B-oQ4e` | **silent AR degrade**, as predicted | HTTP 200, coherent text, mode `ar`, `draft_head_installed` false, drafted 0; only the log line `mtp_heads not found -> mtp_off: serving autoregressive` says so |
| `JANGQ-AI/Qwen3.5-4B-JANG_4S` | **does not load** | `ValueError: Expected shape (248320, 640) but received shape (248320, 320) for parameter language_model.model.embed_tokens.weight`; exit 1 at the model-load step, before any port bind |

## What this settles

- The prediction from source and tensor bytes held on all four artifacts.
- The "head actually drafted" receipt is the final SSE chunk's `mtplx_stats`: `drafted_tokens`,
  `accepted_drafts`, `rejected_drafts`, `mtp_depth`, `mode`, `draft_head_installed`. Acceptance is
  computed from those; a 0%-acceptance head would show there. Both OptiQ sidecars accept ~90%.
- The silent-degrade case returns a perfectly healthy response. Only `mode`/`drafted_tokens` (or
  the log) separate it from an MTP cell. The runtime must refuse a depth pin unless the receipt
  shows drafting.
- **JANG_4S does not load under MTPLX**: its quantisation layout (embed width 320 packed vs the
  640 mlx-lm expects) is outside MTPLX's loader. Cell set C (vMLX vs MTPLX on one embedded head)
  is closed; that is a finding about MTPLX's artifact contract, not a reason to substitute an
  MTPLX pack.
- Thinking is on by default for Qwen3.5/3.6: text arrives in `reasoning_content` (127 of 128
  tokens), `content` empty at 128 tokens. TTFT timing therefore falls under Decision 119
  ("timed on reasoning channel").
- Sampler resolved by the profile at default: temperature 0.6, top_p 0.95, top_k 20; a request
  `temperature: 0` was honoured (`draft_sampler_resolved_temperature` 0.0). Penalties not set.
- A seed is generated server-side when none is sent (log shows one); at temperature 0 it is
  inert. The harness sends none.
- `/v1/models` lists exactly one entry, the `--model-id` value.

## Still open

- RAM session-bank has no serve flag (budget env-only, 41 GB auto on this machine); whether a
  zero budget honestly disables warm restore gates a `cache_state=off` cell.
- Whether oMLX loads `Qwen3.5-4B-OptiQ-4bit` (gates the AR "vs oMLX" column).
- Mismatched `model` string in a request; not probed.
- The depth ladder at 2 and 3 and the AR (`--no-mtp`) control were not run here; they are cells.
