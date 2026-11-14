"""Checks for ohyesmlx/quickbench.py.

No runtime, no model, no network, no real Osaurus settings and no real Application Support:
every side effect the module takes is a fake. ``run_cells`` answers with a real
``measure.CellResult``, so the row the module reads is ``report.summarize``'s rather than a
hand-built one, and the only files a test reads are the summaries a run wrote under a
``tmp_path`` root.

The counterweight is the other half of the contract: a fake records every call, so "the
chosen repo was never evicted", "nothing was downloaded", "the port was probed" and "the
restore ran even though the cell raised" are all checks on what the module did, not on what
it said it did.
"""

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from ohyesmlx import (
    catalog,
    engines,
    fetch,
    measure,
    osaurus_settings,
    quickbench,
    runtimes,
    transport,
)

# --- the catalog rows and the engines ---------------------------------------------------------


def a_model(
    repo, fmt, base, *, size_bytes=2_000_000_000, engine_names=("mlxlm", "osaurus", "optiq")
):
    """One real catalog row: sum(files) must equal size_bytes, as `catalog.load` requires."""
    return catalog.Model(
        repo=repo,
        base=base,
        title=repo,
        params=2_000_000_000,
        format=fmt,
        modality="text",
        license="apache-2.0",
        tier="starter",
        revision="a" * 40,
        size_bytes=size_bytes,
        files=[
            catalog.ModelFile(
                path="config.json", size=size_bytes, sha256="b" * 64, git_oid=None
            )
        ],
        engines=list(engine_names),
        measured_here=False,
        notes="",
    )


CHOSEN = a_model("org/two-b-stock", "stock4bit", "TwoB")
SIBLING = a_model("org/two-b-oq4", "oq4", "TwoB", size_bytes=3_000_000_000)
SIBLING_2 = a_model("org/two-b-jang", "jang4", "TwoB", size_bytes=4_000_000_000)
UNRELATED = a_model("org/other", "oq4", "Other")
MODELS = [CHOSEN, SIBLING, SIBLING_2, UNRELATED]


def an_engine(name, *, installed=True, version="0.31.3", tested=True):
    return engines.EngineStatus(
        name=name,
        title=name,
        blurb="",
        installed=installed,
        version=version,
        path=f"/bin/{name}" if installed else None,
        tested=tested,
        verified="2026-10-29",
        install=None,
    )


ENGINES = [an_engine("mlxlm"), an_engine("optiq")]
WITH_OSAURUS = [an_engine("mlxlm"), an_engine("osaurus"), an_engine("optiq")]


# --- fakes: every side effect the module takes ------------------------------------------------


