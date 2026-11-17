import Foundation
import Observation

public enum Screen: Sendable, Equatable {
    case launching
    case couldntStart
    case unsupported
    /// macOS is running the app from its translocated, read-only copy; nothing may be installed.
    case moveToApplications
    case welcome
    case yourMac
    case engines
    case models
    case benchmark
    case results
}

public enum JobState: Sendable, Equatable {
    case running
    case stoppingAfterCell
    case stoppingNow
    case finished
    case failed
    case cancelled
    case interrupted

    public var text: String {
        switch self {
        case .running: return "Running"
        case .stoppingAfterCell: return "Stopping after this cell…"
        case .stoppingNow: return "Stopping…"
        case .finished: return "Finished"
        case .failed: return "Failed"
        case .cancelled: return "Cancelled"
        case .interrupted: return "Interrupted"
        }
    }

    public var isActive: Bool {
        self == .running || self == .stoppingAfterCell || self == .stoppingNow
    }
}

public struct JobStatus: Sendable, Equatable {
    public let id: String
    public let kind: JobKind
    public let name: String
    public var state: JobState
    public var fraction: Double
    public var message: String
    public var events: [JobEvent]

    public init(
        id: String,
        kind: JobKind,
        name: String,
        state: JobState,
        fraction: Double,
        message: String,
        events: [JobEvent]
    ) {
        self.id = id
        self.kind = kind
        self.name = name
        self.state = state
        self.fraction = fraction
        self.message = message
        self.events = events
    }
}

public struct LowDisk: Sendable, Equatable {
    public let freeBytes: Int64
    public let neededBytes: Int64

    public init(freeBytes: Int64, neededBytes: Int64) {
        self.freeBytes = freeBytes
        self.neededBytes = neededBytes
    }

    public var amountToFree: Int64 {
        max(0, neededBytes - freeBytes)
    }
}

public struct InterruptedJob: Sendable, Equatable {
    public let kind: JobKind
    public let name: String
    public let started: String

    public init(kind: JobKind, name: String, started: String) {
        self.kind = kind
        self.name = name
        self.started = started
    }
}

public struct BenchmarkCell: Sendable, Equatable, Identifiable {
    public let stage: String
    public let engine: String
    public let format: String
    public var status: String
    public var reason: String?
    public var decodeTPS: Double?
    public var ttftS: Double?
    public var runtimeVersion: String?

    public var id: String { "\(stage)/\(engine)/\(format)" }

    public init(
        stage: String,
        engine: String,
        format: String,
        status: String,
        reason: String?,
        decodeTPS: Double? = nil,
        ttftS: Double? = nil,
        runtimeVersion: String? = nil
    ) {
        self.stage = stage
        self.engine = engine
        self.format = format
        self.status = status
        self.reason = reason
        self.decodeTPS = decodeTPS
        self.ttftS = ttftS
        self.runtimeVersion = runtimeVersion
    }

    /// One summary cell in stage *stage*, which is the same row the live progress built.
    public init(stage: String, cell: QuickCell) {
        self.init(
            stage: stage,
            engine: cell.engine,
            format: cell.format,
            status: cell.status,
            reason: cell.reason,
            decodeTPS: cell.decodeTPS,
            ttftS: cell.ttftS,
            runtimeVersion: cell.runtimeVersion
        )
    }
}

public struct EngineFailure: Sendable, Equatable {
    public let code: String
    public let outputTail: String

    public init(code: String, outputTail: String) {
        self.code = code
        self.outputTail = outputTail
    }
}

