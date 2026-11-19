"""Phase 5.5 items 4, 6 and 7: backend cleanup.

**Item 4 (AC-1):** a malformed ``lab-paths.json`` no longer breaks a ``ps``/``lsof`` helper
call. ``_engine_command`` reads the lab files for every absolute program so it can prefix a
lab directory to PATH; a system helper never needs that prefix, and reading the files for it
let one broken file disable stopping and recovery for every engine (S5-F10's real gap: its
test injects ``_engine_env``, so ``_engine_command``'s own ``_lab_paths()`` call still ran).
An engine START still reads them, so a broken lab file still refuses a start.

**Item 6 (AC-2):** a cancel takes effect during the hash of one large file, not only between
files. The hash raises a private ``_Cancelled``; ``_download`` turns that into its existing
``cancelled()`` event pair, and ``finish`` keeps the partial for a resume.

**Item 7 (AC-3):** a legacy bare-pid ``download.lock`` whose pid has been recycled (now
another program) no longer wedges every future download.

Nothing here starts a server, loads a model or downloads a byte: every path is a scratch
path, and the only processes run are ``lsof`` and ``ps`` through their real positions.
"""

from __future__ import annotations

import builtins
import hashlib
import json
import os
import socket

import pytest

from ohyesmlx import engines, fetch, runtimes
from ohyesmlx.catalog import Model, ModelFile

ENGINES = ("mlxlm", "osaurus", "omlx", "optiq", "vmlx")
REPO = "org/name"
REV = "a" * 40
CDN = "https://us.aws.cdn.hf.co/xet-bridge-us/x"


# ---------------------------------------------------------------------------
# Scratch lab files: `_lab_paths`'s two inputs, and never the real ones
# ---------------------------------------------------------------------------


def write_manifest(tmp_path, lab_paths=None):
    """A manifest of the shipped shape, with optional per-engine ``lab_path``."""
    lab_paths = lab_paths or {}
    payload = {
        name: {
            "version": "0.0.0",
            "verified": "2026-10-29",
            "lab_path": lab_paths.get(name),
            "canary": None,
        }
        for name in ENGINES
    }
    path = tmp_path / "engines-tested.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def bind_lab_inputs(monkeypatch, manifest, lab_paths_path):
    """Point `_lab_paths`'s two loaders at scratch files, leaving `_engine_env` alone.

    ``_lab_paths`` imports both names from ``engines`` on every call, so replacing them on
    the module is how the read inside ``_engine_command`` is exercised without this Mac's
    Application Support file. ``_engine_env`` is not patched: that is the S5-F10 gap.
    """
    real_manifest, real_paths = engines.load_manifest, engines.lab_paths

    def load(path=None):
        return real_manifest(manifest if path is None else path)

    def load_paths(path=None, **kwargs):
        return real_paths(lab_paths_path if path is None else path, **kwargs)

    monkeypatch.setattr(engines, "load_manifest", load)
    monkeypatch.setattr(engines, "lab_paths", load_paths)


