# oQ portability spike — does stock mlx-lm load an oQ-quantized model?

**Date:** 2026-09-14
**Question:** Can stock mlx-lm load an oQ-quantized model?
**Artifact under test:** `avneetsb/gemma-4-12B-it-qat-oQ4-fp16`, local copy at
`~/.cache/huggingface/hub/avneetsb/gemma-4-12B-it-qat-oQ4-fp16/`
**Verdict: FAILS.**

mlx-lm 0.31.3 refuses this artifact at architecture resolution, before any weight file or
quantization setting is touched:

```
ValueError: Model type gemma4_unified not supported.
```

The `mlx_lm.server` process does not exit on this failure. It binds `127.0.0.1:8081`,
logs `Starting httpd at 127.0.0.1 on port 8081...`, and leaves a dead generation thread
behind — so a client POST connects successfully and then hangs forever with zero bytes
received. **No completion text was ever produced.** There is nothing to quote but the
traceback and the client-side timeout.

## Why it fails

`config.json` declares `"model_type": "gemma4_unified"`. mlx-lm resolves an architecture by
importing `mlx_lm.models.<model_type>`; the installed package ships `gemma4` and
`gemma4_text` (registered as exactly those names in their `ModelArgs`) but has no
`gemma4_unified` module. The failure is at `get_model_classes()` in
`mlx_lm/utils.py:334` — the first thing `load_model` does.

**Scope caveat, and it matters:** the run never reached weight loading or the
`quantization` block. So this spike does **not** establish whether oQ's per-layer
mixed-bit scheme is executable by stock mlx-lm. It establishes only that *this artifact, as
published, cannot be loaded by mlx-lm 0.31.3* — the blocker observed is the model-type
name, not the quantization config.

## Environment

| | |
|---|---|
| Host | macOS 26.6.2, arm64 (Apple Silicon) |
| Python (spike venv) | 3.14.7 (Homebrew, `/opt/homebrew/Cellar/python@3.14`) |
| mlx-lm | **0.31.3** (installed fresh from PyPI, no local patches) |
| mlx | 0.32.2 |

`pip show mlx-lm` (verbatim):

```
Name: mlx-lm
Version: 0.31.3
Summary: LLMs with MLX and the Hugging Face Hub
Home-page: https://github.com/ml-explore/mlx-lm
Author: MLX Contributors
Author-email: mlx@group.apple.com
License: MIT
Location: /private/tmp/mlxspike/lib/python3.14/site-packages
Requires: jinja2, mlx, numpy, protobuf, pyyaml, sentencepiece, transformers
Required-by:
```

No model was downloaded for this spike. Only wheels were fetched (mlx-lm and its deps).

## Locating the snapshot directory

The standard HF hub layout for this repo exists but holds no weights — only a ref:

```
$ ls ~/.cache/huggingface/hub/models--avneetsb--gemma-4-12B-it-qat-oQ4-fp16
refs
$ find ~/.cache/huggingface/hub/models--avneetsb--gemma-4-12B-it-qat-oQ4-fp16 -maxdepth 3
/Users/jrazz/.cache/huggingface/hub/models--avneetsb--gemma-4-12B-it-qat-oQ4-fp16
/Users/jrazz/.cache/huggingface/hub/models--avneetsb--gemma-4-12B-it-qat-oQ4-fp16/refs
/Users/jrazz/.cache/huggingface/hub/models--avneetsb--gemma-4-12B-it-qat-oQ4-fp16/refs/main
$ du -sh ~/.cache/huggingface/hub/models--avneetsb--gemma-4-12B-it-qat-oQ4-fp16
4.0K
$ cat ~/.cache/huggingface/hub/models--avneetsb--gemma-4-12B-it-qat-oQ4-fp16/refs/main
bfc0d4335b066255bdf7e5daa4ca515113b349d2
```

The actual downloaded artifact sits in a flat `local_dir`-style path under the same cache
tree, and that is what was passed to `--model`:

```
$ ls -l ~/.cache/huggingface/hub/avneetsb/gemma-4-12B-it-qat-oQ4-fp16/
total 14024448
drwxr-xr-x@  3 jrazz  staff          96 Jul 19 15:39 .cache
-rw-r--r--@  1 jrazz  staff        1570 Jul 19 15:39 .gitattributes
-rw-r--r--@  1 jrazz  staff       17466 Jul 19 15:39 chat_template.jinja
-rw-r--r--@  1 jrazz  staff       21448 Jul 19 15:39 config.json
-rw-r--r--@  1 jrazz  staff         260 Jul 19 15:39 generation_config.json
-rw-r--r--@  1 jrazz  staff  5016490126 Jul 19 15:44 model-00001-of-00002.safetensors
-rw-r--r--@  1 jrazz  staff  2131654337 Jul 19 15:41 model-00002-of-00002.safetensors
-rw-r--r--@  1 jrazz  staff      129797 Jul 19 15:39 model.safetensors.index.json
-rw-r--r--@  1 jrazz  staff         868 Jul 19 15:39 processor_config.json
-rw-r--r--@  1 jrazz  staff         516 Jul 19 15:39 README.md
-rw-r--r--@  1 jrazz  staff        2747 Jul 19 15:39 tokenizer_config.json
-rw-r--r--@  1 jrazz  staff      32169626 Jul 19 15:39 tokenizer.json
$ du -sh ~/.cache/huggingface/hub/avneetsb/gemma-4-12B-it-qat-oQ4-fp16
6.7G
```

Relevant `config.json` facts:

- `"model_type": "gemma4_unified"` — the blocker.
- `"quantization": {"mode": "affine", "group_size": 64, "bits": 4, ...}` — a top-level
  4-bit default plus roughly 70 per-layer overrides, each its own `{bits, group_size,
  mode}` dict, at `bits: 5` and `bits: 6` for selected `self_attn.{q,k,v,o}_proj` and
  `mlp.down_proj` tensors. This is the oQ mixed-precision shape. It was never parsed,
  because the run failed earlier.

## Exact commands run

```bash
# 1. venv + install
python3 -m venv /tmp/mlxspike && /tmp/mlxspike/bin/pip install -q mlx-lm
# -> INSTALL_OK

# 2. version evidence
/tmp/mlxspike/bin/pip show mlx-lm
# -> Version: 0.31.3   (full output above)

# 3. model discovery
ls ~/.cache/huggingface/hub/        # then find/du on the paths shown above
# -> weights found at ~/.cache/huggingface/hub/avneetsb/gemma-4-12B-it-qat-oQ4-fp16

# 4. port check, then server (background)
lsof -i :8081 || echo "8081 free before start"
# -> 8081 free before start
/tmp/mlxspike/bin/python -m mlx_lm.server \
  --model /Users/jrazz/.cache/huggingface/hub/avneetsb/gemma-4-12B-it-qat-oQ4-fp16 \
  --port 8081

# 5. one chat completion
curl -sS --max-time 60 -X POST http://127.0.0.1:8081/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"/Users/jrazz/.cache/huggingface/hub/avneetsb/gemma-4-12B-it-qat-oQ4-fp16","messages":[{"role":"user","content":"Name three primary colors."}],"max_tokens":64,"temperature":0,"stream":false}' \
  -w '\nHTTP_CODE=%{http_code}\n'

# 6. cleanup + port verification
kill 47512
lsof -i :8081 || echo "8081 free after kill"
# -> 8081 free after kill
```

## Evidence: verbatim server traceback

Captured on the server's stderr (log: harness shell-output log for the background task).
The harness prefixes each captured chunk with `[stderr]`; those prefixes and the one
interleaved logger line (`Starting httpd ...`, emitted on the main thread) are the only
non-program text below. Otherwise byte-for-byte:

```
Exception in thread Thread-1 (_generate):
Traceback (most recent call last):
  File "/private/tmp/mlxspike/lib/python3.14/site-packages/mlx_lm/utils.py", line 188, in _get_classes
    arch = importlib.import_module(f"mlx_lm.models.{model_type}")
  File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/importlib/__init__.py", line 88, in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<frozen importlib._bootstrap>", line 1406, in _gcd_import
  File "<frozen importlib._bootstrap>", line 1371, in _find_and_load
  File "<frozen importlib._bootstrap>", line 1335, in _find_and_load_unlocked
ModuleNotFoundError: No module named 'mlx_lm.models.gemma4_unified'

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/threading.py", line 1082, in _bootstrap_inner
    self._context.run(self.run)
    ~~~~~~~~~~~~~~~~~^^^^^^^^^^
  File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/threading.py", line 1024, in run
    self._target(*self._args, **self._kwargs)
    ~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/private/tmp/mlxspike/lib/python3.14/site-packages/mlx_lm/server.py", line 695, in _generate
    self.model_provider.load_default()
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^
  File "/private/tmp/mlxspike/lib/python3.14/site-packages/mlx_lm/server.py", line 385, in load_default
    self.load("default_model", None, "default_model")
    ~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/private/tmp/mlxspike/lib/python3.14/site-packages/mlx_lm/server.py", line 394, in load
    self._load(*model_key)
    ~~~~~~~~~~^^^^^^^^^^^^
  File "/private/tmp/mlxspike/lib/python3.14/site-packages/mlx_lm/server.py", line 349, in _load
    model, tokenizer = load(
                       ~~~~^
        model_path,
        ^^^^^^^^^^^
        adapter_path=adapter_path,
        ^^^^^^^^^^^^^^^^^^^^^^^^^^
        tokenizer_config=self._tokenizer_config,
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "/private/tmp/mlxspike/lib/python3.14/site-packages/mlx_lm/utils.py", line 491, in load
    model, config = load_model(model_path, lazy, model_config=model_config)
                    ~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/private/tmp/mlxspike/lib/python3.14/site-packages/mlx_lm/utils.py", line 334, in load_model
    model_class, model_args_class = get_model_classes(config=config)
                                    ~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^
  File "/private/tmp/mlxspike/lib/python3.14/site-packages/mlx_lm/utils.py", line 191, in _get_classes
    raise ValueError(msg)
ValueError: Model type gemma4_unified not supported.
```

Supporting fact — what the installed mlx-lm does ship:

```
$ ls /tmp/mlxspike/lib/python3.14/site-packages/mlx_lm/models/ | grep -i gemma
gemma.py
gemma2.py
gemma3_text.py
gemma3.py
gemma3n.py
gemma4_text.py
gemma4.py
recurrent_gemma.py
$ grep -n "model_type" /tmp/mlxspike/lib/python3.14/site-packages/mlx_lm/models/gemma4.py
16:    model_type: str = "gemma4"
```

## Evidence: the request produced no completion

First POST attempt produced nothing within the 30 s shell window. Re-run with an explicit
client-side cap, verbatim:

```
$ date +%T; curl -sS --max-time 60 -X POST http://127.0.0.1:8081/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"/Users/jrazz/.cache/huggingface/hub/avneetsb/gemma-4-12B-it-qat-oQ4-fp16","messages":[{"role":"user","content":"Name three primary colors."}],"max_tokens":64,"temperature":0,"stream":false}' -w '\nHTTP_CODE=%{http_code}\n'; echo "curl_exit=$?"; date +%T
23:24:18

HTTP_CODE=000
curl_exit=28
23:25:18

curl: (28) Operation timed out after 60005 milliseconds with 0 bytes received
```

Zero bytes received, HTTP code `000` (no response line at all), curl exit 28. The
connection is accepted; the generation worker that would answer it died during load, and
`mlx_lm.server` has no health gate to fail the request fast. There is no completion text
to quote for this spike.

## What this establishes

1. Stock mlx-lm 0.31.3 cannot load this oQ artifact. The refusal is deterministic, exact,
   and at architecture lookup — not a memory, disk, or timeout artifact.
2. `mlx_lm.server` fails silently from the client's point of view: it binds the port and
   prints `Starting httpd...` after the load thread has already raised, then serves
   requests that hang. Any harness that waits for "port is open" as its readiness signal
   will misread this failure as a live server.
3. The 12B oQ4 artifact occupies 6.7 GiB on disk (two safetensors shards,
   5,016,490,126 + 2,131,654,337 bytes).
4. The blocker is the declared `model_type` (`gemma4_unified`), which the installed
   mlx-lm does not provide; supported gemma4 names in this version are `gemma4` and
   `gemma4_text`.

## What this does not establish

- **Whether stock mlx-lm can execute oQ's quantization scheme.** The run never reached
  the `quantization` block. Unanswered.
- Whether a *newer* mlx-lm, or the identical oQ weights re-declared under a supported
  `model_type`, loads and generates correctly. Untested.
- Any performance, memory, or accuracy number. None were taken.

## Reproduction notes

- The spike venv is left in place at `/tmp/mlxspike` (mlx-lm 0.31.3, mlx 0.32.2, plus
  pytest); every command above is copy-pasteable from it.
- No model was downloaded; only the existing local artifact was read.
- Port 8081 was confirmed free before the run and after `kill`, per house port hygiene.
- The repo's own test suite (`python3 -m pytest -q`, 29 tests) passes unchanged; this
  spike touched no code.

## Round 2

**VERDICT: LOADS.**

**Artifact tested:** `Jundot/Qwen3.6-35B-A3B-oQ4-mtp` from
`~/.cache/huggingface/hub/Jundot/Qwen3.6-35B-A3B-oQ4-mtp/` (20.1 GiB, five safetensors
shards; same flat `local_dir` layout as Round 1). **Load duration ≈ 4 s.** mlx-lm 0.31.3
preloads `--model` at server start on a silent generator thread, so the load was timed on
an identical re-run by sampling the server's RSS every 2 s: 0.2 GB at 0 s → 4.6 GB at 2 s
→ 17.9 GB at 4 s → 20.1 GB plateau at 8 s. The first request then returned HTTP 200 in
1.83 s.

**Completion text, verbatim** — `choices[0].message.reasoning`, `finish_reason: "length"`,
64/64 completion tokens (15 prompt tokens), `message.content` absent:

```
，,跟ashaa.atore quell�不会ulatSR2ancel Hard1* "uhl an:...,1. 40面-VP : tep  1etasconfIAS11. ass question questionys- 0 memory 1 exleCT us  以能 ze
```

Not coherent English — it is mixed-script token salad with replacement characters, so the
artifact loads and generates without error but its output is unusable text.


# `cold_load_s` is not one quantity, and the ranking it produced was inverted

Date: 2026-09-15. Machine: MacBook Pro, M2 Max, 64 GiB, macOS 26.6.2.
Probe: `$CLAUDE_JOB_DIR/tmp/probe_lazy.py` and `confirm_lazy.py`. Qwen3.5-4B.

## The claim this corrects

`docs/research/2026-09-15-grid-loadability-probe.md` published a cold-load ranking and called
it *"the first genuinely comparable figure this project has produced"*:

| runtime | median cold load | as published |
|---|---|---|
| oMLX 0.6.4 | 2.18 s | **fastest** |
| mlx-optiq 0.5.6 | 3.23 s | |
| mlx-lm 0.31.3 | 3.85 s | |
| vMLX 1.6.59 | 16.13 s | slowest |

It was not comparable. Two different quantities sat in one column, and the runtime it named
fastest is second slowest.

## The measurement

`cold_load_s` is the time from spawn until `await_ready` returns. That is a real load time for
a runtime that loads weights at startup. For a runtime that loads them **lazily, on the first
request**, it is the time until the process was *listening* — and the load itself then happens
inside request #1, where it is charged to that request's latency.

Three requests per runtime, **no warmups**, same artifact, timing each:

| runtime | reported `cold_load_s` | req 1 | req 2 | req 3 | hidden in req 1 |
|---|---|---|---|---|---|
| mlx-lm | 3.32 | 0.47 | 0.40 | 0.41 | 0.07 |
| **oMLX** | **3.12** | **3.93** | 0.42 | 0.42 | **+3.51** |
| mlx-optiq | 4.14 | 0.31 | 0.27 | 0.27 | 0.04 |
| vMLX | 9.09 | 0.51 | 0.43 | 0.41 | 0.10 |

Confirmed on two further artifacts:

| artifact | runtime | reported | req 1 | req 2–3 | hidden |
|---|---|---|---|---|---|
| stock-4bit | oMLX | 2.20 | 4.26 | 0.41 / 0.42 | **+3.85** |
| stock-4bit | mlx-lm | 3.29 | 0.46 | 0.39 / 0.36 | 0.10 |
| OptiQ | oMLX | 2.20 | 3.56 | 0.52 / 0.48 | **+3.08** |
| OptiQ | mlx-lm | 2.12 | 0.49 | 0.42 / 0.42 | 0.07 |

**oMLX hides 3.08–3.85 s in its first request, on every artifact tested. The other three hide
0.04–0.10 s, which is noise.** oMLX is the only lazy loader of the four.

## The corrected ranking

Time to first useful token — what a user actually waits — is `cold_load_s` plus the first
request's penalty:

| runtime | reported | hidden | **true cost** | published rank | true rank |
|---|---|---|---|---|---|
| mlx-lm | 3.32 | 0.07 | **3.39 s** | 3rd | **1st** |
| mlx-optiq | 4.14 | 0.04 | **4.18 s** | 2nd | 2nd |
| oMLX | 3.12 | 3.51 | **6.63 s** | **1st** | **3rd** |
| vMLX | 9.09 | 0.10 | **9.19 s** | 4th | 4th |

The runtime published as fastest to load is in fact slower than two of the three it beat.

## Why the harness could not have caught this

`measure.py` runs **three warmup requests before measuring**. A lazy loader's entire cost lands
in warmup #1, which is discarded by design — warmups exist precisely to exclude first-request
effects like JIT and cache population from the measured figures.

That is the right instinct and the wrong outcome here. A JIT warm-up is an artifact of
benchmarking. **Loading the weights is not** — it is work the user pays for every time they
start the server, and discarding it makes a runtime look faster than it is at exactly the
moment the user is waiting.

So the cost is real, is paid on every cold start, and appears **nowhere** in the record:
excluded from `cold_load_s` because readiness already returned, and excluded from every
measured figure because it happened during a warmup.

## The shape, again

This is the fourth instance today of the same failure, and the pattern is now unmistakable:

| | column said | column measured |
|---|---|---|
| stock mlx-lm on a 256-expert MoE | fastest healthy row | token salad |
| oMLX decode rate | 1,532,954,517 tok/s | a zero-length window |
| oMLX TTFT | 5.499 s first-token latency | time-to-completion, wrong channel |
| **oMLX cold load** | **fastest loader** | **time until listening** |

Every one of them is a plausible number attached to a column name that describes something
else. None raised. None timed out. All four would have shipped.

## What should change

`cold_load_s` should keep its definition — time to readiness is a real and useful figure — but
it must not be the only one, and it must not be presented as time-to-first-token.

The cheapest honest fix: **record the first warmup request's latency** alongside it. Warmups
are already made and already timed; only the record discards them. A `first_request_s` column
makes a lazy loader visible without changing what anything already means, and the report can
say plainly that a large gap between it and later requests is a load the runtime deferred.

Any cross-runtime load comparison must use `cold_load_s + first_request_s`, and the leaderboard
should say which runtimes deferred work into the request.

## What this does not say

- Nothing about throughput. A slow loader may still generate fastest, and oMLX's steady-state
  request latency (0.42 s) is comparable to the others'. The correction is to the *load*
  column only.
- Nothing about why oMLX defers. The `--no-cache` pin this harness applies may be involved;
  that was not tested, and the deferral is a fact about how the harness runs it regardless.
- Nothing about Osaurus, which was not in this probe.

## Reproducing

```
python probe_lazy.py    # 4 runtimes, one artifact, 3 requests each, no warmups
python confirm_lazy.py  # oMLX vs mlx-lm across two more artifacts
```

The whole test is: run requests with no warmups and look at whether request 1 costs more than
requests 2 and 3. If it does, the runtime deferred its load into the request.


# Disk Audit — 2026-09-15

Internal SSD, `disk0` → APFS container `disk3`, 994.7 GB capacity ceiling. 37.6 GB unallocated.

Filesystem-only audit. No project planning documents were read. No files were deleted, moved,
or truncated; every number below is a measurement taken during this session. Nothing was
committed.

## Measurement constraints

Stated up front because they bound what this report can claim:

- **No root.** `sudo -n` fails (`a password is required`). All `du` figures are unprivileged and
  therefore **exclude** directories the account cannot read. The exclusions are enumerated in
  §2 and are bounded, not silent.
- **`tmutil` has no size verb.** `tmutil version` reports 4.0.0. `tmutil localsnapshotinfo` is not
  a valid verb on this build, `tmutil calculatedrift` only accepts a machine directory and rejects
  `/`, and `diskutil apfs listSnapshots` reports identity and purgeability but no byte counts.
  Snapshot space is therefore reported as a derived residual, not a direct measurement.
- **No hardlinks anywhere in the model stores.** Verified with
  `find <dir> -type f -links +1` across `~/.cache/huggingface/hub`, `~/MLXModels`, `~/.omlx/cache`,
  `~/.osaurus/cache` and `~/AI/LTX/models`: **0 files with nlink > 1** in each. Symlinks are not
  followed by `du` and are not hardlinks, so no blob is double counted and the `du` totals are exact.
- **Rounding.** Sizes are exact GB (bytes / 1024³) except where a command was run with `-g`, in
  which case the value is a whole-GB truncation. Nothing is estimated from file counts or
  extrapolated.

---

## 0. Headline: the "700 GB unaccounted for" premise does not survive measurement

The 700 GB gap was an artefact of comparing APFS accounting against a Finder-visible home
directory. Once dot-directories are included, the overwhelming majority of the volume is
attributed to directories that can be named precisely.

| Layer | GB |
|---|---:|
| APFS container ceiling (`disk3`) | 994.7 |
| In use by volumes | 957.0 |
| Not allocated (free) | 37.6 |

