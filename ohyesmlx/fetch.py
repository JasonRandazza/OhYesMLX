"""Downloading one catalog model into the Hugging Face hub cache, and evicting it again.

Seam S5. All five engines see the HF cache layout without configuration (research
2026-10-30 §2.6), so a download writes what ``huggingface_hub`` would have written:
``models--<org>--<name>/blobs/<hash>``, ``snapshots/<revision>/<path>`` as a *relative*
symlink into ``blobs/``, and ``refs/main`` holding the revision.

The rules this module is built to keep, each from the plan's ACs:

- **Consent first, then a catalog id.** ``repo`` is looked up in the catalog the caller
  hands in; a caller never names a URL or a path, and ``plan`` refuses a hostile repo,
  revision, file path or hash before anything opens or is written (AC-1, AC-11).
- **A file's hash is the one the catalog pins.** An LFS file is verified by sha256 before
  it leaves ``blobs/<sha256>.incomplete``; a non-LFS file is verified by the git blob id
  the catalog carries. Both rules, and why the second is not a sha256, live at ``_verify``
  (AC-3).
- **Resume is a Range request.** A ``.incomplete`` of N bytes asks for ``bytes=N-``, a
  206's ``Content-Range`` must start at N, and a 200 means the server ignored the range
  and the file restarts from zero (AC-4). An expired signed URL (403/410) is resolved
  one more time and never in a loop.
- **Only https hosts under huggingface.co or hf.co**, on the request we build and on the
  URL the transport landed on (AC-5). No ``Authorization`` header is ever sent and
  ``HF_TOKEN`` / ``HF_ENDPOINT`` are never read (AC-14).
- **Nothing visible until everything is verified.** Blobs are completed first, then the
  snapshot links, then ``refs/main`` (AC-15). A failure leaves ``.incomplete`` residue
  and no link.
- **Evict removes only what this module created.** The ledger at the injected path lists,
  per repo, the blobs, links and directories *this* download created; ``evict`` removes
  those paths, reference-scans every snapshot symlink in the cache before deleting a
  blob, refuses an unlisted repo, and fails closed on a ledger it cannot read (AC-8,
  AC-12). A pre-existing blob is reused but never ledgered, so a user's own copy is
  never removed by evict.

Every side effect is a parameter: the transport (``open_url``), the hardware scan, sleep,
clock, emitter, cancellation probe, and the four filesystem locations. Tests run entirely
on ``tmp_path`` with a fake transport; this module never contacts a network in a test.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from ohyesmlx import app_support_dir, catalog, engines
from ohyesmlx.catalog import Model, disk_needed
from ohyesmlx.hardware import scan as _scan_hardware

# The one host a request may start at. Every hop after it must still be allowed.
HF_BASE = "https://huggingface.co"
ALLOWED_HOSTS = ("huggingface.co", "hf.co")

# The branch name under `refs/`, and the cache layout's two fixed directory names.
REF_NAME = "main"

# Bytes per read. Small enough that a cancel between chunks is noticed quickly and that
# a server sending more than the catalog size is caught before much of it is buffered.
CHUNK_SIZE = 256 * 1024

# AC-4: an in-flight progress event is emitted at most once this often on the injected
# clock, so a fast transfer cannot write one event per chunk (a few GB is tens of thousands
# of chunks).
PROGRESS_INTERVAL_S = 0.5

# AC-4: an in-flight event also needs the model-wide fraction to have advanced by at least
# this much (0.5%) since the last one, so a 2 GB download emits on the order of a few hundred
# events in total rather than one every half second however little moved.
PROGRESS_MIN_FRACTION = 0.005

# AC-10: four tries in total, exponential backoff between them, and a 429's Retry-After
# honoured up to a ceiling so a hostile header cannot park the job for a day.
MAX_ATTEMPTS = 4
BACKOFF_S = 0.5
RETRY_AFTER_CEILING_S = 60.0

# AC-10: every request carries a socket timeout. Injectable only through the transport;
# the default opener is the only place it is used.
TIMEOUT_S = 60.0

# AC-11's shape rules live in `catalog`; only this module's Content-Range parser is here.
_CONTENT_RANGE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")

# The app's own Application Support directory, asked of the package rather than restated.
_APP_SUPPORT = str(app_support_dir(engines.DEFAULT_ENV.home))
DEFAULT_LEDGER = os.path.join(_APP_SUPPORT, "fetched.json")
DEFAULT_LOG = os.path.join(_APP_SUPPORT, "fetch-log.jsonl")
DEFAULT_LOCK_DIR = os.path.join(_APP_SUPPORT, "locks")

# AC-7: one download at a time, across repos and processes. The lock's name is fixed so a
# second download -- of the same repo or any other -- is refused while one is running; a
# per-repo name would let five downloads compete for the same disk.
LOCK_NAME = "download.lock"


class HostNotAllowed(Exception):
    """A redirect left the two hosts this module will follow."""


class LedgerError(Exception):
    """The fetch ledger cannot be read, so nothing may be created or removed."""


@dataclass(frozen=True)
class PlannedFile:
    """One file's destination and verification data, derived by ``plan``."""

    path: str
    size: int
    sha256: str | None
    git_oid: str | None
    blob: str
    link: str
    url: str


