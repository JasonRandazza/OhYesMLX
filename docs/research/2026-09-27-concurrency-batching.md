# Concurrency at four batch widths on five runtimes: the 2026-09-16 "none of them batch" finding was the caps' — three harness flags, the seeded path and Osaurus's host sequence setting — and lifting them buys 1.45–1.72× aggregate on `decode` at ~80% off each request's own rate

**Date:** 2026-09-27 — the seedless sweep 02:56 → 09:56 EDT; the uncapped re-run 12:40 → 15:50 EDT, stopped there and resumed for one cell 19:03 → 19:38 EDT; the Osaurus sequence-cap sweep 20:34 → 21:56 EDT.
**Study:** v3.1 — Decision 128 (no request seed at temperature 0) then Decision 129 (the runtime batch caps follow the run's `concurrency`; `8899b3a` extended it to Osaurus's host key); the second pass over Phase 6's plan 06-01 concurrency sweep, following `docs/research/2026-09-16-concurrency-omlx.md`, whose conclusion this paper supersedes.
**Harness:** 0.3.0 — `source_sha256 423650119dedde78f0873873e3aa41653999eec59001f4cf16242ab4b5748b92` for all twenty run directories under `results/sweep-conc-seedless`, and `6968456b730692c642201632055cfe3271d07db0df2afeb04458cde8f08427a2` for all twelve under `results/sweep-conc-uncapped` and all four under `results/sweep-conc-osaurus-seqs` — uniform within each sweep, from the joins' own provenance lines.
**Runner:** `scripts/run_sweep_concurrency.sh` (`RUNTIMES=`, `OUT=`), one run per (runtime, N); each runtime's four runs joined by `ohyesmlx.cli sweep --varying concurrency` into that directory's `sweep-oq4__<runtime>.md`. The sequence-cap sweep is the same runner with `RUNTIMES=osaurus` and `OUT=results/sweep-conc-osaurus-seqs`, each cell's cap written by `osaurus_set_seqs` before its run (§4).
**Subject:** `RepublicOfKorokke/Qwen3.5-4B-oQ4` — 3,160,559,814 bytes, the same artifact directory in every one of the 108 rows — on mlx-lm 0.31.3, oMLX 0.6.4, OptiQ 0.5.13, vMLX 1.6.59 and Osaurus 0.25.13.
**Author:** Command Code implementer (the write-up); the runs are the coordinator's.

## Why this run exists

The 2026-09-16 paper published one of the project's load-bearing findings: **not one of the five runtimes gains
throughput from eight simultaneous requests.** Its decode-workload table reads mlx-lm 1.15×, oMLX 1.02×,
mlx-optiq 1.01×, vMLX 1.01×, Osaurus 1.01× at N=8 against each runtime's own N=1, with four of the five flat
inside 2%, every batch span ~8× a single request's, and TTFT growing in proportion — serialization, not
batching, and "concurrency is pure latency cost" on all five. That finding was wrong about all five — the three
harness flags, the seed route and Osaurus's host default — and the reason is configuration rather than the engines:

- **The request seed.** Every run in that grid sent `seed 0`. In mlx-lm the seed is the gate on the serving
  path: a seeded request bypasses `BatchGenerator` and is served sequentially (`mlx_lm/server.py:685-686`),
  and OptiQ routes with it, so **their concurrency columns measured a path everyday clients never take**
  (Decision 128). The older columns' own tell is in the 09-16 paper: mlx-lm's *per-request* rate rose
  67.0 → 77.1 while its aggregate rose, which the paper correctly called impossible under real batching —
  it was a seeded sequential runtime happening to run fast.
- **The concurrency caps.** Since `b1fc311` the harness hard-coded oMLX `--max-concurrent-requests 1`, OptiQ
  `--max-concurrent 1` and vMLX `--max-num-seqs 1` into their start commands, so on those three every
  N>1 cell admitted one request at a time no matter what the client sent (Decision 129). The harness measured
  its own cap.
