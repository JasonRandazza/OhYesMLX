# S1 dossier — Security and trust boundaries (Fable 5.2 review, P0)

Scope as ordered: `ohyesmlx/server.py` (whole), the security-relevant ranges of `ohyesmlx/engines.py`,
`ohyesmlx/fetch.py` (whole security surface), `ohyesmlx/cli.py` (`app`, `_recover_startup`),
`ohyesmlx/runtimes.py` (`stop_orphaned_engines`, `stop_own_engines`, ledger, `_resolve_program`,
`_engine_env`), `ohyesmlx/__init__.py`, `app/Sources/OhYesMLXKit/{BackendLauncher,HTTPBackend,BackendToken}.swift`,
`scripts/build_app.sh`, `docs/threat-model.md` (all). All line numbers verified against the working tree at
`714e8f6` by `grep -n` / `sed -n` after graphify located each symbol. Nothing was changed; no suite was run
(the coordinator runs it); no server, engine or app was started.

Code is quoted at a line or two only; everything else is a pointer.

## 1. Map

### ohyesmlx/server.py (1051 lines — whole file in scope)

The localhost API. One guard, four read-only GETs, the job routes, SSE, cancel/abort, shutdown.

- `server.py:1-27` — module docstring: the API contract and the guard's rationale (the token is the control that matters; Host/Origin are defence in depth; no refusal echoes a header value or the token).
- `server.py:53-56` — `HOST = "127.0.0.1"`: the only bind address, never `0.0.0.0`/`::`.
- `server.py:58-90` — the caps: `HANDLER_TIMEOUT_S` 10 (:62), `KEEPALIVE_S` 15 (:66), `MAX_EVENTS` 10,000 (:70), `MAX_BODY_BYTES` 4,096 (:73), `JOB_SHUTDOWN_WAIT_S` 120 (:76), `JOB_KILL_GRACE_S` 15 (:81), `MAX_HANDLER_THREADS` 32 (:86), `MAX_STREAMS_PER_JOB` 4 (:90).
- `server.py:94-99` — `_ENDPOINTS`: the four GET routes, the one place the served set is written.
- `server.py:103-112` — `_JOB_ARGS` / `_JOB_FLAGS`: the closed arg set per job kind (one name key, `confirmed`, and quickbench's `osaurus` bool). No kind has a key naming a path, URL, command or version.
- `server.py:116` — `_JOB_PATH` regex: 16-hex id plus optional `/events` or `/cancel`; anything else 404.
- `server.py:122-145` — `_ERRORS`: the pinned code→(status, fixed message) table; `bad_args`/`internal` carry a message instead, never a header value or the token.
- `server.py:148-150` — `_event`: one server-authored event in the pinned job shape (`engines._job_event`).
- `server.py:153-232` — `_Job`: one accepted job — id, kind, validated args, events, condition, `cancel_requested`/`abort_requested`, stream slots. `append` (:176-202) is the sole writer; stores `done` last so the slot and the outcome cannot disagree; ends the job at the event cap (:185-195). `cancelled` (:209-211) and `aborted` (:213-219) are the probes modules read. `open_stream`/`close_stream` (:221-232) hold the per-job stream cap.
- `server.py:235-304` — `_Jobs`: every accepted job and the one running slot under one lock. `claim` (:247-254), `finished` (:256-259), `cancel_and_wait` (:261-292) — cancels install/download/quickbench, waits bounded, then `engines.kill_running_steps()` and `JOB_KILL_GRACE_S` more, then one `shutdown_abandoned` stderr line; `_wait_for_done` (:294-304) waits on the job condition, never the socket.
- `server.py:307-312` — `_job_code`: the last error event's code, for the job end line.
- `server.py:315-340` — `_args_problem`: the closed-args validator — allowed keys only, `confirmed` must be JSON `true`, flags must be JSON bools; names are the module's own refusal, never checked here.
- `server.py:343-344` — `_now`.
- `server.py:347-356` — `_served_path`: a path is logged only when it is a served route, else `<unknown>` (no client text reaches the log).
- `server.py:359-376` — `_log_refusal`: one JSON stderr line per refusal — code, method, `_served_path`, time; query string dropped; never a header value or the token.
- `server.py:379-386` — `_log_job`: one start and one end line per job; no token or header value.
- `server.py:389-404` — `_Handler` head: `protocol_version = "HTTP/1.0"` (one request per connection, load-bearing against smuggling/keep-alive slot holding, :399-402), `timeout = HANDLER_TIMEOUT_S` (:404).
- `server.py:408-410` — `log_message`: the access log is silenced.
- `server.py:414-433` — `do_GET`…`do_OPTIONS`: all seven methods through `_guarded`.
- `server.py:435-438` — `_guarded`: the guard runs first; the router sees the request only on pass.
- `server.py:440-458` — `_guard`: exact `Host` match (`127.0.0.1:<port>` or `localhost:<port>`, absent refused), any `Origin` refused, then `Authorization: Bearer <token>` via `hmac.compare_digest` on UTF-8 bytes (:456) so a non-ASCII header is a 401 and never a 500. Fixed order, fixed messages.
- `server.py:460-464` — `_refuse`: log + respond + `False`.
- `server.py:468-470` — `_path`: the request path without its query (query text is never logged).
- `server.py:472-498` — `_route`: exact paths; path resolved before method (unknown path is 404 even for POST); a module raise is `500 internal` carrying its message, no traceback.
- `server.py:500-510` — `_route_job_create`: `POST /jobs` only; a body that stopped arriving closes the connection instead of 500.
- `server.py:512-528` — `_route_job_action`: `/events` is GET-only, `/cancel` POST-only.
- `server.py:532-534` — `_get_hardware`: `dataclasses.asdict(scan())`.
- `server.py:536-558` — `_get_engines`: `detect_all` with `engines.install_plan` composed in; a plan that cannot be derived is a 500 naming the engine.
- `server.py:560-614` — `_get_recommendations`: `recommend.pick`/`exclusion_reason` over scan, detections, catalog, `fetch.downloaded`, and `quickbench.latest`'s `best` blocks keyed by the measured repo.
- `server.py:616-638` — `_get_quickbench_plan`: one query argument (`repo`), the module's own `ValueError` as `400 bad_args`.
- `server.py:640-646` — `_query`: query string as a mapping; read to answer, never echoed.
- `server.py:648-650` — `_macos_major`: integer before the first dot of `Hardware.macos`.
- `server.py:654-704` — `_post_job`: AC-1's order — Content-Type → Content-Length (413 before the body is read) → body → JSON → kind → args — then `secrets.token_hex(8)` job id (:681), `claim` the slot (409 `busy` naming the running job), start line to stderr, job thread, 202. A raise between claim and thread start stores `error`+`done` to free the slot (:691-703, T-04's fix).
- `server.py:706-720` — `_job_body`: 415 unless `application/json`; `Content-Length` must parse as an integer in `[0, 4096]` or 413; only then is the body read.
- `server.py:722-766` — `_run_job`: the one module call per kind — `install`/`download` get the name and literal `True`; `quickbench` gets `confirmed=True`, the `osaurus` bool, `cancel` and `abort` probes; `evict` gets the name and `True`. A raise is `error code internal` + `done`; `done` is guaranteed last (:759-763); the end line logs `ok`/`code`.
- `server.py:768-810` — `_post_job_cancel`: unknown job → 404, evict → `not_cancellable`, finished → `job_finished`, then `_cancel_now`; bodyless cancel sets `cancel_requested` only; `{"now": true}` additionally sets `abort_requested` and starts the injected `stop_engines` once on a daemon thread (both flags set under the job condition before the thread starts, so a module cannot observe one without the other); non-quickbench + now → `not_abortable`.
- `server.py:812-852` — `_cancel_now`: a cancel is bodyless only when neither `Content-Length` nor `Content-Type` is declared, or the declared length is integer zero; anything else goes through `_job_body`'s guards (same 415/413/400 as `POST /jobs`); the body must be `{}`-or-`{"now": true}` with no extra keys.
- `server.py:854-879` — `_get_job_events`: SSE entry — unknown job 404, bad `Last-Event-ID` 400, stream slot or 429; a disconnect ends the handler and never the job.
- `server.py:881-894` — `_last_event_id`: non-negative integer or `400 bad_event_id`.
- `server.py:896-935` — `_stream_job`: replays stored events after `last_seq`, waits on the job condition, writes `: keepalive` comments every `keepalive_s`, closes after `done`; the socket timeout bounds each write.
- `server.py:939-955` — `_respond`: the pinned error shape from `_ERRORS` (status and code cannot disagree).
- `server.py:957-965` — `_write_json`: UTF-8 JSON, `Cache-Control: no-store`, no `Access-Control-*` header ever.
- `server.py:968-999` — `_Server`: `daemon_threads`, one handler-thread slot per connection taken non-blocking before the thread exists (`process_request` :984-993), released in the thread's `finally` (:995-999). Past `MAX_HANDLER_THREADS` the connection is closed with no response and no thread.
- `server.py:1002-1051` — `make_server`: module seams default to the real functions (tests inject fakes); `token = token or secrets.token_urlsafe(32)` (:1050) — lives only on the server object and in the one stdout line the CLI prints; the socket is bound and listening before return.

### ohyesmlx/engines.py — security-relevant ranges (file is 1340 lines)