@dataclass(frozen=True)
class Planned:
    """A pure description of where one catalog row would land; no I/O was done."""

    model: Model
    cache_dir: str
    repo_dir: str
    blobs_dir: str
    snapshot_dir: str
    refs_dir: str
    ref_path: str
    files: list[PlannedFile]
    size_bytes: int


def default_cache_dir(env=None) -> str:
    """The hub cache to use when the caller did not inject one.

    ``HF_HUB_CACHE`` wins, then ``~/.cache/huggingface/hub`` (AC-2). ``HF_TOKEN`` and
    ``HF_ENDPOINT`` are deliberately absent: this downloader is anonymous and never
    talks to a mirror (AC-14).
    """
    env = os.environ if env is None else env
    configured = env.get("HF_HUB_CACHE")
    if configured:
        return configured
    home = env.get("HOME") or os.path.expanduser("~")
    return os.path.join(home, ".cache", "huggingface", "hub")


def host_allowed(host: str | None) -> bool:
    """Whether *host* is huggingface.co, hf.co, or a subdomain of either."""
    if not host:
        return False
    host = host.lower()
    return any(host == base or host.endswith("." + base) for base in ALLOWED_HOSTS)


def url_allowed(url: str | None) -> bool:
    """AC-5: https, on an allowed host. The one definition the redirect guard asks."""
    if not url:
        return False
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    return parts.scheme == "https" and host_allowed(parts.hostname)


def _check_inside(repo: str, destination: str, container: str) -> None:
    """Refuse a destination that does not resolve inside the directory it belongs to."""
    root = os.path.abspath(container)
    resolved = os.path.abspath(destination)
    if os.path.commonpath([root, resolved]) != root:
        raise ValueError(f"{repo}: {destination!r} resolves outside {container!r}")


def plan(model: Model, cache_dir: str | None = None) -> Planned:
    """Where *model* would land under *cache_dir*, with every name checked (AC-11).

    Pure: no directory is created, nothing is hashed, no request is built beyond the
    string. A hostile literal in the catalog -- a repo that is not one org/name pair, a
    revision that is not a commit, a path with ``..``, a hash that is not a hash -- raises
    ``ValueError`` here, before any caller can open a socket or write a file.
    """
    repo = model.repo
    if not isinstance(repo, str) or not catalog._REPO.match(repo):
        raise ValueError(f"repo {repo!r} is not an org/name id")
    if not isinstance(model.revision, str) or not catalog._COMMIT.match(model.revision):
        raise ValueError(f"{repo}: revision {model.revision!r} is not a 40-hex commit")

    root = cache_dir or default_cache_dir()
    org, name = repo.split("/")
    repo_dir = os.path.join(root, f"models--{org}--{name}")
    blobs_dir = os.path.join(repo_dir, "blobs")
    snapshot_dir = os.path.join(repo_dir, "snapshots", model.revision)
    refs_dir = os.path.join(repo_dir, "refs")
    ref_path = os.path.join(refs_dir, REF_NAME)

    files: list[PlannedFile] = []
    for item in model.files:
        catalog.check_path(repo, item.path)
        if item.sha256 is not None and item.git_oid is not None:
            raise ValueError(f"{repo}: {item.path!r} carries both a sha256 and a git_oid")
        if item.sha256 is not None:
            if not catalog._SHA256.match(item.sha256):
                raise ValueError(f"{repo}: {item.path!r} sha256 is not 64 lowercase hex")
            key = item.sha256
        elif item.git_oid is not None:
            if not catalog._COMMIT.match(item.git_oid):
                raise ValueError(f"{repo}: {item.path!r} git_oid is not 40 lowercase hex")
            key = item.git_oid
        else:
            raise ValueError(f"{repo}: {item.path!r} carries neither a sha256 nor a git_oid")
        blob = os.path.join(blobs_dir, key)
        link = os.path.join(snapshot_dir, item.path)
        _check_inside(repo, blob, blobs_dir)
        _check_inside(repo, link, snapshot_dir)
        url = (
            f"{HF_BASE}/{repo}/resolve/{model.revision}/"
            f"{urllib.parse.quote(item.path, safe='/')}"
        )
        files.append(
            PlannedFile(
                path=item.path,
                size=item.size,
                sha256=item.sha256,
                git_oid=item.git_oid,
                blob=blob,
                link=link,
                url=url,
            )
        )
    return Planned(
        model=model,
        cache_dir=root,
        repo_dir=repo_dir,
        blobs_dir=blobs_dir,
        snapshot_dir=snapshot_dir,
        refs_dir=refs_dir,
        ref_path=ref_path,
        files=files,
        size_bytes=sum(item.size for item in model.files),
    )


