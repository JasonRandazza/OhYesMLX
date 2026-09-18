# Plan 02-01 — the accuracy harness spike: endpoint validation, the vMLX string-stop deadlock, the reasoning-channel trap, and the pins the campaign inherits

Date: 2026-09-18. **Measured.** This document reports the execution of Plan 02-01, the harness
spike and local-endpoint validation defined in `docs/research/2026-09-17-v2-track2-accuracy-study-design.md`
`§6.2`. One cell was touched — `stock4bit__vmlx`, artifact `mlx-community/Qwen3.5-4B-4bit` at
snapshot `0e7ffd5c629ef7719d4cbc04069232580bfa9d9c` — and one cell is not a study. No format was
scored against another, no accuracy comparison is published here, and **nothing in this document
answers Q1–Q4**.

What it does do is the thing the spike exists for: it establishes that the instrument works, it
pins the harness and the runtime, it prices the one presentation setting the design left open, and
it reports four findings that would each have corrupted a campaign run before a single
format-versus-format number existed — one of them a bug in the serving engine that had to be
fixed before any benchmark could complete.

Read with, in this order:

- **The study design** — `docs/research/2026-09-17-v2-track2-accuracy-study-design.md`. Every
  section reference below is to that document unless another file is named. `§6.2` is the spike's
  own ten-step protocol and `§6.2`'s step numbers are used as the spine of `§10`.
- **The spike record** — `results/spike-eval/spike-report.json` and
  `results/spike-eval/lm_eval_output.txt`, plus the harness's own
  `results/spike-eval/mlx-community__Qwen3.5-4B-4bit/results_2026-09-17T22-25-38.103494.json`
  and its `samples_gsm8k_2026-09-17T22-25-38.103494.jsonl`.
- **The scratch probes** — `scratch/*.py`, twenty-one probes kept in the repository. They are the
  spike's working record: they show what was tried and in what order. Their *output* was written to
  `/tmp/spike_*/` and to the console, not into the repository; where this document cites a number
  that exists only in a `/tmp` results file, it says so, and `§10` lists that as a record-keeping
  defect to fix before the campaign.

---

## 1. Executive summary and headline status

### 1.1 The one-paragraph verdict

The instrument works. `lm-evaluation-harness` 0.4.13 drives vMLX 1.6.59 over the OpenAI-compatible
`/v1/chat/completions` endpoint, reads the answer out of the channel the model actually uses,
records every item verbatim, and produces byte-reproducible output across independent invocations.
Two things had to be solved to get there, and both are now pinned: **a variable-shadowing bug in
vMLX's scheduler that deadlocks the engine on a request carrying a string stop sequence** (which is
every request of every task in this study), and **the reasoning-channel trap** that `§3.5`
predicted, which turns a thinking model's benchmark run into a column of zeros unless reasoning is
switched off or budgeted for. With the bug patched and `enable_thinking=false`, all four tasks run
clean and fast: ~1.0–1.9 s/item on MMLU, 3.27 s/item on GSM8K, 0.6 s/item on ARC-Challenge
and 3.87 s/item on IFEval, which puts a full 3,030-item cell in the **1.2–1.9 h** range rather than
the design's 5–7 h estimate — so the pre-registered downward budget dial of `§3.3` is **not**
triggered.

Against that good news, the spike also found the thing a spike is for: **at each task's own default
few-shot count, two of the four tasks cannot score at all.** `mmlu_generative`'s installed default
is 0 shots and `arc_challenge_chat`'s is 0 shots; at 0 shots the model answers in prose and the
harness's filters cannot extract a letter, so MMLU scored **0.00 on all 57 subjects** (114 items)
and ARC-Challenge scored **0.00 on 2 items — including one item the model answered correctly**
("The best answer is C" against a target of `C`, failed by the `remove_whitespace` filter). The
same mechanism, measured directly on 5 identical items, is what makes `fewshot_as_multiturn`
worth 60 accuracy points on MMLU rather than 0: **True → 0.60, False → 0.00**. The setting is frozen
at `true`, the MMLU default is overridden to 5 shots because the spike measured that it must be,
and the ARC-Challenge reading is left as an open decision for the campaign (`§6.5`, `§10.3`).

### 1.2 Status of the ten `§6.2` exit criteria

| # | `§6.2` step | status | evidence / what is missing |
|---|---|---|---|
| 1 | Install and version-pin the harness; record `uv` and `lm-eval` versions; harness runs offline afterwards | **PASS** | `uv 0.11.20 (9252ba6b5 2026-06-10 aarch64-apple-darwin)`, `lm-eval 0.4.13`; offline re-verified **2026-09-18**: `uv run --isolated --offline --with "lm-eval[api,ifeval]==0.4.13"` → `Installed 1 package in 4ms`, `lm-eval 0.4.13`, 0.248 s (`§2.2`) |
| 2 | Enumerate the installed task registry; pin each task's exact id, version hash and generative variant | **PASS** | four ids, four versions, four task hashes, read from the installed registry and the harness's own output (`§6.1`) |
| 3 | Start runtime R through `runtimes.RUNTIMES[...]`, read the resolved `model_id` and version, issue the canary | **PASS** | canary answered in `content`, vMLX 1.6.59, `port_released: true`; the switch that keeps it there is found and recorded (`§4`) |
| 4 | Price the two `fewshot_as_multiturn` settings on one task, one format | **PASS** | 0.60 vs 0.00 on 5 identical items, both scores recorded as the pin's provenance (`§5`) |
| 5 | Run one task at the pinned budget; audit item count, identity hash, effective `num_fewshot` and cap | **PASS, at spike scale** | item counts and caps audited from the harness's own JSON; the `--limit`-per-subtask trap is now *measured* (57 subjects × limit 2 = 114 items); identity material found (`doc_id` + `doc_hash`/`prompt_hash`/`target_hash`) (`§6`) |
| 6 | Measure the generation-length distribution; set per-task caps at the 99th percentile | **NOT MET** | no per-item token count exists in any recorded artifact; the endpoint model drops `usage` and the harness never tokenizes (`§7`). Caps in use are *audited*, not *calibrated* |
| 7 | Measure seconds per item, per task, per runtime and model | **PASS** | harness request-phase rates and `total_evaluation_time_seconds` for eight invocations (`§8`) |
| 8 | Verify determinism: the same item twice in one process, and once in a second block | **PARTIAL** | two independent invocations reproduced both GSM8K completions byte-for-byte and their `prompt_hash`es; n = 2 items, one task, one cell; no within-process repeat (`§6.4`) |
| 9 | Verify the retry/reconciliation behaviour: count requests at the runtime and compare with items | **NOT VERIFIED** | the retry rule is pinned from the installed source (3 attempts, 300 s, concurrency 1) but the runtime's request count was never captured, so items ≠ requests could not be checked (`§6.4`, `§10.3`) |
| 10 | Record the chat-template digest across each study's five artifacts | **PASS** | dense column byte-identical (7,756 B, `sha256 a4aee8af…`); MoE column five distinct templates, declared as a prompt-composition difference (`§9`) |

**A green spike is not acceptance.** Three of the ten criteria are not fully met, and `§10` lists
them as gates rather than footnotes. Two of them (6 and 9) are *measurement* gaps that a short
calibration run closes; the third (8) is an n = 2 observation that the campaign's own replicates
will extend.

### 1.3 The four findings that change the campaign

1. **The vMLX string-stop deadlock (`§3`).** In `vmlx_engine/mllm_scheduler.py`, the post-decode
   string-stop check reused the response loop's own counter variable:
   `idx = full_text.find(stop_str, search_start)`. A stop string that is *not* present in the
   per-token search window returns `-1`, `idx += 1` sets it back to `0`, and the loop re-processes
   the same response forever, pinning the step executor thread at 100 % CPU. The pinned
   `eos_string=<|im_end|>` means **every** request of **every** task in this study carries a string
   stop, so the engine's exposure to this bug was universal rather than task-specific. Renamed to
   `match_idx` in both engine copies and verified byte-identical with `cmp`.
2. **The reasoning-channel trap, and the switch that closes it (`§4`).** The canary passes: the
   answer arrives in `content`. On benchmarks it does not survive — with thinking on and a
   `max_gen_toks` smaller than the trace, vMLX returns HTTP 502 `reasoning_only_no_content` or a
   null `content`, and `lm-evaluation-harness` has no reasoning-channel rule. `--gen_kwargs
   enable_thinking=false` reaches vMLX as a top-level field of the chat-completions body and turns
   the same items into answers: IFEval 0.00 → 1.00 and 45.8 s → 12.8 s for the same two items.
3. **`fewshot_as_multiturn: true`, priced rather than preferred (`§5`).** Same 5 MMLU items, same
   model, same runtime, one flag apart: 0.60 vs 0.00. With the shots as alternating messages the
   answer is a bare letter and `get_response` matches; with the shots inlined as text the model
   echoes the full choice string ("D. All of the above") and the filter cannot extract a letter.