def cell_result(cell, *, status="PASS", tokens=60, reason=None):
    """One decode row: `tokens` completion tokens over a 1.0 s content window."""
    observation = transport.Observation(
        ok=True,
        error=None,
        ttft_s=0.2,
        last_content_s=1.2,
        total_s=1.3,
        prompt_tokens=32,
        completion_tokens=tokens,
        reasoning_tokens=None,
        content_event_count=2,
        text="A measured answer.",
        token_source="usage",
    )
    return measure.CellResult(
        cell=cell,
        workload_id="decode",
        status=status,
        reason=reason,
        observations=[observation],
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


class FakeRunCells:
    """The run loop: records each call, answers each cell with a real `CellResult`.

    `answers` is keyed by runtime and is (status, completion tokens); one second of content
    window makes the tokens the decode rate, so 60 is 60.0 tok/s.
    """

    def __init__(self, answers=None, on_call=None):
        self.answers = dict(answers or {})
        self.calls = []
        self.on_call = on_call

    def __call__(self, cells, workloads, **kwargs):
        assert len(cells) == 1, "one run_cells call is one cell"
        self.calls.append({"cells": cells, "workloads": workloads, **kwargs})
        if self.on_call is not None:
            self.on_call(cells[0], kwargs)
        status, tokens = self.answers.get(cells[0].runtime, ("PASS", 60))
        return [cell_result(cells[0], status=status, tokens=tokens)]


class FakeCache:
    """The downloader, evictor and downloaded check, recording every call in order."""

    def __init__(
        self, downloaded=(), download_result=True, evict_result=True, evict_error=None, log=None
    ):
        self.repos = set(downloaded)
        self.downloads = []
        self.evicts = []
        self.download_result = download_result
        self.evict_result = evict_result
        self.evict_error = evict_error
        self.log = log if log is not None else []
        self.cache_dirs = []

    def downloaded(self, model, cache_dir=None):
        return model.repo in self.repos

    def download(self, repo, confirmed, *, cache_dir=None, emit=None):
        self.cache_dirs.append(cache_dir)
        self.downloads.append(repo)
        self.log.append(("download", repo))
        return self.download_result

    def evict(self, repo, confirmed, *, cache_dir=None, emit=None):
        self.cache_dirs.append(cache_dir)
        self.evicts.append(repo)
        self.log.append(("evict", repo))
        if self.evict_error is not None:
            raise self.evict_error
        return self.evict_result


class FakeOsaurus:
    """Pin, restore and recover, recorded in one list so their order can be checked."""

    def __init__(self, *, recover=True, pin_error=None, restore=True, restore_error=None, log=None):
        self.recover_result = recover
        self.pin_error = pin_error
        self.restore_result = restore
        self.restore_error = restore_error
        self.calls = []
        self.log = log if log is not None else []

    def recover(self, **kwargs):
        self.calls.append(("recover", kwargs))
        self.log.append(("recover", kwargs))
        return self.recover_result

    def pin(self, **kwargs):
        self.calls.append(("pin", kwargs))
        self.log.append(("pin", kwargs))
        if self.pin_error is not None:
            raise ValueError(self.pin_error)
        return None

    def restore(self, **kwargs):
        self.calls.append(("restore", kwargs))
        self.log.append(("restore", kwargs))
        if self.restore_error is not None:
            raise OSError(self.restore_error)
        return self.restore_result


class FakeClock:
    """A clock that advances one second per call, so `actual_s` is deterministic."""

    def __init__(self, start=1_700_000_000.0):
        self.now = start

    def __call__(self):
        self.now += 1.0
        return self.now


class FakeLoad:
    """The load average: one value per call, the last one repeated."""

    def __init__(self, values=(1.0,)):
        self.values = list(values)
        self.calls = 0

    def __call__(self):
        value = self.values[min(self.calls, len(self.values) - 1)]
        self.calls += 1
        return value


class CancelAfter:
    """The cancel probe, true from the check after the given number."""

    def __init__(self, after=None):
        self.after = after
        self.checks = 0

    def __call__(self):
        self.checks += 1
        return self.after is not None and self.checks > self.after


class AbortProbe:
    """The "Stop now" probe: false until something flips it, true from the next check on."""

    def __init__(self):
        self.triggered = False
        self.checks = 0

    def __call__(self):
        self.checks += 1
        return self.triggered


class PortProbe:
    """The port probe: answers from a set and records every port asked about."""

    def __init__(self, busy=()):
        self.busy = set(busy)
        self.ports = []

    def __call__(self, port):
        self.ports.append(port)
        return port in self.busy


def a_run(
    tmp_path,
    *,
    answers=None,
    downloaded=(CHOSEN.repo,),
    engines_list=ENGINES,
    models=MODELS,
    osaurus=False,
    confirmed=True,
    download_result=True,
    evict_result=True,
    evict_error=None,
    port_busy=(),
    app_running=False,
    cancel_after=None,
    abort=None,
    recover=True,
    pin_error=None,
    restore=True,
    restore_error=None,
    loads=(1.0,),
    run_cells=None,
):
    """Run quickbench against scratch directories with every side effect faked."""
    log = []
    cache = FakeCache(
        downloaded=downloaded,
        download_result=download_result,
        evict_result=evict_result,
        evict_error=evict_error,
        log=log,
    )
    fake_osaurus = FakeOsaurus(
        recover=recover, pin_error=pin_error, restore=restore,
        restore_error=restore_error, log=log,
    )
    probe = PortProbe(port_busy)
    events = []
    cells = run_cells
    if cells is None:
        cells = FakeRunCells(answers, on_call=lambda cell, _kwargs: log.append(("cell", cell.id)))

    ok = quickbench.run(
        CHOSEN.repo,
        confirmed=confirmed,
        osaurus=osaurus,
        models=models,
        statuses=engines_list,
        hw=SimpleNamespace(),
        run_cells=cells,
        download=cache.download,
        evict=cache.evict,
        downloaded=cache.downloaded,
        pin=fake_osaurus.pin,
        restore=fake_osaurus.restore,
        recover=fake_osaurus.recover,
        port_in_use=probe,
        osaurus_app_running=lambda: app_running,
        load=FakeLoad(loads),
        clock=FakeClock(),
        emit=events.append,
        cancel=CancelAfter(cancel_after),
        abort=quickbench._never_cancelled if abort is None else abort,
        cache_dir=str(tmp_path / "cache"),
        results_dir=str(tmp_path / "quickbench"),
        backup_dir=str(tmp_path / "backup"),
        baseline_path=str(tmp_path / "baseline.json"),
    )
    found = sorted((tmp_path / "quickbench").glob("*/summary.json"))
    summary = json.loads(found[0].read_text(encoding="utf-8")) if found else None
    fakes = SimpleNamespace(
        cache=cache,
        osaurus=fake_osaurus,
        probe=probe,
        events=events,
        run_cells=cells,
        log=log,
    )
    return ok, fakes, summary


def a_plan(tmp_path, *, downloaded=(CHOSEN.repo,), engines_list=ENGINES, models=MODELS):
    cache = FakeCache(downloaded=downloaded)
    return quickbench.plan(
        CHOSEN.repo,
        SimpleNamespace(),
        engines_list,
        models,
        cache_dir=str(tmp_path / "cache"),
        downloaded=cache.downloaded,
    )


# --- AC-1: the plan is shown before anything runs ---------------------------------------------


def test_the_plan_lists_installed_engines_that_list_the_row(tmp_path):
    """Untested builds are included and labelled, and an installed engine the row does not
    list is not a stage-A cell -- the engine list comes from the row."""
    statuses = [
        an_engine("mlxlm", version="0.31.3", tested=True),
        an_engine("optiq", version="0.5.14", tested=False),
        an_engine("omlx", version="0.7.3", tested=False),
        an_engine("vmlx", installed=False, version=None),
    ]
    row = a_model(CHOSEN.repo, CHOSEN.format, CHOSEN.base, engine_names=("mlxlm", "optiq"))

    shown = a_plan(tmp_path, engines_list=statuses, models=[row])

    assert [
        (engine.engine, engine.version, engine.tested) for engine in shown.stage_a
    ] == [("mlxlm", "0.31.3", True), ("optiq", "0.5.14", False)]


def test_the_plan_names_the_siblings_and_only_the_missing_download_bytes(tmp_path):
    """The chosen row is not a sibling, an unrelated base is not one either, and a sibling
    already in the cache contributes no download."""
    shown = a_plan(tmp_path, downloaded=(CHOSEN.repo, SIBLING_2.repo))

    assert [sibling.repo for sibling in shown.stage_b] == [SIBLING.repo, SIBLING_2.repo]
    assert [sibling.downloaded for sibling in shown.stage_b] == [False, True]
    assert shown.download_bytes == SIBLING.size_bytes


def test_the_plan_estimate_is_per_cell_plus_the_download_at_the_constant_rate(tmp_path):
    shown = a_plan(tmp_path, downloaded=(CHOSEN.repo,))

    # Two installed engines plus two sibling formats is four cells at 90 s, and the 7 GB of
    # missing siblings is 350 s at the assumed 20 MB/s.
    assert len(shown.stage_a) == 2 and len(shown.stage_b) == 2
    assert shown.download_bytes == 7_000_000_000
    assert shown.estimate_s == 4 * 90 + 350


def test_the_plan_refuses_a_repo_that_is_not_downloaded(tmp_path):
    with pytest.raises(ValueError, match="download it first"):
        a_plan(tmp_path, downloaded=())


def test_the_plan_refuses_a_repo_that_is_not_a_catalog_model(tmp_path):
    with pytest.raises(ValueError, match="not a catalog model"):
        quickbench.plan(
            "org/nope",
            SimpleNamespace(),
            ENGINES,
            MODELS,
            cache_dir=str(tmp_path / "cache"),
            downloaded=FakeCache(downloaded=(CHOSEN.repo,)).downloaded,
        )


def test_the_plan_says_whether_osaurus_would_be_pinned(tmp_path):
    assert a_plan(tmp_path, engines_list=WITH_OSAURUS).osaurus is True
    assert a_plan(tmp_path, engines_list=ENGINES).osaurus is False


def test_the_plan_creates_nothing_and_measures_nothing(tmp_path):
    """AC-1 is the "before anything runs" screen: no directory, no cell, no port probe."""
    shown = a_plan(tmp_path)

    assert shown.stage_a
    assert not (tmp_path / "quickbench").exists()
    assert not (tmp_path / "cache").exists()


# --- AC-2: stage A, then stage B, one variable each -------------------------------------------


def test_each_cell_is_one_run_cells_call_through_the_one_selector(tmp_path):
    """One `--cells` string per cell and `build_cells` turns it into the selection; the
    light-cell pins and the stage directory are the plan's own."""
    ok, fakes, summary = a_run(tmp_path)

    assert ok is True
    snapshot = fetch.plan(CHOSEN, str(tmp_path / "cache")).snapshot_dir
    assert len(fakes.run_cells.calls) == 2 + 2
    for call in fakes.run_cells.calls:
        assert len(call["cells"]) == 1
        cell = call["cells"][0]
        assert cell.id == f"{cell.label}__{cell.runtime}"
        assert cell.artifact_dir
        assert [workload.id for workload in call["workloads"]] == ["decode"]
        assert call["warmup"] == 3
        assert call["measured"] == 5
        assert call["cooldown_s"] == 10
        assert call["quick"] is True
    first = fakes.run_cells.calls[0]
    assert first["cells"][0].artifact_dir == snapshot
    assert first["cells"][0].runtime == "mlxlm"
    assert first["results_dir"].endswith(os.path.join("A", "mlxlm"))


def test_stage_a_names_the_winner_and_reports_cells_within_the_tie_band(tmp_path):
    _ok, _fakes, summary = a_run(tmp_path, answers={"mlxlm": ("PASS", 60), "optiq": ("PASS", 58)})
    assert summary["stage_a"]["winner"] == "mlxlm"
    assert summary["stage_a"]["tie"] == ["mlxlm", "optiq"]

    _ok, _fakes, summary = a_run(tmp_path / "second", answers={"mlxlm": ("PASS", 60), "optiq": ("PASS", 40)})
    assert summary["stage_a"]["winner"] == "mlxlm"
    assert summary["stage_a"]["tie"] == []


def test_no_pass_cell_means_stage_b_does_not_run_and_the_summary_says_why(tmp_path):
    ok, fakes, summary = a_run(
        tmp_path,
        answers={"mlxlm": ("FAIL", 60), "optiq": ("FAIL", 50)},
    )

    assert ok is True
    assert summary["stage_a"]["winner"] is None
    assert summary["stage_b"]["cells"] == []
    assert summary["stage_b"]["engine"] is None
    assert "not run" in summary["stage_b"]["note"]
    assert fakes.cache.downloads == []
    assert len(fakes.run_cells.calls) == 2, "stage B measured nothing"


def test_a_row_no_installed_engine_lists_measures_nothing_and_says_so(tmp_path):
    ok, fakes, summary = a_run(tmp_path, engines_list=[an_engine("omlx")])

    assert ok is True
    assert summary["stage_a"]["cells"] == []
    assert f"no installed engine lists {CHOSEN.repo}" in summary["stage_b"]["note"]
    assert fakes.run_cells.calls == []


def test_stage_a_uses_the_pinned_snapshot_not_a_newest_mtime_lookup(tmp_path):
    """Audit finding 4: the artifact dir is the catalog revision, whatever is newer."""
    cache = tmp_path / "cache"
    snapshot = Path(fetch.plan(CHOSEN, str(cache)).snapshot_dir)
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text("{}")
    decoy = cache / "models--org--two-b-stock" / "snapshots" / ("f" * 40)
    decoy.mkdir(parents=True)
    (decoy / "config.json").write_text("{}")
    os.utime(decoy, (2_000_000_000, 2_000_000_000))

    _ok, fakes, _summary = a_run(tmp_path)

    assert fakes.run_cells.calls[0]["cells"][0].artifact_dir == str(snapshot)


def test_stage_b_reuses_the_chosen_rows_row_and_measures_each_sibling(tmp_path):
    ok, fakes, summary = a_run(tmp_path)

    assert ok is True
    assert summary["stage_b"]["engine"] == "mlxlm"
    reused, first_sibling, second_sibling = summary["stage_b"]["cells"]
    assert reused["reused"] is True
    assert (reused["format"], reused["engine"]) == (CHOSEN.format, "mlxlm")
    assert reused["decode_tps"] == summary["stage_a"]["cells"][0]["decode_tps"]
    assert (first_sibling["format"], first_sibling["reused"]) == (SIBLING.format, False)
    assert (second_sibling["format"], second_sibling["reused"]) == (SIBLING_2.format, False)
    assert len(fakes.run_cells.calls) == 4, "the chosen row is reused, not measured twice"


def test_a_missing_sibling_is_downloaded_before_its_cell_and_evicted_after_it(tmp_path):
    _ok, fakes, _summary = a_run(tmp_path, downloaded=(CHOSEN.repo,))

    assert fakes.cache.downloads == [SIBLING.repo, SIBLING_2.repo]
    assert fakes.cache.evicts == [SIBLING.repo, SIBLING_2.repo]
    for sibling in (SIBLING, SIBLING_2):
        downloaded = fakes.log.index(("download", sibling.repo))
        evicted = fakes.log.index(("evict", sibling.repo))
        between = [entry for entry in fakes.log[downloaded:evicted] if entry[0] == "cell"]
        assert len(between) == 1, "the sibling's own cell runs between its download and evict"
    # The sibling is fetched into and evicted from the run's own cache, never the default one.
    assert fakes.cache.cache_dirs == [str(tmp_path / "cache")] * 4


def test_an_already_downloaded_sibling_is_neither_downloaded_nor_evicted(tmp_path):
    _ok, fakes, _summary = a_run(
        tmp_path, downloaded=(CHOSEN.repo, SIBLING.repo, SIBLING_2.repo)
    )

    assert fakes.cache.downloads == []
    assert fakes.cache.evicts == []


def test_a_refused_sibling_eviction_is_logged_and_recorded(tmp_path):
    """AC-4: a `busy` (or any) evict refusal is a fact about what this run left on disk,
    not a return value to discard."""
    ok, fakes, summary = a_run(tmp_path, evict_result=False)

    assert ok is True
    assert fakes.cache.evicts == [SIBLING.repo, SIBLING_2.repo]
    assert summary["not_evicted"] == [SIBLING.repo, SIBLING_2.repo]
    for sibling in (SIBLING, SIBLING_2):
        events = [
            event
            for event in fakes.events
            if event["type"] == "log" and event["payload"] == {"repo": sibling.repo}
        ]
        assert len(events) == 1, "one log event names the repo that was not evicted"


def test_an_evictor_that_raises_is_logged_and_recorded(tmp_path):
    """An eviction that raises is a repo still on disk, not a reason to end the run: the
    catch is the leftover sweep's (one log event naming the repo) and the repo is recorded."""
    ok, fakes, summary = a_run(tmp_path, evict_error=OSError("the log path is not writable"))

    assert ok is True
    assert summary["ended"] == "finished"
    assert fakes.cache.evicts == [SIBLING.repo, SIBLING_2.repo]
    assert summary["not_evicted"] == [SIBLING.repo, SIBLING_2.repo]
    for sibling in (SIBLING, SIBLING_2):
        events = [
            event
            for event in fakes.events
            if event["type"] == "log" and event["payload"] == {"repo": sibling.repo}
        ]
        assert len(events) == 1, "one log event names the repo whose eviction raised"
        assert "the log path is not writable" in events[0]["message"]


def test_nothing_not_evicted_leaves_an_empty_list(tmp_path):
    _ok, _fakes, summary = a_run(tmp_path)

    assert summary["not_evicted"] == []


def test_a_refused_sweep_eviction_is_logged_and_recorded(tmp_path):
    """The `outstanding` sweep's evict refuses too: the repo stays named in the summary
    rather than vanishing with the run."""
    ok, fakes, summary = a_run(
        tmp_path, downloaded=(CHOSEN.repo,), cancel_after=3, evict_result=False
    )

    assert ok is False
    assert summary["ended"] == "cancelled"
    assert fakes.cache.evicts == [SIBLING.repo], "the sweep, not the per-cell finally"
    assert summary["not_evicted"] == [SIBLING.repo]
    events = [
        event
        for event in fakes.events
        if event["type"] == "log" and event["payload"] == {"repo": SIBLING.repo}
    ]
    assert len(events) == 1


def test_the_chosen_repo_is_never_downloaded_or_evicted(tmp_path):
    """The one cell quickbench must not touch: its bytes were the user's own choice."""
    _ok, fakes, _summary = a_run(tmp_path)

    assert CHOSEN.repo not in fakes.cache.downloads
    assert CHOSEN.repo not in fakes.cache.evicts


def test_the_summary_is_a_record_of_the_whole_run(tmp_path):
    ok, _fakes, summary = a_run(tmp_path, loads=(1.0, 2.0, 0.5, 0.4))

    assert ok is True
    assert summary["ended"] == "finished"
    assert summary["repo"] == CHOSEN.repo
    assert summary["plan"]["stage_a"]
    assert summary["estimate_s"] == quickbench.plan(
        CHOSEN.repo,
        SimpleNamespace(),
        ENGINES,
        MODELS,
        cache_dir=str(tmp_path / "cache"),
        downloaded=FakeCache(downloaded=(CHOSEN.repo,)).downloaded,
    ).estimate_s
    assert isinstance(summary["actual_s"], float) and summary["actual_s"] >= 0
    assert summary["harness"]["version"]
    assert len(summary["harness"]["source_sha256"]) == 64
    assert [entry["name"] for entry in summary["engines"]] == ["mlxlm", "optiq"]
    assert all(entry["tested"] is True for entry in summary["engines"])
    assert summary["load"]["stage_a"] == {"before": 1.0, "after": 2.0, "label": None}
    assert summary["load"]["stage_b"] == {"before": 0.5, "after": 0.4, "label": None}
    assert summary["stage_a"]["caveat"] == "engines compared on one format only"
    assert summary["stage_b"]["caveat"] == "formats compared on one engine only"
    assert summary["label"] == "quick: measured on this Mac"
    for cell in summary["stage_a"]["cells"] + summary["stage_b"]["cells"]:
        assert cell["status"] in ("PASS", "FAIL", "SKIPPED")
        assert "reason" in cell
        assert cell["label"] == "quick: measured on this Mac"
    assert summary["best"] == {
        "engine": "mlxlm",
        "decode_tps": 60.0,
        "ttft_s": 0.2,
        "measured_at": summary["best"]["measured_at"],
        "quick": True,
    }
    assert not list(Path(summary["results_dir"]).glob("*.tmp")), "the write is atomic"


def test_a_run_without_consent_starts_nothing(tmp_path):
    ok, fakes, summary = a_run(tmp_path, confirmed=False)

    assert ok is False
    assert summary is None, "no run directory exists for a refused run"
    assert fakes.run_cells.calls == []
    assert [event["payload"]["code"] for event in fakes.events if event["type"] == "error"] == [
        "consent_required"
    ]


# --- AC-3: nothing the user owns is changed without consent -----------------------------------


def test_the_default_port_probe_asks_runtimes_and_reads_unknown_as_busy(monkeypatch):
    """One guard, not a second TCP probe: `runtimes._port_is_free`, with its no-answer as busy."""
    monkeypatch.setattr(runtimes, "_port_is_free", lambda port: port == 8100)

    assert quickbench._port_busy(8100) is False
    assert quickbench._port_busy(8081) is True


def test_an_engine_whose_port_is_in_use_is_skipped_with_quit_first(tmp_path):
    busy = runtimes.RUNTIMES["optiq"].port
    _ok, fakes, summary = a_run(tmp_path, port_busy=(busy,))

    optiq = next(
        cell for cell in summary["stage_a"]["cells"] if cell["engine"] == "optiq"
    )
    assert optiq["status"] == "SKIPPED"
    assert optiq["reason"] == "quit optiq first"
    assert busy in fakes.probe.ports, "the port is probed before the engine is skipped"
    assert all(
        call["cells"][0].runtime != "optiq" for call in fakes.run_cells.calls
    ), "nothing on that port was started"


def test_osaurus_is_skipped_while_its_app_runs(tmp_path):
    _ok, fakes, summary = a_run(
        tmp_path, engines_list=WITH_OSAURUS, osaurus=True, app_running=True
    )

    osaurus = next(
        cell for cell in summary["stage_a"]["cells"] if cell["engine"] == "osaurus"
    )
    assert osaurus["status"] == "SKIPPED"
    assert osaurus["reason"] == "quit the Osaurus app first"
    assert fakes.osaurus.calls == []
    assert all(
        call["cells"][0].runtime != "osaurus" for call in fakes.run_cells.calls
    )


def test_osaurus_is_skipped_without_consent(tmp_path):
    _ok, fakes, summary = a_run(tmp_path, engines_list=WITH_OSAURUS, osaurus=False)

    osaurus = next(
        cell for cell in summary["stage_a"]["cells"] if cell["engine"] == "osaurus"
    )
    assert osaurus["status"] == "SKIPPED"
    assert "osaurus: false" in osaurus["reason"]
    assert fakes.osaurus.calls == []


def test_osaurus_is_recovered_pinned_and_restored_around_its_cell(tmp_path):
    ok, fakes, summary = a_run(tmp_path, engines_list=WITH_OSAURUS, osaurus=True)

    assert ok is True
    kinds = [entry[0] for entry in fakes.log]
    recover = kinds.index("recover")
    pin = kinds.index("pin")
    cell = next(
        index
        for index, entry in enumerate(fakes.log)
        if entry[0] == "cell" and entry[1].endswith("__osaurus")
    )
    restore = kinds.index("restore")
    assert recover < pin < cell < restore
    # AC-2: recover, pin and restore are handed the same backup and the same baseline, and the
    # baseline is the drift guard's -- a pin against another path is a pin the guard never saw.
    assert [kind for kind, _kwargs in fakes.osaurus.calls] == [
        "recover",
        "pin",
        "restore",
    ]
    for kind, kwargs in fakes.osaurus.calls:
        assert kwargs["backup_dir"] == str(tmp_path / "backup"), kind
        assert kwargs["baseline_path"] == str(tmp_path / "baseline.json"), kind
    assert summary["osaurus"] == {
        "allowed": True,
        "pinned": True,
        "restored": True,
        "reason": None,
    }


def test_quickbench_pins_against_the_drift_guards_baseline_by_default():
    assert not hasattr(quickbench, "DEFAULT_BASELINE_PATH"), "one baseline path, the guard's"
    default = inspect.signature(quickbench.run).parameters["baseline_path"].default
    assert default == osaurus_settings.BASELINE_PATH


def test_the_host_pinned_between_pin_and_restore_shows_no_drift(tmp_path):
    """04-03c's defect: a pin against a path the guard does not read leaves the pinned host
    (caches off) reading as drift, and the cell is refused. Real pin/restore on tmp paths."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "server.json").write_text(json.dumps({"numberOfThreads": 12}))
    (config_dir / "server-runtime.json").write_text(
        json.dumps(
            {
                "cache": {
                    "blockDisk": {"enabled": True},
                    "prefix": {"enabled": True},
                }
            }
        )
    )
    baseline_path = tmp_path / "baseline.json"
    captured = []
    cache = FakeCache(downloaded=(CHOSEN.repo,))

    def capture_between_pin_and_restore(_cell, _kwargs):
        captured.append(
            osaurus_settings.diff_against_baseline(
                osaurus_settings.capture_osaurus_settings(config_dir),
                osaurus_settings.load_baseline(baseline_path),
            )
        )

    ok = quickbench.run(
        CHOSEN.repo,
        confirmed=True,
        osaurus=True,
        models=MODELS,
        statuses=[an_engine("osaurus")],
        hw=SimpleNamespace(),
        run_cells=FakeRunCells(on_call=capture_between_pin_and_restore),
        download=cache.download,
        evict=cache.evict,
        downloaded=cache.downloaded,
        pin=lambda **kwargs: osaurus_settings.pin(config_dir, **kwargs),
        restore=lambda **kwargs: osaurus_settings.restore(config_dir, **kwargs),
        recover=lambda **kwargs: osaurus_settings.recover(config_dir, **kwargs),
        osaurus_drift=lambda **kwargs: quickbench._osaurus_drift(
            config_dir=config_dir, **kwargs
        ),
        keep_during_run=lambda **kwargs: quickbench._keep_during_run(
            config_dir=config_dir, **kwargs
        ),
        port_in_use=lambda port: False,
        osaurus_app_running=lambda: False,
        load=FakeLoad(),
        clock=FakeClock(),
        emit=[].append,
        cancel=CancelAfter(),
        cache_dir=str(tmp_path / "cache"),
        results_dir=str(tmp_path / "quickbench"),
        backup_dir=str(tmp_path / "backup"),
        baseline_path=str(baseline_path),
    )

    assert ok is True
    assert len(captured) == 3, "one capture per Osaurus cell, each between its pin and restore"
    assert all(drift == () for drift in captured), captured
    assert not (tmp_path / "backup").exists(), "a verified restore left no backup behind"
    assert not baseline_path.exists(), "the pin's baseline went with the restore"


def test_drift_between_pin_and_restore_fails_the_cell_and_keeps_both_copies(tmp_path):
    """045-02a AC-7: a host that moved under the cell fails it, and both files are kept."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    originals = {
        "server.json": json.dumps({"numberOfThreads": 12}).encode(),
        "server-runtime.json": json.dumps(
            {
                "cache": {
                    "blockDisk": {"enabled": True},
                    "prefix": {"enabled": True},
                    "defaultMaxKVSize": 4096,
                }
            }
        ).encode(),
    }
    for name, data in originals.items():
        (config_dir / name).write_bytes(data)
    baseline_path = tmp_path / "baseline.json"
    during_run_dir = tmp_path / "backup" / "during-run"
    rewritten = {}

    def rewrite_a_pinned_key(_cell, _kwargs):
        (config_dir / "server.json").write_text(json.dumps({"numberOfThreads": 4}))
        (config_dir / "server-runtime.json").write_text(
            json.dumps(
                {
                    "cache": {
                        "blockDisk": {"enabled": False},
                        "prefix": {"enabled": False},
                        "defaultMaxKVSize": 8192,
                    }
                }
            )
        )
        for name in osaurus_settings.PIN_FILES:
            rewritten[name] = (config_dir / name).read_bytes()

    kept_at_restore = []

    def restore(**kwargs):
        kept_at_restore.append(
            {
                name: (during_run_dir / name).read_bytes()
                for name in osaurus_settings.PIN_FILES
                if (during_run_dir / name).exists()
            }
        )
        return osaurus_settings.restore(config_dir, **kwargs)

    ok = quickbench.run(
        CHOSEN.repo,
        confirmed=True,
        osaurus=True,
        models=[CHOSEN],
        statuses=[an_engine("osaurus")],
        hw=SimpleNamespace(),
        run_cells=FakeRunCells(on_call=rewrite_a_pinned_key),
        downloaded=lambda model, cache_dir=None: True,
        pin=lambda **kwargs: osaurus_settings.pin(config_dir, **kwargs),
        restore=restore,
        recover=lambda **kwargs: osaurus_settings.recover(config_dir, **kwargs),
        osaurus_drift=lambda **kwargs: quickbench._osaurus_drift(
            config_dir=config_dir, **kwargs
        ),
        keep_during_run=lambda **kwargs: quickbench._keep_during_run(
            config_dir=config_dir, **kwargs
        ),
        port_in_use=lambda port: False,
        osaurus_app_running=lambda: False,
        load=FakeLoad(),
        clock=FakeClock(),
        emit=[].append,
        cancel=CancelAfter(),
        cache_dir=str(tmp_path / "cache"),
        results_dir=str(tmp_path / "quickbench"),
        backup_dir=str(tmp_path / "backup"),
        baseline_path=str(baseline_path),
    )

    summary = json.loads(
        next((tmp_path / "quickbench").glob("*/summary.json")).read_text(
            encoding="utf-8"
        )
    )
    cell = next(
        cell for cell in summary["stage_a"]["cells"] if cell["engine"] == "osaurus"
    )
    assert ok is True
    assert cell["status"] == "FAIL"
    assert cell["reason"].startswith("Osaurus changed its settings during the run: ")
    assert "server.json:numberOfThreads" in cell["reason"]
    assert "server-runtime.json:cache.defaultMaxKVSize" in cell["reason"]
    assert (during_run_dir.stat().st_mode & 0o777) == 0o700
    for name in osaurus_settings.PIN_FILES:
        assert (during_run_dir / name).read_bytes() == rewritten[name]
    assert kept_at_restore == [rewritten], "both files were kept before restore ran"
    assert summary["osaurus"]["during_run"] == str(during_run_dir)
    # The restore still ran and verified, so the user's originals are back.
    assert summary["osaurus"]["restored"] is True
    for name, data in originals.items():
        assert (config_dir / name).read_bytes() == data


