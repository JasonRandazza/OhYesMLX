import SwiftUI

enum StatusKind {
    case pass
    case warning
    case fail
    case neutral
    /// DESIGN.md §4.3's "Stopped by you": a `stop.circle` in secondary, never a number.
    case stopped

    var symbol: String {
        switch self {
        case .pass, .warning: return "circle.fill"
        case .fail: return "xmark.circle.fill"
        case .neutral: return "minus.circle"
        case .stopped: return "stop.circle"
        }
    }

    var color: Color {
        switch self {
        case .pass: return .green
        case .warning: return .orange
        case .fail: return .red
        case .neutral, .stopped: return .secondary
        }
    }
}

/// The one mapping from a cell's status string to its glyph and word (DESIGN.md §4.3).
///
/// `ABORTED` reads "Stopped by you" and never carries a number; a status the design has no
/// word for is shown as the backend wrote it.
func cellStatus(_ status: String) -> (kind: StatusKind, word: String) {
    switch status {
    case "PASS": return (.pass, "PASS")
    case "FAIL": return (.fail, "FAIL")
    case "SKIPPED": return (.neutral, "SKIPPED")
    case "ABORTED": return (.stopped, "Stopped by you")
    default: return (.neutral, status)
    }
}

/// Status is always a glyph plus a word; the glyph carries colour, the word carries meaning.
struct StatusGlyph: View {
    let kind: StatusKind

    var body: some View {
        Image(systemName: kind.symbol)
            .font(.system(size: 8))
            .foregroundStyle(kind.color)
            .accessibilityHidden(true)
    }
}
