"""Checks for ohyesmlx.fetch.

Every check drives the module through its injected seams: a fake transport that records
each request and returns literal bytes, a hardware stub with a literal free-space number,
a clock and a sleep that only record, and a ``tmp_path`` cache, ledger, lock directory and
log. No socket is opened, no real sleep is taken, and the real ``~/.cache/huggingface`` is
never read or written.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import time
from collections import namedtuple

import pytest

from ohyesmlx import fetch
from ohyesmlx.catalog import Model, ModelFile

REPO = "org/name"
REV = "a" * 40
WEIGHTS = b"hello world"
CONFIG = b'{"a":1}'


def test_the_lock_dir_guard_fires_on_the_real_directory():
    """AC-4's guard is the suite-wide fixture in ``tests/conftest.py``; this proves it
    refuses the real path rather than merely being installed."""
    with pytest.raises(AssertionError, match="real lock directory"):
        fetch._acquire_lock(os.path.join(fetch.DEFAULT_LOCK_DIR, fetch.LOCK_NAME))


def git_oid(body):
    """The git blob id of *body*: sha1 over ``"blob <len>\\0" + bytes``."""
    return hashlib.sha1(b"blob %d\x00" % len(body) + body).hexdigest()


GIT = git_oid(CONFIG)
SHA = hashlib.sha256(WEIGHTS).hexdigest()
CDN = "https://us.aws.cdn.hf.co/xet-bridge-us/x"
RESOLVE = f"https://huggingface.co/{REPO}/resolve/{REV}/weights.safetensors"


class Response:
    """A response object with the four things the downloader reads, and nothing else."""

    def __init__(self, status, body=b"", headers=None, *, url=CDN, chunk=None, on_read=None):
        self.status = status
        self.headers = dict(headers or {})
        self.url = url
        self._body = body
        self._offset = 0
        self._chunk = chunk
        self._on_read = on_read
        self.closed = False

    def read(self, amount=-1):
        size = len(self._body) if amount is None or amount < 0 else amount
        if self._chunk is not None:
            size = min(size, self._chunk)
        data = self._body[self._offset : self._offset + size]
        self._offset += len(data)
        if self._on_read is not None:
            self._on_read(self)
        return data

    def close(self):
        self.closed = True


class Transport:
    """A fake transport: records every (url, headers) and asks *handler* for a response."""

    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def __call__(self, url, headers=None):
        recorded = dict(headers or {})
        self.calls.append((url, recorded))
        return self.handler(url, recorded)

    @property
    def urls(self):
        return [url for url, _ in self.calls]

    @property
    def headers(self):
        return [headers for _, headers in self.calls]


def serve(bodies, *, status=200, chunk=None, ignore_range=False, on_read=None):
    """A transport that serves *bodies* by file name, honouring Range unless told not to."""

    def handler(url, headers):
        name = url.rsplit("/", 1)[-1]
        body = bodies[name]
        requested = headers.get("Range")
        if requested and not ignore_range:
            start = int(requested.split("=", 1)[1].rstrip("-"))
            payload = body[start:]
            return Response(
                206,
                payload,
                {
                    "Content-Length": str(len(payload)),
                    "Content-Range": f"bytes {start}-{len(body) - 1}/{len(body)}",
                },
                chunk=chunk,
                on_read=on_read,
            )
        return Response(
            status, body, {"Content-Length": str(len(body))}, chunk=chunk, on_read=on_read
        )

    return Transport(handler)


def make_model(files, *, repo=REPO, revision=REV):
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
        revision=revision,
        size_bytes=sum(entry.size for entry in entries),
        files=entries,
        engines=["mlxlm"],
        measured_here=False,
        notes="",
    )


TWO_FILES = [
    ("weights.safetensors", WEIGHTS, "lfs"),
    ("config.json", CONFIG, "git"),
]


class Flag:
    """A cancel probe a response can flip after its first read."""

    def __init__(self):
        self.value = False

    def __call__(self):
        return self.value


class Clock:
    """A fake clock the download reads; a response's reads advance it by a fixed step."""

    def __init__(self, start=100.0):
        self.value = start

    def __call__(self):
        return self.value

    def advance(self, seconds, _response=None):
        self.value += seconds


_Usage = namedtuple("usage", "total used free")
_CURRENT = []  # the Harness of the running test; its ``free`` is the cache volume's room


@pytest.fixture(autouse=True)
def _fake_disk_usage(monkeypatch):
    """The guards ask ``hardware.free_bytes_at(cache_dir)``, which asks ``shutil.disk_usage``."""

    def disk_usage(path):
        free = _CURRENT[-1].free
        free = free() if callable(free) else free
        return _Usage(free, 0, free)

    monkeypatch.setattr(shutil, "disk_usage", disk_usage)


class Harness:
    """Every injected seam for one test, all rooted in ``tmp_path``.

    *free* is what the cache's volume reports (a number, or a callable asked at each guard).
    """

    def __init__(self, tmp_path, models, transport, *, free=10**12, clock=1234.5):
        self.models = models
        self.transport = transport
        self.cache = tmp_path / "hub"
        self.support = tmp_path / "support"
        self.ledger = self.support / "fetched.json"
        self.log = self.support / "fetch-log.jsonl"
        self.locks = self.support / "locks"
        self.free = free
        _CURRENT.append(self)
        self.clock = clock
        self.cancel = Flag()
        self.events = []
        self.sleeps = []

    def download(self, repo=REPO, confirmed=True, **overrides):
        kwargs = dict(
            models=self.models,
            cache_dir=str(self.cache),
            ledger_path=str(self.ledger),
            log_path=str(self.log),
            lock_dir=str(self.locks),
            open_url=self.transport,
            sleep=self.sleeps.append,
            clock=lambda: self.clock,
            emit=self.events.append,
            cancel=self.cancel,
        )
        kwargs.update(overrides)
        return fetch.download(repo, confirmed, **kwargs)

    def evict(self, repo=REPO, confirmed=True, **overrides):
        kwargs = dict(
            cache_dir=str(self.cache),
            ledger_path=str(self.ledger),
            log_path=str(self.log),
            lock_dir=str(self.locks),
            emit=self.events.append,
        )
        kwargs.update(overrides)
        return fetch.evict(repo, confirmed, **kwargs)

    def codes(self):
        return [
            event["payload"]["code"]
            for event in self.events
            if event["type"] == "error"
        ]

    @property
    def repo_dir(self):
        return self.cache / "models--org--name"

    @property
    def blobs(self):
        return self.repo_dir / "blobs"

    @property
    def snapshot(self):
        return self.repo_dir / "snapshots" / REV

    @property
    def ref(self):
        return self.repo_dir / "refs" / "main"


def ledger_of(harness):
    return json.loads(harness.ledger.read_text())


# ---------------------------------------------------------------------------
# 1. Consent, unknown repo, bad names
# ---------------------------------------------------------------------------


def test_consent_required_opens_nothing(tmp_path):
    transport = serve({"weights.safetensors": WEIGHTS})
    harness = Harness(tmp_path, [make_model(TWO_FILES)], transport)

    assert harness.download(confirmed=False) is False

    assert transport.calls == []
    assert not harness.cache.exists()
    assert harness.events == [
        {
            "seq": 1,
            "type": "error",
            "message": f"consent was not given; nothing of {REPO} was downloaded",
            "fraction": None,
            "payload": {"code": "consent_required"},
        },
        {
            "seq": 2,
            "type": "done",
            "message": "fetch ended",
            "fraction": None,
            "payload": None,
        },
    ]
    logged = [json.loads(line) for line in harness.log.read_text().splitlines()]
    assert [line["type"] for line in logged] == ["error", "done"]
    assert logged[0]["code"] == "consent_required"
    assert logged[0]["engine"] == REPO


def test_unknown_repo_opens_nothing(tmp_path):
    transport = serve({"weights.safetensors": WEIGHTS})
    harness = Harness(tmp_path, [make_model(TWO_FILES)], transport)

    assert harness.download(repo="other/repo") is False

    assert transport.calls == []
    assert not harness.cache.exists()
    assert harness.codes() == ["unknown_repo"]
    assert harness.events[0]["message"] == (
        "other/repo is not a catalog model; nothing was downloaded"
    )


