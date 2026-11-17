"""Fable 5.2 S4-F3: the disk guard asks the root volume, not the volume the cache is on.

The finding: both download guards read ``hardware().disk_free_bytes``
(``ohyesmlx/fetch.py:819`` and ``:1146``), which ``hardware.scan`` defines as the free space
of ``"/"`` (``ohyesmlx/hardware.py:146-153``). ``cache_dir`` is never consulted for free
space, although it may name any volume: ``fetch.default_cache_dir`` honours
``HF_HUB_CACHE`` (:137-149) and D8 says the user may pick another volume. So a cache on an
external SSD that is nearly full passes the guard while the internal disk has room, and a
cache on an empty external SSD is refused because the internal disk is nearly full.

These checks state the finding's rule -- the free space that decides a download is the one
on the filesystem that will hold the bytes -- and fail on the code as reviewed. Nothing
touches a real volume: ``shutil.disk_usage`` is replaced by a map from path to volume, and
the injected ``hardware`` carries the *root* volume's number, exactly as ``hardware.scan``
does when ``"/"`` is all it reports. No socket is opened and no real sleep is taken.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from collections import namedtuple
from types import SimpleNamespace

from ohyesmlx import fetch
from ohyesmlx.catalog import Model, ModelFile, disk_needed

REPO = "org/name"
REV = "a" * 40
CDN = "https://us.aws.cdn.hf.co/xet-bridge-us/x"

# The two volumes the tests model: 200 GiB of room, or 500 bytes of room.
ROOMY = 200 * 1024**3
TIGHT = 500

Usage = namedtuple("usage", "total used free")


def git_oid(body):
    """The git blob id of *body*: sha1 over ``"blob <len>\\0" + bytes``."""
    return hashlib.sha1(b"blob %d\x00" % len(body) + body).hexdigest()


class Response:
    """A response object with the four things the downloader reads, and nothing else."""

    def __init__(self, status, body, headers):
        self.status = status
        self.headers = dict(headers)
        self.url = CDN
        self._body = body
        self._offset = 0
        self.closed = False

    def read(self, amount=-1):
        size = len(self._body) if amount is None or amount < 0 else amount
        data = self._body[self._offset : self._offset + size]
        self._offset += len(data)
        return data

    def close(self):
        self.closed = True


class Transport:
    """Serves each catalog file by name, honouring a Range request; records every call."""

    def __init__(self, bodies):
        self.bodies = bodies
        self.calls = []

    def __call__(self, url, headers=None):
        recorded = dict(headers or {})
        self.calls.append((url, recorded))
        body = self.bodies[url.rsplit("/", 1)[-1]]
        requested = recorded.get("Range")
        if requested:
            start = int(requested.split("=", 1)[1].rstrip("-"))
            payload = body[start:]
            return Response(
                206,
                payload,
                {
                    "Content-Length": str(len(payload)),
                    "Content-Range": f"bytes {start}-{len(body) - 1}/{len(body)}",
                },
            )
        return Response(200, body, {"Content-Length": str(len(body))})


class Volumes:
    """``shutil.disk_usage`` over two volumes.

    *cache_volume* is the directory that stands in for the disk the cache lives on -- the
    scratch root, because the cache itself does not exist before the guard and a helper must
    ask the nearest existing parent. Every path equal to it or under it reads
    ``external_free``, everything else ``internal_free``. A path that does not exist raises
    ``FileNotFoundError``, as the real call does.
    """

    def __init__(self, cache_volume, *, internal_free, external_free):
        self.cache_volume = os.path.realpath(str(cache_volume))
        self.internal_free = internal_free
        self.external_free = external_free

    def __call__(self, path):
        candidate = os.path.realpath(str(path))
        if not os.path.exists(candidate):
            raise FileNotFoundError(candidate)
        on_cache_volume = candidate == self.cache_volume or candidate.startswith(
            self.cache_volume + os.sep
        )
        chosen = self.external_free if on_cache_volume else self.internal_free
        free = chosen() if callable(chosen) else chosen
        return Usage(free, free, free)


def hardware_on_the_root_volume(free):
    """What ``hardware.scan`` reports: the free space of ``"/"`` and nothing about the cache."""
    return lambda: SimpleNamespace(
        disk_free_bytes=free, volumes=[{"path": "/", "free_bytes": free}]
    )


def make_model(files, *, repo=REPO):
    """A catalog row from ``(path, body, "lfs"|"git")`` triples; hashes are the truth."""
    entries = []
    for path, body, kind in files:
        entries.append(
            ModelFile(
                path=path,
                size=len(body),
                sha256=hashlib.sha256(body).hexdigest() if kind == "lfs" else None,
                git_oid=git_oid(body) if kind == "git" else None,
            )
        )
    return Model(
        repo=repo,
        title="A model",
        params=1_000_000,
        format="4bit",
        modality="text",
        license="mit",
        tier="starter",
        revision=REV,
        size_bytes=sum(entry.size for entry in entries),
        files=entries,
        engines=["mlxlm"],
        measured_here=False,
        notes="",
    )


def run_download(tmp_path, monkeypatch, model, transport, hardware, disk_usage):
    """Drive ``fetch.download`` with a scratch cache; return ``(result, codes, events)``."""
    monkeypatch.setattr(shutil, "disk_usage", disk_usage)
    support = tmp_path / "support"
    events = []
    result = fetch.download(
        model.repo,
        True,
        models=[model],
        cache_dir=str(tmp_path / "hub"),
        ledger_path=str(support / "fetched.json"),
        log_path=str(support / "fetch-log.jsonl"),
        lock_dir=str(support / "locks"),
        open_url=transport,
        hardware=hardware,
        sleep=lambda seconds: None,
        clock=lambda: 1234.5,
        emit=events.append,
        cancel=lambda: False,
    )
    codes = [event["payload"]["code"] for event in events if event["type"] == "error"]
    return result, codes, events


def test_a_full_cache_volume_is_refused_even_when_the_root_volume_has_room(tmp_path, monkeypatch):
    """The external SSD the cache is on holds 500 bytes; the internal disk holds 200 GiB."""
    body = b"w" * 1000
    model = make_model([("weights.safetensors", body, "lfs")])
    transport = Transport({"weights.safetensors": body})
    volumes = Volumes(tmp_path, internal_free=ROOMY, external_free=TIGHT)

    result, codes, events = run_download(
        tmp_path,
        monkeypatch,
        model,
        transport,
        hardware_on_the_root_volume(ROOMY),
        volumes,
    )

    assert result is False, (
        f"the cache volume has {TIGHT} bytes free and this download needs "
        f"{disk_needed(len(body))}; it was accepted because the root volume reads {ROOMY}"
    )
    assert "low_disk" in codes, codes
    assert transport.calls == [], "the refusal must come before any request"
    refusal = next(event for event in events if event["payload"].get("code") == "low_disk")
    assert refusal["payload"]["free_bytes"] == TIGHT, (
        "the refusal must report the free space of the volume the cache is on, "
        f"not the root volume's {ROOMY}: {refusal['payload']!r}"
    )


def test_a_roomy_cache_volume_is_not_refused_when_the_root_volume_is_full(
    tmp_path, monkeypatch
):
    """The internal disk holds 500 bytes; the external SSD the cache is on holds 200 GiB."""
    body = b"w" * 1000
    model = make_model([("weights.safetensors", body, "lfs")])
    transport = Transport({"weights.safetensors": body})
    volumes = Volumes(tmp_path, internal_free=TIGHT, external_free=ROOMY)

    result, codes, _events = run_download(
        tmp_path,
        monkeypatch,
        model,
        transport,
        hardware_on_the_root_volume(TIGHT),
        volumes,
    )

    assert "low_disk" not in codes, (
        "the cache volume has "
        f"{ROOMY} bytes free, so this download fits; it was refused with "
        f"{codes} because the root volume reads {TIGHT}"
    )
    assert result is True
    blob = tmp_path / "hub" / "models--org--name" / "blobs" / hashlib.sha256(body).hexdigest()
    assert blob.read_bytes() == body


def test_the_per_file_guard_also_asks_the_cache_volume(tmp_path, monkeypatch):
    """The first file fills the cache volume; the re-check before the second sees that.

    Both guard sites (``fetch.py:819`` and ``:1146``) read the same root-volume number; this
    pins the second one: the volume empties after the first transfer, and a guard that asks
    the cache's own filesystem refuses the second file before requesting it.
    """
    first = b"a" * 400
    second = b"b" * 400
    model = make_model(
        [
            ("weights.safetensors", first, "lfs"),
            ("config.json", second, "git"),
        ]
    )
    transport = Transport({"weights.safetensors": first, "config.json": second})
    volumes = Volumes(
        tmp_path,
        internal_free=ROOMY,
        external_free=lambda: ROOMY if not transport.calls else 0,
    )

    result, codes, events = run_download(
        tmp_path,
        monkeypatch,
        model,
        transport,
        hardware_on_the_root_volume(ROOMY),
        volumes,
    )

    assert "low_disk" in codes, (
        "after the first file the cache volume has no room left and config.json still "
        f"needs {disk_needed(len(second))} bytes; the per-file guard read the root "
        f"volume's {ROOMY} "
        f"and answered {codes}"
    )
    assert result is False
    assert [url.rsplit("/", 1)[-1] for url, _headers in transport.calls] == [
        "weights.safetensors"
    ], "the second file must be refused before it is requested"
    refusal = next(event for event in events if event["payload"].get("code") == "low_disk")
    assert refusal["payload"]["free_bytes"] == 0, (
        f"the re-check must report the cache volume's free space: {refusal['payload']!r}"
    )
