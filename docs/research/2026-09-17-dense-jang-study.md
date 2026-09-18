# Plan 01-01 — the dense JANG study: `Qwen3.5-4B` in vMLX and Osaurus

Date: 2026-09-17. Measured 14:56:43–16:56:51 local as four runs and one join. One model
(`Qwen3.5-4B`), two runtimes that both load JANG and portables, two single-variable axes, and one
replication pass over the cells that carry the claim. Design, pre-registered readings and pins:
`docs/research/2026-09-17-v2-track1-jang-study-design.md` (§6.2 is this plan).

This document is written against that design's rules, not around them. Where a pre-registered pin
was not taken, or a pre-registered ordering did not survive its own replication, the record is
reported as it stands and the reading is narrowed — §8 is the list, and the largest item in it
changes what one of the three workload columns is allowed to mean.

---

## 1. Executive summary and headline finding

### 1.1 What ran

| run | runtime | started | ended | rows | run directory |
|---|---|---|---|---|---|
| vMLX column (format axis) | vmlx 1.6.59 | 14:56:49 | 15:39:59 | 12 (4 cells × 3 workloads) | `results/grid-jang-dense/20260917T185649Z-format` |
| Osaurus column (format axis) | osaurus 0.25.6 | 15:40:05 | 16:20:49 | 12 (4 cells × 3 workloads) | `results/grid-jang-dense/20260917T194005Z-format` |
| the join | — | 16:20:54 | 16:20:54 | — | `results/grid-jang-dense/grid.md` |
| vMLX replicate | vmlx 1.6.59 | 16:20:54 | 16:38:19 | 6 (2 cells × 3) | `results/grid-jang-dense/replicate/20260917T202054Z-format` |
| Osaurus replicate | osaurus 0.25.6 | 16:38:24 | 16:56:45 | 6 (2 cells × 3) | `results/grid-jang-dense/replicate/20260917T203824Z-format` |

**36 of 36 (cell, workload) rows are PASS, every row names `n = 9` measured requests, and the
coherence floor passed on all of them** — twelve cells visited twice, no lost visit, no `FAIL`, no
`N/A`. One warmup window did not close: `stock4bit__vmlx` on `decode` hit the cap
(`warmup_plateau: false`, 37 warmups), which §3.1 reads rather than hides. The runner's timeline is
`results/grid-jang-dense/runner.log`, which ends
`JANGDENSEDONE 16:56:51` with the script's exit 0; its two Osaurus settings restores are both
`cmp -s` verified (`runner.log:10`, `:154`).

Two columns, two axes. Each column holds the runtime constant and varies the format — that is the
format axis, and it is legal here because both vMLX and Osaurus load portables *and* JANG, which is
what closed the hole v1 recorded as the founding decision. The grid additionally prints the
`jang4s` row across both columns: the **runtime axis on identical bytes**, the only comparison in
this project where two different loaders see the same weights.

### 1.2 The headline: R1 on the decode workload, in both runtimes

On the 512-token `decode` shape, the one workload whose rate a prefix cache cannot touch and whose
window is long enough to be a rate rather than an opening, `JANG_4S` led its column in **both**
runtimes and in **both** visits:

| runtime | primary `L` vs best portable | replicate `L` vs the same portable | R1 |
|---|---|---|---|
| vmlx 1.6.59 | **+13.9%** (54.2 v 47.6) | **+16.8%** (59.1 v 50.6) | yes |
| osaurus 0.25.6 | **+9.5%** (42.5 v 38.8) | **+9.0%** (46.0 v 42.2) | yes |