- **Osaurus's host default.** `~/.osaurus/config/server-runtime.json` ships `concurrency.continuousBatching:
  true` with `concurrency.maxConcurrentSequences: 1`, so the engine admitted one sequence at a time; no flag
  exists for it. The sequence-cap sweep sets that key to the run's N (§4) and the flat column becomes a
  batching ladder — 1.59× aggregate on `decode` at N=8 against the same runtime's N=1.

All three are addressed. Decision 128 removed the request seed at temperature 0 (`Runtime.request_seed` returns
`None`; `b820bda`), where it changes no token and where a seeded request is not what a client sends. Decision 129
made each cap `str(concurrency)` (`47cccb5`), with the N=1 commands byte-identical so no earlier grid shifts. The
Osaurus cap is not one of the three flags and not a flag at all: it is the host setting
`concurrency.maxConcurrentSequences`, which ships at 1, which the sequence-cap sweep sets to the run's N
(`osaurus_set_seqs`, `8899b3a`) and restores byte-exact — and at N≠1 it batches (§4).

This paper is the re-run, in three sweeps, same runner, same artifact, same pins, one variable each:

- `results/sweep-conc-seedless/` — **Decision 128 alone**: all five runtimes, seedless, caps still 1.
- `results/sweep-conc-uncapped/` — **Decision 129**: oMLX, OptiQ and vMLX with caps = N.
- `results/sweep-conc-osaurus-seqs/` — **the host setting**: Osaurus alone, `concurrency.maxConcurrentSequences`
  = the run's N (the host ships 1), 20:34 → 21:56.

The result in one paragraph: the capped columns reproduce 09-16's shape. Uncapped — and, on the seedless
path, mlx-lm too — all four decode like a batching server: per-request rate down ~78–82% at N=8, aggregate up
**1.45–1.72×**, TTFT up 4–7× instead of 8–148×. Osaurus does the same once its host key is at N: per-request
down 80.6% on `decode`, aggregate up **1.59×**, TTFT 0.306 → 1.439 s (§4); the flat column is the shipped
default of 1, not a fixed engine. On the prefill workload, oMLX and vMLX still do not gain aggregate even
uncapped (§5), and Osaurus at cap = N joins them (18.1 → 21.3, ×1.18, §4). **mlx-lm and OptiQ joined them
on 2026-09-29: the rows this paper first printed for them on `prefill` (aggregate 61.1 → 96.1 and 57.3 → 74.8,
TTFT 0.15–0.19 s) were prompt-cache hits, and with the cache off they read flat too — see the correction below.**

## Correction, 2026-09-29: mlx-lm's and OptiQ's `prefill` rows were prompt-cache hits

**Axis — `concurrency`, with `cache_state` now off.** Decision 130. On the seedless path, mlx-lm and OptiQ ran
with `--prompt-cache-size` unpassed, which leaves mlx-lm's default LRU prompt cache (10) on, and the batched
path caches prefix segments (`docs/research/2026-09-28-seedless-validation-grids.md` §2.2). The `prefill`
workload repeats one ~1,320-token prompt, so from the second request on every request was served from the
cache: 1,320 tokens in 0.15–0.19 s is not a prefill. The harness now passes `--prompt-cache-size 0` unless
`cache_state` is pinned `on` (`runtimes.prompt_cache_flags`), and mlx-lm and OptiQ were re-run alone into
`results/sweep-conc-cacheoff` (2026-09-29 07:32 → 10:03 EDT, harness `6f36eb98`, all eight cells exit 0, one
session, mlx-lm `1 2 4 8` then OptiQ `8 4 2 1`). oMLX, vMLX and Osaurus already ran cache-off and are unchanged.
The header still records `cache_state: null` on both sides, so the join guard cannot tell these runs from the
cache-on ones; they are their own directory and no table here is a join across the two.

`prefill` (64), cache off — the rows that replace §1's and §5's mlx-lm and OptiQ `prefill` figures:

| runtime | metric | 1 | 2 | 4 | 8 | N=8/N=1 |
|---|---|---|---|---|---|---|
| mlx-lm | per-request decode tok/s | 78.4 | 44.1 | 25.4 | 13.9 | 0.18× |
| | aggregate tok/s | 20.6 | 21.8 | 22.8 | 22.3 | **1.08×** |
| | TTFT p50 s | 2.294 | 4.414 | 8.703 | 17.411 | 7.6× |
| OptiQ | per-request decode tok/s | 73.0 | 31.1 | 19.4 | 10.2 | 0.14× |
| | aggregate tok/s | 15.3 | 12.5 | 17.6 | 17.7 | **1.16×** |
| | TTFT p50 s | 2.441 | 5.943 | 7.853 | 15.377 | 6.3× |

against the cache-on rows they replace: mlx-lm aggregate 61.1 → 96.1 (×1.57), TTFT 0.152 → 1.017 s; OptiQ
57.3 → 74.8 (×1.31), TTFT 0.188 → 1.467 s. With the cache off both runtimes sit where oMLX (×1.02), vMLX (×1.17)
and Osaurus at cap = N (×1.18) already sat: N=1 TTFT ~2.2–2.9 s, aggregate ~15–23 tok/s, flat across the ladder.
OptiQ's N=1 cell is flagged +10.9% still-warming (early → late per-request median, its own leaderboard note),
which is why its ratio is the least firm of the six; mlx-lm's `prefill` cells are all within ±2.0%.

**What this changes.** The three-way split §5 describes ("~2–3 s vs ~0.15–0.19 s N=1 TTFT ... present on three
runtimes") is gone: it was the cache, not a runtime property, and all five runtimes read a ~2.2–2.9 s prefill of
this prompt at N=1. What §5 said about oMLX and vMLX stands, and now describes all five: the decode leg of this
shape batches (per-request decode collapses 81–86% at N=8 on all five, Osaurus at cap = N) while the completion aggregate
barely moves, because the wall time is the prompt leg.

**What survives.** The headline. `decode`-shape aggregate at N=8 against N=1, cache off: mlx-lm 65.6 → 110.7
(**1.69×**, was 1.72×), OptiQ 65.3 → 108.0 (**1.65×**, was 1.65×). `chat` reads 65.5 → 100.6 and 57.9 → 98.7. The
cache also touched the short prompts a little: N=1 TTFT p50 on `chat` and `decode` is 0.224 and 0.253 s for
mlx-lm (was 0.145 and 0.147) and 0.268 and 0.273 s for OptiQ (was 0.155 and 0.188), so §1–§4's small-prompt TTFT
columns for these two runtimes were partly cache time as well; their ratios, and the decode rates, were not.

**One observation this re-run adds and does not explain.** OptiQ at N=2 is the odd cell: its per-request
decode is 30.1 / 30.7 / 31.1 on `chat` / `decode` / `prefill` (cache-on N=2: 45.4 / 44.7 / 48.0), so its N=2
aggregate (52.5 / 56.4 / 12.5) is below its own N=1 on all three shapes (57.9 / 65.3 / 15.3), before N=4 recovers to 90.8 / 97.8
/ 17.6. It is the same on all three workloads, so it is not one cell's warmup, and Decision 129's rule
(prompt concurrency `max(1, N//4)`) gives OptiQ the same setting at N=2 as before. **Repeated 2026-09-29 (13:18 → 13:29 EDT, `results/optiq-n2-repeat`, N=2 alone, cache off, all
three shapes PASS): the dip did not recur.** Per-request decode was 44.9 / 42.3 / 45.6 tok/s on `chat` /
`decode` / `prefill` (first cache-off run 30.1 / 30.7 / 31.1; cache-on 45.4 / 44.7 / 48.0) and aggregate
76.6 / 75.0 / 16.3 (first run 52.5 / 56.4 / 12.5), drift within ±2.7% on every shape. So the first run's N=2
cells were a session or ordering effect — they ran after N=8 and N=4 in the same session — not the
cache-off flag and not an N=2 scheduling quirk; the cause of the first run's low cells is not identified
beyond that. Use the repeat's N=2 figures for OptiQ; the first run's N=2 cells stay in the record. Every
observation in the repeat carries `cached_tokens: 0` (54 of 54), the first live reading of that field on
OptiQ: the cache was off, as pinned.

## What ran

**The seedless sweep** — all five runtimes, caps still 1, seedless, one artifact `oq4`:

| runtime | N order | wall clock (EDT) | run directories, in that order (`20260927T…Z-format`) |
|---|---|---|---|
| mlx-lm | `1 2 4 8` | 02:56:24 → 03:52:42 | `065624 070250 071157 072639` |
| oMLX | `8 4 2 1` | 03:52:53 → 05:25:54 | `075253 084132 090616 091905` |
| OptiQ | `1 2 4 8` | 05:26:04 → 06:44:54 | `092605 093214 094307 100405` |
| vMLX | `8 4 2 1` | 06:45:05 → 08:17:59 | `104505 113328 115814 121106` |
| Osaurus | `1 2 4 8` | 08:18:09 → 09:56:14 | `121810 122535 123906 130511` |

**The uncapped sweep** — oMLX, OptiQ, vMLX, caps = N:

| runtime | N order | wall clock (EDT) | run directories, in that order |
|---|---|---|---|
| oMLX | `1 2 4 8` | 12:40:44 → 14:11:05 | `164044 164932 170405 172729` |
| OptiQ | `8 4 2 1` | 14:11:16 → 15:07:28 | `181116 183903 185251 190115` |
| vMLX | `1 2 4 8` | 15:07:38 → 15:50:10 | `190738 191652 192856` |
| vMLX N=8 | — | 19:03:02 → 19:38:06 | `230302` |

Wall clocks are the runner's own (`runner.log` in each sweep, an exec-owned redirect). The uncapped sweep's
run of vMLX **N=8 was stopped with it**: the runner's trap wrote `ABORTED 15:50:16` and swept the ports; the
Mac had to be moved (the coordinator's reason, not a defect in any measured cell), and vMLX N=8 was then run
alone at 19:03:02–19:38:06 — the runner.log line says `(resumed after the 15:50 stop)`. The joins written by
that second session include it, so the uncapped vMLX ladder is three cells from one session and its N=8 from
another, 3 h 13 m later. Run directory names are the same instants in UTC under
`results/<sweep>/oq4__<runtime>/`.

**The sequence-cap sweep** — Osaurus alone, `concurrency.maxConcurrentSequences` = the run's N (the host ships
1), caches off and idle residency 900 s as in every Osaurus cell:

| runtime | N order | wall clock (EDT) | run directories, in that order (`20260928T…Z-format`) |
|---|---|---|---|
| Osaurus | `1 2 4 8` | 20:34:28 → 21:55:54 | `003428 004311 005619 011729` |

It is contiguous, one session, no stop or resume: the runner re-recorded the cap-1 baseline for the N=1 cell,
wrote the key before each of the other three (`osaurus server-runtime.json:concurrency.maxConcurrentSequences
= N (baseline re-recorded)`, `runner.log`), and closed with `osaurus settings restored byte-exact (cmp)`
before the 21:56:00 join.

**Pins every run in a sweep shared**, from the joins' shared-pins line, verified field by field by the join
guard: temperature `0.0`, seed `—` (the policy; every row records `request_seed: null`), warmup
`{cap: 20, floor: 10, mode: plateau, plateau_pct: 3.0, window: 5}`, measured `9`, cooldown `30.0` s, and
`prompt_tokens`, `cache_state`, `kv_quant`, `mtp_depth`, `stream_experts` all not taken. Workloads `chat`
(max_tokens 128), `prefill` (64) and `decode` (512), identical messages in all 36 runs — the same three
shapes the MTP paper of 2026-09-25 ran, down to the benchmark-design question and the engineering standard.
The sequence-cap sweep's four runs carry the same shared-pins line.

