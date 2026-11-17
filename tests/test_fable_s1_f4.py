"""S1-F4: the per-file retry budget is never reset by progress, and exhausting it deletes
a valid partial.

``_fetch_file`` sets ``attempts = 0`` once before ``while True`` (fetch.py:916) and only
increments it on a failed pass. Four short closes spread across a transfer -- each one
after the file grew -- therefore reach the ``attempts + 1 >= MAX_ATTEMPTS`` branch
(fetch.py:1112-1118), which calls ``size_mismatch(..., remove=incomplete)`` and unlinks
every correctly received byte. A user cancel keeps the same partial "for a resume"
(fetch.py:769).

The transport here honours Range and closes after exactly one further byte, so every pass
makes progress: the transfer would finish if the budget were per-pass rather than
cumulative. Scaled down from the finding's 20 GB / gigabytes-per-pass to 10 bytes / 1 byte
per pass; nothing in the code path depends on the magnitude.
"""

from __future__ import annotations

import hashlib
import os

from ohyesmlx import fetch
from ohyesmlx.catalog import Model, ModelFile

REPO = "org/name"
REV = "a" * 40
BODY = b"0123456789"
SHA = hashlib.sha256(BODY).hexdigest()
CDN = "https://us.aws.cdn.hf.co/xet-bridge-us/x"


class ShortResponse:
    """A 206 that carries exactly one byte at *start* and then reads as EOF."""

    def __init__(self, start, total):
        self.status = 206
        self.headers = {
            "Content-Length": "1",
            "Content-Range": f"bytes {start}-{start}/{total}",
        }
        self.url = CDN
        self._start = start
        self._sent = False

    def read(self, amount=-1):
        if self._sent:
            return b""
        self._sent = True
        return BODY[self._start : self._start + 1]

    def close(self):
        pass


class FullResponse:
    """A 200/206 that serves the whole remaining body and ends cleanly."""

    def __init__(self, start, total):
        self.status = 200 if start == 0 else 206
        payload = BODY[start:]
        self.headers = {"Content-Length": str(len(payload))}
        if start:
            self.headers["Content-Range"] = f"bytes {start}-{total - 1}/{total}"
        self.url = CDN
        self._payload = payload
        self._sent = False

    def read(self, amount=-1):
        if self._sent:
            return b""
        self._sent = True
        return self._payload

    def close(self):
        pass


def model():
    return Model(
        repo=REPO,
        title="A model",
        params=10,
        format="4bit",
        modality="text",
        license="mit",
        tier="starter",
        revision=REV,
        size_bytes=len(BODY),
        files=[
            ModelFile(
                path="weights.safetensors",
                size=len(BODY),
                sha256=SHA,
                git_oid=None,
            )
        ],
        engines=["mlxlm"],
        measured_here=False,
        notes="",
    )


class Run:
    def __init__(self, tmp_path, open_url):
        self.cache = tmp_path / "hub"
        self.support = tmp_path / "support"
        self.events = []
        self.sleeps = []
        self.open_url = open_url

    def download(self):
        return fetch.download(
            REPO,
            True,
            models=[model()],
            cache_dir=str(self.cache),
            ledger_path=str(self.support / "fetched.json"),
            log_path=str(self.support / "fetch-log.jsonl"),
            lock_dir=str(self.support / "locks"),
            open_url=self.open_url,
            sleep=self.sleeps.append,
            clock=lambda: 1234.5,
            emit=self.events.append,
            cancel=lambda: False,
        )

    def codes(self):
        return [event["payload"]["code"] for event in self.events if event["type"] == "error"]

    @property
    def incomplete(self):
        return self.cache / "models--org--name" / "blobs" / f"{SHA}.incomplete"


def test_a_valid_four_byte_prefix_is_deleted_when_the_cumulative_budget_runs_out(tmp_path):
    sizes_when_asked = []

    def handler(url, headers):
        ranged = (headers or {}).get("Range")
        start = int(ranged.split("=", 1)[1].rstrip("-")) if ranged else 0
        sizes_when_asked.append(
            os.path.getsize(run.incomplete) if os.path.exists(run.incomplete) else 0
        )
        return ShortResponse(start, len(BODY))

    run = Run(tmp_path, handler)

    assert run.download() is False

    # Every one of the four passes wrote a byte before closing: 0, then 1, then 2, then 3
    # bytes were already on disk when the next request was made.
    assert sizes_when_asked == [0, 1, 2, 3]
    assert len(run.sleeps) == 3
    assert run.codes() == ["size_mismatch"]
    # The bytes received so far are a valid prefix of the catalog's file -- the same
    # partial a cancel would have kept (fetch.py:769).
    assert os.path.exists(run.incomplete), (
        "the four-byte prefix was deleted even though every pass made progress and the "
        "bytes are a valid prefix of the catalog's 10-byte file"
    )
    assert run.incomplete.read_bytes() == BODY[:4]


def test_one_short_close_without_exhaustion_keeps_the_partial_until_the_next_pass(tmp_path):
    """Control: a single short close is retried and the transfer completes, so the removal
    in the test above is caused by the cumulative budget, not by a short close itself."""
    passes = []

    def handler(url, headers):
        passes.append((headers or {}).get("Range"))
        ranged = (headers or {}).get("Range")
        start = int(ranged.split("=", 1)[1].rstrip("-")) if ranged else 0
        return ShortResponse(start, len(BODY)) if len(passes) == 1 else FullResponse(
            start, len(BODY)
        )

    run = Run(tmp_path, handler)

    assert run.download() is True

    assert passes == [None, "bytes=1-"]
    assert run.codes() == []
