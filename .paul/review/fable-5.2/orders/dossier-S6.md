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
S6 — Packaging and release.
Scope: scripts/build_app.sh, scripts/check_bundle.sh, scripts/fetch_python_standalone.sh, scripts/make_sbom.py,
scripts/smoke_clean_account.sh and .py, scripts/dev_backend_venv.sh, app/Resources/Info.plist,
docs/release/gatekeeper.md, .gitignore, the launcher's production-path code in
app/Sources/OhYesMLXKit/BackendLauncher.swift, the translocation guard in AppModel.swift.
Contracts: docs/threat-model.md §10 (all rows + the 2026-11-14 status table), PLAN.md D6/D7,
.paul/phases/v5-onboarding/05-06-PLAN.md and 05-06-SUMMARY.md.
Extra scan patterns: `set -e`, unquoted `$`, `rm -rf`, `codesign`, `--deep`, `hdiutil`, `ditto`, `shasum`, `curl`,
`xattr`, `compileall`, `-B`.
Extra open questions: can the build sign something it did not verify; what a user who moves the app after
installing pip engines actually sees; whether the SBOM can disagree with what ships; whether the gatekeeper doc
promises anything the app does not do.
