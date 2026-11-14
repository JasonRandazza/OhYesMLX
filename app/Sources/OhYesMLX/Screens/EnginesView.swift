import OhYesMLXKit
import SwiftUI

struct EnginesView: View {
    let model: AppModel
    var initialConsentEngine: String? = nil

    @State private var consent: EngineStatus?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Engines are the programs that run models.")
                .font(.title3)
                .padding(.horizontal, 20)
                .padding(.top, 20)

            if let refusal = model.refusal {
                Label {
                    Text(refusal.message)
                } icon: {
                    Image(systemName: "exclamationmark.triangle")
                        .foregroundStyle(.orange)
                }
                .font(.callout)
                .padding(.horizontal, 20)
                .padding(.top, 8)
            }

            Form {
                Section {
                    ForEach(model.engines) { engine in
                        EngineRow(model: model, engine: engine) {
                            consent = engine
                        }
                    }
                }

                Section {
                    HStack {
                        Spacer()
                        Button("Continue to Models") {
                            model.go(to: .models)
                        }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.large)
                        .disabled(!model.enginesComplete)
                    }
                }
            }
            .formStyle(.grouped)
            .frame(maxWidth: 680)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .onAppear {
            Task {
                await model.enginesScreenAppeared()
                if let name = initialConsentEngine, consent == nil {
                    consent = model.engines.first { $0.name == name && $0.install != nil }
                }
            }
        }
        .sheet(item: $consent) { engine in
            if let plan = engine.install {
                ConsentSheet(title: engine.title, plan: plan) {
                    startInstall(engine)
                }
            }
        }
    }

    private func startInstall(_ engine: EngineStatus) {
        model.installConsent = true
        Task {
            await model.install(engine: engine.name)
            model.installConsent = false
        }
    }
}

private struct EngineRow: View {
    let model: AppModel
    let engine: EngineStatus
    let install: () -> Void

    private var activeJob: JobStatus? {
        guard let job = model.job, job.kind == .install, job.name == engine.name, job.state.isActive
        else { return nil }
        return job
    }

    private var failure: EngineFailure? {
        model.engineFailures[engine.name]
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(engine.title)
                            .fontWeight(.semibold)
                        if let version = engine.version {
                            Text(version)
                                .monospacedDigit()
                                .foregroundStyle(.secondary)
                        }
                    }
                    Text(engine.blurb)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(accessibilityLabel)

                Spacer(minLength: 12)

                trailing
            }

            if let failure {
                failureView(failure)
            }
        }
        .padding(.vertical, 2)
    }

    @ViewBuilder
    private var trailing: some View {
        if let job = activeJob {
            VStack(alignment: .trailing, spacing: 4) {
                if job.fraction > 0 {
                    ProgressView(value: job.fraction)
                        .frame(width: 120)
                } else {
                    ProgressView()
                        .frame(width: 120)
                }
                Text(job.message)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.trailing)
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Installing \(engine.title)")
        } else if engine.installed {
            HStack(spacing: 6) {
                StatusGlyph(kind: engine.tested ? .pass : .warning)
                Text(engine.tested ? "Installed, tested" : "Installed, untested")
                if !engine.tested {
                    Badge("untested build")
                }
            }
            .accessibilityHidden(true)
        } else if failure == nil {
            HStack(spacing: 8) {
                if let reason = model.oneSlotReason {
                    Text(reason)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Button("Install…", action: install)
                    .disabled(!model.canStartJob)
                    .accessibilityHint(Text(model.oneSlotReason ?? ""))
            }
        }
    }

    private func failureView(_ failure: EngineFailure) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(failure.code)
                .monospaced()
                .foregroundStyle(.secondary)
            if !failure.outputTail.isEmpty {
                Text(failure.outputTail)
                    .monospaced()
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Button("Try Again") {
                retry()
            }
            .disabled(!model.canStartJob)
            .accessibilityHint(Text(model.oneSlotReason ?? ""))
            .padding(.top, 2)
        }
        .font(.caption)
        .padding(.leading, 2)
    }

    private func retry() {
        model.installConsent = true
        Task {
            await model.install(engine: engine.name)
            model.installConsent = false
        }
    }

    private var accessibilityLabel: String {
        var label = engine.title
        if let version = engine.version {
            label += " \(version)"
        }
        if engine.installed {
            label += engine.tested ? ", installed, tested" : ", installed, untested"
        } else {
            label += ", not installed"
        }
        return label
    }
}
