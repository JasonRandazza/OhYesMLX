"""Uniform lifecycle over five heterogeneous local runtimes.

One dataclass per runtime behind one interface, because nothing else about them is alike:
``mlx_lm.server`` is Python, Osaurus is a Swift app behind a launcher, oMLX is a CLI shim
that execs an app binary, ``optiq serve`` is an MLX-optimised fork of mlx-lm, and vMLX is an
Electron app whose CLI is one entry point into the engine that app bundles. All five
speak OpenAI-compatible HTTP on loopback; beyond that, each names the same weights
differently and each starts with flags the others would choke on.

    handle = RUNTIMES["osaurus"].start(artifact_dir, "ornith-1.0-35b-jang_4m")
    ...measure...
    handle.stop()          # does not return while the port is held or the process lives

**Readiness is not the port, and for no runtime here is it the model list.**
On a load failure mlx-lm 0.31.3 binds 8081 and logs ``Starting httpd at 127.0.0.1 on port
8081...`` after the load thread has already raised, so a client POST connects and then
hangs forever with zero bytes received. Its ``/v1/models`` handler cannot be believed
either: it lists ``str(Path(--model).resolve())`` straight off disk, so the inventory
returns the right id even when the model was never loaded. oMLX lists every directory it
finds in its catalog the same way, and Osaurus lists a model it then answers ``not
installed or registered with any provider`` for. Both signals are therefore required --
the model id *and* a log with no load failure in it -- and the log is read again once the
id appears, because a runtime writes the failure while it is answering the model list
(docs/research/2026-09-14-oq-portability-spike.md,
docs/research/2026-09-15-grid-loadability-probe.md).

The flag tuples below are ported verbatim from LMRE's ``runtime_adapters``. They are not
defaults, they are pins, and each one costs something when it is left to the runtime.

The cache pin (Phase 6, plan 06-02) is a start-command flag on four of the five runtimes and
a host setting on the fifth. ``cache_state=None`` is the pin not taken, and every runtime
starts exactly as it did before the pin existed. ``"off"`` is prefix/KV reuse disabled and
``"on"`` is enabled, and the value a runtime cannot deliver is refused up front rather than
approximated -- see :meth:`Runtime.cache_state_refusal` and, for the one runtime with no flag
in either direction, :meth:`Osaurus.cache_state_refusal`.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .osaurus_settings import (
    capture_osaurus_settings,
    describe_drift,
    diff_against_baseline,
    load_baseline,
)

# A 35B takes minutes to load, and a slow cold read of a 20 GB artifact can take more.
READY_TIMEOUT_S = 900.0
READY_POLL_S = 1.0
MODELS_TIMEOUT_S = 5.0
VERSION_TIMEOUT_S = 30.0
STOP_TIMEOUT_S = 30.0
STOP_POLL_S = 0.25
TERM_GRACE_S = 10.0
KILL_GRACE_S = 5.0
# How much of a runtime's log a readiness poll reads. 64 KB was not enough to hold a
# failure: a shape mismatch prints one parameter name per line, so oMLX's fatal line sat
# 1.4 KB inside the 64 KB window on the read that mattered and had scrolled out of it by
# the next one -- the same log reaches 266 KB with its parameter dump printed three times
# (results/logs/omlx-20260915T135626-71559.log: line 2530 at byte 136,891 of 201,042).
# ponytail: a dump longer than this hides the fatal line again; the upgrade path is a
# forward scan that stops at the first failure line instead of reading a window.
LOG_TAIL_BYTES = 1024 * 1024

LSOF = shutil.which("lsof") or "/usr/sbin/lsof"
LOGS_DIR = Path(__file__).resolve().parents[1] / "results" / "logs"

# The two states the cache pin may take. `None` is not a third state: it is the absence of the
# pin, and it must never read as "off" -- the runs measured before the pin existed ran each
# runtime's own default, and those defaults were not uniform (the Osaurus grid columns ran
# with its prefix cache ON). `on` is not "whatever the runtime happens to do" either: it is
# the state whose reuse the run header names, pinned where that runtime has a way to pin it.
CACHE_STATE_OFF = "off"
CACHE_STATE_ON = "on"
CACHE_STATES = (CACHE_STATE_OFF, CACHE_STATE_ON)

# Loopback-only key for a run-owned oMLX. Not a shared secret, and not user state.
OMLX_API_KEY = "ohyesmlx-local"
OMLX_CATALOG_TOKEN = "{OHYESMLX_OMLX_CATALOG}"
OMLX_CATALOG_DIRNAME = "catalog"
OMLX_BASE_DIRNAME = "base"
SAFE_CATALOG_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")

# vMLX's engine source ships inside the app bundle the ``vmlx`` wrapper on PATH execs, and
# the constant in it is the version the running server reports: server.py passes it as the
# FastAPI app version (docs/runtimes/vmlx.md §9.4). There is no version subcommand and
# ``vmlx --version`` exits 2, so this file is where the provenance is.
VMLX_ENGINE_INIT = (
    "/Applications/vMLX.app/Contents/Resources/vmlx-engine-source/vmlx_engine/__init__.py"
)
VMLX_VERSION_SED = r's/^__version__ = "\([^"]*\)".*$/\1/p'

# A line that means the runtime will never answer, whatever the port says. Kept narrow
# on purpose: this gate fails a run, so a pattern that matches ordinary startup chatter
# would make a healthy runtime look broken.
LOG_ERROR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"Traceback \(most recent call last\)"),
    re.compile(r"^Exception in thread "),
    re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception):\s"),
    re.compile(r"^\[?(?:error|ERROR)\]?[:\s]"),
    re.compile(
        r"\b(?:failed to load|error while loading|unable to load|exited unexpectedly)\b",
        re.IGNORECASE,
    ),
    re.compile(r"Address already in use", re.IGNORECASE),
    re.compile(r"\b(?:Segmentation fault|Abort trap|Bus error|Killed: 9)\b"),
)

# What an inventory poll can raise while a runtime is still coming up.
_TRANSIENT = (OSError, http.client.HTTPException, ValueError, KeyError, TypeError)


class RuntimeLifecycleError(RuntimeError):
    """Base class for a runtime that could not be started or stopped cleanly."""


class RuntimeStartError(RuntimeLifecycleError):
    """A runtime never became ready, or was refused before it was spawned."""


class RuntimeStopError(RuntimeLifecycleError):
    """A runtime did not release its port."""


def _now() -> float:
    return time.monotonic()


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _run(command: tuple[str, ...], timeout_s: float):
    """Run a short-lived helper command. ``None`` if it could not be run at all."""
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _spawn(command: tuple[str, ...], log_path: Path) -> int:
    """Start a runtime detached, logging to *log_path*, and return its pid.

    New session, so the tree it creates can be signalled as a group: oMLX starts through
    a shell shim and Osaurus through a launcher, and a signal to the pid alone is not
    guaranteed to reach the server.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "ab", buffering=0) as log:
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as error:
            raise RuntimeStartError(f"could not start {command[0]}: {error}") from error
    return process.pid


