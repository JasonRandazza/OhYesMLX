# Order: why mlx-lm's prompt cache never hits in the multi-turn run (investigation, docs only)
Files you may touch: docs/research/2026-09-25-multiturn-runtime-axis.md (append an addendum section
answering its open question about mlx-lm's prompt cache); create docs/runtimes/mlx-lm.md only if
a per-runtime capability note is warranted (match the structure of docs/runtimes/omlx.md, short).
Evidence: mlx_lm.server source in ~/.local/share/ohyesmlx/mlx-lm-0.31.3 (the version measured), the
harness start command for mlx-lm in ohyesmlx/runtimes.py, results/multiturn/ run dirs and their
results/logs/mlxlm-* logs from 2026-09-25. Answer from source with file:line: how the server keys and
reuses its prompt cache, and why ten fixed turns of one conversation never hit (e.g. hybrid ArraysCache
not trimmable -- see docs/research/2026-09-17-cache-state-split.md -- or request shape, or a flag).
A negative claim needs source evidence (AGENTS.md "Never infer a capability from the absence of a flag").
No code changes, no git, no server starts. Report DONE with the answer, or BLOCKED.
