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
file (`_ledger_path()`), each through `_shutdown(pid, port, tuple(stop_command))` (the spawned pid; `_shutdown` already takes every other listener on the port), and returns
how many it stopped. It reads the ledger and never writes it: `Handle.stop` still drops its own entry when the
cell's own stop path runs. A `RuntimeStopError` from one entry is written as one stderr line
`{"error": {"code": "abort_stop_failed", "message": str}}` and the next entry is still tried.

`quickbench.run(..., abort=<callable>)` (default never) — after each `measure_cell` returns, if `abort()` is
True the cell's record is replaced by status `"ABORTED"` with reason `"stopped by the user mid-cell; no number
is reported"` and no figures, and the run ends `"cancelled"` exactly as a between-cell cancel does (the
in-flight cell's stop path, sibling eviction and the Osaurus restore still run; the cell's raw rows stay on disk
because raw observations are never discarded). `"ABORTED"` joins the cell statuses in `v5-quickbench.md`; an
ABORTED cell never wins and is never compared. If the engine had not yet written its ledger entry when the
abort arrived, nothing is stopped, the cell runs to its own end and is still recorded `ABORTED`: the worst case
of "Stop now" is "Stop after this cell" with the number discarded.

## The launcher (`BackendLauncher`, plan 05-02)

- **Interpreter.** Production: `<App>.app/Contents/Resources/python/bin/python3`, with `ohyesmlx` installed in
  that interpreter's own site-packages (plan 05-06). Development: the path in `OYMLX_DEV_PYTHON`, a venv made
  by `scripts/dev_backend_venv.sh` whose site-packages holds a `.pth` naming the repo root. Neither found:
  the `couldnt_start` screen, naming which path was looked for.
- **Argv:** `[python, "-I", "-B", "-m", "ohyesmlx.cli", "app"]` (the package has no `__main__.py`; `cli.py` has the `__main__` guard). Nothing else, and never the token (P5-2, P5-3). `-B` because the app bundle is signed and may sit on a read-only volume, so the backend never writes bytecode into it (P5-6, plan 05-06); the bundled `ohyesmlx` is precompiled at build time.
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
- **Single instance (P5-7):** an exclusive `flock` on `<App Support>/OhYesMLX/app.lock` taken before the
  spawn; a second launch that cannot take it activates the running app (by bundle id, when it has one) and
  exits without spawning.

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
