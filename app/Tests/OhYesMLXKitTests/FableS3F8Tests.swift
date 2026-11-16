import Darwin
import Foundation
import XCTest

@testable import OhYesMLXKit

/// S3-F8 claims the single-instance `flock` lives only in the app process
/// (`BackendLauncher.swift:260-269`, released when that descriptor closes, `:518-528`), so a
/// crashed or force-quit app frees `app.lock` while the backend it spawned is still unwinding
/// (`cli.py:1168` waits up to `server.JOB_SHUTDOWN_WAIT_S` = 120 s, then `JOB_KILL_GRACE_S` =
/// 15 s) and a relaunch starts a second backend beside it.
///
/// The claim only holds if the backend does not inherit the locked descriptor: `acquireLock`
/// opens it without `O_CLOEXEC`, but `FoundationLauncherProcess.run` (`:84-93`) hands the child
/// to Foundation's `Process`, whose close-on-exec behaviour decides the question. The test
/// therefore launches the real `BackendLauncher` with the real `FoundationLauncherProcess` and
/// a fake backend that reports its own descriptor table, then models the app's death by
/// `dup2`-ing `/dev/null` over the lock descriptor — the flock is released exactly as it is
/// when the process dies, and the descriptor number stays occupied so the still-live
/// `LaunchSession`'s later `close()` cannot land on an unrelated descriptor.
///
/// Corrected for the AC-12 design (05-08 Task 4): the backend owns `app.lock`, so the fake
/// backend takes it itself (from the `--lock-dir` the launcher passes) and prints the pinned
/// refusal when it cannot; the app holds no descriptor to lose; and a refusal with no other
/// app instance may come back as `.stillFinishing` as well as `.alreadyRunning`.
final class FableS3F8Tests: XCTestCase {
    func testAppDeathDoesNotFreeTheLockWhileTheBackendIsAlive() async throws {
        let fileManager = FileManager.default
        let root = fileManager.temporaryDirectory
            .appendingPathComponent("fable-s3-f8-\(UUID().uuidString)")
        let appSupport = root.appendingPathComponent("support")
        try fileManager.createDirectory(at: appSupport, withIntermediateDirectories: true)
        addTeardownBlock { try? fileManager.removeItem(at: root) }

        let firstInterpreter = try writeFakeBackend(root: root, name: "python3-first")
        let secondInterpreter = try writeFakeBackend(root: root, name: "python3-second")
        let lockPath = appSupport.appendingPathComponent("app.lock").path

        let firstLauncher = makeLauncher(interpreter: firstInterpreter, appSupport: appSupport)
        let firstOutcome = await firstLauncher.start()
        guard case .running(let firstBackend) = firstOutcome else {
            XCTFail("the first launch did not start: \(firstOutcome)")
            return
        }
        defer { firstBackend.forceKill() }

        let childReport = await readEventually(firstInterpreter.path + ".fds", timeout: 3)
        let childHoldsLock = childReport?.contains(lockPath) ?? false
        print("S3-F8: backend descriptor report mentions app.lock: \(childHoldsLock)")
        if let childReport {
            print("S3-F8: backend descriptor report:\n\(childReport)")
        } else {
            print("S3-F8: the backend wrote no descriptor report")
        }

        XCTAssertTrue(firstBackend.isRunning, "the fake backend died before the app-death check")

        // Control: while the app's descriptor is still held, the same second launcher is refused,
        // so a later `.running` means the descriptor's disappearance is what freed the lock.
        let secondLauncher = makeLauncher(interpreter: secondInterpreter, appSupport: appSupport)
        let controlOutcome = await secondLauncher.start()
        guard isRefusal(controlOutcome) else {
            XCTFail(
                "control failed: the second launch was not refused while the first session held "
                    + "app.lock: \(controlOutcome)"
            )
            return
        }

        // The app crashes: every descriptor it held on app.lock goes away.
        let replaced = replaceDescriptors(toPath: lockPath)
        XCTAssertEqual(
            replaced, 0,
            "the app holds an app.lock descriptor across the child's life; AC-12 gives it to the backend"
        )
        XCTAssertTrue(
            firstBackend.isRunning,
            "the backend must still be alive (stdin EOF starts its up-to-135 s job wait)"
        )

        let free = lockIsFree(lockPath)
        print("S3-F8: app.lock free after the app's death, backend still alive: \(String(describing: free))")

        if let free, !free, !childHoldsLock {
            XCTFail(
                "app.lock stayed held although the backend's descriptor report does not mention it; "
                    + "the test's model of the app's death is wrong and the result is inconclusive"
            )
        }

        let secondOutcome = await secondLauncher.start()

        switch secondOutcome {
        case .alreadyRunning, .stillFinishing:
            XCTAssertTrue(
                childHoldsLock,
                "alreadyRunning came back although the backend does not hold app.lock; "
                    + "the test's model of the app's death is wrong and the result is inconclusive"
            )
        case .running(let secondBackend):
            secondBackend.forceKill()
            XCTFail(
                "app.lock was free while the backend the dead app spawned was still alive "
                    + "(backend holds app.lock: \(childHoldsLock)); a relaunch starts a second backend "
                    + "beside it — S3-F8 reproduced"
            )
        case .couldntStart(let message):
            XCTFail("inconclusive: the second launch failed for another reason: \(message)")
        }
    }

