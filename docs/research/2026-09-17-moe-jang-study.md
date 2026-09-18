# Plan 01-02 — the MoE JANG study: `LFM2.5-8B-A1B` in vMLX and Osaurus

Date: 2026-09-17. Measured 17:30:57–18:46:01 local as four runs and one join. One model
(`LFM2.5-8B-A1B`, a 32-expert MoE), two runtimes that both load JANG and portables, two
single-variable axes, and one replication pass over the cells that carry the claim. Design,
pre-registered readings and pins: `docs/research/2026-09-17-v2-track1-jang-study-design.md`
(§6.3 is this plan); the dense half of the same design is §6.2, measured and written up in
`docs/research/2026-09-17-dense-jang-study.md`.

This document is written against that design's rules, not around them. Where a pre-registered
reading fires, it says so in the design's own vocabulary; where a pre-registered *pin* changed
the shape of a column, the record is reported as it stands. §8 is the list of limits, and the
first item in it changes what this campaign's headline is allowed to attribute.

---

## 1. Executive summary and headline finding

### 1.1 What ran

| run | runtime | started | ended | rows | run directory |
|---|---|---|---|---|---|
| vMLX column (format axis) | vmlx 1.6.59 | 17:31:03 | 17:57:59 | 15 (5 cells × 3 workloads) | `results/grid-jang-moe/20260917T213103Z-format` |
| Osaurus column (format axis) | osaurus 0.25.6 | 17:58:05 | 18:26:50 | 15 (5 cells × 3 workloads) | `results/grid-jang-moe/20260917T215805Z-format` |
| the join | — | 18:26:55 | 18:26:56 | — | `results/grid-jang-moe/grid.md` |
| Osaurus replicate | osaurus 0.25.6 | 18:26:56 | 18:36:26 | 6 (2 cells × 3) | `results/grid-jang-moe/replicate/20260917T222656Z-format` |
| vMLX replicate | vmlx 1.6.59 | 18:36:32 | 18:45:55 | 6 (2 cells × 3) | `results/grid-jang-moe/replicate/20260917T223632Z-format` |

**42 of 42 (cell, workload) rows exist, 40 are PASS and every PASS row names `n = 9` measured
requests.** Fourteen cells were visited twice (ten across the two primary columns, four in the
replicate) with no lost visit. The two `FAIL`s are both in the
Osaurus decode workload and both carry the reason the design predicted for one of them (§4.1).
The runner's timeline is `results/grid-jang-moe/runner.log`, which ends
`JANGMOEDONE 18:46:01` (`runner.log:161`) after four `exit=0` columns and a `GRID exit=0`; its
two Osaurus settings restores are both `cmp -s` verified (`runner.log:9`, `runner.log:152`).

Two columns, two axes, and this campaign is the first in the project where the two runtimes sit
in one grid with **no structural hole**: the MoE loadability probe found all five labels loading
in both runtimes (`2026-09-16-moe-loadability-probe.md`), and the campaign ran all five. The grid
additionally prints the `jang2l` row across both columns — the **runtime axis on identical
bytes** (3,062,430,853 B in every cell of all four runs), the only comparison in this project
where two different loaders see the same weights.

Five cells per column also means the format axis is read with its full cast present:
`stock4bit`, `oq4`, `oq4e`, `optiq` and `jang2l` all ran in both runtimes, which the dense
campaign could not do in either column (its `optiq__vmlx` and `stock4bit__osaurus` cells never
existed — §2.1/§2.2 of the design).

### 1.2 The headline: R4 — the dense JANG decode lead does not transfer to the MoE

On the 512-token `decode` shape, the workload whose rate a prefix cache cannot touch and whose
window is long enough to be a rate rather than an opening, `JANG_2L` does **not** lead the
portable formats. It ties one and loses to the other, and it loses in a way that replicates.

`L` is the design's pre-registered definition,
`(decode_tps(JANG) − decode_tps(best_portable)) / decode_tps(best_portable) × 100`, evaluated per
workload against that column's own best non-JANG cell, and never pooled. Percentages are the
quotient of the one-decimal figures the leaderboards and the grid render; Appendix B recomputes
every one of them from the records' full-precision medians, where no reading moves.

| workload | runtime | primary `L` | replicate `L` | verdict under R-tie |
|---|---|---|---|---|
| `decode` | vmlx 1.6.59 | **+0.87%** | **−0.50%** | **tie** — both visits inside the 2.5% band → **R3** |
| `decode` | osaurus 0.25.6 | **−5.12%** | **−9.80%** | `stock4bit` ahead in both visits, both clear of the band |
| `chat` | vmlx 1.6.59 | −2.86% | +0.60% | direction reverses between visits → no ordering |
| `chat` | osaurus 0.25.6 | −11.07% | −3.71% | `stock4bit` ahead in both visits |
| `prefill` | vmlx 1.6.59 | −10.42% | −0.50% | one visit inside the band → tie |
| `prefill` | osaurus 0.25.6 | −11.16% | −9.86% | `stock4bit` ahead in both visits |

Three readings follow, and each is a rule doing its job:

- **In vMLX, `decode` is a tie and that is the finding.** `jang2l` 116.3 against `stock4bit`
  115.3 is 0.87% — the value is marginally the higher of the two and the difference is less than
  half the band the project pre-registered as unresolvable. The replicate reverses the sign at
  0.50%, which is what a tie looks like under a second visit. **R3: the JANG bundle bought nothing
  measurable over the best portable format on this model, workload and runtime.**
- **In Osaurus, `stock4bit` cleanly beats `jang2l` on sustained decode** — 123.0 against 116.7
  (−5.12%) in the primary, 127.5 against 115.0 (−9.80%) in the replicate. Both visits clear the
  band and the direction agrees, so under R-tie this **is** an ordering, and it is the opposite
  of the dense column's.
- **Put beside Plan 01-01, the pre-registered reading is R4 — split by model.** The dense study
  measured a replicated JANG lead in both runtimes; this one measures a tie in one and a
  replicated loss in the other, on the same two runtimes, the same two axes and the same pin set:

| model | runtime | `L` primary | `L` replicate | reading |
|---|---|---|---|---|
| `Qwen3.5-4B` (dense, plan 01-01) | vmlx 1.6.59 | **+13.9%** | **+16.8%** | R1 — JANG led |
| `Qwen3.5-4B` (dense, plan 01-01) | osaurus 0.25.6 | **+9.5%** | **+9.0%** | R1 — JANG led |
| `LFM2.5-8B-A1B` (MoE, this plan) | vmlx 1.6.59 | +0.87% | −0.50% | R3 — tie |
| `LFM2.5-8B-A1B` (MoE, this plan) | osaurus 0.25.6 | **−5.12%** | **−9.80%** | JANG behind, replicated |

The design's R4 exists to catch exactly this: *"R1/R2 on one model, R3 or reversed sign on the
other"* — the same shape the v1 format ordering had when it failed to transfer from dense to MoE.
**The JANG decode advantage measured on `Qwen3.5-4B` does not transfer to `LFM2.5-8B-A1B`.** R4's
own limit travels with it and §8.3 states it in full: this campaign changed two things between the
two studies — the model and the JANG profile (`JANG_4S` at 4.15 average bits in the dense study,
`JANG_2L` at 2.37 here) — so "model-specific" is the reading the design pre-registered, and it is
not the same claim as "MoE architecture is why".

### 1.3 What the same evidence does *not* say

- **It does not say JANG_2L is slower to serve.** It says the 512-token sustained decode rate is
  where JANG's dense lead fails to appear. On the other two workloads JANG is at or near the top
  of the vMLX column, and on prompt processing it is substantially ahead (§3.5).
- **It does not say JANG_2L is bigger or costlier.** The bundle is the smallest artifact in the
  campaign — 3.06 GB against 4.78–5.47 GB — and the lightest in memory by a wide margin (§7). It
  carries 36% fewer bytes on disk than the artifact that beat it on Osaurus decode and still
  decoded slower there, which is a finding about the runtime's decode path rather than about the
  artifact's size (§6.1).
- **It does not price the shipped vMLX JANG path.** JIT and native MTP are pinned off in every
  vMLX cell of this study, by design, so the JANG cell differs from its column only in its bytes —
  and the vendor's headline decode path is JIT-on. §8.5 restates that this is a floor.

### 1.4 The cross-runtime row, and what it establishes

Same bytes, two loaders (`JANGQ-AI/LFM2.5-8B-A1B-JANG_2L` @ `5fb82773…`, 3,062,430,853 B on every
`jang2l` row of all four runs):

| workload | vMLX primary | Osaurus primary | vMLX lead | vMLX replicate | Osaurus replicate | vMLX lead |
|---|---|---|---|---|---|---|
| `decode` | 116.3 | 116.7 | **−0.34%** | 120.4 | 115.0 | **+4.70%** |
| `chat` | 112.2 | 126.1 | −11.02% | 117.4 | 132.3 | −11.26% |
| `prefill` (decode rate) | 97.1 | 123.4 | −21.31% | 99.5 | 124.4 | −20.02% |

**The two implementations no longer separate on sustained decode the way they did in the dense
study.** There, vMLX's JANG cell decoded the identical weights 27.5% and 28.5% faster than
Osaurus's; here the primary reads as a tie (−0.34%, inside the band) and the replicate puts vMLX
4.70% ahead — opposite directions, so under R-tie the row publishes **both numbers and no
ordering**. What does separate, in both visits and by a wide margin, is the rest of the row.
Measured as Osaurus relative to vMLX — the opposite convention to the table's own `vMLX lead`
column, and stated so the two cannot be confused — Osaurus's JANG cell is **+12.4% / +12.7%** ahead
on `chat` and **+27.1% / +25.0%** ahead on the `prefill` workload's 64-token rate, while vMLX's
prompt-processing throughput is **+97.8% / +104.4%** ahead of Osaurus's on the same bytes (§5,
§6.3). Every one of those is a wide margin; none of them is the 512-token sustained decode rate
that carries §1.2, which is this row's tie.

