# Phase 5 — the joined grid, and why its runtime axis cannot be published yet

Date: 2026-09-16. Machine: MacBook Pro, M2 Max, 64 GiB unified memory, macOS 26.6.2.
Run directories (gitignored): `results/grid/20260916T004734Z-format` (mlx-lm),
`…T010139Z` (oMLX), `…T011536Z` (mlx-optiq), `…T012842Z` (vMLX), `…T014210Z` (Osaurus).
Rendered with `ohyesmlx grid <the five directories>`.

**Zero measurement.** Nothing here started a runtime or loaded a model. Phase 5 reads back
what Phase 3 already wrote.

## What this phase was for

Phase 3 measured the grid one column at a time: five invocations of
`ohyesmlx run --study format`, each holding one runtime constant and varying the
quantization format, twelve cells apiece, **60 of 60 PASS**. Five run directories, five
leaderboards, and no join.

The decision pinned in Phase 3 says what those five files contain:

> A grid contains both axes as its slices. Rows (one format, many runtimes) are the runtime
> axis; columns (one runtime, many formats) are the format axis; the best cell is a
> recommendation. Attribute within a row or column, recommend across the whole.

The columns were read in Phase 3 — that is where the format ordering came from. **The rows
were never read.** The runtime axis had been measured in full, sat in five files, and no
tool in this project could open them. That is the third time this project has found a
quantity recorded and unread: `runtime_version` before `7945067`, `measured_drift` before
`40a8a0e`, and now the entire runtime axis.

So Phase 5 is a join, not a campaign. The original roadmap wrote it as a separate
runtime-axis measurement; that campaign would have re-measured data already on disk.

## What was built

**`measure.load_run(path)`** — the exact inverse of `write_jsonl`. A run directory, or the
`results.jsonl` inside it, comes back as its header and one `CellResult` per line.
`Cell(**record["cell"])` and `Observation(**obs)` are `asdict`'s inverse by construction,
which is why `_record` was written with no derived fields inside either object.

The three derived fields a *record* carries — `measured_count`, `warmup_count`, `drift` —
are deliberately not read back. They are recomputed from the observations they summarize.
A loader that trusted them would let a hand-edited file publish a drift its own samples do
not support. They stay in the file for a reader with `jq`; the loader ignores them.

Verified by round-trip against all 60 real records: `_record(load_run(p)[1][i])` equals the
line it came from, dict for dict, in every column.

**`report.render_grid(runs, rank=…)`** — formats down, runtimes across, one table per
workload, never averaged across them. Four entry states that must not collapse into each
other:

| entry | means |
|---|---|
| a number | a measured cell that cleared every floor |
| `no value` | a cell that cleared every floor and has no value for *this* metric |
| `FAIL` | a measured cell that did not clear one |
| `—` | a combination no run measured |

The matrix is ragged by design — no runtime loads JANG and the other formats both — so `—`
is the ordinary case. The second state exists because `_number` renders `None` as the same
em dash as the fourth: a cell that produced language, cleared every floor, and streamed its
whole completion in one content delta has no decode rate, and filing it beside the
combinations that do not exist would be a different claim entirely.

**Four join guards.** Joining five separately-invoked runs is the one place this project
could vary two things without noticing, so the join refuses rather than renders when the
pins disagree, when one cell appears in two directories, when one format label points at two
artifacts, or when one runtime appears at two versions. Each names both run directories and
the field that disagreed. There is no latest-wins rule: which run is newer is not which run
is right.

**`ohyesmlx grid <run-dir>…`** takes directories one by one. No glob, no `--all`:
`results/grid/` holds thirteen run directories from three sessions, and a grid assembled by
wildcard would silently join columns that never belonged together.

Eight of those thirteen predate `first_request_workload_id`, and the loader **refuses them
by line number** rather than defaulting the field. A default would render those cells as
cold visits that made no request — the exact false claim that field was added to kill.

## The grid, decode workload, `decode_tps`

| format | mlx-lm | oMLX | mlx-optiq | vMLX | Osaurus |
|---|---|---|---|---|---|
| stock4bit | 66.6 (drift +21.2%) | 75.9 | 77.5 | 74.9 | — |
| oq4 | 62.7 (drift +13.0%) | 75.5 | 75.8 | 72.8 | 66.9 |
| oq4e | 61.7 (drift +11.5%) | 68.0 | 69.9 | 66.1 | 64.7 |
| optiq | 59.8 (drift +14.0%) | 65.1 | 66.7 | — | 63.7 |
| jang4s | — | — | — | 78.2 | 69.5 |

