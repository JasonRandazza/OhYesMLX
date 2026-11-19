# Cold-load ordering audit — what the S5-F2 overstatement does to published orderings

Date: 2026-11-19. **Paper audit. No runtime was started, no model loaded, no tensor read, nothing
downloaded.** Every figure below is arithmetic on numbers already published or already on disk in
`results/`.

Subject: Fable S5-F2 (`.paul/review/fable-5.2/S5-findings.md`, finding F2) — `cold_load_s`
included the engine's version probe and one `lsof` call until plan 05-07 (merged 2026-11-16,
`3033233`). Before 05-07 the clock ran from `started = _now()` through `await_ready(...)`,
`self.version()`, and `_serving_pid(...)`; after it, `cold_load_s` is taken on the line following
`await_ready` and the probe and listener lookup follow (`ohyesmlx/runtimes.py:2856-2891`).

The measured size of that constant is in `.paul/phases/v5-onboarding/05-14-SUMMARY.md:34`, and in
this order's task table:

| Engine | Overstatement, warm median (cold first call) |
|---|---|
| mlx-lm | 1.01 s (1.83 s) |
| OptiQ | 1.03 s (1.76 s) |
| Osaurus | 0.31 s |
| oMLX | 0.11 s (0.15 s) |
| vMLX | 0.07 s |

Each figure is the version probe plus one 0.068 s `lsof`. The arithmetic checks: 0.94 + 0.068 =
1.01, 1.76 + 0.068 = 1.83, 0.96 + 0.07 = 1.03, 1.69 + 0.07 = 1.76, 0.24 + 0.07 = 0.31, 0.04 + 0.07
= 0.11, 0.08 + 0.07 = 0.15, 0.004 + 0.07 = 0.07.

**A footnote on the summary's own sentence.** `05-14-SUMMARY.md:34` closes with "the old
`cold_load_s` was overstated by about 1.0–1.8 s for mlx-lm and OptiQ, about 0.3 s for Osaurus, and
about 0.1 s for oMLX and vMLX." Read as a band per group of engines, that is right at the warm
bound and slightly low at the cold one: mlx-lm is 1.01–1.83 s and OptiQ 1.03–1.76 s (so 1.0–1.8),
Osaurus 0.31 s, vMLX 0.07 s, and oMLX 0.11 s warm but **0.15 s cold**, which is nearer 0.2 than
0.1. Per engine, over both bounds, the number is the table above.

---

## 1. Method

For every published engine comparison:

1. the engine's overstatement is subtracted from **both** bounds of each cell — the warm median,
   and the cold first call where one was measured;
2. an adjacent pair `a < b` (published as `a` faster) is re-tested at each bound independently.
   The verdict is **No** when `a` stays below `b` at both bounds, **Yes** when it inverts at both,
   **Only at cold bound** when it holds warm and inverts cold, **Only at warm bound** for the
   reverse;
3. a single-engine figure becomes a **range**: `[published − cold overstatement, published − warm
   overstatement]`. Osaurus and vMLX have one overstatement, so their range is a point.

Publication means a written doc under `docs/` or `README.md`. Raw `results/` directories, their
generated `grid.md`/`leaderboard.md`, and `.paul/` notes are not publications and are not audited
here; they are used only as provenance.

### 1.1 The `lsof` term cancels in every gap

Each side of a gap pays the same 0.068 s, so it subtracts out:

```
gap_corrected = (v_b − probe_b − 0.068) − (v_a − probe_a − 0.068) = gap_original − (probe_b − probe_a)
```