`L` is the design's pre-registered definition, `(decode_tps(JANG) − decode_tps(best_portable)) /
decode_tps(best_portable) × 100`, evaluated per workload and never pooled. Both cells clear the
2.5% tie band in both visits and the direction agrees in both, so **the reading is R1: the JANG
bundle beat the best portable format in both runtimes that load it, and the effect is not private
to one loader.** R1's own limit travels with it: this says the lead is real and duplicated across
two independent implementations; it does not say *why*, because packing, bit assignment and the
loader travel together in every cell that produced it (§6).

**Which numbers the percentages are taken from.** Every `L` in this document is the quotient of the
one-decimal figures the leaderboards and the grid render — the published table a reader can check
it against — and not of the records' full-precision medians. The two bases differ by at most
0.24 pp, and the largest case is this section's own: from full precision, vMLX's decode lead reads
**+13.7%** (54.185 v 47.642) against the printed +13.9%, and Osaurus's reads **+9.6%**
(42.517 v 38.800) against the printed +9.5%. No conclusion in this document turns on the
difference — every gap stays on the same side of the 2.5% band and of the 5% replication threshold
under either basis — and Appendix B recomputes both.

### 1.3 What the same evidence does *not* license

Three limits belong beside the headline, and each is a rule doing its job rather than an
inconvenience.

- **`chat` yields no ordering in either runtime.** In vMLX the JANG-versus-stock4bit comparison
  *reverses sign* between the primary (−8.8%) and the replicate (+14.7%); in Osaurus the primary
  lead (+8.6%) falls inside the tie band in the replicate (−1.8%). The pre-registered rule for
  exactly this shape ("a lead that clears 2.5% in one run and sits inside the band in the other is
  reported as a tie with both numbers printed", and a direction that does not agree is not a lead)
  leaves `chat` with both figures printed and **no ordering published**. §3.2 and §4.2 carry the
  numbers and the drift that explains the vMLX half.
- **`prefill` is a tie in both columns** — vMLX −0.8% in the primary and +7.9% in the replicate;
  Osaurus +6.1% and +1.0%. One visit inside the band is enough to make it a tie under R-tie, and
  each column supplied one.
- **The Osaurus `prefill` column is not a prefill column.** Every Osaurus `prefill` cell in the
  primary measured **prefix-cache lookups**, not prompt processing: each cell's first prefill
  request took 3.4–3.7 s and every subsequent one 0.27–0.61 s, and the replicate's first prefill
  request took 0.32–0.33 s — the entry was already on disk. `~/.osaurus/cache/kv_v2/` gained eight
  KV entries totalling **566.0 MB** while the column ran. The consequence is precise and stated in
  full in §4.3: this workload's `ttft_p50_s` and `prefill_tps` are lookups, its `decode_tps` — the
  metric every table here ranks by — is untouched, and the cross-runtime `prefill` row may not be
  read on TTFT or prefill throughput at all.

### 1.4 The cross-runtime row, and the one thing it does establish

Same bytes, two loaders (`JANGQ-AI/Qwen3.5-4B-JANG_4S` @ `4567967a…`, 3,207,385,506 B in both
columns — identical `disk_bytes` on every row):

| workload | vMLX primary | Osaurus primary | vMLX lead | vMLX replicate | Osaurus replicate | vMLX lead |
|---|---|---|---|---|---|---|
| `decode` | 54.2 | 42.5 | **+27.5%** | 59.1 | 46.0 | **+28.5%** |
| `chat` | 55.2 | 48.1 | +14.8% | 60.0 | 49.6 | +21.0% |
| `prefill` (decode rate) | 60.2 | 55.8 | +7.9% | 62.7 | 59.0 | +6.3% |

vMLX's JANG implementation decodes the identical weights **27.5–28.5% faster** than Osaurus's, and
the two independent orderings of that pair — taken at different points in the session, with the
same column order both times (a deviation, §8.2) — produce a gap that moves by 1.0 percentage point
while every cell inside them moved 8–15% between visits. What that establishes is *that the two
implementations differ, and by how much, on identical bytes*. It does not establish which internal
does it: loader, scheduler, Metal usage and memory accounting all move together in that row.

---

## 2. Provenance and operational environment

### 2.1 Runtimes and versions

| runtime | version (recorded per row) | how the version is established |
|---|---|---|
| vMLX | **1.6.59** on all 18 vMLX rows | `runtime_version` in every row; the constant is read from the app bundle's engine source (`runtimes.py`'s `VMLX_ENGINE_INIT`), since `vmlx --version` exits 2 |
| Osaurus | **0.25.6** on all 18 Osaurus rows | `runtime_version` in every row, from the running server |

One runtime at a version per column, both columns at one version each: join guard 4 had nothing to
refuse, and the grid's provenance block names each version beside its run directory.

### 2.2 The pins, as recorded — and the one that was not taken

Read from the header line of each `results.jsonl`, and printed by the grid's provenance block:

| pin | value | status |
|---|---|---|
| `temperature` | `0.0` | as designed |
| `seed` | `0` | as designed |
| `warmup` | `{mode: plateau, window: 5, floor: 10, cap: 20, plateau_pct: 3.0}` | as designed; 35 of 36 rows closed on the rule — `stock4bit__vmlx` `decode` hit the cap and records `warmup_plateau: false` (§3.1) |
| `measured` | `9` batches, `concurrency` `1` | as designed |
| `cooldown_s` | `30.0` | as designed |
| `prompt_tokens` | `null` (the three pinned literals) | as designed |
| **`cache_state`** | **`null` — the pin not taken** | **deviation**; see §8.1 |

`cache_state: null` is not a third state and is never to be read as `off`: it is the pin not
taken, and `runtimes.py` says so in the constant's own comment ("the runs measured before the pin
existed ran each runtime's own default, and those defaults were not uniform (the Osaurus grid
columns ran with its prefix cache ON)"). The consequence differs by runtime and is worked out
cell by cell in §3.0 and §4.3:

- **vMLX is provably unaffected.** Its start command is byte-identical with and without the pin
  (`runtimes.py:1089-1091`: the prefix flag is `--disable-prefix-cache` unless the pin is `on`,
  and `--disable-block-disk-cache` is unconditional at `:1124`). Independently, this model's hybrid
  path has no backend to serve a hit from, and vMLX measured 1.00x on it in 06-02
  (`docs/research/2026-09-17-cache-state-split.md`).
- **Osaurus is affected, and the effect is in the numbers.** The host's own files carried
  `cache.prefix.enabled: true` and `cache.blockDisk.enabled: true` throughout both Osaurus columns
  (the runner restored them byte-exact, so today's live file is the state at run time), no
  `--cache-state off` was passed, and `Osaurus.cache_state_refusal` returns `None` for the absent
  pin rather than refusing it. §4.3 shows what that did to the `prefill` workload.

### 2.3 The artifacts

All paths are under `$H = ~/.cache/huggingface/hub/`. `disk_bytes` is recomputed per row at
measurement time and agrees with the pre-run inventory of the design's §4.2 on every row — the
five dense artifacts did not change between the design's audit and the run.

| label | repo | snapshot | bytes | GiB | GB |
|---|---|---|---|---|---|
| `jang4s` | `JANGQ-AI/Qwen3.5-4B-JANG_4S` | `4567967a46cd9e9bf26d3bb491ddd422ad607775` | 3,207,385,506 | 2.987 | 3.207 |
| `stock4bit` | `mlx-community/Qwen3.5-4B-4bit` | `0e7ffd5c629ef7719d4cbc04069232580bfa9d9c` | 3,061,131,520 | 2.851 | 3.061 |
| `oq4` | `RepublicOfKorokke/Qwen3.5-4B-oQ4` | `3ae88a7d17b1c6bb71b795c1090948a82508fdb8` | 3,160,559,814 | 2.944 | 3.161 |
| `oq4e` | `uingei/Qwen3.5-4B-oQ4e` | `2e232d525d5df5e7a6eece4b03b17087e6b3c3ac` | 3,167,949,891 | 2.950 | 3.168 |
| `optiq` | `mlx-community/Qwen3.5-4B-OptiQ-4bit` | `6cb5bdfd0bf15f484881fb9f1ab6d7c840fddde9` | 4,043,620,369 | 3.766 | 4.044 |

`optiq` appears only in the Osaurus column: the design's dense OptiQ hole is a vMLX multimodal-path
refusal (the artifact's per-layer map omits every `vision_tower` parameter), and it is recorded
there as `—`, never measured, never manufactured into a `FAIL`.

**Digest of the one artifact whose sidecar the reading depends on**, re-verified today rather than
quoted:

```
shasum -a 256 $H/models--JANGQ-AI--Qwen3.5-4B-JANG_4S/snapshots/4567967a46cd9e9bf26d3bb491ddd422ad607775/jang_config.json
3a9bf087d86505da8828cd2a2d39cb7c37066c755132fbfca35fbafeebe2abcd
```

That is byte-identical to the digest recorded at design time, so the artifact's own claims about
itself (`actual_bits: 4.15`, `block_size: 64`, `bit_widths_used: [4, 6]`, `format: jang/2.0`,
`capabilities.cache_type: hybrid`, `has_vision: true`) are the ones §6 reads. A provenance note
that survives from the audit: **four of the five dense artifacts carry a `.vmlx-alignment.lock`;
the JANG bundle carries none** (checked again today) — a tool has touched the portables'
directories and has never touched JANG's.

### 2.4 Host handling

- **Osaurus settings.** Byte-exact `cp -p` copies of `~/.osaurus/config/server-runtime.json` and
  `server.json`, idle residency pinned to **900 s** for the duration (the host's own 30 unloads
  the model inside the 30 s cooldown), restore verified with `cmp -s` after the column and again
  after the replicate — `runner.log:6`, `:10`, `:150`, `:154`, both reporting
  `osaurus settings restored byte-exact (cmp)`. The `INT/TERM/HUP` trap is in the script
  (`scripts/run_jang_dense.sh:93`), so an interrupt restores rather than leaving the host pinned.
- **What the settings step did *not* do**, and this is the same deviation as §2.2 in its runner
  form: the design's §3.5 required the cache toggles set false for the campaign *and* per-cell
  `shasum -a 256` digests of both files. The runner pinned residency and restored/compared the
  files, but it never toggled the cache keys and never took per-cell digests. No per-cell digest
  evidence exists for this campaign; the pre/post restoration is what the record carries.
- **Ports and isolation.** vMLX on 8000 (`Starting server at http://127.0.0.1:8000` in every vMLX
  log), Osaurus on 1337. Ports swept between every column (five ports plus stale Osaurus apps, by
  full executable path) in `runner.log` at `:1-2`, `:5`, `:9`, `:149`, `:153`. One runtime held
  weights at a time.
