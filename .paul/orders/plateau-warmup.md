GOAL: the harness applies one warmup budget to five runtimes, and the joined grid showed that
this makes the runtime-axis ordering a ranking of warmup speed rather than serving speed. Make
warmup a measured property of the cell instead of a pinned constant.

FILES YOU MAY EDIT: ohyesmlx/measure.py, tests/test_measure.py.

READ FIRST: `docs/interfaces.md`, section "Phase 5 plan 05-02 — warmup is measured, not
pinned". It pins the rule, all three constants, the new field and the header change. Do not
deviate; if a constant looks wrong to you, say so in your report and implement the pinned one
anyway — the numbers came from the 60-cell grid and are not yours to retune.

THE DEFECT, measured. Decode workload, per-column median `change_pct` across the MEASURED
window: mlx-lm +17.0% (11 of 12 rows over 5%), oMLX +2.6%, mlx-optiq -0.0%, vMLX +0.5%,
Osaurus +1.0%. Every sign positive — cells getting faster, which is under-warmup. Re-ranked on
each cell's late-window median, mlx-lm moves from last in every decode row to 1st, 4th, 3rd and
3rd; on stock4bit from 66.6 to 77.4, which ties the leader.

REQUIRED:

1. `MIN_WARMUP = 3` stays. Add `WARMUP_CAP = 16` and `WARMUP_PLATEAU_PCT = 3.0`, each with the
   measured table above as the comment justifying it.

2. `_workload_visit`'s warmup loop becomes the plateau rule: after the floor, compare the last
   three warmup rates — `(max - min) / median` — and open the measured window when that spread
   is within `WARMUP_PLATEAU_PCT`. Rates come from `decode_tps`, the same function every
   published figure uses. A warmup observation carrying no rate cannot settle the window. The
   cap ends it either way.

3. New `CellResult` field `warmup_plateau: bool | None` and a record field beside
   `warmup_count`. `True` when every warmup window on this row settled, `False` when any hit
   the cap, `None` when no warmup ran. A row that hit the cap was still climbing and must not
   render as one that settled.

4. `run_cells`: `warmup: int | str = "plateau"`, `measured: int = 9`. An `int` still means a
   fixed budget of that many requests and still refuses below `MIN_WARMUP`. The run header's
   `warmup` becomes the dict the interface doc pins when the rule is in force, and stays the
   integer when a fixed budget was asked for.

5. `load_run` must round-trip the new field. It is the inverse of `_record`; keep it so.

ACCEPTANCE: pytest -q green from a 389 baseline, no regressions.

Tests must cover: a stream whose rates plateau immediately stops at the floor of 3; one that
keeps climbing runs to the cap of 16 and sets `warmup_plateau=False`; one that settles at,
say, 7 stops there with `warmup_plateau=True` and `warmup_count` 7; a warmup observation with
no decode rate cannot settle the window; `warmup=3` still means exactly three requests and
writes the integer header; the plateau header round-trips through `load_run`; and a measured
figure is unchanged by any of it — the warmup window must not contribute one sample to a
published number, and that assertion is the one that matters most.

Red-check the cap test and the "no rate cannot settle" test, and report that you did.

DO NOT change `measured_drift`, `decode_tps`, `_set_status`, the coherence gate, the visit
plan, or anything in report.py, cli.py, transport.py, runtimes.py. Do not start a server or
load a model — a full grid re-run under these pins is the coordinator's next step and it takes
hours, so a defect you leave here costs all of them.

ANSWER IN YOUR REPORT: with `measured=9` and `VISIT_ROUNDS` as it is, what quota does each
visit get, and does `measured_drift`'s early/late split still fall where its docstring says it
does? Name the numbers.
