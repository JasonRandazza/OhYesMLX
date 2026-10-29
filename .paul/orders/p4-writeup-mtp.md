# Order: Phase 4 writeup -- native-MTP draft-depth sweep (03-06)

Goal: write `docs/research/2026-09-25-mtp-depth-sweep.md`, in the style and rigour of the three
Phase 4 writeups already committed (`docs/research/2026-09-25-*.md`, read them first).

Inputs (read all; results/ is gitignored, cite paths):
- vMLX, valid: `results/sweep-mtp-fixed/sweep-jang4s__vmlx.md`, its run dirs and `runner.log`;
  logs `results/logs/vmlx-20260925T16{4108,4505,4813,5148,5452,5834}-*.log`, `...T17{0143,0616}-*.log`.
- vMLX, void (keep, explain why): `results/sweep-mtp/void-*` and `*.void-depth-not-held.log`.
- OptiQ: `results/sweep-mtp/sweep-optiq4b__optiq.md`, `sweep-optiq__optiq.md`, their logs.
- Mechanism: `docs/runtimes/vmlx.md` §7.4-7.4.1, commit ac90077, `docs/runtimes/optiq.md`.
Coordinator-verified facts (re-derive from logs, report any disagreement as a finding):
- Fixed rerun, summed over both visits: d1 accept 0.73 (depth 1), d2 0.50 (depth 2), d3 0.29 (depth 3);
  every cycle drafted at the pinned depth; 0 fallback_to_ar, 0 start-rung lines, 0 margin_truncated.
- decode tok/s off/1/2/3: decode 72.4/74.9/71.1/60.5; chat 74.9/74.7/70.8/60.0; prefill 75.6/79.0/76.1/62.3. All reasoning-timed.
Must cover: axis + caveat (one runtime per pairing; a 4B; single visit per depth; desktop apps open);
why no speedup (acceptance falls per depth, verify cost); the void run and the pin fix; the OptiQ FAILs
with their quoted reasons; what this cannot claim (35B vMLX untested, other runtimes refuse MTP).
Touch only that one new file. No git, no runtimes, no pytest. Report DONE or BLOCKED with the reason.
