# mlx-lm 0.31.3 — runtime capability and configuration reference

Written 2026-09-25 from static inspection of the installed package plus the two visit logs of the
ten-turn run (`results/logs/mlxlm-20260925T091430-41697.log`, `…T101438-…`). Nothing here was
established by starting the server; the harness coordinator runs live probes separately, and every
claim carries its evidence inline. Why this document exists: mlx-lm is the measurement control, and
two of its behaviours were being read off its command line and got the answer wrong — the prompt
cache is not a cache that can serve this model, and a pinned seed silently changes the whole
serving path.

**Version.** `_version.py` → `__version__ = "0.31.3"`, the package
`~/.local/share/ohyesmlx/mlx-lm-0.31.3/lib/python3.14/site-packages/mlx_lm/` that
`scripts/run_multiturn.sh` puts on `PATH` (`export PATH="$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH"`).

**Evidence convention.** `$PKG` = the package root above, and a citation relative to it:
`server.py:753` means `$PKG/server.py` line 753; `models/cache.py:1674` means
`$PKG/models/cache.py` line 1674; `generate.py` and `sample_utils.py` are siblings of `server.py`.
The option/MTP/streaming refusals the harness itself enforces are *not* restated here —
they live once, in `ohyesmlx/runtimes.py` (`MlxLm.kv_quant_refusal`, `.mtp_depth_refusal`,
`.stream_experts_refusal`, `prompt_cache_flags`), with their own citations.

---

## 1. Start command and the flag surface the harness uses

`python -m mlx_lm.server --model <artifact dir> --port 8081`, plus `--prompt-cache-size 0|10` when
and only when `cache_state` is taken (`ohyesmlx/runtimes.py:1826-1850`, passed at `:1878`).
`--prompt-cache-size`'s default is **10** (`server.py:1871-1876`), so an unpinned run measures the
default LRU. Other defaults that matter to a cell and are not passed:
`--prefill-step-size 2048` (`server.py:1865-1870`), `--decode-concurrency 32`,
`--prompt-concurrency 8` (`server.py:1853-1863`).

## 2. The pin that decides the serving path — `seed`

The server serves a request through one of two paths, and the gate is:

```python
def _is_batchable(self, args):
    return self.model_provider.is_batchable and args.seed is None
```

