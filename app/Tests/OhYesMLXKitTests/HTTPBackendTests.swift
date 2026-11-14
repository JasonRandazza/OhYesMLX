import XCTest
@testable import OhYesMLXKit

final class FakeTransport: HTTPTransport, @unchecked Sendable {
    struct Response: Sendable {
        let status: Int
        let data: Data
    }

    enum ScriptLine: Sendable {
        case line(String)
        case failure(URLError.Code)
        case backendError(BackendError)
    }

    private let lock = NSLock()
    private var responses: [String: Response] = [:]
    private var scripts: [[ScriptLine]] = []
    private var recorded: [URLRequest] = []

    var requests: [URLRequest] {
        lock.withLock { recorded }
    }

    func setResponse(status: Int, data: Data, for path: String) {
        lock.withLock { responses[path] = Response(status: status, data: data) }
    }

    func enqueueStream(_ lines: [ScriptLine]) {
        lock.withLock { scripts.append(lines) }
    }

    func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let response = lock.withLock {
            recorded.append(request)
            return responses[request.url?.path ?? ""]
        }
        guard let response else { throw URLError(.unsupportedURL) }
        let http = try XCTUnwrap(
            HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: response.status,
                httpVersion: nil,
                headerFields: nil
            )
        )
        return (response.data, http)
    }

    func lines(for request: URLRequest) async throws -> AsyncThrowingStream<String, Error> {
        let script = lock.withLock {
            recorded.append(request)
            return scripts.isEmpty ? [] : scripts.removeFirst()
        }
        return AsyncThrowingStream { continuation in
            for item in script {
                switch item {
                case .line(let line):
                    continuation.yield(line)
                case .failure(let code):
                    continuation.finish(throwing: URLError(code))
                    return
                case .backendError(let error):
                    continuation.finish(throwing: error)
                    return
                }
            }
            continuation.finish()
        }
    }
}

final class HTTPBackendTests: XCTestCase {
    private let token = BackendToken("s3cret-token-value")
    private let port = 51_234

    private func backend(_ transport: FakeTransport) -> HTTPBackend {
        HTTPBackend(port: port, token: token, transport: transport, retryDelay: .zero)
    }

    func testHardwareRequestCarriesOnlyTheBearerHeader() async throws {
        let transport = FakeTransport()
        transport.setResponse(status: 200, data: try Fixtures.data("hardware.json"), for: "/hardware")

        let hardware = try await backend(transport).hardware()

        XCTAssertEqual(hardware.chip, "Apple M2 Max")
        let request = try XCTUnwrap(transport.requests.first)
        XCTAssertEqual(request.url?.absoluteString, "http://127.0.0.1:51234/hardware")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer s3cret-token-value")
        XCTAssertNil(request.value(forHTTPHeaderField: "Origin"))
        XCTAssertEqual(Set(try XCTUnwrap(request.allHTTPHeaderFields).keys), ["Authorization"])
    }

    func testEnginesAndRecommendationsDecode() async throws {
        let transport = FakeTransport()
        transport.setResponse(status: 200, data: try Fixtures.data("engines.json"), for: "/engines")
        transport.setResponse(
            status: 200,
            data: try Fixtures.data("recommendations.json"),
            for: "/recommendations"
        )

        let engines = try await backend(transport).engines()
        let recommendations = try await backend(transport).recommendations()

        XCTAssertEqual(engines.count, 5)
        XCTAssertEqual(recommendations.picks.count, 12)
    }

    func testQuickbenchPlanNamesTheRepoInTheQuery() async throws {
        let transport = FakeTransport()
        transport.setResponse(
            status: 200,
            data: try Fixtures.data("quickbench_plan.json"),
            for: "/quickbench/plan"
        )

        let plan = try await backend(transport).quickbenchPlan(repo: "mlx-community/Qwen3.5-2B-4bit")

        XCTAssertEqual(plan.estimateS, 630)
        let request = try XCTUnwrap(transport.requests.first)
        let components = try XCTUnwrap(URLComponents(url: try XCTUnwrap(request.url), resolvingAgainstBaseURL: false))
        XCTAssertEqual(components.queryItems, [
            URLQueryItem(name: "repo", value: "mlx-community/Qwen3.5-2B-4bit"),
        ])
    }

