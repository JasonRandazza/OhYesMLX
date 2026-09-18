# v2 Track 1 — The JANG Study: design, single-variable test matrix, and measurement protocol

Date: 2026-09-17. **Design only.** Nothing in this document is measured: no runtime was started,
no model was loaded, no tensor was read. Every figure cited below is either recomputed from disk
today (Section 4, with the command that recomputes it) or quoted from a v1 document or run
record, and each one names its source. The numbers this study will produce do not exist yet.

Subject: the JANG quantization family (`JANG_4S`, `JANG_2L`, and the `JANGTQ` variants) on the
two runtimes that load it — vMLX 1.6.59 and Osaurus 0.25.x — against the portable formats those
same two runtimes already load. Ten artifacts, two models, zero downloads, one variable at a
time.

---

## 1. Executive summary and the problem statement

### 1.1 The question

JANG bundles are the fastest quantization family this project has seen on the models where it
can run at all. In the v1 grids they lead their own columns:

| grid | workload | JANG cell | its column's portable cells | source |
|---|---|---|---|---|
| dense, re-measured | decode | `jang4s__vmlx` **77.3** | stock4bit 75.6, oq4 73.3, oq4e 66.7 | `2026-09-16-phase5-joined-grid.md` |
| dense, re-measured | decode | `jang4s__osaurus` **69.5** | oq4 68.7, oq4e 64.7, optiq 63.5 | same |
| dense, re-measured | chat | `jang4s__osaurus` **77.8** | oq4 74.3, oq4e 71.5, optiq 70.1 | same |
| dense, re-measured | chat | `jang4s__vmlx` 76.9 | stock4bit **77.1**, oq4 74.4, oq4e 67.3 | same — a **tie**, 0.3% |
| MoE (plateau pins) | decode | `jang2l__osaurus` **147.1** | oq4 145.4, oq4e 142.5 | `2026-09-16-moe-format-axis.md` |
| MoE (plateau pins) | decode | `jang2l__vmlx` 122.2 | stock4bit **133.3**, oq4 120.9, oq4e 119.8 | same — mid-pack |

Four of those six readings are leads, one is a tie inside a band this project has already ruled
unresolvable, and one is mid-pack. That is the whole of the evidence, and it is four cells out of
the 120 the v1 grids measured, measured inside columns built to answer a different question.

So the study's question is narrow and it is worth stating exactly: **on one model at a time, in
one runtime at a time, what does the JANG bundle buy over the best portable format that runtime
loads — and does an answer bought in one runtime survive in the other?**

### 1.2 Why JANG was kept off the axis in v1

The founding decision, and the reason it held, is recorded in `.paul/STATE.md`:

> **JANG is a runtime+format bundle, not an axis point** | Phase 1 | No runtime loads JANG and the
> other formats both. Own study, after v1.

In v1 that was measured rather than assumed. Three independent runtimes reject `JANG_4S` with the
**byte-identical** error (`2026-09-15-grid-loadability-probe.md`):

```
ValueError: Expected shape (248320, 640) but received shape (248320, 320)
           for parameter language_model.model.embed_tokens.weight
```

`embed_tokens` is packed at half the width the stock model declares. The difference is not a
precision variant a generic loader reads badly — the tensor geometry differs — so a runtime either
implements JANG unpacking or it sees a malformed file. On the MoE model the three refusals take
three different shapes (`2026-09-16-moe-loadability-probe.md`): mlx-lm refuses at load with
`Expected shape (128000, 128) but received shape (128000, 384)`, oMLX starts and answers HTTP 409
at request time, and mlx-optiq starts, reports ready, accepts the request and **never answers** —
ten minutes to learn what a refusal says in milliseconds.

An axis point that only two of five runtimes can reach is not an axis point. Had v1 put
`jang4s__vmlx` into a `--study format` column beside `oq4__omlx` it would have moved the runtime
*and* the format in one comparison, and no number in that column could have been attributed to
either. That is the single-variable rule, and it is why the JANG cells exist in v1 only as the
last column of a ragged grid.

### 1.3 What changed: both JANG runtimes load portable formats too

The v1 grid already contained the shape of the fix, and `.paul/STATE.md` recorded it while
closing Phase 3:

> **Osaurus and vMLX are two independent JANG runtimes, both kept** | Phase 3 | JANG cannot be a
> format-axis row, but JANG-on-Osaurus vs JANG-on-vMLX is the runtime axis with format held
> constant. **Two implementations are what make a single-variable JANG study possible at all.**

What makes v2 different is the other half: **the same two runtimes load the portable formats.**

| runtime | loads (dense) | loads (MoE) | cannot load |
|---|---|---|---|
| vMLX 1.6.59 | stock-4bit, oQ4, oQ4e, **JANG_4S** | stock-4bit, oQ4, oQ4e, OptiQ, **JANG_2L** | dense OptiQ-4bit (missing vision parameters in the per-layer map — §2.1) |
| Osaurus 0.25.x | oQ4, oQ4e, OptiQ, **JANG_4S** | stock-4bit, oQ4, oQ4e, OptiQ, **JANG_2L** | dense stock-4bit (listed, not registered with any provider — §2.2) |

Sources: the two loadability probes above; every one of those cells answered coherently when
probed, and the MoE probe's five-format Osaurus column and five-format vMLX column are the reason
the MoE matrix in §2 is fuller than the dense one.

So the study splits into the only two readings JANG was always missing:

1. **The runtime held constant is 1A/1B** — one runtime, several formats with JANG among them.
   This is the format axis, and it is now legal in each of the two JANG runtimes. (It is "legal"
   in the sense `cli._check_axis` means: every cell in the selection names one runtime.)
2. **The artifact held constant is 1C** — the same JANG bytes, two loaders. This is the runtime
   axis, and it is the only comparison in the project where two different loaders see identical
   weights.

### 1.4 The claim this study is allowed to make

At the end of Phase 1 the study must be able to say, for each model: *"in runtime R, the JANG
bundle did (or did not) beat the best portable format on this workload by this much, with these
confounds named"* — and, where both runtimes agree, what the agreement rules out. It may not say
that JANG is faster in general, because two models on one machine are not a general claim, and it
may not say *why* beyond the attribution rules of Section 3, because the bundles differ from the
portables in size, bit width, packing and loader all at once and no artifact pair in this set
isolates one of those from the others.

---

## 2. The test matrix

### 2.0 How a matrix is read here

A cell is `(format, runtime)` and its id is `"<label>__<runtime>"`. `ohyesmlx run --study format`
holds the runtime constant and `--study runtime` holds the format constant; `cli._check_axis`
refuses a selection that varies both, before any runtime starts. A **column** (one runtime, many
formats) is the format axis. A **row** (one format, many runtimes) is the runtime axis. The best
cell across the whole matrix is a recommendation and never an attribution.

Labels are the vocabulary already used by `scripts/gridspec.sh` and `scripts/gridspec-moe.sh`:
`jang4s`, `jang2l`, `stock4bit`, `oq4`, `oq4e`, `optiq`. Keeping them means the study's records
read the same way v1's do and the grid's join guards keep their meaning: guard 3 refuses a join
where one label points at two artifacts (which is also why the dense and the MoE campaigns live in
separate directories and are joined separately — see §2.4).

### 2.1 Study 1A — JANG vs portable inside vMLX (format axis)

`--study format`, runtime `vmlx` held constant, one run per model.

**Dense — `Qwen3.5-4B`, four cells:**

| label | cell | repo / snapshot | role |
|---|---|---|---|
| `jang4s` | `jang4s__vmlx` | `JANGQ-AI/Qwen3.5-4B-JANG_4S` · `4567967a…` | the JANG arm |
| `stock4bit` | `stock4bit__vmlx` | `mlx-community/Qwen3.5-4B-4bit` · `0e7ffd5c…` | the stock MLX 4-bit control |
| `oq4` | `oq4__vmlx` | `RepublicOfKorokke/Qwen3.5-4B-oQ4` · `3ae88a7d…` | portable mixed-precision |
| `oq4e` | `oq4e__vmlx` | `uingei/Qwen3.5-4B-oQ4e` · `2e232e…` | portable mixed-precision |

**The one dense hole is a vMLX refusal, and it is worth more than the cell would have been.**
vMLX rejects `mlx-community/Qwen3.5-4B-OptiQ-4bit` in 9.2 s:

```
ERROR:vmlx_engine.models.mllm:Failed to load MLLM: Missing 297 parameters:
vision_tower.blocks.0.attn.proj.bias, …
ValueError: Missing 297 parameters
ERROR:    Application startup failed. Exiting.
```

The reading "the OptiQ conversion dropped the vision tower" is wrong: both artifacts carry 297
`vision_tower.*` tensors and both declare `vision_config`. The difference is in `config.json` —
OptiQ ships a per-layer quantization map with **249 entries**, and **0 of them are
`vision_tower`**, over bits `[4, 8]`. vMLX loads this checkpoint through its multimodal path,
builds a vision tower, finds no map entry for its parameters, and reports 297 missing
(`2026-09-15-grid-loadability-probe.md`). mlx-lm, oMLX and Osaurus load the same file, because
they either treat the checkpoint as text-only or fall back to the global rule for unnamed layers —
a fallback the probe established by behaviour and does not explain.

That is a **format × runtime interaction**, and it is the strongest argument this project has that
the matrix must be read cell by cell: it is invisible on the format axis (oMLX loads all five
formats) and invisible on the runtime axis (vMLX loads four of five). The study records the cell
as never run, renders `—` in the grid, and prints the reason in the write-up. **No synthetic
`FAIL` is manufactured for it** — a cell that was never attempted is not a measured failure, and
the grid's four entry states (`number`, `no value`, `FAIL`, `—`) exist so that a reader can tell
them apart.

**MoE — `LFM2.5-8B-A1B`, five cells:**

| label | cell | repo / snapshot | role |
|---|---|---|---|
| `jang2l` | `jang2l__vmlx` | `JANGQ-AI/LFM2.5-8B-A1B-JANG_2L` · `5fb82773…` | the JANG arm |
| `stock4bit` | `stock4bit__vmlx` | `mlx-community/LFM2.5-8B-A1B-MLX-4bit` · `146590a4…` | stock MLX 4-bit control |
| `oq4` | `oq4__vmlx` | `stamsam/LFM2.5-8B-A1B-oQ4` · `acb4fd20…` | portable mixed-precision |
| `oq4e` | `oq4e__vmlx` | `brainworkup/LFM2.5-8B-A1B-oQ4e` · `88977e47…` | portable mixed-precision |
| `optiq` | `optiq__vmlx` | `mlx-community/LFM2.5-8B-A1B-OptiQ-4bit` · `5a5c5958…` | portable mixed-precision |

