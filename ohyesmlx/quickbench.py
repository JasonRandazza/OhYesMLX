"""`ohyesmlx quickbench`: two single-axis stages on this Mac, and a best-for-you summary.

Seam S8 and T4.4. Stage A holds the chosen model's format constant and varies the serving
engine: one light cell per installed engine that lists the row. Stage B holds the winner
fixed and varies the format: the chosen row plus its catalog siblings, whose one download at
a time is fetched and evicted around its own cell. Every number is labelled "quick: measured
on this Mac" and lives under Application Support, so a quick run can never join the published
tables -- `report._check_not_quick` refuses its header by value.

Four rules shape the run, and each is one the harness already paid for:

- **A fast cell that emits garbage is a failed cell.** The coherence gate is the harness's,
  untouched: a cell that does not PASS wins nothing and is never compared.
- **One variable at a time.** Each stage writes its own caveat into the summary: stage A
  cannot claim anything about formats, and stage B cannot claim anything about engines.
- **Nothing the user owns is changed without consent.** An engine whose port is already in
  use, and Osaurus while its app runs, are skipped with a reason rather than swept aside;
  Osaurus's host settings are pinned only with ``osaurus=True``, only after ``recover``, and
  put back in a ``finally``.
- **The user's chosen model stays.** Only a sibling this run downloaded is ever evicted.

``--cells`` stays the only cell selector: :func:`cell_spec` writes one cell as a ``--cells``
string and ``cli.build_cells`` turns it into the selection, exactly as ``canary`` does. Each
cell is its own ``run_cells`` call, which is what makes a cancel between cells possible.

Every side effect is an injected parameter: the run loop, the downloader and evictor, the
downloaded check, Osaurus pin/restore/recover, the mid-run drift check and the copy it keeps,
the port probe, the Osaurus-app probe, the load average, the clock, the emitter and the
cancel probe. Tests run on scratch directories with fakes, so none starts a runtime,
downloads a model, reads this Mac's Application Support, or touches ``~/.osaurus``.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from ohyesmlx import (
    __version__,
    app_support_dir,
    canary,
    catalog,
    cli,
    engines,
    fetch,
    measure,
    osaurus_settings,
    report,
    runtimes,
)
from ohyesmlx.hardware import scan as _scan_hardware

# D9's light cell, defined once and used by both stages. A quick cell is the same request
# shape and the same coherence gate as a published one, with a fixed small warmup, five
# measured batches and a ten-second cooldown so 4-6 cells fit the app's ~10 minutes.
WARMUP = 3
MEASURED = 5
COOLDOWN_S = 10.0

# Decision 131's ~5% session bar, asked of `canary` rather than restated: two cells inside it
# are one reading on this host, so stage A reports them as a tie instead of ranking noise.
TIE = canary.NOISE_FLOOR

# The plan's estimate, and the two constants it is made of: one cell costs about a minute and
# a half on this class of Mac, and a download is assumed at 20 MB/s. An estimate is never a
# measurement, and the summary records it beside the actual seconds.
ESTIMATE_PER_CELL_S = 90
DOWNLOAD_BYTES_PER_S = 20_000_000

# How every number this module produces is labelled (D5), and the two caveats D3 attaches to
# the stages. Written once: the summary and the CLI read them from here.
LABEL = "quick: measured on this Mac"
CAVEAT_A = "engines compared on one format only"
CAVEAT_B = "formats compared on one engine only"
BUSY = "this Mac was busy"
CANCELLED = "the run was cancelled before this cell"

# The one place a quick run's files live. Asked of the package rather than restated, the way
# `fetch` asks it, so the app's Application Support directory has one spelling.
DEFAULT_RESULTS_DIR = str(app_support_dir(engines.DEFAULT_ENV.home) / "quickbench")

# Osaurus's backup is a fixed path rather than a per-run one: a crash between a pin and its
# restore leaves the only copy of the user's settings behind, and `recover` can only find it if
# the next run looks in the same directory. The baseline is not: it is the one
# `runtimes.Osaurus.check_host_state` reads, `osaurus_settings.BASELINE_PATH` by default.
DEFAULT_BACKUP_DIR = os.path.join(DEFAULT_RESULTS_DIR, "osaurus-backup")

# The one name a quick run's record is written under, in every stamp directory.
SUMMARY_NAME = "summary.json"

# The one workload each stage measures. `decode` is the shape both axes were always read on:
# sustained generation after a short prompt, at the pinned 512-token cap.
WORKLOAD_ID = "decode"


@dataclass(frozen=True)
class PlannedEngine:
    """One stage-A cell's engine, with the build it is and whether the harness tested it."""

    engine: str
    version: str | None
    tested: bool


