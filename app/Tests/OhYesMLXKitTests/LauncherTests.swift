import XCTest
@testable import OhYesMLXKit

final class FakeLauncherProcess: LauncherProcess, @unchecked Sendable {
    let input = Pipe()
    let output = Pipe()
    let error = Pipe()

    private let lock = NSLock()
    private var running = false
    private var termination: (@Sendable (Int32) -> Void)?
    private var recordedArgv: [String] = []
    private var recordedEnvironment: [String: String] = [:]
    private var recordedDirectory: URL?
    private var terminations = 0
    private var kills = 0
    private var exitSignal = DispatchSemaphore(value: 0)

    var terminateStops = false

    var argv: [String] { lock.withLock { recordedArgv } }
    var environment: [String: String] { lock.withLock { recordedEnvironment } }
    var directory: URL? { lock.withLock { recordedDirectory } }
    var terminateCount: Int { lock.withLock { terminations } }
    var killCount: Int { lock.withLock { kills } }
    var isRunning: Bool { lock.withLock { running } }

    var stdin: FileHandle? { input.fileHandleForWriting }
    var stdout: FileHandle? { output.fileHandleForReading }
    var stderr: FileHandle? { error.fileHandleForReading }

    var onTermination: (@Sendable (Int32) -> Void)? {
        get { lock.withLock { termination } }
        set { lock.withLock { termination = newValue } }
    }

    func run(argv: [String], environment: [String: String], directory: URL) throws {
        lock.withLock {
            recordedArgv = argv
            recordedEnvironment = environment
            recordedDirectory = directory
            running = true
        }
    }

    func terminate() {
        let stops = lock.withLock { () -> Bool in
            terminations += 1
            return terminateStops
        }
        if stops {
            exit(status: 15)
        }
    }

    func kill() {
        lock.withLock { kills += 1 }
        exit(status: 9)
    }

    func waitForExit(timeout: TimeInterval) -> Bool {
        if !isRunning { return true }
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if !isRunning { return true }
            _ = exitSignal.wait(timeout: .now() + 0.01)
        }
        return !isRunning
    }

    func exit(status: Int32) {
        let handler: (@Sendable (Int32) -> Void)? = lock.withLock {
            guard running else { return nil }
            running = false
            exitSignal.signal()
            return termination
        }
        handler?(status)
    }

    func writeStdout(_ text: String) {
        try? output.fileHandleForWriting.write(contentsOf: Data(text.utf8))
    }

    func writeStderr(_ text: String) {
        try? error.fileHandleForWriting.write(contentsOf: Data(text.utf8))
    }

    func closeStdout() {
        try? output.fileHandleForWriting.close()
    }
}

final class LauncherFactory: @unchecked Sendable {
    private let lock = NSLock()
    private var queued: [FakeLauncherProcess]
    private var made: [FakeLauncherProcess] = []

    init(_ fakes: [FakeLauncherProcess] = []) {
        queued = fakes
    }

    func make() -> any LauncherProcess {
        lock.withLock {
            let fake = queued.isEmpty ? FakeLauncherProcess() : queued.removeFirst()
            made.append(fake)
            return fake
        }
    }

    var count: Int { lock.withLock { made.count } }
    var fakes: [FakeLauncherProcess] { lock.withLock { made } }
    var last: FakeLauncherProcess? { lock.withLock { made.last } }
}

final class LauncherTests: XCTestCase {
    private var temporaryDirectories: [URL] = []

    override func tearDown() {
        for directory in temporaryDirectories {
            try? FileManager.default.removeItem(at: directory)
        }
        temporaryDirectories = []
        super.tearDown()
    }

    private func temporaryAppSupport() -> URL {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("ohyesmlx-launcher-\(UUID().uuidString)")
        temporaryDirectories.append(url)
        return url
    }

    private func environment() -> [String: String] {
        [
            "HOME": "/Users/tester",
            "USER": "tester",
            "LOGNAME": "tester",
            "TMPDIR": "/var/folders/test/",
            "LANG": "en_US.UTF-8",
            "PYTHONPATH": "/from/the/shell",
            "OYMLX_DEV_PYTHON": "/usr/bin/true",
        ]
    }

