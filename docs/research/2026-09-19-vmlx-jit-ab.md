# The vMLX JIT A/B: `--no-jit` against `--enable-jit` on `Qwen3.5-4B-JANG_4S` and `LFM2.5-8B-A1B-JANG_2L`

Date: 2026-09-19. **Measured.** Two columns of two JANG cells on vMLX 1.6.59, run back to back
on one machine, differing in exactly one byte of the start command: `--no-jit` (15:51:47–16:05:23
local) against `--enable-jit` (16:05:59–16:20:27). Runner: `scripts/run_vmlx_jit_ab.sh`. Record:
`results/vmlx-jit-ab/` — `runner.log`, and per column one `results.jsonl` (every raw observation)
plus one `leaderboard.md`.

**Axis statement, and it is carried by every table below.** This study varies the runtime's JIT
state, and holds the models, the workload shapes, the runtime version and every other start flag
constant. It can say what JIT cost on these two artifacts at batch size 1 on this machine. It
cannot say what JIT does for models it did not run or at batch sizes above 1, and — because the
two columns ran sequentially rather than interleaved — it does not partition the measured
difference between the JIT state and the machine's thermal state (§2.6). Three claims here are of
that kind — the mechanism (§3.2), the cold-load reading (§2.5) and the like-for-like windows
(§2.6) — and each is labelled where it appears.

Two mechanics of the record matter before the numbers.

- The run directories carry the `-format` suffix because the format study driver was the vehicle
  each column ran under (`python -m ohyesmlx.cli run --study format`). The axis this document
  reads is the JIT state across the two columns, never the within-column format ordering — the
  leaderboards' own header caveat ("runtime held constant; this compares quantization, not
  serving") is about that ordering, and it is not the comparison here.
- The two columns' start commands are identical apart from one flag. `Vmlx.start_command` reads
  `OHYESMLX_VMLX_ENABLE_JIT` and emits `--enable-jit` only for `"1"`, `--no-jit` otherwise
  (`ohyesmlx/runtimes.py:1092-1099`):

  ```text
  vmlx serve <artifact_dir> --host 127.0.0.1 --port 8000 --served-model-name <name> \
    --stream-interval 1 --continuous-batching --max-num-seqs 1 \
    {--no-jit | --enable-jit} --disable-native-mtp --disable-prefix-cache --disable-block-disk-cache
  ```

  Passing neither JIT flag was not an option: left alone, vMLX turns JIT on by itself for a JANG
  affine bundle (`docs/runtimes/vmlx.md` §7.1), which is exactly the state the pin exists to keep
  out of a measured command.

---

## 1. Executive summary and metadata

### 1.1 What ran

| field | value |
|---|---|
| date measured | **2026-09-19** |
| machine | Apple **M2 Max**, 64 GB unified memory (68,719,476,736 bytes), macOS 26.6.2 (build 25G83) |
| runtime | **vMLX 1.6.59**, recorded on all 12 rows (`runtime_version`); the constant is read from the bundle's engine source, since `vmlx --version` exits 2 |
| variable | `--no-jit` vs `--enable-jit`, moved by `OHYESMLX_VMLX_ENABLE_JIT` — the only byte that differs between the two columns' start commands |
| columns | JIT off 15:51:47–16:05:23 local (13 m 36 s); JIT on 16:05:59–16:20:27 (14 m 28 s); 36 s between them, one port sweep and one 30 s cooldown |
| artifacts | `jang4s__vmlx` = **`Qwen3.5-4B-JANG_4S`** (dense, 3,207,385,506 B, snapshot `4567967a46cd9e9bf26d3bb491ddd422ad607775`); `jang2l__vmlx` = **`LFM2.5-8B-A1B-JANG_2L`** (MoE, 3,062,430,853 B, snapshot `5fb82773427c2f25395de8821eff6d95e86feb53`) |
| workloads | `chat` (128 max tokens, 29/32 prompt tokens), `prefill` (64 max tokens, 1,314/1,335 prompt tokens, a 6,485-character excerpt), `decode` (512 max tokens, 29/32 prompt tokens) — byte-identical prompts in both columns |
| pins | temperature 0, seed 0, concurrency 1, 9 measured requests per (cell, workload), warmup plateau rule (cap 20, floor 10, 3 % over a 5-request window), 30 s cooldown after each visit that measured |
| held constant | prefix cache off, MTP off, block-disk cache off, `--stream-interval 1`, continuous batching on, `--max-num-seqs 1` |
| record | `results/vmlx-jit-ab/jit-off/20260919T195147Z-format/` and `results/vmlx-jit-ab/jit-on/20260919T200559Z-format/`, each with `results.jsonl` + `leaderboard.md`; `results/vmlx-jit-ab/runner.log` ends `VMLXJITABDONE 16:20:32` with both columns at exit 0 |

