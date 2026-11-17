# v5 app — interface shapes (Phase 5, pinned 2026-11-13)

The SwiftUI client in `app/` and the two backend additions it needs. The client is a client only: every
number, refusal and decision comes from the backend shapes in `v5-onboarding.md` and `v5-quickbench.md`,
which this file points at and never restates. Plans: `.paul/phases/v5-onboarding/05-*-PLAN.md`. The
packaging rules it must keep are `docs/threat-model.md` §10 (P5-1..P5-12).

## Backend addition: "Stop now" (plan 05-01, Jason 2026-11-13, prototype Q3)

`POST /jobs/{id}/cancel` keeps its current meaning with no body (or `{}`): stop at the next check, which for a
quickbench is **between cells** ("Stop after this cell"). It also accepts the body `{"now": true}`, under the
same body guard as `POST /jobs` (`415`/`413`/`400 bad_json`), with these refusals:

- any key other than `now`, or a `now` that is not JSON `true`: `400 bad_args` naming the key;
- `now` on a job whose kind is not `quickbench`: `409 not_abortable` ("only a quickbench can stop mid-cell");
- the existing `404 unknown_job`, `409 not_cancellable` (evict) and `409 job_finished` still come first.

On `{"now": true}` the server sets the job's cancel flag **and** its abort flag, then starts its injected
`stop_engines` (default `runtimes.stop_own_engines`) on a daemon thread and answers `202` at once; a second
`{"now": true}` on the same job answers `202` and starts no second stop (audit 05-01).

`runtimes.stop_own_engines(root=None) -> int` stops every engine in **this process's** running-engines ledger
file (`_ledger_path()`), each through `_shutdown(pid, port, _stop_command_for_port(port))` (the spawned pid;
`_shutdown` already takes every other listener on the port), and returns how many it stopped. It reads the
ledger and never writes it: `Handle.stop` still drops its own entry when the cell's own stop path runs. A
`RuntimeStopError` from one entry is written as one stderr line
`{"error": {"code": "abort_stop_failed", "message": str}}` and the next entry is still tried.

The ledger file (plan 05-09) is `{"owner": {"pid", "lstart", "argv"}, "entries": [{"pid", "lstart", "argv",
"serving_pid", "serving_lstart", "serving_argv", "port"}, ...]}`, identities as `ps` prints them under
`LC_ALL=C TZ=UTC`. It holds no command: the stop command is derived from `RUNTIMES` by the entry's port, and a
`stop_command` field in a file written before 05-09 is ignored. "This process's" file means its owner block is
this process (`runtimes.same_process`); a file an earlier process left under the same pid, or one without an
owner block, is never Stop now's, and an entry marked `"inherited": true` (an earlier process's entry this one
could not settle) is skipped. An entry whose recorded pid is alive but no longer the recorded process is one
`abort_stop_failed` line and is not signalled.

`quickbench.run(..., abort=<callable>)` (default never) — after each `measure_cell` returns, if `abort()` is
True the cell's record is replaced by status `"ABORTED"` with reason `"stopped by the user mid-cell; no number
is reported"` and no figures, and the run ends `"cancelled"` exactly as a between-cell cancel does (the
in-flight cell's stop path, sibling eviction and the Osaurus restore still run; the cell's raw rows stay on disk
because raw observations are never discarded). `"ABORTED"` joins the cell statuses in `v5-quickbench.md`; an
ABORTED cell never wins and is never compared. Since 05-09 the engine is in the ledger from its spawn, so an
abort during the load stops it too (below).

**Stop now during a load (plan 05-09, S5-F5).** The engine is in the ledger from its spawn: `Runtime.start`
writes the entry (pid, identity, port) right after `_spawn` and before it awaits readiness, and writes it again
after readiness with `serving_pid` (replace by pid, no duplicate). The first write is one `ps` and a file and is
not subtracted from `cold_load_s` (the engine loads while it runs); an earlier process's file at the same path is
settled before the load clock starts. Identity is compared by start time, since oMLX, vMLX and MTPLX `exec` from a
shell script and change argv. So a Stop now (or a launch after a killed backend) during the load already finds and stops the
engine. A start that fails and whose own cleanup succeeds forgets the entry; one whose cleanup fails keeps it.
A `RuntimeStopError` from a cell ends the quickbench run (summary `ended: "error"`, no later cell started, the
Osaurus restore still run) rather than being recorded as one `FAIL` cell.

