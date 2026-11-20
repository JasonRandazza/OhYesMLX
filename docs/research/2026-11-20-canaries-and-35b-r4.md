# 2026-11-20 day run: five-engine canary, vMLX baseline re-record, 35B replicate r4

Jason authorised a full day of measurement while he was away. The machine was prepared as in `2026-11-20-vmlx-1.6.84-quiet-canaries.md`. Every step was gated on a 5- and 15-minute load average below 3.0. Osaurus was pinned through `scripts/osaurus-pin.sh` for both of its runs and restored byte-exact afterwards, verified with `cmp`; the host's idle residency of 30 was confirmed after the last run.

**Raw data.**
- `results/canary/20261120T190622Z-vmlx`: the baseline record.
- `results/canary/20261120T19{1332,1824,2256,2641,3043}Z-*`: the five-engine canary.
- `results/harden-35b-r4/`: the 35B grid, 15 cells × 3 workloads, all PASS, on `main` at `34c973b`.

## 1. vMLX canary baseline re-recorded

At Jason's request, `ohyesmlx/engines-tested.json` vMLX now holds **81.67 tok/s and 0.1843 s TTFT at 1.6.84** (recorded 2026-11-20). The five-engine run 25 minutes later read 82.16 tok/s and 0.1818 s, which is "no effect".

The morning's three quiet runs read 77.3–78.7 tok/s. So vMLX at a fixed version differs by about 5% between the morning and the afternoon of one quiet day. The new baseline sits at the high end of that spread, as the old 73.40 sat at the low end.

## 2. Five-engine canary (verdicts only, no baselines written except vMLX's)

| Engine | Version measured | Verdict | decode now / baseline | TTFT now / baseline | Baseline from |
|---|---|---|---|---|---|
| oMLX | 0.7.3 | no effect | 83.07 / 83.25 | 0.171 / 0.176 | 2026-11-02, 0.7.3 |
| vMLX | 1.6.84 | no effect | 82.16 / 81.67 | 0.182 / 0.184 | 2026-11-20, 1.6.84 |
| mlx-lm | 0.31.3 | moved −7.9% (TTFT) | 68.76 / 67.07 | 0.227 / 0.246 | 2026-10-29, 0.31.3 |
| Osaurus | 0.25.33 | moved +10.6% (decode) | 66.22 / 59.87 | 0.289 / 0.308 | 2026-11-19, 0.25.33 |
| OptiQ | **0.5.13** | moved +41.1% (TTFT) | 75.42 / 76.88 | 0.233 / 0.165 | 2026-10-29, **0.7.8** |

- **OptiQ's baseline is not comparable.** It was recorded on the global 0.7.8 install. Since 05-07 the harness runs the 0.5.13 lab copy, so the verdict compares two builds.
- **mlx-lm's baseline predates 05-07.** Before 05-07 the mlx-lm control could resolve the OptiQ lab venv's mlx 0.32.4 (S5-F1); today it runs mlx 0.32.2. That is a candidate cause for the TTFT difference, not an established one.
- **Osaurus moved at the same version** between 2026-11-19 and today.

**What this shows about the canary.** A single run per engine, held against a single-run baseline, moves 5–10% between sessions at a fixed version. That is wider than `canary.NOISE_FLOOR` (5%). Three of today's five "moved" verdicts trace to baseline conditions rather than to a version change. How to fix that is a methodology decision for Jason; options include multi-run baselines and a per-engine floor.

## 3. 35B replicate r4 (Qwen3.6-35B-A3B; `scripts/run_grid_35b.sh`, `--study format`, cache off)

The decode tok/s for each cell, across the three runs on disk:
- **09-20:** `grid-35b`.
- **09-25:** `harden-35b-r3`.
- **11-20:** `harden-35b-r4`.