@dataclass(frozen=True)
class PlannedSibling:
    """One stage-B sibling format: its row, its bytes, and whether it is already cached."""

    repo: str
    format: str
    size_bytes: int
    downloaded: bool


@dataclass(frozen=True)
class QuickPlan:
    """What a confirmed run would do, shown before anything starts (AC-1).

    ``osaurus`` is true when Osaurus is one of stage A's engines: the run pins and restores
    its host settings for that cell only if it is also confirmed with ``osaurus=True``,
    which is the run's own consent field and not something a plan can grant.
    """

    repo: str
    format: str
    stage_a: list[PlannedEngine]
    stage_b: list[PlannedSibling]
    download_bytes: int
    osaurus: bool
    estimate_s: int


def _print_event(event: dict) -> None:
    print(json.dumps(event), flush=True)


def _discard(event: dict) -> None:
    """The sibling fetch's and evict's own events: their outcome is quickbench's to report.

    Their default emitter prints to stdout, which under ``ohyesmlx app`` is the pipe the app
    reads its launch line from; quickbench reports the download and the eviction in its own
    events instead.
    """


def _never_cancelled() -> bool:
    return False


def estimate_seconds(cells: int, download_bytes: int) -> int:
    """The plan's estimate in seconds: per-cell cost plus the download at 20 MB/s.

    One definition of the estimate, so the plan and the summary's estimate-vs-actual pair
    are the same number rather than two close ones.
    """
    return round(cells * ESTIMATE_PER_CELL_S + download_bytes / DOWNLOAD_BYTES_PER_S)


def _port_busy(port: int) -> bool:
    """Whether something is listening on *port*, asked of `runtimes` rather than re-probed.

    A probe, never a stop: an engine whose port answers may be the user's own server, and
    quickbench skips it rather than ending a process it did not start. A port that cannot be
    verified is reported busy, so "unknown" skips the engine instead of starting over it.
    """
    return not runtimes._port_is_free(port)


