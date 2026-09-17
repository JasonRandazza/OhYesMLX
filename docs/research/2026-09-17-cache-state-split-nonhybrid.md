# 06-02, the non-hybrid control — the cold/warm KV split on Llama-3.1-8B-oQ4, five runtimes

Date: 2026-09-17. Ran 12:26:10–13:33:33 local as ten runs, one per (runtime, cache state), joined
afterwards. One variable moved: the run header pin `cache_state`. Everything else is held constant
by the join guard, field by field.

The earlier half of plan 06-02 measured the cold/warm KV split on `Qwen3.5-4B-oQ4` and found the
five runtimes split two ways: oMLX and Osaurus served a repeated 4,096-token prompt as a 0.4–0.5 s
lookup, while mlx-lm, OptiQ and vMLX showed nothing at all — 1.00x, 0.98x, 1.00x
(`docs/research/2026-09-17-cache-state-split.md`). That document named the mechanism
(`ArraysCache` in the model's cache list makes `can_trim_prompt_cache` false, so mlx-lm's prompt
trie cannot serve a longer stored entry; vMLX's hybrid path has no non-paged backend) and left the
obvious prediction open — *would a plain-attention model show the hits?* This is that test, run on
`brainworkup/Llama-3.1-8B-oQ4`, whose 32 layers are all standard `KVCache`.

**Every one of the five runtimes now hits**, and the three that showed nothing on the hybrid model
are among the fastest: mlx-lm 19.112 s → **0.136 s** (140.0x) and OptiQ 19.637 s → **0.138 s**
(141.8x). vMLX, which turned its own prefix cache off for the hybrid model, stores and serves here
without any change to the harness's flags. The flat result was a property of the model-and-runtime
pair, exactly as that document predicted, and not of these runtimes' cache implementations.

## What ran, and what the sweep can claim

`scripts/run_sweep_cache_nonhybrid.sh` walked five runtimes — mlx-lm 0.31.3, oMLX 0.6.4,
mlx-optiq 0.5.6, vMLX 1.6.59, Osaurus 0.25.6 — at `off` then `on`, one cell each:
`oq4__<runtime>`, all five serving the same artifact (`brainworkup/Llama-3.1-8B-oQ4`, snapshot
`a041336af01fe59ffe17c762d4c970564dcabc53`, 4,726,926,473 bytes on disk — every row's
`disk_bytes`), one workload, `prefill`, `max_tokens` 64, one prompt: a length-cut of the committed
source the prompt-length sweep used, cut for 4,096 tokens **by the serving tokenizer**
(`achieved` 4089 in the header). Each pair runs `off` first and `on` second, so a pair's warm
column is always the later measurement and any drift inside a pair leans the same way for all
five.

Pins every run shares: temperature `0.0`, seed `0`, warmup the plateau rule (two windows of 5
rates, a 3% step between their medians, floor 10, cap 20), `measured` 9 batches, `concurrency` 1,
`cooldown_s` 30.0, `prompt_tokens` target 4096 / achieved 4089. `cache_state` is the one pin they
differ on. Each cell is planned for two visits (`VISIT_ROUNDS`), the nine measured requests
splitting 5 and 4.

| runtime | `off` run directory | `on` run directory |
|---|---|---|
| mlx-lm 0.31.3 | `20260917T162610Z-format` | `20260917T163922Z-format` |
| oMLX 0.6.4 | `20260917T164142Z-format` | `20260917T165226Z-format` |
| mlx-optiq 0.5.6 | `20260917T165500Z-format` | `20260917T170554Z-format` |
| vMLX 1.6.59 | `20260917T170825Z-format` | `20260917T171756Z-format` |
| Osaurus 0.25.6 | `20260917T172032Z-format` | `20260917T173114Z-format` |

All ten cells are **PASS**, all ten measured the pinned nine requests, and **no request in any of
the ten failed**: 308 of 308 requests came back (218 warmups and 90 measured) and no record
carries an `error`. Every warmup window closed — nine of the ten on the plateau rule, the tenth
(mlx-lm `off`) at the cap, which its row records as `warmup_plateau: false` and Section "Caveats"
reads. No visit was lost. The joined renders are `results/sweep-cache-nonhybrid/sweep-ttft.md`
(ordered by `ttft_p50_s`) and `sweep-decode.md` (ordered by `decode_tps`); every number below is
recomputed from the ten `results.jsonl` files, and the p50s reproduce the rendered table to the
digit. The runner's own stdout is `results/sweep-cache-nonhybrid/runner.log`, which also carries
the Osaurus toggle and restore lines and ends `SWEEPDONE 13:33:39` with the script's exit 0.

Ratios below are computed from the records' full-precision p50s. The same quotients taken from the
rendered three-decimal columns are 140.5x (mlx-lm), 36.9x (oMLX), 142.3x (OptiQ), 39.2x (vMLX) and
25.3x (Osaurus), so a reader comparing this table against `sweep-ttft.md` finds the identical
figure inside the rounding of the columns that feed it.

Two claim limits are structural. The sweep varies the cache pin alone on **one model**, and that
model is the control for a question about a different one: what it establishes is that the earlier
flat result was the hybrid artifact's doing, not a general statement about any of the five
runtimes. And the workload is prefill-bound: the published figure is the time to the first token
of a 64-token reply, not a decode or a chat result.

## The headline: off against on, p50 and p90

`ttft_p50_s` and `ttft_p90_s`, seconds, over each cell's nine measured requests. The ratio is
`on / off` for the median; the speed-up is `off / on`. Drift annotations are the leaderboard's own
(`measure.measured_drift`, a decode-rate figure — see the caveats).

| cell | off p50 | off p90 | on p50 | on p90 | on/off | speed-up |
|---|---|---|---|---|---|---|
| `oq4__mlxlm` | 19.112 | 19.364 | **0.136** | 0.141 | 0.0071 | **140.0x** |
| `oq4__omlx` | 19.495 | 19.626 | **0.529** | 0.533 | 0.0271 | **36.8x** |
| `oq4__optiq` | 19.637 | 19.908 | **0.138** | 0.144 | 0.0071 | **141.8x** |
| `oq4__vmlx` | 16.440 | 16.695 | **0.419** | 0.429 | 0.0255 | **39.3x** |
| `oq4__osaurus` | 17.641 | 17.852 | **0.697** | 0.725 | 0.0395 | **25.3x** |

Nothing is flat. The slowest warm median (Osaurus, 0.697 s) is 4% of its own cold prefill, and the
fastest (mlx-lm, 0.136 s) is 0.7% of it. p90 tracks p50 inside every cell — the widest spread
between the two is 4.1% (Osaurus `on`, 0.725 against 0.697) and the narrowest 0.7% (oMLX `off`) —
so the warm column is a steady state and not a distribution with a long tail. p99 is
0.143 / 0.537 / 0.145 / 0.430 / 0.726 s on the `on` cells, between 1.5% and 4.5% above each cell's
own median.

The off column spreads 16.440–19.637 s across the five runtimes on the same prompt and the same
weights: 250.8 prefill tok/s for vMLX against 210.0 for OptiQ, a 19% band that is the runtimes'
prompt processing and has nothing to do with the cache. The warm column spreads differently —
**five-fold**, from 0.136 s to 0.697 s — and that spread is the finding Section "Which lookups are
fastest" reads.

## The first request against the rest

The check the design pinned — is the warm figure a hit or a miss — read off each `on` cell's own
warmup series and the server logs behind it. Each visit starts its runtime once, and the harness's
warmup rule (two windows of 5, 3% step, cap 20) runs per visit; replaying that rule over the
recorded per-request decode rates splits the series 10 + 10 warmups for the four 20-warmup cells
and 14 + 11 for Osaurus's 25, which is what the record holds.

| on cell | visit 1, request #1 | visit 1, rest median | visit 2, request #1 | visit 2, rest median | measured p50 |
|---|---|---|---|---|---|
| `oq4__mlxlm` | 16.569 | 0.137 | **15.991** | 0.133 | 0.136 |
| `oq4__omlx` | 21.351 | 0.544 | **20.732** | 0.527 | 0.529 |
| `oq4__optiq` | 20.489 | 0.140 | **20.250** | 0.144 | 0.138 |
| `oq4__vmlx` | 16.046 | 0.426 | **15.414** | 0.416 | 0.419 |
| `oq4__osaurus` | 18.533 | 0.702 | **1.503** | 0.689 | 0.697 |

Four things follow, and the logs say them one request at a time:

- **The first request of every visit is a full prefill.** mlx-lm's `on` logs hold 15 requests in
  visit 1 (10 warmups + 5 measured) and 14 in visit 2; of those, exactly one each — the opening
  request — logs `Prompt processing progress: 0/4123`, the whole prompt, and each of the other 27
  logs `0/1` (log names in the Appendix). OptiQ's two logs read the same: one `0/4123` apiece,
  against 14 and 13 `0/1` lines.
- **Request #2 is already a lookup**, and it stays one for the rest of the visit. mlx-lm's warmup
  #2 is 0.115 s against its #1 of 16.569 s; OptiQ's is 0.111 s; vMLX's 0.497 s; oMLX's 0.800 s;
  Osaurus's 0.606 s.
- **The cache does not survive a visit.** A visit is a fresh process, and each one pays the full
  prefill again at its head — 15.991 / 20.732 / 20.250 / 15.414 s for the four whose boundaries the
  series shows plainly. The warm column is a within-visit measurement, and it is presented as one.
- **vMLX stores and serves, and says so.** `Stored cache for request … (4118 cache-key tokens from
  4119 prompt tokens, KV truncated to 4118)` fifteen times in visit 1, and `Request …: cache hit,
  4118 tokens cached, 5 remaining to process` fourteen times; visit 2 is 14 stores and 13 hits.
  The engine's startup line `Memory-aware cache enabled: limit=4822.3MB` and its
  `MemoryAwarePrefixCache initialized: max_memory=4822.3MB, max_entries=1000, ttl=disabled` are the
  tier that serves them.

Osaurus is the one cell whose visit-2 opener is not a full prefill: **1.503 s** against a 0.689 s
rest median and an 18.5 s full prefill. That is 2.2x the visit's steady hit and 8% of a prefill —
and it is the *second* time this exact shape has appeared, the first being 1.418 s at the head of
visit 2 in the hybrid sweep (`2026-09-17-cache-state-split.md`, "the two that hit"). Two documents,
two models, the same runtime and the same boundary: something carries a partial prefix across an
Osaurus visit and neither document establishes what. It is left in the open questions again rather
than attributed.

The `off` column has no step anywhere, in any cell:

| off cell | warmup #1 | rest median | full band | first prefill logged as |
|---|---|---|---|---|
| `oq4__mlxlm` | 14.049 | 17.043 | 14.049–19.225 | `0/4123` on 25 of 25 requests (visit 1) and 14 of 14 (visit 2) |
| `oq4__omlx` | 20.628 | 18.881 | 18.563–20.628 | `oMLX cache disabled` in both visits |
| `oq4__optiq` | 19.116 | 19.046 | 18.643–20.154 | `0/4123` on 15 of 15 and 14 of 14 |
| `oq4__vmlx` | 15.453 | 15.914 | 15.453–16.186 | `cache_outcome=unknown` on every request, no `cache hit` line in either log |
| `oq4__osaurus` | 17.887 | 16.911 | 16.212–17.887 | host toggled off (below) |

mlx-lm's `off` cell is the exception in shape rather than in kind: its band is 5.2 s wide because
its warmups climbed steadily (14.049 → 19.225 s across 20 requests) and the window ran to the cap
without settling. Its own row records it (`warmup_plateau: false`, drift +14.5%), and the caveats
below price it.

## The hybrid model against the non-hybrid one

The two sweeps differ in one thing — the artifact — and hold the harness, the flags, the prompt
target (4,096 tokens by the serving tokenizer), the workload, the warmup rule, the cooldown and the
visit plan identical. The `on`/`off` speed-up is therefore read side by side:

| runtime | Qwen3.5-4B-oQ4 (hybrid): off → on p50, speed-up | Llama-3.1-8B-oQ4 (plain attention): off → on p50, speed-up |
|---|---|---|
| mlx-lm | 7.825 → 7.845, **1.00x** | 19.112 → **0.136**, **140.0x** |
| oMLX | 8.487 → 0.487, 17.44x | 19.495 → 0.529, 36.8x |
| OptiQ | 9.813 → 9.983, **0.98x** | 19.637 → **0.138**, **141.8x** |
| vMLX | 8.283 → 8.260, **1.00x** | 16.440 → 0.419, **39.3x** |
| Osaurus | 9.401 → 0.404, 23.29x | 17.641 → 0.697, 25.3x |

The hybrid numbers are that document's own table; the non-hybrid column is this one's. The `off`
columns differ too — 7.8–9.8 s against 16.4–19.6 s — and that difference is the artifact (a 3.16 GB
hybrid 4B against a 4.73 GB dense 8B), not a cache. Each sweep used the same committed document and
the same closing question, cut to the same target length, but not to the same bytes: the two
serving tokenizers reach the cut at different points (`achieved` 4096 against 4089), and every
comparison in this document is between a runtime's own two columns, which share one template and
one tokenizer.

### Why the three flat cells were flat, and what changed

The hypothesis to test was specific, and it survives contact: **the flat result came from the
model's cache list, not from a cache that was broken, missing or mis-flagged.**

**The flag was live in both sweeps, in both directions.** The harness passes
`--prompt-cache-size 0` for `off` and `--prompt-cache-size 10` for `on` from one definition shared
by mlx-lm and OptiQ (`ohyesmlx/runtimes.py:764-788`), and the server's own output states the
state without being asked. In this sweep, mlx-lm's `off` logs carry `Prompt Cache: 0 sequences,
0.00 GB` before every one of their 39 requests, so nothing was ever held; its `on` logs carry
`0 sequences` before the opening request of each visit and `1 sequences, 0.57 GB` before every
other one. OptiQ's logs read the same way under its own extra `mlx prompt-cache cap: 9.60 GB`
line. That is the identical flag, on the identical server code, that produced `1 sequences` and no
hit at all on Qwen3.5-4B.

**The gate the earlier document named is the gate that opened.** On the hybrid model
`can_trim_prompt_cache` was false for the whole cache — `ArraysCache` defines no `trim`, one
`ArraysCache` in the list makes the trie's only branch for a longer entry unreachable
(`models/cache.py:1683`) — and every request logged `Prompt processing progress: 0/4106`, the
whole prompt. Here the same line reads **`0/1`**: the server fetched its stored 4,122-token
sequence, trimmed it to the prompt's prefix, and had one token left to process. The measurement
agrees to the tenth of a second a full prefill would not (0.136 s against 19.112 s).

**The layer layouts are in the runtimes' own logs.** vMLX prints
`Runtime cache layout: model_type=… layers=32 layout=0:KVCache;…;31:KVCache` for Llama where it
printed `0:ArraysCache;…;31:KVCache` for Qwen3.5-4B; oMLX prints
`Model info set: 32 layers (32 KVCache), 8 KV heads, 32 Q heads, 128 head_dim` and leaves its paged
block size at **256 tokens**, where the hybrid run logged `Enlarging paged cache block_size=256 to
4096 for ArraysCache hybrid model (reduces boundary snapshot overhead)`. Same five runtimes, same
config reading code, two layouts — and the layouts are the variable.

**vMLX's flat cell was the engine's own decision, and it reverses without a harness change.** On
the hybrid model its `on` visits warned `hybrid prefix cache has no supported backend with paged
and block-disk cache disabled; no RAM fallback` and stamped `cache_outcome=skipped
retained_tokens=0` on all 29 requests. Here, under the same pins — the block-disk L2 is disabled
in *both* states (`ohyesmlx/runtimes.py:1082-1091`, `--disable-block-disk-cache`) — it prints
`Memory-aware cache enabled`, stores 4,118 tokens per request and answers `cache hit` on 27 of 29.
Same build, same flags, different model: the RAM tier exists for `family=llama` and not for the
hybrid path.

**And the two that did hit on the hybrid model were not the ceiling.** oMLX and Osaurus hit there
by designs that never need to trim — paged boundary snapshots, and whatever Osaurus keeps — which
is why the hybrid document's summary was "a property of the model-and-runtime pair". This sweep
puts the three that could not hit there at the *top* of its own table.

### Which lookups are fastest

Given a trimmable cache, the ranking inverts against the hybrid sweep's:

| runtime | warm p50 | what serves the prefix | where it lives |
|---|---|---|---|
| mlx-lm | **0.136 s** | the trie's stored sequence, trimmed to the prefix (`PromptTrie.search` → `can_trim_prompt_cache` → `cache.trim`) | in-process KV, `1 sequences, 0.57 GB` |
| OptiQ | **0.138 s** | the same code — `optiq serve` forwards unknown flags to the mlx-lm server in its venv | in-process KV, same `Prompt Cache:` lines |
| vMLX | 0.419 s | `MemoryAwarePrefixCache`, `limit=4822.3MB` | in-RAM mirror of the native cache (`retained_tokens=4118`) |
| oMLX | 0.529 s | `BlockAwarePrefixCache` over `PagedSSDCacheManager` | the run's own scratch, blocks of **256** tokens |
| Osaurus | 0.697 s | host-managed; its 35-byte logs record no tier | not established |

The two that store the prefix as an in-process KV serve it in ~136–138 ms with no serialization
step; the three with a tier behind them pay 0.42–0.70 s for the same 4,000-token prefix. oMLX's
figure is the one with a visible cause: its blocks are 256 tokens here, where the hybrid run logged
the engine enlarging them to 4,096 "for ArraysCache hybrid model (reduces boundary snapshot
overhead)", so the same prompt is assembled from ~16 paged blocks out of its own SSD directory.
That is a plausible account of the gap between 0.529 and 0.419 s; it is not settled by anything in
this record, and the ranking above is a measurement rather than an explanation.

## Decode throughput and ITL

The published decode figures, and the same cells' aggregate and prefill columns, from the metric
cards (all 64 completion tokens per request, n=9):

| cell | decode tok/s off → on | ITL s off → on | aggregate tok/s off → on | prefill tok/s off → on |
|---|---|---|---|---|
| `oq4__mlxlm` | 36.3 → 32.8 | 0.0280 → 0.0310 | 3.2 → 31.1 | 215.7 → 30,210.0 |
| `oq4__omlx` | 46.3 → 36.7 | 0.0219 → 0.0277 | 3.1 → 28.5 | 211.5 → 7,792.3 |
| `oq4__optiq` | 41.6 → 32.7 | 0.0244 → 0.0310 | 3.0 → 30.6 | 210.0 → 29,773.4 |
| `oq4__vmlx` | 38.2 → 32.5 | 0.0266 → 0.0312 | 3.5 → 27.1 | 250.8 → 9,850.0 |
| `oq4__osaurus` | 46.0 → 36.1 | 0.0221 → 0.0282 | 3.4 → 25.3 | 233.7 → 5,917.1 |

**The prefill column on the `on` rows is not a prefill rate.** It is `prompt_tokens / TTFT` of a
*cache fetch* — 30,210 tok/s for mlx-lm is 4,123 tokens divided by a 0.136 s lookup, and it must
not be quoted beside the `off` rows' 210–251 tok/s as though the same work got faster. The hybrid
document raised this for the two runtimes that hit there; here every row of the column has it.
The number that genuinely changed on the same nine requests is **aggregate throughput**, which
includes the prefill each cell paid: ≈3.0–3.5 tok/s cold against ≈25.3–31.1 tok/s warm, a 7.4x to
10.2x rise on the same work with the 19.5 s prefill removed.

**Decode is lower in the `on` column of every runtime**, by 10% (mlx-lm, 32.8 against 36.3) to 23%
(Osaurus, 36.1 against 46.0), and it is not a property of the measured window. The warmup rate
series — the same per-request decode rate, taken before any measured request, over the same cells —
agrees with the measured window cell by cell: mlx-lm 38.1 → 33.6 tok/s (a −11.8% gap in warmup
against −9.6% measured), oMLX 47.4 → 37.6 (−20.6% / −20.7%), OptiQ 42.9 → 32.9 (−23.3% / −21.3%),
vMLX 39.1 → 33.3 (−14.9% / −14.8%), Osaurus 47.5 → 36.0 (−24.3% / −21.6%). The gap is the cell's,
not the window's.

ITL carries that difference and nothing of its own. It is `span / (tokens − 1)` while decode tok/s
is `tokens / span`, so the two are reciprocal by construction; ITL × decode tok/s lands 1.4–1.8%
above 1.0 on all ten cells, and 64/63 = 1.0159 is exactly the gap between a rate over 64 tokens and
a mean interval over 63. So the column is stable in both states — 22–31 ms per token across the ten
cells — and its difference is the decode difference.

What the gap is *not* established to be is a cache effect. In the `off` cells each decode window
opens immediately after a 4,123-token prefill burst; in the `on` cells it opens after a lookup.
That is a real difference between the two columns and the obvious candidate, but this sweep did not
isolate it and none of the numbers above is attributed to the cache.

## Memory and footprint

`peak_mb` is Apple's `phys_footprint` sampled at 1 Hz through the workload's own window in each
visit (one workload per cell here, so the window is the visit); the published figure is the higher
of the cell's two visits (`measure._highest_peak`).

| cell | peak MB off | peak MB on | Δ |
|---|---|---|---|
| `oq4__mlxlm` | 6,271 | 6,267 | −4 |
| `oq4__omlx` | 6,357 | 6,336 | −21 |
| `oq4__optiq` | 8,949 | 8,939 | −10 |
| `oq4__vmlx` | 6,385 | **7,520** | **+1,135** |
| `oq4__osaurus` | 3,726 | 3,778 | +52 |

**vMLX is the one cell whose footprint moved**, by 1,135 MB (+1.11 GB decimal), and it is the one
runtime that says what it allocated: `Memory-aware cache: 15% of RAM`,
`MemoryAwarePrefixCache initialized: max_memory=4822.3MB, max_entries=1000, ttl=disabled`, holding
`retained_tokens=4118` per request. For scale, a 4,118-token KV at this model's geometry — 32
layers × 8 KV heads × 128 head_dim × 2 (K and V) × 2 bytes, the geometry oMLX's own log prints —
is 539.8 MB by arithmetic, so the retained block is about half the sampled difference and the
fetch path holds the rest transiently. Both halves are the runtime's own RAM tier; neither is a
model's.

The other four move by less than 0.6%. mlx-lm is the instructive one: its cache *reports* holding
`1 sequences, 0.57 GB`, and its sampled peak does not move — the sampled peak is set by the
visit's transient prefill allocations, which both states pay, so `peak_mb` is **not** a cache
footprint. The samplers' vmmap cross-check (`memory_split`) agrees in direction for vMLX — 6,451.2
MB against 7,884.8 MB — but it cannot arbitrate a half-gigabyte entry: every one of the ten cells'
vmmap figures is an exact multiple of 102.4 MB, because `sample.parse_vmmap_summary` reads vmmap's
own `G` column, which displays one decimal place. That is why mlx-lm's cross-check reads 6,246.4 MB
in *both* states while its cache reports 0.57 GB. Osaurus's 3.7 GB against mlx-lm's 6.3 GB on the
same 4.73 GB of weights is the `phys_footprint` accounting difference already documented for this
runtime (`docs/research/2026-09-16-footprint-is-not-one-quantity.md`); no cross-runtime memory
comparison is made here, and none is available from these rows.

## Host isolation and integrity

Four mechanisms, and what each one left behind:

**Osaurus: the state is a host file, toggled around the runs and restored byte-exact.** The harness
will not touch it — `Runtime.cache_state_refusal` (`ohyesmlx/runtimes.py:830-857`) compares the live
`cache.prefix.enabled` against the requested state *before* the runtime starts and records `N/A`
with the disagreeing value when they differ, because "a restart is not a way to turn the cache on".
Both Osaurus cells are PASS with nine measured, so the host held the state each cell claims: both
cache keys false for `off`, the host's own files for `on`. The runner did the toggling
(`scripts/run_sweep_cache_nonhybrid.sh`): `cp -p` backups of `~/.osaurus/config/server-runtime.json`
and `server.json`, `cache.prefix.enabled` and `cache.blockDisk.enabled` set false for `off`,
`modelIdleResidencyPolicy.seconds` pinned to **900** in *both* states (the host's 30 would unload
the model inside the 30 s cooldown), the drift baseline re-recorded so the harness's own start gate
passes, and restoration verified with `cmp -s` against the byte-exact copies — on the normal path
and on INT/TERM/HUP. `runner.log` records `osaurus settings restored byte-exact (cmp)` and the
runner exited 0, which is that check's verdict. Independently of the runner's log:

- `~/.osaurus/config/server-runtime.json` reads `cache.prefix.enabled: true` and
  `cache.blockDisk.enabled: true` with its **pre-sweep mtime** (2026-09-15 17:52:48; `cp -p`
  restores timestamps as well as bytes), two days before this sweep;
- `server.json` is back to `modelIdleResidencyPolicy.seconds: 30` with its own pre-sweep mtime
  (2026-09-16 20:44:21);
- `config/osaurus-settings-baseline.json` is git-clean (`git status --short config/` is empty)
  with the caches `true` and residency `900`.

**oMLX: the cache cannot escape the run.** Every start gets a fresh scratch directory
(`create_omlx_scratch` → `/private/var/folders/…/T/ohyesmlx-omlx-<8 chars>`, passed as
`--base-path` with a per-run model catalog), and the SSD cache directory resolves inside it. Both
`on` visits' logs name it and both scan **zero** files:
`SSD cache scan complete: scanned=0, indexed=0, errors=0, total_size=0 B`. `stop()` removes the
scratch: all ten scratch names referenced by this sweep's four oMLX logs are absent from disk
afterwards. Nothing this sweep served can come from an earlier run, and nothing survives into
visit 2 — which is what the full prefill at the head of every visit shows.

**Ports: swept at both ends of every cell, and none was ever found.** Each runtime owns one port —
mlx-lm 8081, OptiQ 8080, vMLX 8000, oMLX 8100, Osaurus 1337 — and the runner sweeps all five before
and after every cell, printing a line for each holder it finds. `runner.log` holds **no sweep
line**: at all twenty boundaries the five ports were free and no stale Osaurus app was resident.
The sweep kills a stale Osaurus by **full executable path**, never by the name (Jason's `osaurus mcp`
is long-running and is not matched), and `Runtime.start` refuses to start over a listener it did not
start (`ohyesmlx/runtimes.py:721-725`); every cell's `stop()` waits for its port to free before the
next cell begins.

**Nothing else ran on the machine.** The sweep is ten sequential runs with a 30 s cooldown, a port
sweep between each, and no other process was started by this work; the same invariant that voided
the oMLX column on 2026-09-16 is the one this runner enforces at every boundary.

## What this means for a reader

- **The flat half of the 06-02 result does not travel to a plain-attention model.** On
  `Llama-3.1-8B-oQ4` all five runtimes serve a repeated 4,096-token prompt out of a cache, and the
  three that could not do so on Qwen3.5-4B are the fastest of the five: mlx-lm and OptiQ at
  0.136 s and 0.138 s. If you benchmark mlx-lm, OptiQ or vMLX on a hybrid model and see no warm
  benefit, the question to ask is what its layers are made of, not whether the flag worked.
- **Two of the five are worth 140x on a repeated long prompt, two more 39x, one 25x — on this
  model, at this length, prefill-bound.** The speed-up is the ratio between a full prompt
  processing and a lookup; on shorter prompts, or in a workload that decodes far more than it
  prefills, the same mechanism is worth proportionally less.
- **The warm column is a lookup latency, not a prefill rate.** `prefill tok/s` on every `on` row of
  this sweep describes a hash-and-fetch, and the highest number in the table (30,210 tok/s) is
  exactly that. Quote it, if at all, beside the cold column with the word "lookup" attached.
- **A cache hit costs memory only in the runtime that keeps the entry in RAM by design.** vMLX's
  RAM mirror shows +1.11 GB; the four others' sampled peaks move by less than 0.6%, and `peak_mb`
  cannot see a cache that reuses the buffers a prefill already allocated.

## Caveats

- **One `off` cell was still moving when it was measured, and it is the one with the largest
  speed-up.** mlx-lm's `off` cell never reached the plateau (`warmup_plateau: false`): its visit 1
  ran all 20 warmups with TTFT climbing 14.049 → 19.225 s, its drift annotation is +14.5% (early
  median 35.1 tok/s against a late median of 40.2), and its visit-2 measured requests are 12.3%
  faster than visit-1's (16.833 s against 19.192 s). Read against the settled half, its speed-up is
  ~123x rather than 140.0x, and the direction of the finding is unchanged. Every other `off` cell's
  two visits agree within 1.7%; the `on` cells' agree within 3.8% except mlx-lm's, whose visit 2 is
  7.5% faster than its visit 1 (0.129 s against 0.140 s) — a warm hit getting faster, not a
  boundary.
- **Drift annotations are decode-rate drift, not TTFT drift.** `drift` compares the median decode
  rate of the first half of a cell's measured requests against the second half's. Four `off` cells
  are annotated negative (−0.03 to −2.26%, a session reading), the `on` cells +2.28 to +4.86% (not
  finished warming), and mlx-lm's `off` +14.46% as above.
- **The two visit windows are not equal work.** The nine measured requests split 5 (visit 1) and 4
  (visit 2), and where a visit boundary is visible in a series — the `on` cells' every visit opening
  with a full prefill, and Osaurus's 1.503 s opener — the cells are read as two samples, not one.
  Percentiles are taken over the nine together, as the leaderboard does.
- **The reported prompt length is the runtime's own, and none of them is the header's.** `usage`
  says 4,123 tokens for mlx-lm, OptiQ, vMLX and Osaurus, 4,124 for oMLX, against the header's
  `achieved` 4089 from the serving tokenizer. Each runtime applies its own template; every
  comparison here is between a runtime's own two columns, which share a template and a tokenizer.
- **The two `off`/`on` cells of a pair are consecutive, not simultaneous.** `off` always ran first
  and `on` second, so any monotonic session effect inside a pair leans the same way for all five
  runtimes and none of it is attributed to the cache.
- **Osaurus's version moved across documents.** It is 0.25.6 here against 0.25.5 in the hybrid
  sweep, so the two Osaurus columns in Section "The hybrid model against the non-hybrid one" differ
  in the model *and* the runtime build; the other four runtimes are at one version across both.
- **Cross-runtime memory is not comparable** in this sweep or any other from this harness, for the
  reason `docs/research/2026-09-16-footprint-is-not-one-quantity.md` records; the memory table
  above is read row by row.

## Open questions

1. **Why is decode 10–23% slower in the later cell of every pair?** The gap is in the measured
   window and in the warmup series alike, and it is the one number here that moved in every
   runtime in the same direction without being asked to. The `off` cells' decode follows a
   4,123-token prefill burst and the `on` cells' follows a lookup; whether that costs clocks, cache
   residency or allocator state is not measured.
2. **What carries Osaurus's prefix across a visit boundary?** 1.503 s at the head of visit 2 here,
   1.418 s on the hybrid model — twice observed, once per model, and neither document's evidence
   establishes which tier it is (its per-visit logs are one line long). A probe that restarts the
   runtime with each tier disabled in turn would settle it.
3. **Is the warm TTFT a publishable number beside a cold prefill, or a separate column?** The
   report prints it in the same column as the `off` rows and derives `prefill tok/s` from it — a
   30,210 tok/s reading for a hash lookup. Still a decision above this document; this sweep makes
   it five rows instead of two.
4. **Does the warm lookup scale with prompt length?** This sweep measured one length on one model.
   oMLX's block size (256 tokens here, 4,096 for hybrids) and mlx-lm's single retained sequence
   both predict that a multi-block prompt and a shorter-than-block prompt behave differently, and
   neither has been measured.
5. **Is the ~136 ms floor a floor?** mlx-lm and OptiQ both land at 136–138 ms for a 4,123-token
   prefix on this model. Whether that is the trim-and-restore cost, the harness's own request
   overhead, or a coincidence of two runtimes sharing one server is not separated by anything
   here.

## Appendix: evidence files

| what | where |
|---|---|
| ten run records (header pins + observations) | `results/sweep-cache-nonhybrid/<run dir>/results.jsonl` |
| per-cell metric cards | `results/sweep-cache-nonhybrid/<run dir>/leaderboard.md` |
| joined renders | `results/sweep-cache-nonhybrid/sweep-ttft.md`, `sweep-decode.md` |
| runner transcript (toggle, restore, exit 0) | `results/sweep-cache-nonhybrid/runner.log` |
| per-cell CLI output | `results/sweep-cache-nonhybrid/log-<runtime>-<state>.log` (the mlx-lm `off` one is 0 bytes) |
| mlx-lm / OptiQ `on` logs: 1 full prefill + trims | `results/logs/mlxlm-20260917T123922-30030.log`, `…T124044-30030.log`, `results/logs/optiq-20260917T130554-61696.log`, `…T130721-61696.log` |
| mlx-lm / OptiQ `off` logs: `Prompt Cache: 0 sequences` | `results/logs/mlxlm-20260917T122610-14306.log`, `…T123444-14306.log`, `results/logs/optiq-20260917T125500-49015.log`, `…T130044-49015.log` |
| vMLX layout, `Memory-aware cache`, `cache hit` lines | `results/logs/vmlx-20260917T131756-75872.log`, `…T131926-75872.log` |
| vMLX `off`: `cache_outcome=unknown`, no hit | `results/logs/vmlx-20260917T130825-64604.log`, `…T131329-64604.log` |
| oMLX layout, block size 256, scratch at `scanned=0` | `results/logs/omlx-20260917T125226-45479.log`, `…T125354-45479.log` |
| oMLX `off`: `cache disabled` | `results/logs/omlx-20260917T124142-33019.log`, `…T124722-33019.log` |
| Osaurus per-visit logs (one line each) | `results/logs/osaurus-20260917T132033-79283.log`, `…T132559-79283.log`, `…T133114-92193.log`, `…T133253-92193.log` |
| the hybrid sweep this one contrasts with | `docs/research/2026-09-17-cache-state-split.md`, `results/sweep-cache/` |
| the runner and the model fetch | `scripts/run_sweep_cache_nonhybrid.sh`, `scripts/fetch_cache_nonhybrid.sh`, `scripts/probe_cache_nonhybrid.py` |
