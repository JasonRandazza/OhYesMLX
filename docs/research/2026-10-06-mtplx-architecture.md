# MTPLX — source and architecture deep read (2026-10-06)

**Purpose:** decide whether and how MTPLX (https://github.com/youssofal/MTPLX) becomes the
sixth runtime on the runtime axis. Research only — no install, no model download, no server
start, no writes outside this document.

**Revision read:** `youssofal/MTPLX@9882703f3105363ddc37eca9f97aa09a1d387112`
("Release notes: the 2.12.2 gate results", 2026-10-03). A shared `git clone --depth 1` at
`/private/tmp/claude-501/mtplx-src` was used to read source. The GitHub commits API confirms
`9882703` is the current `main` HEAD as of 2026-10-06
(https://api.github.com/repos/youssofal/MTPLX/commits?per_page=2). All `file:line` citations
below are relative to that revision.

**Method / tiers:** source read first; web second, SearXNG then GitHub's REST API and
mtplx.com. Claims are labelled:

- **VERIFIED(source)** — read directly in the MTPLX source at `9882703`, or in a GitHub API
  response quoted with its URL.
- **CLAIMED(vendor/community)** — stated by MTPLX's own docs/site or a third party; not
  independently reproduced.
- **INFERRED** — my reasoning over verified facts; not stated by MTPLX.

Cross-references: `AGENTS.md` (this repo's rules), `docs/runtimes/optiq.md` §9.2,
`docs/runtimes/vmlx.md` §7.4.1, `docs/runtimes/omlx.md` §8.8, `docs/runtimes/osaurus.md` §7.8,
`docs/research/2026-09-25-mtp-depth-sweep.md`.

---

## 1. What it is

MTPLX is a native Mac app plus CLI (`mtplx`, PyPI package version 2.12.2) that serves local
LLMs on Apple Silicon with the **model's own multi-token-prediction heads** as a speculative
decoder, behind an OpenAI- and Anthropic-compatible HTTP server. [VERIFIED(source):
`pyproject.toml:7` name/version; `docs/server.md:1-8` server target and a runnable example;
`README.md:15` mechanism; `README.md:39-58` app/CLI install paths]

The vendor's headline claim is exactness: *"MTPLX accepts a drafted token with probability
min(1, p/q) and resamples rejected positions from the residual (p − q)+, the Leviathan–Chen
construction, which preserves the model's distribution at any temperature. Output is verified
bit for bit against single-token decoding."* [CLAIMED(vendor): https://mtplx.com/faq/ , read
2026-10-06] §3.4 checks that claim against the code and the in-tree caveats.

Ecosystem position, relevant because oMLX is one of our five runtimes: MTPLX's site states
oMLX's README credits MTPLX for its Lightning-MTP verify-shape Metal kernels. [CLAIMED(vendor):
https://mtplx.com/faq/ ; INFERRED: corroborated in kind by `NOTICE:35-45`, which records
in-tree kernels adapted from dflash-mlx and oMLX's QSA kernel.]

## 2. Repo layout

Facts from a directory listing at `9882703`; per-path notes cite the files that fix each role.

| Path | What it is | Evidence |
|---|---|---|
| `mtplx/` | The Python package: 142 files, 16 subpackages (`server/`, `batching/`, `cache_bank/`, `models/`, `backends/`, `kernels/`, `commands/`, `dashboard/`, `ui/`, `vision/`, `templates/`, `benchmarks/`, `docs/`, `data/`, `kpi/`, `correctors/`) | directory listing; `pyproject.toml:106-118` |
| `mtplx/server/` | The HTTP server, 44,650-line `openai.py` plus 15 focused modules (`request_policy.py`, `stream_rate.py`, `mtp_batch.py`, `responses.py`, an `omlx_bridge/` …) | `wc -l`; dir listing |
| `apps/MTPLXApp` | Swift package, **supervisor only**: launches/stops hidden `mtplx serve`, typed HTTP/SSE clients, settings, logs. "inference stays in the existing `mtplx` daemon" | `apps/MTPLXApp/README.md:10-34` |
| `dashboard/` | React 19 + Vite + Tailwind TS dashboard (bun lockfile, bun tests) | `dashboard/package.json:1-35` |
| `bin/mtplx` | Bash wrapper the native app uses to launch the daemon: venv discovery, runtime-source shadow, `exec … python -m mtplx.cli` | `bin/mtplx:1-119` |
| `native_extensions/` | Two nanobind/Metal extension packages: `qsa_kernels` (Qwen4 QSA sparse-GQA) and `verify_mlp` | directory listing; `pyproject.toml:57` (nanobind) |
| `vllm_metal/` | Vendored subset of vllm-metal's Apache-2.0 paged-attention Metal kernels, used for local MLX dispatch only | `NOTICE:33-36` |
| `tests/` | Large pytest suite (hundreds of files, incl. `tests/test_mtp_*`, `test_reasoning_stream_split.py`, `test_qsa_*`) | directory listing; release commit message below |
| `benchmarks/`, `scripts/`, `tools/`, `docs/`, `mistakes/` | Bench runners, dev scripts, internal docs; `mistakes/` is a written-postmortem directory | directory listing |
| `dist-pifix/` | One pre-built wheel (`mtplx-2.9.1-py3-none-any.whl`) | directory listing |

The package ships a prebuilt dashboard bundle (`mtplx/dashboard/_static/**`,
`pyproject.toml:112`) so the server can serve it without bun. [VERIFIED(source)]

## 3. How MTP speculative decoding is implemented

### 3.1 Draft heads

The draft is the checkpoint's own MTP head, loaded by per-family patch modules —
`mtp_patch.py` (Qwen3-Next lineage) plus `qwen3_5_mtp_patch.py`, `deepseek_mtp_patch.py`,
`glm_mtp_patch.py`, `hy_v3_mtp_patch.py`, `mimo_mtp_patch.py`, `nemotron_h_mtp_patch.py`,
`step3p5_mtp_patch.py`, and the Qwen4/Flash-Next family inside `models/qwen4_exp.py`.
[VERIFIED(source): file listing; `models/qwen4_exp.py:7052-7056` ("Build + load the MTP head
from `mtp.safetensors`")]

Head resolution order — config pointer first, then fixed names — is one function:

```
mlx_lm_extra_tensors.mtp_file
→ mtp.safetensors → mtp/weights.safetensors → model-mtp.safetensors
```

[VERIFIED(source): `artifacts.py:425-435`]. Heads may also be **embedded** as `mtp.*` tensors
in the main weights or as appended decoder layers; the registry's own wording is "`mtp.safetensors`
or embedded `mtp.*`". [VERIFIED(source): `registry.py:1933`; `artifacts.py:179-195`]. The
canonical expected key sets (`mtp.layers.0.*`, MoE variants, prequantized variants) live in
`constants.py:20-207`.

Note for the harness: this is the same config-pointer key OptiQ bundles use
(`mlx_lm_extra_tensors.mtp_file → optiq/mtp.safetensors`, per our `docs/runtimes/optiq.md`
§9.2). Whether MTPLX's loader accepts an OptiQ/JANG-exported head's tensor layout is **not
established here** — see §12 and the unverified list.

### 3.2 Depth

- `mtplx serve --depth N` — default **3**. [VERIFIED(source): `cli.py:3665`]
- `--mtp` / `--no-mtp` toggle native-MTP generation on the same loaded runtime;
  `--generation-mode {mtp,ar,auto}` chooses the mode explicitly (`auto` default).
  [VERIFIED(source): `cli.py:700-716`, `cli.py:3668-3671`]
- For the Qwen 3.8 family the descriptor fixes the range: default 3, min 1, **max 3**, with a
  recorded memory-kill at depth 4 and falsified D6–D8 cells ("acceptance cannot fill the
  window"). [VERIFIED(source): `backends/descriptors.py:536-556`]
- For the Qwen4/Flash-Next family (`qwen4_exp`) the descriptor says depth is a **ceiling**
  under an adaptive "expected_value" policy the serving lane declares — the same shape our
  vMLX §7.4.1 documents as `adaptive`. [VERIFIED(source): `backends/descriptors.py:442-455`]
  `--adaptive-policy {none,streak,expected_value,cost}` defaults to `none` at the CLI
  (`cli.py:875-879`), but a family lane can install its own policy. [VERIFIED(source);
  INFERRED: a MTPLX "fixed depth N" cell on `qwen4_exp` needs the same verify-the-depth-ran
  discipline as vMLX unless the family is one without an adaptive policy.]

### 3.3 Verify and commit

Two verify strategies appear in the serial loop; both commit through the same rule.

- **Sequential strategy** (`verify_strategy == "sequential"`): one draft token at a time;
  accept → commit draft and forward it; reject → commit the correction.
  [VERIFIED(source): `generation.py:9866-9968`]
- **Capture strategy** (default family lanes): the verify forward is the two-row batch
  `[primary, draft]`; on acceptance the draft is committed **and** a bonus token is sampled
  from the target row at the next position (`generation.py:10042-10058`) — the standard
  speculative-sampling bonus token. [VERIFIED(source): `generation.py:9970-10058`]
- There is also a Qwen4 **block verifier** with its own `scaled_residual` (union of target
  and scaled draft support) and a verify-glue path. [VERIFIED(source):
  `qwen4_block_verify.py:444-456`; `generation.py:15411-15475`]

The acceptance rule itself is one small, shared module:

- accept with `min(1, p/q)` — `sampling.py:295-300`;
- on rejection sample from the normalized `max(p − q, 0)` residual — `sampling.py:303-339`;
- `verify_one_token` composes the two — `sampling.py:358-369`; the marginal oracle
  (`speculative_output_marginal`, `sampling.py:372-391`) exists to prove the composed law
  recovers the target distribution.

Production call sites: `generation.py:9895-9907` (sequential), `:10017-10028` (capture),
`:10207`, `:15456`, `:16972`; `compute_acceptance_probability` is the alias import of
`sampling.acceptance_probability` at `generation.py:140-142`. The on-device fast path keeps the
same law over sparse top-k distributions (`fast_sampling.py:355-376`; `batched_decode.py`
for the batched lane). [VERIFIED(source)]

### 3.4 "Exact at any temperature" — what the code does at T=0 and T>0

**T > 0.** The committed stream is produced by the Leviathan–Chen construction above. Two
properties matter for the harness:

- The output marginal is preserved **for any draft distribution q**; the draft temperature is
  deliberately free (`draft_sampling.resolve_draft_temperature`: "Correctness never depends on
  this value: probability-ratio acceptance derives p and q independently, so any draft
  temperature preserves the output marginal", `draft_sampling.py:18-22`; same statement in
  `frspec_draft.py:6`). This means a draft head run at a different temperature, or an adaptive
  draft temperature, does not invalidate the target law; it changes acceptance and speed.
  [VERIFIED(source)]
- The vendor's evidence for the sampled path is a comparison of "a thousand four-token samples
  from the fast path with a thousand from the plain path at temperature 1, top-p 0.95 and
  top-k 20, by token id", matching "within the plain path's own noise", on two packs, plus the
  statement that "numerical equivalence of the model's execution paths is checked separately".
  [CLAIMED(vendor): `README.md:34`]

**T = 0 (what a OhYesMLX cell sends).** The production loop does not route greedy through the
residual machinery; it branches explicitly:

```
target_token = argmax(target_logits_for_draft)
accepted_now = draft_token == target_token
correction   = target_token
```

[VERIFIED(source): `generation.py:9882-9888` (sequential) and `:10004-10010` (capture); the
rejection path for greedy simply keeps verify logits and continues, `:9941-9944`]. So at T=0 a
committed token is *the target's own argmax at that position* wherever the draft diverged —
the draft changes speed, not the token choice, modulo numerics.

**The numerics caveat, and it is in-tree.** The turbo verify kernels "are not bit-exact versus
stock kernels (different accumulation order). Argmax-identical on all probed positions; at the
product sampler (temp 0.6 / top_p 0.95 / top_k 20) the live D3 verify path measured total
variation 0.0 and sample agreement 1.0 on every probed cell", and "Speculative acceptance
remains mathematically exact with respect to the verify-computed target distribution. Do not
use for bit-exactness QA." [VERIFIED(source): `docs/turbo-verify.md:29-36`]. The exact-T0
guard that would force stock kernels during greedy verify is **off by default**, and its own
comment records that it "never delivered MTP==AR greedy identity (cross-M frame flips survive
stock kernels) and cost 5-21% greedy decode". [VERIFIED(source): `attention_context.py:99-113`;
`generation.py:11292` arms it only when the flag is set]

**Reading for the harness (INFERRED):** "exact at any temperature" is a statement about the
**sampler law** — given the verify-computed target distribution, T=0 output is the target's
greedy token and T>0 output is distributionally the target's. It is **not** a claim of
bit-identity with MTPLX's own plain-AR path, and the vendor FAQ's "verified bit for bit
against single-token decoding" [CLAIMED(vendor): FAQ] is in tension with the in-tree
`docs/turbo-verify.md` caveat. For a OhYesMLX cell this means: a T=0 MTPLX cell is
greedy-faithful to MTPLX's own verify stack; comparing its tokens to another runtime's greedy
stream is a cross-runtime comparison and was never promised.

Receipts a cell could read back: every verify event carries `accepted`, `accept_probability`,
`correction`, `verify_strategy`, and per-depth acceptance sums; the greedy-chain eligibility
receipt names `greedy_draft` / `greedy_target`. [VERIFIED(source): `generation.py:9912-9940`;
`generation.py:12751-12752`]

## 4. Batching and concurrency

- **One owner thread for model execution**; each request owns its own prompt, logical KV,
  sampler settings, seeded RNG, budget, stop state and output stream. Even when requests share
  a batched allocation, per-row masks/offsets/commits prevent cross-context reads.
  [VERIFIED(source): `docs/concurrency.md:8-11`, `:46-56`]
- Scheduler modes, chosen at server start: `serial` (**default**), `cooperative`, `ar_batch`,
  `mtp_batch`, `mtp_cohort_experimental`, `hyper` (admission fixed at 1; width reserved for
  self-speculative rows). [VERIFIED(source): `docs/concurrency.md:15-41`]
- `--scheduler-mode` default `serial` with a measured reason in the help text: "serialized MTP
  beats the batched-AR lane end to end on prefill-heavy concurrent loads because MTP decode is
  ~4x faster per stream". `--batching-preset` default `latency`; `--max-active-requests`
  exists (positive int, no default) and is **refused** in `hyper` mode.
  [VERIFIED(source): `cli.py:776-805`; `docs/concurrency.md:38-41`]
- The batched MTP lane is model-specific (`server/mtp_batch.py`; the Qwen3.6-35B-A3B fixed
  B8/K1 lane documented in `docs/concurrency/qwen35b-mtp-batch.md`) and has a numerics preset
  `--mtp-batch-numerics {throughput,balanced,serial-exact}`. [VERIFIED(source):
  `cli.py:799-803`; `docs/concurrency.md:86-96`]

**Answer to the order's question:** MTPLX is **single-stream by default** — requests are
served one at a time on the serial lane — and concurrency is an opt-in scheduler mode, not a
property of the product path. A OhYesMLX cell that sends one request at a time is measuring
the default path; a concurrency cell must declare the mode it selected. [VERIFIED(source) +
INFERRED for the harness framing]

## 5. KV cache design

Three layers, all on by default:

1. **Warm RAM session bank.** Every conversation's KV state stays warm after a turn so the next
   message restores instead of re-prefilling. Budgets and TTLs are env-only
   (`MTPLX_SESSION_BANK_IDLE_TTL_S` 3600 s, `_MAX_BYTES` auto = half the RAM left after
   weights, capped 48 GiB, `_MAX_ENTRIES` 24/48). A conversation over its per-session budget
   keeps a **reference lease** to the live KV instead of a snapshot, counted in `held_nbytes`.
   [VERIFIED(source): `docs/server.md:158-182`, `:184-194`]
2. **SSD cold tier, persistent.** Default store `~/.mtplx/session-bank` (or
   `--ssd-session-cache-dir`). Content-addressed: `entries/` holds one `payload.json` per
   snapshot naming shared `blobs/`, and `manifest.sqlite` names the entries a restore may use.
   `--ssd-session-cache {on,write-only,off}` defaults to **on**; cap defaults `100GB` (scaled
   down on small-RAM Macs, further by `min(cap, free_disk/4)`, writes stop below 10 GiB free);
   a rolling write budget (`MTPLX_SSD_WRITE_BUDGET_PER_HOUR`, 128G) guards SSD wear; orphan
   reconcile runs at open and `mtplx gc [--apply]` inspects/cleans. [VERIFIED(source):
   `docs/server.md:209-250`; `cli.py:2542` help text; `cli.py:829-834`]
3. **Paged KV quantization.** CLI `--paged-kv-quantization | --paged-kv-quant | --kv-quant
   {off,q8,q4}`, **default off**. q8/q4 are symmetric per-head quantization with fp32 scales;
   q8 keeps a context-sized unquantized mirror below a 1024-token threshold, q4 keeps no
   mirror; prefill stays unquantized; the compiled verify step dequantizes in attention; "the
   dense two-pass and dense-decode layouts are not used while active". [VERIFIED(source):
   `cli.py:848-871`; `kv_quant.py:81-128`]. TurboQuant is a separate, kernel-level mode
   (vLLM-Metal kernels; default q8 keys / q3 values in its config helper) and is explicitly
   "intentionally separate" from the in-tree q8/q4 mode. [VERIFIED(source): `kv_quant.py:1-6`;
   `turboquant.py:17-68`]

Prefix identity is `model_path × mtp_enabled × hidden_variant × template_hash × …`, and the
cold-tier schema stores `mtp_enabled` as part of the cache key — an AR run and an MTP run do
not share entries. [VERIFIED(source): `cache_bank/cold_tier.py:3229-3243`, `:2828-2843`;
`session_bank.py:59-69`]. `POST /admin/cache/clear` exists. [VERIFIED(source):
`docs/server.md:44`]

**Harness consequences.** (a) A cold-cache cell must control the SSD store — point
`--ssd-session-cache-dir` at the run's scratch so `stop()` removes it, mirroring the oMLX SSD
cache handling in `runtimes.Omlx.start_command` (AGENTS.md hazard list). (b) `--ssd-session-cache off`
was found in the serve parser; **no flag was found for disabling the RAM session bank** —
budgets are env-only (`MTPLX_SESSION_BANK_MAX_BYTES`), and whether a zero budget is accepted
is unverified. (c) The one-copy cache rewrite in 2.12.2 has an open failure mode: issue #592
reports `ValueError: QSA pooled hold N rows; resizing to M would cut them` on cache-missing
turns (compaction) with `LIVE_FRONTIER=1` on Flash-Next, i.e. a **loud** engine error, not a
silent wrong number. [CLAIMED(community): https://github.com/youssofal/MTPLX/issues/592 ,
read 2026-10-06; INFERRED: fail-loud, but it makes long-conversation warmup cells flaky until
fixed.]

## 6. Sampler defaults, and the `generation_config.json` question

The question the harness asks of a new runtime before a first cell (AGENTS.md, Decision 131):
which penalties and sampler values the server applies when the request sends only temperature,
`max_tokens` and the messages.

- **Project-wide defaults: temperature 0.6, top_p 0.95, top_k 20.**
  [VERIFIED(source): `constants.py:16-18`; `mtplx serve` carries the same defaults on
  `--temperature` (`cli.py:3768-3772`), `--top-p` (`:3773-3775`), `--top-k` (`:3777`)]
- **Penalties default 0.0** — `--default-presence-penalty` / `--default-frequency-penalty`,
  default 0.0. [VERIFIED(source): `cli.py:3779-3787`]. Resolution order is request value →
  server default → 0.0. [VERIFIED(source): `server/request_policy.py:293-302`]
- **Anonymous clients' sampler fields are honored by default.** Since 2.5.3,
  `MTPLX_CLIENT_CONTROLS_DEFAULT=honor`: "OpenAI-API semantics. Explicit body params
  (temperature/top_p/enable_thinking) from anonymous clients are applied." The flip's stated
  reason is exactly our failure mode: "external tools send temperature:0 expecting OpenAI
  semantics, were silently served the 0.6 coding sampler, and published 'MTPLX does not
  respect temp=0'". MTPLX's own managed surfaces (app / OpenCode / Pi / Open WebUI hints) stay
  server-owned. [VERIFIED(source): `openai.py:17210-17232`, `:17265-17297`]
- **Family-owned defaults override the generic ones** for two families:
  `qwen3_8` → `temperature 1.0, top_p 0.95, top_k 20`; `qwen4_exp` → `1.0/0.95/20`. The
  dispatch is `descriptors.sampler_defaults_for_model` (`backends/descriptors.py:559-574`;
  values at `:407` and `:441`). All other families keep the descriptor/project defaults.
  [VERIFIED(source)]
- **`generation_config.json` is read for exactly two lanes**, and only for
  temperature/top_p/top_k: (1) `hy_v3` — "Tencent ships 0.9 / 1.0 / off"
  (`openai.py:43414-43468`); (2) the Gemma-4 target/assistant pair
  (`gemma4_pair.py:81-89`, `:135-148`). **No code path reads presence/frequency penalty from
  a bundle's `generation_config.json`** — a repo-wide search for `presence_penalty` /
  `frequency_penalty` finds request fields, CLI defaults, the sampling math and the opt-in
  Loop Guard, and `generation_config` is parsed only by the two lanes above.
  [VERIFIED(source): grep over `mtplx/**/*.py` at `9882703`, results cited above;
  INFERRED: the Decision-131 bundle-penalty check therefore has nothing to find on MTPLX.]
- **Sampler interventions are off by default.** Loop Guard (DRY-style steering) is opt-in:
  "OFF (opt-in)… no synthetic steering touches sampling by default" (`openai.py:28869-28884`).
  The literal-repetition stops are "OFF BY DEFAULT since 2.12.0 (project policy: no
  generation-policy intervention ships on)" (`openai.py:28835-28852`). The thinking-budget
  guard is experimental/off. [VERIFIED(source): `CHANGELOG.md:46`]
- **Seed.** The OpenAI-format request schema carries `seed` (`openai.py:1801`, `:2079`);
  resolution is request seed → server seed → fresh random (`openai.py:28887-28904`).
  A seedless T=0 request is greedy-inert on RNG, matching the harness's no-seed rule.
  [VERIFIED(source); INFERRED for the harness equivalence]

**Cell consequence (INFERRED):** a harness request with `temperature: 0` overrides the 0.6/1.0
defaults and makes top-p/top-k inert; no bundle penalty can apply; the only defaults that
could differ by family and would need recording are the thinking mode (§7) and, on hy_v3 /
Gemma-4-pair, the generation_config temperature — which the request's temperature 0 overrides.
The sampler survey for MTPLX is therefore short, but the family and pack should still be
recorded with the row.

## 7. Chat template and thinking

- Encoding goes through `tokenizer.apply_chat_template` with `enable_thinking`,
  `preserve_thinking`, `reasoning_effort` and `tools` kwargs; a manual Gemma-4 encoder exists
  for converted artifacts without a template; a fallback handles template-less tokenizers.
  [VERIFIED(source): `chat_encoding.py:298-347`; `:223-295`]
- `--reasoning {auto,on,off}` defaults to **auto** ("use `--reasoning off` for
  terse/non-reasoning runs"); `--preserve-thinking {auto,on,off,scoped}` defaults to auto
  (scoped keeps reasoning only inside the active agent round). [VERIFIED(source):
  `cli.py:610-615`, `:645-651`]
- Per-family reasoning codecs carry their own `default_mode` in the descriptor table —
  `auto` for most (e.g. `descriptors.py:370`, `:485`, `:526`, `:736`, `:827`, `:926`, `:1018`),
  `off` for the mlx-lm AR lane (`:683`), `on` for Laguna (`:632`). [VERIFIED(source);
  INFERRED: the Qwen3.5/3.6 native packs must be read per artifact at pin time, exactly as the
  harness treats each runtime's thinking default today.]
- Templates ship in `mtplx/templates/` (e.g. `qwen36_froggeric_v19`, `qwen36_froggeric_v21_3`).
  [VERIFIED(source): file listing; those templates contain `enable_thinking` and
  `reasoning_content` handling]
- A thinking-budget guard exists and is opt-in (`--agent-thinking-budget` /
  `MTPLX_THINKING_BUDGET`; "Off because it can end reasoning early"). [VERIFIED(source):
  `CHANGELOG.md:46`]

## 8. Streamed output: channels, TTFT, and granularity

- **Two channels in the OpenAI SSE stream.** Visible deltas are exactly
  `delta.content` and `delta.reasoning_content` (the server's own visible-delta census lists
  both prefixes, `openai.py:28086-28089`); the Anthropic bridge maps `reasoning_content` to
  `thinking` blocks (`:6749-6754`, `:6944-6951`). [VERIFIED(source)]
- **The splitter is a declared contract**, `ReasoningContentStreamSplitter`: "Incrementally
  split backend-native reasoning from visible content… `start()`, `feed(text)` and
  `finish(...)` return `(field, text)` chunks, `field` being `"reasoning_content"` or
  `"content"`". It never emits the tail of its pending buffer while that tail could still be
  the prefix of an unfinished reasoning tag (`STREAM_TAG_HOLDBACK`, ≥32 chars).
  [VERIFIED(source): `reasoning_codecs.py:319-329`, `:56-64`]
- **MTPLX's own TTFT definition**: "the time from the request's arrival to the first visible
  delta (content, reasoning or tool call)", split into named spans
  (`mtplx_stats.ttft_spans.exclusive_s`). [VERIFIED(source): `CHANGELOG.md:29`]
- **Granularity**: `--stream-interval` (serve) defaults to **1** — "Committed-token batch size
  per chat SSE chunk" (`cli.py:3710-3713`; the server rejects values < 1 at `openai.py:5315`).
  Two mechanisms shape the wire without changing the bytes: adjacent same-field runs are
  coalesced into one frame (`_coalesce_stream_fields`, "channel boundaries are preserved by
  construction — a reasoning→content flip always lands in different tuples and is never merged
  across", `openai.py:17620-17644`), and a release pacer spreads a block-sized batch
  (≥ `MTPLX_STREAM_PACER_MIN_TOKENS`, default 6) token-by-token at ≤30 ms/piece "so every
  client sees a flow instead of a paste"; "only the write cadence changes".
  [VERIFIED(source): `openai.py:17583-17617`]

**Consequence for OhYesMLX (INFERRED).** A thinking-on MTPLX response streams
`reasoning_content` deltas first, so `transport.timing_channel` will classify the first timed
delta as reasoning — the Decision 119 path, timed on the reasoning channel and labelled, is
the shape to reuse from oMLX (`docs/runtimes/omlx.md` §8.8 and `docs/research/2026-09-15-omlx-streams-in-the-reasoning-channel.md`).
Probe with a large `max_tokens` and read `content_event_count` — the two habits AGENTS.md
records from the oMLX mis-read. The holdback means the *first* reasoning delta may arrive a
tag-length later than the first sampled token; that delay is inside TTFT and identical in
kind to the tag-holdback other runtimes have. [INFERRED]

## 9. MLX / mlx-lm pin — and the fork question

- **`mlx==0.32.2`, exactly.** The pin comment says 0.32.3 "decodes at the same speed, but its
  output is not bit-identical to 0.32.2 on Flash-Next, and the app bundles 0.32.2, so pip and
  Homebrew now install what the app runs." An earlier comment records 0.32.0 → 0.32.2
  measuring +29% decode / +41% prefill at 88.4k. [VERIFIED(source): `pyproject.toml:29-36`]
- **`mlx-lm>=0.31,<0.32`** (the runtime bundles its own loader modules for some families).
  [VERIFIED(source): `pyproject.toml:37`]
- `transformers>=5.10.0,!=5.13.0,<5.17` (each bound has a measured reason, incl. a GHSA floor
  and a poisoned 5.13.0), `nanobind>=2`, plus `fastapi`, `uvicorn`, `pydantic`, `numpy`,
  `rich`, `safetensors`, `huggingface-hub`, `pillow`. [VERIFIED(source): `pyproject.toml:14-63`]
- **No MLX fork.** "MTPLX runs on stock PyPI MLX; no fork is required for any profile (the
  legacy `--strict-mlx-fork-assert` flag is a deprecated no-op)." [VERIFIED(source):
  `INSTALL.md:45`; `profiles.py:792-809`; `docs/releases/v2.0.0.md:15`; the fork requirement
  was removed in 2.0.0, `CHANGELOG.md:4365-4373`]. The wrapper does honor an optional
  `MTPLX_MLX_FORK_PYTHON_ROOT` via `PYTHONPATH` (`bin/mtplx:33`, `:108-110`) — a dev hook, not
  the product default. [VERIFIED(source)]
- Custom Metal kernels live **in-package** (`mtplx/kernels/`, `native_extensions/`,
  `vllm_metal/`). The vendor's own description: "in-package Metal kernels, not an MLX fork or
  patched qmm build." [VERIFIED(source): `profiles.py:906`; CLAIMED(vendor wording reviewed
  from the source comment)]

