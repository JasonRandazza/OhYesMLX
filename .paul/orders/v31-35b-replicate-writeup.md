# Order: writeup -- third 35B replicate settles the level shift
Write docs/research/2026-09-25-35b-third-replicate.md in the style of
docs/research/2026-09-24-hardening-validation-grids.md (read it first; this settles its open item).
Also append a dated "Update 2026-09-25" note to that 09-24 paper and to docs/research/2026-09-20-35b-moe-serving.md
pointing at the new paper (never rewrite their findings). Touch only those three files.
Data: results/grid-35b/grid.md (published 2026-09-20), results/harden-2026-09-23/grid-35b/grid.md (r2),
results/harden-35b-r3/grid.md (r3, 18:17-20:24 EDT 2026-09-25, runner.log, run dirs, logs). Coordinator figures
(median per-runtime ratio over the 9-12 shared cell-workloads, decode_tps): r2/pub mlxlm +19.7 omlx +16.8
optiq +10.7 vmlx +1.5 osaurus -8.1; r3/pub +22.2 +25.6 +16.9 +5.4 +2.7; r3/r2 +2.7 +6.6 +5.6 +3.7 +6.8 (%).
Re-derive them; report any disagreement. Format ordering stock4bit > oq4 > optiq holds in every column of all
three grids except Osaurus, whose oq4/optiq pair swaps in pub and r3 by 1-4 tok/s.
Must cover: axis/caveat; the conclusion (r2 and r3 agree within ~3-7%, so the 09-20 levels for mlx-lm/oMLX/OptiQ
are the outlier; finding 17's cross-runtime levels are superseded, its format orderings stand); what differs between
the grids (harness sha, reasoning-timed labels, drift signs -- the published grid's positive drifts), what r3 cannot
say (why 09-20 was low; r3 ran in an evening with desktop apps open; r3 is uniformly a few % above r2); runtime-axis
orderings that changed (read them from the tables). No git, no runtimes. Report DONE or BLOCKED.
