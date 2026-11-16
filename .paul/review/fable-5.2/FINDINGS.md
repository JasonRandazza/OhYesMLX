---
description: "Verified, ranked findings of the Fable 5.2 whole-project review of OhYesMLX (2026-11-14/15)"
type: Review
about: "OhYesMLX"
---

# Fable 5.2 review of OYMLX — findings

Written 2026-11-15 by the Opus coordinator. This file is the review's deliverable (PLAN.md §7). It is history, not state:
STATE.md carries one row pointing here, and the fixes go through ordinary PAUL plans.

## 1. Result in one paragraph

Claude Fable 5.2 reviewed all six sections (S1 security and trust boundaries, S2 measurement integrity, S3 the SwiftUI
app, S4 the onboarding backend, S5 runtime lifecycle and host safety, S6 packaging and release), each over a dossier
that MiMo v2.6 Pro (DeepSeek for half of S2) built and the coordinator spot-checked. Fable reported **75 findings**
and covered every dossier hotspot and open question in every section (coverage 30/30, 32/32, 28/28, 28/28, 29/29,
28/28). DeepSeek V4.1 Flash verifiers tried to reproduce each one with the smallest failing test in the
`review/fable-verify` worktree. **73 are CONFIRMED and 2 are REFUTED.** After the coordinator's own checks the ranking
is **4 High, 36 Medium, 35 Low**. Two of the four Highs mean numbers this project publishes are wrong today (S2-F1,
S5-F1). The other two mean a core path does not work as built (S3-F1: the app's live job stream never dispatches an
event) or a published metric includes time that is not load (S5-F2).

## 2. How the verdicts were reached

- **Fable is a claim, not evidence** (AGENTS.md). Every finding got a verifier: one run each for High and Medium,
  and one batched run per section for the Lows, to save Command Code budget.
- Each verifier wrote a test in a new file (`tests/test_fable_s<n>_f<k>.py` or
  `app/Tests/OhYesMLXKitTests/FableS<n>F<k>Tests.swift`) and a report ending in `VERDICT:` and `SEVERITY-CHECK:`.
  The reports are copied into `verify/` here; the tests stay unmerged on `review/fable-verify`.