**Each cell is 9 measured batches** — a batch is N requests issued together, so a cell publishes summaries
over 9 requests at N=1 and 72 at N=8 (`n = 9 / 18 / 36 / 72` in the rows), warmups excluded. **All 108 rows in
the three sweeps are `PASS`**, `floor coherence pass`, `floor metrics pass`; no cell in this paper is a `FAIL`,
`N/A` or `no value`, and the coherence gate — language on every measured cell — is the floor every number
here cleared.

**Timing channels.** Every mlx-lm, oMLX, vMLX and Osaurus row in all three sweeps carries `timed on reasoning
channel`; every OptiQ row is content-timed. So a TTFT, ITL or decode figure is channel-dependent *across*
runtimes (Decision 122 lists `ttft_p50_s` and `prefill_tps` as `CHANNEL_DEPENDENT_RANKS`), and this paper
draws no cross-runtime ordering from one. Within a runtime the four N columns are one channel, and that is
the comparison every result below is.

## Conditions

- **Three sessions, one day.** The seedless sweep is 02:56 → 09:56, the uncapped one 12:40 → 15:50 plus the
  19:03 cell, and the sequence-cap sweep 20:34 → 21:56, Osaurus alone. Within-sweep N-vs-N comparisons are the
  results; a capped-vs-uncapped or cap-1-vs-cap-N pair is two sessions, and a cross-runtime level is six
  windows in one day's sequential sessions, not a ranking.
- **The N=1 state is the same in all three sweeps** — Decision 129 made the N=1 start commands byte-identical,
  and the sequence-cap sweep re-recorded its N=1 with the key at the host's 1 — and the measurements of it
  differ by up to 8.9% on the four runtimes run twice: oMLX prefill per-request 107.9 (seedless) → 98.3
  (uncapped) and decode 75.7 → 69.1, vMLX chat 73.6 → 69.4. Osaurus's third measurement is its own: `decode`
  63.5 / 60.3 / 0.306 against the seedless 67.3 / 64.8 / 0.288 (5.6%) is inside that bar, while its `chat` and
  `prefill` N=1 pairs are the flagged still-warming rows of §6. That spread is the session bar for any
  cross-sweep reading, and the reason §1's side-by-side is at N=8/N=1 ratios rather than at raw levels.
- **What each cap does.** oMLX's `--max-concurrent-requests` feeds both `SchedulerConfig.max_num_seqs` and
  the BatchGenerator's `completion_batch_size` (`settings.py:1710-1712`) and admission gates on it
  (`scheduler.py:9979-9982`). OptiQ's `--max-concurrent N` is injected as `--decode-concurrency N` and
  `--prompt-concurrency max(1, N//4)` unless those flags are passed (`cli.py:2937-2945`), so its ladder runs
  decode/prompt 1/1, 2/1, 4/1, 8/2; mlx-lm takes no concurrency flag from the harness at all, and Osaurus's
  cap is not a flag but the host setting `concurrency.maxConcurrentSequences`, which the sequence-cap sweep
  sets to the run's N and restores byte-exact (§4).
- **Order and direction.** The runner alternates N direction per runtime so thermal drift cannot alias onto
  the pin: ascending for mlx-lm, OptiQ and Osaurus, descending for oMLX and vMLX, in the seedless sweep; oMLX
  ascending, OptiQ descending, vMLX ascending in the uncapped one; and Osaurus ascending, contiguous from
  20:34 to 21:56, in the sequence-cap one. The uncapped vMLX N=8 cell is both the
  largest N and the last measurement, and it is separated by the resume, which cuts both ways and is why its
  own drift reading matters (it is +0.3%, §6).
- **Osaurus is pinned around its cells** by `scripts/osaurus-pin.sh` (prefix and blockDisk caches off,
  `modelIdleResidencyPolicy.seconds` 900) and restored byte-exact with `cmp` afterwards; its engine settings
  live in `~/.osaurus/config/`, the harness passes no flag because there is none, and its one concurrency
  setting — `concurrency.maxConcurrentSequences` — sits at the host's `1` in every cell of the first two
  sweeps and is set to the run's own N in the sequence-cap sweep, then put back byte-exact (§4).
- **Warmup and drift at N>1.** Warmup settles on aggregate throughput; a row's `drift %` reads per-request
  rates, and the joins print the sentence beside every table: at concurrency > 1 a positive drift means the
  per-request rate was still moving, not that the cell was under-warmed. The rows' own annotation of a
  positive change uses report.py's generic wording ("insufficient warmup, not a thermal effect"); both are
  readings of the same observation — a per-request series that had not stopped moving when the window
  closed — and §6 lists every row where the direction is that visible.
- **Nothing attests the host's state** during any of the three sweeps. The harness cannot detect contention, and the
  runner swept ports and stale Osaurus apps before and after every cell as it always does.

## Results

### 1. Capped vs uncapped side by side: same runtime, same N, two different answers

**Axis — `concurrency`, and the harness's handling of it.** The capped columns are the seedless sweep (caps
1, Decision 128 only); the uncapped columns are the Decision 129 re-run. Both are one artifact, one machine,
one day, and the same four pins otherwise. **Caveat:** the N=1 baselines differ by up to 8.9% between the
sessions (Conditions, above), and the ratio column carries that; the load-bearing rows are named.

`decode` workload, per-request decode tok/s (the join's `decode_tps`; `results/sweep-conc-{seedless,uncapped}/sweep-oq4__<runtime>.md`):

| runtime | cap | N=1 | N=2 | N=4 | N=8 | N=8/N=1 |
|---|---|---|---|---|---|---|
| oMLX | 1 (seedless) | 75.7 | 73.7 | 73.3 | 73.1 | 0.97× |
| oMLX | = N (uncapped) | 69.1 | 44.6 | 25.5 | 12.4 | **0.18×** |
| OptiQ | 1 | 68.9 | 69.1 | 69.3 | 69.1 | 1.00× |
| OptiQ | = N | 67.4 | 44.7 | 26.6 | 14.6 | **0.22×** |
| vMLX | 1 | 71.4 | 71.7 | 72.2 | 72.2 | 1.01× |
| vMLX | = N | 68.5 | 41.1 | 25.2 | 14.0 | **0.20×** |

`decode` workload, aggregate tok/s:

| runtime | cap | N=1 | N=2 | N=4 | N=8 | N=8/N=1 |
|---|---|---|---|---|---|---|
| oMLX | 1 | 71.5 | 71.6 | 72.2 | 72.2 | 1.01× |
| oMLX | = N | 65.2 | 85.2 | 95.0 | 94.4 | **1.45×** |
| OptiQ | 1 | 67.3 | 67.7 | 68.2 | 68.1 | 1.01× |
| OptiQ | = N | 65.6 | 84.6 | 98.7 | 108.2 | **1.65×** |
| vMLX | 1 | 69.9 | 70.1 | 70.5 | 70.5 | 1.01× |
| vMLX | = N | 65.1 | 80.3 | 81.4 | 107.1 | **1.65×** |

`decode` workload, TTFT p50 s:

| runtime | cap | N=1 | N=2 | N=4 | N=8 | N=8/N=1 |
|---|---|---|---|---|---|---|
| oMLX | 1 | 0.399 | 3.903 | 10.898 | 25.187 | 63.1× |
| oMLX | = N | 0.426 | 0.591 | 1.117 | 1.886 | 4.4× |
| OptiQ | 1 | 0.180 | 3.959 | 11.501 | 26.641 | 148.0× |
| OptiQ | = N | 0.188 | 0.357 | 0.681 | 1.300 | 6.9× |
| vMLX | 1 | 0.173 | 3.781 | 11.053 | 25.576 | 147.8× |
| vMLX | = N | 0.180 | 0.296 | 0.543 | 1.084 | 6.0× |

**Both signatures are in the tables.** The capped rows are the 09-16 finding exactly: per-request rate flat
(within 3.4%), aggregate flat (within 1.2%), and TTFT growing 63–148× from 0.173–0.399 s — everything after
the single admitted request queues. The uncapped rows are the opposite pair: per-request down 78–82%,
aggregate up 1.45–1.65×, TTFT up 4.4–6.9×. Same model, same prompts, same protocol; between the two columns
in these tables nothing moved but the three literals — the seed half had already moved in the seedless sweep.

Context, for the same `decode` shape in the same seedless sweep: **mlx-lm batches too** on the seedless
path — per-request 65.9 → 14.5, aggregate 65.3 → 112.5 (**1.72×**), TTFT 0.147 → 0.989 — and **Osaurus does
not at its shipped default** — 67.3 → 68.4, 64.8 → 66.0 (1.02×), TTFT 0.288 → 27.388 — with the host key at
N it batches too (63.5 → 12.3, 60.3 → 95.7, **1.59×**, §4).

**Against 09-16's own table** (a seeded grid whose directories cannot be joined to these, so this is a
reading of that paper, not a re-measurement): the capped columns today reproduce its shape and its levels —
oMLX decode aggregate 71.5/71.6/72.2/72.2 against 70.4/71.4/72.2/72.5, OptiQ 67.3…68.1 against 72.1…73.0,
vMLX 69.9…70.5 against 71.1…72.1, Osaurus 64.8…66.0 against 66.4…67.0. mlx-lm is the one column the seed
alone moved — it is the one of the four with no cap — and it is the direct before/after: 09-16's N=8
aggregate was 73.9 (1.15×, dismissed there because its per-request rate rose); today's seedless column is
112.5 (1.72×) with the per-request rate falling, which is batching's signature.

