# v5 quickbench pins — interface shapes

Plan 04-03a's catalog base, quick pin and Osaurus pin, and plan 04-03b's quickbench and the lab path an install writes.

## v5.0 plan 04-03a — the catalog `base`, the `quick` pin, and one Osaurus pin

The three foundations quickbench (04-03b) stands on, each with one definition.

**`Model.base` and `catalog.siblings`.** Every catalog row carries `base`, the name of the base
model it was quantized from — `"Qwen3.5-0.8B"` on both the stock 4-bit and the OptiQ row,
`"Qwen3.5-2B"` on both the stock 4-bit and the oQ4 row (the only two bases with two rows today).
`scripts/build_catalog.py` writes it from its own seed table, so a rebuild cannot drop it.
`catalog.siblings(model, models)` returns the other rows with the same `base` in catalog order;
a missing or non-string `base` is a `ValueError` naming the file, the repo and the field, like
every other row check.

**The `quick` header pin.** `run_cells(..., quick=False)` records `quick` (a bool) in the run
header; `False` is the default and is what a header written before the pin existed is read as.
`quick` joins `report.PIN_FIELDS`, but the joined tables never compare it: `_check_not_quick`
refuses any grid or sweep naming a run directory whose header pins `quick: true`, by value and
before guard 1, so a quick-vs-quick pair is refused as surely as a quick run beside a full one.
The refusal names the directory and says quickbench results never join the published tables.
`ABSENT_PINS["quick"]` is `False`, so every pre-04-03a run joins exactly as it did before.

**`osaurus_settings.pin` / `restore` / `recover`.** The pin moved out of shell into the module so
quickbench and `scripts/osaurus-pin.sh` share one definition of it.

```
pin(config_dir=None, *, backup_dir, baseline_path=None) -> None
restore(config_dir=None, *, backup_dir, baseline_path=None) -> bool
recover(config_dir=None, *, backup_dir, baseline_path=None) -> bool
```

`pin` copies `server-runtime.json` and `server.json` (`PIN_FILES`) and the baseline at `baseline_path`
(as `baseline.json`, or a `baseline.absent` marker when there is none; 04-03c) byte-exact into `backup_dir`,
sets `cache.prefix.enabled = false`, `cache.blockDisk.enabled = false` and
`modelIdleResidencyPolicy.seconds = 900`, and writes the baseline the drift guard reads to
`baseline_path` — `BASELINE_PATH` by default, the one the drift guard reads: `<repo>/config/` in a checkout and
`<Application Support>/config/` in an installed app (`ohyesmlx.writable_root()` is the one definition of which);
quickbench uses it too (04-03c). It refuses (`ValueError`) while a backup exists,
because overwriting it would destroy the only copy of the user's own settings; recovering first
is the caller's move. Both configs are parsed before either is replaced, so a malformed file
leaves its neighbour untouched.

`restore` puts each backed-up file back (the baseline to `baseline_path`; the marker deletes the baseline the pin wrote), returns `True` only when each is byte-identical to its
backup (`filecmp.cmp(shallow=False)`), and removes the backups on success; `False` keeps them so a
restore that did not take effect can be retried. `recover` is the same restore for a backup a
crash between pin and restore left behind, and a no-op (`False`, no error) without one — 04-03b
calls it before any new pin, and the app may call it at launch.

Every write is a temp file in the same directory followed by `os.replace`, so a kill mid-write
never leaves a half-written Osaurus config; the backup directory is created `0700`; the file's
own mode is preserved across the replace. `pin` and `restore`/`recover` each write one JSON line
to stderr, naming the files and the outcome and never their contents.
`scripts/osaurus-pin.sh` keeps its trap, its port/app sweep and its restore verdict, and calls
these functions instead of carrying its own copy of the edit; the byte-exact verdict printed as
"restored byte-exact (cmp)" is now the module's `filecmp` comparison, the one definition of it.

## v5.0 plan 04-03b — quickbench, and the lab path an install writes