def a_free_port():
    """A port nothing is listening on: bound to take it, then released."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


# ---------------------------------------------------------------------------
# AC-1: system helpers never read the lab files
# ---------------------------------------------------------------------------


def test_a_malformed_lab_file_does_not_take_out_the_process_helpers(tmp_path, monkeypatch):
    """`lsof` and `ps` answer when the lab file is not JSON: neither can use a lab PATH."""
    malformed = tmp_path / "lab-paths.json"
    malformed.write_text("{", encoding="utf-8")
    bind_lab_inputs(monkeypatch, write_manifest(tmp_path), malformed)

    assert runtimes._listener_pids(a_free_port()) == ()
    identity = runtimes._process_identity(os.getpid())
    assert isinstance(identity, tuple) and len(identity) == 2
    assert all(isinstance(part, str) and part for part in identity)


def test_an_lsof_outside_the_system_directories_still_probes(tmp_path, monkeypatch):
    """`LSOF` is `shutil.which("lsof")` and may live in Homebrew, so the name is skipped."""
    helpers = tmp_path / "helpers"
    helpers.mkdir()
    lsof = helpers / "lsof"
    os.symlink(runtimes.LSOF, lsof)
    monkeypatch.setattr(runtimes, "LSOF", str(lsof))
    malformed = tmp_path / "lab-paths.json"
    malformed.write_text("{", encoding="utf-8")
    bind_lab_inputs(monkeypatch, write_manifest(tmp_path), malformed)

    assert runtimes._listener_pids(a_free_port()) == ()


def test_a_lab_directory_is_still_prefixed_to_a_programs_path(tmp_path, monkeypatch):
    """A program inside a recorded lab directory keeps today's PATH prefix."""
    lab_bin = tmp_path / "optiq-venv" / "bin"
    lab_bin.mkdir(parents=True)
    (lab_bin / "optiq").write_text("", encoding="utf-8")
    lab_file = tmp_path / "lab-paths.json"
    lab_file.write_text(json.dumps({"optiq": str(lab_bin)}), encoding="utf-8")
    bind_lab_inputs(monkeypatch, write_manifest(tmp_path), lab_file)

    _command, env = runtimes._engine_command(None, (str(lab_bin / "optiq"), "serve"))

    assert env["PATH"].split(os.pathsep)[0] == str(lab_bin)


def test_a_broken_lab_file_still_refuses_an_engine_start(tmp_path, monkeypatch):
    """A start reads the lab files: a malformed one refuses, never falls back to global."""
    malformed = tmp_path / "lab-paths.json"
    malformed.write_text("{", encoding="utf-8")
    bind_lab_inputs(monkeypatch, write_manifest(tmp_path), malformed)

    with pytest.raises(ValueError):
        runtimes._engine_command("optiq", ("optiq", "serve"))


# ---------------------------------------------------------------------------
# AC-2: a cancel interrupts a hash mid-file
# ---------------------------------------------------------------------------


class CountingFile:
    """A file handle that counts its own ``read`` calls, so a stop is observable."""

    def __init__(self, handle, reads):
        self._handle = handle
        self._reads = reads

    def read(self, size=-1):
        self._reads.append(1)
        return self._handle.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._handle.close()
        return False


def count_reads(monkeypatch, path):
    """Count the chunk reads of *path* only; every other open is untouched."""
    reads = []
    real_open = builtins.open

    def counting_open(name, mode="r", *args, **kwargs):
        handle = real_open(name, mode, *args, **kwargs)
        if str(name) == str(path):
            return CountingFile(handle, reads)
        return handle

    monkeypatch.setattr(fetch, "open", counting_open, raising=False)
    return reads


def cancel_after(reads, allowed):
    """Cancel turns true once more than *allowed* chunks have been read: a mid-file stop."""

    def cancel():
        return len(reads) > allowed

    return cancel


def make_model(body):
    """One catalog row holding a single LFS file, hashes taken from the truth."""
    return Model(
        repo=REPO,
        title="A model",
        params=1_000_000,
        format="4bit",
        modality="text",
        license="mit",
        tier="starter",
        revision=REV,
        size_bytes=len(body),
        files=[
            ModelFile(
                path="weights.safetensors",
                size=len(body),
                sha256=hashlib.sha256(body).hexdigest(),
                git_oid=None,
            )
        ],
        engines=["mlxlm"],
        measured_here=False,
        notes="",
    )


