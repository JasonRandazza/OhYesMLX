# vMLX 1.6.59 — runtime capability and configuration reference

Written 2026-09-15 by static inspection only. Nothing in this document was established by
starting the server, loading a model, or sending a request; the harness coordinator runs live
probes separately. Every claim below carries its evidence inline.

**Version.** `vmlx_engine/__init__.py:15` → `__version__ = "1.6.59"`. `Info.plist`
`CFBundleShortVersionString` `1.6.59`, `CFBundleVersion` `1.6.59`, `CFBundleIdentifier`
`net.vmlx.app`, `NSHumanReadableCopyright` `Copyright 2026 JANGQ AI. All rights reserved.`
There is **no `--version` flag** on the CLI (verified: `vmlx --version` →
`error: unrecognized arguments: --version`), and no version subcommand. See §9.4.

**Evidence convention.** Source citations are relative to the bundle root
`$SRC = /Applications/vMLX.app/Contents/Resources/vmlx-engine-source/vmlx_engine/`. So
`server.py:6199` means `$SRC/server.py` line 6199. Citations under
`bundled-python/python/bin/`, `~/Library/Application Support/vmlx/` and `~/.cache/vmlx-engine/`
are given in full. Command-line citations prefixed `--help` mean the literal output of running
that subcommand's `--help`, which is static and was captured with the server never started.

**The governing rule, restated because this document exists because of it.** `--help` documents
a command line. It does not document a runtime. vMLX's real configuration surface spans five
places, and the largest of them is not the command line:

1. the command-line flags (`cli.py`),
2. **438 distinct `VMLX_*` / `VMLINUX_*` environment variables read from the shipped source**,
   none of which appear in any start command,
3. `~/Library/Application Support/vmlx/chats.db`, a SQLite database the GUI writes its settings
   into, which the GUI then translates into the same CLI flags with its own defaults,
4. per-request fields the OpenAI-compatible endpoint honours (`api/models.py`),
5. behaviour that is only in the shipped source (`server.py`, `output_collector.py`,
   `native_mtp_ar_safety.py`, `utils/jang_loader.py`).

A claim that vMLX *cannot* do something needs evidence from 2–5, not from the absence of a flag
in 1.

**One instruction tension, resolved and stated rather than hidden.** The dispatch asks for
streaming behaviour to be *measured, not inferred*, and simultaneously forbids starting the
server, loading a model, or sending a request. Those cannot both hold. The static limit is the
explicit hard limit and the coordinator owns live probes, so §5 quotes the exact line that
decides each behaviour and §5.9 states precisely what a live probe must confirm and what
observation would falsify each claim. Nothing in §5 is a guess dressed as a measurement.

---

## 1. Entry points

### 1.1 The executable chain

There is one shell script between the binary on `PATH` and Python.

| # | Path | Kind | What it does |
|---|---|---|---|
| 1 | `/Users/jrazz/.local/bin/vmlx` | POSIX `sh` script, 265 bytes, mode `-rwxr-xr-x` | `exec "/Applications/vMLX.app/Contents/Resources/bundled-python/python/bin/vmlx" "$@"` |
| 2 | `…/bundled-python/python/bin/vmlx` | `sh`/Python polyglot console script | `'''exec' "$(dirname "$0")/python3" -B -s "$0" "$@"` then `from vmlx_engine.cli import main` |
| 3 | `…/bundled-python/python/bin/python3` | CPython 3.12 (symlink → `python`) | Runs `$0` as the module with `-B -s` |

The `~/.local/bin/vmlx` shim is a **real file, not a symlink**, and its own comment states the
reason verbatim:

```sh
#!/bin/sh
# vMLX ships a bundled Python whose console scripts resolve python3 relative to their own
# directory, so a symlink into ~/.local/bin breaks them. Exec in place instead.
exec "/Applications/vMLX.app/Contents/Resources/bundled-python/python/bin/vmlx" "$@"
```

**That comment is correct, and the mechanism is worth being exact about.** The bundled console
script's first line is the `sh`/Python polyglot idiom:

```sh
#!/bin/sh
'''exec' "$(dirname "$0")/python3" -B -s "$0" "$@"
' '''
```

`$0` is the path the kernel was given, *without* resolving symlinks. `dirname "$0"` is therefore
the directory the script was *reached through*, not the directory it lives in. Invoked as a
symlink at `~/.local/bin/vmlx`, it looks for `~/.local/bin/python3` — which does not exist, and
there is no error beyond `exec` failing. **A symlink into `~/.local/bin` breaks this runtime;
a wrapper that `exec`s the bundle path does not.** That is the opposite of oMLX, where the
`omlx-cli` script uses `realpath "$0"` and survives symlinking, while its separate
`~/.omlx/bin/omlx` shim hardcodes the app path and breaks when the bundle moves.

The two interpreter flags matter for reproducibility: `-B` suppresses `.pyc` writes into the
signed bundle, `-s` suppresses the user site-packages directory. Neither prevents `PYTHONPATH`
from being honoured, so an inherited `PYTHONPATH` still applies.

### 1.2 The four wrappers on this machine

`~/.local/bin` contains four wrappers, all byte-identical apart from their target. They are
plain files, not symlinks, each `exec`ing the corresponding bundled console script:

| Wrapper | Target | Console script entry |
|---|---|---|
| `~/.local/bin/vmlx` | `…/python/bin/vmlx` | `from vmlx_engine.cli import main` |
| `~/.local/bin/vmlx-engine` | `…/python/bin/vmlx-engine` | `from vmlx_engine.cli import main` |
| `~/.local/bin/vmlx-serve` | `…/python/bin/vmlx-serve` | `from vmlx_engine.cli import main` |
| `~/.local/bin/vmlx-engine-bench` | `…/python/bin/vmlx-engine-bench` | `from vmlx_engine.benchmark import main` |

**`vmlx`, `vmlx-engine` and `vmlx-serve` are the same entry point.** All three import
`vmlx_engine.cli.main`; they differ only in `sys.argv[0]`, which the script normalises with
`sys.argv[0] = sys.argv[0].removesuffix('.exe')`. Nothing in the CLI dispatches on the
invocation name. `vmlx-engine-bench` is the only one with a different entry point, and it is
reachable two ways: `vmlx bench …` (subcommand) and `vmlx-engine-bench …` (direct).

Two further console scripts ship in the bundle with **no** wrapper on this machine's `PATH`:
`vmlx-engine-chat` and `vmlx-worker`. `vmlx-worker` is the distributed-inference worker side of
`--distributed`.

### 1.3 Other executables shipped in the bundle

`…/bundled-python/python/bin/` holds **144 entries**. Only a handful are vMLX's own; the rest
are dependencies' console scripts, and they are reachable and runnable even though nothing on
`PATH` points at them.

| Family | Examples | What they are |
|---|---|---|
| vMLX's own | `vmlx`, `vmlx-engine`, `vmlx-serve`, `vmlx-engine-chat`, `vmlx-engine-bench`, `vmlx-worker` | See §1.2 |
| JANG tooling | `jang`, `jang-convert-{gemma4,mistral3,qwen35,zaya,kimi,laguna,mimo-v2}-{jang,jangtq,mxfp4,mxfp8}`, `jang-verify-mimo-v2`, `jang-mmlu`, `jang-laguna-runtime`, `jang-mistral3-runtime` | The JANG quantiser and per-family converters. **This is the format toolchain behind §8** |
| mlx-lm / mlx-vlm | `mlx_lm`, `mlx_lm.chat`, `mlx_lm.benchmark`, `mlx_lm.manage`, `mlx_vlm.convert`, `mlx.distributed_config` | Upstream MLX tools, bundled |
| mflux (image) | `mflux-generate*`, `mflux-capabilities`, `mflux-concept*`, `mflux-upscale-*` | The image-generation backend behind `--mflux-class` / `--image-mode` |
| dflash | `dflash` | The DFlash2 lane; see §6.3 |
| HF / misc | `hf`, `huggingface-cli`, `fastapi`, `httpx`, `mcp`, `typer`, `jsonschema` | Dependencies |

`…/Contents/MacOS/vMLX` (53 KB) is the Electron launcher; `…/Contents/Resources/app.asar`
(84,989,152 bytes) is the GUI application. `LSMinimumSystemVersion` is `26.0.0`, and the
bundle carries the entitlements-facing usage strings (`NSMicrophoneUsageDescription`,
`NSCameraUsageDescription`, …) that the audio/video paths need.

### 1.4 The GUI is a second entry point that composes the same flags

The GUI is not a separate server. It builds a `vmlx serve` argument vector from its own stored
settings and spawns the same CLI. The settings it reads are in SQLite, not a config file (§3.2),
and it divides some of them by 100 on the way out (`app.asar:133153`
`args.push("--cache-memory-percent", (cacheMemoryPercent / 100).toString())`). **A cell started
from the GUI and a cell started from the command line are not the same cell unless the flags are
reconciled by hand.** The harness drives the CLI, so this document's §2 is authoritative for it;
§3.2 exists so that a GUI-launched run can be recognised as different.

---

## 2. The command-line surface

### 2.1 Top level

```
usage: vmlx [-h]
            {serve,bench,bench-detok,convert,info,list,doctor,bundle-check}
            ...

vmlx-engine: Apple Silicon MLX backend for vLLM
```

| Command | Purpose |
|---|---|
| `serve` | Start OpenAI-compatible server — **the one a benchmark uses** |
| `bench` | Run benchmark (in-process, not over HTTP) |
| `bench-detok` | Benchmark streaming detokenizer optimization |
| `convert` | Convert HuggingFace model to quantized MLX **or JANG** format |
| `info` | Display model metadata |
| `list` | List models in a directory |
| `doctor` | Run diagnostics on a model directory |
| `bundle-check` | Validate a local model bundle and atomically repair safe index defects |

There is no `--version` and no global option other than `-h`.

### 2.2 `serve` — the full flag surface

Verified against `vmlx serve --help` (580 lines, captured in full).

**Unlike oMLX, these "default:" strings ARE argparse defaults.** oMLX declares every flag
`default=None` and pulls real values from `settings.json`, so its help text is prose. Here the
defaults are declared in the parser and are the values used — `--stream-interval` is
`default=8` (`cli.py:3748`) and the help says `(default: 8)`; `--port` is `default=8000`. Where
a default is genuinely conditional the help says so (`--image-quantize`: "default: auto-detect
from model name").

#### 2.2.1 Positioning

| Flag | Default | Controls |
|---|---|---|
| `model` (positional) | required | HuggingFace model name **or local path**. First argument — unlike `optiq serve --model` and `mlx_lm.server --model` |
| `--served-model-name` | `None` | Custom name exposed via `/v1/models`. Default: auto-extracted from the model path (§9.5) |
| `--host` | `127.0.0.1` | Bind interface; `0.0.0.0` = LAN |
| `--port` | `8000` | TCP port |
| `--uds` | `None` | Unix socket path; **`--host` and `--port` are then ignored entirely** |
| `--api-key` | `None` | Require `Authorization: Bearer <key>`. Unset ⇒ **no auth at all** (§4.2) |
| `--rate-limit` | unset | Max requests/minute per client IP; `0` = no limit |
| `--timeout` | `300` | Per-request wall clock before cancellation |
| `--log-level` | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR` |
| `--allowed-origins` | `*` | CORS origins |

#### 2.2.2 Batching and streaming

| Flag | Default | Controls |
|---|---|---|
| `--stream-interval` | **`8`** | Tokens generated before a streaming update is sent. Applied only when `--continuous-batching` is on; forced to `1` otherwise (`cli.py:2892`). **See §5.2 — this is the single most important flag for a streaming measurement on this runtime** |
| `--continuous-batching` | enabled | Enables prefix cache, in-memory paged cache, stored-cache codecs, concurrent users |
| `--no-continuous-batching` | — | Direct single-request engine; disables the features above |
| `--max-num-seqs` | `1` | Simultaneous requests. Requires `--continuous-batching` |
| `--prefill-batch-size` | `512` | Prompts processed at once during prefill |
| `--prefill-step-size` | `2048` | Max tokens per prefill chunk. Lower it for large MoE at long context (Metal single-buffer OOM). **Note:** Hybrid models (e.g. Qwen3.5) default to one-shot prefill and bypass this flag unless `VMLX_ALLOW_HYBRID_CHUNKED_PREFILL=1` is exported in the environment (see `docs/research/2026-09-17-vmlx-32k-chunked-prefill.md`). |
| `--completion-batch-size` | `512` | Responses decoding simultaneously |
| `--prefill-keep-alloc` | off | Skips per-chunk `mx.clear_cache()`, by setting `VMLX_PREFILL_KEEP_ALLOC=1` |
| `--max-tokens` | `4096` | Default output cap; per-request `max_tokens` overrides |
| `--max-prompt-tokens` | auto | Max prompt accepted before prefill; auto memory-safe limit if omitted |

#### 2.2.3 Caches

| Flag | Default | Controls |
|---|---|---|
| `--enable-prefix-cache` | **enabled** | Cache computed KV for prompt prefixes. RAM only |
| `--disable-prefix-cache` | — | Turn it off |
| `--dsv4-enable-prefix-cache` | — | **Deprecated** compatibility flag; DeepSeek-V4 now follows the normal controls |
| `--prefix-cache-size` | `100` | Max cached prefixes — legacy entry-count mode only, ignored when memory-aware is active |
| `--prefix-cache-max-bytes` | `None` | Global byte budget; eviction priority assistant → user → system |
| `--cache-memory-mb` | auto | Fixed prefix-cache budget. Default auto ≈20% of available RAM |
| `--cache-memory-percent` | `0.15` | Fraction of available RAM when auto-detecting. **Decimal: 0.15 = 15%** (`app.asar` stores the integer `15` and divides by 100) |
| `--no-memory-aware-cache` | — | Fall back to entry-count eviction. Help says "Not recommended" |
| `--cache-ttl-minutes` | `0` | Evict entries not accessed within N minutes; `0` = never |
| `--ssm-state-cache-size` | `0` | Retained in-RAM SSM companion entries; `0` keeps typed state SSD-only |
| `--ssm-state-cache-mb` | `0` | RAM budget for the same |
| `--use-paged-cache` | **off** | In-RAM block paged cache. Requires `--continuous-batching` |
| `--no-paged-cache` | — | Disable the generic in-memory paged tier; block disk cache may stay as SSD-only |
| `--paged-cache-block-size` | `64` | Tokens per content-addressed block |
| `--max-cache-blocks` | `1000` | Max indexed blocks; caps the RAM pool (paged on) or the in-memory index (SSD-only) |
| `--kv-cache-quantization` | native/auto | `none`/`q4`/`q8`. **Omitting it selects "production auto mode" and passing it explicitly disables loader-level TurboQuant** (§7.2) |
| `--kv-cache-group-size` | `64` | Group size; used only when quantization is q4/q8 |
| `--enable-disk-cache` | **off** | Persist prompt KV to SSD, surviving restarts. Requires `--continuous-batching` |
| `--disk-cache-dir` | `~/.cache/vmlx-engine/prompt-cache` | — |
| `--disk-cache-max-gb` | `10` | Total size; `0` = unlimited |
| `--enable-block-disk-cache` | on when `--continuous-batching` + prefix cache | Content-addressed blocks to SSD; with paged on it is L2, with paged off it is the authoritative tier |
| `--disable-block-disk-cache` | — | Disable it, including the disk-only tier |
| `--block-disk-cache-dir` | `~/.cache/vmlx-engine/block-cache/<model_hash>` | — |
| `--block-disk-cache-max-gb` | unset | Overrides the percent when given; `0` = unlimited |
| `--block-disk-cache-max-percent` | `10` | Percent of the cache volume's capacity |
| `--no-state-machine-stops` | off | Disables token-level reasoning/stop detection, falling back to a legacy substring `<think>` scan |
| `--enable-vision-memory-cache` / `--no-vision-memory-cache` | **off** | Retain multimodal processor outputs in a RAM LRU. "Diagnostic opt-in; the shipping SSD-only profile leaves this off" |
| `--vision-memory-cache-size` | unset | Entries; no effect with `--no-vision-memory-cache` |

#### 2.2.4 Acceleration and MoE streaming

| Flag | Default | Controls |
|---|---|---|
| `--enable-jit` / `--no-jit` | **auto** | `mx.compile` on the forward pass. **Auto-ON for JANG affine bundles** — see §7.1; `--no-jit` is applied last and wins |
| `--speculative-model` | unset | Draft model for speculative decoding |
| `--num-draft-tokens` | `3` | Draft tokens per step |
| `--native-mtp-depth` | `3` | **Starting** depth for in-model MTP heads; wins over `VMLX_NATIVE_MTP_DEPTH` |
| `--native-mtp-depth-policy` | adaptive | `adaptive`/`fixed`. Both start at `--native-mtp-depth` and never exceed it |
| `--native-mtp-sampling-policy` | compatible-only | `compatible-only`/`deterministic-defaults`/`greedy-only`. **`greedy-only` forces temperature 0, top_p 1, top_k 0, min_p 0, repetition_penalty 1 even when the request asks otherwise** |
| `--disable-native-mtp` | off | Disable MTP even when the bundle has MTP tensors |
| `--enable-pld` | off | Prompt Lookup Decoding: n-gram draft verification, "~5-8x on long structured or repetitive output. Net-neutral or negative on short novel prompts" |
| `--pld-summary-interval` | `487` | Log a PLD effectiveness summary every N spec-decode tokens |
| `--smelt` | off | Load backbone + N% of MoE experts from SSD; claims ~50% RAM reduction at ~97% speed |
| `--smelt-experts` | `50` | Percentage of experts per MoE layer (10–100) |
| `--flash-moe` | off | Stream expert weights from SSD on demand; keeps active experts in a slot bank |
| `--flash-moe-slot-bank` | `256` | Expert weight sets cached in RAM |
| `--flash-moe-prefetch` | `none` | `none`/`temporal` |
| `--flash-moe-io-split` | `4` | Parallel I/O threads |
| `--omni-backend` | `stage1` | `stage1` PyTorch/MPS; `stage2` native MLX RADIO + Parakeet via `VMLX_OMNI_BACKEND=stage2` |

#### 2.2.5 Model, parsing and sampling

| Flag | Default | Controls |
|---|---|---|
| `--model-family` | auto | Force the family, bypassing detection from `jang_config.json`/`config.json`. Unknown names are honoured with a kv cache plus a warning |
| `--text-only` | off | Force text-only load. Overrides `--is-mllm` and autodetect |
| `--is-mllm` | off | Force multimodal load; autodetect checks `config.json` for `vision_config` |
| `--embedding-model` | unset | Separate embedding model for `/v1/embeddings`, alongside the chat model |
| `--enable-auto-tool-choice` | off | Let the model decide when to call tools; requires `--tool-call-parser` |
| `--tool-call-parser` | `auto` | 60+ named parsers (`qwen`, `llama`, `hermes`, `mistral`, `deepseek*`, `glm*`, `kimi*`, …) |
| `--tool-parser-plugin` | unset | Import a `.py`/module registering extra parsers; repeatable |
| `--reasoning-parser` | `auto` | `none`/`qwen3`/`deepseek_r1`/`poolside_v1`/`glm_think_block`/`minimax_m2`/`think_xml`/`openai_gptoss`/`inkling`/`mistral`/`gemma4`/`minimax_m3`/`dots3`/`muse_glimmer`/`muse` |
| `--default-temperature` | `0.7` fallback | Server-wide; per-request `temperature` overrides |
| `--default-top-p` / `--default-top-k` / `--default-min-p` / `--default-repetition-penalty` | unset | Server-wide. If unset, bundle metadata (`generation_config.json`/`jang_config`) is used when present |
| `--default-enable-thinking` | unset | `true`/`false`; per-request `enable_thinking` overrides |
| `--chat-template` | unset | Jinja2 template string override |
| `--chat-template-kwargs` | unset | JSON defaults for the template, e.g. `{"enable_thinking": false}` |

#### 2.2.6 MCP, distributed, image/audio

| Flag | Default | Controls |
|---|---|---|
| `--mcp-config` | unset | MCP config file (JSON/YAML); tools appear in `/v1/mcp/tools` |
| `--mcp-enabled-servers` / `--mcp-disabled-servers` | unset | Comma-separated allow/deny lists |
| `--mcp-enabled-tools` / `--mcp-disabled-tools` | unset | Comma-separated allow/deny lists |
| `--distributed` | off | Coordinator mode; discovers workers via Bonjour |
| `--cluster-secret` | unset | Shared secret for worker authentication |
| `--distributed-mode` | `pipeline` | `pipeline` or `tensor` (needs high bandwidth) |
| `--worker-nodes` | unset | `ip:port,ip:port` instead of Bonjour |
| `--inference-endpoints` | built-in list | Endpoints that keep the server awake / reset the idle timeout |
| `--wake-timeout` | `300` | Max wait for a JIT wake from deep sleep |
| `--image-quantize` | auto | `3`/`4`/`5`/`6`/`8` bits for mflux image models |
| `--image-mode` | auto | `generate` or `edit` |
| `--mflux-class` | unset | e.g. `Flux1`, `Flux2Klein`, `ZImage`, `QwenImageEdit` |
| `--lora-paths` / `--lora-scales` | unset | LoRA adapters and scales for image models |

### 2.3 The other subcommands

| Command | Flags |
|---|---|
| `bench` | `model` positional, plus the cache/batching subset: `--num-prompts`, `--max-tokens`, `--max-num-seqs`, `--prefill-batch-size`, `--prefill-step-size`, `--completion-batch-size`, `--enable-prefix-cache`/`--disable-prefix-cache`, `--prefix-cache-size`, `--cache-memory-mb`, `--cache-memory-percent`, `--no-memory-aware-cache`, `--cache-ttl-minutes`, `--ssm-state-cache-size`, `--ssm-state-cache-mb`, `--use-paged-cache`, `--paged-cache-block-size`, `--max-cache-blocks`, `--kv-cache-quantization`, `--kv-cache-group-size`, `--enable-disk-cache`, `--disk-cache-dir`, `--disk-cache-max-gb`, `--enable-block-disk-cache`/`--disable-block-disk-cache`, `--block-disk-cache-dir`, `--block-disk-cache-max-gb`, `--smelt`, `--smelt-experts`, `--flash-moe`, `--flash-moe-slot-bank` |
| `bench-detok` | `model` positional (default `mlx-community/Qwen3-0.6B-8bit`), `--iterations` |
| `convert` | `model` positional, `--output`/`-o`, `--bits`/`-b {2,3,4,6,8}`, `--group-size`, `--mode {default,NF4}`, `--jang-profile`/`-j`, `--jang-method {mse,rtn,mse-all}`, `--calibration-method {weights,activations}`, `--imatrix-path`, `--use-awq`, `--awq-alpha`, `--dtype`, `--force`, `--skip-verify`, `--trust-remote-code` |
| `info` | `model` positional |
| `list` | `directory` positional |
| `doctor` | `model` positional, `--no-inference` |
| `bundle-check` | `model` positional, `--no-repair`, `--no-cache`, `--json` |

> **`bench` is not the same measurement as `serve`.** It runs in-process. Two of its help
> strings say so explicitly: `--use-paged-cache` — "NOTE: bench does not apply the serve-path
> generic paged default-on; pass this explicitly to benchmark the paged backend", and
> `--dsv4-enable-prefix-cache` — "Default benchmarking uses full prefill because restored-cache
> output equivalence is not proven." A figure from `vmlx bench` is not a serving figure.
>
> Conversely, two bench flags are documented as deliberately *matching* serve, so that bench
> figures do describe serving: `--cache-memory-percent` — "Kept equal to serve: benchmarking
> under different cache defaults than the server actually uses produces numbers that do not
> describe serving" — and `--flash-moe-slot-bank` — "Kept equal to serve so a benchmark measures
> the shipped expert-cache size." The two directions coexist; read the help for the flag in
> question.

---

## 3. The settings surface beyond the command line

### 3.1 There is no settings file. This is the important negative.

**`vmlx serve` reads no configuration file.** A grep for config-file loading in `cli.py` returns
only *model* descriptors — `config.json`, `jang_config.json`, `tokenizer_config.json`,
`generation_config.json`, `chat_template.jinja` — every one of them read from inside the model
directory being served, never from a user config path. There is no `~/.vmlx/`, no
`~/.config/vmlx/`, and no `settings.json`.

Verified on this machine:

```
$ ls ~/.vmlx ~/.config/vmlx
ls: /Users/jrazz/.vmlx: No such file or directory
ls: /Users/jrazz/.config/vmlx: No such file or directory
```

Two consequences, both favourable to the harness compared with oMLX and Osaurus:

- **The start command is the whole truth for the CLI path.** There is no second layer that can
  silently override a flag. oMLX's hazard — flags persisted into `settings.json` and a stale
  `--model-dir` outliving the probe that set it — does not exist here.
- **The `--help` defaults are the real defaults** (§2.2), so a cell can be reconstructed from
  its command line.

What replaces the settings file is the environment (§3.3), and what replaces it for the *GUI*
is a SQLite table (§3.2).

### 3.2 The GUI's settings table

`~/Library/Application Support/vmlx/chats.db` is the Electron GUI's SQLite database. It has 15
tables; two carry configuration:

```sql
CREATE TABLE settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
      );

