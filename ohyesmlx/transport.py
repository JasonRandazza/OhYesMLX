"""SSE measurement client for one local OpenAI-compatible endpoint.

Ported near-verbatim from LMRE's transport.py. Every line of the stream loop is a bug
someone already paid for, so nothing here is tidied up. Three things differ on purpose:
the loopback allowlist in ``_parts`` is now a plain ``http://127.0.0.1:<port>/v1`` check,
the return value is the frozen :class:`Observation`, and the caller's ``token_counter`` is
wired through instead of being accepted and ignored.

Streaming is always on internally with ``stream_options.include_usage``; the caller sees
only the timings and the token accounting.
"""

from __future__ import annotations

import http.client
import json
import select
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlparse

from .token_counter import TokenCounter, resolve_token_accounting

_TOKEN_SOURCES = {
    "EXACT_VISIBLE": "usage",
    "DERIVED_REASONING_CONTENT": "local_tokenizer",
    "INCOMPARABLE_TOKEN_ACCOUNTING": "none",
}


class TransportError(RuntimeError):
    code = "transport_failed"

    def __init__(
        self,
        message: str,
        *,
        reason: str = "transport_failed",
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.http_status = http_status


@dataclass(frozen=True)
class Observation:
    """One measured request."""

    ok: bool
    error: str | None
    ttft_s: float | None
    last_content_s: float | None
    total_s: float
    prompt_tokens: int | None
    completion_tokens: int | None
    reasoning_tokens: int | None
    content_event_count: int
    text: str
    token_source: str
    # Appended last, not slotted in beside ``text`` where docs/interfaces.md lists it: a
    # field with a default cannot precede one without, and the default is what lets the
    # failure path in measure.py build an Observation with no reasoning to report.
    reasoning_text: str = ""


def _parts(base_url: str) -> tuple[str, int, str]:
    normalized = base_url.rstrip("/")
    parsed = urlparse(normalized)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or not parsed.port
        or parsed.path != "/v1"
    ):
        raise TransportError(
            "endpoint must be http://127.0.0.1:<port>/v1",
            reason="endpoint_forbidden",
        )
    return parsed.hostname, parsed.port, parsed.path


def _connection(
    base_url: str, timeout_s: float
) -> tuple[http.client.HTTPConnection, str]:
    host, port, path = _parts(base_url)
    return http.client.HTTPConnection(host, port, timeout=timeout_s), path


def _call_before_deadline(
    call: Callable[[], object],
    connection: http.client.HTTPConnection,
    deadline: float,
) -> object:
    result: list[object] = []
    errors: list[BaseException] = []
    completed = threading.Event()

    def run() -> None:
        try:
            result.append(call())
        except BaseException as error:
            errors.append(error)
        finally:
            completed.set()

    threading.Thread(target=run, daemon=True).start()
    while not completed.wait(
        min(0.1, max(0.0, deadline - time.monotonic()))
    ):
        if time.monotonic() >= deadline:
            connection.close()
            raise TransportError("request timed out", reason="timeout")
    if time.monotonic() >= deadline:
        raise TransportError("request timed out", reason="timeout")
    if errors:
        raise errors[0]
    return result[0]


def _usage_count(value: object, message: str) -> int:
    """A usage counter: a non-negative int, or a refusal naming *message*."""
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TransportError(message, reason="invalid_token_accounting")
    return value