Every **flip verdict in this document is therefore identical whether or not the 0.068 s is
included**. It moves published *levels* (each engine down by 0.068 s) and published *ratios*
(slightly, in the slower loader's favour) and nothing else. Worked check: oMLX 3.12 vs mlx-lm 3.32
gives a −0.70 s warm gap and a −1.48 s cold gap at 0.000 s `lsof` and at 0.068 s alike.

### 1.2 Which published runs could actually have paid the 0.068 s

The `lsof` and the version probe did not enter and leave the timed window together. Evidence from
`git log -S` on `ohyesmlx/runtimes.py`, checked at every revision of `Runtime.start`:

| window state | first revision | date |
|---|---|---|
| version probe **inside**, `_serving_pid` **outside** (`cold_load_s=_now() - started` is evaluated in the `Handle(...)` argument list, before the later `serving_pid=` keyword) | `b1fc311` | 2026-09-15 |
| version probe **inside**, `_serving_pid` **inside** (assigned above the `cold_load_s = _now() - started` statement) | `ef01396` | 2026-09-23 17:41 −0400 |
| both **outside** (`cold_load_s` taken on the line after `await_ready`) | `8824447` | 2026-11-16 |

Every published cold-load figure in this audit was measured on or before **2026-09-20**, so:

- the **version probe** was in the timed window for **all of them** — the correction applies;
- the **`lsof`** was *not* in the timed window for any of them. Applying the full 0.068 s
  therefore over-corrects every published level by exactly 0.068 s. By §1.1 that changes no
  verdict; for absolute levels the "probe only" column below is the tighter figure.

`_port_is_free(self.port)` also runs before `started = _now()` at every revision, so the port
check is outside the window throughout and contributes nothing to the constant.

**One limit on the constant's decomposition.** From `dd7dace` (2026-09-19) `await_ready` calls
`_listener_pids(self.port)` — an `lsof` — on every poll while the spawned pid is dead
(`ohyesmlx/runtimes.py:2729+`, the `if not _process_alive(pid) and _listener_pids(...) == ()`
line). That is Osaurus's normal path, because `osaurus serve` hands off and exits, so an Osaurus
start from 09-19 onward pays an `lsof` per readiness poll *inside* the window, not one. The 0.31 s
in the task table is the measured aggregate for the code as measured, so it is used as given; the
point is recorded so that "probe + one `lsof`" is not read as a decomposition of the Osaurus
column. Osaurus is not a party to any flip below, so nothing in the verdicts turns on it.

---

## 2. The claims

`Run present?` says whether the doc's numbers trace to a `results/` directory that is still on
disk, and whether the raw row was re-read for this audit. `Predates 05-07?` is Yes for every row —
the newest audited run is 2026-09-20 and 05-07 merged 2026-11-16 — and no audited run header
carries a `harness` key, which the harness began writing on 2026-09-23 (`5313062`).

| # | Source | Date | Engines and published cold-load figures | Run present? | Old ordering | Corrected range (cold..warm bound) | Flips |
|---|---|---|---|---|---|---|---|
| 1 | `docs/research/2026-09-15-grid-loadability-probe.md:101` | 09-15 | oMLX 2.18, mlx-optiq 3.23, mlx-lm 3.85, vMLX 16.13 (medians) | **No** — `grid-probe.json` lived in `$CLAUDE_JOB_DIR/tmp` and is not in the repo | oMLX < optiq < mlx-lm < vMLX | oMLX 2.03–2.07, optiq 1.47–2.20, mlx-lm 2.02–2.84, vMLX 16.06 | **Only at cold bound** (oMLX/optiq); the rest No |
| 2 | `docs/research/2026-09-15-grid-loadability-probe.md:14` | 09-15 | stock-4bit row: mlx-lm 4.01, oMLX 3.11, optiq 4.20, vMLX 18.13 | **No** — same probe | oMLX < mlx-lm < optiq < vMLX (value order) | mlx-lm 2.18–3.00, oMLX 2.96–3.00, optiq 2.44–3.17, vMLX 18.06 | **Only at cold bound** (oMLX/mlx-lm, exactly level warm); the rest No |
| 3 | `docs/research/2026-09-15-cold-load-is-not-one-quantity.md:30` | 09-15 | mlx-lm 3.32, oMLX 3.12, mlx-optiq 4.14, vMLX 9.09 | **No** — `probe_lazy.py` prints JSON and keeps no file; `confirm_lazy.py` is not in `scripts/` | oMLX < mlx-lm < optiq < vMLX | mlx-lm 1.49–2.31, oMLX 2.97–3.01, optiq 2.38–3.11, vMLX 9.02 | **Yes** (oMLX/mlx-lm); the rest No |
| 4 | `docs/research/2026-09-15-first-live-run.md:39` | 09-15 | oQ4 row: mlx-lm 3.48, oMLX 3.11 | **Yes** — `results/20260915T143057Z-runtime/results.jsonl` (raw 3.480009709 and 3.114653417) | oMLX < mlx-lm | mlx-lm 1.65–2.47, oMLX 2.96–3.00 | **Yes** |
| 5 | `docs/research/2026-09-16-moe-loadability-probe.md:28` | 09-16 | Osaurus 1.3, mlx-lm 1.9–2.5, oMLX 1.7–2.2, optiq 3.1–3.3, vMLX 18–19 | **No** — `probe_grid_moe.py` prints JSON and keeps no file | Osaurus < oMLX ∩ mlx-lm (the ranges already overlap) < optiq < vMLX | mlx-lm 0.07–1.49, oMLX 1.55–2.09, optiq 1.34–2.27, Osaurus 0.99, vMLX 17.93–18.93 | **Yes** (oMLX/mlx-lm: no overlap survives); the rest No |
| 6 | `docs/research/2026-09-20-multiturn-conversation-sweep.md:82` | 09-20 | mlxlm 2.14, omlx 3.10, optiq 3.30, vmlx 8.12, osaurus 2.66 | **Yes** — `results/plan-03-04/multiturn_results.json` re-read, figures match | mlx-lm < osaurus < oMLX < optiq < vMLX | mlx-lm 0.31–1.20, osaurus 2.35, oMLX 2.95–2.99, optiq 1.54–2.34, vMLX 8.05 | **Yes** (oMLX/optiq); the rest No |
| 7 | `docs/research/2026-09-20-cold-warm-load-attribution-35b.md:48` | 09-20 | mlxlm 3.99, omlx 2.17, optiq 3.28, vmlx 8.08, osaurus 1.39 | **Yes** — `results/plan-03-02/probe_results.json` re-read, figures match | osaurus < omlx < optiq < mlxlm < vmlx | osaurus 1.08, oMLX 2.02–2.06, optiq 1.52–2.25, mlx-lm 2.16–2.98, vMLX 8.01 | **Only at cold bound** (oMLX/optiq); the rest No |
| 8 | `docs/research/2026-09-20-cold-warm-load-attribution-35b.md:23` | 09-20 | true cost `t_ready + t_1`: osaurus 3.42, mlxlm 4.64, omlx 7.45, vmlx 8.66, optiq 12.44 | **Yes** — same file (only the `t_ready` half moves; `t_1` is a request latency and is untouched) | osaurus < mlxlm < omlx < vmlx < optiq | osaurus 3.11, mlx-lm 2.81–3.63, oMLX 7.30–7.34, vMLX 8.59, optiq 10.68–11.41 | **Only at cold bound** (osaurus/mlxlm); the rest No |
| 9 | `docs/research/2026-09-20-35b-moe-serving.md:62` | 09-19/20 | stock4bit probe: mlxlm 4.0, omlx 3.1, optiq 3.3, vmlx 10.1, osaurus 1.4 | **Yes** — `results/probe-35b.jsonl` raw 4.0 / 3.09 / 3.25 / 10.09 / 1.44 | osaurus < omlx < optiq < mlxlm < vmlx | osaurus 1.13, oMLX 2.94–2.98, optiq 1.49–2.22, mlx-lm 2.17–2.99, vMLX 10.02 | **Yes** (oMLX/optiq); the rest No |
| 10 | `docs/research/2026-09-20-35b-moe-serving.md:191` | 09-19/20 | grid stock4bit: osaurus 2.67, omlx 3.14, optiq 3.32, mlxlm 3.58, vmlx 10.11 | **Yes** — `results/grid-35b/*/results.jsonl` re-read, figures match | osaurus < omlx < optiq < mlxlm < vmlx | osaurus 2.36, oMLX 2.99–3.03, optiq 1.56–2.29, mlx-lm 1.75–2.57, vMLX 10.04 | **Yes** (oMLX/optiq); the rest No |
| 11 | `docs/research/2026-09-17-dense-jang-study.md:599` | 09-17 | vMLX 7.06–7.08, Osaurus 1.25–1.29 (`cold_load_s`) | **Yes** — `results/grid-jang-dense/*/results.jsonl` and `replicate/`, figures match | Osaurus < vMLX | Osaurus 0.94, vMLX 6.99 | No |
| 12 | `docs/research/2026-09-17-moe-jang-study.md:801` | 09-17 | vMLX 7.09–7.10, Osaurus 1.27–1.30 | **Yes** — `results/grid-jang-moe/*/results.jsonl` and `replicate/`, figures match | Osaurus < vMLX | Osaurus 0.96, vMLX 7.02 | No |
| 13 | `docs/research/2026-09-17-jang-cross-runtime.md:727-732` | 09-17 | synthesis of #11 and #12; no new figures | **Yes** — inherited from the two grids | Osaurus < vMLX | as #11/#12 | No |

Ranges in the "Corrected range" column use the task table (probe + `lsof`). Per §1.2, dropping
the 0.068 s raises every level by 0.068 s and leaves every verdict unchanged.

---

## 3. Pair by pair

Each line states the published gap, then the gap recomputed at the warm and cold bounds. `gap` is
`b − a`, so a negative corrected gap is an inversion.

### 3.1 `grid-loadability-probe.md:101` — the four-runtime median table

```
oMLX 2.18 < optiq 3.23     published +1.05   warm +0.13 (2.07 vs 2.20)   cold −0.56 (2.03 vs 1.47)   Only at cold bound
optiq 3.23 < mlx-lm 3.85   published +0.62   warm +0.64 (2.20 vs 2.84)   cold +0.55 (1.47 vs 2.02)   No
mlx-lm 3.85 < vMLX 16.13   published +12.28  warm +13.22                 cold +14.04                 No
```

This is the table the same day's `2026-09-15-cold-load-is-not-one-quantity.md` already withdrew the
*ranking* from (`:91-96` carries the correction banner). What this audit adds is that the
withdrawal was not only right but **understated in one direction**: corrected, mlx-optiq is
demonstrably faster to listening than oMLX at the cold bound, so even as a time-to-listening
column the order is `optiq < mlx-lm < oMLX < vMLX` at the cold bound and `oMLX < optiq < mlx-lm <
vMLX` warm. The oMLX-vs-optiq position is not resolvable from these numbers.

### 3.2 `grid-loadability-probe.md:14` — the stock-4bit cells of the same probe

```
oMLX 3.11 < mlx-lm 4.01    published +0.90   warm +0.00 (3.00 vs 3.00)   cold −0.78 (2.96 vs 2.18)   Only at cold bound
mlx-lm 4.01 < optiq 4.20   published +0.19   warm +0.17                  cold +0.26                  No
optiq 4.20 < vMLX 18.13    published +13.93  warm +14.89                 cold +15.62                 No
```

The warm bound lands on a **dead heat** — 3.002 s against 3.002 s to two decimals — so this pair
is "level at warm, mlx-lm ahead at cold". A 0.90 s claim becoming a tie and then an inversion is
the sharpest single illustration of the defect here.

### 3.3 `cold-load-is-not-one-quantity.md:30` — the reported column

```
oMLX 3.12 < mlx-lm 3.32    published +0.20   warm −0.70 (3.01 vs 2.31)   cold −1.48 (2.97 vs 1.49)   Yes
mlx-lm 3.32 < optiq 4.14   published +0.82   warm +0.80                  cold +0.89                  No
optiq 4.14 < vMLX 9.09     published +4.95   warm +5.91                  cold +6.64                  No
```

**The paper's conclusion survives; its opening comparison does not.** This document's thesis is
that the `cold_load_s` column is not one quantity, and its corrected ranking (`:54-59`) puts mlx-lm
first at 3.39 s and oMLX third at 6.63 s. Re-correcting that table with its own cold half:

| runtime | published true cost | corrected (cold..warm) |
|---|---|---|
| mlx-lm | 3.39 | 1.56–2.38 |
| mlx-optiq | 4.18 | 2.42–3.15 |
| oMLX | 6.63 | 6.48–6.52 |
| vMLX | 9.19 | 9.12 |

The order `mlx-lm < optiq < oMLX < vMLX` is unchanged and the gaps widen in mlx-lm's favour, so the
paper's thesis is strengthened. What goes is the sentence's premise that oMLX "reports 3.12 s and
mlx-lm 3.32 s" in the *reported* column: with the probe removed, mlx-lm reported less than oMLX
even before the lazy-load correction — the 0.20 s that put oMLX first was the probe. Re-corrected,
the true-cost table's `vMLX` and `oMLX` entries barely move (their own constants are 0.07 and
0.11–0.15 s) while mlx-lm and optiq each drop about 1.8 s, so the four-way order is exactly what
that table already printed.

