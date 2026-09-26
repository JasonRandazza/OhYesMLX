# OptiQ (`mlx-optiq` 0.5.13) — capability and configuration reference

> **Re-verified against `mlx-optiq` 0.5.13 on 2026-09-25.** This document was written against
> 0.5.6; on 2026-09-25 every `file:line` citation and capability claim in §1–§8 (and the non-MTP
> material in §9) was walked against the installed source at
> `/Users/jrazz/Dev/tools/mlx-optiq/.venv/lib/python3.12/site-packages/` (`optiq --version` →
> `mlx-optiq, version 0.5.13`), with stale line numbers corrected in place. `mlx-lm` is
> unchanged at 0.31.3 and every `mlx_lm/` citation was re-checked against it. The pass changed
> three claims materially: OptiQ now reports `usage.completion_tokens_details.reasoning_tokens`
> (§6.2 — this document's "never present" blocker is lifted), it injects `--prompt-cache-size`
> and `--max-tokens` as well as `--prompt-cache-bytes` (§7.3), and both shims consume the
> closing usage frame so neither bypasses `--context-scale` (§6.6). The `serve` flag block also
> declares four flags this document had not listed (`--ngram-draft`, `--ngram-gate`,
> `--ngram-min`, `--on-generation-death`). Still not verified: everything marked **NEEDS
> PROBE** — no server was started, no model loaded, and no request sent in this pass. §9.2's
> MTP-gate passages are documented separately and were not part of this pass.

Static inspection. Nothing in this document was produced by starting the server, loading a
model, or sending a request. Where a claim depends on live behaviour rather than code, it is
marked **NEEDS PROBE** and the exact probe is given.

Sources, all read directly:

| Component | Version | Path |
|---|---|---|
| `mlx-optiq` | **0.5.13** (every citation re-read 2026-09-25) | `/Users/jrazz/Dev/tools/mlx-optiq/.venv/lib/python3.12/site-packages/optiq` |
| `mlx-lm` (the actual HTTP server) | **0.31.3** | `/Users/jrazz/Dev/tools/mlx-optiq/.venv/lib/python3.12/site-packages/mlx_lm` |

Everything below is cited as `file:line` relative to
`/Users/jrazz/Dev/tools/mlx-optiq/.venv/lib/python3.12/site-packages/` unless stated. Bare module
names resolve there: `cli.py` is `optiq/cli.py`, `serve.py` is `optiq/serve.py`, `server.py` is
`mlx_lm/server.py`, and `variants.py` / `mtp_patch.py` / `artifacts.py` live under
`optiq/runtime/` (`optiq/runtime/mtp/` for the last two) rather than at the root.

**The single most important structural fact:** `optiq serve` is not a server. It is a stack of
patch installs — 33 distinct `install_*` functions called inside `serve_cmd` alone, plus a handful
of patches installed under other names (`install_rot_merge`, `install_fused_sdpa`,
`install_sampler_rng`, `install_context_cap`, `install_idle_unload`) — applied to
`mlx_lm.server`, ending in an unconditional hand-off:

```
optiq/cli.py:3310    sys.argv = ["mlx_lm.server"] + argv_extra
optiq/cli.py:3311    from mlx_lm.server import main as mlx_main
optiq/cli.py:3312    mlx_main()
```

So the HTTP surface, the sampler, the chat template, the SSE format and the `usage` block are
**mlx-lm's**, not OptiQ's. OptiQ's own contributions are the patches, and the patches are where
the surprises are. A capability question ("can it do X") is answered by mlx-lm's code; a
*configuration* question is answered by OptiQ's.

---

## 1. Entry points

### 1.1 The binary on PATH

```
$ ls -l /Users/jrazz/.local/bin/optiq
lrwxr-xr-x  optiq -> /Users/jrazz/Dev/tools/mlx-optiq/.venv/bin/optiq
```

`/Users/jrazz/Dev/tools/mlx-optiq/.venv/bin/optiq` is a 323-byte Python console script:

```python
#!/Users/jrazz/Dev/tools/mlx-optiq/.venv/bin/python3
# -*- coding: utf-8 -*-
import sys
from optiq.cli import cli
...
sys.exit(cli())
```

Registered by `mlx_optiq-0.5.13.dist-info/entry_points.txt`:

```
[console_scripts]
optiq = optiq.cli:cli
```

**On the interpreter-resolution hazard, precisely.** The dispatch asks whether a console script
resolves its interpreter relative to its own location, breaking when symlinked into
`~/.local/bin`. For this install it does **not** — the shebang is an absolute path into the
venv, so the `~/.local/bin/optiq` symlink works. The failure mode here is the adjacent one:
the shebang is absolute to *that specific venv*, so the entry point survives symlinking but
does not survive the venv being moved, renamed, or rebuilt. `~/.local/bin/optiq` would then
fail with a missing-interpreter error, not a fallback to another Python.

Verified: the symlink is on PATH, the shebang is absolute, and the two agree.

### 1.2 The interpreter chain

```
.venv/bin/python3 -> python -> /Users/jrazz/.local/share/uv/python/cpython-3.12-macos-aarch64-none/bin/python3.12
```

`.venv/pyvenv.cfg`: `home = /Users/jrazz/.local/share/uv/python/cpython-3.12-macos-aarch64-none/bin`,
`uv = 0.11.20`, `version_info = 3.12.13`, `include-system-site-packages = false`.

The venv is uv-managed and pins a uv-managed CPython. Two indirections (venv `python3` → venv
`python` → uv toolchain) mean a `uv python` upgrade can move the interpreter out from under a
venv.

### 1.3 Other executables in the same bundle

`.venv/bin` holds 72 scripts. Two categories matter:

- **`mlx_lm.server`** — the stock, unpatched upstream server, same absolute venv shebang. It is
  directly runnable. Running it serves the same model **with every OptiQ patch absent**: no
  streaming experts, no KV patches, no structured output, no auth, no variant handling. It is
  the control condition for any "what did OptiQ change" question, and it is on PATH.
- The other 17 `mlx_lm.*` entry points (`mlx_lm.convert`, `.generate`, `.chat`, `.lora`, …),
  plus unrelated transitive scripts (`flask`, `hf`, `huggingface-cli`, `uvicorn`, `pytest`,
  `ruff`, `transformers`, …).

### 1.4 A server that ships but cannot be started

`optiq/runtime/mtp/server/openai.py` is a **complete second OpenAI-compatible server**
(8,891 lines, FastAPI/uvicorn-style, distinct from `mlx_lm.server`) with its own argparse at
`optiq/runtime/mtp/server/openai.py:8525` and its own sampler defaults
(`openai.py:5468-5472`: `temperature 0.6`, `top_p 0.95`, `top_k 20`, `max_tokens 16384`,
`reasoning "auto"`).

It is launched as a subprocess by
`optiq/runtime/mtp/commands/public.py:5271-5274`:

```python
cmd = [
    sys.executable,
    "-m",
    "mtplx.server.openai",
```

**In this install that command cannot work.** `mlx_optiq-0.5.13.dist-info/top_level.txt` contains
only `optiq`, and:

```
$ .venv/bin/python3 -c "import importlib.util as u; print(u.find_spec('mtplx'))"
None
```

There is no `mtplx` package and no `.pth` providing it. `optiq/runtime/mtp/cli.py` is not wired
to any `optiq` subcommand either — the top-level command set is
`benchmark, cloud, cluster, code, config, convert, eval, kv-cache, lab, latency, lora,
prune-experts, run, serve`, plus a hidden `game` (registered at `optiq/cli.py:68, 210, 338,
941, 1097, 1165, 2089 (hidden), 2108, 2123, 2214, 2441, 2498, 3324, 3471, 3766` — there is no
`add_command` call anywhere in the module).

**Consequence for this document, and it is the load-bearing one for §5:** `reasoning_content`
appears only in that unreachable tree. Nothing on the `optiq serve` path can emit it. See §5.1.

---

## 2. Command-line surface

### 2.1 Top level

```
optiq [OPTIONS] COMMAND [ARGS]...
  --version    Show the version and exit.
  --help
```

`optiq --version` is the harness's `version_command` (`runtimes.Optiq.version_command`) and
answers in the runtime's own phrasing, `mlx-optiq, version <X>`; `Optiq.parse_version` records
the version alone.

### 2.2 `optiq serve` — OptiQ's own flags

Declared at `optiq/cli.py:2498-2656`, with
`context_settings={"ignore_unknown_options": True, "allow_extra_args": True}` (`cli.py:2500`),
which is what makes the forwarding in §2.3 possible.

| Flag | Default | Controls | Source |
|---|---|---|---|
| `--kv-bits INTEGER` | `None` (fp16) | Uniform KV cache quantization. Help says "4 or 8", but the option is declared `type=int` with **no `choices`**, so nothing enforces that set at the CLI and whatever is passed reaches `mx.quantize` | `cli.py:2502-2503` |
| `--kv-group-size INTEGER` | `64` | KV quant group size | `cli.py:2504` |
| `--quantized-kv-start INTEGER` | `0` | Token offset where KV quant begins | `cli.py:2505-2506` |
| `--kv-config FILE` | `None` | Per-layer mixed-precision KV; **overrides `--kv-bits`** | `cli.py:2507-2509` |
| `--adapter TEXT` (repeatable) | `()` | LoRA adapter(s), HF id or local dir; switches to mounted-LoRA mode | `cli.py:2510-2521` |
| `--anthropic/--no-anthropic` | **on** | OpenAI **Anthropic** `/v1/messages` endpoint | `cli.py:2522-2527` |
| `--responses/--no-responses` | **on** | OpenAI `/v1/responses` endpoint | `cli.py:2528-2533` |
| `--context-scale FLOAT` | `1.0` | **Multiplies reported usage token counts** — see §6.3 | `cli.py:2534-2541` |
| `--max-concurrent INTEGER` | `8` | Decode parallelism; also sets prompt-concurrency to `max(1, n//4)` | `cli.py:2542-2549` |
| `--auth/--no-auth` | **on** | Requires `Bearer sk-optiq-*` **if a header is present** | `cli.py:2550-2553` |
| `--mtp` | off | MTP speculative decoding via `OptiqEngine`; **the header pin's road in — §9.2** | `cli.py:2554-2558` |
| `--mtp-depth INTEGER` | `2` | Draft tokens per verify cycle; fixed for the whole call — §9.2 | `cli.py:2559-2563` |
| `--drafter TEXT` | `None` | Separate drafter model (γ=1 greedy); **mutually exclusive with `--mtp`** | `cli.py:2564-2571` |
| `--ngram-draft INTEGER` | `0` (off) | Prompt-lookup speculation: draft up to N tokens copied from the conversation itself; combines with `--mtp`, mutually exclusive with `--drafter` | `cli.py:2572-2582` |
| `--ngram-gate/--no-ngram-gate` | **on** | Choose the n-gram draft length per pass (calibrated once on first use) instead of using `--ngram-draft` as a fixed length | `cli.py:2583-2588` |
| `--ngram-min INTEGER` | `3` | Shortest n-gram match that triggers a draft | `cli.py:2589-2592` |
| `--no-fused-kv` | off | Opts out of the tight-RAM KV-quant path — see §7.7 | `cli.py:2593-2606` |
| `--stream-experts/--no-stream-experts` | `None` = **auto** | SSD expert streaming — see §7.1 | `cli.py:2607-2615` |
| `--stream-experts-cache INTEGER` | `0` | LRU expert cache per projection | `cli.py:2616-2620` |
| `--models-dir DIRECTORY` | `None` | Advertise local quants in `/v1/models`; **implies `--allow-model-switch`** | `cli.py:2621-2627` |
| `--allow-model-switch/--single-model` | single | Whether a request's `model` can hot-swap the server | `cli.py:2628-2635` |
| `--idle-timeout INTEGER` | `0` (off) | Unload model after N idle seconds | `cli.py:2636-2642` |
| `--max-context TEXT` | `"auto"` | `auto` / integer hard cap / `off` | `cli.py:2643-2650` |
| `--on-generation-death CHOICE` | `restart` | What to do when the generation loop dies (`restart` or `exit`); beats the `serve_on_generation_death` setting (§3.1). Implementation `serve.py:754-806` | `cli.py:2651-2656` |

Two defaults are worth stating twice because they are on by default and change the wire
surface: `--anthropic` and `--responses` both ship **enabled**.

**Whole block re-read 2026-09-25.** Every `Source` in this table is now a 0.5.13 line number,
taken from the installed source. Four flags that this table did not previously carry are listed
here for the first time: `--ngram-draft`, `--ngram-gate`, `--ngram-min` (prompt-lookup
speculation) and `--on-generation-death` (generation-watchdog policy). One default is worth
stating precisely: `--max-concurrent 8` is *injected* as `--decode-concurrency` /
`--prompt-concurrency` only when the caller did not pass those flags (`cli.py:2937-2945`, §7.4).

### 2.3 Everything else is mlx-lm's

Unknown options land in `ctx.args` (`cli.py:2500` sets `ignore_unknown_options` /
`allow_extra_args`; `cli.py:2768` takes `argv_extra = list(ctx.args)`) and are re-emitted verbatim
as `mlx_lm.server`'s argv (`cli.py:3310`). The real, authoritative flag set is therefore
mlx_lm.server's argparse, `mlx_lm/server.py:1751-1887`:

| Flag | Default | Controls |
|---|---|---|
| `--model` | `None` | Weights path or HF repo id |
| `--adapter-path` | `None` | Single adapter (OptiQ no longer uses this route — §3.4) |
| `--host` | `127.0.0.1` | Bind host |
| `--port` | `8080` | Bind port |
| `--allowed-origins` | `*` | CORS, comma-split |
| `--draft-model` | `None` | Speculative draft model |
| `--num-draft-tokens` | `3` | Draft tokens per step |
| `--trust-remote-code` | off | Tokenizer remote code |
| `--log-level` | `INFO` | Logging |
| `--chat-template` | `""` | Override chat template |
| `--use-default-chat-template` | off | Fall back to tokenizer default |
| `--temp` | **`0.0`** | Default temperature — **the fallback the injection in §7.2 overwrites** |
| `--top-p` | `1.0` | Default top-p |
| `--top-k` | `0` (disabled) | Default top-k |
| `--min-p` | `0.0` (disabled) | Default min-p |
| `--max-tokens` | **`512`** | Default generation cap |
| `--chat-template-args` | `{}` | JSON of `apply_chat_template` kwargs |
| `--decode-concurrency` | **`32`** | Parallel decodes |
| `--prompt-concurrency` | **`8`** | Parallel prompts |
| `--prefill-step-size` | `2048` | Prefill chunking |
| `--prompt-cache-size` | **`10`** | Distinct KV caches retained |
| `--prompt-cache-bytes` | `None` (**uncapped**) | Byte cap on the KV prompt cache |
| `--pipeline` | off | Pipelining instead of tensor parallelism |

Two upstream defaults are actively hostile on unified memory and OptiQ overrides both, silently,
unless you passed the underlying flag (§7.3, §7.4): `--decode-concurrency 32`,
`--prompt-cache-bytes` uncapped. Two more are now injected the same way and are easy to miss:
`--prompt-cache-size` (already touched, contrary to what this document used to say) and
`--max-tokens` (§7.3).

Also executed unconditionally at startup, not a flag:

```
mlx_lm/server.py:1888    if mx.metal.is_available():
mlx_lm/server.py:1889        wired_limit = mx.device_info()["max_recommended_working_set_size"]
mlx_lm/server.py:1890        mx.set_wired_limit(wired_limit)
```

The server raises MLX's wired-memory limit to the device maximum at boot. This is not
configurable by any flag and is not OptiQ's doing.

---

## 3. Settings surface beyond the command line

OptiQ has a real settings system, and it is larger than the `serve` flags.

### 3.1 Files and precedence

```
optiq/settings.py:18    explicit argument > environment > repo config > user config > default
optiq/settings.py:22    repo:  <repo>/.optiq/optiq.json     -- checked in, shared by the team
optiq/settings.py:23    user:  ~/.optiq/config.json         -- personal, applies everywhere
```

`OPTIQ_HOME` relocates the state root (`state_root()`, `settings.py:213-229`), and both config
paths derive from it (`user_config_path()`, `settings.py:232-234`; `repo_config_path()`,
`settings.py:237-238`). Every setting also has a canonical `OPTIQ_<NAME>` environment variable
(`settings.py:88-90`); the legacy-alias mechanism still exists (`Setting.aliases`,
`settings.py:86`, consulted at `settings.py:300-304`) but **no setting in 0.5.13 declares one**,
so that path is dead code today.

**Neither config file exists on this machine** — there is no `~/.optiq/config.json` and no
`.optiq/` in this repository. Every setting below is therefore at its default for any run this
harness makes today. That is worth re-checking before publishing a table, because a stray
`~/.optiq/config.json` would silently move every number. Re-checked 2026-09-25: both absent, and
no `OPTIQ_*` variable is set in the shell that ran the check.

The whole registry is one tuple, `SETTINGS` at `optiq/settings.py:96-204`:

| Setting | Default | Meaning |
|---|---|---|
| `home` | `None` → `~/.optiq` | State root. **Environment only** — a config file cannot set it (`settings.py:102-105`) |
| `output_dir` | `None` → `./optiq_output` | Converted artifact destination |
| `sandbox_container` | `None` | Container runtime for the code sandbox |
| `sandbox_python_image` | `python:3.11-slim` | Container image for the python tool |
| `sandbox_shell_image` | `alpine:3.20` | Container image for the terminal tool |
| `lab_boot_timeout` | `900` | Seconds to wait for a model server |
| `cluster_cwd` | `None` | Cluster worker cwd |
| `cluster_headroom_gb` | `None` → `2` | RAM free per node when placing shards |
| `cluster_cache_mb` | `None` | Per-node MLX cache limit |
| `cluster_gpu_reserve_gb` | `0.75` | GPU memory reserved per node |
| **`stream_prefetch`** | **`False`** | Prefetch next layer's experts while current runs |
| **`stream_scales_budget_gb`** | `None` | Cap on resident expert scales |
| **`stream_reference`** | `None` = auto | Force streaming of the *reference* model |
| **`flash_attn`** | **`"auto"`** | Attention backward: `auto`/`always`/`never` |
| `flash_attn_budget_gb` | `None` | Budget routing stock vs tiled backward |
| `flash_block` | `128` | Query-block size for tiled backward |
| **`fused_ce`** | `None` = auto | Fused cut-CE, gated on logit tensor size |
| `fused_ce_budget_mb` | `512` | Logit size above which fused CE turns on |
| `fused_dpo` | `False` | Fused CE for DPO |
| **`no_think`** | **`False`** | Disable thinking blocks on all chat endpoints |
| `anthropic_no_think` | `False` | Same, Anthropic shim only |
| **`lowbit_search`** | **`True`** | Range-search per group when quantizing |
| `lowbit_search_max_bits` | `3` | Widest bit-width the search applies to |
| `adapter_cache` | `None` → `~/.cache/optiq/adapters` | Remote adapter cache |
| **`kernels`** | **`True`** | Custom Metal kernels, enabled per model from a `TESTED` allowlist (`serve.py:540-578`, read at `:568`) |
| **`serve_on_generation_death`** | `"restart"` | Generation-watchdog action; `optiq serve --on-generation-death` beats it for that run (`serve.py:754-780`) |
| **`prefill_step`** | `512` | Prefill chunk size for the OptiQ engine (distinct from mlx-lm's `--prefill-step-size`) |
| **`dump_requests`** | `None` | When set, **every POST body is written** to that directory as `<n>-<path>.json` (`serve.py:1832-1852`, called at `:2086`) |
| `kv_debug` | `False` | Log KV rotation/quant decisions |
| `merge_debug` | `False` | Log batched rotating-cache merges |

`optiq config` prints every resolved value **and its source** (`describe()`, `settings.py:401-410`;
printing at `settings.py:419-444`), which is the intended way to record this in a run artifact.
Credentials are redacted (`settings.py:384-398`), though none of the settings above is one.

### 3.2 Which settings have no command-line equivalent

**Almost all of them.** No `optiq serve` flag *writes* a setting in `SETTINGS` — none calls
`settings.set_override` — but two have a flag that reaches the same behaviour by another route
(`--low-bit-search` on `convert`, `--on-generation-death` on `serve`). Everything else is
reachable only through `OPTIQ_*` environment variables or the two JSON files. The ones that touch
the serving path are marked in bold above:

- `stream_prefetch` — read at `optiq/runtime/moe_stream.py:183`, off by default.
- `stream_scales_budget_gb` — `moe_stream.py:370`.
- `no_think` — `optiq/cli.py:2837-2841`; `OPTIQ_NO_THINK=1` installs a global patch forcing
  `enable_thinking=False` on every chat request (`optiq/no_think.py:26-49`). This one *does*
  have a per-request equivalent (`:no-think` suffix, §4.3) but no CLI flag.
- `anthropic_no_think` — `optiq/anthropic_shim.py:284-290`.
- `flash_attn`, `flash_attn_budget_gb`, `flash_block` — `optiq/ops/attention_patch.py:91-110`,
  `optiq/ops/flash_attention_tiled.py:56`.
- `fused_ce`, `fused_ce_budget_mb` — `optiq/lora/trainer.py:120-128`.
- `lowbit_search`, `lowbit_search_max_bits` — `optiq/core/lowbit.py:169-185`. `--low-bit-search` /
  `--no-low-bit-search` exists, and it is on `optiq convert` (`cli.py:956-961`, applied at
  `cli.py:1038-1046`), not `serve`.
- `kernels` — `optiq/serve.py:540-578`; part of the `serve` path but with no flag.
- `serve_on_generation_death` — `optiq/serve.py:754-780`. The one setting with a **serve** flag:
  `--on-generation-death` (`cli.py:2651-2656`) passes the action straight to the watchdog, which
  prefers it over the setting. No other serve flag reaches this registry.

These are the ones that "silently decide what a cell measures": `OPTIQ_NO_THINK` alone changes
whether reasoning tokens exist at all, `OPTIQ_FLASH_ATTN` changes the attention kernel on a
training path, not the serving path, and `OPTIQ_KERNELS=0` turns off the serving-path kernel
rewrites that ship **enabled** by default (§3.1) — so an environment check has to include it.

### 3.3 Four more hidden configuration surfaces

Not in `SETTINGS`, but read at serve time:

1. **`generation_config.json` in the model directory.** `optiq serve` reads it and injects
   sampler flags (§7.2). This is per-artifact configuration that no flag and no env var
   announces.
2. **`~/.optiq/`** as a state root, and `~/.cache/optiq/adapters` for adapters
   (`settings.py:180-182`).
3. **Cloud Boost config** — `optiq/cli.py:3114-3127` loads `optiq.code.config` and installs
   a `/boost` handler **unconditionally**, even with no API key. A `/boost` request is
   intercepted before it reaches the model (`serve.py:2071-2186`; the trigger test is at
   `serve.py:2133`).
4. **`OPTIQ_DUMP_REQUESTS`** — with the `dump_requests` setting set, every POST body the server
   receives is written to disk (`serve.py:1832-1852`, called at `serve.py:2086`). Off by
   default, so it is invisible unless someone sets it; when on, it records every prompt a
   published run sent.

### 3.4 Adapters do not use mlx-lm's adapter route

`--adapter` does **not** forward `--adapter-path`. The comment at `optiq/cli.py:2797-2803` says
the upstream route "is a no-op on OptiQ's mixed-precision quantized base in some configs, so we
no longer use it." All adapters go through `install_multi_adapter` (`cli.py:2804-2805`, definition
`serve.py:1203-1402`), which registers sidecars and gates a `ContextVar` per request.

---

## 4. Per-request API fields

### 4.1 Non-standard fields `optiq serve` itself honours

| Field | Effect | Source | Default |
|---|---|---|---|
| `guided_json` | vLLM-style JSON constraint (lm-format-enforcer) | `optiq/runtime/structured.py:139-140` | `None` |
| `guided_regex` | Regex-constrained generation | `structured.py:142-143` | falsy → skipped |
| `guided_choice` | Constrain to one of a list | `structured.py:144-145` | falsy → skipped |
| `response_format` | `json_object` / `json_schema` | `structured.py:130-136` | `None` |
| `tool_choice` | Only `"required"` and `{"type":"function",...}` are honoured | `structured.py:94,105` | `None` |
| `adapters` (or `adapter`) | Selects a mounted LoRA adapter | `optiq/serve.py:1398` | `None` |

`structured.py` is installed unconditionally (`cli.py:3176-3177`) and **defaults
`enable_thinking=False`** on any request carrying a constraint (`structured.py:322-331` — it uses
`setdefault`, so an explicit client value still wins), so constrained requests do not produce
reasoning tokens unless the client asked for them.

### 4.2 Non-standard fields mlx-lm honours

| Field | Effect | Source | Default |
|---|---|---|---|
| `draft_model` | Speculative draft model | `mlx_lm/server.py:1164` | CLI `--draft-model` |
| `num_draft_tokens` | Draft tokens per step | `server.py:1165-1167` | CLI (3) |
| `adapters` | Adapter selection | `server.py:1168` | `None` |
| `max_completion_tokens` | Alias for `max_tokens`, **checked first** | `server.py:1169-1173` | `None` |
| `top_k` | Top-k sampling | `server.py:1178` | CLI (0) |
| `min_p` | Min-p sampling | `server.py:1179` | CLI (0.0) |
| `repetition_penalty` | Repetition penalty | `server.py:1180` | `0.0` |
| `repetition_context_size` | Window for the above | `server.py:1181` | `20` |
| `presence_context_size` | Window for presence penalty | `server.py:1183` | `20` |
| `frequency_context_size` | Window for frequency penalty | `server.py:1185` | `20` |
| `xtc_probability` | XTC sampling probability | `server.py:1186` | `0.0` |
| `xtc_threshold` | XTC threshold | `server.py:1187` | `0.0` |
| `chat_template_kwargs` | Merged into `apply_chat_template`; how `enable_thinking` is set | `server.py:1192`, applied `server.py:544-547` | `None` |
| `logit_bias` | Logit biasing | `server.py:1188`, normalised `1253-1257` | `None` |
| `role_mapping` | Custom role prefixes | `server.py:1598` | `None` |

The sampling resolution chain is body-first:

```python
mlx_lm/server.py:1174    self.temperature = self.body.get(
mlx_lm/server.py:1175        "temperature", self.response_generator.cli_args.temp
```

So a request that omits `temperature` inherits the CLI value — which is the value §7.2 may have
rewritten.

### 4.3 Model-id suffixes — a per-request field hidden in `model`

`install_thinking_variants` is installed **unconditionally** on every `optiq serve`
(`cli.py:2888-2889`), and `install_variants` again afterwards (`cli.py:3202-3203`). Together
they make the `model` string carry control data (`optiq/runtime/variants.py:29-36`):

| Suffix | Effect | Source |
|---|---|---|
| `:no-think` | `enable_thinking=False` | `no_think.py:79-84`; `optiq/runtime/variants.py:31` |
| `:nothink` | `enable_thinking=False` | `optiq/runtime/variants.py:32` |
| `:think` | `enable_thinking=True` | `no_think.py:79-84`; `optiq/runtime/variants.py:30` |
| `:precise` | **Sets `temperature = 0.0`** | `optiq/runtime/variants.py:33` |
| `:creative` | **Sets `temperature = 0.8, top_p = 0.95`** | `optiq/runtime/variants.py:34` |
| `:balanced` | **Sets `temperature = 0.4, top_p = 0.9`** | `optiq/runtime/variants.py:35` |

`precise` / `creative` / `balanced` overwrite the handler's sampler attributes for that request
(`optiq/runtime/variants.py:83-85`), so they beat both the body and the CLI. An unknown suffix is
left alone (`variants.py:53-56`), and only `think`, `no-think`, `precise` and `creative` are
advertised in `/v1/models` (`variants.py:42`) — `nothink` and `balanced` work if sent but are not
listed. The harness uses `:no-think` (`Optiq.model_id_candidates`) — which is sound, and is the
variant whose text lands in `delta.content` rather than `delta.reasoning` (see §5).

### 4.4 Accepted but ignored

These are traps: they parse cleanly and do nothing.

| Field | Reality | Evidence |
|---|---|---|
| `n` | Never read. Always one choice. | No request-body read of `n` in `mlx_lm/server.py`; a grep for `body.get("n")` / `body["n"]` across both packages finds none (re-run 2026-09-25) |
| `user` | Never read. | Same, for `body.get("user")` / `body["user"]` |
| `tool_choice: "none"` / `"auto"` | mlx-lm ignores `tool_choice`; OptiQ acts only on `"required"`/function form | `structured.py:89` states mlx-lm "ignores `tool_choice` entirely" |
| `role_mapping` | Only used on the no-chat-template fallback path | `server.py:558-559` |
| `logprobs` on OptiQ's replaced generators | Returns placeholder `0.0` | `serve.py:407-414` `_NullLogprobs`; used at `serve.py:521,996,1160,1174` |
| Anthropic `thinking`, `metadata` | Never read | `anthropic_shim.py` |
| Responses `metadata`, `store`, `reasoning`, `text`, `truncation` | Never read from the request | `responses_shim.py` |

---

## 5. Streaming behaviour

**This section is static evidence only. No SSE stream was captured. Every claim here is a
code-level fact about which branch executes; the end-to-end shape has not been observed, and
the coordinator should confirm it with the probe at the end of this section.**

### 5.1 Which channels, and the headline correction

The `optiq serve` path emits **`reasoning`**. It does **not** emit `reasoning_content`.

```
$ grep -n "reasoning" mlx_lm/server.py | grep -v "gen.state\|initial_state"
mlx_lm/server.py:1357            if reasoning_text:
mlx_lm/server.py:1358                choice[key_name]["reasoning"] = reasoning_text
```

```
$ grep -rln "reasoning_content" optiq/ mlx_lm/
optiq/runtime/mtp/server/openai.py     <- unreachable, §1.4
optiq/runtime/mtp/opencode.py          <- the same unreachable tree
optiq/runtime/mtp/cli.py               <- the same unreachable tree
optiq/runtime/mtp/commands/public.py   <- the same unreachable tree
optiq/code/engine.py                   <- a CLIENT, reads either name
optiq/code/loop.py                     <- a CLIENT, replays it on the next turn
optiq/code/config.py                   <- a CLIENT, a help string
optiq/code/trace_writer.py             <- a CLIENT
optiq/compaction.py                    <- drops it when compacting history
optiq/eval/backends.py                 <- an eval CLIENT
optiq/responses_shim.py                <- REQUEST side only, see below
mlx_lm/chat_templates/deepseek_v32.py  <- a chat template string
optiq/mlx_lm_patches/deepseek_v4_chat_template.jinja  <- another template string
```

Re-run 2026-09-25; the list has grown since this document was written, and every addition is a
*client* or a *request*. `responses_shim.py` mentions the name only while building the OpenAI
request it forwards — an assistant turn's stored reasoning is replayed as `reasoning_content` so
the chat template can render it (`responses_shim.py:169-326`) — and it emits Anthropic-style
`thinking` / Responses-style `reasoning` items, never a `reasoning_content` field. Not one of
those is the `mlx_lm.server` response path. This matters directly: the oMLX finding was
that oMLX streams **only** in `reasoning_content`
(`docs/research/2026-09-15-omlx-streams-in-the-reasoning-channel.md`). OptiQ does the opposite —
it streams in `reasoning` and never writes `reasoning_content`. **A harness that reads only
`reasoning_content` will see zero reasoning deltas from OptiQ and will conclude, wrongly, that
OptiQ emits no reasoning.** The two runtimes put the same information in differently-named
fields.

OptiQ's own client hedges for exactly this reason (`optiq/code/engine.py:583-584`):

```python
reasoning = (getattr(delta, "reasoning", None)
             or getattr(delta, "reasoning_content", None))
```

### 5.2 Channel inventory and granularity

Deltas are assembled in one place, `mlx_lm/server.py:1349-1360`:

```python
mlx_lm/server.py:1354        choice[key_name] = {"role": "assistant"}
mlx_lm/server.py:1355        if text: choice[key_name]["content"] = text
mlx_lm/server.py:1357        if reasoning_text:
mlx_lm/server.py:1358            choice[key_name]["reasoning"] = reasoning_text
mlx_lm/server.py:1359        if tool_calls: choice[key_name]["tool_calls"] = tool_calls
```

| Channel | Present when | Granularity | Evidence |
|---|---|---|---|
| `role` | Every delta, `"assistant"` | — | `server.py:1354` |
| `content` | Normal-state text | **Per token** | `server.py:1455` loop; `server.py:1489` write |
| `reasoning` | Reasoning-state text | **Per token** | `server.py:1460-1461` |
| `tool_calls` | A parsed call exists | **Whole, one chunk** | `server.py:1462-1469`; JSON-serialized at once |
| `finish_reason` | Per choice | — | `server.py:1312` |
| `logprobs` | When requested | — | `server.py:1317-1328` |
| `usage` | Only if `stream_options.include_usage` | One trailing frame, `"choices": []` | `server.py:1516-1526` |
| `data: [DONE]` | Terminal | — | `server.py:1527` |
| `: keepalive n/total` | During prefill | SSE comment | `server.py:1410-1415` |

The emitter is `APIHandler.handle_completion` (`mlx_lm/server.py:1368-1552`) writing at
`server.py:1489`: `self.wfile.write(f"data: {json.dumps(resp)}\n\n".encode())`.

One further channel is added by OptiQ, not mlx-lm: `usage.completion_tokens_details` appears on
every non-streaming response and every streamed usage frame because of `install_reasoning_token_usage`
(cli.py:3111-3112, §6.2), and `usage.optiq_boost` appears when a Boost fell back to the local
model (`serve.py:1800-1802`).

Granularity is controlled by the loop variable, **not** by any numeric interval:

```
mlx_lm/server.py:1455    for gen in response:
mlx_lm/server.py:1460        if gen.state == "reasoning":
mlx_lm/server.py:1461            reasoning_text += gen.text
mlx_lm/server.py:1462        elif gen.state == "tool":
...
mlx_lm/server.py:1469            text += gen.text
```

One `Response` per decoded token, so one chunk per token. **There is no optiq equivalent of
oMLX's `stream_interval`.** OptiQ's `install_streaming_experts` does "prefill bucketing" for
graph-recompile reasons (`cli.py:2614-2615` states it; the bucketing is
`optiq/runtime/moe_stream.py:250-292`), which is prefill, not delta granularity.

### 5.3 No channel is mirrored

`reasoning` and `content` are fed by mutually exclusive states (`server.py:1460-1469`) and both
accumulators are reset after every emit (`server.py:1491-1493`). A single chunk cannot carry
both. The Anthropic and Responses shims keep them separate too (`anthropic_shim.py:445-481`,
where `delta.reasoning` and `delta.content` drive separate content blocks; `responses_shim.py:697-732`,
where they drive a `reasoning_summary_text.delta` item and an `output_text.delta` item with their
own accumulators at `:608-612`).

This is the opposite of oMLX, which mirrors the completed text into `content` at the end. **The
mirroring-dedupe logic the harness built for oMLX must not be applied blindly to OptiQ** — for
OptiQ, a `content` delta is real content.

Caveat: generator *replacements* change how tokens are produced, not the channel mapping.
`--mtp` (`serve.py:424-537`), assistant-drafter (`serve.py:1107-1202`) and diffusion
(`serve.py:1414-1545`) all yield per-token `GenerationResponse` objects; the diffusion path runs
the decode to completion and then replays token-by-token (`serve.py:1414-1545`), which would
show a real TTFT followed by a compressed burst.

### 5.4 What controls whether `reasoning` appears at all

A conjunction:

1. **Tokenizer vocabulary.** `mlx_lm/tokenizer_utils.py:256-284` infers think tokens from the
   vocab — only `<think>/</think>` and `<longcat_think>/</longcat_think>` are recognised —
   exposing `has_thinking` (`tokenizer_utils.py:391-392`). If `has_thinking` is False there is no
   reasoning state at all and think text arrives as ordinary `content`.
2. **`enable_thinking` in the chat template.** Defaults to `has_thinking`
   (`tokenizer_utils.py:335-337`); overridden per request by `chat_template_kwargs`, by
   `OPTIQ_NO_THINK=1`, by `OPTIQ_ANTHROPIC_NO_THINK`, by the `:think`/`:no-think` model suffix,
   or forced off by structured output (`structured.py:322-324`).

### 5.5 Probe to confirm

**NEEDS PROBE.** One request, `max_tokens` large (128+, not 8 — the oMLX error was a sample
size of one), counting deltas per channel:

```bash
curl -sN http://127.0.0.1:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"<served-id>","messages":[{"role":"user","content":"Explain confounded variables in three sentences."}],
       "max_tokens":128,"stream":true,"temperature":0,
       "stream_options":{"include_usage":true}}'
```

Expected from the source: many `delta.reasoning` chunks, then `delta.content` chunks, **zero**
`reasoning_content`, one `usage` frame, then `[DONE]`. The same request with `":no-think"`
appended should move the text into `content`. If either expectation fails, the source has been
patched since 0.5.13 and this document is stale.

---

## 6. Token accounting

### 6.1 What `usage` contains

`mlx_lm/server.py:1339-1347`:

```python
response["usage"] = {
    "prompt_tokens": prompt_token_count,
    "completion_tokens": completion_token_count,
    "total_tokens": prompt_token_count + completion_token_count,
}
if prompt_cache_count is not None and prompt_cache_count >= 0:
    response["usage"]["prompt_tokens_details"] = {
        "cached_tokens": prompt_cache_count,
    }
```

The stock block emits exactly four fields, the last only on a prefix-cache hit. OptiQ adds two
more on top of it: `completion_tokens_details.reasoning_tokens` (§6.2) and, after a Boost that
fell back to the local model, `usage.optiq_boost` (`serve.py:1799-1802`).

### 6.2 Reasoning **is** now separated

Nothing in `mlx_lm/server.py` has a `completion_tokens_details` or a `reasoning_tokens`; the
stock count is folded into `completion_tokens`:

```
mlx_lm/server.py:1472                tokens.append(gen.token)      # every state
mlx_lm/server.py:1522                        len(tokens),          # -> completion_tokens
```

`prompt_tokens` is `len(ctx.prompt)` (`server.py:1533`) and excludes any model-generated
reasoning.

**But OptiQ patches that block, and it was patched since this document was written.**
`install_reasoning_token_usage` (`serve.py:1747-1819`, installed unconditionally at
`cli.py:3111-3112`) wraps `handle_completion` to count the tokens the server itself classifies as
`reasoning` (`serve.py:1780-1785`), and `_add_details` (`serve.py:1793-1805`) writes

```
usage["completion_tokens_details"]["reasoning_tokens"] = <that count>
```

onto the non-streaming response and the streamed `include_usage` frame alike.

What that means for this harness:

- `docs/interfaces.md` pins
  `reasoning_tokens: int | None  # from usage.completion_tokens_details, if present`. On 0.5.13
  that field **is** present on OptiQ — this document used to call it a permanent `None` and a
  blocker for `interfaces.md`. That claim is withdrawn.
- `completion_tokens` still *includes* reasoning: the patch adds the breakdown, it does not
  subtract. `completion_tokens - reasoning_tokens` is the content-only count, and that subtraction
  is only comparable against a runtime that reports the same breakdown.
- `usage.optiq_boost` (`serve.py:1799-1802`) can also appear, and is not a token field.

### 6.3 Reported usage is scaled by `--context-scale`

`optiq/runtime/context_scale.py:33-39`:

```python
for k in ("prompt_tokens", "completion_tokens"):
    ...
    u[k] = int(round(v * factor))
p, c = u.get("prompt_tokens"), u.get("completion_tokens")
    u["total_tokens"] = p + c
```

Installed only when `context_scale != 1.0` (`cli.py:3209-3211`). The harness passes
`--context-scale 1.0` (`Optiq.start_command`), so this is a **no-op today** — but it is
one keystroke from silently multiplying every published token count, and the module docstring is
explicit that generation is untouched (`context_scale.py:11-13`).

### 6.4 The rate fields named in the dispatch do not exist here

```
$ grep -rn "generation_tokens_per_second\|generation_duration\|prompt_duration" optiq/ mlx_lm/ --include=*.py
(no matches)
```

`generation_tokens_per_second` and `generation_duration` **are absent from both packages**. No
tokens-per-second or duration field is emitted in `usage` on any OptiQ or mlx-lm path. The
15286.61-from-a-zero-duration failure described in the dispatch cannot arise here in that form.

What does exist are internal `GenerationResponse` fields that are never serialized —
`prompt_tps` / `generation_tps` — and OptiQ computes them with a **clamped denominator**:

```
optiq/serve.py:524            prompt_tps=ev["prompt_tokens"] / max(ev["prefill_time_s"], 1e-6),
optiq/serve.py:1156           elapsed = max(time.time() - t0, 1e-6)
optiq/serve.py:1165           generation_tps=n_tokens / elapsed,
optiq/runtime/engine.py:775   "decode_tps": (n_generated + 1) / max(elapsed, 1e-6),
```

`max(elapsed, 1e-6)` converts a zero or negative interval into a denominator of `1e-6`, so
`n / 1e-6` — up to 10⁶ × the token count. **The absurd-rate generator is present; only the
field that would publish it is missing.** Anything that reads these objects (rather than the
HTTP `usage` block) inherits the trap. (The `prompt_tps` division appears twice, at `serve.py:524`
and `:999`; the clamped-elapsed `generation_tps` twice, at `serve.py:1165` and `:1179`. The
diffusion and Dhara replay paths pass a literal `generation_tps=0.0`, `serve.py:1492-1493` and
`:1594-1595`.)

The exact source quote the dispatch asked for, for the record:

```
optiq/serve.py:524:  prompt_tps=ev["prompt_tokens"] / max(ev["prefill_time_s"], 1e-6),
```

### 6.5 Usage on streaming is opt-in

`stream_options` defaults to `None` (`server.py:1162`) and the usage frame is gated:

```
mlx_lm/server.py:1516    if (
mlx_lm/server.py:1517        self.stream_options is not None
mlx_lm/server.py:1518        and self.stream_options["include_usage"]
mlx_lm/server.py:1519    ):
```

**By default a streamed OptiQ response carries no usage at all.** The harness must send
`stream_options.include_usage`.

### 6.6 The shim endpoints count differently

| Endpoint | `input_tokens` | `output_tokens` | Reasoning |
|---|---|---|---|
| `/v1/chat/completions` | real | real (incl. reasoning) | folded in, and also broken out as `completion_tokens_details.reasoning_tokens` (§6.2) |
| `/v1/messages`, non-stream | from `prompt_tokens`, minus the cache read (`anthropic_shim.py:364-377`, used at `:360`) | from `completion_tokens` | carried as a `thinking` content block, not counted |
| `/v1/messages`, **streaming** | from the usage frame when one arrives (`anthropic_shim.py:447-448`), else the hard-coded `0` in the opening frame (`:408-416`) | from the usage frame, else one per `content` delta (`:478`); emitted as `self.usage or {output_tokens: count}` (`:499-503`) | thinking deltas are emitted (`:453-463`) but the fallback count excludes them |
| `/v1/responses`, non-stream | from `prompt_tokens` (`responses_shim.py:511-515`) | from `completion_tokens` | `_reasoning_tokens`: the server's count when present, else `max(1, len(reasoning_text.split()))` (`:408-414`) |
| `/v1/responses`, streaming | from the usage frame (`responses_shim.py:684-689`), else `0` (`:616`) | same, else one per delta (`:725`) | same `_reasoning_tokens` helper (`:899-910`) |

**Both shims now request and consume the closing usage frame** (`anthropic_shim.py:269-271`,
`responses_shim.py:388-390`), so both inherit `--context-scale`; this document used to say the
Anthropic streaming path bypassed it entirely. The word count is now only a fallback for a
server that reports no `reasoning_tokens` (`responses_shim.py:408-414`) — the "actual count is
hidden inside mlx-lm" comment this document quoted is gone. The Responses shim also reports the
prompt-cache hit as `input_tokens_details.cached_tokens` (`responses_shim.py:417-429`).

The harness pins `--no-anthropic --no-responses`, so none of this is on a measured cell; it
matters only to anyone who turns either endpoint on.

---

## 7. Behaviour that changes performance without appearing in the start command

This is the section the dispatch exists for. `--stream-experts` is the known one; it is neither
the only one nor the one most likely to bite this harness.

### 7.1 SSD expert streaming — the known heuristic, sourced

```
optiq/runtime/moe_stream.py:621    def should_stream(model_path: str, headroom: float = 0.70) -> bool:
optiq/runtime/moe_stream.py:622        """Auto-detect: stream a MoE quant whose on-disk weights are too large to
optiq/runtime/moe_stream.py:623        sit resident in ``headroom`` of total RAM (where MLX would OOM at compute)."""
optiq/runtime/moe_stream.py:624        if not is_streamable_moe(model_path):
optiq/runtime/moe_stream.py:625            return False
optiq/runtime/moe_stream.py:626        try:
optiq/runtime/moe_stream.py:627            import psutil
optiq/runtime/moe_stream.py:628            total = psutil.virtual_memory().total
optiq/runtime/moe_stream.py:629        except Exception:
optiq/runtime/moe_stream.py:630            try:
optiq/runtime/moe_stream.py:631                total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
optiq/runtime/moe_stream.py:632            except Exception:
optiq/runtime/moe_stream.py:633                return False
optiq/runtime/moe_stream.py:634        return model_disk_bytes(model_path) > headroom * total
```

The threshold is `headroom = 0.70` (`moe_stream.py:621`), applied as
`model_disk_bytes > 0.70 * psutil.virtual_memory().total`. `model_disk_bytes` is the sum of the
snapshot's `*.safetensors` (`moe_stream.py:612-618`).

Note it compares against **total** RAM, not available RAM — a distinction the codebase itself
calls out at `cli.py:3870-3875`:

> `should_stream()` compares against total RAM, so a 20 GB quant "fits" in 70% of 36 GB while
> 4 GB is actually free -- and the process is killed with no traceback, which reads as a crash
> rather than as running out of room.

So the heuristic has **both** failure directions: it turns streaming on when the model "fits"
by total RAM but not by available RAM (slow), and it leaves streaming off when total RAM is
large but the machine is busy (OOM).

Wiring: `install_streaming_experts` (`optiq/serve.py:1612-1695`) patches
`mlx_lm.server.ModelProvider._load`. The decision is `optiq/serve.py:1641-1643`:

```python
def _wants(mp: str) -> bool:
    return ((mode == "on" and is_streamable_moe(mp))
            or (mode == "auto" and should_stream(mp)))
```

`--stream-experts` maps `None → "auto"`, `True → "on"`, `False → "off"`
(`optiq/cli.py:3095-3096`), and `mode == "off"` returns before installing anything
(`serve.py:1629-1630`), so `--no-stream-experts` is a **complete** opt-out, not a partial one.

**Is `is_streamable_moe` even reached for the harness's `--no-stream-experts`?** No. Good.

### 7.2 **Sampler injection from `generation_config.json` — the one that fires for this harness**

`optiq/cli.py:2968-2975`:

```python
from .runtime.gen_config import read_recommended_sampling, merge_into_argv
if model_arg:
    recommended = read_recommended_sampling(model_arg)
    if recommended:
        argv_extra = merge_into_argv(
            argv_extra, recommended,
            prefix_log="[optiq.serve] applying model-recommended sampler:",
        )
```

`merge_into_argv` (`optiq/runtime/gen_config.py:124-169`) appends `--temp`, `--top-p`,
`--top-k`, `--min-p` for any recommended key **not already present in argv**:

```python
optiq/runtime/gen_config.py:162        already = any(a == flag or a.startswith(flag + "=") for a in out)
optiq/runtime/gen_config.py:163        if already:
optiq/runtime/gen_config.py:164            continue
optiq/runtime/gen_config.py:165        out += [flag, str(value)]
```

**This was the harness's "temperature 0" hazard, and four flags close it.**
`Optiq.start_command` passes `--temp 0 --top-p 1 --top-k 0 --min-p 0` explicitly, so every key
`merge_into_argv` can forward is already in argv, `already` is true for all of them, and the
injection is a no-op. The hazard is live rather than hypothetical, and was checked on 2026-09-25:
**every OptiQ quant in this host's HF cache carries a `generation_config.json`**, and
`read_recommended_sampling` resolves it from the cache snapshot (`gen_config.py:110-121`). The
three cached ones recommend `temperature 0.2` / `top_k 80` (LFM2.5-8B-A1B-OptiQ-4bit) and
`temperature 0.7` / `top_p 0.8` / `top_k 20` / `min_p 0.0` (Qwen3.5-4B and Qwen3.6-35B-A3B).

The three that matter most are the ones the request body does not carry:
`measure._request` sends `temperature` and no other sampler field — and `seed` only on the cells
whose runtime keeps it (`runtimes.Runtime.request_seed`, §9.2) — so an injected `--top-p`,
`--top-k` or `--min-p` would otherwise set the sampling distribution from a line in the
artifact, with nothing in the recorded command saying so.

`merge_into_argv` forwards only `--temp`, `--top-p`, `--top-k` and `--min-p` — its `flag_for`
map holds those four and nothing else. So of the five keys `_SAMPLER_KEYS` reads, four are
pinned by the harness and the fifth, `repetition_penalty`, cannot reach this command line at
all: it is exposed to clients, not forwarded to `mlx_lm.server`.

The injection is not fully silent — it prints
`[optiq.serve] applying model-recommended sampler: temperature=…` — but it does not appear in
the command the harness records, which is the whole category this document is about.

`read_recommended_sampling` also **never raises** (`gen_config.py:28-59`) and reads only
`temperature`, `top_p`, `top_k`, `min_p`, `repetition_penalty` (`gen_config.py:25`), dropping any
value that means "disabled" in another stack's convention — `top_k: -1`, a `top_p` outside
`(0, 1]`, a negative temperature or penalty (`_sane`, `gen_config.py:62-80`). With
`allow_hf_fetch=False` (the serve default) it is local-only.

### 7.3 `--prompt-cache-bytes`, `--prompt-cache-size` and `--max-tokens` are injected

`optiq/cli.py:2908-2931` computes a cache budget and appends flags unless the caller already
passed them:

```
optiq/cli.py:2912    _model_dir = _resolve_model_dir(model_arg)
optiq/cli.py:2913    pc_bytes = default_prompt_cache_bytes(_model_dir)
optiq/cli.py:2915    argv_extra = inject_prompt_cache_bytes(argv_extra, pc_bytes)
optiq/cli.py:2917    argv_extra = inject_prompt_cache_size(argv_extra, default_prompt_cache_size(_model_dir))
optiq/cli.py:2921    install_prompt_cache_byte_cap(_pc_budget)
optiq/cli.py:2924    inflates = inject_default_max_tokens(argv_extra)   # --max-tokens 32768
```

`default_prompt_cache_bytes` (`optiq/lab/mlx_cleanup.py:85-112`) derives from **what is left
after the weights and the live conversation**, not total RAM:

```
optiq/lab/mlx_cleanup.py:109    free = total - weights - _live_kv_bytes(model_dir, context_tokens)
optiq/lab/mlx_cleanup.py:110    budget = int(free * PROMPT_CACHE_FREE_FRACTION)     # 0.25
optiq/lab/mlx_cleanup.py:111    capped = min(int(total * PROMPT_CACHE_FRACTION), budget)   # 0.15 of total
optiq/lab/mlx_cleanup.py:112    return max(MIN_PROMPT_CACHE_FLOOR, capped)         # floor 512 MiB
```

The `_live_kv_bytes` subtraction is new since this document was written (`mlx_cleanup.py:115-135`)
and it is a real change of behaviour, not a refactor: the budget used to count only the weights,
so the cache and the live conversation were handed the same bytes twice. On a 36 GB M3 running
Qwen3.6-35B-A3B-REAP-19B that read 5.4 GB of cache as affordable while an 88k-token conversation
was itself holding 1.8 GB, and the session died of memory at turn 280 with the cache at its cap
and obeying it.

If the model dir cannot be resolved, it falls back to `max(2 GiB, 15% of RAM)`
(`mlx_cleanup.py:104-105`; constants at `:55-56`). The value is RAM-derived, so **it differs
between machines** — a 36 GiB and a 64 GiB Mac run the same artifact with different cache
budgets, and prefix-cache hit rates are therefore not comparable across machines without
recording this number.

**Three things 0.5.13 does that the 0.5.6 this document was written against did not:**

1. **`--prompt-cache-size` is now injected too** (`cli.py:2917`). `default_prompt_cache_size`
   (`mlx_cleanup.py:138-155`) returns 10 for an ordinary model and
   `HYBRID_PROMPT_CACHE_SIZE = 3` (`mlx_cleanup.py:67`) for a model whose cached prefixes cannot
   be trimmed (a Qwen3.5/3.6-style hybrid: ten turns of one conversation are ten full copies).
   This document used to say the flag was not touched; that is no longer true, and the injected
   value is model-shaped rather than constant.
2. **The byte cap is applied to the cache object itself**, not only passed as a flag
   (`install_prompt_cache_byte_cap`, `cli.py:2919-2921`, implementation `mlx_cleanup.py:226-263`).
   `--prompt-cache-bytes` reaches `LRUPromptCache` only on mlx-lm's *batch* path; on the
   sequential path — the one KV quantization forces (§7.7) and `--ngram-draft` forces too
   (`serve.py:611`) — the flag alone is silently ignored and the cache keeps up to ten whole
   conversations.
3. **`--max-tokens` is injected** at `DEFAULT_MAX_TOKENS = 32768` unless the caller passed one
   (`cli.py:2922-2927`; `mlx_cleanup.py:223` and `:266-275`). mlx-lm's own default is 512, and a
   request that omits `max_tokens` is exactly what that 512 truncated — an OpenAI client reads an
   absent limit as "up to the context". So on OptiQ an absent `max_tokens` means up to 32768
   tokens, not 512, and any harness assumption built on the §2.3 default is wrong for the
   no-`max_tokens` case.

`--prompt-cache-size` is the only one of the three the harness ever passes itself — and only on a
run that pins a cache state (§9, `runtimes.prompt_cache_flags`), which disables the injection for
that run.

### 7.4 Concurrency is capped below upstream's default

`optiq/cli.py:2933-2949`. With the `--max-concurrent` default of `8`:

```
optiq/cli.py:2943            argv_extra += ["--decode-concurrency", str(int(max_concurrent))]
optiq/cli.py:2945            argv_extra += ["--prompt-concurrency", str(max(1, int(max_concurrent) // 4))]
```

So the effective values are decode 8 / prompt 2, against upstream's 32 / 8
(`mlx_lm/server.py:1856,1862`) — unless the caller passed the underlying flag, which wins
(`cli.py:2938-2945`). The harness passes `--max-concurrent 1`, giving decode 1 / prompt 1. Fine,
but note the number that matters is `--decode-concurrency`, which the harness does not record.

### 7.5 MLX reuse-pool cleanup on every request

`optiq/cli.py:2902-2903` installs a post-response hook:

```
optiq/cli.py:2902    cleanup_threshold = default_threshold_bytes()
optiq/cli.py:2903    install_server_cleanup(cleanup_threshold)
```

`default_threshold_bytes()` is `max(1 GiB, 10% of total RAM)`
(`optiq/lab/mlx_cleanup.py:80-82`; constants at `:39-44`). When MLX's buffer reuse pool exceeds
it, the hook runs `gc.collect()` then `mx.clear_cache()` (`mlx_cleanup.py:191-200`; the calls are
at `:198-199`). The hook is installed
**unconditionally** on every `optiq serve` and is not exposed as a flag. It is RAM-derived, so
it fires at different points on different machines, and it costs a re-allocation from Metal when
it fires (`mlx_cleanup.py:16-18` estimates 10–100 ms).

### 7.6 Context cap `auto`

`--max-context auto` (the default) estimates a KV token cap and installs a rotating window
**only when the model's native context would not fit RAM** (`optiq/cli.py:3222-3258`; the `auto`
estimation is `:3230-3248`). When it
fires it changes the KV cache class to `RotatingKVCache`, which changes long-context behaviour
and can change output. The harness passed `--max-context 8192` until 2026-09-16 and passes `off` since: an integer
cap rotates rather than refuses, and on Qwen3.5 / LFM2 it was a no-op because both define
`make_cache` (`docs/research/2026-09-16-prompt-length-context-limits.md`). Either way the auto
path is bypassed, which is correct and should stay.