def downloaded(model: Model, cache_dir: str | None = None) -> bool:
    """Whether every file ``plan`` names is already in the cache, by size and link only (AC-1).

    This answers a recommendation request, where a multi-GB file cannot be hashed: each
    snapshot link must be present and resolve to a file of the catalog's size, and the blob
    it resolves into must be there at that size too. That is the evidence a resume already
    trusts before it asks for a byte -- a file of the right size but the wrong bytes reads
    as downloaded here, which is the price of the cheap check and why ``_verify`` still runs
    after a transfer. Nothing is written and nothing is hashed; a ``.incomplete`` file alone
    is not a download, because the snapshot link is written only after every file verifies
    (AC-15). ``plan``'s ``ValueError`` for a hostile name propagates: the caller is asking
    about a catalog row, and a name that cannot be planned is not a name this answers for.
    """
    planned = plan(model, cache_dir)
    for planned_file in planned.files:
        try:
            if not os.path.isfile(planned_file.link):
                return False
            if os.path.getsize(planned_file.link) != planned_file.size:
                return False
            if not os.path.isfile(planned_file.blob):
                return False
            if os.path.getsize(planned_file.blob) != planned_file.size:
                return False
        except OSError:
            return False
    return True


# ---------------------------------------------------------------------------
# The ledger: what this module created, and nothing else (AC-7, AC-8, AC-12)
# ---------------------------------------------------------------------------

_LEDGER_LISTS = ("created_blobs", "created_links", "created_dirs")


def _ledger_load(path, *, missing_ok: bool) -> dict:
    """Read and validate the ledger; a missing or ill-shaped file raises LedgerError."""
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except FileNotFoundError as error:
        if missing_ok:
            return {"repos": {}}
        raise LedgerError(f"the fetch ledger {path} does not exist") from error
    except OSError as error:
        raise LedgerError(f"cannot read the fetch ledger {path}: {error}") from error
    try:
        payload = json.loads(text)
    except ValueError as error:
        raise LedgerError(f"the fetch ledger {path} is not JSON: {error}") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("repos"), dict):
        raise LedgerError(f"the fetch ledger {path} holds no 'repos' object")
    for repo, entry in payload["repos"].items():
        if not isinstance(entry, dict):
            raise LedgerError(f"the fetch ledger {path}: entry {repo!r} is not an object")
        for key in _LEDGER_LISTS:
            value = entry.get(key)
            if not isinstance(value, list) or not all(isinstance(p, str) for p in value):
                raise LedgerError(
                    f"the fetch ledger {path}: entry {repo!r} field {key!r} "
                    "must be a list of paths"
                )
        if not isinstance(entry.get("revision"), str):
            raise LedgerError(f"the fetch ledger {path}: entry {repo!r} has no revision")
        if not isinstance(entry.get("bytes"), int) or isinstance(entry.get("bytes"), bool):
            raise LedgerError(f"the fetch ledger {path}: entry {repo!r} has no byte count")
        if not isinstance(entry.get("time"), (int, float)) or isinstance(entry.get("time"), bool):
            raise LedgerError(f"the fetch ledger {path}: entry {repo!r} has no time")
    return payload


def _ledger_save(path, payload: dict) -> None:
    """Write the ledger atomically: a reader never sees half a file."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    temporary = f"{path}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


# ---------------------------------------------------------------------------
# The lock file: one download at a time, across repos and processes (AC-7, AC-18)
# ---------------------------------------------------------------------------


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def _acquire_lock(path: str) -> bool:
    """Create the lock file, reclaiming one whose pid is gone; False means busy."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    for _ in range(2):
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            try:
                with open(path, encoding="utf-8") as handle:
                    pid = int(handle.read().strip())
            except (OSError, ValueError):
                pid = None
            if pid is not None and _pid_alive(pid):
                return False
            try:
                os.remove(path)
            except OSError:
                return False
            continue
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
        return True
    return False