(`server.py:685-686`). `model_provider.is_batchable` is true when there is no draft model and every
cache from `make_prompt_cache(model)` has `merge` (`server.py:370-374`) — true for `qwen3_5_moe`
(caches: `ArraysCache.merge`, `models/cache.py:702`; `KVCache.merge`, `:397`). **A request that
carries a seed is therefore never batched**, and every harness run pins one
(`measure.py:165`'s `SEED = 0`, applied per request at `:1073` and sent by `transport.py:181-182`).
Consequences of the sequential path
(`_serve_single`, `server.py:922-1021`):

- one cache insert per request, at the end of generation, keyed by `prompt + every generated token`
  (`server.py:969`, `:1006`, `:1019-1021`), `cache_type="assistant"`;
- **no per-segment snapshots** — the prefix-keyed inserts exist only in the batched path
  (`server.py:864-880`), so a seeded run can never store an entry that a *later, longer* prompt
  could use as a prefix;
- no continuous batching, so `prompt_concurrency`/`decode_concurrency` never apply.

## 3. The prompt cache: what it holds, and what it can serve

Storage is a token trie keyed by whatever token list a caller inserts (`LRUPromptCache`,
`models/cache.py:1623`, insert at `:1696-1737`; a re-insert of the same key replaces it,
`:1712-1717`) — in the sequential path that is `prompt + completion` and nothing else (§2), while
the batched path additionally inserts prompt-prefix snapshots. Fetch is
`fetch_nearest_cache` (`:1674-1694`), and it has exactly three branches:

| branch | condition | needs | serves |
|---|---|---|---|
| `exact` | a stored key equals the whole query | nothing | the whole query (`:1676-1678`) |
| `longer` | a stored key extends past the query's common prefix | **a trimmable cache** — `can_trim_prompt_cache` (`:1683`) = `all(c.is_trimmable() ...)` (`:88-92`) | the query, after trimming the stored cache back to `common_prefix` (`:1681-1688`) |
| `shorter` | a stored key is a prefix of the query | nothing | the query from that prefix on (`:1690-1692`) |

`PromptTrie.search` (`:1578-1620`) supplies all three at once; a prefix entry is only reported when
it ends past token index 0 (`:1602`).

**The trim gate is a property of the model, and this family fails it.** `qwen3_5_moe` (and
`qwen3_5`) build `[ArraysCache(size=2) if l.is_linear else KVCache() for l in self.layers]`
(`models/qwen3_5.py:304-305`, `is_linear` at `:212`, MoE inherits at `qwen3_5_moe.py:6`/`:21`).
`ArraysCache` (`models/cache.py:594-728`) defines no `is_trimmable` and no `trim`, so it inherits
the base `False` (`:146-147`) — and one of them in the list makes the predicate false for all 40
entries. On `Qwen3.6-35B-A3B-oQ4` (40 layers, `full_attention_interval: 4` → 30 linear + 10 full
attention) **the `longer` branch is dead**, whatever the flag says. Recorded, not inferred: the
ten-turn run's cache held ten assistant keys and, on **every** request of both visits, `user: 0 /
system: 0` and a full prefill — see `docs/research/2026-09-25-multiturn-runtime-axis.md`,
"Addendum: why mlx-lm's prompt cache never hit".

A pure-attention artifact has `KVCache` throughout (`is_trimmable` → `True`, `models/cache.py:375`)
and reaches the `longer` branch. **That case is a prediction, not a measurement** (the same open
question `docs/research/2026-09-17-cache-state-split.md` holds).

## 4. How to read its logs

- `Prompt Cache: N sequences, X GB` plus one line per cache type (`_log_cache_stats`,
  `server.py:461-470`). The **per-type breakdown** is the tell: `user`/`system` entries only exist
  if the batched path's segment inserts ran.
- `Prompt processing progress: <processed>/<total>`: `<total>` is the **stripped** prompt
  (`_serve_single` passes `prompt=rest` into `stream_generate`, `server.py:976-980`;
  `generate.py:425-427`), so a served prefix of P tokens shows `0/(N−P)`. The sequential path
  prints `0/N` first (`generate.py:429`), then one chunk leaving the final token (`:430-453`), then
  `N/N` (`:463`). **A batched request never prints a `0/N` line** (it forwards
  `PromptProcessingBatch.Response.progress`, `generate.py:1824-1836`) — so `0/N` is the signature
  that a run never batched, independent of any argument inspection.
- `usage.cached_tokens` carries the served-prefix count over the HTTP API
  (`server.py:1344-1346`). The harness's `Observation` does **not** record it; the log is the only
  artifact that holds the fact.

## 5. Determinism in a cell

`temperature 0.0` is greedy (`make_sampler` returns `argmax` at `temp == 0`,
`sample_utils.py:46-47`) and a request's seed is re-applied per request (`server.py:955-957`), so a
pinned-cell repeat of the same prompt reproduces the completion
byte-for-byte — turn-02 of the ten-turn run's 24 warmups and 9 measured requests hold one distinct
`reasoning_text`. That is what makes a cell's repeats comparable; it is also why repeated requests
collapse onto one cache key rather than filling the LRU.

## 6. What I could not determine

1. **Whether a batchable (seed-less) run would actually hit for this conversation shape.** Source
   says it should: the boundary snapshot's key is a strict prefix of the next turn's prompt, so the
   `shorter` branch would serve it with no trim needed. Not measured.
2. **Whether mlx-lm can be given a prefix-keyed entry any other way.** The segment inserts
   (`server.py:864-880`) and `cache/prompt_cache` files aside, I found no insert path; the absence
   of others is a reading of the file, not a positive constraint.
3. **The exact token split of `…assistant\n<think>\n` in this tokenizer.** The template and the
   added-token table (ids 248068/248069) say the tail is there; no request was tokenized to count
   it.
