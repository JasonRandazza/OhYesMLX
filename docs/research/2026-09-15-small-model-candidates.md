# Small-model candidates for the format axis: dense and MoE proof-of-concept models

**Date:** 2026-09-15
**Role:** research pass (documentation only — no code changed, nothing downloaded, no server started)

The format axis holds the serving runtime constant at oMLX and varies the quantization format
across four cells: **stock mlx 4-bit**, **oQ4**, **oQ4e**, and **OptiQ-4bit**. This note asks
whether a *small* model exists for which all four artifacts are published, so that the entire
matrix can sit on disk at once. It answers four questions against primary sources, and it treats
the MoE question (Q2) as the load-bearing one.

**Evidence rules.** Every claim carries the source URL, the HF API query, or the local path that
was checked. Sizes are the sum of file byte-sizes reported by
`https://huggingface.co/api/models/<repo>?blobs=true`, expressed in decimal GB (bytes ÷ 10⁹);
`du` on disk will differ by block size and by the `blobs/` symlink layout. Anything not directly
verified is marked **UNVERIFIED** and is not inferred. Repository existence, `model_type`, layer
count, expert count, and file sizes were all read from the API on 2026-09-15.

**Budget.** The task states 36 GiB free. `df -h /Users/jrazz` on this machine reports
`35Gi` avail on `/dev/disk3s5` (869 Gi used of 926 Gi). Both figures are used below; 36 GiB is
treated as the ceiling and the ~35 GiB df reading is treated as the practical one.

**Format semantics, pinned from the local tree.** `oQ4e` is not a separate bit width — it is oQ4
with imatrix-weighted quantization. From
`/Applications/oMLX.app/Contents/Resources/omlx/oq.py`:
`OQ_LEVELS = {2, 2.5, 2.7, 3, 3.5, 4, 5, 6, 8}` (line 44), the repo suffix is built as
`suffix = f"-oQ{level_str}{'e' if enhanced else ''}"` (line 1340), and the docstring for the
`enhanced` parameter reads "Enable oQe imatrix-weighted quantization" (line 5730). So oQ4 vs oQ4e
is a *calibration* difference at the same nominal level, which is exactly the kind of distinction
the format axis exists to measure.

---

## Q1 — Small dense candidates (3–5 B)

### How candidates were found

Org inventories were enumerated whole:
`?author=Jundot&limit=1000` (50 repos), `?author=JANGQ-AI&limit=1000` (80 repos),
`?author=mlx-community&search=<family>` (per-family paging), plus whole-HF searches
`?search=oQ4e` and `?search=oQ4` to catch third-party oQ publishers, and
`?author=mlx-community&search=OptiQ-4bit` (77 repos).

The four formats do **not** have a single publisher each. In practice:

| Format | Typical publisher |
|---|---|
| stock mlx 4-bit | `mlx-community` (and the base org, e.g. `LiquidAI`) |
| OptiQ-4bit | `mlx-community` only — 77 repos total, all under `mlx-community` |
| oQ4 / oQ4e | third parties: `Jundot`, `gcoli`, `stamsam`, `brainworkup`, `RepublicOfKorokke`, `uingei`, `beaupi`, `Regis-RCR`, `TheWirelessPhoenix`, … |
| JANG / JANGTQ | `JANGQ-AI` (80 repos) and `OsaurusAI` |

### Ranked by how many of the four formats exist

| Rank | Base model | Params | Formats found | Verdict |
|---|---|---|---|---|
| 1 | **Qwen3.5-4B** | ~4 B dense | **4 / 4** + JANG | fully usable |
| 2 | **gemma-4-E4B-it** | ~4 B effective | **4 / 4** + JANG | fully usable |
| 3 | **gemma-4-E2B-it** | ~2 B effective | 4 / 4 (oQ4 UNVERIFIED) + JANG | usable, but below the 3–5 B ask |
| 4 | **LFM2.5-2.6B** | 2.6 B dense | 4 / 4 | usable, but below the 3–5 B ask |
| 5 | **MiniCPM5-2B** | ~2 B dense | 3 / 4 (stock 4-bit UNVERIFIED) | below range |
| 6 | **Fara1.5-4B** | 4 B dense | 2 / 4 (stock + OptiQ) | too few |
| 7 | **Nanbeige4.2-3B** | 3 B dense | 2 / 4 (stock + OptiQ) | **disqualified on architecture** |
| 8 | **Spark-X2.5-4B** | 4 B dense | 2 / 4 (OptiQ + JANG) | **disqualified on architecture** |
| 9 | **NVIDIA-Nemotron-3-Nano-4B** | 4 B dense hybrid | 2 / 4 (OptiQ + oQ4) | too few |
| 10 | **SmolLM3-3B** | 3 B dense | 2 / 4 (stock + oQ4) | too few |
| 11 | **Phi-4-mini-instruct** | 3.8 B dense | 2 / 4 (stock + oQ4e) | too few |
| 12 | **Ministral-3-3B** | 3 B dense | 2 / 4 (stock + oQ4) | too few |
| 13 | **DeepSeek-R1-Distill-Qwen-7B** | 7 B dense | 2 / 4 (stock + oQ4e) | out of range, too few |
| 14 | **Llama-3.2-3B-Instruct** | 3 B dense | **1 / 4** (stock only) | useless to us |
| 15 | **VibeThinker-3B** | 3 B dense | **1 / 4** (OptiQ only) | useless to us |
| 16 | **mini-coder-4b** | 4 B dense | **1 / 4** (OptiQ only) | useless to us |
| 17 | **DeepSeek-R1-Distill-Qwen-1.5B** | 1.5 B dense | **1 / 4** (stock only) | useless to us |

