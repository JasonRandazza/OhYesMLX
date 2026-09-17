GOAL (read-only diagnosis, no edits): the prompt sweep's Osaurus 128-token cell
(results/sweep-prompt/, the osaurus run with prompt_tokens target 128; see
docs/research/2026-09-16-prompt-length-sweep.md "Osaurus at 128 is one visit's worth of
requests") recorded 13 warmups and 4 measured requests where the run pins measured=9, and was
marked PASS with no note. Find out why from the code and the record.

READ: ohyesmlx/measure.py (run_cells, warmup/plateau, visits, how `measured` is counted and
split across visits, what ends a visit early, how errors/timeouts are recorded), ohyesmlx/report.py
(what n_measured feeds, any floor on it), the record and log for that cell.

ANSWER:
1. The exact code path that let a cell finish with 4 of 9 measured requests. Quote file:line.
   If the record cannot distinguish between candidate paths, list them and what evidence each
   would leave, and which the record shows.
2. Whether any other of the 25 sweep cells or the published grids (results/grid/2026091*,
   results/grid-moe/2026091*) have n_measured below their pin. Give a list.
3. The smallest change that makes a short measured window visible: status, floor, or note —
   name the function and the rule you would add. Do not implement.
Do not start servers, run pytest, or use git. The machine is measuring; keep CPU use minimal.