### 7.7 Fused KV path is automatic when KV quantization is on

`optiq/cli.py:2730-2739`: with `--kv-bits` or
`--kv-config` set and no `--no-fused-kv`, two patches install automatically (streaming per-layer
conversion + fused quantized SDPA). The `--no-fused-kv` help states the effect as a ~2x memory
reduction at 32k on a 24 GB Mac (`cli.py:2602-2604`: "24 GB Mac, granite-4.1-8b-4bit at 32k peak
goes from 16.35 GB (stock u4, would OOM) to 7.60 GB"). Not active for this harness (no KV
quantization), but it means any future KV-quant cell has a memory profile that differs from stock
mlx-lm and must be recorded.

The two patches are worth naming separately, because they are two changes and not one: the
streaming conversion converts **one layer at a time** instead of letting mlx-lm enqueue every
layer's `to_quantized` as one lazy batch, since the stock path holds "fp16_all_layers +
quantized_all_layers co-resident" and OOMs on tight RAM
(`optiq/runtime/streaming_kv_quant.py:1-25`); the fused SDPA replaces the attention with a
FlashAttention-2 tiling that never materializes the scores matrix, and its header carries the
figures above (`optiq/runtime/fused_quant_sdpa.py:1-30`). **So an OptiQ KV-quant cell is not
stock-mlx-lm-with-a-quantized-cache** — it is a different attention kernel and a different
conversion strategy. `--no-fused-kv` is the opt-out and produces stock behaviour, which is the
right control arm if the codec is the variable.