A candidate with only one format is useless to us; ranks 14–17 are listed precisely so that they
can be struck from the shortlist. Note that three of the seven "candidate families" named in the
task (Llama 3.2 3B, SmolLM3, Phi-4-mini) are **single- or dual-format models with no OptiQ and no
JANG artifact** — the OptiQ line starts at much newer model families.

### Rank 1 — Qwen3.5-4B (dense, 4/4)

32 layers, hidden 2560, 16 attention heads, vocab 248 320. Base config:
`https://huggingface.co/Qwen/Qwen3.5-4B/raw/main/config.json`.

| Format | Repo id | Size (GB) |
|---|---|---|
| stock mlx 4-bit | `mlx-community/Qwen3.5-4B-4bit` | 3.06 |
| oQ4 | `RepublicOfKorokke/Qwen3.5-4B-oQ4` | 3.16 |
| oQ4e | `uingei/Qwen3.5-4B-oQ4e` | 3.17 |
| OptiQ-4bit | `mlx-community/Qwen3.5-4B-OptiQ-4bit` | 4.04 |
| *(JANG_4S, bonus)* | `JANGQ-AI/Qwen3.5-4B-JANG_4S` | 3.21 |

**Four-format total: 13.43 GB (12.51 GiB).** With JANG: 16.64 GB (15.50 GiB).

Other oQ4e artifacts exist and are interchangeable as cells:
`craquehouse/Qwen3.5-4B-oQ4e-fp16-text-only` (2.53 GB, text-only),
`scottlowry/Qwen3.5-4B-oQ4e-mtp` (3.29 GB, ships `oq_imatrix_report.json`),
`TheWirelessPhoenix/Qwen3.5-4B-oQ4e-fp16-mtp` (2.62 GB).
Other oQ4: `RepublicOfKorokke/Qwen3.5-4B-oQ4-fp16` (3.17 GB), `AtBeginDocument/Qwen3.5-4B-oQ4`.

### Rank 2 — gemma-4-E4B-it (dense, 4/4)

42 layers, hidden 2560, 8 attention heads, vocab 262 144. Base config:
`https://huggingface.co/google/gemma-4-E4B-it/raw/main/config.json`.
"E4B" is an *effective*-parameter figure; the checkpoint carries the full Gemma 4 multimodal
config (`architectures: ["Gemma4ForConditionalGeneration"]`), and the MLX artifacts are text-only,
with vision weights stripped.

| Format | Repo id | Size (GB) |
|---|---|---|
| stock mlx 4-bit | `mlx-community/gemma-4-e4b-it-4bit` | 5.18 |
| oQ4 | `beaupi/gemma-4-E4B-it-oQ4` | 4.79 |
| oQ4e | `Jundot/gemma-4-E4B-it-oQ4e-mtp` | 5.54 |
| OptiQ-4bit | `mlx-community/gemma-4-e4b-it-OptiQ-4bit` | 7.52 |
| *(JANG_4M, bonus)* | `JANGQ-AI/gemma-4-E4B-it-qat-JANG_4M` | 10.82 |

**Four-format total: 23.03 GB (21.45 GiB).** With JANG: 33.85 GB (31.53 GiB).

Interchangeable oQ4 artifacts: `Regis-RCR/gemma-4-E4B-it-oQ4` (4.79 GB), `tevino/gemma-4-E4B-it-oQ4`,
`Xartorx/gemma-4-E4B-it-oQ4`, `mlx-community/unsloth-gemma-4-E4B-it-qat-oQ4` (5.38 GB, qat base).
Also existing: a non-qat stock `mlx-community/gemma-4-e4b-4bit` (5.25 GB).

**Caveat that matters for the axis:** the JANG artifact
(`JANGQ-AI/gemma-4-E4B-it-qat-JANG_4M`, 10.82 GB) and the `unsloth-…-qat-oQ4` artifact are built
on the **qat** base while the others are not. Mixing them would vary the base model as well as the
format, which the project's one-axis rule forbids. The JANG cell is therefore *not* free here — it
would require finding a non-qat JANG artifact. UNVERIFIED that one exists.

### Rank 3 — gemma-4-E2B-it (dense, 4/4, below range)

35 layers, hidden 1536. `https://huggingface.co/google/gemma-4-E2B-it/raw/main/config.json`.