### 2. The full ladders

Every required reading of the first two sweeps is in these six tables: per workload (chat / prefill / decode),
per runtime and N, the per-request decode rate, the aggregate rate, and TTFT p50. All figures are the joins'
rows; each run directory under `results/sweep-conc-{seedless,uncapped}/oq4__<runtime>/` carries the same
numbers in its own `leaderboard.md` and its raw `results.jsonl`. `n` is 9 measured batches per cell
(9/18/36/72 requests at N = 1/2/4/8). The sequence-cap sweep's three ladders are §4's, built the same way from
the four leaderboards under `results/sweep-conc-osaurus-seqs/oq4__osaurus/`.

**Seedless sweep — caps 1, seedless — `chat` (max_tokens 128)**

| runtime | metric | 1 | 2 | 4 | 8 |
|---|---|---|---|---|---|
| mlx-lm | per-request decode tok/s | 72.1 | 46.4 | 27.1 | 15.0 |
| | aggregate tok/s | 66.1 | 84.4 | 98.2 | 107.0 |
| | TTFT p50 s | 0.145 | 0.258 | 0.487 | 0.986 |
| oMLX | per-request decode tok/s | 85.9 | 75.0 | 69.3 | 67.1 |
| | aggregate tok/s | 67.5 | 67.6 | 67.2 | 66.3 |
| | TTFT p50 s | 0.404 | 1.307 | 3.133 | 7.101 |
| OptiQ | per-request decode tok/s | 72.3 | 71.7 | 69.0 | 70.0 |
| | aggregate tok/s | 66.6 | 66.4 | 66.0 | 66.3 |
| | TTFT p50 s | 0.144 | 1.122 | 3.069 | 7.091 |
| vMLX | per-request decode tok/s | 73.6 | 73.0 | 72.4 | 71.7 |
| | aggregate tok/s | 66.8 | 66.8 | 66.1 | 65.5 |
| | TTFT p50 s | 0.175 | 1.114 | 3.070 | 6.987 |
| Osaurus | per-request decode tok/s | 70.2 | 73.7 | 73.8 | 73.7 |
| | aggregate tok/s | 61.1 | 63.4 | 63.0 | 62.9 |
| | TTFT p50 s | 0.299 | 1.273 | 3.341 | 7.437 |

**Seedless — `prefill` (64)** — the mlx-lm and OptiQ rows here are prompt-cache hits, superseded by the cache-off table in the 2026-09-29 correction above.

| runtime | metric | 1 | 2 | 4 | 8 |
|---|---|---|---|---|---|
| mlx-lm | per-request decode tok/s | 71.6 | 45.7 | 27.4 | 14.9 |
| | aggregate tok/s | 61.1 | 77.3 | 89.7 | 96.1 |
| | TTFT p50 s | 0.152 | 0.262 | 0.499 | 1.017 |
| oMLX | per-request decode tok/s | 107.9 | 107.3 | 107.4 | 107.3 |
| | aggregate tok/s | 19.3 | 19.2 | 19.2 | 19.2 |
| | TTFT p50 s | 2.714 | 4.351 | 7.727 | 14.394 |
| OptiQ | per-request decode tok/s | 78.6 | 76.0 | 79.1 | 77.5 |
| | aggregate tok/s | 58.2 | 58.0 | 57.5 | 57.6 |
| | TTFT p50 s | 0.181 | 0.614 | 1.486 | 3.231 |
| vMLX | per-request decode tok/s | 73.1 | 73.8 | 72.9 | 73.2 |
| | aggregate tok/s | 21.0 | 20.9 | 21.0 | 20.9 |
| | TTFT p50 s | 2.176 | 3.719 | 6.399 | 12.918 |
| Osaurus | per-request decode tok/s | 88.8 | 86.4 | 87.5 | 88.3 |
| | aggregate tok/s | 19.7 | 19.6 | 19.7 | 19.7 |
| | TTFT p50 s | 2.521 | 4.138 | 7.395 | 13.876 |

**Seedless — `decode` (512)**

| runtime | metric | 1 | 2 | 4 | 8 |
|---|---|---|---|---|---|
| mlx-lm | per-request decode tok/s | 65.9 | 43.3 | 26.2 | 14.5 |
| | aggregate tok/s | 65.3 | 83.6 | 102.0 | 112.5 |
| | TTFT p50 s | 0.147 | 0.259 | 0.482 | 0.989 |
| oMLX | per-request decode tok/s | 75.7 | 73.7 | 73.3 | 73.1 |
| | aggregate tok/s | 71.5 | 71.6 | 72.2 | 72.2 |
| | TTFT p50 s | 0.399 | 3.903 | 10.898 | 25.187 |
| OptiQ | per-request decode tok/s | 68.9 | 69.1 | 69.3 | 69.1 |
| | aggregate tok/s | 67.3 | 67.7 | 68.2 | 68.1 |
| | TTFT p50 s | 0.180 | 3.959 | 11.501 | 26.641 |
| vMLX | per-request decode tok/s | 71.4 | 71.7 | 72.2 | 72.2 |
| | aggregate tok/s | 69.9 | 70.1 | 70.5 | 70.5 |
| | TTFT p50 s | 0.173 | 3.781 | 11.053 | 25.576 |
| Osaurus | per-request decode tok/s | 67.3 | 68.0 | 68.4 | 68.4 |
| | aggregate tok/s | 64.8 | 65.5 | 66.0 | 66.0 |
| | TTFT p50 s | 0.288 | 4.207 | 11.887 | 27.388 |

**Uncapped sweep — caps = N — `chat`**

