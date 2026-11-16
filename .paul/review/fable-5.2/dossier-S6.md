# S6 dossier — Packaging and release

Scope: `scripts/build_app.sh`, `scripts/check_bundle.sh`, `scripts/fetch_python_standalone.sh`,
`scripts/make_sbom.py`, `scripts/smoke_clean_account.sh` + `.py`, `scripts/dev_backend_venv.sh`,
`app/Resources/Info.plist`, `docs/release/gatekeeper.md`, `.gitignore`, the production-path code in
`app/Sources/OhYesMLXKit/BackendLauncher.swift`, and the translocation guard in
`app/Sources/OhYesMLXKit/AppModel.swift`.

Everything in scope was introduced between 2026-10-29 (`dev_backend_venv.sh`, 05-02) and 2026-11-14
(the packaging set, commit `101df7c`); the smoke scripts are 045-03 (`743ada3`, fixes `369f180`,
`f7c22e0`). The one release ever built is `dist/OhYesMLX.app` 0.3.0 from `101df7c`, checked by the
coordinator (threat-model §10 status table, 2026-11-14). Nothing in this scope has been run,
built, or executed by this dossier writer — all line numbers were confirmed by grep/sed on the
working tree at `714e8f6`.

---

## 1. Map

### scripts/fetch_python_standalone.sh (83 lines) — the committed record of the one download the bundle needs (D6)

- `scripts/fetch_python_standalone.sh:15-18` — the pins: release `20261026`, tarball
  `cpython-3.14.10+20261026-aarch64-apple-darwin-install_only.tar.gz`, sha256 `30a18bcb…5183a4`, the GitHub URL.
- `scripts/fetch_python_standalone.sh:20-22` — cache paths under `~/Library/Caches/OhYesMLX/build` (tarball + unpacked tree).
- `scripts/fetch_python_standalone.sh:24-37` — `--identity` mode: prints the four pinned facts as KEY=VALUE (consumed by build_app.sh:26-29).
- `scripts/fetch_python_standalone.sh:39-42` — arm64-only guard (D1).
- `scripts/fetch_python_standalone.sh:44-46` — `digest()`: `shasum -a 256 | awk`.
- `scripts/fetch_python_standalone.sh:48-56` — cached-tarball re-verification; a cache mismatch deletes and refetches.
- `scripts/fetch_python_standalone.sh:58-68` — fetch (`curl -fsSL --retry 3` to `.part`), sha256 check **before** anything is unpacked, rename into cache only on match.
- `scripts/fetch_python_standalone.sh:70-81` — unpack to `${UNPACKED}.tmp`, verify `python/bin/python3` exists, `rm -rf "$UNPACKED"` then mv (the only destructive step on this script's paths).
- `scripts/fetch_python_standalone.sh:83` — prints the python root for build_app.sh's `$(...)` capture.

### scripts/build_app.sh (129 lines) — assembles, precompiles, signs and zips dist/OhYesMLX.app

- `scripts/build_app.sh:1-10` — header: macOS's own tools only (no new dependency); explicitly not notarized (D7).
- `scripts/build_app.sh:11` — `set -eu`.
- `scripts/build_app.sh:13-17` — ROOT/APP_DIR/DIST/APP/CONTENTS path derivation from `$0`.
- `scripts/build_app.sh:19-22` — `fail()`.
- `scripts/build_app.sh:24-35` — fetches the interpreter twice (once for the root, once `--identity` for release/url/sha256), then reads the one version definition: `ohyesmlx.__version__` from the repo copy **before** it is copied (lines 33-34).
- `scripts/build_app.sh:36-43` — names `OhYesMLX-$VERSION.zip` / `-sbom.json`; `swift build -c release` of `app/` (the Swift package at `app/Package.swift`).
- `scripts/build_app.sh:45-52` — `rm -rf "$APP"` then assemble: ditto the binary, ditto Info.plist, PlistBuddy sets both version keys from $VERSION, `plutil -lint`.
- `scripts/build_app.sh:54-63` — ditto the interpreter into `Contents/Resources/python`; asserts the bundled `sys.prefix` is inside the app (`-I -B`, OYMLX_APP env) so the bundle cannot resolve back to the build cache.
- `scripts/build_app.sh:65-78` — ditto `ohyesmlx/` into the bundled site-packages, strip `__pycache__`/`*.pyc`, then `compileall -q -j 0 --invalidation-mode unchecked-hash` over the whole `Resources/python/lib` (stdlib included) and assert at least one pyc landed; rationale comment 71-75 (child interpreters and engine venvs share this stdlib; unchecked-hash pycs never look stale after copy/zip/read-only mount).
- `scripts/build_app.sh:80-86` — licence check: every LICENSE*/COPYING* in the fetched tree must exist byte-identical (`cmp -s`) in the bundle (05-06 AC-7, audit-added).
- `scripts/build_app.sh:88-108` — ad-hoc signing inside-out: `find` over Resources/python, classify with `file -b`, each Mach-O `codesign --force --sign -` then `codesign --verify --strict`, list recorded to a mktemp file (trap-cleanup 89-90); then sign the app binary (105) and the bundle (106), then `codesign --verify --deep --strict --verbose=2` (107).
- `scripts/build_app.sh:110-122` — SBOM via `scripts/make_sbom.py` run with `${PYTHON:-/usr/bin/python3}` and the bundled interpreter as `--python`; **re-verifies the signature after** (122), because the SBOM step runs the bundled interpreter and a stray .pyc would break the seal (P5-6).
- `scripts/build_app.sh:124-129` — `ditto -c -k --keepParent` zip; prints APP, ZIP, SBOM paths.

### scripts/make_sbom.py (266 lines) — the release SBOM (P5-12), stdlib only, one runnable check

- `scripts/make_sbom.py:25-26` — schema `ohyesmlx-sbom/1`, REPO_ROOT from `__file__`.
- `scripts/make_sbom.py:29-60` — `parse_requirements()`: every `name==version` pin and every `--hash=sha256:` line from a hashed requirements file; any option line, unhashed pin, or hash-before-pin is `ValueError` (threat model T-01 shape).
- `scripts/make_sbom.py:63-80` — `engine_dependencies()`: one entry per `ohyesmlx/constraints/<engine>-<version>.txt`; empty dir is an error.
- `scripts/make_sbom.py:83-91` — `interpreter_version()`: asks the bundled python its version with `-I -B` (no bytecode into the bundle).
- `scripts/make_sbom.py:94-104` — `git_commit()`: `git rev-parse HEAD` of the repo, None if git fails.
- `scripts/make_sbom.py:107-113` — `source_sha256()`: imports and calls `ohyesmlx.measure._source_sha256()` from the repo tree — the one definition of the package source digest (never copied).
- `scripts/make_sbom.py:116-147` — `build_document()`: schema/generated/app(name, version, git_commit, source_sha256)/interpreter(distribution, version, release_tag, url, sha256)/swift toolchain/engine_dependencies.
- `scripts/make_sbom.py:150-202` — `check()` (`--check`): parser happy/sad cases, the committed constraints parse with 64-hex hashes and exactly engines {mlxlm, optiq}, source digest shape, document round-trips.
- `scripts/make_sbom.py:205-262` — `main()`: required-flag enforcement (219-232), imports `__version__` from the repo (234-236), writes `--out` (250-253), prints a digest of the written text (255-261).

### scripts/check_bundle.sh (263 lines) — proves P5-3, P5-4, P5-6, P5-9 on the bundle that would ship

- `scripts/check_bundle.sh:14-28` — usage: `<app> [--no-gui]`; anything else exits 2.
- `scripts/check_bundle.sh:30-35` — APP made absolute; `PYTHON` = the bundled interpreter; PASS/FAIL helpers, `FAILURES` counter.
- `scripts/check_bundle.sh:37-58` — mktemp work dir (resolved through `cd -P` for the /var vs /private/var spelling, comment 38-40), MOUNT/DMG paths, `cleanup()` (kill app+backend pids, `hdiutil detach -force`, `rm -rf "$WORK"`) on EXIT/INT/TERM.
- `scripts/check_bundle.sh:60-63` — bundled interpreter must exist and be executable.
- `scripts/check_bundle.sh:65-103` — **P5-3**: runs the bundled python under `-I -B` with a shadow module planted in both cwd and PYTHONPATH and asserts no user site, no cwd, no PYTHON* on `sys.path`, and `import shadow` fails.
- `scripts/check_bundle.sh:105-133` — **P5-4**: `env -i` (HOME + fixed PATH only) HTTPS GET to `https://huggingface.co/api/models/mlx-community/Qwen3-0.6B-4bit`, asserts 200 and `CERT_REQUIRED`+`check_hostname` (uses the system trust store; no CA bundled).
- `scripts/check_bundle.sh:135-257` — **P5-6/P5-9** (skipped under `--no-gui`):
  - `:138-145` — refuses to run while another `OhYesMLX.app/Contents/MacOS/OhYesMLX` matches pgrep (P5-7 precondition), then `hdiutil create -srcfolder … -format UDRO` (read-only image).
  - `:147-156` — attach `-nobrowse -readonly -mountpoint`; the mount must actually read `read-only` in `mount` output.
  - `:158-170` — `open` the mounted copy; wait up to 60 s for the backend python pid on the mount path (`${MOUNT#/private}` spelling, comment 38-40).
  - `:172-198` — find the backend's listen port via `lsof -nP -a -p … -iTCP -sTCP:LISTEN` (`-a` was a fixed defect), poll `GET /hardware` up to 30 s; 200 **or** 401 both PASS (401 = token is the parent's, P5-2).
  - `:201-207` — **P5-9 argv**: `ps -o args=` must contain exactly `-I -B -m ohyesmlx.cli app`.
  - `:209-231` — **P5-9 env**: reads the backend's environment from `ps eww`; when the block is present it must show `PATH=/usr/bin:/bin:/usr/sbin:/sbin` and no PYTHON*; when macOS withholds it (comment: 27.2.1 returns argv only) the check FAILs with "needs a decision here" rather than passing an unverified property.
  - `:234-250` — quit via `osascript` by bundle id, wait, SIGTERM escalation, FAIL if still alive.
  - `:252-255` — `codesign --verify --deep --strict` on the mounted copy after the run (the P5-6 seal), detach.
