import Foundation

public enum JobKind: Sendable, Equatable, CaseIterable {
    case install
    case download
    case evict
    case quickbench

    public var wireName: String {
        switch self {
        case .install: return "install"
        case .download: return "download"
        case .evict: return "evict"
        case .quickbench: return "quickbench"
        }
    }

    public init?(wireName: String) {
        switch wireName {
        case "install": self = .install
        case "download": self = .download
        case "evict": self = .evict
        case "quickbench": self = .quickbench
        default: return nil
        }
    }
}

public enum JobArgs: Sendable, Equatable {
    case install(engine: String)
    case download(repo: String)
    case evict(repo: String)
    case quickbench(repo: String, osaurus: Bool)

    public var kind: JobKind {
        switch self {
        case .install: return .install
        case .download: return .download
        case .evict: return .evict
        case .quickbench: return .quickbench
        }
    }

    public var name: String {
        switch self {
        case .install(let engine): return engine
        case .download(let repo): return repo
        case .evict(let repo): return repo
        case .quickbench(let repo, _): return repo
        }
    }

    public var body: [String: JSONValue] {
        switch self {
        case .install(let engine):
            return ["engine": .string(engine), "confirmed": .bool(true)]
        case .download(let repo), .evict(let repo):
            return ["repo": .string(repo), "confirmed": .bool(true)]
        case .quickbench(let repo, let osaurus):
            return [
                "repo": .string(repo),
                "confirmed": .bool(true),
                "osaurus": .bool(osaurus),
            ]
        }
    }
}

public struct BackendEndpoint: Sendable, Equatable {
    public let port: Int
    public let token: BackendToken

    public init(port: Int, token: BackendToken) {
        self.port = port
        self.token = token
    }
}

public protocol Backend: Sendable {
    func hardware() async throws -> Hardware
    func engines() async throws -> [EngineStatus]
    func recommendations() async throws -> Recommendations
    func quickbenchPlan(repo: String) async throws -> QuickPlan
    func startJob(kind: JobKind, args: JobArgs) async throws -> String
    func cancel(jobID: String, now: Bool) async throws
    func events(jobID: String, after: Int?) -> AsyncThrowingStream<JobEvent, Error>
}
