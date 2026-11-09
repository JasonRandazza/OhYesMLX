# OhYesMLX v5.0 backend: threat model and attack-surface review

Phase 4.5, plan 045-01 (2026-11-03). This document covers the Python backend that the v5.0 SwiftUI app
(Phase 5) will spawn: the localhost API (`ohyesmlx app`), the installers, the model downloader, quickbench and
the harness code quickbench reaches. Its purposes:

- record what is exposed, to whom, and on what assumption;
- list every finding, with a verdict reached by reading the code;
- record the disposition of each finding: fixed in plan 045-02, carried into the Phase 5 packaging checklist,
  or accepted.

This review changes no code. The fixes are plan 045-02.

> **Disclosure rule (045-01 AC-5b).** The repository is public. Some confirmed high or medium findings may not
> be fixed yet. For each of those, this document gives only the id, severity and area. Its reproduction detail
> is kept in a local, gitignored file and moves into this document in the commit that fixes it.

Related documents: `docs/interfaces.md` (the pinned API and job shapes), `AGENTS.md` (runtime hazards),
`.paul/phases/v5-onboarding/PLAN.md` (decisions D1-D10).

---

## 1. Scope

**In scope.**

- `ohyesmlx/server.py`, `engines.py`, `fetch.py`, `quickbench.py`, `osaurus_settings.py`, `hardware.py`,
  `catalog.py`, `recommend.py`, and the `app` and `quickbench` paths in `cli.py`.
- `runtimes.py` and `measure.py`, as far as quickbench reaches them: engine start and stop, the PATH built from
  lab paths, logs and scratch directories.
- The data files these read and write: `engines-tested.json`, `catalog.json`, `constraints/*.txt`,
  `lab-paths.json`, the fetch ledger and logs, the install log, quickbench summaries, the Osaurus pin backups
  and the drift-guard baseline.

**Out of scope.**

- The CLI measurement paths that the app never reaches: `run`, `grid`, `sweep` and `canary`. These are a
  developer tool run by hand.
- The serving engines themselves (Osaurus, oMLX, vMLX, mlx-lm, OptiQ). They are third-party processes that the
  harness starts.
- The SwiftUI client. It does not exist yet, so its requirements are in the checklist (section 9) rather than
  reviewed as code.

## 2. Assets

| Asset | Why it matters |
|---|---|
| The per-launch token | Whoever holds it can drive every endpoint, including installs, downloads, evictions and quickbench. It exists only in the server object (`server.py:837`) and in the one stdout line the CLI prints to the parent app (`cli.py:1091`). |
| The user's files and Hugging Face cache (`~/.cache/huggingface/hub` or `HF_HUB_CACHE`) | `evict` deletes from the cache, and `download` writes into it. A path that escapes the cache is data loss. |
| Osaurus host config (`~/.osaurus/config/server{,-runtime}.json`) and the drift-guard baseline (`config/osaurus-settings-baseline.json`) | quickbench pins these and restores them. If a restore is missed, the user's own Osaurus keeps running under settings they did not choose. |
| Installed engines (`~/Library/Application Support/OhYesMLX/engines/*`) and `lab-paths.json` | `lab-paths.json` decides which binaries every engine start executes. `runtimes._engine_env` (`runtimes.py:433-487`) puts its directories at the front of PATH for each spawned server and each helper command. Whoever can write it chooses the code that runs. |
| The fetch ledger (`fetched.json`), fetch log, install log, quickbench summaries | The ledger is what `evict` trusts to know what it may delete. The logs and summaries are the user's local record. |
| The user's consent | Every action that changes the machine requires `confirmed: true` from the client. quickbench also takes an explicit boolean before pinning Osaurus. |
| Machine availability | One model resident at a time, ports released, no orphaned engine servers holding GPU memory. |

## 3. Actors

| Actor | In scope? | Reason |
|---|---|---|
| A web page in the user's browser, including DNS rebinding | **In** | Any page can send requests to 127.0.0.1. A rebinding page gets a foreign `Host`. |
| Another process running as the same user | **In, limited** | It can already edit `~/.zshrc`, the user's files and every file this app writes, so nothing here can be kept from it. Findings that only such a process can trigger are rated at most medium. What is in scope is whether the app makes that process's job *easier*, or leaves the user's state wrong without saying so. |
| Another local account on the same Mac | **In** | Loopback ports are reachable by every local user. Files under the user's home are readable by others when their mode allows it. |
| A LAN or Tailscale peer | **In** | Covered by the bind address: the server binds `127.0.0.1` only (`server.py:48`). |
| A compromised or spoofed upstream: PyPI, Hugging Face (including its CDN and xet redirect hosts), GitHub releases | **In** | The installer runs pip, the downloader fetches weights, and guided installs open release pages. |
| Root, physical access, a compromised OS | **Out** | Nothing an unprivileged user-space app can do defends against these. |

## 4. Trust boundaries