def chat(
    base_url: str,
    model: str,
    messages: list[dict],
    *,
    max_tokens: int,
    temperature: float = 0.0,
    seed: int | None = None,
    timeout_s: float = 600.0,
    api_key: str | None = None,
    token_counter: TokenCounter | None = None,
) -> Observation:
    connection: http.client.HTTPConnection | None = None
    started = time.monotonic()
    first_token: float | None = None
    content: list[str] = []
    reasoning_parts: list[str] = []
    content_event_count = 0
    last_content: float | None = None
    # Reasoning deltas are timed unconditionally. Whether they are this response's output
    # stream is only knowable once both accumulations are complete, and the timings have to
    # already exist by then.
    first_reasoning: float | None = None
    last_reasoning: float | None = None
    reasoning_event_count = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    reasoning_tokens: int | None = None
    usage_reasoning_tokens: int | None = None
    try:
        connection, path = _connection(base_url, timeout_s)
        body: dict[str, object] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if seed is not None:
            body["seed"] = seed
        payload = json.dumps(body).encode()
        deadline = started + timeout_s
        headers = {"Content-Type": "application/json"}
        if api_key:
            # oMLX answers an unauthenticated /v1/chat/completions with HTTP 401 and a run
            # that never sends this measures a server that loaded no weights at all.
            headers["Authorization"] = f"Bearer {api_key}"
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TransportError("request timed out", reason="timeout")
        connection.timeout = remaining
        _call_before_deadline(
            lambda: connection.request(
                "POST",
                f"{path}/chat/completions",
                body=payload,
                headers=headers,
            ),
            connection,
            deadline,
        )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TransportError("request timed out", reason="timeout")
        request_socket = getattr(connection, "sock", None)
        if request_socket is not None:
            request_socket.settimeout(remaining)
        response = _call_before_deadline(
            connection.getresponse, connection, deadline
        )
        if response.status != 200:
            _call_before_deadline(response.read, connection, deadline)
            raise TransportError(
                f"chat request returned HTTP {response.status}",
                reason="http_status",
                http_status=response.status,
            )
        if "text/event-stream" not in response.getheader(
            "Content-Type", ""
        ):
            raise TransportError(
                "chat response is not an SSE stream", reason="not_sse"
            )
        stream_socket = connection.sock
        if stream_socket is None:
            stream_socket = getattr(
                getattr(getattr(response, "fp", None), "raw", None),
                "_sock",
                None,
            )
        if stream_socket is None:
            raise TransportError(
                "chat stream failed", reason="stream_setup_failed"
            )
        # Prefer HTTPResponse.read1 so Transfer-Encoding: chunked
        # (Osaurus) is decoded. Reading response.fp raw exposes hex chunk
        # sizes as SSE lines.
        stream_reader = response
        pending = bytearray()
        stream_done = False
        # Never apply a short socket timeout to the stream makefile:
        # after a TimeoutError, Python's socket makefile permanently
        # raises OSError("cannot read from timed out object") on later
        # peeks/reads.
        # Wait with select() instead so OptiQ prompt-processing keepalives
        # that arrive >1s after headers do not abort the cohort.
        stream_socket.settimeout(None)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TransportError("request timed out", reason="timeout")
            try:
                readable, _, _ = select.select(
                    [stream_socket],
                    [],
                    [],
                    min(1.0, remaining),
                )
            except (ValueError, OSError):
                break
            if not readable:
                continue
            try:
                chunk = stream_reader.read1(4096)
            except (BlockingIOError, InterruptedError, TimeoutError):
                continue
            except http.client.IncompleteRead as error:
                chunk = error.partial or b""
                if not chunk:
                    break
            except OSError:
                break
            if not chunk:
                break
            pending.extend(chunk)
            while b"\n" in pending:
                newline = pending.index(b"\n")
                line = bytes(pending[:newline])
                del pending[: newline + 1]
                decoded = line.decode("utf-8")
                if decoded in ("", "\r") or decoded.startswith(":"):
                    continue
                if not decoded.startswith("data: "):
                    raise TransportError(
                        "unsupported SSE framing", reason="unsupported_sse"
                    )
                data = decoded[6:].rstrip()
                if data == "[DONE]":
                    stream_done = True
                    break
                event = json.loads(data)
                choices = event.get("choices", [])
                if choices:
                    delta_obj = choices[0].get("delta", {})
                    if not isinstance(delta_obj, dict):
                        delta_obj = {}
                    # mlx-lm 0.31.3 spells the reasoning channel `reasoning`; other servers
                    # spell it `reasoning_content`. Both are read, and a delta that carries
                    # both is counted once.
                    reasoning_delta = delta_obj.get("reasoning_content")
                    if not reasoning_delta:
                        reasoning_delta = delta_obj.get("reasoning")
                    if reasoning_delta:
                        reasoning_parts.append(str(reasoning_delta))
                        reasoning_event_count += 1
                        arrived = time.monotonic()
                        if first_reasoning is None:
                            first_reasoning = arrived
                        last_reasoning = arrived
                    delta = delta_obj.get("content")
                    if delta:
                        if first_token is None:
                            first_token = time.monotonic()
                        last_content = time.monotonic()
                        content_event_count += 1
                        content.append(str(delta))
                usage = event.get("usage")
                if isinstance(usage, dict):
                    prompt_value = usage.get("prompt_tokens")
                    if prompt_value is not None:
                        prompt_tokens = _usage_count(
                            prompt_value, "prompt-token accounting is invalid"
                        )
                    completion_value = usage.get("completion_tokens")
                    if completion_value is not None:
                        completion_tokens = _usage_count(
                            completion_value,
                            "completion-token accounting is invalid",
                        )
                    details = usage.get("completion_tokens_details")
                    if (
                        isinstance(details, dict)
                        and "reasoning_tokens" in details
                    ):
                        usage_reasoning_tokens = _usage_count(
                            details["reasoning_tokens"],
                            "reasoning-token accounting is invalid",
                        )
            if stream_done:
                break
        if not stream_done:
            raise TransportError(
                "incomplete SSE stream", reason="incomplete_sse"
            )
        ended = time.monotonic()
        joined = "".join(content)
        reasoning_text = "".join(reasoning_parts)
        # oMLX 0.6.4 mirrors its reasoning text into the content channel: the same string
        # arrives twice and the two accumulations come out identical. That is one stream
        # read twice, not two channels, so accounting sees an empty reasoning channel and
        # the visible count reconciles against usage.completion_tokens exactly as it does
        # when a runtime emits content alone. Comparing the accumulations is what holds when
        # the duplicate arrives non-adjacently or in chunks of a different size. The
        # duplicate itself stays in ``reasoning_text``: the record keeps what was sent.
        #
        # The same comparison answers the timing question, and it is the only detector: when
        # the two accumulations are identical it is the reasoning deltas that streamed, and
        # the content channel carries the finished text as one copy at the end. Timing the
        # copy measured the wrong channel — 5.499 s of TTFT where the first reasoning delta
        # landed at 0.685 s, and a 1.66e-07 s decode window against a real 1.668 s.
        mirrored = bool(reasoning_text) and reasoning_text == joined
        # mlx-lm 0.31.3 and vMLX 1.6.59 answer a thinking model entirely in the reasoning
        # channel and never reach content inside the workload's cap. The stream produced
        # output; it is spelled in the other channel. Timing only the content channel raised
        # empty_content over the top of a response that had just streamed, which is how 24 of
        # the grid's 60 results came back with no figure and no token count at all.
        reasoning_only = bool(reasoning_text) and not joined
        # The output stream, decided once for all three shapes: the content deltas, unless the
        # reasoning deltas are what streamed — because the runtime mirrored them into content,
        # or because no content ever arrived. The count moves with the timing, never without
        # it: report.py reads a count below two as a stream with no interval to divide by and
        # omits decode tok/s, ITL and prefill tok/s, so a corrected window under a count of one
        # is computed and then discarded. A stream of one reasoning delta still reports one —
        # it really did arrive whole — and still publishes no rate.
        if mirrored or reasoning_only:
            stream_ttft_s, stream_last_s, stream_events = (
                first_reasoning,
                last_reasoning,
                reasoning_event_count,
            )
        else:
            stream_ttft_s, stream_last_s, stream_events = (
                first_token,
                last_content,
                content_event_count,
            )
        # Neither channel produced anything, so there is no output stream to measure.
        if stream_ttft_s is None:
            raise TransportError(
                "chat stream produced no content", reason="empty_content"
            )
        if stream_last_s is None:
            raise TransportError(
                "chat stream content timing is unavailable",
                reason="content_timing_unavailable",
            )
        # A response that never reached content arrived in one channel, so there is no second
        # one to split it from and the runtime's own completion total is that channel's count.
        # Accounting is sent an empty reasoning channel and reads the total — the branch
        # resolve_token_accounting already takes when a runtime emits no reasoning at all,
        # reached from the other side. Mirrored text is the same case: one stream, read twice.
        accounting_reasoning_text = (
            "" if (mirrored or reasoning_only) else reasoning_text
        )
        if (
            usage_reasoning_tokens is not None
            and completion_tokens is not None
            # Not when reasoning is the only channel: the split the runtime reports is the
            # whole response, and the visible remainder of zero is not a count this response
            # has.
            and not reasoning_only
        ):
            if usage_reasoning_tokens > completion_tokens:
                raise TransportError(
                    "reasoning tokens exceed total completion tokens",
                    reason="invalid_token_accounting",
                )
            visible_exact = completion_tokens - usage_reasoning_tokens
            if visible_exact <= 0:
                raise TransportError(
                    "visible output token count is invalid",
                    reason="invalid_token_accounting",
                )
            reasoning_tokens = usage_reasoning_tokens
            content_tokens = visible_exact
            token_source = "usage"
        else:
            _, content_tokens, accounting_status = resolve_token_accounting(
                reasoning_text=accounting_reasoning_text,
                visible_text=joined,
                completion_tokens=completion_tokens,
                token_counter=token_counter,
            )
            token_source = _TOKEN_SOURCES[accounting_status]
        return Observation(
            ok=True,
            error=None,
            ttft_s=stream_ttft_s - started,
            last_content_s=stream_last_s - started,
            total_s=ended - started,
            prompt_tokens=prompt_tokens,
            completion_tokens=content_tokens,
            reasoning_tokens=reasoning_tokens,
            content_event_count=stream_events,
            text=joined,
            reasoning_text=reasoning_text,
            token_source=token_source,
        )
    except TransportError as error:
        failure_message = str(error)
    except TimeoutError:
        failure_message = "request timed out"
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
    ):
        failure_message = "chat stream failed"
    finally:
        if connection is not None:
            connection.close()
    return Observation(
        ok=False,
        error=failure_message,
        ttft_s=None if first_token is None else first_token - started,
        last_content_s=None if last_content is None else last_content - started,
        total_s=time.monotonic() - started,
        prompt_tokens=None,
        completion_tokens=None,
        reasoning_tokens=None,
        content_event_count=content_event_count,
        text="".join(content),
        reasoning_text="".join(reasoning_parts),
        token_source="none",
    )