def _process_alive(pid: int) -> bool:
    """Whether *pid* is still running, reaping it first when it is our own child.

    Without the reap an exited child stays a zombie, and ``kill(pid, 0)`` keeps
    succeeding on it -- so a stopped runtime would look alive forever.
    """
    try:
        reaped, _status = os.waitpid(pid, os.WNOHANG)
    except OSError:
        pass
    else:
        if reaped == pid:
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _signal_tree(pid: int, sig: int) -> None:
    try:
        os.killpg(os.getpgid(pid), sig)
    except ProcessLookupError:
        return
    except PermissionError as error:
        raise RuntimeStopError(
            f"permission denied signalling process group of {pid}"
        ) from error


def _signal_process(pid: int, sig: int) -> None:
    """Signal one pid, and only it.

    Deliberately not the process group. A pid recovered from the port belongs to a runtime's
    own launcher, whose grouping this harness never established -- ``osaurus serve`` hands
    the port to an app process by a mechanism of its own -- and a group signal could reach
    something this run has no claim on.
    """
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        return
    except PermissionError as error:
        raise RuntimeStopError(f"permission denied signalling process {pid}") from error


def _port_is_free(port: int) -> bool:
    """Whether nothing is listening on *port*, per ``lsof``.

    A port this cannot be verified on is reported as busy: the caller is deciding
    whether to hand a port to a runtime or to let a run finish, and in both cases
    "unknown" has to mean "not free yet".
    """
    result = _run((LSOF, "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"), STOP_TIMEOUT_S)
    if result is None:
        return False
    return not result.stdout.strip()


def _listener_pids(port: int) -> tuple[int, ...]:
    """The pids listening on *port* right now, per ``lsof -t``.

    This is how a process a runtime's launcher handed off to is named. ``osaurus serve``
    starts the app, prints ``listening on http://127.0.0.1:1337`` and exits, so the pid this
    run spawned is not the one holding the weights -- and once ``osaurus stop`` has freed the
    port there is nothing left to find it by. So it is read while the port is still held.

    Reading it is only ever a claim about a process this run started: :meth:`Runtime.start`
    refuses to spawn over a listener it did not create, so anything listening on the port
    after that check appeared because this run spawned a runtime onto it.
    """
    result = _run((LSOF, "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"), STOP_TIMEOUT_S)
    if result is None:
        # Unverifiable is "no process named", not "nothing is running": the port check every
        # stop also makes refuses to treat an unanswerable lsof as free.
        return ()
    return tuple(
        dict.fromkeys(
            int(line) for line in result.stdout.split() if line.strip().isdigit()
        )
    )


def _serving_pid(spawned: int, port: int) -> int:
    """The pid actually holding the weights, which is not always the one that was spawned.

    ``osaurus serve`` starts the app, prints the address it is listening on and exits, so a
    sampler pointed at the spawned pid measures a launcher on its way out -- 4.7 MB from a
    single sample, against 2,699-4,172 MB and 11-14 samples from every runtime that stays.
    The port names the survivor, on the same claim :func:`_listener_pids` documents: a
    listener that appeared after :meth:`Runtime.start` refused to spawn over one is ours.

    The spawned pid is kept whenever the port cannot improve on it: nothing listening,
    the spawned pid already listening, or more than one distinct listener. An unreadable
    port is not a licence to sample a stranger's memory and publish it as this cell's.
    """
    listeners = _listener_pids(port)
    if len(listeners) == 1 and spawned not in listeners:
        return listeners[0]
    return spawned


def _read_log(path: Path) -> str:
    """The tail of a runtime's log, or ``""`` when there is nothing to read yet."""
    try:
        with open(path, "rb") as log:
            log.seek(0, os.SEEK_END)
            size = log.tell()
            log.seek(max(0, size - LOG_TAIL_BYTES))
            return log.read().decode("utf-8", "replace")
    except OSError:
        return ""


def _log_path(name: str) -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    return LOGS_DIR / f"{name}-{stamp}-{os.getpid()}.log"


def log_load_error(text: str) -> str | None:
    """The load failure visible in a runtime's log, or ``None`` when the log is clean.

    The *last* match is returned, not the first: a Python traceback names its cause on
    its final line (``ValueError: Model type gemma4_unified not supported.``), and the
    first is only ever the marker that says one is coming.
    """
    found = None
    for line in text.splitlines():
        if any(pattern.search(line) for pattern in LOG_ERROR_PATTERNS):
            found = line.strip()
    return found