    func testStartJobSendsTheClosedArgsIncludingOsaurusFalse() async throws {
        let transport = FakeTransport()
        transport.setResponse(
            status: 202,
            data: Data("{\"job_id\": \"a1b2c3d4e5f60708\"}".utf8),
            for: "/jobs"
        )

        let jobID = try await backend(transport).startJob(
            kind: .quickbench,
            args: .quickbench(repo: "mlx-community/Qwen3-0.6B-4bit", osaurus: false)
        )

        XCTAssertEqual(jobID, "a1b2c3d4e5f60708")
        let request = try XCTUnwrap(transport.requests.first)
        XCTAssertEqual(request.httpMethod, "POST")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "application/json")
        let body = try XCTUnwrap(request.httpBody)
        let object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: body) as? [String: Any]
        )
        XCTAssertEqual(object["kind"] as? String, "quickbench")
        let args = try XCTUnwrap(object["args"] as? [String: Any])
        XCTAssertEqual(args["repo"] as? String, "mlx-community/Qwen3-0.6B-4bit")
        XCTAssertEqual(args["confirmed"] as? Bool, true)
        XCTAssertEqual(args["osaurus"] as? Bool, false)
    }

    func testCancelNowSendsTheNowBodyAndBetweenCellsSendsNone() async throws {
        let transport = FakeTransport()
        transport.setResponse(status: 202, data: Data("{}".utf8), for: "/jobs/a1b2c3d4e5f60708/cancel")

        try await backend(transport).cancel(jobID: "a1b2c3d4e5f60708", now: false)
        try await backend(transport).cancel(jobID: "a1b2c3d4e5f60708", now: true)

        let between = try XCTUnwrap(transport.requests.first)
        XCTAssertNil(between.httpBody)
        let now = try XCTUnwrap(transport.requests.last)
        let body = try XCTUnwrap(now.httpBody)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
        XCTAssertEqual(object["now"] as? Bool, true)
        XCTAssertEqual(object.keys.count, 1)
    }

    func testErrorEnvelopeBecomesBackendError() async throws {
        let transport = FakeTransport()
        transport.setResponse(status: 404, data: try Fixtures.data("not_found.json"), for: "/hardware")

        do {
            _ = try await backend(transport).hardware()
            XCTFail("expected a BackendError")
        } catch let error as BackendError {
            XCTAssertEqual(error.code, "not_found")
            XCTAssertEqual(error.status, 404)
            XCTAssertEqual(error.message, "no such path")
        }
    }

    func testEventsResumeAfterADroppedStream() async throws {
        let transport = FakeTransport()
        transport.enqueueStream([
            .line("id: 1"),
            .line("data: \(makeEventJSON(seq: 1))"),
            .line(""),
            .line("id: 2"),
            .line("data: \(makeEventJSON(seq: 2))"),
            .line(""),
            .failure(.networkConnectionLost),
        ])
        transport.enqueueStream([
            .line("id: 3"),
            .line("data: \(makeEventJSON(seq: 3))"),
            .line(""),
            .line("id: 4"),
            .line("data: \(makeEventJSON(seq: 4, type: "done", message: "finished"))"),
            .line(""),
        ])

        var received: [JobEvent] = []
        for try await event in backend(transport).events(jobID: "a1b2c3d4e5f60708", after: nil) {
            received.append(event)
        }

        XCTAssertEqual(received.map(\.seq), [1, 2, 3, 4])
        XCTAssertEqual(received.count, 4)
        XCTAssertEqual(received.last?.type, .done)
        XCTAssertEqual(transport.requests.count, 2)
        XCTAssertNil(transport.requests[0].value(forHTTPHeaderField: "Last-Event-ID"))
        XCTAssertEqual(transport.requests[1].value(forHTTPHeaderField: "Last-Event-ID"), "2")
    }

    func testAPoisonEventIsSkippedAndItsIDIsNeverFetchedAgain() async throws {
        let transport = FakeTransport()
        transport.enqueueStream([
            .line("id: 1"),
            .line("data: {\"seq\": 1, \"type\": \"progress\"}"),
            .line(""),
            .failure(.networkConnectionLost),
        ])
        transport.enqueueStream([
            .line("id: 2"),
            .line("data: \(makeEventJSON(seq: 2, type: "done", message: "finished"))"),
            .line(""),
        ])

        var received: [JobEvent] = []
        for try await event in backend(transport).events(jobID: "a1b2c3d4e5f60708", after: nil) {
            received.append(event)
        }

        XCTAssertEqual(received.map(\.seq), [2])
        XCTAssertEqual(received.last?.type, .done)
        XCTAssertEqual(transport.requests.count, 2, "the poison frame was fetched again")
        XCTAssertEqual(transport.requests[1].value(forHTTPHeaderField: "Last-Event-ID"), "1")
    }

    func testUnknownJobEndsTheStreamWithoutReconnecting() async throws {
        let transport = FakeTransport()
        transport.enqueueStream([
            .backendError(BackendError(code: "unknown_job", status: 404, message: "no such job")),
        ])

        var received: [JobEvent] = []
        for try await event in backend(transport).events(jobID: "a1b2c3d4e5f60708", after: nil) {
            received.append(event)
        }

        XCTAssertTrue(received.isEmpty)
        XCTAssertEqual(transport.requests.count, 1)
    }

    func testTokenIsRedactedInEveryDescription() throws {
        let token = BackendToken("s3cret-token-value")
        let secret = "s3cret-token-value"

        XCTAssertEqual(String(describing: token), "<redacted>")
        XCTAssertEqual(String(reflecting: token), "<redacted>")
        XCTAssertEqual("\(token)", "<redacted>")
        XCTAssertFalse(String(describing: token).contains(secret))

        var dumped = ""
        dump(token, to: &dumped)
        XCTAssertFalse(dumped.contains(secret), dumped)
        XCTAssertTrue(dumped.contains("<redacted>"), dumped)
    }
}
