# W1 sweep — Fable 5.2 review (P0)

Part A checks every shape and rule in `docs/interfaces/v5-onboarding.md`, `v5-quickbench.md`,
`v5-hardening.md`, `v5-app.md` and `measurement-core.md` against the code that produces or
consumes it. Each shape gets a verdict; every mismatch is one line
`doc path:line vs code path:line — what differs`. Part B lists tests that cannot fail. Suites
were not run (the order forbids it); nothing outside this file was touched.

Part A verified by direct reading of the cited code ranges, located through
`graphify-out/graph.json` and grep. Where a scout's report is behind a verdict, the cited code
lines were re-read and confirmed before inclusion.

## Findings index

Part A mismatches (12):

1. v5-onboarding.md:80-82 vs ohyesmlx/recommend.py:150-154 — ranking keys order starter tier
   before params (doc: after), and restrict starter-first to `comfortable` rows (doc: any fit).
2. v5-onboarding.md:25 vs ohyesmlx/engines.py:413 — `lab_paths` takes an undocumented
   `read=None` seam. (minor)
3. v5-quickbench.md:74 vs ohyesmlx/server.py:640-646 — "`repo` is the only query parameter"
   is not enforced; extras are ignored, not refused. (nuance)
4. v5-quickbench.md:82-90 vs ohyesmlx/quickbench.py:511 — `run(..., abort=...)` missing from
   the signature block (pinned in v5-app.md:28). (stale doc)
5. v5-quickbench.md:122 vs ohyesmlx/quickbench.py:159-165 — formula names `cards`; the
   parameter is `cells` (and the result is rounded). (naming)
6. v5-hardening.md:67-68 vs ohyesmlx/engines.py:813-828 — the pinned argv block omits
   `--no-deps`, which the code carries and the doc's own prose states.
7. measurement-core.md:173-174 vs ohyesmlx/runtimes.py:2291-2292 — "the two without one"
   ignores concurrency; the code (and MTPLX) make it three.
8. measurement-core.md:194-196 vs ohyesmlx/sample.py:292-302 — the result dict also carries
   `pid` and `interval_s`.
9. measurement-core.md:420-422 vs ohyesmlx/measure.py:592-626 — the run-header pin list
   omits `quick`, which the code writes and `PIN_FIELDS` compares.
10. v5-app.md:56 vs app/Sources/OhYesMLXKit/BackendLauncher.swift:47, 545 — child-exit
    delivery is an `onExit` closure, not the pinned `.exited(status, stderrTail)` case.
11. v5-app.md:93 vs app/Sources/OhYesMLX/Screens/BenchmarkView.swift:76, 85 — the cancel
    controls read "Stop After This Cell" / "Stop Now", not the binding's sentence case.
12. v5-app.md:100 vs app/Sources/OhYesMLX/RootView.swift:67 — the button reads
    "Check Again", not "Check again".

Part B tests that cannot fail (2): see the section at the end —
`tests/test_server.py::test_recommendations_leaves_measured_here_null_without_a_finished_quick_run`
and `app/Tests/OhYesMLXKitTests/AppModelTests.swift::testExcludedModelCarriesItsReason`.

---

## Part A — interface drift

### `docs/interfaces/v5-onboarding.md`

**`Hardware`** (:11-16) — matches.
Field list identical (`ohyesmlx/hardware.py:41-54`); `supported` false off Apple Silicon or
under `MIN_RAM_BYTES` = 8 GiB (`hardware.py:35`, `hardware.py:92-97`) with every other field
still reported (`hardware.py:154-167`); `model_budget_bytes` computed by `model_budget`,
defined once in `hardware.py` (`hardware.py:100-108`).

**`EngineStatus`** (:18-23) — matches.
Fields identical (`ohyesmlx/engines.py:191-201`); `tested` is the detected version against
`engines-tested.json` (`engines.py:60`, `engines.py:617`); `verified` is the manifest's ISO
date set whether or not the engine is installed (`engines.py:618`); `detect_all` returns
`install: null` (`engines.py:619`). `names and ports come from runtimes.py` holds:
`ONBOARDING_ENGINES` matches `RUNTIMES`' five names (`engines.py:53`).

**Lab paths** (:25-31) — matches, one signature note.
`LAB_ENGINES = ("mlxlm", "optiq")` is the whole allowlist (`engines.py:384`); missing file is
`{}`, and invalid JSON, a non-object, an unknown engine key, an app-engine key, or a bad value
raises `ValueError` naming the file and the key (`engines.py:435-461`); `runtimes._engine_env`
prefixes the file's directories to `PATH`, the file overriding the manifest's `lab_path` per
engine, and refuses a directory that is not there or fails `check_lab_dir`
(`ohyesmlx/runtimes.py:512-526`); `detect_all` looks in lab paths first (`engines.py:600-608`).
- v5-onboarding.md:25 vs ohyesmlx/engines.py:413 — `lab_paths` also takes an undocumented
  keyword `read=None` (a text-injection seam for detection/tests); the documented signature is
  otherwise exact. Cosmetic; the shape is unchanged.

**App-bundle executables** (:33-43) — matches.
`ENGINE_BUNDLE_EXECUTABLES` maps `omlx`, `vmlx`, `osaurus` exactly as pinned, with osaurus's
derived from `OSAURUS_APP_BUNDLES` and pointing at `Contents/Helpers/osaurus`, not
`OSAURUS_APP_EXECUTABLES`' `Contents/MacOS/osaurus` (`runtimes.py:149-172`).
`_resolve_program` resolves the first non-`env`/non-`K=V` token against
`shutil.which(token, path=env["PATH"])`, substitutes the bundle executable only when the name
does not resolve and the file exists and is executable, and returns the command unchanged
otherwise (`runtimes.py:534-566`); its only callers are `_spawn` and `_run`
(`runtimes.py:574`, `runtimes.py:600`). Start commands are built before it runs, so recorded
argv is unchanged.

**`Plan`** (:45-48) — matches.
`Plan`/`Step` fields identical (`engines.py:170-188`); `guided_download` vs `command` kinds
produced by `_guided_plan`/`_command_plan` (`engines.py:749`, `engines.py:779`).