The columns are Phase 3's result and are unchanged: `stock4bit > oq4 > oq4e > OptiQ`,
identically in mlx-lm, oMLX and mlx-optiq, zero inversions in five columns.

## The runtime axis, read for the first time

Each row, ordered by `decode_tps`, one format held constant:

**decode** (512 tokens, the sustained shape)

- `stock4bit`: mlx-optiq 77.5 > oMLX 75.9 > vMLX 74.9 > mlx-lm 66.6
- `oq4`: mlx-optiq 75.8 > oMLX 75.5 > vMLX 72.8 > Osaurus 66.9 > mlx-lm 62.7
- `oq4e`: mlx-optiq 69.9 > oMLX 68.0 > vMLX 66.1 > Osaurus 64.7 > mlx-lm 61.7
- `optiq`: mlx-optiq 66.7 > oMLX 65.1 > Osaurus 63.7 > mlx-lm 59.8
- `jang4s`: vMLX 78.2 > Osaurus 69.5

**chat** (128 tokens)

- `stock4bit`: oMLX 87.9 > mlx-optiq 84.0 > vMLX 81.2 > mlx-lm 76.0
- `oq4`: oMLX 87.1 > mlx-optiq 82.4 > vMLX 80.6 > Osaurus 71.8 > mlx-lm 67.3
- `oq4e`: oMLX 79.7 > mlx-optiq 75.6 > vMLX 72.4 > Osaurus 71.8 > mlx-lm 62.9
- `optiq`: oMLX 75.4 > mlx-optiq 71.4 > Osaurus 70.0 > mlx-lm 59.3
- `jang4s`: vMLX 80.5 > Osaurus 77.3

Two things stand out, and only one of them survives scrutiny.

**The workload changes the winner.** mlx-optiq leads every decode row; oMLX leads every chat
row. Same cells, same session, same pins — the only difference is a 128-token cap against a
512-token one. This is the "three workloads, never averaged" decision showing up in the
output: a blended score would have hidden a real disagreement between two shapes behind a
single number that describes neither.

**mlx-lm is last in eleven of fourteen orderings.** This is the result that does not
survive, and the next section is why.

## The finding: this ordering is the warmup budget, not the runtimes

mlx-lm is the drift-contaminated column: `+17.0%` median `change_pct` across its own
measurement window, 11 of 12 rows over the `5.0%` annotation threshold, every sign positive
— cells getting *faster* across their window, which is insufficient warmup, not thermal
throttle.

`measured_drift` splits each cell's measured samples in half and compares the medians. The
published figure is the median of all five. Re-rank the decode rows on each cell's
**late-window** median instead — the half taken after the cell had been running longest:

| format | published (median of 5) | late-window median |
|---|---|---|
| stock4bit | oMLX > mlx-optiq > vMLX > **mlx-lm (4th)** | oMLX 77.4 ≈ **mlx-lm 77.4 (1st–2nd)** > mlx-optiq 77.2 > vMLX 75.2 |
| oq4 | … > Osaurus > **mlx-lm (5th)** | mlx-optiq 75.8 > oMLX 75.1 > vMLX 72.8 > **mlx-lm 69.5 (4th)** > Osaurus 68.5 |
| oq4e | … > Osaurus > **mlx-lm (5th)** | mlx-optiq 69.3 > oMLX 68.5 > **mlx-lm 68.0 (3rd)** > vMLX 66.5 > Osaurus 64.7 |
| optiq | … > Osaurus > **mlx-lm (4th)** | oMLX 67.2 > mlx-optiq 66.8 > **mlx-lm 66.7 (3rd)** > Osaurus 63.6 |

mlx-lm moves from last in every row to first, fourth, third and third. On `stock4bit` it
goes from 66.6 — a clear last place — to 77.4, which ties the leader.

**The runtime axis as published is measuring how long each runtime takes to warm up, and
calling it how fast each runtime serves.** The harness applies one warmup budget (3 requests)
to all five runtimes; mlx-lm has not finished warming when its measured window opens and the
other four have. Nothing about that is a property of mlx-lm's serving speed.

