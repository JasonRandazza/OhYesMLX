# Phase 3 research — the small-model catalog, where each engine looks for a model, and a stdlib downloader

**Date:** 2026-10-30
**Role:** research pass for v5.0 Phase 3 (`catalog.py`, `recommend.py`, `fetch.py`). Documentation
only — no code changed, no weight file downloaded, no server started, no model loaded. The only
data bytes read were two 100-byte `Range` probes (§3.3), one of them on a `.safetensors` file, to
establish 206 semantics; every other request was metadata, a listing or a `HEAD`.
**Scope:** Jason's constraint (2026-10-29): the first catalog is models of **at most 3B
parameters**, pulled one at a time because free disk is scarce; Hugging Face as a live source comes
later (T3.5).

**Evidence labels.**

- **VERIFIED** — read from a primary source (HTTP response, shipped file, binary string table) or
  computed from one; the URL, command or path is given.
- **CLAIMED** — vendor documentation only.
- **INFERRED** — follows from something VERIFIED but is not itself observed.
- **UNKNOWN** — not established here; the probe that would settle it is named.

**This machine, 2026-10-30.** macOS 27.2, arm64. Installed engines (VERIFIED — plist / `--version` /
`__init__.py`, commands in §7): Osaurus **0.25.29**, oMLX **0.7.2**, OptiQ **0.7.8**, mlx-lm
**0.31.3** (harness venv, `~/.local/share/ohyesmlx/mlx-lm-0.31.3`), vMLX **1.6.82**. Three of the
five moved since the versions `AGENTS.md` and `docs/runtimes/*.md` were written against
(Osaurus 0.25.28→0.25.29, OptiQ 0.5.13→0.7.8, vMLX 1.6.59→1.6.82); every claim below states which
build it was read from.

---

## 0. Findings, worst first

1. **Nothing published by the tracked oQ/JANG quantizers fits the cap.** `JANGQ-AI` (82 repos,
   listed whole) publishes no artifact below 4B: its smallest is `Qwen3.5-4B-JANG_4S` (4.66B
   params) and `gemma-4-E2B-it-qat-JANG_4M` (5.12B params). `Jundot` (90 repos) likewise starts at
   gemma-4-E2B/4B. `uingei`'s author listing now returns zero repos and `uingei/Qwen3.5-4B-oQ4e`
   answers HTTP 401 (the repo this project measured is no longer public). Only **RepublicOfKorokke**
   publishes ≤3B oQ artifacts (`Qwen3.5-2B-oQ4`, etc.). A ≤3B catalog is therefore mostly
   `mlx-community` stock quants plus one RepublicOfKorokke oQ4.
2. **"3B" in a model name is not 3B parameters, and the strict cap has no 3B row.** SmolLM3-3B is
   3.075B, Llama-3.2-3B is 3.213B, Ministral-3-3B is 3.849B, gemma-4-E2B is 5.123B total ("2B
   effective"). The strict ≤3.0B set tops out at LFM2.5-2.6B (2.697B). Whether 3.08/3.21 count as
   "3B class" is a decision for Jason, not a fact.
3. **No MoE with ≤3B total parameters has an MLX checkpoint that any of the five engines can load.**
   The candidate exists on paper — `ibm-granite/granite-3.0-3b-a800m-instruct` (3B total / 800M
   active, `granitemoe`, 40 experts top-8, `config.json` VERIFIED) — but it has no MLX conversion
   anywhere on the Hub (`?search=granite-3.0-3b-a800m-mlx` and `?filter=mlx&search=granitemoe` both
   empty). The community MoE pair that a search surfaces (`allura-org/MoE-Girl_*`) answers **401**
   on the model API, i.e. is not publicly downloadable today. The only ≤3B-total family whose
   module is named for experts is `granite-4.0-h-*`, and those ship **dense**
   (`num_local_experts: 0`). The one MoE this repo has actually measured, LFM2.5-8B-A1B, is **8.47B
   total / 1B active** and therefore over the cap.
4. **The small Qwen3.5 models are vision-language checkpoints, not text models.**
   `Qwen/Qwen3.5-0.8B` and `-2B` are `Qwen3_5ForConditionalGeneration` with a `vision_config`, and
   the MLX 4-bit artifacts keep it (`config.json` has `vision_config`; the OptiQ-4bit 0.8B bundle
   ships a 201 MB `optiq_vision.safetensors`). The text path loads them — Qwen3.5-4B is the same
   shape and PASSes on mlx-lm, oMLX, OptiQ and vMLX (Osaurus has no row for the stock artifact) —
   but a "multimodal-free text model per family" rule is satisfied by
   Qwen3/LFM2.5/granite/SmolLM3/Llama-3.2, not by Qwen3.5.
5. **The Hugging Face cache is the one on-disk layout all five engines see without a copy.**
   Osaurus auto-imports `~/.cache/huggingface/hub`; oMLX appends it to its model dirs by default;
   mlx-lm and OptiQ *list the whole cache* in `/v1/models`; vMLX and the other two accept a snapshot
   path. A plain two-level `~/MLXModels/<org>/<name>` directory is second (Osaurus's model root,
   oMLX's "organized" layout, paths for the rest) and is the cheaper layout for a custom downloader.
6. **oMLX 0.7.2 does not make the per-run catalog the only model dir.** Its server calls
   `get_effective_model_dirs()` with no argument, and that function appends the HF cache whenever
   `huggingface.hf_cache_enabled` is true — the default (`settings.py:715`, `:1507-1530`,
   `server.py:2480-2481`). The harness's command (`runtimes.py:2392-2405`) does not pass
   `--no-hf-cache`, so a cell's runtime also scans the user's cache. Model ids still resolve to the
   cell's own entry, so no published number is invalidated, but AGENTS.md's "so only the cell's
   model is visible" is not what this build does. **Finding for the coordinator.**
7. **A stdlib downloader is enough, and the probes say why** (§3): `urllib` follows the 307/302 to
   the CDN and preserves `Range` (206 verified), the CDN URL is signed for exactly 3600 s, the
   sha256 to verify against is the tree listing's `lfs.oid` (the CDN `ETag` is the *xet* hash, not
   the file hash), and the anonymous quotas are 500 API / 3,000 resolver requests per 300 s. The
   only real losses are hf_xet's parallel chunk transfer (speed) and built-in retries (implementable).

---

## 1. Candidate models at or near the cap

### 1.1 Method

Every number below came from the Hub API on 2026-10-30, never from a model card's prose:

```sh
curl -s 'https://huggingface.co/api/models/<repo>?blobs=true'      # siblings[].size, safetensors, gated, cardData
curl -s 'https://huggingface.co/<repo>/raw/main/config.json'       # model_type, architectures, quantisation
curl -s 'https://huggingface.co/api/models/<base-repo>'            # base params (see the trap below)
```

**The trap:** `safetensors.total` is not a reliable logical parameter count across quantized repos.
For the mlx-community 4-bit artifacts it lands within a few percent of the base count
(`Qwen3.5-0.8B-4bit` 852,985,920 against `Qwen/Qwen3.5-0.8B` 873,438,784), but
`mitslabo/Qwen3.5-0.8B-oQ4-fp16` reports 122,983,744 for the same 0.87B model and
`mlx-community/Qwen3.5-0.8B-OptiQ-4bit` reports 752,393,024. The reason the number moves is not
established here; what is established is that it is not comparable across artifacts, so parameter
counts in the table are read from the **base** model's metadata. A repo with no public base (the
Llama-3.2 MLX conversion) is read from `meta-llama/Llama-3.2-3B-Instruct`, whose metadata is public
even though its weights are gated.

