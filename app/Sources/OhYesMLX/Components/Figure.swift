import SwiftUI

/// A number and its unit from `Format`, with tabular digits and never split across lines.
struct Figure: View {
    let text: String

    init(_ text: String) {
        self.text = text
    }

    var body: some View {
        Text(text)
            .monospacedDigit()
            .fixedSize()
    }
}