**Status of the twelve rows — all usable.** 12 of 12 (cell, workload) rows are `PASS` with
`n = 9`, **the coherence floor passed on every one of them**, every warmup window closed its
plateau, and no visit was lost or retried. Two properties of what those rows describe are worth
stating up front, because they are what makes the rates real numbers rather than absence:

- **Every response streamed, in the reasoning channel.** All 108 responses (2 columns × 6 rows ×
  9 requests) returned with an empty `content` channel and 268–2,656 characters in the reasoning
  channel: both models answered entirely in that channel, spending their whole token budget there. The
  harness's transport promotes the reasoning window to the measured window when content never
  arrives (`ohyesmlx/transport.py:395-412`), and the gate judges content *or* reasoning
  (`ohyesmlx/measure.py:1050-1059`), so a stream of token salad would still have failed the
  cell. None did. Every rate below is an inter-token rate over a stream that was actually
  delivered.
- **The two columns sent the same work and got the same answers.** Prompt token counts are
  identical in both columns (29/1,314/29 and 32/1,335/32), every request returned exactly its
  `max_tokens` (128/64/512 tokens) in the same number of stream deltas in both columns
  (128/64/512 per request on the dense rows, 127/63/511 on the MoE rows, uniform across every
  request), and **all 54 paired samples are byte-identical between the columns** — the determinism
  temperature 0 with seed 0 buys, and the cheapest evidence that the JIT flag is the only thing
  that moved.

The one floor this build does not evaluate is `fits`: nothing under `ohyesmlx/` reads the host's
total unified memory, so each leaderboard prints that floor as *not evaluated* rather than
cleared, and no row's peak is judged against a memory budget. Peak MB is reported below as what
it is — a measurement — not as a pass.

### 1.2 Headline finding

**JIT does not improve decode speed on these 4B/8B models on Apple Silicon. Across all six
(cell, workload) pairs, `--enable-jit` carries a −2.7 % to −11.3 % decode-throughput penalty
(−1.5 to −8.7 tok/s).**

| cell | workload | JIT off | JIT on | Δ | Δ % |
|---|---|---|---|---|---|
| `jang4s__vmlx` | chat | 58.7 | 57.0 | −1.7 | −2.8 % |
| `jang4s__vmlx` | prefill | 54.8 | 53.3 | −1.5 | −2.7 % |
| `jang4s__vmlx` | decode | 65.0 | 57.7 | −7.3 | −11.3 % |
| `jang2l__vmlx` | chat | 110.7 | 103.9 | −6.9 | −6.2 % |
| `jang2l__vmlx` | prefill | 108.9 | 100.2 | −8.7 | −8.0 % |
| `jang2l__vmlx` | decode | 113.4 | 105.6 | −7.8 | −6.8 % |

Decode tok/s, median of 9 per-request rates; §2.1 carries the full table and Appendix A the
full-precision medians every percentage here is taken from.

The penalty is in the decode rate and nowhere else in the metrics: prefill throughput moved
+2.3 % on the dense model and −1.3 % on the MoE (mixed, both within scatter — §2.3), short-prompt
TTFT moved by at most 3 ms either way (§2.2), and peak memory moved by at most 81 MB, downward
(§2.4). Cold load fell by 1.0–3.0 s in the JIT-on column, which this run records but does not
attribute to JIT (§2.5).

**What the same evidence does not license.**

