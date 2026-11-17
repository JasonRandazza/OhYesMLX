---
phase: 05-app
plan: 10b
plan_type: tdd
wave: 1
depends_on: ["05-09", "05-10"]
files_modified: [ohyesmlx/runtimes.py, ohyesmlx/measure.py, ohyesmlx/quickbench.py, AGENTS.md, docs/interfaces.md, docs/runtimes/omlx.md, docs/runtimes/vmlx.md, docs/runtimes/mtplx.md, docs/runtimes/osaurus.md, tests/test_port_independence.py, tests/test_runtimes*.py, tests/test_measure*.py, tests/test_quickbench*.py]
autonomous: false
description: "Port independence: a resident engine is found by its process, on whatever port it listens, and the start refusal names engine, pid and port; a default port held by something that is not an engine no longer blocks a start -- the engine gets a free port, passed with --port and recorded on every row"
type: Plan
about: "OhYesMLX"
---

<objective>
## Goal
Close the gap 05-09's AC-8 left (ROADMAP "Plan 05-10b", Jason 2026-11-16), steps (1) and (2) only:

1. **Resident engines by process.** One `ps` scan matches every engine's processes (as Osaurus's app is already matched
   by full executable path) and `lsof` reads the port each listens on. `Runtime.start` refuses while any engine is
   resident, whatever its port, and the refusal names the engine, the pid and the port.
2. **Free-port fallback.** Default ports stay. When a default port is held by a process that is not an engine, the
   harness picks a free loopback port, passes it with `--port`, and records the port on every row. No engine settings
   file is touched.

## Purpose
Two failures today, both from treating "a listener on one of six ports" as "an engine is resident":
- A user's engine on a non-default port (an oMLX app server on 8001, say) is invisible, so a second model can load
  beside it and every number in the run is silently corrupted (AGENTS.md "Exactly one model is resident").
- An unrelated dev server on 8000/8080/8081/8100/8200 blocks every start, though nothing is resident.

## Output
`ohyesmlx/runtimes.py` (resident scan, port choice, ledger stop command by engine name), `ohyesmlx/measure.py` (`port`
on each row), `ohyesmlx/quickbench.py` (skip reason asks the scan); one new test file plus edits to existing ones;
AGENTS.md "Ports" hazard line; `docs/interfaces.md` row field; `docs/runtimes/*.md` process signatures;
`05-10b-SUMMARY.md`.
</objective>

<context>
## Project Context
@AGENTS.md (one model resident; ports; one definition of everything; never infer a capability from a missing flag)
@.paul/STATE.md
@.paul/HANDOFF.md (worker routing while Command Code is limited; worktree/stash/venv traps)
@.paul/phases/v5-onboarding/05-09-SUMMARY.md (AC-8: a start refuses while any engine port or Osaurus app is resident)

## Source Files (landmarks, read 2026-11-17)
- `ohyesmlx/runtimes.py`
  - `RUNTIMES` (l.4134): six `Runtime(name, port)`; every subclass builds its argv from `self.port`.
  - `Runtime.start` (l.~2575): loops `_port_is_free` over every `RUNTIMES` port, then `_resident_osaurus_pids()`.
  - `_resident_osaurus_pids` (l.685): `ps -axo pid=,args=`, argv0 in `OSAURUS_APP_EXECUTABLES`.
  - `ENGINE_BUNDLE_EXECUTABLES` (l.~170): in-bundle CLIs for omlx, vmlx, osaurus.
  - `_port_is_free`, `_listener_pids` (l.734, 747): lsof, unreadable = busy.
  - `_record_running_engine` (l.1920) records `port`; `_stop_command_for_port` (l.2024) maps port -> runtime.
  - `Osaurus.start_command` (l.2830): `osaurus serve --port N --yes`.
- `ohyesmlx/quickbench.py` `_skip_reason` (l.463): `port_in_use(RUNTIMES[name].port)` -> "quit {name} first".
- `ohyesmlx/measure.py`: `CellResult.runtime_version` / `mlx_version` (l.267-283) set at the first started visit
  (l.880); record written l.~1561; `load_run` reads with `record.get` (l.1658).
- `~/.osaurus/config/server.json` holds `"port": 1337` (read 2026-11-17). Whether `osaurus serve --port N` rewrites
  that file is not established.
</context>

<acceptance_criteria>

## AC-1: An engine on a non-default port blocks a start, and the refusal names it
```gherkin
Given a process whose argv matches an engine's signature is listening on a port that is not that engine's default
  (e.g. `omlx serve ... --port 8001`, or the oMLX/vMLX/MTPLX app's own server)
When any runtime's start is attempted
Then the start is refused before anything is spawned
And the message names the engine, the pid and the port it listens on ("unknown" when lsof cannot read it)
```