def test_no_drift_between_pin_and_restore_passes_and_keeps_nothing(tmp_path):
    """AC-7's other half: an unchanged host leaves today's behaviour exactly as it was."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "server.json").write_text(json.dumps({"numberOfThreads": 12}))
    (config_dir / "server-runtime.json").write_text(
        json.dumps(
            {
                "cache": {
                    "blockDisk": {"enabled": True},
                    "prefix": {"enabled": True},
                }
            }
        )
    )

    ok = quickbench.run(
        CHOSEN.repo,
        confirmed=True,
        osaurus=True,
        models=[CHOSEN],
        statuses=[an_engine("osaurus")],
        hw=SimpleNamespace(),
        run_cells=FakeRunCells(),
        downloaded=lambda model, cache_dir=None: True,
        pin=lambda **kwargs: osaurus_settings.pin(config_dir, **kwargs),
        restore=lambda **kwargs: osaurus_settings.restore(config_dir, **kwargs),
        recover=lambda **kwargs: osaurus_settings.recover(config_dir, **kwargs),
        osaurus_drift=lambda **kwargs: quickbench._osaurus_drift(
            config_dir=config_dir, **kwargs
        ),
        keep_during_run=lambda **kwargs: quickbench._keep_during_run(
            config_dir=config_dir, **kwargs
        ),
        port_in_use=lambda port: False,
        osaurus_app_running=lambda: False,
        load=FakeLoad(),
        clock=FakeClock(),
        emit=[].append,
        cancel=CancelAfter(),
        cache_dir=str(tmp_path / "cache"),
        results_dir=str(tmp_path / "quickbench"),
        backup_dir=str(tmp_path / "backup"),
        baseline_path=str(tmp_path / "baseline.json"),
    )

    summary = json.loads(
        next((tmp_path / "quickbench").glob("*/summary.json")).read_text(
            encoding="utf-8"
        )
    )
    cell = next(
        cell for cell in summary["stage_a"]["cells"] if cell["engine"] == "osaurus"
    )
    assert ok is True
    assert cell["status"] == "PASS"
    assert "during_run" not in summary["osaurus"]
    assert not (tmp_path / "backup" / "during-run").exists()
    assert not (tmp_path / "backup").exists(), "a verified restore left no backup behind"


def test_a_drift_check_that_raises_fails_the_cell_and_still_restores(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    originals = {
        "server.json": json.dumps({"numberOfThreads": 12}).encode(),
        "server-runtime.json": json.dumps(
            {
                "cache": {
                    "blockDisk": {"enabled": True},
                    "prefix": {"enabled": True},
                }
            }
        ).encode(),
    }
    for name, data in originals.items():
        (config_dir / name).write_bytes(data)

    def raising_drift(**_kwargs):
        raise RuntimeError("cannot read the host's settings")

    ok = quickbench.run(
        CHOSEN.repo,
        confirmed=True,
        osaurus=True,
        models=[CHOSEN],
        statuses=[an_engine("osaurus")],
        hw=SimpleNamespace(),
        run_cells=FakeRunCells(),
        downloaded=lambda model, cache_dir=None: True,
        pin=lambda **kwargs: osaurus_settings.pin(config_dir, **kwargs),
        restore=lambda **kwargs: osaurus_settings.restore(config_dir, **kwargs),
        recover=lambda **kwargs: osaurus_settings.recover(config_dir, **kwargs),
        osaurus_drift=raising_drift,
        keep_during_run=lambda **kwargs: quickbench._keep_during_run(
            config_dir=config_dir, **kwargs
        ),
        port_in_use=lambda port: False,
        osaurus_app_running=lambda: False,
        load=FakeLoad(),
        clock=FakeClock(),
        emit=[].append,
        cancel=CancelAfter(),
        cache_dir=str(tmp_path / "cache"),
        results_dir=str(tmp_path / "quickbench"),
        backup_dir=str(tmp_path / "backup"),
        baseline_path=str(tmp_path / "baseline.json"),
    )

    summary = json.loads(
        next((tmp_path / "quickbench").glob("*/summary.json")).read_text(
            encoding="utf-8"
        )
    )
    cell = next(
        cell for cell in summary["stage_a"]["cells"] if cell["engine"] == "osaurus"
    )
    assert ok is True
    assert cell["status"] == "FAIL"
    assert cell["reason"] == "cannot read the host's settings"
    assert "during_run" not in summary["osaurus"]
    # Restore still ran and verified, so the user's originals are back.
    assert summary["osaurus"]["restored"] is True
    for name, data in originals.items():
        assert (config_dir / name).read_bytes() == data
    assert not (tmp_path / "backup").exists()


def test_a_cell_that_raises_still_restores_osaurus(tmp_path):
    def raising(cells, workloads, **kwargs):
        raise RuntimeError("the runtime refused to start")

    ok, fakes, summary = a_run(
        tmp_path, engines_list=WITH_OSAURUS, osaurus=True, run_cells=raising
    )

    assert ok is True
    assert [entry[0] for entry in fakes.osaurus.calls] == ["recover", "pin", "restore"]
    osaurus = next(
        cell for cell in summary["stage_a"]["cells"] if cell["engine"] == "osaurus"
    )
    assert osaurus["status"] == "FAIL"
    assert osaurus["reason"] == "the runtime refused to start"


def test_osaurus_wins_stage_a_and_is_pinned_again_for_stage_b(tmp_path):
    """AC-3's per-cell rule: every Osaurus cell is pinned before it and restored after it."""
    ok, fakes, summary = a_run(
        tmp_path,
        engines_list=[an_engine("osaurus")],
        osaurus=True,
        downloaded=(CHOSEN.repo,),
    )

    assert ok is True
    assert summary["stage_a"]["winner"] == "osaurus"
    assert [entry[0] for entry in fakes.osaurus.calls] == [
        "recover",
        "pin",
        "restore",
    ] * 3
    assert summary["osaurus"]["pinned"] is True
    assert summary["osaurus"]["restored"] is True
    assert len(fakes.run_cells.calls) == 3, "one stage-A cell and the two sibling cells"