def _release_lock(path: str) -> None:
    """Remove the lock only while it still names this process."""
    try:
        with open(path, encoding="utf-8") as handle:
            owner = int(handle.read().strip())
    except (OSError, ValueError):
        return
    if owner != os.getpid():
        return
    try:
        os.remove(path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Events and the local log
# ---------------------------------------------------------------------------


def _emitter(emit, log_path, *, repo: str, confirmed: bool):
    """The pinned job-event shape (`engines._job_event`), logged locally before it is emitted.

    The log line is ``engines._append_install_log``'s, asked rather than copied: one
    append-only local JSONL record of what this app did, never uploaded (AC-7).
    """
    state = {"seq": 0}

    def send(kind, message, *, fraction=None, payload=None):
        state["seq"] += 1
        event = engines._job_event(state["seq"], kind, message, fraction, payload)
        engines._append_install_log(
            log_path,
            engine=repo,
            confirmed=confirmed,
            kind=kind,
            step=None,
            exit_code=None,
            code=(payload or {}).get("code"),
        )
        emit(event)
        return event

    return send


def _refuse(send, code: str, message: str, **payload) -> bool:
    """One refusal, and the end of its stream: an ``error`` never stands alone."""
    send("error", message, payload={"code": code, **payload})
    send("done", "fetch ended")
    return False


# ---------------------------------------------------------------------------
# HTTP details asked by the downloader
# ---------------------------------------------------------------------------


class _GuardedRedirects(urllib.request.HTTPRedirectHandler):
    """AC-5's allowlist applied to every hop, not only to the final response."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not url_allowed(newurl):
            raise HostNotAllowed(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _real_open(url: str, headers: dict):
    """The production transport: a GET that follows only allowlisted redirects."""
    request = urllib.request.Request(url, headers=dict(headers or {}), method="GET")
    opener = urllib.request.build_opener(_GuardedRedirects)
    try:
        return opener.open(request, timeout=TIMEOUT_S)
    except urllib.error.HTTPError as error:
        # urllib raises on every non-2xx status; the error *is* the response, with its
        # own status, headers and body, which is what the caller wants to read.
        return error
    except urllib.error.URLError as error:
        # A refusal raised inside the redirect handler must reach the caller as itself,
        # not as a connection failure the retry loop would try four times.
        if isinstance(error.reason, HostNotAllowed):
            raise error.reason
        raise


def _print_event(event: dict) -> None:
    print(json.dumps(event), flush=True)


def _never_cancelled() -> bool:
    return False


def _response_url(response) -> str | None:
    url = getattr(response, "url", None)
    if url:
        return url
    geturl = getattr(response, "geturl", None)
    return geturl() if geturl is not None else None


def _status(response) -> int:
    for name in ("status", "code"):
        value = getattr(response, name, None)
        if isinstance(value, int):
            return value
    return -1


def _header(response, name: str) -> str | None:
    headers = getattr(response, "headers", None) or {}
    value = headers.get(name)
    if value is not None:
        return value
    items = getattr(headers, "items", None)
    if items is None:
        return None
    for key, candidate in items():
        if key.lower() == name.lower():
            return candidate
    return None


def _integer_header(response, name: str) -> int | None:
    value = _header(response, name)
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _close(response) -> None:
    close = getattr(response, "close", None)
    if close is not None:
        try:
            close()
        except OSError:
            pass


def _retry_delay(response, attempts: int) -> float:
    """Backoff for one transient failure: Retry-After for a 429, else 0.5, 1, 2 s."""
    if _status(response) == 429:
        value = _header(response, "Retry-After")
        try:
            seconds = float(str(value).strip())
        except (TypeError, ValueError):
            return BACKOFF_S * (2**attempts)
        return min(max(seconds, 0.0), RETRY_AFTER_CEILING_S)
    return BACKOFF_S * (2**attempts)


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------


def _inside(path: str, root: str) -> bool:
    real_root = os.path.realpath(root)
    real = os.path.realpath(path)
    try:
        return os.path.commonpath([real_root, real]) == real_root
    except ValueError:
        return False


def _partial_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_blob_sha1(path: str, size: int) -> str:
    """The sha1 a git blob id names: ``sha1("blob <size>\\0" + bytes)``, streamed."""
    digest = hashlib.sha1(b"blob %d\x00" % size)
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify(planned_file: PlannedFile, path: str) -> bool:
    """Whether *path* is the file the catalog pins.

    An LFS file is checked by sha256. A non-LFS file's catalog id is a git blob oid -- a
    sha1 over ``"blob <len>\\0" + bytes`` rather than over the bytes -- so it is checked by
    recomputing exactly that and comparing it to ``git_oid``. The CDN's ``ETag`` is the xet
    hash rather than the file's (research 2026-10-30 §3.4). This is the one place the two
    verification rules and their rationale live.
    """
    try:
        if os.path.getsize(path) != planned_file.size:
            return False
    except OSError:
        return False
    if planned_file.sha256 is not None:
        return _sha256_file(path) == planned_file.sha256
    return _git_blob_sha1(path, planned_file.size) == planned_file.git_oid


def _make_dirs(path: str, created: list[str], stop: str) -> None:
    """Create *path* and its missing parents above *stop*, recording the new ones."""
    missing: list[str] = []
    current = path
    while current and current != stop and not os.path.isdir(current):
        missing.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    os.makedirs(path, exist_ok=True)
    created.extend(reversed(missing))


def _referenced_blobs(cache_dir: str) -> set[str]:
    """Every blob any snapshot symlink in the whole cache resolves to (AC-8)."""
    referenced: set[str] = set()
    try:
        names = sorted(os.listdir(cache_dir))
    except OSError:
        return referenced
    for name in names:
        if not name.startswith("models--"):
            continue
        snapshots = os.path.join(cache_dir, name, "snapshots")
        for base, dirs, files in os.walk(snapshots, followlinks=False):
            for entry in dirs + files:
                path = os.path.join(base, entry)
                if os.path.islink(path):
                    referenced.add(os.path.realpath(path))
    return referenced


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


def download(
    repo: str,
    confirmed: bool,
    *,
    models=None,
    cache_dir: str | None = None,
    ledger_path=DEFAULT_LEDGER,
    log_path=DEFAULT_LOG,
    lock_dir=DEFAULT_LOCK_DIR,
    open_url=_real_open,
    hardware=_scan_hardware,
    sleep=time.sleep,
    clock=time.time,
    emit=_print_event,
    cancel=_never_cancelled,
) -> bool:
    """Put catalog model *repo* into the hub cache, resumably and verified.

    The order of the guards is the order the refusals mean: consent, then a catalog id,
    then the name shapes, then the cross-process lock, then the ledger, then "already
    present", then disk. Nothing is opened before consent, and no byte is requested
    before the disk guard has accepted.
    """
    send = _emitter(emit, log_path, repo=repo, confirmed=confirmed)

    if not confirmed:
        return _refuse(
            send, "consent_required", f"consent was not given; nothing of {repo} was downloaded"
        )

    available = catalog.load() if models is None else models
    model = next((entry for entry in available if entry.repo == repo), None)
    if model is None:
        return _refuse(
            send, "unknown_repo", f"{repo} is not a catalog model; nothing was downloaded"
        )

    try:
        planned = plan(model, cache_dir)
    except ValueError as error:
        return _refuse(send, "bad_name", str(error))

    lock_path = os.path.join(lock_dir, LOCK_NAME)
    if not _acquire_lock(lock_path):
        return _refuse(send, "busy", "another download is already running")

    created: dict[str, list[str]] = {"blobs": [], "links": [], "dirs": []}
    try:
        return _download(
            planned, send, created, ledger_path, open_url, hardware, sleep, clock, cancel
        )
    finally:
        if any(created.values()):
            _record(ledger_path, planned, created, clock, send)
        _release_lock(lock_path)


def _record(ledger_path, planned: Planned, created: dict, clock, send) -> None:
    """Merge what this call created into the ledger; never drop a previous entry."""
    try:
        ledger = _ledger_load(ledger_path, missing_ok=True)
    except LedgerError as error:
        send("log", f"the fetch ledger was not updated: {error}")
        return
    repo = planned.model.repo
    entry = ledger["repos"].get(repo) or {
        "created_blobs": [],
        "created_links": [],
        "created_dirs": [],
        "revision": planned.model.revision,
        "time": 0.0,
        "bytes": planned.model.size_bytes,
    }
    for key in _LEDGER_LISTS:
        target = entry[key]
        for path in created[key[len("created_"):]]:
            if path not in target:
                target.append(path)
    entry["revision"] = planned.model.revision
    entry["bytes"] = planned.model.size_bytes
    entry["time"] = clock()
    ledger["repos"][repo] = entry
    try:
        _ledger_save(ledger_path, ledger)
    except OSError as error:
        send("log", f"the fetch ledger {ledger_path} was not written: {error}")


def _download(
    planned: Planned, send, created, ledger_path, open_url, hardware, sleep, clock, cancel
) -> bool:
    """The body of ``download`` once the lock is held; returns True on success."""
    repo = planned.model.repo
    revision = planned.model.revision

    try:
        _ledger_load(ledger_path, missing_ok=True)
    except LedgerError as error:
        return _refuse(send, "ledger_unreadable", str(error))

    send("log", f"{repo} at {revision}: {len(planned.files)} files, {planned.size_bytes} bytes")

    def cancelled() -> bool:
        send(
            "error",
            f"the download of {repo} was cancelled; the partial file is kept for a resume",
            payload={"code": "cancelled"},
        )
        send("done", "download cancelled")
        return False

    def size_mismatch(message: str, *, path: str, remove: str | None = None) -> bool:
        if remove is not None:
            _remove(remove)
        return _refuse(send, "size_mismatch", message, path=path)

    # --- what is already here? A blob is verified before it is reused (AC-12). ---
    present: dict[str, bool] = {}
    for planned_file in planned.files:
        blob = planned_file.blob
        if os.path.islink(blob):
            return _refuse(
                send,
                "integrity_failed",
                f"{blob} is a symlink; nothing was written through it",
                path=blob,
            )
        if os.path.exists(blob):
            if not os.path.isfile(blob) or not _verify(planned_file, blob):
                return _refuse(
                    send,
                    "integrity_failed",
                    f"the cache already holds {blob} and it does not match the catalog; "
                    "nothing was overwritten",
                    path=blob,
                )
            present[planned_file.path] = True
        else:
            present[planned_file.path] = False

    def remaining(planned_file: PlannedFile) -> int:
        if present[planned_file.path]:
            return 0
        return max(0, planned_file.size - _partial_size(planned_file.blob + ".incomplete"))

    # --- AC-6 / AC-16: missing bytes x the catalog's disk margin, before any request. ---
    missing_bytes = sum(remaining(planned_file) for planned_file in planned.files)
    needed = disk_needed(missing_bytes)
    free = hardware().disk_free_bytes
    if free < needed:
        return _refuse(
            send,
            "low_disk",
            f"{free} bytes free is less than the {needed} bytes this download needs",
        )

    def make_dirs(path: str, stop: str) -> None:
        _make_dirs(path, created["dirs"], stop)

    make_dirs(planned.repo_dir, planned.cache_dir)
    make_dirs(planned.blobs_dir, planned.repo_dir)
    if not _inside(planned.blobs_dir, planned.repo_dir):
        return _refuse(
            send,
            "bad_name",
            f"{planned.blobs_dir} resolves outside {planned.repo_dir}",
        )

    # --- AC-15: links only after every file is verified; refs/main last. ---
    def link_all() -> bool:
        make_dirs(planned.snapshot_dir, planned.repo_dir)
        if not _inside(planned.snapshot_dir, planned.repo_dir):
            return _refuse(
                send,
                "bad_name",
                f"{planned.snapshot_dir} resolves outside {planned.repo_dir}",
            )
        for planned_file in planned.files:
            parent = os.path.dirname(planned_file.link)
            make_dirs(parent, planned.repo_dir)
            if not _inside(parent, planned.snapshot_dir):
                return _refuse(
                    send,
                    "bad_name",
                    f"{planned_file.link} resolves outside {planned.snapshot_dir}",
                )
            if os.path.lexists(planned_file.link):
                if os.path.islink(planned_file.link) and os.path.realpath(
                    planned_file.link
                ) == os.path.realpath(planned_file.blob):
                    continue
                return _refuse(
                    send,
                    "integrity_failed",
                    f"{planned_file.link} already exists and does not point at "
                    f"{planned_file.blob}; nothing was overwritten",
                    path=planned_file.link,
                )
            os.symlink(os.path.relpath(planned_file.blob, parent), planned_file.link)
            created["links"].append(planned_file.link)
        make_dirs(planned.refs_dir, planned.repo_dir)
        if not os.path.lexists(planned.ref_path):
            with open(planned.ref_path, "w", encoding="utf-8") as handle:
                handle.write(revision + "\n")
            created["links"].append(planned.ref_path)
        return True

    if all(present.values()):
        if cancel():
            return cancelled()
        if not link_all():
            return False
        send(
            "result",
            f"{repo} is already in the cache; nothing was downloaded",
            payload={"status": "already_present", "repo": repo, "bytes": 0},
        )
        send("done", "already present")
        return True

    # --- the files themselves ---
    def finish(planned_file: PlannedFile, incomplete: str) -> bool:
        if not _verify(planned_file, incomplete):
            _remove(incomplete)
            checked = "sha256" if planned_file.sha256 is not None else "git_oid"
            return _refuse(
                send,
                "integrity_failed",
                f"{planned_file.path} did not match the catalog's {checked}; "
                "the partial file was removed and nothing was linked",
                path=planned_file.blob,
            )
        os.replace(incomplete, planned_file.blob)
        created["blobs"].append(planned_file.blob)
        return True

    def _fetch_file(planned_file: PlannedFile) -> bool:
        incomplete = planned_file.blob + ".incomplete"
        if os.path.islink(incomplete):
            return _refuse(
                send,
                "integrity_failed",
                f"{incomplete} is a symlink; nothing was written through it",
                path=planned_file.blob,
            )
        reresolved = False
        attempts = 0
        # AC-4: the in-flight progress this file has already reported, kept across a retry
        # so an emitted fraction never goes backwards -- a 200 to a Range request restarts
        # the write at zero.
        last_progress = None
        last_fraction = 0.0
        while True:
            if cancel():
                return cancelled()
            have = _partial_size(incomplete)
            if have > planned_file.size:
                return size_mismatch(
                    f"{incomplete} holds {have} bytes, more than the "
                    f"{planned_file.size} the catalog pins",
                    path=planned_file.blob,
                    remove=incomplete,
                )
            if have == planned_file.size:
                return finish(planned_file, incomplete)
            headers = {"Range": f"bytes={have}-"} if have else {}
            try:
                response = open_url(planned_file.url, headers)
            except HostNotAllowed as error:
                return _refuse(
                    send,
                    "host_not_allowed",
                    f"refusing to follow a redirect to {error}",
                )
            except OSError as error:
                if attempts + 1 >= MAX_ATTEMPTS:
                    return _refuse(
                        send,
                        "http_error",
                        f"{planned_file.path}: the connection failed {MAX_ATTEMPTS} times "
                        f"(last: {error})",
                    )
                sleep(BACKOFF_S * (2**attempts))
                attempts += 1
                continue
            try:
                landed = _response_url(response)
                if not url_allowed(landed):
                    return _refuse(
                        send,
                        "host_not_allowed",
                        f"refusing to read {planned_file.path} from {landed}: only https "
                        f"URLs on {', '.join(ALLOWED_HOSTS)} are allowed",
                    )
                status = _status(response)
                if status == 401:
                    gated = (_header(response, "X-Error-Code") or "").strip() == "GatedRepo"
                    detail = (
                        "the repository is gated; a token would be required"
                        if gated
                        else "no such repository or file"
                    )
                    return _refuse(
                        send,
                        "gated" if gated else "not_found",
                        f"{planned_file.path}: the server answered 401 ({detail})",
                    )
                if status == 404:
                    return _refuse(
                        send,
                        "not_found",
                        f"{planned_file.path}: the server answered 404; no such file at "
                        f"{revision}",
                    )
                if status in (403, 410):
                    if not reresolved:
                        reresolved = True
                        send(
                            "log",
                            f"the signed URL for {planned_file.path} has expired "
                            f"(HTTP {status}); resolving once more",
                        )
                        continue
                    return _refuse(
                        send,
                        "http_error",
                        f"{planned_file.path}: the server answered HTTP {status} again "
                        "after a fresh resolve",
                    )
                if status == 416:
                    return size_mismatch(
                        f"{planned_file.path}: the server refused the {have}-byte range "
                        f"(HTTP 416) but the catalog pins {planned_file.size} bytes",
                        path=planned_file.blob,
                        remove=incomplete,
                    )
                if status == 429 or 500 <= status <= 599:
                    if attempts + 1 >= MAX_ATTEMPTS:
                        return _refuse(
                            send,
                            "http_error",
                            f"{planned_file.path}: the server answered HTTP {status} "
                            f"{MAX_ATTEMPTS} times",
                        )
                    sleep(_retry_delay(response, attempts))
                    attempts += 1
                    continue
                if status not in (200, 206):
                    return _refuse(
                        send,
                        "http_error",
                        f"{planned_file.path}: the server answered HTTP {status}",
                    )

                length = _integer_header(response, "Content-Length")
                if status == 206:
                    match = _CONTENT_RANGE.match(
                        (_header(response, "Content-Range") or "").strip()
                    )
                    if match is None:
                        return size_mismatch(
                            f"{planned_file.path}: a 206 without a usable Content-Range",
                            path=planned_file.blob,
                            remove=incomplete,
                        )
                    start, end, total = (int(value) for value in match.groups())
                    if (
                        start != have
                        or end < start
                        or total != planned_file.size
                        or (length is not None and length != end - start + 1)
                    ):
                        return size_mismatch(
                            f"{planned_file.path}: the server answered bytes "
                            f"{start}-{end}/{total} for a request starting at {have} of "
                            f"{planned_file.size}",
                            path=planned_file.blob,
                            remove=incomplete,
                        )
                elif length is not None and length > planned_file.size:
                    return size_mismatch(
                        f"{planned_file.path}: the server claims {length} bytes and the "
                        f"catalog pins {planned_file.size}",
                        path=planned_file.blob,
                        remove=incomplete,
                    )

                if status == 200 and have:
                    send(
                        "log",
                        f"the server ignored the {have}-byte resume for "
                        f"{planned_file.path}; restarting from zero",
                    )
                mode = "ab" if status == 206 and have else "wb"
                written = have if mode == "ab" else 0
                over = False
                with open(incomplete, mode) as handle:
                    while True:
                        if cancel():
                            return cancelled()
                        chunk = response.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        if written + len(chunk) > planned_file.size:
                            over = True
                            break
                        handle.write(chunk)
                        written += len(chunk)
                        # AC-4: bytes in flight, by byte: a multi-GB file is one file, and a
                        # per-file event left the bar at 0% for minutes. The fraction is the
                        # whole model's -- files finished plus this file's bytes so far --
                        # and the two gates keep a fast disk from emitting per chunk while
                        # still moving a slow transfer's bar.
                        if written < planned_file.size:
                            now = clock()
                            fraction = (accounted + written) / planned.size_bytes
                            if fraction >= last_fraction + PROGRESS_MIN_FRACTION and (
                                last_progress is None
                                or now - last_progress >= PROGRESS_INTERVAL_S
                            ):
                                last_progress = now
                                last_fraction = fraction
                                send(
                                    "progress",
                                    f"{planned_file.path}: {written} of "
                                    f"{planned_file.size} bytes",
                                    fraction=fraction,
                                    payload={
                                        "path": planned_file.path,
                                        "bytes_done": accounted + written,
                                        "bytes_total": planned.size_bytes,
                                    },
                                )
                if over:
                    return size_mismatch(
                        f"{planned_file.path}: the server sent more than the "
                        f"{planned_file.size} bytes the catalog pins",
                        path=planned_file.blob,
                        remove=incomplete,
                    )
                if written == planned_file.size:
                    return finish(planned_file, incomplete)
                if attempts + 1 >= MAX_ATTEMPTS:
                    return size_mismatch(
                        f"{planned_file.path}: the transfer ended at {written} of "
                        f"{planned_file.size} bytes",
                        path=planned_file.blob,
                        remove=incomplete,
                    )
                sleep(BACKOFF_S * (2**attempts))
                attempts += 1
            finally:
                _close(response)

    def fetch_file(planned_file: PlannedFile) -> bool:
        """Run one file's transfer, keeping its residue on the ledger when it fails.

        AC-15: a leftover ``.incomplete`` is the only residue a failed transfer leaves,
        and evict removes it -- which it can only do for a path the ledger names.
        """
        if _fetch_file(planned_file):
            return True
        residue = planned_file.blob + ".incomplete"
        if os.path.lexists(residue) and residue not in created["blobs"]:
            created["blobs"].append(residue)
        return False

    accounted = sum(item.size for item in planned.files if present[item.path])
    for planned_file in planned.files:
        if cancel():
            return cancelled()
        if present[planned_file.path]:
            send("log", f"reusing {planned_file.blob} ({planned_file.size} bytes already present)")
            continue
        need = remaining(planned_file)
        required = disk_needed(need)
        free = hardware().disk_free_bytes
        if free < required:
            return _refuse(
                send,
                "low_disk",
                f"{free} bytes free is less than the {required} bytes {planned_file.path} "
                "still needs",
            )
        if not fetch_file(planned_file):
            return False
        accounted += planned_file.size
        fraction = accounted / planned.size_bytes if planned.size_bytes else 1.0
        send(
            "progress",
            f"{planned_file.path}: {planned_file.size} bytes",
            fraction=fraction,
            payload={"path": planned_file.path, "bytes": planned_file.size},
        )

    if cancel():
        return cancelled()
    if not link_all():
        return False
    written = sum(item.size for item in planned.files if not present[item.path])
    send(
        "result",
        f"downloaded {written} bytes for {repo} at {revision}",
        payload={"status": "downloaded", "repo": repo, "bytes": written},
    )
    send("done", "download finished")
    return True


# ---------------------------------------------------------------------------
# Evict
# ---------------------------------------------------------------------------


def evict(
    repo: str,
    confirmed: bool,
    *,
    cache_dir: str | None = None,
    ledger_path=DEFAULT_LEDGER,
    log_path=DEFAULT_LOG,
    emit=_print_event,
) -> bool:
    """Remove exactly the paths the ledger records for *repo* (AC-8).

    A repo the ledger does not list is refused, and a ledger that cannot be read makes
    this refuse everything: an eviction that guessed would be the one operation in this
    app capable of deleting a file nobody asked it to touch.
    """
    send = _emitter(emit, log_path, repo=repo, confirmed=confirmed)

    if not confirmed:
        return _refuse(
            send, "consent_required", f"consent was not given; nothing of {repo} was removed"
        )
    if not isinstance(repo, str) or not catalog._REPO.match(repo):
        return _refuse(send, "bad_name", f"repo {repo!r} is not an org/name id")

    try:
        ledger = _ledger_load(ledger_path, missing_ok=False)
    except LedgerError as error:
        return _refuse(send, "ledger_unreadable", str(error))

    entry = ledger["repos"].get(repo)
    if entry is None:
        return _refuse(
            send, "unknown_repo", f"{repo} is not in the fetch ledger; nothing was removed"
        )

    root = cache_dir or default_cache_dir()
    for key in _LEDGER_LISTS:
        for path in entry[key]:
            if not _inside(path, root):
                return _refuse(
                    send,
                    "ledger_unreadable",
                    f"the fetch ledger lists {path}, which resolves outside {root}; "
                    "nothing was removed",
                )

    removed: list[str] = []
    kept: list[str] = []

    # Links first: the reference scan below then reads the cache without them.
    for path in entry["created_links"]:
        if not (os.path.islink(path) or os.path.lexists(path)):
            continue
        try:
            os.remove(path)
            removed.append(path)
        except OSError as error:
            kept.append(path)
            send("log", f"could not remove {path}: {error}")

    referenced = _referenced_blobs(root)
    for path in entry["created_blobs"]:
        residue = path + ".incomplete"
        if _inside(residue, root) and os.path.lexists(residue):
            _remove(residue)
            removed.append(residue)
        if not os.path.exists(path):
            continue
        if os.path.realpath(path) in referenced:
            kept.append(path)
            send("log", f"keeping {path}: a snapshot elsewhere still references it")
            continue
        try:
            os.remove(path)
            removed.append(path)
        except OSError as error:
            kept.append(path)
            send("log", f"could not remove {path}: {error}")

    # Directories deepest-first, and only when their creation path is now empty.
    for path in reversed(entry["created_dirs"]):
        if not os.path.isdir(path):
            continue
        try:
            os.rmdir(path)
            removed.append(path)
        except OSError:
            kept.append(path)
            send("log", f"keeping {path}: it is not empty")

    kept_set = set(kept)
    for key in _LEDGER_LISTS:
        entry[key] = [path for path in entry[key] if path in kept_set]
    if any(entry[key] for key in _LEDGER_LISTS):
        ledger["repos"][repo] = entry
    else:
        del ledger["repos"][repo]
    try:
        _ledger_save(ledger_path, ledger)
    except OSError as error:
        send("log", f"the fetch ledger {ledger_path} was not written: {error}")

    send(
        "result",
        f"removed {len(removed)} paths for {repo}",
        payload={"repo": repo, "removed": removed, "kept": kept},
    )
    send("done", "eviction finished")
    return True