@pytest.mark.parametrize(
    "model",
    [
        make_model(TWO_FILES, repo="org/../../etc"),
        make_model(TWO_FILES, repo="org"),
        make_model(TWO_FILES, repo="org/name/extra"),
        make_model(TWO_FILES, repo="org/na me"),
        make_model(TWO_FILES, revision="main"),
        make_model(TWO_FILES, revision="A" * 40),
        make_model([("../../etc/passwd", WEIGHTS, "lfs")]),
        make_model([("a/../b", WEIGHTS, "lfs")]),
        make_model([("/etc/passwd", WEIGHTS, "lfs")]),
        make_model([("a\\b", WEIGHTS, "lfs")]),
        make_model([("a\x00b", WEIGHTS, "lfs")]),
        make_model([("a//b", WEIGHTS, "lfs")]),
        make_model([("", WEIGHTS, "lfs")]),
        Model(
            repo=REPO,
            title="t",
            params=1,
            format="4bit",
            modality="text",
            license="mit",
            tier="starter",
            revision=REV,
            size_bytes=11,
            files=[ModelFile(path="x", size=11, sha256="zz", git_oid=None)],
            engines=["mlxlm"],
            measured_here=False,
            notes="",
        ),
        Model(
            repo=REPO,
            title="t",
            params=1,
            format="4bit",
            modality="text",
            license="mit",
            tier="starter",
            revision=REV,
            size_bytes=11,
            files=[ModelFile(path="x", size=11, sha256=None, git_oid="short")],
            engines=["mlxlm"],
            measured_here=False,
            notes="",
        ),
        Model(
            repo=REPO,
            title="t",
            params=1,
            format="4bit",
            modality="text",
            license="mit",
            tier="starter",
            revision=REV,
            size_bytes=11,
            files=[ModelFile(path="x", size=11, sha256=SHA, git_oid=GIT)],
            engines=["mlxlm"],
            measured_here=False,
            notes="",
        ),
        Model(
            repo=REPO,
            title="t",
            params=1,
            format="4bit",
            modality="text",
            license="mit",
            tier="starter",
            revision=REV,
            size_bytes=11,
            files=[ModelFile(path="x", size=11, sha256=None, git_oid=None)],
            engines=["mlxlm"],
            measured_here=False,
            notes="",
        ),
    ],
)
def test_plan_refuses_a_hostile_literal(tmp_path, model):
    with pytest.raises(ValueError):
        fetch.plan(model, str(tmp_path / "hub"))


def test_download_refuses_a_bad_name_before_any_request_or_write(tmp_path):
    model = make_model([("../../etc/passwd", WEIGHTS, "lfs")])
    transport = serve({"passwd": WEIGHTS})
    harness = Harness(tmp_path, [model], transport)

    assert harness.download() is False

    assert transport.calls == []
    assert not harness.cache.exists()
    assert harness.codes() == ["bad_name"]


# ---------------------------------------------------------------------------
# 2. Layout and verification with a two-file fake model
# ---------------------------------------------------------------------------


def test_happy_path_writes_the_hugging_face_cache_layout(tmp_path):
    transport = serve({"weights.safetensors": WEIGHTS, "config.json": CONFIG})
    harness = Harness(tmp_path, [make_model(TWO_FILES)], transport)

    assert harness.download() is True

    assert harness.repo_dir.name == "models--org--name"
    weights_blob = harness.blobs / SHA
    config_blob = harness.blobs / GIT
    assert weights_blob.read_bytes() == WEIGHTS
    assert config_blob.read_bytes() == CONFIG

    weights_link = harness.snapshot / "weights.safetensors"
    config_link = harness.snapshot / "config.json"
    assert os.path.islink(weights_link)
    assert os.readlink(weights_link) == f"../../blobs/{SHA}"
    assert weights_link.read_bytes() == WEIGHTS
    assert os.readlink(config_link) == f"../../blobs/{GIT}"
    assert config_link.read_bytes() == CONFIG

    assert os.listdir(harness.repo_dir / "snapshots") == [REV]
    assert harness.ref.read_text() == REV + "\n"
    assert not (harness.blobs / f"{SHA}.incomplete").exists()

    assert transport.urls[0] == RESOLVE
    assert all(
        url == f"https://huggingface.co/{REPO}/resolve/{REV}/{name}"
        for url, name in zip(transport.urls, ["weights.safetensors", "config.json"])
    )


def test_happy_path_ledger_records_only_what_the_call_created(tmp_path):
    transport = serve({"weights.safetensors": WEIGHTS, "config.json": CONFIG})
    harness = Harness(tmp_path, [make_model(TWO_FILES)], transport)

    assert harness.download() is True

    entry = ledger_of(harness)["repos"][REPO]
    assert entry["revision"] == REV
    assert entry["bytes"] == len(WEIGHTS) + len(CONFIG)
    assert entry["time"] == 1234.5
    assert entry["created_blobs"] == [str(harness.blobs / SHA), str(harness.blobs / GIT)]
    assert entry["created_links"] == [
        str(harness.snapshot / "weights.safetensors"),
        str(harness.snapshot / "config.json"),
        str(harness.ref),
    ]
    assert entry["created_dirs"] == [
        str(harness.repo_dir),
        str(harness.blobs),
        str(harness.repo_dir / "snapshots"),
        str(harness.snapshot),
        str(harness.repo_dir / "refs"),
    ]


def test_happy_path_events_use_the_pinned_job_shape(tmp_path):
    transport = serve({"weights.safetensors": WEIGHTS, "config.json": CONFIG})
    harness = Harness(tmp_path, [make_model(TWO_FILES)], transport)

    assert harness.download() is True

    assert [event["type"] for event in harness.events] == [
        "log",
        "progress",
        "progress",
        "result",
        "done",
    ]
    assert [event["seq"] for event in harness.events] == [1, 2, 3, 4, 5]
    for event in harness.events:
        assert set(event) == {"seq", "type", "message", "fraction", "payload"}
    assert [event["payload"] for event in harness.events[1:3]] == [
        {"path": "weights.safetensors", "bytes": 11},
        {"path": "config.json", "bytes": 7},
    ]
    assert harness.events[1]["fraction"] == 11 / 18
    assert harness.events[2]["fraction"] == 1.0
    assert harness.events[3]["payload"] == {
        "status": "downloaded",
        "repo": REPO,
        "bytes": 18,
    }
    assert harness.events[-1]["message"] == "download finished"


# ---------------------------------------------------------------------------
# 3. Integrity failure leaves nothing visible
# ---------------------------------------------------------------------------


def test_checksum_mismatch_removes_the_partial_and_links_nothing(tmp_path):
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    transport = serve({"weights.safetensors": b"HELLO WORLD"})
    harness = Harness(tmp_path, [model], transport)

    assert harness.download() is False

    blob = harness.blobs / SHA
    assert harness.codes() == ["integrity_failed"]
    assert harness.events[1]["payload"]["path"] == str(blob)
    assert not blob.exists()
    assert not (harness.blobs / f"{SHA}.incomplete").exists()
    assert not harness.snapshot.exists()
    assert not harness.ref.exists()


def test_a_failure_on_the_second_file_leaves_no_links(tmp_path):
    model = make_model(
        [("weights.safetensors", WEIGHTS, "lfs"), ("other.safetensors", CONFIG, "lfs")]
    )
    other_sha = hashlib.sha256(CONFIG).hexdigest()
    transport = Transport(
        lambda url, headers: Response(
            200,
            WEIGHTS if url.endswith("weights.safetensors") else b'{"a":2}',
            {"Content-Length": "11" if url.endswith("weights.safetensors") else "7"},
        )
    )
    harness = Harness(tmp_path, [model], transport)

    assert harness.download() is False

    assert (harness.blobs / SHA).exists()
    assert not (harness.blobs / other_sha).exists()
    assert not harness.snapshot.exists()
    assert not harness.ref.exists()
    assert harness.codes() == ["integrity_failed"]


# ---------------------------------------------------------------------------
# 4. Resume with Range
# ---------------------------------------------------------------------------


def test_resume_sends_a_range_and_writes_only_the_remainder(tmp_path):
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    transport = serve({"weights.safetensors": WEIGHTS})
    harness = Harness(tmp_path, [model], transport)
    incomplete = harness.blobs / f"{SHA}.incomplete"
    incomplete.parent.mkdir(parents=True)
    incomplete.write_bytes(WEIGHTS[:5])

    assert harness.download() is True

    assert transport.headers[0] == {"Range": "bytes=5-"}
    assert (harness.blobs / SHA).read_bytes() == WEIGHTS
    assert not incomplete.exists()


