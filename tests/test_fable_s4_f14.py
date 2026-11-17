"""S4-F14: a verified partial is renamed into place without fsync, and nothing re-checks bytes.

Two halves, and only the second can be a failing test; the first is cited from the source.

1. **No flush before the rename.** `fetch.py:891-904` (`finish`) calls `_verify(...)` and then
   `os.replace(incomplete, planned_file.blob)` at :902. Neither `finish` nor `_fetch_file`
   (:906-1122) calls `os.fsync` on the partial before the rename, and nothing fsyncs the
   directory after it -- `grep -n "fsync" ohyesmlx/fetch.py` returns no match at all, which the
   report records as the command and its empty output. A rename is journaled before the data
   blocks are, so a power loss seconds after a download "finishes" can leave a blob of the
   right length and the wrong contents. No test can stage a power loss, which is why this half
   is evidence from the source rather than a test.

2. **Nothing downstream re-checks.** `downloaded` (:272-298) is size-and-link only (UAT-001),
   so a wrong-contents blob of the right size reads as ready, and `quickbench.plan` gates on
   `downloaded` alone (quickbench.py:283). A run then measures the corrupt artifact and files
   its FAIL -- or a plausible number -- under the catalog row. A later `download` refuses with
   `integrity_failed ... nothing was overwritten` (:798-806), so the app cannot repair it.

The test below is the finding's own idea, made concrete: a ledgered blob padded to the exact
catalog size with the wrong bytes, then a quick-bench run of that row. The run must refuse
before an engine is started (and before Osaurus is pinned). It drives `run`, not `plan`:
`plan` serves `GET /quickbench/plan` on the request thread and must not hash (05-10 AC-9; the
second test pins that).
"""

from __future__ import annotations

import os
from dataclasses import replace
from types import SimpleNamespace

from test_quickbench import ENGINES, WITH_OSAURUS, FakeCache, FakeOsaurus, FakeRunCells, a_model

from ohyesmlx import catalog, fetch, quickbench

REPO = "org/corrupt-oq4"
SIZE = 400


def _row():
    row = a_model(REPO, "oq4", "Corrupt", size_bytes=SIZE)
    return replace(
        row,
        files=[
            catalog.ModelFile(
                path="model.safetensors", size=SIZE, sha256="d" * 64, git_oid=None
            )
        ],
    )


def a_cache_with_right_size_wrong_bytes(cache_dir, model):
    """What a rename-without-fsync leaves: the right length, the wrong contents."""
    planned = fetch.plan(model, cache_dir)
    planned_file = planned.files[0]
    os.makedirs(planned.blobs_dir, exist_ok=True)
    with open(planned_file.blob, "wb") as handle:
        handle.write(b"x" * planned_file.size)  # right length, not the catalog's sha256
    os.makedirs(planned.snapshot_dir, exist_ok=True)
    os.symlink(planned_file.blob, planned_file.link)
    os.makedirs(planned.refs_dir, exist_ok=True)
    with open(planned.ref_path, "w", encoding="utf-8") as handle:
        handle.write(model.revision)
    return planned_file


def test_a_wrong_bytes_blob_of_the_right_size_is_planned_for_measurement(tmp_path):
    """Half 2: a corrupt blob of the catalog's size passes `downloaded`, so the plan accepts it."""
    model = _row()
    cache_dir = str(tmp_path / "cache")
    planned_file = a_cache_with_right_size_wrong_bytes(cache_dir, model)

    # The blob is not the file the catalog pins.
    assert os.path.getsize(planned_file.blob) == planned_file.size
    assert fetch._verify(planned_file, planned_file.blob) is False, (
        "precondition: the blob is the right size and the wrong bytes"
    )
    assert fetch.downloaded(model, cache_dir) is True, (
        "precondition: `downloaded` is size-and-link only (UAT-001), so the wrong bytes pass"
    )

    # `plan` serves a request thread and must stay a stat-only answer (05-10 AC-9), so the
    # check is `run`'s, once, before the Osaurus pin and before any engine: it is driven here.
    log = []
    events = []
    cells = FakeRunCells(on_call=lambda cell, _kwargs: log.append(("cell", cell.id)))
    fake_osaurus = FakeOsaurus(log=log)
    ok = quickbench.run(
        REPO,
        confirmed=True,
        osaurus=True,
        models=[model],
        statuses=WITH_OSAURUS,
        hw=SimpleNamespace(),
        run_cells=cells,
        download=FakeCache(log=log).download,
        evict=FakeCache(log=log).evict,
        pin=fake_osaurus.pin,
        restore=fake_osaurus.restore,
        recover=fake_osaurus.recover,
        port_in_use=lambda _port: False,
        osaurus_app_running=lambda: False,
        load=lambda: 1.0,
        emit=events.append,
        cache_dir=cache_dir,
        results_dir=str(tmp_path / "quickbench"),
        backup_dir=str(tmp_path / "backup"),
        baseline_path=str(tmp_path / "baseline.json"),
    )

    assert ok is False
    assert cells.calls == [], (
        "the run started an engine for a blob that fails `fetch._verify`, so it would "
        "measure a corrupt artifact and file the number under the catalog row"
    )
    assert fake_osaurus.calls == [], "Osaurus was recovered or pinned for a refused run"
    assert not list((tmp_path / "quickbench").glob("*/summary.json")), "a refused run wrote a row"
    error = next(e for e in events if e["type"] == "error")
    assert error["payload"]["code"] == "integrity_failed"
    assert "model.safetensors" in error["message"]
    assert "remove it on the Models screen, then download it again" in error["message"]


def test_plan_never_hashes_a_wrong_bytes_blob(tmp_path):
    """The plan stays cheap: it accepts what `downloaded` accepts, and `run` does the hashing."""
    model = _row()
    cache_dir = str(tmp_path / "cache")
    a_cache_with_right_size_wrong_bytes(cache_dir, model)

    shown = quickbench.plan(
        REPO,
        SimpleNamespace(),
        ENGINES,
        [model],
        cache_dir=cache_dir,
        downloaded=fetch.downloaded,
    )

    assert shown.stage_a, "plan answered from size and link alone"
