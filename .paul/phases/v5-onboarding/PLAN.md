---
description: "v5.0 Onboarding App — milestone plan, seams and ticket slices (DRAFT, awaiting seam confirmation)"
type: Plan
about: "OhYesMLX"
---

# v5.0 — Onboarding App

Status: APPROVED 2026-10-29 (seams S1–S8 and decisions D1–D8 confirmed by Jason). Decisions by Jason, this date: SwiftUI shell over a Python backend; guided install
with consent; curated catalog first (Hugging Face live later); new milestone, ahead of and pausing MTPLX (v4.0).

## Decisions (grilling round 1, all accepted 2026-10-29)

- D1 Apple Silicon only; Intel or <8 GB RAM gets a plain "unsupported" screen, no recommendations.
- D2 Engines in v5.0: Osaurus, oMLX, OptiQ, mlx-lm, vMLX. MTPLX joins the registry when its branch lands. GUI-app engines (Osaurus, oMLX, vMLX): installer opens the official download and verifies after, no scripting.
- D3 Quickbench is two stages, one axis each: A = engines with format fixed; B = formats with the winning engine fixed. Each result carries its can't-claim caveat.
- D4 ~10 min budget; shows time and download size first; starts only on click; one model ≤3B at a time, evict before the next fetch.
- D5 "Fits" is computed from the user's RAM/disk and labelled estimated; speed shown only from runs on the user's Mac ("measured on your Mac"). M2 Max numbers never predict other machines.
- D6 Standalone Python (python-build-standalone) bundled in the .app with the ohyesmlx package.
- D7 First release = unsigned GitHub Releases .app zip (right-click, Open); notarization waits on an Apple Developer account decision. Xcode build is the developer path; the CLI stays.
- D8 Local only: no telemetry, no upload. Results in ~/Library/Application Support/OhYesMLX/; "Export results" writes a JSON file. Models in the HF cache by default; the user may pick another volume.
- D9 (2026-11-02) Quickbench runs lighter cells than the harness: fixed small warmup, 5 measured requests, 10 s cooldown, coherence gate kept, about 1-1.5 min per cell so 4-6 cells fit D4's ~10 minutes. Results are labelled "quick" and never join the published tables.
- D10 (2026-11-02) The localhost API is guarded by a per-launch bearer token printed on startup, a Host check (127.0.0.1/localhost:<port> only) and refusal of any request carrying an Origin header. Stage B finds a model's other formats through a catalog `base` field.

## Purpose

OhYesMLX stays a measurement tool, and gains a front door. A Mac owner with no terminal habit opens an app,
is told in plain language what their machine is (chip, unified memory, free disk), meets the serving engines,
installs the ones they choose, is handed models that fit, and can run a short benchmark to find which
engine and quantization is fastest on *their* hardware. The harness remains the single source of
measurement truth; the app is a client of it.

## Architecture

```
SwiftUI app (app/)  ──HTTP JSON on 127.0.0.1──>  ohyesmlx/server.py
                                                   ├─ hardware.py   scan the Mac
                                                   ├─ engines.py    registry, detect, install plans, installer
                                                   ├─ catalog.py    config/catalog.json (curated models)
                                                   ├─ recommend.py  fit rules -> ranked picks with reasons
                                                   ├─ fetch.py      download/evict models under a disk budget
                                                   └─ existing harness (measure.py, runtimes.py) for the quick benchmark
```

Rules carried over: stdlib only; one definition of everything (engine names/ports/versions already live in
`runtimes.py` — `engines.py` asks it, never copies); the server holds no logic the modules lack; every GUI
action is reachable as a tested function first. Disk is scarce on the owner's machine: the downloader is
a first-class concern, not a detail (models are fetched one at a time and evicted on request).

## Seams (to confirm before any test is written)

| # | Seam (public interface) | Catches | Misses |
|---|---|---|---|
| S1 | `hardware.scan(run=...) -> Hardware` (injected command runner; fixtures of real `sysctl`/`df` output for M1…M4, Pro/Max/Ultra) | chip/RAM/disk parsing, unknown-chip fallback, tiering | the real machine's quirks (checked by one manual smoke) |
| S2 | `engines.detect_all(env) -> list[EngineStatus]`, `engines.install_plan(name) -> Plan` (pure data) | what is installed, version, what an install would do/size/source | actually running installers |
| S3 | `engines.install(plan, confirm, run)` with fake runner | consent gate (no step before `confirm`), order, failure rollback/report, progress events | real brew/pip/dmg behaviour (manual smoke per engine) |
| S4 | `recommend.pick(hw, catalog, installed, free_disk) -> list[Pick]` | fit-with-headroom math, ≤ disk budget, engine/format compatibility, reason text | model quality (not scored; out of scope) |
| S5 | `fetch.plan(model, hw)` / `fetch.run(plan, runner)` | disk guard, one-at-a-time, eviction choice, resume | real HF network |
| S6 | HTTP: `GET /hardware /engines /recommendations`, `POST /jobs`, `GET /jobs/{id}/events` against a started server on an ephemeral port | the contract the Swift app depends on, job lifecycle, error shapes | UI rendering |
| S7 | Swift: view-model tests with a stub client (XCTest); one UI smoke | screen flow, state mapping, error display | pixel design |
| S8 | `ohyesmlx quickbench` -> existing results.jsonl | small fixed cell set runs through the harness and joins into a "best for you" summary | thermal/contention (harness rules still apply) |