def _osaurus_app_running(run=subprocess.run) -> bool:
    """Whether the Osaurus app has a process at its own executable path.

    Matched by full executable path and never by the name ``osaurus``: ``osaurus mcp`` is a
    user's long-running client that shares the name, and the app outlives its server, so a
    name match is both too broad and the wrong question. A probe that cannot run is read as
    the app being present, because the alternative -- starting Osaurus's cell anyway -- is
    what ends the user's own app (AGENTS.md).
    """
    try:
        completed = run(
            [runtimes.PS, "-axo", "comm="],
            capture_output=True,
            text=True,
            timeout=10,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return True
    for line in (completed.stdout or "").splitlines():
        command = line.strip()
        if any(
            command == binary or command.startswith(binary + " ")
            for binary in runtimes.OSAURUS_APP_EXECUTABLES
        ):
            return True
    return False


def _osaurus_drift(*, baseline_path, config_dir=None) -> str | None:
    """The host's drift from the run's baseline since the pin, or None when it has not moved.

    Read after a cell, from the same config directory ``pin`` edited, and compared with the
    baseline that pin wrote: a host that moved mid-run was measuring a configuration the pin
    did not reach. A run with no baseline has nothing to compare against and reports no drift;
    the baseline's absence is `pin`'s business, not this check's.
    """
    baseline = osaurus_settings.load_baseline(pathlib.Path(baseline_path))
    if baseline is None:
        return None
    drift = osaurus_settings.diff_against_baseline(
        osaurus_settings.capture_osaurus_settings(
            pathlib.Path(config_dir) if config_dir is not None else None
        ),
        baseline,
    )
    return osaurus_settings.describe_drift(drift) if drift else None


def _keep_during_run(*, during_run_dir, config_dir=None) -> None:
    """Copy the two host files ``pin`` edits into *during_run_dir*, byte-exact.

    The copy is how a change the user made mid-run survives ``restore``: a verified restore
    puts the pinned originals back, so without it the only bytes left would be the ones the
    user replaced. The directory is created ``0700``, like the backup itself.
    """
    destination = pathlib.Path(during_run_dir)
    destination.mkdir(parents=True, exist_ok=True)
    os.chmod(destination, osaurus_settings.BACKUP_DIR_MODE)
    source = (
        pathlib.Path(config_dir)
        if config_dir is not None
        else osaurus_settings.DEFAULT_CONFIG_DIR
    )
    for name in osaurus_settings.PIN_FILES:
        (destination / name).write_bytes((source / name).read_bytes())


def _catalog_row(repo: str, models) -> catalog.Model:
    """The catalog row named *repo*, or ``ValueError`` naming the repo."""
    for model in models:
        if model.repo == repo:
            return model
    raise ValueError(f"{repo} is not a catalog model; nothing was measured")


def plan(
    repo,
    hw,
    statuses,
    models,
    *,
    cache_dir=None,
    downloaded=fetch.downloaded,
) -> QuickPlan:
    """What a confirmed run of *repo* would do, and nothing else (AC-1).

    Pure apart from the injected download check: no directory is created, nothing is
    fetched and no runtime is started. Stage A is the installed engines that list the row,
    in the order detection reported them, each with its version and whether the manifest
    tested it -- an untested build is included and labelled rather than quietly dropped.
    Stage B is the row's catalog siblings, with every missing download's bytes named, and
    the estimate is :func:`estimate_seconds` over the cells and those bytes.

    The chosen repo must already be in the cache. Quickbench never fetches or evicts the
    user's own choice, so a repo that is not there is refused with "download it first"
    rather than downloaded into a measurement nobody asked for.

    *hw* is part of the pinned signature -- the app has the scan already -- and the plan
    does not vary with it: the estimate is a constant per cell plus bytes over an assumed
    rate, and the engines are the row's own list. *downloaded* is the filesystem question
    and is injected so a test never reads this Mac's Hugging Face cache.
    """
    model = _catalog_row(repo, models)
    if not downloaded(model, cache_dir):
        raise ValueError(
            f"{repo} is not in this Mac's Hugging Face cache; download it first -- "
            "quickbench never fetches or evicts the model you chose"
        )

    stage_a = [
        PlannedEngine(engine=status.name, version=status.version, tested=status.tested)
        for status in statuses
        if status.installed and status.name in model.engines
    ]
    stage_b = [
        PlannedSibling(
            repo=sibling.repo,
            format=sibling.format,
            size_bytes=sibling.size_bytes,
            downloaded=downloaded(sibling, cache_dir),
        )
        for sibling in catalog.siblings(model, models)
    ]
    missing_bytes = sum(
        sibling.size_bytes for sibling in stage_b if not sibling.downloaded
    )
    return QuickPlan(
        repo=model.repo,
        format=model.format,
        stage_a=stage_a,
        stage_b=stage_b,
        download_bytes=missing_bytes,
        osaurus=any(engine.engine == "osaurus" for engine in stage_a),
        estimate_s=estimate_seconds(len(stage_a) + len(stage_b), missing_bytes),
    )


def cell_spec(fmt: str, engine: str, artifact_dir: str) -> str:
    """One cell as the ``--cells`` string ``cli.build_cells`` already parses."""
    return f"{fmt}__{engine}={artifact_dir}"


def _cell_record(
    engine,
    fmt,
    artifact_dir,
    *,
    row=None,
    status=None,
    reason=None,
    reused=False,
) -> dict:
    """One cell's line in the summary: its status, its numbers, and the quick label.

    A measured cell takes ``row`` from ``report.summarize`` -- the one definition of a
    published figure -- and a skipped or failed one carries its own status and reason with
    no number at all. A skipped cell reporting zero would be a measurement it did not make.
    """
    return {
        "engine": engine,
        "format": fmt,
        "artifact_dir": artifact_dir,
        "status": (row or {}).get("status", status),
        "reason": (row or {}).get("reason", reason),
        "decode_tps": (row or {}).get("decode_tps"),
        "ttft_s": (row or {}).get("ttft_p50_s"),
        "runtime_version": (row or {}).get("runtime_version"),
        "label": LABEL,
        "reused": reused,
    }


def _skipped(engine, fmt, artifact_dir, reason) -> dict:
    return _cell_record(engine, fmt, artifact_dir, status="SKIPPED", reason=reason)


def _winner(cells) -> tuple[dict | None, list[str]]:
    """Stage A's winner and the engines inside the tie band.

    The winner is the PASS cell with the highest decode rate; a cell inside ``TIE`` of it is
    reported as a tie rather than ranked, because two cells that close are one reading on
    this host (Decision 131). An exact tie keeps the first in stage order, so the same run is
    the same run twice.
    """
    passed = [
        cell
        for cell in cells
        if cell["status"] == "PASS" and cell["decode_tps"] is not None
    ]
    if not passed:
        return None, []
    top = max(passed, key=lambda cell: cell["decode_tps"])
    tied = [
        cell["engine"]
        for cell in passed
        if top["decode_tps"] - cell["decode_tps"] <= top["decode_tps"] * TIE
    ]
    return top, tied


def _best(summary, measured_at) -> dict | None:
    """The best-for-you cell: AC-5's five fields, or None when nothing passed.

    Stage B is the comparison the summary exists for, so its cells decide when it ran; a run
    that stopped at stage A offers A's winner. Only a PASS cell with a decode rate is
    eligible, which is what keeps a failed cell out of `Pick.measured_here`.
    """
    cells = (
        summary["stage_b"]["cells"]
        if summary["stage_b"]["engine"]
        else summary["stage_a"]["cells"]
    )
    passed = [
        cell
        for cell in cells
        if cell["status"] == "PASS" and cell["decode_tps"] is not None
    ]
    if not passed:
        return None
    top = max(passed, key=lambda cell: cell["decode_tps"])
    return {
        "engine": top["engine"],
        "decode_tps": top["decode_tps"],
        "ttft_s": top["ttft_s"],
        "measured_at": measured_at,
        "quick": True,
    }


def _skip_reason(name, osaurus, osaurus_app_running, port_in_use) -> str | None:
    """Why an engine cannot be driven into its cell here, or None when it can.

    Nothing on a skipped engine's port is stopped: the process there may be the user's own
    server, and the harness's stop path would end it. Osaurus is checked for its app before
    its port, because the app outlives the server and the harness's stale-instance sweep
    would end it.
    """
    if name == "osaurus":
        if not osaurus:
            return "Osaurus was not allowed for this run (osaurus: false)"
        if osaurus_app_running():
            return "quit the Osaurus app first"
    port = runtimes.RUNTIMES[name].port
    if port_in_use(port):
        return f"quit {name} first"
    return None


def _stamp(when: float) -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(when))


