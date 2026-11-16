"""Reproduction for Fable 5.2 S2-F1: a FAILED quickbench cell carries its numbers to the app.

The claim: ``quickbench._cell_record`` copies ``decode_tps`` and ``ttft_p50_s`` off
``report.summarize``'s row with no status test (``quickbench.py:346-350``), although its own
docstring says a failed cell carries "no number at all". ``report._row`` keeps the medians on
a FAIL row -- its renderers suppress them, the row does not -- so the ``result`` event and
``quickbench.json`` carry ``status: FAIL, decode_tps: 300``, and both Swift views print the
figure whenever it is non-nil, beside the word "Failed".

Each test drives ``quickbench.run`` with ``run_cells`` stubbed to return a real
``measure.CellResult`` that has been through the real gate, ``measure._set_status``: the
verdict is measure's, not the test's, and every observation holds the timing of a healthy
300 tok/s request. No runtime, no model, no network.
"""

from __future__ import annotations

from ohyesmlx import measure, transport

from test_quickbench import a_run, an_engine

SALAD = "，,跟ashaa.atore quell\ufffd不会ulatSR2ancel Hard1"
INCOHERENT = "incoherent output: replacement characters"


def an_observation(*, ok=True, error=None, tokens=300):
    """One request at 300 tok/s: 300 completion tokens over a 1.0 s content window."""
    return transport.Observation(
        ok=ok,
        error=error,
        ttft_s=0.2,
        last_content_s=1.2,
        total_s=1.3,
        prompt_tokens=32,
        completion_tokens=tokens,
        reasoning_tokens=None,
        content_event_count=2,
        text=SALAD if ok else "",
        token_source="usage",
    )


def a_failed_cell(cell, observations, expected_reason):
    """One cell the way ``measure.run_cells`` returns it: raw samples, then ``_set_status``."""
    result = measure.CellResult(
        cell=cell,
        workload_id="decode",
        status="PASS",
        reason=None,
        observations=observations,
        batch_spans=[],
        warmup_observations=[],
        warmup_plateau=True,
        cold_load_s=1.0,
        first_request_s=None,
        first_request_workload_id=None,
        memory={},
        runtime_version="0.31.3",
        disk_bytes=None,
    )
    measure._set_status(result)
    assert result.status == "FAIL" and result.reason.startswith(expected_reason), (
        f"the gate did not produce the claimed verdict: {result.status} {result.reason!r}"
    )
    return [result]


def failing_run_cells(observations, expected_reason):
    """A ``run_cells`` that answers every cell with the same failed result."""

    def run_cells(cells, workloads, **kwargs):
        assert len(cells) == 1, "one run_cells call is one cell"
        return a_failed_cell(cells[0], observations, expected_reason)

    return run_cells


def run_one_cell(tmp_path, observations, expected_reason):
    ok, fakes, summary = a_run(
        tmp_path,
        run_cells=failing_run_cells(observations, expected_reason),
        engines_list=[an_engine("mlxlm")],
    )
    assert ok is True
    record, = summary["stage_a"]["cells"]
    published = next(
        event["payload"]["stage_a"]["cells"][0]
        for event in fakes.events
        if event["type"] == "result"
    )
    return record, published


def test_a_failed_incoherent_cell_publishes_no_figure(tmp_path):
    """The 2026-09-15 case: HTTP 200, full speed, five requests of token salad.

    The cell is FAIL and its observations stay on the record. What it must not carry is a
    tok/s or TTFT the app can print beside "Failed": those are the samples that earned the
    verdict, not a measurement of a cell that passed.
    """
    record, published = run_one_cell(
        tmp_path, [an_observation() for _ in range(5)], INCOHERENT
    )

    assert record["status"] == "FAIL" and published["status"] == "FAIL"
    assert record["reason"] == INCOHERENT and published["reason"] == INCOHERENT

    assert published["decode_tps"] is None and record["decode_tps"] is None, (
        f"a FAIL cell published {record['decode_tps']} tok/s to the app"
    )
    assert published["ttft_s"] is None and record["ttft_s"] is None, (
        f"a FAIL cell published TTFT {record['ttft_s']} s"
    )


def test_a_failed_cell_with_two_lost_requests_publishes_no_survivor_median(tmp_path):
    """A row whose reason is "2 of 5 measured requests failed": the three that came back are
    still a median the app would print, and a cell the harness judged FAIL is not a
    measurement whichever half of its samples are used.
    """
    observations = [
        an_observation(ok=False, error="stream closed before any content"),
        an_observation(ok=False, error="stream closed before any content"),
        an_observation(),
        an_observation(),
        an_observation(),
    ]

    record, published = run_one_cell(
        tmp_path,
        observations,
        "2 of 5 measured requests failed; first: stream closed before any content",
    )

    assert record["status"] == "FAIL" and published["status"] == "FAIL"

    assert published["decode_tps"] is None and record["decode_tps"] is None, (
        f"a FAIL cell published the survivors' median {record['decode_tps']} tok/s"
    )
    assert published["ttft_s"] is None and record["ttft_s"] is None
