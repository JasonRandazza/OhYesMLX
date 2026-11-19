import Foundation

public enum JSONValue: Sendable, Equatable, Codable {
    case null
    case bool(Bool)
    case int(Int64)
    case double(Double)
    case string(String)
    case array([JSONValue])
    case object([String: JSONValue])

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Int64.self) {
            self = .int(value)
        } else if let value = try? container.decode(Double.self) {
            self = .double(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
        } else if let value = try? container.decode([String: JSONValue].self) {
            self = .object(value)
        } else {
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "unsupported JSON value"
            )
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .null:
            try container.encodeNil()
        case .bool(let value):
            try container.encode(value)
        case .int(let value):
            try container.encode(value)
        case .double(let value):
            try container.encode(value)
        case .string(let value):
            try container.encode(value)
        case .array(let value):
            try container.encode(value)
        case .object(let value):
            try container.encode(value)
        }
    }

    public subscript(key: String) -> JSONValue? {
        guard case .object(let object) = self else { return nil }
        return object[key]
    }

    public var stringValue: String? {
        guard case .string(let value) = self else { return nil }
        return value
    }

    public var boolValue: Bool? {
        guard case .bool(let value) = self else { return nil }
        return value
    }

    public var intValue: Int64? {
        switch self {
        case .int(let value): return value
        case .double(let value): return Int64(value)
        default: return nil
        }
    }

    public var doubleValue: Double? {
        switch self {
        case .double(let value): return value
        case .int(let value): return Double(value)
        default: return nil
        }
    }

    public var arrayValue: [JSONValue]? {
        guard case .array(let value) = self else { return nil }
        return value
    }

    public var objectValue: [String: JSONValue]? {
        guard case .object(let value) = self else { return nil }
        return value
    }
}

public struct Volume: Codable, Sendable, Equatable {
    public let path: String
    public let freeBytes: Int64

    enum CodingKeys: String, CodingKey {
        case path
        case freeBytes = "free_bytes"
    }

    public init(path: String, freeBytes: Int64) {
        self.path = path
        self.freeBytes = freeBytes
    }
}

public struct Hardware: Codable, Sendable, Equatable {
    public let supported: Bool
    public let unsupportedReason: String?
    public let chip: String
    public let family: String
    public let tier: String
    public let cpuCores: Int
    public let gpuCores: Int?
    public let ramBytes: Int64
    public let macos: String
    public let diskFreeBytes: Int64
    public let diskTotalBytes: Int64?
    public let volumes: [Volume]
    public let modelBudgetBytes: Int64
    /// The mount point of the volume `diskFreeBytes` measures; nil when the probe failed, so a
    /// broken probe never names a volume it did not read.
    public let diskVolume: String?

    enum CodingKeys: String, CodingKey {
        case supported
        case unsupportedReason = "unsupported_reason"
        case chip
        case family
        case tier
        case cpuCores = "cpu_cores"
        case gpuCores = "gpu_cores"
        case ramBytes = "ram_bytes"
        case macos
        case diskFreeBytes = "disk_free_bytes"
        case diskTotalBytes = "disk_total_bytes"
        case volumes
        case modelBudgetBytes = "model_budget_bytes"
        case diskVolume = "disk_volume"
    }

    public init(
        supported: Bool,
        unsupportedReason: String?,
        chip: String,
        family: String,
        tier: String,
        cpuCores: Int,
        gpuCores: Int?,
        ramBytes: Int64,
        macos: String,
        diskFreeBytes: Int64,
        diskTotalBytes: Int64?,
        volumes: [Volume],
        modelBudgetBytes: Int64,
        diskVolume: String? = nil
    ) {
        self.supported = supported
        self.unsupportedReason = unsupportedReason
        self.chip = chip
        self.family = family
        self.tier = tier
        self.cpuCores = cpuCores
        self.gpuCores = gpuCores
        self.ramBytes = ramBytes
        self.macos = macos
        self.diskFreeBytes = diskFreeBytes
        self.diskTotalBytes = diskTotalBytes
        self.volumes = volumes
        self.modelBudgetBytes = modelBudgetBytes
        self.diskVolume = diskVolume
    }

    /// Bytes in use on the measured volume, or nil when the backend sent no total.
    ///
    /// `total - free` because both numbers describe the same volume; clamped at both ends so a
    /// free figure above a stale total can never draw an inverted bar.
    public var usedBytes: Int64? {
        guard let diskTotalBytes else { return nil }
        return min(diskTotalBytes, max(0, diskTotalBytes - diskFreeBytes))
    }