### 3.4 `first-live-run.md:39` — the two FAIL rows

```
oMLX 3.11 < mlx-lm 3.48    published +0.37   warm −0.53 (3.00 vs 2.47)   cold −1.31 (2.96 vs 1.65)   Yes
```

The doc's prose (`:49-52`) publishes "the cold load of a 21.6 GB 256-expert MoE under stock mlx-lm
really is about three and a half seconds". It is about **1.6–2.5 s**. The observation that the
number "is measured before any token is generated" still holds; its size does not. This is the only
audited doc whose *prose* states a cross-engine cold-load comparison in words rather than a table,
and it is the one that moves most in absolute terms.

### 3.5 `moe-loadability-probe.md:28` — the five-runtime sentence

The doc gives ranges, so the pair is tested as an overlap rather than a point comparison:

| runtime | published | corrected warm | corrected cold |
|---|---|---|---|
| Osaurus | 1.3 | 0.99 | 0.99 |
| oMLX | 1.7–2.2 | 1.59–2.09 | 1.55–2.05 |
| mlx-lm | 1.9–2.5 | 0.89–1.49 | 0.07–0.67 |
| mlx-optiq | 3.1–3.3 | 2.07–2.27 | 1.34–1.54 |
| vMLX | 18–19 | 17.93–18.93 | 17.93–18.93 |

