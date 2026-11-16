import Foundation
import XCTest
@testable import OhYesMLXKit

/// S3-F2: `AppModel.apply`'s `.result` branch (`AppModel.swift:700-702`) has no
/// `args.kind == .quickbench` guard, so the `result` event a download, evict or install
/// emits overwrites the finished quickbench's `summaryData` and nils `summary`. Results
/// then renders the live-cells branch, "This run has not finished yet" (`ResultsView.swift:45-51`),
/// and Export stays enabled (`:72`) writing the job receipt as
/// `OhYesMLX-quickbench-<stamp>.json` (`:195-205`).
@MainActor
final class FableS3F2Tests: XCTestCase {
    private var benchRepo: String { "mlx-community/Qwen3.5-2B-4bit" }
    private var otherRepo: String { "mlx-community/Qwen3.5-4B-4bit" }

    private func makeModel() throws -> (AppModel, StubBackend) {
        let suiteName = "ohyesmlx-fable-s3f2-\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        let backend = StubBackend(
            hardware: try Fixtures.hardware,
            engines: try Fixtures.engines,
            recommendations: try Fixtures.recommendations,
            plan: try Fixtures.quickPlan
        )
        let model = AppModel(
            backend: backend,
            defaults: defaults,
            bundlePath: "/Applications/OhYesMLX.app"
        )
        addTeardownBlock {
            defaults.removePersistentDomain(forName: suiteName)
        }
        return (model, backend)
    }

    private func done(_ seq: Int, _ message: String) -> JobEvent {
        JobEvent(seq: seq, type: .done, message: message, fraction: nil, payload: nil)
    }

    /// One cell lands as progress, then the summary, then done — the order a real
    /// quickbench produces, so `liveCells` is non-empty when the summary arrives.
    private func runQuickbench(on model: AppModel, backend: StubBackend) async throws -> Data {
        backend.enqueue(events: [
            JobEvent(
                seq: 1,
                type: .progress,
                message: "mlxlm … PASS",
                fraction: 0.5,
                payload: .object([
                    "stage": .string("A"),
                    "engine": .string("mlxlm"),
                    "format": .string("mlx affine 4-bit gs64"),
                    "status": .string("PASS"),
                    "reason": .null,
                ])
            ),
            JobEvent(
                seq: 2,
                type: .result,
                message: "quickbench finished",
                fraction: nil,
                payload: try Fixtures.decode(JSONValue.self, "quickbench_summary_finished.json")
            ),
            done(3, "quickbench finished"),
        ])
        await model.quickbench(repo: benchRepo)
        XCTAssertEqual(model.job?.kind, .quickbench)
        XCTAssertEqual(model.job?.state, .finished)
        XCTAssertEqual(
            model.summary?.ended, .finished,
            "the quickbench fixture did not land as a finished summary"
        )
        XCTAssertFalse(
            model.liveCells.isEmpty,
            "precondition: a real run leaves live cells behind, so ResultsView takes its live-cells branch once summary is nil"
        )
        return try XCTUnwrap(model.summaryData)
    }

    func testADownloadResultDoesNotReplaceTheBenchmarkSummary() async throws {
        let (model, backend) = try makeModel()
        await model.launch()
        let benchmarkExport = try await runQuickbench(on: model, backend: backend)

        // fetch.py:1172-1176 — the download's own receipt.
        backend.enqueue(events: [
            JobEvent(
                seq: 1,
                type: .result,
                message: "downloaded 1234 bytes for \(otherRepo) at abc",
                fraction: nil,
                payload: .object([
                    "status": .string("downloaded"),
                    "repo": .string(otherRepo),
                    "bytes": .int(1234),
                ])
            ),
            done(2, "download finished"),
        ])
        await model.download(repo: otherRepo)
        XCTAssertEqual(model.job?.kind, .download)
        XCTAssertEqual(model.job?.state, .finished)

        XCTAssertEqual(
            model.summary?.ended, .finished,
            "the download's result event emptied the finished summary (AppModel.swift:700-702 has no kind guard)"
        )
        XCTAssertEqual(
            model.summaryData, benchmarkExport,
            "Export would write the download receipt, not the benchmark summary (ResultsView.swift:72, 195-205)"
        )
    }

    func testAnEvictResultDoesNotReplaceTheBenchmarkSummary() async throws {
        let (model, backend) = try makeModel()
        await model.launch()
        let benchmarkExport = try await runQuickbench(on: model, backend: backend)

        // fetch.py:1303 — the evict's receipt.
        backend.enqueue(events: [
            JobEvent(
                seq: 1,
                type: .result,
                message: "removed 1 paths for \(otherRepo)",
                fraction: nil,
                payload: .object([
                    "repo": .string(otherRepo),
                    "removed": .array([.string("/models/x/blob")]),
                    "kept": .array([]),
                ])
            ),
            done(2, "eviction finished"),
        ])
        await model.evict(repo: otherRepo)
        XCTAssertEqual(model.job?.kind, .evict)
        XCTAssertEqual(model.job?.state, .finished)

        XCTAssertEqual(
            model.summary?.ended, .finished,
            "the evict's result event emptied the finished summary (AppModel.swift:700-702 has no kind guard)"
        )
        XCTAssertEqual(
            model.summaryData, benchmarkExport,
            "Export would write the eviction receipt, not the benchmark summary"
        )
    }

    func testAnInstallResultDoesNotReplaceTheBenchmarkSummary() async throws {
        let (model, backend) = try makeModel()
        await model.launch()
        let benchmarkExport = try await runQuickbench(on: model, backend: backend)
        model.installConsent = true

        // engines.py:1317 — the install's receipt.
        backend.enqueue(events: [
            JobEvent(
                seq: 1,
                type: .result,
                message: "installation complete",
                fraction: nil,
                payload: .object(["installed": .bool(true)])
            ),
            done(2, "install finished"),
        ])
        await model.install(engine: "mlxlm")
        XCTAssertEqual(model.job?.kind, .install)
        XCTAssertEqual(model.job?.state, .finished)

        XCTAssertEqual(
            model.summary?.ended, .finished,
            "the install's result event emptied the finished summary (AppModel.swift:700-702 has no kind guard)"
        )
        XCTAssertEqual(
            model.summaryData, benchmarkExport,
            "Export would write the install receipt, not the benchmark summary"
        )
    }
}
