import Foundation

public struct StubScript: Sendable, Equatable {
    public let events: [JobEvent]
    public let hold: Bool

    public init(events: [JobEvent], hold: Bool = false) {
        self.events = events
        self.hold = hold
    }
}

public struct StubJobStart: Sendable, Equatable {
    public let kind: JobKind
    public let args: JobArgs

    public init(kind: JobKind, args: JobArgs) {
        self.kind = kind
        self.args = args
    }
}

public struct StubCancelCall: Sendable, Equatable {
    public let jobID: String
    public let now: Bool

    public init(jobID: String, now: Bool) {
        self.jobID = jobID
        self.now = now
    }
}

public final class StubBackend: Backend, @unchecked Sendable {
    private struct Job {
        let args: JobArgs
        let script: StubScript
    }

    private let lock = NSLock()
    private var hardwareValue: Hardware
    private var enginesValue: [EngineStatus]
    private var recommendationsValue: Recommendations
    private var planValue: QuickPlan?

    private var hardwareError: BackendError?
    private var enginesError: BackendError?
    private var recommendationsError: BackendError?
    private var planError: BackendError?
    private var startJobError: BackendError?
    private var cancelError: BackendError?

    private var queuedScripts: [StubScript] = []
    private var jobs: [String: Job] = [:]
    private var starts: [StubJobStart] = []
    private var cancels: [StubCancelCall] = []
    private var heldContinuations: [String: AsyncThrowingStream<JobEvent, Error>.Continuation] = [:]

    private var hardwareCalls = 0
    private var enginesCalls = 0
    private var recommendationsCalls = 0
    private var nextID = 1

    public init(
        hardware: Hardware,
        engines: [EngineStatus],
        recommendations: Recommendations,
        plan: QuickPlan? = nil
    ) {
        self.hardwareValue = hardware
        self.enginesValue = engines
        self.recommendationsValue = recommendations
        self.planValue = plan
    }

    public func setHardware(_ value: Hardware) {
        lock.withLock { hardwareValue = value }
    }

    public func setEngines(_ value: [EngineStatus]) {
        lock.withLock { enginesValue = value }
    }

    public func setRecommendations(_ value: Recommendations) {
        lock.withLock { recommendationsValue = value }
    }

    public func setPlan(_ value: QuickPlan?) {
        lock.withLock { planValue = value }
    }

    public func setError(_ error: BackendError?, for endpoint: Endpoint) {
        lock.withLock {
            switch endpoint {
            case .hardware: hardwareError = error
            case .engines: enginesError = error
            case .recommendations: recommendationsError = error
            case .plan: planError = error
            case .startJob: startJobError = error
            case .cancel: cancelError = error
            }
        }
    }

    public enum Endpoint: Sendable {
        case hardware
        case engines
        case recommendations
        case plan
        case startJob
        case cancel
    }

    public func enqueue(events: [JobEvent], hold: Bool = false) {
        lock.withLock { queuedScripts.append(StubScript(events: events, hold: hold)) }
    }

    public func releaseJob(_ events: [JobEvent] = []) {
        let continuations = lock.withLock {
            let value = heldContinuations
            heldContinuations.removeAll()
            return value
        }
        for continuation in continuations.values {
            for event in events {
                continuation.yield(event)
            }
            continuation.finish()
        }
    }

    public var startedJobs: [StubJobStart] {
        lock.withLock { starts }
    }

    public var cancelCalls: [StubCancelCall] {
        lock.withLock { cancels }
    }

    public var hardwareRequestCount: Int {
        lock.withLock { hardwareCalls }
    }

    public var enginesRequestCount: Int {
        lock.withLock { enginesCalls }
    }

    public var recommendationsRequestCount: Int {
        lock.withLock { recommendationsCalls }
    }

    public func hardware() async throws -> Hardware {
        let (error, value) = lock.withLock {
            hardwareCalls += 1
            return (hardwareError, hardwareValue)
        }
        if let error { throw error }
        return value
    }

    public func engines() async throws -> [EngineStatus] {
        let (error, value) = lock.withLock {
            enginesCalls += 1
            return (enginesError, enginesValue)
        }
        if let error { throw error }
        return value
    }

