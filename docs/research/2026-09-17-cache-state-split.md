# 06-02: the cold/warm KV split, measured — oq4 at 4096 tokens, five runtimes

Date: 2026-09-17. Ran 2026-09-16 22:47:06–23:35:10 local as ten runs, one per
(runtime, cache state), joined afterwards. One variable moved: the run header pin `cache_state`.
Everything else is held constant by the join guard, field by field.

The question 06-02 exists to answer is what a runtime's prefix/KV reuse is worth on a repeated
long prompt: the same 4,096-token document sent again and again, with reuse pinned off in one
run and on in the other, on the one format all five runtimes serve. The ten cells answer it in
two kinds of way, and the split is not the one the Phase 6 design expected: **two runtimes
collapse to a lookup, and three show nothing at all — for three different, evidenced reasons,
none of which is a broken flag.**

## What ran, and what the sweep can claim

`scripts/run_sweep_cache.sh` walked five runtimes — mlx-lm 0.31.3, oMLX 0.6.4, mlx-optiq 0.5.6,
vMLX 1.6.59, Osaurus 0.25.5 — at `off` then `on`, one cell each: `oq4__<runtime>`, all five
serving the same artifact (`RepublicOfKorokke--Qwen3.5-4B-oQ4`, 3,160,559,814 bytes on disk),
one workload, `prefill`, `max_tokens` 64, one prompt: the same 4,096-token cut of the committed
source the prompt-length sweep used (`achieved` 4,096 by the serving tokenizer, recorded in the
header). Each pair runs `off` first and `on` second, so a pair's warm column is always the later
measurement and any drift inside a pair leans the same way for all five.

Pins every run shares: temperature `0.0`, seed `0`, warmup the plateau rule (two windows of 5
rates, a 3% step between their medians, floor 10, cap 20), `measured` 9 batches, `concurrency`
1, `cooldown_s` 30.0, `prompt_tokens` target 4096 / achieved 4096. `cache_state` is the one pin
they differ on. Each cell is planned for two visits (`VISIT_ROUNDS`), the nine measured requests
splitting 5 and 4.

| runtime | `off` run directory | `on` run directory |
|---|---|---|
| mlx-lm 0.31.3 | `20260917T024706Z-format` | `20260917T025229Z-format` |
| oMLX 0.6.4 | `20260917T025746Z-format` | `20260917T030306Z-format` |
| mlx-optiq 0.5.6 | `20260917T030502Z-format` | `20260917T031101Z-format` |
| vMLX 1.6.59 | `20260917T031704Z-format` | `20260917T032230Z-format` |
| Osaurus 0.25.5 | `20260917T032755Z-format` | `20260917T033334Z-format` |

All ten cells are **PASS**, all ten measured the pinned nine requests, and **no request in any
of the ten failed** — 303 of 303 requests came back (213 warmups and 90 measured), and the
records carry no `error` on any of them. Every warmup window
settled (`warmup_plateau` true), and no visit was lost. The joined render is
`results/sweep-cache/sweep-ttft.md`, produced with
`ohyesmlx sweep --varying cache_state --rank ttft_p50_s`; every number below is recomputed from
the ten `results.jsonl` files, and the p50s reproduce the rendered table to the digit.

The runner's own stdout went to `results/sweep-cache/runner.log`, which is **0 bytes again**:
the per-run logs (`log-<runtime>-<state>.log`) hold each run's leaderboard in full, so nothing
below needed the runner's echo lines.

Two claim limits are structural. The sweep varies the cache pin alone on **one model** — and
Qwen3.5-4B is a hybrid model, which turns out to be the whole of Section "Why three runtimes
show no warm benefit". And the workload is prefill-bound: the published figure is the time to
the first token of a 64-token reply, not a decode or a chat result.

## The headline: off against on, p50 and p90

`ttft_p50_s` and `ttft_p90_s`, seconds, over each cell's nine measured requests. The ratio is
`on / off` for the median; the speed-up is `off / on`. Drift annotations are the leaderboard's
own (`measure.measured_drift`, a decode-rate figure — see the caveats).