@MainActor
@Observable
public final class AppModel {
    public private(set) var screen: Screen = .launching
    public private(set) var hardware: Hardware?
    public private(set) var engines: [EngineStatus] = []
    public private(set) var recommendations: Recommendations?
    public private(set) var quickPlan: QuickPlan?
    public private(set) var job: JobStatus?
    public private(set) var refusal: BackendError?
    public private(set) var benchmarkRefusal: BackendError?
    public private(set) var engineFailures: [String: EngineFailure] = [:]
    public private(set) var modelRefusals: [String: BackendError] = [:]
    public private(set) var lowDisk: [String: LowDisk] = [:]
    public private(set) var liveCells: [BenchmarkCell] = []
    public private(set) var summary: QuickSummary?
    /// Every field the summary's payload carried, re-serialised; that is what Export writes
    /// (AC-2, D8), so keys this client does not model survive into the file.
    public private(set) var summaryData: Data?
    public private(set) var interruptedJob: InterruptedJob?
    public private(set) var launchError: String?
    public private(set) var backendStopped: Int32?
    public private(set) var backendStderrTail: [String] = []
    public private(set) var quitInProgress = false
    public private(set) var quitAnywayOffered = false
    public private(set) var alreadyRunning = false
    /// `app.lock` is held by a backend with no app in front of it: the previous session is still
    /// unwinding (S3-F8). Shown on the couldn't-start screen with **Check again**.
    public private(set) var previousSessionFinishing = false
    public private(set) var shouldExit = false

    /// Retry's hand-off to the screens that own a gate: the Engines screen opens its consent
    /// sheet for this engine, and the Benchmark screen shows this repo's plan. Never a start.
    public var consentRequest: String?
    public var requestedBenchmarkRepo: String?

    public var installConsent = false
    public var osaurusConsent = false
    public var onQuitComplete: (() -> Void)?

    /// Q6's absolute gate: one definition, asked by every path that starts a job or a screen.
    public var unsupported: Bool { hardware?.supported == false }

    public var showsInterruptedBanner: Bool { interruptedJob != nil && !unsupported }

    // Step completion, as the sidebar ticks it off.

    public var yourMacComplete: Bool { hardware != nil }

    public var enginesComplete: Bool { engines.contains(where: \.installed) }

    public var modelsComplete: Bool { recommendations?.picks.contains(where: \.downloaded) ?? false }

    /// A finished quickbench is a tick even after a later job replaces `job`, and a row the
    /// backend marked measured here is the same fact from the other record.
    public var benchmarkComplete: Bool {
        if let summary, summary.ended == .finished { return true }
        return recommendations?.picks.contains { $0.measuredHere != nil } ?? false
    }

    private var backend: any Backend
    private var runner: (any BackendRunner)?
    private let launcher: BackendLauncher?
    private let defaults: UserDefaults
    private let bundlePath: String
    private let hardwareReadyTimeout: TimeInterval
    private let inflightKey = "inflightJob"
    /// The repo the newest plan request is for; a slower earlier response is dropped.
    private var planningRepo: String?
    /// The job a start is waiting on `POST /jobs` for: the slot is claimed synchronously, before
    /// the first await, so a second start cannot enter while the first is in the air (S3-F6).
    private var starting: JobArgs?
    /// The ending an `error` event recorded; `done` is what makes it the job's state (S3-F5).
    private var endedState: JobState?
    private var eventTask: Task<Void, Never>?

    public init(
        backend: any Backend,
        runner: (any BackendRunner)? = nil,
        launcher: BackendLauncher? = nil,
        defaults: UserDefaults = .standard,
        hardwareReadyTimeout: TimeInterval = 10,
        bundlePath: String = Bundle.main.bundlePath
    ) {
        self.backend = backend
        self.runner = runner
        self.launcher = launcher
        self.defaults = defaults
        self.bundlePath = bundlePath
        self.hardwareReadyTimeout = hardwareReadyTimeout
    }

    public convenience init(
        launcher: BackendLauncher,
        defaults: UserDefaults = .standard,
        hardwareReadyTimeout: TimeInterval = 10,
        bundlePath: String = Bundle.main.bundlePath
    ) {
        self.init(
            backend: PlaceholderBackend(),
            runner: nil,
            launcher: launcher,
            defaults: defaults,
            hardwareReadyTimeout: hardwareReadyTimeout,
            bundlePath: bundlePath
        )
    }

