GOAL: Write the findings document for the 06-01c prompt-length sweep, just run.

FILES YOU MAY EDIT: NEW docs/research/2026-09-16-prompt-length-sweep.md only. Read-only
everywhere else, including results/ (gitignored, local). No git, no servers, no pytest.

INPUTS: results/sweep-prompt/*-format/ (25 runs: 5 runtimes x 128/1024/4096/16384/32768, oq4
cell, Qwen3.5-4B), results/sweep-prompt/log-*.log, results/sweep-prompt/sweep-ttft.md (rendered
with `ohyesmlx sweep --varying prompt_tokens --rank ttft_p50_s`). Context:
docs/research/2026-09-16-prompt-length-context-limits.md (incl. "Measured"),
docs/research/2026-09-16-phase6-design.md, scripts/run_sweep_prompt.sh. Match the style of the
other docs in docs/research/ (full prose, tables, no summary-of-summary).

COVER, each from the data (compute; quote numbers):
1. The TTFT p50 table, and TTFT p90 beside it. Ordering per length; where adjacent runtimes are
   within ~3%, say it is a tie, not a rank.
2. Scaling: TTFT vs length per runtime, and prefill tok/s = locally counted `achieved` / TTFT
   (NOT usage.prompt_tokens: Osaurus reports chars/4). Where does each runtime's rate peak and
   fall off.
3. Cache-hit check: for every cell, first warmup TTFT and min TTFT against measured median. The
   coordinator found none (min/median >= 0.68, the 0.68 being Osaurus at 128, sub-second).
   Confirm or refute per cell.
4. vMLX at 32k: status FAIL. Count ok vs failed requests (warmup + measured; coordinator saw 28
   failures, error "chat stream produced no content", streams closing after 6-25 s, no HTTP
   error), their timing pattern, and that the earlier probe served 32k twice. It is not a
   context refusal (`—`) — say what it is and is not. Do not speculate past the data.
5. Osaurus ran with prefix and block-disk caches off (runner toggles and restores; final drift
   NONE, verified).
6. Caveats: the drift annotations in the TTFT table are decode-rate drift, not TTFT drift; the
   mlx-lm 4k decode drift +6.7%; warmup counts per cell and the ~8 h wall time vs the 4-5 h
   budget (32k cells 38-49 min).
7. Open questions this raises (e.g. rerun vMLX 32k? publish with it as FAIL?). Jason decides.

REPORT: the file path and the three most important numbers.
