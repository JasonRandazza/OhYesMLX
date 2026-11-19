import OhYesMLXKit
import SwiftUI

/// Step 3: the picks for this Mac, their download actions, and the disk they need.
///
/// The row anatomy is comp 5's with DESIGN.md §4.4's fixes: Start here badge, title,
/// format, fit glyph and word with an `estimated` badge, the backend's own reason line, and
/// one trailing action. Every number is the backend's; nothing here computes one.
struct ModelsView: View {
    let model: AppModel

    @State private var evicting: Pick?

    var body: some View {
        Form {
            Section {
                Text(
                    "Picked for \(Format.memory(model.hardware?.ramBytes ?? 0)) of memory. "
                        + "Fit is estimated from each model's size. Speed is only known after "
                        + "the benchmark."
                )
                .font(.callout)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            }

            Section {
                ForEach(model.recommendations?.picks ?? []) { pick in
                    ModelRow(model: model, pick: pick, remove: { evicting = pick })
                }
            }

            if let excluded = model.recommendations?.excluded, !excluded.isEmpty {
                Section {
                    DisclosureGroup("Not recommended for this Mac") {
                        ForEach(excluded) { row in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(model.displayName(for: row.modelID))
                                Text(row.reason)
                                    .font(.callout)
                                    .foregroundStyle(.secondary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            .padding(.vertical, 2)
                        }
                    }
                }
            }

            Section {
                HStack {
                    Spacer()
                    Button("Continue to Benchmark") {
                        model.go(to: .benchmark)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .disabled(model.downloadedPicks.isEmpty)
                }
            }
        }
        .formStyle(.grouped)
        .frame(maxWidth: 680)
        .onAppear {
            openRequestedEvict()
            Task { await model.refreshRecommendations() }
        }
        .onChange(of: model.evictRequest) { openRequestedEvict() }
        .onChange(of: model.recommendations) { openRequestedEvict() }
        .sheet(item: $evicting) { pick in
            EvictSheet(pick: pick) {
                Task { await model.evict(repo: pick.modelID) }
            }
        }
        .toolbar {
            ToolbarItem(placement: .automatic) {
                DiskMeter(hardware: model.hardware, download: activeDownload)
            }
        }
    }

    /// Retry of an interrupted evict lands here: the same `evicting` state and sheet the row's
    /// Remove button opens, and the same gate that button takes, so nothing is evicted without
    /// the user's confirmation and a greyed Remove is never offered a sheet (S3-F15).
    private func openRequestedEvict() {
        if let pick = model.takeEvictRequest() { evicting = pick }
    }

    private var activeDownload: DiskMeter.Download? {
        guard let job = model.job, job.kind == .download, job.state.isActive else { return nil }
        guard let progress = model.downloadProgress(repo: job.name) else { return nil }
        return DiskMeter.Download(
            title: model.displayName(for: job.name),
            done: progress.done,
            total: progress.total
        )
    }
}

/// One pick's row: what it is, how well it fits, why, and its one trailing action (comp 5).
private struct ModelRow: View {
    let model: AppModel
    let pick: Pick
    let remove: () -> Void

    private var job: JobStatus? {
        guard let job = model.job, job.state.isActive, job.name == pick.modelID else { return nil }
        return job
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        if pick.startHere {
                            Badge("Start here")
                        }
                        Text(pick.title)
                            .fontWeight(.semibold)
                        Text(pick.format)
                            .foregroundStyle(.secondary)
                    }
                    .fixedSize(horizontal: false, vertical: true)
                    HStack(spacing: 6) {
                        HStack(spacing: 4) {
                            StatusGlyph(kind: pick.fit == "comfortable" ? .pass : .warning)
                            Text(pick.fit == "comfortable" ? "Comfortable" : "Tight")
                                .fixedSize()
                        }
                        Badge(pick.fitBasis)
                    }
                    Text(pick.reason)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                    if let measured = pick.measuredHere {
                        HStack(spacing: 6) {
                            Figure(Format.rate(measured.decodeTPS))
                                .foregroundStyle(.secondary)
                            Badge("quick: measured on this Mac")
                        }
                    }
                }
                .layoutPriority(1)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(accessibilityLabel)

                Spacer(minLength: 12)

                trailing
                    // Comp 5 fixes the end slot's width (`width:250px`); without it a long
                    // title squeezes the reason into a column a few characters wide.
                    .frame(width: 250, alignment: .trailing)
            }

