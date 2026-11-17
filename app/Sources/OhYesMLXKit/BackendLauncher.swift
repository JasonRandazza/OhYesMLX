import AppKit
import Darwin
import Foundation

public enum LaunchOutcome: Sendable {
    case running(RunningBackend)
    case couldntStart(String)
    /// `app.lock` is held and another instance of this app is running: activate it and exit.
    case alreadyRunning
    /// `app.lock` is held and no other instance of this app is running: a previous session's
    /// backend is still unwinding (S3-F8). The app says so and offers **Check again**.
    case stillFinishing
}

public enum QuitOutcome: Sendable, Equatable {
    case exited
    case terminated
    case killed
    case stillRunning
}

public struct QuitTiming: Sendable, Equatable {
    public var grace: TimeInterval
    public var terminateGrace: TimeInterval
    public var jobBound: TimeInterval

    public init(grace: TimeInterval, terminateGrace: TimeInterval, jobBound: TimeInterval) {
        self.grace = grace
        self.terminateGrace = terminateGrace
        self.jobBound = jobBound
    }

    public static let standard = QuitTiming(grace: 10, terminateGrace: 5, jobBound: 150)
}

public protocol LauncherProcess: AnyObject, Sendable {
    var isRunning: Bool { get }
    var stdin: FileHandle? { get }
    var stdout: FileHandle? { get }
    var stderr: FileHandle? { get }
    var onTermination: (@Sendable (Int32) -> Void)? { get set }
    func run(argv: [String], environment: [String: String], directory: URL) throws
    func terminate()
    func kill()
    func waitForExit(timeout: TimeInterval) -> Bool
}

public protocol BackendRunner: AnyObject, Sendable {
    var endpoint: BackendEndpoint { get }
    var stderrTail: [String] { get }
    var isRunning: Bool { get }
    var onExit: (@Sendable (Int32, [String]) -> Void)? { get set }
    func quit(jobRunning: Bool) async -> QuitOutcome
    func forceKill()
}

public final class FoundationLauncherProcess: LauncherProcess, @unchecked Sendable {
    private let process = Process()
    private let inputPipe = Pipe()
    private let outputPipe = Pipe()
    private let errorPipe = Pipe()
    private let lock = NSLock()
    private var storedTerminationHandler: (@Sendable (Int32) -> Void)?

    public init() {}

    public var isRunning: Bool { process.isRunning }

    public var stdin: FileHandle? { inputPipe.fileHandleForWriting }

    public var stdout: FileHandle? { outputPipe.fileHandleForReading }

    public var stderr: FileHandle? { errorPipe.fileHandleForReading }

    public var onTermination: (@Sendable (Int32) -> Void)? {
        get { lock.withLock { storedTerminationHandler } }
        set {
            lock.withLock { storedTerminationHandler = newValue }
            if let newValue {
                process.terminationHandler = { finished in
                    newValue(finished.terminationStatus)
                }
            } else {
                process.terminationHandler = nil
            }
        }
    }

    public func run(argv: [String], environment: [String: String], directory: URL) throws {
        process.executableURL = URL(fileURLWithPath: argv[0])
        process.arguments = Array(argv.dropFirst())
        process.environment = environment
        process.currentDirectoryURL = directory
        process.standardInput = inputPipe
        process.standardOutput = outputPipe
        process.standardError = errorPipe
        try process.run()
    }

    public func terminate() {
        process.terminate()
    }

    public func kill() {
        // S3-F16: once `Process` has reaped the child its pid is free for reuse, and a SIGKILL
        // to it would land on whatever took the number. A pidfd would close the remaining
        // check-to-signal window; Foundation's `Process` exposes none.
        guard process.isRunning else { return }
        Darwin.kill(process.processIdentifier, SIGKILL)
    }

    public func waitForExit(timeout: TimeInterval) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while process.isRunning {
            if Date() >= deadline { return false }
            Thread.sleep(forTimeInterval: 0.02)
        }
        return true
    }
}

public final class BackendLauncher: @unchecked Sendable {
    public typealias ProcessFactory = @Sendable () throws -> any LauncherProcess

    public static let pathForChild = "/usr/bin:/bin:/usr/sbin:/sbin"
    public static let inheritedKeys = ["HOME", "USER", "LOGNAME", "TMPDIR", "LANG"]

    private let environment: [String: String]
    private let appSupportDirectory: URL
    private let productionInterpreter: URL
    private let processFactory: ProcessFactory
    private let timing: QuitTiming
    private let launchTimeout: TimeInterval
    private let otherInstanceRunning: @Sendable () -> Bool