def test_a_206_starting_elsewhere_is_refused(tmp_path):
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    transport = Transport(
        lambda url, headers: Response(
            206,
            b" world",
            {"Content-Length": "6", "Content-Range": "bytes 0-5/11"},
        )
    )
    harness = Harness(tmp_path, [model], transport)
    incomplete = harness.blobs / f"{SHA}.incomplete"
    incomplete.parent.mkdir(parents=True)
    incomplete.write_bytes(WEIGHTS[:5])

    assert harness.download() is False

    assert harness.codes() == ["size_mismatch"]
    assert not (harness.blobs / SHA).exists()
    assert not harness.snapshot.exists()


def test_a_200_to_a_range_request_restarts_from_zero(tmp_path):
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    transport = serve({"weights.safetensors": WEIGHTS}, ignore_range=True)
    harness = Harness(tmp_path, [model], transport)
    incomplete = harness.blobs / f"{SHA}.incomplete"
    incomplete.parent.mkdir(parents=True)
    incomplete.write_bytes(WEIGHTS[:5])

    assert harness.download() is True

    assert transport.headers[0] == {"Range": "bytes=5-"}
    assert (harness.blobs / SHA).read_bytes() == WEIGHTS


# ---------------------------------------------------------------------------
# 5. An expired signed URL is resolved once more
# ---------------------------------------------------------------------------


def test_an_expired_signed_url_is_resolved_once_more(tmp_path):
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    counter = {"n": 0}

    def handler(url, headers):
        counter["n"] += 1
        if counter["n"] == 1:
            return Response(403)
        return Response(200, WEIGHTS, {"Content-Length": "11"})

    transport = Transport(handler)
    harness = Harness(tmp_path, [model], transport)

    assert harness.download() is True

    assert counter["n"] == 2
    assert (harness.blobs / SHA).read_bytes() == WEIGHTS


def test_a_second_403_is_not_resolved_again(tmp_path):
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    counter = {"n": 0}

    def handler(url, headers):
        counter["n"] += 1
        return Response(403)

    transport = Transport(handler)
    harness = Harness(tmp_path, [model], transport)

    assert harness.download() is False

    assert counter["n"] == 2
    assert harness.codes() == ["http_error"]
    assert not (harness.blobs / SHA).exists()


# ---------------------------------------------------------------------------
# 6. Hosts and URLs are constrained
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://huggingface.co/org/name/resolve/x",
        "https://cdn-lfs.huggingface.co/blob",
        "https://us.aws.cdn.hf.co/xet-bridge-us/x",
        "https://hf.co/x",
    ],
)
def test_allowed_hosts(url):
    assert fetch.url_allowed(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "http://huggingface.co/org/name",
        "https://evil.example/x",
        "https://huggingface.co.evil.example/x",
        "https://evil-huggingface.co/x",
        "https://huggingface.co@evil.example/x",
        "",
        None,
    ],
)
def test_refused_hosts(url):
    assert fetch.url_allowed(url) is False


def test_a_final_url_outside_the_allowlist_is_refused(tmp_path):
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    transport = Transport(
        lambda url, headers: Response(
            200, WEIGHTS, {"Content-Length": "11"}, url="https://evil.example/x"
        )
    )
    harness = Harness(tmp_path, [model], transport)

    assert harness.download() is False

    assert harness.codes() == ["host_not_allowed"]
    assert not (harness.blobs / SHA).exists()
    assert not harness.snapshot.exists()


def test_an_http_final_url_is_refused(tmp_path):
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    transport = Transport(
        lambda url, headers: Response(
            200, WEIGHTS, {"Content-Length": "11"}, url=f"http://huggingface.co/{REPO}"
        )
    )
    harness = Harness(tmp_path, [model], transport)

    assert harness.download() is False

    assert harness.codes() == ["host_not_allowed"]


# ---------------------------------------------------------------------------
# 7. The disk guard counts what is missing
# ---------------------------------------------------------------------------


def test_disk_guard_counts_missing_bytes_not_the_total(tmp_path):
    model = make_model(TWO_FILES)
    transport = serve({"config.json": CONFIG})
    harness = Harness(tmp_path, [model], transport, free=9)
    harness.blobs.mkdir(parents=True)
    (harness.blobs / SHA).write_bytes(WEIGHTS)

    # total 18 x 1.2 = 22 bytes would refuse; the 7 missing x 1.2 = 9 bytes fits.
    assert harness.download() is True

    assert transport.urls == [f"https://huggingface.co/{REPO}/resolve/{REV}/config.json"]
    assert (harness.blobs / GIT).read_bytes() == CONFIG


def test_disk_guard_refuses_before_any_request(tmp_path):
    model = make_model(TWO_FILES)
    transport = serve({"weights.safetensors": WEIGHTS, "config.json": CONFIG})
    harness = Harness(tmp_path, [model], transport, free=8)

    assert harness.download() is False

    assert harness.codes() == ["low_disk"]
    error = next(event for event in harness.events if event["type"] == "error")
    assert error["message"] == "8 bytes free is less than the 22 bytes this download needs"
    assert error["payload"] == {
        "code": "low_disk",
        "free_bytes": 8,
        "needed_bytes": 22,
    }
    assert transport.calls == []
    assert not harness.cache.exists()
    assert not harness.ledger.exists()


def test_the_disk_guard_is_rechecked_before_each_file(tmp_path):
    model = make_model(TWO_FILES)
    transport = serve({"weights.safetensors": WEIGHTS, "config.json": CONFIG})
    calls = []

    def free():
        calls.append(1)
        return 10**12 if len(calls) == 1 else 0

    harness = Harness(tmp_path, [model], transport, free=free)

    assert harness.download() is False

    assert len(calls) == 2
    assert harness.codes() == ["low_disk"]
    # The per-file guard, with the 11-byte first file's own required bytes.
    error = next(event for event in harness.events if event["type"] == "error")
    assert error["payload"] == {
        "code": "low_disk",
        "free_bytes": 0,
        "needed_bytes": 14,
    }
    assert transport.calls == []


# ---------------------------------------------------------------------------
# 8. Pre-existing and partial downloads are reused, never clobbered
# ---------------------------------------------------------------------------


def test_a_fully_present_model_makes_no_request(tmp_path):
    transport = serve({"weights.safetensors": WEIGHTS, "config.json": CONFIG})
    harness = Harness(tmp_path, [make_model(TWO_FILES)], transport)

    assert harness.download() is True
    calls = len(transport.calls)
    ledger_before = harness.ledger.read_text()
    harness.events.clear()

    assert harness.download() is True

    assert len(transport.calls) == calls
    assert harness.events[-2]["payload"] == {
        "status": "already_present",
        "repo": REPO,
        "bytes": 0,
    }
    assert harness.ledger.read_text() == ledger_before


def test_a_present_blob_is_reused_and_only_the_missing_file_is_requested(tmp_path):
    model = make_model(TWO_FILES)
    transport = serve({"config.json": CONFIG})
    harness = Harness(tmp_path, [model], transport)
    harness.blobs.mkdir(parents=True)
    (harness.blobs / SHA).write_bytes(WEIGHTS)

    assert harness.download() is True

    assert transport.urls == [f"https://huggingface.co/{REPO}/resolve/{REV}/config.json"]
    entry = ledger_of(harness)["repos"][REPO]
    assert entry["created_blobs"] == [str(harness.blobs / GIT)]


def test_a_present_blob_the_download_reused_is_never_evicted(tmp_path):
    model = make_model(TWO_FILES)
    transport = serve({"config.json": CONFIG})
    harness = Harness(tmp_path, [model], transport)
    harness.blobs.mkdir(parents=True)
    (harness.blobs / SHA).write_bytes(WEIGHTS)

    assert harness.download() is True
    assert harness.evict() is True

    assert (harness.blobs / SHA).read_bytes() == WEIGHTS
    assert not (harness.blobs / GIT).exists()
    assert not (harness.snapshot / "weights.safetensors").exists()
    assert not harness.ref.exists()