Published, oMLX and mlx-lm overlap over 1.9–2.2 s. Corrected, the two bands **do not touch** —
mlx-lm tops out at 1.49 s warm while oMLX starts at 1.55 s cold — and mlx-lm is the faster loader
by 0.06–2.02 s depending on which end of each band a reader takes. The whole of the reported
overlap was the probe. Osaurus remains first and vMLX last; optiq's relation to both is unchanged.
Note the sentence's "mlx-lm 1.9–2.5 s" band itself is mostly the probe: corrected, mlx-lm's own
spread is 0.89–1.49 s warm.

### 3.6 `multiturn-conversation-sweep.md:82` — the lifecycle summary row

```
mlx-lm 2.14 < Osaurus 2.66    published +0.52   warm +1.22 (1.13 vs 2.35)   cold +2.04 (0.31 vs 2.35)   No
Osaurus 2.66 < oMLX 3.10      published +0.44   warm +0.64 (2.35 vs 2.99)   cold +0.60 (2.35 vs 2.95)   No
oMLX 3.10 < optiq 3.30        published +0.20   warm −0.72 (2.99 vs 2.27)   cold −1.41 (2.95 vs 1.54)   Yes
optiq 3.30 < vMLX 8.12        published +4.82   warm +5.78                  cold +6.51                  No
```