Container contents, all four volumes:

| Volume | Role | GB |
|---|---|---:|
| `disk3s1` Macintosh HD | System (sealed) | 12.6 |
| `disk3s2` Preboot | Preboot | 9.0 |
| `disk3s3` Recovery | Recovery | 1.3 |
| `disk3s5` Macintosh HD - Data | Data | 933.9 |
| `disk3s6` VM | swap | 0.00002 |
| | **total** | **956.8** |

Data volume reconciliation:

| | GB |
|---|---:|
| Data volume consumed (APFS) | 933.9 |
| Attributed to readable directories | 656.5 |
| **Not explainable from readable files** | **~277.4** |

The 656.5 GB of readable directories breaks down as: `~` 591.45, `/Applications` 26.45,
`/opt` 12.91, `Data/System` 11.76, `/private` 7.87, `/Library` 6.05, `/usr` 0.75.

**The two answers to the original question:**

1. **~368 GB sits in dot-directories the Finder hides.** `~/.cache` (152.80) + `~/MLXModels`
   (147.07) + `~/.omlx` (68.58) alone is 368.45 GB. None of it appears in a default Finder view of
   the home folder. This is why the space looked unaccounted for.
2. **~277 GB is APFS-resident and invisible to `du` at any depth** — local Time Machine snapshots
   plus a small set of root-only system directories. Detail in §2.

---

## 1. Top consumers

26 directories, full paths, measured GB. Overlap is intentional — parent and child are both shown
where the parent's total is otherwise hard to attribute.

| GB | Path | Notes |
|---:|---|---|
| 152.80 | `/Users/jrazz/.cache` | parent of rows 3, 11, 12 |
| 147.07 | `/Users/jrazz/MLXModels` | parent of rows 4, 7 |
| 100.61 | `/Users/jrazz/.cache/huggingface/hub` | the "~100 GB HF cache" |
| 93.65 | `/Users/jrazz/MLXModels/OsaurusAI` | JANG-format MLX weights |
| 82.08 | `/Users/jrazz/Library` | parent of rows 9, 13, 21, 22, 23 |
| 68.58 | `/Users/jrazz/.omlx/cache` | KV/prefix cache, confirmed by header |
| 53.41 | `/Users/jrazz/MLXModels/image` | diffusion weights |
| 41.82 | `/Users/jrazz/AI/LTX` | `models/` 41.43 + repo |
| 37.30 | `/Users/jrazz/Library/Application Support` | parent of rows 21, 22 |
| 26.45 | `/Applications` | Xcode 5, Android Studio 4, Docker 3 |
| 26.42 | `/Users/jrazz/.cache/uv` | `archive-v0` 26.42 |
| 21.82 | `/Users/jrazz/.cache/vmlx-engine` | `block-cache/` 21.82 |
| 21.31 | `/Users/jrazz/Library/Caches` | Homebrew 7.58, Google 5.97 |
| 20.68 | `/Users/jrazz/.gradle` | `caches/` 17.68 |
| 18.50 | `/Users/jrazz/Dev` | `active/` 14.11 |
| 17.68 | `/Users/jrazz/.gradle/caches` | Gradle artifact cache |
| 14.11 | `/Users/jrazz/Dev/active` | source checkouts |
| 13.36 | `/Users/jrazz/.android` | `avd/` 13.13 |
| 13.13 | `/Users/jrazz/.android/avd` | emulator images |
| 12.91 | `/opt` | Homebrew (`/opt/homebrew`) |
| 12.86 | `/Users/jrazz/Library/Application Support/Claude` | `vm_bundles/` 11.22 |
| 12.70 | `/Users/jrazz/Library/Application Support/Google` | Chrome 7.91, DriveFS 3.46 |
| 11.00 | `/Users/jrazz/Library/Android` | SDK |
| 10.90 | `/Users/jrazz/.osaurus` | `cache/kv_v2` 8.24 |
| 8.24 | `/Users/jrazz/.osaurus/cache` | KV cache, confirmed by header |
| 7.92 | `/Users/jrazz/.npm` | `_cacache` 5.95 |

Directories from the brief that landed small enough to fall off this table, all measured:
`~/Documents` 1, `~/Downloads` 1, `~/Movies` 1, `~/Desktop` 1, `~/Music` 1, `~/Pictures` 1,
`~/.Trash` 1 (and **empty of items** — `ls ~/.Trash | wc -l` = 0), `~/.docker` 0.02,
`~/.lmstudio` 1.44, `~/Library/Developer` 0.74, `~/Library/Containers` 6.90
(`com.docker.docker` 5.98), `/private/var/folders` 2.01, `/private/var/vm` 2.00,
`/private/var/db` 3.29, `/Library` 6.05, `/Library/Developer` 5
(`CoreSimulator/Caches` 3.04).

**Xcode is not the problem here.** `~/Library/Developer/Xcode/DerivedData` is **0.11 GB**. The
brief anticipated DerivedData, iOS DeviceSupport, simulators and archives as a likely consumer;
on this machine they total **0.74 GB**. `~/Library/Developer` as a whole is 0.74 GB and
`/Library/Developer` is 5 GB. There is no meaningful Xcode reclaim on this machine.

**Absent entirely:** `~/.ollama` and `~/.orbstack` do not exist. `~/.lmstudio` is 1.44 GB.
`~/.docker` is 0.02 GB — the container data lives in
`~/Library/Containers/com.docker.docker` (5.98 GB) instead.

---

## 2. Invisible space

### 2.1 Local Time Machine snapshots — the leading explanation

```
$ tmutil listlocalsnapshots /
com.apple.TimeMachine.2026-09-03-130310.local
com.apple.TimeMachine.2026-09-10-130415.local
```

```
$ diskutil apfs listSnapshots disk3s5
Snapshots for disk3s5 (2 found)
+-- D3B2B526-6A82-40B2-B7B2-1F0D11D9706D
|   Name:        com.apple.TimeMachine.2026-09-03-130310.local
|   XID:         7799681
|   Purgeable:   Yes
+-- F2654AB6-A7A8-46AF-8CD5-7FACE336CAE1
    Name:        com.apple.TimeMachine.2026-09-10-130415.local
    XID:         8048239
    Purgeable:   Yes
    NOTE:        This snapshot limits the minimum size of APFS Container disk3
```

Two snapshots exist. Both are marked `Purgeable: Yes`. The second carries APFS's own note that it
**limits the minimum size of the container** — that is APFS stating the snapshot pins blocks that
the container cannot release.

**Byte-exact snapshot size could not be obtained without root** (see constraints). What can be
stated rigorously:

- The 277.4 GB residual is *not* attributable to root-only directories. Those are
  `/System/Volumes/Data/.DocumentRevisions-V100`, `.Spotlight-V100`, `.fseventsd`,
  `/private/var/db` and a handful of `/Library` entries. Measured where readable:
  `/private/var/db` 3.29 GB, `/private/var` 7.87 GB total. On a volume of this size these are
  normally single-digit to low-tens of GB. `/private/var/folders` is 2.01 GB, `/private/var/vm`
  2.00 GB (`sleepimage`, exactly 2147483648 bytes).
- Therefore **the bulk of the 277.4 GB residual is snapshot-pinned blocks** — data that was
  deleted from the live filesystem but is retained because a snapshot still references it.

This is consistent with the known history of this machine: large quantized model artifacts
(~19–23 GB each) are downloaded, evaluated and deleted repeatedly, and any deletion after
2026-09-03 is still pinned by these snapshots.

**This is the single largest reclaimable item on the machine, and it is invisible to `du`,
Finder, and `df`'s "used" figure alike.** The fix is `tmutil deletelocalsnapshots <date>` (or
`sudo tmutil thinlocalsnapshots / <bytes> 4` to thin rather than delete), which requires the
password that this session did not have. **Not executed — this report is read-only.**

### 2.2 Purgeable space

`diskutil apfs list` on this build emits no `Purgeable` line for the container or its volumes, and
`diskutil apfs list -plist` exposes no purgeable key (only `CapacityCeiling`, `CapacityFree`,
`CapacityInUse`, `CapacityQuota`, `CapacityReserve`). The requested
`grep -i -A2 purgeable` equivalent therefore returns nothing from `diskutil`; the only
purgeability signal available unprivileged is the per-snapshot `Purgeable: Yes` in §2.1.

### 2.3 Other containers

`diskutil list` shows two additional containers on the same physical disk, outside `disk3`:
`disk1` (Apple_APFS_ISC, 524.3 MB) and `disk2` (Apple_APFS_Recovery, 5.4 GB). Both are
system-managed. `/Volumes` contains only a `.timemachine` directory and a `Macintosh HD` symlink
to `/`; there are no mounted external volumes contributing to the count.

---

## 3. Model artifacts

True sizes, one line per repo. **No hardlinks exist in any of these trees** (§Measurement
constraints), and `du` does not follow the snapshot symlinks in the HF cache, so each blob is
counted exactly once. Nothing here is double counted.

### 3.1 `~/.cache/huggingface/hub` — 100.61 GB total

Two different layouts coexist, which is worth knowing before scripting against this cache: most
entries use the canonical `models--<org>--<name>/{blobs,refs,snapshots,trees}` form, but four are
plain `<org>/<name>/` directories instead. Both are listed.

| GB | Path (relative to `~/.cache/huggingface/hub/`) |
|---:|---|
| 23.00 | `mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit` |
| 21.49 | `mlx-community/Ornith-1.0-35B-OptiQ-4bit` |
| 20.15 | `Jundot/Qwen3.6-35B-A3B-oQ4-mtp` |
| 19.67 | `georgeis55/Ornith-1.0-35B-MLX-oQ4` |
| 8.42 | `mlx-community/gemma-4-12B-it-qat-OptiQ-4bit` |
| 6.69 | `avneetsb/gemma-4-12B-it-qat-oQ4-fp16` |
| 0.94 | `models--mlx-community--Qwen3.6-35B-A3B-OptiQ-4bit` |
| 0.26 | `models--chopratejas--kompress-v2-base` |
| 0.002 | `models--answerdotai--ModernBERT-base` |
| **100.61** | **total** |

**Seven empty stub repos** — `refs/` only, 4 KB each, no `blobs/` content. These are
interrupted or ref-only metadata fetches and occupy no meaningful space, but they are clutter that
will confuse any script that enumerates the cache by directory:

`models--mlx-community--ltx-2.5-mlx-q8`, `models--mlx-community--ltx-2.5-mlx-ditq8`,
`models--mlx-community--Agents-A1-OptiQ-4bit`, `models--Jundot--Qwen3.6-35B-A3B-oQ4-mtp`,
`models--JANGQ-AI--Spark-X2.5-4B-JANG_8M`, `models--georgeis55--Ornith-1.0-35B-MLX-oQ4`,
`models--avneetsb--gemma-4-12B-it-qat-oQ4-fp16`.

Note that `models--Jundot--Qwen3.6-35B-A3B-oQ4-mtp` (stub, empty) and
`Jundot/Qwen3.6-35B-A3B-oQ4-mtp` (20.15 GB, populated) are the *same model repo* under the two
layouts. Similarly for `georgeis55` and the two `mlx-community` entries. A naive per-directory
enumeration will report these twice, once at 4 KB and once at full size.
`~/.cache/huggingface/hub/.locks/` holds 19 empty lock directories, also harmless.

### 3.2 `~/MLXModels` — 147.07 GB total

**`~/MLXModels/OsaurusAI` — 93.65 GB**

| GB | Model |
|---:|---|
| 18.46 | `Ornith-1.0-35B-JANG_4M` |
| 18.35 | `Qwen3.6-35B-A3B-JANGTQ4` |
| 16.88 | `Qwen3.8-27B-JANG_4D` |
| 9.47 | `gemma-4-12B-it-qat-JANG_4M` |
| 7.50 | `Bonsai-27b-Ternary-JANG` |
| 6.32 | `Raptor-v0.5-8B-A1B-JANG_6M` |
| 3.64 | `Raptor-0.6-preview-JANG_6M` |
| 3.64 | `Nanbeige4.2-3B-JANG_6M` |
| 3.43 | `Spark-X2.5-4B-JANG_6M` |
| 3.43 | `Raptor-0.6.1-preview-JANG_6M` |
| 2.50 | `MiniCPM5-2B-JANG_8M` |
| 0.03 | `rampart-mlx` |
| **93.65** | **subtotal** |

**`~/MLXModels/image` — 53.41 GB**

| GB | Model | Contains |
|---:|---|---|
| 27.77 | `Qwen-Image-Edit-mflux-q5` | `text_encoder` 14.43, `transformer` 13.09, `vae` 0.24, `tokenizer` 0.01 |
| 25.65 | `ideogram-4-fp8` | `transformer` 8.65, `unconditional_transformer` 8.65, `text_encoder` 8.18, `vae` 0.16 |
| **53.41** | | |

**`~/MLXModels/mlx-community` — ~0 GB** (shell directory, effectively empty).

### 3.3 `~/AI/LTX/models` — 41.43 GB

Separate from the two stores above — a diffusion-model repo checkout under `~/AI/LTX`, not part of
the HF cache.

### 3.4 Cross-store observation

The three model stores hold **289.11 GB combined** (`~/.cache/huggingface` 100.61,
`~/MLXModels` 147.07, `~/AI/LTX` 41.43). The HF cache and `MLXModels` hold the *same model
families* in *different quantization formats* — e.g. `Ornith-1.0-35B` appears as
`-OptiQ-4bit` (21.49), `-oQ4-mtp` variants, and `-JANG_4M` (18.46); `Qwen3.6-35B-A3B` appears as
`-OptiQ-4bit` (23.00), `-JANGTQ4` (18.35) and `-oQ4-mtp` (20.15). This is a deliberate axis-of-
comparison workload for this project, **not** accidental duplication, and it is the reason the
disk filled. It is recorded here as a fact, not as a recommendation.

---

## 4. Reclaim table

`SAFE` = regenerable or re-downloadable **and** containing no personal data. Anything with any
uncertainty is `CHECK-FIRST`. **Every model file is `CHECK-FIRST` regardless of age** — which
models go is the human's call.

Categories are confirmed where possible by inspecting file *contents*, not by trusting the
directory name: the three KV caches below were each verified by reading the JSON header of a
`shard` file and confirming they hold `layer_N_state_M` / `L0.cache.N` attention state rather
than model parameters.

### SAFE

| Path | GB | What it is | Risk | Reasoning |
|---|---:|---|---|---|
| `~/.omlx/cache` | 68.58 | oMLX SSD KV/prefix cache | **SAFE** | Header inspection shows `layer_0_state_0` `[1,3,8192]` BF16 + `[1,32,128,128]` F32 per layer — attention state, not weights. Content-addressed, 734 shards, no manifest; regenerates as the server runs. Contains no documents. |
| `~/.cache/uv` | 26.42 | uv package archive cache | **SAFE** | `archive-v0` holds unpacked wheel artifacts; `uv cache clean` is the supported path and everything re-downloads from PyPI. |
| `~/.cache/vmlx-engine/block-cache` | 21.82 | vMLX KV block cache | **SAFE** | Header shows `L0.cache.0` `[1,3,8192]` F16 + `[1,32,128,128]` F32 — same KV shape as oMLX. 3,847 block files, regenerated on use. |
| `~/.gradle/caches` | 17.68 | Gradle dependency/artifact cache | **SAFE** | Rebuilt from Maven repositories on next build; contains no sources. |
| `~/.osaurus/cache/kv_v2` | 8.24 | Osaurus KV cache | **SAFE** | Header shows `__jang_cache_format_version__` plus `__layer_kind_N__` markers — serialized KV state. 19 files, no model weights. |
| `~/Library/Caches/Homebrew` | 7.58 | Homebrew download cache | **SAFE** | `downloads/` 7.58 GB of bottles and tarballs; `brew cleanup` is the supported path and everything re-downloads. |
| `~/Library/Caches/Google` | 5.97 | Chrome/Android Studio HTTP cache | **SAFE** | Ordinary browser and IDE caches; re-fetched on demand. No user documents. |
| `~/.npm/_cacache` | 5.95 | npm content-addressable cache | **SAFE** | `npm cache clean --force`; re-populated from the registry. |
| `/Library/Developer/CoreSimulator/Caches` | 3.04 | CoreSimulator runtime cache | **SAFE** | Downloaded simulator runtime images; re-fetched by Xcode. |
| `/private/var/folders` | 2.01 | Per-user temp/cache (`$TMPDIR`) | **SAFE** | Ephemeral by design; macOS reaps these and apps recreate what they need. |
| `/private/var/vm/sleepimage` | 2.00 | Hibernation image (exactly 2147483648 B) | **SAFE** | Regenerated on demand by the kernel; deleting it costs one slower wake from hibernation. |
| `~/.cache/codex-runtimes` | 1.89 | Downloaded runtime binaries | **SAFE** | Re-downloadable tool runtimes. |
| `~/Library/Caches/ms-playwright` | 1.10 | Playwright browser binaries | **SAFE** | `npx playwright install` re-fetches. |
| `~/.cache/puppeteer` | 1.05 | Puppeteer Chromium download | **SAFE** | Re-fetched by the installer. |
| `~/Library/Developer/Xcode/DerivedData` | 0.11 | Xcode build products | **SAFE** | Pure build output; regenerated by the next build. Included for completeness — it is negligible. |
| **Running total** | **173.44** | | | **Achieved without touching root, snapshots, or any model.** |

### CHECK-FIRST

| Path | GB | What it is | Risk | Reasoning |
|---|---:|---|---|---|
| APFS local snapshots (2) | **~277** (residual, see §2.1) | `com.apple.TimeMachine.2026-09-03/10` | **CHECK-FIRST** | Largest single item on the disk. `Purgeable: Yes`, and one is flagged as limiting the container minimum — so it is almost certainly reclaimable. **But these are the only local restore points on the machine**; deleting them destroys the ability to roll back anything changed since 2026-09-03. Byte-exact size needs root. Human must decide. |
| `~/.cache/huggingface/hub` | 100.61 | HF model cache, 6 populated repos | **CHECK-FIRST** | Re-downloadable in principle, but these are the artifacts under comparison in this project's own measurement work; which ones are still needed is a research decision, not a housekeeping one. |
| `~/MLXModels` | 147.07 | JANG/JANGTQ quantized MLX weights | **CHECK-FIRST** | Same reasoning. Some of these formats may not be reproducible or re-downloadable at their current revisions. |
| `~/AI/LTX/models` | 41.43 | LTX diffusion weights | **CHECK-FIRST** | Same reasoning. |
| `~/Library/Application Support/Claude/vm_bundles` | 11.22 | Claude Desktop VM images | **CHECK-FIRST** | Re-downloadable, but it is the app's active runtime; deleting it forces a re-provision that the app may or may not do cleanly. |
| `~/.android/avd` | 13.13 | Android emulator images | **CHECK-FIRST** | System images re-download via `sdkmanager`, but an AVD can hold cold-boot snapshots and app state created by hand. |
| `~/Library/Android` | 11.00 | Android SDK | **CHECK-FIRST** | Mostly re-downloadable, but may contain the only copy of a locally-built or side-loaded artifact. |
| `~/Library/Application Support/Google/DriveFS` | 3.46 | Google Drive local cache | **CHECK-FIRST** | A local cache of cloud content — but Drive Files On-Demand can hold the *only* copy of a file if it was never fully synced. Explicitly a data-loss risk. |
| `~/.local/share` | 4.70 | XDG app data | **CHECK-FIRST** | Mixed content; some subdirectories are caches and some are genuine application state. Not itemized this pass. |
| `~/Library/Application Support/Google/Chrome` | 7.91 | Chrome profile | **CHECK-FIRST** | Contains the real profile: history, cookies, saved passwords, extensions. Mostly not reclaimable without losing state. |
| `/private/var/db` | 3.29 | System databases and diagnostics | **CHECK-FIRST** | Partially root-only and partly unreadable even unprivileged. Not a disk-space target; leave it alone. |
| `~/Library/Containers/com.docker.docker` | 5.98 | Docker Desktop VM disk image | **CHECK-FIRST** | Contains every local image, volume and container. Deleting it destroys all local Docker state. Use `docker system prune` inside the app instead. |
| `~/.lmstudio` | 1.44 | LM Studio data | **CHECK-FIRST** | May hold downloaded models or conversation history. |
| `~/.gradle` (non-cache) | 3.00 | wrapper/native/daemon | **CHECK-FIRST** | Small residual outside `caches/`; not independently itemized. |
| `/opt/homebrew` | 12.91 | Homebrew Cellar | **CHECK-FIRST** | Installed packages, not cache. `brew autoremove` is the safe subset; the 12.91 GB is not straightforwardly reclaimable. |

### DO-NOT-TOUCH

| Path | GB | What it is | Risk | Reasoning |
|---|---:|---|---|---|
| `~/Dev` | 18.50 | Source checkouts (`Dev/active` 14.11) | **DO-NOT-TOUCH** | Working source trees, including uncommitted work. |
| `~/Documents`, `~/Desktop`, `~/Pictures`, `~/Music`, `~/Movies`, `~/Downloads` | ~6 total | Personal files | **DO-NOT-TOUCH** | User documents. Each is ~1 GB; there is nothing to win here. |
| `/Applications` | 26.45 | Installed applications | **DO-NOT-TOUCH** | Uninstalling an app is a decision about workflow, not disk hygiene. |
| `/System/Volumes/Data/System`, `/usr`, `Preboot`, `Recovery`, sealed System volume | ~35 | OS | **DO-NOT-TOUCH** | System-managed. Sealed and read-only. |
| `~/.Trash` | 1 | Trash | **DO-NOT-TOUCH** | Left alone deliberately: emptying Trash is destructive and outside this report's remit. It is also already empty of items. |

### The 277 GB is the whole answer, and it is one command away

