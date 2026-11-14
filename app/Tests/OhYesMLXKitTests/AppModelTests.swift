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
        runner: (any BackendRunner)? = nil
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
        let model = AppModel(backend: backend, runner: runner, defaults: defaults)
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

    private func result(_ seq: Int, _ summary: [String: JSONValue]) -> JobEvent {
        JobEvent(
            seq: seq,
            type: .result,
            message: "quickbench finished",
            fraction: nil,
            payload: .object(summary)
        )
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
            progress(2, "stage A: mlxlm PASS", payload: .object(["engine": .string("mlxlm"), "status": .string("PASS")])),
            result(3, ["ended": .string("finished")]),
            done(4, "quickbench finished"),
        ])
        await stack.model.quickbench(repo: quickbenchRepo)
        XCTAssertEqual(stack.model.screen, .results)
        XCTAssertEqual(stack.model.summary?["ended"]?.stringValue, "finished")
        XCTAssertEqual(stack.backend.startedJobs.last?.args, .quickbench(repo: quickbenchRepo, osaurus: false))
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
                payload: .object(["engine": .string("mlxlm"), "skipped": .string("quit mlxlm first")])
            ),
            progress(
                3,
                "stage A: vmlx N/A: runtime 'vmlx' did not start: RuntimeStartError: could not start",
                payload: .object(["engine": .string("vmlx"), "status": .string("N/A")])
            ),
            progress(
                4,
                "stage A: osaurus SKIPPED: Osaurus was not allowed for this run (osaurus: false)",
                payload: .object(["engine": .string("osaurus"), "status": .string("SKIPPED")])
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
        let stack = try makeStack(hardware: unsupported)
        await stack.model.launch()

        XCTAssertEqual(stack.model.screen, .unsupported)
        XCTAssertEqual(stack.model.hardware?.unsupportedReason, "this Mac is not Apple silicon")

        stack.model.go(to: .welcome)
        XCTAssertEqual(stack.model.screen, .unsupported)
        stack.model.go(to: .models)
        XCTAssertEqual(stack.model.screen, .unsupported)

        stack.model.installConsent = true
        stack.backend.enqueue(events: [progress(1, "Preparing OptiQ", fraction: 0), done(2)])
        await stack.model.install(engine: "optiq")
        XCTAssertEqual(stack.model.screen, .unsupported)
        XCTAssertEqual(stack.backend.startedJobs.last?.args, .install(engine: "optiq"))
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
            result(1, ["ended": .string("finished"), "not_evicted": .array([.string(left)])]),
            done(2),
        ])

        await stack.model.quickbench(repo: quickbenchRepo)

        XCTAssertEqual(stack.model.notEvicted, [left])
        let line = try XCTUnwrap(stack.model.notEvictedLines.first)
        XCTAssertTrue(line.hasPrefix("Left on disk: LFM2.5 8B A1B MoE 4-bit"), line)
        XCTAssertTrue(line.contains("— it was in use. You can remove it from Models."), line)
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
}
