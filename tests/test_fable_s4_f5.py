"""S4-F5: stage B names a best by raw max, with no tie band.

Stage A ranks its PASS cells through ``_winner``, which reports anything inside ``TIE``
(``canary.NOISE_FLOOR``, 0.05) as a tie rather than a winner. Stage B ranks the same way
nowhere: ``_best`` takes ``max`` over ``stage_b.cells``, which contains the reused stage-A
baseline row (``dict(top, reused=True)``) beside the siblings measured after it. A sibling
1.5% faster than the baseline is therefore named this Mac's best, and ``latest`` hands that
block to ``/recommendations`` as ``measured_here``.
"""

import ohyesmlx.quickbench as quickbench


def a_cell(*, fmt, repo, decode_tps, reused=False):
    cell = {
        "engine": "omlx",
        "format": fmt,
        "repo": repo,
        "decode_tps": decode_tps,
        "ttft_s": 0.2,
        "status": "PASS",
        "reason": None,
    }
    if reused:
        cell["reused"] = True
    return cell


def a_stage_b_summary(*, baseline_tps, sibling_tps):
    return {
        "stage_a": {"cells": [], "engine": None},
        "stage_b": {
            "caveat": quickbench.CAVEAT_B,
            "engine": "omlx",
            "note": None,
            "cells": [
                a_cell(
                    fmt="stock4bit",
                    repo="org/stock",
                    decode_tps=baseline_tps,
                    reused=True,
                ),
                a_cell(fmt="oq4", repo="org/oq4", decode_tps=sibling_tps),
            ],
        },
    }


def test_best_keeps_the_baseline_when_the_sibling_is_inside_the_tie_band():
    # 72.1 is 1.5% over 71.0: inside the 5% band _winner calls a tie.
    summary = a_stage_b_summary(baseline_tps=71.0, sibling_tps=72.1)
    best = quickbench._best(summary, "2026-11-15T00:00:00+00:00")
    assert best["repo"] == "org/stock", (
        "a 1.5% gap was ranked as a win; stage A calls anything within 5% a tie"
    )
    assert best["format"] == "stock4bit"
    assert best["decode_tps"] == 71.0


def test_best_takes_the_sibling_once_it_clears_the_band():
    # Control: a gap wider than TIE is a real win, so the band is not "always keep the
    # baseline".
    summary = a_stage_b_summary(baseline_tps=60.0, sibling_tps=70.0)
    best = quickbench._best(summary, "2026-11-15T00:00:00+00:00")
    assert best["repo"] == "org/oq4"
    assert best["decode_tps"] == 70.0
