"""Checks for ohyesmlx.transport against a real SSE server.

The server is a stdlib ``http.server`` writing real SSE bytes over a real socket: real
``Content-Length`` framing, real ``Transfer-Encoding: chunked`` framing, real gaps
between chunks. Nothing here is mocked and no live model runtime is started — none is
needed, because the four stream shapes that matter (chunked, reasoning-then-content, a
first chunk more than a second after the headers, and a stream that just stops) are all
reproducible with stdlib alone.
"""

from __future__ import annotations

import dataclasses
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from ohyesmlx.transport import Observation, chat, timing_channel
from test_token_counter import FixedMapTokenCounter

MESSAGES = [{"role": "user", "content": "hi"}]
DONE = b"data: [DONE]\n\n"
# Captured verbatim from oMLX 0.6.4: one request at max_tokens=8, eight tokens generated,
# and the same eight-token string arriving twice — once as reasoning_content, then again in
# content. The harness counted both copies and could publish no tok/s figure for oMLX.
OMLX_MIRRORED = "\nThinking Process:\n\n1.  **"


class SseHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    framing = "content-length"
    events: list[tuple[float, bytes]] = []
    pre_body_delay_s = 0.0
    status = 200
    content_type = "text/event-stream"
    stall_after_headers_s = 0.0
    chunk_bytes = 24
    posted: list[dict] = []
    authorization: list[str | None] = []

    def log_message(self, *args: object) -> None:
        return

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        SseHandler.posted.append(json.loads(self.rfile.read(length)))
        SseHandler.authorization.append(self.headers.get("Authorization"))
        chunked = SseHandler.framing == "chunked"
        self.send_response(SseHandler.status)
        self.send_header("Content-Type", SseHandler.content_type)
        if chunked:
            self.send_header("Transfer-Encoding", "chunked")
        else:
            self.send_header(
                "Content-Length",
                str(sum(len(piece) for _, piece in SseHandler.events)),
            )
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        # Headers are already on the wire here: the delay below is a gap between
        # the response headers and the first byte of the body, which is what
        # OptiQ's prompt-processing keepalives look like.
        if SseHandler.stall_after_headers_s:
            time.sleep(SseHandler.stall_after_headers_s)
        if SseHandler.pre_body_delay_s:
            time.sleep(SseHandler.pre_body_delay_s)
        for delay, piece in SseHandler.events:
            if delay:
                time.sleep(delay)
            self.wfile.write(
                _chunked(piece, SseHandler.chunk_bytes) if chunked else piece
            )
            self.wfile.flush()
        if chunked:
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()


class SseServer:
    """A real HTTP server that answers one POST with one SSE stream."""

    def __init__(self) -> None:
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), SseHandler)
        self.port = self._httpd.server_port
        self.base_url = f"http://127.0.0.1:{self.port}/v1"
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, daemon=True
        )
        self._thread.start()

    def respond(
        self,
        *events: tuple[float, bytes],
        framing: str = "content-length",
        pre_body_delay_s: float = 0.0,
        status: int = 200,
        content_type: str = "text/event-stream",
        stall_after_headers_s: float = 0.0,
    ) -> None:
        """Queue one stream. Each event's delay is slept before that event is written, so
        the delays are cumulative: ``(0.0, a), (0.2, b)`` writes ``b`` 0.2s after ``a``."""
        SseHandler.events = list(events)
        SseHandler.framing = framing
        SseHandler.pre_body_delay_s = pre_body_delay_s
        SseHandler.status = status
        SseHandler.content_type = content_type
        SseHandler.stall_after_headers_s = stall_after_headers_s
        SseHandler.posted = []
        SseHandler.authorization = []

    def posted(self) -> dict:
        return SseHandler.posted[-1]

    def authorization(self) -> str | None:
        """The Authorization header the last POST carried, or ``None`` if it carried none."""
        return SseHandler.authorization[-1]

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=5)


@pytest.fixture
def server():
    running = SseServer()
    try:
        yield running
    finally:
        running.stop()


