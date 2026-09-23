GOAL: Fix single-delta timing, add a timing-channel field, and add the transport tests that can actually fail (review items A2, A5-prep, E2, E3 in .paul/review/2026-09-23/SUMMARY.md).
FILES: ohyesmlx/transport.py, tests/test_transport.py. Touch nothing else.
ITEMS:
(A2) A content delta sets first_token and last_content from ONE `now = time.monotonic()` read, so a one-delta stream has last_content_s == ttft_s exactly (a zero window, never float noise). Same for reasoning deltas (already one read; keep it).
(A5-prep) Append one field to Observation, last, with a default: `timing_channel: str = "content"`. Set it to "reasoning" when the mirrored or reasoning-only branch chose the reasoning timings, "content" otherwise, and "content" on the failure path. Old records without the key must still load via Observation(**raw) (the default does this).
(E2) Let the test SSE server be configured to answer a given HTTP status (e.g. 401, 500) or a non-event-stream Content-Type (application/json); assert chat() returns ok=False with the exact existing error text for each.
(E3) A server that sends headers then stalls: chat(..., timeout_s=1.0) returns ok=False with "request timed out" within a few seconds.
CONSTRAINTS: The SSE loop's behaviour on real streams must not change otherwise (chunked decoding, [DONE], mirrored/reasoning-only selection, token accounting).
ACCEPTANCE: each new test red-checked (fails without its fix; report it). Suite green (baseline 497; report count). `git diff --stat` only the two files.