def test_a_restore_that_does_not_verify_ends_the_run_and_names_the_backup(tmp_path):
    ok, fakes, summary = a_run(
        tmp_path, engines_list=WITH_OSAURUS, osaurus=True, restore=False
    )

    assert ok is False
    assert summary["ended"] == "restore_failed"
    assert summary["osaurus"]["restored"] is False
    assert summary["best"] is None
    errors = [event for event in fakes.events if event["type"] == "error"]
    assert errors[-1]["payload"]["code"] == "restore_failed"
    assert errors[-1]["payload"]["backup_dir"] == str(tmp_path / "backup")
    assert str(tmp_path / "backup") in errors[-1]["message"]
    assert summary["stage_b"]["cells"] == [], "the run stops after a failed restore"


def test_a_restore_that_raises_ends_the_run_exactly_as_a_false_one(tmp_path):
    """A raise after a pin that took effect is a restore that did not verify, not a log line."""
    ok, fakes, summary = a_run(
        tmp_path,
        engines_list=WITH_OSAURUS,
        osaurus=True,
        restore_error="the settings write failed",
    )

    assert ok is False
    assert summary["ended"] == "restore_failed"
    assert summary["osaurus"]["restored"] is False
    assert summary["best"] is None
    errors = [event for event in fakes.events if event["type"] == "error"]
    assert errors[-1]["payload"]["code"] == "restore_failed"
    assert errors[-1]["payload"]["backup_dir"] == str(tmp_path / "backup")
    assert str(tmp_path / "backup") in errors[-1]["message"]
    assert summary["stage_b"]["cells"] == [], "the run stops after a raising restore"


