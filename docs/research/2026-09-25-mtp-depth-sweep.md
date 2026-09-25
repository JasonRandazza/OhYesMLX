# Native MTP at four draft depths on vMLX: depth 1 buys nothing, depth 3 costs 18%, and the first ladder did not hold its pin

**Date:** 2026-09-25 (night ladder 06:15 → 07:00 EDT; the fixed-depth rerun 16:41 → 17:09 EDT)
**Study:** v3.1 Phase 4, plan 03-06 (native-MTP draft-depth sweep) — the harness pass over the
header pin `mtp_depth` at `off`/`1`/`2`/`3`, with the pre-registered design
`docs/research/2026-09-20-v3-phase3-plan-03-06-study-design.md` read against it in §5
**Harness:** 0.3.0 — `source_sha256 78511b87ed8d51ba9eb2b64222b7531f547c2043d685087c2256f2eddb682652`
for the four rerun directories and `a8ad60e7f76e13c5f2c4b7eaa686989abc60ff2cab5809999f7873ff6ed5c9c1`
for the twelve night ones, identical within each block (`sweep-jang4s__vmlx.md`,
`sweep-optiq4b__optiq.md`, `sweep-optiq__optiq.md`)
**Runner:** `scripts/run_sweep_mtp.sh` → `results/sweep-mtp/`; rerun as `PAIRS=jang4s__vmlx
OUT=results/sweep-mtp-fixed scripts/run_sweep_mtp.sh` → `results/sweep-mtp-fixed/`, each block
joined by `ohyesmlx.cli sweep --varying mtp_depth`
**Subject:** `JANGQ-AI/Qwen3.5-4B-JANG_4S` (3,207,385,506 bytes on disk, identical in all four
rerun cells; one MTP layer, 31 `mtp.layers.0.*` tensors) on vMLX 1.6.59 — plus OptiQ 0.5.13 on
`mlx-community/Qwen3.5-4B-OptiQ-4bit` and `mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit`, whose depth
cells produced no number at all (§4)
**Author:** Claude Opus coordinator

## Why this run exists

Plan 03-06 pre-registered five hypotheses about native multi-token prediction on Apple Silicon —
acceptance degrading with depth (H1), a decode speedup above 1.15× at depths 1 and 2 on
low-entropy text (H2), TTFT invariance (H3), a bounded draft-head memory cost (H4), and the
adaptive safety valve as protection against a net loss (H5). Its own arms named
`Jundot/Qwen3.6-35B-A3B-oQ4-mtp`, three prompt archetypes (code / reasoning / architecture),
an `adaptive` arm and a no-MTP-weights control artifact.

What landed is narrower, and the reason is on this host rather than in the design's reasoning:
**a depth is only honest on an artifact whose heads the runtime will wire** (§7.4.1's bundle gate,
`runtimes.vmlx_mtp_refusal`). On 2026-09-25 that set is one artifact — the 4B `JANG_4S`:

- `models--Jundot--Qwen3.6-35B-A3B-oQ4` (the 35B the Phase 4 sweeps otherwise use) declares
  `text_config.mtp_num_hidden_layers: 1` and its `model.safetensors.index.json` holds **2,010 keys
  and zero `mtp.*`** ones, so vMLX's inspector reports the block as `metadata_inconsistent`
  (§7.4.2) and the harness refuses a depth there in the files, before any model loads.
- The bundle the design names, `models--Jundot--Qwen3.6-35B-A3B-oQ4-mtp`, holds `refs/main` and
  nothing else in its HuggingFace cache entry on this host — no snapshot, no weights. A vMLX 35B
  depth cell would begin with a ~20 GB download, which is its own decision and not this run's.

So the ladder ran where a depth is a claim the artifacts can carry: a 4B, the one model family
(`qwen3_5`) whose MTP path this vMLX release wires. Everything below is that ladder, and §5 says
what it therefore cannot say about the design's 35B question.

**The sweep ran twice, and the second time is the data.** The 06:15 ladder held the flag pair
without the environment variables that make it mean what it says, and the runtime moved depth
underneath it (§3): the pinned columns were not the depths they declared. Commit `ac90077` fixed
the pin (`env VMLX_NATIVE_MTP_AR_SAFETY=0 VMLX_NATIVE_MTP_AR_REENTRY=0`, carried as an `env` prefix
on the start command), added the log half of the claim (`Vmlx.mtp_depth_missing`), and the pairing
was re-run at 16:41. Four of the twelve night run directories are kept and renamed for the defect;
the six OptiQ ones are kept because their failure is a different one, and it is a result (§4).

## What ran