- **The visit structure, confirmed from the loader logs rather than assumed.** Each cell's runtime
  starts once per visit and runs all three workloads under that one load, both visits inside the
  cell's own process pair: the primary vMLX column left **8** server logs for 4 cells, in the order
  `stock4bit → oq4 → oq4e → jang4s → jang4s → oq4e → oq4 → stock4bit`
  (`results/logs/vmlx-20260917T145649…153409-65592.log`), i.e. visit 1 forward and visit 2
  reversed, exactly as `VISIT_ROUNDS` plans. The Osaurus column left 8 matching logs at five-minute
  spacing.

### 2.5 The pins the join guard cannot see, verified in the logs

`results.jsonl` does not record the start command, so the design's §3.6 answer is per-run log
evidence. All of it was found, and the negative was found too:

| check | expected evidence | observed |
|---|---|---|
| JANG path taken, not the generic loader | `JANG v2 … loaded`, `Pre-fixed N module(s)` | `JANG v2 VLM detected — loading via mmap (instant)`, **`Pre-fixed 217 module(s) with mixed-precision bit widths`**, `JANG v2 VLM loaded in 0.8s` — in the JANG cells of both vMLX runs, 217 on every one (the design predicted 217 on the dense artifact) |
| portable cells on the generic path | `MLLM loaded successfully` | present in every portable vMLX log; the JANG loader lines are absent there |
| **JIT off** | *absence* of `JIT: mx.compile applied successfully — running warmup pass` | **absent from all 12 vMLX logs** (`grep -ci "JIT"` = 0 and `grep -ciE "mx\.compile applied\|running warmup pass"` = 0 on every one) |
| **MTP off** | `MLLM native MTP skipped for request=…: disabled by VMLX_NATIVE_MTP=0/--disable-native-mtp` | present, many times per log (43–50 occurrences in the replicate logs) despite the bundle shipping `vmlx_mtp_proposal_head.json` |
| TurboQuant KV state | skipped, and for which reason | `TurboQuant KV skipped: VMLX_DISABLE_TQ_KV=1; using native model cache` in the JANG cells; `TurboQuant skipped: VMLX_DISABLE_TQ_KV=1` in the portables; the design's predicted wording (`jang_config has no 'turboquant' block`) is not the mechanism the log reports — the env var the harness's own flag path sets is |

One log line needs its meaning stated rather than left to a reader, because it appears in the JANG
cells and nowhere else: `SSD prefix cache: stored in the model's NATIVE cache representation …
(JANGTQ/JANG-affine high-fidelity default)`. It describes the *storage codec* that tier would use
for a JANG-affine bundle; it is not a statement that the tier ran, and the tier is disabled by
`--disable-block-disk-cache` on this harness's command in both cache states. The behavioural check
agrees: vMLX's prefill TTFTs are flat across every warmup and measured request of every cell
(§3.0), which is the shape of a runtime that prefills every time.

---

## 3. The format axis inside vMLX

`--study format`, runtime `vmlx` held constant at 1.6.59, four cells, `n = 9` per (cell, workload).
Source: `results/grid-jang-dense/20260917T185649Z-format/leaderboard.md`; ordered per workload by
`decode_tps`, never pooled.

### 3.0 The shape of the column before the numbers

Every cell in this column prefills every time it is asked. The evidence is the TTFT sequence, not
a flag: the JANG cell's prefill warmups run 2.138, 2.584, 2.613 … 2.563 s (21 of them) with its
measured requests at 2.31–2.64 s, and `stock4bit`'s run 2.246 … 3.338 s with measured at
2.68–3.78 s. Nothing collapses, nothing is served from anywhere but the weights. That is what a
column with `--disable-prefix-cache` and `--disable-block-disk-cache` in its start command, on a
hybrid model with no cache backend to serve from, is supposed to look like — and it is the
comparison's control against the Osaurus column's behaviour in §4.3.

### 3.1 `decode` (512 tokens) — the workload that carries the claim

| cell | `decode_tps` | JANG's lead over it | drift % | TTFT p50 s | ITL s | aggregate tok/s | peak MB | cold load s |
|---|---|---|---|---|---|---|---|---|
| `jang4s__vmlx` | **54.2** | — | +5.9 | 0.185 | 0.0185 | 53.5 | 3820 | 7.06 |
| `oq4__vmlx` | 47.6 | **+13.9%** | +14.2 | 0.250 | 0.0210 | 46.2 | 3819 | 7.08 |
| `oq4e__vmlx` | 46.0 | +17.8% | +5.4 | 0.243 | 0.0218 | 42.3 | 3946 | 7.07 |
| `stock4bit__vmlx` | 44.2 | +22.6% | +16.6 | 0.277 | 0.0227 | 42.8 | 3843 | 7.08 |

The ordering is clean and the gaps are not marginal: the smallest is 13.9%, five times the tie
band. The three portables separate too (47.6 > 46.0 > 44.2, the two ends 7.7% apart), so
`oq4` is the best portable legitimately rather than by rounding.

Every cell in this table drifted **positive** (+5.4% to +16.6%): each was still climbing when its
window closed, so each published rate is an early-window figure. That is a property of the whole
column and cannot be subtracted out — and it is not a JANG advantage, because the JANG cell's
drift (+5.9%) is smaller than two of the three portables'. The design's rule stands: drift
annotates, never fails, and never explains away a 13.9% gap that the replicate then widens.

**One row hit the warmup cap, and it is the last-placed one.** `stock4bit__vmlx` on `decode`
records `warmup_plateau: false` with 37 warmups — its window was still moving when the cap
stopped it, which is the direction its +16.6% drift also points. It keeps its place and its
annotation, per the rule that a cell still climbing is ranked and annotated rather than dropped;
if it is under-measured it is under-measured *low*, which widens the JANG lead rather than
manufacturing it.

### 3.2 `chat` (128 tokens) — a sign reversal, reported as one

| cell | `decode_tps` | JANG's lead over it | drift % | TTFT p50 s | ITL s | aggregate tok/s | peak MB |
|---|---|---|---|---|---|---|---|
| `stock4bit__vmlx` | **60.5** | **−8.8%** | **−24.7** | 0.179 | 0.0167 | 48.2 | 3838 |
| `jang4s__vmlx` | 55.2 | — | −0.8 | 0.185 | 0.0182 | 50.7 | 3826 |
| `oq4e__vmlx` | 46.6 | +18.5% | +1.0 | 0.249 | 0.0216 | 42.8 | 3955 |
| `oq4__vmlx` | 46.1 | +19.7% | +33.4 | 0.244 | 0.0219 | 41.4 | 3819 |

