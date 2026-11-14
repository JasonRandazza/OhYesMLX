import XCTest
@testable import OhYesMLXKit

final class SSETests: XCTestCase {
    func testFixtureParsesFourEventsInSeqOrder() throws {
        let text = try Fixtures.text("download_events.sse")
        let parsed = try SSEParser.events(from: text)

        XCTAssertEqual(parsed.events.map(\.seq), [1, 2, 3, 4])
        XCTAssertEqual(parsed.events.map(\.type), [.progress, .progress, .error, .done])
        XCTAssertEqual(parsed.lastEventID, "4")

        let first = parsed.events[0]
        XCTAssertEqual(first.message, "downloading mlx-community/Qwen3-0.6B-4bit")
        XCTAssertEqual(try XCTUnwrap(first.fraction), 0.0, accuracy: 1e-12)

        let second = parsed.events[1]
        XCTAssertEqual(try XCTUnwrap(second.fraction), 0.42, accuracy: 1e-12)
        XCTAssertEqual(second.payload?["bytes_done"]?.intValue, 147_582_145)
        XCTAssertEqual(second.payload?["bytes_total"]?.intValue, 351_386_061)

        let third = parsed.events[2]
        XCTAssertEqual(third.payload?["code"]?.stringValue, "low_disk")
        XCTAssertEqual(third.payload?["free_bytes"]?.intValue, 100_000_000)
        XCTAssertEqual(third.payload?["needed_bytes"]?.intValue, 421_663_274)
        XCTAssertNil(third.fraction)

        XCTAssertEqual(parsed.events[3].message, "download refused")
    }

    func testKeepaliveCommentIsIgnored() {
        var parser = SSEParser()
        XCTAssertNil(parser.consume(line: ": keepalive"))
        XCTAssertNil(parser.consume(line: ""))
        XCTAssertNil(parser.lastEventID)
    }

    func testIncrementalParserRecordsTheLastDispatchedID() {
        var parser = SSEParser()
        XCTAssertNil(parser.consume(line: "id: 7"))
        XCTAssertNil(parser.consume(line: "data: {\"seq\": 7}"))
        XCTAssertEqual(parser.consume(line: ""), "{\"seq\": 7}")
        XCTAssertEqual(parser.lastEventID, "7")
        XCTAssertNil(parser.consume(line: "data: no id follows"))
        XCTAssertEqual(parser.consume(line: ""), "no id follows")
        XCTAssertEqual(parser.lastEventID, "7")
    }
}
