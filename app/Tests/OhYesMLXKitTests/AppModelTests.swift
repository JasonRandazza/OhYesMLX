import XCTest
@testable import OhYesMLXKit

final class FakeRunner: BackendRunner, @unchecked Sendable {
    let endpoint = BackendEndpoint(port: 1, token: BackendToken("t"))

    private let lock = NSLock()
    private var quitArguments: [Bool] = []
    private var kills = 0
    private var outcome: QuitOutcome

    init(outcome: QuitOutcome = .stillRunning) {
        self.outcome = outcome
    }

    var stderrTail: [String] { [] }
    var isRunning: Bool { true }
    var onExit: (@Sendable (Int32, [String]) -> Void)?

    var quitCalls: [Bool] { lock.withLock { quitArguments } }
    var forceKills: Int { lock.withLock { kills } }

    func quit(jobRunning: Bool) async -> QuitOutcome {
        lock.withLock { quitArguments.append(jobRunning) }
        return outcome
    }

    func forceKill() {
        lock.withLock { kills += 1 }
    }
}

/// A backend whose plan for one repo is slow, so a later pick's answer can overtake it.
final class SlowPlanBackend: Backend, @unchecked Sendable {
    private let inner: StubBackend
    private let slowRepo: String
    private let lock = NSLock()
    private var planCalls: [String] = []

    init(inner: StubBackend, slowRepo: String) {
        self.inner = inner
        self.slowRepo = slowRepo
    }

    var requestedRepos: [String] { lock.withLock { planCalls } }

    func hardware() async throws -> Hardware { try await inner.hardware() }

    func engines() async throws -> [EngineStatus] { try await inner.engines() }

    func recommendations() async throws -> Recommendations { try await inner.recommendations() }

    func quickbenchPlan(repo: String) async throws -> QuickPlan {
        lock.withLock { planCalls.append(repo) }
        if repo == slowRepo {
            try? await Task.sleep(for: .milliseconds(150))
        }
        let plan = try await inner.quickbenchPlan(repo: repo)
        return QuickPlan(
            repo: repo,
            format: plan.format,
            stageA: plan.stageA,
            stageB: plan.stageB,
            downloadBytes: plan.downloadBytes,
            freeAfterBytes: plan.freeAfterBytes,
            osaurus: plan.osaurus,
            estimateS: plan.estimateS
        )
    }

    func startJob(kind: JobKind, args: JobArgs) async throws -> String {
        try await inner.startJob(kind: kind, args: args)
    }

    func cancel(jobID: String, now: Bool) async throws {
        try await inner.cancel(jobID: jobID, now: now)
    }

    func events(jobID: String, after: Int?) -> AsyncThrowingStream<JobEvent, Error> {
        inner.events(jobID: jobID, after: after)
    }
}

@MainActor
final class AppModelTests: XCTestCase {
    struct Stack {
        let model: AppModel
        let backend: StubBackend
        let defaults: UserDefaults
        let suiteName: String
    }

    private func makeStack(
        hardware: Hardware? = nil,
        recommendations: Recommendations? = nil,
        plan: QuickPlan? = nil,
        runner: (any BackendRunner)? = nil,
        bundlePath: String = Bundle.main.bundlePath
    ) throws -> Stack {
        let suiteName = "ohyesmlx-app-model-tests-\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        let hardwareValue = try hardware ?? Fixtures.hardware
        let recommendationsValue = try recommendations ?? Fixtures.recommendations
        let backend = StubBackend(
            hardware: hardwareValue,
            engines: try Fixtures.engines,
            recommendations: recommendationsValue,
            plan: plan
        )
        let model = AppModel(
            backend: backend,
            runner: runner,
            defaults: defaults,
            bundlePath: bundlePath
        )
        addTeardownBlock {
            defaults.removePersistentDomain(forName: suiteName)
        }
        return Stack(model: model, backend: backend, defaults: defaults, suiteName: suiteName)
    }

