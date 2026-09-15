# Format availability and runtime tooling for the Qwen3.6-35B-A3B format axis

**Date:** 2026-09-15
**Role:** research pass for the format-axis study (documentation only — no code changed)

The format axis holds the serving runtime constant at oMLX and varies the quantization format.
This note answers four questions against primary sources: what artifacts exist per format, what
oMLX can actually load, where each runtime's cache lives and how it is cleared, and whether
GuideLLM can replace the hand-rolled concurrency sweep.

**Evidence rules.** Every claim carries a source URL or the local path that was checked. Anything
not directly verified is marked **UNVERIFIED** and is not inferred. No model server was started,
no package was installed, and no file other than this one was created or edited in the repository.

**Host inspected.** macOS 26.6.2 (build 25G83), `uname -m` → `arm64`. Python 3.14.7
(`/opt/homebrew`), pip 26.2.1. Runtime versions on this machine: `omlx 0.6.4` (`omlx --version`);
CLI wrapper `/Users/jrazz/.omlx/bin/omlx` execs `/Applications/oMLX.app/Contents/MacOS/omlx-cli`;
`mlx-optiq 0.5.6` (`optiq --version`); Osaurus app `0.25.3`
(`defaults read /Applications/osaurus.app/Contents/Info.plist CFBundleShortVersionString`).

---

## Q1 — What quantized artifacts for `qwen3_5_moe` actually exist and are downloadable

### Architecture confirmation

`Qwen3.6-35B-A3B` is `model_type: "qwen3_5_moe"`
(`architectures: ["Qwen3_5MoeForConditionalGeneration"]`, 40 layers, 256 routed experts,
MTP head), read from the local OptiQ checkpoint's config:
`~/.cache/huggingface/hub/models--mlx-community--Qwen3.6-35B-A3B-OptiQ-4bit/snapshots/70a3aa32c7feef511182bf16aa332f37e8d82014/config.json`.

mlx-lm 0.31.3 ships that architecture — verified in the oMLX bundle's own interpreter:
`/Applications/oMLX.app/Contents/Resources/Python/framework-mlx-base/lib/python3.11/site-packages/mlx_lm/models/qwen3_5_moe.py`
(`mlx_lm-0.31.3.dist-info` next to it). This is consistent with the earlier finding in
`docs/research/2026-09-14-oq-portability-spike.md` that 0.31.3 ships `gemma4`/`gemma4_text`
but not `gemma4_unified`.

### Artifacts per format

Sizes are the sum of file sizes reported by the Hugging Face API (`?blobs=true`); `du` on disk can
differ by filesystem block size. "Downloads" is the API's `downloads` field. Every row was queried
on 2026-09-15.

| Format | Repo id | Quantized weights | Files | lastModified | Downloads |
|---|---|---|---|---|---|
| stock mlx 4-bit | `mlx-community/Qwen3.6-35B-A3B-4bit` | 20.40 GB | 17 | 2026-04-16 | 31,712 |
| oQ4 | `Jundot/Qwen3.6-35B-A3B-oQ4-mtp` | 21.61 GB | 16 | 2026-05-12 | 382 |
| oQ4e | `Jundot/Qwen3.6-35B-A3B-oQ4e-mtp` | 21.61 GB | 17 | 2026-07-09 | 3,445 |
| OptiQ | `mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit` | 24.67 GB | 17 | 2026-07-14 | 6,416 |
| JANGTQ2 | `JANGQ-AI/Qwen3.6-35B-A3B-JANGTQ` | 11.63 GB | 29 | 2026-09-08 | 212 |
| JANGTQ4 | `JANGQ-AI/Qwen3.6-35B-A3B-JANGTQ4` | 19.68 GB | 36 | 2026-09-08 | 153 |

Source for each size: `https://huggingface.co/api/models/<repo>?blobs=true`.
Repo discovery: `https://huggingface.co/api/models?author=mlx-community&search=Qwen3.6-35B-A3B`,
`...?author=Jundot&search=Qwen3.6`, `...?author=OsaurusAI&limit=200`,
`...?author=JANGQ-AI&limit=500`.

### Two corrections to the task's framing

