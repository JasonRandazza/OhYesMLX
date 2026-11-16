"""Reproduction for Fable 5.2 S2-F8: a hung engine is retried to the end of the run.

The claim: ``measure._request`` (``:1160-1198``) passes no ``timeout_s``, so
``transport.chat``'s default 600 s deadline (``transport.py:163``) governs every request, and
neither ``_workload_visit`` (``:948-992``) nor ``_warmup_window`` (``:995-1038``) has a branch
that stops on repeated ``timeout`` failures. Under the plateau rule a failed request appends
``None`` to the warmup series, ``_settled`` cannot settle on ``None`` (``:1138-1139``), and the
window runs to ``WARMUP_CAP = 20`` -- after which the measured quota is issued anyway. A server
that accepted the connection and never answers therefore costs 20 + quota requests at 600 s
each, per workload, per visit.

The test counts requests rather than waiting: the transport answers instantly with a timeout
observation, which is the same failure the deadline produces, and the quantity under test is
how many of them the loop is willing to make.
"""

from __future__ import annotations

import pytest

from ohyesmlx import measure

from test_measure import FakeObservation, Harness

# The observation ``transport.chat`` returns when a request hits its 600 s deadline.
TIMEOUT = FakeObservation(
    ok=False,
    error="TransportError: timeout after 600s",
    ttft_s=None,
    last_content_s=None,
    total_s=600.0,
    prompt_tokens=None,
    completion_tokens=None,
    content_event_count=0,
    text="",
    token_source="none",
)


@pytest.fixture
def harness(monkeypatch, tmp_path):
    """``test_measure``'s harness, which is a fixture in that file rather than in conftest."""
    return Harness(monkeypatch, tmp_path)


def test_a_hung_engine_is_not_retried_to_the_end_of_the_run(harness):
    """One workload, the default plateau warmup, a transport that always times out.

    With no bailout the loop spends the whole warmup cap and both measured quotas on
    requests that can only time out again: 20 warmup + 3 measured on visit 1, 20 + 2 on
    visit 2. At the real 600 s deadline that is the run's whole afternoon for one cell.
    """
    harness.transport.responder = lambda call: TIMEOUT
    harness.add_runtime("mlxlm")

    harness.run([harness.cell("oq__mlxlm", "mlxlm")], warmup=measure.WARMUP_MODE, measured=5)

    made = len(harness.transport.calls)
    # Every request the two visits made, warmups included. A visit that ends after a couple
    # of consecutive timeouts issues a handful; no bailout issues 45.
    assert made <= 10, (
        f"a permanently hung engine was asked {made} times (20 warmup + 3 measured, then "
        "20 + 2) -- at transport.py's default 600 s deadline that is ~7.5 hours per "
        "workload for a cell that has already failed"
    )
