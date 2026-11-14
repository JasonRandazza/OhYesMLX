import Darwin
import XCTest
@testable import OhYesMLXKit

final class LiveBackendTests: XCTestCase {
    func testLiveRoundTrip() async throws {
        guard let python = ProcessInfo.processInfo.environment["OYMLX_DEV_PYTHON"],
              !python.isEmpty
        else {
            throw XCTSkip("OYMLX_DEV_PYTHON is not set; skipping the live backend round trip")
        }

        var environment = ProcessInfo.processInfo.environment
        environment["OYMLX_DEV_PYTHON"] = python
        let appSupport = FileManager.default.temporaryDirectory
            .appendingPathComponent("ohyesmlx-live-\(UUID().uuidString)")
        defer {
            try? FileManager.default.removeItem(at: appSupport)
        }

        let launcher = BackendLauncher(
            environment: environment,
            appSupportDirectory: appSupport,
            launchTimeout: 30
        )
        let outcome = await launcher.start()
        guard case .running(let running) = outcome else {
            XCTFail("the backend did not start: \(outcome)")
            return
        }
        defer { running.forceKill() }

        let backend = HTTPBackend(port: running.endpoint.port, token: running.endpoint.token)
        let hardware = try await backend.hardware()
        let engines = try await backend.engines()
        let recommendations = try await backend.recommendations()

        XCTAssertFalse(hardware.chip.isEmpty)
        XCTAssertGreaterThan(hardware.ramBytes, 0)
        XCTAssertFalse(engines.isEmpty)
        XCTAssertTrue(engines.contains { $0.name == "mlxlm" })
        XCTAssertFalse(recommendations.picks.isEmpty || recommendations.unsupportedReason != nil)

        let quit = await running.quit(jobRunning: false)
        XCTAssertEqual(quit, .exited)

        let deadline = Date().addingTimeInterval(2)
        while running.exitStatus == nil, Date() < deadline {
            try await Task.sleep(for: .milliseconds(20))
        }
        XCTAssertEqual(running.exitStatus, 0)
        XCTAssertTrue(portIsFree(running.endpoint.port), "port \(running.endpoint.port) is still bound")
    }

    private func portIsFree(_ port: Int) -> Bool {
        let descriptor = socket(AF_INET, SOCK_STREAM, 0)
        guard descriptor >= 0 else { return false }
        defer { close(descriptor) }

        var reuse: Int32 = 1
        setsockopt(
            descriptor,
            SOL_SOCKET,
            SO_REUSEADDR,
            &reuse,
            socklen_t(MemoryLayout<Int32>.size)
        )

        var address = sockaddr_in()
        address.sin_family = sa_family_t(AF_INET)
        address.sin_port = in_port_t(UInt16(port).bigEndian)
        address.sin_addr.s_addr = inet_addr("127.0.0.1")
        let result = withUnsafePointer(to: &address) { pointer in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { rebound in
                Darwin.bind(descriptor, rebound, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        return result == 0
    }
}
