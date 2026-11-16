import XCTest

@testable import OhYesMLXKit

/// A backend whose first `startJob` stays in the air until the test lets it go, and whose
/// later calls answer the way `server.py` does while another job holds the one slot.
final class FableS3F6Backend: Backend, @unchecked Sendable {
    private let inner: StubBackend
    private let lock = NSLock()
    private var calls = 0
    private var waiting = false
    private var pending: CheckedContinuation<String, Error>?

    init(inner: StubBackend) {
        self.inner = inner
    }

    var firstStartIsInTheAir: Bool { lock.withLock { waiting } }
    var startCalls: Int { lock.withLock { calls } }

    func startJob(kind: JobKind, args: JobArgs) async throws -> String {
        let index = lock.withLock { () -> Int in
            calls += 1
            return calls
        }
        if index == 1 {
            return try await withCheckedThrowingContinuation { continuation in
                lock.withLock {
                    pending = continuation
                    waiting = true
                }
            }
        }
        throw BackendError(code: "busy", status: 409, message: "Busy: another job is running")
    }

    func releaseFirstStart(jobID: String = "ffffffffffffffff") {
        let continuation = lock.withLock { () -> CheckedContinuation<String, Error>? in
            let value = pending
            pending = nil
            return value
        }
        continuation?.resume(returning: jobID)
    }

    func hardware() async throws -> Hardware { try await inner.hardware() }
    func engines() async throws -> [EngineStatus] { try await inner.engines() }

    func recommendations() async throws -> Recommendations {
        try await inner.recommendations()
    }

    func quickbenchPlan(repo: String) async throws -> QuickPlan {
        try await inner.quickbenchPlan(repo: repo)
    }

    func cancel(jobID: String, now: Bool) async throws {
        try await inner.cancel(jobID: jobID, now: now)
    }

    func events(jobID: String, after: Int?) -> AsyncThrowingStream<JobEvent, Error> {
        inner.events(jobID: jobID, after: after)
    }
}

/// S3-F6: `AppModel.start` writes or clears the crash record before `POST /jobs` has claimed
/// the slot. A second start that the backend refuses deletes the first start's record, and a
/// refused benchmark start has already wiped the run on screen while leaving the refusal where
/// only the Engines screen renders it.
@MainActor
final class FableS3F6Tests: XCTestCase {
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

    func testASecondStartWhileTheFirstIsInTheAirDeletesTheWinnersCrashRecord() async throws {
        let suiteName = "fable-s3-f6-\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        addTeardownBlock { defaults.removePersistentDomain(forName: suiteName) }

        let backend = FableS3F6Backend(
            inner: StubBackend(
                hardware: try Fixtures.hardware,
                engines: try Fixtures.engines,
                recommendations: try Fixtures.recommendations
            )
        )
        let model = AppModel(
            backend: backend,
            defaults: defaults,
            bundlePath: "/Applications/OhYesMLX.app"
        )
        await model.launch()
        XCTAssertEqual(model.screen, .welcome)
        model.installConsent = true

        let winner = Task { await model.install(engine: "optiq") }
        await waitUntil { backend.firstStartIsInTheAir }

        // `job` is set only once `POST /jobs` answers, so the model still believes the slot is
        // free and the reset plus `writeInflight` have both already run for this job.
        XCTAssertNil(model.job, "the job is not recorded until the POST answers")
        XCTAssertFalse(
            model.canStartJob,
            "a second start is offered while the first one is in the air"
        )
        XCTAssertNotNil(model.oneSlotReason)

        // A second control asks for a download; the backend refuses it the way it refuses any
        // second job.
        await model.download(repo: "mlx-community/Qwen3.5-2B-4bit")
        XCTAssertEqual(model.refusal?.code, "busy")
        XCTAssertEqual(
            model.modelRefusals["mlx-community/Qwen3.5-2B-4bit"]?.code, "busy",
            "the refusal belongs on the Models screen that asked"
        )
        XCTAssertEqual(backend.startCalls, 1, "the claim refuses a second start before any POST")

        // AC-4: the crash record is written only after the POST succeeds, so nothing exists
        // yet for the loser to delete, and the loser writes none of its own.
        XCTAssertNil(
            defaults.dictionary(forKey: "inflightJob"),
            "a crash record exists before the POST has claimed the slot"
        )

        backend.releaseFirstStart()
        await winner.value

        XCTAssertEqual(model.job?.state, .running)
        XCTAssertEqual(
            defaults.dictionary(forKey: "inflightJob")?["name"] as? String,
            "optiq",
            "a job is running with no crash record behind it"
        )
    }

    func testARefusedBenchmarkStartWipesTheRunOnScreenAndSetsNoBenchmarkRefusal() async throws {
        let suiteName = "fable-s3-f6-\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        addTeardownBlock { defaults.removePersistentDomain(forName: suiteName) }

        let stub = StubBackend(
            hardware: try Fixtures.hardware,
            engines: try Fixtures.engines,
            recommendations: try Fixtures.recommendations,
            plan: try Fixtures.quickPlan
        )
        let model = AppModel(
            backend: stub,
            defaults: defaults,
            bundlePath: "/Applications/OhYesMLX.app"
        )
        await model.launch()

        let summary = try JSONDecoder().decode(
            JSONValue.self,
            from: Fixtures.data("quickbench_summary_finished.json")
        )
        stub.enqueue(events: [
            JobEvent(
                seq: 1,
                type: .result,
                message: "quickbench finished",
                fraction: nil,
                payload: summary
            ),
            JobEvent(
                seq: 2,
                type: .done,
                message: "quickbench finished",
                fraction: nil,
                payload: nil
            ),
        ])
        await model.quickbench(repo: try Fixtures.quickPlan.repo)
        XCTAssertEqual(model.summary?.ended, .finished)
        XCTAssertNotNil(model.summaryData)
        XCTAssertEqual(model.screen, .results)

        stub.setError(
            BackendError(code: "busy", status: 409, message: "Busy: another job is running"),
            for: .startJob
        )
        await model.startBenchmark()

        XCTAssertEqual(model.refusal?.code, "busy")
        XCTAssertNotNil(
            model.summary,
            "a refused start cleared the run already on screen though nothing ran"
        )
        XCTAssertNotNil(model.summaryData)
        XCTAssertNotNil(
            model.benchmarkRefusal,
            "the Benchmark screen has no refusal to show for the start it refused"
        )
    }
}
