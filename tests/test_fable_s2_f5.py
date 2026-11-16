"""Reproduction for Fable 5.2 S2-F5: a usage split is trusted against a stream that refutes it.

The claim: ``transport.chat`` takes the usage branch (``transport.py:445-466``) whenever
``usage.completion_tokens_details.reasoning_tokens`` is present, and the only sanity check
is ``visible_exact <= 0``. A runtime that streams non-mirrored reasoning deltas and then
content, while reporting ``reasoning_tokens: 0`` as a constant, has its whole
``completion_tokens`` published as visible content — divided by a window that covers only
the content deltas — labelled ``token_source: "usage"``. The ``reasoning_text`` the
function already holds (``transport.py:387``) is never consulted on that branch, even
though the local-counter path it skips demands the split sum exactly.

The stream here is the shape the finding names: two reasoning deltas, three content
deltas, a usage block that reports 500 completion tokens and zero reasoning tokens. Real
SSE over a real socket, via the same stdlib server ``tests/test_transport.py`` uses.
"""

from __future__ import annotations

import pytest

from ohyesmlx.transport import chat

from test_token_counter import FixedMapTokenCounter
from test_transport import (
    DONE,
    MESSAGES,
    SseServer,
    _content,
    _reasoning,
    _stop,
    _usage,
)


@pytest.fixture
def server():
    running = SseServer()
    try:
        yield running
    finally:
        running.stop()


def _a_non_mirrored_reasoning_stream(server) -> None:
    server.respond(
        (0.0, _reasoning("think ")),
        (0.0, _reasoning("think")),
        (0.0, _content("one ")),
        (0.0, _content("two ")),
        (0.0, _content("three")),
        (0.0, _stop()),
        (0.0, _usage(completion_tokens=500, reasoning_tokens=0)),
        (0.0, DONE),
    )


def test_zero_usage_reasoning_over_a_real_reasoning_stream_is_not_taken(server):
    """The stream refutes the usage block, and the usage branch runs anyway.

    The two channels differ, so this is not the oMLX mirror: 500 tokens landed in a stream
    the harness timed on its three content deltas. Publishing 500 as the visible content
    count is the 5x-inflated decode rate the finding describes, and nothing on the branch
    looks at the reasoning text that contradicts it.
    """
    _a_non_mirrored_reasoning_stream(server)

    observation = chat(server.base_url, "model", MESSAGES, max_tokens=512)

    assert observation.ok, observation.error
    # The scenario is the claimed one: a real reasoning channel, not a mirror, not
    # reasoning-only. The timing window covers content alone.
    assert observation.reasoning_text == "think think"
    assert observation.text == "one two three"
    assert observation.reasoning_text != observation.text
    assert observation.content_event_count == 3

    assert observation.token_source != "usage", (
        "the usage split was taken from a stream whose reasoning text refutes it, "
        f"publishing completion_tokens={observation.completion_tokens} "
        f"reasoning_tokens={observation.reasoning_tokens} labelled {observation.token_source!r}"
    )
    assert observation.completion_tokens != 500, (
        f"all 500 completion tokens published as visible content: "
        f"{observation.completion_tokens}"
    )


def test_a_reconciling_counter_does_not_stop_the_usage_branch_running_first(server):
    """Even a counter that can reconcile the total exactly is never asked.

    400 reasoning + 100 content tokens sum to the runtime's own total of 500, which is the
    check ``resolve_token_accounting`` makes (``token_counter.py:107-112``) and the usage
    branch does not: the branch runs first and skips the call.
    """
    _a_non_mirrored_reasoning_stream(server)

    observation = chat(
        server.base_url,
        "model",
        MESSAGES,
        max_tokens=512,
        token_counter=FixedMapTokenCounter(
            {"think think": 400, "one two three": 100}
        ),
    )

    assert observation.ok, observation.error
    assert observation.token_source != "usage", (
        f"the usage split was taken: completion_tokens={observation.completion_tokens}, "
        f"reasoning_tokens={observation.reasoning_tokens}, "
        f"token_source={observation.token_source!r}"
    )
    assert observation.completion_tokens != 500