    public init(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        appSupportDirectory: URL = BackendLauncher.defaultAppSupportDirectory(),
        productionInterpreter: URL = BackendLauncher.bundledInterpreter(),
        processFactory: @escaping ProcessFactory = { FoundationLauncherProcess() },
        timing: QuitTiming = .standard,
        launchTimeout: TimeInterval = 30,
        otherInstanceRunning: @escaping @Sendable () -> Bool = BackendLauncher.anotherInstanceIsRunning
    ) {
        self.environment = environment
        self.appSupportDirectory = appSupportDirectory
        self.productionInterpreter = productionInterpreter
        self.processFactory = processFactory
        self.timing = timing
        self.launchTimeout = launchTimeout
        self.otherInstanceRunning = otherInstanceRunning
    }

    /// Whether another process with this app's bundle id is running. False without a bundle id.
    public static func anotherInstanceIsRunning() -> Bool {
        guard let bundleID = Bundle.main.bundleIdentifier else { return false }
        let me = ProcessInfo.processInfo.processIdentifier
        return NSRunningApplication.runningApplications(withBundleIdentifier: bundleID)
            .contains { $0.processIdentifier != me }
    }

    public static func defaultAppSupportDirectory() -> URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library")
            .appendingPathComponent("Application Support")
            .appendingPathComponent("OhYesMLX")
    }

    public static func bundledInterpreter() -> URL {
        URL(fileURLWithPath: Bundle.main.bundlePath)
            .appendingPathComponent("Contents")
            .appendingPathComponent("Resources")
            .appendingPathComponent("python")
            .appendingPathComponent("bin")
            .appendingPathComponent("python3")
    }

    public func start() async -> LaunchOutcome {
        let directory: URL
        do {
            directory = try prepareAppSupport()
        } catch {
            return .couldntStart("could not create \(appSupportDirectory.path): \(error.localizedDescription)")
        }

        guard let interpreter = resolveInterpreter() else {
            return .couldntStart(missingInterpreterMessage())
        }

        // The backend owns app.lock (P5-7); this probe only saves a spawn when it is held.
        switch probeLock() {
        case .free:
            break
        case .held:
            return heldOutcome()
        case .failed(let message):
            return .couldntStart(message)
        }

        let process: any LauncherProcess
        do {
            process = try processFactory()
        } catch {
            return .couldntStart("could not create the backend process: \(error.localizedDescription)")
        }

        let session = LaunchSession(process: process, timing: timing)
        // -B: never write bytecode into the bundle; it is signed and may be on a read-only
        // volume (P5-6). The bundle's own modules are precompiled at build time.
        let argv = [
            interpreter.path, "-I", "-B", "-m", "ohyesmlx.cli", "app",
            "--lock-dir", appSupportDirectory.path,
        ]
        do {
            try process.run(argv: argv, environment: childEnvironment(), directory: directory)
        } catch {
            session.abandon()
            return .couldntStart("could not start \(interpreter.path): \(error.localizedDescription)")
        }
        session.startReading()

        let line = await session.awaitLaunchLine(timeout: launchTimeout)
        if let data = line?.data(using: .utf8),
           let refusal = try? JSONDecoder().decode(LockRefusal.self, from: data),
           refusal.error.code == "already_running" {
            // The lock was taken between the probe and the backend's own flock.
            session.abandon()
            return heldOutcome()
        }
        guard let line,
              let data = line.data(using: .utf8),
              let parsed = try? JSONDecoder().decode(LaunchLine.self, from: data)
        else {
            let tail = session.stderrTail
            session.abandon()
            let reason = line == nil
                ? "the backend did not print its launch line"
                : "the backend's launch line could not be read"
            let joined = tail.isEmpty ? reason : reason + "\n" + tail.joined(separator: "\n")
            return .couldntStart(joined)
        }

        let endpoint = BackendEndpoint(port: parsed.port, token: BackendToken(parsed.token))
        return .running(RunningBackend(endpoint: endpoint, session: session))
    }

    public func childEnvironment() -> [String: String] {
        var result = ["PATH": Self.pathForChild]
        for key in Self.inheritedKeys {
            if let value = environment[key] {
                result[key] = value
            }
        }
        return result
    }

    public func resolveInterpreter() -> URL? {
        let fileManager = FileManager.default
        if fileManager.isExecutableFile(atPath: productionInterpreter.path) {
            return productionInterpreter
        }
        if let development = environment["OYMLX_DEV_PYTHON"], !development.isEmpty {
            if fileManager.isExecutableFile(atPath: development) {
                return URL(fileURLWithPath: development)
            }
        }
        return nil
    }

    public func missingInterpreterMessage() -> String {
        let production = "the bundled Python at \(productionInterpreter.path)"
        guard let development = environment["OYMLX_DEV_PYTHON"], !development.isEmpty else {
            return "could not find \(production), and OYMLX_DEV_PYTHON is not set"
        }
        return "could not find \(production), and OYMLX_DEV_PYTHON names \(development), which is not executable"
    }

    private func prepareAppSupport() throws -> URL {
        let fileManager = FileManager.default
        var isDirectory: ObjCBool = false
        if !fileManager.fileExists(atPath: appSupportDirectory.path, isDirectory: &isDirectory) {
            try fileManager.createDirectory(
                at: appSupportDirectory,
                withIntermediateDirectories: true,
                attributes: [.posixPermissions: 0o700]
            )
        }
        return appSupportDirectory
    }

    private enum LockProbe {
        case free
        case held
        case failed(String)
    }

    /// Takes and at once releases `app.lock`. Only EWOULDBLOCK means another holder (S3-F14);
    /// any other failure is the errno text, so it reaches the couldn't-start screen.
    private func probeLock() -> LockProbe {
        let path = appSupportDirectory.appendingPathComponent("app.lock").path
        let descriptor = open(path, O_CREAT | O_RDWR | O_CLOEXEC, S_IRUSR | S_IWUSR)
        guard descriptor >= 0 else {
            return .failed("could not open \(path): \(String(cString: strerror(errno)))")
        }
        defer { close(descriptor) }
        guard flock(descriptor, LOCK_EX | LOCK_NB) == 0 else {
            let code = errno
            if code == EWOULDBLOCK { return .held }
            return .failed("could not lock \(path): \(String(cString: strerror(code)))")
        }
        flock(descriptor, LOCK_UN)
        return .free
    }

    private func heldOutcome() -> LaunchOutcome {
        otherInstanceRunning() ? .alreadyRunning : .stillFinishing
    }
}

