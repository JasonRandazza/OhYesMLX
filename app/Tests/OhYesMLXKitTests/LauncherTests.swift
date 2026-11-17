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

    /// `isRunning` false with no termination callback delivered yet: the window in which
    /// `Process` has reaped the child but `handleTermination` has not run (S3-F16).
    func markExitedWithoutTermination() {
        lock.withLock { running = false }
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
        launchTimeout: TimeInterval = 2,
        otherInstance: Bool = false
    ) -> BackendLauncher {
        BackendLauncher(
            environment: environment(),
            appSupportDirectory: appSupport,
            productionInterpreter: URL(fileURLWithPath: "/nonexistent/bundled/python3"),
            processFactory: { factory.make() },
            timing: timing,
            launchTimeout: launchTimeout,
            otherInstanceRunning: { otherInstance }
        )
    }

    /// Holds `app.lock` in *appSupport* the way a live backend does; the descriptor is returned
    /// so the test can release it.
    private func holdLock(in appSupport: URL) throws -> Int32 {
        try FileManager.default.createDirectory(at: appSupport, withIntermediateDirectories: true)
        let descriptor = open(appSupport.appendingPathComponent("app.lock").path, O_CREAT | O_RDWR, 0o600)
        XCTAssertGreaterThanOrEqual(descriptor, 0)
        XCTAssertEqual(flock(descriptor, LOCK_EX | LOCK_NB), 0)
        return descriptor
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

        XCTAssertEqual(fake.argv, [
            "/usr/bin/true", "-I", "-B", "-m", "ohyesmlx.cli", "app", "--lock-dir", appSupport.path,
        ])
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

    func testTheFirstStdoutLineIsTheLaunchLineWhenTwoArriveBeforeTheAwait() async throws {
        let fake = FakeLauncherProcess()
        let session = LaunchSession(process: fake, timing: .standard)

        session.deliverLine("{\"port\": 43210, \"token\": \"launch-token\"}")
        session.deliverLine("a later stdout line")

        let line = await session.awaitLaunchLine(timeout: 2)
        XCTAssertEqual(line, "{\"port\": 43210, \"token\": \"launch-token\"}")
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

    /// P5-7: the backend holds app.lock; the launcher's probe holds nothing past its check.
    func testTheLauncherHoldsNoLockWhileItsBackendRuns() async throws {
        let fake = FakeLauncherProcess()
        let factory = LauncherFactory([fake])
        let appSupport = temporaryAppSupport()
        let backend = try await startRunning(makeLauncher(factory: factory, appSupport: appSupport), fake)
        defer { backend.forceKill() }

        let descriptor = try holdLock(in: appSupport)
        flock(descriptor, LOCK_UN)
        close(descriptor)
    }

    func testAHeldLockWithAnotherAppIsAlreadyRunningAndSpawnsNothing() async throws {
        let factory = LauncherFactory()
        let appSupport = temporaryAppSupport()
        let descriptor = try holdLock(in: appSupport)
        defer { close(descriptor) }

        let outcome = await makeLauncher(factory: factory, appSupport: appSupport, otherInstance: true).start()
        guard case .alreadyRunning = outcome else {
            XCTFail("expected alreadyRunning, got \(outcome)")
            return
        }
        XCTAssertEqual(factory.count, 0)
    }

    /// S3-F8: a crashed app's backend still holds the lock and no app is in front of it.
    func testAHeldLockWithNoOtherAppIsStillFinishingUntilItIsReleased() async throws {
        let secondProcess = FakeLauncherProcess()
        let factory = LauncherFactory([secondProcess])
        let appSupport = temporaryAppSupport()
        let launcher = makeLauncher(factory: factory, appSupport: appSupport)
        let descriptor = try holdLock(in: appSupport)

        let outcome = await launcher.start()
        guard case .stillFinishing = outcome else {
            XCTFail("expected stillFinishing, got \(outcome)")
            close(descriptor)
            return
        }
        XCTAssertEqual(factory.count, 0)

        flock(descriptor, LOCK_UN)
        close(descriptor)
        let backend = try await startRunning(launcher, secondProcess)
        defer { backend.forceKill() }
        XCTAssertEqual(factory.count, 1)
    }

    /// The lock taken between the probe and the backend's own flock: the backend's pinned
    /// refusal line maps the same way the probe does.
    func testTheBackendsRefusalLineMapsToStillFinishingOrAlreadyRunning() async throws {
        for otherInstance in [false, true] {
            let fake = FakeLauncherProcess()
            let factory = LauncherFactory([fake])
            let launcher = makeLauncher(
                factory: factory,
                appSupport: temporaryAppSupport(),
                otherInstance: otherInstance
            )
            fake.writeStdout("{\"error\": {\"code\": \"already_running\", \"holder_pid\": 4242}}\n")
            let outcome = await launcher.start()
            switch (outcome, otherInstance) {
            case (.stillFinishing, false), (.alreadyRunning, true):
                break
            default:
                XCTFail("otherInstance \(otherInstance): got \(outcome)")
            }
            XCTAssertFalse(fake.isRunning, "the refusing child was not reaped")
        }
    }

    /// The model shows "still finishing" in place of quitting, and **Check again** re-probes.
    @MainActor
    func testTheModelShowsStillFinishingAndCheckAgainReprobes() async throws {
        let factory = LauncherFactory()
        let appSupport = temporaryAppSupport()
        let descriptor = try holdLock(in: appSupport)
        defer { close(descriptor) }
        let model = AppModel(
            launcher: makeLauncher(factory: factory, appSupport: appSupport),
            bundlePath: "/Applications/OhYesMLX.app"
        )

        await model.launch()
        XCTAssertEqual(model.screen, .couldntStart)
        XCTAssertTrue(model.previousSessionFinishing)
        XCTAssertFalse(model.alreadyRunning)

        await model.relaunch()
        XCTAssertTrue(model.previousSessionFinishing)
        XCTAssertFalse(model.alreadyRunning)
        XCTAssertEqual(factory.count, 0)
    }

    /// S3-F14: only EWOULDBLOCK is a holder; an unopenable lock is couldn't-start with errno text.
    func testAnUnopenableLockIsCouldntStartWithTheErrnoText() async throws {
        let factory = LauncherFactory()
        let appSupport = temporaryAppSupport()
        try FileManager.default.createDirectory(
            at: appSupport.appendingPathComponent("app.lock"),
            withIntermediateDirectories: true
        )

        let outcome = await makeLauncher(factory: factory, appSupport: appSupport, otherInstance: true).start()
        guard case .couldntStart(let message) = outcome else {
            XCTFail("expected couldntStart, got \(outcome)")
            return
        }
        XCTAssertTrue(message.contains("Is a directory"), message)
        XCTAssertEqual(factory.count, 0)
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