    /// The volume's name for a label: "Storage" for "/Volumes/Storage", nil for the startup
    /// disk ("/" or absent), which is every label's unchanged case.
    public var diskVolumeName: String? {
        guard let diskVolume, diskVolume != "/" else { return nil }
        return URL(fileURLWithPath: diskVolume).lastPathComponent
    }

    /// The label text when there is no other volume to name: the startup disk's, and a Mac
    /// whose hardware has not been read yet.
    public static let startupDiskLabel = "Free disk"

    /// The one definition of the "Free disk" label: `diskFreeBytes` is the cache volume's,
    /// so the label names that volume when it is not the startup disk.
    public var freeDiskLabel: String {
        guard let name = diskVolumeName else { return Self.startupDiskLabel }
        return "Free disk on \(name)"
    }
}

public struct PlanStep: Codable, Sendable, Equatable {
    public let id: String
    public let label: String
    public let command: [String]?

    public init(id: String, label: String, command: [String]?) {
        self.id = id
        self.label = label
        self.command = command
    }
}

public struct InstallPlan: Codable, Sendable, Equatable {
    public let engine: String
    public let kind: String
    public let sourceURL: String
    public let sizeBytesEstimate: Int64?
    public let needsAdmin: Bool
    public let steps: [PlanStep]

    enum CodingKeys: String, CodingKey {
        case engine
        case kind
        case sourceURL = "source_url"
        case sizeBytesEstimate = "size_bytes_estimate"
        case needsAdmin = "needs_admin"
        case steps
    }

    public init(
        engine: String,
        kind: String,
        sourceURL: String,
        sizeBytesEstimate: Int64?,
        needsAdmin: Bool,
        steps: [PlanStep]
    ) {
        self.engine = engine
        self.kind = kind
        self.sourceURL = sourceURL
        self.sizeBytesEstimate = sizeBytesEstimate
        self.needsAdmin = needsAdmin
        self.steps = steps
    }
}

public struct EngineStatus: Codable, Sendable, Equatable, Identifiable {
    public let name: String
    public let title: String
    public let blurb: String
    public let installed: Bool
    public let version: String?
    public let path: String?
    public let tested: Bool
    public let verified: String?
    public let install: InstallPlan?

    public var id: String { name }

    enum CodingKeys: String, CodingKey {
        case name
        case title
        case blurb
        case installed
        case version
        case path
        case tested
        case verified
        case install
    }

    public init(
        name: String,
        title: String,
        blurb: String,
        installed: Bool,
        version: String?,
        path: String?,
        tested: Bool,
        verified: String?,
        install: InstallPlan?
    ) {
        self.name = name
        self.title = title
        self.blurb = blurb
        self.installed = installed
        self.version = version
        self.path = path
        self.tested = tested
        self.verified = verified
        self.install = install
    }
}

public struct MeasuredHere: Codable, Sendable, Equatable {
    public let decodeTPS: Double
    public let engine: String
    public let format: String?
    public let measuredAt: String
    public let quick: Bool
    public let repo: String?
    public let ttftS: Double

    enum CodingKeys: String, CodingKey {
        case decodeTPS = "decode_tps"
        case engine
        case format
        case measuredAt = "measured_at"
        case quick
        case repo
        case ttftS = "ttft_s"
    }

    public init(
        decodeTPS: Double,
        engine: String,
        measuredAt: String,
        quick: Bool,
        ttftS: Double,
        format: String? = nil,
        repo: String? = nil
    ) {
        self.decodeTPS = decodeTPS
        self.engine = engine
        self.format = format
        self.measuredAt = measuredAt
        self.quick = quick
        self.repo = repo
        self.ttftS = ttftS
    }
}

/// P5-11: finished files of a not-downloaded row sit on disk at a size the catalog does not
/// pin. `ours` are in this app's fetch ledger (Download repairs them); `foreign` are not
/// (`fetch.download` refuses to overwrite them). Absent or null means nothing mismatched.
public enum MismatchOnDisk: String, Codable, Sendable, Equatable {
    case ours
    case foreign
}

public struct Pick: Codable, Sendable, Equatable, Identifiable {
    public let modelID: String
    public let title: String
    public let paramsB: Double
    public let format: String
    public let sizeBytes: Int64
    public let fit: String
    public let fitBasis: String
    public let engines: [String]
    public let installNeeded: Bool
    public let startHere: Bool
    public let reason: String
    public let downloaded: Bool
    public let measuredHere: MeasuredHere?
    public let mismatchOnDisk: MismatchOnDisk?

    public var id: String { modelID }

