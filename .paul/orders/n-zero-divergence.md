GOAL: a cell that answered in the reasoning channel must publish n = its real sample count, not
n=0. Today report.py and measure.py disagree about what "came back" means.

FILES YOU MAY EDIT: ohyesmlx/report.py, ohyesmlx/measure.py, tests/test_report.py,
tests/test_measure.py.

THE DIVERGENCE, found by the worker that built the floors:
- `report._row` counts samples with `[o for o in observations if o.ok]`.
- `measure._came_back(o)` is `o.ok or o.error == EMPTY_CONTENT_ERROR`.
A response that produced no content delta but did produce reasoning has `ok=False` and
`error == EMPTY_CONTENT_ERROR`. measure counts it; report does not.

Observed on the real record `results/20260915T151218Z-runtime/results.jsonl`: measure wrote
`measured_count: 5` and the leaderboard printed `n = 0/5` for the same cell.

WHY THIS IS URGENT RATHER THAN COSMETIC. It changes no figure on that record because the row
is FAIL. But two of the five runtimes this project measures — stock mlx-lm and vMLX — answer
ENTIRELY in the reasoning channel on a thinking model. Measured today on Qwen3.5-4B, both
returned coherent text with zero content deltas. Those cells will PASS and publish `n=0/5`
with real figures beside it. A sample count of zero next to a populated row is the kind of
number a reader either disbelieves or, worse, believes.

REQUIRED: one definition of "this request came back", used by both modules. `measure._came_back`
already encodes it correctly — expose it as a public predicate on measure and have report use
it, rather than respelling the condition in report (respelling it is how the two drifted
apart). report already imports from measure for the coherence floor, so the precedent exists.

CHECK EVERY OTHER `.ok` READ in report.py while you are there and say in your report which ones
you changed and which you deliberately left. Some may be correct as `.ok` — a figure that needs
content timing genuinely requires a content delta. Do not change those; the two-content-delta
rate domain is correct and stays. This is about the SAMPLE COUNT and anything else that means
"did this request happen", not about which requests have valid timing.

ACCEPTANCE: pytest -q green from a 294 baseline, no regressions. Tests must cover: a
reasoning-only observation counts toward n in report; a genuine transport failure still does
not; the rate columns are unchanged for both cases; the published figures for an ordinary
content-streaming cell are byte-identical to today. Red-check it and report that you did.

Do not touch transport.py, runtimes.py, coherence.py, token_counter.py, cli.py. Do not start a
server or load a model.