    public func recommendations() async throws -> Recommendations {
        let (error, value) = lock.withLock {
            recommendationsCalls += 1
            return (recommendationsError, recommendationsValue)
        }
        if let error { throw error }
        return value
    }

    public func quickbenchPlan(repo: String) async throws -> QuickPlan {
        let (error, plan) = lock.withLock { (planError, planValue) }
        if let error { throw error }
        guard let plan else {
            throw BackendError(
                code: "bad_args",
                status: 400,
                message: "\(repo) is not in this Mac's Hugging Face cache; download it first"
            )
        }
        return plan
    }

    public func startJob(kind: JobKind, args: JobArgs) async throws -> String {
        try lock.withLock {
            if let error = startJobError {
                throw error
            }
            let script = queuedScripts.isEmpty
                ? StubScript(events: [])
                : queuedScripts.removeFirst()
            let hex = String(nextID, radix: 16)
            let jobID = String(repeating: "0", count: max(0, 16 - hex.count)) + hex
            nextID += 1
            jobs[jobID] = Job(args: args, script: script)
            starts.append(StubJobStart(kind: kind, args: args))
            return jobID
        }
    }

    public func cancel(jobID: String, now: Bool) async throws {
        let error = lock.withLock {
            cancels.append(StubCancelCall(jobID: jobID, now: now))
            return cancelError
        }
        if let error { throw error }
    }

    public func events(jobID: String, after: Int?) -> AsyncThrowingStream<JobEvent, Error> {
        let script = lock.withLock { jobs[jobID]?.script ?? StubScript(events: []) }
        let floor = after ?? 0
        let events = script.events.filter { $0.seq > floor }
        return AsyncThrowingStream { continuation in
            for event in events {
                continuation.yield(event)
            }
            if script.hold {
                lock.withLock { heldContinuations[jobID] = continuation }
            } else {
                continuation.finish()
            }
        }
    }
}

#if DEBUG
/// The screens a DEBUG build can be started in, for screenshots without a backend.
/// Selected by `OYMLX_STUB_SCENARIO=<rawValue>`; release builds ignore the variable.
public enum StubScenario: String, CaseIterable, Sendable {
    case welcome
    case engines
    case enginesConsent = "engines-consent"
    case enginesBusy = "engines-busy"
    case enginesFailed = "engines-failed"
    case couldntStart = "couldnt-start"
    case unsupported
    case backendStopped = "backend-stopped"
    case interrupted
    case models
    case modelsDownloading = "models-downloading"
    case modelsLowDisk = "models-low-disk"
    case benchmarkPlan = "benchmark-plan"
    case benchmarkRunning = "benchmark-running"
    case resultsFinished = "results-finished"
    case resultsCancelled = "results-cancelled"

    static let stubRepo = "mlx-community/Qwen3.5-2B-4bit"

    public var consentEngineName: String? {
        self == .enginesConsent ? "osaurus" : nil
    }

    var hardwareReadyTimeout: TimeInterval {
        self == .couldntStart ? 0.2 : 2
    }

    /// The summary as a `JSONValue`, which is the shape the stream carries: a scenario stages
    /// the same record a run writes, so Results is screenshotted from the pinned shape.
    static func summaryPayload(cancelled: Bool) -> JSONValue {
        let data = (try? JSONEncoder().encode(stubSummary(cancelled: cancelled))) ?? Data()
        return (try? JSONDecoder().decode(JSONValue.self, from: data)) ?? .null
    }

