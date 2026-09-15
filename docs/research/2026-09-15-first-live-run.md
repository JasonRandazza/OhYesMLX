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
