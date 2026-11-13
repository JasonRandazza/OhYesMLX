# Sweep pins — interface shapes

The Phase 6 sweeps: that a sweep is a pin rather than an axis, and the concurrency, prompt-length, lost-visit and cache-state pins a sweep must honour.

## Phase 6 — a sweep is a pin, not an axis

Full reasoning in `docs/research/2026-09-16-phase6-design.md`. What is settled and pinned:

`--study` names which of a **cell's** two variables a selection may vary, and a cell is
`(format, runtime)`. Concurrency, prompt length and cache state are none of those — they are
properties of how the run drove the cells, which is what the run header holds. So each sweep
is N runs differing in exactly one header pin, joined afterwards, the same shape the grid
already is.

```python
def render_sweep(runs, *, varying: str, rank: str = DEFAULT_RANK) -> str: ...
# varying: the one header field these runs are allowed to disagree about.
```

Every other field is compared as join guard 1 compares it. `varying` must actually vary: a
sweep whose runs all pin the same value is not a sweep, and two runs sharing a value of the
swept pin is the duplicate case guard 2 already refuses. The swept pin is named in the title
and the provenance block — a table that does not say what varied between its columns is the
thing this project exists not to publish.

**At concurrency N > 1 the ordering metric is aggregate throughput, not `decode_tps`.** N
requests share one GPU, so per-request decode rate falls as N rises by construction; a reader
who sees it drop from 75 to 30 between N=1 and N=8 and concludes the runtime got worse has
read a throughput result as a latency result. Per-request rate stays recorded, TTFT becomes a
queueing measurement whose percentiles matter more than its median, and `_aggregate_tps` —
which already exists — is what the sweep is ordered by.

**The warmup rule does not carry over to concurrency — measured, plan 06-01a.** oMLX, N=8,
workload `chat`, 16 batches:

```
per-request median   65.3 - 81.0   NEVER settles in 16 batches
aggregate tok/s      62.1 - 68.3   settles at batch 12
```

Per-request decode rate at N>1 carries queueing variance of about ±11% with no trend, which a
3% trend test can never satisfy — the same shape as the noisy prefill workload at N=1, and the
same wrong answer: it would run every concurrent cell to the cap and report "did not settle"
about a cell with nothing left to warm.

So **a concurrency sweep warms on aggregate throughput**, which is also the quantity it
publishes. `_settled` takes a second form for it: the same two-window median comparison at the
same tolerance, over `_aggregate_tps` per batch rather than per-request rates. The rule's shape
is unchanged; only the series it reads changes.

A sequential run (N=1) keeps warming on per-request decode rate. One batch of one is not the
same measurement as one request, and nothing about the existing grid changes.

Prompt lengths are **token** counts verified against the tokenizer that will serve them, with
the achieved count recorded beside the target. A prompt that exceeds a runtime's context is
never silently truncated — OptiQ's cap is pinned `off` so nothing rotates it — but no
`REFUSED` status is built for it: the runtimes' own HTTP 400/413 reports as the `FAIL` it is
(see "Refusals are not built yet, on purpose" below), and a cell a *pin* refuses renders
`N/A` with its reason.

---

## Phase 6 plan 06-01b — the concurrency pin

```python
def run_cells(cells, workloads, *, warmup="plateau", measured=9, concurrency=1,
              cooldown_s=30.0, results_dir): ...
```

**`measured` counts batches, not requests.** At `concurrency=1` a batch is one request and
nothing about the existing grid changes — that equivalence is what keeps every number measured
so far comparable. At `concurrency=8`, `measured=9` means nine batches of eight, so the cell
records 72 observations and nine batch spans.

**A batch is N requests issued together under one clock.** The span is measured around the
whole batch, because summing per-request spans would count the overlap N times and aggregate
throughput is the quantity a concurrency sweep publishes. Threads, not processes:
`concurrent.futures.ThreadPoolExecutor` around the existing `transport.chat`, which is blocked
on an SSE stream. **The stream reader is not re-implemented** — one definition of TTFT, one of
the decode window, one `Observation`.

New on `CellResult` and the record:

```python
batch_spans: list[float]   # wall-clock seconds per measured batch; one entry per batch
```

`aggregate_tps` for a batch is its completion tokens over its span. Read back leniently like
`warmup_plateau`: a record written before concurrency existed has no batch spans and `[]` is
exactly true of it, since there were no batches. A sequential record's spans are *not*
reconstructed from per-request totals — a gap between two sequential requests is not part of
either one.

**Warmup at concurrency > 1 reads aggregate throughput.** Same rule, same constants, different
series: `_settled` over per-batch aggregate rather than per-request decode rates. Measured in
plan 06-01a — at N=8 the per-request series swings ±11% with no trend and never settles, while
aggregate settles at batch 12. At `concurrency=1` the per-request series is used exactly as
today.

