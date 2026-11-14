import XCTest
@testable import OhYesMLXKit

final class DecodingTests: XCTestCase {
    func testHardwareDecodesWithInt64ByteCounts() throws {
        let hardware = try Fixtures.hardware
        let ram: Int64 = hardware.ramBytes
        let disk: Int64 = hardware.diskFreeBytes
        let budget: Int64 = hardware.modelBudgetBytes

        XCTAssertTrue(hardware.supported)
        XCTAssertNil(hardware.unsupportedReason)
        XCTAssertEqual(hardware.chip, "Apple M2 Max")
        XCTAssertEqual(hardware.family, "M2")
        XCTAssertEqual(hardware.tier, "max")
        XCTAssertEqual(hardware.cpuCores, 12)
        XCTAssertEqual(hardware.gpuCores, 30)
        XCTAssertEqual(ram, 68_719_476_736)
        XCTAssertEqual(disk, 43_377_606_656)
        XCTAssertEqual(budget, 49_392_123_904)
        XCTAssertEqual(hardware.macos, "27.2.1")
        XCTAssertEqual(hardware.volumes, [Volume(path: "/", freeBytes: 43_377_606_656)])
    }

    func testEngineStatusDecodes() throws {
        let engines = try Fixtures.engines
        XCTAssertEqual(engines.count, 5)
        XCTAssertEqual(engines.map(\.name), ["mlxlm", "osaurus", "omlx", "optiq", "vmlx"])
        let mlxlm = try XCTUnwrap(engines.first)
        XCTAssertEqual(mlxlm.title, "mlx-lm")
        XCTAssertTrue(mlxlm.installed)
        XCTAssertEqual(mlxlm.version, "0.31.3")
        XCTAssertEqual(mlxlm.path, "/Users/user/.local/share/ohyesmlx/mlx-lm-0.31.3/bin/mlx_lm.server")
        XCTAssertTrue(mlxlm.tested)
        XCTAssertEqual(mlxlm.verified, "2026-10-29")
        XCTAssertNil(mlxlm.install)
        XCTAssertFalse(engines[1].tested)
    }

    func testEngineStatusDecodesAnInstallPlan() throws {
        let json = """
        [{
          "name": "osaurus",
          "title": "Osaurus",
          "blurb": "Native menubar app with its own MLX engine.",
          "installed": false,
          "version": null,
          "path": null,
          "tested": false,
          "verified": "2026-11-02",
          "install": {
            "engine": "osaurus",
            "kind": "guided_download",
            "source_url": "https://osaurus.ai/",
            "size_bytes_estimate": null,
            "needs_admin": false,
            "steps": [
              {"id": "open", "label": "Open the download page", "command": null},
              {"id": "verify", "label": "Verify the install", "command": ["/usr/bin/true"]}
            ]
          }
        }]
        """
        let engines = try JSONDecoder().decode([EngineStatus].self, from: Data(json.utf8))
        let plan = try XCTUnwrap(engines.first?.install)
        XCTAssertEqual(plan.engine, "osaurus")
        XCTAssertEqual(plan.kind, "guided_download")
        XCTAssertEqual(plan.sourceURL, "https://osaurus.ai/")
        XCTAssertNil(plan.sizeBytesEstimate)
        XCTAssertFalse(plan.needsAdmin)
        XCTAssertEqual(plan.steps.map(\.id), ["open", "verify"])
        XCTAssertEqual(plan.steps[1].command, ["/usr/bin/true"])
    }

    func testRecommendationsDecode() throws {
        let recommendations = try Fixtures.recommendations
        XCTAssertEqual(recommendations.picks.count, 12)
        XCTAssertTrue(recommendations.excluded.isEmpty)
        XCTAssertNil(recommendations.unsupportedReason)

        let first = try XCTUnwrap(recommendations.picks.first)
        XCTAssertEqual(first.modelID, "mlx-community/LFM2.5-8B-A1B-MLX-4bit")
        XCTAssertEqual(first.sizeBytes, 4_782_228_614)
        XCTAssertEqual(first.fit, "comfortable")
        XCTAssertEqual(first.fitBasis, "estimated")
        XCTAssertTrue(first.startHere)
        XCTAssertFalse(first.downloaded)
        XCTAssertNil(first.measuredHere)

        let measured = try XCTUnwrap(
            recommendations.picks.first { $0.modelID == "mlx-community/Qwen3.5-2B-4bit" }
        )
        XCTAssertEqual(measured.measuredHere?.engine, "omlx")
        XCTAssertEqual(measured.measuredHere?.quick, true)
        XCTAssertEqual(try XCTUnwrap(measured.measuredHere?.ttftS), 0.06846141593996435, accuracy: 1e-12)
    }

    func testQuickPlanDecodes() throws {
        let plan = try Fixtures.quickPlan
        XCTAssertEqual(plan.repo, "mlx-community/Qwen3.5-2B-4bit")
        XCTAssertEqual(plan.format, "mlx affine 4-bit gs64")
        XCTAssertEqual(plan.stageA.count, 5)
        XCTAssertEqual(plan.stageA.first?.engine, "mlxlm")
        XCTAssertEqual(plan.stageA.first?.tested, true)
        XCTAssertEqual(plan.stageB.count, 1)
        XCTAssertEqual(plan.stageB.first?.sizeBytes, 1_794_528_789)
        XCTAssertEqual(plan.stageB.first?.downloaded, false)
        XCTAssertEqual(plan.downloadBytes, 1_794_528_789)
        XCTAssertTrue(plan.osaurus)
        XCTAssertEqual(plan.estimateS, 630)
    }

    func testBackendErrorDecodes() throws {
        let envelope = try Fixtures.decode(BackendErrorEnvelope.self, "not_found.json")
        XCTAssertEqual(envelope.error.code, "not_found")
        XCTAssertEqual(envelope.error.status, 404)
        XCTAssertEqual(envelope.error.message, "no such path")

        let refused = try Fixtures.decode(BackendErrorEnvelope.self, "quickbench_plan_refused.json")
        XCTAssertEqual(refused.error.code, "bad_args")
        XCTAssertEqual(refused.error.status, 400)
        XCTAssertEqual(refused.error.message, "nope/nope is not a catalog model; nothing was measured")
    }

    func testMissingRequiredKeyFailsDecoding() {
        let decoder = JSONDecoder()
        XCTAssertThrowsError(try decoder.decode(Hardware.self, from: Data("{}".utf8)))
        XCTAssertThrowsError(try decoder.decode(JobEvent.self, from: Data("{\"seq\": 1}".utf8)))
    }
}