def test_a_cancelled_ending_carries_the_summary_path_in_its_terminal_events(tmp_path):
    _ok, fakes, summary = a_run(tmp_path, cancel_after=0)

    assert [event["type"] for event in fakes.events[-2:]] == ["error", "done"]
    assert fakes.events[-2]["payload"] == {
        "code": "cancelled",
        "results_dir": summary["results_dir"],
    }
    assert fakes.events[-1]["payload"] == {"results_dir": summary["results_dir"]}


def test_a_restore_failed_ending_carries_the_summary_path_in_its_done(tmp_path):
    _ok, fakes, summary = a_run(
        tmp_path, engines_list=WITH_OSAURUS, osaurus=True, restore=False
    )

    done = fakes.events[-1]
    assert done["type"] == "done"
    assert done["payload"] == {"results_dir": summary["results_dir"]}


def test_a_pin_that_refuses_skips_osaurus_with_that_reason(tmp_path):
    _ok, fakes, summary = a_run(
        tmp_path,
        engines_list=WITH_OSAURUS,
        osaurus=True,
        pin_error="refusing to pin Osaurus settings: the backup directory already holds one",
    )

    osaurus = next(
        cell for cell in summary["stage_a"]["cells"] if cell["engine"] == "osaurus"
    )
    assert osaurus["status"] == "SKIPPED"
    assert "already holds one" in osaurus["reason"]
    assert all(
        call["cells"][0].runtime != "osaurus" for call in fakes.run_cells.calls
    )


