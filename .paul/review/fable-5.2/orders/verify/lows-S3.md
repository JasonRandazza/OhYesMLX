# Order: verify one Fable 5.2 finding (V step)

You verify one finding from a senior reviewer. Its report is a claim, not evidence. Your job is to prove it or refute it.

You run inside the `fable-verify` Orca worktree (branch `review/fable-verify`). Write exactly one report file:
`.paul/review/fable-5.2/verify/<FINDING-ID>.md`. If you can write a test, put it in a NEW file named after the finding
(`tests/test_fable_<finding-id>.py`, or `app/Tests/OhYesMLXKitTests/Fable<FindingId>Tests.swift`), so parallel
verifiers never edit the same file. Never fix the code.

Method:
1. Read the cited code (the ranges named) and its dossier entry. The dossiers live in the main checkout (read-only, absolute path):
   `/Users/jrazz/Dev/active/OhYesMLX/.paul/review/fable-5.2/dossier-S<n>.md`. Restate the claim in one line.
2. Try to reproduce it with the smallest failing test (pytest, or a swift test in app/Tests). Run only that test:
   `/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python -m pytest -q <file>::<name>` or
   `cd app && swift test --filter <name>`. A test that passes on the current code means the claim is not reproduced.
3. If no test is possible (a race needing real timing, a GUI-only path, packaging), give the concrete evidence instead:
   the exact code path with line numbers, or a command and its output.
4. End the file with exactly one verdict line:
   `VERDICT: CONFIRMED (test: <path::name>)` or `VERDICT: CONFIRMED (no test: <why>)` or `VERDICT: REFUTED (<evidence>)`
   and a line `SEVERITY-CHECK: agree | lower to <x> | raise to <x> — <why>`.
Never start a server, engine, model download or the app. Never edit code outside the one test you add.

---
FINDING:
 (BATCH) S3-F11 S3-F12 S3-F13 S3-F14 S3-F15 S3-F16 S3-F17

BATCH RULE: verify each finding below separately, one after another, applying the method above to each and writing
one report per finding (verify/<FINDING-ID>.md, each ending in its own VERDICT and SEVERITY-CHECK lines) and one test
file per finding. These are Low severity: prefer reading the code path and citing it when a test would need more
than about 40 lines. Do not spawn subagents.

=== FINDING-ID: S3-F11 ===
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


=== FINDING-ID: S3-F12 ===
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


=== FINDING-ID: S3-F13 ===
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


=== FINDING-ID: S3-F14 ===
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


=== FINDING-ID: S3-F15 ===
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


=== FINDING-ID: S3-F16 ===
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


=== FINDING-ID: S3-F17 ===
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

