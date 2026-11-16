# Dossier S3 — The SwiftUI app

Scope: `app/Sources/OhYesMLXKit/*.swift`, `app/Sources/OhYesMLX/**/*.swift`, `app/Package.swift`.
Baseline: working tree = `714e8f6` on `main`; the app tree itself is unchanged since `101df7c`
(05-06, which also carries the wave-2 review fixes; see §3). Line numbers below are from this tree,
confirmed with `grep -n`/`sed -n` against each file. Nothing was run, started, or fixed; the only
file written is this one.

## 1. Map

### app/Package.swift (20 lines)

- `app/Package.swift:2-20` — SwiftPM manifest: library target `OhYesMLXKit`, executable `OhYesMLX`
  (depends on the kit), test target `OhYesMLXKitTests`; zero external dependencies; swift-tools 6
  language mode.

### app/Sources/OhYesMLXKit/BackendToken.swift (19 lines)

- `BackendToken.swift:3-19` — the token wrapper: `description`/`debugDescription`/`customMirror`
  all render `<redacted>` (P5-1), `raw` (:18, internal) is the only accessor of the secret and is
  read only by `HTTPBackend.makeRequest`'s Authorization builder.

### app/Sources/OhYesMLXKit/Backend.swift (87 lines)

- `Backend.swift:3-27` — `JobKind` enum (install/download/evict/quickbench) with `wireName` and
  `init?(wireName:)` (the inverse; nil for unknown wire names).
