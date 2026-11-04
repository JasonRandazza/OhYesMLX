"""The app's localhost API: four read-only GETs and the job routes, behind a per-launch token.

Seam S6, plans 04-01, 04-02 and 04-03b. The SwiftUI app (Phase 5) is a client of this server and
nothing else, so this module is the contract -- and it holds no rule a module already defines.
``/hardware`` is ``hardware.scan``, ``/engines`` is ``detect_all`` with ``engines.install_plan``
composed in, ``/recommendations`` is ``recommend.pick`` plus ``recommend.exclusion_reason`` (and
``Pick.measured_here`` from ``quickbench.latest``), and ``/quickbench/plan`` is
``quickbench.plan``; a fit rule or a version comparison written here would be a second copy of
one that lives in its module.

``POST /jobs`` is the first surface that changes this Mac, and it carries a NAME, a literal
``true`` and -- for quickbench -- one boolean of consent, and nothing else: no path, no URL, no
command, no version. The module it calls owns the
allowlist, the consent gate, the lock and the rollback, so an unknown name or a low disk is that
module's own refusal, delivered on the job's event stream -- never a rule invented here.

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
import re
import secrets
import sys
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ohyesmlx import catalog, engines, fetch, hardware, quickbench, recommend

# The only address this server ever binds: never 0.0.0.0 and never ::, so nothing off this
# machine can reach it and a page's DNS-rebinding request arrives with a foreign Host the guard
# can refuse.
HOST = "127.0.0.1"

# AC-8 of 04-01: a client that opens a connection and then says nothing -- or dribbles headers --
# holds its thread until this elapses, and the base class turns the timeout into a closed
# connection. It stays set on a job stream too, where it bounds each WRITE: a client that stops
# reading is released at the first blocked send instead of holding a handler thread forever.
HANDLER_TIMEOUT_S = 10.0

# AC-4: while a job is quiet the stream writes this comment every 15 s. The wait is on the job's
# condition, never on the socket, so the interval is a comment and not a read timeout.
KEEPALIVE_S = 15.0

# AC-4: a job keeps at most this many events. The terminal error and done are stored inside the
# cap, so a job that overflows is ended at exactly the cap.
MAX_EVENTS = 10_000

# AC-1: the largest job body this server reads, checked from the header before the read.
MAX_BODY_BYTES = 4_096

# AC-6: shutdown cancels a running install or download and waits at most this long for it.
JOB_SHUTDOWN_WAIT_S = 120.0

# AC-3: one handler thread per connection, from accept to close, and no more than this many at
# once. A local account opening connections cannot grow the thread count without bound; a
# connection past the cap is closed before a thread exists for it.
MAX_HANDLER_THREADS = 32

# AC-3: one job may have at most this many event streams open at once, so four clients cannot
# each hold a handler thread on the same job; the fifth is refused rather than queued.
MAX_STREAMS_PER_JOB = 4

# The paths that answer, and the handler each one runs. Anything else is 404, whatever the
# method -- and this mapping is the only place the set is written down.
_ENDPOINTS = {
    "/hardware": "_get_hardware",
    "/engines": "_get_engines",
    "/recommendations": "_get_recommendations",
    "/quickbench/plan": "_get_quickbench_plan",
}

# AC-1: the closed set of args per kind, as the one name key; ``confirmed`` is the other key and
# must be JSON true. No kind has a key that names a path, a URL, a command or a version.
_JOB_ARGS = {
    "install": "engine",
    "download": "repo",
    "evict": "repo",
    "quickbench": "repo",
}

# The one kind that also takes a boolean the client states: whether the user allowed Osaurus's
# host settings to be pinned for the run and restored afterwards (AC-3).
_JOB_FLAGS = {"quickbench": ("osaurus",)}

# The only pattern a job path takes: the 16-hex id and one of the two actions. A job with no
# action is nothing this server serves, and a path that does not match is 404.
_JOB_PATH = re.compile(r"/jobs/([0-9a-f]{16})(/events|/cancel)?")

# The pinned codes with their statuses (docs/interfaces.md, v5.0, **Errors**). The message is
# fixed per code, so a refusal can never echo a header value or the token; ``internal``,
# ``install_plan_failed`` and ``bad_args`` carry a message instead, and no exception this module
# raises on its own path includes request data (``bad_args`` names a JSON key, never a value).
_ERRORS = {
    "bad_host": (403, "the Host header must be 127.0.0.1:<port> or localhost:<port>"),
    "origin_refused": (403, "a request carrying an Origin header is refused"),
    "unauthorized": (401, "a valid Authorization: Bearer token is required"),
    "not_found": (404, "no such path"),
    "method_not_allowed": (405, "the method is not served on this path"),
    "internal": (500, None),
    "install_plan_failed": (500, None),
    "bad_kind": (400, "kind must be install, download, evict or quickbench"),
    "bad_args": (400, None),
    "bad_json": (400, "the body is not valid JSON"),
    "unsupported_media_type": (415, "the body must be application/json"),
    "body_too_large": (413, "Content-Length must be an integer no greater than 4096"),
    "busy": (409, "another job is already running"),
    "unknown_job": (404, "no such job"),
    "bad_event_id": (400, "Last-Event-ID must be a non-negative integer"),
    "too_many_streams": (429, "a job has at most four event streams"),
    "not_cancellable": (409, "an evict job cannot be cancelled"),
    "job_finished": (409, "the job has already finished"),
}


def _event(kind: str, message: str, payload: dict | None) -> dict:
    """One server-authored event in the pinned shape; ``_Job._store`` assigns its seq."""
    return engines._job_event(0, kind, message, None, payload)


class _Job:
    """One accepted job: its id, its events, the condition they arrive on, and its cancel flag.

    ``append`` is the module's ``emit``. It is the only writer, it assigns the job's own ``seq``
    (the stream's event id), and it stores ``done`` last: the moment that event is stored the
    registry's one slot is freed (AC-3), so a job's outcome and its slot cannot disagree.
    """

    def __init__(self, registry: "_Jobs", job_id: str, kind: str, name: str, args=None):
        self.id = job_id
        self.kind = kind
        self.name = name
        # The validated closed set this job was accepted with. The streams pass ``name`` on,
        # and quickbench's ``osaurus`` consent is the one other value a module is handed.
        self.args = dict(args or {})
        self.events: list[dict] = []
        self.condition = threading.Condition()
        self.done = False
        self.cancel_requested = False
        self.streams = 0
        self._registry = registry

    def append(self, event: dict) -> None:
        """Store one module event and wake the stream; end the job at the cap or on ``done``."""
        terminal = False
        with self.condition:
            if self.done:
                return
            if event.get("type") == "done":
                self._store(event)
                terminal = True
            elif len(self.events) >= MAX_EVENTS - 2:
                self.cancel_requested = True
                self._store(
                    _event(
                        "error",
                        "the job produced too many events; it was ended",
                        {"code": "too_many_events"},
                    )
                )
                self._store(_event("done", "job ended at the event cap", None))
                terminal = True
            else:
                self._store(event)
            if terminal:
                self.done = True
            self.condition.notify_all()
        if terminal:
            self._registry.finished(self)

    def _store(self, event: dict) -> None:
        stored = dict(event)
        stored["seq"] = len(self.events) + 1
        self.events.append(stored)

    def cancelled(self) -> bool:
        """The callable a module probes; True from the moment ``POST /jobs/{id}/cancel`` lands."""
        return self.cancel_requested

    def open_stream(self) -> bool:
        """Take one of the job's stream slots, or False when all of them are held (AC-3)."""
        with self.condition:
            if self.streams >= MAX_STREAMS_PER_JOB:
                return False
            self.streams += 1
            return True

    def close_stream(self) -> None:
        """Give a stream slot back, however that stream ended."""
        with self.condition:
            self.streams -= 1


class _Jobs:
    """Every job this process has accepted, and the one running slot, under one lock (AC-3)."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.running: _Job | None = None
        self.jobs: dict[str, _Job] = {}

    def get(self, job_id: str) -> _Job | None:
        with self.lock:
            return self.jobs.get(job_id)

    def claim(self, job: _Job) -> _Job | None:
        """Take the slot for *job*, or return the job already holding it."""
        with self.lock:
            if self.running is not None:
                return self.running
            self.running = job
            self.jobs[job.id] = job
            return None

    def finished(self, job: _Job) -> None:
        with self.lock:
            if self.running is job:
                self.running = None

    def cancel_and_wait(self, timeout: float) -> None:
        """Cancel a running install, download or quickbench, wait, and give up after *timeout*.

        An evict has no cancel flag and is only waited for: it is a handful of unlinks and
        interrupting it would leave a ledger that disagrees with the disk. A quickbench run
        has one and notices it between cells, where its own eviction and Osaurus restore
        still run. AC-6: the wait is a bound, not a promise -- a pip step can outlive it, and
        docs/interfaces.md says so.
        """
        with self.lock:
            job = self.running
        if job is None:
            return
        if job.kind in ("install", "download", "quickbench"):
            job.cancel_requested = True
        deadline = time.monotonic() + timeout
        with job.condition:
            while not job.done:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                job.condition.wait(remaining)


def _job_code(job: _Job) -> str | None:
    """The code of the last error event stored, or null: what a job's end line reports."""
    for event in reversed(job.events):
        if event.get("type") == "error":
            return (event.get("payload") or {}).get("code")
    return None


def _args_problem(args, name_key: str, *, flags=()) -> str | None:
    """The first reason *args* is not the closed set for its kind, naming the key; else None.

    Names, versions, paths and disk numbers are not checked here: a string that is not an
    engine or a catalog repo is the module's own refusal (``unknown_engine``, ``unknown_repo``),
    delivered on the job's stream. ``confirmed`` must be JSON ``true`` -- not ``"true"``, not 1
    -- because it is the client's statement that a user chose this action (docs/interfaces.md).
    *flags* are the booleans a kind also takes (quickbench's ``osaurus``); each is required and
    must be a JSON bool, for the same reason ``confirmed`` is: it records a choice.
    """
    if not isinstance(args, dict):
        return "args must be an object"
    extra = sorted(set(args) - {name_key, "confirmed", *flags})
    if extra:
        return f"unexpected key {extra[0]}"
    missing = [key for key in (name_key, "confirmed", *flags) if key not in args]
    if missing:
        return f"missing key {missing[0]}"
    if not isinstance(args[name_key], str):
        return f"{name_key} must be a string"
    if args["confirmed"] is not True:
        return "confirmed must be true"
    for flag in flags:
        if not isinstance(args[flag], bool):
            return f"{flag} must be true or false"
    return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _served_path(path: str) -> str:
    """*path* when the router serves it, else ``<unknown>``: no client text reaches the log.

    The served set is the router's own -- ``_ENDPOINTS`` for the four GETs, ``/jobs`` and
    ``_JOB_PATH`` for the job routes -- so a new route is added in one place and this check
    follows it.
    """
    if path in _ENDPOINTS or path == "/jobs" or _JOB_PATH.fullmatch(path):
        return path
    return "<unknown>"


def _log_refusal(code: str, method: str, path: str) -> None:
    """One JSON line per refusal, so a probe from a page leaves a trace and nothing else does.

    The fields are the code, the method, the path and the time -- never a header value and
    never the token, so the app can surface the line without handling a secret. The query
    string is dropped with the path it arrived on: it is client text, and a caller that pasted
    the token into it would otherwise write the token to stderr. The path itself is written
    only when it is a route this server serves; anything else is ``<unknown>``, for the same
    reason -- a request path is client text too.
    """
    print(
        json.dumps(
            {
                "refused": code,
                "method": method,
                "path": _served_path(path),
                "time": _now(),
            }
        ),
        file=sys.stderr,
        flush=True,
    )


def _log_job(record: dict) -> None:
    """One JSON line per job start and per job end (AC-6), and nothing per event.

    The start line is ``{"job", "kind", "name", "time"}`` and the end line
    ``{"job", "ok", "code", "time"}``; neither carries a token or a header value, so the record
    the app can surface says what ran and how it ended and nothing a secret could hide in.
    """
    print(json.dumps(record), file=sys.stderr, flush=True)


class _Handler(BaseHTTPRequestHandler):
    """The request handler: one guard, three GETs, the job routes, and no other response shape.

    ``self.server`` is the object :func:`make_server` built, carrying the injected ``scan``,
    ``detect``, ``load_catalog``, ``install``, ``download`` and ``evict`` seams, the job
    registry and the launch ``token``. ``timeout`` is overridden per server by the factory, so
    the test that proves a stalled connection -- or a stalled stream write -- is dropped does
    not wait the production ten seconds.
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
        """Exact paths for the GETs and the job routes; anything else is 404.

        The path is resolved before the method: there is nothing at an unknown path to be
        method-not-allowed about, so a POST to one is a 404, while a POST to ``/hardware`` is
        the 405 AC-6 names. A module that raises is a 500 carrying its message and no
        traceback, which is the one diagnostic the app needs and nothing more.
        """
        path = self._path()
        if path == "/jobs":
            self._route_job_create(method)
            return
        match = _JOB_PATH.fullmatch(path)
        if match is not None:
            self._route_job_action(method, match.group(1), match.group(2))
            return
        endpoint = _ENDPOINTS.get(path)
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

    def _route_job_create(self, method: str) -> None:
        if method != "POST":
            self._respond("method_not_allowed")
            return
        try:
            self._post_job()
        except TimeoutError:
            # A body that stopped arriving is the socket timeout's case, not a 500.
            self.close_connection = True
        except Exception as error:  # a thread that would not start is the only likely raise
            self._respond("internal", str(error))

    def _route_job_action(self, method: str, job_id: str, action: str | None) -> None:
        if action == "/events":
            if method != "GET":
                self._respond("method_not_allowed")
                return
            self._get_job_events(job_id)
            return
        if action == "/cancel":
            if method != "POST":
                self._respond("method_not_allowed")
                return
            try:
                self._post_job_cancel(job_id)
            except Exception as error:
                self._respond("internal", str(error))
            return
        self._respond("not_found")

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
        macos_major = self._macos_major()
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
        The rows already in this Mac's Hugging Face cache are asked of ``fetch.downloaded``,
        which is the one definition of that question (sizes and links, never hashes), and
        passed to both functions, so a downloaded row is not excluded for disk and says so
        in its reason. On an unsupported Mac both lists are empty and
        ``unsupported_reason`` carries the one sentence: a per-model exclusion there would
        be a copy of a reason that belongs to the Mac, not to the model.

        ``measured_here`` is D5's one field this Mac can fill: the ``best`` block of the
        newest finished quickbench summary for that repo, read through
        ``quickbench.latest`` -- a quick run on this Mac, never one of our M2 Max rows. A
        repo with no finished quick run (or one whose every cell failed) keeps null.
        """
        hw = self.server.scan()
        statuses = self.server.detect()
        models = self.server.load_catalog()
        downloaded = frozenset(model.repo for model in models if fetch.downloaded(model))
        measured = {
            repo: summary["best"]
            for repo, summary in self.server.summaries().items()
            if isinstance(summary.get("best"), dict)
        }
        picks = [
            dataclasses.asdict(pick)
            for pick in recommend.pick(
                hw,
                models,
                statuses,
                hw.disk_free_bytes,
                downloaded,
                measured_here=measured,
            )
        ]
        excluded = []
        if hw.supported:
            for model in models:
                reason = recommend.exclusion_reason(
                    model, hw, hw.disk_free_bytes, downloaded
                )
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

    def _get_quickbench_plan(self) -> None:
        """AC-1's plan for one catalog repo, so the app can show it before the click.

        The query carries the only argument -- ``repo`` -- and no path, version or number.
        A repo that is not in the catalog, or one that is not in this Mac's cache, is the
        module's own ``ValueError`` delivered as ``400 bad_args`` with its message: "download
        it first" is a refusal the user can act on, and the plan never fetches it for them.
        """
        values = self._query().get("repo") or []
        if len(values) != 1 or not values[0]:
            self._respond("bad_args", "repo must name exactly one catalog model")
            return
        try:
            shown = quickbench.plan(
                values[0],
                self.server.scan(),
                self.server.detect(),
                self.server.load_catalog(),
            )
        except ValueError as error:
            self._respond("bad_args", str(error))
            return
        self._write_json(200, dataclasses.asdict(shown))

    def _query(self) -> dict:
        """The request's query string as a mapping, with the path's text never logged.

        Client text lives here and nowhere else: it is read to answer the request and never
        echoed into a stderr line, which is why the refusal log writes the path without it.
        """
        return urllib.parse.parse_qs(self.path.partition("?")[2], keep_blank_values=True)

    def _macos_major(self) -> int:
        """The integer before the first dot of ``Hardware.macos``: one definition, two callers."""
        return int(self.server.scan().macos.split(".", 1)[0])

    # --- the job routes --------------------------------------------------------------------

    def _post_job(self) -> None:
        """Validate, take the one slot, answer 202, and start the module call on a thread.

        The order is AC-1's exactly: Content-Type, Content-Length (refused before the body is
        read), the body, JSON, kind, args. Only after all of it is the slot claimed and the
        thread started, so no job exists for a request that was refused.
        """
        body = self._job_body()
        if body is None:
            return
        try:
            payload = json.loads(body)
        except ValueError:
            self._respond("bad_json")
            return

        kind = payload.get("kind") if isinstance(payload, dict) else None
        name_key = _JOB_ARGS.get(kind) if isinstance(kind, str) else None
        if name_key is None:
            self._respond("bad_kind")
            return
        args = payload.get("args")
        problem = _args_problem(args, name_key, flags=_JOB_FLAGS.get(kind, ()))
        if problem is not None:
            self._respond("bad_args", problem)
            return

        job = _Job(self.server.jobs, secrets.token_hex(8), kind, args[name_key], args)
        running = self.server.jobs.claim(job)
        if running is not None:
            self._respond("busy", f"job {running.id} is still running")
            return
        try:
            _log_job({"job": job.id, "kind": job.kind, "name": job.name, "time": _now()})
            threading.Thread(
                target=self._run_job, args=(job,), daemon=True, name=f"job-{job.id}"
            ).start()
        except Exception as error:
            # AC-2: the slot was claimed, so a failure before the thread runs must end the
            # job here. `append`'s terminal `done` is what frees it.
            job.append(
                _event(
                    "error",
                    str(error) or "the job could not be started",
                    {"code": "internal"},
                )
            )
            job.append(_event("done", "the job ended before it started", None))
            self._respond("internal", str(error))
            return
        self._write_json(202, {"job_id": job.id})

    def _job_body(self) -> bytes | None:
        """Read the body, or refuse it from the headers first; None means a refusal was written."""
        content_type = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self._respond("unsupported_media_type")
            return None
        try:
            length = int(self.headers.get("Content-Length"))
        except (TypeError, ValueError):
            self._respond("body_too_large")
            return None
        if length < 0 or length > MAX_BODY_BYTES:
            self._respond("body_too_large")
            return None
        return self.rfile.read(length)

    def _run_job(self, job: _Job) -> None:
        """Run the one module call, and make a raise end the stream with ``internal`` and ``done``.

        The module owns its consent gate, its lock, its rollback and its refusal codes; the
        server hands it the validated name, the literal ``true`` and its emit/cancel callables,
        and adds nothing of its own. The end line is written however the call ended.
        """
        ok = False
        try:
            if job.kind == "install":
                ok = self.server.install(
                    job.name,
                    True,
                    macos_major=self._macos_major(),
                    emit=job.append,
                    cancel=job.cancelled,
                )
            elif job.kind == "download":
                ok = self.server.download(
                    job.name, True, emit=job.append, cancel=job.cancelled
                )
            elif job.kind == "quickbench":
                ok = self.server.quickbench(
                    job.name,
                    confirmed=True,
                    osaurus=job.args.get("osaurus") is True,
                    emit=job.append,
                    cancel=job.cancelled,
                )
            else:
                ok = self.server.evict(job.name, True, emit=job.append)
        except Exception as error:
            job.append(
                _event("error", str(error) or "the job failed unexpectedly", {"code": "internal"})
            )
            job.append(_event("done", "the job ended after an unexpected error", None))
        finally:
            if not job.done:
                # The guard, not a second contract: the module owns its ending, and this only
                # frees the slot if one returned without it.
                job.append(_event("done", "the job ended without a done event", None))
            _log_job(
                {"job": job.id, "ok": ok is True, "code": _job_code(job), "time": _now()}
            )

    def _post_job_cancel(self, job_id: str) -> None:
        """Flip a running install's or download's cancel flag; an evict has none (AC-5)."""
        job = self.server.jobs.get(job_id)
        if job is None:
            self._respond("unknown_job")
            return
        if job.kind == "evict":
            self._respond("not_cancellable")
            return
        if job.done:
            self._respond("job_finished")
            return
        job.cancel_requested = True
        self._write_json(202, {"job_id": job.id})

    def _get_job_events(self, job_id: str) -> None:
        """Stream the job's events as server-sent events, then close after ``done`` (AC-4).

        The stream waits on the job's condition, never on the socket, so a job that is quiet
        for longer than the socket timeout is not cut off; the socket timeout stays set so it
        bounds each WRITE, and a client that stops reading releases its handler thread at the
        first blocked send. A disconnect ends the handler and never the job.
        """
        job = self.server.jobs.get(job_id)
        if job is None:
            self._respond("unknown_job")
            return
        last_seq = self._last_event_id()
        if last_seq is None:
            return
        if not job.open_stream():
            self._respond("too_many_streams")
            return
        try:
            self._stream_job(job, last_seq)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True
        finally:
            # AC-3: the slot comes back whichever way the stream ended -- done, a module that
            # raised, a client that disconnected, or the write timeout.
            job.close_stream()

    def _last_event_id(self) -> int | None:
        """The ``Last-Event-ID`` to resume after, 0 for the whole stream, or None on a refusal."""
        value = self.headers.get("Last-Event-ID")
        if value is None:
            return 0
        try:
            last_seq = int(value)
        except (TypeError, ValueError):
            self._respond("bad_event_id")
            return None
        if last_seq < 0:
            self._respond("bad_event_id")
            return None
        return last_seq

    def _stream_job(self, job: _Job, last_seq: int) -> None:
        """Write stored events in seq order, wait for new ones, and keepalive while quiet."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.flush()

        with job.condition:
            cursor = 0
            while cursor < len(job.events) and job.events[cursor]["seq"] <= last_seq:
                cursor += 1

        while True:
            with job.condition:
                if cursor >= len(job.events) and job.done:
                    return
                if cursor >= len(job.events):
                    before = len(job.events)
                    job.condition.wait(self.server.keepalive_s)
                    batch = job.events[cursor:] if len(job.events) > before else None
                else:
                    batch = job.events[cursor:]
                cursor = len(job.events)
            if batch is None:
                if job.done:
                    return
                self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
                continue
            for event in batch:
                if event["seq"] <= last_seq:
                    continue
                last_seq = event["seq"]
                self.wfile.write(
                    f"id: {event['seq']}\ndata: {json.dumps(event)}\n\n".encode("utf-8")
                )
                self.wfile.flush()
                if event.get("type") == "done":
                    return

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


class _Server(ThreadingHTTPServer):
    """The listener, with one handler-thread slot taken before each thread starts (AC-3).

    The slot is acquired non-blocking in ``process_request``: when the cap is reached the
    connection is closed with no response and no thread. Ownership passes to the handler
    thread the moment ``ThreadingMixIn.process_request`` has started it, and that thread
    releases the slot in a ``finally`` around every ending -- a normal response, a handler
    exception, and the socket timeout the base class turns into a closed connection.
    """

    daemon_threads = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.handler_slots = threading.BoundedSemaphore(MAX_HANDLER_THREADS)

    def process_request(self, request, client_address) -> None:
        if not self.handler_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            # The thread never took ownership of the slot, so this path still owns it.
            self.handler_slots.release()
            raise

    def process_request_thread(self, request, client_address) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.handler_slots.release()


def make_server(
    port: int = 0,
    *,
    scan=hardware.scan,
    detect=engines.detect_all,
    load_catalog=catalog.load,
    install=engines.install,
    download=fetch.download,
    evict=fetch.evict,
    quickbench=quickbench.run,
    summaries=quickbench.latest,
    token: str | None = None,
    timeout: float = HANDLER_TIMEOUT_S,
    keepalive_s: float = KEEPALIVE_S,
) -> ThreadingHTTPServer:
    """The listening server on 127.0.0.1:*port*, already accepting connections.

    The module seams default to the real functions, so the CLI passes none of them and a test
    passes fakes; the job seams take a name, a literal ``true`` and -- for quickbench -- the
    client's boolean ``osaurus``, and emit on the job, so a test never installs, downloads,
    starts a runtime or opens a socket. *summaries* is the quickbench reader
    ``/recommendations`` asks for ``measured_here``, injected so a test never reads this
    Mac's Application Support directory. *token* is generated fresh with
    ``secrets.token_urlsafe(32)`` when the caller has none, and it lives only on this object and
    in the one line the CLI prints -- no file, no log, no argv. *timeout* bounds each connection
    (and each stream write) and is short only in the tests that prove it; *keepalive_s* is the
    quiet interval between stream comments and is short only in the test that proves one.

    The socket is bound and listening before this returns, so a client may connect the moment
    it has read the announced line; a bind that fails raises ``OSError`` to the caller, which is
    where the exit code 2 and the stderr line belong.
    """
    handler = type("_TimedHandler", (_Handler,), {"timeout": timeout})
    listener = _Server((HOST, port), handler)
    listener.scan = scan
    listener.detect = detect
    listener.load_catalog = load_catalog
    listener.install = install
    listener.download = download
    listener.evict = evict
    listener.quickbench = quickbench
    listener.summaries = summaries
    listener.jobs = _Jobs()
    listener.keepalive_s = keepalive_s
    listener.token = token if token is not None else secrets.token_urlsafe(32)
    return listener