    /// Whether macOS is running this app from its App Translocation copy (AC-7, plan 05-06).
    ///
    /// A quarantined app opened where it was downloaded is run from a random read-only path
    /// under `/AppTranslocation/` that changes every launch. Engine venvs are made from
    /// `sys.executable` — a path inside the bundle — so a venv made in one such run points at
    /// an interpreter that is gone the next time. Nothing is spawned until the app is moved.
    static func isTranslocated(bundlePath: String) -> Bool {
        bundlePath.contains("/AppTranslocation/")
    }

    var translocated: Bool {
        Self.isTranslocated(bundlePath: bundlePath)
    }

    public var oneSlotReason: String? {
        if let starting {
            let name = starting.kind == .install ? starting.name : displayName(for: starting.name)
            return "Busy: starting \(starting.kind.wireName) \(name)"
        }
        guard let job, job.state.isActive else { return nil }
        let name = job.kind == .install ? job.name : displayName(for: job.name)
        return "Busy: \(job.kind.wireName) \(name) is running"
    }

    public var canStartJob: Bool {
        oneSlotReason == nil
    }

    public var notEvictedLines: [String] {
        (summary?.notEvicted ?? []).map { repo in
            let pick = recommendations?.picks.first { $0.modelID == repo }
            let title = pick?.title ?? repo
            let size = pick.map { Format.size($0.sizeBytes) } ?? "size unknown"
            return "Left on disk: \(title) (\(size)) — it was in use. You can remove it from Models."
        }
    }

    /// The results rows: the summary once it lands, the live progress before that.
    ///
    /// One source per phase, never both. Live cells are what the Benchmark screen shows as they
    /// land; a `result` replaces them with the summary's own cells, so the Results table and the
    /// record on disk say the same thing.
    public var benchmarkCells: [BenchmarkCell] {
        guard let summary else { return liveCells }
        return summary.stageA.cells.map { BenchmarkCell(stage: "A", cell: $0) }
            + summary.stageB.cells.map { BenchmarkCell(stage: "B", cell: $0) }
    }

    public var notEvicted: [String] { summary?.notEvicted ?? [] }

    /// The pick a busy reason names, so "Busy: download Qwen3.5 2B is running" is readable
    /// and a repo with no recommendation row still names the repo id (AC-6).
    public func displayName(for repo: String) -> String {
        recommendations?.picks.first { $0.modelID == repo }?.title ?? repo
    }

    /// An engine's plain-language title, for a plan or a cell row. Unknown names are shown as
    /// the backend wrote them.
    public func engineTitle(_ name: String) -> String {
        engines.first { $0.name == name }?.title ?? name
    }

    /// The cell a running benchmark is on: the first planned cell whose row has not landed.
    ///
    /// Derived, never guessed: the plan lists every cell in order and each one emits its own
    /// progress row when it is done, so the first planned cell with no row is the one in
    /// flight. A cell that was skipped emits a row too, so it stops being "next" as it should.
    /// Stage B's engine is read from a landed stage-B row when there is one; before that the
    /// winner is not the client's to name.
    public var nextBenchmarkCell: (title: String, detail: String)? {
        guard let plan = quickPlan, job?.kind == .quickbench, job?.state.isActive == true else {
            return nil
        }
        let landed = Set(liveCells.map(\.id))
        for planned in plan.stageA {
            if !landed.contains("A/\(planned.engine)/\(plan.format)") {
                return (engineTitle(planned.engine), "A · \(plan.format)")
            }
        }
        let stageBEngine = liveCells.first(where: { $0.stage == "B" })?.engine
        for sibling in plan.stageB {
            let id = stageBEngine.map { "B/\($0)/\(sibling.format)" }
            if id.map({ !landed.contains($0) }) ?? true {
                let detail = stageBEngine.map { "B · \(engineTitle($0))" } ?? "B"
                return (sibling.format, detail)
            }
        }
        return nil
    }

    /// The downloaded picks, the list the Benchmark screen chooses from.
    public var downloadedPicks: [Pick] {
        (recommendations?.picks ?? []).filter(\.downloaded)
    }

    /// The Benchmark screen's default: the first downloaded Start-here pick, else the first
    /// downloaded row, else nothing.
    public var defaultBenchmarkPick: Pick? {
        downloadedPicks.first(where: \.startHere) ?? downloadedPicks.first
    }

