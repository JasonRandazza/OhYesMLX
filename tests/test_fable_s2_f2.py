"""S2-F2: an SSE chunk already in the reader is invisible until the socket sees more bytes.

``transport.chat`` reads the body with ``HTTPResponse.read1`` over ``http.client``'s
8 KiB ``BufferedReader`` but waits on ``select()`` of the raw socket between reads.  A
``readline`` inside ``read1`` fills that buffer with everything the kernel held, and
``read1`` then returns one HTTP chunk of it.  The rest sits in user space, where
``select`` cannot see it, so the loop waits for bytes that have already arrived.

Each test sends the bytes of a complete chunked SSE response over a real socket, and the
server's writes are the only variable: closing, holding the connection open, or arriving
in one burst. Three probes of the same defect, one per shape it takes.
"""

from __future__ import annotations

import json
import socket
import threading
import time

from ohyesmlx.transport import chat

MESSAGES = [{"role": "user", "content": "hi"}]

HEADERS = (
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Type: text/event-stream\r\n"
    b"Transfer-Encoding: chunked\r\n"
    b"\r\n"
)


def _sse(payload: dict) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode()


def _content(text: str) -> bytes:
    return _sse({"choices": [{"delta": {"content": text}, "finish_reason": None}]})


STOP = _sse({"choices": [{"delta": {}, "finish_reason": "stop"}]})
USAGE = _sse({"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 3}})
DONE = b"data: [DONE]\n\n"
EVENTS = (_content("a"), _content("b"), _content("c"), STOP, USAGE, DONE)


def _chunk(payload: bytes) -> bytes:
    return f"{len(payload):x}\r\n".encode() + payload + b"\r\n"


def _response(*events: bytes) -> bytes:
    """A complete chunked SSE response, small enough to arrive in one segment."""
    return HEADERS + b"".join(_chunk(event) for event in events) + b"0\r\n\r\n"


class _OneShot:
    """Answers one POST, then closes at a chosen moment.

    ``writes`` is a list of ``(delay_s, bytes)`` written in order after the request has
    been read; ``close_after_s=None`` holds the connection open until :meth:`stop`.
    """

    def __init__(
        self,
        writes: list[tuple[float, bytes]],
        *,
        close_after_s: float | None,
    ) -> None:
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(1)
        self.port = self._listener.getsockname()[1]
        self.base_url = f"http://127.0.0.1:{self.port}/v1"
        self._writes = writes
        self._close_after_s = close_after_s
        self._release = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        try:
            connection, _ = self._listener.accept()
        except OSError:
            return
        with connection:
            request = b""
            while b"\r\n\r\n" not in request:
                piece = connection.recv(4096)
                if not piece:
                    return
                request += piece
            for delay, payload in self._writes:
                if delay:
                    time.sleep(delay)
                connection.sendall(payload)
            if self._close_after_s is None:
                self._release.wait(timeout=30.0)
            else:
                time.sleep(self._close_after_s)

    def stop(self) -> None:
        self._release.set()
        self._listener.close()
        self._thread.join(timeout=5)


def _run(writes, *, close_after_s, timeout_s=3.0):
    server = _OneShot(writes, close_after_s=close_after_s)
    try:
        started = time.monotonic()
        observation = chat(
            server.base_url, "model", MESSAGES, max_tokens=16, timeout_s=timeout_s
        )
        elapsed = time.monotonic() - started
    finally:
        server.stop()
    return observation, elapsed


def test_control_the_same_bytes_on_a_closing_connection_are_read_promptly():
    """Proves the framing is valid and the reader walks a buffered stream once the socket
    is permanently readable (EOF), so the failures below are the wait, not the bytes."""
    observation, elapsed = _run(
        [(0.0, _response(*EVENTS))], close_after_s=0.0
    )

    assert observation.ok, observation.error
    assert elapsed < 1.0


def test_a_whole_response_arriving_in_one_write_is_read_without_waiting_for_more_bytes():
    observation, elapsed = _run(
        [(0.0, _response(*EVENTS))], close_after_s=None
    )

    assert observation.ok, (
        f"error={observation.error!r} after {elapsed:.2f}s; every chunk of this "
        "response was in the client's BufferedReader before the wait"
    )
    assert elapsed < 2.0, (
        f"took {elapsed:.2f}s of a 3.0s deadline; the loop waited on select() with "
        "the stream already in user space"
    )


def test_a_delta_already_buffered_is_stamped_when_the_next_bytes_arrive():
    """Headers alone, then the rest of the stream in one write, then silence for 0.5 s.

    Both content deltas arrived together, but the reader returns one HTTP chunk per
    wake-up, so the second is stamped when the close finally makes the socket readable
    again: the decode window measures the gap between writes, not between tokens.
    """
    observation, _ = _run(
        [
            (0.0, HEADERS),
            (0.05, _chunk(_content("a")) + _chunk(_content("b"))
                   + _chunk(STOP) + _chunk(USAGE) + _chunk(DONE) + b"0\r\n\r\n"),
        ],
        close_after_s=0.5,
    )

    assert observation.ok, observation.error
    assert observation.text == "ab"
    window = observation.last_content_s - observation.ttft_s
    assert window < 0.25, (
        f"the two deltas arrived in one write but are {window:.2f}s apart; the second "
        "was stamped on the close, not on arrival"
    )