def run_download(tmp_path, monkeypatch, model, cancel):
    """Drive `fetch.download` with scratch paths; no byte is ever requested."""
    events = []
    calls = []

    def never(url, headers=None):
        calls.append((url, headers))
        raise AssertionError("a cancelled download must not request a body")

    monkeypatch.setattr(fetch, "free_bytes_at", lambda path: 200 * 1024**3)
    support = tmp_path / "support"
    result = fetch.download(
        model.repo,
        True,
        models=[model],
        cache_dir=str(tmp_path / "hub"),
        ledger_path=str(support / "fetched.json"),
        log_path=str(support / "fetch-log.jsonl"),
        lock_dir=str(support / "locks"),
        open_url=never,
        sleep=lambda seconds: None,
        clock=lambda: 1234.5,
        emit=events.append,
        cancel=cancel,
    )
    return result, events, calls


def cancelled_events(events):
    """The code of every error event, and the last (held) event's type."""
    codes = [event["payload"]["code"] for event in events if event["type"] == "error"]
    return codes, events[-1]["type"]


def test_a_cancel_stops_a_hash_mid_file(tmp_path, monkeypatch):
    """`_verify`'s hash honours a cancel every 64 chunks, not only at the end."""
    body = b"x" * (16 * 500)
    model = make_model(body)
    planned_file = fetch.plan(model, str(tmp_path / "hub")).files[0]
    path = tmp_path / "blob"
    path.write_bytes(body)
    monkeypatch.setattr(fetch, "CHUNK_SIZE", 16)
    reads = count_reads(monkeypatch, path)

    with pytest.raises(fetch._Cancelled):
        fetch._verify(planned_file, str(path), cancel=cancel_after(reads, 2))

    assert len(reads) < 500
    assert len(reads) <= 2 + 64


def test_a_cancel_stops_a_git_blob_hash_too(tmp_path, monkeypatch):
    """The non-LFS rule's hash takes the same cancel."""
    body = b"y" * (16 * 500)
    path = tmp_path / "blob"
    path.write_bytes(body)
    monkeypatch.setattr(fetch, "CHUNK_SIZE", 16)
    reads = count_reads(monkeypatch, path)

    with pytest.raises(fetch._Cancelled):
        fetch._git_blob_sha1(str(path), len(body), cancel=cancel_after(reads, 2))

    assert len(reads) < 500
    assert len(reads) <= 2 + 64


def test_a_cancel_during_the_hash_of_a_preexisting_blob_keeps_it(tmp_path, monkeypatch):
    """A blob being re-verified is neither removed nor repaired by a cancel."""
    body = b"z" * (16 * 500)
    model = make_model(body)
    planned_file = fetch.plan(model, str(tmp_path / "hub")).files[0]
    blob = planned_file.blob
    os.makedirs(os.path.dirname(blob), exist_ok=True)
    with open(blob, "wb") as handle:
        handle.write(body)
    monkeypatch.setattr(fetch, "CHUNK_SIZE", 16)
    reads = count_reads(monkeypatch, blob)

    result, events, calls = run_download(tmp_path, monkeypatch, model, cancel_after(reads, 2))

    assert result is False
    assert cancelled_events(events) == (["cancelled"], "done")
    assert len(reads) < 500
    assert os.path.exists(blob) and os.path.getsize(blob) == len(body)
    assert calls == []


def test_a_cancel_during_the_hash_of_a_finished_partial_keeps_it(tmp_path, monkeypatch):
    """`finish`'s verify is cancelled before the partial is removed or renamed."""
    body = b"w" * (16 * 500)
    model = make_model(body)
    planned_file = fetch.plan(model, str(tmp_path / "hub")).files[0]
    incomplete = planned_file.blob + ".incomplete"
    os.makedirs(os.path.dirname(incomplete), exist_ok=True)
    with open(incomplete, "wb") as handle:
        handle.write(body)
    monkeypatch.setattr(fetch, "CHUNK_SIZE", 16)
    reads = count_reads(monkeypatch, incomplete)

    result, events, calls = run_download(tmp_path, monkeypatch, model, cancel_after(reads, 2))

    assert result is False
    assert cancelled_events(events) == (["cancelled"], "done")
    assert os.path.exists(incomplete) and os.path.getsize(incomplete) == len(body)
    assert not os.path.exists(planned_file.blob)
    assert calls == []