Read the drift column before the ordering, because it is the story. `stock4bit` was **slowing down
as it was measured** — its own row says early median 63.4 tok/s against a late median of 47.7 —
and it is the cell that "beat" JANG here. The replicate ran the same pair again (§3.4): `jang4s`
60.0 against `stock4bit` 52.3, a **+14.7% lead for JANG, the opposite sign**, with `stock4bit`'s
replicate number sitting between that cell's primary early and late medians. Two visits, two
directions, one of them visibly thermally compromised: under R-tie this is not a lead for either
cell, and under R-reproduce both cells moved more than 5% between visits and are published with
both figures and no ordering between them.

Against the other two portables the gap does not reverse — JANG leads `oq4e` by 18.5% and `oq4` by
19.7% — but `oq4`'s own +33.4% drift is the largest number of that kind in the campaign, so the
honest statement is the same one the rules produce: **the `chat` workload separates the JANG bundle
from nothing in this column**, and the one ordering it appeared to produce was a thermal artifact
that the replicate exposed.

### 3.3 `prefill` (64 tokens) — a tie, and a real prefill

| cell | `decode_tps` | JANG's lead over it | drift % | TTFT p50 s | **prefill tok/s** | peak MB |
|---|---|---|---|---|---|---|
| `stock4bit__vmlx` | 60.7 | **−0.8%** | −12.4 | 2.834 | 463.6 | 4727 |
| `jang4s__vmlx` | **60.2** | — | +2.3 | 2.450 | **536.3** | 4640 |
| `oq4__vmlx` | 53.8 | +11.9% | +10.1 | 3.570 | 368.1 | 4595 |
| `oq4e__vmlx` | 50.8 | +18.5% | +5.5 | 3.250 | 404.3 | 4734 |

JANG against `stock4bit` is 0.8% — **inside the band, a tie**, and the design's rule forbids
printing it as an ordering. The two are not the same kind of number underneath, though, and this
column's TTFTs are real: `jang4s` reaches the first token of a 1,314-token prompt in 2.450 s
(536.3 tok/s of genuine prompt processing) against `stock4bit`'s 2.834 s and `oq4`'s 3.570 s.
Against the *portables other than stock*, JANG's prefill-side advantage is unambiguous: +11.9% over
`oq4` and +18.5% over `oq4e` on the same 64-token decode metric, with TTFT p50 better by 1.12 s and
0.80 s respectively.

### 3.4 The replicate: the lead is confirmed, and one number is repaired

`results/grid-jang-dense/replicate/20260917T202054Z-format`, `jang4s__vmlx` against
`stock4bit__vmlx` — the pair with the widest margin in the primary's decode workload, `+22.6%`.

| workload | `jang4s` | `stock4bit` | JANG's lead | primary's lead | agreement |
|---|---|---|---|---|---|
| `decode` | 59.1 | 50.6 | **+16.8%** | +22.6% | same direction, clears the band |
| `chat` | 60.0 | 52.3 | **+14.7%** | −8.8% | **reversed** |
| `prefill` | 62.7 | 58.1 | +7.9% | −0.8% | one visit in the band |

The decode lead replicates: a second visit, an independently started column, and JANG still leads
by a margin five times the band. The two other workloads do not, and neither gets an ordering in
§1.3. What the replicate does for `chat` is worth naming precisely: it is the run that shows the
primary's `stock4bit` chat number was a cell in thermal decline rather than a faster format — the
same conclusion the drift annotation on that row reached on its own, now with a second visit behind
it.

---

## 4. The format axis inside Osaurus

`--study format`, runtime `osaurus` held constant at 0.25.6, four cells, `n = 9` per (cell,
workload). Source: `results/grid-jang-dense/20260917T194005Z-format/leaderboard.md`.

### 4.1 `decode` (512 tokens) — a replicated lead and a three-way tie behind it

| cell | `decode_tps` | JANG's lead over it | drift % | TTFT p50 s | ITL s | aggregate tok/s | peak MB | cold load s |
|---|---|---|---|---|---|---|---|---|
| `jang4s__osaurus` | **42.5** | — | +5.1 | 0.297 | 0.0236 | 41.5 | 3400 | 1.26 |
| `oq4__osaurus` | 38.8 | **+9.5%** | +18.7 | 0.359 | 0.0258 | 39.3 | 2466 | 1.29 |
| `optiq__osaurus` | 38.7 | +9.8% | −1.0 | 0.316 | 0.0259 | 37.7 | 2472 | 1.25 |
| `oq4e__osaurus` | 38.6 | +10.1% | +6.2 | 0.335 | 0.0260 | 38.0 | 2216 | 1.26 |

JANG leads the best portable by 9.5% — four times the band — and the lead is confirmed by the
replicate (+9.0%, §4.4).

**The three portables behind it are a tie, not an ordering.** `oq4` 38.8, `optiq` 38.7, `oq4e` 38.6
span 0.52% end to end, well inside the 2.5% band. The grid ranks them 2 / 3 / 4 because a renderer
ranks what it is given; by this project's own rule those three rank numbers are a reader's
inference and not the measurement's claim, and this document prints them as a tie. The tie is
itself a reading: it reproduces the v1 MoE finding (`2026-09-16-moe-format-axis.md` — the three
specialized formats indistinguishable on a 32-expert MoE) on the dense model and in a runtime v1
never had a full column for.

### 4.2 `chat` (128 tokens) and `prefill` (64 tokens)

| `chat` cell | `decode_tps` | JANG's lead over it | drift % | TTFT p50 s | aggregate tok/s |
|---|---|---|---|---|---|
| `jang4s__osaurus` | **48.1** | — | +2.3 | 0.303 | 42.3 |
| `oq4__osaurus` | 44.3 | +8.6% | +12.9 | 0.286 | 41.4 |
| `oq4e__osaurus` | 41.5 | +15.9% | +9.3 | 0.329 | 37.8 |
| `optiq__osaurus` | 41.4 | +16.2% | +7.2 | 0.312 | 38.1 |

`oq4e` 41.5 against `optiq` 41.4 is another inside-band pair (0.24%) that a rank number would
overstate. The JANG lead here is +8.6% and it does **not** survive R-tie: the replicate reads
`oq4` ahead of `jang4s` by 1.8% (§4.4), inside the band, so `chat` is published as a tie with both
numbers — this is the Osaurus half of §1.3's second bullet.