def test_a_busy_stage_is_labelled_but_still_measured(tmp_path):
    ok, fakes, summary = a_run(tmp_path, loads=(1.0, 6.0, 0.5, 0.4))

    assert ok is True
    assert summary["load"]["stage_a"]["label"] == "this Mac was busy"
    assert summary["load"]["stage_b"]["label"] is None
    assert any("this Mac was busy" in event["message"] for event in fakes.events)


# --- AC-4: runs as a job, cancellable between cells -------------------------------------------


def test_a_cancelled_run_stops_between_cells_and_writes_its_summary(tmp_path):
    ok, fakes, summary = a_run(tmp_path, cancel_after=0)

    assert ok is False
    assert summary["ended"] == "cancelled"
    assert summary["best"] is None
    assert fakes.run_cells.calls == []
    assert [
        (cell["engine"], cell["status"], cell["reason"])
        for cell in summary["stage_a"]["cells"]
    ] == [
        ("mlxlm", "SKIPPED", quickbench.CANCELLED),
        ("optiq", "SKIPPED", quickbench.CANCELLED),
    ]
    assert summary["stage_b"]["note"] == "stage B was not run: the run was cancelled"
    assert [event["payload"]["code"] for event in fakes.events if event["type"] == "error"] == [
        "cancelled"
    ]