def _chunked(payload: bytes, size: int) -> bytes:
    parts: list[bytes] = []
    for offset in range(0, len(payload), size):
        piece = payload[offset : offset + size]
        parts.append(f"{len(piece):x}\r\n".encode() + piece + b"\r\n")
    return b"".join(parts)


def _sse(payload: dict) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode()


def _content(text: str) -> bytes:
    return _sse({"choices": [{"delta": {"content": text}, "finish_reason": None}]})


def _reasoning(text: str, field: str = "reasoning_content") -> bytes:
    return _sse(
        {"choices": [{"delta": {field: text}, "finish_reason": None}]}
    )


def _stop() -> bytes:
    return _sse({"choices": [{"delta": {}, "finish_reason": "stop"}]})


def _usage(
    *,
    prompt_tokens: int = 7,
    completion_tokens: int | None = None,
    reasoning_tokens: int | None = None,
) -> bytes:
    usage: dict[str, object] = {"prompt_tokens": prompt_tokens}
    if completion_tokens is not None:
        usage["completion_tokens"] = completion_tokens
    if reasoning_tokens is not None:
        usage["completion_tokens_details"] = {"reasoning_tokens": reasoning_tokens}
    return _sse({"choices": [], "usage": usage})


def _without_clocks(observation: Observation) -> Observation:
    """An observation with its three wall-clock fields blanked.

    Only the machine knows when the deltas landed, so a field-for-field pin compares every
    field but those three.
    """
    return dataclasses.replace(
        observation, ttft_s=None, last_content_s=None, total_s=0.0
    )


def test_chunked_transfer_encoding_stream_is_decoded(server):
    """Osaurus answers with Transfer-Encoding: chunked. Hex sizes are not SSE."""
    server.respond(
        (0.0, _content("hello")),
        (0.0, _content(" world")),
        (0.0, _stop()),
        (0.0, _usage(completion_tokens=2, reasoning_tokens=0)),
        (0.0, DONE),
        framing="chunked",
    )

    observation = chat(server.base_url, "model", MESSAGES, max_tokens=16)

    assert observation.ok, observation.error
    assert observation.text == "hello world"
    assert observation.content_event_count == 2
    assert observation.prompt_tokens == 7
    assert observation.completion_tokens == 2
    assert observation.reasoning_tokens == 0
    assert observation.token_source == "usage"
    assert observation.ttft_s is not None
    assert observation.last_content_s >= observation.ttft_s
    assert observation.total_s >= observation.last_content_s


def test_ttft_ignores_reasoning_deltas_and_counts_content_only(server):
    server.respond(
        (0.0, _reasoning("think hard")),
        (0.4, _content("ok")),
        (0.0, _stop()),
        (0.0, _usage(completion_tokens=5, reasoning_tokens=3)),
        (0.0, DONE),
    )

    observation = chat(server.base_url, "model", MESSAGES, max_tokens=16)

    assert observation.ok, observation.error
    assert observation.text == "ok"
    assert observation.content_event_count == 1
    # TTFT is time to first CONTENT token: the reasoning delta landed 0.4s earlier
    # and must not have started the clock.
    assert observation.ttft_s >= 0.35
    assert observation.last_content_s >= observation.ttft_s
    assert observation.reasoning_tokens == 3
    assert observation.completion_tokens == 2
    assert observation.token_source == "usage"


def test_reasoning_deltas_spelled_reasoning_are_captured(server):
    """mlx-lm 0.31.3 emits delta.reasoning. Matching only reasoning_content dropped them."""
    server.respond(
        (0.0, _reasoning("ext", field="reasoning")),
        (0.0, _reasoning("ultip", field="reasoning")),
        (0.0, _content("ok")),
        (0.0, _stop()),
        (0.0, _usage(completion_tokens=5, reasoning_tokens=2)),
        (0.0, DONE),
    )

    observation = chat(server.base_url, "model", MESSAGES, max_tokens=16)

    assert observation.ok, observation.error
    assert observation.reasoning_text == "extultip"
    assert observation.text == "ok"
    # Captured, never folded into the visible output or its timing.
    assert observation.content_event_count == 1