**`Model`** (:50-65) — matches.
Field list identical (`ohyesmlx/catalog.py:95-117`); `base` is required non-empty at load
(`catalog.py:208`, `_string` at 120-124); `params` documented and treated as the base count
(`catalog.py:101`); `size_bytes` enforced equal to the sum of `files` (`catalog.py:231-235`);
every file carries exactly one of `sha256`/`git_oid`, never both and never neither
(`catalog.py:183-192`), with 64-hex/40-hex validation (174-182); `engines` is a subset of the
five (`catalog.py:239-244`); `measured_here` must be a bool (245-247); every violation raises
`ValueError` naming the file, the repo and the field (`catalog.py:199-206`).
Note: `Model.base` carries a default `""` declared last (`catalog.py:112-117`) so hand-built
test rows skip it; `load` can never produce it. The doc shape is what the file holds; this is
the documented test seam, not drift.

**`check_path` / `disk_needed`** (:67-69) — matches.
`check_path` is the one path guard (`catalog.py:138-157`), applied by `_files` at load
(`catalog.py:170`) and by `fetch.plan` (`ohyesmlx/fetch.py:227`); `disk_needed` is
`ceil(nbytes * DISK_MARGIN)` with `DISK_MARGIN = 1.2` (`catalog.py:51-60`), and `recommend`
and `fetch` both ask it (`recommend.py:141`, `fetch.py` plan).

**`Pick`** (:71-91) — one mismatch.
Fields identical (`ohyesmlx/recommend.py:72-84`); `params_b` is the base count in billions,
one decimal (`recommend.py:196`); `fit` comfortable at 2.0x and tight at 1.25x of
`Hardware.model_budget_bytes`, omitted otherwise (`recommend.py:36-43`, 87-93);
`fit_basis` always `"estimated"` (200); `engines`/`install_needed` semantics (190-202); the
reason template carries decimal-GB numbers and no speed claim, and a downloaded row's says it
is already on this Mac with no download size (96-115); a downloaded row is exempt from the
disk budget and still answers to memory (133-147); `measured_here` comes only from the
caller's optional map (163, 174-176, 206).
- v5-onboarding.md:80-82 vs ohyesmlx/recommend.py:150-154 — the ranking keys differ twice:
  (1) the doc orders "comfortable before tight, then larger `params`, starter tier first only
  while free disk is under 20 GiB, ties by repo id" — params before the starter-tier rule —
  while `_rank`'s key order is (fit, tier, -params, repo), so under disk pressure a smaller
  starter row outranks a larger standard one; (2) the doc's starter-tier rule fires whenever
  free disk is under 20 GiB, while the code additionally requires
  `fit == "comfortable"` (`starter_first = fit == "comfortable" and free_disk <
  STARTER_DISK_PRESSURE_BYTES`, `recommend.py:152`), so tight rows never take starter-first
  order. The code's comment claims "AC-4's order: fit, then tier under disk pressure, then
  more parameters, then repo id" (`recommend.py:151`); the doc text disagrees with the code's
  stated order. Which one is the intent needs Jason's word — the sweep does not adjudicate.

**`exclusion_reason` + `GET /recommendations`** (:93-101) — matches.
`exclusion_reason(model, hw, free_disk, downloaded=...)` returns a fixed-template memory or
disk shortfall and null on clearance, with `downloaded` repos not asked for disk
(`recommend.py:118-147`); the server composes `{"picks", "excluded", "unsupported_reason"}`
from `pick` + `exclusion_reason` with `downloaded` built from `fetch.downloaded`, and on an
unsupported Mac answers empty picks with `Hardware.unsupported_reason`, never copied into a
per-model reason (`ohyesmlx/server.py:560-607`; `fetch.downloaded(model, cache_dir=None)`
exists as pinned, `fetch.py:272`).

**`canary`** (:193-207) — matches.
`NOISE_FLOOR = 0.05` (`ohyesmlx/canary.py:47`) and `LOAD_NOISY = 4.0` (`canary.py:53`) with a
reading noisy at `max(before, after) > 4.0` (`canary.py:88-89`); `canary.cells(engine, spec)`
writes exactly one `--cells` string (`canary.py:193-199`) consumed by `cli.build_cells` +
`measure.run_cells` on the decode workload one engine at a time in manifest order
(`ohyesmlx/cli.py:877-934`); `verdict` is the pure worst-moved comparison past the floor
(`canary.py:108-135`); a non-PASS row is `FAIL: <reason>` and is never compared
(`canary.py:149-150`); `--engines/--record/--allow-noisy/--yes` all exist, and without `--yes`
the quiet-machine rule and the estimate print and nothing starts (`cli.py:755-789`, 893-894);
`--record` writes only `decode_tok_s`, `ttft_s`, `version_measured`, `measured` and never
adopts the tested version or its date (`canary.py:207-228`). The manifest's canary block keys
are exactly `{format, repo, workload, decode_tok_s, ttft_s, measured, version_measured}`
(`ohyesmlx/engines-tested.json`).

**Job** (:103-120) — matches.
Closed args set `_JOB_ARGS`/`_JOB_FLAGS` (`server.py:103-112`); `_args_problem` names the key
for an extra/missing key, a non-string name, `confirmed` not JSON true, or a non-bool
`osaurus` → `400 bad_args` (`server.py:315-339`); unknown kind → `400 bad_kind`
(`server.py:673`); a non-JSON Content-Type is `415`, an oversized/absent Content-Length
`413` before the body is read, invalid JSON `400 bad_json` (`server.py:664-720`); `202
{"job_id": 16-hex}` (`secrets.token_hex(8)`, `server.py:681`, 704); a second job is `409
busy` naming the running id (`server.py:684`) and the slot frees when `done` is stored
(`server.py:182-202`). Module refusals (`unknown_engine`, `unknown_repo`, `low_disk` with
integer `free_bytes`/`needed_bytes`) arrive as the job's `error`/`done` events
(`server.py` job thread; `engines.py:1132-1138` event shape).

**Events** (:121-132) — matches.
Framing `id: <seq>\ndata: <event JSON>\n\n` (`server.py:930-932`); event shape
`{"seq","type","message","fraction","payload"}` (`engines.py:1132-1138`); `404 unknown_job`
(`server.py:862-864`); stored replay then `Last-Event-ID` resume with `400 bad_event_id` on a
non-integer or negative value (`server.py:881-907`); `: keepalive` every quiet 15 s
(`KEEPALIVE_S = 15.0`, `server.py:66`, 915-923); close after `done` (`server.py:934-935`);
`MAX_STREAMS_PER_JOB = 4` (`server.py:90`) with `429 too_many_streams` and the slot returned
however the stream ends (`server.py:221-232`, 869-879); `MAX_EVENTS = 10_000`
(`server.py:70`) ended with `error {"code": "too_many_events"}` + `done` (`server.py:185-195`);
the stream waits on the job's condition and each write is bounded by the socket timeout
(`server.py:857-860`, 404).

