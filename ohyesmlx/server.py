"""The app's read-only localhost API: three GET endpoints behind a per-launch token.

Seam S6, plan 04-01. The SwiftUI app (Phase 5) is a client of this server and nothing else,
so this module is the contract -- and it holds no rule a module already defines. ``/hardware``
is ``hardware.scan``, ``/engines`` is ``detect_all`` with ``engines.install_plan`` composed in,
``/recommendations`` is ``recommend.pick`` plus ``recommend.exclusion_reason``; a fit rule or a
version comparison written here would be a second copy of one that lives in its module.

Any page the user opens can send requests to 127.0.0.1, so every request passes one guard
before the router sees it: the ``Host`` must name this server, an ``Origin`` header is refused
outright, and ``Authorization: Bearer <token>`` must carry the token ``make_server`` generated
and the CLI printed once. The token is the control that matters, because a cross-site ``<img>``
or a top-level navigation carries no ``Origin`` and a correct ``Host``; the other two are
defence in depth. The guard answers in a fixed order with fixed messages, so no refusal can
echo a header value or the token back to its caller.

The response bodies are the shapes pinned in ``docs/interfaces.md`` (v5.0), serialised with
``dataclasses.asdict``: this module composes, it does not translate.
"""

from __future__ import annotations

import dataclasses
import hmac
import json
import secrets
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ohyesmlx import catalog, engines, hardware, recommend

# The only address this server ever binds: never 0.0.0.0 and never ::, so nothing off this
# machine can reach it and a page's DNS-rebinding request arrives with a foreign Host the guard
# can refuse.
HOST = "127.0.0.1"

# AC-8: a client that opens a connection and then says nothing -- or dribbles headers -- holds
# its thread until this elapses, and the base class turns the timeout into a closed connection.
HANDLER_TIMEOUT_S = 10.0

# The three paths that answer, and the handler each one runs. Anything else is 404, whatever
# the method -- and this mapping is the only place the set is written down.
_ENDPOINTS = {
    "/hardware": "_get_hardware",
    "/engines": "_get_engines",
    "/recommendations": "_get_recommendations",
}

# The pinned codes with their statuses (docs/interfaces.md, v5.0, **Errors**). The message is
# fixed per code, so a refusal can never echo a header value or the token; ``internal`` and
# ``install_plan_failed`` carry the exception's message instead, and no exception this module
# raises on its own path includes request data.
_ERRORS = {
    "bad_host": (403, "the Host header must be 127.0.0.1:<port> or localhost:<port>"),
    "origin_refused": (403, "a request carrying an Origin header is refused"),
    "unauthorized": (401, "a valid Authorization: Bearer token is required"),
    "not_found": (404, "no such path"),
    "method_not_allowed": (405, "only GET is served on this path"),
    "internal": (500, None),
    "install_plan_failed": (500, None),
}


def _log_refusal(code: str, method: str, path: str) -> None:
    """One JSON line per refusal, so a probe from a page leaves a trace and nothing else does.

    The fields are the code, the method, the path and the time -- never a header value and
    never the token, so the app can surface the line without handling a secret. The query
    string is dropped with the path it arrived on: it is client text, and a caller that pasted
    the token into it would otherwise write the token to stderr.
    """
    print(
        json.dumps(
            {
                "refused": code,
                "method": method,
                "path": path,
                "time": datetime.now(timezone.utc).isoformat(),
            }
        ),
        file=sys.stderr,
        flush=True,
    )


