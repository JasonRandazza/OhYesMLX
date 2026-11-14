import OhYesMLXKit
import SwiftUI

struct RootView: View {
    let model: AppModel
    var debugConsentEngine: String? = nil

    var body: some View {
        Group {
            if let status = model.backendStopped {
                BackendStoppedStateView(status: status, stderrTail: model.backendStderrTail) {
                    Task { await model.relaunch() }
                }
            } else {
                switch model.screen {
                case .launching:
                    LaunchingStateView()
                case .couldntStart:
                    CouldntStartStateView(
                        message: model.launchError ?? "The backend did not start."
                    ) {
                        Task { await model.relaunch() }
                    }
                case .unsupported:
                    UnsupportedStateView(reason: model.hardware?.unsupportedReason)
                default:
                    shell
                }
            }
        }
        .frame(minWidth: 900, minHeight: 600)
    }

    private var shell: some View {
        NavigationSplitView {
            sidebar
        } detail: {
            VStack(spacing: 0) {
                lifecycleBanners
                if model.showsInterruptedBanner, let interrupted = model.interruptedJob {
                    InterruptedBanner(
                        job: interrupted,
                        retry: { Task { await model.retryInterrupted() } },
                        dismiss: { model.dismissInterrupted() }
                    )
                }
                screenBody
            }
            .navigationTitle(currentItem.title)
            .navigationSubtitle(currentItem.stepText)
            .toolbar {
                ToolbarItemGroup(placement: .primaryAction) {
                    if model.screen == .welcome || model.screen == .yourMac {
                        Button("Scan Again") {
                            Task { await model.reload() }
                        }
                    }
                    if model.screen == .engines {
                        Button("Check Again") {
                            Task { await model.checkEnginesAgain() }
                        }
                    }
                }
            }
        }
    }

    private var sidebar: some View {
        List(selection: selection) {
            Section("Setup") {
                ForEach(SidebarItem.allCases) { item in
                    Label {
                        HStack {
                            Text(item.title)
                            Spacer()
                            if item.isComplete(model) {
                                Image(systemName: "checkmark.circle")
                                    .foregroundStyle(.secondary)
                                    .accessibilityHidden(true)
                            }
                        }
                    } icon: {
                        Image(systemName: item.symbol)
                    }
                    .tag(item)
                    .disabled(!item.isReachable(model))
                }
            }
        }
        .navigationSplitViewColumnWidth(min: 200, ideal: 220)
        .safeAreaInset(edge: .bottom, spacing: 0) {
            Text("Nothing changes on this Mac without a click.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(16)
        }
    }

    private var selection: Binding<SidebarItem?> {
        Binding(
            get: { SidebarItem(screen: model.screen) ?? .yourMac },
            set: { item in
                if let item {
                    model.go(to: item.screen)
                }
            }
        )
    }

    private var currentItem: SidebarItem {
        SidebarItem(screen: model.screen) ?? .yourMac
    }

    @ViewBuilder
    private var lifecycleBanners: some View {
        if model.quitInProgress {
            HStack(spacing: 12) {
                ProgressView()
                    .controlSize(.small)
                if let job = model.job {
                    Text("Finishing \(job.kind.wireName) \(job.name)…")
                } else {
                    Text("Finishing…")
                }
                Spacer()
            }
            .font(.callout)
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .background(.quaternary.opacity(0.4))
        }
        if model.quitAnywayOffered {
            HStack(spacing: 12) {
                Text("The backend did not stop.")
                Spacer()
                Button("Quit anyway") {
                    model.quitAnyway()
                }
            }
            .font(.callout)
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .background(.quaternary.opacity(0.4))
        }
    }

    @ViewBuilder
    private var screenBody: some View {
        switch model.screen {
        case .welcome, .yourMac:
            YourMacView(model: model)
        case .engines:
            EnginesView(model: model, initialConsentEngine: debugConsentEngine)
        case .models:
            modelsPlaceholder
        case .benchmark:
            benchmarkPlaceholder
        case .results:
            resultsPlaceholder
        default:
            EmptyView()
        }
    }

    private var modelsPlaceholder: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(model.recommendations?.picks ?? []) { pick in
                    VStack(alignment: .leading, spacing: 4) {
                        Text("\(pick.title) — \(pick.format), \(Format.size(pick.sizeBytes))")
                        Text(pick.reason)
                            .font(.callout)
                            .foregroundStyle(.secondary)
                        if pick.downloaded {
                            Text("downloaded")
                        }
                        if let failure = model.modelRefusals[pick.modelID] {
                            Text(failure.message)
                        }
                        if let low = model.lowDisk[pick.modelID] {
                            Text("Free \(Format.size(low.amountToFree)) to download this model.")
                        }
                        HStack {
                            Button("Download") {
                                Task { await model.download(repo: pick.modelID) }
                            }
                            .disabled(!model.canStartJob)
                            Button("Quick benchmark") {
                                Task { await model.quickbench(repo: pick.modelID) }
                            }
                            .disabled(!model.canStartJob)
                        }
                    }
                }
                ForEach(model.recommendations?.excluded ?? []) { excluded in
                    Text("\(excluded.modelID): \(excluded.reason)")
                }
                if let reason = model.oneSlotReason {
                    Text(reason)
                }
            }
            .padding(20)
            .frame(maxWidth: 680, alignment: .leading)
        }
    }

    private var benchmarkPlaceholder: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                if let plan = model.quickPlan {
                    Text("\(plan.repo) — \(plan.format)")
                    Text("Stage A: \(plan.stageA.map(\.engine).joined(separator: ", "))")
                    Text("Stage B: \(plan.stageB.map(\.repo).joined(separator: ", "))")
                    Text(
                        "Download \(Format.size(plan.downloadBytes)), "
                            + Format.duration(Double(plan.estimateS))
                    )
                }
                if let refusal = model.benchmarkRefusal {
                    Text(refusal.message)
                }
                HStack {
                    Button("Stop after this cell") {
                        Task { await model.cancelJob(now: false) }
                    }
                    Button("Stop now") {
                        Task { await model.cancelJob(now: true) }
                    }
                }
                if let job = model.job {
                    Text("\(job.kind.wireName) \(job.name): \(job.state.text) \(job.message)")
                }
                ForEach(model.benchmarkCells) { cell in
                    Text("\(cell.engine): \(cell.status)\(cell.reason.map { ": \($0)" } ?? "")")
                }
            }
            .padding(20)
            .frame(maxWidth: 680, alignment: .leading)
        }
    }

    private var resultsPlaceholder: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(model.benchmarkCells) { cell in
                    Text("\(cell.engine): \(cell.status)\(cell.reason.map { ": \($0)" } ?? "")")
                }
                ForEach(model.notEvictedLines, id: \.self) { line in
                    Text(line)
                }
            }
            .padding(20)
            .frame(maxWidth: 680, alignment: .leading)
        }
    }
}