| Cell | 09-20 | 09-25 r3 | 11-20 r4 | r4 vs r3 | Versions r3 → r4 |
|---|---|---|---|---|---|
| stock4bit / mlx-lm | 64.1 | 78.3 | 67.2 | −14.2% | 0.31.3 → 0.31.3 |
| oq4 / mlx-lm | 59.3 | 69.2 | 60.8 | −12.1% | |
| optiq / mlx-lm | 59.1 | 67.5 | 58.8 | −12.8% | |
| stock4bit / OptiQ | 66.6 | 79.4 | 70.6 | −11.1% | 0.5.13 → 0.5.13 |
| oq4 / OptiQ | 59.2 | 70.1 | 63.2 | −9.8% | |
| optiq / OptiQ | 56.3 | 67.2 | 59.5 | −11.5% | |
| stock4bit / oMLX | 67.9 | 82.2 | 95.2 | +15.8% | 0.6.4 → 0.7.3 |
| oq4 / oMLX | 62.0 | 73.6 | 83.7 | +13.7% | |
| optiq / oMLX | 60.2 | 70.4 | 75.6 | +7.4% | |
| stock4bit / vMLX | 66.4 | 75.2 | 75.0 | −0.3% | 1.6.59 → 1.6.84 |
| oq4 / vMLX | 63.8 | 66.2 | 68.0 | +2.8% | |
| optiq / vMLX | 56.5 | 58.6 | 58.8 | +0.3% | |
| jangtq4 / vMLX | 58.7 | 60.5 | 58.9 | −2.7% | |
| stock4bit / Osaurus | 58.1 | 59.6 | 54.8 | −8.0% | 0.25.12 → 0.25.33 |
| oq4 / Osaurus | 54.1 | 56.1 | 52.6 | −6.4% | |
| optiq / Osaurus | 55.9 | 57.4 | 54.6 | −5.0% | |

### What holds

**Every format ordering within a runtime holds.** This is the format axis, the project's headline.

| Runtime | Ordering, both r3 and r4 |
|---|---|
| mlx-lm | stock4bit > oq4 > optiq |
| OptiQ | stock4bit > oq4 > optiq |
| oMLX | stock4bit > oq4 > optiq |
| Osaurus | stock4bit > optiq > oq4 |
| vMLX | stock4bit > oq4 > {jangtq4, optiq} |

In vMLX, jangtq4 and optiq read 58.9 against 58.8, a dead heat; in r3 they read 60.5 against 58.6.

### What moved

- **mlx-lm and OptiQ fell 10–19% at unchanged versions.** This is on every workload, and they fell back to within about 6% of the 09-20 grid. Decision 127 recorded that r2 and r3 read 10–26% *above* 09-20 for mlx-lm, oMLX and OptiQ. For mlx-lm and OptiQ, r4 is the 09-20 level again, so the r2/r3 level shift was the outlier.
  - mlx-lm now runs mlx 0.32.2, its own venv, where r3 predates the 05-07 lab-PATH fix. But OptiQ (mlx 0.32.4) fell by the same amount, so mlx core alone does not explain it.
  - The cause is **not established**.
- **oMLX rose 7–16% in decode, and its TTFT more than halved** (0.42 → 0.17–0.20 s), across 0.6.4 → 0.7.3. That is consistent with a version effect. The canary's 4B baselines start at 0.7.3, so it never compared 0.6.4 with 0.7.3.
- **Osaurus fell 5–8%** across 0.25.12 → 0.25.33.
- **vMLX decode is flat** across 1.6.59 → 1.6.84. Its prefill-workload decode rose 6–17%.

**Consequence for the runtime axis at 35B:** the cross-runtime decode order is not stable between replicates.

| Run | stock4bit decode order |
|---|---|
| r3 | oMLX > OptiQ > mlx-lm > vMLX > Osaurus |
| r4 | oMLX > vMLX > OptiQ > mlx-lm > Osaurus |

Any published 35B runtime-axis ranking below the top position should be read against this. Deciding which documents need a note is Jason's call; none is edited here.

### Cold load at 35B

r4 is the first 35B run on the corrected clock (05-07). Its `cold_load_s` levels are mlx-lm 1.1–2.3 s, OptiQ 2.1 s, oMLX 2.1–3.1 s, Osaurus 1.0 s and vMLX 13.2–19.2 s.

The vMLX row qualifies this morning's finding. Against **1.6.82 at 4B**, 1.6.84 shows no cold-load regression. Against **1.6.59 at 35B** (r3: 8.2–10.2 s), 1.6.84 loads **4–9 s slower** (13.2–19.2 s). S5-F2's 0.07 s cannot account for that, and nothing here separates page-cache state from version.

Cross-runtime `cold_load_s` remains uncomparable for ranking (Decision 120); these are levels within a runtime.

## Open, for Jason

1. **Canary baselines.** OptiQ's is from the wrong build, 0.7.8 where the harness runs 0.5.13. mlx-lm's predates 05-07. Osaurus's reads 10% low. Re-record all three, and decide whether a baseline should be the median of several runs.
2. **35B runtime-axis claims.** The order below oMLX changed between r3 and r4. Should the 35B papers get a note citing r4?
3. **vMLX 1.6.84 cold load at 35B (+4–9 s against 1.6.59).** A page-cache-controlled probe (purge, then load) would separate cache state from version.
