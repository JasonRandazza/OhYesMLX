import Foundation
import XCTest
@testable import OhYesMLXKit

/// F17: `planBenchmark` clears `quickPlan` only for a `BackendError`. Any other failure (a
/// timeout, a decode error) returns false and leaves the previous model's plan in place, which
/// `startBenchmark` then runs from `quickPlan.repo`.
private final class PlanFailsForOneRepoBackend: Backend, @unchecked Sendable {
    let inner: StubBackend
    let plan: QuickPlan
    let failingRepo: String

    init(inner: StubBackend, plan: QuickPlan, failingRepo: String) {
        self.inner = inner
        self.plan = plan
        self.failingRepo = failingRepo
    }

    func hardware() async throws -> Hardware { try await inner.hardware() }

    func engines() async throws -> [EngineStatus] { try await inner.engines() }

    func recommendations() async throws -> Recommendations { try await inner.recommendations() }

    func quickbenchPlan(repo: String) async throws -> QuickPlan {
        if repo == failingRepo { throw URLError(.timedOut) }
        return plan
    }

    func startJob(kind: JobKind, args: JobArgs) async throws -> String {
        try await inner.startJob(kind: kind, args: args)
    }

    func cancel(jobID: String, now: Bool) async throws {
        try await inner.cancel(jobID: jobID, now: now)
    }

    func events(jobID: String, after: Int?) -> AsyncThrowingStream<JobEvent, Error> {
        inner.events(jobID: jobID, after: after)
    }
}

@MainActor
final class FableS3F17Tests: XCTestCase {
    func testPlanFailureClearsThePreviousModelsPlan() async throws {
        let suiteName = "ohyesmlx-fable-s3-f17-\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        addTeardownBlock {
            defaults.removePersistentDomain(forName: suiteName)
        }
        let plan = try Fixtures.quickPlan
        let inner = StubBackend(
            hardware: try Fixtures.hardware,
            engines: try Fixtures.engines,
            recommendations: try Fixtures.recommendations
        )
        let backend = PlanFailsForOneRepoBackend(
            inner: inner,
            plan: plan,
            failingRepo: "mlx-community/Elsewhere-4bit"
        )
        let model = AppModel(backend: backend, defaults: defaults)

        let first = await model.planBenchmark(repo: plan.repo)
        XCTAssertTrue(first)
        XCTAssertEqual(model.quickPlan?.repo, plan.repo)

        // The picker moved to another model and its plan request timed out.
        let second = await model.planBenchmark(repo: backend.failingRepo)
        XCTAssertFalse(second)

        XCTAssertNil(
            model.quickPlan,
            "the plan for \(plan.repo) is still the one on screen under the new pick"
        )
        XCTAssertNotNil(
            model.benchmarkRefusal,
            "the failed plan for the new pick was reported nowhere"
        )
    }
}
