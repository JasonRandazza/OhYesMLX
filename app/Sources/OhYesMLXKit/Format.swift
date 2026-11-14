import Foundation

/// The one place a byte count, a rate or a duration becomes text.
public enum Format {
    private static let nbsp = "\u{00A0}"

    /// Memory, in binary gigabytes labelled GB the way macOS labels it: 68719476736 -> "64 GB".
    public static func memory(_ bytes: Int64) -> String {
        trimmed(Double(bytes) / 1_073_741_824, places: 1) + nbsp + "GB"
    }

    /// Disk and download sizes, decimal: 43377606656 -> "43.4 GB", 351386061 -> "351 MB".
    public static func size(_ bytes: Int64) -> String {
        if bytes >= 1_000_000_000 {
            return trimmed(Double(bytes) / 1_000_000_000, places: 1) + nbsp + "GB"
        }
        let megabytes = Int64((Double(bytes) / 1_000_000).rounded())
        return String(megabytes) + nbsp + "MB"
    }

    /// "62.1 tok/s".
    public static func rate(_ tokensPerSecond: Double) -> String {
        fixed(tokensPerSecond, places: 1) + nbsp + "tok/s"
    }

    /// "0.21 s" under a minute, "about 11 min" above it.
    public static func duration(_ seconds: Double) -> String {
        if seconds < 60 {
            return trimmed(seconds, places: 2) + nbsp + "s"
        }
        return "about " + String(Int((seconds / 60).rounded())) + nbsp + "min"
    }

    private static func fixed(_ value: Double, places: Int) -> String {
        String(format: "%.\(places)f", value)
    }

    private static func trimmed(_ value: Double, places: Int) -> String {
        var text = fixed(value, places: places)
        guard text.contains(".") else { return text }
        while text.hasSuffix("0") {
            text.removeLast()
        }
        if text.hasSuffix(".") {
            text.removeLast()
        }
        return text
    }
}
