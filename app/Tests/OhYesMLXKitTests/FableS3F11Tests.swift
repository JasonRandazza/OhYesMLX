import Foundation
import XCTest
@testable import OhYesMLXKit

/// F11: `HTTPBackend.events` retries every error except `unknown_job`, forever. After the
/// backend has exited the port is closed, so the stream must end rather than reconnect for
/// the rest of the process.
private final class RefusingPortTransport: HTTPTransport, @unchecked Sendable {
    private let lock = NSLock()
    private var attempts = 0
    private var stopped = false

    var attemptCount: Int { lock.withLock { attempts } }

    /// Ends the loop through a path the events code already treats as terminal, so a failing
    /// test does not leave a reconnect loop running behind the rest of the suite.
    func stopRetrying() {
        lock.withLock { stopped = true }
    }

    func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        throw URLError(.cannotConnectToHost)
    }

    func lines(for request: URLRequest) async throws -> AsyncThrowingStream<String, Error> {
        if lock.withLock({ stopped }) {
            throw BackendError(code: "unknown_job", status: 404, message: "job unknown")
        }
        lock.withLock { attempts += 1 }
        throw URLError(.cannotConnectToHost)
    }
}

final class FableS3F11Tests: XCTestCase {
    func testEventsGivesUpOnARefusedPort() async throws {
        let transport = RefusingPortTransport()
        let backend = HTTPBackend(
            port: 51_234,
            token: BackendToken("token"),
            transport: transport,
            retryDelay: .milliseconds(2)
        )

        let finished = expectation(description: "the events stream ends after a refused connection")
        let consumer = Task {
            do {
                for try await _ in backend.events(jobID: "job", after: nil) {}
            } catch {}
            finished.fulfill()
        }

        await fulfillment(of: [finished], timeout: 0.5)
        let attempts = transport.attemptCount

        transport.stopRetrying()
        consumer.cancel()
        _ = await consumer.result

        XCTAssertLessThan(
            attempts,
            30,
            "events reconnected \(attempts) times in half a second to a port nothing is listening on"
        )
    }
}
