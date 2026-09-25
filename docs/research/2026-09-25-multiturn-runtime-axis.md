# The ten-turn conversation on five runtimes: flat decode, growing TTFT, and two columns that never answer

**Date:** 2026-09-25 (night grid 09:14 → 10:22 EDT; the Osaurus column re-run 12:31 → 12:52 EDT)
**Study:** v3.1 Phase 4, plan 03-04 (multi-turn conversation sweep) — the harness runtime axis over
`turn-01 … turn-10`
**Harness:** 0.3.0, `source_sha256 a8ad60e7f76e13c5f2c4b7eaa686989abc60ff2cab5809999f7873ff6ed5c9c1`,
identical in both run directories
**Runner:** `scripts/run_multiturn.sh` → `results/multiturn/` and `results/multiturn-osaurus/`,
joined by `ohyesmlx.cli grid` separately
**Subject:** `Jundot/Qwen3.6-35B-A3B-oQ4` (21,125,808,764 bytes on disk), one format (`oq4`), five
runtimes — the one format all five serve
**Author:** Claude Opus coordinator

## Why this run exists

Plan 03-04 pre-registered five hypotheses about what a growing conversation does to a thinking
model's serving on Apple Silicon: that a prefix cache decouples TTFT from history (H1), that decode
stays within 5% of turn 1 across ten turns (H2), that ITL moves by less than 1 ms (H3), that the
process footprint grows by no more than 250 MB (H4), and that all four runtimes stay coherent and
responsive for ten turns (H5). The design pinned `temperature=0`, `seed=0`, `max_tokens=64` and a
ten-question technical dialogue whose assistant turns were to be *the runtime's own previous
answers*, fed back live.

The runner made two deliberate changes to that design, and both matter when reading the results:

1. **The history is the pinned conversation with fixed literal assistant replies, not each
   runtime's own output** (`scripts/run_multiturn.sh`: "turn N is the same prompt on every
   runtime"). A live-reply history would make each column's prompts a different text, which is the
   single-variable rule's line.
