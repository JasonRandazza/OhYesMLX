# Order: verify one Fable 5.2 finding (V step)

You verify one finding from a senior reviewer. Its report is a claim, not evidence. Your job is to prove it or refute it.

You run inside the `fable-verify` Orca worktree (branch `review/fable-verify`). Write exactly one report file:
`.paul/review/fable-5.2/verify/<FINDING-ID>.md`. If you can write a test, put it in a NEW file named after the finding
(`tests/test_fable_<finding-id>.py`, or `app/Tests/OhYesMLXKitTests/Fable<FindingId>Tests.swift`), so parallel
verifiers never edit the same file. Never fix the code.

Method:
1. Read the cited code (the ranges named) and its dossier entry. The dossiers live in the main checkout (read-only, absolute path):
   `/Users/jrazz/Dev/active/OhYesMLX/.paul/review/fable-5.2/dossier-S<n>.md`. Restate the claim in one line.
2. Try to reproduce it with the smallest failing test (pytest, or a swift test in app/Tests). Run only that test:
   `/Users/jrazz/.local/share/ohyesmlx/test-venv/bin/python -m pytest -q <file>::<name>` or
   `cd app && swift test --filter <name>`. A test that passes on the current code means the claim is not reproduced.
3. If no test is possible (a race needing real timing, a GUI-only path, packaging), give the concrete evidence instead:
   the exact code path with line numbers, or a command and its output.
4. End the file with exactly one verdict line:
   `VERDICT: CONFIRMED (test: <path::name>)` or `VERDICT: CONFIRMED (no test: <why>)` or `VERDICT: REFUTED (<evidence>)`
   and a line `SEVERITY-CHECK: agree | lower to <x> | raise to <x> — <why>`.
Never start a server, engine, model download or the app. Never edit code outside the one test you add.

---
FINDING:
 (BATCH) S5-F11 S5-F12 S5-F13 S5-F14

BATCH RULE: verify each finding below separately, one after another, applying the method above to each and writing
one report per finding (verify/<FINDING-ID>.md, each ending in its own VERDICT and SEVERITY-CHECK lines) and one test
file per finding. These are Low severity: prefer reading the code path and citing it when a test would need more
than about 40 lines. Do not spawn subagents. If tests/test_fable_<id>.py already exists (a killed earlier run), run and reuse it rather than rewriting it.

=== FINDING-ID: S5-F11 ===
### F11 — `Handle.stop` can signal the process group of a stranger that inherited a reaped launcher pid
- Severity: Low (needs pid reuse within one cell; the blast radius is a whole same-user process group)
- Where: `ohyesmlx/runtimes.py:612-631` (`_process_alive`), `:651-659` (`_signal_tree`), `:1663-1672` (`_shutdown`)
- Failure scenario: `osaurus serve` is a launcher that exits after hand-off. `await_ready` polls `_process_alive(pid)`, whose `waitpid(WNOHANG)` reaps it, freeing the pid for reuse while the handle keeps it for the whole cell (minutes, two visits). At stop, `_process_alive(pid)` falls through to `os.kill(pid, 0)`, which succeeds for any same-user process now holding that number; `_signal_tree` then sends SIGTERM and, after the grace period, SIGKILL to `os.getpgid(pid)` — the stranger's group. `_stop_orphan` proves identity before this; the live path does not. Distinct from S1-F1 (stale ledger file).
- Evidence: `os.killpg(os.getpgid(pid), sig)`; no record that the pid was already reaped.
- Confidence: 60 on the logic; the reuse probability on a quiet benchmark Mac is small and unmeasured.
- Fix direction: keep the `Popen` (or a "reaped" flag) on the handle and never signal a pid this process has already reaped; for the Osaurus launcher, signal only `serving_pid` after an identity check.
- Test idea: spawn `true`, let `_process_alive` reap it, patch `os.kill` to succeed for that pid; assert `_shutdown` does not call `os.killpg`. Fails today.


=== FINDING-ID: S5-F12 ===
### F12 — `osaurus_set_seqs` rewrites the live host config in place, outside the module that owns the edit
- Severity: Low (a kill between truncate and write leaves an empty `server-runtime.json`; the backup heals it only if a restore then runs — see F6/F7)
- Where: `scripts/osaurus-pin.sh:46-67`
- Failure scenario: `json.dump(runtime, open(conf, 'w'), indent=2)` truncates the user's file before writing, with no temp-and-rename, bypassing `osaurus_settings._write_atomic` and the key list `pin` owns (a second definition of "edit the host and re-record the baseline"). The argument check passes `0` though the message says "positive", so a run can set `maxConcurrentSequences = 0` and re-record it as the baseline.
- Evidence: quoted line; `''|*[!0-9]*)` is the only validation.
- Confidence: 75.
- Fix direction: a `set_key`-style function in `osaurus_settings` (atomic write, read-back, baseline) that both `pin` and the wrapper call; reject 0.
- Test idea: `osaurus_set_seqs 0` against a scratch config; assert non-zero exit. Fails today.