    /// The run in progress at the moment comp 6b is screenshotted: stage A's third cell, two
    /// cells landed, both stop controls available.
    private func benchmarkRunningEvents() -> [JobEvent] {
        let format = "mlx affine 4-bit gs64"
        func cell(_ seq: Int, _ engine: String, _ status: String, _ reason: String?) -> JobEvent {
            JobEvent(
                seq: seq,
                type: .progress,
                message: "stage A: \(engine) \(status)",
                fraction: Double(seq) / 5.0,
                payload: .object([
                    "stage": .string("A"),
                    "engine": .string(engine),
                    "format": .string(format),
                    "status": .string(status),
                    "reason": reason.map { .string($0) } ?? .null,
                ])
            )
        }
        return [
            JobEvent(
                seq: 1,
                type: .progress,
                message: "stage A: 5 installed engine(s), one format (engines compared on one format only)",
                fraction: 0,
                payload: .object(["stage": .string("A")])
            ),
            cell(2, "mlxlm", "PASS", nil),
            cell(3, "osaurus", "PASS", nil),
            cell(4, "omlx", "SKIPPED", "quit omlx first"),
        ]
    }

    private var missingEngines: Set<String> {
        switch self {
        case .enginesConsent, .enginesBusy: return ["osaurus", "optiq"]
        case .enginesFailed: return ["optiq"]
        default: return []
        }
    }

    /// The scenarios that show the Benchmark screen's plan or run need one from the backend;
    /// so do the Results ones, because a run starts from the plan it was shown.
    private var needsPlan: Bool {
        switch self {
        case .benchmarkPlan, .benchmarkRunning, .resultsFinished, .resultsCancelled: return true
        default: return false
        }
    }

    func makeBackend() -> StubBackend {
        let backend = StubBackend(
            hardware: Self.stubHardware(supported: self != .unsupported),
            engines: Self.stubEngines(missing: missingEngines),
            recommendations: recommendations,
            plan: needsPlan ? Self.stubPlan : nil
        )
        if self == .modelsLowDisk {
            // The refusal's numbers are the payload's; the disk the meter re-reads is this one.
            backend.setHardware(Self.stubHardware(supported: true, diskFreeBytes: 39_000_000_000))
        }
        if self == .couldntStart {
            backend.setError(
                BackendError(
                    code: "couldnt_start",
                    status: nil,
                    message: """
                    the backend did not print its launch line
                    Traceback (most recent call last):
                      File "ohyesmlx/server.py", line 41, in <module>
                        sock.bind(("127.0.0.1", 47821))
                    OSError: [Errno 48] Address already in use
                    """
                ),
                for: .hardware
            )
        }
        if self == .enginesBusy {
            backend.enqueue(
                events: [
                    JobEvent(
                        seq: 1,
                        type: .progress,
                        message: "Downloading Qwen3.5 2B",
                        fraction: 0.42,
                        payload: nil
                    ),
                ],
                hold: true
            )
        }
        if self == .modelsDownloading {
            backend.enqueue(
                events: [
                    JobEvent(
                        seq: 1,
                        type: .progress,
                        message: "Downloading Qwen3.5 2B",
                        fraction: 0.42,
                        payload: .object([
                            "path": .string("model-00001-of-00002.safetensors"),
                            "bytes_done": .int(588_000_000),
                            "bytes_total": .int(1_400_000_000),
                        ])
                    ),
                ],
                hold: true
            )
        }
        if self == .modelsLowDisk {
            backend.enqueue(events: [
                JobEvent(
                    seq: 1,
                    type: .progress,
                    message: "Downloading Qwen3.5 2B",
                    fraction: 0.18,
                    payload: .object([
                        "path": .string("model-00001-of-00002.safetensors"),
                        "bytes_done": .int(252_000_000),
                        "bytes_total": .int(1_400_000_000),
                    ])
                ),
                JobEvent(
                    seq: 2,
                    type: .error,
                    message: "39000000000 bytes free is less than the 40200000000 bytes "
                        + "this download needs",
                    fraction: nil,
                    payload: .object([
                        "code": .string("low_disk"),
                        "free_bytes": .int(39_000_000_000),
                        "needed_bytes": .int(40_200_000_000),
                    ])
                ),
                JobEvent(
                    seq: 3,
                    type: .done,
                    message: "download refused",
                    fraction: nil,
                    payload: nil
                ),
            ])
        }
        if self == .benchmarkRunning {
            backend.enqueue(
                events: benchmarkRunningEvents(),
                hold: true
            )
        }
        if self == .resultsFinished || self == .resultsCancelled {
            backend.enqueue(
                events: [
                    JobEvent(
                        seq: 1,
                        type: .result,
                        message: "quickbench finished",
                        fraction: nil,
                        payload: Self.summaryPayload(cancelled: self == .resultsCancelled)
                    ),
                    JobEvent(
                        seq: 2,
                        type: .done,
                        message: self == .resultsCancelled
                            ? "quickbench cancelled"
                            : "quickbench finished",
                        fraction: nil,
                        payload: nil
                    ),
                ]
            )
        }
        if self == .enginesFailed {
            backend.enqueue(events: [
                JobEvent(seq: 1, type: .progress, message: "Preparing OptiQ", fraction: 0, payload: nil),
                JobEvent(
                    seq: 2,
                    type: .error,
                    message: "step install failed with exit code 1",
                    fraction: nil,
                    payload: .object([
                        "code": .string("step_failed"),
                        "output_tail": .string(
                            "ERROR: Could not find a version that satisfies the requirement "
                                + "mlx-optiq==0.5.13\nERROR: No matching distribution found for mlx-optiq==0.5.13"
                        ),
                    ])
                ),
                JobEvent(
                    seq: 3,
                    type: .done,
                    message: "install failed; nothing else was run",
                    fraction: nil,
                    payload: nil
                ),
            ])
        }
        return backend
    }