4. **Caps and defaults are not what the command line says (`§6.3`, `§7`).** `max_gen_toks` in
   `--model_args` is only a *default*: `arc_challenge_chat` runs at its own 100 tokens and `ifeval`
   at its own 1,280, whatever the command line passes — and ARC's 100 is **below the 112-token
   reasoning trace the canary produced**, so with thinking on ARC-Challenge cannot complete a trace
   inside its own cap. Likewise `num_fewshot` is not 5 and 25 by convention; the installed
   registry says 0 for MMLU and 0 for ARC-Challenge, and 0 is what the spike's all-zero runs show.

---

## 2. Tooling and runtime provenance

### 2.1 The pins, in one table

| element | pinned value | where it is recorded |
|---|---|---|
| evaluator | `lm-evaluation-harness` **0.4.13**, installed as `lm-eval[api,ifeval]==0.4.13` | `spike-report.json` → `lm_eval_version`; every results JSON → `lm_eval_version` |
| runner | `uv` **0.11.20 (9252ba6b5 2026-06-10 aarch64-apple-darwin)** | `spike-report.json` → `uv_version` |
| isolation | `uv run --isolated --with …`, so `ohyesmlx/` gains no import, no module and no entry in `pyproject.toml` (`§4.3`) | `scripts/probe_accuracy_spike.py`; the isolated env resolves at `/Users/jrazz/.cache/uv/archive-v0/C1AjZzuUCa8t3OMR/lib/python3.13/site-packages/lm_eval` (the results JSON's `config_source` names the task YAML under it) |
| serving runtime | **vMLX 1.6.59**, port 8000 | `spike-report.json` → `runtime_version`, `runtime`; `vmlx_engine/__init__.py:15` → `__version__ = "1.6.59"` |
| engine patch | **1.6.59 + the local `mllm_scheduler.py` stop-deadlock fix** — the version string does **not** record it | `§3`; `sha256 9710d2b9cf07abc7380f46fef240e64febb2d06d52eb7f64236bd0e76cf686f7` |
| model artifact | `mlx-community/Qwen3.5-4B-4bit` at `0e7ffd5c629ef7719d4cbc04069232580bfa9d9c` | `spike-report.json` → `artifact`; `§2.4` of the design for its bytes |
| served model id | `mlx-community/Qwen3.5-4B-4bit` (the resolved `Handle.model_id`, not the path) | `spike-report.json` → `model_id` |
| cache state | `"off"` → `--disable-prefix-cache --disable-block-disk-cache` on the start command | `spike-report.json` → `cache_state`; `runtimes.CACHE_STATE_OFF` |
| endpoint model | `--model local-chat-completions` with `--apply_chat_template` | `lm_eval_output.txt` invocation line |

The start command is not hand-written anywhere; it comes from `runtimes.RUNTIMES["vmlx"]`, which is
the point of `§4.3`'s rule that the start command *is* a pin:

```
vmlx serve <artifact> --host 127.0.0.1 --port 8000 --served-model-name mlx-community/Qwen3.5-4B-4bit
  --stream-interval 1 --continuous-batching --max-num-seqs 1 --no-jit --disable-native-mtp
  --disable-prefix-cache --disable-block-disk-cache
```

`--no-jit` and `--disable-native-mtp` are the JANG-study floor configuration carried over unchanged,
so a Track 2 score describes the same floor configuration a Track 1 speed number describes.

### 2.2 Offline execution, verified rather than asserted

`§4.3` requires the uv cache to be warm before any campaign block, and `§6.2`'s step 1 exit
criterion is "the harness runs offline afterwards". On 2026-09-18 this was re-run with uv's network
access refused at the flag level:

```
$ uv run --isolated --offline --with "lm-eval[api,ifeval]==0.4.13" \
    python -c "import importlib.metadata as m; print('lm-eval', m.version('lm-eval'))"
Installed 1 package in 4ms
lm-eval 0.4.13
real  0m0.248s
```

The `--offline` flag makes uv refuse the network; the run completed in a quarter second and
installed one package from the local cache. The spike's own record agrees: the tracked invocation
logs `Installed 1 package in 2ms`. **The exit criterion is met.** What this does not prove is that
no *transient* fetch happened on 2026-09-17; it proves that a fetch is no longer necessary, which
is the property the campaign needs.

### 2.3 The recorded invocation, verbatim

```
lm_eval --model local-chat-completions \
  --model_args base_url=http://127.0.0.1:8000/v1/chat/completions,model=mlx-community/Qwen3.5-4B-4bit,
    tokenizer=/…/models--mlx-community--Qwen3.5-4B-4bit/snapshots/0e7ffd5c…,
    think_end_token=</think>,eos_string=<|im_end|>,max_gen_toks=1024,max_length=4096 \
  --apply_chat_template --gen_kwargs enable_thinking=false \
  --tasks gsm8k --limit 2 --output_path results/spike-eval/ --log_samples
```

Harness-side defaults that were **not** overridden, and therefore apply to the campaign as well:
`num_concurrent = 1`, `max_retries = 3`, `timeout = 300 s` (`lm_eval/models/api_models.py`). The
`--limit 2` run logs `Concurrent requests are disabled. To enable concurrent requests, set
num_concurrent > 1`, which is `§3.4`'s concurrency pin confirmed from the harness's own mouth rather
than from its documentation.

### 2.4 Three pins that are recorded but inert — do not read them as controls

The audit found three `--model_args` that the harness accepts, writes into its results JSON, and
never uses on this endpoint model. Each one is a place where a later reader could believe a control
exists that does not:

| pin | what the record says | what actually happens |
|---|---|---|
| `tokenizer=<artifact_dir>` | recorded in `model_args` and in the results JSON | the invocation logs `Using tokenizer None`, and `LocalChatCompletion.tok_encode` returns its input unchanged (`lm_eval/models/openai_completions.py`). Nothing is tokenized harness-side |
| `max_length=4096` | recorded in `model_args` | logged as `Tokenized requests are disabled. Context + generation length is not checked.` No context-length check runs |
| the artifact's chat template | the results JSON carries `chat_template: ""` and `chat_template_sha: null` | the harness sends `messages` and the runtime applies its own template server-side. The template that matters is the runtime's, which is why `§9` audits it in the artifacts |

**`think_end_token` and `eos_string` are live**, and they are load-bearing: `think_end_token`
drives `postprocess_generated_text`'s reasoning strip (`§4.2`), and `eos_string` is appended to
every task's `until` list (`§6.3`).

### 2.5 Lifecycle, and the one line that closes it

The runtime was started and stopped through `runtimes.RUNTIMES["vmlx"]`, never by hand;
`Handle.stop()` runs in a `finally` and the port is re-checked. The record's closing line is
`"port_released": true`, and the start/stop discipline is `§3.7`'s item 7 in practice: one runtime
holds weights at a time, and a block that does not release its port has failed whatever else it
reported.

Two provenance subtleties worth printing, because both look like something they are not:

- **`git_hash: 935cd6e` in every results JSON is the OhYesMLX repository's HEAD, not a harness
  commit.** `lm_eval/loggers/utils.py`'s `get_git_commit_hash()` shells `git describe --always` and
  falls back to `get_commit_from_path(os.getcwd())`; with the harness installed from a wheel inside
  a uv archive there is no git directory to read, so the field records *the directory the command
  ran in*. It is a useful provenance field, and it is not the harness's version. The harness's
  version is the string `0.4.13`.
- **The runtime version string cannot distinguish the patched engine from the shipped one.** The
  fix in `§3` is a local edit inside `/Applications/vMLX.app`; `__version__` stayed `1.6.59`. Any
  block in this campaign must therefore hash the engine file it ran against (`§10.3`).

---

## 3. Upstream fix: the vMLX string-stop deadlock bug

### 3.1 The symptom, and how far the record can carry it

The first live probes drove the endpoint directly (`scratch/test_vmlx_req.py`, written 20:53; then
`test_stops.py` at 20:57, `test_stops_debug.py` at 21:04, `diagnose_vmlx_hang.py` at 21:09,
`test_second_req.py` and `test_stop_varieties.py` at 21:10, `test_empty_stop.py` at 21:11) and the
picture they were built around is unambiguous: **a request that carries a string stop sequence does
not return, and the same request without one returns in milliseconds.** The four traces that follow
(`trace_stop_hang.py` 21:13, `trace_steps_count.py` 21:15, `trace_step_internal.py` 21:25,
`trace_next_internal.py` 22:10) walk the boundary inwards — engine call, scheduler step,
batch-generator `_next`, response processing — and `test_fixed_stop.py` (22:11) asserts the exact
buggy source line before monkeypatching the method and getting both stop tests to finish. The file
edit to the engine landed at **22:12**.

What the record *does not* contain is the console output of the failing invocations, so this
document does not claim which run first hung or for how long. Two facts from the filesystem mark the
edge of what is known: the sweep written at 22:17:40 (`scratch/test_spike_runs.py`) produced a
results file for its middle leg (`/tmp/spike_ifeval/`, 22:18:02–22:18:44) and **no results file at
all for its ARC-Challenge and GSM8K legs**, which are the two legs that carry multi-entry stop
lists; and every invocation after 22:19:59 — all of them carrying stop lists and all of them with
`enable_thinking=false` — completed and wrote one. The pre-fix hang is documented by the probes that
were written to chase it; the fix's behavioural verification is the post-22:19:59 record, plus the
source diff below, which does not depend on any run at all.

### 3.2 The defect, in source

`/Applications/vMLX.app/Contents/Resources/vmlx-engine-source/vmlx_engine/mllm_scheduler.py`, in
`_process_batch_responses`' post-decode string-stop check:

```python
idx = 0
while idx < len(responses):                      # the response loop counter
    response = responses[idx]
    …
    if request.sampling_params.stop:
        full_text = detok.text
        in_think = '<think>' in full_text and '</think>' not in full_text.split('<think>')[-1]
        if not in_think:
            max_stop_len = max(len(s) for s in request.sampling_params.stop)
            search_start = max(0, len(full_text) - len(new_text) - max_stop_len + 1)
            …
            for stop_str in request.sampling_params.stop:
                idx = full_text.find(stop_str, search_start)     # <-- shadows the loop counter
                if idx >= 0:
                    string_stop_truncate = idx
                    new_text = ""
                    break
    …
    outputs.append(output)
    idx += 1                                     # <-- now increments a character offset, or -1
```

The inner assignment writes a **character offset** (or `-1`) into the variable that the outer loop
uses as a **response index**. Two consequences, and the second is the fatal one:

1. **On a hit**, `idx` becomes the offset of the matched stop string, so `idx += 1` resumes the
   response loop at an arbitrary response. Responses are skipped, and `outputs` loses rows.
2. **On a miss**, `find` returns `-1`, the condition fails, the loop falls through, and `idx += 1`
   evaluates to `0` — the loop restarts at `responses[0]` and never advances. The thread spins, the
   request never completes, and the client waits forever on a connection the server believes is
   still being worked on.

A miss is not the rare case. `search_start` is a **per-token window**
(`len(full_text) - len(new_text) - max_stop_len + 1`), so on most tokens none of the configured stop
strings appears in it at all. The steady state is the infinite loop, and the exit from it is luck:
the loop advances only on a token whose window happens to contain one of the stop strings, and even
then it advances to a character offset rather than to the next response.

The check is skipped entirely while an unclosed `<think>` block is open (`in_think`), which is why a
*thinking* run does not trip this on the trace itself — and why the trap in `§4` and the deadlock
here are two different doors into the same room: both are hit by the same requests, in the same
conditions, on the same model.

### 3.3 The blast radius inside this study, which is the whole study

`eos_string=<|im_end|>` is pinned in `--model_args` and `handle_stop_sequences` appends it to every
task's `until` list, so **every request of every task carries at least one string stop**:

| task | `until` in the task's own config | effective `stop` after the `eos_string` merge |
|---|---|---|
| `gsm8k` | `["Question:", "</s>", "<|im_end|>"]` | 3 sequences |
| `mmlu_generative` | `["</s>", "\n"]` | 3 sequences (`"</s>"`, `"\n"`, `"<|im_end|>"`) |
| `arc_challenge_chat` | `["\n\n", "."]` | 3 sequences (`"\n\n"`, `"."`, `"<|im_end|>"`) |
| `ifeval` | `[]` | 1 sequence (`"<|im_end|>"`) |

A spine that ran this study without the fix would be exposed on **every** request it issues, because
the pin itself guarantees a stop list on all of them — and the collected record shows two such
invocations producing no results file at all (`§3.1`). That is the confound ledger's bucket-one
failure: caught by an instrument that could not run, rather than by a number that looked wrong.

### 3.4 The fix, and how it was verified

The variable was renamed, in the inner loop only:

```python
            for stop_str in request.sampling_params.stop:
                match_idx = full_text.find(stop_str, search_start)
                if match_idx >= 0:
                    string_stop_truncate = match_idx
                    new_text = ""
                    break
```

`mllm_scheduler.py` exists twice in the bundle — the readable source tree and the copy inside
`bundled-python`, which is the file the app actually imports — and **both** were patched on
2026-09-17 at 22:12. Verification is by content, not by recollection:

```
$ cmp -s \
  /Applications/vMLX.app/Contents/Resources/vmlx-engine-source/vmlx_engine/mllm_scheduler.py \
  /Applications/vMLX.app/Contents/Resources/bundled-python/python/lib/python3.12/site-packages/vmlx_engine/mllm_scheduler.py
byte-identical
$ shasum -a 256 <both paths>
9710d2b9cf07abc7380f46fef240e64febb2d06d52eb7f64236bd0e76cf686f7  (both)
```

What this document can and cannot say about the fix, precisely:

- **Verified here:** the shipped copies are byte-identical to each other, both contain `match_idx`
  and no longer contain the shadowing assignment, and the patched region is the only difference
  visible at that site.
- **Verified by the campaign's own record:** the post-fix invocations that *do* carry stop lists
  complete — `gsm8k` with 3 stops, `mmlu_generative` with 3 stops, `arc_challenge_chat` with 3 stops
  — each in seconds, and each wrote a results file (`§8.1`).
- **Not verified here:** a controlled pre-fix/post-fix A/B in this document. The pre-fix state no
  longer exists on disk, and `scratch/test_fixed_stop.py` is a monkeypatch of the *running* engine's
  method (a different mechanism from the source edit, used to confirm the diagnosis before the file
  was edited). I did not start a runtime for this report.

### 3.5 The standing consequence for Phase 2

The version string does not record this patch, so vMLX's provenance for every Track 2 block is
"**1.6.59 + local `mllm_scheduler.py` fix, sha256 `9710d2b9…`**". `§4.1`'s confound #9 refuses a
campaign that spans two versions of one runtime; a local patch is a version in everything but the
string. The gate is one command per block, recorded in the manifest — `shasum -a 256` of the engine
file — and it is listed in `§10.3`.

---

## 4. The reasoning-channel trap and the thinking-mode resolution

### 4.1 The canary passed, and the canary is not enough

The canary of `§3.5` was issued against the live endpoint and its **entire** response is kept
verbatim in `results/spike-eval/spike-report.json`:

| field | value |
|---|---|
| request | `{"messages": [{"role": "user", "content": "What is 2+2? Answer with just the number."}], "temperature": 0.0, "max_tokens": 256, "stream": false, "model": "mlx-community/Qwen3.5-4B-4bit"}` |
| `choices[0].message.content` | `"4"` |
| `choices[0].message.reasoning_content` | a 112-token trace beginning `"Thinking Process:\n\n1.  **Analyze the Request:** …"` |
| `choices[0].finish_reason` | `stop` |
| `usage` | prompt 18, completion 112, total 130 |
| channel the harness reads | **`content`** — the rule of `§3.5` is satisfied for this (runtime, model, artifact) |

The order's console log records the same request returning in **1.49 s**; no artifact carries that
latency, so treat it as a console record rather than a file-backed number (this is exactly the
hygiene problem `§10.3` asks the campaign to fix).

So the canary says the channel is fine — and the canary would have been *wrong*. The trap does not
fire on a question the model can answer in four tokens of content: it fires when the generation
budget runs out **inside the reasoning trace**, before a `</think>` and before any content. Then one
of two things happens, and they are different failures:

| signature | what the runtime returns | what the harness does | what a speed-only reader sees |
|---|---|---|---|
| **A — null content** | HTTP 200 with `choices[0].message.content == null` | `parse_generations` returns `None`; the caller substitutes `LMEVAL_MODEL_NONE_ANSWER_PLACEHOLDER`, which **defaults to the empty string**, and logs one warning per item: `API returned null content. Content filled with … Check reasoning_content field or generation limits.` | a scored item, 0 %, and a warning that scrolls past |
| **B — 502 `reasoning_only_no_content`** | HTTP 502 | `response.raise_for_status()`, preceded by `API request failed! Status code: 502 … Retrying.`; tenacity retries **3×**, then raises | a failed invocation — loud, but three times as slow |

Both signatures were observed in the spike's working record. This is `§3.5`'s trap with its exact
code path now named: `lm_eval/models/openai_completions.py` (`LocalChatCompletion.parse_generations`
reads `choices["message"]["content"]` and nothing else) and `lm_eval/models/api_models.py` (the
placeholder substitution). **The harness has no reasoning-channel rule, exactly as the design
predicted — but it is not silent about it in case A, and it is not silent at all in case B.** The
publishable correction is therefore narrower than "it scores 0 % with nothing raised": it scores
0 % with a per-item warning that nothing in the score distinguishes from a wrong answer.

### 4.2 The switch, and why it is a *pin* rather than a preference

`--gen_kwargs enable_thinking=false` is the dispatch's mechanism, and it works because of one line
in the harness's payload builder. `LocalChatCompletion._create_payload` pops the fields it knows
(`do_sample`, `max_gen_toks`/`max_tokens`, `temperature`, `until`) and then splats the rest into the
body:

```python
        return {
            "messages": messages,
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stop": stop[:4],
            "seed": seed,
            **gen_kwargs,
        }
```

So `enable_thinking` arrives at vMLX as a **top-level field of the chat-completions request** — not
a chat-template kwarg, not a header. vMLX accepts it there: `ChatCompletionRequest.enable_thinking:
bool | None = None` (`vmlx_engine/api/models.py:300`), with server-side handling around it that maps
`reasoning_effort` and the model's own defaults into the same field. The runtime-side equivalent,
found by source reading and **not** exercised in the spike, is `vmlx serve
--default-enable-thinking false`, which would set the default for the whole column without a
per-request field.

The design anticipated this shape — `§3.5`'s mechanism 3, "the switch, if the canary fails" — but
the spike's sequence was different, and the difference is worth stating plainly: **the canary did
not fail; the benchmarks did.** The switch was adopted on benchmark evidence, which makes it a
declared **condition** of the study rather than a repair to a broken canary.

### 4.3 What the switch buys, measured

All figures below are from the spike's own results JSONs; "s/item" is
`total_evaluation_time_seconds / effective items` and **includes** the harness's startup, so it is
an upper bound (`§8.2`).

| task (items) | thinking ON | thinking OFF |
|---|---|---|
| `ifeval` (2) | 0.00 strict / 0.00 loose, 45.81 s → 22.90 s/item | **1.00 strict / 1.00 loose**, 12.85 s → 6.42 s/item |
| `gsm8k` (2) | no results file survives for this configuration; the console record carries **15.30 s/item** | **1.00 strict / 1.00 flexible**, 10.69 s → 5.35 s/item; the tracked spike-report run adds 3.37 s/item from the harness's request-phase progress line |
| `mmlu_generative` (114 at 0-shot) | not run | 0.00 (a formatting result, `§6.5`) in 135.49 s → 1.19 s/item |
| `mmlu_virology_generative` (5, 5-shot) | not run | **0.60**, 8.53 s → 1.71 s/item |
| `arc_challenge_chat` (2) | not run | 0.00 (a formatting result, `§6.5`) in 5.37 s → 2.69 s/item |

The order's console record puts the GSM8K contrast at **3.27 s/item with thinking off against
15.30 s/item with thinking on (4.7×)**, and IFEval at 3.87 s/item, ARC-Challenge at 1.7 it/s
(0.6 s/item) and MMLU at ~1.0–1.9 s/item. Those four rates come from the harness's own
`Requesting API: … it/s` line during the scratch runs, which was printed to the console and not
saved; the rates in the table above are the file-backed upper bounds for the same invocations. Where
the two disagree, the console rate is the better per-item estimate and this document treats it as
such.

**What the switch also does, and this is not free.** With `enable_thinking=false` the setting is
uniform across every cell, which removes the truncation confound (`§4.1` #3) and makes
`§3.5`'s truncation-FAIL rule almost unreachable — good for the campaign. But it also means the
study no longer observes the artifacts' **native** reasoning behaviour at all: the per-cell
thinking rate that `§3.5` asks the manifest to publish becomes 0 **by construction**, not by
measurement, and `§3.5`'s sentence "the model's *use* of it is measured and published per cell" is
no longer satisfied by this pin. The design's open question `§8.2` ("the thinking-off arm … it is
named and not scheduled") is now the main arm. That is a decision the coordinator has to make and
record, because it changes what a score means: these scores are the artifacts' *non-thinking*
accuracy, and a format that damages long reasoning traces specifically would not show it here.

### 4.4 The residual risk the canary rule should carry forward

`§4.5`'s pre-flight already requires the canary to "answer in the channel the harness reads". The
spike's evidence says that check is necessary and **not sufficient**: the canary answered correctly
in 112 completion tokens at a 256-token budget, and the same model under a 100-token task cap
(`arc_challenge_chat`'s own, `§6.3`) could not have. A canary that passes says the channel is right
*at that budget*; it says nothing about the budget. The cheapest hardening is to keep the canary's
`max_tokens` at or above the largest per-task cap the campaign will use, and to record the canary's
`usage.completion_tokens` beside the caps.

---

## 5. Presentation pricing: `fewshot_as_multiturn`

### 5.1 The two runs

`§3.6` step 2 asks for one task, one format, both settings, the two scores recorded as the pin's
provenance. The spike ran MMLU virology generative — the subject used throughout the MMLU work —
5-shot, on the **same five items**, against the **same** cell, with `enable_thinking=false` in both:

| run | flag | task hash | `exact_match,get_response` | seconds, 5 items |
|---|---|---|---|---|
| A | `--fewshot_as_multiturn True` (the harness's default; the tracked log prints `Using default fewshot_as_multiturn=True`) | `bcc7df3f54bf203c47d8820526a40d16bffdb425e7aee0cb99518f8594b3589c` | **0.60** (3/5) | 8.53 |
| B | `--fewshot_as_multiturn False` | `83072eff8b2185a5e22f7139af067eef409e8cb0ae8ec005e8c93637811634cb` | **0.00** (0/5) | 8.77 |

Both runs are `scratch/test_mmlu_5shot.py` and `scratch/test_mmlu_singleturn.py`; their
`--log_samples` output is under `/tmp/spike_mmlu_5shot/` and `/tmp/spike_mmlu_5shot_singleturn/`
(the durability defect of `§10.3`).

### 5.2 The mechanism, item by item

The `get_response` filter is `regex "^(.*?)(?=\\n|$)"` → `remove_whitespace` → `take_first`: take
the first line and strip whitespace. There is no letter extraction. So the score turns entirely on
whether the model's first line *is* the letter:

| item | target | A (`multiturn=True`) response → filtered | B (`multiturn=False`) response → filtered |
|---|---|---|---|
| 0 | `A` | `C` | `D. unknown` |
| 1 | `D` | `D` | `D. All of the above` |
| 2 | `B` | `D` | `D. Tuberculosis` |
| 3 | `B` | `B` | `B. Virus replication happens at an intracellular level` |
| 4 | `B` | `B` | `B. Exclusively breast fed for six months` |

Read the targets against column B carefully: **three of the five answers are correct and all five
score wrong**, because the choice text is echoed and the filter compares strings. Column A is the
same model, same items, same sampling: the shots as alternating `user`/`assistant` messages (the
recorded prompt is `system` + five `(user, assistant)` pairs + the query, 1,213 characters of
content, 12 messages) elicit the bare letter, and the first line matches.

The finding is not "multiturn is better". It is that **the presentation decides whether this task
can be scored at all**, and `§3.6`'s "one frozen setting" therefore has to be frozen at `true` or
the MMLU reading measures formatting.

### 5.3 The pin, and two consequences worth keeping

- **Frozen setting: `fewshot_as_multiturn: true`** for every task of every cell of every study,
  with runs A and B above as the provenance.
- **The setting changes the harness's task hash.** The same task id under the two settings carries
  two different hashes (`bcc7df3f…` vs `83072eff…`), because the resolved config is part of what is
  hashed. This is a gift to `§3.3`'s item-identity check and a trap for a careless one: two cells at
  the same task id but different presentation will *not* hash alike, and the runner should refuse
  them rather than average them. The identity check must be per `(task id, resolved config)`, and the
  task hash is the cheapest way to enforce exactly that.
- **The same mechanism explains the 0-shot zeros of `§6.5`** — at 0 shots the model answers in prose
  or in choice text, and the filter has nothing to extract.

---

## 6. Task registry and effective-configuration audit

### 6.1 The four pins

Read from the installed registry inside the isolated environment
(`…/lm_eval/tasks/…`) and from the harness's own results JSON, which records the resolved config
verbatim. Every hash below is the harness's `task_hashes` entry — a fingerprint of the task
**including its resolved configuration**, which is why two hashes appear for MMLU in `§5.1`.

| task id | version | task hash | effective `num_fewshot` | effective cap | effective `stop` | filter / metric | universe |
|---|---|---|---|---|---|---|---|
| `mmlu_generative` (group: 57 subject subtasks + 4 category groups) | subtask metadata `3.0`, group `3` | `mmlu_virology_generative` = `bcc7df3f54bf203c47d8820526a40d16bffdb425e7aee0cb99518f8594b3589c` (at 5-shot, multiturn) | **0 unless passed**; 5 measured working | model default (`max_gen_toks`) — the template sets none | `["</s>", "\n", "<|im_end|>"]` | `get_response` / `exact_match,get_response` | 57 subjects, **14,042** items |
| `gsm8k` | `3.0` | `1b3f08b929018851ea417880bab9c364c59f3a7d13a2c1276f1b821318759a08` | **5** (from the task YAML) | model default | `["Question:", "</s>", "<|im_end|>"]` | `strict-match` + `flexible-extract` / `exact_match` | 1,319 items |
| `arc_challenge_chat` | `1.0` | `87473216b5b01d96ac850d16f383bc2892b239a2ac6fc878f5d2ba3779e010fc` | **0** (set in the task YAML) | **100** (its own, wins over `--model_args`) | `["\n\n", ".", "<|im_end|>"]` | `remove_whitespace` / `exact_match,remove_whitespace` | 1,172 items |
| `ifeval` | `4.0` | `7f2cb49030874196473321cff6a485e78cbbee395a3e940c71321d830a21528d` | **0** (set in the task YAML) | **1,280** (its own, wins over `--model_args`) | `["<|im_end|>"]` | none / `prompt_level_strict_acc` (+3) | 541 prompts |

Three of these four universes and the MMLU geometry were re-derived from the spike's own output
rather than quoted, and they agree with `§3.3`: 1,319 / 1,172 / 541 confirmed, and the 57 MMLU
subject sizes **sum to 14,042**.

### 6.2 The `--limit` trap, now measured instead of feared

`§3.3` warns that `--limit N` means N **per subtask** on a grouped task, and that the flag therefore
multiplies by 57 on MMLU. The spike's `mmlu_generative` run at `--limit 2` recorded:

- 57 subject rows, **each** with `"original"` = the subject's own size and `"effective"` = 2;
- four category groups (`mmlu_generative::stem` …) and one group row, each with `sample_len` = the
  sum of its members' items;
- `mmlu_generative::stem` = 38, `::other` = 26, `::social sciences` = 24, `::humanities` = 26, and
  the group row = **114** — i.e. 57 × 2, not 2.

So the arithmetic of the trap is now witnessed. At `--limit 250` this group would have issued
**10,219 requests**, not 250: 16 subjects are larger than 250 and contribute 250 each (4,000 items),
while the other **41 subjects are smaller than 250 and contribute their entire sets** (6,219 items).
The design's "well over twelve thousand" was the right order and slightly high — the exact figure is
derived here by summing `min(250, size)` over the 57 recorded subject sizes. The design's item-count
audit (`§4.5`) is the control, and this is the run that proves it is load-bearing: a 40× unintended
sample is invisible in a score and visible in `n-samples.effective`.

**The smallest subject is 100 items** (`mmlu_abstract_algebra_generative`, `mmlu_college_chemistry_generative`,
`mmlu_college_computer_science_generative`, `mmlu_college_mathematics_generative`,
`mmlu_computer_security_generative`, `mmlu_business_ethics_generative`, `mmlu_global_facts_generative`,
`mmlu_medical_genetics_generative`, `mmlu_us_foreign_policy_generative`,
`mmlu_high_school_computer_science_generative`), and the largest is 1,534
(`mmlu_professional_law_generative`). `§3.3`'s conditional — "if any subject were smaller than 40
that subject contributes its whole set" — **does not fire**: **zero** subjects are smaller than 40,
so the 40-items-per-subject budget (2,280 items) is available in full.

### 6.3 Where the caps actually come from, and the one that bites

`max_gen_toks` in `--model_args` sets the **model-level default** (`TemplateAPI.max_gen_toks`, whose
own class default is 256). A task that declares `generation_kwargs.max_gen_toks` in its own YAML
overrides it at request time, because the payload builder pops the task's value first and falls back
to the model default only if it is absent. The resolved configs record which happened:

| task | what was passed | what ran | proof |
|---|---|---|---|
| `arc_challenge_chat` | `max_gen_toks=1024` (scratch run) | **100** | resolved `generation_kwargs` = `{'max_gen_toks': 100, 'until': ['\n\n', '.'], 'enable_thinking': False}` |
| `ifeval` | `max_gen_toks=1024` | **1280** | resolved `generation_kwargs` = `{'until': [], 'do_sample': False, 'temperature': 0.0, 'max_gen_toks': 1280, 'enable_thinking': False}` |
| `gsm8k` | `max_gen_toks=1024` | 1024 | no task cap; the model default applied |
| `mmlu_generative` | `max_gen_toks=256` or `1024` depending on the run | same as passed | no task cap in the template |

**ARC-Challenge's own 100-token cap is smaller than the 112-token reasoning trace the canary
produced for `"What is 2+2?"`.** With thinking on, that task cannot finish a trace inside its own
cap, which is the guaranteed route into `§4.1`'s signature A/B. With thinking off it generates ~20
characters and the cap is irrelevant — which is the second reason the `enable_thinking=false` pin is
not optional.

Two more harness behaviours worth recording while the source is open, because both are silent:

- **`stop[:4]`.** The chat payload sends at most **four** stop sequences. All four tasks are within
  that (3, 3, 3, 1), so nothing was dropped in this spike. A future task with five `until` entries
  would lose one with no warning anywhere.
- **`handle_stop_sequences` appends the EOS string to `until`** unless it is already present. With
  `eos_string=<|im_end|>` pinned, the merged list is what the table above shows, and the runtime
  receives it as the request's `stop` array — the array whose presence triggers `§3`'s bug.

### 6.4 What the audit did **not** verify

- **Requests served ≠ items sent.** The reconciliation of `§3.4` needs the runtime's request count.
  No runtime log was captured for any spike invocation, so a retried request would be invisible. The
  retry rule is pinned (`max_retries = 3`, `timeout = 300 s`, concurrency 1, and each retry logs
  `Retry attempt N`) and the campaign must capture the runtime log to use it (`§10.3`).
- **Within-process determinism.** `§6.2` step 8 asks for the same item twice in one process. What
  the record *does* contain is better than nothing and worth stating exactly: two independent
  invocations of `gsm8k` at `--limit 2` — the tracked spike-report run at 22:25:38 and the scratch
  run at 22:20:17 — produced **byte-identical completions for both items** (the Janet duck-egg item
  and the blue/white fibre item) and identical `prompt_hash`es. That is the "once in a second block"
  half of the check, at n = 2 items, one task, one cell. It is a real result and it is not a
  determinism measurement.
- **Seed forwarding, in the sense of the value having an effect.** The harness does forward it —
  `_create_payload` puts `"seed": seed` in the body, with `random_seed: 0` in the recorded config —
  and vMLX does read it (`SamplingParams.seed` → `sampling.py`, which builds a seeded MLX key when
  the value is not `None`). At `temperature 0` the decode is greedy and the seed is
  belt-and-braces — which is the honest form of `§3.4`'s "forwarded if the model type forwards it,
  **if it does not, that is declared rather than assumed**". It is forwarded; it is not a control
  the study depends on.

### 6.5 The configuration finding that needs a decision: 0-shot means unscorable

This is the spike's most consequential audit result and it is not a bug in any component. It is an
interaction between three correct things:

1. `§3.6` pins the few-shot count at **each task's own default**;
2. the installed registry's defaults for the generative/chat variants are **0** for
   `mmlu_generative` and **0** for `arc_challenge_chat` (the conventional 5-shot and 25-shot belong
   to configurations the dispatch's endpoint model cannot run — the completion-style variants);
3. both tasks score by matching a **letter** against a filter that does not extract one.

Measured consequences:

| run | items | result | mechanism, from the recorded samples |
|---|---|---|---|
| `mmlu_generative`, 0-shot, thinking off | 114 (57 subjects × limit 2) | **0.00 on every subject, every category, and the group** | the model answers in prose: target `A` ← *"There are currently **10** known human polyomaviruses."*; target `D` ← an AIDS-activism paragraph. No letter, nothing for `get_response` to match |
| `arc_challenge_chat`, 0-shot, thinking off | 2 | **0.00** | item 0: target `C`, model `The best answer is C` — **correct, and failed by `remove_whitespace`**; item 1: target `B`, model answers in prose with no letter at all |
| `mmlu_virology_generative`, **5-shot**, multiturn | 5 | **0.60** | the model emits `C`, `D`, `D`, `B`, `B` (`§5.2`) |

The ARC item 0 case is the sharpest one in the whole spike: a **right answer recorded as wrong**,
because `arc_challenge_chat`'s built-in instruction ("Your response should end with 'The best answer
is [the_answer_letter]'") and its `gen_prefix: The best answer is` put the letter inside a wrapper
that its own `remove_whitespace` filter does not strip. That is confound #17 of the ledger — "a low
score from extraction failure where the model answered" — caught, with the item, the target and the
response on file.

**The decision the campaign needs** (recorded, not taken, here):

- **MMLU**: pass `--num_fewshot 5` explicitly. It is measured working (`§5.1`), it is the
  configuration the vendor's claim is stated in, and the design already carries the escape hatch —
  "the spike records the effective value from the harness's resolved config and **that recorded
  value is the pin**". Recording 5 as the pin is a *choice*, and it must be printed as one, because
  at 1,140–2,280 items a 5-shot prompt also changes the cost model.
- **ARC-Challenge**: the same override is not obviously available, because the chat variant's answer
  format is not a bare letter. The available options are to pass a few-shot count and see whether
  the demonstrations teach the format, to accept an all-zero reading (which the design's P3 would
  then have to interpret as a *collapse* — correctly, and uselessly, since it would be true of every
  format), or to drop the task and record the substitution (`§3.2`'s rule). **This is a
  pre-campaign decision with a cost either way, and it is not mine to take.**

Until it is taken, no ARC-Challenge score from this harness is interpretable, and a MMLU score at
0 shots is a measurement of format compliance.

---

## 7. Generation length: what is known, and the criterion that is not met

`§6.2` step 6 is "measure the generation-length distribution and set the per-task caps at the 99th
percentile", with the exit criterion "caps pinned, truncation rate at the chosen cap < 5 %". **This
was not done, and the honest status is that no recorded artifact contains a per-item generated-token
count.** The reasons are structural, and each is verifiable:

- the endpoint model's `parse_generations` returns only the response **text**
  (`lm_eval/models/openai_completions.py`); `usage` from the vMLX response is never read, so no
  per-item token count reaches any sample record, results JSON or manifest;
- `Tokenized requests are disabled` and `Using tokenizer None` (the tracked invocation's own log),
  so the harness cannot count tokens itself;
- the scratch probes did not capture the runtime's log, which is the one place per-request counts
  exist — vMLX logs them: `logger.debug(f"Request {request_id} finished: {finish_reason},
  prompt={request.num_prompt_tokens}, completion={request.num_output_tokens} tokens")`
  (`vmlx_engine/mllm_scheduler.py:3629`).

What *is* on file about length:

| observation | value | source |
|---|---|---|
| canary, thinking **on**, `max_tokens=256` | **112** completion tokens for a one-character answer | `spike-report.json` → `canary_response.usage.completion_tokens` |
| canary prompt | 18 tokens (the same 18-token prompt the campaign's tasks exceed by two orders of magnitude) | same |
| completion characters, thinking **off**, GSM8K | 257 chars (one item, the Janet item) | tracked `samples_gsm8k_*.jsonl` |
| completion characters, thinking **off**, MMLU 5-shot virology | 1 char (`C`, `D`, …) | `/tmp/spike_mmlu_5shot/…` |
| completion characters, thinking **off**, ARC-C | 20 chars (`The best answer is C`) | `/tmp/spike_arc_nothink/…` |
| completion characters, thinking **off**, IFEval | 1,973 chars (a twelve-line poem) — the longest generation in the spike | `/tmp/spike_ifeval_nothink/…` |
| prompt sizes sent (content characters, exactly) | GSM8K 5-shot: 11 messages / 3,172 chars; MMLU 5-shot: 12 messages / 1,213 chars; ARC-C 0-shot: 2 / 552; IFEval 0-shot: 1 / 304 | the recorded `arguments` in each `--log_samples` file |

**The consequence is not cosmetic.** The truncation-FAIL rule of `§3.5` ("a cell whose truncation
rate exceeds 5 % is a FAIL") cannot be evaluated against caps that were never calibrated, and the
design's own cost model (`§6.1`) assumes a mean generation of ~150 tokens that no measurement
supports. Two things mitigate it and neither replaces it: with `enable_thinking=false` the observed
completions are short (1–1,973 characters), and the caps in force (100–1,280) are generous next to
them. A format under test could behave differently — that is exactly the hypothesis the study
exists to test — so the caps must be set from a measurement, not from this paragraph.

**The cheapest closeout** (a decision for the coordinator, not a spike task): one short calibration
run per task with the runtime launched at `--log-level DEBUG` and its stdout captured, then parse
`completion=N tokens` lines for the 99th percentile. Note that `--log-level DEBUG` is **not** the
pinned start command — `runtimes.Vmlx.start_command` does not pass it, and `scratch/test_stops_debug.py`
shows it accepted — so it is either a declared, temporary calibration condition or a second reason
to keep the probe's log. Either way it belongs in the manifest with the caps it produced.

---

## 8. Cost model and execution budget validation

### 8.1 What was measured, per invocation

`total_evaluation_time_seconds` is the harness's own field. It includes context building, model
setup and saving, so dividing it by items gives an **upper bound** on seconds per item; the
harness's `Requesting API: … it/s` progress line is the request-phase rate and is the better number,
but it was only preserved on disk for the one tracked invocation.

| invocation | task (n-shot) | thinking | items | score | `total_evaluation_time_seconds` | s/item (upper bound) | harness request-phase rate |
|---|---|---|---|---|---|---|---|
| tracked `probe_accuracy_spike.py` | `gsm8k` (5) | off | 2 | 1.00 | 11.02 | 5.51 | **3.37 s/item** (logged) |
| `spike_gsm8k_nothink` | `gsm8k` (5) | off | 2 | 1.00 | 10.69 | 5.35 | 3.27 s/item (console) |
| `spike_mmlu_5shot` | `mmlu_virology_generative` (5) | off | 5 | 0.60 | 8.53 | 1.71 | ~1.9 s/item (console) |
| `spike_mmlu_5shot_singleturn` | `mmlu_virology_generative` (5) | off | 5 | 0.00 | 8.77 | 1.75 | — |
| `spike_mmlu_nothink` | `mmlu_generative` (0) | off | 114 | 0.00 | 135.49 | **1.19** | ~1.0 s/item (console) |
| `spike_arc_nothink` | `arc_challenge_chat` (0) | off | 2 | 0.00 | 5.37 | 2.69 | 0.6 s/item (console, 1.7 it/s) |
| `spike_ifeval_nothink` | `ifeval` (0) | off | 2 | 1.00 | 12.85 | 6.42 | 3.87 s/item (console) |
| `spike_ifeval` | `ifeval` (0) | **on** | 2 | 0.00 | 45.81 | 22.90 | — |

The best-supported per-task rates for the campaign's cost model are therefore the console
request-phase rates, because they exclude startup and because the file-backed upper bounds on
n = 2–5 items are dominated by it: **MMLU ~1.0–1.9, GSM8K ~3.1–3.3, ARC-C ~0.6, IFEval ~3.8 s/item**.

**One arithmetic defect in the tracked record, for the record's sake.**
`probe_accuracy_spike.py`'s `count_of` counts *lines* in the `--log_samples` file, and a task with
two filters writes two lines per item — so the tracked report's `items_scored: 4` is 2 items × 2
filters, and its `seconds_per_item: 3.042` divides a startup-inclusive wall clock by twice the item
count. The harness's own `.json` for the same run says `n-samples.gsm8k.effective = 2`. The two
numbers happen to land near the harness's 3.37 s/item because the divisor error and the startup term
pull in opposite directions; the next reader should use `n-samples.*.effective` (or the harness's
progress line) and never the sample-line count. This is the project's "never report an unreconciled
number" rule applied to the spike's own report file.

### 8.2 The 3,030-item cell, recomputed

| task | items | s/item (low) | s/item (high) | cell time (low) | cell time (high) |
|---|---|---|---|---|---|
| MMLU (57 × 40) | 2,280 | 1.0 | 1.9 | 38.0 min | 72.2 min |
| GSM8K | 250 | 3.1 | 3.3 | 12.9 min | 13.8 min |
| ARC-Challenge | 250 | 0.6 | 0.6 | 2.5 min | 2.5 min |
| IFEval | 250 | 3.8 | 3.8 | 15.8 min | 15.8 min |
| **per cell** | **3,030** | | | **≈1.15 h** | **≈1.74 h** |

The order's summary states **~1.5–2.0 h per cell**, which is the conservative end of this range; the
difference is the startup term (four invocations per cell) plus whatever the MMLU 5-shot prompts do
to the prefill term once they run at 2,280 items instead of 5. Either way the figure is **1.2–2.0 h**
against a campaign total of **65–90 h** assumed at 5–7 h per dense cell.

**Therefore `§3.3`'s downward dial (MMLU 40 → 20 items per subject) is not triggered.** The
condition attached to it — "only on the spike's measured seconds-per-item" — is not met: the measured
rate is 2–5× faster than the design's estimate. The design's estimate was conservative because it
assumed a mean generation of ~150 tokens with thinking on; the switch in `§4` removed that term.

**Three caveats that travel with this table, all of them reasons the campaign should re-measure
rather than quote:**

1. **n is 2–114 items per task, at caps and few-shot counts that are not yet the campaign's**
   (0-shot and 5-shot MMLU are both in this table; ARC ran at its own 100-token cap).
2. **The MMLU term dominates and is the least secure**: 1.19 s/item measured at 0-shot on 114 items
   versus ~1.9 s/item measured on 5 five-shot items. The five-shot prompt is the one the campaign
   will run, and it was measured on five items.
3. **Nothing here was measured under load.** The spike's longest run is 135 s. The thermal
   protections of `§3.7` (cell-major blocks, rotated order, 30 s cooldowns, seconds-per-item drift
   annotation) remain exactly as written, and the spike provides no evidence about them in either
   direction.

### 8.3 What the campaign must still do to make these numbers comparable

The design pins "items issued == items pinned" and "items sent must equal requests served". The
spike got half of that: the item counts are audited from the harness's own output (`§6.2`), and the
request side is open (`§6.4`). The runtime log is the missing artifact, and it is also where per-item
token counts live (`§7`), so capturing it once serves three of `§10`'s gates.

---

## 9. Chat template consistency audit

`§3.6`'s third item: the runtime applies its own server-side template, that template lives in the
artifacts, and two artifacts with different templates are two different prompts. Method used here:
find every file in each snapshot whose name contains `chat_template`, hash the template **string**
(whether it sits inline in `tokenizer_config.json` or in the sidecar file), and compare.

### 9.1 Dense `Qwen3.5-4B`: clean, five of five identical

| label | repo | where the template lives | template bytes | template `sha256` |
|---|---|---|---|---|
| `jang4s` | `JANGQ-AI/Qwen3.5-4B-JANG_4S` | inline in `tokenizer_config.json` only | 7,756 | `a4aee8afcf2e0711942cf848899be66016f8d14a889ff9ede07bca099c28f715` |
| `stock4bit` | `mlx-community/Qwen3.5-4B-4bit` | `chat_template.jinja` only | 7,756 | `a4aee8afcf2e0711942cf848899be66016f8d14a889ff9ede07bca099c28f715` |
| `oq4` | `RepublicOfKorokke/Qwen3.5-4B-oQ4` | **both**, byte-identical | 7,756 | `a4aee8afcf2e0711942cf848899be66016f8d14a889ff9ede07bca099c28f715` |
| `oq4e` | `uingei/Qwen3.5-4B-oQ4e` | `chat_template.jinja` only | 7,756 | `a4aee8afcf2e0711942cf848899be66016f8d14a889ff9ede07bca099c28f715` |
| `optiq` | `mlx-community/Qwen3.5-4B-OptiQ-4bit` | `chat_template.jinja` only | 7,756 | `a4aee8afcf2e0711942cf848899be66016f8d14a889ff9ede07bca099c28f715` |

**The dense column is clean on this axis**: five artifacts, one template string, one digest, and
`§3.6`'s "identical → the column is clean and the digest of the shared string is recorded" is
satisfied with the digest above.

One correction to the dispatch's phrasing, because it decides whether a per-cell check is needed.
The order records this finding as "5 artifacts have byte-identical `tokenizer_config.json` chat
templates". That is true of the **template string** and not true of where it is stored: only
`jang4s` and `oq4` carry it inline, `oq4` carries it twice, and the other three carry it **only** as
`chat_template.jinja`. A loader that reads only `tokenizer_config.json` would find **no** template
for `stock4bit`, `oq4e` and `optiq` and fall back to its own default — which would turn a clean
column into three prompts and one. vMLX resolves and reads `<model path>/chat_template.jinja`
(`vmlx_engine/server.py:17392`) and lists that filename among the files it attests against the
bundle (`_BUNDLE_ATTESTATION_FILENAMES`, same file), so the digest above is the template the runtime
is positioned to apply. **Not verified by observation**:
the applied template was not captured from a live server, and the tracked results JSON records
`chat_template: ""` because the harness's own field is empty for this endpoint model. `§4.5`'s
pre-flight already requires the template digest per cell; the concrete form of that check is
"resolve the template the way the runtime resolves it, hash the result, and print it in the
manifest".

### 9.2 MoE `LFM2.5-8B-A1B`: five distinct templates, declared

| label | repo | `chat_template.jinja` bytes | template `sha256` |
|---|---|---|---|
| `jang2l` | `JANGQ-AI/LFM2.5-8B-A1B-JANG_2L` | 4,348 | `badd75a82f8b5d735ee23947e2623a0e6e404b35266aee54b04318f39af28301` |
| `stock4bit` | `mlx-community/LFM2.5-8B-A1B-MLX-4bit` | 4,674 | `f434e8c96e6c0a63a022a3ad0a299bb94e58aa90e3c9ebe65034f8e8c6188aa9` |
| `oq4` | `stamsam/LFM2.5-8B-A1B-oQ4` | 4,294 | `46cd92afe7fee81fc1d71c19a140fd74d89e5e971b272230c5444475aa1b0bf9` |
| `oq4e` | `brainworkup/LFM2.5-8B-A1B-oQ4e` | 4,621 | `6d65c8804847ad74eea912dd7eca3dc1cf7a457b53a77f47d841a14121910963` |
| `optiq` | `mlx-community/LFM2.5-8B-A1B-OptiQ-4bit` | 4,815 | `4b8e3c791748d84dd125048b20b4b93781c4286222145c2ad06274b1fe9ad53f` |

**Five templates, five digests, and the difference is not whitespace**: collapsing all runs of
whitespace to single spaces leaves five distinct strings. The MoE column therefore carries a
**declared prompt-composition difference** under `§3.6`, and the design's consequences follow
unchanged — it is printed above every score of that study, and **no column-level claim may be
published from it**. The alternative (normalising the template) is a code change to the runtime's
prompt path and stays out of scope.

Note the asymmetry with the dense column, because it will be read as a format effect unless it is
labelled: on the dense model all five artifacts share one template, so a dense Δ is not a prompt
difference; on the MoE they do not, so a MoE Δ carries one more candidate explanation than the
dense Δ does. The vendor's claim is tested on the MoE (`§1.2` of the design), which makes this the
column where the caveat costs the most.

---

## 10. Exit criteria and readiness for Plan 02-02

### 10.1 What the spike bought

- **A working instrument**, with the endpoint model, the channel, the payload shape, the item record
  and the timing all confirmed against the harness's own files rather than against documentation.
- **A fixed engine.** The string-stop deadlock is diagnosed to a line, patched in both copies, and
  verified byte-identical. Without it the engine is exposed on every request this study issues,
  since the pin itself guarantees a stop list on all of them.
- **The reasoning switch**, priced on two tasks, with its code path named on both sides of the
  boundary, and with its cost to the design stated plainly (`§4.3`).
- **The presentation pin**, priced rather than preferred: `fewshot_as_multiturn: true`.
- **The registry pins**: four task ids, four versions, four task hashes, four effective caps, three
  effective stop lists, one proven `--limit` trap and one proven filter failure.
- **The identity material** for `§3.3`'s item-set proof: `--log_samples` writes `doc_id` **and**
  `doc_hash`, `prompt_hash` and `target_hash` per item, which is a stronger basis than the design's
  "sorted `doc_id` list, otherwise target+prompt" expected. The field set to record in the manifest
  is the four of them.
- **Timing that closes the budget question** in the campaign's favour, with its caveats attached.

### 10.2 What the spike did not verify

- A generation-length distribution, and therefore any calibrated cap (`§7`).
- Items sent versus requests served, and therefore the retry blind spot (`§6.4`).
- Within-process determinism (n = 2 items across two invocations is all there is).
- Cross-runtime anything: one runtime was started, and it was the intended one.
- Any MoE artifact, any second format, any score comparison.
- Whether the runtime honors the seed as a control (`temperature 0` makes it moot).
- The applied chat template, as opposed to the artifact's template string (`§9.1`).
- Nothing about thermal behaviour, contention, or long-run stability: the longest run was 135 s.

### 10.3 Gates before 02-02's first cell

Each of these is one command or one small edit, and each closes a way a cell could produce an
uninterpretable number:

| # | gate | why it is a gate, not a nicety |
|---|---|---|
| 1 | **Hash the vMLX engine file per block** (`shasum -a 256 …/vmlx_engine/mllm_scheduler.py`, expect `9710d2b9…`) and record it in the manifest | the version string is `1.6.59` with and without the `§3` patch; a block that ran against the unpatched file cannot complete |
| 2 | **Calibrate the caps** from a `--log-level DEBUG` capture, per task, and record the 99th percentile | `§6.2` step 6 is unmet; the truncation FAIL rule is unevaluable without it |
| 3 | **Capture the runtime log for every invocation** | closes the reconciliation check *and* carries the per-item token counts *and* records retries (`Retry attempt N`) |
| 4 | **Move scratch output out of `/tmp`** into the campaign directory | the spike's own raw record — samples for ARC, IFEval, MMLU, both `fewshot_as_multiturn` runs — is in `/tmp` and will be swept; `§3.8` requires every item verbatim to be kept |
| 5 | **Decide the MMLU and ARC-Challenge few-shot counts** (`§6.5`), and print the decision with its precision cost | at 0 shots both tasks measure format compliance; on ARC the current build records a correct answer as wrong |
| 6 | **Pin the identity field set** (`doc_id` + `doc_hash` + `prompt_hash` + `target_hash`) and the task-hash check per `(task id, resolved config)` | `§5.3`: the same task id under two presentations carries two different hashes, and the identity check must catch that rather than average it |
| 7 | **Re-run the canary per (runtime, model, artifact) with `max_tokens` ≥ the largest per-task cap**, and record `usage.completion_tokens` beside the caps | `§4.4`: the canary passed at 256 while ARC-Challenge's own cap is 100 |
| 8 | **Confirm the thinking switch on the artifact's own model id before each block** | `§3.5`'s per-cell pin; the switch is a request-body field here, and its absence is invisible in a score |
| 9 | **Print the template digest the runtime resolves** for the column's five artifacts | `§9.1`: the template string is identical across the dense column but its storage is not |

### 10.4 The one-sentence status this document supports

*The instrument is validated and the pins are known; the campaign may start once the caps are
calibrated, the runtime log is captured, and the few-shot question of `§6.5` is decided.*

---

## Appendix A — evidence index

| what | where |
|---|---|
| the spike's structured report: uv and `lm-eval` versions, runtime version, the canary verbatim, the invocation's return code and score, port release | `results/spike-eval/spike-report.json` |
| the tracked invocation's full stdout/stderr, including the merged `model_args`, the `--limit` warning, `Using default fewshot_as_multiturn=True`, the effective `gen_kwargs`, and the request-phase rate | `results/spike-eval/lm_eval_output.txt` |
| the harness's own results JSON for the tracked run: resolved `configs`, `task_hashes`, `n-samples`, `fewshot_as_multiturn`, `git_hash`, `chat_template_sha` | `results/spike-eval/mlx-community__Qwen3.5-4B-4bit/results_2026-09-17T22-25-38.103494.json` |
| the tracked run's per-item record: prompt messages, targets, raw responses, filtered responses, `doc_hash` / `prompt_hash` / `target_hash` | `results/spike-eval/mlx-community__Qwen3.5-4B-4bit/samples_gsm8k_2026-09-17T22-25-38.103494.jsonl` |
| the spike's executable protocol and its offline self-test | `scripts/probe_accuracy_spike.py` (`--self-test`) |
| the working record of the deadlock diagnosis, the stop-sequence probes, the thinking switch and both `fewshot_as_multiturn` runs | `scratch/test_stops*.py`, `scratch/test_stop_varieties.py`, `scratch/test_fixed_stop.py`, `scratch/trace_*.py`, `scratch/diagnose_vmlx_hang.py`, `scratch/test_thinking_off.py`, `scratch/test_gen_kwargs.py`, `scratch/test_mmlu_*.py`, `scratch/test_ifeval_nothink.py`, `scratch/check_qwen_channels.py`, `scratch/test_spike_runs.py` |
| the patched engine and the pre-fix shadowing site | `/Applications/vMLX.app/Contents/Resources/vmlx-engine-source/vmlx_engine/mllm_scheduler.py` (`match_idx` at 3527) and the byte-identical copy under `Contents/Resources/bundled-python/python/lib/python3.12/site-packages/vmlx_engine/` |
| the harness's null-content path, retry policy, stop handling and payload construction | `…/lm_eval/models/api_models.py`, `…/lm_eval/models/openai_completions.py`, `…/lm_eval/models/utils.py` in the uv archive (`archive-v0/C1AjZzuUCa8t3OMR`) |
| the task definitions and defaults | `…/lm_eval/tasks/mmlu/generative/`, `…/gsm8k/gsm8k.yaml`, `…/arc/arc_challenge_chat.yaml`, `…/ifeval/ifeval.yaml` |
| the runtime's acceptance of `enable_thinking` and `seed` | `…/vmlx_engine/api/models.py:300` (`ChatCompletionRequest.enable_thinking`), `…/vmlx_engine/mllm_scheduler.py:2723,3148`, `…/vmlx_engine/sampling.py` |
| the runtime's per-request token-count log line, the only route to a length distribution | `…/vmlx_engine/mllm_scheduler.py:3629` |
| the spike's protocol as designed | `docs/research/2026-09-17-v2-track2-accuracy-study-design.md` `§3.4`, `§3.5`, `§3.6`, `§4.1`, `§4.3`, `§6.1`, `§6.2` |
| the start commands, readiness rule, cache pin, port map | `ohyesmlx/runtimes.py` |

Transient paths, named because they are load-bearing today and gone tomorrow:
`/tmp/spike_arc_nothink/`, `/tmp/spike_gsm8k_nothink/`, `/tmp/spike_ifeval/`,
`/tmp/spike_ifeval_nothink/`, `/tmp/spike_mmlu_5shot/`, `/tmp/spike_mmlu_5shot_singleturn/`,
`/tmp/spike_mmlu_nothink/` — each holding a results JSON plus its `samples_*.jsonl`. Gate 4 of
`§10.3` exists because they should not be there.

## Appendix B — every recorded spike invocation

Local time, 2026-09-17. The window is `[date, mtime]` of the invocation's own results file: the
harness writes its `date` field at the start of evaluation and the file at the end, and the two
agree with `total_evaluation_time_seconds` to within a few seconds on all eight runs. `n` is the
effective item count from the harness's own `n-samples`. The engine patch landed at **22:12**; the
diagnosis probes ran **20:53–22:11**; every scored run below is after 22:17.

| # | window | probe | task | shots | thinking | `n` | score | `total_evaluation_time_seconds` |
|---|---|---|---|---|---|---|---|---|
| — | 22:17:40 script written; **no results file** for the ARC-Challenge or GSM8K legs | `test_spike_runs.py` | `arc_challenge_chat`, `gsm8k` | 0 / 5 | on | — | nothing recorded — the console log was not saved (`§3.1`) | — |
| 1 | 22:18:02 → 22:18:44 | `test_spike_runs.py` | `ifeval` | 0 | on | 2 | 0.00 strict / 0.00 loose | 45.81 |
| 2 | 22:20:04 → 22:20:06 | `test_gen_kwargs.py` | `arc_challenge_chat` | 0 | off | 2 | 0.00 | 5.37 |
| 3 | 22:20:10 → 22:20:17 | `test_gen_kwargs.py` | `gsm8k` | 5 | off | 2 | 1.00 | 10.69 |
| 4 | 22:20:38 → 22:20:47 | `test_ifeval_nothink.py` | `ifeval` | 0 | off | 2 | **1.00 strict / 1.00 loose** | 12.85 |
| 5 | 22:21:08 → 22:23:20 | `test_mmlu_nothink.py` | `mmlu_generative` (group) | 0 | off | 114 | 0.00 on all 57 subjects | 135.49 |
| 6 | 22:23:59 → 22:24:04 | `test_mmlu_5shot.py` | `mmlu_virology_generative` | 5, multiturn | off | 5 | **0.60** | 8.53 |
| 7 | 22:24:26 → 22:24:31 | `test_mmlu_singleturn.py` | `mmlu_virology_generative` | 5, single-turn | off | 5 | **0.00** | 8.77 |
| 8 | 22:25:30 → 22:25:38 | `probe_accuracy_spike.py` (tracked) | `gsm8k` | 5 | off | 2 | 1.00 | 11.02 |

Plus the canary (unknown latency, console-recorded at 1.49 s), the direct-probe stop tests
(`test_stops.py`, `test_stop_varieties.py`, `test_empty_stop.py`, `test_second_req.py`,
`test_vmlx_req.py`, `test_stops_debug.py`), the two channel probes
(`check_qwen_channels.py`, `test_thinking_off.py`) and the four deadlock traces — none of which
scored anything, and all of which wrote their findings to the console.

## Appendix C — number provenance

| this document | value(s) | source |
|---|---|---|
| `§1.1`, `§8.2` cell times and the dial verdict | 1.15–1.74 h per cell | computed here from the per-task rates in `§8.1`; no new measurement |
| `§2.1`, `§2.2` tool and runtime pins | uv 0.11.20, lm-eval 0.4.13, vMLX 1.6.59, offline 0.248 s | `spike-report.json`; the offline check was **re-run 2026-09-18** for this document |
| `§3.2`–`§3.4` the deadlock | source lines, the `-1 → 0` mechanism, `match_idx`, both copies byte-identical, `sha256 9710d2b9…` | read from the installed engine source and hashed **today**; the pre/post behaviour comes from the campaign's own runs |
| `§4.1` the canary | content `"4"`, 112 completion tokens, 18 prompt tokens, channel `content` | `spike-report.json` |
| `§4.3` thinking on/off | IFEval 0.00→1.00, 45.81 s→12.85 s; per-task rates | the results JSONs under `/tmp/spike_*` and `results/spike-eval/` |
| `§5` the presentation pricing | 0.60 vs 0.00 and the five responses of each | the two `samples_*.jsonl` files under `/tmp/spike_mmlu_5shot*` |
| `§6.1` registry table | ids, versions, hashes, caps, stops, filters | the installed task YAMLs in the uv archive and the `configs`/`task_hashes` blocks of the results JSONs |
| `§6.2` the `--limit` trap and the MMLU universe | 57 subjects, 14,042 items, minimum subject 100, group 114 at limit 2 | summed and counted **today** from the `n-samples` block of `/tmp/spike_mmlu_nothink/…/results_*.json` |
| `§7` lengths | 112-token canary, completion characters, prompt characters | `spike-report.json`, the `samples_*.jsonl` files, and the debug line at `mllm_scheduler.py:3629` |
| `§9` template digests | 7,756 B / `a4aee8af…` dense; five MoE digests | hashed **today** from the HuggingFace cache snapshots named in `§2.4` of the design |

**No accuracy number in this document compares two formats.** The scores quoted are single cells
measured for instrumentation reasons; none of them answers a question of the study.
