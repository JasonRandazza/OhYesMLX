import XCTest
@testable import OhYesMLXKit

final class FormatTests: XCTestCase {
    private let nbsp = "\u{00A0}"

    func testMemoryUsesBinaryGBLabelledAsMacOSDoes() {
        XCTAssertEqual(Format.memory(68_719_476_736), "64" + nbsp + "GB")
        XCTAssertEqual(Format.memory(49_392_123_904), "46" + nbsp + "GB")
        XCTAssertEqual(Format.memory(17_179_869_184), "16" + nbsp + "GB")
    }

    func testSizesUseDecimalGBWithOneDecimalAndWholeMegabytes() {
        XCTAssertEqual(Format.size(43_377_606_656), "43.4" + nbsp + "GB")
        XCTAssertEqual(Format.size(351_386_061), "351" + nbsp + "MB")
        XCTAssertEqual(Format.size(900_000_000), "900" + nbsp + "MB")
    }

    func testRatesAndDurations() {
        XCTAssertEqual(Format.rate(62.1), "62.1" + nbsp + "tok/s")
        XCTAssertEqual(Format.duration(0.21), "0.21" + nbsp + "s")
        XCTAssertEqual(Format.duration(660), "about 11" + nbsp + "min")
    }

    func testNumberAndUnitAreJoinedByANonBreakingSpace() {
        XCTAssertEqual(Format.memory(68_719_476_736), "64\u{00A0}GB")
        XCTAssertEqual(Format.size(43_377_606_656), "43.4\u{00A0}GB")
        XCTAssertEqual(Format.size(351_386_061), "351\u{00A0}MB")
        XCTAssertEqual(Format.rate(62.1), "62.1\u{00A0}tok/s")
        XCTAssertEqual(Format.duration(0.21), "0.21\u{00A0}s")
        XCTAssertEqual(Format.duration(660), "about 11\u{00A0}min")
    }
}
