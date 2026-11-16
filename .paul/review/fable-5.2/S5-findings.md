# S5 findings — Runtime lifecycle and host safety

Reviewer: Fable 5.2 (final pass), 2026-11-15.
Scope: `ohyesmlx/runtimes.py`, `ohyesmlx/osaurus_settings.py`, `scripts/osaurus-pin.sh`.
Method: dossier-S5 read whole; source read at the dossier's ranges; leads chased are named in each
finding's Evidence. Nothing was run. Nothing in the dossier's "Already known" list is repeated, and
S1-F1, S1-F2, S2-F3, S2-F4, S2-F10, S3-F3 and S4-F1 are referenced, not re-reported.

14 findings: 2 High, 8 Medium, 4 Low.

---

### F1 — The mlx-lm control cell runs from OptiQ's lab venv on this Mac: lab bins are prefixed to PATH for every engine, and the control's command is a bare `python`
- Severity: High (a published row labelled "mlx-lm 0.31.3" is measured on a build nothing vouched for; breaks "vary one thing at a time")
- Where: `ohyesmlx/runtimes.py:508-531` (`_engine_env`), `:2421-2424` (`MlxLm.start_command`), `:2463-2464` (`MlxLm.version_command`)
- Failure scenario: this Mac's `~/Library/Application Support/OhYesMLX/lab-paths.json` holds exactly `{"optiq": ".../engines/optiq-0.5.13/bin"}`; mlx-lm has no lab entry. Every spawn therefore gets `PATH = <optiq lab bin>:<ambient>`. The control starts as `python -m mlx_lm.server`, and `python` resolves in OptiQ's venv before `~/.local/share/ohyesmlx/mlx-lm-0.31.3/bin` (the venv AGENTS.md names, and the one `run_canary.sh:15` puts on PATH). OptiQ's venv carries mlx-lm 0.31.3 on **mlx 0.32.4**; the mlx-lm venv carries mlx-lm 0.31.3 on **mlx 0.32.2**. The version probe is `python -m mlx_lm --version` through the same PATH, so it reports `0.31.3` either way. Rows measured before the OptiQ lab copy was recorded and rows measured after are joined under one identical stamp while the mlx core under them differs, and nothing in a row says so.
- Evidence: `for name, entry in manifest.items(): ... prefixes.append(resolved)` then `env["PATH"] = os.pathsep.join(prefixes + [ambient])` — one PATH for all engines, no per-engine selection. `return ("python", "-m", "mlx_lm.server", ...)`. The `_engine_env` docstring still says the command begins with the bare name `mlx_lm.server`; the code says `python`, and either name exists in OptiQ's bin (`bin/mlx_lm.server` is there too). Lead chased: this Mac's `lab-paths.json`, the two venvs' `mlx-*.dist-info`, OptiQ venv's `pyvenv.cfg` and `mlx_lm/_version.py`.
- Confidence: 80. Raise to ~97 with `ls -l <optiq lab>/bin/python` (the venv was made by `python -m venv`, which creates it; the Glob tool does not list symlinks) and one `python -c "import mlx.core as mx; print(mx.__version__)"` under the harness's PATH. Whether the mlx 0.32.2 → 0.32.4 step moves tok/s is not measured; the defect is that the harness cannot tell.
- Fix direction: `_engine_env(engine)` prefixes only that engine's lab bin (the caller knows which runtime it is starting); helpers that are not engine commands get no prefix (see F10). Record the mlx core version beside `runtime_version` for the Python runtimes.
- Test idea: `_engine_env` driven with a scratch `lab-paths.json` naming only `optiq`; assert the environment built for the mlx-lm runtime does not contain OptiQ's bin. Fails today.

