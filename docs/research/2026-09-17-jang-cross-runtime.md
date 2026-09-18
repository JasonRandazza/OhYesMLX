# Plan 01-03 — the cross-runtime JANG synthesis: dense and MoE, two models, two loaders

Date: 2026-09-17. **No new measurement.** Nothing in this document was measured for it: no
runtime was started, no model was loaded, no tensor was read. Every number below is quoted from
one of the two campaigns it synthesizes, and every table names the section it came from.

Sources, in the design's order:

- **Design** — `docs/research/2026-09-17-v2-track1-jang-study-design.md`: the pre-registered
  readings (R1–R4), the 2.5% tie band, the replication rules, the confound ledger (`§3.3`), the
  attribution framework (`§3.1`) and this plan's charter (`§6.4`).
- **Dense** — `docs/research/2026-09-17-dense-jang-study.md` (Plan 01-01): `Qwen3.5-4B` and
  `JANG_4S`, in vMLX 1.6.59 and Osaurus 0.25.6.
- **MoE** — `docs/research/2026-09-17-moe-jang-study.md` (Plan 01-02): `LFM2.5-8B-A1B` and
  `JANG_2L`, in the same two runtimes at the same two versions.

This is the paper the design's `§6.4` commissions: it reads the JANG rows of the two grids as the
runtime axis, sets the two models' readings side by side, and answers the four questions in order.
Where a study narrowed its own dispatch's attribution — dense `§6.3` did this explicitly — the
narrowing is kept rather than re-widened.

---

## 1. Executive summary and the synthesis thesis

### 1.1 The four questions, answered directly (design §6.4)

**1. Did JANG lead in vMLX, in Osaurus, in both, or in neither — per model, per workload?**

On the workload that carries the readings — the 512-token `decode` shape, whose rate a prefix
cache cannot touch — the serving outcome forms a 2×2 matrix, and only one of its four quadrants is
a win:

| model | runtime | `L` primary | `L` replicate | reading |
|---|---|---|---|---|
| `Qwen3.5-4B` (dense, `JANG_4S`) | vmlx 1.6.59 | **+13.9%** | **+16.8%** | **R1 — replicated lead** |
| `Qwen3.5-4B` (dense, `JANG_4S`) | osaurus 0.25.6 | **+9.5%** | **+9.0%** | **R1 — replicated lead** |
| `LFM2.5-8B-A1B` (MoE, `JANG_2L`) | vmlx 1.6.59 | +0.87% | −0.50% | **R3 — tie** (both visits inside the band) |
| `LFM2.5-8B-A1B` (MoE, `JANG_2L`) | osaurus 0.25.6 | **−5.12%** | **−9.80%** | `stock4bit` ahead in both visits |