**`engines.record_lab_path(engine, bin_dir, *, path=LAB_PATHS_FILE) -> None`** (AC-0). One atomic
writer for the machine-local lab-paths file, beside the one reader `lab_paths`. `install` calls it
after a pip engine's steps succeed, with that venv's `bin` directory, because the venv lives under
Application Support where no shell exports it and the start commands use bare names; without the
entry every mlx-lm and OptiQ cell on a Mac that installed through the app fails to start. The path
is written beside the `engines_dir` the call was handed (`engines._lab_paths_beside`), so a scratch
engines directory keeps its own file. Every other engine's entry is kept, and the engine's own is
replaced only by an install of the version the manifest pins. A failed step writes nothing; an
app engine is refused (`ValueError`), like the reader refuses one. *bin_dir* is refused by
`engines.check_lab_dir` before the file is read or written (045-02b, below), and the write is
`ohyesmlx.atomic_write_text`.

**`GET /quickbench/plan?repo=R`** (AC-1). The plan below, as the app shows it before the click.
`repo` is the only query parameter; a missing or repeated one is `400 bad_args`, and the module's
own refusal — a repo that is not in the catalog, or one that is not in this Mac's cache
("download it first") — is `400 bad_args` carrying its message. The endpoint never fetches.

```python
# ohyesmlx/quickbench.py
def plan(repo, hw, statuses, models, *, cache_dir=None,
         downloaded=fetch.downloaded) -> QuickPlan: ...
def run(repo, *, confirmed, osaurus=False, models=None, statuses=None, hw=None,
        run_cells=measure.run_cells, download=fetch.download, evict=fetch.evict,
        downloaded=fetch.downloaded, pin=osaurus_settings.pin,
        restore=osaurus_settings.restore, recover=osaurus_settings.recover,
        osaurus_drift=_osaurus_drift, keep_during_run=_keep_during_run,
        port_in_use=_port_busy, osaurus_app_running=_osaurus_app_running,
        load=canary.load, clock=time.time, emit=_print_event, cancel=_never_cancelled,
        cache_dir=None, results_dir=DEFAULT_RESULTS_DIR,
        backup_dir=DEFAULT_BACKUP_DIR, baseline_path=osaurus_settings.BASELINE_PATH) -> bool: ...
def latest(root=DEFAULT_RESULTS_DIR) -> dict[str, dict]: ...
def cell_spec(fmt: str, engine: str, artifact_dir: str) -> str: ...
def estimate_seconds(cells: int, download_bytes: int) -> int: ...

@dataclass(frozen=True)
class PlannedEngine:   # one stage-A cell's engine
    engine: str
    version: str | None
    tested: bool

@dataclass(frozen=True)
class PlannedSibling:  # one stage-B format
    repo: str
    format: str
    size_bytes: int
    downloaded: bool

@dataclass(frozen=True)
class QuickPlan:
    repo: str
    format: str
    stage_a: list[PlannedEngine]   # installed engines that list the row, detection order
    stage_b: list[PlannedSibling]  # catalog.siblings(row, models), catalog order
    download_bytes: int            # the sum of the missing siblings' size_bytes
    osaurus: bool                  # Osaurus is in stage A: the run pins it if allowed
    estimate_s: int
```

`plan` is pure apart from the injected `downloaded`: no directory is created, nothing is fetched,
no runtime is started. `stage_a` includes an untested build and labels it (`tested: false`); it
never invents an engine the row does not list. An empty `stage_a` is a legal plan and the run says
why it measured nothing. `estimate_s` is `cards * ESTIMATE_PER_CELL_S (90) + download_bytes /
DOWNLOAD_BYTES_PER_S (20_000_000)`, the two constants and the function being the one definition of
the estimate the summary compares with its actual seconds.

`run` returns True when the run finished, False for a refusal, a cancel or a failed Osaurus
restore. Every side effect is a parameter; the defaults are the real functions. `--cells` remains
the only selector: each cell is one `run_cells` call (one light cell, `--cells` string composed by
`cell_spec` and parsed by `cli.build_cells`), with `warmup=3`, `measured=5`, `cooldown_s=10` and
`quick=True`, under `.../quickbench/<stamp>/A/<engine>` or `.../quickbench/<stamp>/B/<format>__<engine>`.

The run's rules, each one a rule the harness already paid for:

- **One variable per stage.** Stage A varies the engine on the chosen row's format; its winner is
  the PASS cell with the highest `decode_tps`, and PASS cells inside `canary.NOISE_FLOOR` (5%) of
  it are reported as a tie. Stage B holds that engine and varies the format over the chosen row
  plus its siblings; the chosen row's stage-A row is reused, never measured twice. With no PASS
  cell stage B does not run and the summary says why. Neither stage's numbers can be read as the
  other's claim: the summary carries each stage's caveat, and every cell carries the label
  `quick: measured on this Mac`.