| Format | Repo id | Size (GB) |
|---|---|---|
| stock mlx 4-bit | `mlx-community/gemma-4-e2b-4bit` | 3.61 |
| oQ4e | `Jundot/gemma-4-E2B-it-oQ4e-mtp` | 3.87 |
| OptiQ-4bit | `mlx-community/gemma-4-e2b-it-OptiQ-4bit` | 5.26 |
| *(JANG_4M, bonus)* | `JANGQ-AI/gemma-4-E2B-it-qat-JANG_4M` | 7.84 |
| oQ4 | **UNVERIFIED** — not found in `?search=gemma-4-E2B-oQ` results | — |

At ~2 B it is below the requested 3–5 B band, but it is the cheapest full-four-format set found
(three verified + JANG = 20.58 GB; with oQ4 UNVERIFIED the 4/4 claim rests on a search miss, not
a confirmed artifact).

### Ranks 4–5 — the 2.x B dense pair (context, below range)

**LFM2.5-2.6B** — 30 layers, hidden 2048, `model_type: lfm2`.

| Format | Repo id | Size (GB) |
|---|---|---|
| stock mlx 4-bit | `mlx-community/LFM2.5-2.6B-4bit` | 1.54 |
| oQ4 | `gcoli/LFM2.5-2.6B-MLX-oQ4-fp16` | 1.60 |
| oQ4e | `gcoli/LFM2.5-2.6B-MLX-oQ4e-fp16` | 1.60 |
| OptiQ-4bit | `mlx-community/LFM2.5-2.6B-OptiQ-4bit` | 2.01 |

Four-format total: **6.75 GB (6.29 GiB)**. No JANG artifact found for this base.

**MiniCPM5-2B** — 42 layers, hidden 2048, `model_type: llama`.

| Format | Repo id | Size (GB) |
|---|---|---|
| oQ4 | `RepublicOfKorokke/MiniCPM5-2B-oQ4-fp16` | 1.49 |
| oQ4e | `gcoli/MiniCPM5-2B-oQ4e-fp16` | 1.49 |
| OptiQ-4bit | `mlx-community/MiniCPM5-2B-OptiQ-4bit` | 1.94 |
| stock mlx 4-bit | **UNVERIFIED** — `mlx-community/MiniCPM5-2B-4bit` returned HTTP 401 | — |

### Ranks 6–13 — two formats or fewer (recorded, not recommended)

| Base model | stock 4-bit | oQ4 | oQ4e | OptiQ | JANG |
|---|---|---|---|---|---|
| Fara1.5-4B | `runanywhere/Fara1.5-4B-mlx-4bit` | — | — | `mlx-community/Fara1.5-4B-OptiQ-4bit` (4.22 GB) | — |
| Nanbeige4.2-3B | `MercuriusDream/Nanbeige4.2-3B-mlx-4bit` | — | — | `mlx-community/Nanbeige4.2-3B-OptiQ-4bit` (3.32 GB) | — |
| Spark-X2.5-4B | — | — | — | `mlx-community/Spark-X2.5-4B-OptiQ-4bit` (3.05 GB) | `JANGQ-AI/Spark-X2.5-4B-JANG_8M` (4.39 GB) |
| NVIDIA-Nemotron-3-Nano-4B | — | `RepublicOfKorokke/NVIDIA-Nemotron-3-Nano-4B-oQ4` (2.35 GB) | — | `mlx-community/NVIDIA-Nemotron-3-Nano-4B-OptiQ-4bit` (3.10 GB) | — |
| SmolLM3-3B | `mlx-community/SmolLM3-3B-4bit` (1.75 GB) | `AtBeginDocument/SmolLM3-3B-oQ4` (1.82 GB) | — | — | — |
| Phi-4-mini-instruct | `mlx-community/Phi-4-mini-instruct-4bit` (2.18 GB) | — | `TheWirelessPhoenix/Phi-4-mini-instruct-oQ4e` (2.28 GB) | — | — |
| Ministral-3-3B | `mlx-community/Ministral-3-3B-Base-2512-4bit` (2.80 GB) | `gcoli/Ministral-3-3B-Base-2512-oQ4` (5.74 GB) | — | — | — |
| DeepSeek-R1-Distill-Qwen-7B | — | — | `TheWirelessPhoenix/DeepSeek-R1-Distill-Qwen-7B-oQ4e` (4.48 GB) | — | — |

Searches that returned empty for these bases: `?search=Ministral-3-3B-OptiQ`,
`?search=Ministral-3-3B-JANG`, `?search=Phi-4-mini-oQ`, `?search=DeepSeek-R1-Distill-Qwen-1.5B-OptiQ`,
`?search=Qwen3-30B-A3B-OptiQ`. A search miss is weaker evidence than a confirmed artifact and is
recorded as such.

### Ranks 14–17 — single-format (explicitly useless)

