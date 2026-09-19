# Milestone v3 Phase 1 — 35B MoE Serving Benchmark Study Design: Qwen3.6-35B-A3B across Stock 4-bit, OptiQ, oQ4, and JANG

Date: 2026-09-19. **Design only. No measurements in this document.** No runtime was started, no
model was loaded, no tensor was read. Every figure below is either recomputed from the hub or
from the shipped configuration today (with the query that recomputes it), or quoted from a run
record or a v1/v2 document, and each one names its source. The numbers this study will produce
do not exist yet.

Subject: `Qwen3.6-35B-A3B` — a 35.95 B-parameter hybrid-attention MoE with 256 routed experts,
8 routed per token, and ~3 B active parameters — in four 4-bit artifacts, on the five runtimes
this harness drives. Four downloads, one model, one variable at a time, at the scale where
resident memory stops being a detail.

---

## 1. Executive summary and the problem statement

### 1.1 The question

Every published number this project owns was measured on a model that fits comfortably in
memory. The hero models are `Qwen3.5-4B` (2.99 GiB) and `LFM2.5-8B-A1B` (4.45 GiB) — a fifth and
a fourteenth of a 64 GiB machine. At those sizes the question the project exists to answer, *is
it your runtime or your quantization that is costing you speed and memory*, has only ever been
asked in the regime where memory is free.

At 35 B the same question changes character in three ways, and each one is a reason the sub-10 B
answers cannot simply be assumed to carry upward:

1. **The model is a third of the machine, not a fifth of it.** 18.35–23.00 GiB of weights against
   64 GiB of unified memory: 28.7%–35.9%. Peak footprint is what decides whether a configuration
   is usable at all, and peak footprint is the metric Phase 5 established is *not one quantity
   across runtimes* (`2026-09-16-footprint-is-not-one-quantity.md`). At 4 B that un-comparability
   was a footnote; at 35 B it is the headline risk.
2. **The routed path is 1/12 of the parameters.** 8 of 256 experts are read per token. Decode is
   therefore a very small number of bytes per token drawn from a very large file, which is a
   different access pattern from every model this project has measured.
3. **This is the family that produced the founding defect.** Stock `mlx_lm.server` loaded
   `Jundot/Qwen3.6-35B-A3B-oQ4-mtp` — 256 experts, this architecture — in ~4 s, returned HTTP
   200, generated at full throughput, and produced mixed-script token salad
   (`2026-09-14-oq-portability-spike.md`). Phase 4 established the failure is runtime-specific,
   not format-specific (`2026-09-15-phase4-256-expert.md`), but that was one artifact, two
   runtimes, and one 64-token request. This study puts the same architecture through five
   runtimes and four quantizations with the gate that caught it on every row.

The question, stated exactly: **at 35 B, on one runtime at a time and one quantization at a
time, which of the four 4-bit artifacts is worth its disk and its memory, and does the ordering
that holds inside a runtime survive when the runtime changes?**

### 1.2 What 35 B changes: residency on a 64 GiB M2 Max

The host is an M2 Max in a laptop chassis: 64 GiB of unified memory shared by the CPU, the GPU
and everything else the machine is doing, and a thermal envelope that throttles under sustained
inference (`AGENTS.md`, "Thermal"). Three quantities, all derived from shipped configuration,
bound what this study can ask:

| quantity | value | where it comes from |
|---|---|---|
| weights, smallest artifact (`jangtq4`) | 18.354 GiB = **28.7%** of unified memory | §2.2, hub API |
| weights, largest artifact (`optiq`) | 22.998 GiB = **35.9%** of unified memory | §2.2, hub API |
| KV cache per token, all 10 full-attention layers at fp16 | 20,480 B = 20.0 KiB/token | derived: 2 kv_heads × 256 head_dim × 2 (K and V) × 2 B × 10 layers |
| KV cache at the three pinned workloads | chat 3.0 MiB, prefill 26.8 MiB, decode 10.5 MiB | 20.0 KiB × (prompt + cap), on §6.1's measured prompt counts |
| KV cache at the declared context limit | 5.000 GiB | 20.0 KiB × 262,144 |

**The KV cache is a rounding error at these workloads and would not be at long context.** The
pinned suite's longest shape is a 1,309-token prompt plus a 64-token answer, so the whole KV
state is under 27 MiB against ~20 GiB of weights. That is worth stating because it *bounds the
study's memory claim*: what this study measures about memory is the weights plus each runtime's
own overhead, and nothing here speaks to context growth. The 5.000 GiB figure at the model's
declared 262,144 max position is the reason context work is Phase 2's (Plan 03-04/03-05) and not
a missing row here.

The dispatch's framing — weights "occupying ~35-45% of 64GB unified memory" — is a claim about
*residency*, and residency is `peak_mb`, which has not been measured. Weight bytes alone are
28.7%–35.9% (§2.3); a measured `peak_mb` will sit above that floor by whatever a runtime adds,
and measuring that difference per runtime is H4's job rather than an assumption this document
makes. **No peak footprint is asserted anywhere in this document.**

Disk is the second residency constraint, and it is the one already paid:

| | value |
|---|---|
| four artifacts, current revisions | 85,956,850,906 B = 85.957 GB = **80.053 GiB** |
| free on `/System/Volumes/Data` today | **186 GiB** (`df -h /Users/jrazz`, 2026-09-19) |
| fraction of free disk | **43.0%** |