1. **The stock 4-bit artifact is not "uniform affine".** `mlx-community/Qwen3.6-35B-A3B-4bit`
   declares a top-level `{group_size: 64, bits: 4, mode: "affine"}` **plus 80 explicit
   per-tensor overrides, all at 8 bits** (`mlp.gate`, `mlp.shared_expert_gate`, and friends).
   Verified by reading the raw config:
   `https://huggingface.co/mlx-community/Qwen3.6-35B-A3B-4bit/raw/main/config.json`.
   This is the standard mlx-community recipe, not a uniform quant, and it changes what the
   "stock" cell of the format axis actually contains.
2. **JANG/JANGTQ for this exact architecture is not published under the OsaurusAI org.** The
   full OsaurusAI listing (133 repos, 74 of them JANG-named) contains, for the 35B-A3B family,
   only `OsaurusAI/Qwen3.5-35B-A3B-JANG_2S` and `...-JANG_4K` — both **Qwen3.5**, not Qwen3.6.
   For **Qwen3.6**-35B-A3B the org publishes `mxfp4`, `MXFP4-MTP`, `MXFP8-MTP` only. The
   JANG/JANGTQ artifacts for qwen3_5_moe live under `JANGQ-AI` (97 repos, all JANG-named), which
   is the JANG vendor org (its model cards link osaurus.ai and vmlx.net).

   Source: `https://huggingface.co/api/models?author=OsaurusAI&limit=200` and
   `https://huggingface.co/api/models?author=JANGQ-AI&limit=500`.

### Other oQ/oQe members of the family (names only; sizes not measured)

`Jundot/Qwen3.6-35B-A3B-oQ6-mtp` (675 dl), `-oQ4-fp16-mtp` (358), `-oQ6-fp16-mtp` (646),
`-oQ4` (124), `-oQ2` (67), `-oQ6` (78), `-oQ3e-mtp` (246). Source: the Jundot author query above.
The oQ4e card states the artifact was produced by "oQ (oMLX v0.4.5.dev1) mixed-precision
quantization", format "MLX safetensors":
`https://huggingface.co/Jundot/Qwen3.6-35B-A3B-oQ4e-mtp/raw/main/README.md`.

The OptiQ card documents the mix explicitly: 392 tensors at 8-bit, 118 at 4-bit, group 64, plus a
bundled MTP head (`optiq/mtp.safetensors`) and an `optiq/optiq_vision.safetensors` sidecar:
`https://huggingface.co/mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit/raw/main/README.md`.
JANGTQ's own config is `{"version": 2, "weight_format": "mxtq", "profile": "JANGTQ2",
"quantization": {"method": "affine+mxtq", "group_size": 64, "bits_default": 2}}`:
`https://huggingface.co/JANGQ-AI/Qwen3.6-35B-A3B-JANGTQ/raw/main/jang_config.json`.

### What is already on this machine (no downloads allowed per AGENTS.md)

| Repo | Local path | Size on disk |
|---|---|---|
| `Jundot/Qwen3.6-35B-A3B-oQ4-mtp` | `~/.cache/huggingface/hub/Jundot/Qwen3.6-35B-A3B-oQ4-mtp/` | 21.61 GB of safetensors, byte-identical to the hub |
| `mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit` | `~/.cache/huggingface/hub/mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit/` | 24.69 GB total (5 shards + both `optiq/` sidecars), per-file sizes identical to the hub |
| `Jundot/Qwen3.6-35B-A3B-oQ4-mtp` (hub layout) | `~/.cache/huggingface/hub/models--Jundot--Qwen3.6-35B-A3B-oQ4-mtp/` | 4 KB — `refs/main` only (`883dbfad79be43ce3f016d952dd374c62b7a96ec`), no `snapshots/`, no `blobs/` |

No JANG artifact for this model is present: `~/.cache/huggingface/hub/models--JANGQ-AI--Spark-X2.5-4B-JANG_8M/`
holds only `refs/` and is a different model; `~/.cache/huggingface/hub/OsaurusAI/` and
`~/.cache/huggingface/hub/JANGQ-AI/` contain no model files (`.DS_Store` only).

---

## Q2 — What can oMLX actually load?

Installed version 0.6.4 (latest release; `v0.7.0.dev2` is a pre-release). Sources:
`https://github.com/jundot/omlx/releases`, `https://api.github.com/repos/jundot/omlx/releases?per_page=100`.