**Second automatic side effect.** KV quant can silently cost cross-request batching.
`install_quantized_kv` tries
`install_batch_kv_quant(default=(kv_bits, kv_group_size))` first — a mergeable quantizing cache
class for `BatchGenerator` — and falls back to `force_sequential_for_kv_quant("--kv-bits")` when
the hook point is missing (`optiq/serve.py:79-81`; the `--kv-config` path does the same at
`:286-287`). That function's own docstring is explicit that mlx-lm's batch path never quantizes
the KV cache and that the sequential path is forced instead, "strictly better than honoring the
flag in name only" (`serve.py:95-115`). At the harness's
`--max-concurrent 1` this costs nothing, but a future concurrency sweep on this runtime could
measure a batching loss that the flag caused.

### 7.8 The sampling RNG fix

`optiq/cli.py:3168-3174` installs a thread-safe sampler, because "mlx-lm's compiled categorical
sampler freezes the RNG on the generation worker thread, so temperature/seed are ignored and
output is effectively greedy" (`runtime/sampler_rng.py`, installed at `cli.py:3171-3172`). This
changes what `temperature`/`seed` do relative to stock
mlx-lm. It is a behavioural difference from the `mlxlm` runtime in this harness — the same
request body can produce different sampling behaviour on the two runtimes.