---

## 2. Provenance and operational environment

### 2.1 Runtimes and versions

| runtime | version (recorded per row) | how the version is established |
|---|---|---|
| vMLX | **1.6.59** on all 21 vMLX rows (15 primary + 6 replicate) | `runtime_version` in every row; the constant is read from the app bundle's engine source (`runtimes.py`'s `VMLX_ENGINE_INIT`), since `vmlx --version` exits 2 |
| Osaurus | **0.25.6** on all 21 Osaurus rows | `runtime_version` in every row, from the running server |

One runtime at a version per column, both columns at one version each: join guard 4 had nothing to
refuse, and the grid's provenance block names each version beside its run directory.

### 2.2 The pins, as recorded — and this time the cache pin *was* taken

Read from the header line of each `results.jsonl`, printed by the grid's provenance block, and
compared field by field by the join guard across the two primary columns:

| pin | value | status |
|---|---|---|
| `temperature` | `0.0` | as designed, in the request body (`transport.py:157`) |
| `seed` | `0` | as designed, sent only when non-`None` (`transport.py:162-163`) |
| `warmup` | `{mode: plateau, window: 5, floor: 10, cap: 20, plateau_pct: 3.0}` | as designed; 40 of 42 rows closed on the rule |
| `measured` | `9` batches, `concurrency` `1` | as designed |
| `cooldown_s` | `30.0` | as designed |
| `prompt_tokens` | `null` (the three pinned literals) | as designed |
| **`cache_state`** | **`"off"`, on every row of all four runs** | **as designed — the pin the dense campaign did not take** |

`cache_state: "off"` is the campaign's most consequential pin and the reason its Osaurus column
means something the dense one could not. Every Osaurus run passed `--cache-state off`, the runner
toggled the host's own cache keys false around both Osaurus columns, and §4.0 shows the
behavioural result: every Osaurus prefill request in this campaign is a genuine prompt
processing, with no collapsing TTFT sequence anywhere.

**Two rows hit the warmup cap and both are the FAILed cells** — `oq4e__osaurus` `decode` and
`optiq__osaurus` `decode`, each at `warmup_count = 40` with `warmup_plateau: false` (20 per
visit, both visits). No other row failed to close its window, and no cell lost a visit.

### 2.3 The artifacts

All paths are under `$H = ~/.cache/huggingface/hub/`. `disk_bytes` is recomputed per row at
measurement time; every row of every run agrees with the pre-run inventory of the design's §4.2 to
the byte, and the two runtimes' rows agree with each other on the same label.

| label | repo | snapshot | bytes | files | declared quantization |
|---|---|---|---|---|---|
| `jang2l` | `JANGQ-AI/LFM2.5-8B-A1B-JANG_2L` | `5fb82773427c2f25395de8821eff6d95e86feb53` | **3,062,430,853** | 18 | JANG v2, `actual_bits` **2.37**, widths `[2, 6, 8]` + 18 passthrough-16 |
| `stock4bit` | `mlx-community/LFM2.5-8B-A1B-MLX-4bit` | `146590a491db88581884033023f51f6b49a27b89` | 4,782,228,753 | 11 | affine 4-bit, group 64, **+ 22 layer overrides at 8 bits** |
| `oq4` | `stamsam/LFM2.5-8B-A1B-oQ4` | `acb4fd209565b7c05de287488416f4217820a3db` | 4,994,822,580 | 10 | affine 4-bit, group 64, + 38 overrides (26×8, 11×6, 1×5) |
| `oq4e` | `brainworkup/LFM2.5-8B-A1B-oQ4e` | `88977e47cd1fe2eb5ec5bf5230d3de9868adef9e` | 4,994,831,815 | 11 | affine 4-bit, group 64, + 38 overrides (26×8, 11×6, 1×5) |
| `optiq` | `mlx-community/LFM2.5-8B-A1B-OptiQ-4bit` | `5a5c595823cf26ab1068508eb5cf85816bb2db6b` | 5,473,296,789 | 14 | affine 4-bit, group 64, + 155 overrides (92×8, 63×4) |

Two facts from that table matter later and are read from the artifacts' own `config.json`, walked
today rather than quoted:

- **The `stock4bit` control is uniform-4-bit on most modules and 8-bit on 22 of them** — all 22
  are `model.layers.{2..23}.feed_forward.gate`, i.e. the MoE router of every layer that has one.
  "Stock 4-bit" is the honest label for the artifact and is not a claim that every tensor in it is
  4 bits.
- **`jang2l`'s `config.json` declares `{"group_size": 64, "bits": 2}` with no per-module map at
  all**, and that declaration is *wrong about its own safetensors*: vMLX's loader detects the
  disagreement and repairs it from tensor shapes at load time (§2.6, §6.2). The sidecar is the
  artifact's claim about itself; the loader's warning is the artifact's measured correction.

**Digest of the one artifact whose sidecar the reading depends on**, re-verified today rather than
quoted:

```
shasum -a 256 $H/models--JANGQ-AI--LFM2.5-8B-A1B-JANG_2L/snapshots/5fb82773427c2f25395de8821eff6d95e86feb53/jang_config.json
858385d169c8028f0e59654d591510f519ba4cac58ed61365c49eed31a26f610
```

That is byte-identical to the digest recorded at design time, so the artifact's own claims about
itself are the ones §6 reads: `format: jang/2.0`, `quantization.method: jang-importance`,
`profile: JANG_2L`, `target_bits: 2.0` / `actual_bits: **2.37**`, `block_size: 64`,
`bit_widths_used: [2, 6, 8]`, `asymmetric`, architecture `hybrid_moe_ssm` with `has_vision: false`
and `has_moe: true`, `capabilities.cache_type: hybrid`, `runtime.total_weight_bytes: 3,044,371,880`.

Three readings the design pre-registered on that sidecar apply unchanged here:

1. **`actual_bits` is an average over the bundle, not over the tensors decode touches.** MoE decode
   touches 4 of 32 experts per token per layer, the sidecar says three widths are present and
   nothing in it says which module got which. A per-token byte model is **not derivable** — so
   every rate below is published beside `actual_bits`, `bit_widths_used`, block size and the
   measured on-disk bytes, and no explanation here depends on a byte count nobody measured.
2. **`source_model.parameters` reads `34.5B`** for a model this project documents as 8 B total /
   1 B active. It is a label a quantiser wrote, kept and labelled, never published as a value.
3. **The bundle carries no `turboquant` block**, so loader-level TurboQuant KV is not active for
   it; the vMLX loader's own line confirms the KV codec is the harness's env-var path, not the
   artifact's auto path (§2.6).

A provenance note that survives from the audit and was re-checked today: **four of these five
artifacts carry a `.vmlx-alignment.lock`; the JANG bundle carries none.**

### 2.4 Host handling

- **Osaurus settings.** `cp -p` copies of `~/.osaurus/config/server-runtime.json` and `server.json`
  were taken before the first Osaurus cell; both cache keys (`cache.prefix.enabled`,
  `cache.blockDisk.enabled`) were set **false** for the whole campaign, and
  `modelIdleResidencyPolicy.seconds` was pinned to **900** (the host's own 30 unloads the model
  inside the 30 s cooldown). Both files were restored and verified with `cmp -s` after the column
  and again after the replicate — `runner.log:9` and `runner.log:152`, each reading
  `osaurus settings restored byte-exact (cmp)`. The `INT/TERM/HUP` trap is in the script
  (`scripts/run_jang_moe.sh:106`), so an interrupt restores rather than leaving the host pinned.
- **What today's live files show, and why that is the promise kept.** Read now, the host's files
  carry `cache.prefix.enabled: true`, `cache.blockDisk.enabled: true` and residency `30` — the
  host's own state, restored byte-exact. The campaign's state was the other one, and the behavioural
  evidence for it is §4.0's TTFT sequences rather than the file as it sits today.
- **What the settings step did *not* do.** The design's §3.5 required a per-cell
  `shasum -a 256` of both files so that a byte moving between two cells — tracked key or not —
  would be in the record. The runner pinned, restored and `cmp`-verified, but it took no per-cell
  digests. No per-cell digest evidence exists for this campaign; the pre/post restoration is what
  the record carries. The same deviation the dense campaign recorded, for the same reason.
- **The per-model thinking switch, checked here because the runner did not record it.** The
  design's pre-flight (§5.8) asks which of the campaign's model ids carry a per-model
  `disableThinking` entry in the Osaurus app plist. Checked today: the plist holds **15
  `model_options_*` keys and none of them is any of this campaign's five ids**, so no per-model
  thinking switch could have differed between the two columns' cells, and none of the five ran
  under a special one.
- **Ports and isolation.** vMLX on 8000, Osaurus on 1337. Ports swept and stale Osaurus apps
  killed by full executable path (`^/Applications/osaurus.app/Contents/MacOS/osaurus`) at
  `runner.log:1`, `:4`, `:8`, `:148`, `:151`, `:155`. One runtime held weights at a time.

### 2.5 The pins the join guard cannot see, verified in the logs

`results.jsonl` does not record the start command, so this is per-run log evidence, and this
campaign's version of it differs from the dense campaign's in two ways that a reader must not
carry over by habit.

