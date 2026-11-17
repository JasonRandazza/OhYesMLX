"""Check for S1-F3: a network error read from a response body must not escape ``download``.

The finding: ``chunk = response.read(CHUNK_SIZE)`` sits inside ``try: ... finally: _close``
with no ``except`` (``ohyesmlx/fetch.py:1066-1077``), so a ``TimeoutError`` raised mid-body
leaves ``_fetch_file``, skips ``fetch_file``'s residue bookkeeping (:1124-1135), and reaches
the server's ``except Exception`` (``server.py:754``) as an unexpected ``internal``. The
retry loop the function is built around never runs for the commonest failure of a long
transfer.

Driven only through the module's injected seams: a fake transport, a literal free-space
number, a sleep and clock that only record, and a ``tmp_path`` cache/ledger/lock/log.
No socket is opened and no real sleep is taken.
"""

from __future__ import annotations

import hashlib
import json

from ohyesmlx import fetch
from ohyesmlx.catalog import Model, ModelFile

REPO = "org/name"
REV = "a" * 40
BODY = bytes(range(100))
SHA = hashlib.sha256(BODY).hexdigest()
CDN = "https://us.aws.cdn.hf.co/xet-bridge-us/x"
CUT = 4  # bytes each response delivers before the connection drops


class CutResponse:
    """A response whose body stalls after ``CUT`` bytes, then raises like a dead socket."""

    def __init__(self, status, body, headers):
        self.status = status
        self.headers = dict(headers)
        self.url = CDN
        self.closed = False
        self._body = body
        self._offset = 0

    def read(self, amount=-1):
        if self._offset >= CUT:
            if self._offset < len(self._body):
                raise TimeoutError("The read operation timed out")
            return b""
        size = amount if amount is not None and amount > 0 else len(self._body)
        end = min(self._offset + size, CUT, len(self._body))
        data = self._body[self._offset : end]
        self._offset = end
        return data

    def close(self):
        self.closed = True


class Transport:
    """Records each request and answers every one with the same mid-body drop."""

    def __init__(self):
        self.calls = []

    def __call__(self, url, headers=None):
        recorded = dict(headers or {})
        self.calls.append((url, recorded))
        requested = recorded.get("Range")
        if requested:
            start = int(requested.split("=", 1)[1].rstrip("-"))
            payload = BODY[start:]
            return CutResponse(
                206,
                payload,
                {
                    "Content-Length": str(len(payload)),
                    "Content-Range": f"bytes {start}-{len(BODY) - 1}/{len(BODY)}",
                },
            )
        return CutResponse(200, BODY, {"Content-Length": str(len(BODY))})


def make_model():
    entry = ModelFile(
        path="weights.safetensors",
        size=len(BODY),
        sha256=SHA,
        git_oid=None,
    )
    return Model(
        repo=REPO,
        title="A model",
        params=1,
        format="4bit",
        modality="text",
        license="mit",
        tier="starter",
        revision=REV,
        size_bytes=len(BODY),
        files=[entry],
        engines=["mlxlm"],
        measured_here=False,
        notes="",
    )


def test_a_mid_body_timeout_is_retried_and_never_escapes_download(tmp_path):
    transport = Transport()
    cache = tmp_path / "hub"
    support = tmp_path / "support"
    ledger = support / "fetched.json"
    events = []
    sleeps = []

    result = fetch.download(
        REPO,
        True,
        models=[make_model()],
        cache_dir=str(cache),
        ledger_path=str(ledger),
        log_path=str(support / "fetch-log.jsonl"),
        lock_dir=str(support / "locks"),
        open_url=transport,
        sleep=sleeps.append,
        clock=lambda: 1234.5,
        emit=events.append,
        cancel=lambda: False,
    )

    assert result is False, "a dropped body must end the download, not escape it"
    assert len(transport.calls) > 1, "the mid-body failure must reach the retry loop"
    assert sleeps, "a retry must back off"

    codes = [event["payload"]["code"] for event in events if event["type"] == "error"]
    assert codes, "a failed transfer must emit its own refusal"
    assert set(codes) <= {"http_error", "size_mismatch"}, codes
    assert not (support / "locks" / fetch.LOCK_NAME).exists()

    incomplete = cache / "models--org--name" / "blobs" / f"{SHA}.incomplete"
    if incomplete.exists():
        recorded = json.loads(ledger.read_text())["repos"][REPO]["created_blobs"]
        assert str(incomplete) in recorded, "evict can only remove what the ledger names"
