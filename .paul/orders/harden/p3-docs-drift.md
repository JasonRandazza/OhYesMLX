GOAL: Hardening Phase 3, review group F (documentation drift). Findings and their evidence are in .paul/review/2026-09-23/docs.md: F1, F2, F3, F4, F5, F6, F7, F8, F9, F11, F12. F10 is FABRICATED (the quoted README lines do not exist) — ignore it. Phase 2 (A5 reasoning label, A7, D1 e2e percentiles, D3) has just landed; the code is the authority for every schema.
FILES: README.md, docs/interfaces.md, docs/runtimes/optiq.md, docs/runtimes/vmlx.md. Touch nothing else.
RULES:
- Every statement you write about a field, header key, runtime or behaviour must be checked against ohyesmlx/*.py first. Quote the code, not the old doc. Do not invent anything the code does not do.
- README runtime lists: exactly the five registered runtimes (runtimes.RUNTIMES keys: mlxlm, omlx, optiq, vmlx, osaurus). MLX Studio is not a registered runtime; mention it only as an external app if at all. No "all MLX runtimes" claims.
- F4: README must state what is actually pinned: request temperature 0 and seed; OptiQ sampler flags (Phase 1 A6 — check runtimes.py for what is pinned). Do not claim top_p / repetition_penalty are pinned where they are not.
- F11: replace stale line citations with function/symbol names (they do not rot); mark the "subclass would need" section in vmlx.md historical.
- F12: the one-definition rationale lives in AGENTS.md; interfaces.md points to it, does not restate it.
- Prose stays in the existing voice; change only what is drifted. No new sections beyond what a finding requires.
ACCEPTANCE: report per finding: fixed (with the code symbol you checked) or not-a-defect (with evidence). `git diff --stat` shows only the four files. Do not commit. No test run is needed (docs only), but run the suite once to confirm nothing reads these files: /Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q
