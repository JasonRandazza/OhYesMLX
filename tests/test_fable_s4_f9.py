"""S4-F9: a failed stage-B sibling download leaves its ledgered partial unreported.

`quickbench.run` adds a sibling to `outstanding` only after `download` returns True, so a
download that fails part-way is neither evicted after its cell nor swept by the run's
`finally`, and the run still ends "finished". The sibling fetch's own events go to
`quickbench._discard`, so a refusal's code never reaches the skipped cell's reason.

Fakes only: the downloader leaves the `.incomplete` and the ledger entry a failed real
transfer leaves (`fetch.fetch_file`, fetch.py:1124-1135, recorded by `download`'s `finally`
at fetch.py:715-718), then emits the `error` event `fetch._refuse` emits and returns False.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

from test_quickbench import (
    CHOSEN,
    ENGINES,
    MODELS,
    SIBLING,
    CancelAfter,
    FakeClock,
    FakeLoad,
    FakeOsaurus,
    FakeRunCells,
    PortProbe,
)

from ohyesmlx import fetch, quickbench


class RefusingSiblingCache:
    """The downloader, evictor and downloaded check, with failing sibling downloads.

    `download` leaves the `.incomplete` and the ledger entry a real failed transfer leaves,
    emits the refusal `fetch._refuse` emits, and returns False. `evict` removes exactly that
    repo's partial, so a run that evicted its failed download would leave no file behind.
    """

    def __init__(self, cache_dir, log):
        self.repos = {CHOSEN.repo}
        self.cache_dir = str(cache_dir)
        self.ledger_path = fetch.ledger_for(self.cache_dir)
        self.log = log
        self.downloads = []
        self.evicts = []
        self.partials = {}

    def downloaded(self, model, cache_dir=None):
        return model.repo in self.repos

    def _partial_for(self, repo):
        return os.path.join(
            self.cache_dir, "blobs", repo.replace("/", "--") + ".incomplete"
        )

    def _ledger_add(self, repo, partial):
        ledger = {"repos": {}}
        if os.path.exists(self.ledger_path):
            with open(self.ledger_path, encoding="utf-8") as handle:
                ledger = json.load(handle)
        ledger["repos"][repo] = {
            "created_blobs": [partial],
            "created_links": [],
            "created_dirs": [],
            "revision": "a" * 40,
            "time": 0.0,
            "bytes": 1024,
        }
        with open(self.ledger_path, "w", encoding="utf-8") as handle:
            json.dump(ledger, handle)

    def download(self, repo, confirmed, *, cache_dir=None, emit=None):
        self.downloads.append(repo)
        self.log.append(("download", repo))
        partial = self._partial_for(repo)
        os.makedirs(os.path.dirname(partial), exist_ok=True)
        with open(partial, "wb") as handle:
            handle.write(b"p" * 1024)  # 2.5 of 3 GB, in miniature
        self.partials[repo] = partial
        self._ledger_add(repo, partial)
        # fetch._refuse's own shape: an `error` carrying the code, then the stream's `done`.
        emit(
            {
                "seq": 1,
                "type": "error",
                "message": f"{repo} refused: another download is already running",
                "fraction": None,
                "payload": {"code": "busy"},
            }
        )
        emit(
            {
                "seq": 2,
                "type": "done",
                "message": "fetch ended",
                "fraction": None,
                "payload": None,
            }
        )
        return False

    def evict(self, repo, confirmed, *, cache_dir=None, emit=None):
        self.evicts.append(repo)
        self.log.append(("evict", repo))
        self.repos.discard(repo)
        partial = self.partials.pop(repo, None)
        if partial and os.path.exists(partial):
            os.remove(partial)
        return True


def a_run(tmp_path):
    log = []
    events = []
    cache = RefusingSiblingCache(tmp_path / "cache", log)
    fake_osaurus = FakeOsaurus(log=log)
    ok = quickbench.run(
        CHOSEN.repo,
        confirmed=True,
        models=MODELS,
        statuses=ENGINES,
        hw=SimpleNamespace(),
        run_cells=FakeRunCells(
            on_call=lambda cell, _kwargs: log.append(("cell", cell.id))
        ),
        download=cache.download,
        evict=cache.evict,
        downloaded=cache.downloaded,
        pin=fake_osaurus.pin,
        restore=fake_osaurus.restore,
        recover=fake_osaurus.recover,
        port_in_use=PortProbe(),
        osaurus_app_running=lambda: False,
        load=FakeLoad(),
        clock=FakeClock(),
        emit=events.append,
        cancel=CancelAfter(None),
        abort=quickbench._never_cancelled,
        cache_dir=str(tmp_path / "cache"),
        results_dir=str(tmp_path / "quickbench"),
        backup_dir=str(tmp_path / "backup"),
        baseline_path=str(tmp_path / "baseline.json"),
    )
    found = sorted((tmp_path / "quickbench").glob("*/summary.json"))
    assert found, "the run wrote no summary"
    summary = json.loads(found[0].read_text(encoding="utf-8"))
    return ok, cache, summary, events


def test_a_failed_sibling_download_is_evicted_or_recorded(tmp_path):
    """The failed download's ledgered partial is neither evicted nor named not_evicted."""
    ok, cache, summary, _events = a_run(tmp_path)

    assert ok is True, "the run did not report itself finished"
    assert summary["ended"] == "finished"
    assert SIBLING.repo in cache.downloads, "the sibling download was never attempted"
    assert os.path.exists(cache.partials[SIBLING.repo]), (
        "precondition: the failed download's ledgered partial is on disk"
    )

    assert (
        SIBLING.repo in cache.evicts or SIBLING.repo in summary["not_evicted"]
    ), (
        f"{SIBLING.repo} failed to download and left "
        f"{cache.partials[SIBLING.repo]} in the fetch ledger, but the run ended "
        f'"finished" without evicting it (evicts={cache.evicts!r}) and without '
        f"recording it (not_evicted={summary['not_evicted']!r})"
    )


def test_a_refused_sibling_download_keeps_the_refusals_code_in_the_cell_reason(tmp_path):
    """The refusal's code reaches the skipped cell instead of being swallowed by _discard."""
    _ok, _cache, summary, _events = a_run(tmp_path)

    cell = next(
        cell for cell in summary["stage_b"]["cells"] if cell["repo"] == SIBLING.repo
    )
    assert cell["status"] == "SKIPPED"
    assert "busy" in cell["reason"], (
        f"the cell's reason is {cell['reason']!r}; the download emitted error code "
        f'"busy" through the emit quickbench handed it, and the reason names no cause'
    )