**The header pin** gains `concurrency`, so join guard 1 compares it and a sweep declares it via
`render_sweep(varying="concurrency")`.

**What does not change:** the floors, the coherence gate, `measured_drift`, `decode_tps`,
`prefill_tps`, `itl_s`, and every per-request figure. A concurrent cell's requests are judged
one at a time exactly as a sequential cell's are — a fast cell emitting garbage is still a
failed cell, at any concurrency.

---

## Phase 6 plan 06-01c — the prompt-length pin

Findings behind it, from the runtimes' shipped source: `docs/research/2026-09-16-prompt-length-context-limits.md`.

```python
# cli.py
LONGTEXT = Path(__file__).with_name("longtext.md")   # frozen; sha256 3ed2c160…a8a3
# Phase 6 walked 128, 1024, 4096, 16384 and 32768; --prompt-tokens takes any N.

def sized_prompt(counter, target: int) -> tuple[str, int]: ...
# -> (prompt text, achieved token count). achieved <= target, and achieved is what
#    counter.count(text) returns for the exact text returned.
```

```
ohyesmlx run --study format --cells <cell> --prompt-tokens 4096
```

**The text.** `SIZED_HEAD + cut + SIZED_TAIL`, where the source is the MS-7 excerpt body out of
`PREFILL_PROMPT` (between its BEGIN and END markers) followed by `longtext.md`, and `cut` is the
longest prefix of that source ending at a **whitespace boundary** whose whole prompt counts
`<= target`. Found by bisection over whitespace positions using only `counter.count`, so a test
can drive it with a counter as simple as `len(text.split())`. The head asks the model to read
the document; the tail asks, in one sentence, what the document is about — a question any cut
can answer, which the MS-7 question is not once the cut lands before rule 3. No repetition,
ever: a target whose prompt would need more text than the source holds is a `ValueError`, as
is a target too small to fit the head and tail.

`longtext.md` is the 2026-09-14 and 2026-09-15 research documents concatenated in name order,
frozen as a package file (60,701 tokens by the Qwen3.5-4B tokenizer). It is never regenerated
from `docs/`: those documents may be edited, and a prompt that changed under a pin is a
different prompt. Chosen by Jason, 2026-09-16, over a downloaded book and authored text.

**The workload.** With `--prompt-tokens N` the run measures **one** workload, `prefill`, whose
message is `sized_prompt(counter, N)` and whose cap is 64 — the existing prefill cap. `chat` and
`decode` are not run: they would be byte-identical across every run of the sweep and cost a
plateau warmup each. Without the flag the three pinned workloads run exactly as today.

**The counter is the serving tokenizer.** `TokenCounter(cell.artifact_dir)` for each distinct
artifact the cells name. If two artifacts' counters disagree about the achieved count of the
prompt, the run is refused before a runtime starts: one run pins one prompt length.

**The header pin.**

```python
"prompt_tokens": {"target": 4096, "achieved": 4093} | None   # None: the three pinned workloads
```

`run_cells(..., prompt_tokens: dict | None = None, ...)` writes it verbatim; `measure` does not
compute it. `load_run` needs nothing: a header is a dict, and `.get` of an absent key is `None`,
which is exactly true of every run before this pin.

**Join guard 1 compares both sweep pins.** `PIN_FIELDS` gains `concurrency` and
`prompt_tokens`. `concurrency` is compared with an absent value read as `1` — every run written
before the pin existed issued requests one at a time, so `1` is the fact and not a default
standing in for something unknown. This closes a defect: 06-01b's header pin was never added to
`PIN_FIELDS`, so `ohyesmlx grid` would have joined an N=8 run into an N=1 grid without a word.

**Refusals are not built yet, on purpose.** The source says no runtime refuses 32k on
Qwen3.5-4B: mlx-lm has no check, OptiQ's cap is now `off`, oMLX's discovered limit is 262,144,
vMLX's memory estimate lands far above it. Osaurus is unreadable and gets a live probe first. A
`REFUSED` status is built only if a probe shows a refusal; until then an HTTP 400/413 at a long
prompt reports as the `FAIL` it currently is, and the sweep is not published with one in it.

---

## Phase 6 — the lost visit and the short measured window (found by 06-01c's sweep)

The prompt sweep's Osaurus 128 cell recorded **4 measured requests against a run pinning 9**, on
a row that was marked `PASS` with no note. Two visits are planned per cell and its quota splits
5/4; visit 1's `runtime.start()` raised, visit 2 measured its quota of four, and `_set_status`
rewrote the row from the samples that survived — erasing both the failure and the fact that half
the window was missing. A reader of that table saw a full `PASS` row with the count column
reading `4/4`.

