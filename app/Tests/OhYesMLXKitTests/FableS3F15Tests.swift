import Foundation
import XCTest
@testable import OhYesMLXKit

/// F15(a): the interrupted banner's Retry calls `retryInterrupted`, which for an install goes
/// straight to `start(.install(engine:))`. The install button's only path goes through the
/// consent sheet first (`EnginesView.startInstall` sets `installConsent`); Retry does not, so
/// a plan the user never saw can run.
@MainActor
final class FableS3F15Tests: XCTestCase {
    func testRetryOfAnInterruptedInstallDoesNotStartWithoutConsent() async throws {
        let suiteName = "ohyesmlx-fable-s3-f15-\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        addTeardownBlock {
            defaults.removePersistentDomain(forName: suiteName)
        }
        // The record a crash between writeInflight and done leaves behind.
        defaults.set(
            ["kind": "install", "name": "optiq", "started": "2026-11-15T00:00:00Z"],
            forKey: "inflightJob"
        )

        let backend = StubBackend(
            hardware: try Fixtures.hardware,
            engines: try Fixtures.engines,
            recommendations: try Fixtures.recommendations
        )
        let model = AppModel(backend: backend, defaults: defaults)
        await model.launch()

        XCTAssertEqual(model.interruptedJob?.kind, .install)
        XCTAssertFalse(model.installConsent, "nothing in this test has shown the consent sheet")

        await model.retryInterrupted()

        XCTAssertTrue(
            backend.startedJobs.isEmpty,
            "Retry started an install with installConsent false: the consent sheet was skipped"
        )
    }
}