def test_reasoning_text_joins_both_spellings_in_one_stream(server):
    server.respond(
        (0.0, _reasoning("think ")),
        (0.0, _reasoning("again", field="reasoning")),
        (0.0, _content("ok")),
        (0.0, _stop()),
        (0.0, DONE),
    )

    observation = chat(server.base_url, "model", MESSAGES, max_tokens=16)

    assert observation.ok, observation.error
    assert observation.reasoning_text == "think again"
    assert observation.text == "ok"


def test_a_delta_carrying_both_spellings_is_counted_once(server):
    server.respond(
        (
            0.0,
            _sse(
                {
                    "choices": [
                        {
                            "delta": {"reasoning_content": "think", "reasoning": "think"},
                            "finish_reason": None,
                        }
                    ]
                }
            ),
        ),
        (0.0, _content("ok")),
        (0.0, _stop()),
        (0.0, DONE),
    )

    observation = chat(server.base_url, "model", MESSAGES, max_tokens=16)

    assert observation.ok, observation.error
    assert observation.reasoning_text == "think"


def test_reasoning_text_is_empty_when_the_model_emits_none(server):
    server.respond(
        (0.0, _content("ok")),
        (0.0, _stop()),
        (0.0, _usage(completion_tokens=2, reasoning_tokens=0)),
        (0.0, DONE),
    )

    observation = chat(server.base_url, "model", MESSAGES, max_tokens=16)

    assert observation.ok, observation.error
    assert observation.reasoning_text == ""


def test_reasoning_text_is_defaulted_so_an_observation_can_omit_it():
    """measure.py's failure path builds an Observation with no reasoning to report."""
    observation = Observation(
        ok=False,
        error="chat stream failed",
        ttft_s=None,
        last_content_s=None,
        total_s=0.1,
        prompt_tokens=None,
        completion_tokens=None,
        reasoning_tokens=None,
        content_event_count=0,
        text="",
        token_source="none",
    )

    assert observation.reasoning_text == ""


def test_reasoning_text_survives_an_incomplete_stream(server):
    server.respond((0.0, _reasoning("ext", field="reasoning")), (0.0, _stop()))

    observation = chat(server.base_url, "model", MESSAGES, max_tokens=16)

    assert observation.ok is False
    assert observation.error == "incomplete SSE stream"
    assert observation.reasoning_text == "ext"


def test_first_chunk_more_than_a_second_after_headers_is_survived(server):
    server.respond(
        (0.0, b": keepalive 1/1\n\n"),
        (0.0, _content("late")),
        (0.0, _stop()),
        (0.0, DONE),
        pre_body_delay_s=1.2,
    )

    started = time.monotonic()
    observation = chat(server.base_url, "model", MESSAGES, max_tokens=16)

    assert observation.ok, observation.error
    assert observation.text == "late"
    assert time.monotonic() - started >= 1.2


def test_token_source_is_local_tokenizer_when_usage_cannot_split_reasoning(server):
    server.respond(
        (0.0, _reasoning("think hard")),
        (0.0, _content("ok")),
        (0.0, _stop()),
        (0.0, _usage(completion_tokens=5)),
        (0.0, DONE),
    )

    observation = chat(
        server.base_url,
        "model",
        MESSAGES,
        max_tokens=16,
        token_counter=FixedMapTokenCounter({"think hard": 3, "ok": 2}),
    )

    assert observation.ok, observation.error
    assert observation.token_source == "local_tokenizer"
    assert observation.completion_tokens == 2
    assert observation.reasoning_tokens is None


def test_token_source_is_none_without_a_counter(server):
    server.respond(
        (0.0, _reasoning("think hard")),
        (0.0, _content("ok")),
        (0.0, _stop()),
        (0.0, _usage(completion_tokens=5)),
        (0.0, DONE),
    )

    observation = chat(server.base_url, "model", MESSAGES, max_tokens=16)

    assert observation.ok, observation.error
    assert observation.token_source == "none"
    assert observation.completion_tokens is None
    assert observation.reasoning_tokens is None


