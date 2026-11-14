import Foundation
import Observation

public enum Screen: Sendable, Equatable {
    case launching
    case couldntStart
    case unsupported
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
    /// The summary exactly as the backend sent it, which is what Export writes (AC-2, D8).
    public private(set) var summaryData: Data?
    public private(set) var interruptedJob: InterruptedJob?
    public private(set) var launchError: String?
    public private(set) var backendStopped: Int32?
    public private(set) var backendStderrTail: [String] = []
    public private(set) var quitInProgress = false
    public private(set) var quitAnywayOffered = false
    public private(set) var alreadyRunning = false
    public private(set) var shouldExit = false

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

    public var benchmarkComplete: Bool { job?.kind == .quickbench && job?.state == .finished }

    private var backend: any Backend
    private var runner: (any BackendRunner)?
    private let launcher: BackendLauncher?
    private let defaults: UserDefaults
    private let hardwareReadyTimeout: TimeInterval
    private let inflightKey = "inflightJob"

    public init(
        backend: any Backend,
        runner: (any BackendRunner)? = nil,
        launcher: BackendLauncher? = nil,
        defaults: UserDefaults = .standard,
        hardwareReadyTimeout: TimeInterval = 10
    ) {
        self.backend = backend
        self.runner = runner
        self.launcher = launcher
        self.defaults = defaults
        self.hardwareReadyTimeout = hardwareReadyTimeout
    }

    public convenience init(
        launcher: BackendLauncher,
        defaults: UserDefaults = .standard,
        hardwareReadyTimeout: TimeInterval = 10
    ) {
        self.init(
            backend: PlaceholderBackend(),
            runner: nil,
            launcher: launcher,
            defaults: defaults,
            hardwareReadyTimeout: hardwareReadyTimeout
        )
    }

    public var oneSlotReason: String? {
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
        if runner == nil, let launcher {
            switch await launcher.start() {
            case .couldntStart(let message):
                launchError = message
                screen = .couldntStart
                return
            case .alreadyRunning:
                alreadyRunning = true
                return
            case .running(let running):
                adopt(running)
            }
        }
        interruptedJob = loadInflight()
        await reload()
    }

    public func relaunch() async {
        guard let launcher else { return }
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
    /// being re-fetched runs the plan on screen rather than finding none.
    @discardableResult
    public func planBenchmark(repo: String) async -> Bool {
        guard !unsupported else { return false }
        benchmarkRefusal = nil
        do {
            quickPlan = try await backend.quickbenchPlan(repo: repo)
            return true
        } catch let error as BackendError {
            quickPlan = nil
            refusal = error
            benchmarkRefusal = error
            return false
        } catch {
            return false
        }
    }

    /// Run the plan already on screen. A plan that is not there is a refusal, never a run.
    public func startBenchmark() async {
        guard let quickPlan else { return }
        await start(.quickbench(repo: quickPlan.repo, osaurus: osaurusConsent))
    }

    public func cancelJob(now: Bool) async {
        guard let current = job, current.state.isActive else { return }
        do {
            try await backend.cancel(jobID: current.id, now: now)
            var status = current
            status.state = now ? .stoppingNow : .stoppingAfterCell
            job = status
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
        if var current = job, current.state.isActive {
            current.state = .interrupted
            job = current
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
        switch interrupted.kind {
        case .install:
            await start(.install(engine: interrupted.name))
        case .download:
            await start(.download(repo: interrupted.name))
        case .evict:
            await start(.evict(repo: interrupted.name))
        case .quickbench:
            await quickbench(repo: interrupted.name)
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
        guard !unsupported else { return }
        refusal = nil
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

        let started = ISO8601DateFormatter().string(from: Date())
        writeInflight(InterruptedJob(kind: args.kind, name: args.name, started: started))

        let jobID: String
        do {
            jobID = try await backend.startJob(kind: args.kind, args: args)
        } catch let error as BackendError {
            refusal = error
            defaults.removeObject(forKey: inflightKey)
            return
        } catch {
            defaults.removeObject(forKey: inflightKey)
            return
        }

        job = JobStatus(
            id: jobID,
            kind: args.kind,
            name: args.name,
            state: .running,
            fraction: 0,
            message: "",
            events: []
        )
        if args.kind == .quickbench {
            screen = .benchmark
        }

        do {
            for try await event in backend.events(jobID: jobID, after: nil) {
                await apply(event, jobID: jobID, args: args)
                if event.type == .done { break }
            }
        } catch let error as BackendError {
            refusal = error
        } catch {
            // The stream ended without its `done`; the job's own state already says what it
            // did, and the recommendations below are still asked for.
        }
        // AC-6: a download or an evict changes what is on disk, so the step ticks and the
        // Benchmark picker are re-read from the backend rather than left on stale rows.
        if args.kind == .download || args.kind == .evict {
            await refreshRecommendations()
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
                // A half-restored run sends `done` and no error; only its summary says so.
                status.state = summary?.ended == .restoreFailed ? .failed : .finished
            }
            job = status
            defaults.removeObject(forKey: inflightKey)
            if args.kind == .quickbench {
                screen = .results
            }
            return
        case .error:
            let code = event.payload?["code"]?.stringValue
            status.state = code == "cancelled" ? .cancelled : .failed
            let error = BackendError(code: code ?? "error", status: nil, message: event.message)
            refusal = error
            route(error: error, event: event, args: args)
            job = status
            if args.kind == .download, code == "low_disk" {
                await refreshHardware()
            }
            return
        case .result:
            summaryData = event.payloadData
            summary = summaryData.flatMap { try? JSONDecoder().decode(QuickSummary.self, from: $0) }
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
