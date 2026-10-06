# MTPLX — operating surface and harness-integration points (2026-10-06)

**Purpose:** MTPLX's own operating reference for the runtime axis — install, version of
record, the `mtplx serve` command line, files and environment, the HTTP API and
per-request fields, ports, model selection, cold load and memory, stop, background
behaviour — then a hook-by-hook table against the `Runtime` class in
`ohyesmlx/runtimes.py`. It is the companion to
`docs/research/2026-10-06-mtplx-architecture.md` (mechanism and verdict) and is written
in the shape of `docs/runtimes/*.md` §1. Research only: no install, no model download,
no server start, no writes outside this file.

**Revision read:** `youssofal/MTPLX@9882703f3105363ddc37eca9f97aa09a1d387112`
("Release notes: the 2.12.2 gate results", 2026-10-03) via the shared `--depth 1` clone
at `/private/tmp/claude-501/mtplx-src`. All `file:line` citations below are relative to
that revision, with `$SRC` = `/private/tmp/claude-501/mtplx-src`. PyPI's attestation
for the 2.12.2 wheel and sdist names the same commit as the publishing commit
(https://pypi.org/project/mtplx/, read 2026-10-06), so the tree read here is the
released 2.12.2 tree, not a later `main`.

**Method / tiers:** source read first across the CLI, server, daemon-client and app
supervisor; web second, SearXNG then PyPI and the repo's own README/INSTALL. Claims are
labelled:

- **VERIFIED(source)** — read directly in the source at `9882703`, cited `file:line`.
- **VERIFIED(registry)** — read from PyPI's own record of the release.
- **CLAIMED(vendor)** — stated by MTPLX's docs/README/changelog but not code-read here.
- **INFERRED** — reasoning over verified facts; not stated by MTPLX.

**Cross-references:** `docs/research/2026-10-06-mtplx-architecture.md` (mechanism, MTP
implementation, license, verdict); `ohyesmlx/runtimes.py` (the hooks, the port table);
`docs/interfaces.md` "`ohyesmlx/runtimes.py` — issue #3" (the pinned shapes);
`AGENTS.md` (Decision 131 sampler survey, one-runtime-holds-weights, `peak_mb` caveat);
`docs/runtimes/optiq.md` §9.2 and `docs/runtimes/vmlx.md` §7.4.1 (what the harness
already measures for MTP).

---

## 1. Install, version of record, and what ships

**Three install channels, one artifact.** [VERIFIED(source): `INSTALL.md:3-39`;
README.md:39-58]

| Channel | Command | What lands on disk |
|---|---|---|
| DMG app | mtplx.com/download | app bundle that bootstraps its own engine (no Homebrew needed), puts `mtplx` on PATH |
| curl installer | `curl -fsSL https://raw.githubusercontent.com/youssofal/MTPLX/main/scripts/install_macos.sh \| bash` | venv at `~/.mtplx/venv`, durable launcher at `~/.local/bin/mtplx`; never writes into Homebrew's directories; `MTPLX_PYTHON` / `MTPLX_VENV` / `MTPLX_USER_BIN` / `MTPLX_GLOBAL_BIN` override the paths |
| Homebrew | `brew install youssofal/mtplx/mtplx` | tap formula |
| pip | `python3 -m pip install mtplx` | console script `mtplx = mtplx.cli:main` |

[VERIFIED(source): `scripts/install_macos.sh:14-26` (env knobs), `:33-52` (launcher
creation; it refuses to replace a file it did not create), `:76` (`launcher="$user_bin/mtplx"`);
`INSTALL.md:23` (venv path); `pyproject.toml:102-104` (console scripts, incl.
`mtplx-tune`)]

**Requirements:** Apple Silicon (M1 or newer), Python 3.11+, macOS 14+.
[CLAIMED(vendor): README.md:60; `INSTALL.md:5-10` says "macOS with MLX support";
pyproject classifiers say macOS]

**Version of record: 2.12.2.** [VERIFIED(source): `pyproject.toml:7`;
`mtplx/version.py:5`] [VERIFIED(registry): PyPI lists 2.12.2 as the latest release,
uploaded 2026-10-03, with the provenance attestation naming commit `9882703`; the
release history shows 2.11.3 → 2.12.0 → 2.12.1 → 2.12.2 inside three weeks
(https://pypi.org/project/mtplx/, read 2026-10-06)]

`mtplx --version` prints `mtplx 2.12.2` (a parenthetical `(<packaged>)` appears only
when the display version differs; they are the same string here).
[VERIFIED(source): `mtplx/cli.py:207-218`, `:2231-2235`]

**Runtime stack pins that matter to a cell.** `mlx==0.32.2` exactly — the pin's own
comment says 0.32.3 decodes at the same speed but is not bit-identical on Flash-Next
and the app bundles 0.32.2; `mlx-lm>=0.31,<0.32`;
`transformers>=5.10.0,!=5.13.0,<5.17`; plus fastapi/uvicorn/pydantic/safetensors/
numpy/rich/huggingface-hub/pillow/nanobind. No MLX fork: "MTPLX runs on stock PyPI
MLX; no fork is required for any profile". [VERIFIED(source): `pyproject.toml:14-63`;
`INSTALL.md:45`]

**Nothing in the installer installs a background item** — it writes a venv and a
launcher link and stops; see §9 for the app's supervisor. [VERIFIED(source):
`scripts/install_macos.sh:14-26`, `:33-52`]

## 2. The `mtplx serve` command line

**Shape of the process.** `mtplx serve` is a foreground wrapper. It resolves and gates
the model, prints a startup banner, then builds the child argv
`sys.executable -P -m mtplx.server.openai --model … --host … --port … --depth … …`
and — when `MTPLX_APP_PARENT_PID` is **not** set, which is the harness case —
`os.execvpe`s itself into it. The spawned pid *becomes* the server process.
[VERIFIED(source): `mtplx/commands/public.py:9975-9991` (child argv), `:10383-10391`
(`os.execvpe`); `:10374-10390` and `:10466-10474` are the app-parent path, where it
spawns a child instead and runs a watchdog]

A busy port is refused before anything loads: `error: port <N> is already in use` with
occupant-aware advice, exit 2 (the four `mtplx start` quickstart surfaces attach to an
existing healthy daemon instead of refusing). [VERIFIED(source):
`mtplx/commands/public.py:9698-9701`, `:9841-9853`; the quickstart attach branches at
`:9701-9840`]

**Every option the `serve` parser declares.** The parser block is `mtplx/cli.py:3610-3938`
and its block helpers are at `:606-908`; these tables are the whole surface, read from
source rather than `--help`.

### 2.1 Model, profile and startup

| Flag | Default | Notes |
|---|---|---|
| `--model` | `DEFAULT_HF_MODEL_ID` = the Qwen 3.8 27B Optimized Speed pack (`Youssofal/Qwen3.8-27B-MTPLX-Optimized-Speed`) | local path or HF repo id [VERIFIED(source): `mtplx/cli.py:3613`, `:2237`; `mtplx/profiles.py:158`, `:207`; README.md:106] |
| `--model-id` | `DEFAULT_PUBLIC_MODEL_ID` = `mtplx-qwen38-27b-optimized-speed`; otherwise derived from the artifact | the id `/v1/models` answers to; "defaults to the loaded artifact identity" [VERIFIED(source): `mtplx/cli.py:3844-3848`; `mtplx/profiles.py:165`, `:212`; derivation `mtplx/commands/public.py:11931-11939` → `mtplx/default_models.py:561-576`] |
| `--cache-dir` | — | model cache root override |
| `--model-search-dir DIR` | — | additional read-only library root; repeatable [VERIFIED(source): `mtplx/cli.py:633-640`] |
| `--download` | off | download an HF model before starting if it is not cached |
| `--profile NAME` | `sustained` (`DEFAULT_PROFILE_NAME`); per-model resolution picks `turbo` for the quantized 27B/9B flagships and the Flash-Next packs | **profiles carry env sets, including `MTPLX_LONG_CONTEXT_MTP_DEPTH*` on Turbo** — record the resolved profile with a cell [VERIFIED(source): `mtplx/cli.py:3621-3632`; `mtplx/profiles.py:16`, `:417-419`, `:572-574`] |
| `--unsafe-force-unverified` | off | bypass the model-compatibility gate |
| `--agent-rewrites {on,off}` | unset = passthrough | "off is a hard passthrough guarantee"; unset already injects nothing |
| `--yes` | off | confirm unsafe non-interactive actions |

### 2.2 Network and auth

| Flag | Default | Notes |
|---|---|---|
| `--host` | `127.0.0.1` | non-localhost binds require `--api-key`/`--api-key-file` [VERIFIED(source): `mtplx/cli.py:3650-3658`; `mtplx/commands/public.py:9608-9625`] |
| `--port` | **8000** | collides with vMLX's 8000 — §5 |
| `--no-auth` | off | disables key auth on a localhost bind |
| `--api-key` | None | Bearer or X-API-Key required when set |
| `--api-key-file` | — | missing file is created with a fresh key, printed once |
| `--rate-limit N` | 0 (off) | requests/min per client key |

### 2.3 MTP and draft control (the flags the depth pin would drive)

| Flag | Default | Notes |
|---|---|---|
| `--depth N` | 3 | native-MTP draft depth [VERIFIED(source): `mtplx/cli.py:3665`] |
| `--mtp` / `--no-mtp` | neither = engine default (`load_mtp=True`, mode `auto`) | `--no-mtp` = target-only AR on the same loaded runtime [VERIFIED(source): `mtplx/cli.py:700-716`] |
| `--generation-mode {mtp,ar,auto}` | None = pack's recommended mode, falling back to MTP | [VERIFIED(source): `mtplx/cli.py:3667-3676`] |
| `--load-mtp` / `--no-load-mtp` | True | `--no-load-mtp` for stock-AR diagnostics |
| `--stock-ar` | off | diagnostic: target AR, no sidecar |
| `--draft-temperature` / `--draft-top-p` / `--draft-top-k` | unset | draft sampler; correctness never depends on it (architecture doc §3.4) |
| `--verify-strategy` | `capture_commit` | 8 choices (batched, sequential, capture, capture_commit, graphbank, graphbank_capture_commit, trim_commit, target_prefix) |
| `--verify-core` | `linear-gdn-from-conv-tape` | |
| `--draft-core` | `stock` | `device-d2`, `device` available |
| `--mtp-adapter PATH`, `--merge-mtp-adapter` | — | MTP LoRA adapter |
| `--mtp-quant-bits`, `--mtp-quant-group-size` (64), `--mtp-quant-mode {affine,symmetric}` | unset / 64 / affine | quantize the loaded MTP head |
| `--adaptive-policy {none,streak,expected_value,cost}` + 16 `--adaptive-*` economics flags | `none` | default none = fixed depth; the family lane can install a default policy (architecture doc §3.2) [VERIFIED(source): `mtplx/cli.py:875-908`] |

### 2.4 Sampling defaults, streaming, batching, caches

| Flag | Default | Notes |
|---|---|---|
| `--default-temperature`/`--temperature` | 0.6 | request `temperature: 0` overrides — §4.3 |
| `--default-top-p`/`--top-p`, `--default-top-k`/`--top-k` | 0.95 / 20 | [VERIFIED(source): `mtplx/cli.py:3766-3778`] |
| `--default-presence-penalty`, `--default-frequency-penalty` | 0.0 / 0.0 | exact no-op at default (vendor wording) [VERIFIED(source): `mtplx/cli.py:3779-3790`] |
| `--max-tokens` (dest `max_response_tokens`), `--context-window` | None | server-side response ceiling / window override |
| `--stream-interval N` | 1 | committed tokens per SSE chunk [VERIFIED(source): `mtplx/cli.py:3709-3714`] |
| `--stream-stall-deadline-s` | env `MTPLX_STREAM_STALL_DEADLINE_S` or 300 | watchdog; 0 off |
| `--allow-swap` | off | admit prompts past the memory fit (507 otherwise) |
| `--scheduler-mode` | `serial` | choices from the `SchedulerMode` enum (serial, cooperative, ar_batch, mtp_batch, mtp_cohort_experimental, hyper) [VERIFIED(source): `mtplx/cli.py:776-792`; architecture doc §4] |
| `--batching-preset` | `latency` | solo/latency/agent/throughput |
| `--mtp-batch-numerics` | `throughput` | Qwen MTP route: fast B8 / balanced B8 / serial B1-exact |
| `--max-active-requests`, `--decode-batch-max`, `--batch-wait-ms`, `--prefill-chunk-tokens` | None | refuse in `hyper` mode (architecture doc §4) |
| `--experimental-mtp-cohorts` | off | |
| `--ssd-session-cache {off,on,write-only}` | **on** | persistent SessionBank cold tier; writes to `~/.mtplx/session-bank` or `--ssd-session-cache-dir` [VERIFIED(source): `mtplx/cli.py:816-845`; docs/server.md:209-223] |
| `--ssd-session-cache-max-size` (auto), `--ssd-session-cache-min-prefix-tokens` (512) | | |
| `--paged-kv-quantization` / `--paged-kv-quant` / `--kv-quant {off,q8,q4}` | **off** | paged-KV codec; see §10's kv_quant row for the naming mismatch with the harness values |
| `--ngram-prewarm auto\|all\|off\|GiB` (+ `--no-ngram-prewarm`, `--ngram-prewarm-order PATH`) | flag unset; env `MTPLX_NGRAM_PREWARM` unset → auto | Flash-Next's streamed n-gram table pre-read at load; a load-time SSD read inside `cold_load_s` [VERIFIED(source): `mtplx/cli.py:726-773`; docs/server.md:46-77] |

### 2.5 Reasoning, memory, startup extras

| Flag | Default | Notes |
|---|---|---|
| `--reasoning {auto,on,off}` | auto | "use `--reasoning off` for terse/non-reasoning runs" [VERIFIED(source): `mtplx/cli.py:606-616`] |
| `--reasoning-effort` | `auto` | levels are per-model [VERIFIED(source): `mtplx/cli.py:619-630`] |
| `--reasoning-parser {qwen3,step3p5,gemma4,poolside_v1,none}` | qwen3 | |
| `--preserve-thinking {auto,on,off,scoped}` (+ hidden `--strip-assistant-reasoning-history`) | auto | history policy for Qwen templates |
| `--tool-prompt-mode {hybrid,native}` (hybrid), `--chat-template-profile` (local_qwen36), `--chat-template-path` | | [VERIFIED(source): `mtplx/cli.py:677-697`] |
| `--memory-limit SIZE\|max` | 75% of RAM; ≤ RAM−38 GiB from 128 GB up | engine Metal limit; env `MTPLX_MEMORY_LIMIT_BYTES` [VERIFIED(source): `mtplx/cli.py:3753-3765`; `mtplx/server/openai.py:2849-2870`] |
| `--warmup-tokens N` | **16** | startup generation (see §7); 0 disables |
| `--strict-warmup` | off | fail startup if the warmup pass fails |
| `--fan-mode {default,smart,max}` / `--max` / `--require-max-fans` / `--enable-thermal-poll` | default | fans; thermal poll off by default [VERIFIED(source): `mtplx/cli.py:663-674`, `:3896-3912`] |
| `--no-stats-footer` | footer on, but API clients never receive it since 2.5.3 | pass it for a deterministic body anyway [CLAIMED(vendor): docs/server.md:327-331; env `MTPLX_STATS_FOOTER_SCOPE` in the census] |
| `--app-launch-id`, `--open-browser` | — | app surfaces |
| `--embedding-model REF[=ID]`, `--reranker-model REF[=ID]` (repeatable), `--retrieval-max-resident` (2), `--retrieval-idle-timeout` (0), `--retrieval-max-tokens` (0), `--retrieval-trust-remote-code` | | opt-in retrieval models; loaded on first request; `/v1/models` stays chat-only by default [VERIFIED(source): `mtplx/cli.py:3849-3888`; `mtplx/server/openai.py:37496-37513`] |
| `--strict-fast-path` | deprecated no-op | stock MLX, no fork |

Globals: `mtplx --no-color`, `mtplx --version`; most inspection commands take
`--json`. [VERIFIED(source): `mtplx/cli.py:2226-2235`]

**Two defaults that decide what an idle cell measures even though nobody passes them:**
`scheduler-mode` is `serial` — one request at a time on the MTP oracle lane — and
`stream-interval` is 1, so every committed token is its own SSE chunk (subject to the
coalescing/pacer described in the architecture doc §8). [VERIFIED(source):
`mtplx/cli.py:776-792`, `:3709-3714`]

## 3. Files and environment variables

### 3.1 Files

| Path | What it is | Evidence |
|---|---|---|
| `~/.mtplx/venv` | installer's venv (default `MTPLX_VENV`) | `INSTALL.md:23`; `scripts/install_macos.sh:19-22` |
| `~/.local/bin/mtplx` | installer's launcher (default `MTPLX_USER_BIN`) | `scripts/install_macos.sh:21`, `:76` |
| `~/.mtplx/config.toml` | user config; `model_dir` (writable primary), `model_dirs` (ordered discovery roots), `embedding_models`, `reranker_models` | `mtplx/config.py:18` (`DEFAULT_CONFIG_PATH`); [CLAIMED(vendor): PyPI README "Model libraries" and "Embeddings and reranking"] |
| `~/.mtplx/models` | default model cache directory (`MTPLX_MODEL_DIR` default per `mtplx setup --model-dir` help) | [VERIFIED(source): `mtplx/cli.py:2469-2472`] |
| `~/.mtplx/session-bank` | default SessionBank SSD cold tier (`--ssd-session-cache-dir`) | docs/server.md:211, `:249-250`; `mtplx/cli.py:2542` |
| `~/.mtplx/api-key` | the key file path the CLI itself suggests for non-localhost binds | [VERIFIED(source): `mtplx/cli.py:3656`, `:9623`] |
| `~/Library/Application Support/MTPLX/settings.json` | the macOS app's persisted config (`MTPLX_APP_SETTINGS_PATH` overrides) | [VERIFIED(source): `mtplx/app_settings.py:4`, `:24-26`; `apps/MTPLXApp/README.md:34`] |

There is **no pid file**. A running daemon is identified by `/health` — `startup.pid`,
`startup.launch_id` (present only for app-launched daemons), `model`, `model_path` —
or by `lsof` on its port. [VERIFIED(source): `mtplx/daemon_client.py:82-124`, `:275-300`,
`:301-322`; `mtplx/server/openai.py:36319` (`_startup_health_payload`)]

### 3.2 Environment variables

The package tree mentions **762 distinct `MTPLX_*` names**
(`rg -o "MTPLX_[A-Z0-9_]+" mtplx/ | sed 's/.*://' | sort -u | wc -l` at `$SRC`), most of
them per-family kernel switches whose defaults are the shipped ones. The ones a cell or
a pin must know:

| Variable | Default | Meaning |
|---|---|---|
| `MTPLX_MEMORY_LIMIT_BYTES` | same rule as `--memory-limit` | engine Metal limit; the flag wins |
| `MTPLX_WIRED_LIMIT_BYTES` | `min(engine limit, max(4 GiB, 60% RAM), 160 GiB)` | MLX wired-residency cap set at startup [VERIFIED(source): `mtplx/server/openai.py:2826-2827`, `:2866-2870`] |
| `MTPLX_MLX_CACHE_LIMIT` | RAM tier, 8 GiB at ≥100 GB; `off` disables | reclaimable MLX buffer pool; returned to macOS after each request unless `MTPLX_CLEAR_CACHE_AFTER_REQUEST=off` [CLAIMED(vendor): docs/server.md:124-136] |
| `MTPLX_SESSION_BANK_IDLE_TTL_S` / `_ACTIVE_PIN_TTL_S` / `_MAX_BYTES` / `_PER_SESSION_BYTES` / `_MAX_ENTRIES` | 3600 / 600 / auto (≤48 GiB) / auto / 24 (48) | RAM session-bank budgets — **env-only; no serve flag was found for them** [CLAIMED(vendor): docs/server.md:172-178] |
| `MTPLX_SSD_SESSION_CACHE` / `_DIR` / `_MAX_SIZE` / `MTPLX_SSD_WRITE_BUDGET_PER_HOUR` / `MTPLX_SSD_WRITER_BACKLOG_BYTES` | on / ~/.mtplx/session-bank / auto / 128G / 4G | SSD cold-tier equivalents of the flags [VERIFIED(source): flag surface `mtplx/cli.py:816-845`; [CLAIMED(vendor): docs/server.md:218-223]] |
| `MTPLX_NGRAM_PREWARM` (+ `MTPLX_NGRAM_PREWARM_ORDER`) | unset → auto | the flag overrides [VERIFIED(source): `mtplx/cli.py:726-773`] |
| `MTPLX_STREAM_STALL_DEADLINE_S` | 300 | stream watchdog |
| `MTPLX_CLIENT_CONTROLS_DEFAULT` | `honor` (since 2.5.3) | anonymous clients' explicit body params are applied — the flip's own reason is exactly "tools send temperature:0 expecting OpenAI semantics" [VERIFIED(source): `mtplx/server/openai.py:17210-17232`] |
| `MTPLX_MANAGED_CLIENT_CONTROLS` | `auto` | app policy for connected clients (pi/opencode/hermes/openwebui) [VERIFIED(source): `mtplx/server/openai.py:17257-17275`] |
| `MTPLX_LONG_CONTEXT_MTP_DEPTH_POLICY` / `_THRESHOLD` / `MTPLX_LONG_CONTEXT_MTP_DEPTH` | **`off`** / 98304 / 2 | context-aware depth cap; off means a D3 request stays D3 at long context [VERIFIED(source): `mtplx/profiles.py:572-574`, `:633-674`] |
| `MTPLX_GREEDY_DRAFT_CHAIN`, `MTPLX_EXPERIMENT_DEPTH_CEILING` | (present in census) | greedy-chain selection / depth ceiling — defaults not read here |
| `MTPLX_THINKING_BUDGET` | off | opt-in thinking budget | 
| `MTPLX_LOOP_GUARD`, `MTPLX_REPETITION_STOP` | off (project policy since 2.12.0) | sampler interventions, opt-in [VERIFIED(source, read at this revision): architecture doc §6; `CHANGELOG.md:46`] |
| `MTPLX_STATS_FOOTER_SCOPE` | app surfaces only | `all` restores pre-2.5.3 footer [CLAIMED(vendor): docs/server.md:327-331] |
| `MTPLX_APP_SETTINGS_PATH`, `MTPLX_APP_PARENT_PID`, `MTPLX_APP_LAUNCH_ID` | — | app integration: settings file, child-watchdog switch, daemon ownership marker [VERIFIED(source): `mtplx/app_settings.py:24`; `mtplx/commands/public.py:10372-10405`; `mtplx/daemon_client.py:283-291`] |

## 4. HTTP API

One FastAPI/uvicorn app serves OpenAI- and Anthropic-compatible routes on
`http://127.0.0.1:8000` by default. [VERIFIED(source): `mtplx/server/openai.py:44639-44646`;
docs/server.md:1-8]

### 4.1 Routes

| Method / path | Purpose | Source |
|---|---|---|
| `GET /health` | readiness + full state (model, generation_mode, depth, mtp_enabled, sampler, memory guard, session bank, warmup) | `mtplx/server/openai.py:36254-36366` |
| `GET /metrics` | Prometheus-style metrics | `:37426` |
| `GET /v1/models` | chat model list (exactly the loaded model by default) | `:37496-37555` |
| `POST /v1/chat/completions` | the measured route; SSE when `stream: true` | `:37679` |
| `POST /v1/completions` | legacy completions | `:42590` |
| `POST /v1/responses` | Codex Responses compatibility (stateless text + client tools) | `:42457` |
| `POST /v1/messages`, `/v1/messages/count_tokens` | Anthropic Messages compatibility | `:42520`, `:42552` |
| `POST /v1/embeddings`, `POST /v1/rerank` | opt-in retrieval models | `:37557`, `:37638` |
| `GET /admin/sessions`, `POST /admin/sessions/{id}/clear`, `POST /admin/cache/clear`, `GET /admin/cache/ssd`, `POST /admin/cache/ssd/archive` | session/cache administration | `:37436-37500` |
| `GET|POST /v1/mtplx/settings`, `GET /v1/mtplx/snapshot`, `GET /v1/mtplx/flight`, `POST /v1/mtplx/cancel/{request_id}`, thermal/app/benchmark surfaces | live control and telemetry | `:36578-37440` |
| `GET /` , `GET /v1`, `GET /dashboard` | human surfaces | `:36193`, `:36225`, `:43347` |

### 4.2 Auth on the loopback bind

With no key configured — the default on a `127.0.0.1` bind — every route is
authorized (`_request_is_authorized` returns True). When `--api-key` /
`--api-key-file` is set, an ASGI middleware answers 401 "missing or invalid API key"
(Bearer or X-API-Key) on **every** JSON route, `/health` and `/v1` included; only the
`/dashboard` static bundle and the browser sign-in bootstrap are exempt.
[VERIFIED(source): `mtplx/server/openai.py:5341-5345`, `:29995-30018`, `:36095-36121`]

### 4.3 Per-request fields, honoured and how

| Field(s) | Resolution / gate | Evidence |
|---|---|---|
| `max_tokens`, `max_completion_tokens` | `max_tokens` wins; the alias is the fallback | `mtplx/server/openai.py:1786-1787`, `:16886-16891` |
| `temperature`, `top_p`/`topP`, `top_k`/`topK`, `presence_penalty`, `frequency_penalty` | request value → server default → built-in; explicit anonymous params honoured because `MTPLX_CLIENT_CONTROLS_DEFAULT=honor` (the flip was made because tools sending `temperature: 0` were being served the 0.6 coding sampler). Managed-client hints (mtplx/opencode/openwebui/pi/hermes) are server-owned | `mtplx/server/openai.py:17210-17345`, `:17278-17316` |
| `seed` | request seed → server seed → fresh random (`_fresh_seed`) | `mtplx/server/openai.py:1801`, `:28884-28904` |
| `stream` | SSE chat chunks; the final chunk always carries `usage` and `mtplx_stats` | `:42086-42099` |
| `stream_options` | declared in the schema and recorded in observability; **no branch reads `include_usage` — usage is emitted unconditionally in the final chunk**, so the harness's `stream_options.include_usage` request is accepted and its usage read works | `:1809`, `:26097-26101`, `:42093-42099` |
| `enable_thinking`, `reasoning_effort` | honoured under the same client-controls gate (thinking controls allow anonymous callers by default) | `:1802-1803`, `:17300-17316`, `:35548-35579` |
| `depth` (aliases `mtp_depth`, `speculative_depth`, `draft_block_size`, `gemma_draft_block_size`) | **per-request MTP draft depth**: resolved by backend-descriptor priority, clamped to the descriptor's `[minimum, maximum]`, out-of-range is HTTP 400; gate is the same client-controls rule | `:1797-1799`, `:17066-17114`, `:17348-17391`; `mtplx/server/request_policy.py:359-363` |
| `generation_mode` (`mtp`/`ar`) | per-request override; `mtp` on a runtime loaded without MTP is HTTP 400 | `:17040-17063` |
| `chat_template_kwargs`, `metadata`, `tools`, `tool_choice`, `stop`, `response_format`, `user` | accepted; `metadata` carries the client-controls opt-ins | `:1781-1820` |

**Two depth policies can move a depth after the request arrives, and both are off by
default.** The OpenCode short-context policy is a no-op returning the requested depth
unchanged ("disabled_depth_preservation"); the long-context cap resolves through
`resolve_long_context_mtp_depth`, whose defaults are `policy=off`. A depth cell should
still record that it kept the defaults (or pinned the envs), exactly as the vMLX
`fixed` discipline requires. [VERIFIED(source): `mtplx/server/openai.py:17394-17446`;
`mtplx/profiles.py:615-674`]

**Receipts available for a depth cell.** The final SSE chunk carries
`mtplx_stats`, and the CLI's own stats reader names `mtp_depth`, `accept_rate`,
`decode_tok_s`, `ttft_s`, `request_elapsed_s` — candidate evidence for the log/stats
half of `mtp_depth_missing`, though the exact "the head drafted" marker is still to be
pinned (architecture doc's unverified list §12.3). [VERIFIED(source):
`mtplx/daemon_client.py:716-728`]

## 5. Ports and port conflicts

| Runtime / surface | Port | Conflict with MTPLX (8000) |
|---|---|---|
| **MTPLX `mtplx serve --port` default** | **8000** | — |
| vMLX | 8000 | **direct collision** — the Runtime classes must hand MTPLX a free port [VERIFIED(source): `mtplx/cli.py:3659`; `ohyesmlx/runtimes.py:2965`] |
| Osaurus | 1337 | none |
| optiq | 8080 | none |
| mlx_lm.server | 8081 | none |
| oMLX | 8100 | none |

[VERIFIED(source): harness ports `ohyesmlx/runtimes.py:2960-2966`; MTPLX default
`mtplx/cli.py:3659`; the vendor's own quick starts use `http://127.0.0.1:8000` (README.md:84,
docs/server.md:7)]