- **The coordinator re-ran every test itself:** Python `tests/test_fable_*.py` per section (S1+S2 26 failing assertions
  plus 11 passing controls; S4 26 failed / 5 passed; S5 34 / 14; S6 13 / 16 / 1 skipped) and
  `swift test --filter Fable` for S3 (36 failures across 26 tests; S3-F3's tests pass, matching its REFUTED verdict).
  Every confirmed test failed with an assertion that names its defect. `git status` in the worktree showed only new
  test files and reports: no verifier edited code.
- The coordinator read each High against the code, and each REFUTED verdict and each proposed severity change.
  Section 4 records the outcomes.
- Three findings were confirmed without a test, on cited code paths: S3-F13 (a SwiftUI modifier the kit test
  target cannot import), S3-F16 (a pid-reuse window with no seam to inject) and S6-F3 (the check runs only inside
  `check_bundle.sh`, which launches the app).

## 3. The four Highs

**S2-F1: a FAILED quickbench cell sends its tok/s and TTFT to the app, which prints them.** `report._row` computes the
median `decode_tps` whatever the row's status, `quickbench.py:346-350` copies it into the cell, and
`ResultsView.swift:246-247` prints it beside "Failed". The docstring at `quickbench.py:335-337` promises the opposite:
"a skipped or failed one carries … no number at all". This is the 2026-09-15 token-salad rule broken on the newest
surface. Test: `tests/test_fable_s2_f1.py` (two cases: an incoherent cell, and a cell with two lost requests).

**S3-F1: the app's real event stream never dispatches.** `HTTPBackend.swift:38` feeds `URLSession.AsyncBytes.lines`
into the SSE parser, and `.lines` drops empty lines. The parser (`SSE.swift:11-21`) dispatches an event only on a
blank line, so no `progress`, `result`, `error` or `done` event ever arrives over the real transport. A job stays
`.running` and holds the one slot. The UI tests missed it because they inject a fake line stream. The verifier's test
drives a real `URLSession` through a stub `URLProtocol`. Test: `FableS3F1Tests`. The live Phase 5 checks (Stop now, a
real download) would have hit this first.

**S5-F1: the mlx-lm control cell runs from OptiQ's lab venv on this Mac.** `runtimes.lab_env` (`runtimes.py:505-531`)
prefixes every pinned engine's lab bin directory to PATH for **every** engine's start, and `MlxLm.start_command`
starts the bare name `mlx_lm.server`. The coordinator checked this Mac: `lab-paths.json` names
`…/OhYesMLX/engines/optiq-0.5.13/bin`, that directory ships its own `mlx_lm.server` and `python`, and its packages
differ from the dedicated control venv: **mlx 0.32.4 vs 0.32.2 and transformers 5.12.1 vs 5.17.0**, both with
mlx-lm 0.31.3. A row labelled "mlx-lm 0.31.3" therefore measured a different stack than it records, with nothing in
the row able to show it. The verifier proposed Medium. The coordinator keeps it High, because it varies a second
thing on the control and that is the one rule this project exists for. **The fix plan must also establish which
measured runs started while the lab-paths file existed, and mark them.** Test: `tests/test_fable_s5_f1.py`.

**S5-F2: `cold_load_s` includes the version probe and an `lsof` call.** It is published as load time, but it carries a
per-runtime constant (a subprocess probe and a port listing) inside the spawn-to-ready window. The size of that
constant has not been measured. The fix should measure it once on each runtime, because that number decides whether
any published cold-load ordering could have flipped. Test: `tests/test_fable_s5_f2.py`.

## 4. Coordinator rulings on severity and verdicts

- **S5-F1** → High (Fable: High): kept High (verifier proposed Medium): on this Mac the mlx-lm control resolves OptiQ lab bin, mlx 0.32.4 vs the dedicated venv 0.32.2, transformers 5.12.1 vs 5.17.0
- **S4-F1** → Medium (Fable: High): start() itself refuses a busy port and a resident Osaurus app (runtimes.py:2295-2305); what remains is a late, unclear failure
- **S3-F3** → Low (Fable: Medium): backend sends restore_failed error before done (quickbench.py:733-739); residual: stale comment AppModel.swift:677 and misleading Results/Benchmark copy
- **S4-F8** → Low (Fable: Medium): no shipped catalog row has divergent engine lists
- **S5-F14** → Low (Fable: Low): engines.py:501 bounds the non-/Applications case; Fable itself rated it Low on this Mac
- **S6-F7** → Low (Fable: Medium): refuted: ps eww shows env of ad-hoc-signed processes; check_bundle P5-9 holds; residual substring PATH match
Every other verifier severity check agreed with Fable's rating.

## 5. Proposed fix plans

Grouped by the code they touch, so each plan has one owner surface. Each confirmed finding's red test becomes that
fix's first test. Proposed order: **A, B and C first**, because they hold the published-number and safety defects;
then D, E and F; G last, before any release. P5-11 (already known: `Pick.downloaded` is a bool) joins plan E.

| Plan | Surface | Findings | Highs | IDs |
|---|---|---|---|---|
| A | Published numbers and measurement integrity | 14 | 3 | S2-F1, S2-F2, S2-F3, S2-F4, S2-F5, S2-F6, S2-F7, S2-F8, S2-F9, S2-F11, S5-F1, S5-F2, S5-F9, S4-F5 |
| B | App job lifecycle and event stream | 16 | 1 | S3-F1, S3-F2, S3-F3, S3-F4, S3-F5, S3-F6, S3-F7, S3-F8, S3-F11, S3-F12, S3-F13, S3-F14, S3-F15, S3-F17, S1-F5, S1-F6 |
| C | Process identity, locks and the running-engines ledger | 11 | 0 | S1-F1, S1-F2, S3-F16, S4-F13, S5-F3, S5-F4, S5-F5, S5-F10, S5-F11, S5-F13, S5-F14 |
| D | Downloads, disk and eviction | 10 | 0 | S1-F3, S1-F4, S1-F8, S3-F10, S4-F3, S4-F7, S4-F9, S4-F11, S4-F12, S4-F14 |
| E | Onboarding decisions (stage B, recommend, install) | 8 | 0 | S1-F7, S3-F9, S4-F1, S4-F2, S4-F4, S4-F6, S4-F8, S4-F10 |
| F | Osaurus pin and restore | 5 | 0 | S2-F10, S5-F6, S5-F7, S5-F8, S5-F12 |
| G | Packaging and release | 11 | 0 | S6-F1, S6-F2, S6-F3, S6-F4, S6-F5, S6-F6, S6-F7, S6-F8, S6-F9, S6-F10, S6-F11 |
Workers: DeepSeek for most fixes; `kimi-pro` only where a fix needs harder judgment (A's S5-F1 run audit, B's SSE
transport). Each plan goes through audit → APPLY → two-axis review → unify, as usual.

## 6. All findings, ranked

Severity is after the coordinator's checks; "Fable said" is the reviewer's original rating. The full text of each finding
is in `S<n>-findings.md`, and its verification is in `verify/S<n>-F<k>.md`.

| # | ID | Severity (checked) | Fable said | Verdict | Fix plan | Claim | Where |
|---|---|---|---|---|---|---|---|
| 1 | S2-F1 | **High** | High | CONFIRMED | A | A FAILED quickbench cell carries its tok/s and TTFT to the app, which prints them | `ohyesmlx/quickbench.py:346-350` (and docstring 335-337); printed at `app/Sources/OhYesMLX/Screens/ResultsView |
| 2 | S3-F1 | **High** | High | CONFIRMED | B | The real event stream never dispatches: `URLSession.AsyncBytes.lines` drops the blank line the SSE parser waits for | `app/Sources/OhYesMLXKit/HTTPBackend.swift:38`, `:121-142`; `app/Sources/OhYesMLXKit/SSE.swift:11-21` |
| 3 | S5-F1 | **High** | High | CONFIRMED | A | The mlx-lm control cell runs from OptiQ's lab venv on this Mac: lab bins are prefixed to PATH for every engine, and the control's command is a bare `python` | `ohyesmlx/runtimes.py:508-531` (`_engine_env`), `:2421-2424` (`MlxLm.start_command`), `:2463-2464` (`MlxLm.ver |
| 4 | S5-F2 | **High** | High | CONFIRMED | A | `cold_load_s` includes the version probe and an `lsof` call | `ohyesmlx/runtimes.py:2317-2344` (`Runtime.start`), `:2120-2130` (`Runtime.version`) |
| 5 | S1-F1 | **Medium** | Medium | CONFIRMED | C | "Stop now" signals whatever a stale own-pid ledger file names, with no identity check | `ohyesmlx/runtimes.py:1908-1937` (`stop_own_engines`), `:1769-1770` (`_record_running_engine`), `:1890-1891` ( |
| 6 | S2-F2 | **Medium** | Medium | CONFIRMED | A | The SSE loop waits on `select()` of the raw socket while reading through a buffered reader, so buffered chunks are invisible until more bytes arrive | `ohyesmlx/transport.py:264-292` |
| 7 | S2-F3 | **Medium** | Medium | CONFIRMED | A | `runtime_version` is stamped on the first started visit only; a later visit's version is never compared | `ohyesmlx/measure.py:860-865`; consumers `report.py:1624-1660` (guard 4), `report.py:1677-1680` |
| 8 | S2-F4 | **Medium** | Medium | CONFIRMED | A | `peak_mb` is published from a sampler that stopped early; `memory["error"]` is written and never read | `ohyesmlx/sample.py:262-279, 290-302`; `ohyesmlx/report.py:865`; `ohyesmlx/measure.py:880` |
| 9 | S2-F5 | **Medium** | Medium | CONFIRMED | A | The usage reasoning split is trusted without being reconciled against the reasoning text the stream delivered | `ohyesmlx/transport.py:445-466` |
| 10 | S3-F2 | **Medium** | Medium | CONFIRMED | B | Any job's `result` event overwrites the benchmark summary; a later download empties Results and makes Export write the wrong file | `app/Sources/OhYesMLXKit/AppModel.swift:700-702`; `app/Sources/OhYesMLX/Screens/ResultsView.swift:18`, `:45-51 |
| 11 | S3-F4 | **Medium** | Medium | CONFIRMED | B | `cancelJob` writes back a snapshot taken before its await, discarding events and able to pin the slot busy | `app/Sources/OhYesMLXKit/AppModel.swift:517-523` |
| 12 | S3-F5 | **Medium** | Medium | CONFIRMED | B | The app treats a job as over at `error`, but the backend holds the slot and runs rollback until `done` | `app/Sources/OhYesMLXKit/AppModel.swift:689-695`, `:263-270`, `:569`; `ohyesmlx/engines.py:1234-1236`, `:1272- |
| 13 | S3-F6 | **Medium** | Medium | CONFIRMED | B | `start()` does its destructive bookkeeping before the slot is claimed, and a refused start is invisible outside Engines | `app/Sources/OhYesMLXKit/AppModel.swift:610-635`; `app/Sources/OhYesMLX/Screens/EnginesView.swift:17` |
| 14 | S3-F7 | **Medium** | Medium | CONFIRMED | B | The "couldn't start" screen's button relaunches while the backend is alive, and the app quits itself | `app/Sources/OhYesMLX/RootView.swift:22`; `app/Sources/OhYesMLXKit/AppModel.swift:386-402`, `:410-443`; `app/S |
| 15 | S3-F8 | **Medium** | Medium | CONFIRMED | B | The single-instance lock lives in the app, not the backend, so a crashed or force-quit app can be relaunched beside a backend that is still unwinding | `app/Sources/OhYesMLXKit/BackendLauncher.swift:260-269`, `:501-516`; `ohyesmlx/cli.py:1168`, `:1184-1202`; `oh |
| 16 | S3-F9 | **Medium** | Medium | CONFIRMED | E | Results drops the run's own contention flag and tie list, then calls one engine "fastest" and "Best on your Mac" | `app/Sources/OhYesMLX/Screens/ResultsView.swift:89-98`, `:143`, `:240-242`; `app/Sources/OhYesMLXKit/Models.sw |
| 17 | S3-F10 | **Medium** | Medium | CONFIRMED | D | Free-disk figures go stale after every download and removal, and "Free disk after" is client arithmetic over the stale value | `app/Sources/OhYesMLX/Screens/ModelsView.swift:74`, `:286-295`; `app/Sources/OhYesMLX/Screens/BenchmarkView.sw |
| 18 | S4-F1 | **Medium** | High | CONFIRMED | E | Stage B starts the winner engine without re-running the occupied-port / Osaurus-app check | ohyesmlx/quickbench.py:844-901 (no `_skip_reason`), against :431-447 and the stage-A call at :776 |
| 19 | S4-F2 | **Medium** | Medium | CONFIRMED | E | A pip engine can be "installed" for `detect_all`/`install` yet unstartable by the app, with no repair path | ohyesmlx/engines.py:1242-1245 (refusal), :526-563 (detection), :987-996 (`start_new_session=True`), :1294-1295 |
| 20 | S4-F3 | **Medium** | Medium | CONFIRMED | D | The disk guard measures `/`, not the volume the cache is on | ohyesmlx/fetch.py:819, :1146; ohyesmlx/hardware.py:151-152; ohyesmlx/server.py:594-603 (same number feeds `rec |
| 21 | S4-F4 | **Medium** | Medium | CONFIRMED | E | Cancel and "Stop now" are not observed during a stage-B sibling download, and its progress is discarded | ohyesmlx/quickbench.py:864-866 (also :845, :891 — the only probes) |
| 22 | S4-F5 | **Medium** | Medium | CONFIRMED | A | Stage B names a "best" by raw max with no noise band, and that label is persisted as `measured_here` | ohyesmlx/quickbench.py:398-428 (`_best`), against :374-395 (`_winner` applies `TIE`), :836 (reused stage-A row |
| 23 | S4-F6 | **Medium** | Medium | CONFIRMED | E | The memory sentences state numbers the fit rule does not use | ohyesmlx/recommend.py:108-112 (`_reason`), :135-137 (`exclusion_reason`), against :87-93 (`_fit`), :36/:43 (2. |
| 24 | S4-F7 | **Medium** | Medium | CONFIRMED | D | A partly-downloaded row is excluded on its full size, so it cannot be resumed from the screen that owns it | ohyesmlx/recommend.py:139-146; ohyesmlx/server.py:594-603; against ohyesmlx/fetch.py:816-827 (`missing_bytes`) |
| 25 | S4-F9 | **Medium** | Medium | CONFIRMED | D | A failed or refused sibling download leaves its partial on disk, unreported, and hides why it failed | ohyesmlx/quickbench.py:862-890 |
| 26 | S5-F3 | **Medium** | Medium | CONFIRMED | C | "Exactly one model resident" is checked against the engine's own port and the Osaurus app only, and a failed stop is followed by the next start | `ohyesmlx/runtimes.py:2267-2316` (pre-start checks in `Runtime.start`), `:634-648` (`_resident_osaurus_pids`,  |
| 27 | S5-F4 | **Medium** | Medium | CONFIRMED | C | An orphan entry that cannot be verified is dropped without a word and its ledger file deleted, so the engine is never recoverable | `ohyesmlx/runtimes.py:1827-1864` (`_stop_orphan`), `:1867-1905` (`stop_orphaned_engines`), `:1728-1744` (`_pro |
| 28 | S5-F5 | **Medium** | Medium | CONFIRMED | C | An engine is absent from the ledger for its entire load, the longest phase of a start | `ohyesmlx/runtimes.py:2317-2352` (`Runtime.start`), `:588-609` (`_spawn`, `start_new_session=True`) |
| 29 | S5-F6 | **Medium** | Medium | CONFIRMED | F | The shell pin and the app pin keep the "only copy" in two different directories, so a crashed shell run makes the app back up the pinned state as the user's original and report it restored | `scripts/osaurus-pin.sh:18,31-37` (`BACKUP_DIR="$CONFIG_DIR.phase4-orig"`, trap on `INT TERM HUP` only); `ohye |
| 30 | S5-F7 | **Medium** | Medium | CONFIRMED | F | `osaurus_restore_check` returns success and disarms the restoring trap after a FAILED restore, and the abort path prints no verdict at all | `scripts/osaurus-pin.sh:69-84` (`osaurus_restore_check`), `:24-29` (`osaurus_restore`), `:32` (trap) |
| 31 | S5-F8 | **Medium** | Medium | CONFIRMED | F | Every pin re-records the baseline from the live host, so the drift gate compares the host to itself for the whole pinned run, and no snapshot is kept with the results | `ohyesmlx/osaurus_settings.py:285` (`write_baseline` at the end of `pin`); `scripts/osaurus-pin.sh:7,65`; `ohy |
| 32 | S5-F9 | **Medium** | Medium | CONFIRMED | A | Two host settings that change what a cell measures are outside the attestation: the app plist's `disableThinking`, and `concurrency.smeltMode` on any cell without a `stream_experts` pin | `ohyesmlx/osaurus_settings.py:40-80` (`TRACKED_KEYS`: two JSON files, no plist, no `smeltMode`); `ohyesmlx/run |
| 33 | S5-F10 | **Medium** | Medium | CONFIRMED | C | `lsof`, `ps` and stop commands run under the lab environment, so one engine's lab-path defect disables stopping and recovery for every engine | `ohyesmlx/runtimes.py:569-585` (`_run`), `:511-526` (`_engine_env` loop), `:1656-1662` (`_shutdown`), `:1908-1 |
| 34 | S6-F1 | **Medium** | Medium | CONFIRMED | G | The bundle ships timestamp pycs for the stdlib modules the build itself imported, so the "unchecked-hash everywhere" fix for the sealed-bundle writes is incomplete | scripts/build_app.sh:33-34 (no `-B`), :55 (`ditto` of the cache tree), :76-77 (`compileall` without `-f`), :78 |
| 35 | S6-F2 | **Medium** | Medium | CONFIRMED | G | The unpacked interpreter tree is reused without verification, and it has already diverged from the tarball the SBOM names | scripts/fetch_python_standalone.sh:70 (reuse test), :50-68 (the gate covers the tarball only); scripts/build_a |
| 36 | S6-F3 | **Medium** | Medium | CONFIRMED | G | check_bundle's P5-6 signature check cannot fail for the defect it was written for | scripts/check_bundle.sh:143-158 (read-only image), :186-198 (the only request), :252-254 (the verify) |
| 37 | S6-F4 | **Medium** | Medium | CONFIRMED | G | Moving the app after installing engines leaves them "installed" and unstartable, and the recovery gatekeeper.md gives is refused by the app | ohyesmlx/engines.py:797 and :1173 (venv from `sys.executable`), :265-279 (version read from files only), :1242 |
| 38 | S6-F5 | **Medium** | Medium | CONFIRMED | G | The clean-account smoke that is meant to close P5-5 runs a wheel in a Homebrew-Python venv, not the bundle | scripts/smoke_clean_account.py:843-855; scripts/smoke_clean_account.sh (`PY=/opt/homebrew/bin/python3.14`, the |
| 39 | S6-F6 | **Medium** | Medium | CONFIRMED | G | The SBOM can name a commit that does not contain the shipped code, and its source digest is taken from the repository, not from the bundle | scripts/make_sbom.py:94-113; ohyesmlx/measure.py:436-440; scripts/build_app.sh:68 and :111; docs/release/gatek |
| 40 | S6-F8 | **Medium** | Medium | CONFIRMED | G | The release's integrity story is unbacked: no step produces the promised sha256, and the doc credits the ad-hoc signature with tamper evidence it does not give | scripts/build_app.sh:8 and :124-129; docs/release/gatekeeper.md:30-31, :52-56; scripts/make_sbom.py:128-147 |
| 41 | S1-F2 | **Low** | Low | CONFIRMED | C | Owner liveness is decided by pid alone, so a recycled pid makes a dead owner's lock or ledger permanent | `ohyesmlx/fetch.py:354-390` (`_pid_alive`, `_acquire_lock`); `ohyesmlx/runtimes.py:612` (`_process_alive`), `: |
| 42 | S1-F3 | **Low** | Low | CONFIRMED | D | A network error mid-body escapes `_fetch_file`: no retry, and the partial is never ledgered | `ohyesmlx/fetch.py:1066-1077` (read loop), `:936-954` (the only `except OSError`), `:1124-1135` (`fetch_file`) |
| 43 | S1-F4 | **Low** | Low | CONFIRMED | D | The retry budget is cumulative per file and its exhaustion deletes a valid partial | `ohyesmlx/fetch.py:1112-1120`, `:916` |
| 44 | S1-F5 | **Low** | Low | CONFIRMED | B | `done` frees the job slot before the download's ledger write and lock release | `ohyesmlx/fetch.py:711-718` with `:772`, `:887`, `:1177`; `ohyesmlx/server.py:198-202` |
| 45 | S1-F6 | **Low** | Low | CONFIRMED | B | The event cap ends the job on paper while its worker keeps running, breaking "one job, one model" | `ohyesmlx/server.py:185-202` |
| 46 | S1-F7 | **Low** | Low | CONFIRMED | E | The lab-path record can refuse after the irreversible install, leaving a venv nothing rolls back or records | `ohyesmlx/engines.py:1294-1295`, `:493-496` |
| 47 | S1-F8 | **Low** | Low | CONFIRMED | D | Evict deletes `refs/main` because it once created it, even after another tool rewrote it | `ohyesmlx/fetch.py:871-874` (write + ledger), `:1250-1258` (remove) |
| 48 | S2-F6 | **Low** | Low | CONFIRMED | A | A FAIL row whose requests failed in transport is published as "coherence: pass", and the transport reason buries garbage | `ohyesmlx/report.py:1102-1106`; `ohyesmlx/measure.py:1236-1245` |
| 49 | S2-F7 | **Low** | Low | CONFIRMED | A | A lost second visit fails the row; a lost first visit is an annotation | `ohyesmlx/measure.py:843-852` and `654-668`; contract `docs/interfaces/sweep-pins.md:174-203` |
| 50 | S2-F8 | **Low** | Low | CONFIRMED | A | A hung engine is retried at 600 s per request with no consecutive-failure bailout | `ohyesmlx/measure.py` `_warmup_window` / `_request` (1000-1112 range); default `timeout_s=600.0` in `transport |
| 51 | S2-F9 | **Low** | Low | CONFIRMED | A | `_check_harness` skips a header with no `harness` key, so a pre-stamp run joins a stamped one | `ohyesmlx/report.py:1499-1502` |
| 52 | S2-F10 | **Low** | Low | CONFIRMED | F | A restore that raises after a pin that did not take effect is swallowed without a trace | `ohyesmlx/quickbench.py:707-717` |
| 53 | S2-F11 | **Low** | Low | CONFIRMED | A | `latest` picks by file mtime and keys only on winners, so a repo can show a superseded number | `ohyesmlx/quickbench.py:1040-1058` |
| 54 | S3-F3 | **Low** | Medium | REFUTED | B | A failed Osaurus restore is never stated to the user, and its detection depends on the whole summary decoding | `app/Sources/OhYesMLXKit/AppModel.swift:679-681`, `:702`; `app/Sources/OhYesMLX/Screens/ResultsView.swift:110- |
| 55 | S3-F11 | **Low** | Low | CONFIRMED | B | `HTTPBackend.events` reconnects forever on every error except `unknown_job` | `app/Sources/OhYesMLXKit/HTTPBackend.swift:143-156` |
| 56 | S3-F12 | **Low** | Low | CONFIRMED | B | Quit handshake: a backend that exits while "Quit anyway" is offered strands the app, and the quit banner mislabels what is happening | `app/Sources/OhYesMLXKit/AppModel.swift:531-533`, `:571-574`; `app/Sources/OhYesMLX/RootView.swift:10-11`, `:1 |
| 57 | S3-F13 | **Low** | Low | CONFIRMED | B | "Stop After This Cell" cannot be escalated to "Stop Now" | `app/Sources/OhYesMLX/Screens/BenchmarkView.swift:80`, `:89`, `:95-98` |
| 58 | S3-F14 | **Low** | Low | CONFIRMED | B | Any failure to open or lock `app.lock` is reported as "already running" and the app quits silently | `app/Sources/OhYesMLXKit/BackendLauncher.swift:170-172`, `:260-269` |
| 59 | S3-F15 | **Low** | Low | CONFIRMED | B | Retry from the interrupted banner skips the plan and confirmation the first start required, and the banner itself only appears for crashes | `app/Sources/OhYesMLXKit/AppModel.swift:546-559`, `:684` |
| 60 | S3-F16 | **Low** | Low | CONFIRMED | C | `kill()` signals a pid without checking the child is still that process | `app/Sources/OhYesMLXKit/BackendLauncher.swift:99-101` |
| 61 | S3-F17 | **Low** | Low | CONFIRMED | B | A plan fetch that fails without a `BackendError` leaves the previous model's plan under the new picker selection, and Start runs it | `app/Sources/OhYesMLXKit/AppModel.swift:506-508`, `:512-514` |
| 62 | S4-F8 | **Low** | Medium | CONFIRMED | E | Stage B runs the winner engine on every sibling, whether or not the sibling's row lists that engine | ohyesmlx/quickbench.py:292 (stage A filters on `model.engines`), :294-302 (stage B unfiltered), :848-901 |
| 63 | S4-F10 | **Low** | Low | CONFIRMED | E | An exception on the install failure path skips rollback | ohyesmlx/engines.py:1199-1213 (`send` appends the log, then emits), :1232-1237, :1266-1280 |
| 64 | S4-F11 | **Low** | Low | CONFIRMED | D | Quick-bench deletes the user's own partial download of a sibling | ohyesmlx/quickbench.py:852-866, :915-921; ohyesmlx/fetch.py:1250-1277 |
| 65 | S4-F12 | **Low** | Low | CONFIRMED | D | The final sweep's evict failure is logged but not recorded in `not_evicted` | ohyesmlx/quickbench.py:944-953, against :922-928 |
| 66 | S4-F13 | **Low** | Low | CONFIRMED | C | The download lock can be stolen in the gap between its creation and its pid being written | ohyesmlx/fetch.py:371-389 |
| 67 | S4-F14 | **Low** | Low | CONFIRMED | D | A verified partial is renamed into place without fsync, and nothing downstream re-checks bytes | ohyesmlx/fetch.py:891-904 (`finish`), :272-298 (`downloaded`), :780-809; ohyesmlx/quickbench.py:283 |
| 68 | S5-F11 | **Low** | Low | CONFIRMED | C | `Handle.stop` can signal the process group of a stranger that inherited a reaped launcher pid | `ohyesmlx/runtimes.py:612-631` (`_process_alive`), `:651-659` (`_signal_tree`), `:1663-1672` (`_shutdown`) |
| 69 | S5-F12 | **Low** | Low | CONFIRMED | F | `osaurus_set_seqs` rewrites the live host config in place, outside the module that owns the edit | `scripts/osaurus-pin.sh:46-67` |
| 70 | S5-F13 | **Low** | Low | CONFIRMED | C | The ledger's `stop_command` is data on disk that gets executed | `ohyesmlx/runtimes.py:1693-1783` (record/read), `:1827-1864`, `:1908-1937` |
| 71 | S5-F14 | **Low** | Low | CONFIRMED | C | The Osaurus app is recognised only under `/Applications` | `ohyesmlx/runtimes.py:149-152`, `:163-172`, `:634-648` |
| 72 | S6-F7 | **Low** | Medium | REFUTED | G | check_bundle's P5-9 environment check contradicts its own recorded evidence, and its PATH match is a substring | scripts/check_bundle.sh:209-231; docs/threat-model.md:606; AGENTS.md ("`scripts/check_bundle.sh dist/OhYesMLX. |
| 73 | S6-F9 | **Low** | Low | CONFIRMED | G | No gate runs the path every downloader takes: a quarantined zip | scripts/check_bundle.sh (whole), scripts/smoke_clean_account.sh (whole); app/Sources/OhYesMLXKit/AppModel.swif |
| 74 | S6-F10 | **Low** | Low | CONFIRMED | G | "Remove everything the app has added" leaves two things behind | docs/release/gatekeeper.md:71-87; ohyesmlx/engines.py:813-828; app/Sources/OhYesMLXKit/AppModel.swift:221, :23 |
| 75 | S6-F11 | **Low** | Low | CONFIRMED | G | P5-4 reports a network outage as a packaging failure and cannot tell it from a TLS failure | scripts/check_bundle.sh:105-133 |
## 7. Tests (branch `review/fable-verify`, unmerged)

- **S2-F1**: `test: tests/test_fable_s2_f1.py::test_a_failed_incoherent_cell_publishes_no_figure, tests/test_fable_s2_f1.py::test_a_failed_cell_with_two_lost_requests_publishes_no_survivor_median`
- **S3-F1**: `test: app/Tests/OhYesMLXKitTests/FableS3F1Tests.swift::testEventsOverTheRealTransportDispatchADoneEvent`
- **S5-F1**: `test: tests/test_fable_s5_f1.py::test_the_mlx_lm_control_does_not_get_another_engines_lab_bin_on_path`
- **S5-F2**: `test: tests/test_fable_s5_f2.py::test_cold_load_s_does_not_include_the_version_probe_or_lsof`
- **S1-F1**: `test: tests/test_fable_s1_f1.py::test_stop_now_does_not_signal_a_stale_own_pid_ledger_entry`
- **S2-F2**: `test: tests/test_fable_s2_f2.py::test_a_whole_response_arriving_in_one_write_is_read_without_waiting_for_more_bytes, tests/test_fable_s2_f2.py::test_a_delta_already_buffered_is_stamped_when_the_next_bytes_arrive`
- **S2-F3**: `test: tests/test_fable_s2_f3.py::test_an_update_between_visits_cannot_leave_a_pass_row`
- **S2-F4**: `test: tests/test_fable_s2_f4.py::test_a_pass_row_publishes_a_bare_number_for_a_peak_the_sampler_disowned`
- **S2-F5**: `test: tests/test_fable_s2_f5.py::test_zero_usage_reasoning_over_a_real_reasoning_stream_is_not_taken`
- **S3-F2**: `test: app/Tests/OhYesMLXKitTests/FableS3F2Tests.swift::testADownloadResultDoesNotReplaceTheBenchmarkSummary`
- **S3-F4**: `test: app/Tests/OhYesMLXKitTests/FableS3F4Tests.swift::testACancelThatReturnsAfterDoneDoesNotReactivateTheJob`
- **S3-F5**: `test: app/Tests/OhYesMLXKitTests/FableS3F5Tests.swift::testTheJobIsStillRunningDuringTheRollbackThatFollowsAnError`
- **S3-F6**: `test: app/Tests/OhYesMLXKitTests/FableS3F6Tests.swift::FableS3F6Tests.testASecondStartWhileTheFirstIsInTheAirDeletesTheWinnersCrashRecord`
- **S3-F7**: `test: app/Tests/OhYesMLXKitTests/FableS3F7Tests.swift::testRetryingFromCouldntStartDoesNotTreatTheLiveBackendAsASecondInstance`
- **S3-F8**: `test: app/Tests/OhYesMLXKitTests/FableS3F8Tests.swift::testAppDeathDoesNotFreeTheLockWhileTheBackendIsAlive`
- **S3-F9**: `test: app/Tests/OhYesMLXKitTests/FableS3F9Tests.swift::testTheResultsScreenShowsTheContentionLabel + ::testATiedStageIsNotBadgedAsOneFastestEngine`
- **S3-F10**: `test: app/Tests/OhYesMLXKitTests/FableS3F10Tests.swift::testDownloadCompletionRefreshesFreeDisk + ::testEvictCompletionRefreshesFreeDisk`
- **S4-F1**: `test: tests/test_fable_s4_f1.py::test_a_port_that_goes_busy_after_stage_a_is_not_driven_in_stage_b, tests/test_fable_s4_f1.py::test_an_osaurus_app_opened_after_stage_a_is_not_pinned_for_stage_b`
- **S4-F2**: `test: tests/test_fable_s4_f2.py::test_an_app_venv_with_no_lab_record_is_startable_or_installable_again`
- **S4-F3**: `test: tests/test_fable_s4_f3.py::test_a_full_cache_volume_is_refused_even_when_the_root_volume_has_room`
- **S4-F4**: `test: tests/test_fable_s4_f4.py::test_a_stage_b_sibling_download_hears_stop`
- **S4-F5**: `test: tests/test_fable_s4_f5.py::test_best_keeps_the_baseline_when_the_sibling_is_inside_the_tie_band`
- **S4-F6**: `test: tests/test_fable_s4_f6.py::test_the_peak_the_memory_sentence_states_is_above_budget_only_for_a_left_out_row[8-gib-1.82-gb-tight]`
- **S4-F7**: `test: tests/test_fable_s4_f7.py::test_a_partly_downloaded_row_is_judged_on_what_is_left`
- **S4-F9**: `test: tests/test_fable_s4_f9.py::test_a_failed_sibling_download_is_evicted_or_recorded`
- **S5-F3**: `test: tests/test_fable_s5_f3.py::test_start_refuses_when_a_failed_stop_left_another_engine_resident`
- **S5-F4**: `test: tests/test_fable_s5_f4.py::test_an_orphan_whose_port_cannot_be_read_keeps_its_ledger_file`
- **S5-F5**: `test: tests/test_fable_s5_f5.py::test_the_ledger_names_the_engine_before_readiness_is_awaited`
- **S5-F6**: `test: tests/test_fable_s5_f6.py::test_a_crashed_shell_pin_does_not_let_the_app_report_the_pinned_state_restored — restore() returns True with the host at idle 900; ::test_a_pin_refuses_over_a_backup_in_another_directory — the second pin succeeds into its own directory; ::test_the_shell_pin_and_the_app_pin_name_one_backup_directory; ::test_the_shell_pin_restores_on_a_plain_exit`
- **S5-F7**: `test: tests/test_fable_s5_f7.py::test_a_failed_restore_check_exits_non_zero`
- **S5-F8**: `test: tests/test_fable_s5_f8.py::test_pin_replaces_the_committed_baseline_with_the_live_host`
- **S5-F9**: `test: tests/test_fable_s5_f9.py::test_RED_the_capture_attests_concurrency_smelt_mode`
- **S5-F10**: `test: tests/test_fable_s5_f10.py::test_a_stop_is_not_refused_by_a_lab_path_that_is_not_there`
- **S6-F1**: `test: tests/test_fable_s6_f1.py::test_the_builds_version_read_cannot_write_bytecode and tests/test_fable_s6_f1.py::test_the_builds_compileall_replaces_the_bytecode_it_copies`
- **S6-F2**: `test: tests/test_fable_s6_f2.py::test_the_tree_the_build_copies_is_the_tarball_and_nothing_else`
- **S6-F3**: `no test: the P5-6 step exists only inside `scripts/check_bundle.sh`, whose run launches the app and writes Application Support — both forbidden to this role — and this worktree has no `dist/` bundle; the same mechanism was applied to the shipped artifact in the main checkout, with the two-sided result quoted above`
- **S6-F4**: `test: tests/test_fable_s6_f4.py::test_a_venv_whose_interpreter_moved_with_the_app_is_not_installed[mlxlm]`
- **S6-F5**: `test: tests/test_fable_s6_f5.py::test_the_smoke_spawns_the_venv_console_script_with_no_interpreter_flags`
- **S6-F6**: `test: tests/test_fable_s6_f6.py::test_a_dirty_worktree_does_not_stamp_a_bare_git_commit`
- **S6-F8**: `test: tests/test_fable_s6_f8.py::test_the_build_produces_the_digest_the_release_doc_promises`
- **S1-F2**: `test: tests/test_fable_s1_f2.py::test_a_lock_whose_owner_pid_belongs_to_another_process_is_reclaimed; tests/test_fable_s1_f2.py::test_a_dead_owners_ledger_file_is_swept_when_its_pid_is_alive_again`
- **S1-F3**: `test: tests/test_fable_s1_f3.py::test_a_mid_body_timeout_is_retried_and_never_escapes_download`
- **S1-F4**: `test: tests/test_fable_s1_f4.py::test_a_valid_four_byte_prefix_is_deleted_when_the_cumulative_budget_runs_out`
- **S1-F5**: `test: tests/test_fable_s1_f5.py::test_done_arrives_while_the_lock_is_still_held_and_the_ledger_is_unwritten`
- **S1-F6**: `test: tests/test_fable_s1_f6.py::test_the_cap_must_not_free_the_slot_while_the_module_call_still_owns_the_engine`
- **S1-F7**: `test: tests/test_fable_s1_f7.py::test_a_lab_paths_refusal_after_the_pip_steps_rolls_the_venv_back`
- **S1-F8**: `test: tests/test_fable_s1_f8.py::test_evict_keeps_a_refs_main_that_no_longer_holds_the_ledger_revision`
- **S2-F6**: `test: tests/test_fable_s2_f6.py::test_a_transport_failure_beside_garbage_is_not_published_as_coherence_pass`
- **S2-F7**: `test: tests/test_fable_s2_f7.py::test_the_two_lost_visits_are_judged_alike`
- **S2-F8**: `test: tests/test_fable_s2_f8.py::test_a_hung_engine_is_not_retried_to_the_end_of_the_run`
- **S2-F9**: `test: tests/test_fable_s2_f9.py::test_a_stamped_column_beside_a_legacy_one_says_so_or_refuses`
- **S2-F10**: `test: tests/test_fable_s2_f10.py::test_a_raising_restore_after_a_failed_pin_names_the_backup_directory`
- **S2-F11**: `test: tests/test_fable_s2_f11.py::test_a_repo_the_newest_run_measured_and_lost_does_not_keep_an_older_win`
- **S3-F3**: `REFUTED (test: app/Tests/OhYesMLXKitTests/FableS3F3Tests.swift::testARestoreFailureIsFailedAndStatedEvenWhenTheSummaryDoesNotDecode — the backend's own `error` event sets `.failed` before the summary and `BenchmarkView.swift:39-40,115-128` renders its restore message; ::testAnAddedUnknownFieldKeepsTheTypedRestoreFailure — added fields decode)`
- **S3-F11**: `test: app/Tests/OhYesMLXKitTests/FableS3F11Tests.swift::testEventsGivesUpOnARefusedPort`
- **S3-F12**: `test: app/Tests/OhYesMLXKitTests/FableS3F12Tests.swift::testBackendExitingWhileQuitAnywayOfferedCompletesTheQuit`
- **S3-F13**: `no test: the `.disabled(stopping)` is a SwiftUI modifier in the `OhYesMLX` executable target, which the kit test target cannot import; the kit-level test shows the model still accepts "Stop Now" after "Stop After This Cell", so the view's single `stopping` flag is the whole of the block`
- **S3-F14**: `test: app/Tests/OhYesMLXKitTests/FableS3F14Tests.swift::testAppLockThatCannotBeOpenedIsNotAlreadyRunning`
- **S3-F15**: `test: app/Tests/OhYesMLXKitTests/FableS3F15Tests.swift::testRetryOfAnInterruptedInstallDoesNotStartWithoutConsent`
- **S3-F16**: `no test: the window is between Foundation reaping the child and `Darwin.kill`, which has no deterministic trigger and no syscall seam to inject; the evidence is the unguarded call at `BackendLauncher.swift:99-101` and its forceKill/quitWait callers`
- **S3-F17**: `test: app/Tests/OhYesMLXKitTests/FableS3F17Tests.swift::testPlanFailureClearsThePreviousModelsPlan`
- **S4-F8**: `test: tests/test_fable_s4_f8.py::test_stage_b_skips_a_sibling_that_does_not_list_the_winner_engine`
- **S4-F10**: `test: tests/test_fable_s4_f10.py::test_an_emitter_that_raises_on_the_error_event_still_rolls_the_venv_back`
- **S4-F11**: `test: tests/test_fable_s4_f11.py::test_the_users_own_partial_of_a_sibling_survives_the_runs_eviction`
- **S4-F12**: `test: tests/test_fable_s4_f12.py::test_a_sweep_eviction_that_raises_is_recorded_in_not_evicted`
- **S4-F13**: `test: tests/test_fable_s4_f13.py::test_an_empty_lock_naming_no_pid_is_held_not_reclaimed`
- **S4-F14**: `test: tests/test_fable_s4_f14.py::test_a_wrong_bytes_blob_of_the_right_size_is_planned_for_measurement`
- **S5-F11**: `test: tests/test_fable_s5_f11.py::test_handle_stop_never_signals_the_group_of_a_pid_it_already_reaped`
- **S5-F12**: `test: tests/test_fable_s5_f12.py::test_zero_is_refused_like_the_message_says`
- **S5-F13**: `test: tests/test_fable_s5_f13.py::test_stop_now_does_not_execute_a_stop_command_read_from_the_ledger`
- **S5-F14**: `test: tests/test_fable_s5_f14.py::test_resident_osaurus_pids_sees_a_home_directory_install`
- **S6-F7**: `REFUTED (on Darwin 27.2.1 `ps eww -p <pid> -o command=` prints the full environment of an ad-hoc-signed process — the class `build_app.sh:95` puts the bundled `python3` in (`codesign`: `flags=0x2(adhoc)`, no platform identifier) — and fed that live dump the script's own block at `check_bundle.sh:214-231` prints two PASS with `COUNT=0`, so the `*)` branch is not taken, "all checks PASS" is reachable, and `docs/threat-model.md:606` is consistent with the check; the false statement is the comment at `:209-212`, which reads `ps eww` against Apple platform binaries (`/bin/sh`, `/bin/sleep`, Finder) that hide it; the surviving substring/PYTHON* weakness is real and proved by `tests/test_fable_s6_f7.py`)`
- **S6-F9**: `test: tests/test_fable_s6_f9.py::test_no_gate_loads_a_quarantined_zip_the_way_a_downloader_does`
- **S6-F10**: `test: tests/test_fable_s6_f10.py::test_an_engine_install_leaves_pips_default_cache_and_the_doc_does_not_say_so`
- **S6-F11**: `test: tests/test_fable_s6_f11.py::test_one_failure_line_covers_both_a_dead_network_and_a_bad_certificate`
## 8. Cost and process notes

- **Fable 5.2:** six headless `claude -p --model claude-fable-5-2` runs, 9–16 minutes each, at about $3.6–5.0
  API-equivalent each ($24.46 total), all on Jason's plan inside the promotion. Neither the Fable reset nor any full
  reset was used. `Agent(model: "fable")` resolves to `claude-fable-5-1`, which is why the plan's amendment runs Fable
  headless.
- **Command Code:** dossiers and the W1 sweep about $1.03 (8 runs: MiMo v2.6 Pro, DeepSeek for half of S2), and
  verification $2.69 (52 DeepSeek runs). The expensive part was not dollars but the 5-hour window. Seven parallel MiMo
  Pro dossier workers took it from 6% to 70%, and S2's worker spawned its own subagents. Lessons: cap fan-out at 2–3,
  forbid subagents in dossier orders, and batch Low verifications.
- **Kimi K3.1 Pro** was added as an explicit-only route (`kimi-pro`, bench 18/18) but did no review work. At $0.20/M
  cache reads it costs about 10× MiMo Pro per run, so DeepSeek did the verification.
- A stuck nightly Deep Wiki librarian automation (`command-code`, 18 h old) was found and stopped during P0. It may
  have been using quota, and it is worth a look in Agent-Environment.
- One MiMo request was refused by its provider as "high risk" while writing a mechanical-scan section (grep hits for
  `eval(`, `shell=True` and similar). The continuation listed pattern names instead of quoting source.
