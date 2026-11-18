import Foundation
import XCTest
@testable import OhYesMLXKit

/// Plan 05-11 T4: the Results caveats (S3-F9, AC-7) and the Models Re-download row (P5-11, AC-8),
/// asserted on the Kit-side values the views read.
final class Plan0511T4Tests: XCTestCase {

    // MARK: - P5-11 mismatch_on_disk

    private func pick(mismatch: String?) throws -> Pick {
        var object = try XCTUnwrap(
            try JSONSerialization.jsonObject(with: Fixtures.data("recommendations.json")) as? [String: Any]
        )
        var picks = try XCTUnwrap(object["picks"] as? [[String: Any]])
        var first = picks[0]
        if let mismatch {
            first["mismatch_on_disk"] = mismatch
        } else {
            first["mismatch_on_disk"] = NSNull()
        }
        picks[0] = first
        object["picks"] = picks
        let data = try JSONSerialization.data(withJSONObject: object)
        return try JSONDecoder().decode(Recommendations.self, from: data).picks[0]
    }

    func testAbsentMismatchDecodesToNilAndKeepsDownload() throws {
        let recs = try Fixtures.decode(Recommendations.self, "recommendations.json")
        let row = try XCTUnwrap(recs.picks.first)
        XCTAssertNil(row.mismatchOnDisk)
        XCTAssertEqual(row.downloadTitle, "Download")
        XCTAssertNil(row.mismatchLine)
    }

    func testNullMismatchIsNil() throws {
        let row = try pick(mismatch: nil)
        XCTAssertNil(row.mismatchOnDisk)
        XCTAssertEqual(row.downloadTitle, "Download")
    }

    func testOursOffersReDownload() throws {
        let row = try pick(mismatch: "ours")
        XCTAssertEqual(row.mismatchOnDisk, .ours)
        XCTAssertEqual(row.downloadTitle, "Re-download")
        XCTAssertNil(row.mismatchLine)
    }

    func testForeignOffersNoButtonAndSaysRemoveFirstWithoutCorrupt() throws {
        let row = try pick(mismatch: "foreign")
        XCTAssertEqual(row.mismatchOnDisk, .foreign)
        let line = try XCTUnwrap(row.mismatchLine)
        XCTAssertTrue(line.contains("Hugging Face cache"))
        XCTAssertFalse(line.lowercased().contains("corrupt"))
        XCTAssertFalse(row.downloadTitle.lowercased().contains("corrupt"))
    }

    @MainActor
    func testMismatchScenarioStagesOneOursAndOneForeignRow() async throws {
        let model = StubScenario.modelsMismatch.makeModel()
        await StubScenario.modelsMismatch.drive(model)
        let kinds = (model.recommendations?.picks ?? []).compactMap(\.mismatchOnDisk)
        XCTAssertEqual(Set(kinds), [.ours, .foreign])
    }

    // MARK: - S3-F9 busy and tie

    private func finished() throws -> QuickSummary {
        try Fixtures.decode(QuickSummary.self, "quickbench_summary_finished.json")
    }

    func testBusyLineIsPerStageAndNilWhenClean() throws {
        let summary = try finished()
        XCTAssertNil(summary.busyLine(stageA: true))
        XCTAssertEqual(summary.busyLine(stageA: false), "this Mac was busy")
    }

    func testSingleWinnerIsFastestAndNoTieLine() throws {
        let summary = try finished()
        XCTAssertFalse(summary.stageA.isTied)
        XCTAssertNil(summary.bestTieLine)
        XCTAssertEqual(summary.bestHeading, "Best on your Mac")
        let badges = summary.stageA.cells.compactMap { summary.stageA.badge(for: $0) }
        XCTAssertEqual(badges, [.fastest])
    }

    func testTwoEngineTieBadgesNobodyFastestAndStatesTheTie() throws {
        let data = try StubScenario.stubSummaryData(cancelled: false, busyTie: true)
        let summary = try JSONDecoder().decode(QuickSummary.self, from: data)
        XCTAssertTrue(summary.stageA.isTied)
        let badges = summary.stageA.cells.map { summary.stageA.badge(for: $0) }
        XCTAssertFalse(badges.contains(.fastest))
        XCTAssertEqual(
            Set(summary.stageA.cells.filter { summary.stageA.badge(for: $0) == .tied }.map(\.engine)),
            Set(summary.stageA.tie)
        )
        XCTAssertTrue(try XCTUnwrap(summary.bestTieLine).contains("tied"))
        XCTAssertNotEqual(summary.bestHeading, "Best on your Mac")
        XCTAssertEqual(summary.busyLine(stageA: true), "this Mac was busy")
    }
}