This is not a reason to distrust the *format* axis. Within the mlx-lm column the runtime is
held constant, so the warmup shortfall lands on every format in that column — and the format
ordering there is identical to the one oMLX and mlx-optiq produce from a clean window. It is
specifically the **cross-runtime** reading that the warmup budget contaminates, because that
is the reading where the warmup budget is the variable and nobody declared it one.

**Do not read the late-window column as the corrected answer.** With `measured = 5`,
`measured_drift` compares a median of two against a median of two and discards the middle
sample. The direction is trustworthy — it is unanimous across 60 rows — but a single row's
magnitude is not, and a ranking built from medians-of-two is not a ranking. What the table
above establishes is that **the ordering is not stable under a defensible change in how the
window is taken**, which is enough to refuse to publish it and not enough to replace it.

### What settles it

A per-runtime warmup budget, and a re-run of at least the mlx-lm column at a budget long
enough that its drift lands where the other four already do (`+2.6 / −0.0 / +0.5 / +1.0%`).
Raising the *global* budget would pay mlx-lm's cost on four runtimes that do not need it and
lengthen a 67-minute grid for nothing. Raising `measured` above 5 at the same time would
make each `change_pct` a comparison of real medians rather than of pairs.

Until then the runtime axis is **measured, joined, and not publishable**. The format axis is
unaffected.

## The eighth measurement-validity defect: `peak_mb` is not one quantity across runtimes

The join exposed this the moment a row was ordered by memory. Decode workload, `footprint`
against `vmmap`'s resident size and the weights on disk:

| runtime | footprint MB | resident MB | weights MB |
|---|---|---|---|
| mlx-lm | 2867–3789 | 3379–4198 | 3061–4044 |
| oMLX | 3686–4198 | 4403–4813 | 3061–4044 |
| mlx-optiq | 2970–3789 | 3379–4198 | 3061–4044 |
| vMLX | 3686 | 4096–4301 | 3061–3207 |
| **Osaurus** | **1331–2560** | 2867–3994 | 3161–4044 |

In four columns `footprint` lands within a few percent of the weight bytes. In the Osaurus
column it lands at roughly **half** of them — below the size of the weights the process is
serving, which a process holding those weights in anonymous memory cannot do — while that
same column's resident size sits right at the weights.

The direction is that Osaurus's weight pages are file-backed and clean, and `footprint` does
not count them. That is a hypothesis about the sampler, not a finding about the runtime, and
until it is probed the headline "Osaurus uses half the memory of every other runtime" is a
claim about `footprint`.

This is the same shape as `cold_load_s`, which Phase 3 already established is not one
quantity across runtimes because oMLX loads lazily and hides 3.08–3.85 s inside request #1.
Both are now in `report.CROSS_RUNTIME_UNCOMPARABLE`: a **runtime-axis** ordering by either
metric prints the reason it cannot be read as a ranking, directly above the ordering. A
format-axis ordering by them is untouched and correct — within one column the runtime is
held constant, so whatever the number leaves out, it leaves out identically.

## Prior art

`mlx-Chronos` already publishes a protocol for the runtime axis. This project's contribution
on that axis is the specific runtime set and the format-held-constant discipline, not the
idea, and any write-up that reaches publication says so and cites it rather than presenting
the axis as new ground. The format axis is the unoccupied ground; the runtime axis is a
second reading of the same measurement, offered as corroboration.

## What this phase did not verify

- No runtime was started and no model was loaded.
- The eight pre-`first_request_workload_id` run directories were not read at all.
- Join guards 3 (one label, two artifacts) and 4 (one runtime, two versions) were exercised
  only against synthetic runs. No real pair could trip them: every would-be pair involves an
  09-15 directory the loader refuses on schema.
- Guard 4 compares `runtime_version` as an exact string, and mlx-optiq reports
  `"mlx-optiq, version 0.5.6"` rather than a bare `0.5.6`. Uniform within its column today,
  so the guard does not misfire; a runtime that rephrases its `--version` output would read
  as a version change.
- The prefill workload's Osaurus figures are taken with its KV prefix cache **on** — it
  cannot be disabled from any command line — and Osaurus rises in the prefill rows in a way
  it does not in chat or decode. Phase 3 isolated that as an 8.3× cache effect on prefill.
  Nothing in this phase re-examined it.
