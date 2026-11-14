// swift-tools-version:6.0
import PackageDescription

let package = Package(
    name: "OhYesMLX",
    platforms: [.macOS(.v14)],
    products: [
        .library(name: "OhYesMLXKit", targets: ["OhYesMLXKit"]),
        .executable(name: "OhYesMLX", targets: ["OhYesMLX"]),
    ],
    targets: [
        .target(name: "OhYesMLXKit"),
        .executableTarget(name: "OhYesMLX", dependencies: ["OhYesMLXKit"]),
        .testTarget(
            name: "OhYesMLXKitTests",
            dependencies: ["OhYesMLXKit"],
            resources: [.process("Fixtures")]
        ),
    ]
)