| Boundary | The assumption it rests on |
|---|---|
| Browser → localhost API | Loopback bind, an exact `Host` match and refusal of any `Origin` stop rebinding and cross-site reads. The token stops blind cross-site writes, because a cross-site `<img>` or navigation carries no `Origin` and a correct `Host` (`server.py:17-23`). |
| Other local account → localhost API | The 256-bit token (`secrets.token_urlsafe(32)`), which travels only over the parent's stdout pipe. Availability is not protected by it (see the probe results in section 6). |
| API → modules | The server passes a name string, a literal `true` and, for quickbench, one boolean. Nothing else reaches a module (`server.py:79-90`, `_args_problem` at `server.py:243-268`). Every name is resolved against a committed allowlist: the five engines, the catalog rows, the ledger's keys. |
| Installer → pip and PyPI | Exact version pins from committed constraints files (`engines.py:660-665`), run in a venv under Application Support with `PYTHONPATH` and `PIP_*` dropped (`engines.py:870-882`). The pins are versions, not hashes. |
| Downloader → Hugging Face | https only, to `huggingface.co`, `hf.co` and their subdomains, including redirects (`fetch.py:152-168`, `fetch.py:433-445`). Each file is checked after transfer against the catalog's sha256 or git blob id (`fetch.py:572-588`). Certificate verification is the Python default. |
| Harness → engine processes | Lab-path directories go at the front of PATH (`runtimes.py:470-486`). Servers are spawned in their own session (`runtimes.py:518-525`) and stopped by process group, or by the pids listening on their port. |
| App → user-owned state (Osaurus config, HF cache) | Byte-exact backup and restore (`osaurus_settings.py:225-330`). `evict` removes only paths the ledger recorded, after checking each one resolves inside the cache (`fetch.py:1180-1189`). |

## 5. Entry points

### 5.1 HTTP routes (`server.py`)

Every method is routed through one guard first (`do_GET` … `do_OPTIONS`, `server.py:332-356`; the guard is at
`server.py:358-376`).

| Route | Method | Handler | Changes the machine? |
|---|---|---|---|
| `/hardware` | GET | `_get_hardware` `server.py:450` → `hardware.scan` | No |
| `/engines` | GET | `_get_engines` `server.py:454` → `engines.detect_all`, `install_plan` | No |
| `/recommendations` | GET | `_get_recommendations` `server.py:478` → `recommend.pick`, `fetch.downloaded`, `quickbench.latest` | No |
| `/quickbench/plan?repo=` | GET | `_get_quickbench_plan` `server.py:531` → `quickbench.plan` | No |
| `/jobs` | POST | `_post_job` `server.py:569` | Yes, via the job kinds below |
| `/jobs/{16 hex}/events` | GET | `_get_job_events` `server.py:683` (SSE) | No |
| `/jobs/{16 hex}/cancel` | POST | `_post_job_cancel` `server.py:668` | Sets a cancel flag |
| anything else | any | 404 / 405 | No |

### 5.2 Job kinds and their accepted arguments (`server.py:81-90`)

| Kind | Args (closed set) | Module | What the module allowlists |
|---|---|---|---|
| `install` | `engine: str`, `confirmed: true` | `engines.install` `engines.py:999` | One of five engine names. The plan is derived inside the module and never supplied by the caller. |
| `download` | `repo: str`, `confirmed: true` | `fetch.download` `fetch.py:629` | Catalog rows only (`fetch.py:659-663`) |
| `evict` | `repo: str`, `confirmed: true` | `fetch.evict` `fetch.py:1143` | `_REPO` pattern, then ledger keys (`fetch.py:1167-1177`) |
| `quickbench` | `repo: str`, `confirmed: true`, `osaurus: bool` | `quickbench.run` `quickbench.py:424` | Catalog rows that are already downloaded |

### 5.3 Subprocess calls

| Location | argv | Where argv comes from | Environment |
|---|---|---|---|
| `engines.py:849` `_real_run` | `{python} -m venv <root>`; `<root>/bin/python -m pip install --no-input --disable-pip-version-check <pkg>==<ver> -c <constraints>` | `_command_plan` `engines.py:698-730`: constants plus `sys.executable` | `_hermetic_env` `engines.py:870`: ambient minus `PYTHONPATH` and `PIP_*` |
| `engines.py:863` `_real_open` | `open <url>` | `_release_url`, checked against https + `github.com`/`pypi.org` (`engines.py:900`) | Ambient; `open` resolved on PATH |
| `hardware.py:47` `_run` | `sysctl -n …`, `sw_vers -productVersion`, `ioreg -rc AGXAccelerator -d1` (`hardware.py:117-122`) | Constants | Ambient; bare names; no timeout |
| `quickbench.py:186` | `ps -axo comm=` | Constant | Ambient; bare name |
| `runtimes.py:493` `_run` | Helper commands per runtime, including `ps -axo pid=,args=` (`runtimes.py:554`) | Runtime classes | `_engine_env`: lab-path directories prefixed to PATH |
| `runtimes.py:518` `_spawn` | Engine start commands (bare names `mlx_lm.server`, `optiq`, `vmlx`, `osaurus`, `omlx`) | Runtime classes and the catalog artifact path | `_engine_env`; `start_new_session=True`; stdout to a log |
| `runtimes.py:124` | `lsof` resolved once with `shutil.which` on the ambient PATH | Constant | n/a |
| `runtimes.py:545`, `572`, `590` | `os.kill` / `os.killpg` on pids this run started or found listening on the engine's port | Port probes, the run's own pids, `_resident_osaurus_pids` | n/a |

### 5.4 Outbound network requests

| Location | URL construction | Guard |
|---|---|---|
| `fetch.py:443-445` | `https://huggingface.co/{repo}/resolve/{40-hex revision}/{quoted path}` (`fetch.py:221-224`), from catalog literals validated by `fetch.plan` | `_GuardedRedirects` refuses any redirect off `url_allowed` (`fetch.py:433-439`) |
| `runtimes.py:1350`, `1373` | `http://127.0.0.1:<engine port>/…` readiness and model-list probes | Loopback; constant ports |
| `engines.py:863` | Opens a release page in the user's browser (not fetched by the app) | `_url_allowed` `engines.py:900` |