- `engines.py:327-337` — `_app_support` / `_engines_dir`: everything app-local derives from `ohyesmlx.app_support_dir`; `engines/` under it holds the venvs.
- `engines.py:340-351` — `_app_engine_venvs` / `_app_engine_scripts`: the version-suffixed venv roots a pip install creates (a second version never lands on a measured one).
- `engines.py:354-378` — `LAB_PATHS_NAME`, `_lab_paths_file`, `_lab_paths_beside`, `LAB_PATHS_FILE`: the machine-local lab-paths file beside the app's engines dir; `LAB_ENGINES = ("mlxlm", "optiq")` (:384) is the closed set of engines a lab path may name.
- `engines.py:387-411` — `check_lab_dir`: refuses a lab path that is not absolute, not a directory, not owned by this user, or group/other-writable; `os.stat` follows symlinks on purpose (:393-394) — the directory the process reads must be private.
- `engines.py:413-462` — `lab_paths`: the one reader for the machine-local file; missing file is `{}`; any other ill shape raises `ValueError` naming the file; keys limited to the onboarding engines and to `LAB_ENGINES`.
- `engines.py:465-496` — `record_lab_path`: the one writer; `check_lab_dir` before the file is read (:493); read-replace-write through `atomic_write_text` (:496); refuses an engine outside `LAB_ENGINES`.
- `engines.py:625-672` — the guided tables: `_GUIDED_TRACKS` (:633-637, release pages pinned to `TESTED_VERSIONS`, never `releases/latest`), `_release_url` (:640-643), `_GUIDED_ASSETS` (:651-655), `_GUIDED_SIZES` (:659-663), `_PIP_SOURCES` (:665-668), `_PIP_PACKAGES` (:672).
- `engines.py:674-687` — `CONSTRAINTS_DIR` / `constraints_path`: the committed, frozen dependency closure per engine per tested version.
- `engines.py:695-697` — `_PIN`, `_PIN_ONLY`, `_HASHED_PIN`: the only requirement grammars the installer accepts (a pin and sha256 hashes; no option lines).
- `engines.py:700-719` — `_requirement_lines`: continuation joining, shared with `scripts/hash_freeze.py`.
- `engines.py:722-746` — `_check_hashed_requirements`: refuses any line that is not `name==version` + `--hash=sha256:<64 hex>`; option lines (`--index-url`, `-r`, `-e`, …) refused explicitly (T-01's validator).
- `engines.py:749-776` — `_guided_plan`: a guided-download plan — two no-command steps, a pinned release page as `source_url`; nothing is fetched by the app.
- `engines.py:779-831` — `_command_plan`: the pip plan. Step 1 `["{python}", "-I", "-m", "venv", root]` (:797). Step 2 runs the venv's own python with `-I -m pip install --isolated --no-input --disable-pip-version-check --require-hashes --only-binary :all: --no-deps -r <constraints>` (:813-828). argv is constants plus `sys.executable`; no caller-supplied string exists (T-01/T-07's fix).
- `engines.py:834-863` — `install_plan`: pure data; the name check (`ONBOARDING_ENGINES`), the constraints-file existence check, `_check_hashed_requirements`, then the plan. An unknown name raises `ValueError` before anything runs.
- `engines.py:876-901` — the install constants: `DEFAULT_ENGINES_DIR`, `DEFAULT_INSTALL_LOG`, `STEP_TIMEOUT_S` 900, `OUTPUT_TAIL_BYTES` 4096, `LOW_DISK_FLOOR_BYTES` 2 GiB, `ALLOWED_DOWNLOAD_HOSTS = ("github.com", "pypi.org")` (:893), `POLL_S`/`POLL_TIMEOUT_S`, `TIMEOUT_EXIT_CODE`.
- `engines.py:904-928` — `EngineLocks`: one non-blocking in-process lock per engine (T-15: in-process only; P5-7 is the cross-process answer).
- `engines.py:931-945` — `_cap` / `_tail`: output bounded to 4 KiB before it reaches an event.
- `engines.py:948-974` — `_RUNNING_STEPS` registry (guarded by `_RUNNING_STEPS_LOCK`), `_kill_step_group` (SIGKILL the process group, :955-960), `kill_running_steps` (:963-974: kill every step this process started; nothing else is signalled).
- `engines.py:977-1008` — `_real_run`: argv list, never a shell string; `start_new_session=True`; spawn+register under the lock so a shutdown kill cannot miss a starting step; `communicate(timeout=timeout_s)`, on expiry the group is killed and `TIMEOUT_EXIT_CODE` returned.
- `engines.py:1011-1017` — `OPEN = "/usr/bin/open"` and `_real_open`: an absolute path so no PATH entry picks the opener (T-09); `subprocess.run` with no timeout (a browser open returns at once; see §5).
- `engines.py:1024-1036` — `_hermetic_env`: ambient minus `PYTHONPATH` and every `PIP_*` (T-07's first half).
- `engines.py:1054-1056` — `_url_allowed`: https + hostname in `ALLOWED_DOWNLOAD_HOSTS`; asked before a guided plan opens anything.
- `engines.py:1059-1095` — `_venv_root` (finds `-m venv` wherever the `-I` moved it), `_plan_engines_dir`, `_relocate` (points the plan's paths at the injected engines dir; identity in production).
- `engines.py:1098-1123` — `_rollback`: removes only paths whose `realpath` resolves inside the engines dir; a symlink that points out is refused and reported (AC-7), never followed.
- `engines.py:1126-1138` — `_job_event`: the pinned job-event shape every emitter builds in one place.
- `engines.py:1141-1156` — `_append_install_log`: append-only local JSONL (`open(log_path, "a")` — follows a symlink, noted threat-model §5.5).
- `engines.py:1159-1340` — `install`: consent → name/plan derivation (the name check is first, :1221-1230) → `confirmed` literal check (:1239) → already-installed (:1242) → lock (:1247) → disk (:1324-1333) → `run_steps` (:1250-1297: per-step cancel probe, `_relocate`, `_hermetic_env`, bounded output, rollback on failure, `record_lab_path` only after success at :1294-1295) or `run_guided` (:1299-1322: `_url_allowed` then `open_url`, poll detection with cancel probes). Lock released in `finally` (:1339-1340). No caller-supplied command, argv or URL is ever executed (AC-6).

### ohyesmlx/fetch.py — security surface (file is 1310 lines)

- `fetch.py:55-93` — constants: `HF_BASE = "https://huggingface.co"` (:56), `ALLOWED_HOSTS = ("huggingface.co", "hf.co")` (:57), `CHUNK_SIZE` 256 KiB, retry/backoff with `RETRY_AFTER_CEILING_S` 60 (:80, a hostile `Retry-After` cannot park the job), `TIMEOUT_S` 60 (:84), `DEFAULT_LEDGER`/`DEFAULT_LOG`/`DEFAULT_LOCK_DIR` under Application Support (:90-93).
- `fetch.py:95-98` — `LOCK_NAME = "download.lock"`: one download at a time across repos and processes (AC-7).
- `fetch.py:101-134` — `HostNotAllowed`, `LedgerError`, `PlannedFile`, `Planned` (pure description; no I/O).
- `fetch.py:137-149` — `default_cache_dir`: `HF_HUB_CACHE` or `~/.cache/huggingface/hub`; `HF_TOKEN`/`HF_ENDPOINT` deliberately never read (AC-14).
- `fetch.py:152-168` — `ledger_for`: the app's ledger for the default cache, a sibling `<realpath>.ohyesmlx-fetched.json` for any other (a scratch run never pollutes the app's ledger — `7393715`).
- `fetch.py:171-176` — `host_allowed`: exact `huggingface.co`/`hf.co` or dot-subdomain, case-folded.
- `fetch.py:179-187` — `url_allowed`: https + `host_allowed`; the one definition the redirect guard asks.
- `fetch.py:190-195` — `_check_inside`: a destination must resolve inside the directory it belongs to (`abspath`+`commonpath`, ValueError otherwise).
- `fetch.py:198-201` — `_repo_dir`: `models--<org>--<name>` — the one repo directory helper for `plan` and `evict` (T-13's fix).
- `fetch.py:204-269` — `plan`: pure; refuses a hostile literal before any caller opens a socket or writes — repo must match `catalog._REPO` (:213-214), revision must be a 40-hex commit (:215-216), each file path through `catalog.check_path` (:227, which refuses `..`), exactly one of sha256/git_oid and each must match its hex grammar (:228-239), blob and link `_check_inside` (:242-243), URL built from the validated literals with the path percent-quoted (:244-247).
- `fetch.py:272-298` — `downloaded`: size-and-link presence check only (cheap by design; `UAT-001` accepted); a hostile name propagates `ValueError`.
- `fetch.py:305-341` — `_LEDGER_LISTS` and `_ledger_load`: shape-checked strictly (lists of strings, revision, int bytes, numeric time); anything else is `LedgerError` — fail closed for `evict`.
- `fetch.py:344-346` — `_ledger_save`: atomic (`atomic_write_text`, mkstemp name — no cross-process collision).
- `fetch.py:354-405` — `_pid_alive`, `_acquire_lock` (`O_CREAT|O_EXCL`, mode `0644`, stale-pid reclaim by liveness probe then remove-and-retry — the §9 accepted check-then-remove race), `_release_lock` (removes only while it names this process).
- `fetch.py:413-443` — `_emitter` (job events logged locally via `engines._append_install_log` before emit), `_refuse` (an `error` never stands alone: `done` follows).
- `fetch.py:451-475` — `_GuardedRedirects` (every redirect hop re-checked against `url_allowed`; off-allowlist raises `HostNotAllowed`, :454-457) and `_real_open` (GET, guarded opener, 60 s timeout; `HostNotAllowed` is re-raised as itself so the retry loop cannot retry a refusal, :470-475).
- `fetch.py:550-556` — `_inside`: `realpath`+`commonpath` containment.
- `fetch.py:559-571` — `_link_conflicts` / `_link_refusal`: an existing snapshot link that is not the symlink to this blob refuses the run (`integrity_failed`, nothing overwritten) — both the pre-transfer pass and `link_all` use it (T-16's fix).
- `fetch.py:588-621` — `_sha256_file`, `_git_blob_sha1`, `_verify`: the one place the two verification rules live — LFS files by sha256, non-LFS by recomputed git blob sha1 over `"blob <len>\0"+bytes`; size checked first.
- `fetch.py:624-635` — `_make_dirs`: creates and records only the missing directories up to `stop`.
- `fetch.py:638-654` — `_referenced_blobs`: every blob any snapshot symlink in the cache resolves to (evict's guard against deleting a blob another repo still references).
- `fetch.py:662-718` — `download`: guard order is the refusal order — consent (:689), catalog id (:694-699), name shapes via `plan` (:701-704), cross-process lock (:706-708), then `_download`; ledger recorded in `finally` for whatever was created (:715-718).
- `fetch.py:721-749` — `_record`: merge-only ledger update; never drops a previous entry.
- `fetch.py:752-1178` — `_download`: ledger readable or `ledger_unreadable` (:759-762); pre-transfer pass — a conflicting snapshot link or a symlink blob refuses `integrity_failed` before any request (:782-809); an existing blob must match the catalog or nothing is overwritten (:798-806); disk guard on missing bytes × margin before any request (:816-827) and again per file (:1144-1155); `link_all` (:842-875) only after every file verifies (AC-15), each parent `_inside`-checked, relative symlinks (:868), `refs/main` last (:870-874); `finish` (:891-904) verifies then `os.replace` to the blob; `_fetch_file` (:906-1122) — `.incomplete` symlink refused (:908-914), Range resume with strict `Content-Range` checks (:1024-1055), over-length and short transfers refused, 403/410 re-resolved exactly once (:984-998), 401 gated-vs-missing distinguished (:965-976), final landed URL re-checked against `url_allowed` (:956-963), chunk loop refuses a body larger than the catalog (:1073-1075); `fetch_file` (:1124-1135) keeps failed residue on the ledger so evict can remove it.
- `fetch.py:1186-1310` — `evict`: consent (:1209), `_REPO` shape (:1213-1214), the download lock (:1216-1220), ledger must exist and parse (`missing_ok=False`, :1224-1226), repo must be listed (:1228-1232), **every** ledger path `_inside` that repo's own `models--` directory or `ledger_unreadable` and nothing removed (:1236-1244); links removed first, blobs only when no snapshot anywhere still references them (:1260-1277), directories only when empty (:1280-1288), ledger rewritten under the lock (:1290-1300), lock released in `finally` (:1309-1310).

### ohyesmlx/cli.py — the `app` surface

- `cli.py:823-838` — the `app` subcommand parser: `--port N` (default 0, ephemeral) and nothing else.
- `cli.py:1064-1105` — `_recover_startup`: before the launch line — `runtimes.stop_orphaned_engines()` (:1077-1080, failure is one stderr line), then the Osaurus pin recovery, only while the Osaurus app is not running (:1084-1092; a failure to probe reads as "running"), `osaurus_settings.recover` otherwise (:1093-1101); every outcome is one stderr line and none can stop the server.
- `cli.py:1108-1170` — `_app`: `ensure_app_support()` before the first write (:1137), `make_server(args.port)` with `bind_failed` stderr + exit 2 on OSError (:1139-1147), recovery before the launch line (:1151), `SIGTERM` handler and the stdin-EOF thread installed before the line is printed (:1156-1157), the launch line `{"port", "token"}` to stdout only (:1159-1163), `serve_forever`, and on every exit path `jobs.cancel_and_wait(JOB_SHUTDOWN_WAIT_S)` + `server_close()` (:1167-1169) so the port is released before the process is gone. The token never touches argv, a file or a log.
- `cli.py:1173-1181` — `_stop`: SIGTERM raises `KeyboardInterrupt` (a signal handler cannot call `shutdown()` from the serve thread).
- `cli.py:1184-1202` — `_stop_at_eof`: stdin EOF is the parent-death signal; read through `sys.stdin.buffer.raw` to avoid the CPython shutdown lock abort; then `listener.shutdown()`.

### ohyesmlx/runtimes.py — in-scope functions (file is 3811 lines)

- `runtimes.py:98-135` — stop constants (`STOP_TIMEOUT_S` 30, `TERM_GRACE_S` 10, `KILL_GRACE_S` 5), `LSOF = shutil.which("lsof") or "/usr/sbin/lsof"` (:125, the one remaining PATH-resolved tool — threat-model §7.4 T-09 residual), `PS = "/bin/ps"` (:129), `RUNNING_ENGINES_DIRNAME = "running-engines"` (:135).
- `runtimes.py:471-531` — `_engine_env`: the ambient env with each lab directory prefixed to PATH (:527-530); a lab path that is missing raises `RuntimeStartError` naming the engine (:516-521) and one that exists goes through `engines.check_lab_dir` (:522-525) before it can shape which binary runs; the machine-local file overrides the committed manifest's (always null) `lab_path`.
- `runtimes.py:534-566` — `_resolve_program`: the program token (first token not `env`/`K=V`) resolved against *env*'s PATH (:561); only when it does not resolve is `ENGINE_BUNDLE_EXECUTABLES` (:163) consulted, substituting an existing executable; a name that resolves is untouched.
- `runtimes.py:569-586` — `_run`: helper commands with `capture_output`, `timeout_s`, `stdin=DEVNULL`, `env=_engine_env()`; a missing lab copy refuses the start, not the probe.
- `runtimes.py:588-609` — `_spawn`: `start_new_session=True`, stdout/stderr to the engine's own log, `env=_engine_env()`, `_resolve_program` applied; `OSError` becomes `RuntimeStartError`.
- `runtimes.py:1608-1683` — `_await_exit`, `_kill_resident` (SIGKILL what a stop command left holding the port; Osaurus instances ignore SIGTERM, :1617-1635), `await_port_free` (:1638-1653), `_shutdown` (:1656-1683: listeners read before the stop command; the spawned pid's tree TERM→KILL; every other listener on the port killed by pid; then the port must be free).
- `runtimes.py:1686-1725` — the engine ledger file: `_ledger_path` (`<writable_root>/results/running-engines/<owner pid>.json`, :1686-1690), `_ledger_entries` (absent/unreadable holds none, :1693-1702), `_write_ledger` (temp + `os.replace`, file removed when empty, :1705-1725).
- `runtimes.py:1728-1744` — `_process_identity`: `(lstart, argv)` for a pid from one `ps -ww -o lstart=,args=` call — the evidence a recovered entry is compared against.
- `runtimes.py:1747-1783` — `_record_running_engine`: both spawned and serving pid with their identities, port and stop command; written after `cold_load_s` is taken (never inside a measurement).
- `runtimes.py:1786-1797` — `_forget_running_engine`: drops this pid's entry; a ledger write failure is one stderr line, never a failed stop.
- `runtimes.py:1800-1824` — `_recorded_identity` (which identity an entry recorded for a pid) and `_entry_stop_command` (the one parser for the recorded stop command).
- `runtimes.py:1827-1864` — `_stop_orphan`: an entry is stopped through `_shutdown` only when every listener on the port is a recorded pid with its recorded identity (or nothing listens and the spawned pid is alive with its identity); anything else — unreadable port, stranger listening, reused pid, identity mismatch — is dropped and never signalled.
- `runtimes.py:1867-1905` — `stop_orphaned_engines`: only files whose owner pid is dead; only `<digits>.json` is a ledger; entries through `_stop_orphan`; the file is removed once handled and kept (with a raise) when a stop failed, so a later launch retries.
- `runtimes.py:1908-1937` — `stop_own_engines`: reads only `<this pid>.json`, stops each entry through `_shutdown` **without** an identity re-check (the file is this process's own record), one stderr line per failing stop, returns the count. This is what `{"now": true}` starts.

### ohyesmlx/__init__.py (89 lines — whole file in scope)

- `__init__.py:24` — `APP_SUPPORT_MODE = 0o700`.
- `__init__.py:27-30` — `app_support_dir`: `~/Library/Application Support/OhYesMLX`.
- `__init__.py:33-40` — `_repo_root` / `_is_checkout` (a small function so tests can patch it).
- `__init__.py:43-52` — `writable_root`: the one directory the app may write in — the checkout root, else Application Support (T-03's fix; no write inside a packaged tree).
- `__init__.py:55-62` — `ensure_app_support`: create 0700 or tighten an existing directory to 0700 — mkdir's mode is umask-filtered, so the `chmod` is the guarantee (:58-61).
- `__init__.py:65-84` — `atomic_write_text`: mkstemp in the target's directory, write+fsync, `os.replace`; any failure removes the temp and re-raises.
- `__init__.py:87-89` — `stderr_json`: the one definition of a machine-readable stderr line.

### app/Sources/OhYesMLXKit/BackendLauncher.swift (566 lines)

- `BackendLauncher.swift:4-29` — `LaunchOutcome`, `QuitOutcome`, `QuitTiming` (grace 10 s, terminate 5 s, job bound 150 s — "Quit anyway", :28).
- `BackendLauncher.swift:31-50` — `LauncherProcess` / `BackendRunner` protocols.
- `BackendLauncher.swift:52-111` — `FoundationLauncherProcess` (`@unchecked Sendable`, NSLock around the termination handler); `run` passes argv/env/directory explicitly (:84-93); `kill` is `SIGKILL` to the child pid (:99-101).
- `BackendLauncher.swift:113-275` — `BackendLauncher`: `pathForChild = "/usr/bin:/bin:/usr/sbin:/sbin"` (:116, P5-9), `inheritedKeys = ["HOME","USER","LOGNAME","TMPDIR","LANG"]` (:117, env built not inherited); `start()` (:158-210) — `prepareAppSupport` (:243-254, created 0o700), interpreter resolution (:222-233, bundled python else `OYMLX_DEV_PYTHON`), `acquireLock` (:260-269, `flock(LOCK_EX|LOCK_NB)` on `app.lock`, P5-7 — a second launch never spawns), argv `[python, "-I", "-B", "-m", "ohyesmlx.cli", "app"]` (:185, no token in argv/env), launch line parsed from the first stdout line into `LaunchLine {port, token}` (:194-209, the token enters memory here and nowhere else).
- `BackendLauncher.swift:212-220` — `childEnvironment`: PATH plus the five inherited keys only.
- `BackendLauncher.swift:277-528` — `LaunchSession`: `startReading` drains stdout/stderr continuously (:318-329); `awaitLaunchLine` (30 s timeout, :331-352); `quitWait` (:380-398) — close stdin, wait; with a job running never signals within `jobBound`; else grace → `terminate` → `kill`; `abandon` (:405-415); `deliverLine` (:447-466) — the FIRST stdout line is the launch line, later lines never overwrite it (fix `ac0de1b`); stderr ring capped at 200 lines (:468-475); `handleTermination` (:501-516) releases the lock and fires the exit handler once.
- `BackendLauncher.swift:530-566` — `RunningBackend` (the `BackendRunner` the app holds), `LaunchLine` (`port`, `token` decoded from the one stdout line).

### app/Sources/OhYesMLXKit/HTTPBackend.swift (222 lines)

- `HTTPBackend.swift:3-49` — `HTTPTransport` and `URLSessionTransport` (`lines` drains a non-2xx body into a thrown `BackendError`).
- `HTTPBackend.swift:51-209` — `HTTPBackend`: GETs (:70-88), `startJob` (:90-96), `cancel` (:98-108, `{"now": true}` body only when now), `events` (:110-162, SSE reconnect loop; a poison frame advances `last` past its SSE id so it is never re-fetched — fix `ac0de1b`; `unknown_job` ends the loop), `makeRequest` (:171-191) — `http://127.0.0.1:<port>` only, `Authorization: Bearer <token.raw>` (:182) is the only place the raw token is read, `Content-Type` only when a body exists.
- `HTTPBackend.swift:199-208` — `error(data:status:)`: decodes the pinned error envelope; a body it cannot read is `bad_response`.

### app/Sources/OhYesMLXKit/BackendToken.swift (19 lines — whole file)

- `BackendToken.swift:3-19` — the token wrapper: `description`/`debugDescription`/`customMirror` all render `<redacted>` (:10-16); `raw` (:18) is internal and read only by `makeRequest`. P5-1's mechanism.

### scripts/build_app.sh (129 lines — signing in scope)

- `build_app.sh:24-37` — the pinned python-build-standalone interpreter: fetched by `scripts/fetch_python_standalone.sh`, whose `--identity` names `release=`, `url=`, `sha256=` (:26-29) — the hash is recorded in the SBOM (:115-116).
- `build_app.sh:39-52` — release Swift build; assemble `Contents/MacOS` + `Info.plist`.
- `build_app.sh:54-63` — interpreter copied into `Contents/Resources/python`; an assert proves `sys.prefix` resolves inside the bundle (:61-63); `-B` everywhere the bundled interpreter runs (P5-6).
- `build_app.sh:65-78` — `ohyesmlx` into bundled site-packages; the whole bundled tree precompiled with `--invalidation-mode unchecked-hash` pycs (:76-77) so no child interpreter writes bytecode into the signed bundle.
- `build_app.sh:80-86` — licence files shipped unmodified (`cmp`).
- `build_app.sh:88-108` — signing: every Mach-O under the bundled interpreter ad-hoc signed and `codesign --verify --strict` per file (:91-102), the app binary and the bundle signed `--force --sign -` (:105-106), then `codesign --verify --deep --strict --verbose=2` (:107). Ad-hoc only — no Developer ID, no notarization (D7, `docs/release/gatekeeper.md`).
- `build_app.sh:110-122` — SBOM via `scripts/make_sbom.py` (interpreter tag/url/sha256, ohyesmlx commit, Swift toolchain, pinned packages); re-verify after the SBOM step because it runs the bundled interpreter (:122).
- `build_app.sh:124-127` — `ditto` zip of the signed app.

### docs/threat-model.md (609 lines — all of it)

- `threat-model.md:23-42` — §1 scope (the same code this dossier maps; the Swift client was then unborn and lives in the §10 checklist).
- `threat-model.md:44-54` — §2 assets (the token, the HF cache, Osaurus config, `lab-paths.json`, the fetch ledger, consent, machine availability).
- `threat-model.md:56-65` — §3 actors (web page incl. DNS rebinding; same-user process "in, limited"; another local account; LAN peers out via the bind; compromised upstream in; root out).
- `threat-model.md:67-77` — §4 trust boundaries (browser→API rests on loopback + exact Host + Origin refusal + token; API→modules rests on the closed arg set; installer→pip rests on pinned constraints; downloader→HF rests on https+allowlist+hashes).
- `threat-model.md:79-182` — §5 entry points (5.1 routes, 5.2 job kinds, 5.3 subprocess calls, 5.4 outbound requests, 5.5 disk writes with symlink handling, 5.6 files a caller can influence, 5.7 the 102-hit inventory cross-check).
- `threat-model.md:184-231` — §6 live probes (2026-01-03… 2026-11-03): 26 probes incl. rebinding Host, Origin variants, `text/plain` simple request, oversize/short bodies, hostile repo ids, 50 SSE streams, 50 silent connections; real state hash-identical before/after.
- `threat-model.md:233-533` — §7 findings (rubric :235-243; table :268-289 T-01…T-16, R-01…R-04; detail :291-533).
- `threat-model.md:535-555` — §8 carried items and audit deferrals (14 rows).
- `threat-model.md:557-569` — §9 accepted risks (9 rows).
- `threat-model.md:571-609` — §10 packaging checklist P5-1…P5-12 and its status table at the Phase 5 first pass (P5-11 partly met/open; P5-5 clean-account pending).

## 2. Contracts

The rules that bind this code, as pointers with the binding sentences quoted.

**docs/interfaces/v5-onboarding.md** — the pinned API and job shapes.

- `v5-onboarding.md:163-169` (the app/`ohyesmlx app` section): "It binds `127.0.0.1` only — never `0.0.0.0` and never `::` — to an ephemeral port unless `--port N` is given, and before serving it writes exactly one line to stdout, `{"port": int, "token": str}`, where the token is `secrets.token_urlsafe(32)`, fresh per launch and never written to disk, argv or a log (the client holds the pipe)." And the guard order: "a `Host` that is not exactly `127.0.0.1:<port>` or `localhost:<port>` — including an absent one — is `403 bad_host`; any `Origin` header at all is `403 origin_refused`; anything but `Authorization: Bearer <token>` is `401 unauthorized`, compared as UTF-8 bytes with `hmac.compare_digest`…".
- `v5-onboarding.md:103-111` (**Job**): "`args` is the closed set `{"engine": str, "confirmed": true}` for `install`, `{"repo": str, "confirmed": true}` for `download` and `evict`, and `{"repo": str, "confirmed": true, "osaurus": bool}` for `quickbench`: an extra key, a missing key, a non-string name, a `confirmed` that is not JSON `true`, or an `osaurus` that is not a JSON bool is `400 bad_args` naming the key… an unknown name is the module's own refusal… delivered as the job's `error` and `done` events".
- `v5-onboarding.md:122` (**Job events**): the pinned event shape `{"seq", "type", "message", "fraction", "payload"}`; :129 the 10,000-event cap; :133-142 the cancel/abort semantics (evict `not_cancellable`, finished `job_finished`, `{"now": true}` = "Stop now" for quickbench only); :142-151 shutdown: cancel at the next check, wait ≤ 120 s, then the kill grace and one `{"error": {"code": "shutdown_abandoned", …}}` line.
- `v5-onboarding.md:160` (**Errors**): `{"error": {"code", "status", "message"}}` — "The server binds 127.0.0.1 only."; :180-181 the refusal line contract ("never a header value or the token, with the query string dropped, and with `path` written only [when served]").
- `v5-onboarding.md:67` (catalog): "`catalog.check_path(where, path)` is the one file-path guard" — what `fetch.plan` relies on for file paths.

**docs/interfaces/v5-app.md** — the launcher and client contract.

- `v5-app.md:43`: "**Argv:** `[python, "-I", "-B", "-m", "ohyesmlx.cli", "app"]` … Nothing else, and never the token (P5-2, P5-3)."
- `v5-app.md:44-45`: "**Environment:** built, not inherited: `PATH=/usr/bin:/bin:/usr/sbin:/sbin` (launchd's default, P5-9)…" plus the inherited keys.
- `v5-app.md:48-55`: the launch line is the first stdout line; "Stderr, and stdout after the launch line, are drained continuously from spawn so the child never blocks on a full pipe. Stdin is a pipe held open until quit (EOF is the backend's parent-death signal)."
- `v5-app.md:58-61` (P5-8): "While a job is running the wait is unbounded … never sends SIGKILL on its own; 150 s after stdin closed it offers **Quit anyway**, and only that [kills]".
- `v5-app.md:62-63` (P5-7): "**Single instance:** an exclusive `flock` on `<App Support>/OhYesMLX/app.lock` taken before the spawn; a second launch that cannot take it activates the running app…".
- `v5-app.md:69`: requests carry "`Authorization: Bearer <token>`, never an `Origin` header".
- `v5-app.md:90-91`: `inflightJob` in `UserDefaults`, cleared on `done`; a leftover at launch shows the interrupted banner with **Retry**.

**AGENTS.md** (repo root) — the rules that apply here.

- AGENTS.md:73: "Raw observations are never discarded. Summaries must stay recomputable from them." (binds the job event record and the install/fetch logs: append-only, capped output but never silently dropped history).
- AGENTS.md:80: "**No new dependency** without naming, in the commit message, what it replaces." (this whole surface is stdlib-only; `runtimes.py:312` even tests it).
- The coherence rule ("A fast cell that emits garbage is a failed cell") binds quickbench jobs this server starts, but quickbench's own gate is another section's scope.
- AGENTS.md "Stop and ask before adding a module, a subcommand, or a header pin": `app` is an approved subcommand (v5.0 approved surfaces, AGENTS.md hard boundaries).

**docs/threat-model.md** — rows that name this code (the whole file is mapped above; the binding ones):

- §4 (`:67-77`): the six trust boundaries and the assumption each rests on — e.g. "The token stops blind cross-site writes, because a cross-site `<img>` or navigation carries no `Origin` and a correct `Host`".
- §7.3 (`:268-289`): the 16 findings + 4 rejected with verdicts and dispositions (see §3 below).
- §9 (`:557-569`): the accepted risks — no 401 lockout, no TLS on loopback, finished jobs kept in memory, same-user HF-cache symlink races (T-14), "Anyone holding the token can submit consented jobs — by design", the `_acquire_lock` stale-reclaim race.
- §10 (`:571-609`): P5-1…P5-12 bind the Swift client and the packaging; the status table at `:596-609` is the current claim (P5-11 **open**; P5-5 clean-account run pending).

**docs/design/phase5/DESIGN.md** — app sections only. Little security content: §4.6 requires "the reason next to every job-starting control" (consent UX), §5 the accessibility floor, §6 states what the file does not decide. No security boundary lives here; the consent/stop copy it designs is what P5-8/P5-10 surface.

## 3. Already known — do not re-report

Format: `- <claim> — <source> — fixed <sha> | accepted | deferred | open`.

**threat-model §7.3 findings (all verified against code at 045-01; dispositions as tested):**

- T-01: pip installs pinned by version, not hash — threat-model :293-315 — fixed `a031ad4` (full-hash requirements, `--require-hashes --only-binary :all: --no-deps`, `_check_hashed_requirements`; pygame source build removed `369f180`).
- T-02: an interrupted app left engines running, an Osaurus pin unrestored, a pip step without rollback — :335-363 — fixed `9bc9388` (startup recovery + running-engines ledger + kill-grace); (d) withdrawn.
- T-03: backend wrote inside its own package tree — :377-390 — fixed `4b35ef8` (`writable_root`; P5-6).
- T-04: the job slot could leak for the life of the process — :392-401 — fixed `4b35ef8`.
- T-05: an Osaurus pin clobbered mid-cell was measured as pinned — :365-375 — fixed `9bc9388` (drift check + `during-run/` copy); residual: the check does not run when the cell itself raises (accepted, §9/T-05 residual).
- T-06: `evict` raced a download over the ledger — :317-333 — fixed `fb4e61c` (evict under `download.lock`).
- T-07: installer environment (pip config, `PYTHONHOME`, no `-I`) — :403-415 — fixed `a031ad4` (`-I` both steps, `--isolated`).
- T-08: unbounded handler threads and job streams — :417-427 — fixed `4b35ef8` (32 handler slots, 4 streams/job); residual accepted in §9 ("a local account filling the 32 handler slots").
- T-09: bare command names on a lab-prefixed PATH — :429-438 — fixed `4b35ef8` (absolute `/bin/ps`, `/usr/sbin/sysctl`, `/usr/bin/sw_vers`, `/usr/sbin/ioreg`, `/usr/bin/open`; `hardware._run` timeout); **residual open**: `runtimes.LSOF` is still `shutil.which("lsof")` at import (`runtimes.py:125`) — named at :429 ("not part of this finding") and again in 045-02a "Known gaps" and 045-02b "Still open, carried".
- T-10: file modes (other local accounts could read logs/ledger) — :440-446 — fixed `4b35ef8` (`ensure_app_support` 0700; P5-5).
- T-11: a token pasted into a URL path reached the refusal log — :448-454 — fixed `4b35ef8` (`_served_path`).
- T-12: `lab-paths.json` values only checked as non-empty strings — :456-466 — fixed `a031ad4` (`check_lab_dir` at record and start).
- T-13: `evict` trusted a tampered ledger against the whole cache root — :468-479 — fixed `fb4e61c` (per-repo `_repo_dir` containment); note :476-479: the host's real `fetched.json` then held scratch residue, cleaned later (`743ada3` "host ledger residue removed").
- T-14: same-user symlink races in the HF cache — :481-487 — accepted (§9 :564: fixing fully needs `O_NOFOLLOW`/`openat` throughout `fetch`).
- T-15: in-process install lock; two app installs could collide — :489-494 — deferred to checklist P5-7 (single instance), which the §10 status table marks **Met** (`flock` on `app.lock`, `101df7c` bundle).
- T-16: snapshot-conflict check ran after the transfer — :496-506 — fixed `fb4e61c` (`_link_conflicts` in the pre-transfer pass).
- R-01 (`_REPO` admits `.`/`..`, no traversal) — :508-514 — rejected with reasoning (org/name one component, catalog-only names, `check_path` for file paths).
- R-02 (guard bypass candidates: all seven `do_*` guarded, TRACE/CONNECT 501, absolute-form 404, chunked body 413, HTTP/1.0 closes) — :516-523 — rejected.
- R-03 (TLS under a bundled Python fails closed) — :525-530 — rejected; checklist P5-4, status **Met** (`check_bundle` P5-4, macOS `/etc/ssl/cert.pem`).
- R-04 (`PYTHONHTTPSVERIFY=0` is same-user only and content is hash-gated) — :532-533 — rejected.

**threat-model §8 carried / §9 accepted (S1-relevant rows):**

- UAT-001: `fetch.downloaded` compares sizes, a size mismatch reads as "not ours" — :547 — accepted (Jason 2026-11-03); the copy fix P5-11 is — open (§10 status: "Partly met … needs a backend field").
- No lockout on repeated 401s — :548, :561 — accepted (256-bit token, loopback).
- No TLS on loopback — :560, :562 — accepted.
- Finished jobs kept in memory — :551, :563 — accepted.
- A local account filling the 32 handler slots — :568 — accepted (10 s timeout; the permanent leak T-04 is closed).
- `_acquire_lock` stale-reclaim check-then-remove race — :569 — accepted (crash + two-process race at one instant).
- DMG checksum/signature verification — :553 — accepted (the app never downloads a binary; the user installs from the vendor page).
- A pip step outliving a shutdown / per-job stream cap / Osaurus mid-run rewrite / post-transfer conflict check — :540-544 — fixed in 045-02 (the T-rows above).
- SBOM/dependency provenance — :555 → P5-12 — fixed (`make_sbom.py`, `101df7c`; status **Met**).

**STATE.md (Deferred Issues / Blockers) touching this code:**

- P5-11: the app cannot offer "Re-download" (`Pick.downloaded` is one bool) — STATE Deferred Issues — deferred (also "in the Fable S4 scope").
- Disk tightened to 40 GiB free (2026-11-13) — STATE Deferred Issues — deferred (relevant to download's disk guard behaviour only marginally).
- All other deferred issues (README, run-dir schema, osaurus-pin script consolidation, MMLU arm) and the resolved blockers (sampler penalties, hero-model re-serialisation, prompt-cache pin) concern measurement, not this surface.

**Phase-5 wave-1/2 review logs (`.paul/review/2026-11-14-phase5-w1`, `-w2`) — S1-relevant findings and their fixes:**

- Cancel body detection: `Content-Type` with no `Content-Length` answered 202 and ignored `{"now": true}`; `Content-Length: 00` gave 400 — w1 spec.log item 1 — fixed `ac0de1b` (now `_cancel_now` keys bodyless on *both* headers absent and parses the length as an integer: `test_a_cancel_body_gets_the_same_guard_codes_as_post_jobs`, `test_a_cancel_body_is_detected_by_its_headers_and_its_length_as_an_integer`).
- Poison SSE frame re-fetched forever (`HTTPBackend.events` never advanced `last`) — w1 standards.log — fixed `ac0de1b` (frame id advances `last`).
- Two stdout lines before the await lost the launch line (`BackendLauncher.deliverLine`) — w1 standards.log — fixed `ac0de1b` ("The FIRST stdout line is the launch line").
- Wave-2 (w2 standards.log) items 1-10 concern UI copy, `AppModel` state and duplicate helpers; none is a trust-boundary defect; their fixes "landed in the 05-06 commit's app tree" (`fee692b` → `101df7c`). The `AppModel.summary` leak across job kinds (w2 item 4) is a state bug, not a security one, and is in the S4/S5 area.
- Threat-model P5-1…P5-12: "no breach found" in both wave reviews (w1/w2 standards.log closers).

**Earlier review (`.paul/review/2026-09-23/*`):** predates `server.py`, `fetch.py`, `engines.py` (zero mentions); its `runtimes.py`/`cli.py` findings are measurement failure-paths with line numbers now stale (it reviewed the pre-v5 harness). Nothing there names the S1 functions (`_engine_env`, `_resolve_program`, the ledger, the stoppers arrived with 045-02a/045-03). Not re-listed.

**`.paul/review/fable-5.2/orders/W1-sweep.log`** (in flight at dossier time): an interface-docs sweep; its only recorded finding so far is `recommend._rank` ordering drift — not S1 scope. No S1 finding yet.

**045-02a/02b SUMMARY "Known gaps / still open, carried" that land in S1:**

- `runtimes.LSOF` via `shutil.which` on the ambient PATH at import — 045-02a "Known gaps", 045-02b "still open, carried" — open (see T-09 residual).
- "The four atomic-write copies (`osaurus_settings`, `runtimes`, `measure`, `quickbench`)" — PHASE-4.5 "Carried forward" — open (one-definition drift risk; `__init__.atomic_write_text` is the reference).
- Global pip config under `--isolated` accepted — PHASE-4.5 carried + §9 — accepted.
- The lock-reclaim race — §9 — accepted (above).
- `/engines` reports vMLX installed for an account that cannot execute its bundle (multi-user Macs) — PHASE-4.5 carried — open (availability, not integrity).
- `ensure_app_support` before the bind means an unwritable HOME is a traceback, not the `bind_failed` line — 045-02a "Known gaps" — open (minor; the app always has a writable HOME).
- The host's polluted `fetched.json` entry (scratch caches from 2026-11-03) — 045-02b UNIFY — the mechanism is fixed (`7393715`); "cleaning it is Jason's call" — open (housekeeping).
- `test_server` thread-cap test is a load-sensitive flake (once in four runs) — 045-02b UNIFY — open (test reliability, not a code defect).
- `/etc/sudoers.d/oymlxtest` remains until Jason removes it — 045-03 Deviations — open (host hygiene, outside the repo).

## 4. Hotspots

The ranges where a defect would hurt most. Test column names the test that would fail if it broke (details in §6).

1. `server.py:440-458` — `_guard`: the only thing between any web page and every endpoint. A defect here is unauthenticated installs/downloads/evictions on the user's Mac. — tests: `test_server.py::test_a_foreign_host_is_403_bad_host` … `test_the_guard_runs_before_the_router` (:199-297), `::test_every_job_route_is_behind_the_04_01_guard` (:1778).
2. `server.py:1002-1051` — `make_server` token generation and custody (`secrets.token_urlsafe(32)`, object + one stdout line only): a leak or a predictable token voids the boundary for every other local account. — `test_server.py::test_each_launch_gets_its_own_token` (:187), `::test_no_response_or_log_echoes_the_token_or_a_header_value` (:298).
3. `server.py:103-145` + `315-340` — the closed job-args set and `_args_problem`: the one choke point keeping a request from naming a path, URL, command or version; a defect makes `POST /jobs` an arbitrary-execution surface. — `test_server.py::test_quickbench_args_are_a_closed_set` (:1099), `::test_bad_args_is_400_naming_the_key_and_starts_no_job` (:1126), `::test_an_unknown_kind_is_400_bad_kind` (:1145).
4. `server.py:706-720` — `_job_body`: Content-Length trusted only after integer parse and the 4 KiB cap, before any read; a defect is request-body memory growth or smuggling past the cap. — `test_server.py::test_a_missing_or_non_integer_content_length_is_413_before_the_body` (:1172), `::test_an_oversize_body_is_413_and_is_never_read` (:1186).
5. `server.py:768-852` — cancel/abort: `{"now": true}` starts a process-stopping thread (`stop_own_engines` → `_shutdown` → SIGTERM/SIGKILL on real pids); a defect kills engines outside a job or lets a stale request signal processes. — `test_server.py::test_stop_now_sets_both_flags_starts_one_stop_and_the_job_ends_cancelled` (:2060) through `::test_a_second_stop_now_answers_202_without_a_second_stop` (:2294).
6. `server.py:261-292` + `engines.py:948-974` — shutdown: `cancel_and_wait` → `kill_running_steps` kills process groups; a registry or grouping defect signals the wrong tree. — `test_server.py::test_cancel_and_wait_past_its_bound_kills_the_steps_then_waits_for_done` (:1694), `::test_the_post_kill_wait_is_bounded_by_the_kill_grace` (:1727), `engines` via `test_engines.py::test_each_step_is_bounded_by_the_injected_timeout` (:948).
7. `server.py:968-999` + `58-90` — the handler/stream caps: availability of the API itself; a leak is a wedged backend (T-04/T-08's memory). — `test_server.py::test_the_handler_thread_cap_closes_the_extra_connection_and_releases_at_timeout` (:1870), `::test_a_fifth_stream_on_one_job_is_429_and_a_freed_slot_admits_another` (:1899) (note: the thread-cap test is load-sensitive flaky per 045-02b UNIFY).
8. `engines.py:779-831` — `_command_plan`'s pip argv (`-I`, `--isolated`, `--require-hashes`, `--only-binary :all:`, `--no-deps`): a dropped flag reopens T-01/T-07 — a compromised upstream file executing at install. — `test_engines.py::test_the_committed_constraints_files_are_fully_hashed_and_pin_their_own_engine` (:365), `::test_no_plan_step_is_a_shell_string_and_none_uses_sudo` (:1199), `::test_steps_run_with_a_hermetic_env_that_drops_pythonpath_and_pip` (:958).
9. `engines.py:722-746` — `_check_hashed_requirements`: the validator that makes `--require-hashes` mean something; a grammar gap admits an option line (`-r`, `--index-url`) into pip's argv. — `test_engines.py::test_the_hashed_requirements_validator_refuses_anything_but_hashed_pins` (:404), `::test_a_file_ending_in_a_continuation_is_refused_as_unhashed` (:418).
10. `engines.py:1250-1295` — `run_steps`'s rollback and lab-path record: `_rollback` deletes paths; a containment defect deletes a user directory; recording a lab path wrong puts attacker-adjacent code on PATH forever. — `test_engines.py::test_rollback_refuses_a_path_that_resolves_outside_the_engines_dir` (:1135), `::test_a_venv_that_existed_before_the_call_is_never_removed` (:1116), `::test_a_successful_pip_install_records_its_venv_bin_and_engine_env_prefixes_it` (:777).
11. `engines.py:1299-1306` — `run_guided`'s `_url_allowed` before `open_url`: the only thing keeping `open` off a hostile URL. — `test_engines.py::test_a_url_outside_the_https_allowlist_is_refused_before_the_opener` (:1246), `::test_guided_source_urls_pin_the_three_tested_releases_and_never_latest` (:251).
12. `engines.py:387-496` — `check_lab_dir` / `record_lab_path`: lab dirs decide which `mlx_lm.server`/`optiq` binary runs; a writable-by-others directory is code execution of the user's choosing at the next cell. — `test_engines.py::test_record_lab_path_refuses_a_directory_that_must_not_join_path` (:897) … `::test_record_lab_path_refuses_a_lab_dir_owned_by_another_user` (:928); `test_runtimes.py::test_a_lab_path_owned_by_another_user_is_refused_at_start` (:3659).
13. `fetch.py:171-187` + `451-475` — the URL/host allowlist and per-hop redirect guard: the trust boundary to the internet; a defect is a fetch from (and a write of) attacker-chosen content. — `test_fetch.py::test_allowed_hosts`/`::test_refused_hosts` (:643-659), `::test_a_final_url_outside_the_allowlist_is_refused` (:663), `::test_an_http_final_url_is_refused` (:679), `::test_no_request_carries_an_authorization_header` (:960).
14. `fetch.py:204-269` — `plan`'s name validation (repo/revision/path/hash grammars, `_check_inside`): every later path and URL is built from these literals; a `..` or a crafted hash here is path traversal in the HF cache. — `test_fetch.py::test_plan_refuses_a_hostile_literal` (:380), `::test_download_refuses_a_bad_name_before_any_request_or_write` (:385).
15. `fetch.py:605-621` — `_verify` (sha256 / git-blob-sha1): the only gate between a downloaded byte and a "verified" weight file a model will load. — `test_fetch.py::test_checksum_mismatch_removes_the_partial_and_links_nothing` (:493), `::test_an_existing_non_lfs_blob_of_the_right_size_but_wrong_bytes_is_refused` (:839).
16. `fetch.py:906-1122` — `_fetch_file`'s write path (`.incomplete` symlink refusal, Range/Content-Range arithmetic, over-length refusal): writes into the user's HF cache from a remote body; a defect is cache corruption or a write through a planted symlink (T-14's residual). — `test_fetch.py::test_a_206_starting_elsewhere_is_refused` (:552), `::test_a_content_length_larger_than_the_catalog_is_refused` (:904), `::test_a_body_larger_than_the_catalog_is_refused` (:918), `::test_a_content_range_with_the_wrong_total_is_refused` (:936).
17. `fetch.py:1186-1310` — `evict`: the only destructive operation in the app; its ledger containment is what keeps it from deleting a user's file. — `test_fetch.py::test_evict_removes_exactly_the_ledger_paths` (:1137), `::test_evict_refuses_a_ledger_path_that_resolves_outside_the_cache` (:1231), `::test_evict_refuses_a_ledger_path_outside_that_repos_own_directory` (:1264), `::test_evict_refuses_a_corrupt_ledger` (:1213).
18. `runtimes.py:1827-1905` — `_stop_orphan` / `stop_orphaned_engines`: signals pids found in a ledger file; the identity gate is the only thing separating "our dead run's engine" from "a stranger's process". — `test_runtimes.py::test_a_dead_owners_matching_engine_is_stopped_through_shutdown` (:3827), `::test_a_reused_pid_is_dropped_and_never_signalled` (:4002), `::test_a_stranger_listening_on_the_recorded_port_is_dropped` (:3925), `::test_a_listener_whose_recorded_identity_no_longer_matches_is_dropped` (:3956).
19. `runtimes.py:1908-1937` + `1656-1683` — `stop_own_engines` / `_shutdown`: "Stop now" SIGTERMs then SIGKILLs real process trees, keyed by a ledger this process wrote — no identity re-check on this path (see §7 Q3). — `test_runtimes.py::test_stop_own_engines_stops_only_this_processes_entries_and_never_writes` (:4103), `::test_stop_kills_the_process_the_launcher_left_holding_the_weights` (:2823).
20. `cli.py:1108-1170` + `app/Sources/OhYesMLXKit/BackendLauncher.swift:158-220` — the launch seam: where the token is minted, printed, parsed and held; and where a second instance is refused (`flock`). A defect leaks the token or spawns two backends (T-15/T-06's premise). — `test_cli.py::test_the_app_creates_app_support_before_it_serves` (:1166), `::test_the_app_serves_hardware_until_its_stdin_closes` (:1412); `app/Tests/OhYesMLXKitTests/LauncherTests.swift::testArgvEnvironmentAndDirectory` (:187), `::testSecondLauncherIsAlreadyRunningAndSpawnsNothing` (:418), `HTTPBackendTests.swift::testTokenIsRedactedInEveryDescription` (:260).

## 5. Mechanical scan

Grep results with locations; one line each; "none" = no hits. Python scope: `server.py`, `engines.py`, `fetch.py`, `cli.py`, `runtimes.py`, `__init__.py`. Swift scope: the three S1 files. Not judged, only listed.

**Python, the standard patterns:**

- `shell=True` — none.
- `os.system` — none.
- `eval(` — none.
- `exec(` — none (the only `exec`-family word is `os.exec`-free; `execv` appears nowhere in these files).
- `pickle` — code: none. One docstring mention: `runtimes.py:3648` ("the pickled session bank", MTPLX wording).
- bare `except:` — none.
- `except Exception: pass` — none. The `pass`-only excepts are all narrow: `server.py:832` (`ValueError` in the length parse), `engines.py:959` (`ProcessLookupError, PermissionError` on a gone group), `fetch.py:404,529,584` (`OSError` on lock release/close/remove), `runtimes.py:620` (`OSError` in `_process_alive`), `runtimes.py:1604` (`OSError, RuntimeStopError`).
- `chmod` — `ohyesmlx/__init__.py:61` (`path.chmod(APP_SUPPORT_MODE)` — the 0700 guarantee). Swift counterpart: `BackendLauncher.swift:250` `[.posixPermissions: 0o700]` at directory creation.
- `tempfile.mktemp` — none (`mkstemp` is used instead: `__init__.py:75`).
- `open(` with `w`/`a` on a path built from input — `fetch.py:872` (`refs/main` "w"; path components are `plan`-validated literals), `fetch.py:1066` (`<blob>.incomplete` "ab"/"wb"; a symlink there is refused at :908-914 first), `engines.py:1155` (install log "a"; follows a symlink — noted `threat-model.md:136`), `runtimes.py:596` (engine log "ab"), `runtimes.py:1717` (ledger temp "w"), `__init__.py:77` (atomic temp). All destinations derive from `app_support_dir`/`writable_root` or validated cache paths.
- `subprocess` without a timeout — `engines.py:1017` `subprocess.run([OPEN, url], check=False, stdin=DEVNULL)`: no `timeout=` (the only unbounded one; `/usr/bin/open` returns immediately, but the flag is absent as written). Bounded: `engines.py:988` (`communicate(timeout=timeout_s)`), `runtimes.py:573` (`timeout=timeout_s`). Unbounded by design (a detached server): `runtimes.py:599` (`_spawn`, `start_new_session`, logged).
- `json.loads` on unbounded input — request bodies: `server.py:665,838` (capped at 4,096 bytes by `_job_body` first). File reads with no size bound: `engines.py:79` (committed `engines-tested.json`), `engines.py:442` (`lab-paths.json`), `fetch.py:320` (fetch ledger), `runtimes.py:939` (JSON object read from a log), `runtimes.py:1696` (engine ledger). Length-bounded: `runtimes.py:1134` (`handle.read(length)`). Stream reads from loopback engines / helper output: `runtimes.py:1432,1455,2668`.

**Python, the extra S1 patterns:**

- `Origin` — `server.py:452` (any `Origin` header refused), `server.py:124` (`origin_refused` code). Nothing else reads it.
- `Host` — `server.py:450` (exact match on `127.0.0.1:<port>` / `localhost:<port>`).
- `Authorization` — `server.py:454-456` (the only Python reader); `HTTPBackend.swift:182` (the only writer). `fetch` sends none by design (`fetch.py:23`, test `test_fetch.py:960`).
- `compare_digest` — `server.py:456` (UTF-8 bytes), rationale at :446-447.
- `0o7` — `ohyesmlx/__init__.py:24` (`APP_SUPPORT_MODE = 0o700`), `BackendLauncher.swift:250`.
- `umask` — `ohyesmlx/__init__.py:58` (comment explaining the chmod); `threat-model.md:130` notes everything else is created with the process umask.
- `os.replace` — `fetch.py:902` (incomplete → blob), `runtimes.py:1722` (engine ledger), `__init__.py:81` (atomic_write_text). `fetch._ledger_save` goes through `atomic_write_text`.
- `symlink` — create: `fetch.py:868` (relative link), `runtimes.py:1573` (oMLX scratch catalog). Refuse-to-write-through: `fetch.py:791-797` (blob), `fetch.py:908-914` (`.incomplete`). Checked-before-unlink: `runtimes.py:1583`. Removal-never-follows: `engines.py:1116-1121`.
- `realpath` — the containment primitives: `engines.py:1105-1108` (`_rollback`), `fetch.py:165-167,551-553` (`ledger_for`, `_inside`), `fetch.py:563` (`_link_conflicts`), `fetch.py:653,1268` (reference scan), plus detection use in `engines.py:219,267,293,504-516`.
- `..` — no `..` literal is used in a path build; the only occurrence is the refusal text in `catalog.py:155` ("walks up with `'..'`", `check_path`).
- `Content-Length` — request side: `server.py:713,825-831` (integer parse, zero-class handling; error text :134). Response side: `server.py:962`. Remote side: `fetch.py:1024` (against the catalog's size).
- `--require-hashes` — `engines.py:822` (argv), rationale :725-746.
- `--isolated` — `engines.py:819` (argv), rationale :802.
- `-I` — `engines.py:797` (venv step), `engines.py:815` (pip step), `BackendLauncher.swift:185` (child argv), `build_app.sh:33,61,66` (bundled interpreter runs).
- `PATH` — construction: `runtimes.py:527-530` (lab prefixes first), `BackendLauncher.swift:116,213` (fixed launchd default). Resolution against it: `runtimes.py:561` (`shutil.which(token, path=env PATH)`). Constants immune to it: `runtimes.py:125` (`LSOF = shutil.which("lsof") or "/usr/sbin/lsof"` — resolved once at import; the one PATH-resolved tool left), `runtimes.py:129` (`PS = "/bin/ps"`), `engines.py:1013` (`OPEN = "/usr/bin/open"`).

**Swift (BackendLauncher, HTTPBackend, BackendToken):**

- `try!` — none.
- `!` force-unwrap on optionals from I/O — none (all I/O values are `if let`/`guard let`; `process.processIdentifier` at :100 is a non-optional).
- `fatalError` — none.
- `DispatchQueue.main.sync` — none.
- `@unchecked Sendable` — `BackendLauncher.swift:52,113,277,530` (four classes; each guards its mutable state with `NSLock`, visible at :57,:71-81,:281,:519).
- `Task {` without cancellation handling — `HTTPBackend.swift:36` (line reader; `onTermination` cancels the task, :46) and `HTTPBackend.swift:112` (SSE loop; `onTermination` :160, `is CancellationError` :148, `Task.isCancelled` :151). Both wire cancellation; neither is a bare detached task.
- `print(` — none (the token's redaction is structural: `BackendToken.swift:10-16`).

**scripts/build_app.sh:**

- Signing: `codesign --force --sign -` ad-hoc at :95 (each bundled Mach-O), :105 (app binary), :106 (bundle); verification at :97 (`--strict` per file), :107 (`--verify --deep --strict --verbose=2`), :122 (re-verify after the SBOM step). No Developer ID, no notarization (:10, D7).
- Network: none in this file; the interpreter fetch lives in `scripts/fetch_python_standalone.sh`, which reports `url=`/`sha256=` for the SBOM (:26-29, :115-116).
- `chmod` / `eval` / backtick command substitution — none (`$()` only, :13, :25-29, :66, :89, :111).

## 6. Test inventory

Per hotspot (numbering matches §4), the tests that would fail if it broke. Suite layout: `tests/test_server.py` (91 tests), `test_fetch.py` (81), `test_engines.py` (100), `test_runtimes.py` (211), `test_cli.py` (54), `test_paths.py` (10); Swift in `app/Tests/OhYesMLXKitTests/`. The coordinator runs the suites; counts here are `def test` tallies, not run results.

1. `_guard` — `tests/test_server.py::test_a_foreign_host_is_403_bad_host` (:199), `::test_an_absent_host_is_403_bad_host` (:210), `::test_both_exact_host_forms_are_accepted` (:220), `::test_any_origin_header_is_403_origin_refused` (:228), `::test_a_missing_or_wrong_token_is_401_unauthorized` (:238), `::test_the_token_is_compared_as_bytes_so_non_ascii_is_401_not_500` (:249), `::test_the_guard_runs_before_the_router` (:259), `::test_a_refused_request_reaches_no_handler_and_runs_no_module` (:272), `::test_every_job_route_is_behind_the_04_01_guard` (:1778), `::test_a_job_response_carries_no_cors_header` (:1801).
2. Token custody — `tests/test_server.py::test_each_launch_gets_its_own_token` (:187), `::test_no_response_or_log_echoes_the_token_or_a_header_value` (:298), `::test_a_refusal_writes_one_stderr_line_and_a_served_request_writes_nothing` (:771), `::test_the_refusal_line_carries_no_header_value_and_no_query` (:787), `::test_a_refused_unknown_path_is_logged_as_unknown_not_echoed` (:1947); Swift: `app/Tests/OhYesMLXKitTests/HTTPBackendTests.swift::testTokenIsRedactedInEveryDescription` (:260), `LauncherTests.swift::testArgvEnvironmentAndDirectory` (:187, asserts the argv/env carry no token).
3. Closed args — `tests/test_server.py::test_download_and_evict_take_a_repo_name` (:1071), `::test_quickbench_args_are_a_closed_set` (:1099), `::test_bad_args_is_400_naming_the_key_and_starts_no_job` (:1126), `::test_an_unknown_kind_is_400_bad_kind` (:1145), `::test_the_modules_own_refusal_arrives_as_its_error_and_done_events` (:1233).
4. Body guard — `tests/test_server.py::test_a_missing_or_non_integer_content_length_is_413_before_the_body` (:1172), `::test_an_oversize_body_is_413_and_is_never_read` (:1186), `::test_a_body_of_exactly_the_limit_is_accepted` (:1201), `::test_invalid_json_is_400_bad_json` (:1221), `::test_a_cancel_body_gets_the_same_guard_codes_as_post_jobs` (:2189), `::test_a_cancel_body_is_detected_by_its_headers_and_its_length_as_an_integer` (:2219).
5. Cancel/abort — `tests/test_server.py::test_cancel_makes_the_modules_probe_answer_true_and_the_stream_ends_cancelled` (:1575), `::test_cancel_of_an_evict_job_is_409_not_cancellable` (:1595), `::test_cancel_of_a_finished_job_is_409_job_finished` (:1612), `::test_a_cancel_without_now_keeps_its_old_meaning` (:2037), `::test_stop_now_sets_both_flags_starts_one_stop_and_the_job_ends_cancelled` (:2060), `::test_a_bad_cancel_body_is_400_bad_args_naming_the_key_and_sets_no_flag` (:2088), `::test_stop_now_on_a_job_that_is_not_a_quickbench_is_409_not_abortable` (:2128), `::test_the_old_refusals_are_answered_before_the_body_matters` (:2148), `::test_stop_now_answers_202_before_the_stop_finishes` (:2267), `::test_a_second_stop_now_answers_202_without_a_second_stop` (:2294), `::test_stop_engines_defaults_to_the_runtimes_stop` (:2028).
6. Shutdown / step kill — `tests/test_server.py::test_shutdown_cancel_waits_for_a_running_job_to_its_done` (:1659), `::test_shutdown_does_not_cancel_an_evict_and_waits_for_it` (:1676), `::test_cancel_and_wait_past_its_bound_kills_the_steps_then_waits_for_done` (:1694), `::test_the_post_kill_wait_is_bounded_by_the_kill_grace` (:1727), `::test_a_job_that_outlives_the_kill_grace_is_abandoned_with_one_stderr_line` (:1746); `tests/test_engines.py::test_kill_running_steps_kills_every_registered_group` (:1754), `::test_each_step_is_bounded_by_the_injected_timeout` (:948); `tests/test_cli.py::test_shutdown_cancels_a_running_download_and_exits_zero` (:1518).
7. Caps — `tests/test_server.py::test_the_handler_thread_cap_closes_the_extra_connection_and_releases_at_timeout` (:1870, load-sensitive flake noted in §3), `::test_a_fifth_stream_on_one_job_is_429_and_a_freed_slot_admits_another` (:1899), `::test_past_the_event_cap_the_job_ends_with_too_many_events_and_done` (:1527), `::test_a_client_that_never_reads_is_dropped_at_the_write_timeout_while_the_job_runs` (:1424), `::test_a_second_job_while_one_is_running_is_409_busy_naming_the_job` (:1297), `::test_a_start_log_that_raises_answers_500_and_frees_the_slot` (:1827), `::test_a_thread_that_will_not_start_answers_500_and_frees_the_slot` (:1846).
8. pip argv — `tests/test_engines.py::test_mlxlm_plan_creates_the_pinned_venv_then_installs_the_tested_version` (:274), `::test_optiq_plan_creates_the_pinned_venv_then_installs_the_tested_version` (:302), `::test_the_committed_constraints_files_are_fully_hashed_and_pin_their_own_engine` (:365), `::test_no_plan_step_is_a_shell_string_and_none_uses_sudo` (:1199), `::test_steps_run_with_a_hermetic_env_that_drops_pythonpath_and_pip` (:958), `::test_the_bundled_python_is_the_one_the_plan_creates_the_venv_with` (:972).
9. Hashed-requirements validator — `tests/test_engines.py::test_the_hashed_requirements_validator_refuses_anything_but_hashed_pins` (:404), `::test_a_file_ending_in_a_continuation_is_refused_as_unhashed` (:418), `::test_the_hashed_requirements_validator_accepts_a_pin_with_several_hashes` (:428), `::test_an_unhashed_constraints_file_refuses_the_install_as_no_constraints` (:456), `::test_a_pip_engine_with_no_constraints_file_refuses_as_no_constraints` (:717), `::test_every_pip_engine_has_a_constraints_file_for_its_tested_version` (:347).
10. Rollback / lab-path record — `tests/test_engines.py::test_rollback_refuses_a_path_that_resolves_outside_the_engines_dir` (:1135), `::test_a_venv_that_existed_before_the_call_is_never_removed` (:1116), `::test_over_the_real_plan_a_failed_pip_step_rolls_back_and_a_success_records` (:821), `::test_a_failed_pip_install_records_no_lab_path_and_keeps_the_others` (:800), `::test_a_successful_pip_install_records_its_venv_bin_and_engine_env_prefixes_it` (:777).
11. Guided URL gate — `tests/test_engines.py::test_a_url_outside_the_https_allowlist_is_refused_before_the_opener` (:1246), `::test_guided_source_urls_pin_the_three_tested_releases_and_never_latest` (:251), `::test_a_tested_version_bump_moves_the_guided_url_with_no_other_edit` (:266), `::test_a_guided_plan_opens_the_https_page_then_polls_detect_until_installed` (:1209).
12. Lab-dir policy — `tests/test_engines.py::test_record_lab_path_refuses_an_app_engine_and_writes_nothing` (:883), `::test_record_lab_path_refuses_a_directory_that_must_not_join_path` (:897), `::test_record_lab_path_writes_for_a_lab_dir_nobody_else_can_write` (:917), `::test_record_lab_path_refuses_a_lab_dir_owned_by_another_user` (:928); `tests/test_runtimes.py::test_a_lab_path_owned_by_another_user_is_refused_at_start` (:3659), `::test_a_lab_path_is_prefixed_to_path_and_the_rest_of_the_environment_passes_through` (:3349), `::test_a_lab_path_that_does_not_exist_is_refused_naming_the_engine` (:3384).
13. URL/redirect allowlist — `tests/test_fetch.py::test_allowed_hosts` (:643), `::test_refused_hosts` (:659), `::test_a_final_url_outside_the_allowlist_is_refused` (:663), `::test_an_http_final_url_is_refused` (:679), `::test_no_request_carries_an_authorization_header` (:960), `::test_an_expired_signed_url_is_resolved_once_more` (:592), `::test_a_second_403_is_not_resolved_again` (:611).
14. `plan` validation — `tests/test_fetch.py::test_plan_refuses_a_hostile_literal` (:380), `::test_download_refuses_a_bad_name_before_any_request_or_write` (:385), `::test_consent_required_opens_nothing` (:258), `::test_unknown_repo_opens_nothing` (:288).
15. `_verify` — `tests/test_fetch.py::test_checksum_mismatch_removes_the_partial_and_links_nothing` (:493), `::test_an_existing_blob_that_does_not_match_is_not_overwritten` (:811), `::test_an_existing_non_lfs_blob_of_the_wrong_size_is_refused` (:825), `::test_an_existing_non_lfs_blob_of_the_right_size_but_wrong_bytes_is_refused` (:839).
16. Transfer write path — `tests/test_fetch.py::test_resume_sends_a_range_and_writes_only_the_remainder` (:537), `::test_a_206_starting_elsewhere_is_refused` (:552), `::test_a_200_to_a_range_request_restarts_from_zero` (:573), `::test_a_content_length_larger_than_the_catalog_is_refused` (:904), `::test_a_body_larger_than_the_catalog_is_refused` (:918), `::test_a_content_range_with_the_wrong_total_is_refused` (:936), `::test_a_snapshot_link_pointing_elsewhere_is_refused_before_any_request` (:855), `::test_a_regular_file_where_the_snapshot_link_belongs_is_refused_before_any_request` (:881), `::test_a_failure_on_the_second_file_leaves_no_links` (:509).
17. `evict` — `tests/test_fetch.py::test_evict_requires_consent` (:1119), `::test_evict_refuses_a_repo_the_ledger_does_not_list` (:1128), `::test_evict_removes_exactly_the_ledger_paths` (:1137), `::test_evict_leaves_a_foreign_directory_untouched` (:1163), `::test_evict_keeps_a_blob_a_second_snapshot_still_references` (:1174), `::test_evict_keeps_a_foreign_file_inside_the_repo_directory` (:1190), `::test_evict_refuses_a_corrupt_ledger` (:1213), `::test_evict_refuses_a_missing_ledger` (:1223), `::test_evict_refuses_a_ledger_path_that_resolves_outside_the_cache` (:1231), `::test_evict_refuses_a_ledger_path_outside_that_repos_own_directory` (:1264), `::test_a_live_lock_holder_makes_evict_busy_and_removes_nothing` (:1306), `::test_the_evict_lock_is_released_after_a_normal_evict` (:1331), `::test_the_evict_lock_is_released_when_an_evict_raises` (:1339).
18. Orphan stop / identity — `tests/test_runtimes.py::test_a_dead_owners_matching_engine_is_stopped_through_shutdown` (:3827), `::test_an_osaurus_shaped_entry_with_a_dead_launcher_is_stopped` (:3847), `::test_a_reused_launcher_pid_blocks_the_osaurus_shaped_stop` (:3886), `::test_a_stranger_listening_on_the_recorded_port_is_dropped` (:3925), `::test_a_listener_whose_recorded_identity_no_longer_matches_is_dropped` (:3956), `::test_a_reused_pid_is_dropped_and_never_signalled` (:4002), `::test_a_live_owners_ledger_is_never_read_or_touched` (:4042), `::test_the_ledger_file_is_removed_once_its_last_entry_is_gone` (:4088), `::test_a_started_engine_is_recorded_with_its_pid_port_and_identity` (:3743).
19. `stop_own_engines` / `_shutdown` — `tests/test_runtimes.py::test_stop_own_engines_stops_only_this_processes_entries_and_never_writes` (:4103), `::test_stop_own_engines_reports_a_failing_stop_and_still_stops_the_next` (:4133), `::test_stop_own_engines_without_a_readable_ledger_is_zero` (:4161), `::test_stop_kills_the_process_the_launcher_left_holding_the_weights` (:2823), `::test_stop_escalates_to_sigkill_when_sigterm_is_ignored` (:2691), `::test_stop_raises_if_spawned_pid_survives_sigkill` (:2674), `::test_stop_refuses_handoff_cleanup_when_listener_probe_is_unavailable` (:2709), `::test_a_listener_that_is_the_spawned_pid_is_not_signalled_twice` (:2851). **Gap:** no test drives pid recycling of *this* process's own ledger file (see §7 Q3).
20. Launch seam / single instance — `tests/test_cli.py::test_the_app_creates_app_support_before_it_serves` (:1166), `::test_the_app_serves_hardware_until_its_stdin_closes` (:1412), `::test_the_app_exits_zero_on_a_signal` (:1451), `::test_the_app_started_with_dev_null_exits_at_once_by_design` (:1469), `::test_the_app_reports_a_bind_failure_on_stderr_and_exits_two` (:1486), `::test_the_app_recovers_an_osaurus_backup_before_the_launch_line` (:1262), `::test_a_running_osaurus_app_leaves_the_backup_for_the_next_launch` (:1298), `::test_a_recovery_that_raises_is_one_line_and_the_app_still_serves` (:1327), `::test_an_orphan_stop_that_raises_is_one_line_and_the_app_still_serves` (:1382); `tests/test_paths.py::test_ensure_app_support_creates_the_directory_0700` (:191), `::test_ensure_app_support_tightens_a_pre_existing_0755_directory` (:199), `::test_without_a_checkout_the_writable_root_is_application_support` (:136); Swift: `LauncherTests.swift::testArgvEnvironmentAndDirectory` (:187), `::testTheFirstStdoutLineIsTheLaunchLineWhenTwoArriveBeforeTheAwait` (:213), `::testEOFBeforeTheLaunchLineIsCouldntStartWithTheStderrTail` (:265), `::testQuitWhileAJobRunsClosesStdinAndNeverSignals` (:321), `::testQuitEscalatesGraceThenTerminateThenKill` (:343), `::testSecondLauncherIsAlreadyRunningAndSpawnsNothing` (:418); `HTTPBackendTests.swift::testTokenIsRedactedInEveryDescription` (:260).

Coverage gaps visible from this inventory (not defects, just untested or thinly tested):

- `BackendLauncher.acquireLock`'s flock is tested via `testSecondLauncherIsAlreadyRunningAndSpawnsNothing` with a fake; no test holds the real lock file across two real launches (P5-7's live check was manual: "A second `open -n` of the .app focuses the first").
- `build_app.sh` is exercised by `scripts/check_bundle.sh` (a manual packaging check per AGENTS.md), not by the pytest or swift suites.
- The engine-ledger `_write_ledger` crash-between-write-and-replace path has no direct test (the docstring claims previous-file survival; `atomic_write_text`'s equivalent is likewise untested for its `BaseException` branch).
- `server.py:447`'s non-ASCII `Authorization` behaviour is tested (`:249`), but a non-ASCII *Host* header is not (it would fail the exact-match and be `bad_host`; fine, but untested).

## 7. Open questions for the reviewer

Falsifiable questions I suspect but could not prove from a read-only pass. Each names the location and what would settle it.

1. **Can any browser-submittable request shape reach a route and change state without the token?** Location: `server.py:435-458` plus `BaseHTTPRequestHandler`'s method dispatch. My reading: no — all seven `do_*` go through `_guarded`, TRACE/CONNECT get 501 from the base class, a "simple" `text/plain` POST dies at 415 but only after the 401, and fetch-no-cors/navigation cannot set `Authorization`. What would falsify: a request that reaches `_route` without passing all three checks (e.g. a base-class code path calling `do_*` without `_guarded`, or a second handler class somewhere). Is there anything in the stdlib `http.server` version pinned by the bundled Python that dispatches by method name dynamically (bypassing the seven explicit `do_*` wrappers)? The explicit wrappers exist precisely to catch that — worth one adversarial look at `BaseHTTPRequestHandler.handle_one_request` in the bundled 3.14.
2. **Host-match edge cases: is refusing case/alias variants deliberate and complete?** Location: `server.py:450`. `LOCALHOST:<port>`, `localhost.:<port>`, `127.0.0.1:<port> ` (trailing space), and a duplicate `Host` header (first value wins) all end in `bad_host` — fail-closed, but I could not confirm that `self.headers.get("Host")` on the bundled CPython cannot return a joined value for duplicates ("a, b"), which would also fail the exact match (still fail-closed, but the refusal reason would mislead). A two-line probe would settle it.
3. **Can pid recycling plus a stale own-ledger make `stop_own_engines` kill a process it did not start?** Location: `runtimes.py:1908-1937` (`stop_own_engines` performs **no** identity re-check, unlike `_stop_orphan` :1846-1863) and `runtimes.py:1867-1905` (`stop_orphaned_engines` skips any file whose owner pid is alive — including one whose owner is *this* process under a recycled pid). Scenario: process A (pid N) records an engine, is SIGKILLed; its `N.json` survives; pid N is recycled to a new `ohyesmlx app`; startup skips `N.json` because `_process_alive(N)` is true (it is us); a "Stop now" then `_shutdown`s the *stale* pid/port — if a stranger now holds that port it is killed as a "listener the runtime's launcher started". What would falsify: proof that the recorded entries cannot outlive their owner (they cannot — `_forget_running_engine` runs on stop, but not on SIGKILL) or that macOS pid recycling within the ledger's lifetime is impossible. The identity gate exists for orphans; the same gate is absent here.
4. **What exactly could a compromised PyPI file still do post-T-01?** Location: `engines.py:813-828`, `constraints/*.txt`. Hash-pinned, wheels-only, `--no-deps` with a frozen closure closes the "add a file to an existing version" and sdist-build vectors. Remaining surface I could not close from the repo: (a) the *freeze* itself (`scripts/hash_freeze.py`) trusting whatever PyPI served at freeze time; (b) the console scripts a wheel installs run at engine start under the user's account — a compromised maintainer who publishes a *new version* is pinned out, but a hash frozen from a compromised upload is pinned *in*; (c) `scripts/fetch_python_standalone.sh`'s tarball: is its sha256 checked against the download before extraction, and is that hash's source trusted (python-build-standalone's own release attestation)? `build_app.sh:26-29` records the hash but I did not read the fetcher's verification.
5. **A malicious HF repo: what remains if the catalog pins everything?** Location: `fetch.py:204-269`, `605-621`. The repo id, 40-hex revision, per-file hash and size are committed in `catalog.json`, and content is verified after transfer — so a hostile *content* at the pinned hash is out. What a malicious upstream can still do is serve a redirect (guarded per hop), lie about lengths (checked), or hold a 429/5xx to stall the job (bounded to 4 attempts, `Retry-After` capped at 60 s). The open piece: `catalog.json` is fetched/updated by `scripts/build_catalog.py` from HF — is the catalog row itself reviewed before commit (a row added with an attacker's repo/revision/hash would be "valid" end to end)? That is a process question the code cannot answer.
6. **The `_acquire_lock` stale-reclaim race in the two-process world the app now actually has.** Location: `fetch.py:366-390`; accepted in §9 with the trigger "a crash plus a two-process race at the same instant" and the change-condition "More than one backend per user is ever supported (P5-7)". But CLI `quickbench` (a second process) fetches/evicts through the same `download.lock` beside the app. Is the §9 rationale still current now that app+CLI is a supported combination, or should the reclaim use an atomic owner token? Low impact (lost ledger entry or a doubled download), but the accepted-risk text predates the two-process reality.
7. **Does anything besides `HTTPBackend.makeRequest` ever read `BackendToken.raw`?** Location: `BackendToken.swift:18`. P5-1's grep gate ("the token's variable shows it only in the `Authorization` header builder") held at the wave reviews (`ac0de1b` era); the w2 diff touched `AppModel`/`BackendLauncher` afterwards (`101df7c`). One re-run of that grep on the current tree would re-confirm the claim the §10 status table rests on — cheap, and the claim is load-bearing for every "Met" in that table.
8. **`engines.py:1017` — `_real_open` runs `/usr/bin/open` with no `timeout=`.** It is the only unbounded `subprocess.run` in scope. `open` normally returns immediately, but under a wedged LaunchServices it may not. Impact is one hung job thread (bounded by nothing; the job slot stays held until it returns — `busy` for everything after). Is the absence deliberate (a timeout that kills `open` after the URL was handed off would misreport a successful open), and if so should the comment name it?
9. **T-14's TOCTOU window in `fetch`: the islink checks at `fetch.py:791-797`/`908-914` and the `lexists`→`open` at `:871-874` are check-then-use.** Accepted for a same-user adversary (§9), but the acceptance names only "the HF cache". The install log (`engines.py:1155`) and fetch log (`fetch.py:424`) append through whatever path is there — also same-user accepted? Threat-model §5.5 says "Follows a symlink" as fact without a disposition line. A one-line §9 row would close the ambiguity.
10. **Ledger/log file modes below App Support.** `ensure_app_support` is 0700, so the directory gates everything under it (T-10's fix). But files inside — `fetched.json`, `install-log.jsonl`, `lab-paths.json`, `running-engines/*.json` — are created at umask (typically 0644, and `_acquire_lock` explicitly 0644). The 045-03 note says `_ledger_save` writes 0600 on one host ("mode went 0644 → 0600, which is what `_ledger_save` writes" — via `mkstemp`'s 0600). So: is the 0600 of `atomic_write_text` temps relied on as the mode guarantee for every JSON file under App Support, and is `install-log.jsonl`'s append (which does not go through `atomic_write_text`) intentionally umask-moded? Worth confirming because T-10's fix rationale ("another local account can read the install and fetch logs") is fully closed only by the directory mode, which the tests pin (`test_paths.py::test_ensure_app_support_creates_the_directory_0700`) — good — but nothing pins the file modes beneath it.

---

Dossier written from the working tree at `714e8f6` (plus the untracked review logs in `.paul/review/`). Read-only except this file. No suite run; no server, engine or app started.