- **It does not name the mechanism.** No profiler ran, no dispatch count was taken, and nothing
  here observes the compiled graph. §3.2 states the mechanism the numbers are consistent with and
  labels it a hypothesis.
- **It does not partition JIT from the machine's thermal state.** The two columns ran
  sequentially, so a warm machine and the JIT state move together between them; §2.6 records the
  drift, the like-for-like windows, and the direction of that confound. The finding is the sign —
  JIT-on was not faster in any cell-workload at its published window, nor in 11 of 12
  like-for-like windows — not a precise per-cell cost.
- **It covers two artifacts, one machine, one batch size.** A dense 4B and an MoE 8B-A1B at
  concurrency 1 on an M2 Max with vMLX 1.6.59. It says nothing about other quantizations, larger
  models, or batched serving.
- **It does not contradict the directive that put JIT on by default.** That rationale is about a
  397B model (`JANG_1L`), which this machine cannot hold; that regime was not re-measured here,
  and the directive's case is untouched rather than overturned (§3.1).

---

## 2. Measured comparison tables

**Metric definitions** (pinned in `docs/interfaces.md`, applied in `ohyesmlx/report.py`):
`decode_tps` is `completion_tokens / (last content delta − TTFT)`, a per-request rate, and every
figure below is the **median of the 9 measured requests** in that (cell, workload) row. On rows
whose stream never carried content, the transport promotes the last reasoning delta into that
field, so the window is still the stream's last delta (§1.1).
`ttft_p50` is the median of the 9 per-request first-delta times. `prefill_tps` is
`prompt_tokens / TTFT`, median. Peak MB is the maximum `footprint -p <pid>` sample over the
workload's own window (sampled once per second, 23–127 samples per window across the 12 rows),
taken from the higher of the cell's two visits; it is never `ps` RSS. Cold load is spawn →
readiness, one load per cell shared by its three workload rows.

**Basis of the percentages.** Every Δ % in this document is computed from the full-precision
medians in Appendix A, not from the one- and three-decimal figures printed above. The two bases
differ by at most 0.1 pp and no reading turns on the difference. Every figure printed here is
what the column's own `leaderboard.md` prints at its rounding; every one was recomputed from
`results.jsonl` for this document.

**A rate needs a stream, and each row had one.** Each of the 108 measured responses returned its
full `max_tokens` budget (128 / 64 / 512 tokens), streamed in 128/64/512 deltas per request on the
dense rows and 127/63/511 on the MoE rows — at least one delta per MoE request carried two tokens,
with `--stream-interval 1` pinned — so no rate here divides by a collapsed window and no TTFT here
is a disguised time-to-completion.

### 2.1 Decode throughput (tok/s)

The ranking metric, and the one the headline rests on. `chat` and `prefill` are short-prompt
shapes; `decode` is the 512-token shape whose window is long enough to be a rate rather than an
opening.

| cell | workload | JIT off | JIT on | Δ tok/s | Δ % |
|---|---|---|---|---|---|
| `jang4s__vmlx` (Qwen3.5-4B-JANG_4S) | chat | 58.7 | 57.0 | −1.7 | **−2.8 %** |
| `jang4s__vmlx` | prefill | 54.8 | 53.3 | −1.5 | **−2.7 %** |
| `jang4s__vmlx` | decode | 65.0 | 57.7 | −7.3 | **−11.3 %** |
| `jang2l__vmlx` (LFM2.5-8B-A1B-JANG_2L) | chat | 110.7 | 103.9 | −6.9 | **−6.2 %** |
| `jang2l__vmlx` | prefill | 108.9 | 100.2 | −8.7 | **−8.0 %** |
| `jang2l__vmlx` | decode | 113.4 | 105.6 | −7.8 | **−6.8 %** |

Every row is negative. The smallest gap is the dense model's `prefill` row (−2.7 %, −1.5 tok/s)
and the largest is its `decode` row (−11.3 %, −7.3 tok/s); the MoE's three rows cluster at −6.2 %
to −8.0 %. The magnitudes have to be read against the drift §2.6 reports: the smallest gaps sit
inside what that much machine movement can account for on their own, the larger ones do not, and
the direction is consistent in every row — which is why §2.6 carries the window-by-window check
rather than asking the reader to take the medians on faith.

