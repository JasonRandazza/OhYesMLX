import OhYesMLXKit
import SwiftUI

/// Step 4: the plan before anything runs (D4), then the run itself with both stop controls (Q3).
///
/// Nothing here computes a number: the plan, its estimate, the progress and every cell row are
/// the backend's. The screen's only decisions are which pick is chosen and when Start is pressed.
struct BenchmarkView: View {
    let model: AppModel

    @State private var selectedRepo: String?

    private var selection: String? {
        selectedRepo ?? model.requestedBenchmarkRepo ?? model.defaultBenchmarkPick?.modelID
    }

    private var running: Bool { model.job?.state.isActive == true && model.job?.kind == .quickbench }

    var body: some View {
        Group {
            if model.downloadedPicks.isEmpty {
                emptyState
            } else {
                Form {
                    Section {
                        Picker("Model", selection: Binding(
                            get: { selection },
                            set: { value in
                                selectedRepo = value
                                if let value {
                                    Task { await model.planBenchmark(repo: value) }
                                }
                            }
                        )) {
                            ForEach(model.downloadedPicks) { pick in
                                Text(pick.title).tag(Optional(pick.modelID))
                            }
                        }
                    }

                    if let refusal = model.benchmarkRefusal {
                        refusalSection(refusal)
                    } else if let plan = model.quickPlan {
                        if running {
                            runningSections(plan)
                        } else {
                            planSections(plan)
                        }
                    } else {
                        Section {
                            HStack {
                                Spacer()
                                ProgressView()
                                    .controlSize(.small)
                                Text("Working out the plan…")
                                    .foregroundStyle(.secondary)
                                Spacer()
                            }
                        }
                    }
                }
                .formStyle(.grouped)
                .frame(maxWidth: 680)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .onAppear {
            if model.quickPlan == nil, let repo = selection {
                Task { await model.planBenchmark(repo: repo) }
            }
        }
        .toolbar {
            if running {
                ToolbarItemGroup(placement: .primaryAction) {
                    Button {
                        Task { await model.cancelJob(now: false) }
                    } label: {
                        Label("Stop After This Cell", systemImage: "pause.circle")
                            .labelStyle(.titleAndIcon)
                    }
                    .help("Stop After This Cell")
                    .disabled(stopping)

                    Button {
                        Task { await model.cancelJob(now: true) }
                    } label: {
                        Label("Stop Now", systemImage: "stop.circle")
                            .labelStyle(.titleAndIcon)
                    }
                    .help("Stop Now")
                    .disabled(model.job?.state == .stoppingNow)
                }
            }
        }
    }

    private var stopping: Bool {
        guard let state = model.job?.state else { return false }
        return state == .stoppingAfterCell || state == .stoppingNow
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            Text("Download a model first")
                .font(.title3)
            Text("The benchmark measures a model you already have, so it can time it here.")
                .foregroundStyle(.secondary)
            Button("Go to Models") {
                model.go(to: .models)
            }
            .buttonStyle(.borderedProminent)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(40)
    }

    private func refusalSection(_ refusal: BackendError) -> some View {
        Section {
            Label {
                Text(refusal.message)
                    .fixedSize(horizontal: false, vertical: true)
            } icon: {
                Image(systemName: "exclamationmark.triangle")
                    .foregroundStyle(.orange)
            }
            Button("Choose Another Model") {
                model.go(to: .models)
            }
        }
    }

    // MARK: - the plan, shown before anything runs

    @ViewBuilder
    private func planSections(_ plan: QuickPlan) -> some View {
        Section {
            Text(
                "This is the plan. Nothing runs until you press Start. Every cell uses "
                    + "\(model.displayName(for: plan.repo)) so only one thing changes at a time."
            )
            .font(.callout)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
        }

        Section("Stage A: engines") {
            Text("format fixed at \(plan.format)")
                .font(.caption)
                .foregroundStyle(.secondary)
            ForEach(plan.stageA, id: \.engine) { engine in
                HStack {
                    Text(model.engineTitle(engine.engine))
                    if !engine.tested {
                        Badge("untested build")
                    }
                    Spacer()
                    if let version = engine.version {
                        Figure(version).foregroundStyle(.secondary)
                    }
                }
            }
            if plan.stageA.isEmpty {
                Text("No installed engine lists this model; the run will say so.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
        }

        Section("Stage B: formats") {
            Text("on the Stage A winner")
                .font(.caption)
                .foregroundStyle(.secondary)
            ForEach(plan.stageB, id: \.repo) { sibling in
                HStack {
                    Text(sibling.format)
                    Spacer()
                    if sibling.downloaded {
                        Text("already on disk")
                            .foregroundStyle(.secondary)
                    } else {
                        Text("one extra download, \(Format.size(sibling.sizeBytes))")
                            .foregroundStyle(.secondary)
                    }
                }
            }
            if plan.stageB.isEmpty {
                Text("This model has no other formats in the catalog.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
        }

        Section("Before you start") {
            LabeledContent("Time") {
                HStack(spacing: 6) {
                    Figure(Format.duration(Double(plan.estimateS)))
                    Badge("estimated")
                }
            }
            LabeledContent("Downloads") {
                Figure(Format.size(plan.downloadBytes))
            }
            LabeledContent("Free disk after") {
                HStack(spacing: 6) {
                    Figure(diskAfter(plan))
                    Badge("estimated")
                }
            }
        }

        Section("Osaurus") {
            Toggle(
                "Pin Osaurus settings for the run",
                isOn: Binding(
                    get: { model.osaurusConsent },
                    set: { model.osaurusConsent = $0 }
                )
            )
            .disabled(!plan.osaurus)
            Text(
                "Holds Osaurus's settings still so its numbers compare fairly. The app asks "
                    + "the backend to put your settings back when the run ends or is stopped; "
                    + "Results says whether that worked."
            )
            .font(.callout)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
            if !plan.osaurus {
                Text("Osaurus is not installed, so this run has nothing to pin.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
        }

        Section {
            HStack {
                if let reason = model.oneSlotReason {
                    Text(reason)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else {
                    Text("For steadier numbers, quit other heavy apps first.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button("Start Benchmark") {
                    Task { await model.startBenchmark() }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(!model.canStartJob)
                .accessibilityHint(Text(model.oneSlotReason ?? ""))
            }
        }
    }

    private func diskAfter(_ plan: QuickPlan) -> String {
        let free = model.hardware?.diskFreeBytes ?? 0
        return Format.size(max(0, free - plan.downloadBytes))
    }

    // MARK: - the run

    @ViewBuilder
    private func runningSections(_ plan: QuickPlan) -> some View {
        Section {
            HStack(alignment: .firstTextBaseline) {
                Text(stageLine(plan))
                Spacer()
                if let state = model.job?.state, state == .stoppingAfterCell || state == .stoppingNow {
                    Text(state.text)
                        .foregroundStyle(.secondary)
                }
            }
            ProgressView(value: model.job?.fraction ?? 0)
            Text(
                "Stop After This Cell lets the cell in flight finish and keeps its result. "
                    + "Stop Now ends at once and this cell is not counted. Results says whether "
                    + "your Osaurus settings were put back."
            )
            .font(.caption)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
        }

        if let next = model.nextBenchmarkCell {
            Section("Now running") {
                HStack(spacing: 8) {
                    ProgressView()
                        .controlSize(.small)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(next.title)
                            .fontWeight(.medium)
                        Text(next.detail)
                            .font(.callout)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }

        Section("Cells") {
            if model.liveCells.isEmpty {
                Text("Waiting for the first cell.")
                    .foregroundStyle(.secondary)
            }
            ForEach(model.liveCells) { cell in
                BenchmarkCellRow(cell: cell, title: cell.stage == "B" ? cell.format : model.engineTitle(cell.engine))
            }
        }
    }

    /// "Stage A: engines, cell 3 of 5" — the count is the plan's, the position is landed cells.
    private func stageLine(_ plan: QuickPlan) -> String {
        let landed = model.liveCells
        let stage = landed.last?.stage ?? "A"
        let planned = stage == "A"
            ? plan.stageA.map(\.engine)
            : plan.stageB.map(\.format)
        let reached = landed.filter { $0.stage == stage }.count
        let name = stage == "A" ? "engines" : "formats"
        return "Stage \(stage): \(name), cell \(min(reached + 1, planned.count)) "
            + "of \(planned.count)"
    }
}

/// One cell row: the stage letter and index come from the live payload's own stage field, the
/// status is a glyph plus a word, and a measured cell shows its figures (DESIGN.md §4.3).
struct BenchmarkCellRow: View {
    let cell: BenchmarkCell
    let title: String

    var body: some View {
        let status = cellStatus(cell.status)
        HStack(spacing: 8) {
            Text("\(cell.stage) · \(title)")
                .frame(maxWidth: .infinity, alignment: .leading)
            HStack(spacing: 4) {
                StatusGlyph(kind: status.kind)
                SwiftUI.Text(status.word)
            }
            .foregroundStyle(.secondary)
            if let decode = cell.decodeTPS {
                Figure(Format.rate(decode))
                    .foregroundStyle(.secondary)
            }
        }
    }
}
