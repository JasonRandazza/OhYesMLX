"""Reproduction for Fable 5.2 S4-F4: a stage-B sibling download ignores Stop and Stop now.

The claim: ``quickbench.run`` fetches a missing stage-B sibling with
``download(sibling.repo, True, cache_dir=cache_dir, emit=_discard)``
(``quickbench.py:864-866``), so the ``cancel`` and ``abort`` probes the run already holds
(``quickbench.py:510-511``) never reach the downloader -- a multi-GB fetch runs to the end
before ``cancel()`` is read at ``:891`` -- and every event the download emits is thrown away,
leaving one ``stage B: downloading`` event for the whole fetch.

Each test drives ``quickbench.run`` with every side effect faked (the fakes
``tests/test_quickbench.py`` uses) over a cache that is missing both stage-B siblings. The
downloader records the keywords it was handed and acts inside the call, which is the only
moment a stop pressed *during* a real fetch could be seen. No runtime, no model, no network.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from ohyesmlx import quickbench

from test_quickbench import (
    NO_VERIFY,
    CHOSEN,
    ENGINES,
    MODELS,
    FakeCache,
    FakeClock,
    FakeLoad,
    FakeOsaurus,
    FakeRunCells,
)


class StopProbe:
    """A cancel or "Stop now" probe: false until the test flips it, with its asks counted."""

    def __init__(self):
        self.triggered = False
        self.checks = 0

    def __call__(self):
        self.checks += 1
        return self.triggered


class SiblingDownload:
    """The stage-B downloader: records the keywords handed to it, then runs ``during``.

    A real sibling fetch takes minutes, so the callable the run hands in is the only way a
    stop landing mid-fetch can be observed before the transfer ends.
    """

    def __init__(self, during=None):
        self.calls = []
        self.during = during

    def __call__(self, repo, confirmed, *, cache_dir=None, emit=None, **kwargs):
        recorded = {
            "repo": repo,
            "confirmed": confirmed,
            "cache_dir": cache_dir,
            "emit": emit,
        }
        recorded.update(kwargs)
        self.calls.append(recorded)
        if self.during is not None:
            self.during(recorded)
        return True


def a_stage_b_run(tmp_path, download, *, cancel=None, abort=None):
    """One quickbench run over the chosen row with both siblings missing and all else faked."""
    log = []
    cache = FakeCache(downloaded=(CHOSEN.repo,), log=log)
    osaurus = FakeOsaurus(log=log)
    events = []
    ok = quickbench.run(
        CHOSEN.repo,
        confirmed=True,
        osaurus=False,
        models=MODELS,
        statuses=ENGINES,
        hw=SimpleNamespace(),
        run_cells=FakeRunCells(on_call=lambda cell, _kwargs: log.append(("cell", cell.id))),
        download=download,
        evict=cache.evict,
        downloaded=cache.downloaded,
        pin=osaurus.pin,
        restore=osaurus.restore,
        recover=osaurus.recover,
        port_refusal=lambda name: None,
        verify=NO_VERIFY,
        osaurus_app_running=lambda: False,
        load=FakeLoad((1.0,)),
        clock=FakeClock(),
        emit=events.append,
        cancel=cancel if cancel is not None else quickbench._never_cancelled,
        abort=abort if abort is not None else quickbench._never_cancelled,
        cache_dir=str(tmp_path / "cache"),
        results_dir=str(tmp_path / "quickbench"),
        backup_dir=str(tmp_path / "backup"),
        baseline_path=str(tmp_path / "baseline.json"),
    )
    return ok, events


def test_a_stage_b_sibling_download_hears_stop(tmp_path):
    probe = StopProbe()

    def press_stop(recorded):
        probe.triggered = True
        stop = recorded.get("cancel")
        recorded["answered_after_stop"] = None if stop is None else bool(stop())

    download = SiblingDownload(press_stop)
    a_stage_b_run(tmp_path, download, cancel=probe)

    first = download.calls[0]
    assert "cancel" in first, (
        "quickbench.run called the stage-B sibling download without a cancel callable, so a "
        "Stop pressed while it fetches is not observed until the transfer ends "
        f"(quickbench.py:864-866; keywords handed in: {sorted(first)})"
    )
    assert first["answered_after_stop"] is True, (
        "the callable handed to the stage-B download did not answer True after the run's "
        "own cancel probe was set, so the download cannot stop early"
    )


def test_a_stage_b_sibling_download_hears_stop_now(tmp_path):
    abort = StopProbe()

    def press_stop_now(recorded):
        abort.triggered = True
        stop = recorded.get("cancel")
        recorded["answered_after_stop_now"] = None if stop is None else bool(stop())

    download = SiblingDownload(press_stop_now)
    a_stage_b_run(tmp_path, download, abort=abort)

    first = download.calls[0]
    assert "cancel" in first, (
        "quickbench.run called the stage-B sibling download without a cancel callable, so "
        '"Stop now" is not observed while it fetches '
        f"(quickbench.py:864-866; keywords handed in: {sorted(first)})"
    )
    assert first["answered_after_stop_now"] is True, (
        'the callable handed to the stage-B download did not answer True after the run\'s own '
        'abort probe was set, so "Stop now" cannot stop the fetch'
    )


def test_a_stage_b_sibling_downloads_progress_reaches_the_caller(tmp_path):
    marker = "org/two-b-oq4: config.json 25%"

    def report_progress(recorded):
        emit = recorded["emit"]
        if emit is not None:
            emit(
                {
                    "type": "progress",
                    "seq": 1,
                    "message": marker,
                    "fraction": 0.25,
                    "payload": {"path": "config.json"},
                }
            )

    download = SiblingDownload(report_progress)
    _ok, events = a_stage_b_run(tmp_path, download)

    messages = [event.get("message") or "" for event in events]
    forwarded = next((i for i, m in enumerate(messages) if marker in m), None)
    assert forwarded is not None, (
        "the stage-B download's own progress event never reached the caller's emitter: "
        "quickbench.py:864-866 hands the downloader emit=_discard, so one "
        "'stage B: downloading' event is the whole report of a multi-GB fetch. The stage-B "
        f"download events the caller received: {json.dumps([m for m in messages if 'download' in m])}"
    )
    start = next(i for i, m in enumerate(messages) if m.startswith("stage B: downloading"))
    cell = next(i for i, m in enumerate(messages) if m.startswith("stage B: oq4 "))
    assert start < forwarded < cell, (
        "download progress must arrive after the stage-B download starts and before its "
        f"cell is measured (start={start}, progress={forwarded}, cell={cell})"
    )


def test_stage_b_progress_is_throttled_to_one_event_per_whole_percent(tmp_path):
    def flood(recorded):
        for i in range(1, 1001):  # 0.1% steps
            recorded["emit"](
                {"type": "progress", "message": f"chunk {i}", "fraction": i / 1000, "payload": {}}
            )

    download = SiblingDownload(flood)
    _ok, events = a_stage_b_run(tmp_path, download)

    forwarded = [
        e for e in events if (e.get("payload") or {}).get("repo") and e["type"] == "progress"
        and (e.get("payload") or {}).get("stage") == "B" and e["message"].startswith("chunk")
    ]
    # two siblings, each at most 101 whole-percent steps (0..100), far below 1000 per sibling
    assert 0 < len(forwarded) <= 2 * 101


class StoppedDownload(SiblingDownload):
    """A sibling fetch that hears a Stop now mid-transfer and gives up, as fetch.download does."""

    def __call__(self, repo, confirmed, **kwargs):
        super().__call__(repo, confirmed, **kwargs)
        return False if kwargs["cancel"]() else True


def test_a_stop_now_heard_by_a_sibling_download_ends_the_run_cancelled(tmp_path):
    """Coordinator check (05-11 T1): a stopped download is not a skip; no later sibling is fetched."""
    abort = StopProbe()
    download = StoppedDownload(lambda _recorded: setattr(abort, "triggered", True))
    _ok, events = a_stage_b_run(tmp_path, download, abort=abort)

    assert len(download.calls) == 1, "a later sibling was fetched after Stop now"
    summary_path = next((tmp_path / "quickbench").rglob("summary.json"))
    summary = json.loads(summary_path.read_text())
    assert summary["ended"] == "cancelled"
    skipped = [c for c in summary["stage_b"]["cells"] if c.get("status") == "SKIPPED"]
    assert skipped and all(
        c["reason"] == "the run was cancelled before this cell" for c in skipped
    ), "a stopped download must read as the cancelled tail, not as 'could not be downloaded'"
