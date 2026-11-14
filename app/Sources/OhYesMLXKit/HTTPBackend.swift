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
                    for try await line in bytes.lines {
                        continuation.yield(line)
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
                var finished = false
                while !finished {
                    do {
                        let request = try makeRequest(
                            path: "/jobs/\(jobID)/events",
                            lastEventID: last > 0 ? last : nil
                        )
                        var parser = SSEParser()
                        let lines = try await transport.lines(for: request)
                        for try await line in lines {
                            guard let payload = parser.consume(line: line) else { continue }
                            let event = try JSONDecoder().decode(JobEvent.self, from: Data(payload.utf8))
                            last = max(last, event.seq)
                            continuation.yield(event)
                            if event.type == .done {
                                finished = true
                                break
                            }
                        }
                        if !finished {
                            try await Task.sleep(for: retryDelay)
                        }
                    } catch let error as BackendError where error.code == "unknown_job" {
                        finished = true
                    } catch is CancellationError {
                        finished = true
                    } catch {
                        if Task.isCancelled {
                            finished = true
                        } else {
                            try? await Task.sleep(for: retryDelay)
                        }
                    }
                }
                continuation.finish()
            }
            continuation.onTermination = { _ in task.cancel() }
        }
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