`size_bytes` is the sum of every file size in the repo's `siblings` list — tokenizer, sidecars and
README included, because that is what the disk pays. This is the same summation the existing
download-size research used (`docs/research/2026-09-15-small-model-candidates.md`).

### 1.2 The spread

The order asks for ~0.5B, ~1B, ~2B, ~3B and one MoE with small active parameters. That is the
table's shape; the `cap` column is the honest verdict against Jason's "at most 3B".

| # | repo | params (base) | format | size_bytes | cap |
|---|---|---|---|---|---|
| 1 | `mlx-community/Qwen3-0.6B-4bit` | 751,632,384 | mlx affine 4-bit, gs 64 | 351,386,061 | in |
| 2 | `mlx-community/Qwen3.5-0.8B-4bit` | 873,438,784 | mlx affine 4-bit, gs 64 | 652,029,391 | in (VL) |
| 3 | `mlx-community/Qwen3.5-0.8B-OptiQ-4bit` | 873,438,784 | OptiQ-4bit (4/8-bit mixed, 187 overrides) | 886,129,146 | in (VL) |
| 4 | `mlx-community/LFM2.5-1.2B-Instruct-4bit` | 1,170,340,608 | mlx affine 4-bit, gs 64 | 663,395,788 | in |
| 5 | `mlx-community/granite-4.0-h-1b-4bit` | 1,461,538,368 | mlx affine 4-bit, gs 64 | 833,197,077 | in |
| 6 | `mlx-community/Qwen3.5-2B-4bit` | 2,274,069,824 | mlx affine 4-bit, gs 64 | 1,749,081,927 | in (VL) |
| 7 | `RepublicOfKorokke/Qwen3.5-2B-oQ4` | 2,274,069,824 | oQ4 (4/5/6/8-bit, 41 overrides) | 1,794,528,789 | in (VL) |
| 8 | `mlx-community/LFM2.5-2.6B-4bit` | 2,697,198,592 | mlx affine 4-bit, gs 64 | 1,535,593,294 | in |
| 9 | `mlx-community/gemma-4-e2b-it-4bit` | 5,123,178,051 (2B effective) | mlx affine 4-bit, gs 64 | 3,583,088,661 | **over** (VL) |
| 10 | `mlx-community/SmolLM3-3B-4bit` | 3,075,098,624 | mlx affine 4-bit, gs 64 | 1,747,380,812 | **over by 2.5%** |
| 11 | `mlx-community/Llama-3.2-3B-Instruct-4bit` | 3,212,749,824 | mlx affine 4-bit, gs 64 | 1,824,825,759 | **over by 7%** |
| 12 | `mlx-community/LFM2.5-8B-A1B-MLX-4bit` | 8,467,856,832 (1B active) | mlx affine 4-bit, gs 64; 32 experts, top-4 | 4,782,228,614 | **over** (the only measured MoE) |

All twelve: `gated: false` (VERIFIED from the model metadata). Licenses in §5.

Why these and not others:

- **#1** is the ~0.5B slot: 0.75B total, 351 MB, pure text, `qwen3`, and it is the cheapest model in
  the set by disk. Qwen2.5-0.5B (`qwen2`) is smaller still (289,601,064 B) but two generations old.
- **#2–#3** are the same base in two formats and the pair is the format-axis test in miniature: the
  OptiQ bundle is 1.36× the size of the stock 4-bit one, and 23% of it (201,202,432 B) is a vision
  sidecar the text path never reads.
- **#5** is the only hybrid (Mamba + attention) family in the set: 40 layers, 4 attention layers,
  36 Mamba layers, so its KV is tiny and its residency is dominated by weights. It is the class
  where "KV headroom" is negligible and a fit rule that assumed otherwise would be wrong.
- **#8** is the largest strictly-in-cap artifact (2.697B).
- **#9–#11** are the "3B" names that are not 3B; **#12** is the MoE the spread asks for and the cap
  forbids.

### 1.3 Engine compatibility, and how each claim was checked

Two kinds of evidence, both read on this machine:

- **Python engines** — the module `mlx_lm.models.<model_type>.py` exists in the build the engine
  actually loads, and `mlx_lm.utils.load` resolves `model_type` to that module
  (`mlx_lm/utils.py:187-189` in the harness's 0.31.3: `MODEL_REMAPPING.get(model_type, model_type)`
  then `importlib.import_module(f"mlx_lm.models.{model_type}")`). **VERIFIED** by listing each build's
  models directory:

```sh
ls ~/.local/share/ohyesmlx/mlx-lm-0.31.3/lib/python3.14/site-packages/mlx_lm/models/   # mlx-lm 0.31.3
ls ~/Dev/tools/mlx-optiq/.venv/lib/python3.12/site-packages/mlx_lm/models/             # OptiQ 0.7.8 → mlx_lm 0.32.2
ls /Applications/oMLX.app/Contents/Resources/Python/framework-mlx-base/lib/python3.11/site-packages/mlx_lm/models/  # oMLX 0.7.2 → 0.31.4.dev132
ls /Applications/vMLX.app/Contents/Resources/bundled-python/python/lib/python3.12/site-packages/mlx_lm/models/      # vMLX 1.6.82 → 0.31.3
```

All four builds carry `qwen3.py`, `qwen3_5.py`, `lfm2.py`, `lfm2_moe.py`, `gemma4.py`,
`gemma4_text.py`, `granitemoehybrid.py`, `smollm3.py`, `llama.py` (and `ministral3.py`). **VERIFIED**
for every family in the table.

- **Osaurus** — a native Swift app with no Python. Its architecture support is the set of MLXLLM
  model classes compiled into the binary plus the `model_type` strings present in it (a string
  proves the literal ships, not which code path reads it — the same distinction
  `docs/runtimes/osaurus.md` §0 draws). **VERIFIED** by the string table:

```sh
strings -a /Applications/osaurus.app/Contents/MacOS/osaurus | grep -o -E '_TtC6MLXLLM[0-9]+[A-Za-z0-9_]+Model'
# Qwen3Model, Qwen35Model, Qwen35TextModel, Qwen35MoEModel, LFM2Model, LFM2MoEModel,
# GraniteMoeHybridModel, Gemma4Model, Gemma4TextModel, SmolLM3Model, OlmoEModel, LlamaModel,
# Phi3Model, MiniCPMModel, …
strings -a /Applications/osaurus.app/Contents/MacOS/osaurus | grep -x -E '[a-z0-9_]+' | grep -E 'qwen3_5|lfm2|gemma4|granitemoehybrid|smollm3|llama'
# qwen3_5, qwen3_5_moe, lfm2, lfm2_moe, gemma4, gemma4_text, granitemoehybrid, llama
```