Ranked by reclamation per unit of risk, the finding is unambiguous:

| Rank | Action | GB | Risk | Blocker |
|---:|---|---:|---|---|
| 1 | Thin or delete the two local snapshots (`sudo tmutil thinlocalsnapshots / 250000000000 4`, or `sudo tmutil deletelocalsnapshots <date>`) | ~277 | CHECK-FIRST | Needs password; destroys restore points |
| 2 | The 15 SAFE cache rows | 173.44 | SAFE | None |
| 3 | Model artifacts | 289.11 | CHECK-FIRST | Research decision |

**Rank 1 alone recovers more than every SAFE row combined (277 vs 173.44), and it is a single
command.** It is also the only reclaim that requires no judgement about which models are still
needed.

---

## 5. Blockers and what would settle them

Three items could not be measured in this session. None of them changes the shape of the answer,
but each would tighten a number:

1. **Byte-exact snapshot size.** Needs root. `tmutil` 4.0.0 provides no size verb and
   `tmutil calculatedrift` rejects `/`. With sudo, `sudo tmutil listlocalsnapshots /` combined
   with a container listing before/after a thin would give an exact figure. Currently reported as
   the 277.4 GB residual — bounded above and below by the fact that readable root-only
   directories in `/private/var` total only 7.87 GB.
2. **The root-only directories themselves.** `/System/Volumes/Data/.DocumentRevisions-V100`,
   `.Spotlight-V100`, `.fseventsd` all return `Permission denied` even for `du`. Expected
   low-tens of GB at most; unmeasurable without sudo. `.DocumentRevisions-V100` is the one that
   could in principle be larger, since it stores version history for edited documents.
3. **Purgeable accounting.** This `diskutil` build emits no purgeable line, contrary to the
   brief's expectation. The only purgeability evidence available unprivileged is the per-snapshot
   `Purgeable: Yes` flag.

---

## Method

Every figure in this report came from one of: `df -h`, `diskutil info` / `diskutil apfs list` /
`diskutil apfs listSnapshots` / `diskutil list`, `tmutil listlocalsnapshots`,
`du -d1 -g` / `du -d2 -g` / `du -sk`, `find -type f -links +1`, `stat -f %z`,
`find -exec stat`, `sysctl vm.swapusage`, `mount`, `ls`. Traversal was shallow-first and widened
only where a directory was large; the volume was never recursed wholesale.

Confirmed absent on this machine: `~/.ollama`, `~/.orbstack`, `~/Public`. Swap is not in use
(`vm.swapusage` reports 0.00 M total).

No destructive command was run. No cache was emptied. No file was created other than this one.


# The first live run — runtime axis on the cached oQ4 256-expert MoE

Date: 2026-09-15. Run directory: `results/20260915T143057Z-runtime/` (gitignored; regenerate
with the command below). Machine: MacBook Pro, M2 Max, 64 GiB unified memory, macOS 26.6.2.

This is the first time the harness was pointed at real servers. Every one of the 206 tests
that were green before this run used a fake transport, so nothing in the suite had ever
proved that `runtimes.py` can start a real process, that `transport.py` can read a real SSE
stream, or that `sample.py` can read a real process's footprint. This run was chosen to cost
nothing: both cells use an artifact already in the Hugging Face cache, so no download was
needed and the 97%-full data volume was never touched.

It is also the Phase 4 experiment as the roadmap specified it — *one cached artifact, two
runtimes, coherence as the outcome, zero downloads* — run early because it doubles as the
harness's first contact with reality.

## What was run

```
ohyesmlx run --study runtime --cells \
  oq4__mlxlm=~/.cache/huggingface/hub/Jundot/Qwen3.6-35B-A3B-oQ4-mtp,\
  oq4__omlx=~/.cache/huggingface/hub/Jundot/Qwen3.6-35B-A3B-oQ4-mtp
```

One variable varied: the serving runtime. Held constant: the artifact, byte for byte — the
same 21,636,566,952 bytes on disk for both cells, the same prompt, the same 256-token budget,
temperature 0, seed 0, three warmups and five measured requests split across two visits.

`mlx_lm` 0.31.3 is not on `PATH`; it lives in the spike virtualenv at `/tmp/mlxspike`, and
`MlxLm.start_command` invokes a bare `python -m mlx_lm.server`. The run therefore prepended
`/tmp/mlxspike/bin` to `PATH`. **That venv is in `/tmp` and will not survive a reboot.** It is
the only copy of `mlx-lm` on this machine outside oMLX's own app bundle, and the control arm
of every future runtime-axis run depends on it.

## Result

| cell | runtime | status | n | cold load s | peak MB | runtime version | reason |
|---|---|---|---|---|---|---|---|
| `oq4__mlxlm` | mlxlm | FAIL | 0/5 | 3.48 | 19,456 | 0.31.3 | still thinking: no content within max_tokens |
| `oq4__omlx` | omlx | FAIL | 0/5 | 3.11 | 119 | 0.6.4 | 5 of 5 measured requests failed; first: chat request returned HTTP 401 |

Not one published metric was produced. The harness is nonetheless the thing that worked here:
it started both runtimes, waited on the log rather than the port, sampled memory at 1 Hz for
26.7 s and 24 samples, recorded `phys_footprint`, read the artifact's size on disk, captured
each runtime's version, wrote every raw observation to `results.jsonl`, rendered the
leaderboard, stopped both servers and freed both ports, and exited 0. The failures below are
defects it *surfaced*, not defects in surfacing.

Two things the run proves in passing and that were previously only assumed: the cold load of a
21.6 GB 256-expert MoE under stock mlx-lm really is about three and a half seconds, and the
resident cost really is about 19.5 GB against 64 GiB of unified memory. Both numbers are from
the run record, and both hold regardless of the coherence verdict, because they are measured
before any token is generated.

## Defect 1 — `transport.py` reads the wrong field name for reasoning deltas

`transport.py` collected reasoning deltas from `delta.reasoning_content`. mlx-lm 0.31.3 emits
`delta.reasoning`. Captured verbatim from a direct `curl` against the same model on a separate
port, outside the harness:

```json
{"choices":[{"index":0,"finish_reason":null,
             "delta":{"role":"assistant","reasoning":"ext"}}]}
```

Because the spelling did not match, every reasoning delta was discarded, `content_event_count`
stayed at 0, and the stream closed with no content at all. `transport.chat` reported its
empty-content failure, and `measure._set_status` classified the cell as `STILL_THINKING` — "no
output is not bad output".

That classification was defensible on the evidence the harness had. It was wrong on the
evidence the server actually sent.

## Defect 2 — the reasoning channel was full of token salad, and the gate could not see it

The same direct `curl` shows what those discarded deltas contained:

```
delta.reasoning: "ext"
delta.reasoning: "ultip"
delta.reasoning: "好的"
```

Mixed-script fragments, exactly the failure mode recorded in
`docs/research/2026-09-14-oq-portability-spike.md`. The model is not thinking; it is producing
the same garbage the spike found, in a different channel, and it never emits a closing think
marker, so it never transitions to content and burns the entire token budget.

This is the failure the coherence gate exists for, and the gate as shipped would have let it
through with a reason that reads like a budget problem rather than a correctness problem. A
reader scanning a results table would see "still thinking: no content within max_tokens" and
conclude the token budget was too small. It was not. The output was garbage.

The rule the gate was built on — *a fast cell that emits garbage is a failed cell* — has to
extend to the reasoning channel. Garbage is garbage wherever it is spelled. `STILL_THINKING`
is the honest verdict only when a response produced neither content nor reasoning.

## Defect 3 — no measured request was ever authenticated

`Omlx.api_key()` returns the key oMLX is started with, and `runtimes._inventory` sends it as a
bearer token on the `/v1/models` readiness probe. That is the only place it was ever sent.
`transport.chat` built its headers as `{"Content-Type": "application/json"}` and took no
`api_key` parameter at all, so every measured request went out unauthenticated. oMLX's log is
unambiguous:

```
omlx.server - WARNING - POST /v1/chat/completions → 401: API key required   (×6)
```

The shape of this bug is worth naming because the project has already been bitten by it once.
`docs/interfaces.md` carries a standing warning that `token_counter` "must be wired at every
call site" — in the predecessor project the exact token path existed, was never passed by any
production caller, and the resulting metric was `None` in 100% of runs on disk. This is the
same failure: a correct capability, present in one module, never threaded through to the
module that needed it. The readiness probe authenticating while the measurement did not is the
tell.

The peak-memory column makes the consequence visible: oMLX's cell reports 119 MB. That is a
server process that loaded no weights at all, because every request it received was rejected
before it reached the engine. A 119 MB "peak" for a 21.6 GB artifact is not a memory
measurement; it is the signature of a cell that never ran.

## What changed as a result

`docs/interfaces.md` was amended to pin both fixes before any code was written, so the two
workers could build concurrently against the same shapes:

- `Observation` gains `reasoning_text: str` — the joined reasoning deltas, `""` when the model
  emitted none. `ttft_s`, `last_content_s` and `text` keep their content-only meaning; the
  reasoning channel is captured, never folded into the timing of visible output.
- `chat()` gains `api_key: str | None = None`, sent as `Authorization: Bearer <key>` when set,
  with a standing note that it must be wired at every call site for the same reason
  `token_counter` carries one.
- Both spellings, `delta.reasoning` and `delta.reasoning_content`, are read.

## What this does not settle

The 256-expert question itself is still open. This run did not compare stock mlx-lm against
oMLX on coherence, because oMLX never loaded the model — it answered 401 and shut down. The
comparison has to be re-run once authentication reaches the measured requests. Until then the
only thing established about `Jundot/Qwen3.6-35B-A3B-oQ4-mtp` is that stock mlx-lm executes it
incorrectly, which the spike had already established by other means.

What this run does settle is that the harness reports that failure honestly instead of
publishing a fast row, and that it now has two fewer blind spots than it did this morning.

## Reproducing

```
PATH=/tmp/mlxspike/bin:$PATH python -m ohyesmlx.cli run --study runtime \
  --cells oq4__mlxlm=<artifact>,oq4__omlx=<artifact>
```

The direct SSE probe that settled the field-name question, which needs no harness:

```
python -m mlx_lm.server --model <artifact> --port 8091
curl -sN http://127.0.0.1:8091/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"<artifact>","messages":[{"role":"user","content":"Say hello in one sentence."}],
       "max_tokens":48,"stream":true,"temperature":0}' | head -12
```


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


# The grid's real shape — Qwen3.5-4B across four formats and five runtimes

Date: 2026-09-15. Machine: MacBook Pro, M2 Max, 64 GiB, macOS 26.6.2.
Probe script: `$CLAUDE_JOB_DIR/tmp/probe_grid.py`; raw results `grid-probe.json`.

Not a measurement. One 24-token request per cell, coherence checked, runtime stopped. The
question is only *which cells can run at all*, because the grid's shape was being guessed and
the guesses were wrong.

## Result

| format | mlxlm 0.31.3 | oMLX 0.6.4 | mlx-optiq 0.5.6 | vMLX 1.6.59 | Osaurus 0.25.3 |
|---|---|---|---|---|---|
| stock-4bit | ✓ 4.01 s | ✓ 3.11 s | ✓ 4.20 s | ✓ 18.13 s | ⚠ port held |
| oQ4 | ✓ 3.21 s | ✓ 2.19 s | ✓ 3.19 s | ✓ 16.13 s | ⚠ port held |
| oQ4e | ✓ 3.83 s | ✓ 2.12 s | ✓ 3.24 s | ✓ 16.10 s | ⚠ port held |
| OptiQ-4bit | ✓ 3.87 s | ✓ 2.17 s | ✓ 3.21 s | ✗ **refused** | ⚠ port held |

**15 live cells of 20 probed.** Every cell marked ✓ loaded the artifact and returned coherent
text. The grid is far denser than predicted.

`⚠ port held` is not a capability result. `osaurus.app` was running and holding port 1337, and
the harness refused to start over a listener it did not spawn — correctly, since a server whose
settings it cannot pin measures nothing. That column is unprobed, not failed.

## Every predicted refusal was wrong

Before the probe, the sketched grid marked mlx-lm as unable to load oQ4, oQ4e, or OptiQ. It
loads all three, coherently. The one genuine refusal in the grid was not predicted at all.

This is the second time in one session that a capability claim was made from expectation rather
than evidence — the first was "oMLX does not stream". The rule in `AGENTS.md` exists because of
the first; this is the confirmation that a probe, not a prediction, is what establishes shape.

## The one real refusal, and why it is not a format incompatibility

vMLX rejects the OptiQ artifact in 9.2 s:

```
ERROR:vmlx_engine.models.mllm:Failed to load MLLM: Missing 297 parameters:
vision_tower.blocks.0.attn.proj.bias,
vision_tower.blocks.0.attn.proj.weight,
...
ValueError: Missing 297 parameters
ERROR:    Application startup failed. Exiting.
```

The obvious reading — "the OptiQ conversion dropped the vision tower" — is wrong. Both
artifacts carry it:

| artifact | total tensors | `vision_tower.*` tensors | `model_type` | `vision_config` |
|---|---|---|---|---|
| stock-4bit | 1221 | **297** | `qwen3_5` | present |
| OptiQ-4bit | 1221 | **297** | `qwen3_5` | present |

Identical. The weights are there. The difference is in `config.json`:

| artifact | `quantization` keys |
|---|---|
| stock-4bit | `group_size`, `bits`, `mode` — one uniform rule |
| OptiQ-4bit | those three **plus 249 per-layer entries** |

OptiQ is a mixed-precision format: it records a per-layer quantization map at 4 and 8 bits. And
that map covers the language model only:

```
per-layer quantization entries: 249
  vision_tower entries:   0
  language_model entries: 249
  bits used: [4, 8]
```

**mlx-community's OptiQ-4bit conversion of Qwen3.5-4B quantizes the language model and leaves
the vision tower out of its per-layer map entirely.** vMLX loads this checkpoint through its
multimodal path (`models.mllm`), builds a `vision_tower`, consults the quantization map for its
parameters, finds no entry for any of them, and reports 297 missing.

The other three runtimes load the same file. They either treat the checkpoint as text-only or
fall back to the global `group_size`/`bits`/`mode` for layers the map does not name. That
fallback is not verified here and should not be assumed — what is established is that the
artifact loads in three runtimes and not the fourth, and why the fourth refuses.

**This is a format × runtime interaction, not a property of either alone.** It is invisible on
the format axis, because oMLX loads all four formats. It is invisible on the runtime axis,
because vMLX loads three of four formats. Only the grid shows it, and only reading the log
explains it. A cell marked "incompatible" without that log would have been filed as "vMLX
cannot read OptiQ", which is false.

## Cold load, four formats, runtime held constant

> **CORRECTED — this section's ranking is wrong.** See
> `2026-09-15-cold-load-is-not-one-quantity.md`. oMLX loads its weights lazily on the first
> request, so its `cold_load_s` is a time-to-listening, not a load time, and it hides
> 3.08-3.85 s in request #1. True time-to-first-token puts mlx-lm first at 3.39 s and oMLX
> third at 6.63 s — the runtime named fastest below is second slowest. The figures in the
> table are accurate as `cold_load_s`; the comparison drawn from them is not.

The first genuinely comparable figure this project has produced. Each runtime loaded the same
four artifacts; the runtime is the only thing that varies within a column.

| runtime | median cold load | n |
|---|---|---|
| oMLX 0.6.4 | **2.18 s** | 4 |
| mlx-optiq 0.5.6 | 3.23 s | 4 |
| mlx-lm 0.31.3 | 3.85 s | 4 |
| vMLX 1.6.59 | **16.13 s** | 3 |

vMLX is **7.4× slower to load** than oMLX, consistently, across three different artifacts
(18.13 / 16.13 / 16.10 s). This is a load-time figure only and says nothing about throughput —
a runtime that starts slowly may still generate fastest, which is exactly why the grid reports
cold load as its own column rather than folding it into a score.

## Four runtimes, four output conventions, one model

Every ✓ cell returned coherent text, but not through the same channel or shape:

| runtime | behaviour at `max_tokens=24` |
|---|---|
| mlx-lm | reasoning channel only, zero content deltas — still inside `<think>` |
| oMLX | 3 deltas, reasoning mirrored into content |
| mlx-optiq | answers directly — its `:no-think` model-id variant |
| vMLX | reasoning channel only, like mlx-lm |

The same prompt, the same weights, four different stream shapes. Every channel-handling fix
made earlier today — the `reasoning` field name, the mirror dedupe, mirrored-stream timing, the
two-delta rate domain — is load-bearing for this grid. Without them, two of these four runtimes
would publish no figures and a third would publish wrong ones.

## A flaw in the probe itself, recorded rather than hidden

The probe's `verdict` field keys off `Observation.ok`, which is `False` when the content channel
is empty. So mlx-lm and vMLX cells — which loaded fine and produced coherent reasoning — were
labelled `answered: chat stream produced no content`. The label is wrong; the data beside it
(`coherent: true`, the text itself) is right, and the table above is read from `coherent`.

The same content-versus-reasoning distinction that produced three separate defects earlier in
the day was walked into again while writing the instrument to check for them. A 24-token budget
also guarantees a thinking model never exits `<think>`, which a larger budget would have avoided.

## What this settles for Phase 3

- The format axis holds at oMLX: it loads **4 of 4** formats, and fastest.
- The runtime axis holds at any of the four formats: **4 of 5 runtimes** load each, pending the
  Osaurus column.
- The grid has exactly **one** structural hole in its probed region, and it is explained.
- JANG_4S is still downloading. Its row is expected to be Osaurus and vMLX only, and that
  expectation is a prediction — the record above is what predictions in this project are worth.

## Reproducing

Run `probe_grid.py` with `~/.local/share/ohyesmlx/mlx-lm-0.31.3/bin` on `PATH`, and quit
`osaurus.app` first. `READY_TIMEOUT_S` is lowered to 180 s: a cell needing fifteen minutes to
load is a no for grid purposes.

---

# Addendum — the full 25-cell grid, after the Osaurus and JANG rows

Written after the initial 20-cell probe, once `osaurus.app` released port 1337 and JANG_4S
finished downloading. **20 of 25 cells are live.**

| format | mlx-lm 0.31.3 | oMLX 0.6.4 | mlx-optiq 0.5.6 | vMLX 1.6.59 | Osaurus 0.25.3 |
|---|---|---|---|---|---|
| stock-4bit | ✓ | ✓ | ✓ | ✓ | ✗ not registered |
| oQ4 | ✓ | ✓ | ✓ | ✓ | ✓ |
| oQ4e | ✓ | ✓ | ✓ | ✓ | ✓ |
| OptiQ-4bit | ✓ | ✓ | ✓ | ✗ vision map | ✓ |
| JANG_4S | ✗ shape | ✗ shape | ✗ shape | ✓ | ✓ |

## The JANG row settles a founding decision at the tensor level

`STATE.md` has recorded since the founding session that JANG is a runtime+format bundle rather
than an axis point. That rested on repo cards, three unmerged oMLX PRs, and a maintainer's
objection — documentary evidence. It is now measured.

Three independent runtimes reject JANG_4S with the **byte-identical** error:

```
ValueError: Expected shape (248320, 640) but received shape (248320, 320)
           for parameter language_model.model.embed_tokens.weight
```

`embed_tokens` is packed at **half** the expected width. This is not a precision variant that a
generic loader reads badly — the tensor geometry differs, so a loader either implements JANG
unpacking or sees a malformed file. oMLX tried both of its paths and failed both: the VLM path
reported 1221 parameters not in the model, then the LLM fallback hit the same shape error.

Two runtimes load it. vMLX logs `JANG v2 VLM loaded in 1.2s` through `utils/jang_loader`, having
`Pre-fixed 217 module(s) with mixed-precision bit widths`. Osaurus serves it and answered
coherently.

**Two JANG runtimes is what makes JANG studiable.** A format that loads in exactly one runtime
can never be compared without moving two variables. With vMLX and Osaurus both serving JANG_4S,
`JANG on vMLX` against `JANG on Osaurus` is the runtime axis with the format held constant —
the only legal single-variable study JANG can appear in, and it exists only because both were
kept.

## Every runtime advertises models it cannot serve

Three for three, now measured rather than suspected:

| runtime | lists it? | serves it? | how the truth surfaces |
|---|---|---|---|
| mlx-lm 0.31.3 | yes | no | documented in `runtimes.py`: `/v1/models` echoes `str(Path(--model).resolve())` off disk |
| oMLX 0.6.4 | yes | no | `cold_load_s = 2.15 s` recorded, then **HTTP 409** on the chat request |
| Osaurus 0.25.3 | yes | no | lists `qwen3.5-4b-4bit`, answers `not installed or registered with any provider` |

The existing rule — *readiness comes from the log, never the port* — is not strong enough.
**And never the model list either.** oMLX is the sharpest case: it passed `await_ready`, returned
a handle, and published a cold-load figure for weights it had already failed to load. A FAIL
cell would still have been honest, but it would have carried a fabricated 2.15 s load time into
the record.

## Osaurus needs a name, not a path

Every Osaurus cell failed with `osaurus exited before it served 'osaurus/stock4bit'`. Osaurus
serves from its own catalogue and names models after the **repo, lowercased**. Live
`GET /v1/models` returns:

```
qwen3.5-4b-4bit, qwen3.5-4b-oq4, qwen3.5-4b-oq4e, qwen3.5-4b-optiq-4bit,
qwen3.5-4b-jang_4s, nanbeige4.2-3b-jang_6m, ornith-1.0-35b-jang_4m, foundation
```

`Osaurus.model_id_candidates` builds from `name_forms(artifact_dir)`, and in Hugging Face cache
layout that directory is `.../models--<org>--<name>/snapshots/<commit-hash>` — so every
candidate it generates is a commit hash, which Osaurus never answers to. Driven by hand with
the right id, Osaurus served oQ4, oQ4e, OptiQ and JANG_4S, all coherent.