def test_token_source_is_none_when_the_local_count_contradicts_usage(server):
    server.respond(
        (0.0, _reasoning("think")),
        (0.0, _content("ok")),
        (0.0, _stop()),
        (0.0, _usage(completion_tokens=9)),
        (0.0, DONE),
    )

    observation = chat(
        server.base_url,
        "model",
        MESSAGES,
        max_tokens=16,
        token_counter=FixedMapTokenCounter({"think": 3, "ok": 2}),
    )

    assert observation.ok, observation.error
    assert observation.token_source == "none"
    assert observation.completion_tokens is None


def test_a_mirrored_reasoning_stream_reconciles_against_usage(server):
    """The oMLX capture: the same string in both channels is one stream, counted once.

    Eight tokens were generated and usage says eight. Counting the reasoning copy and the
    content copy gave sixteen, and resolve_token_accounting rejected 8 != 16, which is why
    no decode tok/s figure could be published for oMLX.
    """
    server.respond(
        (0.0, _reasoning(OMLX_MIRRORED)),
        (0.0, _content(OMLX_MIRRORED)),
        (0.0, _stop()),
        (0.0, _usage(prompt_tokens=13, completion_tokens=8)),
        (0.0, DONE),
    )

    observation = chat(
        server.base_url,
        "model",
        MESSAGES,
        max_tokens=8,
        token_counter=FixedMapTokenCounter({OMLX_MIRRORED: 8}),
    )

    assert observation.ok, observation.error
    assert observation.prompt_tokens == 13
    assert observation.completion_tokens == 8
    # "usage", not "local_tokenizer": the duplicate is dropped before accounting, so there
    # is no split left to derive and the count comes straight from the runtime's own total.
    assert observation.token_source == "usage"
    # The runtime did send a reasoning channel, so the record still carries it; only the
    # accounting drops the duplicate.
    assert observation.reasoning_text == OMLX_MIRRORED
    assert observation.text == OMLX_MIRRORED
    assert observation.content_event_count == 1


def test_a_mirrored_stream_is_caught_across_unequal_non_adjacent_chunks(server):
    """The comparison is over the accumulations, not over any two deltas."""
    server.respond(
        (0.0, _reasoning("\nThinking ")),
        (0.0, _content("\nThinking ")),
        (0.0, _reasoning("Process:\n\n1.  **")),
        (0.0, _content("Process:")),
        (0.0, _content("\n\n1.  **")),
        (0.0, _stop()),
        (0.0, _usage(prompt_tokens=13, completion_tokens=8)),
        (0.0, DONE),
    )

    observation = chat(
        server.base_url,
        "model",
        MESSAGES,
        max_tokens=8,
        token_counter=FixedMapTokenCounter({OMLX_MIRRORED: 8}),
    )

    assert observation.ok, observation.error
    assert observation.token_source == "usage"
    assert observation.completion_tokens == 8
    assert observation.reasoning_text == OMLX_MIRRORED
    assert observation.text == OMLX_MIRRORED
    # Two reasoning deltas, not the three content ones: the reasoning channel is the stream
    # that carried the output, and the content copy of it is not a second one.
    assert observation.content_event_count == 2


