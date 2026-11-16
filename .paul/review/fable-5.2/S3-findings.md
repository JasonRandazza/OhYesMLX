# S3 findings — the SwiftUI app

Reviewer: Fable 5.2, 2026-11-15. Read-only review: nothing was run, so every finding is from
source. Backend facts are quoted from `ohyesmlx/` at the lines given; where a lead was not
chased to the end, the Confidence line says so. Items in the dossier's "Already known" list and
W1 sweep rows 10–12 are not repeated.

Ordering is by severity, then by confidence.

### F1 — The real event stream never dispatches: `URLSession.AsyncBytes.lines` drops the blank line the SSE parser waits for
- Severity: High
- Where: `app/Sources/OhYesMLXKit/HTTPBackend.swift:38`, `:121-142`; `app/Sources/OhYesMLXKit/SSE.swift:11-21`
- Failure scenario: any live job (install, download, evict, quickbench) in the built app. The
  backend frames events as `id: N\ndata: {...}\n\n`. Foundation's `AsyncLineSequence` yields no
  element for an empty line, so `SSEParser.consume(line:)` never sees `""`, never dispatches, and
  only grows `dataLines`. No `JobEvent` reaches `AppModel.apply`. When the job ends the server
  (HTTP/1.0) closes the stream, `finished` is still false, and the loop reconnects every 200 ms
  with no `Last-Event-ID`, replaying the whole log, forever. On screen: the job sits at
  "Running", fraction 0; `canStartJob` stays false for the life of the process while the
  backend's slot is free; a quickbench never reaches Results; `inflightJob` is never cleared, so
  the next launch shows a false "interrupted" banner; Quit sees `jobRunning == true` and waits
  the 150 s job bound.
- Evidence: `for try await line in bytes.lines { continuation.yield(line) }` (transport) feeding
  `if line.isEmpty { … return data.joined(separator: "\n") }` (the only dispatch).
  `HTTPBackend.events` never calls `parser.dispatch()` at stream end either. Every test that
  covers `events` injects a fake `HTTPTransport`; `LiveBackendTests` calls only `hardware`,
  `engines`, `recommendations`; UI states are proven through `StubBackend`. The phase record
  agrees that nothing live has gone through this path: `05-04-PLAN.md:85` "Screenshots of every
  state, without a live job", `05-05-SUMMARY.md:39` "Not run: a live download or quickbench".
- Confidence: 75. The behaviour of `AsyncLineSequence` (empty lines omitted) is from memory of
  Foundation's source and of the common "can't use `bytes.lines` for SSE" report, not from a run.
  One live job in the app, or the test below, settles it either way.
- Fix direction: split the byte stream on `\n` yourself and keep empty lines (or treat the next
  `id:` line and end-of-stream as dispatch boundaries). Add the live test so the real transport
  is exercised once.
- Test idea: a `URLProtocol`-backed `URLSession` (or `LiveBackendTests` starting an `evict` of a
  repo that is not present) driving `HTTPBackend(transport: URLSessionTransport(...)).events`;
  assert that a `done` event is yielded within a few seconds.

### F2 — Any job's `result` event overwrites the benchmark summary; a later download empties Results and makes Export write the wrong file
- Severity: Medium
- Where: `app/Sources/OhYesMLXKit/AppModel.swift:700-702`; `app/Sources/OhYesMLX/Screens/ResultsView.swift:18`, `:45-51`, `:72`, `:195-205`
- Failure scenario: finish a quickbench (Results shows the best card), then download or remove
  another model, which is the natural next step. `fetch.py:1172-1176` sends
  `result {"status":"downloaded","repo":…,"bytes":…}`. `apply` sets `summaryData` to that payload
  and `summary` to nil. Results now shows "This run has not finished yet; its cells appear here
  as they land." over the old live cells, which is false, and "Export Results…" stays enabled and
  saves the download receipt as `OhYesMLX-quickbench-<stamp>.json`.
- Evidence: `case .result: summaryData = event.payloadData; summary = summaryData.flatMap { try?
  JSONDecoder().decode(QuickSummary.self, from: $0) }` has no `args.kind == .quickbench` guard,
  while `.progress` two lines below has one. Other `result` emitters: `fetch.py:883`, `:1173`,
  `:1303`, `engines.py:1317`. The w2 fix guarded only the `.done` reader (`:679-680`).