## 10. License and attribution

- **Apache-2.0.** [VERIFIED(source): `LICENSE:1-4`; `pyproject.toml:11`; GitHub API
  `"spdx_id": "Apache-2.0"`]. The repo also ships `CITATION.cff` and a `NOTICE`.
- **`NOTICE` adds an in-product attribution requirement**: products that "include, embed, or
  are built on MTPLX" must display *"Powered by MTPLX"* in a user-visible place; "Attribution
  in a source repository, a README, or a marketing page alone does not satisfy this
  requirement." For benchmarks/writing it asks for "MTPLX by Youssof Altoukhi" with a link.
  [VERIFIED(source): `NOTICE:8-28`]. Vendored/adapted components listed: vllm-metal's
  paged-attention kernels, dflash-mlx kernels, PipeNetwork's Laguna MLX implementation, oMLX's
  QSA kernel. [VERIFIED(source): `NOTICE:33-45`]
- **For OhYesMLX (INFERRED):** the harness does not embed MTPLX in a shipped product, so the
  in-product banner is not engaged by a measurement run; a published results document or table
  that builds on it should carry the credit line the NOTICE asks for, which is cheap. If the
  harness ever ships a bundled runtime venv it would cross into the "includes or embeds"
  language and the banner requirement should be re-read.