    private func makeLauncher(
        factory: LauncherFactory,
        appSupport: URL,
        timing: QuitTiming = .standard,
        launchTimeout: TimeInterval = 2
    ) -> BackendLauncher {
        BackendLauncher(
            environment: environment(),
            appSupportDirectory: appSupport,
            productionInterpreter: URL(fileURLWithPath: "/nonexistent/bundled/python3"),
            processFactory: { factory.make() },
            timing: timing,
            launchTimeout: launchTimeout
        )
    }

    private func startRunning(
        _ launcher: BackendLauncher,
        _ fake: FakeLauncherProcess,
        port: Int = 43_210
    ) async throws -> RunningBackend {
        fake.writeStdout("{\"port\": \(port), \"token\": \"launch-token\"}\n")
        let outcome = await launcher.start()
        guard case .running(let backend) = outcome else {
            XCTFail("expected a running backend, got \(outcome)")
            throw CancellationError()
        }
        return backend
    }

    private func waitUntil(
        timeout: TimeInterval = 2,
        _ condition: @escaping () -> Bool
    ) async {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if condition() { return }
            try? await Task.sleep(for: .milliseconds(10))
        }
    }

    func testArgvEnvironmentAndDirectory() async throws {
        let fake = FakeLauncherProcess()
        let factory = LauncherFactory([fake])
        let appSupport = temporaryAppSupport()
        let launcher = makeLauncher(factory: factory, appSupport: appSupport)
        let backend = try await startRunning(launcher, fake)
        defer { backend.forceKill() }

        XCTAssertEqual(fake.argv, ["/usr/bin/true", "-I", "-m", "ohyesmlx.cli", "app"])
        XCTAssertEqual(fake.environment, [
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": "/Users/tester",
            "USER": "tester",
            "LOGNAME": "tester",
            "TMPDIR": "/var/folders/test/",
            "LANG": "en_US.UTF-8",
        ])
        XCTAssertEqual(fake.directory?.path, appSupport.path)
        XCTAssertEqual(backend.endpoint.port, 43_210)
        XCTAssertEqual(backend.endpoint.token.raw, "launch-token")

        let attributes = try FileManager.default.attributesOfItem(atPath: appSupport.path)
        let mode = try XCTUnwrap(attributes[.posixPermissions] as? NSNumber)
        XCTAssertEqual(mode.intValue, 0o700)
    }

    func testChattyStderrStillYieldsTheLaunchLine() async throws {
        let fake = FakeLauncherProcess()
        let factory = LauncherFactory([fake])
        let launcher = makeLauncher(factory: factory, appSupport: temporaryAppSupport())

        fake.writeStdout("{\"port\": 43211, \"token\": \"launch-token\"}\n")
        let noise = String(repeating: "a chatty stderr line\n", count: 60_000)
        let startTask = Task { await launcher.start() }
        DispatchQueue.global().async {
            try? fake.error.fileHandleForWriting.write(contentsOf: Data(noise.utf8))
        }

        let outcome = await startTask.value
        guard case .running(let backend) = outcome else {
            XCTFail("expected a running backend, got \(outcome)")
            return
        }
        defer { backend.forceKill() }
        await waitUntil { backend.stderrTail.count == 200 }
        XCTAssertEqual(backend.stderrTail.count, 200)
        XCTAssertEqual(backend.stderrTail.last, "a chatty stderr line")
    }

    func testStdoutAfterTheLaunchLineIsDrainedAndDiscarded() async throws {
        let fake = FakeLauncherProcess()
        let factory = LauncherFactory([fake])
        let launcher = makeLauncher(factory: factory, appSupport: temporaryAppSupport())
        let backend = try await startRunning(launcher, fake)
        defer { backend.forceKill() }

        let noise = String(repeating: "stdout junk\n", count: 60_000)
        let writer = Task.detached {
            try? fake.output.fileHandleForWriting.write(contentsOf: Data(noise.utf8))
        }
        await writer.value

        XCTAssertEqual(backend.endpoint.port, 43_210)
        XCTAssertFalse(backend.stderrTail.contains { $0.contains("stdout junk") })
        XCTAssertTrue(backend.isRunning)
    }

    func testEOFBeforeTheLaunchLineIsCouldntStartWithTheStderrTail() async throws {
        let fake = FakeLauncherProcess()
        let factory = LauncherFactory([fake])
        let launcher = makeLauncher(factory: factory, appSupport: temporaryAppSupport())
        fake.terminateStops = true
        fake.writeStderr("fatal: no such module ohyesmlx\n")
        fake.closeStdout()

        let outcome = await launcher.start()
        guard case .couldntStart(let message) = outcome else {
            XCTFail("expected couldntStart, got \(outcome)")
            return
        }
        XCTAssertTrue(message.contains("fatal: no such module ohyesmlx"), message)
    }

    func testNoLaunchLineWithinTheTimeoutIsCouldntStart() async throws {
        let fake = FakeLauncherProcess()
        let factory = LauncherFactory([fake])
        let launcher = makeLauncher(
            factory: factory,
            appSupport: temporaryAppSupport(),
            launchTimeout: 0.1
        )
        fake.terminateStops = true
        fake.writeStderr("the backend is hanging\n")

        let outcome = await launcher.start()
        guard case .couldntStart(let message) = outcome else {
            XCTFail("expected couldntStart, got \(outcome)")
            return
        }
        XCTAssertTrue(message.contains("the backend did not print its launch line"), message)
        XCTAssertTrue(message.contains("the backend is hanging"), message)
        XCTAssertEqual(fake.terminateCount, 1)
    }

    func testMissingInterpreterNamesThePathLookedFor() async {
        let factory = LauncherFactory()
        let launcher = BackendLauncher(
            environment: ["HOME": "/Users/tester"],
            appSupportDirectory: temporaryAppSupport(),
            productionInterpreter: URL(fileURLWithPath: "/nonexistent/bundled/python3"),
            processFactory: { factory.make() }
        )

        let outcome = await launcher.start()
        guard case .couldntStart(let message) = outcome else {
            XCTFail("expected couldntStart, got \(outcome)")
            return
        }
        XCTAssertTrue(message.contains("/nonexistent/bundled/python3"), message)
        XCTAssertTrue(message.contains("OYMLX_DEV_PYTHON is not set"), message)
        XCTAssertEqual(factory.count, 0)
    }

    func testQuitWhileAJobRunsClosesStdinAndNeverSignals() async throws {
        let fake = FakeLauncherProcess()
        let factory = LauncherFactory([fake])
        let launcher = makeLauncher(
            factory: factory,
            appSupport: temporaryAppSupport(),
            timing: QuitTiming(grace: 0.05, terminateGrace: 0.05, jobBound: 0.1)
        )
        let backend = try await startRunning(launcher, fake)

        let outcome = await backend.quit(jobRunning: true)
        XCTAssertEqual(outcome, .stillRunning)
        XCTAssertEqual(fake.terminateCount, 0)
        XCTAssertEqual(fake.killCount, 0)

        let afterClose = try fake.input.fileHandleForReading.read(upToCount: 1)
        XCTAssertTrue(afterClose == nil || afterClose?.isEmpty == true)

        backend.forceKill()
        XCTAssertEqual(fake.killCount, 1)
    }

    func testQuitEscalatesGraceThenTerminateThenKill() async throws {
        let fake = FakeLauncherProcess()
        let factory = LauncherFactory([fake])
        let launcher = makeLauncher(
            factory: factory,
            appSupport: temporaryAppSupport(),
            timing: QuitTiming(grace: 0.05, terminateGrace: 0.05, jobBound: 1)
        )
        let backend = try await startRunning(launcher, fake)

        let outcome = await backend.quit(jobRunning: false)
        XCTAssertEqual(outcome, .killed)
        XCTAssertEqual(fake.terminateCount, 1)
        XCTAssertEqual(fake.killCount, 1)
    }

    func testQuitReturnsTerminatedWhenSigtermStopsTheBackend() async throws {
        let fake = FakeLauncherProcess()
        fake.terminateStops = true
        let factory = LauncherFactory([fake])
        let launcher = makeLauncher(
            factory: factory,
            appSupport: temporaryAppSupport(),
            timing: QuitTiming(grace: 0.05, terminateGrace: 0.2, jobBound: 1)
        )
        let backend = try await startRunning(launcher, fake)

        let outcome = await backend.quit(jobRunning: false)
        XCTAssertEqual(outcome, .terminated)
        XCTAssertEqual(fake.terminateCount, 1)
        XCTAssertEqual(fake.killCount, 0)
    }

    func testQuitReturnsExitedWhenTheBackendStopsItself() async throws {
        let fake = FakeLauncherProcess()
        let factory = LauncherFactory([fake])
        let launcher = makeLauncher(
            factory: factory,
            appSupport: temporaryAppSupport(),
            timing: QuitTiming(grace: 0.5, terminateGrace: 0.2, jobBound: 1)
        )
        let backend = try await startRunning(launcher, fake)

        let quit = Task { await backend.quit(jobRunning: false) }
        try await Task.sleep(for: .milliseconds(30))
        fake.exit(status: 0)
        let outcome = await quit.value
        XCTAssertEqual(outcome, .exited)
        XCTAssertEqual(fake.terminateCount, 0)
        XCTAssertEqual(fake.killCount, 0)
    }

    func testChildExitWhileRunningReportsStatusAndTheStderrTail() async throws {
        let fake = FakeLauncherProcess()
        let factory = LauncherFactory([fake])
        let launcher = makeLauncher(factory: factory, appSupport: temporaryAppSupport())
        let backend = try await startRunning(launcher, fake)

        let recorded = ExitRecord()
        let expectation = expectation(description: "the launcher reports the exit")
        backend.onExit = { status, tail in
            recorded.record(status: status, tail: tail)
            expectation.fulfill()
        }
        fake.writeStderr("the backend crashed\n")
        await waitUntil { backend.stderrTail.contains("the backend crashed") }
        fake.exit(status: 3)
        await fulfillment(of: [expectation], timeout: 2)

        XCTAssertEqual(recorded.status, 3)
        XCTAssertTrue(recorded.tail.contains("the backend crashed"), "\(recorded.tail)")
        XCTAssertEqual(backend.exitStatus, 3)
        XCTAssertFalse(backend.isRunning)
    }

    func testSecondLauncherIsAlreadyRunningAndSpawnsNothing() async throws {
        let firstProcess = FakeLauncherProcess()
        let secondProcess = FakeLauncherProcess()
        let factory = LauncherFactory([firstProcess, secondProcess])
        let appSupport = temporaryAppSupport()
        let first = makeLauncher(factory: factory, appSupport: appSupport)
        let second = makeLauncher(factory: factory, appSupport: appSupport)

        let firstBackend = try await startRunning(first, firstProcess)
        XCTAssertEqual(factory.count, 1)

        let secondOutcome = await second.start()
        guard case .alreadyRunning = secondOutcome else {
            XCTFail("expected alreadyRunning, got \(secondOutcome)")
            return
        }
        XCTAssertEqual(factory.count, 1)

        firstProcess.exit(status: 0)
        await waitUntil { !firstBackend.isRunning }

        let secondBackend = try await startRunning(second, secondProcess, port: 43_212)
        defer { secondBackend.forceKill() }
        XCTAssertEqual(factory.count, 2)
    }
}

final class ExitRecord: @unchecked Sendable {
    private let lock = NSLock()
    private var recordedStatus: Int32?
    private var recordedTail: [String] = []

    var status: Int32? { lock.withLock { recordedStatus } }
    var tail: [String] { lock.withLock { recordedTail } }

    func record(status: Int32, tail: [String]) {
        lock.withLock {
            recordedStatus = status
            recordedTail = tail
        }
    }
}