- Confidence: 90 for download; install and evict payloads were located by grep, not read.
- Fix direction: accept `.result` into `summary`/`summaryData` only when `args.kind ==
  .quickbench`.
- Test idea: stub a finished quickbench, then a download whose stream carries a `result`; assert
  `model.summary?.ended == .finished` and `summaryData` unchanged.

### F3 — A failed Osaurus restore is never stated to the user, and its detection depends on the whole summary decoding
- Severity: Medium
- Where: `app/Sources/OhYesMLXKit/AppModel.swift:679-681`, `:702`; `app/Sources/OhYesMLX/Screens/ResultsView.swift:110-114`; `app/Sources/OhYesMLX/Screens/BenchmarkView.swift:219-220`, `:276-277`
- Failure scenario: the pin's restore fails during a run (`quickbench.py:805-807`, `:931-933`).
  The backend ends with `done "quickbench stopped after a failed Osaurus restore"` and
  `summary.osaurus.restored == false` plus a reason. The app shows Results with "This run ended
  without a result; nothing is recommended from it." Nothing reads `summary.osaurus` (no
  reference in `app/Sources` outside the type), `job.message` renders only at
  `EnginesView.swift:145`, and the stage-B note that names the restore is written only when
  stage B never started (`quickbench.py:981-991`), so a failure in stage B leaves no line at all.
  The user's Osaurus settings are still pinned and the Benchmark screen has told them twice
  that "Osaurus settings are restored". Second path: `QuickSummary` requires all 16 keys and
  non-optional `label`/`reused`/`tie`; one added or renamed backend field makes `try?` return
  nil, the job reads `.finished`, and the screen says the run "has not finished yet".
- Evidence: `let restoreFailed = status.kind == .quickbench && summary?.ended == .restoreFailed`;
  `summary.ended == .cancelled ? "This run was stopped…" : "This run ended without a result…"`.
- Confidence: 65. Raise it by confirming no other view renders `JobState.failed` for a
  quickbench, and by reading what `_recover_startup` restores on the next launch (it may repair
  the pin, which lowers the harm but not the missing statement).
- Fix direction: read `ended` and `osaurus` from the raw payload (`event.payload?["ended"]`)
  rather than through the full typed decode, and give `restore_failed` its own Results section:
  what was pinned, that it was not put back, the backend's reason, and what the user can do.
  Soften the two "are restored" sentences to what the code can promise.
- Test idea: a stub summary with `ended: restore_failed` and one unknown extra-typed field (so
  the typed decode fails); assert the job state is `.failed` and the model exposes the restore
  failure.

### F4 — `cancelJob` writes back a snapshot taken before its await, discarding events and able to pin the slot busy
- Severity: Medium
- Where: `app/Sources/OhYesMLXKit/AppModel.swift:517-523`
- Failure scenario: press "Stop After This Cell" as the last cell lands. While
  `backend.cancel` is in flight, `apply` processes `result`, `error`/`done` and sets the job
  finished. The cancel returns and `job = status` restores the old copy with state
  `.stoppingAfterCell`. `isActive` is true again with no further event coming:
  `oneSlotReason` reports Busy, every start control is disabled, Quit takes the job path
  (150 s wait), and the stop buttons stay disabled, until the app is restarted. In the milder
  case the write only drops the events and fraction that arrived during the await.
- Evidence: `guard let current = job …; try await backend.cancel(…); var status = current;
  status.state = …; job = status`.
- Confidence: 85. The window is one localhost round trip, so it needs a cancel near a job's end,
  which is exactly when users press Stop.
- Fix direction: after the await, re-read `job`, and set the stopping state only if it is the
  same id and still active.
- Test idea: a backend whose `cancel` suspends until the test has delivered `done`; assert the
  job is not active afterwards.