Osaurus also discovers the Hugging Face cache on its own: all five formats appeared in its
catalogue without being copied into `~/MLXModels/`. A symlink placed there during
investigation was removed and changed nothing.

## What the grid costs and what it yields

Five formats of Qwen3.5-4B total **15.6 GB**. Twenty live cells, on a 4B model that most
runtimes load in 2–4 seconds. Against that: four rows that are clean runtime comparisons, five
columns that are clean format comparisons, and one best cell that answers what to actually run.

The two holes are both explained rather than empty, which is the point of probing instead of
predicting.


# CORRECTED — oMLX streams; the harness was reading the wrong channel

Date: 2026-09-15. Machine: MacBook Pro, M2 Max, 64 GiB, macOS 26.6.2.

> **This document's original title and conclusion were wrong.** It was first written as
> "oMLX 0.6.4 does not stream, and the harness nearly published 1.5 billion tok/s", and it
> claimed on the evidence of `omlx serve --help` that no flag could make oMLX stream
> incrementally. That claim is false. oMLX streams fine. The original text is preserved
> below under "What the first version claimed", because how the wrong conclusion was reached
> is the more useful half of this document.

## The correction

oMLX 0.6.4 streams incrementally — in the **`reasoning_content`** channel. It then emits the
entire completed text once more as a single `content` delta at the end. Timed directly, one
request, `max_tokens=128`:

| channel | deltas | first | last | window |
|---|---|---|---|---|
| `reasoning_content` | **15** | 0.685 s | 2.352 s | **1.668 s** |
| `content` | 1 | 2.352 s | 2.352 s | 0.000 s |

`docs/interfaces.md` pins `ttft_s` as *"send → first CONTENT delta. Reasoning deltas
excluded."* For this runtime that is the one channel carrying no timing information at all.
The harness was not measuring a runtime that fails to stream; it was reading the only channel
where the streaming does not appear.

### What the harness published, and what is true

| | published | actual |
|---|---|---|
| TTFT | 5.499 s | **0.685 s** in the probe above — roughly 8x lower |
| decode window | 1.66e-07 s (float noise) | **1.668 s** across 15 deltas |
| decode tok/s | 1,532,954,517.6 | a real, ordinary rate |
| aggregate tok/s | 44.9 | 44.9 — unaffected, it never used per-delta timing |

The reported TTFT was wrong by an order of magnitude **in oMLX's disfavour**. Had the runtime
axis shipped on that number, it would have published a false and damaging claim about a
runtime that was performing well.

### Consequences

- **No hunt for a different runtime is needed.** oMLX loads all four formats and can carry
  the full metric set, decode tok/s and ITL included. The format axis is unaffected.
- **The `>= 2 content deltas` guard in `report.py` stays.** A one-delta stream genuinely has
  no rate, and omitting it is correct. oMLX simply is not a one-delta stream once the right
  channel is read.
- **`transport.py` must take timing from the reasoning deltas when a runtime mirrors.** That
  is the actual fix, and it is separate from the report guard.
- **The mirroring dedupe already shipped is still correct** — it addressed token *counting*.
  Timing is a second, independent consequence of the same mirroring.

## What the first version claimed

Verbatim, the reasoning that produced the wrong answer:

> No flag changes this. `omlx serve --help` exposes `--sse-keepalive-mode`,
> `--max-concurrent-requests`, `--embedding-batch-size`, cache and memory controls, and
> nothing that sets streaming granularity.

Every fact in that paragraph is true. `omlx serve --help` really does expose no
streaming-granularity flag. The conclusion drawn from it — that oMLX therefore cannot stream
incrementally — does not follow, and was not checked before being written down.

## How the error was actually found, and what would have found it sooner

Three cheap checks, none of which had been run:

**1. The settings file, not the flags.** `~/.omlx/settings.json` holds 17 top-level keys
covering scheduler, cache, memory, and sampling — a configuration surface much larger than
the command line. (It contains no streaming key either, but it establishes that `--help` is
not the whole story.)

**2. The shipped source.** oMLX bundles readable Python at
`/Applications/oMLX.app/Contents/Resources/omlx/`. One grep finds it:

```
omlx/output_collector.py:188:    This is used to implement stream_interval batching,
omlx/output_collector.py:192:    stream_interval: int = 1
omlx/engine_core.py:157:    stream_interval: int = 1  # Tokens to batch before streaming (1=every token)
```

A per-token streaming mechanism, defaulting to every token, in a runtime just declared
incapable of streaming. That single grep contradicts the published conclusion outright.

**3. A longer probe.** The original probe used `max_tokens=8` — small enough that the whole
response plausibly fit one chunk, so one content delta looked like proof of non-streaming
rather than a sample size of one. At 96 and 128 tokens the structure is unmistakable: 11 and
15 reasoning deltas against 1 content delta.

**The general lesson.** `--help` documents the command line. It does not document the
runtime. These are GUI applications shipping a CLI as one entry point among several, and
their real configuration surface spans flags, a settings file, per-request API fields, and
behaviour visible only in the shipped source. A negative capability claim — "this tool
*cannot* do X" — needs evidence from the source or the settings, not the absence of a flag.

A claim that a tool cannot do something should be held to a higher standard than a claim
that it can, because the first one closes off investigation and the second invites it.

## The part of the original finding that survives

The `PASS` really did publish 1,532,954,517 tok/s and an ITL of exactly 0.0000, and the guard
added in response is correct and stays. `content_event_count` really was recorded in every
observation from the first live run onward, and nothing read it — that remains the strongest
argument for a startup capability probe rather than a field nobody consults.

And the underlying shape holds, just with a different culprit: **the harness published a
measurement-shaped number that measured something other than what its column name claimed.**
The runtime was fine. The instrument was pointed at the wrong channel.

## Reproducing

```
omlx serve --model-dir <catalog> --host 127.0.0.1 --port 8106 \
  --max-concurrent-requests 1 --memory-guard off --no-cache --api-key probe-key
```

Then time both channels separately — counting deltas per channel is the whole test, and
`max_tokens` must be large enough that a streaming runtime would produce many:

```
curl -sN http://127.0.0.1:8106/v1/chat/completions \
  -H 'Content-Type: application/json' -H 'Authorization: Bearer probe-key' \
  -d '{"model":"probe-model","messages":[{"role":"user","content":"Explain confounded variables in three sentences."}],
       "max_tokens":128,"stream":true,"temperature":0,"stream_options":{"include_usage":true}}'
```


# Phase 4 — the 256-expert question, answered

Date: 2026-09-15. Machine: MacBook Pro, M2 Max, 64 GiB unified memory, macOS 26.6.2.
Run directories (gitignored): `results/20260915T143057Z-runtime/`,
`results/20260915T144415Z-runtime/`, `results/20260915T144831Z-runtime/` — three runs of the
same two cells, because the first two were invalidated by harness defects the runs themselves
exposed. The third is the result.

**Zero downloads.** Both cells serve one artifact already in the Hugging Face cache.

## The question

`docs/research/2026-09-14-oq-portability-spike.md` recorded that stock `mlx_lm.server` loads
`Jundot/Qwen3.6-35B-A3B-oQ4-mtp` — a 256-expert MoE — in about four seconds, returns HTTP 200,
generates at full throughput, and produces mixed-script token salad with replacement
characters. Nothing raised. Nothing timed out.

That finding left one thing unresolved, and it was the largest open risk in the project: **is
the oQ4 quantization broken, or is stock mlx-lm executing it wrong?** If the format is at
fault, the entire format axis — the v1 milestone — is built on a variable that can silently
corrupt a model, and every oQ4 row in every future table is suspect. If the runtime is at
fault, the format axis is clean and the finding is a runtime-axis result about one server.

`STATE.md` carried it as a blocker: *"Stock mlx-lm executes a 256-expert oQ4 MoE incorrectly —
loads and generates at speed, output is token salad. Invalidates any speed number taken
without a coherence check."*

## The experiment

Vary one thing: the serving runtime. Hold everything else constant — not "an equivalent
artifact" but *the same directory*, 21,636,566,952 bytes, read by both runtimes:

```
ohyesmlx run --study runtime --cells \
  oq4__mlxlm=~/.cache/huggingface/hub/Jundot/Qwen3.6-35B-A3B-oQ4-mtp,\
  oq4__omlx=~/.cache/huggingface/hub/Jundot/Qwen3.6-35B-A3B-oQ4-mtp
```

Same prompt, same 256-token budget, temperature 0, seed 0, three warmups and five measured
requests across two visits. `--study runtime` makes the CLI refuse a selection that varies the
format, so the held-constant variable is enforced rather than promised.

## The answer: the runtime, not the format

| runtime | version | verdict | what it produced |
|---|---|---|---|
| stock mlx-lm | 0.31.3 | **FAIL — incoherent output: replacement characters** | `oughwet. �ت .10. A of  �cho6...不会GV作者 conclusion }s leteton324 thouch� galinging on2 As高薪 �生活11` |
| oMLX | 0.6.4 | **coherent** — `is_coherent` returns `(True, "ok")` | see below |

oMLX, on the same bytes:

> Here's a thinking process:
>
> 1. **Understand User Query:**
>    - **Core Question:** Why can't a benchmark that changes two variables at once attribute a
>      difference to either one?
>
> 2. **Identify Key Concepts:**
>    - This is about experimental design, specifically the principle of *ceteris paribus* (all
>      else being equal) and *confounding variables*.
>    - When two variables change simultaneously, their effects are *confounded* or *entangled*.
>    - You cannot isolate the causal effect of either…

That is a correct and relevant answer to the prompt, produced from the artifact stock mlx-lm
turns into salad.

**The oQ4 quantization of this checkpoint is sound. Stock mlx-lm 0.31.3 executes it
incorrectly.** The failure is runtime-specific.

### Why this matters more than one model

The format axis is the v1 milestone, and it was resting on an unexamined possibility that oQ4
could silently corrupt a model. It cannot — at least not here, and here is the hardest case
available: 256 experts, the checkpoint that actually failed. Phase 3 can proceed without the
caveat that its oQ4 column might be measuring a broken quantizer rather than a quantizer.

It also relocates the original finding. It is not "oQ4 is dangerous". It is "stock mlx-lm
mis-executes high-expert-count MoE routing", which is a **runtime-axis** result — and one that
a speed-only harness would have published as its fastest, healthiest row.

### What it does not establish

- **One checkpoint, one runtime pair.** Two runtimes on one 256-expert model. It does not
  characterise mlx-lm across expert counts, and it does not clear oQ4 for checkpoints not
  tested. The standing caveat for Phase 3 still holds: LFM2.5-8B-A1B has 32 experts, this
  checkpoint has 256, and a clean LFM2.5 result validates the machinery without exonerating
  stock mlx-lm on high-expert MoE.
- **No speed comparison.** Neither cell published a tok/s figure, for different reasons. See
  below.
- **No root cause.** *That* mlx-lm mis-executes this checkpoint is established. *Why* — routing,
  expert indexing, a dtype assumption in the MoE kernel — is not investigated here.

## The three runs, and why there were three

The first live run of this harness ever executed is documented in
`docs/research/2026-09-15-first-live-run.md`. Each run exposed a defect and was invalidated
by it; each defect was fixed before the next.

**Run 1** — both cells FAIL, no verdict. `transport.py` read `delta.reasoning_content`; mlx-lm
0.31.3 spells it `delta.reasoning`, so every reasoning delta was discarded and the stream
looked empty. The cell was labelled `STILL_THINKING` — "no output is not bad output" — when in
fact the output existed, was in the other channel, and was salad. oMLX returned HTTP 401 to
every measured request: `chat()` never sent an `Authorization` header, though the readiness
probe did. Its reported peak of **119 MB for a 21.6 GB artifact** is the signature of a server
that never loaded any weights.

**Run 2** — mlx-lm now correctly reads `incoherent output: replacement characters`, with the
salad preserved on the record. oMLX authenticated, loaded in 4.8 s, and generated 256 tokens
per request at 73 tok/s by its own log — then every request failed inside the harness with
`RuntimeError: neither tokenizers nor transformers is available`. Environmental: the run
virtualenv had no tokenizer library. Installed, no code change.

**Run 3** — the result above.

## The remaining defect: oMLX emits every token twice

Run 3's oMLX cell is coherent but still `FAIL`, on a token-accounting reason:
`no content completion tokens from token_source='none', so decode tok/s is undefined`.

Every one of the five observations had `len(text) == len(reasoning_text) == 1240`, exactly.
A direct probe against oMLX, outside the harness, shows why — it sends the same string twice,
in two consecutive chunks:

```json
{"choices":[{"delta":{"reasoning_content":"\nThinking Process:\n\n1.  **"}}]}
{"choices":[{"delta":{"content":"\nThinking Process:\n\n1.  **"}}]}
{"usage":{"prompt_tokens":13,"completion_tokens":8,"total_tokens":21}}
```

Eight tokens were generated and `usage` says eight. The harness counted the reasoning copy and
the content copy, reached sixteen, and `resolve_token_accounting` correctly refused to
reconcile 8 against 16 — returning `INCOMPARABLE_TOKEN_ACCOUNTING` and publishing nothing.

**The refusal is the harness working as designed.** `token_counter.py` exists precisely to
refuse a count that does not reconcile with the runtime's own total, because the predecessor
project shipped a token path that no caller used and reported `None` in 100% of runs. What
went wrong is upstream of the refusal: the duplicate should never have been counted twice.

Worth recording alongside it — the same `usage` block reports
`"generation_tokens_per_second": 15286.61`, derived from a `generation_duration` of `0.0`.
A server's self-reported rate is not a measurement.

## Reproducing

```
PATH=/tmp/mlxspike/bin:$PATH python -m ohyesmlx.cli run --study runtime \
  --cells oq4__mlxlm=<artifact>,oq4__omlx=<artifact>
```

The raw oMLX probe that settled the duplication question:

```
omlx serve --model-dir <catalog> --host 127.0.0.1 --port 8105 \
  --max-concurrent-requests 1 --memory-guard off --no-cache --api-key probe-key
curl -sN http://127.0.0.1:8105/v1/chat/completions \
  -H 'Content-Type: application/json' -H 'Authorization: Bearer probe-key' \
  -d '{"model":"probe-model","messages":[{"role":"user","content":"Say hello."}],
       "max_tokens":8,"stream":true,"temperature":0,
       "stream_options":{"include_usage":true}}'
```

`mlx-lm` 0.31.3 is not on `PATH` — it lives only in `/tmp/mlxspike`, which will not survive a
reboot, and it is the control arm of every runtime-axis run.


# Prior art: published MLX serving-runtime and quantization-format benchmarks

**Date:** 2026-09-15
**Question:** Who has already published what we intend to publish, and did anyone hold one
variable constant while doing it?
**Method:** Web research only. All pages were fetched 2026-09-15. Every factual claim below
carries the URL it came from. Anything I could not verify is marked **UNVERIFIED**.

**Verdict in four lines:**