- `Backend.swift:29-67` — `JobArgs` enum: four cases; `body` (:53-66) builds the `POST /jobs` args
  dict — always `confirmed: true`, quickbench adds `osaurus` (the consent toggle's wire value).
- `Backend.swift:69-77` — `BackendEndpoint` struct (port + token) — what the launch line decodes to.
- `Backend.swift:79-87` — `Backend` protocol: `hardware`, `engines`, `recommendations`,
  `quickbenchPlan`, `startJob`, `cancel(jobID:now:)`, `events(jobID:after:)` returning
  `AsyncThrowingStream<JobEvent, Error>`.

### app/Sources/OhYesMLXKit/Models.swift (787 lines)

- `Models.swift:3-96` — `JSONValue` enum: the untyped JSON tree every payload rides on;
  `init(from:)` :12-35 (Int64 preserved for integers), `encode(to:)` :36-55, typed accessors
  :56-96 (string/bool/int/double/array/object).
- `Models.swift:98-111` — `Volume` (path, freeBytes; `free_bytes` key).
- `Models.swift:113-169` — `Hardware` (supported, unsupportedReason, chip, family, tier, cpuCores,
  gpuCores, ramBytes, macos, diskFreeBytes, volumes, modelBudgetBytes; snake_case CodingKeys).
- `Models.swift:171-181` — `PlanStep` (id, label, command?).
- `Models.swift:183-215` — `InstallPlan` (engine, kind, sourceURL, sizeBytesEstimate, needsAdmin,
  steps).
- `Models.swift:217-263` — `EngineStatus` (name, title, blurb, installed, version?, path?, tested,
  verified?, install?).
- `Models.swift:265-301` — `MeasuredHere` (decodeTPS, engine, format?, measuredAt, quick, repo?,
  ttftS) — one quickbench measurement of a pick on this Mac.
- `Models.swift:303-365` — `Pick` (modelID, title, paramsB, format, sizeBytes, fit, fitBasis,
  engines, installNeeded, startHere, reason, downloaded, measuredHere?).
- `Models.swift:367-382` — `ExcludedModel` (modelID, reason).
- `Models.swift:384-400` — `Recommendations` (picks, excluded, unsupportedReason?).
- `Models.swift:402-412` — `PlannedEngine` (engine, version?, tested).
- `Models.swift:414-433` — `PlannedSibling` (repo, format, sizeBytes, downloaded).
- `Models.swift:435-471` — `QuickPlan` (repo, format, stageA, stageB, downloadBytes, osaurus,
  estimateS).
- `Models.swift:473-479` — `JobEventType` enum (progress/log/result/error/done).
- `Models.swift:481-513` — `JobEvent` (seq, type, message, fraction?, payload?); `payloadData`
  :499-505 re-encodes `payload` with `.sortedKeys` — the client's canonical re-serialisation, not
  the wire's bytes (docstring says so; see §3 w2#3).
- `Models.swift:515-527` — `BackendError` (code, status?, message; `LocalizedError`).
- `Models.swift:529-534` — `BackendErrorEnvelope` (internal; the `{error: {...}}` body wrapper).
- `Models.swift:536-541` — `QuickEnding` enum (finished/cancelled/restore_failed/error).
- `Models.swift:543-556` — `QuickHarness` (version, sourceSHA256).
- `Models.swift:558-569` — `QuickEngine` (name, version?).
- `Models.swift:570-625` — `QuickCell` (engine, format, repo, artifactDir, status, reason?,
  decodeTPS?, ttftS?, runtimeVersion?, label, reused; `id` = "format/engine/artifactDir").
- `Models.swift:626-641` — `QuickStageA` (caveat, cells, winner?, tie, note?).
- `Models.swift:642-655` — `QuickStageB` (caveat, engine?, cells, note?).
- `Models.swift:656-667` — `QuickLoad` (the per-runtime load record in the summary).
- `Models.swift:668-682` — `QuickLoads`.
- `Models.swift:683-706` — `QuickOsaurus` (the pin/restore record).
- `Models.swift:707-779` — `QuickSummary` (label, repo, format, plan, estimateS, actualS?, ended,
  resultsDir, notEvicted, harness, engines, load, osaurus, stageA, stageB, best?).
- `Models.swift:781-787` — `QuickSummary.bestFormat` extension (winning cell's format, falling
  back to the chosen row's).

### app/Sources/OhYesMLXKit/Format.swift (54 lines)

- `Format.swift:4-54` — the one place numbers become text: `memory` :8-11 (binary GB, macOS
  labelling), `size` :13-20 (decimal GB/MB), `rate` :22-25 ("62.1 tok/s"), `percent` :27-30,
  `duration` :32-37 ("0.21 s" / "about 11 min"), `fixed` :39-41, `trimmed` :43-52; number and unit
  joined by NBSP.

### app/Sources/OhYesMLXKit/SSE.swift (65 lines)

- `SSE.swift:3-51` — `SSEParser`: incremental `id:`/`data:` framing; `consume(line:)` :10-47
  (blank line dispatches the joined data, `:` comments ignored, `lastEventID` recorded per
  dispatched frame), `dispatch()` :49-51.
- `SSE.swift:53-64` — `events(from:)` static: whole-text fixture parser (tests/previews).

### app/Sources/OhYesMLXKit/HTTPBackend.swift (222 lines)

- `HTTPBackend.swift:3-6` — `HTTPTransport` protocol (`data(for:)`, `lines(for:)`).
- `HTTPBackend.swift:8-49` — `URLSessionTransport`: `data` :15-21, `lines` :23-49 (byte-lines
  stream, task cancelled on stream termination).
- `HTTPBackend.swift:51-210` — `HTTPBackend` struct (port + token + transport + retryDelay):
  `hardware` :70-72, `engines` :74-76, `recommendations` :78-80, `quickbenchPlan` :82-88,
  `startJob` :90-96, `cancel` :98-108 (body `{"now": true}` only when now; nil otherwise),
  `events` :110-162 (SSE consume loop, poison-frame skip, reconnect on drop with
  `Last-Event-ID`, `unknown_job`/cancellation end the stream), `get` :164-169,
  `makeRequest` :171-192 (the ONLY reader of `token.raw`, `Authorization: Bearer` header),
  `check` :193-197, `error` :199-210 (error envelope → `BackendError`, else `bad_response`).
- `HTTPBackend.swift:212-217` — `StartJobBody` (kind + args).
- `HTTPBackend.swift:219-222` — `JobIDResponse` (`job_id` → jobID).

### app/Sources/OhYesMLXKit/BackendLauncher.swift (566 lines)

- `BackendLauncher.swift:4-15` — `LaunchOutcome` (couldntStart/alreadyRunning/running) and
  `QuitOutcome` (exited/terminated/killed/stillRunning) enums.
- `BackendLauncher.swift:17-29` — `QuitTiming` (grace 10 s, terminateGrace 5 s, jobBound 150 s;
  `standard` at :28).
- `BackendLauncher.swift:31-40` — `LauncherProcess` protocol (run/terminate/kill/waitForExit,
  stdin/stdout/stderr handles, onTermination).
- `BackendLauncher.swift:43-50` — `BackendRunner` protocol (endpoint, stderrTail, isRunning,
  onExit, `quit(jobRunning:)`, `forceKill()`).
- `BackendLauncher.swift:52-111` — `FoundationLauncherProcess` (`@unchecked Sendable`): `Process()`
  wrapper; `run` :84-93, `terminate` :95-97, `kill` :99-101, `waitForExit` :103-111 (bounded
  poll).
- `BackendLauncher.swift:113-275` — `BackendLauncher` (`@unchecked Sendable`): `init` :126-140,
  `defaultAppSupportDirectory` :142-147 (App Support/OhYesMLX), `bundledInterpreter` :149-156,
  `start` :158-210 (single-instance `flock` on `app.lock`, spawn, await the launch line,
  `alreadyRunning`/`couldntStart`/`running` outcomes), `childEnvironment` :212-220 (built, not
  inherited: only `inheritedKeys`; PATH pinned to `pathForChild`), `resolveInterpreter` :222-233,
  `missingInterpreterMessage` :235-241, `prepareAppSupport` :243-254 (creates 0700 — P5-5),
  `lockPath` :256-258, `acquireLock` :260-269, `releaseLock` :271-275.
- `BackendLauncher.swift:277-528` — `LaunchSession` (`@unchecked Sendable`, the child-process
  state machine): `startReading` :318-329 (drain threads), `awaitLaunchLine` :331-352,
  `installExitHandler` :354-369, `closeStdin` :371-378, `quitWait` :380-398 (stdin close → wait;
  job: unbounded-ish `jobBound`; no job: grace → SIGTERM → SIGKILL), `forceKill` :400-403,
  `abandon` :405-415 (failed launch cleanup), `readLines` :417-445 (stdout/stderr drain; ring
  capped 200), `deliverLine` :447-466 (first stdout line is the launch line; later lines never
  overwrite), `appendStderr` :468-475, `stdoutEnded` :477-486, `timeOutLaunchLine` :488-499,
  `handleTermination` :501-516, `releaseLockIfNeeded` :518-528 (flock release).
- `BackendLauncher.swift:530-566` — `RunningBackend` (`BackendRunner`): `quit` :550-556 (async
  hop onto `quitWait`), `forceKill` :558-566.

### app/Sources/OhYesMLXKit/StubBackend.swift (1020 lines)

- `StubBackend.swift:3-31` — fixture records: `StubScript`, `StubJobStart`, `StubCancelCall`.
- `StubBackend.swift:33-234` — `StubBackend` (`@unchecked Sendable`, NSLock-guarded script
  double): setters :75-111 (incl. `Endpoint` enum :104-111), `enqueue`/`releaseJob` :113-129,
  call recorders :131-149, protocol methods :151-234 (`startJob` :191-206 replays queued scripts
  through `events` :216-234; `hold` holds the stream until `releaseJob`).
- `StubBackend.swift:236-936` — `StubScenario` enum: 17 screen states :237-252, `consentEngineName`
  :256-258, `hardwareReadyTimeout` :260-264, `summaryPayload` :266-271, `benchmarkRunningEvents`
  :273-302, `missingEngines` :304-312, `needsPlan` :314-319, `makeBackend` :321-468 (the full
  scripted backend per scenario), fixtures `stubHardware` :470-488, `stubEngines` :490-538,
  `engine` :540-560, `osaurusPlan` :562-580, `optiqPlan` :582-613, `recommendations` :615-622,
  `stubRecommendations` :624-708, `stubPlan` :710-736, `stubSummaryData` :738-740,
  `stubSummary` :742-936.
- `StubBackend.swift:938-1020` — `@MainActor` extension: `makeModel` :940-958 (an `AppModel` on a
  private `UserDefaults` suite; seeds `inflightJob` for the `interrupted` scenario),
  `drive` :960-1020 (scripted user: navigates, starts jobs, injects `backendExited` for
  `backend-stopped`) — DEBUG-only.

### app/Sources/OhYesMLXKit/AppModel.swift (821 lines)

- `AppModel.swift:4-16` — `Screen` enum (launching, couldntStart, unsupported, moveToApplications,
  welcome, yourMac, engines, models, benchmark, results).
- `AppModel.swift:18-42` — `JobState` enum (running, stoppingAfterCell, stoppingNow, finished,
  failed, cancelled, interrupted); `text` :27-38, `isActive` :39-42 (the first three).
- `AppModel.swift:44-70` — `JobStatus` (id, kind, name, state, fraction, message, events).
- `AppModel.swift:72-84` — `LowDisk` (freeBytes, neededBytes; `amountToFree` :81-84 = needed−free).
- `AppModel.swift:86-96` — `InterruptedJob` (kind, name, started) — the banner record.
- `AppModel.swift:98-143` — `BenchmarkCell` (stage, engine, format, status, reason?, decodeTPS?,
  ttftS?, runtimeVersion?; `id` :108 = "stage/engine/format"; wire init :131-143).
- `AppModel.swift:145-153` — `EngineFailure` (code, outputTail).
- `AppModel.swift:155-821` — `AppModel` (`@MainActor @Observable`, the whole app state):
  state vars :158-215 (screen, hardware, engines, recommendations, quickPlan, job, refusal,
  benchmarkRefusal, engineFailures, modelRefusals, lowDisk, liveCells, summary, summaryData,
  interruptedJob, launchError, backendStopped, backendStderrTail, quitInProgress,
  quitAnywayOffered, alreadyRunning, shouldExit, installConsent, osaurusConsent,
  onQuitComplete; `inflightKey` :213); computed: `unsupported` :188, `showsInterruptedBanner`
  :190-192, `yourMacComplete` :194, `enginesComplete` :196, `modelsComplete` :198,
  `benchmarkComplete` :200-206 (summary/measuredHere-derived, survives later jobs);
  `init` :217-231 (all dependencies injectable), `convenience init(launcher:)` :233-253
  (PlaceholderBackend until launch); `isTranslocated` :255-257 / `translocated` :259-261
  (`/AppTranslocation/` check — AC-7); `oneSlotReason` :263-267, `canStartJob` :269-271,
  `notEvictedLines` :273-285 (the ONE "Left on disk…" template — Q7), `benchmarkCells` :287-292
  (summary replaces live cells), `notEvicted` :293; `displayName` :297-301, `engineTitle`
  :303-312 (tested/verified suffix); `nextBenchmarkCell` :314-334 ("Now running" guess from
  planned−landed); `downloadedPicks` :336-340, `defaultBenchmarkPick` :342-348;
  `downloadProgress` :350-360 (bytes_done/bytes_total from the latest such payload);
  `launch` :362-384 (translocation gate → launcher.start → adopt → loadInflight → reload),
  `relaunch` :386-408, `reload` :410-444 (hardware poll until `hardwareReadyTimeout`, then
  engines + recommendations; failure → couldntStart); `go(to:)` :446-449 (unsupported gate),
  `appBecameActive` :451-453, `enginesScreenAppeared` :455-457, `checkEnginesAgain` :459-461
  (all three → `refreshEngines` — Q5); `install` :463-469 (consent gate), `download` :471-473,
  `evict` :475-477; `quickbench` :479-489 (plan then start), `planBenchmark` :491-510
  (`planningRepo` identity guard :497, :501, :505 — stale responses dropped),
  `startBenchmark` :512-515, `cancelJob` :517-529 (now → `.stoppingNow`, else
  `.stoppingAfterCell`); `backendExited` :531-539 (crash: active job → `.interrupted`; ignored
  while quitting); `dismissInterrupted` :541-544, `retryInterrupted` :546-560 (re-sends by
  kind; quickbench re-plans); `requestQuit` :562-577 (runner.quit; `.stillRunning` →
  `quitAnywayOffered`), `quitAnyway` :579-582 (the only SIGKILL path), `finishQuit` :584-589;
  `adopt` :591-599 (swap in the live HTTPBackend + exit handler), `refreshEngines` :601-605;
  `start` :607-666 (the job funnel: translocation/unsupported guard :608, per-kind state reset,
  `writeInflight` before `startJob`, POST failure clears inflight and sets `refusal`, sets
  `job`, quickbench → `.benchmark` screen, consumes the event stream to `done`,
  download/evict re-request recommendations); `apply` :668-712 (per-event state machine: `done`
  → finished/failed(restoreFailed, quickbench-only :679-681) + inflight clear + quickbench →
  `.results`; `error` → cancelled/failed + `route`; `result` → summary/summaryData;
  `progress` → live cells for quickbench); `route` :713-738 (error landing: engineFailures /
  modelRefusals / lowDisk / benchmarkRefusal — a cancelled quickbench never becomes a plan
  refusal); `updateBenchmarkCell` :740-760 (merge by "stage/engine/format"); `refreshHardware`
  :762-767, `refreshRecommendations` :769-773; `writeInflight` :775-780 / `loadInflight`
  :782-791 (UserDefaults `inflightJob` = {kind, name, started}).
- `AppModel.swift:794-821` — `PlaceholderBackend` (private; every method throws
  `URLError(.cannotConnectToHost)`; the pre-launch backend).

### app/Sources/OhYesMLX/OhYesMLXApp.swift (96 lines)

- `OhYesMLXApp.swift:5-74` — `@main` App: `init` :15-30 (DEBUG: `OYMLX_STUB_SCENARIO` →
  `StubScenario.makeModel()`; else production model with `BackendLauncher`), `body` :32-52
  (Window "OhYesMLX" 1100×720 min 900×600; `scenePhase == .active` → `appBecameActive`;
  `alreadyRunning` → focus the existing instance and `NSApp.terminate`), `launchView` :54-74
  (`.task { launch() }`, or `scenario.drive` in DEBUG).
- `OhYesMLXApp.swift:76-96` — `AppDelegate` (`@MainActor`): `applicationDidFinishLaunching`
  :80-86 (`.regular` activation; `onQuitComplete` → `reply(toApplicationShouldTerminate: true)`),
  `applicationShouldTerminate` :88-95 (`requestQuit()` in a Task, `.terminateLater`).

### app/Sources/OhYesMLX/RootView.swift (262 lines)

- `RootView.swift:4-34` — `RootView.body`: full-window states first (backendStopped →
  BackendStoppedStateView with relaunch :9-12; launching :14-15; couldntStart :16-22; unsupported
  :23-24; moveToApplications :25-26) else `shell`.
- `RootView.swift:36-74` — `shell`: NavigationSplitView; interrupted banner (display-named copy,
  Retry re-sends the real job) :47-57; toolbar "Scan Again"/"Check Again" :61-71.
- `RootView.swift:76-107` — `sidebar`: Setup list, completion checkmarks (accessibilityHidden),
  footer "Nothing changes on this Mac without a click."
- `RootView.swift:109-123` — `selection` binding and `currentItem` (screen → sidebar item).
- `RootView.swift:125-156` — `lifecycleBanners`: quit-in-progress line ("Finishing …") and the
  "Quit anyway" offer banner.
- `RootView.swift:158-174` — `screenBody` switch over screens → the five screen views.
- `RootView.swift:176-215` — `SidebarItem` enum (yourMac/engines/models/benchmark/results; title,
  symbol, stepText).
- `RootView.swift:217-262` — `SidebarItem` extension: `init?(screen:)` :217-233,
  `isComplete` :235-244 (delegates to the model's four `…Complete`), `isReachable` :246-262
  (sequential-gate reachability).

### app/Sources/OhYesMLX/Components/ (5 files)

- `Badge.swift:4-23` — `Badge` view: small capsule text chip ("estimated", "Start here", …).
- `ConsentSheet.swift:7-82` — install consent sheet: plan steps (label + SF Mono command),
  estimated size, needs-admin row, Cancel/Install ("Open Download Page" for guided_download);
  no undo claim (DESIGN §4.1).
- `Figure.swift:4-16` — `Figure` view: monospaced-digit number+unit chip.
- `InterruptedBanner.swift:5-30` — one-line interrupted-job banner with Retry/Dismiss.
- `StatusGlyph.swift:3-32` — `StatusKind` (pass/warning/fail/neutral/stopped → SF symbol + semantic
  colour :10-27); `cellStatus` :34-43 (the ONE status-string → glyph+word mapping; ABORTED →
  "Stopped by you"); `StatusGlyph` :45-54 (8 pt glyph, accessibilityHidden).

### app/Sources/OhYesMLX/Screens/ (6 files)

- `BenchmarkView.swift:8-93` — `BenchmarkView.body`: empty state :100-113, model Picker (fires
  `planBenchmark` per change) :22-36, refusal/plan/running sections :38-55, stop toolbar ("Stop
  After This Cell"/"Stop Now", `.help` :73-90), `onAppear` plans the default :64-70.
  Internals: `stopping` :95-98, `emptyState` :100-113, `refusalSection` :115-131,
  `planSections` :133-253 (stage tables, "Before you start" Time/Downloads/Free-disk-after with
  `estimated` badges :188-207, Osaurus consent toggle :209-238, Start Benchmark :240-253),
  `diskAfter` :255-258 (client-computed free−downloads), `runningSections` :263-310 (state line,
  explainer, "Now running", "Cells"), `stageLine` :312-323 ("Stage A: engines, cell 3 of 5").
- `BenchmarkView.swift:327-347` — `BenchmarkCellRow`: stage · title, StatusGlyph + word,
  decode figure.
- `EnginesView.swift:4-81` — `EnginesView`: the one place `model.refusal` renders :17, engine
  rows, consent sheet flow; `startInstall` :74-80 (sets `installConsent`, installs, clears).
- `EnginesView.swift:83-215` — `EngineRow`: title/version/installed-state label, `activeJob`
  :91-95, `failure` :97-99 (EngineFailure output tail), `trailing` :135-174 (Install…/Try Again
  with the one-slot reason beside the control :185-197), `failureView` :176-201,
  `accessibilityLabel` :203-215.
- `FullWindowStates.swift:4-185` — `LaunchingStateView` :4-17, `CouldntStartStateView` :19-42,
  `UnsupportedStateView` :44-68, `MoveToApplicationsStateView` :70-94, `BackendStoppedStateView`
  :96-137 (exit status + stderr tail + Relaunch), `CenteredState` :139-157, `StderrBox` :159-174
  (stderr shown as written — P5-10), `CopyDetailsButton` :176-185.
- `ModelsView.swift:9-89` — `ModelsView`: pick rows, `activeDownload` :79-89 (disk meter's
  Download), toolbar DiskMeter.
- `ModelsView.swift:91-268` — `ModelRow`: Start-here badge/title/format, fit glyph+word +
  `fitBasis` badge :113-119, reason :120-122, measuredHere figure + "quick: measured on this
  Mac" badge :124-130, composed `accessibilityLabel` :136-137/:247-266, `lowDiskLine` :160-170
  (Q4: `amountToFree` from the refusal payload), `trailing` :172-245 (progress + Cancel /
  busy / Downloaded + Remove… / Download, each with the reason beside it and an a11y hint).
- `ModelsView.swift:270-313` — `DiskMeter` (free-disk gauge; the in-progress download drawn as
  "set aside"): nested `Download` :271-275, body :280-303, `reserved` :308-311.
- `ModelsView.swift:319-352` — `EvictSheet`: remove confirmation (names the freed size; the row
  stays), Cancel/Remove.
- `ResultsView.swift:11-75` — `ResultsView.body`: summary → best card + stage sections +
  not-evicted lines; live → "not finished yet" + cells; no run → "Measured on this Mac";
  Export toolbar button (disabled without summaryData).
- `ResultsView.swift:77-84` — `exported()` binding (export error alert).
- `ResultsView.swift:87-122` — `bestSection`: "Best on your Mac" card (or the cancelled/empty
  line).
- `ResultsView.swift:124-163` — `stageSection`: caveat/note + `ResultCellRow`s (stage B named by
  format, winner check).
- `ResultsView.swift:165-193` — `noRunSection`: "Measured on this Mac" rows from `measuredHere`.
- `ResultsView.swift:195-209` — `export()`: `NSSavePanel` → writes `model.summaryData`
  ("re-serialised as JSON" copy).
- `ResultsView.swift:211-221` — `stamp()` (yyyymmdd-hhmmss filename).
- `ResultsView.swift:223-286` — `ResultCellRow`: engine+version, status glyph+word,
  decode/TTFT figures, note; `status` :259-268, `figure` :270-280, `statusIsSecondary` :282-286.
- `YourMacView.swift:4-75` — `YourMacView`: chip/family/tier, cores, RAM (binary GB), macOS,
  free disk, model budget; `processor` :69-75.

## 2. Contracts

### docs/interfaces/v5-app.md (pinned 2026-11-13; whole file binds this section)

- **Launcher** (`:37-64`): "Argv: `[python, "-I", "-B", "-m", "ohyesmlx.cli", "app"]` … Nothing
  else, and never the token (P5-2, P5-3)"; "Launch line: the first stdout line,
  `{"port": int, "token": str}`"; "Stdin is a pipe held open until quit (EOF is the backend's
  parent-death signal)"; Quit (P5-8): "close the child's stdin, then wait for exit. While a job
  is running the wait is unbounded … never sends SIGKILL on its own; 150 s after stdin closed it
  offers **Quit anyway**, and only that [kills]".
- **Client** (`:66-75`): one `Backend` protocol, `HTTPBackend` ("header `Authorization: Bearer
  <token>`, never an `Origin` header") and `StubBackend`; "Codable types mirror the pinned JSON
  exactly (snake_case keys via `CodingKeys`, byte counts `Int64`)"; "SSE: `id:`/`data:` framing,
  resumes with `Last-Event-ID` after a dropped connection, ends after `done`"; "an error body
  decodes to `BackendError {code, status, message}` and the UI shows its `message` as the backend
  wrote it".
- **AppModel + screens** (`:77-104`): the ten screens; App Translocation gate "before it spawns
  the backend and before any job can start"; Q1 one slot ("every other job-starting control is
  disabled with the reason … A `409 busy` that still arrives is shown as the backend's message");
  Q2 interrupted job ("writes `{kind, name, started}` to `UserDefaults` key `inflightJob` and
  clears it on `done` … **Retry** (re-sends the same job after a fresh user click) and
  **Dismiss**. Never an automatic retry"); Q3 stop controls ("Results shows an ABORTED cell as
  'Stopped by you', with no number"); Q4 low_disk ("how much to free computed from the refusal
  payload's `needed_bytes - free_bytes` … the client never parses the message or restates the
  disk margin"); Q5 re-verify engines on active/appear/Check again; Q6 unsupported is absolute
  ("no control leads past it"); Q7 not_evicted copy ("Left on disk: <title> (<size>) — it was in
  use. You can remove it from Models.").
- **"Stop now"** (`:8-35`): `POST /jobs/{id}/cancel` with `{"now": true}` aborts mid-cell; "the
  run ends 'cancelled' exactly as a between-cell cancel does"; stop semantics: "Stop now" means
  "Stop after this cell" with the number discarded (`:35`).

### docs/interfaces/v5-onboarding.md — JSON shapes the client decodes

- `Hardware` (`:11-16`): `{"supported": bool, "unsupported_reason": str|null, … "disk_free_bytes":
  int, "volumes": [{"path", "free_bytes"}], "model_budget_bytes": int}`.
- Recommendations/pick (`:54`, `:74`): `… "downloaded": bool, "measured_here": object|null}`;
  "`measured_here` is non-null only for a run on this user's Mac (Decision D5) … never filled
  from our M2 Max rows" (`:88-90`).
- Job stream (`:103-137`): `POST /jobs` → `202 {"job_id": "16-hex"}`; events are `{"seq": int,
  "type": "progress|log|result|error|done", "message": str, "fraction": float|null, "payload":
  object|null}` (`:121-122`); "a `Last-Event-ID` request header resumes after that seq" (`:124`);
  "A job keeps at most 10,000 events" (`:129`); cancel answers `202` and a second job is
  `409 busy` naming the running job's id (`:119-120`, `:133`); a `low_disk` error payload carries
  `free_bytes` and `needed_bytes` as JSON integers (`:114-115`); a download's progress payload
  carries `bytes_done`/`bytes_total` (`:152`).

### docs/interfaces/v5-quickbench.md — shapes the client decodes

- Cell progress (`:132-133`): "Every `progress` event about a cell … carries
  `{"stage": "A"|"B", "engine": str, "format": str, "status": str, "reason": str|null}".
- Plan (`:102-124`): `stage_a: list[PlannedEngine]`, `stage_b: list[PlannedSibling]`,
  `estimate_s`; "`estimate_s` is `cards * ESTIMATE_PER_CELL_S (90) + download_bytes / …" — the
  estimate the summary compares with its actual seconds.
- Stages (`:139-145`): "Stage A varies the engine … Stage B holds that engine and varies the
  format"; "every cell carries the label `quick: measured on this Mac`".

### docs/threat-model.md §10 — rows naming this code (checklist, status at Phase 5 first pass)

- **P5-1** (`:577`, status `:598`): "The Swift client never writes the token to `os_log`,
  `print`, stdout/stderr, a file, a crash report, analytics, or a URL." Status: Met.
- **P5-2** (`:578`, `:599`): "The backend is spawned with the token in no argv and no environment
  variable. The client reads the launch line only from the child's stdout pipe." Status: Met.
- **P5-7** (`:583`, `:601`): "Only one app instance (and so one backend) runs per user. A second
  launch focuses the first." Status: Met (`flock` on `app.lock`).
- **P5-8** (`:584`, `:602`): "On quit, the client closes the backend's stdin and waits for it to
  exit, and does not SIGKILL while a job reports itself running. On launch, the backend's startup
  recovery (T-02) has run before the first screen offers a job." Status: Met.
- **P5-10** (`:586`, `:604`): "The app may show or persist the backend's stderr lines as they
  are, and must never add request headers or the token to them." Status: Met.
- **P5-11** (`:587`, `:605`): "Copy: a model whose files differ in size from the catalog is
  offered as 're-download', not reported as corrupt." Status: **Partly met / open** (see §3).

### docs/design/phase5/DESIGN.md (app sections)

- §4.1: "Do not claim an uninstall" — the consent sheet lists plan steps, size, needs_admin
  "and nothing else"; the comp's invented `pip install` line is banned.
- §4.3: "Every status is a glyph plus a word: PASS `circle.fill` green, FAIL
  `xmark.circle.fill` red, SKIPPED `minus.circle` secondary, Stopped by you `stop.circle`
  secondary. The note column carries the reason."
- §4.6 (Q1): "Disabled actions need their reason next to them, not elsewhere … Keep that pattern
  on every job-starting control, and expose the reason as the control's accessibility hint."
- §5 accessibility floor: "Every glyph that carries status has a text label beside it. VoiceOver
  reads the row as one element … All actions are reachable by keyboard … the window must lay out
  at its minimum size (900×600) without truncating a figure."
- §6: "every number (the backend's)" is not the screen's to compute or claim; hype words banned.

### AGENTS.md rules that bind here

- "One definition of everything" (and "Each rationale is written once") — applies to the
  not_evicted copy, the status→word mapping, and any re-derived backend string.
- "Stop and ask before adding a module, a subcommand, or a header pin" — `app/` is an approved
  surface (v5.0, 2026-10-29) in the listed form; a new Swift file/target is a new surface.
- "No new dependency without naming what it replaces" — `Package.swift` has none; keep it so.
- The app test command: `cd app && OYMLX_DEV_PYTHON=$HOME/.local/share/ohyesmlx/app-dev-venv/bin/python swift test`
  (a UI change also needs coordinator screenshots of `OYMLX_STUB_SCENARIO` states in light/dark).
- "Never infer a capability from the absence of a flag" — governs any claim that a runtime or the
  backend cannot do something (client-side negative claims need source evidence).

## 3. Already known — do not re-report

Format: `- <claim> — <source> — fixed <sha> | accepted | deferred | open`.
(All shas are on `main`; the w2 fix order is recorded in `fee692b`, whose note says the fixes
landed in the 05-06 commit's app tree, i.e. `101df7c`.)

### Threat-model §10 status (2026-11-14 first pass, checked on the `101df7c` bundle)

- P5-1 token-logging rule met (raw value read only in `HTTPBackend`'s Authorization builder;
  `BackendToken` prints `<redacted>`) — threat-model §10 status — accepted (Met).
- P5-2 argv/env/launch-line rule met — threat-model §10 status — accepted (Met).
- P5-5 App Support 0700 "Met on this account; clean account pending" — threat-model §10 status —
  open (clean-account smoke needs Jason's sudoers step, 05-06 AC-6).
- P5-6 read-only bundle run met (with `-B` and precompiled tree) — threat-model §10 status —
  accepted (Met).
- P5-7 single instance met (`open -n` focuses the first; `flock` on `app.lock`) — threat-model
  §10 status — accepted (Met).
- P5-8 quit protocol met (no signal during a job; Quit anyway only after 150 s) — threat-model
  §10 status — accepted (Met).
- P5-10 stderr shown as written, no token in it — threat-model §10 status — accepted (Met).
- **P5-11 only partly met**: the app never says "corrupt" but "cannot offer 'Re-download' because
  `Pick.downloaded` is a single bool: the client cannot tell 'absent' from 'present with different
  sizes'. This needs a backend field." — threat-model §10 status + STATE.md Deferred Issues —
  **open** (also flagged as Fable S4 scope; a backend field plus Models row copy).
- P5-12 SBOM ships (interpreter, ohyesmlx, toolchain, 105 pinned packages) — threat-model §10
  status — accepted (Met).

### Phase summaries — Deviations / Carried forward

- Unbundled `swift run` is background-only (no Dock icon; menu Quit works); 05-04 added
  `.regular` activation — 05-02-SUMMARY Deviations 1 — fixed `3495886`.
- Memory rendered decimal ("68.7 GB"); 05-04's `Format.memory` renders binary "64 GB" as About
  This Mac does — 05-02-SUMMARY Deviations 2 — fixed `3495886`.
- Bundle-id activation of an already-running instance untestable until the .app existed —
  05-02-SUMMARY Deviations 3 — fixed `101df7c` (05-06 built the bundle; §10 P5-7 verifies it).
- 05-06 deviations (packaging, not client logic): `-B` added to the SBOM step; version 0.3.0
  reads `ohyesmlx.__version__`; nothing published (no GitHub Release, no notarization — D7,
  outward-facing, Jason's call) — 05-06-SUMMARY Deviations — accepted/deferred.
- PHASE-4.5 carried forward: §10 checklist P5-3/P5-4 must re-verify against the bundled
  interpreter (done in §10 status: Met), `/engines` can report vMLX installed for an account
  that cannot execute its bundle (multi-user Macs) — deferred; §9 accepted risks (lock
  stale-reclaim race; global pip config under `--isolated`) — accepted.
- 05-01 deviations are backend-side (Content-Length detection, `_entry_stop_command`, smoke
  script's retired `skipped` key — "fix when 05-06 reruns the smoke") — 05-01-SUMMARY Deviations
  1-3 — deferred (last one still pending the AC-6 smoke run).

### Wave-1 review findings (`.paul/review/2026-11-14-phase5-w1/`) — all fixed in `ac0de1b`

- Stage-B quickbench cells collapse into one row keyed by engine (data loss in the client's cell
  table) — w1 spec #2 + standards HARD #1 — fixed `ac0de1b` (structured cell events; `BenchmarkCell`
  carries `stage/engine/format`, rows keyed `"stage/engine/format"`).
- Q6's absolute gate missed quickbench (a run/Retry could reach the benchmark screen on an
  unsupported Mac) — w1 spec #3 — fixed `ac0de1b` (`start()` guards `!unsupported, !translocated`;
  banner suppressed on unsupported via `showsInterruptedBanner`).
- Poison SSE event (undecodable frame) looped forever (`last` never advanced; job pinned running;
  false "interrupted" at next launch) — w1 standards JUDGEMENT (HTTPBackend.swift) — fixed
  `ac0de1b` (skip + advance `last` to the frame's SSE id).
- `deliverLine` overwrite lost the launch line when two stdout lines arrived before the await
  (healthy backend reported "could not be read") — w1 standards JUDGEMENT (BackendLauncher.swift)
  — fixed `ac0de1b` (first line wins; later lines discarded).
- w1 spec #1/#4/#5 are Python-side (server/quickbench/test_quickbench) — out of S3 scope.
- w1 standards "P5-1..P5-12: no breach found" — accepted.

### Wave-2 review findings (`.paul/review/2026-11-14-phase5-w2/`) — fixes in `101df7c`

- Stale `summary` marked every later job failed (`.done` consulted `summary?.ended` for any kind)
  — w2 spec #1 / standards #4 — fixed `101df7c` (`status.kind == .quickbench` guard,
  `AppModel.swift:679-681`; test `testADownloadAfterARestoreFailedQuickbenchStillFinishes`).
- Benchmark tick was ephemeral (keyed off the current `job`) — w2 spec #2 — fixed `101df7c`
  (`benchmarkComplete` derives from summary/measuredHere; tests
  `testTheBenchmarkTickSurvivesALaterDownload`, `testAPickMeasuredHereTicksBenchmark…`).
- D8 "exactly as received" not implemented (`payloadData` re-encodes sorted-keys; export claimed
  byte-exactness) — w2 spec #3 — fixed `101df7c` by the "accept re-encode and fix the copy"
  branch: docstrings now say "this client's own canonical re-serialisation", the export panel
  says "re-serialised as JSON". **The spec side (05-05 AC-2/AC-5 wording "exactly as received")
  was not found in `docs/` by grep — whether the pinned contract was amended is unverified here.**
- Two definitions of the not_evicted line (ResultsView built its own; tests pinned the other) —
  w2 spec #4 / standards #6 — fixed `101df7c` (ResultsView renders `model.notEvictedLines`, the
  one template at `AppModel.swift:273-285`).
- Benchmark plan fetch race (picker A→B quick: stale plan wins) — w2 spec #5 — fixed `101df7c`
  (`planningRepo` identity guard; test `testASlowPlanForThePreviousPickIsDropped`).
- AC-1's grep gate: `String(format:)` in ModelsView — w2 spec #6 / standards #1 — fixed `101df7c`
  (`String(format:)` now only in `Format.swift`; verified by grep in §5).
- `BenchmarkCellRow` rendered status as a bare word (DESIGN §4.3 violation) — w2 standards #2 —
  fixed `101df7c` (StatusGlyph + word at `BenchmarkView.swift:327-347`).
- Disabled "Try Again" carried only an a11y hint, no visible reason beside the control — w2
  standards #3 — fixed `101df7c` (reason rendered beside it at `EnginesView.swift:185-197`).
- StatusGlyph 9 pt vs DESIGN §3's 8 pt — w2 standards #7 — fixed `101df7c`
  (`StatusGlyph.swift:50` reads `.font(.system(size: 8))`).
- Status-word inconsistency ("Pass"/"PASS") across three files — w2 standards #8 — fixed
  `101df7c` (`cellStatus` at `StatusGlyph.swift:34-43` is the one mapping).
- Duplicated install flow (startInstall vs retry) — w2 standards #9 — fixed `101df7c`
  (`startInstall` at `EnginesView.swift:74-80` is the single path).
- `waitUntilAsync` byte-for-byte duplicate of `waitUntil` in AppModelTests — w2 standards #10 —
  fixed `101df7c` (grep now finds one `waitUntil` at `AppModelTests.swift:121`).
- w2 standards #5 is Python-side (server.py/quickbench.py "newest wins") — out of S3 scope.

### Other review dirs

- `.paul/review/2026-09-23/` predates `app/` (Phase 3-era; Python/scripts/docs only) — no app
  findings to carry.
- STATE.md Blockers (Osaurus sampler penalties, mlx-lm prompt caches, hero-model safetensors
  re-serialisation) are measurement-side — out of S3 scope.

## 4. Hotspots

Where a defect would hurt most: the token/child-process trust boundary, the one job slot and its
state machine, quit-vs-job semantics, numbers the UI presents as measured, and races around the
two async gaps (`await` points on `@MainActor`).

1. `app/Sources/OhYesMLXKit/BackendLauncher.swift:158-210` — `BackendLauncher.start`: spawns the
   child and parses the launch line (the token enters the process here); a mis-parse either
   leaks (logs the line) or bricks launch — guarded by `LauncherTests`
   (`testArgvEnvironmentAndDirectory`, `testTheFirstStdoutLineIsTheLaunchLine…`).
2. `BackendLauncher.swift:447-466` — `deliverLine`/`awaitLaunchLine` :331-352: the launch-line
   race; regressing the "first line wins" fix silently loses the token line on a chatty child —
   `LauncherTests.testTheFirstStdoutLineIsTheLaunchLineWhenTwoArriveBeforeTheAwait`,
   `testChattyStderrStillYieldsTheLaunchLine`.
3. `BackendLauncher.swift:212-220` — `childEnvironment`: the P5-2/P5-9 boundary (token must
   never be in env; PATH pinned); a leak here is invisible in the UI —
   `LauncherTests.testArgvEnvironmentAndDirectory`.
4. `BackendLauncher.swift:380-398` — `quitWait`: the P5-8 signal escalation; SIGKILL during a
   running job violates the pinned contract and can corrupt a run's on-disk record —
   `LauncherTests.testQuitWhileAJobRunsClosesStdinAndNeverSignals`,
   `testQuitEscalatesGraceThenTerminateThenKill`, `testQuitReturnsTerminated…`,
   `testQuitReturnsExited…`.
5. `BackendLauncher.swift:260-269` — `acquireLock`: single-instance (P5-7/T-15); failure mode is
   two backends, two model loads on one Mac —
   `LauncherTests.testSecondLauncherIsAlreadyRunningAndSpawnsNothing`.
6. `app/Sources/OhYesMLXKit/AppModel.swift:562-589` — `requestQuit`/`quitAnyway`/`finishQuit`:
   quit-during-job semantics and the only force-kill path; a wrong `jobRunning` read either kills
   a running job or hangs the quit — `AppModelTests.testQuitWhileAJobRunsOffersQuitAnyway`,
   `testQuitMidDownloadLeavesTheBannerAndNoAutomaticRetry` (model level).
7. `app/Sources/OhYesMLX/OhYesMLXApp.swift:88-95` — `applicationShouldTerminate`
   (`.terminateLater` + `requestQuit` Task): the AppKit side of the quit handshake; a missed
   `reply(toApplicationShouldTerminate:)` leaves a zombie window or kills early — **none at the
   AppKit layer** (model-level tests only).
8. `AppModel.swift:607-666` — `start`: the one-slot funnel and `inflightJob` write; the crash
   record ("what was interrupted") is only as good as the clear-on-done/error bookkeeping here —
   `AppModelTests.testHappyPathInstallDownloadBenchmark`, `testQuitMidDownloadLeavesTheBanner…`,
   `testRetryResendsTheJobAndDismissClearsIt`.
9. `AppModel.swift:668-712` — `apply`: every state transition of a job (done/error/result), the
   restoreFailed-only failure rule, summary attach and inflight clear —
   `testADownloadAfterARestoreFailedQuickbenchStillFinishes`,
   `testACancelledSummaryTypesAndKeepsItsRawBytes`,
   `testTheSummaryReplacesLiveCellsInTheResultsRows`,
   `testAPayloadThatIsNotASummaryLeavesTheTypedValueEmpty`.
10. `AppModel.swift:517-529` — `cancelJob`: stop-now/stop-after-cell states; contains an await
    gap where event state can interleave (see §7 Q4) — `AppModelTests.testCancelModesSetTheirMessages`,
    `testTheRunningScenarioHasItsStopControlsAndLiveCells`.
11. `AppModel.swift:531-539` — `backendExited`: the backend-crash state transition (job →
    .interrupted, screen → backend-stopped) — `LauncherTests.testChildExitWhileRunningReportsStatusAndTheStderrTail`
    + the `backend-stopped` scenario (`testEveryStubScenarioReachesItsScreen`); no direct
    AppModel-level crash test found.
12. `app/Sources/OhYesMLXKit/HTTPBackend.swift:171-192` — `makeRequest`: the only `token.raw`
    reader (P5-1); also builds every wire request —
    `HTTPBackendTests.testHardwareRequestCarriesOnlyTheBearerHeader`,
    `testTokenIsRedactedInEveryDescription`.
13. `HTTPBackend.swift:110-162` — `events`: SSE reconnect/`Last-Event-ID`/poison-skip loop; a
    regression pins the job running or replays events —
    `HTTPBackendTests.testEventsResumeAfterADroppedStream`,
    `testAPoisonEventIsSkippedAndItsIDIsNeverFetchedAgain`,
    `testUnknownJobEndsTheStreamWithoutReconnecting`.
14. `app/Sources/OhYesMLXKit/Models.swift:499-505` — `JobEvent.payloadData`: the export bytes
    (D8 semantics — re-serialisation, not the wire's); misleading copy here re-opens the w2 #3
    finding — `DecodingTests.testPayloadDataKeepsKeysTheTypedSummaryDoesNotModel`,
    `testPayloadDataKeepsIntegersAsIntegers`.
15. `Models.swift:12-35` — `JSONValue.init(from:)`: integer fidelity for byte counts
    (`Int64`); a Double round-trip would corrupt sizes in the UI —
    `DecodingTests.testHardwareDecodesWithInt64ByteCounts`,
    `testPayloadDataKeepsIntegersAsIntegers`.
16. `AppModel.swift:775-791` — `writeInflight`/`loadInflight`: the interrupted-job record
    (UserDefaults); a stale entry manufactures a false banner, a lost one hides a real
    interruption — `AppModelTests.testQuitMidDownloadLeavesTheBannerAndNoAutomaticRetry`,
    `testRetryResendsTheJobAndDismissClearsIt`.
17. `AppModel.swift:740-760` — `updateBenchmarkCell`: live-cell identity ("stage/engine/format");
    the w1 data-loss bug lived here — `AppModelTests.testTwoStageBSiblingsStayTwoRows`,
    `testAStageBAbortedRowCarriesItsReasonFromThePayload`.
18. `AppModel.swift:491-510` — `planBenchmark`: plan/request identity (the w2 race); a stale
    plan lets Start Benchmark run the wrong repo —
    `AppModelTests.testASlowPlanForThePreviousPickIsDropped`,
    `testPlanningStartsNothingAndStartRunsThePlannedRepo`.
19. `app/Sources/OhYesMLX/Screens/ResultsView.swift:195-209` — `export()`: the only file write in
    the app (NSSavePanel); writes the summary the user believes is the record — **none** (no test
    exercises the panel path).
20. `app/Sources/OhYesMLXKit/StubBackend.swift:938-1020` — `StubScenario.makeModel`/`drive`: the
    entire UI-state proof rests on these fixtures driving real event flows (w2 confirmed they do,
    not screen-setting) — `AppModelTests.testEveryStubScenarioReachesItsScreen` and the scenario
    tests :1080-1170.

## 5. Mechanical scan

Patterns from the order; grep over `app/Sources/**` + `app/Package.swift` (no Python in scope,
so the Python list is "no hits — Swift-only scope" across the board).

Python patterns (`shell=True`, `os.system`, `eval(`, `exec(`, `pickle`, bare `except:`,
`except Exception: pass`, `chmod`, `tempfile.mktemp`, `open(..., "w")` on input-built paths,
`subprocess` without timeout, `json.loads` unbounded): **none — no Python files in scope.**

Swift — requested patterns:

- `try!` — none.
- `!` force-unwrap on optionals from I/O — none found (regex `\)!|\]!|url!|data!|first!|last!|as!`
  is empty across `app/Sources`; all handle/URL/data optionals are `guard`/`if let`).
- `fatalError` — none.
- `DispatchQueue.main.sync` — none (no `DispatchQueue.main` at all).
- `@unchecked Sendable` — `BackendLauncher.swift:52` (FoundationLauncherProcess), `:113`
  (BackendLauncher), `:277` (LaunchSession), `:530` (RunningBackend), `StubBackend.swift:33`
  (StubBackend). All five guard state with `NSLock` (`LaunchSession`/`BackendLauncher` via
  `lock`, `StubBackend` likewise) — listed, not judged.
- `Task {` without cancellation handling — `RootView.swift:12, 22, 51, 63, 68`;
  `ModelsView.swift:65, 69, 189, 238`; `BenchmarkView.swift:29, 67, 74, 83, 245`;
  `EnginesView.swift:58, 76`; `OhYesMLXApp.swift:37, 91`; `AppModel.swift:595`;
  `StubBackend.swift:969, 981, 994`. (The two in `HTTPBackend.swift:36, 112` DO handle
  cancellation: `continuation.onTermination = { task.cancel() }` and `Task.isCancelled` checks.)
- `print(` — none.
- `Color(` literal initializers — none (`StatusGlyph.swift:20-25` uses semantic `.green`,
  `.orange`, `.red`, `.secondary`).

Swift — extra S3 patterns:

- `@MainActor` — `AppModel.swift:155` (AppModel), `AppModel.swift:595` (`Task { @MainActor in`),
  `StubBackend.swift:938` (StubScenario extension), `OhYesMLXApp.swift:76` (AppDelegate),
  `OhYesMLXApp.swift:91` (`Task { @MainActor in`), `RootView.swift:234, 245` (SidebarItem
  methods).
- `nonisolated` — none.
- `Task.detached` — none.
- `await` inside `withLock` — none (every `withLock` is `NSLock`'s synchronous closure —
  40+ call sites in `BackendLauncher.swift`/`StubBackend.swift`, all non-async; an `await` there
  would not compile).
- `DispatchQueue` — `BackendLauncher.swift:320, 325` (drain threads),
  `:348` (launch-line timeout), `:552` (quitWait off the main actor). All `.global`, never
  `.main`.
- `Process(` — `BackendLauncher.swift:53` (the one `Process()` instance, FoundationLauncherProcess).
- `terminationHandler` — `BackendLauncher.swift:75` (set), `:79` (cleared).
- `FileHandle` — `BackendLauncher.swift:33-35` (protocol), `:64-68` (props), `:372` (stdin close),
  `:417` (readLines drain).
- `UserDefaults` — `AppModel.swift:210, 221, 235` (inflightJob persistence),
  `StubBackend.swift:941` (stub suite `ohyesmlx.stub.scenario`).
- `NSSavePanel` — `ResultsView.swift:197`.
- `accessibility` — `RootView.swift:87`; `ModelsView.swift:136, 137, 218, 225, 241, 247, 295`;
  `BenchmarkView.swift:250`; `EnginesView.swift:119, 120, 150, 151, 160, 171, 195, 203`;
  `FullWindowStates.swift:144`; `ResultsView.swift:256`; `StatusGlyph.swift:52`.
- `.help(` — `BenchmarkView.swift:79, 88`.
- `String(format:` — `Format.swift:28, 40` only (the AC-1 grep gate passes on the current tree).
- `Color(` — none (see above).

## 6. Test inventory

One line per hotspot (§4 numbering); suite is `app/Tests/OhYesMLXKitTests/` run via
`cd app && OYMLX_DEV_PYTHON=$HOME/.local/share/ohyesmlx/app-dev-venv/bin/python swift test`
(coordinator runs it; nothing was run for this dossier).

1. Launcher.start/launch line — `LauncherTests.swift::testArgvEnvironmentAndDirectory`,
   `::testTheFirstStdoutLineIsTheLaunchLineWhenTwoArriveBeforeTheAwait`,
   `::testEOFBeforeTheLaunchLineIsCouldntStartWithTheStderrTail`,
   `::testNoLaunchLineWithinTheTimeoutIsCouldntStart`.
2. deliverLine first-line rule — `LauncherTests.swift::testTheFirstStdoutLineIsTheLaunchLineWhenTwoArriveBeforeTheAwait`,
   `::testChattyStderrStillYieldsTheLaunchLine`, `::testStdoutAfterTheLaunchLineIsDrainedAndDiscarded`.
3. childEnvironment — `LauncherTests.swift::testArgvEnvironmentAndDirectory`
   (argv, env keys, directory asserted).
4. quitWait escalation — `LauncherTests.swift::testQuitWhileAJobRunsClosesStdinAndNeverSignals`,
   `::testQuitEscalatesGraceThenTerminateThenKill`, `::testQuitReturnsTerminatedWhenSigtermStopsTheBackend`,
   `::testQuitReturnsExitedWhenTheBackendStopsItself`.
5. single instance — `LauncherTests.swift::testSecondLauncherIsAlreadyRunningAndSpawnsNothing`.
6. requestQuit/quitAnyway — `AppModelTests.swift::testQuitWhileAJobRunsOffersQuitAnyway`,
   `::testQuitMidDownloadLeavesTheBannerAndNoAutomaticRetry`,
   `::testRetryResendsTheJobAndDismissClearsIt`.
7. applicationShouldTerminate — **none** (AppKit glue untested; the model side is item 6).
8. start funnel/inflight — `AppModelTests.swift::testHappyPathInstallDownloadBenchmark`,
   `::testQuitMidDownloadLeavesTheBannerAndNoAutomaticRetry`,
   `::testRetryResendsTheJobAndDismissClearsIt`,
   `::testATranslocatedBundleAsksForApplicationsAndStartsNoJob`.
9. apply state machine — `AppModelTests.swift::testADownloadAfterARestoreFailedQuickbenchStillFinishes`,
   `::testACancelledSummaryTypesAndKeepsItsRawBytes`,
   `::testTheSummaryReplacesLiveCellsInTheResultsRows`,
   `::testAPayloadThatIsNotASummaryLeavesTheTypedValueEmpty`,
   `::testCancelModesSetTheirMessages`, `::testQuickbenchCellsCarrySkippedAndMissingBinaryRows`.
10. cancelJob — `AppModelTests.swift::testCancelModesSetTheirMessages`,
    `::testTheRunningScenarioHasItsStopControlsAndLiveCells` (model level; the double-cancel
    interleaving in §7 Q4 has **no** test).
11. backendExited — `LauncherTests.swift::testChildExitWhileRunningReportsStatusAndTheStderrTail`
    (runner level) + `AppModelTests.swift::testEveryStubScenarioReachesItsScreen`
    (backend-stopped scenario); no direct AppModel crash-transition test.
12. makeRequest/token — `HTTPBackendTests.swift::testHardwareRequestCarriesOnlyTheBearerHeader`,
    `::testTokenIsRedactedInEveryDescription`.
13. events loop — `HTTPBackendTests.swift::testEventsResumeAfterADroppedStream`,
    `::testAPoisonEventIsSkippedAndItsIDIsNeverFetchedAgain`,
    `::testUnknownJobEndsTheStreamWithoutReconnecting`.
14. payloadData — `DecodingTests.swift::testPayloadDataKeepsKeysTheTypedSummaryDoesNotModel`,
    `::testPayloadDataKeepsIntegersAsIntegers`; export panel path itself: **none**.
15. JSONValue integers — `DecodingTests.swift::testHardwareDecodesWithInt64ByteCounts`,
    `::testPayloadDataKeepsIntegersAsIntegers`.
16. inflight persistence — `AppModelTests.swift::testQuitMidDownloadLeavesTheBannerAndNoAutomaticRetry`,
    `::testRetryResendsTheJobAndDismissClearsIt`.
17. updateBenchmarkCell — `AppModelTests.swift::testTwoStageBSiblingsStayTwoRows`,
    `::testAStageBAbortedRowCarriesItsReasonFromThePayload`,
    `::testQuickbenchCellsCarrySkippedAndMissingBinaryRows`.
18. planBenchmark race — `AppModelTests.swift::testASlowPlanForThePreviousPickIsDropped`,
    `::testPlanningStartsNothingAndStartRunsThePlannedRepo`,
    `::testAPlanRefusalNamesTheBackendMessageAndStartsNothing`.
19. export() — **none**.
20. StubScenario fixtures — `AppModelTests.swift::testEveryStubScenarioReachesItsScreen`,
    `::testTheRunningScenarioHasItsStopControlsAndLiveCells`,
    `::testTheFinishedResultsScenarioShowsABestAndTheCancelledOneDoesNot`,
    `::testTheDownloadingScenarioExposesTheByteCounters`,
    `::testTheLowDiskScenarioCarriesTheRefusalsOwnNumbers`.

Supporting suites: `SSETests.swift` (framing), `FormatTests.swift` (all five Format forms),
`DecodingTests.swift` (every pinned shape incl. missing-key failure), `LiveBackendTests.swift`
(one live round trip, presumably integration), `Fixtures.swift` (shared JSON fixtures).

Gaps worth naming: the AppKit quit handshake (7), the export write (19), the cancelJob
interleaving (10), the AppModel-level backend-crash transition (11), and every visual/a11y claim
(DESIGN §4.3/§5) — none of those have runnable checks; the coordinator's screenshot pass
(`OYMLX_STUB_SCENARIO` states, light/dark) is their only guard.

## 7. Open questions for the reviewer

1. **Two quick clicks on a job-starting control open a window before the slot is claimed.**
   `AppModel.start` sets `job` only after `try await backend.startJob` returns
   (`AppModel.swift:627-637`); until then `oneSlotReason`/`canStartJob` still say idle
   (`:263-271`). Two fast clicks on Download (Models) or Start Benchmark produce two `start()`
   calls and two `POST /jobs`; the loser gets `409 busy`, which `start()` writes to the global
   `refusal` (`:628-631`) — and `model.refusal` renders **only** in `EnginesView.swift:17`. On
   Models/Benchmark the user sees nothing, against v5-app Q1 ("A `409 busy` that still arrives is
   shown as the backend's message"). Falsifiable: double-click Download on Models with a stubbed
   slow `startJob`; watch a `409` refusal land where no view reads it. Is a click-time
   "starting" state (or routing `refusal` per screen) intended?
2. **Backend crash while "Quit anyway" is offered erases the quit path.** Sequence: quit with a
   job → `quitWait` returns `.stillRunning` → `quitAnywayOffered = true` (`AppModel.swift:568-572`)
   → backend crashes anyway → `backendExited` (`:531-539`) sets `backendStopped` → `RootView`
   `:9-12` swaps the whole window for `BackendStoppedStateView`, whose only actions are Relaunch
   and Copy Details; the "Quit anyway" banner (`RootView.swift:142-155`) is unreachable. The
   user asked to quit and is now offered a relaunch. (A Cmd-Q from that state still exits
   cleanly: `requestQuit` finds the process already dead and finishes.) Falsifiable:
   drive the `backend-stopped` scenario after a still-running quit. Intended terminal state?
3. **Quit during each job kind — Retry semantics differ per kind, and install skips the consent
   gate.** `retryInterrupted` (`AppModel.swift:546-560`) calls `start(.install(engine:))`
   directly, bypassing the `installConsent` check `install(engine:)` enforces (`:463-469`); the
   consent flag is never persisted. v5-app Q2 says Retry "re-sends the same job after a fresh
   user click" — so is the Retry click itself the consent, or should the consent sheet re-open
   after a relaunch (the app restarted since consent was given)? Related: quit-mid-quickbench
   Retry re-plans first (`quickbench(repo:)`), so a catalog change while quit turns the
   interruption into a plan refusal with the banner already dismissed (`:549`) — the record is
   lost. Falsifiable: set `installConsent = false`, seed `inflightJob` with an install, call
   `retryInterrupted`.
4. **Two quick clicks on the stop controls race an in-flight `cancel` against events.**
   `cancelJob` (`AppModel.swift:517-529`) snapshots `current = job`, awaits
   `backend.cancel(...)`, then writes `job = status` from the **pre-await** snapshot. If a `done`
   event lands during that await, `apply` sets the finished state first and the stale write then
   re-pins the job to `.stopping…` — and no further events arrive (the stream ended with the
   `done`), so the row stays "Stopping…" forever. Second click ("Stop Now" after "Stop after this
   cell") passes the `isActive` guard and sends a second cancel that may earn
   `409 job_finished`/`not_cancellable` → global `refusal` again (see Q1).
   Falsifiable: a stub whose `cancel` suspends while a scripted `done` arrives. Should
   `cancelJob` re-read `job` after the await (or set the stopping state before it)?
5. **"Best on your Mac" claims more than a quick run measured.** `ResultsView.swift:92` labels
   the summary's winner "Best on your Mac", while the badge beneath it says "quick: measured on
   this Mac" — the pinned label (v5-quickbench.md:145) that admits the measurement is a short
   quickbench. Everything measured is one 5-iteration run of one model on one day; "Best on your
   Mac" reads as a standing claim. The `estimated` badges on Time/Free-disk-after
   (`BenchmarkView.swift:194-205`) are correctly scoped; the Models row's
   "quick: measured on this Mac" (`ModelsView.swift:131`) likewise. Is the Results heading the
   one over-claim, or is it meant as "best on your Mac [from this run]" with the caveat section
   carrying the scope (the stage caveats are rendered, `ResultsView.swift:124-163`)? Related
   minor: "Now running" (`BenchmarkView.swift:285`) shows the first *unlanded planned* cell
   (`AppModel.nextBenchmarkCell:314-334`) — a guess while events are in flight, presented as
   fact.
6. **VoiceOver order and row semantics are inconsistent between the three row types.**
   `ResultCellRow` combines children (`ResultsView.swift:256`) and `ModelRow`/`EngineRow`
   compose a full `accessibilityLabel` (`ModelsView.swift:247-266`,
   `EnginesView.swift:203-215`) — but `BenchmarkCellRow` (`BenchmarkView.swift:327-347`) does
   neither: its stage·title, glyph word and figure are read as separate fragments, and its
   StatusGlyph is hidden (`StatusGlyph.swift:52`), so the row announces "PASS" without context.
   Also: the sidebar completion checkmark is `accessibilityHidden` (`RootView.swift:87`) with no
   "complete" in the item label, so step completion is silent; `DiskMeter`'s "set aside" caption
   (`ModelsView.swift:294-300`) has no a11y label while the gauge does (`:295`). Falsifiable:
   VoiceOver on the running Benchmark screen vs the Results screen. DESIGN §5 wants "the row as
   one element".
7. **Two sources of download progress can disagree on screen.** `apply` shows
   `event.fraction ?? status.fraction` in the progress bar (`AppModel.swift:672`) while
   `downloadProgress` (`:350-360`) renders `bytes_done/bytes_total` text from the latest payload
   carrying both keys (skipping later events that lack them). The backend pins the fraction as
   the same ratio (v5-onboarding.md:152), so this is duplication rather than divergence today —
   but if the two ever disagree (reused bytes, sidecar files), the bar and the text disagree
   visibly with no one definition deciding which is the number. Which is authoritative?
8. **The poison-frame skip depends on integer SSE ids.** `HTTPBackend.events` advances `last`
   past an undecodable frame only `if let frameID = parser.lastEventID, let id = Int(frameID)`
   (`HTTPBackend.swift:129-132`); a poison frame with no `id:` line (or a non-integer id) leaves
   `last` unadvanced and re-fetches it forever — exactly the w1 defect, still reachable at the
   edge. The server pin (v5-onboarding.md:122-125) implies ids are seq integers on every frame,
   so this holds while the backend honors the pin. Worth confirming the reviewer agrees the
   coupling is pinned (and whether a fixture for "poison frame without id:" should exist —
   `testAPoisonEventIsSkippedAndItsIDIsNeverFetchedAgain` sends frames **with** ids).