The published order `mlx-lm < Osaurus < oMLX < optiq < vMLX` becomes `mlx-lm < optiq < Osaurus <
oMLX < vMLX` — optiq moves from fourth to second. The two leading pairs hold, so this changes one
sentence of a table nobody read as a ranking, but the row is labelled "Startup / Cold Load Time"
and is the only place in that paper where a cross-runtime load level appears.

This paper already carries a probe-script caveat (`:3`) saying its figures are not comparable with
harness-produced ones. The overstatement is a separate defect and is not covered by that caveat:
`probe_multiturn_sweep.py:153` calls `rt.start` and reads `handle.cold_load_s`, so it inherited the
harness's timed window exactly.

### 3.7 `cold-warm-load-attribution-35b.md:48` — the cold-startup column

```
osaurus 1.39 < omlx 2.17    published +0.78   warm +0.98 (1.08 vs 2.06)   cold +0.94 (1.08 vs 2.02)   No
omlx 2.17 < optiq 3.28      published +1.11   warm +0.19 (2.06 vs 2.25)   cold −0.50 (2.02 vs 1.52)   Only at cold bound
optiq 3.28 < mlx-lm 3.99    published +0.71   warm +0.73                  cold +0.64                  No
mlx-lm 3.99 < vmlx 8.08     published +4.09   warm +5.03                  cold +5.85                  No
```

The published order `osaurus < omlx < optiq < mlxlm < vmlx` is a **strict ordering that does not
exist**. At the warm bound it is `osaurus < optiq < omlx < mlxlm < vmlx`; at the cold bound
`osaurus < optiq < omlx` becomes `osaurus < optiq`, with oMLX dropping behind optiq by half a
second. Either way oMLX is not second-fastest; it is third.

### 3.8 `cold-warm-load-attribution-35b.md:23` — the "completely inverts" ranking

```
osaurus 3.42 < mlxlm 4.64     published +1.22   warm +0.52 (3.11 vs 3.63)   cold −0.30 (3.11 vs 2.81)   Only at cold bound
mlxlm 4.64 < omlx 7.45        published +2.81   warm +3.71                  cold +4.49                  No
omlx 7.45 < vmlx 8.66         published +1.21   warm +1.25                  cold +1.29                  No
vmlx 8.66 < optiq 12.44       published +3.78   warm +2.82                  cold +2.09                  No
```

This is the paper's headline — "Evaluating True Time to First Output completely inverts the startup
ranking: `osaurus` (3.42 s) > `mlxlm` (4.64 s) > …". Only the `t_ready` half of each figure is
probe-contaminated (`first_request_s` is a request latency the probe never touched), so the
correction is smaller than elsewhere, but the leading pair is inside it: **at the cold bound
mlx-lm's true cost is 2.81 s against Osaurus's 3.11 s**, so the ranking no longer inverts at all —
Osaurus is first to ready and second to first token. Warm, Osaurus stays first. The next three
positions are unaffected.

### 3.9 `35b-moe-serving.md:62` — the loadability probe row

```
osaurus 1.44 < omlx 3.09    published +1.65   warm +1.85 (1.13 vs 2.98)   cold +1.81 (1.13 vs 2.94)   No
omlx 3.09 < optiq 3.25      published +0.16   warm −0.76 (2.98 vs 2.22)   cold −1.45 (2.94 vs 1.49)   Yes
optiq 3.25 < mlx-lm 4.00    published +0.75   warm +0.77                  cold +0.68                  No
mlx-lm 4.00 < vmlx 10.09    published +6.09   warm +7.03                  cold +7.85                  No
```