**Cancel** (:133-141) — matches.
`202` and the cancel callable answers True from then on (`server.py:209-219`, 768-852);
stop points per kind as pinned — download per chunk (`fetch.py:1068`), install between steps
and guided polls with the 900 s step timeout and rollback still applying
(`engines.py:1191-1255`, `STEP_TIMEOUT_S` `engines.py:884`), quickbench between cells with its
cancelled summary (`quickbench.py:772-1010`); `409 not_cancellable` for evict, `409
job_finished`, `404 unknown_job` in that precedence (`server.py:783-790`); the optional body
`{"now": true}` runs the same body guard and sets the abort path (`server.py:795-852`).

**Shutdown** (:142-151) — matches.
`cancel_and_wait(JOB_SHUTDOWN_WAIT_S = 120.0)` (`server.py:76`, `cli.py:1156-1170`); an evict
is waited, never cancelled (`server.py:277`); `engines.kill_running_steps()` then
`JOB_KILL_GRACE_S = 15.0` more (`server.py:81`, 280-281); one stderr line
`{"error": {"code": "shutdown_abandoned", "job", "kind"}}` (`server.py:284-292`); job start
and end stderr lines exactly as pinned, never a token or header value
(`server.py:687`, 764-766); exit 0.

**Download progress events** (:152-158) — matches.
`fraction = (finished + written) / the model's total` with resume seeded from on-disk bytes
(`fetch.py:1085`, 1064, 1137-1158); payload `{"path","bytes_done","bytes_total"}`
(`fetch.py:1097-1101`); emitted only on a ≥0.005 advance **and** ≥0.5 s of the injected clock
(`PROGRESS_MIN_FRACTION = 0.005` `fetch.py:74`, `PROGRESS_INTERVAL_S = 0.5` `fetch.py:69`,
gates at 1086-1089); a file no larger than one chunk emits none (`fetch.py:1083`); one
`progress` with `{"path","bytes"}` per finished file (`fetch.py:1160-1165`).

**Errors** (:160) — matches.
`{"error": {"code", "status", "message"}}` from one `_ERRORS` table with `status` repeating
the HTTP status (`server.py:939-955`); the server binds `127.0.0.1` only (`server.py:56`).

**`ohyesmlx app`** (:162-191) — matches.
Bind and ephemeral port or `--port` (`server.py:56`, `cli.py:826-840`); exactly one stdout
line `{"port", "token"}` with `secrets.token_urlsafe(32)` (`cli.py:1160-1163`,
`server.py:1050`); guard order bad_host (absent included) → any `Origin` → Bearer token
compared as UTF-8 bytes with `hmac.compare_digest` (`server.py:450-457`); route table and
`404 not_found` / `405 method_not_allowed` / `500 install_plan_failed` naming the engine /
`500 internal` with the message and no traceback (`server.py:488-498`, 554-555); every JSON
response `application/json; charset=utf-8` + `Cache-Control: no-store`, streams
`text/event-stream` + `no-store` (`server.py:961-963`, 899-900); no `Access-Control-*` header
anywhere in the package; HTTP/1.0 with daemon handler threads (`server.py:402`, 978); idle
10 s (`HANDLER_TIMEOUT_S = 10.0`, `server.py:62`); `MAX_HANDLER_THREADS = 32` with a full
pool closed with no response and no thread (`server.py:86`, 982-999); guard refusals write
one stderr line `{"refused", "method", "path", "time"}` with the query dropped and the path
`<unknown>` off the served set (`server.py:347-376`, 468-470), served GETs log nothing
(`server.py:408-410`); `app_support_dir()` created `0700` before serving and before a
confirmed quickbench (`cli.py:1137`, `ohyesmlx/__init__.py:24-61`); stdin EOF/SIGINT/SIGTERM
release the port and exit 0 (`cli.py:1156-1202`); a bind failure prints nothing on stdout,
writes one `{"error": {"code": "bind_failed", "message"}}` line and exits 2
(`cli.py:1139-1147`).

### `docs/interfaces/v5-quickbench.md`

**`Model.base` and `catalog.siblings`** (:9-15) — matches.
`base` required per row with a `ValueError` naming file/repo/field (`catalog.py:208`, 206);
`siblings` returns the other same-`base` rows in catalog order (`catalog.py:296-304`); the
build script's seed table writes `base` and its two duplicate bases are exactly the two the
doc names (`scripts/build_catalog.py:56-190`).

**The `quick` header pin** (:17-23) — matches.
`run_cells(..., quick: bool = False)` writes `"quick"` into the run header
(`ohyesmlx/measure.py:454`, 625); `"quick"` is in `report.PIN_FIELDS` (`ohyesmlx/report.py:261`);
`ABSENT_PINS["quick"] = False` (`report.py:1445`); `_check_not_quick` refuses by value
(`header.get("quick", False)`, `report.py:1463-1478`) and runs before `_check_pins` = guard 1
in both the grid and the sweep (`report.py:527-528`, 2325-2326), naming the directory and
saying quickbench results never join the published tables.

**`osaurus_settings.pin` / `restore` / `recover`** (:25-57) — matches.
Signatures exact (`ohyesmlx/osaurus_settings.py:227-232`, 339-344, 364-369); `PIN_FILES`
pinned pair (`osaurus_settings.py:50`); `baseline.json` / `baseline.absent` markers (55-56);
the three settings set as pinned (279-281); `BASELINE_PATH` under `writable_root()/config`
(46, `ohyesmlx/__init__.py:43-52`); `ValueError` while a backup exists (252-258) and both
configs parsed before either is replaced (267-268); `restore`/`recover` share one
`filecmp.cmp(shallow=False)` verdict with backups removed only on success and `recover` a
silent `False` without one (289-336, 381-382); temp + `os.replace` with mode preservation
(178-199), `0700` backup dir (59, 271), one stderr JSON line per operation (211-224);
`scripts/osaurus-pin.sh` calls `s.pin`/`s.restore`, keeps its trap and sweep, and prints the
module's verdict (`osaurus-pin.sh:28-83`).

