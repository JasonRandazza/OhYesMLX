# Osaurus 0.25.3 — capability and configuration reference

Scope: Osaurus `0.25.3` (build `0.25.3`), bundle `com.dinoki.osaurus`, as installed on this
host on 2026-09-15. Everything below is static inspection. No server was started, no model
was loaded, and no request was sent to produce this document.

**Read §0.1 before you touch this runtime from a script.** `--help` is not intercepted by
most Osaurus subcommands, and running `osaurus serve --help` starts a server.

---

## 0. Method, and the one assumption that did not hold

The dispatch's method section assumed these runtimes bundle readable Python, so that "the
shipped source is the authority when it disagrees with the docs". **Osaurus does not ship
Python.** It is a native Swift application — the bundle links `mlx-swift`, `swift-nio`,
`swift-crypto`, `SwiftProtobuf`, and `Sentry`. The only `.py` file anywhere in the bundle is
`Resources/SwiftMath_SwiftMath.bundle/Contents/Resources/mathFonts.bundle/math_table_to_plist.py`,
a vendored font-generation script with no runtime role.

There is therefore **no readable source** to cite. The shipped authority is two Mach-O
executables containing compiled Swift. What survives compilation, and is cited below:

| Evidence class | What it is | How it is cited |
|---|---|---|
| **E1 — CLI** | Captured `--help` / usage text | Excerpt plus the exact command |
| **E2 — settings file** | A JSON/YAML/plist document on disk | `path:key` and the observed value |
| **E3 — binary string** | A literal embedded in a shipped Mach-O | `<binary> @ <decimal byte offset>` |
| **E4 — observed** | Something this session actually did | Stated with its timestamp |

Reproduce every E3 citation with:

```sh
strings -a -n 4 -t d /Applications/osaurus.app/Contents/MacOS/osaurus | grep -F '<literal>'
strings -a -n 4 -t d /Applications/osaurus.app/Contents/Helpers/osaurus | grep -F '<literal>'
```

`G:` below means `Contents/MacOS/osaurus` (the GUI app, 125,583,952 bytes) and `H:` means
`Contents/Helpers/osaurus` (the CLI, 25,014,976 bytes).

**Absence of a string is weaker evidence than presence of one**, and is flagged wherever it
carries a claim. A string table shows that a symbol, key, or message exists; it cannot show
control flow. Where a question is about *behaviour* rather than *surface*, this document says
so instead of guessing — most importantly in §5.

---

## 0.1 DANGER — `--help` is not a read-only flag on this runtime

This session ran `--help` against every subcommand, on the dispatch's instruction. On
**most** Osaurus subcommands an unrecognised flag is not an error: the command runs, and
`--help` is consumed as an ordinary operand or silently dropped. Observed 2026-09-15 at
11:44.

| Command | What it actually did |
|---|---|
| `osaurus serve --help` | **Started the server.** Printed `listening on http://127.0.0.1:1337` |
| `osaurus stop --help` | **Stopped the running server.** Printed `stopped` |
| `osaurus run --help` | **Started an interactive chat session** with model id `--help` |
| `osaurus pull --help` | **Attempted a Hugging Face download** of `--help`, and created a directory `~/.osaurus/models/--help` |
| `osaurus show --help` | `Error: Model not found: --help` |
| `osaurus list --help` | Listed models (flag ignored) |
| `osaurus status --help` | Printed `stopped` |
| `osaurus version --help` | Printed `Osaurus 0.25.3 (0.25.3)` |
| `osaurus bench --help` | Refused: `Unknown option: --help` + usage |
| `osaurus doctor --help` | Refused: `osaurus doctor: unknown argument '--help'` + usage |
| `osaurus mcp --help` | Printed usage (intercepted) |

Only `mcp`, `doctor`, and `bench` validate their arguments. Everything else executes.

**Remediation performed.** The server this session started was stopped and port 1337
verified free; the app process this session spawned (PID 93777, 910 MB phys_footprint) was
terminated; the `~/.osaurus/models/--help` directory this session created was removed and
`~/.osaurus/models` (which did not exist before, and was created by the failed pull) was
removed with it. The pre-existing app process (PID 92460, started 10:53:52, before this
session) was left running and untouched.

**Operational rule for this project:** never invoke `--help`, and never rely on an
unrecognised flag being rejected. Read the usage text from a captured copy, or from the
string table, and never from the binary itself.

---

## 1. Entry points

### 1.1 What is on `PATH`

| Path | Type | Size | Role |
|---|---|---|---|
| `/Users/jrazz/.local/bin/osaurus` | **symlink** → `/Applications/osaurus.app/Contents/Helpers/osaurus` | — | The CLI, E4 |
| `/Applications/osaurus.app/Contents/Helpers/osaurus` | Mach-O 64-bit executable arm64 | 25,014,976 B | The CLI implementation |
| `/Applications/osaurus.app/Contents/MacOS/osaurus` | Mach-O 64-bit executable arm64 | 125,583,952 B | The GUI app; **this is where the runtime lives** |

`CFBundleExecutable` is `osaurus` and `LSUIElement` is `true`, so the main app runs as a
menu-bar accessory with no dock icon (`Contents/Info.plist`).

### 1.2 The CLI is a thin client, not the server

The CLI does not implement inference. `osaurus serve` was observed (E4) to launch

```
/Applications/osaurus.app/Contents/MacOS/osaurus --launched-by-cli
```

and then report `listening on http://127.0.0.1:1337`. The literal `--launched-by-cli` is at
`H:8685856`. Every subcommand that reports runtime state is a client of the GUI app: the
`mcp` help text says so explicitly — *"Runs an MCP stdio server that proxies tool discovery
and calls to the local Osaurus HTTP server"* (E1).

**Consequence for measurement:** anything the CLI reports about the model, the cache, or
timings is the GUI process's answer, not the CLI's own observation.

### 1.3 The symlink is safe — resolution is not self-relative

The dispatch asked specifically whether a console script resolves anything relative to its
own location, which a `~/.local/bin` symlink would break. **Osaurus does not.** There is no
`Contents/Helpers`-relative or `executableURL`-relative lookup in the CLI's string table.

Instead the CLI locates the app by absolute path and by LaunchServices:

| Literal | Offset |
|---|---|
| `/Applications/Osaurus.app` | `H:8685792` |
| `/Applications/osaurus.app` | `H:8685792` (adjacent; see reproduce command) |
| `kMDItemCFBundleIdentifier == 'com.dinoki.osaurus'` | grep `com.dinoki.osaurus` in `H` |
| `com.dinoki.osaurus.control.ui` | grep in `H` |
| `brew install --cask osaurus` (fallback message) | grep in `H` |

