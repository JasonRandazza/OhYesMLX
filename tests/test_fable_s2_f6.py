"""Reproduction for Fable 5.2 S2-F6: a transport-failed row is published as "coherence: pass".

The claim: ``measure._set_status`` returns at the ``failures`` branch
(``measure.py:1236-1245``) before ``_incoherent`` (``:1256``) can run, so a cell whose nine
measured requests are one timeout and eight token-salad responses carries the reason "1 of 9
measured requests failed" and never the incoherence verdict. ``report._floor_verdicts``
(``report.py:1097-1106``) then matches neither the ``N/A`` branch nor
``_coherence_failed`` -- the reason is not the gate's vocabulary -- and prints
``coherence: pass`` beside ``metrics: fail``. The table states the coherence gate passed on a
cell it never judged, and on garbage.

The alternative branch the finding asks for is not asserted here: the row may instead report
``not reached`` for coherence, which is the state ``_floor_verdicts`` already has for a gate an
earlier failure never got to. What must not happen is ``pass``.
"""

from __future__ import annotations

from ohyesmlx import measure, report, transport

# The captured salad from the 2026-09-15 mlx-lm incident: HTTP 200, full speed, no language.
SALAD = "，,跟ashaa.atore quell\ufffd不会ulatSR2ancel Hard1"


def answered(text, *, tokens=64):
    """One healthy request that streamed *text*: timings and token counts intact."""
    return transport.Observation(
        ok=True,
        error=None,
        ttft_s=0.2,
        last_content_s=1.2,
        total_s=1.3,
        prompt_tokens=32,
        completion_tokens=tokens,
        reasoning_tokens=None,
        content_event_count=2,
        text=text,
        token_source="usage",
    )


def timed_out():
    """One request the transport gave up on, exactly as ``_request`` records it."""
    return transport.Observation(
        ok=False,
        error="TransportError: timeout after 600s",
        ttft_s=None,
        last_content_s=None,
        total_s=600.0,
        prompt_tokens=None,
        completion_tokens=None,
        reasoning_tokens=None,
        content_event_count=0,
        text="",
        token_source="none",
    )


def a_row(observations):
    """One cell the way ``run_cells`` leaves it: every raw observation, then the gate."""
    result = measure.CellResult(
        cell=measure.Cell(
            id="oq4__mlxlm", runtime="mlxlm", artifact_dir="/models/oq4", label="oq4"
        ),
        workload_id="decode",
        status="PASS",
        reason=None,
        observations=list(observations),
        batch_spans=[],
        warmup_observations=[],
        warmup_plateau=True,
        cold_load_s=1.0,
        first_request_s=None,
        first_request_workload_id=None,
        memory={},
        runtime_version="mlx-lm 0.31.3",
        disk_bytes=None,
    )
    measure._set_status(result)
    return report.summarize([result])[0]


def coherence_floor(row):
    return next(floor for floor in row["floors"] if floor["floor"] == "coherence")


def test_a_transport_failure_beside_garbage_is_not_published_as_coherence_pass():
    """One timeout and eight salad responses: the gate never judged, and the row says it passed.

    The eight that came back are the sample the gate exists to read. Returning at the
    transport-failure branch first means the row's reason is the timeout -- and the floor table
    reads a reason it does not recognise as "the coherence gate passed".
    """
    row = a_row([timed_out()] + [answered(SALAD) for _ in range(8)])

    assert row["status"] == "FAIL"
    assert row["reason"].startswith(measure.INCOHERENT_PREFIX), (
        f"the responses that came back must be judged before the transport failure: "
        f"{row['reason']!r}"
    )

    floor = coherence_floor(row)
    assert floor["state"] == "fail", (
        "a row whose eight surviving samples are token salad is published as "
        f"coherence: {floor['state']} (detail {floor['detail']!r}) under the reason "
        f"{row['reason']!r}; the gate never ran on it and the garbage it exists to catch "
        "is on the record"
    )


def test_nine_timeouts_do_not_claim_the_coherence_gate_passed():
    """The same label for a cell that produced no language at all.

    ``coherence: pass`` here is the strongest form of the claim: every one of the nine
    requests failed in transport, no response was ever judged, and the row states the gate
    passed.
    """
    row = a_row([timed_out() for _ in range(9)])

    assert row["status"] == "FAIL"
    floor = coherence_floor(row)
    assert floor["state"] == "not reached", (
        f"nine failed requests are published as coherence: {floor['state']} "
        f"(reason {row['reason']!r})"
    )


def test_a_start_failure_does_not_claim_the_coherence_gate_passed():
    floors = report._floor_verdicts(
        "FAIL", "runtime 'omlx' did not start: TimeoutError: port 8100 never opened"
    )

    assert next(floor for floor in floors["floors"] if floor["floor"] == "coherence") == {
        "floor": "coherence", "state": "not reached", "detail": None
    }
