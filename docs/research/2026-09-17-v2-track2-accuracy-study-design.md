# v2 Track 2 — The Accuracy Study: design, single-variable test matrix, evaluation protocol, and the Pareto framework

Date: 2026-09-17. **Design only.** Nothing in this document is measured: no runtime was started,
no model was loaded, no benchmark item was run, no harness was installed. Every figure quoted
below is either verified on disk today (Section 2.4, with the command that re-derives it) or read
from one of the three v2 Track 1 documents that closed this morning, and each one names its
source. The scores this study will produce do not exist yet, and nothing in Track 1 predicts them.

Subject: **what the speed and the density cost in accuracy.** Ten artifacts — the five dense
`Qwen3.5-4B` formats and the five MoE `LFM2.5-8B-A1B` formats — scored on one pinned benchmark
suite under one pinned harness, one format at a time, against the two numbers Track 1 already
published for the same cells.

Read first, in this order:

- **Track 1 design** — `docs/research/2026-09-17-v2-track1-jang-study-design.md`: the matrix
  vocabulary (`§2.0`), the tie band and replication rules (`§2.5`), the confound ledger (`§3.3`),
  the pre-registered readings (`§3.7`), and the hand-off to this track (`§6.5`, `§8.4`).
- **Track 1 synthesis** — `docs/research/2026-09-17-jang-cross-runtime.md`: every speed and memory
  figure this document uses as a coordinate, and the rule that closes Track 1 (`§8.4`: "Track 2
  opens on exactly the question Track 1 is forbidden to answer").
- **Harness contracts** — `docs/interfaces.md`, `ohyesmlx/measure.py`, `ohyesmlx/runtimes.py`.

---

## 1. Executive summary and the problem statement

### 1.1 The trilogy, and the coordinate that is missing

v1 and v2 Track 1 published two of the three numbers a reader needs to choose a quantization
format. The first is **speed**, the second is **memory and disk**, and the third — **accuracy** —
has been deliberately out of scope since v1's founding decision:

> **Speed + memory only in v1** | Pre-phase | Accuracy work is refused until v1 ships, however
> tempting. (`.paul/STATE.md`, Decisions)

That deferral has been discharged. What is now on the record, per model, per runtime, per
workload, is this:

| | dense `Qwen3.5-4B` | MoE `LFM2.5-8B-A1B` |
|---|---|---|
| sustained decode winner (`decode`, 512 tok) | `JANG_4S`, replicated, **+13.9% / +16.8%** in vMLX and **+9.5% / +9.0%** in Osaurus | **tie** in vMLX (+0.87% / −0.50%, R3); `stock4bit` ahead in Osaurus by **5.12% / 9.80%** |
| disk | `JANG_4S` is **4.8% larger** than `stock4bit` (+146.3 MB) | `JANG_2L` is **36.0% smaller** than `stock4bit`, 38.7% smaller than `oq4`/`oq4e`, ≈44% smaller than `optiq` |
| peak footprint | no format-axis reading is published (the column spread is 127 MB in vMLX and is the runtime's own accounting in Osaurus) | `JANG_2L` **30.5%** under `stock4bit` in vMLX, **15.7%** under it in Osaurus, 38.3% under `optiq` |
| prompt processing | vMLX: 536.3 tok/s at a 2.450 s TTFT against `stock4bit`'s 463.6 at 2.834 s | vMLX: **+53.6% / +38.4%**; Osaurus: +0.8% / +2.8% on identical bytes |
| cost of the dense lead | `JANG_4S` declares 4.15 average bits against `stock4bit`'s uniform 4 — the one near-equal-precision pair in the artifact set | `JANG_2L` declares **2.37** average bits against ≈4 — **no equal-precision pair exists** |

Sources: `2026-09-17-jang-cross-runtime.md` `§1.1`, `§1.2`, `§3.1`–`§3.3`, `§6.1`–`§6.3`;
`2026-09-17-dense-jang-study.md` `§1.2`, `§3.1`, `§4.1`, `§6.1`, `§7.1`;
`2026-09-17-moe-jang-study.md` `§1.2`, `§3.1`, `§4.1`, `§6.1`, `§7.1`.

A two-coordinate system cannot answer the question the project exists to answer. "Is your serving
runtime or your quantization costing you speed and memory" has a third term: *and what is it
buying you*. The recommendation a reader takes away is different in each of three worlds that the
speed table cannot separate:

- `JANG_2L` buys 36% of the disk and 16–31% of the footprint for a decode tie, **and** holds
  accuracy → take the density.
- `JANG_2L` buys the same density **and** loses 3 accuracy points → the reader's own workload
  decides, and this study's job is to publish the exchange rate rather than a verdict.
- `JANG_2L` buys the same density **and** collapses on reasoning → the speed table was describing
  a broken artifact, and the correct publication is a **FAIL** with the sample, exactly as a
  token-salad cell is failed today.

Only the third of those is a floor violation, and the project already knows what a floor violation
looks like from the other side. Track 1's own words:

> The coherence gate … is **a floor, not an eval**: it says "this is language", never "this is
> right" (Track 1 design `§5.4`).

Track 2 is the eval. The gate stays where it is, as the floor beneath it.

### 1.2 The vendor claim this study tests

`JANG_2L` is a 2.37-average-bit bundle whose selling argument is that importance-weighted
quantization is not the same thing as uniform low-bit quantization — specifically, that it
**preserves reasoning fidelity, and reaches parity with or beats 4-bit MMLU**.

The claim, as this project's dispatch records it, is a claim about a **relation**, not about a
number: `score(JANG_2L) ≥ score(any 4-bit artifact)`. A relation is portable in a way a level is
not, and that is what makes it testable here at all. The vendor measures with its own harness,
very likely in-process, at its own few-shot configuration and its own item set; this project
measures over HTTP with its pins recorded. Those two measurements will never be comparable as
levels, and this study does not attempt it. What it can do is measure the relation **inside one
harness, one item set, one machine**, where every confound the vendor's and this project's setups
disagree about cancels because both sides of the comparison are measured the same way.

Three rules ride on that, and they are the reason this section exists:

1. **The exact wording of the claim is captured before it is tested.** The artifact's own model
   card and sidecar are read at spike time and quoted in the write-up beside the reading. Testing
   a paraphrase is how a study ends up refuting something nobody said.
2. **A failure to reproduce is not a refutation.** If `JANG_2L` scores below `stock4bit` here,
   the publishable sentence is "under this harness, at these pins, on this item set, the parity
   claim does not reproduce", with both pins published side by side. The vendor's own measurement
   may be entirely correct at its own pins.
3. **The claim is tested where it is falsifiable.** `JANG_2L` at 2.37 bits against an ≈4-bit
   artifact is the only comparison in the artifact set where a collapse is a live hypothesis. On
   the dense model the pair is 4.15 bits against 4.0, and the honest expectation is a small
   effect — which is exactly why the dense study's instrument has to resolve small effects (see
   `§5.2`), and the MoE study's instrument has to survive a large one.

### 1.3 The four questions

The dispatch names four. Each is a single comparison on the format axis, and each is answered by
one study below:

| # | question | study | the comparison it turns on |
|---|---|---|---|
| Q1 | **Vendor claim**: does `JANG_2L` at 2.37 bits reach or beat 4-bit MMLU? | 2B | `jang2l` vs `stock4bit` on MMLU, plus the same pair on the other three tasks |
| Q2 | **Quality trade for `JANG_4S`**: does a 14–17% decode lead cost subtle task degradation against uniform 4-bit? | 2A | `jang4s` vs `stock4bit` — the artifact set's one near-equal-precision pair |
| Q3 | **Pareto value of OptiQ**: did its latency and footprint penalty buy accuracy, or is it dominated? | 2A (Osaurus column), 2B, `§5.5` | `optiq` against every other format on the same runtime, on both axes |
| Q4 | **Mixed precision**: does outlier-channel protection (`oQ4` / `oQ4e`) buy task accuracy over stock 4-bit? | 2A, 2B | `oq4`, `oq4e` vs `stock4bit` on the same runtime |

Q3 is the only one that is not a pairwise reading. It is a **Pareto** question — "is this cell
dominated" — and it is answered by no single comparison. `§5.5` is the framework, and it is
deliberately not a score.

### 1.4 The single-variable invariant for evaluation

**Vary one thing at a time.** In Track 2, exactly one thing varies within a study: **the bytes of
the artifact.** A cell is `(format, runtime)` and its id is `"<label>__<runtime>"`, exactly as in
Track 1, and a study holds the runtime constant while the format moves. Everything else is a pin:

| held constant | value | where it is pinned |
|---|---|---|
| runtime | one per column | the column itself; `§2.1`–`§2.2` |
| task ids and their versions | four tasks, resolved from the installed harness | `§3.2` |
| item set | one pinned sample per task, identical for every cell | `§3.3` |
| prompt composition | few-shot count = each task's own default; one `fewshot_as_multiturn` setting; the artifact's own chat template, checked identical across the column | `§3.6` |
| generation | temperature 0, fixed seed, one cap per task | `§3.4`, `§4.2` |
| reasoning handling | one channel mode, one `</think>` treatment, one truncation policy | `§3.5` |
| harness | one `lm-eval` version, recorded per invocation | `§4.3` |
| scheduling | one campaign order, one cooldown, one load per cell per block | `§3.7` |
| cache state | `off` — every request a full prefill | `§4.2` |

Two things this invariant does **not** say, both of which matter:

- **It does not pin the model's behaviour.** A 2.37-bit model that stops emitting reasoning
  traces, or emits twice as many, is a *finding about the format* and is measured, not
  suppressed. The pin is on conditions; behaviour is the reading. What it obliges is that the
  behaviour is **reported** per cell (thinking rate, generation length, truncation rate, `§3.5`),
  so no score is read without it.
- **It does not put accuracy and speed in one run.** Track 1's numbers are not re-measured, and
  Track 2's runs never produce a rate. The two coordinates are joined by `(label, runtime)`, in
  prose and in tables, under `§5.6`'s rules.

### 1.5 What a completed study may say

At the end of Phase 2 the project must be able to say, for each model: *"in runtime R, on this
pinned item set with the harness named, format A scored X% on task T and format B scored Y%,
the paired difference is Δ with this interval, and — if the formats differ at all outside the
band — this is what the speed and the disk buy and cost."*

It may not say that a format is more accurate in general (two models, one harness, one machine),
it may not say that a quantizer "preserves reasoning" (that is the claim being tested, not a
conclusion to be borrowed), and it may not publish a ranking from inside the parity band, ever.

---

## 2. The test matrix

### 2.0 How a cell is read here

A cell is `(format, runtime)`; labels are Track 1's — `jang4s`, `jang2l`, `stock4bit`, `oq4`,
`oq4e`, `optiq` — so that a Track 2 row and a Track 1 row name the same artifact and can be set
side by side without a translation table. The label vocabulary is not cosmetic: it is what keeps
join guard 3 ("one format label pointing at two artifacts") meaningful if a machine ever joins
these runs, and it is what makes the Pareto tables of `§5.5` legible.

Three properties of Track 2's matrix are inherited from Track 1 and are not re-derived:

1. **A column is the format axis.** One runtime, several formats, runtime held constant. That is
   what every one of 2A and 2B's columns is.
2. **A row is the runtime axis.** One artifact, two runtimes — Study 2C, and nothing else.
3. **Dense and MoE are never joined.** The run record does not name the model, and the two
   campaigns keep the same label pointing at two different artifacts; they are separate
   campaigns in separate directories, read side by side in one document and never in one tool
   output (Track 1 design `§2.4`).

What is new in Track 2 is only this: a cell that Track 1 measured for speed and memory now also
carries a **score**. No cell is re-measured for speed.

### 2.1 Study 2A — the dense format axis, in two columns, covering five formats

`Qwen3.5-4B`. **No single runtime loads all five dense formats**, and this was measured, not
inherited: vMLX refuses dense OptiQ in 9.2 s with `Missing 297 parameters` because the artifact's
per-layer quantization map carries 249 entries and 0 of them are `vision_tower.*`, while Osaurus
lists dense `stock4bit` in `GET /v1/models` and refuses it at request time as `not installed or
registered with any provider` (Track 1 design `§2.1`, `§2.2`; `2026-09-15-grid-loadability-probe.md`).

So Study 2A is **two columns**, each a legal single-variable format axis, together covering all
five formats:

**Column A — runtime `vmlx` held constant (4 cells):**

| label | cell | artifact | Q it serves |
|---|---|---|---|
| `jang4s` | `jang4s__vmlx` | `JANGQ-AI/Qwen3.5-4B-JANG_4S` @ `4567967a…` | Q2 |
| `stock4bit` | `stock4bit__vmlx` | `mlx-community/Qwen3.5-4B-4bit` @ `0e7ffd5c…` | Q2 (the control) |
| `oq4` | `oq4__vmlx` | `RepublicOfKorokke/Qwen3.5-4B-oQ4` @ `3ae88a7d…` | Q4 |
| `oq4e` | `oq4e__vmlx` | `uingei/Qwen3.5-4B-oQ4e` @ `2e232d52…` | Q4 |

**Column B — runtime `osaurus` held constant (4 cells):**

| label | cell | artifact | Q it serves |
|---|---|---|---|
| `jang4s` | `jang4s__osaurus` | `JANGQ-AI/Qwen3.5-4B-JANG_4S` @ `4567967a…` | Q2, and 2C's dense row |
| `oq4` | `oq4__osaurus` | `RepublicOfKorokke/Qwen3.5-4B-oQ4` @ `3ae88a7d…` | Q4 |
| `oq4e` | `oq4e__osaurus` | `uingei/Qwen3.5-4B-oQ4e` @ `2e232d52…` | Q4 |
| `optiq` | `optiq__osaurus` | `mlx-community/Qwen3.5-4B-OptiQ-4bit` @ `6cb5bdfd…` | **Q3** |

Two things follow, and both are stated rather than discovered later:

- **`optiq` on the dense model is measured only on Osaurus.** The Pareto question Q3 is therefore
  answered on the dense model by the Osaurus frontier, and by the MoE frontier where `optiq__vmlx`
  does exist. The dense vMLX cell renders `—` with the vision-map reason, never a synthetic FAIL:
  a cell that was never attempted is not a measured failure (Track 1 design `§2.1`).
- **`stock4bit` on the dense model is measured only on vMLX.** The uniform-4 control for the
  dense model therefore comes from one runtime. A second dense control exists in none of the
  other runtimes: mlx-lm, oMLX and mlx-optiq load the four portables but load no JANG bundle and
  are not in this study at all (`§2.5`).

**Q2 is answered in Column A alone**, because that is where both halves of the near-equal-precision
pair live. Column B answers Q2's other half — whether the `JANG_4S` result transfers — only
against `oq4`/`oq4e`/`optiq`, and the write-up says so.

**Q3's Dense reading has a shape worth naming before it is measured.** On Osaurus the dense
portables are a 0.52% tie on decode (38.8 / 38.7 / 38.6 for `oq4` / `optiq` / `oq4e` — the
renderer's ranks 2/3/4 are not the measurement's claim) while carrying very different footprints
(2,466 / 2,472 / 2,216 MB) and very different disk (3.161 / 4.044 / 3.168 GB). If their accuracies
also tie, `optiq` is **strictly dominated on two axes** and the answer to Q3 is a clean "yes, and
it cost 28% more disk than either of the other two portables for nothing". That is a publishable
negative result, and `§5.5` is written so it can be published as one.

### 2.2 Study 2B — the MoE format axis, one complete column

`LFM2.5-8B-A1B`. All five MoE formats load in **both** runtimes, so this is the one place in the
project where a five-format column can be run with no structural hole (Track 1 synthesis `§2.2`).

The study runs **one column, runtime `vmlx` held constant**, and the reason is stated as a
pin-and-evidence choice rather than a preference:

| label | cell | artifact | Q it serves |
|---|---|---|---|
| `jang2l` | `jang2l__vmlx` | `JANGQ-AI/LFM2.5-8B-A1B-JANG_2L` @ `5fb82773…` | **Q1**, **Q3** |
| `stock4bit` | `stock4bit__vmlx` | `mlx-community/LFM2.5-8B-A1B-MLX-4bit` @ `146590a4…` | **Q1** (the comparator the claim names) |
| `oq4` | `oq4__vmlx` | `stamsam/LFM2.5-8B-A1B-oQ4` @ `acb4fd20…` | Q3, Q4 |
| `oq4e` | `oq4e__vmlx` | `brainworkup/LFM2.5-8B-A1B-oQ4e` @ `88977e47…` | Q3, Q4 |
| `optiq` | `optiq__vmlx` | `mlx-community/LFM2.5-8B-A1B-OptiQ-4bit` @ `5a5c5958…` | **Q3** |

**Why vMLX holds the column.** The MoE campaign ran five formats in each runtime and its vMLX
column is the one that produced **zero FAILs** and zero structural holes; the Osaurus column
produced two decode-workload FAILs (`oq4e`, `optiq`, both `token_source='none'` on the 512-token
shape — `2026-09-17-moe-jang-study.md` `§4.1`). A runtime whose long-generation accounting fails
on two of five artifacts is a runtime whose benchmark client would be spending retries inside
the measurement, and the accuracy study's generation lengths are *longer* than any workload
Track 1 ran. The second reason is the first reason restated in Track 1's own numbers: `JANG_2L`
ties `stock4bit` on decode in vMLX (+0.87% / −0.50%) and loses to it in Osaurus (−5.12% /
−9.80%). **vMLX is where the two artifacts are indistinguishable on speed, so accuracy is the
only thing that separates them** — which is precisely the question Q1 asks.

One MoE caveat travels with the column and is printed beside every Pareto table that uses it:
`oq4__vmlx` published a **+76.0% drift** on decode, so its 65.6 tok/s narrates its window more
than its artifact (MoE `§3.1`). Its accuracy score is unaffected — the score does not depend on
the speed coordinate — but the *speed* coordinate of that one cell carries the annotation into
`§5.5`'s plot, and the write-up may not read `oq4`'s frontier position as a property of `oq4`
alone.

**Why the MoE Osaurus column is not run.** MoE-Osaurus `oq4e` and `optiq` have **no speed
coordinate at all** — their decode rows FAIL — so a MoE-Osaurus Pareto frontier would be three
points and two holes, and the column would double the campaign's cost to answer Q1 twice. What
2C does instead is the cheap version of the same check: the JANG artifact alone, in both
runtimes, on one task (`§2.3`).

### 2.3 Study 2C — the cross-runtime numerical-consistency reading

Same bytes, two loaders. Track 1 read this row for speed and found the two implementations differ
by +27.5% / +28.5% on dense decode and by a tie-or-+4.70% on MoE decode, while differing by
roughly 2× on MoE prompt processing (`2026-09-17-jang-cross-runtime.md` `§4.1`–`§4.3`). Track 2
reads the same row for answers.

**The formulation, stated carefully.** The dispatch's framing is "verify that custom loader
unpacking kernels produce bit-for-bit identical or numerically consistent accuracy". What this
harness can observe is narrower than "bit-for-bit identical kernels" and wider than an accuracy
delta, and the difference is the whole value of the study:

- **Observable:** with `temperature 0`, the same pinned items, and one load per cell, each
  runtime produces a final answer string per item. The **per-item answer-agreement rate** between
  the two runtimes on the same artifact is a direct, high-resolution instrument: an accuracy
  delta over 250 items is one number with a ±4 pp interval, while an agreement rate is 250
  comparisons and detects a single differing item.
- **Not observable here:** whether the two loaders compute bitwise-identical activations. Nothing
  in this project reads a tensor, and no measurement over HTTP can see inside a kernel. The
  study publishes the answer-agreement rate and never promotes it to a claim about kernels.

**What 2C runs** (both are small, and the dense half is free — 2A already produces it):

| row | artifact | cells | items |
|---|---|---|---|
| MoE JANG | `JANG_2L` @ `5fb82773…` | `jang2l__vmlx` (from 2B) + `jang2l__osaurus` (new) | one task, pinned: ARC-Challenge 250 |
| dense JANG | `JANG_4S` @ `4567967a…` | `jang4s__vmlx` (2A) + `jang4s__osaurus` (2A) | the same |
| dense portables | `oq4`, `oq4e` | both runtimes (2A) | the same |

**Pre-registered interpretation rules:**

1. The published quantity is the **agreement rate** `A = (items answering identically) / n`, with
   the per-item disagreements kept in the raw record and the first disagreement quoted in the
   write-up.
2. **No cross-runtime accuracy ordering is ever published from 2C.** Two cells on a row is a
   comparison, not an ordering — Track 1's rule, unchanged (Track 1 design `§2.3`).
3. A cross-runtime accuracy claim anywhere in Phase 2 (the only candidate is "does the `JANG_4S`
   result transfer between loaders?") is published **only** with its agreement rate beside it. If
   `A < 99%`, the runtimes are a live confound for that artifact, both numbers are printed, and no
   cross-runtime reading is drawn from them. 99% is a pre-registered choice, not a measurement;
   the rate is what the study reports either way.
4. **A disagreement is a finding about the pair**, never a bug to be smoothed. The write-up names
   the item and the two answers.

### 2.4 The ten artifacts, verified on disk today

All ten were re-verified today with the harness's own function — the one whose return value is
written into every Track 1 record's `disk_bytes` — and every size below matches the Track 1
inventory byte for byte. **Zero downloads are required for this study.**

Recompute:

```sh
python3 - <<'PY'
import os, sys; sys.path.insert(0, '.')
from ohyesmlx.measure import artifact_bytes
H = os.path.expanduser('~/.cache/huggingface/hub')
for repo, snap in [
  ('JANGQ-AI/Qwen3.5-4B-JANG_4S',             '4567967a46cd9e9bf26d3bb491ddd422ad607775'),
  ('mlx-community/Qwen3.5-4B-4bit',           '0e7ffd5c629ef7719d4cbc04069232580bfa9d9c'),
  ('RepublicOfKorokke/Qwen3.5-4B-oQ4',        '3ae88a7d17b1c6bb71b795c1090948a82508fdb8'),
  ('uingei/Qwen3.5-4B-oQ4e',                  '2e232d525d5df5e7a6eece4b03b17087e6b3c3ac'),
  ('mlx-community/Qwen3.5-4B-OptiQ-4bit',     '6cb5bdfd0bf15f484881fb9f1ab6d7c840fddde9'),
  ('JANGQ-AI/LFM2.5-8B-A1B-JANG_2L',          '5fb82773427c2f25395de8821eff6d95e86feb53'),
  ('mlx-community/LFM2.5-8B-A1B-MLX-4bit',    '146590a491db88581884033023f51f6b49a27b89'),
  ('stamsam/LFM2.5-8B-A1B-oQ4',               'acb4fd209565b7c05de287488416f4217820a3db'),
  ('brainworkup/LFM2.5-8B-A1B-oQ4e',          '88977e47cd1fe2eb5ec5bf5230d3de9868adef9e'),
  ('mlx-community/LFM2.5-8B-A1B-OptiQ-4bit',  '5a5c595823cf26ab1068508eb5cf85816bb2db6b'),
]:
    print(repo, artifact_bytes(os.path.join(H, 'models--' + repo.replace('/', '--'),
                                            'snapshots', snap)))
PY
```

Run today, it prints the ten byte counts in the table below and **39,948,257,890** as their sum.

`files` is the walked file count; `bytes` is the distinct-inode sum. `GiB` is binary, `GB`
decimal, both given because two v1 documents print decimal GB for these same artifacts.

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

Totals, re-summed today: dense **16,640,647,100 B**, MoE **23,307,610,790 B**, both
**39,948,257,890 B**.

**Declared bits**, which is the column the accuracy study is really about:

| label | declared precision | declared widths | block | source |
|---|---|---|---|---|
| `jang4s` | **4.15** average (`target_bits` 2.5) | `quantization.bit_widths_used: [4, 6]` | 64 | sidecar `jang_config.json`, sha256 `3a9bf087…beebe2abcd` (re-verified today) |
| `jang2l` | **2.37** average (`target_bits` 2.0) | `[2, 6, 8]` **+ 18 passthrough tensors at 16** (`passthrough_bit_widths_used`) | 64 | sidecar `jang_config.json`, sha256 `858385d1…1a26f610` (re-verified today) |
| `stock4bit` | 4.0 uniform (declared) | — | — | artifact name and `config.json`; read at spike time |
| `oq4`, `oq4e` | ≈4, **mixed** (per-layer map; no published average) | — | — | Track 1 design `§3.1a`; dense study `§5.1` |
| `optiq` | ≈4, **mixed** (no published average) | — | — | Track 1 design `§3.1a`; dense study `§5.1` |

Three facts from that table are load-bearing for Track 2 and are not incidental:

1. **`jang4s` vs `stock4bit` is the only near-equal-precision pair in the set** — 4.15 against
   4.00, on an artifact that is 4.8% *larger*. Q2 is therefore the one question in this study
   whose answer can be attributed to the quantizer rather than to the bit count, and it is the
   reason 2A's instrument must resolve small differences.
2. **`jang2l` vs anything is a 2.37-against-≈4 comparison by construction**, and the sidecar's
   `actual_bits` is an average over the bundle, not over the tensors decode touches —
   `[2, 6, 8]` says three widths are present and names no module. Every score in Study 2B is
   published beside the declared bits and the measured bytes, and no explanation is offered that
   depends on a per-module byte count nobody measured (Track 1 design `§3.2`).
3. **The dispatch's dense hierarchy is v1's, and Track 1's columns order differently.** The
   dispatch's dense ordering `JANG_4S > stock4bit > oq4 > oq4e > optiq` is v1's
   (`2026-09-16-phase5-joined-grid.md`, where the portables ran `stock4bit` 75.6 > `oq4` 73.3 >
   `oq4e` 66.7 in vMLX and `oq4` 68.7 > `oq4e` 64.7 > `optiq` 63.5 in Osaurus); Track 1's
   re-measured dense vMLX column orders the portables `oq4` 47.6 > `oq4e` 46.0 > `stock4bit` 44.2,
   and its Osaurus column ties all three at 38.6–38.8. Nothing about Track 2 changes because of
   this, and nothing here joins the two grids: the speed coordinate of a Pareto table is **that
   cell's own Track 1 figure from its own column**, never a figure carried across pin sets.

### 2.5 The ragged edges, and why each is a measurement rather than a gap

| hole | what a reader might assume | what is true | evidence |
|---|---|---|---|
| dense `optiq__vmlx` | "vMLX cannot read OptiQ" | vMLX reads the **MoE** OptiQ; on the dense checkpoint its multimodal path requires 297 vision parameters the artifact's per-layer map omits (0 of 249 entries) | `2026-09-15-grid-loadability-probe.md`; Track 1 design `§2.1` |
| dense `stock4bit__osaurus` | "Osaurus cannot read stock 4-bit" | listed in `GET /v1/models`, refused at request time as `not installed or registered with any provider`; the MoE stock-4bit serves | `2026-09-15-grid-loadability-probe.md`; Track 1 design `§2.2` |
| dense `*__mlxlm`, `__omlx`, `__optiq` | "not tested" | tested in v1 and refused: shape error (mlx-lm), HTTP 409 (oMLX), hang (mlx-optiq) | `2026-09-15-grid-loadability-probe.md`; `2026-09-16-moe-loadability-probe.md` |
| MoE Osaurus column | "not tested" | run for speed in Track 1; **not run here**, because two of its five decode rows have no speed coordinate and it would double the campaign to answer Q1 twice | `2026-09-17-moe-jang-study.md` `§4.1` |

**Label discipline across the two models.** `stock4bit`, `oq4`, `oq4e`, `optiq` each name two
different artifacts — one dense, one MoE — exactly as in Track 1. The MoE and dense campaigns are
separate directories, joined separately if ever joined; a document may print them side by side
and this one does.

### 2.6 Replication, and the tie band inherited from Track 1

The rules were written before Track 1's data existed and are applied here unchanged (Track 1
design `§2.5`):

- **Tie band (speed):** adjacent cells within **2.5%** are a tie. It is the largest gap v1
  observed to change places when the measurement window moved.
- **R-reproduce:** a replicate landing more than **5%** from its primary on the same cell is
  published with both figures and no ordering.
- **R-nothing:** no replicate may be discarded for being inconvenient.

For Track 2 those rules apply to the **speed coordinates**, which are quoted rather than
re-measured, and to the **seconds-per-item** drift check of `§3.7`. They do not apply to an
accuracy score, which has its own interval arithmetic (`§5.2`) — a distinction the write-up must
make every time it prints a Δ beside a tok/s figure.

**What gets a replicate in Track 2.** Mirroring Track 1's economy — replication is for the cells
that carry the claim, not for the ones that describe the column:

| study | replicate | why |
|---|---|---|
| 2A | `jang4s` + `stock4bit` on vMLX, and `jang4s` on Osaurus, on **MMLU** only | Q2's decisive pair, on the one task where a small effect is resolvable |
| 2B | `jang2l` + `stock4bit` on vMLX, on **MMLU** only | Q1's decisive pair |
| 2C | none | the row is a comparison across runtimes on one item set; a second visit measures the harness, not the loaders, and the agreement rate already reports per-item stability within a visit |

The replicate is a **second visit in a different campaign block, with the cell order reversed**,
and it is what turns a Δ into a **difference** reading under `§5.3` rather than a single visit's
point estimate. Its MMLU budget is the full pinned set, because a replicate on a smaller subsample
cannot answer the question it exists to answer.

---

## 3. The benchmark suite and the evaluation protocol

### 3.1 Task selection

Four tasks, each pricing a different failure mode, each named by the dispatch:

| task | what it prices | why it is in this study | floor |
|---|---|---|---|
| **MMLU** (generative) | knowledge breadth, multi-subject multiple choice | **the vendor's own benchmark** — Q1 is stated in MMLU points, so the claim cannot be tested anywhere else. 57 subjects also makes it the one task where a small Δ is resolvable at the budget of `§3.3` | 25% (4-way) |
| **GSM8K** | multi-step chain-of-thought arithmetic | the failure mode that a 2.37-bit MoE is most likely to exhibit is a *broken chain*, not a missing fact — a model that has lost its arithmetic can still score respectably on recall-shaped questions | 0 (exact match) |
| **ARC-Challenge** | reasoning under adversarial distraction | the distractor-shaped version of the same question; ARC-C items are chosen because retrieval alone does not answer them | 25% (4-way) |
| **IFEval** | instruction-following, programmatically verified | the format axis's effect on *obedience* rather than knowledge, and the only task here whose metric is not an answer match. A quantizer that damages long-range instruction adherence shows up here and nowhere else | 0 (strict) |

**What is deliberately not run, and why.** Perplexity is not a task and is not run — the road-map
says so ("every published format comparison either changes the runtime too, is vendor
self-reported, or measures perplexity instead of task accuracy", `.paul/ROADMAP.md`). HellaSwag
was a candidate in the hand-off's preliminary scope and is dropped: it is a fourth
multiple-choice task with the same failure mode as ARC-Challenge, and at this campaign's cost
(`§6.1`) a redundant task is a task that removes a format from the matrix. Long-context recall,
tool use, and code generation are out of scope and named in `§7`.

**No task pooling, ever.** The four tasks are four readings and are never averaged into one
number (§5.4).

### 3.2 What `local-chat-completions` can serve, and what it cannot

The endpoint model is fixed by the dispatch:

```
--model local-chat-completions --model_args base_url=http://127.0.0.1:<port>/v1,model=<resolved id>
```

The consequence has to be stated, because it changes which tasks are runnable:

- The chat-completions path serves **`generate_until`** requests. A task whose metric is computed
  from token log-probabilities (`loglikelihood`, and therefore `acc_norm`) cannot be served
  through it — the endpoint returns no usable logprobs for a continuation, and the harness has no
  way to score one.
- Therefore **every selected task is run in its generative form**, and the primary metric per
  task is the generative one: `exact_match` for the multiple-choice generative variants, the
  answer-match metric for GSM8K, and `prompt_level_strict_acc` for IFEval.
- **Task ids are pinned against the installed harness's own registry at spike time**, never from
  documentation or memory. `lm_eval --tasks list` (or the installed version's equivalent) is
  enumerated in Plan 02-01, the exact id for each task and its version hash are recorded, and
  that is the pin. `AGENTS.md`'s rule applies with full force: a claim that a task does not exist
  in generative form needs evidence from the installed registry, not the absence of a familiar
  name.
- **What the spike must fall back to if the generative variant is absent.** It is not a
  workaround — there isn't one that keeps the single-variable rule intact. The task is dropped
  and the substitution is recorded, or the study is re-scoped. An `acc` computed by a different
  mechanism is a different task and may not be merged into a column.

### 3.3 The sample budget, and the resolution it buys

Full MMLU is 14,042 questions (dispatch). Running it across ten format-cells is where this
campaign would die, so the budget is pinned — but the pin has to be on the **item count**, not on
the flag, and here is why.

**The `--limit` trap.** `--limit N` limits the number of examples **per task**, and for a grouped
task every subtask is a task. On the MMLU group, `--limit 250` therefore means up to 250 items
*per subject* across 57 subjects — well over twelve thousand requests, i.e. most of the full
benchmark, not 3% of it. The dispatch's "`--limit 250` or `--limit 500` per task" is exactly
right about what the flag says and exactly wrong about what the item count is on a group, and the
difference is a factor of 57. **This is why the design pins items and requires the spike to
count them** (`§4.5`): the invocation is audited against the item budget by reading the harness's
own result JSON, and a mismatch stops the campaign before a format is scored under a pin nobody
intended.

**The pinned budget:**

| task | universe | pinned budget | form | why this number |
|---|---|---|---|---|
| MMLU (generative) | 57 subjects; 14,042 items total | **40 items per subject = 2,280** | all 57 subjects, first 40 by the task's own doc order | preserves the macro-average-over-subjects structure that "an MMLU score" means; 40 is below the smallest subject's own size (the smallest subjects carry ~100 items — **confirmed at spike time from the installed registry before the campaign starts**, and if any subject were smaller than 40 that subject contributes its whole set and the fact is recorded) |
| GSM8K | 1,319 test items | **250** | first 250 by doc order | the dispatch's budget; its generations are the longest per item, so these 250 items cost more than the count suggests |
| ARC-Challenge | 1,172 test items | **250** | first 250 by doc order | the dispatch's budget, unchanged |
| IFEval | 541 prompts | **250** | first 250 by doc order | the dispatch's budget, unchanged; short generations |
| **per cell** | | **3,030 items** | | |

The `universe` column is what these tasks are recorded as in this project's dispatch and prior
art (14,042 items over 57 subjects; 1,319 / 1,172 / 541 for the other three). **The spike confirms
every one of those counts — and each subtask's own size — from the installed harness's own
registry before the campaign starts**, because a harness version can add or remove items and the
budget is stated in items either way.

**Identical items across every format, and proved rather than assumed.** Same task id, same
version, same `--limit`, same `--seed`, same doc order ⇒ the same items. Proved per (cell, task)
by hashing the item identity from the harness's `--log_samples` output — the sorted `doc_id` list
if the installed version writes it, otherwise the concatenation of each item's target and
rendered prompt, whichever the spike finds (the field set used is recorded in the manifest). Two
cells whose per-task identity hashes differ are **not comparable** and the runner refuses the
pair. This check is what makes the paired instrument of `§5.2` legal; without it, the comparison
silently degrades to an unpaired one and the interval widens by a factor of several.

**The resolution that budget buys.** For a single score, `p̂ = k/n` and

```
SE(p̂) = sqrt(p̂ (1 − p̂) / n)
```

but the study's primary instrument is the **paired** difference between two formats on identical
items (`§5.2`), whose standard error is much smaller because item difficulty cancels:

```
Δ = (b − c) / n          b = items format A got right and B wrong
SE(Δ) ≈ sqrt(b + c) / n  c = items format B got right and A wrong
```

with the exact (binomial) interval used when `b + c < 25`, where the normal approximation is not
trustworthy. Worked out for the two budgets this campaign actually uses:

| n | discordance `(b+c)/n` | `b + c` | `SE(Δ)` | 95% CI half-width |
|---|---|---|---|---|
| 250 | 10% | 25 | 2.00 pp | **±3.9 pp** |
| 250 | 20% | 50 | 2.83 pp | ±5.5 pp |
| 2,280 | 10% | 228 | 0.66 pp | **±1.3 pp** |
| 2,280 | 20% | 456 | 0.94 pp | ±1.8 pp |

For comparison, the unpaired standard error at `p ≈ 0.5` is 3.16 pp at n=250 and 1.05 pp at
n=2,280 — so pairing is what makes the difference measurable at all, and **it is only at MMLU's
2,280 items that the ±1.5 pp parity band of `§5.1` is resolvable, and only in the typical
discordance range.** A 250-item task cannot resolve a 1.5 pp difference even paired. The design
says so now, in advance, so that the write-up cannot present a 250-item tie as evidence of
parity: it is an indeterminate reading and it is published as one (`§5.2`).

**The budget dial, pre-registered.** The item budget may be revised **downward exactly once**,
before 2A's first cell runs, and only on the spike's measured seconds-per-item (`§6.1`): MMLU's
per-subject count goes 40 → 20 (1,140 items), and nothing else moves. Generation caps, task
composition, sample mechanism and pin set are **not** dials — changing them changes what the
number means, while changing the item count changes only its precision. The consequence of the
dial is published with the revision: at 1,140 items the CI half-width is ±1.8 pp at 10%
discordance, the band is no longer resolvable for sub-2 pp effects, and more comparisons land in
the indeterminate bin. **Halving precision is a cost; changing meaning is a defect.**

### 3.4 The wire protocol

One request per item, issued by the harness against the runtime's OpenAI-compatible endpoint:

| element | pin | why |
|---|---|---|
| endpoint | `http://127.0.0.1:<port>/v1/chat/completions` via `--model local-chat-completions` | the dispatch's endpoint model; every runtime here speaks it |
| `model` | the **resolved** `Handle.model_id`, not the path | each runtime names the same weights differently, and a wrong id is a 404 the harness may retry into a timeout rather than report |
| `temperature` | `0.0` | the project's standing pin; also the model type's own default, which the spike confirms reached the request from the runtime's log |
| `seed` | fixed, recorded | forwarded if the model type forwards it; **if it does not, that is declared rather than assumed** — at temperature 0 the answer is greedy and the seed is belt-and-braces, but an unforwarded pin that nobody checked is exactly the class of defect this project keeps finding |
| `max_tokens` (per task) | the cap of `§3.5` | set once from the spike's length distribution and never per cell |
| `stream` | **off** | no metric here is a timing, and streaming only adds a chunk-reassembly surface (the oMLX one-delta and mirrored-channel traps are *streaming* traps). Non-streaming responses carry the same channels, and the spike verifies the channel rule of `§3.5` against them |
| concurrency | **1** | Phase 6 measured that none of these five runtimes batch (N=8 aggregate gains 0.99–1.15×, TTFT in proportion), so concurrency buys time and costs queueing. Pinned at 1 for every cell, and the spike confirms it from the server-side request timeline |
| timeouts / retries | recorded, not guessed | a retry is a hidden re-request. The harness's retry behaviour is read from the installed version in the spike, pinned in the manifest, and **reconciled against the runtime's own request count**: items sent must equal requests served. A mismatch is a FAIL for that cell — the project's "never report an unreconciled number" rule, applied to a benchmark client |
| tokenizer | the artifact's own (`tokenizer=<artifact_dir>`) | the harness tokenizes with the serving model's tokenizer, exactly as `TokenCounter` does in `measure.py`. A cell whose tokenizer cannot be built is **N/A** with the reason, never a silent fallback — the rule `_visit` already enforces |

**Prompt composition and the chat interface** (`§3.6`) is the other half of the wire protocol and
is pinned there because it is the most likely place for a silent second variable.

### 3.5 Reasoning traces: `<think>`, the channel trap, and truncation

This is the section that decides whether the study produces numbers or a green run full of zeros.
The project has already paid for the lesson once, in the other direction.

**The trap, in the project's own words.** `docs/interfaces.md` records that mlx-lm 0.31.3 and
vMLX 1.6.59 are **reasoning-only on a thinking model** — the answer arrives in the reasoning
channel and `delta.content` is empty — and that before this was handled, *all 24 of their grid
rows failed with "no content-delta timing"*. The project's own client reads the reasoning channel
when content is empty (`measure._judged_text`, `transport`'s mirrored/reasoning-only rules).
**`lm-evaluation-harness` has no such rule.** It reads `choices[0].message.content`. A cell that
answers entirely in the reasoning channel would therefore score **0%**, with no error raised
anywhere, on a run that looks perfectly healthy. That is the 256-expert token-salad incident one
layer up: a plausible-looking number from a machine that was never answering the question.

**The three mechanisms, and which one is a pin:**

1. **`think_end_token="</think>"`** (the dispatch's mechanism) tells the harness to treat a
   reasoning block as a preamble and score only what follows it. That is the right treatment for
   an artifact that emits `<think>…</think>answer in content`, and it is pinned in `--model_args`
   for every cell.
2. **The channel rule.** `think_end_token` does nothing for a runtime that puts the *whole*
   answer in `reasoning_content` and leaves `content` empty. The answer channel is a property of
   the runtime build and the model, and it is **validated per (runtime, model, artifact) in the
   spike**, with a canary question whose answer is known, before any cell is scored. The canary's
   request and full response — every channel, verbatim — is kept in the spike's record.
3. **The switch, if the canary fails.** Where a runtime offers a way to make the model answer in
   `content` (Osaurus's per-model `disableThinking` key in the app plist is one such switch; it
   already exists in Track 1's confound ledger, item 11), that switch becomes a **per-cell pin**:
   its value is verified for *this artifact's* model id before the cell runs, the check is
   recorded, and a cell whose switch cannot be set the same way as its column-mates is **N/A**
   with the reason. Whether a switch exists for each runtime/model pair is a **source-reading
   question for the spike** — and `AGENTS.md`'s rule governs it: the absence of a flag is not
   evidence that the setting does not exist.

**The pin is on conditions, never on behaviour.** Whatever the reasoning mode is, it is identical
in mechanism across the column, and the model's *use* of it is measured and published per cell:

| published per (cell, task) | definition | why it matters |
|---|---|---|
| **thinking rate** | fraction of scored responses containing a reasoning block | a format that stops reasoning is a quality finding, and it must be visible beside the score |
| **mean generated tokens** | per response, from the runtime's own `usage` where available | the cost of the answer, and how close it runs to the cap |
| **truncation rate** | fraction of responses whose generation reached the cap | a truncated response is a wrong answer that is not a knowledge failure |
| **parse-failure rate** | fraction of responses the task's filter could not extract an answer from | the harness-side analogue of an incoherent cell |

**The truncation rule, pre-registered.** The cap per task is set in the spike from the measured
length distribution — above the 99th percentile of the spike's per-task generation length, so that
a complete trace is not cut off. A cell whose truncation rate exceeds **5%** is a **FAIL** with
the rate and a sample published, and no score is read from it: its score measures the cap, not the
format. A cell under 5% publishes the rate beside its score.

### 3.6 Prompt composition

The composition is the harness's, pinned in three places, and the third one is a Track 2
discovery waiting to happen:

1. **Few-shot count.** `--num_fewshot` is **not passed**: each task runs at its own declared
   default (the conventional configurations are 5-shot for MMLU and GSM8K, 25-shot for
   ARC-Challenge and 0-shot for IFEval — **the spike records the effective value from the
   harness's resolved config and that recorded value is the pin**). Overriding a default is a
   second variable; inheriting it and recording it is a pin.
2. **How the shots are presented.** One `fewshot_as_multiturn` setting, chosen once in the spike
   and frozen. The spike prices the choice on one format and one task — both settings, same items,
   the two scores recorded — so the pin is a measurement rather than a preference, and then it is
   the same for all ten cells and every task.
3. **The chat template is the artifact's own, and five artifacts of a column may not carry
   identical ones.** The runtime applies its own server-side template; that string lives in each
   artifact's `tokenizer_config.json`. Two artifacts with different templates are two different
   prompts, and the difference would land in the score with nothing in the table saying so. The
   spike therefore compares the chat-template string across the five artifacts of each study and
   records the result:
   - **identical** → the column is clean on this axis, and the digest of the shared string is
     recorded;
   - **not identical** → the column carries a **declared prompt-composition difference**, it is
     printed above every score of that study, and no column-level claim is published from it.
     The alternative — normalising the template — is a code change to the runtime's prompt path
     and is out of scope for this study.

### 3.7 Thermal protection and campaign shaping

An M2 Max in a laptop chassis throttles under sustained inference, and this campaign is the
longest the project has attempted (`§6.1` estimates tens of hours). The protections, all of them
structural rather than hopeful:

1. **One load per cell per block.** `measure.py`'s rule is reused exactly: a visit starts the
   runtime **once** and runs every task under that one load, then stops it. Ten cells × one load
   per block, never one load per task.
2. **Cell-major blocks, with the order rotated.** Each block runs one cell's four tasks under one
   load, and the campaign's cell order is **rotated between passes** — the format walked first in
   one pass is walked last in the next — so a thermal step cannot land on one format's whole
   score. This is `visit_plan`'s alternating order at campaign scale, and it is also why a
   replicate cell is re-visited in a different position rather than re-run in place. A cell is
   never split across blocks: splitting it would mean four loads instead of one and four thermal
   windows instead of one.
3. **A 30 s cooldown between invocations that produced requests**, matching the harness's own
   `cooldown_s` pin. A cooldown after a failed start is 30 seconds spent cooling nothing; it is
   skipped.
4. **Nothing else runs on this machine** while a block is measured. Not a test suite, not a git
   operation, not a download, not "lightweight" background work. The harness cannot detect
   contention; the discipline holds without enforcement, and it has already cost this project one
   column.
5. **Drift is measured on seconds-per-item.** Every invocation records wall-clock and items, so
   the derived rate is comparable across the whole campaign. A replicate landing more than **5%**
   from its primary on the same (cell, task) is annotated and explained, never smoothed — the
   rate's sensitivity to prompt length makes it a blunt instrument, which is why it annotates and
   never fails.
6. **Sessions are recorded, and blocks are resumable.** Each (cell, task) invocation is an
   independent unit with its own manifest line, so a campaign can span evenings. The session id
   and start/stop timestamps ride in the manifest, and the write-up prints which block produced
   which score — a campaign that spans sessions and hides it is a campaign whose thermal history
   is missing.
7. **One runtime holds weights at a time.** Between blocks the runtime is stopped by
   `Handle.stop()`, which does not return until the port is free, and the ports are swept. Ports:
   vMLX 8000, Osaurus 1337 (and, for the record, mlx-lm 8081, `optiq` 8080, oMLX 8100).

### 3.8 The raw record

Two rules from the project's founding apply to Track 2 without modification, and they decide the
record's shape:

> **Raw observations are never discarded or truncated. The record keeps what was sent, including
> the sample that failed.**

So, per invocation, the campaign keeps:

| artifact | what it is | who reads it |
|---|---|---|
| `manifest.jsonl`, one line per invocation | the pins, in one place: cell, task id + version hash, harness version, start command, runtime version, `model_args`, effective `num_fewshot`, effective cap, item count, item-identity hash, cache state, scores with their metric names, thinking/truncation/parse rates, seconds per item, session id, runtime log path | a reader with `jq`, and the synthesis |
| the harness's own results JSON, verbatim | `lm_eval`'s output file — it carries the harness's resolved `configs`, its own git hash and date. This is the **pin evidence**, archived whole rather than re-typed | the write-up, and anyone auditing a pin |
| the harness's `--log_samples` output, verbatim | **every item's** prompt-side identity, target, raw response and filtered response. This is the raw observation of Track 2; a summary of it is not | the paired analysis of `§5.2`, the agreement check of 2C, and the failing sample a FAIL publishes |
| the runtime's log for the block | the loader's own lines, the request trace, the version | the reconciliation check of `§3.4` and the channel check of `§3.5` |

**Nothing in `ohyesmlx/` is modified for this.** There is no new module, no new field in
`results.jsonl`, and no second writer for a run record — `measure.py` owns that record and Track
2 does not pretend to write it. The manifest is the campaign's own file in its own directory
(`results/accuracy/<campaign>/`), which is the same economy Track 1's runner logs used.

---

## 4. The confound ledger and experimental controls

### 4.1 The ledger

Every confound this study knows about, what it would fake, the pin that answers it, and the
evidence a reader can check afterwards. A confound with no pin is listed as unpinned — that is
what makes the ledger honest.

| # | confound | what it would fake | the pin | evidence left behind |
|---|---|---|---|---|
| 1 | **Precision / size** — `jang2l` at 2.37 bits against ≈4 | a packing or loader effect where a bit-count effect is doing the work | no pin equalizes them. Every score is published beside `actual_bits`, `bit_widths_used`, block size and measured `disk_bytes`; the **dense** `jang4s`/`stock4bit` pair is the one near-equal-precision comparison (`§2.4`) | the sidecar's declared fields (digests in `§2.4`), the artifact sizes, printed beside every score |
| 2 | **Reasoning channel** — a runtime that answers in `reasoning_content` and leaves `content` empty | a format scoring 0% with no failure raised, on a green run | the per-(runtime, model, artifact) canary of `§3.5`, validated in the spike before any cell is scored | the canary's full response, kept verbatim in the spike's record; the per-cell thinking rate |
| 3 | **Truncation** — a cap set below a format's reasoning length | a knowledge failure where the cap cut the answer | the cap set from the spike's 99th-percentile length; the **5% truncation FAIL** rule | per-cell truncation rate and generated-token distribution, in the manifest and beside every score |
| 4 | **Prompt composition** — shots, shot presentation, chat template | a format difference that is a prompt difference | one `num_fewshot` (each task's default), one `fewshot_as_multiturn`, and the chat-template comparison across the column's five artifacts (`§3.6`) | the harness's resolved `configs` in its own results JSON, archived verbatim; the template comparison and digest in the manifest |
| 5 | **Item-set drift** — two cells scored on different items | a Δ from different questions rather than different weights | one task id + version, one `--limit`, one `--seed`, one doc order, **proved** by the per-(cell, task) identity hash (`§3.3`) | the identity hash on every manifest line; the raw `--log_samples` file per invocation |
| 6 | **Sampling** — temperature, seed, retries | a stochastic difference read as a format difference; a retried request that hides a failure | temperature 0; seed pinned and *verified as forwarded*; the harness's retry behaviour recorded and reconciled against the runtime's request count (`§3.4`) | the harness's `configs` block; the reconciliation counts; the runtime log |
| 7 | **Task ids and versions** — a harness update renames or revises a task | two "MMLU" runs that are not one task | task ids and their version hashes pinned at spike time from the installed registry (`§3.2`) | each invocation's own results JSON, which names the task and its version |
| 8 | **Harness version** — `lm-eval` moves under `--isolated` | a score difference from a filter change | one `lm-eval` version, recorded per invocation; the environment is warmed in the spike and the campaign runs offline (`§4.3`) | the version string in every manifest line; the harness's `git_hash` in its own output |
| 9 | **Runtime version** | a version step read as a format effect | `Handle.version` recorded per block; a campaign spanning two versions of one runtime is refused — the grid's guard 4, applied to a campaign | `runtime_version` per block, in the manifest and the write-up |
| 10 | **Osaurus host state** — cache keys, residency, the per-model thinking switches | any Osaurus cell becoming unattributable the moment a setting moved | byte-exact backup/restore with `cmp -s` verification, the drift guard against `config/osaurus-settings-baseline.json`, residency 900 s, `cache_state off`, and the per-artifact thinking-switch check (`§4.4`) | runner log: the toggle, the restore line, the `cmp` result; `shasum -a 256` of both settings files before and after each cell |
| 11 | **Cache state** — a prefix hit changes what a request did | two cells measured under different prompt-processing conditions | `cache_state: off` for every cell of every study (`§4.2`) | the start command in the manifest; the runtime's own cache line per block |
| 12 | **Concurrency / queueing** | a timeout or a latency artefact read as an answer difference | concurrency 1, confirmed from the server-side request timeline in the spike | the spike's timeline; the request reconciliation |
| 13 | **Thermal / session drift** | a thermal curve wearing a format's name | cell-major blocks with the cell order rotated between passes, 30 s cooldowns, session ids, the seconds-per-item drift check (`§3.7`) | the per-invocation seconds-per-item series; session boundaries in the manifest |
| 14 | **Contamination** — these benchmarks are public and predate every artifact | an absolute score read as capability | **no pin.** Declared: the study's interest is *differences between formats on the same items*, which contamination cannot manufacture | stated in every write-up; no absolute-capability claim is published |
| 15 | **Cross-runtime numerical difference** — two loaders, same bytes | a loader difference read as a format difference | 2C's per-item agreement rate, published beside any cross-runtime reading; no ordering from a two-cell row | the agreement rate and the first disagreement, quoted (`§2.3`) |
| 16 | **Footprint across runtimes** | a memory "ranking" between vMLX and Osaurus inside a Pareto table | none — the metrics are not comparable. `report.CROSS_RUNTIME_UNCOMPARABLE` governs; Pareto frontiers are per (model, runtime) (`§5.6`) | the frontier tables name their runtime in the header |
| 17 | **The evaluator's filters** — answer extraction is harness-side regex | a low score from extraction failure where the model answered | the parse-failure rate published per cell; >20% is a FAIL, 5–20% is a score with the rate beside it | the raw and filtered responses in `--log_samples`, side by side |

### 4.2 Pinned parameters

The run pins for every invocation, in one table. Anything absent from this table is either a
property of the cell (the artifact) or a property of the task (its own config) — nothing else
moves.

| pin | value | where it comes from |
|---|---|---|
| `temperature` | `0.0` | `measure.TEMPERATURE`, and the model type's default |
| `seed` | fixed; forwarded if the model type forwards it | `measure.SEED`; forwarding **verified** in the spike, else declared |
| `max_tokens` (per task) | the cap of `§3.5`, set once | the spike's 99th-percentile length distribution |
| `stream` | `false` | `§3.4` |
| concurrency | `1` | `§3.4`, `§3.7` |
| `cache_state` | **`"off"`** | `runtimes.py`'s cache pin; `--disable-prefix-cache` and `--disable-block-disk-cache` in vMLX's start command, the host toggled for Osaurus |
| `num_fewshot` | each task's own default | `§3.6`; the effective value read back from the harness |
| `fewshot_as_multiturn` | one frozen setting | `§3.6`, priced once in the spike |
| item set | 2,280 + 250 + 250 + 250 | `§3.3` |
| task ids + versions | pinned from the installed registry | `§3.2` |
| harness version | one, recorded | `§4.3` |
| runtime | one per column | `§2.1`–`§2.2` |
| schedule | cell-major blocks, rotated cell order, 30 s cooldowns | `§3.7` |

**The cache-state pin is deliberate and its cost is accepted.** A prefix cache hit is invisible to
a benchmark client: no field in the harness's sample record says whether a request reused KV. A
hit would make one format's requests (a format the runtime caches differently or not at all) run
under different conditions from another's, and the difference would land in nothing that this
study can read. So the run pays a full prefill per item — expensive on dense, where prefill is
slow — and gets a condition that is identical across the column. The alternative (cache on, for
speed) was considered and rejected with that reason.

### 4.3 Tool isolation: `uv run --isolated --with lm-eval`

The zero-dependency invariant is a project rule, not a convenience:

> **No new dependency without naming what it replaces.** (`.paul/STATE.md`, Boundaries)

The evaluation tool is therefore run **outside** the package, in a throwaway environment:

```sh
uv run --isolated --with lm-eval lm_eval \
  --model local-chat-completions \
  --model_args base_url=http://127.0.0.1:8000/v1,model=<resolved id>,tokenizer=<artifact_dir>,… \
  --tasks <pinned ids> --limit … --seed 0 \
  --output_path results/accuracy/<campaign>/<cell>/<task>/ \
  --log_samples
```

| rule | why |
|---|---|
| `ohyesmlx/` gains no import, no module, no entry in `pyproject.toml` | the core package stays stdlib-only and dependency-free |
| the `lm-eval` version is recorded in every manifest line and in the write-up | a filter or task change between versions is a different task (`§4.1` #7, #8) |
| the uv cache is **warmed in Plan 02-01**, before any campaign block | the first `uv run` fetches the harness; a fetch inside a campaign competes for the disk and the machine while a block is measured — the standing "never download while measuring" rule, applied to the toolchain |
| the campaign runs offline | nothing about scoring needs the network, and its absence is one fewer variable |
| the runner starts and stops runtimes through `runtimes.RUNTIMES[...]`, not by hand | the start commands *are* pins (`--no-jit`, `--disable-native-mtp`, the cache flags, `--max-context off`). A hand-written command would be a second definition of them, and this project's rule is that two writers for one artifact is the pattern it exists to avoid |
| the runner is `scripts/run_accuracy_<study>.sh` + a small lifecycle helper, modelled on `scripts/run_jang_dense.sh` | same shape as every other campaign runner in the repo |

### 4.4 Runtime lifecycle and host controls

- **Readiness is the log, not the port**, and the model list is not evidence either: mlx-lm lists
  a `--model` path it never loaded, oMLX lists a JANG artifact it had already failed on, and
  Osaurus lists a model it answers `not installed` for. `Runtime.await_ready` already enforces
  both signals; Track 2 uses it unchanged.
- **Osaurus**, per Track 1's discipline, and byte-exact on every exit path:
  1. `cp -p` backups of `~/.osaurus/config/server-runtime.json` and `server.json` before the first
     Osaurus block;
  2. `cache.prefix.enabled` and `cache.blockDisk.enabled` set **false** for the campaign;
  3. `modelIdleResidencyPolicy.seconds` pinned to **900** — a precondition, not an optimization,
     because the host's own 30 unloads the model inside the 30 s cooldown and a long benchmark
     block would measure a half-evicted model;
  4. the baseline re-recorded so the harness's drift gate passes, and `--cache-state off` on every
     run so `Osaurus.cache_state_refusal` refuses a cell the host disagrees with;
  5. restore verified with **`cmp -s`** — not with the drift guard — on the normal path *and* on
     `INT`/`TERM`/`HUP`, then `git checkout -- config/osaurus-settings-baseline.json`;
  6. `shasum -a 256` of both files before and after every Osaurus cell, because the drift guard
     watches 23 keys and a byte that moved outside them would not be in the record.
- **The per-model thinking switches** are read for *this artifact's* model id before its block,
  recorded, and must agree with the column's mode (`§3.5`).
- **One runtime holds weights at a time**, and the sweep between blocks kills stale Osaurus
  instances **by full executable path** — `^/Applications/osaurus.app/Contents/MacOS/osaurus` —
  and **never by the name `osaurus`**, because `osaurus mcp` is a long-running user process that
  must not be touched.
- **The `vmlx` blocks inherit Track 1's start command untouched**, JIT and native MTP pinned off,
  which means every score here describes the same floor configuration the speed numbers describe.

### 4.5 Per-cell pre-flight

Before a cell is scored, and recorded in its manifest line. A failure here is a refusal, not a
degraded measurement:

| check | how it is read | why it matters |
|---|---|---|
| the artifact's bytes are what `§2.4` says | `artifact_bytes` at block start | the study is about these ten artifacts |
| the tokenizer builds from the artifact | `TokenCounter(artifact_dir)` | the `_visit` rule; a missing tokenizer is N/A, never a fallback |
| the runtime resolves the model id and logs no load failure | `await_ready`'s two-signal rule | every runtime here advertises models it cannot serve |
| the canary answers **in the channel the harness reads** | one known-answer request, full response kept | `§3.5`; the difference between a score and a column of zeros |
| the effective item count equals the budget | count items in the invocation's own results JSON | the `--limit` trap, caught before a format is scored under an unintended sample |
| the item identity hash matches the study's first cell | hash of `doc_id`s (or target+prompt) | `§3.3`; the paired instrument depends on it |
| the effective `num_fewshot`, cap and template digest are what the study pinned | the harness's resolved `configs` | `§4.1` #4, #7 |
| the request count reconciles | items sent vs requests served in the runtime log | the retry blind spot |
| the thinking switch matches the column's mode | the host setting, for this artifact's id | `§3.5` |
| the runtime version is the campaign's | `Handle.version` | `§4.1` #9 |

---

## 5. Pre-registered decision rules and the Pareto framework

### 5.1 The accuracy parity band

> **Two formats are at parity on a task when their scores differ by no more than 1.5 percentage
> points, with the paired interval of `§5.2` lying entirely inside that band.**

Three notes the write-up must carry every time the band is used:

1. **It is percentage points, never relative percent.** 1.5 relative percent of a 40% score is
   0.6 pp — a factor of 2.5 apart from the band. Every table prints `pp`.
2. **It is a decision rule, not a measurement.** 1.5 pp is chosen a priori, before any score
   exists, so that the write-up cannot pick its threshold after seeing the data. It is not
   derived from a replicate (no accuracy replicate existed to derive one from) and it is not
   claimed to be a physical constant.
3. **It may be widened by the campaign's own evidence, never narrowed.** If a replicate visit
   moves a cell's score by more than half the band on the same items at temperature 0, that
   movement is a harness finding, and the band widens to the observed movement for that task —
   printed with the reason and the two scores. Widening costs indeterminacy; narrowing would
   manufacture differences.

**Why 1.5 pp, and what it costs.** It is the largest band that leaves the study able to detect a
small effect on MMLU (the reasoned discordance in `§3.3` gives ±1.3–1.8 pp at 2,280 items) and
the smallest that does not chase the noise of a 250-item task — which, as `§3.3` shows, cannot
resolve 1.5 pp at all. The band is therefore **task-dependent in effect and uniform in
statement**: on MMLU it is a live threshold; on the three 250-item tasks it is a floor below which
nothing can be claimed either way, and the indeterminate bin is where those comparisons land.

### 5.2 The paired instrument

Every comparison this study publishes is computed on **identical items**, and that is what makes
the interval usable.

```
score(c, t) = k(c, t) / n(t)                       accuracy of cell c on task t
Δ(A, B)     = (b − c) / n                          paired difference, A vs B
SE(Δ)       ≈ sqrt(b + c) / n                      McNemar, normal approximation, b + c ≥ 25
```

where `b` counts items A answered correctly and B did not, and `c` the reverse. Below `b + c = 25`
the exact binomial interval is used and the comparison is reported as indeterminate unless the
exact test excludes zero. **`b + c` is published with every Δ** — it is the quantity a reader
needs to judge whether the two formats were distinguishable on this item set at all, and it is
the number a design that had not thought about pairing would never have shown.

Three bins, pre-registered, exhaustive:

| bin | condition | what the write-up may say |
|---|---|---|
| **tie (parity)** | \|Δ\| ≤ 1.5 pp **and** the paired 95% interval lies entirely within ±1.5 pp | "the two formats are at parity on this task, on these items" |
| **difference** | \|Δ\| > 1.5 pp **and** the paired 95% interval excludes zero **and** the replicate agrees in direction | "A scored Δ points above B on this task; the paired interval is [lo, hi]; `b + c` was K" |
| **indeterminate** | everything else — including a Δ outside the band whose interval straddles zero, and a Δ inside the band whose interval escapes it | "the comparison is indeterminate at this item count: Δ = X pp, interval [lo, hi], K discordant items. This is not evidence of parity and not evidence of a difference" |

The third bin is the one that will fill the tables on the 250-item tasks, and it is in the design
on purpose. A study that reported those comparisons as ties would be publishing a sample size's
opinion as a measurement.

**Unpaired means unpaired.** Any comparison of two cells that were not scored on the same item
set is refused rather than computed unpaired — the identity hash check of `§3.3` decides, and the
runner will not emit the comparison.

### 5.3 The reading vocabulary

The dispatch names three pre-registered outcomes, P1–P3, for the format-under-test against its
comparator (in 2B that is `jang2l` vs `stock4bit`; in 2A it is `jang4s` vs `stock4bit`). Each is
a decision rule with a condition and a permitted sentence:

| reading | condition | what the study may say | what it may not say |
|---|---|---|---|
| **P1 — quality parity** | the comparison is in the **tie** bin, in the primary and the replicate | "format A's speed and/or memory advantage is bought at no measurable accuracy cost on this task, on these items" | "A is as accurate as B in general" — parity is on this task, this item set, this harness |
| **P2 — measured degradation** | the comparison is in the **difference** bin with A below B, in the primary and the replicate | "A gives up Δ points (interval, K discordant) of task-T accuracy; against its measured speed/memory advantage that is an exchange rate of R per unit" | that the exchange rate is acceptable — the framework publishes rates, it does not choose for the reader |
| **P3 — quality collapse** | **either** (a) a cell's point score is **at or below the task's floor** — 25% for the two four-way multiple-choice tasks, 0% for GSM8K and IFEval — on any task, **or** (b) its **parse-failure rate exceeds 20%** | "the format fails the reasoning floor: score X against a chance floor of 25%, on these items" — published as a **FAIL** with the failing sample | anything about the format's other tasks as though this were not fatal. A collapsed cell publishes no Δ and no Pareto position |

Two additions the dispatch's three readings need in order to be applied without fudging:

- **At-chance is reported separately and is not collapse.** A score that is not significantly above
  chance (a one-sided 95% test against `p = 1/k`) is a distinct, weaker reading: "at chance on
  this task". Collapse is the stronger claim — the point estimate at or below the floor — and it
  is the one that publishes as FAIL.
- **A reading needs its replicate.** P1 and P2 are published only when the primary and the
  replicate agree on the bin. Where they disagree, the reading is indeterminate and both scores
  are printed — Track 1's R-reproduce rule, applied to accuracy, and the reason `§2.6` names
  which cells get a replicate.

### 5.4 No task pooling, and no blended score

Two rules from Phase 3/5 govern the tables here, unchanged:

> **Floors then one ordering metric, never a blended score** … a single number would encode an
> arbitrary trade-off as though it were measured. (`.paul/STATE.md`, Decisions; `docs/interfaces.md`)

and

> Figures are never averaged across workloads. (`docs/interfaces.md`, Workloads)

Applied to Track 2:

- **No cross-task average accuracy.** MMLU, GSM8K, ARC-Challenge and IFEval are four readings.
  A format that gains on MMLU and loses on IFEval is a finding, and it is exactly the finding a
  pooled score would destroy. Where a summary is genuinely needed, the permitted form is a
  **count**, not a mean: "format A is at parity or better on 3 of 4 tasks, and below by Δ on the
  fourth."
- **No quality-adjusted single number.** No "accuracy per token", no weighted score, no composite
  index. The Pareto frontier of `§5.5` is the honest replacement: it keeps every coordinate
  measured and lets the reader see the trade instead of the study choosing one.
- **Floors gate everything.** A cell that fails P3, or fails a floor of `§3.5`, or whose
  reconciliation fails, publishes no Δ and occupies no frontier position. A blank column is never
  mistaken for a favourable one.

### 5.5 The 2-D Pareto formulation

The framework's job is to answer "which format should a reader run" without inventing a weight.
It does that by computing **non-dominated sets**, not scores.

**Coordinates.** For a cell `c = (format f, runtime r)`:

```
x(c)   = score(c, t)         accuracy on task t (one primary axis; MMLU by default, each task in secondary tables)
y₁(c)  = decode_tps(c)       quoted from Track 1's record for this cell (never re-measured)
y₂(c)  = peak_mb(c)          within one runtime only
y₃(f)  = disk_bytes(f)       the format's own bytes, runtime-independent
```

**Dominance with bands.** `c` dominates `c′` on the pair `(x, y)` when **all** of the following
hold:

1. `x(c) − x(c′) > 1.5 pp` with the paired interval excluding zero — **a difference, not a tie,
   and not indeterminate**;
2. `y(c)` is at least as good as `y(c′)` by more than `y`'s own band — **2.5%** for throughput
   (Track 1's tie band), **1%** for memory (the scale at which Track 1's own replicate agreed
   with itself: 1 MB and 21 MB on the MoE cells), and exact equality for disk;
3. at least one of the two inequalities is strict.

A point that no other point dominates is **on the frontier**. A pair inside the bands on both axes
is a **tie**, printed as two points, not as a domination — the same rule that stopped the project
publishing a rank number beside a 0.3% gap.

**The consequence, stated for Q3.** If `optiq`'s accuracy is at parity with `oq4`'s and its
throughput and footprint and disk are all worse by more than their bands, `optiq` is **strictly
dominated** — and that is a complete, publishable answer to Q3: "the penalty bought nothing, on
this model, in this runtime, on these items." No verdict is published when the accuracy
comparison is indeterminate; the frontier then simply carries `optiq` as a non-dominated point,
with its indeterminate Δ shown.

**Trade rates are pair properties, never table properties.** Between two cells, the exchange rate
is a slope:

```
R_quality_per_speed  = (x(A) − x(B)) / (y₁(A) − y₁(B))     pp per tok/s
R_quality_per_memory = (x(A) − x(B)) / (y₂(A) − y₂(B))     pp per 100 MB
R_quality_per_disk   = (x(A) − x(B)) / (y₃(A) − y₃(B))     pp per GB
```

Each is published with both cells named, both coordinates, and the interval propagated from the
accuracy interval. A slope whose accuracy difference is in the **tie** or **indeterminate** bin is
published as a slash through the table, not as a number — the whole point of the band is that a
rate computed from an unresolvable difference is not an exchange rate at all.

**Frontiers are per (model, runtime).** Never across runtimes: `peak_mb` doesn't measure the same
pages in two runtimes (`report.CROSS_RUNTIME_UNCOMPARABLE`; `2026-09-16-footprint-is-not-one-quantity.md`),
and the accuracy coordinate's cross-runtime portability is exactly what 2C measures rather than
assumes. So Phase 2 produces, at most, four frontier tables:

| model | runtime | formats on the frontier | speed coordinate source |
|---|---|---|---|
| `Qwen3.5-4B` | `vmlx` | `stock4bit`, `oq4`, `oq4e`, `jang4s` | dense study `§3.1` |
| `Qwen3.5-4B` | `osaurus` | `oq4`, `oq4e`, `optiq`, `jang4s` | dense study `§4.1` |
| `LFM2.5-8B-A1B` | `vmlx` | `stock4bit`, `oq4`, `oq4e`, `optiq`, `jang2l` | MoE study `§3.1` |
| `LFM2.5-8B-A1B` | `osaurus` | — not drawn — | two of five decode rows are FAILs (MoE `§4.1`) |

### 5.6 Joining the accuracy coordinate to Track 1's speed coordinates

The join is **editorial and explicit**: each Pareto table carries a `speed source` column naming
the Track 1 section its `decode_tps` and `peak_mb` came from, exactly as the Track 1 synthesis
does, and the tables are written by hand into the write-up rather than rendered by `report.py` —
the tool joins run directories whose pins match, and Track 2's pins (`cache_state: "off"`, a
whole different record shape) do not match Track 1's.

The coordinates, quoted from Track 1's primary visits, that the frontier tables will use:

| cell | `decode_tps` | drift | `peak_mb` | `disk_bytes` | source |
|---|---|---|---|---|---|
| `jang4s__vmlx` | **54.2** | +5.9 | 3,820 | 3,207,385,506 | dense `§3.1` |
| `oq4__vmlx` | 47.6 | +14.2 | 3,819 | 3,160,559,814 | dense `§3.1` |
| `oq4e__vmlx` | 46.0 | +5.4 | 3,946 | 3,167,949,891 | dense `§3.1` |
| `stock4bit__vmlx` | 44.2 | +16.6 | 3,843 | 3,061,131,520 | dense `§3.1` |
| `jang4s__osaurus` | **42.5** | +5.1 | 3,400 | 3,207,385,506 | dense `§4.1` |
| `oq4__osaurus` | 38.8 | +18.7 | 2,466 | 3,160,559,814 | dense `§4.1` |
| `optiq__osaurus` | 38.7 | −1.0 | 2,472 | 4,043,620,369 | dense `§4.1` |
| `oq4e__osaurus` | 38.6 | +6.2 | 2,216 | 3,167,949,891 | dense `§4.1` |
| `jang2l__vmlx` | **116.3** | +0.5 | 3,624 | 3,062,430,853 | MoE `§3.1` |
| `stock4bit__vmlx` | 115.3 | +3.9 | 5,214 | 4,782,228,753 | MoE `§3.1` |
| `optiq__vmlx` | 100.6 | +6.1 | 5,869 | 5,473,296,789 | MoE `§3.1` |
| `oq4e__vmlx` | 97.0 | +10.9 | 5,416 | 4,994,831,815 | MoE `§3.1` |
| `oq4__vmlx` | 65.6 | **+76.0** | 5,415 | 4,994,822,580 | MoE `§3.1` — rate annotated, window never closed |
| `stock4bit__osaurus` | 123.0 | +5.9 | 4,542 | 4,782,228,753 | MoE `§4.1` |
| `jang2l__osaurus` | 116.7 | +3.2 | 3,829 | 3,062,430,853 | MoE `§4.1` |
| `oq4__osaurus` | 115.8 | +2.6 | 4,497 | 4,994,822,580 | MoE `§4.1` |

Three rules for reading that table, each of which the project learned the hard way:

1. **A speed coordinate carries its drift marker into the plot.** `oq4__vmlx`'s +76.0% means its
   65.6 tok/s narrates its window more than its artifact; the point is drawn with the annotation
   and the write-up may not read `oq4`'s frontier position as a property of `oq4` alone.
2. **No cross-runtime ordering is read from `peak_mb` or from `cold_load_s`.** Those metrics are
   not one quantity across runtimes; every table above names its runtime in the header.
3. **The speed coordinate is a quotation.** Track 1 measured it; Track 2 does not re-measure it,
   and the write-up says so above each table.

### 5.7 What the write-up may say, and what it may not

May say:

- "On MMLU's pinned 2,280 items, in vMLX 1.6.59, `JANG_2L` scored X and `stock4bit` scored Y, a
  paired difference of Δ points with interval [lo, hi] over K discordant items."
- "The parity claim reproduces / does not reproduce under these pins; the vendor's pins are
  these, ours are these."
- "`optiq` is strictly dominated on the MoE vMLX frontier: at parity on accuracy, `jang2l` is
  15.6% faster (116.3 against 100.6 tok/s) and its bundle is 44% smaller on disk (3.06 GB against
  5.47 GB), with 38.3% less peak footprint."
- "The two loaders agreed on A% of items on identical bytes, and here is the first item they
  disagreed on."

May not say:

- That a format is more accurate **in general** (two models, one harness, one machine, one item
  set).
- That a quantizer **preserves** or **damages** reasoning as a property of the method — the study
  measures this bundle, these bytes, this snapshot.
- Any ordering from a Δ inside ±1.5 pp, or from an indeterminate comparison, or from an unpaired
  comparison.
- Any absolute-capability claim: these benchmarks are public and contaminated, and the subsample
  is a subsample (MMLU here is 57 × 40, not the full benchmark; a 250-item task is 250 items).
- Any speed or memory number that is not a quotation from Track 1 with its section named.

---

## 6. Execution roadmap for Phase 2

### 6.1 Preconditions, and the budget

**Preconditions.** The ten artifacts are on disk and re-verified today (`§2.4`), zero downloads.
The harness is installed and warm-cached by 02-01, and never fetched during a block. The host is
quiet, the ports are free, and the Osaurus settings baseline is backed up and re-recorded before
the first Osaurus block. `ohyesmlx/` is untouched — no code change is a precondition of this
phase, and none is planned.

**The cost model**, so the campaign's size is derived rather than discovered:

```
seconds per item ≈ prompt_tokens / prefill_tps + generated_tokens / decode_tps + fixed overhead
```

with the rates Track 1 measured: dense prefill **536.3 tok/s** (vMLX, measured on the 1,314-token
prompt), dense decode **44–54 tok/s** (vMLX) and **38–43 tok/s** (Osaurus), MoE prefill
**1,643.4 tok/s** (vMLX) and **830.9 tok/s** (Osaurus), MoE decode **97–123 tok/s**. Taking an
MMLU 5-shot prompt of ~1,200 tokens, a mean generation of ~150 tokens, and the pinned 3,030
items:

| study | cells | ≈ seconds/item | ≈ hours per cell (4 tasks) | ≈ campaign total |
|---|---|---|---|---|
| 2A dense, vMLX column (4 cells) | 4 | 4–6 (dense prefill dominates) | 5–7 h | **20–28 h** |
| 2A dense, Osaurus column (4 cells) | 4 | 5–8 (prefill rate unmeasured on dense Osaurus — see below) | 6–9 h | **24–36 h** |
| 2B MoE, vMLX column (5 cells) | 5 | 1.5–2.5 | 2–3 h | **10–15 h** |
| 2C MoE Osaurus (`jang2l`, one task) | 1 | 3 | ≈0.5 h | **≈1 h**, load included |
| replicates (3 cells × the pinned MMLU set) | 3 | — | 2–3.5 h | **≈10 h** |
| **Phase 2, all studies** | | | | **65–90 h of generation** |

That last row is the campaign's real size and it is the coordinator's decision point: Phase 2 is
days of continuous inference on one laptop, split into session-sized blocks, and the two dials
that move it are named above and in `§3.3` — the MMLU per-subject count (40 → 20, which roughly
halves the dense columns), and the dense Osaurus column itself, which may be deferred **as a
whole** (never partially: a column missing a format is not a format axis) if the window does not
hold, at the cost of Q3's dense half and of 2C's third dense row.

**Two honest caveats on that table, both of which the spike resolves before the campaign starts.**
First, dense Osaurus prefill was never measured cleanly — its Track 1 column measured prefix-cache
*lookups* on that workload and published nothing (`2026-09-17-jang-cross-runtime.md` `§2.4`, dense
study `§4.3`) — so its column's estimate is bracketed rather than derived. Second, the estimate
assumes a mean generation of ~150 tokens; a thinking-on model emitting 500-token traces roughly
triples the decode term, and the spike measures the real distribution (`§6.2`).

**Therefore the budget is confirmed by measurement, not by this table**, and the dial is the one
`§3.3` pre-registers: one downward revision of MMLU's per-subject count (40 → 20) before 2A's
first cell, with its precision cost published. Nothing else moves.

### 6.2 Plan 02-01 — harness spike and local-endpoint validation

**The spike measures nothing about formats.** It exists to establish that the instrument works,
and everything it establishes is recorded once and reused by every later plan. It is a single
cell — one format, one runtime, one model — plus one task per runtime.

| step | what | exit criterion |
|---|---|---|
| 1 | Install and version-pin the harness in the isolated uv env; record `uv --version` and the `lm-eval` version | the harness runs offline afterwards |
| 2 | Enumerate the installed task registry; pin each task's exact id, version hash and generative variant | four task ids pinned, with the registry evidence for each |
| 3 | Start runtime R via `runtimes.RUNTIMES[...]`, read the resolved `model_id` and version, issue the **canary** | the answer arrives in the channel the harness reads, or the switch that makes it do so is found and recorded; a pair with neither is out of the study with its reason |
| 4 | Price the two `fewshot_as_multiturn` settings on one task, one format | one setting frozen, with both scores recorded as the pin's provenance |
| 5 | Run one task at the pinned budget; audit the item count, the identity hash, the effective `num_fewshot` and cap from the harness's own output | items issued == items pinned; identity hash recorded |
| 6 | Measure the generation-length distribution and set the per-task caps at the 99th percentile | caps pinned, truncation rate at the chosen cap < 5% |
| 7 | Measure seconds per item, per task, per runtime and model | the budget of `§6.1` confirmed or the `§3.3` dial applied |
| 8 | Verify determinism: the same item twice in one process, and once in a second block | identical answers, or a measured disagreement rate that becomes `§5.1`'s widened band |
| 9 | Verify the retry/reconciliation behaviour: count requests at the runtime and compare with items | items == requests served, or the harness's retry rule is pinned and its count published |
| 10 | Record the chat-template digest across each study's five artifacts | identical → clean; different → a declared prompt-composition difference |

**A green spike is not acceptance.** The spike publishes which of these checks passed, which
failed, and what it did not verify — including any check that could not be run at all.

### 6.3 Plan 02-02 — dense accuracy study (`Qwen3.5-4B`)

Two columns, eight cells, four tasks, one pinned item set, plus the Q2 replicate (`jang4s` +
`stock4bit` on vMLX and `jang4s` on Osaurus, MMLU).

| step | command shape (abridged) | output |
|---|---|---|
| 1 | Column A: `scripts/run_accuracy_dense.sh` over `gridspec.sh`'s four vMLX artifacts, `cache_state off` | four cells scored, one manifest per (cell, task) |
| 2 | Column B: the same runner over the four Osaurus artifacts, host toggled per `§4.4` | four cells scored |
| 3 | Replicate: `jang4s` + `stock4bit` on vMLX **and** `jang4s` on Osaurus, MMLU, reversed cell order, own blocks | the P1/P2 evidence for Q2 |
| 4 | 2C's dense half: per-item agreement across the three formats present in both runtimes | the agreement rates of `§2.3` |
| 5 | Write-up: `docs/research/<date>-accuracy-dense.md` | Q2 and Q4 answered; Q3's dense half answered on Osaurus |

Exit criteria: every cell scored or N/A/FAIL with its reason; item-identity hashes agree within
each task across all eight cells; every confound in `§4.1` pinned or declared; the reconcile check
clean on every block; the replicate run.

### 6.4 Plan 02-03 — MoE accuracy study (`LFM2.5-8B-A1B`)

One column, five cells, four tasks, plus the Q1 replicate (`jang2l` + `stock4bit` on vMLX, MMLU)
and 2C's MoE row (`jang2l__osaurus`, one task).

| step | command shape (abridged) | output |
|---|---|---|
| 1 | `scripts/run_accuracy_moe.sh` over `gridspec-moe.sh`'s five vMLX artifacts | five cells scored |
| 2 | Replicate: `jang2l` + `stock4bit` on vMLX, MMLU, reversed order | the P1/P2 evidence for Q1 |
| 3 | 2C: `jang2l__osaurus` on the pinned task | the agreement rate of `§2.3` |
| 4 | Write-up: `docs/research/<date>-accuracy-moe.md` | Q1 answered against both the vendor's claim and Track 1's speed tie |

**The known decoding, pre-registered:** `jang2l` at 2.37 bits is the one cell in the project where
P3 is a live outcome. If it fires, the write-up publishes the FAIL, its score, its floor, and the
failing response verbatim — and the project's speed table gains a footnote it did not have: a
format that ties on throughput and fails the reasoning floor.

### 6.5 Plan 02-04 — the Pareto synthesis

No new measurement. The scored cells are placed on the coordinates of `§5.5` and read as
non-dominated sets, per model, per runtime, per task.

| step | what | output |
|---|---|---|
| 1 | Assemble the frontier tables `§5.5` draws — three of the four possible, the MoE Osaurus one being un-drawable — with their speed quotations and drift annotations | dominance verdicts with their bins |
| 2 | Compute trade rates for the pairs that cleared the band | slopes, labelled per pair of cells |
| 3 | Answer the four questions of `§1.3` in order, in the vocabulary of `§5.3` | the study's findings |
| 4 | Join to Track 1: the recommendation table that finally has three coordinates | `docs/research/<date>-accuracy-pareto.md` |

**The one sentence this synthesis may publish**, in the shape Track 1's synthesis used:

> *On `Qwen3.5-4B` and `LFM2.5-8B-A1B`, in vMLX 1.6.59 and Osaurus 0.25.x, at these pins and on
> this item set, format A's measured speed and density advantage was / was not bought with a
> measurable accuracy cost of Δ points (interval, K discordant items), and the frontier of
> non-dominated formats is…*

with Track 1's limits travelling with it unchanged: not faster in general, not why, not equal
precision on the MoE, not a cross-runtime memory ranking — and now, not an accuracy claim beyond
this harness and these items.

---

## 7. What this study will not establish

- **Not absolute capability, and not a leaderboard score.** MMLU here is 57 subjects × 40 items in
  generative form through a chat endpoint; the three other tasks are 250 items each. These are
  subsamples, they are not comparable to published numbers for these models, and the benchmarks
  are public and predate every artifact.
- **Not a refutation of the vendor.** A non-reproduction is a non-reproduction — different
  harness, different items, different pins, over HTTP. The vendor's own measurement may be
  correct at its own pins.
- **Not "quantization preserves reasoning".** Two models, one harness, one machine. The reading is
  about *these ten artifacts at these snapshots*.
- **Not a cause.** The bundle and the loader travel together, exactly as in Track 1. 2C measures
  the observable — per-item answer agreement between two loaders on identical bytes — and says
  nothing about kernels, activations or bitwise identity.
- **Not a new speed or memory measurement.** Every rate and footprint in a Track 2 table is a
  quotation from Track 1 with its section named and its drift marker intact.
- **Not a cross-runtime accuracy ordering**, and not a cross-runtime memory ordering at all.
- **Not a task-pooled or quality-adjusted score.** No average across tasks, no composite index.
- **Not a claim from inside the band.** A tie is a tie; an indeterminate comparison is published
  as indeterminate; neither is evidence in either direction.

---

## 8. Open questions

1. **Where does the accuracy coordinate get a second model?** Two models is what makes a reading
   model-specific; a third model is a new campaign, not an extra cell.
2. **The thinking-off arm.** The dispatch's budget holds thinking to whatever the artifacts do.
   A separate, small arm — thinking pinned off, MMLU only, the decisive pair — would price the
   reasoning channel's contribution to both score and cost. It is named and not scheduled, and if
   it ever runs it gets its own directory and its own write-up, never a column of this study.
3. **Does the accuracy ordering transfer across runtimes?** 2C's agreement rates are the first
   evidence; a full second column per model is the experiment that would answer it, and it is out
   of Phase 2's budget.
4. **Is `JANG_2L`'s density discount worth the accuracy cost — and to whom?** The framework
   publishes the rate and does not answer this. A reader with 8 GB of unified memory and one with
   64 GB take different answers from one frontier.
5. **What does an accuracy reading do to the vendor's other claims?** Out of scope here; the
   claim captured in 02-01 is this study's only one, and it is quoted from the artifact's own
   material rather than from any third-party description of it.

---

## Appendix A — evidence index

| what | where |
|---|---|
| the founding deferral of accuracy, and the decision table Track 2 answers to | `.paul/STATE.md` (Decisions, Boundaries) |
| the hand-off that names this phase and its preliminary scope | `.paul/HANDOFF.md`; `.paul/ROADMAP.md` (Phase 2) |
| Track 1's matrix vocabulary, tie band, replication rules, confound ledger, and the hand-off to this track | `docs/research/2026-09-17-v2-track1-jang-study-design.md` (`§2.0`, `§2.5`, `§3.3`, `§3.7`, `§6.5`, `§8.4`) |
| every speed, memory and disk figure quoted in this document | `docs/research/2026-09-17-dense-jang-study.md`, `…-moe-jang-study.md`, `…-jang-cross-runtime.md` (`§1`–`§7` of each) |
| the dense OptiQ vision-map refusal and the Osaurus stock-4bit refusal | `docs/research/2026-09-15-grid-loadability-probe.md`; Track 1 design `§2.1`, `§2.2` |
| the two MoE Osaurus decode FAILs | `docs/research/2026-09-17-moe-jang-study.md` `§4.1` |
| `decode_tps`, `prefill_tps`, `CROSS_RUNTIME_UNCOMPARABLE`, `DRIFT_ANNOTATION_PCT`, `DEFAULT_RANK` | `ohyesmlx/report.py` |
| the runtime start commands, readiness rule, cache pin and refusal | `ohyesmlx/runtimes.py` |
| the visit/load structure Track 2 reuses, the tokenizer rule, the coherence gate | `ohyesmlx/measure.py`; `docs/interfaces.md` |
| the reasoning-channel rule that lm-eval does not have | `docs/interfaces.md` ("which channel is the output stream"); `ohyesmlx/measure.py` (`_judged_text`, `EMPTY_CONTENT_ERROR`) |
| the artifact sets of both models | `scripts/gridspec.sh`, `scripts/gridspec-moe.sh` |
| the Osaurus settings baseline, drift guard and restore discipline | `config/osaurus-settings-baseline.json`; `ohyesmlx/osaurus_settings.py`; `scripts/run_sweep_cache.sh`; `scripts/run_jang_dense.sh:93` |
| every artifact size and the two sidecar digests in `§2.4` | re-verified today with `ohyesmlx.measure.artifact_bytes` and Python's `hashlib.sha256`; the commands are printed in `§2.4` |

## Appendix B — number provenance

Every figure in this document is either a quotation or a recomputation, and this table says which:

| this document | value(s) | source |
|---|---|---|
| `§1.1` tier-1 table | JANG leads, disk and memory deltas, prompt deltas | `2026-09-17-jang-cross-runtime.md` `§1.2`, `§3.1`–`§3.3`, `§6.1`–`§6.3`; `dense-jang-study.md` `§1.2`, `§3.1`, `§4.1`, `§7.1`; `moe-jang-study.md` `§1.2`, `§3.1`, `§4.1`, `§7.1` |
| `§2.1`, `§2.2`, `§2.6` matrix and holes | refusal mechanisms, loadability, FAILs | Track 1 design `§2.1`–`§2.4`; `2026-09-15-grid-loadability-probe.md`; `2026-09-17-moe-jang-study.md` `§4.1` |
| `§2.4` artifact table | sizes, file counts, totals | **recomputed today** (`artifact_bytes`); identical to Track 1 design `§4.2` |
| `§2.4` declared bits | `actual_bits`, `bit_widths_used`, digests | `jang_config.json` in both snapshots, **re-read and re-hashed today**; Track 1 design `§3.2`, `§4.2` |
| `§3.3` resolution table | `SE(Δ)` and intervals | computed here from the McNemar form; no measurement involved |
| `§5.6` coordinate table | `decode_tps`, drift, `peak_mb`, `disk_bytes` | dense study `§3.1`, `§4.1`; MoE study `§3.1`, `§4.1`; disk bytes from `§2.4` |
| `§6.1` cost model | prefill and decode rates | dense study `§3.1`, `§3.3`; MoE study `§3.1`, `§3.3`; `2026-09-17-jang-cross-runtime.md` `§5` |

No number in this document was measured for it.