| block | cell | depths, in run order | wall clock (EDT) | run directories |
|---|---|---|---|---|
| night | `jang4s__vmlx` | `off 1 2 3` | 06:15:13 → 06:41:04 | `results/sweep-mtp/` **void** — kept under `void-jang4s__vmlx__depth-not-held-ar-safety-and-sticky-rung/`, joined as `void-sweep-jang4s__vmlx.depth-not-held.md` |
| night | `optiq4b__optiq` | `3 2 1 off` | 06:41:14 → 06:50:19 | `results/sweep-mtp/optiq4b__optiq/` |
| night | `optiq__optiq` | `off 1 2 3` | 06:50:30 → 07:00:42 | `results/sweep-mtp/optiq__optiq/` |
| afternoon | `jang4s__vmlx` | `off 1 2 3` | 16:41:08 → 17:09:35 | `results/sweep-mtp-fixed/jang4s__vmlx/` |

Wall clocks are the runner's own (`results/sweep-mtp/runner.log`, `results/sweep-mtp-fixed/runner.log`;
the runner prints its join commands immediately after the last `exit=0` and the joins themselves
were run separately). The rerun's runner.log echoes the three join commands the script always
prints; only the vMLX pairing has directories under
`results/sweep-mtp-fixed/`, which is why only that sweep is at that path. Depth order is
`off → 1 → 2 → 3` for both vMLX blocks (ascending) and `3 → 2 → 1 → off` for the 4B OptiQ block —
see Conditions for what the ascending order costs the vMLX columns.

**Per visit, per depth**, the four rerun directories and the server log files they produced:

| `mtp_depth` | run directory | log files (visit 1, visit 2) | cold load s |
|---|---|---|---|
| `off` | `20260925T204108Z-format` | `results/logs/vmlx-20260925T164108-53117.log`, `…T164505-53117.log` | 8.17 |
| `1` | `20260925T204812Z-format` | `…T164813-60100.log`, `…T165148-60100.log` | 5.18 |
| `2` | `20260925T205452Z-format` | `…T165452-66926.log`, `…T165834-66926.log` | 5.18 |
| `3` | `20260925T210143Z-format` | `…T170143-73943.log`, `…T170616-73943.log` | 5.16 |

**Pins every run in both blocks shared**, from the sweeps' own shared-pins line: temperature `0.0`,
seed `0`, warmup `{cap: 20, floor: 10, mode: plateau, plateau_pct: 3.0, window: 5}`, measured `9`,
cooldown `30.0` s, concurrency `1`, and `prompt_tokens`, `cache_state`, `kv_quant`,
`stream_experts` all not taken. Workloads `chat` (max_tokens 128), `prefill` (64) and `decode`
(512), identical messages in all twelve runs; the servers' own prompt counts (34 / 1,319 / 34 on
this bundle) are each runtime's own tokenizer on the same text.

**Each cell is visited twice** (`measure.visit_plan`), with the nine measured batches split 5 + 4
across the cold and hot visits, and a row's memory reading is the visit whose sampled peak was
higher (`measure._highest_peak`). Every depth column below therefore has two run directories'
worth of requests in one row — 92, 91 and 93 MTP requests at depths 1, 2 and 3, warmups included
(the log writes one line per request on these four runs; the night logs write two for a request
that ever fell back, which is one of the ways the two blocks differ — §3).

**Every one of the twelve rerun cells is `PASS`,** `n = 9` measured per workload, and every
measured request on all four depths carries the grid's `reasoning timed` marker: 9 of 9 measured
requests per cell were timed on the reasoning stream, because this bundle answers inside its trace
and never reaches a content token under these caps. The first measured request of the depth-3
`chat` cell (`20260925T210143Z-format`, 128 completion tokens, 55 content deltas) opens:

> `Here's a thinking process that leads to the suggested explanation:` … `**Core Task:** Explain why a benchmark that changes two variables simultaneously cannot attribute a difference to either one.`

That is the run's own prompt read back, and it is language on every cell at every depth.

## Conditions

- **The vMLX depth order is ascending, so the pin is confounded with the clock** — `off` first,
  `3` last, 28 minutes later. The runner's comment claims the per-pairing direction alternates so
  drift cannot alias onto the pin; for this pairing it does not alternate, and the depth-3 column
  is both the deepest and the last. What the record offers against that is not an interleave but a
  phase that does not care about depth: **the prefill-bound readings are flat across the ladder** —
  the `prefill` shape's TTFT p50 is 1.814 / 1.751 / 1.718 / 1.784 s and its prefill throughput
  724.4 / 750.2 / 764.8 / 736.7 tok/s, i.e. no trend at the ±5% level where the `chat` shape loses
  19.9%. The machine that served depth 3's prompt at `off`'s speed is the same machine; the decode
  change is the pin's. That argument is a reading of a different phase, not a control, and the
  within-cell drift markers (below) are the other thing it has.
