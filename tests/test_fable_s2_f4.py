"""Reproduction for Fable 5.2 S2-F4: ``peak_mb`` is published from a sampler that gave up.

The claim, restated in one line: when ``footprint`` returns nothing three times running,
``sample.Sampler._loop`` sets ``error`` and returns for good, ``stop()`` still returns the
maximum of the samples taken before that, and ``report._row`` publishes it as the cell's
``peak_mb`` while nothing between ``stop()`` and the row ever reads ``memory["error"]``.

Three tests, one per link in that chain:

* the sampler really does return a number beside an error (``sample.py:262-279, 290-302``);
* a PASS row publishes it with no marker (``report.py:865``);
* ``_highest_peak`` keeps one of two visit dicts on ``peak_mb`` alone, so the other visit's
  error is dropped even when it is the visit that gave up (``measure.py:1210-1220``).

No runtime, no model, no network: the sampler reads a monkeypatched ``phys_footprint_mb``.
"""

from __future__ import annotations

import time

from ohyesmlx import measure, sample as sample_mod
from ohyesmlx.report import render_cards, summarize
from ohyesmlx.sample import Sampler

from test_report import cell_result, obs

GAVE_UP = (
    "footprint read nothing 3 times running for pid 4242; "
    "the process has most likely exited"
)


def test_a_sampler_that_gave_up_still_returns_the_peak_it_reached(monkeypatch):
    """Two good reads, then three misses: the loop returns, and ``stop()`` keeps the number."""
    reads = iter([4000.0, 4096.0])
    interval = sample_mod.CONSECUTIVE_MISSES_BEFORE_STOP * 0.001

    monkeypatch.setattr(sample_mod, "phys_footprint_mb", lambda pid: next(reads, None))
    monkeypatch.setattr(sample_mod, "vmmap_split", lambda pid: {})
    monkeypatch.setattr(sample_mod, "gpu_wired_limit", lambda: {})

    sampler = Sampler(4242, interval_s=interval).start()
    deadline = time.monotonic() + 5.0
    while sampler.running and time.monotonic() < deadline:
        time.sleep(interval)
    result = sampler.stop()

    assert result["error"] == GAVE_UP
    assert result["peak_mb"] == 4096.0
    assert result["n_samples"] == 2


def test_a_pass_row_publishes_a_bare_number_for_a_peak_the_sampler_disowned():
    """A memory dict carrying both a peak and an error publishes neither the error nor a marker."""
    row = summarize(
        [cell_result([obs()], status="PASS", memory={"peak_mb": 4096.0, "error": GAVE_UP})]
    )[0]

    assert row["status"] == "PASS"
    assert row["peak_mb"] is None
    assert row["memory_note"] == GAVE_UP
    assert f"| peak_mb | — | {GAVE_UP} |" in render_cards([row])


def test_a_disowned_visit_that_wins_the_peak_comparison_reaches_the_row_intact(monkeypatch):
    """The sampler's own dict, kept by ``_highest_peak``, arrives at the row with its error.

    This is the reachability link the finding's ``measure.py:880`` cite names: the error is
    *not* dropped here when the disowned visit holds the larger peak -- it survives on
    ``result.memory`` and is then never read. Only the reverse case (the clean visit's peak is
    larger) drops it, and there it is dropped correctly, because the number published is the
    clean visit's own.
    """
    reads = iter([9150.0])
    interval = sample_mod.CONSECUTIVE_MISSES_BEFORE_STOP * 0.001

    monkeypatch.setattr(sample_mod, "phys_footprint_mb", lambda pid: next(reads, None))
    monkeypatch.setattr(sample_mod, "vmmap_split", lambda pid: {})
    monkeypatch.setattr(sample_mod, "gpu_wired_limit", lambda: {})

    sampler = Sampler(4242, interval_s=interval).start()
    deadline = time.monotonic() + 5.0
    while sampler.running and time.monotonic() < deadline:
        time.sleep(interval)
    disowned = sampler.stop()

    kept = measure._highest_peak(disowned, {"peak_mb": 4096.0, "error": None})
    assert kept["peak_mb"] == 9150.0
    assert kept["error"] == GAVE_UP

    row = summarize([cell_result([obs()], status="PASS", memory=kept)])[0]
    assert row["peak_mb"] is None
    assert row["memory_note"] == GAVE_UP
    assert row["status"] == "PASS"