| `prefill` cell | `decode_tps` | JANG's lead over it | drift % | TTFT p50 s | **prefill tok/s** | note |
|---|---|---|---|---|---|---|
| `jang4s__osaurus` | **55.8** | — | +11.0 | 0.457 | 2886.7 | **2,886.7 is not a prefill rate — §4.3** |
| `oq4__osaurus` | 52.6 | +6.1% | +11.9 | 0.404 | 3261.9 | idem |
| `optiq__osaurus` | 50.4 | +10.7% | +2.8 | 0.462 | 2857.9 | idem |
| `oq4e__osaurus` | 48.2 | +15.8% | +7.1 | 0.422 | 3124.3 | idem |

The `decode_tps` column of this table is a decode measurement and stands. The TTFT and prefill
throughput columns are lookups, and §4.3 is why.

### 4.3 The finding: the Osaurus `prefill` column measured prefix-cache lookups

This is not an inference from a flag; it is the shape of the cell's own requests, with the on-disk
corroboration behind it.

**(a) The request pattern.** For every Osaurus `prefill` cell in the primary column, the first
prefill request of the process is 5.6–13.8x the slowest request that follows it, and no other
request in the cell is anywhere near it:

| cell (primary) | first prefill request | every other prefill request | `prompt_tokens` |
|---|---|---|---|
| `jang4s__osaurus` | **3.425 s** | 0.317–0.607 s (23 warmups + 9 measured) | 1319 |
| `oq4__osaurus` | **3.536 s** | 0.278–0.446 s | 1319 |
| `oq4e__osaurus` | **3.726 s** | 0.270–0.467 s | 1319 |
| `optiq__osaurus` | **3.542 s** | 0.307–0.567 s | 1319 |

Compare the vMLX column's flat sequences (§3.0), and compare the calibration this project already
owns: on this same model family, 06-02 measured an Osaurus prefix hit as **0.404 s against its own
9.401 s cold prefill of a 4,096-token prompt — 4% of it, a 23.29x collapse**
(`docs/research/2026-09-17-cache-state-split.md`). A hit on this model is not a slightly faster
prefill; it is a different kind of number. That is what the Osaurus cells are full of.

**(b) The cache is on disk, and it was written while the column ran.**
`~/.osaurus/cache/kv_v2/` gained **eight KV entries totalling 566.0 MB** inside the primary
column's window — at 15:40, 15:41, 15:45, 15:46, 15:51, 15:52, 15:57 and 15:58, i.e. during the
column's first four visits. The column's second visit (16:02–16:16) wrote **no new KV entry file
at all**, and neither did the replicate (16:38–16:56); the only files those windows touched are
the SQLite index's own (`cache_index.db`, `-shm`, `-wal`, mtimes 16:49–16:56), which is what
"already resident" looks like on a content-addressed store. The directory holds ~11 GB from
earlier sessions, and the run records carry no field that could have shown any of this — which is
the same disease, in a new runtime, that the design's confound #7 was written to prevent.

**(c) Something outlived the process, and the records say so.**
Because each visit starts a fresh server process, a fresh in-process cache cannot explain why the
second visit's first prefill request was also fast. The entry outlived the process — either on
disk, or in a resident app the next `serve` invocation reattached to. These records cannot separate
those two, and this document does not pretend otherwise; what they can establish is that *some*
reuse outlived a process whose RAM cache could not have.

**(d) What this does and does not contaminate.**

| figure, Osaurus `prefill` rows | status |
|---|---|
| `decode_tps` (the metric every table ranks by) | **sound.** The rate is completion tokens over the span from first content token to last; a reused prefix shortens the wait for the first token and cannot change the per-token cost of the 64 tokens that follow |
| `ttft_p50_s`, `ttft_p90_s`, `prefill_tps` | **not prefill figures.** `prefill_tps = prompt_tokens / ttft_s` (`report.py`), so 2,886.7 tok/s is 1319 / 0.457 — a lookup's reciprocal. Osaurus's only un-cached prefill in each cell (≈385, 373, 354 and 372 tok/s for the four cells, from the 3.4–3.7 s first requests, which may still carry one-time kernel-compilation cost and are therefore a *lower* bound) is 7.5–8.8x below the published figure and below vMLX's real 536.3 tok/s on the same prompt shape |
| the format ordering *within* the Osaurus column | **sound**, with a caveat that is stated rather than assumed: every cell in the column ran under the same host state, so the lookup is a constant, and the ranking is on `decode_tps` regardless |
| any cross-runtime `prefill` comparison of TTFT or prefill throughput | **void.** vMLX prefills every request; Osaurus looked it up. §5 states this beside the row |

### 4.4 The replicate: the decode lead survives, `chat` and `prefill` sit in the band

`results/grid-jang-dense/replicate/20260917T203824Z-format`, `jang4s__osaurus` against
`oq4__osaurus`.

| workload | `jang4s` | `oq4` | gap | primary's gap | reading |
|---|---|---|---|---|---|
| `decode` | 46.0 | 42.2 | **JANG +9.0%** | JANG +9.5% | replicated lead |
| `chat` | 49.6 | 50.5 | **`oq4` +1.8%** | JANG +8.6% | tie — inside the band |
| `prefill` | 59.0 | 58.4 | JANG +1.0% | JANG +6.1% | tie — inside the band |

The replicate's `prefill` cells had **no cold request at all** (first prefill requests 0.328 s and
0.322 s), which is (b) of §4.3 stated as a prediction that held: by the replicate, both prompts
were already in the cache from the primary column.

---

## 5. The cross-runtime JANG axis

Same artifact, two independent loaders. Nothing was re-measured for this row; it is the `jang4s`
row of the grid plus the same row of the replicate, and the two directories of each pair share
every pin the join guard compares (`cache_state` `null`, the same plateaus, the same literals).
Identical bytes are confirmed on both sides: `disk_bytes` = 3,207,385,506 on every `jang4s` row of
all four runs, and one snapshot revision, `4567967a46cd9e9bf26d3bb491ddd422ad607775`.

| workload | vMLX primary | Osaurus primary | vMLX lead | vMLX replicate | Osaurus replicate | vMLX lead |
|---|---|---|---|---|---|---|
| `decode` | 54.2 | 42.5 | **+27.5%** | 59.1 | 46.0 | **+28.5%** |
| `chat` | 55.2 | 48.1 | +14.8% | 60.0 | 49.6 | +21.0% |
| `prefill` | 60.2 | 55.8 | +7.9% | 62.7 | 59.0 | +6.3% |

Supporting figures on `decode`, both primary: TTFT p50 0.185 s against 0.297 s, ITL 0.0185 s
against 0.0236 s, aggregate 53.5 against 41.5 tok/s. vMLX is ahead on every one of them, and the
gap is widest on the metric that matters most for sustained generation.

**What this row establishes, and what it cannot.** It establishes that two loaders given identical
weights do not produce the same number — by 27.5% on decode, 14.8% on chat and 7.9% on the prefill
workload's decode rate — and it is the only place in this project where that comparison has one
variable in it. It cannot attribute the difference to anything inside either implementation:
loader, scheduler, Metal usage, KV handling and memory accounting all differ between these two
runtimes, and the row moves all of them at once.

