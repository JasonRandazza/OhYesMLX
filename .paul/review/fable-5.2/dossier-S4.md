# Dossier S4 — The onboarding backend (engines, fetch, quickbench, catalog, recommend, hardware)

Prepared for the Fable 5.2 review. Scope per `orders/dossier-S4.md`: `ohyesmlx/engines.py` (1340 lines),
`ohyesmlx/fetch.py` (1310), `ohyesmlx/quickbench.py` (1059), `ohyesmlx/catalog.py` (305), `ohyesmlx/recommend.py`
(209), `ohyesmlx/hardware.py` (167), `ohyesmlx/catalog.json` (schema only), `ohyesmlx/engines-tested.json`,
`ohyesmlx/constraints/` (headers only). All line numbers verified against the working tree at `714e8f6`
(2026-11-15). Nothing was changed; no test suite was run (the coordinator runs them).

## 1. Map

Every function in scope, `path:start-end — what it does`. Ranges are exact (start = `def`/decorator line,
end = that definition's own last line, or the blank that closes it when the next construct is a module-level
constant block), confirmed by reading each file whole.

### ohyesmlx/engines.py (1340 lines)

Registry of the five onboarding engines, detection, install plans, the install executor, rollback and lab paths.
Module constants: `ONBOARDING_ENGINES` (:53, the five names), `MANIFEST_PATH` (:60), `TESTED_VERSIONS` (:151,
derived from the manifest at import), `LAB_PATHS_FILE` (:378), `LAB_ENGINES` (:384, mlxlm+optiq only),
`DEFAULT_ENGINES_DIR`/`DEFAULT_INSTALL_LOG` (:879-880), `STEP_TIMEOUT_S` 900 (:884), `OUTPUT_TAIL_BYTES` 4096
(:885), `LOW_DISK_FLOOR_BYTES` 2 GiB (:889), `ALLOWED_DOWNLOAD_HOSTS` (:893), `POLL_S`/`POLL_TIMEOUT_S`
(:897-898), `TIMEOUT_EXIT_CODE` 124 (:901), `OPEN` `/usr/bin/open` (:1013).

