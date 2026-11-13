---
phase: 045-security
plan: 03
type: Summary
about: "OhYesMLX"
status: applied (code review pending)
completed: 2026-11-13
duration: "2026-11-13, one session (plan, audit, scripts, two live runs, two fixes)"
commits: [743ada3, 369f180]
tests: "1281 -> 1324 passed"
description: "Clean-account smoke as oymlxtest: 21/21 checks pass after fixing two defects only a fresh account could show — optiq could not install without Homebrew SDL, and the three app engines could not start under launchd's PATH"
---

# 045-03 SUMMARY: clean-account smoke

The v5.0 backend was built from `git archive HEAD` into a wheel, installed into a venv in the home of
`oymlxtest` (uid 502, standard user, created by Jason 2026-11-13), and driven end to end the way the Swift
client will drive it: spawned with a held stdin pipe, launch line read from its stdout, every API surface a
first-time user reaches exercised. Run 1 found two code defects; both were fixed test-first and run 2 passed
every check. Jason's account was verified unchanged after both runs.

## Commits

| Commit | Contents |
|---|---|
| `743ada3` | PLAN + AUDIT; `scripts/smoke_clean_account.{sh,py}` and 34 tests (Task 1, Command Code); the host fetch ledger's scratch residue removed (AC-9); PREAMBLE refreshed (18 modules, graphify-first, pace rule). 1315 tests. |
| `369f180` | F1 and F2 fixes (two parallel Command Code orders), `interfaces.md` and STATE follow-ups, run-1 evidence. 1324 tests. |

## Acceptance criteria

