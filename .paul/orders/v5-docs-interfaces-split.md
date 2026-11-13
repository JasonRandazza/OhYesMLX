# Order: split docs/interfaces.md into docs/interfaces/ by subject (verbatim); one deliverable, no tangents
Why (Jason, 2026-11-13): the file is 1,861 lines in 21 sections filed by when they were written; workers read it whole. Split it so a reader opens one 100-400-line file per subject.
Mapping (move each `## ` section VERBATIM, in its current order, heading included; do not edit, merge, reword or reflow any moved text):
- `docs/interfaces/measurement-core.md`: sections from `## \`ohyesmlx/transport.py\`` through `## Metric formulas` (transport, runtimes, sample, measure, report, metric formulas)
- `docs/interfaces/grid-and-warmup.md`: `## Phase 5 — the joined grid`, `## Phase 5 plan 05-02 — warmup is measured, not pinned`
- `docs/interfaces/sweep-pins.md`: the five `## Phase 6 ...` sections (sweep is a pin; 06-01b concurrency; 06-01c prompt-length; lost visit; 06-02 cache-state)
- `docs/interfaces/study-pins.md`: `## Phase 4 study 03-05`, `## Phase 4 studies 03-06, 03-03`, `## Phase 4 study 03-04`
- `docs/interfaces/v5-onboarding.md`: `## v5.0 — Onboarding shapes (pinned 2026-10-29, T0.2)`
- `docs/interfaces/v5-quickbench.md`: `## v5.0 plan 04-03a`, `## v5.0 plan 04-03b`
- `docs/interfaces/v5-hardening.md`: `## v5.0 plan 045-02a`, `## v5.0 plan 045-02b`
Each new file starts with `# <Subject> — interface shapes` and one sentence naming what it covers; then the moved sections.
`docs/interfaces.md` becomes an index: its original preamble (lines before the first `## `), then a table: every original `## ` heading (exact text) → the file that now holds it. Old references like "docs/interfaces.md section X" must resolve through this table.
Update live references (not history): every `interfaces.md` mention in `ohyesmlx/*.py`, `tests/*.py`, `scripts/*`, `AGENTS.md`, `.paul/orders/PREAMBLE.md`, `docs/runtimes/*.md`, `docs/threat-model.md` → the specific new file (keep a section name if one was given). Do NOT edit `.paul/phases/**`, `.paul/orders/*.log|*.md` other than PREAMBLE, `.paul/archive/**`, `docs/research/**` — they are history and resolve through the index.
Verification you must run and report: a script that concatenates the `## ` sections of the seven new files in the mapping order and compares them byte-for-byte to the original sections (from `git show HEAD:docs/interfaces.md`); it must print IDENTICAL. Line counts per new file. `grep -rn 'interfaces\.md'` over the live-reference paths after your edits. `/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python -m pytest -q` (1329) green. Do not commit.
Files you may touch: docs/interfaces.md, docs/interfaces/*.md (new), and the live-reference files above (reference text only). Report under 250 words.
