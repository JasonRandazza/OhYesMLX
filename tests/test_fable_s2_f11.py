"""Reproduction for Fable 5.2 S2-F11: ``latest`` picks by file mtime and keys only on winners.

The claim has two halves, both in ``quickbench.latest`` (``quickbench.py:1036-1059``):

1. **A superseded number can be served.** Run 1 chooses repo X, X wins at 60 tok/s. Run 2
   (after an engine update) chooses X again, measures X at 48, and sibling Y wins. ``latest``
   keys on ``best.repo`` alone, so run 2 contributes Y only and run 1's X stands -- 60 tok/s
   for X, although the newest measurement of X on this Mac is 48. ``GET /recommendations``
   hands that block to ``Pick.measured_here`` (``recommend.py:206``).
2. **Ordering is ``st_mtime``.** A results directory restored from a backup, or copied with
   ``cp -p``, outranks a newer run although every summary carries its own ``best.measured_at``
   and the run directory's name is its own start stamp (``quickbench.py:567``).

Both tests write only summaries under ``tmp_path`` -- the files ``a_run`` produces, in the
shape ``docs/interfaces/v5-quickbench.md:169-198`` pins.
"""

from __future__ import annotations

import json
import os

from ohyesmlx import quickbench


def write_summary(root, stamp, *, best, mtime, ended="finished"):
    """One finished run directory: a summary whose own record states what it measured."""
    directory = root / stamp
    directory.mkdir(parents=True)
    path = directory / "summary.json"
    path.write_text(
        json.dumps({"ended": ended, "results_dir": str(directory), "best": best}),
        encoding="utf-8",
    )
    os.utime(path, (mtime, mtime))
    return path


def a_best(*, repo, decode_tps, measured_at, engine="mlxlm", fmt="stock4bit"):
    return {
        "engine": engine,
        "format": fmt,
        "repo": repo,
        "decode_tps": decode_tps,
        "ttft_s": 0.2,
        "measured_at": measured_at,
        "quick": True,
    }


def test_a_repo_the_newest_run_measured_and_lost_does_not_keep_an_older_win(tmp_path):
    """Run 1: X wins at 60. Run 2: X measured at 48, sibling Y wins. ``latest`` shows X = 60.

    The newest fact about X on this Mac is 48 tok/s, measured by the newest finished run. The
    screen that reads this map shows the user 60, from a run two engine versions back, with
    nothing saying so.
    """
    root = tmp_path / "quickbench"
    older = "20260901T100000Z"
    newer = "20261101T100000Z"

    write_summary(
        root,
        older,
        best=a_best(repo="org/x", decode_tps=60.0, measured_at="2026-09-01T10:05:00+00:00"),
        mtime=1_000,
    )
    # The newer run: X was the chosen row, X measured 48, and the sibling Y won stage B.
    directory = root / newer
    directory.mkdir(parents=True)
    (directory / "summary.json").write_text(
        json.dumps(
            {
                "ended": "finished",
                "repo": "org/x",
                "best": a_best(
                    repo="org/y", decode_tps=72.0, measured_at="2026-11-01T10:05:00+00:00"
                ),
                "stage_a": {
                    "cells": [
                        {
                            "engine": "mlxlm",
                            "format": "stock4bit",
                            "repo": "org/x",
                            "artifact_dir": "/models/x",
                            "status": "PASS",
                            "reason": None,
                            "decode_tps": 48.0,
                            "ttft_s": 0.3,
                            "runtime_version": "mlx-lm 0.32.0",
                            "label": quickbench.LABEL,
                            "reused": True,
                        }
                    ]
                },
                "stage_b": {"cells": []},
            }
        ),
        encoding="utf-8",
    )
    os.utime(directory / "summary.json", (2_000, 2_000))

    found = quickbench.latest(root)

    assert found["org/y"]["best"]["decode_tps"] == 72.0, "the newest run's winner is served"
    if "org/x" in found:
        assert found["org/x"]["best"]["decode_tps"] != 60.0, (
            "a repo the newest run measured at 48 tok/s is served at 60 from an older run: "
            f"{found['org/x']['best']}"
        )


def test_a_directory_touched_later_does_not_outrank_a_newer_run(tmp_path):
    """Two finished runs of one repo; the older one has the newer mtime.

    ``st_mtime`` is a property of the directory, not of the measurement: restoring it from a
    backup, copying it, or re-saving a file in it moves it. The summary's own ``measured_at``
    is what says which run is newer.
    """
    root = tmp_path / "quickbench"
    write_summary(
        root,
        "20260901T100000Z-older-run",
        best=a_best(repo="org/x", decode_tps=48.0, measured_at="2026-09-01T10:05:00+00:00"),
        mtime=9_000,  # touched/copied later than the run below
    )
    write_summary(
        root,
        "20261101T100000Z-newer-run",
        best=a_best(repo="org/x", decode_tps=60.0, measured_at="2026-11-01T10:05:00+00:00"),
        mtime=1_000,
    )

    found = quickbench.latest(root)

    assert found["org/x"]["best"]["measured_at"] == "2026-11-01T10:05:00+00:00", (
        "the older run was served because its summary file has the newer mtime: "
        f"{found['org/x']['best']['measured_at']}"
    )
