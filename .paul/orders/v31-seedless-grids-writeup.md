# Order: write up the seedless validation grids (Decision 128)
Write docs/research/2026-09-28-seedless-validation-grids.md, full detail, in the style of
docs/research/2026-09-24-hardening-validation-grids.md, which it is the counterpart of. Append a dated
"Update 2026-09-28" note to that paper pointing here (do not rewrite its body).
Files you may touch: those two only. No git, no server starts, no measurement.
Sources (every figure from a leaderboard.md / results.jsonl / grid.md; none from this order):
- New: results/harden-2026-09-27-seedless/grid-{35b,dense,moe}/ (+ runner-*.log, tonight.log): 22:01-04:51,
  seedless (request_seed None on every row), runtime caps at N=1 (byte-identical commands to 09-23).
- Old: results/harden-2026-09-23/grid-{35b,dense,moe}/ (seed 0). The two cannot be joined (pin guard); compare
  per cell and workload by reading both.
Must cover:
1. Status: 35B 48/48 PASS, dense 60/60, MoE 59/60 -- the one FAIL (moe optiq__osaurus decode, no content tokens):
   say whether the 09-23 grid had the same FAIL, from its rows.
2. Per runtime and grid: median and range of decode tok/s and TTFT p50 change new vs old. The coordinator's
   reading, to check not copy: every runtime's decode fell (oMLX/vMLX/Osaurus about -4 to -16%, which the seed
   cannot explain -- they do not route on it), while mlx-lm and OptiQ fell further (-13 to -25%) and their TTFT fell
   31-43% on dense/MoE. Separate the common-mode session shift from the seed-path effect only as far as the rows
   allow; say plainly what cannot be separated (two sessions, no replicate). Cite Decision 127's 10-26% session
   level shift on 35B as precedent (STATE.md).
3. Do the format orderings within each runtime (the project's findings) still hold? Per runtime, list any inversion.
4. What this means for the published figures: which findings stand on orderings, which quote levels.
5. Caveats and "what this cannot claim".
Report DONE or BLOCKED with any figure you could not trace.
