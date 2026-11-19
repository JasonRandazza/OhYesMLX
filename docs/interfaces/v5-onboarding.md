# v5 onboarding — interface shapes

The v5.0 onboarding shapes pinned at T0.2: hardware, engines, catalog, recommendation, install, fetch, the localhost API and its job stream, and quickbench.

## v5.0 — Onboarding shapes (pinned 2026-10-29, T0.2)

Plan and seams: `.paul/phases/v5-onboarding/PLAN.md`. These shapes are the coupling between the Python
modules, the localhost API and the Swift client; change one here first. All JSON is UTF-8, keys snake_case,
sizes in bytes, no floats for byte counts.

**`Hardware`** (`hardware.scan(run=...) -> Hardware`; `GET /hardware`)
`{"supported": bool, "unsupported_reason": str|null, "chip": "Apple M2 Max", "family": "M2", "tier": "base|pro|max|ultra",
"cpu_cores": int, "gpu_cores": int|null, "ram_bytes": int, "macos": "15.4", "disk_free_bytes": int,
"disk_total_bytes": int, "volumes": [{"path": str, "free_bytes": int}], "model_budget_bytes": int}`
`supported` is false off Apple Silicon or under 8 GiB RAM; every other field is still reported. `model_budget_bytes`
is defined once, in `hardware.py`. `disk_free_bytes` and `disk_total_bytes` are the free and total space of the same
volume -- the one the Hugging Face cache lives on -- and both come from one `hardware.disk_bytes_at` call.

**`EngineStatus`** (`engines.detect_all(env) -> list`; `GET /engines`)
`{"name": "osaurus|omlx|optiq|mlxlm|vmlx", "title": str, "blurb": str, "installed": bool, "version": str|null,
"path": str|null, "tested": bool, "verified": str|null, "install": Plan|null}`. Names and ports come from `runtimes.py`.
`tested` is the installed version against `ohyesmlx/engines-tested.json`, and `verified` is that manifest's ISO date
for the build (present whether or not the engine is installed; added 2026-10-29, plan 025-01).
`detect_all` returns `install: null`; the server composes `install_plan(name, macos)` into `GET /engines` (Phase 4).