**`engines.record_lab_path`** (:61-71) — matches.
Signature exact (`engines.py:465`); written beside the `engines_dir` handed to the call via
`_lab_paths_beside` (`engines.py:368-375`, call at 1295); `check_lab_dir(bin_dir)` before the
file is read or written (`engines.py:493-494`); an app engine refused `ValueError`
(483-487); other entries kept (494-495); the write is `atomic_write_text` (496); `install`
calls it after a pip engine's steps succeed and writes nothing on a failed step (1280-1295).

**`GET /quickbench/plan`** (:73-76) — matches, one descriptive nuance.
Missing/repeated/empty `repo` is `400 bad_args`, a module refusal is `400 bad_args` carrying
its message, and the endpoint never fetches (`server.py:616-638`).
- v5-quickbench.md:74 vs ohyesmlx/server.py:640-646 — the doc says "`repo` is the only query
  parameter"; the handler reads `repo` and silently ignores any extra query parameters
  instead of refusing them. No stated refusal rule differs; only this clause.

**`plan` / `run` / `latest` / `cell_spec` / `estimate_seconds` + the three dataclasses**
(:78-117) — matches, one signature delta.
`PlannedEngine`, `PlannedSibling`, `QuickPlan` field lists exact and in order
(`quickbench.py:105-139`); `plan`/`latest`/`cell_spec` signatures exact (255-263, 1023,
317-319).
- v5-quickbench.md:82-90 vs ohyesmlx/quickbench.py:511 — `run` in code also carries
  `abort=_never_cancelled` (between `cancel` and `cache_dir`), absent from this signature
  block; it is pinned in `v5-app.md:28`, so this is stale doc coverage, not an unpinned
  parameter.

**Plan purity, stage_a rules, estimate** (:119-124) — matches, one naming difference.
`ESTIMATE_PER_CELL_S = 90`, `DOWNLOAD_BYTES_PER_S = 20_000_000` (`quickbench.py:72-73`);
`plan` is pure apart from injected `downloaded` and never invents an engine (282-314); an
empty `stage_a` is legal and says why (816-821).
- v5-quickbench.md:122 vs ohyesmlx/quickbench.py:159-165 — the formula text says
  `cards * ESTIMATE_PER_CELL_S`; the code's parameter is `cells` (and the result is
  `round(...)`). Same arithmetic, different name in the doc.

**`run` semantics and cell layout** (:126-130) — matches.
Returns True finished / False for a refusal, cancel or failed restore (1011-1020); one
`run_cells` call per cell via `cli.build_cells` + `cell_spec` with `warmup=3`, `measured=5`,
`cooldown_s=10`, `quick=True` (`quickbench.py:61-63`, 669-675); directories
`.../A/<engine>` and `.../B/<format>__<engine>` (792, 850, 900).

**Per-cell `progress` payload** (:132-135) — matches.
Exactly `{"stage","engine","format","status","reason"}` on every measured or skipped cell in
both stages, `SKIPPED` for a skip, `reason` null when none (`quickbench.py:781-804`, 879-912).

**The run's rules** (:137-166) — matches, all pinned strings exact.
Winner/tie through `canary.NOISE_FLOOR` (`quickbench.py:67`); the stage-A row reused in stage
B with `reused=True` (836); the chosen repo never downloaded or evicted (283-287, 538-539);
port-occupied skip `quit <engine> first` (446) and Osaurus-app skip
`quit the Osaurus app first` matched by full executable path (198-204, 443); `recover` before
`pin` and `restore` in `finally` (660-661, 707-711); `osaurus_drift(baseline_path=...)` after
the pinned cell with `keep_during_run(during_run_dir=<backup_dir>/during-run)` in a `0700`
directory named `osaurus.during_run` (685-689), the drift failure reason
`Osaurus changed its settings during the run: ` + `describe_drift` (701), a raising check
failing the cell with its message (690-693), and `restore` either way; contention read
through `canary.load` before and after each stage and above `LOAD_NOISY` labelled
`this Mac was busy` (770-937, 80).

**Summary and cell shapes** (:168-199) — matches.
Every pinned key present, including `not_evicted`, the `harness` block, `load.stage_a/b`,
`osaurus` + its conditional `during_run`, both stage blocks with their exact caveat strings,
and `best` (`quickbench.py:341-353`, 398-428, 572-605); the cell shape carries
`PASS|FAIL|SKIPPED|ABORTED`, `label`, `reused` (341-353, 84).

**`best`, the `result` event, `latest`** (:201-211) — matches.
`best` non-null only when `ended == "finished"` (994-996); the summary goes out as one
`result` event from the single write place before the ending's `error`/`done` (997-1019);
`latest()` answers the newest **finished** summary keyed by `best.repo` and skips unreadable
files (1040-1058); `GET /recommendations` fills `Pick.measured_here` only from it (server.py
composition, verified above).

**CLI and job kind** (:213-215) — matches.
`ohyesmlx quickbench --repo R --yes [--osaurus]` prints the plan and starts nothing without
`--yes` (`cli.py:792-818`, 1001-1031); the `quickbench` job kind takes `repo`,
`confirmed: true` and the bool `osaurus`, and a plain cancel stops between cells
(`server.py:107`, 743-751).

### `docs/interfaces/v5-app.md` — "Stop now" (:8-35)

**Cancel body and refusals** — matches.
The body runs the same guard as `POST /jobs`; any key other than `now` or a `now` that is not
JSON true is `400 bad_args` naming the key; `now` on a non-quickbench is `409 not_abortable`
(`"only a quickbench can stop mid-cell"`, `server.py:144`); `404 unknown_job` →
`409 not_cancellable` → `409 job_finished` keep their precedence before the body is parsed
(`server.py:782-791`).

**Abort mechanics** — matches.
`{"now": true}` sets the cancel flag and the abort flag and starts `stop_engines` (default
`runtimes.stop_own_engines`) on a daemon thread, answering `202` at once; a second
`{"now": true}` answers `202` and starts no second stop (`server.py:798-810`).
`stop_own_engines(root=None) -> int` reads this process's ledger only (`_ledger_path()`),
never writes it, stops each entry through `_shutdown(pid, port, tuple(stop_command))`, and
turns a `RuntimeStopError` into one `{"error": {"code": "abort_stop_failed", ...}}` stderr
line before continuing (`runtimes.py:1908-1937`, 143).

