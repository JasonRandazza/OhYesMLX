import Foundation
import XCTest
@testable import OhYesMLXKit

/// S3-F9: the finished summary carries the run's own contention label and its stage-A tie
/// list, and the Results screen renders neither — so a stage the harness flagged "this Mac
/// was busy" reads as a clean result, and one engine inside the tie band is singled out as
/// "fastest in stage" under a "Best on your Mac" heading.
///
/// The rendering lives in the `OhYesMLX` executable target, which this test bundle does not
/// link, so a view cannot be instantiated here. The tests therefore split the claim in two:
/// the summary arrives carrying both fields (behavioural, through the real decoder), and no
/// file in the view target reads either of them (a scan of `app/Sources/OhYesMLX`).
final class FableS3F9Tests: XCTestCase {

    // MARK: - the view target's sources

    private var viewTarget: URL {
        // <checkout>/app/Tests/OhYesMLXKitTests/FableS3F9Tests.swift -> <checkout>/app/Sources/OhYesMLX
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/OhYesMLX")
    }

    private func viewSources() throws -> [(path: String, text: String)] {
        let root = viewTarget.standardizedFileURL
        guard FileManager.default.fileExists(atPath: root.path) else {
            XCTFail("the view target is not where this test looks for it: \(root.path)")
            return []
        }
        guard let walker = FileManager.default.enumerator(
            at: root, includingPropertiesForKeys: nil
        ) else {
            XCTFail("cannot enumerate \(root.path)")
            return []
        }
        var found: [(path: String, text: String)] = []
        for case let url as URL in walker where url.pathExtension == "swift" {
            found.append((url.lastPathComponent, try String(contentsOf: url, encoding: .utf8)))
        }
        XCTAssertFalse(found.isEmpty, "no Swift files under \(root.path)")
        XCTAssertTrue(
            found.contains { $0.path == "ResultsView.swift" },
            "the scan did not reach ResultsView.swift, so its result means nothing"
        )
        return found
    }

    /// Whole-word matches only: a bare `contains("load")` would count "Download" and
    /// "reload" and pass this test without anything reading `summary.load`.
    private func codeLines(matching word: String, in text: String) -> [String] {
        let pattern = "(?<![A-Za-z_])\(word)(?![A-Za-z_])"
        guard let regex = try? NSRegularExpression(pattern: pattern) else {
            XCTFail("bad predicate \(pattern)")
            return []
        }
        return text.split(separator: "\n", omittingEmptySubsequences: false)
            .map(String.init)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .filter { line in
                regex.firstMatch(
                    in: line, range: NSRange(line.startIndex..., in: line)
                ) != nil
            }
    }

    // MARK: - the fields the backend really sends

    /// The fixture is the backend's own finished summary: stage B was measured while the Mac
    /// was busy, and the client decodes the label. Nothing here is wrong until it is dropped.
    func testTheFinishedSummaryCarriesItsContentionLabel() throws {
        let summary = try Fixtures.decode(QuickSummary.self, "quickbench_summary_finished.json")
        XCTAssertEqual(summary.load.stageB?.label, "this Mac was busy")
        XCTAssertEqual(summary.load.stageB?.before ?? 0, 1.51, accuracy: 1e-9)
        XCTAssertEqual(summary.load.stageB?.after ?? 0, 1.66, accuracy: 1e-9)
    }

    /// Two engines inside `TIE` are one reading on this host, so the backend names both. It
    /// still offers a `best`: `_best` reads only the decode rate (`quickbench.py:398-428`).
    /// So a tie leaves the client with a tie list *and* a single recommendation to qualify.
    func testATiedStageCarriesBothNamesAndStillABest() throws {
        var object = try XCTUnwrap(
            try JSONSerialization.jsonObject(
                with: try Fixtures.data("quickbench_summary_finished.json")
            ) as? [String: Any]
        )
        var stageA = try XCTUnwrap(object["stage_a"] as? [String: Any])
        stageA["tie"] = ["omlx", "mlxlm"]
        object["stage_a"] = stageA

        let data = try JSONSerialization.data(withJSONObject: object)
        let summary = try JSONDecoder().decode(QuickSummary.self, from: data)

        XCTAssertEqual(summary.stageA.tie, ["omlx", "mlxlm"])
        XCTAssertEqual(summary.stageA.winner, "omlx")
        XCTAssertNotNil(summary.best, "a tie still yields a best, so the best card needs the qualifier")
    }

    // MARK: - what the Results screen does with them

    /// The requirement: a stage the harness labelled contended is shown as contended. The
    /// finding says the label is decoded and rendered nowhere; this asserts the view reads
    /// it. On the current code it fails — `ResultsView.swift` has no `load` outside a comment.
    func testTheResultsScreenShowsTheContentionLabel() throws {
        let sources = try viewSources()
        let readers = sources.filter { file in
            ["load", "loads", "busy", "QuickLoad", "QuickLoads"].contains { word in
                !codeLines(matching: word, in: file.text).isEmpty
            }
        }
        XCTAssertFalse(
            readers.isEmpty,
            "no view reads the summary's contention label; a stage measured under load is "
                + "shown as a clean result"
        )
    }

    /// The requirement: when two engines are inside the noise floor, neither is "fastest".
    /// On the current code `ResultsView.swift:143` badges by `cell.engine == winner` alone
    /// and the file never mentions `tie`, so this fails.
    func testATiedStageIsNotBadgedAsOneFastestEngine() throws {
        let sources = try viewSources()
        let readers = sources.filter { !codeLines(matching: "tie", in: $0.text).isEmpty }
        XCTAssertFalse(
            readers.isEmpty,
            "no view reads stage_a.tie; one engine inside the tie band is badged "
                + "\"fastest in stage\" under \"Best on your Mac\""
        )
    }
}