def test_an_existing_blob_that_does_not_match_is_not_overwritten(tmp_path):
    model = make_model(TWO_FILES)
    transport = serve({"weights.safetensors": WEIGHTS, "config.json": CONFIG})
    harness = Harness(tmp_path, [model], transport)
    harness.blobs.mkdir(parents=True)
    (harness.blobs / SHA).write_bytes(b"other bytes")

    assert harness.download() is False

    assert harness.codes() == ["integrity_failed"]
    assert (harness.blobs / SHA).read_bytes() == b"other bytes"
    assert transport.calls == []


def test_an_existing_non_lfs_blob_of_the_wrong_size_is_refused(tmp_path):
    model = make_model(TWO_FILES)
    transport = serve({"weights.safetensors": WEIGHTS, "config.json": CONFIG})
    harness = Harness(tmp_path, [model], transport)
    harness.blobs.mkdir(parents=True)
    (harness.blobs / GIT).write_bytes(CONFIG + b"!")

    assert harness.download() is False

    assert harness.codes() == ["integrity_failed"]
    assert (harness.blobs / GIT).read_bytes() == CONFIG + b"!"
    assert transport.calls == []


def test_an_existing_non_lfs_blob_of_the_right_size_but_wrong_bytes_is_refused(tmp_path):
    """A non-LFS file is verified by its git blob id, not by its size: same length, other
    bytes is not the file the catalog pins."""
    model = make_model(TWO_FILES)
    transport = serve({"weights.safetensors": WEIGHTS, "config.json": CONFIG})
    harness = Harness(tmp_path, [model], transport)
    harness.blobs.mkdir(parents=True)
    (harness.blobs / GIT).write_bytes(b'{"a":2}')  # the pinned file's 7 bytes, different text

    assert harness.download() is False

    assert harness.codes() == ["integrity_failed"]
    assert (harness.blobs / GIT).read_bytes() == b'{"a":2}'
    assert transport.calls == []


def test_a_snapshot_link_pointing_elsewhere_is_refused_before_any_request(tmp_path):
    """AC-6: the conflict ``link_all`` refuses is found before a byte is requested, so a
    multi-GB transfer is not spent on a download that cannot become visible."""
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    transport = serve({"weights.safetensors": WEIGHTS})
    harness = Harness(tmp_path, [model], transport)
    elsewhere = harness.repo_dir / "user-file.bin"
    elsewhere.parent.mkdir(parents=True)
    elsewhere.write_bytes(b"the user's own bytes")
    link = harness.snapshot / "weights.safetensors"
    link.parent.mkdir(parents=True)
    os.symlink(elsewhere, link)
    blob = harness.blobs / SHA

    assert harness.download() is False

    assert harness.codes() == ["integrity_failed"]
    error = next(event for event in harness.events if event["type"] == "error")
    assert error["message"] == (
        f"{link} already exists and does not point at {blob}; nothing was overwritten"
    )
    assert transport.calls == []
    assert not blob.exists()
    assert link.read_bytes() == b"the user's own bytes"


def test_a_regular_file_where_the_snapshot_link_belongs_is_refused_before_any_request(
    tmp_path,
):
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    transport = serve({"weights.safetensors": WEIGHTS})
    harness = Harness(tmp_path, [model], transport)
    link = harness.snapshot / "weights.safetensors"
    link.parent.mkdir(parents=True)
    link.write_bytes(b"not a link")

    assert harness.download() is False

    assert harness.codes() == ["integrity_failed"]
    assert transport.calls == []
    assert not (harness.blobs / SHA).exists()
    assert link.read_bytes() == b"not a link"


# ---------------------------------------------------------------------------
# 9. Bounded writes
# ---------------------------------------------------------------------------


def test_a_content_length_larger_than_the_catalog_is_refused(tmp_path):
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    transport = Transport(
        lambda url, headers: Response(200, WEIGHTS, {"Content-Length": "99"})
    )
    harness = Harness(tmp_path, [model], transport)

    assert harness.download() is False

    assert harness.codes() == ["size_mismatch"]
    assert not (harness.blobs / SHA).exists()
    assert not (harness.blobs / f"{SHA}.incomplete").exists()


def test_a_body_larger_than_the_catalog_is_refused(tmp_path):
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    transport = Transport(
        lambda url, headers: Response(200, WEIGHTS + b"x", {"Content-Length": "11"})
    )
    harness = Harness(tmp_path, [model], transport)

    assert harness.download() is False

    assert harness.codes() == ["size_mismatch"]
    assert [event for event in harness.events if event["type"] == "error"][-1][
        "message"
    ] == "weights.safetensors: the server sent more than the 11 bytes the catalog pins"
    assert len(transport.calls) == 1
    assert not (harness.blobs / SHA).exists()
    assert not (harness.blobs / f"{SHA}.incomplete").exists()


def test_a_content_range_with_the_wrong_total_is_refused(tmp_path):
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    transport = Transport(
        lambda url, headers: Response(
            206,
            WEIGHTS,
            {"Content-Length": "11", "Content-Range": "bytes 0-10/99"},
        )
    )
    harness = Harness(tmp_path, [model], transport)
    incomplete = harness.blobs / f"{SHA}.incomplete"
    incomplete.parent.mkdir(parents=True)
    incomplete.write_bytes(WEIGHTS[:5])

    assert harness.download() is False

    assert harness.codes() == ["size_mismatch"]


# ---------------------------------------------------------------------------
# 10. Anonymous only
# ---------------------------------------------------------------------------


