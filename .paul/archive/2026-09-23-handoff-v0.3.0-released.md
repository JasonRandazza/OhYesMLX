---
description: "OhYesMLX — session handoff, 2026-09-23 (v0.3.0 released)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-23 (v0.3.0 released)

> Session-transfer note. Read this, then `.paul/STATE.md` (Decisions 117–118), then `AGENTS.md`.
> Where this and STATE disagree, STATE wins.

## Where things stand

- **v0.3.0 is tagged and released:** https://github.com/JasonRandazza/OhYesMLX/releases/tag/v0.3.0
  (wheel + sdist on GitHub Releases; not published to PyPI). `main` is pushed.
- **Plan 03-09 (`ohyesmlx pareto`) was withdrawn before release** (Decision 117). It ranked
  `peak_mb` across runtimes and shipped a hand-copied, rounded table.
- **Duplicate and dead code trimmed** (Decision 118). There is now one decode/prefill/ITL definition
  (`measure.py`; `report._per_request` asks it), one disk-size walk (`measure.artifact_bytes`),
  shared grid/sweep join guards, and one `cli._join`. Powermetrics sampling and the `fits` floor are gone.
- **AGENTS.md's ~1,000-line target is retired** and replaced by three rules: one definition of everything,
  each rationale written once, and stop and ask before any new module, subcommand or header pin.
- **Tests:** 497 pass (`/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q`).
- **Knowledge graph:** `graphify-out/` (gitignored). Code-only (package, tests, scripts), 1,807 nodes.
  Rebuild with `graphify update .` after code changes.

## Next moves

1. `/paul:discuss-milestone` for the next milestone. Decide first whether non-MLX adapters
   (llama.cpp / Ollama) are in scope: they stretch the project's "MLX on a Mac" core value.
2. Optional: audit item 1, removing rationale restated across `report.py`/`measure.py` docstrings
   (~−800 lines, prose only). Deferred as low value per line of review.
3. README says `--cells` "or configuration files". There is no config-file selector, so fix the wording.
4. A pareto view rebuilt as `pareto <run_dirs>` from `results.jsonl`, within-runtime memory only,
   is a candidate if wanted.

## Standing invariants

Unchanged from AGENTS.md: one model resident at a time, a quiet machine while measuring, no
`ohyesmlx/*.py` edits during a grid, and the coherence gate before any number counts.