| Format | Loads in oMLX 0.6.4? | Evidence |
|---|---|---|
| stock mlx 4-bit | **Yes** | oMLX README v0.6.4, Models table: "LLM — Any model supported by mlx-lm" (`https://raw.githubusercontent.com/jundot/omlx/v0.6.4/README.md`); release notes benchmark `Qwen3.6-35B-A3B 4-bit` (v0.7.0.dev1 notes) |
| oQ / oQe | **Yes, first-class** | oQ is oMLX's own quantizer: bundle ships `/Applications/oMLX.app/Contents/Resources/omlx/oq.py` and `omlx/admin/oq_manager.py`; oQ model cards name oMLX as the producing tool |
| OptiQ | **Expected yes — UNVERIFIED by execution** | The installed bundle contains OptiQ-specific code paths: `_resolve_optiq_vision_sidecar()` reads `config.json`'s `optiq_vision.sidecar` (`omlx/engine/vlm.py:545-573`); model discovery special-cases `optiq/optiq_vision.safetensors` in index files (`omlx/model_discovery.py:1117-1126`); `mlx_lm_extra_tensors.mtp_file` — the exact key the OptiQ checkpoint declares for `optiq/mtp.safetensors` — is resolved in `omlx/oq.py:1564-1577`. The OptiQ card itself says "Load it with `mlx-lm` and use it as usual". No server was started, so no load was attempted. |
| JANG / JANGTQ | **No** | See below. No released oMLX version contains a JANG engine. |

### JANG: the premise does not hold

The task states JANG support "reportedly landed via a PR". The primary record says otherwise:

- Three JANG PRs exist and **all three are open and unmerged**: [#364](https://github.com/jundot/omlx/pull/364)
  (opened 2026-03-24, 1,130 insertions), [#820](https://github.com/jundot/omlx/pull/820)
  (2026-04-20), [#1828](https://github.com/jundot/omlx/pull/1828) (draft, 2026-06-11).
  `https://api.github.com/repos/jundot/omlx/pulls/364|820|1828` → `state: open`, `merged: false`,
  `merged_at: null` for each.
- No `omlx/engine/jang.py` at tags `v0.3.6`, `v0.3.8rc1`, `v0.3.12`, `v0.4.0`
  (`https://api.github.com/repos/jundot/omlx/git/trees/<tag>?recursive=1`; all HTTP 404 for the raw
  path). The v0.3.x engine directories contain 14 modules — `base, batched, dflash, embedding,
  reranker, sts, stt, tts, vlm, audio_utils, …` — and no JANG loader. `omlx/model_discovery.py` at
  `v0.3.8rc1` contains zero occurrences of the string `jang`.
- None of the 100 most recent release notes mention JANG (release list grepped programmatically).
- The installed 0.6.4 bundle has no file matching `*jang*` anywhere under
  `/Applications/oMLX.app` (`find` across the bundle).
- The JANGTQ model card states the requirement plainly: "**JANGTQ requires our custom loader** —
  stock `mlx_lm.load()` can't parse `.tq_packed` tensors. You need `jang-tools`", and "All JANG
  models are meant to be run in vMLX"
  (`https://huggingface.co/JANGQ-AI/Qwen3.6-35B-A3B-JANGTQ/raw/main/README.md`).

**Contradicting source, recorded rather than resolved:** issue
[#1889](https://github.com/jundot/omlx/issues/1889) ("JANG support removed in v0.4.x without
notice", 2026-06-15) asserts that PR #364 "was merged into v0.3.x" and that the engine was removed
during the v0.4 refactor. That assertion is not supported by the PR state, the release notes, or the
tag trees above; the issue is closed as *not planned*. **No oMLX version can be named as the one
that shipped JANG**, because none did. The maintainer's position in the #364 thread (2026-03-28) is
also on record: the quality delta over oQ was marginal in his measurements and he objected to a
platform-locked dependency, so this may never merge.

**Consequence for the study.** The format axis as scoped — one runtime, four formats — **breaks on
JANG**. It cannot be fixed by artifact choice: no downloadable JANG/JANGTQ artifact of this
architecture is loadable by any released oMLX. The realistic options are (a) drop JANG from the
matrix and carry the caveat in the published table, or (b) move JANG to its own runtime (vMLX /
`jang-tools`), which violates the one-runtime invariant and would have to be declared as a second,
separate axis. That is a design decision for the coordinator, not a research finding.

Cheapest next check, not performed here because no server may be started in this role: launch the
installed oMLX against the *local* OptiQ artifact and issue one completion. If that fails too, the
format axis narrows to two formats (stock, oQ) until the OptiQ question is settled.

---

## Q3 — Cache clearing per runtime

Two of the three runtimes keep KV/prefix state on disk across restarts, so a cold run requires an
explicit clear. The third has nothing to clear.

### oMLX — tiered hot-RAM / cold-SSD prefix cache, survives restarts

- **On disk:** `~/.omlx/cache` — taken from the live settings file
  `/Users/jrazz/.omlx/settings.json`: `cache.ssd_cache_dir = "/Users/jrazz/.omlx/cache"`,
  `cache.ssd_cache_max_size = "92GB"`, `cache.hot_cache_write_through = false`,
  `cache.hot_cache_only = false`, `cache.enabled = true`.
  Layout locally: 16 hex subdirectories `0`…`f` holding `*.safetensors` blocks (69 GB total), plus
  empty `_boundary_snapshots/`, `response-state/`, `vision_features/`.
- **Documented clearing:** admin HTTP endpoints
  `POST /api/ssd-cache/clear` and `POST /api/hot-cache/clear`, both `Depends(require_admin)`
  (`/Applications/oMLX.app/Contents/Resources/omlx/admin/routes.py:5639` and `:5685`). The SSD
  endpoint first asks each loaded model's SSD manager to clear, then deletes `*.safetensors` in
  each of the 16 hex subdirs, so it also wipes caches for models that are not loaded. The hot-cache
  endpoint drops the in-RAM cache and reclaims through the scheduler's synchronized path.
  With `hot_cache_write_through` enabled (0.6.3rc3+), clearing the hot cache flushes dirty blocks
  instead of discarding them.
- **Not available as a CLI command:** `omlx --help` lists only
  `start | stop | restart | serve | launch | diagnose | cluster`.
- **Cold start procedure:** stop the server, clear the SSD cache (endpoint or the directory), start
  the server. Clearing while stopped is what the endpoint's filesystem fallback exists for.

### Osaurus — disk cache configured in `~/.osaurus/config`, survives restarts

- **On disk:** `~/.osaurus/cache/kv_v2/` — 8.2 GB locally: 16 `*.safetensors` entries,
  `cache_index.db` (+ `-shm`, `-wal`), and `ssm_companion/`. Non-KV cache files in the same
  directory: `model-sizes.json`, `external-models.json`, `greeting-pool.json`, `image-edit-inputs/`.
- **Config:** `/Users/jrazz/.osaurus/config/server-runtime.json` → `cache`:
  `blockDisk {enabled: true, maxSizePercent: 10}`, `prefix {enabled: true}`, `legacyDisk {enabled: false}`,
  `pagedKV {enabled: false}`, `defaultMaxKVSize: 65536`, `liveKVCodec: "engine_selected"`,
  `storedKVCodec: "auto"`, `enableSSMReDerive: true`, `longPromptMultiplier: 2`.
  `server.json` also carries `modelEvictionPolicy: "Strict (One Model)"` and
  `modelIdleResidencyPolicy: {mode: "after_seconds", seconds: 900}`.
- **Documented clearing:** the app's bundled guides say the toggles live in **Settings → Server**
  and that "cache changes unload loaded models to take effect"
  (`/Applications/osaurus.app/Contents/Resources/OsaurusCore_OsaurusCore.bundle/Contents/Resources/guide-settings.md:23`,
  `guide-server-api.md:26`, `guide-memory.md:21` — the last one states the on-disk prompt cache
  persists prompt prefixes across restarts). The app binary contains an action labelled
  `clear ssd cache` (next to `clear cache`, `disk cache size`, `paged kv`) plus
  `_isClearingDiskCache` / `_clearedCacheSummary`, and exposes `GET /admin/cache-stats`
  (`strings -a /Applications/osaurus.app/Contents/MacOS/osaurus`). There is no CLI subcommand:
  `osaurus --help` has none.
- **Caveat:** cache settings are explicitly *not* part of the declarative config surface
  (`guide-config.md:80`), which is why `osaurus config export` (run on this machine) prints no
  cache section. Binary string also warns: "Legacy disk cache cannot run at the same time as paged
  KV cache" — locally both are off, `blockDisk` is on.

### optiq — nothing persists; `optiq serve`'s KV cache lives in RAM

- **On disk:** no cache directory. `optiq config` (run on this machine) has no cache-path setting
  (`output_dir` is for converted models; `adapter_cache` unset). The KV cache is built per process
  by the bundled mlx-lm (`make_prompt_cache`) and, with `--kv-bits`/`--kv-config`, converted in
  place to per-layer quantized caches
  (`/Users/jrazz/Dev/tools/mlx-optiq/.venv/lib/python3.12/site-packages/optiq/core/kv_cache.py:434`
  `maybe_quantize_kv_mixed`, `:483` `make_mixed_kv_cache`). The mlx-lm 0.31.3 server in that venv
  keeps its prompt cache in RAM as an LRU (`--prompt-cache-size` / `--prompt-cache-bytes`,
  `.../mlx_lm/server.py:1872,1878`) — this version has no on-disk prompt-cache file flag.
- **Documented clearing:** none is needed — restarting the process is the clear.
  **UNVERIFIED** that no other optiq component writes a disk cache: a search of the installed
  package for cache-dir/persist/SSD references found only Lab memory management
  (`optiq/lab/mlx_cleanup.py`) and conversion outputs.
- Two disk locations exist and are *not* caches: `~/.optiq/lab/` (Lab UI state) and the
  `-o/--output` directory of `optiq kv-cache`, whose `kv_config.json` is configuration — deleting
  it only reverts KV precision to fp16.
- Related knobs on `optiq serve`: `--stream-experts` (SSD-resident MoE weights, not a cache),
  `--stream-experts-cache` (in-RAM LRU, default 0), `--idle-timeout` (unload after N idle seconds).

**Cold/warm summary:** oMLX and Osaurus both require an explicit clear between cold and warm runs;
optiq is cold after every restart. Any harness that only restarts processes will silently measure a
warm oMLX and a warm Osaurus.

---

## Q4 — GuideLLM

**Repo:** `https://github.com/vllm-project/guidellm` (Apache-2.0, formerly Neural Magic, now under
the vLLM project). **PyPI:** `guidellm`, version **0.7.3**, wheel `guidellm-0.7.3-py3-none-any.whl`.
Metadata: `https://pypi.org/pypi/guidellm/json`.

**Can it drive an arbitrary OpenAI-compatible endpoint on localhost?** Yes. The backend is selected
with `--backend kind=openai_http,target=http://localhost:8000`, and `request_format=` picks the route
(`/v1/chat/completions`, `/v1/completions`, `/v1/embeddings`, `/v1/audio/...`). Nothing in the
quickstart requires vLLM — vLLM is only the example server. Source: repo README,
`https://github.com/vllm-project/guidellm`.

**Does it pip-install cleanly on macOS arm64?** **UNVERIFIED by execution** — no venv was created
(this role may not write outside the working directory). What was verified is wheel availability for
every dependency on this host (arm64, Python 3.14.7):

| Package | Version | macos arm64-capable wheel |
|---|---|---|
| uvloop (hard dep) | 0.22.1 | `cp314-…-macosx_10_13_universal2.whl` (universal2 covers arm64) |
| numpy (hard dep) | 2.5.3 | `cp314-cp314-macosx_11_0_arm64.whl` |
| torch (hard dep) | 2.14.0 | `cp314-cp314-macosx_14_0_arm64.whl` |
| orjson (`perf`) | 3.12.0 | `cp314-cp314-macosx_15_0_arm64.whl` |
| msgspec (`perf`) | 0.21.1 | `cp314-cp314-macosx_11_0_arm64.whl` |
| culsans, click, httpx, pydantic, faker, loguru, rich, tabulate, transformers | — | pure Python (`py3-none-any`) |

Sources: `https://pypi.org/pypi/<pkg>/json` for each row. Two caveats: the README's stated
prerequisite is "Python 3.10 – 3.13" while PyPI metadata says `>=3.10,<4.0`, so 3.14 is allowed by
metadata but untested upstream; and `pip install guidellm[recommended]` pulls
`perf` + `tokenizers` extras (`tiktoken`, `blobfile`, `mistral-common`), which were not checked
wheel-by-wheel.

**What JSON does it emit?** By default `guidellm run` writes `benchmarks.json` **and**
`benchmarks.csv` into `GUIDELLM__DEFAULT_RESULTS_DIR` (current directory if unset). Any `--output`
replaces the defaults: `--output kind=json,path=results/benchmark.json`, plus `yaml`, `csv`, `html`,
`plot` (png/jpg/svg/pdf). The JSON holds configuration, metadata, benchmark statistics and retained
per-request data, and is reloadable in Python via
`GenerativeBenchmarksReport.load_file("benchmarks.json")`. Request-level payload size is bounded
with `--metrics kind=generative,sample_size=N` (N per status group; `0` keeps stats only).
Source: `https://raw.githubusercontent.com/vllm-project/guidellm/main/docs/guides/outputs.md`.

**How are concurrency and request rate specified?** Through the profile:

- `--profile kind=concurrent,streams=16` — N in-flight requests (our concurrency sweep).
- `--profile kind=constant,rate=10` — target arrival rate in requests/second.
- `--profile kind=poisson`, `kind=throughput,max_concurrency=…`, `kind=synchronous`, `kind=sweep`.
- Profile config also accepts `warmup=` / `cooldown=` as a fraction or absolute units;
  `--constraint kind=max_duration,seconds=…`, `kind=max_requests,count=…`,
  `kind=max_errors,count=…`, and `kind=over_saturation`.
- Example: `guidellm run --backend kind=openai_http,target=http://localhost:8000
  --profile kind=concurrent,streams=16,warmup=0.1,cooldown=0.1
  --constraint kind=max_duration,seconds=… --data kind=synthetic_text,prompt_tokens=256,output_tokens=128`.

Source: `https://github.com/vllm-project/guidellm` (README, "Load Patterns" / "Benchmark Controls").

**Percentiles.** GuideLLM reports full distributions per metric rather than a single mean:
request rate, request concurrency, SLO attainment, goodput, output/total tokens per second, request
latency, dispatch delay, scheduled latency, TTFT, ITL, TPOT — summarised as mean/median/mode/variance/
stddev/min/max/count/sum **and percentiles p001, p01, p05, p10, p25, p50, p75, p90, p95, p99, p999**.
Source: `https://raw.githubusercontent.com/vllm-project/guidellm/main/docs/guides/metrics.md`.
That is strictly more than our hand-rolled `ttft_p50/p90/p99`, so the substitution is mechanically
sound.

**Three definitional mismatches to resolve before adopting it as the concurrency harness** — these
are exactly the definitions AGENTS.md pins, and GuideLLM does not obviously match them:

1. GuideLLM defines TTFT as "the time taken to generate the first token of the output"
   (`docs/guides/metrics.md`). Our TTFT is the first **content** token with reasoning deltas
   excluded. Whether GuideLLM's TTFT crosses a reasoning token is **UNVERIFIED** — the docs do not
   say. If it does, our numbers and its numbers are not the same metric.
2. Its ITL "excludes the first token", which is the same shape as our `itl_s` formula, so that one
   maps cleanly.
3. Token counts: `--metrics prefer_response_metrics=true` (default) prefers server-reported counts.
   Our `token_source` rule requires the runtime's `usage` only when it separates reasoning from
   content. Whether GuideLLM partitions reasoning tokens is **UNVERIFIED**.

Also worth noting: GuideLLM's default output includes per-request retained data, which fits the
project's "raw observations are never discarded" rule directly — but its JSON is its own schema, not
`results.jsonl`, so a conversion step would be needed.

---

## What this does not establish (UNVERIFIED list)

1. That oMLX 0.6.4 loads `mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit` end to end. Code paths and the
   model card both say it should; no load was attempted here.
2. That `guidellm` installs cleanly on this exact machine, and whether it separates reasoning tokens
   for TTFT/token counts. Wheel availability was checked; execution was not.
3. That no oMLX release between `v0.3.0` and `v0.3.12` shipped JANG. Tag trees were sampled
   (`v0.3.6`, `v0.3.8rc1`, `v0.3.12`, `v0.4.0`) plus all 100 recent release notes, all of which are
   negative. A full 24-tag sweep was not run.
4. The semantics of the HF `downloads` field (assumed to be a recent download count, not cumulative).
5. Whether issue #1889's account (JANG merged in v0.3.x, removed in v0.4) is true. It conflicts with
   every other primary source and is closed as not planned; it is recorded here so the conflict is
   visible rather than silently resolved.

**If the JANG premise has to hold for the format axis, that is a design decision, not a research
finding** — it requires either a second runtime or acceptance of a three-format matrix with the
caveat stated in the published table.

---

## Sources

Remote (queried 2026-09-15):

- HF API model listings and file sizes: `https://huggingface.co/api/models?author=mlx-community&search=Qwen3.6-35B-A3B`,
  `https://huggingface.co/api/models?author=Jundot&search=Qwen3.6`,
  `https://huggingface.co/api/models?author=OsaurusAI&limit=200`,
  `https://huggingface.co/api/models?author=JANGQ-AI&limit=500`,
  and `https://huggingface.co/api/models/<repo>?blobs=true` for each repo in the Q1 table.
- Model cards and configs: `https://huggingface.co/mlx-community/Qwen3.6-35B-A3B-4bit/raw/main/config.json`,
  `https://huggingface.co/mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit/raw/main/README.md`,
  `https://huggingface.co/Jundot/Qwen3.6-35B-A3B-oQ4e-mtp/raw/main/README.md`,
  `https://huggingface.co/JANGQ-AI/Qwen3.6-35B-A3B-JANGTQ/raw/main/README.md`,
  `https://huggingface.co/JANGQ-AI/Qwen3.6-35B-A3B-JANGTQ/raw/main/jang_config.json`.
- oMLX: `https://github.com/jundot/omlx/releases`,
  `https://api.github.com/repos/jundot/omlx/releases?per_page=100`,
  `https://api.github.com/repos/jundot/omlx/pulls/364` (and `/820`, `/1828`),
  `https://github.com/jundot/omlx/issues/1889`,
  `https://github.com/jundot/omlx/pull/364`,
  `https://raw.githubusercontent.com/jundot/omlx/v0.6.4/README.md`,
  `https://raw.githubusercontent.com/jundot/omlx/v0.3.8rc1/omlx/model_discovery.py`,
  `https://api.github.com/repos/jundot/omlx/git/trees/<v0.3.6|v0.3.8rc1|v0.3.12|v0.4.0>?recursive=1`.
- GuideLLM: `https://github.com/vllm-project/guidellm`,
  `https://raw.githubusercontent.com/vllm-project/guidellm/main/docs/guides/outputs.md`,
  `https://raw.githubusercontent.com/vllm-project/guidellm/main/docs/guides/metrics.md`,
  `https://pypi.org/pypi/guidellm/json` and the per-dependency PyPI JSON endpoints.

Local paths checked (read-only):

- `~/.cache/huggingface/hub/` (org and repo directories; per-file sizes vs. the hub API).
- `~/.omlx/settings.json`, `~/.omlx/cache/` (layout and 69 GB total), `/Applications/oMLX.app/Contents/Resources/omlx/`
  (`admin/routes.py:5639,5685`, `engine/vlm.py:545`, `model_discovery.py:1117`, `oq.py:1564`),
  `.../Python/framework-mlx-base/lib/python3.11/site-packages/mlx_lm/models/qwen3_5_moe.py` and
  `mlx_lm-0.31.3.dist-info`.
- `~/.osaurus/config/server-runtime.json`, `~/.osaurus/config/server.json`, `~/.osaurus/cache/kv_v2/`,
  `/Applications/osaurus.app/Contents/MacOS/osaurus` (strings), the bundled guides under
  `/Applications/osaurus.app/Contents/Resources/OsaurusCore_OsaurusCore.bundle/Contents/Resources/`.
- `/Users/jrazz/Dev/tools/mlx-optiq/.venv/lib/python3.12/site-packages/optiq/` (`core/kv_cache.py`,
  `lab/mlx_cleanup.py`), `.../mlx_lm/server.py:1872,1878`, `~/.optiq/lab/`.