    enum CodingKeys: String, CodingKey {
        case modelID = "model_id"
        case title
        case paramsB = "params_b"
        case format
        case sizeBytes = "size_bytes"
        case fit
        case fitBasis = "fit_basis"
        case engines
        case installNeeded = "install_needed"
        case startHere = "start_here"
        case reason
        case downloaded
        case measuredHere = "measured_here"
        case mismatchOnDisk = "mismatch_on_disk"
    }

    public init(
        modelID: String,
        title: String,
        paramsB: Double,
        format: String,
        sizeBytes: Int64,
        fit: String,
        fitBasis: String,
        engines: [String],
        installNeeded: Bool,
        startHere: Bool,
        reason: String,
        downloaded: Bool,
        measuredHere: MeasuredHere?,
        mismatchOnDisk: MismatchOnDisk? = nil
    ) {
        self.modelID = modelID
        self.title = title
        self.paramsB = paramsB
        self.format = format
        self.sizeBytes = sizeBytes
        self.fit = fit
        self.fitBasis = fitBasis
        self.engines = engines
        self.installNeeded = installNeeded
        self.startHere = startHere
        self.reason = reason
        self.downloaded = downloaded
        self.measuredHere = measuredHere
        self.mismatchOnDisk = mismatchOnDisk
    }
}

extension Pick {
    /// The download button's title: "Re-download" only for files this app wrote (P5-11).
    public var downloadTitle: String {
        mismatchOnDisk == .ours ? "Re-download" : "Download"
    }

    /// The one plain line shown instead of a button when the files on disk are not ours:
    /// `fetch.download` would refuse them, so a non-nil line means no download button.
    public var mismatchLine: String? {
        mismatchOnDisk == .foreign
            ? "The files already on this Mac don't match this version. "
                + "Remove them from the Hugging Face cache, then download again."
            : nil
    }
}

public struct ExcludedModel: Codable, Sendable, Equatable, Identifiable {
    public let modelID: String
    public let reason: String

    public var id: String { modelID }

    enum CodingKeys: String, CodingKey {
        case modelID = "model_id"
        case reason
    }

    public init(modelID: String, reason: String) {
        self.modelID = modelID
        self.reason = reason
    }
}

public struct Recommendations: Codable, Sendable, Equatable {
    public let picks: [Pick]
    public let excluded: [ExcludedModel]
    public let unsupportedReason: String?

    enum CodingKeys: String, CodingKey {
        case picks
        case excluded
        case unsupportedReason = "unsupported_reason"
    }

    public init(picks: [Pick], excluded: [ExcludedModel], unsupportedReason: String?) {
        self.picks = picks
        self.excluded = excluded
        self.unsupportedReason = unsupportedReason
    }
}

public struct PlannedEngine: Codable, Sendable, Equatable {
    public let engine: String
    public let version: String?
    public let tested: Bool

    public init(engine: String, version: String?, tested: Bool) {
        self.engine = engine
        self.version = version
        self.tested = tested
    }
}

public struct PlannedSibling: Codable, Sendable, Equatable {
    public let repo: String
    public let format: String
    public let sizeBytes: Int64
    public let downloaded: Bool

    enum CodingKeys: String, CodingKey {
        case repo
        case format
        case sizeBytes = "size_bytes"
        case downloaded
    }

    public init(repo: String, format: String, sizeBytes: Int64, downloaded: Bool) {
        self.repo = repo
        self.format = format
        self.sizeBytes = sizeBytes
        self.downloaded = downloaded
    }
}

public struct QuickPlan: Codable, Sendable, Equatable {
    public let repo: String
    public let format: String
    public let stageA: [PlannedEngine]
    public let stageB: [PlannedSibling]
    public let downloadBytes: Int64
    /// Free bytes on the cache's volume once `downloadBytes` have landed, floored at 0; the
    /// backend's figure, never computed here.
    public let freeAfterBytes: Int64
    public let osaurus: Bool
    public let estimateS: Int

    enum CodingKeys: String, CodingKey {
        case repo
        case format
        case stageA = "stage_a"
        case stageB = "stage_b"
        case downloadBytes = "download_bytes"
        case freeAfterBytes = "free_after_bytes"
        case osaurus
        case estimateS = "estimate_s"
    }

    public init(
        repo: String,
        format: String,
        stageA: [PlannedEngine],
        stageB: [PlannedSibling],
        downloadBytes: Int64,
        freeAfterBytes: Int64,
        osaurus: Bool,
        estimateS: Int
    ) {
        self.repo = repo
        self.format = format
        self.stageA = stageA
        self.stageB = stageB
        self.downloadBytes = downloadBytes
        self.freeAfterBytes = freeAfterBytes
        self.osaurus = osaurus
        self.estimateS = estimateS
    }
}