def test_cancel_after_a_sibling_download_evicts_it_and_measures_no_more(tmp_path):
    """`after=3` is the check after the first sibling's download: stage A's two checks, then
    the stage-B top-of-loop check, then that one."""
    ok, fakes, summary = a_run(
        tmp_path, downloaded=(CHOSEN.repo,), cancel_after=3
    )

    assert ok is False
    assert summary["ended"] == "cancelled"
    assert fakes.cache.downloads == [SIBLING.repo]
    assert fakes.cache.evicts == [SIBLING.repo], "what this run fetched is taken back out"
    assert len(fakes.run_cells.calls) == 2, "no sibling cell was measured"
    assert [
        (cell["format"], cell["status"], cell["reason"])
        for cell in summary["stage_b"]["cells"][1:]
    ] == [
        (SIBLING.format, "SKIPPED", quickbench.CANCELLED),
        (SIBLING_2.format, "SKIPPED", quickbench.CANCELLED),
    ]


# --- AC-5: the summary feeds the recommendations ----------------------------------------------


def test_latest_returns_the_newest_finished_summary_per_repo(tmp_path):
    root = tmp_path / "quickbench"

    def write(stamp, payload, *, mtime):
        directory = root / stamp
        directory.mkdir(parents=True)
        path = directory / "summary.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        os.utime(path, (mtime, mtime))

    write(
        "old",
        {"repo": "org/a", "ended": "finished", "best": {"engine": "mlxlm"}},
        mtime=1_000,
    )
    write(
        "new",
        {"repo": "org/a", "ended": "finished", "best": {"engine": "optiq"}},
        mtime=2_000,
    )
    write(
        "cancelled",
        {"repo": "org/b", "ended": "cancelled", "best": None},
        mtime=3_000,
    )
    (root / "broken").mkdir()
    (root / "broken" / "summary.json").write_text("{not json", encoding="utf-8")

    found = quickbench.latest(root)

    assert set(found) == {"org/a"}
    assert found["org/a"]["best"] == {"engine": "optiq"}


def test_latest_of_a_missing_root_is_no_summaries(tmp_path):
    assert quickbench.latest(tmp_path / "absent") == {}


def test_the_summary_the_run_wrote_is_what_latest_reads(tmp_path):
    _ok, _fakes, _summary = a_run(tmp_path)

    found = quickbench.latest(tmp_path / "quickbench")

    assert list(found) == [CHOSEN.repo]
    assert found[CHOSEN.repo]["best"]["engine"] == "mlxlm"
    assert found[CHOSEN.repo]["best"]["quick"] is True