final class LaunchSession: @unchecked Sendable {
    private let process: any LauncherProcess
    private let timing: QuitTiming
    private let lock = NSLock()

    private var stderrRing: [String] = []
    private var pendingLine: String?
    private var lineWaiter: CheckedContinuation<String?, Never>?
    private var lineDelivered = false
    private var timedOut = false
    private var eof = false
    private var exited = false
    private var status: Int32 = 0
    private var storedExitHandler: (@Sendable (Int32, [String]) -> Void)?
    private var stdinClosed = false

    init(process: any LauncherProcess, timing: QuitTiming) {
        self.process = process
        self.timing = timing
        process.onTermination = { [weak self] status in
            self?.handleTermination(status: status)
        }
    }

    var isRunning: Bool { process.isRunning }

    var exitStatus: Int32? {
        lock.withLock { exited ? status : nil }
    }

    var stderrTail: [String] {
        lock.withLock { stderrRing }
    }

    var exitHandlerSnapshot: (@Sendable (Int32, [String]) -> Void)? {
        lock.withLock { storedExitHandler }
    }

    func startReading() {
        if let stdout = process.stdout {
            DispatchQueue.global(qos: .utility).async { [weak self] in
                self?.readLines(from: stdout, isStdout: true)
            }
        }
        if let stderr = process.stderr {
            DispatchQueue.global(qos: .utility).async { [weak self] in
                self?.readLines(from: stderr, isStdout: false)
            }
        }
    }

    func awaitLaunchLine(timeout: TimeInterval) async -> String? {
        await withCheckedContinuation { continuation in
            lock.lock()
            if let pending = pendingLine {
                pendingLine = nil
                lineDelivered = true
                lock.unlock()
                continuation.resume(returning: pending)
                return
            }
            if eof {
                lock.unlock()
                continuation.resume(returning: nil)
                return
            }
            lineWaiter = continuation
            lock.unlock()
            DispatchQueue.global().asyncAfter(deadline: .now() + timeout) { [weak self] in
                self?.timeOutLaunchLine()
            }
        }
    }

    func installExitHandler(_ handler: (@Sendable (Int32, [String]) -> Void)?) {
        var fire = false
        var currentStatus: Int32 = 0
        var tail: [String] = []
        lock.lock()
        storedExitHandler = handler
        if exited {
            fire = true
            currentStatus = status
            tail = stderrRing
        }
        lock.unlock()
        if fire {
            handler?(currentStatus, tail)
        }
    }

    func closeStdin() {
        let handle: FileHandle? = lock.withLock {
            if stdinClosed { return nil }
            stdinClosed = true
            return process.stdin
        }
        try? handle?.close()
    }