- `scripts/check_bundle.sh:259-263` — exit non-zero if any FAIL; "all checks PASS" otherwise.

### scripts/smoke_clean_account.sh (314 lines) — 045-03 clean-account smoke driver (runs as jrazz, drives everything through `sudo -n -u oymlxtest`)

- `scripts/smoke_clean_account.sh:17-27` — constants: TEST_USER `oymlxtest`, TEST_HOME, SMOKE `/Users/Shared/oymlx-smoke`, `PY=/opt/homebrew/bin/python3.14`, six AC-1 ports, the one downloaded model (`mlx-community/Qwen3-0.6B-4bit`, download-purpose comment 23-27).
- `scripts/smoke_clean_account.sh:32` — `log()`.
- `scripts/smoke_clean_account.sh:36-42` — `as_test_user()`: the one wrapper for every test-user command — `sudo -n -u oymlxtest env -i` with launchd's default PATH (P5-9) and a readable cwd.
- `scripts/smoke_clean_account.sh:46` — `fail()` (preflight preconditions; exits 1 naming the one that failed).
- `scripts/smoke_clean_account.sh:48-51` — `listeners_on()` (as jrazz and as the test user).
- `scripts/smoke_clean_account.sh:53-78` — `preflight()`: passwordless sudo, six ports free, Osaurus app not running (its own full-path check, AGENTS.md hazard), `xcode-select -p`, ≥5 GiB free, and the test user has neither App Support state nor the model's HF hub dir.
- `scripts/smoke_clean_account.sh:84-123` — `snapshot_host()`: AC-7's one function (used by both setup and verify-host) — copies Jason's App Support listing + `lab-paths.json`/`fetched.json` (absent-markers so a later appearance is a diff), HF hub listing, `~/.osaurus/config` files; target chmod 700 (comment 91).
- `scripts/smoke_clean_account.sh:125` — `pgrep_snapshot()`.
- `scripts/smoke_clean_account.sh:129-166` — `setup()`: preflight, world-writable results dir (token never on disk, comment 132-133), host snapshot, `git archive HEAD` into a mktemp work dir, `uv build --wheel`, the client taken from `git show HEAD:` (same revision as the wheel, 156-157), test-user venv, `pip install --no-deps --no-index` the wheel.
- `scripts/smoke_clean_account.sh:181-243` — the AC-6 sweep: `SWEEP_SIGNALLED`/`SWEEP_SEEN` bookkeeping (`sweep_hit` 185-192, one signal per pid), `sweep_once` (194-217: client, the six ports, the app by its own start command, engines under the test user's engines dir and the in-bundle oMLX/vMLX tools — every listing scoped `-u $TEST_USER`, comment 170-179), `sweep` (219-227: two passes 10 s apart because a still-loading engine binds its port late), `sweep_pid` (229-243: TERM, 5 s, KILL).
- `scripts/smoke_clean_account.sh:245-268` — `run()`: trap `sweep` on EXIT, runs the client with `--forbid /Users/jrazz`, then sweeps, diffs `pgrep` before/after, and reports failure if the sweep had to signal anything.
- `scripts/smoke_clean_account.sh:272-281` — `verify_host()`: AC-7 diff of the two snapshots (exit 1 on any difference).
- `scripts/smoke_clean_account.sh:285-302` — `teardown()`: removes the test user's venv/App Support/HF cache and everything in `$SMOKE` except `results/`.
- `scripts/smoke_clean_account.sh:304-314` — subcommand dispatch.

### scripts/smoke_clean_account.py (949 lines) — the smoke client, run as the throwaway user; pure helpers unit-tested

- `scripts/smoke_clean_account.py:31-44` — bounded timeouts (launch 60 s, install 1800 s, download 900 s, quickbench 1800 s, shutdown 10 s) and `APP_SUPPORT`.
- `scripts/smoke_clean_account.py:47-48` — `LaunchLineError`.
- `scripts/smoke_clean_account.py:56-86` — `parse_launch()`: the launch line must be exactly one non-blank line, a JSON object with exactly `port` (int 1..65535) and `token` (non-empty str) — anything else is a refusal (AC-2, P5-2).
- `scripts/smoke_clean_account.py:89-91` — `parse_ports()`: the .sh's PORTS list, the one definition.
- `scripts/smoke_clean_account.py:94-133` — `_sse_frame()` / `parse_sse()`: SSE framing per the pin (blank-line terminators, `: keepalive` dropped, multi-line `data:` joined).
- `scripts/smoke_clean_account.py:136-140` — `forbid_hits()`: the one definition of the `/Users/jrazz` leak scan.
- `scripts/smoke_clean_account.py:143-198` — `_pip_argv()`, `_flag_value()`, `pip_argv_problems()`: the install plan must carry `--require-hashes`, `--isolated`, `--no-deps`, `--only-binary :all:`, no `--no-binary`, and `-r <constraints>` inside the installed package's own dir (AC-3/AC-4; rationale in the docstring 164-174).
- `scripts/smoke_clean_account.py:201-244` — result bookkeeping: `add_check` (only place `checks` grows; PASS/FAIL/SKIP only), `update_check` (in-place rewrite), `gate` (SKIP naming the first failed prerequisite), `counts`, `summary_lines`.
- `scripts/smoke_clean_account.py:247-254` — `job_failed()`: last error code a job's stream carried.
- `scripts/smoke_clean_account.py:257-261` — `hub_repo_dir()`: asks `fetch._repo_dir`/`fetch.default_cache_dir` (one definition).
- `scripts/smoke_clean_account.py:264-301` — `cell_outcomes()`: per-engine cell outcomes from progress + the closing result summary (summary wins; the structured `status` payload, the 05-01 review fix).
- `scripts/smoke_clean_account.py:309-414` — `Client` (HTTP/1.0, 127.0.0.1 only, token header, every body leak-scanned): `request` 321-339, `post_job` 341-350 (`POST /jobs` with `confirmed: True`), `follow` 352-414 (the whole SSE stream to `done`, bounded by deadline, frame-wise leak scan).
- `scripts/smoke_clean_account.py:417-424` — `_outcome()`.
- `scripts/smoke_clean_account.py:427-435` — `_drain()`: holds the child's stdout open and records any line after the launch one.
- `scripts/smoke_clean_account.py:438-441` — `_port_free()`.
- `scripts/smoke_clean_account.py:444-465` — `read_launch_line()`: raw-fd byte-at-a-time read bounded by `select`, so a silent child cannot hang the client and nothing is buffered past the first line.
- `scripts/smoke_clean_account.py:468-472` — `_mode()`.
- `scripts/smoke_clean_account.py:475-493` — `check_ac2()`: launch line is the only stdout; App Support is `0700` (P5-5).
- `scripts/smoke_clean_account.py:496-608` — `check_ac3()`: the four read endpoints describe a fresh Mac (hardware keys, engines absent with hash-pinned plans via `pip_argv_problems`, recommendations shape, pre-download `/quickbench/plan` refusal, token required → 401), plus the leak scan result.
- `scripts/smoke_clean_account.py:611-678` — `check_ac4()`: both installs run to `done`, land in `lab-paths.json`, pass `engines.check_lab_dir`, and `/engines` reports them installed.
- `scripts/smoke_clean_account.py:681-793` — `check_ac5()`: download → real plan → confirmed quickbench (`osaurus=False`) → `cell_outcomes` must show mlxlm+optiq PASS → evict → the model dir and the ledger entry both gone (773-793).
- `scripts/smoke_clean_account.py:796-822` — `check_ac6()`: stdin EOF answered within 10 s, exit 0, all six ports free.
- `scripts/smoke_clean_account.py:825-917` — `main()`: spawns `[sys.prefix/bin/ohyesmlx, app]` (843, 850-855) with stdin/stdout pipes and stderr to a log; launch-line parse; AC-3/4/5 in one try whose `except Exception` is recorded (896-903) and whose `finally` always closes stdin (904-906); post-run updates of the launch and leak entries (908-916).
- `scripts/smoke_clean_account.py:920-927` — `_shut_down()`: closes stdin, records AC-6.
- `scripts/smoke_clean_account.py:930-945` — `_finish()`: one JSON results file at 0644, per-AC summary lines, exit 1 iff any FAIL.

### scripts/dev_backend_venv.sh (35 lines) — makes the `swift run` backend venv

- `scripts/dev_backend_venv.sh:12-14` — script/repo/dir derivation (dir defaults `~/.local/share/ohyesmlx/app-dev-venv`).
- `scripts/dev_backend_venv.sh:16-26` — interpreter pick: `python3` if ≥3.11, else a **hardcoded** fallback `/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python` (line 17), else exit 1.
- `scripts/dev_backend_venv.sh:28-31` — `python -m venv`, then one `.pth` file (`ohyesmlx-repo.pth`) naming the checkout so `-I` imports the repo without pip or network.
- `scripts/dev_backend_venv.sh:33-35` — sanity import print; prints the interpreter path for `OYMLX_DEV_PYTHON`.

### app/Resources/Info.plist (32 lines) — the bundle's plist template

- `app/Resources/Info.plist:9-10` — `CFBundleIdentifier` `io.github.jasonrandazza.ohyesmlx` (the bundle-id activation and the check_bundle quit path key off this).
- `app/Resources/Info.plist:19-22` — `CFBundleShortVersionString`/`CFBundleVersion` placeholder `0.0.0`, overwritten from `ohyesmlx.__version__` at build (build_app.sh:50-51).
- `app/Resources/Info.plist:25-26` — `LSMinimumSystemVersion` 14.0; `:23-24` category `public.app-category.developer-tools` (both 05-06 AC-2).

### docs/release/gatekeeper.md (98 lines) — the no-terminal first-run document (05-06 AC-5)

- `docs/release/gatekeeper.md:6-19` — move the app to Applications **before** first open (App Translocation; "Nothing is installed from that run" + a Quit-only screen).
- `docs/release/gatekeeper.md:21-24` — moving the app after installing engines: reinstall mlx-lm and OptiQ; models and results unaffected.
- `docs/release/gatekeeper.md:26-45` — not notarized (D7); the Open Anyway flow; "You only do this once per copy."
- `docs/release/gatekeeper.md:47-67` — why it is safe to check: "A sha256 is published next to the zip. The release notes list the zip's sha256"; the SBOM contents; network claims ("only to Hugging Face … and to PyPI … Nothing is uploaded").
- `docs/release/gatekeeper.md:69-90` — the three disk places (App Support, HF cache, `~/Library/Caches/OhYesMLX` build cache) and the removal recipe.
- `docs/release/gatekeeper.md:92-98` — notarization named as gated on an account, not done.

### .gitignore (32 lines)

- `.gitignore:2-3` — `results/`, `*.jsonl` (evidence regenerated).
- `.gitignore:6-14` — venvs, pyc, `build/`, `dist/` (the build output; 05-06 Task 1 requires it), caches.
- `.gitignore:31-32` — `app/.build/` (Swift build output).
- (History note: the 045-01 security-log ignore block was removed whole in 045-02b — see §3.)

### app/Sources/OhYesMLXKit/BackendLauncher.swift (566 lines) — production-path code

- `BackendLauncher.swift:4-29` — `LaunchOutcome`, `QuitOutcome`, `QuitTiming` (standard: stdin-EOF grace 10 s, SIGTERM grace 5 s, job-bound wait 150 s).
- `BackendLauncher.swift:31-50` — `LauncherProcess` / `BackendRunner` protocols (the seam the tests inject through).
- `BackendLauncher.swift:52-111` — `FoundationLauncherProcess` (`@unchecked Sendable`, NSLock-guarded termination handler 70-82; `run` 84-93 wires the three pipes; `kill` is SIGKILL 99-101; `waitForExit` polls `isRunning` 103-110).
- `BackendLauncher.swift:113-275` — `BackendLauncher` (`@unchecked Sendable`):
  - `:116-117` — `pathForChild = "/usr/bin:/bin:/usr/sbin:/sbin"` and `inheritedKeys = [HOME, USER, LOGNAME, TMPDIR, LANG]` — the whole child environment's definition (P5-9).
  - `:126-140` — init with injectable environment/appSupport/interpreter/factory/timing/timeout (launch timeout 30 s).
  - `:142-147` — `defaultAppSupportDirectory()`: `~/Library/Application Support/OhYesMLX`.
  - `:149-156` — `bundledInterpreter()`: `<Bundle>/Contents/Resources/python/bin/python3` (production path; D6).
  - `:158-210` — `start()`: prepare App Support → resolve interpreter → `acquireLock` (else `.alreadyRunning`) → spawn → `awaitLaunchLine` → JSON-decode `{port, token}` → `.running`; every failure path calls `session.abandon()` (kill + lock release).
  - `:185` — the argv, one definition: `[python, "-I", "-B", "-m", "ohyesmlx.cli", "app"]` (P5-2/P5-3/P5-6).
  - `:212-220` — `childEnvironment()`: PATH fixed, five inherited keys, nothing else, no PYTHON*.
  - `:222-233` — `resolveInterpreter()`: production interpreter if executable, else `OYMLX_DEV_PYTHON` if executable, else nil (development is the second choice, never overriding a present bundle).
  - `:235-241` — `missingInterpreterMessage()` names which path was looked for (05-02 requirement).
  - `:243-254` — `prepareAppSupport()`: created with `posixPermissions 0o700` before the spawn (P5-5); existing dir untouched.
  - `:256-274` — `app.lock` single instance: `open` + `flock(LOCK_EX|LOCK_NB)` (P5-7); release on unlock/close.
- `BackendLauncher.swift:277-528` — `LaunchSession` (`@unchecked Sendable`, one NSLock over all state):
  - `:318-329` — `startReading()`: stdout and stderr drained on background queues from spawn (the pipe never fills).
  - `:331-352` — `awaitLaunchLine(timeout:)`: continuation + one-shot timer; EOF before the line resumes nil.
  - `:354-369` — `installExitHandler` (fires immediately if already exited).
  - `:371-378` — `closeStdin()` (idempotent; the backend's parent-death signal).
  - `:380-398` — `quitWait(jobRunning:)`: job running → close stdin and wait `jobBound` (150 s), **never** signal; idle → `grace` 10 s → SIGTERM → `terminateGrace` 5 s → SIGKILL (P5-8).
  - `:400-415` — `forceKill()`, `abandon()` (terminate, 0.5 s, kill, release lock).
  - `:417-445` — `readLines()`: line splitting over both pipes; stderr into a bounded ring (200 lines, 468-475).
  - `:447-466` — `deliverLine()`: **first** stdout line wins; a later line never overwrites a pending one (comment 459-460; the wave-1 review fix, see §3).
  - `:477-499` — `stdoutEnded` / `timeOutLaunchLine` completion bookkeeping.
  - `:501-527` — `handleTermination` + `releaseLockIfNeeded` (the lock is released exactly once, on exit or abandon).
- `BackendLauncher.swift:530-561` — `RunningBackend`: endpoint + quit/forceKill facade.
- `BackendLauncher.swift:563-566` — `LaunchLine: Decodable { port, token }` — the launch-line shape as the client reads it (v5-onboarding.md:164-165 pins it).

### app/Sources/OhYesMLXKit/AppModel.swift — the translocation guard only

- `AppModel.swift:249-257` — `isTranslocated(bundlePath:)`: `bundlePath.contains("/AppTranslocation/")` (doc 249-254: engine venvs are made from `sys.executable`, a bundle path that dies with the translocated copy).
- `AppModel.swift:259-261` — `translocated` computed from the injected `bundlePath`.
- `AppModel.swift:362-384` — `launch()`: the guard at `:365-368` runs **before** `launcher.start()`; translocated → `screen = .moveToApplications`, nothing spawned (AC-7).
- `AppModel.swift:386-408` — `relaunch()`: the same guard first (`:387-389`).
- `AppModel.swift:607-609` — `start(_ args:)` (every job): `guard !unsupported, !translocated else { return }` — "no job can start from a translocated bundle, whatever the screen says" (comment 608).

---

## 2. Contracts

### docs/interfaces/v5-app.md — "The launcher" (the shape BackendLauncher composes on)

- `docs/interfaces/v5-app.md:39-41` (Interpreter): "Production: `<App>.app/Contents/Resources/python/bin/python3`, with `ohyesmlx` installed in that interpreter's own site-packages (plan 05-06). Development: the path in `OYMLX_DEV_PYTHON`… Neither found: the `couldnt_start` screen, naming which path was looked for."
- `docs/interfaces/v5-app.md:43-44` (Argv): "`[python, "-I", "-B", "-m", "ohyesmlx.cli", "app"]` (the package has no `__main__`…) Nothing else, and never the token (P5-2, P5-3). `-B` because the app bundle is signed and may sit on a read-only volume… the bundled `ohyesmlx` is precompiled at build time."
- `docs/interfaces/v5-app.md:46-47` (Environment): "built, not inherited: `PATH=/usr/bin:/bin:/usr/sbin:/sbin` (launchd's default, P5-9), `HOME`, `USER`, `LOGNAME`, `TMPDIR`, `LANG` from the parent, nothing else. No `PYTHON*` variable."
- `docs/interfaces/v5-app.md:48-50` (Launch line): "the first stdout line, `{"port": int, "token": str}` (v5-onboarding.md). The client waits at most 30 s for it; EOF or exit first is `couldnt_start` carrying the last stderr lines (P5-10)."
- `docs/interfaces/v5-app.md:54-56` (Stderr/streams): "Stderr, and stdout after the launch line, are drained continuously from spawn so the child never blocks on a full pipe. Stdin is a pipe held open until quit (EOF is the backend's parent-death signal)."
- `docs/interfaces/v5-app.md:58-61` (Quit, P5-8): "While a job is running the wait is unbounded from the app's side… 150 s after stdin closed it offers **Quit anyway**, and only that click sends SIGKILL. With no job running, wait 10 s, then SIGTERM, then 5 s, then SIGKILL."
- `docs/interfaces/v5-app.md:62` (Single instance, P5-7): "an exclusive `flock` on `<App Support>/OhYesMLX/app.lock` taken before the spawn".
- `docs/interfaces/v5-app.md:80-83` (screens): "`moveToApplications` is the App Translocation state (plan 05-06, AC-7): `AppModel` checks `bundlePath` for `/AppTranslocation/` before it spawns the backend and before any job can start… The screen says 'Move OhYesMLX to your Applications folder, then open it again' and offers only Quit."

### docs/interfaces/v5-onboarding.md — the launch line's producing side (what smoke_clean_account.py consumes)

- `docs/interfaces/v5-onboarding.md:164-165`: "before serving it writes exactly one line to stdout, `{"port": int, "token": str}`, where the token is `secrets.token_urlsafe(32)`, fresh per launch and never written to disk, argv or a log (the client holds the pipe)."
- `docs/interfaces/v5-onboarding.md:43` (P5-9 history): the bare engine names failed under "launchd's (threat-model P5-9)… with `[Errno 2]`" — the reason `runtimes.ENGINE_BUNDLE_EXECUTABLES` exists and the smoke's F2 fix.

### AGENTS.md — the standing rules this code is held to

- "Downloads need a reason and a record… the repo ids go in a committed script (`scripts/fetch_moe.sh` is the pattern)" — `fetch_python_standalone.sh` is that pattern's packaging instance (its header names the rule; `smoke_clean_account.sh:23-27` states the smoke model's purpose).
- "No new dependency without naming what it replaces" — `build_app.sh:8-9`: "Every tool is macOS's own… so there is no new dependency." `make_sbom.py` docstring: "Stdlib only."
- "One definition of everything" — the version is read once (`build_app.sh:32-35`); the source digest is *asked of* `measure._source_sha256()` (`make_sbom.py:107-113`), the constraints are the committed `ohyesmlx/constraints/*.txt`, the leak scan is `forbid_hits` (`smoke_clean_account.py:136-140`), the ports list is the .sh's `PORTS` (`parse_ports`, `:89-91`).
- "Never infer a capability from the absence of a flag… A claim that a tool CANNOT do something needs evidence" — check_bundle.sh:209-231 lives this rule for `ps eww`'s environment block: when macOS withholds it, the check refuses to pass an unverified property and says so.
- "A cell that produces incoherent output has FAILED" is the harness rule; its smoke-side echo is `AC-5.quickbench_cells` requiring real PASS cells (`smoke_clean_account.py:749-758`).

### docs/threat-model.md §10 — the packaging checklist (P5 rows that bind this code)

- P5-1/P5-2 (`:577-578`): "The Swift client never writes the token to `os_log`, `print`, stdout/stderr, a file, a crash report, analytics, or a URL"; "The backend is spawned with the token in no argv and no environment variable. The client reads the launch line only from the child's stdout pipe."
- P5-3 (`:579`): "The bundled Python is started with `-I`, so no user site-packages, `PYTHON*` environment or current directory on `sys.path` affect it. pip runs with `--isolated`."
- P5-4 (`:580`): "An HTTPS fetch to `huggingface.co` succeeds on a clean account, and certificate verification is never disabled to make it work."
- P5-5 (`:581`): "`~/Library/Application Support/OhYesMLX` is created with mode `0700` before the backend first writes there."
- P5-6 (`:582`): "Nothing is written inside the `.app` bundle… A run with the bundle on a read-only volume succeeds and `codesign --verify --deep` still passes afterwards."
- P5-7 (`:583`): "Only one app instance (and so one backend) runs per user."
- P5-8 (`:584`): "On quit, the client closes the backend's stdin and waits for it to exit, and does not SIGKILL while a job reports itself running."
- P5-9 (`:585`): "The backend's PATH is launchd's default, not the user's shell PATH… An app engine whose command-line tool ships inside its `.app` is exec'd from `runtimes.ENGINE_BUNDLE_EXECUTABLES`…"
- P5-10 (`:586`): "The app may show or persist the backend's stderr lines as they are, and must never add request headers or the token to them."
- P5-11 (`:587`): "Copy: a model whose files differ in size from the catalog is offered as 're-download', not reported as corrupt." (Not implemented — see §3.)
- P5-12 (`:588`): "An SBOM of the bundled interpreter and every pinned engine dependency (names, versions, hashes from T-01) ships with each release."
- The **2026-11-14 status table** (`:590-609`) records every row as Met on the `101df7c` bundle except **P5-11 "Partly met… Open"** and P5-5 "Met on this account; clean account pending". Evidence lines worth carrying to review: P5-4 "using macOS's `/etc/ssl/cert.pem`; no CA file is bundled"; P5-6 "before that fix, child interpreters wrote stdlib bytecode into the bundle"; P5-9 evidence claims check_bundle P5-9 passed with "launchd PATH, no PYTHON*"; P5-12 "105 pinned packages with hashes". The table's own caveat: "'Clean account' means the `oymlxtest` run of 05-06 AC-6, which is still to come (it needs Jason's sudoers step)."

