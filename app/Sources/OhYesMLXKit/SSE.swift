import Foundation

public struct SSEParser: Sendable {
    public private(set) var lastEventID: String?
    private var eventID: String?
    private var dataLines: [String] = []

    public init() {}

    public mutating func consume(line: String) -> String? {
        if line.isEmpty {
            let data = dataLines
            let dispatchedID = eventID
            eventID = nil
            dataLines = []
            guard !data.isEmpty else { return nil }
            if let dispatchedID {
                lastEventID = dispatchedID
            }
            return data.joined(separator: "\n")
        }
        if line.hasPrefix(":") {
            return nil
        }
        let field: String
        let value: String
        if let colon = line.firstIndex(of: ":") {
            field = String(line[line.startIndex..<colon])
            var rest = String(line[line.index(after: colon)...])
            if rest.hasPrefix(" ") {
                rest.removeFirst()
            }
            value = rest
        } else {
            field = line
            value = ""
        }
        switch field {
        case "id":
            eventID = value
        case "data":
            dataLines.append(value)
        default:
            break
        }
        return nil
    }

    public mutating func dispatch() -> String? {
        consume(line: "")
    }

    public static func events(from text: String) throws -> (events: [JobEvent], lastEventID: String?) {
        var parser = SSEParser()
        var events: [JobEvent] = []
        let normalized = text.replacingOccurrences(of: "\r\n", with: "\n")
        let decoder = JSONDecoder()
        for line in normalized.split(separator: "\n", omittingEmptySubsequences: false) {
            if let payload = parser.consume(line: String(line)) {
                events.append(try decoder.decode(JobEvent.self, from: Data(payload.utf8)))
            }
        }
        return (events, parser.lastEventID)
    }
}
