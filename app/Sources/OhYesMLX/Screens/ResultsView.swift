import AppKit
import OhYesMLXKit
import SwiftUI
import UniformTypeIdentifiers

/// Step 5: the typed summary as a record of what ran, what it cost, and what it left behind.
///
/// A cancelled run is shown as one: no best card, an ABORTED cell as "Stopped by you" with no
/// number, and the not_evicted line for anything this run could not put back (Q7). Every
/// figure is the summary's; nothing is recomputed here.
struct ResultsView: View {
    let model: AppModel

    @State private var exportError: String?

    var body: some View {
        Form {
            if let summary = model.summary {
                bestSection(summary)
                stageSection(
                    title: "Stage A · engines",
                    caveat: summary.stageA.caveat,
                    note: summary.stageA.note,
                    cells: summary.stageA.cells,
                    winner: summary.stageA.winner,
                    byFormat: false
                )
                stageSection(
                    title: summary.stageB.engine.map { "Stage B · formats on \(model.engineTitle($0))" }
                        ?? "Stage B · formats",
                    caveat: summary.stageB.caveat,
                    note: summary.stageB.note,
                    cells: summary.stageB.cells,
                    winner: nil,
                    byFormat: true
                )
                if !model.notEvictedLines.isEmpty {
                    Section {
                        ForEach(model.notEvictedLines, id: \.self) { line in
                            Text(line)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            } else if model.liveCells.isEmpty {
                noRunSection
            } else {
                Section {
                    Text("This run has not finished yet; its cells appear here as they land.")
                        .foregroundStyle(.secondary)
                }
                Section("Cells") {
                    ForEach(model.liveCells) { cell in
                        BenchmarkCellRow(cell: cell, title: cell.stage == "B" ? cell.format : model.engineTitle(cell.engine))
                    }
                }
            }
        }
        .formStyle(.grouped)
        .frame(maxWidth: 680)
        .frame(maxWidth: .infinity, alignment: .leading)
        .alert("Export failed", isPresented: exported()) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(exportError ?? "")
        }
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button("Export Results…") {
                    export()
                }
                .disabled(model.summaryData == nil)
            }
        }
    }

    private func exported() -> Binding<Bool> {
        Binding(
            get: { exportError != nil },
            set: { if !$0 { exportError = nil } }
        )
    }

    // MARK: - the header card

    @ViewBuilder
    private func bestSection(_ summary: QuickSummary) -> some View {
        Section {
            if let best = summary.best {
                HStack(alignment: .firstTextBaseline) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Best on your Mac")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text("\(model.engineTitle(best.engine)) with \(summary.bestFormat)")
                            .font(.title3)
                            .fontWeight(.semibold)
                        Badge("quick: measured on this Mac")
                    }
                    Spacer()
                    VStack(alignment: .trailing, spacing: 2) {
                        Figure(Format.rate(best.decodeTPS))
                            .font(.title2)
                        Text("decode speed, \(model.displayName(for: summary.repo))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            } else {
                Text(
                    summary.ended == .cancelled
                        ? "This run was stopped; nothing is recommended from it."
                        : "This run ended without a result; nothing is recommended from it."
                )
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    // MARK: - a stage's table

    @ViewBuilder
    private func stageSection(
        title: String,
        caveat: String,
        note: String?,
        cells: [QuickCell],
        winner: String?,
        byFormat: Bool
    ) -> some View {
        Section {
            if cells.isEmpty {
                Text("No cell in this stage.")
                    .foregroundStyle(.secondary)
            }
            ForEach(cells) { cell in
                ResultCellRow(
                    cell: cell,
                    // Stage B holds the engine fixed and varies the format, so its rows are named by
                    // format (the engine is in the section title); stage A's by engine and version.
                    title: byFormat ? cell.format : model.engineTitle(cell.engine),
                    isWinner: cell.engine == winner && cell.status == "PASS",
                    showsVersion: !byFormat
                )
            }
            if let note {
                Text(note)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Text(caveat)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        } header: {
            Text(title)
        }
    }

    // MARK: - nothing has run

    @ViewBuilder
    private var noRunSection: some View {
        Section {
            Text("No benchmark has run since OhYesMLX opened.")
                .foregroundStyle(.secondary)
        }
        let measured = (model.recommendations?.picks ?? []).filter { $0.measuredHere != nil }
        if !measured.isEmpty {
            Section("Measured on this Mac") {
                ForEach(measured) { pick in
                    HStack {
                        Text(pick.title)
                        Spacer()
                        if let quick = pick.measuredHere {
                            Figure(Format.rate(quick.decodeTPS))
                                .foregroundStyle(.secondary)
                            Badge("quick: measured on this Mac")
                        }
                    }
                }
            }
        }
    }

    // MARK: - Export (D8)

    /// A panel the user chooses the file in, and the summary's payload written to it.
    ///
    /// The bytes are the received payload (`AppModel.summaryData`) re-serialised, not an
    /// encode of the typed value, so every field the backend sent survives into the file,
    /// including keys this client does not model (AC-2).
    private func export() {
        guard let data = model.summaryData else { return }
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.json]
        panel.nameFieldStringValue = "OhYesMLX-quickbench-\(stamp()).json"
        panel.canCreateDirectories = true
        panel.title = "Export Results"
        panel.message = "Every field the backend sent, re-serialised as JSON."
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            try data.write(to: url, options: .atomic)
        } catch {
            exportError = error.localizedDescription
        }
    }

    private func stamp() -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyyMMdd-HHmmss"
        return formatter.string(from: Date())
    }
}

/// One result row: engine and version, status glyph plus word, both figures, and the note.
///
/// The status is never a pill and never colour alone: `DESIGN.md` §4.3 names the glyph and the
/// word for each status, and a stopped cell reads "Stopped by you" with no number.
struct ResultCellRow: View {
    let cell: QuickCell
    let title: String
    let isWinner: Bool
    var showsVersion = true

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                HStack(spacing: 6) {
                    Text(title)
                        .fontWeight(isWinner ? .semibold : .regular)
                    if showsVersion, let version = cell.runtimeVersion {
                        Text(version)
                            .foregroundStyle(.secondary)
                            .monospacedDigit()
                    }
                    if isWinner {
                        Badge("fastest in stage")
                    }
                }
                Spacer(minLength: 12)
                status
                figure(cell.decodeTPS.map(Format.rate))
                figure(cell.ttftS.map(Format.duration))
            }
            if let reason = cell.reason, !reason.isEmpty {
                Text(reason)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .combine)
    }

    private var status: some View {
        let display = cellStatus(cell.status)
        return HStack(spacing: 4) {
            StatusGlyph(kind: display.kind)
            Text(display.word)
        }
        .font(.callout)
        .foregroundStyle(statusIsSecondary ? AnyShapeStyle(.secondary) : AnyShapeStyle(.primary))
        .frame(width: 130, alignment: .leading)
    }

    private func figure(_ text: String?) -> some View {
        Group {
            if let text {
                Figure(text)
            } else {
                Text("–")
                    .foregroundStyle(.secondary)
            }
        }
        .frame(width: 84, alignment: .trailing)
    }

    private var statusIsSecondary: Bool {
        let kind = cellStatus(cell.status).kind
        return kind != .pass && kind != .fail
    }
}