def test_no_request_carries_an_authorization_header(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_secret_token")
    monkeypatch.setenv("HF_ENDPOINT", "https://mirror.example")
    transport = serve({"weights.safetensors": WEIGHTS, "config.json": CONFIG})
    harness = Harness(tmp_path, [make_model(TWO_FILES)], transport)

    assert harness.download() is True

    assert transport.calls
    for headers in transport.headers:
        assert not any(key.lower() == "authorization" for key in headers)
    assert "hf_secret_token" not in json.dumps(harness.events)
    assert "hf_secret_token" not in harness.log.read_text()


# ---------------------------------------------------------------------------
# 11. Busy and the one cross-process lock
# ---------------------------------------------------------------------------


def test_a_live_lock_holder_makes_the_download_busy(tmp_path):
    transport = serve({"weights.safetensors": WEIGHTS})
    harness = Harness(tmp_path, [make_model(TWO_FILES)], transport)
    harness.locks.mkdir(parents=True)
    (harness.locks / fetch.LOCK_NAME).write_text(str(os.getpid()))

    assert harness.download() is False

    assert harness.codes() == ["busy"]
    assert harness.events[0]["message"] == "another download is already running"
    assert transport.calls == []
    assert not harness.cache.exists()


def test_a_second_repo_is_refused_busy_while_a_download_holds_the_lock(tmp_path):
    """AC-7: one download at a time, across repos. A per-repo lock let two repos download
    at once; a live holder of the one lock refuses the next download whatever it names."""
    transport = serve({"weights.safetensors": WEIGHTS, "config.json": CONFIG})
    models = [
        make_model(TWO_FILES),
        make_model([("other.bin", CONFIG, "lfs")], repo="org/other"),
    ]
    harness = Harness(tmp_path, models, transport)
    harness.locks.mkdir(parents=True)
    (harness.locks / fetch.LOCK_NAME).write_text(str(os.getpid()))

    assert harness.download(repo="org/other") is False

    assert harness.codes() == ["busy"]
    assert harness.events[0]["message"] == "another download is already running"
    assert transport.calls == []
    assert not harness.cache.exists()


def test_a_stale_lock_from_a_dead_pid_is_reclaimed(tmp_path):
    transport = serve({"weights.safetensors": WEIGHTS, "config.json": CONFIG})
    harness = Harness(tmp_path, [make_model(TWO_FILES)], transport)
    harness.locks.mkdir(parents=True)
    lock = harness.locks / fetch.LOCK_NAME
    # Above macOS's pid ceiling, so no process can hold it.
    lock.write_text("999999")

    assert harness.download() is True

    assert not lock.exists()
    assert (harness.blobs / SHA).read_bytes() == WEIGHTS


def test_the_lock_is_released_after_a_refusal(tmp_path):
    transport = serve({"weights.safetensors": WEIGHTS, "config.json": CONFIG})
    harness = Harness(tmp_path, [make_model(TWO_FILES)], transport, free=1)

    assert harness.download() is False

    assert harness.codes() == ["low_disk"]
    error = next(event for event in harness.events if event["type"] == "error")
    assert error["payload"] == {
        "code": "low_disk",
        "free_bytes": 1,
        "needed_bytes": 22,
    }
    assert not (harness.locks / fetch.LOCK_NAME).exists()


# ---------------------------------------------------------------------------
# 12. Cancel
# ---------------------------------------------------------------------------


def test_cancel_keeps_the_partial_links_nothing_and_releases_the_lock(tmp_path):
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    harness = Harness(tmp_path, [model], serve({}))
    first_read = {"done": False}

    def flip(_response):
        if not first_read["done"]:
            first_read["done"] = True
            harness.cancel.value = True

    harness.transport = serve({"weights.safetensors": WEIGHTS}, chunk=4, on_read=flip)

    assert harness.download() is False

    incomplete = harness.blobs / f"{SHA}.incomplete"
    assert incomplete.exists()
    assert 0 < incomplete.stat().st_size < 11
    assert not (harness.blobs / SHA).exists()
    assert not harness.snapshot.exists()
    assert not harness.ref.exists()
    assert [event["type"] for event in harness.events[-2:]] == ["error", "done"]
    assert harness.events[-2]["payload"]["code"] == "cancelled"
    assert not (harness.locks / fetch.LOCK_NAME).exists()
    logged = [json.loads(line) for line in harness.log.read_text().splitlines()]
    assert logged[-2]["code"] == "cancelled"

    # AC-15: the residue is on the ledger, so evict can remove it.
    assert str(incomplete) in ledger_of(harness)["repos"][REPO]["created_blobs"]


def test_a_cancelled_download_resumes_and_completes(tmp_path):
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    harness = Harness(tmp_path, [model], serve({}))
    first_read = {"done": False}

    def flip(_response):
        if not first_read["done"]:
            first_read["done"] = True
            harness.cancel.value = True

    harness.transport = serve({"weights.safetensors": WEIGHTS}, chunk=4, on_read=flip)
    assert harness.download() is False
    incomplete = harness.blobs / f"{SHA}.incomplete"
    assert incomplete.exists()

    harness.cancel.value = False
    resumed = serve({"weights.safetensors": WEIGHTS})
    harness.transport = resumed
    harness.events.clear()

    assert harness.download() is True

    assert resumed.headers[0]["Range"].startswith("bytes=")
    assert (harness.blobs / SHA).read_bytes() == WEIGHTS
    assert not incomplete.exists()


# ---------------------------------------------------------------------------
# 13. Evict: exactly the ledger, nothing else
# ---------------------------------------------------------------------------


def downloaded(tmp_path, free=10**12):
    transport = serve({"weights.safetensors": WEIGHTS, "config.json": CONFIG})
    harness = Harness(tmp_path, [make_model(TWO_FILES)], transport, free=free)
    assert harness.download() is True
    harness.events.clear()
    return harness


def test_evict_requires_consent(tmp_path):
    harness = downloaded(tmp_path)

    assert harness.evict(confirmed=False) is False

    assert harness.codes() == ["consent_required"]
    assert (harness.blobs / SHA).exists()


def test_evict_refuses_a_repo_the_ledger_does_not_list(tmp_path):
    harness = downloaded(tmp_path)

    assert harness.evict(repo="other/repo") is False

    assert harness.codes() == ["unknown_repo"]
    assert (harness.blobs / SHA).exists()


def test_evict_removes_exactly_the_ledger_paths(tmp_path):
    harness = downloaded(tmp_path)

    assert harness.evict() is True

    assert not harness.repo_dir.exists()
    assert not harness.ledger.exists() or ledger_of(harness)["repos"] == {}
    assert harness.events[-2]["payload"] == {
        "repo": REPO,
        "removed": [
            str(harness.snapshot / "weights.safetensors"),
            str(harness.snapshot / "config.json"),
            str(harness.ref),
            str(harness.blobs / SHA),
            str(harness.blobs / GIT),
            str(harness.repo_dir / "refs"),
            str(harness.snapshot),
            str(harness.repo_dir / "snapshots"),
            str(harness.blobs),
            str(harness.repo_dir),
        ],
        "kept": [],
    }
    assert harness.events[-1]["message"] == "eviction finished"


def test_evict_leaves_a_foreign_directory_untouched(tmp_path):
    harness = downloaded(tmp_path)
    foreign = harness.cache / "models--other--thing" / "snapshots" / REV / "model.bin"
    foreign.parent.mkdir(parents=True)
    foreign.write_bytes(b"not ours")

    assert harness.evict() is True

    assert foreign.read_bytes() == b"not ours"


def test_evict_keeps_a_blob_a_second_snapshot_still_references(tmp_path):
    harness = downloaded(tmp_path)
    other = harness.cache / "models--other--thing" / "snapshots" / ("c" * 40) / "shared.bin"
    other.parent.mkdir(parents=True)
    os.symlink(harness.blobs / SHA, other)

    assert harness.evict() is True

    assert (harness.blobs / SHA).read_bytes() == WEIGHTS
    assert os.path.islink(other)
    assert other.read_bytes() == WEIGHTS
    assert not (harness.snapshot / "weights.safetensors").exists()
    entry = ledger_of(harness)["repos"][REPO]
    assert entry["created_blobs"] == [str(harness.blobs / SHA)]


def test_evict_keeps_a_foreign_file_inside_the_repo_directory(tmp_path):
    harness = downloaded(tmp_path)
    mine = harness.repo_dir / "notes.txt"
    mine.write_text("the user's own note")

    assert harness.evict() is True

    assert mine.read_text() == "the user's own note"
    assert harness.repo_dir.exists()
    assert not (harness.blobs / SHA).exists()
    assert not harness.ref.exists()


def test_evict_removes_resume_residue(tmp_path):
    harness = downloaded(tmp_path)
    residue = harness.blobs / f"{SHA}.incomplete"
    residue.write_bytes(b"partial")

    assert harness.evict() is True

    assert not residue.exists()


def test_evict_refuses_a_corrupt_ledger(tmp_path):
    harness = downloaded(tmp_path)
    harness.ledger.write_text("{not json")

    assert harness.evict() is False

    assert harness.codes() == ["ledger_unreadable"]
    assert (harness.blobs / SHA).exists()


def test_evict_refuses_a_missing_ledger(tmp_path):
    harness = Harness(tmp_path, [make_model(TWO_FILES)], serve({}))

    assert harness.evict() is False

    assert harness.codes() == ["ledger_unreadable"]


def test_evict_refuses_a_ledger_path_that_resolves_outside_the_cache(tmp_path):
    harness = Harness(tmp_path, [make_model(TWO_FILES)], serve({}))
    harness.blobs.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("keep me")
    escape = harness.blobs / "escape"
    os.symlink(outside, escape)
    harness.ledger.parent.mkdir(parents=True, exist_ok=True)
    harness.ledger.write_text(
        json.dumps(
            {
                "repos": {
                    REPO: {
                        "revision": REV,
                        "time": 1.0,
                        "bytes": 1,
                        "created_blobs": [str(escape)],
                        "created_links": [],
                        "created_dirs": [],
                    }
                }
            }
        )
    )

    assert harness.evict() is False

    assert harness.codes() == ["ledger_unreadable"]
    assert outside.read_text() == "keep me"
    assert os.path.islink(escape)


@pytest.mark.parametrize("where", ["another_repo", "cache_root", "outside"])
def test_evict_refuses_a_ledger_path_outside_that_repos_own_directory(tmp_path, where):
    """AC-5: the whole cache root was too wide a boundary. A path in another repo's
    directory, at the root itself, or outside the cache refuses the eviction before
    anything is removed."""
    harness = Harness(tmp_path, [make_model(TWO_FILES)], serve({}))
    legit = harness.blobs / SHA
    legit.parent.mkdir(parents=True)
    legit.write_bytes(WEIGHTS)
    if where == "another_repo":
        stray = harness.cache / "models--other--thing" / "blobs" / "x"
    elif where == "cache_root":
        stray = harness.cache / "notes.txt"
    else:
        stray = tmp_path / "outside.txt"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_bytes(b"keep me")
    harness.ledger.parent.mkdir(parents=True, exist_ok=True)
    harness.ledger.write_text(
        json.dumps(
            {
                "repos": {
                    REPO: {
                        "revision": REV,
                        "time": 1.0,
                        "bytes": 1,
                        "created_blobs": [str(legit), str(stray)],
                        "created_links": [],
                        "created_dirs": [],
                    }
                }
            }
        )
    )

    assert harness.evict() is False

    assert harness.codes() == ["ledger_unreadable"]
    assert harness.events[0]["message"].endswith("nothing was removed")
    assert legit.read_bytes() == WEIGHTS, "nothing was removed, not even the listed legit path"
    assert stray.read_bytes() == b"keep me"


def test_a_live_lock_holder_makes_evict_busy_and_removes_nothing(tmp_path):
    """AC-4: evict writes the fetch ledger, so it takes the download lock like a download
    does, and a live holder is refused rather than raced."""
    harness = downloaded(tmp_path)
    (harness.locks / fetch.LOCK_NAME).write_text(str(os.getpid()))
    ledger_before = harness.ledger.read_bytes()
    listed = [
        harness.blobs / SHA,
        harness.blobs / GIT,
        harness.snapshot / "weights.safetensors",
        harness.snapshot / "config.json",
        harness.ref,
    ]

    assert harness.evict() is False

    assert harness.codes() == ["busy"]
    assert harness.events[0]["message"] == (
        "a download or eviction is running; nothing was removed"
    )
    assert harness.ledger.read_bytes() == ledger_before
    for path in listed:
        assert path.exists(), path


def test_the_evict_lock_is_released_after_a_normal_evict(tmp_path):
    harness = downloaded(tmp_path)

    assert harness.evict() is True

    assert not (harness.locks / fetch.LOCK_NAME).exists()


def test_the_evict_lock_is_released_when_an_evict_raises(tmp_path, monkeypatch):
    harness = downloaded(tmp_path)

    def boom(_cache_dir):
        raise RuntimeError("the reference scan failed")

    monkeypatch.setattr(fetch, "_referenced_blobs", boom)

    with pytest.raises(RuntimeError):
        harness.evict()

    assert not (harness.locks / fetch.LOCK_NAME).exists()


def test_a_second_evict_refuses_the_repo_as_unlisted(tmp_path):
    harness = downloaded(tmp_path)

    assert harness.evict() is True
    harness.events.clear()
    assert harness.evict() is False

    assert harness.codes() == ["unknown_repo"]


# ---------------------------------------------------------------------------
# 13b. The ledger follows the cache (045-02b review)
# ---------------------------------------------------------------------------


def sibling_ledger(harness):
    """The ledger a non-default cache owns: a sibling of the cache directory."""
    return os.path.realpath(str(harness.cache)) + ".ohyesmlx-fetched.json"


def test_a_non_default_cache_writes_its_own_sibling_ledger(tmp_path, monkeypatch):
    """A scratch cache with no ``ledger_path`` records what it fetched beside itself, and
    this Mac's ledger is left byte-identical."""
    real = tmp_path / "app-support" / "fetched.json"
    real.parent.mkdir()
    real.write_text('{"repos": {}}\n', encoding="utf-8")
    monkeypatch.setattr(fetch, "DEFAULT_LEDGER", str(real))
    transport = serve({"weights.safetensors": WEIGHTS, "config.json": CONFIG})
    harness = Harness(tmp_path, [make_model(TWO_FILES)], transport)

    assert harness.download(ledger_path=None) is True

    sibling = sibling_ledger(harness)
    assert os.path.dirname(sibling) == os.path.dirname(os.path.realpath(str(harness.cache)))
    entry = json.loads(pathlib.Path(sibling).read_text(encoding="utf-8"))["repos"][REPO]
    assert entry["created_blobs"] == [str(harness.blobs / SHA), str(harness.blobs / GIT)]
    assert real.read_text(encoding="utf-8") == '{"repos": {}}\n'


def test_the_default_cache_uses_the_apps_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)
    linked = tmp_path / "linked-cache"
    os.symlink(fetch.default_cache_dir(), linked)

    assert fetch.ledger_for(None) == fetch.DEFAULT_LEDGER
    assert fetch.ledger_for(fetch.default_cache_dir()) == fetch.DEFAULT_LEDGER
    assert fetch.ledger_for(str(linked)) == fetch.DEFAULT_LEDGER