`mtplx stop`/attach probing defaults to ports `(8000, 18083, 18084, 18085)` plus the
app's persisted port; `18083-18085` are `mtplx start`'s per-target defaults
(opencode/swival/hermes), so they can collide with nothing the harness runs today.
[VERIFIED(source): `mtplx/daemon_client.py:27-29`, `:151-174`]

A second `mtplx serve` on a held port exits with the occupant's classification instead
of binding. [VERIFIED(source): `mtplx/commands/public.py:9698-9701`, `:9841-9853`]

## 6. Model selection and restricting to one model

- `--model` takes a **local directory path or an HF repo id**; `--download` fetches a
  repo id that is not cached. [VERIFIED(source): `mtplx/cli.py:3613-3620`;
  `mtplx/cli.py:2296` (start's help: "Verified model path or Hugging Face repo id")]
- Additional library roots: `--model-search-dir` (repeatable) on the command, or
  `model_dir` / `model_dirs` in `~/.mtplx/config.toml` / `MTPLX_MODEL_DIRS`.
  [VERIFIED(source): `mtplx/cli.py:633-640`; [CLAIMED(vendor): PyPI README "Model
  libraries"]]
- **Exactly one chat model is served.** `/v1/models` builds a single chat entry from
  `state.model_id`; retrieval models appear only with `?capability=embedding|rerank`
  and only when `--embedding-model` / `--reranker-model` were passed. There is no
  catalog to prune — unlike oMLX, no per-run catalog directory is needed to keep other
  models invisible. [VERIFIED(source): `mtplx/server/openai.py:37496-37555`]
- The served id is either `--model-id` explicitly or derived from the artifact by
  `public_model_id_for_ref` (lowercased, sanitized slug; a path symlink resolves to the
  canonical artifact's name). The startup log prints `Model: <id>` and `/health`
  returns `model` and `model_path`, so the harness does not have to re-derive the id —
  **pass `--model-id` explicitly with the candidate the run will check**, or read
  `/health`. [VERIFIED(source): `mtplx/commands/public.py:11927-11939`;
  `mtplx/default_models.py:561-576`; `mtplx/server/openai.py:36292-36295`, `:44575`]
- Before serving, the wrapper runs the model-compatibility gate and refuses
  incompatible artifacts unless `--unsafe-force-unverified`; the vendor's framing is
  "no silent fallbacks". [VERIFIED(source): `mtplx/commands/public.py:9925-9936`;
  [CLAIMED(vendor): PyPI README "Compatibility, honestly"]]
- **The artifact contract is the open question, not the surface**: whether MTPLX loads
  an OptiQ/JANG artifact or only its own packs is the sibling document's unverified
  item §12.1, and nothing in this surface read changes it.

## 7. Cold load and memory

**Order of operations.** `main()` parses args, applies the memory caps, constructs
`ServerState` — which **loads the runtime and runs the startup warmup inside its
constructor** — then creates the app, prints `MTPLX is ready.`, and only then calls
`uvicorn.run`. The port opens *after* weights and warmup; there is no
"bind-then-load-late" window like oMLX's. [VERIFIED(source):
`mtplx/server/openai.py:44538-44557`, `:4094` (`self.warmup_status = _run_startup_warmup(self)`),
`:44639-44646`]

**Startup warmup is a real cost inside `cold_load_s`.** The default `--warmup-tokens 16`
runs one generation (`"MTPLX warmup."`, seed 0, the configured sampler) and prints
`[6/6] Warming model with 16 tokens`; `--warmup-tokens 0` skips it with its own line.
A failed warmup is fatal only under `--strict-warmup`. `[n/6]`-numbered lines are the
startup banner's shape. [VERIFIED(source): `mtplx/server/openai.py:32351-32408`
and the `[n/6]` labels at `:4066`, `:4075`, `:32361-32364`; flag default
`mtplx/cli.py:3922-3932`]

**Readiness signals.** `log_level="warning"` and `access_log=False` mean uvicorn prints
no "Uvicorn running" banner — the readiness signal is the startup lines then `/health`
(`ok: true`) or `/v1/models`. A load failure happens before the port is bound, so a
failed start exits rather than serving a dead socket. [VERIFIED(source):
`mtplx/server/openai.py:44639-44646`; `mtplx/server/openai.py:36254-36292`]

**Memory caps at startup.** The server sets both MLX limits before the model loads:
`mx.set_memory_limit` (default 75% of RAM, ≤ RAM−38 GiB from 128 GB up, `max` =
everything outside macOS's reserve) and `mx.set_wired_limit` (default
`min(engine limit, max(4 GiB, 60% of RAM), 160 GiB)`, clamped to what macOS allows and
reported in `applied`). [VERIFIED(source): `mtplx/server/openai.py:2810-2958`]

**Wired vs anonymous, for `footprint -p`.** MTPLX's own memory guard describes what the
engine allocates as **wired memory in the kernel's accounting** ("wired went from 4.4 GB
to …", and the wired term drives its floors), and its docs describe a 128 GB Mac wiring
~85 GB of weights. `phys_footprint` (what `sample.py` samples) includes wired pages, so
a MTPLX cell's `peak_mb` is measurable — but per `AGENTS.md` it is sound only *within*
a runtime: this is exactly the Osaurus-style accounting the `peak_mb` caveat names, and
MTPLX rows must not be ranked on `peak_mb` against runtimes that hold weights
anonymously. `/health` and `/v1/mtplx/snapshot` report the process's own
`phys_footprint_bytes` and `host_overhang_bytes`, which is a corroborating reading the
harness can record beside the sampler's. [VERIFIED(source): `mtplx/system_memory.py:461-477`;
[CLAIMED(vendor): docs/server.md:74-75, `:196-202`]; `AGENTS.md` "Peak memory"]

**Other memory the cell should pin.** The RAM session bank holds warm KV after a turn
(budgets env-only, §3.2); the SSD cold tier is on by default and writes to
`~/.mtplx/session-bank` unless pointed elsewhere; the n-gram pre-read (default `auto`)
reads up to the whole streamed table into the page cache **during the load**, so on a
Flash-Next pack it is inside `cold_load_s` unless `--ngram-prewarm off`. Mirror the
oMLX rule: point `--ssd-session-cache-dir` at the per-run scratch so `stop()` removes
it. [VERIFIED(source): `mtplx/cli.py:816-845`, `:726-773`; `ohyesmlx/runtimes.py`
`Omlx.start_command` comment]

## 8. Stopping it, and confirming the port is free

- **Foreground:** Ctrl-C/SIGTERM; uvicorn runs with `timeout_graceful_shutdown=5` and
  atexit cleanup, and the comments record a session-bank flush on a clean SIGTERM/Ctrl-C
  (a plain kill used to lose entries still in flight). [VERIFIED(source):
  `mtplx/server/openai.py:44626-44646`, `:24486`, `:36061`]
- **`mtplx stop [--host H] [--port N] [--grace-seconds 10] [--json]`:** finds the
  daemon via `/health` (`startup.pid`), sends SIGTERM, polls process exit every 0.2 s,
  escalates to SIGKILL after the grace; with `--port` omitted it probes
  `8000/18083/18084/18085` (+ app port) and refuses ambiguously if several answer.
  [VERIFIED(source): `mtplx/cli.py:2515-2532`; `mtplx/daemon_client.py:475-551`;
  `mtplx/commands/public.py:2956-2991`]
- **What it refuses:** a port that is not MTPLX (`not_mtplx` — a wedged daemon stops
  answering `/health` and reads as foreign), no reported pid, or permission denied;
  the copy tells you to kill the pid by hand. [VERIFIED(source):
  `mtplx/commands/public.py:3004-3021`; `mtplx/daemon_client.py:422-449`]
- **Port release:** `mtplx stop` returns when the *process* is gone; it does not
  itself lsof the port. The harness's `Handle.stop` → `_shutdown` → `await_port_free`
  remains the confirmation, and its SIGTERM-to-the-spawned-pid fallback reaches the
  server directly because `serve` exec'd into it (§2). [VERIFIED(source):
  `ohyesmlx/runtimes.py:1438-1483`; `mtplx/daemon_client.py:527-551`]

## 9. Background and Login-Item behaviour

- **The CLI installs no background item.** The installer writes a venv and a launcher
  link; nothing else in the CLI paths read here installs a LaunchAgent, a LaunchDaemon
  or a login item. [VERIFIED(source): `scripts/install_macos.sh:14-26`, `:33-52`;
  searches over `apps/MTPLXApp/Sources` and `scripts/` for
  `SMAppService|ServiceManagement|LoginItem|LaunchAgent|launchctl` returned no
  shipped-code hits — the only `launchctl` matches in the tree are test fixtures under
  `docs/laguna-mlxfast-port/`. The shipped app bundle's `Info.plist` is not in this
  repository, so the DMG app's own login behaviour is not closed from source here.]
- **The app is a supervisor, not an inference process.** `DaemonSupervisor` launches a
  hidden `mtplx serve` with `Process`, captures logs, probes `/health`, and "stops
  gracefully before force kill"; inference stays in the `mtplx` daemon.
  [VERIFIED(source): `apps/MTPLXApp/README.md:10-34`]
- **The app's presence is detectable and changes the CLI's process shape:** it sets
  `MTPLX_APP_PARENT_PID`, which flips `serve` from `exec` to spawn-child-plus-watchdog,
  and `/health.startup.launch_id` marks an app-owned daemon; `mtplx start`/`serve`
  quickstart surfaces attach to an existing healthy daemon rather than loading a
  second copy. [VERIFIED(source): `mtplx/commands/public.py:10372-10405`, `:9701-9840`;
  `mtplx/daemon_client.py:107-124`, `:275-300`]
- The vendor docs say the app's daemon "inherits the login environment" (relevant when
  pinning env-var-only settings from a harness vs against the app's daemon).
  [CLAIMED(vendor): docs/server.md:169-170]

**Harness consequence (INFERRED):** before starting MTPLX, the port check and the
resident-process check the harness already performs are the guard that matters here;
if the app is running, it may hold a daemon on 8000 and `serve` will refuse that port
(it does **not** silently attach). Do not fight it over the port — give the cell a
free one, as the harness does for every runtime.

## 10. Hook-by-hook: what MTPLX offers the `Runtime` class

The hooks are read from `ohyesmlx/runtimes.py` and `docs/interfaces.md` ("the pinned
shapes"). "Ready" means the surface exists at `9882703`; "gap" names what is missing
for a measured cell.

| Hook (harness) | What MTPLX offers | Evidence | State |
|---|---|---|---|
| `start_command` | `mtplx serve --model <artifact> --host 127.0.0.1 --port <free> ...` — exec's into the server, so the spawned pid is the serving pid; `--no-auth` unnecessary on loopback (no key = authorized); pass `--no-stats-footer` for a deterministic body; add the pins below as the run declares them | §2; `mtplx/commands/public.py:10383-10391`; `mtplx/server/openai.py:5341-5345` | ready |
| health check (`await_ready`: model id in `/v1/models` + no load error in log) | `/v1/models` returns exactly one chat entry = `state.model_id`; `/health` returns `ok`, `model`, `model_path`; the log carries `[n/6]` startup lines and `MTPLX is ready.`; a load failure precedes the port bind, so the process exits rather than serving a dead socket. **Pass `--model-id` with the id the readiness check will look for** (or read `/health.model`) instead of re-deriving the slug | §4.1, §6, §7 | ready |
| `request_seed` | The body schema carries `seed`; resolution request → server (none by default) → fresh random. At temperature 0 the harness's base policy (send none) is safe: greedy output does not depend on the RNG. No code path was found that gates scheduling or batching on a seed (unlike mlx-lm's sequential-path gate), so the OptiQ-style exception is **not** needed — INFERRED, to be confirmed on the first live cell | §4.3; `mtplx/server/openai.py:28884-28904` | ready (inferred) |
| version string | `mtplx --version` → `mtplx 2.12.2`; parse off the `mtplx ` prefix | §1; `mtplx/cli.py:207-218` | ready |
| `cache_state` on/off | **on**: `--ssd-session-cache on` (default) + RAM bank budgets env-set; **off**: `--ssd-session-cache off` is a real flag, and the SSD dir can be pointed at the run scratch — but the **RAM session bank has no serve flag found** (budgets are env-only). Whether a zero/absent budget honestly disables warm restore is unverified; until probed, an `off` cell cannot be claimed | §2.4, §3.2; `mtplx/cli.py:816-845`; docs/server.md:158-178 | **gap** |
| stop | `mtplx stop --port <p>` (health-pid SIGTERM → SIGKILL after grace); plain SIGTERM to the spawned pid also reaches uvicorn directly; harness's `await_port_free` still confirms the port | §8 | ready |
| `kv_quant` (extra pin) | `--paged-kv-quantization {off,q8,q4}` (default off) is a real start flag, but the harness values name **MLX affine** codecs (`affine8`/`affine4` = int codes + scales + biases); MTPLX's q8/q4 is "symmetric per-head quantization with fp32 scales" — a different codec, so a codec cell needs a new value or a refusal, not a rename | §2.4; architecture doc §5 | mismatch to decide |
| `mtp_depth` (extra pin) | Start flags `--depth N` + `--generation-mode mtp` (and `--no-mtp` for off); per-request `depth` also exists. Family caps apply (qwen3_8 max 3 in the descriptor; qwen4_exp is a ceiling under an adaptive policy), and the log/stats half ("the head drafted at depth N") is not yet pinned | §2.3, §4.3; architecture doc §3.2, §12.7 | partially ready; **log half is a gap** |
| `stream_experts` (extra pin) | No expert-streaming surface was found in the `serve` parser or the modules read; the base class's default (refuse `on`, accept `off`) is the honest answer — recorded as "no surface found", not "cannot" | §2; `ohyesmlx/runtimes.py:1613-1626` | n/a by default |

## 11. What a sixth runtime would need (integration reading)

INFERRED, over the verified surface above:

1. **Port**: MTPLX must be given the harness's free port — its default 8000 is vMLX's.
   Nothing else about the mapping is contested: `start_command`, stop, version and
   readiness all have direct answers.
2. **Sampler survey (Decision 131) is short**: request `temperature: 0` is honoured
   (client-controls default `honor`), penalties default 0.0, no bundle
   `generation_config` penalty path exists (architecture doc §6), loop guard and
   repetition stop are off; the two things to record per artifact are the **thinking
   default** and the **resolved profile** (a profile can install long-context depth
   envs).
3. **The three practical gaps before a depth cell**: (a) a RAM-bank `off` that can be
   honestly claimed for `cache_state=off`; (b) the log/stats marker that proves the
   pinned depth drafted — `mtplx_stats.mtp_depth`/`accept_rate` in the final chunk is
   the best candidate (§4.3); (c) the artifact contract — whether the harness's
   existing packs load at all (sibling doc §12.1) or whether the first cell uses an
   MTPLX-native pack.
4. **Readiness**: use `--model-id` to pin the served id, or read `/health.model`;
   do not re-derive the slug in `model_id_candidates`.
5. Cross-reference the sibling document for the mechanism-level verdict and the
   per-runtime positioning; this document deliberately does not repeat it.

## Unverified items (listed per the order)

1. **RAM session-bank disable.** No serve flag was found for the RAM bank (budgets are
   env-only: `MTPLX_SESSION_BANK_MAX_BYTES` etc.); whether a zero budget stops warm
   restore honestly is unverified — and it gates an honest `cache_state="off"` cell.
2. **The "head drafted" marker for a depth cell.** Candidates: `mtplx_stats.mtp_depth`,
   `accept_rate`, `decode_tok_s` in the final SSE chunk, `/health.depth`/`mtp_enabled`;
   the exact receipt to gate on is not pinned.
3. **Seed scheduling.** No code path gating batching/scheduling on a request seed was
   found, but this was not exhaustively traced; the first live cell should confirm the
   base no-seed policy.
4. **The app's own Login-Item/background setup.** No `SMAppService`/`LaunchAgent`/
   `LoginItem` code was found in the app sources in this repository; the shipped DMG
   bundle's `Info.plist` is not in the repo, so the DMG's login behaviour is not closed
   from source here.
5. **The live 2.12.2 command surface.** Every flag/default above is read from source and
   parser text; no process was started (order forbids it).
6. **The artifact contract.** Whether MTPLX loads OptiQ/JANG-exported artifacts (the
   harness's existing packs) is the sibling document's open item §12.1 and is untouched
   here.
7. **`/v1/models` request-model handling.** What a chat request naming a different
   `model` string receives (400 vs silent serving of the loaded model) was not read.

## Sources index

- **Source**: `youssofal/MTPLX@9882703f3105363ddc37eca9f97aa09a1d387112`, shared clone
  `/private/tmp/claude-501/mtplx-src` (read 2026-10-06). Files cited inline:
  `pyproject.toml`, `README.md`, `INSTALL.md`, `CHANGELOG.md`, `scripts/install_macos.sh`,
  `mtplx/cli.py`, `mtplx/commands/public.py`, `mtplx/version.py`, `mtplx/config.py`,
  `mtplx/app_settings.py`, `mtplx/profiles.py`, `mtplx/default_models.py`,
  `mtplx/daemon_client.py`, `mtplx/system_memory.py`, `mtplx/server/openai.py`,
  `mtplx/server/request_policy.py`, `apps/MTPLXApp/README.md`, `docs/server.md`.
- **Web**: https://pypi.org/project/mtplx/ (version 2.12.2, released 2026-10-03,
  publishing commit `9882703`); https://github.com/youssofal/MTPLX (README/INSTALL);
  https://mtplx.com/ (download/benchmarks, via the sibling document).
- **In-repo cross-references**: `docs/research/2026-10-06-mtplx-architecture.md`;
  `ohyesmlx/runtimes.py`; `docs/interfaces.md`; `AGENTS.md`.
