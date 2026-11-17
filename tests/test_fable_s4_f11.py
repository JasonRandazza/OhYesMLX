"""S4-F11: quick-bench's eviction deletes the user's own partial download of a sibling.

The consent copy promises one *extra* download and that only what the run downloaded is taken
back out (quickbench.py:20 "The user's chosen model stays. Only a sibling this run downloaded
is ever evicted"; the app's Stage B row at `BenchmarkView.swift:175-180` says "already on
disk" or "one extra download"). But stage B decides with `if not sibling_plan.downloaded:`
(quickbench.py:852), and `downloaded` is a whole-repo question (fetch.py:272-298, UAT-001).
So a repo the user downloaded to 80% from the Models screen reads as *not* downloaded; the
run resumes it to 100%, `fetched` becomes True (:864-866), the cell is measured, and the inner
`finally` calls `evict(sibling.repo, True, ...)` (:914-921).

`evict` removes every path in that **repo's** ledger entry (fetch.py:1250-1277), and
`fetch._record` merges each download into the one entry it already has, never replacing it
(fetch.py:721-745) -- so the eviction deletes the 80% the user fetched deliberately along with
the 20% this run fetched.

The test seeds that exact state with the real `fetch` functions. The user's partial is written
and ledgered the way an interrupted real `download` leaves it, and the run gets the real
`downloaded` and `evict`. No network, no model, no runtime: the cache is a scratch directory
and every file is a hundred bytes.
"""

from __future__ import annotations

import json
import os
from dataclasses import replace
from types import SimpleNamespace

from test_quickbench import (
    ENGINES,
    FakeClock,
    FakeLoad,
    FakeOsaurus,
    FakeRunCells,
    PortProbe,
    a_model,
)

from ohyesmlx import fetch, quickbench

NOW = 1_700_000_000.0
CHOSEN_REPO = "org/small-stock"
SIBLING_REPO = "org/small-oq4"
OTHER_REPO = "org/small-jang"


def _discard(_event):
    return None


def a_small_row(repo, fmt, *, size=400):
    """One catalog row whose single LFS file is small enough to write in a test."""
    row = a_model(repo, fmt, "Small", size_bytes=size)
    return replace(
        row,
        files=[
            __import__("ohyesmlx.catalog", fromlist=["ModelFile"]).ModelFile(
                path="model.safetensors", size=size, sha256="c" * 64, git_oid=None
            )
        ],
    )


CHOSEN = a_small_row(CHOSEN_REPO, "stock4bit")
SIBLING = a_small_row(SIBLING_REPO, "oq4")
OTHER = a_small_row(OTHER_REPO, "jang4")
MODELS = [CHOSEN, SIBLING, OTHER]


def materialize(cache_dir, model):
    """A completed download's end state: the blob, its snapshot link, and an empty ledger."""
    planned = fetch.plan(model, cache_dir)
    planned_file = planned.files[0]
    os.makedirs(planned.blobs_dir, exist_ok=True)
    with open(planned_file.blob, "wb") as handle:
        handle.write(b"b" * planned_file.size)
    os.makedirs(planned.snapshot_dir, exist_ok=True)
    os.symlink(planned_file.blob, planned_file.link)
    return planned