def _raise_on_log_error(name: str, log_path: Path) -> None:
    """Raise when the runtime's log reports a load failure, and only then.

    Called before the model list is polled and again after it has answered with one of our
    ids. The second read is what catches a runtime that lists a model it cannot serve, and
    it has to happen second: the failure is written *while* the model list is being
    answered -- live, oMLX answered ``GET /v1/models`` with a JANG artifact at 13:56:29,1xx
    and the VLM path had failed on it at 13:56:29,130
    (results/logs/omlx-20260915T135626-71559.log).
    """
    error = log_load_error(_read_log(log_path))
    if error is not None:
        raise RuntimeStartError(f"{name} failed to load: {error} (log: {log_path})")


def _inventory(base_url: str, *, api_key: str | None = None) -> tuple[str, ...]:
    """The model ids a runtime is currently offering."""
    request = urllib.request.Request(f"{base_url}/models")
    if api_key:
        request.add_header("Authorization", f"Bearer {api_key}")
    with urllib.request.urlopen(request, timeout=MODELS_TIMEOUT_S) as response:
        payload = json.loads(response.read())
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        raise ValueError(f"unrecognised model list from {base_url}")
    return tuple(
        entry["id"]
        for entry in data
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    )


def hub_repo_name(artifact_dir: str) -> str | None:
    """The repo an HF-cache artifact belongs to, lowercased, or ``None`` if it is not one.

    The hub lays a repo out as ``models--<org>--<name>/snapshots/<commit>``, so the
    directory a cell is handed is the commit hash and ``name_forms`` can derive nothing
    but hashes from it. The repo's name survives only in the ``models--<org>--<name>``
    directory above ``snapshots/``, and Osaurus serves every model under it, lowercased:
    the live inventory reads ``qwen3.5-4b-oq4``, ``ornith-1.0-35b-jang_4m``, and so on.
    """
    for part in Path(os.path.abspath(artifact_dir)).parts:
        if not part.startswith("models--"):
            continue
        organization, _, repository = part[len("models--") :].partition("--")
        if organization and repository:
            return repository.lower()
    return None


def name_forms(artifact_dir: str) -> tuple[str, ...]:
    """Every name one artifact is served under, derived from its directory.

    Ported from LMRE's model-ID alias registry. The forms are the ones actually observed
    between these runtimes and that project's cells: the HF repo id (``mlx-community/X``),
    the flat-hub spelling (``mlx-community__X``), the routed spelling Osaurus gives an
    oMLX model (``omlx/X``), and the artifact directory itself, which is what
    ``mlx_lm.server`` and ``optiq serve`` report.
    """
    path = Path(os.path.abspath(artifact_dir))
    forms = [path.name]
    if path.parent.name:
        forms += [f"{path.parent.name}/{path.name}", f"{path.parent.name}__{path.name}"]
    forms += [f"omlx/{path.name}", str(path)]
    return _ordered(forms)


def _ordered(*groups) -> tuple[str, ...]:
    """The names in priority order, first mention winning and nothing repeated."""
    seen: dict[str, None] = {}
    for group in groups:
        for name in group:
            if name:
                seen.setdefault(name, None)
    return tuple(seen)


def resolve_model_id(candidates: tuple[str, ...], inventory: tuple[str, ...]) -> str | None:
    """The name the runtime itself is using, or ``None`` if it is offering none of them.

    The match is returned as the runtime spells it, never as it was asked for: a handle
    carries what the server answers to, because that is what a request must name.
    """
    available = set(inventory)
    for candidate in candidates:
        if candidate in available:
            return candidate
    return None


@dataclass(frozen=True)
class OmlxScratch:
    """The per-run directories an oMLX start is given, all under one removable root."""

    root: Path
    catalog: Path
    base: Path
    link_name: str


def omlx_link_name(artifact_dir: str, model_id: str) -> str:
    """The name oMLX will serve the weights under.

    A catalog entry cannot contain a slash, so the HF repo id spelling is unavailable
    here and the artifact's own directory name is the last resort -- which is what
    LMRE's oMLX cells used.
    """
    for candidate in (model_id, *name_forms(artifact_dir)):
        if SAFE_CATALOG_NAME.fullmatch(candidate):
            return candidate
    raise RuntimeStartError(f"no safe oMLX catalog name for {artifact_dir!r}")


def create_omlx_scratch(artifact_dir: str, model_id: str) -> OmlxScratch:
    """A fresh model catalog and base path for oMLX, holding exactly one model.

    oMLX serves whatever directory ``--model-dir`` points at, so a directory holding one
    symlink is how a cell is made to see only its own model. The base path is per-run for
    the same class of reason: oMLX writes catalog settings under it, and they must not
    land in the user's own configuration.
    """
    artifact = Path(artifact_dir).resolve()
    if not artifact.is_dir():
        raise RuntimeStartError(f"artifact is not a directory: {artifact_dir}")
    root = Path(tempfile.mkdtemp(prefix="ohyesmlx-omlx-"))
    catalog = root / OMLX_CATALOG_DIRNAME
    base = root / OMLX_BASE_DIRNAME
    catalog.mkdir()
    base.mkdir()
    link_name = omlx_link_name(artifact_dir, model_id)
    (catalog / link_name).symlink_to(artifact, target_is_directory=True)
    return OmlxScratch(root=root, catalog=catalog, base=base, link_name=link_name)


