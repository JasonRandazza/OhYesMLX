"""S4-F12: the final sweep's evict failure is logged but not recorded in `not_evicted`.

A cancel landing right after a sibling download `break`s at `quickbench.py:891-893`, so the
per-cell `finally` (:914-930) is never reached and the repo is swept by the run-level `finally`
at :943-953 instead. That sweep records a *refused* eviction (`note_not_evicted`, :946-947, the
same helper the inner path uses at :921) but an eviction that *raises* only logs
(:948-953) -- no `summary["not_evicted"].append(leftover)`.

The summary and the Results screen therefore say nothing was left behind while the sibling is
still in the fetch ledger. The inner path at :922-928 does both, so the two sites disagree.

Fakes only: the evictor raises before touching anything, and the cancel probe fires after the
sibling download, which is the finding's stated trigger.
"""

from __future__ import annotations

from test_quickbench import (
    CHOSEN,
    SIBLING,
    a_run,
)


def test_a_sweep_eviction_that_raises_is_recorded_in_not_evicted(tmp_path):
    """The cancel-after-download ending must name the sibling it could not evict."""
    ok, fakes, summary = a_run(
        tmp_path,
        downloaded=(CHOSEN.repo,),
        cancel_after=3,
        evict_error=OSError("the fetch ledger is not readable"),
    )

    assert ok is False, "a cancelled run does not report success"
    assert summary["ended"] == "cancelled"
    assert fakes.cache.evicts == [SIBLING.repo], (
        "precondition: the cancel landed after the sibling download, so the run-level sweep "
        "is the site that evicted"
    )
    assert fakes.cache.evict_error is not None, "precondition: the eviction raised"

    assert summary["not_evicted"] == [SIBLING.repo], (
        f"the sweep's eviction of {SIBLING.repo} raised and the repo is still in the fetch "
        f"ledger, but the summary records nothing left behind "
        f"(not_evicted={summary['not_evicted']!r}); the inner path at quickbench.py:922-928 "
        f"records the same failure"
    )