| cell | off p50 | off p90 | on p50 | on p90 | on/off | speed-up |
|---|---|---|---|---|---|---|
| `oq4__mlxlm` | 7.825 | 8.016 | 7.845 | 8.393 | 1.003 | 1.00x |
| `oq4__omlx` | 8.487 | 8.540 | **0.487** | 0.499 | 0.057 | **17.44x** |
| `oq4__optiq` | 9.813 | 9.905 | 9.983 | 10.094 | 1.017 | 0.98x |
| `oq4__vmlx` | 8.283 | 8.349 | 8.260 | 8.302 | 0.997 | 1.00x |
| `oq4__osaurus` | 9.401 | 9.466 | **0.404** | 0.411 | 0.043 | **23.29x** |

The three that show nothing do not show a little: mlx-lm's on-cell median is 0.3% above its
off-cell's, vMLX's is 0.3% below, OptiQ's is 1.7% above — and OptiQ's on cell ran *slower* than
its off one while its warmup window was still climbing (drift +0.5%; the off cell reads −1.4%),
so even that 1.7% is a session reading and not a cache effect. Inside each of the six flat
cells (three runtimes, two states) the measured TTFTs span at most 9.4% (and as little as 1.4%),
and the late half's median sits above the early half's on two of them and below it on the other
four — which is the shape of a session, not of a cache.

The two that collapse collapse to a *different kind of number*: 0.487 s and 0.404 s against
their own 8.5 s and 9.4 s single-request prefill, which is 6% and 4% of it. A prefix hit on
this model is not a slightly faster prefill.

One annotation of the sweep's render belongs in this table's reading rather than beside it:
`oq4__mlxlm` on carries drift −6.1% and `oq4__omlx` on +11.5% (early 82.1 tok/s against late
91.6, n=9). Both are *decode-rate* drift over the 64-token tail; neither touches the TTFT this
document orders by. The oMLX one is the visit boundary, not a thermal curve: the nine measured
requests split 5 and 4 across two visits, and visit 2's hits (0.343–0.435 s) are simply faster
than visit 1's (0.487–0.500 s).

## The first request against the rest