def test_verify_with_no_cancel_answers_as_today(tmp_path):
    """True and False are unchanged when nothing cancels."""
    body = b"v" * 100
    model = make_model(body)
    planned_file = fetch.plan(model, str(tmp_path / "hub")).files[0]
    good = tmp_path / "good"
    good.write_bytes(body)
    bad = tmp_path / "bad"
    bad.write_bytes(body[:-1] + b"!")

    assert fetch._verify(planned_file, str(good)) is True
    assert fetch._verify(planned_file, str(bad)) is False


# ---------------------------------------------------------------------------
# AC-3: a legacy bare-pid lock held by a non-ohyesmlx process is stale
# ---------------------------------------------------------------------------


def a_lock(tmp_path, text):
    lock = tmp_path / fetch.LOCK_NAME
    lock.write_text(text, encoding="utf-8")
    return lock


def live(monkeypatch, argv):
    """A lock owner that is alive, its argv given (``None``: unreadable)."""
    monkeypatch.setattr(runtimes, "same_process", lambda pid, identity=None: True)
    monkeypatch.setattr(
        runtimes,
        "_process_identity",
        (lambda pid: None) if argv is None else (lambda pid: ("Mon Oct 27 10:00:00 2026", argv)),
    )


def test_a_legacy_lock_whose_argv_is_not_ohyesmlx_is_reclaimed(tmp_path, monkeypatch):
    """A recycled pid now belongs to another program: the lock is stale, not busy."""
    lock = a_lock(tmp_path, "4242")
    live(monkeypatch, "/usr/bin/other-app --serve")

    assert fetch._acquire_lock(str(lock)) is True


def test_a_legacy_lock_whose_argv_names_ohyesmlx_is_busy(tmp_path, monkeypatch):
    """Every launcher's argv carries the name, so a real owner is still respected."""
    lock = a_lock(tmp_path, "4242")
    live(monkeypatch, "/usr/bin/python3 -m ohyesmlx.cli app")

    assert fetch._acquire_lock(str(lock)) is False
    assert lock.read_text(encoding="utf-8") == "4242"


def test_a_legacy_lock_whose_argv_cannot_be_read_is_busy(tmp_path, monkeypatch):
    """Fail closed: an unreadable argv is a busy lock, not a license to break it."""
    lock = a_lock(tmp_path, "4242")
    live(monkeypatch, None)

    assert fetch._acquire_lock(str(lock)) is False


def test_a_json_lock_with_an_identity_keeps_todays_answer(tmp_path, monkeypatch):
    """The current format's identity decides, as before; no argv check is added."""
    lock = a_lock(tmp_path, json.dumps({"pid": 4242, "lstart": "x", "argv": "/usr/bin/other"}))
    live(monkeypatch, "/usr/bin/other-app --serve")

    assert fetch._acquire_lock(str(lock)) is False


def test_a_legacy_lock_naming_this_process_is_busy_without_an_argv_check(tmp_path, monkeypatch):
    """`same_process` answers the own pid from its cache; a test runner's argv is no proof."""
    lock = a_lock(tmp_path, str(os.getpid()))
    monkeypatch.setattr(runtimes, "same_process", lambda pid, identity=None: True)

    def boom(pid):
        raise AssertionError("the own pid's lock must be held without reading its argv")

    monkeypatch.setattr(runtimes, "_process_identity", boom)

    assert fetch._acquire_lock(str(lock)) is False


def test_release_lock_still_removes_only_a_lock_naming_this_process(tmp_path):
    """`_release_lock` is unchanged: another pid's lock is left alone."""
    theirs = a_lock(tmp_path, "4242")
    fetch._release_lock(str(theirs))
    assert theirs.exists()

    ours = a_lock(tmp_path, str(os.getpid()))
    fetch._release_lock(str(ours))
    assert not ours.exists()
