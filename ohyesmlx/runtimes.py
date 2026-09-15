"""Uniform lifecycle over four heterogeneous local runtimes.

One dataclass per runtime behind one interface, because nothing else about them is alike:
``mlx_lm.server`` is Python, Osaurus is a Swift app behind a launcher, oMLX is a CLI shim
that execs an app binary, ``optiq serve`` is an MLX-optimised fork of mlx-lm. All four
speak OpenAI-compatible HTTP on loopback; beyond that, each names the same weights
differently and each starts with flags the others would choke on.

    handle = RUNTIMES["osaurus"].start(artifact_dir, "ornith-1.0-35b-jang_4m")
    ...measure...
    handle.stop()          # does not return until the port is free

**Readiness is not the port, and for ``mlx_lm.server`` it is not the model list either.**
On a load failure mlx-lm 0.31.3 binds 8081 and logs ``Starting httpd at 127.0.0.1 on port
8081...`` after the load thread has already raised, so a client POST connects and then
hangs forever with zero bytes received. Its ``/v1/models`` handler cannot be believed
either: it lists ``str(Path(--model).resolve())`` straight off disk, so the inventory
returns the right id even when the model was never loaded. Both signals are therefore
required -- the model id *and* a log with no load failure in it
(docs/research/2026-09-14-oq-portability-spike.md).

The flag tuples below are ported verbatim from LMRE's ``runtime_adapters``. They are not
defaults, they are pins, and each one costs something when it is left to the runtime.
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
LOG_TAIL_BYTES = 64 * 1024

LSOF = shutil.which("lsof") or "/usr/sbin/lsof"
LOGS_DIR = Path(__file__).resolve().parents[1] / "results" / "logs"

# Loopback-only key for a run-owned oMLX. Not a shared secret, and not user state.
OMLX_API_KEY = "ohyesmlx-local"
OMLX_CATALOG_TOKEN = "{OHYESMLX_OMLX_CATALOG}"
OMLX_CATALOG_DIRNAME = "catalog"
OMLX_BASE_DIRNAME = "base"
SAFE_CATALOG_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")

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
    """Take a runtime down and do not return until its port is free."""
    if stop_command:
        _run(stop_command, STOP_TIMEOUT_S)
    if _process_alive(pid):
        _signal_tree(pid, signal.SIGTERM)
        if not _await_exit(pid, TERM_GRACE_S):
            _signal_tree(pid, signal.SIGKILL)
            _await_exit(pid, KILL_GRACE_S)
    await_port_free(port)


@dataclass
class Handle:
    """One running runtime.

    The first six fields are the pinned interface. ``stop_command`` and ``scratch`` are
    lifecycle state the handle needs to release its own port, and carry the same defaults
    an interface-shaped construction would give them.
    """

    pid: int
    port: int
    base_url: str
    model_id: str
    version: str
    cold_load_s: float
    stop_command: tuple[str, ...] = ()
    scratch: str | None = None
    # The credential the runtime was started with. Measured requests must send it: oMLX
    # answers an unauthenticated /v1/chat/completions with 401, and the readiness probe
    # authenticating while the measurement did not is how that went unnoticed.
    api_key: str | None = None

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

    def start_command(self, artifact_dir: str, model_id: str) -> tuple[str, ...]:
        raise NotImplementedError

    def stop_command(self) -> tuple[str, ...]:
        return ()

    def version_command(self) -> tuple[str, ...]:
        return ()

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
        self, artifact_dir: str, model_id: str
    ) -> tuple[tuple[str, ...], str | None]:
        """The argv to spawn, plus any scratch tree a stop will have to remove."""
        return self.start_command(artifact_dir, model_id), None

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
        -- mlx-lm lists the ``--model`` path whether or not it ever loaded -- while a
        traceback cannot. Readiness needs both.
        """
        candidates = self.model_id_candidates(artifact_dir, model_id)
        deadline = _now() + timeout_s
        complaint = "no inventory yet"
        while True:
            error = log_load_error(_read_log(log_path))
            if error is not None:
                raise RuntimeStartError(
                    f"{self.name} failed to load: {error} (log: {log_path})"
                )
            if not _process_alive(pid):
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
                    return resolved
                complaint = f"inventory has {len(inventory)} models, none of them ours"
            if _now() >= deadline:
                raise RuntimeStartError(
                    f"{self.name} did not serve {candidates[0]!r} within "
                    f"{timeout_s:g}s ({complaint}; log: {log_path})"
                )
            _sleep(READY_POLL_S)

    def start(self, artifact_dir: str, model_id: str) -> Handle:
        """Spawn the runtime, hold until it can answer, and return its handle."""
        if not _port_is_free(self.port):
            raise RuntimeStartError(
                f"port {self.port} is already held by a listener this run did not "
                f"start; refusing to start {self.name} over it"
            )
        self.check_host_state()
        command, scratch = self.build_command(artifact_dir, model_id)
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
            stop_command=self.stop_command(),
            scratch=scratch,
            api_key=self.api_key(),
        )


class MlxLm(Runtime):
    """The control: stock mlx-lm's own server."""

    def start_command(self, artifact_dir: str, model_id: str) -> tuple[str, ...]:
        return ("python", "-m", "mlx_lm.server", "--model", artifact_dir, "--port", str(self.port))

    def version_command(self) -> tuple[str, ...]:
        return ("python", "-m", "mlx_lm", "--version")

    def model_id_candidates(self, artifact_dir: str, model_id: str) -> tuple[str, ...]:
        # mlx_lm.server appends str(Path(--model).resolve()) to /v1/models, and also
        # every mlx-looking repo in the HF cache.
        absolute = str(Path(os.path.abspath(artifact_dir)))
        return _ordered((absolute, model_id), name_forms(artifact_dir))


class Osaurus(Runtime):
    """The one runtime with no tuning flags to pin, and host settings instead."""

    def start_command(self, artifact_dir: str, model_id: str) -> tuple[str, ...]:
        # No model and no tuning on the command line: what a cell measures is decided by
        # ~/.osaurus/config, which check_host_state refuses to run away from.
        return ("osaurus", "serve", "--port", str(self.port), "--yes")

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
        # anything like the artifact's path.
        return _ordered((model_id,), name_forms(artifact_dir))

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

    def start_command(self, artifact_dir: str, model_id: str) -> tuple[str, ...]:
        return (
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
            "--no-cache",
        )

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
        self, artifact_dir: str, model_id: str
    ) -> tuple[tuple[str, ...], str | None]:
        scratch = create_omlx_scratch(artifact_dir, model_id)
        command = tuple(
            str(scratch.catalog) if part == OMLX_CATALOG_TOKEN else part
            for part in self.start_command(artifact_dir, model_id)
        )
        return command + (
            "--base-path",
            str(scratch.base),
            "--api-key",
            OMLX_API_KEY,
        ), str(scratch.root)


class Optiq(Runtime):
    """The fork whose expert-streaming heuristic silently costs 5x on large artifacts."""

    def start_command(self, artifact_dir: str, model_id: str) -> tuple[str, ...]:
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
            "--max-context",
            "8192",
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
        )

    def version_command(self) -> tuple[str, ...]:
        return ("optiq", "--version")

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


RUNTIMES: dict[str, Runtime] = {
    "mlxlm": MlxLm(name="mlxlm", port=8081),
    "osaurus": Osaurus(name="osaurus", port=1337),
    "omlx": Omlx(name="omlx", port=8100),
    "optiq": Optiq(name="optiq", port=8080),
}
