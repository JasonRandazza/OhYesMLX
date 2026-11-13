# Grid and warmup — interface shapes

How the joined grid is assembled, and how a cell's warmup window is measured rather than pinned.

## Phase 5 — the joined grid

Phase 3 measured the grid one column at a time: five invocations of `ohyesmlx run --study
format`, five run directories, each holding one runtime's twelve rows. The grid exists only
as five files that nobody joins. Phase 5 joins them.

The reading is the one Phase 3 pinned: a **column** (one runtime, many formats) is the
format axis, a **row** (one format, many runtimes) is the runtime axis, and the best cell
across the whole grid is a *recommendation*, never an attribution. Nothing in this phase
re-measures anything.

### `ohyesmlx/measure.py` — reading a run back

```python
def load_run(path) -> tuple[dict, list[CellResult]]: ...
# path: a run directory or its results.jsonl.
# Returns (run_header, results) — line 1 of the file, then one CellResult per line after it.
```

The exact inverse of `write_results`/`_record`. `Cell(**record["cell"])` and
`Observation(**obs)` round-trip by construction, which is why the record was written with
`asdict` and no derived fields inside those two objects.

The three **derived** fields in a record — `measured_count`, `warmup_count`, `drift` — are
*not* read back onto the object. They are recomputed from the observations that carry them.
A loader that read them would let a hand-edited file publish a drift that its own samples do
not support. Their presence in the file is for a reader with `jq`, not for this function.

The round-trip is testable and must be tested: `_record(load_run(p)[1][i])` equals the i-th
record on disk, byte for byte, for a real grid run dir.

### `ohyesmlx/report.py` — the grid

```python
def render_grid(runs, *, rank: str = DEFAULT_RANK) -> str: ...
# runs: list[tuple[str, dict, list[dict]]] — (run label, run header, summarize()'d rows)
```

One grid per workload, never averaged across them — the same rule that governs the
leaderboard. Rows are format labels, columns are runtime names, and each entry is the
`rank` metric for that cell.

**Five entry states, and they must not render alike:**

| state | renders | means |
|---|---|---|
| measured, PASS | the number | a result |
| PASS, no value for *this* metric | `no value` | the cell cleared every floor; the metric has no domain on this stream |
| measured, not PASS | `FAIL` | the cell ran and did not clear a floor |
| not measured, `N/A` | `N/A` | the cell was planned and the runtime could not be driven into it; the reason is on the row in its own run's leaderboard |
| never measured | `—` | that combination does not exist |

The second state exists because `_number` renders `None` as the same em dash as the
fifth. A cell that produced language, cleared the floors, and streamed its whole
completion in one content delta has no decode rate — `order_rows` already ranks such a row
last with a note rather than excluding it, and the grid must not be the one place that
distinction collapses back into "does not exist".

The fourth is its own state for the same reason one step further out: a cell the runtime could
not be driven into was on the plan, so rendering it as the dash a combination nobody ran gets
files a refusal beside an omission — which is what the KV-quant sweep did, where every
non-OptiQ codec cell is `N/A`, until 2026-09-25. `ENTRY_LEGEND` names all five and both joined
tables print it.

The matrix is ragged by nature — no runtime loads JANG and the other formats both — so
`—` is the ordinary case, and a reader who cannot tell it from `FAIL` is reading a
different grid. A drift-annotated cell (`DRIFT_ANNOTATION_PCT`) carries its marker into the
entry beside the number, because a grid that hides what the leaderboard shows is a
downgrade of the same data.

### The join guards

Joining five separately-invoked runs is the one place this project can vary two things
without noticing, so the join refuses rather than renders when:

1. **The pins disagree.** Every run header field — `report.PIN_FIELDS`:
   `temperature`, `seed`, `warmup`, `measured`, `cooldown_s`, `concurrency`,
   `prompt_tokens`, `cache_state`, `kv_quant`, `mtp_depth`, `stream_experts`,
   `quick` — and every workload's `messages` and `max_tokens` must be identical across all
   runs. Columns that answered different prompts are not one grid. An absent `quick` is
   `False` (plan 04-03a), so a run measured before the pin joins one that pinned it `False`.
2. **A cell appears twice.** The same `(label, runtime, workload_id)` from two run
   directories is ambiguous; name both directories and refuse. There is no "latest wins"
   rule, because which run is newer is not which run is right.