def remove_omlx_catalog(catalog: Path) -> None:
    """Remove a catalog this process created, and nothing else.

    Every entry is checked to be a symlink before it is unlinked. A directory of symlinks
    is a thing this module made; a recursive delete of a path whose contents were not
    checked is how a harness eats a model directory.
    """
    if not catalog.exists():
        return
    for child in sorted(catalog.iterdir()):
        if not child.is_symlink():
            raise RuntimeStopError(f"oMLX catalog holds a non-symlink entry: {child}")
        child.unlink()
    catalog.rmdir()


def _remove_scratch(scratch: str | None) -> None:
    """Drop a failed start's leftovers. Never raises: it runs beside a real error."""
    if scratch is None:
        return
    root = Path(scratch)
    try:
        remove_omlx_catalog(root / OMLX_CATALOG_DIRNAME)
        shutil.rmtree(root, ignore_errors=True)
    except (OSError, RuntimeStopError):
        pass


def _await_exit(pid: int, timeout_s: float) -> bool:
    deadline = _now() + timeout_s
    while _process_alive(pid):
        if _now() >= deadline:
            return False
        _sleep(STOP_POLL_S)
    return True


def _kill_resident(pids: tuple[int, ...]) -> None:
    """Kill what a runtime's own stop command left behind, and wait for it to go.

    ``osaurus stop`` frees port 1337 and leaves the app process resident, still holding the
    weights: a freed port satisfies the one-runtime-holds-weights rule's letter and breaks
    its substance, and a grid run would leak about one such process per cell into the memory
    it is trying to measure. SIGTERM is ignored by these instances, so the escalation ladder
    that :func:`_shutdown` walks for a spawned pid would only be ten seconds of waiting for
    the same outcome.
    """
    for pid in pids:
        if not _process_alive(pid):
            continue
        _signal_process(pid, signal.SIGKILL)
        if not _await_exit(pid, KILL_GRACE_S):
            raise RuntimeStopError(
                f"process {pid} was still listening on this runtime's port and is alive "
                f"{KILL_GRACE_S:g}s after SIGKILL"
            )


def await_port_free(port: int, timeout_s: float = STOP_TIMEOUT_S) -> None:
    """Block until nothing is listening on *port*, or raise.

    A run that does not release its port has failed, whatever else it reported, so this
    is the last thing every stop does.
    """
    deadline = _now() + timeout_s
    while True:
        if _port_is_free(port):
            return
        if _now() >= deadline:
            raise RuntimeStopError(
                f"port {port} is still held {timeout_s:g}s after stopping; "
                f"check `{LSOF} -nP -iTCP:{port} -sTCP:LISTEN`"
            )
        _sleep(STOP_POLL_S)


def _shutdown(pid: int, port: int, stop_command: tuple[str, ...] = ()) -> None:
    """Take a runtime down and do not return until its port is free and its processes gone.

    The listeners are read *before* the stop command runs, because the stop command is what
    frees the port and a process it leaves behind can no longer be named by that port
    afterwards. The pid this run spawned is one candidate; every other pid listening on the
    port is a process the runtime's launcher started out of this run's spawn, and is killed
    on its own pid rather than as a group (see :func:`_signal_process`).
    """
    listeners = _listener_pids(port)
    if stop_command:
        _run(stop_command, STOP_TIMEOUT_S)
    if _process_alive(pid):
        _signal_tree(pid, signal.SIGTERM)
        if not _await_exit(pid, TERM_GRACE_S):
            _signal_tree(pid, signal.SIGKILL)
            _await_exit(pid, KILL_GRACE_S)
    _kill_resident(tuple(other for other in listeners if other != pid))
    await_port_free(port)


@dataclass
class Handle:
    """One running runtime.

    The pinned fields come first, and ``first_request_s`` is the last of them: the latency of
    the cold visit's first warmup request, which is where a runtime that loads its weights
    lazily pays for them. ``cold_load_s`` is only a time-to-listening for one of those, so a
    cross-runtime load comparison uses the sum. The measurement loop fills it in when that
    request lands, because the request is its to make. Everything after it is lifecycle state
    the handle needs to release its own port and to be addressed to, and carries the same
    defaults an interface-shaped construction would give it.
    """

    pid: int
    port: int
    base_url: str
    model_id: str
    version: str
    cold_load_s: float
    first_request_s: float | None = None
    # The pid to sample memory from, when the launcher that was spawned is not the process
    # that ended up holding the weights. ``None`` means the spawned pid is the server.
    serving_pid: int | None = None
    stop_command: tuple[str, ...] = ()
    scratch: str | None = None
    # The credential the runtime was started with. Measured requests must send it: oMLX
    # answers an unauthenticated /v1/chat/completions with 401, and the readiness probe
    # authenticating while the measurement did not is how that went unnoticed.
    api_key: str | None = None

    @property
    def memory_pid(self) -> int:
        """The pid whose footprint is this runtime's. See :func:`_serving_pid`."""
        return self.pid if self.serving_pid is None else self.serving_pid

    def stop(self) -> None:
        """Stop the runtime. Does not return until the port is free."""
        _shutdown(self.pid, self.port, self.stop_command)
        _remove_scratch(self.scratch)