**The column-order caveat, stated because the guard did not operate.** The design's §2.5 required
the replicate's column order to be the reverse of the primary's, so that a session-long thermal or
load trend could not alias onto runtime identity. The runner ran vMLX first in the primary *and*
first in the replicate (§8.2), so the guard the protocol intended was not in force. The substitute
evidence is the pair of gaps themselves: the same comparison taken at two different points in a
session in which the twelve replicated cells moved between −13.6% and +14.5% produces +27.5% and
+28.5% — a 1.0 pp spread. A session trend that could manufacture a 27.5% gap would have to move it
between the two occasions it was measured, and it does not.

**Two structural limits ride on this row and are not negotiable.**

- **Loader and runtime are not separable here.** The claim is "the two implementations differ, by
  this much, on identical bytes", never "vMLX's loader is 27.5% faster than Osaurus's scheduler" or
  any other cut through the pair.
- **`cold_load_s` and `peak_mb` may not be read across it.** `report.CROSS_RUNTIME_UNCOMPARABLE`
  prints its reason above any runtime-axis ordering by either. §7 gives the numbers with their
  sums and their non-comparability.

---

## 6. Attribution breakdown: why 4.15 bits beats 4.0 bits

The question the design pre-registered (§3.1) is whether JANG's speed is the weights or the thing
that loads the weights. On this artifact set, three candidate causes exist and one of them is
already dead.

### 6.1 Size is eliminated, and that is the cleanest result in this study

| artifact | declared `actual_bits` | `bit_widths_used` | block | bytes on disk | GiB |
|---|---|---|---|---|---|
| `jang4s` (JANG_4S) | **4.15** | `[4, 6]` | 64 | **3,207,385,506** | 2.987 |
| `stock4bit` | 4.0 (uniform) | — | — | 3,061,131,520 | 2.851 |
| `oq4` | ~4 (mixed) | — | — | 3,160,559,814 | 2.944 |
| `oq4e` | ~4 (mixed) | — | — | 3,167,949,891 | 2.950 |

The JANG bundle is **4.8% larger than the stock-4bit artifact** and 1.5% larger than `oq4`, and it
declares *more* average bits (4.15 against ~4.0) with two widths present rather than one. A decode
lead that holds while carrying more bytes and more bits cannot be a size effect and cannot be a
fewer-bytes-per-token effect. This is the one comparison in the set at near-equal precision, and it
points away from precision as the explanation.

### 6.2 The accelerator paths are pinned off, so they cannot be the explanation either

Each of these is a logged fact of this campaign, not a setting read off a config:

| candidate accelerator | what would have shown it | what the campaign shows |
|---|---|---|
| `mx.compile` (JIT) | `JIT: mx.compile applied successfully — running warmup pass` | absent from all 12 vMLX logs; `--no-jit` on every start command. Independently, vMLX's auto-JIT default excludes multimodal and hybrid SSM/Mamba models (`docs/runtimes/vmlx.md` §7.1; `cli.py:2132-2136`), and this bundle is both (`has_vision: true`, `cache_type: hybrid`) — so the JANG cell could not have been the compiled one even if the flag had been omitted |
| MTP / speculative decode | `MLLM native MTP skipped for request=…` | present on the requests of every vMLX cell, including the JANG cells that ship `vmlx_mtp_proposal_head.json` |
| Loader-level TurboQuant KV | a `TurboQuant:` state line | `TurboQuant KV skipped: VMLX_DISABLE_TQ_KV=1`; the dense bundle carries no `turboquant` block for the auto path to find |
| Prefix/disk cache | a collapsing TTFT sequence | flat (§3.0), with both cache flags disabled |

**So the JANG lead was measured with the JANG artifact's accelerator switches off and the portables'
switches equally off.** The vendor's headline decode path is JIT-on; this study's number is a floor
for it, not a replica of it — and that is what makes the remaining explanation interesting.

### 6.3 What is left standing, and why this artifact set cannot split it

Two mechanisms survive, and they travel together in every cell that produced a lead.

1. **The weight layout: mixed-bit packing, including embeddings at half width.** The bundle is
   per-tensor assigned (`bit_widths_used: [4, 6]`, block 64, asymmetric, `mx.quantize`), and its
   tensor geometry is not the shape a generic loader expects — the v1 loadability probe measured
   three independent runtimes refusing it with the *same* error on the same tensor:
   `Expected shape (248320, 640) but received shape (248320, 320) for parameter
   language_model.model.embed_tokens.weight` (`2026-09-15-grid-loadability-probe.md`). That is a
   packed half-width embedding, measured from the artifact, not a documentation claim. What vMLX
   does with it is visible in this campaign's logs and is a loader step the portables do not take:
   **`Pre-fixed 217 module(s) with mixed-precision bit widths`** on every JANG load, in a process
   whose portables log the generic `MLLM loaded successfully` line instead.
2. **The kernel path that unpacked layout selects.** vMLX ships family-specific fused Metal kernels
   for this model family (`docs/runtimes/vmlx.md` §6 and Appendix A: the `VMLX_QWEN35_*` toggles,
   part of 438 kernel switches) and its JANG-affine path is explicitly a "compile-eligible decode
   path" (§7.1). Which kernels ran for this bundle is **not observable in these records** — the
   loader's own line names the pre-fix, not the kernel, and this study pinned the one switch that
   would have let a reader see compilation happen.