    /// The download's own byte counters from its latest progress payload (v5-onboarding.md).
    ///
    /// The backend sends `{"path", "bytes_done", "bytes_total"}` and the same pair as the
    /// event's `fraction`; the two numbers are shown as sent rather than recomputed here.
    public func downloadProgress(repo: String) -> (done: Int64, total: Int64)? {
        guard let job, job.kind == .download, job.name == repo else { return nil }
        for event in job.events.reversed() {
            guard let payload = event.payload,
                  let done = payload["bytes_done"]?.intValue,
                  let total = payload["bytes_total"]?.intValue
            else { continue }
            return (done, total)
        }
        return nil
    }

    public func launch() async {
        // AC-7: checked before anything is spawned, because the venvs it would make point at a
        // bundle path that is gone the next launch.
        guard !translocated else {
            screen = .moveToApplications
            return
        }
        if runner == nil, let launcher {
            switch await launcher.start() {
            case .couldntStart(let message):
                launchError = message
                screen = .couldntStart
                return
            case .alreadyRunning:
                alreadyRunning = true
                return
            case .stillFinishing:
                previousSessionFinishing = true
                screen = .couldntStart
                return
            case .running(let running):
                adopt(running)
            }
        }
        interruptedJob = loadInflight()
        await reload()
    }

    public func relaunch() async {
        guard !translocated else {
            screen = .moveToApplications
            return
        }
        guard let launcher else { return }
        previousSessionFinishing = false
        // S3-F7: a live backend is never spawned over; the retry is a reload against it.
        if let runner, runner.isRunning {
            screen = .launching
            await reload()
            return
        }
        backendStopped = nil
        backendStderrTail = []
        quitAnywayOffered = false
        job = nil
        screen = .launching
        switch await launcher.start() {
        case .couldntStart(let message):
            launchError = message
            screen = .couldntStart
        case .alreadyRunning:
            alreadyRunning = true
        case .stillFinishing:
            previousSessionFinishing = true
            screen = .couldntStart
        case .running(let running):
            adopt(running)
            interruptedJob = loadInflight()
            await reload()
        }
    }

    public func reload() async {
        let deadline = Date().addingTimeInterval(hardwareReadyTimeout)
        while true {
            do {
                hardware = try await backend.hardware()
                break
            } catch let error as BackendError {
                if Date() >= deadline {
                    refusal = error
                    launchError = error.message
                    screen = .couldntStart
                    return
                }
            } catch {
                if Date() >= deadline {
                    launchError = error.localizedDescription
                    screen = .couldntStart
                    return
                }
            }
            try? await Task.sleep(for: .milliseconds(100))
        }
        do {
            engines = try await backend.engines()
            recommendations = try await backend.recommendations()
            screen = hardware?.supported == true ? .welcome : .unsupported
        } catch let error as BackendError {
            refusal = error
            launchError = error.message
            screen = .couldntStart
        } catch {
            launchError = error.localizedDescription
            screen = .couldntStart
        }
    }

    public func go(to target: Screen) {
        guard !unsupported else { return }
        screen = target
    }

    public func appBecameActive() async {
        await refreshEngines()
    }

    public func enginesScreenAppeared() async {
        await refreshEngines()
    }

    public func checkEnginesAgain() async {
        await refreshEngines()
    }

    public func install(engine: String) async {
        guard installConsent else {
            refusal = BackendError(code: "bad_args", status: 400, message: "confirmed must be true")
            return
        }
        await start(.install(engine: engine))
    }

    public func download(repo: String) async {
        await start(.download(repo: repo))
    }

    public func evict(repo: String) async {
        await start(.evict(repo: repo))
    }

    public func quickbench(repo: String) async {
        guard await planBenchmark(repo: repo) else { return }
        await startBenchmark()
    }

