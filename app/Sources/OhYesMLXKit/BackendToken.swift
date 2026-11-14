import Foundation

public struct BackendToken: Sendable, Equatable, CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    private let text: String

    public init(_ text: String) {
        self.text = text
    }

    public var description: String { "<redacted>" }

    public var debugDescription: String { "<redacted>" }

    public var customMirror: Mirror {
        Mirror(self, children: ["text": "<redacted>"], displayStyle: .struct)
    }

    var raw: String { text }
}
