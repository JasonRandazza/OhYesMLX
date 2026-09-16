GOAL: the deferred-load note fires on workloads that did not carry the load. Attribute it to
the workload that actually made request #1, and say nothing on the others.

FILES YOU MAY EDIT: ohyesmlx/measure.py, ohyesmlx/report.py, tests/test_measure.py,
tests/test_report.py.

## THE DEFECT

`measure.py` computes the cold visit's first-request latency once and copies it onto EVERY
workload row of that cell (see `_first_warmup_latency` and the `cold_visit` block at the end
of the visit). `report.py::_row` then compares that one number against THIS ROW's own median
measured request, which is a different workload's population:

    "first_request_note": _deferred_load_note(
        result.first_request_s, [observation.total_s for observation in measured]
    )

A visit runs chat, then prefill, then decode. Request #1 belongs to whichever ran first. On
the other two rows the comparison crosses workloads, so an EAGER loader's honest 3.6-5.0 s
chat request is measured against prefill's ~1.0 s median and reads as +2.6-4.0 s of deferral
that never happened. Measured: `DEFERRED_LOAD_EXCESS_S = 1.0` fires on 15 of 60 recorded rows;
only the rows whose own workload ran first are real.

`DEFERRED_LOAD_EXCESS_S` is NOT the bug and its value must not change. The comment block above
it records the populations that chose 1.0 s and stays as it is. No threshold separates these
populations, because the two sides are not comparing the same thing.

## WHAT TO BUILD

`first_request_s` stays on every row — it is the visit's fact and the column is correct. Only
the NOTE moves. A row earns the note only when its own workload made the visit's first
request; every other row of that cell carries no deferred-load note at all.

Do it by recording, on the cold visit, WHICH workload carried request #1 — the loop already
knows, since `_first_warmup_latency` walks the results in the order they ran. Follow how
`first_request_s` is already set on every result; do not invent a second mechanism beside it.
A visit with no warmup observations records nothing and every row stays silent, as now.

Do not fold this into a new column, do not average across workloads, and do not add a config
knob. The rows that lose the note lose a claim the harness could not support.

## ACCEPTANCE

pytest -q green from a 331 baseline, no regressions. Tests must cover: the workload that ran
first gets the note when the excess clears the threshold; a sibling workload of the same cell
whose median is far below that same first request gets NO note; a cold visit with no warmups
leaves every row silent; a warm visit still carries no note. Red-check each one and report it.

Do not start a server, load a model, or send a request. Do not touch runtimes.py,
transport.py, coherence.py, token_counter.py, sample.py, cli.py.