| check | expected evidence | observed |
|---|---|---|
| JANG path taken, not the generic loader | the JANG loader's own lines | `JANG v2 detected — loading via mmap (instant)`, `Loading 6 safetensors shards via mmap`, `JANG v2 loaded in 1.0s: LFM2.5-8B-A1B (2.4-bit avg)` (replicate: `0.7s`) — in the `jang2l` cells of both vMLX runs, and in no portable log |
| the mixed-precision repair the design predicted by wording | `Pre-fixed N module(s) with mixed-precision bit widths` | **absent, and a different line carries the same meaning**: `quant_shape_inference: patched 67 module(s) … config disagreed with safetensors shapes (top-level config claimed bits=2 group_size=64; per-module overrides corrected from shape)`. The MoE bundle takes the **text** path (`is_mllm_model(...): tier=jang_config_explicit_false result=False`), not the dense bundle's multimodal path, so the dense `Pre-fixed 217` line is not the check to look for here |
| **JIT off** | *absence* of `JIT: mx.compile applied successfully — running warmup pass` | **absent from all 14 vMLX logs** — 0 matching lines, case-insensitive, across the whole campaign |
| **MTP off** | `MLLM native MTP skipped for request=…` on every request | **0 matching lines in all 14 logs — because there is nothing to skip**: neither the MoE JANG bundle nor the MoE stock-4bit bundle ships an MTP head (checked today: 0 MTP files in either snapshot). `--disable-native-mtp` is still in the start command (`runtimes.py:1119`); the dense campaign's 43–50 lines per log were an artifact of *its* bundle's MTP head |
| TurboQuant KV state | a `TurboQuant:` state line | `TurboQuant KV skipped: VMLX_DISABLE_TQ_KV=1; using native model cache plus scheduler-level q4/q8 storage only when explicitly requested and compatible.` — the env-var path the harness's own flag sets, not the design's predicted `jang_config has no 'turboquant' block` wording |
| **the prefix cache is off in vMLX** | a behavioural check | `Hybrid SSM cache detected but prefix cache is disabled; SSM companion lookup/store/re-derive is disabled for this run` — **present in all 14 vMLX logs**, once per visit, and the TTFT sequences agree (§3.0) |
| the sampling the server actually resolved | per-request kwargs | `{'temperature': 0.0, 'top_p': 1.0, 'max_tokens': 128, 'enable_thinking': True, …}` — `temperature` pinned by the harness, `top_p` the runtime's own default. The harness sends no `top_p` and no `repetition_penalty`; §8.6 carries the consequence |

Two log lines need their meaning stated rather than left to a reader, because both appear in the
JANG cells:

- `Native live-cache policy active: preserving the model's make_cache() objects; generic TurboQuant
  KV replacement is disabled.` — a KV-precision policy statement, not a cache state.
- `SSD prefix cache: stored in the model's NATIVE cache representation … (JANGTQ/JANG-affine
  high-fidelity default)`. It describes the *storage codec* that tier would use for a JANG-affine
  bundle; it is not a statement that the tier ran, and the tier is disabled by
  `--disable-block-disk-cache`, which is unconditional in this harness's command
  (`runtimes.py:1124`). The behavioural check agrees: vMLX's per-cell TTFT sequences are flat
  (§3.0).

**The start tuple, for the record** (`runtimes.py:1092-1125`): `vmlx serve <dir> --host 127.0.0.1
--port 8000 --served-model-name <name> --stream-interval 1 --continuous-batching --max-num-seqs 1
--no-jit --disable-native-mtp --disable-prefix-cache --disable-block-disk-cache`. It is
byte-identical for a JANG cell and a portable cell, which is the point: the only thing that
differs between two cells of a vMLX column is the artifact.

### 2.6 The visit structure, and one evidence gap

Each cell's runtime starts once per visit and runs all three workloads under that one load, both
visits inside the cell's own process pair. The primary vMLX column left **10 server logs for 10
visits** in the order `stock4bit → oq4 → oq4e → optiq → jang2l → jang2l → optiq → oq4e → oq4 →
stock4bit` (17:31:03, 17:33:49, 17:37:32, 17:40:33, 17:43:25, 17:45:56, 17:48:20, 17:50:57,
17:53:29, 17:56:03 — visit 1 forward, visit 2 reversed, exactly as `VISIT_ROUNDS` plans); the
replicate left 4 for its 4 visits in the order `jang2l → stock4bit → stock4bit → jang2l`
(18:36:32, 18:39:07, 18:41:40, 18:44:04). The Osaurus column left 14 matching logs.

**The one record gap**: the primary vMLX column's captured CLI stdout,
`results/grid-jang-moe/log-vmlx.log`, is a **0-byte file** (created 17:31, mode `600`), where the
Osaurus column's (`log-osaurus.log`, 515 lines) and both replicate logs carry their rendered
leaderboards. The run itself is intact — the run directory holds `results.jsonl` and
`leaderboard.md`, `GRID exit=0` — so this is a capture artifact for one column, and the vMLX
column's own evidence is its run directory plus the 10 per-cell runtime logs in `results/logs/`.
It is named here rather than passed over because the runner's own comment says the redirect was
moved inside the script precisely so that runner output could not come unbound from its command.

---

## 3. The format axis inside vMLX

`--study format`, runtime `vmlx` held constant at 1.6.59, five cells, `n = 9` per (cell,
workload). Source: `results/grid-jang-moe/20260917T213103Z-format/leaderboard.md`; ordered per
workload by `decode_tps`, never pooled.

### 3.0 The shape of the column before the numbers

Every cell in this column prefills every time it is asked, and the evidence is the TTFT sequence
rather than a flag. `jang2l__vmlx` on the `prefill` workload: warmups 0.655, 0.664 … 0.883 s
(21 of them) with its nine measured requests at 0.791–0.822 s. `stock4bit__vmlx`: warmups 0.867 …
1.302 s, measured 1.087–1.265 s. Nothing collapses anywhere in the column, which is what a start
command carrying `--disable-prefix-cache` and `--disable-block-disk-cache`, on a hybrid model whose
SSM companion path the log itself reports as disabled, is supposed to look like.

One detail of the column belongs here because two tables depend on it: **`prefill_tps` is
`usage.prompt_tokens / ttft_s` (`report.py`), i.e. the server's own count of the prompt it
processed.** The JANG bundle tokenizes the pinned prefill literal into **1,335 tokens** and each
portable into **1,332** — a 3-token, 0.2% difference produced by the bundle's own
`chat_template.jinja` / tokenizer, constant for every request of every cell of the format. It is
small enough not to move any reading here and is named so that no reader compares a
`prefill_tps` across two cells whose denominators are not identical.

### 3.1 `decode` (512 tokens) — a tie at the top, and four portables that separate

| cell | `decode_tps` | JANG's lead over it | drift % | TTFT p50 s | ITL s | aggregate tok/s | peak MB | cold load s |
|---|---|---|---|---|---|---|---|---|
| `jang2l__vmlx` | **116.3** | — | +0.5 | 0.098 | 0.0086 | 113.8 | 3624 | 7.10 |
| `stock4bit__vmlx` | 115.3 | **+0.87%** | +3.9 | 0.116 | 0.0087 | 112.5 | 5214 | 7.09 |
| `optiq__vmlx` | 100.6 | +15.6% | +6.1 | 0.125 | 0.0100 | 99.2 | 5869 | 7.08 |
| `oq4e__vmlx` | 97.0 | +19.9% | +10.9 | 0.138 | 0.0103 | 98.1 | 5416 | 7.08 |
| `oq4__vmlx` | 65.6 | +77.3% | +76.0 | 0.196 | 0.0153 | 73.6 | 5415 | 7.07 |

The two cells at the top are **0.87% apart — a tie**, and the grid's ranks 1 and 2 are the
renderer's, not the measurement's claim. Behind them the portables do separate cleanly:
`stock4bit` is 12.75% ahead of `optiq`, which is 3.58% ahead of `oq4e`, which is 32.37% ahead of
`oq4` — so the column has a real ordering underneath a tied top pair.

**`oq4`'s row is the one to read before its number.** Its `decode_tps` is the lowest in the column
and its drift is **+76.0%** — early median 60.6 tok/s against a late median of 106.7 — the largest
move of that kind in the campaign. It was still climbing when its window closed, so 65.6 is an
early-window figure for a cell that had not settled, and it says more about the window than about
the artifact. It keeps its place and its annotation, per the rule that a cell still moving is
ranked and annotated rather than dropped.

**No other row in this table under-measures JANG's competition**: `jang2l`'s own drift is +0.5%,
the smallest in the column.

### 3.2 `chat` (128 tokens) — a sign reversal between visits, reported as one

| cell | `decode_tps` | JANG's lead over it | drift % | TTFT p50 s | ITL s | aggregate tok/s | peak MB |
|---|---|---|---|---|---|---|---|
| `stock4bit__vmlx` | **115.5** | **−2.86%** | +1.7 | 0.114 | 0.0087 | 104.0 | 5196 |
| `jang2l__vmlx` | 112.2 | — | +3.7 | 0.092 | 0.0090 | 104.0 | 3605 |
| `optiq__vmlx` | 96.9 | +15.8% | +7.6 | 0.119 | 0.0104 | 91.0 | 5851 |
| `oq4__vmlx` | 96.1 | +16.8% | +10.0 | 0.120 | 0.0105 | 91.4 | 5396 |
| `oq4e__vmlx` | 94.4 | +18.9% | +24.8 | 0.123 | 0.0107 | 85.2 | 5397 |

`stock4bit` is 2.86% ahead of JANG here — just outside the band, so a bare reading of the primary
would publish a `stock4bit` lead. The replicate does not permit it: on the same pair it reads
`jang2l` 117.4 against `stock4bit` 116.7, a **+0.60% lead the other way** (§3.4). Two visits, two
directions, one of them inside the band: under R-tie this workload **publishes both numbers and no
ordering**.

The three portables behind the pair are a tie cluster among themselves — `optiq` 96.9 to `oq4`
96.1 is 0.83% and `oq4` to `oq4e` is 1.77% — so the honest statement for the bottom of the table
is the same one the rules produce: **the `chat` workload separates the JANG bundle from the three
`o*` portables (15.8–18.9%) and from nothing at the top.**

