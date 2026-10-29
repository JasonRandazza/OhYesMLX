GOAL: write three Phase 4 study writeups from the 2026-09-25 runs:
  docs/research/2026-09-25-kv-quant-sweep.md        (study 03-05)
  docs/research/2026-09-25-expert-streaming-sweep.md (study 03-03)
  docs/research/2026-09-25-multiturn-runtime-axis.md (study 03-04)
FILES YOU MAY EDIT: those three files only. Touch nothing else. Run nothing but read-only commands
(cat/grep/python reading results/*). No runtime, no measurement, no pytest, no git.

STYLE: match docs/research/2026-09-24-hardening-validation-grids.md — full prose, each table states
its axis and the caveat naming what it cannot claim (AGENTS.md "Vary one thing at a time"). Every
number recomputed from results.jsonl / leaderboard.md, with run directory named. Design intent:
docs/research/2026-09-20-v3-phase*-plan-03-0{3,4,5}-study-design.md — say where results answer it.

INPUTS: results/sweep-kvquant/{sweep-p16384.md,sweep-p32768.md,oq4__*/,void-oq4__osaurus-residency-unpinned/,runner-night.log,runner.log};
results/sweep-streaming/{sweep.md,stock4bit__*/}; results/multiturn/{grid.md,*/}, results/multiturn-osaurus/{grid.md,*/};
server logs results/logs/*-20260925T*.log; docs/research/2026-09-24-kv-quant-surface.md.

COORDINATOR'S VERIFIED FINDINGS (confirm each against the rows; flag any disagreement, do not paper over):
1. KV: only OptiQ drives a codec. decode off/affine8/affine4 = 69.8/35.0/33.5 (16k), 61.6/22.9/21.8 (32k);
   TTFT +12% (16k) / +18% (32k); peak 28672 -> 26624 MB; all coherent. Others `off` only (refused codecs are
   N/A rows, which the sweep table renders as `—` — note that rendering). Osaurus `off` was rerun 11:34–12:30
   after the night's cells were N/A from an unpinned host setting (commit 732eaef); its column was measured
   ~6 h after the others: name that confound. Osaurus/oMLX/mlx-lm/vMLX `off` rows are reasoning-timed, OptiQ
   content-timed — no cross-runtime TTFT ordering (Decision 122). peak_mb never ranks across runtimes (A7).
2. Streaming: OptiQ on = 9.3/9.6/9.3 vs off 84.4/90.3/77.7 (chat/prefill/decode); the model fits RAM, so this
   measures the cost, not a benefit. vMLX on (--flash-moe) = FAIL coherence (replacement chars, implausible
   words) with the `Flash MoE enabled: 40 layers patched, 18.12 GB freed` banner present — quote sample output.
3. Multi-turn: decode flat across turns (oMLX 82–89, mlx-lm/OptiQ ~70–74, vMLX ~66, Osaurus 51–61 with
   drift up to +27% — noisy); TTFT grows ~linearly with history on all five (no prefix reuse under these pins).
   oMLX turn-06 FAIL "still thinking" at max_tokens 128; oMLX turn-04 lacks the reasoning-timed note and reads
   105.4 — find out from its observations why (channel), and say it. The grid refuses to join the night run
   with the Osaurus rerun (duplicate cell, no latest-wins rule), so Osaurus is its own grid — present it
   alongside, with the time-of-run caveat.
Each doc ends with "Open questions" and "What this cannot claim". Report the three paths and any finding you
could not confirm.