### 7.9 Installed unconditionally, for completeness

Each of these patches `mlx_lm.server` on every `optiq serve` run, with no flag:
download-retry shim (`cli.py:2695-2696`), tool-argument normalization (`cli.py:2701-2702`),
EOS-terminated tool calls (`cli.py:2707-2708`), generation watchdog (`cli.py:2709-2710`),
rotating-cache merge fix (`cli.py:2717-2724`), thinking variants (`cli.py:2888-2889`), server
cleanup and the prompt-cache byte cap (`cli.py:2902-2903`, `:2919-2921`), single-model field
policy (`cli.py:2957-2958`), tested kernels (`cli.py:2993-2994`), custom-code tokenizer
(`cli.py:2998-2999`), message-shape `content: null` on non-streaming messages
(`cli.py:3108-3109`), reasoning-token usage (`cli.py:3111-3112`, §6.2), Cloud Boost
(`cli.py:3117-3123`), sampling RNG fix (`cli.py:3171-3172`), structured output
(`cli.py:3176-3177`), tool-call healing (`cli.py:3185-3186`), and model variants
(`cli.py:3202-3203`). Conditional on the model or the flags, and equally invisible in the
recorded command: vision serving for a checkpoint with an `optiq_vision` sidecar
(`cli.py:3072-3089`), and the diffusion / Dhara / n-gram generator replacements
(`cli.py:2980-2990`, `:3016-3025`, `:3041-3066`).