| Base model | Only format found | Repo id | Size (GB) |
|---|---|---|---|
| Llama-3.2-3B-Instruct | stock mlx 4-bit | `mlx-community/Llama-3.2-3B-Instruct-4bit` | 1.82 |
| VibeThinker-3B | OptiQ-4bit | `mlx-community/VibeThinker-3B-OptiQ-4bit` | 2.29 |
| mini-coder-4b | OptiQ-4bit | `mlx-community/mini-coder-4b-OptiQ-4bit` | 3.00 |
| DeepSeek-R1-Distill-Qwen-1.5B | stock mlx 4-bit | `mlx-community/DeepSeek-R1-Distill-Qwen-1.5B-MLX` — **not a single model**: 17.00 GB multi-quant bundle containing `*-2,6_mixed/`, `*-3,4_mixed/`, `*-3,6_mixed/` subdirectories | — |

**These four are useless to us.** They cannot supply more than one cell of the format axis.
Llama-3.2-3B is the clearest case: a well-known, easy-to-run 3 B dense model with no OptiQ, no oQ,
and no JANG artifact anywhere on the Hub.

---

## Q2 — Small MoE candidates (the important one)

### Why this question is the load-bearing one

The failure being chased is: **stock `mlx_lm.server` loads `Jundot/Qwen3.6-35B-A3B-oQ4-mtp`,
returns HTTP 200, generates a clean 64/64 tokens at full speed, and the text is mixed-script token
salad with replacement characters.** Confirmed architecture of that exact checkpoint:

```
Jundot/Qwen3.6-35B-A3B-oQ4-mtp
  model_type        = qwen3_5_moe
  num_experts       = 256
  num_experts_per_tok = 8
  num_hidden_layers = 40
```
Source: `https://huggingface.co/Jundot/Qwen3.6-35B-A3B-oQ4-mtp/raw/main/config.json`.

`mlx-community/Qwen3.5-35B-A3B-OptiQ-4bit` is the **same** architecture at the same expert count
(256 experts, 8 per token, 40 layers), so the runtime-side failure is a 256-expert MoE phenomenon.
A dense-only proof of concept could come back all-green and prove nothing, exactly as the task
warns. The JANG vendor's diagnosis — high expert counts compressed to the same bit width as
attention — makes **expert count the parameter to optimize for**, not total size.

### Ranked by expert count, then by format count

| Rank | Base model | Params (total/active) | **Experts** | Formats | Fits 36 GiB (all formats)? |
|---|---|---|---|---|---|
| 1 | **Qwen3.5-35B-A3B** | 35 B / 3 B | **256** (top-8) | 3–4 | **No** — 55.66 GB for 3 formats |
| 2 | **NVIDIA-Nemotron-3-Nano-30B-A3B** | 30 B / 3 B | **128** + 1 shared (top-6) | 3 / 4 | **No** — 58.45 GB |
| 3 | **Ling-3.0-tiny** | ~8 B | **128** + 1 shared (top-8) | 2 / 4 | Yes (9.11 GB) but 2 formats only |
| 4 | **Mellum2-12B-A2.5B** | 12 B / 2.5 B | 64 (top-8) | 1 verified | — |
| 5 | **OLMoE-1B-7B** | 7 B / 1 B | 64 (top-8) | **1 / 4** | — (useless) |
| 6 | **DeepSeek-V2-Lite** | 16 B / 2.4 B | 64 routed + 2 shared (top-6) | 2 / 4 | mixed bases |
| 7 | **gpt-oss-20b** | 21 B / 3.6 B | 32 (top-4) | 3 / 4 | Yes — 34.07 GB |
| 8 | **LFM2.5-8B-A1B** | 8 B / 1 B | **32** (top-4) | **4 / 4** | **Yes — 20.23 GB** |
| 9 | Qwen1.5-MoE-A2.7B | 14 B / 2.7 B | 60 (top-4) | 1 verified | 2024-era, superseded |
| 10 | granite-3.0-3b-a800m | 3 B / 0.8 B | 40 (top-8) | 1 verified | — |
| 11 | phi-3.5-moe | 42 B | 16 (top-2) | 1 verified | 2024-era, superseded |

### The two candidates that matter

**LFM2.5-8B-A1B** — 8 B total, 1 B active, **32 experts**, top-4, 24 layers, hidden 2048,
`moe_intermediate_size` 1792. This is the *only* model found that combines a published
**four-format set** with MoE architecture. Base config:
`https://huggingface.co/LiquidAI/LFM2.5-8B-A1B/raw/main/config.json`.

| Format | Repo id | Size (GB) |
|---|---|---|
| stock mlx 4-bit | `mlx-community/LFM2.5-8B-A1B-MLX-4bit` | 4.78 |
| *(official stock)* | `LiquidAI/LFM2.5-8B-A1B-MLX-4bit` | 4.85 |
| oQ4 | `stamsam/LFM2.5-8B-A1B-oQ4` | 4.99 |
| oQ4e | `brainworkup/LFM2.5-8B-A1B-oQ4e` | 4.99 |
| OptiQ-4bit | `mlx-community/LFM2.5-8B-A1B-OptiQ-4bit` | 5.47 |
| *(JANG_2L, bonus)* | `JANGQ-AI/LFM2.5-8B-A1B-JANG_2L` | 3.06 |

