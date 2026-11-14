import OhYesMLXKit
import SwiftUI

struct YourMacView: View {
    let model: AppModel

    var body: some View {
        Form {
            Section {
                Text(
                    "Welcome to OhYesMLX. It sets up local AI on this Mac and measures what "
                        + "runs fastest here. This is what it found. Nothing on your Mac has been changed."
                )
                .font(.title3)
                .fixedSize(horizontal: false, vertical: true)
            }

            if let hardware = model.hardware {
                Section("This Mac") {
                    LabeledContent("Chip") {
                        Text(hardware.chip)
                    }
                    LabeledContent("Processor") {
                        Text(processor(hardware)).monospacedDigit()
                    }
                    LabeledContent("Memory") {
                        Figure("\(Format.memory(hardware.ramBytes)) unified")
                    }
                    LabeledContent("Free disk") {
                        Figure(Format.size(hardware.diskFreeBytes))
                    }
                    LabeledContent("macOS") {
                        Figure(hardware.macos)
                    }
                }

                Section("Room for models") {
                    HStack(spacing: 8) {
                        Text("About \(Format.memory(hardware.modelBudgetBytes)) is available for model weights")
                            .monospacedDigit()
                        Badge("estimated")
                    }
                    Text(
                        "Worked out from \(Format.memory(hardware.ramBytes)) of unified memory. "
                            + "It is a planning figure, not a measurement; what fits in practice "
                            + "depends on what else is open."
                    )
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                }
            }

            Section {
                HStack {
                    Spacer()
                    Button("Continue to Engines") {
                        model.go(to: .engines)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                }
            }
        }
        .formStyle(.grouped)
        .frame(maxWidth: 680)
    }

    private func processor(_ hardware: Hardware) -> String {
        if let gpu = hardware.gpuCores {
            return "\(hardware.cpuCores) CPU cores, \(gpu) GPU cores"
        }
        return "\(hardware.cpuCores) CPU cores"
    }
}