`install_message_shape` is worth singling out: it adds `"content": None` to non-streaming
messages that produced only reasoning, and **deliberately does not touch `delta`**
(`serve.py:1698-1744`). Its docstring records that this was found when a live test read
`message["content"]` and got a `KeyError` (`serve.py:1713`).

### 7.10 Settings-level heuristics that are not flags

- `flash_attn: "auto"` — attention-backward kernel chosen by memory budget
  (`optiq/ops/attention_patch.py:91-110`). Training path, not serving.
- `fused_ce: None` = auto, gated on the logit tensor's size against `fused_ce_budget_mb: 512`
  (`optiq/lora/trainer.py:120-128`).
- `stream_reference: None` = auto — `models/llm.py:296-308` runs `should_stream()` on the
  *reference* model during KL evaluation, so a reference can silently switch to streaming and
  change the KL reference's numerics.
- `lowbit_search: True` by default — `optiq/core/lowbit.py:185`, applied only for `mode ==
  "affine"` and `bits <= 3` (`lowbit.py:211-214`). Silently inert outside that range.

---

## 8. Quantization formats

### 8.1 It does not have its own format parser

OptiQ delegates all base-model format decoding to `mlx_lm.utils.load_model`, then layers on the
streaming loader, a fast-load shim, a requantizer, and sidecars. Format questions are therefore
mostly mlx-lm questions.