### F5 — The app treats a job as over at `error`, but the backend holds the slot and runs rollback until `done`
- Severity: Medium
- Where: `app/Sources/OhYesMLXKit/AppModel.swift:689-695`, `:263-270`, `:569`; `ohyesmlx/engines.py:1234-1236`, `:1272-1279`; `app/Sources/OhYesMLXKit/BackendLauncher.swift:380-398`
- Failure scenario: cancel an install, or have a step fail. `engines.py` sends `error`, then runs
  `_rollback(created, engines_dir, send)`, then `done`. At `error` the app sets
  `.cancelled`/`.failed`, so `isActive` is false while files are still being removed. (a) Quit in
  that gap goes down the no-job path: stdin closed, SIGTERM at 10 s, SIGKILL 5 s later, against
  a backend that is inside rollback. The pinned rule is that a running job is never signalled.
  (b) Any start in the gap is answered `409 busy`, which the user cannot see outside Engines
  (F6), and for a benchmark has already wiped the previous run's summary.
- Evidence: `status.state = code == "cancelled" ? .cancelled : .failed` at `error`;
  `let jobRunning = job?.state.isActive == true`; `send("error", … "cancelled") / _rollback(…) /
  send("done", …)`.
- Confidence: 60. The gap exists in source; its length (a venv removal) was not measured, and
  quickbench and download send `error` and `done` adjacently, so only install is exposed.
- Fix direction: keep the job active until `done` (record the failure code at `error`, flip the
  state at `done`), which is also what the backend's slot does.
- Test idea: stub an install that sends `error`, pauses, then `done`; assert `canStartJob` is
  false and `requestQuit` passes `jobRunning: true` during the pause.

### F6 — `start()` does its destructive bookkeeping before the slot is claimed, and a refused start is invisible outside Engines
- Severity: Medium
- Where: `app/Sources/OhYesMLXKit/AppModel.swift:610-635`; `app/Sources/OhYesMLX/Screens/EnginesView.swift:17`
- Failure scenario: `job` is set only after `POST /jobs` returns, so a second `start()` can enter
  while the first is awaiting (double-click, or Retry on the interrupted banner followed by
  another control). The loser gets `409 busy` and runs `defaults.removeObject(forKey:
  inflightKey)`, deleting the winner's crash record, so a later crash shows no interrupted
  banner. Separately, a benchmark start clears `liveCells`, `summary` and `summaryData` before
  the POST; if the POST is refused or the connection fails, the previous run's results are gone
  from the screen and nothing ran. In both cases `refusal` is set, but only `EnginesView` renders
  it; on Models and Benchmark the click appears to do nothing (and the non-`BackendError` branch
  sets nothing at all).
- Evidence: reset block at `:611-620` and `writeInflight` at `:623` precede `try await
  backend.startJob` at `:627`; `catch let error as BackendError { refusal = error;
  defaults.removeObject(forKey: inflightKey); return }`.
- Confidence: 70. The double-entry window is a localhost round trip; the wipe-on-refusal and the
  invisible refusal need no race.
- Fix direction: claim the slot synchronously (a `starting` flag checked by `oneSlotReason` and
  by `start` itself), move the per-kind reset and `writeInflight` after a successful POST, and
  route a start refusal to the screen that asked (`benchmarkRefusal` / `modelRefusals`).
- Test idea: a backend whose `startJob` suspends; call `start` twice, fail the second with
  `busy`, complete the first; assert `inflightJob` is still present and `summary` from a prior
  run survives a refused benchmark start.

### F7 — The "couldn't start" screen's button relaunches while the backend is alive, and the app quits itself
- Severity: Medium
- Where: `app/Sources/OhYesMLX/RootView.swift:22`; `app/Sources/OhYesMLXKit/AppModel.swift:386-402`, `:410-443`; `app/Sources/OhYesMLXKit/BackendLauncher.swift:170-172`, `:260-269`
- Failure scenario: the backend launches and is adopted, but `reload()` fails (hardware not
  answered within the timeout, or `engines`/`recommendations` throws, for example one field this
  client cannot decode). The screen is `.couldntStart` with a live `runner`. The user presses the
  button; `relaunch()` calls `launcher.start()` without stopping the runner; the first session
  still holds the `flock`, so `acquireLock` fails and `start` returns `.alreadyRunning`;
  `alreadyRunning = true` makes the app activate "the other instance" (itself) and
  `NSApp.terminate`. The same happens after "Scan Again" fails. The user's retry closes the app
  with no message.
- Evidence: `relaunch` goes straight to `switch await launcher.start()` and maps
  `.alreadyRunning` to `alreadyRunning = true`; `reload` sets `screen = .couldntStart` on any
  failure without touching `runner`.
