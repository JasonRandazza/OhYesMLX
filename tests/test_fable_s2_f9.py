"""Reproduction for Fable 5.2 S2-F9: a legacy header joins a stamped one with no comparison.

The claim: ``report._check_harness`` (``report.py:1497-1510``) does
``harness = header.get("harness")`` and ``if harness is None: continue``. A column written
before ``harness.source_sha256`` existed therefore continues past the guard instead of being
compared, so a 2026-09-16 column and a column measured this week join as one grid -- two
different harness revisions by construction, which is exactly what guard 6 exists to refuse
(``docs/interfaces/grid-and-warmup.md:96-100``).

The fix direction is either a refusal or a rendered caveat naming the legacy column, so the
test drives ``render_grid`` and accepts both. The all-legacy join is a different case and must
stay readable: every header predating the block lacks it and there is nothing to compare.
"""

from __future__ import annotations

import pytest

from ohyesmlx import report

from test_report import RUN_A, RUN_B, grid_run, run_header

STAMPED = {"version": "0.3.0", "source_sha256": "a" * 64}


def a_mixed_join():
    """One column stamped with a harness revision, one column written before the block."""
    return [
        grid_run(
            RUN_A,
            "mlxlm",
            "mlx-lm 0.31.3",
            ("oq4",),
            workload_ids=("chat",),
            header=run_header(("chat",), harness=STAMPED),
        ),
        grid_run(
            RUN_B,
            "omlx",
            "oMLX 0.6.4",
            ("oq4",),
            workload_ids=("chat",),
            header=run_header(("chat",)),
        ),
    ]


def test_a_stamped_column_beside_a_legacy_one_says_so_or_refuses():
    """The mixed join is two harness revisions, and the rendered grid must not be silent.

    Either acceptable answer names the legacy column the guard cannot compare: a refusal, or a
    caveat line carrying that column's label beside the word for the missing block.
    """
    try:
        rendered = report.render_grid(a_mixed_join())
    except ValueError as refusal:
        assert "harness" in str(refusal).lower(), (
            f"the join refused, but not for the harness: {refusal}"
        )
        return

    named = [
        line
        for line in rendered.splitlines()
        if RUN_B in line and "harness" in line.lower()
    ]
    assert named, (
        "one column carries harness.source_sha256 and one predates it; the grid rendered "
        "both as one join with nothing naming the column that could not be compared"
    )


def test_an_all_legacy_join_is_still_no_comparison():
    """Every column predates the block: there is nothing to compare, and the join stands."""
    assert report._check_harness([("legacy-a", {}, []), ("legacy-b", {}, [])]) is None


def test_two_stamped_headers_that_disagree_still_refuse():
    """The guard that already works, kept here so the fix cannot weaken it."""
    with pytest.raises(ValueError, match="source_sha256"):
        report._check_harness(
            [
                ("stamped-a", {"harness": STAMPED}, []),
                ("stamped-b", {"harness": {"version": "0.3.0", "source_sha256": "b" * 64}}, []),
            ]
        )