### F2 — `cold_load_s` includes the version probe and an `lsof` call
- Severity: High (a published metric carries a per-runtime constant that is not load time)
- Where: `ohyesmlx/runtimes.py:2317-2344` (`Runtime.start`), `:2120-2130` (`Runtime.version`)
- Failure scenario: `started = _now()` precedes `_spawn`; inside the timed window come `await_ready(...)`, then `self.version()`, then `_serving_pid(pid, self.port)`, and only then `cold_load_s = _now() - started`. `version()` is a fresh subprocess on every start (no memo): `python -m mlx_lm --version` (a cold Python import of mlx-lm), `osaurus doctor --json --redact`, `optiq --version`, `omlx --version`, each with a 30 s ceiling. AGENTS.md's own example is mlx-lm loading a 35B in 4 s; a 1-2 s interpreter import on top of that is tens of percent, and it differs per runtime, so the cross-runtime cold-load ordering is contaminated by how slow each CLI is to print its version.
- Evidence: the comment at the measurement states the intent and shows the gap: "the ledger entry is written after the load time is taken, so no measured `cold_load_s` contains the `ps` calls" — the version subprocess and the `lsof` call sit before that line. `result = _run(command, VERSION_TIMEOUT_S)` runs unconditionally per start.
- Confidence: 85 on the ordering (read directly). Raise by timing each `version_command` once; the size of the bias is not measured here.
- Fix direction: take `cold_load_s` on the line after `await_ready` returns; do the version probe and `_serving_pid` after it.
- Test idea: a fake runtime whose `version()` advances the injected clock by 5 s; assert `handle.cold_load_s` is unchanged. Fails today.

