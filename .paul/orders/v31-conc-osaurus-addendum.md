# Order: add the Osaurus sequence-cap sweep to the concurrency paper
Edit docs/research/2026-09-27-concurrency-batching.md only. No git, no server starts.
Source: results/sweep-conc-osaurus-seqs/ (runner.log, sweep-oq4__osaurus.md, each run's leaderboard.md):
2026-09-27 20:34-21:56, Osaurus alone, host concurrency.maxConcurrentSequences set to the run's N by
scripts/osaurus-pin.sh osaurus_set_seqs (commit 8899b3a) and restored byte-exact after. Every figure from those rows.
1. Add a section after the decode results: Osaurus with its sequence cap at N, side by side with the seedless
   (cap 1) Osaurus rows, all three workloads, per-request decode / aggregate / TTFT p50 at N=1,2,4,8.
2. Resolve the paper's Open question 1 (maxConcurrentSequences): answered, with the numbers. Note that
   memorySafety safe_auto (docs/runtimes/osaurus.md, the memory-safety section) did not bound it at N<=8 on this
   host -- as observed, not as a source claim.
3. Update the headline, the everyday-user section and "what this cannot claim" so no sentence still says Osaurus
   does not batch as its conclusion; the as-shipped cap-1 result stays, labelled as the host default.
4. Name any row with |drift| > 5% (N=1 chat +48.0% among them) as the paper already does for the others.
Report DONE or BLOCKED.
