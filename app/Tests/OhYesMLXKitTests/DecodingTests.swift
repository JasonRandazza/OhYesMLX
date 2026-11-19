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
        XCTAssertEqual(hardware.diskTotalBytes, 994_662_584_320)
        XCTAssertEqual(hardware.usedBytes, 994_662_584_320 - 43_377_606_656)
        XCTAssertEqual(budget, 49_392_123_904)
        XCTAssertEqual(hardware.macos, "27.2.1")
        XCTAssertEqual(hardware.volumes, [Volume(path: "/", freeBytes: 43_377_606_656)])
    }

    func testHardwareWithoutDiskTotalStillDecodesAndDrawsNoBar() throws {
        let json = try Fixtures.text("hardware.json")
        let withoutTotal = json
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.contains("\"disk_total_bytes\"") }
            .joined(separator: "\n")
        let hardware = try JSONDecoder().decode(Hardware.self, from: Data(withoutTotal.utf8))

        XCTAssertNil(hardware.diskTotalBytes, "an old backend sends no total")
        XCTAssertNil(hardware.usedBytes, "no total means no used figure and no bar")
        XCTAssertEqual(hardware.diskFreeBytes, 43_377_606_656)
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
        XCTAssertEqual(plan.freeAfterBytes, 41_583_077_867)
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

    // MARK: - AC-2 (05-05) · the quickbench summary, typed

    func testFinishedSummaryDecodes() throws {
        let summary = try Fixtures.decode(QuickSummary.self, "quickbench_summary_finished.json")

        XCTAssertEqual(summary.label, "quick: measured on this Mac")
        XCTAssertEqual(summary.repo, "mlx-community/Qwen3.5-2B-4bit")
        XCTAssertEqual(summary.ended, .finished)
        XCTAssertEqual(summary.estimateS, 630)
        XCTAssertEqual(try XCTUnwrap(summary.actualS), 704.512, accuracy: 1e-9)
        XCTAssertEqual(summary.plan.stageA.count, 5)
        XCTAssertEqual(summary.resultsDir.hasSuffix("20261114T143200Z"), true)
        XCTAssertTrue(summary.notEvicted.isEmpty)
        XCTAssertEqual(summary.harness.version, "0.5.0")
        XCTAssertEqual(summary.engines.map(\.name), ["mlxlm", "osaurus", "omlx", "optiq", "vmlx"])
        XCTAssertEqual(summary.load.stageB?.label, "this Mac was busy")
        XCTAssertEqual(summary.osaurus.restored, true)

        XCTAssertEqual(summary.stageA.caveat, "engines compared on one format only")
        XCTAssertEqual(summary.stageA.winner, "omlx")
        XCTAssertEqual(summary.stageA.cells.map(\.status), ["PASS", "PASS", "PASS", "FAIL", "SKIPPED"])
        XCTAssertEqual(summary.stageA.cells.first?.decodeTPS, 55.4)
        XCTAssertEqual(summary.stageA.cells.first?.ttftS, 0.21)
        XCTAssertNil(summary.stageA.cells[3].decodeTPS, "a FAIL cell carries no figure")
        XCTAssertEqual(summary.stageA.cells[3].reason, "the server did not answer within 60 s")
        XCTAssertEqual(summary.stageB.caveat, "formats compared on one engine only")
        XCTAssertEqual(summary.stageB.engine, "omlx")
        XCTAssertEqual(summary.stageB.cells.map(\.reused), [true, false])

        let best = try XCTUnwrap(summary.best)
        XCTAssertEqual(best.engine, "omlx")
        XCTAssertEqual(best.decodeTPS, 62.1)
        XCTAssertTrue(best.quick)
        XCTAssertEqual(best.format, "oQ4 (mixed 4/5/6/8)")
        XCTAssertEqual(best.repo, "RepublicOfKorokke/Qwen3.5-2B-oQ4")
        XCTAssertEqual(summary.stageB.cells.last?.repo, "RepublicOfKorokke/Qwen3.5-2B-oQ4")
        XCTAssertEqual(summary.stageA.cells.first?.repo, "mlx-community/Qwen3.5-2B-4bit")
        XCTAssertTrue(
            summary.bestFormat.contains("oQ4"),
            "the best card names the winning cell's format, not the chosen row's"
        )
    }

    func testAnOlderSummaryWhoseBestNamesNoArtifactStillDecodes() throws {
        let text = try Fixtures.text("quickbench_summary_finished.json")
        let older = text.replacingOccurrences(
            of: "\"format\": \"oQ4 (mixed 4/5/6/8)\",\n"
                + "    \"repo\": \"RepublicOfKorokke/Qwen3.5-2B-oQ4\",\n"
                + "    \"decode_tps\": 62.1,",
            with: "\"decode_tps\": 62.1,"
        )
        XCTAssertNotEqual(older, text, "the fixture still carries the fields this removes")

        let summary = try JSONDecoder().decode(QuickSummary.self, from: Data(older.utf8))

        XCTAssertNil(summary.best?.format)
        XCTAssertNil(summary.best?.repo)
        XCTAssertEqual(summary.bestFormat, "mlx affine 4-bit gs64")
    }

    func testCancelledSummaryDecodesWithAnAbortedCellAndNoBest() throws {
        let summary = try Fixtures.decode(QuickSummary.self, "quickbench_summary_cancelled.json")

        XCTAssertEqual(summary.ended, .cancelled)
        XCTAssertNil(summary.best, "a cancelled run recommends nothing")
        XCTAssertEqual(summary.notEvicted, ["RepublicOfKorokke/Qwen3.5-2B-oQ4"])
        XCTAssertNil(summary.load.stageB)

        let aborted = try XCTUnwrap(
            summary.stageB.cells.first { $0.status == "ABORTED" }
        )
        XCTAssertEqual(aborted.reason, "stopped by the user mid-cell; no number is reported")
        XCTAssertNil(aborted.decodeTPS)
        XCTAssertNil(aborted.ttftS)
        XCTAssertEqual(
            summary.stageA.cells.map(\.status),
            ["PASS", "SKIPPED", "SKIPPED"]
        )
    }

    func testASummaryMissingThePinnedKeysFailsDecoding() {
        let decoder = JSONDecoder()
        XCTAssertThrowsError(
            try decoder.decode(QuickSummary.self, from: Data("{\"ended\": \"finished\"}".utf8))
        )
    }

    func testPayloadDataKeepsKeysTheTypedSummaryDoesNotModel() throws {
        // A key the client does not model is what a re-encode of the typed value would drop,
        // and that is exactly what Export must not do: the file is the record, so a field the
        // backend added after this client shipped still lands in it.
        var object = try XCTUnwrap(
            try JSONSerialization.jsonObject(
                with: Fixtures.data("quickbench_summary_finished.json")
            ) as? [String: Any]
        )
        object["future_field"] = ["added_by": "a later backend", "value": 7]
        let data = try JSONSerialization.data(withJSONObject: object)

        let event = JobEvent(
            seq: 9,
            type: .result,
            message: "quickbench finished",
            fraction: nil,
            payload: try JSONDecoder().decode(JSONValue.self, from: data)
        )
        let payload = try XCTUnwrap(event.payloadData)
        let written = try XCTUnwrap(
            try JSONSerialization.jsonObject(with: payload) as? [String: Any]
        )
        XCTAssertEqual(
            Set(written.keys),
            [
                "label", "repo", "format", "plan", "estimate_s", "actual_s", "ended",
                "results_dir", "not_evicted", "harness", "engines", "load", "osaurus",
                "stage_a", "stage_b", "best", "future_field",
            ]
        )
        let future = try XCTUnwrap(written["future_field"] as? [String: Any])
        XCTAssertEqual(future["added_by"] as? String, "a later backend")
        XCTAssertEqual(future["value"] as? Int, 7, "the value survives as sent")

        // The typed value is the same record minus that key, which is why Export does not use it.
        let typed = try JSONDecoder().decode(QuickSummary.self, from: data)
        let reencoded = try XCTUnwrap(
            try JSONSerialization.jsonObject(with: try JSONEncoder().encode(typed)) as? [String: Any]
        )
        XCTAssertNil(reencoded["future_field"], "a re-encode of the typed value drops it")
    }

    func testPayloadDataKeepsIntegersAsIntegers() throws {
        // A byte count above 2^31 is what a download event carries; re-serialising must not
        // turn it into a float or truncate it.
        let json = Data(#"{"bytes_done": 5000000000, "bytes_total": 12884901888}"#.utf8)
        let event = JobEvent(
            seq: 1,
            type: .progress,
            message: "downloading",
            fraction: 0.5,
            payload: try JSONDecoder().decode(JSONValue.self, from: json)
        )

        let data = try XCTUnwrap(event.payloadData)

        XCTAssertEqual(
            String(decoding: data, as: UTF8.self),
            #"{"bytes_done":5000000000,"bytes_total":12884901888}"#
        )
    }
}
