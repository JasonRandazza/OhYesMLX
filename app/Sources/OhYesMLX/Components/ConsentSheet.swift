import OhYesMLXKit
import SwiftUI

/// The install consent sheet. It lists exactly what will run (DESIGN.md §4.1):
/// the plan's steps, the estimated size and whether an admin password is needed.
/// It never claims an undo the backend does not have.
struct ConsentSheet: View {
    let title: String
    let plan: InstallPlan
    let install: () -> Void

    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Install \(title)?")
                .font(.headline)
            Text(
                plan.kind == "guided_download"
                    ? "Opens the official download page, then checks again."
                    : "OhYesMLX will run exactly these steps. Nothing else on your Mac changes."
            )
            .foregroundStyle(.secondary)

            VStack(alignment: .leading, spacing: 10) {
                ForEach(Array(plan.steps.enumerated()), id: \.offset) { index, step in
                    VStack(alignment: .leading, spacing: 4) {
                        Text("\(index + 1). \(step.label)")
                        if let command = step.command {
                            Text(command.joined(separator: " "))
                                .font(.caption)
                                .monospaced()
                                .textSelection(.enabled)
                                .padding(6)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(
                                    .quaternary.opacity(0.6),
                                    in: RoundedRectangle(cornerRadius: 4)
                                )
                        }
                    }
                }
            }

            Divider()

            Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 6) {
                GridRow {
                    Text(
                        plan.kind == "guided_download"
                            ? "Download (estimated)"
                            : "Download"
                    )
                    .foregroundStyle(.secondary)
                    Text(plan.sizeBytesEstimate.map(Format.size) ?? "Unknown")
                        .monospacedDigit()
                }
                GridRow {
                    Text("Needs admin password")
                        .foregroundStyle(.secondary)
                    Text(plan.needsAdmin ? "Yes" : "No")
                }
            }
            .font(.callout)

            HStack {
                Spacer()
                Button("Cancel") {
                    dismiss()
                }
                .keyboardShortcut(.cancelAction)
                Button(plan.kind == "guided_download" ? "Open Download Page" : "Install") {
                    install()
                    dismiss()
                }
                .keyboardShortcut(.defaultAction)
            }
        }
        .padding(20)
        .frame(width: 520)
    }
}
