import Foundation
import XCTest
@testable import OhYesMLXKit

/// F10: a download or an evict changes what is on disk, but the app's `hardware` value —
/// the only source of the Models toolbar's "Free disk" and the Benchmark screen's
/// "Free disk after" — is not re-read when the job finishes. These tests give the stub a
/// lower `disk_free_bytes` on the second call, as a real download would leave behind, and
/// assert the model picked it up.
@MainActor
final class FableS3F10Tests: XCTestCase {
    private struct Stack {
        let model: AppModel
        let backend: StubBackend
        let defaults: UserDefaults
        let suiteName: String
    }

    private func makeStack(freeBytes: Int64) throws -> Stack {
        let base = try Fixtures.hardware
        let suiteName = "ohyesmlx-fable-s3-f10-\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        let backend = StubBackend(
            hardware: hardware(base, freeBytes: freeBytes),
            engines: try Fixtures.engines,
            recommendations: try Fixtures.recommendations
        )
        let model = AppModel(backend: backend, defaults: defaults)
        addTeardownBlock {
            defaults.removePersistentDomain(forName: suiteName)
        }
        return Stack(model: model, backend: backend, defaults: defaults, suiteName: suiteName)
    }

    private func hardware(_ base: Hardware, freeBytes: Int64) -> Hardware {
        Hardware(
            supported: base.supported,
            unsupportedReason: base.unsupportedReason,
            chip: base.chip,
            family: base.family,
            tier: base.tier,
            cpuCores: base.cpuCores,
            gpuCores: base.gpuCores,
            ramBytes: base.ramBytes,
            macos: base.macos,
            diskFreeBytes: freeBytes,
            diskTotalBytes: base.diskTotalBytes,
            volumes: base.volumes,
            modelBudgetBytes: base.modelBudgetBytes
        )
    }

    private func done(_ seq: Int, _ message: String) -> JobEvent {
        JobEvent(seq: seq, type: .done, message: message, fraction: nil, payload: nil)
    }

    func testDownloadCompletionRefreshesFreeDisk() async throws {
        let before: Int64 = 40_000_000_000
        let after: Int64 = 20_000_000_000
        let stack = try makeStack(freeBytes: before)
        await stack.model.reload()
        XCTAssertEqual(stack.model.hardware?.diskFreeBytes, before)

        // The download landed 20 GB of weights on the disk.
        stack.backend.setHardware(hardware(try Fixtures.hardware, freeBytes: after))
        stack.backend.enqueue(events: [done(1, "download finished")])
        await stack.model.download(repo: "mlx-community/Qwen3-0.5B-4bit")
        XCTAssertEqual(stack.model.job?.state, .finished)

        XCTAssertEqual(
            stack.model.hardware?.diskFreeBytes,
            after,
            "a finished download leaves the free-disk figure re-read, not the launch-time one"
        )
    }

    func testEvictCompletionRefreshesFreeDisk() async throws {
        let before: Int64 = 20_000_000_000
        let after: Int64 = 25_000_000_000
        let stack = try makeStack(freeBytes: before)
        await stack.model.reload()
        XCTAssertEqual(stack.model.hardware?.diskFreeBytes, before)

        // The removal freed 5 GB.
        stack.backend.setHardware(hardware(try Fixtures.hardware, freeBytes: after))
        stack.backend.enqueue(events: [done(1, "removed")])
        await stack.model.evict(repo: "mlx-community/Qwen3-0.5B-4bit")
        XCTAssertEqual(stack.model.job?.state, .finished)

        XCTAssertEqual(
            stack.model.hardware?.diskFreeBytes,
            after,
            "a finished evict leaves the free-disk figure re-read, not the launch-time one"
        )
    }
}