| runtime | metric | 1 | 2 | 4 | 8 |
|---|---|---|---|---|---|
| oMLX | per-request decode tok/s | 84.5 | 47.0 | 27.1 | 12.6 |
| | aggregate tok/s | 64.6 | 75.3 | 89.2 | 81.0 |
| | TTFT p50 s | 0.428 | 0.596 | 1.015 | 1.827 |
| OptiQ | per-request decode tok/s | 70.9 | 45.4 | 27.3 | 14.6 |
| | aggregate tok/s | 64.2 | 79.1 | 94.4 | 98.3 |
| | TTFT p50 s | 0.155 | 0.362 | 0.686 | 1.370 |
| vMLX | per-request decode tok/s | 69.4 | 41.2 | 24.3 | 13.4 |
| | aggregate tok/s | 63.8 | 75.1 | 88.3 | 97.6 |
| | TTFT p50 s | 0.174 | 0.300 | 0.562 | 1.098 |

**Uncapped — `prefill`** — OptiQ's rows here are prompt-cache hits, superseded by the cache-off table in the 2026-09-29 correction above.

| runtime | metric | 1 | 2 | 4 | 8 |
|---|---|---|---|---|---|
| oMLX | per-request decode tok/s | 98.3 | 51.0 | 20.1 | 18.7 |
| | aggregate tok/s | 17.8 | 17.4 | 18.5 | 18.2 |
| | TTFT p50 s | 2.901 | 5.099 | 8.435 | 15.598 |
| OptiQ | per-request decode tok/s | 77.6 | 48.0 | 29.0 | 15.2 |
| | aggregate tok/s | 57.3 | 64.6 | 78.8 | 74.8 |
| | TTFT p50 s | 0.188 | 0.376 | 0.686 | 1.467 |
| vMLX | per-request decode tok/s | 72.2 | 40.0 | 24.0 | 13.3 |
| | aggregate tok/s | 19.8 | 21.3 | 22.2 | 23.1 |
| | TTFT p50 s | 2.289 | 4.414 | 8.772 | 17.407 |

**Uncapped — `decode`**

| runtime | metric | 1 | 2 | 4 | 8 |
|---|---|---|---|---|---|
| oMLX | per-request decode tok/s | 69.1 | 44.6 | 25.5 | 12.4 |
| | aggregate tok/s | 65.2 | 85.2 | 95.0 | 94.4 |
| | TTFT p50 s | 0.426 | 0.591 | 1.117 | 1.886 |
| OptiQ | per-request decode tok/s | 67.4 | 44.7 | 26.6 | 14.6 |
| | aggregate tok/s | 65.6 | 84.6 | 98.7 | 108.2 |
| | TTFT p50 s | 0.188 | 0.357 | 0.681 | 1.300 |
| vMLX | per-request decode tok/s | 68.5 | 41.1 | 25.2 | 14.0 |
| | aggregate tok/s | 65.1 | 80.3 | 81.4 | 107.1 |
| | TTFT p50 s | 0.180 | 0.296 | 0.543 | 1.084 |

### 3. Decode: who batches and by how much

**Axis — `concurrency` within a runtime.** The table below is the `decode` shape's N=8 against its own N=1,
per runtime and per sweep, and it is the paper's headline in one view. **Caveat:** each row is that sweep's
own session; the gain column is a within-runtime N=8/N=1 ratio and is the one number here that survives the
session bar in Conditions.

| runtime | sweep | per-request N=1 → N=8 | aggregate N=1 → N=8 | **N=8/N=1** | TTFT p50 N=1 → N=8 |
|---|---|---|---|---|---|
| mlx-lm | seedless (cap 1, seed gone) | 65.9 → 14.5 (−78.0%) | 65.3 → 112.5 | **1.72×** | 0.147 → 0.989 |
| oMLX | seedless (cap 1) | 75.7 → 73.1 (−3.4%) | 71.5 → 72.2 | 1.01× | 0.399 → 25.187 |
| oMLX | uncapped (cap = N) | 69.1 → 12.4 (−82.1%) | 65.2 → 94.4 | **1.45×** | 0.426 → 1.886 |
| OptiQ | seedless (cap 1) | 68.9 → 69.1 (+0.3%) | 67.3 → 68.1 | 1.01× | 0.180 → 26.641 |
| OptiQ | uncapped | 67.4 → 14.6 (−78.3%) | 65.6 → 108.2 | **1.65×** | 0.188 → 1.300 |
| vMLX | seedless (cap 1) | 71.4 → 72.2 (+1.1%) | 69.9 → 70.5 | 1.01× | 0.173 → 25.576 |
| vMLX | uncapped | 68.5 → 14.0 (−79.6%) | 65.1 → 107.1 | **1.65×** | 0.180 → 1.084 |
| Osaurus | seedless (host default cap 1) | 67.3 → 68.4 (+1.6%) | 64.8 → 66.0 | 1.02× | 0.288 → 27.388 |
| Osaurus | sequence cap = N | 63.5 → 12.3 (−80.6%) | 60.3 → 95.7 | **1.59×** | 0.306 → 1.439 |

The vMLX uncapped row's N=8 cell is the one run alone at 19:03–19:38; its own drift is +0.3% and its N=1–4
cells are from the earlier window, so the row's *direction* is solid and its magnitude is the least controlled
number in the table. Osaurus's sequence-cap row is the third sweep's own session — Osaurus alone, 20:34–21:56,
under the host setting — and its detail is §4. mlx-lm's distance (1.72×) is not a claim that it is a better
server than the other three — it is a different session, a different timing channel and a different shape of
ladder (see channel caveat), and only its direction is comparable.

**Memory moves with the same split.** Peak `phys_footprint` at N=8 against N=1, within each runtime (a
cross-runtime comparison of these columns is forbidden — `peak_mb` counts different page classes per runtime):

| runtime (sweep) | chat | prefill | decode |
|---|---|---|---|
| mlx-lm (seedless) | 3031 → 5133 | 4250 → 11264 | 3375 → 7962 |
| oMLX (seedless, cap 1) | 4208 → 4232 | 5595 → 5609 | 4209 → 4235 |
| oMLX (uncapped) | 4217 → 9482 | 5603 → 5768 | 4215 → 17408 |
| OptiQ (seedless, cap 1) | 3337 → 3574 | 4288 → 4764 | 3125 → 3399 |
| OptiQ (uncapped) | 3331 → 5083 | 4454 → 7283 | 3084 → 6284 |
| vMLX (seedless, cap 1) | 3863 → 3881 | 4651 → 4659 | 3875 → 3883 |
| vMLX (uncapped) | 3885 → 5539 | 4662 → 6847 | 3883 → 5439 |
| Osaurus (seedless, host default cap 1) | 1608 → 1602 | 3566 → 3561 | 2504 → 2491 |
| Osaurus (sequence cap = N) | 1626 → 3637 | 3583 → 4857 | 2512 → 3765 |

The capped columns barely move (oMLX decode +26 MB across the whole ladder, OptiQ +274, vMLX +8) because one
request at a time holds one request's KV; uncapped, the same runtimes hold the batches (oMLX decode
4.2 → 17.4 GB, +13.2 GB at N=8). Osaurus's flat peak is its flat everything at the host default; with the key
at N it holds the batches too (decode 2.5 → 3.8 GB, §4).

### 4. Osaurus's sequence cap: at `concurrency.maxConcurrentSequences` = N it batches, and the shipped default of 1 is the flat column