## 11. Release cadence and issue/PR health

- **Cadence: very fast, shipping weekly-to-daily.** 40 releases from `1.0.0` (2026-06-10) to
  `2.12.2` (2026-10-03); the last four weeks alone: 2.11.3 (09-17), 2.12.0 (09-23), 2.12.1
  (10-02), 2.12.2 (10-03). [VERIFIED(source): `CHANGELOG.md` version headings]
- **Repo health at 2026-10-06** (GitHub REST API, read 2026-10-06): created 2026-05-02;
  2,526 stars; 197 forks; last push 2026-10-03; default branch `main`
  (https://api.github.com/repos/youssofal/MTPLX). Issues: **320 total, 16 open**; PRs:
  **278 total, 27 open** (https://api.github.com/search/issues?q=repo:youssofal/MTPLX+type:issue
  and `+type:pr`, both read 2026-10-06 — the order's "16 issues, 27 PRs at last look" are the
  open counts and still exact). Activity is live: issue #592 updated 2026-10-06, PR #600
  opened 2026-10-06 by a regular contributor.
- **Quality signals.** The release commit itself recorded "pytest 11,284 passed, Swift 1,104,
  M1 to M4 rehearsal 763" [VERIFIED(source): commit `9882703` message, GitHub commits API].
  The tree carries a `mistakes/` directory of written postmortems and changelog entries with
  measured conditions and raw logs. Contributors beyond the founder appear repeatedly in the
  changelog (e.g. @jvmenen, @qshiftedx, @davidtai, @bpmforge). [VERIFIED(source):
  `CHANGELOG.md:25-120`; directory listing]
- **Risk notes for the harness.** (1) Pin the exact version per row; 2.12.x changed cache and
  memory policy weekly, and the project itself refuses mlx 0.32.3 because output differs —
  version drift here is behavioural, not cosmetic. (2) The open #592 failure is loud
  (engine error on cache-miss compaction), so a cell that hits it FAILs rather than lying;
  still, avoid long multi-turn warmup cells until fixed. (3) Some vendor performance claims
  are machine-specific and some "16 GB" measurements were done "by limiting a 128 GB Mac"
  [CLAIMED(vendor): FAQ]; do not carry them into our tables.

## 12. Verdict: does MTPLX become a sixth runtime, and how?

**Short answer (INFERRED from the verified facts above):** yes — MTPLX is the strongest
candidate sixth runtime because it is the only one whose *product identity* is native-MTP
speculative decoding, and its default posture (serial scheduler, temperature honored, no
bundle penalties, no default sampling interventions, OpenAI SSE with explicit channels) is
harness-friendly. But it should enter through the **MTP-depth study on MTPLX-loadable
artifacts first**, not by dropping it into existing runtime-axis columns, because the artifact
contract and one or two pins still need work.

Where it fits the five-runtime landscape:

| Runtime | MTP is… | Engine lineage | What a MTPLX cell adds |
|---|---|---|---|
| mlx-lm | absent | upstream | a product that exists because of MTP |
| OptiQ | an opt-in engine (`--mtp --mtp-depth`) | mlx-lm fork | a second independent MTP implementation to cross-check OptiQ's |
| vMLX | native, adaptive, env-pinned | own engine | a fixed-depth contrast (MTPLX depth is family-capped at 3 for qwen3_8, adaptive-ceiling on qwen4_exp) |
| Osaurus | vmlx-swift engine, config-only | Swift app | third independent implementation |
| oMLX | monkey-patch, per-model, single-stream only | oMLX patch | — (oMLX itself credits MTPLX kernels) |

Effort per harness requirement (each item cites §above):

1. **Transport**: OpenAI `/v1/chat/completions` with SSE and `reasoning_content`; port is a
   serve flag, default 8000 — **collides with vMLX's 8000** (AGENTS.md hazard list), so the
   Runtime class must pass a free port. [§1, §8]
2. **Artifact gate**: refuse a depth up front unless the family is one MTPLX wires, the config
   declares an MTP layer (`mtp_num_hidden_layers` / `num_nextn_predict_layers` /
   `mtp.*` keys), and the head resolves through `expected_mtp_file` and parses
   (`mtp_patch.py:663-673`, `:760-784`). Mirroring `runtimes.vmlx_mtp_refusal` /
   `optiq_mtp_refusal`. **Do not assume OptiQ/JANG sidecars load — that is unverified.**
   [§3.1]
3. **Depth pin**: `mtp_depth={off,N}` maps to `--no-mtp` and
   `--depth N --generation-mode mtp`; a depth cell must also declare the scheduler stays
   `serial`. For `qwen4_exp` packs, verify no adaptive policy demotes the depth (vMLX §7.4.1
   discipline), because its descriptor declares one. [§3.2, §4]
4. **Cache pin**: `cache_state` maps to `--ssd-session-cache {on,off}` plus a RAM-bank control
   that **was not found as a flag** — to be settled before any `cache_state` claim. Point the
   SSD dir at the per-run scratch. [§5]
5. **KV pin**: `--paged-kv-quantization off|q8|q4` (default off) — names come from the
   runtime's own vocabulary, same shape as the existing `KV_QUANTS` pin. [§5]
6. **Sampler survey before the first cell**: record family + thinking default; no bundle
   penalty exists to pin; temperature is honored from the request (openai.py:17210-17232);
   loop guard and repetition stop are off. [§6, §7]
7. **Log/stats half**: a candidate receipt set exists (per-event `accepted`/`accept_probability`
   /`correction`, `greedy_draft`/`greedy_target`, `mtplx_stats` in responses, MTP activation
   stats), but **the exact marker that proves "the head drafted in this cell" is not pinned
   yet** — that gate is the main to-do. [§3.3, §3.4; unverified list]
8. **Coherence gate** applies unchanged. And the one-variable rule: an MTPLX column declares
   the runtime axis with the engine named (its own MTP), not the same engine as OptiQ.

Recommended sequencing (INFERRED): (a) resolve the artifact question on one MTPLX-native pack
(Qwen 3.5/3.6 or the harness's JANG Qwen3.5-4B if its head loads); (b) run depth
`off/1/2/3` cells on that one artifact with cache and thinking pinned and the sampler recorded;
(c) only then widen to format-axis comparisons, where MTPLX's per-family support and its own
pack ecosystem become a variable that has to be declared.

---

## Unverified items (listed per the order)

1. **OptiQ/JANG sidecar loadability in MTPLX.** MTPLX resolves
   `mlx_lm_extra_tensors.mtp_file` (`artifacts.py:425-435`), the same pointer OptiQ uses, but
   whether MTPLX's head contract accepts an OptiQ-exported `optiq/mtp.safetensors` (prequant
   layout, fused-expert split) was not tested; a load is the coordinator's to run. [INFERRED
   risk from §3.1 + `docs/runtimes/optiq.md` §9.2]
