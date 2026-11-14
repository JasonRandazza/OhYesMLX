import OhYesMLXKit
import SwiftUI

/// Q2: one sentence, Retry and Dismiss. It never retries by itself.
struct InterruptedBanner: View {
    let job: InterruptedJob
    let retry: () -> Void
    let dismiss: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Image(systemName: "info.circle")
                    .foregroundStyle(.secondary)
                    .accessibilityHidden(true)
                Text(
                    "\(job.kind.wireName.capitalized) of \(job.name) was interrupted when OhYesMLX quit."
                )
                .frame(maxWidth: .infinity, alignment: .leading)
                Button("Retry", action: retry)
                Button("Dismiss", action: dismiss)
            }
            .font(.callout)
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .background(.yellow.opacity(0.12))
            Divider()
        }
    }
}