CREATE TABLE model_settings (
        model_path TEXT PRIMARY KEY,
        alias TEXT,
        temperature REAL,
        top_p REAL,
        max_tokens INTEGER,
        ttl_minutes INTEGER,
        pinned INTEGER DEFAULT 0,
        port INTEGER,
        cache_quant TEXT,
        disk_cache_enabled INTEGER DEFAULT 0,
        reasoning_mode TEXT DEFAULT 'auto'
      );
```

`settings` is a flat key/value store written on change, so **only keys that have been touched
appear in it** — the full key set is defined in `app.asar`'s `DEFAULT_CONFIG`, not in the
database. On this machine the table currently holds:

| key | value |
|---|---|
| `inference_mode` | `expert` |
| `gateway_port` | `8081` |
| `gateway_host` | `127.0.0.1` |
| `appMode` | `server` |
| `locale` | `en` |
| `ui_zoom_factor` | `1` |
| `sidebarCollapsed` | `false` |
| `notice_dismissed_version` | `1.5.45` |
| `image_settings` | `{"steps":4,"width":1024,"height":1024,"guidance":3.5,"negativePrompt":"","count":1,"strength":0.8}` |
| `migration_*` (8 keys) | timestamps |

Two facts worth carrying forward:

- **The GUI's default port is 8081, which collides with `mlx_lm.server`.** The harness registry
  assigns `mlxlm` port 8081 and `vmlx` port 8000 (`runtimes.RUNTIMES`). A GUI-launched vMLX on
  its 8081 default and an `mlxlm` cell cannot run at the same time; on its 8000 default it
  collides with the `vmlx` cell instead.
- **The GUI's defaults diverge from the CLI's in at least one place.** `DEFAULT_CONFIG`
  (`app.asar:53528`) sets `cacheMemoryPercent: 15`, and the arg builder divides by 100
  (`app.asar:133153`), so the GUI sends `--cache-memory-percent 0.15` — the same effective
  value as the CLI default. But `maxCacheBlocks` is *computed*
  (`app.asar:147218` `indexBlocksForCapacity(mutable.pagedCacheBlockSize)`) rather than fixed at
  the CLI's `1000`, and three startup-default functions (`applyMissingCacheStackStartupDefaults`,
  `applySsdFirstCacheDefaults`, `applyDefaultConfig`) rewrite cache settings for detected model
  families. **A GUI-launched server can run a different cache stack from a CLI-launched one
  serving the same weights.**

The GUI also enforces mutual exclusions the CLI does not: `smelt` and `flashMoe` turn each other
off (`app.asar`, `onChange("smelt", v2)` / `if (v2 && flashMoeActive) onChange("flashMoe", false)`),
and `enableJit` is forced off when a hybrid model is active. The CLI accepts both flags
simultaneously and leaves the outcome to the loader.

`model_settings` is a per-model override table (temperature, top_p, max_tokens, TTL, pin, port,
cache quant, disk cache, reasoning mode) applied by the GUI when it launches that model. It has
no CLI equivalent — the CLI has no per-model profile concept at all.

### 3.3 The 438 environment variables

This is the real "settings surface beyond the command line". The shipped source reads **438
distinct `VMLX_*` / `VMLINUX_*` variable names**, and **not one of them appears in any start
command**. `VMLINUX_*` names are the older spelling; most are read as a fallback pair, e.g.
`native_mtp_ar_safety.py:113-114`:

```python
def ar_safety_enabled() -> bool:
    return env_flag(True, "VMLINUX_NATIVE_MTP_AR_SAFETY", "VMLX_NATIVE_MTP_AR_SAFETY")