def test_a_mirrored_stream_is_timed_from_the_reasoning_deltas(server):
    """The oMLX shape: the output streams in reasoning and arrives again, whole, in content.

    Timing the content copy measured the duplicate — 5.499 s of TTFT where the first
    reasoning delta landed at 0.685 s, and a decode window of 1.66e-07 s where the
    generation ran for 1.668 s.

    The keepalive goes first so the deltas are clocked as they are written: a body byte that
    lands in the same read as the response headers is not seen until the next write. Delays
    are cumulative, so this stream writes reasoning at 0.2 s and 0.6 s and the content copy
    of the same text at 1.2 s.
    """
    server.respond(
        (0.0, b": keepalive 1/1\n\n"),
        (0.2, _reasoning("\nThinking ")),
        (0.4, _reasoning("Process:\n\n1.  **")),
        (0.6, _content(OMLX_MIRRORED)),
        (0.0, _stop()),
        (0.0, _usage(prompt_tokens=13, completion_tokens=8)),
        (0.0, DONE),
    )

    observation = chat(server.base_url, "model", MESSAGES, max_tokens=8)

    assert observation.ok, observation.error
    assert observation.reasoning_text == OMLX_MIRRORED
    assert observation.text == OMLX_MIRRORED
    assert observation.token_source == "usage"
    # Every published metric's inputs are now present: a window from the reasoning deltas, a
    # count of two, usage prompt tokens and the runtime's own content token count.
    assert observation.completion_tokens == 8
    # The clock starts at the first reasoning delta, 0.2s in. Content timing would put it at
    # the copy, 1.2s in.
    assert observation.ttft_s < 0.45
    # And it stops at the last reasoning delta, 0.6s in: a window of the 0.4s the generation
    # actually took, not the float noise between two timestamps on one copy.
    assert observation.last_content_s - observation.ttft_s >= 0.3
    assert observation.last_content_s < 1.0
    # Timing and count move together. report.py omits decode tok/s, ITL and prefill tok/s
    # below two deltas, so the corrected window under the content channel's count of one
    # would be computed and then discarded, and the bug would survive its own fix.
    assert observation.content_event_count == 2


def test_a_content_streaming_response_keeps_its_own_timing(server):
    """No reasoning channel: every field is what the content deltas measured, as before."""
    server.respond(
        (0.0, b": keepalive 1/1\n\n"),
        (0.2, _content("hello")),
        (0.4, _content(" world")),
        (0.0, _stop()),
        (0.0, _usage(completion_tokens=2, reasoning_tokens=0)),
        (0.0, DONE),
    )

    observation = chat(server.base_url, "model", MESSAGES, max_tokens=16)

    assert observation.ok, observation.error
    assert observation.reasoning_text == ""
    assert observation.text == "hello world"
    # Content deltas at 0.2s and 0.6s: the timing and the count are the content channel's own.
    assert observation.ttft_s < 0.45
    assert observation.last_content_s >= 0.55
    assert observation.last_content_s - observation.ttft_s >= 0.3
    assert observation.content_event_count == 2
    assert observation.reasoning_tokens == 0


def test_a_mirrored_stream_of_one_reasoning_delta_still_reports_a_count_of_one(server):
    """One delta is the whole response, so report.py must still omit that cell's rates."""
    server.respond(
        (0.0, b": keepalive 1/1\n\n"),
        (0.2, _reasoning(OMLX_MIRRORED)),
        (0.4, _content(OMLX_MIRRORED)),
        (0.0, _stop()),
        (0.0, _usage(prompt_tokens=13, completion_tokens=8)),
        (0.0, DONE),
    )

    observation = chat(server.base_url, "model", MESSAGES, max_tokens=8)

    assert observation.ok, observation.error
    assert observation.content_event_count == 1
    # The timing still moved off the content copy: the one reasoning delta at 0.2s is when
    # the response was written, and the copy at 0.6s is not.
    assert observation.ttft_s < 0.45
    assert observation.last_content_s < 0.45


def test_a_mirrored_stream_is_unchanged_field_for_field(server):
    """The mirrored path, pinned whole: the fix below must not have moved a single field."""
    server.respond(
        (0.0, _reasoning(OMLX_MIRRORED)),
        (0.0, _content(OMLX_MIRRORED)),
        (0.0, _stop()),
        (0.0, _usage(prompt_tokens=13, completion_tokens=8)),
        (0.0, DONE),
    )

    observation = chat(server.base_url, "model", MESSAGES, max_tokens=8)

    assert _without_clocks(observation) == Observation(
        ok=True,
        error=None,
        ttft_s=None,
        last_content_s=None,
        total_s=0.0,
        prompt_tokens=13,
        completion_tokens=8,
        reasoning_tokens=None,
        content_event_count=1,
        text=OMLX_MIRRORED,
        token_source="usage",
        reasoning_text=OMLX_MIRRORED,
    )