### 2.2 TTFT p50 (s)

| cell | workload | JIT off | JIT on | Δ s | Δ % |
|---|---|---|---|---|---|
| `jang4s__vmlx` | chat | 0.142 | 0.144 | +0.002 | +1.5 % |
| `jang4s__vmlx` | prefill | 2.282 | 2.231 | −0.051 | −2.3 % |
| `jang4s__vmlx` | decode | 0.139 | 0.139 | 0.000 | 0.0 % |
| `jang2l__vmlx` | chat | 0.102 | 0.104 | +0.002 | +1.9 % |
| `jang2l__vmlx` | prefill | 1.019 | 1.033 | +0.014 | +1.4 % |
| `jang2l__vmlx` | decode | 0.102 | 0.105 | +0.003 | +2.5 % |

The four short-prompt rows moved by 2–3 ms and the two long-prompt rows by 14–51 ms, both signs
present; five of six moved *up* by 1.4–2.5 %. Nothing here is a JIT effect in either direction at
this sample size — the whole spread is −2.3 % to +2.5 %, and the one row printed as 0.0 % is
−0.31 % at full precision (0.139173 s against 0.138744 s, both of which round to 0.139; see
Appendix A). The reading is the plain one: **JIT did not move prompt-processing latency
meaningfully on either artifact**, and no claim about TTFT is made beyond that.

### 2.3 Prefill throughput (tok/s)

`prefill_tps = prompt_tokens / TTFT`, median, on the `prefill` workload (1,314 prompt tokens
dense, 1,335 MoE).

| cell | JIT off | JIT on | Δ tok/s | Δ % |
|---|---|---|---|---|
| `jang4s__vmlx` | 575.8 | 589.1 | +13.3 | **+2.3 %** |
| `jang2l__vmlx` | 1310.0 | 1292.4 | −17.5 | **−1.3 %** |

Opposite signs on the two artifacts, and both smaller than the 2.5 % the same flag moved TTFT by
— a tie in effect at this sample size. The value of the row is what it rules out: **JIT's
penalty is not in prompt processing.** If a compiled forward pass helped anywhere on these
shapes, prefill is where it would show, and it does not show.

### 2.4 Peak memory (MB, `phys_footprint`)

Each figure is the peak of that workload's own sampling window; a peak belongs to the shape that
made it, so all six rows are printed rather than one peak per cell.

| cell | workload | JIT off | JIT on | Δ MB | Δ % |
|---|---|---|---|---|---|
| `jang4s__vmlx` | chat | **3791** | **3717** | **−74** | **−2.0 %** |
| `jang4s__vmlx` | prefill | 4605 | 4531 | −74 | −1.6 % |
| `jang4s__vmlx` | decode | 3792 | 3711 | −81 | −2.1 % |
| `jang2l__vmlx` | chat | **3596** | **3596** | **0** | **0.0 %** |
| `jang2l__vmlx` | prefill | 4266 | 4265 | −1 | −0.0 % |
| `jang2l__vmlx` | decode | 3615 | 3615 | 0 | 0.0 % |