**`quickbench.run(abort=...)`** — matches.
After each cell, `abort()` True replaces the cell record with status `ABORTED`, reason
`stopped by the user mid-cell; no number is reported` and no figures, the run ends
`"cancelled"`, the in-flight stop path, sibling eviction and Osaurus restore still run, and
the cell's raw rows stay on disk (`quickbench.py:84-85`, 808-810); an `ABORTED` cell never
wins and is never compared (winner selection takes PASS cells only). If the engine had not
written its ledger entry yet, nothing is stopped and the cell is still recorded `ABORTED` —
the code's worst case matches the pinned "Stop after this cell" with the number discarded.

### `docs/interfaces/v5-hardening.md`

**The running-engines ledger** (:11-21) — matches.
Entry fields exactly `{pid, lstart, argv, serving_pid, serving_lstart, serving_argv, port,
stop_command}` (`runtimes.py:1771-1782`); one file per owner at
`<writable_root()>/results/running-engines/<owner pid>.json` (`_ledger_path`,
`runtimes.py:1686-1690`); each pid's identity read from `/bin/ps -ww -o lstart=,args= -p`
(`runtimes.py:1735`) with an exited launcher recorded null (1763-1768); the write is after
`cold_load_s` is taken (2340-2347); its failure is one stderr line
`{"error": {"code": "running_engine_ledger", ...}}` (`LEDGER_ERROR_CODE`, `runtimes.py:139`,
2348-2349) and never fails the start; every write is same-directory temp + `os.replace`
(1715-1722); `Handle.stop` drops its entry and the file goes with the last one (1786-1797,
1711-1712).

**`stop_orphaned_engines(root=None)`** (:23-34) — matches.
Only digit-stem `*.json` files are ledgers and a live owner's file is never read or touched
(`runtimes.py:1882-1891`); listeners come from `lsof -t` (703); the entry is stopped through
`_shutdown(pid, port, tuple(stop_command))` only when every listener is a recorded pid with
its recorded identity, or nothing is listening and the spawned pid is alive with its identity
(1844-1863); an unreadable port, a stranger listener, or an identity mismatch is dropped and
never signalled; a stop that does not take effect keeps the file and raises
`RuntimeStopError` (1893-1905). The code carries one extra identity guard within the doc's
"reused pid … dropped" clause: when listeners exist and the launcher pid is alive, its
identity must match too before signalling (1847-1853).

**An install step's process group** (:50-56) — matches.
`_real_run` spawns `Popen(..., start_new_session=True)` and registers in `_RUNNING_STEPS`
inside the spawn lock, empty however the step ends (`engines.py:987-1008`); a step over its
own timeout has its group killed and still reports `TIMEOUT_EXIT_CODE` (124) with the output
it produced (1001-1004, 901); `kill_running_steps()` kills every registered group
(963-974) and is what `_Jobs.cancel_and_wait` calls when its 120 s bound expires
(`server.py:279-281`).

**A pip engine's install argv** (:60-77) — one mismatch.
Both steps run their interpreter with `-I`, the pip step `--isolated --no-input
--disable-pip-version-check --require-hashes --only-binary :all: --no-deps -r
<ohyesmlx/constraints/<name>-<version>.txt>` with no `pkg==ver` on the command line, and the
pygame omission rationale is where the doc points (`engines.py:779-831`, 809-812).
- v5-hardening.md:67-68 vs ohyesmlx/engines.py:813-828 — the pinned `sh` block omits
  `--no-deps` between `--only-binary :all:` and `-r`; the code carries it (`engines.py:825`)
  and the doc's own prose at :74-75 states it. The argv block is stale against both.

**`engines._check_hashed_requirements`** (:79-89) — matches.
Called by `install_plan` beside the missing-file check and reported as error code
`no_constraints` (`engines.py:854-862`, 1220-1230); the line grammar is
`name==version` + one-or-more `--hash=sha256:<64 lowercase hex>` and nothing else
(`engines.py:695-697`); a hashless pin's message says "carries no hashes" (737-741); anything
else is refused naming the line, and both messages name the file (742-746);
`scripts/hash_freeze.py` reads one freeze file, writes it back with every
`urls[].digests.sha256` sorted and one header naming source and date (48-51, 94-98, 126).
Minor note: `hash_freeze.py` is stdlib-only in what it runs but imports `ohyesmlx` helpers
(`atomic_write_text`, `_requirement_lines`), so "a stdlib maintenance script beside
`scripts/`" is true of its dependencies, not of its imports.

**`engines.check_lab_dir`** (:91-98) — matches.
Raises `ValueError` naming path and reason unless absolute, a directory under `os.stat`
following symlinks, `st_uid == os.geteuid()`, and no group/other write bit
(`engines.py:387-410`); `runtimes._engine_env` calls it after `expanduser` and after its
"nothing at" refusal (whose wording stands), wrapping a failure as `RuntimeStartError`
carrying the message (`runtimes.py:515-525`); `record_lab_path` calls it before the file is
read or written (`engines.py:493`); `detect_all` only reports and propagates a `ValueError`
as a configuration defect, never a fallback (`engines.py:600-621`).

**`fetch.ledger_for`** (:100-107) — matches.
`DEFAULT_LEDGER` is `<app support>/fetched.json` (`fetch.py:89-92`); `ledger_for` returns it
for `None` or a `realpath` equal to `default_cache_dir()`, else
`<realpath(cache_dir)>.ohyesmlx-fetched.json` as a sibling outside the cache
(`fetch.py:152-168`); `fetch.download` and `fetch.evict` take `ledger_path=None` and default
to it, honouring an explicit path as before (`fetch.py:668-686`, 1191-1206).

### `docs/interfaces/measurement-core.md`

**`Observation` + `chat()`** (:7-33) — matches.
All 14 fields identical in name, order and defaults (`ohyesmlx/transport.py:48-79`);
`chat()`'s signature identical including `temperature=0.0`, `timeout_s=600.0`, `api_key`,
`token_counter`; streaming always on with `stream_options.include_usage`
(`transport.py:193-194`). Prose nit: :41-42 says `reasoning_text` is "declared **last**",
while the listing at :22-24 (and the code) put `cached_tokens`/`mtplx_stats` after it; the
substantive claim — it is the first defaulted field, so it follows every non-default one —
stands.