**Four-format total: 20.23 GB (18.84 GiB).** With JANG: 23.29 GB (21.69 GiB).
Interchangeable alternates: `RepublicOfKorokke/LFM2.5-8B-A1B-oQ4`, `Erkan/LFM2.5-8B-A1B-oQ4`,
`airagrp/LFM2.5-8B-A1B-oQ4e`, `djrsystemservices/LFM2.5-8B-A1B-MLX-oQ4e`.
All six artifacts declare the same `num_experts: 32`, `num_experts_per_tok: 4` — verified per repo.

**The honest limitation:** 32 experts is *eight times fewer* than the 256-expert configuration that
fails. If the defect depends on expert count — which is the working hypothesis — an
LFM2.5-8B-A1B proof of concept must be expected to come back **green** and prove nothing about the
35B-A3B failure. It is a valid test of the *format axis machinery* and a poor test of the *bug*.
This is stated plainly rather than buried: choose it for plumbing, not for diagnosis.

**NVIDIA-Nemotron-3-Nano-30B-A3B** — 30 B total, 3 B active, **128 routed experts** + 1 shared,
top-6, 52 layers, hidden 2688. The highest expert count that has more than two formats.

| Format | Repo id | Size (GB) |
|---|---|---|
| stock mlx 4-bit | `mlx-community/NVIDIA-Nemotron-3-Nano-30B-A3B-4bit` | 17.79 |
| oQ4e | `splats/NVIDIA-Nemotron-3-Nano-30B-A3B-oQ4e` | 18.58 |
| OptiQ-4bit | `mlx-community/NVIDIA-Nemotron-3-Nano-30B-A3B-OptiQ-4bit` | 22.08 |

**Three-format total: 58.45 GB (54.44 GiB) — does not fit.** No oQ4 (non-imatrix) and no JANG artifact
found for this base. Related but distinct: `JANGQ-AI/Nemotron-3-Nano-Omni-30B-A3B-JANGTQ4` and
`OsaurusAI/Nemotron-3-Nano-Omni-30B-A3B-JANG_4M` are for the **Omni** variant, a different base.

**Qwen3.5-35B-A3B** — the failing architecture itself, at 256 experts.

| Format | Repo id | Size (GB) |
|---|---|---|
| stock mlx 4-bit | `mlx-community/Qwen3.5-35B-A3B-4bit` | 20.42 |
| OptiQ-4bit | `mlx-community/Qwen3.5-35B-A3B-OptiQ-4bit` | 23.57 |
| *(JANG_2S)* | `JANGQ-AI/Qwen3.5-35B-A3B-JANG_2S` | 11.67 |
| *(JANG_4K)* | `JANGQ-AI/Qwen3.5-35B-A3B-JANG_4K` | 19.67 |

Three-format total: 55.66 GB (51.83 GiB) — **does not fit**. No oQ4/oQ4e artifact was found under
that exact base name (`?search=Qwen3.5-35B-A3B-oQ4e` returned zero results); the oQ4e 35B-A3B
artifacts on the Hub are for the **Ornith-1.5** derivative
(`scottlowry/Ornith-1.5-35B-A3B-oQ4e-mtp`, `BLCKHWK60/Ornith-1.5-35B-A3B-oQ4e`), which is a
different base model and therefore not the same cell.

A REAP-pruned variant exists and is worth knowing about:
`mlx-community/Qwen3.5-35B-A3B-OptiQ-4bit-REAP-19B` (13.76 GB) keeps the `qwen3_5_moe` type and
40 layers but is pruned to **128** experts — the pruning removes exactly the property under test,
so it is not a substitute for the 256-expert cell.

### MoE candidates that are disqualified

| Base model | Why | Evidence |
|---|---|---|
| **Ling-3.0-tiny** | 128 experts — the ideal small high-expert-count MoE, **but** see Q4: supported only via an oMLX patch, and only 2 of 4 formats exist (stock 4-bit 4.46 GB + oQ4e 4.65 GB). Not a four-format set. | `mlx-works/Ling-3.0-tiny-oQ4e`, `rapid-mlx/Ling-3.0-tiny-MLX-4bit` |
| **OLMoE-1B-7B** | 64 experts, 7 B total — attractive size, but **only the stock 4-bit MLX artifact exists** (`mlx-community/OLMoE-1B-7B-0125-Instruct-4bit`, 3.90 GB). No OptiQ, no oQ, no JANG under any author. | `?search=OLMoE` full listing; `?search=oLMoE-oQ`, `?search=OLMoE-OptiQ` empty |
| **DeepSeek-V2-Lite** | 64 routed + 2 shared experts. Stock exists (`mlx-community/DeepSeek-V2-Lite-Chat-4bit-mlx`) and one oQ4e exists — but that oQ4e is for the **Coder** variant (`pxleng/DeepSeek-Coder-V2-Lite-Instruct-oQ4e`, 9.32 GB), a different base. Two different bases ≠ one format axis. | `?search=DeepSeek-V2-Lite` listing |
| **Mellum2-12B-A2.5B** | 64 experts, `model_type: mellum`, 7.15 GB oQ4e (`intellitour/Mellum2-12B-A2.5B-Thinking-oQ4e-fp16`). No stock MLX 4-bit, no OptiQ, no JANG found. | `?search=Mellum2-12B`, `?search=Mellum` listings |
| **granite-3.0-3b-a800m** | 40 experts, only an unquantized HF release (`ibm-granite/granite-3.0-3b-a800m-instruct`, 6.75 GB). No MLX quantizations at all in `mlx-community`. | `?author=mlx-community&search=granite-3.0-3b-a800m` empty |
| **Qwen1.5-MoE-A2.7B**, **phi-3.5-moe** | 2024-era; single stock quantization each. Superseded by every row above. | `mlx-community/Qwen1.5-MoE-A2.7B-Chat-4bit`, `mlx-community/phi-3.5-moe-instruct-4bit` |