The flat-TTFT check the design pinned — is the warm figure a hit or a miss — read off each on
cell's own warmup series. `rest median` is the median of every warmup after a visit's first
request (for the three flat runtimes no visit boundary is visible in the series and it is simply
every warmup after the first); `min/p50` is the fastest warmup over the measured median, the
ratio the 06-01c cache check used (a recorded hit there was 0.11 of its cell's median).

| on cell | warmup #1 (visit 1) | warmup #2 | rest median | min/p50 | measured p50 |
|---|---|---|---|---|---|
| `oq4__mlxlm` | 7.530 | 7.671 | 7.831 | 0.96 | 7.845 |
| `oq4__omlx` | 11.728 | **0.601** | 0.509 | 0.82 | 0.487 |
| `oq4__optiq` | 9.779 | 9.891 | 9.917 | 0.98 | 9.983 |
| `oq4__vmlx` | 7.922 | 8.087 | 8.126 | 0.96 | 8.260 |
| `oq4__osaurus` | 10.208 | **0.382** | 0.405 | 0.82 | 0.404 |

Two readings, and they are different facts:

- **oMLX and Osaurus hit from the second request of each visit.** Their first request is a full
  prompt, and for oMLX it is also where the deferred weight load lands: `first request s` 12.40 s
  on against 12.22 s off, and the off cell's opening request reads 11.567 s TTFT against the on
  cell's 11.728 s. Osaurus's is a plain full prefill — 10.208 s on against 9.498 s off — and its
  second request is already 0.382 s. From there the whole visit is a lookup.
- **The other three never hit, in either visit.** For them #1, #2 and the rest of the series sit
  inside one band (mlx-lm 7.53–8.53, OptiQ 9.78–9.99, vMLX 7.92–8.19) and the band is the off
  cell's own level. mlx-lm's min/p50 of 0.96 and vMLX's 0.96 are warm-window spread; there is no
  request anywhere in their series that resembles a lookup.

The second visit separates the two behaviours further. A visit is a fresh start, and the caches
do not all survive it:

| on cell | visit 2, request #1 | visit 2, rest median | what survives a visit |
|---|---|---|---|
| `oq4__mlxlm` | (no step anywhere in the series) | — | nothing to survive; no hit either visit |
| `oq4__omlx` | **11.619** | 0.484 | nothing: new process, new per-run scratch, `scanned=0` |
| `oq4__optiq` | (no step anywhere in the series) | — | nothing to survive |
| `oq4__vmlx` | (no step anywhere in the series) | — | nothing to survive |
| `oq4__osaurus` | **1.418** | 0.401 | something does; not established which tier (see below) |

oMLX's visit 2 opening at 11.619 s — the full cost again — is the per-run scratch doing its job:
`Runtime.build_command` creates the scratch at start and `stop()` removes it, so the paged SSD
directory is empty at every restart (`SSD cache scan complete: scanned=0, indexed=0`). The warm
column is a within-visit measurement and is presented as one.

## Why three runtimes show no warm benefit

Each of the three was driven into a state its own logs confirm it held. The flags are live; the
caches either store and cannot serve, or are declined by the runtime itself.

### mlx-lm 0.31.3 and OptiQ 0.5.6: the cache holds, and can never serve this model

**The flag was live, in both directions.** Both runtimes run the same server code — OptiQ's venv
bundles mlx-lm 0.31.3 (`mlx_lm/_version.py`) and `optiq serve` hands the arguments it does not
know to it (`optiq/cli.py:2571` `argv_extra = list(ctx.args)` … `:3030-3032`
`sys.argv = ["mlx_lm.server"] + argv_extra; mlx_main()`), which is why its log carries the same
`Prompt Cache:` lines unmodified. The harness passes `--prompt-cache-size 0` for `off` and
`--prompt-cache-size 10` for `on` (`ohyesmlx/runtimes.py:764-788`, one definition shared by both
runtimes). The logs make the flag's effect visible:

| state | mlx-lm log | meaning |
|---|---|---|
| off | `Prompt Cache: 0 sequences, 0.00 GB` before every request (17 + 14 requests) | the size check evicts each entry as it is inserted (`models/cache.py:1728-1732`) — nothing is ever held |
| on | `0 sequences` before request 1, then `1 sequences, 0.19 GB` before every one of the other 29, always `- assistant: 1 / - user: 0 / - system: 0` | a store succeeded, exactly once per cell, and stayed |

OptiQ's two logs read the same way (`0/4108`, `1 sequences`, `assistant: 1`) — it is the same
server, and its own extra `--prompt-cache-bytes` cap of 9.60 GB (`optiq/cli.py:2700-2719`, the
`mlx prompt-cache cap: 9.60 GB` line in its log) never came near eviction at 0.19 GB.

**The stored key is the finished generation, not the prompt.** A request fetches by its prompt
tokens (`server.py:753-756`, `fetch_nearest_cache(current_model_key, prompt)`), but the cache is
inserted when generation finishes, keyed by the tokens the KV cache then holds
(`server.py:901-908`, `insert_cache(current_model_key, r.all_tokens[:], …, cache_type="assistant")`),
and `all_tokens` is defined as exactly that — "the tokens contained in the KV Cache"
(`generate.py:1137-1140` and `:1371-1377`, consumed at `:1443`) — the 4,106 prompt tokens plus
the 64 generated ones. The `assistant: 1 / user: 0` breakdown above says nothing was keyed by
the bare prompt: the segment-boundary insert (`server.py:864-879`) never fired for this prompt,
so the trie holds one sequence, and it is longer than any request.

**A repeat of the same prompt is therefore a prefix of the stored key, and the only branch that
can serve a longer entry is gated on a trim this model cannot do.** `PromptTrie.search`
(`models/cache.py:1578-1620`) returns `exact=None`, `longer=<the stored sequence>`,
`common_prefix=4106` for the second request. `LRUPromptCache.fetch_nearest_cache`
(`models/cache.py:1674-1694`) is the whole decision:

```python
def fetch_nearest_cache(self, model, tokens):
    result = self._trie.search(model, tokens)
    if result.exact is not None:                       # no: the stored key carries 64 extra tokens
        ...
    short_length = len(result.shorter) if result.shorter is not None else 0
    if result.longer is not None and result.common_prefix > short_length:
        cache_entry = self._trie.get(result.model, result.longer)
        if can_trim_prompt_cache(cache_entry.prompt_cache):    # ← the gate, models/cache.py:1683
            ...                                              #    False for this model
    if short_length > 0:                               # nothing: there is no shorter entry
        ...
    return None, tokens                                # so: the whole prompt, every time
```

and the gate is False because of the model. Qwen3.5-4B's cache is built as
`[ArraysCache(size=2) if l.is_linear else KVCache() for l in self.layers]`
(`models/qwen3_5.py:304-305`), and the artifact's `config.json` declares 32 layers with
`full_attention_interval: 4` — 24 linear-attention layers and 8 full-attention ones. `ArraysCache`
(`models/cache.py:594`) defines no `is_trimmable` and no `trim`, so it inherits the base
`is_trimmable() → False` (`models/cache.py:146-147`); `can_trim_prompt_cache` is
`all(c.is_trimmable() for c in cache)` (`models/cache.py:88-92`), and one ArraysCache in the
list makes it False for the whole cache. vMLX's log prints the same layer layout from the same
config (`Runtime cache layout: model_type=qwen3_5 layers=32 layout=0:ArraysCache;…;31:KVCache`).

**The record agrees with the reading.** Every request in both mlx-lm cells and both OptiQ cells
logs `Prompt processing progress: 0/4106` (OptiQ `0/4108`) — and the denominator is the *stripped*
prompt, so a served prefix of N tokens would print `0/(4106−N)`. The total is the full prompt on
every one of them: 31 of 31 requests in mlx-lm's off cell, 30 of 30 in its on cell, and 29 of 29
in each of OptiQ's. Nothing was ever stripped, and every request prefilled its whole prompt. The
TTFTs say the same thing to the tenth of a second a cache hit would not.

**This is not a property of these two runs.** The same thing happened to both runtimes in the
06-01c prompt sweep, whose cells had no cache pin and therefore ran mlx-lm's and OptiQ's own
defaults: `mlxlm-20260916T130416-87425.log` and `optiq-20260916T152526-98257.log` each hold 14
`Prompt Cache: 1 sequences` lines, and that sweep's own cache check put every one of their cells'
minimum TTFT at 0.96–1.00 of its median. The cache has been storing and never serving on this
model since the first time it was measured.

### vMLX 1.6.59: the engine turns the prefix cache back off for a hybrid model

**The flag was live.** The harness passes `--disable-prefix-cache` for `off` and
`--enable-prefix-cache` for `on` (`ohyesmlx/runtimes.py:1089-1091`), and the engine's own output
tells the two states apart without being asked:

- the `on` visits print `Memory-aware cache: 15% of RAM` at startup — a line `cli.py:2723-2733`
  prints only when `enable_prefix_cache` is true (`cli.py:2639`, `:2725`); the `off` visits print
  neither it nor anything else in its place;
- the `on` visits print, once per process:
  `WARNING:vmlx_engine.mllm_scheduler:hybrid prefix cache has no supported backend with paged and block-disk cache disabled; no RAM fallback`
  — and the `off` visits do not.

**The engine then disables prefix storage itself, and says why on every request.** The `on` log
carries one line per request: `cache_outcome=skipped retained_tokens=0 durable=false
detail='hybrid prefix cache has no supported backend with paged and block-disk cache disabled; no
RAM fallback'` — 29 of 29 requests across its two visits, against `cache_outcome=unknown
 detail='cleanup completed; no store outcome recorded'` for all 29 of the off cell's. No request
in either state ever shows `cached_tokens` other than 0 on its `MLLM prefill cache-in` line.

The decision is `vmlx_engine/mllm_scheduler.py:758-770`: when the model is detected hybrid
(Mamba-style state layers alongside full attention — the log's
`VLM hybrid model detected (MambaCache + KVCache layers)` and `Hybrid/path-dependent cache model
detected`), the prefix cache is enabled, the paged cache is off and the block-disk cache is off,
the scheduler records the reason, warns, and sets `self.config.enable_prefix_cache = False`
(`:764-770`); the reason is then stamped on every request from `:3836-3838`. The comment above it
is explicit that this is deliberate — "an unavailable SSD/native route must never silently become
a resident payload cache".

The block-disk tier is off in **both** states, and that is this sweep's single-variable rule, not
an accident: left unset, the engine turns the SSD L2 on by itself whenever continuous batching and
prefix caching are both active and persists it under `~/.cache/vmlx-engine/block-cache/<hash>`,
which survives restarts and could serve another run's prefix (`runtimes.py:1082-1087`, `:1124`).
So under this pin, on this build, **a hybrid model has no prefix-cache backend vMLX will use**:
the only tiers the hybrid path accepts are the two the harness disables. The on cell's flat TTFT
is what that decision looks like from outside — and it is a finding about vMLX 1.6.59's hybrid
path, not a finding about flags.

### The two that do not fall into this section

oMLX and Osaurus hit, and they hit *on the same model and the same prompt* — so the hybrid cache
is not unservable in general. What the other three lack is a hybrid-aware backend: oMLX stores
paged **boundary snapshots** of the ArraysCache state at block granularity and hands them back
whole (below), while mlx-lm's trie can only serve a stored entry by trimming it, and vMLX's
hybrid path has no non-paged tier. Details in the next section.

## The two that hit

### oMLX 0.6.4: paged blocks, in the run's own scratch

`off` keeps the `--no-cache` flag the command already carried (`runtimes.py:939-941`,
`omlx/cli.py:1139-1143`); `on` is its absence, and the log states both states plainly:

| | `off` visit log | `on` visit log |
|---|---|---|
| cache | `oMLX cache disabled (mlx-lm BatchGenerator manages KV internally)`; `Vision feature cache enabled (SSD: disabled)` | `paged SSD-only mode: max_blocks=100000, block_size=4096 tokens`; `paged SSD cache enabled: cache_dir=<scratch>/base/cache` |
| hybrid handling | — | `Enlarging paged cache block_size=256 to 4096 for ArraysCache hybrid model (reduces boundary snapshot overhead)` |
| per request | a full prefill, every measured TTFT 8.43–8.55 s (warmups 8.19–8.54) | `Using boundary cache snapshot …: storing 4096/4170 tokens` once per visit, then `Skipping cache store …: reason=boundary_snapshot_unavailable tokens=4106 block_size=4096 available_boundaries=0` on the visit's other 15 requests (16 requests per visit, both visits) |

That last line is the hit, seen from the store side: the block for this prompt already exists, so
there is nothing new to store. The snapshot takes the first 4,096 tokens of the 4,170 the
request's KV held (its own line: `storing 4096/4170 tokens (skipping trailing partial block …)`);
from request 2 on that block is fetched rather than prefilled, and the TTFT is 0.6 s, then
0.4–0.5 s for the visit.

The cache directory is inside the per-run scratch the runtime is handed
(`Runtime.build_command` → `create_omlx_scratch`), created at start and removed at stop, and both
visit logs show it scanning **0** files at startup. Nothing this run serves can come from an
earlier run's SSD state, and nothing survives into visit 2 — which is why visit 2 opens with the
full 11.6 s again.

### Osaurus 0.25.5: host settings, toggled around the runs and restored

Osaurus has no cache flag in either direction. The state is `cache.prefix.enabled` (and
`cache.blockDisk.enabled`) in `~/.osaurus/config/server-runtime.json`, which the harness refuses
to touch: `Runtime.cache_state_refusal` (`runtimes.py:830-859`) compares the live setting against
the requested state **before** the runtime is started and records `N/A` with the setting and the
value that disagreed when they differ — "a restart is not a way to turn the cache on". Both
Osaurus cells here are PASS with nine measured, so the check passed with the host in the state
each run asked for; a host that disagreed would have produced no number at all.

The runner is what flips the files — `scripts/run_sweep_cache.sh`, byte-exact `cp -p` backups of
both config files, the two cache keys set false for `off`, and `modelIdleResidencyPolicy.seconds`
pinned to **900** in *both* states (the host's 30 would unload the model inside the 30 s
cooldown), re-recording the drift baseline after each toggle so the harness's own start gate
passes. Restoration is verified with `cmp`, not with the drift guard, and the script refuses to
exit 0 unless both files are byte-identical to the copies again — on the normal path and on
INT/TERM/HUP. The runner's exit was 0, which is that check's verdict; what the repository shows
afterwards is what it leaves behind:

- `~/.osaurus/config/server-runtime.json` reads `cache.prefix.enabled: true` and
  `cache.blockDisk.enabled: true`, with the file's **pre-sweep mtimes** intact
  (2026-09-15 17:52:48; `cp -p` restores timestamps as well as bytes) — and
  `server.json` is back to `modelIdleResidencyPolicy.seconds: 30` with its own pre-sweep mtime;
- `config/osaurus-settings-baseline.json` is git-clean (caches `true`, residency `900`) with
  mtime **23:35:15** — five seconds after the last cell's log closed at 23:35:10, which is where
  the runner's restore runs.

The measurement agrees with the toggle: `off` is a full prefill at every request in both visits
(warmups 8.98–9.85 s, measured 9.14–9.51 s, opening request of visit 1 at 9.498 s — no hit
anywhere in the series), `on` is a full prefill once (10.208 s) and then 0.33–0.62 s for the
rest of the visit.

One number in the `on` cell is not yet explained and is left as it stands: **visit 2's first
request is 1.418 s** — a third of a full prefill, but 3.5x the 0.405 s the visit's other requests
take. Each visit starts the runtime again (two visits per cell, and `runtimes._log_path` writes
one log per start: `{name}-{timestamp}-{harness pid}.log`), and the model stays resident across
the cooldown by design, so something carries across that boundary; whether it is the enabled
block-disk tier or state in the resident app is not established by anything read for this
document.

## The off column against the prompt-length sweep's 4096 column

The same cell was measured once before, at the same length, with no cache pin: the 06-01c sweep's
4096 column (`docs/research/2026-09-16-prompt-length-sweep.md`, `results/sweep-prompt/`). Same
artifact, same prompt (achieved 4,096), same pins but the cache pin, three to ten hours earlier
the same day. The two columns SHOULD agree: as the sections above show, the reuse was off or
non-functional in every one of the five prompt-sweep cells too — mlx-lm and OptiQ ran their
default `--prompt-cache-size 10` and their logs hold `1 sequences` with no hit, oMLX ran its
`--no-cache` (`omlx-20260916T151153-79462.log` reads `oMLX cache disabled`), vMLX's log reads
`cache_outcome=unknown` (prefix caching off, the pre-pin command), and Osaurus ran toggled-off as
that sweep's own document records.

| runtime | this sweep, off p50 | 06-01c 4096 p50 | Δ | this off p90 | 06-01c 4096 p90 | Δ |
|---|---|---|---|---|---|---|
| mlx-lm | 7.825 | 7.835 | −0.1% | 8.016 | 8.271 | −3.1% |
| oMLX | 8.487 | 8.141 | +4.2% | 8.540 | 8.198 | +4.2% |
| OptiQ | 9.813 | 9.026 | +8.7% | 9.905 | 9.577 | +3.4% |
| vMLX | 8.283 | 9.020 | −8.2% | 8.349 | 9.139 | −8.7% |
| Osaurus | 9.401 | 8.266 | +13.7% | 9.466 | 8.419 | +12.4% |

Read correctly, this table **corroborates the flat result rather than contradicting it**: two
controlled columns that differ in a pin which provably did nothing on this model (Section "Why
three runtimes show no warm benefit") can only differ by the session, and they differ by less
than 9% on four of the five runtimes — two of those by more than 8%, which is what re-measuring
a 4k prefill cell hours later on the same machine already costs. The one that does not fit is
Osaurus, and it is also the one whose runtime version moved: **0.25.5 here against 0.25.4 in
that sweep**. A version step is the disagreement this project's join guard exists to refuse
(guard 4, `report._check_one_version_per_runtime`), so Osaurus's +13.7% is a number that moved
two things and is not attributed to either.

## What this means for a reader

- **The warm column is a lookup latency, not a prefill rate.** `prefill tok/s` on the two on rows
  (`8,439` for oMLX, `10,174` for Osaurus in their published rows) is `prompt_tokens / TTFT` of a
  *cache fetch* — it is not a prompt-processing throughput and must not be quoted beside the off
  cells' 419–525 tok/s as though the same thing got faster. What genuinely changed is the time to
  first token on a repeated prompt: **17x on oMLX and 23x on Osaurus, on this model at this
  length.**
- **On this model, three of the five runtimes' caches are worth nothing.** A repeated 4,096-token
  prompt costs what a fresh one costs on mlx-lm, OptiQ and vMLX — not because the flag was
  missing, but because mlx-lm's trie cannot serve an entry it may not trim, and vMLX's hybrid
  path has no non-paged tier at all.
- **The reason is architectural, so it is a property of the model-and-runtime pair, and it
  travels.** Qwen3.5-4B is 24 linear-attention layers against 8 attention layers
  (`full_attention_interval: 4`); any runtime whose prefix path is built on trimmable attention
  caches will behave the same way on it, and the identical layer layout shows up in vMLX's log.
  A reader benchmarking a different model — a plain-attention one — should expect different
  answers from mlx-lm and vMLX, and must not carry these three flat results over.
- **The two that work say how.** oMLX answers by never needing to trim: it snapshots the hybrid
  cache at block boundaries and restores whole blocks (its first `on` log line names the hybrid
  case outright). vMLX has that design too — its block-disk/paged tiers — but the harness pins
  those off because one of them persists outside the run.

## Caveats

- **Drift annotations are decode-rate drift, not TTFT drift.** `drift` compares the median decode
  rate of the first half of a cell's measured requests against the second half's. Two cells are
  annotated (`oq4__mlxlm` on −6.1%, `oq4__omlx` on +11.5%); both are computed over the 64-token
  decode tail, neither moved a TTFT, and neither is a floor. The oMLX one is the visit boundary
  as noted above.
- **The two visit windows are not equal work.** The nine measured requests split 5 (visit 1) and
  4 (visit 2), and a visit boundary is visible in a series when the cache does not survive it
  (oMLX on) or carries into it (Osaurus on). Percentiles are taken over the nine together, as
  the leaderboard does.
- **The reported prompt length differs by runtime, and none of them is the header's.** `usage`
  says 4,106 tokens for mlx-lm and Osaurus, 4,108 for OptiQ, 4,101 for vMLX, against the header's
  `achieved` 4,096 from the serving tokenizer. Each runtime applies its own template; the
  comparison here is between a runtime's own two columns, which share a template.
- **Peak memory is lower on the two hit cells, and that is not a cache measurement**: oMLX 6,715
  MB on against 7,173 off, Osaurus 2,515 against 2,896. The cells differ by visit composition
  and by where the sampler's window fell; nothing here isolates the cache's own footprint.
- **One runtime version moved across documents, and only one.** Osaurus 0.25.4 (06-01c) → 0.25.5
  (here). The four other runtimes are at one version across both sweeps.

## Open questions

1. **Would a non-hybrid model show mlx-lm and vMLX hits?** The mechanism established here is
   `ArraysCache` in the cache list (`can_trim_prompt_cache` false) for mlx-lm, and the hybrid
   path having no non-paged backend for vMLX. Both predict a plain-attention model would serve a
   repeated prompt out of the LRU cache at `--prompt-cache-size 10`, and that prediction is
   directly testable on any of the attention-only formats already in the repository. Until it is
   tested, "mlx-lm does not cache" is not a claim this document makes.
2. **Is vMLX's hybrid prefix cache reachable at all under this harness?** Its only accepted
   backends are paged RAM and the block-disk L2, and the L2 is a persisted, machine-global tier
   the harness pins off. Either the tier gets an isolation story (its own directory per run,
   cleared at start) or vMLX stays flat on hybrid models. Not measured here.
3. **Is the warm TTFT a publishable prefill number or a lookup number?** The report prints it in
   the same column as the off cells and derives `prefill tok/s` from it, which reads as a
   prefill rate of 8,439 tok/s for oMLX. A reader who quotes that column without the caveat has a
   number that describes a hash lookup. Whether the warm cell gets its own column, its own
   status, or a note on the row is a decision above this document.
4. **What carries Osaurus's cache across a visit boundary?** Visit 2's first request is 1.418 s
   against a 0.405 s warm median and a ~9.4 s prefill. The block-disk tier is a candidate, the
   resident app is another, and the 35-byte per-visit logs record neither.
5. **Does the hit change with prompt length?** This sweep measured one length. oMLX stores a
   4,096-token block for a 4,106-token prompt and skips the tail; a prompt of several blocks, or
   one shorter than a single 4,096-token block, may store and fetch differently, and the warm
   figure with it. 06-01c's length sweep and this pin have not yet been crossed.