    /// The plan for *repo*, and nothing started: the Benchmark screen shows this first (D4).
    ///
    /// The previous plan is kept until the new one arrives, so a Start pressed while a plan is
    /// being re-fetched runs the plan on screen rather than finding none. A response that
    /// arrives after the picker has moved on belongs to a plan that is no longer selected, so
    /// it is dropped rather than replacing the newer one.
    @discardableResult
    public func planBenchmark(repo: String) async -> Bool {
        guard !unsupported else { return false }
        benchmarkRefusal = nil
        planningRepo = repo
        do {
            let plan = try await backend.quickbenchPlan(repo: repo)
            guard planningRepo == repo else { return false }
            quickPlan = plan
            return true
        } catch let error as BackendError {
            guard planningRepo == repo else { return false }
            quickPlan = nil
            refusal = error
            benchmarkRefusal = error
            return false
        } catch {
            guard planningRepo == repo else { return false }
            quickPlan = nil
            benchmarkRefusal = BackendError(
                code: "plan_failed",
                status: nil,
                message: "Could not work out the plan: \(error.localizedDescription)"
            )
            return false
        }
    }

    /// Run the plan already on screen. A plan that is not there is a refusal, never a run.
    public func startBenchmark() async {
        guard let quickPlan else { return }
        await start(.quickbench(repo: quickPlan.repo, osaurus: osaurusConsent))
    }

    public func cancelJob(now: Bool) async {
        guard let current = job, current.state.isActive, current.state != .stoppingNow else {
            return
        }
        do {
            try await backend.cancel(jobID: current.id, now: now)
            // The await let events in: re-read, and mark stopping only a job that is still the
            // same one and still active (S3-F4). Stop Now escalates; Stop After never demotes.
            guard var latest = job, latest.id == current.id, latest.state.isActive else { return }
            if now {
                latest.state = .stoppingNow
            } else if latest.state == .running {
                latest.state = .stoppingAfterCell
            }
            job = latest
        } catch let error as BackendError {
            refusal = error
        } catch {
            return
        }
    }

    public func backendExited(status: Int32, stderrTail: [String]) {
        guard !quitInProgress else { return }
        backendStopped = status
        backendStderrTail = stderrTail
        eventTask?.cancel()
        if var current = job, current.state.isActive {
            current.state = .interrupted
            job = current
        }
        // The app was asked to quit and offered "Quit anyway"; the backend is gone, so the
        // quit is complete rather than stranded behind the backend-stopped screen (S3-F12).
        if quitAnywayOffered {
            finishQuit()
        }
    }

    public func dismissInterrupted() {
        interruptedJob = nil
        defaults.removeObject(forKey: inflightKey)
    }

    public func retryInterrupted() async {
        guard !unsupported else { return }
        guard let interrupted = interruptedJob else { return }
        interruptedJob = nil
        // Retry goes through the gate the button has, never straight to a start (S3-F15):
        // install asks for consent, evict is confirmed on Models, a benchmark shows its plan.
        switch interrupted.kind {
        case .install:
            if installConsent {
                await start(.install(engine: interrupted.name))
            } else {
                consentRequest = interrupted.name
                go(to: .engines)
            }
        case .download:
            await start(.download(repo: interrupted.name))
        case .evict:
            go(to: .models)
        case .quickbench:
            if downloadedPicks.contains(where: { $0.modelID == interrupted.name }) {
                requestedBenchmarkRepo = interrupted.name
            }
            go(to: .benchmark)
            await planBenchmark(repo: interrupted.name)
        }
    }

    public func requestQuit() async {
        guard !quitInProgress, !shouldExit else { return }
        quitInProgress = true
        guard let runner else {
            finishQuit()
            return
        }
        let jobRunning = job?.state.isActive == true
        let outcome = await runner.quit(jobRunning: jobRunning)
        if outcome == .stillRunning {
            quitInProgress = false
            quitAnywayOffered = true
            return
        }
        finishQuit()
    }

    public func quitAnyway() {
        runner?.forceKill()
        finishQuit()
    }

    private func finishQuit() {
        quitInProgress = false
        quitAnywayOffered = false
        shouldExit = true
        onQuitComplete?()
    }

