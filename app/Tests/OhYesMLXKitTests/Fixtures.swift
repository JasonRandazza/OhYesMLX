import Foundation
@testable import OhYesMLXKit

enum Fixtures {
    static func data(_ name: String) throws -> Data {
        if let url = Bundle.module.url(forResource: name, withExtension: nil, subdirectory: "Fixtures") {
            return try Data(contentsOf: url)
        }
        if let url = Bundle.module.url(forResource: name, withExtension: nil) {
            return try Data(contentsOf: url)
        }
        throw NSError(
            domain: "Fixtures",
            code: 1,
            userInfo: [NSLocalizedDescriptionKey: "missing fixture \(name)"]
        )
    }

    static func decode<T: Decodable>(_ type: T.Type, _ name: String) throws -> T {
        try JSONDecoder().decode(type, from: data(name))
    }

    static func text(_ name: String) throws -> String {
        try String(decoding: data(name), as: UTF8.self)
    }

    static var hardware: Hardware {
        get throws { try decode(Hardware.self, "hardware.json") }
    }

    static var engines: [EngineStatus] {
        get throws { try decode([EngineStatus].self, "engines.json") }
    }

    static var recommendations: Recommendations {
        get throws { try decode(Recommendations.self, "recommendations.json") }
    }

    static var quickPlan: QuickPlan {
        get throws { try decode(QuickPlan.self, "quickbench_plan.json") }
    }
}

func makeEventJSON(
    seq: Int,
    type: String = "progress",
    message: String = "step",
    fraction: Double? = nil,
    payload: String = "null"
) -> String {
    let fractionText = fraction.map { String($0) } ?? "null"
    return "{\"seq\": \(seq), \"type\": \"\(type)\", \"message\": \"\(message)\", "
        + "\"fraction\": \(fractionText), \"payload\": \(payload)}"
}
