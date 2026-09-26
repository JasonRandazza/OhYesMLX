# Hardening validation: the three published grids, re-run on the hardened harness

**Date:** 2026-09-24 (run 2026-09-23 23:18 → 2026-09-24 05:37 EDT)
**Milestone:** v3.1 Hardening, after Phases 1 and 2
**Harness:** 0.3.0, `source_sha256 07387e20…d5604` (commit `17b3791`), identical in every column
**Runner:** `scripts/run_harden_validation.sh` → `results/harden-2026-09-23/grid-{35b,dense,moe}/`
**Author:** Claude Opus coordinator

## Why this run exists

Phases 1 and 2 of the hardening milestone changed what the harness does on real runtimes:
residency checks and the stray-Osaurus refusal (B1–B4), persist-on-failure (C1–C4), one-chunk
timing and the two-delta domain (A2), OptiQ sampler pins (A6), the harness revision in every
header (D2), the reasoning-channel label (A5), no cross-runtime ordering on `peak_mb` and
`cold_load_s` (A7), end-to-end latency percentiles (D1) and the unknown-version join refusal
(D3). Every one of those had passing unit tests and none had met a live runtime. This run
re-executes the three published grids **unchanged** (same gridspecs, same runner scripts,
same pins; only the output directory moved) so the fixes meet real servers, and so each
published grid gets an independent replicate.

## What ran

| grid | runner | model(s) | columns | wall clock | exit |
|---|---|---|---|---|---|
| 35B MoE | `run_grid_35b.sh`, `--cache-state off` | Qwen3.6-35B-A3B × 4 formats | mlxlm, omlx, optiq, vmlx, osaurus | 23:18 → 01:36 | 0 |
| dense | `run_grid.sh` | Qwen3.5-4B × 5 formats | same five | 01:41 → 04:09 | 0 |
| MoE | `run_grid_moe.sh` | LFM2.5-8B-A1B × 5 formats | same five | 04:14 → 05:37 | 0 |

Runtime versions: mlx-lm 0.31.3, oMLX 0.6.4, mlx-optiq 0.5.13, vMLX 1.6.59, Osaurus 0.25.12.
No row carries an `unknown:` version, so all three grids pass the D3 join guard.

### Conditions

- Google Drive (sustained ~100% CPU) was quit before the start; the stray Osaurus app
  (`--launched-by-cli`, see below) was swept by the runner before the first column.
- **Contention during the first column.** From about 23:18 to 23:30 Jason deleted Time Machine
  local snapshots and ran an orphaned-process reaper while the 35B mlx-lm column was measuring.
  That is a stated defect in conditions under AGENTS.md. The column is **kept**, not discarded:
  contention can only slow a cell, and this column came out *faster* than the published one with
  no drift marker on its `chat` or `decode` rows, so the contention left no visible mark. It
  is named here so that a reader who doubts it knows where to look
  (`grid-35b/20260924T031838Z-format`).
- Nothing else ran from 23:30 until the end of the run: no git, no tests, no workers.

## Results

### The harness changes held on live runtimes

- Every column started, measured and released its port. No stray-Osaurus refusal fired after
  the runner's sweep, and no cleanup or SIGKILL failure was raised.
- Every leaderboard carries the harness sha, and the grid join accepted all five columns
  because the sha is identical.
- E2E P50/P90/P99 are populated wherever TTFT percentiles are, e.g. `stock4bit__mlxlm` 35B:
  `chat` 1.833 / 1.853 / 1.863 s, `decode` 7.091 / 7.209 / 7.216 s.
- The only FAIL in any grid is the same one the published MoE grid carries (`optiq × osaurus`).

### MoE grid: replicates

Every cell is within about 1.5% of the published grid (`results/grid-moe/`). Examples on
`decode`: stock4bit mlxlm 154.3 → 156.0, omlx 159.6 → 160.7, vmlx 133.3 → 131.9; oq4 osaurus
145.4 → 145.9. Format orderings within every runtime are unchanged.

### Dense grid: replicates

The published dense grid (`results/grid/`, the five directories its provenance names) against
this run, `decode` workload:

| format | mlxlm | omlx | optiq | vmlx | osaurus |
|---|---|---|---|---|---|
| stock4bit | 70.1 → 70.3 | 75.9 → 73.6 | 77.8 → 74.7 | 75.6 → 75.0 | — |
| oq4 | 67.0 → 69.3 | 75.5 → 73.0 | 76.2 → 70.4 | 73.3 → 68.2 | 68.7 → 68.5 |
| oq4e | 64.1 → 64.8 | 69.3 → 66.7 | 69.5 → 65.2 | 66.7 → 64.7 | 64.7 → 64.4 |
| optiq | 59.6 → 61.1 | 67.3 → 63.8 | 66.6 → 62.5 | — | 63.5 → 62.6 |

Most cells are within 4%, and the largest move (oq4 on optiq, −7.6%) keeps its place. **The
format ordering inside every runtime is identical to the published one**, which is the claim
the format axis makes.

### 35B grid: orderings replicate, levels do not

The format ordering within each runtime replicates on `decode` in every column. The absolute
rates do not, stock4bit row, published → this run:

| workload | mlxlm | omlx | optiq | vmlx | osaurus |
|---|---|---|---|---|---|
| chat | 65.0 → 82.4 | 70.3 → 87.4 | 70.1 → 77.4 | 65.7 → 71.7 | 63.8 → 61.9 |
| prefill | 64.5 → 83.7 | 84.1 → 95.3 | 76.7 → 83.3 | 63.8 → 70.3 | 72.8 → 66.9 |
| decode | 64.1 → 75.2 | 67.9 → 74.1 | 66.6 → 73.7 | 66.4 → 71.7 | 58.1 → 55.8 |