private enum SidebarItem: Int, CaseIterable, Identifiable {
    case yourMac = 1
    case engines
    case models
    case benchmark
    case results

    var id: Int { rawValue }

    var title: String {
        switch self {
        case .yourMac: return "Your Mac"
        case .engines: return "Engines"
        case .models: return "Models"
        case .benchmark: return "Benchmark"
        case .results: return "Results"
        }
    }

    var symbol: String {
        switch self {
        case .yourMac: return "desktopcomputer"
        case .engines: return "server.rack"
        case .models: return "shippingbox"
        case .benchmark: return "gauge"
        case .results: return "chart.bar.fill"
        }
    }

    var stepText: String { "Step \(rawValue) of 5" }

    var screen: Screen {
        switch self {
        case .yourMac: return .yourMac
        case .engines: return .engines
        case .models: return .models
        case .benchmark: return .benchmark
        case .results: return .results
        }
    }

    init?(screen: Screen) {
        switch screen {
        case .welcome, .yourMac:
            self = .yourMac
        case .engines:
            self = .engines
        case .models:
            self = .models
        case .benchmark:
            self = .benchmark
        case .results:
            self = .results
        default:
            return nil
        }
    }

    @MainActor
    func isComplete(_ model: AppModel) -> Bool {
        switch self {
        case .yourMac: return model.yourMacComplete
        case .engines: return model.enginesComplete
        case .models: return model.modelsComplete
        case .benchmark: return model.benchmarkComplete
        case .results: return false
        }
    }

    @MainActor
    func isReachable(_ model: AppModel) -> Bool {
        if SidebarItem(screen: model.screen) == self { return true }
        switch self {
        case .yourMac: return true
        case .engines: return model.yourMacComplete
        case .models: return model.enginesComplete
        case .benchmark: return model.modelsComplete
        case .results:
            return model.benchmarkComplete
                || !model.benchmarkCells.isEmpty
                || model.summary != nil
        }
    }
}
