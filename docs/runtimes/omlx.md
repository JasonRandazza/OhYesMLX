# oMLX 0.6.4 — runtime capability and configuration reference

Written 2026-09-15 by static inspection only. Nothing in this document was established by
starting the server, loading a model, or sending a request; the harness coordinator runs live
probes separately. Every claim below carries its evidence inline.

**Version.** `omlx/_version.py` → `__version__ = "0.6.4"`; `omlx/_build_info.py` →
`build_number = "260830015308-macos26-27"`. `Info.plist` `CFBundleShortVersionString` `0.6.4`,
`CFBundleVersion` `2529`. Bundled engines pinned in `omlx/_engine_commits.json`: mlx-lm
`ab1806e8`, mlx-embeddings `32981fa4`, mlx-vlm `78b96eb5`, mlx-audio `51753266`.

**Evidence convention.** Source citations are relative to the bundle root
`$SRC = /Applications/oMLX.app/Contents/Resources/omlx/`. So `server.py:2233` means
`/Applications/oMLX.app/Contents/Resources/omlx/server.py` line 2233. Citations under
`omlx-cli`, `settings.json` and `~/.omlx/` are given in full.

**The governing rule, restated because this document exists because of it.** `--help`
documents a command line. It does not document a runtime. oMLX's real configuration surface
spans five places, and the largest of them is not the command line:

1. the command-line flags (`omlx/cli.py`),
2. `~/.omlx/settings.json`, whose keys are read by `omlx/settings.py`,
3. environment variables seeded by the CLI *from* settings.json — so a setting can change
   behaviour without appearing in the start command at all,
4. per-request fields the OpenAI-compatible endpoint honours (`omlx/api/openai_models.py`),
5. behaviour that is only in the shipped source (`omlx/engine_core.py`,
   `omlx/api/thinking.py`, `omlx/output_collector.py`).

A claim that oMLX *cannot* do something needs evidence from 2–5, not from the absence of a
flag in 1.

---

## 1. Entry points

### 1.1 The executable chain

There are three shell scripts between the binary on `PATH` and Python:

| # | Path | Kind | What it does |
|---|---|---|---|
| 1 | `/opt/homebrew/bin/omlx` | symlink → `/Users/jrazz/.omlx/bin/omlx` | — |
| 2 | `/Users/jrazz/.omlx/bin/omlx` | POSIX `sh` script | Reads `~/Library/Application Support/oMLX/base-path` into `OMLX_BASE_PATH` if readable, then `exec '/Applications/oMLX.app/Contents/MacOS/omlx-cli' "$@"` |
| 3 | `/Applications/oMLX.app/Contents/MacOS/omlx-cli` | POSIX `sh` script, `set -eu` | Resolves `APP_ROOT`, exports the bundled interpreter's environment, then `exec "$PYTHON" -m omlx.cli "$@"` |
| 4 | `…/Resources/Python/cpython-3.11/bin/python3` | CPython | `Python 3.11.10`, runs the module |

`omlx-cli` verbatim (lines 1–20):

```sh
#!/bin/sh
set -eu

REAL_PATH="$(realpath "$0")"
APP_ROOT="$(CDPATH= cd -- "$(dirname -- "$REAL_PATH")/.." && pwd)"
RESOURCES="$APP_ROOT/Resources"
PYROOT="$RESOURCES/Python"
CPYTHON="$PYROOT/cpython-3.11"
PYTHON="$CPYTHON/bin/python3"
MLX_SITE="$PYROOT/framework-mlx-base/lib/python3.11/site-packages"

export PYTHONHOME="$CPYTHON"
export PYTHONDONTWRITEBYTECODE=1
if [ -n "${PYTHONPATH:-}" ]; then
    export PYTHONPATH="$RESOURCES:$MLX_SITE:$PYTHONPATH"
else
    export PYTHONPATH="$RESOURCES:$MLX_SITE"
fi

exec "$PYTHON" -m omlx.cli "$@"
```

### 1.2 Interpreter resolution — what this means for a caller

- **`omlx-cli` resolves its own location, not its invocation path.** `realpath "$0"` follows
  symlinks to the real bundle file, so a symlink from `~/.local/bin/omlx` (or anywhere else)
  into `…/MacOS/omlx-cli` still computes a correct `APP_ROOT` and still finds its interpreter.
  A symlink does **not** break this script.
- **The `~/.omlx/bin/omlx` shim is the fragile one, in the opposite way.** It is a copy of the
  shim, not a symlink, and it hardcodes `exec '/Applications/oMLX.app/Contents/MacOS/omlx-cli'`.
  It therefore survives being copied anywhere, but it breaks if the app bundle is moved,
  renamed, or reinstalled to a different path — the bootstrap file it reads is consulted only
  for `OMLX_BASE_PATH`, never to locate the app. **A relocated bundle leaves this shim pointing
  at a path that no longer exists, with no error beyond `exec` failing.**
- **`PYTHONHOME` is exported, so the caller's Python environment is fully overridden.** A
  virtualenv, a pyenv shim, or a `conda` activation on `PATH` has no effect: `omlx` always runs
  the bundle's CPython 3.11.10 with the bundle's site-packages. Any `pip install` into a
  project venv is invisible to `omlx`.
- **`PYTHONPATH` prepends the bundle, so the bundle wins name collisions.** The bundle's
  `Resources` and `MLX_SITE` come *before* an inherited `PYTHONPATH`, so an inherited path can
  add modules but cannot shadow a bundled one.
- **`PYTHONDONTWRITEBYTECODE=1`** is set, so no `__pycache__` is written into the signed bundle
  (the shipped `__pycache__` directories are from the build).
- **The bootstrap file does not exist on this machine.**
  `/Users/jrazz/Library/Application Support/oMLX/base-path` is absent, so `OMLX_BASE_PATH` is
  never exported by the shim and the base path falls through to the default resolution
  (`~/.omlx` — see §3.1). The `[ -r … ]` guard means its absence is silent.
- `realpath` is present at `/bin/realpath` on macOS 26, so `set -eu` does not abort on a missing
  command.

### 1.3 Other executables shipped in the bundle

| Path | Kind | Used for |
|---|---|---|
| `…/MacOS/oMLX` | Mach-O binary, 28.9 MB | The GUI application (menubar app). Not required to run the server. |
| `…/MacOS/omlx-cluster-python` | `sh` script | Identical environment setup to `omlx-cli`, but `exec "$PYTHON" "$@"` — a bare interpreter entry point, for running arbitrary scripts inside the bundle's environment. |
| `~/.omlx/bin/omlx-cluster-python` | `sh` script | **Generated by oMLX**, rewritten on every server start (`# Written by oMLX so another Mac can run this node's interpreter over SSH. Do not edit; it is rewritten on every server start.`). It hardcodes `PYTHONHOME`/`PYTHONPATH`/interpreter as absolute paths into the bundle and `exec`s them. This is the SSH-facing entry point for distributed nodes. |

Note the difference between the two `omlx-cluster-python` scripts: the one in the bundle
resolves paths relative to itself, the one in `~/.omlx/bin` has them baked in by the server.

### 1.4 Console-script note

