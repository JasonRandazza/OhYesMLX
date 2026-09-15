GOAL: a rate the stream cannot support must be omitted with a reason, never computed. The
harness just published 1,532,954,517 tok/s and called the cell PASS.

FILES YOU MAY EDIT: ohyesmlx/report.py, tests/test_report.py ONLY.

WHAT HAPPENED, measured today. oMLX 0.6.4 accepts "stream": true, returns SSE framing, and
then delivers the ENTIRE completion in ONE content delta. All five measured observations:

    events=1  ctok=256  ttft=5.3532  last_content=5.3532  window=1.66e-07
    events=1  ctok=256  ttft=5.1823  last_content=5.1823  window=2.08e-07
    events=1  ctok=256  ttft=5.4986  last_content=5.4986  window=1.67e-07
    events=1  ctok=256  ttft=5.9044  last_content=5.9044  window=8.40e-08
    events=1  ctok=256  ttft=6.5838  last_content=6.5838  window=1.67e-07

decode tok/s is completion_tokens / (last_content_s - ttft_s). With one delta those two
timestamps are the same instant and the window is float noise, so 256 / 1.7e-07 published
1.5 billion tok/s, ITL published 0.0000, and the cell passed.

THREE THINGS TO FIX.

1. decode tok/s and ITL require at least TWO content deltas. With fewer there is no
   inter-token interval in the stream and the rate is undefined, not large. Omit both,
   exactly the way p90/p99 are already omitted below five samples, and say why in the row's
   notes. Follow that existing pattern rather than inventing a second one — read how the
   sample-count omission is worded and matched.

2. TTFT IS NOT COMPARABLE when content_event_count == 1. It is not time-to-first-token; it
   is time-to-entire-completion, because the first content delta IS the whole response. The
   row must say so. A reader comparing oMLX's 5.5 s against a token-streaming runtime's
   real TTFT would conclude oMLX has terrible latency, when the two numbers measure
   different things. Do NOT suppress the TTFT value - label it.

3. aggregate tok/s stays. It is every completion token over the wall time the measured
   requests took, it needs no per-delta timing, and at 44.9 tok/s it is the only honest rate
   this stream supports.

DO NOT change the cell's PASS/FAIL status. This is not a coherence failure and not a
transport failure: the runtime served the model correctly and the text was language. An
undefined metric is omitted and explained, the way a missing percentile already is. Do not
add a tolerance, a floor, or an epsilon to the window; do not compute a rate from a window
you have to guard against zero.

ACCEPTANCE: pytest -q green from a 232 baseline, no regressions. Tests must cover: a
one-delta cell omits decode tok/s and ITL, keeps aggregate tok/s, keeps its TTFT value, and
its notes say both why the rates are gone and that TTFT is time-to-completion; a normal
multi-delta cell is completely unchanged; a two-delta cell computes a rate as it does today,
so the boundary is exercised and not merely asserted. Red-check it: revert your change,
watch the new tests fail with the absurd rate present, restore, and report that you did.