OptiQ is included here and excluded above, and the asymmetry is the point: `LFM2.5-8B-A1B` is
text-only (its JANG sibling's sidecar declares `has_vision: false`), so there is no vision tower
for vMLX to build and the per-layer-map path that refuses the dense checkpoint cannot be reached.
The probe measured this — the MoE probe's OptiQ row reads `LOADS` for all five runtimes, vMLX
included — and v1's MoE grid nonetheless omitted `optiq__vmlx` because `gridspec-moe.sh` mirrors
the dense shape. This study makes the call explicitly rather than inheriting it, and the call is
to run the cell: it is the fifth portable, it costs about four minutes of wall clock for its three
workloads (§6.3), and its presence on one model and absence on the other is a finding that would
otherwise be filed as "vMLX cannot load OptiQ", which is false.

### 2.2 Study 1B — JANG vs portable inside Osaurus (format axis)

`--study format`, runtime `osaurus` held constant, one run per model. Every Osaurus run in this
study carries `--cache-state off` and requires the host toggled (§3.5, §5.7).

**Dense — four cells:**

| label | cell | role |
|---|---|---|
| `jang4s` | `jang4s__osaurus` | the JANG arm |
| `oq4` | `oq4__osaurus` | portable mixed-precision |
| `oq4e` | `oq4e__osaurus` | portable mixed-precision |
| `optiq` | `optiq__osaurus` | portable mixed-precision |

**The one dense hole is a catalogue fact, not a capability.** `stock4bit` (`qwen3.5-4b-4bit`) is
returned by `GET /v1/models` and then answers **`not installed or registered with any provider`**
when named in a request (`2026-09-15-grid-loadability-probe.md`; `docs/runtimes/osaurus.md`
§4.4.2). Osaurus serves from its own catalogue, the entry is the repo name lowercased, and the
entry's *provider registration* is separate from its listing. So the dense Osaurus column has no
stock-4bit cell: the artifact is on disk and the runtime offers it, and offering is not serving —
the same disease every runtime here has in a different form (mlx-lm lists a path it never loaded;
oMLX listed a JANG artifact it had already failed to load and published a 2.15 s cold load for
it).

The cell is recorded as never run with that reason. **What the study gains from it is the control
it does keep**: `oq4` and `oq4e` are in both runtimes' dense columns, so the JANG-vs-portable
question is answerable in both, and the missing stock-4bit cell costs only the stock comparison —
which the v1 dense grid already has, under vMLX and the other three runtimes.

**MoE — five cells:** `jang2l`, `stock4bit`, `oq4`, `oq4e`, `optiq`, all `__osaurus`. Unlike the
dense artifact, `lfm2.5-8b-a1b-mlx-4bit` **is** registered on this host: the MoE probe's
stock4bit row reads `LOADS` for all five runtimes including Osaurus. That gives the MoE matrix
five labels × two runtimes with no structural hole at all.

One cell in this column has a known failure mode, and the design predicts it rather than being
surprised by it: `optiq__osaurus` on the **decode** workload FAILed in the v1 MoE grid with
`no content completion tokens from token_source='none', so decode tok/s is undefined` — Osaurus
served the artifact, produced text, and reported no usable completion-token count for the
512-token shape (`2026-09-16-moe-format-axis.md`). The same cell passed `chat` and `prefill`. If
it reproduces, it is published as `FAIL` with that reason and no rate is read from it — the rule
that has held since Phase 2. If it does not reproduce, the difference is a finding about the
Osaurus build, and the Osaurus version is recorded per cell (`runtime_version`) so the comparison
is at least anchored.

### 2.3 Study 1C — JANG held constant, the runtime varies (runtime axis)

Same artifact bytes, two loaders. This is the row reading of the two columns above, not a third
campaign — the same economy Phase 5 applied to the runtime axis it found already measured:

| row | cells | artifact (identical in both) | what moves |
|---|---|---|---|
| dense JANG | `jang4s__vmlx` vs `jang4s__osaurus` | `JANGQ-AI/Qwen3.5-4B-JANG_4S` @ `4567967a…` | the loader and the runtime |
| MoE JANG | `jang2l__vmlx` vs `jang2l__osaurus` | `JANGQ-AI/LFM2.5-8B-A1B-JANG_2L` @ `5fb82773…` | the loader and the runtime |

Both rows are printed by `ohyesmlx grid` over the two run directories of the model's campaign:
the tool already renders rows across columns, and the JANG row is one of them. Nothing is
re-measured for 1C, and nothing may be: **the two directories must share every pin** (they will —
one runner, one flag set, one cache-state pin) or the join refuses by design.

Three limits ride on this row and the write-up states them beside it:

- **Loader and runtime are not separable here.** The row is JANG-on-vMLX against
  JANG-on-Osaurus, and vMLX and Osaurus differ in their loader, their scheduler, their Metal
  usage and their memory accounting at once. What the row establishes is *that the two
  implementations differ*, and by how much, on identical bytes — not which internal does it.
- **`cold_load_s` and `peak_mb` cannot be read across it.** `report.CROSS_RUNTIME_UNCOMPARABLE`
  prints its reason above any runtime-axis ordering by either: a footprint that lands within a
  few percent of the weights in four runtimes and at half of them in Osaurus is not one quantity,
  and a load that a runtime defers past readiness is a time-to-listening (`2026-09-16-phase5-joined-grid.md`,
  `2026-09-15-cold-load-is-not-one-quantity.md`). A cross-runtime load comparison uses
  `cold_load_s + first_request_s`; a memory comparison is not available from this harness at all.
- **Two cells per row is not an ordering.** It is a comparison, and it is reported with both
  numbers, the tie band of §2.5, and the replication of §2.5 applied to it.

### 2.4 The ragged edges, and why each is a measurement rather than a gap

The matrix is ragged by necessity, and every hole has a named cause. Consolidated:

| hole | what a reader might assume | what is true | evidence |
|---|---|---|---|
| dense `optiq__vmlx` | "vMLX cannot read OptiQ" | vMLX reads the *MoE* OptiQ; on the dense checkpoint its multimodal path requires vision parameters the artifact's per-layer map omits (0 of 249 entries) | §2.1 |
| dense `stock4bit__osaurus` | "Osaurus cannot read stock 4-bit" | listed in `/v1/models`, refused at request time as `not installed or registered with any provider`; the *MoE* stock 4-bit serves | §2.2 |
| dense `jang4s__mlxlm`, `__omlx`, `__optiq` | "not tested" | tested: shape refusal (mlx-lm), HTTP 409 (oMLX), hang (mlx-optiq, from the MoE probe's sibling case) | `2026-09-15-grid-loadability-probe.md`, `2026-09-16-moe-loadability-probe.md` |
| MoE `jang2l__mlxlm`, `__omlx`, `__optiq` | "not tested" | tested: shape refusal, HTTP 409, hang | `2026-09-16-moe-loadability-probe.md` |

Two consequences the execution plan depends on:

1. **Dense and MoE campaigns are never joined into one grid.** The run header does not name the
   model; the thing that would refuse a cross-model join is join guard 3, *one format label
   pointing at two artifacts* — the same label `stock4bit` on the dense snapshot and the MoE
   snapshot. Keeping the two campaigns in separate directories (`results/grid-jang-dense/`,
   `results/grid-jang-moe/`) and joining each separately is therefore not tidiness, it is the
   guard's precondition. A document may print the two grids side by side; the tool may not
   produce them in one table.
2. **A cell enters a column only after a loadability probe says it loads.** v1's lesson is that
   every predicted refusal was wrong and the one real refusal was not predicted
   (`2026-09-15-grid-loadability-probe.md`). Every cell in §2.1–§2.3 is probe-backed, and §5.8 is
   the per-cell pre-flight that re-establishes it for the artifact actually on disk on the day of
   the run.

### 2.5 Replication, and the tie band the study is pre-registered against

v1's runtime axis was first published and then withdrawn because the ordering moved under a
defensible change in how the window was taken: five adjacent pairs sat within 2.5% and swapped
places (`2026-09-16-phase5-joined-grid.md`). The study inherits the rule:

> **Adjacent cells within 2.5% are a tie, not an ordering.** 2.5% is not a physical constant; it
> is the largest gap v1 observed to change places when the window moved, and it is used here as a
> pre-registered band rather than as a discovered one.

**Replication is required for the cells that carry the claim** and not for the ones that describe
the column. Each model's campaign runs, after its two columns:

- a **replicate run per runtime** naming only the two decisive cells of that column — the JANG
  cell and the portable cell it beat (or lost to) by the widest margin in the primary;
- with the **column order reversed** against the primary (Osaurus's replicate before vMLX's, or
  the reverse of what the primary did), so that a session-long thermal or load trend cannot alias
  onto runtime identity;
- same pins, same workloads, same flag tuple, its own run directory.

**Pre-registered decision rules:**

- **R-tie.** A JANG lead is published as a lead only if the primary and the replicate agree on the
  direction *and* the gap clears 2.5% in both. A lead that clears 2.5% in one run and sits inside
  the band in the other is reported as a tie with both numbers printed.
- **R-reproduce.** A replicate that lands more than **5%** away from its primary on the same cell
  is published with both figures and no ordering between them. 5% is the project's existing
  drift-annotation threshold (`report.DRIFT_ANNOTATION_PCT`), and the largest visit-to-visit
  disagreement measured between two visits of one cell so far is 3.8%
  (`2026-09-17-cache-state-split-nonhybrid.md`), so 5% is the point at which a difference is
  larger than anything the harness has observed inside a cell.
- **R-nothing.** No replicate may be discarded for being inconvenient. A repeat run that disagrees
  is the finding; the campaign is not trimmed to the run that agreed.

---

## 3. The attribution analysis framework

### 3.1 Three candidate causes, and what can actually separate them

The question this framework exists to answer is: *is JANG's speed the weights, or the thing that
loads the weights?* Three candidate causes are named, each with the observation that could
separate it — and, where no such observation exists in this artifact set, that is stated rather
than worked around.

**(a) Weight-format causes** — what the bytes are: bytes per token (`bits × active parameters`),
per-tensor bit assignment, group size, packing (the half-width `embed_tokens` that generic
loaders cannot read), and whether the on-disk layout needs unpacking at load or per token.

*Separating observation available here:* the **dense** pair `jang4s` vs `stock4bit` is the one
near-equal-precision comparison in the set. JANG_4S declares `actual_bits: 4.15` at block size 64
and `bit_widths_used: [4, 6]`; the stock artifact is uniform 4-bit. On disk the JANG bundle is
**4.8% larger** (3,207,385,506 against 3,061,131,520 bytes, §4). A decode lead there cannot be a
size effect — it holds while carrying *more* bytes and *more* bits — which makes that one
comparison the cleanest evidence the study can produce for a non-size explanation. It cannot,
however, separate packing from kernel selection: both travel with the bundle.

*What is not available:* on the **MoE** model there is no equal-precision pair at all. JANG_2L
declares `actual_bits: 2.37` with `bit_widths_used: [2, 6, 8]` and 18 passthrough-16 tensors,
against portables at ~4 bits. A lead there is confounded with precision by construction.

**(b) Loader-level causes** — what the runtime does with the bytes: JANG unpacking, the mixed-bit
width "pre-fix" pass (vMLX's loader logs `Pre-fixed N module(s) with mixed-precision bit widths` —
217 on the dense artifact in v1), kernel selection for non-uniform affine layouts, `mx.compile`
(JIT), MTP heads, and loader-level KV quantization.

*Separating observation available here:* **Study 1C's row** — identical bytes, two independent
loaders. It is the only place in the project where two loaders see the same weights. It attributes
*to the pair*, not within a runtime, and it is the reason both JANG runtimes were kept.

**(c) Runtime-pin causes** — what the start command and host settings decide: vMLX's `--no-jit`
and `--disable-native-mtp`, the prefix/block-disk caches, Osaurus's `performance.tiedHeadCodec`,
`mtp.mode`, `cache.*`.

*Separating observation available here:* the pins themselves, made explicit and recorded (§3.4,
§3.5), plus one deferred single-variable A/B: **JANG with JIT against JANG without JIT, inside
vMLX on the same artifact.** That pair moves exactly one thing — the accelerator — because the
weights are constant. It is not in Phase 1 (§6.5) and it is the cheapest way this project will
ever have to price vMLX's JANG-specific optimization.

### 3.2 What the two JANG bundles declare about themselves

Read from `jang_config.json` in each snapshot on 2026-09-17 (both hashed, §4.2). The sidecar is
the artifact's own claim about itself; like a server's self-report it is provenance, and it is
quoted rather than trusted — but here it is the only statement that exists about how the bytes
were made.

| field | dense `JANG_4S` | MoE `JANG_2L` |
|---|---|---|
| `quantization.method` | `jang-importance` | `jang-importance` |
| `quantization.profile` | `JANG_4S` | `JANG_2L` |
| `quantization.target_bits` / `actual_bits` | 2.5 / **4.15** | 2.0 / **2.37** |
| `quantization.block_size` | 64 | 64 |
| `bit_widths_used` | `[4, 6]` | `[2, 6, 8]` (+ 18 tensors at 16) |
| `quantization_scheme` / `backend` | `asymmetric` / `mx.quantize` | `asymmetric` / `mx.quantize` |
| `format` / `format_version` | `jang` / 2.0 | `jang` / 2.0 |
| `architecture` | `hybrid_ssm`, `has_vision: true` | `hybrid_moe_ssm`, `has_vision: false`, `has_moe: true` |
| `capabilities.cache_type` | `hybrid` | `hybrid` |
| `runtime.total_weight_bytes` | 2,245,263,360 (2.09 GiB) | 3,044,371,880 (2.84 GiB) |

Three readings the framework pins, because each one is a trap for a careless write-up:

1. **`actual_bits` is an average over the bundle, not over the tensors decode touches.** MoE
   decode touches the routed experts; `bit_widths_used: [2, 6, 8]` says three widths are present
   and nothing in the sidecar says which module received which. A per-token byte model
   (`bytes/token ≈ active_params × actual_bits / 8`) is therefore **not derivable** from this
   file. Every rate in the write-up is published beside `actual_bits`, `bit_widths_used`, block
   size and the measured on-disk bytes, and no explanation is offered that depends on a byte
   count nobody measured.
2. **The dense sidecar's `total_weight_bytes` is 30% below the artifact on disk** (2.09 GiB
   declared, 2.99 GiB measured). The bundle declares `has_vision: true`, ships
   `preprocessor_config.json` and `video_preprocessor_config.json`, and its file list carries an
   MTP head; the declared figure is the language model. Anyone quoting 2.09 GiB as "the artifact
   size" would be quoting a subset. The record's `disk_bytes` is the measured whole.
3. **The MoE sidecar's `source_model.parameters` reads `34.5B`** for a model this project
   documents as 8 B total / 1 B active. It is a label written by the quantiser, not a
   measurement, and it is recorded here so nobody reads it as a third figure. Same rule as a
   server's self-reported tok/s: kept, labelled, never published as a value.

### 3.3 The confound ledger

Every confound this study knows about, what it would fake, the pin that answers it, and the
evidence a reader can check afterwards. A confound with no pin is listed as unpinned — that is
what makes the ledger honest.

| # | confound | what it would fake | the pin | evidence left behind |
|---|---|---|---|---|
| 1 | **Precision/size** — JANG's bits differ from the portables' | "JANG's packing is faster" when a smaller bundle simply moved fewer bytes | no pin equalizes them; every rate is published beside `actual_bits`, `bit_widths_used`, block size and the measured on-disk bytes, and the **dense** pair is the one near-equal-precision comparison (§3.1a) | `disk_bytes`, the sidecar's `actual_bits`/`bit_widths_used`, printed beside every rate |
| 2 | **Auto-JIT on affine bundles** — vMLX turns `mx.compile` on by itself for JANG affine bundles when neither JIT flag is passed; `--no-jit` is applied last and wins | "the JANG format is faster" when the JANG *cell* was the only cell running compiled | `--no-jit` in every vMLX start command of this study | the loader's own log line `JIT: mx.compile applied successfully — running warmup pass` must be **absent** in every vMLX log of the campaign (§5.8) |
| 3 | **MTP heads in the bundle** — the dense `JANG_4S` bundle ships `vmlx_mtp_proposal_head.json`; a bundle with a native MTP head can decode speculatively where the portables cannot | "JANG decodes faster" when one cell was running speculative decoding | `--disable-native-mtp` in every vMLX start command | the log line `MLLM native MTP skipped for request=…: disabled by VMLX_NATIVE_MTP=0/--disable-native-mtp` present on every request (§5.8) |
| 4 | **Loader-level TurboQuant KV** — auto-enabled only when the bundle's `jang_config.json` carries a `turboquant` block; KV precision is then decided by the artifact, not the flags | two JANG bundles with identical bit widths behaving differently for a reason no flag records | none in the harness; the omission of `--kv-cache-quantization` is deliberate and recorded (§3.4) | the loader's INFO line (`TurboQuant: not enabled` / `TurboQuant auto-enabled`) captured per run; **neither snapshot's `jang_config.json` carries a `turboquant` block** (hashed today, §4.2) |
| 5 | **Osaurus host settings** — no model and no tuning flags on its command line; caching, KV size, tied-head codec, MTP mode, threads and memory guards all live in `~/.osaurus/config` | any Osaurus number becoming unattributable the moment a setting moved between cells | `--cache-state off` (enforced by `Osaurus.cache_state_refusal`), the drift guard, byte-exact backup/restore, and a pre/post digest of both files (§3.5) | `config/osaurus-settings-baseline.json` drift **NONE** before every Osaurus cell; runner log carrying the toggle and the `cmp` restore |
| 6 | **Idle residency** — `modelIdleResidencyPolicy.seconds` unloads the model mid-window | a cell measured on a half-evicted model | pinned to **900 s** for the duration of every Osaurus run, restored after (host's own 30) | runner log line `osaurus idle residency pinned to 900 s`; restore verified with `cmp`, not with the drift guard (`§3.5`) |
| 7 | **Prefix/KV cache** — Osaurus cannot disable it from any command line, and a repeated prefill prompt is then a lookup; vMLX's hybrid path has no RAM fallback so its cache is already off | the prefill column measuring a cache lookup in one runtime and a full prefill in the other | `--cache-state off` on **every** run of this study, both runtimes | the header pin `cache_state: "off"`; vMLX's start command carries `--disable-prefix-cache` and `--disable-block-disk-cache`; Osaurus's host files were toggled false before the first cell and restored at the end |
| 8 | **Warmup** — one budget applied to two runtimes ranks them by how fast they warm | a runtime's warmup being read as its serving speed (the v1 runtime-axis defect) | the plateau rule, measured per cell: two windows of 5 rates, medians compared at 3%, floor 10, cap 20 | `warmup_count` per cell; `warmup_plateau: false` where a window hit the cap |
| 9 | **Thermal/session drift** | a thermal curve wearing a runtime's name | `visit_plan`'s two visits in opposite orders, a 30 s cooldown between visits, and the reversed column order between primary and replicate (§2.5) | `drift` per cell; annotation at ±5% |
| 10 | **Cross-runtime load and memory** — `cold_load_s` is a time-to-listening for a lazy loader, and `footprint` counts different pages per runtime | a load or memory "ranking" between vMLX and Osaurus | none: the metrics are not comparable. Use `cold_load_s + first_request_s` for load and publish no cross-runtime memory ordering | the renderer prints `CROSS_RUNTIME_UNCOMPARABLE` above any runtime-axis ordering by either |
| 11 | **Per-model thinking switches** — Osaurus's `disableThinking` lives in the app plist, per model, in no config file the drift guard reads, and it decides whether the model emits reasoning tokens at all | two Osaurus cells differing by the entire reasoning token count with nothing in the artifact saying why | a pre-flight plist check for the study's two Osaurus ids (§5.8) | the observation's own token counts; the plist values recorded in the run notes |
| 12 | **Runtime version** — Osaurus moved 0.25.3 → 0.25.6 across v1's documents; guard 4 refuses one runtime at two versions in a grid | a version step read as a format effect (Osaurus measured 1.15x across exactly such a step) | `runtime_version` recorded per cell; all runs of a campaign checked to one version before joining | the grid's provenance block, which names each column's version |

### 3.4 Pinning discipline — vMLX

The start command is fixed **once**, in `ohyesmlx/runtimes.py`, before the campaign begins, and
nothing in the campaign edits it. For a JANG cell it is byte-identical to the command a portable
cell gets; that is the point — the flag tuple is not per-format, so the only thing that differs
between two cells in a vMLX column is the artifact.

| pin | value | what it would otherwise change |
|---|---|---|
| `--no-jit` | **passed, always** (JIT off) | `mx.compile` is auto-ON for JANG affine bundles when neither JIT flag is passed (`cli.py:2085-2159`); `--no-jit` is applied last and wins. Without this pin the JANG cell would be the only compiled cell in its column |
| `--disable-native-mtp` | **passed, always** (MTP off) | MTP re-tunes its own depth mid-request; the dense JANG bundle ships `vmlx_mtp_proposal_head.json`, so without this pin a JANG cell could decode speculatively |
| `--stream-interval 1` | pinned | 8 is the default and batches tokens before the harness can count deltas |
| `--continuous-batching` + `--max-num-seqs 1` | pinned | single-stream measurement; `--no-continuous-batching` silently forces `stream_interval=1`, an interaction invisible in argv |
| `--disable-block-disk-cache` | pinned in both cache states | the SSD L2 turns itself on whenever continuous batching and prefix caching are both active, writes to `~/.cache/vmlx-engine/block-cache/<model_hash>`, and survives restarts |
| `--disable-prefix-cache` | pinned (the `cache_state: "off"` pin) | a prefix hit would be invisible to `Observation` and would publish as prefill throughput |
| `--api-key` | omitted | no auth by default; a measured request needs no credential |
| `--kv-cache-quantization` | **omitted, and the omission is recorded** | omitting selects production auto mode; *passing* it disables loader-level TurboQuant. Neither choice is neutral, which is why the omission is written down rather than assumed |
| `--enable-disk-cache`, `--use-paged-cache` | omitted | both off by default; the disk prompt cache makes request 1 differ from requests 2+ |

### 3.5 Pinning discipline — Osaurus

Osaurus takes no tuning flags: `osaurus serve --port 1337 --yes` carries no model and no settings,
and what a cell measures lives in `~/.osaurus/config`. The harness does not edit the host's files;
the **runner** does, with a byte-exact backup and restore, exactly as `scripts/run_sweep_cache.sh`
already does for the cache split. The mechanism, stated as the study's precondition:

1. `osaurus_settings.write_baseline()` records the live state as the baseline the harness's start
   gate compares against; `cp -p` copies of `server-runtime.json` and `server.json` are taken
   first, byte-exact.
2. For this study, `cache.prefix.enabled` and `cache.blockDisk.enabled` are set **false** for the
   whole campaign (§3.3's confound 7), and `modelIdleResidencyPolicy.seconds` is pinned to
   **900** — the host's own 30 would unload the model inside the 30 s cooldown.
3. Every Osaurus run passes `--cache-state off`, and `Osaurus.cache_state_refusal` refuses the
   cell up front if the host disagrees — so a toggle that silently failed cannot be measured
   through: the cell is `N/A` with the setting and the disagreeing value in the reason.
4. At the end, and on `INT`/`TERM`/`HUP`, both files are restored from the `cp -p` copies and
   **verified with `cmp -s`**, not with the drift guard. `git checkout --
   config/osaurus-settings-baseline.json` puts the committed baseline back.

**A finding that changes what "precondition" means here.** The live residency value on this host
today is **30** and the committed baseline says **900** — deliberately, by Jason's choice — and
`config/` is git-clean. Checked today with the module's own functions (read-only, no server
started):

```
drift_against_baseline(capture_osaurus_settings(), load_baseline())
  → 1 drifted key: server.json:modelIdleResidencyPolicy.seconds — baseline 900, host 30
```

`Osaurus.check_host_state` raises on exactly that difference. So **the 900 s pin is not an
optimization, it is a precondition**: a runner that does not pin it gets a refusal from the
harness, not a measurement. That is the guard working as designed — the host's own value
contradicts the recorded baseline, so the mismatch surfaces rather than being absorbed.

**What the drift guard does not watch, and the study's answer to it.** `TRACKED_KEYS` is 23 keys
and two live keys under `cache` are outside it (`cache.enableSSMReDerive`, a state setting on a
hybrid SSM model, and `cache.prefix.legacyEntryCountCache`). The baseline file also does not carry
`performance.deepseekV4ActivationQAT` or the `mtp.*` companion keys. Rather than ask for a code
change, the runner records **`shasum -a 256` of both files before and after every Osaurus cell**,
so any byte that moved — tracked or not — is in the record. A digest change between two cells of
one column invalidates the comparison, and the campaign stops and says so.

### 3.6 The pins the join guard cannot see

This is the one structural gap in the harness that this study must work around, and it is worth
stating plainly: **`results.jsonl` does not record the start-command flags.** Its header carries
`temperature`, `seed`, `warmup`, `measured`, `concurrency`, `prompt_tokens`, `cache_state`,
`cooldown_s` and the workloads — a flag tuple that changed between two runs is invisible to join
guard 1, so two runs that differ in `--no-jit` would join without a word.

The study's answers, in order of strength:

1. **One flag tuple per campaign.** The vMLX tuple of §3.4 is frozen before Plan 01-01 and is not
   edited until Phase 1 closes. That is a process pin, and it is recorded in the campaign's
   runner script — a file under version control, which is the only place it can be recorded
   today.
2. **Per-run log evidence.** The loader's own lines are the witness: the JIT warmup line must be
   absent, the MTP-skipped line present, `TurboQuant:` line captured, `JANG` load line captured
   (§5.8). These live in `results/logs/` with a timestamp and a pid, beside the run.
3. **Never join across arms.** If a future arm changes the tuple (the deferred JIT A/B of §3.1c),
   it gets its own run directory *and* its own write-up, and it is never added to a
   `ohyesmlx grid` invocation that contains a cell from another arm. The tool cannot refuse it;
   the procedure must.

### 3.7 Pre-registered readings

Written before the data exists, so the write-up cannot choose its story afterwards. `best_portable`
is the highest decode rate among the column's non-JANG cells on the same workload and cells; the
lead is defined as

```
L(workload) = (decode_tps(JANG) − decode_tps(best_portable)) / decode_tps(best_portable) × 100
```

evaluated per workload, never pooled across workloads, and the workload is printed with every L.

| reading | condition | what the study may say | what it may not say |
|---|---|---|---|
| **R1 — replicated lead** | L > +2.5% in the primary *and* the replicate, in **both** runtimes, on the same workload | "the JANG bundle beat the best portable format in both runtimes that load it; the effect is not private to one loader" | *why* it is faster — packing, bits and loader remain entangled (§3.1a) |
| **R2 — loader-local lead** | L > +2.5% in one runtime and inside the band in the other | "in runtime A the JANG bundle led by X; in runtime B it did not; the difference between the two is the loader pair, and nothing here separates one loader from the other" | any generalization to other models, other sizes, or the other runtime's future builds |
| **R3 — tie** | \|L\| ≤ 2.5% everywhere | "JANG bought nothing measurable over the best portable format on this model, workload and runtime" | "JANG is slower" — a tie is not a loss |
| **R4 — split by model** | R1/R2 on one model, R3 or reversed sign on the other | "the effect is model-specific" — which is exactly what the v1 format ordering did when it failed to transfer from dense to MoE (`2026-09-16-moe-format-axis.md`) | pooling the two models into one claim |

Also pre-registered, and applying to every reading above:

- **No rate is published from a cell that did not produce language** (the coherence gate, §5.4).
- **No ordering where the gap is inside 2.5%** without the word tie beside it.
- **No number attributed to "the format"** — the attributable unit is the *bundle* (these bytes at
  this snapshot) measured in *this runtime at this version*.

---

## 4. On-disk artifact inventory and storage verification

### 4.1 Method

`ohyesmlx.measure.artifact_bytes` — the harness's own function, the one whose return value is
written into every record's `disk_bytes` — was run over each snapshot path today. It walks the
tree, counts each file once by `(device, inode)`, and follows symlinks, which is exactly what makes a
Hugging Face cache snapshot correct: its files are symlinks into `blobs/` that several snapshots
can share. File counts are the walked file count; for every artifact here the distinct-inode
count equals the walked count, so nothing within an artifact is double-counted and no blob is
shared between two of these ten.

Recompute:

```sh
python3 -c "
import os, sys; sys.path.insert(0, '.')
from ohyesmlx.measure import artifact_bytes
H = os.path.expanduser('~/.cache/huggingface/hub')
print(artifact_bytes(H + '/models--JANGQ-AI--Qwen3.5-4B-JANG_4S/snapshots/4567967a46cd9e9bf26d3bb491ddd422ad607775'))
"
```

### 4.2 The ten artifacts

All paths are under `$H = ~/.cache/huggingface/hub/`. `GiB` is the binary unit and `GB` the
decimal one; both are given because the dispatch's figures are GiB and two v1 documents print
decimal GB for the same bytes.

| model | label | repo | snapshot | files | bytes | GiB | GB |
|---|---|---|---|---|---|---|---|
| Qwen3.5-4B | `jang4s` | `JANGQ-AI/Qwen3.5-4B-JANG_4S` | `4567967a46cd9e9bf26d3bb491ddd422ad607775` | 15 | 3,207,385,506 | 2.987 | 3.207 |
| Qwen3.5-4B | `stock4bit` | `mlx-community/Qwen3.5-4B-4bit` | `0e7ffd5c629ef7719d4cbc04069232580bfa9d9c` | 12 | 3,061,131,520 | 2.851 | 3.061 |
| Qwen3.5-4B | `oq4` | `RepublicOfKorokke/Qwen3.5-4B-oQ4` | `3ae88a7d17b1c6bb71b795c1090948a82508fdb8` | 12 | 3,160,559,814 | 2.944 | 3.161 |
| Qwen3.5-4B | `oq4e` | `uingei/Qwen3.5-4B-oQ4e` | `2e232d525d5df5e7a6eece4b03b17087e6b3c3ac` | 11 | 3,167,949,891 | 2.950 | 3.168 |
| Qwen3.5-4B | `optiq` | `mlx-community/Qwen3.5-4B-OptiQ-4bit` | `6cb5bdfd0bf15f484881fb9f1ab6d7c840fddde9` | 15 | 4,043,620,369 | 3.766 | 4.044 |
| LFM2.5-8B-A1B | `jang2l` | `JANGQ-AI/LFM2.5-8B-A1B-JANG_2L` | `5fb82773427c2f25395de8821eff6d95e86feb53` | 18 | 3,062,430,853 | 2.852 | 3.062 |
| LFM2.5-8B-A1B | `stock4bit` | `mlx-community/LFM2.5-8B-A1B-MLX-4bit` | `146590a491db88581884033023f51f6b49a27b89` | 11 | 4,782,228,753 | 4.454 | 4.782 |
| LFM2.5-8B-A1B | `oq4` | `stamsam/LFM2.5-8B-A1B-oQ4` | `acb4fd209565b7c05de287488416f4217820a3db` | 10 | 4,994,822,580 | 4.652 | 4.995 |
| LFM2.5-8B-A1B | `oq4e` | `brainworkup/LFM2.5-8B-A1B-oQ4e` | `88977e47cd1fe2eb5ec5bf5230d3de9868adef9e` | 11 | 4,994,831,815 | 4.652 | 4.995 |
| LFM2.5-8B-A1B | `optiq` | `mlx-community/LFM2.5-8B-A1B-OptiQ-4bit` | `5a5c595823cf26ab1068508eb5cf85816bb2db6b` | 14 | 5,473,296,789 | 5.097 | 5.473 |

Totals: dense **16,640,647,100 B** (15.50 GiB / 16.64 GB), MoE **23,307,610,790 B**
(21.71 GiB / 23.31 GB), both **39,948,257,890 B** (37.20 GiB / 39.95 GB).

Two JANG-specific facts the plan depends on, both from the file listing:

- **The dense `JANG_4S` bundle ships `vmlx_mtp_proposal_head.json`.** None of the nine other
  artifacts does. That is the concrete reason `--disable-native-mtp` is a pin (§3.3 #3) and not a
  precaution: without it, the JANG cell is the only cell in its column that can decode
  speculatively.
- **Both JANG bundles carry `jang_config.json` and `tokenizer.json`; neither carries a
  `turboquant` block.** So loader-level TurboQuant KV is not active for either (its auto path
  requires `turboquant.enabled=true` in that file), the KV codec is the runtime's default in both
  cells, and the loader's `TurboQuant: not enabled` line is the per-run confirmation (§5.8).
  Sidecar digests for the campaign's provenance banner:
  `JANG_4S` `3a9bf087d86505da8828cd2a2d39cb7c37066c755132fbfca35fbafeebe2abcd`,
  `JANG_2L` `858385d169c8028f0e59654d591510f519ba4cac58ed61365c49eed31a26f610`.

A provenance note: **eight of the ten artifacts carry a `.vmlx-alignment.lock`** — every one
except the two JANG bundles — written by a tool that has touched those directories before. The
JANG bundles carry none. `disk_bytes` is recorded per cell at
measurement time, so a bundle that changes size between cells would show in the record rather than
silently re-baselining; `vmlx bundle-check --json` is the explicit integrity assertion available
before spending a load.

### 4.3 Where the dispatch's figures differ from the disk

Nine of the ten sizes in the dispatch that commissioned this document agree with the disk to
three decimal places in GiB (2.99 / 2.85 / 2.94 / 2.95, 2.85 / 4.45 / 4.65 / 4.65 / 5.10). **The
dense OptiQ row does not**: the dispatch says 3.06 GB, and the disk says
**4,043,620,369 bytes = 3.766 GiB**. 3.06 is the *decimal* GB figure for the dense stock-4bit
artifact (3.061 GB), so the row appears to have picked up its neighbour's number. The MoE section
of the dispatch is at the same GiB scale and agrees throughout, and
`docs/research/2026-09-16-moe-format-axis.md` independently records the dense OptiQ artifact at
"4.04 GB against stock's 3.06" — which is this document's 4.044 GB and 3.061 GB. The table in
§4.2 is what the disk says; the dispatch's row is corrected here rather than silently carried.

### 4.4 Zero-download compliance

**All ten artifacts are present on disk and complete: zero downloads are needed for this study.**
Every snapshot hash named in §4.2 was resolved and walked today. No fetch script is required —
`scripts/fetch_moe.sh` and its sibling were used in v1 and are not needed here — and no `hf
download` may run during the campaign. The standing rule holds unchanged: *never download while a
measurement is running*, because it competes for the disk `cold_load_s` is timing.

---

## 5. Experimental protocol and invariants

### 5.1 The run and its pins

Every campaign run is one `ohyesmlx run` invocation, and it writes
`<results-dir>/<run-id>/results.jsonl` (header line, then one line per (cell, workload)) plus a
markdown leaderboard. The header's pins for this study:

| pin | value | where it comes from |
|---|---|---|
| `temperature` | `0.0` | `measure.TEMPERATURE` |
| `seed` | `0` | `measure.SEED` |
| `warmup` | `{mode: plateau, window: 5, floor: 10, cap: 20, plateau_pct: 3.0}` | the plateau rule; the floor is `2 × window` |
| `measured` | `9` **batches** | at `concurrency` 1 a batch is one request |
| `concurrency` | `1` | this study is sequential; concurrency is a v1 sweep's pin, not a JANG variable |
| `prompt_tokens` | `null` | the three pinned workloads send their own literals; no sized prompt |
| `cache_state` | `"off"` | **both runtimes**, for the whole study (§3.3 #7, §3.5) |
| `cooldown_s` | `30.0` | between visits |

`cache_state: "off"` is a deliberate departure from v1's grid runs, which carried no cache pin at
all. The consequences are stated rather than discovered: vMLX's start command is byte-identical
either way (`cache_state ≠ "on"` already selects `--disable-prefix-cache`), Osaurus is now held to
a state the host must be in, and **these runs cannot be joined with any v1 run directory** — join
guard 1 compares `cache_state`, and `ABSENT_PINS` reads the old runs' absent pin as `None`, which
is the pin *not taken* rather than a state. v1's JANG cells stay history, compared in prose with
the cache-state difference named, and are never a column of this study's grid.

### 5.2 The workloads

Three shapes, pinned in `cli.py`, never averaged into each other, one table per shape:

| id | prompt | `max_tokens` | what it exposes |
|---|---|---|---|
| `chat` | `PROMPT` (short) | 128 | per-request latency and overhead |
| `prefill` | `PREFILL_PROMPT` (~1.6k tokens) | 64 | prompt-processing throughput |
| `decode` | the same `PROMPT` as `chat` | 512 | sustained generation and memory growth |

`chat` and `decode` send the same prompt and differ only in the cap, which is the point. A figure
from one shape is not a ranking, and the JANG lead `L` (§3.7) is computed per workload and never
pooled.

### 5.3 Visits, cooldown, interleave

Each cell is visited **twice** (`VISIT_ROUNDS = 2`), the nine measured batches splitting 5 and 4,
with the second visit walking the cell list in reverse. A 30 s cooldown separates visits that
sampled anything. Nothing about this changes for JANG: the visit plan is per-cell and format-blind,
and the reasons (thermal aliasing, one load per visit) are the ones v1 already recorded.

### 5.4 The coherence gate

Every measured response is judged by `ohyesmlx/coherence.py`; more than half incoherent and the
cell is **FAIL** with the offending sample still on the record, and no tok/s, TTFT, ITL or
throughput figure is read from it. A fast cell that emits token salad is a failed cell — the rule
that has defined this project since stock mlx-lm loaded a 256-expert oQ4 MoE in 4 s, returned HTTP
200, hit full throughput and produced mixed-script garbage with nothing raised. The gate reads
content, or reasoning when a response emitted no content at all, because a reasoning-only runtime
is a normal shape here: mlx-lm 0.31.3 and vMLX 1.6.59 both answer entirely in that channel on a
thinking model, and vMLX is one of this study's two runtimes.

A JANG bundle's mixed-precision layers are exactly the kind of artifact on which an incoherent
cell is plausible, and the gate is what makes such a cell publishable as a failure instead of as a
number. **The gate is a floor, not an eval**: it says "this is language", never "this is right".

### 5.5 Memory and load

- **Memory** is Apple's `phys_footprint` read from `/usr/bin/footprint -p <pid>` once a second
  across each workload's own window; the published `peak_mb` is the higher of the cell's two
  visits. Never `ps` RSS. A **runtime-axis** ordering by it prints
  `report.CROSS_RUNTIME_UNCOMPARABLE`: four columns of the 2026-09-16 grid report a footprint
  within a few percent of their weight bytes and Osaurus reports roughly half of them
  (`2026-09-16-footprint-is-not-one-quantity.md`). Format-axis orderings within one runtime are
  unaffected, which is what Studies 1A and 1B publish.
- **Load** is two numbers, never one: `cold_load_s` (spawn → ready) and `first_request_s` (the
  cold visit's first warmup latency, where a lazy loader pays for its weights), with
  `first_request_workload_id` naming which shape made that request. Any cross-runtime load
  comparison uses the **sum**. Within a column it stays whatever it is, identically for every
  cell.
- **Disk** is `disk_bytes` per cell, from §4's function, sidecar files included.

### 5.6 Analysis rules

The ones that hold for every published table, restated here because the JANG write-up will be read
by people who did not read Phase 5:

1. **Floors first, pass/fail, never weighted**: coherence, every published metric present, and the
   cell fits in unified memory.
2. **One named ordering metric per table**, printed in the header. There is no blended score:
   weighting a second of latency against a megabyte has no objective answer. Default is
   `decode_tps` (`report.DEFAULT_RANK`); a TTFT-ranked table names `ttft_p50_s` and carries no
   drift marker where the marker would misstate the number it sits beside.
3. **Ties are printed as ties** (§2.5). A rank number beside a 0.3% gap is a reader's inference,
   not the measurement's claim.
4. **Drift annotates, never fails.** `measured_drift` compares the medians of the first and second
   halves of a cell's measured requests; ±5% is the annotation threshold. A positive drift means
   the window closed while the cell was still warming, and it is printed rather than smoothed.
5. **A short window is annotated, never dropped** (`(n=K of N)`), and a lost visit keeps its
   reason on the row.
6. **A run is discarded only for a stated defect in its conditions**, never for its number, and the
   discarded directory is kept and named with the reason. v1 paid for this rule with a column: the
   first oMLX grid column was measured while the coordinator pushed commits and ran pytest, one
   cell warmed at 68–73 tok/s and measured 40–60, and it would have inverted the format ordering
   that replicates across three codebases.
7. **Raw observations are never truncated**, warmups included, and derived fields are recomputed
   from them on read.

### 5.7 Host isolation

- **Nothing else runs on this machine while a cell is measured.** Not a test suite, not a git
  operation, not a download, not "lightweight" background work. The harness cannot detect
  contention, so the rule holds without enforcement, and the JANG campaign is the last thing on
  the machine while it runs.
- **One runtime holds weights at a time.** `run_cells` stops the current runtime and confirms its
  port is free before starting the next; a leaked resident would contend for the memory the next
  cell measures. Ports: vMLX **8000**, Osaurus **1337** (and, for the record, mlx-lm 8081, `optiq`
  8080, oMLX 8100).
- **Osaurus leftovers are swept by full executable path** —
  `^/Applications/osaurus.app/Contents/MacOS/osaurus` — and **never by the name `osaurus`**:
  `osaurus stop` frees the port and leaves the app resident at ~900 MB, and `osaurus mcp` is a
  long-running user process that must not be touched.
- **The Osaurus settings guarantee.** Backup (`cp -p`) → pin (`cache.*` false, residency 900) →
  re-record the baseline so the harness's own gate passes → run → restore → `cmp -s` against the
  copies, on the normal path **and** on `INT`/`TERM`/`HUP`, then `git checkout --
  config/osaurus-settings-baseline.json`. Restoration is verified with `cmp`, not with the drift
  guard: the host's 30 legitimately differs from the committed baseline's 900 and the guard would
  report Jason's own machine as drift forever. Jason's guarantee is that his KV caches and idle
  residency come back byte-exact, and this study's runner is built to honour it on every path out.
- **oMLX is not a runtime in this study** (it loads no JANG format), so its per-run scratch and
  SSD-cache rules do not apply here beyond `run_cells`'s guarantees.
- **Runner logs**: the wrapper writes progress to `results/<campaign>/runner.log` via `exec >
  "$OUT/runner.log" 2>&1` — the redirect is inside the script because a caller-side `cmd & > file`
  produced four 0-byte runner logs in v1. Per-cell CLI output is captured per cell.

### 5.8 Per-cell pre-flight, and the evidence each JANG cell must leave behind

Before a cell enters a column, the run's own start path has already established: the artifact
exists, a `TokenCounter` builds from it (both JANG bundles carry `tokenizer.json`; a missing
tokenizer makes the cell `N/A`, never a silent fallback), and the runtime resolves the model id
*and* writes no load failure to its log — readiness is neither the port nor the model list, and
this project has published a cold load for a model that had already failed to load. Beyond that,
the campaign checks the following per cell and records them in the run notes:

| check | how it is read | why it matters |
|---|---|---|
| vMLX resolved the JANG bundle | log: `JANG v2 … loaded` and a `Pre-fixed N module(s) with mixed-precision bit widths` line (217 on the dense artifact in v1) | proves the loader path, not the generic `mlx_lm.load` fallback |
| JIT is **off** | absence of `JIT: mx.compile applied successfully — running warmup pass` in all vMLX logs | the affine auto-JIT path (§3.3 #2) leaves the wrong trace if it fired |
| MTP is **off** | presence of `MLLM native MTP skipped for request=…: disabled by VMLX_NATIVE_MTP=0/--disable-native-mtp` on every request | the dense bundle ships an MTP head |
| TQ KV state | `TurboQuant: not enabled (jang_config has no 'turboquant' block…)` — or, if it says `auto-enabled`, the campaign stops | KV precision would have been artifact-decided |
| Osaurus answered as itself | the model id resolves (`qwen3.5-4b-jang_4s`, `lfm2.5-8b-a1b-jang_2l`) and the log has no load failure | the catalogue/registration trap is dense stock-4bit's |
| Osaurus thinking switch | the plist's per-model `disableThinking` for the study's two ids, recorded in the run notes | it changes the token counts and the channel shape with nothing in the artifact saying so |
| Osaurus settings unchanged | `shasum -a 256` of `server-runtime.json` and `server.json` before/after each cell | the drift guard watches 23 keys; the digests watch all of them |

---

## 6. Execution plan

### 6.1 Preconditions

- **Artifacts**: §4 verified — ten present, zero downloads, digests recorded.
- **Harness**: no code change is required. The study runs on today's `ohyesmlx run --study format`
  (both columns of §2.1/§2.2), `--cache-state off`, and `ohyesmlx grid` (the join that prints
  Study 1C). Two new runner scripts are the whole of the new code, modelled on
  `scripts/run_grid.sh` and `scripts/run_sweep_cache.sh`; the vMLX flag tuple of §3.4 is left
  exactly as `runtimes.py` already has it.
- **Host**: quiet machine; ports free; Osaurus settings backed up and the 900 s pin in place
  (§3.5); the baseline re-recorded and drift **NONE** before the first Osaurus cell.
- **Ordering**: each model's two columns run back to back, and the replicate's column order is the
  reverse of the primary's (§2.5).
- **Nothing is published from a probe**, and nothing measured for pre-flight enters a record.

### 6.2 Plan 01-01 — Dense JANG study (`Qwen3.5-4B`)

| step | command (abridged; paths resolved from `gridspec.sh`) | output |
|---|---|---|
| 1. vMLX column | `run --study format --cache-state off --cells "jang4s__vmlx=$JG4S,stock4bit__vmlx=$S4,oq4__vmlx=$Q4,oq4e__vmlx=$QE" --results-dir results/grid-jang-dense` | one run dir, 12 rows (4 cells × 3 workloads) |
| 2. Osaurus column | same flags, `"--cells jang4s__osaurus=$JG4S,oq4__osaurus=$Q4,oq4e__osaurus=$QE,optiq__osaurus=$OQ"` | one run dir |
| 3. join | `grid <vmlx-dir> <osaurus-dir> --out results/grid-jang-dense/grid.md` | the format-axis grid and, in it, the **1C dense JANG row** |
| 4. replicate | two 2-cell runs, `--cells "jang4s__<rt>=…,<best-portable>__<rt>=…"`, column order reversed, own dirs | the R-tie / R-reproduce evidence |
| 5. write-up | `docs/research/<date>-jang-dense.md` | the finding, with §3.7's reading applied |

Cost expectation, derived from v1 rather than guessed: the five-column dense grid measured 60 rows
in 2 h 28 m, so one 4-format column (12 rows) is ≈ 30 min and a 2-format replicate (6 rows) ≈ 15
min. **Plan 01-01 is a couple of hours of measurement.** Exit criteria: both columns PASS (or FAIL
with reasons), no lost visit unexplained, replicate run, grid joined, JANG row read, and every
confound in §3.3 either pinned or declared.

### 6.3 Plan 01-02 — MoE JANG study (`LFM2.5-8B-A1B`)

Same five steps over the MoE cell sets of §2.1/§2.2 (five cells per column, including
`optiq__vmlx` and `stock4bit__osaurus`). `results/grid-jang-moe/`. Cost expectation, on the same
derivation: the v1 MoE grid measured 60 rows in 1 h 24 m, so a five-format column (15 rows) is
≈ 20 min. The known decoding is that `optiq__osaurus` may reproduce v1's decode-workload FAIL; a
FAIL there is an outcome, reported with its reason, and the column still stands.

### 6.4 Plan 01-03 — Cross-runtime JANG synthesis

No new measurement. The JANG rows of the two grids (dense `jang4s`, MoE `jang2l`) are read as the
runtime axis, with the two caveats of §2.3 attached, and the two models' readings are set side by
side. The synthesis answers, in order:

1. Did JANG lead in vMLX, in Osaurus, in both, or in neither — per model, per workload (§3.7)?
2. Did the two runtimes agree on the *direction*, and how far apart are their JANG rates on
   identical bytes?
3. Does the dense reading transfer to the MoE model (R4), or does the effect, like v1's format
   ordering, prove model-specific?
4. What remains unattributed, in the ledger's own terms — precision, packing, loader — with the
   deferred JIT A/B named as the next experiment rather than the answer.

Deliverable: `docs/research/<date>-jang-cross-runtime.md`, the paper that closes v2 Track 1.

### 6.5 Out of scope for Phase 1

- **The JIT A/B inside vMLX** (§3.1c): a legal single-variable pair (`--enable-jit` vs `--no-jit`,
   artifact and runtime constant) but a different arm, and the join guard cannot see the flag
   (§3.6). Named as the first follow-up, not run here.
- **Accuracy.** Nothing in this study speaks to what the formats cost in quality. A JANG lead in
  tok/s and a JANG loss in accuracy can both be true, and v2's accuracy track is a separate study
  with its own pinning discipline.
- **Any third model, any other runtime.** mlx-lm, oMLX and mlx-optiq cannot load either JANG
  bundle; adding a model is a new campaign, not an extra cell.
- **Long-context, concurrency, cache-state sweeps.** Each is a pin this study holds at one value.
  None is a JANG variable, and v1's machinery for each already exists.

---

## 7. What this study will not establish

- **Not that JANG is faster in general.** Two models, two runtimes, one M2 Max. A lead here is a
  lead on `Qwen3.5-4B` or `LFM2.5-8B-A1B`, in vMLX 1.6.59 or Osaurus 0.25.x, at these pins.
- **Not why**, beyond the pre-registered readings. The bundle and the loader travel together by
  construction (§3.1a/b); the one clean separator — same bytes, two loaders — attributes to the
  pair and not within it.
- **Not equal-precision.** On the MoE the comparison is 2.37 average bits against ~4; JANG_2L is
  36–39% smaller than the portable 4-bit artifacts, and the study says so beside every number.
- **Not the shipped vMLX JANG experience.** JIT and native MTP are pinned off so that the JANG
  cell differs from its column only in its bytes. The vendor's headline path is JIT-on, and the
  study's number is a floor for it, not a replica of it.
- **Not publishable cross-runtime memory or load rankings.** Those two metrics are not one
  quantity across runtimes (§5.5).
- **Not accuracy, and not a recommendation about quality.** See §6.5.

## 8. Open questions

1. **Is the dense JANG_4S lead (77.3 vMLX, 69.5 Osaurus) a bit advantage or a packing one?** The
   dense comparison is near-equal-precision (4.15 vs 4 bits) and JANG carries more bytes, which
   rules out a size explanation. It rules out nothing about packing, kernel or loader.
2. **Why is vMLX's JANG_2L cell mid-pack while Osaurus's leads?** 122.2 against 133.3 stock in the
   same column, versus 147.1 leading Osaurus's column. Same bytes, two loaders — this is exactly
   what 1C exists to re-measure under one pin set, and the v1 numbers were taken in a grid whose
   warmup and session conditions differed between columns.
3. **Does `optiq__osaurus` fail decode again?** If the token-accounting failure is
   version-specific it will show in `runtime_version`; if it is artifact-specific the same FAIL
   recurs (v1: `token_source='none'` on the 512-token shape).
4. **What does the dense bundle's `vmlx_mtp_proposal_head.json` do when it is not disabled?**
   Untested here by design. It is the second half of the deferred JIT/MTP arm.
5. **Should the JANG bundles' numbers be compared against the vendor's published claims?** Not in
   this document's scope, and the vendor measures with its own harness (`vmlx bench` is
   in-process, not over HTTP). If that comparison is ever made, both sides' pins must be published
   side by side.

## Appendix A — record fields this study relies on

From `measure.py`'s record and `report.summarize`: `cell{id,runtime,artifact_dir,label}`,
`workload_id`, `status`, `reason`, `cold_load_s`, `first_request_s`,
`first_request_workload_id`, `memory{peak_mb,samples,…}`, `runtime_version`, `disk_bytes`,
`measured_count`, `warmup_count`, `warmup_plateau`, `drift`, `observations[]`,
`warmup_observations[]`, `batch_spans` (absent at `concurrency` 1), `lost_visit_reason` and
`cold_load_after_lost_visit` (present only when true), and the header pins of §5.1. Derived
figures are recomputed on read; the three the record stores (`measured_count`, `warmup_count`,
`drift`) are for a reader with `jq` and are not read back.

## Appendix B — evidence index

| what | where |
|---|---|
| the founding decision, and the two-JANG-runtimes decision | `.paul/STATE.md` (Decisions table) |
| JANG's tensor-level refusal on three runtimes; the dense OptiQ vision-map refusal; Osaurus's not-registered stock-4bit | `docs/research/2026-09-15-grid-loadability-probe.md` |
| MoE loadability; optiq hangs on JANG; vMLX's 18–19 s MoE cold loads | `docs/research/2026-09-16-moe-loadability-probe.md` |
| the v1 dense grid's JANG cells and the tie rule | `docs/research/2026-09-16-phase5-joined-grid.md` |
| the v1 MoE grid's JANG_2L cells and the `optiq__osaurus` decode FAIL | `docs/research/2026-09-16-moe-format-axis.md` |
| vMLX's auto-JIT for affine bundles; the MTP depth policy; the TQ-KV block; caches and the startup trim | `docs/runtimes/vmlx.md` §§7.1, 7.2, 7.4, 7.5, 8 |
| Osaurus's settings, the tracked keys, `tiedHeadCodec: q6`, per-model `disableThinking` | `docs/runtimes/osaurus.md` §§3.2, 4.4, 7.4; `ohyesmlx/osaurus_settings.py`; `config/osaurus-settings-baseline.json` |
| the cache-state pin, and the Osaurus toggle/restore precedent | `docs/interfaces.md` ("Plan 06-02"); `scripts/run_sweep_cache.sh`; `docs/research/2026-09-17-cache-state-split.md` |
| the run/flag pins as they exist in code | `ohyesmlx/runtimes.py` (`MlxLm`…`Vmlx.start_command`), `ohyesmlx/measure.py`, `ohyesmlx/cli.py` |
| the v1 cell sets this study extends | `scripts/gridspec.sh`, `scripts/gridspec-moe.sh` |
| the artifact sizes and counts in §4 | recomputed today with `ohyesmlx.measure.artifact_bytes`; `jang_config.json` shasums as shown |