3. **One format label points at two artifacts.** Same name, different bytes, across
   columns — the runtime-axis row guard `_held_constant` already makes within a table.
4. **One runtime appears at two versions.** Across columns two *different* runtimes at
   different versions is the grid working as intended; the *same* runtime at 0.25.3 in one
   directory and 0.25.4 in another is the held-constant variable moving, and Osaurus
   measured 1.15x across exactly that step.
5. **A joined row has an unknown runtime version.** A shared check refuses any
   `runtime_version` beginning with `unknown` in `render_grid` or `render_sweep`, naming the
   run directory, cell and value; a join cannot establish that the runtime stayed constant
   when its version is not stated. Single-run leaderboards render these rows unchanged.
6. **The harness source differs.** `_check_harness` compares each header's
   `harness.source_sha256` and refuses a join whose columns were measured by different
   harness source, naming both directories; a header predating the block carries none and is
   skipped. Two revisions of the loop are not one grid.

**A quickbench run is refused before guard 1, on the value rather than a mismatch.** `_check_not_quick`
runs in `render_grid` and `render_sweep` ahead of `_check_pins`, so `ohyesmlx grid` on a single
directory whose header pins `quick: true` refuses, and a quick-vs-quick pair is refused like any
other. The message names the directory and says quickbench results never join the published tables.
A header without the key is an ordinary run: `ABSENT_PINS["quick"]` is `False`, which is what every
run measured before the pin existed did.

Guard 4 compares `runtime_version` as an exact string, after each runtime's
`parse_version`. mlx-optiq's own parser strips the prose off `"mlx-optiq, version 0.5.6"`
so the bare `0.5.6` is what gets recorded (`runtimes.Optiq.parse_version`, commit
`1f61ee2`), which is what keeps the guard comparing versions rather than `--version`
phrasings. Anything not shaped `..., version X` is passed through whole.

Every guard names the offending run directory or both disagreeing directories in its message.
A grid or sweep that refuses must say which
two files disagreed and on what.

### Provenance

The rendered grid states, above the tables: each column's run directory, runtime and
version, and the pins all columns share. That block is the evidence the join was legal, and
it is what makes the grid recomputable by someone holding only the five `results.jsonl`
files.

### `ohyesmlx/cli.py`

```
ohyesmlx grid <run-dir> [<run-dir> ...] [--rank decode_tps] [--out FILE]
```

Explicit directories, never a glob over `results/grid/` — that directory holds thirteen
run dirs from three sessions, and a grid assembled by wildcard would silently join columns
that never belonged together. `--out` defaults to stdout only.

---

## Phase 5 plan 05-02 — warmup is measured, not pinned

The joined grid's runtime axis ordered the five runtimes by how long each takes to warm up
and called it how fast each one serves. mlx-lm is last in 11 of 14 orderings on the
published median and 1st/3rd/3rd/4th on the late-window median — see
`docs/research/2026-09-16-phase5-joined-grid.md`. One warmup budget applied to five
runtimes is the cause: three requests leaves mlx-lm still climbing and the other four
settled.

Raising the global budget is the wrong fix. It pays mlx-lm's cost on four runtimes that do
not need it and lengthens a 67-minute grid for nothing, and it replaces one guessed constant
with a larger guessed constant. **Warmup stops being a pin and becomes a measured property
of the cell.**

### The plateau rule

A workload's warmup window keeps issuing requests until its decode rate stops moving:

```python
MIN_WARMUP = 3            # the floor a caller pinning a fixed budget may not go below
WARMUP_WINDOW = 5         # rates per window; the rule compares the medians of two
WARMUP_CAP = 20           # the window closes here whether or not it settled
WARMUP_PLATEAU_PCT = 3.0  # the step between two window medians
```

The cell is warm when the median of the last `WARMUP_WINDOW` rates is within
`WARMUP_PLATEAU_PCT` of the median of the `WARMUP_WINDOW` before them. It is a **trend test
and never a variance test** — see "Noise is not unfinished warmup" below. A rate comes from `decode_tps`, the same function every published figure uses; a
warmup observation that carries none cannot settle the window, and the cap is what ends it.

**One window is not enough, measured.** oMLX serving Qwen3.5-4B-oQ4, fourteen identical chat
requests in a flat loop with no harness structure around them, decode tok/s:

```
103.5  102.8  103.3 | 70.8  73.4  75.7  73.6  75.2  75.3  74.6  72.0  73.8  72.9  73.3
```

