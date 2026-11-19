import Foundation
import XCTest
@testable import OhYesMLXKit

/// Plan 055-02, Phase 5.5 items 2, 3 and 8: Retry of an interrupted evict opens the remove
/// sheet, a second launch activates the other instance, and Free disk names its volume.
@MainActor
final class Plan05502Tests: XCTestCase {
    private let repo = "mlx-community/Qwen3.5-2B-4bit"

    private func pick(modelID: String, downloaded: Bool) -> Pick {
        Pick(
            modelID: modelID,
            title: "Qwen3.5 2B",
            paramsB: 2,
            format: "mlx affine 4-bit gs64",
            sizeBytes: 1_400_000_000,
            fit: "comfortable",
            fitBasis: "estimated",
            engines: ["mlxlm"],
            installNeeded: false,
            startHere: true,
            reason: "Fits with room to spare.",
            downloaded: downloaded,
            measuredHere: nil
        )
    }

    /// A model whose inflight record names *kind* for *name*, and whose picks are *picks*.
    private func makeModel(
        picks: [Pick],
        kind: String?,
        name: String? = nil
    ) throws -> (model: AppModel, backend: StubBackend, defaults: UserDefaults) {
        let suiteName = "ohyesmlx-plan-055-02-\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        addTeardownBlock {
            defaults.removePersistentDomain(forName: suiteName)
        }
        if let kind {
            defaults.set(
                [
                    "kind": kind,
                    "name": name ?? repo,
                    "started": ISO8601DateFormatter().string(from: Date()),
                ],
                forKey: "inflightJob"
            )
        }
        let backend = StubBackend(
            hardware: try Fixtures.hardware,
            engines: try Fixtures.engines,
            recommendations: Recommendations(picks: picks, excluded: [], unsupportedReason: nil)
        )
        let model = AppModel(backend: backend, defaults: defaults)
        return (model, backend, defaults)
    }

    private func waitUntil(
        timeout: TimeInterval = 2,
        _ condition: @MainActor () -> Bool
    ) async {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if condition() { return }
            try? await Task.sleep(for: .milliseconds(5))
        }
    }

    // MARK: - AC-1 · Retry of an interrupted evict opens the remove sheet

    func testRetryOfAnInterruptedEvictRequestsTheRemoveSheetAndStartsNothing() async throws {
        let downloaded = pick(modelID: repo, downloaded: true)
        let (model, backend, _) = try makeModel(picks: [downloaded], kind: "evict")
        await model.launch()
        XCTAssertEqual(model.interruptedJob?.kind, .evict)

        await model.retryInterrupted()

        XCTAssertEqual(model.screen, .models, "Retry must land on Models")
        XCTAssertEqual(model.evictRequest, repo, "Retry must name the pick it wants confirmed")
        XCTAssertTrue(
            backend.startedJobs.isEmpty,
            "Retry started an evict without the user's confirmation (S3-F15)"
        )
    }

    func testTheEvictRequestResolvesToThePickTheRemoveButtonOpens() {
        let downloaded = pick(modelID: repo, downloaded: true)
        XCTAssertEqual(AppModel.requestedEvictPick(repo, in: [downloaded]), downloaded)
        XCTAssertNil(
            AppModel.requestedEvictPick("org/no-longer-on-disk", in: [downloaded]),
            "a pick that is no longer listed opens nothing"
        )
        XCTAssertNil(AppModel.requestedEvictPick(nil, in: [downloaded]))
    }

    func testTheEvictRequestUsesTheRemoveButtonsOwnGate() async throws {
        let downloaded = pick(modelID: repo, downloaded: true)
        let (model, backend, _) = try makeModel(picks: [downloaded], kind: nil)
        await model.launch()

        XCTAssertTrue(model.canRemove(downloaded), "a downloaded pick with an idle slot offers Remove")
        XCTAssertFalse(
            model.canRemove(pick(modelID: repo, downloaded: false)),
            "Remove is not offered for a pick that is not on disk"
        )

        backend.enqueue(
            events: [
                JobEvent(seq: 1, type: .progress, message: "Downloading", fraction: 0.2, payload: nil)
            ],
            hold: true
        )
        let download = Task { await model.download(repo: "org/other") }
        await waitUntil { model.job != nil }

        XCTAssertFalse(model.canRemove(downloaded), "an active job greys Remove, and the request answers to it")

        backend.releaseJob([
            JobEvent(seq: 2, type: .done, message: "finished", fraction: nil, payload: nil)
        ])
        await download.value
    }

    // MARK: - AC-2 · the second launch activates the other instance

    func testTheOtherInstanceIsThePidThatIsNotThisProcess() {
        XCTAssertEqual(
            BackendLauncher.otherPID(among: [111, 222], me: 111),
            222,
            "the second launch must activate the other instance, never itself"
        )
        XCTAssertNil(
            BackendLauncher.otherPID(among: [111], me: 111),
            "no other instance means nothing is activated"
        )
        XCTAssertNil(BackendLauncher.otherPID(among: [], me: 111))
    }

    // MARK: - AC-3 · Free disk names its volume

    /// The fixture's Hardware with a `disk_volume` key added: nil leaves the key out, which is
    /// what a backend that predates the field sends, and "null" is what a failed probe sends.
    private func hardwareWithVolume(_ fragment: String?) throws -> Hardware {
        var json = try Fixtures.text("hardware.json")
        if let fragment {
            json = json.replacingOccurrences(
                of: "\"model_budget_bytes\": 49392123904",
                with: "\"model_budget_bytes\": 49392123904, \"disk_volume\": \(fragment)"
            )
        }
        return try JSONDecoder().decode(Hardware.self, from: Data(json.utf8))
    }

    func testDiskVolumeDecodesAndIsOptional() throws {
        let absent = try hardwareWithVolume(nil)
        XCTAssertNil(absent.diskVolume, "a backend with no volume field still decodes")

        let external = try hardwareWithVolume("\"/Volumes/Storage\"")
        XCTAssertEqual(external.diskVolume, "/Volumes/Storage")

        XCTAssertNil(
            try hardwareWithVolume("null").diskVolume,
            "a failed probe sends null and never a guessed \"/\""
        )
    }

    func testFreeDiskLabelIsUnchangedOnTheStartupDisk() throws {
        XCTAssertEqual(try hardwareWithVolume(nil).freeDiskLabel, "Free disk")
        XCTAssertEqual(try hardwareWithVolume("\"/\"").freeDiskLabel, "Free disk")
    }

    func testFreeDiskLabelNamesAnotherVolume() throws {
        XCTAssertEqual(
            try hardwareWithVolume("\"/Volumes/Storage\"").freeDiskLabel,
            "Free disk on Storage"
        )
    }
}