Three additions, all of them annotations and none of them floors — the same rule drift follows:
a window that was short is a result, and dropping it would delete the only row that says so.

```python
CellResult.lost_visit_reason: str | None   # the failed visit's reason, kept where _set_status
                                           # cannot overwrite it. None = no visit was lost.
CellResult.cold_load_after_lost_visit: bool  # the start that recorded cold_load_s came after a
                                             # lost visit, so it is a warm-page-cache start and
                                           # not the cell's cold one.
CellResult.measured_pin: int | None        # the run's batch pin, stamped on every row by
                                           # run_cells. NOT written to the record: the header
                                           # owns it there, one copy per run, and a result
                                           # rebuilt by load_run carries None.
```

`lost_visit_reason` and `cold_load_after_lost_visit` are written to the record **only when they
are true**, so a cell whose every visit measured keeps the record it always had, byte for byte;
both are read back leniently on the same reasoning — every record on disk was written before the
fields existed and no visit of theirs was lost, so the absence *is* the fact.

```python
def summarize(results: list[CellResult], *, measured: int | None = None) -> list[dict]: ...
```

*measured* is the run's batch pin, passed in by a caller joining run directories because a
result rebuilt by `load_run` does not carry it. A row that landed fewer batches than the pin —
counted off `batch_spans` above concurrency 1 and off the observations at 1, because the pin
counts batches — carries `short_note` and the row reads `(n=K of N)` beside its number in the
grid and the sweep. No pin at all is **no check**, never a pin of zero: that is the honest
reading of an older record and of a caller that never knew about the pin, and it is the one
place a run short of its window can go unremarked.