- **The user's choice stays.** A sibling is downloaded only when missing, measured, and evicted
  after its cell, so at most one extra model is on disk. The chosen repo is never downloaded and
  never evicted by quickbench; a sibling the ledger does not list is refused by `fetch.evict`.
- **Nothing is started on an occupied port.** An engine whose port answers is skipped with the
  reason `quit <engine> first`, and nothing on that port is stopped. Osaurus is also skipped while
  its app process runs, matched by its full executable path and never by name (`quit the Osaurus
  app first`); quickbench never runs a stale-instance sweep.
- **Osaurus is asked, pinned and restored.** It runs only with `osaurus=True`; `recover` runs
  before any `pin`, both with quickbench's fixed backup directory under Application Support, and
  `restore` runs in a `finally` around the cell. A recover that does not verify leaves the backup in
  place, so `pin` refuses and the cell is skipped with that reason. A restore that does not verify
  emits an `error` naming the backup directory and ends the run. After a pinned cell and before its
  `restore`, `osaurus_drift(baseline_path=baseline_path)` compares the host with the baseline the
  pin wrote; drift fails the cell with the reason `Osaurus changed its settings during the run: `
  + `osaurus_settings.describe_drift`, after `keep_during_run(during_run_dir=<backup_dir>/during-run)`
  copies both `PIN_FILES` byte-exact from the same config directory the check read into a `0700`
  directory named in the summary as `osaurus.during_run` -- so a change the user made mid-run
  survives the restore. A check that raises fails the cell with its message. `restore` still runs
  either way.
- **Contention is recorded, not refused.** `canary.load()` is read before and after each stage; a
  stage above `canary.LOAD_NOISY` is labelled `this Mac was busy`.

The summary is `.../quickbench/<stamp>/summary.json`, written atomically and written on every
ending (finished, cancelled, restore failed, unexpected raise):

```python
{
  "label": "quick: measured on this Mac",
  "repo": str, "format": str,
  "plan": <QuickPlan as JSON>, "estimate_s": int, "actual_s": float,
  "ended": "finished" | "cancelled" | "restore_failed" | "error",
  "results_dir": str,                      # the stamp directory
  "not_evicted": [str],                    # siblings the fetch layer refused to evict (`busy` or
                                           # any other refusal): empty when none failed
  "harness": {"version": str, "source_sha256": str},
  "engines": [{"name": str, "version": str|null, "tested": bool}],   # stage A's engines
  "load": {"stage_a": {"before": float, "after": float, "label": str|null} | null,
           "stage_b": ... | null},
  "osaurus": {"allowed": bool, "pinned": bool, "restored": bool|null, "reason": str|null},
  # "during_run": str is added to that object only when a mid-cell drift was caught: it is
  # <backup_dir>/during-run, where both host files were kept byte-exact before the restore
  "stage_a": {"caveat": "engines compared on one format only", "cells": [cell],
              "winner": str|null, "tie": [str], "note": str|null},
  "stage_b": {"caveat": "formats compared on one engine only", "engine": str|null,
              "cells": [cell], "note": str|null},
  "best": {"engine": str, "decode_tps": float, "ttft_s": float,
           "measured_at": iso, "quick": true} | null
}
# cell: {"engine", "format", "artifact_dir", "status": "PASS|FAIL|SKIPPED|ABORTED",
#        "reason": str|null, "decode_tps": float|null, "ttft_s": float|null,
#        "runtime_version": str|null, "label": "quick: measured on this Mac",
#        "reused": bool}
# ABORTED ("Stop now"): a mid-cell stop, no figure, never the winner -- see v5-app.md.
```

`best` is non-null only on a finished run: a cancelled or half-restored run is a record of what
happened, never a recommendation. `quickbench.latest(root)` returns the newest **finished** summary
per repo, keyed by repo id, skipping a file it cannot read — and `GET /recommendations` hands each
row's `best` to `recommend.pick(measured_here=...)`, which is the only way `Pick.measured_here` is
ever filled (D5).

The job kind is the same keystrokes the CLI uses: `ohyesmlx quickbench --repo R --yes [--osaurus]`
prints the plan and starts nothing without `--yes`; the `quickbench` job kind takes `repo`,
`confirmed: true` and the bool `osaurus`; `POST /jobs/{id}/cancel` stops it between cells.