## AC-2: One definition of "an engine process"
```gherkin
Given the six runtimes
When the resident scan, the start refusal, the stale-Osaurus sweep and quickbench's skip reason ask whether an engine is resident
Then they all ask one function over one signature table
And the Osaurus app is still matched by full executable path and never by the name `osaurus` (`osaurus mcp` is not an engine)
And `_resident_osaurus_pids` callers keep their behaviour (it becomes a filter over the shared scan, or is deleted in favour of it)
```

## AC-3: A non-engine on a default port no longer blocks; the engine moves
```gherkin
Given a process that is not an engine listens on a runtime's default port (e.g. a dev server on 8000)
And no engine is resident
When that runtime starts
Then it is started on a free loopback port, passed with `--port`, and the handle, base_url, readiness probe, ledger
  entry and stop all use that port
And one stderr line names the default port, its holder's pid and the port chosen
And a default port that is free is used unchanged (every existing start command is byte-identical in that case)
```

## AC-3b: An unrecognised model server is never moved around <!-- audit-added M1 -->
```gherkin
Given a default port is held by a process the signature table does not match
When the port decision runs
Then the holder counts as resident (the start is refused, naming pid, executable and port) if EITHER
  its executable path lies inside any known engine install root (the bundles in `ENGINE_BUNDLE_EXECUTABLES`,
  `OSAURUS_APP_BUNDLES`, `/Applications/MTPLX.app`, `~/.mtplx`, the lab venvs from `lab-paths.json`)
  OR `GET http://127.0.0.1:<port>/v1/models` (no credential, 2 s timeout) answers 200 with a JSON object holding a
  `data` list, or 401/403
And only a holder that passes neither test is a non-engine, and only then does the engine move
And a probe that times out or is refused counts as "not a model server" (recorded residual: an engine mid-load whose
  argv and executable are both unrecognised)
```

## AC-4: Osaurus does not move
```gherkin
Given port 1337 is held by a process that is not an engine
When Osaurus starts
Then the start is refused, naming the holder's pid, and nothing is spawned
Because Osaurus's port also lives in `~/.osaurus/config/server.json`, which the harness does not edit, and whether
  `serve --port` rewrites that file is not established (AGENTS.md: a negative claim needs the source)