The bold rows are the two the summary quotes. Across all six the peak moved by at most 81 MB, and
always downward — **JIT bought no memory back and cost none** on artifacts this small. (The
row-to-row spread within a cell, e.g. 3791 MB chat against 4605 MB prefill on the dense model, is
the workload's own KV window, not JIT.)

### 2.5 Cold load time (s)

Spawn → readiness, one load per cell, carried on all three of the cell's rows.

| cell | JIT off | JIT on | Δ s | Δ % |
|---|---|---|---|---|
| `jang4s__vmlx` | 9.11 | 6.08 | −3.03 | −33.3 % |
| `jang2l__vmlx` | 7.07 | 6.07 | −1.01 | −14.2 % |

**These two rows are recorded, not attributed.** They point the opposite way to what the runtime
reference predicts: `docs/runtimes/vmlx.md` §7.6 reads the source as compiling and running a
1-token warmup pass *inside* load whenever JIT is on, which would make the JIT-on column's cold
load longer, and it is 1.0–3.0 s shorter instead. Two mechanisms outside the JIT flag could
produce that, and this run cannot separate them from it:

- **The JIT-on column ran second.** The same two artifacts had been read from the same paths
  fourteen minutes earlier, so the OS file cache was warm; the harness's own design note is that
  "a later visit starts from a warm page cache" (`ohyesmlx/measure.py:694-697`), and that applies
  between columns as much as between visits. The dense cell's 3.03 s is the largest drop, and that
  cell is also the one the first column loaded from cold — by the second column, both artifacts
  had been read once already.
- **The block-disk cache is off in both columns** (`--disable-block-disk-cache`), so the cache
  namespace that would normally be trimmed synchronously inside cold load is not in play here;
  what remains is the OS page cache above.

What the pair does support is narrower and still worth having: **no JIT-related load penalty is
visible on either artifact.** A caller who pays the documented compile-plus-warmup cost at load
does not pay it in readiness time on these cells.

### 2.6 Thermal drift, and the like-for-like windows

Both columns slowed as they ran — the thermal curve this machine produces under sustained
inference — and the drift differs between the columns. That is the one confound this design
leaves open, so it is reported with the numbers rather than asserted away.

| cell | workload | drift off % | drift on % | visit-1 median off → on (tok/s) | visit-1 Δ % | visit-2 median off → on (tok/s) | visit-2 Δ % | published window Δ % |
|---|---|---|---|---|---|---|---|---|
| `jang4s__vmlx` | chat | −6.4 | −13.9 | 58.81 → 58.16 | −1.1 % | 54.97 → 49.96 | −9.1 % | −2.8 % |
| `jang4s__vmlx` | prefill | −15.6 | −10.3 | 56.05 → 54.88 | −2.1 % | 47.38 → 49.05 | **+3.5 %** | −2.7 % |
| `jang4s__vmlx` | decode | −17.8 | −11.7 | 66.29 → 60.61 | −8.6 % | 54.18 → 53.56 | −1.2 % | −11.3 % |
| `jang2l__vmlx` | chat | +0.1 | −1.1 | 110.59 → 104.52 | −5.5 % | 110.74 → 103.52 | −6.5 % | −6.2 % |
| `jang2l__vmlx` | prefill | −7.9 | −2.8 | 109.33 → 102.24 | −6.5 % | 100.75 → 99.29 | −1.5 % | −8.0 % |
| `jang2l__vmlx` | decode | −6.3 | −2.2 | 113.45 → 106.80 | −5.9 % | 106.45 → 104.84 | −1.5 % | −6.8 % |

Drift is the harness's own published field: the median decode rate of the first half of a cell's
measured requests against the second half's. "Visit-1" and "visit-2" are the five and four
measured requests of the cell's two visits (the runtime restarts between them, the directions
alternate); splitting the window this way gives the closest thing to like-for-like the design
contains.

What the table says, in order of how much weight it will bear:

1. **The direction is stable; the magnitude is thermal.** All six published-window gaps are
   negative, all six visit-1 gaps are negative (−1.1 % to −8.6 %), and five of six visit-2 gaps
   are negative — the exception is the dense model's `prefill` row, which reverses to +3.5 % in a
   window where both columns sit at the throttled floor of 47–49 tok/s. Eleven of twelve
   like-for-like windows keep the sign.
2. **The drift is not the same on both sides of the A/B.** The JIT-off column drifted −6.4 % to
   −17.8 % and the JIT-on column −1.1 % to −13.9 %, cell by cell, and the columns ran one after
   the other rather than interleaved. A warmer machine and the JIT-on state move together, and
   that bias points **in favour of the headline** — so read the penalty as "JIT-on was not faster
   anywhere, and on the windows least contaminated by clock movement it was 1–9 % slower", not as
   a fixed per-cell JIT cost. The two smallest gaps (the dense `chat` and `prefill` rows at
   −1.1 % and −2.1 % in visit 1) are inside what a thermal offset can explain on their own; the
   MoE's and the dense `decode` row's visit-1 gaps (−5.5 % to −8.6 %) are not.