The dispatch that commissioned this document attributes the lead to "custom Metal kernel unpacking
and packed half-width embeddings". The narrower, defensible statement is the one above: the half-
width packing is evidenced from the artifact, the mixed-width pre-fix is evidenced in the loader
trace, and the kernel selection is the part that this artifact set cannot separate from it. The
design said the same thing from the other side (§3.1a: "it cannot, however, separate packing from
kernel selection: both travel with the bundle"), and the deferred JIT A/B named in §3.1c does not
separate them either — it moves the accelerator, not the packing.

**Attribution the study may publish**, in the design's own vocabulary: *on `Qwen3.5-4B`, in vMLX
1.6.59 and Osaurus 0.25.6, the JANG_4S bundle decoded the 512-token shape ahead of the best
portable format by the margins in §1.2, while carrying 4.8% more bytes than the uniform-4-bit
artifact and with JIT, MTP and KV quantization each pinned off. The remaining candidate causes are
the bundle's own packed mixed-bit layout and the loader/kernel path that consumes it, and this
measurement does not separate those two.*

---

## 7. Memory and cold-start cost

### 7.1 Peak footprint (`footprint -p <pid>`, `phys_footprint`)

| workload | vMLX `jang4s` | vMLX portables | Osaurus `jang4s` | Osaurus portables |
|---|---|---|---|---|
| `chat` | 3826 | 3819 / 3838 / 3955 | 2579 | 1424 / 1643 / 1645 |
| `prefill` | 4640 | 4595 / 4727 / 4734 | 3591 | 2602 / 2850 / 2934 |
| `decode` | **3820** | 3819 / 3843 / 3946 | **3400** | 2216 / 2466 / 2472 |

Within a column the footprints are tight and format-light: vMLX's four decode cells sit inside
127 MB of each other, and the JANG cell at 3820 MB is *not* the largest — `oq4e`, whose artifact is
39.4 MB smaller on disk, reports 3946 MB. Osaurus's are less tight and are dominated by the
runtime's own accounting rather than by the weights.

**Across runtimes this number is not one quantity and no ordering may be read from it.** vMLX
reports a footprint within a few percent of the weight bytes; Osaurus reports roughly half of them,
because it holds weights in wired, GPU-pinned pages that `phys_footprint` charges differently (the
measured basis is `2026-09-16-footprint-is-not-one-quantity.md`, and `report.CROSS_RUNTIME_UNCOMPARABLE`
prints the reason above any runtime-axis ordering on it). The grid obeys this: its runtime-axis
lines order by `decode_tps` and never by memory.

### 7.2 Cold start: two numbers, never one

| runtime | `cold_load_s` | `first_request_s` | sum | what the second number is |
|---|---|---|---|---|
| vMLX 1.6.59 | 7.06–7.08 (primary), 7.08 / 8.11 (replicate) | 1.68–2.17 (primary), 1.69 / 1.79 (replicate) | **8.76–9.24 s**, replicate 8.87–9.80 s | an ordinary warm request: vMLX loads weights before readiness, so `cold_load_s` is the load |
| Osaurus 0.25.6 | 1.25–1.29 (primary), 1.25 / 1.28 (replicate) | 2.99–4.71 (primary), 2.77 / 2.92 (replicate) | **4.27–5.96 s**, replicate 4.02–4.20 s | a deferred load: Osaurus is *listening* in 1.25 s and loads on the first request, which is why a cross-runtime load comparison uses the sum — and why the sum is the only figure in this section that is comparable at all |

The largest `first_request_s` of the campaign is `optiq__osaurus` at 4.71 s, and the leaderboard
annotates it correctly (+1.26 s over the median measured request of the workload that made it: a
load this runtime deferred past readiness). Ranking on `cold_load_s` alone would name Osaurus
**5.5–5.7x** the faster loader; ranking on the sum names it 2.1–2.3x, and the sum is what the
design's §5.5 says to use.

### 7.3 A third cost this study did not intend to measure

The Osaurus disk cache is not just a confound (§4.3(b)) — it is a cost. `~/.osaurus/cache/kv_v2/`
holds **~11 GB** and gained **566.0 MB** during one 40-minute column, and nothing in this harness
clears it or reports it. The design's rule that "raw observations are never discarded" has a
counterpart here that this campaign discovered the hard way: a runtime's on-disk cache is part of
its measured conditions, and a study that does not pin it is measuring whatever the last session
left behind.

---

## 8. Threats to validity and boundaries

### 8.1 The `cache_state` pin was not taken — and in Osaurus it is visible in the data

Covered in §2.2 and §4.3 and restated here as the campaign's first-order defect. The design
required `--cache-state off` on every run, host cache keys false, and per-cell `shasum` evidence;
none of the three was done. On vMLX this is provably a no-op. On Osaurus it is the difference
between measuring prompt processing and measuring a lookup, and the campaign's own numbers show
the lookup: 3.4–3.7 s first requests against 0.27–0.57 s for every one that followed, and no cold
request at all in the replicate.

**What this changes**: the Osaurus `prefill` rows' TTFT and prefill throughput are not prefill
figures and no cross-runtime prefill statement may use them. **What it does not change**: the
`decode` lead in either column (ranked on a metric a cache cannot move), and therefore the R1
reading that this study exists to test.

**What the record still owes**: whether the entry that survived the process boundary came from
`cache/kv_v2` or from a resident app reattached by the next `serve` invocation. The records cannot
separate those, and the per-cell digests and cache pin that would have made it decidable were not
taken.

### 8.2 The replicate's column order was not reversed

The design pre-registered the reversal (§2.5, §6.1) so that a session trend could not alias onto
runtime identity, and `scripts/run_jang_dense.sh` ran vMLX before Osaurus in both passes
(`runner.log:3`, `:147`, `:151`). The guard therefore did not operate. §5 states the substitute
evidence — two orderings of the same cross-runtime pair, 1.0 pp apart while the cells inside them
moved 8–15% — and the limit that rides with it: the substitute is a replication, not the
pre-registered design.

### 8.3 R-reproduce fires on 9 of 12 cell pairs, so the campaign's absolute levels are not visit-stable

| runtime | workload | cell | primary | replicate | change |
|---|---|---|---|---|---|
| vmlx | `decode` | `jang4s` | 54.2 | 59.1 | **+9.0%** |
| vmlx | `decode` | `stock4bit` | 44.2 | 50.6 | **+14.5%** |
| vmlx | `chat` | `jang4s` | 55.2 | 60.0 | **+8.7%** |
| vmlx | `chat` | `stock4bit` | 60.5 | 52.3 | **−13.6%** |
| vmlx | `prefill` | `jang4s` | 60.2 | 62.7 | +4.2% |
| vmlx | `prefill` | `stock4bit` | 60.7 | 58.1 | −4.3% |
| osaurus | `decode` | `jang4s` | 42.5 | 46.0 | **+8.2%** |
| osaurus | `decode` | `oq4` | 38.8 | 42.2 | **+8.8%** |
| osaurus | `chat` | `jang4s` | 48.1 | 49.6 | +3.1% |
| osaurus | `chat` | `oq4` | 44.3 | 50.5 | **+14.0%** |
| osaurus | `prefill` | `jang4s` | 55.8 | 59.0 | **+5.7%** |
| osaurus | `prefill` | `oq4` | 52.6 | 58.4 | **+11.0%** |

Under R-reproduce, nine of twelve pairs are published with both figures and no ordering between
them. Two readings follow, and both are printed rather than smoothed:

- **Direction of the movement**: eleven of twelve cells read *higher* in the replicate, which ran
  later in the session and after a second warm-up of the same artifacts. The one cell that moved
  down is `stock4bit__vmlx` on `chat` (−13.6%), the cell whose primary carried the campaign's
  largest negative drift (−24.7%) — a cell in thermal decline in visit 1, consistent with its
  visit-2 figure sitting between its own early and late medians.
- **Why the claim survives anyway**: every comparison this document publishes is *within* a visit —
  two cells measured in the same session window, interleaved by the visit plan — and the
  replication rule exists to test whether such a comparison repeats. It does, on the one workload
  that carries the claim (§1.2). What R-reproduce forbids is reading §3.1's "54.2" as the JANG
  bundle's decode rate on this machine; it is that cell's rate on that visit, and the replicate's
  59.1 is the same statement about a later one.

### 8.4 The pins make this a floor for vMLX's shipped JANG path, not a replica of it

JIT and native MTP are off in every vMLX cell of this study by design, so the JANG cell differs
from its column only in its bytes — but the vendor's headline path is JIT-on, and the JANG-affine
auto-JIT default exists precisely because someone measured it worth having. **The vMLX numbers here
are a floor for that path, not a measurement of it.** The deferred single-variable A/B (`--enable-jit`
against `--no-jit`, artifact and runtime constant) is the cheapest experiment this project will ever
have, it is named in the design as the first follow-up, and it would price exactly the accelerator
that was pinned off. It is not run here.

### 8.5 The boundaries, stated plainly

- **One model.** `Qwen3.5-4B`, dense, hybrid SSM. Nothing here transfers to the MoE model, and
  R4 — the model-specificity reading — is **not decidable from this plan**: it needs Plan 01-02's
  `LFM2.5-8B-A1B` column, and until that runs, "JANG leads" is a statement about this artifact on
  this machine.
- **Not equal precision.** JANG_4S at 4.15 average bits against stock's uniform 4 is
  near-equal-precision *for the dense pair that carries the cleanest result*; `oq4` and `oq4e`
  declare their own mixed assignments, and the MoE study's 2.37-bit arm will not have this property
  at all.
- **No accuracy claim.** Nothing here speaks to what any format costs in quality. A JANG lead in
  tok/s and a JANG loss in accuracy can both be true; that is a separate study with its own pins.
- **No cross-runtime memory or load ranking.** §7 explains why, with the measured basis.
- **A three-model-token difference between the columns.** The same literal prompt is 29 tokens to
  the vMLX column and 34 to the Osaurus column (1,314 against 1,319 for the prefill literal) —
  template rendering, identical for every cell within a column, and worth naming before anyone
  compares `prefill_tps` across the row (which §4.3 forbids for other reasons anyway).
- **Warmup left a fingerprint on the campaign.** Twenty of the twenty-four primary rows drifted
  positive (range −24.7% to +33.4%). The four negatives are `stock4bit__vmlx`'s two (−24.7% on
  `chat`, −12.4% on `prefill`, §3.2), `jang4s__vmlx` `chat` (−0.8%) and `optiq__osaurus` `decode`
  (−1.0%) — and all twelve replicate rows drifted positive (+1.3% to +14.7%). The grid prints the
  marker; this document did not drop a single row for it, per the rule that a cell still moving is
  ranked and annotated because dropping it would delete the only row that says the window was too
  short.