| AC | Result | Evidence |
|---|---|---|
| AC-1 setup builds what a user gets | PASS | `preflight: ok` both runs (sudo -n, six ports free, Osaurus app not running, `xcode-select -p`, ≥5 GiB, no prior state). Wheel `ohyesmlx-0.3.0-py3-none-any.whl` from `git archive HEAD`; venv by `python3.14 -I -m venv`; every step under `env -i` with launchd's PATH. |
| AC-2 backend starts the way the app will | PASS | `AC-2.launch_line` PASS (one stdout line, no extras during the run); `AC-2.app_support_mode` PASS, `0o700`. |
| AC-3 read endpoints describe a fresh Mac | PASS | `/hardware`, `/engines`, `/recommendations` 200; mlxlm and optiq not installed with hash-pinned plans; app engines reported installed (bundles in `/Applications` are shared); `/quickbench/plan` 400 `bad_args` "download it first"; no token → 401; **no response body or SSE line contained `/Users/jrazz`** (`AC-3.no_host_paths`). |
| AC-4 hash-pinned installs succeed | PASS (run 2) | mlxlm 11.5 s, optiq 15.1 s (first→last SSE event); both named in oymlxtest's `lab-paths.json`, both pass `check_lab_dir`, `/engines` reports both installed. Run 1: optiq FAILED (F1). |
| AC-5 download, quickbench, evict | PASS (run 2) | Download 140 s, 174 events; `/quickbench/plan` 200 after it; quickbench cells: mlxlm PASS, optiq PASS, **omlx PASS** (from its bundle, F2), osaurus SKIPPED (`osaurus: false` by plan), stage B omlx PASS, vmlx N/A (environment, below); evict PASS, model dir and ledger entry gone. Quickbench numbers are not results and are not recorded here. |
| AC-6 shutdown leaves nothing behind | PASS | stdin closed → exit 0; all six ports free. The `pgrep -lu oymlxtest` diff shows only `mdworker_shared` (Spotlight) appearing — macOS per-user services, not the smoke. The plan's "snapshot equals" wording was too strict for a live account; the check that matters (no engine, no app, no port) holds. |
| AC-7 Jason's account untouched | PASS | `verify-host: Jason's account is unchanged` after run 1 and after run 2 (Application Support listing + `cmp` of `lab-paths.json`/`fetched.json`, HF cache listing, `~/.osaurus/config` per file). |
| AC-8 findings fixed, not just noted | PASS | F1 and F2 fixed with red tests and re-run live; environment causes recorded below. |
| AC-9 host ledger residue gone | PASS | Entry `mlx-community/Qwen3.5-2B-4bit` (60 paths, 0 inside the real cache) removed through `fetch._ledger_save`; the ledger is `{"repos": {}}`; backup `045-03-evidence/fetched.json.before-ledger-cleanup`. |

## Findings

**F1 — optiq could not install on a typical Mac (fixed, `369f180`).** Run 1: `step_failed` after 18 s.
Reproduced by hand as oymlxtest: pygame 2.6.1 (no cp314 wheel) built from source per `engines._SOURCE_BUILDS`
fails with `fatal error: 'SDL.h' file not found` (`045-03-evidence/run1-optiq-pip-repro.log`). The 045-02b
live install passed only because Jason's Homebrew has `sdl2`. pygame is imported only by `optiq game`
(lazy `from .game import run`, `optiq/cli.py:2104`; `pip show pygame` → Required-by: mlx-optiq only).
Fix: pygame removed from `constraints/optiq-0.5.13.txt`, `_SOURCE_BUILDS` deleted, every pip step gains
`--no-deps` (the file is the whole closure). Every install is now wheels-only and fully hash-checked; the
threat-model §9 source-build row is resolved and STATE's monthly pygame-wheel watch is gone. This supersedes
Jason's 2026-11-10 call (STATE Decisions, struck through with the reason). Run 2 proves `optiq serve` works
without pygame (optiq cell PASS). Jason's own lab copy still has pygame; serving code is identical.

**F2 — oMLX, vMLX and Osaurus could not start under launchd's PATH (fixed, `369f180`).** Run 1:
`could not start omlx: [Errno 2] No such file or directory: 'omlx'` (vmlx the same), while `/engines`
said both were installed. The start commands use bare names that resolve only through per-user shims on a
developer's shell PATH (`~/.omlx/bin/omlx`, Jason's hand-made `~/.local/bin/vmlx`, `osaurus` →
`Contents/Helpers/osaurus`). The shipped app's backend gets launchd's PATH (P5-9), so in the app these three
engines would never have started for anyone. Fix: `runtimes.ENGINE_BUNDLE_EXECUTABLES` and
`_resolve_program`, used by `_spawn` and `_run` only; a name that does not resolve on the child's PATH execs
the in-bundle tool. Recorded start commands are byte-identical, and a name that resolves (Jason's harness) is
untouched. Match sites (Osaurus app detection, orphan ledger, `serving_argv`) were checked and none changes.
Run 2: omlx PASS from the bundle.

**Environment, not code:**
- **vMLX cannot run from any account but the one that installed it, on this Mac.** Its bundled Python is
  `drwx------ jrazz /Applications/vMLX.app/Contents/Resources/bundled-python`. A user who installs vMLX
  owns that directory, so a single-user Mac is unaffected. The resolver found the path but `os.access(X_OK)`
  is false for oymlxtest, so the bare name was kept and the start failed as before.
- **`/engines` reports vMLX installed for an account that cannot run it** (detection checks the bundle,
  not executability). Deferred: only a multi-user Mac where another account installed vMLX hits it.
- **oMLX writes `~/.omlx/bin/omlx-cluster-python` (493 bytes) whenever it serves**, despite the per-run
  `--base-path`. oMLX's own behaviour; harmless; evict and teardown do not remove it.
- **A failed install's pip output reaches the client but not the install log.** The `error` event carries
  `payload.output_tail` (`engines.py:1276`); `install-log.jsonl` records only step and exit code. Not changed.

## Deviations

1. **Two live runs, not one.** Run 1 exposed F1 and F2; run 2 is the acceptance run. Both are kept in
   `045-03-evidence/` (`run1-*`, `run2-*`).
2. **The first Task 1 dispatch timed out** after 30 minutes having written nothing (the background default,
   not the order's fault entirely: it read whole 1,000-line files). Re-dispatched with a 2-hour limit and a
   pace note; PREAMBLE gained "Code graph — use it first" and "Pace"; every dispatch now has a 5-minute
   progress monitor (Jason, 2026-11-13).
3. **Coordinator edits to the worker's scripts:** host snapshot directory `0700` (it holds copies of Jason's
   config under world-readable `/Users/Shared`), `..` dropped from the `ls -laT` comparison (Application
   Support's own mtime moves with any app), and the quickbench SSE stream kept in the results as evidence.
4. **The ledger was rewritten once with no change before the real edit** (a wrong key guess); mode went
   `0644` → `0600`, which is what `_ledger_save` writes.
5. **`/etc/sudoers.d/oymlxtest`** (`jrazz ALL=(oymlxtest) NOPASSWD: ALL`, run-as oymlxtest only) was added
   by Jason for this plan. Removing it needs root: **Jason runs `sudo rm /etc/sudoers.d/oymlxtest`.**

## Teardown

oymlxtest's venv, Application Support/OhYesMLX, HF cache, `~/.omlx` and `~/.cache` removed; `/Users/Shared/oymlx-smoke`
keeps only `results/`. The account itself stays (Jason's).

## Code review

Pending (Standards + Spec, `6cdf9aa..HEAD`).