`L` is the design's definition (`§3.7`): `(decode_tps(JANG) − decode_tps(best_portable)) /
decode_tps(best_portable) × 100`, per workload, never pooled. Sources: dense `§1.2`; MoE `§1.2`.
On the other two workloads the dense columns publish no ordering at all (dense `§1.3`), and the
MoE column publishes a replicated `stock4bit` lead on `chat` and on the `prefill` workload's
64-token rate (MoE `§4.4`). §3 states all twelve readings.

**2. Did the two runtimes agree on the direction, and how far apart are their JANG rates on
identical bytes?**

They agreed completely on the dense model and split on the MoE. On `JANG_4S`'s identical
3,207,385,506 bytes, vMLX led Osaurus on all three workloads in both visits — by **+27.5% /
+28.5%** on `decode`, +14.8% / +21.0% on `chat`, +7.9% / +6.3% on the `prefill` workload's decode
rate (dense `§5`). On `JANG_2L`'s identical 3,062,430,853 bytes the direction reversed on two of
three: Osaurus led by **+12.4% / +12.7%** on `chat` and **+27.1% / +25.0%** on the `prefill`
decode rate, while vMLX's prompt-processing throughput ran **+97.8% / +104.4%** ahead on the same
weights — and the `decode` row that carries the readings went from a 27.5% vMLX lead to a tie
(−0.34%) or a 4.70% vMLX lead depending on the visit (MoE `§1.4`, `§5`). Source tables: §4 below.

**3. Does the dense reading transfer to the MoE model (R4), or does the effect prove
model-specific?**

**R4 — split by model — is triggered.** The dense study measured a replicated lead in both
runtimes; the MoE study measured a tie in one and a replicated loss in the other, on the same two
runtimes, the same two axes and the same pin set. The dense decode reading did not transfer. What
transfers is the *density*, not the speed: `JANG_2L` carries 36% fewer bytes on disk and 16–31%
less peak footprint than the artifact that beat it, and buys no sustained-decode advantage in
either runtime (MoE `§6.4`, `§7.3`). R4's own limit travels with the reading and §5.6 states it:
the two studies changed **two** things at once — the model *and* the JANG profile (`JANG_4S` at
4.15 average bits against `JANG_2L` at 2.37) — so "model-specific" is the pre-registered reading,
and "MoE architecture is why" is a candidate rather than a measurement.

**4. What remains unattributed, and what is the exact next experiment?**

The ledger's residual is **packing vs kernel vs JIT** (design `§3.1a/c`). Both campaigns pinned
`--no-jit` and `--disable-native-mtp` off to isolate the format, so both measure a floor of the
vendor's shipped JANG path, and the loader's own lines name the pre-fix and the bit average but
never the kernel. The one clean separator the evidence does supply is measured, not deferred: on
identical bytes the two implementations differ by roughly 2× on prompt processing and by nothing
on decode, which places the prompt advantage in vMLX's *implementation of the format*, not in the
format (MoE `§6.3a`). The deferred single-variable follow-up is named in the design (`§3.1c`) and
unrun: **`--no-jit` against JIT inside vMLX on identical JANG weights** — one artifact, one
runtime, one flag. §7 frames it, with the rule that it may never be joined with either campaign's
grid (design `§3.6.3`).

### 1.2 The synthesis thesis: the JANG duality

The two studies do not disagree about JANG; they measure two different products wearing one name.
The bundle family's serving value flips with the model, and the flip is clean:

- **On dense `Qwen3.5-4B`, `JANG_4S` is a throughput winner.** It beats the best portable format
  on sustained decode in both runtimes at near-equal precision — 4.15 average bits against the
  stock artifact's uniform 4 — while carrying **4.8% more bytes** than that artifact (dense
  `§1.2`, `§6.1`). More bytes and more bits, faster decode: the lead cannot be a size effect, and
  it replicates in both loaders.
- **On MoE `LFM2.5-8B-A1B`, `JANG_2L` is a density winner.** It is 36.0% smaller on disk than the
  artifact that beat it on Osaurus decode and 38.7% smaller than `oq4`/`oq4e`, carries the
  campaign's smallest disk (3.06 GB against 4.78–5.47 GB) and its smallest footprint (30.5% under
  `stock4bit` in vMLX, 15.7% under it in Osaurus) — and on sustained decode it ties in vMLX (R3)
  and loses in Osaurus by a replicated 5.1% / 9.8% (MoE `§7.1`, `§7.3`). On this model the decode
  step's cost is not governed by the weight bytes, because a 36%-smaller bundle would otherwise
  not lose.

So the answer to "did JANG lead" is not yes or no; it is **per model, per workload, per runtime**,
and the two tables that carry it are §3 and §4. The single sentence this synthesis may publish:

> **Across two models and two independent implementations of the same format, in vMLX 1.6.59 and
> Osaurus 0.25.6 on one M2 Max, the JANG bundle's sustained-decode advantage is conditional on the
> model — present and replicated on dense `Qwen3.5-4B`, absent on MoE `LFM2.5-8B-A1B` — while its
> disk and memory-density advantage held in both studies, and its prompt-processing advantage is
> a property of one loader rather than of the bytes.**

### 1.3 What this synthesis is not allowed to say

Each of these is a rule doing its job, and each is stated in the studies it comes from:

- **Not that JANG is faster or slower in general.** Two models, two runtimes, one machine
  (design `§7`).
- **Not why beyond the readings.** The bundle and the loader travel together in every cell that
  produced a number (design `§3.1a/b`).
- **Not equal precision anywhere on the MoE.** `JANG_2L` is 2.37 average bits against portables at
  ~4, and the design pre-registered that comparison as "confounded with precision by
  construction" (design `§3.1a`; MoE `§8.7`).
- **Not the shipped vMLX JANG experience.** JIT and native MTP are off in every vMLX cell of both
  campaigns; the vendor's headline path is JIT-on, so every vMLX number here is a floor for it,
  not a replica of it (dense `§8.4`; MoE `§8.5`).
- **Not a cross-runtime memory or load ranking.** `peak_mb` is not one quantity across runtimes
  and a lazy loader's `cold_load_s` is a time-to-listening; no ordering is published by either
  (dense `§7.1`; MoE `§7.1`; design `§2.3`).
- **Not an accuracy claim.** Nothing in Track 1 speaks to what any format costs in quality. §8.4
  hands that to Track 2.

---

## 2. The test matrix and methodological basis

### 2.1 The two campaigns

Each model's campaign is two single-variable format-axis columns, one join, and one replication
pass over the cells that carry its claim (design `§2.1`–`§2.3`, `§5.3`, `§6.2`, `§6.3`).

| campaign | model | vMLX column | Osaurus column | join | replicates | rows |
|---|---|---|---|---|---|---|
| Plan 01-01, dense | `Qwen3.5-4B` | vmlx 1.6.59, 14:56:49–15:39:59, `results/grid-jang-dense/20260917T185649Z-format` | osaurus 0.25.6, 15:40:05–16:20:49, `…/20260917T194005Z-format` | `grid.md`, 16:20:54 | vMLX 16:20:54–16:38:19; Osaurus 16:38:24–16:56:45 | 36 rows (24 primary + 12 replicate), **36 PASS** |
| Plan 01-02, MoE | `LFM2.5-8B-A1B` | vmlx 1.6.59, 17:31:03–17:57:59, `results/grid-jang-moe/20260917T213103Z-format` | osaurus 0.25.6, 17:58:05–18:26:50, `…/20260917T215805Z-format` | `grid.md`, 18:26:55 | Osaurus 18:26:56–18:36:26; vMLX 18:36:32–18:45:55 | 42 rows (30 primary + 12 replicate), **40 PASS + 2 FAIL** |

Every PASS row names `n = 9` measured requests; no cell lost a visit in either campaign; both
runner logs end on the script's own success line with exit 0 (dense `§1.1`; MoE `§1.1`). The two
`FAIL`s are both Osaurus `decode` rows in the MoE campaign and are covered in §2.7.

**One structure difference between the campaigns belongs here**, because it bears on how the
cross-runtime rows may be read: the dense replicate ran vMLX before Osaurus, the same order as the
dense primary, so its pre-registered column-order reversal did **not** operate and the dense study
substituted a two-occasion replication argument (dense `§5`, `§8.2`). The MoE replicate ran
Osaurus first against a vMLX-first primary — the reversal as designed (MoE `§1.1`).

### 2.2 The matrices

`✓` = measured. The dense matrix has two structural holes, both measured in the v1 loadability
probes and both re-declared by the design before the campaign ran; the MoE matrix has none.

| label | dense: vMLX | dense: Osaurus | MoE: vMLX | MoE: Osaurus |
|---|---|---|---|---|
| `jang4s` | ✓ | ✓ | — | — |
| `jang2l` | — | — | ✓ | ✓ |
| `stock4bit` | ✓ | **—** § | ✓ | ✓ |
| `oq4` | ✓ | ✓ | ✓ | ✓ |
| `oq4e` | ✓ | ✓ | ✓ | ✓ |
| `optiq` | **—** ¶ | ✓ | ✓ | ✓ |
| cells per column | 4 | 4 | 5 | 5 |
| rows per column | 12 | 12 | 15 | 15 |

- **§** dense `stock4bit__osaurus` was never run: the artifact is listed by `GET /v1/models`
  and refused at request time as `not installed or registered with any provider` — offering is
  not serving (design `§2.2`).
- **¶** dense `optiq__vmlx` was never run: vMLX's multimodal path requires vision parameters the
  artifact's per-layer map omits (0 of 249 entries), a **format × runtime interaction** that is
  invisible on either axis alone (design `§2.1`). The MoE OptiQ loads in vMLX because
  `LFM2.5-8B-A1B` is text-only — `has_vision: false` in its JANG sibling's sidecar.

The hole that mattered most to this synthesis is the MoE matrix's completeness: five labels ran in
both runtimes, so every format-axis reading in §3 is against the same cast, and the MoE study
states the consequence — it is the first campaign in the project where the two runtimes sit in one
grid with no structural hole (MoE `§1.1`).

### 2.3 Artifacts, byte identity, and zero downloads

All ten artifacts were present on disk before either campaign; both studies re-verified snapshot
hashes and sizes at run time, and both record **zero downloads** (design `§4.4`; dense `§2.3`;
MoE `§2.3`). Totals: dense **16,640,647,100 B**, MoE **23,307,610,790 B**, combined
**39,948,257,890 B** (design `§4.2`).

The two JANG bundles, and what each declares about itself (sidecar digests re-verified on the day,
byte-identical to their design-time values):

| field | dense `JANG_4S` | MoE `JANG_2L` |
|---|---|---|
| snapshot | `4567967a46cd9e9bf26d3bb491ddd422ad607775` | `5fb82773427c2f25395de8821eff6d95e86feb53` |
| bytes on disk (measured) | 3,207,385,506 | 3,062,430,853 |
| `actual_bits` / widths / block | **4.15** / `[4, 6]` / 64 | **2.37** / `[2, 6, 8]` (+18 at 16) / 64 |
| architecture | `hybrid_ssm`, `has_vision: true` | `hybrid_moe_ssm`, `has_vision: false`, `has_moe: true` |
| `jang_config.json` sha256 | `3a9bf087…beebe2abcd` | `858385d1…1a26f610` |
| source of the row | dense `§2.3` | MoE `§2.3` |

Two provenance facts carried from the audits: **neither JANG bundle carries a `turboquant` block**
(so loader-level TurboQuant KV is not artifact-decided for either), and **neither carries a
`.vmlx-alignment.lock`** while most portables do. And one artifact-self-description trap the MoE
campaign measured rather than quoted: `JANG_2L`'s `config.json` declares uniform `bits=2,
group_size=64`, and the safetensors disagree on **67 modules**, a disagreement vMLX's loader
repairs from tensor shapes at load time (MoE `§2.3`, `§6.2`). No per-token byte model is derivable
from either sidecar, and neither study publishes one.

### 2.4 The pins, and the one that differed between campaigns

Read from the header line of each `results.jsonl` and printed by each grid's provenance block:

| pin | dense | MoE |
|---|---|---|
| `temperature` `0.0`, `seed` `0` | as designed | as designed |
| `warmup` `{plateau, window 5, floor 10, cap 20, 3.0%}` | 35 of 36 rows closed; 1 hit the cap | 40 of 42 rows closed; the 2 that hit the cap are the 2 FAILs |
| `measured` 9 batches, `concurrency` 1 | as designed | as designed |
| `cooldown_s` `30.0`, `prompt_tokens` `null` | as designed | as designed |
| **`cache_state`** | **`null` — the pin not taken** | **`"off"` on every row of all four runs** |
| vMLX `--no-jit`, `--disable-native-mtp`, `--disable-prefix-cache`, `--disable-block-disk-cache` | in every start command | in every start command |
| Osaurus residency 900 s + restore `cmp`-verified | yes | yes |
| per-cell `shasum` of the Osaurus settings files | **not taken** | **not taken** |

The cache pin is the campaigns' largest methodological difference and it changed what one workload
column is allowed to mean:

- **Dense**: `cache_state: null` is not a third state and is never to be read as `off`; it is the
  pin not taken. On vMLX this is provably a no-op (the start command is byte-identical either way,
  and this model's hybrid path has no backend to serve a hit from). On Osaurus it is visible in
  the data: every dense Osaurus `prefill` cell measured **prefix-cache lookups** — first requests
  3.4–3.7 s against 0.27–0.61 s for every one that followed, 566.0 MB of KV entries written to
  `~/.osaurus/cache/kv_v2/` while the column ran — so that column's `ttft_p50_s` and `prefill_tps`
  are not prefill figures, and **no cross-runtime `prefill` statement may use them**. Its
  `decode_tps`, the metric every table ranks by, is sound (dense `§4.3`).
- **MoE**: `cache_state: "off"` on every row, the host's cache keys toggled false for the whole
  campaign, and the behavioural check passed: every Osaurus prefill cell's first request is as
  fast as or faster than the ones after it, no collapsing sequence exists anywhere, and the
  campaign's `prefill` columns measure genuine prompt processing in both runtimes — which is what
  makes the MoE cross-runtime prompt comparison *legal* where the dense one is void (MoE `§2.2`,
  `§4.0`, `§5`).

The per-cell `shasum` gap is shared and stated: neither runner took digests between cells, so a
byte that moved outside the drift guard's 23 tracked keys would not be in either record; the pre/
post `cp -p` + `cmp -s` restoration is what both records carry (dense `§2.2`; MoE `§2.4`, `§8.6`).

### 2.5 Host handling and the byte-exact Osaurus restoration guarantee

Both campaigns ran the same discipline (design `§3.5`; dense `§2.4`; MoE `§2.4`):

1. `cp -p` backups of `~/.osaurus/config/server-runtime.json` and `server.json` taken before the
   first Osaurus cell.
2. `modelIdleResidencyPolicy.seconds` pinned to **900** for the campaign — a precondition, not an
   optimization: the host's own 30 unloads the model inside the 30 s cooldown, and the harness's
   start gate refuses a cell whose host disagrees (design `§3.5`).
3. For the MoE campaign additionally, both cache keys set **false** for the whole run.
4. Restore verified with **`cmp -s`**, not with the drift guard, on the normal path *and* on
   `INT`/`TERM`/`HUP` — the trap is in both runners (dense `scripts/run_jang_dense.sh:93`; MoE
   `scripts/run_jang_moe.sh:106`).
5. Four verified restores in the record: dense `runner.log:10`, `:154`; MoE `runner.log:9`,
   `:152`, each reading `osaurus settings restored byte-exact (cmp)`.

The guarantee holds as stated, and the evidence for it is the behavioural one: the host's files
read today carry the host's own values (`cache.prefix.enabled: true`, `cache.blockDisk.enabled:
true`, residency `30`) because the campaigns' state was restored byte-exact — which is also why
the MoE campaign's cache-off behaviour is evidenced by its TTFT sequences rather than by the files
as they sit now (MoE `§2.4`).

Ports and isolation were swept between every column in both campaigns (five ports plus stale
Osaurus apps, killed by full executable path, never by the name `osaurus`), and one runtime held
weights at a time throughout (dense `§2.4`; MoE `§2.4`).

### 2.6 Replication and the pre-registered decision rules

The rules were written before the data existed and are applied unchanged (design `§2.5`, `§3.7`):

- **Tie band.** Adjacent cells within **2.5%** are a tie, not an ordering — the largest gap v1
  observed to change places when the measurement window moved.
- **R-tie.** A JANG lead is published only if primary and replicate agree on direction *and* the
  gap clears 2.5% in both.
- **R-reproduce.** A replicate landing more than **5%** from its primary on the same cell is
  published with both figures and no ordering.
- **R-nothing.** No replicate may be discarded for being inconvenient.
- **R1/R2/R3/R4.** Replicated lead / loader-local lead / tie / split by model, with the
  vocabularies of §1.1.

How they fired: the dense replicate fired **R-reproduce on 9 of 12** cell pairs (dense `§8.3`);
the MoE replicate fired it on **1 of 12** (MoE `§8.1`). Every comparison either study publishes is
*within* a visit — two cells measured in the same session window, interleaved by the visit plan —
and what R-reproduce forbids is reading a single visit's level as "the bundle's rate on this
machine". This synthesis obeys that: the primary and replicate figures are printed side by side
wherever a reading turns on them, and no absolute level is quoted as a property of an artifact.

### 2.7 The floors: coherence, metrics, and the two FAILs

- **Coherence passed on every row of both campaigns**, including both FAILs. No cell in Track 1
  produced token salad; the standing rule — a fast cell that emits garbage is a failed cell, and
  no rate is published from one — never had to fire (design `§5.4`; dense `§1.1`; MoE `§1.1`).
- **The two MoE FAILs are metrics-floor failures, not coherence ones**: `oq4e__osaurus` and
  `optiq__osaurus` on `decode` produced ordinary prose (128 and 33 content deltas respectively),
  but Osaurus reported no usable completion-token count for the 512-token shape
  (`token_source='none'`), so `decode_tps` is undefined and no rate, ITL, drift or aggregate
  figure is read from either. The failure reproduces v1's `optiq__osaurus` decode FAIL and extends
  it to `oq4e`, which places its association with **Osaurus on the 512-token shape**, not with one
  quantization. Their `ttft_p50_s` and `prefill_tps` are arithmetic on two numbers that do not
  describe a prefill and must not be read (MoE `§4.1`, `§8.4`).
- **One dense row kept its place without closing its warmup window** —
  `stock4bit__vmlx` on `decode`, `warmup_plateau: false` at the cap — ranked and annotated, never
  dropped; if it is under-measured it is under-measured *low*, which widens the JANG lead rather
  than manufacturing it (dense `§3.1`).

---

## 3. Synthesis Finding 1: the format axis across dense and MoE

Both campaigns' format-axis columns rank by `decode_tps` (`report.DEFAULT_RANK`), per workload,
never pooled; every `L` below is JANG against that column's best non-JANG cell on the same
workload, computed from the one-decimal figures the leaderboards render (both studies verified the
rendered basis agrees with full precision to within 0.24 pp dense / 0.06 pp MoE, and that no
reading moves between bases — dense `§1.2`; MoE Appendix B).

### 3.1 Dense `Qwen3.5-4B` — `JANG_4S` leads both columns on decode

**The vMLX column** (source: dense `§3.1`):

| cell | `decode_tps` | JANG's lead over it | drift % | TTFT p50 s | ITL s | aggregate tok/s | peak MB |
|---|---|---|---|---|---|---|---|
| `jang4s__vmlx` | **54.2** | — | +5.9 | 0.185 | 0.0185 | 53.5 | 3820 |
| `oq4__vmlx` | 47.6 | **+13.9%** | +14.2 | 0.250 | 0.0210 | 46.2 | 3819 |
| `oq4e__vmlx` | 46.0 | +17.8% | +5.4 | 0.243 | 0.0218 | 42.3 | 3946 |
| `stock4bit__vmlx` | 44.2 | +22.6% | +16.6 | 0.277 | 0.0227 | 42.8 | 3843 |

The smallest gap in the column is 13.9% — five times the tie band — and the three portables
separate among themselves (47.6 > 46.0 > 44.2), so "best portable" is `oq4` legitimately rather
than by rounding.

**The Osaurus column** (source: dense `§4.1`):

| cell | `decode_tps` | JANG's lead over it | drift % | TTFT p50 s | ITL s | aggregate tok/s | peak MB |
|---|---|---|---|---|---|---|---|
| `jang4s__osaurus` | **42.5** | — | +5.1 | 0.297 | 0.0236 | 41.5 | 3400 |
| `oq4__osaurus` | 38.8 | **+9.5%** | +18.7 | 0.359 | 0.0258 | 39.3 | 2466 |
| `optiq__osaurus` | 38.7 | +9.8% | −1.0 | 0.316 | 0.0259 | 37.7 | 2472 |
| `oq4e__osaurus` | 38.6 | +10.1% | +6.2 | 0.335 | 0.0260 | 38.0 | 2216 |

Here the three portables behind JANG are a **tie** — 38.8 / 38.7 / 38.6, a 0.52% span — so the
grid's ranks 2/3/4 are the renderer's and not the measurement's claim (dense `§4.1`).

### 3.2 MoE `LFM2.5-8B-A1B` — `JANG_2L` leads neither column on decode

**The vMLX column** (source: MoE `§3.1`):

| cell | `decode_tps` | JANG's lead over it | drift % | TTFT p50 s | ITL s | aggregate tok/s | peak MB |
|---|---|---|---|---|---|---|---|
| `jang2l__vmlx` | **116.3** | — | +0.5 | 0.098 | 0.0086 | 113.8 | 3624 |
| `stock4bit__vmlx` | 115.3 | **+0.87%** | +3.9 | 0.116 | 0.0087 | 112.5 | 5214 |
| `optiq__vmlx` | 100.6 | +15.6% | +6.1 | 0.125 | 0.0100 | 99.2 | 5869 |
| `oq4e__vmlx` | 97.0 | +19.9% | +10.9 | 0.138 | 0.0103 | 98.1 | 5416 |
| `oq4__vmlx` | 65.6 | +77.3% | +76.0 | 0.196 | 0.0153 | 73.6 | 5415 |

The top pair is **0.87% apart — a tie**; the apparent "JANG is 1st" is a rank number, not a
claim. Behind them the portables do separate (`stock4bit` 12.75% ahead of `optiq`, which is 3.58%
ahead of `oq4e`, which is 32.37% ahead of a `oq4` cell whose +76.0% drift says its window closed
while it was still climbing, so 65.6 narrates its window more than its artifact — MoE `§3.1`).

**The Osaurus column** (source: MoE `§4.1`):

| cell | `decode_tps` | JANG's lead over it | drift % | TTFT p50 s | ITL s | aggregate tok/s | peak MB |
|---|---|---|---|---|---|---|---|
| `stock4bit__osaurus` | **123.0** | **−5.12%** | +5.9 | 0.221 | 0.0081 | 118.8 | 4542 |
| `jang2l__osaurus` | 116.7 | — | +3.2 | 0.221 | 0.0086 | 112.1 | 3829 |
| `oq4__osaurus` | 115.8 | **+0.78%** | +2.6 | 0.230 | 0.0087 | 110.8 | 4497 |
| `oq4e__osaurus` | **FAIL** | — | — | — | — | — | 4501 |
| `optiq__osaurus` | **FAIL** | — | — | — | — | — | 4749 |

Two readings in one table: `stock4bit` leads JANG by 5.12%, and `jang2l` against `oq4` is 0.78% —
a **tie** — so the only publishable ordering below the leader is "`stock4bit` ahead of the rest,
and the rest tied among themselves" (MoE `§4.1`). The two FAILs are §2.7's.

### 3.3 The full `L` matrix — all twelve readings, both models

Rendered-basis `L`, primary / replicate, with the verdict each pair earns under R-tie. Sources:
dense `§3.1`–`§4.4`; MoE `§3.1`–`§4.4`.

**Dense `Qwen3.5-4B` / `JANG_4S`:**

| workload | vMLX `L` (pri / rep) | vMLX verdict | Osaurus `L` (pri / rep) | Osaurus verdict |
|---|---|---|---|---|
| `decode` (512 tok) | **+13.9% / +16.8%** | **R1 — replicated lead** | **+9.5% / +9.0%** | **R1 — replicated lead** |
| `chat` (128 tok) | −8.8% / +14.7% | sign reversal → **no ordering** | +8.6% / −1.8% | one visit inside the band → **tie** |
| `prefill` (64 tok) | −0.8% / +7.9% | one visit inside the band → **tie** | +6.1% / +1.0% | **tie** (and both rows are lookups — see §4.4) |

**MoE `LFM2.5-8B-A1B` / `JANG_2L`:**

| workload | vMLX `L` (pri / rep) | vMLX verdict | Osaurus `L` (pri / rep) | Osaurus verdict |
|---|---|---|---|---|
| `decode` (512 tok) | +0.87% / −0.50% | **R3 — tie** (both visits inside the band) | **−5.12% / −9.80%** | replicated `stock4bit` lead |
| `chat` (128 tok) | −2.86% / +0.60% | sign reversal → **no ordering** | **−11.07% / −3.71%** | replicated `stock4bit` lead |
| `prefill` (64 tok) | −10.42% / −0.50% | one visit inside the band → **tie** | **−11.16% / −9.86%** | replicated `stock4bit` lead |

Two workload-level facts sit outside `L` because the ranking metric is `decode_tps` on every
shape, and both belong in this matrix:

- **The MoE column's prompt-processing advantage is not a decode `L`.** On the `prefill` workload,
  `jang2l`'s first token arrives in 0.812 s (1,643.4 prompt tok/s) against `stock4bit`'s 1.245 s
  (1,069.7) in the primary — **+53.6%** prompt throughput and a first token **0.433 s sooner** —
  and the replicate reproduces the direction at **+38.4%** (0.783 s / 1,705.6 against 1.081 s /
  1,232.2). It is the one place in the MoE campaign where `jang2l` is unambiguously ahead of the
  artifact that beat it on decode, and its magnitude moved 15.2 pp between the two visits that
  measured it (MoE `§3.3`–`§3.5`).
- **The dense column's prompt side is real but not an `L` either**: `jang4s__vmlx` reaches the
  first token of the 1,314-token prompt in 2.450 s (536.3 tok/s of genuine prompt processing)
  against `stock4bit`'s 2.834 s (463.6) and `oq4`'s 3.570 s — while the 64-token decode metric
  JANG is ranked by is a 0.8% tie with `stock4bit`. The dense Osaurus prompt figures are lookups
  and cannot be read at all (dense `§3.3`, `§4.2`–`§4.3`).

### 3.4 What the matrix licenses

- **On dense, the format axis produces one published ordering and it is JANG's**: a replicated
  decode lead in both runtimes, with the other two workloads left as ties or as a sign reversal
  the replicate exposed (dense `§1.3`).
- **On the MoE, the format axis produces published orderings that are all for `stock4bit`**:
  a replicated lead in Osaurus on all three workloads and a tie in vMLX on the one that carries
  the reading (MoE `§1.2`, `§4.4`).
- **`chat` never produced an ordering that favors JANG, in any of the four columns.** In dense
  vMLX the comparison *reversed sign* between visits (the primary's `stock4bit` number was a cell
  in thermal decline — early median 63.4 tok/s against a late 47.7, drift −24.7%); in dense
  Osaurus the primary lead fell inside the band in the replicate; in MoE vMLX it reversed
  explicitly (−2.86% → +0.60%); and in MoE Osaurus it produced a **replicated lead for
  `stock4bit`** (−11.07% / −3.71%). Three non-orderings and one ordering against JANG, and the
  rules that produced them are the same rules that produced the R1 lead — which is the point of
  pre-registering them.
- **The tie band did real work in both directions.** It demoted a within-band "lead" (dense
  Osaurus `chat`'s +8.6%) and it elevated a marginal-looking gap to an unresolvable tie (MoE vMLX
  `decode`'s +0.87%, where the sign then reversed at −0.50%).

---

## 4. Synthesis Finding 2: the runtime axis on identical bytes

Study 1C holds the artifact constant and varies the loader: one row per model, the same bytes in
two independent implementations, nothing re-measured for it. Byte identity is confirmed on both
sides — `disk_bytes` is constant on every JANG row of every run of each campaign, at one snapshot
revision per model (dense `§5`; MoE `§5`).

### 4.1 Dense: vMLX leads every workload, by 27.5–28.5% on decode

`JANG_4S`, 3,207,385,506 B in all four runs:

| workload | vMLX primary | Osaurus primary | vMLX lead | vMLX replicate | Osaurus replicate | vMLX lead |
|---|---|---|---|---|---|---|
| `decode` | 54.2 | 42.5 | **+27.5%** | 59.1 | 46.0 | **+28.5%** |
| `chat` | 55.2 | 48.1 | +14.8% | 60.0 | 49.6 | +21.0% |
| `prefill` (decode rate) | 60.2 | 55.8 | +7.9% | 62.7 | 59.0 | +6.3% |

Supporting `decode` figures, both primary: TTFT p50 0.185 s against 0.297 s, ITL 0.0185 s against
0.0236 s, aggregate 53.5 against 41.5 tok/s — vMLX ahead on every one of them, widest on the
metric that matters most for sustained generation (dense `§5`).

What the row does and does not establish is worth restating in the studies' own terms: it
establishes *that two loaders given identical weights do not produce the same number*; it cannot
attribute the difference to anything inside either implementation, because loader, scheduler,
Metal usage, KV handling and memory accounting all differ between the runtimes and the row moves
them at once (dense `§5`). The dense column-order deviation (§2.1) means this row's replication
was not the pre-registered reversal; the substitute evidence is that two orderings of the same
pair taken at different points in a session in which the twelve replicated cells moved −13.6% to
+14.5% produce +27.5% and +28.5% — a 1.0 pp spread (dense `§5`, `§8.2`).

### 4.2 MoE: the direction splits by workload

`JANG_2L`, 3,062,430,853 B in all four runs:

| workload | vMLX primary | Osaurus primary | vMLX lead | vMLX replicate | Osaurus replicate | vMLX lead |
|---|---|---|---|---|---|---|
| `decode` | 116.3 | 116.7 | **−0.34%** (tie) | 120.4 | 115.0 | **+4.70%** |
| `chat` | 112.2 | 126.1 | −11.02% | 117.4 | 132.3 | −11.26% |
| `prefill` (decode rate) | 97.1 | 123.4 | −21.31% | 99.5 | 124.4 | −20.02% |
| `prefill` (prompt tok/s) | **1,643.4** | 830.9 | **+97.8%** | **1,705.6** | 834.3 | **+104.4%** |

Supporting `decode` figures, both primary: TTFT p50 0.098 s against 0.221 s, ITL 0.0086 s against
0.0086 s (identical), aggregate 113.8 against 112.1 tok/s, peak 3624 against 3829 MB (MoE `§5`).

**The `decode` row publishes no ordering.** The primary's −0.34% is inside the band and the
replicate's +4.70% is outside it in the other direction, so R-tie is not satisfied — neither
condition holds across the pair — and what is published is both numbers with the tie named on the
primary (MoE `§5`). Measured as Osaurus relative to vMLX (the opposite convention to the table's
`vMLX lead` column, stated so the two cannot be confused), Osaurus's JANG cell is **+12.4% /
+12.7%** ahead on `chat` and **+27.1% / +25.0%** ahead on the `prefill` workload's 64-token
rate, while vMLX's prompt processing is **+97.8% / +104.4%** ahead on the same bytes — every one
of those a wide margin, and none of them the 512-token sustained decode rate that carries §3.

### 4.3 The reversal, side by side

| workload | dense `JANG_4S`: who leads, pri / rep | MoE `JANG_2L`: who leads, pri / rep |
|---|---|---|
| `decode` (512 tok) | **vMLX**, +27.5% / +28.5% | **no ordering** (tie, then vMLX +4.70%) |
| `chat` (128 tok) | **vMLX**, +14.8% / +21.0% | **Osaurus**, +12.4% / +12.7% |
| `prefill` (decode rate) | **vMLX**, +7.9% / +6.3% (decode-rate basis stands; the dense Osaurus TTFT/prefill figures are lookups and are void) | **Osaurus**, +27.1% / +25.0% |
| `prefill` (prompt tok/s) | not computable — dense Osaurus measured lookups | **vMLX**, +97.8% / +104.4% |

Three measured statements follow, and only the first is a property of the bytes:

1. **The vMLX-vs-Osaurus JANG difference is not a property of the loaders alone.** A 27.5% gap on
   one artifact and a tie-or-4.7% gap on another, measured by the same harness on the same machine
   within hours of each other, says the pair's behaviour is **artifact-dependent** (MoE `§5.1`).
   This is the cross-study result that single-runtime studies cannot produce, and it is the reason
   Study 1C was designed into both campaigns.
2. **On the MoE, Osaurus's JANG implementation leads on everything before the first token**
   (`chat` and the prefill decode rate), while vMLX's loader owns long-prompt ingestion on the
   same weights. On the dense, vMLX owned all three.
3. **The loader/runtime pair is not separable and nothing here cuts it.** Attribution stays at
   "the two implementations differ, by this much, on identical bytes" (design `§2.3`).

A *hypothesis* the two rows suggest, labelled as one because no measurement in either campaign
tests it: vMLX's strength appears on sustained decode of dense uniform packing and on long prompt
ingestion, and Osaurus's appears on per-request dispatch latency — its `chat` and prefill-decode-
rate leads on the MoE sit beside the campaign's lowest prefill TTFT (1.603 s, its own cell) and its
smallest bundle (3.06 GB, the `jang2l` artifact). Whether the split follows the loader's language,
its scheduler, its Metal usage or its kernel selection cannot be read from these records, and the
studies decline to name a cause; this synthesis does too. Hypotheses are cheap and this one is not
evidence.

### 4.4 The limits that ride on both rows

- **`cold_load_s` and `peak_mb` may not be read across a row.** `report.CROSS_RUNTIME_UNCOMPARABLE`
  prints its reason above any runtime-axis ordering by either: vMLX reports a footprint within a
  few percent of the weight bytes and Osaurus roughly half of them, and a load a runtime defers
  past readiness is a time-to-listening. A cross-runtime load comparison uses the **sum**
  (dense `§5`, `§7`; MoE `§5`, `§7.1`).
- **The dense `prefill` cross-runtime row is a decode-rate row only.** Its TTFT and prefill
  throughput are lookups on the Osaurus side and void (dense `§4.3`). The MoE row is the first
  place in the project where a cross-runtime prompt comparison is legal, because both columns
  prefilled every request (MoE `§5.3`).
- **Sampling defaults ride along across runtimes.** The harness pins `temperature` and `seed` and
  does not send `top_p` or `repetition_penalty` (`transport.py:155-163`); within a column this is
  a constant and every format-axis reading is unaffected, but across the JANG row it rides with
  the loader. The vMLX logs show the server resolving `top_p: 1.0` per request; no equivalent
  record exists for Osaurus's defaults (MoE `§8.6`).
- **Two cells per row is a comparison, not an ordering** — reported with both numbers, the tie
  band and the replication rule applied (design `§2.3`). §4.1 and §4.2 do exactly that.

---

## 5. Architectural attribution: dense uniformity vs MoE routing dynamics

The design's question (`§3.1`) is whether JANG's speed is the weights or the thing that loads the
weights. Across the two campaigns the evidence supports one **measured** statement, reframes one
dispatch-level claim, and leaves one mechanism where it belongs — a candidate.

### 5.1 Dense: size is eliminated, and that is the cleanest result in Track 1

| artifact | declared bits | widths | block | bytes on disk | GiB |
|---|---|---|---|---|---|
| `jang4s` (`JANG_4S`) | **4.15** | `[4, 6]` | 64 | **3,207,385,506** | 2.987 |
| `stock4bit` | 4.0 (uniform) | — | — | 3,061,131,520 | 2.851 |
| `oq4` | ~4 (mixed) | — | — | 3,160,559,814 | 2.944 |
| `oq4e` | ~4 (mixed) | — | — | 3,167,949,891 | 2.950 |

The JANG bundle is **4.8% larger than the uniform-4-bit artifact** and 1.5% larger than `oq4`,
and it declares more average bits. A decode lead that holds while carrying more bytes and more
bits cannot be a size effect and cannot be a fewer-bytes-per-token effect. This is the one
near-equal-precision comparison in the whole artifact set (dense `§6.1`; design `§3.1a`).

### 5.2 Dense: what remains — packed mixed-bit layout and the kernel path that consumes it

Two mechanisms survive, and they travel together in every cell that produced a lead:

1. **The weight layout.** The bundle is per-tensor assigned (`bit_widths_used: [4, 6]`, block 64,
   asymmetric, `mx.quantize`), and its geometry is not what a generic loader expects: three
   independent runtimes refuse it with the byte-identical error
   `Expected shape (248320, 640) but received shape (248320, 320) for parameter
   language_model.model.embed_tokens.weight` — a **packed half-width embedding**, measured from
   the artifact, not a documentation claim. What vMLX does with it is a loader step the portables
   do not take: `Pre-fixed 217 module(s) with mixed-precision bit widths`, logged on every JANG
   load while the portables log the generic loader line instead (dense `§6.3`).
2. **The kernel path that layout selects.** vMLX ships family-specific fused Metal kernels for
   this model family and its JANG-affine path is explicitly a compile-eligible decode path — but
   which kernels ran for this bundle **is not observable in these records**, and the study pinned
   the one switch that would have let a reader see compilation happen (dense `§6.3`).

The dense study's own dispatch attributed the lead to "custom Metal kernel unpacking and packed
half-width embeddings"; the study narrowed that, and this synthesis keeps the narrowing: the
half-width packing is evidenced from the artifact, the mixed-width pre-fix is evidenced in the
loader trace, and **kernel selection is the part the artifact set cannot separate from packing**.

### 5.3 MoE: routing dynamics is the candidate, and it is not measured

On the MoE the question has a different shape, because there is **no equal-precision pair at all**
(2.37 average bits against ~4, on a bundle 36–44% smaller):

- **Measured, and it cuts against the size story**: the 36%-smaller bundle decoded **5.1–9.8%
  slower** in Osaurus and tied in vMLX. If the decode step were dominated by streaming weight
  bytes, the smaller bundle could not lose — so on this model the time is going somewhere the
  artifact's size does not govern (MoE `§6.1`).
- **Candidate, not measured**: `LFM2.5-8B-A1B` routes **4 of 32 experts per token**
  (`num_experts: 32`, `num_experts_per_tok: 4`, from the artifact's own `config.json`), so the
  expert weight stream is fragmented across 32 modules and any per-module unpack or layout cost is
  paid many times per token. A per-token cost that is not proportional to total weight bytes is
  exactly what "36% smaller, 5–10% slower" looks like — and a routed MoE is a plausible reason a
  quantized bundle's byte savings stop converting into decode throughput.
- **What the campaign says it cannot test**: three things would be needed and none is present — a
  dense model at ~2.4 bits measured in the same runtimes with the same harness; a per-module bit
  map for this bundle (the `config.json` declares uniform 2-bit and the loader itself repairs 67
  modules from shapes); or a kernel-level trace, which is not emitted. The MoE study states this
  and so does this synthesis: **"dense JANG won, MoE JANG did not" is a true statement about two
  bundles on two models and is not a measurement of expert routing, of 2.37-bit precision, or of
  kernel overhead as a single variable** (MoE `§6.3c`).

### 5.4 The measured separator: the prompt advantage is implementation-specific

The strongest attribution fact Track 1 produced is a comparison of identical bytes. On `JANG_2L`
at 3,062,430,853 B:

| metric | same bytes in vMLX | same bytes in Osaurus | reading |
|---|---|---|---|
| prompt processing (prefill tok/s) | 1,643.4 / 1,705.6 | 830.9 / 834.3 | **~2x difference** |
| sustained decode (`decode_tps`) | 116.3 / 120.4 | 116.7 / 115.0 | **no difference** |

The 2.37-bit arithmetic is fixed in both runtimes; the loaders are not; and the loaders produce a
2× difference on one metric and none on another. **Whatever produced vMLX's prompt-processing
advantage is in vMLX's implementation of the format, not in the format** (MoE `§6.3a`). That
directly limits the sentence "2.37 bits delivered +53.6% prompt throughput" (the dispatch-level
phrasing): the identical bits deliver **+0.8% / +2.8%** in Osaurus on the same machine, so a
format-intrinsic byte explanation is insufficient — the bits are necessary at most and are not
sufficient. The direction of the effect (fewer bytes per weight read during ingestion) remains a
plausible mechanism; the magnitude belongs to vMLX's loader.

### 5.5 The prefill-vs-decode split, stated carefully

Why may an advantage exist on the prompt and not on the generation? Prompt processing reads each
weight once per prompt against all tokens in parallel; decode reads (a subset of) the weights once
per token. A bundle with fewer bytes per weight can therefore help ingestion while a per-token
unpack or gather cost — paid on every generated token, fragmented across expert modules — offsets
its byte savings during generation. That is the candidate's shape, and it is consistent with the
MoE numbers in both columns. Three limits keep it a candidate rather than a finding:

- **The magnitude is not stable**: the vMLX prompt advantage moved 15.2 pp between the two visits
  that measured it (+53.6% → +38.4%), while the direction replicated (MoE `§3.5`).
- **The runtime control falsifies the simple version**: identical weights give +0.8% / +2.8% in
  Osaurus. A property of the artifact would not need the loader (MoE `§3.5`, `§4.3`).
- **It is not a decode advantage, and no reader may read it as one** — the same MoE row's 64-token
  decode rate is the one that loses to `stock4bit` in both visits (MoE `§3.3`–`§3.4`).

### 5.6 The confound on the cross-model comparison itself

R4's naming is "split by model", and that is what the evidence supports — but the two halves of
Track 1 changed **two** things between their columns: the model (`Qwen3.5-4B`, dense hybrid SSM,
against `LFM2.5-8B-A1B`, 32-expert MoE) **and** the JANG profile (`JANG_4S` at 4.15 average bits
with widths `[4, 6]` against `JANG_2L` at 2.37 with widths `[2, 6, 8]` and 18 passthrough-16
tensors) — two profiles from the same quantiser family, not two settings of one artifact. So
"model-specific" is the pre-registered reading, and any explanation that names expert routing is
naming a candidate. Separating the two variables needs a dense model at ~2.4 bits or a MoE at
~4.15 bits, measured with the same harness and pins; neither exists in this campaign and neither
is scheduled (MoE `§6.3`, `§8.3`).

### 5.7 Attribution this synthesis may publish

In the design's own vocabulary, for the two campaigns together:

> *On `Qwen3.5-4B` and `LFM2.5-8B-A1B`, in vMLX 1.6.59 and Osaurus 0.25.6, the JANG bundles'
> decode-rate outcome is model- and bundle-specific: `JANG_4S` led the best portable format in
> both runtimes by a replicated 9.0–16.8% while carrying 4.8% more bytes than the uniform-4-bit
> artifact, and `JANG_2L` tied `stock4bit` in vMLX and lost to it in Osaurus by a replicated
> 5.1–9.8% while carrying 36% fewer bytes; the `JANG_2L` prompt-processing advantage is
> implementation-specific (roughly 2× in vMLX, +0.8–2.8% in Osaurus on identical bytes) and no
> measurement here separates packing, kernel selection, or the pinned-off JIT from each other or
> attributes the cross-model difference to MoE routing rather than to the two bundles themselves.*

---

## 6. The unified resource economy: throughput vs memory footprint vs disk

### 6.1 The trade, per model

| | dense `Qwen3.5-4B`, `JANG_4S` | MoE `LFM2.5-8B-A1B`, `JANG_2L` |
|---|---|---|
| bytes on disk | 3,207,385,506 (2.987 GiB) | 3,062,430,853 (2.852 GiB) |
| vs `stock4bit` | **+4.8%** (+146.3 MB) | **−36.0%** (−1.72 GB) |
| vs the column's best portable on decode | +1.5% vs `oq4` | −36.0% vs `stock4bit`; −38.7% vs `oq4`/`oq4e`; ≈−44% vs `optiq` |
| peak footprint, `decode` (vMLX) | 3820 MB — not the largest of its four cells (3819/3820/3843/3946) | **3624 MB — 30.5% under `stock4bit`'s 5214** |
| peak footprint, `decode` (Osaurus) | 3400 MB — the largest of its four cells (2216/2466/2472/3400) | **3829 MB — 15.7% under `stock4bit`'s 4542** |
| **sustained decode outcome** | **+13.9 / +16.8% (vMLX); +9.5 / +9.0% (Osaurus)** | **tie (vMLX, R3); −5.12 / −9.80% (Osaurus)** |
| prompt-processing outcome | vMLX: 536.3 tok/s at 2.450 s TTFT against `stock4bit`'s 463.6 at 2.834 s, while the 64-token rank metric is a 0.8% tie with it (+11.9%/+18.5% over `oq4`/`oq4e` on that metric); Osaurus: not readable — lookups | **vMLX: +53.6 / +38.4%; Osaurus: +0.8 / +2.8%** |

Sources: dense `§3.1`, `§3.3`, `§4.1`, `§6.1`, `§7.1`; MoE `§3.1`, `§3.3`–`§3.5`, `§4.1`–`§4.4`,
`§7.1`. Memory cell counts are the four/five cells of each column's decode workload.

### 6.2 Dense: speed at a 4.8% disk premium, at near-equal precision

The dense bundle is the *larger* artifact of its decisive pair and the faster one, and there is no
size story to tell in either direction: +146.3 MB (+4.8%) buys a replicated 9–17% decode lead,
and the bundle's footprint within vMLX carries no penalty (3820 MB is not the largest of the
column's four decode cells). The dense study published no format-axis memory reading at all —
vMLX's four decode cells sit inside 127 MB of each other, and the Osaurus column's spreads are
dominated by the runtime's own accounting rather than by the weights (dense `§7.1`). The dense
memory question is therefore open, and this synthesis does not open it further: the numbers are
in the table above and no claim is published from them.

### 6.3 MoE: density at a 36% disk and 16–31% memory discount

This is the campaign's clearest JANG result and it is a format-axis reading, which is what
Studies 1A/1B publish (MoE `§7.1`, `§7.3`):

- **Disk**: `JANG_2L` saves **1.72 GB** against the artifact that beat it on Osaurus decode; the
  MoE artifact set totals 23,307,610,790 B and `jang2l` is **13.1%** of it.
- **Memory**: 3,624 MB against 5,214 MB in vMLX (**30.5% less**, and 38.3% under `optiq`'s
  5,869 MB); 3,829 MB against 4,542 MB in Osaurus (**15.7% less**). The replicate agrees within
  1 MB and 21 MB — the tightest cell-to-cell agreement in the campaign.
- **Throughput**: nothing is bought on sustained decode (tie in vMLX, 5.1–9.8% slower on
  Osaurus). A prompt-heavy workload gets vMLX's 1.5–1.6× prompt throughput on top of the density
  — a combination no other artifact in the campaign offers, with a magnitude that moved 15.2 pp
  between the two visits that measured it.

Put plainly, in the MoE study's own words: **on this model the JANG bundle's value is density,
not sustained-decode throughput** (MoE `§7.3`). A reader constrained by memory or disk gets 30%
(vMLX) or 16% (Osaurus) of their footprint back and 36% of the disk; a reader constrained by
tokens per second on a long generation gets nothing over `stock4bit` in vMLX and loses in Osaurus.

### 6.4 Cold start: two numbers, never one

A runtime that loads weights before readiness and one that defers the load past readiness do not
produce the same quantity, so the only comparable figure is the **sum** (design `§5.5`; dense
`§7.2`; MoE `§7.2`):

| runtime / campaign | `cold_load_s` | `first_request_s` | sum |
|---|---|---|---|
| vMLX, dense | 7.06–7.08 (primary), 7.08 / 8.11 (replicate) | 1.68–2.17 (primary), 1.69 / 1.79 | **8.76–9.24 s**; replicate 8.87–9.80 s |
| Osaurus, dense | 1.25–1.29 (primary), 1.25 / 1.28 | 2.99–4.71 (primary), 2.77 / 2.92 | **4.27–5.96 s**; replicate 4.02–4.20 s |
| vMLX, MoE (`jang2l` / `stock4bit`) | 7.10 / 7.09; replicate 8.11 / 7.08 | 1.19 / 1.22; replicate 1.23 / 1.21 | **8.29 / 8.31 s**; replicate 9.34 / 8.29 s |
| Osaurus, MoE (`jang2l` / `stock4bit`) | 1.27 / 1.30; replicate 1.28 / 1.27 | 2.76 / 3.51; replicate 2.31 / 2.04 | **4.03 / 4.81 s**; replicate 3.59 / 3.31 s |

Three things this table does *not* license: ranking on `cold_load_s` alone (it would name Osaurus
5.5–6.3× the faster loader, which is a time-to-listening, not a cold start); reading any cell
across a runtime boundary by anything but the sum; and ignoring the one outlier both studies name
rather than smooth — `jang2l__vmlx`'s replicate load of **8.11 s**, about 14% above every other
vMLX load of the same session, on a metric no reading turns on (MoE `§7.2`). One JANG-specific
load advantage does survive inside a column: `jang2l` is the **fastest cell to first token in both
Osaurus visits** (4.03 s against 4.16 / 4.74 / 4.81 / 5.20 in the primary), which is what a
36%-smaller bundle that the runtime's loader reads natively should look like (MoE `§7.2`).

### 6.5 The non-comparabilities, restated once

- **Peak memory is not one quantity across runtimes.** vMLX reports a footprint well above the
  weight bytes; Osaurus reports roughly half of them because it holds weights in wired, GPU-pinned
  pages that `phys_footprint` charges differently. Every within-column reading above is legal;
  no cross-runtime memory ordering is (dense `§7.1`; MoE `§7.1`;
  `2026-09-16-footprint-is-not-one-quantity.md`).
- **A third cost neither campaign intended to measure**: the Osaurus disk cache is not just the
  dense campaign's confound — it held ~11 GB and gained 566.0 MB during one 40-minute column, and
  nothing in the harness clears or reports it. A runtime's on-disk cache is part of its measured
  conditions, and a study that does not pin it measures whatever the last session left behind
  (dense `§7.3`). The MoE campaign's cache-off protocol is the fix, and §2.4 records that it
  worked.

---

## 7. The confound ledger and the next experiment

### 7.1 The design's ledger, item by item, as the two campaigns discharged it

The design's confound ledger (`§3.3`, twelve items) is the checklist this section closes. "Pinned"
means the mechanism was fixed and the evidence is in the record; "declared" means it has no pin
and every affected number is published beside it.

| # | confound | dense campaign | MoE campaign |
|---|---|---|---|
| 1 | **Precision/size** | the near-equal-precision pair (4.15 vs 4.0 bits, JANG +4.8% bytes) resolves it for the decisive comparison; no equalization elsewhere | **no equal-precision pair exists**; 2.37 vs ~4 bits, declared beside every rate |
| 2 | **Auto-JIT on affine bundles** | pinned `--no-jit`; the JIT warmup line is absent from all 12 vMLX logs | pinned; absent from all 14 vMLX logs |
| 3 | **MTP heads in the bundle** | pinned `--disable-native-mtp`; the skip line present per request (the dense bundle ships an MTP head) | flag present but **inert** — neither MoE bundle ships an MTP head, so the absence of the log line is not evidence the flag was dropped (MoE `§8.5`) |
| 4 | **Loader-level TurboQuant KV** | neither sidecar carries a `turboquant` block; the KV codec is the harness env-var path, line captured | same, plus the SSM-specific `prefix cache disabled` line once per visit |
| 5 | **Osaurus host settings** | toggled where needed, restored `cmp`-verified; **per-cell digests not taken** | cache keys false for the campaign, restored `cmp`-verified; **per-cell digests not taken** — a shared gap |
| 6 | **Idle residency** | 900 s pinned, restored (host's own 30) | same |
| 7 | **Prefix/KV cache** | **`cache_state: null` — the pin not taken**; vMLX provably unaffected; Osaurus `prefill` measured lookups → its TTFT/prefill throughput void, decode sound | **`cache_state: "off"` on every row**; behavioural check passed in both columns; genuine prefills everywhere |
| 8 | **Warmup** | plateau rule; 1 row hit the cap and kept its place | plateau rule; the 2 rows that hit the cap are the 2 FAILs |
| 9 | **Thermal/session drift** | visits with 30 s cooldowns; drift annotations; **replicate column order not reversed** (substitute evidence stated); R-reproduce fired 9/12 | visits with cooldowns; **replicate order reversed as designed**; R-reproduce fired 1/12 |
| 10 | **Cross-runtime load/memory** | not comparable; no ordering published | not comparable; no ordering published |
| 11 | **Per-model thinking switches** | **not recorded** — an open gap in that campaign's evidence | checked post hoc: 15 `model_options_*` plist keys and none is any of the campaign's five ids — the confound is uniform rather than absent |
| 12 | **Runtime version** | vmlx 1.6.59, osaurus 0.25.6 on every row | same two versions on every row |

Sources: design `§3.3`; dense `§2.2`, `§2.5`, `§8`; MoE `§2.2`, `§2.5`, `§8`.

### 7.2 What remains unattributed: packing vs kernel vs JIT

Both campaigns pinned **`--no-jit` and `--disable-native-mtp`** in every vMLX start command, by
design, so that the JANG cell differs from its column only in its bytes — and both studies say
what that means: the vendor's headline decode path is JIT-on (and the dense bundle ships an MTP
head), so **every vMLX number in Track 1 is a floor for the shipped JANG path, not a measurement
of it** (dense `§8.4`; MoE `§8.5`). Inside that floor, the loader's own lines name the pre-fix
(`Pre-fixed 217 module(s)` dense; `patched 67 module(s)` MoE) and the bit average, never the
kernel. So three candidates remain entangled in every cell that produced a lead:

| candidate | status after Track 1 |
|---|---|
| **Packing** — mixed-bit layout, packed half-width embeddings | evidenced from the artifact (the three-runtime shape refusal) and the loader trace; not separable from kernel selection |
| **Kernel selection** — the fused Metal path that consumes that layout | not observable in these records; JIT is pinned off so the compile-and-warmup trace cannot appear |
| **JIT / MTP accelerators** — `mx.compile`, native MTP heads | pinned off in both campaigns; named, unmeasured; the deferred A/B prices exactly this |

### 7.3 The next experiment: the vMLX JIT A/B

The design named it before any data existed (`§3.1c`, `§6.5`) and both studies leave it named and
unrun: **`--enable-jit` against `--no-jit` inside vMLX, artifact and runtime constant, on the JANG
weights themselves.** Why it is the right next experiment, in the campaigns' own reasons:

- It is the cheapest experiment the project will ever have: one flag, one artifact, one runtime
  (dense `§8.4`).
- It is a **legal single-variable pair**: the weights are constant and the accelerator moves — the
  design's one deferred separator for runtime-pin causes.
- It prices the thing both campaigns pinned off, and the MoE result makes it more interesting than
  it was in dense: vMLX's JANG cell posts a 1.5–1.6× prompt-processing advantage **with JIT off**
  and no decode advantage at all, so the A/B measures an accelerator whose margin is currently
  unmeasured in both directions (MoE `§8.5`).
- **It does not separate packing from kernel** — it moves the accelerator, not the layout — so the
  ledger's first two candidates stay entangled even after it runs (dense `§6.3`).

Three constraints travel with it and none is optional: it gets its **own run directory, its own
flag tuple and its own write-up**; it may **never be joined** with either campaign's grid, because
`results.jsonl` does not record the start command and no join guard can see a flag
(design `§3.6.3`); and it is measured on a quiet machine under the same pins, since it is a
comparison of a few percent at most and R-reproduce's 5% threshold is the scale of the noise it
must survive. The MTP half of the arm — what the dense bundle's `vmlx_mtp_proposal_head.json` does
when it is not disabled — remains the design's open question 4 and is a second flag on the same
artifact (MoE `§8.5`).

### 7.4 Also open, so the ledger is complete

- **The dense Osaurus `prefill` column was never measured.** The cache pin's absence turned it
  into a lookup column; the MoE campaign demonstrated that the protocol the design asked for works
  and produces genuine prefills. A dense Osaurus re-run under `cache_state: "off"` is the smallest
  repair available to Track 1's one void workload.
- **Model vs profile.** A dense model at ~2.4 bits or a MoE at ~4.15 bits, same harness and pins,
  would separate R4's two variables; neither exists in this campaign and neither is scheduled
  (MoE `§8.3`).
- **A per-module bit map or a kernel trace** would move expert-routing and kernel cost from
  candidate to measured; neither is emitted by either runtime, and the MoE bundle's `config.json`
  is demonstrably wrong about its own safetensors (MoE `§6.2`–`§6.3`).

---

## 8. Phase 1 closeout and transition to Track 2

### 8.1 Exit criteria, as met

The design's Plan 01-01 exit criteria (`§6.2`) name six conditions; Track 1 closes on all six,
for both models:

| criterion | dense | MoE |
|---|---|---|
| both columns PASS, or FAIL with reasons | 36/36 PASS | 40 PASS + 2 FAIL with their reasons recorded |
| no lost visit unexplained | none lost | none lost |
| replicate run | both runtimes, 2 cells × 3 workloads each | both runtimes, 2 cells × 3 workloads each |
| grid joined | `results/grid-jang-dense/grid.md` | `results/grid-jang-moe/grid.md` |
| JANG row read | ✅ (dense `§5`) | ✅ (MoE `§5`) |
| every confound pinned or declared | ✅ with two declared deviations (cache pin not taken; replicate order not reversed) | ✅ with the shared per-cell-digest gap declared |

### 8.2 What Track 1 established, in the only sentences it permits

1. **On `Qwen3.5-4B`, the `JANG_4S` bundle beat the best portable format on the 512-token decode
   shape in both runtimes that load it**, by a replicated +13.9% / +16.8% in vMLX and +9.5% /
   +9.0% in Osaurus, while carrying 4.8% more bytes than the uniform-4-bit artifact, with JIT,
   MTP and KV quantization each pinned off (R1).
2. **On `LFM2.5-8B-A1B`, the `JANG_2L` bundle bought nothing measurable over `stock4bit` on that
   shape in vMLX** (+0.87% / −0.50%, both inside the band — R3) **and lost to it in Osaurus** by a
   replicated −5.12% / −9.80%, while carrying 36% fewer bytes on disk and 16–31% less footprint,
   and while posting a +53.6% / +38.4% prompt-processing advantage in vMLX and +0.8% / +2.8% in
   Osaurus on the same bytes.
3. **R4 is triggered: the dense reading does not transfer to the MoE model.** The effect is
   model-and-bundle-specific — with the model ∧ profile confound named — and the density benefit
   is the part that held in both studies.
4. **The two implementations differ, by a lot, on identical bytes** — and by a different lot
   per artifact: +27.5% / +28.5% decode on dense JANG_4S, tie-or-+4.70% on MoE JANG_2L, with
   Osaurus ahead on MoE chat/prefill-dispatch and vMLX ~2× ahead on MoE prompt ingestion. Loader
   and runtime are not separable in that row; that is what it establishes and all it establishes.
5. **Every vMLX number is a floor for the shipped JANG experience**, not a measurement of it,
   because both campaigns pinned the accelerators off.

And the limits travel with them unchanged: not faster in general, not why, not equal precision on
the MoE, not a cross-runtime memory or load ranking, and **not accuracy** (design `§7`).

### 8.3 Open questions: what closed, what carried

From the design's `§8` and the campaigns' own lists:

| question | status after Track 1 |
|---|---|
| Is the dense `JANG_4S` lead a bit advantage or a packing one? | **open and narrowed**: size is eliminated (JANG is larger and faster); packing vs kernel selection remains unseparated (§5.2, §7.2) |
| Why did v1's Osaurus `JANG_2L` cell lead while vMLX's was mid-pack? | **does not reproduce under one pin set**: with `cache_state: "off"` and one harness, vMLX's JANG ties `stock4bit` and Osaurus's JANG loses to it. The v1 readings cannot be joined to these runs (`cache_state` is absent there and `"off"` here), so the comparison is prose-only and the pin difference is named (MoE `§2.2`, design `§5.1`) |
| Does `optiq__osaurus` fail decode again? | **reproduced and extended**: the FAIL is associated with Osaurus on the 512-token shape (it took `oq4e` too), not with one artifact (MoE `§4.1`, `§8.4`) |
| What does the dense bundle's MTP head do when not disabled? | **open**: untested by design; the second half of the deferred arm (§7.3) |
| Vendor-claim comparisons | **out of scope**, unchanged: the vendor measures with its own in-process harness (design `§8.5`) |

### 8.4 Transition to Track 2: Accuracy Scoring

Track 1's coherence gate is what every number in this paper rests on, and it is **a floor, not an
eval**: it says "this is language", never "this is right" (design `§5.4`). It did its job — no
cell in either campaign failed it, including the two metric-floor FAILs — and it is deliberately
the last thing Track 1 says about quality.

Track 2 opens on exactly the question Track 1 is forbidden to answer, and the two models make it
sharp in opposite directions:

- **MoE density is now a priced offer**: `JANG_2L` returns 36% of the disk and 16–31% of the
  footprint for a decode rate that ties in vMLX and loses 5–10% in Osaurus, plus a vMLX prompt
  advantage of unstable magnitude. Whether that trade is worth taking depends on what 2.37 average
  bits cost in quality — and that number does not exist yet.
- **Dense speed at near-equal precision is the same question mirrored**: `JANG_4S` charges 4.8%
  more disk for a 9–17% decode lead, and near-equal precision suggests a small quality cost —
  suggests, not measures.
- **A JANG lead in tok/s and a JANG loss in accuracy can both be true.** Track 2's deliverable is
  the scored study that prices the trade, with its own pinning discipline; nothing in Track 1 —
  including every number in this paper — may be used to predict its result (design `§6.5`, `§7`).

Track 1 closes on the readings in §8.2 and the ledger in §7; Track 2 inherits the question, not
the answer.

---

## Appendix A — evidence index

| what | where |
|---|---|
| pre-registered readings R1–R4, tie band, R-tie / R-reproduce / R-nothing, confound ledger, deferred JIT A/B, this plan's charter | `docs/research/2026-09-17-v2-track1-jang-study-design.md` (`§2.5`, `§3.1`–`§3.7`, `§6.4`, `§6.5`, `§7`) |
| the dense campaign: runs, pins, columns, replicate, cross-runtime row, attribution, memory | `docs/research/2026-09-17-dense-jang-study.md` (`§1`–`§8`) |
| the MoE campaign: runs, pins, columns, replicate, cross-runtime row, attribution, memory | `docs/research/2026-09-17-moe-jang-study.md` (`§1`–`§8`) |
| the runners, their pins and their `cmp`-verified restores | `scripts/run_jang_dense.sh`, `scripts/run_jang_moe.sh`, `results/grid-jang-{dense,moe}/runner.log` |
| the four dense run directories (columns, replicate) | `results/grid-jang-dense/20260917T{185649Z,194005Z}-format`, `…/replicate/20260917T{202054Z,203824Z}-format` |
| the four MoE run directories (columns, replicate) | `results/grid-jang-moe/20260917T{213103Z,215805Z}-format`, `…/replicate/20260917T{222656Z,223632Z}-format` |
| the joined grids (the 1C rows) | `results/grid-jang-{dense,moe}/grid.md` |
| JANG sidecar declarations and digests | each snapshot's `jang_config.json` (`3a9bf087…`, `858385d1…`) |
| the half-width embedding refusal, measured on three runtimes | `docs/research/2026-09-15-grid-loadability-probe.md` |
| v1's JANG cells (prose comparison only — `cache_state` absent there) | `docs/research/2026-09-16-phase5-joined-grid.md`, `docs/research/2026-09-16-moe-format-axis.md` |
| why a footprint is not one quantity across runtimes | `docs/research/2026-09-16-footprint-is-not-one-quantity.md` |
| what an Osaurus prefix hit costs on this project's record | `docs/research/2026-09-17-cache-state-split.md` |
| `decode_tps`, `prefill_tps`, `CROSS_RUNTIME_UNCOMPARABLE` formulas | `ohyesmlx/report.py` |
| the cache pin's meaning (`None` is not `off`) | `ohyesmlx/runtimes.py`, `ohyesmlx/measure.py` |

## Appendix B — number provenance

Every figure in this paper is a quotation. This table maps each table in this document to the
section of the underlying study it was read from, so a reader can audit any number without
re-deriving it.

| this document | value(s) | source |
|---|---|---|
| §1.1 outcome matrix; §3.3 `L` matrix (§3.3's dense rows) | `L` primary/replicate for `Qwen3.5-4B` | dense `§1.2`, `§3.1`, `§4.1`, `§3.4`, `§4.4` |
| §1.1, §3.3 (MoE rows) | `L` primary/replicate for `LFM2.5-8B-A1B` | MoE `§1.2`, `§3.1`, `§4.1`, `§3.4`, `§4.4` |
| §2.1 | run windows, row counts, PASS/FAIL totals | dense `§1.1`; MoE `§1.1` |
| §2.2 | matrix completeness, hole reasons | design `§2.1`–`§2.3`; dense `§2.3`; MoE `§2.3` |
| §2.3 | artifact bytes, sidecar fields, digests, zero downloads | design `§4.2`, `§4.4`; dense `§2.3`; MoE `§2.3` |
| §2.4 | pins and the `cache_state` difference | dense `§2.2`; MoE `§2.2` |
| §2.5 | restoration guarantees, runner-log line numbers | dense `§2.4`; MoE `§2.4` |
| §2.6 | R-reproduce fire counts | dense `§8.3`; MoE `§8.1` |
| §2.7 | coherence outcomes, the two FAILs, the capped warmup row | dense `§1.1`, `§3.1`; MoE `§1.1`, `§4.1` |
| §3.1, §3.2 | all per-cell `decode_tps`, drift, TTFT, ITL, aggregate, peak | dense `§3.1`, `§4.1`; MoE `§3.1`, `§4.1` |
| §3.3 (non-`L` bullets) | prompt throughput and TTFT pairs | dense `§3.3`; MoE `§3.3`–`§3.5` |
| §4.1, §4.2 | cross-runtime rows and their supporting figures | dense `§5`; MoE `§5` |
| §5.1 | disk/bit table | dense `§6.1`; design `§4.2` |
| §5.2 | half-width refusal, `Pre-fixed 217` | dense `§6.3`; `2026-09-15-grid-loadability-probe.md` |
| §5.3 | expert counts, 67-module repair, candidate status | MoE `§2.3`, `§6.1`, `§6.3` |
| §5.4 | identical-bytes prompt vs decode table | MoE `§5`, `§6.3a` |
| §5.5 | magnitude instability, Osaurus control | MoE `§3.5`, `§4.3` |
| §5.6 | model ∧ profile confound | MoE `§8.3` |
| §6.1 | disk deltas, footprints, outcome columns | dense `§3.1`, `§6.1`, `§7.1`; MoE `§3.1`, `§6.1`, `§7.1` |
| §6.4 | load two-number sums and the 8.11 s outlier | dense `§7.2`; MoE `§7.2` |
| §6.5 | Osaurus cache cost (566.0 MB / ~11 GB) | dense `§7.3` |
| §7.1 | ledger statuses | design `§3.3`; dense `§2.2`, `§8`; MoE `§2.2`, `§8` |
| §7.3, §7.4 | deferred arm, its constraints and the other open items | design `§3.1c`, `§3.6.3`, `§6.5`; dense `§6.3`, `§8.4`; MoE `§8.3`, `§8.5` |
| §8.2, §8.3 | v1 open questions and their status | design `§8`; MoE `§8.4`; dense `§8.5` |

Two arithmetic conventions are inherited unchanged from the studies and are not re-derived here:
every percentage quoted is the quotient of the **one-decimal figures the leaderboards render**
(both studies verified the rendered and full-precision bases agree to within 0.24 pp dense /
0.06 pp MoE and that no reading moves between them), and every `decode_tps` is
`report.summarize`'s median of `completion_tokens / (last_content_s − ttft_s)` across the measured
requests — recomputable from each run directory's `results.jsonl` with the studies' own Appendix B
scripts.