    private static func stubHardware(supported: Bool, diskFreeBytes: Int64 = 43_377_606_656) -> Hardware {
        Hardware(
            supported: supported,
            unsupportedReason: supported
                ? nil
                : "It has an Intel Core i9 processor. Every engine OhYesMLX sets up is built on "
                    + "Apple's MLX, which runs only on Apple silicon (M1 or later).",
            chip: supported ? "Apple M2 Max" : "Intel Core i9",
            family: supported ? "M2" : "Intel",
            tier: supported ? "max" : "base",
            cpuCores: supported ? 12 : 8,
            gpuCores: supported ? 30 : nil,
            ramBytes: supported ? 68_719_476_736 : 32_000_000_000,
            macos: "27.2.1",
            diskFreeBytes: diskFreeBytes,
            volumes: [Volume(path: "/", freeBytes: diskFreeBytes)],
            modelBudgetBytes: supported ? 49_392_123_904 : 24_000_000_000
        )
    }

    private static func stubEngines(missing: Set<String>) -> [EngineStatus] {
        [
            engine(
                name: "mlxlm",
                title: "mlx-lm",
                blurb: "Apple's reference MLX server, and this harness's control.",
                version: "0.31.3",
                tested: true,
                missing: missing.contains("mlxlm"),
                install: nil
            ),
            engine(
                name: "osaurus",
                title: "Osaurus",
                blurb: "Native menubar app with its own MLX engine.",
                version: "0.25.33",
                tested: false,
                missing: missing.contains("osaurus"),
                install: osaurusPlan
            ),
            engine(
                name: "omlx",
                title: "oMLX",
                blurb: "Menubar app that bundles its own Python and MLX.",
                version: "0.7.3",
                tested: true,
                missing: missing.contains("omlx"),
                install: nil
            ),
            engine(
                name: "optiq",
                title: "OptiQ",
                blurb: "Python package that serves quantized models through the optiq CLI.",
                version: "0.5.13",
                tested: true,
                missing: missing.contains("optiq"),
                install: optiqPlan
            ),
            engine(
                name: "vmlx",
                title: "vMLX",
                blurb: "Desktop app with a bundled Python engine and an OpenAI-compatible server.",
                version: "1.6.82",
                tested: false,
                missing: missing.contains("vmlx"),
                install: nil
            ),
        ]
    }

    private static func engine(
        name: String,
        title: String,
        blurb: String,
        version: String,
        tested: Bool,
        missing: Bool,
        install: InstallPlan?
    ) -> EngineStatus {
        EngineStatus(
            name: name,
            title: title,
            blurb: blurb,
            installed: !missing,
            version: missing ? nil : version,
            path: missing ? nil : "/Applications/\(title).app",
            tested: !missing && tested,
            verified: tested ? "2026-11-02" : nil,
            install: missing ? install : nil
        )
    }

