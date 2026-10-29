# Order: write up the seedless + uncapped concurrency sweep (Decisions 128, 129)
Write docs/research/2026-09-27-concurrency-batching.md, full-detail paper in the style of
docs/research/2026-09-25-mtp-depth-sweep.md. Append a dated "Superseded 2026-09-27" note at the top of
docs/research/2026-09-16-concurrency-omlx.md pointing to it (do not rewrite that paper's body).
Files you may touch: those two only. Touch nothing else. No git, no server starts, no measurement.
Sources (read the rows; every figure must come from a leaderboard.md / results.jsonl, never from this order):
- results/sweep-conc-seedless/ -- 2026-09-27 02:56-09:56, all five runtimes, seedless, caps still 1 (Decision 128 only).
- results/sweep-conc-uncapped/ -- oMLX/OptiQ/vMLX with caps = N (Decision 129). vMLX N=1,2,4 ran 15:07-15:50;
  the sweep was stopped at 15:50 (Jason had to move the Mac) and vMLX N=8 ran alone 19:03-19:38. Say so.
- Joins: sweep-oq4__*.md in both dirs. STATE.md Decisions 128-129; docs/runtimes/{omlx,optiq,vmlx}.md cap rows.
Must cover, per workload (chat, prefill, decode): per-request decode tok/s, aggregate tok/s, TTFT p50 at N=1,2,4,8.
1. The harness caused the 2026-09-16 "none batch" finding: the seed (mlx-lm, OptiQ) and the hard-coded caps
   (oMLX, OptiQ, vMLX). Capped vs uncapped side by side for the three.
2. Decode workload: who batches and by how much (aggregate at N=8 / N=1); Osaurus flat as shipped (no flags; say
   "not tested whether a setting changes it", never "cannot").
3. Prefill workload: oMLX and vMLX aggregate stays ~18-23 tok/s. Check docs/runtimes/omlx.md / the order log
   .paul/orders/v31-conc-cap.log item 3 (oMLX prefill_batch_size=1 hard-coded, scheduler.py:3088) and say what the
   source shows and what is only inferred. Why their N=1 prefill TTFT is ~2-3 s vs mlx-lm/OptiQ ~0.15-0.19 s:
   report what the rows show; do not invent a cause.
4. Every row with |drift| > 5% named with its value and the row's own note: notably uncapped oMLX prefill N=2
   (+118.9%, still warming) and vMLX decode N=4 (-32.7%, ran 15:28-15:50 while the machine was about to be moved --
   state that as timing only, no cause claimed). Say which conclusions they do and do not touch.
5. Caveats: one model (Qwen3.5-4B-oQ4), one machine, runtime axis within one runtime per sweep (each table varies N
   only), cross-runtime levels are not rankings (different sessions), reasoning-channel timing labels.
6. What an everyday user should take from it, one short section.
Report DONE or BLOCKED with any figure you could not trace to a row.