=== FINDING-ID: S5-F13 ===
### F13 — The ledger's `stop_command` is data on disk that gets executed
- Severity: Low (same-user tampering only; it is an exec primitive the design does not need)
- Where: `ohyesmlx/runtimes.py:1693-1783` (record/read), `:1827-1864`, `:1908-1937`
- Failure scenario: any same-user process writes `running-engines/<live owner or own pid>.json` with a `stop_command` of its choosing. In `stop_own_engines` it is run with no identity check (S1-F1's path); in `_stop_orphan` it is run once the pid/port identity matches, which an attacker who started the listener controls. Correction to the dossier's Q7: in `_stop_orphan` the identity checks do precede the command; only "Stop now" runs it unchecked.
- Evidence: `_shutdown(pid, port, _entry_stop_command(entry))`.
- Confidence: 60 that it is worth acting on; the fix is a deletion.
- Fix direction: derive the stop command from `RUNTIMES` by the recorded port and delete the field from the ledger.
- Test idea: ledger entry with `stop_command: ["/usr/bin/touch", "<tmp>/x"]` on a matching identity; assert `<tmp>/x` does not exist after `stop_orphaned_engines`. Fails today.


=== FINDING-ID: S5-F14 ===
### F14 — The Osaurus app is recognised only under `/Applications`
- Severity: Low on this Mac; Medium for the shipped app on other Macs (a stale app the sweep cannot see is a second resident model)
- Where: `ohyesmlx/runtimes.py:149-152`, `:163-172`, `:634-648`
- Failure scenario: Osaurus installed to `~/Applications` (Homebrew `--appdir`, or a user without admin rights). `_resident_osaurus_pids` matches only the two `/Applications` executables, so the stale-app refusal never fires and the post-`osaurus stop` kill never finds the app; it stays resident at ~900 MB plus weights through every later cell. `ENGINE_BUNDLE_EXECUTABLES` has the same assumption, so under launchd's PATH the engine also reads as installed-but-unstartable.
- Evidence: `OSAURUS_APP_BUNDLES = ("/Applications/osaurus.app", "/Applications/Osaurus.app")`.
- Confidence: 50 (not checked how `/engines` detection locates the bundle; if it also assumes `/Applications`, the engine is simply "not installed" there and the exposure shrinks to a CLI user).
- Fix direction: add the `~/Applications` spellings to the one tuple, or take the bundle path from `osaurus doctor`'s `apps[].path`, still matching by full executable path.
- Test idea: `ps` output patched to show `~/Applications/osaurus.app/Contents/MacOS/osaurus`; assert `_resident_osaurus_pids()` returns it. Fails today.

---

## Coverage

Hotspots (20):

1. `_signal_tree` / `_signal_process` `:651-675` — covered (F11)
2. `_resident_osaurus_pids` `:634-648` — covered (F3, F14)
3. `_shutdown` `:1656-1683` — covered (F3, F10, F11)
4. `_kill_resident` `:1617-1635` — covered; pid-only, no new finding
5. `_stop_orphan` `:1827-1864` — covered (F4, F13)
6. `stop_orphaned_engines` `:1867-1905` — covered (F4, F10)
7. `stop_own_engines` `:1908-1940` — covered (F10, F13; the missing identity check is S1-F1)
8. `Runtime.start` `:2267-2362` — covered (F2, F3, F5)
9. Ledger read/write/record `:1693-1783` — covered (F5, F13)
10. `await_ready` `:2197-2251` — covered; no finding. Noted only: with `lsof` unavailable an exited engine is not detected (`None` is not `()`), so the cell waits out the full timeout
11. `_engine_env` `:471-531` — covered (F1, F10)
12. `_resolve_program` `:534-566` — covered; no new finding (bundle paths: F14)
13. `_spawn` `:588-609` — covered (F5, F11)
14. `_serving_pid` `:713-729` — covered; inside the timed window (F2); dead-launcher fallback is S2-F4's ground
15. `Osaurus.check_host_state` `:2694-2712` + `osaurus_settings.py:130-146,387-411` — covered (F8, F9)
16. `pin` `:227-286` — covered (F6, F8); crash ordering inside `pin` traced and sound
17. `_put_back` / `restore` `:289-361` — covered; sound, no new finding
18. `osaurus-pin.sh:31-37,69-84` — covered (F6, F7)
19. `osaurus_set_seqs` `:46-67` — covered (F12)
20. Never-by-name tables `runtimes.py:145-173` — covered (F14); every signal site is by pid or full executable path

Open questions (9):

- Q1 signal by name / `osaurus stop` / pgid — covered: no by-name signal in scope; `osaurus stop` reaching the app is by design; the pgid risk is F11
- Q2 two models resident — covered (F3; contributing paths F4, F5, F14)
- Q3 Osaurus restore skipped on an exit path — covered (F6, F7)
- Q4 plist invisible to the drift gate — covered (F9)
- Q5 `LSOF` ambient PATH — covered; Already known (T-09), not re-reported
- Q6 mlx-lm venv preflight — covered; Already known, not re-reported. F1 is a different defect: the venv is present and is bypassed
- Q7 ledger `stop_command` executed verbatim — covered (F13)
- Q8 `osaurus_set_seqs` non-atomic — covered (F12)
- Q9 dropped orphan entry gone permanently — covered (F4)