There is **no** `omlx` console script installed by a Python packaging step and nothing in the
bundle's `bin/` — `…/Resources/Python/cpython-3.11/bin/` contains only `python`, `python3`,
`python3.11`. The `omlx` command on `PATH` is the shell shim in §1.1, which means the
"console script resolves its interpreter relative to its own location" hazard applies to the
*shim's hardcoded app path*, not to a shebang. If the app bundle moves, the shim silently
points nowhere.

---

## 2. The command-line surface

### 2.1 Top level

```
usage: cli.py [-h] [--version]
              {start,stop,restart,serve,launch,diagnose,cluster} ...
```

| Command | Purpose |
|---|---|
| `start` | Start oMLX as a managed background server (talks to the GUI app's state machine) |
| `stop` | Stop the managed background server |
| `restart` | Restart the managed background server |
| `serve` | Start the multi-model OpenAI-compatible server (this is the one a benchmark uses) |
| `launch` | Launch an external coding tool configured against the running server |
| `diagnose` | Diagnostic checks (`menubar` only) |
| `cluster` | Distributed-node diagnostics and planning; **does not** configure interfaces or initialize JACCL |
| `--version` | Print version and exit |

### 2.2 `serve` — the full flag surface

Verified against `omlx/cli.py:1040–1230` and `omlx serve --help`.

| Flag | argparse default | Effective default (`settings.py`) | Controls |
|---|---|---|---|
| `--model-dir` | `None` | `~/.omlx/models` via `ModelSettings.get_model_dirs` | Directory whose subdirectories are models |
| `--host` | `None` | `127.0.0.1` (`ServerSettings.host`) | Bind host; comma-separated multi-bind supported (`cli.py:220`) |
| `--port` | `None` | `8000` (`ServerSettings.port`) | Bind port |
| `--log-level` | `None` | `info` | `trace` includes full message content |
| `--sse-keepalive-mode` | `None` | `chunk` | `chunk` = protocol-aware no-op event; `comment` = legacy `: keep-alive`; `off` = none. **See §6.3 — this is a measurement hazard.** |
| `--max-audio-upload-size` | `None` | `100MB` | Per-request RAM cap for audio uploads |
| `--max-concurrent-requests` | `None` | `8` | Concurrent requests; higher = more memory |
| `--embedding-batch-size` | `None` | `32` | Embedding inputs per forward pass |
| `--memory-guard` | `None` | `balanced` | `off`/`safe`/`balanced`/`aggressive`; passing a tier turns the guard **on** |
| `--memory-guard-gb` | `None` | unset | Custom ceiling in GB; sets tier to `custom` and turns the guard on |
| `--paged-ssd-cache-dir` | `None` | unset | Enables the paged SSD prefix cache |
| `--paged-ssd-cache-max-size` | `None` | `100GB` (CLI) / `auto` (settings) | Cache size cap |
| `--hot-cache-max-size` | `None` | `0` (disabled) | In-memory hot cache size |
| `--hot-cache-write-through` | `False` | `False` | Persist every hot block to SSD immediately |
| `--no-cache` | `False` | — | Disables the paged SSD cache (mlx-lm `BatchGenerator` still manages KV states internally) |
| `--initial-cache-blocks` | `None` | `256` | Blocks pre-allocated at startup |
| `--mcp-config` | `None` | unset | MCP tool-integration config path |
| `--hf-endpoint` | `None` | unset | HuggingFace Hub endpoint override |
| `--hf-cache` / `--no-hf-cache` | `None` | enabled | Discover models from the HF hub local cache |
| `--ms-endpoint` | `None` | unset | ModelScope endpoint |
| `--http-proxy`, `--https-proxy`, `--no-proxy`, `--ca-bundle` | `None` | unset | Network |
| `--base-path` | `None` | `~/.omlx` | oMLX data root |
| `--api-key` | `None` | `auth.api_key` from settings | API key for authentication |

**The `--help` text's "default:" strings are prose, not argparse defaults.** Every argument is
declared `default=None` (`cli.py:1052` `"--host", type=str, default=None, help="Host to bind
(default: 127.0.0.1)"`, `cli.py:1055` the same for `--port`). The stated defaults are the
*shipped* defaults; the values actually used come from `settings.json` first. On this machine
the help says port 8000 and the server binds **8106**.

**Flags are persisted to `settings.json`.** `cli.py:192–198`:

```python
if _has_cli_overrides(args):
    try:
        settings.save_cli_overrides(args)
        print("Saved CLI arguments to settings.json")
```

The persisted set is `_has_cli_overrides`'s tuple (`cli.py:51–75`): `model_dir`, `port`,
`host`, `log_level`, `sse_keepalive_mode`, `max_audio_upload_size`,
`max_concurrent_requests`, `embedding_batch_size`, `memory_guard`, `memory_guard_gb`,
`paged_ssd_cache_dir`, `paged_ssd_cache_max_size`, `hot_cache_max_size`,
`hot_cache_write_through`, `initial_cache_blocks`, `mcp_config`, `hf_endpoint`,
`hf_cache_enabled`, `ms_endpoint`, `http_proxy`, `https_proxy`, `no_proxy`, `ca_bundle`, plus
`no_cache` as the one boolean with a `False` default. **`--api-key` is not in this list** —
it is not persisted.

> **Operational consequence, live on this machine.** `settings.json` currently reads
> `"model_dirs": ["/Users/jrazz/.claude/jobs/1704c764/tmp/omlxcat"]` and that directory **no
> longer exists** (verified: `ls` → `No such file or directory`). It was written there by the
> previous probe's `--model-dir`. A future `omlx serve` that omits `--model-dir` will discover
> zero models and start an empty server. **Always pass `--model-dir` explicitly.**

### 2.3 The other subcommands

| Command | Flags |
|---|---|
| `start` | `--timeout`, `--no-wait` |
| `stop` | `--timeout` |
| `restart` | `--timeout`, `--no-wait` |
| `launch` | positional `tool` (`claude`, `copilot`, `codex`, `codex_app`, `opencode`, `openclaw`, `hermes`, `pi`, `list`), `--model`, `--host`, `--port`, `--api-key`, `--tools-profile {minimal,coding,messaging,full}`, `--opus`, `--sonnet`, `--haiku`, `--cross-session` |
| `diagnose` | positional `{menubar}` |
| `cluster` | `{status,worker-smoke,collective-smoke,pipeline-smoke,plan}` |

`--cross-session` on `launch` is documented as requiring "enabling telemetry and feature-flag
traffic to Anthropic that is otherwise kept disabled by default". Nothing in `serve` sends
telemetry.

### 2.4 A second, dead configuration path

`omlx/config.py:172` defines `class OMLXConfig` with `from_env()` and `from_cli_args()`, and
different defaults (host `0.0.0.0`, port `8000`, `top_k` `0`, `continuous_batching` `False`).
`from_cli_args` looks for flags (`--model`, `--top-k`, `--continuous-batching`,
`--trust-remote-code`) that `omlx serve` does not define.

**It is not the live path.** The only thing imported from `omlx.config` anywhere in the bundle
is `parse_size` (`cli.py:252`, `cli.py:905`, `settings.py:33`). `OMLXConfig` is never
instantiated. The live path is `init_settings()` (`settings.py:1776`) → `GlobalSettings.load()`
(`settings.py:965`). Do not read defaults off `config.py`.

---

## 3. The settings surface beyond the command line

### 3.1 Location and resolution

`GlobalSettings.load` (`settings.py:965–1005`) resolves the base path in this order:

1. an explicit `base_path` argument (from `--base-path`),
2. `OMLX_BASE_PATH` in the environment (the shim sets this from the bootstrap file),
3. the macOS app's bootstrap file,
4. `~/.omlx`.

It then loads `{base_path}/settings.json` if present, applies environment overrides, then CLI
overrides. **Priority hierarchy, documented at `settings.py:972`: CLI > env > file >
defaults.** On this machine the base path is `/Users/jrazz/.omlx` and the file is
`/Users/jrazz/.omlx/settings.json`.

`SETTINGS_VERSION = "1.0"` (`settings.py:41`), written as the `"version"` key.

### 3.2 The 17 top-level keys

`version` plus 16 section objects, matching `GlobalSettings`'s fields (`settings.py:934–963`):
`server`, `model`, `memory`, `scheduler`, `cache`, `auth`, `mcp`, `huggingface`, `modelscope`,
`network`, `sampling`, `logging`, `claude_code`, `integrations`, `ui`, `idle_timeout`.

### 3.3 Keys with **no** command-line equivalent

These are the settings that silently decide what a cell measures. Each one is read from
`settings.json` and has no corresponding flag.

| Key | Shipped default | This machine | Why it matters for a measurement |
|---|---|---|---|
| `server.burst_decode_mode` | `balanced` | `balanced` | **Sets decode granularity and reported throughput.** Mapped to env vars the CLI then exports — see §8.1. `off`/`light`/`balanced`/`aggressive` = `(max_steps, single_s)` of `(1,0.0)`/`(64,0.05)`/`(64,0.1)`/`(64,0.2)` (`settings.py:139–144`). |
| `server.preserve_mid_system_cache` | `True` | `true` | Cache retention policy |
| `server.auto_start_on_launch` | `True` | `true` | GUI-app behaviour, not server |
| `server.server_aliases` | `[]` | 5 entries | Hostnames the server answers as |
| `server.distributed_inference_enabled` | `False` | `false` | Gates the cluster surface; off ⇒ those routes return 404 (`server.py:362–367`) |
| `model.model_fallback` | `False` | `false` | If a requested model is missing, serve a default instead of erroring. **Silently changes which weights answer.** |
| `model.hide_helper_models` | `False` | `false` | Hides dFlash/Assistant/Draft helper models from `/v1/models` |
| `memory.prefill_memory_guard` | `True` | **`false`** | Prefill estimation + generation-scheduling deferral |
| `memory.memory_guard_tier` | `balanced` | `balanced` | Active-memory reclaim ratio |
| `memory.memory_guard_custom_ceiling_gb` | `0.0` | `0.0` | Only consulted when tier is `custom` |
| `memory.soft_threshold` | `0.85` | `0.85` | Admission pause + LRU eviction |
| `memory.hard_threshold` | `0.95` | `0.95` | In-flight abort |
| `memory.prefill_safe_zone_ratio` | `0.80` | `0.80` | Adaptive chunk throttle trigger |
| `memory.prefill_min_chunk_tokens` | `32` | `32` | Floor before a request is aborted |
| `scheduler.chunked_prefill` | `False` | `false` | Interleaves long prefills with decode; trades TTFT for per-step overhead |
| `scheduler.prefill_priority` | `context` | `context` | `context` shrinks prefill steps to fit the largest prompt; `speed` never shrinks and admits fewer prompts |
| `scheduler.decode_fairness` | `True` | `true` | Forces prefill to yield GPU time to running decodes; chunks are capped while any engine decodes |
| `cache.enabled` | `True` | **`false`** | Paged SSD prefix cache |
| `cache.ssd_cache_max_size` | `auto` (10% of SSD) | `92GB` | — |
| `cache.hot_cache_max_size` | `0` | `0` | In-memory hot cache |
| `cache.hot_cache_write_through` | `False` | `false` | — |
| `cache.initial_cache_blocks` | `256` | `256` | Startup allocation |
| `cache.ane_compile_cache` | `False` | `false` | Sets `OMLX_QWEN35_ANE_COMPILE_CACHE=1` (`cli.py:117–118`) |
| `cache.gdn_snapshot_storage` | `auto` | `auto` | GDN state: SSD sidecar vs embedded |
| `cache.gdn_sidecar_precision` | `fp32` | `fp32` | `fp32`/`bf16`/`int8`/`rht_int8`/`rht_int16` |
| `cache.gdn_ssd_pending_max_size` | `512MB` | `512MB` | — |
| `sampling.max_context_window` | `32768` | `32768` | Fallback context length when neither a per-model override nor a discovered native length exists |
| `sampling.max_context_window_policy` | `None` | `null` | Operator cap: server returns `min(native, policy)` |
| `sampling.max_tokens` | `32768` | `32768` | Default `max_tokens` when the request omits it |
| `sampling.temperature` | `1.0` | `1.0` | Default when the request omits it |
| `sampling.top_p` | `0.95` | `0.95` | Default when the request omits it |
| `sampling.top_k` | `0` | `20` | Default when the request omits it |
| `sampling.repetition_penalty` | `1.0` | `1.0` | Default when the request omits it |
| `idle_timeout.idle_timeout_seconds` | `None` | `null` | When set, **unloads the model after inactivity**. Minimum 60 (`admin/routes.py:360`). |
| `logging.retention_days` | `7` | `7` | Log rotation |

> **`top_k` deserves attention.** The shipped default is `0` (disabled) but this machine has
> `20`. A request that omits `top_k` therefore samples differently here than on a stock
> install. The project's own rule — "left unpinned invalidates the comparison" — applies to
> the *server-side* default as much as to client-sent values.

### 3.4 Settings that DO have a CLI equivalent

For completeness, the settings reachable from the command line: `server.host`,
`server.port`, `server.log_level`, `server.sse_keepalive_mode`,
`server.max_audio_upload_size`, `model.model_dir`, `scheduler.max_concurrent_requests`,
`scheduler.embedding_batch_size`, `memory.memory_guard_tier`,
`memory.memory_guard_custom_ceiling_gb`, `cache.ssd_cache_dir`, `cache.ssd_cache_max_size`,
`cache.hot_cache_max_size`, `cache.hot_cache_write_through`, `cache.initial_cache_blocks`,
`mcp.config_path`, `huggingface.endpoint`, `huggingface.hf_cache_enabled`,
`modelscope.endpoint`, `network.*`, and `auth.api_key`. All the rest of §3.3 is
settings-file-only, which is exactly the point of listing it.

`server.host` and `auth.api_key` are also settable through environment variables in the
legacy `config.py` path — but that path is dead (§2.4).

---

## 4. The API surface

### 4.1 Routes

| Method + path | Auth | Source |
|---|---|---|
| `GET /health` | **none** | `server.py:2467` (no `verify_api_key` dependency) |
| `GET /api/status` | required | `server.py:2517` |
| `GET /v1/models` | required | `server.py:2892` |
| `GET /v1/models/status` | required | `server.py:2985` |
| `POST /v1/models/{model_id}/unload` | required | `server.py:3035` |
| `POST /v1/models/{model_id}/load` | required | `server.py:3051` |
| `POST /v1/embeddings` | required | `server.py:3094` |
| `POST /v1/rerank` | required | `server.py:3221` |
| `POST /v1/completions` | required | `server.py:3325` |
| `POST /v1/chat/completions` | required | `server.py:3524` |
| `POST /v1/messages` (Anthropic) | required | `server.py:5568` |
| `POST /v1/messages/count_tokens` | required | `server.py:5957` |
| `POST /v1/responses` (OpenAI Responses) | required | `server.py:6083` |
| `GET /v1/responses/{response_id}` | required | `server.py:7274` |
| MCP, web-search, audio routers | required | `server.py:614`, `621`, `632` |

### 4.2 Authentication

`verify_api_key` (`server.py:312–353`) returns `True` — **no auth** — when either:

1. `_server_state.api_key is None` (no key configured), or
2. `global_settings.auth.skip_api_key_verification` is `True`.

Otherwise it requires a bearer token, falling back to the `x-api-key` header for Anthropic SDK
compatibility (`server.py:335–341`). A missing token raises **401 `"API key required"`**; a
wrong token raises **401 `"Invalid API key"`** and logs a key fingerprint. It checks the main
key **and** every `auth.sub_keys` entry (`server.py:344–351`).

On this machine `auth.api_key` is set and `skip_api_key_verification` is `false`, so
**`/v1/chat/completions` requires a key**; `auth.sub_keys` contains one named
`BenchmarkHarness`. `GET /health` needs no key, so a readiness poll works before the key is
wired up.

### 4.3 Per-request fields beyond the standard set

`ChatCompletionRequest` (`api/openai_models.py:284–331`). Standard OpenAI fields plus these
extensions:

| Field | Type | Notes |
|---|---|---|
| `top_k` | int | Sampling |
| `min_p` | float | Sampling |
| `xtc_probability` | float | XTC sampling |
| `xtc_threshold` | float | XTC sampling |
| `repetition_penalty` | float | — |
| `repetition_context_size` | int > 0 | — |
| `max_completion_tokens` | — | Alias of `max_tokens` via `AliasChoices` |
| `thinking_budget` | int ≥ 0 | Max thinking tokens; `None` = unlimited |
| `reasoning_effort` | `str \| int \| float` | Forwarded to the **chat template**. Strings for Qwen-style (`"low"`..`"xhigh"`); floats for numeric-effort templates (Inkling, `0.1`–`0.99`). Each template validates its own vocabulary (`api/openai_models.py:317–321`). |
| `chat_template_kwargs` | dict | Arbitrary chat-template kwargs, e.g. `enable_thinking` |
| `specprefill` | bool \| None | Per-request SpecPrefill override |
| `specprefill_keep_pct` | float \| None | Keep rate override |
| `specprefill_threshold` | int \| None | Min tokens to trigger |
| `structured_outputs` | dict | vLLM-compatible: `json` / `regex` / `choice` / `grammar` |
| `guided_grammar` | str | Alias normalised to `structured_outputs` |
| `response_format` | `text`/`json_object`/`json_schema` | — |
| `stream_options.include_usage` | bool, default `False` | **The usage block is only emitted on the stream when this is true** (`server.py:5112`) |
| `seed` | int | Best-effort reproducibility |

There is **no per-request field for streaming granularity, `stream_interval`, cache control, or
burst mode.** Those are server-level only.

---

## 5. Streaming behaviour

This is the section the document exists for. Everything here is sourced to the line that
decides it.

### 5.1 Which channels it emits

The chat-completions stream is produced by `stream_chat_completion` (`server.py:4728–5148`).
The channel a token lands in is decided by `ThinkingParser` (`api/thinking.py:215–369`), which
is fed each incremental `output.new_text` at `server.py:4806`:

```python
thinking_delta, content_delta = thinking_parser.feed(output.new_text)
```

The parser maintains one boolean, `_in_thinking`, and routes each character to one of two
output buffers. It recognises four tag families (`api/thinking.py:17–24`):
`<think>`/`</think>`, `<mm:think>`/`</mm:think>` (MiniMax), and
`<think:opensource>`/`</think:opensource>` (HY3).

| Channel | Emitted as | Streaming? |
|---|---|---|
| `reasoning_content` | `ChatCompletionChunkDelta(reasoning_content=…)`, `server.py:4818` | **Yes, incrementally** — one delta per parser feed that produced thinking text |
| `content` | `ChatCompletionChunkDelta(content=…)`, `server.py:4839` | Yes in the normal case; **collapses to a single delta** in the recovery case (§5.2) |
| `content` (buffered mode) | `server.py:4972` | Only when tool-call filtering disabled content streaming (§5.4) |
| `tool_calls` | `server.py:5049`, parsed from accumulated text after the stream ends | No — emitted whole, once |
| `usage` | `server.py:5116–5148` | No — one final chunk, only if `stream_options.include_usage` |
| `finish_reason` | `server.py:5057–5067` | Final chunk, empty delta |

There is **no** `reasoning` (non-`_content`) channel on the OpenAI path. `reasoning` naming
exists only in Harmony/gpt-oss handling and on the Anthropic path.

### 5.2 Why `content` arrives as ONE delta when `stream_interval` is 1

**`stream_interval` is not what makes content a single delta, and that is the finding.**

`stream_interval` defaults to `1` in three places — `EngineConfig.stream_interval`
(`engine_core.py:157`), `SchedulerConfig.stream_interval` (`config.py:100`), and
`RequestStreamState.stream_interval` (`output_collector.py:192`) — with the comment
`# Tokens to batch before streaming (1=every token)`. It is **not settable** from the command
line or from `settings.json`; no flag and no settings key assigns it, so it is always 1. At
`engine_core.py:382–435`, `stream_interval == 1` selects `use_simple_streaming`, which skips
the interval check entirely and calls `collector.put(req_output)` for *every* step output.
`stream_interval = 1` therefore means **the engine deliberately withholds nothing.**

So the single-delta behaviour is produced *above* the engine, and there are two distinct
mechanisms. They are independent; a given response may exhibit either.

#### Mechanism A — the thinking-parser recovery path (this is the one that mirrors the text)

`ThinkingParser.finish()` (`api/thinking.py:326–369`):

```python
if (
    self._in_thinking
    and not self._close_seen
    and not self._content_emitted
    and self._thinking_accumulated
):
    recovered = "".join(self._thinking_accumulated) + partial
    self._content_emitted = True
    return ("", recovered)
```

Its own comment states the intent exactly:

> Recovery: prompt opened a thinking block (or model echoed `<think>` itself), the close tag
> never arrived, and nothing ever streamed as content. Re-emit the accumulated thinking text as
> content so the answer body is not empty. The thinking events already streamed live cannot be
> retracted, so the client sees the same text twice — once in the thinking panel, once as the
> answer.

`finish()` is called once, after the generation loop, at `server.py:4854`, and its returned
`content_delta` is emitted as **one** chunk at `server.py:4888–4902`.

The trigger conditions are all four of:

1. `_in_thinking` is `True` — true from the start when `start_in_thinking=True`, or set when a
   `<think>` tag is seen;
2. `_close_seen` is `False` — the model never emitted a closing tag;
3. `_content_emitted` is `False` — nothing ever went out on the content channel;
4. `_thinking_accumulated` is non-empty.

`start_in_thinking` comes from `prompt_opens_thinking()` (`api/thinking.py:95–142`), which
encodes the prompt and returns `True` when the think-start token id appears **within the last
three prompt tokens without a think-end token after it** (`api/thinking.py:130–142`). A
template that renders `…<|im_start|>assistant\n<think>\n` hits this.

**The consequence, stated plainly: when a reasoning model runs out of `max_tokens` before it
emits `</think>`, the entire response is classified as reasoning, streams out incrementally in
`reasoning_content`, and is then re-emitted verbatim as a single `content` delta at EOS.** The
content channel is a *duplicate* of the reasoning channel, and it carries no information about
when the answer was produced.

This is what the project's own corrected record measured
(`docs/research/2026-09-15-omlx-streams-in-the-reasoning-channel.md`):

| channel | deltas | first | last | window |
|---|---|---|---|---|
| `reasoning_content` | 15 | 0.685 s | 2.352 s | 1.668 s |
| `content` | 1 | 2.352 s | 2.352 s | 0.000 s |

The content delta's first and last timestamp are identical and equal to the last reasoning
delta's — the signature of a single delta emitted after the loop exits. That run used
`max_tokens=128` on a small model, and the server's own log for the 128-token request records
`finish_reason=length`
(`~/.omlx/logs/server.log`: `2026-09-15 11:29:09,164 - Chat completion: model=probe-model, 128
tokens in 2.38s (76.3 tok/s), prompt: 19, finish_reason=length, max_tokens=128`). The think
block was cut off by the token cap, which is precisely the trigger.

> **This is a self-inflicted artifact of probe design.** Raising `max_tokens` past the point
> where the model finishes thinking removes it. A probe that caps `max_tokens` tightly on a
> reasoning model will always see content as one delta — and will draw a false conclusion about
> the runtime's streaming, which is the original oMLX error in miniature.

#### Mechanism B — decode-burst coalescing (this sets the granularity of the deltas that DO stream)

The engine does not hand back one output per `scheduler.step()`. `_step_burst`
(`engine_core.py:326–369`) chains steps inside a single executor hand-off, bounded by a **time
budget**:

```python
decode_burst_max_steps: int = field(
    default_factory=lambda: int(os.environ.get("OMLX_DECODE_BURST_MAX_STEPS", "64"))
)
decode_burst_budget_single_s: float = field(
    default_factory=lambda: float(
        os.environ.get("OMLX_DECODE_BURST_BUDGET_SINGLE_S", "0.1")
    )
)
decode_burst_budget_s: float = field(
    default_factory=lambda: float(os.environ.get("OMLX_DECODE_BURST_S", "0.03"))
)
```

and the budget is **adaptive** — aggressive when one request is active, tight when concurrent
(`engine_core.py:347–355`):

```python
# Adaptive budget: single active request -> aggressive (nothing else to
# stay responsive to); concurrent -> tight to keep admission/abort low.
single = running is None or len(running) <= 1
budget = (
    self.config.decode_burst_budget_single_s
    if single
    else self.config.decode_burst_budget_s
)
```

Its docstring gives the reason and the price (`engine_core.py:329–333`):

> Each decode token otherwise bounces back to the event loop, which ping-pongs the GIL with the
> asyncio loop + uvicorn on the main thread (~1ms/token of contention). Chaining a few steps
> lets the MLX thread hold the GIL continuously (in-process sync loop hits ~80 tok/s vs ~74
> through the per-token async hand-off).

Then `RequestOutputCollector` **merges** the queued outputs when the consumer has not drained
them (`output_collector.py:54–72`, `_merge_outputs` at `117–164`):

```python
merged_new_token_ids = existing.new_token_ids + new.new_token_ids
merged_new_text = existing.new_text + new.new_text
```

and `add_request` constructs it with aggregation **on** (`engine_core.py:609`):
`RequestOutputCollector(aggregate=True)`.

**Net effect:** `output.new_text` is not one token. It is whatever accumulated during one burst
— up to `decode_burst_max_steps` tokens, or as many as fit in the time budget. The
`reasoning_content` deltas in the corrected record are consistent with this: 15 deltas over
1.668 s is **0.111 s per delta**, against a `balanced` single-request budget of 0.1 s. The
deltas are burst-shaped, not token-shaped.

There is a third, smaller contributor: `RequestOutputCollector.should_send`
(`output_collector.py:195–213`) always sends the first token and always sends on `finished`, so
under `stream_interval > 1` the first and last deltas are never withheld. With
`stream_interval == 1` this path is not taken at all.

### 5.3 Everything `stream_interval` cannot do

Because `stream_interval` is fixed at 1 and unsettable, the only lever a cell has over delta
granularity is **`server.burst_decode_mode`** in `settings.json` (§8.1). There is no flag for
it.

### 5.4 What suppresses content streaming entirely

When tools are present and `ToolCallStreamFilter` is inactive, `stream_content` is set `False`
(`server.py:4784–4796`):

```python
if has_tools:
    _content_filter = ToolCallStreamFilter(engine.tokenizer)
    _thinking_filter = ToolCallStreamFilter(engine.tokenizer, consume_dsml_separator=False)
    if _content_filter.active:
        tool_filter = _content_filter
        thinking_filter = _thinking_filter
    else:
        stream_content = False
```

With `stream_content = False` the per-token loop emits nothing at all, and reasoning and content
are both flushed **buffered, after the stream ends** (`server.py:4951–4977`). A tools-enabled
request on a model with an inactive filter therefore produces **zero incremental deltas on
either channel**. Do not benchmark with `tools` set.

### 5.5 The keepalive frame — a first-event trap

`--sse-keepalive-mode` defaults to `chunk`, and this machine's `settings.json` has
`sse_keepalive_mode: "chunk"`. In that mode `_with_sse_keepalive` (`server.py:2191–2234`)
emits a frame **before the generator starts**:

```python
# Send initial keepalive immediately so clients with short read
# timeouts (e.g. openclaw ~15s) don't disconnect during prefill.
if keepalive_chunk is not None:
    yield keepalive_chunk
```

and for `openai_chat` that frame is `_chat_keepalive_chunk(response_id)`
(`server.py:2154–2176`), a **syntactically valid `chat.completion.chunk`**:

```
data: {"id":"<the real completion id>","object":"chat.completion.chunk","created":0,
"model":"keepalive","choices":[{"index":0,"delta":{"role":"assistant","content":""},
"finish_reason":null}]}
```

The source comment at `server.py:2097–2099` is explicit that this is the first event of every
stream:

> The delta carries `"role":"assistant"` because this frame is the **FIRST event of every
> stream** and some accumulators type the whole stream from the first chunk's role.

**Measurement consequence.** A TTFT probe that latches the first SSE `data:` frame, or the
first frame whose delta contains a `content` key, will read approximately zero — the frame
arrives before prefill begins and its `content` field is present and empty. Two independent
defences are needed, and both are cheap:

- ignore frames whose `model` is `"keepalive"` or whose `id` is `chatcmpl-keepalive`;
- count a content delta only when `delta.content` is **non-empty**;
- and, because keepalives also repeat every 10 s mid-stream (`interval: float = 10.0`,
  `server.py:2194`), do not treat any keepalive as a token.

Setting `sse_keepalive_mode` to `off` removes this hazard for a probe, but it is a
settings-file-only change and it is not the default.

### 5.6 What to measure on this runtime

| Metric | Correct source | Why |
|---|---|---|
| TTFT | first **`reasoning_content`** delta with non-empty text | The content channel can carry no timing at all (§5.2A) |
| ITL / TPOT | gaps between successive `reasoning_content` deltas | 15 usable deltas in the reference run |
| Decode window | first → last non-empty `reasoning_content` delta | 1.668 s in the reference run, not `1.66e-07` |
| Output throughput (per-request) | `usage.completion_tokens` ÷ decode window | Prefer this over the runtime's self-reported rate (§6) |
| Aggregate throughput | unchanged | The project's aggregate figure was never affected |
| Channel counts | both `content_event_count` and `reasoning_event_count` | A single content delta is a *signal*, not a failure |

`docs/interfaces.md` pins `ttft_s` as "send → first CONTENT delta. Reasoning deltas excluded."
For this runtime that is the one channel carrying no timing information at all — the defect is
in the instrument, not the runtime.

**A one-content-delta response has no rate**, and omitting the rate is correct. But a
one-content-delta response is also *diagnostic*: it means the thinking block was cut off, and
the reasoning channel is where the timing lives.

---

## 6. Token accounting

### 6.1 What the usage block reports

`Usage` (`api/openai_models.py:366–381`) extends the standard block with oMLX timing
extensions. All timings are in **seconds**.

| Field | Source |
|---|---|
| `prompt_tokens`, `completion_tokens`, `total_tokens` | `server.py:5121–5123` |
| `prompt_tokens_details.cached_tokens` | `server.py:5124–5126` |
| `model_load_duration` | Only if > 1.0 s (`server.py:5127–5131`) |
| `time_to_first_token` | `round(ttft, 2)`, `server.py:5132` |
| `total_time` | `round(total_duration, 2)`, `server.py:5133` |
| `prompt_eval_duration` | `round(metric_prefill_duration, 2)`, `server.py:5134` |
| `generation_duration` | `round(metric_gen_duration, 2)`, `server.py:5135` |
| `prompt_tokens_per_second` | `pt / metric_prefill_duration` if > 0, `server.py:5136` |
| `generation_tokens_per_second` | `ct / metric_gen_duration` if > 0, `server.py:5141` |

**Reasoning is NOT separated in the usage block.** `completion_tokens` is a single count. There
is no `reasoning_tokens` field and no reasoning/content split anywhere in `Usage`. If a cell
needs to know how many tokens were reasoning, it must count reasoning deltas itself.

The usage chunk is **only emitted on a stream when `stream_options.include_usage` is true**
(`server.py:5112`). On a non-streaming response, `usage` is always present
(`ChatCompletionResponse.usage`, `api/openai_models.py:392`).

### 6.2 The self-reported rates are NOT trustworthy — with recorded evidence

The runtime's own log for this machine contains the anomaly:

```
2026-09-15 10:52:45,963 - omlx.server - INFO - Chat completion: model=probe-model,
  8 tokens in 1.03s (15286.6 tok/s), prompt: 13, finish_reason=length,
  max_tokens=8, request_max_tokens=8
2026-09-15 11:28:25,853 - Chat completion: model=probe-model,
  96 tokens in 6.28s (78.5 tok/s), prompt: 23, finish_reason=length
2026-09-15 11:29:09,164 - Chat completion: model=probe-model,
  128 tokens in 2.38s (76.3 tok/s), prompt: 19, finish_reason=length
```

Same model, same machine, minutes apart: **15,286.6 tok/s** and **76.3 tok/s**.

**The mechanism.** The generation window is a wall-clock subtraction that begins when the
consumer first sees a token (`server.py:5071–5078`):

```python
end_time = time.perf_counter()
total_duration = end_time - start_time
ttft = (first_token_time - start_time) if first_token_time else total_duration
is_diffusion = getattr(engine, "is_diffusion_model", False)
if is_diffusion:
    gen_duration = total_duration
else:
    gen_duration = end_time - (first_token_time or start_time)
```

and `first_token_time` is stamped inside the streaming loop, on the first output carrying
`new_text` (`server.py:4799–4800`):

```python
if first_token_time is None and output.new_text:
    first_token_time = time.perf_counter()
```

Now combine that with §5.2B. When the **entire generation completes inside one decode burst**,
the collector merges every token into a single `RequestOutput`, the consumer receives exactly
one output, and `first_token_time` is stamped at the moment of arrival — which is also
`end_time`. So `gen_duration ≈ 0`. With `max_tokens=8` and a warm model the whole response
fits one burst; with `max_tokens=128` it spans many, and the window is real.

The 15,286.6 figure is `8 tokens ÷ ~0.000523 s`. The reported `generation_duration` would be
`round(0.000523, 2)` = **0.0**, while the rate was computed from the *unrounded* value
(`server.py:5141` divides by `metric_gen_duration`, `server.py:5135` rounds it). That is exactly
the reported pair: **`generation_tokens_per_second` of 15286.61 from a `generation_duration` of
0.0.** The two fields are derived from the same number at different precisions.

**Verdict.**

- `generation_tokens_per_second` and the log's `tok/s` are **not trustworthy for short
  generations**. They are a rate whose denominator can collapse toward zero.
- The failure is silent, the number looks plausible-to-spectacular, and nothing in the artifact
  flags it. It is the same class of defect as the published 1.53 billion tok/s.
- **A sanity guard is arithmetic:** compute your own rate from `completion_tokens` and a decode
  window you measured from deltas. If `generation_duration` is reported as `0.0` while
  `generation_tokens_per_second` is large, the rate is meaningless — the two are inconsistent
  by construction, and the inconsistency is the tell.
- `prompt_eval_duration` and `prompt_tokens_per_second` are computed the same way and are
  reliable only if `ttft > 0`, which it is for any real prefill.

---

## 7. Quantization formats

### 7.1 Formats it loads

The loader dispatches on `quantization_config.quant_method` in `model_loading.py:1255–1291`.

| Format | Evidence | Notes |
|---|---|---|
| **Standard MLX affine** (`bits` + `group_size`) | `model_loading.py:1287–1289` — unknown methods fall through with `# The quant method may be already supported by mlx-lm; simply return None.` | Handled by mlx-lm. 4-bit and 8-bit both load (the project's `Holo-3.1-4B-MLX-8bit` and `Qwen3.6-35B-A3B-oQ4` both appear in `~/.omlx/stats.json` with completed requests). |
| **mxfp4** | `oq.py:727`, `oq.py:4722` `{"kind": "mxfp4", "bits": 4, "group_size": 32, "mode": "mxfp4"}`, `utils/model_loading.py:334` | Loaded; `models/qwen3.6-35b-a3b-mxfp4-mtp` in `stats.json` served 24 requests |
| **nvfp4** | `utils/model_loading.py:298` `"mode": "nvfp4"` | Derived from `compressed-tensors` |
| **fp8 / mxfp8** | `oq.py:215–218`: `quant_method == "mxfp8"` or `fp8`; `oq.py:3169` `_NATIVE_FLOAT8_QUANT_METHODS` | Recognised as native float8 |
| **`compressed-tensors`** | `model_loading.py:1261–1270` | Only when `qwen38_modelopt_mixed.is_supported_config(config)` — and it **refuses the text-only path**: `raise ValueError("The supported Qwen3.8 ModelOpt mixed checkpoint is a VLM; refusing the text-only fallback loader")` |
| **`paroquant`** | `model_loading.py:1272–1286` | Requires a **separately installed** package: `ImportError("This model uses ParoQuant. Install it separately with: pip install \"paroquant[mlx]\"")` |
| **OptiQ-quantized (`oQ4`)** | `oq.py` (349 KB) is the converter/runtime module | Every `*-oQ4*` / `*-OptiQ-4bit` model in `stats.json` served requests |

Because the fallback is "let mlx-lm try", the honest statement is: **oMLX loads anything
mlx-lm loads, plus explicit dispatch for `compressed-tensors`, `paroquant`, `fp8`/`mxfp8`, and
`mxfp4`.** The set cannot be enumerated from a positive list, because there isn't one.

### 7.2 Formats it refuses or cannot load

| Case | Evidence | Behaviour |
|---|---|---|
| `paroquant` without the extra package | `model_loading.py:1275–1279` | `ImportError` with the install hint |
| Qwen3.8 ModelOpt `compressed-tensors` loaded as text-only | `model_loading.py:1265–1269` | `ValueError`, explicit refusal |
| VLM load where the ParoQuant loader returned text-only | `model_loading.py:1282–1286` | `ValueError` |
| Architectures on the deny list | `model_discovery.py:256–258` `UNSUPPORTED_MODEL_TYPES`, `UNSUPPORTED_ARCHITECTURES`; checked at `model_discovery.py:421–426` | Filtered at discovery — the model never appears in `/v1/models` |

Both deny-lists are **empty sets** in 0.6.4 (`UNSUPPORTED_MODEL_TYPES: set[str] = set()`,
`UNSUPPORTED_ARCHITECTURES: set[str] = set()`). Discovery refuses nothing by architecture out
of the box.

### 7.3 `trust_remote_code`

`ModelSettings`/`engine/batched.py:50` default `trust_remote_code=False`. `config.py:76–78`
records the reason: *"Security: default off. HuggingFace repos can ship arbitrary
`modeling_*.py` that gets executed at load time when this is True. Issue #926."* There is **no
`serve` flag for it**, so a checkpoint needing remote code needs a settings or per-model
change. Note `engine/vlm.py:387` defaults the VLM path to `trust = True` before kwargs override
it — a positional difference worth knowing.

`utils/model_loading.py:60`: if a `model_file` is given and `trust_remote_code` is false, the
custom file is not executed.

---

## 8. What silently changes performance without appearing in the start command

### 8.1 Burst decode — the direct analogue of mlx-optiq's `--stream-experts`

**The start command does not contain it. `settings.json` does, and the CLI converts it into
environment variables at startup.**

`settings.json` key `server.burst_decode_mode` → `burst_decode_env()` (`settings.py:148–162`):

```python
BURST_DECODE_MODES: dict[str, tuple[int, float]] = {
    "off": (1, 0.0),
    "light": (64, 0.05),
    "balanced": (64, 0.1),
    "aggressive": (64, 0.2),
}
DEFAULT_BURST_DECODE_MODE = "balanced"
```

exported by `cli.py:179–182`:

```python
# Seed Burst Decode env vars so EngineConfig picks up the saved mode at
# engine construction (no restart needed when the mode changes later).
for _key, _value in burst_decode_env(settings.server.burst_decode_mode).items():
    os.environ[_key] = _value
```

which `EngineConfig` reads at construction (`engine_core.py:176–188`). **Visible cost or
benefit, per the source's own comment (`settings.py:135–138`): "higher = faster, but tokens
stream in larger chunks".**

| Mode | `max_steps` | single-request budget | Consequence for a cell |
|---|---|---|---|
| `off` | 1 | 0.0 | One step per hand-off; finest deltas; the ~74 tok/s path |
| `light` | 64 | 0.05 s | — |
| **`balanced` (default, and this machine)** | 64 | **0.1 s** | ~0.1 s deltas; the ~80 tok/s path |
| `aggressive` | 64 | 0.2 s | Fewest, largest deltas |

Note `burst_decode_env` does **not** set `OMLX_DECODE_BURST_BUDGET_S`, so the *concurrent*
budget stays at its 0.03 s default regardless of mode. Only the single-request budget moves.
Because the budget is adaptive on concurrency (§5.2B), **a cell's delta granularity depends on
how many requests were in flight**, which is a function of the harness's own concurrency, not
of the model.

`decode_burst_max_steps` is documented as "a safety cap (bounds the host-side output list), NOT
a memory knob" (`engine_core.py:174–175`).

### 8.2 Memory guard — on by default, off on this machine

`MemorySettings.prefill_memory_guard` ships **`True`** (`settings.py:503`). This machine has it
**`false`**. When on, it does three things that all change a measurement:

- **Admission pause + LRU eviction** at `soft_threshold` × ceiling (default 0.85),
- **in-flight abort** at `hard_threshold` (default 0.95),
- **adaptive prefill throttling**: when current memory ≥ `hard_cap × prefill_safe_zone_ratio`
  (default 0.80), the next chunk is sized so its predicted transient stays under the cap; if
  even `prefill_min_chunk_tokens` (32) would exceed it, the request is **aborted**
  (`settings.py:516–521`).

`scheduler.prefill_priority` decides what gets sacrificed: `"context"` (default) shrinks
prefill steps "down to the floor so the largest possible prompt still completes (slower near
the ceiling)", `"speed"` "never shrinks; keep full-size steps and only admit prompts that fit
at full speed (smaller effective context limit)" (`settings.py:287–292`). Two machines with
different values measure different prefill speeds for the same prompt.

`scheduler.decode_fairness` (default `True`, `settings.py:293–297`) force-chunks prompts under
contention, caps chunks while any engine decodes, and makes each chunk repay a decode time
debt. Turning it off restores pre-fairness behaviour. **This directly changes TTFT under
concurrency.**

### 8.3 The paged SSD prefix cache and the hot cache

`cache.enabled` ships `True` and this machine has it **`false`** — matching the probe recipe's
`--no-cache`. When enabled it silently serves prefixes from disk, which is the single largest
silent TTFT determinant available: a warm prefix cache turns a large prefill into a lookup.
`cache.ssd_cache_max_size` defaults to `auto` = 10% of SSD capacity
(`settings.py:401–414`), so the effective cache size depends on the disk, not the config.

`hot_cache_max_size` (default `0`, disabled) adds a RAM tier; `hot_cache_write_through`
persists every block immediately. `ane_compile_cache` (default `False`) sets
`OMLX_QWEN35_ANE_COMPILE_CACHE=1` (`cli.py:117–118`), and because the native gate reads the
variable once at the first ANE compile (`settings.py:340–343`), changing it needs a restart.

**The cache is also a persistence hazard across runs:** SSD cache contents survive process
restart, so a "cold" run is only cold if the cache was cleared or disabled.

### 8.4 Automatic model unloading

`idle_timeout.idle_timeout_seconds` (default `None` = no TTL) is a **global** fallback TTL that
the engine pool applies per model (`engine_pool.py:3097–3126`). If set, a model can be evicted
between two cells of a run, and the next request pays a cold load. Minimum value 60 s
(`admin/routes.py:360`). Cold load time is a separate metric and must never be folded into the
first request.

### 8.5 Model fallback

`model.model_fallback` (default `False`) makes the server serve *a default model* when the
requested id is not found. With it on, a typo in a cell's model name returns 200 with the wrong
weights. `hide_helper_models` similarly controls whether dFlash/Assistant/Draft helpers appear
in `/v1/models`, which affects model enumeration.

### 8.6 Settings that are read only at specific moments

Two settings are latched, not live: `cache.ane_compile_cache` (read at the first ANE compile)
and the `OMLX_DECODE_BURST_*` variables (read at **engine construction**). The burst variables
being re-seeded per request is why "no restart needed when the mode changes later" holds —
engines loaded later pick up the new mode, but an already-loaded engine keeps the old budget.

### 8.7 Features that can be enabled but are off here

`server.distributed_inference_enabled` (`false`) gates the whole cluster surface; off ⇒ 404
(`server.py:362–367`). `mcp.expose_tools` (`true`) and the `integrations.*` block add
network-facing tools if configured. None are active on this machine.

---

## 9. Address and ports

| Source | Value |
|---|---|
| `settings.json` `server.port` | **8106** |
| `omlx serve --help` prose default | 8000 |
| `settings.py` `ServerSettings.port` | 8000 |

**The server binds 8106 on this machine, not 8000 and not 8100.** The project's standing note
that oMLX uses port 8100 is not what `settings.json` says. Bind address is `127.0.0.1`,
multi-bind is supported via a comma-separated `--host` (`cli.py:220–247`), and the port is
bound *before* models preload so a conflict fails fast (`cli.py:217–219`, `cli.py:236`).

---

## 10. What I could not determine

Stated plainly, with the reason, per the rule that a negative claim needs better evidence than
a positive one.

1. **The exact number of tokens per delta under each burst mode.** I have the budget (0.1 s) and
   the observed rate (15 deltas over 1.668 s ⇒ 0.111 s per delta, ~8.5 tokens per delta at 128
   tokens). Deriving the mapping exactly would need a live run with delta timestamps, which
   this dispatch forbids.
2. **Whether `mxfp4` models take a different code path that changes speed.** `oq.py` and
   `patches/` contain model-family-specific overrides (e.g. `deepseek_v4/utils_patch.py:210`
   sets `{"group_size": 32, "bits": 4, "mode": "mxfp4"}`) but I did not trace whether any are
   active for the models in `~/.cache/huggingface/hub`. This needs a per-model probe.
3. **The complete per-model VLM/OCR default surface.** `engine/vlm.py` contains
   `OCR_MODEL_GENERATION_DEFAULTS` applied when a model's `config_model_type` is in
   `OCR_MODEL_TYPES` (`server.py:1744–1759`), which silently overrides generation defaults for
   those models. I did not enumerate which types or what the overrides are.
4. **Whether the 5.499 s TTFT in the older record came from the content channel or from a cold
   model load.** The corrected table shows content at 2.352 s and reasoning at 0.685 s; neither
   is 5.499 s. The two figures come from different runs under different conditions, and I have
   no artifact that reconciles them. The 5.499 s figure should be treated as unreproduced.
5. **Whether any code path sets `stream_interval` above 1.** Grep across the whole bundle finds
   only the three defaults and the internal uses; nothing assigns a different value. So it is
   effectively fixed at 1, but "nothing assigns it" is weaker evidence than a positive
   constraint, and I am labelling it as such.
6. **`process_memory_enforcer.py` (78 KB) and `memory_monitor.py` (66 KB) were surveyed, not
   read.** They contain reclaim heuristics (including `OMLX_DISABLE_PRESSURE_RECLAIM=1` to
   restore stock behaviour, `process_memory_enforcer.py:1484`, `1516–1517`) whose thresholds
   could add further silent performance determinants. §8.2 covers the settings-level surface;
   the internal heuristics are not audited here.

---

## 11. Reproduction of the one live fact cited

Everything else in this document is static. The log lines in §6.2 and the request counts in
§7.1 come from files already on disk and can be re-read without starting anything:

```
grep "Chat completion:" ~/.omlx/logs/*.log
cat ~/.omlx/stats.json
```

The two-channel timing table in §5.2A is quoted from this project's own
`docs/research/2026-09-15-omlx-streams-in-the-reasoning-channel.md`, which records the probe
that produced it. It is cited, not re-derived.

---

## 12. Summary — the eight questions this document was written to answer

1. **Entry points.** Three shell scripts and a bundled CPython 3.11.10. `omlx-cli` resolves its
   own location safely through symlinks; the `~/.omlx/bin/omlx` shim hardcodes the app path and
   breaks if the bundle moves. `PYTHONHOME` override means a project venv is invisible to it.
2. **Command-line surface.** Full table in §2.2. **The `--help` "default:" strings are prose,
   not argparse defaults** — every flag is `default=None` and real values come from
   `settings.json`. CLI flags are persisted into `settings.json`, including a `--model-dir`
   that is now a deleted path.
3. **Settings surface.** `~/.omlx/settings.json`, 17 top-level keys. The settings with **no CLI
   equivalent** are enumerated in §3.3; `sampling.top_k` (this machine: 20, not the shipped 0)
   and `server.burst_decode_mode` are the two most likely to move a number.
4. **Per-request fields.** §4.3. `top_k`, `min_p`, `repetition_penalty`,
   `repetition_context_size`, `xtc_*`, `thinking_budget`, `reasoning_effort`,
   `chat_template_kwargs`, `specprefill*`, `structured_outputs`, `guided_grammar`,
   `stream_options.include_usage`, `seed`. No streaming-granularity field exists.
5. **Streaming.** Reasoning streams incrementally in `reasoning_content`; `content` can arrive
   as a single mirrored delta. `stream_interval` is 1 and unsettable. **Two independent
   mechanisms** explain the single content delta: the thinking-parser recovery path at
   `api/thinking.py:350–358` (fires when the thinking block is never closed — e.g. when
   `max_tokens` cuts it off) and decode-burst coalescing at `engine_core.py:326–369` +
   `output_collector.py:117–164`. The keepalive frame is a valid chunk with empty content
   emitted before prefill (§5.5).
6. **Token accounting.** Standard counts plus oMLX timing extensions; **reasoning is not
   separated**. Self-reported rates are **not trustworthy for short generations** — recorded
   evidence of 15,286.6 tok/s against 76.3 tok/s for the same model, mechanism in §6.2.
7. **Silent performance determinants.** Burst decode seeded from settings into env vars;
   memory guard tiers and thresholds; SSD/hot prefix caches; `decode_fairness`; `prefill_priority`;
   idle-timeout model eviction; `model_fallback`. §8.
8. **Quantization.** Loads everything mlx-lm loads, plus explicit dispatch for
   `compressed-tensors`, `paroquant`, `fp8`/`mxfp8`, `mxfp4`. Refuses a text-only load of the
   Qwen3.8 ModelOpt VLM checkpoint and errors informatively when ParoQuant is not installed.
   §7.
