# Order: build a review dossier for one section of OYMLX (Fable 5.2 review, P0)

A senior reviewer (Claude Fable 5.2) will review this section next. Its tokens are scarce and expensive; yours are
not. Your dossier is what lets it spend its tokens on judgment instead of reading. Accuracy beats length: a wrong
line number or a false "already fixed" costs the reviewer more than a missing one.

Write exactly one file: `.paul/review/fable-5.2/dossier-<SECTION>.md` (the section id is at the end of this order).
Touch nothing else. Do not fix anything you find; list it. Target 15-25K tokens; hard cap 30K.

The dossier has these seven parts, in this order, with these headings:

## 1. Map
Every file and function in scope: `path:start-end — what it does (one line)`. Use `graphify query`/`graphify explain`
to locate, then confirm each range with `grep -n`/`sed -n`. Group by file.

## 2. Contracts
The rules that bind this code, as pointers plus the one or two binding sentences quoted: `docs/interfaces/*.md`
(grep the shapes this code produces or consumes), `AGENTS.md` (the rules that apply here), `docs/threat-model.md`
(rows that name this code), `docs/design/phase5/DESIGN.md` (app sections only).

## 3. Already known — do not re-report
Everything already found about this code, each with its source and status: threat-model §9 accepted risks and
§10 status table, STATE.md Deferred Issues and Blockers, the "Deviations"/"Carried forward" parts of every
`.paul/phases/v5-onboarding/*SUMMARY.md`, and every finding in `.paul/review/*/` logs with the commit that fixed it.
Format: `- <claim> — <source> — fixed <sha> | accepted | deferred | open`.

## 4. Hotspots
The 10-20 ranges where a defect would hurt most (user's Mac or data, a wrong or misattributed number, a race, a
trust boundary). Each: `path:start-end — why it is risky — which test guards it (or "none")`.

## 5. Mechanical scan
Grep results with locations, each one line, for the patterns listed in the section scope below (and for Python
always: `shell=True`, `os.system`, `eval(`, `exec(`, `pickle`, bare `except:`, `except Exception: pass`,
`chmod`, `tempfile.mktemp`, `open(` with `w` on a path built from input, `subprocess` without a timeout,
`json.loads` on unbounded input; for Swift always: `try!`, `!` force-unwrap on optionals from I/O, `fatalError`,
`DispatchQueue.main.sync`, `@unchecked Sendable`, `Task {` without cancellation handling, `print(`).
Say "none" for a pattern with no hits. Do not judge them; list them.

## 6. Test inventory
For each hotspot: the test(s) that would fail if it broke (`tests/…::name` or `app/Tests/…`), or "none".

## 7. Open questions for the reviewer
5-10 specific, falsifiable questions where you suspect a problem but could not prove it, each with the location.

Rules: read-only except the one dossier file; never start a server, engine or app; never run the test suites
(the coordinator does); quote code minimally (a line or two), point instead of pasting.
Report when done: the dossier path, its size in characters, and the three map lines you are least sure of.

---
SECTION:
S1 — Security and trust boundaries.
Scope: ohyesmlx/server.py (whole: guard, routes, jobs, SSE, cancel/abort, shutdown); the security-relevant ranges of
ohyesmlx/engines.py (install plans, `_command_plan`, `_real_run`, `kill_running_steps`, `_check_hashed_requirements`,
`check_lab_dir`, `record_lab_path`, guided downloads), ohyesmlx/fetch.py (URL/redirect guard, path guard, ledger, disk
checks, evict), ohyesmlx/cli.py (`app` subcommand, `_recover_startup`), ohyesmlx/runtimes.py (`stop_orphaned_engines`,
`stop_own_engines`, ledger, `_resolve_program`, `_engine_env`), ohyesmlx/__init__.py (`app_support_dir`, writable root),
app/Sources/OhYesMLXKit/{BackendLauncher,HTTPBackend,BackendToken}.swift, scripts/build_app.sh (signing),
docs/threat-model.md (all of it: map each T-finding to the code that closes it).
Extra scan patterns: `Origin`, `Host`, `Authorization`, `compare_digest`, `0o7`, `umask`, `os.replace`, `symlink`,
`realpath`, `..`, `Content-Length`, `--require-hashes`, `--isolated`, `-I`, `PATH`.
Extra open questions to include: can a web page reach the API (DNS rebinding, simple requests); can a job argument
reach a filesystem path or argv unvalidated; can two app instances or a stale ledger make the backend kill a process
it did not start; what a malicious HF repo or a compromised PyPI file could do.