## The launcher (`BackendLauncher`, plan 05-02)

- **Interpreter.** Production: `<App>.app/Contents/Resources/python/bin/python3`, with `ohyesmlx` installed in
  that interpreter's own site-packages (plan 05-06). Development: the path in `OYMLX_DEV_PYTHON`, a venv made
  by `scripts/dev_backend_venv.sh` whose site-packages holds a `.pth` naming the repo root. Neither found:
  the `couldnt_start` screen, naming which path was looked for.
- **Argv:** `[python, "-I", "-B", "-m", "ohyesmlx.cli", "app", "--lock-dir", <appSupportDirectory>]` (the package has no `__main__.py`; `cli.py` has the `__main__` guard). Nothing else, and never the token (P5-2, P5-3). `-B` because the app bundle is signed and may sit on a read-only volume, so the backend never writes bytecode into it (P5-6, plan 05-06); the bundled `ohyesmlx` is precompiled at build time.
- **Environment:** built, not inherited: `PATH=/usr/bin:/bin:/usr/sbin:/sbin` (launchd's default, P5-9),
  `HOME`, `USER`, `LOGNAME`, `TMPDIR`, `LANG` from the parent, nothing else. No `PYTHON*` variable.
- **Working directory:** `~/Library/Application Support/OhYesMLX`, created `0700` by the client before the
  spawn if absent (P5-5).
- **Launch line:** the first stdout line, `{"port": int, "token": str}` (v5-onboarding.md). The client
  waits at most 30 s for it; EOF or exit first is `couldnt_start` carrying the last stderr lines (P5-10).
  After it, the client polls `GET /hardware` until 200 (at most 10 s) before leaving `launching`.
- **Token:** held in a `BackendToken` value whose `description`/`debugDescription` are `"<redacted>"`; the
  only reader of its raw string is the `Authorization` header builder (P5-1).
- **Stderr:** each line is kept in a bounded ring (last 200) and may be shown as it is (P5-10).
  Stderr, and stdout after the launch line, are drained continuously from spawn so the child never blocks on a
  full pipe. Stdin is a pipe held open until quit (EOF is the backend's parent-death signal).
- **Child exit while running:** `.exited(status, stderrTail)`; the app shows "The backend stopped" with
  **Relaunch**, and a running job keeps its `inflightJob` entry so the interrupted banner follows.
- **Quit (P5-8):** close the child's stdin, then wait for exit. While a job is running the wait is unbounded
  from the app's side (the backend bounds itself: 120 s + `JOB_KILL_GRACE_S`); the app shows "Finishing
  <job>…" and never sends SIGKILL on its own; 150 s after stdin closed it offers **Quit anyway**, and only that
  click sends SIGKILL. With no job running, wait 10 s, then SIGTERM, then 5 s, then SIGKILL.
- **Single instance (P5-7, owner moved to the backend in 05-08, S3-F8):** the **backend** holds an exclusive
  `flock(LOCK_EX | LOCK_NB)` on `<lock dir>/app.lock` for its whole life, so a crashed or force-quit app's
  backend keeps it until it has finished unwinding. `<lock dir>` is the `--lock-dir` argument the launcher
  passes (its own `appSupportDirectory`, so a test or scratch launch locks its own directory); without it,
  `ohyesmlx.app_support_dir()`. Only the lock moves; every other path still comes from `HOME`. The backend
  takes the lock before it binds the port, runs startup recovery or prints anything, writes its pid into the
  file, and opens it non-inheritable, so no engine server it spawns ever holds it. When the lock is held, the
  backend's only stdout line is the refusal below and it exits 2, having bound nothing:

  ```json
  {"error": {"code": "already_running", "holder_pid": 4242}}
  ```

  `holder_pid` is the integer the holder wrote, or `null` when the file is unreadable or not yet written. Any
  other failure to open or lock is one stderr line `{"error": {"code": "lock_failed", "message": str}}`, exit 2,
  nothing on stdout. The app holds no lock across the child's life. Before spawning it probes the lock (take and
  release at once) only as a fast path; the probe and the refusal line map the same way: **another instance of
  the app is running** (by bundle id, other than itself) → `.alreadyRunning`, which activates it and exits;
  **none is** → `.stillFinishing`, the couldn't-start screen as "The previous session is still finishing" with
  **Check again** (a relaunch). Only `EWOULDBLOCK` means a holder (S3-F14): any other probe failure is
  `.couldntStart` with the errno text. With a live backend, the couldn't-start retry is a reload against it,
  never a second spawn (S3-F7).

## The client (`Backend` protocol, plan 05-02)

One protocol, two implementations: `HTTPBackend` (URLSession against `http://127.0.0.1:<port>`, header
`Authorization: Bearer <token>`, never an `Origin` header) and `StubBackend` (fixtures, for view-model tests
and previews). Methods map 1:1 onto routes: `hardware()`, `engines()`, `recommendations()`,
`quickbenchPlan(repo:)`, `startJob(kind:args:) -> jobID`, `cancel(jobID:now:)`, `events(jobID:after:) ->
AsyncThrowingStream<JobEvent>` (SSE: `id:`/`data:` framing, resumes with `Last-Event-ID` after a dropped
connection, ends after `done`). Codable types mirror the pinned JSON exactly (snake_case keys via
`CodingKeys`, byte counts `Int64`); an error body decodes to `BackendError {code, status, message}` and the UI
shows its `message` as the backend wrote it.

## The app model (`AppModel`, plan 05-02; screens in 05-04/05-05)

Screens: `launching`, `couldntStart`, `unsupported`, `moveToApplications`, `welcome`, `yourMac`, `engines`,
`models`, `benchmark`, `results`. `moveToApplications` is the App Translocation state (plan 05-06, AC-7):
`AppModel` checks `bundlePath` for `/AppTranslocation/` before it spawns the backend and before any job can
start, because engine venvs are made from `sys.executable`, a path inside the app that changes every launch
there. The screen says "Move OhYesMLX to your Applications folder, then open it again" and offers only Quit.
The flow and its edge cases are the Phase 5 prototype's (`prototype/phase5-flows`, never merged);
Jason's answers to its seven questions (2026-11-13) are binding:

1. **One slot:** while a job runs, every other job-starting control is disabled with the reason
   "Busy: <kind> <name> is running". A `409 busy` that still arrives is shown as the backend's message.
2. **Interrupted job:** before `startJob` the client writes `{kind, name, started}` to
   `UserDefaults` key `inflightJob` and clears it on `done`. At launch, a leftover entry shows a one-line banner
   "<kind> of <name> was interrupted when OhYesMLX quit." with **Retry** (re-sends the same job after a fresh
   user click) and **Dismiss**. Never an automatic retry.
3. **Cancel a benchmark:** two controls, "Stop after this cell" (`cancel(now: false)`) and "Stop now"
   (`cancel(now: true)`); the first shows "Stopping after this cell…", the second "Stopping…". Results shows an
   ABORTED cell as "Stopped by you", with no number.
4. **`low_disk`:** owned by the Models screen: shown inline on that model's row, the disk meter refreshed
   (`hardware()` again), with how much to free computed from the refusal payload's `needed_bytes - free_bytes` (plan 05-01 adds both to
   every `low_disk` payload; the client never parses the message or restates the disk margin).
5. **Guided install re-verify:** `engines()` is re-requested whenever the app becomes active or the Engines
   screen appears, and from a **Check again** button.
6. **Unsupported Mac:** absolute. `hardware.supported == false` shows only `unsupported` with
   `unsupported_reason`; no control leads past it.
7. **`not_evicted`:** Results shows one plain line per repo: "Left on disk: <title> (<size>) — it was in use.
   You can remove it from Models."
