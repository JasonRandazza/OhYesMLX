import Foundation
import XCTest
@testable import OhYesMLXKit

/// F14: `acquireLock` returns nil for an `open` failure and for every `flock` failure, and
/// `start` maps nil to `.alreadyRunning`. A lock path that cannot be opened at all is
/// reported as another instance and the app activates that (nonexistent) instance and quits.
final class FableS3F14Tests: XCTestCase {
    func testAppLockThatCannotBeOpenedIsNotAlreadyRunning() async throws {
        let support = FileManager.default.temporaryDirectory
            .appendingPathComponent("ohyesmlx-fable-s3-f14-\(UUID().uuidString)")
        // A directory where the lock file should be: open(2) fails with EISDIR.
        try FileManager.default.createDirectory(
            at: support.appendingPathComponent("app.lock"),
            withIntermediateDirectories: true
        )
        addTeardownBlock {
            try? FileManager.default.removeItem(at: support)
        }

        let launcher = BackendLauncher(
            environment: ["OYMLX_DEV_PYTHON": "/usr/bin/true"],
            appSupportDirectory: support,
            productionInterpreter: URL(fileURLWithPath: "/nonexistent/bundled/python3"),
            processFactory: { FakeLauncherProcess() },
            timing: .standard,
            launchTimeout: 1
        )

        switch await launcher.start() {
        case .alreadyRunning, .stillFinishing:
            XCTFail("a lock path that could not be opened was reported as another instance")
        case .couldntStart:
            break
        case .running:
            XCTFail("the launcher started a backend through an unusable lock path")
        }
    }
}
