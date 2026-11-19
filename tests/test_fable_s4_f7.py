"""Fable 5.2 S4-F7: a partly-downloaded row is excluded on its full size.

The finding: ``/recommendations`` builds its ``downloaded`` set from
``fetch.downloaded`` (``server.py:582``), which is all-or-nothing (``fetch.py:272-298``).
``recommend.exclusion_reason`` then applies the disk margin to the *whole* artifact
(``recommend.py:141-146``) although ``fetch.download``'s own guard applies it to the bytes
still missing (``fetch.py:811-827``: ``sum(remaining(...))``, where a file's ``.incomplete``
prefix is subtracted). A download interrupted at 80% therefore leaves ``pick``'s list when
free disk is below 1.2x the full size, even when it comfortably covers 1.2x the remainder --
and an excluded row is plain text with neither Download nor Remove
(``app/Sources/OhYesMLX/Screens/ModelsView.swift:33-48``), so the partial cannot be resumed
from the screen that owns it.

These checks drive the real ``_Handler._get_recommendations`` with its three injected
dependencies and a captured ``_write_json``: no socket is opened, no model is loaded, and
``fetch.downloaded`` reads only ``tmp_path`` through ``HF_HUB_CACHE``.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

from ohyesmlx import fetch, server
from ohyesmlx.catalog import Model, ModelFile, disk_needed
from ohyesmlx.engines import EngineStatus
from ohyesmlx.hardware import Hardware

REPO = "mlx-community/LFM2.5-8B-A1B-MLX-4bit"
REV = "a" * 40
SHA = "b" * 64
SIZE = 4_782_228_614  # the catalog's LFM2.5-8B-A1B-MLX-4bit row
PRESENT = SIZE * 4 // 5  # an 80% partial: the finding's "4.0 GB of 4.78 GB"
REMAINING = SIZE - PRESENT
BUDGET_64_GIB = 49_392_123_904  # hardware.model_budget's own answer for 64 GiB


def a_model():
    return Model(
        repo=REPO,
        title="LFM2.5 8B A1B",
        params=8_467_856_832,
        format="4bit",
        modality="text",
        license="lfm1.0",
        tier="standard",
        revision=REV,
        size_bytes=SIZE,
        files=[ModelFile(path="model.safetensors", size=SIZE, sha256=SHA, git_oid=None)],
        engines=["mlxlm"],
        measured_here=False,
        notes="",
    )


def a_mac(free_disk):
    return Hardware(
        supported=True,
        unsupported_reason=None,
        chip="Apple M2 Max",
        family="M2",
        tier="max",
        cpu_cores=12,
        gpu_cores=38,
        ram_bytes=64 * 1024**3,
        macos="15.4",
        disk_free_bytes=free_disk,
        disk_total_bytes=free_disk,
        volumes=[],
        model_budget_bytes=BUDGET_64_GIB,
    )


def an_engine():
    return EngineStatus(
        name="mlxlm",
        title="mlx-lm",
        blurb="",
        installed=True,
        version="0.31.3",
        path="/opt/mlx-lm",
        tested=True,
        verified="2026-10-30",
        install=None,
    )


def write_partial(model, cache, body_size):
    """A download interrupted after *body_size* bytes of the one file."""
    planned = fetch.plan(model, str(cache))
    os.makedirs(planned.blobs_dir, exist_ok=True)
    with open(planned.files[0].blob + ".incomplete", "wb") as handle:
        handle.truncate(body_size)
    return planned


def recommendations(model, hw, cache, monkeypatch):
    """The payload ``GET /recommendations`` writes, without a socket."""
    monkeypatch.setenv("HF_HUB_CACHE", str(cache))
    written = []
    handler = SimpleNamespace(
        server=SimpleNamespace(
            scan=lambda: hw,
            detect=lambda: [an_engine()],
            load_catalog=lambda: [model],
            summaries=lambda: {},
        ),
        _write_json=lambda status, payload: written.append((status, payload)),
    )
    server._Handler._get_recommendations(handler)
    assert len(written) == 1
    return written[0]


def test_a_partly_downloaded_row_is_judged_on_what_is_left(tmp_path, monkeypatch):
    model = a_model()
    planned = write_partial(model, tmp_path, PRESENT)

    # ``fetch.download``'s own guard (fetch.py:811-818): 1.2 x the bytes still missing.
    missing = sum(
        max(0, planned_file.size - fetch._partial_size(planned_file.blob + ".incomplete"))
        for planned_file in planned.files
    )
    assert missing == REMAINING
    assert fetch.downloaded(model, str(tmp_path)) is False

    free = disk_needed(REMAINING) * 3 // 2
    assert disk_needed(missing) < free, "fetch.download would accept this resume"

    status, body = recommendations(model, a_mac(free), tmp_path, monkeypatch)

    assert status == 200
    assert [pick["model_id"] for pick in body["picks"]] == [REPO], (
        "a row with 80% on disk and room for the remainder was left out of the picks"
    )
    assert body["excluded"] == []


def test_a_row_with_nothing_on_disk_is_still_excluded_on_its_full_size(tmp_path, monkeypatch):
    # Control: the remainder rule must not become "never exclude".
    model = a_model()
    assert fetch.downloaded(model, str(tmp_path)) is False
    free = disk_needed(SIZE) // 2

    status, body = recommendations(model, a_mac(free), tmp_path, monkeypatch)

    assert status == 200
    assert body["picks"] == []
    assert [row["model_id"] for row in body["excluded"]] == [REPO]