The machine serves the first three requests from a boost state and then steps down ~29% to
the rate it holds — request 1 spends 1.24 s generating and request 4 spends 1.81 s for the
same 128 tokens, so this is the runtime slowing down and not the stream re-chunking. The
boost phase is **flat**: 0.5% spread. A single-window rule calls that warm at request three,
at a rate 40% above what the cell can sustain, and certifies exactly the three requests the
fixed budget already used while claiming to have verified something. Live, before and after:

| rule | warm declared at | first measured request |
|---|---|---|
| one window | 103.3 | 75.7 (−27%) |
| two windows | 77.0 | 76.1 (−1%) |

So the floor is `2 * WARMUP_WINDOW`, not `MIN_WARMUP`.

**Noise is not unfinished warmup, also measured.** The first cell of the aborted 03:30Z
column — mlx-lm serving stock-4bit, the prefill workload's warmup rates:

```
70.3 74.7 72.5 77.1 71.9 78.6 77.5 73.6 70.2 70.9 75.2 64.8 72.5 71.3 76.8 75.4
```

No trend at all. That cell is warm from request one and simply swings ±8% per request, and a
rule requiring neighbouring rates to agree within 3% can never be satisfied by it: it ran to
the cap, spent sixteen requests learning nothing, and reported "did not settle" about a cell
with nothing left to warm. Per-request noise is a property of the workload — a 128-token chat
varies far more than a 512-token decode — and reading it as unfinished warmup conflates two
different things, which is the conflation this rule exists to undo.

So the test compares **window medians only**, never the spread inside a window, and the window
is five rather than three because a median of three of those rates is itself noise. Live, on
the cell that had capped twice:

| workload | warmups | settled | warm rate | first measured |
|---|---|---|---|---|
| chat | 12 | yes | 77.5 | 78.0 |
| prefill | 10 | yes | 85.1 | 78.2 |
| decode | 11 | yes | 67.0 | 66.8 |

The floor of ten also caught a third thing: under the old floor of six, the decode workload
settled while it was still climbing (measured 64.7 → 66.7 across its window).

`3.0%` sits between the two populations the grid measured — four runtimes settle their whole
*measured* window inside `+2.6 / −0.0 / +0.5 / +1.0%`, and mlx-lm moves `+17.0%` across its.
A plateau tolerance below that spread would chase noise; one above it would call mlx-lm warm
while it was still climbing.

The cap is not a fallback that quietly substitutes for the rule. A window that hit it did
**not** settle, and that is a finding about the cell:

```python
warmup_plateau: bool | None   # new CellResult field, new record field
```

`True` when every warmup window on this row reached the plateau, `False` when any hit the
cap, `None` when no warmup ran. A capped cell that rendered identically to a settled one
would be this project's own recurring defect — a quantity recorded and unread — committed
one more time.

`warmup_count` already records how many requests it took, so the budget each runtime needed
becomes a published number rather than a constant in a source file.

`load_run` reads `warmup_plateau` **leniently** — the first field it did that for, and
`batch_spans`, `lost_visit_reason` and `cold_load_after_lost_visit` are read the same way. A
record written before the rule existed was measured under a fixed budget, so the rule did not
run on it and `None` is exactly true of those rows rather than a default standing in for
something unknown. That is what separates it from `first_request_workload_id`, whose absence is
refused: a default there would claim the cold visit made no request, which is false about rows
whose visit did. A default is honest when the absence is the fact, and the five 2026-09-16 columns
the Phase 5 write-up published stay readable by the tool that published them.

### The pins change, so every column re-runs

The run header's `warmup` becomes the rule rather than a count:

```python
{"mode": "plateau", "window": 5, "floor": 10, "cap": 20, "plateau_pct": 3.0}
```

and `measured` goes `5 → 9`. At 5, `measured_drift` compares a median of two against a
median of two and throws the middle sample away, which is why the drift threshold cannot be
tightened and why a single row's magnitude is untrustworthy. At 9 it compares medians of
four.

Join guard 1 compares both fields, so **a column measured under the new pins cannot join one
measured under the old**. This is not a mlx-lm re-run; it is a full grid re-run, and the
five 2026-09-16 directories become history the moment it starts.

`run_cells(warmup=...)` still accepts an `int` for a fixed budget — a quick run pinning three
requests is still a legal thing to ask for, and it is what most tests want. `"plateau"` is
the default and is what the grid runs.

---