### 5.5 Locations written on disk

Application Support means `~/Library/Application Support/OhYesMLX`, derived from `HOME`. Files and directories
are created with the process umask (typically `0644`/`0755`) unless stated.

| Path | Writer | Mode | Symlink handling |
|---|---|---|---|
| `…/engines/<name>-<ver>/` (venv) | `engines.install` via `-m venv` and pip | umask | `_rollback` removes only paths resolving inside `engines/` (`engines.py:938-963`) |
| `…/lab-paths.json` | `record_lab_path` `engines.py:433-475`: temp + `os.replace` | umask | The temp name is fixed (`.tmp`) |
| `…/install-log.jsonl` | `_append_install_log` `engines.py:981-996`: append | umask | Follows a symlink |
| `…/fetched.json` (ledger) | `_ledger_save` `fetch.py:320-328`: temp + `os.replace` | umask | The temp name is fixed |
| `…/fetch-log.jsonl` | fetch emitter: append | umask | Follows a symlink |
| `…/locks/download.lock` | `_acquire_lock` `fetch.py:348-372`: `O_CREAT\|O_EXCL` | `0644` | Exclusive create; a stale pid is reclaimed |
| HF cache `models--org--name/{blobs,snapshots,refs}` | `fetch.download`: `.incomplete` append/write (`fetch.py:1022-1025`), `os.replace` to the blob (`fetch.py:861`), `os.symlink` for the snapshot (`fetch.py:827`), `refs/main` (`fetch.py:831`), dirs (`fetch.py:601`) | umask | Refuses to write through a blob or `.incomplete` that is a symlink (`fetch.py:753`, `fetch.py:871`) |
| `~/.osaurus/config/server{,-runtime}.json` | `osaurus_settings.pin`/`restore`: `_write_atomic` `osaurus_settings.py:176-197` | Keeps the existing mode | The temp name is fixed (`.pin-tmp`) |
| `…/quickbench/osaurus-backup/` | `osaurus_settings.pin` `osaurus_settings.py:268-269` | `0700` | — |
| `config/osaurus-settings-baseline.json` (**in the repo / package tree**) | `osaurus_settings.write_baseline`, pin and restore | umask | — |
| `…/quickbench/<run>/summary.json` | `quickbench.py:392-401`: temp + replace | umask | — |
| `…/quickbench/<run>/results.jsonl` and header | `measure.run_cells` `measure.py:582`, `measure.py:1436-1448` | umask | — |
| `results/logs/` (**in the repo / package tree**) | `runtimes.py:125`, `runtimes.py:865`: engine server logs | umask | — |
| `$TMPDIR/ohyesmlx-omlx-*`, `ohyesmlx-mtplx-*` | `tempfile.mkdtemp` `runtimes.py:1485`, `runtimes.py:3319`; removed with `rmtree` (`runtimes.py:1495`, `1522`) | `0700` | Unlinks only symlink children (`runtimes.py:1502-1511`) |

### 5.6 Files read that a caller can influence

| File | Reader | Validation |
|---|---|---|
| `lab-paths.json` | `engines.lab_paths` `engines.py:381-430` | Keys limited to `mlxlm`/`optiq`. Values must be non-empty strings, and the path must exist (`runtimes.py:476`). No check of where it points. |
| `fetched.json` | `fetch._ledger_load` `fetch.py:284-317` | Shape-checked. Every path must resolve inside the cache root before `evict` removes anything (`fetch.py:1180-1189`). |
| `quickbench/*/summary.json` | `quickbench.latest` `quickbench.py:853-882` | Must be JSON, must be finished, repo must be a string. Only its `best` block is passed to the client. |
| Osaurus config and backups | `osaurus_settings` | JSON objects. The restore is verified byte-exact. |
| `HF_HUB_CACHE`, `HOME` environment | `fetch.default_cache_dir` `fetch.py:137-149`, `engines._Filesystem.home` `engines.py:204`, `osaurus_settings.py:40` | None. These decide every path above. |

### 5.7 Inventory cross-check (AC-1)

Command, over the eleven modules in scope:

```sh
P='subprocess|Popen|urlopen|HTTPSConnection|os\.replace|os\.symlink|os\.open|open\(.*["'"'"']w|chmod|rmtree|unlink|def do_|write_text|write_bytes|makedirs|mkdir|shutil\.|os\.rename|http\.client|socket|os\.environ|os\.kill|execv'
grep -nE "$P" ohyesmlx/{server,engines,fetch,quickbench,osaurus_settings,hardware,catalog,recommend,cli,runtimes,measure}.py
```

Hits per file: server 14, engines 14, fetch 14, quickbench 8, osaurus_settings 11, hardware 5, catalog 0,
recommend 0, cli 5, runtimes 26, measure 5 (102 in all). Reconciliation:

- **Accounted for in 5.1-5.6:** every executable hit.
- **Imports, `except` clauses, type references and docstring or comment mentions:** server's
  `socket`/`timeout` docstrings, `subprocess.DEVNULL` arguments, `fetch.py:82`, `fetch.py:185`,
  `osaurus_settings.py:26`, `osaurus_settings.py:179`, `cli.py:1057`, `cli.py:1109`, `runtimes.py:256`,
  `runtimes.py:410`, `engines.py:444`, `engines.py:738`. None is an entry point.
