# Phase 3 plan 03-02 — the format axis on a MoE model

Date: 2026-09-16, measured 07:15–08:40Z. Run directories (gitignored):
`results/grid-moe/20260916T071532Z-format` (mlx-lm), `…T073145Z` (oMLX), `…T074854Z`
(mlx-optiq), `…T080547Z` (vMLX), `…T082354Z` (Osaurus). Rendered with
`ohyesmlx grid <the five directories>`.

Subject: `LFM2.5-8B-A1B` — `model_type: lfm2_moe`, 8 B total, **1 B active, 32 experts,
top-4**. Same five runtimes, same three workloads, same pins as the dense grid:
`warmup {mode: plateau, window: 5, floor: 10, cap: 20, plateau_pct: 3.0}`, `measured 9`,
`temperature 0.0`, `seed 0`, `cooldown_s 30.0`.

**59 of 60 PASS**, 59 of 60 settled, one FAIL. 1 h 24 m — a little over half the dense grid's
wall clock, because only 1 B of the 8 B parameters is active per token.

## The headline: the format ordering does not transfer between models

The dense grid's result, replicated in three codebases that share nothing, was a clean
four-way separation:

> `stock4bit > oq4 > oq4e > OptiQ`, zero inversions in five columns.

The MoE grid does **not** reproduce that. It reproduces something simpler and, read carefully,
more interesting:

> `stock4bit` wins by a wide margin, and the three specialized formats are **tied with each
> other**.

stock-4bit's margin over the best non-stock format in the same column:

| workload | mlx-lm | oMLX | mlx-optiq | vMLX |
|---|---|---|---|---|
| chat | +13.4% | +13.8% | +11.0% | +4.6% |
| prefill | +13.1% | +16.9% | +12.4% | +5.3% |
| decode | +13.8% | +12.1% | +11.6% | +9.0% |

And the spread among `oq4`, `oq4e` and `OptiQ` in the same column:

| workload | mlx-lm | oMLX | mlx-optiq | Osaurus |
|---|---|---|---|---|
| chat | 1.0% | 1.2% | 7.1% | 6.2% |
| prefill | 0.3% | 1.0% | 1.2% | 6.8% |
| decode | 1.1% | 2.1% | 2.5% | — |

In mlx-lm, oMLX and mlx-optiq — the three that agreed so precisely on the dense model — the
three specialized formats sit inside 0.3–2.5% of each other. By the rule Phase 5 established
for the runtime axis, **that is a tie, not an ordering**, and the rank numbers the grid prints
for them should be read as such. Only Osaurus separates them at all (6–7%), and it is the
column whose KV prefix cache cannot be turned off.

So the dense model's clean `oq4 > oq4e > OptiQ` tail is not a property of those quantizers. It
is a property of those quantizers **on that model**. On a 32-expert MoE they are
indistinguishable from each other and all three give up 11–17% to stock MLX 4-bit.

This is exactly the kind of claim the single-variable discipline exists to license. Both grids
hold the runtime constant down each column and vary only the format; the two grids differ in
the model and in nothing else that was measured. A published comparison that had run one model
and generalized would have got the tail ordering wrong.

## On-disk size, and OptiQ again

| format | GB |
|---|---|
| JANG_2L | 3.06 |
| stock 4-bit | 4.78 |
| oQ4 | 4.99 |
| oQ4e | 4.99 |
| OptiQ | 5.47 |

OptiQ is the largest artifact here, as it was on the dense model (4.04 GB against stock's
3.06), and it is last or tied-last on speed in every column that carries it. Two models, same
finding: OptiQ costs disk and returns nothing measurable on either axis this project measures.
It may well buy accuracy — that is v2's question and nothing here speaks to it.

JANG_2L is by far the smallest at 3.06 GB, 36% under stock, and it leads Osaurus's decode
column outright (147.1) while sitting mid-pack on vMLX. As on the dense model it cannot be a
format-axis row, because no runtime loads it alongside the others.

## The runtime axis of this grid

- `stock4bit` decode: oMLX 159.6 > mlx-optiq 155.0 > mlx-lm 154.3 > vMLX 133.3
- `oq4` decode: Osaurus 145.4 > oMLX 142.5 > mlx-optiq 139.0 > mlx-lm 135.5 > vMLX 120.9
- `oq4e` decode: Osaurus 142.5 > oMLX 142.4 > mlx-optiq 138.6 > mlx-lm 134.1 > vMLX 119.8
- `jang2l` decode: Osaurus 147.1 > vMLX 122.2

**vMLX is last in every row of this grid**, by 10–20% — a reversal from the dense grid where it
sat mid-pack. **Osaurus leads the rows it can enter**, and mlx-lm, oMLX and mlx-optiq are
within a few percent of each other on most rows. The oMLX/mlx-optiq/mlx-lm cluster at
142.5/139.0/135.5 on `oq4` is a 5% band across three runtimes; Phase 5's tie rule applies to
the middle of it as much as it does anywhere.

Memory, decode workload, and read with the eighth defect in mind — `footprint` is not one
quantity across runtimes, so this is five numbers rather than a ranking: mlx-lm 4822–5545 MB,
oMLX 5014–5671, mlx-optiq 4919–5492, vMLX 3624–5419, Osaurus 3703–4616.

## The one FAIL, and why it is the right outcome

`optiq__osaurus` on the decode workload:
`no content completion tokens from token_source='none', so decode tok/s is undefined`.

Osaurus served the OptiQ artifact, produced text, and reported no usable completion-token
count for that combination — so the harness has no numerator for a rate. It publishes a FAIL
rather than a number derived from re-tokenized output, which is the rule that has held since
Phase 2: **never report an unreconciled number.** The same cell passes on chat and prefill, so
this is specific to the 512-token shape.

It also exercised the grid's four entry states on real data for the first time: that cell
renders `FAIL`, the combinations that were never run render `—`, and a reader can tell them
apart. Under the three-state rendering the workers first built, a measured failure and a cell
that does not exist would have looked identical.

## What this does not say

- **Nothing about accuracy.** These are speed and memory figures. A format that gives up 13%
  of throughput and buys back quality is a good trade this project cannot see, and v1 refuses
  to guess at it.
- **Nothing about 256-expert MoE.** LFM2.5-8B-A1B has 32 experts and every runtime served it
  coherently. The checkpoint that fails has eight times as many. The standing caveat holds:
  a clean result here validates the machinery and exonerates nothing at 256. See
  `docs/research/2026-09-16-moe-loadability-probe.md` and the Phase 4 write-up.
- **Nothing about the dense tail ordering being wrong.** It replicated in three codebases and
  stands on that model. What this grid shows is that it does not generalize.