    private func waitUntil(
        timeout: TimeInterval = 2,
        _ condition: @MainActor () -> Bool
    ) async {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if condition() { return }
            try? await Task.sleep(for: .milliseconds(5))
        }
    }

    private func progress(
        _ seq: Int,
        _ message: String,
        fraction: Double? = nil,
        payload: JSONValue? = nil
    ) -> JobEvent {
        JobEvent(seq: seq, type: .progress, message: message, fraction: fraction, payload: payload)
    }

    private func done(_ seq: Int, _ message: String = "finished") -> JobEvent {
        JobEvent(seq: seq, type: .done, message: message, fraction: nil, payload: nil)
    }

    private func failure(
        _ seq: Int,
        _ message: String,
        code: String,
        extra: [String: JSONValue] = [:]
    ) -> JobEvent {
        var payload = extra
        payload["code"] = .string(code)
        return JobEvent(
            seq: seq,
            type: .error,
            message: message,
            fraction: nil,
            payload: .object(payload)
        )
    }

    /// A summary payload in the pinned shape (`docs/interfaces/v5-quickbench.md`), taken from
    /// the finished fixture with the caller's own ending and not_evicted. A non-finished run
    /// never carries a best, which is the fixture's own rule applied to the new ending.
    private func summaryPayload(
        ended: String = "finished",
        notEvicted: [String] = []
    ) throws -> JSONValue {
        var object = try XCTUnwrap(
            try JSONSerialization.jsonObject(
                with: Fixtures.data("quickbench_summary_finished.json")
            ) as? [String: Any]
        )
        object["ended"] = ended
        object["not_evicted"] = notEvicted
        if ended != "finished" {
            object["best"] = NSNull()
        }
        return try JSONDecoder().decode(
            JSONValue.self,
            from: JSONSerialization.data(withJSONObject: object)
        )
    }

    private func result(seq: Int, ended: String = "finished", notEvicted: [String] = []) throws -> JobEvent {
        JobEvent(
            seq: seq,
            type: .result,
            message: "quickbench finished",
            fraction: nil,
            payload: try summaryPayload(ended: ended, notEvicted: notEvicted)
        )
    }

    private func cellPayload(
        _ stage: String,
        _ engine: String,
        _ format: String,
        _ status: String,
        _ reason: String?
    ) -> JSONValue {
        .object([
            "stage": .string(stage),
            "engine": .string(engine),
            "format": .string(format),
            "status": .string(status),
            "reason": reason.map { .string($0) } ?? .null,
        ])
    }

    private var downloadRepo: String { "mlx-community/Qwen3-0.6B-4bit" }
    private var quickbenchRepo: String { "mlx-community/Qwen3.5-2B-4bit" }

    // MARK: - a · the happy path

    func testHappyPathInstallDownloadBenchmark() async throws {
        let stack = try makeStack(plan: try Fixtures.quickPlan)
        await stack.model.launch()
        XCTAssertEqual(stack.model.screen, .welcome)
        XCTAssertEqual(stack.model.hardware?.chip, "Apple M2 Max")
        XCTAssertEqual(stack.model.engines.count, 5)
        XCTAssertEqual(stack.model.recommendations?.picks.count, 12)

        stack.model.go(to: .yourMac)
        XCTAssertEqual(stack.model.screen, .yourMac)
        stack.model.installConsent = true

        stack.backend.enqueue(events: [
            progress(1, "Preparing OptiQ", fraction: 0),
            progress(2, "OptiQ installed", fraction: 1),
            done(3, "install finished"),
        ])
        await stack.model.install(engine: "optiq")
        XCTAssertEqual(stack.model.job?.state, .finished)
        XCTAssertEqual(stack.backend.startedJobs.last?.args, .install(engine: "optiq"))

        stack.model.go(to: .models)
        stack.backend.enqueue(events: [
            progress(1, "Downloading Qwen3 0.6B", fraction: 0),
            progress(2, "model.safetensors", fraction: 1),
            done(3, "download finished"),
        ])
        await stack.model.download(repo: downloadRepo)
        XCTAssertEqual(stack.model.job?.state, .finished)
        XCTAssertNil(stack.defaults.dictionary(forKey: "inflightJob"))

        stack.backend.enqueue(events: [
            progress(1, "stage A: 5 installed engine(s)", payload: .object(["stage": .string("A")])),
            progress(
                2,
                "stage A: mlxlm PASS",
                payload: .object([
                    "stage": .string("A"),
                    "engine": .string("mlxlm"),
                    "format": .string("mlx affine 4-bit gs64"),
                    "status": .string("PASS"),
                    "reason": .null,
                ])
            ),
            try result(seq: 3),
            done(4, "quickbench finished"),
        ])
        await stack.model.quickbench(repo: quickbenchRepo)
        XCTAssertEqual(stack.model.screen, .results)
        XCTAssertEqual(stack.model.summary?.ended, .finished)
        XCTAssertEqual(stack.backend.startedJobs.last?.args, .quickbench(repo: quickbenchRepo, osaurus: false))
    }

    // MARK: - the translocated bundle (AC-7, plan 05-06)

    /// macOS runs a quarantined app from `/AppTranslocation/<uuid>/d/...`, a path that changes
    /// every launch. The venvs are made from `sys.executable`, so nothing may be spawned there.
    func testATranslocatedBundleAsksForApplicationsAndStartsNoJob() async throws {
        let translocated = "/private/var/folders/xy/T/AppTranslocation/8F2C-9A1B/d/OhYesMLX.app"
        XCTAssertTrue(AppModel.isTranslocated(bundlePath: translocated))
        XCTAssertFalse(AppModel.isTranslocated(bundlePath: "/Applications/OhYesMLX.app"))

        let stack = try makeStack(bundlePath: translocated)
        await stack.model.launch()
        XCTAssertEqual(stack.model.screen, .moveToApplications)

        await stack.model.download(repo: downloadRepo)
        await stack.model.evict(repo: downloadRepo)
        stack.model.installConsent = true
        await stack.model.install(engine: "optiq")
        await stack.model.quickbench(repo: quickbenchRepo)
        XCTAssertTrue(stack.backend.startedJobs.isEmpty)
    }

    // MARK: - b · a failed install keeps its tail, and the retry clears it

    func testInstallFailureKeepsTheOutputTailAndRetrySucceeds() async throws {
        let stack = try makeStack()
        await stack.model.launch()
        stack.model.installConsent = true

        stack.backend.enqueue(events: [
            progress(1, "Preparing mlx-lm", fraction: 0),
            failure(
                2,
                "step pip-install failed with exit code 1",
                code: "step_failed",
                extra: [
                    "output_tail": .string(
                        "ERROR: Could not find a version that satisfies the requirement mlx==0.31.3"
                    ),
                ]
            ),
            done(3, "install failed; nothing else was run"),
        ])
        await stack.model.install(engine: "mlxlm")

        XCTAssertEqual(stack.model.job?.state, .failed)
        let failure = try XCTUnwrap(stack.model.engineFailures["mlxlm"])
        XCTAssertEqual(failure.code, "step_failed")
        XCTAssertTrue(failure.outputTail.contains("Could not find a version"))

        stack.backend.enqueue(events: [
            progress(1, "Preparing mlx-lm", fraction: 0),
            done(2, "install finished"),
        ])
        await stack.model.install(engine: "mlxlm")
        XCTAssertEqual(stack.model.job?.state, .finished)
        XCTAssertNil(stack.model.engineFailures["mlxlm"])
    }

    // MARK: - c · one slot, Q1

    func testOneSlotReasonDisablesOtherJobs() async throws {
        let stack = try makeStack()
        await stack.model.launch()
        stack.model.installConsent = true

        stack.backend.enqueue(events: [progress(1, "Preparing OptiQ", fraction: 0)], hold: true)
        let install = Task { await stack.model.install(engine: "optiq") }
        await waitUntil { stack.model.job != nil }

        XCTAssertEqual(stack.model.oneSlotReason, "Busy: install optiq is running")
        XCTAssertFalse(stack.model.canStartJob)

        stack.backend.releaseJob([done(2, "install finished")])
        await install.value
        XCTAssertNil(stack.model.oneSlotReason)
        XCTAssertTrue(stack.model.canStartJob)
    }

    func testBusyRefusalFromTheBackendIsShownVerbatim() async throws {
        let stack = try makeStack()
        await stack.model.launch()
        stack.backend.setError(
            BackendError(code: "busy", status: 409, message: "job a1b2c3d4e5f60708 is still running"),
            for: .startJob
        )

        await stack.model.download(repo: downloadRepo)
        XCTAssertEqual(stack.model.refusal?.code, "busy")
        XCTAssertEqual(stack.model.refusal?.message, "job a1b2c3d4e5f60708 is still running")
        XCTAssertNil(stack.model.job)
        XCTAssertNil(stack.defaults.dictionary(forKey: "inflightJob"))
    }

    // MARK: - d · quickbench before the model is downloaded

    func testQuickbenchWithoutADownloadShowsTheBackendsMessage() async throws {
        let stack = try makeStack()
        await stack.model.launch()

        await stack.model.quickbench(repo: downloadRepo)

        let refusal = try XCTUnwrap(stack.model.benchmarkRefusal)
        XCTAssertEqual(refusal.code, "bad_args")
        XCTAssertEqual(refusal.status, 400)
        XCTAssertTrue(refusal.message.contains("download it first"), refusal.message)
        XCTAssertTrue(stack.backend.startedJobs.isEmpty)
        XCTAssertEqual(stack.model.screen, .welcome)
    }

    // MARK: - e · skipped and missing-binary rows

    func testQuickbenchCellsCarrySkippedAndMissingBinaryRows() async throws {
        let stack = try makeStack(plan: try Fixtures.quickPlan)
        await stack.model.launch()
        stack.backend.enqueue(events: [
            progress(1, "stage A: 5 installed engine(s)", payload: .object(["stage": .string("A")])),
            progress(
                2,
                "stage A: mlxlm skipped: quit mlxlm first",
                payload: cellPayload(
                    "A", "mlxlm", "mlx affine 4-bit gs64", "SKIPPED", "quit mlxlm first"
                )
            ),
            progress(
                3,
                "stage A: vmlx N/A: runtime 'vmlx' did not start: RuntimeStartError: could not start",
                payload: cellPayload(
                    "A",
                    "vmlx",
                    "mlx affine 4-bit gs64",
                    "N/A",
                    "runtime 'vmlx' did not start: RuntimeStartError: could not start"
                )
            ),
            progress(
                4,
                "stage A: osaurus SKIPPED: Osaurus was not allowed for this run (osaurus: false)",
                payload: cellPayload(
                    "A",
                    "osaurus",
                    "mlx affine 4-bit gs64",
                    "SKIPPED",
                    "Osaurus was not allowed for this run (osaurus: false)"
                )
            ),
            done(5),
        ])

        await stack.model.quickbench(repo: quickbenchRepo)

        XCTAssertEqual(stack.model.benchmarkCells.count, 3)
        let mlxlm = try XCTUnwrap(stack.model.benchmarkCells.first { $0.engine == "mlxlm" })
        XCTAssertEqual(mlxlm.status, "SKIPPED")
        XCTAssertEqual(mlxlm.reason, "quit mlxlm first")

        let vmlx = try XCTUnwrap(stack.model.benchmarkCells.first { $0.engine == "vmlx" })
        XCTAssertEqual(vmlx.status, "N/A")
        XCTAssertTrue(vmlx.reason?.contains("did not start") == true, vmlx.reason ?? "")

        let osaurus = try XCTUnwrap(stack.model.benchmarkCells.first { $0.engine == "osaurus" })
        XCTAssertEqual(osaurus.status, "SKIPPED")
        XCTAssertTrue(osaurus.reason?.contains("(osaurus: false)") == true, osaurus.reason ?? "")
    }

    func testTwoStageBSiblingsStayTwoRows() async throws {
        let stack = try makeStack(plan: try Fixtures.quickPlan)
        await stack.model.launch()
        stack.backend.enqueue(events: [
            progress(
                1, "stage A: mlxlm PASS",
                payload: cellPayload("A", "mlxlm", "mlx affine 4-bit gs64", "PASS", nil)
            ),
            progress(
                2, "stage B: oQ4 (mixed 4/5/6/8) PASS",
                payload: cellPayload("B", "mlxlm", "oQ4 (mixed 4/5/6/8)", "PASS", nil)
            ),
            progress(
                3, "stage B: mxfp4 PASS",
                payload: cellPayload("B", "mlxlm", "mxfp4", "PASS", nil)
            ),
            done(4),
        ])

        await stack.model.quickbench(repo: quickbenchRepo)

        XCTAssertEqual(stack.model.benchmarkCells.map(\.id), [
            "A/mlxlm/mlx affine 4-bit gs64",
            "B/mlxlm/oQ4 (mixed 4/5/6/8)",
            "B/mlxlm/mxfp4",
        ])
        XCTAssertEqual(stack.model.benchmarkCells.map(\.stage), ["A", "B", "B"])
        XCTAssertEqual(stack.model.benchmarkCells.map(\.status), ["PASS", "PASS", "PASS"])
    }

    func testAStageBAbortedRowCarriesItsReasonFromThePayload() async throws {
        let stack = try makeStack(plan: try Fixtures.quickPlan)
        await stack.model.launch()
        stack.backend.enqueue(events: [
            progress(
                1,
                "mlxlm ABORTED: a message the client must never parse",
                payload: cellPayload(
                    "B",
                    "mlxlm",
                    "oQ4 (mixed 4/5/6/8)",
                    "ABORTED",
                    "stopped by the user mid-cell; no number is reported"
                )
            ),
            done(2, "quickbench cancelled"),
        ])

        await stack.model.quickbench(repo: quickbenchRepo)

        let cell = try XCTUnwrap(stack.model.benchmarkCells.first)
        XCTAssertEqual(cell.stage, "B")
        XCTAssertEqual(cell.format, "oQ4 (mixed 4/5/6/8)")
        XCTAssertEqual(cell.status, "ABORTED")
        XCTAssertEqual(cell.reason, "stopped by the user mid-cell; no number is reported")
    }

    // MARK: - f · an unsupported Mac is absolute, Q6

    func testUnsupportedMacIsAbsolute() async throws {
        let unsupported = Hardware(
            supported: false,
            unsupportedReason: "this Mac is not Apple silicon",
            chip: "Intel Core i9",
            family: "Intel",
            tier: "base",
            cpuCores: 8,
            gpuCores: nil,
            ramBytes: 32_000_000_000,
            macos: "27.2.1",
            diskFreeBytes: 400_000_000_000,
            volumes: [],
            modelBudgetBytes: 24_000_000_000
        )
        let stack = try makeStack(hardware: unsupported, plan: try Fixtures.quickPlan)
        stack.defaults.set(
            [
                "kind": "quickbench",
                "name": quickbenchRepo,
                "started": ISO8601DateFormatter().string(from: Date()),
            ],
            forKey: "inflightJob"
        )
        await stack.model.launch()

        XCTAssertEqual(stack.model.screen, .unsupported)
        XCTAssertEqual(stack.model.hardware?.unsupportedReason, "this Mac is not Apple silicon")
        XCTAssertNotNil(stack.model.interruptedJob)
        XCTAssertFalse(
            stack.model.showsInterruptedBanner,
            "the interrupted banner is shown on an unsupported Mac"
        )

        stack.model.go(to: .welcome)
        XCTAssertEqual(stack.model.screen, .unsupported)
        stack.model.go(to: .models)
        XCTAssertEqual(stack.model.screen, .unsupported)

        stack.model.installConsent = true
        stack.backend.enqueue(events: [progress(1, "Preparing OptiQ", fraction: 0), done(2)])
        await stack.model.install(engine: "optiq")
        XCTAssertTrue(stack.backend.startedJobs.isEmpty, "an install started on an unsupported Mac")

        stack.backend.enqueue(events: [done(1)])
        await stack.model.quickbench(repo: quickbenchRepo)
        XCTAssertTrue(
            stack.backend.startedJobs.isEmpty, "a quickbench started on an unsupported Mac"
        )
        XCTAssertNil(stack.model.quickPlan, "the plan was fetched for a Mac that cannot run it")
        XCTAssertEqual(stack.model.screen, .unsupported)

        await stack.model.retryInterrupted()
        XCTAssertTrue(
            stack.backend.startedJobs.isEmpty, "a retry started on an unsupported Mac"
        )
        XCTAssertNotNil(stack.model.interruptedJob, "retry ran on an unsupported Mac")
        XCTAssertEqual(stack.model.screen, .unsupported)
    }

    // MARK: - g · quit mid-download, Q2

    func testQuitMidDownloadLeavesTheBannerAndNoAutomaticRetry() async throws {
        let stack = try makeStack()
        await stack.model.launch()

        stack.backend.enqueue(events: [progress(1, "Downloading", fraction: 0.2)], hold: true)
        let download = Task { await stack.model.download(repo: downloadRepo) }
        await waitUntil { stack.model.job != nil }

        let entry = try XCTUnwrap(stack.defaults.dictionary(forKey: "inflightJob"))
        XCTAssertEqual(entry["kind"] as? String, "download")
        XCTAssertEqual(entry["name"] as? String, downloadRepo)
        XCTAssertNotNil(entry["started"] as? String)

        stack.model.backendExited(status: 1, stderrTail: ["crash"])
        XCTAssertEqual(stack.model.backendStopped, 1)
        XCTAssertEqual(stack.model.job?.state, .interrupted)
        XCTAssertNotNil(stack.defaults.dictionary(forKey: "inflightJob"))

        let relaunched = AppModel(backend: stack.backend, defaults: stack.defaults)
        await relaunched.launch()
        XCTAssertEqual(relaunched.interruptedJob?.kind, .download)
        XCTAssertEqual(relaunched.interruptedJob?.name, downloadRepo)
        XCTAssertTrue(stack.backend.startedJobs.count == 1)

        stack.backend.releaseJob([done(2, "download finished")])
        await download.value
    }

    func testRetryResendsTheJobAndDismissClearsIt() async throws {
        let stack = try makeStack()
        let started = ISO8601DateFormatter().string(from: Date())
        stack.defaults.set(
            ["kind": "download", "name": downloadRepo, "started": started],
            forKey: "inflightJob"
        )

        await stack.model.launch()
        XCTAssertEqual(stack.model.interruptedJob?.kind, .download)
        XCTAssertTrue(stack.backend.startedJobs.isEmpty)

        stack.backend.enqueue(events: [done(1, "download finished")])
        await stack.model.retryInterrupted()
        XCTAssertEqual(stack.backend.startedJobs.last?.args, .download(repo: downloadRepo))
        XCTAssertNil(stack.model.interruptedJob)
        XCTAssertNil(stack.defaults.dictionary(forKey: "inflightJob"))

        let second = try makeStack()
        second.defaults.set(
            ["kind": "download", "name": downloadRepo, "started": started],
            forKey: "inflightJob"
        )
        await second.model.launch()
        second.model.dismissInterrupted()
        XCTAssertNil(second.model.interruptedJob)
        XCTAssertNil(second.defaults.dictionary(forKey: "inflightJob"))
    }

    // MARK: - h · excluded rows and low_disk, Q4

    func testExcludedModelCarriesItsReason() async throws {
        let recommendations = Recommendations(
            picks: try Fixtures.recommendations.picks,
            excluded: [
                ExcludedModel(
                    modelID: "mlx-community/too-big",
                    reason: "Needs about 60.0 GB of memory at peak; this Mac's budget is 49.4 GB"
                ),
            ],
            unsupportedReason: nil
        )
        let stack = try makeStack(recommendations: recommendations)
        await stack.model.launch()

        let excluded = try XCTUnwrap(stack.model.recommendations?.excluded.first)
        XCTAssertEqual(excluded.modelID, "mlx-community/too-big")
        XCTAssertTrue(excluded.reason.contains("Needs about 60.0 GB"))
    }

    func testLowDiskIsStoredAgainstTheRepoAndRefreshesHardware() async throws {
        let stack = try makeStack()
        await stack.model.launch()
        let before = stack.backend.hardwareRequestCount

        let refreshed = Hardware(
            supported: true,
            unsupportedReason: nil,
            chip: "Apple M2 Max",
            family: "M2",
            tier: "max",
            cpuCores: 12,
            gpuCores: 30,
            ramBytes: 68_719_476_736,
            macos: "27.2.1",
            diskFreeBytes: 100_000_000,
            volumes: [],
            modelBudgetBytes: 49_392_123_904
        )
        stack.backend.setHardware(refreshed)
        stack.backend.enqueue(events: [
            progress(1, "downloading", fraction: 0.1),
            failure(
                2,
                "100000000 bytes free is less than the 421663274 bytes this download needs",
                code: "low_disk",
                extra: [
                    "free_bytes": .int(100_000_000),
                    "needed_bytes": .int(421_663_274),
                ]
            ),
            done(3, "download refused"),
        ])

        await stack.model.download(repo: downloadRepo)

        XCTAssertEqual(stack.model.hardware?.diskFreeBytes, 100_000_000)
        XCTAssertEqual(stack.backend.hardwareRequestCount, before + 1)
        XCTAssertEqual(stack.model.lowDisk[downloadRepo]?.amountToFree, 321_663_274)
        XCTAssertEqual(stack.model.modelRefusals[downloadRepo]?.code, "low_disk")
        XCTAssertEqual(
            stack.model.modelRefusals[downloadRepo]?.message,
            "100000000 bytes free is less than the 421663274 bytes this download needs"
        )
    }

    // MARK: - i · the Osaurus pin is asked per run

    func testOsaurusDeclinedSendsFalseAndAllowedSendsTrue() async throws {
        let stack = try makeStack(plan: try Fixtures.quickPlan)
        await stack.model.launch()

        stack.model.osaurusConsent = false
        stack.backend.enqueue(events: [done(1)])
        await stack.model.quickbench(repo: quickbenchRepo)
        XCTAssertEqual(
            stack.backend.startedJobs.last?.args,
            .quickbench(repo: quickbenchRepo, osaurus: false)
        )

        stack.model.osaurusConsent = true
        stack.backend.enqueue(events: [done(1)])
        await stack.model.quickbench(repo: quickbenchRepo)
        XCTAssertEqual(
            stack.backend.startedJobs.last?.args,
            .quickbench(repo: quickbenchRepo, osaurus: true)
        )
    }

    // MARK: - Q3 · both cancel modes

    func testCancelModesSetTheirMessages() async throws {
        let stack = try makeStack(plan: try Fixtures.quickPlan)
        await stack.model.launch()
        stack.backend.enqueue(events: [progress(1, "stage A", fraction: 0)], hold: true)
        let bench = Task { await stack.model.quickbench(repo: quickbenchRepo) }
        await waitUntil { stack.model.job != nil }
        let jobID = try XCTUnwrap(stack.model.job?.id)

        await stack.model.cancelJob(now: false)
        XCTAssertEqual(stack.backend.cancelCalls.last, StubCancelCall(jobID: jobID, now: false))
        XCTAssertEqual(stack.model.job?.state.text, "Stopping after this cell…")

        await stack.model.cancelJob(now: true)
        XCTAssertEqual(stack.backend.cancelCalls.last, StubCancelCall(jobID: jobID, now: true))
        XCTAssertEqual(stack.model.job?.state.text, "Stopping…")

        stack.backend.releaseJob([
            failure(2, "quickbench was cancelled; nothing further was measured", code: "cancelled"),
            done(3, "quickbench cancelled"),
        ])
        await bench.value
        XCTAssertEqual(stack.model.job?.state, .cancelled)
    }

    // MARK: - a job's ending is its own, never a stale summary's (spec #1)

    func testADownloadAfterARestoreFailedQuickbenchStillFinishes() async throws {
        let stack = try makeStack(plan: try Fixtures.quickPlan)
        await stack.model.launch()

        stack.backend.enqueue(events: [
            try result(seq: 1, ended: "restore_failed"),
            done(2, "quickbench ended"),
        ])
        await stack.model.quickbench(repo: quickbenchRepo)
        XCTAssertEqual(stack.model.summary?.ended, .restoreFailed)
        XCTAssertEqual(stack.model.job?.state, .failed)

        stack.backend.enqueue(events: [done(1, "download finished")])
        await stack.model.download(repo: downloadRepo)
        XCTAssertEqual(stack.model.job?.kind, .download)
        XCTAssertEqual(stack.model.job?.state, .finished)
    }

    // MARK: - Q5 · engines re-verify

    func testAppBecameActiveAndEnginesAppearRefetchEngines() async throws {
        let stack = try makeStack()
        await stack.model.launch()
        let initial = stack.backend.enginesRequestCount

        await stack.model.appBecameActive()
        XCTAssertEqual(stack.backend.enginesRequestCount, initial + 1)

        await stack.model.enginesScreenAppeared()
        XCTAssertEqual(stack.backend.enginesRequestCount, initial + 2)

        await stack.model.checkEnginesAgain()
        XCTAssertEqual(stack.backend.enginesRequestCount, initial + 3)
    }

    // MARK: - Q7 · not_evicted

    func testNotEvictedLinesNameTheRepoAndTitle() async throws {
        let stack = try makeStack(plan: try Fixtures.quickPlan)
        await stack.model.launch()
        let left = "mlx-community/LFM2.5-8B-A1B-MLX-4bit"
        stack.backend.enqueue(events: [
            try result(seq: 1, notEvicted: [left]),
            done(2),
        ])

        await stack.model.quickbench(repo: quickbenchRepo)

        XCTAssertEqual(stack.model.notEvicted, [left])
        let line = try XCTUnwrap(stack.model.notEvictedLines.first)
        XCTAssertTrue(line.hasPrefix("Left on disk: LFM2.5 8B A1B MoE 4-bit"), line)
        XCTAssertTrue(line.contains("— it was in use. You can remove it from Models."), line)
    }

    // MARK: - AC-1/AC-2 (05-05) · a cancelled run reaches Results typed, with its raw bytes

    func testACancelledSummaryTypesAndKeepsItsRawBytes() async throws {
        let stack = try makeStack(plan: try Fixtures.quickPlan)
        await stack.model.launch()
        // One key this client does not model: Export writes the payload as received, so a
        // field the backend added after the client shipped still lands in the file.
        var object = try XCTUnwrap(
            try JSONSerialization.jsonObject(
                with: try Fixtures.data("quickbench_summary_cancelled.json")
            ) as? [String: Any]
        )
        object["future_field"] = ["added_by": "a later backend", "value": 7]
        let cancelled = try JSONSerialization.data(withJSONObject: object)
        let payload = try JSONDecoder().decode(JSONValue.self, from: cancelled)
        stack.backend.enqueue(events: [
            JobEvent(seq: 1, type: .result, message: "quickbench cancelled", fraction: nil, payload: payload),
            failure(2, "quickbench was cancelled; nothing further was measured", code: "cancelled"),
            done(3, "quickbench cancelled"),
        ])

        await stack.model.quickbench(repo: quickbenchRepo)

        XCTAssertEqual(stack.model.screen, .results)
        let summary = try XCTUnwrap(stack.model.summary)
        XCTAssertEqual(summary.ended, .cancelled)
        XCTAssertNil(summary.best, "a cancelled run recommends nothing")
        XCTAssertEqual(summary.notEvicted, ["RepublicOfKorokke/Qwen3.5-2B-oQ4"])

        // The rows come from the summary, not from the progress events before it.
        XCTAssertEqual(
            stack.model.benchmarkCells.map(\.status),
            ["PASS", "SKIPPED", "SKIPPED", "PASS", "ABORTED"]
        )
        XCTAssertEqual(stack.model.benchmarkCells.last?.stage, "B")
        XCTAssertEqual(
            stack.model.benchmarkCells.last?.reason,
            "stopped by the user mid-cell; no number is reported"
        )
        XCTAssertNil(stack.model.benchmarkCells.last?.decodeTPS)

        // Export writes the payload as received: every key the payload carries survives,
        // including one this client does not model.
        let data = try XCTUnwrap(stack.model.summaryData)
        let written = try XCTUnwrap(
            try JSONSerialization.jsonObject(with: data) as? [String: Any]
        )
        XCTAssertNotNil(written["plan"], "a key the typed value models is written")
        let harness = try XCTUnwrap(written["harness"] as? [String: Any])
        XCTAssertNotNil(harness["source_sha256"])
        XCTAssertEqual(written["results_dir"] as? String, summary.resultsDir)
        let future = try XCTUnwrap(
            written["future_field"] as? [String: Any],
            "a re-encode of the typed value would have dropped this key"
        )
        XCTAssertEqual(future["value"] as? Int, 7)
    }

    func testTheSummaryReplacesLiveCellsInTheResultsRows() async throws {
        let stack = try makeStack(plan: try Fixtures.quickPlan)
        await stack.model.launch()
        stack.backend.enqueue(events: [
            progress(1, "stage A: mlxlm PASS", payload: cellPayload(
                "A", "mlxlm", "mlx affine 4-bit gs64", "PASS", nil
            )),
            try result(seq: 2),
            done(3),
        ])

        await stack.model.quickbench(repo: quickbenchRepo)

        XCTAssertEqual(stack.model.liveCells.count, 1, "the live row is kept as it landed")
        XCTAssertEqual(
            stack.model.benchmarkCells.map(\.stage),
            ["A", "A", "A", "A", "A", "B", "B"],
            "once the summary lands, its cells are the rows"
        )
    }

    func testAPayloadThatIsNotASummaryLeavesTheTypedValueEmpty() async throws {
        let stack = try makeStack(plan: try Fixtures.quickPlan)
        await stack.model.launch()
        stack.backend.enqueue(events: [
            JobEvent(
                seq: 1,
                type: .result,
                message: "quickbench finished",
                fraction: nil,
                payload: .object(["ended": .string("finished")])
            ),
            done(2),
        ])

        await stack.model.quickbench(repo: quickbenchRepo)

        XCTAssertNil(stack.model.summary, "a summary the client cannot type is never a half one")
        XCTAssertNotNil(stack.model.summaryData, "nor is its payload lost")
    }

    // MARK: - AC-6 (05-05) · the busy reason names the pick, and models re-read their rows

    func testOneSlotReasonNamesThePickTitleAndFallsBackToTheRepoID() async throws {
        let stack = try makeStack(plan: try Fixtures.quickPlan)
        await stack.model.launch()

        stack.backend.enqueue(events: [progress(1, "Downloading", fraction: 0.1)], hold: true)
        let download = Task { await stack.model.download(repo: quickbenchRepo) }
        await waitUntil { stack.model.job?.events.count == 1 }
        XCTAssertEqual(
            stack.model.oneSlotReason,
            "Busy: download Qwen3.5 2B 4-bit is running",
            "the pick's title, not its repo id"
        )
        stack.backend.releaseJob([done(2)])
        await download.value

        stack.backend.enqueue(events: [progress(1, "Downloading", fraction: 0.1)], hold: true)
        let unknown = Task { await stack.model.download(repo: "org/no-such-row") }
        await waitUntil { stack.model.job?.events.count == 1 }
        XCTAssertEqual(stack.model.oneSlotReason, "Busy: download org/no-such-row is running")
        stack.backend.releaseJob([done(2)])
        await unknown.value
    }

    func testDownloadAndEvictReRequestRecommendations() async throws {
        let stack = try makeStack(plan: try Fixtures.quickPlan)
        await stack.model.launch()
        let initial = stack.backend.recommendationsRequestCount

        stack.backend.enqueue(events: [done(1)])
        await stack.model.download(repo: downloadRepo)
        XCTAssertEqual(stack.backend.recommendationsRequestCount, initial + 1)

        stack.backend.enqueue(events: [done(2)])
        await stack.model.evict(repo: downloadRepo)
        XCTAssertEqual(stack.backend.recommendationsRequestCount, initial + 2)

        stack.backend.enqueue(events: [done(3)])
        await stack.model.install(engine: "optiq")
        XCTAssertEqual(
            stack.backend.recommendationsRequestCount,
            initial + 2,
            "an install changes no model row"
        )
    }

    // MARK: - AC-4 · a plan is not a run

    func testPlanningStartsNothingAndStartRunsThePlannedRepo() async throws {
        let stack = try makeStack(plan: try Fixtures.quickPlan)
        await stack.model.launch()

        let planned = await stack.model.planBenchmark(repo: quickbenchRepo)
        XCTAssertTrue(planned)
        XCTAssertEqual(stack.model.quickPlan?.repo, quickbenchRepo)
        XCTAssertTrue(stack.backend.startedJobs.isEmpty, "the plan started a job")

        stack.backend.enqueue(events: [done(1)])
        await stack.model.startBenchmark()
        XCTAssertEqual(
            stack.backend.startedJobs.last?.args,
            .quickbench(repo: quickbenchRepo, osaurus: false)
        )
    }

    func testAPlanRefusalNamesTheBackendMessageAndStartsNothing() async throws {
        let stack = try makeStack()
        await stack.model.launch()

        let planned = await stack.model.planBenchmark(repo: downloadRepo)

        XCTAssertFalse(planned)
        XCTAssertNil(stack.model.quickPlan)
        XCTAssertEqual(stack.model.benchmarkRefusal?.code, "bad_args")
        XCTAssertTrue(stack.backend.startedJobs.isEmpty)
    }

    func testASlowPlanForThePreviousPickIsDropped() async throws {
        let suiteName = "ohyesmlx-plan-race-\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        addTeardownBlock { defaults.removePersistentDomain(forName: suiteName) }

        let stub = StubBackend(
            hardware: try Fixtures.hardware,
            engines: try Fixtures.engines,
            recommendations: try Fixtures.recommendations,
            plan: try Fixtures.quickPlan
        )
        let slowRepo = "mlx-community/a-slow-pick"
        let backend = SlowPlanBackend(inner: stub, slowRepo: slowRepo)
        let model = AppModel(backend: backend, defaults: defaults)
        await model.launch()

        let slow = Task { await model.planBenchmark(repo: slowRepo) }
        await waitUntil { backend.requestedRepos.contains(slowRepo) }
        let fastPlanned = await model.planBenchmark(repo: quickbenchRepo)
        let slowPlanned = await slow.value

        XCTAssertTrue(fastPlanned)
        XCTAssertFalse(slowPlanned, "the earlier pick's answer landed after the picker moved on")
        XCTAssertEqual(model.quickPlan?.repo, quickbenchRepo)
    }

    // MARK: - AC-2c · quit while a job runs offers Quit anyway

    func testQuitWhileAJobRunsOffersQuitAnyway() async throws {
        let runner = FakeRunner(outcome: .stillRunning)
        let stack = try makeStack(runner: runner)
        await stack.model.launch()

        stack.backend.enqueue(events: [progress(1, "Downloading", fraction: 0.1)], hold: true)
        let download = Task { await stack.model.download(repo: downloadRepo) }
        await waitUntil { stack.model.job != nil }

        await stack.model.requestQuit()
        XCTAssertEqual(runner.quitCalls, [true])
        XCTAssertTrue(stack.model.quitAnywayOffered)
        XCTAssertFalse(stack.model.shouldExit)
        XCTAssertEqual(runner.forceKills, 0)

        stack.model.quitAnyway()
        XCTAssertEqual(runner.forceKills, 1)
        XCTAssertTrue(stack.model.shouldExit)

        stack.backend.releaseJob([done(2)])
        await download.value
    }

    // MARK: - AC-2 · the sidebar's completion ticks

    func testStepCompletionTracksHardwareEnginesModelsAndBenchmark() async throws {
        let pick = Pick(
            modelID: "org/example-2b-4bit",
            title: "Example 2B",
            paramsB: 2,
            format: "mlx 4-bit",
            sizeBytes: 1_400_000_000,
            fit: "comfortable",
            fitBasis: "estimated",
            engines: ["mlxlm"],
            installNeeded: false,
            startHere: true,
            reason: "Fits with room to spare.",
            downloaded: true,
            measuredHere: nil
        )
        let downloaded = Recommendations(
            picks: [pick],
            excluded: [],
            unsupportedReason: nil
        )
        let stack = try makeStack(recommendations: downloaded, plan: try Fixtures.quickPlan)
        await stack.model.launch()

        XCTAssertTrue(stack.model.yourMacComplete)
        XCTAssertTrue(stack.model.enginesComplete)
        XCTAssertTrue(stack.model.modelsComplete)
        XCTAssertFalse(stack.model.benchmarkComplete)

        stack.backend.enqueue(events: [try result(seq: 1), done(2)])
        await stack.model.quickbench(repo: quickbenchRepo)
        XCTAssertTrue(stack.model.benchmarkComplete)
    }

    func testTheBenchmarkTickSurvivesALaterDownload() async throws {
        let stack = try makeStack(
            recommendations: Recommendations(picks: [], excluded: [], unsupportedReason: nil),
            plan: try Fixtures.quickPlan
        )
        await stack.model.launch()
        XCTAssertFalse(stack.model.benchmarkComplete)

        stack.backend.enqueue(events: [try result(seq: 1), done(2)])
        await stack.model.quickbench(repo: quickbenchRepo)
        XCTAssertTrue(stack.model.benchmarkComplete)

        stack.backend.enqueue(events: [done(1, "download finished")])
        await stack.model.download(repo: downloadRepo)
        XCTAssertEqual(stack.model.job?.kind, .download)
        XCTAssertTrue(stack.model.benchmarkComplete, "a later job took the Benchmark tick away")
    }

    func testAPickMeasuredHereTicksBenchmarkWithNoSummaryInThisSession() async throws {
        let stack = try makeStack()
        await stack.model.launch()

        XCTAssertNil(stack.model.summary)
        XCTAssertTrue(
            stack.model.benchmarkComplete,
            "a pick measured on this Mac is a finished benchmark"
        )
    }

    // MARK: - 05-05 · the stub scenarios render without a backend

    /// Each screenshot scenario drives the model to the screen it names, so a coordinator's
    /// screenshot is of a state the model really reached rather than of a preview that lies.
    func testEveryStubScenarioReachesItsScreen() async throws {
        for scenario in StubScenario.allCases {
            let model = scenario.makeModel()
            await scenario.drive(model)
            switch scenario {
            case .welcome, .unsupported, .couldntStart, .backendStopped:
                break
            case .engines, .enginesConsent, .enginesBusy, .enginesFailed:
                XCTAssertEqual(model.screen, .engines, scenario.rawValue)
            case .models:
                XCTAssertEqual(model.screen, .models, scenario.rawValue)
                XCTAssertFalse(model.downloadedPicks.isEmpty, "the picker has a default")
            case .modelsDownloading, .modelsLowDisk, .modelsMismatch:
                XCTAssertEqual(model.screen, .models, scenario.rawValue)
            case .benchmarkPlan:
                XCTAssertEqual(model.screen, .benchmark, scenario.rawValue)
                XCTAssertEqual(model.quickPlan?.repo, StubScenario.stubRepo, scenario.rawValue)
                XCTAssertTrue(model.benchmarkCells.isEmpty, "nothing has run in the plan frame")
            case .benchmarkRunning:
                XCTAssertEqual(model.screen, .benchmark, scenario.rawValue)
            case .resultsFinished, .resultsCancelled, .resultsBusyTie:
                XCTAssertEqual(model.screen, .results, scenario.rawValue)
                XCTAssertNotNil(model.summary, scenario.rawValue)
            case .interrupted:
                break
            }
        }
    }

    func testTheRunningScenarioHasItsStopControlsAndLiveCells() async throws {
        let model = StubScenario.benchmarkRunning.makeModel()
        await StubScenario.benchmarkRunning.drive(model)

        XCTAssertEqual(model.screen, .benchmark)
        XCTAssertEqual(model.job?.state, .running)
        XCTAssertEqual(model.liveCells.count, 3)
        XCTAssertEqual(model.liveCells.map(\.status), ["PASS", "PASS", "SKIPPED"])
        XCTAssertTrue(model.canStartJob == false, "the stop controls have the one slot")
    }

    func testTheFinishedResultsScenarioShowsABestAndTheCancelledOneDoesNot() async throws {
        let finished = StubScenario.resultsFinished.makeModel()
        await StubScenario.resultsFinished.drive(finished)
        XCTAssertEqual(finished.screen, .results)
        XCTAssertEqual(finished.summary?.ended, .finished)
        XCTAssertEqual(finished.summary?.best?.engine, "omlx")
        XCTAssertEqual(finished.summary?.best?.decodeTPS, 62.1)

        let cancelled = StubScenario.resultsCancelled.makeModel()
        await StubScenario.resultsCancelled.drive(cancelled)
        XCTAssertEqual(cancelled.screen, .results)
        XCTAssertEqual(cancelled.summary?.ended, .cancelled)
        XCTAssertNil(cancelled.summary?.best)
        XCTAssertEqual(
            cancelled.summary?.stageA.cells.map(\.status),
            ["PASS", "SKIPPED", "SKIPPED"],
            "the engine it never reached is SKIPPED, not missing"
        )
        XCTAssertEqual(
            cancelled.notEvictedLines,
            [
                "Left on disk: Qwen3.5 2B oQ4 (1.8\u{00A0}GB) — it was in use. "
                    + "You can remove it from Models."
            ]
        )
        XCTAssertTrue(
            cancelled.benchmarkCells.contains { $0.status == "ABORTED" },
            "the stopped cell is in the rows Results draws"
        )
    }

    func testTheDownloadingScenarioExposesTheByteCounters() async throws {
        let model = StubScenario.modelsDownloading.makeModel()
        await StubScenario.modelsDownloading.drive(model)
        await waitUntil { model.downloadProgress(repo: StubScenario.stubRepo) != nil }

        let counters = try XCTUnwrap(model.downloadProgress(repo: StubScenario.stubRepo))
        XCTAssertEqual(counters.total, 1_400_000_000)
        XCTAssertEqual(counters.done, 588_000_000)
        XCTAssertEqual(model.job?.fraction, 0.42)
    }

    func testTheLowDiskScenarioCarriesTheRefusalsOwnNumbers() async throws {
        let model = StubScenario.modelsLowDisk.makeModel()
        await StubScenario.modelsLowDisk.drive(model)

        let low = try XCTUnwrap(model.lowDisk[StubScenario.stubRepo])
        XCTAssertEqual(low.freeBytes, 39_000_000_000)
        XCTAssertEqual(low.neededBytes, 40_200_000_000)
        XCTAssertEqual(low.amountToFree, 1_200_000_000)
        XCTAssertEqual(model.hardware?.diskFreeBytes, 39_000_000_000, "the meter re-read the disk")
    }
}