A class name proves the architecture is compiled in; it does not prove a given bundle loads. Where a
family has a live row here, the table says so; the rest are **INFERRED** from class/module presence
and are marked in the footnote.

**Local evidence per family from `results/` (VERIFIED — `grep artifact_dir results/**/results.jsonl`):**

| family | live PASS rows on |
|---|---|
| `qwen3_5` | all five, but not on one artifact: Osaurus on the oQ4/oQ4e/OptiQ/JANG_4S 4B bundles; the stock `mlx-community/Qwen3.5-4B-4bit` on the other four only |
| `lfm2_moe` | all five (`mlx-community/LFM2.5-8B-A1B-MLX-4bit`, grid-moe 2026-09-16/17/24/28) |
| `llama` | all five (`brainworkup/Llama-3.1-8B-oQ4`) |
| everything else in the table | source evidence only; no row on this machine |

One observed caveat: Osaurus listed `qwen3.5-4b-4bit` in `/v1/models` but answered *"not installed or
registered with any provider"* when it was asked to serve it (`docs/runtimes/osaurus.md` §4.4.2,
2026-09-15). Its `qwen3_5` support is real (oQ4/oQ4e/OptiQ/JANG 4B artifacts all PASS), but "listed"
on that runtime is not "servable".

**JANG and the cap.** `JANGQ-AI` publishes nothing ≤3B (finding 1). `OsaurusAI` publishes small JANG
bundles — e.g. `OsaurusAI/LFM2.5-2.6B-JANG_6M` (2,491,711,617 B, `lfm2`, JANG_6M: 8-bit with 6-bit
per-tensor overrides) — and this machine has `~/MLXModels/OsaurusAI/Nanbeige4.2-3B-JANG_6M` on disk.
Those are servable by **Osaurus** (its own catalogue; `jang_config.json` read at
`docs/runtimes/osaurus.md` §8.2-8.3) and by **vMLX** (`vmlx_engine/utils/jang_loader.py`, whose
`load_jang_model` handles JANG_4M/6M and JANGTQ). For mlx-lm/OptiQ/oMLX their loading is
**UNKNOWN**: the generic loader reads `config.json`'s per-path `quantization` block
(`mlx_lm/utils.py:348-363`), but JANG's `jang_config.json` carries a tensor-quantization manifest
that "a generic loader will not reproduce" (`docs/runtimes/osaurus.md` §8.3). Publishing a JANG row
to an engine without a JANG loader risks the silent token-salad class this project exists to catch,
so a catalog must gate JANG by engine, not by model_type alone.

### 1.4 What the quantizer orgs actually publish under 3B

| org | repos | smallest ≤3B artifact | verdict |
|---|---|---|---|
| `mlx-community` | not enumerated (paged by family) | `Qwen3-0.6B-4bit` (351 MB) | the catalog's source |
| `RepublicOfKorokke` | 154 | `Qwen3.5-0.8B-oQ6/oQ8`, `Qwen3.5-2B-oQ4` | one oQ4 row in the table |
| `JANGQ-AI` | 82 | none ≤3B (smallest: `Qwen3.5-4B-JANG_4S`, 4.66B) | n/a under the cap |
| `Jundot` | 90 | none ≤3B (smallest: `gemma-4-E2B-it-oQ4e-mtp`, 5.12B) | n/a under the cap |
| `uingei` | author listing returns 0; the 4B oQ4e repo answers 401 | n/a | the measured artifact is no longer public |
| `OsaurusAI` | 183 | `LFM2.5-2.6B-JANG_6M`, `MiniCPM5-2B-JANG_8M`, `Nanbeige4.2-3B-JANG_6M` | Osaurus/vMLX only |

(All counts and `gated`/existence checks VERIFIED via `?author=<org>&limit=1000` and per-repo
`/api/models/<repo>`, 2026-10-30.)

---

## 2. Where each engine looks for a model on disk

The harness passes an **artifact directory** to every runtime except Osaurus (which takes no model
argument at all). That is the harness's shape, not the engines' own: each engine has a discovery
surface of its own, and the onboarding app has to decide which one to write into.

### 2.1 mlx-lm 0.31.3 (the harness's control)