3. **The two longest shapes drifted most**, consistent with the heat they generate: the 512-token
   `decode` and the 1,314-token `prefill` rows hold the two largest off-column drifts (−17.8 %
   and −15.6 %), while the MoE's 128-token `chat` row slipped +0.1 % across its window at all.

A design that wanted the JIT effect without the thermal one would interleave the two states
within a column (or run an off–on–off sandwich) so that position and state decorrelate. This
runner did not, and the record is reported as it stands rather than re-labelled: **the axis is
JIT, the caveat is that the second column met a warmer machine, and the direction of that caveat
favours the finding rather than weakening it to zero.**

---

## 3. Architectural analysis

### 3.1 Why the runtime turns JIT on by default for JANG affine bundles

The auto-enable is documented in the runtime and in the shipped source. `docs/runtimes/vmlx.md`
§7.1 quotes the rationale verbatim from `cli.py:2079-2083`:

> Default JIT (mx.compile) ON for JANG affine models per Eric directive 2026-06-27: 397B JANG_1L
> observed at ~10 tok/s without JIT vs expected 20+; 9B affine at 90 tok/s shows compile-eligible
> decode path is healthy at this family.

Four things about that note bear on this study, and each narrows it:

- **It is a directive, not a measurement.** Its own words are "observed at ~10 tok/s without JIT
  vs expected 20+" — one model, one number, against an expectation rather than a measured
  alternative.
- **It is about a 397B model.** `JANG_1L` at 397B parameters does not fit this project's machine;
  the default exists because of a regime these two cells do not occupy, and this document does
  not test it.
- **It is applied by the runtime, not by the caller.** The enable fires only when the user passed
  neither flag (`cli.py:2085-2087`), it is limited to affine JANG layouts that are not in the
  excluded families and not compile-unsafe (`cli.py:2119-2136`), and `--no-jit` is applied last
  and wins (`cli.py:2788-2796` — the source comments that the ordering is load-bearing because
  otherwise the flag is "silently overridden"). The mechanism is therefore a default that a
  measured command must explicitly opt out of, which is what both columns here did.
- **The same note contains a sentence that is not evidence for its default:** "9B affine at
  90 tok/s shows compile-eligible decode path is healthy at this family" says the compile-eligible
  path works at 9B — it does not say JIT made it faster, and at 4B and 8B it did not.

### 3.2 Why JIT regresses at 4B–8B on Apple Silicon

Stated as the mechanism the numbers are consistent with, and not as something this run
established; no profiler and no dispatch counter ran here.

At batch size 1, decode is a memory-bandwidth-bound loop: every generated token requires reading
the active weight bytes and the KV window, and there is no second token to amortize the read
over. `mx.compile` can fuse operations and cut kernel-launch overhead, but it **does not reduce
the bytes that a 4-bit affine dequantization must move to produce a token** — the dequant still
happens, once per weight, per forward. So on these shapes a compiled graph can only pay through
fewer or better kernels, and what this run measures is the other side of that ledger: a 2.7 % to
11.3 % cost, the size and sign of which are consistent with dispatch overhead or a fused
schedule that is worse than the hand-tuned eager path for these kernel shapes. Which of those it
is was not instrumented, and this document does not claim one.

Two measurements in this record are consistent with that reading, one of them independent of
JIT — and one control is what makes the difference a difference:

- **The artifacts are nearly the same size on disk and decode at very different rates.**
  3.21 GB for the dense 4B against 3.06 GB for the MoE 8B-A1B, yet the MoE decodes 1.74×–1.83×
  faster in both columns (113.4 against 65.0 tok/s off; 105.6 against 57.7 on). Total resident
  bytes do not set the decode rate; **bytes moved per generated token** do — the MoE activates
  roughly an eighth of its weights per token — which is the same property that makes a graph
  compile unable to help by itself.
- **The penalty lands on decode and not on prefill.** Prompt processing at 1,314–1,335 tokens is
  the compute-bound shape in this set, and it moved +2.3 % and −1.3 % — a tie (§2.3). A cost that
  appears only in the decode loop is the signature of a decode-loop effect, whether that is
  fusion quality or dispatch, rather than of a model-level setup cost.