No test is written at a seam Jason has not confirmed.

## Tickets

Vertical slices; each is one red→green tracer bullet at one seam, dispatched to `cc-agent implement`
(DeepSeek v4.1 Flash, max thinking, `CC_AGENT_MAX_TURNS=300`) with the preamble. The coordinator verifies
diff + green suite before closing. `docs/interfaces.md` is pinned (T0.2) before any fan-out.

### Phase 0 — Contract (coordinator, no workers)
- T0.1 Amend PROJECT.md (target users, scope), ROADMAP.md (v5.0 above v4.0, MTPLX paused), STATE.md, AGENTS.md (approve the modules above in one place).
- T0.2 Pin `docs/interfaces.md` additions: `Hardware`, `EngineStatus`, `Plan`, `Pick`, job/event JSON shapes.
- T0.3 Commit the pending MTPLX work first so v4.0 is not mixed into v5.0.

### Phase 1 — Know the Mac (S1)
- T1.1 `hardware.scan`: chip name, generation, tier, cores, RAM bytes, macOS version. First test: M2 Max/64 GB fixture.
- T1.2 Disk: free bytes on the model volume (+ external volumes list). The low-disk decision lives in the installer (02-03 AC-11), not on `Hardware`.
- T1.3 `Hardware.model_budget_bytes`: usable RAM for weights after OS/KV headroom (the one place that constant lives).

