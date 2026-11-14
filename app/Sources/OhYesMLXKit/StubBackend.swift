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
            let jobID = String(format: "%016llx", nextID)
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