# --- plan 045-02a AC-5: the Osaurus-app probe names its tool absolutely -----------------------


def test_the_osaurus_app_probe_runs_the_absolute_ps():
    calls = []

    def run(argv, **kwargs):
        calls.append(list(argv))
        return SimpleNamespace(stdout="")

    assert quickbench._osaurus_app_running(run=run) is False
    assert runtimes.PS == "/bin/ps"
    assert calls == [[runtimes.PS, "-axo", "comm="]]


# --- 05-01 AC-3/AC-7: "Stop now", a stop that lands while a cell is being measured ----------
#
# The server stops the engine from outside; quickbench only sees the abort probe answer True
# after the cell's own call returns (or raises). A fake run loop flips the probe while it is
# inside the cell, which is exactly what that looks like from here.


def test_an_abort_during_stage_as_first_cell_records_it_aborted_and_ends_cancelled(tmp_path):
    probe = AbortProbe()
    cells = FakeRunCells(
        on_call=lambda _cell, _kwargs: setattr(probe, "triggered", True)
    )

    ok, fakes, summary = a_run(tmp_path, run_cells=cells, abort=probe)

    assert ok is False
    assert len(fakes.run_cells.calls) == 1, "a cell was measured after the stop"
    aborted, skipped = summary["stage_a"]["cells"]
    assert (aborted["engine"], aborted["status"]) == ("mlxlm", quickbench.ABORTED)
    assert aborted["reason"] == quickbench.ABORTED_REASON
    assert aborted["decode_tps"] is None and aborted["ttft_s"] is None, "a number survived"
    assert (skipped["status"], skipped["reason"]) == ("SKIPPED", quickbench.CANCELLED)
    assert summary["ended"] == "cancelled"
    assert summary["best"] is None
    assert summary["stage_a"]["winner"] is None
    assert summary["stage_b"]["note"] == "stage B was not run: the run was cancelled"
    assert [event["type"] for event in fakes.events[-2:]] == ["error", "done"]
    assert fakes.events[-2]["payload"]["code"] == "cancelled"
    assert fakes.events[-1]["message"] == "quickbench cancelled"


def test_an_abort_during_a_stage_b_cell_evicts_the_sibling_and_stops_there(tmp_path):
    probe = AbortProbe()

    def on_call(_cell, _kwargs):
        # Stage A measures two cells; the third call is stage B's first sibling.
        if len(calls.calls) == 3:
            probe.triggered = True

    calls = FakeRunCells(on_call=on_call)

    ok, fakes, summary = a_run(tmp_path, run_cells=calls, abort=probe)

    assert ok is False
    assert len(fakes.run_cells.calls) == 3, "a sibling after the stop was measured"
    assert fakes.cache.downloads == [SIBLING.repo]
    assert fakes.cache.evicts == [SIBLING.repo], "what this run fetched is taken back out"
    assert [
        (cell["format"], cell["status"], cell["reason"])
        for cell in summary["stage_b"]["cells"][1:]
    ] == [
        (SIBLING.format, quickbench.ABORTED, quickbench.ABORTED_REASON),
        (SIBLING_2.format, "SKIPPED", quickbench.CANCELLED),
    ]
    assert summary["ended"] == "cancelled"
    assert summary["best"] is None
    assert fakes.events[-2]["payload"]["code"] == "cancelled"


def test_an_aborted_osaurus_cell_still_restores_the_host_settings(tmp_path):
    probe = AbortProbe()
    calls = FakeRunCells(
        on_call=lambda cell, _kwargs: setattr(
            probe, "triggered", cell.runtime == "osaurus"
        )
    )

    ok, fakes, summary = a_run(
        tmp_path, engines_list=WITH_OSAURUS, osaurus=True, run_cells=calls, abort=probe
    )

    assert ok is False
    osaurus_cell = next(
        cell for cell in summary["stage_a"]["cells"] if cell["engine"] == "osaurus"
    )
    assert osaurus_cell["status"] == quickbench.ABORTED
    assert [kind for kind, _kwargs in fakes.osaurus.calls] == ["recover", "pin", "restore"]
    assert summary["osaurus"]["restored"] is True
    assert summary["ended"] == "cancelled"


def test_an_abort_after_the_last_cells_engine_stopped_leaves_the_ending_finished(tmp_path):
    """The probe is asked once per measured cell and never after the last one, so a "Stop
    now" that arrives once every engine has stopped is never consulted: the run finishes,
    and `stop_own_engines` finds an empty ledger (its own test)."""
    probe = AbortProbe()

    ok, fakes, summary = a_run(tmp_path, abort=probe)

    assert ok is True
    assert summary["ended"] == "finished"
    assert probe.checks == len(fakes.run_cells.calls) == 4, "a check after the last cell"
    assert not [
        cell
        for stage in ("stage_a", "stage_b")
        for cell in summary[stage]["cells"]
        if cell["status"] == quickbench.ABORTED
    ]


def test_a_stop_that_makes_the_cells_own_stop_raise_is_still_an_aborted_cell(tmp_path):
    """AC-7: the engine is already gone when the cell's own `handle.stop()` runs, so the
    measurement raises. That is the abort, not the run's unexpected error."""
    probe = AbortProbe()

    def run_cells(cells, workloads, **kwargs):
        probe.triggered = True
        raise runtimes.RuntimeStopError("spawned process 4242 is still alive after SIGKILL")

    ok, fakes, summary = a_run(tmp_path, run_cells=run_cells, abort=probe)

    assert ok is False
    assert summary["ended"] == "cancelled", "a stop race became the run's error"
    assert summary["stage_a"]["cells"][0]["status"] == quickbench.ABORTED
    assert summary["stage_a"]["cells"][0]["reason"] == quickbench.ABORTED_REASON
    codes = [event["payload"]["code"] for event in fakes.events if event["type"] == "error"]
    assert codes == ["cancelled"], "the raise was reported as an error on the stream"
    assert fakes.events[-1]["type"] == "done"


def test_an_aborted_cell_is_never_the_winner_even_with_a_number(tmp_path):
    aborted = quickbench._cell_record(
        "mlxlm", "stock4bit", "/a", status=quickbench.ABORTED, reason=quickbench.ABORTED_REASON
    )
    aborted["decode_tps"] = 99.0  # a number the status must still exclude
    failed = quickbench._cell_record("optiq", "stock4bit", "/b", status="FAIL", reason="x")

    assert quickbench._winner([aborted, failed]) == (None, [])


def test_the_default_abort_probe_never_fires(tmp_path):
    default = inspect.signature(quickbench.run).parameters["abort"].default

    assert default is quickbench._never_cancelled
    ok, fakes, summary = a_run(tmp_path)

    assert ok is True and summary["ended"] == "finished"
