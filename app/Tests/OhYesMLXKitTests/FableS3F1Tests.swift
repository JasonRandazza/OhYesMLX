import Foundation
import XCTest
@testable import OhYesMLXKit

/// Serves one SSE body through the real URL loading system so that
/// `URLSessionTransport.lines` — and therefore `URLSession.AsyncBytes.lines` — is
/// exercised exactly as it is in the app. Every other `events` test injects a
/// fake `HTTPTransport`, which never touches Foundation's line sequence.
final class FableS3F1Protocol: URLProtocol {
    static let progressJSON = makeEventJSON(seq: 1, message: "downloading")
    static let doneJSON = makeEventJSON(seq: 2, type: "done", message: "finished")
    static let body = Data(
        "id: 1\ndata: \(progressJSON)\n\nid: 2\ndata: \(doneJSON)\n\n".utf8
    )

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let url = request.url else {
            client?.urlProtocol(self, didFailWithError: URLError(.badURL))
            return
        }
        let response = HTTPURLResponse(
            url: url,
            statusCode: 200,
            httpVersion: "HTTP/1.1",
            headerFields: ["Content-Type": "text/event-stream"]
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Self.body)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

final class FableS3F1Tests: XCTestCase {
    private func makeSession() -> URLSession {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [FableS3F1Protocol.self]
        return URLSession(configuration: configuration)
    }

    /// The mechanism: SSE frames are separated by a blank line, so the parser
    /// dispatches only when the line stream yields `""`. If `bytes.lines`
    /// swallows it, this assertion fails on the real transport.
    func testRealURLSessionLinesKeepTheBlankFrameSeparator() async throws {
        let request = URLRequest(url: try XCTUnwrap(URL(string: "http://127.0.0.1:9/jobs/x/events")))
        let transport = URLSessionTransport(session: makeSession())

        var lines: [String] = []
        do {
            let stream = try await transport.lines(for: request)
            for try await line in stream {
                lines.append(line)
            }
        } catch {
            XCTFail("the real transport failed before a line arrived: \(error)")
            return
        }

        XCTAssertEqual(
            Array(lines.prefix(5)),
            [
                "id: 1",
                "data: \(FableS3F1Protocol.progressJSON)",
                "",
                "id: 2",
                "data: \(FableS3F1Protocol.doneJSON)",
            ],
            "URLSession.AsyncBytes.lines yielded \(lines)"
        )
    }

    /// The symptom: with no blank line, `SSEParser.consume` never dispatches, so
    /// no `JobEvent` reaches `AppModel.apply` and a `done` event never arrives.
    func testEventsOverTheRealTransportDispatchADoneEvent() async throws {
        let backend = HTTPBackend(
            port: 9,
            token: BackendToken("test-token"),
            transport: URLSessionTransport(session: makeSession()),
            retryDelay: .milliseconds(50)
        )
        let stream = backend.events(jobID: "0123456789abcdef", after: nil)

        let events: [JobEvent]
        do {
            events = try await withThrowingTaskGroup(of: [JobEvent].self) { group in
                group.addTask { try await Self.collectUntilDone(stream) }
                group.addTask {
                    try await Task.sleep(for: .seconds(3))
                    throw DeadlineExpired.expired
                }
                let first = try await group.next()!
                group.cancelAll()
                return first
            }
        } catch {
            XCTFail("no JobEvent reached the client within 3 s through the real transport: \(error)")
            return
        }

        XCTAssertEqual(
            events.map(\.seq),
            [1, 2],
            "the SSE frames were never dispatched; the client saw no event"
        )
        XCTAssertEqual(events.last?.type, .done)
    }

    private static func collectUntilDone(
        _ stream: AsyncThrowingStream<JobEvent, Error>
    ) async throws -> [JobEvent] {
        var events: [JobEvent] = []
        for try await event in stream {
            events.append(event)
            if event.type == .done { break }
        }
        return events
    }
}

private enum DeadlineExpired: Error {
    case expired
}