- **CLI-only writes the app never reaches:** `cli.py:864` (`grid --out`), `cli.py:1153` and `cli.py:1172`
  (the `run` directory).
- **Engine settings read through the environment:** `runtimes.py:2859` (`OHYESMLX_VMLX_ENABLE_JIT`), a
  developer toggle that the app never sets.
- **Lock reclaim:** `fetch.py:338` (`os.kill(pid, 0)`) is a liveness probe and sends no signal.

No executable hit is missing from the inventory.

## 6. Live probes (2026-11-03)

**Method.**

- `ohyesmlx app` (the test-venv interpreter, `python -I`) was started with `HOME` and `HF_HUB_CACHE` pointing at
  a scratch directory under `/tmp`.
- Every probe was sent from a script in a separate directory. The token was redacted to `<token>` before
  anything was written.
- No `install` or `quickbench` job was sent. The job probes used `download`/`evict` with repo ids that do not
  exist upstream.

**Real state untouched.** `ls -laR` of the real Application Support directory, HF cache and
`~/.osaurus/config` was piped to `shasum -a 256` before and after the probes:
`7962e8c2…207a` both times. The scratch directory held only a `fetch-log.jsonl` afterwards and was deleted.

| Probe | Result |
|---|---|
| No `Authorization` header | 401 `unauthorized` |
| Wrong token | 401 `unauthorized` |
| Token only in the query string | 401 `unauthorized` |
| `Host: evil.example:<port>` (DNS rebinding) | 403 `bad_host` |
| `Host: 127.0.0.1` without port | 403 `bad_host` |
| `Origin: https://evil.example` | 403 `origin_refused` |
| `Origin: null` | 403 `origin_refused` |
| CORS preflight `OPTIONS /jobs` with an Origin | 403 `origin_refused` (no `Access-Control-*` header on any response) |
| Authorized `GET /hardware` | 200 |
| `POST /jobs` as `text/plain` (a "simple" cross-site request) | 415 `unsupported_media_type` |
| Body over 4,096 bytes | 413 `body_too_large` |
| `Content-Length: 4000` with a 16-byte body | Connection closed after 10.0 s (handler timeout), no response, no job |
| `Content-Length: -1` | 413 `body_too_large` |
| `kind: "shell"` | 400 `bad_kind` |
| Extra arg key `url` | 400 `bad_args` "unexpected key url" |
| `confirmed: "true"` (a string) | 400 `bad_args` |
| `evict` repo `../../etc` | 202, then stream: `error bad_name`, `done` |
| `evict` repo `/Users/jrazz` | 202, then `error bad_name`, `done` |
| `evict` repo `../x` (passes `_REPO`) | 202, then `error ledger_unreadable` (no ledger in scratch), `done` |
| `download` repo `../../tmp` | 202, then `error unknown_repo`, `done` (no network request) |
| `download` of a repo id not in the catalog | 202, then `error unknown_repo`, `done` |
| `GET /jobs/../hardware` | 404 |
| `GET /jobs/<non-hex>/events` | 404 |
| `GET /quickbench/plan?repo=../../etc` | 400 `bad_args` "… is not a catalog model" |
| 50 SSE streams opened on one finished job | Each stream wrote its stored events and closed. 15 of 50 connects were reset by the listen backlog (`socketserver` default `request_queue_size` 5). Threads 2 → 2. |
| 50 silent, unauthenticated TCP connections | Threads 2 → 52, back to 2 after the 10 s handler timeout. Every connection gets its own thread, with no cap. |
| Listening sockets during the run | One: `127.0.0.1:<port>` (IPv4 loopback only) |
| stdin EOF | Exit 0. 20 stderr lines, none containing the token. Port free afterwards. |

A held SSE stream on a *running* job could not be probed safely, because every long-running job kind reaches
real binaries or the network. Section 7 covers it from the code.

## 7. Findings

### 7.1 Severity rubric (one definition)

- **High:** an in-scope actor *without the token* can change the machine, run code, read the user's files, or
  delete data.
- **Medium:** needs the token or a same-user process, or leaves the user's state wrong without saying so.
- **Low:** defence in depth; no exploit path is shown.

A finding that only another process of the same user can trigger, and that does not make that process's job
easier than editing the user's files directly, is rated low (section 3).

### 7.2 Method

Three passes, each verified against the code by the coordinator before any verdict was given:

- The coordinator's own reading and the live probes (sections 5-6).
- A server-side review (`.paul/orders/v5-sec-45-server.md`; the report stays local until 045-02, because it carries unfixed detail).
- An installer and downloader review (`.paul/orders/v5-sec-45-installers.md`; report local until 045-02).

The reviewers' ids are in brackets: F (server), S (installers), C (coordinator). A worker report on its own
never made a finding CONFIRMED.

### 7.3 Findings table

No finding is rated high. Two worker severities were changed after verification:

- **S1** was rated high by its worker and is medium here, as T-01. Exploiting it requires a compromised
  maintainer account on a pinned dependency, PyPI files cannot be replaced once uploaded, and TLS blocks
  spoofing.
- **F5** was rated medium by its worker and is low here, as T-09. A compromised package that could ship a
  shadowing `ps` already runs its own code at every engine start.

Jason approved every severity and disposition as listed at the 045-01 checkpoint (2026-11-03).