### 3.3 `prefill` (64 tokens) — `stock4bit` leads on the rate, JANG leads on the prompt

| cell | `decode_tps` | JANG's lead over it | drift % | TTFT p50 s | **prefill tok/s** | peak MB |
|---|---|---|---|---|---|---|
| `stock4bit__vmlx` | **108.4** | **−10.42%** | −10.2 | 1.245 | 1069.7 | 5906 |
| `jang2l__vmlx` | 97.1 | — | +1.5 | **0.812** | **1643.4** | 4275 |
| `optiq__vmlx` | 88.9 | +9.2% | +5.7 | 1.193 | 1116.3 | 6476 |
| `oq4__vmlx` | 84.5 | +14.9% | +9.4 | 1.244 | 1070.7 | 6048 |
| `oq4e__vmlx` | 84.3 | +15.2% | +9.8 | 1.240 | 1074.6 | 6047 |

The 64-token decode rate puts `stock4bit` 10.42% ahead of JANG — a real gap, and its direction
does not replicate (§3.4).

But **this row is the one place in the campaign where JANG's advantage is large, and it is on the
prompt rather than on the generation.** `jang2l` reaches the first token of the 1,335-token prompt
in **0.812 s** — 1,643.4 tok/s of genuine prompt processing — against `stock4bit`'s **1.245 s** and
1,069.7 tok/s, and against 1.19–1.24 s for the other three portables. That is **+53.6%** prompt
throughput and a first token **0.433 s sooner**, on the same machine, in the same column, with the
same start command, with both cells' TTFT sequences flat (§3.0). `stock4bit`'s own drift is −10.2%
(slowing as it was measured) and the TTFT p50s of the four portables sit in a 52 ms band
(1.193–1.245) while JANG's sits 381 ms below the closest of them.

### 3.4 The replicate: the decode tie holds, `chat` reverses, `prefill` collapses into the band

`results/grid-jang-moe/replicate/20260917T223632Z-format`, `jang2l__vmlx` against
`stock4bit__vmlx` — the pair with the widest margin in the primary's decode workload, resolved
from the primary's own decode rows (`scripts/run_jang_moe.sh:154-175`; `runner.log:147`).

| workload | `jang2l` | `stock4bit` | JANG's lead | primary's lead | reading |
|---|---|---|---|---|---|
| `decode` | 120.4 | 121.0 | **−0.50%** | +0.87% | tie in both visits |
| `chat` | 117.4 | 116.7 | **+0.60%** | −2.86% | **sign reversed** |
| `prefill` | 99.5 | 100.0 | **−0.50%** | −10.42% | one visit in the band → tie |

The decode pair lands 0.50% apart on the second visit, which is what the primary's 0.87% said it
would: **two independent visits, two orderings, both inside the band.**

The prefill row is the campaign's clearest example of why R-tie is written the way it is: the
primary's −10.42% is a clear-looking gap and the replicate's −0.50% is a tie, so the workload
publishes a tie with both numbers. The replicate does not, however, remove JANG's prompt-side
advantage — it reproduces it: `jang2l` 0.783 s / 1,705.6 tok/s against `stock4bit` 1.081 s /
1,232.2 tok/s, **+38.4%** prompt throughput and a first token 0.298 s sooner. §3.5 takes both
visits together.

### 3.5 The finding the column does carry: JANG's prompt-processing advantage replicates

| visit | `jang2l` prefill tok/s | `stock4bit` prefill tok/s | JANG's advantage | JANG TTFT | `stock4bit` TTFT |
|---|---|---|---|---|---|
| primary | **1643.4** | 1069.7 | **+53.6%** | 0.812 s | 1.245 s |
| replicate | **1705.6** | 1232.2 | **+38.4%** | 0.783 s | 1.081 s |

The direction agrees in both visits and the gap clears the band in both, so this is a published
advantage — the one place in the MoE campaign where `jang2l` is unambiguously ahead of the
artifact that beat it on `decode`. Two limits ride with it and neither is optional:

- **The magnitude is not stable.** `stock4bit`'s own `prefill_tps` moved +15.2% between visits
  while JANG's moved +3.8%, so the gap moved 15.2 percentage points (53.6% → 38.4%) between two
  measurements of the same pair. The direction replicates; the number is an occasion.
- **It is a prompt-processing advantage, not a decode one.** It is measured on the `prefill`
  workload's *first token*, and the same row's 64-token decode rate is the one that loses to
  `stock4bit`. A reader who reads this section as "JANG generates faster" has read it backwards.

What this does *not* license is the reason. The dispatch that commissioned this document
attributes it to "low precision (2.37 actual bits) on prompt ingestion", and the arithmetic of
prompt processing — fewer bytes per weight read — is a plausible mechanism. It is not what this
evidence establishes: the identical 2.37-bit bytes produce a **+0.8% / +2.8%** prompt advantage in
Osaurus on the same machine (§4.3, §4.4). A property of the artifact would not need the loader.
§6.3 states what can and cannot be concluded.

---

## 4. The format axis inside Osaurus

`--study format`, runtime `osaurus` held constant at 0.25.6, five cells, `n = 9` per (cell,
workload). Source: `results/grid-jang-moe/20260917T215805Z-format/leaderboard.md`.

### 4.0 The shape of the column: the prefill workload is a prefill, and this is the check

This is the first Osaurus column in the project where the `prefill` workload measured prompt
processing rather than a prefix-cache lookup, and the difference is visible in the cell's own
requests. **No Osaurus prefill cell in this campaign has a collapsing TTFT sequence.** Every
first-warmup of every prefill cell and every request after it sits in the same band:

| cell (primary) | first prefill warmup | every later warmup | measured requests |
|---|---|---|---|
| `stock4bit__osaurus` | 1.553 s | 1.324–1.692 s | 1.530–1.710 s |
| `oq4__osaurus` | 1.335 s | 1.307–1.746 s | 1.625–1.695 s |
| `oq4e__osaurus` | 1.380 s | 1.344–1.729 s | 1.624–1.698 s |
| `optiq__osaurus` | 1.397 s | 1.325–1.747 s | 1.590–1.710 s |
| `jang2l__osaurus` | 1.322 s | 1.282–1.676 s | 1.533–1.614 s |

Compare what a cache hit looks like, measured on this project's own record: the dense campaign's
Osaurus `prefill` cells opened at **3.425–3.726 s** and served every subsequent request in
**0.270–0.607 s** — a 5.6–13.8x collapse — and its replicate had no cold request at all because
the entries were already in `~/.osaurus/cache/kv_v2/`
(`docs/research/2026-09-17-dense-jang-study.md` §4.3; 06-02 measured the same phenomenon at 0.404 s
against a 9.401 s cold prefill of a 4,096-token prompt). Nothing of that shape exists here. The
first warmup of every cell is *not* the slowest request in its cell — it is the fastest or near
it — and the requests run 1.25–1.75 s end to end, against 0.79–1.27 s of measured prefill for the
same prompt shape in vMLX (§3.0): the arithmetic of a slower loader, not the reciprocal of a
lookup.

Note the sharpest single contrast, because it is the one that cannot be explained away: in the
dense campaign's first Osaurus visit the **first** prefill request took 3.4–3.7 s and later ones
took ~0.4 s; here the first request takes 1.32–1.55 s and later ones take 1.28–1.75 s. The
campaign's `cache_state: "off"` pin, the runner's host toggle (`runner.log:5`, `:148`) and the
`cmp`-verified restores (`runner.log:9`, `:152`) produced the behaviour they were written to
produce.

### 4.1 `decode` (512 tokens) — `stock4bit` leads, and two cells fail the metrics floor

| cell | `decode_tps` | JANG's lead over it | drift % | TTFT p50 s | ITL s | aggregate tok/s | peak MB | cold load s |
|---|---|---|---|---|---|---|---|---|
| `stock4bit__osaurus` | **123.0** | **−5.12%** | +5.9 | 0.221 | 0.0081 | 118.8 | 4542 | 1.30 |
| `jang2l__osaurus` | 116.7 | — | +3.2 | 0.221 | 0.0086 | 112.1 | 3829 | 1.27 |
| `oq4__osaurus` | 115.8 | **+0.78%** | +2.6 | 0.230 | 0.0087 | 110.8 | 4497 | 1.25 |
| `oq4e__osaurus` | **FAIL** | — | — | 3.586 | — | — | 4501 | 1.25 |
| `optiq__osaurus` | **FAIL** | — | — | 4.732 | — | — | 4749 | 1.26 |

`stock4bit` leads JANG by 5.12%, and the two cells behind JANG are a **tie with it**, not an
ordering: `jang2l` 116.7 against `oq4` 115.8 is 0.78%. So the table's only publishable orderings
are `stock4bit` ahead of the rest, and the rest tied among themselves.

`stock4bit`'s own +5.9% drift says its number is an early-window figure too; the replicate
returns +3.67% higher (§4.4), consistent with that direction.

**The two FAILs, and they are the design's prediction coming true twice.**

| cell | status | reason (verbatim) | coherence floor | what it actually produced |
|---|---|---|---|---|
| `oq4e__osaurus` | FAIL | `no content completion tokens from token_source='none', so decode tok/s is undefined` | **pass** | 128 content deltas and 685 characters of prose per request, plus ~1,937 characters of reasoning; TTFT 3.535–3.638 s |
| `optiq__osaurus` | FAIL | `no content completion tokens from token_source='none', so decode tok/s is undefined` | **pass** | 33 content deltas and 214 characters of prose per request, plus ~2,528 characters of reasoning; TTFT 4.534–4.784 s |

