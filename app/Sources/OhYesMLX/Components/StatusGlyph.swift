import SwiftUI

enum StatusKind {
    case pass
    case warning
    case fail
    case neutral

    var symbol: String {
        switch self {
        case .pass, .warning: return "circle.fill"
        case .fail: return "xmark.circle.fill"
        case .neutral: return "minus.circle"
        }
    }

    var color: Color {
        switch self {
        case .pass: return .green
        case .warning: return .orange
        case .fail: return .red
        case .neutral: return .secondary
        }
    }
}

/// Status is always a glyph plus a word; the glyph carries colour, the word carries meaning.
struct StatusGlyph: View {
    let kind: StatusKind

    var body: some View {
        Image(systemName: kind.symbol)
            .font(.system(size: 9))
            .foregroundStyle(kind.color)
            .accessibilityHidden(true)
    }
}
