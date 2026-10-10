---
description: "OhYesMLX — session handoff, 2026-09-25 evening (v3.1 Hardening: Phase 4 closed)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-25 evening (Phase 4 closed)

> Read this, then `.paul/STATE.md` (Current Position, Decisions 125–126, Deferred Issues), then
> `AGENTS.md`. STATE wins on conflict. The previous handoff is
> `.paul/archive/2026-09-24-handoff-evening-phase4-code-complete.md`.

## Where things stand

Phase 4 of v3.1 Hardening is **closed**. All four v3 script studies were re-run through the
harness and written up. **Tests: 634 pass.** Commits after `9bd1814` were local when this was
written — check `git log origin/main..main` before assuming anything is pushed.

| study | paper | results |
|---|---|---|
| 03-05 KV quant | `docs/research/2026-09-25-kv-quant-sweep.md` | `results/sweep-kvquant/sweep-p{16384,32768}.md` |
| 03-03 expert streaming | `docs/research/2026-09-25-expert-streaming-sweep.md` | `results/sweep-streaming/sweep.md` |
| 03-04 multi-turn | `docs/research/2026-09-25-multiturn-runtime-axis.md` | `results/multiturn/grid.md`, `results/multiturn-osaurus/grid.md` |
| 03-06 MTP depth | `docs/research/2026-09-25-mtp-depth-sweep.md` | `results/sweep-mtp-fixed/sweep-jang4s__vmlx.md`, `results/sweep-mtp/sweep-optiq*.md` |

Headlines, each argued with its caveats in its paper:

- **KV quant:** only OptiQ drives a live KV codec. affine8/affine4 cut its decode from 69.8 to
  35.0/33.5 tok/s at 16k and 61.6 to 22.9/21.8 at 32k, for about 2 GB of peak memory. Every other
  runtime refuses the codecs (N/A).
- **Expert streaming:** OptiQ `on` decodes at ~9.3 tok/s against ~84 `off`; vMLX `--flash-moe`
  printed its banner and then failed the coherence gate.
- **Multi-turn:** decode is flat across ten turns on every runtime; TTFT grows with history. oMLX
  switches timing channel between turns (so its turn-04 105.4 is content-timed) and its turn-06 is
  FAIL for no content. The Osaurus column was measured ~6 h after the other four and is its own grid.
- **MTP:** vMLX on the 4B JANG_4S — depth 1 and 2 are indistinguishable from off, depth 3 is
  16–20% slower; acceptance per added draft falls 0.73 → 0.50 → 0.29. Every OptiQ depth cell FAILs
  on its own log (35B head shape mismatch; 4B `TypeError` in `engine.py:760`).

## What went wrong on the night, and what fixed it

1. **Every Osaurus cell was N/A.** The Phase 4 runners lacked the grid runner's Osaurus pin, so the
   drift guard refused to start (host residency 30 s vs baseline 900 s). `scripts/osaurus-pin.sh`
   now carries the pin once (Decision 125, `732eaef`); Osaurus was rerun alone and its settings
   restored byte-exact. The void runs are kept as `results/sweep-kvquant/void-oq4__osaurus-residency-unpinned/`.
2. **vMLX's MTP depth was not held.** `--native-mtp-depth-policy fixed` leaves the AR-safety valve
   and the sticky start rung running; the night's depth-3 column ran 3.7% of its cycles at D3.
   Jason approved an env pin (Decision 126, `ac90077`); the rerun held every cycle at the pinned
   depth. The night's vMLX MTP runs are kept as `results/sweep-mtp/void-…depth-not-held…`.
3. My first order for (2) claimed the depth-3 logs never drafted at d3. They did, 5 and 4 times;
   the worker went BLOCKED on it, correctly. The same slip then put a depth-2 log's counts into
   `docs/runtimes/vmlx.md` §7.4.1 as depth-3 ones; the MTP paper's worker caught it and it is corrected.

## Working notes carried forward

- **Offload to Command Code**; Opus writes orders, reviews, runs the suite. `CC_AGENT_MAX_TURNS`
  300 for code, 200 for docs. Command Code self-updates: a dispatch that dies with
  `command-code/dist/index.mjs` ENOENT hit an update in progress — just redispatch.
- `scripts/run_sweep_mtp.sh` takes `PAIRS=` and `run_sweep_kvquant.sh` `RUNTIMES=` to rerun a subset;
  `run_multiturn.sh` takes `CELLS=`. Runners print their join commands; run them yourself.
- `grid` refuses to join two runs holding the same cell (no latest-wins rule) — a rerun column is
  its own grid.
- Graphify rebuilds on every commit (post-commit hook, log `~/.cache/graphify-rebuild.log`); wait
  for it to go idle before a measurement.
- Test command: `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q`.
- Host: Osaurus `modelIdleResidencyPolicy.seconds` is 30 by Jason's choice — the pin restores it.

## Later the same day (2026-09-25 evening)

- v3.1 deferred fixes landed and pushed: N/A cells render `N/A` (`f998dcd`), the single-run leaderboard
  applies A7 and Decision 122, OptiQ's MTP gate refuses a head that cannot fit the block (`773b739`),
  runners run their own joins (`afd8655`), mlx-lm prompt-cache answer (`4cb0c9b`), docs aligned to the
  code (`22c2180`), third 35B replicate written up (`d6931de`, Decision 127).
- LMRE archived (local `~/Dev/archive/`, GitHub read-only), removed from `sync-omarchy`.
- Command Code self-updates on launch: stagger dispatches ~45 s apart, or five at once race the update.

## Next moves

1. Jason's two calls in STATE Blockers/Concerns: the fixed seed disables batching on mlx-lm and OptiQ
   (so the 2026-09-16 "none batch" finding is partly harness-induced), and AGENTS.md's sampler/chat-template
   pinning rule vs what the harness does.
2. Remaining Deferred Issues are small or waiting on a trigger (Osaurus pin copies whose semantics differ,
   `cached_tokens` not recorded, CI, disk audit, old run dirs, thinking-off MMLU).
3. Phase 4 and v3.1 order files are `.paul/orders/{p4,v31}-*.md`; their `.log` files are untracked
   transcripts and can be deleted.