1. **Runtime axis — almost claimed.** `mlx-Chronos` is a real, protocol-driven,
   same-model/same-quant cross-engine benchmark with a public leaderboard. It covers five
   engines we care about (mlx-lm, oMLX, vllm-mlx, Rapid-MLX, Ollama's MLX backend) but not
   Osaurus, optiq, vMLX/MLX Studio, or LM Studio's MLX engine. Nobody has published the
   specific matrix we plan.
2. **Format axis — unclaimed.** No published study holds the runtime constant while varying
   three or more MLX quantization formats with a stated protocol. The closest artifacts are
   a third party's JANG-vs-oQ4-vs-MLX-vs-bf16 task-accuracy run, and a KL-divergence study
   that explicitly found one JANG quant is *not comparable to its base model at all*.
3. **The extraordinary claim is real, quotable, unreproduced, and internally inconsistent.**
   The "JANG 2-bit 74% vs MLX 4-bit 26.5%" headline on MiniMax-M2.5 contradicts its own
   supporting analysis, which says the MLX baseline is broken rather than beaten.
4. **A methodology to align with exists**, but it benchmarks runtimes as *libraries or
   single engines*, not the six server runtimes we named — so it anchors our definitions
   (TTFT, decode vs end-to-end throughput, percentiles, cold start) without pre-empting our
   comparison.

---

## 0. How to read this document

- **"One variable" test.** For every study I record what was held constant and what varied.
  The bar this project sets is: *a comparison that changes both the runtime and the
  quantization format cannot attribute a difference to either*. Several studies below fail
  that test and say so themselves; those are marked.
- **UNVERIFIED** means: a page asserts it, I could not check it against a second source or
  against raw data. It does not mean false.
- **"No prior art found"** means: I searched and did not find it. It is not proof of
  absence.
- The ecosystem moves fast. Versions and dates are recorded with each claim because several
  of the disputes below are version-dependent.

---

## 1. Q1 — Prior art

### 1.1 Runtime-axis studies (runtime varies; model + quant held constant)

#### 1.1.1 mlx-Chronos — the closest thing to a formal protocol

A CLI benchmark suite and community leaderboard for MLX inference engines on Apple Silicon.

- **Engines supported:** `mlx-lm`, `oMLX`, `vllm-mlx`, `Rapid-MLX`, Ollama's MLX backend.
  ([discussion](https://github.com/jundot/omlx/discussions/1391),
  [repo](https://github.com/igurss/mlx-chronos),
  [methodology](https://github.com/igurss/mlx-chronos/blob/main/docs/methodology.md))
- **Measures:** cold TTFT, cached TTFT, request throughput, decode throughput, system RAM
  peak, engine RSS (diagnostic only), thermal state, power source, phase timings; mean,
  stddev, min, max per repeated metric; p95 only at ≥20 trials. All from the client side
  against an OpenAI-compatible endpoint.
- **Methodology details that matter:** fixed prompt pool with a unique prompt per trial;
  `temperature=0.0`, `top_p=1.0` pinned; sustained profile uses one 1000-token generation;
  warmup 2 calls discarded; baseline profile 5 trials with `max_tokens=100`, sustained 1
  trial with `max_tokens=1000`; a cross-run cooldown field
  (`meta.elapsed_since_last_benchmark_seconds`); a SHA-256 integrity seal over the result
  JSON; public leaderboard rows require `usage.completion_tokens`, Low Power Mode off,
  error-free RAM/thermal sampling and a model reference URL.
- **One-variable test:** **Passes within its scope.** Same model and same quantization
  across engines. The methodology document is explicit that cross-engine TTFT is
  *client-observed* latency and "should be read as end-to-end user-observed latency rather
  than pure model latency," and that engine version is recorded because non-comparable
  versions are the main comparability risk.
- **Known limits, stated by the project:** engine RSS "is not a public comparison metric
  because it may not include model weights or Metal allocations mapped outside ordinary
  process RSS"; the trust model states plainly that submissions are community records, not
  hardware-attested measurements.
- **A published result set exists** (M1 Max 64 GB; rapid-mlx 58.8 ±2.2 tok/s, omlx 50.5
  ±0.4, mlx-lm 49.6 ±2.3, ollama 45.4 ±3.2; process RSS 3.5–3.7 GB for the MLX engines vs
  44.6 GB for Ollama; System RAM peak 37.5–57.0 GB). The author adds an honest caveat that
  omlx's caching design is a mismatch with a single-request repeated-prompt metric, "not a
  caching defect."
  ([source](https://bright-lotus-8q5y.here.now/))
- **Why this matters to us:** it is our nearest competitor on the runtime axis, and the
  discussion thread around it is where the field's honest objections live: quantization
  identity ("not all 4bit are the same 4bit, names lie"), thermal/power drift, macOS version
  effects, and the argument that no cross-machine leaderboard can be more than directional.
  ([thread](https://github.com/jundot/omlx/discussions/1391))

#### 1.1.2 `ywchiu/mlx_benchmark_lab` — a careful one-shot runtime comparison

Four MLX engines on one model, five runs per cell, raw JSONL published.

- **Setup:** Apple M5 Max, 64 GB; `mlx-community/Qwen3.6-35B-A3B-4bit` for rapid-mlx,
  omlx, dflash-mlx, mlx-vlm; seven context lengths 64 → 32,768; five repeats per cell,
  warmup discarded; prefix caching explicitly disabled on every engine; one server at a
  time on port 8765.
- **Result shape:** dflash-mlx lead at every context; omlx the flattest degradation curve
  and lowest TTFT variance; at 32K, dflash 121.2 tps vs omlx 82.1 vs rapid-mlx 72.3 vs
  mlx-vlm 67.7.
- **One-variable test:** **Passes for the four-engine row**; a fifth engine (mtplx) was run
  on a *different model* and is flagged by the authors as "not directly comparable."
- **Exemplary honesty:** a later dflash re-test used `cooldown=60` while the other four
  columns were measured at `cooldown=2`, and the README says their long-context numbers
  "would be somewhat higher if re-tested at the longer cooldown." The limitations section
  also records that `/no_think` was only partially honoured, so two engines' decode numbers
  mix reasoning and content tokens. That is the class of caveat our report format should
  make impossible to omit.
  ([repo](https://github.com/ywchiu/mlx_benchmark_lab),
  [write-up](https://www.largitdata.com/en/blog/mlx-inference-benchmark-apple-m5-max/))

#### 1.1.3 Five backends compared (MLX, llama.cpp, Ollama, omlx, vLLM Metal)

- **Setup:** Qwen3.5-9B, "same 4-bit quantized weights (MLX-format or Q4_K_M GGUF)", three
  repetitions after a warm-up.
- **Results:** MLX 25 tok/s / 396 ms TTFT; llama.cpp 15.3 / 196 ms; Ollama 13.8 / 470 ms;
  omlx ~20 / 968 ms; omlx the only backend that batches under concurrency (1.29–1.40× from
  concurrency 1→4).
- **One-variable test:** **Partially fails, and the article says why.** MLX-format 4-bit and
  Q4_K_M GGUF are different quantization schemes; "same 4-bit" is a nominal match only. It
  also states that TTFT for the MLX *library* path and for the HTTP engines "are not
  directly comparable" because one includes network/serialization overhead.
  ([source](https://jaesolshin.com/posts/apple-silicon-llm-backends/))

#### 1.1.4 `mlx-lm` vs oMLX — the cleanest example of a controlled runtime study

- **Setup:** one model (`gemma-4-31b-it-4bit`) served identically to both engines on a Mac
  Studio M4 Max 64 GB; mlx-lm 0.31.3, oMLX 0.4.4.
- **Findings:** warm prefill is a tie (3.45 s vs 3.65 s); single-stream decode is a tie
  (22 vs 25 tok/s); four-request concurrency went *against* the author's thesis (mlx-lm
  2.12× vs oMLX 1.23×, one run); and the one real difference is restart behaviour — after a
  server restart oMLX restored a seeded 8k prefix from SSD in 7.2 s where mlx-lm
  "recovered only about half the way back from a cold prefill."
- **Methodology value:** four documented traps that each produced a fake number first —
  mlx-lm caches prompts (killing naive cold-vs-warm TTFT tests), mlx-lm's server buffers
  rather than streams so inter-token timing is meaningless against it, oMLX lazy-loads so
  its first request times a disk read, and oMLX's SSD cache persists across benchmark runs
  so "cold" must be cleared from `~/.omlx/cache` first.
- **One-variable test:** **Passes**; both engines share the same inference engine, which the
  author notes explicitly ("these two tools are not peers").
  ([source](https://medium.com/macoclock/mlx-lm-vs-omlx-i-was-wrong-about-the-winner-8f36be328069))

#### 1.1.5 arXiv 2511.05502

Cross-reference §4.1 — it is the only peer-style comparative runtime study, but it compares
MLX-as-a-library against MLC-LLM, llama.cpp, Ollama and PyTorch MPS, not the server
runtimes we named.

### 1.2 Format-axis studies (quantization format varies)

#### 1.2.1 `deepsweet/mlx-eval` — the most rigorous format comparison found

A KL-divergence evaluation of MLX quantizations on two base models, by an oMLX contributor,
run against Qwen3.6-35B-A3B and Qwen3.6-27B.

- **Measured:** mean KLD, KLD p95/p99, perplexity, top-1 next-token accuracy, model RAM.
  Prompt is a 131,072-token stress corpus (16 windows × 8,192) with deliberate domain
  shifts; the author states he does **not** smooth these over: "every quantization is
  evaluated under the same conditions."
- **Formats covered:** stock affine Q2–Q8, oQ 2–8, Unsloth UD-MLX 3/4-bit, ParoQuant,
  JANG/JANGTQ 2 and 4, OptiQ 4-bit. Tools: mlx-vlm 0.4.4 for stock/UD/PARO/OptiQ, oMLX
  0.3.6/0.3.8 for oQ, jang-tools loaders for JANG.
- **Headline numbers (Qwen3.6-35B-A3B, KLD mean / RAM GiB):** Q4 0.088 / 18.17; oQ4 0.047 /
  18.83; JTQ4 0.035 / 17.50; OptiQ-4bit 0.028 / 19.67; UD4 0.029 / 19.32; PARO 0.059 /
  17.37.
- **The finding that matters most to us:** a dense-model caveat states plainly that
  `Qwen3.6-27B-JANG_4M` "has nothing to do with the original Qwen3.6-27B log probabilities,
  meaning it's *another separate entity* on its own, but not the Qwen3.6-27B anymore.
  Therefore, it's not directly comparable with anything else the way I do it."
  ([results](https://github.com/deepsweet/mlx-eval/blob/main/results/README.md),
  [statement in PR #364](https://github.com/jundot/omlx/pull/364))
- **One-variable test:** **Passes on the format variable** (same base models, one shared
  evaluation harness, one loader per format as a necessity of the format itself). It is a
  distribution-fidelity study, not a task-accuracy study, and it is single-machine,
  single-run per cell.
- **Why this is the closest prior art to our Study B:** it varies the format while holding
  the evaluation constant — and it produces a comparability *failure*, not just a ranking.
  Any format-axis study we publish should expect and test for the same possibility.

#### 1.2.2 AlexTzk — third-party JANG vs oQ4 vs MLX vs bf16 on matched base models

- **Setup:** MacBook Pro M3 Max 128 GB; five benchmarks with full sets — MMLU 1000,
  TruthfulQA 817, HumanEval 164, LiveCodeBench 100, MBPP 200. Raw per-model JSON/CSV
  published.
- **Headline claims:** on `Nemotron-Cascade-2-30B-A3B`, JANG_4M 79.9% HumanEval vs oQ4
  39.0% "on identical base weights"; on Qwen3.5-35B-A3B, JANG_4K 56.1% HumanEval vs bf16
  29.9% and oQ4 37.2%; but bf16 dominates MBPP (75% vs 33.5%) and LiveCodeBench (41% vs
  18%), and MMLU/TruthfulQA are "essentially tied across all four variants — all sitting in
  the 22–25% range."
  ([Medium](https://medium.com/@alexandru_vasile/i-benchmarked-every-quantization-method-for-apple-silicon-llms-heres-what-actually-wins-7b3e7edff4ef),
  [repo](https://github.com/AlexTzk/MLX-benchmarks))
- **Suspicious results the author himself flags:** a quantized model *beating* full
  precision on HumanEval is "something that shouldn't be possible unless something else is
  going on"; and every Qwen3.5-35B variant including bf16 scores near the 25% chance line on
  MMLU, which he attributes to the base model rather than the quantization.
- **One-variable test:** **Passes for the JANG-vs-oQ4 pairs** (same base model, same
  hardware, same harness); **fails elsewhere** — several columns compare different base
  models (Cascade-30B vs Super-120B vs Qwen3-Coder-Next).
- **Where the raw data lives:** per-model benchmark JSON in the repo, and the oMLX PR thread
  where the work was first posted; the author offered raw JSON for the disputed MiniMax runs
  but did not publish the numbers in text.
  ([PR #364](https://github.com/jundot/omlx/pull/364))

#### 1.2.3 oQ's own benchmark table (oMLX vendor)

- **Setup:** Qwen3.5-35B-A3B; MMLU 300, TruthfulQA 300, HumanEval 164 (full), MBPP 300;
  mlx-lm vs oQ at 2, 3 and 4-bit. Reported: at 2-bit MMLU 14.0% (mlx-lm) vs 64.0% (oQ); at
  4-bit 79.7% vs 83.3%.
- **One-variable test:** **Passes on format** (same model, same runtime family; the
  comparison is *within* the same engine ecosystem), but it is **vendor self-reported**
  and the pipeline for the mlx-lm baseline is not documented.
- **Methodology published:** sensitivity measured as normalized MSE between float and
  quantized outputs; GPTQ via Hessian compensation; mandatory protections (lm_head, MoE
  router, shared-expert gate at 8-bit; vision fp16; SSM state fp32); 600-sample calibration
  set. ([doc](https://github.com/jundot/omlx/blob/main/docs/oQ_Quantization.md))

#### 1.2.4 optiq's Capability Score (vendor)

Cross-reference §3.3. Six tasks, one unweighted mean, published methodology. Self-reported
for its own format; no independent replication found.

#### 1.2.5 JANG's own tables

Cross-reference §2. These vary format *and* runtime together (JANG needs its own loader) and
are the subject of the dispute documented in §2.4.

#### 1.2.6 Individual quantization investigations

- **`n8programs` — MLX quantization scaling laws.** Fixed model (Qwen3-4B-2507-Instruct) on
  an M3 Max; perplexity on enwik8, 256 windows × 512 tokens; fits `a·log2(bpw)^b + c` with
  R² 0.99996 across 6 points; finds DWQ worth "roughly 0.613 bits" of effective precision;
  tested dynamic quant and a combined recipe (`mlx-community/Qwen3-4B-Instruct-2507-DDWQ`).
  Includes an honest correction: an earlier version's code "underestimated standard errors
  by an order of magnitude." One model, one runtime, perplexity only.
  ([source](https://n8programs.substack.com/p/an-examination-of-mlx-quantization))
- **`leriomaggio/mlx-quant-bench`.** Precision ladder bf16/8/4/3-bit on Mistral 7B, M3 Pro
  36 GB; TTFT, decode tok/s, load time, peak GPU memory, per-prompt outputs; discloses that
  TTFT is approximated by running two `generate()` calls (which double-counts prefill), and
  warns that "single-sample variance dominates precision-induced quality differences on this
  prompt suite." ([source](https://github.com/leriomaggio/mlx-quant-bench))
- **`Incept5/MacOS-MLX-Benchmark`.** Precision-ladder plus quality harness: TTFT,
  prefill/decode tok/s, tokens/watt, WS2 sliding-window perplexity, MMLU-Pro (logprob
  scoring, 4 size tiers), output similarity vs the bf16 reference, batch throughput at
  1/4/8/16, thinking on/off comparison. Methodology: 2 warmups discarded, 10 measured runs
  (3 for ≥8B), temperature 0, variant order randomised "to reduce thermal bias," 95% CI and
  CV% reported with CV% > 10% flagged unreliable, prompts padded to equal context.
  ([source](https://github.com/Incept5/MacOS-MLX-Benchmark))
- **The 60-run oMLX eval matrix** (Qwen3.6-35B-A3B, three checkpoints) is a workload
  showcase rather than a controlled study — it varies checkpoint *and* reasoning mode, and
  it is reported in §3.2.
  ([discussion](https://github.com/jundot/omlx/discussions/1230))

### 1.3 Aggregators, leaderboards, integrity experiments

- **llmcheck.net** — 200+ data points across Ollama, LM Studio and MLX with a per-row
  provenance label. Stated protocol for *measured* rows: 256-token prompt, 512 output
  tokens, Q4_K_M, 3 runs, idle machine; the majority of rows are **derived** from memory
  footprint × bandwidth rather than measured, and the site labels them "estimated."
  ([source](https://llmcheck.net/benchmarks))
- **macfax.com** — 11 measured runs, one model (Qwen3-8B Q4_K_M), llama.cpp via
  `llama-bench` pp512/tg128, 5 repetitions, every row signed by the reporting Mac's Secure
  Enclave; runs on battery, in low power mode, on a hot or busy machine are excluded from
  the table. Not an MLX study — but the strongest integrity mechanism found anywhere.
  ([source](https://macfax.com/bench))
- **mlbenchmark.app** — a leaderboard across MLX, GGUF and MLC backends. **UNVERIFIED:**
  the page is a JS application and returned no readable content on fetch; existence only.
  ([source](https://mlbenchmark.app/))
- **omlx.ai community benchmarks** — the oMLX upload/leaderboard surface. On 2026-09-15 it
  returned "Temporary maintenance… Recent growth exceeded the capacity of our current
  database design." ([source](https://omlx.ai/benchmarks/performance))

### 1.4 Runtimes with no comparative benchmark found

- **Osaurus** — no published comparative benchmark located. The engine is
  `osaurus-ai/vmlx-swift-lm` (a fork of `ml-explore/mlx-swift-lm` adding continuous
  batching, maintained by Osaurus). The JANG project also places its `JangPress` load-time
  memory policy in that fork, which makes Osaurus part of the JANG-affiliated path rather
  than a neutral comparison point.
  ([fork](https://github.com/osaurus-ai/vmlx-swift-lm),
  [JangPress attribution](https://github.com/jjang-ai/jangq)) **UNVERIFIED:** whether any
  Osaurus numbers exist outside its own site.
- **LM Studio's MLX engine** — no first-party published benchmark located. LM Studio appears
  in third-party tables as an engine row (llmcheck), mostly on GGUF.
- **vMLX / MLX Studio's own claims** — the marketing numbers ("224× faster than LM Studio at
  100K tokens", "9.7× faster TTFT") appear on the project's surfaces with no measurement
  methodology published that I could find. These compare different applications, engines,
  cache stacks and plausibly different quantizations at once; per our own rule they are a
  press claim, not a benchmark. **UNVERIFIED.**
  ([site](https://shieldstack.dev/), [repo](https://github.com/jjang-ai/vmlx))

### 1.5 Verdict on Q1

- **Runtime axis:** `mlx-Chronos` already does, with a published protocol, what our Study A
  plans to do — but for a different (overlapping) engine set, and it explicitly scopes
  itself to client-observed latency. Our differentiation on this axis is **the specific
  runtimes** (Osaurus, optiq, vMLX, LM Studio MLX) and the format-held-constant discipline,
  not the idea of a protocol.
- **Format axis:** **nobody has done it properly.** Every published format comparison either
  (a) changes the runtime with the format, or (b) is vendor self-reported, or (c) measures a
  proxy (KLD/perplexity) rather than task accuracy, or (d) covers one or two formats.
  The field's best format-axis work — `deepsweet/mlx-eval` — produces a comparability
  warning rather than a clean ranking, which is a result we should design for.
- **No X/Twitter thread with numbers was retrieved.** Web search did not surface X content
  in this pass; if the vMLX/JANG dispute has a public X thread, it was not found from here.
  **UNVERIFIED.**

---

## 2. Q2 — The extraordinary claim

### 2.1 The exact claim, verbatim, and where it lives

The claim appears on at least five surfaces, and **the supporting metadata does not agree
across them.** All quotes below are verbatim.

**A. vMLX README** — https://github.com/jjang-ai/vmlx

> **JANG 2-bit destroys MLX 4-bit on MiniMax M2.5**:
>
> | Quantization | MMLU (200q) | Size |
> |---|---|---|
> | **JANG_2L (2-bit)** | **74%** | 89 GB |
> | MLX 4-bit | 26.5% | 120 GB |
> | MLX 3-bit | 24.5% | 93 GB |
> | MLX 2-bit | 25% | 68 GB |

**B. `jjang-ai/jangq` README** — https://github.com/jjang-ai/jangq

> ### MiniMax-M2.5 — JANG is the ONLY working option
>
> | Model | MMLU | Size |
> |---|---|---|
> | **JANG_2L** | **74%** | 63 GB |
> | **JANG_3M** | **74.5%** | 82 GB |
> | MLX 4-bit | 26.5% | 120 GB |
> | MLX 3-bit | 24.5% | 93 GB |
> | MLX 2-bit | 25% | — |
>
> MLX is broken on MiniMax at ALL bit levels (~25% = random). MiniMax has 256 experts —
> MLX compresses attention to the same bits as expert MLP, destroying coherence.

**C. jangq.ai homepage** — https://jangq.ai/

> The strongest proof points are MiniMax-M2.5 at 82.5 GB beating MLX 4-bit at 119.8 GB by
> +47.5 MMLU points …

with a per-subject table summing to `JANG_2L 148/200 (74%)` vs `MLX 4-bit 53/200 (26.5%)`,
`MLX 3-bit 49/200 (24.5%)`, `MLX 2-bit 50/200 (25%)`.

**D. shieldstack.dev (author's CV site)** — https://shieldstack.dev/

> The result is dramatic: on MiniMax-M2.5 at 230B parameters, JANG achieves **74% MMLU at an
> average of just 2.10 bits** (82.5 GB) while standard MLX 4-bit quantization gets only
> 26.5% MMLU (119.8 GB). That's **3× the accuracy using 37 GB less memory**.

**E. A JANG-family model card** (the abliterated variant) —
https://huggingface.co/dealignai/MiniMax-M2.5-UNCENSORED-JANG_2L

> MLX uniform quantization is **completely broken** on MiniMax at ALL bit levels (~25% =
> random chance). JANG is the only working quantization format for this model.

That card also reports `JANG_2L (base) 74.5%`, this model `~84.7%`, and attributes the
+10.2-point gain to removing safety guardrails — a second extraordinary claim, from the same
author, with no independent replication found.

**The same artifact is reported at three different on-disk sizes:**

| Surface | JANG_2L size | MLX 4-bit size |
|---|---|---|
| `jjang-ai/jangq` README + HF card | 63 GB | 120 GB |
| jangq.ai homepage + shieldstack.dev | 82.5 GB | 119.8 GB |
| vMLX README | 89 GB | 120 GB |

and at two different average bit-widths: "2.10 bits" (shieldstack, jangq.ai model list) vs
`JANG_2L ≈ 2.9 avg bits` in jangq.ai's own profile table.
Additionally, the Qwen3.5-122B MLX baseline for `mixed_2_6` is reported as **56.5%** in the
`jangq` README and in `jangq.ai/vs/mlx`, but as **46%** on the jangq.ai homepage. The
project's own baseline column is not stable page to page.

### 2.2 What is actually claimed — headline vs body

The headline claim and the supporting analysis are **two different claims**, and the
supporting text is the narrower one. Read precisely:

- The **headline** ("JANG 2-bit *destroys* MLX 4-bit"; "3× the accuracy") asserts a
  *beat-the-baseline quality result*: 2-bit beats 4-bit at higher accuracy.
- The **body** ("MLX is broken on MiniMax at ALL bit levels"; "~25% = random") asserts
  something else: that the MLX uniform-quantization pipeline cannot produce a coherent
  MiniMax-M2.5 at any bit level, so the 4-bit baseline is not a working model to beat.

Both statements appear in the same README, three lines apart. If the body is true, the
headline's comparison is against a baseline the author has already declared non-functional;
the interesting result is then "MLX's converter fails on this model," not "2-bit beats
4-bit." If the headline is the intended claim, the body undercuts it. Neither reading is
selected for us by the source.

There is **no second project** claiming to reproduce the MLX 4-bit 26.5% figure, and no
published construction recipe for that baseline — no bit-width table, no quantizer version,
no note on how a 256-expert FP8-source model was dequantized before MLX re-quantized it —
even though the JANG README itself lists "FP8 dequantization: Handles FP8 source models
(MiniMax, Nemotron) automatically" as a **JANG** feature (https://github.com/jjang-ai/jangq).
**UNVERIFIED:** how the MLX baseline was produced.

### 2.3 Stated methodology

The project's research notes are the only place the method is written down —
`jangq-ai/jangq/research/JANG-RESULTS.md`, dated 2026-03-14/17, i.e. *before* the v2.1.5
changelog entry (2026-03-21) that added bfloat16 auto-detection for large expert models:

- "200 questions: 20 per subject × 10 subjects"
- subjects: abstract_algebra, anatomy, astronomy, college_computer_science, college_physics,
  high_school_biology, high_school_chemistry, high_school_mathematics, logical_fallacies,
  world_religions
- "Chat template with `enable_thinking=False`"
- "Temperature: 0.0 (greedy)"; "Max tokens: 20 per question"
- "MMLU dataset: cais/mmlu (HuggingFace, test split)"
- Hardware: "MacBook Pro M4 Max 128 GB (4B/9B), Mac Studio M4 Ultra 256 GB
  (35B/122B/MiniMax)"

([source](https://github.com/jangq-ai/jangq/blob/main/research/JANG-RESULTS.md))

The MiniMax row in that file reports the same 74% / 26.5% / 24.5% / 25% figures with **no
mode stated**, while other tables in the same document are explicitly labelled "No-Think"
or "Reasoning." The project's later README advertises its benchmark harness as a "Smart
two-pass: no-thinking first, then reasoning retry on wrong answers" run with
`--max-thinking 1024` and "forced answers" (https://github.com/jjang-ai/jangq). Which mode
produced the MiniMax numbers is not stated on any surface I found. **UNVERIFIED.**

In the same repository, benchmark scripts exist (`benchmark_mmlu.py`,
`benchmark_mmlu_minimax.py`) and a results file `mmlu_results_4b9b.txt` is checked in; I did
not find a checked-in MiniMax raw log. Script contents are **UNVERIFIED**.
(https://github.com/jangq-ai/jangq)

### 2.4 Reproduction and dispute record

No public reproduction of the MiniMax pair was found. What exists is a documented
*attempted* reproduction and a set of independent results that contradict the broader
"JANG wins at every size point" generalization. All from the oMLX JANG-integration PR
thread: https://github.com/jundot/omlx/pull/364

1. **Attempted validation, inconclusive-to-negative.** AlexTzk (the third-party quant
   benchmarker from §1.2.2), 2026-03-24: JANG's MiniMax result is "one of the best results
   the JANG architecture seems to bring - according to the website - which is why I wanted
   to validate the result for myself," and in the same post: "But on Minimax 2.5 MLX 3bit vs
   JANG 2L, the story is not as consistent". The MiniMax numbers themselves were posted as
   screenshots and never transcribed; the raw JSON offered in the thread was not published
   for MiniMax. **UNVERIFIED.**
2. **A maintained-engine author's matched-size counter-measurement.** jundot (oMLX
   maintainer), 2026-03-28, published a JANG-vs-oQ comparison at matched sizes on
   Nemotron-Cascade-2-30B-A3B, including the *unquantized* reference:

   | Model | Size | MMLU | Winogrande | HumanEval | MBPP |
   |---|---|---|---|---|---|
   | Original (unquantized) | 58.8 GB | 68.1% | 60.0% | 81.1% | 68.3% |
   | JANG_4M | 17.0 GB | 67.7% | 58.9% | 79.9% | 65.0% |
   | oQ4e | 17.3 GB | 68.0% | 59.4% | 81.7% | 68.0% |
   | JANG_2L | 10.3 GB | 61.3% | 51.9% | 75.0% | 60.3% |
   | oQ2e | 10.4 GB | 59.8% | 52.8% | 75.0% | 59.3% |

   His stated conclusion: the two independent quant formats are within noise of each other
   at matched size, and "the benchmark numbers you posted seem to differ quite a bit from
   what i actually measured… i'm not sure if the additional dependency (jang-tools) and
   custom metal kernel justify a dedicated engine integration, when the quality delta over
   standard quants is marginal at best."
3. **A distribution-fidelity evaluator found the artifact not comparable at all.**
   deepsweet, 2026-05-15, on Qwen3.6-27B-JANG_4M: "it has nothing to do with the original
   Qwen3.6-27B log probabilities… it's *another separate entity* on its own, but not the
   Qwen3.6-27B anymore. Therefore, it's not directly comparable with anything else the way I
   do it." (§1.2.1)
4. **The integration claim itself is not supported by its own citation.** The `jjang-ai/jangq`
   README states "oMLX has added JANG integration (PR #364)". The linked PR was open, not
   merged, when fetched, with force-pushes through 2026-08-04; a closed issue
   `jundot/omlx#1889` is titled "JANG support removed in v0.4.x without notice."
5. **Within the JANG ecosystem, model loading is not universal.** In the same PR thread,
   users report Gemma-4 JANG variants failing to load with shape mismatches while other
   variants load, and one contributor concludes "It seems not all JANG model could be loaded
   with jang tools this way." This is orthogonal to the accuracy claim but relevant to
   whether "JANG works" is a single property.

### 2.5 The chance-level failure mode has a documented precedent

The reason the 26.5% figure is a red flag is not only that it is near the 25% line for
4-choice MMLU. It is that **an MLX-harness vendor has already documented this exact failure
mode in public, with almost the same numbers.** From optiq's eval-framework write-up:

> We measured one strong math model at 27% MMLU (≈ chance) and 36% GSM8K on the stock
> harness. Both low scores came from the scoring format, not the model… On that same model
> the real numbers were 74% MMLU and 90% GSM8K.

The documented mechanisms: a generation budget too small to finish a long `think` trace, and
MMLU scored by first-letter logit argmax, which "collapses to chance for a model trained to
reason before answering."
(https://mlx-optiq.com/blog/eval-framework)

Two things follow, and neither should be overstated:

- The failure mode is real: a serious tool-builder measured a strong model at chance on MMLU
  and traced it to the harness, not the weights. A ~25% MMLU reading is therefore not a
  measurement of the model until the harness is shown.
- The failure mode is **not proof** about MiniMax. The optiq precedent is a *different
  model*, and I found no artifact showing how the MLX 4-bit MiniMax baseline was scored. What
  can be said: the JANG materials do not document the MiniMax baseline's harness beyond
  "MLX 4-bit," while the JANG side of the comparison ran a two-pass forced-answer harness
  with thinking disabled. A chance-level baseline and an ordinary harness are exactly the
  confound that produced optiq's 27%→74% swing.

One more independent data point cuts the other way and is worth recording: in the
third-party benchmark from §1.2.2, the Qwen3.5-35B-A3B model scored 22–25% MMLU at **every**
quantization including bf16, on a harness with full MMLU-1000 and no thinking-mode games.
Near-chance MMLU on multiple-choice is not automatically a harness bug; some models are
genuinely weak on it in a given configuration. Both readings remain open.
(https://medium.com/@alexandru_vasile/i-benchmarked-every-quantization-method-for-apple-silicon-llms-heres-what-actually-wins-7b3e7edff4ef)

### 2.6 Q2 — what this establishes and what it does not

**Establishes:**

- The claim exists, verbatim, as quoted above, across five surfaces.
- The claim's own supporting text asserts the baseline is broken, which is not the same
  claim as "2-bit beats 4-bit."
- The supporting metadata is internally inconsistent on size (63 / 82.5 / 89 GB), on average
  bits (2.10 vs ~2.9), and on baseline accuracy for a different model (46% vs 56.5%).
- No public reproduction of the MiniMax figures exists; an attempted third-party validation
  reported the story "not as consistent," an independent maintainer's matched-size
  measurements show a marginal delta on another model, and a KL evaluator found one dense
  JANG quant is not comparable to its base at all.
- The MLX baseline's construction and scoring harness are undocumented in any source I
  found.

**Does not establish:**

- That the 74% or the 26.5% numbers are *wrong*. No one has published a reproduction that
  fails, and no raw MiniMax log was found either way. **UNVERIFIED.**
- That MLX uniform quantization cannot run MiniMax-M2.5. The author says it cannot; I found
  no independent confirmation and no disconfirmation.
- Whether the failure, if real, is MiniMax-specific, FP8-source-specific, 256-expert-MoE-
  specific, or a bug in one converter version.

**How to state it publicly (neither softened nor inflated):** the project claims 74% vs
26.5% on a 200-question MMLU subset; its own explanation is that the MLX side is broken
rather than merely worse; the numbers have not been independently reproduced, the size and
bit-width metadata contradict each other across the project's own pages, and the comparison
changes both the quantization format and the runtime while using an undocumented baseline.

---

## 3. Q3 — How the authors benchmark themselves, and where a harness can legitimately disagree

### 3.1 oMLX

**Two separate tools ship with it.**

**(a) Throughput & latency benchmark** (admin dashboard; `omlx/admin/benchmark.py`). The
documented execution order is: unload every loaded model from the engine pool → load the
target → warmup (length varies by warmup mode) → single-request tests across prompt lengths
from 1,024 up to 200,000 tokens → optional batch tests at 2/4/8 concurrent requests in two
modes ("same prompt" exercises prefix caching; "different prompt" measures raw throughput).
Metrics and formulas: TTFT `(first_token_time - start_time) * 1000` ms; TPOT
`(gen_duration / max(completion_tokens - 1, 1)) * 1000` ms; Gen TPS
`completion_tokens / gen_duration`; peak memory via `mlx.core.get_peak_memory()`. Cache
isolation is enforced by prepending a unique UUID to every generated prompt so SSD cache
hits cannot silently remove prefill work.
([DeepWiki](https://deepwiki.com/jundot/omlx/8.4-benchmark-tool))

**(b) Accuracy harness** (`omlx/admin/accuracy_benchmark.py` + `omlx/eval/`). A
`BaseBenchmark` lifecycle (load → format prompt → extract answer → score) with a queueing
orchestrator and SSE progress. Benchmarks include MMLU, MMLU-Pro, ARC-C, HellaSwag,
TruthfulQA, Winogrande, CMMLU/JMMLU/KMMLU, GSM8K, MathQA, HumanEval, MBPP, LiveCodeBench,
BBQ, SafetyBench. Users choose a `quick_size` sample or the full set; thinking mode raises
`max_tokens` to 8,192–32,768 and strips `<think>` tags; HumanEval/MBPP/LiveCodeBench execute
generated code in a sandbox (subprocess + `resource` rlimits). Results persist per
`{model, benchmark, mode}` with per-question timing and raw responses.
([DeepWiki](https://deepwiki.com/jundot/omlx/13-intelligence-benchmarking-and-evaluation))

**(c) Community upload.** A summary POST (chip, GPU cores, RAM, model settings, scores)
plus a gzipped per-question blob; the uploader "trims long responses and strips prompt text
to protect dataset integrity and stay under the 5MB compressed cap."
([DeepWiki](https://deepwiki.com/jundot/omlx/8.4-benchmark-tool))

### 3.2 The 60-run eval matrix (what their own heavy user does with it)

Regis-RCR, oMLX discussion #1230: a Mac Studio M3 Ultra (96 GB, macOS 26.4.1), oMLX 0.3.8,
one base model (Qwen3.6-35B-A3B MoE), three checkpoints (an oQ8 baseline plus two
reasoning-distilled oQ8e variants), ten benchmarks × two reasoning modes = 60 jobs;
22,686 questions; 38.6 hours wall clock; ~13.4 M output tokens (estimated as
`raw_response` characters ÷ 4); "96 tokens per second average overall throughput, prefill
included."

- The AI-dataset axis is not a quantization study: it compares *checkpoints* (different
  training/distillation) as much as formats, and the two reasoning modes are a third
  variable. The author is explicit that this is a "real-workload showcase."
- **The two roadmap asks are direct evidence of what the built-in harness cannot do:**
  (1) "There is no way to quantify the contribution of any one feature by re-running the
  same bench with that feature disabled" — no per-feature ablation flags for `paged_cache`,
  `paged_ssd_cache`, `prefix_cache`, `hybrid_cache`, etc.; (2) live inference stats are not
  surfaced during accuracy runs, so a 2-hour pass looks idle and a thermal-throttle event
  would be invisible.
- Useful practice worth copying: one JSON per `{model, benchmark, mode}` containing
  `questions[]` with `raw_response`, `time_s` and `category`, which is what makes
  recomputable summaries possible.
  ([discussion](https://github.com/jundot/omlx/discussions/1230))

### 3.3 optiq

Three commands, and they measure three different kinds of thing:

**`optiq eval`** — two stages. *Smoketest*: KL divergence on 64 prompts × 256 tokens
(reference = highest-fidelity model that fits in RAM, auto-resolved: bf16 if it fits under
70% of available RAM, else the community uniform-4-bit publish), plus GSM8K on 50 samples.
*Full suite*: MMLU 5-shot 1,000 samples (first-letter logit argmax, "the standard
cheap-and-stable method"); GSM8K 1,000 (3-shot CoT, `enable_thinking=False`); full IFEval
(strict); BFCL-V3 simple (200); HumanEval (164, sandboxed, pass@1); HashHop long-context
retrieval (25 instances × hops 1–4 at ~12k context). `--score` computes the Capability
Score = unweighted mean of those six; KL is deliberately **excluded** from the score. In
`--reasoning` mode, MMLU is scored generatively instead of by logit argmax and the
documented reason is that logit scoring "collapses to chance" for always-thinking models.
`--served URL` scores through a running `optiq serve` instead of loading weights in-process.
([CLI reference](https://mlx-optiq.com/docs/cli), [write-up](https://mlx-optiq.com/blog/eval-framework))

**`optiq benchmark`** — "Quick-and-dirty perplexity + throughput on a converted model, with
optional baseline side-by-side"; 50 perplexity samples by default; the docs say to prefer
`optiq eval` for headline accuracy numbers.
([CLI reference](https://mlx-optiq.com/docs/cli))

**`optiq latency`** — a **predictor, not a measurement**: "Predicts decode tok/s … using the
Apple Silicon roofline model: `latency ≈ model_bytes / memory_bandwidth + per_layer_overhead`."
The bare form "only counts weight-loading time and is optimistic"; `--calibrate` runs
8 warmup + 15 measured generations to fit the framework-overhead constant, and the docs
disclose that "on M3 Max ~83% of decode latency is overhead (attention, norms, KV cache,
framework)."
([CLI reference](https://mlx-optiq.com/docs/cli))

### 3.4 Where an independent harness would legitimately disagree

| Their choice | Where a client-side harness legitimately disagrees |
|---|---|
| **oMLX throughput bench** measures server-side around the generate call | A client harness measures request-to-first-byte; HTTP, serialization and scheduler queueing are inside oMLX's TTFT by construction and outside yours. The mlx-Chronos methodology states its numbers are client-observed and therefore not "pure model latency" — the two are different metrics wearing the same name. |
| oMLX peak memory = `mx.get_peak_memory()` (Metal allocator) | Not comparable to `phys_footprint` or to a competitor's RSS. mlx-Chronos makes exactly this point when it demotes engine RSS to "diagnostic only" because it "may not include model weights or Metal allocations mapped outside ordinary process RSS." Any memory ranking built on one of these three definitions will not transfer to the others. |
| Cache discipline: UUID-prefixed prompts to defeat SSD cache | Sound in intent, but it tests *cold prefill*, not cold *system state*; the SSD tier persists across restarts and must be cleared outside the tool (`rm -rf ~/.omlx/cache`) or a "cold" run is a lie — documented by a third party in §1.1.4. |
| One measurement per prompt length (loop over `prompt_lengths`) | No per-cell variance is reported from the built-in tool, so a reader cannot distinguish "faster" from "faster this time." ywchiu's lab showed single-shot long-context numbers are exactly where run-to-run spread becomes comparable to the effect. |
| "Same prompt" batch mode mixes prefix-cache effects into concurrency | Aggregate throughput under "same prompt" is not aggregate throughput under unique prompts. Both modes exist, which is good — but a reader must know which one a number came from, and the dashboard number alone does not say. |
| Accuracy harness: sample tiers (`quick_size` vs full), thinking-mode token caps, `<think>` stripping | Sampled MMLU/GSM8K is not the full benchmark; the thinking-mode cap (8k–32k) can truncate a reasoning model mid-trace; and stripping think tags before answer extraction is a scoring policy that changes the number. Each is defensible; none is neutral. |
| Upload strips prompt text and trims long responses; results live on omlx.ai | The published artifact is not independently re-scorable, and the leaderboard was offline on 2026-09-15 ("Temporary maintenance"). Reproducibility then depends on a hosted service. |
| **optiq `latency`** is a roofline *model*; `benchmark` is perplexity + throughput | Neither is an end-to-end serving measurement. A calibrated prediction fitted on 15 generations is not a substitute for measuring TTFT/ITL under a fixed protocol, and the docs say so ("optimistic"). |
| optiq's default scoring loads weights in-process; `--served` changes the code path | optiq states the two paths "agree on published quants, but they are not the same code: only the served one goes through the batch generator, the KV cache and the server's family-specific tool-call parser." An independent harness that scores only over HTTP is measuring the path a user actually has. |
| MMLU by first-letter logit argmax (default) | A different metric from generative MMLU — optiq's own numbers for one model move from 27% (logit) to 74% (generative, reasoning mode). Both are published; a table that silently mixes them is meaningless. |
| Capability Score = unweighted mean of six tasks, no confidence intervals | The mean hides per-task swings of tens of points (HumanEval 79.9 vs oQ4 39.0 in the third-party run, §1.2.2). A composite is a presentation choice; a per-task table is the evidence. |

---

## 4. Q4 — An established methodology to align with

### 4.1 arXiv 2511.05502 — "Production-Grade Local LLM Inference on Apple Silicon"

(https://arxiv.org/abs/2511.05502, full text read from https://arxiv.org/pdf/2511.05502v1)

- **Scope:** five runtimes — MLX, MLC-LLM, llama.cpp, Ollama, PyTorch MPS — on Mac Studio
  M2 Ultra, 24 CPU cores, 76 GPU cores, 192 GB.
- **Versions pinned and reported:** MLX v0.26, MLC-LLM commit `3d42929`, llama.cpp commit
  `b5963`, Ollama v0.10.1, PyTorch 2.7.1 (MPS).
- **Models:** Qwen2.5-Coder-3B primary, Qwen2.5-7B-Instruct for scaling.
- **Quantization:** fp16/bf16 baselines; int8/int4; MLX mixed 3/4/6/8-bit; MLC AWQ/GPTQ;
  llama.cpp GGUF 4/5/8/16; Ollama registry. Each runtime runs its **native** format.
- **Metrics, defined in the paper:** TTFT = client-observed request-acceptance → first token
  (tokenization excluded, warm-path init included); throughput reported **both** as
  decode-only (post-first-token) and end-to-end (prefill + decode); latency as **p50/p90/p99**
  of per-request end-to-end latency and inter-token latency distributions; cold start =
  model load + init, reported separately from warm runs; memory = peak RSS via `vm_stat`
  plus framework-reported device allocations (Metal metrics).
- **Procedure:** one warmup prompt discarded; **N = 10 trials** per
  (framework × model × quant × prompt type × length); fixed random seeds, tokenizer versions
  and sampling parameters; prompt classes = unique-token, prefix-heavy, code-dominant; input
  lengths 1k → 100k; Spotlight/Time Machine/iCloud disabled; no concurrent GPU work.
- **Reported results:** MLX ~230 tok/s sustained with 5–7 ms median and ~12 ms p99
  per-token latency; MLC-LLM ~190 tok/s with lower TTFT ≤16k and paged KV sustaining 100k
  contexts; llama.cpp ~150 tok/s short-context only, collapsing to ~1.2 tok/s at 32k;
  Ollama 20–40 tok/s with >50 s TTFT at 100k; PyTorch MPS 7–9 tok/s and frequent OOM.
  Cold start: MLC ~11 s, MLX ~31 s, llama.cpp <0.5 s cached, Ollama ~0.6 s.
- **Its own limits section ("Threats to Validity")** is the most useful part for us: single
  hardware class, Qwen-2.5 family only, residual OS jitter, divergent metric definitions
  across papers, cache telemetry unstandardised, synthetic concurrency, and an explicit
  statement that its A100 comparisons are contextual rather than head-to-head.

**Two specifics that determine whether we can call our numbers "comparable":**

1. It pins *versions and commit hashes* and interleaves trials as a thermal mitigation —
   both of which our runtimes pin in a different way (apps, not commits).
2. Each runtime runs its own quantization family. So the paper **varies runtime and format
   together** at the headline level; its quantization ablations are within-framework. It is
   not a counter-example to our format axis, and it is the nearest published thing to our
   runtime axis.

**UNVERIFIED:** the paper says "We release scripts, logs, and plots to reproduce all
results"; I did not locate the artifact repository URL in the fetched text.

### 4.2 Apple ML Research — "Exploring LLMs with MLX and the Neural Accelerators in the M5 GPU"

(https://machinelearning.apple.com/research/exploring-llms-mlx-m5, published 2025-11-19)

- **Reports exactly two performance numbers per model:** TTFT in seconds and generation
  speed in tokens/s, measured with `mlx_lm.generate`.
- **Fixed workload:** prompt size 4096; generation speed measured over 128 additional
  tokens. Models: Qwen 1.7B/8B bf16, Qwen 8B/14B 4-bit, Qwen 30B-A3B 4-bit, GPT-OSS 20B
  MXFP4; MacBook Pro M5 24 GB vs M4. Memory footprint per configuration is tabulated
  (e.g. Qwen3-30B-A3B-4bit 17.31 GB).
- **Framing:** TTFT is compute-bound and benefits from Neural Accelerators; subsequent-token
  generation is memory-bandwidth-bound (M4 120 GB/s vs M5 153 GB/s). It is a
  *hardware-generation* comparison, not a runtime comparison, and it is vendor-authored.
- **Why it is still the right thing to align with:** it makes the two-phase split
  explicit — prefill-bound TTFT, bandwidth-bound decode — with a fixed prompt length and a
  fixed generation length, which is the same discipline our pinned-output-length rule
  encodes.

### 4.3 Academic MLX benchmarking adjacent to the above

arXiv 2510.18921, "Benchmarking On-Device Machine Learning on Apple Silicon with MLX"
(https://arxiv.org/abs/2510.18921) — worth reading for what it is *not*: it benchmarks
**MLX framework operations** (reusing `TristanBilot/mlx-benchmark`, 5 iterations per op) and
**encoder-model inference latency** (BERT/RoBERTa/XLM-RoBERTa; 10 iterations; inputs 50–500
characters; batch sizes 1/16/32) on an 8 GB M1 and a 32 GB M2 Max against an NVIDIA A10.
It reports milliseconds per operation and per model, mlx-gpu vs mlx-cpu vs cuda vs cpu
speedups, and finds sublinear batch scaling. It is not an LLM-serving study and contains no
quantization comparison — so it can be cited for per-op methodology, not for anything about
runtimes or formats.

### 4.4 Metrics that recur, and where they diverge

| Metric | arXiv 2511.05502 | Apple M5 post | mlx-Chronos | oMLX built-in | optiq |
|---|---|---|---|---|---|
| TTFT boundary | client-side, includes warm-path init | `mlx_lm.generate`, prompt 4096 | client-side stream | server-side `first_token_time` | not measured (perplexity/throughput) |
| Throughput | decode-only **and** end-to-end | gen tok/s over 128 tokens | request **and** decode, tokens from `usage.completion_tokens` | Gen TPS = completion_tokens/gen_duration | not measured end-to-end |
| Variance | N=10 trials, mean ± std, p50/p90/p99 | not reported | mean/stddev/min/max; p95 ≥20 trials | not per cell | none on the Capability Score |
| Cold start | separate metric | not reported | separate phase, warmup recorded | warmup folded into a phase, not published | cold load not a metric |
| Memory | peak RSS (`vm_stat`) + Metal device allocations | per-config GB table | System RAM peak (public) + RSS (diagnostic) | `mx.get_peak_memory()` | RAM not reported |
| Version pinning | commits, framework and OS versions | macOS beta requirement noted | engine version required for public rows | engine build not in the metric | package version |

**The uncomfortable finding in this table: "memory" currently means four different things
in four credible sources.** A cross-paper memory ranking cannot be assembled today without
choosing one definition and saying so.

### 4.5 What alignment buys us

- The arXiv paper supplies citable definitions for TTFT (client-observed, prefill included),
  the decode-vs-end-to-end throughput split, percentile latencies, and cold start as its own
  metric. Adopting those names means our numbers are comparable to the only peer-style study
  in the field, at least in definition.
- Apple's post supplies the prefill/decode framing and a fixed-prompt/fixed-generation
  discipline.
- Neither supplies a format-held-constant comparison, and neither covers the runtimes this
  project names. The runtime axis is partly claimed (mlx-Chronos); the format axis is not.
- No prior study found tests the specific thing our README asserts nobody has tested:
  *one variable at a time across both axes, on the runtime set that exists today, with the
  raw observations retained.*

---

## 5. UNVERIFIED register

Everything below is asserted by a source but was not independently confirmed in this pass.

1. The MiniMax-M2.5 MMLU pair (JANG_2L 74% vs MLX 4-bit 26.5%) — no public reproduction or
   failure found; no raw MiniMax log located.
2. The 63 / 82.5 / 89 GB size of the same JANG_2L artifact, and 2.10 vs ~2.9 average bits.
3. Whether the JANG_2L + CRACK model's +10.2-point MMLU gain over its base is attributable
   to abliteration rather than measurement.
4. How the MLX 4-bit MiniMax baseline was constructed or scored; whether the 25%-level reads
   are a harness artifact (the optiq precedent makes this a live hypothesis, not a finding).
5. Which mode (no-think vs reasoning two-pass) produced the MiniMax numbers.
6. vMLX's "224× faster than LM Studio" / "9.7× faster TTFT" claims — no methodology found.
7. `mlbenchmark.app` contents (JS-only page).
8. The artifact repository for arXiv 2511.05502.
9. Any Osaurus comparative benchmark, and any first-party LM Studio MLX engine benchmark.
10. The current merged/released state of JANG support in oMLX (the README's "has added JANG
    integration" cites a PR that was open when fetched; issue #1889 records it being removed
    in v0.4.x).
11. X/Twitter threads with numbers — none retrieved in this pass.

---

## 6. Source index

**Runtime comparisons**
- mlx-Chronos discussion — https://github.com/jundot/omlx/discussions/1391
- mlx-Chronos methodology — https://github.com/igurss/mlx-chronos/blob/main/docs/methodology.md
- mlx-Chronos repo — https://github.com/igurss/mlx-chronos
- mlx-Chronos published run (M1 Max) — https://bright-lotus-8q5y.here.now/
- ywchiu/mlx_benchmark_lab — https://github.com/ywchiu/mlx_benchmark_lab
- LargitData write-up — https://www.largitdata.com/en/blog/mlx-inference-benchmark-apple-m5-max/
- Five backends compared — https://jaesolshin.com/posts/apple-silicon-llm-backends/
- mlx-lm vs oMLX (Mac O'Clock) — https://medium.com/macoclock/mlx-lm-vs-omlx-i-was-wrong-about-the-winner-8f36be328069

**Format comparisons**
- deepsweet/mlx-eval results — https://github.com/deepsweet/mlx-eval/blob/main/results/README.md
- oMLX JANG integration PR #364 (dispute record) — https://github.com/jundot/omlx/pull/364
- AlexTzk benchmark repo — https://github.com/AlexTzk/MLX-benchmarks
- Medium write-up — https://medium.com/@alexandru_vasile/i-benchmarked-every-quantization-method-for-apple-silicon-llms-heres-what-actually-wins-7b3e7edff4ef
- oQ quantization doc — https://github.com/jundot/omlx/blob/main/docs/oQ_Quantization.md
- optiq eval framework — https://mlx-optiq.com/blog/eval-framework
- optiq CLI reference — https://mlx-optiq.com/docs/cli
- n8programs, MLX quantization — https://n8programs.substack.com/p/an-examination-of-mlx-quantization
- leriomaggio/mlx-quant-bench — https://github.com/leriomaggio/mlx-quant-bench
- Incept5/MacOS-MLX-Benchmark — https://github.com/Incept5/MacOS-MLX-Benchmark

**The JANG claim and its ecosystem**
- vMLX README — https://github.com/jjang-ai/vmlx
- jjang-ai/jangq README — https://github.com/jjang-ai/jangq
- jangq.ai homepage — https://jangq.ai/
- jangq.ai vs MLX page — https://jangq.ai/vs/mlx/
- shieldstack.dev — https://shieldstack.dev/
- JANG results research note — https://github.com/jangq-ai/jangq/blob/main/research/JANG-RESULTS.md
- Abliterated model card — https://huggingface.co/dealignai/MiniMax-M2.5-UNCENSORED-JANG_2L
- Osaurus Swift engine fork — https://github.com/osaurus-ai/vmlx-swift-lm

**oMLX internals**
- Throughput benchmark tool — https://deepwiki.com/jundot/omlx/8.4-benchmark-tool
- Accuracy/eval framework — https://deepwiki.com/jundot/omlx/13-intelligence-benchmarking-and-evaluation
- 60-run eval matrix — https://github.com/jundot/omlx/discussions/1230
- Community leaderboard (offline 2026-09-15) — https://omlx.ai/benchmarks/performance

**Methodology anchors**
- arXiv 2511.05502 — https://arxiv.org/abs/2511.05502 · https://arxiv.org/pdf/2511.05502v1
- Apple ML Research, M5 + MLX — https://machinelearning.apple.com/research/exploring-llms-mlx-m5
- arXiv 2510.18921 — https://arxiv.org/abs/2510.18921

**Datasets / integrity**
- llmcheck — https://llmcheck.net/benchmarks
- macfax — https://macfax.com/bench
- mlbenchmark.app — https://mlbenchmark.app/


# Small-model candidates for the format axis: dense and MoE proof-of-concept models

**Date:** 2026-09-15
**Role:** research pass (documentation only — no code changed, nothing downloaded, no server started)

The format axis holds the serving runtime constant at oMLX and varies the quantization format
across four cells: **stock mlx 4-bit**, **oQ4**, **oQ4e**, and **OptiQ-4bit**. This note asks
whether a *small* model exists for which all four artifacts are published, so that the entire
matrix can sit on disk at once. It answers four questions against primary sources, and it treats
the MoE question (Q2) as the load-bearing one.

**Evidence rules.** Every claim carries the source URL, the HF API query, or the local path that
was checked. Sizes are the sum of file byte-sizes reported by
`https://huggingface.co/api/models/<repo>?blobs=true`, expressed in decimal GB (bytes ÷ 10⁹);
`du` on disk will differ by block size and by the `blobs/` symlink layout. Anything not directly
verified is marked **UNVERIFIED** and is not inferred. Repository existence, `model_type`, layer
count, expert count, and file sizes were all read from the API on 2026-09-15.

**Budget.** The task states 36 GiB free. `df -h /Users/jrazz` on this machine reports
`35Gi` avail on `/dev/disk3s5` (869 Gi used of 926 Gi). Both figures are used below; 36 GiB is
treated as the ceiling and the ~35 GiB df reading is treated as the practical one.

**Format semantics, pinned from the local tree.** `oQ4e` is not a separate bit width — it is oQ4
with imatrix-weighted quantization. From
`/Applications/oMLX.app/Contents/Resources/omlx/oq.py`:
`OQ_LEVELS = {2, 2.5, 2.7, 3, 3.5, 4, 5, 6, 8}` (line 44), the repo suffix is built as
`suffix = f"-oQ{level_str}{'e' if enhanced else ''}"` (line 1340), and the docstring for the
`enhanced` parameter reads "Enable oQe imatrix-weighted quantization" (line 5730). So oQ4 vs oQ4e
is a *calibration* difference at the same nominal level, which is exactly the kind of distinction
the format axis exists to measure.

---

## Q1 — Small dense candidates (3–5 B)

### How candidates were found

Org inventories were enumerated whole:
`?author=Jundot&limit=1000` (50 repos), `?author=JANGQ-AI&limit=1000` (80 repos),
`?author=mlx-community&search=<family>` (per-family paging), plus whole-HF searches
`?search=oQ4e` and `?search=oQ4` to catch third-party oQ publishers, and
`?author=mlx-community&search=OptiQ-4bit` (77 repos).

The four formats do **not** have a single publisher each. In practice:

| Format | Typical publisher |
|---|---|
| stock mlx 4-bit | `mlx-community` (and the base org, e.g. `LiquidAI`) |
| OptiQ-4bit | `mlx-community` only — 77 repos total, all under `mlx-community` |
| oQ4 / oQ4e | third parties: `Jundot`, `gcoli`, `stamsam`, `brainworkup`, `RepublicOfKorokke`, `uingei`, `beaupi`, `Regis-RCR`, `TheWirelessPhoenix`, … |
| JANG / JANGTQ | `JANGQ-AI` (80 repos) and `OsaurusAI` |

### Ranked by how many of the four formats exist

| Rank | Base model | Params | Formats found | Verdict |
|---|---|---|---|---|
| 1 | **Qwen3.5-4B** | ~4 B dense | **4 / 4** + JANG | fully usable |
| 2 | **gemma-4-E4B-it** | ~4 B effective | **4 / 4** + JANG | fully usable |
| 3 | **gemma-4-E2B-it** | ~2 B effective | 4 / 4 (oQ4 UNVERIFIED) + JANG | usable, but below the 3–5 B ask |
| 4 | **LFM2.5-2.6B** | 2.6 B dense | 4 / 4 | usable, but below the 3–5 B ask |
| 5 | **MiniCPM5-2B** | ~2 B dense | 3 / 4 (stock 4-bit UNVERIFIED) | below range |
| 6 | **Fara1.5-4B** | 4 B dense | 2 / 4 (stock + OptiQ) | too few |
| 7 | **Nanbeige4.2-3B** | 3 B dense | 2 / 4 (stock + OptiQ) | **disqualified on architecture** |
| 8 | **Spark-X2.5-4B** | 4 B dense | 2 / 4 (OptiQ + JANG) | **disqualified on architecture** |
| 9 | **NVIDIA-Nemotron-3-Nano-4B** | 4 B dense hybrid | 2 / 4 (OptiQ + oQ4) | too few |
| 10 | **SmolLM3-3B** | 3 B dense | 2 / 4 (stock + oQ4) | too few |
| 11 | **Phi-4-mini-instruct** | 3.8 B dense | 2 / 4 (stock + oQ4e) | too few |
| 12 | **Ministral-3-3B** | 3 B dense | 2 / 4 (stock + oQ4) | too few |
| 13 | **DeepSeek-R1-Distill-Qwen-7B** | 7 B dense | 2 / 4 (stock + oQ4e) | out of range, too few |
| 14 | **Llama-3.2-3B-Instruct** | 3 B dense | **1 / 4** (stock only) | useless to us |
| 15 | **VibeThinker-3B** | 3 B dense | **1 / 4** (OptiQ only) | useless to us |
| 16 | **mini-coder-4b** | 4 B dense | **1 / 4** (OptiQ only) | useless to us |
| 17 | **DeepSeek-R1-Distill-Qwen-1.5B** | 1.5 B dense | **1 / 4** (stock only) | useless to us |

A candidate with only one format is useless to us; ranks 14–17 are listed precisely so that they
can be struck from the shortlist. Note that three of the seven "candidate families" named in the
task (Llama 3.2 3B, SmolLM3, Phi-4-mini) are **single- or dual-format models with no OptiQ and no
JANG artifact** — the OptiQ line starts at much newer model families.

### Rank 1 — Qwen3.5-4B (dense, 4/4)

32 layers, hidden 2560, 16 attention heads, vocab 248 320. Base config:
`https://huggingface.co/Qwen/Qwen3.5-4B/raw/main/config.json`.

| Format | Repo id | Size (GB) |
|---|---|---|
| stock mlx 4-bit | `mlx-community/Qwen3.5-4B-4bit` | 3.06 |
| oQ4 | `RepublicOfKorokke/Qwen3.5-4B-oQ4` | 3.16 |
| oQ4e | `uingei/Qwen3.5-4B-oQ4e` | 3.17 |
| OptiQ-4bit | `mlx-community/Qwen3.5-4B-OptiQ-4bit` | 4.04 |
| *(JANG_4S, bonus)* | `JANGQ-AI/Qwen3.5-4B-JANG_4S` | 3.21 |

**Four-format total: 13.43 GB (12.51 GiB).** With JANG: 16.64 GB (15.50 GiB).

Other oQ4e artifacts exist and are interchangeable as cells:
`craquehouse/Qwen3.5-4B-oQ4e-fp16-text-only` (2.53 GB, text-only),
`scottlowry/Qwen3.5-4B-oQ4e-mtp` (3.29 GB, ships `oq_imatrix_report.json`),
`TheWirelessPhoenix/Qwen3.5-4B-oQ4e-fp16-mtp` (2.62 GB).
Other oQ4: `RepublicOfKorokke/Qwen3.5-4B-oQ4-fp16` (3.17 GB), `AtBeginDocument/Qwen3.5-4B-oQ4`.

### Rank 2 — gemma-4-E4B-it (dense, 4/4)

42 layers, hidden 2560, 8 attention heads, vocab 262 144. Base config:
`https://huggingface.co/google/gemma-4-E4B-it/raw/main/config.json`.
"E4B" is an *effective*-parameter figure; the checkpoint carries the full Gemma 4 multimodal
config (`architectures: ["Gemma4ForConditionalGeneration"]`), and the MLX artifacts are text-only,
with vision weights stripped.

| Format | Repo id | Size (GB) |
|---|---|---|
| stock mlx 4-bit | `mlx-community/gemma-4-e4b-it-4bit` | 5.18 |
| oQ4 | `beaupi/gemma-4-E4B-it-oQ4` | 4.79 |
| oQ4e | `Jundot/gemma-4-E4B-it-oQ4e-mtp` | 5.54 |
| OptiQ-4bit | `mlx-community/gemma-4-e4b-it-OptiQ-4bit` | 7.52 |
| *(JANG_4M, bonus)* | `JANGQ-AI/gemma-4-E4B-it-qat-JANG_4M` | 10.82 |

**Four-format total: 23.03 GB (21.45 GiB).** With JANG: 33.85 GB (31.53 GiB).

Interchangeable oQ4 artifacts: `Regis-RCR/gemma-4-E4B-it-oQ4` (4.79 GB), `tevino/gemma-4-E4B-it-oQ4`,
`Xartorx/gemma-4-E4B-it-oQ4`, `mlx-community/unsloth-gemma-4-E4B-it-qat-oQ4` (5.38 GB, qat base).
Also existing: a non-qat stock `mlx-community/gemma-4-e4b-4bit` (5.25 GB).

**Caveat that matters for the axis:** the JANG artifact
(`JANGQ-AI/gemma-4-E4B-it-qat-JANG_4M`, 10.82 GB) and the `unsloth-…-qat-oQ4` artifact are built
on the **qat** base while the others are not. Mixing them would vary the base model as well as the
format, which the project's one-axis rule forbids. The JANG cell is therefore *not* free here — it
would require finding a non-qat JANG artifact. UNVERIFIED that one exists.

### Rank 3 — gemma-4-E2B-it (dense, 4/4, below range)

35 layers, hidden 1536. `https://huggingface.co/google/gemma-4-E2B-it/raw/main/config.json`.

| Format | Repo id | Size (GB) |
|---|---|---|
| stock mlx 4-bit | `mlx-community/gemma-4-e2b-4bit` | 3.61 |
| oQ4e | `Jundot/gemma-4-E2B-it-oQ4e-mtp` | 3.87 |
| OptiQ-4bit | `mlx-community/gemma-4-e2b-it-OptiQ-4bit` | 5.26 |
| *(JANG_4M, bonus)* | `JANGQ-AI/gemma-4-E2B-it-qat-JANG_4M` | 7.84 |
| oQ4 | **UNVERIFIED** — not found in `?search=gemma-4-E2B-oQ` results | — |

At ~2 B it is below the requested 3–5 B band, but it is the cheapest full-four-format set found
(three verified + JANG = 20.58 GB; with oQ4 UNVERIFIED the 4/4 claim rests on a search miss, not
a confirmed artifact).

### Ranks 4–5 — the 2.x B dense pair (context, below range)

**LFM2.5-2.6B** — 30 layers, hidden 2048, `model_type: lfm2`.

| Format | Repo id | Size (GB) |
|---|---|---|
| stock mlx 4-bit | `mlx-community/LFM2.5-2.6B-4bit` | 1.54 |
| oQ4 | `gcoli/LFM2.5-2.6B-MLX-oQ4-fp16` | 1.60 |
| oQ4e | `gcoli/LFM2.5-2.6B-MLX-oQ4e-fp16` | 1.60 |
| OptiQ-4bit | `mlx-community/LFM2.5-2.6B-OptiQ-4bit` | 2.01 |

Four-format total: **6.75 GB (6.29 GiB)**. No JANG artifact found for this base.

**MiniCPM5-2B** — 42 layers, hidden 2048, `model_type: llama`.

| Format | Repo id | Size (GB) |
|---|---|---|
| oQ4 | `RepublicOfKorokke/MiniCPM5-2B-oQ4-fp16` | 1.49 |
| oQ4e | `gcoli/MiniCPM5-2B-oQ4e-fp16` | 1.49 |
| OptiQ-4bit | `mlx-community/MiniCPM5-2B-OptiQ-4bit` | 1.94 |
| stock mlx 4-bit | **UNVERIFIED** — `mlx-community/MiniCPM5-2B-4bit` returned HTTP 401 | — |

### Ranks 6–13 — two formats or fewer (recorded, not recommended)

| Base model | stock 4-bit | oQ4 | oQ4e | OptiQ | JANG |
|---|---|---|---|---|---|
| Fara1.5-4B | `runanywhere/Fara1.5-4B-mlx-4bit` | — | — | `mlx-community/Fara1.5-4B-OptiQ-4bit` (4.22 GB) | — |
| Nanbeige4.2-3B | `MercuriusDream/Nanbeige4.2-3B-mlx-4bit` | — | — | `mlx-community/Nanbeige4.2-3B-OptiQ-4bit` (3.32 GB) | — |
| Spark-X2.5-4B | — | — | — | `mlx-community/Spark-X2.5-4B-OptiQ-4bit` (3.05 GB) | `JANGQ-AI/Spark-X2.5-4B-JANG_8M` (4.39 GB) |
| NVIDIA-Nemotron-3-Nano-4B | — | `RepublicOfKorokke/NVIDIA-Nemotron-3-Nano-4B-oQ4` (2.35 GB) | — | `mlx-community/NVIDIA-Nemotron-3-Nano-4B-OptiQ-4bit` (3.10 GB) | — |
| SmolLM3-3B | `mlx-community/SmolLM3-3B-4bit` (1.75 GB) | `AtBeginDocument/SmolLM3-3B-oQ4` (1.82 GB) | — | — | — |
| Phi-4-mini-instruct | `mlx-community/Phi-4-mini-instruct-4bit` (2.18 GB) | — | `TheWirelessPhoenix/Phi-4-mini-instruct-oQ4e` (2.28 GB) | — | — |
| Ministral-3-3B | `mlx-community/Ministral-3-3B-Base-2512-4bit` (2.80 GB) | `gcoli/Ministral-3-3B-Base-2512-oQ4` (5.74 GB) | — | — | — |
| DeepSeek-R1-Distill-Qwen-7B | — | — | `TheWirelessPhoenix/DeepSeek-R1-Distill-Qwen-7B-oQ4e` (4.48 GB) | — | — |

Searches that returned empty for these bases: `?search=Ministral-3-3B-OptiQ`,
`?search=Ministral-3-3B-JANG`, `?search=Phi-4-mini-oQ`, `?search=DeepSeek-R1-Distill-Qwen-1.5B-OptiQ`,
`?search=Qwen3-30B-A3B-OptiQ`. A search miss is weaker evidence than a confirmed artifact and is
recorded as such.

### Ranks 14–17 — single-format (explicitly useless)

| Base model | Only format found | Repo id | Size (GB) |
|---|---|---|---|
| Llama-3.2-3B-Instruct | stock mlx 4-bit | `mlx-community/Llama-3.2-3B-Instruct-4bit` | 1.82 |
| VibeThinker-3B | OptiQ-4bit | `mlx-community/VibeThinker-3B-OptiQ-4bit` | 2.29 |
| mini-coder-4b | OptiQ-4bit | `mlx-community/mini-coder-4b-OptiQ-4bit` | 3.00 |
| DeepSeek-R1-Distill-Qwen-1.5B | stock mlx 4-bit | `mlx-community/DeepSeek-R1-Distill-Qwen-1.5B-MLX` — **not a single model**: 17.00 GB multi-quant bundle containing `*-2,6_mixed/`, `*-3,4_mixed/`, `*-3,6_mixed/` subdirectories | — |

**These four are useless to us.** They cannot supply more than one cell of the format axis.
Llama-3.2-3B is the clearest case: a well-known, easy-to-run 3 B dense model with no OptiQ, no oQ,
and no JANG artifact anywhere on the Hub.

---

## Q2 — Small MoE candidates (the important one)

### Why this question is the load-bearing one

The failure being chased is: **stock `mlx_lm.server` loads `Jundot/Qwen3.6-35B-A3B-oQ4-mtp`,
returns HTTP 200, generates a clean 64/64 tokens at full speed, and the text is mixed-script token
salad with replacement characters.** Confirmed architecture of that exact checkpoint:

```
Jundot/Qwen3.6-35B-A3B-oQ4-mtp
  model_type        = qwen3_5_moe
  num_experts       = 256
  num_experts_per_tok = 8
  num_hidden_layers = 40
```
Source: `https://huggingface.co/Jundot/Qwen3.6-35B-A3B-oQ4-mtp/raw/main/config.json`.

`mlx-community/Qwen3.5-35B-A3B-OptiQ-4bit` is the **same** architecture at the same expert count
(256 experts, 8 per token, 40 layers), so the runtime-side failure is a 256-expert MoE phenomenon.
A dense-only proof of concept could come back all-green and prove nothing, exactly as the task
warns. The JANG vendor's diagnosis — high expert counts compressed to the same bit width as
attention — makes **expert count the parameter to optimize for**, not total size.

### Ranked by expert count, then by format count

| Rank | Base model | Params (total/active) | **Experts** | Formats | Fits 36 GiB (all formats)? |
|---|---|---|---|---|---|
| 1 | **Qwen3.5-35B-A3B** | 35 B / 3 B | **256** (top-8) | 3–4 | **No** — 55.66 GB for 3 formats |
| 2 | **NVIDIA-Nemotron-3-Nano-30B-A3B** | 30 B / 3 B | **128** + 1 shared (top-6) | 3 / 4 | **No** — 58.45 GB |
| 3 | **Ling-3.0-tiny** | ~8 B | **128** + 1 shared (top-8) | 2 / 4 | Yes (9.11 GB) but 2 formats only |
| 4 | **Mellum2-12B-A2.5B** | 12 B / 2.5 B | 64 (top-8) | 1 verified | — |
| 5 | **OLMoE-1B-7B** | 7 B / 1 B | 64 (top-8) | **1 / 4** | — (useless) |
| 6 | **DeepSeek-V2-Lite** | 16 B / 2.4 B | 64 routed + 2 shared (top-6) | 2 / 4 | mixed bases |
| 7 | **gpt-oss-20b** | 21 B / 3.6 B | 32 (top-4) | 3 / 4 | Yes — 34.07 GB |
| 8 | **LFM2.5-8B-A1B** | 8 B / 1 B | **32** (top-4) | **4 / 4** | **Yes — 20.23 GB** |
| 9 | Qwen1.5-MoE-A2.7B | 14 B / 2.7 B | 60 (top-4) | 1 verified | 2024-era, superseded |
| 10 | granite-3.0-3b-a800m | 3 B / 0.8 B | 40 (top-8) | 1 verified | — |
| 11 | phi-3.5-moe | 42 B | 16 (top-2) | 1 verified | 2024-era, superseded |

### The two candidates that matter

**LFM2.5-8B-A1B** — 8 B total, 1 B active, **32 experts**, top-4, 24 layers, hidden 2048,
`moe_intermediate_size` 1792. This is the *only* model found that combines a published
**four-format set** with MoE architecture. Base config:
`https://huggingface.co/LiquidAI/LFM2.5-8B-A1B/raw/main/config.json`.

| Format | Repo id | Size (GB) |
|---|---|---|
| stock mlx 4-bit | `mlx-community/LFM2.5-8B-A1B-MLX-4bit` | 4.78 |
| *(official stock)* | `LiquidAI/LFM2.5-8B-A1B-MLX-4bit` | 4.85 |
| oQ4 | `stamsam/LFM2.5-8B-A1B-oQ4` | 4.99 |
| oQ4e | `brainworkup/LFM2.5-8B-A1B-oQ4e` | 4.99 |
| OptiQ-4bit | `mlx-community/LFM2.5-8B-A1B-OptiQ-4bit` | 5.47 |
| *(JANG_2L, bonus)* | `JANGQ-AI/LFM2.5-8B-A1B-JANG_2L` | 3.06 |

**Four-format total: 20.23 GB (18.84 GiB).** With JANG: 23.29 GB (21.69 GiB).
Interchangeable alternates: `RepublicOfKorokke/LFM2.5-8B-A1B-oQ4`, `Erkan/LFM2.5-8B-A1B-oQ4`,
`airagrp/LFM2.5-8B-A1B-oQ4e`, `djrsystemservices/LFM2.5-8B-A1B-MLX-oQ4e`.
All six artifacts declare the same `num_experts: 32`, `num_experts_per_tok: 4` — verified per repo.

**The honest limitation:** 32 experts is *eight times fewer* than the 256-expert configuration that
fails. If the defect depends on expert count — which is the working hypothesis — an
LFM2.5-8B-A1B proof of concept must be expected to come back **green** and prove nothing about the
35B-A3B failure. It is a valid test of the *format axis machinery* and a poor test of the *bug*.
This is stated plainly rather than buried: choose it for plumbing, not for diagnosis.

**NVIDIA-Nemotron-3-Nano-30B-A3B** — 30 B total, 3 B active, **128 routed experts** + 1 shared,
top-6, 52 layers, hidden 2688. The highest expert count that has more than two formats.

| Format | Repo id | Size (GB) |
|---|---|---|
| stock mlx 4-bit | `mlx-community/NVIDIA-Nemotron-3-Nano-30B-A3B-4bit` | 17.79 |
| oQ4e | `splats/NVIDIA-Nemotron-3-Nano-30B-A3B-oQ4e` | 18.58 |
| OptiQ-4bit | `mlx-community/NVIDIA-Nemotron-3-Nano-30B-A3B-OptiQ-4bit` | 22.08 |

**Three-format total: 58.45 GB (54.44 GiB) — does not fit.** No oQ4 (non-imatrix) and no JANG artifact
found for this base. Related but distinct: `JANGQ-AI/Nemotron-3-Nano-Omni-30B-A3B-JANGTQ4` and
`OsaurusAI/Nemotron-3-Nano-Omni-30B-A3B-JANG_4M` are for the **Omni** variant, a different base.

**Qwen3.5-35B-A3B** — the failing architecture itself, at 256 experts.

| Format | Repo id | Size (GB) |
|---|---|---|
| stock mlx 4-bit | `mlx-community/Qwen3.5-35B-A3B-4bit` | 20.42 |
| OptiQ-4bit | `mlx-community/Qwen3.5-35B-A3B-OptiQ-4bit` | 23.57 |
| *(JANG_2S)* | `JANGQ-AI/Qwen3.5-35B-A3B-JANG_2S` | 11.67 |
| *(JANG_4K)* | `JANGQ-AI/Qwen3.5-35B-A3B-JANG_4K` | 19.67 |

Three-format total: 55.66 GB (51.83 GiB) — **does not fit**. No oQ4/oQ4e artifact was found under
that exact base name (`?search=Qwen3.5-35B-A3B-oQ4e` returned zero results); the oQ4e 35B-A3B
artifacts on the Hub are for the **Ornith-1.5** derivative
(`scottlowry/Ornith-1.5-35B-A3B-oQ4e-mtp`, `BLCKHWK60/Ornith-1.5-35B-A3B-oQ4e`), which is a
different base model and therefore not the same cell.

A REAP-pruned variant exists and is worth knowing about:
`mlx-community/Qwen3.5-35B-A3B-OptiQ-4bit-REAP-19B` (13.76 GB) keeps the `qwen3_5_moe` type and
40 layers but is pruned to **128** experts — the pruning removes exactly the property under test,
so it is not a substitute for the 256-expert cell.

### MoE candidates that are disqualified

| Base model | Why | Evidence |
|---|---|---|
| **Ling-3.0-tiny** | 128 experts — the ideal small high-expert-count MoE, **but** see Q4: supported only via an oMLX patch, and only 2 of 4 formats exist (stock 4-bit 4.46 GB + oQ4e 4.65 GB). Not a four-format set. | `mlx-works/Ling-3.0-tiny-oQ4e`, `rapid-mlx/Ling-3.0-tiny-MLX-4bit` |
| **OLMoE-1B-7B** | 64 experts, 7 B total — attractive size, but **only the stock 4-bit MLX artifact exists** (`mlx-community/OLMoE-1B-7B-0125-Instruct-4bit`, 3.90 GB). No OptiQ, no oQ, no JANG under any author. | `?search=OLMoE` full listing; `?search=oLMoE-oQ`, `?search=OLMoE-OptiQ` empty |
| **DeepSeek-V2-Lite** | 64 routed + 2 shared experts. Stock exists (`mlx-community/DeepSeek-V2-Lite-Chat-4bit-mlx`) and one oQ4e exists — but that oQ4e is for the **Coder** variant (`pxleng/DeepSeek-Coder-V2-Lite-Instruct-oQ4e`, 9.32 GB), a different base. Two different bases ≠ one format axis. | `?search=DeepSeek-V2-Lite` listing |
| **Mellum2-12B-A2.5B** | 64 experts, `model_type: mellum`, 7.15 GB oQ4e (`intellitour/Mellum2-12B-A2.5B-Thinking-oQ4e-fp16`). No stock MLX 4-bit, no OptiQ, no JANG found. | `?search=Mellum2-12B`, `?search=Mellum` listings |
| **granite-3.0-3b-a800m** | 40 experts, only an unquantized HF release (`ibm-granite/granite-3.0-3b-a800m-instruct`, 6.75 GB). No MLX quantizations at all in `mlx-community`. | `?author=mlx-community&search=granite-3.0-3b-a800m` empty |
| **Qwen1.5-MoE-A2.7B**, **phi-3.5-moe** | 2024-era; single stock quantization each. Superseded by every row above. | `mlx-community/Qwen1.5-MoE-A2.7B-Chat-4bit`, `mlx-community/phi-3.5-moe-instruct-4bit` |

### On gpt-oss-20b (32 experts, 3/4 formats)

| Format | Repo id | Size (GB) |
|---|---|---|
| stock mlx MXFP4 | `mlx-community/gpt-oss-20b-MXFP4-Q4` | 11.21 |
| oQ4 | `cjnielson44/gpt-oss-20b-oQ4` | 11.21 |
| OptiQ-4bit | `mlx-community/gpt-oss-20b-OptiQ-4bit` | 11.65 |

Three-format total: **34.07 GB (31.73 GiB)** — it fits, but only alone, and there is no oQ4e and no
JANG. It also has the same 32-expert weakness as LFM2.5-8B-A1B while costing 1.7× the disk.
Note `cjnielson44/gpt-oss-20b-oQ4` ships `config.json.bak-before-mxfp4-expert-overrides` and
`omlx_oQ4_manifest.json` — evidence that oQ on this base required hand-editing the config, which
makes it a weaker "clean format cell" than LFM2.5-8B-A1B's oQ4/oQ4e pair.

---

## Q3 — Total disk for the top of each list

Sizes are decimal GB, summed from the four format artifacts only (JANG excluded — it is a fifth
format, not part of the axis, and the task's four cells are stock/oQ4/oQ4e/OptiQ).

| Combination | stock | oQ4 | oQ4e | OptiQ | **Total** | In GiB | Fits 36 GiB? | Fits 35 GiB? |
|---|---|---|---|---|---|---|---|---|
| **Dense: Qwen3.5-4B (4/4)** | 3.06 | 3.16 | 3.17 | 4.04 | **13.43 GB** | 12.51 | yes | yes |
| **MoE: LFM2.5-8B-A1B (4/4)** | 4.78 | 4.99 | 4.99 | 5.47 | **20.23 GB** | 18.84 | yes | yes |
| **Both together (the recommended set)** | — | — | — | — | **33.66 GB** | **31.35** | **yes** | **yes** |
| Dense: gemma-4-E4B-it (4/4) | 5.18 | 4.79 | 5.54 | 7.52 | 23.03 GB | 21.45 | yes | yes |
| gemma-4-E4B-it + LFM2.5-8B-A1B | — | — | — | — | 43.26 GB | 40.29 | **no** | **no** |
| MoE: gpt-oss-20b (3/4) | 11.21 | 11.21 | — | 11.65 | 34.07 GB | 31.73 | yes (alone) | yes (alone) |
| MoE: Nemotron-3-Nano-30B-A3B (3/4) | 17.79 | — | 18.58 | 22.08 | 58.45 GB | 54.44 | **no** | **no** |
| MoE: Qwen3.5-35B-A3B (3/4) | 20.42 | — | — | 23.57 | 55.66 GB | 51.83 | **no** | **no** |

**Verdict.**

- The recommended dense+MoE pair fits with **31.35 GiB used of 36 GiB**, leaving ~4.6 GiB headroom
  — enough for the HF cache's `blobs/` + `snapshots/` duplication of metadata and any re-download.
- **No 256-expert model can be held in all formats at once.** Qwen3.5-35B-A3B is 55.66 GB for three
  formats; the failing checkpoint's own architecture simply cannot be the format axis's subject at
  full four-format coverage on this machine.
- **No 128-expert model can be held in four formats either** — Nemotron-3-Nano-30B-A3B is 58.45 GB
  for three, and Ling-3.0-tiny only has two formats.
- Adding a JANG fifth cell to both recommendations costs another 6.27 GB (3.21 + 3.06), taking the
  pair to 39.93 GB = 37.19 GiB — **over budget**. If JANG is added, drop the dense model's OptiQ
  cell or accept that only one family gets a JANG cell.

---

## Q4 — Architecture check

### How mlx-lm actually resolves an architecture

From the oMLX bundle's own mlx-lm, `mlx_lm/utils.py`:

```python
MODEL_REMAPPING = { ... }                       # line 45
model_type = MODEL_REMAPPING.get(model_type, model_type)   # line 187
arch = importlib.import_module(f"mlx_lm.models.{model_type}")  # line 189
```

So the test is mechanical: **the file `mlx_lm/models/<model_type>.py` must exist** (or the type must
appear in `MODEL_REMAPPING`). There is no `auto_map` / `trust_remote_code` path — a repo that
ships `modeling_<x>.py` next to its config does **not** get that code executed. This is precisely
how `gemma4_unified` was lost.

### The check that must be run twice — bundled mlx-lm is not the whole story

Checking only `mlx_lm/models/` gives the wrong answer, because **oMLX vendors patches that register
model types mlx-lm 0.31.3 lacks.** The dispatcher is
`/Applications/oMLX.app/Contents/Resources/omlx/utils/model_loading.py` (lines 499–625), which
pre-loads a patch based on `config["model_type"]`:

| Patch applied when `model_type ==` | Vendored module | Source |
|---|---|---|
| `bailing_hybrid` | `omlx/patches/bailing_hybrid/bailing_hybrid_model.py` | registers `mlx_lm.models.bailing_hybrid` from `scaryrawr/mlx-lm` @ `ling-3.0-flash` branch, head SHA `d719464ff754e65d9dec496ef3fea27bddefd79c` |
| `laguna` | `omlx/patches/laguna/laguna_model.py` | `patches/laguna/__init__.py:92` |
| `hy_v3` | `omlx/patches/hy_v3/` | `patches/hy_v3/__init__.py:132` |
| `mimo_v2` | `omlx/patches/mimo_v2/` | `patches/mimo_v2/__init__.py:27` |
| `deepseek_v4*` (prefix) | `omlx/patches/deepseek_v4/` | `model_loading.py:499` |
| `step3p7` | `omlx/patches/step3p7/` | `model_loading.py:505` |
| `glm_moe_dsa` | `omlx/patches/glm_moe_dsa/` | `model_loading.py:547` |
| `llama4` (top-level or `text_config`) | `omlx/patches/llama4_attention.py` | `model_loading.py:541` |
| `minimax_m3` / `minimax_m3_vl` | `omlx/patches/minimax_m3_mlx_lm/` | `model_loading.py:555` |

**No patch exists for `spark2_5`, `nanbeige`, or `lfm2_vl`.** A scoped grep of the entire
`omlx/` tree for those three strings returns only unrelated matches (`dspark_*` kernel names in
`custom_kernels/glm_moe_dsa/fast.py`). They are genuinely unsupported.

### Per-candidate result

Bundled mlx-lm 0.31.3 models directory, listed whole (119 `.py` modules):
`/Applications/oMLX.app/Contents/Resources/Python/framework-mlx-base/lib/python3.11/site-packages/mlx_lm/models/`
— version confirmed at `mlx_lm/_version.py:3 → __version__ = "0.31.3"` and
`mlx_lm-0.31.3.dist-info/` beside it.

Every import below was **executed**, not inferred, using the bundle's own interpreter
`/Applications/oMLX.app/Contents/Resources/Python/cpython-3.11/bin/python3` with
`importlib.import_module("mlx_lm.models." + type)`, run from
`/Applications/oMLX.app/Contents/Resources/Python/framework-mlx-base/lib/python3.11/site-packages`.

| Candidate | `config.json` `model_type` | `mlx_lm/models/<type>.py` | Import test | oMLX patch | **Verdict** |
|---|---|---|---|---|---|
| **Qwen3.5-4B** | `qwen3_5` (text `qwen3_5_text`) | `qwen3_5.py` present | **OK** | not needed | **USABLE** |
| **gemma-4-E4B-it** | `gemma4` (text `gemma4_text`) | `gemma4.py`, `gemma4_text.py` present | **OK** | not needed | **USABLE** |
| **gemma-4-E2B-it** | `gemma4` (text `gemma4_text`) | present | **OK** | not needed | **USABLE** |
| **LFM2.5-2.6B** | `lfm2` | `lfm2.py` present | (dense, same family as `lfm2_moe` OK) | not needed | **USABLE** |
| **LFM2.5-8B-A1B** (MoE) | `lfm2_moe` | `lfm2_moe.py` present | **OK** | not needed | **USABLE** |
| **gpt-oss-20b** (MoE) | `gpt_oss` | `gpt_oss.py` present | **OK** | not needed | **USABLE** |
| **NVIDIA-Nemotron-3-Nano-30B-A3B** (MoE) | `nemotron_h` | `nemotron_h.py` present | **OK** | not needed | **USABLE** |
| **NVIDIA-Nemotron-3-Nano-4B** | `nemotron_h` | present | **OK** | not needed | **USABLE** |
| **Mellum2-12B-A2.5B** (MoE) | `mellum` | `mellum.py` present | **OK** | not needed | **USABLE** |
| **DeepSeek-V2-Lite** (MoE) | `deepseek_v2` | `deepseek_v2.py` present | **OK** | not needed | **USABLE** |
| **Ling-3.0-tiny** (MoE) | `bailing_hybrid` | **absent** | **FAIL** (`No module named 'mlx_lm.models.bailing_hybrid'`) | **`apply_bailing_hybrid_patch` — registers it** | **USABLE via oMLX only** |
| **Nanbeige4.2-3B** | `nanbeige` | **absent** | **FAIL** | **none** | **DISQUALIFIED** |
| **Spark-X2.5-4B** | `spark2_5` | **absent** | **FAIL** | **none** | **DISQUALIFIED** |
| **LFM2.5-VL-3B** | `lfm2_vl` | file is `lfm2-vl.py` (hyphen) | **FAIL** (`No module named 'mlx_lm.models.lfm2_vl'`) | none (mlx-vlm handles it) | **DISQUALIFIED for the LLM engine** |
| **OLMoE-1B-7B** | `olmoe` | `olmoe.py` present | **OK** | not needed | usable, but 1 format |
| **Fara1.5-4B** | `qwen3_5` | present | OK | not needed | usable, but 2 formats |
| **VibeThinker-3B**, **DeepSeek-R1-Distill-Qwen-7B** | `qwen2` | `qwen2.py` present | OK | not needed | usable, but ≤2 formats |
| **Llama-3.2-3B**, **SmolLM3-3B**, **Phi-4-mini** | `llama`, `smollm3`, `phi3` | all present | OK | not needed | usable, but ≤2 formats |
| **Ministral-3-3B** | `mistral3` (text `ministral3`) | `mistral3.py`, `ministral3.py` present | OK | not needed | usable, but 2 formats |

**Two disqualifications bite.** `spark2_5` and `nanbeige` each have an OptiQ-4bit artifact published
by `mlx-community` — a repo that normally only quantizes what it can serve — yet neither type
resolves in this mlx-lm, and oMLX vendors no patch for either. They are unusable on this machine
today. Both repos ship `modeling_*.py` files beside their configs, which is the tell: the publisher
expected a runtime that loads remote code.

**One finding that contradicts a prior note.** `gemma4_unified` is *not* missing in 0.31.3 — it is
remapped:

```python
"gemma4_unified": "gemma4",  # encoder-free multimodal variant; vision/audio weights stripped by sanitize()
```
`mlx_lm/utils.py:55`. The earlier statement in
`docs/research/2026-09-15-format-matrix-and-tooling.md` (line 35) that 0.31.3 ships `gemma4` but
not `gemma4_unified` is true of the *file list* and false of the *resolution path*. Whether the
`sanitize()` path handles real `gemma4_unified` checkpoints end-to-end is **UNVERIFIED** — the
remapping entry is all that was verified here, and no such checkpoint was loaded.

**One negative result worth recording:** `mlx_lm/models/lfm2-vl.py` uses a hyphen in its filename,
so `importlib.import_module("mlx_lm.models.lfm2_vl")` raises `ModuleNotFoundError` even though the
file sits in the models directory. The module is never reachable through mlx-lm's resolution path.
This is a latent packaging bug in mlx-lm 0.31.3; the architecture check must import-test rather
than `ls`.

---

## Recommendation

**Dense model: `Qwen3.5-4B`.**
Four formats exist, plus a fifth (JANG). It is the smallest complete four-format set at 3–5 B, it
resolves natively in mlx-lm 0.31.3 as `qwen3_5` with no patch, and it is the same
transformer-decoder family as the failing model's attention path.

| Format | Artifact | GB |
|---|---|---|
| stock mlx 4-bit | `mlx-community/Qwen3.5-4B-4bit` | 3.06 |
| oQ4 | `RepublicOfKorokke/Qwen3.5-4B-oQ4` | 3.16 |
| oQ4e | `uingei/Qwen3.5-4B-oQ4e` | 3.17 |
| OptiQ-4bit | `mlx-community/Qwen3.5-4B-OptiQ-4bit` | 4.04 |
| | **Total** | **13.43 GB (12.51 GiB)** |

**MoE model: `LFM2.5-8B-A1B`.**
The only MoE on the Hub with a complete four-format set. 8 B total / 1 B active / 32 experts.

| Format | Artifact | GB |
|---|---|---|
| stock mlx 4-bit | `mlx-community/LFM2.5-8B-A1B-MLX-4bit` | 4.78 |
| oQ4 | `stamsam/LFM2.5-8B-A1B-oQ4` | 4.99 |
| oQ4e | `brainworkup/LFM2.5-8B-A1B-oQ4e` | 4.99 |
| OptiQ-4bit | `mlx-community/LFM2.5-8B-A1B-OptiQ-4bit` | 5.47 |
| | **Total** | **20.23 GB (18.84 GiB)** |

**Combined total: 33.66 GB = 31.35 GiB.** Fits the 36 GiB budget with ~4.6 GiB to spare, and fits the
35 GiB `df` reading.

**State the caveat in every table this pair produces:** the MoE cell has **32 experts**, the failing
checkpoint has **256**. A green result from `LFM2.5-8B-A1B` validates the format-axis machinery; it
does **not** exonerate stock mlx-lm on high-expert-count MoE. No 256-expert model fits in all
formats at once on this machine (best case 51.83 GiB), so that hypothesis cannot be closed by a
four-format matrix here at all — it needs a single-format, two-runtime design instead.