| Id | Verdict | Severity | Actor | Area | Disposition |
|---|---|---|---|---|---|
| T-01 | CONFIRMED | medium | compromised upstream | installer (pip) | Fix in 045-02. *Detail withheld until fixed in 045-02.* |
| T-02 | CONFIRMED | medium | same-user / interruption | app lifecycle: interrupted jobs | **Fixed in 045-02a (part B)**; (d) withdrawn. Detail in 7.4. |
| T-03 | CONFIRMED | medium | deployment | writable paths | **Fixed in 045-02a (`4b35ef8`)**, plus checklist P5-6. Detail in 7.4. |
| T-04 | CONFIRMED | medium | another local account (chained with T-08) | server job registry | **Fixed in 045-02a (`4b35ef8`)**. Detail in 7.4. |
| T-05 | CONFIRMED | medium | same-user (the Osaurus app) | quickbench Osaurus pin | **Fixed in 045-02a (part B)**. Detail in 7.4. |
| T-06 | CONFIRMED | medium | second process | fetch ledger | Fix in 045-02. *Detail withheld until fixed in 045-02.* |
| T-07 | CONFIRMED | low | same-user | installer environment | Fix in 045-02 (one line), plus checklist P5-3 |
| T-08 | CONFIRMED | low | any local account / token holder | server threads | **Fixed in 045-02a (`4b35ef8`)**; residual risk in section 9 |
| T-09 | CONFIRMED | low | compromised upstream | bare command names | **Fixed in 045-02a (`4b35ef8`)**, plus checklist P5-9 |
| T-10 | CONFIRMED | low | another local account (read) | file modes | **Fixed in 045-02a (`4b35ef8`)**, plus checklist P5-5 |
| T-11 | CONFIRMED | low | token holder pasting into a URL | refusal log | **Fixed in 045-02a (`4b35ef8`)** |
| T-12 | CONFIRMED | low | same-user | `lab-paths.json` | Fix in 045-02 (validation) |
| T-13 | CONFIRMED | low | same-user | `evict` ledger trust | Fix in 045-02 (per-repo containment) |
| T-14 | CONFIRMED | low | same-user | HF cache symlink races | Accepted, see section 9 |
| T-15 | CONFIRMED | low | second app instance | install lock | Checklist P5-7 |
| T-16 | CONFIRMED | low | none (cost only) | fetch snapshot conflict | Fix in 045-02 |
| R-01 | REJECTED | — | — | `_REPO` admits `.`/`..` | No traversal, see below |
| R-02 | REJECTED | — | — | guard bypass candidates | None found, see below |
| R-03 | REJECTED | — | — | TLS verification under a bundled Python | Fails closed; checklist P5-4 |
| R-04 | REJECTED | — | — | `PYTHONHTTPSVERIFY=0` in the environment | Same-user only, and content is hash-gated |

### 7.4 Low-severity and rejected findings in detail

**T-02, an interrupted app left the machine in a state nothing reported or recovered [F2, C-1, C-2]. Fixed in 045-02a (part B).**

- A `SIGKILL` of `ohyesmlx app`, or its 120 s shutdown wait expiring during a job, left:
  - quickbench: the engine server it had spawned (its own session) still holding its port and weights; the next run
    only skipped that engine.
  - quickbench with an Osaurus cell: `~/.osaurus/config/server{,-runtime}.json` still pinned (caches off,
    residency 900 instead of the user's own), the originals only in the quickbench backup directory. `recover` ran
    only at the start of a later Osaurus cell, never at app launch, so the user's Osaurus could run indefinitely on
    settings they did not choose.
  - install: the pip child running on in a daemon thread, with no rollback and no `lab-paths.json` record, and an
    `install-log.jsonl` with no end line.
- Fix:
  - (a) `ohyesmlx app`, after binding and before its launch line, calls `osaurus_settings.recover` with
    quickbench's backup directory, but only when the Osaurus app is not running (a running app may rewrite the
    files being put back). It writes `{"recovered": "osaurus", ...}` on stderr, or `{"recovery_pending": "osaurus",
    ...}` when the app is running and a backup is waiting. A failure is one stderr line and never stops the server.
  - (b) `runtimes` records each spawned engine (pid, port, `ps` start time and argv) in
    `<writable_root>/results/running-engines/<owner pid>.json`, written atomically after `cold_load_s` is taken, so
    no measured load time includes it. At launch `stop_orphaned_engines` reads only files whose owner process is
    dead, and stops an entry's process group only when its pid is alive with the same start time and argv; a reused
    pid or a matching command started later is dropped and never signalled.
  - (c) each pip step runs in its own process group and is registered while it runs; when the shutdown wait
    expires the server kills those groups and gives the job `JOB_KILL_GRACE_S` (15 s) more for its rollback and
    `done`.
  - (d) withdrawn: `.incomplete` download files are fetch's resume state, not residue, so nothing sweeps them.
- Verified live on a scratch HOME (045-02a SUMMARY): a pinned scratch Osaurus config was recovered byte-exact at
  app startup, and a recorded `sleep` with matching identity was stopped while one with a wrong start time survived.

**T-05, an Osaurus pin clobbered mid-cell was measured and reported as pinned [F3, C]. Fixed in 045-02a (part B).**

- The Osaurus-app check ran only before the cell. If the app relaunched (its Login Item, or an MCP host starting
  `osaurus mcp`) and rewrote its config during the cell, the pin's values were gone, the cell measured under the
  user's settings, and nothing recorded it. `restore` then wrote the backup back and verified against it, so a
  change the user made mid-run was lost while the log said "restored byte-exact".