**Output-stream semantics** (:35-76) — matches.
One mirror/reasoning-only detector (`transport.py:396-407`: `mirrored` and `reasoning_only`),
both routed to the reasoning deltas' first/last/count (415-420); `empty_content` raised when
neither channel produced a timestamp (428-431); both `delta.reasoning` and
`delta.reasoning_content` read (317-319); `text` content-only and `reasoning_text`
reasoning-only throughout.

**`api_key` and `token_counter` wiring** (:46-48, 78-86) — matches.
The one production call site, `measure._request` (`measure.py:1173`), passes
`token_counter=counter` and `api_key=handle.api_key` (1180, 1183); `canary.py` and
`quickbench.py` call `transport.chat` nowhere (quickbench drives `measure.run_cells`).
`TokenCounter(model_dir).count(text) -> int` matches (`token_counter.py:24-76`); the code
annotation is `str | Path` where the doc says `str`.

**`Runtime` + `Handle`** (:88-142) — matches.
Every method present with the pinned signature, including
`mtp_depth_missing(..., *, observations=None, artifact_dir=None)` (`runtimes.py:2096-2103`);
`Handle`'s field order exact (`runtimes.py:1940-1988`), `RUNTIMES` keyed by the six names
(:93). Minor: the code gives the trailing `Handle` fields explicit `None`/`()` defaults the
listing omits (the prose at :148-149 acknowledges this for `first_request_s`), and
`memory_pid` is a property the prose at :146 references.

**`first_request_s`, `log_path`, `request_seed`** (:144-165) — matches.
`_visit` fills `first_request_s` on the cold visit via `_first_warmup_latency` and copies it
with `first_request_workload_id` onto every `CellResult` (`measure.py:908-915`); it is never
passed at construction (`runtimes.py:2350-2362`). `log_path` is the spawn's redirected
stdout/stderr, `None` without a spawn, and an unchecked `on` cell is `FAIL`
(`runtimes.py:596-605`, 1974; `measure.py:850-853`). `request_seed` is `None` while
`TEMPERATURE == 0`, `Optiq` overrides it to `SEED` at an MTP depth, and `measure` asks the
policy once per visit (`runtimes.py:2164`, 2977-2989; `measure.py:860`).