### 8.2 What selects a format

| Mechanism | Keys | Source |
|---|---|---|
| Modern `quantization` block | `bits`, `group_size`, `mode` (default `affine`), plus **per-tensor-path overrides** | `mlx_lm/utils.py:348-363`; OptiQ's streaming loader reads the same at `optiq/runtime/moe_stream.py:459-462,515-517` |
| Legacy `quantization_config` | `quant_method`: `bitnet`, `mxfp4`, `compressed-tensors`, `awq`, `gptq` | `mlx_lm/utils.py:368-390` |
| Static mixed recipes | `mixed_2_6`, `mixed_3_4`, `mixed_3_6`, `mixed_4_6` | `mlx_lm/convert.py:20-80`; OptiQ's default is `mixed_3_6` (`optiq/backends/mlx_backend.py:655`) |
| Repo-name convention | `…-OptiQ-<N>bit` (parsed, not a loader key) | `optiq/lab/optiq_models.py:136-138` |
| Sidecars | `optiq/mtp.safetensors`, `optiq/optiq_vision.safetensors` — the MTP one is a **gate** on the depth pin, §9.2 | `optiq/sidecar_layout.py:28-31`; resolution at `optiq/runtime/mtp/artifacts.py:104-115` |
| MTP quant block | `mtplx_mtp_quantization` (`prequantized`, `policy`) | `optiq/runtime/mtp/artifacts.py:44-46` |
| Architecture | `model_type`: `diffusion_gemma` / `llada2_moe` (diffusion serving), `dhara_ar` (self-speculation) | `optiq/models/diffusion.py:50` lists only `diffusion_gemma` (`DIFFUSION_MODEL_TYPES`); the other two are matched at `optiq/cli.py:2980-2990` and `:3041-3048` |