    private func isRefusal(_ outcome: LaunchOutcome) -> Bool {
        switch outcome {
        case .alreadyRunning, .stillFinishing: return true
        case .running, .couldntStart: return false
        }
    }

    private func makeLauncher(interpreter: URL, appSupport: URL) -> BackendLauncher {
        BackendLauncher(
            environment: [:],
            appSupportDirectory: appSupport,
            productionInterpreter: interpreter,
            processFactory: { FoundationLauncherProcess() },
            timing: QuitTiming(grace: 0.3, terminateGrace: 0.3, jobBound: 0.3),
            launchTimeout: 8
        )
    }

    /// A backend double: takes `app.lock` in the `--lock-dir` it was given, as `ohyesmlx app`
    /// does, or prints the pinned refusal; then prints the launch line, records the descriptors
    /// it holds, and ignores stdin EOF (a plain `sleep`) long enough for the relaunch attempt.
    private func writeFakeBackend(root: URL, name: String) throws -> URL {
        let url = root.appendingPathComponent(name)
        let script = """
        #!/usr/bin/perl
        use Fcntl qw(:flock O_RDWR O_CREAT);
        $| = 1;
        my ($dir) = map { $ARGV[$_ + 1] } grep { $ARGV[$_] eq '--lock-dir' } 0..$#ARGV;
        sysopen(my $lock, "$dir/app.lock", O_RDWR | O_CREAT, 0600) or die "open: $!";
        unless (flock($lock, LOCK_EX | LOCK_NB)) {
          print qq({"error": {"code": "already_running", "holder_pid": null}}\n);
          exit 2;
        }
        print qq({"port": 43410, "token": "fable-s3-f8"}\n);
        system(qq({ lsof -p $$ -Ffn; echo END-OF-REPORT; } > '$0.fds.tmp' 2>/dev/null; mv '$0.fds.tmp' '$0.fds'));
        sleep 5;
        exit 0;
        """
        try Data(script.utf8).write(to: url)
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o755],
            ofItemAtPath: url.path
        )
        return url
    }

    private func readEventually(_ path: String, timeout: TimeInterval) async -> String? {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            // The script renames the finished report into place, so a partial read cannot occur.
            if let text = try? String(contentsOfFile: path, encoding: .utf8),
               text.contains("END-OF-REPORT") {
                return text
            }
            try? await Task.sleep(for: .milliseconds(50))
        }
        return nil
    }

    /// Replaces every descriptor of the test process that refers to *path* with `/dev/null`.
    ///
    /// This is what the kernel does to a dying process: the descriptor closes and the flock is
    /// released — unless another process inherited the same open file description, in which
    /// case the lock stays held. `dup2` keeps the number occupied so the live session's later
    /// `close()` cannot hit a descriptor the second launch opened in the meantime.
    private func replaceDescriptors(toPath path: String) -> Int32 {
        var target = stat()
        guard stat(path, &target) == 0 else { return -1 }
        let nullDescriptor = open("/dev/null", O_RDONLY)
        guard nullDescriptor >= 0 else { return -1 }
        defer { close(nullDescriptor) }

        var replaced: Int32 = 0
        let limit = Int32(min(getdtablesize(), 512))
        for descriptor in Int32(3)..<limit {
            if descriptor == nullDescriptor { continue }
            var candidate = stat()
            guard fstat(descriptor, &candidate) == 0 else { continue }
            guard candidate.st_mode & UInt16(S_IFMT) == UInt16(S_IFREG) else { continue }
            guard candidate.st_dev == target.st_dev, candidate.st_ino == target.st_ino else {
                continue
            }
            if dup2(nullDescriptor, descriptor) == descriptor {
                replaced += 1
            }
        }
        return replaced
    }

    /// Whether a fresh `flock` on *path* succeeds — a different open file description, so it
    /// answers whether any process still holds the lock.
    private func lockIsFree(_ path: String) -> Bool? {
        let descriptor = open(path, O_RDWR)
        guard descriptor >= 0 else { return nil }
        defer { close(descriptor) }
        guard flock(descriptor, LOCK_EX | LOCK_NB) == 0 else { return false }
        flock(descriptor, LOCK_UN)
        return true
    }
}