class _Handler(BaseHTTPRequestHandler):
    """The request handler: one guard, three endpoints, and no other response shape.

    ``self.server`` is the object :func:`make_server` built, carrying the injected ``scan``,
    ``detect`` and ``load_catalog`` seams and the launch ``token``. ``timeout`` is overridden
    per server by the factory, so the test that proves a stalled connection is dropped does not
    wait the production ten seconds.
    """

    # HTTP/1.0 is the base class's default and is load-bearing here: it is what closes the
    # connection after each response, so one request is one connection (AC-8) and a client
    # cannot hold a keep-alive slot open with a half-sent request.
    protocol_version = "HTTP/1.0"

    timeout = HANDLER_TIMEOUT_S

    # --- logging: silenced -----------------------------------------------------------------

    def log_message(self, format: str, *args) -> None:
        """Silence the access log: a served request writes nothing, and refusals write below."""
        pass

    # --- the guard -------------------------------------------------------------------------

    def do_GET(self) -> None:
        self._guarded("GET")

    def do_HEAD(self) -> None:
        self._guarded("HEAD")

    def do_POST(self) -> None:
        self._guarded("POST")

    def do_PUT(self) -> None:
        self._guarded("PUT")

    def do_DELETE(self) -> None:
        self._guarded("DELETE")

    def do_PATCH(self) -> None:
        self._guarded("PATCH")

    def do_OPTIONS(self) -> None:
        self._guarded("OPTIONS")

    def _guarded(self, method: str) -> None:
        """Run the guard first, and let the router see the request only if it passed."""
        if self._guard():
            self._route(method)

    def _guard(self) -> bool:
        """Host, then Origin, then token -- AC-2's order; False means a refusal was written.

        The Host and Origin checks are exact matches on what this server answers to, never a
        substring and never a port-less host, and an absent Host is refused: the app's client
        always sends one, and a request without one is not from the app. The token is compared
        as UTF-8 bytes so a header value that is not ASCII is an ordinary failed comparison
        rather than the ``TypeError`` ``hmac.compare_digest`` raises on non-ASCII ``str``.
        """
        port = self.server.server_address[1]
        if self.headers.get("Host") not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            return self._refuse("bad_host")
        if self.headers.get("Origin") is not None:
            return self._refuse("origin_refused")
        given = self.headers.get("Authorization") or ""
        expected = f"Bearer {self.server.token}"
        if not hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8")):
            return self._refuse("unauthorized")
        return True

    def _refuse(self, code: str) -> bool:
        """Write the refusal and its one stderr line, and answer False to stop the caller."""
        _log_refusal(code, self.command, self._path())
        self._respond(code)
        return False

    # --- the router ------------------------------------------------------------------------

    def _path(self) -> str:
        """The request path without its query: a query value is client text, never logged."""
        return self.path.partition("?")[0]

    def _route(self, method: str) -> None:
        """404 for an unknown path, 405 for a non-GET on one of the three, else the endpoint.

        The path is resolved before the method: there is nothing at an unknown path to be
        method-not-allowed about, so a POST to one is a 404, while a POST to ``/hardware`` is
        the 405 AC-6 names. A module that raises is a 500 carrying its message and no
        traceback, which is the one diagnostic the app needs and nothing more.
        """
        endpoint = _ENDPOINTS.get(self._path())
        if endpoint is None:
            self._respond("not_found")
            return
        if method != "GET":
            self._respond("method_not_allowed")
            return
        try:
            getattr(self, endpoint)()
        except Exception as error:  # a module raised; its message is the whole report
            self._respond("internal", str(error))

    # --- the endpoints ---------------------------------------------------------------------

    def _get_hardware(self) -> None:
        """The ``Hardware`` shape, byte counts as JSON integers -- ``asdict`` adds no floats."""
        self._write_json(200, dataclasses.asdict(self.server.scan()))

    def _get_engines(self) -> None:
        """``detect_all`` with the install plan composed in, and null for an engine already here.

        ``macos_major`` is the integer before the first dot of ``Hardware.macos``, because the
        plan an engine needs differs by macOS generation. A plan that cannot be derived is a
        500 naming the engine: a silent null would report an engine as having nothing to
        install.
        """
        macos_major = int(self.server.scan().macos.split(".", 1)[0])
        statuses = []
        for status in self.server.detect():
            entry = dataclasses.asdict(status)
            entry["install"] = None
            if not status.installed:
                try:
                    entry["install"] = dataclasses.asdict(
                        engines.install_plan(status.name, macos_major)
                    )
                except ValueError as error:
                    self._respond("install_plan_failed", f"{status.name}: {error}")
                    return
            statuses.append(entry)
        self._write_json(200, statuses)

    def _get_recommendations(self) -> None:
        """``pick`` and ``exclusion_reason`` over the scan, the detections and the catalog.

        The free disk is ``Hardware.disk_free_bytes``, the same number ``/hardware`` reports.
        On an unsupported Mac both lists are empty and ``unsupported_reason`` carries the one
        sentence: a per-model exclusion there would be a copy of a reason that belongs to the
        Mac, not to the model.
        """
        hw = self.server.scan()
        statuses = self.server.detect()
        models = self.server.load_catalog()
        picks = [
            dataclasses.asdict(pick)
            for pick in recommend.pick(hw, models, statuses, hw.disk_free_bytes)
        ]
        excluded = []
        if hw.supported:
            for model in models:
                reason = recommend.exclusion_reason(model, hw, hw.disk_free_bytes)
                if reason is not None:
                    excluded.append({"model_id": model.repo, "reason": reason})
        self._write_json(
            200,
            {
                "picks": picks,
                "excluded": excluded,
                "unsupported_reason": hw.unsupported_reason,
            },
        )

    # --- one response builder ---------------------------------------------------------------

    def _respond(self, code: str, message: str | None = None) -> None:
        """Write the pinned error shape from the code table, so status and code cannot disagree.

        ``status`` repeats the HTTP status in the body because a person reading a refusal in a
        browser sees the body, not the status line; both come from the one table entry.
        """
        status, fixed = _ERRORS[code]
        self._write_json(
            status,
            {
                "error": {
                    "code": code,
                    "status": status,
                    "message": fixed if message is None else message,
                }
            },
        )

    def _write_json(self, status: int, payload) -> None:
        """Every response this server writes: UTF-8 JSON, never cached, never CORS-enabled."""
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def make_server(
    port: int = 0,
    *,
    scan=hardware.scan,
    detect=engines.detect_all,
    load_catalog=catalog.load,
    token: str | None = None,
    timeout: float = HANDLER_TIMEOUT_S,
) -> ThreadingHTTPServer:
    """The listening server on 127.0.0.1:*port*, already accepting connections.

    The three module seams default to the real functions, so the CLI passes none of them and a
    test passes fakes. *token* is generated fresh with ``secrets.token_urlsafe(32)`` when the
    caller has none, and it lives only on this object and in the one line the CLI prints -- no
    file, no log, no argv. *timeout* bounds each connection and is short only in the test that
    proves it.

    The socket is bound and listening before this returns, so a client may connect the moment
    it has read the announced line; a bind that fails raises ``OSError`` to the caller, which is
    where the exit code 2 and the stderr line belong.
    """
    handler = type("_TimedHandler", (_Handler,), {"timeout": timeout})
    listener = ThreadingHTTPServer((HOST, port), handler)
    # ThreadingHTTPServer sets this already; it is the server's stated contract (AC-8), not an
    # accident of the stdlib, so a shutdown never waits on a handler thread.
    listener.daemon_threads = True
    listener.scan = scan
    listener.detect = detect
    listener.load_catalog = load_catalog
    listener.token = token if token is not None else secrets.token_urlsafe(32)
    return listener