2. **RAM session-bank disable.** No serve flag was found; only env budgets. Whether
   `MTPLX_SESSION_BANK_MAX_BYTES=0` (or `--per-session` 0) disables warm restore honestly is
   unverified. [§5]
3. **The "head drafted" log marker.** Candidate receipts are listed in §12.7; the exact line
   or stats field to gate a depth cell on is not pinned. [§3.4]
4. **Command-surface behaviour on a live 2.12.2.** `--depth`, `--no-mtp`,
   `--generation-mode`, `--ssd-session-cache` were read from source and help strings; no
   process was started (order forbids it). [§3.2, §5]
5. **T=0 token-identity vs MTPLX's own AR path.** The greedy commit rule was read; whether a
   depth-3 T=0 stream is token-identical to the same pack's `--no-mtp` stream on this hardware
   is exactly what the in-tree caveats say is not guaranteed. [§3.4]
6. **Vendor claims.** All mtplx.com and README numbers were read, not reproduced. [§1, §11]
7. **Thinking default per harness artifact.** Descriptor `default_mode` values were read
   generically; the Qwen3.5/3.6 native packs' entry must be read at pin time. [§7]

## Sources index

- Source: `youssofal/MTPLX@9882703f3105363ddc37eca9f97aa09a1d387112` (shared clone
  `/private/tmp/claude-501/mtplx-src`, read 2026-10-06). Files cited inline: `README.md`,
  `CHANGELOG.md`, `INSTALL.md`, `NOTICE`, `LICENSE`, `pyproject.toml`, `bin/mtplx`,
  `docs/server.md`, `docs/concurrency.md`, `docs/turbo-verify.md`, `docs/concurrency/qwen35b-mtp-batch.md`,
  `apps/MTPLXApp/README.md`, `dashboard/package.json`, `mtplx/{constants,sampling,draft_sampling,frspec_draft,attention_context,artifacts,kv_quant,turboquant,runtime_options,chat_encoding,reasoning_codecs,gemma4_pair,launch_lane,session_bank,cli}.py`,
  `mtplx/backends/{descriptors,registry}.py`, `mtplx/server/{openai,request_policy,stream_rate}.py`,
  `mtplx/{generation,fast_sampling}.py`, `mtplx/models/qwen4_exp.py`, `mtplx/cache_bank/cold_tier.py`.
- Web: https://github.com/youssofal/MTPLX ; https://mtplx.com/faq/ ;
  https://api.github.com/repos/youssofal/MTPLX ; commits/issues/PR search endpoints as cited.