- Confidence: 70. Raise it by stubbing a launcher that returns `.running` and a backend whose
  `recommendations` throws.
- Fix direction: when a runner is alive, the retry is `reload()`; `relaunch()` should first quit
  the existing runner, or refuse when one is running.
- Test idea: model with a live fake runner and a backend that fails `engines()` once; invoke the
  couldn't-start action; assert `alreadyRunning == false` and the second attempt reaches
  `.welcome`.

### F8 — The single-instance lock lives in the app, not the backend, so a crashed or force-quit app can be relaunched beside a backend that is still unwinding
- Severity: Medium
- Where: `app/Sources/OhYesMLXKit/BackendLauncher.swift:260-269`, `:501-516`; `ohyesmlx/cli.py:1168`, `:1184-1202`; `ohyesmlx/server.py:261-292`
- Failure scenario: the app crashes or is force-quit during a quickbench cell. Its lock
  descriptor closes with the process. The old backend sees stdin EOF and waits up to 120 s + 15 s
  for the job, with the engine still holding the model. The user reopens the app at once: the
  lock is free, a second backend starts, runs `_recover_startup()` against state the first
  backend still owns, and the interrupted banner offers Retry. Two backends, and potentially two
  resident models, on one Mac, which is the failure hotspot 5 names. No Python-side lock exists
  (`app.lock`/`flock` have no match under `ohyesmlx/`).
