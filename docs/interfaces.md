# Module interfaces

Pinned so modules can be built concurrently without inventing mismatched shapes.
**These signatures are the contract.** If one is wrong, say so in the ticket and stop —
do not quietly change it, because three other modules are being written against it.

All types are plain dataclasses or dicts. Stdlib only.

| Section | File |
| --- | --- |
| ## `ohyesmlx/transport.py` — issue #2 | [`docs/interfaces/measurement-core.md`](interfaces/measurement-core.md) |
| ## `ohyesmlx/runtimes.py` — issue #3 | [`docs/interfaces/measurement-core.md`](interfaces/measurement-core.md) |
| ## `ohyesmlx/sample.py` — issue #4, **merged, do not change** | [`docs/interfaces/measurement-core.md`](interfaces/measurement-core.md) |
| ## `ohyesmlx/measure.py` — issue #5 | [`docs/interfaces/measurement-core.md`](interfaces/measurement-core.md) |
| ## `ohyesmlx/report.py` — issue #6 | [`docs/interfaces/measurement-core.md`](interfaces/measurement-core.md) |
| ## Metric formulas — one definition each, no forks | [`docs/interfaces/measurement-core.md`](interfaces/measurement-core.md) |
| ## Phase 5 — the joined grid | [`docs/interfaces/grid-and-warmup.md`](interfaces/grid-and-warmup.md) |
| ## Phase 5 plan 05-02 — warmup is measured, not pinned | [`docs/interfaces/grid-and-warmup.md`](interfaces/grid-and-warmup.md) |
| ## Phase 6 — a sweep is a pin, not an axis | [`docs/interfaces/sweep-pins.md`](interfaces/sweep-pins.md) |
| ## Phase 6 plan 06-01b — the concurrency pin | [`docs/interfaces/sweep-pins.md`](interfaces/sweep-pins.md) |
| ## Phase 6 plan 06-01c — the prompt-length pin | [`docs/interfaces/sweep-pins.md`](interfaces/sweep-pins.md) |
| ## Phase 6 — the lost visit and the short measured window (found by 06-01c's sweep) | [`docs/interfaces/sweep-pins.md`](interfaces/sweep-pins.md) |
| ## Phase 6 plan 06-02 — the cache-state pin | [`docs/interfaces/sweep-pins.md`](interfaces/sweep-pins.md) |
| ## Phase 4 study 03-05 — the KV-quantization pin | [`docs/interfaces/study-pins.md`](interfaces/study-pins.md) |
| ## Phase 4 studies 03-06, 03-03 — the MTP-depth and expert-streaming pins | [`docs/interfaces/study-pins.md`](interfaces/study-pins.md) |
| ## Phase 4 study 03-04 — multi-turn as fixed workloads | [`docs/interfaces/study-pins.md`](interfaces/study-pins.md) |
| ## v5.0 — Onboarding shapes (pinned 2026-10-29, T0.2) | [`docs/interfaces/v5-onboarding.md`](interfaces/v5-onboarding.md) |
| ## v5.0 plan 04-03a — the catalog `base`, the `quick` pin, and one Osaurus pin | [`docs/interfaces/v5-quickbench.md`](interfaces/v5-quickbench.md) |
| ## v5.0 plan 04-03b — quickbench, and the lab path an install writes | [`docs/interfaces/v5-quickbench.md`](interfaces/v5-quickbench.md) |
| ## v5.0 plan 045-02a — an interrupted app is recovered at the next launch | [`docs/interfaces/v5-hardening.md`](interfaces/v5-hardening.md) |
| ## v5.0 plan 045-02b — hash-pinned installs and a validated lab path | [`docs/interfaces/v5-hardening.md`](interfaces/v5-hardening.md) |
| ## Phase 5 (v5.0) — the app: launcher, client, app model, and "Stop now" | [`docs/interfaces/v5-app.md`](interfaces/v5-app.md) |