- **The `off` cell is the session's first start.** Its cold load is 8.17 s against 5.16–5.18 s for
  the other three, because it is the first vMLX start after the machine's working day and the
  others follow it within minutes. A cross-cell cold-load reading is not available from this
  ladder; the pin's own cost is what §2 measures, and no cell's first request is an outlier (1.77 /
  1.52 / 1.58 / 1.83 s, none of them carrying the harness's deferred-load note).
- **One run per depth.** The ladder was walked once, in one sitting, on a machine whose desktop was
  in use — the runner sweeps ports and stale Osaurus apps, but the harness cannot detect contention
  and nothing in the record attests the host's state during either block. The two visits inside a
  run are the cold and hot halves of one window, not replicates.
- **The pin is three things, not one** (§7.4.1). A depth cell is
  `env VMLX_NATIVE_MTP_AR_SAFETY=0 VMLX_NATIVE_MTP_AR_REENTRY=0 vmlx serve … --native-mtp-depth N
  --native-mtp-depth-policy fixed`, and the log's own banner is the evidence the second half took:
  `Native MTP: READY D3 (scope: text+vl, sampling: compatible-only, depth: fixed)`. The `off` cell
  passes `--disable-native-mtp` and its banner reads `Native MTP: DISABLED (--disable-native-mtp)`;
  its log holds no `MLLM MTP` line at all, which is what an off cell should look like. **Neither the
  run directory nor the log stores the start command** — the record keeps the `mtp_depth` pin and the
  harness `source_sha256` that together determine it, which is why the commit that changed the
  command is cited by hash above.
- **Depth 3 here means the configured depth is 3 and no controller demoted it.** It does not mean
  every verify cycle drafted three tokens: the third mechanism, the per-cycle confidence gate
  (`VMLX_NATIVE_MTP_DRAFT_MARGIN`), is not touched by the pin, and the log's own counter — quoted in
  §2 — is `margin_truncated=0` on every request of all four cells.

## Results

### 1. Depth 1 is a wash, depth 2 is a wash with a wider spread, depth 3 is a 16–20% loss

**Axis — `mtp_depth`, runtime, artifact and every other pin held constant.** One artifact, four
cells, one shape per table, 9 measured requests each, all four columns timed on the same channel
(`reasoning`). **Caveat — what this cannot read:** this is one runtime's depth ladder on one 4B
bundle, walked once; nothing here ranks runtimes, and §5 names what it does not say about a 35B.

| workload | `off` | `1` | `2` | `3` | `1` vs `off` | `2` vs `off` | `3` vs `off` |
|---|---|---|---|---|---|---|---|
| `chat` (128) | 74.9 | 74.7 | 70.8 | **60.0** | −0.3% | −5.5% | **−19.9%** |
| `prefill` (64) | 75.6 | 79.0 | 76.1 | **62.3** | +4.5% | +0.7% | **−17.6%** |
| `decode` (512) | 72.4 | 74.9 | 71.1 | **60.5** | +3.5% | −1.8% | **−16.4%** |

All twelve figures are `decode_tps` from `results/sweep-mtp-fixed/sweep-jang4s__vmlx.md`, which is
the join of the four run directories' own `leaderboard.md` rows. Two rows carry a drift marker and
both say the same thing: `off`/`prefill` −5.3% and `1`/`chat` −9.9% are *thermal* (the cell slowed
as it was measured); every other row is inside ±3.1%. The two positive steps in the table
(+4.5%, +3.5%) are the same size as the rows' own drift readings — the `off` `prefill` cell moved
5.3% inside its own window — so **no column here is a speedup**; the honest reading of depths 1 and
2 is "indistinguishable from plain decode", and of depth 3 "a fifth slower".

The same ladder on the metrics that are not the ranking metric:

| metric | `off` | `1` | `2` | `3` |
|---|---|---|---|---|
| TTFT p50 s, `prefill` shape (1,319-token prompt) | 1.814 | 1.751 | 1.718 | 1.784 |
| ITL ms, `chat` / `prefill` / `decode` | 13.4 / 13.4 / 13.8 | 13.5 / 12.9 / 13.4 | 14.2 / 13.4 / 14.1 | 16.8 / 16.3 / 16.6 |
| E2E p50 s, `decode` shape (512 tokens) | 7.202 | 6.982 | 7.344 | 8.600 |
| aggregate tok/s, `decode` shape | 71.4 | 73.5 | 69.6 | 59.2 |
| prefill tok/s, `prefill` shape | 724.4 | 750.2 | 764.8 | 736.7 |
| peak MB, `chat` / `prefill` / `decode` | 3830 / 4667 / 3846 | 3868 / 4606 / 3909 | 4026 / 4740 / 4070 | 3901 / 4606 / 3947 |

- **TTFT does not move with depth** — the `prefill` shape's 1.718–1.814 s is a ±2.7% band, and the
  two short-prompt shapes read 0.130–0.147 s (a ±17 ms band, where a percentage is meaningless).
  Drafting is a decode-time mechanism on this runtime: it enters after the prompt is consumed.
- **ITL rises only where the rate falls**: 13.4–13.5 ms at depths 1 and 2 against 16.3–16.8 ms at
  depth 3. That is the same statement as the rate column from the other end — the per-token cost is
  what changed, not the per-request overhead.
- **Memory does not order with depth**: the largest step over `off` is +224 MB (`decode`, depth 2),
  and depth 3 sits between the two. The artifact is byte-identical in all four cells
  (3,207,385,506 bytes), so what a depth changes at runtime is draft state and a longer verify
  graph, not new weights — and at this instrument's resolution the columns are level.

### 2. Why: each further draft is less likely to be accepted, and the cycle it rides in gets dearer

**Axis — `mtp_depth`.** The runtime's own per-request accounting, summed over the two visits of each
depth (the fixed four runs' logs; 92, 91 and 93 requests at depths 1, 2 and 3). **Caveat:** these are
the runtime's own counters over the whole visit, warmups included, and they are the mechanism's
explanation of §1's numbers — not a second measurement of them.

A depth-N cell issues N drafts per verify cycle and accepts them as a **prefix** of the chain, so
the meaningful figure is the probability that the k-th draft is accepted, which is also the
probability that a chain of k drafts survives whole. (The prefix rule is visible in the emitted
counts, not assumed: a chain accepted whole earns one bonus token from the same verify forward, and
the bonus count tracks the deepest level's — 8,815 against 8,849 at depth 1, 4,562 against 4,592 at
depth 2, 2,542 against 2,604 at depth 3, the small deficit being requests' final cycles.)

The two visits of each column, summed:

| column | level 1 | level 2 | level 3 | over all drafts issued | accepted drafts per cycle | tokens emitted per cycle |
|---|---|---|---|---|---|---|
| `1` | **8849/12057 = 0.734** | — | — | 0.734 | 0.734 | 1.480 |
| `2` | 6847/9273 = 0.738 | **4592/9273 = 0.495** | — | 0.617 | 1.234 | 1.745 |
| `3` | 6293/8835 = 0.712 | 3999/8835 = 0.453 | **2604/8835 = 0.295** | 0.487 | 1.460 | 1.765 |

(The bolded figures are the ones the ladder is read for: the drafted token a depth *adds* is
accepted 73% of the time at depth 1, 50% at depth 2 and 29% at depth 3. A column's overall
draft-acceptance rate — 0.734 / 0.617 / 0.487 — is the mean over its levels, and it is *not* the
number that explains the depth's cost, because a cycle that accepts only its first draft still
paid for three.)

A representative request from each column, verbatim
(`finish=` / `accept_by_depth` / `timings_ms` lines, `results/logs/vmlx-20260925T16*` for depths 1
and 2, `…T1701*` for depth 3):

```
MTP[chatcmpl-4b1530a8] finish=length cycles=74 accepted=53/74 (71.6%) emits[init=2,draft=53,bonus=52,verify=21] margin_truncated=0 cycles_by_depth[d1=74] policy=fixed configured=D1 …
MTP[chatcmpl-4b1530a8] accept_by_depth[d1=53/74,d2=0/0,d3=0/0] forwards[seed_main=1,verify_main=75,replay_main=0,mtp=75]

MTP[chatcmpl-411c2d9d] finish=length cycles=57 accepted=69/114 (60.5%) emits[init=2,draft=69,bonus=27,verify=30] margin_truncated=0 cycles_by_depth[d2=57] policy=fixed configured=D2 …
MTP[chatcmpl-411c2d9d] accept_by_depth[d1=42/57,d2=27/57,d3=0/0] forwards[seed_main=1,verify_main=58,replay_main=0,mtp=116]

MTP[chatcmpl-d80b4142] finish=length cycles=53 accepted=74/159 (46.5%) emits[init=2,draft=74,bonus=15,verify=37] margin_truncated=0 cycles_by_depth[d3=53] policy=fixed configured=D3 …
MTP[chatcmpl-d80b4142] accept_by_depth[d1=37/53,d2=21/53,d3=16/53] forwards[seed_main=1,verify_main=54,replay_main=0,mtp=162]
```

Three things are load-bearing in those lines:

- **`cycles_by_depth[dN=<all cycles>]` on every request**: the depth the header declared is the only
  depth that ran, and `mtp=N × cycles` on the `forwards` line is the head called once per drafted
  token. `margin_truncated=0` throughout: no draft chain was cut short by the confidence gate.
- **The denominator of `accepted=` is `cycles × depth`** (74 / 114 = 2 × 57 / 159 = 3 × 53), which is
  why the per-level table above is the readable one: `accepted=X/Y` on a depth-3 line is the total
  accepted across three positions, not a rate.
- **`verify_main` is one per cycle at every depth** (1.008 / 1.010 / 1.011 forwards per cycle
  across the three columns) while `mtp` is one per draft (1.008 / 2.020 / 3.032): each cycle runs the
  same single verify forward, over a longer chain, and one extra head pass per extra draft.

The cost side, from the same logs' own `timings_ms`:

| depth | requests | cycles | MTP forwards per cycle | verify forwards per cycle | `avg_cycle` ms | `sample` ms per cycle |
|---|---|---|---|---|---|---|
| `1` | 92 | 12,057 | 1.008 | 1.008 | 8.09 | 8.17 |
| `2` | 91 | 9,273 | 2.020 | 1.010 | 10.65 | 10.19 |
| `3` | 93 | 8,835 | 3.032 | 1.011 | 14.03 | 13.22 |

So the ladder's arithmetic, in the runtime's own units:

- **tokens emitted per cycle: 1.480 → 1.745 → 1.765** — +17.9% then +1.1%.
- **the cycle's reported cost: 8.09 → 10.65 → 14.03 ms** — +31.7% then +31.7%.

Depth 2 already spends 1.32× the cycle for 1.18× the tokens, and depth 3 spends 1.73× for 1.19×;
measured end to end (§1), that is −5.5% at depth 2 and −19.9% at depth 3 on `chat`. The mechanism
is not subtle: accepting the *first* draft is cheap because the verify forward was going to be run
anyway, and every draft after it multiplies the chain the verify step has to read — the `sample`
step, which is nearly the whole of the cycle the log reports, grows 8.17 → 13.22 ms per cycle
across the ladder — while the token it might buy is accepted less than half the time at depth 2 and
under a third of the time at depth 3. **The acceptance numbers and the cost numbers point the same
way, and it is the opposite way from the design's H2.**

One caveat on those last two columns, stated because a reader will try to reconcile them: the
runtime's `avg_cycle` and its `sample` are a per-cycle accounting of its own, and they do not
reconcile to wall clock — at depth 1, 1.480 tokens per 8.09 ms would be 183 tok/s against a measured
74.7. The published rate is `decode_tps` from `§1`; the ratio between depths is what the two tables
above are for, and the level is not.

### 3. The night's ladder is void: the pin declared a depth the runtime did not hold

The 06:15 block ran the same four values, published four columns, and the columns were not what
their headers said. Its defect is not subtle in the log:

```
MLLM MTP[chatcmpl-4a310528] start rung D1 (previous request ended in D1); promotion probe to D2 after 8 cycles
MLLM MTP[chatcmpl-4a310528] promotion probe D1 -> D2 at cycle=19 (lower rung measured 11.4ms/tok, AR 12.0ms/tok)
MLLM MTP[chatcmpl-4a310528] promotion lost, back to D1: windowed AR safety D2 -> D1 at cycle=31 …
MLLM MTP[chatcmpl-4a310528] AR safety D1 losing at cycle=64 (14.0ms/tok vs AR 12.4ms); confirming over the next window
```

— `results/logs/vmlx-20260925T062816-11233.log` (the night's **depth-2** run). Two controllers that
`--native-mtp-depth-policy fixed` does not stop were both live: the **sticky start rung**, which
opens a request at D1 when the previous one ended at D1 (`start rung D1`), and the **AR-safety
valve**, which demotes a rung per trip and falls back to plain autoregressive decode at depth 1
(`AR safety D3 -> D2`, `D2 -> D1`, `finish=fallback_to_ar`). The night's depth-3 run put
**306 of its 8,196 verify cycles (3.7%) at D3**; 1,337 (16.3%) ran at D2 and 6,553 at D1. Counted
per request — the log writes a second `finish=` line for a request that ever fell back, so lines
are not requests, and the whole file is 105 lines for 45 requests:

| night cell | requests (both visits) | opened at rung D1 | ever ended `fallback_to_ar` | cycles at the pinned depth | share |
|---|---|---|---|---|---|
| depth 2 | 94 | 89 | 29 | 1,607 of 8,910 | 18.0% |
| depth 3 | 87 | 78 | 29 | 306 of 8,196 | 3.7% |

Of the depth-3 run's 201 `accept_by_depth` rows, 9 show a non-zero `d3` denominator — the shape
of a column that is mostly depth 1 wearing a depth-3 header. (§7.4.1 of `docs/runtimes/vmlx.md`
first carried these counts from `…T062816-11233.log`, which is the depth-2 run, as though it were a
depth-3 one; it was corrected alongside this paper.) (For contrast, the
fixed rerun's depth-3 column: 8,835 cycles, **all** of them at D3, and zero start-rung lines, zero
`fallback_to_ar`, zero non-zero `margin_truncated` in all eight of its log files. The valve's own
reading of the same state it was being asked to hold — `AR safety D1 losing at cycle=64 (14.0ms/tok
vs AR 12.4ms)` — is that MTP at depth 1 costs more per token than plain decode, and the fixed rerun
ran that state anyway, because that is what `AR_SAFETY=0` means: *"fixed then never leaves its
depth, even when slower than plain decoding"* (§7.4.1).)

What the night's numbers were, against the rerun's, is the reason the whole block is kept and not
quietly overwritten:

| workload | `off` (night) | `3` (night) | `3` (fixed rerun) |
|---|---|---|---|
| `chat` | 77.9 | 75.6 | **60.0** |
| `prefill` | 77.3 | 78.1 | **62.3** |
| `decode` | 76.0 | 75.7 | **60.5** |

The night's depth-3 column would have published a ~25% faster number than the state it named —
because it was measuring depth 1, mostly. That is the reason the four directories are kept under
`void-jang4s__vmlx__depth-not-held-ar-safety-and-sticky-rung/` with their logs renamed
(`log-jang4s__vmlx-<depth>.void-depth-not-held.log`) and their sweep as
`void-sweep-jang4s__vmlx.depth-not-held.md`: a run discarded for a stated defect in its conditions,
never for its numbers, and the defect here is that the header's claim was false. The one cell the
defect cannot reach is the night's `off` column — with MTP disabled there is no depth to move — and
the harness's own delivery check passes it for exactly that reason; it is not joined into the
rerun's tables because a sweep has one run directory per pin value.

Commit `ac90077` is the fix, and it is two changes rather than one: the start command gained
`env VMLX_NATIVE_MTP_AR_SAFETY=0 VMLX_NATIVE_MTP_AR_REENTRY=0`, and the harness gained the log half
that *would have caught this on the night* (`Vmlx.mtp_depth_missing`: fail a depth cell whose log
shows a `start rung D<k>` below the pin, a `finish=fallback_to_ar`, or no `accept_by_depth` row
with a non-zero `d<N>` denominator). The check is asked once the visit's measured requests have
answered — for vMLX because its evidence is per request, for OptiQ for the reason §4 shows — where
the version that ran the night asked it after the first workload; and the new pin surface was
approved as a pin before it was used.

### 4. OptiQ's six depth cells FAILed, and the runtime's own log is why

**Axis — `mtp_depth`, on two OptiQ artifacts.** The `off` cells ran and passed; every depth cell
is a `FAIL` under `sweep-optiq4b__optiq.md` and `sweep-optiq__optiq.md`, in all six combinations
across the two artifacts and three depths. **Caveat:** these are failures to hold the pin, not
measurements; nothing below is a speed number, and that is the point of printing them.

| cell | artifact | bytes on disk | `off` decode tok/s (`chat`/`prefill`/`decode`) | depth cells |
|---|---|---|---|---|
| `optiq4b__optiq` | `mlx-community/Qwen3.5-4B-OptiQ-4bit` | 4,043,620,369 | 70.9 / 79.9 / 64.3 | `1`, `2`, `3` all FAIL |
| `optiq__optiq` | `mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit` | 24,693,930,096 | 71.0 / 77.8 / 67.3 | `1`, `2`, `3` all FAIL |

Both `off` columns are `PASS` with `n = 9` and carry no `reasoning timed` marker (they are
content-timed, unlike every vMLX row above). The six depth cells fail on the runtime's log, and the
harness's own words differ between the two artifacts because the runtime said different things.

**The 35B (all three depths), quoted verbatim from the row's reason:**

> `mtp_depth='1' was not delivered: optiq's own log never printed '[optiq.serve] MTP engine ready (depth=1).', and it says "WARNING:optiq.runtime.engine:MTP head not attached (MTP head weight 'layers.0.mlp.switch_mlp.gate_proj.weight' has shape (256, 512, 2048), block expects (256, 512, 256) (3 mismatched tensors); the head was built from the wrong config); continuing without MTP" instead. The flag was accepted and the engine attached without a draft head, so this cell is FAIL rather than a number published under a pin it does not hold (log: /Users/jrazz/Dev/active/OhYesMLX/results/logs/optiq-20260925T065802-34585.log).`

The log under it also holds, once per request, `RuntimeError: --mtp requested but '…/Qwen3.6-35B-A3B-OptiQ-4bit/…' has no MTP head. Re-convert with v0.1.0+ optiq convert (which preserves mtp.* tensors).` — 24 of the visit's 25 requests. The engine attached, the head did not fit the block, and every request died.

**The 4B (all three depths), quoted verbatim:**

> `mtp_depth='3' was not delivered: optiq's own log never printed '[optiq.serve] MTP engine ready (depth=3).', and it says nothing about why. The flag was accepted, so this cell is FAIL rather than a number published under a pin nothing confirmed (log: /Users/jrazz/Dev/active/OhYesMLX/results/logs/optiq-20260925T064114-21379.log).`

"Nothing about why" is precise about the *check's* two markers (the ready line and
`MTP head not attached` / `MTP injection failed`), and the log does hold one thing under them:
`[MTP inject] Loaded 29 tensors from …/optiq/mtp.safetensors`, then, on every request, a traceback
ending `File "…/optiq/runtime/engine.py", line 760, in generate_stream / first_token =
_logits_to_token(logits[0, -1], temperature)` / `TypeError: 'NoneType' object is not subscriptable`.
The head's tensors were found and loaded; the generate path that would use them returned nothing.
All 25 requests (20 warmups, 5 measured) came back to the client as `ok=False`, `error=incomplete
SSE stream`, `text=''`; the `prefill` and `decode` rows show `n = 0` because the harness of the night
asked the depth check after workload 0 and stopped the cell — the same check today is asked after
the visit's measured requests, which is why the row's own note reads `short measured window: 5 of 9
pinned batches landed`.

**Why this is a result rather than an infrastructure note.** Both artifacts pass the harness's
artifact gate (`runtimes.optiq_mtp_refusal` — each declares `mtp_num_hidden_layers: 1` and each names
`optiq/mtp.safetensors`, which is the gate's documented accepted case; §9.2 of `docs/runtimes/optiq.md`
records both as satisfying both conditions, and both still do). So on this host the pin's *artifact*
half is necessary and not sufficient: the head can load and still not drive a decode, in two
different ways, and only the log half catches either. Under the project's first rule the verdict is
the one printed — a `FAIL` with the runtime's own text, never a number under a pin the decode did not
hold — and OptiQ contributes no depth column to this study.

### 5. Where the results answer the design (plan 03-06, H1–H5)

The design's arms are not the arms that ran, and the differences are stated where they matter: it
pinned `Jundot/…-35B-A3B-oQ4-mtp` (§ why not), three prompt archetypes (code / reasoning /
architecture — the harness ran its three standard shapes, all prose), an `adaptive` arm (the harness
pin has four values, and `fixed` is what carries a depth), a base-model control without MTP weights
(not run), and `--native-mtp-sampling-policy greedy-only` (not passed; the harness pins `temperature
0.0` and `seed 0`, and every request's log line reads `greedy=True distribution=False`). Read
against what did run:

- **H1, acceptance degrades monotonically with depth: confirmed.** The level-wise figures are
  0.734 / 0.495 / 0.295 for the drafted token each depth adds, and the chain survival at depth 3
  (all three accepted) is 0.295. Error compounding is visible in the ladder's shape, and the second
  level is already below a coin flip.
- **H2, a >1.15× decode speedup at depths 1 and 2 on low-entropy text: refuted on what ran.** No
  cell at any depth beat `off` by more than 4.5%, and that cell (`prefill`, depth 1) is inside its
  own column's drift reading. The design's low-entropy arm was structured **code**; the three
  workloads here are prose (an engineering-standard document and a benchmark-design question), so
  the design's contrast is untested rather than refuted in its own terms — see Open questions.
  What is refuted is the mechanism's premise on this workload: at 0.73 acceptance the first draft
  costs a verify forward and buys a token 73% of the time, which lands at parity, not at 1.15×.
- **H3, TTFT invariance at ±5%: confirmed.** The prompt-bearing shape reads 1.718–1.814 s (a ±2.7%
  band across the ladder) and the two short-prompt shapes 0.130–0.147 s. Drafting does not enter
  prefill on this runtime.
- **H4, a bounded draft-head memory cost (<1.0 GB): confirmed, on a different basis than the
  design's.** The design budgeted ~600 MB of safetensors for a head; here the artifact is the same
  file in all four cells (3,207,385,506 bytes, byte-identical), so the heads are resident in every
  column including `off`, and what the ladder can show is the *draft state's* cost — the largest
  step over `off` is +224 MB, no cell moves more than 6%, and the columns do not order with depth.
  A head-on/head-off comparison needs the design's control artifact, which was not run.
- **H5, the adaptive valve prevents degradation below the AR floor: not testable under this pin,
  and half-answered by the night it voided.** The valve is off in every cell of the rerun, by design
  — that is what makes the depth fixed. What the night shows is the valve working on the other side
  of the same question: it demoted depth 3 to depth 1 and fell the request back to AR in 29 of the
  87 requests of the depth-3 command, on its own reading that MTP was costing 13–16 ms per token
  against an AR baseline of 12–14 ms. So the mechanism the design hoped would protect the number
  does exist and does fire — and the depth-3 column the fixed pin publishes at −18% is a state it
  would have refused. Both facts belong in the same sentence when this ladder is quoted.

## Open questions

1. **What does a depth that is *allowed to adapt* do over a long run?** The rerun answers "what is a
   fixed depth worth"; the production question is what the valve's own policy lands on, and that is
   the design's arm 5. One cell at `--native-mtp-depth-policy adaptive` with the variables left at
   their defaults would say whether the runtime converges on a depth, and which, on these workloads.
2. **Is there a workload where depth 1 pays?** Acceptance at level 1 is 0.71–0.74 on all three
   shapes here, which is what makes the first draft a wash; the design's H2 argues low-entropy code
   should accept more. The harness has the workload mechanism to add one code shape, and it would
   cost one cell per depth rather than a study.
3. **Does the 4B's ladder transfer to a MoE 35B?** The design's subject was a 35B A3B; on a
   bandwidth-bound decode the head's extra compute may be cheaper relative to the weight read,
   which is a different arithmetic from a 4B's. Nothing in this record speaks to it: the 35B bundle
   with heads is not on this host, and the 35B bundle that is has no `mtp.*` tensors to pin.
4. **Why does the runtime's own cycle accounting not close against wall clock?** `avg_cycle` ≈
   `sample` ms per cycle, and both sit at about 40% of the wall-clock per cycle implied by the
   measured rate (1.48 emitted tokens per cycle at 74.7 tok/s is 19.8 ms per cycle, against an
   8.09 ms `avg_cycle`). The published number is the harness's and the ratio between depths is
   unaffected — but anyone building a cost model from the log's fields will find that gap first.
5. **Should OptiQ's depth check quote a traceback?** The 4B's cell says "it says nothing about why"
   because the check's fallback markers are the engine's attach warnings; the log's actual cause —
   `_logits_to_token(None)` — is a stack trace neither marker matches. Either the markers widen, or
   the note's wording changes: "no line this check reads" is not "nothing in the log".
6. **And should `optiq_mtp_refusal` gain a shape check?** The 35B's head loaded from the right file
   and did not fit the block (`(256, 512, 2048)` against `(256, 512, 256)`, 3 tensors). The artifact
   gate could in principle read the sidecar's shapes; today it checks the declaration and the path,
   and the log gate catches the rest.

## What this cannot claim

- **Nothing about a runtime other than vMLX.** The `mtp_depth` pin reaches two runtimes: one is
  vMLX, and the other (OptiQ) has no depth cell on record here at all (§4). mlx-lm, oMLX and
  Osaurus refuse the pin before a server starts, per `docs/research/2026-09-24`-era surface work
  recorded in `docs/interfaces.md`. There is no runtime ranking in this paper and none is possible
  from it.
- **Nothing about a 35B, and nothing about MoE.** Every column above is `Qwen3.5-4B-JANG_4S`, one
  4B dense-ish bundle of 3.2 GB, on one runtime release. The design's subject — a 35B A3B MoE — is
  untested: its `-mtp` bundle is not on this host, and the 35B bundle that is carries no `mtp.*`
  tensors for a depth to pin.
- **Nothing about MTP as a technique.** One family (`qwen3_5`), one release (vMLX 1.6.59), one
  artifact, one ladder walked once, at temperature 0 with one draft-chain length per column. A
  different quant, a different family, or a different runtime's implementation is a different
  measurement.
- **No cross-runtime TTFT or memory comparison** — and no cross-*shape* one either: every table is
  one workload's column, and a `chat` figure is never blended with a `decode` one.
- **Nothing about accuracy.** Coherence is a floor — every cell here produced language, and the gate
  says nothing about whether an answer was right. Nothing in this run scores an output.
- **The depth columns are states the runtime would itself have declined.** `AR_SAFETY=0` is a
  declared state, not a neutral one: the value's whole purpose is to keep MTP drafting when the
  runtime's own measurement says plain decode is faster, and the fixed depth-3 column is that state.
  A production reading of this ladder is "what a fixed depth costs", not "what the runtime would do".
- **No claim that the night's `off` column is wrong.** With MTP disabled there is no depth to move;
  that cell is the same measurement the rerun made, in the same block, and it is cited above as
  context rather than joined into the rerun's tables.

---

## Update 2026-09-25 (later the same day): Open questions 5 and 6, answered by `773b739`

The findings above are unchanged; what follows is what the harness does now, where the two open
questions asked what it should.

- **Open question 5 — should the depth check quote a traceback? Yes.** `runtimes._banner_evidence`
  reads the log head once more when the window holds neither a required line nor a fallback
  marker, and quotes that traceback's exception line and innermost frame
  (`_traceback_cause`); a window with no traceback either says the log "prints no line this check
  reads", which is the narrower, true claim §4's cells showed the old wording getting wrong. On
  the 4B's cells the FAIL now names the `TypeError` at `engine.py:760` instead of saying nothing
  about why; the cells themselves are still FAIL (the check could not confirm a draft head ran).
- **Open question 6 — should `optiq_mtp_refusal` gain a shape check? Yes, as a third condition.**
  `runtimes._optiq_head_packing_refusal` reads the sidecar's safetensors header with the stdlib and
  refuses a head the config declares prequantized when a weight has no `.scales`/`.biases` pair,
  when the pair's axes disagree with the packing arithmetic, or when its routed experts are in the
  fused HF layout `_split_fused_experts` rewrites without their scales. `Qwen3.6-35B-A3B-OptiQ-4bit`
  is now `N/A` before a runtime starts, so §4's load-then-404 failure is not reachable on that
  artifact; the 4B passes all three conditions and its depth cells are driven as before.

Neither change moves a number in this paper: §3's void ladder and the 4B's fixed-depth columns were
measured under the code as it stood, and the record of what those runs printed is what §4 is.