### Phase 2 — Engines (S2, S3)
- T2.1 Registry + `detect_all` for the six engines, reusing `runtimes.py` names/ports/version probes.
- T2.2 `install_plan` per engine (source, size estimate, steps, needs-sudo flag). Parallelizable by engine after T2.1.
- T2.3 `install` executor: consent gate, progress events, failure report. Fake runner only.
- T2.4 Per-engine real-install smoke notes in `docs/runtimes/` (manual, Jason's machine).

### Phase 2.5 — Version stability [INSERTED 2026-10-29, Jason]
Why: every engine upgrades under us (OptiQ went 0.5.13 to 0.7.8 on 2026-10-29) and each upgrade can void published tables. Answer, not a hope:
frozen lab copies, a canary that says whether a bump moved the numbers, and one tested-versions manifest. After 02-01 (needs `engines.py`), before Phase 4.
- T2.5.1 `ohyesmlx/engines-tested.json`: the ONE tested-versions manifest (engine, version, verified date, optional `lab_path`). `engines.TESTED_VERSIONS` becomes a loader of it; nothing else restates a version.
- T2.5.2 Lab copies: pip engines get a version-pinned venv per tested version; the harness resolves the engine from the manifest's `lab_path` when set. App engines: archived tested DMG + lab install outside /Applications with auto-update off. Doc `docs/runtimes/lab-copies.md`; a `wizard` script for the manual steps only Jason can do.
- T2.5.3 `ohyesmlx canary`: fixed ~6-cell set (via `--cells`, no second selector), compared to a stored baseline for the pinned version within the noise floor (5%). Verdict per engine: "no effect on our tables" or "moved N%: re-run <grids>". A measured run: confirm with Jason before launch, machine quiet.
- T2.5.4 Version-bump checklist in `docs/runtimes/lab-copies.md`: how a bump is recorded (manifest + STATE row + canary result).
- T2.5.5 (found 2026-10-30) Freeze each pip lab venv's full dependency set (a `pip freeze` constraints file recorded beside the venv) so a pinned engine is a pinned build, not just a pinned package.
Surfaces approved by Jason 2026-10-29: `ohyesmlx/engines-tested.json`, subcommand `canary`.

### Phase 3 — Models (S4, S5)
- T3.1 `config/catalog.json` schema + loader; seed ≤3B models already measured here (size, formats, engines, measured peak_mb within-runtime).
- T3.2 `recommend.pick`: fit + headroom + disk, ranked. First test: 16 GB M1 gets only models that fit; 64 GB M2 Max gets a wider list.
- T3.3 Reason strings ("fits with 6 GB spare; fastest format on oMLX per our runs").
- T3.4 `fetch.plan/run`: download under a budget, evict-before-fetch, one at a time, `scripts/` repo-id record per AGENTS.md download rule.
- T3.5 (later, deferred) Hugging Face live source behind the catalog interface.

### Phase 4 — Server (S6, S8)
- T4.1 `ohyesmlx app` subcommand + server skeleton, `GET /hardware`, `/engines`.
- T4.2 `GET /recommendations`.
- T4.3 Jobs: install and download as jobs with an event stream.
- T4.4 `quickbench`: fixed small cell set (one model, installed engines, `--cells` is still the only selector) -> summary. Lighter cells per D9; stage B via the catalog `base` field (D10).

Plans (2026-11-02): 04-01 server + guard + GET endpoints (T4.1, T4.2); 04-02 jobs + SSE for install and download (T4.3); 04-03 quickbench (T4.4). Each gets `/paul:audit` before APPLY.
Found at the 04-01 checkpoint (2026-11-02), carried here:
- 04-01b (quick fix, after 04-01 closes): `Hardware.gpu_cores` is hardcoded `None` in `hardware.scan`; read `gpu-core-count` from `ioreg -rc AGXAccelerator -d1` (30 on this M2 Max), with captured `ioreg` text as the fixture and `None` only when the key is absent.
- 04-02: each `Pick` gains `downloaded: bool`, answered by `fetch`'s own present-in-cache check (not a second copy); a downloaded pick's reason says it is already on this Mac and names no download size. Pinned-shape change, recorded in docs/interfaces.md.
- 04-02 or 4.5: guided-download plans open `releases/latest` for Osaurus and vMLX, so a new user installs whatever shipped last, not the tested build. Point `source_url` at the tested version's release (or say plainly in the plan that the page is newer than tested).

### Phase 4.5 — Security hardening [INSERTED 2026-11-02, Jason]
Why: v5.0 is the first time OYMLX runs installers, downloads and a network-reachable server on a non-technical user's Mac. After Phase 4, before the SwiftUI app ships, one phase reviews the whole backend as an attack surface: the localhost API (guard, job args, body limits), installer subprocesses and their environment, downloader URL/path handling and the HF cache, files written under Application Support (permissions, symlinks), the ledger and logs, and what a bundled Python (D6) exposes. Output: a threat model, findings fixed with tests, and a checklist the Phase 5 packaging must keep. Plan written after Phase 4 lands. Carried in from 04-01 (deferred, Jason 2026-11-02): a clean-account smoke, because every engine is installed on this Mac so `GET /engines` has never listed a real install plan for a genuinely absent engine (04-01 checked the composition with every engine forced "not installed"). It needs no second login: a throwaway standard user (`sudo sysadminctl -addUser oymlxtest`) can be driven from this account with `sudo -u oymlxtest -H ohyesmlx app`, then deleted. Do it when Jason chooses; also the Phase 5 install smoke.
Plans (Jason, 2026-11-03): `045-01` threat model and verified findings (no code), `045-02` fixes (planned after 01 unifies), `045-03` clean-account smoke. UAT-001 accepted, documented only. **Complete 2026-11-13** (`PHASE-4.5-SUMMARY.md`).

### Phase 5 — SwiftUI app (S7)
- T5.1 Xcode package, backend launcher (spawn + health wait + quit), `APIClient` with stub.
- T5.2 Welcome + Your Mac screen.
- T5.3 Engines screen (detect, explain, consented install with progress).
- T5.4 Models screen (recommendations, disk meter, download).
- T5.5 Benchmark + Results screen.
- T5.6 Packaging: signed .app, first-run, Gatekeeper notes.

## Process gates (agreed 2026-10-29)

PAUL runs the per-phase loop; this file is the overview. Before a phase starts: `/paul:plan` writes that phase's
PLAN.md (tickets + acceptance criteria). `/paul:research-phase` before Phase 2 (engine install facts, from primary
sources). `/paul:audit` on the Phase 2 and Phase 4 plans. `prototype` before Phase 5 (screen flows). After each
phase: `/paul:unify`, `code-review`, and `/paul:verify` for the manual smoke steps. Phase 1 needs none of this;
T1.1-T1.3 are fully specified by their orders.

## Order and parallelism

P0 → P1 → (P2 ∥ P3) → P4 → P5. Within a phase, tickets that touch different files fan out; the
collateral-deletion guard misfires under fan-out, so verify against `git`. T5.x can start against the stub
client as soon as T0.2 pins the JSON shapes.

## Risks

- Installing six third-party engines is the least deterministic part; mitigated by consent, plans-as-data and manual smoke.
- Notarization and distribution of the .app needs an Apple Developer account decision (T5.6).
- Small-model-only catalog (≤3B, disk) means recommendations are honest only for that range; the catalog says so.
- Swift adds a second toolchain; the dependency rule is "name what it replaces" — SwiftUI replaces nothing in Python and is a client only.