    private static let osaurusPlan = InstallPlan(
        engine: "osaurus",
        kind: "guided_download",
        sourceURL: "https://github.com/osaurus-ai/osaurus/releases",
        sizeBytesEstimate: 310_000_000,
        needsAdmin: false,
        steps: [
            PlanStep(
                id: "open-page",
                label: "Download Osaurus from the release page and drag Osaurus to Applications.",
                command: nil
            ),
            PlanStep(
                id: "verify-install",
                label: "Reopen this screen: Osaurus is detected once its app bundle is in /Applications.",
                command: nil
            ),
        ]
    )

    private static let optiqPlan = InstallPlan(
        engine: "optiq",
        kind: "command",
        sourceURL: "https://pypi.org/project/mlx-optiq/",
        sizeBytesEstimate: nil,
        needsAdmin: false,
        steps: [
            PlanStep(
                id: "create-venv",
                label: "Create a private Python environment for OptiQ.",
                command: [
                    "{python}", "-I", "-m", "venv",
                    "/Users/you/Library/Application Support/OhYesMLX/engines/optiq",
                ]
            ),
            PlanStep(
                id: "install",
                label: "Install OptiQ into it, with every requirement hash-checked.",
                command: [
                    "{python}", "-I", "-m", "pip", "install", "--require-hashes",
                    "-r", "optiq-requirements.txt",
                ]
            ),
            PlanStep(
                id: "verify",
                label: "Check that it starts.",
                command: ["optiq", "--version"]
            ),
        ]
    )

    /// The rows a screenshot needs: three picks (one Start here and downloaded in `.models`,
    /// one tight), a measured row, and an excluded row with its reason.
    private var recommendations: Recommendations {
        switch self {
        case .modelsDownloading, .modelsLowDisk:
            return Self.stubRecommendations(downloaded: false)
        default:
            return Self.stubRecommendations(downloaded: true)
        }
    }

    private static func stubRecommendations(downloaded: Bool) -> Recommendations {
        Recommendations(
            picks: [
                Pick(
                    modelID: stubRepo,
                    title: "Qwen3.5 2B",
                    paramsB: 2,
                    format: "mlx 4-bit",
                    sizeBytes: 1_400_000_000,
                    fit: "comfortable",
                    fitBasis: "estimated",
                    engines: ["mlxlm"],
                    installNeeded: false,
                    startHere: true,
                    reason: "Fits with about 44.6 GB of memory to spare; 1.4 GB download.",
                    downloaded: downloaded,
                    measuredHere: nil
                ),
                Pick(
                    modelID: "mlx-community/LFM2.5-8B-A1B-MLX-4bit",
                    title: "LFM2.5 8B A1B MoE 4-bit",
                    paramsB: 8.5,
                    format: "mlx affine 4-bit gs64",
                    sizeBytes: 4_782_228_614,
                    fit: "comfortable",
                    fitBasis: "estimated",
                    engines: ["mlxlm", "osaurus", "omlx"],
                    installNeeded: false,
                    startHere: true,
                    reason: "Fits with about 40.3 GB of memory to spare; 4.8 GB download.",
                    downloaded: false,
                    measuredHere: nil
                ),
                Pick(
                    modelID: "mlx-community/Qwen3.5-8B-4bit",
                    title: "Qwen3.5 8B 4-bit",
                    paramsB: 8.2,
                    format: "mlx affine 4-bit gs64",
                    sizeBytes: 4_600_000_000,
                    fit: "tight",
                    fitBasis: "estimated",
                    engines: ["mlxlm", "omlx"],
                    installNeeded: false,
                    startHere: false,
                    reason: "Tight fit, about 6.1 GB of memory to spare; 4.6 GB download. "
                        + "Close other apps while it runs.",
                    downloaded: false,
                    measuredHere: nil
                ),
                // The stage-B sibling: a cancelled run leaves it on disk, which is the line
                // Results draws (Q7). Its title and size are what that line needs.
                Pick(
                    modelID: "RepublicOfKorokke/Qwen3.5-2B-oQ4",
                    title: "Qwen3.5 2B oQ4",
                    paramsB: 2,
                    format: "oQ4 (mixed 4/5/6/8)",
                    sizeBytes: 1_794_528_789,
                    fit: "comfortable",
                    fitBasis: "estimated",
                    engines: ["mlxlm", "omlx"],
                    installNeeded: false,
                    startHere: false,
                    reason: "Fits with about 43.9 GB of memory to spare; 1.8 GB download.",
                    downloaded: false,
                    measuredHere: MeasuredHere(
                        decodeTPS: 62.1,
                        engine: "omlx",
                        measuredAt: "2026-11-14T14:44:16.512+00:00",
                        quick: true,
                        ttftS: 0.16,
                        format: "oQ4 (mixed 4/5/6/8)",
                        repo: "RepublicOfKorokke/Qwen3.5-2B-oQ4"
                    )
                ),
            ],
            excluded: [
                ExcludedModel(
                    modelID: "mlx-community/Qwen3-32B-4bit",
                    reason: "Needs about 18.4 GB of memory and this Mac has 46 GB for models, "
                        + "so it would leave nothing for what else is open."
                )
            ],
            unsupportedReason: nil
        )
    }