- **The control that makes this a comparison**: the columns sent identical work and got identical
  answers — identical prompts, identical prompt token counts, identical completion counts, and 54
  of 54 paired samples byte-identical between the columns (§1.1) — so the difference is not a
  sampling or workload artifact. The one thing that moved between them is the flag in the start
  command.

None of that names the culprit inside `mx.compile`; it brackets where the cost is (decode, at
N = 1, on 4-bit affine weights) and leaves the microarchitecture to a profiler this study did
not run.

### 3.3 The harness pin, vindicated by the A/B

Track 1 pinned `--no-jit` to hold the runtime's features constant across the cells it compared,
and this study shows the pin was also the faster state on both artifacts — so none of the earlier
vMLX rows was measured in a configuration that a single flag would have improved.

The history is in the repository, not reconstructed here: `--no-jit` was added to
`Vmlx.start_command` in commit `296f812` ("Add vMLX as the fifth runtime, and pin what the
artifact would otherwise decide"), where the recorded reason is that JIT and MTP are each decided
by the artifact when left alone, and either would make two cells of this runtime differ by
something that is not the variable being measured. Commit `4d9dd0f` turned the pin into the
`OHYESMLX_VMLX_ENABLE_JIT` toggle used by this A/B with the default unchanged, its comment
recording that every command recorded before the toggle existed is byte-identical.

Two consequences, one for those documents and one for this one:

- **The Track 1 vMLX columns stand without a JIT asterisk.** The dense JANG study, the MoE JANG
  study and the cross-runtime JANG comparison were all measured with `--no-jit` in the command.
  This A/B measures what the other setting would have cost: a 2.7 % to 11.3 % decode penalty
  (1.5–8.7 tok/s) on exactly these two artifacts. The pin is therefore not a
  fixed feature that happened to be harmless — it is the faster of the two states, and a JANG
  cell left to the artifact's default would have published a slower number than the tables carry.
- **This run's JIT-off column is byte-comparable to those rows.** The runner's own header states
  it (`scripts/run_vmlx_jit_ab.sh:6-11`): unset means `--no-jit`, "which is why the jit-off column
  is directly comparable to the recorded vMLX rows." The A/B's off column is that same command,
  so the JIT-off figures here are not only internally consistent but position-compatible with
  the earlier vMLX record.

---

## 4. Actionable guidance for users

**For 4B–8B JANG affine bundles on Apple Silicon, turn JIT off.** Two equivalent ways, depending
on who owns the command line:

- **Pass `--no-jit`** on `vmlx serve` — the flag this harness uses, and the one the runtime
  documents as the final word against its own auto-enable.
- **Set `VMLX_DISABLE_JANG_AFFINE_JIT_DEFAULT=1`** when the command line is not yours to edit —
  a GUI-launched server builds its own argv, and this is the supported way to suppress the
  automatic JIT-on for JANG affine bundles (`docs/runtimes/vmlx.md` §3.3, §7.1).

What this buys on the two artifacts measured here: **1.5–8.7 tok/s, 2.7 %–11.3 %** of decode
rate, concentrated in decode; nothing in TTFT or prefill throughput changes in a direction you
can rely on, and peak memory is unchanged to within 81 MB. On the MoE the gain is the larger
share: 6.2–8.0 % across all three shapes.

Two boundary conditions travel with the advice:

- **Do not leave the flag unpinned and expect a default to be neutral.** Not passing
  `--enable-jit` is not a way to disable it: the artifact's format turns it on, so a command that
  says nothing says "on" for JANG affine bundles and "off" for everything else — two different
  feature sets in one table, decided by the model file.
- **This evidence is scoped to what it measured**: a dense 4B (`Qwen3.5-4B-JANG_4S`) and an MoE
  8B-A1B (`LFM2.5-8B-A1B-JANG_2L`), batch size 1, vMLX 1.6.59, an M2 Max. The directive that
  enabled JIT by default rests on a 397B model at a different size regime, and nothing here tests
  or contradicts it; at batch sizes above 1 the arithmetic that makes JIT lose here may not hold,
  because kernels can be amortized across the batch. Measure before generalizing, and pin the
  flag while you do.

To reproduce: `scripts/run_vmlx_jit_ab.sh` (a sweep, the two columns, a 30 s cooldown between
them, a final sweep, and the directories this document reads), or `OHYESMLX_VMLX_ENABLE_JIT=0|1`
around `python -m ohyesmlx.cli run --study format --cells …` for a different cell set.

---

## Appendix A — full-precision medians

Every percentage in this document is computed from these values, which were recomputed from the
two `results.jsonl` files for this document and check against each column's `leaderboard.md` at
its rounding.

### A.1 Decode rate and inter-token latency

| cell | workload | decode_tps off | decode_tps on | Δ % | itl_s off | itl_s on |
|---|---|---|---|---|---|---|
| `jang4s__vmlx` | chat | 58.6878 | 57.0312 | −2.82 % | 0.017173 | 0.017672 |
| `jang4s__vmlx` | prefill | 54.7700 | 53.3153 | −2.66 % | 0.018548 | 0.019054 |
| `jang4s__vmlx` | decode | 65.0217 | 57.6873 | −11.28 % | 0.015410 | 0.017369 |
| `jang2l__vmlx` | chat | 110.7159 | 103.8569 | −6.20 % | 0.009103 | 0.009704 |
| `jang2l__vmlx` | prefill | 108.9323 | 100.2392 | −7.98 % | 0.009326 | 0.010134 |
| `jang2l__vmlx` | decode | 113.3767 | 105.6169 | −6.84 % | 0.008837 | 0.009487 |

### A.2 TTFT and prefill throughput

| cell | workload | ttft_p50 off | ttft_p50 on | Δ % | prefill_tps off | prefill_tps on | Δ % |
|---|---|---|---|---|---|---|---|
| `jang4s__vmlx` | chat | 0.142314 | 0.144405 | +1.47 % | 203.7746 | 200.8242 | −1.45 % |
| `jang4s__vmlx` | prefill | 2.282014 | 2.230623 | −2.25 % | 575.8071 | 589.0732 | +2.30 % |
| `jang4s__vmlx` | decode | 0.139173 | 0.138744 | −0.31 % | 208.3738 | 209.0177 | +0.31 % |
| `jang2l__vmlx` | chat | 0.101914 | 0.103809 | +1.86 % | 313.9896 | 308.2584 | −1.83 % |
| `jang2l__vmlx` | prefill | 1.019113 | 1.032940 | +1.36 % | 1309.9622 | 1292.4272 | −1.34 % |
| `jang2l__vmlx` | decode | 0.102323 | 0.104907 | +2.52 % | 312.7338 | 305.0333 | −2.46 % |

### A.3 Memory, load and drift

`cold_load_s` and `first_request_s` are the cell's and repeat on its three rows; `peak_mb` is the
workload's, from the higher of the cell's two visits; `drift` is the cell's published
first-half-versus-second-half change.

| cell | workload | peak_mb off | peak_mb on | Δ MB | cold_load off | cold_load on | first_request off | first_request on | drift off % | drift on % |
|---|---|---|---|---|---|---|---|---|---|---|
| `jang4s__vmlx` | chat | 3791 | 3717 | −74 | 9.1126 | 6.0811 | 2.3352 | 1.9484 | −6.44 | −13.90 |
| `jang4s__vmlx` | prefill | 4605 | 4531 | −74 | 9.1126 | 6.0811 | 2.3352 | 1.9484 | −15.64 | −10.35 |
| `jang4s__vmlx` | decode | 3792 | 3711 | −81 | 9.1126 | 6.0811 | 2.3352 | 1.9484 | −17.84 | −11.75 |
| `jang2l__vmlx` | chat | 3596 | 3596 | 0 | 7.0726 | 6.0664 | 1.1839 | 1.2640 | +0.13 | −1.07 |
| `jang2l__vmlx` | prefill | 4266 | 4265 | −1 | 7.0726 | 6.0664 | 1.1839 | 1.2640 | −7.90 | −2.84 |
| `jang2l__vmlx` | decode | 3615 | 3615 | 0 | 7.0726 | 6.0664 | 1.1839 | 1.2640 | −6.33 | −2.16 |