def test_evict_on_a_scratch_cache_reads_the_sibling_ledger(tmp_path, monkeypatch):
    real = tmp_path / "app-support" / "fetched.json"
    real.parent.mkdir()
    real.write_text('{"repos": {}}\n', encoding="utf-8")
    monkeypatch.setattr(fetch, "DEFAULT_LEDGER", str(real))
    transport = serve({"weights.safetensors": WEIGHTS, "config.json": CONFIG})
    harness = Harness(tmp_path, [make_model(TWO_FILES)], transport)
    assert harness.download(ledger_path=None) is True
    harness.events.clear()

    assert harness.evict(ledger_path=None) is True

    assert not harness.repo_dir.exists()
    sibling = sibling_ledger(harness)
    assert json.loads(pathlib.Path(sibling).read_text(encoding="utf-8"))["repos"] == {}
    assert real.read_text(encoding="utf-8") == '{"repos": {}}\n'


# ---------------------------------------------------------------------------
# 14. Retries, 429 and Retry-After
# ---------------------------------------------------------------------------


def test_a_5xx_is_retried_with_bounded_backoff(tmp_path):
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    replies = [Response(503), Response(503), Response(200, WEIGHTS, {"Content-Length": "11"})]
    transport = Transport(lambda url, headers: replies.pop(0))
    harness = Harness(tmp_path, [model], transport)

    assert harness.download() is True

    assert harness.sleeps == [0.5, 1.0]


def test_429_honours_retry_after(tmp_path):
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    replies = [
        Response(429, headers={"Retry-After": "7"}),
        Response(200, WEIGHTS, {"Content-Length": "11"}),
    ]
    transport = Transport(lambda url, headers: replies.pop(0))
    harness = Harness(tmp_path, [model], transport)

    assert harness.download() is True

    assert harness.sleeps == [7.0]


def test_429_retry_after_is_capped(tmp_path):
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    replies = [
        Response(429, headers={"Retry-After": "100000"}),
        Response(200, WEIGHTS, {"Content-Length": "11"}),
    ]
    transport = Transport(lambda url, headers: replies.pop(0))
    harness = Harness(tmp_path, [model], transport)

    assert harness.download() is True

    assert harness.sleeps == [60.0]


def test_a_connection_error_is_retried(tmp_path):
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    replies = [OSError("connection reset"), Response(200, WEIGHTS, {"Content-Length": "11"})]

    def handler(url, headers):
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    transport = Transport(handler)
    harness = Harness(tmp_path, [model], transport)

    assert harness.download() is True

    assert harness.sleeps == [0.5]
    assert (harness.blobs / SHA).read_bytes() == WEIGHTS


def test_exhausted_retries_report_an_error(tmp_path):
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    transport = Transport(lambda url, headers: Response(503))
    harness = Harness(tmp_path, [model], transport)

    assert harness.download() is False

    assert len(transport.calls) == 4
    assert harness.sleeps == [0.5, 1.0, 2.0]
    assert harness.codes() == ["http_error"]
    assert not (harness.blobs / SHA).exists()


# ---------------------------------------------------------------------------
# AC-9: gated and missing repos are distinguished and never retried
# ---------------------------------------------------------------------------


def test_a_gated_repo_is_named_gated_and_not_retried(tmp_path):
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    transport = Transport(
        lambda url, headers: Response(401, headers={"X-Error-Code": "GatedRepo"})
    )
    harness = Harness(tmp_path, [model], transport)

    assert harness.download() is False

    assert harness.codes() == ["gated"]
    assert len(transport.calls) == 1
    assert harness.sleeps == []


def test_a_missing_repo_is_named_not_found_and_not_retried(tmp_path):
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    transport = Transport(
        lambda url, headers: Response(401, headers={"X-Error-Code": ""})
    )
    harness = Harness(tmp_path, [model], transport)

    assert harness.download() is False

    assert harness.codes() == ["not_found"]
    assert len(transport.calls) == 1
    assert harness.sleeps == []