**The concurrency cap** (:167-178) — one mismatch.
The chain and the three caps match: `run_cells(concurrency=N)` → `_visit` → `Runtime.start` →
`build_command` → `start_command`, with oMLX `--max-concurrent-requests`, OptiQ
`--max-concurrent`, vMLX `--max-num-seqs`, the rule at `Omlx.start_command`, and
byte-identical commands at `concurrency=1` (`runtimes.py:2729-2757`, 2929-2953, 3227-3252;
`measure.py:443-458`).
- measurement-core.md:173-174 vs ohyesmlx/runtimes.py:2291-2292 — the doc says "the two
  without one ignore it (mlx-lm passes no cap; Osaurus takes no flags at all)"; the code says
  the cap is "ignored by the three that do not" and MTPLX sets none
  (`runtimes.py` `Mtplx.start_command` ~3573). The count is stale since MTPLX joined
  `RUNTIMES` (the doc's own :93 lists it).

**Readiness and `model_id`** (:180-187) — matches, two doc gaps.
Log-first readiness, `/v1/models` for the model id, and a log re-check after the id appears
are as pinned (`runtimes.py:2218-2243`); `Handle.model_id` is the resolved one (:2354).
Not in the doc: MTPLX adds a `/health` gate (`readiness_complaint`, `runtimes.py:3536+`), and
the name-spelling list at :185-186 omits Osaurus's lowercased hub-repo name
(`hub_repo_name`, `runtimes.py:1476-1489`) and the pinned served names (`vmlx_served_name`,
`mtplx_served_name`) — the list is illustrative and incomplete, not contradicted.

**`sample.py` result** (:189-197) — one mismatch.
- measurement-core.md:194-196 vs ohyesmlx/sample.py:292-302 — the result dict also carries
  `"pid": int` and `"interval_s": float` (`sample.py:293-294`); the doc's key list has only
  `peak_mb`, `samples`, `n_samples`, `duration_s`, `memory_split`, `gpu_wired_limit`,
  `error`.

**`Cell` / `CellResult` / `run_cells`** (:201-240) — matches.
`Cell`'s 4 fields and `CellResult`'s 18 fields exact in name, order and defaults, and
`run_cells`'s signature identical including `warmup: int | str = "plateau"`, `measured=9`,
`concurrency=1`, `cooldown_s=30.0`, required `results_dir` (`measure.py:202-289`, 443-458).

**Record serialization and `load_run`** (:242-274) — matches.
`_record` carries every `CellResult` field except `measured_pin`, adds
`measured_count`/`warmup_count`/`drift`, omits `batch_spans`/`lost_visit_reason`/
`cold_load_after_lost_visit` when not true, and writes `request_seed` on every record
(`measure.py:1452-1501`); `load_run` reads the three leniently and an absent `request_seed`
as `0` (`measure.py:1551-1603`).

**`seed` policy** (:252-274) — matches.
Policy and rationale live once at `runtimes.Runtime.request_seed`; the header's `seed` is
`_header_seed()` (the policy) while each row carries `request_seed` (the fact)
(`measure.py:593-597`, 1469); join guard 1 compares the header field via `PIN_FIELDS`.

**`cold_load_s` / `first_request_s`** (:276-304) — matches.
Both fields and `first_request_workload_id` behave as pinned (see above); the deferred-load
note is attributed to the workload that made the request (report's short-window and note
fields, `report.py:881-884` and the summarize row).

**`Workload` and the three shapes** (:306-330) — matches.
`Workload(id, messages, max_tokens)` (`measure.py:212-224`); chat 128 / prefill 64 / decode
512 and the multiturn set of ten turns are pinned literals (`cli.py:509-551`), with no config
file or flag that invents a third. Nit: the `id` comment's enum does not mention multiturn's
`turn-NN` ids.

**Floors and ordering** (:332-373) — matches.
Coherence + `_set_status` floors (`measure.py:1223-1270`); `render_markdown(rows, *, axis,
rank=DEFAULT_RANK)` keyword-only (`report.py:157-185`);
`CROSS_RUNTIME_UNCOMPARABLE = {peak_mb, cold_load_s}` and
`CHANNEL_DEPENDENT_RANKS = {ttft_p50_s, prefill_tps}` with the empty-rank column and
alphabetical `_unpositioned` rows (`report.py:304-344`, 2031-2040); `concurrent` is
`bool(CellResult.batch_spans)` (`report.py:847`); `CONCURRENCY_TTFT_SENTENCE` prints exactly
under the pinned conditions (`report.py:474-475` for `render_markdown`;
`report.py:2358-2364` for `render_sweep` — the sweep predicate is stated two ways,
`varying == "concurrency"` or any header pin > 1, which are equivalent on a sweep that
actually varies, since `_check_sweep_varies` guarantees one run above 1).

**One runtime at a time; visits** (:375-390) — matches.
Stop-then-port-free before the next start (`runtimes.py:1638-1653`, 1981-1988); interleaved
`visit_plan` and `write_jsonl` after every visit (`measure.py:358-366`, 639-676);
`VISIT_ROUNDS` orderings with zero-quota visits dropped, `measured=1` dropping the second,
and `short_note` on a short window (`measure.py:171`, 721-738; `report.py:881-884`).

**`summarize` / `write_jsonl` / the raw record** (:392-444) — one mismatch.
`summarize(results, *, measured=None)` carries the pinned row fields plus the short-window
ones, e2e percentiles over returned samples' `total_s` sharing `MIN_PERCENTILE_N` and
`percentile()` and absent for failed requests (`report.py:394-423`, 796-893);
`write_jsonl(results, path, *, run=)` lives in `measure` and runs after every visit
(`measure.py:652`, 670, 1403-1501); a stored observation is `asdict(Observation)` and nothing
derived (`measure.py:1477-1483`); `render_markdown` emits the axis caveat
(`report.py:464`). Trivial: the code takes `path: str | Path`.
- measurement-core.md:420-422 vs ohyesmlx/measure.py:592-626 — the run-header pin
  enumeration (`temperature`, `seed`, `warmup`, `measured`, `concurrency`, `prompt_tokens`,
  `cache_state`, `kv_quant`, `mtp_depth`, `stream_experts`, `cooldown_s`) omits **`quick`**,
  which `run_cells` writes (`measure.py:625`) and `PIN_FIELDS` compares
  (`report.py:249-262`). The quickbench doc pins it; this listing is stale.

**Metric formulas and `token_source`** (:446-493) — matches.
All three formulas exact, `content_event_count >= 2` the domain with `None` outside it and
the single-delta `ttft_s` labelled time-to-completion (`report.py:876-879`, `measure.py:183`,
292-328); the three `token_source` cases with strict exact-sum reconciliation in case 3 and
no tolerance (`transport.py:445-474`, `token_counter.py:79-116`).

**Dangling reference check** — none. The section "the lost visit and the short measured
window" that :225, :389 and :398-399 read as "below" lives in
`docs/interfaces/sweep-pins.md:176` ("Phase 6 — the lost visit and the short measured
window"); :399's "below" is cross-file. Not drift in the shapes.

### `docs/interfaces/v5-app.md` — launcher, client, app model (:37-104)

**Interpreter / argv / environment / cwd** (:37-47) — matches.
Bundled `<App>.app/Contents/Resources/python/bin/python3` with `OYMLX_DEV_PYTHON` fallback and
a `couldntStart` naming the looked-for path
(`app/Sources/OhYesMLXKit/BackendLauncher.swift:149-156`, 222-241);
`[python, "-I", "-B", "-m", "ohyesmlx.cli", "app"]` with no token in argv
(`BackendLauncher.swift:185`); a built environment of
`PATH=/usr/bin:/bin:/usr/sbin:/sbin` + `HOME, USER, LOGNAME, TMPDIR, LANG` and no `PYTHON*`
(`BackendLauncher.swift:116-117`, 212-220); `~/Library/Application Support/OhYesMLX` created
`0700` before the spawn (`BackendLauncher.swift:142-147`, 243-254).

**Launch line, token, stderr, stdin** (:48-55) — matches.
First stdout line `{port, token}` with a 30 s bound (`launchTimeout = 30`) and a
`couldntStart` carrying the stderr tail on EOF/exit first, then a `hardware()` poll up to 10 s
before leaving `launching` (`BackendLauncher.swift:132`, 194-206; `AppModel.swift:222`,
410-431); `BackendToken`'s `description`/`debugDescription` are `"<redacted>"` with a
redacting mirror and its raw string's only reader is the `Authorization` header builder
(`BackendToken.swift:10-18`, `HTTPBackend.swift:182`); the stderr ring caps at 200 with both
pipes drained from spawn and post-launch stdout dropped (`BackendLauncher.swift:318-329`,
417-475); stdin is a pipe held open until the quit paths close it.

**Child exit** (:56-57) — one mismatch.
Behavior matches: the exit keeps the `inflightJob` entry, marks the job interrupted, and the
app shows "The backend stopped" with **Relaunch** (`AppModel.swift:531-539`,
`FullWindowStates.swift:96-131`).
- v5-app.md:56 vs app/Sources/OhYesMLXKit/BackendLauncher.swift:47, 545 — the doc names the
  delivery shape `.exited(status, stderrTail)`; the code delivers it as the `onExit:
  (@Sendable (Int32, [String]) -> Void)?` closure (`AppModel.swift:594`), and the only
  `.exited` in the launcher is a `QuitOutcome` case of `quitWait`
  (`BackendLauncher.swift:380-397`) carrying no payload. Same payload (status, stderr tail),
  different API shape; no such enum case exists.

**Quit (P5-8)** (:58-61) — matches.
`quitWait` closes stdin first; with a job running the app waits (150 s bound,
`timing.jobBound`) and never signals on its own, then offers **Quit anyway** whose click alone
sends SIGKILL; with no job: 10 s → SIGTERM → 5 s → SIGKILL
(`BackendLauncher.swift:28`, 380-403; `RootView.swift:126-154` "Finishing <job>…").
Note: the doc calls the job-running wait "unbounded from the app's side"; the code bounds its
poll at exactly the 150 s when **Quit anyway** appears — the observable timeline is the
pinned one.

**Single instance (P5-7)** (:62-64) — matches.
Exclusive `flock(LOCK_EX | LOCK_NB)` on `<App Support>/OhYesMLX/app.lock` before the spawn;
a second launch activates the running app by bundle id and exits without spawning
(`BackendLauncher.swift:170`, 256-274; `OhYesMLXApp.swift:40-49`).

**The `Backend` protocol** (:66-75) — matches.
Method set exact including `cancel(jobID:now:)` and
`events(jobID:after:) -> AsyncThrowingStream<JobEvent, Error>`; `HTTPBackend` sends
`Authorization: Bearer` and never an `Origin` (none in the sources), SSE `id:`/`data:`
framing with `Last-Event-ID` resume and end-after-`done`; `StubBackend` conforms for
view-model tests; snake_case `CodingKeys`, `Int64` byte counts, `BackendError
{code, status, message}` with the UI showing `message` verbatim
(`Backend.swift:79-87`, `HTTPBackend.swift:51-208`, `SSE.swift:38-45`, `Models.swift:515-527`).

**`AppModel` and the screens** (:77-83) — matches.
All ten screens named as pinned; `isTranslocated` checks `bundlePath` for
`/AppTranslocation/` before the spawn and before any job, the screen saying "Move OhYesMLX to
your Applications folder, then open it again" and offering only Quit
(`AppModel.swift:249-261`, `FullWindowStates.swift:70-94`).

**Jason's seven answers** (:85-104) — matches, two label-case deltas.
1. One slot: `"Busy: <kind> <name> is running"`, job-starting controls disabled, a late
   `409 busy` shown as the backend's message (`AppModel.swift:263-270`, the three screens).
2. Interrupted job: `{kind, name, started}` in `UserDefaults` key `inflightJob` before
   `startJob`, cleared on `done`, launch banner "… was interrupted when OhYesMLX quit." with
   click-only **Retry**/**Dismiss** (`AppModel.swift:622-635`, `InterruptedBanner.swift`).
   Display note: `<kind>` renders capitalized and the banner substitutes the pick's display
   title for `<name>`.
3. Cancel controls: the `cancel(now:)` mapping, "Stopping after this cell…" / "Stopping…"
   and ABORTED shown as "Stopped by you" with no number are exact
   (`AppModel.swift:30-31`, `StatusGlyph.swift:39`).
   - v5-app.md:93 vs app/Sources/OhYesMLX/Screens/BenchmarkView.swift:76, 85 — the two
     controls are labeled **"Stop After This Cell"** / **"Stop Now"** (title case, also in
     their `.help` and the inline help text at :275-276), not the binding's exact
     "Stop after this cell" / "Stop now".
4. `low_disk`: inline on the model's row, `hardware()` refreshed, and
   `needed_bytes - free_bytes` computed from the payload, never the message
   (`AppModel.swift:72-84`, `ModelsView.swift:147-168`).
5. Guided install re-verify: `engines()` re-requested on activation and screen appearance and
   from the button (`AppModel.swift:451-461`).
   - v5-app.md:100 vs app/Sources/OhYesMLX/RootView.swift:67 — the button reads
     **"Check Again"**, not "Check again".
6. Unsupported Mac absolute: `supported == false` shows only `unsupported` with its reason
   and nothing leads past it (`AppModel.swift:435-449`, `FullWindowStates.swift:44-66`).
7. `not_evicted`: exact line "Left on disk: <title> (<size>) — it was in use. You can remove
   it from Models." per repo (`AppModel.swift:273-280`).

---

## Part B — tests that cannot fail

Sample: the most recently changed tests first from `git log --since=2026-10-29 --name-only`,
by file recency, down through the ≥200-test boundary — `AppModelTests.swift` (36),
`DecodingTests.swift` (13), `FormatTests.swift` (5), `LauncherTests.swift` (13),
`tests/test_server.py` (91), `tests/test_smoke_clean_account.py` (32),
`tests/test_quickbench.py` (59) = 249 tests. Same-date files `HTTPBackendTests.swift` (10),
`SSETests.swift` (3), `LiveBackendTests.swift` (1) were included too: **263 tests examined**
across `tests/` and `app/Tests/`. Every flagged entry below was re-read against the code it
tests before listing.

**Flagged (2):**

- `tests/test_server.py::test_recommendations_leaves_measured_here_null_without_a_finished_quick_run`
  — why it cannot fail: its only assertion (`test_server.py:637`,
  `body["picks"][0]["measured_here"] is None`) is decided by the fake's own configuration
  (`"best": None` in the `summaries` stub, :630-632). A production with the `ended ==
  "finished"` filter deleted, or with the whole `measured_here` fill deleted —
  `recommend.pick` defaults the field to `None` (`recommend.py:84`) — passes it identically.
  The behavior in its name (a cancelled run never recommends) is guarded nowhere in it; the
  companion `test_recommendations_fills_measured_here_from_the_newest_quick_run` (:566) is
  the one that exercises the seam.

- `app/Tests/OhYesMLXKitTests/AppModelTests.swift::testExcludedModelCarriesItsReason`
  — why it cannot fail: both assertions (`AppModelTests.swift:628-629`) compare against the
  same constants the test itself built into the `ExcludedModel` it handed the StubBackend
  (:617-620), and `AppModel.recommendations` is assigned verbatim from the backend
  (`AppModel.swift:434`) — no transformation happens between fake and assertion, so the
  content assertions echo the fake's own return. (The fetch-and-store wiring is the only
  thing exercised; the row's content cannot fail.)

**Cleared (examined and not listable):** call-argument assertions on fakes
(`assert calls == [...]`, fake-transport/launcher argv and environment checks), refusal and
error-path tests, tests asserting concrete decoded or serialized output against literals,
and tests computing expectations through the production function itself (e.g. the pinned
composition test calling the real `recommend.exclusion_reason`). Notable near-misses
reviewed and kept out: `test_server.py::test_hardware_is_the_scan_as_json_with_integer_byte_counts`
(asserts the real `dataclasses.asdict` transformation), `test_quickbench.py::test_the_default_port_probe_asks_runtimes_and_reads_unknown_as_busy`
(asserts the negation of the stub's return), `test_quickbench.py::test_the_plan_estimate_is_per_cell_plus_the_download_at_the_constant_rate`
(pins contract constants against an arithmetic literal, not a re-implementation).