Both cells **produced language** — the coherence gate passed on both, and the text is ordinary
prose about the prompt — and both are excluded by the *metrics* floor, which is the one that had
nothing to work with. Osaurus answered with two channels (reasoning and content) and reported no
usage block, so the harness cannot attribute a completion-token count to either
(`transport.py:26-30`, `resolve_token_accounting` → `INCOMPARABLE_TOKEN_ACCOUNTING` →
`token_source='none'`) and `decode_tps` is undefined. That is exactly the failure
`2026-09-16-moe-format-axis.md` recorded for `optiq__osaurus` on this shape in v1, and this
campaign adds `oq4e` to it: **the failure travels with the 512-token shape and the runtime, not
with one artifact.** Both cells passed `chat` and `prefill`, so the column stands and the grid
prints `FAIL` in its own state rather than a manufactured number — in the middle of a workload
table, which is the first time either JANG study has needed that state. Of the grid's four entry
states, **two occur in this campaign**: a number in every other cell, and `FAIL` on exactly these
two. `no value` does not occur (no cell cleared every floor and lacked the ranking metric), and
neither does `—` (the MoE matrix has no unmeasured combination — five labels ran in both
runtimes, which is the structural completeness the dense campaign's two holes cost it).

Two numbers on those rows must not be read as measurements of anything:

- **Their `ttft_p50_s`** is the run's time to the first *content* delta on a request whose
  reasoning channel was already streaming. It is a real wait, and it is 16x `stock4bit`'s on the
  same shape — but it is not a prefill wait and not comparable to the other rows' TTFT.
- **Their `prefill_tps`** — 8.9 and 6.8 — is `32 / 3.586` and `32 / 4.732`: a 32-token prompt
  divided by a first-content wait. On a normal row that quotient is prompt throughput; here it is
  arithmetic on two numbers that do not describe a prefill. The metric card publishes it because
  the renderer publishes what the record holds; no reader should read it.

### 4.2 `chat` (128 tokens)

| cell | `decode_tps` | JANG's lead over it | drift % | TTFT p50 s | ITL s | aggregate tok/s | peak MB |
|---|---|---|---|---|---|---|---|
| `stock4bit__osaurus` | **141.8** | **−11.07%** | −2.3 | 0.210 | 0.0071 | 114.2 | 3862 |
| `oq4e__osaurus` | 127.2 | −0.86% | +1.4 | 0.232 | 0.0079 | 103.2 | 3861 |
| `jang2l__osaurus` | 126.1 | — | +3.0 | 0.217 | 0.0080 | 104.2 | 3140 |
| `oq4__osaurus` | 124.8 | +1.04% | +5.1 | 0.227 | 0.0081 | 103.2 | 3862 |
| `optiq__osaurus` | 119.7 | +5.35% | +5.4 | 0.234 | 0.0084 | 99.9 | 4088 |

`stock4bit` leads by 11.07%, and the replicate agrees in direction at 3.71% (§4.4), so this is a
published ordering. Behind it is a three-way tie — `oq4e` 127.2, `jang2l` 126.1, `oq4` 124.8, a
1.9% span — and `optiq` 4.09% behind `oq4`, clear of the band.

### 4.3 `prefill` (64 tokens)

| cell | `decode_tps` | JANG's lead over it | drift % | TTFT p50 s | **prefill tok/s** | peak MB |
|---|---|---|---|---|---|---|
| `stock4bit__osaurus` | **138.9** | **−11.16%** | −1.9 | 1.616 | 824.2 | 5204 |
| `oq4__osaurus` | 128.5 | −3.97% | +2.8 | 1.680 | 793.0 | 5159 |
| `oq4e__osaurus` | 128.0 | −3.60% | +2.7 | 1.678 | 793.9 | 5163 |
| `optiq__osaurus` | 126.4 | −2.37% | +3.9 | 1.692 | 787.2 | 5391 |
| `jang2l__osaurus` | 123.4 | — | +4.5 | **1.603** | **830.9** | 4411 |

`stock4bit` leads the 64-token decode rate by 11.16%, and the four cells behind it span 123.4–128.5
(4.1% end to end): `oq4`/`oq4e` are a tie (0.39%), `optiq` is a tie with `oq4e` (1.25%) and with
JANG (2.37%), so the only ordering this table carries below the leader is `stock4bit > the rest`.

**The prompt side of this table is the mirror of §3.5 and the reason that section cannot attribute
its advantage to the bits.** Osaurus's `prefill_tps` values are a 43.7 tok/s band (787.2–830.9)
across five formats whose on-disk sizes differ by 79% — and `jang2l`, the smallest artifact of the
five, holds the top of that band by **+0.8%** over `stock4bit` (830.9 against 824.2) while
overtaking it on TTFT by 0.013 s (1.603 against 1.616). On identical bytes, vMLX's loader turned
2.37-bit weights into a 53.6% prompt-throughput advantage over uniform 4-bit; Osaurus's turned the
same weights into 0.8%. Whatever vMLX is doing, it is not the bits alone.

### 4.4 The replicate: the lead is the same on all three workloads

`results/grid-jang-moe/replicate/20260917T222656Z-format`, `jang2l__osaurus` against
`stock4bit__osaurus`.

| workload | `jang2l` | `stock4bit` | gap | primary's gap | reading |
|---|---|---|---|---|---|
| `decode` | 115.0 | 127.5 | **`stock4bit` +10.8%** | +5.4% | replicated lead |
| `chat` | 132.3 | 137.4 | **`stock4bit` +3.9%** | +12.4% | replicated lead, smaller |
| `prefill` | 124.4 | 138.0 | **`stock4bit` +10.9%** | +12.6% | replicated lead |

`stock4bit` wins all three workloads in the second visit as it did in the first, and the decode
gap *widens*. `jang2l`'s replicate decode row carries a +7.1% drift of its own (early median 114.5
against late 122.6), so its 115.0 is an early-window figure; the same cell's primary drifted +3.2%.
Both cells moved less than 5% between visits (§8.1).

---

## 5. The cross-runtime JANG row

Same artifact, two independent loaders. Nothing was re-measured for this row: it is the `jang2l`
row of the grid plus the same row of the replicate, and the two directories of each pair share
every pin the join guard compares — including `cache_state: "off"`. Identical bytes are confirmed
on both sides: `disk_bytes` = **3,062,430,853** on every `jang2l` row of all four runs, and one
snapshot revision, `5fb82773427c2f25395de8821eff6d95e86feb53`.

| workload | vMLX primary | Osaurus primary | vMLX lead | vMLX replicate | Osaurus replicate | vMLX lead |
|---|---|---|---|---|---|---|
| `decode` | 116.3 | 116.7 | **−0.34%** | 120.4 | 115.0 | **+4.70%** |
| `chat` | 112.2 | 126.1 | −11.02% | 117.4 | 132.3 | −11.26% |
| `prefill` (decode rate) | 97.1 | 123.4 | −21.31% | 99.5 | 124.4 | −20.02% |
| `prefill` (prompt tok/s) | **1643.4** | 830.9 | **+97.8%** | **1705.6** | 834.3 | **+104.4%** |

Supporting figures on `decode`, both primary: TTFT p50 0.098 s against 0.221 s, ITL 0.0086 s
against 0.0086 s, aggregate 113.8 against 112.1 tok/s, peak 3624 against 3829 MB.

**The decode row publishes no ordering.** Primary −0.34% is inside the band; the replicate's
+4.70% is outside it in the other direction. The design's R-tie requires the direction to agree
*and* the gap to clear the band in both visits; here neither condition holds across the pair, so
what is published is **both numbers with the tie named on the primary and the replicate's 4.7%
printed beside it**.

**Comparison with the dense finding, which is the point of this row.** On `Qwen3.5-4B`'s JANG_4S
the same two loaders separated by **+27.5% and +28.5%** on decode — a 1.0 pp spread over two
visits in which every cell inside them moved 8–15%, which is what made it a strong result. On
`LFM2.5-8B-A1B`'s JANG_2L the same comparison reads −0.34% and +4.70%. Three things follow and
only the first is a measurement:

1. **The vMLX-vs-Osaurus JANG difference is not a property of the loaders alone.** A 27.5% gap on
   one artifact and a tie-or-4.7% gap on another, measured by the same harness on the same machine
   within hours of each other, says the pair's behaviour is artifact-dependent.
2. **Osaurus's JANG implementation leads on everything before the first token**, by 12.4% / 12.7%
   on `chat` and 27.1% / 25.0% on the `prefill` workload's decode rate (both Osaurus relative to
   vMLX; the table above states the same gaps as vMLX's −11.0% / −11.3% and −21.3% / −20.0%).
   Against the dense row, where vMLX led all three workloads by 27.5%, 14.8% and 7.9%, the
   direction has reversed on two of the three and the third's 27.5–28.5% decode lead has become
   this campaign's tie.
3. **The `prefill` prompt comparison is now legal where it was void in the dense campaign.** There
   the Osaurus TTFTs were cache lookups and the design's rule forbade reading them (§4.3 of the
   dense study). Here both columns prefilled every request — vMLX by construction, Osaurus by
   §4.0's evidence — so the row is a comparison of two genuine prompt-processing rates on identical
   weights. It is a strong claim (vMLX roughly 2x) measured on the same machine with the same
   harness, and it is subject to §8.6's sampling-defaults caveat.

**Two structural limits ride on this row and are not negotiable.** Loader and runtime are not
separable here — the claim is "the two implementations differ, by this much, on identical bytes",
never which internal does it. And `cold_load_s` and `peak_mb` may not be read across it
(`report.CROSS_RUNTIME_UNCOMPARABLE` prints its reason above any runtime-axis ordering by either);
§7 gives the numbers with their sums and their non-comparability.

---

## 6. Attribution breakdown: why the dense bundle won and this one did not