@dataclass(frozen=True)
class Runtime:
    """One runtime's start command, readiness rule, stop rule and version probe."""

    name: str
    port: int

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def start_command(
        self, artifact_dir: str, model_id: str, *, cache_state: str | None = None
    ) -> tuple[str, ...]:
        raise NotImplementedError

    def stop_command(self) -> tuple[str, ...]:
        return ()

    def version_command(self) -> tuple[str, ...]:
        return ()

    def cache_state_refusal(self, cache_state: str | None) -> str | None:
        """Why this runtime cannot be measured in *cache_state*, or ``None`` when it can.

        The default is ``None``: a runtime whose prefix/KV reuse is controlled by a
        start-command flag can be driven into either state by :meth:`start_command`, and the
        absent pin (``None``) asks for no state at all. The one override is Osaurus, whose
        cache state is host settings this harness must not edit -- it refuses a state the host
        is not in rather than measuring something else and labelling it.
        """
        return None

    def version(self) -> str:
        """Provenance for this runtime's build. Never raises; absence says why."""
        command = self.version_command()
        if not command:
            return "unknown: no version command"
        result = _run(command, VERSION_TIMEOUT_S)
        if result is None:
            return "unknown: version command could not be run"
        if result.returncode != 0:
            return f"unknown: exited with code {result.returncode}"
        return self.parse_version(result.stdout)

    def parse_version(self, output: str) -> str:
        lines = output.strip().splitlines()
        return lines[0].strip() if lines else "unknown: empty version output"

    def model_id_candidates(self, artifact_dir: str, model_id: str) -> tuple[str, ...]:
        raise NotImplementedError

    def api_key(self) -> str | None:
        return None

    def check_host_state(self) -> None:
        """Refuse to start when host state this runtime cannot pin has moved."""

    def build_command(
        self, artifact_dir: str, model_id: str, *, cache_state: str | None = None
    ) -> tuple[tuple[str, ...], str | None]:
        """The argv to spawn, plus any scratch tree a stop will have to remove."""
        return self.start_command(artifact_dir, model_id, cache_state=cache_state), None

    def await_ready(
        self,
        *,
        pid: int,
        log_path: Path,
        artifact_dir: str,
        model_id: str,
        timeout_s: float = READY_TIMEOUT_S,
    ) -> str:
        """Hold until the runtime answers for its model, or raise.

        The log is read before the inventory on every pass because the inventory can lie
        -- mlx-lm lists the ``--model`` path whether or not it ever loaded, oMLX lists its
        whole catalog, Osaurus lists models it refuses -- while a traceback cannot. The
        log is then read *again* once the id is there: a load that fails writes its cause
        while the model list is being answered, so a handle returned on the listing alone
        is how oMLX published a cold load for a model it had already failed to load.
        """
        candidates = self.model_id_candidates(artifact_dir, model_id)
        deadline = _now() + timeout_s
        complaint = "no inventory yet"
        while True:
            _raise_on_log_error(self.name, log_path)
            if not _process_alive(pid) and not _listener_pids(self.port):
                raise RuntimeStartError(
                    f"{self.name} exited before it served {candidates[0]!r} "
                    f"(log: {log_path})"
                )
            try:
                inventory = _inventory(self.base_url, api_key=self.api_key())
            except urllib.error.HTTPError as exc:
                # A rejected credential will not start working in 900 seconds.
                if exc.code in (401, 403):
                    raise RuntimeStartError(
                        f"{self.name} answered the model list with HTTP {exc.code}; "
                        "it wants a credential this run does not have"
                    ) from exc
                complaint = f"HTTPError: {exc}"
            except _TRANSIENT as exc:
                complaint = f"{exc.__class__.__name__}: {exc}"
            else:
                resolved = resolve_model_id(candidates, inventory)
                if resolved is not None:
                    _raise_on_log_error(self.name, log_path)
                    return resolved
                complaint = f"inventory has {len(inventory)} models, none of them ours"
            if _now() >= deadline:
                raise RuntimeStartError(
                    f"{self.name} did not serve {candidates[0]!r} within "
                    f"{timeout_s:g}s ({complaint}; log: {log_path})"
                )
            _sleep(READY_POLL_S)

    def start(
        self, artifact_dir: str, model_id: str, *, cache_state: str | None = None
    ) -> Handle:
        """Spawn the runtime, hold until it can answer, and return its handle.

        *cache_state* is the run's cache pin, threaded into the start command; ``None`` is the
        pin not taken and produces the command this method produced before the pin existed.
        The refusal is not made here: :meth:`cache_state_refusal` is the measurement loop's to
        ask, before it starts anything, so a state this runtime cannot be driven into is
        recorded as ``N/A`` with its reason rather than raised as a start failure.
        """
        if not _port_is_free(self.port):
            raise RuntimeStartError(
                f"port {self.port} is already held by a listener this run did not "
                f"start; refusing to start {self.name} over it"
            )
        self.check_host_state()
        command, scratch = self.build_command(artifact_dir, model_id, cache_state=cache_state)
        log_path = _log_path(self.name)
        started = _now()
        pid = None
        try:
            pid = _spawn(command, log_path)
            resolved = self.await_ready(
                pid=pid,
                log_path=log_path,
                artifact_dir=artifact_dir,
                model_id=model_id,
            )
            version = self.version()
        except BaseException:
            # A start that failed still owns a process, and that process may hold the
            # port. Its own error is the one worth reporting, so cleanup is silent.
            if pid is not None:
                try:
                    _shutdown(pid, self.port, self.stop_command())
                except RuntimeLifecycleError:
                    pass
            _remove_scratch(scratch)
            raise
        return Handle(
            pid=pid,
            port=self.port,
            base_url=self.base_url,
            model_id=resolved,
            version=version,
            cold_load_s=_now() - started,
            serving_pid=_serving_pid(pid, self.port),
            stop_command=self.stop_command(),
            scratch=scratch,
            api_key=self.api_key(),
        )


