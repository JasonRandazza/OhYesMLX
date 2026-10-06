# MTPLX — models, published claims, benchmarks, and community (2026-10-06)

**Purpose:** the second half of the "should MTPLX become the sixth runtime?" decision. The sibling
document `docs/research/2026-10-06-mtplx-architecture.md` (order `mtplx-source`) read the engine:
how the MTP draft/verify loop works, schedulers, KV cache, sampler defaults, streams, license,
release cadence. This document covers what the engine **loads**, what it **claims**, what others
have **measured**, what is **broken**, and who **maintains** it — ending with the one-variable cell
proposal. The operating surface (install, flags, HTTP API, Runtime-hook mapping) is the third
order (`mtplx-surface`) and is not duplicated here.

**Revision read:** `youssofal/MTPLX@9882703f3105363ddc37eca9f97aa09a1d387112` ("Release notes: the
2.12.2 gate results", 2026-10-03), the shared `--depth 1` clone at `/private/tmp/claude-501/mtplx-src`
(HEAD file `.git/refs/heads/main` read directly, 2026-10-06). All `file:line` citations are relative
to that revision. The harness's own artifact claims were read from the local HuggingFace cache on
this host (`~/.cache/huggingface/hub/`, snapshot revisions named inline) — bytes, not remote cards.

**Method / tiers.** Source and local artifacts first, then web in the standard tier order (SearXNG
first; direct fetches of the named vendor pages and the GitHub REST API). Every claim is labelled:

- **VERIFIED(source)** — read directly in the MTPLX source at `9882703`, in a local artifact's
  bytes, in this repo's own docs/source, or in a REST response quoted with its URL.
- **CLAIMED(vendor/community)** — stated by a party (MTPLX, DevoxxGenie, a YouTuber, a third-party
  README); not independently reproduced.
- **INFERRED** — my reasoning over verified facts; not stated by anyone.

**Cross-references:** `AGENTS.md` (vary-one-thing, coherence gate, Decision 131 sampler survey);
`docs/research/2026-10-06-mtplx-architecture.md` (§3.2 depth, §3.4 exactness, §5 cache);
`docs/runtimes/optiq.md` §1.4 and §9.2; `docs/runtimes/vmlx.md` §7.4.1–§7.4.2;
`docs/research/2026-09-25-mtp-depth-sweep.md`.

---

## 1. What models and quant formats MTPLX supports

### 1.1 Model families, from the source's own registry

The architecture catalog (`mtplx/backends/registry.py:131-...`, `ARCHITECTURE_CATALOG`) and the
documentation page `docs/architectures.md` are the authority. As read:

| Tier | Family / architecture | Backend | Status |
|---|---|---|---|
| Product-verified, native MTP | Qwen3-Next lineage: **Qwen3.5 / 3.6 / 3.8**, incl. MoE (`qwen3_5`, `qwen3_6`, `qwen3_8`, aliases incl. `qwen3_5_mtp`) | `qwen3_next` | "Product-verified default backend; this remains the only promoted shipping runtime" (`registry.py:218-235`) |
| Experimental, native | **Qwen4 preview / Qwen3.8-Flash-Next** (`qwen4_exp`) | `qwen4_exp` | contract-gated; native MTP head from the pack's `mtp.safetensors` (`registry.py:236-268`) |
| Experimental, native | **DeepSeek V3/V3.2** MTP (`deepseek_mtp`) | `deepseek_mtp` | contract-gated (`registry.py:269-284`) |
| Experimental, native AR + optional MTP | **DeepSeek-V4-Flash** (`deepseek_v4`) | in-tree | AR backend; MTP engages when `mtp.0.*` weights exist (`docs/architectures.md:7`) |
| Recognized, AR-only | **LFM2.5 MoE** (`lfm2_moe` / `Lfm2MoeForCausalLM`) | `mlx_lm_ar` | "Hybrid ShortConv+GQA MoE **without an MTP head**; loads through the bundled mlx-lm lfm2_moe module and serves target-only AR" (`registry.py:153-174`) |
| Recognized, AR-only | llama-architecture (`llama`), IQuest Coder (`iquestcoder`) | `mlx_lm_ar` | experimental AR-only entries (`registry.py:175-217`) |
| Recognized, AR-only | **Laguna-S-2.1 oQ4e at a pinned revision** | `laguna_ar` | geometry-gated to the exact `mlx-community/Laguna-S-2.1-oQ4e` checkpoint (`registry.py:132-152`) |
| Experimental, contract-gated (per docs) | DeepSeek V3/V4, GLM, MiMo, Nemotron-H, Step3.5, Hy-V3 | per-family patches | `docs/model-compatibility.md:10` |
| Recognized, not runnable | Llama-MTP, generic MTP layouts | — | `docs/architectures.md:9-12` |

The descriptor module also names `gemma4` among supported families
(`supported_families: ("qwen3_5", "qwen3_6", "qwen3_8", "gemma4")`, `backends/descriptors.py:125`;
Gemma-4 pair lane at `:1046`) — matching the README's Gemma 4 packs and the Gemma-4
target/assistant pair (`gemma4_pair.py`). [VERIFIED(source)]

The compatibility tiers a user sees (`mtplx inspect`) are: **verified** (`mtplx_runtime.json` exists
and matches the expected contract), **architecture-compatible, unverified** (Qwen3-Next MTP markers
exist, no contract — "Loads and runs, labeled unverified"), **AR-only**, **incompatible
architecture**, **no MTP** (`docs/model-compatibility.md:3-11`). [VERIFIED(source)]

### 1.2 MTP head discovery — the three layouts that matter for the harness

`expected_mtp_file` resolves, in order: the config pointer `mlx_lm_extra_tensors.mtp_file`, then
`mtp.safetensors`, `mtp/weights.safetensors`, `model-mtp.safetensors` (`artifacts.py:425-435`).
If no sidecar resolves, the injector falls back to **embedded** `mtp.*` tensors selected out of the
shard index (`mtp_patch.py:760-780`; `_candidate_weight_files`, `qwen3_5_mtp_patch.py:124-144`).
The generic injector's gate is `_num_mtp_layers` over
`text_config.mtp_num_hidden_layers → text_config.num_nextn_predict_layers →
num_nextn_predict_layers` (`mtp_patch.py:253-258`); zero layers returns before any head is looked
for. [VERIFIED(source)]

When a head *is* found, its key set is classified against four canonical prequantized layouts
(`_mtp_contract_for_weight_keys`, `mtp_patch.py:484-520`, against `constants.py:20-123`); an exact
key-set match sets `mtp_prequantized` and the quant policy (`all` / `cyankiwi`) automatically.
[VERIFIED(source)] This classification is what makes §3 below answerable at the byte level.

### 1.3 Quant formats

- **MLX safetensors only, as far as the load path goes.** Serving loads through
  `mlx_lm.utils.load` or MTPLX's in-tree model classes; the artifact contract is safetensors +
  config. [VERIFIED(source): `runtime.py:1244-1259`]
- **Body quantization**: the published packs are 4-bit (flat and dynamic), 6-bit, 8-bit
  (dynamic), and FP16 siblings for M1/M2 — all MLX affine-style group quantization with per-module
  overrides where the family needs them. [VERIFIED(source): `README.md:118-131`; the pack
  descriptions; CLAIMED(vendor) for the prose claims about fidelity]
- **Prequantized MTP heads** are a first-class format: `mtp.safetensors` carrying
  `weight`/`scales`/`biases` triplets for the quantized linears, with the canonical dense set
  (29 tensors) and MoE sets (37 / 42 tensors) in `constants.py:20-186`. [VERIFIED(source)]
- **Forge conversion input**: HF checkpoints, incl. compressed-tensors (FP8/AWQ-style) sources
  via `mtplx/compressed_tensors.py`; **GGUF is detected only to refuse it** — "GGUF sources are
  detected but Forge V1 builds MLX/safetensors artifacts only" (`commands/forge.py:64-65`,
  `:577-583`, `:669-681`). Whether any serving path ever loads GGUF: no GGUF tensor-loading code
  was found in the loader I read; the loader keys on safetensors (`.safetensors`/`.bin` detection
  in `hf_loader.py:548` is a presence check, not a loader). [VERIFIED(source) for the Forge
  refusal; INFERRED for "self-serve GGUF serving is not a supported path"].