- Evidence: the lock is acquired by the Swift launcher and released in `handleTermination` or
  by process death; the backend's shutdown is `listener.jobs.cancel_and_wait(
  server.JOB_SHUTDOWN_WAIT_S)` after EOF.
- Confidence: 50. Not read: `_recover_startup` (it may kill the old engine server, which limits
  the overlap but then races the old backend's own cleanup and Osaurus restore), and whether the
  lock fd is opened close-on-exec.
- Fix direction: let the backend own the lock's lifetime: hand the locked descriptor to the
  child (or have the child take the `flock` itself before printing the launch line), so a new
  launch waits or reports "still finishing" until the old backend is gone.
- Test idea: launcher test with a child that ignores stdin EOF for 2 s; drop the first launcher
  without `quit`; assert a second `start()` returns `.alreadyRunning` until the child exits.

### F9 — Results drops the run's own contention flag and tie list, then calls one engine "fastest" and "Best on your Mac"
- Severity: Medium
- Where: `app/Sources/OhYesMLX/Screens/ResultsView.swift:89-98`, `:143`, `:240-242`; `app/Sources/OhYesMLXKit/Models.swift:630`, `:656-660`, `:719`
- Failure scenario: (a) the backend measures load before and after each stage and labels a
  contended stage `this Mac was busy` (`summary.load.stage_a/b.label`). The app decodes it and
  renders it nowhere, so numbers the harness itself flagged as measured under contention are
  shown as a clean "quick: measured on this Mac" result. (b) Two engines land inside the noise
  floor; the backend records `stage_a.tie = [a, b]` (`quickbench.py:831-832`). The app ignores
  `tie`, badges one "fastest in stage" and heads the page "Best on your Mac". Both are the
  project's "a published table carries its caveat" rule failing at the last step.
- Evidence: no reference to `.load`, `.tie`, or "this Mac was busy" in `app/Sources` outside the
  model types and `StubBackend.swift:833` (the fixture carries the label; no view shows it).
  `isWinner: cell.engine == winner && cell.status == "PASS"`.
- Confidence: 80 that both are dropped; whether `best` itself is withheld on a tie was not read
  (`_best`). "Best on your Mac" is the comp's pinned copy (`comps.html:460`), so the wording is a
  product call; the missing qualifiers are the defect.
- Fix direction: render the load label beside the stage caveat when present; when `tie` has more
  than one name, replace "fastest in stage" with "tied" on each and say so on the best card.
- Test idea: view-model test over the finished stub summary: a stage with `load.label` set
  exposes a busy line; a summary with a two-name `tie` yields no single "fastest" row.

### F10 — Free-disk figures go stale after every download and removal, and "Free disk after" is client arithmetic over the stale value
- Severity: Medium
- Where: `app/Sources/OhYesMLX/Screens/ModelsView.swift:74`, `:286-295`; `app/Sources/OhYesMLX/Screens/BenchmarkView.swift:201-206`, `:255-258`; `app/Sources/OhYesMLXKit/AppModel.swift:663-665`, `:696-698`
- Failure scenario: launch with 40 GB free, download a 20 GB model. `hardware` is fetched at
  launch, on "Scan Again", and after a `low_disk` error only; the post-job refresh at `:663-665`
  re-reads recommendations, not hardware. The Models toolbar still says "Free disk 40 GB" and
  the benchmark plan's "Free disk after" is `40 GB − downloadBytes`, overstated by 20 GB. With
  `hardware == nil` it prints 0. The file's header says "Nothing here computes a number".
- Evidence: `let free = model.hardware?.diskFreeBytes ?? 0; return Format.size(max(0, free -
  plan.downloadBytes))`; `if args.kind == .download || args.kind == .evict { await
  refreshRecommendations() }`.
- Confidence: 80. The backend's own low-disk guard still refuses an impossible job, so the harm
  is a wrong number on screen, not a full disk.
- Fix direction: refresh hardware wherever recommendations are refreshed after a download or
  evict, and have the plan carry `free_after` from the backend rather than subtracting here.
- Test idea: stub whose `hardware()` returns a lower `diskFreeBytes` on the second call; run a
  download to `done`; assert `model.hardware.diskFreeBytes` changed.

### F11 — `HTTPBackend.events` reconnects forever on every error except `unknown_job`
- Severity: Low
- Where: `app/Sources/OhYesMLXKit/HTTPBackend.swift:143-156`
- Failure scenario: the backend dies mid-job. `backendExited` marks the job interrupted, but
  the `start()` task is still inside `for try await event in backend.events(…)`, retrying a dead
  port five times a second for the rest of the process, across Relaunch as well (the old
  `HTTPBackend` value keeps its port and token). `start()` never returns, so its trailing
  `refreshRecommendations` never runs. A `401` or a `429 too_many_streams` loops the same way.
- Evidence: `catch { if Task.isCancelled { finished = true } else { try? await
  Task.sleep(for: retryDelay) } }`; nothing cancels the stream when the runner exits.
- Confidence: 85.
- Fix direction: bound consecutive failures (or stop on connection-refused and on 4xx other than
  429), and cancel the event task from `backendExited`.
- Test idea: transport that always throws `URLError(.cannotConnectToHost)`; assert the stream
  finishes within N attempts.

### F12 — Quit handshake: a backend that exits while "Quit anyway" is offered strands the app, and the quit banner mislabels what is happening
- Severity: Low
- Where: `app/Sources/OhYesMLXKit/AppModel.swift:531-533`, `:571-574`; `app/Sources/OhYesMLX/RootView.swift:10-11`, `:130-131`, `:142-144`; `app/Sources/OhYesMLX/OhYesMLXApp.swift:88-95`
- Failure scenario: (a) `requestQuit` gets `.stillRunning`, clears `quitInProgress`, and returns
  without replying to AppKit's `.terminateLater`. If the backend then exits, `backendExited`
  sets `backendStopped`, the backend-stopped view replaces the whole shell including the "Quit
  anyway" banner, and the only button is Relaunch, which starts a new backend in an app the
  user asked to quit. (b) The banner reads "Finishing <kind> <repo id>…" for any non-nil `job`,
  including one that finished an hour ago, and says "Finishing" when closing stdin makes the
  backend cancel the job (W1 backend facts), with the raw repo id rather than the display name.
- Evidence: `if outcome == .stillRunning { quitInProgress = false; quitAnywayOffered = true;
  return }`; `guard !quitInProgress else { return }; backendStopped = status`; `if let job =
  model.job { Text("Finishing \(job.kind.wireName) \(job.name)…") }`.
- Confidence: 70. The backend bounds its own shutdown at about 135 s against the app's 150 s, so
  (a) needs a backend that overruns its bound and then exits.
- Fix direction: in `backendExited`, if `quitAnywayOffered` then `finishQuit()`; show the banner
  line only for an active job and word it as stopping, with the display name.
- Test idea: model test: quit returns `.stillRunning`, then call `backendExited`; assert
  `shouldExit == true` and `onQuitComplete` fired.

### F13 — "Stop After This Cell" cannot be escalated to "Stop Now"
- Severity: Low
- Where: `app/Sources/OhYesMLX/Screens/BenchmarkView.swift:80`, `:89`, `:95-98`
- Failure scenario: the user presses "Stop After This Cell" and the cell in flight hangs or runs
  for minutes. Both buttons are disabled for the rest of the job, so the one control built for
  that moment is unreachable; the only way out is quitting the app, which waits 150 s.
- Evidence: both buttons carry `.disabled(stopping)` where `stopping` is true for
  `.stoppingAfterCell` as well as `.stoppingNow`.
- Confidence: 85 on the behaviour; `v5-app.md:93` pins two controls and does not say the first
  locks the second, and the backend's `aborted()` flag is separate from `cancelled()`.
- Fix direction: disable "Stop Now" only in `.stoppingNow`.
- Test idea: after `cancelJob(now: false)`, assert a second `cancelJob(now: true)` reaches the
  backend and the state becomes `.stoppingNow`.

### F14 — Any failure to open or lock `app.lock` is reported as "already running" and the app quits silently
- Severity: Low
- Where: `app/Sources/OhYesMLXKit/BackendLauncher.swift:170-172`, `:260-269`
- Failure scenario: Application Support is unwritable, the lock path is a directory, or `flock`
  fails for a reason other than `EWOULDBLOCK`. `acquireLock` returns nil, `start` returns
  `.alreadyRunning`, and the app activates whatever shares its bundle id and terminates. There
  is no other instance and no message.
- Evidence: `acquireLock` returns nil for `open` failure and for every `flock` failure alike;
  the caller maps nil to `.alreadyRunning`.
- Confidence: 75.
- Fix direction: return `.alreadyRunning` only for `EWOULDBLOCK`; everything else is
  `.couldntStart` with the errno text.
- Test idea: point `appSupportDirectory` at a path whose `app.lock` is a directory; assert
  `.couldntStart`.

### F15 — Retry from the interrupted banner skips the plan and confirmation the first start required, and the banner itself only appears for crashes
- Severity: Low
- Where: `app/Sources/OhYesMLXKit/AppModel.swift:546-559`, `:684`
- Failure scenario: (a) an install interrupted by a crash is retried with
  `start(.install(engine:))` directly: no consent sheet, no listing of the steps, although the
  plan can differ from the one consented to (new app version, changed lab paths). An interrupted
  evict is re-run without the confirm sheet. (b) On a normal quit mid-download the backend
  cancels the job and its `error`/`done` reach the still-running event loop, so `done` clears
  `inflightJob`; the next launch shows no banner for a download the quit stopped. The test that
  pins the banner (`testQuitMidDownloadLeavesTheBannerAndNoAutomaticRetry`) runs on the stub.
- Evidence: `case .install: await start(.install(engine: interrupted.name))`; `case .done: …
  defaults.removeObject(forKey: inflightKey)`.
- Confidence: 50. (b) depends on the handler thread flushing before the backend exits, and on
  F1 being fixed first.
- Fix direction: route Retry through the same entry points the buttons use (consent sheet for
  install, confirm for evict); decide whether a quit-cancelled job should keep its record and
  clear it on `done` only when the state was not a quit.
- Test idea: `retryInterrupted()` for an install with `installConsent == false`; assert no
  `startJob` call.

### F16 — `kill()` signals a pid without checking the child is still that process
- Severity: Low
- Where: `app/Sources/OhYesMLXKit/BackendLauncher.swift:99-101`
- Failure scenario: `forceKill` (the "Quit anyway" path, or the end of the escalation) races the
  child's own exit; after `Process` has reaped it the pid is free for reuse and
  `Darwin.kill(pid, SIGKILL)` lands on whatever took it.
- Evidence: `Darwin.kill(process.processIdentifier, SIGKILL)` with no `process.isRunning` test.
- Confidence: 40. The window is small; S1 reported the same pattern on the Python side.
- Fix direction: guard with `process.isRunning` (and skip once `handleTermination` has run).
- Test idea: fake process already terminated; assert `kill()` sends nothing.

### F17 — A plan fetch that fails without a `BackendError` leaves the previous model's plan under the new picker selection, and Start runs it
- Severity: Low
- Where: `app/Sources/OhYesMLXKit/AppModel.swift:506-508`, `:512-514`
- Failure scenario: pick model B; the plan request times out or fails to decode. The generic
  `catch { return false }` keeps `quickPlan` for model A, sets no refusal, and the picker shows
  B. "Start Benchmark" is enabled and `startBenchmark` runs `quickPlan.repo`, which is A. The
  plan text does name A, so an attentive user can see it; nothing says the plan for B failed.
- Evidence: `} catch { return false }` after the `BackendError` branch that does clear
  `quickPlan`.
- Confidence: 60.
- Fix direction: treat the generic failure like the `BackendError` branch: clear the plan and
  set `benchmarkRefusal` with the error text.
- Test idea: backend whose `quickbenchPlan` throws `URLError(.timedOut)` for B after a good plan
  for A; assert `quickPlan == nil` and a refusal is set.

## Adjudicated, no finding

- Q6 (VoiceOver row semantics differ across the three row types): a real inconsistency against
  DESIGN §5, but no row hides information from VoiceOver in the code read; left to the design
  pass.
- Q7 (two download-progress sources): both derive from the same event stream; the meter shows
  remaining bytes and the row shows the fraction. Duplication, no divergent number found.
- Q8 (poison-frame skip needs integer ids): the server assigns `seq = len(events) + 1`
  (`server.py:206`), integers from 1, so `Int(frameID)` and `last > 0` hold. Moot until F1 is
  fixed, since no frame is dispatched today.
- Hotspots 1–3 (launch line, first-line-wins, child environment): read; the token enters only
  through the first stdout line and is not placed in the environment or logged.
- Hotspots 14–15: `payloadData` re-serialises through `JSONValue`; integers survive as `Int64`.
  A double with an integral value (`188.0`) is re-emitted as `188`: a type change in the
  exported file, value preserved; not reported.
- `URLSessionTransport` defaults to `URLSession.shared`: loopback requests are not sent to
  system proxies on macOS as far as I know, so no token-exposure finding is made; an ephemeral
  session with `connectionProxyDictionary = [:]` would remove the question.

Coverage:

Hotspots
1. `BackendLauncher.start` :158-210 — covered (no finding; see F14 for the lock mapping)
2. `deliverLine`/`awaitLaunchLine` — covered (no finding)
3. `childEnvironment` — covered (no finding)
4. `quitWait` :380-398 — covered (F5)
5. `acquireLock` :260-269 — covered (F8, F14)
6. `requestQuit`/`quitAnyway`/`finishQuit` — covered (F12, F5)
7. `applicationShouldTerminate` — covered (F12)
8. `AppModel.start` :607-666 — covered (F6, F11)
9. `AppModel.apply` :668-712 — covered (F2, F3, F5)
10. `cancelJob` :517-529 — covered (F4)
11. `backendExited` :531-539 — covered (F12, F11)
12. `HTTPBackend.makeRequest` — covered (no finding)
13. `HTTPBackend.events` :110-162 — covered (F1, F11)
14. `JobEvent.payloadData` — covered (no finding; note above)
15. `JSONValue.init(from:)` — covered (no finding)
16. `writeInflight`/`loadInflight` — covered (F6, F15)
17. `updateBenchmarkCell` — covered (no finding)
18. `planBenchmark` :491-510 — covered (F17)
19. `ResultsView.export()` — covered (F2)
20. `StubScenario.makeModel`/`drive` — covered (no defect in the fixtures; F1 is what they cannot see)

Open questions
1. Double-click start / slot claimed late — covered (F6)
2. Backend exit while "Quit anyway" is offered — covered (F12)
3. Retry semantics per kind, install skips consent — covered (F15)
4. Stop controls racing events — covered (F4, F13)
5. "Best on your Mac" over-claim, "Now running" guess — covered (F9; "Now running" is an inference from landed cells and is not separately reported)
6. VoiceOver row inconsistency — covered (no finding)
7. Two download-progress sources — covered (no finding)
8. Poison-frame skip and integer ids — covered (no finding)

Leads not chased: `_recover_startup` (bears on F3 and F8), `quickbench._best` on a tie (F9),
the install and evict `result` payloads (F2), and `AsyncLineSequence` at runtime (F1).