- Fix: after a pinned Osaurus cell and before `restore`, quickbench compares the live config with the baseline the
  pin wrote. On drift it copies both config files byte-exact into `<backup_dir>/during-run/` (`0700`), names that
  directory in the summary, fails the cell with "Osaurus changed its settings during the run: " and the drifted
  keys, and still restores. Residual: when the cell itself raises, the check does not run, so a mid-run change in
  that path is still overwritten by the restore.

**T-03, the backend writes inside its own package tree [F4, C-3]. Fixed in 045-02a (`4b35ef8`).**

- `osaurus_settings.BASELINE_PATH` was `<package parent>/config/osaurus-settings-baseline.json`, written by every
  app-driven pin and restore; `runtimes.LOGS_DIR` was `<package parent>/results/logs`, written by every engine
  start, and `_spawn` created it outside its `try`, so a read-only tree raised `OSError`, not `RuntimeStartError`.
- Packaged inside a signed, read-only `.app`, every quickbench cell would have failed, the Osaurus pin would have
  rewritten both configs and then raised on the baseline write (undone only by the `finally`'s restore), or, if the
  bundle were writable, the bundle's signature would have been broken.
- Fix: `ohyesmlx.writable_root()` is the one definition of where the app may write: the repository root when the
  package runs from a git checkout (so `BASELINE_PATH` and `LOGS_DIR` are byte-identical to before and no harness
  run, canary or published table moves), otherwise `ohyesmlx.app_support_dir()`. Both constants ask it, and every
  Application Support path in `engines`, `fetch` and `quickbench` derives from `app_support_dir`. Tests: a
  read-only, `.git`-less package tree on a scratch home sends a pin round-trip and an engine spawn log only under
  the scratch Application Support (`tests/test_paths.py`).

**T-04, the job slot could leak for the life of the process [F1, C]. Fixed in 045-02a (`4b35ef8`).**

- `POST /jobs` took the slot with `claim()`, then wrote the start line to stderr and started the job thread with
  nothing to free the slot if either raised; only a stored terminal event frees it.
- Triggers: a parent that had closed stderr (`BrokenPipeError`), or thread creation failing. Chained with T-08, any
  local account could open many idle connections, push the process to its thread limit, make the app's next
  `POST /jobs` fail at `Thread.start()`, and leave every later job `409 busy` until a restart.
- Fix: any exception between `claim()` and a running job thread stores `error` (code `internal`) and `done` on the
  job, which frees the slot, before the 500. Tests: a start-log write that raises and a thread that will not start
  each answer 500, and the next valid `POST /jobs` is 202.

**T-07, installer environment [S2, C].**

- `_hermetic_env` (`engines.py:870-882`) drops `PYTHONPATH` and `PIP_*`, but pip still reads its config files:
  `~/Library/Application Support/pip/pip.conf`, `~/.config/pip/pip.conf` and `/etc/pip.conf`. An `index-url` in
  one of them reroutes the install.
- `PYTHONHOME` passes through.
- The `-m venv` step runs `sys.executable` without `-I`, so it loads the user's site-packages. The venv's own
  Python is not affected: `include-system-site-packages = false` disables the user site inside a venv (this
  corrects the worker's claim).
- Fix: run both steps with `-I`, and run pip with `--isolated`.

**T-08, unbounded threads [F7, C]. Fixed in 045-02a (`4b35ef8`):** `MAX_HANDLER_THREADS` (32) slots taken before a handler thread starts (a connection past the cap is closed with no response and no thread), and `MAX_STREAMS_PER_JOB` (4), past which `/events` is `429 too_many_streams`.

- `ThreadingHTTPServer` (`server.py:823`) starts one thread per connection, with no cap.
- An unauthenticated connection holds a thread for up to `HANDLER_TIMEOUT_S` (10 s). The probe showed 50 idle
  connections taking threads from 2 to 52.
- An authenticated `/events` stream holds a thread for the job's whole life, with no per-job cap. This is the
  stream-reader cap carried from 04-02.
- The listen backlog is the `socketserver` default of 5: the probe saw 15 of 50 rapid connects reset.
- Availability only, but it feeds T-04.
- Fix: a bounded semaphore on concurrent handler threads (refusing with a closed connection when full), and a
  per-job stream cap.

**T-09, bare command names [F5, C]. Fixed in 045-02a (`4b35ef8`):** `/bin/ps`, `/usr/sbin/sysctl`, `/usr/bin/sw_vers`, `/usr/sbin/ioreg` and `/usr/bin/open`, each spelled once; `hardware._run` is bounded by `TOOL_TIMEOUT_S` (10 s) and a hung tool makes `/hardware` a 500. `runtimes.LSOF` is still resolved with `shutil.which` on the ambient PATH at import (not the lab-prefixed engine PATH); not part of this finding.

- `_resident_osaurus_pids` runs `ps` by bare name through `_run` (`runtimes.py:554`), on the PATH that
  `_engine_env` prefixes with lab-path venv `bin/` directories (`runtimes.py:470-486`). It then signals the pids
  it parses.
- A console script named `ps` in a pinned dependency would run, and would choose which pids get signalled.
- `hardware.py:117-122` (`sysctl`, `sw_vers`, `ioreg`) and `quickbench.py:186` (`ps`) use bare names on the
  ambient PATH, and `hardware._run` has no timeout, so a hung `ioreg` hangs a `/hardware` handler.
- Fix: absolute paths (`/bin/ps`, `/usr/sbin/sysctl`, `/usr/bin/sw_vers`, `/usr/sbin/ioreg`, `/usr/bin/open`),
  and a timeout on `hardware._run`.

**T-10, file modes [S7, C]. Fixed in 045-02a (`4b35ef8`):** `ohyesmlx.ensure_app_support()` creates the directory `0700` or tightens an existing one, called by `ohyesmlx app` and `ohyesmlx quickbench` before their first write.

- Nothing under Application Support or the HF cache is created with an explicit mode, apart from the Osaurus
  backup directory (`0700`) and the lock file (`0644`).
- At the usual umask, another local account can read the install and fetch logs, the ledger, quickbench summaries
  and `lab-paths.json`. None holds a secret, but together they describe the machine and its use.
- Fix: create `~/Library/Application Support/OhYesMLX` with `0700`.

**T-11, token in the refusal log [F6]. Fixed in 045-02a (`4b35ef8`):** the refusal line carries the path only when it is a served route, else `<unknown>`.

- `_log_refusal` drops the query string but logs the path verbatim (`server.py:380`, `386-388`), so a token
  pasted into a path segment reaches stderr.
- The token appears nowhere else: not in argv, the environment, files, exception text or child processes (each
  spawned engine's stdout goes to its own log, `runtimes.py:516-525`), and the probes found it in no stderr line.
- Fix: log the matched route name, or `<unknown>`, never the raw path.

**T-12, `lab-paths.json` values [S3].**

- The values are checked only for being non-empty strings (`engines.py:426-429`), and they become the front of
  PATH for every engine start.
- A same-user writer can already edit `~/.zshrc`, so this adds little. The cheap hardening is to require an
  absolute path to an existing directory that is owned by the user and is not group- or world-writable.
- `record_lab_path`'s fixed `.tmp` name (`engines.py:465`) can collide across two processes. Use
  `tempfile.mkstemp` in the same directory.

**T-13, `evict` ledger trust [S4].**

- `evict` checks each ledger path only against the whole cache root (`fetch.py:1178-1187`). A tampered ledger
  can name any file under `HF_HUB_CACHE`, and that check is degenerate if the variable names a volume root.
- Fix: require each path to resolve inside that repo's own `models--org--name` directory.

**T-14, symlink races in the HF cache [S6].**

- Between the `islink` check and `open` of `.incomplete` (`fetch.py:867-873` → `1025`), and between `lexists`
  and `open("w")` of `refs/main` (`fetch.py:830-832`), a same-user process could swap in a symlink.
- A `FileExistsError` from the link race is not caught in `fetch`. The server's `_run_job` still ends the stream
  with `error` and `done` (`server.py:654-658`).
- Accepted (section 9).

**T-15, in-process install lock [S8].**

- `EngineLocks` (`engines.py:802-823`) is a `threading.Lock`, so two `ohyesmlx app` processes could install the
  same engine into one venv directory at once.
- The CLI has no install command (the subcommands are `run`, `grid`, `sweep`, `canary`, `quickbench`, `app`),
  so the only way to get there is two app instances. Checklist P5-7 requires a single instance.

**T-16, the snapshot-conflict check runs after the transfer (carried from Phase 4).**

- `link_all` (`fetch.py:808-834`) refuses a pre-existing snapshot link that points elsewhere (`integrity_failed`,
  nothing overwritten), but only after every blob has been downloaded.
- The blobs are recorded in the ledger in the `finally` (`fetch.py:680-682`), so they are evictable. The cost is
  a wasted multi-GB transfer, not a safety failure.
- Fix: run the same check in the pre-transfer pass.

**R-01, `_REPO` admits `.` and `..` (`catalog.py:75`).** There is no traversal:

- the org and name become one path component, `models--{org}--{name}` (`fetch.py:195`);
- `download` and quickbench take catalog rows only, and `evict` takes ledger keys only;
- file paths pass `check_path` (`catalog.py:138-157`), and blob keys are hex.

The probe for `evict ../x` reached only the ledger lookup.

**R-02, guard bypass candidates [F, probes].**

- All seven `do_*` methods go through `_guarded`.
- TRACE and CONNECT get the base class's 501 without reaching a module.
- Absolute-form targets 404 after the guard.
- Duplicate headers take the first value, which must itself pass.
- A chunked body without `Content-Length` is refused with 413 before any body is read.
- HTTP/1.0 closes the connection after every response, so there is no request smuggling.

**R-03, TLS verification under a bundled Python.**

- `urllib` verifies certificates by default.
- python.org's interpreter ships no CA bundle, so verification fails closed (`CERTIFICATE_VERIFY_FAILED`); it
  never silently skips.
- The packaging requirement is P5-4.

**R-04, `PYTHONHTTPSVERIFY=0`.** Only a same-user process can set the backend's environment, and every downloaded
file is still checked against the catalog's sha256 or git blob id (`fetch.py:572-588`).

## 8. Carried items and audit deferrals

| Item | Origin | Disposition |
|---|---|---|
| Clean-account smoke | 04-01, PHASE-4-SUMMARY | Plan 045-03 (human action, at a time Jason chooses) |
| A pip step outliving a server shutdown | 04-02 audit, PHASE-4-SUMMARY | T-02, fixed in 045-02 |
| Per-job stream-reader cap | 04-02 audit #1 | T-08, fixed in 045-02 |
| The Osaurus app rewriting its config mid-run | 04-03a audit #1 | T-05, fixed in 045-02 |
| A user's own Osaurus edit made during a run is overwritten by restore | 04-03a audit #2 | T-05: the fix keeps the user's current files as a second backup |
| fetch's post-transfer snapshot-conflict check | PHASE-4-SUMMARY | T-16, fixed in 045-02 |
| The Osaurus baseline's location in a packaged app | PHASE-4-SUMMARY, `docs/interfaces.md` | T-03, fixed in 045-02, plus P5-6 |
| The Swift client never logging the token | 04-01 audit #1 | Checklist P5-1 and P5-2 |
| UAT-001: `fetch.downloaded` compares sizes | 04-UAT | **ACCEPTED** (Jason, 2026-11-03). A size mismatch reads as "not ours". Only files rewritten outside the downloader hit it. The Phase 5 copy says "re-download" (P5-11). |
| Rate limiting or lockout on repeated 401s | 04-01 audit #2 | ACCEPTED (section 9) |
| A persistent access-log file | 04-01 audit #3 | ACCEPTED: refusal and job lines go to stderr, which the parent app holds. P5-10 covers what the app may keep. |
| TLS on loopback | 04-01 audit #4 | ACCEPTED (section 9) |
| Finished jobs never pruned | 04-02 audit #2 | ACCEPTED (section 9) |
| Killing a running pip step on cancel | 04-02 audit #3 | Superseded by T-02(c): kill on shutdown expiry only; cancel still waits for the step boundary |
| DMG checksum / signature verification | 02-03 audit #1 | ACCEPTED: the app never downloads a binary; the user installs from the vendor page and macOS checks the signature |
| Thermal drift; other MLX apps holding GPU memory during quickbench | 04-03b audit #1, #2 | ACCEPTED: quick results are labelled and never join the published tables; Phase 5 copy |
| SBOM / dependency provenance for the bundled Python | 045-01 audit, deferred #3 | Checklist P5-12 |

## 9. Accepted risks

| Risk | Why accepted | What would change the decision |
|---|---|---|
| No lockout on repeated 401s | The token is 256 bits and the server is loopback only; brute force is not feasible. Refusals are logged. | A token shortened for convenience, or any non-loopback bind |
| No TLS on loopback | Nothing crosses a network. The threats are other local processes and pages, which the token and the Host/Origin checks cover. | Any remote or LAN access to the API |
| Finished jobs kept in memory | A job is a few KB, one app session runs a handful, and a restart clears them | Long-lived sessions running hundreds of jobs |
| Same-user symlink races in the HF cache (T-14) | Only a process that can already write the user's files can win them. Fixing them fully needs `O_NOFOLLOW`/`openat` handling throughout `fetch`, a large change for no gain against that actor. | Running the backend as a different user from the one that owns the cache |
| Anyone holding the token can submit consented jobs | By design: the token is the boundary, and the parent app is the only holder | The token reaching any second process |
| UAT-001 | Section 8 | Users report surprise re-downloads |
| A local account filling the 32 handler slots (T-08) | Each idle connection is closed by the 10 s handler timeout, so the app's own requests are delayed, not refused for good; the slot leak that made it permanent (T-04) is closed. | The backend serving anything but loopback, or the app needing guaranteed latency |

## 10. Phase 5 packaging checklist

Each line must be checkable by a test or by a manual step that can fail.

| Id | Requirement | From |
|---|---|---|
| P5-1 | The Swift client never writes the token to `os_log`, `print`, stdout/stderr, a file, a crash report, analytics, or a URL. A grep of the Swift sources for the token's variable shows it only in the `Authorization` header builder. | 04-01 audit #1, T-11 |
| P5-2 | The backend is spawned with the token in no argv and no environment variable. The client reads the launch line only from the child's stdout pipe. | 04-01, section 4 |
| P5-3 | The bundled Python is started with `-I`, so no user site-packages, `PYTHON*` environment or current directory on `sys.path` affect it. pip runs with `--isolated`. | T-07 |
| P5-4 | The bundled Python carries a CA bundle (or uses the system trust store). An HTTPS fetch to `huggingface.co` succeeds on a clean account, and certificate verification is never disabled to make it work. | R-03 |
| P5-5 | `~/Library/Application Support/OhYesMLX` is created with mode `0700` before the backend first writes there. A check on a clean account reads `drwx------`. | T-10 |
| P5-6 | Nothing is written inside the `.app` bundle: the Osaurus baseline, engine logs and every other writable file live under Application Support. A run with the bundle on a read-only volume succeeds and `codesign --verify --deep` still passes afterwards. | T-03 |
| P5-7 | Only one app instance (and so one backend) runs per user. A second launch focuses the first. | T-15, T-06 |
| P5-8 | On quit, the client closes the backend's stdin and waits for it to exit, and does not SIGKILL while a job reports itself running. On launch, the backend's startup recovery (T-02) has run before the first screen offers a job. | T-02 |
| P5-9 | The backend's PATH is launchd's default, not the user's shell PATH. The engine PATH prefix comes only from `lab-paths.json`. | T-09 |
| P5-10 | The app may show or persist the backend's stderr lines as they are, and must never add request headers or the token to them. | 04-01 audit #3, T-11 |
| P5-11 | Copy: a model whose files differ in size from the catalog is offered as "re-download", not reported as corrupt. | UAT-001 |
| P5-12 | An SBOM of the bundled interpreter and every pinned engine dependency (names, versions, hashes from T-01) ships with each release. | 045-01 audit deferred #3, T-01 |