public enum JobEventType: String, Codable, Sendable {
    case progress
    case log
    case result
    case error
    case done
}

public struct JobEvent: Codable, Sendable, Equatable, Identifiable {
    public let seq: Int
    public let type: JobEventType
    public let message: String
    public let fraction: Double?
    public let payload: JSONValue?

    public var id: Int { seq }

    /// The payload re-serialised with every field the backend sent, for the file Export
    /// writes (AC-2, D8).
    ///
    /// `JSONValue` models any JSON a backend sends, so this keeps keys `QuickSummary` does
    /// not model (`plan`, `engines`, `load`, `osaurus`, `harness`) instead of dropping them
    /// the way an encode of the typed value would. The bytes are this client's own canonical
    /// re-serialisation, not the wire's: the SSE and HTTP layers hand this client a decoded
    /// event, so the frame's original bytes are gone by the time an event exists here.
    /// Integers stay integers on the way through.
    public var payloadData: Data? {
        guard let payload else { return nil }
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        return try? encoder.encode(payload)
    }

    public init(seq: Int, type: JobEventType, message: String, fraction: Double?, payload: JSONValue?) {
        self.seq = seq
        self.type = type
        self.message = message
        self.fraction = fraction
        self.payload = payload
    }
}

public struct BackendError: Codable, Error, Sendable, Equatable, LocalizedError {
    public let code: String
    public let status: Int?
    public let message: String

    public var errorDescription: String? { message }

    public init(code: String, status: Int?, message: String) {
        self.code = code
        self.status = status
        self.message = message
    }
}

struct BackendErrorEnvelope: Decodable, Sendable {
    let error: BackendError
}

// The quickbench summary (`docs/interfaces/v5-quickbench.md`, the pinned block). It is the one
// record a run leaves, on every ending, and the app reads it rather than re-deriving a number.

public enum QuickEnding: String, Codable, Sendable {
    case finished
    case cancelled
    case restoreFailed = "restore_failed"
    case error
}

public struct QuickHarness: Codable, Sendable, Equatable {
    public let version: String
    public let sourceSHA256: String

    enum CodingKeys: String, CodingKey {
        case version
        case sourceSHA256 = "source_sha256"
    }

    public init(version: String, sourceSHA256: String) {
        self.version = version
        self.sourceSHA256 = sourceSHA256
    }
}

public struct QuickEngine: Codable, Sendable, Equatable {
    public let name: String
    public let version: String?
    public let tested: Bool

    public init(name: String, version: String?, tested: Bool) {
        self.name = name
        self.version = version
        self.tested = tested
    }
}

public struct QuickCell: Codable, Sendable, Equatable, Identifiable {
    public let engine: String
    public let format: String
    public let repo: String
    public let artifactDir: String
    public let status: String
    public let reason: String?
    public let decodeTPS: Double?
    public let ttftS: Double?
    public let runtimeVersion: String?
    public let label: String
    public let reused: Bool

    public var id: String { "\(format)/\(engine)/\(artifactDir)" }

    enum CodingKeys: String, CodingKey {
        case engine
        case format
        case repo
        case artifactDir = "artifact_dir"
        case status
        case reason
        case decodeTPS = "decode_tps"
        case ttftS = "ttft_s"
        case runtimeVersion = "runtime_version"
        case label
        case reused
    }

    public init(
        engine: String,
        format: String,
        repo: String,
        artifactDir: String,
        status: String,
        reason: String?,
        decodeTPS: Double?,
        ttftS: Double?,
        runtimeVersion: String?,
        label: String,
        reused: Bool
    ) {
        self.engine = engine
        self.format = format
        self.repo = repo
        self.artifactDir = artifactDir
        self.status = status
        self.reason = reason
        self.decodeTPS = decodeTPS
        self.ttftS = ttftS
        self.runtimeVersion = runtimeVersion
        self.label = label
        self.reused = reused
    }
}

public struct QuickStageA: Codable, Sendable, Equatable {
    public let caveat: String
    public let cells: [QuickCell]
    public let winner: String?
    public let tie: [String]
    public let note: String?

    public init(caveat: String, cells: [QuickCell], winner: String?, tie: [String], note: String?) {
        self.caveat = caveat
        self.cells = cells
        self.winner = winner
        self.tie = tie
        self.note = note
    }
}

/// How a stage-A cell is marked: one engine "fastest in stage", or each engine inside the
/// noise band "tied" (S3-F9).
public enum StageBadge: Sendable, Equatable {
    case fastest
    case tied
}

extension QuickStageA {
    /// Two or more engines inside the tie band are one reading on this host.
    public var isTied: Bool { tie.count > 1 }

