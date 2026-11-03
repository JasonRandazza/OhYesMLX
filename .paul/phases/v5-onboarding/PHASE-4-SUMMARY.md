---
description: "v5.0 Phase 4 reconciled: guarded localhost API, jobs with SSE, quickbench; reviewed and UAT-verified"
type: Summary
about: "OhYesMLX"
---

# Phase 4 Summary (UNIFY, 2026-11-03)

## Delivered

| Plan | Delivered | Commit |
|---|---|---|
| 04-01 | `ohyesmlx app`: 127.0.0.1 server, per-launch token, Host/Origin/token guard, GET `/hardware` `/engines` `/recommendations` | `1c157b0` |
| 04-01b | `gpu_cores` from `ioreg` | `06fd4fb` |
| 04-02b | `Pick.downloaded`, tested-release install URLs, per-byte download progress | `ddfe220` |
| 04-02 | Jobs: install/download/evict, SSE stream, cancel, one at a time, shutdown wait | `05fc081` |
| 04-03a | catalog `base`/`siblings`, `quick: true` header pin, Python Osaurus pin/restore/recover | `339d7c7` |
| 04-03b | `quickbench` module and subcommand, job kind, `GET /quickbench/plan`, `measured_here` | `ea528fc` |
| 04-03c | Pin backs up and restores the drift guard's baseline; quickbench pins against it | `ad73b76` |
| review | 9 verified Standards + Spec findings fixed | `6c84f5c` |

Tests 959 -> 1164. Live checks by the coordinator: scratch download/evict jobs over SSE; quickbench twice on
Qwen3.5-2B-4bit (2026-11-03: all five engines PASS incl. Osaurus 131.3 tok/s, oQ4 on oMLX best at 178.6, Osaurus
configs and baseline byte-exact under `cmp`). UAT by Jason 2026-11-03: 8 of 8 pass, one known minor issue
(`04-UAT.md`).

## Findings

- A plan defect shows only live: quickbench pinned against a baseline the guard does not read (04-03c).
- Every refusal must end its stream: `fetch` and `engines` refusals sent `error` without `done`, which held the
  one job slot forever. Server tests used fakes that always sent `done`; a real-module job test now exists.
- The hero-model safetensors in the HF cache are the pinned tensors, reordered (proven by sha256 without a
  download); published tables stand. `fetch.downloaded` still reads them as absent (UAT-001).

## Deviations

- Coordinator fixes outside worker scopes: sibling `cache_dir` (04-03b), `docs/interfaces.md` refresh (04-03c),
  restore error text kept, stale Osaurus path in `scripts/run_canary.sh` and `docs/runtimes/lab-copies.md` (review).
- Not handled, by choice: a hand-made backup holding both `baseline.json` and `baseline.absent` raises.
- Carried to Phase 4.5: clean-account smoke, a pip step outliving shutdown, per-job stream-reader cap, the Osaurus
  app rewriting its config mid-run, fetch's post-transfer snapshot-conflict check, the baseline's location in a
  packaged app, the Swift client never logging the token, UAT-001.