The lost visit rides in the metric card as `lost_visit_note` ("a visit to this cell was lost
before the one that measured: …; the samples on this row are the surviving visit's"), beside the
status whose reason it is not, and the cold load carries `cold_load_note` naming which start the
figure came from. Neither is a floor and neither moves a published number.

## Phase 6 plan 06-02 — the cache-state pin

The cold/warm split, per the Phase 6 design ("Cold versus warm KV"): the same prompt answered
with a runtime's prefix/KV reuse off and on, the difference between the two being what the cache
is worth. It is a **pin**, not an axis and not a cell property — one run drives every cell in it
into one state — so it is joined exactly as the other two sweeps are.

```
ohyesmlx run ... --cache-state {off,on}
ohyesmlx sweep <off-run-dir> <on-run-dir> --varying cache_state --rank ttft_p50_s
```

**The header pin.**

```python
"cache_state": "off" | "on" | None     # None: the pin was not taken
```

`PIN_FIELDS` gains `cache_state` and `ABSENT_PINS` reads an absent one as `None` — which is the
one part of this pin that must not be got wrong. `None` is not a third state and it is not a
synonym for `"off"`: every run measured before the pin existed ran each runtime's own default,
and those defaults were not uniform — the Osaurus grid columns ran with its prefix cache ON, and
the same 2026-09-15 columns ran with oMLX's `--no-cache` and vMLX's two disable flags pinned off.
Reading the absence as `off` would fold two different cache states into one column and call them
a comparison. Without the flag every start command is **byte-identical to today**; that is
checked against recorded literals for all five runtimes, not re-derived.

**Amended 2026-09-28 (Decision 130).** The absent pin is still recorded as `None`, but mlx-lm and
OptiQ now deliver reuse off under it: their absent-pin command gained `--prompt-cache-size 0`,
which is the `off` command below. Left at the default 10, the seedless batched path (Decision 128)
answered repeated prompts from the cache and timed hits as prefill
(docs/research/2026-09-28-seedless-validation-grids.md §2.2). oMLX and vMLX already passed their
off flags without a pin, and Osaurus runs with its prefix cache disabled by the sweep script. The
`TODAY` literals carry the new flag for those two runtimes. Rows recorded before this change with
an absent pin ran the default 10 on mlx-lm and OptiQ, and nothing in the run header separates
them from rows recorded after it: keep them in separate run directories and do not join them.

**The mechanism, per runtime.** `off` disables prefix/KV reuse and `on` enables it, through each
runtime's own start command:

| runtime | `off` | `on` | where it comes from |
|---|---|---|---|
| mlx-lm 0.31.3 | `--prompt-cache-size 0` | `--prompt-cache-size 10` | `mlx_lm/server.py:1872` — "Maximum number of distinct KV caches to hold in the prompt cache", default 10. At 0 the cache holds nothing: every insert evicts the entry it just added (`models/cache.py:1696-1737`), so the `fetch_nearest_cache` at `server.py:753` always answers `None` and every request prefills its prompt whole. |
| mlx-optiq 0.5.13 | the same two flags | the same two flags | `optiq serve` is a fork of the same server: unknown options are collected (`optiq/cli.py:2500` `ignore_unknown_options`, `:2768` `ctx.args`) and handed to the bundled `mlx_lm.server`'s own argparse (`:3310`), and the bundle is the same mlx-lm 0.31.3. |
| oMLX 0.6.4 | `--no-cache` (already in the command) | omit `--no-cache` | `omlx/cli.py:1139-1143` — "Disable oMLX paged SSD cache". Absent it, `CacheSettings.enabled` is True (`omlx/settings.py:331`) and the SSD directory resolves to `<base-path>/cache` (`settings.py:387-399`) — for a run, the per-run scratch the runtime is handed and that `stop()` removes. |
| vMLX 1.6.59 | `--disable-prefix-cache` | `--enable-prefix-cache` | `vmlx_engine/cli.py:3658-3670` — `--enable-prefix-cache` defaults True, `--disable-prefix-cache` is the explicit off. `--disable-block-disk-cache` is in **both** states: left unset, the engine turns the SSD L2 on by itself whenever continuous batching and prefix caching are active (`cli.py:661-701`) and persists it under `~/.cache/vmlx-engine/block-cache/<model_hash>`, so the two states would differ in two things and an `on` cell could serve another run's prefix. |
| Osaurus 0.25.x | refused unless the host is already off | refused unless the host is already on | No flag exists in either direction. The state is `cache.prefix.enabled` in `~/.osaurus/config/server-runtime.json`, which the harness does **not** edit — the sweep script does, with a byte-exact backup and restore. |

**A state a runtime cannot be driven into is `N/A` with the reason**, through the same path an
unknown runtime and an unavailable tokenizer take: the runtime is asked
(`Runtime.cache_state_refusal`) *before* it is started, and `_visit` returns `"skip"` so no later
visit retries it. Osaurus is the whole of the mechanism: `_visit` asks it whether the live
`cache.prefix.enabled` matches the requested state (`True` for `on`, `False` for `off`), and a
disagreement — or a settings file that cannot be read, `MISSING`/`UNREADABLE` included — records
the refusal instead of measuring. **A restart is not a way to turn a cache on**: a process that
just started has an empty cache whatever the settings say, so restarting to reach `on` would
label an off cell as an on one, and a cell measured in a state it did not hold is not a result.
The reason names the setting and the value that disagreed, because the fix is a script's and not
this runtime's.

**`render_sweep` gains `varying="cache_state"`.** `concurrency`, `prompt_tokens`,
`cache_state`, `kv_quant`, `mtp_depth` and `stream_experts` are the whole of `SWEEP_PINS`. The
one relaxation stays the prompt-length pin's
alone: a cache sweep's columns are meant to answer the **same** prompt twice, once cold and once
warm, so every workload's `messages` are compared like any other field and two runs that sent
different prompts are refused. The columns render **`off` before `on`** — the cold column is the
baseline the warm one is read against — from `SWEEP_VALUES`, an explicit order rather than the
accident of how two words sort. `off` vs `on` in a *grid* is refused by guard 1 like any other
pin difference, and so is an absent pin against a pinned `off`.

**What the sweep is read on.** TTFT, not a rate: a prefix cache that hits collapses prefill, so
the reading is `ttft_p50_s`. A cell whose runtime never hits the cache measures the same number
in both columns, and that is a finding — "the cache was worth nothing here" — not a failure.
The 2026-09-16 probe found exactly that for an oQ4 prefill on four of the five runtimes, and the
flat-TTFT check (warmup #1 against the measured median) is what tells a hit from a miss rather
than assuming one.

**The runner** is `scripts/run_sweep_cache.sh`, modelled on `scripts/run_sweep_prompt.sh`: the
`oq4` cell, five runtimes, `--prompt-tokens 4096`, each runtime `off` then `on`, into
`results/sweep-cache/`. For Osaurus it snapshots `server-runtime.json` **and** `server.json`
byte-exact, flips `cache.prefix.enabled` and `cache.blockDisk.enabled` false for `off`, sets
`modelIdleResidencyPolicy.seconds` to 900 in **both** states (the host's 30 unloads the model
inside the 30 s cooldown), re-records the baseline so the harness's drift guard passes, and
restores both files with `git checkout -- config/osaurus-settings-baseline.json` at the end and
on INT/TERM/HUP. Restoration is verified with `cmp` against the copies rather than with the drift
guard, because the host's 30 legitimately differs from the committed baseline's 900 and the
guard would report Jason's own machine as drift forever.

