import Foundation

public protocol HTTPTransport: Sendable {
    func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse)
    func lines(for request: URLRequest) async throws -> AsyncThrowingStream<String, Error>
}

public struct URLSessionTransport: HTTPTransport {
    private let session: URLSession

    public init(session: URLSession = .shared) {
        self.session = session
    }

    public func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }
        return (data, http)
    }

    public func lines(for request: URLRequest) async throws -> AsyncThrowingStream<String, Error> {
        let (bytes, response) = try await session.bytes(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }
        if !(200..<300).contains(http.statusCode) {
            var body = Data()
            for try await byte in bytes {
                body.append(byte)
            }
            throw HTTPBackend.error(data: body, status: http.statusCode)
        }
        return AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    // Not `bytes.lines`: it drops empty lines, and an empty line is the SSE event
                    // boundary, so no event ever dispatched (Fable S3-F1). Split on LF ourselves,
                    // keep empty lines, strip a trailing CR, and decode each whole line as UTF-8
                    // so a multi-byte character split across network chunks stays intact.
                    var line: [UInt8] = []
                    for try await byte in bytes {
                        if byte == 0x0A {
                            if line.last == 0x0D { line.removeLast() }
                            continuation.yield(String(decoding: line, as: UTF8.self))
                            line.removeAll(keepingCapacity: true)
                        } else {
                            line.append(byte)
                        }
                    }
                    if !line.isEmpty {
                        if line.last == 0x0D { line.removeLast() }
                        continuation.yield(String(decoding: line, as: UTF8.self))
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }
}

public struct HTTPBackend: Backend {
    /// Consecutive failed attempts after which `events` stops reconnecting (Fable S3-F11). A
    /// dropped connection that delivered events resets the count; a backend that is gone does not.
    static let maxConsecutiveEventFailures = 5

    public let port: Int

    private let token: BackendToken
    private let transport: any HTTPTransport
    private let retryDelay: Duration

    public init(
        port: Int,
        token: BackendToken,
        transport: any HTTPTransport = URLSessionTransport(),
        retryDelay: Duration = .milliseconds(200)
    ) {
        self.port = port
        self.token = token
        self.transport = transport
        self.retryDelay = retryDelay
    }

    public func hardware() async throws -> Hardware {
        try await get("/hardware")
    }

    public func engines() async throws -> [EngineStatus] {
        try await get("/engines")
    }

    public func recommendations() async throws -> Recommendations {
        try await get("/recommendations")
    }

    public func quickbenchPlan(repo: String) async throws -> QuickPlan {
        var components = URLComponents()
        components.path = "/quickbench/plan"
        components.queryItems = [URLQueryItem(name: "repo", value: repo)]
        guard let query = components.string else { throw URLError(.badURL) }
        return try await get(query)
    }

    public func startJob(kind: JobKind, args: JobArgs) async throws -> String {
        let body = try JSONEncoder().encode(StartJobBody(kind: kind.wireName, args: args.body))
        let request = try makeRequest(path: "/jobs", method: "POST", body: body)
        let (data, response) = try await transport.data(for: request)
        try check(response, data: data)
        return try JSONDecoder().decode(JobIDResponse.self, from: data).jobID
    }

    public func cancel(jobID: String, now: Bool) async throws {
        let body: Data?
        if now {
            body = try JSONEncoder().encode(["now": true])
        } else {
            body = nil
        }
        let request = try makeRequest(path: "/jobs/\(jobID)/cancel", method: "POST", body: body)
        let (data, response) = try await transport.data(for: request)
        try check(response, data: data)
    }

    public func events(jobID: String, after: Int?) -> AsyncThrowingStream<JobEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                var last = after ?? 0
                var failures = 0
                while true {
                    var parser = SSEParser()
                    var received = false
                    var finished = false
                    // One frame: decode, advance `last`, yield. A frame this client cannot read
                    // is skipped, never re-fetched: `last` moves to the frame's own SSE id, so the
                    // reconnect asks for what follows it rather than the same event forever.
                    func handle(_ payload: String) {
                        guard let event = try? JSONDecoder().decode(
                            JobEvent.self, from: Data(payload.utf8)
                        ) else {
                            if let frameID = parser.lastEventID, let id = Int(frameID) {
                                last = max(last, id)
                            }
                            return
                        }
                        received = true
                        last = max(last, event.seq)
                        continuation.yield(event)
                        if event.type == .done { finished = true }
                    }
                    do {
                        let request = try makeRequest(
                            path: "/jobs/\(jobID)/events",
                            lastEventID: last > 0 ? last : nil
                        )
                        let lines = try await transport.lines(for: request)
                        for try await line in lines {
                            if let payload = parser.consume(line: line) { handle(payload) }
                            if finished { break }
                        }
                        // A stream that ended mid-event still delivers the event it holds.
                        if !finished, let payload = parser.dispatch() { handle(payload) }
                        if finished { break }
                        failures = received ? 0 : failures + 1
                    } catch let error as BackendError where error.code == "unknown_job" {
                        break
                    } catch is CancellationError {
                        break
                    } catch {
                        if Task.isCancelled { break }
                        failures += 1
                        if Self.isTerminal(error) || failures >= Self.maxConsecutiveEventFailures {
                            continuation.finish(throwing: error)
                            return
                        }
                    }
                    if Task.isCancelled { break }
                    if failures >= Self.maxConsecutiveEventFailures {
                        continuation.finish(throwing: URLError(.networkConnectionLost))
                        return
                    }
                    try? await Task.sleep(for: retryDelay)
                }
                continuation.finish()
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    /// An error no reconnect can fix: nothing is listening (the backend exited), or the backend
    /// refused the request itself (a 4xx other than 429). Everything else is retried, bounded.
    static func isTerminal(_ error: Error) -> Bool {
        if let error = error as? URLError {
            return [.cannotConnectToHost, .cannotFindHost].contains(error.code)
        }
        if let error = error as? BackendError, let status = error.status {
            return (400..<500).contains(status) && status != 429
        }
        return false
    }

    private func get<T: Decodable>(_ path: String) async throws -> T {
        let request = try makeRequest(path: path)
        let (data, response) = try await transport.data(for: request)
        try check(response, data: data)
        return try JSONDecoder().decode(T.self, from: data)
    }

    func makeRequest(
        path: String,
        method: String = "GET",
        body: Data? = nil,
        lastEventID: Int? = nil
    ) throws -> URLRequest {
        guard let url = URL(string: "http://127.0.0.1:\(port)\(path)") else {
            throw URLError(.badURL)
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("Bearer \(token.raw)", forHTTPHeaderField: "Authorization")
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = body
        }
        if let lastEventID {
            request.setValue(String(lastEventID), forHTTPHeaderField: "Last-Event-ID")
        }
        return request
    }

    private func check(_ response: HTTPURLResponse, data: Data) throws {
        guard (200..<300).contains(response.statusCode) else {
            throw Self.error(data: data, status: response.statusCode)
        }
    }

    static func error(data: Data, status: Int) -> BackendError {
        if let envelope = try? JSONDecoder().decode(BackendErrorEnvelope.self, from: data) {
            return envelope.error
        }
        return BackendError(
            code: "bad_response",
            status: status,
            message: "the backend answered \(status) with a body this client could not read"
        )
    }
}

private struct StartJobBody: Encodable {
    let kind: String
    let args: [String: JSONValue]
}

private struct JobIDResponse: Decodable {
    let jobID: String

    enum CodingKeys: String, CodingKey {
        case jobID = "job_id"
    }
}
