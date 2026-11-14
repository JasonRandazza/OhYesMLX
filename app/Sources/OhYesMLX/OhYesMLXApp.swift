import AppKit
import OhYesMLXKit
import SwiftUI

@main
struct OhYesMLXApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @Environment(\.scenePhase) private var scenePhase
    @State private var model: AppModel

    init() {
        let model = AppModel(launcher: BackendLauncher())
        _model = State(initialValue: model)
        AppDelegate.model = model
    }

    var body: some Scene {
        Window("OhYesMLX", id: "main") {
            RootView(model: model)
                .task {
                    await model.launch()
                }
                .onChange(of: scenePhase) { _, phase in
                    if phase == .active {
                        Task { await model.appBecameActive() }
                    }
                }
                .onChange(of: model.alreadyRunning) { _, already in
                    guard already else { return }
                    if let bundleID = Bundle.main.bundleIdentifier {
                        NSRunningApplication
                            .runningApplications(withBundleIdentifier: bundleID)
                            .first?
                            .activate()
                    }
                    NSApp.terminate(nil)
                }
        }
        .defaultSize(width: 760, height: 560)
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    static var model: AppModel?

    func applicationDidFinishLaunching(_ notification: Notification) {
        Self.model?.onQuitComplete = {
            NSApp.reply(toApplicationShouldTerminate: true)
        }
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard let model = Self.model else { return .terminateNow }
        if model.shouldExit { return .terminateNow }
        Task { @MainActor in
            await model.requestQuit()
        }
        return .terminateLater
    }
}
