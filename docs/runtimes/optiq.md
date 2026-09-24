# OptiQ (`mlx-optiq` 0.5.6) — capability and configuration reference

Static inspection. Nothing in this document was produced by starting the server, loading a
model, or sending a request. Where a claim depends on live behaviour rather than code, it is
marked **NEEDS PROBE** and the exact probe is given.

Sources, all read directly:

| Component | Version | Path |
|---|---|---|
| `mlx-optiq` | **0.5.6** | `/Users/jrazz/Dev/tools/mlx-optiq/.venv/lib/python3.12/site-packages/optiq` |
| `mlx-lm` (the actual HTTP server) | **0.31.3** | `/Users/jrazz/Dev/tools/mlx-optiq/.venv/lib/python3.12/site-packages/mlx_lm` |

Everything below is cited as `file:line` relative to
`/Users/jrazz/Dev/tools/mlx-optiq/.venv/lib/python3.12/site-packages/` unless stated.

**The single most important structural fact:** `optiq serve` is not a server. It is a stack of
~25 monkeypatches applied to `mlx_lm.server`, ending in an unconditional hand-off:

```
optiq/cli.py:3030    sys.argv = ["mlx_lm.server"] + argv_extra
optiq/cli.py:3031    from mlx_lm.server import main as mlx_main
optiq/cli.py:3032    mlx_main()
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

Registered by `mlx_optiq-0.5.6.dist-info/entry_points.txt`:

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

`.venv/bin` holds 68 scripts. Two categories matter:

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
(`openai.py:5465-5471`: `temperature 0.6`, `top_p 0.95`, `top_k 20`, `max_tokens 16384`,
`reasoning "auto"`).

It is launched as a subprocess by
`optiq/runtime/mtp/commands/public.py:5274-5276`:

```python
cmd = [
    sys.executable,
    "-m",
    "mtplx.server.openai",
```

**In this install that command cannot work.** `mlx_optiq-0.5.6.dist-info/top_level.txt` contains
only `optiq`, and:

```
$ .venv/bin/python3 -c "import importlib.util as u; print(u.find_spec('mtplx'))"
None
```

There is no `mtplx` package and no `.pth` providing it. `optiq/runtime/mtp/cli.py` is not wired
to any `optiq` subcommand either — the top-level command list is
`benchmark, cloud, cluster, code, config, convert, eval, kv-cache, lab, latency, lora,
prune-experts, serve` (`optiq/cli.py:18-55`), plus a hidden `game`.

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

Declared at `optiq/cli.py:2330-2461`; `context_settings={"ignore_unknown_options": True,
"allow_extra_args": True}` (`cli.py:2332`), which is what makes the forwarding in §2.3 possible.

| Flag | Default | Controls | Source |
|---|---|---|---|
| `--kv-bits INTEGER` | `None` (fp16) | Uniform KV cache quantization, 4 or 8 | `cli.py:2334` |
| `--kv-group-size INTEGER` | `64` | KV quant group size | `cli.py:2336` |
| `--quantized-kv-start INTEGER` | `0` | Token offset where KV quant begins | `cli.py:2337` |
| `--kv-config FILE` | `None` | Per-layer mixed-precision KV; **overrides `--kv-bits`** | `cli.py:2339` |
| `--adapter TEXT` (repeatable) | `()` | LoRA adapter(s), HF id or local dir; switches to mounted-LoRA mode | `cli.py:2342` |
| `--anthropic/--no-anthropic` | **on** | OpenAI **Anthropic** `/v1/messages` endpoint | `cli.py:2354` |
| `--responses/--no-responses` | **on** | OpenAI `/v1/responses` endpoint | `cli.py:2360` |
| `--context-scale FLOAT` | `1.0` | **Multiplies reported usage token counts** — see §6.3 | `cli.py:2366` |
| `--max-concurrent INTEGER` | `8` | Decode parallelism; also sets prompt-concurrency to `max(1, n//4)` | `cli.py:2374` |
| `--auth/--no-auth` | **on** | Requires `Bearer sk-optiq-*` **if a header is present** | `cli.py:2382` |
| `--mtp` | off | MTP speculative decoding via `OptiqEngine` | `cli.py:2386` |
| `--mtp-depth INTEGER` | `2` | Draft tokens per verify cycle | `cli.py:2391` |
| `--drafter TEXT` | `None` | Separate drafter model (γ=1 greedy); **mutually exclusive with `--mtp`** | `cli.py:2396` |
| `--no-fused-kv` | off | Opts out of the tight-RAM KV-quant path | `cli.py:2404` |
| `--stream-experts/--no-stream-experts` | `None` = **auto** | SSD expert streaming — see §7.1 | `cli.py:2418` |
| `--stream-experts-cache INTEGER` | `0` | LRU expert cache per projection | `cli.py:2427` |
| `--models-dir DIRECTORY` | `None` | Advertise local quants in `/v1/models`; **implies `--allow-model-switch`** | `cli.py:2432` |
| `--allow-model-switch/--single-model` | single | Whether a request's `model` can hot-swap the server | `cli.py:2439` |
| `--idle-timeout INTEGER` | `0` (off) | Unload model after N idle seconds | `cli.py:2447` |
| `--max-context TEXT` | `"auto"` | `auto` / integer hard cap / `off` | `cli.py:2454` |

Two defaults are worth stating twice because they are on by default and change the wire
surface: `--anthropic` and `--responses` both ship **enabled**.

### 2.3 Everything else is mlx-lm's

Unknown options land in `ctx.args` and are re-emitted verbatim as `mlx_lm.server`'s argv
(`cli.py:2571`, `cli.py:3030`). The real, authoritative flag set is therefore mlx_lm.server's
argparse, `mlx_lm/server.py:1751-1887`:

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
`--prompt-cache-bytes` uncapped.

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

`OPTIQ_HOME` relocates the state root (`settings.py:198-214`); both config files then move
under it. Every setting also has a canonical `OPTIQ_<NAME>` environment variable
(`settings.py:88-90`), and some have legacy aliases (`settings.py:285-289`).

**Neither config file exists on this machine** — there is no `~/.optiq/config.json` and no
`.optiq/` in this repository. Every setting below is therefore at its default for any run this
harness makes today. That is worth re-checking before publishing a table, because a stray
`~/.optiq/config.json` would silently move every number.

The whole registry is one tuple, `SETTINGS` at `optiq/settings.py:96-189`:

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
| `kv_debug` | `False` | Log KV rotation/quant decisions |
| `merge_debug` | `False` | Log batched rotating-cache merges |

`optiq config` prints every resolved value **and its source** (`settings.py:404-428`), which is
the intended way to record this in a run artifact.

### 3.2 Which settings have no command-line equivalent

**All of them.** `optiq serve` declares no flag that writes any setting in `SETTINGS`. The
settings are reachable only through `OPTIQ_*` environment variables or the two JSON files, and
the ones that touch the serving path are marked in bold above:

- `stream_prefetch` — read at `optiq/runtime/moe_stream.py:183`, off by default.
- `stream_scales_budget_gb` — `moe_stream.py:370`.
- `no_think` — `optiq/cli.py:2640-2642`; `OPTIQ_NO_THINK=1` installs a global patch forcing
  `enable_thinking=False` on every chat request (`optiq/no_think.py:37-45`). This one *does*
  have a per-request equivalent (`:no-think` suffix, §4.3) but no CLI flag.
- `anthropic_no_think` — `optiq/anthropic_shim.py:284-287`.
- `flash_attn`, `flash_attn_budget_gb`, `flash_block` — `optiq/ops/attention_patch.py:91-110`,
  `optiq/ops/flash_attention_tiled.py:56`.
- `fused_ce`, `fused_ce_budget_mb` — `optiq/lora/trainer.py:120-128`.
- `lowbit_search`, `lowbit_search_max_bits` — `optiq/core/lowbit.py:169-185`. These are the only
  settings with a CLI flag, and it is on `optiq convert` (`--low-bit-search`,
  `cli.py:1009`), not `serve`.

These are the ones that "silently decide what a cell measures": `OPTIQ_NO_THINK` alone changes
whether reasoning tokens exist at all, and `OPTIQ_FLASH_ATTN` changes the attention kernel on a
training path, not the serving path.

### 3.3 Three more hidden configuration surfaces

Not in `SETTINGS`, but read at serve time:

1. **`generation_config.json` in the model directory.** `optiq serve` reads it and injects
   sampler flags (§7.2). This is per-artifact configuration that no flag and no env var
   announces.
2. **`~/.optiq/`** as a state root, and `~/.cache/optiq/adapters` for adapters
   (`settings.py:180-182`).
3. **Cloud Boost config** — `optiq/cli.py:2875-2883` loads `optiq.code.config` and installs
   a `/boost` handler **unconditionally**, even with no API key. A `/boost` request is
   intercepted before it reaches the model (`serve.py:1729-1737`).

### 3.4 Adapters do not use mlx-lm's adapter route

`--adapter` does **not** forward `--adapter-path`. The comment at `optiq/cli.py:2600-2606` says
the upstream route "is a no-op on OptiQ's mixed-precision quantized base in some configs, so we
no longer use it." All adapters go through `install_multi_adapter` (`cli.py:2607-2608`), which
registers sidecars and gates a `ContextVar` per request.

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
| `adapters` (or `adapter`) | Selects a mounted LoRA adapter | `optiq/serve.py:1008` | `None` |

`structured.py` is installed unconditionally (`cli.py:2932-2935`) and **forces
`enable_thinking=False`** on any request carrying a constraint
(`structured.py:322-324`), so constrained requests never produce reasoning tokens.

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
(`cli.py:2691-2692`), and `install_variants` again afterwards (`cli.py:2958-2961`). Together
they make the `model` string carry control data:

| Suffix | Effect | Source |
|---|---|---|
| `:no-think` | `enable_thinking=False` | `no_think.py:79-84`; `variants.py:31` |
| `:nothink` | `enable_thinking=False` | `variants.py:32` |
| `:think` | `enable_thinking=True` | `no_think.py:79-84`; `variants.py:30` |
| `:precise` | **Sets `temperature = 0.0`** | `variants.py:33` |
| `:creative` | **Sets `temperature = 0.8, top_p = 0.95`** | `variants.py:34` |
| `:balanced` | **Sets `temperature = 0.4, top_p = 0.9`** | `variants.py:35` |

`precise` / `creative` / `balanced` overwrite the handler's sampler attributes for that request
(`variants.py:83-85`), so they beat both the body and the CLI. The harness uses
`:no-think` (`Optiq.model_id_candidates`) — which is sound, and is the variant whose text lands in
`delta.content` rather than `delta.reasoning` (see §5).

### 4.4 Accepted but ignored

These are traps: they parse cleanly and do nothing.

| Field | Reality | Evidence |
|---|---|---|
| `n` | Never read. Always one choice. | No `body.get("n")` in `mlx_lm/server.py`; grep across both packages finds none |
| `user` | Never read. | Same |
| `tool_choice: "none"` / `"auto"` | mlx-lm ignores `tool_choice`; OptiQ acts only on `"required"`/function form | `structured.py:89` states mlx-lm "ignores `tool_choice` entirely" |
| `role_mapping` | Only used on the no-chat-template fallback path | `server.py:558-559` |
| `logprobs` on OptiQ's replaced generators | Returns placeholder `0.0` | `serve.py:283-287` `_NullLogprobs`; used at `serve.py:378,631,770,1011` |
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
optiq/runtime/mtp/opencode.py
optiq/runtime/mtp/cli.py
optiq/runtime/mtp/commands/public.py
optiq/code/engine.py                   <- a CLIENT, reads either name
optiq/code/trace_writer.py
optiq/eval/backends.py
mlx_lm/chat_templates/deepseek_v32.py  <- a chat template string
```

Not one of those is the `mlx_lm.server` code path. This matters directly: the oMLX finding was
that oMLX streams **only** in `reasoning_content`
(`docs/research/2026-09-15-omlx-streams-in-the-reasoning-channel.md`). OptiQ does the opposite —
it streams in `reasoning` and never writes `reasoning_content`. **A harness that reads only
`reasoning_content` will see zero reasoning deltas from OptiQ and will conclude, wrongly, that
OptiQ emits no reasoning.** The two runtimes put the same information in differently-named
fields.

OptiQ's own client hedges for exactly this reason (`optiq/code/engine.py:233-234`):

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
graph-recompile reasons (`cli.py:2425`), which is prefill, not delta granularity.

### 5.3 No channel is mirrored

`reasoning` and `content` are fed by mutually exclusive states (`server.py:1460-1469`) and both
accumulators are reset after every emit (`server.py:1491-1493`). A single chunk cannot carry
both. The Anthropic and Responses shims keep them separate too
(`anthropic_shim.py:435-459`, `responses_shim.py:582-617`).

This is the opposite of oMLX, which mirrors the completed text into `content` at the end. **The
mirroring-dedupe logic the harness built for oMLX must not be applied blindly to OptiQ** — for
OptiQ, a `content` delta is real content.

Caveat: generator *replacements* change how tokens are produced, not the channel mapping.
`--mtp` (`serve.py:344-388`), assistant-drafter (`serve.py:717-794`) and diffusion
(`serve.py:1024-1148`) all yield per-token `GenerationResponse` objects; the diffusion path runs
the decode to completion and then replays token-by-token (`serve.py:1024-1148`), which would
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
patched since 0.5.6 and this document is stale.

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

Exactly four fields, the last only on a prefix-cache hit.

### 6.2 Reasoning is **not** separated

There is no `completion_tokens_details` and no `reasoning_tokens` anywhere in
`mlx_lm/server.py`. Reasoning tokens are counted, but folded into `completion_tokens`:

```
mlx_lm/server.py:1472                tokens.append(gen.token)      # every state
mlx_lm/server.py:1522                        len(tokens),          # -> completion_tokens
```

`prompt_tokens` is `len(ctx.prompt)` (`server.py:1533`) and excludes any model-generated
reasoning.

This is a direct blocker for `docs/interfaces.md`, which pins
`reasoning_tokens: int | None  # from usage.completion_tokens_details, if present`. For OptiQ it
is never present, so that field will always be `None` and `completion_tokens` will silently
include reasoning. **`completion_tokens` from OptiQ is not comparable to a content-only count.**

### 6.3 Reported usage is scaled by `--context-scale`

`optiq/runtime/context_scale.py:33-39`:

```python
for k in ("prompt_tokens", "completion_tokens"):
    ...
    u[k] = int(round(v * factor))
p, c = u.get("prompt_tokens"), u.get("completion_tokens")
    u["total_tokens"] = p + c
```

Installed only when `context_scale != 1.0` (`cli.py:2965-2968`). The harness passes
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
optiq/serve.py:381        prompt_tps=ev["prompt_tokens"] / max(ev["prefill_time_s"], 1e-6),
optiq/serve.py:766        elapsed = max(time.time() - t0, 1e-6)
optiq/serve.py:775        generation_tps=n_tokens / elapsed,
optiq/runtime/engine.py:753    "decode_tps": (n_generated + 1) / max(elapsed, 1e-6),
```

`max(elapsed, 1e-6)` converts a zero or negative interval into a denominator of `1e-6`, so
`n / 1e-6` — up to 10⁶ × the token count. **The absurd-rate generator is present; only the
field that would publish it is missing.** Anything that reads these objects (rather than the
HTTP `usage` block) inherits the trap.

The exact source quote the dispatch asked for, for the record:

```
optiq/serve.py:381:  prompt_tps=ev["prompt_tokens"] / max(ev["prefill_time_s"], 1e-6),
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
| `/v1/chat/completions` | real | real (incl. reasoning) | folded in |
| `/v1/messages`, non-stream | from `prompt_tokens` (`anthropic_shim.py:358-361`) | from `completion_tokens` | absent |
| `/v1/messages`, **streaming** | **hard-coded `0`** (`anthropic_shim.py:398`) | counts SSE content chunks (`anthropic_shim.py:460,484`) | **excluded** |
| `/v1/responses`, non-stream | from `prompt_tokens` | from `completion_tokens` | `max(1, len(reasoning_text.split()))` — **a word count** (`responses_shim.py:404`) |
| `/v1/responses`, streaming | from `prompt_tokens` or 0 (`responses_shim.py:573`) | counted per delta (`responses_shim.py:610`) | word count (`responses_shim.py:784-787`) |

The Anthropic streaming path bypasses `--context-scale` entirely (it never consumes the OpenAI
usage), and the Responses shim's `reasoning_tokens` is a **fabricated word count**, admitted in
its own comment at `responses_shim.py:401-403` ("Rough estimate — actual count is hidden inside
mlx-lm"). Neither endpoint should be used for token accounting.

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
calls out at `cli.py:3563-3566`:

> `should_stream()` compares against total RAM, so a 20 GB quant "fits" in 70% of 36 GB while
> 4 GB is actually free -- and the process is killed with no traceback, which reads as a crash
> rather than as running out of room.

So the heuristic has **both** failure directions: it turns streaming on when the model "fits"
by total RAM but not by available RAM (slow), and it leaves streaming off when total RAM is
large but the machine is busy (OOM).

Wiring: `install_streaming_experts` (`optiq/serve.py:1222-1305`) patches
`mlx_lm.server.ModelProvider._load`. The decision is `optiq/serve.py:1251-1253`:

```python
def _wants(mp: str) -> bool:
    return ((mode == "on" and is_streamable_moe(mp))
            or (mode == "auto" and should_stream(mp)))
```

`--stream-experts` maps `None → "auto"`, `True → "on"`, `False → "off"`
(`optiq/cli.py:2856-2857`), and `mode == "off"` returns before installing anything
(`serve.py:1239-1240`), so `--no-stream-experts` is a **complete** opt-out, not a partial one.

**Is `is_streamable_moe` even reached for the harness's `--no-stream-experts`?** No. Good.

### 7.2 **Sampler injection from `generation_config.json` — the one that fires for this harness**

`optiq/cli.py:2756-2763`:

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

`merge_into_argv` (`optiq/runtime/gen_config.py:103-148`) appends `--temp`, `--top-p`,
`--top-k`, `--min-p` for any recommended key **not already present in argv**:

```python
optiq/runtime/gen_config.py:141        already = any(a == flag or a.startswith(flag + "=") for a in out)
optiq/runtime/gen_config.py:142        if already:
optiq/runtime/gen_config.py:143            continue
optiq/runtime/gen_config.py:144        out += [flag, str(value)]
```

**This was the harness's "temperature 0" hazard, and four flags close it.**
`Optiq.start_command` passes `--temp 0 --top-p 1 --top-k 0 --min-p 0` explicitly, so every key
`merge_into_argv` can forward is already in argv, `already` is true for all of them, and the
injection is a no-op. The three that matter most are the ones the request body does not carry:
`measure._request` sends `temperature` and `seed` and nothing else, so an injected `--top-p`,
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
`temperature`, `top_p`, `top_k`, `min_p`, `repetition_penalty` (`gen_config.py:25`). With
`allow_hf_fetch=False` (the serve default) it is local-only.

### 7.3 `--prompt-cache-bytes` is injected

`optiq/cli.py:2713-2719` computes a budget and appends the flag unless already present:

```
optiq/cli.py:2713    pc_bytes = default_prompt_cache_bytes(_resolve_model_dir(model_arg))
optiq/cli.py:2715    argv_extra = inject_prompt_cache_bytes(argv_extra, pc_bytes)
```

`default_prompt_cache_bytes` (`optiq/lab/mlx_cleanup.py:81-107`) derives from **what is left
after the weights**, not total RAM:

```
optiq/lab/mlx_cleanup.py:104    free = total - weights
optiq/lab/mlx_cleanup.py:105    budget = int(free * PROMPT_CACHE_FREE_FRACTION)     # 0.25
optiq/lab/mlx_cleanup.py:106    capped = min(int(total * PROMPT_CACHE_FRACTION), budget)   # 0.15 of total
optiq/lab/mlx_cleanup.py:107    return max(MIN_PROMPT_CACHE_FLOOR, capped)         # floor 512 MiB
```

If the model dir cannot be resolved, it falls back to `max(2 GiB, 15% of RAM)`
(`mlx_cleanup.py:99-100`). The value is RAM-derived, so **it differs between machines** — a
36 GiB and a 64 GiB Mac run the same artifact with different cache budgets, and prefix-cache
hit rates are therefore not comparable across machines without recording this number.

`--prompt-cache-size` (upstream default 10) is **not** touched.

### 7.4 Concurrency is capped below upstream's default

`optiq/cli.py:2725-2737`. With the `--max-concurrent` default of `8`:

```
optiq/cli.py:2731            argv_extra += ["--decode-concurrency", str(int(max_concurrent))]
optiq/cli.py:2733            argv_extra += ["--prompt-concurrency", str(max(1, int(max_concurrent) // 4))]
```

So the effective values are decode 8 / prompt 2, against upstream's 32 / 8
(`mlx_lm/server.py:1856,1862`) — unless the caller passed the underlying flag, which wins
(`cli.py:2726-2729`). The harness passes `--max-concurrent 1`, giving decode 1 / prompt 1. Fine,
but note the number that matters is `--decode-concurrency`, which the harness does not record.

### 7.5 MLX reuse-pool cleanup on every request

`optiq/cli.py:2703-2707` installs a post-response hook:

```
optiq/cli.py:2703    cleanup_threshold = default_threshold_bytes()
optiq/cli.py:2704    install_server_cleanup(cleanup_threshold)
```

`default_threshold_bytes()` is `max(1 GiB, 10% of total RAM)`
(`optiq/lab/mlx_cleanup.py:76-78`). When MLX's buffer reuse pool exceeds it, the hook runs
`gc.collect()` then `mx.clear_cache()` (`mlx_cleanup.py:148-152`). The hook is installed
**unconditionally** on every `optiq serve` and is not exposed as a flag. It is RAM-derived, so
it fires at different points on different machines, and it costs a re-allocation from Metal when
it fires (`mlx_cleanup.py:16-18` estimates 10–100 ms).

### 7.6 Context cap `auto`

`--max-context auto` (the default) estimates a KV token cap and installs a rotating window
**only when the model's native context would not fit RAM** (`optiq/cli.py:2980-3024`). When it
fires it changes the KV cache class to `RotatingKVCache`, which changes long-context behaviour
and can change output. The harness passed `--max-context 8192` until 2026-09-16 and passes `off` since: an integer
cap rotates rather than refuses, and on Qwen3.5 / LFM2 it was a no-op because both define
`make_cache` (`docs/research/2026-09-16-prompt-length-context-limits.md`). Either way the auto
path is bypassed, which is correct and should stay.

### 7.7 Fused KV path is automatic when KV quantization is on

`optiq/cli.py:2532-2546`: with `--kv-bits` or `--kv-config` set and no `--no-fused-kv`, two
patches install automatically (streaming per-layer conversion + fused quantized SDPA). The
comment states the effect is a ~2x memory reduction at 32k on a 24 GB Mac
(`cli.py:2413-2415`). Not active for this harness (no KV quantization), but it means any future
KV-quant cell has a memory profile that differs from stock mlx-lm and must be recorded.

### 7.8 The sampling RNG fix

`optiq/cli.py:2927-2930` installs a thread-safe sampler, because "mlx-lm's compiled categorical
sampler freezes the RNG on the generation worker thread, so temperature/seed are ignored and
output is effectively greedy". This changes what `temperature`/`seed` do relative to stock
mlx-lm. It is a behavioural difference from the `mlxlm` runtime in this harness — the same
request body can produce different sampling behaviour on the two runtimes.

### 7.9 Installed unconditionally, for completeness

Each of these patches `mlx_lm.server` on every `optiq serve` run, with no flag:
tool-argument normalization (`cli.py:2506-2507`), EOS-terminated tool calls (`cli.py:2512-2513`),
rotating-cache merge fix (`cli.py:2520-2527`), message-shape `content: null` on non-streaming
messages (`cli.py:2869-2870`), Cloud Boost (`cli.py:2879-2880`), structured output
(`cli.py:2932-2935`), tool-call healing (`cli.py:2941-2944`), model variants
(`cli.py:2958-2961`), thinking variants (`cli.py:2691-2692`), single-model field policy
(`cli.py:2744-2749`), and a download-retry shim (`cli.py:2500-2501`).

`install_message_shape` is worth singling out: it adds `"content": None` to non-streaming
messages that produced only reasoning, and **deliberately does not touch `delta`**
(`serve.py:1325-1346`). Its docstring records that this was found when a live test read
`message["content"]` and got a `KeyError`.

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
| Sidecars | `optiq/mtp.safetensors`, `optiq/optiq_vision.safetensors` | `optiq/sidecar_layout.py:28-31` |
| MTP quant block | `mtplx_mtp_quantization` (`prequantized`, `policy`) | `optiq/runtime/mtp/artifacts.py:44-46` |
| Architecture | `model_type` (`diffusion_gemma`, `llada2_moe`, `dhara_ar`) | `optiq/models/diffusion.py:50`; `optiq/cli.py:2771` |

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
loader silently takes the resident path (`serve.py:1301-1302`). A failed streaming attempt is
also swallowed to a resident load with only a log line (`serve.py:1298-1300`). So
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
`/health` forever (`cli.py:2663-2684`, implementation `cli.py:2298-2328`). The docstring
records that mlx-lm's `/health` is hardcoded to 200 and never consults model state:

```
GET  /health              -> 200 {"status": "ok"}
POST /v1/chat/completions -> nothing, forever
```

Note this check is **local-only and never touches the network** (`cli.py:2301-2304`), so an
uncached repo id is not rejected. It catches an on-disk directory with no `.safetensors` and no
weight index.

---

## 9. What this harness should pin, and why

The harness currently passes (`Optiq.start_command`):
`--model`, `--host`, `--port`, `--no-anthropic`, `--no-responses`, `--no-auth`,
`--max-context off` (8192 before 2026-09-16), `--max-concurrent 1`, `--idle-timeout 0`,
`--context-scale 1.0`, `--no-stream-experts`, `--temp 0 --top-p 1 --top-k 0 --min-p 0`, and
`--prompt-cache-size 0` or `10` when the run pins a cache state.

**Done since this document was written:** the four sampler flags, which this table used to list
as its first priority, are now in the command — every key `merge_into_argv` forwards is already
in argv, so nothing is injected (§7.2).

| Add | Why |
|---|---|
| `--prompt-cache-bytes <N>` | Otherwise a RAM- and weights-derived value is injected (§7.3), differing across machines and not recorded in the start command. |
| `--decode-concurrency 1 --prompt-concurrency 1` | `--max-concurrent 1` already produces these, but recording the real flags removes the indirection. |
| Confirm `OPTIQ_*` unset | `OPTIQ_NO_THINK`, `OPTIQ_STREAM_PREFETCH`, `OPTIQ_FLASH_ATTN` etc. are not flags and would not show in the recorded command (§3.2). Capture `optiq config` output into the run artifact. |
| Record `generation_config.json` | Provenance: it is the file whose sampler recommendations the four flags in the start command now pre-empt (§7.2). Snapshot it like the Osaurus settings baseline. |
| Record the `quantization` block | Per-layer overrides mean the headline bit-width is not the format (§8.2). |

Not needed, and why: `--no-fused-kv` only matters with KV quantization (§7.7);
`--max-context auto` is bypassed by the explicit `off` (§7.6); `--context-scale 1.0` is a
no-op (§6.3) but is worth keeping as documentation of intent.

Also worth pinning in the observation, not the command: `--prompt-cache-size` stays at
upstream's 10, and `mx.set_wired_limit` raises the wired limit to the device maximum on every
run (§2.3).

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
   Read only where it bears on format detection and the `reasoning_content` question.
6. **Whether any `generation_config.json` exists for the artifacts this harness serves.** Not
   checked — but §7.2 means it should be, before the next published run.
