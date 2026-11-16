import XCTest
@testable import OhYesMLXKit

/// Fable 5.2 S3-F16: `kill()` sent SIGKILL to `processIdentifier` with no check that the child was
/// still that process. Once `Process` has reaped it the pid is free for reuse, so a late
/// "Quit anyway" or escalation could SIGKILL whatever inherited the number.
final class FableS3F16Tests: XCTestCase {
    private func exitedSession(deliverTermination: Bool) throws -> (FakeLauncherProcess, LaunchSession) {
        let fake = FakeLauncherProcess()
        let session = LaunchSession(process: fake, timing: .standard)
        try fake.run(argv: ["/bin/true"], environment: [:], directory: URL(fileURLWithPath: "/"))
        if deliverTermination {
            fake.exit(status: 0)
        } else {
            fake.markExitedWithoutTermination()
        }
        XCTAssertFalse(fake.isRunning)
        return (fake, session)
    }

    func testForceKillSendsNothingToAnExitedBackend() throws {
        let (fake, session) = try exitedSession(deliverTermination: true)
        session.forceKill()
        XCTAssertEqual(fake.killCount, 0)
    }

    func testForceKillSendsNothingOnceIsRunningIsFalse() throws {
        let (fake, session) = try exitedSession(deliverTermination: false)
        session.forceKill()
        XCTAssertEqual(fake.killCount, 0)
    }

    func testAbandonSendsNothingToAnExitedBackend() throws {
        let (fake, session) = try exitedSession(deliverTermination: true)
        session.abandon()
        XCTAssertEqual(fake.killCount, 0)
        XCTAssertEqual(fake.terminateCount, 0)
    }

    func testForceKillStillKillsALiveBackend() throws {
        let fake = FakeLauncherProcess()
        let session = LaunchSession(process: fake, timing: .standard)
        try fake.run(argv: ["/bin/true"], environment: [:], directory: URL(fileURLWithPath: "/"))
        session.forceKill()
        XCTAssertEqual(fake.killCount, 1)
    }
}
