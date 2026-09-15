# BLOCKED — coherence gate call site (issue #7)

## Delivered and verified

- `ohyesmlx/coherence.py` — `is_coherent(text, *, expect=None) -> (passed, reason)`, the four
  checks, stdlib only, 94 lines including the module docstring (67 of them code). The first
  failing check is the reason returned.
- `tests/test_coherence.py` — 16 checks, including the captured salad verbatim from
  `docs/research/2026-09-14-oq-portability-spike.md` (a test asserts the fixture equals that
  line, so it cannot drift into a paraphrase) and a coherent English completion.
- `python -m pytest -q` → **199 passed** (baseline 183 + 16 new). No regressions.

## Blocked: the wiring in `ohyesmlx/measure.py`

Task rule: *"run after warmup, before a cell measures. Use a fixed deterministic prompt with a
checkable answer at temperature 0."* That probe is a transport call, and `tests/test_measure.py`
pins the exact number of transport calls per visit and the exact `results.jsonl` line count at
specific call indices. I may not edit that file. Measured in a scratch copy, four ways:

| wiring tried | result |
|---|---|
| probe as its own request after warmup, expectation off | 178 passed, **5 failed** |
| probe as its own request, expectation enforced | 163 passed, **20 failed** |
| probe replaces warmup #1, expectation enforced | 163 passed, **20 failed** |
| probe replaces warmup #1, expectation off, gate judges only responses that came back | **183 passed** |

The five failures of row 1 are the count assertions themselves, not bugs:

1. `test_the_measured_requests_are_split_across_the_visits` — `[4, 3] == [3, 2]`
2. `test_warmups_run_before_the_measurements_and_never_reach_the_samples` — `13 == 5 + 2*3`
3. `test_results_are_persisted_after_every_visit` — `seen[6]` shifts by one call
4. `test_the_persisted_record_carries_raw_observations_and_the_pins` — probe sample in
   `warmup_observations` makes `8 == 2*3`
5. `test_the_handle_is_stopped_after_every_visit_even_when_requests_fail` — a dead server's
   empty response read as "still thinking" (fixable: 183 in row 4 once the gate judges only
   responses that came back)

Rows 2 and 3 add ~15 more: the frozen harness's responder returns the fixed text `"warmup"` /
`"measured"` for every call regardless of the prompt, so no pinned expected answer can ever be
present in it, and every cell fails the gate.

The second gap: *"the gate must fall back to reasoning when content is empty"*. `transport.chat`
collects reasoning deltas into a local and drops them; the returned `Observation` (shape pinned
in `docs/interfaces.md`) carries `text` = content deltas only, and no structured failure reason.
A reasoning-only response reaches the call site as `ok=False, error="chat stream produced no
content", text=""` — the sample text does not exist there, and distinguishing "still thinking"
from "the server died" means matching that message string.

## Decisions needed

1. **May the probe be a request of its own?** If yes, `tests/test_measure.py` must change: three
   call-count/index assertions and the harness responder, which must answer the probe. That file
   is outside the three I was given. If no, the gate runs on the responses the visit already
   makes (row 4 wiring) and the "checkable answer" is only enforced when a run declares one —
   `cli.py`, which passes the workload, is also outside my three files.
2. **Reasoning text:** accept "no content" detection from the transport's empty-content failure
   (the gate already returns `NO_CONTENT` as its own reason, and the cell gets its own status,
   never `incoherent output`), or authorize carrying reasoning text on `Observation`.

## State of the tree

`ohyesmlx/measure.py` is untouched. `ohyesmlx/coherence.py` and `tests/test_coherence.py` are new
and green; nothing imports the gate yet.