The question the design pre-registered (§3.1) is whether JANG's speed is the weights or the thing
that loads the weights. On this artifact set the question has a different shape than it had in
dense, because the MoE set contains **no equal-precision pair at all**.

### 6.1 Size cannot be the explanation in either direction, and here that cuts the other way

| artifact | declared quantization | bytes on disk | GiB | relative to `jang2l` |
|---|---|---|---|---|
| `jang2l` (JANG_2L) | 2.37 average bits, widths `[2, 6, 8]` + 18 passthrough-16 | **3,062,430,853** | 2.852 | — |
| `stock4bit` | affine 4-bit, 22 modules at 8 bits | 4,782,228,753 | 4.454 | **+56.2%** |
| `oq4` | affine 4-bit, 38 overrides | 4,994,822,580 | 4.652 | +63.1% |
| `oq4e` | affine 4-bit, 38 overrides | 4,994,831,815 | 4.652 | +63.1% |
| `optiq` | affine 4-bit, 155 overrides | 5,473,296,789 | 5.097 | +78.7% |

The JANG bundle is **36.0% smaller on disk than the artifact that beat it on Osaurus decode**,
38.7% smaller than `oq4`/`oq4e` and 44.1% smaller than `optiq`, and it carries the fewest bytes
of the five by a wide margin. Two readings follow, and both are about the model rather than the
format:

- **On this MoE, decode throughput is not proportional to weight bytes.** A 36%-smaller bundle
  decoded 5.1–9.8% *slower* in Osaurus and tied in vMLX. If the decode step were dominated by
  streaming weights, the smaller bundle could not lose; it lost, which says the time is going
  somewhere the artifact's size does not govern.
- **The dense campaign's cleanest result does not have an analogue here.** In dense, JANG_4S was
  *larger* than stock-4bit (4.8% more bytes, more average bits) and still won, which eliminated
  size as an explanation for a *win*. Here the bundle is smaller and does not win, which eliminates
  size as an explanation for a *loss* — and by the same logic eliminates it as an explanation for
  a win, since there is no win to explain on the rate.

What size *does* buy is measurable and is in §7: memory and storage.

### 6.2 What the loader trace actually shows, and what it does not

This bundle does not take the path the dense one took, and the difference is visible in the logs:

| observation | dense `JANG_4S` (plan 01-01) | MoE `JANG_2L` (this campaign) |
|---|---|---|
| model classification | `JANG v2 VLM detected — loading via mmap`, `has_vision: true` | `Model config: detection_source=jang_stamped family=lfm2 … cache_subtype=lfm2_moe_hybrid_ssm is_mllm=False`, `is_mllm_model(…): tier=jang_config_explicit_false result=False` |
| mixed-precision repair | `Pre-fixed 217 module(s) with mixed-precision bit widths` | `quant_shape_inference: patched 67 module(s) … config disagreed with safetensors shapes (top-level config claimed bits=2 group_size=64; per-module overrides corrected from shape)` |
| load | `JANG v2 VLM loaded in 0.8s` | `JANG v2 loaded in 1.0s` (replicate `0.7s`): `LFM2.5-8B-A1B (2.4-bit avg)` |
| KV policy | TQ KV skipped via env var; native cache | same, plus `Hybrid SSM cache detected but prefix cache is disabled; SSM companion lookup/store/re-derive is disabled for this run` |

Three facts, and no fourth:

1. **The artifact's own config is wrong about the artifact.** `config.json` says uniform
   `bits=2, group_size=64`; the safetensors disagree on 67 modules and the loader repairs the map
   from tensor shapes. This is the MoE counterpart of the dense bundle's half-width
   `embed_tokens` — evidence that the format's real per-tensor assignment is not in the sidecar —
   and it is *why* the design forbids a per-token byte model here. A reader cannot know which
   module is 2, 6, 8 or 16 bits.
2. **The repair does not show up as a load cost.** vMLX's `cold_load_s` for `jang2l` is 7.10 s in
   the primary against 7.07–7.09 s for the four portables; the loader's own load line says 1.0 s.
   Whatever the 67-module pass costs, it is not visible at cold start.
3. **The logs do not name the kernels.** As in dense, the loader's lines name the pre-fix and the
   bit average, never the kernel or the unpacking path. This study pinned the one switch
   (`--no-jit`) that would have let a reader see compilation happen.

### 6.3 Why the dense bundle won and this one did not: what is measured, and what is a candidate

The dispatch that commissioned this document names three mechanisms — expert routing, 2.37-bit
precision against uniform 4-bit, and kernel overhead. The evidence supports one of them as a
*measured* statement, reframes another, and leaves the third where it belongs.

**(a) Measured: the outcome difference between the two studies is not the artifact's bits, because
the same bits behave differently in two implementations.** This is the campaign's strongest
attribution fact and it is a comparison of identical bytes: on `JANG_2L` at 3,062,430,853 B,
vMLX's prompt processing runs **1,643.4 / 1,705.6 tok/s** against Osaurus's **830.9 / 834.3** —
roughly 2x — while the *decode* rates on those same bytes are 116.3/116.7 (primary) and
120.4/115.0 (replicate). The `JANG_2L` arithmetic is fixed in both runtimes; the loaders are not;
and the loaders produce a 2x difference on one metric and none on another. **Whatever produced
vMLX's prompt advantage is in vMLX's implementation of the format, not in the format.** The design
said the same thing from the other side (§3.1b: the row attributes to the pair, not within it).

**(b) Reframed: "2.37 bits versus uniform 4" is a real difference and not a decode-rate
explanation.** The precision difference is larger than anything in the dense study — 2.37 average
bits against ~4, on a bundle 36–44% smaller — and the design pre-registered that a MoE comparison
is "confounded with precision by construction". But the direction of the confound is *opposite* to
the finding: fewer bits and fewer bytes came with **no decode gain in vMLX and a replicated loss
in Osaurus**. Low precision bought prompt-processing throughput in vMLX (§3.5) and bought nothing
on the decode rate in either runtime. A mechanism that predicts "fewer bits ⇒ faster sustained
decode" is contradicted by this campaign's decode tables in both columns.

**(c) Candidate, not measured: expert-routing and gather cost on a 32-expert MoE.** `LFM2.5-8B-A1B`
routes 4 of 32 experts per token (`num_experts: 32`, `num_experts_per_tok: 4`, from the artifact's
own `config.json`), and the two models that produced the two readings differ in exactly this:
`Qwen3.5-4B` is dense with no expert machinery, `LFM2.5-8B-A1B` is a sparse MoE. A per-token
routing and gather stage is a plausible reason a quantized bundle's byte savings stop converting
into throughput — the expert weight stream is fragmented across 32 modules, so any per-module
unpack or layout cost is paid many times per token, and a per-token cost that is not proportional
to total weight bytes is exactly what "36% smaller, 5–10% slower" looks like.

**This campaign cannot test that.** Three things would be needed and none is here: a dense model
at ~2.4 bits measured in the same runtimes with the same harness; a per-module bit map for this
bundle (the config is wrong and the sidecar has none); or a kernel-level trace (not emitted).
Worse, the two studies that would be compared changed **two** things at once — the model *and* the
JANG profile: `JANG_4S` at 4.15 average bits with widths `[4, 6]` against `JANG_2L` at 2.37 with
widths `[2, 6, 8]`, two different profiles from the same quantiser family and not two settings of
one artifact. "Dense JANG won, MoE JANG did not" is therefore a true statement about two bundles on
two models and **not** a measurement of either variable alone. §8.3 carries this into the
boundaries.

### 6.4 Attribution this study may publish

In the design's own vocabulary: *on `LFM2.5-8B-A1B`, in vMLX 1.6.59 and Osaurus 0.25.6, the
`JANG_2L` bundle did not lead the best portable format on the 512-token decode shape — it tied
`stock4bit` in vMLX (R3) and lost to it in Osaurus by a replicated 5.1% / 9.8% — while carrying
36% fewer bytes on disk and 30.5% (vMLX) / 15.7% (Osaurus) less peak footprint, with JIT and
native MTP pinned off, and while posting a +53.6% / +38.4% prompt-processing advantage over
`stock4bit` in vMLX and +0.8% / +2.8% in Osaurus on identical bytes. The decode-rate outcome is
model- and bundle-specific; the prompt-processing advantage is implementation-specific; and the
mechanism behind either is not separated by this measurement.*

---

## 7. Memory footprint, cold-start cost, and storage economics

### 7.1 Peak footprint (`footprint -p <pid>`, `phys_footprint`)

| workload | vMLX `jang2l` | vMLX portables | Osaurus `jang2l` | Osaurus portables |
|---|---|---|---|---|
| `chat` | 3605 | 5196 / 5396 / 5397 / 5851 | 3140 | 3862 / 3861 / 3862 / 4088 |
| `prefill` | 4275 | 5906 / 6048 / 6047 / 6476 | 4411 | 5204 / 5159 / 5163 / 5391 |
| `decode` | **3624** | 5214 / 5415 / 5416 / 5869 | **3829** | 4542 / 4497 / 4501 / 4749 |

**Within a column, this is the campaign's clearest JANG result, and it is a format-axis reading
which is exactly what Study 1A/1B publish.** On the decode workload:

- **vMLX: 3,624 MB against `stock4bit`'s 5,214 MB — 30.5% less** (and against `optiq`'s 5,869 MB,
  38.3% less). The bundle is 1,590 MB smaller in footprint than the artifact it tied on decode.
- **Osaurus: 3,829 MB against `stock4bit`'s 4,542 MB — 15.7% less.** The runtime that beat it on
  decode paid 713 MB more for the privilege.
- The replicate agrees within 1 MB and 21 MB respectively (3,623 / 5,211 vMLX; 3,808 / 4,516
  Osaurus) — the tightest cell-to-cell agreement in the campaign.

