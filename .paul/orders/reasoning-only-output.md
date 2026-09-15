GOAL: a runtime that answers entirely in the reasoning channel must be measurable. Two of five
runtimes in the grid produce no figures at all, 24 of 60 results, for this one reason.

FILES YOU MAY EDIT: ohyesmlx/transport.py, ohyesmlx/report.py, tests/test_transport.py,
tests/test_report.py.

## FIX 1 — the reasoning channel is the output stream when there is no content

MEASURED, the real grid run just completed. Every mlx-lm 0.31.3 row and every vMLX 1.6.59 row:

    FAIL | excluded by metrics; no content-delta timing, so decode tok/s is undefined

Both runtimes emit ONLY `delta.reasoning` for a thinking model and never reach content within
128, 64 or 512 tokens. `chat()` sees `first_token is None` and raises
TransportError("chat stream produced no content", reason="empty_content"), so the observation
comes back ok=False with no timing and no token count.

transport ALREADY has the right idea for the MIRRORED case: when the accumulated reasoning text
equals the accumulated content, the reasoning deltas are treated as the output stream for
ttft_s, last_content_s and content_event_count. That is correct and stays. It simply stops one
case short: mirrored requires `reasoning == content`, and here content is EMPTY, so it does not
apply.

REQUIRED: when a response produced NO content deltas but DID produce reasoning deltas, the
reasoning deltas are the output stream. Specifically:
- Do not raise empty_content. The stream produced output; it is in the other channel.
- ttft_s = first reasoning delta, last_content_s = last reasoning delta,
  content_event_count = number of reasoning deltas.
- Token accounting: there is no split to derive, because reasoning is the ONLY channel. So
  usage.completion_tokens IS that channel's count — the same reasoning the existing
  empty-reasoning branch in resolve_token_accounting uses, mirrored. Do NOT add a tolerance and
  do NOT re-count locally to reconcile.
- `text` stays content-only, `reasoning_text` keeps the reasoning. The coherence gate already
  reads text first and falls back to reasoning_text, so it needs no change — confirm that and
  say so, do not edit measure.py or coherence.py.
- A response with NEITHER channel still raises empty_content exactly as today. That is the
  genuinely-empty case and measure reports it as STILL_THINKING.

Prefer ONE notion of "the output stream" that covers mirrored, reasoning-only and ordinary
content, rather than three branches — but only if that lands cleanly. If unifying them makes
the code harder to read than three explicit cases, keep them explicit and say why.

## FIX 2 — the deferred-load note does not fire on the case it was built for

`DEFERRED_LOAD_FACTOR = 5.0` compares first_request_s against the median measured request. That
ratio is workload-dependent while the deferral is not, so it misses the real case:

    oMLX, 16-token probe requests : first 3.93 vs median 0.42  = 9.4x  -> would fire
    oMLX, 128-token grid requests : first 5.23 vs median ~1.6  = 3.3x  -> did NOT fire

Same runtime, same ~3.5 s deferred load, different verdict purely because the measured requests
got longer. Key off the ABSOLUTE EXCESS — `first_request_s - median measured` — not the ratio.

The four columns just measured, cold_load_s / first_request_s / approx median measured:

    mlxlm   3.84 / 1.61 / ~1.8   excess negative      honest
    omlx    2.16 / 5.23 / ~1.6   excess ~+3.6 s       DEFERRED, must fire
    optiq   4.11 / 2.06 / ~1.85  excess ~+0.2 s       honest
    vmlx    7.10 / 1.81 / ~1.9   excess negative      honest

Choose the threshold from those two populations, name it as a constant, and justify the number
in your report the way the 5.0 factor was justified. Keep printing both numbers in the note so
a reader can argue with the threshold rather than the finding. Delete DEFERRED_LOAD_FACTOR if
it is now unused — do not leave a dead constant.

## ACCEPTANCE

pytest -q green from a 319 baseline, no regressions. Tests must cover: a reasoning-only stream
yields ttft/last/count from its reasoning deltas and a token count from usage; a stream with
neither channel still raises empty_content; an ordinary content stream is byte-for-byte
unchanged; the mirrored case is unchanged; the deferred-load note fires on the oMLX numbers
above and not on the other three. Red-check both fixes and report that you did.

Do not touch measure.py, runtimes.py, coherence.py, token_counter.py, cli.py. Do not start a
server or load a model.