**Axis — Osaurus's host sequence cap, within one runtime and one session.** The sequence-cap sweep is Osaurus
alone, 20:34 → 21:56 EDT 2026-09-27, under `results/sweep-conc-osaurus-seqs/` (`runner.log`,
`sweep-oq4__osaurus.md`, each run's `leaderboard.md`): the runner re-recorded the cap-1 baseline for the N=1
cell, then set `concurrency.maxConcurrentSequences` to the run's N by `scripts/osaurus-pin.sh osaurus_set_seqs`
(`8899b3a`, the same rule Decision 129 wrote as the three flags, with no flag available here) before each
remaining cell, and finished with `osaurus settings restored byte-exact (cmp)`. **Caveat:** the cap-1 column
below is the seedless sweep's Osaurus runs, ten hours earlier; this sweep's own N=1 re-record is the
within-sweep baseline, the two sessions' cap-1 levels agree on `decode` within the Conditions bar (63.5 against
67.3) while this sweep's `chat` and `prefill` N=1 cells are flagged still-warming rows (§6), and every ratio
below is within one column, not across two.

`chat` (max_tokens 128) — the shipped default against the key at N:

| cap | metric | 1 | 2 | 4 | 8 | N=8/N=1 |
|---|---|---|---|---|---|---|
| 1 — shipped default (seedless sweep) | per-request decode tok/s | 70.2 | 73.7 | 73.8 | 73.7 | 1.05× |
| | aggregate tok/s | 61.1 | 63.4 | 63.0 | 62.9 | 1.03× |
| | TTFT p50 s | 0.299 | 1.273 | 3.341 | 7.437 | 24.9× |
| = N — the key at the run's N | per-request decode tok/s | 48.6 | 37.7 | 23.6 | 13.0 | **0.27×** |
| | aggregate tok/s | 48.0 | 65.8 | 82.7 | 90.5 | **1.89×** |
| | TTFT p50 s | 0.408 | 0.434 | 0.755 | 1.439 | 3.5× |

`prefill` (64):

| cap | metric | 1 | 2 | 4 | 8 | N=8/N=1 |
|---|---|---|---|---|---|---|
| 1 — shipped default (seedless sweep) | per-request decode tok/s | 88.8 | 86.4 | 87.5 | 88.3 | 0.99× |
| | aggregate tok/s | 19.7 | 19.6 | 19.7 | 19.7 | 1.00× |
| | TTFT p50 s | 2.521 | 4.138 | 7.395 | 13.876 | 5.5× |
| = N — the key at the run's N | per-request decode tok/s | 77.8 | 42.0 | 24.5 | 13.4 | **0.17×** |
| | aggregate tok/s | 18.1 | 19.8 | 20.9 | 21.3 | **1.18×** |
| | TTFT p50 s | 2.701 | 4.909 | 9.633 | 19.126 | 7.1× |

`decode` (512):

| cap | metric | 1 | 2 | 4 | 8 | N=8/N=1 |
|---|---|---|---|---|---|---|
| 1 — shipped default (seedless sweep) | per-request decode tok/s | 67.3 | 68.0 | 68.4 | 68.4 | 1.02× |
| | aggregate tok/s | 64.8 | 65.5 | 66.0 | 66.0 | 1.02× |
| | TTFT p50 s | 0.288 | 4.207 | 11.887 | 27.388 | 95.1× |
| = N — the key at the run's N | per-request decode tok/s | 63.5 | 36.7 | 22.4 | 12.3 | **0.19×** |
| | aggregate tok/s | 60.3 | 71.0 | 86.6 | 95.7 | **1.59×** |
| | TTFT p50 s | 0.306 | 0.433 | 0.764 | 1.439 | 4.7× |

**With the key at N the column is batching's signature, not serialization's.** `decode` reads per-request
63.5 → 12.3 (−80.6%), aggregate 60.3 → 95.7 (**1.59×**), TTFT 0.306 → 1.439 s (4.7×); `chat` −73.3% / **1.89×**
/ 3.5×; `prefill` −82.8% / 1.18× / 7.1× — the last the same split §5 describes for oMLX and vMLX, the decode
leg batching while the completion aggregate barely moves. The cap-1 column is flatness — per-request
67.3 → 68.4 (+1.6%), aggregate 64.8 → 66.0 (1.02×), TTFT 0.288 → 27.388 — and it is the host's shipped default,
not a fixed engine: the sweep's own N=1 cell, key at 1, reproduces it. **That answers what this paper left
open — whether `concurrency.maxConcurrentSequences` changes Osaurus: it does, and these are the numbers.**

**The load-bearing row is `decode`, and it is unflagged at both ends** — N=1 +2.9%, N=8 +1.4% (§6). `chat`'s
1.89× and `prefill`'s 1.18× sit on the sweep's two flagged still-warming N=1 baselines — 48.6 published
against an early half at 48.2 and a late half at 71.3, and 77.8 against 73.9 → 80.8 — so those published
per-request figures are early-window ones, and a low baseline can only flatter those ratios. The same
qualifier applies to the side-by-side, where the two cap-1 `chat` N=1 cells (70.2 and 48.6) are 30.8% apart
published and 5.3% apart on their late halves (75.3 against 71.3), while the `decode` N=1 pair, both
unflagged, differ by 5.6%.

