"""Reproduction for Fable 5.2 S2-F7: a lost second visit fails the row; a lost first is an annotation.

The claim: ``measure._visit`` writes ``FAIL`` with the start's reason on a row that already
holds samples (``measure.py:843-852``) and returns ``"retry"``; ``run_cells`` stores that
reason in ``lost[cell.id]`` (``:666-668``), and only a later *measured* visit consumes it
(``:654-663``). A cell whose first visit measured and whose second visit failed therefore ends
the run ``FAIL`` with ``lost_visit_reason`` never written -- while the mirror case (first visit
lost, second measured) is ``PASS`` with the reason as an annotation.

Both rows built here hold only requests that came back healthy and carry every published
metric, so nothing in either row's own samples supports ``FAIL``. The contract the finding
cites (``docs/interfaces/sweep-pins.md:185-186``) reads "Three additions, all of them
annotations and none of them floors -- ... a window that was short is a result", which is the
direction the mirror case follows.

Two tests: the control pins the documented direction (it passes today), and the second asserts
the two losses are judged alike (it fails today). Whether a lost *later* visit should be a
floor is Jason's decision; if it is, the contract sentence needs to say so and this test is
amended with it.
"""

from __future__ import annotations

import pytest

from ohyesmlx import report

from test_measure import Harness

# The runtime that will not start when the test says so, and the exact reason the loop posts.
START_ERROR = RuntimeError("port still held by a stale server")
LOST = "runtime 'mlxlm' did not start: RuntimeError: port still held by a stale server"


@pytest.fixture
def harness(monkeypatch, tmp_path):
    """``test_measure``'s harness, which is a fixture in that file rather than in conftest."""
    return Harness(monkeypatch, tmp_path)


def run_with_lost_visit(harness, *, failing_attempt):
    """One cell, five measured batches split 3 + 2, with the named start attempt raising."""
    harness.add_runtime("mlxlm", start_error=START_ERROR, fail_attempts=(failing_attempt,))
    results = harness.run([harness.cell("oq__mlxlm", "mlxlm")])
    return results[0], report.summarize(results)[0]


def test_the_first_visit_lost_is_an_annotation_on_a_pass_row(harness):
    """The documented direction: the surviving visit's samples decide, the loss is recorded.

    This is the 06-01c case the fields were added for, and it is the control for the test
    below: same cell, same healthy samples, only the failed visit's index differs.
    """
    result, row = run_with_lost_visit(harness, failing_attempt=1)

    assert result.status == "PASS"
    assert result.lost_visit_reason == LOST
    assert result.cold_load_after_lost_visit is True
    assert row["rankable"] is True
    assert row["lost_visit_note"] is not None
    # The window is short and says so -- an annotation, not a verdict.
    assert row["short_note"] is not None


def test_the_two_lost_visits_are_judged_alike(harness):
    """Three healthy samples landed in both rows; only the lost visit's index differs.

    Today the first row is ``PASS``, rankable, with ``lost_visit_note`` naming the loss; the
    second is ``FAIL`` and excluded by the metrics floor, with ``lost_visit_reason`` never
    written -- although every sample it holds is a healthy measurement and no request of its
    failed. A transient second start therefore deletes a cell that had already measured.
    """
    first_lost_result, first_lost_row = run_with_lost_visit(harness, failing_attempt=1)
    second_lost_result, second_lost_row = run_with_lost_visit(harness, failing_attempt=2)

    assert len(first_lost_result.observations) == 2, "visit 2's quota of two"
    assert len(second_lost_result.observations) == 3, "visit 1's quota of three"
    for result in (first_lost_result, second_lost_result):
        assert all(
            observation.ok and observation.completion_tokens and observation.ttft_s is not None
            for observation in result.observations
        ), "every sample on both rows is a healthy measurement"

    assert second_lost_row["rankable"] == first_lost_row["rankable"], (
        "a lost second visit is excluded ("
        f"{second_lost_row['exclusion']!r}, reason {second_lost_row['reason']!r}) while the "
        "mirror loss is a ranked PASS with an annotation "
        f"({first_lost_row['status']!r}, {first_lost_row['lost_visit_note']!r}); the samples "
        "in the two rows are the same healthy requests and only the visit's index differs"
    )
    assert second_lost_row["lost_visit_note"] is not None, (
        "the second direction is not recorded as a lost visit at all: "
        f"lost_visit_reason={second_lost_result.lost_visit_reason!r}"
    )