def _write_summary(path: pathlib.Path, summary: dict) -> None:
    """Write the summary atomically: a reader never sees half a record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(summary, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _emitter(emit):
    """The pinned job-event shape, with this run's own seq: `engines`' one builder."""
    state = {"seq": 0}

    def send(kind, message, *, fraction=None, payload=None):
        state["seq"] += 1
        event = engines._job_event(state["seq"], kind, message, fraction, payload)
        emit(event)
        return event

    return send


def _refuse(send, code: str, message: str) -> bool:
    send("error", message, payload={"code": code})
    send("done", "quickbench did not start")
    return False


def run(
    repo: str,
    *,
    confirmed: bool,
    osaurus: bool = False,
    models=None,
    statuses=None,
    hw=None,
    run_cells=measure.run_cells,
    download=fetch.download,
    evict=fetch.evict,
    downloaded=fetch.downloaded,
    pin=osaurus_settings.pin,
    restore=osaurus_settings.restore,
    recover=osaurus_settings.recover,
    osaurus_drift=_osaurus_drift,
    keep_during_run=_keep_during_run,
    port_in_use=_port_busy,
    osaurus_app_running=_osaurus_app_running,
    load=canary.load,
    clock=time.time,
    emit=_print_event,
    cancel=_never_cancelled,
    cache_dir=None,
    results_dir=DEFAULT_RESULTS_DIR,
    backup_dir=DEFAULT_BACKUP_DIR,
    baseline_path=osaurus_settings.BASELINE_PATH,
) -> bool:
    """Measure stage A, then stage B, and write the summary; True when it finished.

    The order is the plan's: consent, the catalog row, the plan (which refuses a repo that is
    not cached), then the cells. Each cell is one ``run_cells`` call against a ``--cells``
    string this module composed, so a cancel is observed between cells and the harness's own
    stop path still runs for the cell in flight.

    An engine whose port answers, and Osaurus while its app runs, are skipped with a reason
    before anything of theirs is started. Osaurus runs only when the caller confirmed the run
    with ``osaurus=True``; then ``recover`` runs before its ``pin``, all three are handed the
    application's backup path and the same baseline path -- the drift guard's,
    ``osaurus_settings.BASELINE_PATH`` by default -- and ``restore`` runs in a ``finally`` so a
    cell that raises still puts the user's settings back. After a pinned cell and before its
    ``restore``, ``osaurus_drift`` compares the host with that baseline: drift fails the cell,
    after both host files are kept byte-exact in ``<backup_dir>/during-run`` so a change the
    user made mid-run survives the restore. A restore that does not verify,
    whether it returns False or raises, ends the run with an ``error`` naming the backup
    directory and a summary that records it; every ending that wrote a summary carries its
    ``results_dir`` in a terminal event's payload.

    A sibling is downloaded only when it is missing, measured in its own cell, and evicted
    immediately after it, so one extra model at most is on disk. The chosen repo is never
    downloaded and never evicted. Every ending -- finished, cancelled, restore failed, or an
    unexpected raise -- leaves a summary on disk saying which one it was.
    """
    send = _emitter(emit)
    if not confirmed:
        return _refuse(
            send, "consent_required", "consent was not given; nothing was measured"
        )

    models = catalog.load() if models is None else models
    statuses = engines.detect_all() if statuses is None else statuses
    hw = _scan_hardware() if hw is None else hw
    try:
        model = _catalog_row(repo, models)
    except ValueError as error:
        return _refuse(send, "unknown_repo", str(error))
    try:
        shown = plan(
            repo, hw, statuses, models, cache_dir=cache_dir, downloaded=downloaded
        )
    except ValueError as error:
        return _refuse(send, "not_downloaded", str(error))

    started = clock()
    started_iso = datetime.fromtimestamp(started, timezone.utc).isoformat()
    root = pathlib.Path(results_dir) / _stamp(started)
    snapshot = fetch.plan(model, cache_dir).snapshot_dir
    siblings = {sibling.repo: sibling for sibling in catalog.siblings(model, models)}
    decode = [shape for shape in cli.workloads(measure) if shape.id == WORKLOAD_ID]

    summary = {
        "label": LABEL,
        "repo": repo,
        "format": model.format,
        "plan": asdict(shown),
        "estimate_s": shown.estimate_s,
        "actual_s": None,
        "ended": "running",
        "results_dir": str(root),
        # The harness revision every run header carries, asked of the module that writes it
        # rather than hashed a second time here.
        "harness": {
            "version": __version__,
            "source_sha256": measure._source_sha256(),
        },
        "engines": [
            {"name": engine.engine, "version": engine.version, "tested": engine.tested}
            for engine in shown.stage_a
        ],
        "load": {"stage_a": None, "stage_b": None},
        "osaurus": {"allowed": osaurus, "pinned": False, "restored": None, "reason": None},
        "stage_a": {
            "caveat": CAVEAT_A,
            "cells": [],
            "winner": None,
            "tie": [],
            "note": None,
        },
        "stage_b": {"caveat": CAVEAT_B, "engine": None, "cells": [], "note": None},
        "best": None,
    }

    planned = len(shown.stage_a) + len(shown.stage_b)
    done = 0
    outstanding: set[str] = set()
    restore_failure: list[str] = []

    def step(message, payload=None):
        nonlocal done
        done += 1
        send(
            "progress",
            message,
            fraction=(done / planned if planned else 1.0),
            payload=payload,
        )

    def record_load(stage, before, after):
        noisy = max(before, after) > canary.LOAD_NOISY
        summary["load"][stage] = {
            "before": before,
            "after": after,
            "label": BUSY if noisy else None,
        }
        if noisy:
            send(
                "log",
                f"{stage}: {BUSY} (1-minute load {before:.1f} -> {after:.1f}); the numbers "
                "are recorded, not retried",
                payload={"label": BUSY},
            )

    def measure_cell(engine, fmt, artifact_dir, cell_dir):
        """One cell's own `run_cells` call, with Osaurus pinned and restored around it."""
        attempted = False
        pinned = False
        try:
            if engine == "osaurus":
                # AC-3: recover first, because a backup a crash left behind is the only copy
                # of the user's settings and `pin` refuses over one. A recover or pin that
                # does not take effect blocks this engine for the run with its own reason --
                # the cell is skipped, never measured under a settings state it did not
                # reach.
                attempted = True
                blocked = None
                try:
                    recover(backup_dir=backup_dir, baseline_path=baseline_path)
                    pin(backup_dir=backup_dir, baseline_path=baseline_path)
                except Exception as error:
                    blocked = str(error)
                else:
                    pinned = True
                    summary["osaurus"]["pinned"] = True
                if blocked is not None:
                    return _skipped(engine, fmt, artifact_dir, blocked)
            results = run_cells(
                cli.build_cells(measure.Cell, cell_spec(fmt, engine, artifact_dir)),
                decode,
                warmup=WARMUP,
                measured=MEASURED,
                cooldown_s=COOLDOWN_S,
                quick=True,
                results_dir=str(cell_dir),
            )
            if pinned:
                # AC-7: the host is attested once more after the cell and before the originals
                # go back. Drift means the numbers were measured against settings the pin did
                # not reach, so the cell fails -- but the user's current files are kept first,
                # because a verified restore would otherwise replace the only copy of a change
                # they made mid-run.
                try:
                    drift = osaurus_drift(baseline_path=baseline_path)
                    if drift is not None:
                        during_run = pathlib.Path(backup_dir) / "during-run"
                        keep_during_run(during_run_dir=during_run)
                        summary["osaurus"]["during_run"] = str(during_run)
                except Exception as error:
                    return _cell_record(
                        engine, fmt, artifact_dir, status="FAIL", reason=str(error)
                    )
                if drift is not None:
                    return _cell_record(
                        engine,
                        fmt,
                        artifact_dir,
                        status="FAIL",
                        reason="Osaurus changed its settings during the run: " + drift,
                    )
        except Exception as error:
            return _cell_record(
                engine, fmt, artifact_dir, status="FAIL", reason=str(error)
            )
        finally:
            if attempted:
                raised = None
                try:
                    restored = restore(backup_dir=backup_dir, baseline_path=baseline_path)
                except Exception as error:
                    # A restore that raises is a restore that did not verify: handled exactly
                    # as one that returned False, so a raise after a pin that took effect
                    # cannot leave the run measuring on the user's pinned settings.
                    restored = False if pinned else None
                    raised = str(error)
                if restored is True:
                    summary["osaurus"]["restored"] = True
                elif restored is False:
                    summary["osaurus"]["restored"] = False
                    message = (
                        "Osaurus's settings were not restored byte-exact; the user's "
                        f"originals are still at {backup_dir}"
                        + (f" (restore raised: {raised})" if raised else "")
                    )
                    summary["osaurus"]["reason"] = message
                    if pinned:
                        # A pin that did take effect and a restore that did not is a run
                        # that must stop; the error names the backup directory the user's
                        # settings are still in.
                        restore_failure.append(message)
                        send(
                            "error",
                            message,
                            payload={
                                "code": "restore_failed",
                                "backup_dir": str(backup_dir),
                            },
                        )
        rows = report.summarize(results)
        if not rows:
            return _cell_record(
                engine,
                fmt,
                artifact_dir,
                status="FAIL",
                reason="the harness returned no result for this cell",
            )
        return _cell_record(engine, fmt, artifact_dir, row=rows[0])

    try:
        send(
            "progress",
            f"stage A: {len(shown.stage_a)} installed engine(s), one format ({CAVEAT_A})",
            fraction=0.0,
            payload={"stage": "A"},
        )
        load_a = load()
        for engine_plan in shown.stage_a:
            if cancel():
                summary["ended"] = "cancelled"
                break
            name = engine_plan.engine
            reason = _skip_reason(name, osaurus, osaurus_app_running, port_in_use)
            if reason is not None:
                summary["stage_a"]["cells"].append(
                    _skipped(name, model.format, snapshot, reason)
                )
                step(
                    f"stage A: {name} skipped: {reason}",
                    {"engine": name, "skipped": reason},
                )
                continue
            record = measure_cell(
                name, model.format, snapshot, root / "A" / name
            )
            summary["stage_a"]["cells"].append(record)
            step(
                f"stage A: {name} {record['status']}"
                + (f": {record['reason']}" if record["reason"] else ""),
                {"engine": name, "status": record["status"]},
            )
            if restore_failure:
                summary["ended"] = "restore_failed"
                break
        record_load("stage_a", load_a, load())

        if summary["ended"] == "running":
            top, tied = _winner(summary["stage_a"]["cells"])
            if top is None:
                summary["stage_a"]["note"] = (
                    f"no installed engine lists {repo}"
                    if not shown.stage_a
                    else "no stage-A cell passed, so there is no winning engine to hold "
                    "constant for stage B"
                )
                summary["stage_b"]["note"] = (
                    "stage B was not run: " + summary["stage_a"]["note"]
                )
                send(
                    "progress",
                    "stage A: no PASS cell, so stage B is not run",
                    payload={"stage": "B"},
                )
            else:
                summary["stage_a"]["winner"] = top["engine"]
                summary["stage_a"]["tie"] = tied if len(tied) > 1 else []
                summary["stage_b"]["engine"] = top["engine"]
                # The chosen row's stage-A row is the comparison's baseline: reusing it
                # rather than measuring it again keeps one run's numbers for one cell.
                summary["stage_b"]["cells"].append(dict(top, reused=True))
                send(
                    "progress",
                    f"stage B: {top['engine']} over {len(shown.stage_b)} sibling format(s) "
                    f"({CAVEAT_B})",
                    payload={"stage": "B", "engine": top["engine"]},
                )
                load_b = load()
                for sibling_plan in shown.stage_b:
                    if cancel():
                        summary["ended"] = "cancelled"
                        break
                    sibling = siblings[sibling_plan.repo]
                    sibling_snapshot = fetch.plan(sibling, cache_dir).snapshot_dir
                    cell_id = f"{sibling.format}__{top['engine']}"
                    fetched = False
                    if not sibling_plan.downloaded:
                        send(
                            "progress",
                            f"stage B: downloading {sibling.repo} "
                            f"({sibling_plan.size_bytes} bytes)",
                            payload={
                                "repo": sibling.repo,
                                "bytes": sibling_plan.size_bytes,
                            },
                        )
                        reason = f"{sibling.repo} could not be downloaded"
                        try:
                            fetched = download(
                                sibling.repo, True, cache_dir=cache_dir, emit=_discard
                            ) is True
                        except Exception as error:
                            reason = f"{reason}: {error}"
                        if not fetched:
                            summary["stage_b"]["cells"].append(
                                _skipped(
                                    top["engine"],
                                    sibling.format,
                                    sibling_snapshot,
                                    reason,
                                )
                            )
                            step(
                                f"stage B: {sibling.format} skipped: {reason}",
                                {"engine": top["engine"], "skipped": reason},
                            )
                            continue
                        outstanding.add(sibling.repo)
                        if cancel():
                            summary["ended"] = "cancelled"
                            break
                    try:
                        record = measure_cell(
                            top["engine"],
                            sibling.format,
                            sibling_snapshot,
                            root / "B" / cell_id,
                        )
                        summary["stage_b"]["cells"].append(record)
                        step(
                            f"stage B: {sibling.format} {record['status']}"
                            + (f": {record['reason']}" if record["reason"] else ""),
                            {"engine": top["engine"], "status": record["status"]},
                        )
                    finally:
                        if fetched:
                            try:
                                evict(sibling.repo, True, cache_dir=cache_dir, emit=_discard)
                            finally:
                                outstanding.discard(sibling.repo)
                    if restore_failure:
                        summary["ended"] = "restore_failed"
                        break
                record_load("stage_b", load_b, load())
        if summary["ended"] == "running":
            summary["ended"] = "finished"
    except BaseException:
        summary["ended"] = "error"
        raise
    finally:
        for leftover in sorted(outstanding):
            try:
                evict(leftover, True, cache_dir=cache_dir, emit=_discard)
            except Exception as error:
                send(
                    "log",
                    f"could not evict {leftover}: {error}",
                    payload={"repo": leftover},
                )
        summary["actual_s"] = round(clock() - started, 3)
        if summary["ended"] == "cancelled":
            # Every planned cell has a status: one the run never reached is skipped with the
            # reason, so a cancelled record covers its plan rather than only its samples.
            reached = {cell["engine"] for cell in summary["stage_a"]["cells"]}
            for engine_plan in shown.stage_a:
                if engine_plan.engine not in reached:
                    summary["stage_a"]["cells"].append(
                        _skipped(engine_plan.engine, model.format, snapshot, CANCELLED)
                    )
            if summary["stage_b"]["engine"] is not None:
                covered = {cell["format"] for cell in summary["stage_b"]["cells"]}
                for sibling_plan in shown.stage_b:
                    if sibling_plan.format not in covered:
                        summary["stage_b"]["cells"].append(
                            _skipped(
                                summary["stage_b"]["engine"],
                                sibling_plan.format,
                                fetch.plan(
                                    siblings[sibling_plan.repo], cache_dir
                                ).snapshot_dir,
                                CANCELLED,
                            )
                        )
        if summary["stage_b"]["engine"] is None and summary["stage_b"]["note"] is None:
            # A run that stopped before stage B says so in the record, with the reason it
            # stopped rather than with the absence of one.
            summary["stage_b"]["note"] = {
                "cancelled": "stage B was not run: the run was cancelled",
                "restore_failed": "stage B was not run: the run stopped after a failed "
                "Osaurus restore",
            }.get(
                summary["ended"],
                f"stage B was not run: the run ended as {summary['ended']}",
            )
        # Only a finished run carries a best: a cancelled or half-restored run is a record
        # of what happened, not a recommendation (AC-5).
        summary["best"] = (
            _best(summary, started_iso) if summary["ended"] == "finished" else None
        )
        _write_summary(root / SUMMARY_NAME, summary)

    if summary["ended"] == "cancelled":
        send(
            "error",
            "quickbench was cancelled; nothing further was measured",
            payload={"code": "cancelled", "results_dir": str(root)},
        )
        send("done", "quickbench cancelled", payload={"results_dir": str(root)})
        return False
    if summary["ended"] == "restore_failed":
        send(
            "done",
            "quickbench stopped after a failed Osaurus restore",
            payload={"results_dir": str(root)},
        )
        return False
    send("result", "quickbench finished", payload=summary)
    send("done", "quickbench finished")
    return True


def latest(root=DEFAULT_RESULTS_DIR) -> dict[str, dict]:
    """The newest finished summary per repo under *root*, keyed by repo id.

    This is what ``GET /recommendations`` fills ``Pick.measured_here`` from, and only a
    summary whose own record says it finished is read: a cancelled run is a record of what
    happened, never a recommendation (AC-5). A missing directory is no summaries, and a
    file that cannot be read is skipped rather than failing the recommendations screen --
    it is not a number, so nothing here is being silently approximated.
    """
    found: dict[str, tuple[float, dict]] = {}
    root_path = pathlib.Path(root)
    if not root_path.is_dir():
        return {}
    for path in root_path.glob(f"*/{SUMMARY_NAME}"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict) or payload.get("ended") != "finished":
            continue
        repo = payload.get("repo")
        if not isinstance(repo, str) or not repo:
            continue
        try:
            modified = path.stat().st_mtime
        except OSError:
            continue
        if repo not in found or modified > found[repo][0]:
            found[repo] = (modified, payload)
    return {repo: payload for repo, (_modified, payload) in found.items()}