def test_an_ordinary_content_stream_is_unchanged_field_for_field(server):
    """The ordinary path, pinned whole, split accounting included."""
    server.respond(
        (0.0, _content("hello")),
        (0.0, _content(" world")),
        (0.0, _stop()),
        (0.0, _usage(prompt_tokens=7, completion_tokens=5, reasoning_tokens=2)),
        (0.0, DONE),
    )

    observation = chat(server.base_url, "model", MESSAGES, max_tokens=16)

    assert _without_clocks(observation) == Observation(
        ok=True,
        error=None,
        ttft_s=None,
        last_content_s=None,
        total_s=0.0,
        prompt_tokens=7,
        completion_tokens=3,
        reasoning_tokens=2,
        content_event_count=2,
        text="hello world",
        token_source="usage",
        reasoning_text="",
    )


def test_a_reasoning_only_stream_times_and_counts_its_reasoning_deltas(server):
    """mlx-lm 0.31.3 and vMLX 1.6.59: the whole response streams in `delta.reasoning`.

    Twenty-four of the grid's sixty results carried no figure for this. `chat` saw no content
    delta, raised empty_content over a response that had just streamed, and the cell was
    excluded for a decode window the reasoning channel had already produced.
    """
    server.respond(
        (0.0, b": keepalive 1/1\n\n"),
        (0.2, _reasoning("thinking ", field="reasoning")),
        (0.4, _reasoning("out loud", field="reasoning")),
        (0.0, _stop()),
        (0.0, _usage(prompt_tokens=13, completion_tokens=8)),
        (0.0, DONE),
    )

    observation = chat(server.base_url, "model", MESSAGES, max_tokens=128)

    assert observation.ok, observation.error
    # The output stream is the reasoning channel: deltas at 0.2s and 0.6s are the window, and
    # its count of two is what report.py needs before it will publish a rate from it.
    assert observation.ttft_s < 0.45
    assert observation.last_content_s - observation.ttft_s >= 0.3
    assert observation.last_content_s < 1.0
    assert observation.content_event_count == 2
    # Content stayed content and reasoning stayed reasoning. The gate reads text first and
    # falls back to reasoning_text, so the two channels have to arrive intact.
    assert observation.text == ""
    assert observation.reasoning_text == "thinking out loud"
    # Reasoning is the only channel, so there is no split to derive and usage's own completion
    # total is that channel's count — the rule the mirrored case already follows.
    assert observation.completion_tokens == 8
    assert observation.token_source == "usage"


def test_a_reasoning_only_stream_takes_the_total_when_usage_reports_the_split(server):
    """A runtime that reports reasoning_tokens and still never reaches content.

    The split it reports is the whole response, so there is no visible remainder to require
    and usage's total is the count of the one channel that produced output.
    """
    server.respond(
        (0.0, _reasoning("thinking", field="reasoning")),
        (0.0, _reasoning(" out loud", field="reasoning")),
        (0.0, _stop()),
        (0.0, _usage(completion_tokens=6, reasoning_tokens=6)),
        (0.0, DONE),
    )

    observation = chat(server.base_url, "model", MESSAGES, max_tokens=128)

    assert observation.ok, observation.error
    assert observation.completion_tokens == 6
    assert observation.token_source == "usage"


def test_a_stream_with_neither_channel_still_raises_empty_content(server):
    """Nothing in content and nothing in reasoning: no output stream to measure."""
    server.respond(
        (0.0, _stop()),
        (0.0, _usage(completion_tokens=0)),
        (0.0, DONE),
    )

    observation = chat(server.base_url, "model", MESSAGES, max_tokens=128)

    assert observation.ok is False
    assert observation.error == "chat stream produced no content"
    assert observation.text == ""
    assert observation.reasoning_text == ""