def test_a_404_is_not_found_and_not_retried(tmp_path):
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    transport = Transport(lambda url, headers: Response(404))
    harness = Harness(tmp_path, [model], transport)

    assert harness.download() is False

    assert harness.codes() == ["not_found"]
    assert len(transport.calls) == 1


# ---------------------------------------------------------------------------
# AC-2: the cache root
# ---------------------------------------------------------------------------


def test_default_cache_dir_honours_hf_hub_cache():
    assert fetch.default_cache_dir({"HOME": "/Users/test"}) == (
        "/Users/test/.cache/huggingface/hub"
    )
    assert fetch.default_cache_dir(
        {"HOME": "/Users/test", "HF_HUB_CACHE": "/Volumes/scratch/hub"}
    ) == "/Volumes/scratch/hub"


def test_an_injected_cache_dir_wins_over_hf_hub_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "elsewhere"))
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    harness = Harness(tmp_path, [model], serve({"weights.safetensors": WEIGHTS}))

    assert harness.download() is True

    assert (harness.blobs / SHA).exists()
    assert not (tmp_path / "elsewhere").exists()


def test_a_corrupt_ledger_makes_download_refuse_before_any_write(tmp_path):
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    harness = Harness(tmp_path, [model], serve({"weights.safetensors": WEIGHTS}))
    harness.ledger.parent.mkdir(parents=True)
    harness.ledger.write_text("[]")

    assert harness.download() is False

    assert harness.codes() == ["ledger_unreadable"]
    assert not harness.cache.exists()


# ---------------------------------------------------------------------------
# 15. fetch.downloaded: sizes and links only, never a hash (AC-1)
# ---------------------------------------------------------------------------


def cached(tmp_path):
    """A model downloaded into a scratch cache, with its Harness returned."""
    transport = serve({"weights.safetensors": WEIGHTS, "config.json": CONFIG})
    harness = Harness(tmp_path, [make_model(TWO_FILES)], transport)
    assert harness.download() is True
    return harness


def test_downloaded_is_true_only_once_the_whole_tree_is_there(tmp_path):
    harness = cached(tmp_path)
    model = harness.models[0]

    assert fetch.downloaded(model, str(harness.cache)) is True


def test_downloaded_is_false_and_writes_nothing_before_a_download(tmp_path):
    model = make_model(TWO_FILES)
    harness = Harness(tmp_path, [model], serve({}))

    assert fetch.downloaded(model, str(harness.cache)) is False
    assert not harness.cache.exists(), "downloaded must never create the cache"


def test_downloaded_is_false_for_a_partial_incomplete_download(tmp_path):
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    harness = Harness(tmp_path, [model], serve({}))
    incomplete = harness.blobs / f"{SHA}.incomplete"
    incomplete.parent.mkdir(parents=True)
    incomplete.write_bytes(WEIGHTS[:5])

    assert fetch.downloaded(model, str(harness.cache)) is False


def test_downloaded_is_false_for_a_blob_of_the_wrong_size(tmp_path):
    harness = cached(tmp_path)

    (harness.blobs / SHA).write_bytes(WEIGHTS[:5])

    assert fetch.downloaded(harness.models[0], str(harness.cache)) is False


def test_downloaded_is_false_when_a_snapshot_link_is_missing(tmp_path):
    harness = cached(tmp_path)

    (harness.snapshot / "config.json").unlink()

    assert fetch.downloaded(harness.models[0], str(harness.cache)) is False


def test_downloaded_checks_sizes_not_hashes(tmp_path):
    """AC-1: the request path cannot hash a multi-GB file. A same-size, wrong-bytes blob
    reads as downloaded here; ``_verify`` is what catches it, after a transfer."""
    harness = cached(tmp_path)

    (harness.blobs / SHA).write_bytes(b"HELLO WORLD")

    assert fetch.downloaded(harness.models[0], str(harness.cache)) is True


def test_downloaded_propagates_plans_value_error(tmp_path):
    model = make_model(TWO_FILES, repo="org/../../etc")

    with pytest.raises(ValueError):
        fetch.downloaded(model, str(tmp_path / "hub"))


# ---------------------------------------------------------------------------
# 16. Byte-level progress while a file is in flight (AC-4)
# ---------------------------------------------------------------------------


def in_flight(harness):
    """The progress events carrying the in-flight payload, in emitted order."""
    return [
        event
        for event in harness.events
        if event["type"] == "progress" and "bytes_total" in event["payload"]
    ]


def test_in_flight_progress_is_byte_level_throttled_and_monotonic(tmp_path):
    body = b"x" * 1_000
    model = make_model([("weights.safetensors", body, "lfs")])
    clock = Clock()
    transport = serve(
        {"weights.safetensors": body}, chunk=100, on_read=lambda _response: clock.advance(0.25)
    )
    harness = Harness(tmp_path, [model], transport)

    assert harness.download(clock=clock) is True

    events = in_flight(harness)
    # Ten chunks of 10%: the first emits, then the 0.5 s gate admits every second chunk --
    # without it there would be one event per chunk (nine).
    assert [event["fraction"] for event in events] == [0.1, 0.3, 0.5, 0.7, 0.9]
    assert [event["payload"] for event in events] == [
        {"path": "weights.safetensors", "bytes_done": done, "bytes_total": 1_000}
        for done in (100, 300, 500, 700, 900)
    ]
    fractions = [event["fraction"] for event in harness.events if event["type"] == "progress"]
    assert fractions == sorted(fractions), "an emitted fraction never goes backwards"
    assert harness.events[-3]["payload"] == {
        "path": "weights.safetensors",
        "bytes": 1_000,
    }, "the per-file completion event is kept"


def test_in_flight_progress_needs_the_fraction_to_have_advanced(tmp_path):
    """A clock that flies past the time gate still cannot emit per chunk: 0.2% each."""
    body = b"x" * 50_000
    model = make_model([("weights.safetensors", body, "lfs")])
    clock = Clock(0.0)
    transport = serve(
        {"weights.safetensors": body}, chunk=100, on_read=lambda _response: clock.advance(10.0)
    )
    harness = Harness(tmp_path, [model], transport)

    assert harness.download(clock=clock) is True

    assert [event["payload"]["bytes_done"] for event in in_flight(harness)] == list(
        range(300, 50_000, 300)
    )


def test_in_flight_fraction_counts_the_files_already_finished(tmp_path):
    first = b"a" * 1_000
    second = b"b" * 1_000
    model = make_model(
        [("first.safetensors", first, "lfs"), ("second.safetensors", second, "lfs")]
    )
    clock = Clock(0.0)
    transport = serve(
        {"first.safetensors": first, "second.safetensors": second},
        chunk=100,
        on_read=lambda _response: clock.advance(0.25),
    )
    harness = Harness(tmp_path, [model], transport)

    assert harness.download(clock=clock) is True

    second_file = [
        event for event in in_flight(harness) if event["payload"]["path"] == "second.safetensors"
    ]
    # The 1,000 bytes of the finished first file are in every numerator, and the model's
    # 2,000 bytes in every denominator.
    assert [event["payload"]["bytes_done"] for event in second_file] == [
        1_100,
        1_300,
        1_500,
        1_700,
        1_900,
    ]
    assert [event["fraction"] for event in second_file] == [0.55, 0.65, 0.75, 0.85, 0.95]
    assert {event["payload"]["bytes_total"] for event in second_file} == {2_000}


def test_a_resumed_download_starts_its_fraction_from_the_bytes_on_disk(tmp_path):
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    clock = Clock(50.0)
    transport = serve(
        {"weights.safetensors": WEIGHTS}, chunk=3, on_read=lambda _response: clock.advance(1.0)
    )
    harness = Harness(tmp_path, [model], transport)
    incomplete = harness.blobs / f"{SHA}.incomplete"
    incomplete.parent.mkdir(parents=True)
    incomplete.write_bytes(WEIGHTS[:5])

    assert harness.download(clock=clock) is True

    events = in_flight(harness)
    assert events[0]["fraction"] == 8 / 11
    assert events[0]["payload"] == {
        "path": "weights.safetensors",
        "bytes_done": 8,
        "bytes_total": 11,
    }
    fractions = [event["fraction"] for event in harness.events if event["type"] == "progress"]
    assert fractions == sorted(fractions)
    assert fractions[-1] == 1.0