Because `class_predicate` returns the per-path entry verbatim (`mlx_lm/utils.py:349-355`), a
`quantization` block can give **every layer a different bit-width and group size**. Two
artifacts both described as "4-bit" can be entirely different models numerically. Record the
full `quantization` block, not the headline bits.

### 8.3 What the streaming loader will and will not stream

```
optiq/runtime/moe_stream.py:353    _EXPERT_SEGMENTS = (".switch_mlp.", ".mlp.experts.", ".experts.switch_glu.",
optiq/runtime/moe_stream.py:354                        ".ffn.experts.")
optiq/runtime/moe_stream.py:357    def _is_expert_weight(key: str) -> bool:
optiq/runtime/moe_stream.py:358        return key.endswith(".weight") and any(seg in key for seg in _EXPERT_SEGMENTS)
```

`is_streamable_moe` (`moe_stream.py:588-609`) requires all three of: an index file, at least one
expert weight, and at least one listed shard **present on disk**. Disqualifiers: no
`model.safetensors.index.json`; no tensor matching the four segments and ending `.weight`; a
metadata-only cache entry (the comment at `moe_stream.py:600-607` explains this one caused
`/health` to answer 200 while every request hung, which is worth knowing for this harness's
readiness logic); or any exception → `False`.

### 8.4 Accepted but silently ineffective

The important one, and the codebase documents it against itself (`moe_stream.py:344-352`):

> `.experts.switch_glu.` was missing … So every Gemma-4 MoE answered False to
> `is_streamable_moe`, `--stream-experts` was accepted and silently did nothing … Nothing
> warned, because a request to stream something we do not recognise as streamable just falls
> through to a normal load.

That specific segment was added, but the **fall-through remains**: if `_wants()` is false the
loader silently takes the resident path (`serve.py:1691-1692`). A failed streaming attempt is
also swallowed to a resident load with only a log line (`serve.py:1688-1690`). So
`--stream-experts` being present in a command says nothing about whether streaming happened —
only the `[optiq.serve] SSD expert streaming: on` banner plus
`[optiq.serve] SSD expert streaming: pre-loaded <path>` does.

Other silent degradations:

- `fast_quantized_load`: a parameter absent from disk becomes `mx.zeros` (`optiq/runtime/fast_load.py:80-88`);
  unknown module types fall back to the original path (`fast_load.py:129-133`). Its docstring:
  "an unusual checkpoint degrades to 'cheap', never to 'broken'."
- `lowbit_search` is inert unless `mode == "affine"` and `bits <= 3` (`optiq/core/lowbit.py:211-214`).
- A per-layer predicate returning false leaves that layer unquantized, unreported
  (`mlx_lm/utils.py:353-355`).

**`--mtp` is not on that list: it fails, but late.** The engine is built on the first request,
and with no attachable head one warning is logged (`MTP head not attached …`,
`optiq/runtime/engine.py:297-304`) before `--mtp requested but … has no MTP head` is raised
(`serve.py:459-464`) and answered to the client as HTTP 404 (`mlx_lm/server.py:1424-1427`).
Nothing is served AR while the header says MTP — the cell fails loudly, one model load into the
run.

### 8.5 Explicit refusals

OptiQ has **no base-model quant-format refusal table of its own**; the refusals are inherited:

| Error | Source |
|---|---|
| `Only {bits=} is supported for AutoAWQ/GPTQ models.` | `mlx_lm/utils.py:88-89` |
| `Models with non-contiguous group indices (g_idx) are not currently supported…` | `mlx_lm/utils.py:96-99` |
| `Mode ({m.mode}) does not support activation quantization` | `mlx_lm/utils.py:396-402` |
| `Model type {model_type} not supported.` | `mlx_lm/utils.py:190-191` |
| `Invalid quant recipe {recipe}` | `mlx_lm/convert.py:36` |
| `Quant predicates only support 'affine' quantization.` | `mlx_lm/convert.py:122` |
| OptiQ-MEP: `does not know how to prune {model_type!r}…` | `optiq/mep/adapter.py:247-251` |
| OptiQ sidecars: `declares a vision/audio tower and ships weights that OptiQ does not recognise` | `optiq/sidecars.py:210-215` |

An unrecognised `mode` string is **not** refused by OptiQ — it passes straight to
`nn.quantize`/`mx.quantize`.

### 8.6 Refusal to start

`optiq serve` refuses to boot on a model whose weights are missing, rather than answering
`/health` forever (`cli.py:2860-2881`; implementation `_model_cannot_load`, `cli.py:2409-2439`).
The comment records that mlx-lm's `/health` is hardcoded to 200 and never consults model state:

```
GET  /health              -> 200 {"status": "ok"}
POST /v1/chat/completions -> nothing, forever
```

Note this check is **local-only and never touches the network** (`cli.py:2412-2413`), so an
uncached repo id is not rejected. It catches an on-disk directory with no `.safetensors` and no
weight index.

---

## 9. What this harness should pin, and why

The harness currently passes (`Optiq.start_command`):
`--model`, `--host`, `--port`, `--no-anthropic`, `--no-responses`, `--no-auth`,
`--max-context off` (8192 before 2026-09-16), `--max-concurrent 1`, `--idle-timeout 0`,
`--context-scale 1.0`, `--no-stream-experts` or `--stream-experts` (header pin 03-03, below),
`--mtp --mtp-depth N` when the run pins a draft depth (header pin 03-06, §9.2),
`--temp 0 --top-p 1 --top-k 0 --min-p 0`, and
`--prompt-cache-size 0` or `10` when the run pins a cache state.

**Done since this document was written:** the four sampler flags, which this table used to list
as its first priority, are now in the command — every key `merge_into_argv` forwards is already
in argv, so nothing is injected (§7.2).

### 9.1 `--stream-experts` is now a header pin, and the log is its evidence (03-03)

`--stream-experts` is no longer a flag this harness happens to pass: it is the header pin
`--stream-experts {off,on}`, and `--no-stream-experts` stays in the command for `off` and for an
absent pin — which is what keeps every recorded command byte-identical. `auto` is deliberately
**not** a value of the pin: it is the flag's own default (`None` → `"auto"`, `cli.py:2607-2615`,
`:3095-3096`), and taking that decision away from the runtime is what the pin is for. `off` is a
complete opt-out rather than a partial one — `mode == "off"` returns before anything is
installed (`serve.py:1629-1630`) — while `auto` streams a MoE the moment its weights exceed 0.70
of total RAM (`moe_stream.py:621-634`).

**The flag is not evidence that anything streamed, so the cell is checked against the log.**
Every fallback here is silent by design: `_wants()` false takes the resident path with no line
at all (`serve.py:1641-1643`, the fall-through the codebase documents against itself at
`moe_stream.py:344-352`), and a streaming attempt that raises prints one line and loads
resident (`serve.py:1688-1692`). The harness therefore reads the head of this start's own log
after readiness and before the first request, and **FAILs an `on` cell with that log quoted**
unless **both** of these are in it:

```
[optiq.serve] SSD expert streaming: on
[optiq.serve] SSD expert streaming: pre-loaded <path>
```

Both are required, and the first alone is why: the mode banner is printed at startup, before the
model is inspected (`cli.py:3095-3101`), so on a model `is_streamable_moe` answers `False` for
it appears and nothing streams. The pre-load line is printed only when the model was really
built through `load_streaming` (`serve.py:1654-1662`) — and note its own failure twin,
`streaming pre-load failed (…); the server will try at first request`, which is a fallback and
not a success.

**Not moved by this pin:** `--stream-experts-cache` stays at its `0` default, so a streamed cell
is the uncached streaming path; and `--kv-bits` still installs the fused streaming-KV path
(§7.7), which is a different mechanism with a similar name.

### 9.2 `--mtp --mtp-depth` is the second runtime the MTP-depth pin drives (03-06)

`--mtp` is an opt-in flag defaulting to off (`is_flag=True, default=False`, `cli.py:2554-2558`) and
`--mtp-depth` defaults to `2` (`cli.py:2559-2563`), so the header pin
`--mtp-depth {off,1,2,3}` maps straight onto the pair: **`off` and an absent pin pass neither
flag** — OptiQ's own off *is* the absence — and a depth passes `--mtp --mtp-depth N`. Every
recorded OptiQ command is unchanged by this, byte for byte, which is the pin's rule everywhere.

**The depth is fixed for the whole request, so no policy flag travels with it.** The draft/verify
cycle takes `cycle_K = depth` once and keeps it (`optiq/runtime/engine.py:920`), and the
HuggingFace-style dynamic-depth adapter that would have moved K mid-call was measured 4-17%
slower on Apple Silicon and removed (`engine.py:897-905`) — the opposite of vMLX, whose
`adaptive` default is why that runtime needs `--native-mtp-depth-policy fixed` beside every
depth.

**Three artifact conditions, all OptiQ's own, and the harness refuses a cell that fails any**
(`runtimes.optiq_mtp_refusal`):

| condition | source | what it costs otherwise |
|---|---|---|
| the head file is where the resolver looks | `expected_mtp_file`: the path the config names under `mlx_lm_extra_tensors.mtp_file`, else `optiq/mtp.safetensors`, `mtp.safetensors`, `mtp/weights.safetensors`, `model-mtp.safetensors` (`mtp/artifacts.py:104-115`; the subfolder-first/root-fallback pair at `sidecar_layout.py:39-50`) | `--mtp` attaches an engine with no draft head, warns once (`engine.py:297-304`) and answers every request as HTTP 404 (`serve.py:459-464`, `mlx_lm/server.py:1424-1427`) |
| the config declares an MTP layer | `_num_mtp_layers` reads `text_config.mtp_num_hidden_layers`, `text_config.num_nextn_predict_layers`, then `num_nextn_predict_layers` (`mtp_patch.py:69-76`); zero returns before any head is looked for (`:382-385`) | the same 404, with a sidecar sitting on disk unread |
| the head's tensors fit the block its own config says will be built | the config's `mtplx_mtp_quantization` (`with_config_defaults`, `mtp_patch.py:51-66`) against the sidecar's safetensors header (`runtimes._safetensors_shapes`, stdlib: 8-byte LE length + JSON) | the head loads and the block refuses it — `MTP head weight '…' has shape (256, 512, 2048), block expects (256, 512, 256)`, the injection fails, and all 25 requests of the visit answer HTTP 404 (`mtp_patch.py:345-355`, `:444-445`) |