def test_a_reasoning_channel_that_differs_from_content_keeps_content_timing(server):
    """A real second channel is not a mirror, and its timing is not the output's."""
    server.respond(
        (0.0, b": keepalive 1/1\n\n"),
        (0.2, _reasoning("think")),
        (0.4, _content("ok")),
        (0.0, _stop()),
        (0.0, _usage(completion_tokens=7)),
        (0.0, DONE),
    )

    observation = chat(server.base_url, "model", MESSAGES, max_tokens=16)

    assert observation.ok, observation.error
    assert observation.reasoning_text == "think"
    assert observation.text == "ok"
    # The content delta at 0.6s is the first output event; the reasoning delta 0.4s earlier
    # is a different channel and is not part of the response's timing.
    assert observation.ttft_s >= 0.55
    assert observation.content_event_count == 1


def test_a_reasoning_channel_that_differs_from_content_is_still_counted(server):
    """Deduplication is equality, not containment: a real second channel survives it."""
    server.respond(
        (0.0, _reasoning("think")),
        (0.0, _content("think harder")),
        (0.0, _stop()),
        (0.0, _usage(completion_tokens=7)),
        (0.0, DONE),
    )

    observation = chat(
        server.base_url,
        "model",
        MESSAGES,
        max_tokens=16,
        token_counter=FixedMapTokenCounter({"think": 2, "think harder": 5}),
    )

    assert observation.ok, observation.error
    assert observation.token_source == "local_tokenizer"
    assert observation.completion_tokens == 5
    assert observation.reasoning_text == "think"
    assert observation.text == "think harder"


def test_usage_is_requested_and_the_sampling_constants_are_pinned(server):
    server.respond((0.0, _content("ok")), (0.0, DONE))

    observation = chat(
        server.base_url,
        "model",
        MESSAGES,
        max_tokens=32,
        temperature=0.0,
        seed=1234,
    )

    assert observation.ok, observation.error
    assert server.posted() == {
        "model": "model",
        "messages": MESSAGES,
        "temperature": 0.0,
        "max_tokens": 32,
        "stream": True,
        "stream_options": {"include_usage": True},
        "seed": 1234,
    }


def test_seed_is_omitted_when_the_runtime_is_not_asked_to_pin_one(server):
    server.respond((0.0, _content("ok")), (0.0, DONE))

    chat(server.base_url, "model", MESSAGES, max_tokens=32)

    assert "seed" not in server.posted()


def test_api_key_is_sent_as_a_bearer_token(server):
    """oMLX answers an unauthenticated measured request with HTTP 401."""
    server.respond((0.0, _content("ok")), (0.0, _stop()), (0.0, DONE))

    observation = chat(
        server.base_url,
        "model",
        MESSAGES,
        max_tokens=16,
        api_key="ohyesmlx-local",
    )

    assert observation.ok, observation.error
    assert server.authorization() == "Bearer ohyesmlx-local"


def test_no_authorization_header_without_an_api_key(server):
    server.respond((0.0, _content("ok")), (0.0, _stop()), (0.0, DONE))

    observation = chat(server.base_url, "model", MESSAGES, max_tokens=16)

    assert observation.ok, observation.error
    assert server.authorization() is None


def test_endpoint_must_be_loopback_v1(server):
    off_host = chat(
        "http://example.com:8100/v1", "model", MESSAGES, max_tokens=16
    )
    assert off_host.ok is False
    assert off_host.error == "endpoint must be http://127.0.0.1:<port>/v1"
    assert off_host.token_source == "none"

    off_path = chat(
        f"http://127.0.0.1:{server.port}/other", "model", MESSAGES, max_tokens=16
    )
    assert off_path.ok is False
    assert off_path.error == "endpoint must be http://127.0.0.1:<port>/v1"


def test_incomplete_stream_is_reported_rather_than_raised(server):
    server.respond((0.0, _content("reply")), (0.0, _stop()))

    observation = chat(server.base_url, "model", MESSAGES, max_tokens=16)

    assert observation.ok is False
    assert observation.error == "incomplete SSE stream"
    assert observation.text == "reply"
    assert observation.content_event_count == 1


