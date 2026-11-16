import Foundation
import XCTest
@testable import OhYesMLXKit

/// F13: the Benchmark screen disables both stop controls once either has been pressed, so
/// "Stop After This Cell" cannot be escalated to "Stop Now" while a cell hangs. The model
/// itself accepts the escalation; this test pins that, which is what makes the view's
/// `.disabled(stopping)` the whole of the lock.
@MainActor
final class FableS3F13Tests: XCTestCase {
    private func waitUntil(
        timeout: TimeInterval = 2,
        _ condition: () -> Bool
    ) async {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if condition() { return }
            try? await Task.sleep(for: .milliseconds(5))
        }
    }

    func testStopNowReachesTheBackendAfterStopAfterThisCell() async throws {
        let suiteName = "ohyesmlx-fable-s3-f13-\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        addTeardownBlock {
            defaults.removePersistentDomain(forName: suiteName)
        }
        let backend = StubBackend(
            hardware: try Fixtures.hardware,
            engines: try Fixtures.engines,
            recommendations: try Fixtures.recommendations
        )
        let model = AppModel(backend: backend, defaults: defaults)

        backend.enqueue(
            events: [JobEvent(seq: 1, type: .progress, message: "downloading", fraction: 0.1, payload: nil)],
            hold: true
        )
        let job = Task { await model.download(repo: "mlx-community/Qwen3.5-2B-4bit") }
        await waitUntil { model.job != nil }
        XCTAssertEqual(model.job?.state, .running)

        await model.cancelJob(now: false)
        XCTAssertEqual(model.job?.state, .stoppingAfterCell)

        await model.cancelJob(now: true)
        XCTAssertEqual(
            backend.cancelCalls.map(\.now),
            [false, true],
            "a second press of Stop Now must reach the backend"
        )
        XCTAssertEqual(model.job?.state, .stoppingNow)

        backend.releaseJob([JobEvent(seq: 2, type: .done, message: "stopped", fraction: nil, payload: nil)])
        await job.value
    }
}