**Lab paths** (`engines.lab_paths(path=LAB_PATHS_FILE) -> {engine: bin directory}`, machine-local, plan 025-03)
`~/Library/Application Support/OhYesMLX/lab-paths.json` is the only place a real lab path is written; the committed
manifest stays `lab_path: null` everywhere. A missing file is `{}` and invalid JSON, an unknown engine key, or any
app engine (`osaurus|omlx|vmlx`, whose builds are archived rather than run from a lab path) raises `ValueError`
naming the file and key. Only `mlxlm` and `optiq` may name one. `runtimes._engine_env` prefixes these directories to
`PATH` (the file overriding the manifest's `lab_path` per engine, and still refusing a directory that is not there),
and `detect_all` looks in them first, so a canary reports the lab copy's version rather than the global install's.

**App-bundle executables** (`runtimes.ENGINE_BUNDLE_EXECUTABLES`, 045-03). The one table mapping `omlx`, `vmlx`
and `osaurus` to the executable their `.app` ships (`osaurus`'s derived from `OSAURUS_APP_BUNDLES`:
`Contents/Helpers/osaurus`, the tool its shim points at — not the `Contents/MacOS/osaurus` app binary
`OSAURUS_APP_EXECUTABLES` names). `runtimes._resolve_program(command, env) -> tuple[str, ...]` is its only reader,
called by `_spawn` and `_run` only: when the command's program token — the first token that is not `env` or a
`K=V` assignment, since a vMLX depth cell's command starts `env VMLX_...=0 VMLX_...=0 vmlx` — does not resolve
with `shutil.which(token, path=env["PATH"])` and the table holds an existing executable for it, that path is
exec'd instead; otherwise the command is returned unchanged and `_spawn`'s existing `OSError` path reports it. A
name that resolves on the engine PATH is untouched, so a developer shell's per-user shims still run, and
`start_command`, headers and rows stay byte-identical: only the exec'd argv changes. A shipped app's PATH is
launchd's (threat-model P5-9), which is where the bare names failed with `[Errno 2]`.

**`Plan`** (`engines.install_plan(name)`; data only, no side effects)
`{"engine": str, "kind": "guided_download|command", "source_url": str, "size_bytes_estimate": int|null,
"needs_admin": bool, "steps": [{"id": str, "label": str, "command": [str]|null}]}`.
`guided_download` (Osaurus, oMLX, vMLX) opens `source_url` and verifies afterwards; `command` runs `steps`.

**`Model`** (`catalog.load(path=CATALOG_PATH) -> list[Model]`; the seed is `ohyesmlx/catalog.json`, plan 03-01)
`{"repo": "org/name", "base": str, "title": str, "params": int, "format": str, "modality": "text|vision-language",
"license": str, "tier": "starter|standard", "revision": "40-hex commit", "size_bytes": int,
"files": [{"path": str, "size": int, "sha256": "64-hex|null", "git_oid": "40-hex|null"}],
"engines": ["mlxlm|osaurus|omlx|optiq|vmlx"], "measured_here": bool, "notes": str}`.
`base` names the **base model** a format was quantized from (e.g. `"Qwen3.5-2B"`): the same string on
every format of one base and a different one across bases, a non-empty string (plan 04-03a), so
`catalog.siblings(model, models) -> list[Model]` answers the model's other formats from the data, in
catalog order. `params` is the **base** model's count, never the artifact's `safetensors.total` (research §1.1). `size_bytes`
is the sum of `files`, which holds every file the tree listing has, so it is what the disk pays. An LFS file
carries `sha256` (the listing's `lfs.oid`) and a plain git file carries `git_oid`, never both and never
neither — one of them is what a download verifies, and `fetch._verify` holds the one definition of how.
`revision` and every file's size and hash come from one
tree listing at that commit, so a downloader never asks "what is latest". `engines` is the research table's
column, and `measured_here` is true only where a `results/**/results.jsonl` row exists for that exact
artifact. A violation raises `ValueError` naming the file, the repo and the field.

`catalog.check_path(where, path)` is the one file-path guard: `_files` applies it to every row at load and
`fetch.plan` applies it to the row it is handed. `catalog.disk_needed(nbytes) -> int` is
`ceil(nbytes * DISK_MARGIN)`, the one disk-margin rule `recommend` and `fetch` both ask.

**`Pick`** (`recommend.pick(hw, models, engines, free_disk, downloaded=frozenset()) -> list[Pick]`, pure; plan 03-02)
`{"model_id": str, "title": str, "params_b": float, "format": str, "size_bytes": int,
"fit": "comfortable|tight", "fit_basis": "estimated", "engines": [str], "install_needed": bool,
"start_here": bool, "reason": str, "downloaded": bool, "measured_here": object|null,
"mismatch_on_disk": "ours"|"foreign"|null}`.
`model_id` is the catalog row's repo id and `params_b` the **base** count in billions, one decimal.
`fit` is an estimate from `Hardware.model_budget_bytes` alone -- comfortable when twice `size_bytes`
fits it, tight when 1.25x does, otherwise the row is left out -- and `fit_basis` is always
`estimated`, so a fit is never read as a measurement. `engines` lists the installed engines from the
row's own `engines`; when none is installed it lists the row's catalog engines with
`install_needed: true` ("install X first"). `start_here` marks the first three after ranking:
comfortable before tight, then larger `params`, starter tier first only while free disk is under
20 GiB, ties by repo id. `reason` is a fixed template with numbers in decimal GB (1e9 bytes, one
decimal) and carries no speed claim; a `downloaded` row's template says it is already on this Mac
and names no download size. `downloaded` is true when every file `fetch.plan` names has its
snapshot link present and resolving to a blob of the catalog size (`fetch.downloaded(model,
cache_dir=None) -> bool`, sizes and links only, never hashes, never writes; `plan`'s `ValueError`
propagates). Such a row is exempt from the **disk** budget because there is nothing left to
download, and still answers to memory. `measured_here` is non-null only for a run on this user's
Mac (Decision D5); it is null until a finished quickbench summary names the row, and is never filled from our M2 Max
rows. `pick` takes it as an optional `measured_here={repo: block}` argument (plan 04-03b), so the module still reads
no file itself.

Memory sentences quote the factor of the line that decided the row (S4-F6, plan 05-11): a left-out row reads
"Needs about {size x 1.25, rounded up} GB of memory; this Mac's budget is {budget} GB", and an offered row's
"about N GB of memory to spare" is `budget - size x factor` (2.0 comfortable, 1.25 tight).

`mismatch_on_disk` (P5-11, plan 05-11; `fetch.mismatch_on_disk`, stat-only) is null unless a finished blob of a
not-downloaded row sits on disk at a size the catalog does not pin; a `.incomplete` partial alone is null (it is a
resumable Download). `"ours"`: every such blob is in this app's fetch ledger, so Download repairs it -- the app's
button reads **Re-download**. `"foreign"`: `fetch.download` refuses to overwrite a blob it did not write
(`integrity_failed`), so the app offers no download button and says, without the word "corrupt", that the files
already on this Mac don't match and must be removed from the Hugging Face cache before downloading again.

`recommend.exclusion_reason(model, hw, free_disk, downloaded=frozenset()) -> str | None` is the pure
companion for the rows `pick` leaves out: a fixed-template reason naming the memory or disk
shortfall, null for a row that clears both budgets (and for a repo in `downloaded`, whose disk
budget is not applied). `GET /recommendations` (Phase 4) composes
`{"picks": [Pick], "excluded": [{"model_id": str, "reason": str}], "unsupported_reason": str|null}`
from these two functions, building `downloaded` from `fetch.downloaded` over the catalog: `excluded`
is the rows `exclusion_reason` answers non-null for, and on an unsupported Mac `picks` is empty and
`unsupported_reason` carries `Hardware.unsupported_reason` -- the recommender never copies that
sentence into a reason.

**Job** (`POST /jobs` body `{"kind": "install|download|evict|quickbench", "args": {...}}` -> `202 {"job_id": "16-hex"}`)
`args` is the closed set `{"engine": str, "confirmed": true}` for `install`, `{"repo": str, "confirmed": true}` for
`download` and `evict`, and `{"repo": str, "confirmed": true, "osaurus": bool}` for `quickbench`: an extra key, a
missing key, a non-string name, a `confirmed` that is not JSON `true`, or an `osaurus` that is not a JSON bool is
`400 bad_args` naming the key, and an unknown kind is `400 bad_kind`. `confirmed`
is the client's statement that its UI showed this action and the user chose it; the server cannot verify a human, so
Phase 5 sends it only from a user gesture. The server validates no engine name, repo id, version, path or disk number
itself: an unknown name is the module's own refusal (`unknown_engine`, `unknown_repo`), delivered as the job's `error`
and `done` events, and a module that raises still ends the stream with `error` payload `{"code": "internal"}` and
`done`, continuing the job's seq. An `evict` refuses `busy` while a download or another eviction holds
`download.lock` -- the ledger it rewrites is the one a download also writes -- and nothing is removed
(045-02b AC-4). A `low_disk` refusal carries `free_bytes` and `needed_bytes` (JSON integers) in its
`error` payload -- the same two numbers its message prints, so a client computes how much to free
without parsing English or restating the disk margin. A non-JSON Content-Type is
`415 unsupported_media_type`; a missing, non-integer or
over-4096 `Content-Length` is `413 body_too_large` and the body is never read; invalid JSON is `400 bad_json`. One job
runs at a time: a second `POST /jobs` is `409 busy` naming the running job's id, and the slot frees the moment its
`done` event is stored. Jobs are not persisted; they live as long as the process.
Events on `GET /jobs/{id}/events` (server-sent events), one JSON object per `data:` line:
`{"seq": int, "type": "progress|log|result|error|done", "message": str, "fraction": float|null, "payload": object|null}`.
Each event is framed `id: <seq>\ndata: <event JSON>\n\n` in seq order. An unknown job id is `404 unknown_job`; stored
events replay first, a `Last-Event-ID` request header resumes after that seq (non-integer or negative is
`400 bad_event_id`, one beyond the last stored seq waits for new events), a `: keepalive` comment is written every 15 s
while nothing arrives, and the server closes the connection after `done`, so a finished job replays everything and
closes. A job has at most `MAX_STREAMS_PER_JOB` (4) event streams open at once; a fifth is `429 too_many_streams`,
the four already open keep streaming, and a slot comes back however a stream ends -- `done`, an exception, a
disconnect or the write timeout. A job keeps at most 10,000 events; past that it is ended with `error` payload
`{"code": "too_many_events"}` and `done`. The stream waits on the job's condition, never on the socket, so a quiet
job is not cut off; the socket timeout stays set and bounds each write, so a client that stops reading releases its
handler thread at the first blocked send.
`POST /jobs/{id}/cancel` answers `202` and makes the `cancel` callable the module holds answer True from then on; a
download stops at its next chunk, an install only between steps and between guided-download polls (never inside a
running pip step, whose own 900 s timeout and the installer's rollback still apply), a quickbench run only between
cells (its in-flight cell's stop path, sibling eviction and Osaurus restore still run, and the run ends `cancelled`
with a summary), and the stream ends with the module's own cancelled `error`/`done`. Cancelling an `evict` is
`409 not_cancellable`; a finished job is
`409 job_finished`; an unknown id is `404 unknown_job`. An optional body `{"now": true}` stops a
quickbench mid-cell instead of between cells; its refusals are `v5-app.md`'s (**Backend addition:
"Stop now"**).
Shutdown (stdin EOF, `SIGINT`, `SIGTERM`) cancels a running install, download or quickbench at its next check and
waits for any
running job at most 120 s, then exits 0; an evict is waited for, never cancelled. When the 120 s bound expires with
a job still running, the server kills the process group of every install step still in flight
(`engines.kill_running_steps()`) and waits at most `JOB_KILL_GRACE_S` (15 s) more for the job's own rollback and its
`done` (045-02a AC-6); a job that outlives even that grace is abandoned with one stderr line
`{"error": {"code": "shutdown_abandoned", "job": id, "kind": str}}`, never silently. Each job start writes one
stderr line
`{"job": id, "kind": str, "name": str, "time": iso}` and each end one `{"job": id, "ok": bool, "code": str|null,
"time": iso}` — never a token or a header value.
A download's in-flight `progress` events carry `fraction` = (bytes of files already finished + bytes
written so far of the current file) / the model's total bytes and payload
`{"path": str, "bytes_done": int, "bytes_total": int}` (the same numerator and the model's total, so a
resumed download starts from the bytes already on disk). They are emitted at most once per 0.5 s of the
injected clock and only when `fraction` has advanced by at least 0.005 since the last one, so a multi-GB
download emits on the order of a few hundred events rather than one per chunk, and a file no larger than
one chunk emits none. Each finished file still emits one `progress` with payload `{"path", "bytes"}`.

**Errors** are `{"error": {"code": str, "status": int, "message": str}}` with a 4xx/5xx status; `status` repeats the HTTP status (added 2026-11-02, Jason) so a body read on its own still names it. The server binds 127.0.0.1 only.

**`ohyesmlx app [--port N]`** (`ohyesmlx/server.py`, plan 04-01) is the only thing the Swift client talks to.
It binds `127.0.0.1` only — never `0.0.0.0` and never `::` — to an ephemeral port unless `--port N` is given, and
before serving it writes exactly one line to stdout, `{"port": int, "token": str}`, where the token is
`secrets.token_urlsafe(32)`, fresh per launch and never written to disk, argv or a log (the client holds the pipe).
Every request passes one guard before the router sees it, in this order: a `Host` that is not exactly
`127.0.0.1:<port>` or `localhost:<port>` — including an absent one — is `403 bad_host`; any `Origin` header at all is
`403 origin_refused`; anything but `Authorization: Bearer <token>` is `401 unauthorized`, compared as UTF-8 bytes with
`hmac.compare_digest` so a non-ASCII header value is a 401 and never a 500. The token is the primary control: a
cross-site `<img>` or navigation carries no `Origin` and a correct `Host`, and only the token stops it. `GET /hardware`,
`GET /engines`, `GET /recommendations` and `GET /quickbench/plan` answer the shapes above and the job routes answer theirs; an authorised
request to any other path is `404 not_found`, a non-GET on one of those GETs is `405 method_not_allowed`, a
`ValueError` from `engines.install_plan`
is `500 install_plan_failed` naming the engine, and any other module exception is `500 internal` carrying the
exception's message and no traceback. Every JSON response is `Content-Type: application/json; charset=utf-8` with
`Cache-Control: no-store`, and an event stream is `Content-Type: text/event-stream` with the same `no-store`; no
`Access-Control-*` header is ever sent, `OPTIONS` included; the handler stays on
HTTP/1.0, so one request is one connection, handler threads are daemons, a connection idle for 10 s is closed, and
at most `MAX_HANDLER_THREADS` (32) handlers exist at once: a connection that arrives with every slot held is closed
with no response and no thread. Each guard refusal writes one JSON line to stderr, `{"refused": code, "method",
"path", "time"}` — never a header value or the token, with the query string dropped, and with `path` written only
when it is a served route (`/hardware`, `/engines`, `/recommendations`, `/quickbench/plan`, `/jobs`, or the job path
pattern) and `<unknown>` otherwise, because a request path is client text too — while a served GET writes nothing
(the access log is silenced); a job writes only the start and end lines pinned above, so the client can surface a
probe without handling a secret. `ohyesmlx app` creates its Application Support directory (`ohyesmlx.app_support_dir()`,
`~/Library/Application Support/OhYesMLX`) `0700` before it serves, and `ohyesmlx quickbench` does the same before a
confirmed run writes anything. The server dies with its parent: stdin reaching EOF,
`SIGINT` or `SIGTERM` shuts it down, releases the port and exits 0 — which means `ohyesmlx app </dev/null` exits at
once by design, because EOF on stdin *is* the parent-death signal. A socket that cannot be bound prints nothing on
stdout, writes one `{"error": {"code": "bind_failed", "message": str}}` line to stderr and exits 2, so the client can
tell a refusal from a hang.

**`canary`** (`ohyesmlx canary [--engines a,b] [--record] [--allow-noisy] --yes`; `ohyesmlx/canary.py`,
plan 025-02) — Decision 135's drift check, a CLI surface rather than a JSON shape. One fixed cell per
engine, taken from that engine's `canary` block in `ohyesmlx/engines-tested.json`
(`{"format": str, "repo": str, "workload": "decode", "decode_tok_s": float|null, "ttft_s": float|null,
"measured": str|null, "version_measured": str|null}`; the four baseline fields are null until a
`--record` run writes them), measured one engine at a time in manifest order through
`cli.build_cells` + `measure.run_cells` on the `decode` workload alone. `--cells` stays the only cell
selector: `canary.cells(engine, spec)` writes that cell as a `--cells` string and nothing else chooses
one. `canary.verdict(baseline, measured, floor=canary.NOISE_FLOOR)` is the pure comparison — the
worst-moved of `decode tok/s` / `TTFT` past the ~5% session bar (Decision 131) — and a row that is not
`PASS` is `FAIL: <reason>` and is never compared. `canary.LOAD_NOISY` (4.0) against the 1-minute load
average read before and after each cell marks a reading `noisy`, and `--record` refuses a noisy engine
unless `--allow-noisy` is passed. Without `--yes` the quiet-machine rule and the 10-15 minute estimate
are printed and nothing starts. `--record` writes the detected version, the date and the baseline only:
the tested `version` and its `verified` date are never adopted silently.


