GOAL: a cell can PASS with fewer measured batches than pinned and say nothing. Seen: prompt sweep
Osaurus 128 — visit 1's runtime.start() raised, visit 2 measured its quota of 4, and
_set_status rewrote the row to PASS/None, erasing visit 1's failure. Make both visible.

READ FIRST: .paul/orders/short-measured.log (full diagnosis with file:line). Then measure.py
_visit / run_cells / _set_status, report.py summarize / _row / _entry / _cells / card.

FILES YOU MAY EDIT: ohyesmlx/measure.py, ohyesmlx/report.py, ohyesmlx/cli.py (only to thread
the pin if needed), tests/test_measure.py, tests/test_report.py.

REQUIRED:
1. A lost visit is not erased: when a visit fails (start raised, etc.) and a later visit
   measures, the final row stays PASS but keeps the lost visit's reason as a note (field name
   your choice, persisted in the record and read back leniently: absent = none). A cell whose
   every visit measured is byte-identical to today.
2. Short-window note, annotate not exclude (report.py's drift rule is the precedent): when
   measured count < the run's `measured` pin, the row carries "short measured window: K of N
   pinned batches landed; the median is over the K that did" in leaderboard notes and card, and
   render_grid/render_sweep entries print `<value> (n=K of N)` the way drift prints. Not a
   status, not a floor, not a ranking change. The pin comes from the run header.
3. cold_load_s/first_request_s: when the surviving visit is not the first, note that the cold
   load figure is from a later start. One sentence, same note mechanism.

WHAT MUST NOT CHANGE: every existing rendered grid and sweep where all cells measured their pin
(verify: render results/grid/grid.md's five run dirs with `ohyesmlx grid` before and after,
diff = empty; same for `ohyesmlx sweep --varying prompt_tokens --rank ttft_p50_s
results/sweep-prompt/*-format` except the Osaurus 128 entry and its note).

ACCEPTANCE: pytest -q green from 451. Tests: start raises on visit 1, visit 2 measures -> PASS
with the lost-visit reason kept and the short note; all visits fine -> no note; the grid/sweep
entry prints (n=K of N); old records lacking the new field load. Red-check test 1 against
current _set_status and report it. Paste the before/after diff results. Use
/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python. No git, no servers.