```

## AC-5: The port is on every row
```gherkin
Given a measured cell
When its row is written to results.jsonl
Then the row carries `port`, the port the cell's first started visit served on
And a later visit on a different port emits one stderr line naming both, and is not a failure
And `load_run` reads a row written before this plan as `port = None`, and a run header/grid join is unaffected
```

## AC-6: An orphan on a fallback port can still be stopped
```gherkin
Given a ledger entry written by a run whose engine was on a fallback port
When the next launch's orphan sweep or "Stop now" stops it
Then the stop command is derived from the entry's engine name via RUNTIMES (never an argv read from disk, Fable S5-F13)
And an entry written before this plan (no engine name) still resolves by port, as today
```

## AC-7: Quickbench skips only for an engine
```gherkin
Given quickbench plans its cells
When an engine's default port is held by a non-engine
Then that engine is not skipped (it will take a fallback port), except Osaurus (AC-4)
And an engine resident on any port still skips with "quit {name} first" naming its pid and port
```

</acceptance_criteria>

<tasks>

<task type="auto">
  <name>Task 1: Resident engines by process (red tests first)</name>
  <!-- audit-added M2: matching robustness -->
  <files>ohyesmlx/runtimes.py, ohyesmlx/quickbench.py, tests/test_port_independence.py, tests/test_runtimes*.py, tests/test_quickbench*.py, docs/runtimes/{omlx,vmlx,mtplx,osaurus}.md</files>
  <action>
    0. Signatures, read-only, before code. For each engine, establish what its server process's `ps args` look like:
       - CLI starts: the harness's own argv (`python -m mlx_lm.server`, `optiq serve` -- a console script shows as
         `<python> <path>/optiq serve`, `omlx serve`/`omlx-cli serve`, `vmlx serve`, `~/.mtplx/bin/mtplx serve`).
       - App-launched servers (oMLX.app, vMLX.app, MTPLX.app, Osaurus): read each bundle's launcher/source for the argv it
         spawns. Record each in `docs/runtimes/<name>.md`. Where the bundle does not settle it, write exactly that
         ("not established from the bundle") and match only what is established -- never a bare name like `osaurus`,
         `vmlx` or `omlx` anywhere in argv (MCP clients and shells carry these).
       Start no engine for this survey.
    1. Red tests in `tests/test_port_independence.py` with an injected `ps`/`lsof` (the existing `_run` seam):
       an engine argv on a non-default port refuses with engine+pid+port (AC-1); `osaurus mcp` and a shell whose argv
       mentions `mlx_lm.server` as an argument to grep/less are not engines; a lab-venv engine whose path contains
       a space (`~/Library/Application Support/...`) is matched; lsof unreadable for a matched engine still
       refuses, port "unknown"; quickbench skip for a resident engine names pid and port (AC-7). Confirm red.
    2. Add one signature table (keyed by runtime name, derived from the start commands' program tokens and
       `ENGINE_BUNDLE_EXECUTABLES`/`OSAURUS_APP_EXECUTABLES` -- one definition, no second copy of a path) and one
       `resident_engines() -> tuple[(name, pid, ports)]` doing `ps -ww -axo pid=,comm=` and `ps -ww -axo pid=,args=`
       (joined by pid; a pid in only one is skipped) plus `lsof -nP -iTCP -sTCP:LISTEN -a -p <pids>`. Match on the
       executable path (`comm`) first, and on `args` only with regexes anchored at token boundaries
       (`(^|[ /])optiq serve( |$)`, interpreter executable + ` -m mlx_lm.server( |$)`); never split argv on whitespace,
       because lab paths contain spaces.
       `ps` unreadable raises `RuntimeStartError` (fail closed, as `_resident_osaurus_pids` does today).
    3. `Runtime.start`: replace the per-port loop + `_resident_osaurus_pids` refusal with `resident_engines()`.
       `_resident_osaurus_pids` becomes a filter over the scan, or is deleted if no caller needs it (AC-2).
    4. `quickbench._skip_reason`: ask the same port decision `Runtime.start` asks (Task 2's `port_plan`), keeping
       its injectable seams, so quickbench never says "go" for a start that will refuse. <!-- audit-added S1 -->
    Avoid: matching by port anywhere in the resident decision; adding a CLI flag or setting (step 3 of ROADMAP is out).
  </action>
  <verify>New tests red before, green after; `…/test-venv/bin/python -m pytest -q` green</verify>
  <done>AC-1, AC-2, AC-7 satisfied</done>
</task>

<task type="auto">
  <name>Task 2: Free-port fallback, ledger by engine name, port on every row</name>
  <files>ohyesmlx/runtimes.py, ohyesmlx/measure.py, tests/test_port_independence.py, tests/test_runtimes*.py, tests/test_measure*.py</files>
  <action>
    1. Red tests: a non-engine listener on 8000 -> vMLX starts with `--port <free>`, handle.port/base_url match, one
       stderr line names default, holder pid, holder executable and chosen port (AC-3); a holder answering `/v1/models`
       with a `data` list, or 401, or whose executable is inside an engine root, refuses (AC-3b, local fake HTTP
       server in the test); the free-default case is byte-identical to today's
       argv for all six runtimes; Osaurus with a non-engine on 1337 refuses naming the holder (AC-4); a ledger entry with
       `runtime: "vmlx", port: 54321` resolves vMLX's stop command, and a pre-plan entry without `runtime` still
       resolves by port (AC-6); a row carries `port`, an old row loads as `None` (AC-5).
    2. One function `port_plan(runtime) -> int | refusal` holds the whole decision (resident scan, AC-3b holder tests,
       Osaurus, unreadable lsof) and both `Runtime.start` and quickbench ask it. In it: if `self.port` is held and the
       holder passes neither AC-3b test -> Osaurus refuses; others pick a port by binding `127.0.0.1:0` and closing, then continue as
       `dataclasses.replace(self, port=chosen)` so every argv, probe, `_serving_pid`, ledger write and stop reads one
       value. `# ponytail:` the bind-close-spawn race; the existing readiness/`_serving_pid` checks catch a stolen port.
       An unreadable default port stays a refusal (fail closed, as today).
    3. `_record_running_engine` also records `runtime` (the name); `_stop_command_for_port` becomes a lookup by name
       with the port lookup as the fallback for entries without one. Still derived from `RUNTIMES`, never from disk.
    4. `measure.py`: `CellResult.port: int | None = None`, set beside `runtime_version` at the first started visit; a
       differing later visit -> one stderr line, not a failure; written to the record; `load_run` uses `record.get("port")`.
       Do not add it to the run header and do not touch the join guards.
    Avoid: reading or writing any engine settings file; changing any default in `RUNTIMES`.
  </action>
  <verify>New tests red before, green after; full pytest green; `git diff` shows no change to any default port or settings path</verify>
  <done>AC-3, AC-3b, AC-4, AC-5, AC-6 satisfied</done>
