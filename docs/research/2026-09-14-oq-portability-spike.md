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