def prompt_cache_flags(cache_state: str | None) -> tuple[str, ...]:
    """The mlx-lm ``LRUPromptCache`` flags for one cache state: none, off, or a pinned on.

    mlx_lm 0.31.3 keeps an LRU prompt cache and reuses the nearest prefix across requests
    (``server.py:753``, ``fetch_nearest_cache``), and ``--prompt-cache-size`` is its only
    control: "Maximum number of distinct KV caches to hold in the prompt cache"
    (``server.py:1872``, default 10). At 0 the cache holds nothing -- every insert evicts the
    entry it just added (``models/cache.py:1696-1737``), so ``fetch_nearest_cache`` always
    answers ``None`` and every request prefills its prompt whole. That is ``off``.

    ``on`` pins the value instead of relying on it: 10 is what this mlx-lm defaults to, and a
    command that claimed to pin the cache on while naming no size would be adopting whatever a
    later version's default became.

    OptiQ runs this same server -- ``optiq serve`` passes flags it does not know through to
    ``mlx_lm.server``'s own argparse (``optiq/cli.py:2571`` collecting ``ctx.args``, ``:3030``
    handing them to ``mlx_lm.server``, with ``ignore_unknown_options`` set at ``:2332``) and
    bundles the same mlx-lm 0.31.3 -- so both runtimes read one definition of what the flag
    means instead of two that would drift.
    """
    if cache_state == CACHE_STATE_OFF:
        return ("--prompt-cache-size", "0")
    if cache_state == CACHE_STATE_ON:
        return ("--prompt-cache-size", "10")
    return ()


class MlxLm(Runtime):
    """The control: stock mlx-lm's own server."""

    def start_command(
        self, artifact_dir: str, model_id: str, *, cache_state: str | None = None
    ) -> tuple[str, ...]:
        return (
            "python",
            "-m",
            "mlx_lm.server",
            "--model",
            artifact_dir,
            "--port",
            str(self.port),
            *prompt_cache_flags(cache_state),
        )

    def version_command(self) -> tuple[str, ...]:
        return ("python", "-m", "mlx_lm", "--version")

    def model_id_candidates(self, artifact_dir: str, model_id: str) -> tuple[str, ...]:
        # mlx_lm.server appends str(Path(--model).resolve()) to /v1/models, and also
        # every mlx-looking repo in the HF cache.
        absolute = str(Path(os.path.abspath(artifact_dir)))
        return _ordered((absolute, model_id), name_forms(artifact_dir))


class Osaurus(Runtime):
    """The one runtime with no tuning flags to pin, and host settings instead."""

    def start_command(
        self, artifact_dir: str, model_id: str, *, cache_state: str | None = None
    ) -> tuple[str, ...]:
        # No model and no tuning on the command line: what a cell measures is decided by
        # ~/.osaurus/config, which check_host_state refuses to run away from. The cache pin
        # is one of those settings, so it adds no flag here in either state -- and the state
        # it cannot be asked for is refused by cache_state_refusal below, never faked.
        return ("osaurus", "serve", "--port", str(self.port), "--yes")

    def cache_state_refusal(self, cache_state: str | None) -> str | None:
        """Refuse a requested cache state the host's own settings disagree with.

        Osaurus takes no flag for its prefix cache in either direction: the state lives in
        ``~/.osaurus/config/server-runtime.json``, under ``cache.prefix.enabled``, and the
        harness does not edit the host's files -- editing them is the sweep script's job, with
        a byte-exact backup and a restore, because it is a change to Jason's machine rather
        than to this run.

        So a requested state is honoured only when the host is already in it, and anything
        else is ``N/A`` with this reason. A restart is not a way to turn the cache on: a
        process that just started has an empty cache, which is ``off`` whatever the settings
        say, so restarting to reach ``on`` would label an off cell as an on one.
        """
        if cache_state is None:
            return None
        live = capture_osaurus_settings().get("server-runtime.json:cache.prefix.enabled")
        wanted = cache_state == CACHE_STATE_ON
        if live is wanted:
            return None
        state = {True: "true", False: "false"}.get(live, f"unreadable ({live})")
        return (
            f"cache_state={cache_state!r} needs Osaurus's prefix cache "
            f"{'on' if wanted else 'off'}, and the host has cache.prefix.enabled "
            f"{state} in ~/.osaurus/config/server-runtime.json. Osaurus exposes no "
            "start-command flag for the cache, and the harness does not edit the host's "
            "settings, so this cell is N/A in this state rather than measured in another "
            "one. A restart is not a way to turn the cache on: a fresh process has an empty "
            "cache whatever the settings say."
        )

    def stop_command(self) -> tuple[str, ...]:
        return ("osaurus", "stop")

    def version_command(self) -> tuple[str, ...]:
        return ("osaurus", "doctor", "--json", "--redact")

    def parse_version(self, output: str) -> str:
        try:
            payload = json.loads(output)
        except ValueError:
            return "unknown: unparseable `osaurus doctor` output"
        apps = payload.get("apps") if isinstance(payload, dict) else None
        bundles = [entry for entry in apps or [] if isinstance(entry, dict)]
        if not bundles:
            return "unknown: no app bundles in `osaurus doctor` output"
        # doctor reports every installed bundle precisely because duplicates happen.
        # Naming an arbitrary one would make the provenance confidently wrong, so prefer
        # the bundle that is actually serving and say when there was a choice.
        running = [entry for entry in bundles if entry.get("isRunning") is True]
        entry = running[0] if running else bundles[0]
        found = entry.get("version")
        if not isinstance(found, str) or not found.strip():
            return "unknown: no version in `osaurus doctor` bundle entry"
        return found if len(bundles) == 1 else f"{found} (one of {len(bundles)} bundles)"

    def model_id_candidates(self, artifact_dir: str, model_id: str) -> tuple[str, ...]:
        # Osaurus serves from its own library, so the name a user typed need not look
        # anything like the artifact's path. It names each model after the repo,
        # lowercased, and for an artifact in hub layout that name is the only candidate
        # that is not a commit hash -- so it leads, and every other candidate follows.
        return _ordered(
            (hub_repo_name(artifact_dir),), (model_id,), name_forms(artifact_dir)
        )

    def check_host_state(self) -> None:
        """Refuse to start when the host drifted from the recorded baseline.

        No recorded baseline means no gate: a fresh checkout should not be unable to run,
        and an operator who has not recorded a baseline has not yet claimed one.
        """
        baseline = load_baseline()
        if baseline is None:
            return
        drift = diff_against_baseline(capture_osaurus_settings(), baseline)
        if drift:
            raise RuntimeStartError(
                "Osaurus settings drifted from the recorded baseline; these decide what "
                "a cell measures and none of them is visible in the start command:\n"
                + describe_drift(drift)
            )