- `engines.py:63-144 load_manifest(path)` — read + strictly validate `engines-tested.json`; ValueError names file and entry.
- `engines.py:150-151 MANIFEST/TESTED_VERSIONS` — manifest loaded once at import; a bad file stops the module.
- `engines.py:170-177 Step` — one install-plan step: id, label, optional argv.
- `engines.py:179-188 Plan` — one engine's install plan: kind `guided_download|command`, source URL, size estimate, steps.
- `engines.py:191-201 EngineStatus` — one engine's detect result: installed, version, path, tested, verified, install=None.
- `engines.py:204-220 _Filesystem` — real read-only filesystem as the injectable `env` (exists/read_text/listdir/realpath/home).
- `engines.py:236-240 _read_or_none` — read a file or None on OSError/ValueError.
- `engines.py:243-253 _plist_version` — `CFBundleShortVersionString` from a bundle's Info.plist, or None.
- `engines.py:256-262 _module_version` — the literal `__version__ = "…"` in a Python file, or None.
- `engines.py:265-279 _venv_package_version` — a package's version file inside the venv a script lives in.
- `engines.py:286-317 _optiq_version` — OptiQ's version from a sibling pyproject (editable) or dist-info METADATA.
- `engines.py:320-324 _first_existing` — first existing path of a tuple, or None.
- `engines.py:330-332 _app_support` — Application Support dir as a string (asks `ohyesmlx.app_support_dir`).
- `engines.py:335-337 _engines_dir` — `<app support>/engines`, the one derivation shared by detect and install.
- `engines.py:340-347 _app_engine_venvs` — the version-pinned venv root and the unpinned fallback, pin first.
- `engines.py:350-351 _app_engine_scripts` — `bin/<script>` under each of those venv roots.
- `engines.py:363-365 _lab_paths_file` — `<app support>/lab-paths.json`, the one derivation.
- `engines.py:368-375 _lab_paths_beside` — the lab-paths file beside a given engines dir (scratch runs keep their own).
- `engines.py:387-410 check_lab_dir` — refuse a lab dir unless absolute, a directory, owned by this user, not group/other-writable (T-12).
- `engines.py:413-462 lab_paths` — the one reader of lab-paths.json; missing file is `{}`; unknown/app-engine keys raise ValueError.
- `engines.py:465-496 record_lab_path` — the one writer; validates with `check_lab_dir`, merges, writes atomically.
- `engines.py:499-505 _detect_osaurus` — Osaurus via `runtimes.OSAURUS_APP_BUNDLES` (`/Applications/osaurus.app|Osaurus.app`), version from plist.
- `engines.py:508-516 _detect_omlx` — `~/.omlx/bin/omlx` shim first, `/Applications/oMLX.app` fallback; version from the bundle.
- `engines.py:519-523 _lab_script` — the script path a lab dir would hold (or nothing).
- `engines.py:526-538 _detect_optiq` — lab copy, then app venvs, then `~/.local/bin/optiq`, then a Dev checkout.
- `engines.py:541-563 _detect_mlxlm` — lab copy, then app venvs, then the harness venv `~/.local/share/ohyesmlx/mlx-lm-<ver>`.
- `engines.py:566-572 _detect_vmlx` — `/Applications/vMLX.app`, then `~/.local/bin/vmlx`; version from `VMLX_ENGINE_INIT`.
- `engines.py:584-622 detect_all` — one `EngineStatus` per engine in `runtimes.RUNTIMES` order; lab copies detected first; `install: None`.
- `engines.py:640-643 _release_url` — the tested release page URL from `_GUIDED_TRACKS` + `TESTED_VERSIONS` (never `releases/latest`).
- `engines.py:685-687 constraints_path` — `constraints/<engine>-<tested version>.txt`, the one name.
- `engines.py:700-719 _requirement_lines` — requirement lines with `\` continuations joined, comments dropped (shared with `scripts/hash_freeze.py`).
- `engines.py:722-746 _check_hashed_requirements` — refuse any line that is not `name==ver` + `--hash=sha256:<64 hex>`+ (T-01).
- `engines.py:749-776 _guided_plan` — app engines' plan: open the tested release page, then re-detect; per-macOS asset/size.
- `engines.py:779-831 _command_plan` — pip engines' plan: `{python} -I -m venv <pinned root>`, then `<root>/bin/python -I -m pip install --isolated --require-hashes --only-binary :all: --no-deps -r <constraints>`.
- `engines.py:834-863 install_plan` — pure plan derivation; unknown name or missing/unhashed constraints is ValueError before anything runs.
- `engines.py:904-925 EngineLocks` — one non-blocking in-process lock per engine (T-15: in-process only, see P5-7).
- `engines.py:931-933 _cap` — last `OUTPUT_TAIL_BYTES` bytes of text (byte-based, not char-based).
- `engines.py:936-945 _tail` — joined, capped output tail of several streams.
- `engines.py:955-960 _kill_step_group` — SIGKILL one step's process group; gone is not an error.
- `engines.py:963-974 kill_running_steps` — kill every registered step group; the server's shutdown bound calls it (045-02a).
- `engines.py:977-1008 _real_run` — run argv (never a shell string) in its own session, registered under the spawn lock, timeout kills the group.
- `engines.py:1016-1017 _real_open` — `open <url>` in the user's browser (absolute `/usr/bin/open`, no timeout).
- `engines.py:1020-1021 _print_event` — default emitter: one JSON event per line to stdout.
- `engines.py:1024-1036 _hermetic_env` — ambient env minus `PYTHONPATH` and every `PIP_*` key.
- `engines.py:1039-1040 _installed` — whether detection says this engine is installed.
- `engines.py:1043-1046 _disk_required` — 2× the size estimate, or the 2 GiB floor when unknown (AC-11).
- `engines.py:1049-1051 _never_cancelled` — default cancel probe (False).
- `engines.py:1054-1056 _url_allowed` — https and host in `ALLOWED_DOWNLOAD_HOSTS` (AC-9).
- `engines.py:1059-1069 _venv_root` — the directory a `-m venv` argv creates, found by token search (works with `-I`).
- `engines.py:1072-1077 _plan_engines_dir` — the engines dir the plan's venv step targets.
- `engines.py:1080-1095 _relocate` — rewrite plan paths from the production engines dir to the injected one.
- `engines.py:1098-1123 _rollback` — remove only paths this call created that resolve inside engines_dir; symlinks removed not followed.
- `engines.py:1126-1138 _job_event` — the pinned job-event shape, the one builder every module's emitter asks.
- `engines.py:1141-1156 _append_install_log` — append one JSONL line per event (also fetch's log via `fetch._emitter`).
- `engines.py:1159-1340 install` — the executor: consent → already-installed → lock → low disk → steps or guided poll; rollback on failure/cancel; `record_lab_path` after a successful pip run; lock released in `finally`.
- `engines.py:1199-1213 install.send` — event + log append with seq.
- `engines.py:1215-1218 install.refuse` — one `error` event + `done`, False.
- `engines.py:1232-1237 install.cancelled` — cancel path: `error` code `cancelled`, same rollback, `done`.
- `engines.py:1250-1297 install.run_steps` — run each command step; per-step cancel check; failure rolls back; success records the lab path.
- `engines.py:1299-1322 install.run_guided` — allowlist-check the URL, open it, poll `detect()` until installed or 600 s; a timeout is a result not an error.

### ohyesmlx/fetch.py (1310 lines)

Download one catalog model into the HF hub cache (resumable, verified) and evict exactly what it created.
Constants: `HF_BASE`/`ALLOWED_HOSTS` (:56-57), `REF_NAME` "main" (:60), `CHUNK_SIZE` 256 KiB (:64),
`PROGRESS_INTERVAL_S` 0.5 / `PROGRESS_MIN_FRACTION` 0.005 (:69-74), `MAX_ATTEMPTS` 4 / `BACKOFF_S` / `RETRY_AFTER_CEILING_S` 60 (:78-80),
`TIMEOUT_S` 60 (:84), `DEFAULT_LEDGER`/`DEFAULT_LOG`/`DEFAULT_LOCK_DIR` (:91-93), `LOCK_NAME` "download.lock" (:98).

- `fetch.py:101-102 HostNotAllowed` — a redirect left the allowlisted hosts.
- `fetch.py:105-106 LedgerError` — the ledger cannot be read; nothing may be created or removed.
- `fetch.py:109-119 PlannedFile` — one file's destination, size, hash key, blob, link, URL.
- `fetch.py:122-134 Planned` — pure description of where one catalog row lands; no I/O done.
- `fetch.py:137-149 default_cache_dir` — `HF_HUB_CACHE` else `~/.cache/huggingface/hub`; never reads `HF_TOKEN`/`HF_ENDPOINT`.
- `fetch.py:152-168 ledger_for` — `DEFAULT_LEDGER` for the default cache, else `<realpath(cache)>.ohyesmlx-fetched.json` beside it (045-02b).
- `fetch.py:171-176 host_allowed` — huggingface.co / hf.co and their subdomains.
- `fetch.py:179-187 url_allowed` — https + `host_allowed`; the one definition the redirect guard asks.
- `fetch.py:190-195 _check_inside` — refuse a destination resolving outside its container.
- `fetch.py:198-201 _repo_dir` — `<root>/models--<org>--<name>`, the one repo directory (T-13).
- `fetch.py:204-269 plan` — pure plan; refuses hostile repo/revision/path/hash literals before anything opens or writes (AC-11).
- `fetch.py:272-298 downloaded` — every planned file's snapshot link and blob present at the catalog size; sizes and links only, never hashes, never writes (UAT-001 / P5-11).
- `fetch.py:308-341 _ledger_load` — read + validate the ledger shape; missing/ill-shaped raises LedgerError.
- `fetch.py:344-346 _ledger_save` — atomic write via `ohyesmlx.atomic_write_text`.
- `fetch.py:354-363 _pid_alive` — `os.kill(pid, 0)` liveness.
- `fetch.py:366-390 _acquire_lock` — `O_CREAT|O_EXCL` create; reclaim a dead pid's lock (check-then-remove race accepted, §9).
- `fetch.py:393-405 _release_lock` — remove the lock only while it still names this pid.
- `fetch.py:413-436 _emitter` — job events through `engines._job_event`, each also appended to the fetch log.
- `fetch.py:439-443 _refuse` — one `error` + `done`, False.
- `fetch.py:451-457 _GuardedRedirects` — every redirect hop must pass `url_allowed` or HostNotAllowed.
- `fetch.py:460-475 _real_open` — GET with guarded redirects, 60 s timeout; HTTPError returned as the response; HostNotAllowed re-raised as itself.
- `fetch.py:478-479 _print_event` / `fetch.py:482-483 _never_cancelled` — defaults.
- `fetch.py:486-491 _response_url` / `fetch.py:494-499 _status` / `fetch.py:502-513 _header` / `fetch.py:516-521 _integer_header` / `fetch.py:524-530 _close` — duck-typed response accessors (fakes and real responses both).
- `fetch.py:533-542 _retry_delay` — 429 honours Retry-After capped at 60 s; else 0.5·2^n backoff.
- `fetch.py:550-556 _inside` — realpath containment.
- `fetch.py:559-563 _link_conflicts` — an existing snapshot link that is not the symlink to this blob (T-16's one decision).
- `fetch.py:566-571 _link_refusal` — the one refusal text for that case.
- `fetch.py:574-578 _partial_size` — size of a `.incomplete`, 0 when absent.
- `fetch.py:581-585 _remove` — remove a file, ignore OSError.
- `fetch.py:588-593 _sha256_file` — streamed sha256.
- `fetch.py:596-602 _git_blob_sha1` — the git blob id: `sha1("blob <size>\0" + bytes)`, streamed.
- `fetch.py:605-621 _verify` — the one verification rule: size, then sha256 (LFS) or git blob oid (plain); the CDN ETag is not the file's hash.
- `fetch.py:624-635 _make_dirs` — create dirs up to a stop point, recording only the ones created.
- `fetch.py:638-654 _referenced_blobs` — every blob any `models--*/snapshots` symlink in the whole cache resolves to (AC-8).
- `fetch.py:662-718 download` — guards in refusal order: consent, catalog id, name shapes, cross-process lock, ledger readable; then `_download`; ledger updated and lock released in `finally`.
- `fetch.py:721-749 _record` — merge created blobs/links/dirs into the ledger entry; never drop a previous entry.
- `fetch.py:752-1178 _download` — the body: reuse-verified present blobs, disk guard, fetch each missing file, link everything last, refs/main last.
- `fetch.py:766-773 _download.cancelled` — `error` code `cancelled`; the partial is kept for a resume.
- `fetch.py:775-778 _download.size_mismatch` — refuse code `size_mismatch`, optionally removing the named partial.
- `fetch.py:811-814 _download.remaining` — bytes still missing for one file (size minus `.incomplete`).
- `fetch.py:829-830 _download.make_dirs` — recording wrapper.
- `fetch.py:842-875 _download.link_all` — write snapshot symlinks (relative) and `refs/main` only after every file verified (AC-15).
- `fetch.py:891-904 _download.finish` — verify the completed file, `os.replace` `.incomplete` → blob, record it; mismatch removes the partial and refuses.
- `fetch.py:906-1122 _download._fetch_file` — one file's transfer: Range resume, 206 Content-Range checks, 200-restart, 403/410 re-resolve once, 429/5xx retry, over/under-size guards, throttled byte-level progress.
- `fetch.py:1124-1135 _download.fetch_file` — wrap `_fetch_file`; a failure leaves its `.incomplete` on the ledger for evict.
- `fetch.py:1186-1310 evict` — remove exactly the ledger's paths for a repo under `download.lock`: refuse unlisted repo or any path outside that repo's dir, drop links first, reference-scan before blob removal, rmdir only empty dirs, rewrite ledger.

### ohyesmlx/quickbench.py (1059 lines)

`ohyesmlx quickbench`: two single-axis stages on this Mac (D3/D9), sibling download/evict, Osaurus pin, abort.
Constants: `WARMUP` 3 / `MEASURED` 5 / `COOLDOWN_S` 10 (:61-63), `TIE = canary.NOISE_FLOOR` (:67),
`ESTIMATE_PER_CELL_S` 90 / `DOWNLOAD_BYTES_PER_S` 20e6 (:72-73), `LABEL`/`CAVEAT_A`/`CAVEAT_B` (:77-79),
`ABORTED`/`ABORTED_REASON` (:84-85), `DEFAULT_RESULTS_DIR` (:89), `DEFAULT_BACKUP_DIR` (:95, fixed path so
`recover` can find a crash's backup), `SUMMARY_NAME` (:98), `WORKLOAD_ID` "decode" (:102).

- `quickbench.py:105-111 PlannedEngine` — one stage-A engine: name, version, tested.
- `quickbench.py:114-121 PlannedSibling` — one stage-B format: repo, format, size, downloaded.
- `quickbench.py:124-139 QuickPlan` — the plan the app shows before the click (pinned shape, v5-quickbench.md).
- `quickbench.py:142-143 _print_event` / `quickbench.py:146-152 _discard` — emitter defaults; sibling fetch/evict events are discarded (their outcome is quickbench's to report).
- `quickbench.py:155-156 _never_cancelled` — defaults for `cancel` and `abort`.
- `quickbench.py:159-165 estimate_seconds` — `cells*90 + bytes/20e6`, the one estimate definition.
- `quickbench.py:168-175 _port_busy` — ask `runtimes._port_is_free`; unknown reads busy (skip, never start over).
- `quickbench.py:178-205 _osaurus_app_running` — `ps -axo comm=` matched against `runtimes.OSAURUS_APP_EXECUTABLES` full paths (never by name); a probe failure reads "running".
- `quickbench.py:208-225 _osaurus_drift` — compare live Osaurus config with the baseline the pin wrote; None when it has not moved.
- `quickbench.py:228-244 _keep_during_run` — copy both `PIN_FILES` byte-exact into `<backup>/during-run` (`0700`) so a mid-run user edit survives restore.
- `quickbench.py:247-252 _catalog_row` — the catalog row named repo, or ValueError.
- `quickbench.py:255-314 plan` — pure plan (AC-1): stage A = installed engines listing the row; stage B = `catalog.siblings`; refuses a repo not already cached ("download it first").
- `quickbench.py:317-319 cell_spec` — one cell as the `--cells` string `cli.build_cells` parses (the only selector).
- `quickbench.py:322-353 _cell_record` — one summary cell row: status/reason/numbers from `report.summarize`'s row or its own, always `label`.
- `quickbench.py:356-357 _skipped` — a SKIPPED cell row with its reason.
- `quickbench.py:360-371 _aborted` — a "Stop now" cell: status/reason, no number; the abort rationale's one home.
- `quickbench.py:374-395 _winner` — stage A's winner (PASS, highest decode_tps) and cells within `TIE` of it.
- `quickbench.py:398-428 _best` — the best-for-you block: from stage B's cells when stage B ran, else stage A's; winner's own format/repo; only on a finished run.
- `quickbench.py:431-447 _skip_reason` — osaurus-not-allowed / app-running / port-busy, checked before anything of theirs starts.
- `quickbench.py:450-451 _stamp` — UTC stamp `YYYYMMDDTHHMMSSZ` for the run directory.
- `quickbench.py:454-466 _write_summary` — atomic summary write (temp + `os.replace`, fsync; temp removed on any failure).
- `quickbench.py:469-479 _emitter` / `quickbench.py:482-485 _refuse` — job-event wrapper and one-refusal end.
- `quickbench.py:488-1020 run` — the run: consent, plan, stage A loop, stage B loop (sibling download → cell → evict), load labels, summary on every ending, one `result` event carrying the summary, `done` last.
- `quickbench.py:612-620 run.step` — progress event with the run's fraction.
- `quickbench.py:622-629 run.note_not_evicted` — record an eviction the fetch layer refused (AC-4).
- `quickbench.py:631-644 run.record_load` — per-stage 1-minute load before/after; over `canary.LOAD_NOISY` labels the stage busy (recorded, not retried).
- `quickbench.py:646-751 run.measure_cell` — one cell's `run_cells` call with Osaurus recovered→pinned→drift-checked→restored around it (restore in `finally`, restore failure ends the run).
- `quickbench.py:753-761 run.measured` — one cell's record; a stop that lands mid-cell replaces it with `_aborted` (raise-is-the-abort race handled).
- `quickbench.py:1023-1059 latest` — newest **finished** summary per `best.repo`, by file mtime; unreadable files skipped.

### ohyesmlx/catalog.py (305 lines)

- `catalog.py:54-60 disk_needed` — `ceil(nbytes * DISK_MARGIN)`; `DISK_MARGIN` 1.2 (:51) is the one disk-margin rule.
- `catalog.py:80-92 ModelFile` — one file: path, size, and exactly one of sha256 / git_oid.
- `catalog.py:95-117 Model` — one catalog row; `size_bytes == sum(files)`; `base` has the one default ("" for hand-built test rows; `load` requires it).
- `catalog.py:120-124 _string` / `catalog.py:127-135 _integer` — field validators (bool is not an int).
- `catalog.py:138-157 check_path` — the one file-path guard: no absolute, no `..`, no backslash, no NUL, no empty segment.
- `catalog.py:160-194 _files` — validate every file row: path, size, exactly one hash kind.
- `catalog.py:197-265 _model` — validate one row field by field; every ValueError names the file, repo and field.
- `catalog.py:268-293 load` — read and validate `catalog.json` (`built` + `models`), rows in file order.
- `catalog.py:296-305 siblings` — the other rows of the same `base`, catalog order (the D10 stage-B mechanism).

### ohyesmlx/recommend.py (209 lines)

Constants: `COMFORTABLE_FACTOR` 2.0 (:36), `TIGHT_FACTOR` 1.25 (:43), `STARTER_DISK_PRESSURE_BYTES` 20 GiB (:48),
`START_HERE_COUNT` 3 (:51), `_BYTES_PER_GB` 1e9 (:55).

- `recommend.py:58-84 Pick` — one offerable row: fit, engines, install_needed, start_here, reason, downloaded, measured_here.
- `recommend.py:87-93 _fit` — comfortable when 2×size ≤ budget, tight when 1.25×size ≤, else None (the row is left out).
- `recommend.py:96-98 _gb` — bytes as decimal GB, one decimal; the only place bytes become text.
- `recommend.py:101-115 _reason` — the fixed reason template; a downloaded row names no download size.
- `recommend.py:118-147 exclusion_reason` — memory first, then disk (skipped for a downloaded repo); fixed-template shortfall sentences.
- `recommend.py:150-154 _rank` — comfortable before tight, starter first under 20 GiB free, more params, repo id.
- `recommend.py:157-209 pick` — pure ranking; unsupported Mac is `[]`; `engines` = installed ∩ row's, else the row's list with `install_needed`.

### ohyesmlx/hardware.py (167 lines)

Constants: `SW_VERS`/`IOREG` absolute (:26-27), `TOOL_TIMEOUT_S` 10 (:31), `MIN_RAM_BYTES` 8 GiB (:35).

- `hardware.py:41-54 Hardware` — supported, chip/family/tier, cores, ram, macos, disk_free_bytes, volumes, model_budget_bytes.
- `hardware.py:57-71 _run` — run one tool by absolute path, 10 s timeout, check=True (T-09).
- `hardware.py:74-80 _chip_identity` — `"Apple M2 Max"` → family `M2`, tier `max`; unknown trailing word is base.
- `hardware.py:86-89 _gpu_cores` — `"gpu-core-count" = N` from ioreg text, first match or None.
- `hardware.py:92-97 _support` — unsupported off Apple silicon or under 8 GiB RAM (D1).
- `hardware.py:100-108 model_budget` — the one model-budget formula: min(¾, ⅔ by the 36 GiB line)·RAM − 2 GiB.
- `hardware.py:111-129 _volume_paths` — `/` plus real directories under `/Volumes` (skips dot-dirs, Recovery); ponytail comment names the APFS-role ceiling.
- `hardware.py:132-167 scan` — chip/RAM/cores/macos/ioreg via `run`, volumes via `disk_usage`; `disk_free_bytes` is the root volume's.

### Data files

- `ohyesmlx/catalog.json:1-1063` — schema only per scope: top level `{built: "YYYY-MM-DD", source, note, models: [row]}`; 12 rows; row keys exactly `repo, base, title, params, format, modality, license, tier, revision, size_bytes, files, engines, measured_here, notes`; file keys `path, size, sha256, git_oid`. 10 distinct `base` values; two bases carry two rows (Qwen3.5-0.8B stock/OptiQ, Qwen3.5-2B stock/oQ4). Validated on load by `catalog._model` (row shape above).
- `ohyesmlx/engines-tested.json:1-72` — five entries (mlxlm, osaurus, omlx, optiq, vmlx): `version` (str), `verified` (ISO date or null), `lab_path` (null everywhere in the shipped file), `canary` `{format, repo, workload, decode_tok_s, ttft_s, measured, version_measured}` (baselines present for the recorded engines). Validated by `engines.load_manifest` (:63-144).
- `ohyesmlx/constraints/mlxlm-0.31.3.txt`, `ohyesmlx/constraints/optiq-0.5.13.txt` — headers only per scope: 4 comment lines (purpose, venv path, interpreter `Python 3.14.10 (arm64)`, hash provenance "every file PyPI lists … 2026-11-10"), then `name==version \` continued with one or more `--hash=sha256:<64 hex>` lines. optiq's file carries no `pygame` pin (045-03). Enforced by `engines._check_hashed_requirements`; regenerated by `scripts/hash_freeze.py`.

## 2. Contracts

Pointers plus the binding sentences. Line numbers are the doc's own.

### docs/interfaces/v5-onboarding.md

- **Hardware** (L11-16): "`supported` is false off Apple Silicon or under 8 GiB RAM; every other field is still reported. `model_budget_bytes` is defined once, in `hardware.py`."
- **EngineStatus** (L18-23): "`tested` is the installed version against `ohyesmlx/engines-tested.json`, and `verified` is that manifest's ISO date for the build (present whether or not the engine is installed)". `detect_all` returns `install: null`; the server composes `install_plan`.
- **Lab paths** (L25-31): "A missing file is `{}` and invalid JSON, an unknown engine key, or any app engine (`osaurus|omlx|vmlx` …) raises `ValueError` naming the file and key. Only `mlxlm` and `optiq` may name one." `detect_all` looks in lab dirs first.
- **Plan** (L45-48): "`guided_download` (Osaurus, oMLX, vMLX) opens `source_url` and verifies afterwards; `command` runs `steps`."
- **Model** (L50-65): "An LFS file carries `sha256` … and a plain git file carries `git_oid`, never both and never neither — one of them is what a download verifies, and `fetch._verify` holds the one definition of how." `size_bytes` is the sum of `files`; `revision` and every file's size and hash come from one tree listing at that commit, "so a downloader never asks 'what is latest'".
- **catalog helpers** (L67-69): `check_path` is "the one file-path guard"; `disk_needed(nbytes) -> int` is "`ceil(nbytes * DISK_MARGIN)`, the one disk-margin rule `recommend` and `fetch` both ask".
- **Pick** (L71-91): "`fit` is an estimate from `Hardware.model_budget_bytes` alone -- comfortable when twice `size_bytes` fits it, tight when 1.25x does, otherwise the row is left out"; "`downloaded` is true when every file `fetch.plan` names has its snapshot link present and resolving to a blob of the catalog size (`fetch.downloaded(model, cache_dir=None) -> bool`, sizes and links only, never hashes, never writes)"; "Such a row is exempt from the **disk** budget … and still answers to memory"; `measured_here` "is null until a finished quickbench summary names the row, and is never filled from our M2 Max rows".
- **exclusion_reason** (L93-101): fixed-template memory/disk shortfall; "null for a row that clears both budgets (and for a repo in `downloaded`, whose disk budget is not applied)".
- **Job stream** (L103-158): the closed arg sets; "`low_disk` refusal carries `free_bytes` and `needed_bytes` (JSON integers) in its `error` payload"; "An `evict` refuses `busy` while a download or another eviction holds `download.lock` … and nothing is removed"; download progress "fraction = (bytes of files already finished + bytes written so far of the current file) / the model's total bytes … emitted at most once per 0.5 s of the injected clock and only when `fraction` has advanced by at least 0.005"; install cancel "only between steps and between guided-download polls (never inside a running pip step …)"; quickbench cancel "only between cells (its in-flight cell's stop path, sibling eviction and Osaurus restore still run, and the run ends `cancelled` with a summary)". Shutdown: `engines.kill_running_steps()` after the 120 s bound + `JOB_KILL_GRACE_S`.
- **Errors** (L160): `{"error": {"code", "status", "message"}}`; the server binds 127.0.0.1 only.
- **canary** (L193-207): one fixed cell per engine from `engines-tested.json`'s `canary` block; `canary.cells` is the only composer; `--cells` stays the only selector.

### docs/interfaces/v5-quickbench.md

- **Model.base / siblings** (L9-14): "Every catalog row carries `base` … `catalog.siblings(model, models)` returns the other rows with the same `base` in catalog order".
- **pin/restore/recover** (L25-57): "`pin` copies `server-runtime.json` and `server.json` (`PIN_FILES`) and the baseline … byte-exact into `backup_dir`"; "It refuses (`ValueError`) while a backup exists, because overwriting it would destroy the only copy of the user's own settings"; "`restore` … returns `True` only when each is byte-identical to its backup (`filecmp.cmp(shallow=False)`)".
- **record_lab_path** (L61-71): "the engine's own is replaced only by an install of the version the manifest pins … *bin_dir* is refused by `engines.check_lab_dir` before the file is read or written".
- **QuickPlan** (L78-124): the pinned dataclass shapes; "The chosen repo must already be in the cache" (run's rule, L137-166): "The chosen repo is never downloaded and never evicted by quickbench; a sibling the ledger does not list is refused by `fetch.evict`"; "Nothing is started on an occupied port"; "Osaurus is asked, pinned and restored … `restore` runs in a `finally` around the cell"; "Contention is recorded, not refused".
- **Cells and events** (L126-135): each cell is one `run_cells` call with `warmup=3, measured=5, cooldown_s=10, quick=True`; "Every `progress` event about a cell … carries `{"stage": "A"|"B", "engine": str, "format": str, "status": str, "reason": str|null}` … That payload is the whole cell row the app renders".
- **Summary** (L168-211): the pinned summary JSON; "`best` is non-null only on a finished run: a cancelled or half-restored run is a record of what happened, never a recommendation"; "`best`'s `format` and `repo` are the winning cell's own"; "Every ending sends that same summary as one `result` event, from the one place the file is written"; `latest` "returns the newest **finished** summary per repo, keyed by the repo the winning cell measured".

### docs/interfaces/v5-hardening.md

- **Install argv** (L60-77): "{python} -I -m venv …" and "{root}/bin/python -I -m pip install --isolated --no-input --disable-pip-version-check --require-hashes --only-binary :all: -r <constraints>"; "`--no-deps`, so the file is the whole closure and optiq's pygame … is omitted rather than built from source (045-03)".
- **_check_hashed_requirements** (L79-89): "Every non-blank, non-comment logical line … must be exactly `name==version` followed by one or more `--hash=sha256:<64 lowercase hex>` tokens and nothing else."
- **check_lab_dir** (L91-98): "raises `ValueError` naming the path and the reason unless the path is absolute, `os.stat` (following symlinks) is a directory, `st_uid == os.geteuid()`, and `st_mode & (stat.S_IWGRP | stat.S_IWOTH) == 0`."
- **ledger_for** (L100-107): "any other cache gets `<realpath(cache_dir)>.ohyesmlx-fetched.json`, a sibling of the cache and never a path inside it."
- **045-02a** (L50-56): each install step "runs through `Popen(..., start_new_session=True)` and is registered in a module-level set under the same lock that covers its spawn"; "A step that exceeds its own timeout has its process group killed and still reports `TIMEOUT_EXIT_CODE`"; `kill_running_steps()` is what the server's shutdown bound calls.

### AGENTS.md (rules that bind this code)

- **Approved surfaces** (v5.0): modules `hardware.py`, `engines.py`, `catalog.py`, `recommend.py`, `fetch.py`, `server.py`, `quickbench.py`; subcommands `app`, `quickbench`, `canary`; `ohyesmlx/engines-tested.json`; `app/`. "anything beyond them still needs a yes."
- **One definition of everything**: "A formula, a guard, a size or a constant lives in exactly one place and every caller asks it." (Load-bearing here: `disk_needed`, `model_budget`, `_verify`, `check_path`, `check_lab_dir`, `_job_event`, `estimate_seconds`, `cell_spec`.)
- **Each rationale is written once**, where the thing it explains is defined.
- **No new dependency** without naming what it replaces; stdlib first; Python 3.11+.
- **Downloads need a reason and a record**; "the repo ids go in a committed script (`scripts/fetch_moe.sh` is the pattern)"; **never download while a measurement is running**.
- **A cell that produces incoherent output has FAILED** — quickbench uses the harness's coherence gate untouched.
- **Raw observations are never discarded** — a quickbench abort keeps the cell's raw rows on disk.
- **One model resident at a time / quiet machine / thermal** — quickbench inherits the harness rules; D9's light cells do not exempt them.
- **Osaurus runs go through `scripts/osaurus-pin.sh`, always** — the standing pin authorisation and the restore-byte-exact-verified rule; quickbench's own pin/restore is the module implementation of the same contract (045-03a).
- **Stale Osaurus instances**: sweep by full executable path, "never by the name `osaurus`" — `_osaurus_app_running` implements exactly this.
- **Ports** (Osaurus 1337, optiq 8080, mlx-lm 8081, oMLX 8100, vMLX 8000): "A run that does not release its port has failed."
- **Never infer a capability from the absence of a flag**; `docs/runtimes/<name>.md` is the per-runtime capability reference.
- **Never edit `ohyesmlx/*.py` while a grid is running.**

### docs/threat-model.md (rows naming this code)

- §5 trust boundaries (L73-77): installer→pip is version pins in committed constraints run with `PYTHONPATH`/`PIP_*` dropped; downloader→HF is https-only with per-file hash checks; "`evict` removes only paths the ledger recorded, after checking each one resolves inside the cache".
- §5 entry points (L88-113): `/engines` → `detect_all`/`install_plan`; `/recommendations` → `recommend.pick`, `fetch.downloaded`, `quickbench.latest`; job kinds `install`/`download`/`evict`/`quickbench` and their closed args; subprocess rows for `_real_run`, `_real_open`, `hardware._run` ("no timeout" is stale — fixed T-09), `quickbench.py:186` `ps`.
- §5 writes-on-disk (L134-153): venvs via `-m venv`+pip, `lab-paths.json` (temp+replace), `install-log.jsonl` (append), `fetched.json` (atomic), `download.lock` (`O_CREAT|O_EXCL`, 0644), HF cache layout (blob/symlink/refs, symlink-write refusals), quickbench summary (temp+replace).
- §7 findings: T-01 (pip hash pins, fixed 045-02a/b parts), T-02 (interrupted app; (d) withdrawn — `.incomplete` is resume state), T-03 (writable root), T-05 (mid-cell Osaurus drift; one residual), T-06 (evict lock), T-07 (installer env), T-09 (bare command names), T-10 (file modes), T-12 (lab-paths values), T-13 (evict ledger trust), T-14 (HF symlink races — accepted §9), T-15 (in-process install lock — P5-7), T-16 (post-transfer snapshot check), R-01 (`_REPO` admits `.`/`..` — no traversal), R-04 (`PYTHONHTTPSVERIFY=0` — content is hash-gated).
- §9 accepted risks: T-14 symlink races; `_acquire_lock` stale-reclaim check-then-remove race; UAT-001 (size-only `downloaded`).
- §10: P5-3 (`-I`/`--isolated`), P5-5 (0700), P5-6 (nothing inside the bundle), P5-7 (one instance — covers T-15/T-06), P5-9 (launchd PATH, bundle executables), **P5-11 (partly met, open)**, P5-12 (SBOM of pinned engine deps).

### .paul/phases/v5-onboarding/PLAN.md decisions (D1-D10)

- D1 Apple Silicon only; Intel or <8 GB RAM gets a plain "unsupported" screen. (hardware.py `_support`.)
- D2 The five engines; GUI-app engines are guided downloads — "installer opens the official download and verifies after, no scripting". (engines `_guided_plan`.)
- D3 Quickbench two stages, one axis each; each result carries its can't-claim caveat. (quickbench `CAVEAT_A/B`.)
- D4 ~10 min budget; "shows time and download size first; starts only on click; one model ≤3B at a time, evict before the next fetch". (QuickPlan estimate; sibling evict.)
- D5 "Fits" computed and **labelled estimated**; speed shown only from runs on the user's Mac. (Pick `fit_basis`, `measured_here`.)
- D6 Standalone Python bundled in the .app. (packaging, re-verified P5-3/4/6/9.)
- D7 unsigned GitHub Releases .app; CLI stays.
- D8 Local only: no telemetry; results in Application Support; models in the HF cache by default, "the user may pick another volume".
- D9 Quickbench lighter cells (warmup 3, 5 measured, 10 s cooldown), "Results are labelled 'quick' and never join the published tables".
- D10 The localhost API guard (server) and "Stage B finds a model's other formats through a catalog `base` field". (catalog.siblings.)

## 3. Already known — do not re-report

Format: `- <claim> — <source> — fixed <sha> | accepted | deferred | open`.

Known open item the order names explicitly:

- P5-11: the app cannot offer "Re-download" for a model whose files differ in size, because `Pick.downloaded` is a single bool (it cannot distinguish "absent" from "present with different sizes") — threat-model §10 status table ("Partly met"), STATE.md Deferred Issues — **open** (needs a backend field plus Models-row copy).

Threat-model findings that touched this code (all triaged and approved by Jason 2026-11-03):

- T-01 pip installs pinned by version, not hash → constraints files with `--require-hashes --only-binary :all: --no-deps` + `_check_hashed_requirements` — threat-model §7.4 — fixed 045-02b part A (`a031ad4`, review `7393715`).
- T-02 interrupted app left engines/ports/pins/pip steps unrecovered → startup recovery, running-engines ledger, `kill_running_steps`; (d) withdrawn (`.incomplete` is resume state) — threat-model §7.4 — fixed 045-02a (`4b35ef8`, `9bc9388`).
- T-03 backend wrote inside its own package tree → `ohyesmlx.writable_root()` / `app_support_dir` derivations — threat-model §7.4 — fixed 045-02a (`4b35ef8`).
- T-05 an Osaurus pin clobbered mid-cell was measured and reported as pinned → post-cell drift check + `during-run` copies — threat-model §7.4 — fixed 045-02a (`9bc9388`); **residual accepted**: when the cell itself raises, the drift check does not run, so a mid-run user change in that path is still overwritten by the restore.
- T-06 `evict` took no lock and could race a download over the ledger — threat-model §7.4 — fixed 045-02b part B (`fb4e61c`).
- T-07 installer environment: pip config files and `PYTHONHOME` passed through; venv step ran without `-I` → `-I` + `--isolated` — threat-model §7.4 — fixed 045-02b part A (`a031ad4`).
- T-09 bare command names (`ps`, `sysctl`, `sw_vers`, `ioreg`, `open`) → absolute paths + `TOOL_TIMEOUT_S` — threat-model §7.4 — fixed 045-02a (`4b35ef8`).
- T-10 file modes: app support unreadable-by-others only after `ensure_app_support()` 0700 — threat-model §7.4 — fixed 045-02a (`4b35ef8`); P5-5 "Met on this account; clean account pending".
- T-12 `lab-paths.json` values become the front of PATH with only a non-empty-string check → `check_lab_dir` + atomic write — threat-model §7.4 — fixed 045-02b part A (`a031ad4`).
- T-13 `evict` trusted any ledger path under the whole cache root → per-repo containment via `_repo_dir` — threat-model §7.4 — fixed 045-02b part B (`fb4e61c`).
- T-14 same-user symlink races in the HF cache (`islink`→`open` on `.incomplete`, `lexists`→`open("w")` on refs/main) — threat-model §7.4/§9 — **accepted** (fixing needs `O_NOFOLLOW`/`openat` throughout fetch).
- T-15 `EngineLocks` is in-process only; two app instances could install one venv concurrently — threat-model §7.4 — **accepted** to checklist P5-7 (one instance per user; "Met" via `flock` at the Phase 5 status table).
- T-16 snapshot-conflict check ran only after the transfer (wasted multi-GB fetch) → `_link_conflicts` in the pre-transfer pass — threat-model §7.4 — fixed 045-02b part B (`fb4e61c`).
- R-01 `_REPO` admits `.`/`..` — no traversal (org/name is one path component; download/quickbench take catalog rows, evict takes ledger keys) — threat-model §7.4 — **rejected, no change**.
- R-04 `PYTHONHTTPSVERIFY=0` in the environment — same-user only and every file is hash-gated — threat-model §7.4 — **rejected, no change**.
- UAT-001: `fetch.downloaded` compares sizes; a size mismatch reads "not ours" — threat-model §8/§9 — **accepted** (Jason 2026-11-03); "Users report surprise re-downloads" is the named trigger for revisiting.

STATE.md / SUMMARY known gaps and carried items (S4-relevant only):

- The real `fetched.json` on this checkout is polluted: its one entry lists 60 paths under two `/private/tmp/...` scratch caches from 2026-11-03 runs; both the old and the new containment checks refuse it, so no real download became unevictable — 045-02b SUMMARY "Known gaps" + threat-model §7.4 T-13 — **open** (cleaning the host's ledger is a coordinator decision).
- `_acquire_lock`'s stale-reclaim is check-then-remove: two processes that both find a dead owner can both proceed — threat-model §9 — **accepted**.
- Global pip config (`/etc/pip.conf`, Application Support pip.conf) still loads under `--isolated`; needs admin to write and a rerouted index cannot pass the hashes — 045-02b "Deferred" + §9 — **accepted**.
- Two continuation joiners: `scripts/hash_freeze.py` and `engines._requirement_lines` each join `\` continuations in their own helper — 045-02b "Known gaps" — **open** (minor, one-definition).
- `record_lab_path` failing after a successful pip install raises out of `install` (worker's call; no pinned code) — 04-03b SUMMARY "Deviations" — **open** (see §7 Q5).
- `during-run/` stays in the backup dir: it does not block pin/recover, but a later drift overwrites it and `restore` can no longer `rmdir` the backup dir — 045-02a "Known gaps" — **open** (Phase 5 copy item).
- The four remaining atomic-write copies (`osaurus_settings`, `runtimes`, `measure`, `quickbench`) were not migrated to `ohyesmlx.atomic_write_text` — 045-02b "Deferred" / PHASE-4.5 "Carried forward" — **deferred**.
- `/engines` reports vMLX installed for an account that cannot execute its bundle (multi-user Macs only) — PHASE-4.5 "Carried forward" — **open**.
- pygame wheel watch: optiq installs wheels-only with `--no-deps` and no pygame pin (used only by `optiq game`); check monthly and at every OptiQ bump — STATE Decisions 2026-11-13 (`369f180` supersedes the 2026-11-10 source-build call) — **deferred** (watch).
- The two hero-model `model.safetensors` files are re-serialisations of the pinned revision (proven byte-exact over the tensor region); `fetch.downloaded()` still reports them not downloaded (size check) — STATE Blockers (resolved 2026-11-03) — **closed, no action**; the size-check half is UAT-001 above.
- `refs/main` is written only when absent (an HF-style move of an existing ref is not performed for a commit-pinned download) — PHASE-2.5-3 SUMMARY "Deviations" (kept as-is at review) — **accepted**.
- 04-03b's Osaurus baseline-path gap (quickbench pinned a baseline the drift guard did not read) — fixed 04-03c (`ad73b76`).

Prior review findings on this code (`.paul/review/2026-11-14-phase5-w1`, `w2`; `.paul/review/2026-09-23` predates v5 and covers none of these files):

- w1 spec #2 / w1 standards HARD #1: stage-B cells collapsed in the client — quickbench's progress payload carried the winner's engine for every sibling while the message named the format, and no `docs/interfaces/` file pinned the payload; stage-B rows overwrote each other and their reasons were dropped — `.paul/review/2026-11-14-phase5-w1/{spec,standards}.log` — fixed `ac0de1b` ("structured cell events"; payload now carries stage/engine/format/status/reason, pinned in v5-quickbench.md).
- w1 spec #4: `test_an_abort_after_the_last_cells_engine_stopped_leaves_the_ending_finished` could not fail for its claim (probe never triggered) — w1 spec.log — fixed `ac0de1b` ("two tests that could not fail now can"; the test now lives at tests/test_quickbench.py:1565).
- w1 spec #5: AC-7's raise path (`measure_cell` raising while abort()) untested — w1 spec.log — fixed `ac0de1b` (tests/test_quickbench.py:1602 `a_raise_from_measure_cell_itself_while_aborted_is_an_aborted_cell`).
- w1 standards HARD #2: the abort rationale restated in three docstrings (`_aborted`, `run`, `measured`) — w1 standards.log — fixed `ac0de1b` ("abort rationale written once").
- w1 standards JUDGEMENT: the `if record["status"] == ABORTED: summary["ended"] = "cancelled"; break` block copied into both stage loops — w1 standards.log — **open** (verified still duplicated at quickbench.py:808-810 and :934-936; the commit fixed the rationale duplication, not this block).
- 2026-11-14 decision: quickbench `best` did not name its format/repo and a stage-B sibling's win was shown on the chosen model (wrong `measured_here` keying since 04-03b) — STATE Decisions 2026-11-14 — fixed and red-checked `bb762c6`.
- w2 standards #5: two definitions of "newest wins" for `best.repo` (server.py `measured_at`-string tie-break vs `quickbench.latest`'s file-mtime) — `.paul/review/2026-11-14-phase5-w2/standards.log` — fixed in the wave-2 fixes (`101df7c` tree; verified the duplicate is gone — server.py now delegates to `summaries()`/`quickbench.latest`, docstring at server.py:572).
- w2 spec #4 / standards #6: the "Left on disk" (`not_evicted`) line built in two Swift places while tests pin only the AppModel copy — w2 logs — **open, Swift-side** (the summary field `not_evicted` itself is quickbench's and pinned; the duplication is in `app/` and belongs to the app section).
- w2 spec #1, #2, #3, #5, #6 and standards #1-#4, #7: stale-summary job state race, ephemeral benchmark tick, `payloadData` re-encoding vs "exactly as received", benchmark plan fetch race, `String(format:)` gate, glyph size — w2 logs — Swift-side (`app/`), outside S4; listed only so they are not re-attributed to this backend.
- w1 spec #1 (cancel body without `Content-Length`), w1 standards JUDGEMENTS (SSE poison event loop, launcher first-line loss): server/client transport, fixed `ac0de1b` (named in its message); outside S4's file scope.
- 045-03 findings F1/F2: optiq could not install without Homebrew SDL (pygame source build) and app engines could not start under launchd's PATH → pygame omitted wheels-only, bundle executables table — `045-03-SUMMARY.md` — fixed `369f180`.

## 4. Hotspots

The ranges where a defect would hurt most — user data, a wrong or misattributed number, a race, a trust boundary.
`path:start-end — why — guard`.

1. `fetch.py:1222-1300 evict` (containment check + link/blob/dir removal) — the one operation in the app that deletes user-visible files; a containment or ledger-shape bug deletes cache contents the user owns — `tests/test_fetch.py::evict_removes_exactly_the_ledger_paths`, `::evict_leaves_a_foreign_directory_untouched`, `::evict_refuses_a_ledger_path_that_resolves_outside_the_cache`, `::evict_refuses_a_ledger_path_outside_that_repos_own_directory`.
2. `fetch.py:605-621 _verify` — the one rule standing between a hostile/wrong download and a model the app then serves and measures; a wrong hash rule ships corrupt weights with a green status — `tests/test_fetch.py::checksum_mismatch_removes_the_partial_and_links_nothing`, `::an_existing_non_lfs_blob_of_the_wrong_size_is_refused`, `::an_existing_non_lfs_blob_of_the_right_size_but_wrong_bytes_is_refused`.
3. `fetch.py:906-1122 _download._fetch_file` — Range resume, Content-Range validation, restart-on-200, retry bounds; a defect silently corrupts a resumed multi-GB file or loses its resume state — `tests/test_fetch.py::resume_sends_a_range_and_writes_only_the_remainder`, `::a_206_starting_elsewhere_is_refused`, `::a_200_to_a_range_request_restarts_from_zero`, `::a_content_range_with_the_wrong_total_is_refused`, `::a_body_larger_than_the_catalog_is_refused`, `::a_cancelled_download_resumes_and_completes`, `::a_resumed_download_starts_its_fraction_from_the_bytes_on_disk`.
4. `fetch.py:780-809` (present-blob pass: symlink refusal, reuse-only-if-verified) — trusts cache state as evidence; a bug either re-downloads over a user's file or reuses a poisoned one — `tests/test_fetch.py::an_existing_blob_that_does_not_match_is_not_overwritten`, `::a_present_blob_is_reused_and_only_the_missing_file_is_requested`, `::a_present_blob_the_download_reused_is_never_evicted`, `::a_snapshot_link_pointing_elsewhere_is_refused_before_any_request`.
5. `fetch.py:816-827 + 1144-1155` (disk guards before any request and before each file) — filling a user's disk mid-download is the loudest possible failure; the numbers travel in `low_disk`'s payload — `tests/test_fetch.py::disk_guard_counts_missing_bytes_not_the_total`, `::disk_guard_refuses_before_any_request`, `::the_disk_guard_is_rechecked_before_each_file`.
6. `fetch.py:366-405 _acquire_lock/_release_lock` — cross-process mutual exclusion over the shared ledger; a bug races evict against download (T-06) — `tests/test_fetch.py::a_live_lock_holder_makes_the_download_busy`, `::a_stale_lock_from_a_dead_pid_is_reclaimed`, `::a_live_lock_holder_makes_evict_busy_and_removes_nothing`, `::the_evict_lock_is_released_when_an_evict_raises`.
7. `fetch.py:272-298 downloaded` — the size-only cache check that P5-11 and every "already on this Mac" claim rests on; wrong answers mislead the UI and gate quickbench (see §7 Q1) — `tests/test_fetch.py::downloaded_is_true_only_once_the_whole_tree_is_there`, `::downloaded_is_false_for_a_blob_of_the_wrong_size`, `::downloaded_checks_sizes_not_hashes`.
8. `engines.py:1098-1123 _rollback` — recursive delete of install artifacts; a containment bug deletes outside the engines dir (AC-7) — `tests/test_engines.py::rollback_refuses_a_path_that_resolves_outside_the_engines_dir`, `::a_venv_that_existed_before_the_call_is_never_removed`, `::over_the_real_plan_a_failed_pip_step_rolls_back_and_a_success_records`.
9. `engines.py:1250-1297 install.run_steps` — runs pip against the user's machine and decides what counts as created; a bug leaves half an install or removes too much — `tests/test_engines.py::two_steps_run_in_order_with_progress_after_each_and_done_last`, `::a_failing_step_stops_before_the_next_rolls_back_and_reports_the_tail`, `::a_failed_pip_install_records_no_lab_path_and_keeps_the_others`.
10. `engines.py:779-831 _command_plan` + `engines.py:722-746 _check_hashed_requirements` — the supply-chain boundary: what pip is allowed to fetch and run (T-01/T-07) — `tests/test_engines.py::the_committed_constraints_files_are_fully_hashed_and_pin_their_own_engine`, `::the_hashed_requirements_validator_refuses_anything_but_hashed_pins`, `::every_pip_engine_has_a_constraints_file_for_its_tested_version`, `::steps_run_with_a_hermetic_env_that_drops_pythonpath_and_pip`.
11. `engines.py:977-1008 _real_run` + `engines.py:955-974 kill_running_steps` — the process-group registry a server shutdown kills through; a bug either orphans pip trees or signals the wrong processes (T-02c) — `tests/test_engines.py::a_step_runs_in_its_own_session_and_leaves_the_registry_empty`, `::a_step_that_times_out_kills_its_group_and_reports_the_timeout`, `::kill_running_steps_kills_every_registered_group`, `::the_step_lock_is_held_across_popen_and_the_registration`.
12. `engines.py:387-496 check_lab_dir/lab_paths/record_lab_path` — the file that becomes the front of PATH for every engine start; a defect lets a wrong directory choose which server the harness runs (T-12) — `tests/test_engines.py::record_lab_path_refuses_a_directory_that_must_not_join_path`, `::record_lab_path_refuses_a_lab_dir_owned_by_another_user`, `::a_lab_paths_file_that_is_not_json_is_refused_naming_the_file`, `::a_lab_path_for_an_app_engine_is_refused`.
13. `engines.py:1239-1248` (consent → already-installed → lock order) — the consent gate is the trust boundary between the localhost API and the machine (every job needs `confirmed: true`) — `tests/test_engines.py::install_without_consent_runs_nothing_and_emits_its_refusal_then_done`, `::an_already_installed_engine_is_refused_before_the_lock_or_a_step`, `::a_held_lock_refuses_the_second_install_as_busy`.
14. `quickbench.py:646-751 run.measure_cell` (Osaurus recover→pin→drift→restore) — edits the user's own Osaurus host settings and must put them back byte-exact; a bug leaves the user's app running settings they never chose (T-05) — `tests/test_quickbench.py::osaurus_is_recovered_pinned_and_restored_around_its_cell`, `::drift_between_pin_and_restore_fails_the_cell_and_keeps_both_copies`, `::a_restore_that_does_not_verify_ends_the_run_and_names_the_backup`, `::a_cell_that_raises_still_restores_osaurus`, `::an_aborted_osaurus_cell_still_restores_the_host_settings`.
15. `quickbench.py:844-936` (stage-B sibling download → cell → evict, plus the `outstanding` sweep at :944-953) — the only place this app deletes from a cache on its own schedule; the chosen repo must never be touched and every refusal must be recorded — `tests/test_quickbench.py::a_missing_sibling_is_downloaded_before_its_cell_and_evicted_after_it`, `::the_chosen_repo_is_never_downloaded_or_evicted`, `::a_refused_sibling_eviction_is_logged_and_recorded`, `::cancel_after_a_sibling_download_evicts_it_and_measures_no_more`, `::an_abort_during_a_stage_b_cell_evicts_the_sibling_and_stops_there`.
16. `quickbench.py:374-428 _winner/_best` — decides which number the app calls "best for you" and which repo it is attributed to; a defect misattributes a measured speed to a model that never produced it (D5) — `tests/test_quickbench.py::stage_a_names_the_winner_and_reports_cells_within_the_tie_band`, `::a_stage_b_sibling_win_is_keyed_by_the_sibling_not_the_chosen_repo`, `::an_aborted_cell_is_never_the_winner_even_with_a_number`.
17. `quickbench.py:943-1002` (the `finally`: leftover evictions, ending bookkeeping, summary write, the one `result` event) — the record of what happened; a defect loses a summary or reports an ending the run did not have (raw observations never discarded) — `tests/test_quickbench.py::every_ending_carries_the_summary_as_one_result_event_before_its_error`, `::an_unexpected_raise_still_carries_the_summary_as_a_result_event`, `::a_cancelled_run_stops_between_cells_and_writes_its_summary`, `::a_cancelled_ending_carries_the_summary_path_in_its_terminal_events`.
18. `quickbench.py:1023-1059 latest` — feeds `Pick.measured_here`; a defect attaches a number to the wrong row or resurrects a cancelled run's figures — `tests/test_quickbench.py::latest_returns_the_newest_finished_summary_per_repo`, `::the_summary_the_run_wrote_is_what_latest_reads`, `::a_stage_b_sibling_win_is_keyed_by_the_sibling_not_the_chosen_repo`.
19. `recommend.py:87-154 _fit/exclusion_reason/_rank` + `hardware.py:100-108 model_budget` — the fit math every recommendation and every "Fits with X GB to spare" sentence derives from; a defect offers a model that cannot load or hides one that can (D1/D5) — `tests/test_recommend.py::comfortable_when_twice_the_weights_fits_the_budget`, `::tight_at_exactly_1_25_times_the_budget`, `::8_gib_mac_holds_the_2b_oq4_as_tight_only`, `::memory_still_excludes_a_downloaded_row`, `tests/test_hardware.py::model_budget_takes_two_thirds_of_ram_under_36_gib_less_two_gib`.
20. `catalog.py:138-265 check_path/_files/_model` — the validation between a committed JSON file and every path fetch will write and every size evict will trust; a hostile or drifted row reaches the filesystem here or nowhere — `tests/test_catalog.py::the_shared_path_guard_refuses_at_load`, `::size_bytes_that_is_not_the_sum_of_the_files_is_refused`, `::a_file_with_both_a_sha256_and_a_git_oid_is_refused`, `::every_entry_pins_a_commit_and_a_hash_for_its_weights`.

## 5. Mechanical scan

Grep over the six Python files in scope (data files excluded — they contain no code). Each hit is one line,
`path:line — matched fragment`. Not judged, per the order. The Swift pattern set is **not applicable**: S4's
scope contains no Swift.

**`shell=True`** — none.
**`os.system`** — none.
**`eval(`** — none.
**`exec(`** — none.
**`pickle`** — none.
**bare `except:`** — none.
**`except Exception: pass`** — none. (`except Exception` does appear, always binding `as error` or re-raising; listed under "broad except" below.)
**`tempfile.mktemp`** — none. (Atomic writes use `ohyesmlx.atomic_write_text`'s `mkstemp`, or quickbench's fixed `.tmp` name.)
**`statvfs`** — none (disk space comes from `shutil.disk_usage`).
**`chmod`**:
- `quickbench.py:237 — os.chmod(destination, osaurus_settings.BACKUP_DIR_MODE)` (the `during-run` dir, 0700).

**`os.remove`**:
- `engines.py:1117 — os.remove(path)` (rollback of a symlink).
- `engines.py:1121 — os.remove(path)` (rollback of a non-dir, non-link path).
- `fetch.py:383 — os.remove(path)` (reclaim a dead pid's lock file).
- `fetch.py:403 — os.remove(path)` (`_release_lock`).
- `fetch.py:583 — os.remove(path)` (`_remove`, used for failed `.incomplete` partials).
- `fetch.py:1254 — os.remove(path)` (evict: a ledgered link).
- `fetch.py:1273 — os.remove(path)` (evict: a ledgered blob).

**`shutil.rmtree`**:
- `engines.py:1119 — shutil.rmtree(path)` (rollback of a created directory; containment checked at :1105-1114).

**`unlink`**:
- `quickbench.py:465 — temporary.unlink(missing_ok=True)` (the summary's temp file, on a failed write).

**`rename`** — none as `.rename`; the atomic replaces are `os.replace`:
- `fetch.py:902 — os.replace(incomplete, planned_file.blob)` (verified `.incomplete` → blob).
- `quickbench.py:463 — os.replace(temporary, path)` (the summary).
- (plus `ohyesmlx.atomic_write_text`'s internal `os.replace`, outside S4's files: ledger at `fetch.py:346`, lab-paths at `engines.py:496`.)

**`disk_usage`**:
- `hardware.py:132 — def scan(run=_run, disk_usage=shutil.disk_usage, …)` (injectable).
- `hardware.py:148 — free_bytes = disk_usage(path).free` (per volume).

**`lock`** (53 raw grep hits including "clock"/"block"; the actual locking sites):
- `engines.py:904-925 — EngineLocks` (per-engine `threading.Lock`, non-blocking).
- `engines.py:913 — self._locks: dict[str, threading.Lock]`.
- `engines.py:919 — lock.acquire(blocking=False)`; `engines.py:925 — lock.release()`.
- `engines.py:951-952 — _RUNNING_STEPS + _RUNNING_STEPS_LOCK = threading.Lock()` (spawn/registration and kill-list).
- `engines.py:1247 — if not lock.acquire(engine)`; `engines.py:1340 — lock.release(engine)` (install's `finally`).
- `fetch.py:93 — DEFAULT_LOCK_DIR = …/locks`; `fetch.py:98 — LOCK_NAME = "download.lock"`.
- `fetch.py:366-390 — _acquire_lock` (`O_CREAT|O_EXCL|O_WRONLY, 0o644`, stale-pid reclaim, 2 attempts).
- `fetch.py:393-405 — _release_lock` (removes only while it names this pid).
- `fetch.py:706-708 — download acquires`, `fetch.py:718 — releases in finally`; `fetch.py:1216-1220 — evict acquires`, `fetch.py:1310 — releases in finally`.

**`sha256`**:
- `engines.py:697 — _HASHED_PIN = re.compile(… --hash=sha256:[0-9a-f]{64} …)`.
- `engines.py:740/744 — refusal texts naming the hash format`.
- `fetch.py:115 — PlannedFile.sha256`; `fetch.py:228-233 — plan() validates sha256 shape / both-and-neither`.
- `fetch.py:252 — sha256=item.sha256` (PlannedFile construction).
- `fetch.py:588-593 — _sha256_file` (hashlib.sha256, streamed).
- `fetch.py:619-620 — _verify: _sha256_file(path) == planned_file.sha256`.
- `fetch.py:894 — checked = "sha256" if …` (the failure message's rule name).
- `quickbench.py:588 — "source_sha256": measure._source_sha256()` (the summary's harness pin; hashed by `measure`, not here).
- `catalog.py:91 — ModelFile.sha256`; `catalog.py:77 — _SHA256` regex; `catalog.py:173-193 — _files validates and stores it`.

**`size`** (99 raw hits; field/constant mentions included so nothing is hidden):
- `engines.py:22 — (doc) the size before anything runs`; `engines.py:186 — size_bytes_estimate field`; `engines.py:657 — (comment) download sizes table`; `engines.py:755 — size_bytes_estimate=_GUIDED_SIZES[…]`; `engines.py:787 — (comment) wheel size not a footprint`; `engines.py:789 — size_bytes_estimate=None`; `engines.py:1043-1046 — _disk_required(size_bytes_estimate) = 2×, floor 2 GiB`; `engines.py:1325 — needed = _disk_required(plan.size_bytes_estimate)`.
- `fetch.py:63 — (comment) more than the catalog size`; `fetch.py:114 — PlannedFile.size`; `fetch.py:134 — Planned.size_bytes`; `fetch.py:251 — size=item.size`; `fetch.py:268 — size_bytes=sum(item.size …)`; `fetch.py:273-278 — (docstring) the sizes-only check and its price`; `fetch.py:290 — getsize(link) != size`; `fetch.py:294 — getsize(blob) != size`; `fetch.py:574-576 — _partial_size = getsize`; `fetch.py:596-598 — _git_blob_sha1(path, size)`; `fetch.py:615 — getsize(path) != size in _verify`; `fetch.py:621 — … == git_oid`; `fetch.py:735/743 — ledger entry bytes = size_bytes`; `fetch.py:764 — (log) files/bytes`; `fetch.py:775-778 — size_mismatch refusal helper`; `fetch.py:814 — remaining = max(0, size - _partial_size)`; `fetch.py:925-933 — have vs size (over/complete checks)`; `fetch.py:927-929/1000-1002/1030/1039/1042-1045/1049-1052/1104-1106/1113-1115 — the eight size_mismatch refusal sites (partial over size, 416, no Content-Range, wrong total, Content-Length over catalog, body over catalog, transfer ended short)`; `fetch.py:1073/1083 — over-size and progress gates in the write loop`; `fetch.py:1085/1100 — fraction math (bytes_done/bytes_total)`; `fetch.py:1137/1142/1158/1159/1162/1164 — accounted/progress bookkeeping`; `fetch.py:1171 — written = sum of not-present sizes`.
- `quickbench.py:120 — PlannedSibling.size_bytes`; `quickbench.py:298/304 — sibling size / missing bytes`; `quickbench.py:856/859 — the download progress event's bytes`.
- `catalog.py:4/13/28/63 — (docs) size rules and the starter cap`; `catalog.py:90 — ModelFile.size`; `catalog.py:107 — size_bytes == sum(files)`; `catalog.py:172 — _integer(…, "size", positive=False)`; `catalog.py:193 — ModelFile(size=size …)`; `catalog.py:230-234 — size_bytes must equal the files' sum`; `catalog.py:260 — Model(size_bytes=…)`; `catalog.py:273 — (doc)`.
- `recommend.py:9/104 — (docs)`; `recommend.py:76 — Pick.size_bytes`; `recommend.py:87-91 — _fit(size_bytes …)`; `recommend.py:108 — spare = budget - size_bytes`; `recommend.py:115 — the download size in the reason`; `recommend.py:133/136/141/186/198 — fit/exclusion/rank/Pick uses`.
- `hardware.py:135 — ram_bytes = int(run([SYSCTL, "-n", "hw.memsize"]))` (the only `size` hit in hardware.py).

**`resume`** (case-insensitive):
- `fetch.py:17 — (doc) Resume is a Range request`.
- `fetch.py:277 — (doc) the evidence a resume already trusts`.
- `fetch.py:769 — (message) the partial file is kept for a resume`.
- `fetch.py:1060 — (message) the server ignored the N-byte resume`.

**`Range:`** — as a header literal, one site:
- `fetch.py:935 — headers = {"Range": f"bytes={have}-"} if have else {}` (the resume request; `have` is the local partial's size).
- Related response-side: `fetch.py:87 — _CONTENT_RANGE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")`; `fetch.py:1026-1048 — the 206 Content-Range parse and its four refusal conditions`.

**`retry`**:
- `fetch.py:472 — (comment) the retry loop that must not retry a refused redirect`.
- `fetch.py:533-542 — _retry_delay` (429 Retry-After capped 60 s; else 0.5·2^n).
- `fetch.py:917 — (comment) progress kept across a retry`.
- `fetch.py:1014 — sleep(_retry_delay(response, attempts))` (429/5xx path; `MAX_ATTEMPTS` 4 shared across error kinds and short transfers).

**`json.loads`** (all on local files; none size-capped — listed because the order names "json.loads on unbounded input"):
- `engines.py:79 — load_manifest` (committed manifest).
- `engines.py:442 — lab_paths` (machine-local file).
- `fetch.py:320 — _ledger_load` (the fetch ledger).
- `quickbench.py:1042 — latest` (summary files under the results root).
- `catalog.py:282 — load` (committed catalog).

**`open(` with a write mode** (the order names `open(` with `w` on a path built from input):
- `engines.py:1155 — open(log_path, "a")` (`_append_install_log`; `log_path` injected, default under Application Support; follows a symlink — noted in threat-model §5).
- `fetch.py:387 — os.fdopen(descriptor, "w")` (the lock file, from `os.open` O_EXCL).
- `fetch.py:872 — open(planned.ref_path, "w")` (`refs/main`; the path is built from cache_dir + catalog `repo`/`revision`, both shape-checked by `plan`).
- `fetch.py:1066 — open(incomplete, "ab"|"wb")` (`.incomplete`; symlink refused at :908-914; T-14 covers the race to `open`).
- `quickbench.py:459 — open(temporary, "w")` (the summary temp beside the stamp dir).

**`subprocess` without a timeout** (every subprocess call site):
- `engines.py:1017 — subprocess.run([OPEN, url], check=False, stdin=subprocess.DEVNULL)` — **no timeout** (the one hit; `open` just hands the URL to LaunchServices and exits, and the plan's URL is allowlist-checked at :1300 before this runs).
- `engines.py:988-996 — subprocess.Popen(… start_new_session=True)` — bounded by `communicate(timeout=timeout_s)` at :1000 (`STEP_TIMEOUT_S` 900).
- `quickbench.py:188-195 — run([runtimes.PS, …], timeout=10)` — bounded.
- `hardware.py:63-70 — subprocess.run(…, timeout=TOOL_TIMEOUT_S, check=True)` — bounded.

**Broad `except`** (all bind `as error` or re-raise; none is a silent pass):
- `quickbench.py:662 — except Exception as error: blocked = str(error)` (recover/pin failure → cell skipped).
- `quickbench.py:690-693 — except Exception as error: return _cell_record(… FAIL)` (drift-check/keep failure).
- `quickbench.py:703-706 — except Exception as error: … FAIL` (run_cells failure).
- `quickbench.py:712-717 — except Exception as error: restored = False if pinned else None` (restore raising = restore not verified).
- `quickbench.py:757-760 — except Exception: if not abort(): raise` (the abort race; re-raises when not aborting).
- `quickbench.py:867-868 — except Exception as error: reason = …` (sibling download failure → skipped cell).
- `quickbench.py:922-928 — except Exception as error: … not_evicted` (evict raising → recorded).
- `quickbench.py:948-953 — except Exception as error: … not_evicted` (leftover sweep evict raising → recorded).
- `quickbench.py:464-466 — except BaseException: temporary.unlink(…); raise` (summary write cleanup).
- `quickbench.py:940-942 — except BaseException: summary["ended"] = "error"; raise` (the unexpected-raise ending).

**Swift pattern set** (`try!`, force-unwrap, `fatalError`, `DispatchQueue.main.sync`, `@unchecked Sendable`, uncancelled `Task {`, `print(`) — not applicable; S4's scope is `ohyesmlx/` Python and JSON only.

## 6. Test inventory

The test(s) that fail if each hotspot breaks, in hotspot order. Suite layout: `tests/test_engines.py` (100
tests), `test_fetch.py` (81), `test_quickbench.py` (59), `test_catalog.py` (44), `test_recommend.py` (29),
`test_hardware.py` (23), `test_paths.py` (10). All names verified present in the working tree.

1. evict containment/removal: `tests/test_fetch.py::evict_removes_exactly_the_ledger_paths`, `::evict_leaves_a_foreign_directory_untouched`, `::evict_keeps_a_foreign_file_inside_the_repo_directory`, `::evict_refuses_a_ledger_path_that_resolves_outside_the_cache`, `::evict_refuses_a_ledger_path_outside_that_repos_own_directory` (parametrised "where").
2. `_verify`: `tests/test_fetch.py::checksum_mismatch_removes_the_partial_and_links_nothing`, `::an_existing_non_lfs_blob_of_the_wrong_size_is_refused`, `::an_existing_non_lfs_blob_of_the_right_size_but_wrong_bytes_is_refused`.
3. resume/Range transfer: `tests/test_fetch.py::resume_sends_a_range_and_writes_only_the_remainder`, `::a_206_starting_elsewhere_is_refused`, `::a_200_to_a_range_request_restarts_from_zero`, `::an_expired_signed_url_is_resolved_once_more`, `::a_second_403_is_not_resolved_again`, `::a_content_range_with_the_wrong_total_is_refused`, `::a_content_length_larger_than_the_catalog_is_refused`, `::a_body_larger_than_the_catalog_is_refused`, `::a_cancelled_download_resumes_and_completes`.
4. present-blob pass: `tests/test_fetch.py::an_existing_blob_that_does_not_match_is_not_overwritten`, `::a_present_blob_is_reused_and_only_the_missing_file_is_requested`, `::a_present_blob_the_download_reused_is_never_evicted`, `::a_snapshot_link_pointing_elsewhere_is_refused_before_any_request`, `::a_regular_file_where_the_snapshot_link_belongs_is_refused_before_any_request`.
5. disk guards: `tests/test_fetch.py::disk_guard_counts_missing_bytes_not_the_total`, `::disk_guard_refuses_before_any_request`, `::the_disk_guard_is_rechecked_before_each_file`.
6. lock: `tests/test_fetch.py::a_live_lock_holder_makes_the_download_busy`, `::a_second_repo_is_refused_busy_while_a_download_holds_the_lock`, `::a_stale_lock_from_a_dead_pid_is_reclaimed`, `::the_lock_is_released_after_a_refusal`, `::a_live_lock_holder_makes_evict_busy_and_removes_nothing`, `::the_evict_lock_is_released_when_an_evict_raises`.
7. `downloaded`: `tests/test_fetch.py::downloaded_is_true_only_once_the_whole_tree_is_there`, `::downloaded_is_false_for_a_partial_incomplete_download`, `::downloaded_is_false_for_a_blob_of_the_wrong_size`, `::downloaded_is_false_when_a_snapshot_link_is_missing`, `::downloaded_checks_sizes_not_hashes`, `::downloaded_propagates_plans_value_error`.
8. rollback: `tests/test_engines.py::rollback_refuses_a_path_that_resolves_outside_the_engines_dir`, `::a_venv_that_existed_before_the_call_is_never_removed`, `::over_the_real_plan_a_failed_pip_step_rolls_back_and_a_success_records`.
9. run_steps/lab record: `tests/test_engines.py::two_steps_run_in_order_with_progress_after_each_and_done_last`, `::a_failing_step_stops_before_the_next_rolls_back_and_reports_the_tail`, `::a_successful_pip_install_records_its_venv_bin_and_engine_env_prefixes_it`, `::a_failed_pip_install_records_no_lab_path_and_keeps_the_others`, `::cancel_before_the_second_step_rolls_back_the_first`.
10. pip plan + hashed requirements: `tests/test_engines.py::mlxlm_plan_creates_the_pinned_venv_then_installs_the_tested_version`, `::optiq_plan_creates_the_pinned_venv_then_installs_the_tested_version`, `::every_pip_engine_has_a_constraints_file_for_its_tested_version`, `::the_committed_constraints_files_are_fully_hashed_and_pin_their_own_engine`, `::the_optiq_file_does_not_reintroduce_pygame`, `::the_hashed_requirements_validator_refuses_anything_but_hashed_pins`, `::a_file_ending_in_a_continuation_is_refused_as_unhashed`, `::an_unhashed_constraints_file_refuses_the_install_as_no_constraints`.
11. process groups: `tests/test_engines.py::a_step_runs_in_its_own_session_and_leaves_the_registry_empty`, `::a_step_that_times_out_kills_its_group_and_reports_the_timeout`, `::kill_running_steps_kills_every_registered_group`, `::the_step_lock_is_held_across_popen_and_the_registration`, `::a_kill_started_while_a_step_is_spawning_waits_for_and_kills_it`, `::each_step_is_bounded_by_the_injected_timeout`.
12. lab paths/PATH: `tests/test_engines.py::record_lab_path_refuses_a_directory_that_must_not_join_path`, `::record_lab_path_refuses_a_lab_dir_owned_by_another_user`, `::record_lab_path_writes_for_a_lab_dir_nobody_else_can_write`, `::record_lab_path_refuses_an_app_engine_and_writes_nothing`, `::a_lab_paths_file_that_is_not_json_is_refused_naming_the_file`, `::a_lab_path_for_an_app_engine_is_refused`, `::a_lab_path_for_optiq_reports_the_lab_copys_version_and_path`, `tests/test_paths.py::engines_takes_a_scratch_home`.
13. consent/lock order: `tests/test_engines.py::install_without_consent_runs_nothing_and_emits_its_refusal_then_done`, `::install_of_a_name_outside_the_five_refuses_before_anything_runs`, `::an_already_installed_engine_is_refused_before_the_lock_or_a_step`, `::a_held_lock_refuses_the_second_install_as_busy`, `::a_running_install_releases_its_lock_at_the_end`.
14. Osaurus pin lifecycle: `tests/test_quickbench.py::osaurus_is_recovered_pinned_and_restored_around_its_cell`, `::quickbench_pins_against_the_drift_guards_baseline_by_default`, `::the_host_pinned_between_pin_and_restore_shows_no_drift`, `::drift_between_pin_and_restore_fails_the_cell_and_keeps_both_copies`, `::no_drift_between_pin_and_restore_passes_and_keeps_nothing`, `::a_drift_check_that_raises_fails_the_cell_and_still_restores`, `::a_cell_that_raises_still_restores_osaurus`, `::a_restore_that_does_not_verify_ends_the_run_and_names_the_backup`, `::a_restore_that_raises_ends_the_run_exactly_as_a_false_one`, `::a_pin_that_refuses_skips_osaurus_with_that_reason`, `::an_aborted_osaurus_cell_still_restores_the_host_settings`.
15. sibling download/evict: `tests/test_quickbench.py::a_missing_sibling_is_downloaded_before_its_cell_and_evicted_after_it`, `::an_already_downloaded_sibling_is_neither_downloaded_nor_evicted`, `::the_chosen_repo_is_never_downloaded_or_evicted`, `::a_refused_sibling_eviction_is_logged_and_recorded`, `::an_evictor_that_raises_is_logged_and_recorded`, `::a_refused_sweep_eviction_is_logged_and_recorded`, `::nothing_not_evicted_leaves_an_empty_list`, `::cancel_after_a_sibling_download_evicts_it_and_measures_no_more`, `::an_abort_during_a_stage_b_cell_evicts_the_sibling_and_stops_there`.
16. winner/best attribution: `tests/test_quickbench.py::stage_a_names_the_winner_and_reports_cells_within_the_tie_band`, `::no_pass_cell_means_stage_b_does_not_run_and_the_summary_says_why`, `::a_stage_b_sibling_win_is_keyed_by_the_sibling_not_the_chosen_repo`, `::an_aborted_cell_is_never_the_winner_even_with_a_number`, `::stage_b_reuses_the_chosen_rows_row_and_measures_each_sibling`.
17. endings/summary: `tests/test_quickbench.py::every_ending_carries_the_summary_as_one_result_event_before_its_error`, `::an_unexpected_raise_still_carries_the_summary_as_a_result_event`, `::a_cancelled_run_stops_between_cells_and_writes_its_summary`, `::a_cancelled_ending_carries_the_summary_path_in_its_terminal_events`, `::a_restore_failed_ending_carries_the_summary_path_in_its_done`, `::the_summary_the_run_wrote_is_what_latest_reads`.
18. `latest`: `tests/test_quickbench.py::latest_returns_the_newest_finished_summary_per_repo`, `::latest_of_a_missing_root_is_no_summaries`, `::the_summary_the_run_wrote_is_what_latest_reads`.
19. fit math: `tests/test_recommend.py::comfortable_when_twice_the_weights_fits_the_budget`, `::tight_at_exactly_1_25_times_the_budget`, `::excluded_past_1_25_times_the_budget`, `::16_gib_mac_holds_the_8b_moe_as_tight`, `::8_gib_mac_holds_the_2b_oq4_as_tight_only`, `::8_gib_mac_excludes_the_8b_moe`, `::starter_tier_comes_first_when_free_disk_is_under_20_gib`, `::memory_still_excludes_a_downloaded_row`, `tests/test_hardware.py::model_budget_takes_two_thirds_of_ram_under_36_gib_less_two_gib`, `::model_budget_takes_three_quarters_of_ram_from_36_gib_less_two_gib`.
20. catalog validation: `tests/test_catalog.py::the_shared_path_guard_refuses_at_load`, `::size_bytes_that_is_not_the_sum_of_the_files_is_refused`, `::a_file_with_neither_a_sha256_nor_a_git_oid_is_refused`, `::a_file_with_both_a_sha256_and_a_git_oid_is_refused`, `::every_entry_pins_a_commit_and_a_hash_for_its_weights`, `::every_entry_sizes_sum_to_its_files`.

Not covered by any test (the gaps behind §7): a crash mid-pip leaving a half venv that `detect_all` reports
installed (§7 Q2 — `install`'s rollback path is tested, the no-process-left-to-rollback path is not); the disk
guard's volume identity when the cache is not on the root volume (§7 Q3 — all fetch tests run one tmp_path for
both); `quickbench` measuring a right-size wrong-bytes cached artifact (§7 Q1 — `downloaded`'s size-only
semantics are tested as correct, the downstream use is not); retry-exhaustion deleting a resumable partial
(§7 Q8 — the retry paths are tested, the `remove=incomplete` side effect of the short-transfer exhaustion is
asserted only as the refusal).

## 7. Open questions for the reviewer

Falsifiable, with locations. Each is suspected, not proven; the two the order names (data-loss paths, fit-math
edges) and the two it pre-states (P5-11, listed §3) are included where they surface concretely.

1. **A cached-but-wrong artifact is measured and published with no re-verification.** `quickbench.plan`
   (quickbench.py:283) gates on `fetch.downloaded` (fetch.py:272-298), which is sizes and links only, and
   `run.measure_cell` (quickbench.py:669-677) hands the snapshot to `run_cells` as-is; `fetch._verify`
   (fetch.py:605-621) runs only inside `download`. A right-size wrong-bytes artifact (a user copy, or the
   hero-model re-serialisation case in STATE, where `downloaded()` reads False but a same-size corruption would
   read True) passes the gate, is measured, and `_best` (quickbench.py:398-428) attributes its number to a
   catalog row. The coherence gate may catch garbage text, but a subtly wrong quantization still produces
   language. Should a quickbench cell verify the blobs it is about to measure (hashes are in the catalog), or at
   minimum record in the summary that the artifact was not re-verified?

2. **A crash mid-pip leaves a half venv that `detect_all` reports as installed — is there a repair path?**
   `run_steps` rolls back only within its own process (engines.py:1278); a SIGKILL of the app (or
   `kill_running_steps` at shutdown expiry, engines.py:963-974, whose docstring says the rollback "runs in its
   thread once the step returns" — which a SIGKILL prevents) leaves `<engines_dir>/<name>-<ver>` partially
   built. `_detect_mlxlm`/`_detect_optiq` (engines.py:541-563, 526-538) probe for the console script; pip writes
   entry points late, so the exposure is a venv where pip died after entry-point creation. Then `detect_all`
   says `installed: true` and `install` refuses `already_installed` (engines.py:1242-1245) forever. The
   `existed` guard (engines.py:1265-1269) records only roots that did not exist before the call, so a retry
   after a crash is never rolled back either. Does the app need a "remove and reinstall" path, or should
   detection require more than the script's existence (e.g. `--version` or the dist-info)?

3. **The disk guard measures the root volume even when the cache lives elsewhere.** `fetch._download`'s guards
   ask `hardware().disk_free_bytes` (fetch.py:819 and 1146), which `hardware.scan` defines as the root volume's
   free bytes (hardware.py:151-152), while the write goes to `cache_dir` — `HF_HUB_CACHE` may name any volume
   (fetch.py:137-149) and D8 says "the user may pick another volume". A full startup disk and a nearly-full
   external cache passes the guard and fills the external volume; the reverse over-refuses. `recommend`'s
   `free_disk` has the same identity (the server passes `hw.disk_free_bytes`). Should the guard ask
   `shutil.disk_usage(cache_dir)`'s volume instead, or is the root volume the documented budget deliberately?

4. **`evict`'s reference scan sees only `models--*/snapshots` symlinks; a user link elsewhere is invisible.**
   `_referenced_blobs` (fetch.py:638-654) walks the cache's snapshot trees for symlinks. If the user points
   their own symlink (or a hard link) at a ledgered blob from outside that layout — say `~/mymodel ->
   ~/.cache/huggingface/hub/models--org--name/blobs/<sha>` — evict (fetch.py:1261-1277) deletes the blob and
   their link dangles. The blob was this app's, but the bytes the user was relying on are gone with no warning.
   Is that within "Evict removes only what this module created" (the blob is ours), or should the scan also
   cover the ledgered blobs' link counts / a wider symlink pass? (The order's data-loss question.)

5. **`record_lab_path` raising after a successful pip install escapes `install` without rollback or events.**
   engines.py:1294-1295 runs it outside any try; `check_lab_dir` can refuse the venv's `bin` (e.g. a group-writable
   directory under a shared-venv umask). Then `install` raises through `run_steps` → the `finally` releases the
   lock → the server reports `internal`, no `error`/`done` carries the module's code, and the completed venv is
   neither recorded on lab-paths nor rolled back. This is the 04-03b deviation ("worker's call; no pinned
   code"). Should it be a failed step (rollback + `step_failed`) instead of a raise?

6. **Fit/reason arithmetic edges.** (a) `recommend._reason` prints "about X GB of memory to spare" with
   X = budget − size_bytes (recommend.py:108), while fit is decided on 2×/1.25× (recommend.py:87-93) and the
   documented worst-case peak is ~2× (comment at :32-35) — a tight row can read "Tight fit, about 8 GB of
   memory to spare" while peak use exceeds the budget it was judged against. Should the template subtract the
   peak factor? (b) `model_budget` steps from ⅔ to ¾ of RAM at exactly 36 GiB (hardware.py:107): 35 GiB → 21.3
   GiB budget, 36 GiB → 25 GiB. Is that discontinuity the cited Apple wired-memory ceiling, and is 36 GiB the
   right threshold? (c) An 8 GiB Mac passes `_support` (strict `<`, hardware.py:95) with a 3.33 GiB budget —
   matches D1's "under 8 GB", but the comment at :33-34 says below 8 GiB "there is not enough unified memory for
   the smallest model"; is the smallest catalog row actually comfortable there (the test `8_gib_mac_holds_the_2b_oq4_as_tight_only` pins 2B-oQ4 as tight, not 0.6B as comfortable)?

7. **A finished run whose stage B measured nothing reports no `best` at all.** `_best` (quickbench.py:398-411)
   reads stage B's cells whenever `stage_b.engine` is set — which happens as soon as stage A has a winner (:833)
   — so a stage B where every cell FAILed or was SKIPPED yields `best: None` although stage A produced a PASS
   winner, and `latest` then fills no `measured_here`. The interface says "a run that stopped at stage A offers
   A's winner" and "`best` is non-null only on a finished run" (v5-quickbench.md L201-202) but is silent on
   "finished with a fruitless stage B". Intended (a run that could not compare formats offers nothing), or
   should it fall back to A's winner?

8. **Retry exhaustion on a short transfer deletes the resumable partial and reports `size_mismatch`.**
   `_fetch_file`'s `attempts` is shared across connection errors, 429/5xx and short transfers (fetch.py:916-1120);
   when a flaky server keeps ending the body early, the fourth short read takes the `size_mismatch` path with
   `remove=incomplete` (fetch.py:1112-1118) — multi-GB of resumable bytes are deleted and the code reads as
   corruption ("size_mismatch") rather than exhaustion, while a user cancel keeps the same partial deliberately
   (fetch.py:766-773). Is the deletion intended (a stale partial would resume against a wrong base), or should
   exhaustion keep the partial and report `http_error`? (The order's data-loss question, download side.)