    private static var stubPlan: QuickPlan {
        QuickPlan(
            repo: stubRepo,
            format: "mlx affine 4-bit gs64",
            stageA: [
                PlannedEngine(engine: "mlxlm", version: "0.31.3", tested: true),
                PlannedEngine(engine: "osaurus", version: "0.25.33", tested: false),
                PlannedEngine(engine: "omlx", version: "0.7.3", tested: true),
                PlannedEngine(engine: "optiq", version: "0.5.13", tested: true),
                PlannedEngine(engine: "vmlx", version: "1.6.82", tested: false),
            ],
            stageB: [
                PlannedSibling(
                    repo: "RepublicOfKorokke/Qwen3.5-2B-oQ4",
                    format: "oQ4 (mixed 4/5/6/8)",
                    sizeBytes: 1_794_528_789,
                    downloaded: false
                )
            ],
            downloadBytes: 1_794_528_789,
            osaurus: true,
            estimateS: 630
        )
    }

    /// A run's own summary, decoded from the JSON a real run writes. The fixture is the pinned
    /// shape (`docs/interfaces/v5-quickbench.md`), so a screenshot of Results is the shape the
    /// backend sends rather than a hand-built lookalike.
    static func stubSummaryData(cancelled: Bool) throws -> Data {
        try JSONEncoder().encode(stubSummary(cancelled: cancelled))
    }

