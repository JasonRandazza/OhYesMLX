# S1 findings — security and trust boundaries

Reviewer pass over `dossier-S1.md`, 2026-11-14. Source read only at dossier ranges plus named
leads. Nothing was run. Nothing on the dossier's "Already known" list is repeated here.

Verdict in one line: the HTTP guard, token custody, closed job-arg set, hash-pinned installer,
download allowlist and evict containment read as correct. The defects are in **process identity
by pid alone** (F1, F2) and in **job/transfer end-of-life ordering** (F3-F8).

---

### F1 — "Stop now" signals whatever a stale own-pid ledger file names, with no identity check
- Severity: Medium (kills an unrelated same-user process tree and every listener on a recorded port; low probability)
- Where: `ohyesmlx/runtimes.py:1908-1937` (`stop_own_engines`), `:1769-1770` (`_record_running_engine`), `:1890-1891` (`stop_orphaned_engines`)
- Failure scenario: backend with pid N dies without cleanup mid-quickbench (power loss, panic, forced restart, or the app's own "Quit anyway" SIGKILL) and leaves `running-engines/N.json` naming engine pid P, port 8081, and a stop command. A later backend is given pid N (same boot position after a reboot, or pid wrap). At startup `stop_orphaned_engines` skips `N.json` because owner N is alive — it is the backend itself. The first engine start merges the stale entry forward. The user presses Stop now: `_shutdown(P, 8081, <recorded stop command>)` runs the recorded stop command (for an Osaurus entry, `osaurus stop` against the user's own server), SIGTERM/SIGKILLs pid P's tree — now some unrelated process — and kills every listener on 8081.
- Evidence: orphan path gates on `(lstart, argv)`; own path does not: `for entry in _ledger_entries(_ledger_path(root=root)): ... _shutdown(pid, port, _entry_stop_command(entry))`. Stale entries survive: `entries = [entry for entry in _ledger_entries(path) if entry.get("pid") != pid]`. Startup skip: `if _process_alive(int(owner)): continue`. The docstring's premise ("only `<this pid>.json` is read ... the pid this process spawned") is false for a file that predates the process.
- Confidence: 70. Raised by the test below; the pid-collision probability itself is not measured.
- Fix direction: at backend start, treat a pre-existing `<own pid>.json` as an orphan file (run its entries through `_stop_orphan`, then remove it) before any engine can be recorded. Belt and braces: `stop_own_engines` applies `_recorded_identity` before signalling.
- Test idea: write `{"entries":[{"pid": <live unrelated pid>, "port": 59999, "lstart": "x", "argv": "y", "stop_command": []}]}` to `<tmp>/results/running-engines/<os.getpid()>.json`, patch `_shutdown`, call `stop_own_engines(root=tmp)`; assert `_shutdown` was not called. Fails today.

### F2 — Owner liveness is decided by pid alone, so a recycled pid makes a dead owner's lock or ledger permanent
- Severity: Low (stuck state, manual file deletion to recover; no wrong number)
- Where: `ohyesmlx/fetch.py:354-390` (`_pid_alive`, `_acquire_lock`); `ohyesmlx/runtimes.py:612` (`_process_alive`), `:1890-1891`
- Failure scenario: (a) backend pid 734 dies uncleanly during a multi-GB download; after the reboot pid 734 is a system daemon. `os.kill(734, 0)` raises `PermissionError`, which both helpers read as alive, so every later download **and evict** is refused `busy` forever with "another download is already running". (b) Same for `running-engines/734.json`: the file is skipped at every launch, so on a no-reboot pid reuse the orphaned engine keeps its port and ~20 GB of weights and is never recovered — and the next cell then measures with two models resident.
- Evidence: `except PermissionError: return True`; lock file holds only `str(os.getpid())`; ledger owner is only the filename stem.
- Confidence: 75 on the logic; the frequency depends on pid reuse (near-certain for low pids across a reboot, ~1% otherwise).
- Fix direction: record the owner's start time beside its pid (the `ps lstart` helper already exists) and treat a mismatch as dead. For the lock, an `flock` held for the process lifetime removes the question entirely (the Swift side already does this for `app.lock`).
- Test idea: write a lock file naming pid 1; assert `_acquire_lock` reclaims it. Fails today (returns False).

### F3 — A network error mid-body escapes `_fetch_file`: no retry, and the partial is never ledgered
- Severity: Low
- Where: `ohyesmlx/fetch.py:1066-1077` (read loop), `:936-954` (the only `except OSError`), `:1124-1135` (`fetch_file`)
- Failure scenario: a 60 s stall or a reset during a 20 GB file makes `response.read()` raise `TimeoutError`/`ConnectionResetError`/`ssl.SSLError`. Only `open_url` is wrapped, so the exception leaves `_fetch_file`, skips `fetch_file`'s residue bookkeeping, and reaches the server's catch-all as an unexpected error. The four-attempt retry the function is built around never runs for the commonest failure of a long transfer. The multi-GB `.incomplete` is not in `created["blobs"]`, so if the user evicts instead of retrying, evict answers `unknown_repo` or removes nothing and the file has no in-app way out.
- Evidence: `chunk = response.read(CHUNK_SIZE)` sits inside `try: ... finally: _close(response)` with no `except`; `if _fetch_file(planned_file): return True` — the residue append is below it and unreachable on a raise.
- Confidence: 80. Raised by confirming which exception the bundled Python's `HTTPResponse.read(amt)` raises on a short close (b"" on 3.11; not checked for the bundled version).
- Fix direction: catch `OSError` (and `http.client.HTTPException`) around the body read and route it into the same backoff branch as a short transfer; record the residue in a `finally` in `fetch_file`.
- Test idea: fake `open_url` returning a 200 whose `read` yields one chunk then raises `TimeoutError`; assert `download` returns False with an `http_error`/retry rather than raising, and the ledger lists the `.incomplete`.