### On gpt-oss-20b (32 experts, 3/4 formats)

| Format | Repo id | Size (GB) |
|---|---|---|
| stock mlx MXFP4 | `mlx-community/gpt-oss-20b-MXFP4-Q4` | 11.21 |
| oQ4 | `cjnielson44/gpt-oss-20b-oQ4` | 11.21 |
| OptiQ-4bit | `mlx-community/gpt-oss-20b-OptiQ-4bit` | 11.65 |

Three-format total: **34.07 GB (31.73 GiB)** — it fits, but only alone, and there is no oQ4e and no
JANG. It also has the same 32-expert weakness as LFM2.5-8B-A1B while costing 1.7× the disk.
Note `cjnielson44/gpt-oss-20b-oQ4` ships `config.json.bak-before-mxfp4-expert-overrides` and
`omlx_oQ4_manifest.json` — evidence that oQ on this base required hand-editing the config, which
makes it a weaker "clean format cell" than LFM2.5-8B-A1B's oQ4/oQ4e pair.

---

## Q3 — Total disk for the top of each list

Sizes are decimal GB, summed from the four format artifacts only (JANG excluded — it is a fifth
format, not part of the axis, and the task's four cells are stock/oQ4/oQ4e/OptiQ).

| Combination | stock | oQ4 | oQ4e | OptiQ | **Total** | In GiB | Fits 36 GiB? | Fits 35 GiB? |
|---|---|---|---|---|---|---|---|---|
| **Dense: Qwen3.5-4B (4/4)** | 3.06 | 3.16 | 3.17 | 4.04 | **13.43 GB** | 12.51 | yes | yes |
| **MoE: LFM2.5-8B-A1B (4/4)** | 4.78 | 4.99 | 4.99 | 5.47 | **20.23 GB** | 18.84 | yes | yes |
| **Both together (the recommended set)** | — | — | — | — | **33.66 GB** | **31.35** | **yes** | **yes** |
| Dense: gemma-4-E4B-it (4/4) | 5.18 | 4.79 | 5.54 | 7.52 | 23.03 GB | 21.45 | yes | yes |
| gemma-4-E4B-it + LFM2.5-8B-A1B | — | — | — | — | 43.26 GB | 40.29 | **no** | **no** |
| MoE: gpt-oss-20b (3/4) | 11.21 | 11.21 | — | 11.65 | 34.07 GB | 31.73 | yes (alone) | yes (alone) |
| MoE: Nemotron-3-Nano-30B-A3B (3/4) | 17.79 | — | 18.58 | 22.08 | 58.45 GB | 54.44 | **no** | **no** |
| MoE: Qwen3.5-35B-A3B (3/4) | 20.42 | — | — | 23.57 | 55.66 GB | 51.83 | **no** | **no** |

**Verdict.**

- The recommended dense+MoE pair fits with **31.35 GiB used of 36 GiB**, leaving ~4.6 GiB headroom
  — enough for the HF cache's `blobs/` + `snapshots/` duplication of metadata and any re-download.
- **No 256-expert model can be held in all formats at once.** Qwen3.5-35B-A3B is 55.66 GB for three
  formats; the failing checkpoint's own architecture simply cannot be the format axis's subject at
  full four-format coverage on this machine.
- **No 128-expert model can be held in four formats either** — Nemotron-3-Nano-30B-A3B is 58.45 GB
  for three, and Ling-3.0-tiny only has two formats.
- Adding a JANG fifth cell to both recommendations costs another 6.27 GB (3.21 + 3.06), taking the
  pair to 39.93 GB = 37.19 GiB — **over budget**. If JANG is added, drop the dense model's OptiQ
  cell or accept that only one family gets a JANG cell.

---

## Q4 — Architecture check

### How mlx-lm actually resolves an architecture

From the oMLX bundle's own mlx-lm, `mlx_lm/utils.py`:

```python
MODEL_REMAPPING = { ... }                       # line 45
model_type = MODEL_REMAPPING.get(model_type, model_type)   # line 187
arch = importlib.import_module(f"mlx_lm.models.{model_type}")  # line 189
```

So the test is mechanical: **the file `mlx_lm/models/<model_type>.py` must exist** (or the type must
appear in `MODEL_REMAPPING`). There is no `auto_map` / `trust_remote_code` path — a repo that
ships `modeling_<x>.py` next to its config does **not** get that code executed. This is precisely
how `gemma4_unified` was lost.

### The check that must be run twice — bundled mlx-lm is not the whole story

Checking only `mlx_lm/models/` gives the wrong answer, because **oMLX vendors patches that register
model types mlx-lm 0.31.3 lacks.** The dispatcher is
`/Applications/oMLX.app/Contents/Resources/omlx/utils/model_loading.py` (lines 499–625), which
pre-loads a patch based on `config["model_type"]`:

| Patch applied when `model_type ==` | Vendored module | Source |
|---|---|---|
| `bailing_hybrid` | `omlx/patches/bailing_hybrid/bailing_hybrid_model.py` | registers `mlx_lm.models.bailing_hybrid` from `scaryrawr/mlx-lm` @ `ling-3.0-flash` branch, head SHA `d719464ff754e65d9dec496ef3fea27bddefd79c` |
| `laguna` | `omlx/patches/laguna/laguna_model.py` | `patches/laguna/__init__.py:92` |
| `hy_v3` | `omlx/patches/hy_v3/` | `patches/hy_v3/__init__.py:132` |
| `mimo_v2` | `omlx/patches/mimo_v2/` | `patches/mimo_v2/__init__.py:27` |
| `deepseek_v4*` (prefix) | `omlx/patches/deepseek_v4/` | `model_loading.py:499` |
| `step3p7` | `omlx/patches/step3p7/` | `model_loading.py:505` |
| `glm_moe_dsa` | `omlx/patches/glm_moe_dsa/` | `model_loading.py:547` |
| `llama4` (top-level or `text_config`) | `omlx/patches/llama4_attention.py` | `model_loading.py:541` |
| `minimax_m3` / `minimax_m3_vl` | `omlx/patches/minimax_m3_mlx_lm/` | `model_loading.py:555` |

**No patch exists for `spark2_5`, `nanbeige`, or `lfm2_vl`.** A scoped grep of the entire
`omlx/` tree for those three strings returns only unrelated matches (`dspark_*` kernel names in
`custom_kernels/glm_moe_dsa/fast.py`). They are genuinely unsupported.

### Per-candidate result

Bundled mlx-lm 0.31.3 models directory, listed whole (119 `.py` modules):
`/Applications/oMLX.app/Contents/Resources/Python/framework-mlx-base/lib/python3.11/site-packages/mlx_lm/models/`
— version confirmed at `mlx_lm/_version.py:3 → __version__ = "0.31.3"` and
`mlx_lm-0.31.3.dist-info/` beside it.

Every import below was **executed**, not inferred, using the bundle's own interpreter
`/Applications/oMLX.app/Contents/Resources/Python/cpython-3.11/bin/python3` with
`importlib.import_module("mlx_lm.models." + type)`, run from
`/Applications/oMLX.app/Contents/Resources/Python/framework-mlx-base/lib/python3.11/site-packages`.

| Candidate | `config.json` `model_type` | `mlx_lm/models/<type>.py` | Import test | oMLX patch | **Verdict** |
|---|---|---|---|---|---|
| **Qwen3.5-4B** | `qwen3_5` (text `qwen3_5_text`) | `qwen3_5.py` present | **OK** | not needed | **USABLE** |
| **gemma-4-E4B-it** | `gemma4` (text `gemma4_text`) | `gemma4.py`, `gemma4_text.py` present | **OK** | not needed | **USABLE** |
| **gemma-4-E2B-it** | `gemma4` (text `gemma4_text`) | present | **OK** | not needed | **USABLE** |
| **LFM2.5-2.6B** | `lfm2` | `lfm2.py` present | (dense, same family as `lfm2_moe` OK) | not needed | **USABLE** |
| **LFM2.5-8B-A1B** (MoE) | `lfm2_moe` | `lfm2_moe.py` present | **OK** | not needed | **USABLE** |
| **gpt-oss-20b** (MoE) | `gpt_oss` | `gpt_oss.py` present | **OK** | not needed | **USABLE** |
| **NVIDIA-Nemotron-3-Nano-30B-A3B** (MoE) | `nemotron_h` | `nemotron_h.py` present | **OK** | not needed | **USABLE** |
| **NVIDIA-Nemotron-3-Nano-4B** | `nemotron_h` | present | **OK** | not needed | **USABLE** |
| **Mellum2-12B-A2.5B** (MoE) | `mellum` | `mellum.py` present | **OK** | not needed | **USABLE** |
| **DeepSeek-V2-Lite** (MoE) | `deepseek_v2` | `deepseek_v2.py` present | **OK** | not needed | **USABLE** |
| **Ling-3.0-tiny** (MoE) | `bailing_hybrid` | **absent** | **FAIL** (`No module named 'mlx_lm.models.bailing_hybrid'`) | **`apply_bailing_hybrid_patch` — registers it** | **USABLE via oMLX only** |
| **Nanbeige4.2-3B** | `nanbeige` | **absent** | **FAIL** | **none** | **DISQUALIFIED** |
| **Spark-X2.5-4B** | `spark2_5` | **absent** | **FAIL** | **none** | **DISQUALIFIED** |
| **LFM2.5-VL-3B** | `lfm2_vl` | file is `lfm2-vl.py` (hyphen) | **FAIL** (`No module named 'mlx_lm.models.lfm2_vl'`) | none (mlx-vlm handles it) | **DISQUALIFIED for the LLM engine** |
| **OLMoE-1B-7B** | `olmoe` | `olmoe.py` present | **OK** | not needed | usable, but 1 format |
| **Fara1.5-4B** | `qwen3_5` | present | OK | not needed | usable, but 2 formats |
| **VibeThinker-3B**, **DeepSeek-R1-Distill-Qwen-7B** | `qwen2` | `qwen2.py` present | OK | not needed | usable, but ≤2 formats |
| **Llama-3.2-3B**, **SmolLM3-3B**, **Phi-4-mini** | `llama`, `smollm3`, `phi3` | all present | OK | not needed | usable, but ≤2 formats |
| **Ministral-3-3B** | `mistral3` (text `ministral3`) | `mistral3.py`, `ministral3.py` present | OK | not needed | usable, but 2 formats |

**Two disqualifications bite.** `spark2_5` and `nanbeige` each have an OptiQ-4bit artifact published
by `mlx-community` — a repo that normally only quantizes what it can serve — yet neither type
resolves in this mlx-lm, and oMLX vendors no patch for either. They are unusable on this machine
today. Both repos ship `modeling_*.py` files beside their configs, which is the tell: the publisher
expected a runtime that loads remote code.

**One finding that contradicts a prior note.** `gemma4_unified` is *not* missing in 0.31.3 — it is
remapped:

```python
"gemma4_unified": "gemma4",  # encoder-free multimodal variant; vision/audio weights stripped by sanitize()
```
`mlx_lm/utils.py:55`. The earlier statement in
`docs/research/2026-09-15-format-matrix-and-tooling.md` (line 35) that 0.31.3 ships `gemma4` but
not `gemma4_unified` is true of the *file list* and false of the *resolution path*. Whether the
`sanitize()` path handles real `gemma4_unified` checkpoints end-to-end is **UNVERIFIED** — the
remapping entry is all that was verified here, and no such checkpoint was loaded.

**One negative result worth recording:** `mlx_lm/models/lfm2-vl.py` uses a hyphen in its filename,
so `importlib.import_module("mlx_lm.models.lfm2_vl")` raises `ModuleNotFoundError` even though the
file sits in the models directory. The module is never reachable through mlx-lm's resolution path.
This is a latent packaging bug in mlx-lm 0.31.3; the architecture check must import-test rather
than `ls`.

---

## Recommendation

**Dense model: `Qwen3.5-4B`.**
Four formats exist, plus a fifth (JANG). It is the smallest complete four-format set at 3–5 B, it
resolves natively in mlx-lm 0.31.3 as `qwen3_5` with no patch, and it is the same
transformer-decoder family as the failing model's attention path.

| Format | Artifact | GB |
|---|---|---|
| stock mlx 4-bit | `mlx-community/Qwen3.5-4B-4bit` | 3.06 |
| oQ4 | `RepublicOfKorokke/Qwen3.5-4B-oQ4` | 3.16 |
| oQ4e | `uingei/Qwen3.5-4B-oQ4e` | 3.17 |
| OptiQ-4bit | `mlx-community/Qwen3.5-4B-OptiQ-4bit` | 4.04 |
| | **Total** | **13.43 GB (12.51 GiB)** |

**MoE model: `LFM2.5-8B-A1B`.**
The only MoE on the Hub with a complete four-format set. 8 B total / 1 B active / 32 experts.

| Format | Artifact | GB |
|---|---|---|
| stock mlx 4-bit | `mlx-community/LFM2.5-8B-A1B-MLX-4bit` | 4.78 |
| oQ4 | `stamsam/LFM2.5-8B-A1B-oQ4` | 4.99 |
| oQ4e | `brainworkup/LFM2.5-8B-A1B-oQ4e` | 4.99 |
| OptiQ-4bit | `mlx-community/LFM2.5-8B-A1B-OptiQ-4bit` | 5.47 |
| | **Total** | **20.23 GB (18.84 GiB)** |

**Combined total: 33.66 GB = 31.35 GiB.** Fits the 36 GiB budget with ~4.6 GiB to spare, and fits the
35 GiB `df` reading.

**State the caveat in every table this pair produces:** the MoE cell has **32 experts**, the failing
checkpoint has **256**. A green result from `LFM2.5-8B-A1B` validates the format-axis machinery; it
does **not** exonerate stock mlx-lm on high-expert-count MoE. No 256-expert model fits in all
formats at once on this machine (best case 51.83 GiB), so that hypothesis cannot be closed by a
four-format matrix here at all — it needs a single-format, two-runtime design instead.