    private static func stubSummary(cancelled: Bool) -> QuickSummary {
        let mlxlm = QuickCell(
            engine: "mlxlm",
            format: "mlx affine 4-bit gs64",
            repo: stubRepo,
            artifactDir: "/Users/you/.cache/huggingface/hub/models--Qwen3.5-2B-4bit/snapshots/abc",
            status: "PASS",
            reason: nil,
            decodeTPS: 55.4,
            ttftS: 0.21,
            runtimeVersion: "0.31.3",
            label: "quick: measured on this Mac",
            reused: false
        )
        let osaurus = QuickCell(
            engine: "osaurus",
            format: "mlx affine 4-bit gs64",
            repo: stubRepo,
            artifactDir: mlxlm.artifactDir,
            status: "PASS",
            reason: nil,
            decodeTPS: 58.9,
            ttftS: 0.19,
            runtimeVersion: "0.25.33",
            label: mlxlm.label,
            reused: false
        )
        let omlx = QuickCell(
            engine: "omlx",
            format: "mlx affine 4-bit gs64",
            repo: stubRepo,
            artifactDir: mlxlm.artifactDir,
            status: "PASS",
            reason: nil,
            decodeTPS: 61.7,
            ttftS: 0.17,
            runtimeVersion: "0.7.3",
            label: mlxlm.label,
            reused: false
        )
        let optiq = QuickCell(
            engine: "optiq",
            format: "mlx affine 4-bit gs64",
            repo: stubRepo,
            artifactDir: mlxlm.artifactDir,
            status: "FAIL",
            reason: "the server did not answer within 60 s",
            decodeTPS: nil,
            ttftS: nil,
            runtimeVersion: "0.5.13",
            label: mlxlm.label,
            reused: false
        )
        let oq4 = QuickCell(
            engine: "omlx",
            format: "oQ4 (mixed 4/5/6/8)",
            repo: "RepublicOfKorokke/Qwen3.5-2B-oQ4",
            artifactDir: "/Users/you/.cache/huggingface/hub/models--RepublicOfKorokke--Qwen3.5-2B-oQ4/snapshots/def",
            status: "PASS",
            reason: nil,
            decodeTPS: 62.1,
            ttftS: 0.16,
            runtimeVersion: "0.7.3",
            label: mlxlm.label,
            reused: false
        )

        return QuickSummary(
            label: "quick: measured on this Mac",
            repo: stubRepo,
            format: "mlx affine 4-bit gs64",
            plan: stubPlan,
            estimateS: 630,
            actualS: cancelled ? 188.03 : 704.512,
            ended: cancelled ? .cancelled : .finished,
            resultsDir: "/Users/you/Library/Application Support/OhYesMLX/results/quickbench/"
                + (cancelled ? "20261114T151000Z" : "20261114T143200Z"),
            notEvicted: cancelled ? ["RepublicOfKorokke/Qwen3.5-2B-oQ4"] : [],
            harness: QuickHarness(
                version: "0.5.0",
                sourceSHA256: String(repeating: "9f2c1d0b", count: 8)
            ),
            engines: [
                QuickEngine(name: "mlxlm", version: "0.31.3", tested: true),
                QuickEngine(name: "osaurus", version: "0.25.33", tested: false),
                QuickEngine(name: "omlx", version: "0.7.3", tested: true),
                QuickEngine(name: "optiq", version: "0.5.13", tested: true),
                QuickEngine(name: "vmlx", version: "1.6.82", tested: false),
            ],
            load: QuickLoads(
                stageA: QuickLoad(before: 1.42, after: 1.55, label: nil),
                stageB: QuickLoad(before: 1.51, after: 1.66, label: cancelled ? nil : "this Mac was busy")
            ),
            osaurus: QuickOsaurus(allowed: true, pinned: true, restored: true, reason: nil, duringRun: nil),
            stageA: QuickStageA(
                caveat: "engines compared on one format only",
                cells: cancelled
                    ? [
                        mlxlm,
                        QuickCell(
                            engine: "osaurus",
                            format: mlxlm.format,
                            repo: stubRepo,
                            artifactDir: mlxlm.artifactDir,
                            status: "SKIPPED",
                            reason: "quit the Osaurus app first",
                            decodeTPS: nil,
                            ttftS: nil,
                            runtimeVersion: nil,
                            label: mlxlm.label,
                            reused: false
                        ),
                        QuickCell(
                            engine: "omlx",
                            format: mlxlm.format,
                            repo: stubRepo,
                            artifactDir: mlxlm.artifactDir,
                            status: "SKIPPED",
                            reason: "the run was stopped before this cell",
                            decodeTPS: nil,
                            ttftS: nil,
                            runtimeVersion: nil,
                            label: mlxlm.label,
                            reused: false
                        ),
                    ]
                    : [mlxlm, osaurus, omlx, optiq],
                winner: cancelled ? "mlxlm" : "omlx",
                tie: [],
                note: nil
            ),
            stageB: QuickStageB(
                caveat: "formats compared on one engine only",
                engine: cancelled ? "mlxlm" : "omlx",
                cells: cancelled
                    ? [
                        QuickCell(
                            engine: "mlxlm",
                            format: "mlx affine 4-bit gs64",
                            repo: stubRepo,
                            artifactDir: mlxlm.artifactDir,
                            status: "PASS",
                            reason: nil,
                            decodeTPS: 55.4,
                            ttftS: 0.21,
                            runtimeVersion: "0.31.3",
                            label: mlxlm.label,
                            reused: true
                        ),
                        QuickCell(
                            engine: "mlxlm",
                            format: "oQ4 (mixed 4/5/6/8)",
                            repo: "RepublicOfKorokke/Qwen3.5-2B-oQ4",
                            artifactDir: oq4.artifactDir,
                            status: "ABORTED",
                            reason: "stopped by the user mid-cell; no number is reported",
                            decodeTPS: nil,
                            ttftS: nil,
                            runtimeVersion: "0.31.3",
                            label: mlxlm.label,
                            reused: false
                        ),
                    ]
                    : [
                        QuickCell(
                            engine: "omlx",
                            format: "mlx affine 4-bit gs64",
                            repo: stubRepo,
                            artifactDir: mlxlm.artifactDir,
                            status: "PASS",
                            reason: nil,
                            decodeTPS: 61.7,
                            ttftS: 0.17,
                            runtimeVersion: "0.7.3",
                            label: mlxlm.label,
                            reused: true
                        ),
                        oq4,
                    ],
                note: nil
            ),
            best: cancelled
                ? nil
                : MeasuredHere(
                    decodeTPS: 62.1,
                    engine: "omlx",
                    measuredAt: "2026-11-14T14:44:16.512+00:00",
                    quick: true,
                    ttftS: 0.16,
                    format: oq4.format,
                    repo: "RepublicOfKorokke/Qwen3.5-2B-oQ4"
                )
        )
    }
}