So the `~/.local/bin/osaurus` symlink is safe; so is invoking either absolute path directly.
Note the **capitalisation hazard**: the CLI searches for *both* `/Applications/Osaurus.app`
and `/Applications/osaurus.app`. On a case-insensitive HFS+/APFS volume these resolve to the
same bundle, but on a case-sensitive volume only one will exist. The doctor's
`duplicateBundles` verdict exists for the case where both are genuinely installed.

### 1.4 Other executables shipped in the bundle

| Path | Note |
|---|---|
| `Contents/MacOS/osaurus` | The GUI/runtime. Spawned by the CLI. |
| `Contents/Helpers/osaurus` | The CLI. |
| `Contents/Frameworks/Sparkle.framework/Versions/B/Autoupdate` | Sparkle updater helper |
| `Contents/Frameworks/Sparkle.framework/Versions/B/Updater.app` | Sparkle updater UI |
| `Contents/Frameworks/Sentry.framework/Versions/A/Sentry` | Crash reporting dylib |
| `Contents/Frameworks/libswiftCompatibilitySpan.dylib` | Swift runtime shim |

The bundle ships a Linux kernel image at `Contents/Resources/SandboxRuntime/vmlinux`
(18,815,488 B) with `vmlinux.provenance.json`. This is the container sandbox runtime, not
the MLX inference path, and it does not participate in a serving cell. Noted because a naive
"what does this bundle contain" scan will find it and mistake it for the model runtime.

`SUEnableAutomaticChecks` is `true` and `SUFeedURL` is
`https://osaurus-ai.github.io/osaurus/appcast.xml` (`Contents/Info.plist`). **Sparkle can
update the app underneath a running benchmark.** For a measured cell, automatic update
checks are a version-drift hazard independent of any setting this document tracks.

---

## 2. Command-line surface

Captured from the CLI's own top-level help (E1) plus the no-argument usage paths for the
subcommand groups. This is the complete documented surface.

### 2.1 Top-level

| Command | Flags | Defaults / notes |
|---|---|---|
| `serve` | `[--port N] [--expose] [--yes\|-y] [--supervise] [--interval N]` | Starts the server, `localhost` only by default. `--expose` triggers a warning prompt unless `--yes`. `--supervise` runs a keep-alive loop, probe every `--interval` seconds, **default 15**, intended for a launchd `KeepAlive` LaunchAgent. |
| `stop` | — | Stops the server. |
| `status` | — | Prints `running (port N)` or `stopped`. |
| `mcp` | `[--access-key KEY]` `[--tools PATTERNS]` | MCP stdio server proxying to local HTTP. `--tools` is comma-separated, `*` suffix matches by prefix. |
| `version` | also `--version`, `-v` | `Osaurus 0.25.3 (0.25.3)` |
| `doctor` | `[--port N] [--json] [--redact] [--verify-signatures]` | Diagnoses CLI/app skew, duplicate bundles, server startup, model storage. Signature checks are opt-in because they are slow. `--port` domain is `1...65535`. |
| `list` | — | Lists available model IDs. |
| `show <model_id>` | — | Prints model metadata. |
| `pull <model_id>` | — | Downloads from Hugging Face. |
| `run <model_id>` | — | Interactive chat. |
| `bench` | `[--model <id>] [--prompt-tokens 1024,8192] [--max-tokens 128] [--runs 3] [--json <path>] [--port N]` | See §2.3. |
| `bench --tune-prefill` | `[--model <id>] [--candidates 512,1024,2048,4096] [--prompt-tokens 8192] [--runs 3]` | Per-model prefill step tuning. See §7.3. |
| `ui` | — | Shows the menu-bar popover. |

### 2.2 Subcommand groups

| Group | Subcommands / flags |
|---|---|
| `tools` | `list`, `install <plugin_id\|url-or-path>`, `search <query>`, `outdated`, `upgrade`, `uninstall <tool_name>`, `verify`, `create <name> [--language swift\|rust]`, `package <plugin_id> <version> [dylib_path]`, `reload`, `rollback <plugin_id>`, `dev <plugin_id> [--web-proxy <url>]`, `doctor`, `reset` |
| `manifest` | `extract <dylib>`, `validate <manifest.json>` |
| `bundle` | `load <path.mcpb> [--name "Display Name"]` |
| `config` | `export [-o file] [--format yaml\|json]`, `schema [--format yaml\|json]`, `plan <file> [--prune]`, `apply <file> [--prune] [--yes]` |
| `coord` | `[--root PATH]`, then `init`, `status [--json]`, `feature-flags list\|get\|set`, `lock list\|acquire\|release\|reap` |

`config apply` exit codes documented in its own help: `0` fully applied, `1` a change failed
or was cancelled, `3` applied but a step must be finished in the Osaurus app.

### 2.3 `osaurus bench` — the only built-in measurement path

```
Usage: osaurus bench [--model <id>] [--prompt-tokens 1024,8192]
                     [--max-tokens 128] [--runs 3] [--json <path>] [--port N]
       osaurus bench --tune-prefill [--model <id>] [--candidates 512,1024,2048,4096]
                     [--prompt-tokens 8192] [--runs 3]
```

Its help states it *"Requires a running server"* and reports *"uncached/cached TTFT, prefill
tok/s, and decode tok/s per prompt size as JSON"*, tagged with hardware info.

The bench JSON key set, from the CLI's own Codable layout (`H`, contiguous run around
`ttftMs`, `decodeTps`, `prefillTps`): `ttftMs`, `decodeTps`, `prefillTps`, `promptTokens`,
`completionTokens`, `noContent`, `noUsage`, `model`, `maxTokens`, `jsonPath`, `tunePrefill`,
`tuneCandidates`.

Two of those deserve attention. `noUsage` (`H:9181360`) and `noContent` (`G:97428200`) are
**the bench explicitly detecting that the server returned no usage block, or no content** —
i.e. upstream has already anticipated both failure modes and records them rather than
silently reporting a number. Your own harness should treat a missing usage block as a
FAIL-with-reason, not as zero tokens.

### 2.4 What the command line cannot express

This is the defining property of this runtime, and the reason this document exists:

- **There is no model selector on `serve`.** `osaurus serve` takes a port, an exposure
  flag, a confirmation flag, a supervise flag, and an interval. Nothing else. Which model
  is measured is decided per-request by the `model` field, or by whatever happens to be
  resident. (Documented surface only — I did not test for undocumented flags, because
  testing them would run the server.)
- **There is no tuning flag of any kind** — no cache switch, no KV size, no thread count,
  no batch size, no stream interval. Every one of those is a settings key (§3).

---

## 3. Settings surface beyond the command line

There are **three** distinct settings surfaces, and only the first is under `~/.osaurus/`.