A 0.16 s claim becomes a 0.76–1.45 s lead the other way: optiq loaded faster than oMLX on this
artifact, and the published row says the opposite. This table's cells are loadability verdicts, not
a ranking, so the `LOADS`/`Refused` content is unaffected — only the seconds.

### 3.10 `35b-moe-serving.md:191` — the "Fastest Cold Load" recommendation

```
osaurus 2.67 < omlx 3.14    published +0.47   warm +0.67 (2.36 vs 3.03)   cold +0.63 (2.36 vs 2.99)   No
omlx 3.14 < optiq 3.32      published +0.18   warm −0.74 (3.03 vs 2.29)   cold −1.43 (2.99 vs 1.56)   Yes
optiq 3.32 < mlx-lm 3.58    published +0.26   warm +0.28                  cold +0.19                  No
mlx-lm 3.58 < vmlx 10.11    published +6.53   warm +7.47                  cold +8.29                  No
```

**The recommendation holds.** `stock4bit` in `osaurus` stays the fastest cold load at 2.36 s
against 2.99–3.03 s for the next engine, and its margin widens. The interior order
`omlx < optiq < mlxlm` does not: corrected, optiq is third-fastest ahead of oMLX. Since the
recommendation names only the winner, no recommendation in §8 of that paper changes.

### 3.11 The two JANG studies

```
dense-jang:599  Osaurus 1.25 < vMLX 7.06   published +5.81   warm +6.05   cold +6.05   No
moe-jang:801    Osaurus 1.27 < vMLX 7.09   published +5.82   warm +6.06   cold +6.06   No
```

Neither flips: a 5.8 s gap against a 1.8 s worst-case overstatement. vMLX's constant is 0.07 s and
Osaurus's 0.31 s, so the pair barely moves. `jang-cross-runtime.md:727-732` inherits these and is
likewise unaffected.

---

## 4. Ratios and sums

An overstatement that is constant across engines leaves a *sum* comparison almost intact and
*ratios* moving in the slower (less-overstated) loader's favour.

### 4.1 Stated ratios

| Claim | Stated | probe only | probe + lsof | Change |
|---|---|---|---|---|
| `grid-loadability-probe.md:108` "vMLX is **7.4× slower to load** than oMLX" | 7.40× | 7.54–7.68× | 7.75–7.90× | **gap widens**; the sentence understates |
| `dense-jang-study.md:605` "Osaurus **5.5–5.7×** the faster loader" on `cold_load_s` (5.47×–5.66× as printed) | 5.47–5.66× | 6.72–7.01× | 7.12–7.44× | **gap widens ~25%** |
| `moe-jang-study.md:817` / `jang-cross-runtime.md:735` "Osaurus 5.5–6.3× the faster loader" (5.45×–6.34× as printed) | 5.45–6.34× | 6.68–8.03× | 7.07–8.53× | **gap widens ~25%** |

All three sentences exist to argue that `cold_load_s` alone exaggerates the difference. The
correction makes each argument **stronger**, so none needs to change its direction — but each
printed multiple is now wrong, and wrong in the direction that matters least to the reader (it
flatters the argument being made, which is exactly the kind of number that never gets rechecked).

### 4.2 Sums (`cold_load_s + first_request_s`)

Only the `cold_load_s` half is contaminated. Recomputing the two `§7.2` tables:

| Study | Stated ratio on the sum | Corrected band over the printed extremes |
|---|---|---|
| dense (`dense-jang-study.md:605` "2.1–2.3×") | 1.47–2.16× over the four primary cells as printed | 1.53–2.31× |
| MoE (`moe-jang-study.md:816` "1.6–2.6×") | 1.59–2.32× as printed | 1.68–2.49× |

Both corrected bands sit inside the ranges the docs state, so **the sums survive as printed**. The
correction pushes the ratio **up**, not down: Osaurus's own `cold_load_s` was overstated most
(0.31 s, about 5–7% of a 4.3–6.0 s sum) and vMLX's least (0.07 s, 0.8% of 8.7–9.3 s), so removing
each engine's constant shrinks the Osaurus sum proportionally more and widens the ratio in its
favour. Neither flips the cross-runtime conclusion, which is that the sum favours Osaurus
1.5–2.5×.

### 4.3 One derived throughput that does not survive

`cold-warm-load-attribution-35b.md:15` and `:55` divide 19.00 GiB by the mlx-lm cold/warm
difference and publish **5.40 GB/s** of APFS read throughput:

```
stated:        5.61 − 2.09 = 3.52 s  ->  5.40 GB/s
same start:    3.52 s                ->  5.40 GB/s   (both readings pay one probe: cancels)
cold then warm: (5.61−1.83) − (2.09−1.01) = 2.70 s  ->  7.04 GB/s
```

The two readings are one engine at two cache states, so the probe cost is *almost* the same on both
sides and the published figure is probably right. But the cold reading was the first start of that
session and the warm reload a later one, so if the cold start paid the cold-first-call probe and the
warm reload the warm one, the denominator is 2.70 s and the throughput is **7.04 GB/s, not 5.40** —
a 30% spread, which is wider than the "matches the peak sequential read capability" claim can
absorb. The same subtraction drives the printed `2.68×` and `1.91×` reload speedups (`:48`), which
become **4.06×** and **2.65×** at the warm bound.

This is the one published *physical* quantity in the corpus that rests on a `cold_load_s`
subtraction between two starts, and it is the only place where the constant does not cancel
cleanly. It is flagged, not corrected: deciding it needs the two starts' actual probe times, which
were not recorded per start.

---

## 5. Verdict

**Nothing in this corpus needs to be withdrawn, and eight published sentences need a correction
note.** No recommendation changes: the two that name a winner (`35b-moe-serving.md:191` "Fastest
Cold Load: `stock4bit` in `osaurus`"; the JANG studies' "Osaurus reaches first token sooner on the
sum") hold at both bounds.

The recurring failure is one pattern: **oMLX pays 0.11–0.15 s of probe and its neighbours pay
1.0–1.8 s, so every ordering that put oMLX immediately ahead of mlx-lm or mlx-optiq was created by
the probe.** Seven of the eight flips below are an oMLX-adjacent pair (the eighth is row 8's
Osaurus/mlx-lm inversion); the rest of the table is two ratio sentences repeated across three
documents, one dead heat, and one opening comparison in a paper whose conclusion is right.

### 5.1 Sentences that would need a correction note

Listed, not edited.

| Doc | Lines | Sentence, in substance | Why |
|---|---|---|---|
| `docs/research/2026-09-15-grid-loadability-probe.md` | 101–109 | the four-runtime median table and "vMLX is **7.4× slower to load** than oMLX" | oMLX/optiq inverts at the cold bound; ratio becomes 7.5–7.9×. The section already carries a correction banner at `:91-96`; the banner's own statement "the figures in the table are accurate as `cold_load_s`" is no longer true |
| `docs/research/2026-09-15-grid-loadability-probe.md` | 14 | stock-4bit cell row, oMLX 3.11 s against mlx-lm 4.01 s | level at the warm bound, mlx-lm ahead at cold |
| `docs/research/2026-09-15-cold-load-is-not-one-quantity.md` | 30–35 | the "reported `cold_load_s`" column, oMLX 3.12 < mlx-lm 3.32 | inverts at both bounds; the corrected-ranking table at `:54-59` also needs its levels re-cut (order unchanged) |
| `docs/research/2026-09-15-first-live-run.md` | 39–40, 49–52 | "the cold load … under stock mlx-lm really is about three and a half seconds"; oMLX 3.11 against mlx-lm 3.48 | 1.6–2.5 s, not ~3.5 s, and the pair inverts |
| `docs/research/2026-09-16-moe-loadability-probe.md` | 28–29 | "Cold loads: Osaurus 1.3 s, mlx-lm 1.9–2.5 s, oMLX 1.7–2.2 s, …" | the oMLX/mlx-lm overlap was the probe; corrected they do not overlap, and mlx-lm is 0.06–2.0 s faster, not slower |
| `docs/research/2026-09-20-multiturn-conversation-sweep.md` | 82 | "Startup / Cold Load Time" row: mlxlm 2.14, omlx 3.10, optiq 3.30 | optiq is faster than oMLX; optiq moves third → second and oMLX fourth → third |
| `docs/research/2026-09-20-cold-warm-load-attribution-35b.md` | 15, 23, 48, 55 | the cold-startup column, the `t_ready + t_1` inversion ranking, and the 5.40 GB/s derivation | oMLX/optiq flips at cold; osaurus/mlx-lm no longer inverts at cold; the throughput denominator is 2.70–3.52 s, i.e. 5.40–7.04 GB/s |
| `docs/research/2026-09-20-35b-moe-serving.md` | 62, 191 | stock4bit probe seconds; "Fastest Cold Load" row and its interior order | oMLX/optiq inverts. The recommendation itself stands |
| `docs/research/2026-09-17-dense-jang-study.md` | 604–606 | "Ranking on `cold_load_s` alone would name Osaurus **5.5–5.7×** the faster loader" | 6.7–7.4×; the argument strengthens |
| `docs/research/2026-09-17-moe-jang-study.md` | 815–818 | "would name Osaurus 5.5–6.3× the faster loader" | 6.7–8.3×; the argument strengthens |
| `docs/research/2026-09-17-jang-cross-runtime.md` | 734–735 | the same 5.5–6.3× sentence, restated | same |

### 5.2 Sentences that need nothing

Checked and unchanged:

- `docs/interfaces/measurement-core.md:280-295` — states the comparability rule and that ranking on
  `cold_load_s` alone "named oMLX the fastest loader when it is the second slowest to a first
  useful token". Corrected, the true cost orders `mlx-lm < optiq < oMLX < vMLX`, so oMLX is third
  of four — which is what "second slowest" means. Nothing to change; the sentence holds.
- `README.md:66` — defines cold load as its own metric. No cross-engine figure.
- `docs/research/2026-09-17-dense-jang-study.md:597-600` and `:597`'s `§7.2` table, and
  `moe-jang-study.md:799-802`: the `cold_load_s` levels move down by 0.07–0.31 s, and no reading in
  either document turns on them (both say so in place).
- `docs/research/2026-09-24-hardening-validation-grids.md`, `2026-09-25-35b-third-replicate.md`,
  `2026-09-27-concurrency-batching.md` — all three explicitly **refuse** a cross-runtime
  `cold_load_s` ordering (Decision 120 / `report.CROSS_RUNTIME_UNCOMPARABLE`). There is no ordering
  to audit. Their own runs (2026-09-23 onward) are the first that paid the `lsof` inside the
  window, and none of them publishes a level.
- `docs/runtimes/*.md` — capability references. They describe what `cold_load_s` contains and where
  a load lands (e.g. `osaurus.md:874-875`, `vmlx.md:1674-1694`); no cross-engine figure.
- Generated `results/*/grid.md`, `leaderboard.md` and `sweep.md` are results artifacts, not
  publications, and the `grid.md` files carry `decode_tps` only. Their cold-load column, where one
  exists, is a printed leaderboard field and is not an ordering.

---

## 6. What this does not say

- **Nothing here is a measurement.** Every corrected figure is a published figure minus a
  constant measured once on 2026-11-19 on a quiet machine for a different code revision. The
  0.94/1.76 s mlx-lm figure in particular is the *current* `python -m mlx_lm --version`, a cold
  Python import; a September run may have paid more or less depending on page cache and on which
  venv the bare `python` resolved to — a defect of its own, S5-F1, not this one.
- **Nothing about runs after 2026-09-23.** Those paid the `lsof` inside the window, which this
  audit's constant includes and which no published doc's numbers include.
- **Nothing about whether any flipped ordering would flip back on a re-measurement.** The corrected
  ranges for optiq, mlx-lm and oMLX overlap across 1.5–3.0 s; only a rerun settles those four
  pairs. What this audit establishes is that the *published* ordering cannot be defended at both
  bounds, not what the true order is.
- **Nothing about vMLX's 16–18 s cold load.** Its 0.07 s constant is 0.4% of the figure and it is
  last to load in every audited ordering by 6–16 s. No correction here touches it.
- **Osaurus's 0.31 s is used as given** and may understate its in-window cost after 2026-09-19, when
  `await_ready` began calling `lsof` per poll while the spawned pid was dead (§1.2). Every Osaurus
  verdict holds with margin, so the open question does not reach a result.

## Reproducing

Arithmetic only; no runtime, no model.

```
python3 - <<'EOF'
WARM = {"mlx-lm": 0.94, "optiq": 0.96, "osaurus": 0.24, "omlx": 0.04, "vmlx": 0.004}
COLD = {"mlx-lm": 1.76, "optiq": 1.69, "osaurus": 0.24, "omlx": 0.08, "vmlx": 0.004}
LSOF = 0.068
def corrected(engine, value, bound):
    return value - (COLD if bound == "cold" else WARM)[engine] - LSOF
# 3.12 (oMLX) against 3.32 (mlx-lm): +0.20 published, -0.70 warm, -1.48 cold.
print(corrected("omlx", 3.12, "warm"), corrected("mlx-lm", 3.32, "warm"))
print(corrected("omlx", 3.12, "cold"), corrected("mlx-lm", 3.32, "cold"))
EOF
```

Every table above is that function applied to the published columns, with the verdict rule in §1.
Rows marked "Run present? Yes" were re-read from `results/` for this audit and matched the doc to
the rounding it printed; rows marked No cite only what the doc printed, and their run is not on
disk.
