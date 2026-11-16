import Foundation
import XCTest

@testable import OhYesMLXKit

/// A child-process double that prints one launch line and stays alive, so the real
/// `LaunchSession` holds `app.lock` for the life of the test exactly as it does in the app.
final class FableS3F7Process: LauncherProcess, @unchecked Sendable {
    private let input = Pipe()
    private let output = Pipe()
    private let error = Pipe()
    private let lock = NSLock()
    private var running = false
    private var termination: (@Sendable (Int32) -> Void)?
    private let launchLine: String

    init(launchLine: String) {
        self.launchLine = launchLine
    }

    var stdin: FileHandle? { input.fileHandleForWriting }
    var stdout: FileHandle? { output.fileHandleForReading }
    var stderr: FileHandle? { error.fileHandleForReading }
    var isRunning: Bool { lock.withLock { running } }

    var onTermination: (@Sendable (Int32) -> Void)? {
        get { lock.withLock { termination } }
        set { lock.withLock { termination = newValue } }
    }

    func run(argv: [String], environment: [String: String], directory: URL) throws {
        lock.withLock { running = true }
        try? output.fileHandleForWriting.write(contentsOf: Data((launchLine + "\n").utf8))
    }

    func terminate() { exit(status: 15) }
    func kill() { exit(status: 9) }

    func waitForExit(timeout: TimeInterval) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if !isRunning { return true }
            Thread.sleep(forTimeInterval: 0.01)
        }
        return !isRunning
    }

    private func exit(status: Int32) {
        let handler: (@Sendable (Int32) -> Void)? = lock.withLock {
            guard running else { return nil }
            running = false
            return termination
        }
        try? output.fileHandleForWriting.close()
        handler?(status)
    }
}

/// S3-F7: the "couldn't start" screen's only button (`RootView.swift:22`) calls `relaunch()`,
/// and `relaunch()` starts a second backend without quitting the live one (`AppModel.swift:386-408`).
/// The first session still holds the `flock`, so the launcher answers `.alreadyRunning`
/// (`BackendLauncher.swift:170-172`, `:260-269`), the model records it, and `OhYesMLXApp.swift:40-49`
/// reads that as "another instance" and calls `NSApp.terminate` — the retry closes the app.
@MainActor
final class FableS3F7Tests: XCTestCase {
    func testRetryingFromCouldntStartDoesNotTreatTheLiveBackendAsASecondInstance() async throws {
        let fileManager = FileManager.default
        let root = fileManager.temporaryDirectory
            .appendingPathComponent("fable-s3-f7-\(UUID().uuidString)")
        let appSupport = root.appendingPathComponent("support")
        try fileManager.createDirectory(at: appSupport, withIntermediateDirectories: true)
        addTeardownBlock { try? fileManager.removeItem(at: root) }

        let interpreter = root.appendingPathComponent("python3")
        try Data("#!/bin/sh\nexit 0\n".utf8).write(to: interpreter)
        try fileManager.setAttributes(
            [.posixPermissions: 0o755],
            ofItemAtPath: interpreter.path
        )

        let child = FableS3F7Process(launchLine: #"{"port": 9, "token": "fable-s3-f7"}"#)
        let launcher = BackendLauncher(
            environment: [:],
            appSupportDirectory: appSupport,
            productionInterpreter: interpreter,
            processFactory: { child },
            timing: QuitTiming(grace: 0.2, terminateGrace: 0.2, jobBound: 0.2),
            launchTimeout: 2
        )

        let suiteName = "fable-s3-f7-\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        addTeardownBlock { defaults.removePersistentDomain(forName: suiteName) }

        let model = AppModel(
            backend: StubBackend(
                hardware: try Fixtures.hardware,
                engines: try Fixtures.engines,
                recommendations: try Fixtures.recommendations
            ),
            launcher: launcher,
            defaults: defaults,
            hardwareReadyTimeout: 0.3,
            bundlePath: "/Applications/OhYesMLX.app"
        )

        // Launch 1: the child prints a launch line and is adopted; nothing listens on port 9,
        // so the hardware poll times out and the screen becomes "couldn't start" while the
        // runner — and the flock its LaunchSession holds — stays alive.
        await model.launch()
        XCTAssertEqual(model.screen, .couldntStart)
        XCTAssertTrue(
            child.isRunning,
            "the adopted backend is alive behind the couldn't-start screen"
        )

        // The user presses the screen's only button.
        await model.relaunch()

        XCTAssertFalse(
            model.alreadyRunning,
            "the retry took the app's own live backend for another instance; OhYesMLXApp.swift:40-49 "
                + "then activates it (itself) and calls NSApp.terminate, closing the retry"
        )
        XCTAssertEqual(
            model.screen,
            .couldntStart,
            "the retry neither re-ran reload() nor reported another failure; it left the app on "
                + "a launching screen it never completed"
        )

        model.quitAnyway()
    }
}