class Omlx(Runtime):
    """The runtime that has to be given a model directory it cannot see past."""

    def start_command(
        self, artifact_dir: str, model_id: str, *, cache_state: str | None = None
    ) -> tuple[str, ...]:
        command = (
            "omlx",
            "serve",
            "--model-dir",
            OMLX_CATALOG_TOKEN,
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
            "--max-concurrent-requests",
            "1",
            "--memory-guard",
            "off",
        )
        # `--no-cache` is "Disable oMLX paged SSD cache" (omlx/cli.py:1140-1143) and its
        # absence leaves the cache on, because CacheSettings.enabled defaults True
        # (omlx/settings.py:331) and the SSD directory defaults to <base-path>/cache
        # (settings.py:387-399) -- which for a run is the per-run scratch this runtime is
        # given, removed with it at stop. So `off` is the flag that is already there, `on`
        # is dropping it, and the absent pin keeps today's command byte for byte.
        if cache_state != CACHE_STATE_ON:
            command += ("--no-cache",)
        return command

    def version_command(self) -> tuple[str, ...]:
        return ("omlx", "--version")

    def api_key(self) -> str | None:
        return OMLX_API_KEY

    def model_id_candidates(self, artifact_dir: str, model_id: str) -> tuple[str, ...]:
        # oMLX serves the catalog entry names, and the entry is named here.
        return _ordered(
            (omlx_link_name(artifact_dir, model_id),), name_forms(artifact_dir), (model_id,)
        )

    def build_command(
        self, artifact_dir: str, model_id: str, *, cache_state: str | None = None
    ) -> tuple[tuple[str, ...], str | None]:
        scratch = create_omlx_scratch(artifact_dir, model_id)
        command = tuple(
            str(scratch.catalog) if part == OMLX_CATALOG_TOKEN else part
            for part in self.start_command(artifact_dir, model_id, cache_state=cache_state)
        )
        return command + (
            "--base-path",
            str(scratch.base),
            "--api-key",
            OMLX_API_KEY,
        ), str(scratch.root)


class Optiq(Runtime):
    """The fork whose expert-streaming heuristic silently costs 5x on large artifacts."""

    def start_command(
        self, artifact_dir: str, model_id: str, *, cache_state: str | None = None
    ) -> tuple[str, ...]:
        return (
            "optiq",
            "serve",
            "--model",
            artifact_dir,
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
            "--no-anthropic",
            "--no-responses",
            "--no-auth",
            # An integer cap installs a RotatingKVCache that silently rotates a longer prompt
            # instead of refusing it. Qwen3.5 and LFM2 bring their own make_cache and ignore
            # it, so 8192 never capped anything measured -- but a start command claiming a cap
            # that is not there contradicts a 32k figure beside it. `off` is what is true.
            "--max-context",
            "off",
            "--max-concurrent",
            "1",
            "--idle-timeout",
            "0",
            "--context-scale",
            "1.0",
            # OptiQ turns --stream-experts on by itself when model_disk_bytes exceeds
            # 0.70 * total_RAM; identical weights then decode ~5x slower with nothing in
            # the artifact explaining it. Pin it off; never leave it auto.
            "--no-stream-experts",
            # The cache pin, under the same flag stock mlx-lm takes: optiq serve forwards
            # what it does not know to the mlx_lm.server underneath it.
            *prompt_cache_flags(cache_state),
        )

    def version_command(self) -> tuple[str, ...]:
        return ("optiq", "--version")

    def parse_version(self, output: str) -> str:
        """`optiq --version` answers `mlx-optiq, version 0.5.6`, not a bare `0.5.6`.

        The recorded string is what the grid's join guard compares across run directories to
        decide whether one runtime appeared at two versions, and it compares it exactly. The
        prose is uniform today, so the guard does not misfire -- but it is the runtime's
        phrasing rather than its version, and a release that reworded its own `--version`
        output would read as a version change and refuse a legal join. The version is the
        part that means something, so the version is what gets recorded.

        Anything that does not look like `..., version X` is passed through whole rather than
        guessed at: an unrecognised shape is better recorded verbatim than parsed into
        something that looks like a version and is not.
        """
        first = super().parse_version(output)
        _, separator, version = first.rpartition(", version ")
        return version.strip() if separator and version.strip() else first

    def model_id_candidates(self, artifact_dir: str, model_id: str) -> tuple[str, ...]:
        # OptiQ lists the absolute --model path. The :no-think variant is the one whose
        # streams put visible text in delta.content instead of delta.reasoning.
        forms = name_forms(artifact_dir)
        return _ordered(
            (f"{str(Path(os.path.abspath(artifact_dir)))}:no-think", model_id),
            tuple(f"{form}:no-think" for form in forms),
            tuple(f"optiq/{form}" for form in forms),
            forms,
        )