**`memorySafety.safe_auto` did not bind the sequences at N ≤ 8 — as observed, not as a source claim.** The
host's profile is `safe_auto` at slider 2 (`docs/runtimes/osaurus.md` §3.2 and its memory-safety note), which
that document records as an upper bound on the same quantity as `concurrency.maxConcurrentSequences`: a
memory-derived cap below N would win and nothing in a result row would say so. These rows say no such cap sat
below 8: a cap of k < N would have held each cell near k, while the cells' own arithmetic — aggregate ÷
per-request, the requests in flight the two columns imply — reads 0.95 / 1.93 / 3.87 / 7.78 at N = 1 / 2 / 4 /
8 on `decode` and 0.99 / 1.75 / 3.50 / 6.96 on `chat` (the same N=8 reading lands 7.4–7.8 on all five
runtimes' `decode` cells, so the shortfall from 8 is the arithmetic's, not a bound's), and the peak
`phys_footprint` grows with N as held KVs would (chat 1626 → 3637 MB, §3). That is an observation of these
twelve rows on this host; it is not a reading of the binary, and it is not a claim about any other session,
artifact or N.

### 5. Prefill: no runtime gains aggregate on the long-prompt shape once the cache is off

> **2026-09-29 correction.** This section was written when mlx-lm's and OptiQ's `prefill` rows were prompt-cache hits
> (see the correction above). Where it contrasts them with oMLX and vMLX, read the contrast as gone: cache off,
> all five sit at a ~2.2–2.9 s N=1 TTFT and an aggregate of ~15–23 tok/s. The prose below is kept as first
> written, with the two claims the re-run refutes marked.

**Axis — `concurrency`.** Uncapped, the `prefill` shape's aggregate column reads oMLX
**17.8 / 17.4 / 18.5 / 18.2** and vMLX **19.8 / 21.3 / 22.2 / 23.1** tok/s — a ×1.02 and ×1.17 across the
ladder, against ×1.45–1.65 on their own `decode` shape and ×1.31–1.57 for OptiQ and mlx-lm on the same
`prefill` shape (OptiQ 57.3 → 74.8, mlx-lm 61.1 → 96.1) **[superseded: cache hits; cache off they read ×1.16 and ×1.08]**. Their per-request decode on this shape still
collapses (oMLX 98.3 → 18.7, vMLX 72.2 → 13.3) and their TTFT p50 still grows with N (oMLX 2.901 → 15.598,
vMLX 2.289 → 17.407). So the decode leg of this shape batches and the completion-token aggregate does not
rise: the wall time is being spent on the prompt leg, which the TTFT columns show scaling close to N
(×5.4 and ×7.6 for eight requests). Osaurus in the sequence-cap sweep reads the same near-flat aggregate
(18.1 / 19.8 / 20.9 / 21.3, ×1.18, §4) with its per-request decode collapsing the same way (77.8 → 13.4), so
the split is three runtimes' on these rows, not two.

**What the source shows, and what is only inferred.** The flag surfaces are recorded in
`docs/runtimes/omlx.md` and `docs/runtimes/vmlx.md`, and the source behind them reads: for oMLX,
`--max-concurrent-requests` is the only *sequence* cap needing to move — it feeds `SchedulerConfig.max_num_seqs`
**and** `completion_batch_size` (`settings.py:1710-1712`) and admission gates on it (`scheduler.py:9979-9982`)
— and `prefill_batch_size=1` is **hard-coded at BatchGenerator construction** (`scheduler.py:3088`), with
prefills done externally per request (`scheduler.py:9960`); `_effective_max_num_seqs()` also returns 1 for
Llama 4 and overflow recovery (`scheduler.py:9391-9396`). That is a source reading of a batch path that does
not batch prefills, and the rows are consistent with it. It is **not** a measurement of the cause: no cell in
any sweep varies a prefill batch size, so "the literal is why the aggregate stays at ~18" is an inference
from source plus rows, not a result. For vMLX the source reading is the opposite way: `--prefill-batch-size`
and `--completion-batch-size` are 512 each (`cli.py:3640`, `:3653`; `scheduler.py:590-591`), not limiting at
N≤8; three engine-side guards do force serial scheduling for specific families
(`scheduler.py:899-974`, `mllm_scheduler.py:1736-1766`), and none of them matches this Qwen3.5 bundle by
inspection — so vMLX's near-flat prefill aggregate is **not explained by any limit the harness passed**, and
nothing in this record says why it is flat.

**[Superseded 2026-09-29: the ~2–3 s vs ~0.15–0.19 s split was the prompt cache — mlx-lm 2.294 s and OptiQ 2.441 s at N=1 with it off. What follows describes the cache-on rows.]**
**The ~2–3 s vs ~0.15–0.19 s N=1 TTFT is a runtime-level split, and the rows are all that is established.**
The N=1 `prefill` rows: oMLX 2.901 s (uncapped) / 2.714 s (seedless), vMLX 2.289 / 2.176, Osaurus 2.521 /
2.701 (sequence cap), against mlx-lm 0.152 and OptiQ 0.188 / 0.181. The `prefill_tps` rows tell the same story from the other
side — 454.6 (oMLX) and 574.1 (vMLX) against 8668.7 (mlx-lm) and 7289.6 (OptiQ) at N=1 — and since
`prefill_tps = prompt_tokens / ttft_s` (`report.py:6`), the two agree on the same prompt: roughly 1.3k
tokens in every runtime's own count (their products at N=1 land within 1,314–1,320). **The rows do not
establish a cause, and this paper does not invent one.** Two things they do establish: the split is present
at N=1 in *every* sweep that ran it, so it is not a concurrency effect; and it is present on three runtimes, so the one
source literal that would have been the tidy explanation — oMLX's `prefill_batch_size=1` — cannot be the
explanation of the level, since vMLX and Osaurus show the same level and that literal is oMLX's.

### 6. Every row with |drift| > 5%

The joins annotate a drift beyond ±5% on the entry and the row notes carry the direction, the half-window
medians, and report.py's fixed wording for the direction. All sixteen rows in the three sweeps are here (the
`seqs` rows are the sequence-cap sweep's, §4), quoted from the leaderboards under each run directory; the
direction clauses below are that wording verbatim
(`report.py:1039-1043`), and the medians are the rows' own. Drift is not a floor: each of these rows is
ranked with the rest and annotated, and at N>1 the sweep's own sentence governs — positive means the
per-request rate was still moving, not that the cell was under-warmed.

| sweep | cell | shape | N | drift % | the row's own reading | early → late median |
|---|---|---|---|---|---|---|
| seedless | oMLX | chat | 2 | −6.1 | slowing down — the thermal curve the interleave exists to expose | 77.4 → 72.6 |
| seedless | oMLX | chat | 4 | +5.7 | still warming up — insufficient warmup, not a thermal effect | 68.0 → 71.9 |
| seedless | Osaurus | chat | 1 | +9.0 | still warming up — insufficient warmup, not a thermal effect | 69.2 → 75.3 |
| uncapped | oMLX | chat | 1 | −6.7 | slowing down — the thermal curve the interleave exists to expose | 85.0 → 79.4 |
| uncapped | oMLX | prefill | 1 | −6.5 | slowing down — the thermal curve the interleave exists to expose | 98.2 → 91.8 |
| uncapped | oMLX | prefill | 2 | **+118.9** | still warming up — insufficient warmup, not a thermal effect | 37.2 → 81.4 |
| uncapped | oMLX | prefill | 4 | +8.3 | still warming up — insufficient warmup, not a thermal effect | 19.4 → 21.0 |
| uncapped | oMLX | decode | 4 | −5.8 | slowing down — the thermal curve the interleave exists to expose | 25.9 → 24.4 |
| uncapped | OptiQ | chat | 1 | +7.7 | still warming up — insufficient warmup, not a thermal effect | 67.2 → 72.4 |
| uncapped | OptiQ | prefill | 2 | −15.5 | slowing down — the thermal curve the interleave exists to expose | 49.6 → 42.0 |
| uncapped | OptiQ | prefill | 8 | +11.1 | still warming up — insufficient warmup, not a thermal effect | 13.8 → 15.3 |
| uncapped | vMLX | chat | 4 | +8.6 | still warming up — insufficient warmup, not a thermal effect | 23.5 → 25.5 |
| uncapped | vMLX | decode | 4 | −32.7 | slowing down — the thermal curve the interleave exists to expose | 25.4 → 17.1 |
| seqs | Osaurus | chat | 1 | **+48.0** | still warming up — insufficient warmup, not a thermal effect | 48.2 → 71.3 |
| seqs | Osaurus | prefill | 1 | +9.3 | still warming up — insufficient warmup, not a thermal effect | 73.9 → 80.8 |
| seqs | Osaurus | chat | 2 | +9.3 | still warming up — insufficient warmup, not a thermal effect | 35.4 → 38.7 |

**What each one does and does not touch.**

- **The batching results rest on aggregate, and no cell a ratio uses is a drift row.** The load-bearing
  ratios of §3 and §4 use the `decode` shape's N=1 and N=8 aggregates, and **none of the eighteen N=1/N=8
  `decode` cells across the three sweeps is a flagged row**; the one flagged `decode` cell in any sweep is
  vMLX's N=4, which no ratio uses. An aggregate is computed over the whole measured window, which is the same
  window the warmup settled on; the drift note is about the per-request series, which is the series that can
  still move.
- **uncapped oMLX prefill N=2 (+118.9%)** is the paper's largest positive: 51.0 tok/s published from an early
  half at 37.2 against a late half at 81.4 — the published per-request figure is an early-window one and the
  settled value is `≥` it. It touches exactly one cell in one column (oMLX `prefill` per-request at N=2). It
  does not touch §5's claim, which is about the aggregate column (17.4 at that N, whole-window) or the flat
  ladder around it.
- **seqs Osaurus chat N=1 (+48.0%)** is the sequence-cap sweep's largest: 48.6 tok/s published from an early
  half at 48.2 against a late half at 71.3 — an early-window figure whose settled value is `≥` it. It is the
  N=1 baseline of that sweep's `chat` ladder, so the 1.89× there is built on a low baseline and is if
  anything generous (§4). It touches that ratio's baseline. It does not touch §4's load-bearing row, which is
  `decode`, unflagged at both ends (N=1 +2.9, N=8 +1.4).
- **The other still-warming rows** (oMLX chat N=4 +5.7, oMLX prefill N=4 +8.3, OptiQ chat N=1 +7.7, OptiQ
  prefill N=8 +11.1, vMLX chat N=4 +8.6, the seedless Osaurus chat N=1 +9.0, and the sequence-cap sweep's
  Osaurus prefill N=1 +9.3 and chat N=2 +9.3) all move the same way — published per-request is a floor, not a
  ceiling, for that cell. Three of them are N=1 baselines: OptiQ's chat baseline is the
  flagged one, while the aggregate the headline's OptiQ ratios use comes from the unflagged `decode` row at
  both ends (65.6 and 108.2); the seedless Osaurus's flagged N=1 chat entry is the lowest of its four and its
  direction is *away* from a batching reading, and Osaurus's as-shipped (host default cap 1) flatness rests
  on aggregate (61.1 → 62.9) and on the three unflagged cells there; the sequence-cap sweep's flagged
  `prefill` N=1 is the low baseline under that ladder's ×1.18 (§4), and its `decode` row is unflagged at both
  ends.
- **The slowing rows** published a first-half figure above the second half's: oMLX chat N=1 −6.7 and prefill
  N=1 −6.5, oMLX decode N=4 −5.8, OptiQ prefill N=2 −15.5. The two oMLX N=1 cells are chat's and prefill's,
  so any oMLX ratio built on them would be if anything generous; the quoted 1.45× is the `decode` one, whose
  baseline row is unflagged (69.1, drift +4.3). OptiQ's prefill −15.5% touches its N=2 per-request
  value only; its aggregates (64.6 at N=2) are whole-window.
- **uncapped vMLX decode N=4 (−32.7%)** is the largest negative. The cell ran 15:28:56 → 15:50:10, the last
  one before the runner's `ABORTED 15:50:16` (the Mac had to be moved). **That is timing, and this paper
  claims no cause from it** — not the stop, not the move, nothing external; the row's own reading is that the
  cell was slowing down as it was measured, at 25.4 → 17.1 tok/s across its halves. It touches the vMLX
  `decode` ladder's N=4 point (the published 25.2 is a first-half figure) and the confidence in any claim
  that the vMLX ladder is monotone between N=2 and N=8. It does not touch the two cells the 1.65× uses: the
  unflagged N=1 (−4.8, inside the bar) and the N=8 run alone at 19:03, whose own drift is +0.3%.

## What an everyday user should take from it

- **On today's oMLX, OptiQ and vMLX, sending work concurrently now buys real throughput where it used to buy
  nothing — and on Osaurus too, once its own host key is raised.** Eight requests at once return
  **1.45–1.72×** the total tokens per second of eight requests sent one after another (`decode` shape;
  mlx-lm 1.72×, oMLX 1.45×, OptiQ 1.65×, vMLX 1.65×), and Osaurus with `concurrency.maxConcurrentSequences`
  at N returns **1.59×** where its shipped default of 1 returns 1.02×. Before 2026-09-27's fixes, three of
  those four rows would have shown ~1.01× — the harness's cap, not the server; Osaurus's flat 1.02× was its
  host's shipped cap of 1, not a fixed engine.
- **The price is on every request.** The same eight-at-once batch decodes each request at **12–15 tok/s**
  against **63–74 tok/s** alone, and its first token arrives 1.1–1.9 s (oMLX/OptiQ/vMLX, and Osaurus at
  cap = N) instead of 0.17–0.43 s. That is what batching is: aggregate up, per-request down. Choose per your
  traffic — one interactive user is better served alone; a queue of requests is better served batched.
- **Long prompts are the case where batching still does not pay on oMLX, vMLX and cap = N Osaurus.** The
  `prefill` shape's aggregate stays at 18–23 tok/s across the ladder (Osaurus 18.1 → 21.3), and its first
  token at N=8 takes ~15.6 s (oMLX) / ~17.4 s (vMLX) / ~19.1 s (Osaurus). If your traffic is long-prompt, one
  at a time is not leaving throughput on the table on those three.
- **mlx-lm batches by default once the seed is gone; Osaurus batches once its host key is raised.** As
  shipped it caps itself at one sequence (`concurrency.maxConcurrentSequences: 1`) and stays flat — that
  column is the host's default, not the engine's ceiling: with the key at N the same cells return 1.59× on
  `decode` and 1.89× on `chat` (§4). There is no flag to pass; the setting is the surface.
- **Quote the direction, not the level.** One model, one machine, one day; within each runtime the ladder is
  the result. Cross-runtime levels here are six sequential sessions on a laptop.

## Open questions

1. **Is oMLX's hard-coded `prefill_batch_size=1` (`scheduler.py:3088`) the reason its prefill aggregate is
   flat?** The rows are consistent with it and no cell varies it. A test needs a surface that does not
   exist today; until then the link is source-plus-consistency, labelled as an inference in §5.
2. **Why is the prompt leg ~N-scaled on vMLX at all?** TTFT ×7.6 for eight requests on a runtime with
   512-wide prefill flags and no matching serial-scheduling guard in the source. Admission, chunking and
   memory are all live explanations and nothing here separates them.
3. **Is the oMLX chat dip at N=8 (89.2 → 81.0 aggregate) a ceiling or memory pressure?** Its peak nearly
   doubles (5533 → 9482 MB) across the same step, and the N=8 cell is unflagged. One cell; a rerun with a
   memory read per batch would say.
4. **How far does mlx-lm's ladder go?** Its own defaults allow 32 decodes / 8 prompts at once; this sweep
   stops at 8, where its aggregate is still climbing (102.0 → 112.5).
5. **Why do the oMLX N=1 rows read 8.7–8.9% below the seedless sweep's when the command is byte-identical?**
   That is larger than the other two runtimes' N=1 session gap (OptiQ 1.3–2.5%, vMLX 1.2–5.7%) and it is the
   bar under any cross-sweep level; bounding it is a rerun, not an argument.

## What this cannot claim

- **Nothing about a runtime other than these five releases on this one artifact.** `Qwen3.5-4B-oQ4`
  (3,160,559,814 bytes, one artifact directory in all 108 rows), mlx-lm 0.31.3, oMLX 0.6.4, OptiQ 0.5.13,
  vMLX 1.6.59, Osaurus 0.25.13, on one M2 Max. A different quant, model or release is a different
  measurement.
- **No cross-runtime ranking of any kind.** Each runtime was measured in its own window; the timing channels
  differ (OptiQ content, the rest reasoning) and Decision 122 forbids ranking the channel-dependent metrics
  across them; `peak_mb` and `cold_load_s` are uncomparable across runtimes for accounting reasons. The
  ladders' own N-vs-N direction is the result here, never a level against another runtime's level.
- **No claim that any runtime "cannot" batch.** Osaurus's flatness is its shipped host default
  (`concurrency.maxConcurrentSequences: 1`) and it batches once the key is raised (§4); the rows say its
  `safe_auto` memory-safety profile did not bind the sequences at N ≤ 8 on this host in that session,
  which is an observation of those rows and not a source claim about the key's reach. oMLX's prefill flatness
  has a source reading and no measurement of the cause.
- **Nothing about spread or percentiles beyond the rows**: the paper quotes `decode_tps`, `aggregate_tps`,
  `ttft_p50_s` and `peak_mb`, each as published; p90/p99 and ITL are in every leaderboard and not read here.
- **No accuracy claim.** Coherence is a floor — every one of the 108 rows produced language — and nothing in
  this run scores an output.
- **The 09-16 comparison is a reading of that paper, not a re-join.** Its runs were seeded and this harness
  will not join a seed-bearing header to a seedless one (Decision 128); the numbers quoted from it are its
  published table's.
- **The three sweeps are three sessions, and the uncapped vMLX N=8 cell is its own.** Nothing here controls
  for what else the machine was doing; the harness cannot detect contention, and no run in any sweep attests
  the host's state while it ran. The sequence-cap sweep is Osaurus alone, contiguous in one session, and its
  cap-1 comparison column is the seedless sweep's ten hours earlier — a cross-sweep level there is two
  sessions, not one.