**Across runtimes this number is not one quantity and no ordering may be read from it.** vMLX
reports a footprint well above the weight bytes; Osaurus reports roughly half of them, because it
holds weights in wired, GPU-pinned pages that `phys_footprint` charges differently (the measured
basis is `2026-09-16-footprint-is-not-one-quantity.md`; `report.CROSS_RUNTIME_UNCOMPARABLE` prints
the reason above any runtime-axis ordering by it). The grid obeys this: its runtime-axis lines
order by `decode_tps` and never by memory.

### 7.2 Cold start: two numbers, never one

| runtime | `cold_load_s` | `first_request_s` (workload: `chat`) | sum | what the second number is |
|---|---|---|---|---|
| vMLX 1.6.59 | 7.10 / 7.09 (primary `jang2l` / `stock4bit`), 8.11 / 7.08 (replicate) | 1.19 / 1.22, 1.23 / 1.21 | **8.29 / 8.31**, 9.34 / 8.29 | an ordinary warm request: vMLX loads weights before readiness, so `cold_load_s` is the load |
| Osaurus 0.25.6 | 1.27 / 1.30, 1.28 / 1.27 | 2.76 / 3.51, 2.31 / 2.04 | **4.03 / 4.81**, 3.59 / 3.31 | a deferred load: Osaurus is *listening* in ~1.3 s and loads on the first request |

Within the Osaurus column **`jang2l` is the fastest cell to first token in both visits** — 4.03 s
against 4.16 / 4.74 / 4.81 / 5.20 in the primary — which is what a 36%-smaller bundle that
Osaurus's loader reads natively should look like, and it is a real (if modest) advantage of the
smallest artifact. Within the vMLX column the sums are flat at 8.29–8.40 s for all five cells.

**One outlier, named rather than smoothed**: `jang2l__vmlx`'s replicate `cold_load_s` is **8.11 s**
against 7.08–7.10 s for every other vMLX cell visit in the campaign — about 1 s, or 14%, above
every other load of the same artifacts in the same session. It is a single-visit anomaly on a
metric no reading in this document turns on, and it is the only place in the campaign where the
JANG cell's load differs from its column's.

Across runtimes, the design's rule applies: a load comparison uses the **sum**, and on the sum
Osaurus reaches first token **1.6–2.6x sooner than vMLX** on all ten cell pairs (e.g. `jang2l`
4.03 against 8.29 in the primary; `stock4bit` 4.81 against 8.31). Ranking on `cold_load_s` alone
would name Osaurus 5.5–6.3x the faster loader, which is a time-to-listening, not a cold start.

### 7.3 Storage economics, and where the trade lands

The campaign's five MoE artifacts total **23,307,610,790 B (21.71 GiB / 23.31 GB)**, of which
`jang2l` is 13.1%. Against the artifact that beat it on Osaurus decode, **JANG_2L saves 1.72 GB
on disk and 1,590 MB of peak footprint** for a decode rate 5.1–9.8% lower on one runtime and tied
on the other — and for a prompt-processing rate 53.6% higher on vMLX.

Put plainly, this is the campaign's practical finding: **on this model the JANG bundle's value is
density, not sustained-decode throughput.** A reader whose constraint is memory or disk gets 30%
(vMLX) or 16% (Osaurus) of their footprint back and 36% of the disk; a reader whose constraint is
tokens per second on a long generation gets nothing over `stock4bit` in vMLX and loses in Osaurus.
A reader whose workload is prompt-heavy gets vMLX's 1.5–1.6x prompt throughput on top of the
density — a combination no other artifact in this campaign offers, and one whose magnitude moved
15 pp between the two visits that measured it.

---

## 8. Threats to validity and boundaries

### 8.1 R-reproduce fires on 1 of 12 cell pairs, and that pair is a workload that already ties

Under R-reproduce a replicate more than 5% away from its primary is published with both figures
and no ordering. One pair does that:

| runtime | workload | cell | primary | replicate | change |
|---|---|---|---|---|---|
| vmlx | `prefill` | `stock4bit` | 108.4 | 100.0 | **−7.75%** |
| vmlx | `decode` | `stock4bit` | 115.3 | 121.0 | +4.94% |
| vmlx | `chat` | `jang2l` | 112.2 | 117.4 | +4.63% |
| osaurus | `chat` | `jang2l` | 126.1 | 132.3 | +4.92% |
| vmlx | `decode` | `jang2l` | 116.3 | 120.4 | +3.53% |
| osaurus | `decode` | `stock4bit` | 123.0 | 127.5 | +3.66% |
| the other six | — | — | — | — | −3.10% to +2.47% |

**The pair that fires is `stock4bit__vmlx` on `prefill`**, the cell whose primary carried a −10.2%
drift (slowing as it was measured) and whose replicate is 7.75% higher. No ordering this document
publishes turns on that cell's level, and the instability runs against the JANG readings rather
than for them: vMLX's `prefill` workload already publishes a **tie** with both numbers printed
(§3.4), and the replicate's higher `stock4bit` figure is what *shrinks* the JANG prompt advantage
from +53.6% to +38.4%.

Every comparison this document publishes is *within* a visit — two cells measured in the same
session window, interleaved by the visit plan — so what R-reproduce forbids is reading §3.1's
"116.3" as the JANG bundle's decode rate on this machine; it is that cell's rate on that visit.

### 8.2 Two workloads have no settled ordering in vMLX, and this is the rule working

