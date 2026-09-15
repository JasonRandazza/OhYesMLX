GOAL: a runtime that emits no reasoning channel must publish tok/s. Today it cannot, because
the harness demands a reconciliation that is impossible in principle.

FILES YOU MAY EDIT: ohyesmlx/token_counter.py, tests/test_token_counter.py (create it if
absent). Nothing else.

THE EVIDENCE, measured on this machine today. oMLX 0.6.4 served 5 requests, all coherent,
all with an empty reasoning channel after dedupe. Every one published nothing:

    local re-count of decoded text: 257
    server usage.completion_tokens: 256   (finish_reason was "length", max_tokens=256)
    resolve_token_accounting(reasoning_text="", visible_text=<text>,
                             completion_tokens=256, usage_reasoning_tokens=None,
                             token_counter=<real>) -> (None, None, 'INCOMPARABLE_TOKEN_ACCOUNTING')

Re-tokenizing decoded text is not the inverse of generation. A response truncated at
max_tokens re-tokenizes across different boundaries, so the counts differ by one or two. The
requirement of exact equality is therefore unsatisfiable for any truncated response, and
v1's headline metric is unreachable for every runtime that does not report a
reasoning/content split.

THE FIX — and read the reasoning, because it is the point of the change. The local counter
exists to SPLIT a combined stream into reasoning tokens and content tokens. The
reconciliation against usage.completion_tokens exists to validate that DERIVED SPLIT. When
reasoning_text is empty there is no split to derive and nothing to validate: the server's
completion_tokens IS the content token count, by definition, exactly as it is in the
usage_reasoning_tokens branch above it.

So: in resolve_token_accounting, when usage_reasoning_tokens is None, reasoning_text is empty
or whitespace, and completion_tokens is not None — return (0, completion_tokens, "EXACT_VISIBLE")
without consulting the token counter at all.

THIS IS NOT A TOLERANCE AND YOU MUST NOT ADD ONE. Do not compare with a fuzz factor, a
percentage, or a "close enough" window anywhere. Every path where a split IS derived keeps
exact reconciliation unchanged. You are removing a check that had nothing to validate, not
loosening one that did.

ALSO: transport.py maps the status string to Observation.token_source via _TOKEN_SOURCES. Do
not edit transport.py. If "EXACT_VISIBLE" is not already a key in that mapping, say so
clearly in your report and stop rather than editing outside your files — the coordinator will
handle it.

ACCEPTANCE: pytest -q green from a 222 baseline, no regressions. Tests must cover: empty
reasoning + completion_tokens returns completion_tokens exactly and never calls the counter
(prove it with a counter that raises if called); whitespace-only reasoning is treated as
empty; a genuinely non-empty reasoning channel still reconciles exactly and still returns
INCOMPARABLE_TOKEN_ACCOUNTING when the sum disagrees; completion_tokens=None with empty
reasoning is unchanged. Red-check it: revert your change, watch the new tests fail with
"INCOMPARABLE_TOKEN_ACCOUNTING", restore, and report that you did.