</task>

<task type="auto">
  <name>Task 3: Docs where the rules live</name>
  <files>AGENTS.md, docs/interfaces.md</files>
  <action>
    - AGENTS.md "Ports:" line: defaults unchanged; when a default is held by a non-engine the harness moves the engine
      to a free port and records it per row; Osaurus never moves; resident engines are found by process, not port.
      One sentence each, no restated rationale (it lives in `runtimes.py`).
    - AGENTS.md Ports line also says: the runner scripts still sweep default ports by kill -9 (they would kill a
      user's dev server there); an engine on a fallback port is not theirs to sweep. <!-- audit-added S4 -->
    - `docs/interfaces.md` row schema: `port` (int, null on rows before 2026-11-17).
  </action>
  <verify>`git diff AGENTS.md docs/interfaces.md` reviewed by the coordinator</verify>
  <done>AC-3..AC-5 documented where callers look</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <what-built>Process-based resident detection and the free-port fallback</what-built>
  <how-to-verify>
    Needs Jason's "when" (a live engine start; nothing else may run on the machine meanwhile).
    Do NOT use `scripts/run_canary.sh`: its `sweep()` kill -9s whatever holds 8081, which would remove the test
    listener and never exercise the fallback (audit M3). Run the CLI directly with the test venv.
    1. Hold 8081 with a non-engine: `python3 -m http.server 8081 --bind 127.0.0.1`.
    2. `…/test-venv/bin/python -c 'import sys; from ohyesmlx.cli import main; sys.exit(main())' canary --yes --engines mlxlm`:
       it starts on a free port, the row's `port` is that port, coherence PASS, the stderr line names 8081's holder,
       the chosen port is released after, and the http.server is still alive.
    3. Start `mlx_lm.server` by hand on 8091 with a small model; a canary for any engine is refused naming
       mlxlm, its pid and 8091. Stop it; confirm 8091 free.
  </how-to-verify>
  <resume-signal>Type "approved", or describe what differed</resume-signal>
</task>

</tasks>

<boundaries>

## DO NOT CHANGE
- Default ports in `RUNTIMES`, and any engine's argv when its default port is free.
- Any engine settings file (`~/.osaurus/`, `~/.omlx/settings.json`, app plists); `scripts/osaurus-pin.sh`.
- 05-07..05-10 surfaces: the lab PATH split, `cold_load_s` spawn-to-ready, ledger identity (`same_process`), the early
  ledger write before the clock, `fetch`/`hardware` disk and download code.
- The run header, `--cells`, the join guards.

## SCOPE LIMITS
- No user port override (ROADMAP step 3): no CLI flag, no app setting, no new subcommand or module.
- No app (Swift) change: rows gain a field the app's decoder already tolerates (05-10 finding: extra keys are ignored).
- No live engine start by a worker; the live check is the checkpoint, at Jason's "when".
- No download.
- The runner scripts' `sweep()` (kill -9 by default port, ~20 scripts) is unchanged; it is pre-existing and out of
  ROADMAP scope. An engine on a fallback port is stopped by the harness's own handle and ledger. <!-- audit-added S4 -->

</boundaries>

<verification>
Before declaring plan complete:
- [ ] `/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python -m pytest -q` green (main at 1501)
- [ ] Each new test observed red on unfixed code by the coordinator
- [ ] Argv byte-identical for all six runtimes when the default port is free (test)
- [ ] No match on a bare engine name anywhere in argv (test with `osaurus mcp` and a grep line)
- [ ] An unrecognised holder that answers `/v1/models`, or lives in an engine root, refuses (AC-3b test)
- [ ] `Runtime.start` and quickbench ask one `port_plan`; no second port decision exists (grep)
- [ ] `docs/runtimes/*.md` say what each app-launched server's argv is, or that the bundle does not settle it
- [ ] `graphify update .`
- [ ] Live checkpoint run, or recorded as pending Jason's "when"
- [ ] Two-axis review (Standards + Spec) before UNIFY
</verification>

<success_criteria>
- All tasks completed; AC-1..AC-7 met
- A dev server on any default port except 1337 no longer blocks a run
- An engine on any port blocks a start, by name, pid and port
- Old run directories still load and join
</success_criteria>

<output>
After completion, create `.paul/phases/v5-onboarding/05-10b-SUMMARY.md`
</output>