### 3.1 `~/.osaurus/config/` — the primary settings directory

23 documents. Those relevant to measurement:

| File | Relevance |
|---|---|
| `server-runtime.json` | **The runtime settings.** Everything in §3.2. |
| `server.json` | **Host/server settings.** Threads, RAM thresholds, eviction, idle residency, request limits. |
| `chat.json` | Chat defaults that reach inference: `contextLength`, `warmModelsOnLoad`, `coreModelName`, `maxToolAttempts`. |
| `agent-delegation.json` | `ramSafetyPreflightEnabled`, spawn budgets, spawnable models. Can unload the chat model mid-run. |
| `model-exposure.json` | `overrides` map controlling which model ids are visible. |
| `sandbox.json` | Container sandbox (`autoStart`, `cpus`, `memoryGB`). Not the MLX path. |
| `privacy-filter.json`, `relay.json`, `browser.json`, `memory.json`, `tools.json`, `default-agent.json`, `channel-write-kill-switch.json` | Not measurement-relevant for a serving cell. |

Migration markers present: `.server-runtime-legacy-concurrency-migrated`,
`.server-runtime-memory-safety-cache-defaults-v4-migrated`,
`.server-runtime-paged-cache-default-off-v3-migrated`, `tied-head-q6-default-migrated.marker`,
`diffusion-defaults-migrated.marker`. These record that defaults were rewritten on upgrade —
**the same key can mean different things across versions**, which matters when a baseline
file outlives an app update.

### 3.2 `server-runtime.json` — observed values on this host

Every leaf, with the value actually on disk (E2) and the validation string that proves the
key is validated (E3, `G`).

| Key | Value here | Evidence / validated domain |
|---|---|---|
| `schemaVersion` | `3` | — |
| `cache.blockDisk.enabled` | `true` | — |
| `cache.blockDisk.maxSizePercent` | `10` | `cache.blockDisk.maxSizeGB` — "Block disk L2 cache size must be positive." |
| `cache.defaultMaxKVSize` | `65536` | `cache.defaultMaxKVSize` — "Default max KV size must be positive." |
| `cache.enableSSMReDerive` | `true` | — |
| `cache.legacyDisk.enabled` | `false` | "Legacy disk cache cannot run at the same time as paged KV cache. Use block disk L2 for paged cache persistence." |
| `cache.liveKVCodec` | `engine_selected` | enum `engine_selected` (\| `turboquant`); "TurboQuant KV requires explicit key and value bit widths." |
| `cache.longPromptMultiplier` | `2` | "Long-prompt multiplier must be positive." |
| `cache.pagedKV.enabled` | `false` | — |
| `cache.prefix.enabled` | `true` | — |
| `cache.prefix.legacyEntryCountCache` | `false` | — |
| `cache.storedKVCodec` | `auto` | — |
| `concurrency.continuousBatching` | `true` | "Continuous batching is off, so prefix/paged/block-disk cache reuse will be limited or disabled." |
| `concurrency.maxConcurrentSequences` | `1` | "Max concurrent sequences must be positive." |
| `concurrency.smeltMode` | `disabled` | enum `engineSelected` \| `disabled` \| `flashMoE` \| `ssdStreaming` |
| `generation.diffusionMaxDenoisingSteps` | `16` | "Diffusion budgets below 12 steps measurably break coherency on diffusiongemma-26B-A4B (8 steps produces word-salad spans)." |
| `generation.streamInterval` | `1` | "Stream interval must be at least 1." **See §5.** |
| `memorySafety.allowExperimentalMLXPress` | `false` | — |
| `memorySafety.failClosedWhenEstimateUnknown` | `false` | — |
| `memorySafety.mode` | `safe_auto` | enum `balanced` \| `safe_auto` \| `strict` \| `diagnosticDangerous` |
| `memorySafety.slider` | `2` | — |
| `mtp.acceptedTokensOnlyEnterBaseCache` | `true` | — |
| `mtp.keepDraftCacheSeparate` | `true` | — |
| `mtp.mode` | `auto` | enum includes `force_on`, `force_off`, `speculative`, `blocked` |
| `multimodal.enableAudio` | `true` | — |
| `multimodal.enableVideo` | `true` | — |
| `multimodal.requireMediaSaltForCache` | `true` | "Media salt is required when any prompt or KV cache reuse tier is enabled." |
| `multimodal.vlmMode` | `auto` | enum `forceOff` \| `forceOn` \| `auto` |
| `network.corsOrigins` | `["*"]` | — |
| `network.host` | `0.0.0.0` | "Server host cannot be empty." |
| `network.logLevel` | `info` | — |
| `network.port` | `1337` | "Server port must be between 1 and 65535." |
| `performance.compiledDecode` | `false` | — |
| `performance.deepseekV4ActivationQAT` | `false` | — |
| `performance.tiedHeadCodec` | `q6` | — |
| `power.autoSleepEnabled` | `false` | — |
| `power.jitLoad` | `true` | — |
| `power.wakeOnRequest` | `true` | — |
| `tools.enableAutoToolChoice` | `false` | — |

### 3.3 `server-runtime.json` — validated keys absent from this host's file

Absent keys fall back to compiled defaults (see §9.1), but they are live: the binary
validates them and the config-export key list enumerates them. Present in the schema:

`network`: `apiKey`, `servedModelName`, `rateLimitRequestsPerMinute`, `timeoutSeconds`
(`network.timeoutSeconds` — "Timeout must be positive. Use nil for no timeout.").
`concurrency`: **`prefillBatchSize`, `prefillStepSize`, `completionBatchSize`** — each
validated positive (`concurrency.prefillStepSize` — "Prefill step size must be positive.").
`cache`: `turboQuantKeyBits`, `turboQuantValueBits` (each "must be between 2 and 8"),
`cache.prefix.memoryLimitMB`, `cache.prefix.memoryPercent` ("greater than 0 and at most
100"), `cache.prefix.ttlMinutes`, `cache.pagedKV.blockSize`, `cache.pagedKV.maxBlocks`,
`cache.legacyDisk.maxSizeGB`.
`performance`: `fp16Passthrough` (config key `fp16_passthrough`).
`power`: `lightSleepAfterSeconds`, `deepSleepAfterSeconds` ("Deep sleep must be later than
light sleep.").
`generation`: `temperature` ("cannot be negative"), `repetitionPenalty` ("must be
positive"), `maxTokens`.
`tools`: `mcpConfigFile`, `toolParserOverride`, `reasoningParserOverride`,
`customChatTemplate`.
`mtp`: `draftTokenLimit`, `explicitDepth` ("must be 1, 2, or 3"), `dflash2DrafterPath`,
`dflash2BlockSize`.
`memorySafety`: `customPhysicalMemoryFraction` ("greater than 0 and at most 1"),
`customAllocatorCacheBytes`, `customDefaultMaxKVSize`, `customMaxConcurrentSequences`.

### 3.4 `server.json` — the second settings file, same directory

| Key | Value here | Relevance |
|---|---|---|
| `numberOfThreads` | `12` | CPU thread count — a real throughput knob with no CLI flag |
| `modelLoadRAMSoftThreshold` | `0.8` | Load refused/degraded past this fraction |
| `modelLoadRAMHardThreshold` | `0.9` | Hard refusal bound |
| `modelEvictionPolicy` | `"Strict (One Model)"` | **Enforces single residency** |
| `modelIdleResidencyPolicy.mode` | `after_seconds` | Unload trigger |
| `modelIdleResidencyPolicy.seconds` | `900` | Unloads the model 15 min after last use |
| `_modelIdleResidencyPolicyVersion` | `1` | |
| `backlog` | `256` | Listen backlog |
| `genTopP` | `1` | **A sampling default that never appears in a request** |
| `maxRequestBodyBytes` | `33554432` | |
| `maxPairingBodyBytes` | `65536` | |
| `exposeToNetwork` | `false` | |
| `port` | `1337` | Duplicates `network.port`; both are `1337` here |
| `allowedOrigins` | `[]` | |
| `startAtLogin` | `true` | `false` — relevant to whether a cell can assume a clean start |
| `appearanceMode`, `fontSizeMultiplier`, `hideDockIcon` | `system`, `1`, `false` | UI only; correctly not tracked |

**`genTopP: 1`** is worth calling out: a top-p default applied by the host, invisible to the
request. Per AGENTS.md the harness pins `top_p` per request; if it ever relies on the host
default instead, that default lives here.

### 3.5 `chat.json` — settings that reach inference

| Key | Value here | Relevance |
|---|---|---|
| `warmModelsOnLoad` | `true` | **Loads a model into memory at app start, outside any cell** |
| `contextLength` | `128000` | Default context |
| `coreModelName` | `foundation` | Default chat model |
| `disableTools` | `false` | Tool schemas in the prompt change prefill length |
| `maxToolAttempts` | `30` | |
| `systemPrompt` | `""` | |
| `autoGenerateChatTitles` | `true` | **Queues a second inference call after the first** |
| `compactionModelName` / `compactionModelProvider` | `nemotron-3-ultra-free` / `opencode` | Compaction is remote, but it fires on a long session |
| `enableClipboardMonitoring` | `true` | |
| `hotkey.*` | `⌘;` | UI only |

### 3.6 `~/Library/Preferences/com.dinoki.osaurus.plist` — the surface nothing looks at

This is the third surface, and **the one `ohyesmlx/osaurus_settings.py` cannot see at all**.

Decoded from the plist (E2; key names are `model_options_<modelID>`):

| Key | Decoded value |
|---|---|
| `model_options_OsaurusAI/Ornith-1.0-35B-JANG_4M` | `{"version":1,"options":{"disableThinking":{"bool":{"_0":true}}}}` |
| `model_options_OsaurusAI/Nanbeige4.2-3B-JANG_6M` | `disableThinking` = **true** |
| `model_options_OsaurusAI/Qwen3.6-35B-A3B-MXFP4-MTP` | `disableThinking` = **true** |
| `model_options_OsaurusAI/Bonsai-27b-Ternary-JANG` | `disableThinking` = false |
| `model_options_OsaurusAI/Holo3-35B-A3B-JANGTQ4` | `disableThinking` = false |
| `model_options_OsaurusAI/Laguna-XS.2-JANGTQ2` | `disableThinking` = false |
| `model_options_OsaurusAI/Ling-2.6-flash-JANGTQ` | `disableThinking` = false |
| `model_options_OsaurusAI/Ornith-1.5-9B-JANG_6D` | `disableThinking` = false |
| `model_options_OsaurusAI/Raptor-v0.5-8B-A1B-JANG_6M` | `disableThinking` = false |
| `model_options_OsaurusAI/gemma-4-12B-it-JANG_4M` | `disableThinking` = false |
| `model_options_OsaurusAI/gemma-4-12B-it-qat-JANG_4M` | `disableThinking` = false |
| `model_options_openai-chatgpt/gpt-5.6-luna` | `reasoningEffort` = `"high"` |
| `ExternalModelCustomHFCachePath` | `""` |
| `ExternalModelImportHFCache` | `1` |
| `ExternalModelImportLMStudio` | `1` |
| `NSOSPLastRootDirectory` | 760-byte security-scoped bookmark — **the model root** |

**`disableThinking` is a per-model switch that decides whether the measured model emits
reasoning tokens at all.** It is set per model, it lives in the app's preference plist, it
appears in no start command and in no file under `~/.osaurus/config`, and on this host it is
**on** for `Ornith-1.0-35B-JANG_4M`, `Nanbeige4.2-3B-JANG_6M`, and
`Qwen3.6-35B-A3B-MXFP4-MTP`. Two cells that differ only in which model they name can differ
by the entire reasoning token count, and nothing in the artifact would say why.

`NSOSPLastRootDirectory` is why the doctor's `modelRootSource` enum contains
`ModelDirectoryBookmark`. The model root is a bookmark, not a path string, so it is not
readable by grepping config JSON.

### 3.7 Settings with **no** command-line equivalent

Essentially all of them. The only settings the command line can express are the port
(`--port`) and network exposure (`--expose`) on `serve`, and `doctor`/`bench`'s own flags.
There is no flag for cache, KV, threads, batching, memory safety, MTP, stream interval, or
sampling defaults. §2.4.

---

## 4. Per-request API fields

### 4.1 Endpoints

From the GUI binary's route literals (E3): `/health`, `/models`, `/v1/models`,
`/chat/completions`, `/v1/chat/completions`, `/v1/completions`, `/responses`, `/embeddings`,
`/v1/embeddings`, `/v1/mcp`, `/v1/search`, `/v1/web/search`, `/v1/news/search`,
`/v1/audio/speech`, `/v1/audio/transcriptions`, `/v1/images/generations`,
`/v1/videos/generations`, `/v1/videos/jobs/`, `/v1/media/images/generations`,
`/v1/media/videos/jobs`, `/v1/vm`, and admin routes `/admin/config`,
`/admin/config/export`, `/admin/config/plan`, `/admin/config/apply`,
`/admin/config/schema`, `/admin/runtime-settings`, `/admin/generation-settings`,
`/admin/cache-stats`.

Three of those are unusual and useful: **`/admin/runtime-settings`**,
**`/admin/generation-settings`**, and **`/admin/cache-stats`** expose and presumably mutate
the settings in §3.2 over HTTP. I did not determine their methods or bodies statically — a
string table gives route paths, not verbs. They are worth a live probe, because a settings
surface reachable over HTTP means the file baseline in `osaurus_settings.py` can be
contradicted at runtime while the file still reads clean.

### 4.2 Request fields beyond the OpenAI standard set

From the request DTO key layout (E3, contiguous run at `G:97406826` onward). Standard
OpenAI fields are omitted; these are the additions.

| Field | Note |
|---|---|
| `modelOptions` | Per-request model option bag — the request-side twin of §3.6 |
| `enable_thinking` | Toggles reasoning for this request |
| `reasoning_effort` | Reasoning budget selector |
| `session_id` | Server-side session affinity |
| `ttftTrace` | **Asks the server to report TTFT** — a measurement hook built into the API |
| `turnId` | Correlates a turn across SSE frames |
| `idempotencyKey` | |
| `warmupPrefill` | **Prefill a prompt without producing output** — a cache-warmer |
| `cacheStableSystemPrefix` | Marks the system prefix as stable so it can be cached |
| `backgroundModelLoad` | Load the model asynchronously |
| `preserveExistingResidencyOwner` | Keep the current model resident; do not evict for this request |
| `samplingParametersAreImplicit` | Declares that sampling params were defaulted, not supplied |
| `isAgentRequest` | |
| `runAsRemoteAgent`, `remoteAgentLogModel`, `remoteAgentProviderId` | Route to a remote provider |
| `claudeCodeOptions`, `suppressProgressUI` | Client-integration fields |
| `alignmentRepairModel` | |

`stream_options` with `include_usage` (`G:97407541`) is present, so **usage can be requested
in the final streaming frame** — the standard mechanism, and the one a TTFT/ITL harness
needs.

`osaurus_prefill` (`G:97407749`) appears adjacent to the response `usage` object, suggesting
the response carries a server-side prefill annotation. I could not establish its type or
semantics from the string table.

### 4.3 Response fields beyond the standard set

`reasoning_content`, `reasoning_item_id`, `reasoning_encrypted`, `responses_output_items`,
`summaries`, `prefix_hash`, `system_fingerprint`, `osaurus_prefill`, `refusal`.
`reasoning_encrypted` is notable — reasoning can arrive encrypted rather than in clear text.

The OpenResponses (`/responses`) event vocabulary is present in full: `response.created`,
`response.in_progress`, `response.output_item.added`, `response.content_part.added`,
**`response.output_text.delta`**, `response.output_text.done`,
**`response.reasoning_summary_text.delta`**, `response.reasoning_summary_text.done`,
`response.function_call_arguments.delta`, `response.function_call_arguments.done`,
`response.output_item.done`, `response.completed`. The `.delta` events are named
`delta`, which is the same naming Osaurus uses elsewhere for incremental emission.

---

## 5. Streaming behaviour

**This section could not be measured, and that is the honest headline.** The dispatch
requires streaming behaviour "measured, not inferred" — but it also forbids the only action
that would measure it (start the server, send a request). Under static inspection I can
establish the *structure* of the streaming path and the *exact setting that governs
granularity*, and I can name precisely what remains unproven. I have kept the two separate.

### 5.1 Channel separation exists (established)

| Fact | Evidence |
|---|---|
| Content and reasoning deltas are **counted separately** | `[Osaurus][UI] Stream consumption completed: contentDeltas=` and ` reasoningDeltas=` — `G:105217440`, `G:104904192` |
| A dedicated delta processor exists | `OsaurusCore/StreamingDeltaProcessor.swift`; symbol `_TtC11OsaurusCore23StreamingDeltaProcessor` |
| The SSE object is `chat.completion.chunk` | `G:104530336` |
| The delta channel carries `reasoning_content` | `reasoning_content` at `G:97407392`, inside the streaming-frame key run |
| Reasoning is parsed as a first-class channel, not by string-splitting the content | `reasoningParser` (`G:97804048`), `insideReasoning` (`G:97816692`), `terminalInsideReasoning` (`G:97806864`), `harmonyChannelIsReasoning` (`G:97816752`) |
| Reasoning can be left open when generation stops | `unclosedReasoning` is a field on the result type — `G:91493128`; it appears in the mangled result signature alongside `tokenCount`, `tokensPerSecond`, `stopReason` |
| Reasoning can be encrypted in transit | `reasoning_encrypted` in the response DTO |
| Streaming is the expected path, not an error path | `send: got stream, entering delta loop`; `chatengine_streamDeltas_start` / `_done` |

The presence of `insideReasoning` and `terminalInsideReasoning` as named parser states is
the strongest available evidence that Osaurus tracks the reasoning channel as a state
machine and can end a generation *inside* reasoning. The `unclosedReasoning` result flag
confirms the runtime can report that condition rather than hiding it.

### 5.2 What controls granularity (established)

`generation.streamInterval`, validated `>= 1` ("Stream interval must be at least 1." —
`G:107036640`), key literal `generation.streamInterval` at `G:107036608`, **value `1` on
this host** (E2).

This is the direct analogue of oMLX's `stream_interval`, which is exactly the field the
harness failed to find last time. Here it appears in both the settings schema and the
config key list, so it is discoverable from `~/.osaurus/config/server-runtime.json` without
opening the binary. A value of `1` reads as "flush every token", but **the semantics of the
integer are not established by the string table** — see §9.2. Do not report a TTFT
improvement or regression as a function of this key until a live probe has shown what
changing it does.

### 5.3 Not established, and must be probed live

| Question | Status |
|---|---|
| Does `content` stream incrementally, or arrive whole? | **Unknown.** The delta machinery and `contentDeltas` counter imply incremental, but nothing in the string table proves the content channel is not buffered to completion. |
| Does `reasoning_content` stream incrementally, or arrive whole? | **Unknown.** Same reason. oMLX's failure mode was precisely this: reasoning streamed, content did not, and the published claim was the opposite. |
| Is any channel mirrored into another (reasoning copied into `content`)? | **Unknown.** No mirroring symbol was found, but absence-of-string is weak evidence and I will not rest a negative claim on it. |
| What is the exact meaning of `streamInterval`? | **Unknown.** Validated `>= 1`; whether it counts tokens, deltas, or milliseconds is not determinable statically. |
| How many deltas per response in each channel? | **Unmeasurable statically.** This is the number that was wrong by 8x last time. |
| Real TTFT | **Unmeasurable statically.** |

**Probe plan** (for the coordinator, who runs live probes): send one request with
`max_tokens` large enough that a single delta cannot be mistaken for proof of
non-streaming — the oMLX mistake was a probe with `max_tokens: 8`, where one content delta
looked like a complete answer. Count deltas per channel, and repeat the count with
`generation.streamInterval` at `1` and at a larger value to establish what the integer
controls. Record `content_event_count` and a reasoning event count from the first live run
onward, and read them — the harness already recorded `content_event_count` from its first
oMLX run and nothing consulted it.

---

## 6. Token accounting

### 6.1 What the usage block contains

The OpenAI-compatible `usage` object carries exactly four fields (E3, contiguous run at
`G:97407968`):

`prompt_tokens`, `completion_tokens`, `total_tokens`, `tokens_per_second`.

The OpenResponses variant carries `input_tokens`, `output_tokens`, `total_tokens`.

Internally the result type carries more than the wire exposes. From the mangled Swift result
signatures (E3): `tokenCount`, `tokensPerSecond`, `unclosedReasoning`, `stopReason`,
`prefillTokensPerSecond`, `inputTokenCount`, **`cachedInputTokenCount`**, and separately
`ttft`, `modelLoad`. The internal surface also has `promptTokenCount`,
`generationTokenCount`, `generationTokenCount`, `prefixCacheRestoredTokens`
(`G:97803872`), `effectivePromptTokens`, and `cacheRestoredTokens`.

### 6.2 Does it separate reasoning from content?

**No, not on the wire.** `prompt_tokens`, `completion_tokens`, and `total_tokens` are the
whole usage block; there is no `reasoning_tokens`, and no `completion_tokens_details` or
`prompt_tokens_details` anywhere in either binary (grep for those four literals returns
nothing).

This is **absence-of-string evidence**, and I am labelling it as such rather than as a
source-verified negative. It is consistent and it is checkable, but it is not the same class
of proof as a decoded struct. What it means in practice: **a `completion_tokens` figure from
Osaurus cannot be decomposed into reasoning and content.** If a cell's reasoning is enabled,
its `completion_tokens` includes reasoning tokens and the harness cannot tell how many. That
is a real limitation on any reasoning-vs-content throughput comparison.

It also means the separate `reasoningDeltas` count (§5.1) is a *delta* count, not a token
count, and the two must not be conflated.

### 6.3 Are the self-reported rates trustworthy?

**Treat them as suspect until probed, and here is the specific reason.** Osaurus reports a
`tokens_per_second` field in the usage block alongside `total_tokens`. The failure mode this
project is trying to stop repeating is oMLX reporting
`generation_tokens_per_second: 15286.61` from a `generation_duration` of `0.0` — a rate
computed by dividing by a zero/near-zero interval and published without a sanity check.

Two things about Osaurus raise the same flag:

1. **`tokens_per_second` is a single number with no accompanying duration on the wire.** The
   usage block carries no `generation_duration`, no `elapsed`, no start/end timestamps. So
   whatever denominator the server used is **not visible to the client**, and cannot be
   audited or recomputed from the response. An implausible rate cannot be detected from the
   payload alone, because the payload omits the quantity that would make it implausible.
2. **`cachedInputTokenCount` and `prefixCacheRestoredTokens` exist internally but are not in
   the wire usage block.** A run whose prompt came from the prefix/block cache did far less
   prefill work than a cold run, and the response does not say so.

The harness must therefore compute rates from its own wall-clock and its own token counts,
and treat the server's `tokens_per_second` as a cross-check that is expected to disagree.
Record it, but never publish it as the measurement. If the server's number and the harness's
number diverge by a large factor, that divergence is itself the finding.

Note also `noUsage` in the bench JSON (§2.3): upstream has already built the case where the
usage block is absent into its own bench tool. Your harness should do the same.

---

## 7. Behaviour that silently changes performance

These are the mlx-optiq-`--stream-experts` equivalents: things that change what a cell
measures while appearing in no start command.

### 7.1 Two caches are on by default, and one is holding 8.2 GB right now

| Setting | Value | Effect |
|---|---|---|
| `cache.prefix.enabled` | `true` | In-memory prefix reuse |
| `cache.blockDisk.enabled` | `true` | **On-disk L2 KV cache**, `maxSizePercent: 10` |

Measured on this host (E4): `~/.osaurus/cache/kv_v2` contains **8.2 GB** of persisted KV
blocks — 13 `.safetensors` payloads plus `cache_index.db` (with `-shm`/`-wal`). Timestamps
show blocks written 2026-09-10 and again 2026-09-13.

`ohyesmlx/osaurus_settings.py`'s own module docstring already flags this — *"the disk block
cache and the prefix cache are on by default, which is the same class of defect that made
oMLX get `--no-cache` pinned; deciding whether they should be off is a separate call this
module does not make."* This document supplies the missing magnitude: **8.2 GB of warm
cache**, which survives restarts and changes prefill cost between a first run and a second
run of the same prompt.

The 8.2 GB also matters against AGENTS.md's free-disk budget of 36 GiB.

There is no flag for either cache. `concurrency.continuousBatching` (currently `true`) gates
most of this: the binary states "Continuous batching is off, so prefix/paged/block-disk cache
reuse will be limited or disabled."

### 7.2 Memory-safety modes are automatic and can degrade the cell

`memorySafety.mode` is `safe_auto` — an automatic mode, not a fixed one. The modes are
`balanced`, `safe_auto`, `strict`, `diagnosticDangerous`. Embedded messages show what the
automatic modes do:

- `Estimated request working set ... bytes exceeds resolved memory budget ...` — a request
  can be **refused or truncated** based on an estimate the harness never sees.
- `TurboQuant KV is already enabled; reduce the context length or lower the memory-safety
  slider to fit.` — the runtime can change KV encoding to make a request fit.
- `Diagnostic memory mode uses caller-supplied limits and may exceed the host working set.`
- `Performance memory mode may allow macOS compression or swap before refusing a request.`
- `... GiB) approach physical memory; loading materialized instead of mmap so pages stay
  resident.` — **the load strategy itself changes** (mmap vs materialized) based on a memory
  threshold. That is a materially different memory and load-time profile with nothing in the
  artifact recording it.
- `MLXPress/JangPress was not selected by the memory slider. It remains disabled unless the
  host enables a proven routed-bundle lane explicitly.` — **the memory slider gates an
  expert-streaming path.** This is the direct analogue of mlx-optiq turning `--stream-experts`
  on by itself: here it is a slider position, in a settings file, that enables or disables a
  5x-class behaviour.
- `Strict memory safety requires a request working-set estimate before launch.`

`safe_auto` plus `slider: 2` means the automatic path is the one in use. A cell that
measured fine at one RAM pressure level can silently take a different path at another.

### 7.3 `--tune-prefill` persists a per-model performance setting

`osaurus bench --tune-prefill` *"measures the model's TTFT at each candidate prefill step
size and persists the per-model winner (the optimum is model-architecture-dependent); the
server applies it immediately."* (E1, bench help.)

So a benchmark command **writes a persistent per-model performance setting that then applies
to production serving**. The persisted value is `prefillStepSize`, paired with `measuredAt`
and `benchTTFTMs` in the internal tuning record (E3). The schema also has
`concurrency.prefillStepSize` / `prefillBatchSize` / `completionBatchSize`, all validated
positive, none present in this host's `server-runtime.json`.

Running `bench --tune-prefill` on a machine shared with a measurement grid is therefore a
**state-mutating operation**, not a read. Whether the persisted winner lives in
`~/.osaurus/config` or elsewhere I did not determine; it is not in the files enumerated in
§3.2 or §3.4, so it is most likely in the per-model store reachable from the app.

### 7.4 Model residency, eviction, and idle unload

- `modelEvictionPolicy = "Strict (One Model)"` — one model resident at a time. This is the
  enforcement of AGENTS.md's single-residency rule, and it is a *setting*, not a guarantee:
  changing it silently permits two resident models.
- `modelIdleResidencyPolicy = after_seconds / 900` — **the model unloads 15 minutes after
  last use.** A grid with gaps longer than 15 minutes pays a cold load per cell, and the
  cold load is not part of any TTFT figure the server reports.
- `modelLoadRAMSoftThreshold = 0.8`, `modelLoadRAMHardThreshold = 0.9`.
- `chat.json:warmModelsOnLoad = true` — the app loads a model at startup, outside any cell.
- `agent-delegation.json:ramSafetyPreflightEnabled`, `subagentCoexistenceEnabled: true`,
  `imageJobLoadPolicy: "agent_single_residency"`, and an 8-key `spawnableModelNames`
  list — subagent and image delegation **can unload the chat model** to make room
  (`unloadedChatModels` appears in the runtime's own state: `unloadedModelNames`,
  `restoreModelNames`, `insufficientMemory`, `restoreBlocked`). A delegation firing
  mid-cell would unload the measured model.

### 7.5 Per-model `disableThinking` — §3.6

Repeated here because it belongs on this list: it is per-model, it lives in a preference
plist, and it decides whether reasoning tokens are generated at all. On this host it is
**on** for three models.

### 7.6 Automatic update checks

`SUEnableAutomaticChecks = true` (§1.4). The app can replace itself between cells.

---

## 8. Quantization formats

### 8.1 Quantization modes the engine implements

The MLX quantization-mode enum is **`affine`, `mxfp4`, `mxfp8`, `nvfp4`** (E3, contiguous
enum run). Supporting constraints, from the MLX core messages in the same binary:

- `[quantize] The requested number of bits ... is not supported. The supported bits are 2, 3, 4, 5, 6 and 8.`
  — **1-bit and 7-bit are refused**; 2/3/4/5/6/8 accepted.
- `[quantize] The requested group size ... is not supported. The supported group sizes are 32, 64, and 128.`
- `[qqmm] Only 'nvfp4' and 'mxfp8' quantization modes are supported but ...` — the fast
  quantized-matmul path is restricted to `nvfp4` and `mxfp8`.
- `[quantize] Global scale is not supported on the Metal backend.` — a `nvfp4`/`mxfp8`
  feature that Metal refuses.
- `[block_masked_mm] Only block_sizes 32, 64 are supported.`

### 8.2 Weight formats Osaurus recognizes by name

From the format/capability-detection key set (E3): `weightFormat`, `jangFormat`,
`jangProfile`, `jangQuantizationMethod`, `mxtqBits`, `hasJangConfig`, `hasJANGTQSidecar`,
`hasJangTQRuntime`, `bundleFormat`, `routedExpertLayout`, `hasPrestackedAffineRoutedExperts`,
`declaredComputeDType`, `quantizationBits`, `sidecarCodebookBits`, `totalSafetensorsBytes`.

Family names that appear in the bundle and in the model catalogue (E3):
`JANG`, `JANG_4M`, `JANG_6M`, `JANGTQ`, `JANGTQ2`, `JANGTQ4`, `MXFP4`, `MXFP8`, `nvfp4`,
`affine`, `ternary`.

Confirmed present on this host (E2, `/Users/jrazz/MLXModels/OsaurusAI/`):

| Model directory | Weight file(s) | Quant sidecar |
|---|---|---|
| `Ornith-1.0-35B-JANG_4M` | 32 × `model-*.safetensors` | `jang_config.json` |
| `Qwen3.8-27B-JANG_4D` | 4 × `model-*.safetensors` | `jang_config.json` |
| `Nanbeige4.2-3B-JANG_6M` | `model-00001-of-00001.safetensors` | `jang_config.json` |
| `Raptor-v0.5-8B-A1B-JANG_6M` | `model.safetensors` | `jang_config.json` |
| `Spark-X2.5-4B-JANG_6M` | `model-00001-of-00001.safetensors` | `jang_config.json` + `osaurus.json` |
| `rampart-mlx` | `model.safetensors` | none |

So the on-disk container format is **safetensors** in every case. JANG/JANGTQ/MXFP are
*quantization schemes applied to tensors inside safetensors*, identified by a sidecar —
not alternative container formats. A repo without `jang_config.json` (e.g. `rampart-mlx`)
is plain MLX.

### 8.3 What `jang_config.json` declares

Read from `/Users/jrazz/MLXModels/OsaurusAI/Ornith-1.0-35B-JANG_4M/jang_config.json` (E2):

```json
{"quantization": {"method": "jang-importance", "profile": "JANG_4M",
  "target_bits": 4.0, "actual_bits": 4.11, "block_size": 128,
  "calibration_method": "weights", "quantization_method": "mse",
  "scoring_method": "weight-magnitude", "bit_widths_used": [4, 8],
  "passthrough_bit_widths_used": [16], "passthrough_tensor_count": 90,
  "quantization_scheme": "asymmetric", "quantization_backend": "mx.quantize",
  "hadamard_rotation": false, "mlp_asymmetry_floor": true,
  "tensor_quantization_manifest_schema": 1, "tensor_quantization_manifest_count": 432,
  "...": "..."}}
```

Two things matter for measurement. **`bit_widths_used: [4, 8]` plus
`passthrough_bit_widths_used: [16]` with `passthrough_tensor_count: 90`** — a "4-bit" model
here is mixed-precision, with 8-bit and 16-bit tensors in it. Nominal bit width is not the
storage width. `actual_bits: 4.11` against `target_bits: 4.0` is the honest figure.
And `tensor_quantization_manifest_count: 432` means per-tensor plan information ships with
the model; a generic loader will not reproduce it.

`osaurus.json` (`Spark-X2.5-4B-JANG_6M`) carries `{"required_osaurus_version": "0.25.0",
"model_version": "1"}` — **a bundle can gate itself on a minimum app version.** On 0.25.3
this one is satisfied; a future required version above the installed app would refuse.

### 8.4 What is refused

| Refusal | Evidence |
|---|---|
| Bits other than 2, 3, 4, 5, 6, 8 | `[quantize]` message, §8.1 |
| Group sizes other than 32, 64, 128 | `[quantize]` message, §8.1 |
| `nvfp4`/`mxfp8` fast path for any other mode | `[qqmm]` message, §8.1 |
| Global scale on Metal | `[quantize]`/`[dequantize]` messages |
| Unsupported model type at the family level | `Unsupported local model type: hunyuan_v1_dense. Osaurus needs vmlx Hunyuan Dense support before this model can run locally.` |
| A bundle whose MTP metadata is incomplete | `MTP cannot be forced on until the bundle has complete tensor evidence and usable vmlx_mtp_tuning.json metadata` |
| A bundle with no MTP tensors, when MTP is forced manually | `MTP manual depth requires complete MTP tensor evidence in the bundle` |
| `paged` KV for incompatible architectures | `paged_incompatible_model_count`, `isPagedIncompatible`, `requiresPagedBoundaryCompanion` |
| Nanbeige with an unsupported runtime formula | `Nanbeige jang_runtime cache_slot_formula is unsupported` |

**Not established:** whether Osaurus loads GGUF at all. The literal `ggufOnly` exists as a
compatibility-catalogue state (`G:221659`), which suggests GGUF is *classified* rather than
loaded; and every local model on this host is safetensors. I did not find a GGUF loader, but
"no loader string found" is absence evidence and I will not publish it as "cannot load
GGUF". State it as: **no evidence of a GGUF path was found, and GGUF appears as a
catalogue exclusion state; treat as unverified.**

---

## 9. What I could not determine, and why

### 9.1 Compiled defaults for absent settings

`server-runtime.json` on this host omits ~35 schema keys (§3.3). Their fallbacks are Swift
literals in the compiled binary, and **a string table does not contain numeric or boolean
literals in a recoverable way** — there is no mapping from a value to the key it defaults.
I did not guess them.

Two routes exist for a later pass, both requiring the server: `GET /admin/config/schema`
(`--format json` gives a machine-readable JSON Schema — the route literal
`/admin/config/schema?format=` is present in the CLI at `H`), or `osaurus config export`.

### 9.2 Streaming semantics and rates — §5.3, §6.3

Unmeasurable without starting the server, which the dispatch forbids. Named explicitly there
rather than softened here.

### 9.3 `/admin/*` methods and payloads

Route paths are strings; HTTP verbs are not. Unknown without a live probe.

### 9.4 Where the `--tune-prefill` winner is persisted

The record's shape is known (`prefillStepSize`, `benchTTFTMs`, `measuredAt`, `checkedURL`),
not its location. Not in `~/.osaurus/config/` as far as this session searched.

### 9.5 The model root bookmark's target

`NSOSPLastRootDirectory` is a 760-byte security-scoped bookmark. Decoding it into a path
requires resolving a bookmark blob through CoreServices, which I did not do. The model root
on this host is `/Users/jrazz/MLXModels`, established independently (E4: the JANG model
directories listed by `osaurus list` are present there, and `~/Documents/MLXModels` — the CLI
string's `legacy_app_default` — does not exist).

### 9.6 `osaurus doctor --json` — the output shape

Requested explicitly by the dispatch. **I did not run it**, because `doctor` diagnoses
"server startup" and this session had already started a server once by accident. The shape
below is reconstructed from the CLI's Codable key layout (E3, `H`), not observed.

Top-level keys, in the order they appear in the binary's key cluster:

| Key | Note |
|---|---|
| `generatedAt` | `H:9183601` |
| `cliPath` | |
| `cliVersion` | `H:9183621` |
| `cliBuild` | |
| `requestedPort` | `H:9183641` |
| `configuredPort` | `H:9183655` |
| `serverHealthy` | |
| `portOwner` | `H:9183684` |
| `modelRoot` | `H:8686352` |
| `modelRootSource` | `H:9183704` — enum `legacy_app_default` \| `shared_cli_setting` \| `ModelDirectoryBookmark` |
| `modelRootReadable` | |
| `modelCount` | |
| `modelCountComplete` | `H:8686384` |
| `diagnosis` | |
| `recommendation` | `H:9183794` |
| `companionAppPath` | `H:9183824` |
| `probeInterval` | `H:9183846` |
| `maxIterations` | `H:9183860` |

`diagnosis` values, camelCase enum: `healthy`, `appAbsent`, `appStale`, `appNewer`,
`duplicateBundles` (`H:9183424`), `portBusy`, `serverUnhealthy`, `serverNotRunning`
(`H:9183472`), `startupTimeout`.

The CLI also emits **snake_case** verdict codes in another context — `server_not_running`
(`H:8612176`), `server_unhealthy`, `duplicate_bundles`, `app_newer_than_cli`,
`app_stale_incompatible`, `development/unproven` — adjacent to the header string
`Osaurus installation doctor` (`H:8612080`). Which of the two naming schemes reaches the
`--json` output I did not determine. **`--redact`** is documented as producing "a shareable
installation report"; **`--verify-signatures`** adds per-app `signature` and `notarization`
fields whose status enum is `valid` \| `invalid` \| `timedOut` \| `unchecked`, alongside
per-app `version`, `build`, `isRunning`, `isCompanion`.

`probeInterval` and `maxIterations` sit in this string cluster next to `companionAppPath`,
which suggests they belong to the `serve --supervise` loop rather than the doctor report; the
boundary between the two structs could not be established from the string table. Treat the
key list as reliable and the key *grouping* as provisional.

**To confirm:** run `osaurus doctor --json` against a known-stopped server, which is
non-mutating, and diff the keys against this table.

---

## 10. Summary for the harness

The three things a cell must pin, none of which is expressible on the command line:

1. `~/.osaurus/config/server-runtime.json` — cache on/off, KV size, concurrency, memory
   safety, stream interval.
2. `~/.osaurus/config/server.json` — threads, RAM thresholds, eviction, idle unload, `genTopP`.
3. **`~/Library/Preferences/com.dinoki.osaurus.plist`** — per-model `disableThinking`.
   Not currently captured by anything.

The fourth pin is state rather than configuration: **`~/.osaurus/cache/kv_v2` is holding
8.2 GB of warm KV blocks that survive restarts.** A grid that does not clear it is measuring
a cache, not a runtime.

And the operational rule from §0.1: **never run `osaurus <subcommand> --help`.** For most
subcommands that is a state-mutating command, not a documentation lookup.