Both OptiQ quants on this host satisfy the first two: they name `optiq/mtp.safetensors` in
`mlx_lm_extra_tensors.mtp_file` and declare `mtp_num_hidden_layers: 1`. The 35B's sidecar is
1,644,816,560 B. An artifact carrying `mtp.*` tensors in its *main* weights is refused here even
though OptiQ can read those too (`_embedded_mtp_weight_map`, `mtp_patch.py:277-299`) — the
sidecar is the shape every OptiQ quant ships, and a false refusal costs a cell rather than a
number.

**The third condition, added 2026-09-25 after the depth night** (`runtimes._optiq_head_packing_refusal`,
the artifact gate's third question). The 35B passed the first two on the night and its head still
could not load: the sidecar's routed experts are in the fused HuggingFace layout
(`mlp.experts.gate_up_proj` `(256, 1024, 2048)`, `mlp.experts.down_proj` `(256, 2048, 512)`),
`_split_fused_experts` rewrites those into `switch_mlp.*` weights carrying the dense shapes
unchanged (`mtp_patch.py:116-141`), and the block was built quantized — so the shape check raised
and the engine attached without a draft head. The four facts that decide it are all readable
before a server starts:

- **Whether the block is quantized.** `with_config_defaults` takes `prequantized`, `bits`,
  `group_size`, `mode` and `policy` from the config's `mtplx_mtp_quantization` (`mtp_patch.py:51-66`),
  and the block is quantized only when prequantized *and* a width is stated — with no width
  `_quantize_mtp_module` returns first (`:86-87`). A prequantized head is loaded as it is, without
  dequantization (`:162-168`), and the block is quantized *before* the weights are checked (`:444-445`).
- **Which tensors that quantizes.** `policy: all` quantizes every module `nn.quantize` reaches
  (`:90-96`); `cyankiwi` skips `fc`, `pre_fc_norm*` and `norm` and quantizes the rest of
  `layers.*` (`:102-113`); an unstated policy means `all` (`:89`). The converter writes the field by
  exactly that question — `cyankiwi` unless `mtp.fc.weight` was quantized (`mtp_convert.py:200`).
- **What a packed tensor is.** A quantized weight is `(out, in * bits / 32)` and its affine scales
  are `(out, in / group_size)`, so the pair is checkable against itself —
  `weight[-1] * 32 == scales[-1] * group_size * bits` — with no model dimensions. Both artifacts
  satisfy it exactly at bits 4, group 64.
- **What a fused expert tensor cannot be.** Its scales are never rewritten by the split, so the
  block's expert `.scales`/`.biases` have no source at all (`mtp_patch.py:356-364`) — an
  independent refusal from the shape mismatch beside it.

Measured against both artifacts: **`Qwen3.6-35B-A3B-OptiQ-4bit` is refused** (N/A with the two
shapes and the cell's own config quoted) and **`Qwen3.5-4B-OptiQ-4bit` still passes** — its 29
tensors are packed where the block quantizes them, and the one dense tensor it carries,
`mtp.fc.weight`, is outside a `cyankiwi` head's scope. Two ceilings, both a miss rather than a
false refusal: a head that is prequantized *by its key set* rather than by its config
(`_mtp_contract_for_weight_keys`, `mtp_patch.py:204-233`, against the per-family tables at
`mtp/constants.py:54-76`) is not read for shapes, and a sidecar whose header cannot be parsed
answers no shapes at all — the log half below is what catches those.

**The flag is not evidence that a head drafted, and the line that says so arrives late.** The
startup echo `[optiq.serve] MTP speculation enabled (depth=N, model=…)` (`cli.py:3057-3060`) is
printed before any model is touched, and the engine it names is built on the **first request**
(`_get_engine` runs from the patched `stream_generate`, `serve.py:443-471`). So the harness reads
the log head **after the first workload of the visit has answered**, and **FAILs the cell with
the log quoted** unless it carries:

```
[optiq.serve] MTP engine ready (depth=N).
```

taken verbatim from `serve.py:465`, with the pinned depth interpolated — a cell that asked for 3
and got an engine built at 2 is a FAIL, not a number under a depth the decode did not hold. The
fallback lines quoted when it is missing are the engine's own warning that it attached without a
head (`MTP head not attached …`, `MTP engine…`; `engine.py:297-304`); the HTTP 404 that follows
goes to the client and never to the log.

**A log with neither marker is not a log that says nothing** (2026-09-25, open question 5 of
`docs/research/2026-09-25-mtp-depth-sweep.md`). The 4B's three depth cells printed no ready line
and no attach warning, and the check's own words reported that as the log saying "nothing about
why" — while the log held the cause, a per-request traceback ending
`TypeError: 'NoneType' object is not subscriptable` at `engine.py:760` (the generate path that
would have used the loaded head returning nothing). The message now reads the window once more
before it is written (`runtimes._traceback_cause`) and quotes the interpreter's final exception
line and its innermost `File …, line N` frame; a window that holds no traceback — including one
that ends inside a block, or one with neither marker at all — says the narrower true thing,
"prints no line this check reads". The window is unchanged and so is the verdict: the log head
(`runtimes.LOG_HEAD_BYTES`), and a FAIL either way. The same branch serves the two `on` cells of
the streaming pin, so an `on` cell whose log holds a traceback gets it quoted too.

**How a depth cell reaches the MTP generate path at all — and the one way it would not.** MTP is
installed by patching `mlx_lm.server.stream_generate` (`serve.py:470-471`), which the **sequential**
path calls (`_serve_single`, `mlx_lm/server.py:976`) and the `BatchGenerator` path never does. The
two ways a request is routed sequentially are `_is_batchable` being false — which happens when
`args.seed is not None` (`server.py:685-686`) — or a KV-quant flag forcing it
(`force_sequential_for_kv_quant`, `serve.py:95-143`). **A depth cell therefore keeps the seed**:
`runtimes.Optiq.request_seed` overrides the harness's policy for exactly `mtp_depth` 1/2/3, and
every request of such a cell carries `SEED` (`measure._visit` asks once per visit and the row
records it as `request_seed`). A harness that stopped sending it would silently measure plain
autoregressive under an MTP header pin — which is why the exception exists.

**Every other OptiQ cell sends no seed at all** at temperature 0
(`runtimes.Runtime.request_seed` — the policy and its rationale are written there, once, and
switched on 2026-09-26). Omitting it is what puts an ordinary measured OptiQ request on the
**batched** path, which is what everyday clients use and therefore what the format and runtime
axes are about; the loop's own request body drops the key entirely when the value is `None`
(`transport.py:181-182`). `--max-concurrent 1` alone does *not* force the sequential path: it
sets `--decode-concurrency 1` (`cli.py:2937-2949`), and a batch of one still goes through
`BatchGenerator`.

| Add | Why |
|---|---|
| `--prompt-cache-bytes <N>` | Otherwise a RAM- and weights-derived value is injected (§7.3), differing across machines and not recorded in the start command. |
| `--prompt-cache-size <N>` | Same injection channel, and the injected value is 10 or 3 depending on whether the model can trim (§7.3). The run already pins it when it pins a cache state; pinning it always removes the model-shape dependence. |
| `--max-tokens <N>` | Otherwise OptiQ injects 32768, so a request that omits `max_tokens` is capped at 32768 rather than mlx-lm's 512 (§7.3). Recording the cap makes the cell's ceiling explicit. |
| `--decode-concurrency 1 --prompt-concurrency 1` | `--max-concurrent 1` already produces these, but recording the real flags removes the indirection. |
| Confirm `OPTIQ_*` unset | `OPTIQ_NO_THINK`, `OPTIQ_STREAM_PREFETCH`, `OPTIQ_FLASH_ATTN`, `OPTIQ_KERNELS`, `OPTIQ_DUMP_REQUESTS` etc. are not flags and would not show in the recorded command (§3.2). Capture `optiq config` output into the run artifact. |
| Record `generation_config.json` | Provenance: it is the file whose sampler recommendations the four flags in the start command now pre-empt (§7.2). Snapshot it like the Osaurus settings baseline. |
| Record the `quantization` block | Per-layer overrides mean the headline bit-width is not the format (§8.2). |

Not needed, and why: `--no-fused-kv` only matters with KV quantization (§7.7);
`--max-context auto` is bypassed by the explicit `off` (§7.6); `--context-scale 1.0` is a
no-op (§6.3) but is worth keeping as documentation of intent.

Also worth pinning in the observation, not the command: `--prompt-cache-size` stays at
upstream's 10 **only because the harness pins it (0 or 10) whenever it pins a cache state** —
left unpinned, OptiQ injects 10, or 3 on a non-trimmable hybrid (§7.3); and `mx.set_wired_limit`
raises the wired limit to the device maximum on every run (§2.3).

---

## 10. What could not be determined from static inspection

1. **End-to-end streaming shape.** Which deltas actually arrive, their timing, and the real
   TTFT. §5 is a code-path analysis with a probe specified; it is not a measurement.
2. **Whether `optiq serve` and `mlx_lm.server` differ in practice.** The patch stack is
   extensive; the static reading says the channels, `usage` block and sampler resolution are
   mlx-lm's, but the *timing* differences (streaming experts, MTP, fused SDPA) can only be
   measured.
3. **The `mtplx` server's reachability elsewhere.** `python -m mtplx.server.openai` cannot
   resolve in this install. Whether some other entry point provides the `mtplx` module (a
   `.pth`, a different install layout, an older/newer version) was not determined — only that
   *this* install cannot start it, and therefore `reasoning_content` is unreachable here.
4. **MLX's accepted `mode` strings.** OptiQ validates nothing; `nn.quantize`/`mx.quantize`
   decide. Not traced into the MLX core.
5. **The full `optiq/runtime/mtp/` tree** (~50 modules, vendored vLLM-Metal paged-KV runtime).
   Read where it bears on format detection, the `reasoning_content` question and §9.2's attach
   path (`attach`, `inject_mtp_support`, `_num_mtp_layers`, `expected_mtp_file`); the generation
   internals beneath those are not read, and no MTP cell has been run.
6. **`generation_config.json` for the artifacts this harness serves** — asked in an earlier
   revision and answered 2026-09-25 from the local HF cache: **all three cached OptiQ quants ship
   one.** LFM2.5-8B-A1B-OptiQ-4bit: `temperature 0.2`, `top_k 80`, `repetition_penalty 1.05`;
   Qwen3.5-4B-OptiQ-4bit and Qwen3.6-35B-A3B-OptiQ-4bit: `temperature 0.7`, `top_p 0.8`,
   `top_k 20`, `min_p 0.0`, `presence_penalty 1.5`. So the §7.2 read fires on every `optiq serve`
   of these artifacts and the four sampler flags in the start command are doing real work. Still
   open: the same check for any artifact added later, and the fact that the recommendation's
   *values* live in the artifact, not in the recorded command.