---

## Appendix A — evidence index

| what | where |
|---|---|
| design and pre-registered readings R1–R4, tie band, replication rules | `docs/research/2026-09-17-v2-track1-jang-study-design.md` |
| the runner, its pins, its Osaurus toggle/restore and its sweep order | `scripts/run_jang_dense.sh`; `results/grid-jang-dense/runner.log` |
| vMLX column rows, drift notes, metric cards | `results/grid-jang-dense/20260917T185649Z-format/{leaderboard.md,results.jsonl}` |
| Osaurus column rows, drift notes, metric cards | `results/grid-jang-dense/20260917T194005Z-format/{leaderboard.md,results.jsonl}` |
| the two columns joined, with the `jang4s` row | `results/grid-jang-dense/grid.md` |
| replicates | `results/grid-jang-dense/replicate/20260917T{T202054Z,T203824Z}-format/` |
| JANG loader trace, JIT absence, MTP-skipped lines, `Pre-fixed 217` | `results/logs/vmlx-20260917T151535…153409-65592.log`, `…T162609…163031-55306.log` |
| the flat-prefill control (vMLX) and the collapsing one (Osaurus) | the same logs; and every cell's `warmup_observations` in the four `results.jsonl` |
| Osaurus KV entries written during the column | `~/.osaurus/cache/kv_v2/` (8 files, 566.0 MB, mtimes 15:40–15:58) |
| what an Osaurus prefix hit costs on this model | `docs/research/2026-09-17-cache-state-split.md` (0.404 s against 9.401 s, 23.29x) |
| the packed-embedding refusal, measured on three runtimes | `docs/research/2026-09-15-grid-loadability-probe.md` |
| vMLX's auto-JIT exclusions and JANG-affine kernel path | `docs/runtimes/vmlx.md` §§6, 7.1, 8; `vmlx` `cli.py:2119-2159` |
| `prefill_tps`, `decode_tps` and `CROSS_RUNTIME_UNCOMPARABLE` formulas | `ohyesmlx/report.py` |
| the cache pin's meaning, and that `None` is not `off` | `ohyesmlx/runtimes.py` (`CACHE_STATES`, `Osaurus.cache_state_refusal`), `ohyesmlx/measure.py` (`run_cells`) |

## Appendix B — recompute

Everything in this document is recomputed from the four `results.jsonl` files; the rendered
leaderboards were read for their notes, not for their numbers. `decode_tps` is not stored in the
record — `report.py` derives it as `completion_tokens / (last_content_s − ttft_s)`, median across
the measured requests — so a reader recomputes it from `observations`. Two spot checks:

```sh
# the JANG lead on the decode workload, primary, both runtimes, on both bases
python3 - <<'EOF'
import json, statistics as st
def tps(r): return st.median([o["completion_tokens"]/(o["last_content_s"]-o["ttft_s"])
                              for o in r["observations"]])
for d, best, jang in [("20260917T185649Z-format", "oq4__vmlx",    "jang4s__vmlx"),
                      ("20260917T194005Z-format", "oq4__osaurus","jang4s__osaurus")]:
    rows = [json.loads(l) for l in open(f"results/grid-jang-dense/{d}/results.jsonl")][1:]
    t = {r["cell"]["id"]: tps(r) for r in rows if r["workload_id"] == "decode"}
    j, b = t[jang], t[best]
    print(f"{d}  full {j:.3f}/{b:.3f} -> {100*(j-b)/b:+.2f}%   "
          f"rendered {round(j,1)}/{round(b,1)} -> {100*(round(j,1)-round(b,1))/round(b,1):+.2f}%")
EOF

# the Osaurus prefill signature: first prefill request against the rest of its warmups, per cell
# (§4.3's table widens the second column to include the measured requests as well)
python3 - <<'EOF'
import json
for f in ["20260917T194005Z-format", "replicate/20260917T203824Z-format"]:
    rows = [json.loads(l) for l in open(f"results/grid-jang-dense/{f}/results.jsonl")][1:]
    for r in rows:
        if r["workload_id"] != "prefill": continue
        w = [o["ttft_s"] for o in r["warmup_observations"]]
        print(f"{f:38s} {r['cell']['id']:18s} first={w[0]:.3f}s rest={min(w[1:]):.3f}-{max(w[1:]):.3f}s")
EOF
```