### F4 — The retry budget is cumulative per file and its exhaustion deletes a valid partial
- Severity: Low (loss of downloaded bytes only)
- Where: `ohyesmlx/fetch.py:1112-1120`, `:916`
- Failure scenario: a 20 GB file on a flaky link is closed early four times across the whole transfer — each time after gigabytes of progress. `attempts` is never reset on progress, so the fourth short close returns `size_mismatch(..., remove=incomplete)` and deletes 19 GB of correctly received bytes. A user cancel keeps the same partial "for a resume"; a network drop destroys it.
- Evidence: `if attempts + 1 >= MAX_ATTEMPTS: return size_mismatch(f"... the transfer ended at {written} of ...", remove=incomplete)`; `attempts = 0` is set once, before `while True`.
- Confidence: 85.
- Fix direction: reset `attempts` whenever a pass wrote bytes, and on exhaustion refuse with `http_error` and keep the partial (it is prefix-valid; `_verify` guards the end). Reserve removal for a real size contradiction.
- Test idea: fake transport that serves 1 byte then closes, four times, on a 10-byte file; assert the `.incomplete` still exists afterwards.

### F5 — `done` frees the job slot before the download's ledger write and lock release
- Severity: Low
- Where: `ohyesmlx/fetch.py:711-718` with `:772`, `:887`, `:1177`; `ohyesmlx/server.py:198-202`
- Failure scenario: `_download` emits `done`; `_Job.append` marks the job finished and frees the slot at once; only then does `download`'s `finally` run `_record` (ledger read + fsynced atomic write) and `_release_lock`. A client that reacts to `done` with the next download or an evict gets a spurious `busy` — the lock still names this live pid — and an evict that wins the lock race before `_record` would not see what was just created. `done` is documented as last; here it is not.
- Evidence: `try: return _download(...) finally: if any(created.values()): _record(...); _release_lock(lock_path)`; `if terminal: self._registry.finished(self)`.
- Confidence: 65. Raised by timing `_record` (fsync) against a loopback POST round trip.
- Fix direction: emit the terminal `done` from `download` after the `finally` work (the pattern `quickbench.py:943-1019` already follows), or have the server free the slot when the job thread returns rather than on the `done` event.
- Test idea: `emit` callback that, on `done`, asserts the lock file is absent and the ledger already lists the repo. Fails today.