- **Argument:** `--model <path or repo id>` (`server.py:1754-1757`, help text: "The path to the MLX
  model weights, tokenizer, and config").
- **Resolution:** `mlx_lm.utils._download` (`utils.py:218-256`) — if `Path(arg)` exists it is used
  as-is; otherwise `huggingface_hub.snapshot_download(...)` fetches into the standard cache and
  returns the snapshot path. The allow-patterns are `*.json`, `model*.safetensors`, `*.py`,
  `tokenizer.model`, `*.tiktoken`, `tiktoken.model`, `*.jinja`, `*.txt`, `*.jsonl` — the exact file
  set a catalogue downloader needs to mirror for this engine to load the result.
- **Discovery:** `GET /v1/models` is not the served model; it is `scan_cache_dir()` filtered to
  repos holding `config.json`, `model.safetensors.index.json` or `tokenizer_config.json`
  (`server.py:1643-1680`). A model in the HF cache is therefore *listed* by any mlx-lm server, and
  a request naming it is served by loading it.
- **The harness** hands it the artifact directory directly (`runtimes.py:2064-2078`,
  `--model artifact_dir`), so no copy is made and the `models--org--name/snapshots/<rev>` path is
  the one that reaches the loader.

### 2.2 OptiQ 0.7.8

- **Argument:** `optiq serve --model <weights path or HF repo id>` (its own `--model`, forwarded to
  the bundled `mlx_lm.server`). A local directory is used as-is; a repo id is resolved by mlx-lm's
  loader (`optiq/cli.py:2634-2651`: "a repo id; mlx-lm resolves it … mlx-lm downloads those itself").
- **Cache visibility:** inherits mlx-lm's `scan_cache_dir` listing, and adds `--models-dir DIR`
  ("Directory of locally-built OptiQ quants to advertise in /v1/models (in addition to the
  HuggingFace cache and the served model)", `cli.py:2851-2861`, `:3479-3487`).
- **Switching:** `--allow-model-switch` is off by default at 0.7.8 — without it the request's
  `model` field is a label and every request serves `--model`; `--models-dir` implies it
  (`cli.py:2858-2865`). A startup script written for 0.5.13 must be re-read against this build: the
  flag set and defaults are not the ones `docs/runtimes/optiq.md` recorded for 0.5.13.
- **The harness** passes `--model artifact_dir` (`runtimes.py:2570-2600`).

### 2.3 oMLX 0.7.2

- **Argument:** `--model-dir DIR` — "Directory whose subdirectories are models" (`omlx/cli.py`
  argparse; `docs/runtimes/omlx.md:177`). The default is `~/.omlx/models` through
  `ModelSettings.get_model_dirs` (`settings.py:280-294`).
- **Discovery:** `discover_models` (`omlx/model_discovery.py:1955-2084`) scans each model dir with a
  **two-level** rule: a first-level child with `config.json` is a model; otherwise its children are
  scanned as an organisation folder. It also understands the hub layout directly:
  `models--Org--Name/snapshots/<hash>` is resolved to the snapshot and registered when
  `_is_hf_cache_mlx_compatible` accepts it (a `model*.safetensors` file plus MLX metadata, an
  `mlx-community/` repo id, or an MLX-looking name) — `model_discovery.py:2029-2052`,
  `:1588-1650`. **VERIFIED.**
- **The HF cache is appended by default.** `Settings.get_effective_model_dirs`
  (`settings.py:1507-1530`) adds `get_hf_cache_dir()` when `huggingface.hf_cache_enabled` is true,
  and it defaults true (`settings.py:715`); the server calls `get_effective_model_dirs()` with no
  argument (`server.py:2480-2481`). `--hf-cache/--no-hf-cache` exists (`cli.py:1332-1338`). The
  harness's command does not pass it.
- **The harness** creates a per-run catalog directory holding one **symlink** to the artifact
  (`create_omlx_scratch`, `runtimes.py:1466-1488`) and passes `--model-dir <catalog>`
  (`runtimes.py:2392-2405`), with a per-run `--base-path` (`:2525-2529`) so oMLX's settings cannot
  land in the user's config.

**Finding 6 above is here:** because the HF cache is appended, the per-run catalog is *first*, not
*only*. Two consequences for Phase 3: (a) a downloaded model in the HF cache is visible to oMLX
with no flag, which is useful for the app; (b) a harness run on a machine with a populated cache
does not satisfy "only the cell's model is visible" unless `--no-hf-cache` is added — a change to
`runtimes.Omlx.start_command`, which is the coordinator's to make.

### 2.4 Osaurus 0.25.29

- **No model argument, no model selector on `serve`.** The model is chosen per request by the
  `model` field, and the id is the **catalogue entry**, which is the repository name **lowercased**
  (`qwen3.5-4b-oq4`, `ornith-1.0-35b-jang_4m`). A filesystem path never resolves
  (`docs/runtimes/osaurus.md` §4.4). `/v1/models` lists catalogue entries, not weights.
- **Model root:** `~/MLXModels` on this host, laid out `<root>/<owner>/<name>/` (VERIFIED:
  `~/MLXModels/OsaurusAI/Ornith-1.0-35B-JANG_4M`, `~/MLXModels/mlx-community/`). The root is held
  as a bookmark (`NSOSPLastRootDirectory`); `modelRootSource` distinguishes a legacy default, a
  shared CLI setting and the bookmark (§3, §9.5).
- **HF-cache import is on by default.** `ExternalModelImportHFCache = true` and
  `ExternalModelCustomHFCachePath = ""` (empty = `~/.cache/huggingface/hub`) in
  `~/Library/Preferences/com.dinoki.osaurus.plist` — **VERIFIED on this machine**. Models in the
  cache appear in the catalogue without being copied (§4.4.1). A symlink placed in `~/MLXModels`
  also appears (§4.4.2).
- **How a download becomes visible:** put it in the HF cache (auto-import) or under `~/MLXModels/`
  (auto-catalogue). Neither is per-run: both are host state. `osaurus pull <model_id>` is the
  engine's own downloader (`docs/runtimes/osaurus.md` §2.1) — the app's download manager should not
  call it, because its progress and resume semantics are not established here.

### 2.5 vMLX 1.6.82

- **Argument:** positional `model` — "HuggingFace model name **or local path**"
  (`docs/runtimes/vmlx.md` §2.2.1). It loads through `load_model_with_fallback` →
  `mlx_lm.load` (`vmlx_engine/utils/tokenizer.py:…`), so a repo id goes through `snapshot_download`
  into the HF cache and a local path is used as-is.
- **Served id:** `_normalize_model_name` (`server.py:8767-8797`, quoted in
  `docs/runtimes/vmlx.md` §9.5) rewrites a hub-cache path back to `Org/Repo`; a plain directory
  becomes `parent/name`. The harness passes `<artifact_dir>` plus `--served-model-name
  vmlx_served_name(artifact_dir)` so the id is one the run chose (`runtimes.py:2878-2890`).
- **No `--models-dir`** (grep of `vmlx_engine/cli.py` for `models-dir|model_dir` returns nothing):
  vMLX serves the one model it was started with.

### 2.6 The one layout, and the cost of each candidate

| layout | Osaurus | oMLX | mlx-lm | OptiQ | vMLX | work to produce |
|---|---|---|---|---|---|---|
| **HF cache** `~/.cache/huggingface/hub/models--org--name/snapshots/<rev>` | auto (import on) | auto (dir appended by default) | auto-listed; path or repo id | auto-listed; path or repo id | path | reproduce `blobs/` + `snapshots/` symlinks + `refs/main` |
| `~/MLXModels/<org>/<name>` | auto (model root) | with `--model-dir ~/MLXModels` | path | path | path | one `mkdir` + files; nothing else |
| any path `<dir>/` | no (a path never resolves) | with `--model-dir <parent>` or a catalog symlink | path | path | path | one `mkdir` |

**Answer: the HF cache layout is visible to the most engines with the least work** — two engines
discover it with no configuration at all, and the three path-based ones accept the snapshot
directory. The cost is that a *custom* downloader must write the hub layout (content-addressed
`blobs/`, `snapshots/<rev>` symlinks, `refs/main`) rather than a plain directory, or Osaurus's
import and oMLX's cache-entry resolver will not see it.

If the downloader is to write a plain directory instead, `~/MLXModels/<org>/<name>` is the better
target: it is Osaurus's model root, it is oMLX's "organized two-level" layout, and the other three
take it as a path. It also matches the existing on-disk convention on this machine
(`~/MLXModels` is 147 GB of JANG weights already).

**The custom-volume case (D8: "the user may pick another volume").** oMLX and the Python engines
honour `HF_HUB_CACHE`; Osaurus's cache path is the host plist key `ExternalModelCustomHFCachePath`
and its model root is a bookmark, neither of which is per-run. A cache on another volume is
therefore visible to Osaurus only after that host setting is changed. If a second volume must be
first-class, write to a plain directory and point each engine's argument at it.

---

## 3. Downloading from Hugging Face with the standard library only

All probes below were made on 2026-10-30 against `huggingface.co` and its CDN. Authorisation was
anonymous throughout. No weight file was fetched in whole; the only data bytes read were two
100-byte `Range` probes (one `.safetensors`, one `tokenizer.json`).

### 3.1 The tree listing

```
GET https://huggingface.co/api/models/<repo>/tree/<revision>?recursive=true&expand=true
```

Returns a JSON array. Per entry, with `expand=true` (VERIFIED — full response inspected):

```json
{"type":"file","oid":"…","size":625229487,"path":"model.safetensors",
 "lfs":{"oid":"f5a0d9dd…","size":625229487,"pointerSize":134},
 "xetHash":"b707861e…"}
```

- `size` is the file size in bytes; `lfs.oid` is the value HF documents as the file's **sha256**,
  and it is the same value the resolve response returns as `x-linked-etag` (VERIFIED on
  `model.safetensors` of the 0.8B 4-bit repo: `f5a0d9dd…` in both places); `xetHash` is the xet
  content hash the CDN puts in its `ETag`.
- Pagination is real and documented by the server's own response: `?limit=N` returns N entries plus
  `Link: <…&cursor=…>; rel="next"` (VERIFIED with `limit=2`). A sharded 35B repo has ~10 files, so
  one page covers every model in this catalog; implement the loop anyway, or a repo with more files
  than one page returns is silently truncated.
- `revision` may be a branch, tag or commit. `/resolve/<commit>/<file>` resolves (VERIFIED), and a
  commit is immutable by construction, so pinning the commit from the model metadata makes the
  listing and the downloads reproducible.

### 3.2 Resolve, and the redirect to the CDN

```
GET https://huggingface.co/<repo>/resolve/<revision>/<file>
```

- Small text files: **307** to `/api/resolve-cache/models/<repo>/<commit>/<file>?…&etag="…"`, then
  200. (VERIFIED on `config.json`.)
- Weight files: **302** to a signed CDN URL on `us.aws.cdn.hf.co/xet-bridge-us/<repo-sha>/<xet-hash>`
  (VERIFIED on every weight file tried, including 2024-era `Qwen2.5-1.5B` and ancient `gpt2`/`bert`).
- The response to the `HEAD` carries, before the redirect: `x-repo-commit`, `x-linked-size` (the
  file's true byte length), `x-linked-etag` (the LFS sha256 for a weight file; a 40-hex git object
  id for a plain file), `x-xet-hash`, `accept-ranges: bytes` (VERIFIED).
- The signed URL carries `Expires`, `Policy`, `Signature`, `Key-Pair-Id`; **`Expires` was exactly
  3600 s after the request** on the weight-file probe (VERIFIED: `expires - now = 3600`). A resume
  after an hour must re-resolve, not reuse the URL.

### 3.3 Range and resume

- On the CDN URL, `Range: bytes=0-99` answers **206** with `Content-Range: bytes 0-99/<total>` and
  `Content-Length: 100`; `Range: bytes=1000-1099` answers 206 at that offset; an out-of-range start
  answers **416** (all VERIFIED).
- `urllib.request` follows the 302 and **preserves the `Range` header across the redirect**: a plain
  `urlopen(Request(url, headers={"Range": "bytes=0-99"}))` returned 206 and 100 bytes (VERIFIED).
  That is the single fact that makes a stdlib resumable downloader work.
- So resume is: open the target file for append at `offset`, send `Range: bytes=<offset>-`, require
  206 and a matching `Content-Range` total, write, and on 200 (server ignored the range) restart from
  zero rather than appending. Treat 416 as "already complete" only after checking the local size
  equals `x-linked-size`.

### 3.4 Integrity, size and ETag

- Verify the **sha256 from the tree listing's `lfs.oid`**, or equivalently `x-linked-etag`, not the
  CDN's `ETag`: on the xet CDN the `ETag` was `"b707861e…"` (the xet hash) while the sha256 was
  `"f5a0d9dd…"` (VERIFIED — both headers on the same response pair). `hashlib.sha256` is stdlib.
- Compare the downloaded byte count to `x-linked-size` (or `size` from the listing) before renaming.
  Do not trust `Content-Length` on the redirected response alone — it is the CDN's copy of the same
  number, but a proxy that re-encodes would change it.
- Non-LFS files (`config.json`, tokenizer) have no `lfs` block; their listing `oid` is a 40-hex git
  object id, not a content sha256 (VERIFIED: `.gitattributes` and `config.json` carry a 40-hex `oid`
  and no `lfs` entry). Verify them by size, or re-fetch their bytes and hash them with `sha1` over
  `"blob <len>\0" + bytes` (git's object rule) if exactness is needed. **INFERRED** that this is the
  only check available for them; the `oid` is what the listing gives.

### 3.5 Rate limits, gated repos, missing repos

- Anonymous quotas (CLAIMED — `https://huggingface.co/docs/hub/en/rate-limits`, "in September '25":
  API 500, Resolvers 3,000, Pages 100, per **fixed 5-minute window**). The live responses agree:
  `ratelimit: "api";r=498;t=204` / `ratelimit-policy: "fixed window";"api";q=500;w=300` on the tree
  endpoint, and `ratelimit: "resolvers";r=2997;t=213` with `q=3000;w=300` on `/resolve/` (VERIFIED).
  Every response also carried `x-hf-warning: unauthenticated; … set a HF_TOKEN` (VERIFIED). A 429
  arrives on exceed (CLAIMED); the `RateLimit`/`RateLimit-Policy` headers are the signal to back off.
- A **gated** repo answers `/resolve/` with **401** and `x-error-code: GatedRepo` plus an explanatory
  `x-error-message` (VERIFIED on `meta-llama/Llama-3.2-3B-Instruct`).
- A **missing** repo answers **401** too, with body `Invalid username or password.` and **no**
  `x-error-code` (VERIFIED on a nonexistent org/repo). **A downloader must not read 401 as "gated":
  it is the same status for both, and only the body/`X-Error-Code` distinguishes them.** This also
  means a typo in a repo id looks like an authorisation failure — surface the message verbatim.
- A private repo with no token behaves like the missing case (INFERRED from the same 401 path).

### 3.6 Is stdlib enough?

**Yes, for a correct resumable downloader. Evidence, item by item:**

| requirement | stdlib capability | evidence |
|---|---|---|
| listing with sizes and sha256 | `urllib` + `json` | §3.1 |
| follow the 307/302 to the CDN | `urllib.request` follows 301/302/303/307/308 for GET | §3.3 (206 through the redirect) |
| resume | `Range` preserved across the redirect; 206/416 observed | §3.3 |
| integrity | `hashlib.sha256`, size check | §3.4 |
| retry/backoff | `time.sleep` + `HTTPError`/`RateLimit` header | §3.5 |
| atomic finalise | write `*.incomplete`, `os.replace` | — |
| free-space guard | `shutil.disk_usage` | — |
| progress | `Content-Length`/`x-linked-size` per file, total from the listing | §3.1 |

**What stdlib does not give, and why none of it blocks a first version:**

1. **hf_xet's parallel chunk transfer.** `huggingface_hub` with xet reconstructs files from
   content-defined chunks over a CAS API; plain HTTP serves the same bytes sequentially. The cost is
   throughput on a large file, not correctness. On this catalog's sizes (≤4.8 GB) it is a
   minutes-scale difference, **UNKNOWN** in exact terms because no weight file was downloaded here.
2. **Built-in retries, backoff and resume bookkeeping.** Implementable in ~100 lines; the constants
   that matter (quota, 3600 s URL life, 206/416 semantics) are all in §3.5/§3.3.
3. **HTTP/2.** `urllib` is HTTP/1.1. Both hosts answered over HTTP/2 to curl; HTTP/1.1 is not
   refused (the same URLs answer a plain `urllib` request — the 206 probe in §3.3 was made with
   `urllib`, which negotiated HTTP/1.1). Not a correctness issue.
4. **The signed URL expires.** A download longer than an hour must finish on its open connection;
   a resume re-resolves first. Implementable; also true of any client that does not re-resolve.
5. **One unresolved signature detail:** the signed URL carries an `xip=` parameter that looks
   network-derived. Whether a resume from a different network is refused is **UNKNOWN** (probe: start
   a download, change networks, resume). Everything measured here came from one network.

**Verdict for `fetch.py`:** stdlib is enough. Download **one file at a time**, resolve-then-Range,
verify sha256 from the listing, write into a temporary name and `os.replace` on success, and
re-resolve on any 403/expiry. The one design constraint the probes impose is that the *listing*
must be fetched and kept beside the partial download: without `lfs.oid` there is nothing to verify
against, because the CDN's `ETag` is not the file hash.

---

## 4. Disk accounting: weight bytes, resident memory, and KV headroom

### 4.1 Weight bytes → resident memory, measured within one runtime

`peak_mb` is the maximum `phys_footprint` seen by `ohyesmlx/sample.py` (`footprint -p <pid>`,
megabytes = bytes/1024²). AGENTS.md forbids a cross-runtime ranking of this figure, so the table
below reads **down each runtime only**. Source: `results/harden-2026-09-28-cacheoff/grid-dense/*`
(4B) and `grid-moe/*` (8B), PASS rows only, one record per (runtime, workload), each record's peak
taken over that cell's 9 measured requests, `cache_state` absent (under Decision 130 that is the
off command on mlx-lm/OptiQ, and oMLX/vMLX pass their own off flags), `kv_quant` absent
(**VERIFIED** — records re-read with a script over `results/**/results.jsonl`).

`mlx-community/Qwen3.5-4B-4bit` — 3,061,131,520 B on disk = 2,919.3 MiB:

| runtime | chat peak | ratio | decode peak | ratio | prefill peak | ratio |
|---|---|---|---|---|---|---|
| mlx-lm 0.31.3 | 2813.0 | 0.96 | 2862.0 | 0.98 | 4218.0 | 1.44 |
| oMLX 0.7.2 | 4253.0 | 1.46 | 4263.0 | 1.46 | 5655.0 | **1.94** |
| OptiQ 0.7.8 | 3528.0 | 1.21 | 2926.0 | 1.00 | 4286.0 | 1.47 |
| vMLX 1.6.82 | 3708.0 | 1.27 | 3708.0 | 1.27 | 4592.0 | 1.57 |

`mlx-community/LFM2.5-8B-A1B-MLX-4bit` — 4,782,228,753 B = 4,560.7 MiB:

| runtime | chat peak | ratio | decode peak | ratio | prefill peak | ratio |
|---|---|---|---|---|---|---|
| mlx-lm 0.31.3 | 4791.0 | 1.05 | 4984.0 | 1.09 | 5692.0 | 1.25 |
| oMLX 0.7.2 | 5040.0 | 1.11 | 5039.0 | 1.10 | 5890.0 | 1.29 |
| OptiQ 0.7.8 | 6348.0 | 1.39 | 5004.0 | 1.10 | 5712.0 | 1.25 |
| vMLX 1.6.82 | 5180.0 | 1.14 | 5199.0 | 1.14 | 5890.0 | 1.29 |
| Osaurus 0.25.x | 3866.0 | 0.85 | 4529.0 | 0.99 | 5185.0 | 1.14 |

(Osaurus cells are the median of two samples — `results/grid-jang-moe/20260917T215805Z-format` and
its replicate (3862/3870, 4542/4516, 5204/5166); the rest are one record per workload. Osaurus's
4B-stock rows do not exist here, and its `peak_mb` is a *different quantity*: wired GPU pages are
charged differently, which is why a cross-runtime reading is refused —
`docs/research/2026-09-16-footprint-is-not-one-quantity.md`.)

**Reading it.** Within one runtime, the peak lands between **0.96×** and **1.94×** the artifact's
on-disk bytes on the four runtimes whose page accounting is comparable (0.85-1.14× on Osaurus, whose
`peak_mb` is a different quantity — see below); the maximum is usually the **prefill** workload
(~1,309-token prompt, `docs/research/2026-09-16-prompt-length-context-limits.md:117`), with OptiQ's
8B chat row (1.39×) the one exception in these two tables. The extra over weights is KV +
activations + Metal buffers + tokenizer. Two consequences a fit rule must not miss:

- **Weights understate residency by up to half** on the runtime with the largest overhead (oMLX),
  and the error grows with prompt length. A rule that compares `size_bytes` to RAM is optimistic by
  ~2× at 4k.
- **An artifact is not all weights.** The OptiQ 0.8B bundle is 886 MB, of which 201 MB is a vision
  sidecar and 20 MB a tokenizer; the text path loads neither. Disk size is the right number for a
  download budget and a conservative number for a memory budget — conservative in the safe direction.

### 4.2 KV cache at 4k context, by size class

KV bytes per token = `2 (K and V) × attention_layers × kv_heads × head_dim × 2 bytes (fp16)`, read
from each base `config.json`; hybrid families only pay it on their attention layers, and their
recurrent state is O(1) rather than O(context). **INFERRED** from the configs (arithmetic shown):

| model | attention layers | kv heads × head_dim | KV @ 1k | KV @ 4k | constant extra |
|---|---|---|---|---|---|
| Qwen3-0.6B (`qwen3`) | 28 / 28 | 8 × 128 | 112 MiB | **448 MiB** | — |
| Qwen3.5-0.8B (`qwen3_5`) | 6 / 24 | 2 × 256 | 12 MiB | **48 MiB** | linear-attn state |
| Qwen3.5-2B (`qwen3_5`) | 6 / 24 | 2 × 256 | 12 MiB | **48 MiB** | linear-attn state |
| LFM2.5-1.2B (`lfm2`) | 6 / 16 | 8 × 64 | 12 MiB | **48 MiB** | conv state |
| LFM2.5-2.6B (`lfm2`) | 8 / 30 | 8 × 64 | 16 MiB | **64 MiB** | conv state |
| granite-4.0-h-1b (`granitemoehybrid`) | 4 / 40 | 4 × 128 | 8 MiB | **32 MiB** | ~36 MiB Mamba state |
| gemma-4-E2B (`gemma4_text`) | 35, 20 share KV | 1 × 256 | ≤36 MiB | **≤140 MiB** | sliding windows reduce it |
| SmolLM3-3B (`smollm3`) | 36 / 36 | 4 × 128 | 72 MiB | **288 MiB** | — |
| Llama-3.2-3B (`llama`) | 28 / 28 | 8 × 128 | 112 MiB | **448 MiB** | — |
| LFM2.5-8B-A1B (`lfm2_moe`) | 6 / 24 | 8 × 64 | 12 MiB | **48 MiB** | conv state |

**The defensible headroom: 0.5 GiB per concurrent sequence at 4k, for every size class in this
catalog.** The worst case is a full-attention 3B (Llama-3.2-3B: 448 MiB at 4k; Qwen3-0.6B is the
same figure from 28 layers despite a quarter of the weights). The hybrids are ~50-70 MiB; a rule
that assumed one number must take the 0.5 GiB. Add 0.5 GiB per extra concurrent request — at N=8
the KV alone can be 3.5 GiB, which is what the concurrency sweep already measures
(`docs/research/2026-09-27-concurrency-batching.md`). KV quantization (the `kv_quant` pin) halves
or quarters these numbers, but it is a run pin on four of the five runtimes, not a catalog property.

### 4.3 The fit rule this supports

Two separate budgets, because they answer different questions:

- **Memory (D5 "fits", estimated).** `estimated_peak = size_bytes × 2.0` and require
  `estimated_peak ≤ Hardware.model_budget_bytes`. The 2.0 factor is the measured worst case at
  1,309 prompt tokens (1.94) plus the 4k KV delta for a 3B artifact (~0.1×); `model_budget_bytes`
  already subtracts 2 GiB for KV + runtime overhead (`hardware.py:72-80`), so the two guards overlap
  deliberately rather than leaving a gap. On this 64 GiB M2 Max (budget 46 GiB) every row fits; on a
  16 GiB Mac (budget 8.67 GiB) rows 1-11 fit and row 12 (4.78 GB → 8.9 GiB) does not; on an 8 GiB
  Mac (budget 3.33 GiB) rows 1-6 fit, and row 7 (1.79 GB → 3.34 GiB) misses the budget by 0.3%.
- **Disk (D4 "one model at a time", evict before fetch).** Require
  `free_disk ≥ size_bytes × 1.2` for the fetch (the extra covers a largest-shard `.incomplete`
  beside the finished files) and treat "one model resident on disk" as removing the whole repo
  directory. If the fetch writes into the HF cache, removal must take `blobs/`, `snapshots/` and
  `refs/` together — the same mistake the predecessor made in the opposite direction (a disk walk
  that counted snapshots twice; AGENTS.md "One definition of everything").

Two caveats the UI must carry: `size_bytes` is the **download**, not the installed footprint after
the cache's symlinks (identical here, but not on every filesystem), and `peak_mb` is measured on
this 64 GiB M2 Max only — D5 already forbids projecting it onto another Mac.

---

## 5. The table

Every field from the Hub API on 2026-10-30; `gated` is the API's own boolean (all false); params are
the **base** model's count; `measured here?` is `yes` only where a `results/**/results.jsonl` row
exists for that exact artifact.

| model | params | format | size_bytes | license | gated | engines that can serve it | measured here? |
|---|---|---|---|---|---|---|---|
| `mlx-community/Qwen3-0.6B-4bit` | 751,632,384 | mlx affine 4-bit gs64 | 351,386,061 | apache-2.0 | no | all 5 (¹) | no |
| `mlx-community/Qwen3.5-0.8B-4bit` | 873,438,784 | mlx affine 4-bit gs64 | 652,029,391 | apache-2.0 | no | all 5 (²) | no |
| `mlx-community/Qwen3.5-0.8B-OptiQ-4bit` | 873,438,784 | OptiQ-4bit (4/8-bit mixed) | 886,129,146 | apache-2.0 | no | all 5 (²) | no |
| `mlx-community/LFM2.5-1.2B-Instruct-4bit` | 1,170,340,608 | mlx affine 4-bit gs64 | 663,395,788 | LFM Open License 1.0 (`other`) | no | all 5 (¹) | no |
| `mlx-community/granite-4.0-h-1b-4bit` | 1,461,538,368 | mlx affine 4-bit gs64 | 833,197,077 | apache-2.0 | no | all 5 (³) | no |
| `mlx-community/Qwen3.5-2B-4bit` | 2,274,069,824 | mlx affine 4-bit gs64 | 1,749,081,927 | apache-2.0 | no | all 5 (²) | no |
| `RepublicOfKorokke/Qwen3.5-2B-oQ4` | 2,274,069,824 | oQ4 (mixed 4/5/6/8) | 1,794,528,789 | apache-2.0 | no | all 5 (²) | no |
| `mlx-community/LFM2.5-2.6B-4bit` | 2,697,198,592 | mlx affine 4-bit gs64 | 1,535,593,294 | LFM Open License 1.0 (`other`) | no | all 5 (¹) | no |
| `mlx-community/gemma-4-e2b-it-4bit` | 5,123,178,051 (2B effective) | mlx affine 4-bit gs64 | 3,583,088,661 | gemma (repo card; base card apache-2.0 + Gemma 4 licence link) | no | all 5 (⁴) | no |
| `mlx-community/SmolLM3-3B-4bit` | 3,075,098,624 | mlx affine 4-bit gs64 | 1,747,380,812 | apache-2.0 | no | all 5 (¹) | no |
| `mlx-community/Llama-3.2-3B-Instruct-4bit` | 3,212,749,824 | mlx affine 4-bit gs64 | 1,824,825,759 | llama3.2 | no (⁵) | all 5 (⁶) | no |
| `mlx-community/LFM2.5-8B-A1B-MLX-4bit` | 8,467,856,832 (1B active, 32 experts top-4) | mlx affine 4-bit gs64 | 4,782,228,614 | LFM Open License 1.0 (`other`) | no | all 5 (⁷) | **yes** — `results/harden-2026-09-28-cacheoff/grid-moe/` and `results/grid-jang-moe/` (2026-09-17) |

**Footnotes.** (¹) module present in all four mlx-lm builds + the corresponding MLXLLM class in
Osaurus; no live row here. (²) same, and `qwen3_5` has live PASS rows on all five — Osaurus on the
oQ4/oQ4e/OptiQ/JANG_4S 4B bundles, the stock `mlx-community/Qwen3.5-4B-4bit` on the other four
only. The stock 0.8B/2B packages are vision-bearing, and Osaurus was once observed to list a
`qwen3_5` stock 4-bit id and refuse to serve it (`docs/runtimes/osaurus.md` §4.4.2) — engine
support is real, per-artifact serving is not guaranteed. (³) `granitemoehybrid` is dense here
(`num_local_experts: 0`), module + class present, no live row. (⁴) `gemma4` module + `Gemma4Model`
class present, and `OsaurusAI/gemma-4-E2B-it-qat-JANG_4M` exists on the Hub, but no mlx-community
gemma row exists here and no gemma bundle is on this machine's model root. (⁵) the **MLX repo** is
not gated; its base `meta-llama/Llama-3.2-3B-Instruct` is `gated: manual`. (⁶) `llama` has live PASS
rows on all five via `brainworkup/Llama-3.1-8B-oQ4`. (⁷) `lfm2_moe` has live PASS rows on all five
for this exact artifact: the 2026-09-28 cacheoff grid's four columns
(`results/harden-2026-09-28-cacheoff/grid-moe/`) and Osaurus in
`results/grid-jang-moe/20260917T215805Z-format` and its replicate.

**Modality:** rows 2, 3, 6, 7 and 9 are vision-language packages (`vision_config` in the artifact's
`config.json`; row 3 ships a 201 MB vision sidecar). The text path loads them, but they are not the
"multimodal-free text model per family" the order prefers; rows 1, 4, 5, 8, 10, 11 and 12 are text.

---

## 6. What this does not settle

1. **The cap's meaning.** Strict ≤3.0B excludes the only 3B rows and the only measured MoE. If
   "≤3B" is meant as a 3B *class* (3.08/3.21 acceptable), rows 10-11 are in; if it is meant as
   active parameters, `Qwen3.5-35B-A3B` (3B active) is in, which is plainly not intended. Jason's
   call.
2. **No ≤3B MoE with an MLX checkpoint.** The nearest is LFM2.5-8B-A1B (8.47B total / 1B active,
   already measured here). Someone would have to convert `ibm-granite/granite-3.0-3b-a800m-instruct`
   to MLX for the spread's MoE slot to fit the cap; that is a download/convert job, not a catalog
   choice.
3. **Whether Osaurus's catalogue import accepts a hand-written HF-cache entry.** Its import is on
   (plist verified) and cache entries appear (`docs/runtimes/osaurus.md` §4.4.1), but the app was not
   asked to import a directory this document created. Probe: write one repo in hub layout with
   `blobs/`+`snapshots/` and check `GET /v1/models`. (No server was started here.)
4. **The xet `xip` signature and network changes.** Whether a resume after changing networks is
   refused is UNKNOWN (§3.6.5).
5. **The exact hf_xet speed difference.** No weight file was downloaded in full; the 100-byte
   `Range` probe in §3.3 is the only weight byte read.
6. **A JANG artifact on mlx-lm/OptiQ/oMLX.** The `quantization` block may be sufficient for some
   profiles and the `jang_config.json` manifest may be silently ignored — which is the token-salad
   class. Probe: load `OsaurusAI/LFM2.5-2.6B-JANG_6M` on mlx-lm and run the coherence gate, on a
   quiet machine, before any catalog offers JANG outside Osaurus/vMLX.
7. **`uingei`'s repositories are gone** (401, author listing empty). Any run directory referencing
   them is still on disk and still valid as a record; a re-run is no longer possible from that
   source.
8. **oMLX's appended HF cache** (finding 6) is a harness-behaviour question, not a catalog one, but
   it is the one place where this research contradicts a standing rule in `AGENTS.md`.

---

## 7. Reproduction

```sh
# versions
/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' /Applications/osaurus.app/Contents/Info.plist   # 0.25.29
/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' /Applications/oMLX.app/Contents/Info.plist      # 0.7.2
/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' /Applications/vMLX.app/Contents/Info.plist      # 1.6.82
optiq --version                                                                                                # mlx-optiq, version 0.7.8
~/.local/share/ohyesmlx/mlx-lm-0.31.3/bin/python -m mlx_lm --version                                           # 0.31.3

# the Hub facts in §1
curl -s 'https://huggingface.co/api/models/mlx-community/Qwen3.5-0.8B-4bit?blobs=true' | jq '{gated,license:.cardData.license,files:[.siblings[]|{p:.rfilename,s:.size}]}'
curl -s 'https://huggingface.co/mlx-community/Qwen3.5-0.8B-4bit/raw/main/config.json' | jq '{model_type,architectures,vision_config,quantization}'
curl -s 'https://huggingface.co/api/models/Qwen/Qwen3.5-0.8B' | jq '.safetensors.total'
curl -s "https://huggingface.co/api/models?author=JANGQ-AI&limit=1000" | jq length

# the download facts in §3
curl -s 'https://huggingface.co/api/models/mlx-community/Qwen3.5-0.8B-4bit/tree/main?recursive=true&expand=true' | jq '.[0:2]'
curl -sI 'https://huggingface.co/mlx-community/Qwen3.5-0.8B-4bit/resolve/main/model.safetensors' | grep -i -E 'HTTP|location|x-linked|x-xet|ratelimit'
curl -s -o /dev/null -D - -H 'Range: bytes=0-99' '<the location>' | grep -i -E 'HTTP|content-range|etag'
curl -s -o /dev/null -D - 'https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct/resolve/main/config.json' | grep -i 'x-error'

# the memory facts in §4: the exact run dirs the table reads, PASS rows only
python3 - <<'PY'
import json, glob
paths = (glob.glob('results/harden-2026-09-28-cacheoff/grid-dense/*/results.jsonl')
         + glob.glob('results/harden-2026-09-28-cacheoff/grid-moe/*/results.jsonl')
         + ['results/grid-jang-moe/20260917T215805Z-format/results.jsonl',
            'results/grid-jang-moe/replicate/20260917T222656Z-format/results.jsonl'])
for p in paths:
    for line in open(p):
        r = json.loads(line)
        if 'cell' not in r or r.get('status') != 'PASS':
            continue
        a = r['cell']['artifact_dir']
        name = a.split('models--')[-1].split('/')[0] if 'models--' in a else a
        if name in ('mlx-community--Qwen3.5-4B-4bit', 'mlx-community--LFM2.5-8B-A1B-MLX-4bit'):
            print(p.rsplit('/', 2)[0], r['cell']['runtime'], r['workload_id'],
                  (r.get('memory') or {}).get('peak_mb'), r.get('disk_bytes'))
PY

# the engine model-location facts in §2
grep -n 'def get_effective_model_dirs' -A 30 /Applications/oMLX.app/Contents/Resources/omlx/settings.py
grep -n 'get_effective_model_dirs' /Applications/oMLX.app/Contents/Resources/omlx/server.py
/usr/libexec/PlistBuddy -c 'Print' ~/Library/Preferences/com.dinoki.osaurus.plist | grep -E 'ExternalModelImportHFCache|ExternalModelCustomHFCachePath'
ls ~/MLXModels
sed -n '218,256p' ~/.local/share/ohyesmlx/mlx-lm-0.31.3/lib/python3.14/site-packages/mlx_lm/utils.py
grep -n 'scan_cache_dir\|def handle_models_request' ~/.local/share/ohyesmlx/mlx-lm-0.31.3/lib/python3.14/site-packages/mlx_lm/server.py
grep -n 'models-dir\|allow-model-switch' ~/Dev/tools/mlx-optiq/.venv/lib/python3.12/site-packages/optiq/cli.py
```

Sources read: `huggingface.co/docs/hub/en/rate-limits`, `.../api`, `.../models-downloading`,
`.../xet/index`; the HF HTTP API and CDN responses listed above; `docs/runtimes/{osaurus,omlx,optiq,
mlx-lm,vmlx}.md`; `ohyesmlx/runtimes.py`, `ohyesmlx/hardware.py`, `ohyesmlx/sample.py`;
`docs/research/2026-09-15-small-model-candidates.md`,
`2026-09-16-footprint-is-not-one-quantity.md`, `2026-09-16-prompt-length-context-limits.md`,
`2026-10-29-engine-install-paths.md`; the installed engine bundles and both venvs.