    private func adopt(_ running: RunningBackend) {
        runner = running
        backend = HTTPBackend(port: running.endpoint.port, token: running.endpoint.token)
        running.onExit = { [weak self] status, tail in
            Task { @MainActor in
                self?.backendExited(status: status, stderrTail: tail)
            }
        }
    }

    private func refreshEngines() async {
        if let value = try? await backend.engines() {
            engines = value
        }
    }

    private func start(_ args: JobArgs) async {
        // AC-7: no job can start from a translocated bundle, whatever the screen says.
        guard !unsupported, !translocated else { return }
        // The slot is claimed here, before the first await (S3-F6).
        if let reason = oneSlotReason {
            routeStartRefusal(BackendError(code: "busy", status: nil, message: reason), args: args)
            return
        }
        refusal = nil
        starting = args

        let jobID: String
        do {
            jobID = try await backend.startJob(kind: args.kind, args: args)
        } catch let error as BackendError {
            starting = nil
            routeStartRefusal(error, args: args)
            return
        } catch {
            starting = nil
            routeStartRefusal(
                BackendError(code: "start_failed", status: nil, message: error.localizedDescription),
                args: args
            )
            return
        }

        // The POST succeeded, so the slot is the backend's now: only here does the per-kind
        // reset and the crash record happen.
        if args.kind == .quickbench {
            benchmarkRefusal = nil
            liveCells = []
            summary = nil
            summaryData = nil
        } else if args.kind == .install {
            engineFailures[args.name] = nil
        } else {
            modelRefusals[args.name] = nil
        }
        writeInflight(
            InterruptedJob(
                kind: args.kind,
                name: args.name,
                started: ISO8601DateFormatter().string(from: Date())
            )
        )
        endedState = nil
        job = JobStatus(
            id: jobID,
            kind: args.kind,
            name: args.name,
            state: .running,
            fraction: 0,
            message: "",
            events: []
        )
        starting = nil
        if args.kind == .quickbench {
            screen = .benchmark
        }

        let stream = backend.events(jobID: jobID, after: nil)
        let task = Task { [weak self] in
            do {
                for try await event in stream {
                    guard let self else { return }
                    await self.apply(event, jobID: jobID, args: args)
                    if event.type == .done { break }
                }
            } catch let error as BackendError {
                self?.refusal = error
            } catch {
                // The stream ended without its `done`; the job's own state already says what it
                // did, and the recommendations below are still asked for.
            }
        }
        eventTask = task
        await task.value
        // AC-6: a download or an evict changes what is on disk, so the step ticks and the
        // Benchmark picker are re-read from the backend rather than left on stale rows.
        // The free-disk figure moves with them (S3-F10), so the hardware is re-read too.
        if args.kind == .download || args.kind == .evict {
            await refreshRecommendations()
            await refreshHardware()
        }
    }

    /// A refused start is shown on the screen that asked for it, and also in `refusal`, which
    /// Engines renders (S3-F6).
    private func routeStartRefusal(_ error: BackendError, args: JobArgs) {
        refusal = error
        switch args.kind {
        case .quickbench: benchmarkRefusal = error
        case .download, .evict: modelRefusals[args.name] = error
        case .install: break
        }
    }

    private func apply(_ event: JobEvent, jobID: String, args: JobArgs) async {
        guard var status = job, status.id == jobID else { return }
        status.events.append(event)
        status.fraction = event.fraction ?? status.fraction
        status.message = event.message

        switch event.type {
        case .done:
            if status.state.isActive {
                // The backend holds its one slot until `done`, so this is where the job ends
                // (S3-F5). `error` recorded how; a pinned Osaurus whose restore failed also
                // sends `error` (code restore_failed), and its summary says so too. Any other
                // kind's completion is its own, never a summary it did not write.
                let restoreFailed =
                    status.kind == .quickbench && summary?.ended == .restoreFailed
                status.state = endedState ?? (restoreFailed ? .failed : .finished)
            }
            job = status
            defaults.removeObject(forKey: inflightKey)
            if args.kind == .quickbench {
                screen = .results
            }
            return
        case .error:
            let code = event.payload?["code"]?.stringValue
            endedState = code == "cancelled" ? .cancelled : .failed
            let error = BackendError(code: code ?? "error", status: nil, message: event.message)
            refusal = error
            route(error: error, event: event, args: args)
            job = status
            return
        case .result:
            // Only a quickbench's result is the run's summary; a download's or an evict's is
            // its own receipt and must not replace it (S3-F2).
            if args.kind == .quickbench {
                summaryData = event.payloadData
                summary = summaryData.flatMap {
                    try? JSONDecoder().decode(QuickSummary.self, from: $0)
                }
            }
        case .progress:
            if args.kind == .quickbench {
                updateBenchmarkCell(event)
            }
        case .log:
            break
        }
        job = status
    }