class UserPartialThenRunDownload:
    """The user's own 80% download of a sibling, then the run's resume of that same repo."""

    def __init__(self, cache_dir, model):
        self.cache_dir = str(cache_dir)
        self.model = model
        self.ledger_path = fetch.ledger_for(self.cache_dir)
        self.downloads = []
        self.evicts = []
        self.planned = fetch.plan(model, self.cache_dir)
        self.planned_file = self.planned.files[0]
        self.incomplete = self.planned_file.blob + ".incomplete"

    def write_the_users_partial(self):
        """What an interrupted download leaves: 80% of the blob, on the ledger, no link."""
        os.makedirs(self.planned.blobs_dir, exist_ok=True)
        with open(self.incomplete, "wb") as handle:
            handle.write(b"u" * int(self.planned_file.size * 0.8))
        created = {"blobs": [self.incomplete], "links": [], "dirs": []}
        fetch._record(self.ledger_path, self.planned, created, lambda: NOW, _discard)

    def downloaded(self, model, cache_dir=None):
        return fetch.downloaded(model, cache_dir)

    def download(self, repo, confirmed, *, cache_dir=None, emit=None):
        """Stage B's fetch: finish the user's partial, then link the snapshot like `download`."""
        self.downloads.append(repo)
        remaining = self.planned_file.size - os.path.getsize(self.incomplete)
        with open(self.incomplete, "ab") as handle:
            handle.write(b"r" * remaining)
        os.replace(self.incomplete, self.planned_file.blob)
        os.makedirs(self.planned.snapshot_dir, exist_ok=True)
        os.symlink(self.planned_file.blob, self.planned_file.link)
        os.makedirs(self.planned.refs_dir, exist_ok=True)
        with open(self.planned.ref_path, "w", encoding="utf-8") as handle:
            handle.write(self.model.revision)
        created = {
            "blobs": [self.planned_file.blob],
            "links": [self.planned_file.link],
            "dirs": [],
        }
        fetch._record(self.ledger_path, self.planned, created, lambda: NOW, _discard)
        return True

    def evict(self, repo, confirmed, *, cache_dir=None, emit=None):
        """The real evictor: it removes every path the per-repo ledger entry lists."""
        self.evicts.append(repo)
        return fetch.evict(
            repo,
            confirmed,
            cache_dir=self.cache_dir,
            ledger_path=self.ledger_path,
            lock_dir=os.path.join(self.cache_dir, "locks"),
            emit=_discard,
        )


def a_run(tmp_path, cache, events):
    ok = quickbench.run(
        CHOSEN.repo,
        confirmed=True,
        models=MODELS,
        statuses=ENGINES,
        hw=SimpleNamespace(),
        run_cells=FakeRunCells(),
        download=cache.download,
        evict=cache.evict,
        downloaded=cache.downloaded,
        pin=FakeOsaurus().pin,
        restore=FakeOsaurus().restore,
        recover=FakeOsaurus().recover,
        port_in_use=PortProbe(),
        osaurus_app_running=lambda: False,
        load=FakeLoad(),
        clock=FakeClock(),
        emit=events.append,
        cancel=quickbench._never_cancelled,
        abort=quickbench._never_cancelled,
        cache_dir=cache.cache_dir,
        results_dir=str(tmp_path / "quickbench"),
        backup_dir=str(tmp_path / "backup"),
        baseline_path=str(tmp_path / "baseline.json"),
    )
    summary_path = sorted((tmp_path / "quickbench").glob("*/summary.json"))[0]
    return ok, json.loads(summary_path.read_text(encoding="utf-8"))


def test_the_users_own_partial_of_a_sibling_survives_the_runs_eviction(tmp_path):
    cache = UserPartialThenRunDownload(tmp_path / "cache", SIBLING)
    materialize(cache.cache_dir, CHOSEN)
    cache.write_the_users_partial()

    # Preconditions: the user's bytes are on disk and on the ledger, and the row still reads
    # as not downloaded -- which is exactly why stage B fetches it.
    assert os.path.getsize(cache.incomplete) > 0
    with open(cache.ledger_path, encoding="utf-8") as handle:
        entry = json.load(handle)["repos"][SIBLING.repo]
    assert entry["created_blobs"] == [cache.incomplete]
    assert fetch.downloaded(SIBLING, cache.cache_dir) is False, (
        "precondition: an 80% partial is not a download, so stage B treats the row as missing"
    )

    ok, summary = a_run(tmp_path, cache, [])

    assert ok is True
    assert SIBLING.repo in cache.downloads, "precondition: stage B downloaded the sibling"

    # The user's 80% was fetched from the Models screen before the run and is theirs; the run
    # only ever added the remaining 20%. Those bytes must still be readable in the cache
    # afterwards -- as the blob or as a resume-able `.incomplete`.
    survivor = None
    for path in (cache.planned_file.blob, cache.incomplete):
        if os.path.exists(path):
            with open(path, "rb") as handle:
                survivor = handle.read(int(cache.planned_file.size * 0.8))
            break
    assert survivor is not None, (
        f"the run's eviction removed every byte of {SIBLING.repo}, including the 80% partial "
        f"the user had already downloaded from the Models screen before the run -- neither "
        f"{os.path.basename(cache.planned_file.blob)} nor its .incomplete is on disk; the "
        f"summary reports not_evicted={summary['not_evicted']!r} and ended={summary['ended']!r}"
    )
    assert set(survivor) == {ord("u")}, (
        f"the bytes left for {SIBLING.repo} are not the user's: the partial the run resumed "
        f"was replaced rather than preserved"
    )
