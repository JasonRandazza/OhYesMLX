GOAL: when a runtime mirrors its reasoning channel into content, the request's timing must come
from the channel that actually streamed. Today the harness reports a TTFT 8x too slow.

FILES YOU MAY EDIT: ohyesmlx/transport.py, tests/test_transport.py ONLY.

MEASURED, one oMLX 0.6.4 request, max_tokens=128, timed per channel:

    reasoning_content : 15 deltas, first 0.685s, last 2.352s, window 1.668s
    content           :  1 delta,  first 2.352s, last 2.352s, window 0.000s

oMLX streams incrementally in reasoning_content, then emits the ENTIRE completed text once more
as a single content delta at the end. transport pins ttft_s to the first CONTENT delta and
excludes reasoning (docs/interfaces.md), so it times the one channel carrying no timing. It
published TTFT 5.499s for a runtime whose real TTFT is 0.685s, and a decode window of 1.66e-07s
where the real window is 1.668s.

YOU ALREADY HAVE THE MIRROR TEST. `chat()` computes `accounting_reasoning_text` by comparing the
accumulated reasoning text against the accumulated content — that comparison already identifies
exactly this runtime. Reuse it; do not invent a second detector.

REQUIRED. When the accumulated reasoning text is identical to the accumulated content, the
reasoning deltas ARE this response's output stream. For that case only:
- ttft_s is the time of the FIRST reasoning delta.
- last_content_s is the time of the LAST reasoning delta.
- content_event_count is the number of REASONING deltas.
Every other case is untouched: a runtime that streams content normally keeps content timing, and
a runtime with a genuinely different reasoning channel keeps content timing.

You will need to record first/last timestamps and a count for reasoning deltas alongside the ones
already kept for content. The mirror is only detectable once both accumulations are complete, so
capture the reasoning timings unconditionally as the stream runs and choose between them at the
end. Keep the existing empty-content TransportError behaviour for a response that produced
neither channel.

WHY content_event_count MUST MOVE TOO: report.py omits decode tok/s, ITL and prefill tok/s when
content_event_count < 2. If the count stays 1 for a mirrored stream, the corrected timing is
computed and then discarded, and the bug survives the fix.

ACCEPTANCE: pytest -q green from a 239 baseline, no regressions. Tests must cover: a mirrored
stream takes ttft/last/count from the reasoning deltas, with the timing and the count all moving
together; a normal content-streaming response is byte-for-byte unchanged; a response whose
reasoning genuinely differs from its content keeps content timing; a mirrored stream with only
ONE reasoning delta still reports a count of 1 so report.py still omits its rates. Red-check it:
revert, watch the mirrored test fail with content timing, restore, report that you did.

Do not touch report.py, measure.py, coherence.py, runtimes.py, cli.py. Do not start a server.