def test_a_file_no_larger_than_one_chunk_emits_only_the_per_file_event(tmp_path):
    body = b"x" * 500  # one chunk, whatever the clock does
    model = make_model([("weights.safetensors", body, "lfs")])
    clock = Clock(0.0)
    transport = serve(
        {"weights.safetensors": body}, on_read=lambda _response: clock.advance(10.0)
    )
    harness = Harness(tmp_path, [model], transport)

    assert harness.download(clock=clock) is True

    assert [event["type"] for event in harness.events] == [
        "log",
        "progress",
        "result",
        "done",
    ]
    assert in_flight(harness) == []
    assert harness.events[1]["fraction"] == 1.0
    assert harness.events[1]["payload"] == {"path": "weights.safetensors", "bytes": 500}


# --- lock ownership by process identity (05-09 AC-6) ---


def test_lock_records_identity_and_release_removes_it(tmp_path):
    lock = tmp_path / fetch.LOCK_NAME
    assert fetch._acquire_lock(str(lock)) is True
    pid, _identity = fetch._read_lock(str(lock))
    assert pid == os.getpid()
    fetch._release_lock(str(lock))
    assert not lock.exists()


def test_json_lock_with_matching_live_identity_is_busy(tmp_path):
    from ohyesmlx import runtimes

    ident = runtimes._own_identity()
    lock = tmp_path / fetch.LOCK_NAME
    lock.write_text(json.dumps({"pid": os.getpid(), "lstart": ident[0], "argv": ident[1]}))
    assert fetch._acquire_lock(str(lock)) is False


def test_json_lock_with_mismatched_identity_is_reclaimed(tmp_path):
    lock = tmp_path / fetch.LOCK_NAME
    lock.write_text(json.dumps({"pid": os.getpid(), "lstart": "x", "argv": "not this"}))
    assert fetch._acquire_lock(str(lock)) is True
    fetch._release_lock(str(lock))


def test_old_empty_lock_is_reclaimed(tmp_path):
    lock = tmp_path / fetch.LOCK_NAME
    lock.write_text("")
    old = time.time() - fetch.LOCK_WRITE_WINDOW_S - 5
    os.utime(lock, (old, old))
    assert fetch._acquire_lock(str(lock)) is True
    fetch._release_lock(str(lock))


# ---------------------------------------------------------------------------
# 05-10 Task 1: write errors, flush, ledgered repair, evict ref, missing_bytes
# ---------------------------------------------------------------------------


def test_a_write_error_is_not_retried_as_a_network_error(tmp_path, monkeypatch):
    """AC-1: only ``response.read`` is inside the catch; ENOSPC from the partial's write
    is a disk fault, so one request is made and the OSError is not swallowed."""
    import errno

    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    transport = serve({"weights.safetensors": WEIGHTS})
    harness = Harness(tmp_path, [model], transport)

    class FullDisk:
        def __init__(self, handle):
            self._handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self._handle.close()
            return False

        def write(self, data):
            raise OSError(errno.ENOSPC, "No space left on device")

    real_open = open
    monkeypatch.setattr(
        fetch,
        "open",
        lambda path, mode="r", *a, **k: (
            FullDisk(real_open(path, mode, *a, **k)) if str(path).endswith(".incomplete")
            else real_open(path, mode, *a, **k)
        ),
        raising=False,
    )

    with pytest.raises(OSError) as raised:
        harness.download()

    assert raised.value.errno == errno.ENOSPC
    assert len(transport.calls) == 1
    assert harness.sleeps == []
    # the lock is released and the residue is ledgered even though the call raised
    assert not (harness.locks / fetch.LOCK_NAME).exists()
    recorded = ledger_of(harness)["repos"][REPO]["created_blobs"]
    assert str(harness.blobs / f"{SHA}.incomplete") in recorded


def test_the_partial_is_flushed_before_the_rename_and_the_blobs_dir_after(tmp_path, monkeypatch):
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    harness = Harness(tmp_path, [model], serve({"weights.safetensors": WEIGHTS}))
    seen = []

    def flush(fd):
        seen.append((os.path.exists(harness.blobs / SHA), os.fstat(fd).st_mode))

    monkeypatch.setattr(fetch, "_flush", flush)

    assert harness.download() is True

    # first flush: the partial, blob not yet in place; second: the directory, blob in place
    assert [placed for placed, _ in seen] == [False, True]
    import stat

    assert stat.S_ISREG(seen[0][1]) and stat.S_ISDIR(seen[1][1])


def test_flush_falls_back_to_fsync_when_full_fsync_is_unavailable(tmp_path, monkeypatch):
    import fcntl

    synced = []
    monkeypatch.setattr(fcntl, "fcntl", lambda *a: (_ for _ in ()).throw(OSError("no")))
    monkeypatch.setattr(os, "fsync", synced.append)
    fetch._flush(7)
    assert synced == [7]


def test_a_ledgered_blob_that_fails_verification_is_removed_and_fetched_again(tmp_path):
    """AC-4: a blob this app created (the ledger lists it) that no longer verifies is
    repaired, not refused with 'nothing was overwritten'."""
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    transport = serve({"weights.safetensors": WEIGHTS})
    harness = Harness(tmp_path, [model], transport)
    assert harness.download() is True
    blob = harness.blobs / SHA
    blob.write_bytes(b"HELLO WORLD")  # same size, other bytes: the power-loss shape
    harness.events.clear()

    assert harness.download() is True

    assert blob.read_bytes() == WEIGHTS
    assert harness.codes() == []
    assert len(transport.calls) == 2


def test_a_bad_blob_the_ledger_does_not_list_is_still_refused(tmp_path):
    """The ledger names a different blob of this repo, not this one: still the user's."""
    model = make_model(TWO_FILES)
    transport = serve({"weights.safetensors": WEIGHTS, "config.json": CONFIG})
    harness = Harness(tmp_path, [model], transport)
    harness.blobs.mkdir(parents=True)
    (harness.blobs / SHA).write_bytes(b"HELLO WORLD")
    harness.ledger.parent.mkdir(parents=True)
    harness.ledger.write_text(
        json.dumps(
            {
                "version": 1,
                "repos": {
                    REPO: {
                        "created_blobs": [str(harness.blobs / GIT)],
                        "created_links": [],
                        "created_dirs": [],
                        "revision": REV,
                        "time": 1.0,
                        "bytes": 18,
                    }
                },
            }
        )
    )

    assert harness.download() is False

    assert harness.codes() == ["integrity_failed"]
    assert (harness.blobs / SHA).read_bytes() == b"HELLO WORLD"
    assert transport.calls == []


def test_evict_keeps_a_refs_main_it_cannot_read(tmp_path):
    model = make_model([("weights.safetensors", WEIGHTS, "lfs")])
    harness = Harness(tmp_path, [model], serve({"weights.safetensors": WEIGHTS}))
    assert harness.download() is True
    harness.ref.unlink()
    harness.ref.mkdir()  # unreadable as a file

    assert harness.evict() is True

    assert harness.ref.is_dir()
    assert any("refs" in event["message"] for event in harness.events if event["type"] == "log")


def test_missing_bytes_is_stat_only_and_present_overrides_it(tmp_path):
    model = make_model(TWO_FILES)  # 11 + 7 bytes
    cache = str(tmp_path / "hub")
    blobs = tmp_path / "hub" / "models--org--name" / "blobs"
    assert fetch.missing_bytes(model, cache) == 18

    blobs.mkdir(parents=True)
    (blobs / f"{SHA}.incomplete").write_bytes(WEIGHTS[:5])
    assert fetch.missing_bytes(model, cache) == 6 + 7

    # right size, wrong bytes: stat-only counts it as present (it never hashes)
    (blobs / SHA).write_bytes(b"HELLO WORLD")
    assert fetch.missing_bytes(model, cache) == 7
    # a wrong-sized file does not
    (blobs / SHA).write_bytes(b"short")
    assert fetch.missing_bytes(model, cache) == 6 + 7

    # a symlink is never a present blob
    (blobs / SHA).unlink()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.write_bytes(WEIGHTS)
    os.symlink(elsewhere, blobs / SHA)
    assert fetch.missing_bytes(model, cache) == 6 + 7

    assert fetch.missing_bytes(model, cache, present={"weights.safetensors": True, "config.json": False}) == 7