2. **`max_tokens` is 128, not 64** (the grid's workload line). On a model that thinks before it
   answers, the cap decides which phase of generation gets measured, and at 128 tokens the answer
   did not arrive on three of the five columns at all — see §1.

## What ran

| run directory | runtimes | wall clock (EDT) | versions | joined as |
|---|---|---|---|---|
| `results/multiturn/20260925T131430Z-runtime` | mlxlm, omlx, optiq, vmlx (+ osaurus N/A) | 09:14:30 → 10:22:10 | 0.31.3, 0.6.4, 0.5.13, 1.6.59 | `results/multiturn/grid.md` (4 columns) |
| `results/multiturn-osaurus/20260925T163101Z-runtime` | osaurus | 12:31:01 → 12:52:20 | 0.25.12 | `results/multiturn-osaurus/grid.md` (1 column) |

**Pins both joins share**, from the grids' own shared-pins line: temperature `0.0`, seed `0`,
warmup `{cap: 20, floor: 10, mode: plateau, plateau_pct: 3.0, window: 5}`, measured `9`,
cooldown `30.0` s, concurrency `1`, and `prompt_tokens`, `cache_state`, `kv_quant`, `mtp_depth`,
`stream_experts` all not taken. Ten workloads `turn-01 … turn-10`, each `max_tokens` 128, with
identical messages across every column.

**Osaurus is a second sitting, and the grid's own rule keeps it that way.** During the night all
ten Osaurus cells were `N/A`: *"runtime 'osaurus' did not start: RuntimeStartError: Osaurus
settings drifted from the recorded baseline … server.json:modelIdleResidencyPolicy.seconds:
baseline 900, host 30"*. Commit `732eaef` pinned the host settings (and the host prefix cache off),
and the column was re-run at 12:31. It cannot be joined with the night's four columns — a cell
measured in two run directories is a duplicate, and `report._check_cells_appear_once` refuses
rather than choosing: *"there is no latest-wins rule because which run is newer is not which run is
right"*. So the grid was run twice, once per directory, and the two documents are read side by
side. Every Osaurus figure below is its own grid's, from a sitting ~2.2 hours after the others.

**Cache state is not uniform, and the run pinned nothing to make it so.** `cache_state` is not
taken, which means each runtime started at its own default (`cli.py`: "Leaving the flag out pins
nothing … which was not uniform across the grid and is not the same fact as `off`"). In this run:
mlx-lm and OptiQ keep their default LRU prompt cache (mlx-lm's default is 10 entries), oMLX runs
`--no-cache`, vMLX runs `--disable-prefix-cache`, and Osaurus's host prefix cache was pinned false
by `scripts/osaurus-pin.sh`. That is the pin under which "no prefix reuse is visible" is claimed
below — and it is why the mlx-lm column, whose cache is *on*, is the one that needs an explanation
rather than an assumption.

**Every cell is visited twice, and the nine measured requests are split across the two visits.**
`measure.visit_plan` walks the cell list forwards in round 1 and backwards in round 2, so a
runtime is measured cool and then again hot, with the drift figure comparing the two halves of its
own window (`measure.py`: "the first half is the cell's cool visit, the second half its hot one").
The runtime logs show the shape of it plainly: mlx-lm's cell has two log files, one per visit
(`results/logs/mlxlm-20260925T091430-41697.log` and `…T101438-…`), each walking `turn-01`
(24 tokens) through `turn-10` (1393) in about eight minutes. A row's `memory` reading is the visit
whose sampled peak was higher (`measure._highest_peak`), which is why a row's footprint figure is a
maximum over the windows that measured it rather than a single snapshot.

## Results

### 1. What each column is timing, before any number is read

The timing channel is derived per observation (`transport.timing_channel`) from the two texts the
runtime sent: a runtime that never reaches content, or mirrors its reasoning into it, is timed on
the reasoning stream; one that emits content is timed on content. **Axis — the runtime, format
(`oq4`) held constant.** **Caveat:** this is a shape table, not a metric table — it says which
stream each column timed and says nothing about speed. Under a 128-token cap, that split turns out
to be the run's dominant fact:

| runtime | output shape, per turn (first measured request of each) | timing channel | decode window |
|---|---|---|---|
| mlxlm | reasoning only: 483–624 chars of trace, `text` empty, 10 of 10 turns | `reasoning`, 10 of 10 | the trace's own tokens |
| optiq | content only: 375–650 chars of answer, no reasoning text, 10 of 10 turns | `content`, 10 of 10 | the answer's own tokens |
| vmlx | reasoning only: 513–612 chars of trace, `text` empty, 10 of 10 turns | `reasoning`, 10 of 10 | the trace's own tokens |
| osaurus | reasoning only: 483–610 chars of trace, `text` empty, 10 of 10 turns | `reasoning`, 10 of 10 | the trace's own tokens |
| omlx | mixed: 4 turns a mirror of the trace (607/633/601/580 chars, `reasoning == text`), 5 turns a real answer with a 1–3 byte reasoning channel, 1 turn nothing at all | `reasoning` on turns 01/02/03/10, `content` on 04/05/07/08/09, neither on 06 | whichever stream arrived |

Read plainly: **three of the five columns spent the whole 128-token budget inside the reasoning
trace and never produced an answer** — at every turn, not just at the last one. Their decode rate
is the thinking phase's, and their TTFT is the first trace token. OptiQ's column is the answer
phase (its reasoning channel is empty in all ten turns), and oMLX's column does both, switching
between them mid-run. Decode tok/s and ITL are read off one stream's own two
timestamps and so remain one quantity across that boundary (Decision 122); **TTFT is not** — it is
a first-token latency, and the token it is first *of* differs by column.

### 2. Decode is flat across the ten turns on every column

**Axis — the runtime, with the format held constant (`oq4`) and one row per turn.** One cell per
column per turn, nine measured requests each. **Caveat — what this cannot read:** three columns are
timing a trace that never yields content and two are timing answers; the rates are like for like
within a row's own stream, and are not a claim that the runtimes were answering the dialogue the
same way.

| turn | mlxlm | omlx | optiq | vmlx | osaurus |
|---|---|---|---|---|---|
| 01 | 73.7 | 81.9 `R` | 74.2 | 68.1 | 50.6 `+27.1%` |
| 02 | 74.1 | 83.9 `R` | 73.5 | 67.5 | 60.9 `−13.6%` |
| 03 | 73.0 | 82.3 `R` | 72.4 | 66.7 | 56.1 `+10.2%` |
| 04 | 72.0 | **105.4** | 71.6 | 66.1 | 57.8 |
| 05 | 71.3 | 89.7 `+6.4%` | 71.3 | 65.9 | 58.4 `−6.3%` |
| 06 | 71.1 | **FAIL** | 71.0 | 65.4 | 52.9 `+21.5%` |
| 07 | 70.2 | 89.0 | 71.0 | 65.3 | 53.9 `+8.3%` |
| 08 | 70.6 | 88.3 | 71.1 | 65.8 | 53.5 `+11.8%` |
| 09 | 70.4 | 88.1 | 71.6 | 65.7 | 53.9 `+10.4%` |
| 10 | 70.2 | 82.2 `R` | 71.2 | 65.8 | 56.4 |

`R` marks a row the grid prints with its `reasoning timed` marker; a percentage beside a number is
the row's own drift marker (it moved more than 5% across its window). The other four columns do not
need the `R`: mlxlm, vmlx and osaurus are reasoning-timed on all ten turns and optiq is
content-timed on all ten. Every figure is `decode_tps` from the run's `leaderboard.md` /
`results.jsonl`, recomputed from the raw observations for this table. All cells `PASS` unless
named.

- **Within a column, decode barely moves.** mlxlm 70.2–74.1 (5.6% spread), optiq 71.0–74.2 (4.5%),
  vmlx 65.3–68.1 (4.3%): the model's per-token cost is set by the weights, not by a prompt that
  grows from 24 to ~1390 tokens.
- **oMLX's 28.7% spread is two phases, not one cell drifting.** Its reasoning-timed turns read
  81.9–83.9; its content-timed turns read 88.1–89.7, and turn 04 reads 105.4. Only one of those
  nine turns carries a drift marker (turn 05, +6.4%), so the range is the channel switch rather
  than movement inside a cell; turn 04's figure is explained in §5.
- **Osaurus is the one noisy column**: 50.6–60.9 with drift markers on eight of ten turns, up to
  +27.1% and down to −13.6%. Its answer rate is genuinely lower than the others', but no single
  turn of it should be read to a percent.
- **The run does not measure a conversation.** The history is fixed literals and, on three columns,
  no assistant text was ever generated at all; the "conversation" is the pinned prompt, which is
  what makes the comparison clean.

### 3. TTFT grows with history on every column — no prefix reuse is visible

**Axis — turn index within each runtime.** One cell per column, nine measured requests per turn.
**Caveat:** TTFT is the one metric that the channel split moves (see §1), so this table's
cross-runtime reading is limited to the four columns that are wholly one channel — and even there
it is a reading of "no reuse", not of which runtime prefills faster.

| runtime | prompt tokens t1 → t10 | TTFT p50 t1 → t10 (s) | ratio | slope (ms per prompt token), fit R² |
|---|---|---|---|---|
| mlxlm | 24 → 1393 | 0.234 → 2.172 | 9.3× | 1.37, 0.9974 |
| optiq | 26 → 1395 | 0.240 → 2.162 | 9.0× | 1.37, 0.9972 |
| vmlx | 19 → 1388 | 0.179 → 2.127 | 11.9× | 1.38, 0.9964 |
| osaurus | 24 → 1393 | 0.374 → 3.075 | 8.2× | 1.88, 0.9947 |
| omlx | 24 → 1429 | 0.362 → 2.832 | 7.8× | 1.72, 0.9848 |

(Least squares over the ten turns' medians; `omlx` excludes the turn-06 FAIL, which has no
comparable rate, and mixes both channels across its nine points.)

TTFT is linear in the prompt's token count on all five, with R² ≥ 0.985, over a 53–73× growth in
prompt length. The design's H1 predicted this shape for the two runtimes with no cross-request
prefix caching and a *flat* curve for those with it; every column landed in the non-caching band or
above it (8.2×–11.9× growth against a predicted 5–10× for the no-cache case).

That the three explicitly cache-off columns behave this way is the expected result — oMLX runs
`--no-cache`, vMLX `--disable-prefix-cache`, Osaurus a host prefix cache pinned false. What is not
expected is mlx-lm:

- mlx-lm's start command passes no prompt-cache flag when `cache_state` is not taken, so its LRU
  prompt cache is live at its default 10 entries. Its server logs (`results/logs/mlxlm-20260925T091430-41697.log`,
  `…T101438-…`) show the cache filling turn by turn — `Prompt Cache: 1 sequences, 0.07 GB` early,
  `10 sequences, 0.84 GB` by the end of each visit.
- **Not one request in either visit was served from it.** Each visit's log holds 154 and 144
  completed prefills and each walks the ten turns in order; within a turn the prompt is identical
  from request to request, and every one of those requests still logs a full prefill of its own
  length. The last turn's measured requests each prefill all 1393 tokens
  (09:22:11–09:22:31 and 10:21:46–10:22:06). mlx-lm's TTFT at turn 10 is 2.172 s against 0.234 s at
  turn 1, consistent with that.
- So the cache is occupied and the requests are not being served from it. **Why is not established
  by this record** — see Open questions. It is stated here because it is the one column where a
  prefix-reuse hypothesis had a live mechanism to work with and the measurement shows none.

### 4. Memory: the footprint grows more than the design's ceiling, and the growth is not the KV cache

**Axis — turn index within each runtime.** **Caveat:** `peak_mb` never ranks across runtimes (A7);
each row's memory reading is the higher-peak of its two visits, so this table is a per-turn maximum
rather than one continuous trajectory; and both instruments here are coarse — every `peak_mb` in
this run is a whole GiB (13, 14, 15, 19, 20, 21, 22, 26 GiB), and the `vmmap` readings move in
0.1 GiB (102.4 MB) steps. The design's 250 MB prediction sits between one and three quanta of
either instrument, which is worth knowing before the numbers are read.

| runtime | end-of-visit `vmmap` footprint t1 → t10 (MB) | growth | sampled `peak_mb` t1 → t10 | lifetime `vmmap` peak at t10 |
|---|---|---|---|---|
| mlxlm | 19763.2 → 20480.0 | +716.8 | 19456 → 21504 | 21913.6 |
| optiq | 19763.2 → 19968.0 | +204.8 | 26624 → 21504 | 26828.8 (flat all ten turns) |
| vmlx | 20889.6 → 20889.6 | 0 | 20480 → 21504 | 21811.2 |
| omlx | 20889.6 → 20992.0 | +102.4 | 20480 → 22528 | 22528.0 |
| osaurus | 13004.8 → 14233.6 | +1228.8 (t4 15462.4, t8 13414.4) | 13312 → 15360 | 16384.0 |

- The design's H4 ceiling of ≤250 MB holds for oMLX (+102.4) and vMLX (0), is at the edge for
  OptiQ (+204.8), and is exceeded by mlxlm (+716.8) and Osaurus (+1228.8, on a series that moves
  ±1.2 GB between adjacent turns).
- **The KV cache cannot account for it.** oMLX's own startup log records the model's KV geometry —
  `40 layers (10 KVCache), 2 KV heads, 16 Q heads, 256 head_dim. Estimated memory per 64-token
  block: 1.25 MB` — which is 20 KiB per token. The longest conversation adds ~1370 tokens over
  turn 1, i.e. ~27 MB of KV: an order of magnitude below the smallest measured growth. The growth
  in these readings is the allocator's, tracking the larger prefill graphs, and not the cache's.
- Two readings of OptiQ need their own note: its end-of-visit footprint *rises* 204.8 MB across the
  run while its sampled peak *falls* from 26624 to 21504 MB after turn 1 and its lifetime `vmmap`
  peak is 26828.8 MB flat on all ten turns. The first turn's visit contains the load transient; the
  per-turn sampled peak is the maximum within that turn's workload window, not the process's
  lifetime maximum (`measure.py` samples over one workload's window), and the lifetime figure is
  the one that shows the process never released its high-water page.

### 5. oMLX's column flips channel, and fails one turn

The grid prints `reasoning timed` on a row whose nine measured requests were all timed on the
reasoning stream. oMLX's rows carry that marker on turns 01, 02, 03, 06 and 10, and **no marker on
turns 04, 05, 07, 08 and 09** — five turns, not one. From the observations of the night run
(`results/multiturn/20260925T131430Z-runtime/results.jsonl`):

- **Turns 01/02/03/10**: `text == reasoning_text` (607/633/601/580 chars) — the runtime mirrored
  its trace into the content channel and hit the 128-token cap inside it. `transport.timing_channel`
  answers `reasoning` for a mirror, so the row is marked and its TTFT is the trace's first token.
- **Turns 04/05/07/08/09**: `reasoning_text` is one to three bytes of newlines and `text` carries a
  real answer (296/591/598/325/568 chars). The answer arrived on the content channel, so the row is
  timed on content and carries no marker. **This is the whole of turn 04's missing marker**, and
  the reason its 105.4 is not comparable with the 81.9–83.9 of the marked turns above it: it is a
  different stream measured the same way.
- **Turn 06 is a FAIL, and not a coherence failure.** All nine measured requests returned
  `ok=True` with `completion_tokens = 0`, a one-character text and a one-character reasoning text,
  `content_event_count = 1` and `ttft_s ≈ last_content_s` (a zero-length window). The harness's
  verdict is `still thinking: no content within max_tokens`, and the row's own notes read
  *excluded by coherence; not published: FAIL row … TTFT is time-to-completion, not
  time-to-first-token: 9 of 9 measured requests arrived whole in one content delta … n=0: decode
  tok/s, ITL and prefill tok/s omitted*. `coherence.NO_CONTENT` is its own verdict, not an
  incoherence verdict: the cell produced no language, which is why there is no rate and no drift
  figure for it either.

**Turn 04's 105.4 tok/s, specifically.** Its measured requests completed 70 tokens (of the 128
cap) in a 0.66–0.79 s window (`ttft 1.34–1.51 s`, `last_content 2.11–2.17 s`), with 8 content
deltas per request — a real, early-finished answer, and the fastest row in the oMLX column because
it is a short answer's rate on the same hardware. It is a legitimate row of the run: coherent,
`PASS`, nine samples, within-cell drift +0.02%. What it is not is the same quantity as the
marked turns above it, and the doc says so rather than letting a 105.4 sit unexplained in the
middle of a 82–90 band. (A summary of this column as "82–89" reads the eight turns in that band
and rounds turn-05's 89.7 into it; turn 04 is the ninth measured turn and reads 105.4.)

### 6. Where the results answer the design (plan 03-04, H1–H5)

- **H1, prefix caching decouples TTFT (flat, ±20%) for caching runtimes: refuted on every
  column.** All five grow 7.8×–11.9× with history, linearly (R² ≥ 0.985). Three columns had their
  caches explicitly off — the design's own "no caching" arm, whose predicted 5–10× growth matches
  what they show — and the two that had a cache available (mlx-lm's default LRU, and oMLX's, which
  is off by the harness's flag) show no reuse either. See §3 for the mlx-lm observation.
- **H2, decode within 5% of turn 1: holds for three of five.** mlxlm 5.6%, optiq 4.5%, vmlx 4.3%.
  It fails for oMLX (28.7%, or 9.5% if its content-timed turns are set aside) and for Osaurus
  (20.3%, with eight of ten turns carrying drift markers).
- **H3, ITL within 1.0 ms: holds for three of five.** mlxlm 0.76 ms spread, optiq 0.62, vmlx 0.64;
  oMLX 2.68 ms and Osaurus 3.35 ms exceed it, the same two columns H2 fails on.
- **H4, ≤250 MB footprint growth: not confirmed.** It holds for oMLX and vMLX, is marginal for
  OptiQ, and is exceeded by mlxlm (+716.8 MB) and Osaurus (+1228.8 MB) on the finer instrument —
  while the growth is an order of magnitude more than the KV cache the added history can account
  for, and both instruments move in steps larger than the 250 MB the hypothesis is stated in.
- **H5, 100% coherence and turn-responsive answers: half confirmed, half untestable.** The
  coherence floor passed everywhere there was language — no replacement characters and no
  mixed-script salad in any of the 50 measured cells (40 in the night grid, 10 in the Osaurus one)
  — and failed only as `NO_CONTENT` at oMLX turn 06. But
  "output tokens directly responsive to each turn's query" is not testable on this run: three
  columns never emitted an answer, OptiQ's were cut at the 128-token cap, and only oMLX's five
  content turns are answers at all.
- **The design's own protocol was not the one run**: fixed literal replies instead of live
  answers, and 128 tokens instead of 64. Both are the runner's, both are stated above, and the
  consequence of the second is that this study measured *thinking-phase* throughput on most of its
  columns.

### 7. Osaurus, alongside

Its column is a second sitting and cannot be joined (see "What ran"), so it is presented here as
its own grid's figures, from `results/multiturn-osaurus/grid.md`:

- decode 50.6–60.9 tok/s across the ten turns, the lowest column on every turn, with drift markers
  on eight turns: +27.1%, −13.6%, +10.2%, −6.3%, +21.5%, +8.3%, +11.8%, +10.4%.
- TTFT 0.374 → 3.075 s (8.2×), slope 1.88 ms per prompt token — the steepest of the five, so its
  TTFT at turn 10 (3.075 s) is the largest of the five, but 1.88 ms on a different channel is not a
  runtime comparison.
- Memory: 13.0 → 14.2 GB end-of-visit, peak 13312 → 15360 MB, lifetime peak 16384.0 MB — all far
  below the other columns, and all unrankable against them (A7).
- Coherence: 10 of 10 turns PASS, reasoning-timed throughout, like mlxlm and vmlx.
- The sitting was ~2.2 hours after the night's four columns, on a machine that had run the KV sweep
  until 12:30 that morning. Nothing in the record attests the machine's state during either block;
  the Osaurus column's *levels* are the ones most exposed to that, and its own drift markers say
  the same thing from inside the column.

## Open questions

1. **Why does mlx-lm's default prompt cache not shorten TTFT?** Its cache fills to 10 sequences,
   its prompt length grows monotonically, and its turn-10 request still logs a full 1393-token
   prefill. Either the server's reuse path is not reached by this request shape, or the cache's
   entries do not match the next turn's prefix. One instrumented request pair would answer it, and
   the answer changes how every cache-state reading on this runtime should be interpreted.
2. **Is 128 tokens the right cap for a thinking model?** At 128, three of five columns never
   produced an answer and one turn failed with `NO_CONTENT`. The design's H5 wants answers; a cap
   that lets the trace *and* the answer land (or a two-phase design that measures them separately)
   is the cheapest fix, and the harness already separates the two streams by timing channel.
3. **Does the grid need to distinguish a mixed-channel column from a content-timed one?** oMLX's
   rows are marked on five turns and unmarked on five; the unmarked ones read like OptiQ's, which
   is a different measurement. This is a rendering question, not a data one — the channel is in
   every row's `timing_channel`.
4. **Should Osaurus get a same-night grid, or the grid a supersede rule?** The duplicate-cell
   refusal is doing its job (a cell measured twice is ambiguous, not superseded), and the cost is
   that one runtime's column lives in a second document from a second sitting. A re-run on the same
   quiet night is the honest fix; changing the guard is Jason's call.
5. **What produced Osaurus's drift markers?** Eight of its ten rows carry one, and they do not tell
   one story: six say *"it was still warming up as it was measured … insufficient warmup, not a
   thermal effect"* (+27.1%, +21.5%, +11.8%, +10.4%, +10.2%, +8.3%) and two say *"it was slowing
   down as it was measured — the thermal curve"* (−13.6%, −6.3%). On one column, in one sitting, the
   window caught a cell that had not settled and another that was losing speed. A longer warmup
   plateau on that runtime, or a different turn order, would say whether the column's level is
   stable at all.
6. **Peak memory at these conversation lengths is not a measurable quantity with this instrument.**
   Whole-GiB steps (and 0.1 GiB on the cross-check) against KV arithmetic of ~27 MB for the whole
   ten-turn history: H4 as written cannot be settled by this harness. Either the hypothesis is
   restated in units the sampler can see, or the sampler is probed for finer resolution.

## What this cannot claim

- **No cross-runtime TTFT or E2E ordering on any turn where the columns' channels differ** — and
  on this run that is most turns, with oMLX switching channel mid-column (Decision 122).
- **No statement about answer quality or correctness.** Coherence is a floor; no turn of any column
  was scored for whether it answered the question, and three columns produced no answer text at
  all.
- **No memory ranking across runtimes.** `peak_mb` does not charge the same pages in every runtime
  (A7); every memory statement above is a change within one column.
- **Nothing about a real conversation.** The assistant turns are fixed literals, so no runtime's
  output ever entered the history; turn N is the same prompt everywhere.
- **No same-night Osaurus comparison.** Its column is a separate grid from a separate sitting, and
  the duplicate-cell rule is why it is presented alongside rather than joined.
- **Not a context-length study.** The prompt grows as a side effect of the dialogue; the turn index
  is a conversation axis, not the `prompt_tokens` pin, and the figures here should not be compared
  with the 16k/32k KV sweep's.

---

## Addendum (2026-09-25, later the same day): why mlx-lm's prompt cache never hit — Open question 1, answered from source

Written after the grid closed, against the mlx-lm 0.31.3 the run actually used
(`~/.local/share/ohyesmlx/mlx-lm-0.31.3/lib/python3.14/site-packages/mlx_lm/_version.py` →
`"0.31.3"`, the venv `scripts/run_multiturn.sh` puts on `PATH`) and the two mlx-lm visit logs of
this run. No code changed, no server, model or tensor was touched; every claim below is a line
citation or a line of those logs. Citations are relative to the package root:
`server.py` = `mlx_lm/server.py`, `models/cache.py` = `mlx_lm/models/cache.py`.

### The answer

Two facts. Either alone makes every request a full prefill; together they close every branch
`fetch_nearest_cache` has.

1. **The run never entered the server's batched path, so nothing was ever stored at a prefix.**
   Every request carried `seed: 0` (`ohyesmlx/measure.py:165`'s `SEED = 0`, in the header at `:544`
   and on every request at `:1073`; sent by `transport.py:181-182`), and the server's gate is
   `model_provider.is_batchable and args.seed is None` (`server.py:685-686`) — a pinned seed routes
   every request to `_serve_single` (`server.py:813-815`). That path inserts **once** per request,
   at the end of generation (`server.py:1019-1021`), keyed by `cache_key`, which starts as the whole
   prompt (`server.py:969`) and is appended with every generated token (`server.py:1006`), stored
   with the default `cache_type="assistant"`. The per-segment snapshots — the only place this
   server ever creates a *prefix-keyed* entry — exist **only in the batched path**
   (`server.py:864-880`) and are never reached. The cache therefore holds ten keys of the form
   `prompt_k + completion_k`, one per turn, and no key that is a prefix of any request.

2. **The one fetch branch that could have served a request from a longer stored key is closed by
   the model's cache type.** `fetch_nearest_cache` (`models/cache.py:1674-1694`) serves a `longer`
   entry only under `can_trim_prompt_cache` (`:1683`), which is
   `all(c.is_trimmable() for c in cache)` (`:88-92`) and a trim. `Qwen3.6-35B-A3B-oQ4` declares
   `model_type: qwen3_5_moe` with `full_attention_interval: 4`: 30 of its 40 layers are
   `linear_attention`, and `make_cache` is
   `[ArraysCache(size=2) if l.is_linear else KVCache() for l in self.layers]`
   (`models/qwen3_5.py:304-305`, `is_linear` at `:212`; the MoE `Model` inherits it,
   `models/qwen3_5_moe.py:6`/`:21`, `models/qwen3_5.py:522-523`). `ArraysCache`
   (`models/cache.py:594-728`) implements `merge`, `extract`, `filter`, `extend`, `prepare`,
   `finalize`, `advance` — and **neither** `is_trimmable` nor `trim`, so it inherits the base
   `False` (`:146-147`). One `ArraysCache` in the list makes the predicate false for the whole
   cache; the branch is skipped, `short_length` is 0, and the function falls through to
   `return None, tokens` (`:1694`). Full prefill, every request.

### How the key and the reuse decision work, exactly

`PromptTrie.search` (`models/cache.py:1578-1620`) walks the request's tokens down the trie and
returns three things at once: `exact` (a stored key equal to the query), `shorter` (the deepest
stored key that is a *prefix* of the query — noted only when it ends at token index > 0, `:1602`),
and `longer` (the shortest stored key that extends *past* the point where the walk left the trie),
with `common_prefix` = how far the walk got. `fetch_nearest_cache` then tries them in that order:
an exact hit is served whole (`:1676-1678`); a `longer` hit, when it reaches deeper than `shorter`,
is served by **trimming the stored cache back** to `common_prefix` (`:1681-1688`) — the only
branch that needs a trimmable cache; a `shorter` hit is served with **no trimming at all**
(`:1690-1692`); everything else is `None, tokens` (`:1694`).

For the multi-turn conversation, every request was a miss on all three:

- **`exact`**: impossible by construction. Keys carry the turn's own 128 generated tokens, and the
  next turn's prompt carries the *fixed literal* reply in their place (this run's deliberate
  design), so the query is never a stored key.
- **`shorter`**: nothing to find, by fact 1 — no stored key is a prefix of anything.
- **`longer`**: this is the one with a live candidate. Turn N's prompt and turn N−1's key share
  their whole history prefix (the template renders the shared messages identically even though the
  message indices shift, `chat_template.jinja`'s `last_query_index` branch), and they diverge
  exactly where turn N−1's generation prompt had `<think>` and turn N has the literal reply. So the
  walk stops there with `common_prefix` ≈ `len(prompt_{N-1}) − 2`, `shorter` is `None`, and
  `longer` is turn N−1's key — `common_prefix > short_length` is true, and the branch is taken
  right up to `can_trim_prompt_cache`, which is `False` (fact 2). The repeat requests *within* a
  turn are the same case with `common_prefix` = the whole prompt: the stored key is a strict
  extension of the query, servable only by trimming (`prefix = min(len(tokens) - 1, common_prefix)`,
  `:1685`), and it is not trimable.

**Why the count grows one per turn and stops at 10.** Every request of a turn repeats the same
prompt, and at `temperature 0.0` the server is greedy (`make_sampler` returns `argmax`,
`sample_utils.py:46-47`), so it reproduces the completion exactly —
turn-02's 24 warmups and 9 measured requests hold one distinct `reasoning_text` and 128 completion
tokens each — and therefore the same `prompt + completion` key is *replaced* rather than added
(`insert_cache`, `models/cache.py:1712-1717`). Ten turns produce ten distinct keys; the cache's
`max_size` is its default 10 (`server.py:1871-1876`; `cache_state` was not taken, so the harness
passed no `--prompt-cache-size`, `ohyesmlx/runtimes.py:1551-1575`), and eviction
(`models/cache.py:1728-1732`) never fires because the count never exceeds 10.

### What the run's own logs show

- **Every one of the 154 (visit 1) and 144 (visit 2) requests printed `0/<its full prompt
  length>`** as its first progress line, then `<N−1>/N`, then `N/N` (`0/24`, `23/24`, `24/24` at
  turn 1; `0/1393`, `1392/1393`, `1393/1393` at turn 10). That shape is `stream_generate`'s own
  callback: `prompt_progress_callback(0, total)` at `generate.py:429`, then the prefill loop, which
  holds the last token back for the first `_step` (`:430-453`), then `(total, total)` when
  generation begins (`:463`). The batched path never calls it — it forwards
  `PromptProcessingBatch.Response.progress` (`generate.py:1824-1836`), whose first element is the
  tokens consumed by a chunk of at least one, so a batched request cannot print `0/N` at all. The
  two visits are therefore both sequential-path runs, which is what the seed pin predicts.
- **The denominators are the *stripped* prompt**: `_serve_single` passes `prompt=rest` into
  `stream_generate` (`server.py:976-980`) and the callback's `total` is `len(rest)`
  (`generate.py:425-427`). A fetch that served a prefix of P tokens would print `0/(N−P)`. Every
  request printed the full length.
- **Every `Prompt Cache` line in both visits reads `user: 0 sequences` and `system: 0 sequences`**
  (`_log_cache_stats`, `server.py:461-470`) — the app-side tell that the segment-boundary inserts
  never ran — and the total walks 0 → 1 → … → 10, one step per turn, ~15 requests at each level.
- The record cannot show any of this itself: the server reports the served prefix as
  `usage.cached_tokens` (`server.py:1344-1346`), and the harness's `Observation` does not carry
  that field. The logs are the artifact that holds it.

### What would have changed it (source predictions, not measurements)

- **A batchable request.** With `seed` omitted, `_is_batchable` is true for this model — every
  cache in `make_prompt_cache` has `merge` (`ArraysCache.merge`, `models/cache.py:702`; the gate at
  `server.py:370-374`) — and the batched path's boundary insert would store a snapshot keyed by the
  end of the prompt's first segment. For this conversation that key is the history up to
  `…<|im_start|>assistant\n`, which *is* a strict prefix of the next turn's prompt, so the trie
  would return it as `shorter` and `fetch_nearest_cache` would serve it **without any trim** (the
  trim branch is not even consulted: there `common_prefix == short_length`). The segmentation that
  produces it: `tokenizer.has_thinking` is true (the artifact declares `<think>`/`</think>` as added
  tokens, ids 248068/248069, which is what `_infer_thinking` reads, `tokenizer_utils.py:260-273`),
  so `_tokenize` splits the prompt into `[history + generation prompt − think tail, think tail]`
  (`server.py:580-624`). Not measured — it is a reading of the code path this run never took.
- **A model whose cache is trimmable** (no `ArraysCache` in the list — a plain-attention artifact).
  The sequential path would then serve turn N out of turn N−1's key through the trim branch,
  resuming at the shared history prefix, and the same-prompt repeats would be served at
  `len(prompt) − 1`. This is the prediction `docs/research/2026-09-17-cache-state-split.md` already
  holds open (its Open question 1); nothing here was run to test it.
- **A correction of emphasis to the 06-02 document.** Its "the segment-boundary insert
  (`server.py:864-879`) never fired for this prompt" is true but for a stronger reason: with a seed
  pinned, the batched path that contains that insert is never entered at all, so it could not fire
  for *any* prompt in those runs — and their logs carry the same `0/4106` sequential-path
  signature. The flag was live in both states and storing, as that document says; the insert was
  simply unreachable.

### What this does not establish

- Nothing about a batchable run on this artifact was measured; the two predictions above come from
  source and are testable only by a run (no `seed` pin for the first; a non-hybrid artifact for the
  second).
- The low-level details of how the tokenizer renders `…assistant\n<think>\n` (token counts and the
  exact split point) are read off the template and the added-token table, not from a tokenized
  request.
- Whether `ArraysCache` could be made trimmable (it would need the linear-attention state
  snapshotted at a previous length, which the class does not keep) is a question about mlx-lm's
  design, not about this run.