### docs/threat-model.md §9 rows touching this code

- `:569` — "`_acquire_lock`'s stale-lock reclaim is check-then-remove… (T-06) … | More than one backend per user is ever supported (checklist P5-7)" — the Swift side's `flock` (`BackendLauncher.swift:260-269`) is the P5-7 mechanism; the backend's own `_acquire_lock` is separate code.
- `:566`/`:547` — UAT-001 (`fetch.downloaded` compares sizes) → P5-11 copy, still open.

### .paul/phases/v5-onboarding/PLAN.md — D6/D7 (the decisions the packaging implements)

- `PLAN.md:19` — "D6 Standalone Python (python-build-standalone) bundled in the .app with the ohyesmlx package."
- `PLAN.md:20` — "D7 First release = unsigned GitHub Releases .app zip (right-click, Open); notarization waits on an Apple Developer account decision. Xcode build is the developer path; the CLI stays." (Note: the shipped bundle is ad-hoc signed, not unsigned — 05-06's own reading of D7, "ad-hoc signed (D7: no Apple Developer account)", 05-06-PLAN.md:18.)
- `PLAN.md:134` — the phase line: "05-06 (wave 3) T5.6: `.app` assembly with python-build-standalone (D6), ad-hoc signed zip (D7, no Developer account), P5-3/P5-4/P5-6/P5-12 re-verified on the bundled interpreter, clean-account smoke."

### .paul/phases/v5-onboarding/05-06-PLAN.md / 05-06-SUMMARY.md — the section's own acceptance

- AC-1 (`05-06-PLAN.md:42-47`): the exact tarball/tag/sha256; "verifies sha256 … before unpacking, and refuses (non-zero, nothing unpacked) on a mismatch"; cache under `~/Library/Caches/OhYesMLX/build/`.
- AC-2 (`:49-56`): bundle layout, version from `ohyesmlx.__version__`, "signed ad hoc inside-out (every Mach-O under Resources/python, then the app)", `ditto -c -k --keepParent`, argv gains `-B`.
- AC-3 (`:58-62`): the SBOM contents; "ask that function, do not copy it"; "stdlib only and has one runnable check".
- AC-4 (`:64-72`): what check_bundle must prove (P5-3/4/6/9), "each check prints PASS/FAIL and the script exits non-zero on any FAIL".
- AC-5 (`:74-78`): the gatekeeper doc's required contents.
- AC-6 (`:89-95`): the clean-account smoke of **the built app's backend** "via the bundled interpreter, exactly the launcher's argv and env" plus smoke steps needing no engine install; `cell_outcomes` must read the structured payload.
- AC-7 (`:80-87`): the translocation guard before spawning, the full-window state, "no job can start (AppModel test with an injected bundle path)", gatekeeper.md's move/reinstall guidance, and PBS licence files shipped unmodified.
- Task 1 constraints (`:105-107`): "POSIX sh, set -eu, no new dependency… `dist/` gitignored… Sign inside-out without `--deep` for signing (verify may use --deep)."
- Boundaries (`:130-138`): "No notarization, no Developer ID, no upload to GitHub Releases (outward-facing; Jason's call)"; "Apple silicon only (D1); no universal binary"; "No auto-update mechanism." `ohyesmlx/` is DO-NOT-CHANGE ("the package is copied, not modified").
- `05-06-SUMMARY.md:16-29` — the acceptance table (all PASS except "AC-6 clean-account smoke **PENDING** — needs `/etc/sudoers.d/oymlxtest` re-added by Jason"), and `:43-44` the sudoers rule the smoke needs.

---

## 3. Already known — do not re-report

Format: `- <claim> — <source> — fixed <sha> | accepted | deferred | open`.

### Threat-model §10 status table (2026-11-14) — the recorded state of every P5 row this code serves

- P5-1..P5-10, P5-12 recorded **Met** on the `101df7c` bundle — threat-model.md §10 status table (590-609) — accepted as of the first pass; evidence named per row (see §2). Do not re-report "P5-x not verified" — it was, by the coordinator, with check_bundle where noted.
- P5-5 "Met on this account; clean account pending" — threat-model.md:602 — open (the clean-account half is 05-06 AC-6, still pending Jason's sudoers step).
- P5-11 "Partly met… The app never says 'corrupt'. It cannot offer 'Re-download' because `Pick.downloaded` is a single bool… This needs a backend field. Open." — threat-model.md:608 — open (STATE Deferred Issues row "P5-11… also in the Fable S4 scope"; not S6 code).
- The status table's own caveat: the clean-account run "is still to come (it needs Jason's sudoers step)" — threat-model.md:593-594 — open.

### Threat-model §9 accepted risks touching this code

- Stale-lock reclaim in the backend's `_acquire_lock` is check-then-remove (T-06), winning needs a crash plus a two-process race — threat-model.md:569 — accepted ("More than one backend per user is ever supported (checklist P5-7)" would change it). The Swift `flock` in BackendLauncher is not this code.
- UAT-001: `fetch.downloaded` compares sizes, so a size mismatch reads as "not ours" and the Phase 5 copy must say "re-download" (P5-11) — threat-model.md:547, :566 — accepted (Jason 2026-11-03) with the copy fix still open.
- pygame source-build in the OptiQ install (T-01) "RESOLVED, 045-03… pygame is omitted… nothing is built from source" — threat-model.md:567 — fixed `369f180` (recorded so the SBOM/constraints story is not re-litigated).

### STATE.md (Deferred Issues / Blockers) — the S6-relevant rows

- "P5-11: the app cannot offer 'Re-download'… `Pick.downloaded` is a single bool" — STATE.md Deferred Issues — deferred (backend field needed; S4 scope).
- "Disk audit incomplete… **Disk has tightened: 40 GiB free on 2026-11-13**… Phase 5 needs little (python-build-standalone ~100 MB, Swift build cache); revisit before any model fetch" — STATE.md Deferred Issues — deferred (relevant to build/smoke disk preconditions; smoke preflight itself enforces ≥5 GiB, smoke_clean_account.sh:67-68).
- "README.md needs a full rewrite" — STATE.md Deferred Issues — deferred (the gatekeeper doc is the release-facing copy; README is separate).
- No row of STATE's Blockers/Concerns table names S6 code (they are harness/sampler/Osaurus-penalty items). The 2026-11-14 blocker rows about Osaurus penalties concern measurement cells, not packaging.

### "Deviations"/"Carried forward" of the phase summaries

- "The worker added `-B` to the SBOM step after its own verify caught a post-signing `.pyc` (same root cause as #1)" — 05-06-SUMMARY Deviations — fixed `101df7c` (now build_app.sh:120-122 re-verifies after the SBOM step).
- "Version is 0.3.0 because the plist reads `ohyesmlx.__version__` (one definition); bumping for v5.0 is Jason's call" — 05-06-SUMMARY Deviations — open (deliberate; the Info.plist placeholder and build_app.sh:50-51).
- "Nothing published: no GitHub Release, no notarization (D7; outward-facing, Jason's call)" — 05-06-SUMMARY Deviations — open (the release step itself does not exist yet).
- Coordinator finding #1: "The signed bundle was being written to at runtime… child interpreters… wrote `email/__pycache__` etc. into the bundle, breaking the seal. Fix: the whole bundled tree is precompiled with `--invalidation-mode unchecked-hash`" — 05-06-SUMMARY "Coordinator findings fixed during verification" — fixed `101df7c` (build_app.sh:71-78).
- Coordinator finding #2: "check_bundle.sh defects: `/var` vs `/private/var` in `mount` and argv matching; `lsof -p … -iTCP` without `-a` (ORed, read another process's port); its own Python steps now pass `-B`" — 05-06-SUMMARY — fixed `101df7c` (check_bundle.sh:38-41, 175, 72/109).
- 05-01-SUMMARY Deviations 3: "`scripts/smoke_clean_account.py` still reads the retired `payload["skipped"]` key (dead branch, still functional); fix when 05-06 reruns the smoke" — fixed `101df7c` (current `cell_outcomes`, smoke_clean_account.py:264-301, reads the structured `status` payload; no `skipped` key remains — verified by grep).
- 05-02-SUMMARY Deviations 3: "Bundle-id activation of an already-running instance is untestable until 05-06 builds the .app" — addressed manually: "A second `open -n` of the .app focuses the first" (threat-model §10 status, P5-7 row) — accepted as manually verified; still no automated test.
- 045-03-SUMMARY Deviations 3: coordinator edits to the smoke scripts (host snapshot dir `0700`, `..` dropped from the `ls -laT` comparison, quickbench SSE kept as evidence) — fixed `f7c22e0`/in-tree (smoke_clean_account.sh:84-123 carries all three).
- 045-03-SUMMARY Deviations 5: "`/etc/sudoers.d/oymlxtest`… was added by Jason for this plan. Removing it needs root" — the precondition 05-06 AC-6 still waits on (05-06-SUMMARY:43-44) — open.
- 045-02b-SUMMARY Deviations 6: "The `.gitignore` block was removed whole" (the 045-01 security-log ignore lines and their comments) — fixed `7393715` (the .gitignore now has no security-log block) — recorded so its absence is not a finding.
- 045-02b-SUMMARY Deferred: global pip config (`/etc/pip.conf`) still loads under `--isolated` and "needs admin to write and a rerouted index cannot pass the hashes. Recorded, not fixed." — deferred (bounds what `pip_argv_problems` and the gatekeeper doc's hash claims can promise).

### Findings in `.paul/review/*/` logs on S6 code

- `deliverLine` overwrote `pendingLine` when no waiter was registered, so two stdout lines arriving before `awaitLaunchLine` lost the launch line and `start()` abandoned a healthy backend — .paul/review/2026-11-14-phase5-w1/standards.log ("JUDGEMENT — defect (BackendLauncher.swift:445-460)") — fixed `ac0de1b` ("…first launch line"; the current code at BackendLauncher.swift:447-466 keeps the first line only, and `LauncherTests.testTheFirstStdoutLineIsTheLaunchLineWhenTwoArriveBeforeTheAwait` pins it).
- All other wave-1/wave-2 review findings (quickbench stage-B collapse, cancel-body detection, HTTPBackend poison-SSE loop, AppModel `.done` summary leak, `Pick`/Results copy, `String(format:)` gate, StatusGlyph 9 pt, etc.) live outside S6 scope (server.py, quickbench.py, the screens' views) except the two above — .paul/review/2026-11-14-phase5-w{1,2}/*.log — several fixed in `101df7c`'s app tree per `fee692b` ("fixes landed in the 05-06 commit's app tree") — see S1–S5 dossiers, do not re-report here.
- The 2026-09-23 review logs (`.paul/review/2026-09-23/`) predate every S6 file and contain no finding on S6 code — the packaging scripts, Info.plist, gatekeeper.md and BackendLauncher did not exist until 2026-10-29+ — nothing to carry.

### Clean-account smoke findings already recorded (045-03, since the smoke scripts are in this scope)

- F1: optiq could not install on a typical Mac (pygame source build needs Homebrew SDL) — 045-03-SUMMARY Findings — fixed `369f180` (pygame omitted, `--no-deps`, wheels-only).
- F2: oMLX/vMLX/Osaurus could not start under launchd's PATH (bare names resolved only through per-user shims) — 045-03-SUMMARY Findings — fixed `369f180` (`runtimes.ENGINE_BUNDLE_EXECUTABLES`).
- Code-review fixes to the smoke scripts themselves — 045-03-SUMMARY commits table (`f7c22e0`: "Code-review fixes to the smoke scripts"), 1281→1329 tests — fixed `f7c22e0`.
- AC-6 of that smoke (shutdown leaves nothing behind) passed 21/21 as `oymlxtest` on 2026-11-13 — 045-03-SUMMARY — accepted (run 2 evidence in `045-03-evidence/`).
- The 045-03 "plan's 'snapshot equals' wording was too strict for a live account (macOS per-user services like `mdworker_shared` appear in the pgrep diff)" — 045-03-SUMMARY AC-6 — accepted; the diff is advisory, the pass/fail signal is `SWEEP_SIGNALLED` (smoke_clean_account.sh:265-266).

---

## 4. Hotspots

The 20 ranges where a defect would hurt most: the user's Mac or data, a wrong or misattributed number, a race, or a trust boundary. Test column names what fails if it breaks.

1. `scripts/fetch_python_standalone.sh:58-68` — the sha256 gate: this is the only thing between a tampered download (or a compromised cache) and an attacker-supplied interpreter that build_app.sh then signs and ships. A check that runs after unpack, or a cache trusted without re-verification (the re-check at :50-56 is the countermeasure), ships attacker code. — Test: **none** automated (05-06-SUMMARY AC-1 records a manual wrong-pin red-check "exits 1").
2. `scripts/fetch_python_standalone.sh:70-81` — `rm -rf "$UNPACKED"` / `.tmp` unpack dance: the paths derive from `~/Library/Caches/OhYesMLX/build` and the pinned tarball name; a variable slip here is recursive deletion near the user's home. The `.part`-then-mv on the tarball (:67) is the partial-download guard. — Test: none.
3. `scripts/build_app.sh:45-52` — `rm -rf "$APP"` then assemble: destructive on `dist/`; `ROOT` derives from `$0` (:13), so a symlinked or copied invocation deletes a different `dist` than expected. PlistBuddy sets the two version keys; if `VERSION` were empty the `Set` would corrupt the plist (only `[ -n "$VERSION" ]` at :35 guards it). — Test: none (build verified manually at `101df7c`).
4. `scripts/build_app.sh:59-63` — the bundled interpreter's `sys.prefix` assertion: if the copy ever resolved back to `~/Library/Caches/...` (an rpath/home-layout regression in python-build-standalone), every engine venv would point outside the bundle and the read-only-volume run (P5-6) would fail in the field, not at build. — Test: none (P5-6's check_bundle run is the de-facto guard, coordinator-run only).
5. `scripts/build_app.sh:71-78` — the unchecked-hash precompile: this is the fix for the sealed-bundle writes (05-06 finding #1). Its risk is the flip side: unchecked-hash pycs are **never** revalidated against source, so post-build tampering of a `.py` in the bundle would still load the old bytecode and `codesign --verify` would catch the source edit but nothing re-derives pyc↔source. Trust rests entirely on the code seal. — Test: none for the property; check_bundle P5-6 catches writes, not tampering.
6. `scripts/build_app.sh:88-108` — the signing loop: Mach-O classification by `file -b` in a `find | while` subshell; a misclassified Mach-O is never code-signed (only resource-sealed), and `fail` inside the pipeline subshell relies on `set -e` propagating the pipeline's exit status. The verify at :107 is the net. — Test: none automated (`codesign --verify --deep --strict` is build_app.sh's own step and check_bundle re-runs it after a launch).
7. `scripts/build_app.sh:110-122` — SBOM-after-sign ordering: the SBOM step *runs the bundled interpreter*; the re-verify at :122 exists because that can write bytecode (the `-B` at :111 and the precompile are the two layers). A future SBOM field that touches the bundle after :122 would break the shipped seal with the zip already looking fine. — Test: none.
8. `scripts/make_sbom.py:29-60` — `parse_requirements`: a parser edge case (continuation/backslash, hash-line grouping) that silently drops a hash would make the SBOM under-record what pip is allowed to install (T-01's whole point). It fails closed on every shape it does not know. — Test: `python3 scripts/make_sbom.py --check` (self-check; not part of the pytest suite).
9. `scripts/make_sbom.py:94-113` + `:234-247` — SBOM provenance split: `git_commit` is `HEAD`, `source_sha256` is the **working tree** (`measure._source_sha256()`), and the shipped package is `ditto "$ROOT/ohyesmlx"` from that same working tree. In a dirty worktree the SBOM pairs a commit with a digest that commit does not contain. Whether this can make the SBOM disagree with what ships is open question Q3.
10. `scripts/check_bundle.sh:138-156` — the read-only-image check's setup: pgrep precondition (139) protects Jason's own running instance and the P5-7 one-instance rule; `hdiutil create -srcfolder "$APP"` + attach + `rm -rf "$WORK"` cleanup. A cleanup failure leaves a mounted image and orphaned processes on the user's Mac. — Test: none (this script *is* the test).
11. `scripts/check_bundle.sh:172-198` — finding the backend's port and polling `/hardware`: the `lsof -a` disjunction fix (05-06 finding #2) is load-bearing — without `-a` the check read another process's port and could PASS against the wrong server. A stale OhYesMLX on a port would similarly satisfy the curl. — Test: none.
12. `scripts/check_bundle.sh:201-231` — the P5-9 argv + environment checks: argv matching is a substring case pattern (`*"-I -B -m ohyesmlx.cli app"*`), and the env branch hard-FAILs when macOS withholds another process's environment (see open question Q5). — Test: `LauncherTests.testArgvEnvironmentAndDirectory` covers the property at unit level.
13. `scripts/smoke_clean_account.sh:36-42` — `as_test_user`: the `env -i` + fixed PATH wrapper is what makes every smoke observation a "clean account" observation; a command run outside it silently runs as jrazz with jrazz's environment and invalidates the AC. — Test: none (structural; the smoke's own AC-3 leak scan would catch content leaks but not identity).
14. `scripts/smoke_clean_account.sh:181-243` — the sweep: it TERMs/KILLs processes matched by pattern under `sudo -u oymlxtest`. Every listing carries `-u $TEST_USER` and patterns are anchored to the smoke's own paths/bundles; a loosened pattern would signal Jason's processes (the header comment :170-179 records the danger). The two-pass 10 s cadence covers late port binding. — Test: none.
15. `scripts/smoke_clean_account.sh:285-302` — `teardown`'s `rm -rf` of `$TEST_HOME/{oymlx-venv,Library/Application Support/OhYesMLX,.cache/huggingface}` and `$SMOKE/*` (except results): destructive but scoped to the throwaway account; the `[ -e "$entry" ] || continue` guards the empty glob. — Test: none.
16. `scripts/smoke_clean_account.py:825-917` — `main`'s spawn + the AC-6 shutdown contract: stdin is closed from a `finally` (:904-906) so an exception in the checks can never leave the child holding a port with a model resident; `binary = sys.prefix/bin/ohyesmlx` (:843) is the wheel's entry point (see open question Q2 about which artifact the smoke exercises). — Test: `tests/test_smoke_clean_account.py` covers the pure parts only (`test_a_failed_check_never_stops_the_recording`, `test_finish_writes_one_readable_json_file_at_0644`); the shutdown path itself is live-run-only.
17. `scripts/smoke_clean_account.py:444-465` — `read_launch_line`: byte-at-a-time raw-fd read, bounded by `select`; a bug here hangs the smoke or eats a line the drain thread should keep (AC-2's "nothing else on stdout" check depends on it). — Test: `tests/test_smoke_clean_account.py::test_the_launch_read_is_bounded_and_returns_the_first_line`, `::test_the_launch_read_stops_at_the_first_line_and_leaves_the_rest`, `::test_the_launch_read_returns_a_partial_line_at_eof`.
18. `app/Sources/OhYesMLXKit/BackendLauncher.swift:158-233` — the production spawn path: resolve interpreter (bundle first, `OYMLX_DEV_PYTHON` second) → lock → spawn with the one argv definition (`:185`) and the built environment (`:212-220`) → first-stdout-line launch parse. A defect here is every P5-2/P5-3/P5-9 property at once. — Test: `app/Tests/OhYesMLXKitTests/LauncherTests.swift::testArgvEnvironmentAndDirectory`, `::testTheFirstStdoutLineIsTheLaunchLineWhenTwoArriveBeforeTheAwait`, `::testMissingInterpreterNamesThePathLookedFor`.
19. `app/Sources/OhYesMLXKit/BackendLauncher.swift:243-274` and `:380-398` — App Support `0700` + `app.lock` flock (P5-5/P5-7) and the quit escalation that must never SIGKILL a running job (P5-8; the 150 s jobBound and the Quit-anyway click are the only kill paths). — Test: `LauncherTests.testSecondLauncherIsAlreadyRunningAndSpawnsNothing`, `testQuitWhileAJobRunsClosesStdinAndNeverSignals`, `testQuitEscalatesGraceThenTerminateThenKill`, `testQuitReturnsTerminatedWhenSigtermStopsTheBackend`.
20. `app/Sources/OhYesMLXKit/AppModel.swift:249-261, 362-368, 386-389, 607-609` — the translocation guard: a bypass (or a path spelling macOS changes — the check is `contains("/AppTranslocation/")`) lets a run create engine venvs pointing at a dead interpreter path, stranding the pip engines (AC-7). Guarded at three doors: launch, relaunch, job start. — Test: `app/Tests/OhYesMLXKitTests/AppModelTests.swift::testATranslocatedBundleAsksForApplicationsAndStartsNoJob` (injected bundle path; checks `isTranslocated` true/false cases and that `launch()` shows `.moveToApplications`).

---

## 5. Mechanical scan

Grep results, one line each, locations as `path:line`. Patterns listed by the order; "none" means no hits in the scope files. Python scope: `make_sbom.py`, `smoke_clean_account.py`. Swift scope: `BackendLauncher.swift`, `AppModel.swift`. Shell scope: the five `.sh` files. No judgment attached.

### Standard Python patterns

- `shell=True` — none.
- `os.system` — none.
- `eval(` — none.
- `exec(` — none.
- `pickle` — none.
- bare `except:` — none.
- `except Exception: pass` — none. (Nearest: `smoke_clean_account.py:896` `except Exception as error:` — records a FAIL entry, does not pass; and `smoke_clean_account.py:434`/`435` `except (OSError, ValueError): pass` inside `_drain`, a bounded stdout reader.)
- `chmod` — `scripts/smoke_clean_account.py:939` (`os.chmod(path, 0o644)` on the results JSON). (Shell-side: `smoke_clean_account.sh:92` `chmod 700 "$target"`; `:135` `chmod 0777 "$SMOKE/results"`; `:158` `chmod a+rX`.)
- `tempfile.mktemp` — none (`mktemp -d`/`mktemp -t` with templates: `check_bundle.sh:37`, `smoke_clean_account.sh:145`, `build_app.sh:89`).
- `open(` with `w` on a path built from input — `scripts/make_sbom.py:253` (`out.write_text`, `--out` CLI arg, `mkdir -p` first); `scripts/smoke_clean_account.py:848` (`open(log_path, "wb")`, under `--out` + timestamp), `:938` (`write_text` of `{stamp}.json` under `--out`).
- `subprocess` without a timeout — `scripts/make_sbom.py:85-91` and `:96-101` (`subprocess.run` no timeout: the bundled `python -c`, and `git rev-parse`); `scripts/smoke_clean_account.py:850-855` (`Popen`, no subprocess timeout — bounded instead by `read_launch_line`'s select deadline and `process.wait(timeout=SHUTDOWN_TIMEOUT_S)` at :804).
- `json.loads` on unbounded input — `scripts/smoke_clean_account.py:70` (launch line, one bounded line), `:348` (job POST body), `:398` (SSE frame data, streamed up to a 30–1800 s deadline), `:504`, `:533`, `:566`, `:583`, `:667`, `:703` (localhost response bodies, `http.client` `.read()` unbounded), `:633`, `:775` (local files under App Support); `scripts/make_sbom.py:196` (its own document in `--check`).

### Standard Swift patterns

- `try!` — none.
- `!` force-unwrap on optionals from I/O — none (no `try!`, `fatalError`, or `!`-unwraps of I/O results in either file; `process.processIdentifier` at `BackendLauncher.swift:100` is a non-optional).
- `fatalError` — none.
- `DispatchQueue.main.sync` — none.
- `@unchecked Sendable` — `app/Sources/OhYesMLXKit/BackendLauncher.swift:52` (`FoundationLauncherProcess`), `:113` (`BackendLauncher`), `:277` (`LaunchSession`), `:530` (`RunningBackend`) — all four pair it with an `NSLock` around mutable state. None in `AppModel.swift`.
- `Task {` without cancellation handling — `app/Sources/OhYesMLXKit/AppModel.swift:595` (`Task { @MainActor in self?.backendExited(...) }` — fire-and-forget UI handoff; no cancellation). None in BackendLauncher.swift (it uses `DispatchQueue`/continuations).
- `print(` — none in either Swift file.

### Shell / extra scan patterns (this section's list)

- `set -e` — `scripts/build_app.sh:11`, `scripts/check_bundle.sh:12`, `scripts/fetch_python_standalone.sh:13`, `scripts/smoke_clean_account.sh:15`, `scripts/dev_backend_venv.sh:10` — all `set -eu`.
- unquoted `$` — `scripts/smoke_clean_account.sh:57` and `:198` (`for port in $PORTS` — deliberate word splitting of the port list); `scripts/check_bundle.sh:14-15` and `scripts/dev_backend_venv.sh:21` (assignments — no splitting in POSIX assignment); deliberate unquoted globs `"$SMOKE/dist"/*` (`smoke_clean_account.sh:158`) and `"$SMOKE"/*` (`:293`). Heuristic scan only; every other `$` occurrence in these files sits inside quotes or `$( )`.
- `rm -rf` — `scripts/build_app.sh:46` (`"$APP"`), `:69` (`find … -exec rm -rf {} +` on `__pycache__`); `scripts/check_bundle.sh:56` (`"$WORK"` in cleanup); `scripts/fetch_python_standalone.sh:71`, `:75`, `:79` (the unpacked-cache paths); `scripts/smoke_clean_account.sh:89` (`"$target"` snapshot dir), `:146` (mktemp work dir), `:151` (`"$SMOKE/dist"`), `:287-290` (test user's venv/App Support/HF cache), `:298` (`"$entry"` in teardown).
- `codesign` — `scripts/build_app.sh:95`, `:97` (per-Mach-O sign + verify), `:105`, `:106` (binary, then app), `:107`, `:122` (verify --deep --strict, before and after SBOM); `scripts/check_bundle.sh:252` (verify on the mounted copy).
- `--deep` — verify only, never sign: `scripts/build_app.sh:107`, `:122`; `scripts/check_bundle.sh:252`. (05-06 Task 1: "Sign inside-out without `--deep` for signing (verify may use --deep)" — conformed.)
- `hdiutil` — `scripts/check_bundle.sh:54` (detach in cleanup), `:143` (create UDRO), `:149` (attach readonly), `:255` (detach after).
- `ditto` — `scripts/build_app.sh:48` (binary), `:49` (Info.plist), `:55` (interpreter), `:68` (ohyesmlx package), `:126` (zip with `--keepParent`).
- `shasum` — `scripts/fetch_python_standalone.sh:45` (`shasum -a 256` in `digest`). No shasum of the zip anywhere (see open question Q4).
- `curl` — `scripts/fetch_python_standalone.sh:60` (`-fsSL --retry 3` to `.part`); `scripts/check_bundle.sh:186` (`GET /hardware` poll against 127.0.0.1).
- `xattr` — none.
- `compileall` — `scripts/build_app.sh:76-77` (`-q -j 0 --invalidation-mode unchecked-hash` over `Resources/python/lib`).
- `-B` — `scripts/build_app.sh:61`, `:66`, `:76`; `scripts/check_bundle.sh:72`, `:109` (note: written `-B -B`, the flag duplicated); `app/Sources/OhYesMLXKit/BackendLauncher.swift:185` (the production argv).

---

## 6. Test inventory

Per hotspot (§4 numbering), the tests that would fail if it broke. The project suite is pytest (`tests/`) plus `swift test` (`app/Tests/`); the shell scripts have no automated tests and are themselves run by the coordinator.

| # | Guard | Test(s) |
|---|---|---|
| 1 | fetch sha256 gate | none (manual wrong-pin red-check recorded in 05-06-SUMMARY AC-1) |
| 2 | unpack `rm -rf` paths | none |
| 3 | `rm -rf "$APP"` + plist versioning | none (build + `plutil -lint` are build_app.sh's own steps) |
| 4 | bundled `sys.prefix` assertion | none (check_bundle.sh P5-6, coordinator-run, is the de-facto guard) |
| 5 | unchecked-hash precompile | none (check_bundle.sh P5-6 run from a read-only image catches runtime writes only) |
| 6 | signing loop classification | none (build_app.sh:97/:107 self-verify; check_bundle.sh:252 re-verify) |
| 7 | SBOM-after-sign ordering | none (build_app.sh:122 self-verify) |
| 8 | `parse_requirements` | `scripts/make_sbom.py --check` (standalone; NOT in tests/) |
| 9 | SBOM provenance split | none |
| 10 | image setup/cleanup | none (check_bundle.sh is the test) |
| 11 | port discovery + `/hardware` poll | none (check_bundle.sh is the test) |
| 12 | P5-9 argv + env checks | `app/Tests/OhYesMLXKitTests/LauncherTests.swift::testArgvEnvironmentAndDirectory` (the property; not the check script's own branches) |
| 13 | `as_test_user` wrapper | none (structural) |
| 14 | the sweep | none |
| 15 | teardown `rm -rf` | none |
| 16 | smoke `main` spawn + shutdown contract | `tests/test_smoke_clean_account.py::test_a_failed_check_never_stops_the_recording`, `::test_finish_writes_one_readable_json_file_at_0644` (bookkeeping only; the spawn/stdin-finally path is live-run-only) |
| 17 | `read_launch_line` | `tests/test_smoke_clean_account.py::test_the_launch_read_is_bounded_and_returns_the_first_line`, `::test_the_launch_read_stops_at_the_first_line_and_leaves_the_rest`, `::test_the_launch_read_returns_a_partial_line_at_eof` |
| 18 | production spawn path | `app/Tests/OhYesMLXKitTests/LauncherTests.swift::testArgvEnvironmentAndDirectory`, `::testTheFirstStdoutLineIsTheLaunchLineWhenTwoArriveBeforeTheAwait`, `::testChattyStderrStillYieldsTheLaunchLine`, `::testStdoutAfterTheLaunchLineIsDrainedAndDiscarded`, `::testEOFBeforeTheLaunchLineIsCouldntStartWithTheStderrTail`, `::testNoLaunchLineWithinTheTimeoutIsCouldntStart`, `::testMissingInterpreterNamesThePathLookedFor` |
| 19 | App Support 0700 / flock / quit | `app/Tests/OhYesMLXKitTests/LauncherTests.swift::testSecondLauncherIsAlreadyRunningAndSpawnsNothing`, `::testQuitWhileAJobRunsClosesStdinAndNeverSignals`, `::testQuitEscalatesGraceThenTerminateThenKill`, `::testQuitReturnsTerminatedWhenSigtermStopsTheBackend`, `::testQuitReturnsExitedWhenTheBackendStopsItself`, `::testChildExitWhileRunningReportsStatusAndTheStderrTail` (mode 0700 itself: none — smoke `AC-2.app_support_mode` is live-only) |
| 20 | translocation guard | `app/Tests/OhYesMLXKitTests/AppModelTests.swift::testATranslocatedBundleAsksForApplicationsAndStartsNoJob` (covers `isTranslocated` both ways and `launch()` → `.moveToApplications`; the `relaunch()` and `start(_:)` guards at AppModel.swift:386-389/607-609 have no direct test named for them — see Q-note below) |

Full inventory of the smoke's pure-part tests (they guard §4 #16's helpers, not the live paths):
`tests/test_smoke_clean_account.py` — `test_launch_line_reads_port_and_token`, `test_launch_line_tolerates_blank_lines_but_not_two_lines`, `test_launch_line_refuses_every_shape_it_does_not_pin`, the three `test_the_launch_read_*`, four `test_sse_*`, two `test_forbid_scan_*`, `test_real_install_plans_carry_the_hash_pins`, `test_both_pip_engines_install_with_no_deps_and_wheels_only`, four `test_pip_argv_problems_*`/refusal tests, `test_add_check_*` ×2, `test_update_check_*`, `test_gate_*`, `test_counts_*`, `test_job_failed_*`, `test_hub_repo_dir_*` ×2, `test_ports_*`, `test_outcome_*`, `test_cell_outcomes_*` ×2 (the 05-01 structured-payload fix is pinned here), `test_a_failed_check_never_stops_the_recording`, `test_finish_writes_one_readable_json_file_at_0644`. Loader note from its docstring: it loads the script the way `tests/test_hash_freeze.py` loads its script (path import), so the .py's pure functions are tested without the .sh.

---

## 7. Open questions for the reviewer

**Q1 (mandated) — Can the build sign something it did not verify?** `scripts/build_app.sh:88-108`. Every Mach-O under `Contents/Resources/python` is signed and per-file `codesign --verify --strict`-ed (91-102), but classification is `file -b` matching `*Mach-O*` in a `find | while` subshell: a binary whose `file` description lacks "Mach-O" (odd magic, a fat slice, a Mach-O inside an archive in the tree) is never code-signed and is covered only by the app-level resource seal from `codesign --force --sign - "$APP"` (:106). Falsifiable: does `codesign --verify --deep --strict` (:107) actually fail on an unsigned nested Mach-O under Resources (making the net complete), or does --deep only inspect it as a resource? If the latter, the build can sign a bundle containing unverified executable code. The same question covers executable non-Mach-O files (shell scripts in the python tree): sealed as resources but never verified as code.

**Q2 (mandated) — What does a user who moves the app after installing pip engines actually see?** `docs/release/gatekeeper.md:21-24` says: "If you move the app after you have installed engines… install mlx-lm and OptiQ again: each engine is a Python environment built inside the app's own copy of Python, and moving the app leaves the old one behind." But nothing in the app is known to detect the stranded state: engine venvs are made from `sys.executable` (`ohyesmlx/engines.py:1173`), so after a move their `bin/python*` points at a dead bundle path, while `/engines` presumably still reports them installed (detection is `check_lab_dir`, `engines.py:387`, and `_venv_root`/`_relocate` at `:1059-1080` — worth reading to see whether a dead interpreter target is noticed). Falsifiable: does any code path turn "venv exists but its interpreter is gone" into a reinstall prompt, or does the user get an installed-looking row that fails at start with a raw error? The gatekeeper doc's copy promises the reinstall is straightforward; the app may not point the user to it.

**Q3 (mandated) — Can the SBOM disagree with what ships?** `scripts/make_sbom.py:94-113, 234-247`. `git_commit` is `git rev-parse HEAD`; `source_sha256()` hashes the **working tree** via `measure._source_sha256()`; what ships is `ditto "$ROOT/ohyesmlx"` from that working tree (`build_app.sh:68`), and the constraints are re-read from `REPO_ROOT` at SBOM time. In a dirty worktree the SBOM pairs a commit sha with a source digest that commit does not contain — the document can name a commit whose tree differs from the shipped code. Falsifiable: modify one .py without committing, run build_app.sh, and compare the SBOM's `source_sha256`/`git_commit` pair against `git show <commit>:ohyesmlx/...`. Is the intended reading "commit = context, source_sha256 = truth" (documented anywhere?), and should a release build refuse to stamp `git_commit` on a dirty tree?

**Q4 (mandated) — Does the gatekeeper doc promise anything the app does not do?** `docs/release/gatekeeper.md:47-67`. Three claims to check against the code: (a) ":52-53 — "A sha256 is published next to the zip. The release notes list the zip's sha256" — no script computes the zip's sha256 (`build_app.sh:124-129` prints paths; `shasum` exists only in `fetch_python_standalone.sh:45`), so this promise is entirely manual and can silently go unmet at release; (b) ":64-67 — "The app itself makes network requests only to Hugging Face … and to PyPI … Nothing is uploaded, and nothing is ever sent anywhere else" — the known egress is `fetch.py:56` (`HF_BASE`) and pip's index; the `engines.py:634-667` URLs are browser-opened vendor pages, not app fetches — is there truly no other egress in the served modules (catalog refresh, anything else)? (c) ":45 — "You only do this once per copy of the app. If you move or replace the app, macOS asks again" — plausible macOS behaviour, asserted without an in-repo check. Also verify the ":75" table claim "Created so that only your account can read it" against the actual creation (0700 at `BackendLauncher.swift:243-254` covers App Support; the smoke checks it live).

**Q5 — check_bundle's P5-9 env branch FAILs on macOS builds that withhold another process's environment, and the "decision it needs" was never made.** `scripts/check_bundle.sh:209-231`: when `ps eww` returns the argv with no environment block (the comment cites 27.2.1), the check lands on the `*)` branch and FAILs with "…needs a decision here". Yet the threat-model §10 status table records P5-9 **Met** on evidence "check_bundle P5-9: the backend's PATH is launchd's default" (2026-11-14) — implying the env block was readable that day. Falsifiable: run check_bundle on the current macOS against a good bundle; if the env block is withheld, a correct bundle exits non-zero. Should the withheld case be a SKIP-with-note (the property is pinned by `LauncherTests.testArgvEnvironmentAndDirectory`) rather than a FAIL, and which macOS behaviour did the 2026-11-14 evidence actually observe?

**Q6 — 05-06 AC-6 asks for a smoke of the built bundle, but the committed smoke spawns the wheel venv.** `scripts/smoke_clean_account.py:843-855` spawns `os.path.join(sys.prefix, "bin", "ohyesmlx")` — the 045-03 wheel install — with argv `["app"]`, not the launcher's `Contents/Resources/python/bin/python3 -I -B -m ohyesmlx.cli app` (`BackendLauncher.swift:185`) nor its built environment. 05-06-PLAN.md:89-95 (AC-6) wants "the built app's backend as `oymlxtest` (via the bundled interpreter, exactly the launcher's argv and env) and the existing `scripts/smoke_clean_account.sh` steps that need no engine install". Is AC-6 meant to be a hand-run variant of the client against the bundled interpreter (the scripts have no flag for it), or is the wheel smoke considered sufficient? As written, P5-5's "clean account pending" (threat-model §10 status) can only be closed for the wheel artifact, not the bundle a user downloads. Note the client would also then run under the bundled python — `parse_launch`'s docstring and the `tests/` loader assume the repo checkout.

**Q7 — Does `compileall` actually cover every `.py` the bundled interpreter can import at runtime?** `scripts/build_app.sh:76-77` compiles only `$CONTENTS/Resources/python/lib`, and the assertion (:78) proves pycs exist under `site-packages/ohyesmlx`, not that coverage is complete. The defect this fixed (05-06 finding #1: child interpreters writing `email/__pycache__` into the sealed bundle) returns silently wherever a `.py` outside the compiled tree — or a directory `compileall` does not walk (a symlink in the python-build-standalone layout, an uncompiled `lib-dynload` companion) — is imported by a child interpreter or an engine venv. Falsifiable: after a build, `find Contents/Resources/python -name '*.py'` minus the ones with sibling unchecked-hash `.pyc`, then run a child interpreter (`-c "import email"`) against the mounted read-only copy and see if anything tries to write.

**Q8 — P5-4 needs live internet, so a network hiccup reads as a packaging failure.** `scripts/check_bundle.sh:105-133` fails P5-4 (and so exits non-zero) whenever `https://huggingface.co/api/models/mlx-community/Qwen3-0.6B-4bit` does not answer 200 — a DNS outage, an HF incident, or an offline build machine makes a correct bundle look broken. The property being tested (system trust store under `env -i`) does not require that specific endpoint to be up. Is a transient-network FAIL acceptable for a release gate, or should P5-4 distinguish "TLS verification failed" from "the network was unreachable" (the current code asserts both in one step)?