The four Python runtimes are 8–27% faster; Osaurus is 3–8% slower. **This is not a formula
change:** rendering the published 35B run directories with the current code reproduces the
published figures exactly (65.0, 70.3, 70.1, 65.7, 63.8 on `chat`), so the difference is in the
measurements. The cause is not established. mlx-lm (0.31.3), oMLX (0.6.4) and vMLX (1.6.59)
report the same version in both runs and moved +8% to +27%, so a runtime upgrade does not explain
them. OptiQ (0.5.6 → 0.5.13) and Osaurus (0.25.9 → 0.25.12) did change version, so for those two
columns the version and the night are confounded, and **their columns cannot be joined with the
published ones** (the join's version guard refuses that). Untested candidates for the other three:
different host load during the 2026-09-20 run, whose conditions were not recorded, and a thermal
state that differed between the two nights.
Because the runtime-axis *levels* moved by up to a quarter while the format-axis *orderings*
held, the 35B paper's cross-runtime statements are the ones this puts in doubt, and a third
35B replicate is the cheapest way to settle which night was the outlier.

### New finding: OptiQ is the only runtime timed on content

With the A5 label in place, every Qwen3.5/3.6 and LFM2.5 row is `timed on reasoning channel:
9 of 9` on mlx-lm, oMLX, vMLX and Osaurus, and **no OptiQ row is**, on the dense and 35B
grids. The label also applies retroactively: rendering the published run directories with the
current code shows the same split, so it was always there. (On the MoE grid OptiQ is reasoning-timed too.)

What it means per metric:

- **decode tok/s and ITL** time the same generated tokens whichever channel carries them, so
  the runtime axis stays readable for them. That holds as long as token counts are taken
  from the same stream, which is worth one check.
- **TTFT** is not the same quantity across such a row: on a reasoning-timed runtime it is the
  first reasoning token; on OptiQ it is the first content token, which for a thinking model
  may include the whole reasoning trace if OptiQ puts the trace inline. A runtime-axis TTFT
  ordering on these models mixes two definitions. That is Decision 119's label doing its job;
  whether the runtime axis should also *refuse* a TTFT ordering across mixed channels (as A7
  does for `peak_mb`) is a decision for Jason.
- Osaurus on the dense grid is reasoning-timed now and was content-timed in the published run
  (68.7 unlabelled). Its version moved from 0.25.4 to 0.25.12 between the runs, so this is a runtime
  behaviour change, recorded here rather than explained.

## The stray Osaurus app

The app kept reappearing during the session with `--launched-by-cli` and launchd as its parent.
Cause found: `~/.commandcode/mcp.json` registered `osaurus mcp`, so every Command Code session,
including each `cc-agent` worker, launched the app; it was also an enabled Login Item. Jason
removed both on 2026-09-23. Written up in `docs/runtimes/osaurus.md` §1.2.

## What this does not claim

- It does not explain the 35B level shift. It shows the shift is in the measurements, not the
  code.
- It is one replicate per grid. "Replicates" above means the orderings and most levels
  agree across two nights, not that the numbers are pinned.
- Nothing here is an accuracy result.

## Follow-ups

1. A third 35B replicate on a quiet machine, to decide which night was the outlier (≈2.3 h).
2. Decision: should the runtime axis refuse TTFT orderings across rows with mixed timing channels?
3. Check that OptiQ's completion-token count and the reasoning-timed runtimes' counts cover the
   same tokens, before reading decode tok/s across that boundary.

---

## Update 2026-09-25: Follow-up 2 decided, and both refusals extended to the leaderboard (`f998dcd`)

**Follow-up 2 was decided as Decision 122** (2026-09-24): a runtime-axis ordering of
`ttft_p50_s` or `prefill_tps` over rows that were not all timed on one channel prints its values
with no positions and names no best cell — `report.CHANNEL_DEPENDENT_RANKS`, with
`_uncomparable_across_runtimes` enforcing it and `_channel_note` saying which rows mixed, landed in
`report.py` as `e57775d`. That is the runtime axis doing what this paper's §"New finding" said A7
does for `peak_mb`.

**`f998dcd` (2026-09-25) then gave the single-run leaderboard the same treatment**: a runtime-axis
table in `render_markdown` over a rank in `CROSS_RUNTIME_UNCOMPARABLE` or a channel-dependent rank
over mixed rows lists its rows alphabetically with the rank column empty and prints the grid's own
note, and a first-token-latency table over concurrent rows carries `CONCURRENCY_TTFT_SENTENCE`.
Before it, a single run's runtime-axis table numbered `peak_mb` 1 and 2 and published the sampler's
page accounting as a ranking. Nothing in this paper's numbers moves; what changed is the rendering
of the columns it published.

Follow-up 1 (a third 35B replicate) is still open and is carried in `.paul/STATE.md`, Deferred
Issues. Follow-up 3 is still open.

---

## Update 2026-09-25 (evening): Follow-up 1 closed — the third 35B replicate settles the level shift

The third 35B replicate ran 18:17:41 → 20:24:04 EDT on 2026-09-25 into `results/harden-35b-r3/`
(same runner, gridspec, pins and runtime versions as the r2 columns here) and is written up in
`docs/research/2026-09-25-35b-third-replicate.md`. Nothing in this paper's text or numbers changes;
this note records where its open item lands.

- **"Orderings replicate, levels do not" resolves against the published grid.** Over the 9–12
  shared cell-workloads, r2 and r3 agree within 2.7–6.8% per runtime, and both put mlx-lm, oMLX
  and OptiQ 10–26% above the published 09-20 levels. **The published levels for those three
  runtimes are the outlier; finding 17's cross-runtime levels are superseded by the r2/r3 pair,
  and its format orderings stand.**
- **The cause of the published shortfall is still not established.** This paper's two untested
  candidates (host load on the unrecorded 09-20 night, a different thermal state) survive as
  candidates. r3 is uniformly 2.7–6.8% above r2 and ran in an evening with desktop applications
  open — a third uncontrolled condition, not the quiet reference the follow-up asked for.
- The stock4bit row of §"35B grid: orderings replicate, levels do not" becomes published → r2 → r3
  in the new paper, together with the per-runtime ratio table this note is built on; the r2 figures
  printed here are unchanged. Every figure was re-derived from the three `grid.md` files, and the
  three grids were re-rendered with the current tree: r2's and r3's table sections are
  byte-identical to their committed files, and the published grid's reproduces its figures with the
  timing-channel labels restored.

Follow-up 2 (Decision 122, above) and Follow-up 3 are unaffected.