            if let low = model.lowDisk[pick.modelID] {
                lowDiskLine(low)
            } else if let refusal = model.modelRefusals[pick.modelID] {
                Text(refusal.message)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.vertical, 2)
    }

    /// Q4: inline under the row, orange triangle, and the amount is the payload's own pair.
    private func lowDiskLine(_ low: LowDisk) -> some View {
        Label {
            Text("Not enough free disk: free \(Format.size(low.amountToFree)) more and try again")
        } icon: {
            Image(systemName: "exclamationmark.triangle")
                .foregroundStyle(.orange)
        }
        .font(.caption)
        .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder
    private var trailing: some View {
        if let job, job.kind == .download {
            VStack(alignment: .trailing, spacing: 4) {
                ProgressView(value: job.fraction)
                    .frame(width: 200)
                HStack(spacing: 4) {
                    Text(Format.percent(job.fraction))
                        .monospacedDigit()
                    if let progress = model.downloadProgress(repo: pick.modelID) {
                        Text("·")
                        Text("\(Format.size(progress.done)) of \(Format.size(progress.total))")
                            .monospacedDigit()
                    }
                }
                .font(.caption)
                .foregroundStyle(.secondary)
                Button("Pause") {
                    Task { await model.cancelJob(now: false) }
                }
                .controlSize(.small)
            }
        } else if let job {
            // The reason sits beside the control, as comp's Engines row does (DESIGN.md §4.6).
            // The trailing slot gets its width first so the reason never breaks mid-word.
            HStack(spacing: 8) {
                Text(model.oneSlotReason ?? "\(job.kind.wireName.capitalized) is running")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.trailing)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(width: 150, alignment: .trailing)
                ProgressView()
                    .controlSize(.small)
            }
            .layoutPriority(2)
        } else if pick.downloaded {
            HStack(spacing: 8) {
                if let reason = model.oneSlotReason {
                    Text(reason)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(width: 150, alignment: .trailing)
                }
                HStack(spacing: 4) {
                    Image(systemName: "checkmark")
                        .accessibilityHidden(true)
                    Text("Downloaded")
                }
                .font(.callout)
                .foregroundStyle(.secondary)
                Button("Remove…", action: remove)
                    .disabled(!model.canRemove(pick))
                    .accessibilityHint(Text(model.oneSlotReason ?? ""))
            }
            .layoutPriority(2)
        } else {
            HStack(spacing: 8) {
                if let reason = model.oneSlotReason {
                    Text(reason)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(width: 150, alignment: .trailing)
                }
                if let line = pick.mismatchLine {
                    Text(line)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.trailing)
                        .fixedSize(horizontal: false, vertical: true)
                } else {
                    Button(pick.downloadTitle) {
                        Task { await model.download(repo: pick.modelID) }
                    }
                    .disabled(!model.canStartJob)
                    .accessibilityHint(Text(model.oneSlotReason ?? ""))
                }
            }
            .layoutPriority(2)
        }
    }

    private var accessibilityLabel: String {
        var label = pick.title
        if pick.startHere {
            label += ", Start here"
        }
        label += ", \(pick.format), \(pick.fit == "comfortable" ? "comfortable" : "tight") fit"
        label += ", \(pick.reason)"
        if let measured = pick.measuredHere {
            label += ", \(Format.rate(measured.decodeTPS)) measured on this Mac"
        }
        if pick.downloaded {
            label += ", downloaded"
        }
        if let line = pick.mismatchLine {
            label += ", \(line)"
        }
        return label
    }
}

/// The toolbar's disk meter: used out of total, and what a download still needs, in decimal GB.
///
/// `Hardware.disk_total_bytes` is the capacity of the volume `disk_free_bytes` measures, so
/// used is `total - free` and the bar's first segment is that share of the disk (comp 5). A
/// download in progress sets its remaining bytes apart as a second segment inside the same bar,
/// since those bytes are spoken for but not yet used. A backend that sends no total has no
/// capacity to draw against, so the bar is hidden and the free figure stands alone (AC-2).
private struct DiskMeter: View {
    struct Download {
        let title: String
        let done: Int64
        let total: Int64
    }

    let hardware: Hardware?
    let download: Download?

    var body: some View {
        if let hardware {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(hardware.freeDiskLabel)
                        .foregroundStyle(.secondary)
                    Figure(Format.size(hardware.diskFreeBytes))
                }
                .font(.caption)
                if let used = hardware.usedBytes, let total = hardware.diskTotalBytes, total > 0 {
                    Bar(used: Double(used), needed: download?.remaining ?? 0, total: total)
                        .frame(width: 180, height: 6)
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(Text(accessibilityLabel(total: total)))
                }
                if let download {
                    Text(
                        "\(Format.size(download.remaining)) needed for \(download.title)"
                    )
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    private func accessibilityLabel(total: Int64) -> String {
        let disk = hardware?.diskVolumeName.map { "Disk on \($0)" } ?? "Disk"
        var label = "\(disk): \(Format.size(hardware?.diskFreeBytes ?? 0)) free of \(Format.size(total))"
        if let download {
            label += ", \(Format.size(download.remaining)) needed for \(download.title)"
        }
        return label
    }
}

private extension DiskMeter.Download {
    var remaining: Int64 { max(0, total - done) }
}

/// A capacity bar with two segments, left to right: used, then the bytes a running download
/// still needs. A `Gauge` carries one value, and a charting framework is not a dependency.
private struct Bar: View {
    let used: Double
    let needed: Int64
    let total: Int64

    var body: some View {
        GeometryReader { geometry in
            let usedShare = fraction(used)
            let neededShare = min(fraction(Double(max(0, needed))), 1 - usedShare)
            ZStack(alignment: .leading) {
                Capsule().fill(.quaternary)
                HStack(spacing: 1) {
                    Capsule().fill(.secondary).frame(width: geometry.size.width * usedShare)
                    if neededShare > 0 {
                        Capsule().fill(.tertiary).frame(width: geometry.size.width * neededShare)
                    }
                    Spacer(minLength: 0)
                }
            }
        }
    }

    /// *bytes* as a share of the disk, and the two segments never claim more than the bar.
    private func fraction(_ bytes: Double) -> Double {
        guard total > 0 else { return 0 }
        return min(1, max(0, bytes / Double(total)))
    }
}

/// Remove's confirmation: it names the size the removal frees, and says the row stays.
struct EvictSheet: View {
    let pick: Pick
    let remove: () -> Void

    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Remove \(pick.title)?")
                .font(.headline)
            Text(
                "This removes \(Format.size(pick.sizeBytes)) of model files from this Mac. "
                    + "The model stays in the list, so you can download it again at any time."
            )
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)

            HStack {
                Spacer()
                Button("Cancel") {
                    dismiss()
                }
                .keyboardShortcut(.cancelAction)
                Button("Remove") {
                    remove()
                    dismiss()
                }
                .keyboardShortcut(.defaultAction)
            }
        }
        .padding(20)
        .frame(width: 460)
    }
}
