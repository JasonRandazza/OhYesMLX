GOAL: write docs/research/2026-09-17-cache-state-split.md — the 06-02 cold/warm KV result — and
explain from evidence why three runtimes show no warm benefit.

FILES YOU MAY EDIT: that new doc only. No git, no pytest, no servers (a read of installed source and
logs is fine). Match docs/research/ style: full prose, tables, numbers recomputed from records.

INPUTS: results/sweep-cache/ (10 run dirs, oq4, --prompt-tokens 4096, off then on per runtime,
run 2026-09-16 22:47–23:35 local), results/sweep-cache/sweep-ttft.md
(`ohyesmlx sweep --varying cache_state --rank ttft_p50_s`), server logs under results/logs/ for
those times, scripts/run_sweep_cache.sh, docs/interfaces.md "06-02", docs/research/
2026-09-16-phase6-design.md "Cold versus warm KV", docs/research/2026-09-16-prompt-length-sweep.md.

Coordinator's reading (verify every number): TTFT p50 off → on: mlx-lm 7.825→7.845, oMLX
8.487→0.487, OptiQ 9.813→9.983, vMLX 8.283→8.260, Osaurus 9.401→0.404. All 10 PASS, 9 measured,
0 failed requests. oMLX and Osaurus first warmup TTFT ~11.6/10.2 s then collapse — cache hits.

REQUIRED:
1. Table off/on/ratio, p50 and p90; first-request vs rest for each "on" cell.
2. **Why mlx-lm, OptiQ and vMLX "on" show no hit.** First confirm from the server logs / recorded
   start commands that the "on" flags (--prompt-cache-size 10; --enable-prefix-cache) were live.
   Then find the reason in the installed source (mlx-lm 0.31.3 at
   ~/.local/share/ohyesmlx/mlx-lm-0.31.3, mlx-optiq 0.5.6, vMLX 1.6.59 `vmlx_engine`): Qwen3.5-4B is a
   hybrid (linear-attention/SSM + attention) model — check whether its cache is trimmable/reusable
   (e.g. ArraysCache / can_trim_prompt_cache / is_trimmable, vMLX ssm-state-cache flags, any log
   line saying the prefix cache was skipped). Quote file:line. If not established, say unverified.
3. Compare the off cells with the 4096 column of the prompt-length sweep (same cell, cache pin
   absent there); note Osaurus is 0.25.5 here vs 0.25.4 in that sweep.
4. Osaurus: caches toggled by runner, residency pinned 900 s, restored byte-exact (runner exit 0
   = cmp passed). oMLX "on" uses its SSD cache dir in per-run scratch.
5. What this means for a reader, and open questions (e.g. would a non-hybrid model show mlx-lm/
   vMLX hits; is the warm figure a publishable prefill number or a lookup number).
Also note the stdout runner.log is 0 bytes again (per-run logs are fine) — one line, no digging.

REPORT: path, the headline numbers, and the answer to 2 with its evidence.