    func quitWait(jobRunning: Bool) -> QuitOutcome {
        closeStdin()
        if jobRunning {
            if process.waitForExit(timeout: timing.jobBound) {
                return .exited
            }
            return .stillRunning
        }
        if process.waitForExit(timeout: timing.grace) {
            return .exited
        }
        process.terminate()
        if process.waitForExit(timeout: timing.terminateGrace) {
            return .terminated
        }
        process.kill()
        _ = process.waitForExit(timeout: 2)
        return .killed
    }

    func forceKill() {
        let alreadyExited = lock.withLock { () -> Bool in
            stdinClosed = true
            return exited
        }
        // A backend that has exited is never signalled: its pid may already be someone else's.
        guard !alreadyExited, process.isRunning else { return }
        process.kill()
    }

    func abandon() {
        closeStdin()
        if process.isRunning {
            process.terminate()
        }
        if !process.waitForExit(timeout: 0.5) {
            process.kill()
            _ = process.waitForExit(timeout: 1)
        }
    }

    private func readLines(from handle: FileHandle, isStdout: Bool) {
        var buffer = Data()
        while true {
            let chunk = handle.availableData
            if chunk.isEmpty { break }
            buffer.append(chunk)
            while let index = buffer.firstIndex(of: 0x0A) {
                let raw = buffer[buffer.startIndex..<index]
                buffer.removeSubrange(buffer.startIndex...index)
                let line = String(decoding: raw, as: UTF8.self)
                if isStdout {
                    deliverLine(line)
                } else {
                    appendStderr(line)
                }
            }
        }
        if !buffer.isEmpty {
            let line = String(decoding: buffer, as: UTF8.self)
            if isStdout {
                deliverLine(line)
            } else {
                appendStderr(line)
            }
        }
        if isStdout {
            stdoutEnded()
        }
    }

    func deliverLine(_ line: String) {
        lock.lock()
        if lineDelivered || timedOut {
            lock.unlock()
            return
        }
        if let waiter = lineWaiter {
            lineWaiter = nil
            lineDelivered = true
            lock.unlock()
            waiter.resume(returning: line)
        } else {
            // The FIRST stdout line is the launch line: a later line never overwrites a
            // pending one.
            if pendingLine == nil {
                pendingLine = line
            }
            lock.unlock()
        }
    }

    private func appendStderr(_ line: String) {
        lock.lock()
        stderrRing.append(line)
        if stderrRing.count > 200 {
            stderrRing.removeFirst(stderrRing.count - 200)
        }
        lock.unlock()
    }

    private func stdoutEnded() {
        lock.lock()
        eof = true
        let waiter = (lineDelivered || timedOut || pendingLine != nil) ? nil : lineWaiter
        if waiter != nil {
            lineWaiter = nil
        }
        lock.unlock()
        waiter?.resume(returning: nil)
    }

    private func timeOutLaunchLine() {
        lock.lock()
        guard !lineDelivered, !timedOut else {
            lock.unlock()
            return
        }
        timedOut = true
        let waiter = lineWaiter
        lineWaiter = nil
        lock.unlock()
        waiter?.resume(returning: nil)
    }

    private func handleTermination(status: Int32) {
        let handler: (@Sendable (Int32, [String]) -> Void)?
        let tail: [String]
        lock.lock()
        if exited {
            lock.unlock()
            return
        }
        exited = true
        self.status = status
        handler = storedExitHandler
        tail = stderrRing
        lock.unlock()
        handler?(status, tail)
    }
}

public final class RunningBackend: BackendRunner, @unchecked Sendable {
    public let endpoint: BackendEndpoint
    private let session: LaunchSession

    init(endpoint: BackendEndpoint, session: LaunchSession) {
        self.endpoint = endpoint
        self.session = session
    }

    public var stderrTail: [String] { session.stderrTail }

    public var isRunning: Bool { session.isRunning }

    public var exitStatus: Int32? { session.exitStatus }

    public var onExit: (@Sendable (Int32, [String]) -> Void)? {
        get { session.exitHandlerSnapshot }
        set { session.installExitHandler(newValue) }
    }

    public func quit(jobRunning: Bool) async -> QuitOutcome {
        await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async { [session] in
                continuation.resume(returning: session.quitWait(jobRunning: jobRunning))
            }
        }
    }

    public func forceKill() {
        session.forceKill()
    }
}

private struct LaunchLine: Decodable {
    let port: Int
    let token: String
}

/// The backend's refusal when another backend holds `app.lock` (P5-7); `holder_pid` is not read.
private struct LockRefusal: Decodable {
    struct Body: Decodable { let code: String }
    let error: Body
}
