import XCTest

@testable import OhYesMLXKit

/// Records the `jobRunning` each quit was asked with, so a quit during the window between a
/// job's `error` and its `done` can be read back.
final class FableS3F5Runner: BackendRunner, @unchecked Sendable {
    let endpoint = BackendEndpoint(port: 1, token: BackendToken("t"))

    private let lock = NSLock()
    private var arguments: [Bool] = []

    var stderrTail: [String] { [] }
    var isRunning: Bool { true }
    var onExit: (@Sendable (Int32, [String]) -> Void)?

    var quitCalls: [Bool] { lock.withLock { arguments } }

    func quit(jobRunning: Bool) async -> QuitOutcome {
        lock.withLock { arguments.append(jobRunning) }
        return .stillRunning
    }

    func forceKill() {}
}

/// S3-F5: `engines.py` sends `error`, runs `_rollback`, then `done`. `server.py` frees the one
/// job slot only when `done` is stored. `AppModel.apply` flips the job to `.cancelled`/`.failed`
/// at `error`, which makes `canStartJob` true and `requestQuit` pass `jobRunning: false` while
/// the backend is still inside rollback and still holding the slot.
@MainActor
final class FableS3F5Tests: XCTestCase {
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

    func testTheJobIsStillRunningDuringTheRollbackThatFollowsAnError() async throws {
        let suiteName = "fable-s3-f5-\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        addTeardownBlock { defaults.removePersistentDomain(forName: suiteName) }

        let backend = StubBackend(
            hardware: try Fixtures.hardware,
            engines: try Fixtures.engines,
            recommendations: try Fixtures.recommendations
        )
        let runner = FableS3F5Runner()
        let model = AppModel(
            backend: backend,
            runner: runner,
            defaults: defaults,
            bundlePath: "/Applications/OhYesMLX.app"
        )
        await model.launch()
        model.installConsent = true

        // An install that failed at a step: `error` first, then `_rollback`, then `done`.
        backend.enqueue(
            events: [
                JobEvent(
                    seq: 1,
                    type: .error,
                    message: "the install of optiq was cancelled",
                    fraction: nil,
                    payload: .object(["code": .string("cancelled")])
                )
            ],
            hold: true
        )
        let install = Task { await model.install(engine: "optiq") }
        await waitUntil { model.job?.events.contains { $0.type == .error } == true }

        // The window: `error` has landed, `done` has not, the backend's one slot is still held.
        XCTAssertFalse(
            model.job?.events.contains { $0.type == .done } ?? true,
            "the pause must be before `done`"
        )
        XCTAssertFalse(model.canStartJob, "another job is offered while the backend rolls back")
        XCTAssertNotNil(model.oneSlotReason)

        await model.requestQuit()
        XCTAssertEqual(
            runner.quitCalls,
            [true],
            "a quit during rollback must be told a job is running"
        )

        backend.releaseJob([
            JobEvent(seq: 2, type: .done, message: "install cancelled; nothing else was run", fraction: nil, payload: nil)
        ])
        await install.value
    }
}