```

Most of the 438 are per-family kernel toggles (`VMLX_QWEN4_*`, `VMLX_GLM5_*`, `VMLX_DSV4_*`,
`VMLX_M3_*`, `VMLX_QWEN35_*`) that opt individual fused Metal kernels in or out. The complete
name list is in Appendix A. The subset that can move a **measured number** rather than select a
kernel is small, and it is this:

| Variable | Default | What it changes |
|---|---|---|
| `VMLX_DISABLE_JANG_AFFINE_JIT_DEFAULT` | `0` | `1` suppresses the automatic JIT-on for JANG affine bundles (§7.1). The supported way to A/B JIT without editing flags |
| `VMLX_DISABLE_TQ_KV` | unset in the ambient environment; **the CLI sets it to `1` itself** | Skips loader-level TurboQuant. Set on every path except the `VMLX_FORCE_TQ_AUTO=1` diagnostic, and again whenever `--kv-cache-quantization` is passed explicitly (`cli.py:60-91`, `cli.py:1510-1512`) — see §7.2 (research `2026-09-24-kv-quant-surface.md` §7.1) |
| `VMLX_FORCE_TQ_AUTO` | unset | `1` synthesises a 3-bit/4-bit TurboQuant config for bundles that have no `turboquant` block |
| `VMLX_NATIVE_MTP_AR_SAFETY` | `1` (on) | `0` disables the AR-safety valve, so a fixed MTP depth **never leaves its depth even when slower than plain decoding** (§7.4) |
| `VMLX_NATIVE_MTP_RUNTIME_COST_MARGIN` | `1.0` / `1.25` | Cost-gate margin. **Read in three places with two different defaults** — 1.0 for the windowed valve, 1.25 for the legacy runtime-cost gate |
| `VMLX_NATIVE_MTP_ADAPTIVE_DEPTH` | `1` (on) | Depth adaptation |
| `VMLX_NATIVE_MTP_DEPTH_PROBE` | unset | Overrides the depth-1 comparison for either depth policy |
| `VMLX_PREFILL_KEEP_ALLOC` | `0` | `1` skips per-chunk `mx.clear_cache()`; set by `--prefill-keep-alloc` |
| `VMLX_MEMORY_PRESSURE_GUARD` | **`0` (off)** | `1` enables admission rejection at a RAM percentage (§7.3) |
| `VMLX_MEMORY_PRESSURE_REJECT_PCT` | `97` | Rejection threshold for the above — inert while the guard is off |
| `VMLX_METAL_WS_GUARD` | **`1` (on)** | Metal working-set admission guard |
| `VMLX_METAL_WS_REJECT_PCT` | `98`–`99` | Occupancy where admission is refused. Caller-dependent (§7.3) |
| `VMLX_METAL_WS_MAX_GB`, `VMLX_METAL_WS_MAX_BYTES` | computed | Override the working-set ceiling |
| `VMLX_METAL_WIRED_HEADROOM_GB` | computed | Overrides `max(16 GiB, 30% of total RAM)` |
| `VMLX_MLX_CACHE_LIMIT_MB` | computed | Bounds MLX's allocator cache; computed default is 5% of model resident, clamped 512 MB–4 GB (`mlx_memory.py:79-81`) |
| `VMLX_MEMORY_TOTAL_BUDGET_PERCENT` | — | Total memory budget percentage |
| `VMLX_DEFAULT_KV_CACHE_QUANTIZATION` | — | Server-wide KV quantization default |
| `VMLX_PREFIX_CACHE_ENABLED`, `VMLX_PAGED_CACHE_ENABLED`, `VMLX_DISK_CACHE_ENABLED`, `VMLX_DISK_CACHE_DIR`, `VMLX_DISK_CACHE_MAX_GB` | — | Cache toggles and paths, mirroring the flags |
| `VMLX_SAMPLING_TEMPERATURE`, `VMLX_SAMPLING_TOP_P`, `VMLX_SAMPLING_TOP_K`, `VMLX_SAMPLING_MIN_P`, `VMLX_SAMPLING_REPETITION_PENALTY` | — | Server-wide sampling defaults. **These can change what a cell samples without appearing anywhere in the start command** |
| `VMLX_NUM_THREADS`, `VMLX_USE_METAL` | — | Thread count and Metal use |
| `VMLX_LOW_RAM_ADVISORY_GB` | — | Advisory threshold |
| `VMLX_LOG_REQUEST_FIELDS`, `VMLX_DEBUG_LOG_CACHE_HITS`, `VMLX_DEBUG_LOG_CACHE_MISSES`, `VMLX_DEBUG_LOG_MEMORY_USAGE` | — | Instrumentation toggles |
| `VMLX_CLUSTER_SECRET`, `VMLX_WORLD_SIZE`, `VMLX_RANK` | — | Distributed mode |

**The harness should treat the ambient environment as part of the start command.** A cell that
records its argv but not its `VMLX_*` environment has not recorded what it measured. The cheap
defence is to spawn with a scrubbed environment (or an allow-list) rather than inheriting the
shell's, which is the same class of guard as the `check_host_state` hook the other runtimes use.

### 3.4 Settings with no command-line equivalent

Stated as a table, because this is the list that decides what a cell measures.

| Setting | Equivalent flag? | Notes |
|---|---|---|
| Every one of the 438 `VMLX_*`/`VMLINUX_*` variables | **No** | Environment only |
| GUI `settings` table (`inference_mode`, `gateway_port`, `gateway_host`, `appMode`, …) | **No** | GUI only |
| `model_settings` per-model profiles | **No** | GUI only; the CLI has no per-model profile |
| `smelt` + `flashMoe` mutual exclusion | **No** | GUI enforces it; the CLI accepts both |
| `enableJit` forced off for hybrid models (GUI) | **No** | The CLI's own auto-JIT has its own exclusions; the two lists differ |
| `maxCacheBlocks` computed from block size (GUI) | **No** | The CLI default is the fixed `1000` |

Every flag in §2.2 *does* have a command-line equivalent, since §2.2 is enumerated from the
parser. The asymmetry with oMLX is that the CLI is complete here; the hidden layer is the
environment, not a file.

---

## 4. The API surface

### 4.1 Routes

All routes are defined in `server.py`; no `APIRouter`/`include_router` is used. `Auth` below
means the route carries `dependencies=[Depends(verify_api_key)]` — which, when no key is
configured, is a no-op that logs one warning (§4.2).

| Method + path | Auth | Source |
|---|---|---|
| `GET /` | none | `server.py:9624` |
| `GET /health` | **none** | `server.py:13346` |
| `GET /health.mtp` | **none** | `server.py:13776` |
| `GET /v1/models` | Auth | `server.py:16162` |
| `GET /v1/models/{model_id:path}/capabilities` | Auth | `server.py:16188` |
| `GET /v1/capabilities` | Auth | `server.py:16366` |
| `POST /v1/chat/completions` | Auth | `server.py:19520` |
| `POST /v1/chat/completions/{request_id}/cancel` | Auth | `server.py:16066` |
| `POST /v1/completions` | Auth | `server.py:19238` |
| `POST /v1/completions/{request_id}/cancel` | Auth | `server.py:16133` |
| `POST /v1/responses` | Auth | `server.py:22861` |
| `POST /v1/responses/{response_id}/cancel` | Auth | `server.py:16106` |
| `POST /v1/embeddings` | Auth | `server.py:16944` |
| `POST /v1/rerank` | Auth | `server.py:17102` |
| `POST /v1/messages` (Anthropic) | Auth | `server.py:16377` |
| `POST /v1/images/generations`, `/v1/images/edits`, `/v1/images/cancel` | Auth | `server.py:18313`, `18570`, `18175` |
| `POST /v1/audio/transcriptions`, `/v1/audio/speech`; `GET /v1/audio/voices` | Auth | `server.py:19056`, `19138`, `19220` |
| `GET /v1/cache/stats`, `/v1/cache/entries`; `POST /v1/cache/warm`; `DELETE /v1/cache` | Auth | `server.py:14211`, `14359`, `14490`, `15785` |
| `POST /v1/cache/prefix-attestation`, `/v1/cache/token-contract` | Auth | `server.py:15227`, `15570` |
| `POST /admin/soft-sleep`, `/admin/deep-sleep`, `/admin/wake` | Auth | `server.py:13875`, `13924`, `14200` |
| `GET /v1/cluster/status`, `/v1/cluster/nodes`; `POST /v1/cluster/nodes`, `/v1/cluster/scan`; `DELETE /v1/cluster/nodes/{node_id}` | Auth | `server.py:15969`–`16051` |
| `GET /v1/mcp/tools`, `/v1/mcp/servers`; `POST /v1/mcp/execute` | Auth | `server.py:18966`, `18992`, `19021` |
| Ollama-compat `/api/*` | Auth | `server.py:17227`–`18196` |
| `GET /openapi.json` | none | FastAPI default; **the only route carrying the version** |

**`/health` needs no key**, so a readiness poll works before a credential is wired up. That is
the same shape as oMLX.

**`POST /admin/deep-sleep` and `/admin/wake` exist and unload/reload the model.** A cell that
never calls them is unaffected, but they are the reason `--wake-timeout` (default 300 s) exists,
and it is worth knowing the runtime can be put to sleep by an endpoint rather than only by
idleness.

### 4.2 Authentication

`verify_api_key` (`server.py:7177`) returns `True` — **no auth** — when `_api_key is None`
(`server.py:5241` `_api_key: str | None = None`), logging one warning:

```python
if _api_key is None:
    # Log warning once about running without authentication
    if not _auth_warning_logged:
        logger.warning(
            "SECURITY WARNING: Server running without API key authentication. "
            "Anyone can access the API. Use --api-key to enable authentication."
        )
```

Otherwise it requires a bearer token and compares with `secrets.compare_digest`. A missing
credential is **401 `API key required`**; a wrong one is **401 `Invalid API key`**.

**vMLX needs no API key by default.** This is the direct opposite of oMLX, which answers an
unauthenticated `/v1/chat/completions` with 401 — the failure mode this project already recorded
once, where the readiness probe authenticated and the measurement did not. Here an unset
`--api-key` means `api_key()` on the Runtime subclass can return `None` and the handle records
`None` (§9.6), and the harness's existing 401 handling in `await_ready` is a safety net rather
than a requirement.

The startup banner prints the state on stdout (`cli.py:2387`):
`Authentication: DISABLED - Use --api-key to enable`.

### 4.3 Per-request fields beyond the standard set

`ChatCompletionRequest` (`api/models.py:231`). Standard OpenAI fields plus these extensions:

| Field | Line | Notes |
|---|---|---|
| `max_completion_tokens` | `244` | Alias of `max_tokens` |
| `top_k` | `251` | `0` = disabled |
| `min_p` | `252` | Min-p threshold |
| `repetition_penalty` | `253` | `1.0` = disabled |
| `timeout` | `292` | Per-request wall clock, overrides the server default |
| `max_prompt_tokens` | `296` | Inbound prompt cap |
| `max_context_tokens`, `max_context` | `297-298` | Context caps |
| `enable_thinking` | `300` | Thinking toggle |
| `reasoning_effort` | `302` | Effort hint |
| `max_thinking_tokens` | `303` | Reasoning budget |
| `thinking_mode` | `308` | Mode selector |
| `chat_template_kwargs` | `312` | Template kwargs |
| `reasoning` | `336` | Reasoning config dict |
| `cache_salt` | `330` | **Any non-empty value bypasses every cache tier** (§4.4) |
| `skip_prefix_cache` | `331` | Explicit cache bypass |
| `image_token_budget`, `image_max_pixels`, `image_min_pixels`, `image_resized_height`, `image_resized_width` | `272`, `286-289` | Vision controls |
| `video_fps`, `video_max_frames`, `video_max_pixels`, `video_min_pixels`, `video_total_pixels`, `video_resized_height`, `video_resized_width`, `video_token_budget` | `273-283` | Video controls |
| `media_controls_strict` | `290` | Reject unknown media controls |
| `stream_options.include_usage` | `225` | Emit the usage chunk on a stream |
| `stream_options.include_obfuscation` | `228` | — |

`CompletionRequest` (`api/models.py:603`) carries `top_k`, `min_p`, `repetition_penalty`,
`seed`, `frequency_penalty`, `presence_penalty`, `logit_bias`, `logprobs` (legacy integer form),
`timeout`, `max_prompt_tokens`, `max_context_tokens`, `max_context`, `cache_salt`,
`skip_prefix_cache`, `reasoning_effort`, `enable_thinking`.

`ResponsesRequest` (`api/models.py:986`) carries the same sampling set plus `text`,
`store: bool = False`, `previous_response_id`, `instructions`, the reasoning fields, the media
controls, and `cache_salt`/`skip_prefix_cache`. It sets
`model_config = {"extra": "ignore"}` (`:989`), so **unknown fields are silently dropped** on
this endpoint rather than rejected — a typo'd field name is invisible.

`EmbeddingRequest` (`api/models.py:857`) is minimal: `input`, `model`, `encoding_format`.

**Not present, despite being available on sibling runtimes:** no `xtc_probability` /
`xtc_threshold`, no `typical_p`, no `best_of`, no `priority`, no `session_id`, no
`guided_grammar` / `guided_json` / `structured_outputs` / `grammar`. Guided decoding exists but
is reached only through `response_format` with type `json_schema`, built by
`build_guided_json_logits_processor` (`api/tool_calling.py:3591`).

### 4.4 Cache-keying fields

There is no `session_id` and no `pin`. Cache reuse is controlled by exactly two fields:
`cache_salt` and `skip_prefix_cache`. `_compute_bypass_prefix_cache` (`server.py:3721-3748`)
treats **any non-empty salt as "please give me fresh state"** — no cache hits, no cache stores —
across paged/block, memory-aware, legacy prefix, L2 disk, block disk, SSM companion and the
vision caches. The field comment (`api/models.py:313-330`) recommends
`cache_salt: str(uuid.uuid4())` for a guaranteed cold request.

**This is the cleanest cold-cache lever the runtime offers, and it is per-request.**
`cache_salt` on every measured request removes the cross-run cache hazard in §7.5 without
disabling the cache in the start command and without touching the 22 GB already on disk.

Cache keys are token-sequence based. `_CACHE_CONTRACT_FORBIDDEN_SIDE_KEY_FIELDS`
(`server.py:14633-14648`) lists the side keys that may not silently enter a cache contract:
`cache_salt`, `media_salt`, `request_salt`, `skip_prefix_cache`. There is also a warm endpoint,
`POST /v1/cache/warm` with body `{"prompts": [...]}` (`server.py:14490`), which a harness could
use deliberately — and could trip over accidentally if it ever warms a cell it meant to measure
cold.

---

## 5. Streaming behaviour

### 5.1 Which channels it emits

The chat-completions stream is produced by `stream_chat_completion` (`server.py:24886`). The
delta model is `ChatCompletionChunkDelta` (`api/models.py:1250`), and the wire field names come
from it:

```python
class ChatCompletionChunkDelta(BaseModel):
    role: str | None = None
    content: str | None = None
    reasoning: str | None = Field(
        default=None, exclude=True  # Internal storage; excluded from JSON
    )
    tool_calls: list[dict] | None = None

    @computed_field
    @property
    def reasoning_content(self) -> str | None:
        """OpenAI O1-style reasoning field. Only present when thinking is enabled."""
        return self.reasoning
```

| Channel | Emitted as | Streaming? |
|---|---|---|
| `role` | `ChatCompletionChunkDelta(role="assistant")` | **First chunk only**, `server.py:24990-25000` |
| `content` | `delta.content`, `server.py:25848` | Yes, incrementally |
| `reasoning_content` | `delta.reasoning` → JSON `reasoning_content`, `server.py:25849` | Yes, incrementally in the normal path; **can arrive whole at finalization** (§5.4) |
| `tool_calls` | `delta.tool_calls`, `server.py:26250-26267` | **No — buffered and emitted whole after the stream** |
| `finish_reason` | final chunk, empty delta | Once |
| `usage` | `server.py:27121-27139` | Once, **only if `stream_options.include_usage`** |

**There is no `reasoning` (non-`_content`) key on the wire.** `reasoning` is the *internal*
pydantic field, declared `exclude=True`, and `reasoning_content` is a `@computed_field` that
returns it. The only JSON name that ever appears is `reasoning_content`. The `model_dump`
override (`api/models.py:1266-1276`) then pops the key when it is `None`, so a strict parser
never sees `reasoning_content: null`:

```python
d = super().model_dump(**kwargs)
if d.get("reasoning_content") is None:
    d.pop("reasoning_content", None)
return d
```

That override is worth knowing when writing a probe: **absence of the key is the normal case on
a non-reasoning turn, not a missing field.**

`tool_call_generating` exists on the chunk model (`api/models.py:1298`) but the chat SSE path
deliberately does not send it — see the comment at `server.py:25693-25694`. It is used on a
different endpoint (`server.py:28078`, `28208`).

### 5.2 Granularity — `--stream-interval`, and the one line that decides everything

The flag is declared at `cli.py:3745-3753` with `default=8`, and is applied at exactly one place
in the serve path (`cli.py:2892`):

```python
load_model(
    args.model,
    use_batching=args.continuous_batching,
    scheduler_config=scheduler_config,
    stream_interval=args.stream_interval if args.continuous_batching else 1,
    ...
```

**So `--no-continuous-batching` silently forces the interval to 1, discarding whatever
`--stream-interval` said.** A cell that passes both `--no-continuous-batching` and
`--stream-interval 8` measures the 1 behaviour and records 8. That is a genuine
record-versus-measure divergence and it is silent.

It reaches the engine at `engine_core.py:566-572` and is applied per request in the engine loop
(`engine_core.py:245-263`), gated by `RequestStreamState.should_send`
(`output_collector.py:212-230`):

```python
def should_send(self, total_tokens: int, finished: bool) -> bool:
    if finished: return True          # always send on finish
    if self.sent_tokens == 0: return True  # always send first token (low TTFT)
    return (total_tokens - self.sent_tokens) >= self.stream_interval
```

Skipped steps are accumulated and prepended to the next send (`output_collector.py:232-253`).
The counter is `completion_tokens`, so **batching is by generation step, not by character count
and not by delta count.**

Three consequences for a measurement:

1. **The first token and the final token are never withheld.** `should_send` returns `True` for
   both regardless of the interval. So TTFT is not inflated by `stream_interval`, and the last
   delta always arrives.
2. **The interval governs one counter, so it inevitably governs both rails.** The batching
   happens at the engine-output layer, on `req_output.new_text`, *before* any reasoning parsing.
   Reasoning/content splitting happens later, server-side, from the concatenated text
   (`server.py:25447`, `25519-25531`). **There is no separate reasoning interval and no separate
   reasoning counter anywhere.** One value controls both channels' granularity.
3. **`RequestOutputCollector(aggregate=True)`** (`engine_core.py:567-568`) is a second,
   independent coalescer: if the consumer falls behind, `put()` merges outputs
   (`output_collector.py:56-74`, `_merge_outputs` at `:123-171`). So even at
   `--stream-interval 1` a delta can carry more than one token.

### 5.3 No channel is mirrored into another

The two rails are set from independent values in the single delta build
(`server.py:25841-25850`):

```python
delta=ChatCompletionChunkDelta(
    content=emit_content,
    reasoning=emit_reasoning,
),
```

`emit_content` comes from `delta_msg.content`, `emit_reasoning` from `delta_msg.reasoning`
(`server.py:25713-25731`), and in the suppression branch the code explicitly refuses to
redirect one into the other (`server.py:25709-25711`):

```python
# Suppressed reasoning is never redirected into visible content.
# If a boundary delta carries both reasoning and content, only
# the content half is user-visible.
if suppress_reasoning:
    emit_content = delta_msg.content
    emit_reasoning = None
```

The only "duplication" is a field *rename* — the internal attribute `reasoning` is serialised
under the JSON name `reasoning_content`. **No text that appears in `content` originated in the
reasoning rail, and vice versa.** This is a materially different runtime from oMLX, where the
thinking-parser recovery path re-emits the accumulated reasoning text as a single `content`
delta so the same text appears twice. **vMLX has no equivalent of that mirroring**, and the
`suppress_reasoning` guard above is the reason to believe it is deliberate rather than
accidental. This is a positive claim from source, not an inference from a missing flag.

### 5.4 The one case where reasoning arrives whole

A parser may surface its full reasoning block only at stream finalization. vMLX handles that
explicitly (`server.py:26428-26451`):

```python
# A parser may surface its full reasoning block only at stream finalization.
# Emit that late block on the reasoning rail, never as visible content.
if (
    request_parser
    and not content_was_emitted
    and accumulated_reasoning
    and not reasoning_was_streamed
    and not suppress_reasoning
    and not (m3_reasoning_only_answer_enabled or reasoning_only_answer_enabled)
):
    fallback_chunk = ChatCompletionChunk(
        ...
            delta=ChatCompletionChunkDelta(
                reasoning=accumulated_reasoning,
            ),
```

**So `reasoning_content` is incremental in the normal path but can arrive as a single
finalization flush** when `reasoning_was_streamed` is False and the parser deferred. A probe
that assumes "reasoning always streams incrementally" can therefore see a one-delta reasoning
channel and must not read that as a failure. Critically, the fallback emits on the **reasoning
rail**, never into `content` — the opposite of oMLX's recovery path, which emits on the content
rail.

The reasoning parser is selected by `--reasoning-parser` (default `auto`); `none` disables it
entirely, in which case thinking text is not extracted into the reasoning field at all. Which
parsers defer to finalization is not enumerated in this document (§10).

### 5.5 `tool_calls` are buffered

Tool calls are collected during the stream and emitted only after it, in OpenAI's two-chunk
shape (`server.py:26197-26199`):

```python
# Emit tool calls in OpenAI-compatible streaming format (#46):
# Chunk 1: tool_calls data with finish_reason=null
# Chunk 2: empty delta with finish_reason="tool_calls"
```

During buffering the stream sends only neutral heartbeats (`server.py:25695-25706`). There is an
optional speculative START delta carrying empty name/arguments (`server.py:25667-25690`), but
**arguments always arrive whole.** A tools-enabled cell therefore cannot measure tool-call
streaming granularity on this runtime, because there is none.

### 5.6 The keep-alive frame — safe, unlike oMLX's

The chat stream is wrapped in `_stream_with_keepalive` (`server.py:24588`), whose interval is
`_SSE_KEEPALIVE_INTERVAL = 15.0` seconds (`server.py:24577`). On timeout it yields a `None`
sentinel that the generators convert to an **SSE comment** (`server.py:25392`):

```python
            yield ": keep-alive\n\n"
            continue
```

**This is a comment frame, not a data frame.** It begins with `:` and carries no `data:`, so a
spec-compliant SSE parser discards it and it cannot be mistaken for a token or for a first
token. This is the direct contrast with oMLX's `_chat_keepalive_chunk`, which is a
syntactically valid `chat.completion.chunk` with `"model":"keepalive"` and an empty `content`,
emitted *before* prefill — the trap that made a TTFT probe read approximately zero.

The residual hazard here is smaller but real: a probe that counts **raw lines** or **`:`-prefixed
frames** rather than parsing SSE events will inflate its event count by one per 15 s of silence.
Counting deltas by parsing `data: ` lines is sufficient.

There is a second, related behaviour: the timeout is progress-aware. `_stream_with_keepalive`
takes a `progress_probe` and only treats a request as wedged if no tokens advanced across a full
window (`server.py:24594-24606`). **`asyncio.wait_for` is deliberately not used**, because it
cancels on timeout and cancelling an async generator's `__anext__()` finalises it — the comment
is explicit that using it "kills the stream during long prefills or tool call generation."

### 5.7 Usage on a stream is opt-in

`include_usage` is read at `server.py:24944-24945`:
`include_usage = request.stream_options and request.stream_options.include_usage`. Non-terminal
chunks then carry `"usage": null` (`server.py:24960-24961`) and one choices-empty usage chunk is
emitted before `[DONE]` (`server.py:27121-27139`). On a non-streaming response usage is always
present (`ChatCompletionResponse.usage`, `api/models.py:587`).

### 5.8 The `--stream-interval` help text makes a causal claim the source does not support

The help text for `--stream-interval` asserts a three-step causal chain:

> Higher values batch tokens; 1 sends every token but is NOT recommended -- a per-token stream
> lets client backpressure stall the emit loop, and the speculative-decoding cost gate reads
> that stall as MTP cost and falls back to plain autoregressive decode.

The source does not bear this out, and this is exactly the class of claim — a plausible
mechanism asserted in prose — that this project has already been burned by once.

- **The engine loop cannot be stalled by client backpressure.** The producer side is
  non-blocking and aggregating (`output_collector.py:56-74`):

  ```python
  def put(self, output: RequestOutput) -> None:
      """Put an output into the collector (non-blocking)."""
      if self.output is None:
          self.output = output
      elif self.aggregate:
          self.output = self._merge_outputs(self.output, output)   # producer gets ahead → merge
  ```

  and the loop simply yields (`engine_core.py:289-293`). A classmethod `has_waiting_consumers()`
  exists (`output_collector.py:184-191`) but is **never called** — grep finds only its
  definition — so nothing gates stepping on consumer demand.

- **No backpressure signal reaches the MTP cost gate.** `grep -rn backpressure` across the
  engine finds the word only in this CLI help string (`cli.py:3751`) and in unrelated cache
  comments. The gate is wall-clock based, taking `time.perf_counter()` inside the model step
  (`patches/mlx_lm_mtp/batch_generator.py:1188`, `2138-2143`).

- **The valve is built to ignore isolated stalls.** `native_mtp_ar_safety.py:31-32` states the
  design: "a single stalled cycle cannot trip (median guard)", implemented at
  `native_mtp_ar_safety.py:190-192` where the window mean **and** the per-cycle median must both
  exceed the threshold.

The honest formulation, and the one to carry forward: **the literal chain in the help text is
unsupported; at most there is event-loop CPU contention from very frequent SSE work, which the
median guard exists to tolerate.** This does not change the practical advice — `--stream-interval`
defaults to 8 and a cell that wants the finest granularity sets 1, and both are recorded in the
start command — but the *reason* given for the default is not evidence, and a future document
should not cite it as such.

### 5.9 What a live probe must confirm

Each claim above is a line of code, so each has a falsifiable observation:

| Claim | Probe | What would falsify it |
|---|---|---|
| `reasoning_content` streams incrementally | Count deltas on a reasoning model with a **generous** `max_tokens` | One reasoning delta carrying the whole block |
| `content` and `reasoning_content` are independent | Compare their concatenations | Content text that duplicates reasoning text |
| `--stream-interval 8` batches by tokens | Deltas per response at interval 8 vs 1 | Identical delta counts at both settings |
| `--no-continuous-batching` forces interval 1 | Same, with and without `--continuous-batching` | Interval-8 batching while continuous batching is off |
| First and last delta are never withheld | Check the first delta's position against prefill | A first delta arriving only after the interval's worth of tokens |
| Keep-alive frames are comments | Parse raw SSE lines during a long prefill | A `data:` frame with `model":"keepalive"` |

**Use a generous `max_tokens` and a prompt the model finishes inside it.** The oMLX investigation
recorded how a tight `max_tokens` on a reasoning model manufactured a single-delta content
channel, and the resulting false conclusion about the runtime. vMLX's fallback flush (§5.4) is
triggered by parser deferral rather than by truncation, so the same probe design error produces
the same wrong answer here.

---

## 6. Token accounting

### 6.1 What the `usage` block reports

`Usage` (`api/models.py:570`) has exactly four fields:

```python
class Usage(BaseModel):
    """Token usage statistics."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    prompt_tokens_details: PromptTokensDetails | None = None
```

`PromptTokensDetails` (`api/models.py:558`) has `cached_tokens: int = 0` and
`cache_detail: str | None = None`. Built by `get_usage` (`server.py:9519`), which emits
`prompt_tokens_details` only when it is non-trivial:

```python
    prompt_tokens_details=PromptTokensDetails(
        cached_tokens=cached, cache_detail=detail
    )
    if cached > 0 or detail
    else None,
```

`cache_detail` is a tier tag: base values `"memory"`, `"prefix"`, `"disk"`, `"paged"`,
`"block-disk"`, with composite suffixes `+ssm`, `+disk`, `+mixed_swa`, `+zaya_cca`, `+tq-native`,
`+tq`.

**There is no timing and no rate in the usage block.** `generation_tokens_per_second`,
`generation_duration`, `time_to_first_token`, `prompt_tokens_per_second` and `total_duration`
**do not exist as usage fields on the chat endpoint at all.** A grep across the whole bundle for
`generation_tokens_per_second` finds nothing. This is very different from oMLX, where those are
the fields carrying the untrustworthy rate; here the chat response cannot carry a rate, trusted
or otherwise, because it has no field for one.

Sibling surfaces use different shapes: the Responses API uses `input_tokens`/`output_tokens`
(`api/models.py:1194`); the Anthropic adapter adds `cache_read_input_tokens` /
`cache_creation_input_tokens` (`api/anthropic_adapter.py:599-606`); the Ollama adapter uses
`eval_count`, `prompt_eval_count`, `total_duration`, `load_duration`, `prompt_eval_duration`,
`eval_duration` (`api/ollama_adapter.py:490-498`). **A harness comparing across these endpoints
is comparing different accounting schemes.**

### 6.2 Reasoning is NOT separated

There is no `reasoning_tokens` and no `completion_tokens_details` anywhere in the shipped engine
— a grep for both returns zero definitions. `completion_tokens` is one undifferentiated counter,
fed from a real engine counter (`scheduler.py:9573` `completion_tokens=request.num_output_tokens`).

Reasoning is carried as **message text**, not as a token bucket
(`server.py:3450` `"reasoning_content": accumulated_reasoning`). **If a cell needs the reasoning
token count, it must count reasoning deltas itself** — the same conclusion the oMLX document
reached, by the same absence.

### 6.3 The rate fields — where a 15286-class number comes from here

The chat endpoint cannot report a rate in the response. The runtime does log one, and there is a
private receipt on a different endpoint. Both are the same shape as the oMLX defect: a rate whose
denominator is a wall-clock window that can collapse toward zero.

**The log line** (`server.py:27141-27150`):

```python
    if (
        completion_tokens > 1
        and _decode_first_ts is not None
        and _decode_last_ts > _decode_first_ts
    ):
        _decode_elapsed = _decode_last_ts - _decode_first_ts
        logger.info(
            f"Chat completion (stream): {completion_tokens} tokens in "
            f"{_decode_elapsed:.2f}s "
            f"({(completion_tokens - _decode_first_count) / _decode_elapsed:.1f} tok/s decode) "
```

The guard rejects **exactly equal** timestamps but not nearly-equal ones. A microsecond-scale
window passes, and `(completion_tokens - _decode_first_count) / _decode_elapsed` is then
astronomically large. The same construction appears for the Responses stream at
`server.py:29425-29434`.

**Why the window can be nearly zero.** `_decode_first_ts` is stamped on the first observed
count advance, not at request start (`server.py:25414-25419`):

```python
            if completion_tokens > _decode_last_count:
                _decode_last_ts = _decode_output_timestamp(output)
                if _decode_first_ts is None:
                    _decode_first_ts = _decode_last_ts
                    _decode_first_count = completion_tokens
```

and `_decode_output_timestamp` prefers the producer's own `output.generated_at`
(`server.py:9559-9573`). When a speculative/MTP burst or a coalesced
`RequestOutputCollector` merge (§5.2) delivers many tokens under effectively one timestamp,
the first and last observations can be microseconds apart. This is the identical mechanism to
oMLX's: a burst completes the generation, the window collapses, and the rate explodes.

**The private receipt** is `_decode_usage_snapshot` (`server.py:9599`):

```python
    seconds = float(last_token_ts) - float(first_token_ts)
    if not math.isfinite(seconds) or seconds <= 0:
        return None
    tokens = int(completion_tokens) - int(first_token_count)
    return {
        "tokens": tokens,
        "seconds": seconds,
        "tokens_per_second": tokens / seconds,
    }
```

`seconds <= 0` returns `None`, so an exactly-zero denominator is handled — but `seconds = 1e-6`
yields a tokens-per-second in the millions and **is** serialised. Its own docstring
acknowledges the hazard in the adjacent burst case (`server.py:9587-9588`: "Initial
speculative/coalesced tokens have only one observation, so do not invent inter-token timing
inside that first burst"), but the log line at `:27146` enforces no equivalent floor.

**Where this receipt appears matters.** `vmlx_decode` is attached only on the **Responses**
stream, behind a negotiated extension header (`server.py:28279-28291`, `29444-29460`). The chat
stream has no `vmlx_decode`. So for the chat endpoint a harness sees no runtime-reported rate in
the response body at all — only this log line.

**One more unguarded division, outside the engine tree.** The DFlash2 lane is invoked from
`models/mllm.py:6508` (`stream_dflash2_generate`) and logs `generation_tps=%.2f` at
`models/mllm.py:6533` / `:6558` — a two-decimal format, the exact shape of a value like
`15286.61`. The computation is in the vendored package, **not** in `vmlx_engine/`:

`bundled-python/python/lib/python3.12/site-packages/dflash/model_mlx.py:681`
```python
        n, n / (time.perf_counter() - tic), mx.get_peak_memory() / 1e9, finish_reason,
```

with no `if elapsed > 0` guard and `tic` stamped just before the first sampled token
(`dflash/model_mlx.py:770`). A span of exactly `0.0` raises `ZeroDivisionError`; a span of
`6.5e-5` s with `n = 1` yields ~15,286.6. **That is the only computation found in this bundle
that reproduces a number of the reported magnitude from a plausible short generation**, and it
is consistent with the oMLX figure being the same class of defect rather than a coincidence.
The engine's own `generation_tps` property is guarded but only against exactly zero
(`mllm_batch_generator.py:7879` `if self.generation_time == 0: return 0`).

**Verdict for the harness: compute rates from `usage.completion_tokens` ÷ a decode window
measured from deltas. Do not consume any tok/s this runtime logs or attaches.** If a logged
rate ever disagrees with a measured one by more than a few percent on a long generation, that is
itself the finding.

### 6.4 Cached tokens are reported alongside, never subtracted

`scheduler.py:9572-9574` populates `prompt_tokens`, `completion_tokens` and `cached_tokens` from
the same output:

```python
                prompt_tokens=request.num_prompt_tokens,
                completion_tokens=request.num_output_tokens,
                cached_tokens=request.cached_tokens,
```

`num_prompt_tokens` is the **full** prompt length (`scheduler.py:6394`
`request.num_prompt_tokens = len(request.prompt_token_ids)`), while `cached_tokens` is the
reused subset (`request.py:138` `cached_tokens: int = 0  # Number of tokens retrieved from
cache`). **`prompt_tokens` therefore still counts cache hits**, and
`prompt_tokens_details.cached_tokens` is additional information — a positive signal that a cache
tier was used. When a cache is warm, `prompt_tokens` does not shrink; prefill *time* does. A cell
that compares prompt_tokens across a cold and warm run and concludes the cache did nothing has
read the wrong field; the `cache_detail` tier tag is where the evidence is.

### 6.5 Streaming versus non-streaming usage

- **Non-streaming:** usage is computed once, after generation, from the terminal
  `GenerationOutput` (`server.py:20827` `usage=get_usage(output),`). It is the authoritative
  end-of-request total. On `/v1/completions` it is accumulated across choices inline
  (`server.py:19434-19447`).
- **Streaming (chat):** usage is suppressed on every non-terminal chunk and delivered in exactly
  one choices-empty terminal chunk, only when `stream_options.include_usage` is true
  (`server.py:27122-27139`). Counters are accumulated per chunk during the stream
  (`server.py:25410-25424`) rather than read from one object. The same block is also emitted on
  a mid-stream error if any tokens were produced (`server.py:26096-26105`).
- **Streaming (Responses):** OpenAI-shaped usage on `response.completed`, plus the optional
  private `response.usage` event carrying `vmlx_decode` when `incremental_usage_extension` is
  negotiated (`server.py:29444-29460`).

**For a benchmark, non-streaming usage is the cleaner source; for a streaming cell, set
`stream_options.include_usage: true` or the response carries no token counts at all.**

---

## 7. Behaviour that changes performance without appearing in the start command

### 7.1 JIT is turned on automatically for JANG affine bundles

This is vMLX's cleanest analogue of mlx-optiq's `--stream-experts`, and — unusually — the CLI
help documents it. `--no-jit`'s help says: *"JANG affine bundles turn JIT on by themselves when
`--enable-jit` is absent, so 'not passing `--enable-jit`' is NOT a way to disable it — this flag
is."*

The logic is `cli.py:2085-2159`. The guard is that the user passed neither flag
(`cli.py:2085-2087`), and then (`cli.py:2147-2159`):

```python
                        if _is_affine and not _excluded_family and not _compile_unsafe:
                            args.enable_jit = True
                            logger.info(
                                "JANG affine model detected (format=%s, family=%s) — "
                                "defaulting --enable-jit ON for mx.compile decode speedup. "
                                "Disable with --no-jit or env "
                                "VMLX_DISABLE_JANG_AFFINE_JIT_DEFAULT=1.",
                                _fmt, _mc.family_name,
                            )
                            if os.environ.get(
                                "VMLX_DISABLE_JANG_AFFINE_JIT_DEFAULT", "0"
                            ) == "1":
                                args.enable_jit = False
```

All four conditions must hold:

| Condition | Definition | Source |
|---|---|---|
| `_is_affine` | `jang_config_is_affine(_jcfg)` — `format`, `weight_format` or `quantization.mode` matches an affine token | `cli.py:201-213` |
| not `_excluded_family` | not one of `deepseek_v4`, `minimax_m3`, `minimax_m3_vl`, `openpangu_v2` | `cli.py:2119-2125` |
| not `_compile_unsafe` | not multimodal/VLM, and not a hybrid SSM/Mamba cache | `cli.py:2132-2136` |
| user passed neither flag | `not args.enable_jit and not args.disable_jit` | `cli.py:2085-2087` |

The affine token set is exact-match, never substring, and the comment explains why
(`cli.py:190-198`):

```python
# Match exact tokens, never substrings: weight_format is also where mxfp4,
# mxfp8, mxtq and mlx live, and none of those are affine layouts.
_JANG_AFFINE_TOKENS = frozenset({"affine", "jang", "jjqf", "mxq", "jang_affine"})
```

The documented cost/benefit (`cli.py:2079-2083`):

```
# Default JIT (mx.compile) ON for JANG affine models per Eric directive
# 2026-06-27: 397B JANG_1L observed at ~10 tok/s without JIT vs expected
# 20+; 9B affine at 90 tok/s shows compile-eligible decode path is healthy
# at this family.
```

**`--no-jit` wins, and the source says why that ordering is load-bearing** (`cli.py:2788-2796`):

```python
# Configure JIT compilation. --no-jit is the final word: several policy
# blocks above can turn enable_jit ON by themselves (the JANG-affine
# default in particular), so an explicit user "off" has to be applied last
# or it is silently overridden — which is exactly what made the app's JIT
# toggle inert on affine bundles.
if getattr(args, 'disable_jit', False) and getattr(args, 'enable_jit', False):
    args.enable_jit = False
```

**This is directly load-bearing for this project, because JANG is the one format vMLX loads that
nothing else in the harness loads.** A JANG cell will have JIT on unless the harness says
otherwise — and JIT is not free, it costs a one-time `mx.compile` plus a warmup forward pass at
load (§7.6). **A harness that wants to compare a JANG bundle against a non-JANG one on equal
terms must pin `--no-jit`, and a harness that wants to measure JANG as shipped must pin
`--enable-jit`** — writing neither leaves the answer to the bundle's format tag, which is
exactly the "not appearing in the start command" hazard.

### 7.2 Loader-level TurboQuant is bundle-driven, and the flag *disables* it

> **Corrected 2026-09-24 (research `2026-09-24-kv-quant-surface.md` §7.1, §8).** The reading below
> was taken from the loader alone, and the loader is not where the decision starts. In 1.6.59 the
> CLI **pre-sets `VMLX_DISABLE_TQ_KV=1` on every path except the `VMLX_FORCE_TQ_AUTO=1`
> diagnostic** (`cli.py:60-91`; `cli.py:1510-1512` sets it again whenever `--kv-cache-quantization`
> is passed explicitly), and `_patch_turboquant_make_cache` returns immediately when that variable
> is truthy (`utils/jang_loader.py:1969-1975`). **The loader's auto path is therefore unreachable by
> default.** Loader-level TurboQuant requires all three of: the flag omitted, `VMLX_FORCE_TQ_AUTO=1`
> set, and no `VMLX_DISABLE_TQ_KV` / `VMLX_FULL_PRECISION_LIVE_KV` in the ambient environment. The
> "Consequence" paragraph at the end of this section — that the KV cache's precision can be decided
> by a key inside the model artifact — is **superseded**: that is not what this build does by
> default. The text below is kept rather than rewritten, because the loader-side mechanics it
> documents (the `VMLX_FORCE_TQ_AUTO` synthesis, the early returns, the log lines) are still
> accurate; only the conclusion drawn from them is not.

The `--kv-cache-quantization` help states that omitting the flag uses "production auto mode …
with no generic TurboQuant replacement or added stored codec", and that passing it explicitly
"disables loader-level TurboQuant". Both halves are true and the mechanism is subtle.

Passing the flag explicitly sets an environment variable before load (`cli.py:1511-1517`, and the
same pattern at `cli.py:578`, `604`, `733`, `1404`, `1420`, `1913`, `3001`):

```python
os.environ["VMLX_DISABLE_TQ_KV"] = "1"
os.environ.pop("VMLX_FORCE_TQ_AUTO", None)
```

with the log `"--kv-cache-quantization=%s explicit; VMLX_DISABLE_TQ_KV=1 set so JANG-calibrated
TurboQuant KV is skipped at load time."`

The auto path is `_patch_turboquant_make_cache` (`utils/jang_loader.py:1956`), and its condition
is stated in its own docstring: *"only activates when `jang_config.json` has
`turboquant.enabled=true`."* The decision (`utils/jang_loader.py:2055-2083`):

```python
_tq_cfg = jang_cfg.get("turboquant")
_tq_auto_generated = False
if not _tq_cfg:
    # Auto mode is selected by the CLI/panel when the user has not
    # explicitly disabled TQ. ...
    if _os_tq.environ.get("VMLX_FORCE_TQ_AUTO") == "1":
        _tq_auto_generated = True
        _tq_cfg = {
            "enabled": True,
            "default_key_bits": 3,
            "default_value_bits": 3,
            "critical_key_bits": 4,
            "critical_value_bits": 4,
            "critical_layers": [0, 1, 2, -3, -2, -1],
            "seed": 42,
        }
        logger.info("  TurboQuant auto-enabled via VMLX_FORCE_TQ_AUTO=1")
    else:
        logger.info(
            "  TurboQuant: not enabled (jang_config has no `turboquant` block; "
            "default is off — set turboquant.enabled=true in jang_config.json "
            "to opt in, or VMLX_FORCE_TQ_AUTO=1 for legacy auto)"
        )
        return
```

**The precise condition (superseded 2026-09-24 — it is the loader's condition, and the CLI's
`VMLX_DISABLE_TQ_KV=1` is evaluated before it; see the box at the top of §7.2): loader-level
TurboQuant KV is auto-enabled only when the bundle's own `jang_config.json` carries a `turboquant`
block whose `enabled` is not `False`.** With no block, TQ stays off. There are further early
returns for MLA layouts (`jang_loader.py:1977`), MiniMax-M3 (`:2046-2053`), and mixed-SWA without
opt-in or native rotating slots (`:2015-2020`, `:2137-2150`). `VMLX_DISABLE_TQ_KV` is also honoured
by `utils/tokenizer.py:280`, `disk_cache.py:312` and `block_disk_store.py:489`.

**Consequence (superseded 2026-09-24 — see the box at the top of §7.2): the KV cache's precision
can be decided by a key inside the model artifact, not by the start command.** Two JANG bundles
with identical bit widths can have different KV cache behaviour because one ships a `turboquant`
block. A harness recording only the flags records neither. The tell at runtime is the loader's own
INFO line, `TurboQuant: not enabled` or `TurboQuant auto-enabled`. *What survives of this
paragraph:* the log line is still the only tell, and it is still worth reading — but on 1.6.59 the
line it prints for a default command is `TurboQuant: not enabled`, because `VMLX_DISABLE_TQ_KV=1`
is already set.

#### 7.2.1 The stored codec — `q4`/`q8` is storage-only, and inert without the prefix cache

**Added 2026-09-24 (research `2026-09-24-kv-quant-surface.md` §7.1, §7.2, §11).** The flag's own
codec is MLX affine `QuantizedKVCache`, built with raw `mx.quantize` (`scheduler.py:2606-2631`,
and `_wrap_make_cache_quantized` at `scheduler.py:2443-…` / `mllm_scheduler.py:1783-…`). Affine,
not FP8. And it is **not a live cache** — the module states the boundary itself:

> "Quantization is applied at the storage/retrieval boundary of the prefix cache, **NOT at
> model.make_cache() level**. … During generation: full-precision KVCache (no quality loss). In
> prefix cache: quantized QuantizedKVCache (memory savings)."
> — `scheduler.py:2444-2458`

**It only fires when the prefix cache is on.** Both schedulers gate on it and log the no-op when
it is off (`scheduler.py:1393-1404`; the same shape at `mllm_scheduler.py:1165-1177`):

```python
scheduler.py:1393       elif self.config.kv_cache_quantization != "none":
scheduler.py:1394           if self.config.enable_prefix_cache:
scheduler.py:1395               bits = 4 if self.config.kv_cache_quantization == "q4" else 8
scheduler.py:1396               self._wrap_make_cache_quantized(bits, self.config.kv_cache_group_size)
                                logger.info("KV cache quantization enabled: …")
                            else:
                                logger.warning(f"KV cache quantization '{…}' requested but prefix "
                                               "cache is disabled — quantization has no effect "
                                               "without prefix cache")
```

`--disable-prefix-cache` makes `enable_prefix_cache = args.enable_prefix_cache and not
args.disable_prefix_cache` false (`cli.py:2639`), and that value is handed to the scheduler config
at `cli.py:2667`. The harness passes `--continuous-batching` (`runtimes.py:1191`), so the branch is
taken — **but `runtimes.Vmlx.start_command` also passes `--disable-prefix-cache` unless the run was
pinned `cache_state="on"` (`ohyesmlx/runtimes.py:1161-1163`).** Under a default harness start
command, `--kv-cache-quantization q4|q8` on vMLX is therefore **inert**: the runtime logs its own
warning and serves the model's native cache. A future `--kv-quant` cell on this runtime must either
also enable the prefix cache — which would make the run vary two things — or record the value as
`N/A`.

### 7.3 Memory-pressure behaviour — and the threshold that is *not* the optiq one

The direct analogue of mlx-optiq's `model_disk_bytes > 0.70 * total_RAM` heuristic **does not
exist here**, and that is worth stating positively because the absence was checked:

| Variable | Default | On by default? | Effect |
|---|---|---|---|
| `VMLX_MEMORY_PRESSURE_GUARD` | `"0"` | **No** | When `"0"`, `check_memory_pressure` returns immediately (`server.py:6916`). The comment at `server.py:6909-6914` records it as "DEFAULT OFF (Eric directive 2026-06-27)" |
| `VMLX_MEMORY_PRESSURE_REJECT_PCT` | `97` | n/a | Percent of `psutil.virtual_memory().percent` at which new requests get a 503 (`server.py:6923-6927`) |
| `VMLX_METAL_WS_GUARD` | `"1"` | **Yes** | Master enable for the Metal working-set guard (`memory_limits.py:937`) |
| `VMLX_METAL_WS_REJECT_PCT` | `98.0` function default | Yes | Metal occupancy percent at which admission is refused. **Caller-dependent**: `server.py:7026` passes `99.0`, `scheduler.py:8467` uses the 98.0 default, the MLLM path defaults to `"98"` |
| `VMLX_METAL_WS_MAX_GB` | `None` | Override only | Raises/lowers the working-set ceiling (`memory_limits.py:879-882`) |
| `VMLX_METAL_WIRED_HEADROOM_GB` | computed | Override only | Overrides `max(16 GiB, 30% of total RAM)` (computed `jang_loader.py:1544`, read `:1560-1580`) |

The **only** disk-bytes-versus-RAM ratio in the tree is `0.50`, not `0.70`, and it is in the JANG
v1 shard-repack helper rather than the runtime expert-streaming path
(`utils/jang_loader.py:5766-5775`):

```python
model_disk_bytes = sum(sf.stat().st_size for sf in shard_files if sf.exists())
ram_threshold = int(total_ram * 0.50)
use_streaming = model_disk_bytes > ram_threshold
```

It selects between an in-memory repack and a temp-shard streaming repack. **This is a
qualitatively different thing from optiq's heuristic**: it changes *how weights are materialised
during a one-time JANG→MLX repack*, not how they are streamed during decode. It is not a 5x-speed
trap. I record it because it is the nearest analogue and a future reader will look for one, and I
flag that I could not trace which caller invokes the repack helper, so I cannot assert how often
it runs (§10).

**Smelt and Flash MoE have no RAM-ratio auto-enable.** Both are `action="store_true"`
(`cli.py:3949-3954`) and activate only when present (`cli.py:2523`, `server.py:9085`);
`flash_moe_config.py:29` `enabled: bool = False` with the comment "Default False (opt-in)". A
grep for a ratio comparison that turns either on finds none. **The expert-streaming heuristic that
cost optiq 5x has no vMLX equivalent** — on this runtime, expert streaming happens only if the
harness asks for it.

One automatic memory behaviour does exist and is worth recording: the MLX allocator cache is
bounded proportionally to the **model's resident bytes**, not to total RAM
(`mlx_memory.py:79-104`): `_CACHE_LIMIT_FRACTION = 0.05`, clamped to `[512 MB, 4 GB]`. It is
automatic, has no flag, and scales with the model rather than the machine.

### 7.4 MTP adapts its own depth, and the safety valve is on by default

Two independent controllers run without any flag being passed.

**The AR-safety valve** measures wall-clock cost per verify cycle and demotes when MTP loses to
plain decoding. It is on by default (`native_mtp_ar_safety.py:113-114`):

```python
def ar_safety_enabled() -> bool:
    return env_flag(True, "VMLINUX_NATIVE_MTP_AR_SAFETY", "VMLX_NATIVE_MTP_AR_SAFETY")
```

Its docstring states its role (`native_mtp_ar_safety.py:6-8`): *"The depth-adapt gates are what a
fixed policy disables; this valve is not a depth policy, it is the guarantee that a request never
keeps speculating while losing to plain AR."*

The trip condition (`native_mtp_ar_safety.py:162-193`) requires **both** the window mean and the
per-cycle median to exceed `ar_baseline × margin`:

```python
    scale = max(1.0, cur_cycle_ms / anchor_cycle_ms)
    ar_baseline = ar_step_ms * scale
    threshold = ar_baseline * margin
    if mtp_ms_per_tok <= threshold:
        return None
    if per_cycle_ms_per_tok:
        if median(per_cycle_ms_per_tok) <= threshold:      # <-- median guard
            return None
```

On a trip the depth drops by one, and at depth 1 it falls back to plain autoregressive decode
(`mllm_batch_generator.py:6158-6161`):

```python
state.depth = max(1, current_depth - 1)
state.ar_fallback_pending = current_depth <= 1
```

Constants (`native_mtp_ar_safety.py:66-78`): `DEFAULT_WARMUP_CYCLES = 8`,
`DEFAULT_UNPRIMED_WARMUP_CYCLES = 16`, `DEFAULT_WINDOW_CYCLES = 8`, `DEFAULT_MARGIN = 1.0`,
`DEFAULT_SEED_MARGIN = 1.10`, `DEFAULT_PROBE_WARMUP_CYCLES = 4`,
`PROBE_EARLY_ABORT_RATIO = 1.5`.

**The adaptive depth policy** is also on by default (`mllm_batch_generator.py:6397-6400`,
`_native_mtp_env_flag(True, …)`) with the server forcing the env default `"1"`
(`server.py:10364-10365`). Its rolling value controller (`mllm_batch_generator.py:6030-6056`) uses
cooldown 8 cycles, probe interval 48, hysteresis 0.05, raise-min-acceptance 0.88, initial probe
48.

**The default depth is 3** (`native_mtp.py:28-29` `_NATIVE_MTP_DEFAULT_MAX_DEPTH = 3`, hard
ceiling 8), matching the CLI's `--native-mtp-depth` default.

There is a **second, legacy runtime-cost gate** with a different margin — 1.25 rather than 1.0 —
read from the *same* environment variable (`mllm_batch_generator.py:7248-7260`):

```python
margin = _native_mtp_env_float(1.25, "VMLINUX_NATIVE_MTP_RUNTIME_COST_MARGIN",
                               "VMLX_NATIVE_MTP_RUNTIME_COST_MARGIN")
...
if mtp_ms_per_tok > ar_ms * margin:
    state.depth = max(1, current - 1)
    state.ar_fallback_pending = current <= 1
```

**`VMLX_NATIVE_MTP_RUNTIME_COST_MARGIN` is therefore read in three places with two different
defaults.** Setting it to A/B the cost gate moves both gates at once, and the one that fires
first wins. That is a trap for an experiment, not for production.

**Consequences for a cell:** MTP depth can change *within* a single request, so a per-request
MT/s figure is an average over a policy that was adapting underneath it. A cell that disables
adaptation to get a stable number must set `VMLX_NATIVE_MTP_DEPTH_PROBE` /
`VMLX_NATIVE_MTP_AR_SAFETY=0` — and must record that it did, because setting `AR_SAFETY=0` means
"fixed never leaves its depth, even when slower than plain decoding" (the CLI's own words at
`cli.py:4319-4331`), i.e. the resulting speed may be a speed the runtime would have rejected.

#### 7.4.1 What the harness pins now (`--mtp-depth`, header pin 03-06)

The harness drives MTP through one header pin, and a depth cell is three things rather than one:
`--native-mtp-depth N --native-mtp-depth-policy fixed`, the two environment variables that keep
that policy fixed (`env VMLX_NATIVE_MTP_AR_SAFETY=0 VMLX_NATIVE_MTP_AR_REENTRY=0`, carried as a
prefix in the recorded command so the provenance says the depth was pinned rather than leaving it
to the ambient environment), and the log half of the claim (`Vmlx.mtp_depth_missing`, below). The
cell records which value it ran.

| pin value | command | why that is the whole of the pin |
|---|---|---|
| absent | `--disable-native-mtp` | The command of today. Left alone, MTP turns itself on for a bundle carrying MTP heads, so an absent pin that passed nothing would be an MTP cell nobody declared |
| `off` | `--disable-native-mtp` | The same command: the flag is this runtime's own explicit off (`cli.py:1662-1667`), setting `VMLINUX_NATIVE_MTP=0` and clearing any depth an inherited environment left behind |
| `1`, `2`, `3` | `env VMLX_NATIVE_MTP_AR_SAFETY=0 VMLX_NATIVE_MTP_AR_REENTRY=0 vmlx serve … --native-mtp-depth N --native-mtp-depth-policy fixed` | `fixed` is not a second pin, and it is not the whole of a fixed depth on this release. The default policy is `adaptive` ("may also lower the depth on measured acceptance and tries depth 1 once against the configured depth's measured cost, keeping the measured winner", `cli.py:4324-4331`), so an adaptive cell is not a cell at depth N; the two variables above are what make `fixed` mean fixed, because the policy alone leaves two controllers running (next) |

**`fixed` disables the depth economics probe, and only that.** The CLI writes
`VMLINUX_NATIVE_MTP_ADAPTIVE_DEPTH=0` when the policy is `fixed` (`cli.py:1679-1681`), which makes
`_native_mtp_adaptive_policy()` False (`mllm_batch_generator.py:6397-6400`) and therefore makes the
probe's own default False (`_native_mtp_depth_probe_enabled`, `:6403-6418`). That function's own
docstring names what is still live beside it:

> With the probe off and `VMLX_NATIVE_MTP_AR_SAFETY=0` the depth is pinned; the per-cycle
> first-draft confidence gate (`VMLX_NATIVE_MTP_DRAFT_MARGIN`) is a separate, older mechanism and
> still shortens low-confidence drafts.

Two controllers are outside the policy's reach and both move depth:

* **The AR-safety valve** is on by default (`native_mtp_ar_safety.py:113-114`, `env_flag(True, …)`)
  and demotes one rung per trip while the depth is above 1 (`mllm_batch_generator.py:6988-7002`),
  falling back to plain autoregressive decode at depth 1 (`:7029-7047`) — which ends the request
  in the handoff the log calls `finish=fallback_to_ar` (`:18387-18402`).
* **The sticky start rung** (`:17275-17286`) starts a request at D1 when the previous request on
  the engine ended in AR or D1, gated by `_native_mtp_reentry_enabled()` (`:6345-6348`).

Both are `env_flag`-shaped reads for which `0` is off (`native_mtp_ar_safety.py:89-93`,
`mllm_batch_generator.py:5913-5925`), nothing in the engine writes either spelling into
`os.environ` ahead of them, and the process the harness spawns is the one that runs the engine
(`~/.local/bin/vmlx` execs the bundle's console script, which runs `vmlx_engine.cli.main()` in
place and reaches `uvicorn.run` at `cli.py:2943`) — so the `env` prefix reaches both readers. The
CLI's own help states what the first variable buys: *"VMLX_NATIVE_MTP_AR_SAFETY=0 disables the
valve (fixed then never leaves its depth, even when slower than plain decoding)"*
(`cli.py:4325-4329`).

**Approved 2026-09-25.** This reverses the earlier reading, which left `AR_SAFETY` at its default
and called the valve's demotion a property of the runtime as shipped. The study is *fixed depth
N*, and under the policy alone the two runs of 2026-09-25 put 94 requests through a depth-3
command: 30 of them ended in `finish=fallback_to_ar`, 87 began at a `start rung D1`, and only five
of their 212 `accept_by_depth` rows show a non-zero `d3` denominator. A column labelled depth 3
whose requests mostly ran at another depth is not a depth-3 column. The cost of pinning is real
and is stated where §7.4 states it: the resulting speed may be a speed the runtime would itself
have rejected — a fixed-depth cell, which is what the header declares, and the declared state is
what a reader gets. Both variables are in the recorded start command, so no part of it is
ambient.

**The log half: three conditions, and the window is the whole log.** `Vmlx.mtp_depth_missing`
fails a depth cell when the visit's log shows either mechanism the variables disable —
`finish=fallback_to_ar`, or a `start rung D<k>` line with `k` below the pin — or when no
`accept_by_depth` line has a non-zero denominator at `d<N>`. The last is the positive half: it is
the head actually drafting the Nth token in some request of the visit, and it is the only
condition depth 1 is judged on (there is no rung below it, and its fallback is below the pin
itself). The measured runs of 2026-09-25 carried the policy but not the variables, and they are
the reason each condition exists: of the 49 and 45 depth-3 requests in
`results/logs/vmlx-20260925T062816-11233.log` and `-20260925T063452-16321.log`, 47 and 40
inherited a `start rung D1`, 15 and 15 ended in `finish=fallback_to_ar`, and only 0 and 5
`accept_by_depth` rows show a non-zero `d3` denominator.

The window is the whole file (`runtimes._read_log_all`), not the head or the tail: a request's row
is written once per request for as long as the server runs, so a fixed window at one end is a
window on part of the visit, and these logs are only ~290-300 KB. The check is asked once the
visit's measured requests have answered (`measure._visit`), because a log read any earlier covers
fewer requests than the cell publishes.

**Residual caveat, and this one stays.** `VMLX_NATIVE_MTP_DRAFT_MARGIN` is a third mechanism and
this pin does not touch it: the confidence gate reads the head's top-1-minus-top-2 logit gap once,
after the first draft, and stops extending the chain when the gap is below the threshold
(`mllm_batch_generator.py:4743-4774` for the read, `:16919-16965` for the stop, counted as
`margin_truncated` in the finish line). It is off by default on the bundles this harness measures —
the threshold is 0.0 unless the artifact is a `qwen4_exp` under fixed D3, where it is 1.0
(`:4709-4740`), and the finish lines of the 2026-09-25 runs carry `margin_truncated=0`. But an
environment that sets it, or a Qwen4 bundle under this same pin, will end a request's draft chain
early on a low-confidence position. So **"depth 3" here means the configured depth is 3 and no
controller demoted it; it does not mean every verify cycle drafted three tokens.**

**The flag is accepted on a bundle that cannot use it, so the artifact decides first.** The
harness refuses a depth up front (`runtimes.vmlx_mtp_refusal`) unless the artifact on disk shows
MTP the runtime will wire: a family in `native_mtp.py:64-79`, no `drop_mtp` / `mtp_mode` /
`runtime.bundle_has_mtp` saying the bundle dropped its heads (`:883-925`), a config that
declares at least one MTP layer (`:537-546`), and `mtp.*` tensors in the safetensors index
(`:606-611`). Without that check a depth cell on such a bundle is indistinguishable from a
working one: for a bundle that declares no MTP at all the startup banner is skipped
(`cli.py:2441`) and the INFO line that would explain an inactive draft head is conditional on
the bundle having declared something (`native_mtp.py:1307-1316`).

**That silence is measured, and the source says so** (`native_mtp.py:1296-1303`):

> A bundle that DECLARES MTP but is not runtime-supported used to deactivate in total silence,
> so the model ran plain autoregressive with nothing in the log to say why. MEASURED: Nemotron
> 3.5 Lightning (JANG_2L/4M/6M, 34 mtp.layers.0.* tensors, num_nextn_predict_layers=1) and
> Inkling both hit this — the only surfaces telling the truth were /health.mtp and the CLI
> startup banner.

**Both halves of the declaration are required by this check, and each has its own failure in
that source:** a config that expects MTP over an index with no `mtp.*` tensors reads
`metadata_inconsistent` (`:983-986`), and an index that carries them under a config disabling
MTP reads the same (`:987-988`). The accepted case is a bundle on this host:
`models--JANGQ-AI--Qwen3.5-4B-JANG_4S` declares one MTP layer in
`text_config.mtp_num_hidden_layers`, indexes 31 `mtp.layers.0.*` tensors under family
`qwen3_5`, and its start log carries `Qwen3.5/3.6 MTP model adapter applied`
(`results/logs/vmlx-20260924T032906-11424.log:38`) — a depth pin is honest there.

The `on`-side of the same question for the *streaming* pin is the log line quoted in §7.8.

#### 7.4.2 The control surface, the depth ladder, and where the heads have to live

**Added 2026-09-24.** §7.4 says how depth *adapts* and §7.4.1 says what the harness pins. This is the
capability reference: how the feature is switched on, how deep it can go, what makes the runtime
believe a bundle has heads — and one artifact class this runtime cannot see.

**Control surface — flags and environment, never the request.** The flags are in §2.2.4:
`--native-mtp-depth` (default `3`), `--native-mtp-depth-policy adaptive|fixed`,
`--native-mtp-sampling-policy`, `--disable-native-mtp`. Everything else is environment (§3.3):
`VMLX_NATIVE_MTP` (process enable/disable), `VMLX_NATIVE_MTP_MAX_DEPTH` (ceiling), plus the
`AR_SAFETY` / `ADAPTIVE_DEPTH` / cost-margin variables in Appendix A. **No per-request field exists**
— the chat request model (`api/models.py:231-336`) carries none, so a client cannot influence MTP.

**Depth range.** Product default **3**, hard ceiling **8**: `_NATIVE_MTP_DEFAULT_MAX_DEPTH = 3` and
`_NATIVE_MTP_DEPTH_HARD_CEILING = 8` (`native_mtp.py:28-29`), with `native_mtp_max_depth()` clamping
the env ceiling to `[1, 8]` (`:32-44`). The effective depth is resolved in this order
(`native_mtp_effective_depth`, `:800-868`): explicit `VMLX_NATIVE_MTP_DEPTH` → a *measured*
`vmlx_mtp_tuning.json` depth → `jang_config.mtp.recommended_num_drafts` (a v3 stamp) → family default
— **3**, and **1** for `hy_v3` (the `:793-796` docstring records the Hy3 sweep: d1 +10% over
baseline while d2/d3 collapse acceptance). The file is read unless
`VMLX_NATIVE_MTP_USE_TUNING` disables it (`:830`), and its *depth* attestation is strict only above
depth 1 (`:340-358`: depth 1 stands unless the block is `blocked` or `output_equivalent: false`;
deeper needs `validated: true`).

**Where the tuning file is a precondition rather than a hint.** Two gates make it load-bearing, and
both are separate from the depth ladder:

1. `jang_config.runtime.native_mtp_blocked = "<measured reason>"` blocks the runtime path entirely
   unless `VMLX_NATIVE_MTP_FORCE=1` (`:747-754`) — a bundle that measured MTP as a net slowdown
   declares it in its own metadata rather than the engine hardcoding profile names.
2. **Hy3 only**: `vmlx_mtp_tuning.json`'s `native_mtp.output_equivalent` must be exactly `true`. A
   missing or failed attestation reads `runtime_validation_blocked` (`:756-776`), because the
   two-token affine verifier is not bit-identical to one-token AR and has to prove token identity on
   the real quantized weights.

One family also defaults to AR even when everything else passes: `glm5_next` serves autoregressive
unless MTP is explicitly requested (`_runtime_default_enabled_for_family`, `:708-712`; status reason
`:1099-1105`) — the bundle inspector reports it as `runtime_default_mode: "off"` (`:1152-1154`).
Osaurus refuses MTP without usable tuning for *every* family
(`docs/runtimes/osaurus.md` §7.8): same direction, wider scope.

**Head detection needs a declaration *and* tensors.** `inspect_native_mtp_bundle`
(`native_mtp.py:871-1171`) requires all of:

1. **A declaration** — `num_nextn_predict_layers` or `mtp_num_hidden_layers` in `config.json`
   (`:537-548`), or a `jang_config` counter (`runtime.mtp_layers`, `mtp.num_layers`,
   `mtp.num_hidden_layers`, `:563-580`);
2. **Not dropped** — `jang_config.drop_mtp`, `mtp.enabled/kept = false`,
   `mtp.mtp_mode ∈ {none, absent, disabled, off}`, or `runtime.bundle_has_mtp = false` (`:883-925`);
   a bundle name matching `(?:^|[-_.])mtp(?:$|[-_.])` counts as a declaration too (`:222-233`);
3. **Tensor evidence** — `mtp.*` keys matching `(^|\.)mtp(\.|$)`, read from `_bundle_weight_keys`
   (`:606-611`, `:126-212`), which reads `model.safetensors.index.json` when present and then the
   **top-level** `*.safetensors` headers for shards the index does not list
   (`Path(bundle_path).glob("*.safetensors")`, `:158-162`, `:197-201`).

Missing any of the three becomes an issue and the status ladder (`:1070-1134`) reports
`metadata_inconsistent` / `dropped` / `runtime_disabled` / `runtime_validation_blocked` /
`weights_present_runtime_unwired` / `native_runtime_ready`. Even a clean bundle needs the runtime on:
`VMLX_NATIVE_MTP` enabled and the family in `_RUNTIME_SUPPORTED_FAMILIES` (`:64-79`: `qwen3_5`,
`qwen3_5_moe`, `qwen4_exp`, `hy_v3`, `glm5_next`, `dots3_note`; EAGLE-3 drafters are a separate
branch, `minimax_m3` / `minimax_m3_vl` at `:80-83`).

**A sidecar head this runtime cannot read — `optiq/mtp.safetensors`.** The glob in
`_bundle_weight_keys` is top-level only, and the shipped `vmlx_engine` never reads
`mlx_lm_extra_tensors` (grep: zero hits) — the same key OptiQ exports use to point at their head.
**Live example on this host**, snapshot
`~/.cache/huggingface/hub/models--mlx-community--Qwen3.5-4B-OptiQ-4bit/snapshots/6cb5bdfd…`:

| What the artifact says | Value |
|---|---|
| `config.json` MTP declaration | `mtp_num_hidden_layers: 1` (and `text_config.mtp_num_hidden_layers: 1`) |
| `config.json` head pointer | `mlx_lm_extra_tensors.mtp_file = "optiq/mtp.safetensors"` |
| The head on disk | `optiq/mtp.safetensors` — 29 tensors (`mtp_tensor_count` in `config.json`) |
| `model.safetensors.index.json` | **1,221 keys, zero `mtp.*`** |

So the declaration is there and the tensors are there, but not where this runtime looks: it reports
`config expects MTP next-token prediction layers, but the bundle index has no mtp.* tensors`
(`native_mtp.py:983-986`) and serves AR. **A depth pin on such an artifact is refused by the harness's
artifact gate (§7.4.1) for the right reason** — the runtime cannot wire a draft head it cannot see.
The contrast is oMLX, which can merge that same sidecar into the index through an explicit admin
import (`docs/runtimes/omlx.md` §8.8). The finding is not "OptiQ is broken"; it is that **MTP's
presence is a property of where the tensors sit, and the two runtimes read different places.**

### 7.5 Caches — what survives a restart, and 22 GB already on disk

| Cache | Default | On-disk path | Keyed by model? | Survives restart? |
|---|---|---|---|---|
| Prefix cache (in-RAM) | **ON** (`cli.py:3659-3661`) | none | no | **No** |
| Memory-aware cache | **ON** (`scheduler.py:613`) | none | no | No |
| Paged cache (in-RAM blocks) | **OFF** for every family (`cli.py:556-557`) | none | no | No |
| Prompt disk cache | **OFF** (`--enable-disk-cache` is opt-in) | `~/.cache/vmlx-engine/prompt-cache/<slug>_<hash>` | yes | **Yes** |
| Block disk cache (L2) | **ON** when continuous-batching + prefix cache | `~/.cache/vmlx-engine/block-cache/<model_hash>` | yes | **Yes** |
| SSM companion state | in-RAM retention OFF (`0`); typed state SSD-only | `…/block-cache/<model_hash>/ssm_companion` | yes | **Yes** |

Model keying for the disk caches (`scheduler.py:1777-1808`):

```python
scope_key = (f"{self.config.model_path}:quant={quant_tag}:layers={n_layers}"
             f":tq_native={tq_native_tag}"
             f":prefix_cache_schema={PAGED_CACHE_SCHEMA_VERSION}"
             f":{runtime_cache_fingerprint()}")
model_hash = hashlib.sha256(scope_key.encode()).hexdigest()[:12]
cache_dir = os.path.join(base_dir, f"{model_slug}_{model_hash}")
```

so the namespace depends on the model path **and** the quantization tag **and** the layer count
**and** a runtime fingerprint — meaning a runtime upgrade can orphan a whole namespace.

**Two operational findings on this machine.**

1. **There is 22 GB of stale block cache.** `du -sh ~/.cache/vmlx-engine/` → `22G`, across 16
   model-hash namespaces dated May–June 2026. This project's free disk is 36 GiB (per
   `AGENTS.md`), so **the existing vMLX cache is the single largest reclaimable object on the
   volume** and it is not the harness's own data. That is a decision for the coordinator, not
   this document — but a `--disable-block-disk-cache` cell removes both the disk pressure and the
   cold-cache ambiguity in one flag, and `cache_salt` per request (§4.4) removes the latter
   without touching disk.
2. **The block disk cache does a synchronous startup trim**, which costs real time before
   readiness. `block_disk_store.py:680-706`:

   ```python
   # A user can lower the disk-cap slider between sessions. Enforce that
   # new ceiling before serving reads or accepting writes; waiting for the
   # first background write left an oversized cache indefinitely after
   # restart. This synchronous startup trim touches only files and SQLite.
   global_startup_trim = self.global_budget.enforce(force=True)
   ```

   `enforce(force=True)` bypasses the interval short-circuit and walks every managed namespace,
   opening every block index (`global_disk_cache_budget.py:1772-1794`, `:1796-1800`). The cost is
   stated in the source (`global_disk_cache_budget.py:286-289`): *"on a root with hundreds of
   namespaces that is seconds."* **This lands inside cold-load time and scales with whatever is
   already on disk** — so a first run and a run after the cache has grown do not have the same
   cold-load time. Cold load is its own metric and must not be folded into the first request
   (`AGENTS.md`), and this is a concrete reason why.

The prompt disk cache deliberately does **not** preload (`scheduler.py:1769-1772`):

```python
# Disk cache (L2) for persistent prompt cache across restarts.
# Disk cache entries are loaded lazily on cache miss — no L2-to-L1
# warmup at startup. This avoids loading GBs of cache into RAM but
# means first request pays full prefill cost.
```

so with `--enable-disk-cache`, the **first request after a restart pays full prefill** while
later requests may not. A three-request cell with `--enable-disk-cache` measures three different
things.

### 7.6 Warmup at load time — outside the first request, inside cold load

Several warmups run before readiness, so they land in cold-load time rather than in TTFT. That is
the correct place for them, and it is worth stating so that nobody attributes them to a cell.

- **JIT compile plus a 1-token dummy forward pass** (`server.py:6729-6762`):

  ```python
  if replaced:
      logger.info("JIT: mx.compile applied successfully — running warmup pass")
      # Warmup: 1-token forward pass to page in model weights and compile
      # Metal shaders. Without this, the first real request simultaneously
      # pages ~30GB+ of mmap weights AND allocates cache/activations, ...
      warmup_input = mx.array([[0]])  # Single dummy token
      ...
      mx.synchronize()  # Force Metal to finish
  ```

  This only runs when JIT is on — which, per §7.1, is automatic for JANG affine bundles. **A JANG
  cell therefore has a longer cold load than the same weights would with `--no-jit`**, and that
  difference belongs to cold-load time, not to the first request.
- **MLX stream pre-warm** on the worker thread before the model load (`engine/batched.py:1452-1472`).
- **TQ storage decoder warmup**, explicitly before readiness (`scheduler.py:4006-4011`):
  *"This runs during engine start, before readiness is advertised, so the first paged/L2 hit does
  not become the accidental synchronization point"* — timed and logged (`scheduler.py:4043-4055`).
- **DSV4** runs a full-model 1-token warmup after hydration (`loaders/load_jangtq_dsv4.py:1418-1421`).

### 7.7 What did *not* turn up

Recorded explicitly, because "I looked and there is no ratio heuristic" is a different and
stronger statement than "no flag for it":

- No RAM-ratio auto-enable of smelt or Flash MoE (§7.3).
- No `model_disk_bytes > 0.70 * total_RAM` threshold. The only such ratio is `0.50`, in a
  one-time repack path (§7.3).
- No automatic model unloading on idle **in the CLI**. There is no `--idle-timeout` flag; the
  `--timeout` flag is per-request, not per-server. The sleep/wake surface is the explicit
  `/admin/soft-sleep`, `/admin/deep-sleep`, `/admin/wake` endpoints (§4.1).
- No sampler injection from `generation_config.json` beyond the documented
  `--default-top-k` / `--default-min-p` / `--default-repetition-penalty` fallback chain (§2.2.5),
  which is a flag with a documented bundle fallback rather than a hidden override.

### 7.8 `--flash-moe` is accepted on models it cannot stream (`stream_experts`, header pin 03-03)

`--flash-moe` "Enable[s] Flash MoE: stream expert weights from SSD on-demand"
(`cli.py:3963-3970`), `default=False`, and `FlashMoEConfig.enabled: bool = False` — "Default
False (opt-in)" (`flash_moe_config.py:29`). Passing it is therefore the whole of what a cell can
say through its start command, and it is **not evidence that anything streamed.** Every failure
below is logged and then the load simply proceeds resident:

| Outcome | Line | Source |
|---|---|---|
| The model has no MoE layers | `Flash MoE: model has no MoE layers, skipping` | `server.py:8981-8982` |
| The bundle is JANGTQ | `vmlx#81: --flash-moe is not supported on JANGTQ (weight_format=mxtq) …` | `server.py:8964-8973` |
| The patch matched nothing | `Flash MoE: no MoE layers found to patch` | `server.py:9003-9005` |
| The setup raised | `Flash MoE setup failed: %s` | `server.py:9006-9008` |
| smelt or distributed is also on | `Flash MoE: refusing to patch — …` | `server.py:8929-8938` |

The line that says it **is** on is printed only when layers were patched
(`server.py:8996-9002`):

```
Flash MoE enabled: <n> layers patched, <g> GB freed, slot bank=<n>, io_workers=<n>
```

It is written before the runtime can answer: `--flash-moe` is applied at the readiness barrier,
ahead of the yield that lets uvicorn start serving (`server.py:6176-6177`, `:6199`), so it is
already in the log when `GET /v1/models` answers. That is what makes an `on` cell checkable at
all — the harness reads the head of this start's own log and **FAILs the cell with that log
quoted** when the line is not there, rather than publishing a number under `stream_experts='on'`
for a cell that ran resident.

**Not pinned by this flag, and worth knowing:** Flash MoE is mutually exclusive with `--smelt`
and `--distributed` (`cli.py:2565-2573`), and while it is active the engine skips `mx.compile`
(`server.py:6565-6568`) — so an `on` cell is not byte-comparable with an `off` one in the JIT
dimension either. The harness passes `--no-jit` unconditionally, so both states are un-JITed and
the flag is the only thing that moves.

---

## 8. Quantization formats

vMLX's distinguishing feature is that it is **the only runtime in this project's set that loads
JANG**, and the loaders are in-tree rather than upstream. The dispatch gate is
`load_model_with_fallback` (`utils/tokenizer.py:1139`), reached from `models/llm.py:100` (text)
and `models/mllm.py` (VLM), which branches on `is_jang_model()` and otherwise falls through to
stock `mlx_lm.load`.

### 8.1 The format vocabulary

`utils/jang_loader.py:60-69` is the authoritative list:

```python
JANG_CONFIG_FILENAMES = [
    "jang_config.json",
    "jjqf_config.json",
    "jang_cfg.json",
    "mxq_config.json",
]
JANG_FORMAT_VALUES = ["jang", "jang-v2", "jjqf", "mxq"]
JANG_WEIGHT_FORMAT_VALUES = {"affine", "jang_affine", "mxtq", "mxfp4", "mxfp8"}
_MLX_WEIGHT_QUANT_BITS = {2, 3, 4, 5, 6, 8}
_MLX_WEIGHT_QUANT_GROUP_SIZES = {32, 64, 128}
```

duplicated as the runtime limits in `utils/quant_shape_inference.py:133-134`.

### 8.2 What it loads

| Format | Evidence | Notes |
|---|---|---|
| **JANG / JANG-v2 / JJQF / MXQ** | `utils/jang_loader.py:66`; detection `:2415` (`is_jang_model`), `:2313` (`_find_config_path`); loaders `:5259` (text), `:5169` (VLM) | Four config filenames, four format tokens. Embedded form also read from `config.json["jang"]` / `config.json["jang_config"]` (`:2326-2364`) |
| **JANG affine** (per-tensor bit assignment) | `weight_format` ∈ `{"affine", "jang_affine"}`; manifest at `utils/jang_loader.py:6678-6704` | The layout that triggers automatic JIT (§7.1) |
| **JANGTQ / mxtq** | `utils/jang_loader.py:2491` (`weight_format == "mxtq"` → v2); tensor suffix `_vlm_is_mxtq = any(k.endswith(".tq_packed") …)` at `:4272`; loader `loaders/load_jangtq.py:18` re-exporting `jang_tools.load_jangtq` | The TurboQuant-compressed variant; `.tq_packed`/`.tq_norms`/`.tq_bits` sidecars; optional `jangtq_runtime.safetensors` (`cli.py:171`) |
| **mxfp4 / mxfp8** | `utils/jang_loader.py:67`; detection `_jang_quant_mode` at `:221-240`; applied `:4463-4469` via `nn.quantize(..., mode=quant_mode, ...)` | Native MXFP weight layouts |
| **MLX uniform affine 2/3/4/5/6/8-bit, groups 32/64/128** | `utils/jang_loader.py:68-69`, `utils/quant_shape_inference.py:133-134` | Both as JANG's inner layout and as plain bundles via stock `mlx_lm.load` (`utils/tokenizer.py:1551`) |
| **bf16 / fp16 (unquantized)** | stock `mlx_lm.load` fallthrough `utils/tokenizer.py:1551` | JANG loaders also *set* compute dtype to bf16 for large-expert/MLA models (`utils/jang_loader.py:347` `model.set_dtype(mx.bfloat16)`) |

Family-specific loaders are dispatched before the generic JANG path: DSV4
(`utils/tokenizer.py:1446-1458` → `loaders/load_jangtq_dsv4.py`), Laguna (`:1466-1474`),
ministral3 (`:1487-1495`).

### 8.3 What it refuses

Every refusal below is a positive `raise`, not an inference from a missing flag.

| Case | Evidence | Error |
|---|---|---|
| Declared bits outside {2,3,4,5,6,8} or group outside {32,64,128} | `utils/jang_loader.py:294-300` | `ValueError`: "MLX model-weight quantization supports only bits 2/3/4/5/6/8 and group sizes 32/64/128. Re-quantize the bundle or fix the stale quantization metadata." |
| Unsupported group size inferred from tensor shapes | `utils/quant_shape_inference.py:708-712` | `ValueError` |
| Declared quant not supported for MLX | `utils/quant_shape_inference.py:736-739` | `ValueError` |
| JANG format version major > 2 | `utils/jang_loader.py:5352-5355` | `ValueError`: "Unsupported JANG format version: … (this loader supports 1.x and 2.x)" |
| Non-numeric JANG version | `utils/jang_loader.py:5349-5351` | `ValueError` |
| JANG config missing `format`/`weight_format` | `utils/jang_loader.py:5327-5341` | `ValueError` |
| VLM whose config is not a JANG format | `utils/jang_loader.py:5237-5241` | `ValueError` |
| ZAYA loaded through the generic JANG path | `utils/jang_loader.py:1752-1760` | `RuntimeError`: "ZAYA model_type=zaya requires a ZAYA-aware runtime … refusing to load … through a generic JANG path" |
| DSV4 without its dedicated loader available | `utils/tokenizer.py:1498-1502`, `1509-1513` | `RuntimeError`: "DSV4 dedicated loader is unavailable; refusing generic JANG fallback" |
| **GGUF — at conversion time** | `commands/convert.py:139-148` | Prints "Error: This model is in GGUF format, which cannot be converted by vmlx-engine." **Note: refused by `convert`, not by the `serve` loader.** I found no explicit serve-time GGUF refusal, so a GGUF-only bundle would presumably fail later inside generic `mlx_lm.load` — I am not claiming a serve-time refusal, because I do not have one (§10) |

### 8.4 Conversion-only formats — do not assume a runtime loader

These exist in the `convert` command, in `jang_tools`, or in both, but I found **no runtime
weight-dequantisation path** for them. Stating the distinction matters, because "the tool knows
the word NF4" is not evidence that the server can serve it.

| Format | Where it exists | Runtime loader? |
|---|---|---|
| **NF4** | `cli.py:4626-4628` `--mode {default, NF4}` — a conversion mode only | **No loader found** |
| **AWQ** | `cli.py:4657-4660` `--use-awq`, `--awq-alpha`; folded into JANG weights at conversion (`models/spark2_5/spark2_5.py:10` "AWQ fold site") | No distinct AWQ codec — an AWQ-folded bundle is served by the ordinary JANG affine path |
| **GPTQ** | `jang_tools/gptq.py`, `dots3/gptq_dots3.py` | No runtime loader found |
| **FP8** | A *source* dtype for JANGTQ conversion (`jang_tools/profiles_cli.py:50` lists `float8_e4m3fn`) | No runtime FP8 weight loader found |
| **bitsandbytes** | **No reference anywhere** in the engine source or `jang_tools` | **Not supported** |

### 8.5 Local paths and the HuggingFace hub

**Both are supported for text and JANG loads.** `load_jang_model` calls
`prepare_model_bundle_for_load(model_path, allow_download=True)` (`utils/jang_loader.py:5281-5287`,
same for VLM at `:5185-5191`), and `prepare_model_bundle_for_load`
(`model_bundle_integrity.py:545-582`) uses a local directory as-is, else calls
`snapshot_download(str(model))`. A stricter local-only resolver also exists
(`utils/jang_loader.py:2392-2412`, `snapshot_download(..., local_files_only=True)`).

**Image loaders are contractually local-only** — `allow_download=False`
(`model_bundle_integrity.py:554-556`). An absolute path that does not exist raises
`BundleIntegrityError` (`model_bundle_integrity.py:566-567`), so a harness passing a missing
`artifact_dir` gets a loud failure rather than a hub download — which is the correct behaviour
for a benchmark and worth knowing.

The bundle-integrity pass runs at load and prints its result on stdout (`cli.py:856-863`):
`Model bundle integrity: OK (N shards, N tensors, N remaining misaligned tensors)` or
`… atomically repaired …`. `vmlx bundle-check --json` exposes the same check as one
machine-readable object, which is the cheapest way for a harness to assert a bundle is intact
before spending a load on it.

---

## 9. What a `Runtime` subclass would need (**historical**)

> **Historical.** vMLX has since been integrated: it is `runtimes.Vmlx`, registered as
> `RUNTIMES["vmlx"]` on port 8000, alongside `mlxlm` (8081), `osaurus` (1337), `omlx` (8100) and
> `optiq` (8080). This section is kept because it is the analysis the subclass was written from
> — where it disagrees with `ohyesmlx/runtimes.py`, the code is the authority. Most of the flags
> it recommends are what the shipped `Vmlx.start_command` pins; the environment scrub below is
> the one recommendation it does not implement.

This section states what a fifth entry needs, against the `Runtime` interface
(`runtimes.Runtime`) and the `Handle` fields (`runtimes.Handle`).

### 9.1 Start command

The model is a **positional argument, first**, not `--model`. This is the one interface detail
that differs from every existing subclass.

```python
class Vmlx(Runtime):
    def start_command(self, artifact_dir: str, model_id: str) -> tuple[str, ...]:
        return (
            "vmlx", "serve", artifact_dir,
            "--host", "127.0.0.1",
            "--port", str(self.port),
            ...
        )
```

**Port.** The CLI default is `8000`, which was free in the registry when this was written and is
where the shipped subclass took its port (`RUNTIMES["vmlx"]`) — `optiq` is 8080 and `mlxlm` is
8081, so 8000 collided with nothing then. Do **not** use 8081: that is `mlxlm`'s port *and* the
GUI's `gateway_port` default (§3.2). The harness refuses to start over a port it does not own
(`Runtime.start`), so a collision fails loudly rather than silently — but choosing 8000 avoided
the question.

**What to pin, and why** (each is justified above):

| Flag | Value | Reason |
|---|---|---|
| `--api-key` | omit | Default is no auth (§4.2); `api_key()` returns `None` |
| `--stream-interval` | `1` | Finest granularity, unless the cell is *about* granularity. **Pin it explicitly** — 8 is the default and a cell must not inherit a number it did not choose |
| `--continuous-batching` | pin explicitly | Because `--no-continuous-batching` silently forces `stream_interval=1` (`cli.py:2892`), the two flags interact and the interaction is not visible in the argv |
| `--max-num-seqs` | `1` | Single-stream measurement; requires continuous batching |
| `--enable-jit` **or** `--no-jit` | pin one, always | Otherwise a JANG affine bundle silently gets JIT while a non-JANG one does not (§7.1) |
| `--no-speculative-model` | n/a | Not a flag — simply omit `--speculative-model` |
| `--disable-native-mtp` **or** `--native-mtp-depth N --native-mtp-depth-policy fixed` | pin one, always | MTP adapts at runtime (§7.4); either disable it or pin a depth under the fixed policy. **Done since this document was written:** the header pin `--mtp-depth` drives exactly that pair, and a depth is refused on an artifact whose MTP heads the runtime will not wire (§7.4.1) |
| `--flash-moe` | pin on or off, and read the log | Off by default, and accepted on models it cannot stream — every fallback is one log line and a resident load (§7.8). **Done since this document was written:** the header pin `--stream-experts` drives the flag and checks the `Flash MoE enabled:` line |
| `--native-mtp-sampling-policy` | `greedy-only` or leave + record | **`greedy-only` overrides the request's temperature** — it forces temperature 0, top_p 1, top_k 0, min_p 0, repetition_penalty 1. A cell that pins temperature 0 in the request body and passes nothing here is relying on MTP not to override; the default `compatible-only` "leaves sampling defaults alone" |
| `--prefix-cache` state | pin on or off | On by default |
| `--disable-block-disk-cache` | consider pinning | Removes the 22 GB on-disk cache and the synchronous startup trim (§7.5) from cold-load time |
| `--enable-disk-cache` | omit | Off by default; on, it makes request 1 differ from requests 2+ |
| `--use-paged-cache` | omit | Off by default; help says it needs `--continuous-batching` |
| `--kv-cache-quantization` | omit **and record that you omitted it** | Omitting selects production auto mode; passing it *disables* loader-level TurboQuant (§7.2). Neither choice is neutral |
| `--env` | scrub `VMLX_*`/`VMLINUX_*` | 438 variables, none in the start command (§3.3) |

**The scrub is the one non-flag item and it is the most important.** `_spawn` currently inherits
the environment; for this runtime the environment is a configuration surface of the same size as
the CLI. If the harness cannot scrubb, it should at minimum *record* the `VMLX_*` variables it
passed, or the cell's provenance is incomplete.

### 9.2 Readiness signal in the log

There is an **explicit readiness marker**, and it is better than a log-scrape heuristic
(`server.py:6199-6204`):

```python
    # The readiness barrier: uvicorn starts serving only after this yield, so
    # ready=true is reported exactly when requests can actually be answered.
    if _engine is not None or (_image_gen is not None and _image_gen.is_loaded):
        _lifecycle_progress.report(model_loaded=True, ready=True)
```

emitted as one parseable line per update (`load_progress.py:60-63`):

```python
def _emit(snap: dict) -> None:
    # One parseable line per update. INFO so it rides the normal engine log
    # stream the panel already consumes.
    logger.info("LOADPROGRESS %s", json.dumps(snap, separators=(",", ":")))
```

So the literal to match is a JSON object with `"phase":"ready"`, `"model_loaded":true`,
`"ready":true`:

```
LOADPROGRESS {"phase":"ready","completed":N,"total":N,"model_loaded":true,"ready":true,"generation":N}
```

**Two facts about it that a harness must get right.**

1. **It is on stderr, not stdout.** Logging is configured with the stdlib default
   `StreamHandler`, whose stream is **stderr** — `cli.py:2780-2781`
   `logging.basicConfig(level=…, force=True)`, with no `stream=sys.stdout` anywhere in the
   package. The source comments at `cli.py:1191` and `load_progress.py:11` both *call* these
   lines "stdout", and that is wrong. A harness that captures only stdout will see
   `Starting server at http://…` and never see readiness.
2. **`ready:true` is emitted after load and warmup**, because the lifespan runs engine `start()`
   and the acceleration/JIT/MCP setup before it (`server.py:6148-6202`). A harness matching this
   line measures a fully-warmed engine — which is what a benchmark wants, and it means the
   marker is *safe* to use as a warm-readiness signal in a way oMLX's would not be.

The **stdout** stream carries, in order: the `SECURITY CONFIGURATION` banner (`cli.py:2387`),
`Loading model: <path>` (`:2478`), a `Mode:` line (`:2715` / `:2737`), a `Stream interval: N
tokens` line, the cache-stack summary, and finally `Starting server at http://<host>:<port>`
(`cli.py:2942`). There are no progress bars — `tqdm` does not appear — load progress is conveyed
only through the structured `LOADPROGRESS` lines.

**`await_ready` as written already works**, because it polls `GET /v1/models` rather than the
log; `GET /v1/models` carries `Depends(verify_api_key)`, which is a no-op with no key, so the
inventory probe needs no credential. The log is read only for `log_load_error`, and readiness is
decided by the inventory. That is the right shape here too — the log's role is to surface a
traceback, and the `LOADPROGRESS` line is available as a stronger *warm* signal if the harness
ever wants to distinguish "serving" from "warm". A failed load raises before the barrier, so the
`ready:true` line's absence is itself diagnostic.

Note the initial lifecycle line is emitted before anything else (`cli.py:1195`
`_lifecycle_progress.begin_attempt(PHASE_STARTING)`), giving
`LOADPROGRESS {"phase":"starting",…,"ready":false,…"}`. **Match on `"ready":true`, not on the
mere presence of `LOADPROGRESS`.**

### 9.3 Stop

**There are no custom `SIGINT`/`SIGTERM` handlers in the main server path.** A grep for
`signal.signal` / `add_signal_handler` finds handlers only in `distributed/cli.py:152-153`, not
in `cli.py` or `server.py`. Shutdown is therefore uvicorn's default signal handling, which runs
the FastAPI lifespan shutdown half (`server.py:6206-6233`).

That shutdown **flushes disk caches**, and it is bounded by timeouts:

- `await asyncio.wait_for(_engine.stop(), timeout=10)` (`server.py:6216`) — so the engine gets
  up to 10 s.
- `DiskCacheManager.shutdown` joins its writer thread with `join(timeout=10.0)`
  (`disk_cache.py:1794`), draining the write queue and closing the SQLite pool.
- `scheduler.shutdown` (`scheduler.py:7941-7979`) logs its way through the prompt disk cache, the
  SSM companion disk cache and the block disk cache in turn.
- An `atexit` callback removes the global block-cache budget lease
  (`global_disk_cache_budget.py:305-306`).

**So the process may linger for up to ~10 s after SIGTERM while it flushes.** The existing
`_shutdown(pid, port, stop_command)` helper already escalates and does not return until the port
is free, which is the correct contract; `stop_command()` itself needs no value, because the
runtime has no stop subcommand — sending SIGTERM to the spawned PID *is* the stop.

**Disk-cache writes happen incrementally during serving**, on a background writer thread
(`disk_cache.py:16`, `:277`; `store()` is non-blocking). Shutdown flushes only the pending queue,
so a restart is not delayed by a full cache rewrite. But **a run that is killed with SIGKILL
rather than SIGTERM loses its pending queue**, which changes the next run's cache state — a
reason to let `_shutdown` complete rather than escalating early.

### 9.4 Version probe

**There is no `--version` flag** (verified: `vmlx --version` → `error: unrecognized arguments:
--version`), so `version_command()` cannot return a flag invocation the way `optiq --version` and
`omlx --version` do.

The reliable sources, best first:

| Source | How | Value |
|---|---|---|
| **Module constant** | `$SRC/__init__.py:15` | `__version__ = "1.6.59"` — the authoritative one, and `server.py:6236-6241` passes it as the FastAPI app `version`, so it is what `/openapi.json` reports |
| **Bundle `Info.plist`** | `plutil -extract CFBundleShortVersionString raw …/Contents/Info.plist` | `1.6.59` |
| **Running server** | `GET /openapi.json` → `info.version` | `1.6.59`. Needs a live server |
| **`GET /api/version`** | `server.py:17266-17280` | **`"0.12.6"` — do not use.** It is the Ollama-compatibility shim's value, not vMLX's |

Since `Runtime.version()` requires a command, the cleanest fit is a command against the bundled
interpreter, or reading the file directly:

```python
def version_command(self) -> tuple[str, ...]:
    return ("/Applications/vMLX.app/Contents/Resources/bundled-python/python/bin/python3",
            "-c", "import vmlx_engine; print(vmlx_engine.__version__)")
```

with `parse_version` taking the first line. **Note that `version()` is called after
`await_ready`, both from `Runtime.start`, so the running server's `/openapi.json` is also
available at that moment** — but reading the module constant is cheaper and works even if the
server never reaches readiness, which is exactly when provenance matters most.

`GET /v1/models` reports **no version field** (`server.py:16162-16185`; `ModelInfo` at
`api/models.py:747-753` has only `id`, `object`, `created`, `owned_by`), so the model inventory
cannot double as a version probe on this runtime.

### 9.5 What model id `/v1/models` reports

`_resolve_model_name` (`server.py:8800-8805`) is unambiguous:

```python
def _resolve_model_name() -> str:
    """Return the model name to expose via the API.

    Priority: _served_model_name > _model_name > 'default'
    """
    return _served_model_name or _model_name or "default"
```

`_model_name` is `_normalize_model_name(model_name)` (`server.py:9134`), set from the positional
model argument. `_normalize_model_name` (`server.py:8767-8797`) has three cases:

```python
    if os.path.sep in model_name or model_name.startswith("/"):
        parts = model_name.rstrip("/").split("/")
        # HuggingFace hub cache layout: .../hub/models--<org>--<repo>/snapshots/<hash>[/...]
        for part in parts:
            if part.startswith("models--") and "--" in part[len("models--"):]:
                marker = part[len("models--"):]
                seg = marker.split("--", 1)
                if len(seg) == 2 and seg[0] and seg[1]:
                    return f"{seg[0]}/{seg[1]}"
        if len(parts) >= 2:
            return f"{parts[-2]}/{parts[-1]}"
        return parts[-1]
    return model_name
```

So, concretely:

| `artifact_dir` passed to `serve` | Model id on the wire |
|---|---|
| `…/hub/models--JANGQ-AI--Qwen3.5-27B-JANG_4S/snapshots/<hash>` | `JANGQ-AI/Qwen3.5-27B-JANG_4S` |
| `/Users/jrazz/models/qwen3-4bit` | `models/qwen3-4bit` |
| `qwen3-4bit` (no separator) | `qwen3-4bit` |

**This is the third distinct convention among the runtimes this harness drives**: `mlxlm` lists
the absolute `--model` path, `optiq` lists the absolute path with a `:no-think` variant, and
vMLX strips to an `org/repo` form. So `model_id_candidates` should be:

```python
def model_id_candidates(self, artifact_dir: str, model_id: str) -> tuple[str, ...]:
    absolute = str(Path(os.path.abspath(artifact_dir)))
    return _ordered(
        (hf_style_name(absolute), model_id),   # "org/repo" from the path tail
        name_forms(artifact_dir),
    )
```

**And `--served-model-name` removes the guesswork entirely.** With
`--served-model-name <token>`, `/v1/models` reports exactly that token — and additionally lists
`_model_name` when the two differ (`server.py:16168-16172`), because "clients using either name
can find the model". **Pinning `--served-model-name` is strictly better than matching a derived
name**, and it is what the harness should do.

`GET /v1/models` also advertises the embedding model when one is loaded
(`server.py:16174-16179`), so a cell that passes `--embedding-model` sees two entries.

### 9.6 API key

**Not needed.** `verify_api_key` (`server.py:7177-7190`) returns `True` when `_api_key is None`,
which is the default (`server.py:5241`). `--api-key` is opt-in, and it is not persisted anywhere.
So:

```python
def api_key(self) -> str | None:
    return None        # unless the subclass passes --api-key itself
```

This is the opposite of oMLX, where the readiness probe authenticating while the measurement did
not is a recorded failure. Here the failure mode is inverted and harmless: the handle records
`None`, `_inventory` sends no credential, and the server accepts. **If the harness ever passes
`--api-key`, it must also override `api_key()` to match, or the readiness probe will 401** —
`await_ready` already treats 401/403 as fatal and explained (`Runtime.await_ready`), which is the
right behaviour.

### 9.7 The one thing the subclass cannot pin

`check_host_state()` exists so a runtime can refuse to start when host state it cannot control
has moved. vMLX's equivalent surface is larger than its CLI:

- the **22 GB of existing block cache** at `~/.cache/vmlx-engine/block-cache/`, which adds to
  cold-load time via the synchronous startup trim (§7.5);
- the **438 `VMLX_*` environment variables** (§3.3);
- the **GUI's `chats.db` settings** (§3.2), which matter only if the GUI ever launches a server
  on the port the harness wants.

A defensible `check_host_state` for this runtime asserts the port is free (already done
generically) and asserts that no unrecorded `VMLX_*` variable is set in the spawn environment.
The block-cache question is a policy decision for the coordinator, and this document does not
make it.

---

## 10. What could not be determined from static inspection

Stated plainly, with the reason, per the rule that a negative claim needs better evidence than a
positive one.

1. **Which reasoning parsers defer to finalization.** §5.4 quotes the fallback that fires when
   `reasoning_was_streamed` is False, but the set of parsers that *set* that condition to False
   lives across `reasoning/` (15 files, per-family parsers) and was not enumerated. A live probe
   with `--reasoning-parser` set per family would settle it. **Until then, treat "reasoning
   streams incrementally" as the normal case with a documented exception, not as a guarantee.**
2. **Whether the `0.50` shard-repack threshold at `utils/jang_loader.py:5774` runs on every JANG
   load or only on a one-time JANG→MLX repack.** The helper sits inside a large loader and I did
   not trace its callers. This determines whether it is a per-run cost or a first-run cost, and
   therefore whether it belongs in cold-load time on every cell.
3. **The exact runtime cost of the block-disk-cache startup trim on this machine.** The source
   says "on a root with hundreds of namespaces that is seconds" and there are 16 namespaces here
   holding 22 GB, so the cost is likely sub-second — but I did not measure it, and measuring it
   requires starting the server.
4. **Whether a GGUF-only bundle is refused at `serve` time.** The refusal is at `convert`
   (`commands/convert.py:139-148`). I found **no** serve-time GGUF refusal, and I am deliberately
   not converting that absence into a claim: per this project's own rule, "there is no code that
   refuses it" is the honest form, and what actually happens needs a live attempt.
5. **The precise uvicorn literal lines and streams.** `uvicorn.run(app, log_level=…)` is called at
   `cli.py:2943` with no `log_config` override, so uvicorn's library defaults apply — including
   that `uvicorn.error` (carrying "Uvicorn running on …") is conventionally stderr while
   `uvicorn.access` is conventionally stdout. **Those two stream assignments come from the
   uvicorn package, not from this source, and I did not verify them here.**
6. **Whether the `--stream-interval` help text's backpressure claim is *entirely* wrong or merely
   mis-attributed.** §5.8 shows the collector cannot be stalled by a client and no backpressure
   signal reaches the MTP gate. It remains possible that heavy per-token SSE work on the same
   asyncio event loop inflates the *measured* cycle wall — that would be event-loop CPU
   contention, not socket backpressure. Distinguishing the two needs a live run with a slow
   client, which this dispatch forbids.
7. **Whether JIT materially changes decode speed on the specific artifacts this project holds.**
   The source's own evidence is a 397B JANG_1L at ~10 tok/s without JIT against "expected 20+"
   (`cli.py:2079-2083`) — a directive note, not a measurement, and about a model this project
   cannot run at 36 GiB of free disk. Whether JIT is worth its warmup for the artifacts actually
   in `~/.cache/huggingface/hub` is a live question, and §7.1 exists so that the experiment is
   possible: `--enable-jit` vs `--no-jit` on the same JANG bundle.
8. **Whether the DFlash2 `generation_tps` log line is ever emitted on the models this project
   runs.** The unguarded division is in `dflash/model_mlx.py:681`, outside the engine tree, and
   I traced only the three lines around it. I cannot say how often the DFlash2 lane is selected,
   only that its rate computation is unguarded.
9. **The complete GUI settings key set.** `DEFAULT_CONFIG` is defined in an 85 MB `app.asar`; I
   extracted the cache/generation/JIT/MoE keys and their defaults but did not enumerate every
   key. §3.2 is accurate as far as it goes and is explicitly not exhaustive.

---

## Appendix A — the 438 `VMLX_*` / `VMLINUX_*` environment variables

Every name below is read somewhere in `$SRC`. Names differ only by the `VMLX_` / `VMLINUX_`
legacy prefix; most are read as fallback pairs, so the two spellings of a given name are the
same control. Most are per-family kernel toggles. The measurement-relevant subset is tabulated
in §3.3.

**Native MTP** (the largest family, and the one that changes decode behaviour):
`VMLX_NATIVE_MTP`, `_ADAPTIVE_DEPTH`, `_ADAPTIVE_RAISE`, `_ADAPTIVE_VALUE`,
`_ADAPTIVE_WARMUP_CYCLES`, `_AR_CALIBRATION`, `_AR_FALLBACK`, `_AR_FALLBACK_MIN_SAMPLE`,
`_AR_REENTRY`, `_AR_SAFETY`, `_AR_SAFETY_WARMUP`, `_AR_SAFETY_WINDOW`, `_AR_STEP_MS`,
`_COST_AR_STEP_MS`, `_COST_FALLBACK`, `_COST_MIN_CYCLES`, `_COST_RATIO_THRESHOLD`,
`_CYCLE_TRACE`, `_D1_MIN_ACCEPT`, `_D2_MIN_ACCEPT`, `_D3_MIN_ACCEPT`, `_DEPTH`,
`_DEPTH_GATE_MIN_SAMPLE`, `_DEPTH_PROBE`, `_DRAFT_MARGIN`, `_FORCE`, `_MAX_DEPTH`,
`_PARKED_PRIMING`, `_PRIME_WINDOW`, `_PROMPT_PRIMING`, `_RAISE_MIN_ACCEPT`, `_RAISE_MIN_SAMPLE`,
`_RUNTIME_COST_GATE`, `_RUNTIME_COST_MARGIN`, `_RUNTIME_COST_MIN_CYCLES`, `_SEED_COST_MARGIN`,
`_SEED_TRACE`, `_USE_TUNING`, `_VALUE_COOLDOWN_CYCLES`, `_VALUE_HYSTERESIS`,
`_VALUE_INITIAL_PROBE_CYCLES`, `_VALUE_MIN_SAMPLES`, `_VALUE_PROBE_INTERVAL_CYCLES`,
`_VALUE_RAISE_MIN_ACCEPT`, `_VALUE_WINDOW`;
`VMLX_MTP_ALIGNED_HEAD_CACHE`, `_BYPASS`, `_CYCLE_FENCE`, `_FUSED_SYNC`, `_PROFILE`,
`_RECREATE_HEAD_CACHE_ON_REJECT`, `_RETAIN_HEAD_CACHE`, `_SKIP_REPLAY`, `_STOCHASTIC_ACCEPT`,
`_VERIFY_PAD`, `_VERIFY_PAD_TILE`, `_VERIFY_PREFETCH`;
`VMLINUX_MTP_VERIFY_PAD`.

**Caches and storage:** `VMLX_PREFIX_CACHE_ENABLED`, `_MEMORY_LIMIT_MB`;
`VMLX_MEMORY_KV_CACHE_MEMORY_LIMIT_MB`, `_QUANTIZATION`; `VMLX_PAGED_CACHE_BLOCK_SIZE`,
`VMLX_PAGED_CACHE_ENABLED`, `_FRUGAL`, `_METAL_PRESSURE_EVICT`, `_METAL_PRESSURE_MARGIN_GB`;
`VMLX_DISK_CACHE_DIR`, `_ENABLED`, `_MAX_GB`; `VMLX_BLOCK_DISK_ADMISSION_TIMEOUT_SECONDS`,
`_PENDING_WRITE_BYTES`; `VMLX_STRICT_BLOCK_DISK_WRITE_FENCE`;
`VMLX_SSM_DISK_CACHE_DIR`, `_MAX_GB`, `_NAMESPACE`; `VMLX_ENABLE_SSM_DISK_CACHE`,
`VMLX_DISABLE_SSM_DISK_RESTORE`, `VMLX_DISABLE_SSM_INLINE_CAPTURE`, `VMLX_DISABLE_SSM_PREFIX_RESUME`,
`VMLINUX_SSM_STATE_CACHE_MB`; `VMLX_CACHE_HASH_DEBUG`, `VMLX_CACHE_REUSE_BUDGET_FRACTION`,
`VMLX_CHAINED_PREFIX_INDEX_HASH`; `VMLX_TQ_COMPRESS_AFTER`, `_DECODE_TIMING`,
`_RECOMPRESS_MAX_TOKENS`; `VMLX_TURBOQUANT_KEY_BITS`, `_VALUE_BITS`, `_CRITICAL_KEY_BITS`,
`_CRITICAL_VALUE_BITS`, `_SEED`, `_SINK_TOKENS`; `VMLX_DISABLE_TQ_KV`, `VMLX_FORCE_TQ_AUTO`,
`VMLX_SWA_TQ`, `VMLX_MIXED_SWA_STORAGE_TQ`, `VMLX_FULL_PRECISION_LIVE_KV`;
`VMLX_COLD_PREFILL_MATCH_WARM_SPLIT`, `VMLX_COLD_PREFILL_TAIL_SPLIT`;
`VMLX_DISABLE_MIXED_SWA_CLEAN_RESUME`, `VMLX_DISABLE_RECURRENT_PREFIX_REUSE`,
`VMLX_DISABLE_DRIFTING_PREFIX_REUSE`, `VMLX_ZAYA_DISABLE_PREFIX_REUSE`;
`VMLX_VLM_IMAGE_CACHE_LIMIT`, `_FLOOR_GB`, `_FREE_FRACTION`, `_GB`;
`VMLX_PIXEL_CACHE_DEBUG_DIR`.

**Memory and Metal guards:** `VMLX_MEMORY_PRESSURE_GUARD`, `_REJECT_PCT`,
`VMLX_MEMORY_TOTAL_BUDGET_PERCENT`, `VMLX_MLX_CACHE_LIMIT_MB`, `VMLX_TURN_PEAK_ADMISSION`,
`_ALLOWANCE_MB`, `VMLX_LOW_RAM_ADVISORY_GB`; `VMLX_METAL_WS_GUARD`, `_MAX_BYTES`, `_MAX_GB`,
`_REJECT_PCT`; `VMLX_METAL_WIRED_HEADROOM_GB`, `_RESERVE_FRACTION`, `_RESERVE_GB`;
`VMLINUX_METAL_WIRED_RESERVE_FRACTION`, `_GB`, `_PCT`;
`VMLX_METAL_BUFFER_COUNT_GUARD`, `_BUFFER_GUARD_BASELINE`, `_BUFFER_GUARD_FRACTION`;
`VMLX_METAL_PROJECTED_OUTPUT_GUARD`, `_PROJECTED_TOKEN_BUDGET_FRACTION`,
`_PROJECTED_TOKEN_TRANSIENT_MULTIPLIER`; `VMLX_RECONSTRUCT_MEMO_MAX_WS_PCT`,
`VMLX_TRACE_RECONSTRUCT_MEMORY`; `VMLX_PAGED_FRUGAL`.

**Prefill and batching:** `VMLX_PREFILL_ADMISSION`, `_MIN_MARGIN_GB`,
`VMLX_PREFILL_CHUNK_ATTN_BUDGET_GB`, `VMLX_PREFILL_KEEP_ALLOC`, `_TIGHT_PREFILL_ADAPTIVE_GROWTH`,
`VMLX_TIGHT_PROJECTED_STEP_CAP`, `VMLINUX_TIGHT_MEMORY_PREFILL_STEP_SIZE`;
`VMLX_INFERENCE_COMPLETION_BATCH_SIZE`, `_MAX_CONCURRENT_REQUESTS`, `_MAX_TOKENS`,
`_MAX_TOKENS_PER_STEP`, `_PREFILL_BATCH_SIZE`; `VMLX_ANSWER_RESERVE`, `_CONTEXT_OUTPUT_CLAMP`,
`VMLX_DECODE_KV_PRESIZE`, `_PRESIZE_HEADROOM`, `VMLX_DEEP_SPAN_CACHE_CLEAR_TOKENS`,
`VMLX_KV_PRESIZE_SPAN`, `VMLX_CHUNKED_SSM_REDERIVE`, `VMLX_ALLOW_HYBRID_CHUNKED_PREFILL`,
`VMLX_DISABLE_HYBRID_AUTO_CHUNK`, `VMLX_HYBRID_ADAPTIVE_CHUNK`, `_BASE_SPLICE`,
`_CHECKPOINT_INTERVAL`, `_CLEAN_STORE`, `_DETECTION`, `_MIN_CHUNK`, `_ONE_SHOT_GUARD_BYTES`,
`_PREFILL_DRAIN`, `_PREFILL_MEM_TRACE`, `_PREFIX_PROMOTION`, `_SSM_RECOMPUTE`,
`VMLINUX_HYBRID_CLEAN_STORE`, `VMLINUX_HYBRID_PREFIX_PROMOTION`.

**Sampling, logging and process:** `VMLX_SAMPLING_TEMPERATURE`, `_TOP_P`, `_TOP_K`, `_MIN_P`,
`_REPETITION_PENALTY`; `VMLX_LOG_REQUEST_FIELDS`, `VMLX_DEBUG_LOG_CACHE_HITS`,
`_CACHE_MISSES`, `_MEMORY_USAGE`, `VMLX_DEBUG_MEDIA_KWARGS`, `_PROFILE_KERNEL_TIMES`,
`_STATS_INTERVAL`, `VMLX_CENSUS_GC`, `VMLX_PROMPT_DUMP_DIR`, `VMLX_NUM_THREADS`,
`VMLX_USE_METAL`, `VMLX_COMPUTE_PRECISION`, `VMLX_KV_COMPUTE_PRECISION`,
`VMLX_HARMONIZE_PARAM_DTYPES`, `VMLX_DEFAULT_KV_CACHE_QUANTIZATION`,
`VMLX_ALLOW_MLA_KV_QUANT`, `VMLX_REPLAY_EXACT_GEN_PROMPT`,
`VMLX_DISABLE_GEN_PROMPT_STRIP`.

**Distributed:** `VMLX_CLUSTER_SECRET`, `VMLX_WORLD_SIZE`, `VMLX_RANK`, `VMLX_DISCOVER_`,
`VMLX_MODELS_DIR`, `VMLX_MODEL_INTEGRITY_CACHE_DIR`, `VMLINUX_MODELS_DIR`.

**Tooling and reasoning:** `VMLX_TOOL_ARGS_SCHEMA_VALIDATION`,
`VMLINUX_TOOL_ARGS_SCHEMA_VALIDATION`, `VMLX_RESPONSES_HISTORY_MAX`, `VMLX_PLD_MAX_TEMP`.

**PLD and speculation:** `VMLX_PLD_MAX_TEMP`, `VMLX_MTP_*` (above).

**Per-family kernels** — `VMLX_QWEN4_*` (73 names, the largest single family),
`VMLX_GLM5_*` (33), `VMLX_DSV4_*` (30), `VMLX_QWEN35_*` (10), `VMLX_M3_*` (7),
`VMLX_QWEN_VL` / `VMLX_QWEN_VLM_GATED_DELTA_KERNEL`, `VMLX_DOTS3_*` (7),
`VMLX_OMNI_*` (5), `VMLX_MLLM_*` / `VMLINUX_MLLM_*` (~20), `VMLX_CODEBOOK_*` (7).
These select fused Metal kernels per architecture; a wrong value is a correctness bug or a
performance regression, not a configuration knob a benchmark should touch.
