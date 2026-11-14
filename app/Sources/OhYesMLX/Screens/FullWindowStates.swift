import AppKit
import SwiftUI

struct LaunchingStateView: View {
    var body: some View {
        VStack(spacing: 12) {
            ProgressView()
                .controlSize(.large)
            Text("Starting OhYesMLX's engine checker…")
                .font(.title3)
            Text("This usually takes a few seconds.")
                .font(.callout)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct CouldntStartStateView: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        CenteredState(
            symbol: "exclamationmark.triangle",
            title: "OhYesMLX couldn't start its engine checker",
            bodyText: "The checker is a small helper that runs alongside this app. It stopped "
                + "before it was ready. These are the last lines it printed:"
        ) {
            StderrBox(text: message)
            HStack {
                CopyDetailsButton(text: message)
                Spacer()
                Button("Try Again", action: retry)
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .keyboardShortcut(.defaultAction)
            }
            .frame(maxWidth: 640)
        }
    }
}

struct UnsupportedStateView: View {
    let reason: String?

    var body: some View {
        CenteredState(
            symbol: "cpu",
            title: "This Mac is not supported",
            bodyText: reason ?? "The engine checker did not describe this Mac's hardware."
        ) {
            Text("No setting, download or update changes this, so OhYesMLX can't continue on this Mac.")
                .font(.callout)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 520)
            Button("Quit OhYesMLX") {
                NSApplication.shared.terminate(nil)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .keyboardShortcut(.defaultAction)
        }
    }
}

struct BackendStoppedStateView: View {
    let status: Int32
    let stderrTail: [String]
    let relaunch: () -> Void

    private var details: String {
        stderrTail.joined(separator: "\n")
    }

    var body: some View {
        CenteredState(
            symbol: "exclamationmark.octagon",
            title: "The backend stopped",
            bodyText: "The helper that runs engines quit unexpectedly. "
                + "Nothing on your Mac was changed."
        ) {
            Text("Exit status \(status).")
                .font(.callout)
                .foregroundStyle(.secondary)
            if !stderrTail.isEmpty {
                StderrBox(text: details)
            }
            HStack {
                if !stderrTail.isEmpty {
                    CopyDetailsButton(text: details)
                }
                Spacer()
                Button("Relaunch", action: relaunch)
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .keyboardShortcut(.defaultAction)
            }
            .frame(maxWidth: 640)
        }
    }
}

private struct CenteredState<Content: View>: View {
    let symbol: String
    let title: String
    let bodyText: String
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: symbol)
                .font(.system(size: 40))
                .foregroundStyle(.secondary)
                .accessibilityHidden(true)
            Text(title)
                .font(.title2)
                .multilineTextAlignment(.center)
            Text(bodyText)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 520)
            content()
        }
        .padding(40)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct StderrBox: View {
    let text: String

    var body: some View {
        ScrollView(.vertical) {
            Text(text)
                .font(.caption)
                .monospaced()
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(maxWidth: 640, maxHeight: 160)
        .padding(8)
        .background(.quaternary.opacity(0.6), in: RoundedRectangle(cornerRadius: 6))
    }
}

struct CopyDetailsButton: View {
    let text: String

    var body: some View {
        Button("Copy Details") {
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(text, forType: .string)
        }
    }
}