    public func badge(for cell: QuickCell) -> StageBadge? {
        guard cell.status == "PASS" else { return nil }
        if isTied { return tie.contains(cell.engine) ? .tied : nil }
        return cell.engine == winner ? .fastest : nil
    }
}

public struct QuickStageB: Codable, Sendable, Equatable {
    public let caveat: String
    public let engine: String?
    public let cells: [QuickCell]
    public let note: String?

    public init(caveat: String, engine: String?, cells: [QuickCell], note: String?) {
        self.caveat = caveat
        self.engine = engine
        self.cells = cells
        self.note = note
    }
}

public struct QuickLoad: Codable, Sendable, Equatable {
    public let before: Double
    public let after: Double
    public let label: String?

    public init(before: Double, after: Double, label: String?) {
        self.before = before
        self.after = after
        self.label = label
    }
}

public struct QuickLoads: Codable, Sendable, Equatable {
    public let stageA: QuickLoad?
    public let stageB: QuickLoad?

    enum CodingKeys: String, CodingKey {
        case stageA = "stage_a"
        case stageB = "stage_b"
    }

    public init(stageA: QuickLoad?, stageB: QuickLoad?) {
        self.stageA = stageA
        self.stageB = stageB
    }
}

public struct QuickOsaurus: Codable, Sendable, Equatable {
    public let allowed: Bool
    public let pinned: Bool
    public let restored: Bool?
    public let reason: String?
    public let duringRun: String?

    enum CodingKeys: String, CodingKey {
        case allowed
        case pinned
        case restored
        case reason
        case duringRun = "during_run"
    }

    public init(allowed: Bool, pinned: Bool, restored: Bool?, reason: String?, duringRun: String?) {
        self.allowed = allowed
        self.pinned = pinned
        self.restored = restored
        self.reason = reason
        self.duringRun = duringRun
    }
}

public struct QuickSummary: Codable, Sendable, Equatable {
    public let label: String
    public let repo: String
    public let format: String
    public let plan: QuickPlan
    public let estimateS: Int
    public let actualS: Double?
    public let ended: QuickEnding
    public let resultsDir: String
    public let notEvicted: [String]
    public let harness: QuickHarness
    public let engines: [QuickEngine]
    public let load: QuickLoads
    public let osaurus: QuickOsaurus
    public let stageA: QuickStageA
    public let stageB: QuickStageB
    public let best: MeasuredHere?

    enum CodingKeys: String, CodingKey {
        case label
        case repo
        case format
        case plan
        case estimateS = "estimate_s"
        case actualS = "actual_s"
        case ended
        case resultsDir = "results_dir"
        case notEvicted = "not_evicted"
        case harness
        case engines
        case load
        case osaurus
        case stageA = "stage_a"
        case stageB = "stage_b"
        case best
    }

    public init(
        label: String,
        repo: String,
        format: String,
        plan: QuickPlan,
        estimateS: Int,
        actualS: Double?,
        ended: QuickEnding,
        resultsDir: String,
        notEvicted: [String],
        harness: QuickHarness,
        engines: [QuickEngine],
        load: QuickLoads,
        osaurus: QuickOsaurus,
        stageA: QuickStageA,
        stageB: QuickStageB,
        best: MeasuredHere?
    ) {
        self.label = label
        self.repo = repo
        self.format = format
        self.plan = plan
        self.estimateS = estimateS
        self.actualS = actualS
        self.ended = ended
        self.resultsDir = resultsDir
        self.notEvicted = notEvicted
        self.harness = harness
        self.engines = engines
        self.load = load
        self.osaurus = osaurus
        self.stageA = stageA
        self.stageB = stageB
        self.best = best
    }
}

extension QuickSummary {
    /// The run's own contention label for a stage ("this Mac was busy"), nil when clean.
    public func busyLine(stageA isStageA: Bool) -> String? {
        let label = (isStageA ? load.stageA : load.stageB)?.label
        return label?.isEmpty == false ? label : nil
    }

    /// The best card's heading: on a stage-A tie it does not call one engine best (S3-F9).
    public var bestHeading: String {
        stageA.isTied ? "Fastest measured here (top engines tied)" : "Best on your Mac"
    }

    /// Said on the best card when stage A's top engines tied; `best` still names one engine
    /// because the backend picks by decode rate alone.
    public var bestTieLine: String? {
        stageA.isTied
            ? "The top engines tied within the noise band, so this one is not clearly the best on its own."
            : nil
    }

    /// The winning cell's own format, falling back to the chosen row's on a summary written
    /// before the win named its artifact.
    public var bestFormat: String {
        best?.format ?? format
    }
}
