import Foundation
import XCTest
@testable import OhYesMLXKit

/// A backend whose `cancel` does not return until the test lets it. Everything else is the
/// ordinary stub, so the job's events flow exactly as they do in the app.
final class CancelGateBackend: Backend, @unchecked Sendable {
    private let inner: StubBackend
    private let lock = NSLock()
    private var entered = false
    private var released = false

    init(inner: StubBackend) {
        self.inner = inner
    }

    var didEnterCancel: Bool { lock.withLock { entered } }

    func releaseCancel() {
        lock.withLock { released = true }
    }

    func hardware() async throws -> Hardware { try await inner.hardware() }
    func engines() async throws -> [EngineStatus] { try await inner.engines() }
    func recommendations() async throws -> Recommendations { try await inner.recommendations() }

    func quickbenchPlan(repo: String) async throws -> QuickPlan {
        try await inner.quickbenchPlan(repo: repo)
    }

    func startJob(kind: JobKind, args: JobArgs) async throws -> String {
        try await inner.startJob(kind: kind, args: args)
    }

    func cancel(jobID: String, now: Bool) async throws {
        lock.withLock { entered = true }
        // Bounded so a failed test cannot leave this call suspended forever.
        let deadline = Date().addingTimeInterval(5)
        while !lock.withLock({ released }) && Date() < deadline {
            try? await Task.sleep(for: .milliseconds(5))
        }
        try await inner.cancel(jobID: jobID, now: now)
    }

    func events(jobID: String, after: Int?) -> AsyncThrowingStream<JobEvent, Error> {
        inner.events(jobID: jobID, after: after)
    }
}

/// S3-F4: `cancelJob` snapshots `job` before awaiting `backend.cancel` and writes that snapshot
/// back afterwards. A `done` processed during the await is then overwritten: the job becomes
/// active again with no further event coming, pinning the one slot busy.
@MainActor
final class FableS3F4Tests: XCTestCase {
    private let repo = "mlx-community/Qwen3.5-2B-4bit"

    func testACancelThatReturnsAfterDoneDoesNotReactivateTheJob() async throws {
        let suiteName = "ohyesmlx-fable-s3-f4-\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        defer { defaults.removePersistentDomain(forName: suiteName) }

        let stub = StubBackend(
            hardware: try Fixtures.hardware,
            engines: try Fixtures.engines,
            recommendations: try Fixtures.recommendations
        )
        let backend = CancelGateBackend(inner: stub)
        let model = AppModel(
            backend: backend,
            defaults: defaults,
            bundlePath: Bundle.main.bundlePath
        )
        await model.launch()

        // The job is running and its event stream is open, as at the end of a run.
        stub.enqueue(
            events: [
                JobEvent(
                    seq: 1,
                    type: .progress,
                    message: "Downloading",
                    fraction: 0.9,
                    payload: nil
                )
            ],
            hold: true
        )
        let job = Task { await model.download(repo: repo) }
        try await waitUntil { model.job != nil }

        // "Stop After This Cell" pressed just as the last cell is landing.
        let cancel = Task { await model.cancelJob(now: false) }
        try await waitUntil { backend.didEnterCancel }

        // `done` arrives while `backend.cancel` is still in flight.
        stub.releaseJob([
            JobEvent(seq: 2, type: .done, message: "download finished", fraction: nil, payload: nil)
        ])
        try await waitUntil { model.job?.state == .finished }
        XCTAssertEqual(
            model.job?.state,
            .finished,
            "the done event did not reach the model before the cancel returned"
        )

        backend.releaseCancel()
        await cancel.value
        await job.value

        XCTAssertEqual(
            model.job?.state,
            .finished,
            "cancelJob wrote back its pre-await snapshot and re-pinned a finished job to "
                + (model.job?.state.text ?? "nil")
        )
        XCTAssertTrue(
            model.job?.events.contains { $0.type == .done } ?? false,
            "the stale write discarded the done event that arrived during the await"
        )
        XCTAssertNil(model.oneSlotReason, "a finished job still pins the one job slot busy")
        XCTAssertTrue(model.canStartJob)
    }

    private struct WaitTimedOut: Error {}

    private func waitUntil(
        timeout: TimeInterval = 2,
        _ condition: @MainActor () -> Bool
    ) async throws {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if condition() { return }
            try? await Task.sleep(for: .milliseconds(5))
        }
        XCTFail("condition not met within \(timeout) s")
        throw WaitTimedOut()
    }
}
