"""Reproduction for Fable 5.2 S4-F1: stage B does not re-run the skip check.

The claim: stage A calls ``quickbench._skip_reason`` before every cell
(``quickbench.py:776``) but the stage-B loop (``quickbench.py:844-901``) calls ``measured``
with no such check, so an engine whose port went busy -- or an Osaurus app the user opened --
between the two stages is driven into a cell instead of being SKIPPED with its reason.

Each test drives ``quickbench.run`` with every side effect faked (the same fakes
``tests/test_quickbench.py`` uses) and a probe that answers free through stage A and busy
from the first call after it. On the current code the stage-B cell is attempted; the tests
assert the guard's outcome (a SKIPPED cell reading "quit <engine> first", and no stage-B
``run_cells`` call), so they fail with the reported symptom. No runtime, no model, no
network.
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
    WITH_OSAURUS,
    FakeCache,
    FakeClock,
    FakeLoad,
    FakeOsaurus,
    FakeRunCells,
)


class BusyAfterStageA:
    """The port probe: free for stage A's asks, busy from the first call after them."""

    def __init__(self, free_asks):
        self.free = free_asks
        self.asks = 0
        self.ports = []

    def __call__(self, name):
        self.asks += 1
        self.ports.append(name)
        return f"quit {name} first" if self.asks > self.free else None


class AppOpensAfterStageA:
    """The Osaurus app probe: absent for stage A's check, running after it."""

    def __init__(self, absent_asks=1):
        self.absent = absent_asks
        self.asks = 0

    def __call__(self):
        self.asks += 1
        return self.asks > self.absent


def verified_run(
    tmp_path,
    *,
    probe,
    answers=None,
    engines_list=ENGINES,
    osaurus=False,
    app_running=lambda: False,
    cache=None,
):
    """``quickbench.run`` with every side effect faked, the probe under the test's control."""
    cache = cache or FakeCache(downloaded=(CHOSEN.repo,))
    fake_osaurus = FakeOsaurus()
    events = []
    cells = FakeRunCells(answers)
    ok = quickbench.run(
        CHOSEN.repo,
        confirmed=True,
        osaurus=osaurus,
        models=MODELS,
        statuses=engines_list,
        hw=SimpleNamespace(),
        run_cells=cells,
        download=cache.download,
        evict=cache.evict,
        downloaded=cache.downloaded,
        pin=fake_osaurus.pin,
        restore=fake_osaurus.restore,
        recover=fake_osaurus.recover,
        osaurus_drift=lambda **kwargs: None,
        port_refusal=probe,
        verify=NO_VERIFY,
        osaurus_app_running=app_running,
        load=FakeLoad((1.0,)),
        clock=FakeClock(),
        emit=events.append,
        cancel=quickbench._never_cancelled,
        abort=quickbench._never_cancelled,
        cache_dir=str(tmp_path / "cache"),
        results_dir=str(tmp_path / "quickbench"),
        backup_dir=str(tmp_path / "backup"),
        baseline_path=str(tmp_path / "baseline.json"),
    )
    found = sorted((tmp_path / "quickbench").glob("*/summary.json"))
    summary = json.loads(found[0].read_text(encoding="utf-8")) if found else None
    return ok, cells, fake_osaurus, summary


def stage_b_siblings(summary):
    """The stage-B cells that are not the reused stage-A winner row."""
    return [cell for cell in summary["stage_b"]["cells"] if not cell.get("reused")]


def test_a_port_that_goes_busy_after_stage_a_is_not_driven_in_stage_b(tmp_path):
    probe = BusyAfterStageA(len(ENGINES))
    ok, cells, _osaurus, summary = verified_run(
        tmp_path,
        probe=probe,
        answers={"mlxlm": ("PASS", 40), "optiq": ("PASS", 60)},
    )

    assert ok is True
    assert summary["stage_a"]["winner"] == "optiq", "the stage-A sanity check"
    siblings = stage_b_siblings(summary)
    assert len(siblings) == 2, "stage B planned the two sibling formats"
    for cell in siblings:
        assert cell["status"] == "SKIPPED", (
            f"stage B {cell['format']} was measured although the winner's port went busy "
            "after stage A"
        )
        assert cell["reason"] == "quit optiq first"
    measured_ids = {call["cells"][0].id for call in cells.calls}
    assert "oq4__optiq" not in measured_ids, "no stage-B cell was driven in stage B"
    assert "jang4__optiq" not in measured_ids, "no stage-B cell was driven in stage B"


def test_an_osaurus_app_opened_after_stage_a_is_not_pinned_for_stage_b(tmp_path):
    app = AppOpensAfterStageA(absent_asks=1)
    ok, cells, osaurus, summary = verified_run(
        tmp_path,
        probe=BusyAfterStageA(len(WITH_OSAURUS)),
        answers={"mlxlm": ("PASS", 40), "osaurus": ("PASS", 80), "optiq": ("PASS", 60)},
        engines_list=WITH_OSAURUS,
        osaurus=True,
        app_running=app,
    )

    assert ok is True
    assert summary["stage_a"]["winner"] == "osaurus", "the stage-A sanity check"
    siblings = stage_b_siblings(summary)
    assert len(siblings) == 2, "stage B planned the two sibling formats"
    for cell in siblings:
        assert cell["status"] == "SKIPPED", (
            f"stage B {cell['format']} ran although the Osaurus app was opened after "
            "stage A"
        )
        assert cell["reason"] == "quit the Osaurus app first"
    pins = [call for call in osaurus.calls if call[0] == "pin"]
    assert len(pins) == 1, "only stage A's own cell pinned the user's settings"
    measured_ids = {call["cells"][0].id for call in cells.calls}
    assert "oq4__osaurus" not in measured_ids, "no stage-B cell was driven in stage B"
    assert "jang4__osaurus" not in measured_ids, "no stage-B cell was driven in stage B"


def test_a_refusal_before_the_download_spends_no_bytes(tmp_path):
    cache = FakeCache(downloaded=(CHOSEN.repo,))
    probe = BusyAfterStageA(len(ENGINES))
    ok, _cells, _osaurus, summary = verified_run(
        tmp_path,
        probe=probe,
        answers={"mlxlm": ("PASS", 40), "optiq": ("PASS", 60)},
        cache=cache,
    )
    assert ok is True
    assert cache.downloads == [], "a refused engine's siblings are not fetched"
    assert all(c["status"] == "SKIPPED" for c in stage_b_siblings(summary))
    assert probe.asks == len(ENGINES) + 2, "one ask per sibling; none after a refusal"


def test_a_refusal_after_the_download_evicts_the_owned_sibling_and_moves_on(tmp_path):
    """05-11 review: the post-download re-check (AC-1) skips, evicts what it fetched, continues."""
    probe = BusyAfterStageA(len(ENGINES) + 1)  # free for the first sibling's pre-check only
    cache = FakeCache(downloaded=(CHOSEN.repo,))
    ok, cells, _osaurus, summary = verified_run(
        tmp_path,
        probe=probe,
        answers={"mlxlm": ("PASS", 40), "optiq": ("PASS", 60)},
        cache=cache,
    )

    assert ok is True
    first, second = stage_b_siblings(summary)
    assert first["status"] == second["status"] == "SKIPPED"
    assert first["reason"] == second["reason"] == "quit optiq first"
    assert cache.downloads == [first["repo"]], "only the first sibling was fetched"
    assert first["repo"] in cache.evicts, "the fetched sibling was evicted"
    assert summary["ended"] == "finished"
    measured_ids = {call["cells"][0].id for call in cells.calls}
    assert not {"oq4__optiq", "jang4__optiq"} & measured_ids