    private func route(error: BackendError, event: JobEvent, args: JobArgs) {
        switch args.kind {
        case .install:
            if error.code == "step_failed" {
                engineFailures[args.name] = EngineFailure(
                    code: error.code,
                    outputTail: event.payload?["output_tail"]?.stringValue ?? ""
                )
            }
        case .download:
            modelRefusals[args.name] = error
            if error.code == "low_disk",
               let free = event.payload?["free_bytes"]?.intValue,
               let needed = event.payload?["needed_bytes"]?.intValue {
                lowDisk[args.name] = LowDisk(freeBytes: free, neededBytes: needed)
            }
        case .evict:
            modelRefusals[args.name] = error
        case .quickbench:
            // A cancel is an ending, not a plan refusal: keeping it here would replace the
            // plan with a refusal banner when the user comes back to Benchmark (AC-4).
            if error.code != "cancelled" {
                benchmarkRefusal = error
            }
        }
    }

    private func updateBenchmarkCell(_ event: JobEvent) {
        guard let payload = event.payload,
              let stage = payload["stage"]?.stringValue,
              let engine = payload["engine"]?.stringValue,
              let format = payload["format"]?.stringValue,
              let status = payload["status"]?.stringValue
        else { return }

        let cell = BenchmarkCell(
            stage: stage,
            engine: engine,
            format: format,
            status: status,
            reason: payload["reason"]?.stringValue
        )
        if let index = liveCells.firstIndex(where: { $0.id == cell.id }) {
            liveCells[index] = cell
        } else {
            liveCells.append(cell)
        }
    }

    private func refreshHardware() async {
        if let value = try? await backend.hardware() {
            hardware = value
        }
    }

    /// AC-6: the recommendations are re-read after a download or evict, and when Models opens.
    public func refreshRecommendations() async {
        if let value = try? await backend.recommendations() {
            recommendations = value
        }
    }

    private func writeInflight(_ job: InterruptedJob) {
        defaults.set(
            ["kind": job.kind.wireName, "name": job.name, "started": job.started],
            forKey: inflightKey
        )
    }

    private func loadInflight() -> InterruptedJob? {
        guard let object = defaults.dictionary(forKey: inflightKey),
              let kindName = object["kind"] as? String,
              let kind = JobKind(wireName: kindName),
              let name = object["name"] as? String,
              let started = object["started"] as? String
        else { return nil }
        return InterruptedJob(kind: kind, name: name, started: started)
    }
}

private struct PlaceholderBackend: Backend {
    func hardware() async throws -> Hardware {
        throw URLError(.cannotConnectToHost)
    }

    func engines() async throws -> [EngineStatus] {
        throw URLError(.cannotConnectToHost)
    }

    func recommendations() async throws -> Recommendations {
        throw URLError(.cannotConnectToHost)
    }

    func quickbenchPlan(repo: String) async throws -> QuickPlan {
        throw URLError(.cannotConnectToHost)
    }

    func startJob(kind: JobKind, args: JobArgs) async throws -> String {
        throw URLError(.cannotConnectToHost)
    }

    func cancel(jobID: String, now: Bool) async throws {
        throw URLError(.cannotConnectToHost)
    }

    func events(jobID: String, after: Int?) -> AsyncThrowingStream<JobEvent, Error> {
        AsyncThrowingStream { $0.finish() }
    }
}