def test_reasoning_tokens_above_the_completion_total_is_an_error(server):
    server.respond(
        (0.0, _content("ok")),
        (0.0, _stop()),
        (0.0, _usage(completion_tokens=2, reasoning_tokens=5)),
        (0.0, DONE),
    )

    observation = chat(server.base_url, "model", MESSAGES, max_tokens=16)

    assert observation.ok is False
    assert observation.error == "reasoning tokens exceed total completion tokens"


def test_truncated_sse_line_is_a_framing_error(server):
    server.respond(
        (0.0, b'event: content\ndata: {"choices": []}\n\ndata: [DONE]\n\n')
    )

    observation = chat(server.base_url, "model", MESSAGES, max_tokens=16)

    assert observation.ok is False
    assert observation.error == "unsupported SSE framing"


def test_one_content_delta_has_an_exact_zero_timing_window(server):
    server.respond((0.0, _content("whole reply")), (0.0, _stop()), (0.0, DONE))

    observation = chat(server.base_url, "model", MESSAGES, max_tokens=16)

    assert observation.ok, observation.error
    assert observation.last_content_s == observation.ttft_s
    assert timing_channel(observation) == "content"


@pytest.mark.parametrize(
    ("events", "expected_channel"),
    [
        (
            [
                (0.0, _reasoning(OMLX_MIRRORED)),
                (0.0, _content(OMLX_MIRRORED)),
                (0.0, _stop()),
                (0.0, DONE),
            ],
            "reasoning",
        ),
        (
            [(0.0, _reasoning("reasoning only")), (0.0, _stop()), (0.0, DONE)],
            "reasoning",
        ),
        ([(0.0, _content("content")), (0.0, _stop()), (0.0, DONE)], "content"),
    ],
)
def test_observation_labels_the_channel_that_supplied_timings(
    server, events, expected_channel
):
    server.respond(*events)

    observation = chat(server.base_url, "model", MESSAGES, max_tokens=16)

    assert observation.ok, observation.error
    assert timing_channel(observation) == expected_channel


def test_timing_channel_is_derived_so_old_records_answer_too():
    """No stored field: a record written before 2026-09-23 has the same two texts."""
    def obs(text, reasoning):
        return Observation(ok=True, error=None, ttft_s=0.1, last_content_s=0.2, total_s=0.3,
                           prompt_tokens=1, completion_tokens=2, reasoning_tokens=None,
                           content_event_count=2, text=text, token_source="usage",
                           reasoning_text=reasoning)

    assert timing_channel(obs("answer", "")) == "content"
    assert timing_channel(obs("answer", "thinking")) == "content"
    assert timing_channel(obs("", "thinking")) == "reasoning"       # reasoning-only
    assert timing_channel(obs("mirror", "mirror")) == "reasoning"   # oMLX mirroring
    assert "timing_channel" not in {f.name for f in dataclasses.fields(Observation)}


@pytest.mark.parametrize(
    ("status", "content_type", "expected_error"),
    [
        (401, "text/event-stream", "chat request returned HTTP 401"),
        (500, "text/event-stream", "chat request returned HTTP 500"),
        (200, "application/json", "chat response is not an SSE stream"),
    ],
)
def test_http_status_and_content_type_errors_are_reported(
    server, status, content_type, expected_error
):
    server.respond(
        status=status,
        content_type=content_type,
    )

    observation = chat(server.base_url, "model", MESSAGES, max_tokens=16)

    assert observation.ok is False
    assert observation.error == expected_error


def test_headers_then_stall_respects_request_deadline(server):
    server.respond(stall_after_headers_s=2.0)

    started = time.monotonic()
    observation = chat(
        server.base_url, "model", MESSAGES, max_tokens=16, timeout_s=1.0
    )

    assert observation.ok is False
    assert observation.error == "request timed out"
    assert time.monotonic() - started < 3.0