- **`chat`**: −2.86% one way in the primary, +0.60% the other way in the replicate. Opposite
  directions, so no ordering. (`stock4bit`'s own visits moved only +1.04%, so this is not the
  thermal-decline shape the dense campaign's `chat` row had.)
- **`prefill`**: −10.42% in the primary, −0.50% in the replicate. One visit inside the band is
  enough for a tie under R-tie.
- **`decode`** is the workload the readings are taken on, and it is the one whose two visits agree:
  +0.87% and −0.50%, both inside the band, which is a tie in both.

### 8.3 R4's confound: this campaign changed the model *and* the JANG profile

The pre-registered reading is "split by model", and that is what the evidence supports. But the
dense and MoE halves of Plan 01 differ in two ways at once — `Qwen3.5-4B` (dense, hybrid SSM)
against `LFM2.5-8B-A1B` (32-expert MoE), **and** `JANG_4S` (4.15 average bits, widths `[4, 6]`)
against `JANG_2L` (2.37 average bits, widths `[2, 6, 8]`). Any explanation that names expert
routing is naming a candidate, not a measurement (§6.3c). To separate them needs a dense model at
~2.4 bits or a MoE at ~4.15 bits measured with the same harness and pins; neither exists in this
campaign and neither is scheduled.

### 8.4 The two FAIL cells, and what may not be read from them

`oq4e__osaurus` and `optiq__osaurus` on `decode` produced language, passed the coherence floor, and
failed the metrics floor for a runtime-accounting reason (§4.1). No rate, ITL, drift or aggregate
figure is published from either, and the `ttft_p50_s` and `prefill_tps` values their cards carry
are not prefill measurements. The v1 MoE grid recorded the same failure for `optiq` on this shape;
this campaign adds `oq4e`, which makes it two artifacts of the same runtime — so the failure's
association is with **Osaurus on the 512-token shape**, not with one quantization. Whether a
different Osaurus build fixes it is open; `runtime_version` is recorded per row precisely so the
comparison stays anchored.

### 8.5 The pins make this a floor for vMLX's shipped JANG path, not a replica of it

`--no-jit` and `--disable-native-mtp` are in every vMLX cell of this study by design, so the JANG
cell differs from its column only in its bytes — and the vendor's headline JANG path is JIT-on.
**The vMLX numbers here are a floor for that path, not a measurement of it.** The deferred
single-variable A/B (`--enable-jit` against `--no-jit`, artifact and runtime constant) remains the
cheapest experiment this project has, and it is now more interesting than it was in dense: vMLX's
JANG cell posts a 1.5–1.6x prompt-processing advantage with JIT off, and no decode advantage at
all.

One nuance that inverts a dense-campaign check: `--disable-native-mtp` is inert on this model,
because neither MoE bundle ships an MTP head. The absence of the `MLLM native MTP skipped` line in
all 14 logs is therefore **not** evidence that the flag was dropped — the dense campaign's
line-count check does not transfer to a bundle with nothing to skip.

### 8.6 Evidence gaps and unchecked conditions

- **Per-cell `shasum` of the Osaurus settings files was not taken** (design §3.5 required it; the
  runner did pre/post `cp -p` + `cmp -s` only). A byte that moved between two cells — outside the
  drift guard's 23 tracked keys — would not be in this record. The dense campaign shares the gap.
- **The per-model Osaurus thinking switch was not recorded by the runner.** It is checked in §2.4
  here — no `model_options_` entry exists for any of the five ids — but that check is this
  document's, not the campaign's, and it is the reason the confound is uniform rather than absent.
- **The harness pins `temperature` and `seed` and does not send `top_p` or `repetition_penalty`**
  (`transport.py:155-163`), so each runtime's own defaults apply. Within a column this is a
  constant and every format-axis reading is unaffected; across the JANG row it rides along with
  the loader, and the standing project rule names exactly this as a way a cross-runtime comparison
  can be invalidated. The vMLX logs show the server resolving `top_p: 1.0` per request; no
  equivalent record exists for Osaurus's defaults.
- **The primary vMLX column's captured stdout is 0 bytes** (§2.6). The run's own directory and the
  per-cell runtime logs carry its evidence; the column-level CLI transcript does not.
- **The same literal prompt is 1,335 tokens to the vMLX JANG cell and 1,332 to every other cell**
  (JANG bundle's own tokenizer/template). Constant within each cell, 0.2% between them, and named
  so that no reader divides one cell's completions by another's prompt.
- **Warmup fingerprints.** Four of the ten primary vMLX rows drifted more than 5% positive
  (`oq4` `decode` +76.0%, `oq4e` `chat` +24.8%, `oq4e` `decode` +10.9%, `oq4` `chat` +10.0%) and
  one drifted negative (`stock4bit` `prefill` −10.2%); no Osaurus cell exceeded +5.9%. Every
  affected row is printed with its annotation and none was dropped.
- **Thermals and machine quietness cannot be verified from the records.** The rule holds without
  enforcement; what the record shows is four `exit=0` columns, no lost visit, and a runner that
  swept ports and stale apps between every column.

### 8.7 The boundaries, stated plainly

- **One model.** `LFM2.5-8B-A1B`, sparse MoE, 32 experts / 4 active. Nothing here transfers to the
  dense model, and the two models' readings are set side by side only under R4's own terms (§1.2,
  §8.3).
- **Not equal precision.** 2.37 average bits against ~4, on a bundle 36–44% smaller. There is no
  near-equal-precision pair on this model, so unlike the dense study's `jang4s` v `stock4bit`
  comparison, no result here can be read as free of the precision confound.
- **No accuracy claim.** Nothing here speaks to what any format costs in quality. A JANG tie in
  tok/s, a JANG win in memory and a JANG loss in accuracy can all be true; that is a separate
  study with its own pins.
- **No cross-runtime memory or load ranking.** §7 explains why, with the measured basis.
- **No attribution of the decode outcome to architecture.** R4 is triggered; the mechanism is not
  measured (§6.3, §8.3).
- **This is the MoE half of Track 1, not the synthesis.** The two-model reading against R4 is
  Plan 01-03's deliverable and the dense half is `2026-09-17-dense-jang-study.md`.

---

## Appendix A — evidence index

| what | where |
|---|---|
| design, pre-registered readings R1–R4, tie band (2.5%), replication rules (R-tie, R-reproduce, R-nothing) | `docs/research/2026-09-17-v2-track1-jang-study-design.md` §§2.5, 3.7 |
| the dense half of the same design, and the R1 reading this plan tests against | `docs/research/2026-09-17-dense-jang-study.md` §§1.2, 5 |
| the runner, its pins, its Osaurus toggle/restore and its sweep order | `scripts/run_jang_moe.sh`; `results/grid-jang-moe/runner.log` (restores at `:9`, `:152`; `JANGMOEDONE` at `:161`) |
| vMLX column rows, drift notes, metric cards | `results/grid-jang-moe/20260917T213103Z-format/{leaderboard.md,results.jsonl}` |
| Osaurus column rows, the two FAILs, metric cards | `results/grid-jang-moe/20260917T215805Z-format/{leaderboard.md,results.jsonl}` |
| the two columns joined, with the `jang2l` row | `results/grid-jang-moe/grid.md` |
| replicates | `results/grid-jang-moe/replicate/20260917T{T222656Z,T223632Z}-format/` |
| JANG loader trace (`JANG v2 detected … mmap`, `patched 67 module(s)`, `JANG v2 loaded in 1.0s … (2.4-bit avg)`) | `results/logs/vmlx-20260917T174325…175603-60790.log`, `…T183632…184404-36750.log` |
| JIT absence (0 lines) and MTP absence (0 lines, no MTP head in either bundle) | the same 14 logs; `ls` of both MoE snapshots |
| the SSM/prefix-cache-disabled line, once per visit in all 14 vMLX logs | the same 14 logs |
| per-cell visit structure (10 primary logs, 4 replicate) | `results/logs/vmlx-20260917T17*.log`, `results/logs/osaurus-20260917T17*.log` |
| `JANG_2L` sidecar and its digest | `$H/models--JANGQ-AI--LFM2.5-8B-A1B-JANG_2L/snapshots/5fb82773…/jang_config.json` (`858385d1…`) |
| declared per-module quantization of all five MoE artifacts | each snapshot's `config.json` |
| `prefill_tps`, `decode_tps` and `CROSS_RUNTIME_UNCOMPARABLE` formulas | `ohyesmlx/report.py` (`prefill_tps = prompt_tokens / ttft_s`) |
| `token_source`, `INCOMPARABLE_TOKEN_ACCOUNTING`, the output-stream rule | `ohyesmlx/transport.py:26-30`, `:394-419`, `:460-468` |
| vMLX start tuple (`--no-jit`, `--disable-native-mtp`, `--disable-prefix-cache`, `--disable-block-disk-cache`) | `ohyesmlx/runtimes.py:1075-1125` |
| what an Osaurus prefix hit costs on this project's record | `docs/research/2026-09-17-dense-jang-study.md` §4.3; `docs/research/2026-09-17-cache-state-split.md` (0.404 s against 9.401 s) |
| v1's `optiq__osaurus` decode FAIL, which this campaign reproduced and extended | `docs/research/2026-09-16-moe-format-axis.md` |
| why a footprint is not one quantity across runtimes | `docs/research/2026-09-16-footprint-is-not-one-quantity.md` |

## Appendix B — recompute

Everything in this document is recomputed from the four `results.jsonl` files; the rendered
leaderboards were read for their notes, not for their numbers. `decode_tps` is not stored in the
record — `report.py` derives it as `completion_tokens / (last_content_s − ttft_s)`, median across
the measured requests — so the harness's own `summarize` is what a reader should call:

```sh
PY=/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python
$PY - <<'EOF'
import sys; sys.path.insert(0, '.')
from ohyesmlx import measure, report

RUNS = {"vmlx-pri": "results/grid-jang-moe/20260917T213103Z-format",
        "osau-pri": "results/grid-jang-moe/20260917T215805Z-format",
        "osau-rep": "results/grid-jang-moe/replicate/20260917T222656Z-format",
        "vmlx-rep": "results/grid-jang-moe/replicate/20260917T223632Z-format"}
R = {}
for name, path in RUNS.items():
    header, results = measure.load_run(path)
    R[name] = {(r["cell_id"], r["workload_id"]): r
               for r in report.summarize(results, measured=header.get("measured"))}

for rt, pri, rep in [("vmlx", "vmlx-pri", "vmlx-rep"), ("osaurus", "osau-pri", "osau-rep")]:
    jang = "jang2l__" + rt
    for wl in ("chat", "prefill", "decode"):
        out = []
        for run in (pri, rep):
            best = max((r["decode_tps"], cid) for (cid, w), r in R[run].items()
                       if w == wl and "jang" not in cid and r["decode_tps"] is not None)
            j = R[run][(jang, wl)]["decode_tps"]
            out.append((j, best[0], 100 * (j - best[0]) / best[0]))
        # rendered basis: the one-decimal figures the leaderboards publish
        print(f"{rt:8s} {wl:8s} PRI {round(out[0][0],1)}/{round(out[0][1],1)} "
              f"L={100*(round(out[0][0],1)-round(out[0][1],1))/round(out[0][1],1):+.2f}%  "
              f"REP {round(out[1][0],1)}/{round(out[1][1],1)} "
              f"L={100*(round(out[1][0],1)-round(out[1][1],1))/round(out[1][1],1):+.2f}%  "
              f"| full {out[0][2]:+.2f}% / {out[1][2]:+.2f}%")
EOF
```

Both bases, side by side — the rendered one-decimal basis is what every percentage in this
document uses, and the full-precision basis is what the same arithmetic gives from the records'
medians:

| runtime | workload | primary (rendered) | primary (full precision) | replicate (rendered) | replicate (full precision) |
|---|---|---|---|---|---|
| vmlx | `chat` | −2.86% | −2.83% | +0.60% | +0.59% |
| vmlx | `prefill` | −10.42% | −10.48% | −0.50% | −0.54% |
| vmlx | `decode` | +0.87% | +0.89% | −0.50% | −0.48% |
| osaurus | `chat` | −11.07% | −11.12% | −3.71% | −3.72% |
| osaurus | `prefill` | −11.16% | −11.16% | −9.86% | −9.88% |
| osaurus | `decode` | −5.12% | −5.09% | −9.80% | −9.78% |

No conclusion here turns on the difference: the largest disagreement between the two bases is
0.06 pp (`vmlx` `chat` primary), and every gap stays on the same side of the 2.5% band and of the
5% replication threshold under either. Two spot checks on the raw records rather than on the
derived figures:

```sh
# The Osaurus prefill cells are genuine prefills: the first request of each cell is not a
# collapsed lookup, and no later request is one either.
python3 - <<'EOF'
import json
for run in ("20260917T215805Z-format", "replicate/20260917T222656Z-format"):
    rows = [json.loads(l) for l in
            open(f"results/grid-jang-moe/{run}/results.jsonl")][1:]
    for r in rows:
        if r["workload_id"] != "prefill":
            continue
        w = [o["ttft_s"] for o in r["warmup_observations"]]
        m = sorted(o["ttft_s"] for o in r["observations"])
        print(f"{run:38s} {r['cell']['id']:20s} first={w[0]:.3f}s rest={min(w[1:]):.3f}-{max(w[1:]):.3f}s "
              f"measured p50={m[4]:.3f}s prompt_tokens={r['observations'][0]['prompt_tokens']}")
EOF

# The two FAIL cells: language was produced, the accounting was not.
python3 - <<'EOF'
import json
rows = [json.loads(l) for l in
        open("results/grid-jang-moe/20260917T215805Z-format/results.jsonl")][1:]
for r in rows:
    if r["status"] != "FAIL":
        continue
    o = r["observations"][0]
    print(f"{r['cell']['id']:20s} {r['workload_id']:8s} reason={r['reason']!r}")
    print(f"{'':20s} content={len(o['text'])}ch reasoning={len(o['reasoning_text'] or '')}ch "
          f"deltas={o['content_event_count']} token_source={o['token_source']} "
          f"prompt_tokens={o['prompt_tokens']} ttft={o['ttft_s']:.3f}s")
EOF
```