def vmlx_served_name(artifact_dir: str) -> str:
    """The name vMLX will expose these weights under.

    Ported from its ``_normalize_model_name`` (docs/runtimes/vmlx.md §9.5): an HF cache path
    collapses to ``org/repo``, any other path to its last two components, and a name with no
    separator is left alone. ``name_forms`` cannot spell the first of those, so the start
    command pins the served name to this rather than leaving readiness to a guess.
    """
    if os.path.sep not in artifact_dir and not artifact_dir.startswith("/"):
        return artifact_dir
    parts = artifact_dir.rstrip("/").split("/")
    for part in parts:
        if part.startswith("models--") and "--" in part[len("models--") :]:
            organization, _, repository = part[len("models--") :].partition("--")
            if organization and repository:
                return f"{organization}/{repository}"
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return parts[-1]


class Vmlx(Runtime):
    """The only runtime here that loads JANG, and the one whose real settings are 438
    environment variables no start command mentions.

    Deliberately absent from the command line: ``--api-key`` (unset means no authentication
    at all), ``--enable-disk-cache`` and ``--use-paged-cache`` (both off by default, both
    would make request 1 differ from requests 2+), and ``--kv-cache-quantization`` — omitting
    it selects production auto mode while passing it *disables* loader-level TurboQuant, so
    neither choice is neutral and this omission is the recorded one.
    """

    def start_command(
        self, artifact_dir: str, model_id: str, *, cache_state: str | None = None
    ) -> tuple[str, ...]:
        # The prefix cache is `--enable-prefix-cache`, default True (cli.py:3659) against
        # `--disable-prefix-cache` for the explicit off (cli.py:3667), and `on` pins the
        # enable rather than leaving the default to speak for itself.
        #
        # The block-disk tier stays off in BOTH states, and that is the single-variable rule
        # rather than tidiness: when neither block-disk flag is passed the engine turns the
        # SSD L2 on by itself the moment continuous batching and prefix caching are both
        # active (`_apply_paged_block_disk_default`, cli.py:661-701), writing to
        # ~/.cache/vmlx-engine/block-cache/<model_hash> -- state that survives restarts, is
        # not this run's, and would make an `on` cell's prefix possibly another run's. One
        # flag moves between the two states, and it is the prefix cache.
        prefix = ("--enable-prefix-cache",)
        if cache_state != CACHE_STATE_ON:
            prefix = ("--disable-prefix-cache",)
        # JIT is off unless a run asks for it. Left alone the artifact decides — JIT turns
        # itself on for a JANG affine bundle — so the default pins it off and every command
        # recorded before this toggle existed is byte-identical. The one run that measures JIT
        # as its variable (the vMLX JIT A/B) sets OHYESMLX_VMLX_ENABLE_JIT=1 to move this flag
        # and nothing else.
        jit = ("--no-jit",)
        if os.environ.get("OHYESMLX_VMLX_ENABLE_JIT") == "1":
            jit = ("--enable-jit",)
        return (
            "vmlx",
            "serve",
            # Positional and first, which is the one interface difference from every other
            # runtime here: there is no --model flag to pass.
            artifact_dir,
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
            # /v1/models answers to this, so readiness resolves a name this run chose
            # instead of one derived from the path. It leads model_id_candidates.
            "--served-model-name",
            vmlx_served_name(artifact_dir),
            # 8 is the default, and it batches tokens before the harness can count deltas.
            # Pinning the interval only means anything with batching on: without it the
            # runtime forces the interval to 1 and the command would say otherwise.
            "--stream-interval",
            "1",
            "--continuous-batching",
            "--max-num-seqs",
            "1",
            # MTP is decided by the artifact when left alone — it turns itself on for a bundle
            # carrying MTP heads — and it re-tunes its own depth mid-request. That would make
            # two cells of this runtime differ by something that is not the variable being
            # measured, which is the same hazard `jit` above defaults away from.
            *jit,
            "--disable-native-mtp",
            *prefix,
            # A cache hit is invisible to Observation, which carries no cached_tokens, so it
            # would publish as prefill throughput. The block disk cache also survives restarts
            # and is trimmed synchronously inside cold load, on a 22 GB cache that is not ours.
            "--disable-block-disk-cache",
        )

    def stop_command(self) -> tuple[str, ...]:
        # No stop subcommand exists, so SIGTERM to the spawned pid is the stop. Shutdown may
        # take up to ~10s to flush disk caches; _shutdown already waits that out.
        return ()

    def version_command(self) -> tuple[str, ...]:
        # `vmlx --version` is not a flag: the parser rejects it and exits 2. Read the engine's
        # own constant out of the shipped source instead of importing it — the import pulls in
        # the whole engine and measured 9.2s, which start() times as part of cold load, and
        # cold load is a published metric that must not carry harness overhead.
        return ("sed", "-n", VMLX_VERSION_SED, VMLX_ENGINE_INIT)

    def model_id_candidates(self, artifact_dir: str, model_id: str) -> tuple[str, ...]:
        # vMLX strips a path to its last two components, or to org/repo for an HF cache path.
        return _ordered((vmlx_served_name(artifact_dir), model_id), name_forms(artifact_dir))

    def api_key(self) -> str | None:
        # No --api-key means verify_api_key returns True for everyone, so measured requests
        # need no credential. The opposite of oMLX, where an unauthenticated request 401s.
        return None


RUNTIMES: dict[str, Runtime] = {
    "mlxlm": MlxLm(name="mlxlm", port=8081),
    "osaurus": Osaurus(name="osaurus", port=1337),
    "omlx": Omlx(name="omlx", port=8100),
    "optiq": Optiq(name="optiq", port=8080),
    "vmlx": Vmlx(name="vmlx", port=8000),
}