- The **harness's own formats** — oQ4 / oQ4e / OptiQ / JANG — are all MLX safetensors with
  `quantization` blocks (mixed bits, affine and `mxfp8` modes; verified by reading each local
  bundle's config below). Whether each *specific* mixed-patch loads under the pinned
  `mlx==0.32.2`/`mlx-lm>=0.31,<0.32` is a load test, not a doc question. [INFERRED]

---

## 2. The MTPLX-optimised HuggingFace bundles

MTPLX ships its own converted packs under `Youssofal/*`. The catalogue, from the README's pack
tables and the FAQ model answer (`README.md:104-137`, `mtplx.com/faq/`):

| Bundle (repo short name) | Quant | Download / peak | Notes |
|---|---|---|---|
| `Qwen3.8-Flash-Next-MTPLX-Optimized-Speed` | dynamic 4-bit, 8-bit attention | 115.1 GB / ~83 GB resident | 125B MoE; n-gram table streams from SSD; depth 3 (family accepts up to 5); 96 GB+ |
| `Qwen3.8-Flash-Next-MTPLX-Bare-Speed` | flat 4-bit | 106.3 GB / ~74 GB resident | 96 GB+ |
| `Qwen3.8-Flash-Next-MTPLX-Optimized-Quality` | 8-bit G64 + BF16 structure, 4-bit n-gram | 169.96 GB / ~128.5 GiB | 256 GB+; "not yet been run on a 256 GB Mac, and its speed has not been measured" |
| `Qwen3.8-27B-MTPLX-Optimized-Speed` | 4-bit dynamic | 20.4 GB / 23.6 GB peak | the default coding recommendation; 96.0% top-1 agreement with bf16, KL 0.012 (vendor) |
| `Qwen3.8-27B-MTPLX-Bare-Speed` | flat 4-bit | 16.0 GB / 17.0 GB peak | |
| `Qwen3.8-27B-MTPLX-Optimized-Quality` | 8-bit dynamic | 29.4 GB / 32.7 GB peak | 99.3% top-1 agreement, KL 0.0005 (vendor) |
| `Qwen3.8-27B-MTPLX-*-FP16` (3 builds) | fp16 | same sizes | "for M1 and M2" |
| `Qwen3.5-4B-MTPLX-Optimized-Speed` / `-Quality` | 4-bit / 8-bit | peak 2.9 / 4.8 GiB | 8 GB Macs and up; depth 3 |
| `Qwen3.5-9B-MTPLX-Optimized-Speed` | 6-bit | peak 10.0 GiB | "Turbo"; tuning a 16 GB M4 mini lands on depth 1 |
| `MiMo-V2.6-Qwen-9B-MTPLX-Optimized-Speed` | 6-bit | 8.70 GB / 10.0 GiB | Xiaomi's agentic distill of Qwen 3.5 9B, with the Qwen 3.5 9B MTP head; vendor says MiMo's speed on MTPLX not measured yet |
| `Ternary Bonsai 2 27B` (Prism ML) | ternary | 8.85 GB / 11.4 GB peak on M5 Max | Qwen3.8-27B rebuilt with ternary weights + the 27B draft head; Prism ML reports 98.2% of the full model's benchmark average |
| Qwen 3.6 packs (27B speed/quality, 35B-A3B speed/balance) | — | — | "still published and still supported" below the 3.8 recommendation |

[VERIFIED(source) for the table contents as read in `README.md`; sizes/peaks and fidelity
percentages are CLAIMED(vendor)]

Two product facts the harness order should note:

1. **These are a different artifact axis than our format study.** A `Youssofal/*` pack bundles a
   conversion recipe (dynamic/mixed quant), an MTP head, a chat template, and a runtime contract
   (`mtplx_runtime.json`) in one unit. Comparing "MTPLX on its own pack" to "vMLX on `JANG_4S`"
   varies the runtime, the quantization format, and the conversion provenance in one step — three
   variables, and AGENTS.md's one-variable rule forbids publishing it as a runtime result.
   [INFERRED, from the pack contents + the rule]
2. **Forge is the general converter** ("takes a Hugging Face repo and turns it into an MTPLX-ready
   MTP model… publishes back to the Hub if you want") and it reports its own before/after verdict
   (`README.md:181-187`). Forge's head-extraction gap is a live issue — see §8.
   [VERIFIED(source) for Forge; CLAIMED(vendor) for its verdict quality]
3. **Attribution.** The NOTICE requires products that "include, embed, or are built on MTPLX" to
   display "Powered by MTPLX"; published benchmarks/writing are asked for "MTPLX by Youssof
   Altoukhi" with a link (`NOTICE:8-28`). A results document is not an embedded product, but the
   credit line is cheap and the sibling architecture doc already flagged the distinction.
   [VERIFIED(source); INFERRED for the harness reading]

---

## 3. Can it load the harness's existing bundles?

This is the order's central question, and it can now be answered at the level of **declared
capability + tensor bytes**, which leaves only the actual load as the coordinator's test. Each row
below was read from the local HF cache on this host, 2026-10-06.

### 3.1 What each bundle declares and carries

| Bundle (local snapshot read) | `model_type` | Declares MTP? | MTP tensors on disk | Exact key-set match to a MTPLX canonical set? |
|---|---|---|---|---|
| `RepublicOfKorokke/Qwen3.5-4B-oQ4` (`3ae88a7…`) | `qwen3_5` | `text_config.mtp_num_hidden_layers: 1` | **none** — single-file `model.safetensors`, 1,203 keys, 0 `mtp.*`, no index file | n/a |
| `uingei/Qwen3.5-4B-oQ4e` (`2e232d5…`) | `qwen3_5` | same, `=1` | **none** — index 1,221 keys, 0 `mtp.*` | n/a |
| `JANGQ-AI/Qwen3.5-4B-JANG_4S` (`4567967…`) | `qwen3_5` | same, `=1` | **31 embedded `mtp.layers.0.*`** in the single shard; JANG 2.0 config; `vmlx_mtp_proposal_head.json` (vMLX-specific proposal-head gate: eligible:false, "tied_embeddings" — not MTPLX's MTP path) | **exact = `EXPECTED_ALL_PREQUANTIZED_MTP_KEYS` (31)** — the fully-prequantized dense set incl. a quantized `mtp.fc` ✅ |
| `mlx-community/Qwen3.5-4B-OptiQ-4bit` (`6cb5bdf…`) | `qwen3_5` | same, `=1`, plus `mlx_lm_extra_tensors.mtp_file = "optiq/mtp.safetensors"` and `mtplx_mtp_quantization {bits:4, group_size:64, mode:affine, policy:cyankiwi, prequantized:true}` | sidecar `optiq/mtp.safetensors`, **29 tensors** | **exact = `EXPECTED_PREQUANTIZED_MTP_KEYS` (29)** ✅ |
| `Jundot/Qwen3.6-35B-A3B-oQ4` (`0c710db…`) | `qwen3_5_moe` | same, `=1` | **none** — index 2,010 keys, 0 `mtp.*` | n/a |
| `Jundot/Qwen3.6-35B-A3B-oQ4-mtp` | — | — | **not on this host** (refs only, no snapshot) | n/a |
| `mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit` (`70a3aa3…`) | `qwen3_5_moe` | same, `=1`, plus the same `mtp_file` pointer and `mtplx_mtp_quantization` block | sidecar `optiq/mtp.safetensors`, **37 tensors** | **exact = `EXPECTED_QWEN_MOE_PREQUANTIZED_MTP_KEYS` (37)** ✅ |
| `stamsam/LFM2.5-8B-A1B-oQ4`, `brainworkup/...-oQ4e`, `mlx-community/...-OptiQ-4bit`, `JANGQ-AI/...-JANG_2L`, `mlx-community/...-MLX-4bit` | `lfm2_moe` | **no MTP fields at all** in any of the five | 0 `mtp.*` in every index | n/a |

[VERIFIED(source): local `config.json` and safetensors headers at the named snapshots; key-set
comparisons run against `mtplx/constants.py` at `9882703` via a direct set diff — both OptiQ
sidecars matched **exactly**, with zero missing and zero extra keys.]

### 3.2 What MTPLX will do with each, from its own code

The decision tree for a `qwen3_5`-family bundle (all six above except LFM2.5) is:

1. `--mtp` (default on for the family): dispatch to the generic injector because these configs use
   `mtp_num_hidden_layers`, not the `num_nextn_predict_layers` that `is_qwen3_5_mtp_config` keys on
   (`qwen3_5_mtp_patch.py:63-74` vs `mtp_patch.py:253-258`; dispatch order at `runtime.py:807-812`).
2. The injector resolves a head: config pointer → sidecar → embedded. Then:
   - **Sidecar found** → key-set classified; exact match sets `mtp_prequantized`; head attaches.
     [VERIFIED(source): `mtp_patch.py:484-520`, `:760-780`]
   - **No sidecar, embedded `mtp.*` in the index** → embedded head attaches; a detector-gated
     norm heal runs first (`_restore_delta_encoded_mtp_norms` → `shift_delta_mtp_norms`,
     `mtp_patch.py:346-398`; `qwen3_5_mtp_patch.py:147-170`). [VERIFIED(source)]
   - **Neither** → `logger.warning("[MTP inject] MTP weights not found")` and return `False`
     (`mtp_patch.py:780-783`).
3. Back in the runtime, a failed injection is sorted by `mtp_weights_present_on_disk`
   (`runtime.py:813-828`; `artifacts.py:438-489`): can the absence be **positively** proven from
   the index? → warn and **degrade to AR**; otherwise the ambiguity returns `True` and the load
   **raises** `MTP injection failed`. [VERIFIED(source)]

Applied to the table:

| Bundle | Predicted MTPLX behaviour (source-level) | Confidence |
|---|---|---|
| `Qwen3.5-4B-OptiQ-4bit` | **MTP cells should attach**: pointer resolves to `optiq/mtp.safetensors`; the 29 tensors are byte-for-byte the canonical prequantized dense set; `mtplx_mtp_quantization` supplies bits/GS/mode/policy. No `mtplx_runtime.json` → "architecture-compatible, unverified" label only. | High, from source + exact set match; the load itself is unrun |
| `Qwen3.6-35B-A3B-OptiQ-4bit` | Same, against the 37-tensor MoE canonical set (fused `experts.down_proj`/`experts.gate_up_proj` layout, not `switch_mlp`). | High, same caveat |
| `JANGQ-AI/Qwen3.5-4B-JANG_4S` | Embedded head path, and the head is in **canonical form**: `_mtp_contract_for_weight_keys` is applied to embedded keys too (`mtp_patch.py:766-780`), and the 31-tensor set matches `EXPECTED_ALL_PREQUANTIZED_MTP_KEYS` exactly → classified prequantized, policy `all`. The double-shift refusal (`q_norm` mean > 2.4, `runtime.py:1263-1302`) should **not** fire: JANG stores q_norm deltas (layer 15 mean **0.5914**, F16) and mlx-lm's sanitize adds +1.0 when `mtp.*` or an unsanitized conv1d is present (`mlx_lm/models/qwen3_5.py:307-332`; JANG's conv1d is `[8192, 1, 4]`, i.e. unsanitized), landing on **1.5914** — numerically identical to what the three absolute-convention packs store at the same layer (uingei oQ4e and both OptiQ 4B packs all read 1.5914; Jundot/OptiQ 35B read 1.5423). Remaining unknowns: JANG's tensor prefix (`model.language_model.*` vs the standard `language_model.model.*`) through `mlx_lm.utils.load`, and JANG's non-standard quant bookkeeping. | Medium-high — head format and norm arithmetic are verified; the trunk load is not |
| `uingei/Qwen3.5-4B-oQ4e` | Declares MTP, carries none, index *is* readable and holds zero `mtp.*` → positive absence → **warn + serve AR**. A depth pin here would be silently degraded at load; the harness's log half must catch it. | High, from source |
| `Jundot/Qwen3.6-35B-A3B-oQ4` | Same as oQ4e: positive absence in a readable index → **degrade to AR**. | High |
| `RepublicOfKorokke/Qwen3.5-4B-oQ4` | Declares MTP, carries none, **no index and no sidecar** → `mtp_weights_present_on_disk` returns `True` (conservative) → injection failure **raises**; a default MTP-on load should fail loudly. With `--no-mtp` an AR cell may load (unrun). | Medium-high, from source |
| LFM2.5-8B-A1B (all five) | Family `lfm2-moe-ar`, **AR-only by construction** — no MTP head exists on the model, so an MTPLX column on any LFM2.5 artifact is an AR column. [VERIFIED(source): `registry.py:153-174` + zero MTP fields in all five configs] | High |

### 3.3 The format-axis confound, stated plainly

One policy sentence in the README looks at first like a blocker for every row above: **"MTPLX does
not support attaching a separately supplied MTP sidecar to an arbitrary MLX trunk. Matching
architecture fields, tensor shapes, or provenance labels cannot prove that the head was trained
against those exact trunk weights. Use a complete model that already includes its matching MTP
weights, or use Forge to build and verify an artifact from its original source checkpoint."**
(`README.md:187`) [VERIFIED(source)]. The OptiQ bundles are not that case: their sidecar is the
checkpoint's own head, named by the checkpoint's own config (`mlx_lm_extra_tensors.mtp_file`),
quantized alongside the trunk per the `mtplx_mtp_quantization` block, and matching MTPLX's
canonical tensor layouts exactly. What MTPLX withholds from such a pack is the **verified label**,
not the load: no `mtplx_runtime.json` → "architecture-compatible, unverified — loads and runs,
labeled unverified" (`docs/model-compatibility.md:8`). The practical reading: attaching is the
designed behaviour, and the unverified label is the designed caveat to carry onto the row.
[VERIFIED(source) for the policy and the tier; INFERRED for the reading]

- The **OptiQ sidecars are the one clean artifact bridge**: they were not built *for* MTPLX, they
  sit in bundles the harness already measures, and their tensor key sets are the exact layouts
  MTPLX's own constants define. [VERIFIED(source). What this means for provenance: OptiQ's
  `optiq/runtime/mtp/` tree is vendored MTPLX lineage — see §7.]
- But **head presence is not uniform across our formats**: only the OptiQ pair (sidecar) and
  JANG_4S (embedded) have heads; oQ4/oQ4e/35B-oQ4 do not. A "format axis" that walks
  {oQ4, oQ4e, JANG_4S, OptiQ} on MTPLX simultaneously walks "has MTP / has no MTP", which is a
  second variable. The honest splits:
  - **MTP-on format cells** can only use JANG_4S and the OptiQ pair — so a format sweep with MTP
    on is at most 2–3 cells, and its "format" interpretation is weak (one JANG artifact, one
    vendor's OptiQ recipe).
  - **AR format cells** (MTP off / `--no-mtp`) can use all of them, but then the runtime's product
    identity (native MTP) is switched off, and the cell measures a trunk-serving implementation
    whose family support for these quant patches is unverified.
  - **MTPLX's own packs** load the head for sure, but they are a *different artifact*, not a
    different format of the same artifact. Using them in a runtime-axis column varies the artifact
    with the runtime.
- The `RepublicOfKorokke` no-index refusal and the oQ4e/35B-oQ4 silent degrade are exactly the
  class of failure AGENTS.md insists on surfacing: the first is loud (good), the second needs the
  load-log half of the depth claim (a warning line, `"declares MTP layer(s) but ships no MTP
  weights; serving autoregressive"`, `runtime.py:824-828`). [VERIFIED(source)]
  [INFERRED: a MTPLX depth pin must be gated by a real load probe on the artifact, mirroring
  `runtimes.vmlx_mtp_refusal` / `runtimes.optiq_mtp_refusal` — never by the config's declaration.]

---

## 4. Published speed claims

The order asks for method, hardware, model, and independent-reproduction status for each. The
common method line first: MTPLX's benchmarks page states all first-party numbers are "single
stream on a MacBook Pro M5 Max with 128 GB, fans pinned, sampled at the model's own sampler", and
its Notes say: **"One chip. Everything first-party is an M5 Max with 128 GB… MTPLX has published
no M1, M2, M3 or M4 numbers of its own."** [CLAIMED(vendor), but the constraint is vendor-stated:
`mtplx.com/benchmarks/`, read 2026-10-06]

| Claim | Source, date | Method / hardware / model | Independently reproduced? |
|---|---|---|---|
| **2.24x** — 63.056 vs 28.156 tok/s | mtplx.com/history; first public number, 6 May 2026 | M5 Max, temp 0.6/top-p 0.95/top-k 20, Qwen 3.6 27B, depth 3 | No; repeated by vendor and by DevoxxGenie as the author's number |
| **2.69x** — 81.74 vs 30.37 tok/s | 2 Jul 2026 record, raw logs published | M5 Max, 192-token coding bench, thinking off, temp 0.6, fans verified 7,821–7,830 RPM, twin runs 81.74/81.73, Qwen 3.6 27B Optimized Speed, depth 3 | No third-party run found; vendor's own "raw logs" page is the only receipt |
| **2.3x / 2.3x / 3.0x** vs the same pack without MTP | 2.9.0 pack table, 20 Aug 2026 | Qwen 3.8 27B Optimized Speed / Bare / Quality, 46.8 / 49.9 / 39.2 tok/s, quantized draft heads | No |
| **"Twice as fast on the 4-bit packs, up to 3x on the 8-bit Quality pack"** | FAQ, current | Summary of the above | No |
| **125.8 tok/s** — one OpenCode request | 2.11.3, 16 Sep 2026 | M5 Max, 1,301 tokens generated, 18,539-token prompt with 18,364 from cache, depth 3 | No; this is a warm-cache, one-request best, not a repeatable lane |
| **81.74 / 79.3 / 61.8 / 50.3 tok/s** ladder | 2.11.3 benchmarks | Qwen 3.8 Flash-Next, 9k / 109k / 200k contexts | No |
| **227.8 tok/s** — 1.71x over 133.6 plain | 2.2.0, Qwen 3.5 4B, depth 3 | M5 Max | No |
| **145 tok/s** — Qwen 3.6 35B-A3B, depth 2 | 2.2.0, M5 Max | vs 132 at depth 3 | No |
| **"1.6x on a Mac mini; up to 2.24x on Qwen 3.6 27B"** | DevoxxGenie blog, 9 Jul 2026, by Stephan Janssen | Integration review; the 2.24x is attributed to the MTPLX author; the 1.6x phrasing has no machine listed | Partially: an independent project reviewed and used it, but the numbers quoted are the vendor's |
| **23% faster than oMLX** | YouTube, Joe Maddalone, "Run MLX LLMs 23% Faster on a Mac with MTP", 15 Jun 2026 | Description (via search snippet): "Can MTP actually make MLX models faster? In this video, I compare oMLX against MTPLX… head-to-head on Apple Silicon." Video page fetch returned no description text; `?sub_confirmation` boilerplate only. The title's 23% is the claim. | Community demonstration, not replicated here; the full measurement protocol was not retrievable in this pass |
| **oMLX 63.3 vs MTPLX 65.2 / 58.7 tok/s** — oMLX sits between MTPLX's two 27B rows | MTPLX's own compare + benchmarks pages, 15 Aug 2026 night | Both on MTPLX's M5 Max, same task, official Qwen 3.8 sampling; oMLX 0.5.7 on its own 4-bit MTP quant reads 63.3; MTPLX 2.7.0 reads 65.2 (Qwen 3.8 27B Bare Speed) and 58.7 (Optimized Speed); the same page's Qwen 3.6 27B Optimized Speed V2 row reads 59.9–60.1 | Vendor's own measurement, and it keeps a row where the other engine beats one of its packs. This is the honest counterweight to the 23% video |
| **oMLX 53.3 / 72.1 tok/s** — Weschera README | Third party, Mac Studio M4 Max, temp 0, thinking off, 320 tokens, oMLX 0.6.3rc2 ANE prefill, MTP k=3, Qwen 3.8 27B | Cited by MTPLX's compare page | Third-party, but no MTPLX arm on the same machine |
| **MTPLX 55.4 vs llama.cpp MTP 29.7 vs MLX plain 25.7** | Mirai Labs' public board, 1 Sep 2026, M5 Max | Quoted by MTPLX's FAQ | Third-party numbers; the FAQ quotes them |
| **MTPLX 102.0 vs mlx-serve 92.5** (exact decoding, Flash Next) | mlx-serve's own M5 Max table, quoted by MTPLX's compare index | Other engine's own comparison | Third party, opposite direction of marketing (their table) — but not an MTPLX run |
| **18.3 tok/s on M4 Pro 48 GB** — vs llama.cpp MTP 10.5, baseline 7 | vinoth12940 blog, 19 May 2026, MTPLX v0.3.6, Qwen 3.6 27B Optimized Speed, depth 3, temp 0.6/top-p 0.95/top-k 20, reasoning off | M4 Pro, LAN wiring to Hermes | **Independent run, same-machine, published method** — the strongest third-party reproduction located; one machine, one early version |
| **1.31x / 1.42x decode** — forged MiMo-7B-RL on an M3 Max | Stuart Rowlands blog, 5 Sep 2026, contributor | "both my own runs on one machine with fans pinned and plain decoding measured in the same session"; 4-bit body, bf16 sidecar, 2048-token long-code prompt | **Independent contributor measurement**, and deliberately modest (not the vendor's headline scale) |

**Reading the claim landscape:**

1. **Every vendor headline is one machine** (M5 Max 128 GB) with the vendor's own packs, and the
   vendor says so. The 2x–3x multiplier, where it is precisely stated, is *against the same pack
   with MTP off* (2.3–3.0x in the 2.9.0 table), or against that pack's plain decode in a specific
   lane (2.69x record). It is not a cross-runtime multiplier except in the comparison rows.
   [VERIFIED(source) for the statements; INFERRED for the framing]
2. **Independent reproductions exist and are directionally consistent but host-specific**: the
   M4 Pro run (2.6x over its own baseline), the M3 Max forged-model runs (1.31–1.42x), and the
   community videos. None reproduces the headline 125.8 / 81.74 numbers. [INFERRED]
3. **The 23%-vs-oMLX figure is contested by the vendor's own page**: on one same-night run oMLX
   0.5.7 beat MTPLX 2.7.0 (63.3 vs 59.9–60.1) at official Qwen sampling, while MTPLX's Bare Speed
   pack read 65.2 on the same night. The honest summary is *"the two engines trade lanes on M5
   Max; neither has an independent multi-machine, multi-lane comparison"*. [VERIFIED(source) for
   the numbers; INFERRED for the summary]
4. **asiai lists MTPLX as a supported engine** — detection via `owned_by: "mtplx"` in `/v1/models`,
   no fixed default port, rich `/health` (`{"ok": true, "generation_mode": "mtp", …}`), and states
   "Model format: MLX". That page is an *integration* claim, not an independent speed result; it
   says to run `asiai bench --engines mtplx` for comparison. [CLAIMED(vendor of asiai) — asiai.dev,
   22 Jul 2026]
5. The **vendor's own stated restriction** is the one to carry into our tables: interleaving,
   lanes ("Burst / Chat / Coding / Long answer / Agent context / Rewrite"), and "a number is only
   comparable to another number in the same lane". [CLAIMED(vendor), `mtplx.com/benchmarks/`]

---

## 5. Accuracy / exactness claims

The vendor's position, as published: "MTPLX accepts a drafted token with probability min(1, p/q)
and resamples rejected positions from the residual (p − q)+, the Leviathan–Chen construction,
which preserves the model's distribution at any temperature. Output is verified bit for bit
against single-token decoding… every published speed was measured at the sampler the model ships
with. MTPLX has never had a greedy-only path." [CLAIMED(vendor): `mtplx.com/faq/`, read
2026-10-06]

What the code shows (already established in the sibling document, restated here because this
section is where a reader will look for it):

- The accept rule `min(1, p/q)` and the residual resample exist as one shared module
  (`sampling.py:295-339`), and the production loops call it — **at T>0**. [VERIFIED(source)]
- **At T=0 the production loop branches before the residual machinery**: `target = argmax;
  accepted = draft == target; correction = target`. The committed token is the verify stack's own
  greedy token. [VERIFIED(source): `generation.py:9882-9888`, `:10004-10010`]
- The in-tree caveat undermines "bit for bit": the turbo verify kernels "are not bit-exact versus
  stock kernels (different accumulation order)… Do not use for bit-exactness QA", and the guard
  that would force stock kernels in greedy verify is **off by default** (it "never delivered
  MTP==AR greedy identity (cross-M frame flips survive stock kernels) and cost 5-21% greedy
  decode"). [VERIFIED(source): `docs/turbo-verify.md:29-36`; `attention_context.py:99-113`]
- Vendor evidence for the sampled path is "a thousand four-token draws… matching within the plain
  path's own split-half noise", on two packs, at T=1/top-p 0.95/top-k 20. [CLAIMED(vendor):
  `README.md:34`, FAQ; the "eight exactness defects found in its own engine, each with a test that
  pins it" in 2.11.3 is the project's own quality signal — `mtplx.com/history/`]
- The vendor's own release notes record exactness **defects being found in its engine** (2.11.3:
  "fixes eight exactness defects found in its own engine"). That is a healthy process signal and
  also a reminder that the exactness claim is a property of a *pinned version*, not of the
  product name. [CLAIMED(vendor), `mtplx.com/history/` and the 2.12.2 changelog; VERIFIED(source)
  for the changelog text]

**Harness reading (INFERRED):** the coherence gate applies unchanged; "exact at any temperature"
is a statement about the sampler law for a given build, and at T=0 MTPLX is greedy-faithful to its
own verify stack, not guaranteed token-identical to its own AR path or to any other runtime's
greedy stream. No accuracy scoring in v1 (AGENTS.md), so no MTPLX accuracy cell exists to run;
what a depth cell needs is the **acceptance receipt** that the head actually drafted (the
unverified marker list in the architecture doc §12.7), because a head that attaches but drafts
against a mismatched convention runs at ~0% acceptance while reporting success (`mtp_patch.py`
comment at the norm-heal, and the #306 policy).

---

## 6. MTPLX versus the MTP the harness already measures (OptiQ, vMLX, oMLX)

### 6.1 What the harness measures today

One pin drives all of it: `mtp_depth` `{off,1,2,3}` (`ohyesmlx/runtimes.py:1588-1650`), with
per-runtime refusal gates and per-runtime log half:

- **vMLX**: `--native-mtp-depth N --native-mtp-depth-policy fixed` plus
  `VMLX_NATIVE_MTP_AR_SAFETY=0 VMLX_NATIVE_MTP_AR_REENTRY=0`, refused on artifacts whose heads the
  runtime will not wire (`runtimes.vmlx_mtp_refusal`), and verified from the log
  (`Vmlx.mtp_depth_missing`). The fixed rerun: **depth 1 buys nothing, depth 3 costs 18%** on
  JANG_4S; the night ladder was voided because the depth was not held without the env pair
  (`docs/research/2026-09-25-mtp-depth-sweep.md:1-51`). [VERIFIED(source)]
- **OptiQ**: `--mtp --mtp-depth N`, gated by `runtimes.optiq_mtp_refusal` against
  `mlx_lm_extra_tensors.mtp_file` + `mtp_num_hidden_layers` + the sidecar's existence; the 4B/35B
  OptiQ depth cells in the 2026-09-25 sweep produced no number (engine built on first request; the
  4B's cells printed no ready line). `runtimes.Optiq.request_seed` overrides the harness's
  no-seed rule for `mtp_depth` 1/2/3, because that engine exists only on the seeded path
  (`docs/runtimes/optiq.md:1317-1326`). [VERIFIED(source)]
- **Osaurus**: MTP off only, and only through host settings (`runtimes.py:2108-2131`).
- **mlx-lm**: refuses any depth (`runtimes.py:1977-1986`).
- **oMLX**: MTP is a per-model monkey-patch; `docs/runtimes/omlx.md` §8.8 holds the details.
  [VERIFIED(source) for the shape]

### 6.2 The lineage problem: OptiQ's MTP tree is MTPLX's code

OptiQ's tree contains `optiq/runtime/mtp/` with its own `server/openai.py` whose module string is
`mtplx.server.openai`, plus `mtp_patch.py`/`artifacts.py` copies; our own runtime doc says the
`mtplx.server.openai` module cannot resolve in that install and the tree is "unreachable"
(`docs/runtimes/optiq.md:118-142`, `:1364-1375`). The OptiQ packs carry
`mtplx_mtp_quantization` blocks — a name only MTPLX's code reads (`mtp_patch.py:121`, `:347`) —
and their sidecars are byte-exact matches to MTPLX's canonical key sets (§3.1). [VERIFIED(source):
local artifacts + MTPLX constants]

**Consequence for one-variable discipline (INFERRED):** "MTPLX vs OptiQ MTP" on an OptiQ pack is
a comparison of the same MTP *concept* through two engines that share code ancestry and the same
sidecar format — which makes it a *runtime* comparison (still one variable: the runtime), but the
result's interpretation changes: a difference is OptiQ's fork plus its serve path versus MTPLX's,
not two independent MTP implementations. vMLX is the independent implementation (its own
`native_mtp.py`, adaptive policy, safety valve). The cross-check value of a MTPLX column is
therefore greatest against:

- **vMLX on JANG_4S** — if MTPLX loads it (§3.2) — because both runtimes would be driving the same
  embedded heads from the same artifact with fixed depth; and
- **OptiQ on the OptiQ packs** — same artifact, same sidecar, to isolate the engine.

### 6.3 What an MTPLX cell would be comparable to under the one-variable rule

An MTPLX cell is **not** comparable to the published MTPLX benchmarks: those are M5 Max with
MTPLX's own packs (different hardware class, different artifact). It is comparable to:

- the harness's existing depth ladders, if it runs one of the same artifacts at the same depths
  with cache/thinking/sampler pinned; and
- other runtimes on the same artifact and depth.

The seed wrinkle is real and must be recorded per row: OptiQ's MTP path forces a seed
(`runtimes.Optiq.request_seed`), MTPLX is seedless at T=0 (greedy-inert per its own resolution
order), so an OptiQ-vs-MTPLX pairing at depth is *not* identical in the request body. The harness
already treats the seed as a recorded per-runtime pin rather than a shared constant. [VERIFIED
(source): `runtimes.py:1671-1700`; architecture doc §6]

---

## 7. Why people pick it over oMLX (and when they don't)

The two projects are entangled, not rivals in a vacuum:

- oMLX has **loaded MTPLX-format packs since 11 May 2026** and its **Lightning MTP runs on MTPLX
  verify-shape Metal kernels** — its README credit is quoted on MTPLX's press and compare pages:
  "Lightning MTP's verify-shape Metal kernels are powered by MTPLX by Youssof Altoukhi, which also
  inspired the depth-k pipeline." [CLAIMED(vendor) quoting oMLX; corroborated in kind by the
  architecture doc's NOTICE read]
- MTPLX's compare page states what oMLX does well honestly: continuous batching server, SSD
  caching, 21,371 stars (3 Sep 2026), and the 15 Aug same-night win quoted in §4. [CLAIMED(vendor)]

The dividing lines the sources support:

- **Product shape**: MTPLX is a Mac app + CLI sharing one server (`mtplx start` attaches to the
  app's loaded model); oMLX is a continuous-batching server. If you want an app and an agent
  session story (cache restore in ~2 s at 100k, dead-time fixes at 2.11), MTPLX; if you want a
  server with concurrency, oMLX. [CLAIMED(vendor) for MTPLX's framing; CLAIMED(community) for
  the review's]
- **The "no external drafter" property**: DevoxxGenie's review singles this out as the reason to
  pick MTPLX — "No second model, no extra memory, no separate download" — and notes it "will
  refuse to run an incompatible model rather than silently fall back to slow decoding, which I'd
  take over the alternative every time". [CLAIMED(community): DevoxxGenie blog, 9 Jul 2026]
- **Community traffic** shows both directions over time: Reddit threads recommending MTPLX in
  July; a same-author follow-up video by 13 Jul 2026 titled "New oMLX 57% Faster on a Mac?" (the
  oQ4-MTP-vs-standard-MLX comparison, a different claim than MTPLX-vs-oMLX); posts about switching
  fan tools from MTPLX to oMLX while keeping ThermalForge. [CLAIMED(community): search results
  summarised; individual posts not re-read in full]
- One search snippet attributed to `jundot/omlx` issue #2781's discussion reads "For Qwen3.8-27B
  on M3 Max 128GB, oMLX v0.6.2 is decisively faster than MTPLX v2.9.0 at 16K…". I fetched the
  issue body (it is about ANE prefill, not MTPLX) but the merged discussion comments did not
  render in the fetch, so I could not verify the sentence in place. Treat as
  **CLAIMED(community), unverified quote** — listed in §11. [INFERRED risk: it matches the
  general pattern that oMLX's ANE prefill and batching lead at long context]
- Vendor-vs-vendor on the same page: MTPLX's own compare table keeps a row where **oMLX beats one
  MTPLX pack** (63.3 vs 58.7 Optimized Speed — MTPLX's Bare Speed still leads at 65.2, and the
  3.6 V2 row reads 59.9–60.1), and MTPLX's win rows are on its own packs on its own machine. The
  defensible reading: **MTP is not a single-engine moat anymore** — oMLX has MTP (on MTPLX
  kernels), llama.cpp has MTP (May–Aug 2026), mlx-lm's MTP PR is still open. MTPLX's differentiator
  has narrowed to the app/agent experience, exactness discipline, and being first.
  [INFERRED, from the dated records on mtplx.com/history + mlx-lm PR status]

---

## 8. Known issues and bugs, from the tracker

Open-issue census read via the GitHub REST API on **2026-10-06**:
`https://api.github.com/search/issues?q=repo:youssofal/MTPLX+type:issue+state:open` returned
**17 open issues** (the architecture doc's "16 open" at its read is now 17 — issue #601 was opened
2026-10-06). The relevant ones for a harness cell, newest first:

| # | Title (abridged) | Why it matters to us |
|---|---|---|
| 601 | Web chat can't paste images / no markdown | Cosmetic; not harness-relevant |
| 592 | **2.12.2 one-copy: "QSA pooled hold N rows; resizing to M rows would cut them" after a cache-missing turn** | Long warmup/multi-turn cells on Flash-Next flaky; fails loud (engine error), not silently wrong. Root cause analysis in the issue; local patch proposed |
| 591 | **2.12.2 one-copy: OpenCode gets 0% cache hits** (snapshot drops MTP history) | Agent-style sessions lose their whole advantage in 2.12.2; the issue's workaround (`MTPLX_OPENCODE_TOOL_HISTORY_LIVE_FRONTIER=1`) then trips #592 |
| 589 | Feature: view full in-flight request context | Tooling gap |
| 587 | ThermalForge integration: stale socket path, sudo no longer needed | Fan control integration drift; our thermal policy lives in the runner, not the runtime, but tune's fan step is affected |
| 586 | Request for the long-session settings used in benchmarks | Vendor benchmark reproduction pack partially unavailable |
| 584 | **OpenCode User-Agent → tool-call arguments come back as `<parameter=…>` strings after an image turn (2.12.2)** | Real agent-path corruption; 10/10 malformed with the UA header; a coherence-adjacent failure that would be caught by our gate but should not be hit in a text-only cell |
| 583 | Unclosed `<think>` after a tool result → empty content when tools are declared | Reasoning/content split failure in agent shapes; not our single-shot cells |
| 546 | **Flash-Next host-side memory grows ~5 GiB/hour during streaming agent workloads, not reclaimed by `/admin/cache/clear`** | Directly relevant to long cells and to `footprint -p` readings: a multi-hour MTPLX cell on Flash-Next would drift; keep cells short, sample peak early, or avoid Flash-Next |
| 521 | No recommended model for 8 GB M1 | Packaging, not harness |
| 506 | **Packed-GQA verify lane never dispatches at long context; paged lane performs zero calls** | A perf bug on 2.11.3 turbo: depth-dependent KV traffic scaling with draft depth; explains depth-3 long-context decay; measured +30%/+39% recovery estimate. Independent, methodical, unresolved |
| 499 | **TPS drops significantly on M5 Pro for long-running agentic tasks** (6–7 tok/s; continuation of #305) | Same symptom domain as #506; if a depth cell runs long agent turns it may measure the bug, not the pin |
| 494 | `brew` post_install can't reach a private PyPI index | Install friction only |
| 491 | API key required when hosting beyond localhost | Server default; our cells are loopback |
| 422 | **GPU watchdog kill past ~90–104K context on M2/M3 with session-bank restore** (`kIOGPUCommandBufferCallbackErrorImpactingInteractivity`) | Long-context cells on M2/M3-class machines; our host is M-series of some class — check chip before any long-context MTPLX cell |
| 400 | **Flash-Next on M2 Max 96 GB: turbo kernels crash (threadgroup 1024 > 896), `committed` MTP history policy stalls ~1.5 s/verify round (4–5 tok/s)** | Pre-M4 hardware: MTP net-loses to AR past ~2k context on this pack; the issue's author ships AR. A warning for any non-M5-class MTPLX MTP cell |
| 265 | Batch=2 slower than single request (0.41x) on continuous batching | Concurrency cells only; MTPLX's default is serial (architecture doc §4) |

Also verified outside the open list:

- **#306 policy**: an MTPLX-branded pack must keep the MTP head as a standalone sidecar; a trunk
  with embedded `mtp.*` and absolute norm gains double-shifts every trunk RMSNorm under mlx-lm's
  presence-keyed sanitize and "the model still loads and generates — with acceptance collapsed to
  a few percent — so it benchmarks as 'MTPLX models are slow' instead of failing". MTPLX's loader
  now refuses such a trunk with the q-norm check. [VERIFIED(source):
  `docs/model-compatibility.md:22-34`; `runtime.py:1263-1302`]. This is precisely why §3.2 could
  predict JANG_4S's norms: the refusal exists to catch the case, and JANG_4S's stored deltas land
  on the healthy absolute value after the one legitimate shift.
- **Forge's head-extraction gap**: only `mtp.*` / `language_model.mtp.*` layouts were extracted;
  DeepSeek/GLM appended-layer heads and MiMo's `mtp_layers.*` namespace extracted zero keys while
  inspection still said a head was present (PR #442 open, per its author). Even MiMo-7B-RL needed
  three further fixes to complete a forge build, after which it measured **1.31x / 1.42x** on the
  contributor's M3 Max. [CLAIMED(community): stuartrowlands.com, 5 Sep 2026 — the contributor's
  own account, not a vendor statement]
- **Release-note bug classes**: 2.12.1's memory guard refused ordinary prompts on 8/16/32 GB Macs;
  2.12.2 fixed it; the mlx pin note says 0.32.3 "is not bit-identical to 0.32.2 on Flash-Next".
  [VERIFIED(source): `CHANGELOG.md:30-47`; `pyproject.toml:29-36`]

**Reading for the harness:** the loud failures (#592, #306 refusal, the QSA error) are acceptable;
the silent ones (#546 growth, #506 dead lane, #499 decay) are exactly what the harness's own
drift and log-half discipline exist to catch. The tracker is dense with reproducible, well-written
reports — a positive signal about the project's debugging culture, and a negative signal about how
much of the product changes week to week. Pin the version per row and record it.

---

## 9. Maintainer, cadence, bus factor

- **One person, by design.** Youssof Altoukhi (`youssofal`), company YOYO STUDIOS INC., built the
  first commit 27 Apr 2026 and shipped v0.1 on 2 May; the repo's contributor list shows
  **`youssofal` 1,672 contributions** and then `davidtai` 143, `PhilipJohnBasile` 24, `jvmenen`
  20, `dependabot` 17, `Cyb3rb1ade` 17, `stooit` 14, `daniel-farina` 9, and a long tail of 1–8
  contribution names (GitHub contributors API, read 2026-10-06).
  [VERIFIED(source): `https://api.github.com/repos/youssofal/MTPLX/contributors?per_page=100&anon=1`]
- **Cadence**: 40 releases between 1.0.0 (10 Jun 2026) and 2.12.2 (3 Oct 2026); 2.11.3 → 2.12.0 →
  2.12.1 → 2.12.2 within 17 days at the end. The press page claims 51 tagged releases from May to
  4 Sep 2026. [VERIFIED(source): `CHANGELOG.md` headings; CLAIMED(vendor): press page]
- **Adoption** (vendor-measured, 3 Sep 2026): 2,004 stars (now 2,526 per the architecture doc's
  read), 148 forks, 138,089 HF downloads / 30 days across all packs, 61,275 for the 27B Optimized
  Speed alone. [CLAIMED(vendor): `mtplx.com/press/`; the star count is now stale either way]
- **External contribution is real but thin and recent**: the forge head-extraction work is one
  community contributor's (Stuart Rowlands, PR #442); official contributors appear in the
  changelog by name (jvmenen, davidtai, bpmforge, qshiftedx, ProducerGuy/ThermalForge).
  [CLAIMED(community) + VERIFIED(source): `CHANGELOG.md:25-120`]
- **Bus-factor consequences for a harness dependency (INFERRED):**
  - Everything needed to run a pinned cell is Apache-2.0 source + a pip/venv install; the harness
    already vendors runtime *source* for two other runtimes and pins exact versions. A frozen
    MTPLX install keeps working if the project stops, minus new model families.
  - The **artifact ecosystem** is the fragile half: `Youssofal/*` packs, Forge's trained adapters,
    and the "recommended model per memory class" logic all come from the maintainer. The harness
    can sidestep this by measuring MTPLX on *our* OptiQ/JANG artifacts (§3) — which is also the
    one-variable-correct choice.
  - The **attribution requirement** (`NOTICE`) survives the project; any published MTPLX-based
    results should carry "MTPLX by Youssof Altoukhi" per its terms.
- The maintainer's own project conventions are unusually evidence-forward (raw logs published,
  `mistakes/` postmortems in-tree, exactness defects fixed with pinning tests, a compare page that
  keeps a losing row). That is the strongest argument that the numbers in §4, though un-replicated
  here, are not fabricated. [INFERRED]

---

## 10. Verdict, in one paragraph

MTPLX is loadable-adjacent for the harness's **existing** artifacts in exactly two clean cases —
the two mlx-community OptiQ bundles, whose MTP sidecars are byte-exact matches to MTPLX's canonical
prequantized key sets — and plausibly a third (JANG_4S, embedded head, norm arithmetic verified)
pending one load. It is an AR-only runtime for LFM2.5, a warn-and-degrade runtime for oQ4e/35B-oQ4,
and a loud refusal for the index-less oQ4. Its published speed claims are single-machine
(M5 Max 128 GB) and pack-specific, with real but host-specific independent corroboration and a
competitive oMLX lane holding the other side of the scoreboard. The engineering culture is strong;
the bus factor is one person with a long tail. It is a **runtime-axis** candidate on an artifact we
already own — not a format-axis object, and not a drop-in column on its own packs.

---

## 11. Unverified items

1. **No MTPLX process was started and no model loaded** (order constraint). Every "will load /
   will degrade / will raise" statement in §3.2 is a source-level prediction over verified
   config/tensor bytes, not an observation. The load probes are the coordinator's first step.
2. **The OptiQ sidecar contract beyond geometry.** The sidecars have no `mtplx_mtp_contract` block,
   so `hidden_variant`, `concat_order` and `mtp_position_mode` take MTPLX's defaults
   (`post_norm` / `embedding_hidden` / `cache`, `mtp_patch.py:52-64`). If OptiQ's builder chose a
   different variant, the head can attach, pass validation, and draft at ~0% acceptance (the
   in-tree heal comment names exactly that silent case). A depth cell needs the acceptance receipt,
   not just a successful load.
3. **JANG_4S loadability under mlx-lm**: the tensor prefix (`model.language_model.*` vs the
   `language_model.model.*` the other packs use) and JANG's quant bookkeeping are untested against
   `mlx_lm.utils.load` at the pinned range; vMLX has its own `jang_loader` for a reason.
4. **The oQ4 no-index refusal prediction** (`MTP injection failed`) and the `--no-mtp` AR fallback
   were both read from code, not observed.
5. **The "head drafted" receipt** (which log line / stats field proves the MTP head ran in a cell)
   is still not pinned — carried over from the architecture doc's list; it is the gate any depth
   cell needs against problem #2.
6. **Every speed number in §4 is read, not reproduced.** No MTPLX benchmark ran on this host.
7. **The 15 Jun 2026 YouTube video's measurement details**: the title's "23%" and the
   description snippet ("I compare oMLX against MTPLX… head-to-head") were retrieved; the watch
   page returned no readable description or transcript, so machine, prompt, sampling and version
   are unknown. Not to be quoted as a method.
8. **The oMLX-vs-MTPLX sentence in `jundot/omlx#2781`'s discussion** was seen only as a search
   snippet; the comment text did not render in the fetch. Treated as an unverified community quote.
9. **MiMo/Gemma4/Bonsai lanes** were read from docs/packs only; no artifacts for them exist on
   this host and none were downloaded (order constraint).
10. **asiAi numbers**: the engine page is an integration reference; no asiai-measured MTPLX results
    were found on it. The "bench with `asiai bench --engines mtplx`" path is a future comparison
    tool, not a source of results.

## 12. Sources index

- **Source (shared clone, revision `9882703`, read 2026-10-06)**: `README.md` (esp. :19-34,
  :104-137, :181-189, :265-276), `CHANGELOG.md` (:25-120), `NOTICE`, `LICENSE`, `pyproject.toml`,
  `docs/architectures.md`, `docs/model-compatibility.md`, `docs/turbo-verify.md`,
  `docs/concurrency.md`, `docs/server.md`, `mtplx/constants.py`, `mtplx/artifacts.py`,
  `mtplx/mtp_patch.py`, `mtplx/qwen3_5_mtp_patch.py`, `mtplx/runtime.py`,
  `mtplx/backends/registry.py`, `mtplx/backends/descriptors.py`, `mtplx/commands/forge.py`,
  `mtplx/compressed_tensors.py`, `mtplx/hf_loader.py`.
- **This repo**: `AGENTS.md`; `ohyesmlx/runtimes.py`; `docs/runtimes/optiq.md` (§1.4, §9.2);
  `docs/runtimes/vmlx.md` (§7.4.1–7.4.2); `docs/research/2026-09-25-mtp-depth-sweep.md`;
  `docs/research/2026-10-06-mtplx-architecture.md`; the harness's mlx-lm 0.31.3 venv
  (`mlx_lm/models/qwen3_5.py:307-332`).
- **Local artifacts** (this host's HF cache, snapshots as named in §3.1): the seven harness bundles
  plus the five LFM2.5 variants listed there.
- **Web**: `mtplx.com/benchmarks/`, `/compare/`, `/compare/mtplx-vs-omlx/`, `/faq/`, `/history/`,
  `/press/`, `/about/`; `genie.devoxx.com/blog/mtplx-local-llm-apple-silicon`;
  `asiai.dev/engines/mtplx/`; `vinoth12940.github.io/.../genai-20260519-local-mtp-speculative-decoding/`;
  `stuartrowlands.com/posts/mtp-heads-nothing-loads`;
  `youtube.com/watch?v=jU02xG69jXI` (title + snippet only);
  GitHub REST API: repo, contributors, issue search (URLs inline in §8–§9).

---

## 13. Which axis would an MTPLX cell vary?

**The axis is the runtime**, on an artifact the harness already owns, with `mtp_depth` as the
pinned factor walked identically in every column. The concrete proposal, ordered by what the
evidence above supports:

### Cell set A — runtime axis, MTP on, one artifact (the entry table)

- **Artifact:** `mlx-community/Qwen3.5-4B-OptiQ-4bit` (snapshot `6cb5bdf…`) — the only harness
  bundle where a MTPLX MTP head is provably well-formed (§3.1) **and** OptiQ can drive the same
  sidecar. LFM2.5 has no head; oQ4/oQ4e have no head; JANG_4S is pending a load.
- **Columns (one variable: the runtime):** `optiq 0.5.x` and `mtplx 2.12.2`, each at
  `mtp_depth` `1`, `2`, `3` (and `off` as the AR control inside each column).
- **Pins:** `cache_state` off (MTPLX: `--ssd-session-cache off` plus the RAM-bank control from the
  surface order); thinking pinned and recorded per runtime family (architecture doc §7);
  temperature 0; the *request seed recorded per row* — OptiQ's MTP engine needs the seed
  exception (`runtimes.Optiq.request_seed`), MTPLX is seedless, and a cross-runtime depth pairing
  is therefore not request-body-identical. Write that in the conditions block, not a footnote.
- **What it can claim:** "On `Qwen3.5-4B-OptiQ-4bit` at depth N, MTPLX and OptiQ decode at X and
  Y." What it cannot: anything about vMLX, about oQ4 formats, or about MTPLX's own packs.
- **Acceptance before the table counts:** the MTPLX column must carry the "head actually drafted"
  receipt (unverified item #5) — a successful load is not proof, per the silent-0%-acceptance
  failure class.

### Cell set B — the depth ladder inside MTPLX (the comparable-to-vMLX shape)

- **Artifact:** the same OptiQ 4B (or JANG_4S once it loads).
- **Cells:** MTPLX × `mtp_depth {off, 1, 2, 3}` — one variable (depth), runtime fixed, artifact
  fixed. This is the shape that already exists for vMLX on JANG_4S, and it is the shape the
  architecture doc's depth-cap reading (qwen3_5 family range to verify at pin time) applies to.
- **Contrast value:** the published vMLX ladder found depth 1 buys nothing and depth 3 costs 18%
  on JANG_4S. MTPLX's product default is depth 3 (`cli.py:3665`); a MTPLX ladder on JANG_4S is
  the first cross-engine test of whether that default survives this hardware — *if* the JANG_4S
  load probe passes. If it does not, the ladder runs on the OptiQ 4B and is not comparable to the
  vMLX ladder at all (different artifact, different head source).

### Cell set C — the cross-engine artifact bridge (only if JANG_4S loads)

- **Artifact:** `JANGQ-AI/Qwen3.5-4B-JANG_4S`; **columns:** `vmlx 1.6.x` (existing pinned config:
  `--native-mtp-depth N --native-mtp-depth-policy fixed` + the AR-safety env pair) and
  `mtplx 2.12.2` (`--depth N --generation-mode mtp`), depths `off/1/2/3`, cache off.
- This is the only artifact where both runtimes might drive the **same embedded head** without a
  format change — the single cleanest runtime-axis MTP comparison available. It depends entirely
  on unverified item #3; run the load probe first, and if it fails, say so and stop (it is a
  finding about MTPLX's artifact contract, not a reason to swap in a Youssofal pack).

### What NOT to run (and why)

- **Do not drop a `Youssofal/*` pack into a runtime-axis column.** Runtime + quantization format +
  conversion provenance + chat template move together; the cell cannot attribute anything
  (§2, opening of §3.3).
- **Do not compare MTPLX-on-its-pack to vMLX-on-JANG_4S.** Two variables, two artifact lineages.
- **Do not run MTPLX depth cells on the oQ4/oQ4e/35B-oQ4 bundles** without a prior load probe and
  the log half: one raises, two degrade to AR with a log warning
  (`runtime.py:820-828`), and a depth cell that quietly served AR is exactly the failure the
  harness's depth-pin discipline exists to prevent.
- **Do not add an LFM2.5 MTPLX cell as an "MTP" cell.** The family has no MTP head; it can only be
  an AR column, and MTPLX's AR quality for that family's quant patches is untested.
- **Do not quote the vendor numbers in a table with ours** unless the lane, chip, pack and
  version are restated — the vendor's own benchmark page requires the lane to match for
  comparability.

### Harness prerequisites, in dependency order

1. A load probe per candidate artifact (raise/degrade/attach + receipt), mirroring
   `runtimes.vmlx_mtp_refusal` / `runtimes.optiq_mtp_refusal` — as `runtimes.mtplx_mtp_refusal`.
2. The depth-pin mapping and its log half (`--no-mtp` / `--depth N --generation-mode mtp`; the
   scheduler must be declared `serial` for a single-stream cell).
3. The cache pin: SSD session cache dir inside the per-run scratch (so `stop()` removes it),
   plus whatever the surface order finds for the RAM bank.
4. A free port — MTPLX's default 8000 collides with vMLX's, per the AGENTS.md hazard list.
5. The coherence gate and one-variable conditions blocks, unchanged.