@MainActor
extension StubScenario {
    public func makeModel() -> AppModel {
        let defaults = UserDefaults(suiteName: "ohyesmlx.stub.scenario") ?? .standard
        defaults.removeObject(forKey: "inflightJob")
        if self == .interrupted {
            defaults.set(
                [
                    "kind": "download",
                    "name": Self.stubRepo,
                    "started": "2026-11-14T09:12:00Z",
                ],
                forKey: "inflightJob"
            )
        }
        return AppModel(
            backend: makeBackend(),
            defaults: defaults,
            hardwareReadyTimeout: hardwareReadyTimeout
        )
    }

    public func drive(_ model: AppModel) async {
        await model.launch()
        switch self {
        case .welcome, .couldntStart, .unsupported, .backendStopped:
            break
        case .engines, .enginesConsent:
            model.go(to: .engines)
        case .enginesBusy:
            model.go(to: .engines)
            Task { await model.download(repo: Self.stubRepo) }
        case .enginesFailed:
            model.go(to: .engines)
            model.installConsent = true
            await model.install(engine: "optiq")
            model.installConsent = false
        case .interrupted:
            model.go(to: .yourMac)
        case .models:
            model.go(to: .models)
        case .modelsDownloading:
            model.go(to: .models)
            Task { await model.download(repo: Self.stubRepo) }
        case .modelsLowDisk:
            model.go(to: .models)
            await model.download(repo: Self.stubRepo)
        case .benchmarkPlan:
            model.go(to: .benchmark)
            await model.planBenchmark(repo: Self.stubRepo)
        case .benchmarkRunning:
            model.go(to: .benchmark)
            await model.planBenchmark(repo: Self.stubRepo)
            model.osaurusConsent = true
            // The run holds its stream open, so this waits only for the job to exist: that is
            // the state the frame shows, and it keeps a screenshot from racing the start.
            Task { await model.startBenchmark() }
            for _ in 0..<200 where model.job == nil {
                try? await Task.sleep(for: .milliseconds(5))
            }
        case .resultsFinished:
            model.go(to: .results)
            await model.planBenchmark(repo: Self.stubRepo)
            await model.startBenchmark()
        case .resultsCancelled:
            model.go(to: .results)
            await model.planBenchmark(repo: Self.stubRepo)
            await model.startBenchmark()
        }
        if self == .backendStopped {
            model.backendExited(
                status: 1,
                stderrTail: [
                    "Traceback (most recent call last):",
                    "  File \"ohyesmlx/server.py\", line 41, in <module>",
                    "    sock.bind((\"127.0.0.1\", 47821))",
                    "OSError: [Errno 48] Address already in use",
                ]
            )
        }
    }
}
#endif
