import Foundation
import XCTest
@testable import OhYesMLXKit

/// F12(a): `requestQuit` leaves AppKit's `.terminateLater` unreplied to when the runner says
/// `.stillRunning`. If the backend then exits, `backendExited` only records `backendStopped`
/// and the app stays running with a quit it never finishes.
private final class StillRunningRunner: BackendRunner, @unchecked Sendable {
    let endpoint = BackendEndpoint(port: 43_210, token: BackendToken("token"))
    var stderrTail: [String] { [] }
    var isRunning: Bool { true }
    var onExit: (@Sendable (Int32, [String]) -> Void)?

    private let lock = NSLock()
    private var kills = 0

    var forceKillCount: Int { lock.withLock { kills } }

    func quit(jobRunning: Bool) async -> QuitOutcome { .stillRunning }

    func forceKill() {
        lock.withLock { kills += 1 }
    }
}

@MainActor
final class FableS3F12Tests: XCTestCase {
    func testBackendExitingWhileQuitAnywayOfferedCompletesTheQuit() async throws {
        let suiteName = "ohyesmlx-fable-s3-f12-\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        addTeardownBlock {
            defaults.removePersistentDomain(forName: suiteName)
        }
        let backend = StubBackend(
            hardware: try Fixtures.hardware,
            engines: try Fixtures.engines,
            recommendations: try Fixtures.recommendations
        )
        let runner = StillRunningRunner()
        let model = AppModel(backend: backend, runner: runner, defaults: defaults)
        var quitCompletions = 0
        model.onQuitComplete = { quitCompletions += 1 }

        await model.requestQuit()
        XCTAssertTrue(model.quitAnywayOffered, "the runner said still running")
        XCTAssertFalse(model.shouldExit)

        // The backend outlived its own shutdown bound and then exited.
        model.backendExited(status: 0, stderrTail: [])

        XCTAssertEqual(model.backendStopped, 0)
        XCTAssertTrue(
            model.shouldExit,
            "the app was asked to quit and the backend has now exited; it must not keep running"
        )
        XCTAssertEqual(
            quitCompletions,
            1,
            "AppKit's .terminateLater is only replied to through onQuitComplete"
        )
    }
}