One runtime holds weights at a time (`docs/interfaces.md`, "Exactly one runtime may hold weights
at any moment"), so the campaign never needs two of these resident. What it does need is that
the *download* is finished before the first cell is measured: a 86 GB fetch competing for the
same disk `cold_load_s` times is the one contention this project has already written a rule
about (`AGENTS.md`: "Never download while a measurement is running").

### 1.3 What the config implies about decode — arithmetic, not a measurement

The architecture makes one thing predictable without running anything, and it is worth writing
down so that the first measured cell can be read against it rather than admired.

Per decoded token the routed path reads 8 experts × 3 matrices × (2048 × 512) = 25,165,824
parameters per layer, × 40 layers = **1,006,632,960 parameters**. **No artifact in §2.2 overrides
a single `.experts.` tensor**, so all four store this path under their global 4-bit rule. At 4
bits with group size 64 (0.5 B/param, plus two fp16 scale/bias words per 64-parameter group) that
is **0.566 GB per token from the routed experts alone** — the same arithmetic in every artifact.

The rest of the token's read is where the four bit plans diverge (§2.2), and it is stated on one
plan rather than waved at. On `jangtq4`'s declared plan — routed experts at 4, everything else at
8 — the shared expert (0.126 B params), the full attention stack (0.189 B), and the untied
`embed_tokens` and `lm_head` (1.017 B) add:

```
routed experts, per token, 4-bit     0.566 GB
shared + full-attention, 8-bit       0.334 GB
embed_tokens + lm_head, 8-bit        1.081 GB
                                     --------
weights read per decoded token       1.98 GB
```

At a 400 GB/s memory system that is an arithmetic ceiling of **~202 tok/s**. It is a ceiling and
not a prediction: it assumes perfect bandwidth, no kernel loss, no cache reuse and no contention,
and every real number lands below it. Its purpose is to fix the *shape* of H1 in §5.1 — decode at
this architecture is a memory-traffic measurement with a very small compute component — and to
give the probe a sanity band. `stock4bit` is the outlier on this arithmetic and is expected to
read *fewer* bytes than the figure above, because its map raises only 80 gate tensors to 8 bits
and leaves the shared expert, the attention stack and the embeddings at 4. **Nothing in this
paragraph is measured, and no published figure will be derived from it.**

### 1.4 The claim this study is allowed to make

At the end of Phase 1 the study must be able to say: *"in runtime R, on workload W, artifact A
did (or did not) beat artifact B by this much, at these pins, with these confounds named"* — and,
for each hypothesis of §5, whether the pre-registered condition was met.

It may not say that any format is the right choice in general: four artifacts on one model, one
machine, one 64 GiB memory configuration, is not a general claim. It may not say *why* beyond
what the confound ledger can attribute (§3.5), because the artifacts differ in bit assignment,
override coverage, sidecar contents, tensor packing and loader all at once. And it may not read
any number from a cell that did not produce language (§4).

---

## 2. The test matrix

### 2.0 How a matrix is read here

A cell is `(format, runtime)` and its id is `"<label>__<runtime>"`. `ohyesmlx run --study format`
holds the runtime constant and `--study runtime` holds the format constant; `cli._check_axis`
refuses a selection that varies both, before any runtime starts. A **column** (one runtime, many
formats) is the format axis — that is what this campaign runs, five times, one invocation per
runtime. A **row** (one format, many runtimes) is the runtime axis and falls out of the joined
grid for free. The best cell across the whole grid is a recommendation and never an attribution.

Labels are the vocabulary `scripts/gridspec.sh` and `scripts/gridspec-moe.sh` already use —
`stock4bit`, `oq4`, `optiq` — plus `jangtq4` for this model's JANG bundle. **Keeping those labels
is what forces this campaign into its own results directory**, and the reason is join guard 3:
*one format label pointing at two artifacts*. `stock4bit` on `Qwen3.6-35B-A3B` and `stock4bit` on
`Qwen3.5-4B` are different bytes under one name, so a grid that joined this campaign's directory
with any earlier one would be refused — correctly. `results/grid-35b/` is the campaign's
directory, and a document may print two campaigns' tables side by side where the tool may not
produce them in one table (`docs/research/2026-09-17-v2-track1-jang-study-design.md` §2.4, same
rule).

### 2.1 Architecture parity — verified

Every artifact here has to agree about the architecture, or the column varies two things and the
disagreement would be invisible in every table it produced. Each repo's own `config.json` was
read today; the `text_config` block is byte-comparable field by field:

| field | stock4bit | optiq | oq4 | jangtq4 | |
|---|---|---|---|---|---|
| `model_type` | `qwen3_5_moe_text` | `qwen3_5_moe_text` | `qwen3_5_moe_text` | `qwen3_5_moe_text` | SAME |
| `num_hidden_layers` | 40 | 40 | 40 | 40 | SAME |
| `num_experts` | 256 | 256 | 256 | 256 | SAME |
| `num_experts_per_tok` | 8 | 8 | 8 | 8 | SAME |
| `hidden_size` | 2048 | 2048 | 2048 | 2048 | SAME |
| `moe_intermediate_size` | 512 | 512 | 512 | 512 | SAME |
| `shared_expert_intermediate_size` | 512 | 512 | 512 | 512 | SAME |
| `num_attention_heads` / `num_key_value_heads` | 16 / 2 | 16 / 2 | 16 / 2 | 16 / 2 | SAME |
| `head_dim` | 256 | 256 | 256 | 256 | SAME |
| `vocab_size` | 248320 | 248320 | 248320 | 248320 | SAME |
| `full_attention_interval` | 4 | 4 | 4 | 4 | SAME |
| `layer_types` | 30 linear / 10 full | 30 / 10 | 30 / 10 | 30 / 10 | SAME |
| `max_position_embeddings` | 262144 | 262144 | 262144 | 262144 | SAME |
| `mtp_num_hidden_layers` | 1 | 1 | 1 | 1 | SAME |
| `tie_word_embeddings` | False | False | False | False | SAME |

Recompute it — this exact command was run on 2026-09-19 to produce the table above:

```sh
curl -s https://huggingface.co/mlx-community/Qwen3.6-35B-A3B-4bit/raw/main/config.json \
  | python3 -c "import json,sys; c=json.load(sys.stdin)['text_config']; \
print({k: c[k] for k in ('num_hidden_layers','num_experts','num_experts_per_tok','hidden_size','full_attention_interval')})"
# {'num_hidden_layers': 40, 'num_experts': 256, 'num_experts_per_tok': 8, 'hidden_size': 2048,
#  'full_attention_interval': 4}
```

Three readings this table fixes, each one a trap for a careless write-up:

1. **"Hybrid attention" is `full_attention_interval: 4`,** and it is exact: layers 3, 7, 11, …, 39
   are `full_attention` and the other 30 are `linear_attention` (a gated deltanet stack —
   `linear_num_key_heads: 16`, `linear_num_value_heads: 32`, `linear_conv_kernel_dim: 4`). Every
   *cache* consequence of that is already measured on `Qwen3.5-4B`, which is hybrid too: at
   4,096 tokens only oMLX (17.4×) and Osaurus (23.3×) serve a warm prefix hit, while mlx-lm and
   OptiQ cannot trim a hybrid `ArraysCache` and vMLX declines its own prefix cache for hybrids
   without block-disk (`2026-09-17-cache-state-split.md`). The 35 B cells are a *pin* on that
   axis (§6.2), not a re-measurement of it.
2. **The total parameter count is the vendor's, not this document's.** `Qwen/Qwen3.6-35B-A3B`
   reports 35,951,822,704 stored parameters in its safetensors metadata; the MLX bf16 sibling
   reports 35,107,181,936. "35B" and "A3B" are the family's labels, and the active-parameter
   figure of ~3 B is **quoted from that label and not computed here** — §1.3's arithmetic derives
   bytes read per token, which is a different quantity and the only one the study depends on.
3. **The declared architecture is identical; the stored tensor inventory is not.** The four
   weight maps hold 2,090 / 2,090 / 2,010 / 1,930 tensors, all four carrying exactly 333
   `vision_tower` tensors. The difference (80 and 160 fewer on the language-model side for oQ4
   and JANGTQ4) is **recorded and not explained**: nothing checked here establishes which tensors
   a quantizer folded, dropped or renamed, and a claim about it would need a tensor read this
   role does not perform. What matters for the matrix is §3.3: all four are multimodal.

### 2.2 The four artifacts, as they are on the hub today

Sizes are the current revision's file sum from `https://huggingface.co/api/models/<repo>?blobs=true`,
sidecar files included — which is what `ohyesmlx.measure.artifact_bytes` walks and what a cell's
`disk_bytes` records. Queried 2026-09-19. `GiB` is binary, `GB` decimal; both are given because
the dispatch's figures are GiB written as GB (§2.3).

| label | repo | revision | files | bytes | GiB | GB | downloads | last modified |
|---|---|---|---|---|---|---|---|---|
| `stock4bit` | `mlx-community/Qwen3.6-35B-A3B-4bit` | `38740b847e4cb78f352aba30aa41c76e08e6eb46` | 17 | 20,429,169,263 | 19.026 | 20.429 | 30,346 | 2026-04-16 |
| `optiq` | `mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit` | `70a3aa32c7feef511182bf16aa332f37e8d82014` | 17 | 24,693,956,069 | 22.998 | 24.694 | 6,042 | 2026-07-14 |
| `oq4` | `Jundot/Qwen3.6-35B-A3B-oQ4` | `0c710dbaa6cf7cb70a9a0740e2df263effaada9e` | 16 | 21,125,808,699 | 19.675 | 21.126 | 132 | 2026-04-23 |
| `jangtq4` | `JANGQ-AI/Qwen3.6-35B-A3B-JANGTQ4` | `0f77d193d3569eba03bc952141c255496aeae8cd` | 36 | 19,707,916,875 | 18.354 | 19.708 | 175 | 2026-09-08 |
| | | | | **85,956,850,906** | **80.053** | **85.957** | | |

What each artifact declares about itself — read from `config.json` (and `jang_config.json`) today.
This is the artifact's own claim, quoted as provenance and never trusted: the same rule a
server's self-reported tok/s gets.

| label | global rule | per-tensor overrides | the two big sidecars |
|---|---|---|---|
| `stock4bit` | affine, group 64, 4 bits | **80**, all at 8 bits (`mlp.gate`, `mlp.shared_expert_gate` for every layer) | none |
| `optiq` | affine, group 64, 4 bits | **512**: 118 at 4 bits, 394 at 8 bits | `optiq/mtp.safetensors` 1,644,816,498 B; `optiq/optiq_vision.safetensors` 893,179,469 B |
| `oq4` | affine, group 64, 4 bits | **306**: 113 at 5, 14 at 6, 179 at 8 | none |
| `jangtq4` | `mxtq`, group 64, `bits_default` 4 | **312**, all at 8 bits | `jangtq_runtime.safetensors` 10,664 B |

`jangtq4`'s sidecar states its bit plan by module class rather than by tensor name —
`routed_expert: 4`, `attention: 8`, `linear_attention: 8`, `shared_expert: 8`,
`embed_tokens: 8`, `lm_head: 8` — with `format_version 2` and `capabilities.cache_type: "hybrid"`.

Read across all four maps, the coverage is uneven and it matters which way:

| module class | `stock4bit` | `optiq` | `oq4` | `jangtq4` |
|---|---|---|---|---|
| `.experts.` (the routed path) | **no override** | **no override** | **no override** | **no override** |
| `shared_expert.*` | 0 | 120 | 120 | 120 |
| `shared_expert_gate` / `mlp.gate` | 40 / 40 | 40 / — | 40 / — | 0 / — |
| `linear_attn.*` / `self_attn.*` | 0 / 0 | 150 / 40 | 125 / 19 | 150 / 40 |
| `embed_tokens` / `lm_head` | 0 / 0 | 1 / 1 | 1 / 1 | 1 / 1 |

Three consequences, and the first is the one this study leans on:

1. **The routed path takes the global 4-bit rule in every artifact**, because no map names a
   single `.experts.` tensor. That is the one property all four share, it is where ~99% of the
   parameters live, and it is what makes §1.3's per-token arithmetic well defined for all four.
2. **`stock4bit` is not the 8-bit-outside-the-routed-path recipe.** Its 80 overrides reach only
   the routing gates; the shared expert, the attention stack and the embeddings stay at 4 bits.
   The other three raise all of those to 8. So `stock4bit` should read *fewer* bytes per token
   than the other three despite being larger on disk — which is the distinction H1 turns on, and
   the reason H1 is not a disk-size comparison.
3. **`jangtq4` is the smallest artifact while declaring the most 8-bit modules.** It stores the
   routed path more compactly than the affine recipe the others use. That is an *observation from
   two numbers this document measured*, recorded without a mechanism: nothing here establishes
   how `.tq_packed`/mxtq lays those bytes out, and this design does not claim to know.

One operational note that belongs to the plan rather than to the table: **a flat-layout copy of
the `optiq` artifact is already on this host**, at
`~/.cache/huggingface/hub/mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit/` — 24,693,961,658 B over 54
files, byte-complete against the revision above (the extra 5,589 B and 37 files are `hf`'s own
`.cache/huggingface/download/*.metadata`). `hf download` writes the *hub* layout, so fetching
that repo again leaves a second ~23 GiB copy of the same weights. The script says so; the
coordinator decides (§7.2).

### 2.3 Where the dispatch's figures differ from the hub

Three of the four sizes in the dispatch that commissioned this document agree with the hub today
to two decimal places **once read as GiB**, not GB: 19.03 / 19.67 / 18.35 GiB are the current
revisions of `stock4bit` / `oq4` / `jangtq4`. The rest do not, and each difference is worth
naming rather than carrying:

1. **`optiq` is 22.998 GiB, not 20.63.** The dispatched figure is exactly the artifact *minus its
   two `optiq/` sidecar tensors*: `24,693,956,069 − 1,644,816,498 − 893,179,469 = 22,155,960,102`
   B = **20.634 GiB**. Those two files are the bundled MTP head and the vision tower, they are
   part of the download, they are on disk in the directory a cell is handed, and
   `artifact_bytes` counts sidecar files by design. Quoting the subset as "the artifact" is the
   same class of error the v2 design recorded when a sidecar's declared `total_weight_bytes` was
   30% below the artifact on disk
   (`docs/research/2026-09-17-v2-track1-jang-study-design.md` §3.2/§4.3). **The table in §2.2 is
   what the hub says; the dispatch's row is corrected here rather than silently carried.**
2. **The four-artifact total is 80.053 GiB, not ~77.7 GB.** The two figures differ by very nearly
   the 2.364 GiB of sidecar above (the dispatched three are rounded to their GiB, which accounts
   for the last 0.01). Against 186 GiB free that is 43.0% rather than 41.8%: the download still
   fits, and it fits with the correction applied.
3. **`usedStorage` is not the artifact's size, and a reader who checks the API may see 45.8 GB
   for `optiq`.** The repo has accumulated revisions: its current revision is 24.69 GB while
   `usedStorage` reports 45,818,309,658 B. `disk_bytes` records what a cell is actually handed,
   so §2.2's numbers are the current revision's file sum and nothing in this study quotes
   `usedStorage`.
4. **The three "verified 100% architecture-identical" claims in the dispatch hold, and were
   re-verified independently** (§2.1): 40 layers, 256 experts, 8 routed per token, hidden 2048 —
   plus `full_attention_interval: 4`, `mtp_num_hidden_layers: 1` and vocab 248320, which the
   dispatch did not name and which this study pins too.

### 2.4 The columns, per runtime

`--study format`, one invocation per runtime, one run directory each, into `results/grid-35b/`.

| column | cells the probe must clear before the column runs |
|---|---|
| `mlxlm` | `stock4bit`, `oq4`, `optiq` |
| `omlx` | `stock4bit`, `oq4`, `optiq` |
| `optiq` | `stock4bit`, `oq4`, `optiq` |
| `vmlx` | `stock4bit`, `oq4`, `optiq`, `jangtq4` |
| `osaurus` | `stock4bit`, `oq4`, `optiq`, `jangtq4` |

**No cell in this table has been probed.** That sentence is the most important one in §2, and
§3 explains what each cell's prediction rests on and why v1's precedent is that predictions are
worth writing down and never worth trusting. A cell that does not load is `—` in the grid with
its reason printed in the write-up — never a synthetic `FAIL`, because a cell that was never
attempted is not a measured failure, and the grid's four entry states exist so a reader can tell
them apart (`docs/interfaces.md`, "The join guards"; §4.4 below).

The matrix is ragged by construction: three runtimes can carry the format axis three ways,
two can carry it four ways, and the JANG row can only be read across the two runtimes that load
JANG at all. That raggedness is a finding about the ecosystem, not a hole to be papered over.

### 2.5 Replication, and the tie band the study is pre-registered against

v1's runtime axis was first published and then withdrawn because the ordering moved under a
defensible change in how the window was taken: five adjacent pairs sat within 2.5% and swapped
places (`2026-09-16-phase5-joined-grid.md`). The study inherits that rule unchanged:

> **Adjacent cells within 2.5% are a tie, not an ordering.** 2.5% is not a physical constant; it
> is the largest gap v1 observed to change places when the window moved, and it is used here as a
> pre-registered band rather than as a discovered one.

**Replication is required for the cells that carry a hypothesis** and not for the ones that
describe a column. Each hypothesis of §5 names its decisive pair; after the columns run, each
decisive pair gets:

- a **replicate run** naming only those two cells, in its own run directory;
- with the **column order reversed** against the primary, so a session-long thermal or load trend
  cannot alias onto artifact identity — a real risk at 35 B, where every request runs a machine
  that is already hot;
- same pins, same workloads, same flag tuple.

**Pre-registered decision rules:**

- **R-tie.** A lead is published as a lead only if the primary and the replicate agree on the
  direction *and* the gap clears 2.5% in both. A lead that clears 2.5% in one run and sits inside
  the band in the other is a tie, with both numbers printed.
- **R-reproduce.** A replicate more than **5%** away from its primary on the same cell is
  published with both figures and no ordering between them. 5% is the project's existing
  drift-annotation threshold (`report.DRIFT_ANNOTATION_PCT = 5.0`), and the largest
  visit-to-visit disagreement measured inside one cell so far is 3.8%
  (`2026-09-17-cache-state-split-nonhybrid.md`).
- **R-nothing.** No replicate may be discarded for being inconvenient. A repeat run that
  disagrees is the finding; the campaign is not trimmed to the run that agreed.

---

## 3. Candidate serving runtimes and the compatibility matrix

### 3.1 The five runtimes on this host, as they are today

Versions were read on 2026-09-19 with each runtime's own probe. They are recorded per cell as
`runtime_version` and compared exactly across run directories by join guard 4, so a version step
between two columns is a refused join rather than a silent confound — Osaurus measured 1.15×
across exactly such a step in v1.

| runtime | version today | port | how the version is read |
|---|---|---|---|
| `mlxlm` | 0.31.3 | 8081 | `python -m mlx_lm --version`, in its own venv at `~/.local/share/ohyesmlx/mlx-lm-0.31.3/bin` |
| `osaurus` | **0.25.9** | 1337 | `osaurus doctor --json` bundle entry |
| `omlx` | 0.6.4 | 8100 | `omlx --version` |
| `optiq` | 0.5.6 | 8080 | `optiq --version` (recorded as the bare version, not the runtime's `mlx-optiq, version …` phrasing) |
| `vmlx` | 1.6.59 | 8000 | the engine's `__version__` read out of the shipped source — `vmlx --version` exits 2 |

Two standing facts that decide how a 35 B cell can fail, both already paid for:

- **Readiness is neither the port nor the model list.** mlx-lm binds 8081 and logs
  `Starting httpd` after its load thread has died; oMLX lists every directory in its catalog,
  including one it has already failed to load; Osaurus lists a model it then refuses as
  `not installed or registered with any provider`. The harness requires the model id *and* a log
  with no load failure — and reads the log a second time once the id appears, because a load
  failure is written *while* the model list is being answered (`ohyesmlx/runtimes.py`,
  `docs/interfaces.md`).
- **Osaurus takes no tuning flags.** Everything that decides what a cell measures lives in
  `~/.osaurus/config` and an app plist, so a 35 B Osaurus cell's conditions are only as good as
  the settings guarantee of §3.4. Note the host has moved since v1 was written up — 0.25.3 →
  0.25.6 → **0.25.9** — and the per-model `disableThinking` flag lives in the app plist, is set
  per model, and appears in neither the start command nor any file the drift guard reads. On this
  host it is **`true` for `OsaurusAI/Qwen3.6-35B-A3B-MXFP4-MTP`**, a sibling artifact
  (`docs/runtimes/osaurus.md` §4.4). The study's four Osaurus ids do not exist in that plist yet,
  so this is a **pre-flight** check after the first launch, not a prediction.

### 3.2 The matrix, as predictions with the evidence each row rests on

Every entry below is a prediction. The probe of §7.3 is what settles them, and v1's lesson is
quoted in full because it is the reason this section is written as evidence rather than as a
table of verdicts: **every predicted refusal in v1 was wrong, and the one real refusal was not
predicted** (`2026-09-15-grid-loadability-probe.md`).

| cell | prediction | what the prediction rests on | status |
|---|---|---|---|
| `stock4bit` in `mlxlm` | loads | mlx-lm 0.31.3 ships `qwen3_5_moe` — verified in a shipped interpreter at `…/mlx_lm/models/qwen3_5_moe.py`, with `mlx_lm-0.31.3.dist-info` beside it (`2026-09-15-format-matrix-and-tooling.md`); the artifact is plain mlx-community affine | **unprobed** |
| `stock4bit` in `omlx`, `optiq` | loads | oMLX's own README v0.6.4: "LLM — any model supported by mlx-lm"; `optiq serve` is a fork of the same server | **unprobed** |
| `stock4bit` in `vmlx` | ? | vMLX loaded the dense `Qwen3.5-4B` stock-4bit and the MoE `LFM2.5-8B-A1B` stock-4bit in v1 | **unprobed** |
| `stock4bit` in `osaurus` | ? | the v1 MoE *probe* recorded `LOADS` for Osaurus on the MoE stock-4bit while the *dense* one was refused as `not installed or registered with any provider` — and the MoE grid's Osaurus column nonetheless omitted the cell (`2026-09-16-moe-loadability-probe.md`; `scripts/gridspec-moe.sh`) | **unprobed** |
| `oq4` in all five | loads, five of five | oQ is oMLX's own quantizer and the artifact is portable affine with an override map; v1 and v2 measured `oq4` live in all five runtimes on both hero models | **unprobed** |
| `optiq` in `omlx` | loads | the 0.6.4 bundle carries the OptiQ paths (`_resolve_optiq_vision_sidecar`, `model_discovery.py` OptiQ special-casing, `mlx_lm_extra_tensors.mtp_file`) and the card says "load it with mlx-lm and use it as usual" (`2026-09-15-format-matrix-and-tooling.md` §Q2) | **unprobed** |
| `optiq` in `vmlx` | **refused?** | vMLX refused the *dense* `Qwen3.5-4B-OptiQ-4bit` in 9.2 s — `Missing 297 parameters: vision_tower.…` — because its per-layer map named no `vision_tower` entry; it loaded the *text-only* MoE OptiQ in the same campaign. **This model is multimodal in all four artifacts (see §3.3), so the dense refusal's precondition is present here and the MoE precedent does not clear it.** | **unprobed, hazard named** |
| `optiq` in `mlxlm`, `optiq`, `osaurus` | ? | mlx-lm/oMLX/Osaurus loaded the dense OptiQ that vMLX refused | **unprobed** |
| `jangtq4` in `vmlx` | loads | vMLX is the runtime JANG is built for; the JANGTQ model card requires "our custom loader" and states the models "are meant to be run in vMLX"; the bundle declares `weight_format: "mxtq"` (verified today) | **unprobed** |
| `jangtq4` in `osaurus` | loads | Osaurus ships JANGTQ4 models in its own library — the host's plist already carries `model_options_OsaurusAI/Holo3-35B-A3B-JANGTQ4` — so the engine reads this format | **unprobed** |
| `jangtq4` in `mlxlm`, `omlx`, `optiq` | **refused** | v1 measured three independent refusals with three different shapes on JANG: a shape mismatch at load (mlx-lm), HTTP 409 at request time (oMLX), and a hang (mlx-optiq). For JANGTQ specifically the refusal is source-backed rather than observed: the model card states stock `mlx_lm.load()` cannot parse `.tq_packed` tensors, and **no released oMLX contains a JANG engine** — three PRs open and unmerged, no `jang.py` at four sampled tags, no JANG string in the installed 0.6.4 bundle (`2026-09-15-format-matrix-and-tooling.md` §Q2) | **source-backed negative; not re-probed** |

**The three JANG refusals are the only negative claims in this table, and each one is backed by
a source read or a prior live refusal rather than by the absence of a flag.** Everything marked
`unprobed` is exactly that: a cell that runs in the probe, or does not, and the run's record is
where the answer lives.

### 3.3 The vision-tower hazard — the one thing this study found while designing itself

Read from the four weight maps today: **all four artifacts carry 333 `vision_tower.*` tensors,
and all four per-layer quantization maps contain zero `vision_tower` entries** (80, 512, 306 and
312 override entries respectively, every one under `language_model`). All four `config.json`
files declare a `vision_config` (27-layer ViT, hidden 1152, `out_hidden_size` 2048), and all four
repos carry `image-text-to-text` as their pipeline tag.

That combination — multimodal checkpoint plus a sparse override map that names no vision tensor —
is **byte-for-byte the shape of the dense `Qwen3.5-4B-OptiQ-4bit` refusal in vMLX**, where the
map had 249 entries and 0 of them were `vision_tower`, and vMLX built a vision tower, found no
map entry for its parameters, and reported 297 missing.

Two things this does **not** establish, both important:

- It is **not a prediction that vMLX refuses these cells.** The dense OptiQ artifact was refused
  by vMLX alone; mlx-lm, oMLX and Osaurus loaded the same file. A sparse map plus a vision tower
  is a precondition, not a cause, and nothing here shows what vMLX does with *these* maps.
- It is **not OptiQ-specific here.** In v1 the hazard bounded one cell. Here it is present in all
  four artifacts, so the hazard covers every vMLX cell in this campaign, and the probe of §7.3 is
  the only thing that distinguishes them.

It is recorded because it changes what the probe is *for*: not "does the runtime load OptiQ" but
"does any runtime's multimodal path bind to these weights", which is a question about all twenty
cells rather than about one format.

### 3.4 Pinning discipline, per runtime

The start commands are fixed in `ohyesmlx/runtimes.py` and nothing in the campaign edits them.
For four of the five the flag tuple is byte-identical for every cell in a column — that is the
point, and it is what keeps a column single-variable. The pins that matter at 35 B, and why:

**`vmlx`** — the runtime whose real settings are 438 environment variables no start command
mentions.

| pin | value | what it would otherwise change |
|---|---|---|
| `--no-jit` | passed, always | `mx.compile` is auto-ON for JANG affine bundles when neither JIT flag is passed (`cli.py:2085-2159`). Without the pin the `jangtq4` cell would be the only compiled cell in its column. It is also the faster choice on this host: the vMLX JIT A/B measured a **−2.7% to −11.3%** decode penalty from `--enable-jit` on 4B/8B models (`2026-09-19-vmlx-jit-ab.md`) |
| `--disable-native-mtp` | passed, always | **all four of these artifacts declare `mtp_num_hidden_layers: 1`**, and OptiQ ships an MTP head as a 1.64 GB sidecar. vMLX turns MTP on by itself for a bundle carrying heads and re-tunes depth mid-request, so without this pin a cell could decode speculatively |
| `--disable-prefix-cache`, `--disable-block-disk-cache` | passed | the SSD L2 turns itself on when continuous batching and prefix caching are both active, persists under `~/.cache/vmlx-engine/block-cache/<model_hash>`, and survives restarts. A prefix hit is invisible to `Observation` (no `cached_tokens`) and would publish as prefill throughput |
| `--stream-interval 1`, `--continuous-batching`, `--max-num-seqs 1` | passed | 8 is the default interval and batches tokens before the harness can count deltas; `--no-continuous-batching` silently forces the interval to 1, an interaction invisible in argv |
| `--kv-cache-quantization` | **omitted, and the omission is recorded** | omitting selects production auto mode; *passing* it disables loader-level TurboQuant. Neither choice is neutral |

**`mlxlm` / `optiq`** — `--prompt-cache-size 0` (the `cache_state: "off"` pin). `optiq serve`
additionally pins `--max-context off` (an integer cap installs a `RotatingKVCache` that silently
rotates a longer prompt instead of refusing it), `--no-stream-experts`, `--max-concurrent 1`,
`--idle-timeout 0`, `--context-scale 1.0`, `--no-auth`.

`--no-stream-experts` deserves its own line at this scale, because it is the pin whose premise
is *nearly* true here: OptiQ turns expert streaming on by itself when `model_disk_bytes >
0.70 × total_RAM`, and this machine's threshold is 0.70 × 64 GiB = **44.8 GiB**. The largest
artifact in this study is 22.998 GiB — 51% of the threshold — so **auto would not fire for any
cell here**, and the pin is what makes that a fact rather than an inference. Where streaming
becomes the variable is Plan 03-03, under a different memory regime; it is not a variable of this
study, and this study's cells are the "off" baseline that plan will need.

**`omlx`** — a per-run model catalog holding a symlink to exactly one artifact (`--model-dir`),
a per-run base path, `--max-concurrent-requests 1`, `--memory-guard off`, `--no-cache`, and a
loopback-only API key that **must be sent on every measured request** or every cell 401s.

**`osaurus`** — no flags at all. Its conditions are the host settings of §3.5 confound 5/6 and
the runner's backup-pin-restore, not this study's to invent.

### 3.5 The confound ledger

Every confound this study knows about, what it would fake, the pin that answers it, and the
evidence a reader can check afterwards. A confound with no pin is listed as unpinned — that is
what makes the ledger honest.

| # | confound | what it would fake | the pin | evidence left behind |
|---|---|---|---|---|
| 1 | **Bit width and bytes read** — the four artifacts store the routed path at 4 bits and the rest at 8, by different recipes | "this format decodes faster" when one artifact simply reads fewer bytes | no pin equalizes them; every rate is published beside the measured `disk_bytes` and the artifact's own override map (§2.2) | `disk_bytes` per cell; the override tables in §2.2 |
| 2 | **Vision-tower load path** (§3.3) | "vMLX cannot load OptiQ" when the runtime's multimodal path bound to *every* artifact's vision tensors | none available; the probe settles it per cell | the probe record's per-cell verdict and the loader log |
| 3 | **MTP heads** — all four declare `mtp_num_hidden_layers: 1`; OptiQ ships one as a 1.64 GB sidecar | "this format decodes faster" when one cell ran speculative decoding | `--disable-native-mtp` in every vMLX start command | vMLX's log line `MLLM native MTP skipped for request=…: disabled by VMLX_NATIVE_MTP=0/--disable-native-mtp` present on every request |
| 4 | **Auto-JIT on affine bundles** (#3's sibling) | "the JANG cell is faster" when it was the only compiled cell | `--no-jit` in every vMLX start command | the loader's `JIT: mx.compile applied successfully — running warmup pass` line must be **absent** in every vMLX log |
| 5 | **Osaurus host settings** — caching, KV size, tied-head codec, MTP mode, threads and memory guards all live in `~/.osaurus/config` and none is in a start command | an Osaurus number becoming unattributable the moment a setting moved between cells | `--cache-state off` (refused by `Osaurus.cache_state_refusal` unless the host already agrees), the drift guard, byte-exact backup/restore, and `shasum -a 256` of both files before and after every Osaurus cell | `config/osaurus-settings-baseline.json` drift **NONE** before every Osaurus cell; the digests in the runner log — the drift guard watches 23 keys, the digests watch all of them |
| 6 | **Idle residency** — `modelIdleResidencyPolicy.seconds` unloads the model mid-window, and a 35 B reload is minutes | a cell measured on a half-evicted model, or a cooldown that becomes a reload | pinned to **900 s** for every Osaurus run and restored after (the host's own 30 unloads inside the 30 s cooldown) | runner log line `osaurus idle residency pinned to 900 s`; restore verified with `cmp -s`, never with the drift guard |
| 7 | **Prefix/KV cache on a hybrid model** — Qwen3.6 is hybrid (`cache_type: "hybrid"` in the JANG sidecar, `full_attention_interval: 4` in all four configs), and hybrids behave differently from the dense models v1's cache sweep used | the prefill column measuring a cache lookup in one runtime and a full prefill in another — a 1,309-token prompt makes that difference large | `--cache-state off` on **every** run of this study, all five runtimes, with the Osaurus host precondition | the header pin `cache_state: "off"`; vMLX/optiq/mlx-lm start commands carry their disable flags; Osaurus's host files were toggled and restored |
| 8 | **Warmup** — one budget applied to five runtimes ranks them by how fast they warm (v1's runtime-axis defect) | a runtime's warmup read as its serving speed | the plateau rule, measured per cell: two windows of 5 rates, medians compared at 3%, floor 10, cap 20 | `warmup_count` per cell; `warmup_plateau: false` where a window hit the cap |
| 9 | **Thermal drift, amplified at 35 B** — every request runs a laptop chassis already hot from the previous one | a thermal curve wearing an artifact's name | `visit_plan`'s two visits in opposite orders, a 30 s cooldown, and the reversed column order between primary and replicate (§2.5) | `drift` per cell; annotation at ±5% |
| 10 | **Cross-runtime load and memory** — `cold_load_s` is a time-to-listening for a lazy loader, and `footprint` counts different page classes per runtime | a load or memory "ranking" between runtimes | none: the metrics are not comparable across runtimes. Use `cold_load_s + first_request_s` for load; publish no cross-runtime memory ordering | `report.CROSS_RUNTIME_UNCOMPARABLE` prints its reason above any runtime-axis ordering by either. **Format-axis orderings within one column are unaffected, and those are what H2/H3/H4 publish** |
| 11 | **Runtime version** — Osaurus moved 0.25.3 → 0.25.9 across the documents this study cites | a version step read as a format effect (1.15×, measured on exactly such a step) | `runtime_version` recorded per cell; all runs of a campaign checked to one version before joining | the grid's provenance block names each column's version; join guard 4 enforces it |
| 12 | **Disk contention from the fetch** | a cold load timed while 86 GB was still arriving | the fetch finishes before the first cell; `AGENTS.md`'s standing rule | the fetch log's `FETCHDONE` timestamp precedes the first run directory's mtime |
| 13 | **Tokenizer availability** | a cell measured with a substitute tokenizer, or a rate derived from a count nothing validated | `TokenCounter(cell.artifact_dir)`; an artifact without a tokenizer makes the cell **N/A** with the reason, before the runtime starts | the cell's `token_source` field, and `N/A` rows where a tokenizer could not be built |
| 14 | **A 35 B reload inside a cooldown** | a "lost visit" that was really a timeout, or a cell measured while a previous process still held 20 GiB | `run_cells` stops the previous runtime and confirms its port is free before starting the next; one runtime holds weights at a time | `lost_visit_reason` on the row, `cold_load_after_lost_visit` where a start followed a lost visit |

### 3.6 The pins the join guard cannot see

The one structural gap this study must work around, stated plainly because it is the same gap the
v2 design recorded and nothing has changed: **`results.jsonl` does not record the start-command
flags.** Its header carries `temperature`, `seed`, `warmup`, `measured`, `concurrency`,
`prompt_tokens`, `cache_state`, `cooldown_s` and the workloads. A flag tuple that changed between
two runs is invisible to join guard 1, so two runs differing in `--no-jit` would join without a
word.

The answers, in order of strength:

1. **One flag tuple per campaign.** The tuples above are frozen before the first column and are
   not edited until Phase 1 closes. That is a process pin, recorded in the campaign's runner
   script — a file under version control, which is the only place it can be recorded today.
2. **Per-run log evidence.** The loader's own lines are the witness (§3.5 rows 3, 4, the
   TurboQuant line, and the runtime's load line), kept per run beside the record.
3. **Never join across arms.** If a future arm changes the tuple — the deferred MTP A/B, or
   Plan 03-03's `--stream-experts` regime — it gets its own run directory *and* its own write-up,
   and it is never added to a grid invocation containing a cell from another arm. The tool cannot
   refuse it; the procedure must.

---

## 4. The coherence gate and the floors

### 4.1 The gate

Every measured response on every cell is judged by `ohyesmlx/coherence.py`, and more than half of
a cell's judged responses failing makes the cell a **FAIL** with the first failing reason and the
sample itself still on the record:

```
SCRIPT_MAJORITY = 0.75   # a clear majority of alphabetic characters in one script
MIN_SCRIPTED   = 16      # below this, a majority of a few letters says nothing
WORD_FLOOR     = 0.5     # at least half the whitespace tokens have to look like words
failures * 2 > judged    # the cell-level rule
```

Four checks, in order, the first failure naming the reason: no content, replacement characters, no
majority script, implausible words. `"incoherent output: <reason>"` is the whole of what a reader
sees, and the offending text is preserved rather than truncated.

The gate reads **content, or reasoning when a response emitted no content at all**. That is not a
generosity — it is the shape this campaign runs into. mlx-lm 0.31.3 and vMLX 1.6.59 answer
entirely in the reasoning channel on a thinking model (`docs/interfaces.md`, "Which channel is the
output stream"), and both are runtimes in this matrix. A response with nothing in *either*
channel is `STILL_THINKING` and is its own verdict — no output is not bad output, and it is not
garbage either.

### 4.2 Why it is load-bearing for this study specifically

The founding incident is this exact architecture:

> Stock `mlx_lm.server` loaded `Jundot/Qwen3.6-35B-A3B-oQ4-mtp` — a 256-expert MoE, 21.6 GB — in
> about four seconds, returned HTTP 200, generated 64/64 tokens at full throughput, and produced
> mixed-script token salad with replacement characters. Nothing raised. Nothing timed out.
> — `2026-09-14-oq-portability-spike.md`

The preserved sample, from the Phase 4 run:

```
oughwet. �ت .10. A of  �cho6...不会GV作者 conclusion }s leteton324 thouch� galinging on2 As高薪 �生活11
```

A speed-only harness records that as its healthiest row — it was the *fastest* thing measured that
day. Phase 4 then established the failure is **runtime-specific, not format-specific**: oMLX 0.6.4
answered the same bytes coherently, and its answer was relevant and correct
(`2026-09-15-phase4-256-expert.md`). That is why this study spends five runtimes on this family
instead of assuming the defect belongs to the artifact.

Three consequences the plan is built on:

1. **The four `mlxlm` cells are the closest thing this study has to a pre-registered
   reproduction.** The v1 failure was on `Jundot/Qwen3.6-35B-A3B-oQ4-mtp`; this study's `oq4` cell
   is a different revision of the same architecture from the same author. A reproduction is a
   prediction here, not a certainty — and if it reproduces, it publishes as `FAIL` with the
   sample, exactly as the rule has required since Phase 2.
2. **The gate is a floor, not an eval.** It says "this is language", never "this is right", and
   `coherence.py`'s own docstring is explicit that an alphabetic, Latin-dominant salad with no
   replacement character can pass all three checks. It is the cheap net under the sharp checks.
   Accuracy is Track 2's and is not re-opened here.
3. **A cell that fails the gate is not a slow cell; it is a failed cell.** No tok/s, no TTFT, no
   ITL, no throughput figure is read from it — the row carries `FAIL` and the reason, and the
   number column stays empty. At 35 B the temptation is larger than usual, because a run that
   took an hour feels like it should produce a number.

### 4.3 The floors

A cell is ranked only after it clears every floor, and floors are pass/fail, never weighted:

1. **Coherence** — §4.1.
2. **Every published metric present** — already enforced by `_set_status`. A metric with no domain
   on a stream (fewer than two content deltas, no reconcilable token count) renders `no value`,
   never `0`.
3. **Fits** — `peak_mb` did not exceed available unified memory. At 35 B this floor is the one
   that can actually fail a cell that produced perfect language, and a cell that swaps is not a
   slower cell, it is a void measurement: the harness cannot detect swap, so the floor is the
   guard and the drift annotation is the alarm.

Ranking then uses **one named metric**, chosen by the caller and printed in the table header —
never a blended score. Weighting a second of latency against a megabyte has no objective answer,
and a single number would encode an arbitrary trade-off as though it were measured.
`report.render_markdown` prints the metric card behind every ordering, so an ordering can always
be checked against the numbers that produced it.

### 4.4 What a FAIL publishes, and the four entry states

| state | renders | means |
|---|---|---|
| measured, PASS | the number | a result |
| PASS, no value for *this* metric | `no value` | cleared every floor; the metric has no domain on this stream |
| measured, not PASS | `FAIL` | ran and did not clear a floor — the reason and the sample are on the record |
| never measured | `—` | that combination does not exist: the probe said it does not load, or it was never attempted |

The distinction between the last two is the whole reason the grid has four states. At 35 B the
`—` column will be wide — three runtimes cannot load JANG — and a reader who cannot tell `—` from
`FAIL` is reading a different matrix from the one this study produces.

---

## 5. Pre-registered hypotheses

Written before the data exists, so that the write-up cannot choose its story afterwards. Each
hypothesis names the measured quantity, the decision rule, the condition that would refute it, and
what a confirmation does **not** buy. Rates are per workload and never pooled; `tie` means the
gap sits inside the pre-registered 2.5% band of §2.5.

### 5.1 H1 — decode is set by the bytes read per token, not by the parameters stored

**Statement.** At 256 experts with 8 routed per token, a decoded token reads ~1.98 GB of weights
(§1.3) against a 35.95 B-parameter model. Decode rate should therefore track the bytes the routed
path actually reads, and this architecture should decode far above what its total size suggests.

**Measured quantity.** `decode_tps` per cell, on the `decode` workload, per runtime column, read
against `disk_bytes` and against the artifact's own routing bit plan (§2.2).

**Prediction.** Within a column, the four artifacts order by the bytes their routed path reads —
and the routed path is the same 4-bit global rule in all four (§2.2), so the ordering is set by
how densely each recipe packs those bytes. On §2.2's two measurements that predicts `jangtq4`
first: it is the smallest artifact while carrying the *most* 8-bit overrides, which means its
4-bit routed storage is the densest of the four. It also predicts `stock4bit` reading less per
token than `optiq` and `oq4`, since it alone leaves the shared expert, attention and embeddings at
4 bits — so an ordering that simply tracks `disk_bytes` is **not** what H1 predicts, and would be
evidence against it. Second half: the 35 B cell lands in the same order of magnitude as the
sub-10 B MoE already measured on the same runtime, not at a quarter of it. The v1 MoE grid's
`stock4bit` decode figures (133.3 tok/s on vMLX, and its siblings in `2026-09-16-moe-format-axis.md`)
are the named reference point, quoted with their run directory.

**Falsifier.** A decode ordering that mirrors total artifact size — the largest reading slowest,
the smallest fastest, for no reason beyond the file — or a 35 B decode rate at roughly a quarter
of the 8B-A1B rate on the same runtime. Either would say decode at this scale is not the
bandwidth story §1.3's arithmetic implies, and the second would be a finding about the access
pattern rather than a failed prediction.

**What confirmation does not buy.** Any claim about *why*. H1 can say the rate is consistent with
routing-bound traffic. It cannot separate kernel quality from expert-locality from the fact that
1.007 B parameters spread over 256 experts make for a scattered read — the four artifacts also
differ in bit assignment, override coverage and packing, and no artifact pair here isolates one
of those (confound 1).

### 5.2 H2 — OptiQ is Pareto-dominated at 35 B

**Statement.** OptiQ's 4-bit conversion buys its mixed precision at both ends: it is the largest
artifact on disk and, in v2, it lost on both coordinates that matter. The v2 accuracy studies
eliminated it twice over — strictly Pareto-dominated on dense (−3.1 to −4.4 pp MMLU *and* +28%
disk, `2026-09-18-accuracy-dense.md`) and again on MoE (−7.3 pp MMLU, +14–78% disk,
`2026-09-19-accuracy-moe.md`) — and v1's format axis never once saw it win a decode ordering.

**Measured quantity.** `decode_tps` (speed), `disk_bytes` (disk), `peak_mb` (memory), all three
within one runtime column, where memory *is* comparable.

**Prediction.** At 35 B, OptiQ is the largest artifact (22.998 GiB against `jangtq4`'s 18.354),
does not lead `decode_tps` in any column, and does not lead `peak_mb` in any column. It is
therefore dominated on all three coordinates, and the recommendation is not to spend the
difference — 3.972 GiB over `stock4bit`, 4.644 GiB over `jangtq4` — on it. The interesting form
of this hypothesis at this scale is that a *compositional* failure is what would break it: if
OptiQ's 394 eight-bit overrides land on the tensors that matter most for a routed MoE and its
taller precision wins decode outright.

**Falsifier.** OptiQ leading `decode_tps` outside the tie band in a column while not leading
`peak_mb`, or leading both. Either makes it a Pareto candidate at this scale and would show the
v2 elimination is model-class-specific rather than a property of the recipe.

**What confirmation does not buy.** Any quality statement. This study measures speed, memory and
disk only. The accuracy coordinates exist for the 4B and 8B models and do **not** transfer: a
Pareto frontier drawn here has no accuracy axis, and the write-up must say so beside any
recommendation rather than borrowing v2's.

### 5.3 H3 — JANG's density lead survives at 35 B; its throughput lead does not

**Statement.** v2 established the JANG Duality: on **dense** models JANG led decode at near-equal
precision (+13.9%/+16.8% in vMLX, +9.5%/+9.0% in Osaurus on `Qwen3.5-4B`), and on **MoE** the lead
did not transfer — JANG_2L tied `stock4bit` in vMLX (+0.87%/−0.50%) and lost in Osaurus
(−5.12%/−9.80%) while delivering 36% disk savings and 16–31% memory reduction
(`2026-09-17-jang-cross-runtime.md`). `Qwen3.6-35B-A3B` is MoE *and* hybrid, so the duality's MoE
half is the prediction.

**Measured quantity.** `decode_tps`, `disk_bytes`, and `peak_mb`, in the `vmlx` and `osaurus`
columns — the only two columns that can carry it, and only if the probe clears both JANG and at
least one portable there.

**Prediction.** `jangtq4` is the smallest artifact (18.354 GiB, **3.5% below** `stock4bit`'s
19.026 — a far narrower disk gap than the 36% JANG_2L held against the portables on
`LFM2.5-8B-A1B`, so H3's density half is a much weaker prediction here than it was in v2, and a
`peak_mb` lead is expected to be correspondingly small) and delivers the lowest `peak_mb` in both
columns that carry it, while **not** leading `decode_tps` outside the tie band — the density win
without the throughput win, which is the duality's MoE half repeating on a model with 4.5× the
total parameters of the one it was measured on.

**Falsifier.** `jangtq4` leading `decode_tps` outside the tie band in both runtimes, which would
say the MoE narrowing was an artifact of the 8B class and the duality needs restating; or losing
on density, which would contradict the artifact's own bit plan.

**Two limits that ride on this and are printed beside it.**

- **Loader and runtime are not separable in the JANG row.** JANG loads in exactly two runtimes and
  both differ in loader, scheduler, Metal usage and memory accounting at once. `jangtq4__vmlx` vs
  `jangtq4__osaurus` establishes *that* the two implementations differ and by how much on
  identical bytes; it cannot say which internal does it.
- **If the probe clears JANG in only one of the two runtimes, H3 is a single-runtime reading** and
  is published as one, with the absent column named — not quietly promoted to a two-runtime
  result. `cold_load_s` and `peak_mb` are also not read *across* that row for the reasons in
  confound 10; the density claim is a within-column claim in each of `vmlx` and `osaurus`.

### 5.4 H4 — peak footprint is a per-runtime accounting, and at 35 B the weights stop being a rounding error

**Statement.** Phase 5 measured that `peak_mb` is not one quantity across runtimes: four columns
land within a few percent of their weight bytes and Osaurus reports roughly half of its
(`2026-09-16-footprint-is-not-one-quantity.md`). That was measured on a 4.5 GiB artifact. At
35 B, if the gap between a runtime's reported footprint and its weight bytes is a roughly
*constant* accounting artifact, the models should look nearly identical relative to their weights
— the difference becomes a smaller share of a larger number. If it is *proportional*, the runtime
gap widens with the model.

**Measured quantity.** `peak_mb` and `disk_bytes` per cell, and the ratio `peak_mb / disk_bytes`
per runtime, compared between this campaign and the v1 columns at 4.5 GiB
(`2026-09-16-phase5-joined-grid.md`).

**Prediction.** Within a column, `peak_mb` orders the artifacts the way `disk_bytes` does — at
this size the weights dominate everything a runtime adds — while across rows the footprint-to-
weights ratio stays a property of the runtime, and Osaurus's stays well below the other four.

**Falsifier.** A within-column `peak_mb` ordering that inverts the byte ordering (a runtime
holding more than its weights predict for the smaller artifact — for instance if a paging or
expert-spilling path keeps host-side copies), or a cross-runtime ratio that converges at 35 B.

**What confirmation does not buy.** A cross-runtime memory ranking. The ratio either stays a
per-runtime property (the prediction) or moves with scale (the falsifier); neither outcome makes
`peak_mb` one comparable quantity, and the renderer prints `CROSS_RUNTIME_UNCOMPARABLE` above any
runtime-axis ordering by it regardless.

### 5.5 The rules that apply to every reading above

- **No rate is published from a cell that did not produce language** (§4.1).
- **No ordering where the gap is inside 2.5%** without the word *tie* beside it (§2.5).
- **No number attributed to "the format"** — the attributable unit is the *artifact* (these bytes,
  at this revision) measured in *this runtime at this version*.
- **Drift annotates, never fails** at `DRIFT_ANNOTATION_PCT = 5.0`; a positive drift means the
  window closed while the cell was still warming, and it is printed rather than smoothed.
- **A short window is annotated, never dropped** (`(n=K of N)`), and a lost visit keeps its reason
  on the row.
- **A run is discarded only for a stated defect in its conditions**, never for its number, and the
  discarded directory is kept and named with the reason.
- **Figures are never averaged across workloads.** `chat`, `prefill` and `decode` are three
  corners and can have three different winners.

---

## 6. Workloads and pins

### 6.1 The three shapes

Pinned in `cli.py`, unchanged from v1, one table per shape, never averaged into each other:

| id | prompt | `max_tokens` | what it exposes |
|---|---|---|---|
| `chat` | `PROMPT` (**24 tokens**) | 128 | per-request latency and fixed overhead |
| `prefill` | `PREFILL_PROMPT` (**1,309 tokens**, the MS-7 excerpt) | 64 | prompt-processing throughput |
| `decode` | the same `PROMPT` as `chat` | 512 | sustained generation and memory growth |

**Both counts were taken today, not estimated**, with `TokenCounter` over this model's own
tokenizer — `tokenizer.json` from the local `optiq` artifact. That matters because `cli.py`'s own
comment describes the prefill prompt as "6,485 characters, roughly 1,600 tokens at four characters
per token", and this tokenizer counts **1,309** — the chars/4 heuristic overstates by 19% on this
text. The same heuristic is a known defect in the other direction on Osaurus, whose
`usage.prompt_tokens` is chars/4 and understates a prefill by ~20%
(`2026-09-16-prompt-length-sweep.md`). Neither figure enters a published metric here —
`prefill_tps` divides the runtime's own `prompt_tokens`, and `--prompt-tokens` is not used by this
study — but the study's own KV arithmetic (§1.2) uses the real count, and the divergence is
recorded so nobody re-derives it from the comment.

One caveat on the count, since the harness builds a `TokenCounter` per artifact: all four declare
`vocab_size: 248320`, but their `tokenizer.json` files are **not byte-identical** — 19,989,343 B
in `stock4bit` and `optiq`, 12,807,982 B in `oq4` and `jangtq4`. The count above is the `optiq`
tokenizer's. Nothing in this study compares tokenizer counts across artifacts (it would refuse the
run if they disagreed), so the difference is recorded and not explained; if a cell's
`token_source` ever lands on `local_tokenizer` rather than `usage`, the artifact that served it is
named on the row.

`chat` and `decode` send the same prompt and differ only in the cap, which is the point: the
difference between them is the cost of generating 512 tokens rather than 128 against an identical
prefix. At 35 B the `prefill` shape is the one worth watching: a 1,309-token prompt is where a
hybrid model's cache behaviour and a routed MoE's prompt processing both show up, and it is the
only shape whose KV state (26.8 MiB, §1.2) is measurable against the noise.

**Every cell runs every workload**, and a cell's result is per `(cell, workload)`.

### 6.2 The pins

| pin | value | where it comes from |
|---|---|---|
| `temperature` | `0.0` | `measure.TEMPERATURE` |
| `seed` | `0` | `measure.SEED` |
| `concurrency` | `1` | this study is sequential; concurrency is a sweep pin, not an artifact variable |
| `warmup` | `{"mode": "plateau", "window": 5, "floor": 10, "cap": 20, "plateau_pct": 3.0}` | the plateau rule: two windows of five rates, medians compared at 3% |
| `measured` | `9` **batches** | at `concurrency` 1 a batch is one request |
| `cooldown_s` | `30.0` | between visits |
| `prompt_tokens` | `null` | the three pinned workloads send their own literals |
| `cache_state` | `"off"` | every run, all five runtimes (confound 7) |

Three of these are worth a sentence. **`measured: 9` is not negotiable downward** — at 5,
`measured_drift` compares a median of two against a median of two and throws the middle sample
away, and at 35 B a cell's window is expensive enough that the temptation is real. **`cache_state:
"off"` is a departure from v1's grid runs**, which carried no cache pin at all; its consequence is
stated rather than discovered — the Osaurus column requires the host toggled and restored, and
these runs carry a pin that v1's do not. **The plateau warmup is what makes a 35 B campaign
affordable**: a fixed budget large enough for mlx-lm would spend it on four runtimes that do not
need it, and the measured rule publishes `warmup_count` per cell so the budget each runtime needed
becomes a number rather than a constant in a source file.

### 6.3 Visits, ordering, cooldown

Each cell is visited **twice** (`VISIT_ROUNDS = 2`), the nine measured batches splitting 5 and 4,
with the second visit walking the cell list in reverse. A 30 s cooldown separates visits that
sampled anything. Cell order is **interleaved, never config order** — otherwise a thermal curve
aliases perfectly onto artifact identity, and at 35 B sustained inference in a laptop chassis that
aliasing is not hypothetical (`AGENTS.md`, "Thermal"). Persist after every cell, so a campaign
that dies at hour three keeps the cells it finished.

### 6.4 Memory and load

- **Memory** is Apple's `phys_footprint` read from `/usr/bin/footprint -p <pid>` once a second
  across each workload's window; the published `peak_mb` is the higher of the cell's two visits.
  Never `ps` RSS: Metal buffers, mmap'd weights and wired GPU memory account inconsistently under
  MLX, and two runtimes' weights land in different page classes outright (confound 10).
- **Load** is two numbers, never one: `cold_load_s` (spawn → ready) and `first_request_s` (the
  cold visit's first warmup latency, where a lazy loader pays for its weights), with
  `first_request_workload_id` naming which shape made that request. Any cross-runtime load
  comparison uses the **sum**; within a column it stays whatever it is, identically for every
  cell. **At 35 B this pair is the most expensive thing the campaign pays** and the number most
  likely to be read carelessly: a cold load is minutes here, not seconds, and a runtime that
  defers the read past readiness will hide it in request #1.
- **Disk** is `disk_bytes` per cell, sidecar files included (§2.2 — which is why the OptiQ figure
  is 22.998 GiB and not 20.63).

---

## 7. Execution protocol and next steps

### 7.1 Preconditions

- **Artifacts**: §2.2 verified today — the four revisions named, 80.053 GiB, one of them
  (`optiq`) already byte-complete on this host in flat layout.
- **Disk**: 186 GiB free. The fetch needs 80.1 GiB, or ~57 GiB if the existing OptiQ copy is used
  in place of a second download.
- **Harness**: **no code change is required.** The study runs on today's
  `ohyesmlx run --study format --cache-state off`, `ohyesmlx grid`, and the existing plateau
  warmup. The runners are new scripts modelled on `scripts/run_grid_moe.sh`; the flag tuples of
  §3.4 are exactly as `runtimes.py` already has them.
- **Host**: quiet machine, five ports free (8081 / 1337 / 8100 / 8080 / 8000), no download and no
  test suite running once a cell is being measured.
- **`PATH`**: `~/.local/share/ohyesmlx/mlx-lm-0.31.3/bin` on `PATH`, or every `mlxlm` cell fails
  to start in a way that looks exactly like an unsupported `model_type`.
- **Osaurus**: settings backed up byte-exact, `cache.prefix.enabled` off, residency pinned to
  900 s, baseline re-recorded so the harness's own gate passes, drift **NONE** before the first
  Osaurus cell.
- **Tokenizer wheel**: `tokenizers` present in the run venv, or every cell is `N/A` — that
  environmental defect cost a run in Phase 4.

### 7.2 Step 1 — fetch

```
scripts/fetch_35b.sh            # ~80 GiB, four repos, logs a timestamp per repo
tail -f <script output>         # waits for FETCHDONE
```

Nothing else runs on the machine while this is in flight. If the existing flat-layout OptiQ copy
is used in place of a second download, the cell's `artifact_dir` points at
`~/.cache/huggingface/hub/mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit/`, which is byte-complete
against revision `70a3aa32…`; the script's header says so.

### 7.3 Step 2 — the loadability and coherence probe

**This is the gate for everything in §3.2, and it is not optional.** The probe is one short
request per cell — load, one `max_tokens=24` completion, coherence checked, stop — recorded
verbatim so that a hole in the matrix is evidence rather than absence. It follows
`scripts/probe_grid_moe.py`, with three changes this model forces:

1. **Do not lower `READY_TIMEOUT_S` to the probe's usual 180 s.** That value was calibrated on the
   2.85–5.10 GiB artifacts of the two hero models, and these are 18.35–23.00 GiB: 3.6× to 8.1×
   larger. A cold read must not be given a timeout tuned for a smaller artifact. Keep the 900 s
   default.
2. **Probe all twenty cells, including every cell §3.2 predicts will refuse.** v1's lesson is
   explicit: every predicted refusal was wrong and the one real refusal was not predicted. A
   predicted refusal is probed too, and the record says what actually happened.
3. **Read the verdict, not the exit code.** A cell that fails the gate is recorded `FAIL` with its
   sample; a cell that fails to load is recorded with the runtime's own error text, verbatim.

Output: a per-cell verdict table. **Only cells with a live verdict enter a column** (§2.4), and a
refusal is `—` with its reason in the write-up, never a synthetic `FAIL`.

### 7.4 Step 3 — the grid

One invocation per runtime, `--study format` holding the runtime constant, one run directory per
column, into `results/grid-35b/`:

```
ohyesmlx run --study format --cache-state off \
  --cells "stock4bit__mlxlm=<art>,oq4__mlxlm=<art>,optiq__mlxlm=<art>" \
  --results-dir results/grid-35b
```

with `<art>` resolved per cell from the hub snapshot directories, exactly as
`scripts/gridspec-moe.sh` resolves them. Then:

```
ohyesmlx grid results/grid-35b/*/ --out results/grid-35b/grid.md
```

explicit directories, never a wildcard over a directory that holds more than this campaign
(`docs/interfaces.md`; `results/grid/` already holds thirteen run directories from three
sessions). The join's provenance block is the evidence that the columns share their pins.

**Order**: the columns run back to back, and the replicate runs of §2.5 reverse the column order
against the primary. A session-long thermal or load trend must not be able to wear an artifact's
name.

### 7.5 Step 4 — the report

`docs/research/<date>-35b-moe-serving.md`, carrying: the four artifacts and their revisions; the
five runtime versions; the probe table including the cells that did not run; one grid per
workload; the four hypotheses with their decision rules applied; and a confound table where every
entry is either pinned or declared unpinned. The recommendation, if any, names the whole cell —
artifact, revision, runtime, version, workload — and carries §8's limits beside it.

### 7.6 Cost expectation, and why it cannot be derived here

The v2 design could derive its cost from v1 (60 rows in 2 h 28 m on dense, 1 h 24 m on MoE) because
comparable cells had been measured. **Nothing comparable has been measured here**, and saying so
is more useful than inventing a number:

- **No 35 B cell has ever published a passing figure.** Phase 4 ran two cells on this architecture
  and both were `FAIL` — mlx-lm for incoherence, oMLX for token accounting — so this project owns
  *no* 35 B tok/s, TTFT or load time to extrapolate from.
- **Two terms dominate and neither is derivable from a smaller model.** Cold load scales with the
  bytes read (20 GiB against 3 GiB, 6.7×) and every runtime pays it once per visit, twice per cell;
  and the plateau warmup spends **at least 10 requests per workload per visit** — 60 requests
  minimum per cell before the nine measured batches, each of them a full 35 B forward pass.
- **The first cell is therefore the calibration.** Run one cell, read its wall clock, and size the
  rest from that measurement rather than from an estimate. If the campaign has to fit a window,
  the thing to cut is the number of columns attempted in one session — never `measured` (§6.2).

### 7.7 Out of scope for Phase 1

- **Expert streaming / paging under memory pressure.** Plan 03-03's question. The largest artifact
  here is 51% of the `--stream-experts auto` threshold (§3.4), so no cell of this study exercises
  the regime, and pretending otherwise would be measuring the wrong thing.
- **Cold vs warm page cache attribution.** Plan 03-02. This study pins its cache state (`off`) and
  reports `cold_load_s` and `first_request_s`; it does not manipulate the OS page cache.
- **MTP as a variable.** `--disable-native-mtp` is a pin (§3.4), so no cell here measures what the
  MTP head is worth.
- **Context length, multi-turn, KV quantization.** Phase 2's, and §1.2 is why: the pinned suite's
  whole KV state is under 27 MiB.
- **Accuracy.** The fourth coordinate does not exist for this model in this study. Nothing here
  speaks to quality, and no accuracy figure from a 4B or 8B model transfers to it.

---

## 8. What this study will not establish

- **Not a general ordering of the four formats.** One model, four artifacts, one 64 GiB M2 Max.
- **Not why**, beyond what §3.5's ledger can attribute. The artifacts differ in bit assignment,
  override coverage, sidecar contents, tensor packing and loader at once.
- **Not equal precision.** All four store the routed path at the same global 4-bit rule, and then
  differ about everything else (4 bits throughout for `stock4bit`, 8 bits on the shared expert,
  attention and embeddings for the other three, and different packing for `jangtq4`). No pair here
  is a precision control, and `stock4bit` and `jangtq4` — the closest pair on disk at 19.026 vs
  18.354 GiB — are the *least* alike in how those bytes are laid out.
- **Not the shipped experience of any vendor's headline path.** JIT and native MTP are pinned off
  on vMLX, expert streaming is pinned off on OptiQ, and cache reuse is off everywhere. Each is a
  deliberate pin; each means these numbers are a floor for the vendor's own configuration, not a
  replica of it.
- **Not a cross-runtime memory or load ranking** (§5.4, confound 10).
- **Not accuracy, and not a quality recommendation.** See §7.7.
- **Not a claim about other 35 B models, other expert counts, or other memory sizes.** The
  project's standing caveat still holds, inverted: the MoE hero model carried *32* experts while
  the failure was on *256*. This campaign measures 256, and it says nothing about the range
  between them.

## 9. Open questions

1. **Does the mlx-lm incoherence reproduce on this revision?** The v1 failure was
   `Jundot/Qwen3.6-35B-A3B-oQ4-mtp`; this study measures `Jundot/Qwen3.6-35B-A3B-oQ4` — same
   architecture, same author, different revision. If it reproduces, `mlxlm` loses three cells; if
   it does not, the defect was version- or artifact-specific and the 2026-09-14 finding needs its
   scope narrowed in the write-up.
2. **Is the vision-tower hazard (§3.3) real for vMLX on this model, and for how many of the four
   artifacts?** The v1 precedent is one dense artifact and one refusal; here the precondition is
   present four times.
3. **Does Osaurus register a hub-cache artifact it has never been told about?** Its dense
   stock-4bit refusal was a registration failure, not a load failure, and its library does not
   contain these four ids yet.
4. **What does the `optiq` artifact's 1.64 GB MTP sidecar do when it is not disabled?** Untested
   by design here. It is the second half of the deferred MTP arm.
5. **Does the 1.98 GB/token arithmetic in §1.3 survive contact with a measured rate?** Its use
   here is to fix H1's shape and to bound the probe's expectations. If the measured rate lands far
   below the bound in every cell and every runtime, the shortfall is a finding about memory
   traffic at 256 experts and belongs in the write-up, not in the appendix.

---

## Appendix A — record fields this study relies on

From `measure.py`'s record and `report.summarize`: `cell{id, runtime, artifact_dir, label}`,
`workload_id`, `status`, `reason`, `cold_load_s`, `first_request_s`,
`first_request_workload_id`, `memory{peak_mb, samples, …}`, `runtime_version`, `disk_bytes`,
`measured_count`, `warmup_count`, `warmup_plateau`, `drift`, `observations[]`,
`warmup_observations[]`, `batch_spans` (absent at `concurrency` 1), `lost_visit_reason` and
`cold_load_after_lost_visit` (present only when true), and the header pins of §6.2. Derived
figures are recomputed on read; the three the record stores (`measured_count`, `warmup_count`,
`drift`) are for a reader with `jq` and are not read back.

## Appendix B — evidence index

| what | where |
|---|---|
| the founding token-salad finding, and the artifact it was found on | `docs/research/2026-09-14-oq-portability-spike.md` |
| the 256-expert question answered: runtime-specific, not format-specific | `docs/research/2026-09-15-phase4-256-expert.md` |
| what `qwen3_5_moe` artifacts exist; oMLX has no JANG engine; cache clearing per runtime | `docs/research/2026-09-15-format-matrix-and-tooling.md` |
| the dense OptiQ vision-map refusal in vMLX, and Osaurus's not-registered stock-4bit | `docs/research/2026-09-15-grid-loadability-probe.md` |
| `footprint` is not one quantity across runtimes | `docs/research/2026-09-16-footprint-is-not-one-quantity.md` |
| the v1 grids, the tie band, and the warmup defect | `docs/research/2026-09-16-phase5-joined-grid.md`, `2026-09-16-moe-format-axis.md` |
| the cache-state pin and the hybrid cache behaviour | `docs/interfaces.md` ("Plan 06-02"), `docs/research/2026-09-17-cache-state-split-nonhybrid.md`, `2026-09-17-cache-state-split.md` |
| the JANG Duality, and the MoE half of it | `docs/research/2026-09-17-jang-cross-runtime.md`, `2026-09-17-moe-jang-study.md` |
| OptiQ eliminated on quality, twice | `docs/research/2026-09-18-accuracy-dense.md`, `2026-09-19-accuracy-moe.md` |
| the JIT decode penalty that justifies `--no-jit` | `docs/research/2026-09-19-vmlx-jit-ab.md` |
| the study design this one follows | `docs/research/2026-09-17-v2-track1-jang-study-design.md` |
| runtime start commands, pins, ports, readiness rules | `ohyesmlx/runtimes.py`, `docs/runtimes/{vmlx,osaurus,omlx}.md` |
| the gate, the floors, the workloads, the pins | `ohyesmlx/coherence.py`, `ohyesmlx/measure.py`, `ohyesmlx/cli.py`, `docs/interfaces.md` |
| the cell sets this campaign's shape is modelled on | `scripts/gridspec-moe.sh`, `scripts/run_grid_moe.sh`, `scripts/probe_grid_moe.py` |
| the four sizes, revisions, download counts and configs in §2 | HF API, `?blobs=true` and `/raw/main/config.json`, queried 2026-09-19 |
| the runtime versions in §3.1 | each runtime's own version probe, run 2026-09-19 |
