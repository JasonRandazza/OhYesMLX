import OhYesMLXKit
import SwiftUI

struct RootView: View {
    @Bindable var model: AppModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            banners
            switch model.screen {
            case .launching:
                ProgressView("Launching…")
            case .couldntStart:
                Text(model.launchError ?? "The backend could not start.")
            case .unsupported:
                Text(model.hardware?.unsupportedReason ?? "This Mac is not supported.")
            case .welcome:
                welcome
            case .yourMac:
                yourMac
            case .engines:
                engines
            case .models:
                models
            case .benchmark:
                benchmark
            case .results:
                results
            }
            Spacer()
        }
        .padding(20)
        .frame(minWidth: 660, minHeight: 460, alignment: .topLeading)
    }

    @ViewBuilder
    private var banners: some View {
        if model.quitAnywayOffered {
            HStack {
                Text("The backend did not stop")
                Button("Quit anyway") {
                    model.quitAnyway()
                }
            }
        }
        if model.quitInProgress, let job = model.job {
            Text("Finishing \(job.kind.wireName) \(job.name)…")
        }
        if model.backendStopped != nil {
            HStack {
                Text("The backend stopped")
                Button("Relaunch") {
                    Task { await model.relaunch() }
                }
            }
        }
        if let interrupted = model.interruptedJob, model.showsInterruptedBanner {
            HStack {
                Text(
                    "\(interrupted.kind.wireName) of \(interrupted.name) was interrupted when OhYesMLX quit."
                )
                Button("Retry") {
                    Task { await model.retryInterrupted() }
                }
                Button("Dismiss") {
                    model.dismissInterrupted()
                }
            }
        }
        if model.alreadyRunning {
            Text("OhYesMLX is already running.")
        }
        if let refusal = model.refusal {
            Text(refusal.message)
        }
    }

    private var welcome: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Welcome")
            if let hardware = model.hardware {
                Text("\(hardware.chip), \(hardware.cpuCores) cores, \(AppModel.formatGB(hardware.ramBytes)) of memory")
                Text("\(AppModel.formatGB(hardware.diskFreeBytes)) free on disk")
            }
            navigation
        }
    }

    private var navigation: some View {
        HStack {
            Button("Your Mac") { model.go(to: .yourMac) }
            Button("Engines") { model.go(to: .engines) }
            Button("Models") { model.go(to: .models) }
            Button("Benchmark") { model.go(to: .benchmark) }
            Button("Results") { model.go(to: .results) }
            Button("Welcome") { model.go(to: .welcome) }
        }
    }

    private var yourMac: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Your Mac")
            if let hardware = model.hardware {
                Text("Chip: \(hardware.chip) (\(hardware.family) \(hardware.tier))")
                Text("CPU cores: \(hardware.cpuCores)")
                Text("GPU cores: \(hardware.gpuCores.map(String.init) ?? "unknown")")
                Text("Memory: \(AppModel.formatGB(hardware.ramBytes))")
                Text("macOS: \(hardware.macos)")
                Text("Disk free: \(AppModel.formatGB(hardware.diskFreeBytes))")
                Text("Model budget: \(AppModel.formatGB(hardware.modelBudgetBytes))")
            }
            navigation
        }
    }

    private var engines: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Engines")
            Button("Check again") {
                Task { await model.checkEnginesAgain() }
            }
            List(model.engines) { engine in
                VStack(alignment: .leading) {
                    Text("\(engine.title) — \(engine.version ?? "not installed")")
                    Text(engine.installed ? "installed" : "not installed")
                        + Text(engine.tested ? " · tested" : " · untested")
                    if let failure = model.engineFailures[engine.name] {
                        Text("\(failure.code): \(failure.outputTail)")
                    }
                }
            }
        }
        .onAppear {
            Task { await model.enginesScreenAppeared() }
        }
    }

    private var models: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Models")
            List {
                ForEach(model.recommendations?.picks ?? []) { pick in
                    VStack(alignment: .leading) {
                        Text("\(pick.title) — \(pick.format), \(AppModel.formatGB(pick.sizeBytes))")
                        Text(pick.reason)
                        if pick.downloaded {
                            Text("downloaded")
                        }
                        if let failure = model.modelRefusals[pick.modelID] {
                            Text(failure.message)
                        }
                        if let low = model.lowDisk[pick.modelID] {
                            Text("Free \(AppModel.formatGB(low.amountToFree)) to download this model.")
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
            }
            if let reason = model.oneSlotReason {
                Text(reason)
            }
            navigation
        }
    }

    private var benchmark: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Benchmark")
            if let plan = model.quickPlan {
                Text("\(plan.repo) — \(plan.format)")
                Text("Stage A: \(plan.stageA.map(\.engine).joined(separator: ", "))")
                Text("Stage B: \(plan.stageB.map(\.repo).joined(separator: ", "))")
                Text("Download \(AppModel.formatGB(plan.downloadBytes)), about \(plan.estimateS) s")
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
            navigation
        }
    }

    private var results: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Results")
            ForEach(model.benchmarkCells) { cell in
                Text("\(cell.engine): \(cell.status)\(cell.reason.map { ": \($0)" } ?? "")")
            }
            ForEach(model.notEvictedLines, id: \.self) { line in
                Text(line)
            }
            navigation
        }
    }
}