### F6 — The event cap ends the job on paper while its worker keeps running, breaking "one job, one model"
- Severity: Low (no module reaches 10,000 events today; this is the guard's own failure mode)
- Where: `ohyesmlx/server.py:185-202`
- Failure scenario: a job hits the cap mid-cell. The server stores `too_many_events` + `done`, sets only `cancel_requested`, and frees the slot. Quickbench honours cancel between cells, so its engine stays resident for the rest of the cell; a second quickbench accepted in that window starts a second runtime — the exact condition the project voids a run for — and its numbers look normal.
- Evidence: `self.cancel_requested = True ... terminal = True ... self._registry.finished(self)`; no `abort_requested`, no `stop_engines`, no wait for the thread.
- Confidence: 55 (reachability: download progress is gated to ≤ ~200 events, install emits a handful, quickbench siblings emit to `_discard`).
- Fix direction: at the cap, keep the slot held until `_run_job` returns (mark the stream done, not the slot free), and set `abort_requested` for a quickbench.
- Test idea: fake module that appends `MAX_EVENTS` events then blocks on an Event; assert a second job create is refused `busy` while it blocks.

### F7 — The lab-path record can refuse after the irreversible install, leaving a venv nothing rolls back or records
- Severity: Low
- Where: `ohyesmlx/engines.py:1294-1295`, `:493-496`
- Failure scenario: `record_lab_path` raises `ValueError` after both pip steps succeeded — the new `bin` is group-writable (umask 002), or the existing `lab-paths.json` holds an entry `lab_paths` refuses (hand edit, a name a later version dropped). `run_steps` has no handler: `created` is discarded with no rollback, no `done` is sent by the installer, and the server reports an unexpected error. The venv stays on disk unrecorded, so cells for that engine cannot start, and a retry either reinstalls over a directory it will never roll back (`existed` is now true) or is refused `already_installed`.
- Evidence: `if installed_bin is not None: record_lab_path(engine, installed_bin, ...)` sits after the step loop, outside any `try`; `check_lab_dir(bin_dir); entries = lab_paths(path)` both raise.
- Confidence: 60. Raised by checking whether `detect_all` reports an unrecorded app-engines venv as installed.
- Fix direction: validate the lab-paths file before the first step (it is a pure read), `chmod 0o755`/0700 the venv root after creation rather than trusting the umask, and route a late refusal through the same rollback + `done` path a failed step takes.
- Test idea: seed `lab-paths.json` with `{"bogus": "/x"}`, run `install` with a fake `run` that creates the venv dir; assert the event stream ends with `error` + `done` and the venv dir is gone.

### F8 — Evict deletes `refs/main` because it once created it, even after another tool rewrote it
- Severity: Low
- Where: `ohyesmlx/fetch.py:871-874` (write + ledger), `:1250-1258` (remove)
- Failure scenario: the app downloads `org/name` and creates `refs/main`. The user later runs `huggingface-cli download org/name`, which rewrites `refs/main` to a newer commit and adds its own snapshot. Evict in the app keeps the shared blobs (reference scan) and the foreign snapshot, but removes `refs/main` unconditionally — a file whose content is no longer what this app wrote. The user's own copy stops resolving by name offline.
- Evidence: `created["links"].append(planned.ref_path)` then `for path in entry["created_links"]: ... os.remove(path)` with no content check. Blobs get a "still referenced" test; the ref does not.
- Confidence: 75.
- Fix direction: remove `refs/main` only when its content still equals the ledger entry's `revision` (the entry already stores it).
- Test idea: download into a temp cache, overwrite `refs/main` with another 40-hex id, evict; assert the file survives.

---

## Considered and not reported

- Shutdown bound expiring mid-quickbench leaves the engine resident: this is T-02 as written (recovery at next launch). Not repeated.
- "Stop now" racing the cell's own stop: benign — it kills this process's engine and the cell records ABORTED.
- Client-supplied job `name` in the stderr job line: JSON-encoded, token holder only.
- `check_lab_dir` checks the directory but not its parents: needs another account with write on a parent and a victim-owned look-alike directory; not actionable on a single-user Mac.
- Token transport on the Swift side is `URLSession.shared` (default disk `URLCache`, system proxy config). Whether `Cache.db` retains the `Authorization` header was not established; the token is per-launch. An ephemeral session with no cache would close the question cheaply.

## Coverage:

Hotspots
1. `_guard` — covered (correct as read: exact Host, any Origin refused, constant-time bearer)
2. `make_server` token custody — covered
3. closed job args — covered
4. `_job_body` — covered
5. cancel / abort — covered
6. shutdown path (server + `kill_running_steps`) — covered (residual is T-02, known)
7. caps (events, streams, threads) — covered (F6)
8. `_command_plan` — covered
9. `_check_hashed_requirements` — covered (grammar refuses option lines, unhashed pins, EOF continuation)
10. rollback / lab-path record — covered (F7)
11. `run_guided` URL gate — covered
12. `check_lab_dir` / `record_lab_path` — covered
13. fetch allowlist / redirect guard — covered
14. `plan` — covered
15. `_verify` — covered
16. `_fetch_file` — covered (F3, F4)
17. `evict` — covered (F8)
18. `_stop_orphan` / `stop_orphaned_engines` — covered (F2)
19. `stop_own_engines` / `_shutdown` — covered (F1)
20. launch seam — covered for `cli.py:1108-1170` and `BackendLauncher.swift:150-275`; `LaunchSession` teardown (`:277-528`) not read

Open questions
- Q1 guard bypass via stdlib dispatch — covered by reading the handler (fail-closed); no adversarial request was sent, per the no-run rule
- Q2 Host edge cases / duplicate headers — covered by reading (tuple match on the first header value); not exercised
- Q3 pid recycling + stale own ledger — covered: confirmed, F1
- Q4 residual PyPI / standalone-Python hash verification — covered: pins validated before the venv exists; `fetch_python_standalone.sh` checks sha256 before `tar` (`:53-73`, read by grep, not whole)
- Q5 malicious HF repo / catalog — covered for code (`plan` refuses every hostile literal; bytes are hash-pinned); the catalog-change review process is not something the code answers
- Q6 `_acquire_lock` race with app + CLI coexisting — covered: disposition unchanged (double-hold fails safe: a corrupted partial fails `_verify`); the new problem is F2, not the race
- Q7 readers of `BackendToken.raw` — covered: one, `HTTPBackend.makeRequest:182`
- Q8 `_real_open` with no timeout — covered: no finding; a hung `/usr/bin/open` would hold the job slot and is not in the kill registry, but nothing shows it hangs
- Q9 TOCTOU / log append-through-symlink — covered: `_append_install_log` is a plain `open("a")`; same-user only, stays under T-14
- Q10 file modes under App Support — covered: root forced 0700 by `ensure_app_support`; `atomic_write_text` files are 0600; lock and running-engines files are umask-default inside the 0700 root (in a checkout they sit under the repo instead)

Coverage: 30/30 (hotspot 20 partial as noted).