### F3 — "Exactly one model resident" is checked against the engine's own port and the Osaurus app only, and a failed stop is followed by the next start
- Severity: Medium (two models resident voids every number in the run, silently; AGENTS.md calls such a run void)
- Where: `ohyesmlx/runtimes.py:2267-2316` (pre-start checks in `Runtime.start`), `:634-648` (`_resident_osaurus_pids`, exclusion at `:646`), `:1981-1988` (`Handle.stop`); `ohyesmlx/quickbench.py:703-706`
- Failure scenario: (a) `_shutdown` raises for an Osaurus handle — a transient `lsof` failure gives "cannot identify listeners ...; refusing handoff cleanup", raised before anything is signalled, so the app is still serving with its weights. `Handle.stop` skips its `_RUN_STARTED_PIDS.discard` lines. In quick-bench the exception becomes a FAIL cell (`except Exception` → `_cell_record(... "FAIL")`) and the loop goes on. The next engine's start checks `_port_is_free(<its own port>)` — free — and `_resident_osaurus_pids()` — which skips the survivor because `pid not in _RUN_STARTED_PIDS` is false. Second model loads beside the first. (b) Any engine left on another runtime's port (an orphan F4/F5 could not claim, or the user's own `mlx_lm.server` on 8081) is invisible to a start on 8100.
- Evidence: `_shutdown(self.pid, ...)` is the first statement of `Handle.stop`, the discards follow it; `if pid not in _RUN_STARTED_PIDS and _process_alive(pid)`. Lead chased: `measure.py:843` re-raises `RuntimeStopError` (the CLI run aborts, which is right); quick-bench does not.
- Confidence: 65. Raise by confirming nothing between quick-bench cells aborts the run on a stop failure (only `:650-724` was read).
- Fix direction: before a start, refuse while any `RUNTIMES` port is listening, naming the port; make the discards and the scratch removal a `finally` only when the process is verifiably gone, and make a `RuntimeStopError` end the quick-bench run rather than one cell.
- Test idea: patch `_port_is_free` to return False for 8081 only; assert `Omlx.start` (8100) raises `RuntimeStartError`. Fails today.

### F4 — An orphan entry that cannot be verified is dropped without a word and its ledger file deleted, so the engine is never recoverable
- Severity: Medium (an orphan keeps ~20 GB and its port until reboot; with F3 the next run measures beside it)
- Where: `ohyesmlx/runtimes.py:1827-1864` (`_stop_orphan`), `:1867-1905` (`stop_orphaned_engines`), `:1728-1744` (`_process_identity`)
- Failure scenario: at app launch `lsof` fails once (timeout, or F10's environment refusal) so `listeners is None`; or the recorded `lstart` string does not equal today's. `_stop_orphan` returns silently in each case, nothing raised, so `stop_orphaned_engines` unlinks `<owner>.json`. The engine is alive, holding weights, and no later launch will look at it again. The identity mismatch is not exotic: `ps -o lstart=` renders in the caller's locale and local time, the recorder may be a CLI run in the user's shell and the checker the app backend under launchd's allow-listed environment, and a DST change between record and check moves the rendered hour for the same process.
- Evidence: the three early `return`s in `_stop_orphan` precede `_shutdown`; the caller's loop removes the file unless `RuntimeStopError` was raised; `_run((PS, "-ww", "-o", "lstart=,args=", "-p", ...))` runs with `_engine_env()`, i.e. the ambient `LANG`/`LC_*`/`TZ`.
- Confidence: 75 on the drop-and-delete path (read directly); 50 on locale/DST being hit in practice. Raise with the test below and by diffing `ps -o lstart=` under two `TZ` values.
- Fix direction: run `ps` with `LC_ALL=C TZ=UTC`; when an entry's recorded pid is alive or its port is listening but identity cannot be proved, keep the file and emit one stderr JSON line (the `LEDGER_ERROR_CODE` spelling exists) instead of deleting the only claim.
- Test idea: a ledger entry for a live pid, `_listener_pids` patched to return `None`; call `stop_orphaned_engines`; assert the file still exists. Fails today.

### F5 — An engine is absent from the ledger for its entire load, the longest phase of a start
- Severity: Medium (a backend killed mid-load leaves a detached engine with weights that no launch recovers and "Stop now" cannot reach)
- Where: `ohyesmlx/runtimes.py:2317-2352` (`Runtime.start`), `:588-609` (`_spawn`, `start_new_session=True`)
- Failure scenario: quick-bench starts a 35B; `await_ready` may poll for up to 900 s. The user picks "Quit anyway" (SIGKILL to the backend), or the backend crashes. The engine is in its own session and survives. `_record_running_engine` had not run, so `running-engines/` has no entry: `stop_orphaned_engines` finds nothing at the next launch, and the next run is refused (same port) or runs beside it (other port, F3). W1 records "Stop now does nothing before the entry exists" as pinned in `v5-app.md`; the crash orphan is the same gap and is not pinned anywhere.
- Evidence: `pid = _spawn(...)`; `resolved = self.await_ready(...)`; ... `_record_running_engine(pid, serving_pid, self.port, stop_command)` only after `cold_load_s` is taken, justified by "no measured `cold_load_s` contains the `ps` calls".
- Confidence: 75. Raise with the test below.
- Fix direction: write the entry (pid, port, identity) immediately after `_spawn` and update `serving_pid` after readiness; keep AC-6's promise by timing the ledger write and subtracting it, or by starting the clock after it. One `ps` call is ~10 ms against a load.
- Test idea: `await_ready` patched to raise `KeyboardInterrupt` after asserting the ledger file already names the spawned pid. Fails today (no file yet).

### F6 — The shell pin and the app pin keep the "only copy" in two different directories, so a crashed shell run makes the app back up the pinned state as the user's original and report it restored
- Severity: Medium (the user's Osaurus settings stay at idle 900 / caches off for an unbounded time under a "restored" verdict; consent-and-restore rule)
- Where: `scripts/osaurus-pin.sh:18,31-37` (`BACKUP_DIR="$CONFIG_DIR.phase4-orig"`, trap on `INT TERM HUP` only); `ohyesmlx/osaurus_settings.py:227-286` (`pin` refuses only over a backup in its own `backup_dir`); `ohyesmlx/quickbench.py:95,660-661`; `ohyesmlx/cli.py:1082-1095`
- Failure scenario: a shell runner is pinned and then dies outside the trap (SIGKILL, SIGQUIT, power loss, panic, a `set -u` abort — there is no EXIT trap and no shell path calls `recover`). The host is left pinned; the originals sit in `~/.osaurus/config.phase4-orig`. The user opens the app: launch `recover` looks in `results/osaurus-backup`, finds nothing. Quick-bench then runs `recover` (nothing) and `pin` (no backup in *its* directory, so no refusal), copying the already-pinned files as "the user's settings". After the cell `restore` verifies byte-exact against that copy and sets `summary["osaurus"]["restored"] = True`. The real originals return only if a shell runner with Osaurus is run again (its `osaurus_pin` refuses, `run_canary.sh:37` ignores the status, and the closing `osaurus_restore_check` finds the old backup). The mirror case (backend killed mid-pin, then a shell run) heals at the next app launch, but only while Osaurus is not running.
- Evidence: the refusal message at `osaurus_settings.py:257` is keyed on the directory it was handed; `DEFAULT_BACKUP_DIR = os.path.join(DEFAULT_RESULTS_DIR, "osaurus-backup")`; `trap '...; osaurus_restore; exit 130' INT TERM HUP`. Lead chased: `grep backup_dir` in `quickbench.py`/`cli.py`, and `run_canary.sh` whole (43 lines).
- Confidence: 80 on the two-directory path. Raise by a test with two scratch backup dirs.
- Fix direction: one backup location, defined once in `osaurus_settings` and used by the shell wrapper, quick-bench and launch recovery (or a marker beside the host config naming the live backup, which `pin` refuses over wherever it is). Add `EXIT` to the shell trap.
- Test idea: `pin(backup_dir=A)`, then `pin(backup_dir=B)` on the same config dir; assert the second raises. Fails today (it succeeds and B holds the pinned files).

### F7 — `osaurus_restore_check` returns success and disarms the restoring trap after a FAILED restore, and the abort path prints no verdict at all
- Severity: Medium (the standing authorisation requires "restored and verified byte-exact ... and the report says so"; both paths can end without that being true or said)
- Where: `scripts/osaurus-pin.sh:69-84` (`osaurus_restore_check`), `:24-29` (`osaurus_restore`), `:32` (trap)
- Failure scenario: (a) `s.restore(...)` returns False. The function echoes "RESTORE FAILED ... copies kept" into the runner's log, then executes `trap '...; sweep; exit 130' INT TERM HUP` as its last command — so its exit status is 0, the caller prints `DONE`, the script exits 0, and from then on an interrupt no longer attempts a restore. A coordinator checking the exit code sees a clean run. (b) Ctrl-C mid-run: the trap calls `osaurus_restore`, whose Python is `s.restore(...)` with the boolean discarded, so a restore that did not verify exits 0 and the trap goes on to `exit 130` with neither "restored byte-exact" nor "RESTORE FAILED" printed.
- Evidence: `else echo "RESTORE FAILED: ..."; fi` followed directly by the `trap` line, no `return 1`; `s.restore('$CONFIG_DIR', backup_dir='$BACKUP_DIR')" || return 1` (only an exception is a failure there).
- Confidence: 90 (the script was read whole). Raise by running the function against a scratch config dir with one tampered file.
- Fix direction: one function does the restore and prints the verdict; it returns non-zero on failure and leaves the restoring trap armed; the trap calls that same function. Callers exit non-zero on a failed restore.
- Test idea: shell test with `CONFIG_DIR` pointed at a scratch dir and `osaurus_settings.restore` stubbed to return False; assert `osaurus_restore_check` returns non-zero. Fails today.

### F8 — Every pin re-records the baseline from the live host, so the drift gate compares the host to itself for the whole pinned run, and no snapshot is kept with the results
- Severity: Medium (the 20 tracked keys the pin does not set are never compared with the conditions earlier tables were measured under; "Snapshot it and diff against a checked-in baseline before every run")
- Where: `ohyesmlx/osaurus_settings.py:285` (`write_baseline` at the end of `pin`); `scripts/osaurus-pin.sh:7,65`; `ohyesmlx/runtimes.py:2694-2712` (`check_host_state`)
- Failure scenario: between Tuesday's grid and Thursday's the user changes `generation.streamInterval`, `numberOfThreads`, `performance.compiledDecode` or `mtp.mode` in Osaurus's UI. Thursday's `pin` records Thursday's host as the baseline; `check_host_state` diffs the host against it and finds nothing; the run completes; `restore` puts Tuesday's baseline file back. Both grids pass the gate, neither results directory records the 23 values it ran under, and the tables are joined. Since AGENTS.md routes every Osaurus run through the pin, this is the normal path, not an edge.
- Evidence: the wrapper's own header: "the baseline is re-recorded so the guard passes". Lead chased: `grep capture_osaurus_settings` across `ohyesmlx/*.py` — callers are the refusals, `check_host_state` and quick-bench's mid-run drift check; `measure.py` has no reference, so no header carries the snapshot.
- Confidence: 65. The module says its scope is "drift, not correctness", so part of this may be intended; what would settle it is Jason confirming whether the committed baseline is meant to bind across runs.
- Fix direction: `pin` writes baseline = the committed baseline with only the keys it pins overridden (so any other difference still refuses), and the run header stores the captured snapshot so two runs can be diffed after the fact.
- Test idea: baseline file with `numberOfThreads: 8`, host with `numberOfThreads: 4`; `pin`, then `diff_against_baseline(capture, load_baseline())`; assert the drift names `numberOfThreads`. Fails today (empty drift).

### F9 — Two host settings that change what a cell measures are outside the attestation: the app plist's `disableThinking`, and `concurrency.smeltMode` on any cell without a `stream_experts` pin
- Severity: Medium (a row's TTFT and token counts, or its decode rate, change with nothing in the artifact naming why)
- Where: `ohyesmlx/osaurus_settings.py:40-80` (`TRACKED_KEYS`: two JSON files, no plist, no `smeltMode`); `ohyesmlx/runtimes.py:951-969`, `:2642-2664`
- Failure scenario: (a) `~/Library/Preferences/com.dinoki.osaurus.plist` → `model_options_<modelID>.disableThinking` decides whether the model emits reasoning tokens (`docs/runtimes/osaurus.md:498-527`). Flipping it for one model changes TTFT (reasoning is not content), `completion_tokens` and which channel Decision 119 times, with the gate green — AGENTS.md:92 names "an app plist" as part of what must be snapshotted. (b) `smeltMode` (`engineSelected | disabled | flashMoE | ssdStreaming`) decides how many experts are resident — the Osaurus twin of OptiQ's `--stream-experts auto` hazard. It is read only inside `stream_experts_refusal`, which returns at `if stream_experts is None: return None` before reading it. A default MoE cell on a host at `ssdStreaming` is measured, published, and neither gated nor recorded.
- Evidence: `osaurus_smelt_mode` docstring: "Not one of `osaurus_settings.TRACKED_KEYS`, so the drift gate does not attest it". `grep smelt` in `measure.py`: no match.
- Confidence: 70 for (a) (the plist claim rests on the runtime doc, not on Osaurus source read here); 65 for (b) (raise by confirming MoE cells are not always given a `stream_experts` pin).
- Fix direction: add `concurrency.smeltMode` to `TRACKED_KEYS` and delete the ad hoc reader's sentinel copy; read the plist with stdlib `plistlib` and put the `model_options_*` values for the cell's model in the baseline and the row.
- Test idea: `capture_osaurus_settings()` on a scratch config with `concurrency.smeltMode: "ssdStreaming"`; assert the key is in the capture. Fails today.

### F10 — `lsof`, `ps` and stop commands run under the lab environment, so one engine's lab-path defect disables stopping and recovery for every engine
- Severity: Medium (an engine that cannot be stopped keeps its weights; a start refusal names the wrong engine)
- Where: `ohyesmlx/runtimes.py:569-585` (`_run`), `:511-526` (`_engine_env` loop), `:1656-1662` (`_shutdown`), `:1908-1937` (`stop_own_engines`), `:1867-1905`
- Failure scenario: OptiQ's lab directory is deleted or its mode changes while an Osaurus cell is serving (the user reclaims disk; S1-F7 and S4-F2 describe how the record and the directory fall out of step). `_engine_env` raises `RuntimeStartError` naming optiq; `_run` catches it and returns `None` for `/usr/sbin/lsof` — a system tool that never needed the lab PATH. `_listener_pids` is therefore `None`, and `_shutdown` raises "cannot identify listeners ...; refusing handoff cleanup" for every engine that has a stop command; at launch the same `None` makes F4 delete the ledger. If instead `lab-paths.json` becomes invalid JSON, `lab_paths` raises `ValueError`, which `_run` does not catch: `Handle.stop`, the "Stop now" thread and launch recovery all die with a traceback before signalling anything (both callers catch only `RuntimeStopError`). Separately, the loop walks every engine on every spawn, so a missing OptiQ lab copy refuses an mlx-lm or Osaurus start with a message about OptiQ.
- Evidence: `except (OSError, subprocess.SubprocessError, RuntimeStartError): return None`; `_engine_env` docstring: "raises out of here as `ValueError` rather than becoming 'could not run'" — right for a start, wrong for a stop.
- Confidence: 75. Raise with the test below.
- Fix direction: same change as F1 — the lab prefix is per engine and only for that engine's own commands; `LSOF`/`PS` run with a plain environment. A stop path must never be refusable by configuration.
- Test idea: scratch `lab-paths.json` containing `{`; call `_listener_pids(port)` (or `stop_own_engines` with one ledger entry); assert no exception and a real answer. Fails today (`ValueError`).

### F11 — `Handle.stop` can signal the process group of a stranger that inherited a reaped launcher pid
- Severity: Low (needs pid reuse within one cell; the blast radius is a whole same-user process group)
- Where: `ohyesmlx/runtimes.py:612-631` (`_process_alive`), `:651-659` (`_signal_tree`), `:1663-1672` (`_shutdown`)
- Failure scenario: `osaurus serve` is a launcher that exits after hand-off. `await_ready` polls `_process_alive(pid)`, whose `waitpid(WNOHANG)` reaps it, freeing the pid for reuse while the handle keeps it for the whole cell (minutes, two visits). At stop, `_process_alive(pid)` falls through to `os.kill(pid, 0)`, which succeeds for any same-user process now holding that number; `_signal_tree` then sends SIGTERM and, after the grace period, SIGKILL to `os.getpgid(pid)` — the stranger's group. `_stop_orphan` proves identity before this; the live path does not. Distinct from S1-F1 (stale ledger file).
- Evidence: `os.killpg(os.getpgid(pid), sig)`; no record that the pid was already reaped.
- Confidence: 60 on the logic; the reuse probability on a quiet benchmark Mac is small and unmeasured.
- Fix direction: keep the `Popen` (or a "reaped" flag) on the handle and never signal a pid this process has already reaped; for the Osaurus launcher, signal only `serving_pid` after an identity check.
- Test idea: spawn `true`, let `_process_alive` reap it, patch `os.kill` to succeed for that pid; assert `_shutdown` does not call `os.killpg`. Fails today.

### F12 — `osaurus_set_seqs` rewrites the live host config in place, outside the module that owns the edit
- Severity: Low (a kill between truncate and write leaves an empty `server-runtime.json`; the backup heals it only if a restore then runs — see F6/F7)
- Where: `scripts/osaurus-pin.sh:46-67`
- Failure scenario: `json.dump(runtime, open(conf, 'w'), indent=2)` truncates the user's file before writing, with no temp-and-rename, bypassing `osaurus_settings._write_atomic` and the key list `pin` owns (a second definition of "edit the host and re-record the baseline"). The argument check passes `0` though the message says "positive", so a run can set `maxConcurrentSequences = 0` and re-record it as the baseline.
- Evidence: quoted line; `''|*[!0-9]*)` is the only validation.
- Confidence: 75.
- Fix direction: a `set_key`-style function in `osaurus_settings` (atomic write, read-back, baseline) that both `pin` and the wrapper call; reject 0.
- Test idea: `osaurus_set_seqs 0` against a scratch config; assert non-zero exit. Fails today.

### F13 — The ledger's `stop_command` is data on disk that gets executed
- Severity: Low (same-user tampering only; it is an exec primitive the design does not need)
- Where: `ohyesmlx/runtimes.py:1693-1783` (record/read), `:1827-1864`, `:1908-1937`
- Failure scenario: any same-user process writes `running-engines/<live owner or own pid>.json` with a `stop_command` of its choosing. In `stop_own_engines` it is run with no identity check (S1-F1's path); in `_stop_orphan` it is run once the pid/port identity matches, which an attacker who started the listener controls. Correction to the dossier's Q7: in `_stop_orphan` the identity checks do precede the command; only "Stop now" runs it unchecked.
- Evidence: `_shutdown(pid, port, _entry_stop_command(entry))`.
- Confidence: 60 that it is worth acting on; the fix is a deletion.
- Fix direction: derive the stop command from `RUNTIMES` by the recorded port and delete the field from the ledger.
- Test idea: ledger entry with `stop_command: ["/usr/bin/touch", "<tmp>/x"]` on a matching identity; assert `<tmp>/x` does not exist after `stop_orphaned_engines`. Fails today.

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

Coverage: 29/29.
